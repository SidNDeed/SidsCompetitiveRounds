"""Free text a person typed is shown by the bot as the characters typed (BOT-TEXT-ESCAPE-1).

A bug report's description, a comment on a report, a ban's reason: text a
person typed, posted by the bot into Discord. Before this change those texts
went out as they were stored, so a comment holding ** or || or a heading
changed the post's formatting, and a [text](link) showed one address and
opened another. AllowedMentions.none() (the client default) keeps a mention
from pinging; it does not keep it from showing as a mention.

_escape_text is the bot's ONE helper for such text. It is the bot's own code
and calls no library escape (the bot image installs discord.py unpinned).
discord_bot.py is not importable in a test process (it builds the bot at
import), so, as in test_discord_name_markdown.py, what runs here is lifted
out of its AST and executed against fakes. Two layers:

1. The helper, case by case: one case per construct the requirement names,
   line breaks, a bare web address, the cut, backslashes, the empty text and
   a text of marks only. Every case is also run against a helper that returns
   its input, and must fail there (test_each_case_fails_for_a_helper_that_
   returns_its_input), so no case passes for a helper that does nothing.
2. The sites, executed with a typed text that holds marks and mentions: each
   field shows exactly the once-escaped text, so neither a missing escape nor
   a second pass over escaped text passes.
"""

import ast
import asyncio
import builtins
import copy
import os
import re
import types

import pytest

SRC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "discord_bot.py"))
TEXT = open(SRC, encoding="utf-8").read()
TREE = ast.parse(TEXT)
HELPER_PARTS = ("_TEXT_BREAKS", "_TEXT_URL", "_TEXT_LINE_MARK", "_TEXT_ALWAYS")


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
    ns = {"re": re}
    ns.update(extra or {})
    exec(compile(ast.Module(body=picked, type_ignores=[]), SRC, "exec"), ns)
    return ns


ESC = _lift(("_escape_text",), HELPER_PARTS)["_escape_text"]


def _identity(text, limit=None, more="..."):
    return text


# -- how Discord shows a text, written out here ---------------------------------
#
# A bare address (http:// or https:// not glued to a word character before
# it) is a link to its last character that is not . , : ; " ' ) ] -- inside
# it nothing is markdown. Elsewhere a backslash before an ASCII character that
# is not a letter, a digit or white space shows that character alone.

_ADDR = re.compile(r"(?<![0-9A-Za-z_])https?://[^\s<]*[^\s<.,:;\"')\]]", re.IGNORECASE)
_ESCAPABLE = set(chr(c) for c in range(33, 127)) - set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


def _walk(out):
    """(shown text, skeleton). The skeleton holds \\x00 for each escape pair
    and \\x01 for each character of an address, everything else as is."""
    shown, skel, i = [], [], 0
    while i < len(out):
        u = _ADDR.match(out, i)
        if u:
            shown.append(u.group(0))
            skel.append("\x01" * len(u.group(0)))
            i = u.end()
            continue
        if out[i] == "\\" and i + 1 < len(out) and out[i + 1] in _ESCAPABLE:
            shown.append(out[i + 1])
            skel.append("\x00")
            i += 2
            continue
        shown.append(out[i])
        skel.append(out[i])
        i += 1
    return "".join(shown), "".join(skel)


def shown(out):
    return _walk(out)[0]


_LIVE_ANYWHERE = set("\\*_~|`[]<>@")
_LIVE_LINE_OPEN = re.compile(r"[ \t]*([#+-]|[0-9]+[.)])")


def live(out):
    """Every construct that would take effect in `out`: a mark outside an
    escape pair and outside an address, or a line that opens with a heading,
    list or numbered-list mark. Empty means the text is shown as characters."""
    skel = _walk(out)[1]
    found = sorted(set(c for c in skel if c in _LIVE_ANYWHERE))
    for line in skel.split("\n"):
        m = _LIVE_LINE_OPEN.match(line)
        if m:
            found.append("line opens with " + m.group(1))
    return found


def _typed(text):
    """The typed text as it must be shown: every line break one \\n."""
    return re.sub(r"\r\n|[\r\v\f\x1c-\x1e\x85\u2028\u2029]", "\n", text)


def _problems(helper, text, want):
    out = helper(text)
    probs = []
    if out != want:
        probs.append(("output", out, want))
    if not isinstance(out, str):
        return probs + [("not a str", out)]
    if shown(out) != _typed(text):
        probs.append(("shown", shown(out), _typed(text)))
    if live(out):
        probs.append(("live", live(out)))
    return probs


# -- 1. the helper, case by case -------------------------------------------------

CASES = [
    # emphasis, bold, underline, strike, spoiler
    ("emphasis-star", "*a*", "\\*a\\*"),
    ("emphasis-underscore", "_a_", "\\_a\\_"),
    ("bold", "**a**", "\\*\\*a\\*\\*"),
    ("bold-italic", "***a***", "\\*\\*\\*a\\*\\*\\*"),
    ("underline", "__a__", "\\_\\_a\\_\\_"),
    ("strike", "~~a~~", "\\~\\~a\\~\\~"),
    ("spoiler", "||a||", "\\|\\|a\\|\\|"),
    # code span, code block
    ("code-span", "`a`", "\\`a\\`"),
    ("code-span-double", "``a``", "\\`\\`a\\`\\`"),
    ("code-block", "```py\nx\n```", "\\`\\`\\`py\nx\n\\`\\`\\`"),
    # block quote
    ("quote", "> a", "\\> a"),
    ("quote-block", ">>> a", "\\>\\>\\> a"),
    ("quote-second-line", "a\n> b", "a\n\\> b"),
    # heading
    ("heading-1", "# a", "\\# a"),
    ("heading-2", "## a", "\\## a"),
    ("heading-3", "### a", "\\### a"),
    ("heading-second-line", "a\n# b", "a\n\\# b"),
    ("heading-indented", "  # a", "  \\# a"),
    # list marks
    ("list-dash", "- a", "\\- a"),
    ("list-star", "* a", "\\* a"),
    ("list-plus", "+ a", "\\+ a"),
    ("list-number-dot", "1. a", "1\\. a"),
    ("list-number-paren", "12) a", "12\\) a"),
    ("list-nested", "- a\n  - b", "\\- a\n  \\- b"),
    ("list-second-line", "a\n2. b", "a\n2\\. b"),
    # masked link
    ("masked-link", "[a](https://example.com/x)", "\\[a\\](https://example.com/x)"),
    ("masked-link-angle", "[a](<https://example.com/x>)", "\\[a\\](\\<https://example.com/x>)"),
    # small text
    ("small-text", "-# a", "\\-# a"),
    ("small-text-second-line", "a\n-# b", "a\n\\-# b"),
    # mention forms
    ("mention-user", "<@123456789012345678>", "\\<\\@123456789012345678\\>"),
    ("mention-nick", "<@!123456789012345678>", "\\<\\@!123456789012345678\\>"),
    ("mention-role", "<@&123456789012345678>", "\\<\\@&123456789012345678\\>"),
    ("mention-channel", "<#123456789012345678>", "\\<#123456789012345678\\>"),
    ("mention-everyone", "hi @everyone", "hi \\@everyone"),
    ("mention-here", "@here now", "\\@here now"),
    ("mention-slash-command", "</ban:123456789012345678>", "\\</ban:123456789012345678\\>"),
    ("mention-timestamp", "<t:1700000000:R>", "\\<t:1700000000:R\\>"),
    ("mention-emoji", "<:smile:123456789012345678>", "\\<:smile:123456789012345678\\>"),
    # line breaks kept, each kind one \n; marks inside a line stay plain
    ("line-breaks", "a\nb\r\nc\rd\u2028e\x85f", "a\nb\nc\nd\ne\nf"),
    ("line-breaks-open-lines", "ok # 1. - fine\n# h\n- l\n> q\n1. n\r\n+ p",
     "ok # 1. - fine\n\\# h\n\\- l\n\\> q\n1\\. n\n\\+ p"),
    # a bare web address stays whole; text around it is escaped
    ("address", "*see* https://example.com/a_b*c~d|e_(x) and https://x.example/q?a=1&b=__z__.",
     "\\*see\\* https://example.com/a_b*c~d|e_(x) and https://x.example/q?a=1&b=__z__."),
    ("address-opens-line", "https://example.com/__a__\n_b_", "https://example.com/__a__\n\\_b\\_"),
    ("address-glued-is-text", "xhttps://a.example/_b_", "xhttps://a.example/\\_b\\_"),
    ("address-trailing-marks", "(https://example.com/a_b), *x*", "(https://example.com/a_b), \\*x\\*"),
    # backslashes already in the text
    ("backslashes", "a\\b\\*c\\", "a\\\\b\\\\\\*c\\\\"),
    ("backslash-before-mark", "\\_x_", "\\\\\\_x\\_"),
    # a text of marks only
    ("marks-only", "\\*_~|`[]<>@", "\\\\\\*\\_\\~\\|\\`\\[\\]\\<\\>\\@"),
    ("marks-only-line-open", "#\n-\n+\n1.", "\\#\n\\-\n\\+\n1\\."),
]


@pytest.mark.parametrize("text,want", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_a_typed_text_is_shown_as_typed(text, want):
    assert _problems(ESC, text, want) == []


@pytest.mark.parametrize("text,want", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_each_case_fails_for_a_helper_that_returns_its_input(text, want):
    """The failing-first control, kept: a helper that returns its input
    fails every case above."""
    assert _problems(_identity, text, want) != []


def test_an_empty_text_is_empty():
    assert ESC("") == ""
    assert ESC(None) == ""
    assert ESC("", limit=0) == ""
    assert ESC(None, limit=5, more="...") == ""


def test_a_non_text_value_is_shown_as_its_text():
    assert ESC(12) == "12"
    assert ESC("1. a") == "1\\. a"


# -- the cut -------------------------------------------------------------------

CUT_TEXTS = [
    "*" * 20,
    "a_b_c_d_" * 5,
    "- x\n# y\n> z\n12. w\n" * 3,
    "see https://example.com/a_long_path_here end *x*",
    "\\" * 9,
    "<@123456789012345678> @everyone ||s||",
]


@pytest.mark.parametrize("text", CUT_TEXTS, ids=range(len(CUT_TEXTS)))
def test_a_cut_never_ends_inside_an_escape_pair(text):
    full = ESC(text)
    typed = _typed(text)
    for limit in range(0, len(full) + 3):
        out = ESC(text, limit, "...")
        assert len(out) <= limit, (limit, out)
        if len(full) <= limit:
            assert out == full, (limit, out)
            continue
        if limit < 3:
            assert out == "..."[:limit]
            continue
        assert out.endswith("..."), (limit, out)
        body = out[:-3]
        assert full.startswith(body), (limit, body)
        assert live(body) == [], (limit, body, live(body))
        assert typed.startswith(shown(body)), (limit, body)
        # an address is kept whole or not at all
        if "https://" in body:
            assert "https://example.com/a_long_path_here" in body, (limit, body)


def test_a_cut_keeps_whole_pieces():
    assert ESC("*" * 10, 7, "...") == "\\*\\*..."
    assert ESC("*" * 10, 8, "...") == "\\*\\*..."
    assert ESC("12. ab", 6, "+") == "12\\. +"
    assert ESC("12. ab", 3, "+") == "+"
    assert ESC("ab https://example.com/x", 10, "...") == "ab ..."
    assert ESC("abc", 2, "...") == ".."
    assert ESC("*a*", 6) == "\\*a\\*"


def test_the_cut_fails_for_a_helper_that_returns_its_input():
    assert len(_identity("*" * 20, 7, "...")) > 7


# -- the helper is the bot's own -----------------------------------------------

def test_the_helper_calls_no_library_escape():
    """Lesson 253: the library's clean-up is a baseline only and its
    behaviour moves with an unpinned version; the helper is the bot's own."""
    picked = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_escape_text"]
    assert len(picked) == 1
    calls = {ast.unparse(c.func) for c in ast.walk(picked[0]) if isinstance(c, ast.Call)}
    assert not any("discord" in c or "escape_markdown" in c or "escape_mentions" in c for c in calls), calls


# -- 2. the sites ----------------------------------------------------------------

TYPED = "**b** <@&42> @here\n# h\n[x](https://e.example/a_b)"
SHOWN = "\\*\\*b\\*\\* \\<\\@&42\\> \\@here\n\\# h\n\\[x\\](https://e.example/a_b)"


def test_the_site_text_is_shown_as_typed():
    """The text the site tests send, checked once against the helper."""
    assert ESC(TYPED) == SHOWN and shown(SHOWN) == TYPED and live(SHOWN) == []


class _Embed:
    def __init__(self, title=None, description=None, color=None, timestamp=None, **kw):
        self.title, self.description = title, description
        self.fields, self.footer = [], None

    def add_field(self, name=None, value=None, inline=True):
        self.fields.append((name, value))

    def set_footer(self, text=None, **kw):
        self.footer = text

    def field(self, name):
        (value,) = [v for n, v in self.fields if n == name]
        return value


class _NotFound(Exception):
    pass


class _Forbidden(Exception):
    pass


def _discord():
    return types.SimpleNamespace(
        Embed=_Embed, NotFound=_NotFound, Forbidden=_Forbidden,
        AllowedMentions=types.SimpleNamespace(none=lambda: "none"),
        utils=types.SimpleNamespace(escape_markdown=lambda s: re.sub(r"([\\*_~|`])", r"\\\1", s)))


class _Sink:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, embed=None, **kw):
        self.sent.append(embed if embed is not None else content)
        return self

    async def create_thread(self, **kw):
        return None

    async def edit(self, **kw):
        return None


async def _noop(*a, **kw):
    return None


def _run(coro):
    return asyncio.run(coro)


def test_a_bug_report_post_shows_the_description_as_typed():
    channel = _Sink()

    async def api_get(path, timeout=8.0):
        return {"reports": [{"id": "r1", "bug_number": 7, "display_name": "P", "mod_version": "1",
                             "severity": "low", "category": "ui", "description": "  " + TYPED + " "}]}

    ns = _lift(("poll_bug_reports", "_escape_md", "_escape_text"), HELPER_PARTS, {
        "discord": _discord(), "BUG_REPORTS_CHANNEL_ID": 1, "api_get": api_get, "api_post": _noop,
        "bot": types.SimpleNamespace(get_channel=lambda i: channel), "seen_bug_reports": set()})
    _run(ns["poll_bug_reports"]())
    (embed,) = channel.sent
    assert embed.description == SHOWN


def test_a_long_bug_report_is_cut_on_the_escaped_text():
    channel = _Sink()

    async def api_get(path, timeout=8.0):
        return {"reports": [{"id": "r2", "bug_number": 8, "display_name": "P", "description": "*" * 2000}]}

    ns = _lift(("poll_bug_reports", "_escape_md", "_escape_text"), HELPER_PARTS, {
        "discord": _discord(), "BUG_REPORTS_CHANNEL_ID": 1, "api_get": api_get, "api_post": _noop,
        "bot": types.SimpleNamespace(get_channel=lambda i: channel), "seen_bug_reports": set()})
    _run(ns["poll_bug_reports"]())
    (embed,) = channel.sent
    more = "... (truncated — full text in F5 admin viewer)"
    assert len(embed.description) <= 1560 and embed.description.endswith(more)
    assert live(embed.description[:-len(more)]) == []


def _bug_events(events):
    user = _Sink()

    async def api_get(path, timeout=8.0):
        return {"events": events}

    ns = _lift(("poll_bug_report_events", "_escape_md", "_escape_text"), HELPER_PARTS, {
        "discord": _discord(), "api_get": api_get, "_post_bug_event_to_thread": _noop,
        "_ack_bug_events": _noop, "seen_bug_events": set(),
        "bot": types.SimpleNamespace(get_user=lambda i: user, fetch_user=_noop)})
    _run(ns["poll_bug_report_events"]())
    return user.sent


def _event(eid, etype, **kw):
    e = {"event_id": eid, "event_type": etype, "bug_number": 9, "reporter_discord_id": "5",
         "reporter_steam_id": "1", "actor_steam_id": "2", "actor_name": "Admin", "description_snippet": ""}
    e.update(kw)
    return e


def test_a_bug_report_dm_shows_the_report_snippet_as_typed():
    (embed,) = _bug_events([_event("e1", "created", description_snippet=TYPED)])
    assert embed.field("Your report") == SHOWN


def test_a_status_change_dm_shows_the_note_as_typed():
    (embed,) = _bug_events([_event("e2", "status_change", old_status="open", new_status="triaged",
                                   comment=TYPED)])
    assert embed.field("Note from Admin") == SHOWN


def test_a_comment_dm_shows_the_comment_as_typed():
    (embed,) = _bug_events([_event("e3", "comment", comment=TYPED)])
    assert embed.field("Admin says") == SHOWN


def _thread_post(event):
    thread = _Sink()

    async def bug_thread_for(channel, bug_num):
        return thread

    ns = _lift(("_post_bug_event_to_thread", "_escape_md", "_escape_text"), HELPER_PARTS, {
        "BUG_REPORTS_CHANNEL_ID": 1, "_bug_thread_for": bug_thread_for,
        "bot": types.SimpleNamespace(get_channel=lambda i: object())})
    _run(ns["_post_bug_event_to_thread"](event))
    (text,) = thread.sent
    return text


def test_a_thread_status_change_shows_the_comment_as_typed():
    text = _thread_post({"event_type": "status_change", "bug_number": 9, "actor_name": "P",
                         "new_status": "resolved", "comment": TYPED})
    assert text == "**P** → **RESOLVED**\n" + SHOWN


def test_a_thread_comment_shows_the_comment_as_typed():
    text = _thread_post({"event_type": "comment", "bug_number": 9, "actor_name": "P", "comment": TYPED})
    assert text == "**P:** " + SHOWN


def test_a_ban_notice_shows_the_reason_as_typed():
    channel = _Sink()

    class _Resp:
        status = 200

        async def json(self):
            return {"bans": [{"id": "b2", "steam_id": "76561198000000001", "display_name": "N",
                              "reason": TYPED, "banned_by_steam_id": "76561198000000002"}]}

    class _Get:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, *a):
            return False

    import datetime as _dt
    ns = _lift(("poll_new_bans", "_ban_end_line", "_escape_text", "_escape_md"), HELPER_PARTS + ("_BAN_END_LINE_UNREAD",), {
        "discord": _discord(), "datetime": _dt.datetime, "http_session": types.SimpleNamespace(get=lambda *a, **k: _Get()),
        "API_SECRET_KEY": "k", "API_BASE_URL": "http://api", "ADMIN_CHANNEL_ID": 3,
        "aiohttp": types.SimpleNamespace(ClientTimeout=lambda **k: None),
        "bot": types.SimpleNamespace(get_channel=lambda i: channel),
        "_last_ban_id_posted": "b1", "_ban_poller_initialized": True})
    _run(ns["poll_new_bans"]())
    (embed,) = channel.sent
    assert "\nReason: **" + SHOWN + "**\n" in embed.description, embed.description


# =============================================================================
# Stage 2: the class complete (BOT-TEXT-ESCAPE-1)
# =============================================================================

import sys  # noqa: E402

API_DIR = os.path.abspath(os.path.join(os.path.dirname(SRC), "api"))
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)
import discord_text  # noqa: E402

NAME = _lift(("_escape_md",))["_escape_md"]


# -- the api's copy of the two helpers is the bot's, case for case --------------

# Names that hold an address (stage 3): the name helpers put a zero-width
# space after every scheme's colon, so a name is never a link.
ZW = "​"
NAME_ADDRESS_CASES = [
    ("http-at-start", "http://x.example", "http:" + ZW + "//x.example"),
    ("https-in-middle", "see https://y.example now", "see https:" + ZW + "//y.example now"),
    ("upper-case", "HTTPS://Z.EXAMPLE", "HTTPS:" + ZW + "//Z.EXAMPLE"),
    ("mixed-case-one-slash", "HtTp:/one", "HtTp:" + ZW + "/one"),
    ("two-addresses", "a http://b and https://c", "a http:" + ZW + "//b and https:" + ZW + "//c"),
    ("address-with-marks", "[go](https://e.example/a_b)", "\\[go\\](https:" + ZW + "//e.example/a\\_b)"),
    # FIX-1 (L4): every address scheme, not only http and https
    ("any-scheme", "httpx://a and http:x", "httpx:" + ZW + "//a and http:x"),
    ("ftp", "ftp://x.example", "ftp:" + ZW + "//x.example"),
    ("steam", "steam://run/1557740", "steam:" + ZW + "//run/1557740"),
    ("scheme-with-marks", "a+b.c-d://x", "a+b.c-d:" + ZW + "//x"),
    ("one-slash", "File:/x", "File:" + ZW + "/x"),
    ("no-slash-no-break", "mailto:x and 12:/y", "mailto:x and 12:/y"),
]
NAME_TEXTS = ([c[1] for c in CASES] + CUT_TEXTS + ["@everyone", "<@123>", "a\r\nb", "  # x", "12) y", ""]
              + [c[1] for c in NAME_ADDRESS_CASES] + ["a" * 10 + "https://q.example", "x" * 37 + "HTTP://z"])


@pytest.mark.parametrize("text", [c[1] for c in CASES] + CUT_TEXTS, ids=range(len(CASES) + len(CUT_TEXTS)))
def test_the_api_text_helper_is_the_bots(text):
    assert discord_text.escape_text(text) == ESC(text)
    for limit in (0, 2, 3, 5, 9, 17, 40, 200):
        assert discord_text.escape_text(text, limit) == ESC(text, limit), limit
        assert discord_text.escape_text(text, limit, more="…") == ESC(text, limit, more="…"), limit


@pytest.mark.parametrize("text", NAME_TEXTS, ids=range(len(NAME_TEXTS)))
def test_the_api_name_helper_is_the_bots(text):
    assert discord_text.escape_name(text) == NAME(text)
    for limit in (0, 2, 3, 5, 9, 17, 40, 200):
        assert discord_text.escape_name(text, limit) == NAME(text, limit), limit


def test_the_cross_check_fails_for_a_changed_api_helper():
    """Control: the api helper with @ left out differs from the bot's on a
    case of the table, so the two tests above would fail."""
    changed = lambda t: discord_text.escape_text(t).replace("\\@", "@")  # noqa: E731
    assert any(changed(c[1]) != ESC(c[1]) for c in CASES)


# -- the name helper ------------------------------------------------------------

def test_the_name_helper_escapes_a_mention_and_cuts_on_the_escaped_text():
    assert NAME("@everyone") == "\\@everyone"
    assert NAME("<@&42> x") == "\\<\\@&42\\> x"
    for n in range(0, 30):
        out = NAME("*" * 40, n)
        assert len(out) <= n
        body = out[:-3] if out.endswith("...") else out
        assert (len(body) - len(body.rstrip("\\"))) % 2 == 0, (n, out)
    assert NAME("abc", 10) == "abc"


# -- a name is never a link (stage 3: the scheme break is in both name helpers) --

@pytest.mark.parametrize("text,want", [c[1:] for c in NAME_ADDRESS_CASES], ids=[c[0] for c in NAME_ADDRESS_CASES])
def test_a_name_holding_an_address_is_never_a_link_in_either_helper(text, want):
    assert NAME(text) == want
    assert discord_text.escape_name(text) == want


@pytest.mark.parametrize("text", ["a" * 10 + "https://q.example", "x" * 37 + "HTTP://z", "http://" * 9,
                                  "_" * 20 + "ftp://f.example", "steam://" * 5],
                         ids=["middle", "edge", "many", "ftp", "steam"])
def test_the_scheme_break_holds_at_every_cut(text):
    """The break is made before the cut: at every limit the result fits,
    keeps no scheme followed by a slash, and ends inside no pair."""
    for helper in (NAME, discord_text.escape_name):
        for n in range(0, len(text) + 12):
            out = helper(text, n)
            assert len(out) <= n, (n, out)
            assert re.search(r"(?i)[a-z]:/", out) is None, (n, out)
            body = out[:-3] if out.endswith("...") else out
            assert (len(body) - len(body.rstrip("\\"))) % 2 == 0, (n, out)


def test_free_text_keeps_an_address_whole():
    for helper in (ESC, discord_text.escape_text):
        assert helper("see https://y.example now") == "see https://y.example now"
        assert ZW not in helper("HTTP://Z http:/x")


def test_the_scheme_break_control_fails_without_the_break():
    """Failing-first control: a name helper without the break (its output
    with the zero-width spaces taken out) fails every address case."""
    for _id, text, want in NAME_ADDRESS_CASES:
        if ZW in want:
            assert NAME(text).replace(ZW, "") != want


# -- A1 mail: the bot reads the raw value when the api serves it ---------------

MAIL_FUNCS = ("_mail_sent_line", "_escape_md", "_escape_text", "_mail_legacy_plain")
MAIL_PARTS = HELPER_PARTS + ("MAIL_NAME_SHOWN_MAX", "MAIL_SUBJECT_SHOWN_MAX")


def _sent_line(info):
    return _lift(MAIL_FUNCS, MAIL_PARTS)["_mail_sent_line"](info)


def test_mail_new_api_the_raw_values_are_escaped_once_by_the_bot():
    out = _sent_line({"known": True, "sender_name": "OLD", "subject": "OLD",
                      "sender_name_raw": "*Bob* @here", "subject_raw": TYPED})
    assert out.endswith("**\\*Bob\\* \\@here** — *%s*" % SHOWN), out
    assert "OLD" not in out


def test_mail_old_api_the_escaped_fields_show_as_before():
    """An api without the raw fields: the name is taken back to its typed
    text and passes _escape_md once, the subject is the api's own escaped
    field, unchanged."""
    out = _sent_line({"known": True, "sender_name": "Bob", "subject": "the api's \\*escaped\\* text"})
    assert out.endswith("**Bob** — *the api's \\*escaped\\* text*"), out


def _mailpick_labels(threads):
    class _Button:
        def __init__(self, **kw):
            self.kw = kw

    class _View:
        def __init__(self, timeout=None):
            self.items = []

        def add_item(self, item):
            self.items.append(item)

    disc = types.SimpleNamespace(ui=types.SimpleNamespace(View=_View, Button=_Button),
                                 ButtonStyle=types.SimpleNamespace(secondary=2))
    view = _lift(("_mailpick_view", "_mail_legacy_plain"), (), {"discord": disc})["_mailpick_view"](threads)
    return [i.kw["label"] for i in view.items]


def test_a_mail_button_label_is_the_raw_text_cut_to_80():
    """A3: a button label renders no markdown, so it gets the typed text, no
    backslash, cut to Discord's 80 -- from an older api's escaped fields
    too (FIX-1, M1)."""
    (label,) = _mailpick_labels([{"relay_code": "SCR-A", "sender_name": "x\\_y", "subject": "s",
                                  "sender_name_raw": "x_y*", "subject_raw": "#" * 200}])
    assert label == ("x_y* — " + "#" * 200)[:80] and len(label) == 80 and "\\" not in label
    (old,) = _mailpick_labels([{"relay_code": "SCR-A", "sender_name": "x\\_y", "subject": "s"}])
    assert old == "x_y — s"


def test_the_mail_pick_list_reads_the_raw_values():
    sent = []

    class _Chan:
        async def send(self, content=None, **kw):
            sent.append(content)
            return None

    async def threads(discord_id):
        return [{"relay_code": "SCR-A", "sender_name": "OLD", "subject": "OLD",
                 "sender_name_raw": "_Al_", "subject_raw": "<@1> hi"}]

    class _Button:
        def __init__(self, **kw):
            pass

    class _View:
        def __init__(self, timeout=None):
            pass

        def add_item(self, item):
            pass

    disc = types.SimpleNamespace(ui=types.SimpleNamespace(View=_View, Button=_Button),
                                 ButtonStyle=types.SimpleNamespace(secondary=2))
    ns = _lift(("_ask_which_mail", "_mailpick_view", "_escape_md", "_escape_text", "_mail_legacy_plain"), MAIL_PARTS,
               {"discord": disc, "_relay_threads": threads, "_mailpick": {}, "_MAILPICK_MAX": 50})
    _run(ns["_ask_which_mail"](None, "b", discord_id=1, channel=_Chan(), source_message_id=None))
    (text,) = sent
    assert "**\\_Al\\_** — *\\<\\@1\\> hi* · `SCR-A`" in text and "OLD" not in text, text


# -- A2 free text: in-game chat, the LFP message --------------------------------

class _Emoji:
    def __init__(self, name, eid):
        self.name, self.id = name, eid

    def __str__(self):
        return "<:%s:%d>" % (self.name, self.id)


def _lfp(text, limit=1500, emojis=()):
    ns = _lift(("_lfp_render_message", "_escape_text"), HELPER_PARTS + ("_LFP_EMOJI_TOKEN",))
    return ns["_lfp_render_message"](text, types.SimpleNamespace(emojis=list(emojis)), limit)


def test_the_lfp_message_is_shown_as_typed():
    assert _lfp(TYPED) == SHOWN
    out = _lfp("gg :pog_champ: *x*", emojis=[_Emoji("pog_champ", 7)])
    assert out == "gg <:pog_champ:7> \\*x\\*", out


def test_a_long_lfp_message_is_cut_on_the_escaped_text():
    for n in (10, 11, 12, 50, 1500):
        out = _lfp("*" * 3000, n)
        assert len(out) <= n and out.endswith("...") and live(out[:-3]) == [], (n, out)
    out = _lfp("ab :e: " + "*" * 50, 12, emojis=[_Emoji("e", 1)])
    assert len(out) <= 12 and live(out.replace("<:e:1>", "")[:-3]) == [], out


def test_the_flag_embed_text_is_cut_on_the_escaped_text():
    fn = _lift(("_flag_embed_text", "_escape_text"), HELPER_PARTS)["_flag_embed_text"]
    out = fn("_" * 900)
    assert len(out) <= 850 and live(out[:-3]) == []
    assert fn(None) == "not recorded"


# -- A3 plain slots: the raw text, cut to the slot's limit ----------------------

def test_a_bug_report_thread_name_is_raw_and_cut_to_100():
    names = []

    class _Msg:
        async def create_thread(self, name=None, **kw):
            names.append(name)

    class _Chan:
        async def send(self, content=None, embed=None, **kw):
            return _Msg()

    async def api_get(path, timeout=8.0):
        return {"reports": [{"id": "r9", "bug_number": 9, "display_name": "_x_*" * 30, "severity": "low",
                             "category": "ui" * 60, "description": "d"}]}

    ns = _lift(("poll_bug_reports", "_escape_md", "_escape_text"), HELPER_PARTS, {
        "discord": _discord(), "BUG_REPORTS_CHANNEL_ID": 1, "api_get": api_get, "api_post": _noop,
        "bot": types.SimpleNamespace(get_channel=lambda i: _Chan()), "seen_bug_reports": set()})
    _run(ns["poll_bug_reports"]())
    (name,) = names
    assert len(name) == 100 and "\\" not in name and name.startswith("#9 " + ("_x_*" * 10))


class _Option:
    def __init__(self, label=None, value=None, description=None, **kw):
        self.label, self.value, self.description = label, value, description


def _select(cls, *args):
    """A select class of the bot built over a fake Select: its options."""
    got = {}

    class _Select:
        def __init__(self, **kw):
            got.update(kw)

    disc = types.SimpleNamespace(ui=types.SimpleNamespace(Select=_Select), SelectOption=_Option,
                                 Interaction=object)
    node = [n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == cls][0]
    node = copy.deepcopy(node)
    node.decorator_list = []
    ns = {"discord": disc, "re": re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), SRC, "exec"), ns)
    try:
        ns[cls](*args)
    except Exception:
        pass                    # past the options: only they are looked at
    return got.get("options") or []


def test_an_ffa_bet_select_label_is_the_raw_name_cut_to_100():
    (opt,) = _select("FfaBetSelect", "L1", 1, [{"steam_id": "7", "name": "*" * 150, "odds": 2.0, "rating": 1}])
    assert opt.label == "*" * 100


def test_a_lobby_bet_select_label_is_the_raw_label_cut_to_100():
    (opt,) = _select("LobbyBetSelect", "ffa", "L1", [{"value": "v", "label": "_" * 150, "description": "`d`"}])
    assert opt.label == "_" * 100 and opt.description == "`d`"


# -- A4 api-composed texts: the typed parts are escaped where the text is built --

def _api_source(name):
    return open(os.path.join(API_DIR, name), encoding="utf-8").read()


def test_a_relayed_mail_dm_shows_every_typed_part_as_typed():
    import mail_discord
    out = mail_discord.relay_dm_text(None, sender_name="<@1> *Bob*", sender_steam_id="7",
                                     subject="@everyone [x](https://e.example)", body=TYPED,
                                     code="SCR-ABCDEFGHJKMN")
    assert "**\\<\\@1\\> \\*Bob\\***" in out, out
    assert "**\\@everyone \\[x\\](https://e.example)**" in out, out
    assert SHOWN in out, out


def _lift_api(path, funcs):
    tree = ast.parse(_api_source(path))
    picked = [copy.deepcopy(n) for n in tree.body
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in funcs]
    for n in picked:
        n.decorator_list = []
    ns = {"_dtext": discord_text, "_re": re, "re": re}
    exec(compile(ast.Module(body=picked, type_ignores=[]), path, "exec"), ns)
    return ns


def test_a_stream_post_name_follows_the_shared_name_rule():
    fn = _lift_api("main.py", ("_stream_md_escape",))["_stream_md_escape"]
    for s in NAME_TEXTS:
        assert fn(s) == discord_text.escape_name(discord_text.flat(s)), s
    # moved in stage 3: the name helper now breaks the address scheme (a name is never a link)
    assert fn("[watch](https://evil.example)") == "\\[watch\\](https:" + ZW + "//evil.example)"
    assert fn("watch  HTTP://evil.example\nnow") == "watch HTTP:" + ZW + "//evil.example now"


def _string_parts(tree):
    """(constant text, enclosing function name) for every string constant
    and every literal part of an f-string; docstrings are left out."""
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            docs.add(id(body[0].value))
        # a regular expression's pattern finds mention text (to take it out); it writes none
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args \
                and node.func.attr in ("sub", "subn", "compile", "search", "match", "fullmatch",
                                       "findall", "finditer", "split"):
            docs.add(id(node.args[0]))
    out = []

    def walk(node, fn):
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            if isinstance(child, ast.Constant) and isinstance(child.value, str) and id(child) not in docs:
                out.append((child.value, fn))
            walk(child, inner)
    walk(tree, None)
    return out


def _mention_writers():
    found = []
    for name in sorted(os.listdir(API_DIR)):
        if not name.endswith(".py"):
            continue
        for text, fn in _string_parts(ast.parse(_api_source(name))):
            # Discord's mention forms: <@id> <@!id> <@&id> <#id> </name:id>, @everyone,
            # @here -- a form ending a literal part is an f-string writing the id after it.
            for m in re.finditer(r"<@[!&]?(?=\d|$)|<#(?=\d|$)|</[\w-]+:(?=\d|$)|@everyone|@here", text):
                found.append((name, fn, m.group(0)))
    return found


def test_the_api_writes_a_user_mention_in_one_place_only():
    """Channel posts are sent with user mentions allowed. The only mention
    the api writes is _confirmed_mentions's, from stored digit-only Discord
    ids; every typed value in a composed text passes discord_text, which
    escapes every < and @. So typed text cannot add a mention."""
    assert _mention_writers() == [("tournaments.py", "_confirmed_mentions", "<@")]
    assert "isdigit()" in ast.get_source_segment(
        _api_source("tournaments.py"),
        [n for n in ast.parse(_api_source("tournaments.py")).body
         if getattr(n, "name", "") == "_confirmed_mentions"][0])
    for typed in ("<@1>", "<@!1>", "<@&1>", "<#1>", "</x:1>", "@everyone", "@here"):
        for helper in (discord_text.escape_text, discord_text.escape_name):
            shown = helper(typed)
            assert "<@" not in shown.replace("\\<\\@", "") and "@e" not in shown.replace("\\@", "")
            assert re.search(r"(?<!\\)[<@]", shown) is None, (typed, shown)


_SPANS = {}


def _parse(path, source, names):
    """The top-level functions and assignments called `names` of one api
    file, or of a changed copy of it with the same number of lines: the
    file as it stands is parsed once to find their lines, and only those
    lines of `source` are parsed (line numbers kept), so a copy with one
    call changed costs no parse of the whole file."""
    if path not in _SPANS:
        spans = {}
        for n in ast.parse(_api_source(path)).body:
            targets = [n.name] if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) else \
                [t.id for t in n.targets if isinstance(t, ast.Name)] if isinstance(n, ast.Assign) else []
            for t in targets:
                spans.setdefault(t, []).append((n.lineno, n.end_lineno))
        _SPANS[path] = spans
    lines = source.split("\n")
    assert len(lines) == _api_source(path).count("\n") + 1, "a mutant must keep the file's line count"
    body = []
    for name in names:
        for start, end in _SPANS[path].get(name, []):
            part = ast.parse("\n".join(lines[start - 1:end]))
            ast.increment_lineno(part, start - 1)
            body.extend(part.body)
    return ast.Module(body=body, type_ignores=[])


def _lift_src(path, source, funcs=(), assigns=(), extra=None):
    """Functions and named assignments of one api file (or a changed copy of
    its source), run in a namespace of their own."""
    tree = _parse(path, source, tuple(funcs) + tuple(assigns))
    picked = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in funcs:
            n = copy.deepcopy(n)
            n.decorator_list = []
            picked.append(n)
        elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in assigns for t in n.targets):
            picked.append(n)
    ns = {"_dtext": discord_text, "_re": re, "re": re, "os": os}
    ns.update(extra or {})
    exec(compile(ast.Module(body=picked, type_ignores=[]), path, "exec"), ns)
    return ns


# -- L1: each composer's own output; a removed helper fails its own composer ---
#
# A composer's text is the outermost f-string or concatenation around a
# marker of its own, evaluated with the plain (not awaited) assignments of its
# function that the text reads, in source order, and fake inputs for the rest.
# Each composer is checked for the exact once-escaped form of every typed part;
# each helper call taken out of a copy of the source (a mutant per helper) must
# fail that composer's check, and a doubled call must fail it too.

TYPED_NAME = "*Bob* <@1> @here_x"
TYPED_LINES = "**hi** <@&2>\n# head\n@everyone"


def _compose(path, func, marker, inputs, source=None):
    source = _api_source(path) if source is None else source
    tree = _parse(path, source, (func,))
    (fn,) = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func]
    parents = {c: n for n in ast.walk(fn) for c in ast.iter_child_nodes(n)}
    hits = [n for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str) and marker in n.value]
    assert len(hits) == 1, (func, marker, len(hits))
    node = hits[0]
    while isinstance(parents.get(node), (ast.JoinedStr, ast.BinOp, ast.FormattedValue, ast.IfExp)):
        node = parents[node]
    needed = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    assigns = [s for s in ast.walk(fn) if isinstance(s, ast.Assign) and len(s.targets) == 1
               and isinstance(s.targets[0], ast.Name) and s.lineno < node.lineno
               and not any(isinstance(x, ast.Await) for x in ast.walk(s))]
    chosen, grew = [], True
    while grew:
        grew = False
        for s in assigns:
            if s not in chosen and s.targets[0].id in needed and s.targets[0].id not in inputs:
                chosen.append(s)
                needed |= {n.id for n in ast.walk(s.value) if isinstance(n, ast.Name)}
                grew = True
    ns = {"_dtext": discord_text, "_re": re, "re": re}
    ns.update(inputs)
    for s in sorted(chosen, key=lambda s: s.lineno):
        exec(compile(ast.Module(body=[s], type_ignores=[]), path, "exec"), ns)
    return eval(compile(ast.Expression(body=node), path, "eval"), ns)


def _row(**kw):
    return dict(kw)


N64, N80, N128 = (discord_text.escape_name(TYPED_NAME, n) for n in (64, 80, 128))
QUOTED = "\n".join("> " + ln for ln in discord_text.escape_text(TYPED_LINES, 300).split("\n"))
COSMETIC = {"row": _row(name=TYPED_NAME), "note": TYPED_LINES, "render_scale": 1.0,
            "render_offset_x": 0.0, "render_offset_y": 0.0}

# (id, file, function, marker, inputs, the once-escaped parts, the helper calls a mutant takes out)
COMPOSERS = [
    ("chat-strike", "main.py", "_chat_censor_strike", "Auto-mod",
     {"message": TYPED_LINES, "display_name": TYPED_NAME, "steam_id": "7", "channel": "global", "minutes": 5,
      "offenses": 0, "matched": "x"},
     [N128, discord_text.escape_text(TYPED_LINES, 400)],
     ['_dtext.escape_text(message or "", 400)', '_dtext.escape_name(display_name or steam_id or "?", 128)']),
    ("admin-alert", "main.py", "admin_alert_create", "Server alert",
     {"msg": TYPED_LINES, "admin_name": TYPED_NAME, "req": types.SimpleNamespace(category="ops")},
     [N128, discord_text.escape_text(TYPED_LINES)],
     ["_dtext.escape_text(msg)", "_dtext.escape_name(str(admin_name), 128)"]),
    ("mail-spam", "main.py", "_mail_spam_case", "Mail spam",
     {"sender": _row(display_name=TYPED_NAME, steam_id="7"), "same_body": 1, "bulk_hour": 0, "censor_hits": 0,
      "subject": TYPED_LINES, "MAIL_SPAM_BULK_RECIPIENTS": 10},
     [N64, discord_text.escape_text(discord_text.flat(TYPED_LINES), 120)],
     ["_dtext.escape_name(sender.get('display_name') or '?', 64)",
      "_dtext.escape_text(_dtext.flat(subject), 120)"]),
    ("mail-report", "main.py", "mail_report", "Mail report",
     {"row": _row(sender_name=TYPED_NAME, sender_steam_id="7", subject=TYPED_LINES, body=TYPED_LINES),
      "me": _row(display_name=TYPED_NAME), "reason": TYPED_LINES},
     ["**%s** (`7`) reported by **%s**" % (N64, N64), discord_text.escape_text(discord_text.flat(TYPED_LINES), 120),
      QUOTED, discord_text.escape_text(discord_text.flat(TYPED_LINES), 200)],
     ["_dtext.escape_name(row['sender_name'] or '?', 64)", "_dtext.escape_name(me.get('display_name') or '?', 64)",
      "_dtext.escape_text(_dtext.flat(row['subject']), 120)", '_dtext.escape_text(row["body"] or "", 300)',
      "_dtext.escape_text(_dtext.flat(reason), 200)"]),
    ("cosmetic-placement-denied", "main.py", "_admin_cosmetic_review_impl",
     "Your last approved placement remains active. Reason: ", COSMETIC,
     ['"%s"' % N80, discord_text.escape_text(TYPED_LINES)], []),
    ("cosmetic-denied", "main.py", "_admin_cosmetic_review_impl", '" was not approved. Reason: ', COSMETIC,
     ['"%s"' % N80, discord_text.escape_text(TYPED_LINES)], []),
    ("cosmetic-placement-approved", "main.py", "_admin_cosmetic_review_impl",
     "Your last published placement remains active", COSMETIC, ['"%s"' % N80], []),
    ("cosmetic-approved", "main.py", "_admin_cosmetic_review_impl", "after its art and reviewed placement",
     COSMETIC, ['"%s"' % N80], []),
    ("tournament-kick", "tournaments.py", "lock_tournament", "that couldn't make the agreed time: ",
     {"_kind_label": lambda k: "Synchronized", "_dts": lambda s: "Sat", "winning_slot": 1, "kicked": [1, 2],
      "kicked_names": [TYPED_NAME, None], "t": types.SimpleNamespace(kind="sync"),
      "_kicked_names_text": lambda names: _kick_names(None)(names)},
     ["%s, unknown. " % N64], []),
]
# The cosmetic DMs' helper calls, one mutant each (the same text at four sites:
# each mutant takes out one site's call, found by its own marker line).
COSMETIC_MUTANTS = [
    ("cosmetic-placement-denied", "Your placement change for \"{_dtext.escape_name(row[\"name\"], 80)}\" was not approved",
     "Your placement change for \"{row[\"name\"]}\" was not approved"),
    ("cosmetic-placement-denied", "remains active. Reason: {_dtext.escape_text(note)}\"",
     "remains active. Reason: {note}\""),
    ("cosmetic-denied", "Your cosmetic \"{_dtext.escape_name(row[\"name\"], 80)}\" was not approved",
     "Your cosmetic \"{row[\"name\"]}\" was not approved"),
    ("cosmetic-denied", "was not approved. Reason: {_dtext.escape_text(note)}'",
     "was not approved. Reason: {note}'"),
    ("cosmetic-placement-approved", "Your placement change for \"{_dtext.escape_name(row[\"name\"], 80)}\" was approved",
     "Your placement change for \"{row[\"name\"]}\" was approved"),
    ("cosmetic-approved", "Your cosmetic \"{_dtext.escape_name(row[\"name\"], 80)}\" was approved",
     "Your cosmetic \"{row[\"name\"]}\" was approved"),
]


def _kick_names(source):
    src = _api_source("tournaments.py") if source is None else source
    return _lift_src("tournaments.py", src, ("_kicked_names_text",), ("KICK_NAMES_MAX",))["_kicked_names_text"]


def _composer_ok(out, parts):
    return isinstance(out, str) and all(p in out for p in parts) and "*Bob*" not in out \
        and re.search(r"(?<!\\)[<@]", out.replace("<t:", "")) is None


def _run_composer(cid, source=None):
    (c,) = [c for c in COMPOSERS if c[0] == cid]
    return _compose(c[1], c[2], c[3], c[4], source)


@pytest.mark.parametrize("cid", [c[0] for c in COMPOSERS])
def test_each_composer_shows_every_typed_part_escaped_once(cid):
    (c,) = [c for c in COMPOSERS if c[0] == cid]
    out = _run_composer(cid)
    assert _composer_ok(out, c[5]), out


def _mutants():
    out = []
    for cid, path, _f, _m, _i, _p, calls in COMPOSERS:
        for call in calls:      # the call replaced by its first argument: the helper taken out
            out.append((cid, path, call, "(" + ast.unparse(ast.parse(call, mode="eval").body.args[0]) + ")"))
    for cid, old, new in COSMETIC_MUTANTS:
        out.append((cid, "main.py", old, new))
    # a doubled pass is caught as well as a missing one
    out.append(("mail-report", "main.py", "_dtext.escape_name(row['sender_name'] or '?', 64)",
                "_dtext.escape_name(_dtext.escape_name(row['sender_name'] or '?'), 64)"))
    out.append(("tournament-kick", "tournaments.py", 'part = _dtext.escape_name(n, 64) if n else "unknown"',
                'part = n if n else "unknown"'))
    return out


@pytest.mark.parametrize("cid,path,old,new", _mutants(), ids=["%s-%d" % (m[0], i) for i, m in enumerate(_mutants())])
def test_a_removed_or_doubled_helper_fails_its_own_composer(cid, path, old, new):
    src = _api_source(path)
    assert src.count(old) == 1, old
    mutated = src.replace(old, new, 1)
    (c,) = [c for c in COMPOSERS if c[0] == cid]
    if cid == "tournament-kick":
        names = _kick_names(mutated)([TYPED_NAME, None])
        assert not _composer_ok(names + ". ", c[5]), names
        return
    assert not _composer_ok(_run_composer(cid, mutated), c[5])


def test_the_relayed_mail_dm_fails_without_each_of_its_helpers():
    """relay_dm_text (mail_discord.py) is called whole: a copy of the module
    with one helper call taken out shows that part raw."""
    src = _api_source("mail_discord.py")
    calls = ['_dtext.escape_name(_dtext.flat(sender_name) or "?", RELAY_NAME_MAX)',
             '_dtext.escape_text(_dtext.flat(subject) or "(no subject)", RELAY_SUBJECT_MAX)',
             "_dtext.escape_text(_relay_body_layout(body), max(0, min(RELAY_BODY_MAX, budget)))"]
    raw = ['(_dtext.flat(sender_name) or "?")', '(_dtext.flat(subject) or "(no subject)")',
           "(_relay_body_layout(body))"]
    for old, new in zip(calls, raw):
        assert src.count(old) == 1, old
        ns = {"__name__": "mail_discord_mutant"}
        exec(compile(src.replace(old, new, 1), "mail_discord.py", "exec"), ns)
        out = ns["relay_dm_text"](None, sender_name=TYPED_NAME, sender_steam_id="7", subject=TYPED_LINES,
                                  body=TYPED_LINES, code="SCR-ABCDEFGHJKMN")
        assert "*Bob*" in out or "<@" in out or "\n@everyone" in out, (old, out)


def test_the_tournament_kick_list_stays_inside_one_message():
    """L3, the class: a post built from N escaped names packs whole names
    within KICK_NAMES_MAX and says how many more."""
    fn = _kick_names(None)
    out = fn(["_*" * 40] * 100)
    assert len(out) <= 1500 + len(" and 100 more") and out.endswith(" more"), len(out)
    assert out.count(discord_text.escape_name("_*" * 40, 64)) >= 1
    assert fn(["a", "b"]) == "a, b"


def test_no_api_composer_puts_mention_or_link_syntax_against_a_typed_value():
    """B, the api half: no f-string of main.py, tournaments.py or
    mail_discord.py has a constant part ending in @, #, <@&, [ or a backtick
    directly before a value that passes discord_text."""
    found = []
    for name in ("main.py", "tournaments.py", "mail_discord.py"):
        for node in ast.walk(ast.parse(_api_source(name))):
            if not isinstance(node, ast.JoinedStr):
                continue
            for a, b in zip(node.values, node.values[1:]):
                if isinstance(a, ast.Constant) and isinstance(b, ast.FormattedValue) \
                        and str(a.value).endswith(("@", "#", "<@&", "[", "`")) \
                        and "_dtext." in ast.unparse(b.value):
                    found.append((name, node.lineno, a.value[-3:]))
    assert found == []


# -- M4: the stream's live, matchup and final composers -------------------------

STREAM_FUNCS = ("_stream_post_content", "_stream_md_escape", "_stream_mode_label", "_stream_matchup_line",
                "_stream_ended_content")
STREAM_ASSIGNS = ("BROADCAST_TWITCH_URL", "BROADCAST_YOUTUBE_URL", "_STREAM_MODE_LABELS",
                  "BROADCAST_TWITCH_VODS_URL", "BROADCAST_YOUTUBE_VODS_URL", "_STREAM_MATCHUP_NAMES_MAX")


def _stream(source=None):
    src = _api_source("main.py") if source is None else source
    return _lift_src("main.py", src, STREAM_FUNCS, STREAM_ASSIGNS)


STREAM_CANDIDATE = {"names": ["_Bob_", "x*y"], "ratings": [1500, 0], "mode": "1v1"}
BOB = "**%s** (1500)" % discord_text.escape_name("_Bob_")


def _stream_ok(ns):
    live = ns["_stream_post_content"](STREAM_CANDIDATE, None)
    line = ns["_stream_matchup_line"](STREAM_CANDIDATE)
    final = ns["_stream_ended_content"](None, None, [line])
    return (BOB in live and "**x\\*y**" in live and BOB in line and "**x\\*y**" in line
            and "• " + line in final and final.count(BOB) == 1 and "\\\\" not in final)


def test_the_stream_posts_show_each_name_escaped_once():
    """The live post and each stored matchup line escape every name once;
    the final post shows the stored lines as they stand (no second pass)."""
    assert _stream_ok(_stream())


STREAM_MUTANTS = [
    ("live helper removed", '            n = _stream_md_escape(str(names[i])[:24]) if i < len(names) else "?"',
     '            n = str(names[i])[:24] if i < len(names) else "?"'),
    ("matchup helper removed",
     '        n = _stream_md_escape(str(names[i])[:24]) if i < len(names) else "?"\n        try:',
     '        n = str(names[i])[:24] if i < len(names) else "?"\n        try:'),
    ("final pass doubled", "    lines = [str(m) for m in (matchups or []) if str(m).strip()]",
     "    lines = [_stream_md_escape(str(m)) for m in (matchups or []) if str(m).strip()]"),
]


@pytest.mark.parametrize("old,new", [m[1:] for m in STREAM_MUTANTS], ids=[m[0] for m in STREAM_MUTANTS])
def test_a_stream_composer_mutant_fails(old, new):
    src = _api_source("main.py")
    assert src.count(old) == 1, old
    assert not _stream_ok(_stream(src.replace(old, new, 1)))


def test_a_stored_matchup_line_keeps_whole_names():
    """Many names: whole escaped names within the budget, then a count;
    no cut inside an escape pair or a bold pair."""
    ns = _stream()
    line = ns["_stream_matchup_line"]({"names": ["_*" * 12] * 30, "ratings": [], "mode": "ffa"})
    assert line.count("**") % 2 == 0 and "more" in line and len(line) <= 200, line
    body = line.rsplit(", +", 1)[0]
    assert (len(body) - len(body.rstrip("\\"))) % 2 == 0


# -- the bot's sites fixed in round 1 --------------------------------------------

def test_the_opponent_relay_shows_the_message_as_typed():
    bodies, replies = [], []

    async def dm_user(uid, body):
        bodies.append(body)
        return True

    class _Ctx:
        author = types.SimpleNamespace(id=1, global_name="*S*", name="s")

        async def reply(self, text, **kw):
            replies.append(text)

    ns = _lift(("dm_opponent", "_escape_md", "_escape_text"), HELPER_PARTS, {
        "_find_active_opponent_discord_id": lambda cid: ("9", "_Opp_"), "_dm_opponent_rate_ok": lambda c: True,
        "_dm_user": dm_user, "_DM_OPPONENT_LIMIT": 8, "_DM_OPPONENT_WINDOW_SECS": 60})
    _run(ns["dm_opponent"](_Ctx(), message=TYPED))
    assert bodies == ["**[Tournament Relay from \\*S\\*]** " + SHOWN], bodies
    assert replies == ["Relayed to \\_Opp\\_."]


def test_the_elo_refusal_shows_discord_names_as_typed():
    sent = []

    class _Ctx:
        async def send(self, text, **kw):
            sent.append(text)

    ns = _lift(("_elo_refused", "_escape_md"))
    assert _run(ns["_elo_refused"](_Ctx(), ["@everyone", "https://x.example"], False)) is True
    (text,) = sent
    assert text.endswith("**\\@everyone**, **https:" + ZW + "//x.example**"), text


def test_a_discord_name_after_an_at_sign_passes_the_helper_with_it():
    """B: the at-sign and the name pass the name helper as one string."""
    fn = _lift(("_beacon_discord_suffix", "_escape_md"))["_beacon_discord_suffix"]
    assert fn({"discord_display_name": "everyone"}) == "  ·  Discord: \\@everyone"
    assert fn({"discord_display_name": "a_b"}) == "  ·  Discord: \\@a\\_b"
    assert shown(fn({"discord_display_name": "here"}).split(": ", 1)[1]) == "@here"
    assert "@{_escape_md(" not in TEXT and "**@{" not in TEXT


def test_the_digest_names_pass_the_name_helper():
    """C: the held-report digest's escape is a thin call of _escape_md; its
    limits apply to the escaped text."""
    ns = _lift(("_qdig_md", "_qdig_esc", "_escape_md"), ("QDIG_NAME_MAX",))
    for s in ["https://x.example", "*Bob* <@1>", "_" * 40, "ftp://a", "line\nbreak\x07bell"]:
        flat = " ".join("".join(c if c.isprintable() else " " for c in s).split())
        assert ns["_qdig_esc"](s) == NAME(flat, ns["QDIG_NAME_MAX"]), s
        assert len(ns["_qdig_md"](s, 12)) <= 12
    assert ns["_qdig_esc"]("") == "unknown player"


RELEASE = {"tag_name": "v1.0", "name": "@everyone *x* https://y.example", "body": "**notes** <@1>\n- item",
           "html_url": "https://github.com/o/r/releases/tag/v1.0"}


def test_a_release_title_passes_the_name_helper_and_the_body_shows_as_written():
    """D: the title is one line with no markup intent; the body is the
    project's release notes, shown as written."""
    ns = _lift(("_format_release_message", "_release_url", "_release_footer", "_escape_md"),
               ("RELEASE_CONT_MARK", "_RELEASE_FOOTER_MARK"), {"GITHUB_RELEASES_REPO": "o/r"})
    (msg,) = ns["_format_release_message"](RELEASE)
    assert msg.startswith("**\N{ROCKET} New release: \\@everyone \\*x\\* https:" + ZW + "//y.example**\n"), msg
    assert "\n**notes** <@1>\n- item" in msg


def test_a_release_post_notifies_nobody():
    sent = []

    class _Ch:
        async def send(self, content, **kw):
            sent.append(kw)

    async def _sleep(s):
        return None

    state = {}
    ns = _lift(("_send_release_chunks_locked",), (), {
        "discord": _discord(), "RELEASES_CHANNEL_ID": 1, "bot": types.SimpleNamespace(get_channel=lambda i: _Ch()),
        "_release_state_load": lambda: dict(state), "_release_state_save": lambda d: state.update(d),
        "asyncio": types.SimpleNamespace(sleep=_sleep)})
    assert _run(ns["_send_release_chunks_locked"]("v1", ["a", "b"])) is True
    assert sent == [{"allowed_mentions": "none"}] * 2


# -- M1: one pass of the name in every mix of old and new api and bot -----------
#
# The rollout order is the primary api, the standby api, then the bot. The bot
# before this change, as deployed (its name helper and its confirmation line,
# copied from main at 51ead083), stands here as text so the mixes with an older
# bot are run, not argued.

OLD_BOT = r'''
def _escape_md(text) -> str:
    one_line = re.sub(r"\r\n|[\n\r\v\f\x1c-\x1e\x85  ]", " ", str(text))
    escaped = re.sub(r"([\\*_~|`\[\]<>])", r"\\\1", one_line)
    escaped = re.sub(r"^(\s*)([#+-])", r"\1\\\2", escaped)
    return re.sub(r"^(\s*\d+)([.)])", r"\1\\\2", escaped)


def _mail_sent_line(info):
    if not (info or {}).get("known"):
        return "✉️ Sent your reply."
    who = (info.get("sender_name") or "").strip() or "them"
    subj = (info.get("subject") or "").strip() or "(no subject)"
    return "✉️ Sent your reply to **%s** — *%s*" % (_escape_md(who), subj)
'''
MIX_NAME = "x_y *z* @everyone <@1>"


def _old_bot_line(info):
    ns = {"re": re}
    exec(OLD_BOT, ns)
    return ns["_mail_sent_line"](info)


def _old_api_name(name):
    """The older api's sender_name: main.py's _mail_discord_safe, which that
    api served it through (it stands unchanged for the subject)."""
    return _lift_src("main.py", _api_source("main.py"), ("_mail_discord_safe",))["_mail_discord_safe"](name, 64)


def _shown_name(line):
    return shown(line.split("**")[1])


def test_mail_mix_new_api_old_bot_escapes_the_name_once():
    import mail_discord
    line = _old_bot_line({"known": True, "sender_name": mail_discord.older_bot_name(MIX_NAME), "subject": "s"})
    assert _shown_name(line) == "x_y *z* everyone (@1)", line
    assert "\\\\" not in line and "@everyone" not in line and "<@" not in line


def test_mail_mix_old_api_new_bot_escapes_the_name_once():
    legacy = _old_api_name(MIX_NAME)
    assert "\\_" in legacy                                  # the older api's own escape
    out = _sent_line({"known": True, "sender_name": legacy, "subject": "s"})
    assert _shown_name(out) == "x_y *z* everyone (@1)" and "\\\\" not in out, out
    sent = []

    class _Chan:
        async def send(self, content=None, **kw):
            sent.append(content)

    async def threads(discord_id):
        return [{"relay_code": "SCR-A", "sender_name": legacy, "subject": "s"}]

    disc = types.SimpleNamespace(ui=types.SimpleNamespace(View=lambda timeout=None: types.SimpleNamespace(
        add_item=lambda i: None), Button=lambda **kw: kw), ButtonStyle=types.SimpleNamespace(secondary=2))
    ns = _lift(("_ask_which_mail", "_mailpick_view", "_escape_md", "_escape_text", "_mail_legacy_plain"),
               HELPER_PARTS + ("MAIL_NAME_SHOWN_MAX", "MAIL_SUBJECT_SHOWN_MAX"),
               {"discord": disc, "_relay_threads": threads, "_mailpick": {}, "_MAILPICK_MAX": 50})
    _run(ns["_ask_which_mail"](None, "b", discord_id=1, channel=_Chan(), source_message_id=None))
    (text,) = sent
    row = [ln for ln in text.split("\n") if "SCR-A" in ln][0]
    assert _shown_name(row) == "x_y *z* everyone (@1)" and "\\\\" not in row, row
    (label,) = _mailpick_labels([{"relay_code": "SCR-A", "sender_name": legacy, "subject": "s\\_t"}])
    assert label == "x_y *z* everyone (@1) — s_t", label


def test_mail_mix_new_api_new_bot_escapes_the_name_once():
    import mail_discord
    out = _sent_line({"known": True, "sender_name": mail_discord.older_bot_name(MIX_NAME), "subject": "s",
                      "sender_name_raw": MIX_NAME, "subject_raw": "s"})
    assert _shown_name(out) == MIX_NAME and "\\\\" not in out, out


def test_the_mail_pick_list_fits_one_message_after_escaping():
    """L3: five threads whose names and subjects are all marks stay inside
    Discord's 2000 characters after escaping, from either api."""
    sent = []

    class _Chan:
        async def send(self, content=None, **kw):
            sent.append(content)

    rows = {"new": [{"relay_code": "SCR-%012d" % i, "sender_name": "x", "subject": "x",
                     "sender_name_raw": "_*" * 32, "subject_raw": "_*" * 60} for i in range(5)],
            "old": [{"relay_code": "SCR-%012d" % i, "sender_name": _old_api_name("_*" * 32),
                     "subject": "\\_" * 60} for i in range(5)]}
    for which, threads_rows in rows.items():
        async def threads(discord_id, _r=threads_rows):
            return _r

        disc = types.SimpleNamespace(ui=types.SimpleNamespace(View=lambda timeout=None: types.SimpleNamespace(
            add_item=lambda i: None), Button=lambda **kw: kw), ButtonStyle=types.SimpleNamespace(secondary=2))
        ns = _lift(("_ask_which_mail", "_mailpick_view", "_escape_md", "_escape_text", "_mail_legacy_plain"),
                   HELPER_PARTS + ("MAIL_NAME_SHOWN_MAX", "MAIL_SUBJECT_SHOWN_MAX"),
                   {"discord": disc, "_relay_threads": threads, "_mailpick": {}, "_MAILPICK_MAX": 50})
        _run(ns["_ask_which_mail"](None, "b", discord_id=1, channel=_Chan(), source_message_id=None))
        assert len(sent[-1]) <= 2000, (which, len(sent[-1]))
        names = [ln[2:ln.index("** — ")] for ln in sent[-1].split("\n") if "SCR-0" in ln]
        bad = [(n, live(n)) for n in names if live(n)]
        assert len(names) == 5
        assert bad == [], (which, bad)


def test_the_api_serves_the_raw_mail_fields_beside_the_older_bots():
    """The api half of the mixes: the raw values are keys of their own; an
    older bot's subject stays the escaped field it shows as it stands, and its
    name is older_bot_name's (that bot's own escape is the one pass)."""
    src = _api_source("mail_discord.py")
    assert src.count('"subject_raw": ') == 2 and src.count('"sender_name_raw": ') == 2
    assert src.count('"subject": safe(') == 2 and src.count('"sender_name": older_bot_name(') == 2


# =============================================================================
# B. the census
# =============================================================================

# == B. the census of every typed value that reaches a Discord slot ==========
#
# What it walks: discord_bot.py's AST, every function and method.
#
# THE SINKS, by class. A sink is an argument Discord shows:
#   markdown ("md"): the content of send / reply / edit / send_message /
#     edit_message / edit_original_response (first positional or content=),
#     an Embed's title= and description= (also set by assignment to .title or
#     .description), add_field's name= and value=;
#   plain (renders no markdown): an embed's set_footer text= and set_author
#     name=, a Modal's title=, a Button's label=, a Select's placeholder=, a
#     SelectOption's label= and description=, a TextInput's label= /
#     placeholder= / default=, a thread name (create_thread name=, edit
#     name=), and the same keywords (title=, label=, placeholder=) passed to
#     super().__init__ by a subclass of a Modal, a Button or a Select.
#
# THE SOURCES, by class. From each sink argument the walk goes backwards
# through the expression: an f-string, a %-format, a concatenation, a join, a
# slice, a method call on a text (.strip(), .replace(), ...), a conditional, a
# comprehension (its variable stands for what it iterates), a local variable
# (every value assigned to it, appended, extended or inserted into it, or bound
# by for / with), a closure's variable, a module-level variable, a parameter
# (what the callers pass, when the walk came in through a call; every
# caller's argument otherwise, three calls deep, callers found by name for a
# function and by attribute for a method), and the return values of a bot
# function the argument calls. The walk ends at a source and records it:
#   1. a value the api returns: a read by a CONSTANT key, x["key"] or
#      x.get("key")  -> the key, classed in KEY_CLASSES;
#   2. a name Discord supplies: an attribute read, x.display_name,
#      x.global_name, x.nick, x.name, getattr(x, "name"), and an object shown
#      as its text (a member, a user, a guild, a channel, a role, a thread)
#      -> ".attr", classed in ATTR_CLASSES;
#   3. text typed into the bot's commands, modals and components: a
#      parameter of a command or an event, a TextInput's .value, a message's
#      .content -> "param:name" in PARAM_CLASSES, or ".attr".
# Every record carries the helper passes on its way (_escape_md = "name",
# _escape_text = "text"), counted: a value that passed one helper twice, or
# both, is a record with two passes.
#
# THE RULE: a typed value (class name, free or admin) reaches a markdown
# slot through EXACTLY ONE pass of its helper (name -> _escape_md, free and
# admin -> _escape_text) and a plain slot through none. A count of 0 in a
# markdown slot is reported, a count of 2 or more anywhere is reported, the
# other helper is reported. A typed value glued to mention or link syntax
# (a composer's constant text ending in "@", "#", "<@&", "[" or a backtick,
# directly before the value) is reported whatever its passes.
#
# WHAT IT CANNOT RESOLVE IS REPORTED, never passed: a name bound nowhere, a
# parameter with no caller it can find, a walk cut at its depth bound, and a
# key, attribute or parameter not in its table. Each is a problem unless
# UNRESOLVED lists it, with its count and the reason it is not a typed value.
# Not walked at all, plainly: text the bot puts into a file, an image or a
# webhook username (none of these is a Discord markdown slot).

SINK_CONTENT = {"send", "reply", "edit", "send_message", "edit_message", "edit_original_response"}
SINK_KW = {
    "Embed": ("md", ("title", "description")),
    "add_field": ("md", ("name", "value")),
    "create_thread": ("plain", ("name",)),
    "Button": ("plain", ("label",)),
    "SelectOption": ("plain", ("label", "description")),
    "Select": ("plain", ("placeholder",)),
    "TextInput": ("plain", ("label", "placeholder", "default")),
    "Modal": ("plain", ("title",)),
    "set_footer": ("plain", ("text",)),
    "set_author": ("plain", ("name",)),
}
SUPER_KW = ("title", "label", "placeholder")
NONTEXT = {"int", "float", "len", "bool", "round", "abs", "sum", "min", "max", "isinstance", "hash", "id",
           "range", "type", "divmod", "any", "all", "hex", "ord", "callable", "hasattr"}
HELPERS = {"_escape_md": "name", "_escape_text": "text"}
# Mention or link syntax a composer must not put directly against a typed value.
GLUE = ("@", "#", "<@&", "[", "`")
_EMPTY = {}                      # the one empty binding (its id is part of a walk key)
_BUILTINS = frozenset(dir(builtins))   # names the bot uses without defining them
_EXC = object()                  # marks a name bound by `except ... as name`


def _targets(t):
    """(name, position) for each name an assignment target binds: the
    position in a tuple target, None for a plain name (or a nested one)."""
    if isinstance(t, ast.Name):
        return [(t.id, None)]
    if isinstance(t, (ast.Tuple, ast.List)):
        out = []
        for i, x in enumerate(t.elts):
            if isinstance(x, ast.Name) and not any(isinstance(y, ast.Starred) for y in t.elts):
                out.append((x.id, i))
            else:
                out += [(n.id, None) for n in ast.walk(x) if isinstance(n, ast.Name)]
        return out
    return [(n.id, None) for n in ast.walk(t) if isinstance(n, ast.Name)]


def _glue_of(text, treat):
    """(mark, passes so far) when `text` ends with mention or link syntax: the
    number of passes tells a mark inside a helper's argument (the whole
    "@name" passed the helper) from one outside it."""
    for g in GLUE:
        if text.endswith(g):
            return (g, len(treat))
    return None


def _sink_args(call):
    """(kind, expression) for each shown argument of one call."""
    f = call.func
    attr = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
    kw = {k.arg: k.value for k in call.keywords if k.arg}
    out = []
    if attr in SINK_CONTENT:
        if call.args:
            out.append(("md", call.args[0]))
        if "content" in kw:
            out.append(("md", kw["content"]))
        if attr == "edit" and "name" in kw:
            out.append(("plain", kw["name"]))
    elif attr in SINK_KW:
        kind, names = SINK_KW[attr]
        out += [(kind, kw[k]) for k in names if k in kw]
    elif (attr == "__init__" and isinstance(f.value, ast.Call) and isinstance(f.value.func, ast.Name)
          and f.value.func.id == "super"):
        out += [("plain", kw[k]) for k in SUPER_KW if k in kw]
    return out


def _is_entry(fn):
    """A function Discord calls with what a person typed: a command, an event,
    a component's or a modal's callback."""
    if fn is None:
        return False
    if fn.name in ("callback", "on_submit", "interaction_check", "on_error", "on_timeout"):
        return True
    for d in fn.decorator_list:
        text = ast.unparse(d)
        if "command" in text or text.endswith(".event") or "listen" in text:
            return True
    return False


class _Census:
    """One walk of one source text; .reads is the list of
    (key, passes, slot kind, function, line, glue)."""

    def __init__(self, source):
        self.tree = ast.parse(source)
        self.funcs = {}        # name -> top-level function node, or a class's __init__
        self.methods = {}      # method name -> [method nodes]
        self.parent = {}       # node -> enclosing function node (None at module level)
        self.callers = {}      # callee name -> [(call node, enclosing function)]
        self.acallers = {}     # attribute name -> [(call node, enclosing function)]
        self.module = {}       # module-level name -> [assigned expressions]
        self.defined = set()   # module-level defs, classes and imports
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs[node.name] = node
                self.defined.add(node.name)
            elif isinstance(node, ast.ClassDef):
                self.defined.add(node.name)
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name == "__init__":
                            self.funcs[node.name] = item
                        self.methods.setdefault(item.name, []).append(item)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    self.defined.add((a.asname or a.name).split(".")[0])
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    for n in ast.walk(t):
                        if isinstance(n, ast.Name) and node.value is not None:
                            self.module.setdefault(n.id, []).append(node.value)
            elif isinstance(node, (ast.Try, ast.If)):
                for sub in ast.walk(node):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        for a in sub.names:
                            self.defined.add((a.asname or a.name).split(".")[0])
                    elif isinstance(sub, ast.Assign):
                        for t in sub.targets:
                            if isinstance(t, ast.Name):
                                self.module.setdefault(t.id, []).append(sub.value)
        self._index(self.tree, None)
        self.reads = []
        self._seen = set()
        self._binds = []
        self.sinks = {}        # sink name -> number of shown arguments walked
        for node, fn in list(self.parent.items()):
            if isinstance(node, ast.Call):
                for kind, expr in _sink_args(node):
                    f = node.func
                    name = "super().__init__" if isinstance(f, ast.Attribute) and f.attr == "__init__" \
                        else f.attr if isinstance(f, ast.Attribute) else f.id
                    self.sinks[name] = self.sinks.get(name, 0) + 1
                    self._eval(expr, fn, _EMPTY, (), kind, 0, None)
            elif isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Attribute) and t.attr in ("title", "description") for t in node.targets):
                self.sinks["= .title/.description"] = self.sinks.get("= .title/.description", 0) + 1
                self._eval(node.value, fn, _EMPTY, (), "md", 0, None)
        # An FAQ entry's handler ({"handler": f} in the FAQ table) answers
        # into the FAQ embed's description: its return is a markdown slot.
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and k.value == "handler" and isinstance(v, ast.Name) \
                            and v.id in self.funcs:
                        handler = self.funcs[v.id]
                        for ret in ast.walk(handler):
                            if isinstance(ret, ast.Return) and self.parent.get(ret) is handler:
                                self._eval(ret.value, handler, _EMPTY, (), "md", 0, None)

    def _index(self, node, fn):
        for child in ast.iter_child_nodes(node):
            self.parent[child] = fn
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    self.callers.setdefault(child.func.id, []).append((child, fn))
                elif isinstance(child.func, ast.Attribute):
                    self.acallers.setdefault(child.func.attr, []).append((child, fn))
            inner = child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            self._index(child, inner)

    def _record(self, key, treat, kind, fn, node, glue):
        self.reads.append((key, treat, kind, fn.name if fn is not None else "<module>", node.lineno, glue))

    def _eval(self, e, fn, bind, treat, kind, depth, glue, proj=None):
        """Walk one expression back to its sources. `proj` is set when only
        one element of the tuples the expression yields is wanted (a name
        bound by a tuple target: `for medal, name in rows`)."""
        if e is None or isinstance(e, (ast.Constant, ast.Lambda)):
            return
        if isinstance(e, ast.Tuple) and proj is not None:
            if proj < len(e.elts) and not any(isinstance(x, ast.Starred) for x in e.elts):
                self._eval(e.elts[proj], fn, bind, treat, kind, depth, glue)
            else:
                self._eval(e, fn, bind, treat, kind, depth, glue)
            return
        if isinstance(e, (ast.List, ast.Set)):        # a collection: each element, the projection kept
            for x in e.elts:
                self._eval(x, fn, bind, treat, kind, depth, None, proj)
            return
        if isinstance(e, ast.Subscript):
            sl = e.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                self._record(sl.value, treat, kind, fn, e, glue)
            elif isinstance(sl, ast.Constant) and isinstance(sl.value, int) and sl.value >= 0 and proj is None:
                self._eval(e.value, fn, bind, treat, kind, depth, glue, sl.value)   # x[0]: one element
            else:
                self._eval(e.value, fn, bind, treat, kind, depth, glue, proj)
            return
        if isinstance(e, ast.Call):
            self._call(e, fn, bind, treat, kind, depth, glue, proj)
            return
        if isinstance(e, ast.Name):
            self._name(e.id, e, fn, bind, treat, kind, depth, glue, proj)
            return
        if isinstance(e, ast.Attribute):
            self._record("." + e.attr, treat, kind, fn, e, glue)
            return
        if isinstance(e, ast.JoinedStr):
            g = glue
            for part in e.values:
                if isinstance(part, ast.Constant):
                    g = _glue_of(str(part.value), treat) if part.value else g
                    continue
                self._eval(part.value, fn, bind, treat, kind, depth, g)
                g = None
            return
        if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Add):
            self._eval(e.left, fn, bind, treat, kind, depth, glue, proj)
            g = _glue_of(e.left.value, treat) if isinstance(e.left, ast.Constant) \
                and isinstance(e.left.value, str) else None
            self._eval(e.right, fn, bind, treat, kind, depth, g, proj)
            return
        if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Mod) and isinstance(e.left, ast.Constant) \
                and isinstance(e.left.value, str):
            fmt = e.left.value
            args = e.right.elts if isinstance(e.right, ast.Tuple) else [e.right]
            heads = re.split(r"%(?:\([^)]*\))?[-#0 +]*\d*(?:\.\d+)?[sdirfxXeEgGc%]", fmt)
            for i, a in enumerate(args):
                g = _glue_of(heads[i], treat) if i < len(heads) and heads[i] else (glue if i == 0 else None)
                self._eval(a, fn, bind, treat, kind, depth, g)
            return
        if isinstance(e, (ast.ListComp, ast.GeneratorExp, ast.SetComp, ast.DictComp)):
            inner = dict(bind)
            self._binds.append(inner)
            for gen in e.generators:
                for t, p in _targets(gen.target):
                    inner[t] = (gen.iter, fn, bind, p)
            if isinstance(e, ast.DictComp):
                self._eval(e.value, fn, inner, treat, kind, depth, glue)
            else:
                self._eval(e.elt, fn, inner, treat, kind, depth, glue, proj)
            return
        if isinstance(e, ast.Compare):
            return                       # a comparison shows a yes/no, not the value
        if isinstance(e, ast.IfExp):     # the test decides; only the two branches are shown
            self._eval(e.body, fn, bind, treat, kind, depth, glue, proj)
            self._eval(e.orelse, fn, bind, treat, kind, depth, glue, proj)
            return
        if isinstance(e, ast.BoolOp):    # `a or b` shows one of its operands
            for v in e.values:
                self._eval(v, fn, bind, treat, kind, depth, glue, proj)
            return
        if isinstance(e, ast.Dict):
            for v in e.values:
                self._eval(v, fn, bind, treat, kind, depth, None)
            return
        if isinstance(e, ast.Await):
            self._eval(e.value, fn, bind, treat, kind, depth, glue, proj)
            return
        first = True
        for child in ast.iter_child_nodes(e):
            if isinstance(child, ast.expr):
                self._eval(child, fn, bind, treat, kind, depth, glue if first else None)
                first = False

    def _call(self, e, fn, bind, treat, kind, depth, glue, proj=None):
        f = e.func
        if (isinstance(f, ast.Attribute) and f.attr == "get" and e.args
                and isinstance(e.args[0], ast.Constant) and isinstance(e.args[0].value, str)):
            self._record(e.args[0].value, treat, kind, fn, e, glue)
            for a in e.args[1:]:
                self._eval(a, fn, bind, treat, kind, depth, glue)
            return
        if isinstance(f, ast.Name) and f.id == "getattr" and len(e.args) >= 2 \
                and isinstance(e.args[1], ast.Constant) and isinstance(e.args[1].value, str):
            self._record("." + e.args[1].value, treat, kind, fn, e, glue)
            for a in e.args[2:]:
                self._eval(a, fn, bind, treat, kind, depth, glue)
            return
        if isinstance(f, ast.Name) and f.id in HELPERS:
            for a in list(e.args[:1]) + [k.value for k in e.keywords if k.arg in (None, "text")]:
                self._eval(a, fn, bind, treat + (HELPERS[f.id],), kind, depth, glue)
            for a in list(e.args[1:]) + [k.value for k in e.keywords if k.arg not in (None, "text")]:
                self._eval(a, fn, bind, treat, kind, depth, None)     # the limit and the `more` text
            return
        if isinstance(f, ast.Name) and f.id in NONTEXT:
            return
        if isinstance(f, ast.Name) and f.id == "zip" and proj is not None:
            if proj < len(e.args):
                self._eval(e.args[proj], fn, bind, treat, kind, depth, glue)
            return
        if isinstance(f, ast.Name) and f.id == "enumerate" and proj is not None:
            if proj == 1 and e.args:
                self._eval(e.args[0], fn, bind, treat, kind, depth, glue)
            return
        callee = self._function(f.id, fn) if isinstance(f, ast.Name) else None
        if callee is not None:
            if depth < 10:
                self._returns(callee, e, fn, bind, treat, kind, depth + 1, glue, proj)
            else:
                self._record("?depth:" + callee.name, treat, kind, fn, e, glue)
            return
        if isinstance(f, ast.Name) and f.id in self.funcs:       # a class: its object shown as text
            self._record("?object:" + f.id, treat, kind, fn, e, glue)
            return
        if isinstance(f, ast.Name) and f.id not in self.defined and f.id not in _BUILTINS:
            # a callable held in a variable (a handler, a callback): what it
            # returns is not known here
            if not self._call_param(f.id, e, fn, bind, treat, kind, depth, glue, proj):
                self._record("?call:" + f.id, treat, kind, fn, e, glue)
            return
        keep = proj if isinstance(f, ast.Name) and f.id in ("sorted", "list", "tuple", "reversed", "set") \
            else None
        if isinstance(f, ast.Attribute):           # a method on a text: the text keeps the glue
            self._eval(f.value, fn, bind, treat, kind, depth, glue)
            glue = None
        for i, a in enumerate(list(e.args) + [k.value for k in e.keywords]):
            self._eval(a, fn, bind, treat, kind, depth, glue if i == 0 else None, keep)

    def _call_param(self, name, call, fn, bind, treat, kind, depth, glue, proj, hops=0):
        """A call of a function passed in as a parameter (`render(answer)`):
        the returns of every bot function the callers pass for it, bound to
        this call's arguments. False when some caller passes something else,
        or no caller is found."""
        scope = fn
        while scope is not None:
            params = [a.arg for a in scope.args.posonlyargs + scope.args.args + scope.args.kwonlyargs]
            if name in params and not self._assigned(scope, name):
                break
            scope = self.parent.get(scope)
        if scope is None or hops > 4:
            return False
        args = []
        is_method = [a.arg for a in scope.args.args][:1] == ["self"]
        params = [a.arg for a in scope.args.posonlyargs + scope.args.args]
        params = params[1:] if is_method else params
        for c, cfn in self.callers.get(scope.name, []):
            if self._function(scope.name, cfn) is not scope:
                continue
            arg = c.args[params.index(name)] if name in params and params.index(name) < len(c.args) else None
            for k in c.keywords:
                if k.arg == name:
                    arg = k.value
            if arg is None:
                continue                   # the parameter's default (None here)
            args.append((arg, cfn))
        if not args:
            return False
        ok = True
        for arg, cfn in args:
            target = self._function(arg.id, cfn) if isinstance(arg, ast.Name) else None
            if target is not None:
                if depth < 10:
                    self._returns(target, call, fn, bind, treat, kind, depth + 1, glue, proj)
            elif isinstance(arg, ast.Name):
                ok = self._call_param(arg.id, call, cfn, bind, treat, kind, depth, glue, proj, hops + 1) and ok
            elif isinstance(arg, ast.Lambda):      # its body, its parameters bound to this call's arguments
                inner = {}
                self._binds.append(inner)
                for p, a in zip([x.arg for x in arg.args.args], call.args):
                    inner[p] = (a, fn, bind, None)
                for p in [x.arg for x in arg.args.args]:
                    inner.setdefault(p, None)
                self._eval(arg.body, cfn, inner, treat, kind, depth + 1, glue, proj)
            else:
                ok = False
        return ok

    def _function(self, name, fn):
        """The bot function a call by `name` runs: a def nested in the
        calling function or one around it, else a top-level one."""
        if not hasattr(self, "_nested"):
            self._nested = {(id(p), n.name): n for n, p in self.parent.items()
                            if p is not None and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        scope = fn
        while scope is not None:
            if (id(scope), name) in self._nested:
                return self._nested[(id(scope), name)]
            scope = self.parent.get(scope)
        f = self.funcs.get(name)
        return f if f is not None and f.name == name else None

    def _returns(self, callee, call, fn, bind, treat, kind, depth, glue, proj=None):
        """The values a bot function returns, its parameters bound to this
        call's arguments."""
        params = [a.arg for a in callee.args.posonlyargs + callee.args.args]
        if params and params[0] == "self":
            params = params[1:]
        inner = {}
        self._binds.append(inner)          # kept alive: its id is part of a walk key
        for p, a in zip(params, call.args):
            inner[p] = (a, fn, bind, None)
        for k in call.keywords:
            if k.arg:
                inner[k.arg] = (k.value, fn, bind, None)
        for p in params + [a.arg for a in callee.args.kwonlyargs]:
            inner.setdefault(p, None)    # unbound: its default, not its callers
        for node in ast.walk(callee):
            if isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom)) and self.parent.get(node) is callee:
                self._eval(node.value, callee, inner, treat, kind, depth, glue, proj)

    def _name(self, name, at, fn, bind, treat, kind, depth, glue, proj=None):
        if name in bind:
            if bind[name] is None:
                return
            expr, efn, ebind, p = bind[name]
            self._eval(expr, efn, ebind, treat, kind, depth, glue, p if p is not None else proj)
            return
        scope = fn
        while scope is not None:
            # depth: a visit is never cut short by an earlier deeper one
            key = (id(scope), name, treat, kind, id(bind), depth, glue, proj)
            values = self._assigned(scope, name)
            params = [a.arg for a in scope.args.posonlyargs + scope.args.args + scope.args.kwonlyargs]
            if scope.args.vararg:
                params.append(scope.args.vararg.arg)
            if scope.args.kwarg:
                params.append(scope.args.kwarg.arg)
            if values or name in params:
                if key in self._seen:
                    return
                self._seen.add(key)
                for v, p in values:
                    if v is _EXC:
                        self._record("<exception>", treat, kind, scope, at, glue)
                    else:
                        self._eval(v, scope, bind if scope is fn else _EMPTY, treat, kind, depth, glue,
                                   p if p is not None else proj)
                if name in params and name != "self":
                    if _is_entry(scope):
                        self._record("param:" + name, treat, kind, scope, at, glue)
                    elif depth >= 5:
                        self._record("?depth-param:%s.%s" % (scope.name, name), treat, kind, scope, at, glue)
                    elif not self._callers(scope, name, treat, kind, depth + 1, glue):
                        self._record("?no-caller:%s.%s" % (scope.name, name), treat, kind, scope, at, glue)
                return
            scope = self.parent.get(scope)
        if name in self.module:
            key = (None, name, treat, kind, depth, glue, proj)
            if key in self._seen:
                return
            self._seen.add(key)
            for v in self.module[name]:
                self._eval(v, None, _EMPTY, treat, kind, depth, glue, proj)
            return
        if name in self.defined or name in _BUILTINS or name in ("True", "False", "None"):
            return                       # a function, a class, a module: not a text
        self._record("?unbound:" + name, treat, kind, fn, at, glue)

    def _assigned(self, scope, name):
        """Every (expression, element) a function binds to `name`: an
        assignment, an append or insert, a for or with target. `element` is
        the position of `name` in a tuple target, else None."""
        if not hasattr(self, "_assign_cache"):
            self._assign_cache = {}
        ck = (id(scope), name)
        if ck in self._assign_cache:
            return self._assign_cache[ck]
        vals = []
        for node in ast.walk(scope):
            if self.parent.get(node) is not scope:      # a nested def's own statements are its own
                continue
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    vals += [(node.value, p) for n, p in _targets(t) if n == name]
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                if isinstance(node.target, ast.Name) and node.target.id == name and node.value is not None:
                    vals.append((node.value, None))
            elif isinstance(node, ast.NamedExpr):
                if node.target.id == name:
                    vals.append((node.value, None))
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                vals += [(node.iter, p) for n, p in _targets(node.target) if n == name]
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if item.optional_vars is not None:
                        vals += [(item.context_expr, p) for n, p in _targets(item.optional_vars) if n == name]
            elif isinstance(node, ast.ExceptHandler):
                if node.name == name:
                    vals.append((_EXC, None))
            elif isinstance(node, ast.Call):
                f = node.func
                if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == name
                        and f.attr in ("append", "extend", "insert", "add", "appendleft")):
                    vals += [(a, None) for a in node.args[-1:]]
        self._assign_cache[ck] = vals
        return vals

    def _callers(self, callee, name, treat, kind, depth, glue):
        """Every call that runs `callee`, its argument for `name` walked.
        False when no call is found."""
        params = [a.arg for a in callee.args.posonlyargs + callee.args.args]
        is_method = params[:1] == ["self"]
        if is_method:
            params = params[1:]
        calls = []
        for call, cfn in self.callers.get(callee.name, []):
            if self._function(callee.name, cfn) is callee:
                calls.append((call, cfn))
        if callee.name == "__init__":
            calls += [(c, f) for cname, node in self.funcs.items() if node is callee
                      for c, f in self.callers.get(cname, [])]
        elif is_method:
            calls += self.acallers.get(callee.name, [])
        found = False
        for call, cfn in calls:
            arg = None
            if name in params and params.index(name) < len(call.args):
                arg = call.args[params.index(name)]
            for k in call.keywords:
                if k.arg == name:
                    arg = k.value
            found = True
            if arg is not None:
                self._eval(arg, cfn, _EMPTY, treat, kind, depth, glue)
        return found


# Every source the walk finds, with its class:
#   name    a name a person chose          -> _escape_md in a markdown slot, raw in a plain slot
#   free    free text a person typed       -> _escape_text in a markdown slot, raw in a plain slot
#   admin   text an admin or moderator typed  (the same rule as free)
#   system  the server's own value: numbers, ids, codes, statuses, times, labels, card names,
#           server sentences, the FAQ text
#   api     text the api composed and escaped itself (channel posts, stream posts, DMs, the
#           api's refusal sentences, an older api's escaped mail subject): shown as the api
#           sent it
# A key read from an api answer: x["key"] or x.get("key").
KEY_CLASSES = {
    "name": """
        actor actor_name bet_on_name bettor_name discord_display_name display_name host_name name names
        next_opponent opponent opponent_name owner_name p1_display_name p1_name p2_display_name p2_name
        player player1_name player2_name players reporter_name sender_name sender_name_raw subject_name
        t1a_name t1b_name t2a_name t2b_name waiting_on winner_name""",
    "free": """
        body comment description description_snippet message subject_raw""",
    "admin": """
        invalidation_reason reason""",
    "api": """
        a b content detail error subject""",
    "system": """
        accept_blocked_reason action_label amount answer api_unreachable assumption avg_fps
        bad_argument banned_by_steam_id base best_casual_streak best_ranked_streak
        dup_at_pull pay slot
        blocks_activated blocks_successful bracket_side bug_number bullets_fired bullets_hit cap
        card_name cards cards_summary carried_from case_id case_status casual_losses casual_wins
        category channel code connection_summary created_at current_streak custom_id damage_dealt
        deadline_at default_start_ts discord_id duo_rounds_won duration_seconds ended_at entries
        error_answer evidence_summary family field final_placement flag_reason fps_avg game_code
        game_codes game_number gold_earned gold_gained gold_spent group h2h_casual_losses
        h2h_casual_wins h2h_ranked_losses h2h_ranked_wins h2h_series_losses h2h_series_wins held
        html_url id kind label latest_mod_version level line lobby_id lobby_members lock_at loss_delta
        losses match_context match_id match_invalidation_reason match_label max_players min_players
        mod_version mode modes muted new_status next_match_label not_found noun odds_multiplier
        old_status opponent_rounds_won p1_odds p1_rating p1_rating_change
        p1_score p1_series_wins p1_steam_id p1_streak p1_wins p2_odds p2_rating
        p2_rating_change p2_score p2_series_wins p2_steam_id p2_streak p2_wins page payout peak
        peak_rating pending pending_match pending_match_label ping_avg ping_max placement
        picks player_count player_rounds_won point_progress pool_rank price
        primary_only prize_gold prize_players prize_xp queue_size rank rank_name ranked_dc_count
        ranked_series_losses ranked_series_wins rarity rating rating_after rating_before rating_change
        rating_deviation reason_head reason_text recorded region_breakdown relay_code
        resolution result round rounds_won runner_up_signup_id scheduled_start_ts schema
        score_summary score_target seed sentence series_id series_losses series_status series_wins
        server_error settings severity side slots solo_rounds_won status steam_id subject_steam_id
        suspect_steam_text sweeps_given sweeps_taken t1_odds t1_rounds_won t1_series_wins t1_wins
        t1a_rating t1b_rating t2_odds t2_rounds_won t2_series_wins t2_wins t2a_rating
        t2b_rating tag_name team team_a team_b telemetry_summary third_place_signup_id times_picked
        title too_large top_card top_card_names top_card_picks total total_matches total_players
        total_xp tournament_kind tournament_label value votes win_delta win_probability
        winner_signup_id wins xp_earned xp_for_next_level xp_gained xp_into_level""",
}
KEYS = {k: c for c, ks in KEY_CLASSES.items() for k in ks.split()}

# Discord's own names and the bot's stored copies (sources 2 and 3), by the
# attribute read: ".attr".
ATTR_CLASSES = {
    "name": """
        .display_name .global_name .labels .name .name_a .name_b .names .p1_name
        .p2_name .t1_label .t2_label .target_label""",
    "free": """
        .content""",
    "system": """
        .amount .cards_val .emojis .entries .hidden_inactive .id .lobby_id .mention
        .mode .page .pages .rec_val .series_id .shape .status .text .total_pages .total_players
        .tournament_tag .utc .values""",
}
# A parameter of a command, an event or a component callback (source 3).
PARAM_CLASSES = {
    "name": """
        param:search""",
    "free": """
        param:code param:filter param:message param:page""",
}
for _table in (ATTR_CLASSES, PARAM_CLASSES):
    KEYS.update({k: c for c, ks in _table.items() for k in ks.split()})

# A source whose class differs in one function: (function, key) -> (class, why).
OVERRIDES = {
    ("_format_release_message", "body"): (
        "system", "the slot: the body of a release read from the release source, the project's release "
                  "notes written as markdown and shown as written"),
    ("cmd_cards", "param:filter"): ("system", "a Literal of ranked, casual and all: discord.py refuses any "
                                              "other value before the command runs"),
    ("cmd_game", "param:code"): ("system", "reduced to the hex digits 0-9a-f before it is shown"),
    ("cmd_leaderboard", "param:page"): ("system", "turned into a whole number before it is shown"),
    ("_modcase_click", ".content"): ("api", "the case post's own text as the bot posted it (api-composed), "
                                            "kept as it stands when the outcome is added below it"),
}

# What the walk cannot resolve, by kind, with the number of reads and why
# none of them is a typed value. Any other unresolved read is a problem.
UNRESOLVED = {
    "<exception>": (14, "an exception's own text (str(e)) in an error line: the library's or the "
                        "server's words"),
    "?call:handler": (3, "_faq_resolve_answer calls an FAQ entry's handler; every handler the FAQ table "
                         "names is walked as a markdown slot of its own"),
    "?no-caller:_dm_all_signups.body": (1, "no call of _dm_all_signups stands in the bot: nothing "
                                           "reaches this send"),
}

RULE = {"name": "name", "free": "text", "admin": "text"}


def _census_problems(source, keys=None, census=None):
    keys = KEYS if keys is None else keys
    reads = (census or _Census)(source).reads
    problems, unresolved = [], {}
    for key, treat, kind, fn, line, glue in reads:
        if key.startswith("?") or key == "<exception>":
            unresolved[key] = unresolved.get(key, 0) + 1
            continue
        if key not in keys:
            problems.append("new key %r at %s line %d" % (key, fn, line))
            continue
        cls = OVERRIDES.get((fn, key), (keys[key],))[0]
        if cls not in RULE:
            continue
        if glue is not None and (glue[1] != len(treat) or not treat):
            problems.append("%s key %r is glued to %r at %s line %d" % (cls, key, glue[0], fn, line))
        want = () if kind == "plain" else (RULE[cls],)
        if treat == want:
            continue
        how = "raw" if not treat else "through %s" % " + ".join(treat)
        problems.append("%s key %r reaches a %s slot %s at %s line %d" % (cls, key, kind, how, fn, line))
    for k in sorted(set(unresolved) | set(UNRESOLVED)):
        if unresolved.get(k, 0) != UNRESOLVED.get(k, (0,))[0]:
            problems.append("cannot resolve %s: %d reads, UNRESOLVED lists %d" % (
                k, unresolved.get(k, 0), UNRESOLVED.get(k, (0,))[0]))
    return problems


def test_every_typed_value_reaching_a_discord_slot_passes_its_helper_once():
    """The census: every source read on the way to a Discord slot stands in
    its table, every name, free and admin source reaches a markdown slot
    through exactly one pass of its helper and a plain slot through none,
    none is glued to mention or link syntax, and every read the walk cannot
    resolve is one UNRESOLVED lists. Anything else fails here with the
    function and the line."""
    assert _census_problems(TEXT) == []


def test_the_census_has_no_unused_entries():
    reads = _Census(TEXT).reads
    seen = {r[0] for r in reads}
    assert sorted(set(KEYS) - seen) == []
    assert all((fn, k) in {(r[3], r[0]) for r in reads} for fn, k in OVERRIDES)
    assert sorted(set(UNRESOLVED) - seen) == []


def test_the_census_walks_every_sink_kind_it_lists():
    sinks = _Census(TEXT).sinks
    listed = set(SINK_CONTENT) | set(SINK_KW) | {"super().__init__", "= .title/.description"}
    # Kinds the bot does not call today are listed so a new call is walked; they are named here.
    absent = {"edit_message", "set_author", "Modal", "Select"}
    assert {k for k in listed if not sinks.get(k)} == absent, sinks


# Each mutant: (what it changes, the text it replaces, the new text, a word every problem must hold).
CENSUS_MUTANTS = [
    ("api key, name", "_escape_md(f.get('p1_name'), 120)", "(f.get('p1_name'))",
     "'p1_name' reaches a md slot raw"),
    ("api key, free text", "_escape_text(content, 1900)", "(content)", "'message' reaches a md slot raw"),
    ("api key, admin text", "Reason: **{_escape_text(b.get('reason') or 'violation')}**",
     "Reason: **{(b.get('reason') or 'violation')}**", "'reason' reaches a md slot raw"),
    ("Discord name", 'f"**{_escape_md(n)}**" for n in unlinked', 'f"**{n}**" for n in unlinked',
     "'.display_name' reaches a md slot raw"),
    ("command text", "{_escape_text(message, 1500)}", "{message[:1500]}",
     "'param:message' reaches a md slot raw"),
    ("a doubled pass", "_escape_md(f.get('p1_name'), 120)", "_escape_md(_escape_md(f.get('p1_name')), 120)",
     "'p1_name' reaches a md slot through name + name"),
    ("a plain modal title escaped", 'super().__init__(title=f"Bet on {str(name)[:38]}")',
     'super().__init__(title=f"Bet on {_escape_md(str(name)[:38])}")', "reaches a plain slot through name"),
    ("a button label escaped", "style=discord.ButtonStyle.secondary, label=label[:80],",
     "style=discord.ButtonStyle.secondary, label=_escape_md(label)[:80],", "reaches a plain slot through name"),
    ("@ outside the helper, queue beacon", "Discord: {_escape_md('@' + str(dname))}",
     "Discord: @{_escape_md(str(dname))}", "is glued to '@'"),
    ("@ outside the helper, my stats", "Discord: **{_escape_md('@' + str(_dname))}**",
     "Discord: **@{_escape_md(str(_dname))}**", "is glued to '@'"),
    ("the digest's names", "    return _escape_md(s, limit)\n", "    return s\n", "reaches a md slot raw"),
    ("a release title", 'name = _escape_md(release_json.get("name") or tag, 200)',
     'name = release_json.get("name") or tag', "'name' reaches a md slot raw at _format_release_message"),
    ("an older api's mail name",
     'who = _escape_md(_mail_legacy_plain(t.get("sender_name")).strip() or "?", MAIL_NAME_SHOWN_MAX)',
     'who = _mail_legacy_plain(t.get("sender_name")).strip() or "?"', "'sender_name' reaches a md slot raw"),
    ("a call the walk cannot follow", 'f"**{_escape_md(n)}**" for n in unlinked',
     'f"**{fmt(n)}**" for n in unlinked', "cannot resolve ?call:fmt"),
]


def _mutant_ok(problems, word):
    return bool(problems) and all(word in p for p in problems)


@pytest.mark.parametrize("old,new,word", [m[1:] for m in CENSUS_MUTANTS], ids=[m[0] for m in CENSUS_MUTANTS])
def test_the_census_finds_each_mutant(old, new, word):
    assert TEXT.count(old) == 1, old
    problems = _census_problems(TEXT.replace(old, new, 1))
    assert _mutant_ok(problems, word), problems


class _BlindCensus(_Census):
    """A census whose walk reports nothing."""

    def _record(self, *a, **kw):
        return None


def test_a_blind_census_or_a_judge_that_passes_everything_fails_every_mutant():
    """Control: the mutant test above cannot pass for a census that sees
    nothing, nor for a judge that passes every read."""
    for _what, old, new, word in CENSUS_MUTANTS:
        mutated = TEXT.replace(old, new, 1)
        assert not _mutant_ok(_census_problems(mutated, census=_BlindCensus), word)
        assert not _mutant_ok([], word)          # the judge that passes everything returns no problem


def test_the_census_finds_a_key_left_out_of_the_table():
    keys = dict(KEYS)
    del keys["comment"]
    problems = _census_problems(TEXT, keys)
    assert problems and all(p.startswith("new key 'comment'") for p in problems), problems


def test_a_comment_only_edit_leaves_the_census_unchanged():
    edited = TEXT.replace("def _escape_text(", "# census control: a comment only\ndef _escape_text(", 1)
    assert edited != TEXT
    assert _census_problems(edited) == []
    assert sorted(map(repr, (r[:4] for r in _Census(edited).reads))) == \
        sorted(map(repr, (r[:4] for r in _Census(TEXT).reads)))
