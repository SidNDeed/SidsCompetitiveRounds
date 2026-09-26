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
             "_enabled_boards", "_render_board", "_adopt_board_messages", "_boards_are_anchored",
             "_repost_board_set", "publish_boards", "publish_lb_loop"}
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


FAKE_DISCORD = types.SimpleNamespace(
    Embed=_Embed, Interaction=object,
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
        self.edits.append(kw)
        self.embeds = kw.get("embeds", self.embeds)
        self.view = kw.get("view", self.view)

    async def delete(self):
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
        raise RuntimeError(f"Unknown Message {mid}")

    def history(self, limit=100):
        if self.history_raises:
            raise RuntimeError("history boom")
        snapshot = list(self.messages)[-limit:][::-1]      # newest first, as Discord answers

        async def gen():
            for m in snapshot:
                yield m
        return gen()

    def titles(self):
        return [(m.embeds[0].title if m.embeds else None) for m in self.messages]


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


def _expected_md(name):
    """The name as a row must show it: cut to 24 characters FIRST, then each
    significant character preceded by one backslash. Written out here, not
    taken from the bot's helper, so the helper does not grade itself."""
    return "".join("\\" + ch if ch in _MD_LITERAL else ch for ch in name[:24])


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
@pytest.mark.parametrize("name", [_MD_NAME, "x" * 23 + "*tail", "y" * 23 + "\\tail"],
                         ids=["every-significant-character", "cut-at-a-star", "cut-at-a-backslash"])
def test_a_display_name_is_literal_inside_every_board_row(ns, renderer, name):
    """A display name went into `**...**` as typed, so a name carrying * _ `
    ~ | could close the bold early, open italics, code or a spoiler, or bleed
    into the next row. All four renderers now escape through ONE helper,
    after the 24-character cut: the two cut cases put a * or a backslash
    exactly at character 24, where escaping first and cutting second strands
    a lone backslash that swallows the closing **. Controls: the escape
    skipped at one renderer reds that renderer's cases only."""
    row = _MD_ROWS[renderer](1)[0]
    row["display_name"] = name
    line = ns[renderer](row, 1)
    assert _bold_segment(line) == _expected_md(name), (renderer, line)


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


def test_a_failed_repost_delete_leaves_a_duplicate_not_a_hole(ns):
    """The other failure direction, which is the price of the fix.

    If the replacement goes out but the old message will not delete, the
    channel carries that board twice. That is the deliberate trade: a stale
    duplicate above the set is recoverable by the re-adopt sweep, an absent
    board is not recoverable until the next tick. We track the NEW id either
    way, so the next tick edits the right message.
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
    assert any("not deleted" in ln for ln in ns["_log"])


def test_a_failed_repost_delete_is_swept_on_a_later_tick(ns):
    """Round 3 finding 12. The replacement is posted and anchored and the old
    message will not delete; the log promised that the next tick's re-adopt
    sweeps it, but the sweep ran only while a board id was missing, so the
    duplicate stayed for good. The channel now owes a sweep until one
    completes: retried while the delete keeps failing, done once it goes
    through, and not run again after that.

    MUTATION: drop the owed-sweep trigger, or leave the channel marked swept
    after the failed delete. Must fail."""
    _tick(ns)
    ch = ns["_ch"]
    old_2v2 = ns["_lb_message_ids"][CID]["2v2"]
    ch.post_from_someone_else()
    ch.delete_fails = {old_2v2}
    _tick(ns)                                   # re-anchor; the old 2v2 will not go
    assert [t for t in ch.titles() if t is not None].count(T_2V2) == 2, ch.titles()
    ns["_log"].clear()
    _tick(ns)                                   # still refused: swept again, still owed
    assert any("couldn't delete duplicate 2v2 board mid=%d" % old_2v2 in ln
               for ln in ns["_log"]), ns["_log"]
    assert CID not in ns["_lb_swept"]
    ch.delete_fails = set()
    ns["_log"].clear()
    _tick(ns)                                   # goes through: the duplicate is gone
    assert old_2v2 in ch.deleted
    assert ch.titles() == [None, T_1V1, T_2V2, T_FFA], ch.titles()
    assert CID in ns["_lb_swept"]
    assert sum(1 for ln in ns["_log"] if ": edited board mid=" in ln) == 3
    # ...and a clean channel is not swept again on every tick.
    calls = []
    real = ns["_adopt_board_messages"]

    async def counting(*a, **kw):
        calls.append(1)
        return await real(*a, **kw)
    ns["_adopt_board_messages"] = counting
    _tick(ns)
    assert calls == [], "a channel with nothing owed was swept again"


def test_a_restart_whose_rescan_fails_sweeps_the_old_set_on_a_later_tick(ns):
    """Round 3 finding 15. After a restart the id map is empty and the rescan
    is what finds the set already in the channel. When that history read
    fails, a fresh set is posted and anchored -- and the sweep ran only while
    an id was missing, so the old set stayed above it for good. A failed
    rescan now leaves the sweep owed, and the next tick's sweep keeps the
    newest copy of each board and removes the old set.

    MUTATION: mark the channel swept although the rescan failed, or drop the
    owed-sweep trigger. Must fail."""
    _tick(ns)
    ch = ns["_ch"]
    old = dict(ns["_lb_message_ids"][CID])
    ns["_lb_message_ids"].clear()               # the process restarts: both maps are
    ns["_lb_swept"].clear()                     # process memory
    ch.history_raises = True
    ns["_log"].clear()
    _tick(ns)
    assert any("rescan failed" in ln for ln in ns["_log"]), ns["_log"]
    assert len([t for t in ch.titles() if t is not None]) == 6, ch.titles()
    fresh = dict(ns["_lb_message_ids"][CID])
    assert set(fresh.values()).isdisjoint(old.values())
    ch.history_raises = False
    ns["_log"].clear()
    _tick(ns)
    assert sorted(ch.deleted) == sorted(old.values()), (ch.deleted, old)
    assert ch.titles() == [T_1V1, T_2V2, T_FFA], ch.titles()
    assert ns["_lb_message_ids"][CID] == fresh
    assert CID in ns["_lb_swept"]


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


def test_a_transient_edit_failure_posts_fresh_and_re_anchors_next_tick(ns):
    _tick(ns)
    ch = ns["_ch"]
    old_2v2 = ns["_lb_message_ids"][CID]["2v2"]
    ch.fetch_fails_once.add(old_2v2)                     # e.g. a 429 on that one message
    ns["_log"].clear()
    _tick(ns)
    assert any(f"2v2: edit of mid={old_2v2} failed" in ln for ln in ns["_log"])
    assert any("2v2: posted fresh board message" in ln for ln in ns["_log"])
    assert ns["_lb_message_ids"][CID]["2v2"] != old_2v2
    ns["_log"].clear()
    _tick(ns)                                            # self-heals: order restored, no duplicate
    assert ch.titles() == [T_1V1, T_2V2, T_FFA]
    assert sum(1 for ln in ns["_log"] if "not at the channel bottom" in ln) == 1


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
