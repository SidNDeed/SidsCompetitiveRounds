"""#scr-leaderboard publishes every board (v1.41.0 item 1).

The bot cannot be run here, so this is how the change is checked without a
live Discord. discord_bot.py is not importable in a test process (it builds
the bot at import), so the publisher, the board catalogue and the row
renderers are lifted out of its AST, stripped of their harness decorators and
EXECUTED against fakes for the bot, the channel, api_get and the discord
namespace — the same lift the mail-bot tests use.

Two contracts are checked against the SERVER rather than against a copy:
every board's path and query parameters are resolved on the api's own route
table, and every row renderer may read only fields that the endpoint's
response model in schemas.py declares. A renderer copied from the 1v1 shape
fails that second check, which is its negative control.
"""

import ast
import asyncio
import copy
import datetime as _dt
import os
import re
import types
from pathlib import Path

import pytest

# The real library, for the two things a copy of them would prove nothing
# about: the exception classes publish_boards now branches on, and
# escape_markdown. A hand-rolled NotFound would be a fixture agreeing with the
# code by construction -- it would still pass if production raised something
# else entirely -- and a hand-rolled escaper would test the copy, not the
# escaping. The rest of the discord surface stays faked; discord_bot.py itself
# is still not importable (it builds the bot at import).
import discord

import main
import schemas

SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "discord_bot.py"))
TEXT = open(SRC, encoding="utf-8").read()
TREE = ast.parse(TEXT)

WANT_FUNC = {"rank_emoji", "get_rank_name", "_lb_name", "_lb_line",
             "_split_lb_descriptions",
             "_build_board_embeds", "_board_medal", "_lb_line_2v2", "_lb_line_ffa", "_lb_line_ovt",
             "_enabled_boards", "_render_board", "_reconcile_board_messages",
             "_repost_board_set", "_delete_board_message",
             "publish_boards", "publish_lb_loop"}
WANT_CLASS = {"LeaderboardPaginator"}
WANT_ASSIGN = {"RANK_ROLES", "LB_PAGE_SIZE", "LB_TOTAL_FETCH", "BOARDS",
               "_lb_message_ids", "_lb_unknown_board_keys",
               "LB_RECONCILE_CEILING", "_LB_NAME_BREAKS"}

# The owed-delete queue is GONE. Asserted rather than assumed: the mechanism
# produced a HIGH and two MEDIUMs inside its own fix, so it was deleted rather
# than patched a third time, and what makes that deletion real is that no name
# of it survives anywhere in the module. The channel is now the only record of
# what still needs deleting.
GONE_FROM_SOURCE = ["_lb_pending_deletes", "LB_PENDING_DELETE_CAP",
                    "_remember_pending_delete", "_cancel_owed_deletes_for_live_boards",
                    "_retry_pending_deletes", "_adopt_board_messages",
                    "_boards_are_anchored", "LB_HISTORY_SCAN"]

CID = 777

# The EXACT urls the boards must request, written out rather than read off
# BOARDS. A fixture keyed on the code under test agrees with it by
# construction: the fake used to answer by PATH, so min_series=1 -> 999 or
# role=combined -> solo resolved to the same rows and published the wrong
# population with every assertion still green. Declaring the whole url means
# a changed query value finds no payload at all.
U_1V1 = "/leaderboard?limit=500&min_matches=1"
U_2V2 = "/team/leaderboard?limit=500&min_series=1"
U_FFA = "/ffa/leaderboard?limit=500&min_games=1"
U_OVT = "/ovt/leaderboard?limit=500&role=combined"
P_1V1 = "/leaderboard?limit=1&min_matches=1&include_inactive=true"
P_2V2 = "/team/leaderboard?limit=1&min_series=1&include_inactive=true"
P_FFA = "/ffa/leaderboard?limit=1&min_games=1&include_inactive=true"

T_1V1 = "🏆 Ranked Leaderboard"
T_2V2 = "👥 2v2 Ranked Leaderboard"
T_FFA = "🎯 FFA Ranked Leaderboard"


def _run(coro):
    return asyncio.run(coro)


# ── fakes: the discord surface the lifted code touches ────────────────────

class _Embed:
    def __init__(self, title=None, description=None, color=None, timestamp=None):
        self.title, self.description, self.color, self.timestamp = title, description, color, timestamp
        self.footer = None

    def set_footer(self, text=None):
        self.footer = text


def _not_found(what="Unknown Message"):
    """The real discord.NotFound, built the way the library builds it."""
    return discord.NotFound(types.SimpleNamespace(status=404, reason="Not Found"), what)


class _Button:
    def __init__(self, label=None, style=None, custom_id=None, **kw):
        self.label, self.style, self.custom_id = label, style, custom_id
        self.disabled = False
        self.callback = None


def _button(**kw):
    def deco(fn):
        fn.__button_kw__ = kw
        return fn
    return deco


class _View:
    """discord.ui.View enough for these views: children in DEFINITION order,
    each bound to its decorated method, as discord.py builds them."""

    def __init__(self, timeout=None):
        self.timeout = timeout
        self.children = []
        for klass in reversed(type(self).__mro__):
            for name, attr in vars(klass).items():
                kw = getattr(attr, "__button_kw__", None)
                if kw is not None:
                    btn = _Button(**kw)
                    btn.callback = getattr(self, name)
                    self.children.append(btn)


FAKE_DISCORD = types.SimpleNamespace(
    Embed=_Embed, Interaction=object,
    ButtonStyle=types.SimpleNamespace(secondary="secondary"),
    Color=types.SimpleNamespace(gold=lambda: "gold", blurple=lambda: "blurple",
                                orange=lambda: "orange", teal=lambda: "teal"),
    ui=types.SimpleNamespace(View=_View, Button=_Button, button=_button),
    # Real, not faked: the publisher branches on these classes and escapes
    # with this function, so a stand-in would only ever confirm itself.
    utils=discord.utils,
    NotFound=discord.NotFound, Forbidden=discord.Forbidden,
    HTTPException=discord.HTTPException)


class _Msg:
    _next = 5000

    def __init__(self, ch, author, embeds, view):
        _Msg._next += 1
        self.id, self.ch, self.author, self.embeds, self.view = _Msg._next, ch, author, embeds, view
        self.edits = []

    @property
    def components(self):
        """discord.py's own Message.components for a message sent or last
        edited with a view: the library's ActionRow, built from the payload
        Discord returns (one row of buttons, each with the custom_id the view
        gave it), so the identity read runs against the real component
        classes and not a stand-in that could only confirm itself. A message
        sent with no view has none -- the shape of a board posted before the
        key marker existed."""
        if self.view is None:
            return []
        return [discord.components.ActionRow({"type": 1, "components": [
            {"type": 2, "style": 2, "label": c.label or "", "custom_id": c.custom_id}
            for c in self.view.children]})]

    async def edit(self, **kw):
        if self.id in self.ch.edit_fails:
            raise RuntimeError("503 Service Unavailable")
        if self.id not in {m.id for m in self.ch.messages}:
            raise _not_found("Unknown Message")
        self.edits.append(kw)
        self.embeds = kw.get("embeds", self.embeds)
        self.view = kw.get("view", self.view)

    async def delete(self):
        # An already-deleted message is a NotFound, not a refusal -- the two
        # are different answers to "do we still owe this delete?".
        if self.id not in {m.id for m in self.ch.messages}:
            raise _not_found("Unknown Message")
        if self.id in self.ch.delete_fails:
            raise RuntimeError("403 Missing Permissions")
        self.ch.deleted.append(self.id)
        self.ch.messages = [m for m in self.ch.messages if m.id != self.id]
        # The absence watch: a delete that leaves a watched board with no
        # message on the channel AT ALL is recorded at the moment it happens,
        # so "never absent" is a reading of every intermediate state rather
        # than of the state a tick ends in.
        left = set(self.ch.titles())
        for title in self.ch.must_stay:
            if title not in left:
                self.ch.absences.append((title, self.id))


class _Channel:
    """Messages oldest-first, the way the channel reads top to bottom."""

    def __init__(self, cid, bot_user):
        self.id, self.bot_user = cid, bot_user
        self.messages, self.deleted, self.sent = [], [], []
        self.history_raises = False
        # A history read that dies PART-WAY, after the scan has already acted
        # on some of what it saw. Discord pages history, so a read that
        # succeeds for the first page and 500s on the second is an ordinary
        # failure -- and it leaves the scan holding work it has done and
        # keepers it has not merged. `history_raises` alone only ever models
        # the read failing before it yields anything.
        self.history_raises_after = None
        self.fetch_fails_once = set()
        # A message that is on the channel when the tick READS it and gone by
        # the time the tick fetches it to edit -- a moderator, or another
        # process, in the gap. Discord answers that fetch with a 404, so the
        # message is removed here and NotFound raised, which is the only
        # failure that says a replacement is needed.
        self.vanish_on_fetch = set()
        # A message the READ yields and that is gone the moment after: the
        # read has handed it over, and before the tick acts on anything a
        # moderator or a second process removes it. This is the gap between
        # a read and every decision made from it -- the gap the round 3 H1
        # race lived in -- driven deterministically.
        self.vanish_after_read = set()
        # Titles that must never have NO message on the channel; any delete
        # that leaves one of them absent is recorded in `absences`.
        self.must_stay = set()
        self.absences = []
        # A live channel refuses sends, edits and deletes: a 5xx, a rate
        # limit, a revoked Manage-Messages. Without these the repost path --
        # the only code here that REMOVES a message -- has no failing case in
        # the suite, and a check that cannot fail is worse than none (#342).
        self.send_fails_for_titles = set()
        self.delete_fails = set()
        self.edit_fails = set()
        # The READ's cost, counted where Discord would bill it: one per REST
        # request discord.py's own paging makes (GET .../messages, at most
        # 100 messages each). An in-memory iterator could not show that one
        # `history()` call is many requests on a long channel.
        self.history_requests = 0
        self._state = types.SimpleNamespace(
            http=types.SimpleNamespace(logs_from=self._logs_from),
            create_message=lambda channel, data: data["msg"])

    async def _get_channel(self):
        return self

    async def _logs_from(self, channel_id, limit, before=None, after=None, around=None):
        """GET /channels/{id}/messages as discord.py's paging calls it: newest
        first, at most `limit` (never over 100) messages older than `before`."""
        self.history_requests += 1
        if self.history_raises:
            raise RuntimeError("history boom")
        assert after is None and around is None, "the reconcile read pages backwards only"
        assert 1 <= limit <= 100, limit
        newest_first = list(self.messages)[::-1]
        if before is not None:
            # Paging resumes by id, as Discord's does: real ids are snowflakes,
            # in channel order. A test that reorders messages stays on one page.
            ids = [m.id for m in self.messages]
            assert ids == sorted(ids), "paged past a channel whose ids are out of order"
            newest_first = [m for m in newest_first if m.id < before]
        return [{"id": str(m.id), "msg": m} for m in newest_first[:limit]]

    async def send(self, embeds=None, view=None):
        title = embeds[0].title if embeds else None
        if title in self.send_fails_for_titles:
            raise RuntimeError("503 Service Unavailable")
        m = _Msg(self, self.bot_user, embeds, view)
        self.messages.append(m)
        self.sent.append(m)
        return m

    def post_from_someone_else(self):
        m = _Msg(self, "chatter", [], None)
        self.messages.append(m)
        return m

    async def fetch_message(self, mid):
        # A transient refusal and an absent message are DIFFERENT answers, and
        # the publisher now acts on the difference: only "it is gone" may cost
        # a message its id. A fake that raised the same thing for both made
        # every transient blip look like a deletion.
        if mid in self.fetch_fails_once:
            self.fetch_fails_once.discard(mid)
            raise RuntimeError("429 rate limited")
        if mid in self.vanish_on_fetch:
            self.vanish_on_fetch.discard(mid)
            self.messages = [m for m in self.messages if m.id != mid]
            raise _not_found(f"Unknown Message {mid}")
        for m in self.messages:
            if m.id == mid:
                return m
        raise _not_found(f"Unknown Message {mid}")

    def history(self, limit=100):
        """discord.py's OWN Messageable.history -- the library's paging, over
        _logs_from -- with this fake's failure and timing levers around it. A
        `history_raises` read fails on its first request, as a real one does
        (the call itself does no I/O); a part-way failure is modelled at any
        message, which covers the real one at a page boundary."""
        pages = discord.abc.Messageable.history(self, limit=limit)

        async def gen():
            i = 0
            async for m in pages:
                if self.history_raises_after is not None and i >= self.history_raises_after:
                    raise RuntimeError("history boom part-way")
                yield m
                i += 1
                if m.id in self.vanish_after_read:
                    self.vanish_after_read.discard(m.id)
                    self.messages = [x for x in self.messages if x.id != m.id]
        return gen()

    def titles(self):
        return [(m.embeds[0].title if m.embeds else None) for m in self.messages]


class _Bot:
    def __init__(self, ch, guilds=1):
        self.user, self.ch = "scr-bot", ch
        self.fetch_channel_calls = 0
        # Only the FIRST guild owns the channel. bot.fetch_channel answers for
        # any of them, which is what made a per-guild publish loop publish the
        # same three boards once per guild.
        self.guilds = [types.SimpleNamespace(
            get_channel=(lambda cid, own=(i == 0): ch if (own and cid == CID) else None))
            for i in range(guilds)]

    def get_channel(self, cid):
        return self.ch if cid == CID else None

    async def fetch_channel(self, cid):
        self.fetch_channel_calls += 1
        return self.ch if cid == CID else None


class _Api:
    """api_get, answering by EXACT url only.

    Two things here are copies of production behaviour rather than
    conveniences, and both were defects when they were conveniences:

    (1) api_get CANNOT PROPAGATE. It wraps the whole request in try/except,
        prints "API GET error: ..." and returns None (discord_bot.py:292), and
        returns None with a printed status on any non-200. So a transport
        failure is modelled by an Exception payload that this fake CATCHES and
        reports exactly as api_get does -- never by raising into the caller.
        Raising put the suite on paths no network failure can reach, and left
        the paths real failures DO take covered only by accident.

    (2) A url the fixture did not declare answers None and is recorded in
        `unexpected`. Resolving it by path instead meant the query string was
        never part of the contract: a board that asked for min_series=999 or
        role=solo got the same rows and published the wrong population with
        every assertion still green.
    """

    def __init__(self, payloads, log=None):
        self.payloads, self.calls = dict(payloads), []
        self.unexpected = []
        self.log = [] if log is None else log

    async def get(self, path, timeout=8.0):
        self.calls.append(path)
        if path not in self.payloads:
            self.unexpected.append(path)
            self.log.append(f"API GET {path.split('?')[0]} -> HTTP 404")
            return None
        val = self.payloads[path]
        if isinstance(val, Exception):
            self.log.append(f"API GET error: {val}")
            return None
        if val is None:
            self.log.append(f"API GET {path.split('?')[0]} -> HTTP 503")
        return val


class _Interaction:
    def __init__(self):
        self.edits = []

        async def edit_message(**kw):
            self.edits.append(kw)
        self.response = types.SimpleNamespace(edit_message=edit_message)


# ── lifting ───────────────────────────────────────────────────────────────

def _lift():
    picked, seen = [], set()
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in WANT_ASSIGN:
                    picked.append(node)
                    seen.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in WANT_ASSIGN:
            picked.append(node)
            seen.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in WANT_FUNC:
            fn = copy.deepcopy(node)
            fn.decorator_list = []                     # @tasks.loop is the harness's
            picked.append(fn)
            seen.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name in WANT_CLASS:
            picked.append(copy.deepcopy(node))
            seen.add(node.name)
    want = WANT_FUNC | WANT_ASSIGN | WANT_CLASS
    assert seen == want, want - seen
    return picked


def _bot_ns(api, bot, boards_raw="1v1,2v2,ffa", out=None):
    """A fresh namespace per test — _lb_message_ids and the unknown-key set
    are real process state and must never be shared between ticks of
    different tests."""
    out = out if out is not None else []
    api.log = out                     # api_get prints into the same log the bot does
    ns = {"discord": FAKE_DISCORD, "os": os, "re": re, "bot": bot, "api_get": api.get,
          "datetime": _dt.datetime, "timezone": _dt.timezone,
          "LEADERBOARD_CHANNEL_ID": CID, "LB_ACTIVE_DAYS": 90,
          "LEADERBOARD_BOARDS_RAW": boards_raw,
          "print": lambda *a, **k: out.append(" ".join(str(x) for x in a))}
    exec(compile(ast.Module(body=_lift(), type_ignores=[]), SRC, "exec"), ns)
    ns["_log"], ns["_api"], ns["_ch"] = out, api, bot.ch
    ns["_bot"] = bot
    return ns


# ── rows, shaped like the endpoints' response models ──────────────────────

def _rows_1v1(n=3):
    return [{"rank": i + 1, "steam_id": f"7656119804041065{i}", "display_name": f"Player{i}",
             "rating": 1700 - i, "rd": 60, "total_matches": 25, "wins": max(0, 20 - i), "losses": 5,
             "win_rate": 0.8} for i in range(n)]


def _rows_2v2(n=3):
    return [{"rank": i + 1, "steam_id": f"7656119804041065{i}", "display_name": f"Duo{i}",
             "rating": 1650 - i, "rd": 70, "peak_rating": 1700, "completed_series": 12,
             "series_wins": max(0, 8 - i), "series_losses": 4, "win_rate": 0.667} for i in range(n)]


def _rows_ffa(n=3):
    return [{"rank": i + 1, "steam_id": f"7656119804041065{i}", "display_name": f"Ffa{i}",
             "rating": 1580 - i, "rd": 80, "peak_rating": 1600, "games_played": 30,
             "wins": max(0, 9 - i), "top3": 18, "avg_placement": 2.44, "win_rate": 0.3} for i in range(n)]


def _rows_ovt(n=3):
    return [{"rank": i + 1, "steam_id": f"7656119804041065{i}", "display_name": f"Ovt{i}",
             "games_played": 34, "wins": max(0, 20 - i), "losses": 14, "win_rate": 58.8,   # PERCENT: 1v2 is the one board that pre-scales
             "solo_games": 12, "duo_games": 22} for i in range(n)]


def _payloads(n=3, broken=None):
    """Every url the publisher may ask for, keyed WHOLE. Anything else the
    code asks for answers None and lands in _Api.unexpected."""
    p = {U_1V1: {"entries": _rows_1v1(n), "total_players": 120},
         U_2V2: {"entries": _rows_2v2(n), "total_players": 40},
         U_FFA: {"entries": _rows_ffa(n), "total_players": 25},
         U_OVT: {"entries": _rows_ovt(n), "total_players": n},
         # The inactive probes answer the SAME population as their board, so
         # no footer suffix appears unless a test asks for one.
         P_1V1: {"entries": _rows_1v1(1), "total_players": 120},
         P_2V2: {"entries": _rows_2v2(1), "total_players": 40},
         P_FFA: {"entries": _rows_ffa(1), "total_players": 25}}
    p.update(broken or {})
    return p


def _fresh(n=3, broken=None, boards_raw="1v1,2v2,ffa"):
    api = _Api(_payloads(n, broken))
    return _bot_ns(api, _Bot(_Channel(CID, "scr-bot")), boards_raw=boards_raw)


@pytest.fixture
def ns():
    return _fresh()


def _tick(ns):
    _run(ns["publish_boards"]())


# ── reachability: the code under test is the code that runs ───────────────

def test_the_loop_publishes_the_set_and_the_single_board_publisher_is_gone():
    fn = next(n for n in TREE.body
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "publish_lb_loop")
    assert [ast.unparse(d) for d in fn.decorator_list] == ["tasks.loop(minutes=10)"]
    # ONE publish per tick, asked of the AST rather than of the text: the
    # first version of this check grepped the unparsed function for
    # "bot.guilds" and was failed by its own docstring, which names the
    # defect. Structure cannot be satisfied -- or refuted -- by prose.
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "publish_boards"]
    assert len(calls) == 1, f"publish_lb_loop calls publish_boards {len(calls)} times"
    assert not calls[0].args and not calls[0].keywords, (
        "publish_boards takes no argument: LEADERBOARD_CHANNEL_ID names one "
        "channel and the publisher resolves it itself")
    assert not [n for n in ast.walk(fn) if isinstance(n, (ast.For, ast.AsyncFor))], (
        "publish_lb_loop is looping again. It used to loop over bot.guilds and "
        "publish per guild against the same global channel id, and "
        "bot.fetch_channel answers for ANY guild -- so every extra guild "
        "repeated the whole tick against the same three messages")
    assert re.search(r"publish_lb_loop\.start\(\)", TEXT)
    # No caller left pointing at the single-board publisher, and no half-done
    # rename: both old names are gone from the file.
    assert not re.search(r"\bpublish_lb\s*\(", TEXT)
    assert "_build_lb_embeds" not in TEXT


# ── the catalogue, against the api's own route table ──────────────────────

def _route_params(path):
    for r in main.app.routes:
        if getattr(r, "path", None) == path and "GET" in (getattr(r, "methods", None) or set()):
            code = r.endpoint.__code__
            return set(code.co_varnames[:code.co_argcount])
    return None


# What each board must ASK FOR, values included. The previous version of
# this check read the parameter NAMES out of whatever the catalogue happened
# to send and confirmed the endpoint declares them -- so min_series=1 -> 999,
# or role=combined -> solo, passed while the channel published a different
# population. Values are the contract; names are only half of it.
BOARD_QUERIES = {
    "1v1": ("/leaderboard", {"limit": "500", "min_matches": "1"}),
    "2v2": ("/team/leaderboard", {"limit": "500", "min_series": "1"}),
    "ffa": ("/ffa/leaderboard", {"limit": "500", "min_games": "1"}),
    "1v2": ("/ovt/leaderboard", {"limit": "500", "role": "combined"}),
}
PROBE_QUERIES = {
    "1v1": ("/leaderboard", {"limit": "1", "min_matches": "1", "include_inactive": "true"}),
    "2v2": ("/team/leaderboard", {"limit": "1", "min_series": "1", "include_inactive": "true"}),
    "ffa": ("/ffa/leaderboard", {"limit": "1", "min_games": "1", "include_inactive": "true"}),
    "1v2": None,
}


def _split_url(url):
    route, _, query = url.partition("?")
    return route, dict(p.split("=", 1) for p in query.split("&") if p)


def test_every_board_url_resolves_on_the_api_with_the_params_and_values_it_sends(ns):
    """Every board's url, whole: route, parameter names, parameter VALUES.

    Two different failures are covered. A param the endpoint does not declare
    is dropped silently and the board publishes the UNFILTERED answer (bug
    #266's class -- the deployed-but-stale api that answers 200 and ignores a
    query parameter it does not know; see docs/deploy-reference.md). And a
    param whose VALUE moves publishes a different population from the one
    this channel is supposed to show, with no error anywhere.
    """
    seen = set()
    for b in ns["BOARDS"]:
        seen.add(b["key"])
        route, params = _split_url(b["path"])
        assert (route, params) == BOARD_QUERIES[b["key"]], (
            "%s board now requests %s %s" % (b["key"], route, params))
        declared = _route_params("/api/v1" + route)
        assert declared is not None, f"{b['key']}: no GET route /api/v1{route}"
        for name in params:
            assert name in declared, f"{b['key']}: /api/v1{route} takes no '{name}'"

        want_probe = PROBE_QUERIES[b["key"]]
        if want_probe is None:
            assert b["probe"] is None, f"{b['key']}: gained a probe with no contract here"
            continue
        proute, pparams = _split_url(b["probe"])
        assert (proute, pparams) == want_probe, (
            "%s probe now requests %s %s" % (b["key"], proute, pparams))
        for name in pparams:
            assert name in (_route_params("/api/v1" + proute) or set()), (
                f"{b['key']}: probe route /api/v1{proute} takes no '{name}'")
    assert seen == set(BOARD_QUERIES), "a board was added or removed without a url contract"


def test_the_board_minimums_are_the_ones_the_client_sees(ns):
    """#153, checked rather than asserted in a comment.

    "Matches the visible leaderboard" means matching what CALLERS PASS. The
    three boards differ and the difference is the whole point:

      1v1  /leaderboard's own default is 5; every real caller passes 1, so
           the board MUST pass 1 too or it shows a different population from
           the one the F5 client shows.
      2v2  their defaults are already 1 and the F5 client passes neither, so
      FFA  the board's explicit 1 must EQUAL that default -- if someone
           raises either default, this board silently stops matching the
           client and this assertion is what says so.
      1v2  has no minimum at all, so the catalogue comment may not claim one.
    """
    import inspect

    def _declared_default(path, param):
        for r in main.app.routes:
            if getattr(r, "path", None) == path and "GET" in (getattr(r, "methods", None) or set()):
                p = inspect.signature(r.endpoint).parameters.get(param)
                assert p is not None, f"{path} declares no {param}"
                return getattr(p.default, "default", p.default)
        raise AssertionError(f"no GET route {path}")

    by_key = {b["key"]: dict(_split_url(b["path"])[1]) for b in ns["BOARDS"]}
    assert _declared_default("/api/v1/leaderboard", "min_matches") == 5
    assert by_key["1v1"]["min_matches"] == "1", (
        "the 1v1 board must pass min_matches=1: the endpoint defaults to 5 and "
        "every real caller passes 1 (#153)")
    for path, param, key in (("/api/v1/team/leaderboard", "min_series", "2v2"),
                             ("/api/v1/ffa/leaderboard", "min_games", "ffa")):
        assert str(_declared_default(path, param)) == by_key[key][param], (
            "%s board sends %s=%s while %s now defaults to %r; the F5 client "
            "passes neither, so the board and the client no longer show the "
            "same population (#153)"
            % (key, param, by_key[key][param], path, _declared_default(path, param)))
    ovt_params = _route_params("/api/v1/ovt/leaderboard") or set()
    assert not {p for p in ovt_params if p.startswith("min_")}, (
        "/ovt/leaderboard now takes a minimum; the 1v2 board must pass it and "
        "the catalogue comment that says it has none must change")


def test_catalogue_keys_titles_and_the_default_set(ns):
    keys = [b["key"] for b in ns["BOARDS"]]
    titles = [b["title"] for b in ns["BOARDS"]]
    assert keys == ["1v1", "2v2", "ffa", "1v2"]
    assert len(set(titles)) == len(titles) and all(titles)
    # The 1v1 title is unchanged, so the first tick after the deploy ADOPTS
    # the board already in the channel instead of posting a second one.
    assert ns["BOARDS"][0]["title"] == T_1V1
    assert [b["key"] for b in ns["_enabled_boards"]()] == ["1v1", "2v2", "ffa"]
    assert re.search(r'os\.getenv\("LEADERBOARD_BOARDS", "1v1,2v2,ffa"\)', TEXT)
    assert all(b["path"].startswith("/") and "limit=500" in b["path"] for b in ns["BOARDS"])


def test_env_list_sets_order_and_names_an_unknown_key():
    out = []
    n2 = _bot_ns(_Api(_payloads()), _Bot(_Channel(CID, "scr-bot")),
                 boards_raw=" FFA , 1v2 ,records, ffa ", out=out)
    assert [b["key"] for b in n2["_enabled_boards"]()] == ["ffa", "1v2"]   # env order, deduped
    assert any("no such board: records" in ln for ln in out), out
    out.clear()
    n2["_enabled_boards"]()
    assert out == []            # named once, not once every ten minutes


# ── row renderers: only their own endpoint's fields ───────────────────────

class _Watch(dict):
    """Records every field a renderer reads, by BOTH access shapes.

    Bracket access alone was not enough. A renderer reaching for
    e.get("bogus") was invisible to the field check below, and .get is
    exactly the shape a line copied from another board tends to arrive in --
    it is also the shape that returns None instead of raising, so the row
    would publish a column of "None" rather than failing its render.
    test_the_field_watch_sees_dict_get is its negative control.
    """

    def __init__(self, d):
        super().__init__(d)
        self.read = set()

    def __getitem__(self, k):
        self.read.add(k)
        return super().__getitem__(k)

    def get(self, k, default=None):
        self.read.add(k)
        return super().get(k, default)


@pytest.mark.parametrize("renderer,rows,model", [
    ("_lb_line", _rows_1v1, schemas.LeaderboardEntry),
    ("_lb_line_2v2", _rows_2v2, schemas.Team2v2LeaderboardEntry),
    ("_lb_line_ffa", _rows_ffa, schemas.FfaLeaderboardEntry),
    ("_lb_line_ovt", _rows_ovt, schemas.Ovt1v2LeaderboardEntry),
])
def test_renderer_reads_only_fields_its_endpoint_returns(ns, renderer, rows, model):
    row = rows(1)[0]
    model(**row)                                     # the test row IS that endpoint's shape
    watched = _Watch(row)
    line = ns[renderer](watched, 1)
    assert watched.read, "renderer read nothing"
    missing = watched.read - set(model.model_fields)
    assert not missing, f"{renderer} reads {missing}, which {model.__name__} does not return"
    assert row["display_name"] in line and line.startswith("`#  1`")


def _renderer_source(ns, name):
    """Source text of one row renderer, for the sibling sweep."""
    import inspect
    return inspect.getsource(ns[name])


_MAIN_INDEX = {}


def _main_index():
    """main.py's text and every def in it, as (first line, last line, name).

    Parsed once: main.py is ~53k lines and two tests want the same answer.
    """
    if not _MAIN_INDEX:
        import io as _io
        from pathlib import Path
        src = _io.open(Path(__file__).resolve().parents[1] / "api" / "main.py",
                       encoding="utf-8", newline="").read()
        spans = sorted((n.lineno, n.end_lineno or n.lineno, n.name)
                       for n in ast.walk(ast.parse(src))
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        _MAIN_INDEX["src"], _MAIN_INDEX["spans"] = src, spans
    return _MAIN_INDEX["src"], _MAIN_INDEX["spans"]


def _enclosing_def(offset):
    """Name of the INNERMOST def containing a character offset in main.py."""
    src, spans = _main_index()
    line = src.count("\n", 0, offset) + 1
    best = None
    for lo, hi, name in spans:
        if lo <= line <= hi and (best is None or lo >= best[0]):
            best = (lo, name)
    return best[1] if best else None


def _def_source(name):
    """The source of main.py's one def called `name`. Asserts there is
    exactly one -- a needle checked against a file that defines two of them
    proves nothing about which one runs."""
    src, spans = _main_index()
    hits = [(lo, hi) for lo, hi, n in spans if n == name]
    assert len(hits) == 1, "main.py defines %s %d times" % (name, len(hits))
    lo, hi = hits[0]
    return "".join(src.splitlines(True)[lo - 1:hi])


def test_win_rate_unit_is_per_endpoint(ns):
    """win_rate is a 0-1 FRACTION on 1v1/2v2/FFA and a PERCENT on 1v2.

    One field name, two units, decided by the endpoint. That is the defect
    this test exists to stop recurring: the 1v2 renderer multiplied by 100
    like the other three and printed 5880% for a 58.8% player, and the
    fixture encoded the same assumption so nothing failed.

    Both halves are pinned. The RENDERER half asserts that the one row
    renderer which shows a win rate at all -- the 1v2 one -- turns its own
    endpoint's unit into the right human percentage, and that no sibling has
    quietly grown a win-rate column. It does NOT check "each board's human
    percentage": three of the four rows carry no win rate, and the sweep
    below asserts exactly that. The SOURCE half asserts main.py still
    produces those units IN THE FOUR HANDLERS THEMSELVES, so that normalising
    the server fails HERE, with a message saying the renderers must change
    too, rather than silently making every 1v2 row read 1%.

    The expected percentage is derived from the fixture rather than written
    out: a hardcoded "59%" stops measuring the moment the fixture moves.
    """
    import re

    # --- renderer half: derived from the fixture's own unit ---------------
    ovt = _rows_ovt(1)[0]
    ovt["wins"], ovt["losses"], ovt["games_played"] = 20, 14, 34
    pct = ovt["win_rate"]                        # percent, as /ovt/leaderboard sends it
    assert pct > 1.0, "the 1v2 fixture must carry a PERCENT for this test to mean anything"
    assert f"{round(pct)}%" in ns["_lb_line_ovt"](ovt, 1), (
        "the 1v2 renderer must NOT scale: its endpoint already returns a percent")
    assert f"{round(pct * 100)}%" not in ns["_lb_line_ovt"](ovt, 1)

    # Sibling sweep (#432): _lb_line_ovt is the ONLY renderer here that
    # shows a win rate. If someone adds one to another row they must pick
    # a unit deliberately rather than copying this line, so this fails
    # and says so.
    renders_wr = {name for name in
                  ("_lb_line", "_lb_line_2v2", "_lb_line_ffa", "_lb_line_ovt")
                  if "win_rate" in _renderer_source(ns, name)}
    assert renders_wr == {"_lb_line_ovt"}, (
        "a row renderer other than the 1v2 one now shows a win rate: %s. "
        "Its endpoint's unit is NOT the same as 1v2's — 1v1/2v2/FFA return a "
        "0-1 fraction and must be multiplied by 100, 1v2 returns a percent "
        "and must not be. Decide per endpoint, do not copy this row."
        % sorted(renders_wr - {"_lb_line_ovt"}))

    # --- source half: the units, in the handlers that produce them --------
    # Scoped by AST, not by grepping the file. A file-wide search was
    # satisfied by the same expression in a comment or in an unrelated route,
    # and it could not tell a producer that STARTED scaling from one that
    # always did -- wrapping a matched fraction expression in `100 *` left it
    # green while the unit moved under it.
    src, _spans = _main_index()
    scaled = [_enclosing_def(m.start())
              for m in re.finditer(r"win_rate\s*=\s*round\(\s*100(?:\.0)?\s*\*", src)]
    assert scaled == ["ovt_leaderboard"], (
        "exactly one handler may pre-scale win_rate, and it must be the 1v2 "
        "one. Found it in %r. If a NEW endpoint started pre-scaling, its "
        "renderer must drop its own 100* too; if ovt_leaderboard STOPPED, "
        "_lb_line_ovt must start scaling and NativeUI.cs:5980 must change "
        "with it." % (scaled,))

    for label, fn, needle in (
            ("1v1", "get_leaderboard", "ROUND(COALESCE(c.wins, 0)::numeric / c.total, 4)"),
            ("2v2", "team_leaderboard", "ROUND(COALESCE(ss.wins, 0)::numeric / ss.total, 4)"),
            ("ffa", "ffa_leaderboard", "win_rate=round(wins / games, 3)"),
            ("1v2", "ovt_leaderboard", "win_rate=round(100.0 * wins / games, 1)"),
    ):
        assert needle in _def_source(fn), (
            "%s: %s no longer produces win_rate as %s; the renderer for that "
            "board assumes it does"
            % (label, fn, "a percent" if label == "1v2" else "a 0-1 fraction"))


# ── the win-rate unit, measured rather than matched ───────────────────────
#
# The assertions above are all SUBSTRING tests, and a substring survives being
# wrapped: `100 * ROUND(COALESCE(c.wins, 0)::numeric / c.total, 4)` still
# contains the needle, and the `win_rate = round(100 *` regex does not read
# SQL at all. So the unit is taken below from the NUMBER each producer
# computes, for the one input 20 wins in 34 games: the three fraction boards
# must land in (0, 1] and the 1v2 board must land above 1. Nothing here can be
# satisfied by how the expression is spelled.

WR_WINS, WR_GAMES = 20, 34


def _sql_win_rate_expr(fn, alias):
    """The `... AS win_rate` expression out of one handler's own SQL, with the
    row's columns replaced by numbers. Located by the alias it is given, not
    by an offset: a handler that stops producing win_rate fails here."""
    import re
    src = _def_source(fn)
    end = src.find(" AS win_rate")
    assert end > 0, "%s no longer spells a `... AS win_rate` SQL expression" % fn
    start = src.rfind("CASE WHEN", 0, end)
    assert start > 0, "%s's win_rate column is no longer a CASE expression" % fn
    expr = src[start:end]
    assert expr.count("\n") < 6, "the matched expression spans too much to be one column"
    expr = re.sub(r"\b%s\.wins\b" % alias, str(WR_WINS), expr)
    expr = re.sub(r"\b%s\.total\b" % alias, str(WR_GAMES), expr)
    assert alias + "." not in expr, (
        "%s's win_rate expression still reads a column this model did not "
        "substitute: %r" % (fn, expr))
    return expr


def _py_win_rate_value(fn):
    """The value one handler's own `win_rate=` keyword expression computes.

    Lifted by AST from the handler source and evaluated, so the NUMBER is the
    production expression's, not a restatement of it.
    """
    import ast as _ast
    tree = _ast.parse(_def_source(fn).lstrip())
    found = [kw.value for node in _ast.walk(tree)
             if isinstance(node, _ast.Call)
             for kw in node.keywords if kw.arg == "win_rate"]
    assert len(found) == 1, "%s sets win_rate %d times" % (fn, len(found))
    return eval(compile(_ast.Expression(found[0]), "<win_rate>", "eval"),
                {"round": round}, {"wins": WR_WINS, "games": WR_GAMES})


@pytest.mark.skipif(not os.environ.get("A1_TEST_PG_DSN"),
                    reason="A1_TEST_PG_DSN unset; the SQL halves need a real PostgreSQL")
def test_the_sql_boards_win_rate_value_is_a_fraction():
    """1v1 and 2v2 produce win_rate in SQL, so PostgreSQL evaluates the
    handler's own expression here and the test reads the number back.

    The renderers on both sides multiply by 100 (NativeUI.cs:4672, NativeUI.cs:27204).
    Wrapping either expression as `100 * ROUND(...)` therefore ships a rate
    100x too large, and it is that VALUE this rejects -- the substring
    assertions above stay green through exactly that edit.
    """
    import asyncio as _asyncio
    import asyncpg

    dsn = os.environ["A1_TEST_PG_DSN"].replace("+asyncpg", "")
    exprs = {"1v1": _sql_win_rate_expr("get_leaderboard", "c"),
             "2v2": _sql_win_rate_expr("team_leaderboard", "ss")}

    async def _values():
        conn = await asyncpg.connect(dsn)
        try:
            return {k: float(await conn.fetchval("SELECT " + e))
                    for k, e in exprs.items()}
        finally:
            await conn.close()

    got = _asyncio.run(_values())
    for label, v in got.items():
        assert 0.0 < v <= 1.0, (
            "%s: the leaderboard query returns win_rate=%r for %d wins in %d "
            "games. That endpoint's consumers multiply by 100, so this is a "
            "rate %r times too large." % (label, v, WR_WINS, WR_GAMES, round(v * 100)))
        assert abs(v - WR_WINS / WR_GAMES) < 0.001, (label, v)


def test_the_python_boards_win_rate_value_has_its_own_endpoints_unit():
    """FFA produces a 0-1 fraction and 1v2 produces a percent, and the
    difference is what both renderers are written against. Evaluated, not
    matched: `100 * round(wins / games, 3)` fails here and passes every
    substring assertion above."""
    ffa = _py_win_rate_value("ffa_leaderboard")
    ovt = _py_win_rate_value("ovt_leaderboard")
    assert 0.0 < ffa <= 1.0, (
        "ffa_leaderboard returns win_rate=%r for %d wins in %d games; the FFA "
        "table multiplies by 100 (NativeUI.cs:4672), so this is %r times too "
        "large" % (ffa, WR_WINS, WR_GAMES, round(ffa * 100)))
    assert ovt > 1.0, (
        "ovt_leaderboard returns win_rate=%r; the 1v2 row does NOT scale "
        "(NativeUI.cs:5980, _lb_line_ovt), so a fraction here prints as 1%%" % ovt)
    assert abs(ovt - 100.0 * ffa) < 0.2, (
        "the two are meant to be the same rate in different units: %r vs %r"
        % (ovt, ffa))


def test_the_win_rate_unit_detector_can_fail(ns):
    """Negative control (#391) for the renderer half above.

    A detector that cannot fail is decoration. Feed the 1v2 renderer the
    FRACTION its sibling boards use and the assertion above must stop
    holding — otherwise it was never testing the scaling at all.
    """
    ovt = _rows_ovt(1)[0]
    pct = ovt["win_rate"]
    ovt["win_rate"] = pct / 100.0                # the wrong unit for this board
    assert f"{round(pct)}%" not in ns["_lb_line_ovt"](ovt, 1), (
        "the renderer assertion cannot distinguish the two units")

def test_mode_rows_are_not_1v1_rows(ns):
    """Negative control for the check above: `wins`/`losses` are exactly what
    a renderer copied from _lb_line would read, and the 2v2 model has
    neither."""
    for key in ("wins", "losses"):
        assert key not in schemas.Team2v2LeaderboardEntry.model_fields
    w = _Watch(_rows_2v2(1)[0])
    ns["_lb_line_2v2"](w, 1)
    assert {"series_wins", "series_losses"} <= w.read
    # 1v2 is unranked and carries no rating — the row says so by not reading one.
    assert "rating" not in schemas.Ovt1v2LeaderboardEntry.model_fields
    w2 = _Watch(_rows_ovt(1)[0])
    ns["_lb_line_ovt"](w2, 1)
    assert "rating" not in w2.read
    # Podium glyphs on the mode boards, not a 1v1 tier glyph.
    assert [ns["_board_medal"](r) for r in (1, 2, 3)] == ["🥇", "🥈", "🥉"]
    assert ns["_board_medal"](4) == ns["_board_medal"](50)


# ── one tick, end to end ──────────────────────────────────────────────────

def test_first_tick_posts_every_board_in_channel_order(ns):
    _tick(ns)
    ch = ns["_ch"]
    assert ch.titles() == [T_1V1, T_2V2, T_FFA]
    assert ch.deleted == []
    assert sorted(ns["_lb_message_ids"][CID]) == ["1v1", "2v2", "ffa"]
    assert sum(1 for ln in ns["_log"] if ": reposted at bottom as" in ln) == 3   # one per board
    # Every board carries the live "Updated <t:...:R>" recency stamp (#140)
    # and its own footer noun.
    for m, b in zip(ch.messages, ns["_enabled_boards"]()):
        assert re.match(r"Updated <t:\d+:R>", m.embeds[0].description)
        assert b["noun"] in m.embeds[-1].footer and "Auto-updated" in m.embeds[-1].footer
    assert [m.embeds[0].color for m in ch.messages] == ["gold", "blurple", "orange"]


def test_second_tick_edits_in_place(ns):
    _tick(ns)
    ch = ns["_ch"]
    ids_before = dict(ns["_lb_message_ids"][CID])
    ns["_log"].clear()
    _tick(ns)
    assert ns["_lb_message_ids"][CID] == ids_before      # same three messages
    assert ch.deleted == [] and len(ch.messages) == 3
    assert [len(m.edits) for m in ch.messages] == [1, 1, 1]
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 3


def test_a_failing_board_costs_only_itself():
    """3 boards, one endpoint down -> 2 published, 1 logged, the loop alive.
    Negative control: test_first_tick_posts_every_board_in_channel_order runs
    the same harness with no failure and publishes 3."""
    n2 = _fresh(broken={U_FFA: None})                    # a non-200
    _run(n2["publish_lb_loop"]())                        # through the loop, not around it
    assert n2["_ch"].titles() == [T_1V1, T_2V2]
    assert any("ffa: no data this tick" in ln for ln in n2["_log"])
    assert not any("Leaderboard publish error" in ln for ln in n2["_log"])
    # A row shape the renderer cannot read is contained the same way.
    n3 = _fresh(broken={U_2V2: {"entries": [{"rank": 1, "display_name": "x"}],
                                "total_players": 1}})
    _run(n3["publish_lb_loop"]())
    assert n3["_ch"].titles() == [T_1V1, T_FFA]
    assert any("2v2: render failed" in ln for ln in n3["_log"])
    assert not any("Leaderboard publish error" in ln for ln in n3["_log"])
    # ...and so is a transport failure, which reaches the publisher as a None
    # and NOT as an exception: api_get catches everything and returns None
    # (discord_bot.py:292), so "render failed (timeout)" is a line no network
    # failure can produce. The api layer is where the timeout is reported.
    n4 = _fresh(broken={U_FFA: RuntimeError("timeout")})
    _run(n4["publish_lb_loop"]())
    assert n4["_ch"].titles() == [T_1V1, T_2V2]
    assert any("API GET error: timeout" in ln for ln in n4["_log"])
    assert any("ffa: no data this tick" in ln for ln in n4["_log"])
    assert not any("render failed" in ln for ln in n4["_log"])


def test_burial_reposts_the_whole_set_once_and_then_settles(ns):
    _tick(ns)
    ch = ns["_ch"]
    ours = [m.id for m in ch.messages]
    stranger = ch.post_from_someone_else()
    ns["_log"].clear()
    _tick(ns)
    assert sorted(ch.deleted) == sorted(ours)            # only our own three
    assert stranger in ch.messages and stranger.id not in ch.deleted
    assert ch.titles() == [None, T_1V1, T_2V2, T_FFA]    # the set, in order, at the bottom
    assert sum(1 for ln in ns["_log"] if "not at the channel bottom" in ln) == 1
    # ...and the tick after that edits: this is not a repost every 10 minutes.
    ns["_log"].clear()
    deleted_before = len(ch.deleted)
    _tick(ns)
    assert len(ch.deleted) == deleted_before
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 3
    assert not any("not at the channel bottom" in ln for ln in ns["_log"])


def test_out_of_order_set_is_re_anchored_in_board_order(ns):
    """The boards are all at the bottom but in the wrong order (a fresh post
    for one board appends it below the others) — order is part of the set."""
    _tick(ns)
    ch = ns["_ch"]
    ch.messages.insert(0, ch.messages.pop())             # FFA to the top
    ns["_log"].clear()
    _tick(ns)
    assert ch.titles() == [T_1V1, T_2V2, T_FFA]
    assert sum(1 for ln in ns["_log"] if "not at the channel bottom" in ln) == 1


def test_buried_set_is_not_reposted_while_a_board_is_missing(ns):
    """The repost may only run while holding a replacement for every board.

    That used to be a data-loss rule: the repost deleted the whole set before
    sending anything, so reposting one board short meant deleting a message
    with nothing to put back. It is now an ORDERING rule -- the repost posts
    each replacement before deleting what it replaces, so a missing board
    would leave its old message stranded ABOVE the newly posted ones rather
    than dropped. Still wrong, no longer destructive. The gate earns its keep
    either way, which is why it stays."""
    _tick(ns)
    ch = ns["_ch"]
    ch.post_from_someone_else()
    ns["_api"].payloads[U_FFA] = None                    # down for this tick only
    ns["_log"].clear()
    _tick(ns)
    assert ch.deleted == []
    assert any("set is buried but a board did not render" in ln for ln in ns["_log"])
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 2
    # It re-anchors on the next tick, once every board renders again.
    ns["_api"].payloads[U_FFA] = _payloads()[U_FFA]
    ns["_log"].clear()
    _tick(ns)
    assert ch.titles()[-3:] == [T_1V1, T_2V2, T_FFA]
    assert sum(1 for ln in ns["_log"] if "not at the channel bottom" in ln) == 1


def _compose_service_env(service):
    """One service's `environment:` block, as {KEY: raw value}."""
    import io as _io
    import re as _re
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    comp = _io.open(p, encoding="utf-8", newline="").read()
    blk = comp[comp.index("\n  %s:" % service):]
    blk = blk[:blk.index("\n    volumes:")]
    return dict(_re.findall(r"^      ([A-Z_0-9]+):\s*(.+?)\s*$", blk, _re.M))


def _compose_bot_env():
    """The bot service's `environment:` block, as {KEY: raw value}."""
    return _compose_service_env("bot")


def test_compose_passes_the_board_list_and_repeats_its_default_exactly():
    """Compose must pass LEADERBOARD_BOARDS, carrying the SAME default.

    Two defects in one test, because fixing the first creates the second.

    (1) The bot reads LEADERBOARD_BOARDS, and compose did not enumerate it, so
        a standard Compose deployment could not enable, disable or reorder
        boards at all: a key in .env is not an env var in the container unless
        it is listed here (#438).

    (2) Adding it the way most of that block is written -- `${VAR:-}` -- would
        have been worse than leaving it out. os.getenv returns its fallback
        only for an ABSENT key; compose passing an empty value makes the key
        present-and-empty, and _enabled_boards() yields nothing for "". The
        leaderboard channel would have gone quiet on the next deploy, .env
        untouched, with "nothing to publish" the only trace. Measured on the
        real function: 3 boards -> 0.

    Repeating the default is the fix, and it makes compose a second source of
    truth for it. This test is what stops the two copies drifting -- which is
    the whole reason it asserts the exact string rather than just presence.
    """
    import re as _re
    env = _compose_bot_env()
    assert "LEADERBOARD_BOARDS" in env, (
        "compose does not pass LEADERBOARD_BOARDS, so no deployment can "
        "change the board set from .env (#438)")

    m = _re.fullmatch(r"\$\{LEADERBOARD_BOARDS:-(.+)\}", env["LEADERBOARD_BOARDS"])
    assert m, (
        "LEADERBOARD_BOARDS must be passed as ${LEADERBOARD_BOARDS:-<default>} "
        "with a NON-EMPTY default. Found %r. An empty default hands the bot "
        "\"\" and publishes no boards at all." % env["LEADERBOARD_BOARDS"])

    code_default = _re.search(
        r'os\.getenv\(\s*"LEADERBOARD_BOARDS"\s*,\s*"([^"]*)"', TEXT).group(1)
    assert m.group(1) == code_default, (
        "compose default %r and discord_bot.py default %r have drifted. They "
        "are two copies of one decision; whichever is wrong, a deployment "
        "publishes a different board set than the code says it does."
        % (m.group(1), code_default))


def test_the_footer_days_and_the_window_the_api_applies_are_one_number():
    """The board footer states how many days of inactivity it hides at. The
    api is what actually hides them, from its own read of the same key name
    in a different process -- so the footer is a public claim about a number
    it does not own, and nothing reports the two copies drifting.

    Three copies must agree: `LB_ACTIVE_DAYS` in discord_bot.py (what the
    footer prints), `LEADERBOARD_ACTIVE_DAYS` in api/main.py (what the window
    IS), and the compose default, which is the only one an operator can move.

    Compose must pass the key to BOTH services, and passing it to one is
    worse than passing it to neither: it would move the api's window while
    the footer kept printing the compiled default, or the reverse. A key
    compose does not enumerate cannot be set from .env at all -- os.getenv
    falls back to the compiled default with no error anywhere (#438) -- which
    is how an operator tightening the window ends up with a wrong number on a
    public channel and a normal-looking log.
    """
    import re as _re
    from pathlib import Path

    KEY = "LEADERBOARD_ACTIVE_DAYS"
    bot_default = _re.search(
        r'os\.getenv\(\s*"%s"\s*,\s*"([^"]*)"' % KEY, TEXT).group(1)
    api_src = Path(__file__).resolve().parents[1] / "api" / "main.py"
    api_default = _re.search(
        r'os\.environ\.get\(\s*"%s"\s*,\s*"([^"]*)"' % KEY,
        api_src.read_text(encoding="utf-8")).group(1)
    assert bot_default == api_default, (
        "the bot's %s default is %r and the api's is %r. The footer prints "
        "the first and the api hides players by the second, so the board "
        "states a window nobody applied." % (KEY, bot_default, api_default))
    int(bot_default)                      # both are read through int()

    for service, sentinel in (("api", "DATABASE_URL"), ("bot", "DISCORD_TOKEN")):
        env = _compose_service_env(service)
        assert sentinel in env, (
            "read the wrong compose block for %r -- got keys %r"
            % (service, sorted(env)))
        assert KEY in env, (
            "compose does not pass %s to the %s service, so .env cannot move "
            "it there and the compiled default is the only value that "
            "service will ever see (#438)." % (KEY, service))
        m = _re.fullmatch(r"\$\{%s:-(.+)\}" % KEY, env[KEY])
        assert m, (
            "%s must reach the %s service as ${%s:-<default>} with a "
            "NON-EMPTY default. Found %r; an empty value is present-and-empty, "
            "which int() cannot read." % (KEY, service, KEY, env[KEY]))
        assert m.group(1) == bot_default, (
            "compose hands the %s service %s=%r while the code default is %r. "
            "They are copies of one decision." % (service, KEY, m.group(1), bot_default))


# ── the same number, third copy: the CLIENT prints it too ─────────────────

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugin"

_WINDOW_WORD = re.compile(r"inactiv", re.I)
# "90d", "90 d", "90d+", "90 days", "90+ days". NOT "{0}d" -- a placeholder
# carries no digits, which is the whole difference this asserts. (The "+"
# before the unit is the form the settings help and the configuration
# description used; the pattern without it could not see either.)
_LITERAL_DAYS = re.compile(r"\b\d+\s*\+?\s*(?:d\b|d\+|days?\b)", re.I)

# Generated or translated, and pinned by the i18n suite instead: the
# catalogues are keyed BY these English strings, so a literal that got past
# the sweep below would be visible there as a key with no placeholder.
_NOT_A_SURFACE = {"I18nCatalogues.cs", "I18nSourceKeys.g.cs"}

_EXTRACTOR = []


def _extractor():
    """tools/i18n_extract.py, loaded once. The tool that decides which client
    strings exist decides what this sweep reads, so a surface it harvests --
    a Tr/TrF call, a CreateText or SetText label, the settings help passed
    through SettingsToggle, a table it ingests -- cannot be missed here."""
    if not _EXTRACTOR:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "i18n_extract_for_the_window_sweep",
            str(PLUGIN_DIR.parent / "tools" / "i18n_extract.py"))
        ex = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ex)
        _EXTRACTOR.append(ex)
    return _EXTRACTOR[0]


_CONFIG_BIND = re.compile(r"Config\.Bind\s*\(")
_STR_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _window_strings_in(fn, src):
    """(file, helper, string) for every string in ONE source that talks about
    the inactive window: each string the i18n extractor harvests from it,
    with the helper it went through, and each string literal inside a
    Config.Bind call -- the description BepInEx writes into the .cfg, which
    is English-only and which the extractor, rightly, never harvests."""
    ex = _extractor()
    src = ex.lf(src)
    found, sites = {}, {}
    ex.harvest_source(fn, src, found, sites)
    out = [(fn, kind, s) for s in sorted(found) for kind in sorted({k for _f, _m, k in sites[s]})]
    for m in _CONFIG_BIND.finditer(src):
        out += [(fn, "Config.Bind", s) for s in _STR_LITERAL.findall(ex.find_call_body(src, m.end() - 1))]
    return [row for row in out if _WINDOW_WORD.search(row[2])]


def _client_inactivity_strings():
    """Every client string -- a translated surface or a configuration
    description -- that talks about the inactive window, in every plugin
    source (a file the extractor's list forgot is swept all the same)."""
    out = []
    for cs in sorted(PLUGIN_DIR.glob("*.cs")):
        if cs.name in _NOT_A_SURFACE:
            continue
        out += _window_strings_in(cs.name, cs.read_text(encoding="utf-8"))
    return out


_MOD_VERSION_BODY = []


def _api_mod_version_body():
    """The /api/v1/mod-version handler, lifted by AST.

    Scoped deliberately: api/main.py is 57k lines and `leaderboard_active_days`
    is a plausible spelling anywhere in it, so a file-wide substring would be
    satisfied by a comment (#441). This reads the one function that answers the
    call every seat makes.
    """
    if not _MOD_VERSION_BODY:
        src = (Path(__file__).resolve().parents[1] / "api" / "main.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        got = None
        for node in ast.walk(tree):
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "get_mod_version"):
                got = ast.get_source_segment(src, node)
                break
        assert got, "get_mod_version is gone from api/main.py"
        _MOD_VERSION_BODY.append((got, src))
    return _MOD_VERSION_BODY[0]


def test_the_day_count_the_client_prints_is_the_one_the_api_advertises():
    """LEADERBOARD_ACTIVE_DAYS has a THIRD reader, and it is not a service.

    The F5 board labels its population and its inactive toggle with the same
    window the api filters on, and it used to do that from a compiled `90`.
    That is the identical defect the test above prevents between the bot and
    the api, one process further out: the number is configurable server-side,
    so on any deployment not set to 90 the client stated a window nobody
    applied -- and a second constant in the client would move that defect
    rather than remove it.

    So: the api ADVERTISES it, once, on the unauthenticated call every seat
    already makes at startup; the client takes the value from that answer and
    keeps no default of its own; and no client surface states the window as a
    literal. The client's own default is 0, which means "not told" -- an
    older server and a failed version check look the same from here, and both
    print no day count at all rather than a number this side invented.
    """
    body, api_src = _api_mod_version_body()
    flat_body = re.sub(r"\s+", " ", body)
    assert '"leaderboard_active_days": LEADERBOARD_ACTIVE_DAYS' in flat_body, (
        "the mod-version route no longer advertises the window from the api's "
        "own constant; the client has no other way to learn it")
    assert api_src.count('"leaderboard_active_days"') == 1, (
        "the api names leaderboard_active_days on %d surfaces. It is "
        "advertised ONCE, or the copies drift exactly as the compiled client "
        "constant did." % api_src.count('"leaderboard_active_days"'))

    client = (PLUGIN_DIR / "ApiClient.cs").read_text(encoding="utf-8")
    flat_client = re.sub(r"\s+", " ", client)
    assert ('int lbDays = ExtractJsonInt(req.downloadHandler.text, '
            '"leaderboard_active_days");') in flat_client, (
        "the client does not read the advertised window out of the "
        "mod-version answer")
    assert ("if (lbDays > 0 && lbDays != LeaderboardActiveDays) { "
            "LeaderboardActiveDays = lbDays; NativeUI.MarkDirty(); }") in flat_client, (
        "the client does not take the advertised window as it must: only a "
        "positive value (a malformed or absent one would turn a label that "
        "states the window into one that states 0d), and a CHANGED value "
        "marks the UI dirty -- the answer arrives after the panel may have "
        "drawn its labels, and an open surface repaints only when dirty")
    assert ("public static int LeaderboardActiveDays { get; private set; } = 0;"
            in flat_client), (
        "the client carries a compiled default for a server setting again -- "
        "0 is the only value that means 'the server has not told us'")
    ui = re.sub(r"\s+", " ", (PLUGIN_DIR / "NativeUI.cs").read_text(encoding="utf-8"))
    assert "public static void MarkDirty()=>dirty=true;" in ui and \
        "if(dirty){dirty=false;RefreshCurrentTab();}" in ui, (
        "MarkDirty no longer feeds the repaint the update loop honours, so "
        "marking the UI dirty repaints nothing")

    surfaces = _client_inactivity_strings()
    assert surfaces, (
        "no client string about the inactive window was found at all, so the "
        "sweep below measured nothing")
    kinds = {kind for _f, kind, _s in surfaces}
    assert {"SettingsToggle", "Config.Bind", "TrF"} <= kinds, (
        "the sweep no longer reaches the settings help, the configuration "
        "descriptions and the translated labels together: it saw %r" % sorted(kinds))
    for name, kind, s in surfaces:
        assert not _LITERAL_DAYS.search(s), (
            "%s (%s) states the inactivity window as a literal: %r. The window "
            "is a server setting; print the value the api advertised, or print "
            "no count." % (name, kind, s))
    assert any("{0}d" in s or "{1}d" in s for _f, _k, s in surfaces), (
        "no client surface prints the advertised window at all any more, so "
        "nothing carries it to the player")


def test_the_literal_day_count_detector_can_fail():
    """The control for the sweep above (#391). Both halves of it: the reader
    must find every KIND of surface that mentions the window -- a translated
    label, the settings help passed through SettingsToggle, a Config.Bind
    description -- and the pattern must call each literal form a literal. A
    sweep over an empty list, one that reads only Tr calls, or one whose
    pattern matched nothing, passes silently and forever."""
    planted = (
        'class Planted { void Build() {\n'
        '    btn = SettingsToggle(box, "SX", size, () => { }, '
        '"Lists players who have not run the mod for 90+ days, tagged (inactive).");\n'
        '    x = I18n.TrF("Show inactive players (90d+): ON", d);\n'
        '    y = I18n.Tr("Show inactive players: ON");\n'
        '    K = Config.Bind("UI", "K", false, "Show players inactive for 90+ days on the leaderboards");\n'
        '} }\n')
    got = _window_strings_in("Planted.cs", planted)
    assert {kind for _f, kind, _s in got} == {"SettingsToggle", "TrF", "Tr", "Config.Bind"}, got
    flagged = sorted(kind for _f, kind, s in got if _LITERAL_DAYS.search(s))
    assert flagged == ["Config.Bind", "SettingsToggle", "TrF"], (
        "the detector does not see every literal day count it was handed: %r" % got)
    assert not _LITERAL_DAYS.search("Show inactive players ({0}d+): ON"), (
        "the detector calls the PLACEHOLDER form a literal, so the sweep "
        "would fail on the fix as well as on the defect")


# Keys discord_bot.py reads that compose does NOT pass into the container.
# This is a RECORDED GAP, not an approval: each is a setting that cannot be
# changed from .env on a standard deployment, and none of them has been
# checked to see whether its compiled default is the right one in production.
# They are listed so the set cannot grow silently -- the same defect has now
# been found four times here (CHAT_CHANNELS "wave-2 find 22", the Twitch trio
# "D1 F12", LEADERBOARD_BOARDS, and LEADERBOARD_ACTIVE_DAYS), which makes it a
# class and not an incident. Removing a name from this list means compose now
# passes it.
#
# LEADERBOARD_ACTIVE_DAYS came off this list rather than staying a recorded
# gap, because one of this wave's new board lines PRINTS it: a footer saying
# "<n> inactive hidden (<d> days)" is a public claim about a window the api
# applied from its own copy of the key. A number only the code can change is
# tolerable while nothing quotes it; a wrong one on a public channel is not.
_KNOWN_UNPASSED = {
    "ADMIN_CHANNEL", "BOT_GEN", "BUG_REPORTS_CHANNEL", "DISCORD_PRESENCE_INTENT",
    "GAMBLER_ROLE", "GAMBLER_SIGNUP_CHANNEL", "GITHUB_RELEASES_REPO",
    "LFP_ROLE", "LIVE_BETS_CHANNEL",
    "SCR_TOURNAMENTS_CHANNEL", "STREAM_BRIDGE_TWITCH_CHANNEL", "TOURNAMENT_CHANNEL",
    "TROPHY_ROLE_CHAMPION", "TROPHY_ROLE_PARTICIPANT", "TROPHY_ROLE_PARTICIPANT2",
    "TROPHY_ROLE_RUNNER_UP", "TROPHY_ROLE_THIRD_PLACE",
}


def test_no_new_bot_setting_becomes_unreachable_from_env():
    """Every env key the bot reads is either passed by compose or recorded.

    The failure this prevents is silent by construction: the code reads the
    key, the key has a plausible compiled default, the container never
    receives it, and an operator editing .env watches nothing happen. There is
    no error to grep for. It has already landed here three times.

    A new name in the failure message means someone added a setting and did
    not wire it through compose. Either add it there -- minding the empty
    default trap above -- or add it to _KNOWN_UNPASSED and say why.
    """
    import re as _re
    read = set(_re.findall(r'os\.getenv\(\s*"([A-Z_0-9]+)"', TEXT))
    read |= set(_re.findall(r'os\.environ\.get\(\s*"([A-Z_0-9]+)"', TEXT))
    read |= set(_re.findall(r'os\.environ\[\s*"([A-Z_0-9]+)"\s*\]', TEXT))
    gap = read - set(_compose_bot_env()) - _KNOWN_UNPASSED
    assert not gap, (
        "discord_bot.py reads %s, which compose never passes into the bot "
        "container, so .env cannot set them and the compiled default is the "
        "only value production will ever see (#438)." % sorted(gap))


def test_a_failed_repost_send_never_takes_a_board_off_the_channel(ns):
    """A send that fails mid-repost leaves that board's old message standing.

    This is the failure the delete-first shape could not survive. It deleted
    the whole set first, so any send failure after that point left the channel
    holding part of the set or none of it until the next tick -- ten minutes
    of empty leaderboard channel, which is the exact appearance of deadness
    that bottom-anchoring exists to prevent (#140).

    The caller's guarantee that every board RENDERED is not the same as every
    send succeeding, and no amount of pre-rendering can make it so. Posting
    each replacement before deleting what it replaces is what closes the gap.
    """
    _tick(ns)
    ch = ns["_ch"]
    ch.post_from_someone_else()                    # bury the set -> next tick reposts
    ch.send_fails_for_titles = {T_2V2}             # 2v2's replacement will not go out
    ns["_log"].clear()
    _tick(ns)

    # The assertion the old shape failed: every board is still on the channel,
    # exactly once. 2v2's is stale and out of order -- present beats correct.
    titles = [t for t in ch.titles() if t is not None]
    assert sorted(titles) == sorted([T_1V1, T_2V2, T_FFA]), titles
    assert any("repost failed" in ln and "old message kept" in ln for ln in ns["_log"])

    # And it re-anchors once the send goes through again, so the degraded
    # ordering is one tick long and not a new steady state.
    ch.send_fails_for_titles = set()
    ns["_log"].clear()
    _tick(ns)
    assert ch.titles()[-3:] == [T_1V1, T_2V2, T_FFA]


def test_the_missing_board_detector_can_fail(ns):
    """Negative control (#391) for the test above.

    Its invariant is only worth having if it can go red. Take a board's
    message away without putting one back -- precisely what a failed send did
    under the delete-first shape -- and the same assertion must fail.
    """
    _tick(ns)
    ch = ns["_ch"]
    _run(ch.messages[1].delete())                  # 2v2 gone, nothing put back
    titles = [t for t in ch.titles() if t is not None]
    assert T_2V2 not in titles
    assert sorted(titles) != sorted([T_1V1, T_2V2, T_FFA])


def test_the_owed_delete_queue_and_its_cap_are_gone_from_the_module():
    """The mechanism was DELETED, not patched again.

    A queue of ids held beside the live-id map produced a HIGH and two
    MEDIUMs inside its own fix: the sweep ran before the channel state
    validated the map, its 24-entry cap could evict a genuinely owed delete,
    and a history read that died part-way could leave one id both live and
    owed. Every one of those is a consequence of keeping a SECOND record of
    what is on the channel. There is now one record -- the channel -- read
    fresh each tick, so an id cannot be in two states at once because the
    structure that held the second state does not exist.

    Asserted by absence, because "we stopped using it" and "it is gone" are
    different claims and only the second one closes the class.
    """
    for name in GONE_FROM_SOURCE:
        assert name not in TEXT, (
            "%s is still in discord_bot.py; the owed-delete bookkeeping was "
            "supposed to be removed, not left reachable" % name)


def _seed_board_message(ch, title):
    """One board message left on the channel by an EARLIER process.

    The publisher's id map is process memory, so a fresh process meets a
    channel it did not post into. This is what the reconcile read adopts.
    """
    return _run(ch.send(embeds=[_Embed(title=title)], view=None))


def test_a_failed_repost_delete_leaves_a_duplicate_and_the_next_read_removes_it(ns):
    """The other failure direction, which is the price of send-before-delete.

    If the replacement goes out but the old message will not delete, the
    channel carries that board twice for a tick. That is the deliberate
    trade: a stale duplicate above the set is recoverable, an absent board is
    not recoverable until the next tick.

    What must NOT happen is the duplicate being left there. Nothing remembers
    it: the next tick READS THE CHANNEL and finds an older message carrying
    an enabled board's title, with that board's newer keeper present -- which
    is the definition of an older copy -- and deletes it once that tick's
    edit of the keeper has landed. No queue is involved and none is needed.
    """
    _tick(ns)
    ch = ns["_ch"]
    old_2v2 = ns["_lb_message_ids"][CID]["2v2"]
    ch.post_from_someone_else()
    ch.delete_fails = {old_2v2}
    ns["_log"].clear()
    _tick(ns)

    titles = [t for t in ch.titles() if t is not None]
    assert titles.count(T_2V2) == 2, titles
    assert ns["_lb_message_ids"][CID]["2v2"] != old_2v2
    assert any("couldn't delete replaced 2v2 board" in ln for ln in ns["_log"])

    # The next tick reads the channel, sees two 2v2 messages, and removes the
    # older one. Nothing had to be remembered between the two ticks.
    ch.delete_fails = set()
    ns["_log"].clear()
    _tick(ns)
    titles = [t for t in ch.titles() if t is not None]
    assert titles.count(T_2V2) == 1, titles
    assert old_2v2 in ch.deleted
    assert any("deleted 1 duplicate stale board message" in ln for ln in ns["_log"])


def test_the_duplicate_removal_can_fail(ns):
    """Negative control (#391) for the branch above: while the delete keeps
    being refused the duplicate must STAY, and the log must say so on every
    tick. A reconcile that reported success on a refusal would pass the test
    above and fix nothing."""
    _tick(ns)
    ch = ns["_ch"]
    old_2v2 = ns["_lb_message_ids"][CID]["2v2"]
    ch.post_from_someone_else()
    ch.delete_fails = {old_2v2}
    _tick(ns)
    assert [t for t in ch.titles() if t is not None].count(T_2V2) == 2
    ns["_log"].clear()
    _tick(ns)                                   # still refused
    assert [t for t in ch.titles() if t is not None].count(T_2V2) == 2
    assert old_2v2 not in ch.deleted
    assert any(f"couldn't delete duplicate 2v2 board mid={old_2v2}" in ln
               for ln in ns["_log"]), ns["_log"]


def test_every_refused_duplicate_is_found_again_however_many_there_are():
    """R2-M2, driven rather than asserted by absence.

    The queue this replaced held at most 24 owed deletes and forgot the
    oldest when a 25th arrived; with the set complete and anchored, nothing
    ever looked for the forgotten one again. Here THIRTY duplicates sit above
    an anchored set while every delete is refused. Each one must be named as
    refused on that tick, and on the first tick after the permission comes
    back every one of them must go -- found by reading the channel, with no
    record of the earlier refusals kept anywhere.
    """
    ns = _fresh()
    ch = ns["_ch"]
    for _ in range(11):                         # oldest first: 30 duplicates, then the keepers
        for title in (T_1V1, T_2V2, T_FFA):
            _seed_board_message(ch, title)
    keepers = [m.id for m in ch.messages[-3:]]
    dupes = {m.id for m in ch.messages[:-3]}
    assert len(dupes) == 30
    ch.delete_fails = set(dupes)
    _tick(ns)

    assert len(ch.messages) == 33
    refused = [ln for ln in ns["_log"] if "couldn't delete duplicate" in ln]
    assert len(refused) == 30, refused
    assert [ns["_lb_message_ids"][CID][k] for k in ("1v1", "2v2", "ffa")] == keepers
    assert not any("not at the channel bottom" in ln for ln in ns["_log"])

    ch.delete_fails = set()
    sent_before = len(ch.sent)
    ns["_log"].clear()
    _tick(ns)

    assert dupes <= set(ch.deleted), sorted(dupes - set(ch.deleted))
    assert [m.id for m in ch.messages] == keepers
    assert ch.titles() == [T_1V1, T_2V2, T_FFA]
    assert len(ch.sent) == sent_before          # removed, not reposted over
    assert any("deleted 30 duplicate stale board message" in ln for ln in ns["_log"])


def test_an_outage_tick_reads_the_channel_and_deletes_no_copy_of_a_board(ns):
    """Fix pass 3, item 1 (the outage control); supersedes R2-L01's "an outage
    tick retries duplicate cleanup".

    An outage tick still READS the channel: the reconcile runs before the
    no-render return, so the id map follows what is on the channel even
    while nothing renders. What it may no longer do is delete a copy of a
    board. A duplicate is deleted only after the same tick has proven a newer
    copy of its board live, and a tick on which the board's endpoint failed
    proves nothing -- so the round 3 shape, which deleted the older copy on
    such a tick on the strength of the read alone, could leave the board
    absent when its keeper vanished after the read.

    Driven: a refused repost delete leaves an older 2v2 message above the
    set; the process restarts, so only the read can re-derive the ids; every
    board endpoint stops answering. That tick adopts the keepers and deletes
    nothing. The first tick on which 2v2 renders again edits its keeper and
    only then removes the older copy.
    """
    _tick(ns)
    ch = ns["_ch"]
    old_2v2 = ns["_lb_message_ids"][CID]["2v2"]
    ch.post_from_someone_else()
    ch.delete_fails = {old_2v2}
    _tick(ns)                                   # re-anchored; the old 2v2 would not delete
    assert [t for t in ch.titles() if t is not None].count(T_2V2) == 2
    keepers = dict(ns["_lb_message_ids"][CID])

    for url in (U_1V1, U_2V2, U_FFA):
        ns["_api"].payloads[url] = None         # every board endpoint is out
    ch.delete_fails = set()
    ns["_lb_message_ids"].clear()               # a restart: only the read knows the ids now
    ch.must_stay = {T_1V1, T_2V2, T_FFA}
    deleted_before = list(ch.deleted)
    ns["_log"].clear()
    _tick(ns)

    assert any("no board rendered this tick" in ln for ln in ns["_log"]), ns["_log"]
    assert ch.deleted == deleted_before, (
        "an outage tick deleted %r; a board that did not render proves no copy "
        "of itself live, so it deletes nothing" % sorted(set(ch.deleted) - set(deleted_before)))
    assert old_2v2 in [m.id for m in ch.messages]
    assert ns["_lb_message_ids"][CID] == keepers, (
        "the outage tick did not re-derive the ids from the channel -- the "
        "read no longer runs on a tick that renders nothing")
    assert any("2v2: 1 older copy/copies left as they are" in ln for ln in ns["_log"]), ns["_log"]

    # The endpoint answers again: the keeper's edit lands, then the older
    # copy goes, on the same tick.
    for url in (U_1V1, U_2V2, U_FFA):
        ns["_api"].payloads[url] = _payloads()[url]
    ns["_log"].clear()
    _tick(ns)
    assert old_2v2 in ch.deleted
    assert [t for t in ch.titles() if t is not None] == [T_1V1, T_2V2, T_FFA]
    assert any("deleted 1 duplicate stale board message" in ln for ln in ns["_log"])
    assert ch.absences == [], ch.absences


def test_the_only_surviving_board_message_is_adopted_not_deleted(ns):
    """The filed HIGH, driven end to end.

    An older 1v1 message survives a refused delete after its replacement went
    out. A moderator then removes the replacement, so that older message is
    the ONLY 1v1 board on the channel. The delete refusal then clears and
    that board's endpoint goes down, so nothing would repost whatever is
    removed.

    The old shape decided this from memory: the id was on an owed-delete
    queue, the sweep ran before anything validated the channel, and it
    deleted the only surviving board. The reconcile cannot reach that state.
    It reads the channel first, and within that read the message is the
    NEWEST one carrying the 1v1 title -- that board's keeper. A keeper is
    what `ids` is set to; it is never also a deletion candidate, because the
    two readings come out of the same pass over the same messages.
    """
    _tick(ns)
    ch = ns["_ch"]
    old_1v1 = ns["_lb_message_ids"][CID]["1v1"]
    ch.post_from_someone_else()                 # bury -> next tick reposts
    ch.delete_fails = {old_1v1}
    _tick(ns)
    new_1v1 = ns["_lb_message_ids"][CID]["1v1"]
    assert new_1v1 != old_1v1
    assert [t for t in ch.titles() if t is not None].count(T_1V1) == 2

    _run(next(m for m in ch.messages if m.id == new_1v1).delete())   # a moderator
    ch.delete_fails = set()                     # permission restored
    ns["_api"].payloads[U_1V1] = None           # and 1v1's endpoint is down
    ns["_log"].clear()
    _tick(ns)

    assert ns["_lb_message_ids"][CID]["1v1"] == old_1v1, (
        "the surviving 1v1 message was not adopted as the board")
    assert old_1v1 not in ch.deleted, (
        "mid=%d was the only 1v1 board on the channel and it was deleted" % old_1v1)
    assert [t for t in ch.titles() if t is not None].count(T_1V1) == 1
    assert any("1v1: no data this tick" in ln for ln in ns["_log"])

    _tick(ns)                                   # the outage continues
    assert T_1V1 in ch.titles()
    assert old_1v1 not in ch.deleted


def test_an_older_copy_survives_a_keeper_that_vanishes_after_the_read(ns):
    """Fix pass 3, item 1: the round 3 HIGH's interleaving, driven.

    The read yields keeper K and an older copy O of the 1v1 board. K is then
    removed -- a moderator, a second process -- AFTER the read handed it over
    and BEFORE anything was deleted. Round 3 deleted O inside the reconcile,
    on the strength of a read that had already gone stale, and at that
    moment the 1v1 board had no message on the channel at all.

    Required: O is retained until the same tick has proven a copy of the
    board live or sent its replacement. Here the edit of K fails with
    NotFound, so the tick ADOPTS O by editing it -- removing nothing -- and
    O is the board. The next tick finds O as its keeper again; because O
    sits above chat it is re-anchored by the repost, which deletes O only
    after O's replacement has been sent. At no point is the board absent.
    """
    _tick(ns)
    ch = ns["_ch"]
    old_1v1 = ns["_lb_message_ids"][CID]["1v1"]
    ch.post_from_someone_else()                 # bury -> next tick reposts
    ch.delete_fails = {old_1v1}                 # ...and the replaced 1v1 will not delete
    _tick(ns)
    keeper = ns["_lb_message_ids"][CID]["1v1"]
    assert keeper != old_1v1
    assert [t for t in ch.titles() if t is not None].count(T_1V1) == 2

    ch.delete_fails = set()                     # every delete would succeed now
    ch.vanish_after_read = {keeper}             # K: read, then gone before anything acts
    ch.must_stay = {T_1V1, T_2V2, T_FFA}
    ns["_log"].clear()
    _tick(ns)

    assert old_1v1 not in ch.deleted, (
        "mid=%d (O) was deleted although its keeper had vanished after the read: "
        "the delete followed the read, not a proof" % old_1v1)
    assert ch.absences == [], (
        "a delete left a board with no message on the channel: %r" % ch.absences)
    assert old_1v1 in [m.id for m in ch.messages]
    assert [t for t in ch.titles() if t is not None].count(T_1V1) == 1
    assert ns["_lb_message_ids"][CID]["1v1"] == old_1v1, "O was not adopted as the board"
    assert any(f"1v1: board mid={keeper} is gone" in ln for ln in ns["_log"]), ns["_log"]
    assert any(f"1v1: edited board mid={old_1v1} (an older copy, adopted" in ln
               for ln in ns["_log"]), ns["_log"]

    # The next tick: O is the keeper on the read; buried under chat, it is
    # replaced by the repost, whose send comes before O's delete.
    ns["_log"].clear()
    _tick(ns)
    assert ch.absences == [], ch.absences
    assert [t for t in ch.titles() if t is not None].count(T_1V1) == 1
    assert ch.titles()[-3:] == [T_1V1, T_2V2, T_FFA]


def test_nothing_is_deleted_without_a_message_for_that_board_still_on_the_channel(ns):
    """The bar property, asserted over one tick's deletions rather than
    argued.

    Every message a tick deletes is either an older COPY of an enabled board,
    deleted only after that tick proved a newer copy live -- or a RETIRED
    board's message, which this deployment does not publish at all. This
    drives both kinds in one tick and asserts that every enabled board still
    has exactly one message when the tick is done, and that no delete along
    the way left a board with none (the absence watch).
    """
    n2 = _fresh()
    _tick(n2)
    ch = n2["_ch"]
    first = dict(n2["_lb_message_ids"][CID])
    # An earlier process's full set, newer than ours, plus a retired board's
    # message: three duplicates and one retirement in the same read.
    for b in n2["_enabled_boards"]():
        _seed_board_message(ch, b["title"])
    retired = _seed_board_message(ch, "⚔️ 1v2 Leaderboard")

    n3 = _bot_ns(_Api(_payloads()), _Bot(ch), boards_raw="1v1,2v2,ffa")
    ch.must_stay = {T_1V1, T_2V2, T_FFA}
    _run(n3["publish_boards"]())

    titles = [t for t in ch.titles() if t is not None]
    for t in (T_1V1, T_2V2, T_FFA):
        assert titles.count(t) == 1, (t, titles)
    assert "⚔️ 1v2 Leaderboard" not in titles
    assert retired.id in ch.deleted
    assert sorted(ch.deleted) == sorted(list(first.values()) + [retired.id])
    assert ch.absences == [], ch.absences


def test_a_channel_read_that_dies_part_way_deletes_nothing(ns):
    """A history read that raises after yielding some messages has NOT shown
    what is on the channel, so this tick deletes nothing at all -- not even
    the duplicate it did see. The conservative direction is a duplicate that
    survives one more tick, never a message removed on an unverified picture.

    It still ADOPTS what it saw: history is newest-first, so the first
    message carrying a title is that title's newest message whether or not
    the read went on to finish, and adopting it removes nothing.
    """
    ch = ns["_ch"]
    ch.post_from_someone_else()
    held = _seed_board_message(ch, T_1V1)
    _seed_board_message(ch, T_2V2)
    _seed_board_message(ch, T_FFA)
    _tick(ns)
    assert ns["_lb_message_ids"][CID]["1v1"] == held.id

    newer = _seed_board_message(ch, T_1V1)      # another process posts a 1v1
    ch.history_raises_after = 4                 # the read dies mid-channel
    ns["_log"].clear()
    _tick(ns)

    assert ch.deleted == [], ch.deleted
    assert any("channel read failed" in ln and "deletes nothing" in ln
               for ln in ns["_log"]), ns["_log"]
    assert [t for t in ch.titles() if t is not None].count(T_1V1) == 2

    # ...and the first complete read resolves it: `newer` is the keeper and
    # the one we were holding is the duplicate. Which of the two goes is
    # decided by the CHANNEL, on that read, not by what an earlier tick
    # happened to be holding.
    ch.history_raises_after = None
    ns["_log"].clear()
    _tick(ns)
    assert held.id in ch.deleted, (
        "the complete read did not remove the older 1v1 message: %r" % ch.deleted)
    assert ns["_lb_message_ids"][CID]["1v1"] != held.id
    assert [t for t in ch.titles() if t is not None].count(T_1V1) == 1


def test_a_channel_deeper_than_the_ceiling_deletes_nothing_and_posts_nothing_fresh():
    """LB_RECONCILE_CEILING is where the read gives up on seeing the whole
    channel, and the tick then behaves exactly like a failed read.

    This is the ONE case the reconcile cannot close, and it is stated rather
    than hidden: a read that stops short has not shown that there is no
    earlier set behind it, so nothing is deleted and no board is posted
    fresh. A board whose id is still held is edited as usual -- fetch_message
    reaches a message at any depth -- so the bound costs a publish only for a
    board this process has lost the id for.
    """
    n2 = _fresh()
    _tick(n2)
    ch = n2["_ch"]
    before = [m.id for m in ch.messages]
    stale = _seed_board_message(ch, T_1V1)      # a duplicate the short read DOES see
    n2["LB_RECONCILE_CEILING"] = 2              # ...and the read now stops short
    n2["_log"].clear()
    _tick(n2)
    assert ch.deleted == [], "a message was deleted on a read that stopped short"
    assert any("holds more than 2 messages" in ln for ln in n2["_log"]), n2["_log"]
    assert [m.id for m in ch.messages] == before + [stale.id]

    # A board the short read never reached is not posted fresh either.
    n2["_lb_message_ids"].clear()
    n2["_log"].clear()
    _tick(n2)
    assert ch.deleted == []
    assert any("2v2: no message id and the channel read was incomplete" in ln
               for ln in n2["_log"]), n2["_log"]
    assert [m.id for m in ch.messages] == before + [stale.id]

    # The control: with the ceiling back above the channel, the same tick
    # reads to the end and resolves everything it refused to touch.
    n2["LB_RECONCILE_CEILING"] = 2000
    n2["_log"].clear()
    _tick(n2)
    assert before[0] in ch.deleted
    assert [t for t in ch.titles() if t is not None].count(T_1V1) == 1


def test_an_empty_configuration_retires_every_board_and_publishes_none():
    """LEADERBOARD_BOARDS carrying no board name means this deployment
    publishes none -- and leaving the last set of messages up says the
    opposite. They are permanently stale from that moment, and a reader
    cannot tell them from boards that stopped updating.

    The disable path used to return before anything read the channel, so the
    retirement that exists for a single dropped key never ran for the case
    where every key is dropped.
    """
    n2 = _fresh()
    _tick(n2)
    ch = n2["_ch"]
    assert ch.titles() == [T_1V1, T_2V2, T_FFA]
    posted = [m.id for m in ch.messages]

    n3 = _bot_ns(_Api(_payloads()), _Bot(ch), boards_raw=",")
    _run(n3["publish_boards"]())

    assert n3["_enabled_boards"]() == []
    assert [t for t in ch.titles() if t is not None] == []
    assert sorted(ch.deleted) == sorted(posted)
    assert any("retired 3 board message" in ln for ln in n3["_log"]), n3["_log"]
    assert any("names no board" in ln for ln in n3["_log"])
    assert n3["_lb_message_ids"].get(CID, {}) == {}

    # ...and it stays empty: the next tick finds nothing to retire and
    # publishes nothing, without an error.
    n3["_log"].clear()
    _run(n3["publish_boards"]())
    assert [t for t in ch.titles() if t is not None] == []
    assert not any("retired" in ln for ln in n3["_log"])


def test_an_empty_configuration_still_refuses_to_retire_on_an_unknown_key():
    """Negative control for the retirement above, in its own failure
    direction. `LEADERBOARD_BOARDS=ffaa` also yields an empty enabled set --
    but by a typo, not by a decision. Acting on it costs every board its
    message; refusing costs nothing but a log line naming the key (#430)."""
    n2 = _fresh()
    _tick(n2)
    ch = n2["_ch"]
    n3 = _bot_ns(_Api(_payloads()), _Bot(ch), boards_raw="ffaa")
    _run(n3["publish_boards"]())
    assert sorted(t for t in ch.titles() if t is not None) == sorted([T_1V1, T_2V2, T_FFA])
    assert ch.deleted == []
    assert any("no such board: ffaa" in ln for ln in n3["_log"])
    assert not any("retired" in ln for ln in n3["_log"])


def test_history_failure_edits_in_place_rather_than_deleting(ns):
    """A read that fails outright, on a tick where every id is already held.
    Nothing is deleted, nothing moves, and each board is edited where it is:
    an unread channel is not a reason to change one."""
    _tick(ns)
    ns["_ch"].history_raises = True
    ns["_log"].clear()
    _tick(ns)
    assert ns["_ch"].deleted == []
    assert any("channel read failed" in ln and "deletes nothing" in ln
               for ln in ns["_log"]), ns["_log"]
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 3


def test_restart_adopts_by_title_and_sweeps_duplicates(ns):
    _tick(ns)
    ch = ns["_ch"]
    first_ids = dict(ns["_lb_message_ids"][CID])
    # Another process posted its own set once; then this one restarts and its
    # id map is empty.
    dupes = [_run(ch.send(embeds=[_Embed(title=b["title"], description="stale")], view=None)).id
             for b in ns["_enabled_boards"]()]
    ns["_lb_message_ids"].clear()
    ns["_log"].clear()
    _tick(ns)
    # Newest per board is the keeper; the older set is swept, not left to look
    # like a second, permanently stale board.
    assert sorted(ch.deleted) == sorted(first_ids.values())
    assert set(ns["_lb_message_ids"][CID].values()) == set(dupes)
    assert any("duplicate stale board message" in ln for ln in ns["_log"])
    assert ch.titles() == [T_1V1, T_2V2, T_FFA]
    assert [len(m.edits) for m in ch.messages] == [1, 1, 1]      # adopted, then edited


# ── identity: the key the buttons carry, never the display title ──────────

T_1V1_RENAMED = "🏆 1v1 Ranked Leaderboard"


def _keys_on_channel(ch):
    """The board key each message's buttons carry, oldest first; None for a
    message with no marker."""
    out = []
    for m in ch.messages:
        key = None
        for row in m.components:
            for c in row.children:
                if (c.custom_id or "").startswith("scrlb:"):
                    key = c.custom_id.split(":")[1]
        out.append(key)
    return out


def _boards_titled(ch, *titles):
    return [m for m in ch.messages if m.embeds and m.embeds[0].title in titles]


def test_a_renamed_board_is_adopted_by_its_key_after_a_restart(ns):
    """A display-title rename, then a restart.

    The title is what a reader sees and the field a maintainer will want to
    change; the message under it is still that board. While the title was
    the identity, the restarted process looked for the NEW title, found
    nothing, posted a fresh board and left the old one -- adopted by nothing,
    retired by nothing -- on the channel for good: two 1v1 boards, one of
    them never updated again. The key in the buttons survives the rename, so
    the old message is adopted and edited into the new title.
    """
    _tick(ns)
    ch = ns["_ch"]
    old_1v1 = ns["_lb_message_ids"][CID]["1v1"]
    assert _keys_on_channel(ch) == ["1v1", "2v2", "ffa"]      # every board carries its key
    ns["BOARDS"][0]["title"] = T_1V1_RENAMED                  # the rename...
    ns["_lb_message_ids"].clear()                             # ...and the restart
    ns["_log"].clear()
    _tick(ns)
    ones = _boards_titled(ch, T_1V1, T_1V1_RENAMED)
    assert len(ones) == 1, (
        f"{len(ones)} 1v1 boards on the channel after a rename and a restart: {ch.titles()}")
    assert ones[0].id == old_1v1, "the old 1v1 message was replaced, not adopted"
    assert ch.titles() == [T_1V1_RENAMED, T_2V2, T_FFA]
    assert ch.deleted == []
    assert not any("posted fresh" in ln for ln in ns["_log"]), ns["_log"]


def test_a_board_from_before_the_marker_is_adopted_by_a_retired_title():
    """The fallback half. A board posted before the key marker existed (the
    single-board publisher's 1v1 is one) carries no key, only its title. A
    rename lists the old title in `retired_titles`, so that message is still
    adopted -- and the edit gives it the marker."""
    n2 = _fresh()
    ch = n2["_ch"]
    old = _seed_board_message(ch, T_1V1)            # no view, so no marker
    _seed_board_message(ch, T_2V2)
    _seed_board_message(ch, T_FFA)
    assert _keys_on_channel(ch) == [None, None, None]
    n2["BOARDS"][0]["title"] = T_1V1_RENAMED
    n2["BOARDS"][0]["retired_titles"] = (T_1V1,)
    _tick(n2)
    ones = _boards_titled(ch, T_1V1, T_1V1_RENAMED)
    assert [m.id for m in ones] == [old.id], (
        f"the board from before the marker was not adopted: {ch.titles()}")
    assert ch.titles() == [T_1V1_RENAMED, T_2V2, T_FFA]
    assert _keys_on_channel(ch) == ["1v1", "2v2", "ffa"]


def test_a_board_switched_off_is_retired_by_its_key_whatever_its_title_now():
    """Retirement takes the same identity. A board published under one
    title, then renamed AND switched off in the next build: the restarted
    process still knows the message as that board's, and retires it."""
    n2 = _fresh(boards_raw="1v1,2v2,ffa,1v2")
    _tick(n2)
    ch = n2["_ch"]
    assert _keys_on_channel(ch) == ["1v1", "2v2", "ffa", "1v2"]
    n3 = _bot_ns(_Api(_payloads()), _Bot(ch), boards_raw="1v1,2v2,ffa")
    n3["BOARDS"][3]["title"] = "⚔️ 1v2 Board"
    _run(n3["publish_boards"]())
    assert "1v2" not in _keys_on_channel(ch), (
        f"a switched-off, renamed board's message was left on the channel: {ch.titles()}")
    assert [t for t in ch.titles() if t is not None] == [T_1V1, T_2V2, T_FFA]
    assert any("retired 1 board message" in ln for ln in n3["_log"]), n3["_log"]


def test_a_key_this_build_does_not_know_is_never_touched_whatever_its_title(ns):
    """A marker is never second-guessed by the title under it. A key no
    BOARDS entry has is some other build's board -- a newer one sharing the
    token, or a board this build dropped from its catalogue -- so its message
    is neither adopted (even under a title this build publishes) nor
    retired."""
    _tick(ns)
    ch = ns["_ch"]
    ours = dict(ns["_lb_message_ids"][CID])
    alien = _run(ch.send(embeds=[_Embed(title=T_1V1)], view=types.SimpleNamespace(
        children=[_Button(label="◀ Prev", custom_id="scrlb:records:prev:0a0b0c0d")])))
    ns["_log"].clear()
    _tick(ns)
    assert alien.edits == [], "a board this build does not know was edited as its own"
    assert alien.id not in ch.deleted, "a board this build does not know was deleted"
    assert alien.id not in ns["_lb_message_ids"][CID].values()
    # It counts as any other message below the set: ours re-anchors beneath it.
    assert ch.messages[0].id == alien.id and ch.messages[0].embeds[0].title == T_1V1
    assert ch.titles()[1:] == [T_1V1, T_2V2, T_FFA]
    assert sorted(ch.deleted) == sorted(ours.values())


def test_every_title_and_retired_title_names_one_board(ns):
    """The fallback identity is a title, so no title may name two boards --
    a retired title included."""
    seen = {}
    for b in ns["BOARDS"]:
        for t in (b["title"], *b.get("retired_titles", ())):
            assert t not in seen, f"{t!r} names both {seen[t]} and {b['key']}"
            seen[t] = b["key"]


def test_a_board_message_of_someone_elses_is_never_touched(ns):
    """"Ours" is the BOT ACCOUNT, and the author check comes before anything
    else is asked about a message.

    Driven in both of the publisher's deleting shapes, because a title alone
    is not ownership: a message carrying an enabled board's title (where it
    would otherwise be a keeper or a duplicate) and one carrying a RETIRED
    board's title (where every copy of ours goes). Neither is touched, and
    neither is adopted as a board this publisher edits.
    """
    ch = ns["_ch"]
    other = _run(ch.send(embeds=[_Embed(title=T_1V1, description="not ours")], view=None))
    other.author = "someone-else"
    theirs_retired = _run(ch.send(embeds=[_Embed(title="⚔️ 1v2 Leaderboard")], view=None))
    theirs_retired.author = "someone-else"
    _tick(ns)
    assert other.id not in ch.deleted and other in ch.messages
    assert theirs_retired.id not in ch.deleted and theirs_retired in ch.messages
    assert other.id not in ns["_lb_message_ids"][CID].values(), (
        "a message posted by another account was adopted as our 1v1 board")
    assert other.edits == [] and theirs_retired.edits == []

    # ...and a second tick, now that the set is anchored, still leaves them.
    ns["_log"].clear()
    _tick(ns)
    assert other.id not in ch.deleted and theirs_retired.id not in ch.deleted


def test_a_transient_edit_failure_keeps_the_message_it_could_not_edit():
    """A 429 on one message says NOTHING about whether that message exists.

    Posting a replacement on it left [old, new] on the channel permanently:
    the new message alone is a correct anchored tail, so no later tick had
    any reason to rescan and nothing ever swept the old one. ONE board is
    configured here deliberately -- the three-board default hid this, because
    a fresh post at the bottom breaks the ORDER of the set and the resulting
    re-anchor happens to clean up after it.
    """
    n2 = _fresh(boards_raw="1v1")
    _tick(n2)
    ch = n2["_ch"]
    mid = n2["_lb_message_ids"][CID]["1v1"]
    ch.fetch_fails_once.add(mid)                         # e.g. a 429 on that one message
    n2["_log"].clear()
    _tick(n2)
    assert [t for t in ch.titles() if t is not None] == [T_1V1], ch.titles()
    assert n2["_lb_message_ids"][CID]["1v1"] == mid, "the id was dropped on a transient failure"
    assert any(f"edit of mid={mid} failed" in ln and "keeping mid=" in ln for ln in n2["_log"])
    assert not any("posted fresh board message" in ln for ln in n2["_log"])

    # ...and the next tick simply edits it again.
    n2["_log"].clear()
    _tick(n2)
    assert sum(1 for ln in n2["_log"] if ": edited board mid=" in ln) == 1
    assert [t for t in ch.titles() if t is not None] == [T_1V1]


def test_a_message_that_is_really_gone_is_replaced(ns):
    """Negative control for the guard above: keeping the id must not mean
    keeping it forever. A NotFound is the one answer that proves a
    replacement is needed, and the board must come back.

    Driven through the one state where the channel read cannot see the
    deletion for us: the message is there when the tick READS the channel and
    gone by the time the tick fetches it to edit -- a moderator, or another
    process, in that gap. Everywhere else the read itself notices, drops the
    id, and the board is posted fresh from the ordinary path.
    """
    _tick(ns)
    ch = ns["_ch"]
    mid = ns["_lb_message_ids"][CID]["2v2"]
    ch.vanish_on_fetch.add(mid)                  # present at the read, gone at the edit
    ns["_log"].clear()
    _tick(ns)
    assert any(f"2v2: board mid={mid} is gone" in ln for ln in ns["_log"]), ns["_log"]
    assert ns["_lb_message_ids"][CID]["2v2"] != mid
    assert sorted(t for t in ch.titles() if t is not None) == sorted([T_1V1, T_2V2, T_FFA])


def test_a_board_whose_message_the_read_cannot_see_is_not_posted_fresh(ns):
    """The same NotFound, on a tick whose channel read was INCOMPLETE.

    A fresh post follows a complete read or it does not happen. An incomplete
    read has not shown that this board has no message further back, and
    posting on it is how a second full set ends up on the channel: perfectly
    anchored, so no later tick has any reason to look again.
    """
    _tick(ns)
    ch = ns["_ch"]
    mid = ns["_lb_message_ids"][CID]["2v2"]
    ch.vanish_on_fetch.add(mid)
    ch.history_raises = True                     # ...and the read failed this tick
    ns["_log"].clear()
    _tick(ns)
    assert any(f"2v2: board mid={mid} is gone" in ln for ln in ns["_log"])
    assert any("2v2: no message id and the channel read was incomplete" in ln
               for ln in ns["_log"]), ns["_log"]
    assert [t for t in ch.titles() if t is not None] == [T_1V1, T_FFA]

    # ...and the first tick with a working read puts it back, from the
    # ordinary re-anchor path: the set is one board short, so it is not
    # anchored, and the repost sends every board including the missing one.
    ch.history_raises = False
    ns["_log"].clear()
    _tick(ns)
    assert not any("channel read was incomplete" in ln for ln in ns["_log"])
    assert sum(1 for ln in ns["_log"] if ": reposted at bottom as" in ln) == 3
    assert ch.titles() == [T_1V1, T_2V2, T_FFA]


# ── paginators ────────────────────────────────────────────────────────────

def test_each_paginator_flips_its_own_board():
    n2 = _fresh(n=60)
    _tick(n2)
    ffa_msg = n2["_ch"].messages[2]
    assert ffa_msg.embeds[0].title == T_FFA
    view = ffa_msg.view
    assert view.board["key"] == "ffa" and view.total_pages == 2
    nxt = next(c for c in view.children if c.label.startswith("Next"))
    inter = _Interaction()
    _run(nxt.callback(inter, nxt))
    page2 = inter.edits[0]["embeds"]
    assert page2[0].title == T_FFA
    assert "Page 2/2" in page2[-1].footer
    assert "avg " in page2[0].description                # FFA rows, not 1v1 rows
    assert "`# 51`" in page2[0].description              # ranks continue, they don't restart
    # No two boards' buttons share a custom_id, and each is scoped to its board.
    ids = [c.custom_id for m in n2["_ch"].messages for c in m.view.children]
    assert len(set(ids)) == len(ids)
    for m, b in zip(n2["_ch"].messages, n2["_enabled_boards"]()):
        assert all(c.custom_id.startswith(f"scrlb:{b['key']}:") for c in m.view.children)
        assert all(len(c.custom_id) <= 100 for c in m.view.children)   # Discord's cap


def test_paginator_buttons_disable_at_the_ends():
    n2 = _fresh(n=60)
    _tick(n2)
    view = n2["_ch"].messages[0].view
    prev, nxt = view.children
    assert prev.label.startswith("◀") and nxt.label.startswith("Next")
    assert prev.disabled and not nxt.disabled
    _run(nxt.callback(_Interaction(), nxt))
    assert not prev.disabled and nxt.disabled


# ── footers ───────────────────────────────────────────────────────────────

def test_inactive_suffix_comes_from_the_probe_and_only_where_one_exists():
    n2 = _fresh(boards_raw="1v1,1v2")
    n2["_api"].payloads[P_1V1] = {
        "entries": _rows_1v1(1), "total_players": 137}          # 120 active, 137 in total
    _tick(n2)
    assert [c for c in n2["_api"].calls if "include_inactive=true" in c] == [P_1V1]
    assert "17 inactive hidden (90 days)" in n2["_ch"].messages[0].embeds[-1].footer
    # 1v2's total_players is the page size (main.py's own KNOWN NIT), so a
    # probe would measure nothing and its catalogue entry sets probe=None --
    # it is NOT probed at all. Its noun says "listed" instead.
    ovt = n2["_ch"].messages[1]
    assert "inactive hidden" not in ovt.embeds[-1].footer
    assert "1v2 players listed" in ovt.embeds[-1].footer


def test_a_failed_probe_never_blocks_the_board():
    """Both ways the probe can fail, because they take different code paths.

    A transport failure or a non-200 reaches _render_board as None -- api_get
    cannot propagate -- and is handled by the `if _all:` test, not by the
    except clause. Only an unreadable 200 reaches the except clause, and the
    old version of this test drove it with a raise that production cannot
    produce, so the clause was being exercised by a path that does not exist
    and the path that DOES exist was not covered at all.
    """
    # (a) the probe endpoint is down: no suffix, and the api layer says why.
    n2 = _fresh(boards_raw="1v1")
    n2["_api"].payloads[P_1V1] = RuntimeError("probe boom")
    _tick(n2)
    assert n2["_ch"].titles() == [T_1V1]
    assert any("API GET error: probe boom" in ln for ln in n2["_log"])
    assert not any("inactive count unreadable" in ln for ln in n2["_log"])
    assert "inactive hidden" not in n2["_ch"].messages[0].embeds[-1].footer

    # (b) the probe answers 200 with a total_players that is not a number:
    # int() raises, the except clause catches it, the board still publishes.
    n3 = _fresh(boards_raw="1v1")
    n3["_api"].payloads[P_1V1] = {"entries": _rows_1v1(1), "total_players": "lots"}
    _tick(n3)
    assert n3["_ch"].titles() == [T_1V1]
    assert any("inactive count unreadable" in ln for ln in n3["_log"])
    assert "inactive hidden" not in n3["_ch"].messages[0].embeds[-1].footer


# ── an empty board is a board (v1.41.0 wave A r2) ─────────────────────────

def test_an_empty_board_publishes_as_empty_and_keeps_its_place():
    """A 200 carrying no entries is a mode nobody has played yet.

    It used to be treated as an outage, which did three things: it kept the
    PREVIOUS tick's players on the channel for as long as the mode stayed
    empty, it counted the board as unrendered so the whole set could not
    re-anchor, and on a first deploy it meant an enabled board never appeared
    at all.
    """
    n2 = _fresh(broken={U_FFA: {"entries": [], "total_players": 0}})
    _tick(n2)
    ch = n2["_ch"]
    assert ch.titles() == [T_1V1, T_2V2, T_FFA]
    ffa = ch.messages[2]
    assert "(no players)" in ffa.embeds[0].description
    assert "0 rated FFA players" in ffa.embeds[-1].footer
    assert not any("ffa: no data this tick" in ln for ln in n2["_log"])

    # ...and the set still re-anchors while that board is empty, because the
    # repost gate counts RENDERED boards and an empty board is rendered.
    ch.post_from_someone_else()
    n2["_log"].clear()
    _tick(n2)
    assert ch.titles()[-3:] == [T_1V1, T_2V2, T_FFA]
    assert sum(1 for ln in n2["_log"] if "not at the channel bottom" in ln) == 1


def test_an_outage_is_still_an_outage():
    """Negative control (#391) for the test above. "Empty is publishable"
    must not have made "the endpoint did not answer" publishable too: that
    would blank a live board on a single failed tick."""
    n2 = _fresh(broken={U_FFA: None})                      # non-200
    _tick(n2)
    assert n2["_ch"].titles() == [T_1V1, T_2V2]
    assert any("ffa: no data this tick" in ln for ln in n2["_log"])

    # An answer with no `entries` key at all is a shape problem, reported as
    # one rather than published as an empty board.
    n3 = _fresh(broken={U_FFA: {"total_players": 4}})
    _tick(n3)
    assert n3["_ch"].titles() == [T_1V1, T_2V2]
    assert any("ffa: answer carried no entries list" in ln for ln in n3["_log"])


# ── a cold start that cannot read the channel posts nothing ───────────────

def test_a_cold_start_whose_channel_read_fails_posts_no_second_set():
    """The failure this closes leaves TWO complete sets on the channel.

    A restart empties the id map, so the first tick has nothing but the
    channel read. A read that FAILS does not mean "found nothing", and
    posting a fresh set on it puts a second set below the first -- perfectly
    anchored, so no later tick has any reason to look again, and the old set
    sits there permanently stale.
    """
    ns = _fresh()
    _tick(ns)
    ch = ns["_ch"]
    before = [m.id for m in ch.messages]
    ns["_lb_message_ids"].clear()                          # restart
    ch.history_raises = True
    ns["_log"].clear()
    _tick(ns)
    assert [m.id for m in ch.messages] == before, "a second set was posted"
    assert ch.deleted == []
    assert any("channel read failed" in ln for ln in ns["_log"])
    assert sum(1 for ln in ns["_log"] if "not posting, retrying next tick" in ln) == 3

    # It recovers on the first tick whose scan works: adopts, edits, no
    # duplicate, nothing deleted.
    ch.history_raises = False
    ns["_log"].clear()
    _tick(ns)
    assert [m.id for m in ch.messages] == before
    assert ch.deleted == []
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 3


def test_the_cold_start_guard_can_fail():
    """Negative control: with the scan WORKING, the same cold start must post
    the set it cannot find. A guard that refused to post either way would
    pass the test above and never publish anything."""
    ns = _fresh()
    _tick(ns)
    ns["_ch"].messages.clear()                             # channel emptied
    ns["_lb_message_ids"].clear()                          # restart
    ns["_log"].clear()
    _tick(ns)
    assert ns["_ch"].titles() == [T_1V1, T_2V2, T_FFA]


# ── two processes on one token ────────────────────────────────────────────

def test_adopting_a_newer_set_that_is_already_anchored_does_not_repost_it():
    """Two bot processes on one token -- what a botched deploy leaves running
    for a few minutes.

    The other process has just posted its own set at the bottom. This one
    still holds ids for the set above it. Reposting on the strength of THOSE
    ids deletes and re-sends three messages that are already exactly where
    they belong -- and the other process does the same thing straight back,
    so the boards churn message ids and buttons every ten minutes with a
    delete/send gap on every pass.

    The shape that prevents it is the order: the channel is read and adopted
    FIRST, and the anchored answer comes out of that same read, after its
    deletions. The position question is therefore always asked about the set
    this tick is actually publishing. The old shape measured position from
    the ids it walked in with and had to ask a second time after adopting.
    """
    ns = _fresh()
    _tick(ns)
    ch = ns["_ch"]
    ours = dict(ns["_lb_message_ids"][CID])
    theirs = [_run(ch.send(embeds=[_Embed(title=b["title"], description="theirs")],
                           view=None)).id
              for b in ns["_enabled_boards"]()]
    ns["_log"].clear()
    _tick(ns)

    assert sorted(ch.deleted) == sorted(ours.values())     # ours were the duplicates
    assert [ns["_lb_message_ids"][CID][k] for k in ("1v1", "2v2", "ffa")] == theirs
    assert not any("reposted at bottom" in ln for ln in ns["_log"])
    assert not any("not at the channel bottom" in ln for ln in ns["_log"])
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 3
    assert ch.titles() == [T_1V1, T_2V2, T_FFA]


def test_the_re_asked_anchor_check_can_fail():
    """Negative control: when the adopted set is NOT at the bottom, the
    repost must still happen. A check that answered "anchored" either way
    would pass the test above and freeze the boards mid-channel."""
    ns = _fresh()
    _tick(ns)
    ch = ns["_ch"]
    theirs = [_run(ch.send(embeds=[_Embed(title=b["title"], description="theirs")],
                           view=None)).id
              for b in ns["_enabled_boards"]()]
    ch.post_from_someone_else()                            # buries THEIR set too
    ns["_log"].clear()
    _tick(ns)
    assert any("reposted at bottom" in ln for ln in ns["_log"])
    assert ch.titles()[-3:] == [T_1V1, T_2V2, T_FFA]
    assert all(t in ch.deleted for t in theirs)


# ── one publish per tick ──────────────────────────────────────────────────

def test_the_tick_costs_the_same_in_one_guild_and_in_five():
    """LEADERBOARD_CHANNEL_ID names ONE channel. The publisher used to take a
    guild and be called once per guild, and `guild.get_channel` returning
    None for a guild that does not own the channel fell through to
    `bot.fetch_channel`, which answers for any guild -- so every extra guild
    re-rendered and re-edited the same three boards.
    """
    one = _bot_ns(_Api(_payloads()), _Bot(_Channel(CID, "scr-bot"), guilds=1))
    _run(one["publish_lb_loop"]())
    many = _bot_ns(_Api(_payloads()), _Bot(_Channel(CID, "scr-bot"), guilds=5))
    _run(many["publish_lb_loop"]())

    assert one["_ch"].titles() == many["_ch"].titles() == [T_1V1, T_2V2, T_FFA]
    assert len(many["_api"].calls) == len(one["_api"].calls)
    assert len(many["_ch"].sent) == len(one["_ch"].sent) == 3
    assert many["_bot"].fetch_channel_calls == 0


# ── a board dropped from the config ───────────────────────────────────────

def test_a_board_dropped_from_the_config_has_its_message_retired():
    """A key removed from LEADERBOARD_BOARDS used to leave its last message
    on the channel for good: permanently stale, and indistinguishable to a
    reader from a board that stopped updating.

    The enabled set is read from the environment once, at import, so it can
    only change across a restart. Retirement rides on the reconcile read
    every tick runs anyway, so it costs no extra history call and does not
    depend on the id map having been emptied.
    """
    n2 = _fresh()
    _tick(n2)
    ch = n2["_ch"]
    assert ch.titles() == [T_1V1, T_2V2, T_FFA]

    n3 = _bot_ns(_Api(_payloads()), _Bot(ch), boards_raw="1v1,2v2")
    _run(n3["publish_boards"]())
    assert [t for t in ch.titles() if t is not None] == [T_1V1, T_2V2]
    assert any("retired 1 board message" in ln for ln in n3["_log"])


def test_retirement_is_refused_while_a_board_name_is_unknown():
    """The guard's failure direction, which is the whole reason it exists.

    A typo drops a real board from the enabled set. Acting on that costs a
    message; refusing costs the board its publish while the log names the
    key. A guard is judged by what its refusal costs (#430).
    """
    n2 = _fresh()
    _tick(n2)
    ch = n2["_ch"]
    n3 = _bot_ns(_Api(_payloads()), _Bot(ch), boards_raw="1v1,2v2,ffaa")
    _run(n3["publish_boards"]())
    assert T_FFA in ch.titles(), "a typo deleted a board's message"
    assert any("no such board: ffaa" in ln for ln in n3["_log"])
    assert not any("retired" in ln for ln in n3["_log"])


# ── burial depth ──────────────────────────────────────────────────────────

def test_a_cold_start_under_a_full_scan_of_chat_finds_the_set_it_left():
    """The old fixed 200-message scan's own failure, driven.

    The publisher used to read a FIXED depth and, finding nothing, post a
    fresh set: a restart after a busy afternoon left the old set orphaned
    above a new one, permanently stale, with nothing that would ever look
    again. The read now stops when the CHANNEL ends, not at a number, so
    there is nothing behind it to miss -- at this depth or any other below
    the ceiling.
    """
    ns = _fresh()
    _tick(ns)
    ch = ns["_ch"]
    ours = dict(ns["_lb_message_ids"][CID])
    for _ in range(210):                     # more than the old 200-message scan
        ch.post_from_someone_else()
    ns["_lb_message_ids"].clear()            # ...and a restart, so only the read knows
    ns["_log"].clear()
    _tick(ns)

    assert not any("posted fresh board message" in ln for ln in ns["_log"]), (
        "a second set was posted over a set the read should have found")
    assert ch.titles()[-3:] == [T_1V1, T_2V2, T_FFA]
    assert sorted(ch.deleted) == sorted(ours.values())    # re-anchored, not duplicated
    assert [t for t in ch.titles() if t is not None] == [T_1V1, T_2V2, T_FFA]
    assert sum(1 for ln in ns["_log"] if "not at the channel bottom" in ln) == 1


def test_the_ceiling_is_the_only_bound_left_and_it_is_pinned():
    """The one depth that is still a bound, written down so it cannot drift
    silently. Everything below it is read to the end of the channel."""
    ns = _fresh()
    assert ns["LB_RECONCILE_CEILING"] == 2000


READ_COST = "min(N, LB_RECONCILE_CEILING) // 100 + 1"


def test_the_read_costs_a_history_request_per_hundred_messages_as_the_text_says():
    """One reconcile read is one `history()` iterator and NOT one request:
    discord.py pages the REST endpoint 100 messages at a time and asks again
    until a page comes back short. The text used to say a board channel
    "costs one history call" -- true of the iterator, and of no channel of
    100 messages or more, so a long channel's REST reads were missing from
    the budget the docstrings gave. The fake now runs the library's own
    paging and counts the requests; the formula both docstrings state is
    evaluated against that count, for channels of one page and of many."""
    ns0 = _fresh()
    ceiling = ns0["LB_RECONCILE_CEILING"]
    for name in ("_reconcile_board_messages", "publish_boards"):
        flat = " ".join(ns0[name].__doc__.split())
        assert READ_COST in flat, f"{name}'s docstring does not state the read's cost as {READ_COST}"
        cap = re.search(r"LB_RECONCILE_CEILING // 100 \+ 1 = (\d+)", flat)
        assert cap and int(cap.group(1)) == ceiling // 100 + 1, (
            f"{name}'s docstring does not state the most one read costs")
        assert "costs one history call" not in flat and "history page" not in flat, name

    for n in (0, 99, 100, 250, ceiling - 1, ceiling, ceiling + 600):
        ns = _fresh()
        ch = ns["_ch"]
        for _ in range(n):
            ch.post_from_someone_else()
        _tick(ns)
        want = eval(READ_COST, {"min": min}, {"N": n, "LB_RECONCILE_CEILING": ceiling})
        assert ch.history_requests == want, (
            f"a channel of {n} messages cost {ch.history_requests} history requests, "
            f"the text says {want}")
    assert want == ceiling // 100 + 1 == 21


# ── player-authored names ─────────────────────────────────────────────────

def test_a_display_name_cannot_reformat_the_row_it_sits_in(ns):
    """Every row renderer, not just the three new ones: the 1v1 row has
    always interpolated the name raw, and a flag names a line while the
    defect is a class (#432).

    Formatting only -- every send this bot makes carries
    allowed_mentions.none(), so none of this could ever have pinged.
    """
    hostile = "**boss**|_x_`y`"
    for renderer, rows in (("_lb_line", _rows_1v1), ("_lb_line_2v2", _rows_2v2),
                           ("_lb_line_ffa", _rows_ffa), ("_lb_line_ovt", _rows_ovt)):
        row = rows(1)[0]
        row["display_name"] = hostile
        line = ns[renderer](row, 1)
        assert hostile not in line, f"{renderer} interpolates the name raw"
        assert "\\*\\*boss\\*\\*" in line, f"{renderer}: {line}"

    # A line break inside a name forges a second row. escape_markdown does
    # not touch those, so the name is flattened before it is escaped.
    for renderer, rows in (("_lb_line", _rows_1v1), ("_lb_line_2v2", _rows_2v2),
                           ("_lb_line_ffa", _rows_ffa), ("_lb_line_ovt", _rows_ovt)):
        row = rows(1)[0]
        row["display_name"] = "a\n`#  2` **ghost**"
        line = ns[renderer](row, 1)
        assert "\n" not in line and "\r" not in line, f"{renderer}: {line!r}"


def test_the_name_sanitiser_leaves_an_ordinary_name_alone(ns):
    """Control for the test above: the assertions there must be measuring the
    escaping and not a renderer that mangles every name it is given."""
    row = _rows_1v1(1)[0]
    row["display_name"] = "Plain Name"
    assert "**Plain Name**" in ns["_lb_line"](row, 1)
    # Truncation still happens FIRST, so the width budget is not spent on
    # backslashes: 24 characters of name, then escaping.
    row["display_name"] = "x" * 40
    assert "**" + "x" * 24 + "**" in ns["_lb_line"](row, 1)


# ── the harness's own guards ──────────────────────────────────────────────

def test_the_field_watch_sees_dict_get():
    """Negative control for _Watch.

    If it recorded only bracket access, a renderer reaching for a field its
    endpoint does not return with .get() would be invisible to the field
    check -- and .get is the shape that returns None instead of raising, so
    the row would publish "None" rather than failing its render.
    """
    w = _Watch(_rows_1v1(1)[0])
    assert w.get("bogus") is None
    assert "bogus" in w.read
    assert w.read - set(schemas.LeaderboardEntry.model_fields) == {"bogus"}


def test_api_get_cannot_propagate_which_is_what_the_fake_copies():
    """The fake's most load-bearing property, pinned against the real one.

    _Api answers None for a transport failure because api_get does: it wraps
    the whole request and returns None on any exception. If that ever
    changed, every "no data this tick" path in this file would be exercising
    a shape production no longer has -- and, the other way round, a fake that
    RAISED (which is what it used to do) put the suite on paths no network
    failure can reach.
    """
    fn = next(n for n in TREE.body
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "api_get")
    broad = [h for h in ast.walk(fn) if isinstance(h, ast.ExceptHandler)
             and (h.type is None or getattr(h.type, "id", None) == "Exception")]
    assert broad, "api_get no longer catches Exception: a transport failure now propagates"
    for h in broad:
        assert not [n for n in ast.walk(h) if isinstance(n, ast.Raise)], (
            "api_get's catch-all re-raises")
        rets = [n for n in ast.walk(h) if isinstance(n, ast.Return)]
        assert rets and all(
            isinstance(n.value, ast.Constant) and n.value.value is None for n in rets), (
            "api_get's catch-all no longer returns None")


def test_no_board_asks_for_a_url_the_fixture_did_not_declare(ns):
    """The fixture is keyed on WHOLE urls, which is what makes a changed
    query value visible at all: an undeclared url answers nothing and is
    recorded."""
    _tick(ns)
    assert ns["_api"].unexpected == []


def test_the_url_fixture_can_fail(ns):
    """Negative control (#391) for the exact-url fixture. Move one query
    VALUE -- precisely the change the old path-keyed fake could not see, and
    the one that publishes a different population with no error anywhere --
    and the board must stop resolving."""
    for b in ns["BOARDS"]:
        if b["key"] == "2v2":
            b["path"] = b["path"].replace("min_series=1", "min_series=999")
    _tick(ns)
    assert ns["_api"].unexpected == ["/team/leaderboard?limit=500&min_series=999"]
    assert ns["_ch"].titles() == [T_1V1, T_FFA]
