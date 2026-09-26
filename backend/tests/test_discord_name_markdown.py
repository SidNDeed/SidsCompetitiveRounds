"""A player's name renders literally in the bot's Markdown (v1.41.0 beta round 4, finding 23).

Beta review round 3: outside the four leaderboard row renderers finding 16
fixed, discord_bot.py printed player names into Markdown as typed -- the
FAQ's top player, /link, /compare, /elo 2v2 and ffa, the series logs, the
bet posts, the tournament board, the tournament DMs -- so a name carrying
** _ ` or a [text](link) changed the formatting, or made a link whose text
says one thing and whose target is another. AllowedMentions.none() stops
pings; it does not stop Markdown.

discord_bot.py is not importable in a test process (it builds the bot at
import), so, as in test_leaderboard_boards.py, what runs here is lifted out
of its AST and executed against fakes. Two layers:

1. A CENSUS of the whole file. Every place a player's Steam or Discord name
   is put into text -- an f-string, a %-format, a concatenation, a join, a
   direct message or embed argument -- passes it through an escape helper
   (_escape_md, discord.utils.escape_markdown, or one of the file's wrappers
   of it), or is listed in ALLOW with the reason it is not Markdown or not a
   player's name. A new unescaped site fails; so does an ALLOW entry that no
   longer matches anything. _Census.carries says what counts as a name: it
   follows a name through locals, lists, parameters and return values, but
   only from the keys and attributes NAME_KEY, NAME_ATTR and EXTRA_ATTR list,
   and from the parameters EXTRA_ATTR names (round 5, F26: a call to a class
   is not followed into its __init__, so LobbyBetModal's target_label
   argument is seeded by its name). A name the server sends under some other
   key is not seen -- the census's bound, stated rather than hidden.
2. Renderers EXECUTED with hostile names: each shows the name as typed.
"""

import ast
import asyncio
import collections
import copy
import datetime as _dt
import json
import os
import re
import types

import pytest

SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "discord_bot.py"))
TEXT = open(SRC, encoding="utf-8").read()
TREE = ast.parse(TEXT)


# -- the census ----------------------------------------------------------------

NAME_KEY = re.compile(
    r"^(display_name|name|names|nick|opponent|next_opponent|holders|members|lobby_members|player|side|"
    r"team_[ab]|winner_team|login|sender_login|author|discord_username|(next_|pending_)?match_label)$"
    r"|^(?!(card|rank|tag|role|file)_name$)[a-z0-9_]*_name$")
NAME_ATTR = {"display_name", "global_name", "nick", "name"}
EXTRA_ATTR = {"name_a", "name_b", "t1_label", "t2_label", "side_label", "vs_name", "target_label"}
# The escapes. The four after escape_markdown are this file's own wrappers of
# discord.utils.escape_markdown; a value through any of them is literal.
SAFE = {"_escape_md", "escape_markdown", "_md_name", "_pc_name", "_game_embed_plain", "_board_name"}
MSG_KW = {"content", "description", "value", "title", "name", "text", "label", "placeholder"}
MSG_CALLS = {"send", "reply", "edit", "send_message", "edit_message", "Embed", "add_field", "set_author",
             "set_footer", "respond", "edit_original_response", "Button", "SelectOption", "TextInput",
             "_dm_user", "_announce_in_channel", "_post_ingame_chat"}
WRAP_CALLS = {"str", "strip", "lstrip", "rstrip", "get", "title", "upper", "lower"}
_SHARED_NODES = (ast.expr_context, ast.operator, ast.boolop, ast.unaryop, ast.cmpop)


def _call_name(call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _key_of(node):
    """The constant string key of x["k"] or x.get("k", ...), else None."""
    if isinstance(node, ast.Subscript):
        sl = node.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            return sl.value
    if isinstance(node, ast.Call) and _call_name(node) == "get" and isinstance(node.func, ast.Attribute) \
            and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None


class _Census:
    """Every site in `text` where a value carrying a player's name is put into
    text without an escape. A value CARRIES A NAME when it is a subscript or
    .get() of a name key; a name attribute; a local, a closure's outer local
    or a list assigned or appended from such a value through plain wrappers
    (x or "?", str(x), x.strip(), x[:n], a conditional, a tuple, a
    comprehension); a parameter some call site passes such a value to, or one
    named in EXTRA_ATTR; or the result of a function that returns one. A call
    to a class is not followed into its __init__. A value through an escape in SAFE
    carries nothing. Sites inside print() are logs and are not counted."""

    def __init__(self, text):
        self.text = text
        self.tree = ast.parse(text)
        self._line_bytes = [(ln + "\n").encode("utf-8") for ln in text.split("\n")]
        # Each node's parent, by id -- not an attribute on the node: CPython
        # shares one instance of each context and operator node (Load, Store,
        # Add, ...) across every tree it parses, and an attribute there would
        # tie this tree to all the others (the renderer tests' deepcopy of one
        # function would copy the whole census tree with it).
        self._parent = {}
        for node in ast.walk(self.tree):
            for ch in ast.iter_child_nodes(node):
                if not isinstance(ch, _SHARED_NODES):
                    self._parent[id(ch)] = node
        self.funcs = [n for n in ast.walk(self.tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        self.by_name = {}
        for fn in self.funcs:
            self.by_name.setdefault(fn.name, []).append(fn)
        # A parameter named in EXTRA_ATTR carries a name from the start (round
        # 5, F26): LobbyBetModal gets target_label as a constructor argument,
        # and a call to a class is not followed into its __init__.
        self.seeds = {id(fn): {a.arg for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
                               if a.arg in EXTRA_ATTR}
                      for fn in self.funcs}
        self.sources = set()
        self.taint = {}
        self._fixpoint()

    def seg(self, node):
        l1, l2, c1, c2 = node.lineno - 1, node.end_lineno - 1, node.col_offset, node.end_col_offset
        if l1 == l2:
            out = self._line_bytes[l1][c1:c2]
        else:
            out = b"".join([self._line_bytes[l1][c1:]] + self._line_bytes[l1 + 1:l2] + [self._line_bytes[l2][:c2]])
        return out.decode("utf-8", "replace")

    def parents(self, node):
        n = self._parent.get(id(node))
        while n is not None:
            yield n
            n = self._parent.get(id(n))

    def func_of(self, node):
        for p in self.parents(node):
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return p
        return None

    def own_nodes(self, fn):
        stack = list(ast.iter_child_nodes(fn))
        while stack:
            n = stack.pop()
            yield n
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            stack.extend(ast.iter_child_nodes(n))

    def carries(self, expr, tainted):
        if expr is None:
            return False
        if isinstance(expr, ast.Call):
            cn = _call_name(expr)
            if cn in SAFE:
                return False
            k = _key_of(expr)
            if k is not None and NAME_KEY.match(k):
                return True
            if cn in self.sources and isinstance(expr.func, ast.Name):
                return True
            if cn in WRAP_CALLS:
                inner = list(expr.args[:1])
                if isinstance(expr.func, ast.Attribute):
                    inner.append(expr.func.value)
                return any(self.carries(a, tainted) for a in inner)
            return False
        if isinstance(expr, ast.Subscript):
            k = _key_of(expr)
            if k is not None:
                return bool(NAME_KEY.match(k))
            return self.carries(expr.value, tainted)
        if isinstance(expr, ast.Attribute):
            return expr.attr in NAME_ATTR or expr.attr in EXTRA_ATTR or bool(NAME_KEY.match(expr.attr))
        if isinstance(expr, ast.Name):
            return expr.id in tainted
        if isinstance(expr, ast.BoolOp):
            return any(self.carries(v, tainted) for v in expr.values)
        if isinstance(expr, ast.IfExp):
            return self.carries(expr.body, tainted) or self.carries(expr.orelse, tainted)
        if isinstance(expr, (ast.Tuple, ast.List, ast.Set)):
            return any(self.carries(e, tainted) for e in expr.elts)
        if isinstance(expr, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            return self.carries(expr.elt, tainted | self._comp_targets(expr, tainted))
        if isinstance(expr, ast.DictComp):
            return self.carries(expr.value, tainted | self._comp_targets(expr, tainted))
        if isinstance(expr, ast.Dict):
            return any(self.carries(v, tainted) for v in expr.values)
        return False

    def _comp_targets(self, comp, tainted):
        out = set()
        for g in comp.generators:
            if self.carries(g.iter, tainted | out):
                for n in ast.walk(g.target):
                    if isinstance(n, ast.Name):
                        out.add(n.id)
        return out

    def _local_taint(self, fn, outer):
        tainted = set(outer) | self.seeds[id(fn)]
        changed = True
        while changed:
            changed = False
            for node in self.own_nodes(fn):
                pairs = []
                if isinstance(node, ast.Assign):
                    pairs = [(t, node.value) for t in node.targets]
                elif isinstance(node, ast.AnnAssign) and node.value is not None:
                    pairs = [(node.target, node.value)]
                elif isinstance(node, (ast.For, ast.AsyncFor)):
                    pairs = [(node.target, node.iter)]
                elif isinstance(node, ast.comprehension):
                    pairs = [(node.target, node.iter)]
                elif isinstance(node, ast.NamedExpr):
                    pairs = [(node.target, node.value)]
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr in ("append", "extend", "insert", "add") \
                        and isinstance(node.func.value, ast.Name):
                    pairs = [(node.func.value, a) for a in node.args]
                for target, value in pairs:
                    if not self.carries(value, tainted):
                        continue
                    for n in ast.walk(target):
                        if isinstance(n, ast.Name) and n.id not in tainted:
                            tainted.add(n.id)
                            changed = True
        return tainted

    def _fixpoint(self):
        for _ in range(50):
            changed = False
            self.taint = {}
            order = sorted(self.funcs, key=lambda f: sum(1 for _ in self.parents(f)))
            for fn in order:
                outer_fn = self.func_of(fn)
                outer = self.taint.get(id(outer_fn), set()) if outer_fn is not None else set()
                self.taint[id(fn)] = self._local_taint(fn, outer)
            for fn in self.funcs:
                t = self.taint[id(fn)]
                for node in self.own_nodes(fn):
                    if isinstance(node, ast.Return) and fn.name not in self.sources \
                            and self.carries(node.value, t):
                        self.sources.add(fn.name)
                        changed = True
                    if not isinstance(node, ast.Call):
                        continue
                    for tgt in self.by_name.get(_call_name(node), []):
                        params = [a.arg for a in tgt.args.posonlyargs + tgt.args.args]
                        shift = 1 if params[:1] == ["self"] and isinstance(node.func, ast.Attribute) else 0
                        for i, a in enumerate(node.args):
                            j = i + shift
                            if j < len(params) and self.carries(a, t) and params[j] not in self.seeds[id(tgt)]:
                                self.seeds[id(tgt)].add(params[j])
                                changed = True
                        kwnames = set(params) | {a.arg for a in tgt.args.kwonlyargs}
                        for kw in node.keywords:
                            if kw.arg in kwnames and self.carries(kw.value, t) \
                                    and kw.arg not in self.seeds[id(tgt)]:
                                self.seeds[id(tgt)].add(kw.arg)
                                changed = True
            if not changed:
                return
        raise AssertionError("the census found no fixpoint")

    def in_print(self, node):
        for p in self.parents(node):
            if isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.func.id == "print":
                return True
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return False
        return False

    def sites(self):
        out = []
        for node in ast.walk(self.tree):
            fn = self.func_of(node)
            t = self.taint.get(id(fn), set()) if fn is not None else set()
            found = []
            if isinstance(node, ast.JoinedStr):
                for v in node.values:
                    if isinstance(v, ast.FormattedValue) and self.carries(v.value, t):
                        found.append(("F", v, v.value))
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and \
                    isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                args = node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
                for a in args:
                    if self.carries(a, t):
                        found.append(("P", node, a))
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                for side in (node.left, node.right):
                    if self.carries(side, t):
                        found.append(("A", node, side))
            elif isinstance(node, ast.Call):
                cn = _call_name(node)
                if cn == "format" and isinstance(node.func, ast.Attribute) and \
                        isinstance(node.func.value, ast.Constant):
                    for a in list(node.args) + [k.value for k in node.keywords]:
                        if self.carries(a, t):
                            found.append(("P", node, a))
                elif cn == "join" and node.args and self.carries(node.args[0], t):
                    found.append(("J", node, node.args[0]))
                elif cn in MSG_CALLS:
                    for k in node.keywords:
                        if k.arg in MSG_KW and self.carries(k.value, t):
                            found.append(("K", node, k.value))
                    for a in node.args:
                        if self.carries(a, t):
                            found.append(("K", node, a))
            for kind, where, expr in found:
                if self.in_print(where):
                    continue
                out.append((fn.name if fn else "<module>", self.seg(expr), kind, where.lineno))
        return sorted(out, key=lambda s: (s[3], s[1]))


# Sites the census finds that are NOT a player's name in Markdown, each with
# its reason: {(function, expression): (count, reason)}. Everything else it
# finds must go through an escape.
_BUTTON = "a button label: plain text, Discord renders no Markdown there"
_FOOTER = "embed footer text: plain text, no Markdown"
_LABEL = "a bracket round label, not a player's name"
ALLOW = {
    ("_mailpick_view", '(t.get("sender_name") or "?").strip()'): (1, _BUTTON),
    ("_maybe_answer_faq_ingame", "data.get('steam_id') or data.get('display_name') or ''"):
        (1, "an internal key for the answered-once check, never shown"),
    ("_fetch_rating_history", "steam_id"): (2, "a Steam id in an API path, not a name"),
    ("cmd_graph", "sid"): (1, "a Steam id in an API path, not a name"),
    ("cmd_graph", "fetch_failed"): (1, _FOOTER),
    ("cmd_graph", "no_cards"): (1, _FOOTER),
    ("cmd_graph", "no_regions"): (1, _FOOTER),
    ("cmd_graph", "dropped"): (1, _FOOTER),
    ("cmd_graph", "missing"): (1, _FOOTER),
    ("_elo_2v2", "label"): (1, "the constants Team A and Team B"),
    ("_elo_ffa", "[ctx.author] if me else []"): (1, "a list of members, not text"),
    ("cmd_game", "p.get('side')"): (1, "the 1v2 side, solo or duo, not a name"),
    ("poll_ffa_queue_beacon", "members"): (1, "the lobby's member count"),
    ("poll_bug_reports", "who[:40]"): (1, "a thread name: plain text, no Markdown"),
    ("poll_anticheat_flags", "f.get('p1_name')"): (1, "composed into ids, which _flag_embed_text escapes whole"),
    ("poll_anticheat_flags", "f.get('p2_name')"): (1, "composed into ids, which _flag_embed_text escapes whole"),
    ("_format_release_message", "name"): (1, "the GitHub release's title, not a player's name"),
    ("dm_opponent", "opp_id"): (1, "the Discord id _dm_user sends to, not text"),
    ("_tmatch_notice_message", "match_label"): (1, _LABEL),
    ("_tmatch_notice_message", "dest"): (4, _LABEL),
    ("_build_tournament_board_embed", "medal"): (2, "the medal emoji beside the podium name"),
    ("__init__", "side_label[:14]"): (1, _BUTTON),
    ("__init__", "side_label[:12]"): (1, _BUTTON),
    ("__init__", "side_label"): (2, _BUTTON),
    ("_pair_label", "(a or '?')[:per]"): (1, _BUTTON + "; its Markdown uses escape at their own sites"),
    ("_pair_label", "(b or '?')[:per]"): (1, _BUTTON + "; its Markdown uses escape at their own sites"),
    ("__init__", "side[:38]"): (2, "a modal title: plain text, no Markdown"),
    ("__init__", "str(target_label)[:38]"): (1, "a modal title: plain text, no Markdown"),
    ("__init__", "nm[:100]"): (1, "a select option label: plain text"),
    ("__init__", "sid[:100]"): (1, "a select option value, not shown"),
    ("_normalize_bettable_lobby", "_nm[:80]"): (1, "a select option label: plain text"),
    ("_normalize_bettable_lobby", "str(val)[-4:]"): (1, "a select option label: plain text"),
}


def _unexpected(sites):
    found = collections.Counter((f, e) for f, e, _k, _l in sites)
    extra = {k: n for k, n in found.items() if n > ALLOW.get(k, (0, ""))[0]}
    stale = {k: v[0] for k, v in ALLOW.items() if found.get(k, 0) < v[0]}
    return extra, stale


@pytest.fixture(scope="module")
def census_sites():
    return _Census(TEXT).sites()


def test_every_player_name_in_markdown_goes_through_an_escape(census_sites):
    """Round 4, finding 23: the class sweep. Every site the census finds is
    escaped, or in ALLOW with its reason -- and ALLOW holds nothing that no
    longer matches, so it cannot quietly outlive the sites it excuses."""
    extra, stale = _unexpected(census_sites)
    lines = {(f, e): ln for f, e, _k, ln in census_sites}
    assert not extra, "a player's name reaches Markdown unescaped: " + "; ".join(
        f"{f} line {lines[(f, e)]}: {e}" for f, e in sorted(extra))
    assert not stale, f"ALLOW entries that match fewer sites than listed: {stale}"


# One unescaped site of each kind the census reports: an f-string, a
# %-format, a concatenation and a join. (function, escaped text, unescaped text).
_UNWRAPS = (
    ("_faq_top_player", "**{_escape_md(top['display_name'])}**", "**{top['display_name']}**",
     "top['display_name']"),
    ("_mail_sent_line", "% (_escape_md(who), subj)", "% (who, subj)", "who"),
    ("poll_bug_report_events", '"Note from " + _escape_md(actor)', '"Note from " + actor', "actor"),
    ("cmd_graph", '", ".join(_escape_md(n) for n in not_linked)', '", ".join(not_linked)', "not_linked"),
)


def test_the_census_finds_an_unescaped_name_of_each_kind():
    """The census's own negative control: the same file with one escape
    removed at an f-string, a %-format, a concatenation and a join. Each
    unescaped site is reported, and nothing else is."""
    text = TEXT
    for _fn, escaped, raw, _expr in _UNWRAPS:
        assert text.count(escaped) == 1, escaped
        text = text.replace(escaped, raw)
    extra, stale = _unexpected(_Census(text).sites())
    assert set(extra) == {(fn, expr) for fn, _e, _r, expr in _UNWRAPS}, extra
    assert not stale


# -- renderers, executed -------------------------------------------------------

BREAKS = "\r\n\v\f" + "".join(map(chr, (0x1C, 0x1D, 0x1E, 0x85, 0x2028, 0x2029)))
HOSTILE = ["[watch](https://example.invalid)", "**Admin**", "# Big", "a_b_c", "`x`", "<@123>",
           "1. first", "- item", "Name\n# Fake", "back\\slash"]


HOSTILE_IDS = ["link", "bold", "heading", "underscores", "code", "mention", "numbered", "bullet",
               "break-then-heading", "backslash"]


def _expect(name):
    """The name as the bot must print it, written out here rather than taken
    from the bot's helper: every line break a space (a CRLF pair one space),
    each of \\ * _ ~ | ` [ ] < > after a backslash, and a leading # - + or
    the dot of a leading 1. after a backslash too."""
    one = re.sub("\r\n", " ", name)
    one = "".join(" " if c in BREAKS else c for c in one)
    out = "".join("\\" + c if c in "\\*_~|`[]<>" else c for c in one)
    out = re.sub(r"^(\s*)([#+-])", lambda m: m.group(1) + "\\" + m.group(2), out)
    return re.sub(r"^(\s*\d+)([.)])", lambda m: m.group(1) + "\\" + m.group(2), out)


def _shows_literally(text, name):
    exp = _expect(name)
    assert exp in text, (name, exp, text)
    if exp != name:
        assert name not in text.replace(exp, ""), (name, text)


class _Embed:
    def __init__(self, title=None, description=None, color=None, timestamp=None, **kw):
        self.title, self.description, self.color = title, description, color
        self.fields, self.footer = [], None

    def add_field(self, name=None, value=None, inline=True):
        self.fields.append((name, value))

    def set_footer(self, text=None, **kw):
        self.footer = text


def _lift(funcs=(), assigns=(), extra=None):
    picked, seen = [], set()
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in funcs:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            picked.append(fn)
            seen.add(node.name)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in assigns
                                                  for t in node.targets):
            picked.append(node)
            seen.update(t.id for t in node.targets if isinstance(t, ast.Name))
    assert seen >= set(funcs) | set(assigns), (set(funcs) | set(assigns)) - seen
    import types
    ns = {"re": re, "_faq_re": re, "datetime": _dt.datetime, "timezone": _dt.timezone,
          "discord": types.SimpleNamespace(Embed=_Embed)}
    ns.update(extra or {})
    exec(compile(ast.Module(body=picked, type_ignores=[]), SRC, "exec"), ns)
    return ns


@pytest.mark.parametrize("name,shown", [("# Big", "\\# Big"), ("- item", "\\- item"), ("+x", "\\+x"),
                                        ("1. first", "1\\. first"), ("12) x", "12\\) x"),
                                        ("-# sub", "\\-# sub"), ("a-b", "a-b"), ("Plain Name", "Plain Name")],
                         ids=["hash", "dash", "plus", "dot", "paren", "subtext", "dash-inside", "plain"])
def test_a_name_that_opens_a_line_opens_nothing(name, shown):
    """Round 4, finding 23: a name can START a line -- /opponent-online's
    reply begins with it, an embed field's name can be it -- and there a
    leading # is a heading, - or + a list item or subtext, 1. a numbered
    list. The helper puts a backslash before that marker (Discord shows the
    marker alone); the same character later in a name is left as it is.

    MUTATION: the line-start escape removed. Must fail."""
    ns = _lift(funcs=("_escape_md",))
    assert ns["_escape_md"](name) == shown


def test_the_faq_top_player_is_literal_on_discord_and_as_typed_in_game():
    """The FAQ's top-player answer (round 3's example at discord_bot.py:1170)
    prints three leaderboard names. On Discord each is literal; in-game chat
    gets the same answer through _faq_plainify, which drops the escapes, so
    a player there still reads the name as typed.

    MUTATION: the escape removed at the top player, or the in-game un-escape
    removed. Each must fail."""
    names = ["**Admin**", "a_b_c", "[watch](https://example.invalid)"]

    async def api_get(path, timeout=8.0):
        return {"entries": [{"display_name": n, "rating": 1700 - i, "wins": 9, "losses": 1}
                            for i, n in enumerate(names)]}

    ns = _lift(funcs=("_escape_md", "_faq_plainify", "_faq_top_player"), extra={"api_get": api_get})
    answer = asyncio.run(ns["_faq_top_player"](None))
    for n in names:
        _shows_literally(answer, n)
    assert answer.count(_expect(names[0])) == 2          # the lead line and the podium
    plain = ns["_faq_plainify"](answer)
    for n in names:
        assert n in plain, (n, plain)
    assert "\\" not in plain, plain


@pytest.mark.parametrize("name", HOSTILE, ids=HOSTILE_IDS)
def test_a_tournament_board_prints_every_name_literally(name):
    """The tournament board's roster and podium: public, and seen by every
    player in the tournament channel.

    MUTATION: the roster's escape removed. Must fail."""
    ns = _lift(funcs=("_escape_md", "_fmt_pt", "_build_tournament_board_embed"),
               assigns=("ASYNC_DEADLINE_DAYS", "_TOURNEY_HOW_IT_WORKS"),
               extra={"_bracket_progress_lines": lambda t: []})
    signups = [{"signup_id": i, "display_name": n, "is_speculative": False}
               for i, n in enumerate([name, "Second", "Third"])]
    voting = ns["_build_tournament_board_embed"](
        {"status": "voting", "signups": signups, "min_players": 8, "max_players": 16}, "sync")
    _shows_literally(voting.description, name)
    done = ns["_build_tournament_board_embed"](
        {"status": "completed", "signups": signups, "winner_signup_id": 0,
         "runner_up_signup_id": 1, "third_place_signup_id": 2}, "async")
    _shows_literally(done.description, name)


@pytest.mark.parametrize("name", HOSTILE, ids=HOSTILE_IDS)
def test_the_live_bet_posts_print_every_name_literally(name):
    """The gambler channel's 1v1 and 2v2 live posts: the names are in the
    title and in the odds or team lines.

    MUTATION: the 2v2 title's escape removed. Must fail."""
    ns = _lift(funcs=("_escape_md", "_format_live_bet_embed", "_format_team_live_bet_embed"))
    one = ns["_format_live_bet_embed"]({"series_id": "s" * 12, "p1_name": name, "p2_name": "Other"})
    _shows_literally(one.title, name)
    _shows_literally(one.description, name)
    two = ns["_format_team_live_bet_embed"]({"series_id": "t" * 12, "t1a_name": name, "t1b_name": "B",
                                             "t2a_name": "C", "t2b_name": "D"})
    _shows_literally(two.title, name)
    _shows_literally(two.description, name)


@pytest.mark.parametrize("name", HOSTILE, ids=HOSTILE_IDS)
def test_a_mail_confirmation_and_a_moderation_result_print_names_literally(name):
    """Two replies that name a player to someone else: the mail relay's
    "sent your reply to NAME" and a moderation button's "applied by NAME to
    NAME"."""
    ns = _lift(funcs=("_escape_md", "_mail_sent_line", "_modcase_render"))
    _shows_literally(ns["_mail_sent_line"]({"known": True, "sender_name": name, "subject": "hi"}), name)
    body = {"status": "ok", "subject_name": name, "subject_steam_id": "76561190000000000"}
    spec = {"label": "Mute", "case_id": "abcdef0123456789"}
    text = ns["_modcase_render"](200, body, spec, "**Mod**")
    _shows_literally(text, name)
    _shows_literally(text, "**Mod**")


# -- round 5, F26: the lobby bet's target label ---------------------------------
#
# LobbyBetModal's target_label is the select option's label, built from the
# players' names (_normalize_bettable_lobby, _build_lobby_bet_targets). The
# confirmation on_submit sends is Markdown; the modal title is plain text.

_LOBBY_ESCAPED = "**{_escape_md(self.target_label)}**"
_LOBBY_RAW = "**{self.target_label}**"
_LOBBY_TITLE = ("__init__", "str(target_label)[:38]")
_MASKED_LINK = re.compile(r"\[[^\]]*\]\(")


class _Interaction:
    """What LobbyBetModal.on_submit touches: the user's id, a response that
    _bet_ack defers, and the followup _bet_reply then sends through. Every
    message sent is kept, in order."""

    def __init__(self):
        self.user = types.SimpleNamespace(id=4242)
        self.sent = []
        sent, deferred = self.sent, []

        class _Response:
            async def defer(self, ephemeral=False, thinking=False):
                deferred.append(True)

            def is_done(self):
                return bool(deferred)

            async def send_message(self, msg, ephemeral=False):
                sent.append(msg)

        class _Followup:
            async def send(self, msg, ephemeral=False):
                sent.append(msg)

        self.response = _Response()
        self.followup = _Followup()


def _lobby_bet_confirmation(label, text=None):
    """(messages sent, API posts) when a bettor submits 1,250 gold on `label`
    in a 2v2 lobby: LobbyBetModal.on_submit lifted out of `text` (the bot's
    source by default) with every helper it calls -- _parse_bet_amount,
    _bet_ack, _discord_bet_error, _bet_reply, _escape_md and
    _LOBBY_BET_MODE_LABEL, all the bot's own -- run against a fake
    interaction and an api_post that accepts the bet."""
    tree = TREE if text is None else ast.parse(text)
    helpers = {"_parse_bet_amount", "_bet_ack", "_discord_bet_error", "_bet_reply", "_escape_md"}
    picked, seen = [], set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in helpers:
            picked.append(copy.deepcopy(node))
            seen.add(node.name)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_LOBBY_BET_MODE_LABEL"
                                                  for t in node.targets):
            picked.append(copy.deepcopy(node))
            seen.add("_LOBBY_BET_MODE_LABEL")
        elif isinstance(node, ast.ClassDef) and node.name == "LobbyBetModal":
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "on_submit":
                    picked.append(copy.deepcopy(item))
                    seen.add("on_submit")
    assert seen == helpers | {"_LOBBY_BET_MODE_LABEL", "on_submit"}, seen
    posted = []

    async def api_post(path, params=None, timeout=None):
        posted.append((path, dict(params or {})))
        return {"status": "ok"}

    ns = {"re": re, "json": json, "api_post": api_post,
          "discord": types.SimpleNamespace(Interaction=object)}
    exec(compile(ast.Module(body=picked, type_ignores=[]), SRC, "exec"), ns)
    modal = types.SimpleNamespace(mode="team", lobby_id="0123456789abcdef",
                                  target_steams="90000000000000001,90000000000000002",
                                  target_label=label, amount_input=types.SimpleNamespace(value="1,250"))
    interaction = _Interaction()
    asyncio.run(ns["on_submit"](modal, interaction))
    return interaction.sent, posted


def _markup(text):
    """The Markdown a message still carries once every backslash-escaped
    character is dropped: what Discord formats."""
    return re.sub(r"\\.", "", text)


@pytest.mark.parametrize("name", HOSTILE, ids=HOSTILE_IDS)
def test_the_lobby_bet_confirmation_prints_the_target_label_literally(name):
    """Round 5, F26: the bettor's confirmation names whom the bet backs.
    Whatever that label holds -- a masked link, **bold**, a heading, a line
    break -- it shows as typed, and the message keeps exactly its own
    formatting: the amount and the label in bold, the lobby id as code, no
    link, one line.

    MUTATION: the confirmation's escape removed. Must fail (the next test
    runs that mutation on the two cases the review names)."""
    sent, posted = _lobby_bet_confirmation(name)
    assert [(p, q["amount"]) for p, q in posted] == [("/discord-lobby-bets", 1250)], posted
    assert len(sent) == 1, sent
    msg = sent[0]
    _shows_literally(msg, name)
    assert " Bet placed: **1,250g** on **%s** in 2v2 lobby `01234567` " % _expect(name) in msg, msg
    shown = _markup(msg)
    assert shown.count("**") == 4 and shown.count("`") == 2, shown
    assert not _MASKED_LINK.search(shown) and "\n" not in msg, shown


@pytest.mark.parametrize("name", ["[watch](https://example.invalid)", "**Admin**"],
                         ids=["masked-link", "bold"])
@pytest.mark.parametrize("escaped", [True, False], ids=["as-shipped", "escape-removed"])
def test_the_lobby_bet_confirmation_test_can_fail(name, escaped):
    """Control (#391) for the test above, on the two cases the review names:
    on_submit lifted from the bot's source with the confirmation's escape
    removed prints the name as Markdown -- a link whose text hides its
    target, or bold that swallows the message's own -- so both checks above
    fail; as shipped (the inert twin) both pass."""
    assert TEXT.count(_LOBBY_ESCAPED) == 1
    text = TEXT if escaped else TEXT.replace(_LOBBY_ESCAPED, _LOBBY_RAW)
    sent, _posted = _lobby_bet_confirmation(name, text)
    shown = _markup(sent[0])
    literal = _expect(name) in sent[0]
    formatted = shown.count("**") != 4 or bool(_MASKED_LINK.search(shown))
    assert (literal, formatted) == ((True, False) if escaped else (False, True)), sent


def test_the_census_counts_the_lobby_target_label(monkeypatch):
    """Round 5, F26: target_label is in the census's vocabulary. With the
    confirmation's escape removed the census reports exactly that site; the
    modal title is counted as well, and excused in ALLOW as plain text.
    Without target_label in EXTRA_ATTR (round 4's vocabulary) the census sees
    neither: the removed escape goes unreported and the title's ALLOW entry
    matches nothing. The vocabulary entry is what makes the flow count."""
    assert TEXT.count(_LOBBY_ESCAPED) == 1
    raw = TEXT.replace(_LOBBY_ESCAPED, _LOBBY_RAW)
    found = collections.Counter((f, e) for f, e, _k, _l in _Census(TEXT).sites())
    assert (found[_LOBBY_TITLE], found[("on_submit", "self.target_label")]) == (1, 0), found
    extra, stale = _unexpected(_Census(raw).sites())
    assert (set(extra), stale) == ({("on_submit", "self.target_label")}, {}), (extra, stale)
    monkeypatch.setitem(globals(), "EXTRA_ATTR", EXTRA_ATTR - {"target_label"})
    extra, stale = _unexpected(_Census(raw).sites())
    assert (extra, stale) == ({}, {_LOBBY_TITLE: 1}), (extra, stale)
