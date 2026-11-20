"""The Discord bot shows the server's streak, never a walk of its own (owner
ruling, 16 Nov 2026: a series or game a moderator voided stays out of every
streak a player is shown).

Before this lane the bot walked GET /players/{id}/matches?limit=50 for three
lines: /rank "Current Streak" (ranked games), and the /mystats ranked and
casual tails (games). That list carries voided games and does not mark them
(its answer is frozen for the released client's parser), so a voided game
lengthened or cut the bot's streak. Each line now shows the field the api
computes for the same unit from the same rows, voided rows left out:
current_ranked_game_streak (ranked 1v1 games, non-team rooms) and
current_casual_streak (casual games, non-team rooms).

Each case gives the bot a server answer carrying the server's number (2,
voided rows already left out) and a match list carrying the voided row
unmarked, as the live route does; the line must show the server's number:
  - a voided win inside a run of wins (the list's walk reads 3);
  - a voided loss between wins (the list's walk reads 1);
  - a voided newest row (the list's walk reads -1).

discord_bot.py is not importable in a test process (it builds the bot at
import), so, as in test_discord_name_markdown.py, the commands are lifted out
of its AST and executed against fakes. Synthetic ids only.
"""
import ast
import asyncio
import copy
import os
import types

import pytest

SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "discord_bot.py"))
TREE = ast.parse(open(SRC, encoding="utf-8").read())

ME = "76561190000047711"
SERVER = 2

# newest first, as the matches list answers: (won, voided). The list never
# marks the voided row; `voided` only documents the case.
HISTORIES = {
    "voided_win_inside_a_run": [(True, False), (True, True), (True, False), (False, False)],
    "voided_loss_between_wins": [(True, False), (False, True), (True, False)],
    "voided_newest_row": [(False, True), (True, False), (True, False)],
}


class _Embed:
    def __init__(self, title=None, color=None, **kw):
        self.title, self.fields, self.description = title, [], None

    def set_thumbnail(self, url=None):
        pass

    def add_field(self, name=None, value=None, inline=True):
        self.fields.append((name, value))

    def set_footer(self, text=None, **kw):
        pass


class _Ctx:
    def __init__(self):
        self.author = types.SimpleNamespace(
            id=1, display_name="Tester", display_avatar=types.SimpleNamespace(url="u"))
        self.sent = []

    async def send(self, content=None, embed=None, **kw):
        self.sent.append(embed if embed is not None else content)

    async def defer(self):
        pass


def _lift(api):
    present = {n.name for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    want = {"cmd_rank", "cmd_mystats", "streak_str"}
    # The streak helpers of whichever build is under test (the base had
    # _calc_streak and _current_streak; this lane has _streak_field).
    want |= present & {"_streak_field", "_calc_streak", "_current_streak"}
    picked = []
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in want:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            picked.append(fn)
    assert {p.name for p in picked} == want

    async def api_get(path, *a, **k):
        return api(path)

    async def _noop(*a, **k):
        return None

    async def lb(*a, **k):
        return "1"

    discord = types.SimpleNamespace(
        Embed=_Embed, Member=object,
        Color=types.SimpleNamespace(gold=lambda: 0),
        utils=types.SimpleNamespace(escape_markdown=lambda t: t))
    ns = {"discord": discord, "api_get": api_get, "_maybe_defer": _noop,
          "get_lb_position": lb, "get_rank_name": lambda r: "Gold",
          "rank_emoji": lambda n: "", "_escape_md": lambda t: t,
          "_hit_block_str": lambda s: "", "_top_cards_lines": lambda s, limit=5: []}
    exec(compile(ast.Module(body=picked, type_ignores=[]), SRC, "exec"), ns)
    return ns


def _api(history, ranked):
    stats = {"steam_id": ME, "display_name": "Tester", "rating": 1500.0,
             "rating_deviation": 80.0, "peak_rating": 1500.0, "team_rating": 1500.0,
             "current_ranked_game_streak": SERVER if ranked else 0,
             "current_casual_streak": 0 if ranked else SERVER}
    matches = [{"won": won, "is_ranked": ranked} for won, _v in history]
    team = {"rating": 1500.0, "series_wins": 3, "series_losses": 1, "current_streak": SERVER}

    def answer(path):
        if path.startswith("/players/by-discord/"):
            return {"steam_id": ME}
        if path.startswith("/players/%s/matches" % ME):
            return matches
        if path == "/players/%s" % ME:
            return stats
        if path.startswith("/team/players/%s/team-stats" % ME):
            return team
        raise AssertionError(path)
    return answer


def _fields(cmd, history, ranked):
    ns = _lift(_api(history, ranked))
    ctx = _Ctx()
    asyncio.run(ns[cmd](ctx, None))
    (embed,) = ctx.sent
    return dict(embed.fields)


WANT = "🔥 %dW streak" % SERVER


@pytest.mark.parametrize("case", sorted(HISTORIES))
def test_rank_current_streak_is_the_servers_ranked_game_streak(case):
    fields = _fields("cmd_rank", HISTORIES[case], ranked=True)
    assert fields["📈  Current Streak"] == WANT, fields


@pytest.mark.parametrize("case", sorted(HISTORIES))
def test_mystats_ranked_tail_is_the_servers_ranked_game_streak(case):
    records = _fields("cmd_mystats", HISTORIES[case], ranked=True)["⚔️  Records"]
    (line,) = [ln for ln in records.split("\n") if ln.startswith("Ranked series:")]
    assert line.endswith("  ·  " + WANT), line


@pytest.mark.parametrize("case", sorted(HISTORIES))
def test_mystats_casual_tail_is_the_servers_casual_streak(case):
    records = _fields("cmd_mystats", HISTORIES[case], ranked=False)["⚔️  Records"]
    (line,) = [ln for ln in records.split("\n") if ln.startswith("Casual:")]
    assert line.endswith("  ·  " + WANT), line


def test_mystats_2v2_tail_is_the_servers_team_streak():
    fields = _fields("cmd_mystats", HISTORIES["voided_newest_row"], ranked=True)
    assert fields["👥  2v2"].endswith("  ·  " + WANT), fields["👥  2v2"]


def test_the_bot_reads_no_match_list_for_a_streak():
    """The commands fetch no match list at all now (they fetched one only for
    the streak), and no helper walks one."""
    seen = []
    base = _api(HISTORIES["voided_newest_row"], ranked=True)

    def api(path):
        seen.append(path)
        return base(path)
    for cmd in ("cmd_rank", "cmd_mystats"):
        ns = _lift(api)
        asyncio.run(ns[cmd](_Ctx(), None))
    assert not [p for p in seen if "/matches" in p], seen
    names = {n.name for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not names & {"_calc_streak", "_current_streak"}, names


@pytest.mark.parametrize("value, want", [(3, 3), (-2, -2), (0, 0), (None, 0), (True, 0), ("4", 0)])
def test_streak_field_takes_an_int_only(value, want):
    ns = _lift(_api([], ranked=True))
    assert ns["_streak_field"]({"k": value}, "k") == want
    assert ns["_streak_field"]({}, "k") == 0
