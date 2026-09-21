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
             "_enabled_boards", "_render_board", "_adopt_board_messages", "_boards_are_anchored",
             "_repost_board_set", "_remember_pending_delete", "_delete_board_message",
             "_retry_pending_deletes", "_cancel_owed_deletes_for_live_boards",
             "publish_boards", "publish_lb_loop"}
WANT_CLASS = {"LeaderboardPaginator"}
WANT_ASSIGN = {"RANK_ROLES", "LB_PAGE_SIZE", "LB_TOTAL_FETCH", "BOARDS",
               "_lb_message_ids", "_lb_unknown_board_keys", "_lb_pending_deletes",
               "LB_PENDING_DELETE_CAP", "LB_HISTORY_SCAN", "_LB_NAME_BREAKS"}

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
        # A live channel refuses sends, edits and deletes: a 5xx, a rate
        # limit, a revoked Manage-Messages. Without these the repost path --
        # the only code here that REMOVES a message -- has no failing case in
        # the suite, and a check that cannot fail is worse than none (#342).
        self.send_fails_for_titles = set()
        self.delete_fails = set()
        self.edit_fails = set()

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
        for m in self.messages:
            if m.id == mid:
                return m
        raise _not_found(f"Unknown Message {mid}")

    def history(self, limit=100):
        if self.history_raises:
            raise RuntimeError("history boom")
        snapshot = list(self.messages)[-limit:][::-1]      # newest first, as Discord answers

        async def gen():
            for i, m in enumerate(snapshot):
                if self.history_raises_after is not None and i >= self.history_raises_after:
                    raise RuntimeError("history boom part-way")
                yield m
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
    like the other three and printed 5880%% for a 58.8%% player, and the
    fixture encoded the same assumption so nothing failed.

    Both halves are pinned. The RENDERER half asserts that the one row
    renderer which shows a win rate at all -- the 1v2 one -- turns its own
    endpoint's unit into the right human percentage, and that no sibling has
    quietly grown a win-rate column. It does NOT check "each board's human
    percentage": three of the four rows carry no win rate, and the sweep
    below asserts exactly that. The SOURCE half asserts main.py still
    produces those units IN THE FOUR HANDLERS THEMSELVES, so that normalising
    the server fails HERE, with a message saying the renderers must change
    too, rather than silently making every 1v2 row read 1%%.

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


def test_a_failed_repost_delete_leaves_a_duplicate_and_the_duplicate_is_retried(ns):
    """The other failure direction, which is the price of the fix.

    If the replacement goes out but the old message will not delete, the
    channel carries that board twice for a tick. That is the deliberate
    trade: a stale duplicate above the set is recoverable, an absent board is
    not recoverable until the next tick. We track the NEW id either way, so
    the next tick edits the right message.

    What must NOT happen is the duplicate being left there. It used to be:
    the failure was logged and forgotten, and the re-adopt sweep that was
    supposed to catch it only runs when a board's id is MISSING -- which this
    path has just made certain it is not. So the id is queued and retried on
    every tick until the delete lands or the message is gone.
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
    assert ns["_lb_pending_deletes"][CID] == [old_2v2]

    # The next tick retries it, with no rescan needed and nothing else moved.
    ch.delete_fails = set()
    ns["_log"].clear()
    _tick(ns)
    titles = [t for t in ch.titles() if t is not None]
    assert titles.count(T_2V2) == 1, titles
    assert ns["_lb_pending_deletes"][CID] == []
    assert any(f"swept stale board message mid={old_2v2}" in ln for ln in ns["_log"])


def test_the_duplicate_retry_can_fail(ns):
    """Negative control (#391) for the sweep above: while the delete keeps
    failing, the id must STAY queued. A queue that empties itself on failure
    would pass the test above and fix nothing."""
    _tick(ns)
    ch = ns["_ch"]
    old_2v2 = ns["_lb_message_ids"][CID]["2v2"]
    ch.post_from_someone_else()
    ch.delete_fails = {old_2v2}
    _tick(ns)
    assert ns["_lb_pending_deletes"][CID] == [old_2v2]
    ns["_log"].clear()
    _tick(ns)                                   # still refused
    assert ns["_lb_pending_deletes"][CID] == [old_2v2]
    assert any(f"mid={old_2v2} still not deletable" in ln for ln in ns["_log"])
    assert [t for t in ch.titles() if t is not None].count(T_2V2) == 2


def test_the_pending_delete_queue_is_bounded(ns):
    """A channel with Manage-Messages revoked refuses every delete, once per
    tick, forever. The queue is a retry list, not a leak."""
    q = []
    cap = ns["LB_PENDING_DELETE_CAP"]
    for i in range(cap + 5):
        ns["_remember_pending_delete"](q, 9000 + i)
    assert len(q) == cap
    assert 9000 not in q and (9000 + cap + 4) in q
    ns["_remember_pending_delete"](q, 9000 + cap + 4)      # already queued
    assert len(q) == cap


def _seed_board_message(ch, title):
    """One board message left on the channel by an EARLIER process.

    The publisher's id map is process memory, so a fresh process meets a
    channel it did not post into. This is what the cold-start scan adopts.
    """
    return _run(ch.send(embeds=[_Embed(title=title)], view=None))


def test_an_owed_delete_is_cancelled_when_its_message_becomes_the_live_board(ns):
    """The owed-delete queue and the live-id map are two records of the same
    message ids, and a scan can move an id from the first into the second.

    An earlier run left two 1v1 messages. The cold-start scan keeps the newer
    and queues the older, whose delete is refused. A moderator then deletes
    the keeper -- so the next scan finds the QUEUED message as the only 1v1
    board on the channel and adopts it. From that moment one id means both
    "the board we publish" and "a delete we still owe", and the sweep at the
    top of the next tick acts on the second reading.

    The cost is not a churned message id. On a tick where that board's
    endpoint is down, "no data this tick" leaves the board alone by design,
    so nothing reposts what the sweep removed: the channel carries two boards
    instead of three for the whole outage. That tick DOES log the sweep, but
    nothing connects the two lines -- the board's own outcome line says it
    was left as it is, and the line that removed it names a bare message id.
    Every tick after it is indistinguishable from an ordinary outage tick.
    """
    ch = ns["_ch"]
    old_1v1 = _seed_board_message(ch, T_1V1)
    new_1v1 = _seed_board_message(ch, T_1V1)
    _seed_board_message(ch, T_2V2)
    _seed_board_message(ch, T_FFA)
    ch.delete_fails = {old_1v1.id}

    _tick(ns)
    ids = ns["_lb_message_ids"][CID]
    pending = ns["_lb_pending_deletes"][CID]
    assert ids["1v1"] == new_1v1.id
    assert pending == [old_1v1.id], pending

    _run(new_1v1.delete())                 # a moderator removes the keeper

    ns["_log"].clear()
    _tick(ns)
    assert ids["1v1"] == old_1v1.id, "the surviving 1v1 message was not adopted"
    assert old_1v1.id not in pending, (
        "mid=%d is the live 1v1 board AND is queued for deletion; the next "
        "tick's sweep deletes the board it is publishing" % old_1v1.id)

    # Now the sweep's own preconditions: the refusal clears, 1v1 is down.
    ch.delete_fails = set()
    ns["_api"].payloads[U_1V1] = None
    ns["_log"].clear()
    _tick(ns)
    assert not any(f"swept stale board message mid={old_1v1.id}" in ln
                   for ln in ns["_log"]), ns["_log"]
    titles = [t for t in ch.titles() if t is not None]
    assert titles.count(T_1V1) == 1, (
        "the live 1v1 board was swept as an owed delete, and the outage means "
        "nothing reposts it: %r" % titles)

    _tick(ns)                              # the outage continues
    assert T_1V1 in [t for t in ch.titles() if t is not None]


def test_the_sweep_refuses_an_id_the_publisher_holds_after_a_part_way_scan(ns):
    """Negative control's other half: the sweep's own check is not redundant.

    The adopt path cancels an owed delete as it adopts, which covers the
    ordinary route. It cannot cover this one. A history read that dies
    PART-WAY has already queued whatever duplicates it got through, and it
    returns without merging its keepers -- so the previous tick's id stays in
    `ids` and may be exactly one of the ids it just queued. That state never
    passes through the adopt-side cancel at all, and the only thing between
    it and a deleted live board is the sweep checking at the point of use.
    """
    ch = ns["_ch"]
    ch.post_from_someone_else()            # so the scan has a 5th thing to die on
    held = _seed_board_message(ch, T_1V1)
    _seed_board_message(ch, T_2V2)
    _seed_board_message(ch, T_FFA)

    _tick(ns)
    ids = ns["_lb_message_ids"][CID]
    assert ids["1v1"] == held.id

    # Another process posts a newer 1v1, so the next scan calls OURS the
    # duplicate -- while we are still publishing it.
    newer = _seed_board_message(ch, T_1V1)
    ch.delete_fails = {held.id}
    ch.history_raises_after = 4            # dies after `held` has been queued

    ns["_log"].clear()
    _tick(ns)
    pending = ns["_lb_pending_deletes"][CID]
    assert pending == [held.id], pending
    assert ids["1v1"] == held.id, "the failed scan must not have merged keepers"
    assert any("rescan failed" in ln for ln in ns["_log"]), ns["_log"]

    # The sweep's preconditions: a readable channel and a delete that works.
    # A moderator removes the newer message, so the one we hold is once again
    # the only 1v1 board there is -- and 1v1 goes down, so nothing reposts
    # whatever the sweep takes. Without this last part the scan would delete
    # mid=held itself, as a genuine duplicate, and the sweep's contribution
    # would not be separable from it.
    ch.history_raises_after = None
    ch.delete_fails = set()
    _run(newer.delete())
    ns["_api"].payloads[U_1V1] = None
    ns["_log"].clear()
    _tick(ns)
    assert not any(f"swept stale board message mid={held.id}" in ln
                   for ln in ns["_log"]), ns["_log"]
    titles = [t for t in ch.titles() if t is not None]
    assert titles.count(T_1V1) == 1, (
        "mid=%d is what the 1v1 board is published as and the sweep took it: "
        "%r" % (held.id, titles))


def test_history_failure_edits_in_place_rather_than_deleting(ns):
    _tick(ns)
    ns["_ch"].history_raises = True
    ns["_log"].clear()
    _tick(ns)
    assert ns["_ch"].deleted == []
    assert any("channel tail read failed" in ln for ln in ns["_log"])
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


def test_a_board_message_of_someone_elses_is_never_touched(ns):
    other = _run(ns["_ch"].send(embeds=[_Embed(title=T_1V1, description="not ours")], view=None))
    other.author = "someone-else"
    _tick(ns)
    assert other.id not in ns["_ch"].deleted
    assert other in ns["_ch"].messages


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

    Driven through the single state where the anchor check cannot see the
    deletion for us -- a channel whose history read is failing, where
    _boards_are_anchored deliberately answers True and every board is edited
    in place. Anywhere else, a missing message breaks the tail and the
    re-anchor path handles it.
    """
    _tick(ns)
    ch = ns["_ch"]
    mid = ns["_lb_message_ids"][CID]["2v2"]
    ch.messages = [m for m in ch.messages if m.id != mid]      # a moderator deleted it
    ch.history_raises = True
    ns["_log"].clear()
    _tick(ns)
    assert any(f"2v2: board mid={mid} is gone" in ln for ln in ns["_log"])
    assert ns["_lb_message_ids"][CID]["2v2"] != mid
    assert sorted(t for t in ch.titles() if t is not None) == sorted([T_1V1, T_2V2, T_FFA])


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

    A restart empties the id map, so the first tick must scan. A scan that
    FAILS does not mean "found nothing", and posting a fresh set on it puts a
    second set below the first -- perfectly anchored, so no later tick has
    any reason to rescan, and the old set sits there permanently stale.
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
    assert any("rescan failed" in ln for ln in ns["_log"])
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
    still holds ids for the set above it, so its anchor check says "not
    anchored" and it heads for the repost; the rescan it runs first ADOPTS
    the other set. Reposting after that deletes and re-sends three messages
    that are already exactly where they belong -- and the other process does
    the same thing straight back, so the boards churn message ids and buttons
    every ten minutes with a delete/send gap on every pass. So the question
    is asked again after adopting.
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
    assert any("the set at the channel bottom is the one just adopted" in ln
               for ln in ns["_log"])
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
    only change across a restart -- and a restart empties the id map, which
    forces the scan this retirement rides on. No extra history read.
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

def test_the_rescan_depth_is_pinned_and_the_id_path_does_not_depend_on_it():
    """Which path the scan depth actually bounds.

    Only ADOPTION reads history. Once an id is held, fetch_message reaches
    that message at ANY depth, so the ordinary bury-and-re-anchor cycle is
    not bounded by this number -- a set buried under more than a full scan's
    worth of chat is still re-anchored, and its old messages still deleted.
    A COLD START past that depth is the case that is not covered, and it
    stays a recorded bound rather than a claim.
    """
    ns = _fresh()
    assert ns["LB_HISTORY_SCAN"] == 200
    _tick(ns)
    ch = ns["_ch"]
    ours = dict(ns["_lb_message_ids"][CID])
    for _ in range(ns["LB_HISTORY_SCAN"] + 10):
        ch.post_from_someone_else()
    ns["_log"].clear()
    _tick(ns)
    assert ch.titles()[-3:] == [T_1V1, T_2V2, T_FFA]
    assert sorted(ch.deleted) == sorted(ours.values())
    assert sum(1 for ln in ns["_log"] if "not at the channel bottom" in ln) == 1


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
