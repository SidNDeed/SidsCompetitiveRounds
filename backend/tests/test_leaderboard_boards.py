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

import main
import schemas

SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "discord_bot.py"))
TEXT = open(SRC, encoding="utf-8").read()
TREE = ast.parse(TEXT)

WANT_FUNC = {"rank_emoji", "get_rank_name", "_escape_md", "_lb_line", "_split_lb_descriptions",
             "_build_board_embeds", "_board_medal", "_lb_line_2v2", "_lb_line_ffa", "_lb_line_ovt",
             "_enabled_boards", "_render_board", "_delete_board_message", "_own_embed_messages",
             "_adopt_board_messages", "_boards_are_anchored", "_repost_board_set", "publish_boards",
             "publish_lb_loop"}
WANT_CLASS = {"LeaderboardPaginator"}
WANT_ASSIGN = {"RANK_ROLES", "LB_PAGE_SIZE", "LB_TOTAL_FETCH", "BOARDS",
               "_lb_message_ids", "_lb_unknown_board_keys", "_lb_swept"}

CID = 777
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


class _NotFound(Exception):
    """discord.NotFound: Discord answered 404 for the message. Round 4: the
    one failure that proves a board message gone (finding 21)."""


FAKE_DISCORD = types.SimpleNamespace(
    Embed=_Embed, Interaction=object, NotFound=_NotFound,
    ButtonStyle=types.SimpleNamespace(secondary="secondary"),
    Color=types.SimpleNamespace(gold=lambda: "gold", blurple=lambda: "blurple",
                                orange=lambda: "orange", teal=lambda: "teal"),
    ui=types.SimpleNamespace(View=_View, Button=_Button, button=_button))


class _Msg:
    _next = 5000

    def __init__(self, ch, author, embeds, view):
        _Msg._next += 1
        self.id, self.ch, self.author, self.embeds, self.view = _Msg._next, ch, author, embeds, view
        self.edits = []

    async def edit(self, **kw):
        if self not in self.ch.messages:
            raise _NotFound(f"404 Unknown Message {self.id}")
        self.edits.append(kw)
        self.embeds = kw.get("embeds", self.embeds)
        self.view = kw.get("view", self.view)

    async def delete(self):
        if self.id in self.ch.delete_fails:
            raise RuntimeError("403 Missing Permissions")
        if self not in self.ch.messages:
            raise _NotFound(f"404 Unknown Message {self.id}")
        self.ch.deleted.append(self.id)
        self.ch.messages = [m for m in self.ch.messages if m.id != self.id]


class _Channel:
    """Messages oldest-first, the way the channel reads top to bottom."""

    def __init__(self, cid, bot_user):
        self.id, self.bot_user = cid, bot_user
        self.messages, self.deleted, self.sent = [], [], []
        self.history_raises = False
        self.history_reads = 0
        # A walk whose later page fails: this many messages are read, newest
        # first, and then the read raises (round 4).
        self.history_fails_after = None
        self.fetch_fails_once = set()
        # A live channel refuses sends and deletes: a 5xx, a rate limit, a
        # revoked Manage-Messages. Without these the repost path -- the only
        # code here that REMOVES a message -- has no failing case in the
        # suite, and a check that cannot fail is worse than none (#342).
        self.send_fails_for_titles = set()
        self.delete_fails = set()

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
        if mid in self.fetch_fails_once:
            self.fetch_fails_once.discard(mid)
            raise RuntimeError("429 rate limited")
        for m in self.messages:
            if m.id == mid:
                return m
        raise _NotFound(f"404 Unknown Message {mid}")

    def history(self, limit=100):
        if self.history_raises:
            raise RuntimeError("history boom")
        self.history_reads += 1
        # limit=None is the whole channel, as discord.py pages it (round 4).
        msgs = list(self.messages) if limit is None else list(self.messages)[-limit:]
        snapshot = msgs[::-1]                              # newest first, as Discord answers
        fails_after = self.history_fails_after

        async def gen():
            for i, m in enumerate(snapshot):
                if fails_after is not None and i >= fails_after:
                    raise RuntimeError("history page failed")
                yield m
        return gen()

    def titles(self):
        return [(m.embeds[0].title if m.embeds else None) for m in self.messages]

    @property
    def last_message_id(self):
        """TextChannel.last_message_id, as the channel stands: the id of its
        newest message (the tournament board's burial check reads it)."""
        return self.messages[-1].id if self.messages else None


class _Bot:
    def __init__(self, ch):
        self.user, self.ch = "scr-bot", ch
        self.guilds = [types.SimpleNamespace(get_channel=lambda cid: ch if cid == CID else None)]

    def get_channel(self, cid):
        return self.ch if cid == CID else None

    async def fetch_channel(self, cid):
        return self.ch if cid == CID else None


class _Api:
    """api_get, answering by exact url first and then by path. None models a
    non-200 (api_get logs the status and returns None); an Exception value is
    raised."""

    def __init__(self, payloads):
        self.payloads, self.calls = dict(payloads), []

    async def get(self, path, timeout=8.0):
        self.calls.append(path)
        val = self.payloads[path] if path in self.payloads else self.payloads.get(path.split("?")[0])
        if isinstance(val, Exception):
            raise val
        return val


class _Interaction:
    def __init__(self):
        self.edits = []

        async def edit_message(**kw):
            self.edits.append(kw)
        self.response = types.SimpleNamespace(edit_message=edit_message)


# ── lifting ───────────────────────────────────────────────────────────────

def _lift(want_func=WANT_FUNC, want_assign=WANT_ASSIGN, want_class=WANT_CLASS):
    picked, seen = [], set()
    for node in TREE.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in want_assign:
                    picked.append(node)
                    seen.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in want_assign:
            picked.append(node)
            seen.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in want_func:
            fn = copy.deepcopy(node)
            fn.decorator_list = []                     # @tasks.loop is the harness's
            picked.append(fn)
            seen.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name in want_class:
            picked.append(copy.deepcopy(node))
            seen.add(node.name)
    want = want_func | want_assign | want_class
    assert seen == want, want - seen
    return picked


def _bot_ns(api, bot, boards_raw="1v1,2v2,ffa", out=None):
    """A fresh namespace per test — _lb_message_ids and the unknown-key set
    are real process state and must never be shared between ticks of
    different tests."""
    out = out if out is not None else []
    ns = {"discord": FAKE_DISCORD, "os": os, "re": re, "bot": bot, "api_get": api.get,
          "datetime": _dt.datetime, "timezone": _dt.timezone,
          "LEADERBOARD_CHANNEL_ID": CID, "LB_ACTIVE_DAYS": 90,
          "LEADERBOARD_BOARDS_RAW": boards_raw,
          "print": lambda *a, **k: out.append(" ".join(str(x) for x in a))}
    exec(compile(ast.Module(body=_lift(), type_ignores=[]), SRC, "exec"), ns)
    ns["_log"], ns["_api"], ns["_ch"] = out, api, bot.ch
    ns["_guild"] = bot.guilds[0]
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
    p = {"/leaderboard": {"entries": _rows_1v1(n), "total_players": 120},
         "/team/leaderboard": {"entries": _rows_2v2(n), "total_players": 40},
         "/ffa/leaderboard": {"entries": _rows_ffa(n), "total_players": 25},
         "/ovt/leaderboard": {"entries": _rows_ovt(n), "total_players": n}}
    p.update(broken or {})
    return p


def _fresh(n=3, broken=None, boards_raw="1v1,2v2,ffa"):
    api = _Api(_payloads(n, broken))
    return _bot_ns(api, _Bot(_Channel(CID, "scr-bot")), boards_raw=boards_raw)


@pytest.fixture
def ns():
    return _fresh()


def _tick(ns):
    _run(ns["publish_boards"](ns["_guild"]))


# ── reachability: the code under test is the code that runs ───────────────

def test_the_loop_publishes_the_set_and_the_single_board_publisher_is_gone():
    fn = next(n for n in TREE.body
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "publish_lb_loop")
    assert [ast.unparse(d) for d in fn.decorator_list] == ["tasks.loop(minutes=10)"]
    assert "await publish_boards(guild)" in ast.unparse(fn)
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


def test_every_board_url_resolves_on_the_api_with_the_params_it_sends(ns):
    for b in ns["BOARDS"]:
        for url in [b["path"]] + ([b["probe"]] if b["probe"] else []):
            route, _, query = url.partition("?")
            params = _route_params("/api/v1" + route)
            assert params is not None, f"{b['key']}: no GET route /api/v1{route}"
            for pair in query.split("&"):
                name = pair.split("=")[0]
                # A param the endpoint does not declare is dropped silently and
                # the board publishes the UNFILTERED answer (bug #266's class).
                assert name in params, f"{b['key']}: /api/v1{route} takes no '{name}'"


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
    def __init__(self, d):
        super().__init__(d)
        self.read = set()

    def __getitem__(self, k):
        self.read.add(k)
        return super().__getitem__(k)


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


# -- a display name is literal inside every board row (round 3 finding 16) --

# Every character the rows must make literal, and no digit and no "!": the
# negative control escapes "!" as well, which must leave these rows alone.
_MD_NAME = "a*b_c`d~e|f\\g[h]<i>j"
_MD_LITERAL = frozenset("\\*_~|`[]<>")
_MD_ROWS = {"_lb_line": _rows_1v1, "_lb_line_2v2": _rows_2v2,
            "_lb_line_ffa": _rows_ffa, "_lb_line_ovt": _rows_ovt}


# Round 4, finding 16's newline half: the characters str.splitlines() breaks a
# line on. A CRLF pair is one break.
_MD_BREAKS = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"


def _one_line(name):
    """Every line break one space, a CRLF pair one break (round 4)."""
    out, i = [], 0
    while i < len(name):
        step = 2 if name.startswith("\r\n", i) else 1
        out.append(" " if name[i] in _MD_BREAKS else name[i])
        i += step
    return "".join(out)


def _expected_md(name):
    """The name as a row must show it: cut to 24 characters FIRST, then every
    line break a single space, and each significant character preceded by one
    backslash. Written out here, not taken from the bot's helper, so the
    helper does not grade itself."""
    return "".join("\\" + ch if ch in _MD_LITERAL else ch for ch in _one_line(name[:24]))


def _bold_segment(line):
    """The text between a row's opening ** and the first ** after it that no
    backslash escapes -- where Discord closes the bold."""
    start = line.index("**") + 2
    i = start
    while i < len(line) - 1:
        if line[i] == "\\":
            i += 2
            continue
        if line.startswith("**", i):
            return line[start:i]
        i += 1
    raise AssertionError("the row's bold never closes: " + line)


@pytest.mark.parametrize("renderer", sorted(_MD_ROWS))
@pytest.mark.parametrize("name", [_MD_NAME, "x" * 23 + "*tail", "y" * 23 + "\\tail",
                                  "Alice\n# 2 Fake", "Bob\r\n- 3 Fake", "Cy\r> 4 Fake",
                                  "Dee\u2028**5 Fake**", "z" * 23 + "\r\nrow"],
                         ids=["every-significant-character", "cut-at-a-star", "cut-at-a-backslash",
                              "lf", "crlf", "cr", "line-separator", "crlf-cut-at-24"])
def test_a_display_name_is_literal_inside_every_board_row(ns, renderer, name):
    """A display name went into `**...**` as typed, so a name carrying * _ `
    ~ | could close the bold early, open italics, code or a spoiler, or bleed
    into the next row. All four renderers now escape through ONE helper,
    after the 24-character cut: the two cut cases put a * or a backslash
    exactly at character 24, where escaping first and cutting second strands
    a lone backslash that swallows the closing **. Controls: the escape
    skipped at one renderer reds that renderer's cases only.

    Round 4, finding 16's newline half: the frozen requirement is literal,
    SINGLE-ROW text, newlines included. The round-3 report's example
    ("Alice" then a new line and "# 2 Fake") still made an apparent extra
    row. Every line break is now one space, and the row one line."""
    row = _MD_ROWS[renderer](1)[0]
    row["display_name"] = name
    line = ns[renderer](row, 1)
    assert _bold_segment(line) == _expected_md(name), (renderer, line)
    assert len(line.splitlines()) == 1, (renderer, line)


@pytest.mark.parametrize("renderer", sorted(_MD_ROWS))
def test_a_line_break_in_a_name_never_makes_a_second_row(ns, renderer):
    """Round 4, finding 16's newline half, on a whole board: three players
    whose names carry a LF, a CRLF pair and a Unicode line separator, each
    followed by text shaped like a row, render as exactly three rows.

    MUTATION: the breaks left in, or only LF made a space. Must fail."""
    rows = _MD_ROWS[renderer](3)
    for r, name in zip(rows, ("Alice\n# 2 Fake", "Bob\r\n`#  3` Fake", "Cy\u2028> 4 Fake")):
        r["display_name"] = name
    board = next(b for b in ns["BOARDS"] if b["line"] is ns[renderer])
    embeds = ns["_build_board_embeds"](board, rows, 3, 0, 1)
    header, body = embeds[0].description.split("\n\n", 1)
    assert header.startswith("Updated <t:"), header
    assert len(body.splitlines()) == 3, body


@pytest.mark.parametrize("renderer", sorted(_MD_ROWS))
def test_a_plain_display_name_renders_unchanged(ns, renderer):
    row = _MD_ROWS[renderer](1)[0]
    row["display_name"] = "Plain Name"
    assert "**Plain Name**" in ns[renderer](row, 1)


def _renderer_source(ns, name):
    """Source text of one row renderer, for the sibling sweep."""
    import inspect
    return inspect.getsource(ns[name])


def test_win_rate_unit_is_per_endpoint(ns):
    """win_rate is a 0-1 FRACTION on 1v1/2v2/FFA and a PERCENT on 1v2.

    One field name, two units, decided by the endpoint. That is the defect
    this test exists to stop recurring: the 1v2 renderer multiplied by 100
    like the other three and printed 5880%% for a 58.8%% player, and the
    fixture encoded the same assumption so nothing failed.

    Both halves are pinned. The renderer half asserts each board turns its
    OWN endpoint's real shape into the same human percentage. The source
    half asserts main.py still produces those units, so that normalising the
    server fails HERE, with a message saying the renderers must change too,
    rather than silently making every 1v2 row read 1%%.
    """
    import io as _io
    import re
    from pathlib import Path

    # --- renderer half: same player, four boards, one right answer --------
    ovt = _rows_ovt(1)[0]
    ovt["wins"], ovt["losses"], ovt["games_played"] = 20, 14, 34
    ovt["win_rate"] = 58.8                       # percent, as /ovt/leaderboard sends it
    assert "59%" in ns["_lb_line_ovt"](ovt, 1), (
        "the 1v2 renderer must NOT scale: its endpoint already returns a percent")
    assert "5880%" not in ns["_lb_line_ovt"](ovt, 1)

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

    # --- source half: the units in main.py have not moved -----------------
    main_py = Path(__file__).resolve().parents[1] / "api" / "main.py"
    src = _io.open(main_py, encoding="utf-8", newline="").read()

    scaled = re.findall(r"win_rate\s*=\s*round\(\s*100(?:\.0)?\s*\*", src)
    assert len(scaled) == 1, (
        "exactly one leaderboard endpoint may pre-scale win_rate (the 1v2 one). "
        "Found %d. If a NEW endpoint started pre-scaling, its renderer must drop "
        "its own 100* too; if the 1v2 one STOPPED, _lb_line_ovt must start "
        "scaling and NativeUI.cs:5980 must change with it." % len(scaled))

    for label, needle in (
            ("1v1", "ROUND(COALESCE(c.wins, 0)::numeric / c.total, 4)"),
            ("2v2", "ROUND(COALESCE(ss.wins, 0)::numeric / ss.total, 4)"),
            ("ffa", "win_rate=round(wins / games, 3)"),
    ):
        assert needle in src, (
            "%s no longer produces win_rate as a 0-1 fraction; its renderer "
            "multiplies by 100 and will now be wrong" % label)


def test_the_win_rate_unit_detector_can_fail(ns):
    """Negative control (#391) for the renderer half above.

    A detector that cannot fail is decoration. Feed the 1v2 renderer the
    FRACTION its sibling boards use and the assertion above must stop
    holding — otherwise it was never testing the scaling at all.
    """
    ovt = _rows_ovt(1)[0]
    ovt["win_rate"] = 0.588                      # the wrong unit for this board
    assert "59%" not in ns["_lb_line_ovt"](ovt, 1), (
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
    n2 = _fresh(broken={"/ffa/leaderboard": None})
    _run(n2["publish_lb_loop"]())                        # through the loop, not around it
    assert n2["_ch"].titles() == [T_1V1, T_2V2]
    assert any("ffa: no data this tick" in ln for ln in n2["_log"])
    assert not any("Leaderboard publish error" in ln for ln in n2["_log"])
    # A row shape the renderer cannot read is contained the same way.
    n3 = _fresh(broken={"/team/leaderboard": {"entries": [{"rank": 1, "display_name": "x"}],
                                              "total_players": 1}})
    _run(n3["publish_lb_loop"]())
    assert n3["_ch"].titles() == [T_1V1, T_FFA]
    assert any("2v2: render failed" in ln for ln in n3["_log"])
    assert not any("Leaderboard publish error" in ln for ln in n3["_log"])
    # ...and so is an endpoint that raises instead of answering.
    n4 = _fresh(broken={"/ffa/leaderboard": RuntimeError("timeout")})
    _run(n4["publish_lb_loop"]())
    assert n4["_ch"].titles() == [T_1V1, T_2V2]
    assert any("ffa: render failed (timeout)" in ln for ln in n4["_log"])


def test_an_empty_board_is_published_as_empty_not_left_stale(ns):
    """Round 3 finding 14. A 200 with entries=[] is an answer -- every FFA
    player aged past the activity window, say. It was taken as no data, so the
    board kept showing the last list for good. It now renders as an honest
    empty board, edited in place. A payload with no entries list at all is
    still no data and leaves the board as it is.

    MUTATION: take an empty list as no data again. Must fail."""
    _tick(ns)
    ch = ns["_ch"]
    ffa = ch.messages[-1]
    ns["_api"].payloads["/ffa/leaderboard"] = {"entries": [], "total_players": 0}
    ns["_api"].payloads["/ffa/leaderboard?limit=1&min_games=1&include_inactive=true"] = {
        "entries": _rows_ffa(1), "total_players": 25}
    ns["_log"].clear()
    _tick(ns)
    assert not any("ffa: no data this tick" in ln for ln in ns["_log"]), ns["_log"]
    assert any("ffa: edited board mid=%d" % ffa.id in ln for ln in ns["_log"]), ns["_log"]
    assert ffa.embeds[0].title == T_FFA
    assert "(no players)" in ffa.embeds[0].description
    assert "Ffa0" not in "".join(e.description for e in ffa.embeds)
    foot = ffa.embeds[-1].footer
    assert foot.startswith("Page 1/1 ") and "0 rated FFA players" in foot, foot
    assert "25 inactive hidden (90 days)" in foot, foot
    assert [b.disabled for b in ffa.view.children] == [True, True]
    # No entries list at all is not an answer: the board is left as it is.
    ns["_api"].payloads["/ffa/leaderboard"] = {"total_players": 0}
    edits = len(ffa.edits)
    ns["_log"].clear()
    _tick(ns)
    assert any("ffa: no data this tick" in ln for ln in ns["_log"]), ns["_log"]
    assert len(ffa.edits) == edits


def test_a_board_nobody_has_played_yet_is_still_posted():
    """Round 3 finding 14, the other half: a board for a mode nobody has
    played yet answers entries=[], and was never posted at all. It is posted
    in its place in the set, as an empty board.

    MUTATION: take an empty list as no data again. Must fail."""
    n2 = _fresh(broken={"/team/leaderboard": {"entries": [], "total_players": 0}})
    _tick(n2)
    ch = n2["_ch"]
    assert ch.titles() == [T_1V1, T_2V2, T_FFA], ch.titles()
    assert "(no players)" in ch.messages[1].embeds[0].description
    assert "0 rated 2v2 players" in ch.messages[1].embeds[-1].footer


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

    Since round 4 (finding 21) the repost deletes each board's old message
    before it posts the replacement, and _repost_board_set skips a board it
    holds no render for before touching anything of it. So a repost one
    board short would not lose that board; it would strand it above the
    moved set, out of order. The gate keeps the set whole, and stays."""
    _tick(ns)
    ch = ns["_ch"]
    ch.post_from_someone_else()
    ns["_api"].payloads["/ffa/leaderboard"] = None       # down for this tick only
    ns["_log"].clear()
    _tick(ns)
    assert ch.deleted == []
    assert any("set is buried but a board did not render" in ln for ln in ns["_log"])
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 2
    # It re-anchors on the next tick, once every board renders again.
    ns["_api"].payloads["/ffa/leaderboard"] = _payloads()["/ffa/leaderboard"]
    ns["_log"].clear()
    _tick(ns)
    assert ch.titles()[-3:] == [T_1V1, T_2V2, T_FFA]
    assert sum(1 for ln in ns["_log"] if "not at the channel bottom" in ln) == 1


def _compose_bot_env():
    """The bot service's `environment:` block, as {KEY: raw value}."""
    import io as _io
    import re as _re
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    comp = _io.open(p, encoding="utf-8", newline="").read()
    blk = comp[comp.index("\n  bot:"):]
    blk = blk[:blk.index("\n    volumes:")]
    return dict(_re.findall(r"^      ([A-Z_0-9]+):\s*(.+?)\s*$", blk, _re.M))


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


# Keys discord_bot.py reads that compose does NOT pass into the container.
# This is a RECORDED GAP, not an approval: each is a setting that cannot be
# changed from .env on a standard deployment, and none of them has been
# checked to see whether its compiled default is the right one in production.
# They are listed so the set cannot grow silently -- the same defect has now
# been found three times here (CHAT_CHANNELS "wave-2 find 22", the Twitch trio
# "D1 F12", and LEADERBOARD_BOARDS), which makes it a class and not an
# incident. Removing a name from this list means compose now passes it.
_KNOWN_UNPASSED = {
    "ADMIN_CHANNEL", "BOT_GEN", "BUG_REPORTS_CHANNEL", "DISCORD_PRESENCE_INTENT",
    "GAMBLER_ROLE", "GAMBLER_SIGNUP_CHANNEL", "GITHUB_RELEASES_REPO",
    "LEADERBOARD_ACTIVE_DAYS", "LFP_ROLE", "LIVE_BETS_CHANNEL",
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


def test_a_failed_repost_send_leaves_the_board_absent_for_one_tick_never_twice(ns):
    """Round 4, finding 21, and what its order costs. The repost used to post
    each replacement before deleting what it replaced, so no send failure
    could take a board off the channel (#140) -- and a delete failure left two
    live copies of it. A replacement is now posted only once its old message
    is proven gone, so a send that fails right after that delete leaves the
    board absent for one tick, never on the channel twice. The next tick's
    complete walk finds no copy of it, posts it, and puts the set back in
    order: the gap is one tick long, not a new steady state."""
    _tick(ns)
    ch = ns["_ch"]
    ch.post_from_someone_else()                    # bury the set -> next tick reposts
    ch.send_fails_for_titles = {T_2V2}             # 2v2's replacement will not go out
    ns["_log"].clear()
    _tick(ns)
    titles = _board_titles(ch)
    assert sorted(titles) == sorted([T_1V1, T_FFA]), titles
    assert any("2v2: repost failed" in ln and "absent until the next tick" in ln
               for ln in ns["_log"]), ns["_log"]
    assert "2v2" not in ns["_lb_message_ids"][CID]
    ch.send_fails_for_titles = set()
    ns["_log"].clear()
    _tick(ns)
    assert _board_titles(ch) == [T_1V1, T_2V2, T_FFA], ch.titles()
    assert ch.titles()[-3:] == [T_1V1, T_2V2, T_FFA]


def test_the_second_copy_detector_can_fail(ns):
    """Negative control (#391) for the never-twice assertions in this file:
    a second live copy of a board -- what a replacement posted before its old
    message was proven gone used to leave -- must fail them."""
    _tick(ns)
    ch = ns["_ch"]
    _run(ch.send(embeds=[_Embed(title=T_2V2, description="a second copy")], view=None))
    titles = _board_titles(ch)
    assert titles.count(T_2V2) == 2
    assert sorted(titles) != sorted([T_1V1, T_2V2, T_FFA])


def test_a_failed_repost_delete_keeps_the_board_and_edits_it_in_place(ns):
    """Round 4, finding 21. The repost used to post the replacement and then
    try the delete, so a delete that failed left the board on the channel
    twice. Nothing replaces a board now until its old message is proven gone:
    when the delete fails, the old message stays this board's message, is
    edited where it is, and is the only copy.

    MUTATION: the old order (post, then delete). Must fail."""
    _tick(ns)
    ch = ns["_ch"]
    old_2v2 = ns["_lb_message_ids"][CID]["2v2"]
    ch.post_from_someone_else()
    ch.delete_fails = {old_2v2}
    ns["_log"].clear()
    _tick(ns)
    titles = _board_titles(ch)
    assert titles.count(T_2V2) == 1, titles
    assert sorted(titles) == sorted([T_1V1, T_2V2, T_FFA]), titles
    assert ns["_lb_message_ids"][CID]["2v2"] == old_2v2
    assert len(next(m for m in ch.messages if m.id == old_2v2).edits) == 1
    assert any("2v2: old message mid=%d not deleted" % old_2v2 in ln and "edited in place" in ln
               for ln in ns["_log"]), ns["_log"]


def test_a_failed_repost_delete_is_retried_until_the_board_moves(ns):
    """Round 3 finding 12, as round 4's order meets it. The old 2v2 message
    will not delete, so the set cannot reach the bottom: every tick retries
    the move, and while the delete keeps failing the board stays one copy,
    edited in place. Once the delete goes through the set is at the bottom
    in order, the next tick edits all three, and a channel with nothing owed
    is not swept again.

    MUTATION: the old order (post, then delete). Must fail."""
    _tick(ns)
    ch = ns["_ch"]
    old_2v2 = ns["_lb_message_ids"][CID]["2v2"]
    ch.post_from_someone_else()
    ch.delete_fails = {old_2v2}
    _tick(ns)                                   # 1v1 and FFA move; 2v2 stays, edited
    assert _board_titles(ch).count(T_2V2) == 1, ch.titles()
    ns["_log"].clear()
    _tick(ns)                                   # still refused: the move is retried
    assert any("2v2: old message mid=%d not deleted" % old_2v2 in ln for ln in ns["_log"]), ns["_log"]
    assert _board_titles(ch).count(T_2V2) == 1, ch.titles()
    ch.delete_fails = set()
    ns["_log"].clear()
    _tick(ns)                                   # goes through: the set is at the bottom
    assert old_2v2 in ch.deleted
    assert ch.titles() == [None, T_1V1, T_2V2, T_FFA], ch.titles()
    ns["_log"].clear()
    _tick(ns)
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 3
    assert CID in ns["_lb_swept"]
    # ...and a clean channel is not swept again on every tick.
    calls = []
    real = ns["_adopt_board_messages"]

    async def counting(*a, **kw):
        calls.append(1)
        return await real(*a, **kw)
    ns["_adopt_board_messages"] = counting
    _tick(ns)
    assert calls == [], "a channel with nothing owed was swept again"


def test_a_restart_whose_rescan_fails_posts_nothing_it_cannot_prove_absent(ns):
    """Round 3 finding 15, as round 4's finding 21 meets it. After a restart
    the id map is empty and the walk is what finds the set already in the
    channel. When that history read fails, a fresh set used to be posted
    beside the old one. Nothing is posted now without a complete walk: the
    tick leaves the channel as it is, the sweep stays owed, and the next
    tick's walk adopts the old set and edits it in place -- one set
    throughout, nothing deleted.

    MUTATION: post a board with no message on record after a failed walk.
    Must fail."""
    _tick(ns)
    ch = ns["_ch"]
    old = dict(ns["_lb_message_ids"][CID])
    ns["_lb_message_ids"].clear()               # the process restarts: both maps are
    ns["_lb_swept"].clear()                     # process memory
    ch.history_raises = True
    ns["_log"].clear()
    _tick(ns)
    assert any("rescan failed" in ln for ln in ns["_log"]), ns["_log"]
    assert _board_titles(ch) == [T_1V1, T_2V2, T_FFA], ch.titles()
    assert len(ch.sent) == 3 and ch.deleted == []
    assert ns["_lb_message_ids"][CID] == {}
    assert CID not in ns["_lb_swept"]
    ch.history_raises = False
    ns["_log"].clear()
    _tick(ns)
    assert ns["_lb_message_ids"][CID] == old
    assert ch.deleted == [] and len(ch.sent) == 3
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 3
    assert CID in ns["_lb_swept"]


def test_a_board_dropped_from_the_list_is_retired_on_restart(ns):
    """Round 3 finding 13. LEADERBOARD_BOARDS goes from 1v1,2v2,ffa to
    1v1,2v2 and the bot restarts. The FFA board's title matched nothing in the
    sweep, so it was never adopted and never deleted: the channel kept a board
    the list no longer names, for good. The restart's sweep now retires it --
    only it, and only ours -- and the two named boards are adopted and edited
    in place.

    MUTATION: an empty retire map, or one that also holds the named boards.
    Must fail."""
    ch = ns["_ch"]
    theirs = _run(ch.send(embeds=[_Embed(title=T_FFA, description="not ours")], view=None))
    theirs.author = "someone-else"
    note = _run(ch.send(embeds=[_Embed(title="Weekly recap", description="ours, no board")], view=None))
    _tick(ns)
    old = dict(ns["_lb_message_ids"][CID])
    ns["LEADERBOARD_BOARDS_RAW"] = "1v1,2v2"        # the list changes; the bot restarts
    ns["_lb_message_ids"].clear()
    ns["_lb_swept"].clear()
    ns["_log"].clear()
    _tick(ns)
    assert ch.deleted == [old["ffa"]], (ch.deleted, old)
    assert ch.titles() == [T_FFA, "Weekly recap", T_1V1, T_2V2], ch.titles()
    assert theirs in ch.messages and note in ch.messages
    assert ns["_lb_message_ids"][CID] == {"1v1": old["1v1"], "2v2": old["2v2"]}
    assert any("retired 1 board message(s) not in LEADERBOARD_BOARDS" in ln for ln in ns["_log"]), ns["_log"]
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 2
    assert CID in ns["_lb_swept"]


def test_an_emptied_list_retires_every_board_and_retries_a_refused_one(ns):
    """Round 3 finding 13, the empty list. With LEADERBOARD_BOARDS emptied,
    publish_boards returned before it touched the channel, so every board
    stayed. The sweep now runs there too and retires every board of ours; it
    is owed until it completes, so a refused delete is retried on the next
    tick, and a completed sweep is not run again.

    MUTATION: no sweep on the empty list, or a refused retire marked
    complete. Must fail."""
    _tick(ns)
    ch = ns["_ch"]
    old = dict(ns["_lb_message_ids"][CID])
    ns["LEADERBOARD_BOARDS_RAW"] = ""               # emptied; the bot restarts
    ns["_lb_message_ids"].clear()
    ns["_lb_swept"].clear()
    ch.delete_fails = {old["2v2"]}
    ns["_log"].clear()
    _tick(ns)
    assert sorted(ch.deleted) == sorted([old["1v1"], old["ffa"]]), (ch.deleted, old)
    assert any("couldn't retire 2v2 board mid=%d" % old["2v2"] in ln for ln in ns["_log"]), ns["_log"]
    assert any("LEADERBOARD_BOARDS is empty" in ln for ln in ns["_log"])
    assert CID not in ns["_lb_swept"]
    ch.delete_fails = set()
    ns["_log"].clear()
    _tick(ns)                                       # retried: the refused one goes too
    assert ch.titles() == [], ch.titles()
    assert CID in ns["_lb_swept"]
    calls = []
    real = ns["_adopt_board_messages"]

    async def counting(*a, **kw):
        calls.append(1)
        return await real(*a, **kw)
    ns["_adopt_board_messages"] = counting
    _tick(ns)
    assert calls == [], "a completed sweep ran again"


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


@pytest.mark.parametrize("boards_raw", ["1v1", "1v1,2v2,ffa"])
def test_a_transient_edit_failure_retries_the_edit_and_never_posts_a_second_copy(boards_raw):
    """Round 4, finding 21, the round-3 report's scenario. A transient fetch
    or edit failure (a 429 here) used to drop the board's id and post a fresh
    board while the old message was still live. With LEADERBOARD_BOARDS=1v1
    the fresh singleton sat at the bottom, the channel read as anchored, no
    sweep ran again, and the old board stayed for good. A failure that does
    not prove the message gone now leaves the board as it is, and the next
    tick edits the same message; however many ticks follow, one copy.

    MUTATION: the edit failure posting a fresh message again. Must fail."""
    n2 = _fresh(boards_raw=boards_raw)
    _tick(n2)
    ch = n2["_ch"]
    ids = dict(n2["_lb_message_ids"][CID])
    first = ids["1v1"]
    ch.fetch_fails_once.add(first)                       # e.g. a 429 on that one message
    n2["_log"].clear()
    _tick(n2)
    assert any(f"1v1: edit of mid={first} failed" in ln and "retried next tick" in ln
               for ln in n2["_log"]), n2["_log"]
    assert not any("posted fresh board message" in ln for ln in n2["_log"]), n2["_log"]
    assert n2["_lb_message_ids"][CID] == ids
    n2["_log"].clear()
    _tick(n2)
    assert any(f"1v1: edited board mid={first}" in ln for ln in n2["_log"]), n2["_log"]
    for _ in range(3):
        _tick(n2)
    assert _board_titles(ch).count(T_1V1) == 1, ch.titles()
    assert ch.deleted == [] and n2["_lb_message_ids"][CID] == ids


def test_a_board_deleted_by_hand_is_posted_again_once(ns):
    """Round 4, finding 21: a 404 is proof. A moderator deletes the 2v2
    board. On the move path the old message's delete answers 404, which is
    as good as a delete; on the edit path (here the tail read fails, so the
    set is edited in place) the edit answers 404 and the board is posted
    fresh at once. Either way it ends as one copy, and the set in order."""
    _tick(ns)
    ch = ns["_ch"]
    old_2v2 = ns["_lb_message_ids"][CID]["2v2"]
    ch.messages = [m for m in ch.messages if m.id != old_2v2]      # deleted by hand
    ch.history_raises = True                                        # the tail read fails
    ns["_log"].clear()
    _tick(ns)
    assert any("2v2: board mid=%d is gone (404)" % old_2v2 in ln for ln in ns["_log"]), ns["_log"]
    assert _board_titles(ch) == [T_1V1, T_FFA, T_2V2], ch.titles()
    ch.history_raises = False
    ns["_log"].clear()
    _tick(ns)
    assert ch.titles() == [T_1V1, T_2V2, T_FFA], ch.titles()
    # The move path: deleted by hand again, with the tail read working.
    gone = ns["_lb_message_ids"][CID]["2v2"]
    ch.messages = [m for m in ch.messages if m.id != gone]
    ns["_log"].clear()
    _tick(ns)
    assert ch.titles() == [T_1V1, T_2V2, T_FFA], ch.titles()
    assert gone not in ch.deleted                        # the 404 was the proof, not a delete


def test_a_walk_that_fails_part_way_posts_nothing_it_did_not_reach(ns):
    """Round 4, findings 15 and 21: a partial walk proves nothing absent. The
    set sits under 120 messages of chat and the process restarts; the walk
    reads 60 messages and fails. Nothing is posted and nothing deleted, the
    sweep stays owed, and the next tick's complete walk finds the set and
    moves it -- one set throughout.

    MUTATION: post a board with no message on record after a failed walk.
    Must fail."""
    _tick(ns)
    ch = ns["_ch"]
    _bury(ch)
    ns["_lb_message_ids"].clear()               # the process restarts
    ns["_lb_swept"].clear()
    ch.history_fails_after = 60
    ns["_log"].clear()
    _tick(ns)
    assert any("rescan failed (history page failed)" in ln for ln in ns["_log"]), ns["_log"]
    assert _board_titles(ch) == [T_1V1, T_2V2, T_FFA], ch.titles()
    assert len(ch.sent) == 3 and ch.deleted == []
    assert CID not in ns["_lb_swept"]
    ch.history_fails_after = None
    _tick(ns)
    assert _board_titles(ch) == [T_1V1, T_2V2, T_FFA], ch.titles()
    assert ch.titles()[-3:] == [T_1V1, T_2V2, T_FFA]
    assert CID in ns["_lb_swept"]


# -- round 4: the sweep reads the whole channel (findings 12, 13, 15) ----------

_DEEP = 120      # messages of chat: deeper than the 50-message window the sweep used to read


def _bury(ch, n=_DEEP):
    for _ in range(n):
        ch.post_from_someone_else()


def _post_set(ns, description):
    """A set of our board messages, as an earlier process left it."""
    ch = ns["_ch"]
    return [_run(ch.send(embeds=[_Embed(title=b["title"], description=description)], view=None)).id
            for b in ns["_enabled_boards"]()]


def _board_titles(ch):
    return [t for t in ch.titles() if t is not None]


def test_a_set_buried_deeper_than_any_window_is_found_on_restart(ns):
    """Round 4, findings 12, 13 and 15, the depth half. The sweep read the
    newest 50 messages, so a set buried under more chat than that was never
    adopted: a restart posted a second set below it, and the first stayed for
    good. The walk now reads the whole channel. A restart finds the set under
    120 messages of chat and moves it to the bottom -- one set, never two --
    and nobody else's message is touched.

    MUTATION: the walk back to the newest 50 messages. Must fail."""
    _tick(ns)
    ch = ns["_ch"]
    old = dict(ns["_lb_message_ids"][CID])
    _bury(ch)
    ns["_lb_message_ids"].clear()               # the process restarts
    ns["_lb_swept"].clear()
    _tick(ns)
    assert _board_titles(ch) == [T_1V1, T_2V2, T_FFA], _board_titles(ch)
    assert ch.titles()[-3:] == [T_1V1, T_2V2, T_FFA]
    assert sorted(ch.deleted) == sorted(old.values()), (ch.deleted, old)
    assert len(ch.messages) == _DEEP + 3
    assert CID in ns["_lb_swept"]


def test_a_duplicate_set_buried_deep_is_swept_on_restart(ns):
    """Round 4, finding 15's depth. An older set of ours sits under 120
    messages of chat and the current set is at the bottom. The restart's walk
    keeps the newest copy of each board and deletes the old set, wherever it
    is; the current set is adopted and edited in place.

    MUTATION: the walk back to the newest 50 messages. Must fail."""
    ch = ns["_ch"]
    stale = _post_set(ns, "stale")
    _bury(ch)
    current = _post_set(ns, "current")
    _tick(ns)                                   # a fresh process: nothing tracked, a sweep owed
    assert sorted(ch.deleted) == sorted(stale), (ch.deleted, stale)
    assert _board_titles(ch) == [T_1V1, T_2V2, T_FFA], _board_titles(ch)
    assert sorted(ns["_lb_message_ids"][CID].values()) == sorted(current)
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 3
    assert CID in ns["_lb_swept"]


def test_a_retired_board_buried_deep_is_still_retired(ns):
    """Round 4, finding 13's depth. The list drops FFA and the bot restarts
    while the FFA board sits under 120 messages of chat: the walk still finds
    it and retires it, and only it.

    MUTATION: the walk back to the newest 50 messages. Must fail."""
    _tick(ns)
    ch = ns["_ch"]
    old = dict(ns["_lb_message_ids"][CID])
    _bury(ch)
    ns["LEADERBOARD_BOARDS_RAW"] = "1v1,2v2"        # the list changes; the bot restarts
    ns["_lb_message_ids"].clear()
    ns["_lb_swept"].clear()
    _tick(ns)
    assert old["ffa"] in ch.deleted, (ch.deleted, old)
    assert _board_titles(ch) == [T_1V1, T_2V2], _board_titles(ch)
    assert CID in ns["_lb_swept"]


# -- round 4: the tournament board runs the same mechanism (finding 22) --------

TB_FUNC = {"_delete_board_message", "_own_embed_messages", "_adopt_tournament_board",
           "_publish_tournament_board", "publish_tournament_board"}
TB_ASSIGN = {"_tournament_board_ids", "_tb_swept"}
T_SYNC = chr(0x1F3C6) + " Sync Tournament"       # the titles _build_tournament_board_embed gives
T_ASYNC = chr(0x1F300) + " Async Tournament"


async def _tb_no_tally(t):
    return None


def _tb_fresh():
    """A fresh bot process for the tournament board: its id map and its
    owed-sweep set start empty, as at every start. The board's two embeds
    come from a stub; what is under test is where the message goes."""
    out = []
    ch = _Channel(CID, "scr-bot")
    ns = {"discord": FAKE_DISCORD, "bot": _Bot(ch), "SCR_TOURNAMENTS_CHANNEL": CID,
          "_watch_cache": {"tournaments": [{"kind": "sync", "status": "voting"}]},
          "http_session": None, "API_SECRET_KEY": "", "API_BASE_URL": "", "aiohttp": None,
          "_build_tournament_board_embed": lambda t, kind, tally=None: _Embed(
              title=T_SYNC if kind == "sync" else T_ASYNC, description="status"),
          # The sync board's start-rule tally (board row 32) is a stub too.
          "_tsync_tally_for": _tb_no_tally,
          "print": lambda *a, **k: out.append(" ".join(str(x) for x in a))}
    exec(compile(ast.Module(body=_lift(TB_FUNC, TB_ASSIGN, set()), type_ignores=[]), SRC, "exec"), ns)
    ns["_log"], ns["_ch"] = out, ch
    return ns


def _tb_tick(ns):
    _run(ns["publish_tournament_board"]())       # the loop body, with its own guard (#129)


def _tb_restart(ns):
    """The process restarts: its memory is gone, the channel is not."""
    ns["_tournament_board_ids"].clear()
    ns["_tb_swept"].clear()


def _tb_copies(ch):
    return [m.id for m in ch.messages
            if m.author == ch.bot_user and m.embeds and (m.embeds[0].title or "").endswith("Tournament")]


def test_the_tournament_board_is_posted_once_and_then_edited_in_place():
    """Round 4, finding 22, the steady state. The first tick walks the empty
    channel and posts the board; later ticks edit that message, and once the
    sweep has completed they do not walk the channel again."""
    ns = _tb_fresh()
    ch = ns["_ch"]
    _tb_tick(ns)
    mid = ns["_tournament_board_ids"][CID]
    assert _tb_copies(ch) == [mid] and ch.messages[-1].embeds[0].title == T_SYNC
    assert CID in ns["_tb_swept"] and ch.history_reads == 1
    ns["_log"].clear()
    _tb_tick(ns)
    _tb_tick(ns)
    assert sum(1 for ln in ns["_log"] if f"edited board mid={mid}" in ln) == 2, ns["_log"]
    assert _tb_copies(ch) == [mid] and ch.deleted == [] and ch.history_reads == 1


def test_a_buried_tournament_board_whose_delete_fails_stays_the_only_copy_until_it_moves():
    """Round 4, finding 22, the round-3 report's first scenario. Chat buries
    the board and its delete fails (a revoked Manage Messages, a 5xx). The
    publisher used to swallow that, post a fresh board at the bottom and
    remember only the fresh one: two copies, and the old one was never
    looked at again. Now nothing is posted while the old message may be
    live -- it is edited where it is -- and the move is retried every tick
    until the delete goes through. One copy at every tick.

    MUTATION: post the replacement first and delete after (the old order).
    Must fail."""
    ns = _tb_fresh()
    ch = ns["_ch"]
    _tb_tick(ns)
    mid = ns["_tournament_board_ids"][CID]
    ch.post_from_someone_else()
    ch.delete_fails.add(mid)
    for _ in range(3):
        ns["_log"].clear()
        _tb_tick(ns)
        assert _tb_copies(ch) == [mid], ch.titles()
        assert any(f"buried board mid={mid} not deleted" in ln for ln in ns["_log"]), ns["_log"]
        assert any(f"edited board mid={mid}" in ln for ln in ns["_log"]), ns["_log"]
    assert len(ch.sent) == 1
    ch.delete_fails.clear()
    _tb_tick(ns)
    new = ns["_tournament_board_ids"][CID]
    assert mid in ch.deleted and _tb_copies(ch) == [new] and ch.messages[-1].id == new


def test_a_duplicate_tournament_board_whose_delete_fails_is_deleted_on_a_later_tick():
    """Round 4, finding 22, the round-3 report's second scenario. A restart
    finds two copies of the board, and the older copy's delete fails. The
    rescan used to log that and forget it. Now the sweep stays owed and runs
    again on every tick until the delete goes through; then the channel
    holds one board, and steady ticks stop walking it.

    MUTATION: a failed duplicate delete not leaving the sweep owed, and the
    owed sweep not run while a board is on record. Each must fail."""
    ns = _tb_fresh()
    ch = ns["_ch"]
    older = _run(ch.send(embeds=[_Embed(title=T_SYNC)])).id
    ch.post_from_someone_else()
    newer = _run(ch.send(embeds=[_Embed(title=T_SYNC)])).id
    ch.delete_fails.add(older)
    _tb_tick(ns)                                  # a fresh process: nothing on record, a sweep owed
    assert ns["_tournament_board_ids"][CID] == newer
    assert CID not in ns["_tb_swept"]
    assert any(f"couldn't delete duplicate board mid={older}" in ln for ln in ns["_log"]), ns["_log"]
    _tb_tick(ns)
    assert older in [m.id for m in ch.messages]   # still refused, still owed
    ch.delete_fails.clear()
    _tb_tick(ns)
    assert older in ch.deleted and _tb_copies(ch) == [newer]
    assert CID in ns["_tb_swept"]
    reads = ch.history_reads
    _tb_tick(ns)
    assert ch.history_reads == reads and _tb_copies(ch) == [newer]


def test_a_tournament_board_buried_deeper_than_the_old_window_is_moved_not_duplicated():
    """Round 4, finding 22 (finding 12's depth, in this publisher's own
    copy). The board sits under 120 messages of chat and the bot restarts.
    The rescan read the newest 50 messages, missed it and posted a second
    board. The walk now reads the whole channel: the restart adopts the
    board and moves it to the bottom -- one copy.

    MUTATION: the walk back to the newest 50 messages. Must fail."""
    ns = _tb_fresh()
    ch = ns["_ch"]
    _tb_tick(ns)
    old = ns["_tournament_board_ids"][CID]
    _bury(ch)
    _tb_restart(ns)
    _tb_tick(ns)
    new = ns["_tournament_board_ids"][CID]
    assert ch.deleted == [old] and _tb_copies(ch) == [new]
    assert ch.messages[-1].id == new and len(ch.messages) == _DEEP + 1
    assert CID in ns["_tb_swept"]


def test_a_tournament_board_walk_that_fails_part_way_posts_nothing():
    """Round 4, finding 22 with finding 21's rule: a partial walk proves no
    copy absent. The board sits under 120 messages of chat and the bot
    restarts; the walk reads 60 messages and fails. Nothing is posted, the
    sweep stays owed, and the next tick's complete walk finds the board and
    moves it -- one copy throughout.

    MUTATION: post with no message on record after a failed walk. Must
    fail."""
    ns = _tb_fresh()
    ch = ns["_ch"]
    _tb_tick(ns)
    old = ns["_tournament_board_ids"][CID]
    _bury(ch)
    _tb_restart(ns)
    ch.history_fails_after = 60
    ns["_log"].clear()
    _tb_tick(ns)
    assert any("rescan failed (history page failed)" in ln for ln in ns["_log"]), ns["_log"]
    assert any("no board on record and no complete walk" in ln for ln in ns["_log"]), ns["_log"]
    assert _tb_copies(ch) == [old] and len(ch.sent) == 1
    assert CID not in ns["_tb_swept"]
    ch.history_fails_after = None
    _tb_tick(ns)
    new = ns["_tournament_board_ids"][CID]
    assert _tb_copies(ch) == [new] and ch.messages[-1].id == new
    assert CID in ns["_tb_swept"]


def test_a_transient_failure_leaves_the_tournament_board_and_retries_it():
    """Round 4, finding 22 with finding 21's rule. A fetch that fails for any
    reason but a 404 (a 429 here) proves nothing gone, so the board is left
    as it is and the next tick edits the same message. One copy throughout,
    and nothing deleted.

    MUTATION: a failed fetch dropping the id and posting fresh. Must fail."""
    ns = _tb_fresh()
    ch = ns["_ch"]
    _tb_tick(ns)
    mid = ns["_tournament_board_ids"][CID]
    ch.fetch_fails_once.add(mid)
    ns["_log"].clear()
    _tb_tick(ns)
    assert any(f"fetch of mid={mid} failed" in ln and "retried next tick" in ln
               for ln in ns["_log"]), ns["_log"]
    _tb_tick(ns)
    assert any(f"edited board mid={mid}" in ln for ln in ns["_log"]), ns["_log"]
    assert _tb_copies(ch) == [mid] and ch.deleted == [] and len(ch.sent) == 1


def test_a_tournament_board_deleted_by_hand_is_posted_again_once():
    """Round 4, finding 22 with finding 21's rule: a 404 is proof. A
    moderator deletes the board; the next tick's fetch answers 404 and the
    board is posted fresh at once -- one copy, and no delete was needed.

    MUTATION: a 404 on the fetch not counted as proof. Must fail."""
    ns = _tb_fresh()
    ch = ns["_ch"]
    _tb_tick(ns)
    gone = ns["_tournament_board_ids"][CID]
    ch.messages = [m for m in ch.messages if m.id != gone]     # deleted by hand
    ns["_log"].clear()
    _tb_tick(ns)
    assert any(f"board mid={gone} is gone (404)" in ln for ln in ns["_log"]), ns["_log"]
    new = ns["_tournament_board_ids"][CID]
    assert new != gone and _tb_copies(ch) == [new] and gone not in ch.deleted


def test_a_failed_tournament_repost_leaves_the_board_absent_for_one_tick_never_twice():
    """Round 4, finding 22 with finding 21's order. The board is buried; its
    delete goes through and the replacement's send fails. The board is
    absent until the next tick, whose complete walk finds no copy and posts
    one: the one price of deleting first, and never two copies.

    MUTATION: post the replacement first and delete after. Must fail."""
    ns = _tb_fresh()
    ch = ns["_ch"]
    _tb_tick(ns)
    old = ns["_tournament_board_ids"][CID]
    ch.post_from_someone_else()
    ch.send_fails_for_titles.add(T_SYNC)
    ns["_log"].clear()
    _tb_tick(ns)
    assert old in ch.deleted and _tb_copies(ch) == []
    assert any("repost failed" in ln for ln in ns["_log"]), ns["_log"]
    assert CID not in ns["_tournament_board_ids"]
    ch.send_fails_for_titles.clear()
    _tb_tick(ns)
    new = ns["_tournament_board_ids"][CID]
    assert _tb_copies(ch) == [new] and ch.messages[-1].id == new


def test_the_tournament_sweep_touches_only_our_board_copies():
    """Round 4, finding 22: the walk now reads the whole channel, so what it
    matches matters more than it did at 50 messages. A board copy is a
    message of this bot's whose first embed's title ends with "Tournament":
    another member's message titled the same, and an embed of ours titled
    otherwise, are never deleted."""
    ns = _tb_fresh()
    ch = ns["_ch"]
    theirs = ch.post_from_someone_else()
    theirs.embeds = [_Embed(title=T_SYNC)]
    other = _run(ch.send(embeds=[_Embed(title="Tournament FFA Complete - 5 players")])).id
    _tb_tick(ns)
    _tb_tick(ns)
    assert ch.deleted == []
    assert theirs in ch.messages and other in [m.id for m in ch.messages]
    assert _tb_copies(ch) == [ns["_tournament_board_ids"][CID]]


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
    n2["_api"].payloads["/leaderboard?limit=1&min_matches=1&include_inactive=true"] = {
        "entries": _rows_1v1(1), "total_players": 137}          # 120 active, 137 in total
    _tick(n2)
    assert [c for c in n2["_api"].calls if "include_inactive=true" in c] == [
        "/leaderboard?limit=1&min_matches=1&include_inactive=true"]
    assert "17 inactive hidden (90 days)" in n2["_ch"].messages[0].embeds[-1].footer
    # 1v2's total_players is the page size (main.py's own KNOWN NIT), so it is
    # probed for no difference and its noun says "listed" instead.
    ovt = n2["_ch"].messages[1]
    assert "inactive hidden" not in ovt.embeds[-1].footer
    assert "1v2 players listed" in ovt.embeds[-1].footer


def test_a_failed_probe_never_blocks_the_board():
    n2 = _fresh(boards_raw="1v1")
    n2["_api"].payloads["/leaderboard?limit=1&min_matches=1&include_inactive=true"] = \
        RuntimeError("probe boom")
    _tick(n2)
    assert n2["_ch"].titles() == [T_1V1]
    assert any("inactive count fetch failed" in ln for ln in n2["_log"])
    assert "inactive hidden" not in n2["_ch"].messages[0].embeds[-1].footer


# -- round 4, finding 24: an empty board is an answer, not a failed read -------

ONE_SHOT_FUNC = {"rank_emoji", "get_rank_name", "_escape_md", "_lb_line", "_split_lb_descriptions",
                 "get_lb_position", "cmd_leaderboard", "_faq_top_player"}
ME = "76561190000000042"
TOP3 = "/leaderboard?limit=3&min_matches=1"
ACTIVE = "/leaderboard?limit=200&min_matches=1"
EVERYONE = "/leaderboard?limit=500&min_matches=1&include_inactive=true"
PAGE1 = "/leaderboard?limit=50&offset=0&min_matches=1"


class _Ctx:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, embeds=None, embed=None):
        self.sent.append((content, embeds if embeds is not None else ([embed] if embed else [])))


def _one_shot(payloads):
    """The four one-shot leaderboard readers -- the FAQ's top player, the
    profile footer's position (two reads) and /lb -- against _Api: a path
    mapped to None is a failed read (api_get returns None for a non-200 or a
    transport error)."""
    api = _Api(payloads)
    ns = {"discord": FAKE_DISCORD, "re": re, "api_get": api.get, "LB_ACTIVE_DAYS": 90}
    body = _lift(want_func=ONE_SHOT_FUNC, want_assign={"RANK_ROLES"}, want_class=set())
    exec(compile(ast.Module(body=body, type_ignores=[]), SRC, "exec"), ns)
    ns["_api"] = api
    return ns


def _row(steam_id, rank, **kw):
    return dict({"rank": rank, "steam_id": steam_id, "display_name": "Someone", "rating": 1500,
                 "wins": 3, "losses": 2}, **kw)


def test_an_empty_active_board_is_an_answer_on_the_profile_footer():
    """Round 4, finding 24. The profile footer's position read took an empty
    list for a failed read: "?", and no second look. The empty active board is
    an answer now, and the lookup goes on to the full list as it does for any
    player who is not on the active one.

    MUTATION: the first read's empty list taken for a failure again. Must fail."""
    ns = _one_shot({ACTIVE: {"entries": [], "total_players": 0},
                    EVERYONE: {"entries": [_row(ME, 4, inactive=True)], "total_players": 1}})
    assert _run(ns["get_lb_position"](ME)) == "4 (inactive 90d+)"
    assert ns["_api"].calls == [ACTIVE, EVERYONE]
    ns = _one_shot({ACTIVE: {"entries": [], "total_players": 0},
                    EVERYONE: {"entries": [], "total_players": 0}})
    assert _run(ns["get_lb_position"](ME)) == "Unranked"


def test_a_failed_read_is_a_question_mark_on_the_profile_footer_never_unranked():
    """A read that fails gives "?" -- unknown -- at either of the two reads.
    The second one used to fall through to "Unranked", which says the player
    is on neither list, from a list that was never read.

    MUTATION: the second read's failure taken for an empty list again. Must fail."""
    ns = _one_shot({ACTIVE: None})
    assert _run(ns["get_lb_position"](ME)) == "?"
    assert ns["_api"].calls == [ACTIVE]
    ns = _one_shot({ACTIVE: {"entries": [_row("76561190000000001", 1)], "total_players": 1},
                    EVERYONE: None})
    assert _run(ns["get_lb_position"](ME)) == "?"
    ns = _one_shot({ACTIVE: {"entries": [_row(ME, 7)], "total_players": 9}})
    assert _run(ns["get_lb_position"](ME)) == "7"


def test_lb_shows_an_honest_empty_board_and_says_it_failed_only_when_the_read_fails():
    """/lb on a board nobody is on (nobody meets the active or minimum-match
    filter) shows the empty board, not a failed read's reply; a failed read
    says it could not reach the leaderboard.

    MUTATION: the empty list taken for a failure again. Must fail."""
    ns = _one_shot({PAGE1: {"entries": [], "total_players": 0}})
    ctx = _Ctx()
    _run(ns["cmd_leaderboard"](ctx))
    [(content, embeds)] = ctx.sent
    assert content is None and len(embeds) == 1
    assert embeds[0].description == "(no players)"
    assert "Page 1/1" in embeds[0].footer and "0 ranked players" in embeds[0].footer
    ns = _one_shot({PAGE1: None})
    ctx = _Ctx()
    _run(ns["cmd_leaderboard"](ctx))
    [(content, embeds)] = ctx.sent
    assert "Couldn't reach the leaderboard" in content and embeds == []


def test_a_page_past_the_last_one_says_which_page_is_the_last():
    """/lb 5 on a two-page board: an answer too, and it says where the board
    ends rather than showing an empty page as if the board were empty.

    MUTATION: the past-the-end description removed. Must fail."""
    ns = _one_shot({"/leaderboard?limit=50&offset=200&min_matches=1": {"entries": [], "total_players": 80}})
    ctx = _Ctx()
    _run(ns["cmd_leaderboard"](ctx, "5"))
    [(content, embeds)] = ctx.sent
    assert content is None
    assert embeds[0].description == "(no players on page 5; the last page is 2)"


def test_the_faq_top_player_tells_an_empty_board_from_an_unreachable_one():
    """The FAQ's top-player answer said it could not reach the leaderboard
    when the board was only empty.

    MUTATION: the empty list taken for a failure again. Must fail."""
    ns = _one_shot({TOP3: {"entries": [], "total_players": 0}})
    empty = _run(ns["_faq_top_player"](None))
    assert "Nobody is on the ranked leaderboard" in empty and "Couldn't reach" not in empty
    ns = _one_shot({TOP3: None})
    assert "Couldn't reach the leaderboard" in _run(ns["_faq_top_player"](None))
