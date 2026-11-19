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
    ("not-a-scheme", "httpx://a and http:x", "httpx://a and http:x"),
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


@pytest.mark.parametrize("text", ["a" * 10 + "https://q.example", "x" * 37 + "HTTP://z", "http://" * 9],
                         ids=["middle", "edge", "many"])
def test_the_scheme_break_holds_at_every_cut(text):
    """The break is made before the cut: at every limit the result fits,
    keeps no scheme followed by its slashes, and ends inside no pair."""
    for helper in (NAME, discord_text.escape_name):
        for n in range(0, len(text) + 12):
            out = helper(text, n)
            assert len(out) <= n, (n, out)
            assert re.search(r"(?i)https?:/", out) is None, (n, out)
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

MAIL_FUNCS = ("_mail_sent_line", "_escape_md", "_escape_text")


def _sent_line(info):
    return _lift(MAIL_FUNCS, HELPER_PARTS)["_mail_sent_line"](info)


def test_mail_new_api_the_raw_values_are_escaped_once_by_the_bot():
    out = _sent_line({"known": True, "sender_name": "OLD", "subject": "OLD",
                      "sender_name_raw": "*Bob* @here", "subject_raw": TYPED})
    assert out.endswith("**\\*Bob\\* \\@here** — *%s*" % SHOWN), out
    assert "OLD" not in out


def test_mail_old_api_the_escaped_fields_show_as_before():
    """An api without the raw fields: the name passes _escape_md as it
    did, the subject is the api's own escaped field, unchanged."""
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
    view = _lift(("_mailpick_view",), (), {"discord": disc})["_mailpick_view"](threads)
    return [i.kw["label"] for i in view.items]


def test_a_mail_button_label_is_the_raw_text_cut_to_80():
    """A3: a button label renders no markdown, so it gets the raw text, no
    backslash, cut to Discord's 80."""
    (label,) = _mailpick_labels([{"relay_code": "SCR-A", "sender_name": "x\\_y", "subject": "s",
                                  "sender_name_raw": "x_y*", "subject_raw": "#" * 200}])
    assert label == ("x_y* — " + "#" * 200)[:80] and len(label) == 80 and "\\" not in label
    (old,) = _mailpick_labels([{"relay_code": "SCR-A", "sender_name": "x\\_y", "subject": "s"}])
    assert old == "x\\_y — s"


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
    ns = _lift(("_ask_which_mail", "_mailpick_view", "_escape_md", "_escape_text"), HELPER_PARTS,
               {"discord": disc, "_relay_threads": threads, "_mailpick": {}, "_MAILPICK_MAX": 50})
    _run(ns["_ask_which_mail"](None, "b", discord_id=1, channel=_Chan(), source_message_id=None))
    (text,) = sent
    assert "**\\_Al\\_** — *\\<\\@1\\> hi* · `SCR-A`" in text and "OLD" not in text, text


def test_the_api_serves_the_raw_mail_fields_beside_the_escaped_ones():
    """A1 mixed state, the api half: the escaped `subject` and `sender_name`
    stay as they were (an older bot reads them); the raw values are new keys
    beside them, in both answers the bot reads."""
    src = open(os.path.join(API_DIR, "mail_discord.py"), encoding="utf-8").read()
    assert src.count('"subject_raw": ') == 2 and src.count('"sender_name_raw": ') == 2
    assert src.count('"subject": safe(') == 2 and src.count('"sender_name": safe(') == 2


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


def test_the_composers_use_the_shared_helpers():
    calls = {}
    for name in ("main.py", "tournaments.py", "mail_discord.py"):
        for node in ast.walk(ast.parse(_api_source(name))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "_dtext":
                calls[(name, node.func.attr)] = calls.get((name, node.func.attr), 0) + 1
    assert calls.get(("main.py", "escape_text"), 0) >= 6 and calls.get(("main.py", "escape_name"), 0) >= 6, calls
    assert calls.get(("tournaments.py", "escape_name"), 0) == 1, calls
    assert calls.get(("mail_discord.py", "escape_text"), 0) == 2, calls
    # no composer keeps the old partial neutralisation (< to ( and @everyone to everyone)
    main_src = _api_source("main.py")
    assert 'safe_msg = (message or "")[:200].replace("<", "(")' not in main_src
    assert 'safe = msg.replace("<", "(")' not in main_src


# =============================================================================
# B. the census
# =============================================================================

# == B. the census of every api value that reaches a Discord slot =============
#
# What it walks: discord_bot.py's AST, every function and method. A SINK is an
# argument Discord shows: the content of send / reply / edit / send_message /
# edit_message / edit_original_response (first positional or content=), an
# Embed's title= and description=, an embed's .title / .description set by
# assignment, add_field's name= and value= (all four render markdown: "md"),
# and the slots that render none ("plain"): create_thread's and edit's name=,
# Button's label=, SelectOption's label= and description=, TextInput's
# label= / placeholder= / default=, Modal's title=, set_footer's text= and
# set_author's name=.
#
# From each sink argument the walk goes backwards through the expression: an
# f-string, a %-format, a concatenation, a join, a slice, a method call on a
# text (.strip(), .replace(), ...), a conditional, a comprehension (its
# variable stands for what it iterates), a local variable (every value
# assigned to it, appended, extended or inserted into it), a closure's
# variable, a parameter (what the callers pass, when the walk came in through
# a call; every caller's argument otherwise, three calls deep), and the
# return values of a bot function the argument calls. A read of a value by a
# CONSTANT key -- x["key"] or x.get("key") -- is where a walk ends: that key
# is recorded with the function and line of the read, the kind of slot, and
# the helper the read passed on its way, if any (_escape_md = "name",
# _escape_text = "text").
#
# What it cannot see, plainly: a key that is not a constant (x[k],
# x.get(name), **kw); a value taken from a Discord object (ctx.author.
# display_name, message.content, a member's nick, a channel's name) or from
# any other attribute; a value that travels through a module-level variable,
# a class attribute, a dict built in one function and read in another under a
# non-constant key, a callback or a lambda; a value a bot function receives
# from a call more than three calls away; text the bot puts into a file,
# an image or a webhook username. Those are covered, where they exist, by the
# site tests above and by tests/test_discord_name_markdown.py, not by this
# census.

SINK_CONTENT = {"send", "reply", "edit", "send_message", "edit_message", "edit_original_response"}
NONTEXT = {"int", "float", "len", "bool", "round", "abs", "sum", "min", "max", "isinstance", "hash", "id",
           "range", "type", "divmod", "any", "all", "hex", "ord"}
HELPERS = {"_escape_md": "name", "_escape_text": "text", "_qdig_md": "qdig"}
_EMPTY = {}                      # the one empty binding (its id is part of a walk key)


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
    elif attr == "Embed":
        out += [("md", kw[k]) for k in ("title", "description") if k in kw]
    elif attr == "add_field":
        out += [("md", kw[k]) for k in ("name", "value") if k in kw]
    elif attr == "create_thread":
        out += [("plain", kw[k]) for k in ("name",) if k in kw]
    elif attr == "Button":
        out += [("plain", kw[k]) for k in ("label",) if k in kw]
    elif attr == "SelectOption":
        out += [("plain", kw[k]) for k in ("label", "description") if k in kw]
    elif attr == "TextInput":
        out += [("plain", kw[k]) for k in ("label", "placeholder", "default") if k in kw]
    elif attr == "Modal":
        out += [("plain", kw[k]) for k in ("title",) if k in kw]
    elif attr == "set_footer":
        out += [("plain", kw[k]) for k in ("text",) if k in kw]
    elif attr == "set_author":
        out += [("plain", kw[k]) for k in ("name",) if k in kw]
    return out


class _Census:
    """One walk of one source text; .reads is the list of
    (key, helper or None, slot kind, function, line)."""

    def __init__(self, source):
        self.tree = ast.parse(source)
        self.funcs = {}        # name -> top-level function node, or a class's __init__
        self.parent = {}       # node -> enclosing function node (None at module level)
        self.callers = {}      # callee name -> [(call node, enclosing function)]
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs[node.name] = node
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
                        self.funcs[node.name] = item
        self._index(self.tree, None)
        self.reads = []
        self._seen = set()
        self._binds = []
        for node, fn in list(self.parent.items()):
            if isinstance(node, ast.Call):
                for kind, expr in _sink_args(node):
                    self._eval(expr, fn, _EMPTY, None, kind, 0)
            elif isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Attribute) and t.attr in ("title", "description") for t in node.targets):
                self._eval(node.value, fn, _EMPTY, None, "md", 0)

    def _index(self, node, fn):
        for child in ast.iter_child_nodes(node):
            self.parent[child] = fn
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                self.callers.setdefault(child.func.id, []).append((child, fn))
            inner = child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            self._index(child, inner)

    def _record(self, key, treat, kind, fn, node):
        self.reads.append((key, treat, kind, fn.name if fn is not None else "<module>", node.lineno))

    def _eval(self, e, fn, bind, treat, kind, depth):
        if e is None or isinstance(e, (ast.Constant, ast.Lambda)):
            return
        if isinstance(e, ast.Subscript):
            sl = e.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                self._record(sl.value, treat, kind, fn, e)
            else:
                self._eval(e.value, fn, bind, treat, kind, depth)
            return
        if isinstance(e, ast.Call):
            f = e.func
            if (isinstance(f, ast.Attribute) and f.attr == "get" and e.args
                    and isinstance(e.args[0], ast.Constant) and isinstance(e.args[0].value, str)):
                self._record(e.args[0].value, treat, kind, fn, e)
                for a in e.args[1:]:
                    self._eval(a, fn, bind, treat, kind, depth)
                return
            if isinstance(f, ast.Name) and f.id in HELPERS:
                for a in list(e.args) + [k.value for k in e.keywords]:
                    self._eval(a, fn, bind, treat or HELPERS[f.id], kind, depth)
                return
            if isinstance(f, ast.Name) and f.id in NONTEXT:
                return
            callee = self._function(f.id, fn) if isinstance(f, ast.Name) else None
            if callee is not None and depth < 6:
                self._returns(callee, e, fn, bind, treat, kind, depth + 1)
                return
            if isinstance(f, ast.Attribute):
                self._eval(f.value, fn, bind, treat, kind, depth)
            for a in list(e.args) + [k.value for k in e.keywords]:
                self._eval(a, fn, bind, treat, kind, depth)
            return
        if isinstance(e, ast.Name):
            self._name(e.id, e, fn, bind, treat, kind, depth)
            return
        if isinstance(e, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            inner = dict(bind)
            self._binds.append(inner)
            for g in e.generators:
                for t in ast.walk(g.target):
                    if isinstance(t, ast.Name):
                        inner[t.id] = (g.iter, fn, bind)
            self._eval(e.elt, fn, inner, treat, kind, depth)
            return
        if isinstance(e, ast.DictComp):
            return
        if isinstance(e, (ast.Attribute, ast.Dict, ast.Compare)):
            return                       # a comparison shows a yes/no, not the value
        if isinstance(e, ast.IfExp):     # the test decides; only the two branches are shown
            self._eval(e.body, fn, bind, treat, kind, depth)
            self._eval(e.orelse, fn, bind, treat, kind, depth)
            return
        for child in ast.iter_child_nodes(e):
            if isinstance(child, ast.expr):
                self._eval(child, fn, bind, treat, kind, depth)

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
        return self.funcs.get(name)

    def _returns(self, callee, call, fn, bind, treat, kind, depth):
        """The values a bot function returns, its parameters bound to this
        call's arguments."""
        params = [a.arg for a in callee.args.posonlyargs + callee.args.args]
        if params and params[0] == "self":
            params = params[1:]
        inner = {}
        self._binds.append(inner)          # kept alive: its id is part of a walk key
        for p, a in zip(params, call.args):
            inner[p] = (a, fn, bind)
        for k in call.keywords:
            if k.arg:
                inner[k.arg] = (k.value, fn, bind)
        for p in params + [a.arg for a in callee.args.kwonlyargs]:
            inner.setdefault(p, None)    # unbound: its default, not its callers
        for node in ast.walk(callee):
            if isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom)) and self.parent.get(node) is callee:
                self._eval(node.value, callee, inner, treat, kind, depth)

    def _name(self, name, at, fn, bind, treat, kind, depth):
        if name in bind:
            if bind[name] is None:
                return
            expr, efn, ebind = bind[name]
            self._eval(expr, efn, ebind, treat, kind, depth)
            return
        scope = fn
        while scope is not None:
            key = (id(scope), name, treat, kind, id(bind), depth)   # depth: a visit is never cut short by an earlier deeper one
            values = self._assigned(scope, name)
            params = [a.arg for a in scope.args.posonlyargs + scope.args.args + scope.args.kwonlyargs]
            if values or name in params:
                if key in self._seen:
                    return
                self._seen.add(key)
                for v in values:
                    self._eval(v, scope, bind if scope is fn else _EMPTY, treat, kind, depth)
                if name in params and depth < 3:
                    self._callers(scope, name, treat, kind, depth + 1)
                return
            scope = self.parent.get(scope)

    def _assigned(self, scope, name):
        """Every expression a function assigns to `name` (or adds to it)."""
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
                    if any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(t)):
                        vals.append(node.value)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                if isinstance(node.target, ast.Name) and node.target.id == name and node.value is not None:
                    vals.append(node.value)
            elif isinstance(node, ast.NamedExpr):
                if node.target.id == name:
                    vals.append(node.value)
            elif isinstance(node, ast.For):
                if any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(node.target)):
                    vals.append(node.iter)
            elif isinstance(node, ast.Call):
                f = node.func
                if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == name
                        and f.attr in ("append", "extend", "insert", "add", "appendleft")):
                    vals.extend(node.args[-1:])
        self._assign_cache[ck] = vals
        return vals

    def _callers(self, callee, name, treat, kind, depth):
        params = [a.arg for a in callee.args.posonlyargs + callee.args.args]
        if params and params[0] == "self":
            params = params[1:]
        names = [n for n, f in self.funcs.items() if f is callee]
        for cname in names:
            for call, cfn in self.callers.get(cname, []):
                arg = None
                if name in params and params.index(name) < len(call.args):
                    arg = call.args[params.index(name)]
                for k in call.keywords:
                    if k.arg == name:
                        arg = k.value
                if arg is not None:
                    self._eval(arg, cfn, _EMPTY, treat, kind, depth)

# Every key the walk finds, with its class:
#   name    a name a person chose          -> _escape_md in a markdown slot, raw in a plain slot
#   free    free text a person typed       -> _escape_text in a markdown slot, raw in a plain slot
#   admin   text an admin or moderator typed  (the same rule as free)
#   system  the server's own value: numbers, ids, codes, statuses, times, labels, card names,
#           server sentences, the maintainer's FAQ and release text
#   api     text the api composed and escaped itself (channel posts, stream posts, DMs, the
#           api's refusal sentences, the older api's escaped mail fields, the error report's
#           api-encoded names): shown as the api sent it
KEY_CLASSES = {
    "name": """
        actor actor_name bet_on_name bettor_name discord_display_name display_name host_name name names
        next_opponent opponent opponent_name owner_name p1_display_name p1_name p2_display_name p2_name
        player player1_name player2_name players reporter_name sender_name_raw subject_name t1a_name
        t1b_name t2a_name t2b_name waiting_on winner_name""",
    "free": """
        comment description description_snippet message subject_raw""",
    "admin": """
        invalidation_reason reason""",
    "api": """
        a b content detail error reporter sender_name subj subject""",
    "system": """
        accept_blocked_reason action_label afters amount answer api_unreachable assumption avg_fps
        bad_argument banned_by_steam_id base baseline best_casual_streak best_ranked_streak
        blocks_activated blocks_successful body bracket_side bug_number bullets_fired bullets_hit cap
        card_name cards cards_summary carried_from case_id case_status casual_losses casual_wins catalog
        category cells channel code connection_summary created_at current_streak custom_id damage_dealt
        deadline_at default_start_ts discord_id duo_rounds_won duration_seconds ended_at entries
        error_answer evidence_summary family field final_placement flag_reason flags fps_avg game_code
        game_codes game_number games gold_earned gold_gained gold_spent group h2h_casual_losses
        h2h_casual_wins h2h_ranked_losses h2h_ranked_wins h2h_series_losses h2h_series_wins held
        html_url id kind label latest_mod_version level line lobby_id lobby_members lock_at loss_delta
        losses match_context match_id match_invalidation_reason match_label max_players min_players
        mod_version mode modes muted new_status next next_match_label not_found noun odds_multiplier oi
        old_status opponent_rounds_won p1_discord_id p1_odds p1_rating p1_rating_change
        p1_score p1_series_wins p1_steam_id p1_streak p1_wins p2_discord_id p2_odds p2_rating
        p2_rating_change p2_score p2_series_wins p2_steam_id p2_streak p2_wins page pages payout peak
        peak_rating pending pending_match pending_match_label ping_avg ping_max place_deltas placement
        picks player_count player_rounds_won png point_progress pool_rank population price
        primary_only prize_gold prize_players prize_xp queue_size rank rank_name ranked_dc_count
        ranked_series_losses ranked_series_wins rarity rating rating_after rating_before rating_change
        rating_deviation reason_head reason_text recorded region_breakdown registry relay_code
        resolution result round rounds_won rows runner_up_signup_id scheduled_start_ts schema
        score_summary score_target seed sentence series_id series_losses series_status series_wins
        server_error settings severity shape side slots solo_rounds_won status steam_id subject_steam_id
        suspect_steam_text sweeps_given sweeps_taken t1_odds t1_rounds_won t1_series_wins t1_wins
        t1a_rating t1b_rating t2_odds t2_rounds_won t2_series_wins t2_wins t2a_rating
        t2b_rating tag_name team team_a team_b telemetry_summary third_place_signup_id times_picked
        title too_large top_card top_card_names top_card_picks total total_matches total_players
        total_xp tournament_kind tournament_label value votes win_delta win_probability windows
        winner_signup_id wins xp_earned xp_for_next_level xp_gained xp_into_level""",
}
KEYS = {k: c for c, ks in KEY_CLASSES.items() for k in ks.split()}

# A key whose class differs in one function: (function, key) -> (class, why).
OVERRIDES = {
    ("_format_release_message", "name"): ("system", "the GitHub release's title, written by the maintainer"),
    ("_aer_decode_response", "name"): ("api", "the error report's subject name: encoded by the api and "
                                              "checked by _aer_check_text before it is shown"),
}

# The held-report digest's own escape, _qdig_md: a third escape, not one of the
# two helpers. tests/test_discord_name_markdown.py proves it escapes at least
# every character _escape_md does. Allowed for names only inside _qdig_*
# functions; an open item of stage 2 (not folded into the two helpers).
QDIG_PREFIX = "_qdig"

# What the walk reports that is not a defect, with the number of reads it covers.
ALLOW = {
    ("poll_lfp_pings", "message"): (1, "the raw half of _lfp_render_message's (shown, raw) pieces: "
                                       "kept only to re-cut it through _escape_text; the shown half "
                                       "passes _escape_text (test_the_lfp_message_is_shown_as_typed)"),
}

RULE = {"name": "name", "free": "text", "admin": "text"}


def _census_problems(source, keys=None):
    keys = KEYS if keys is None else keys
    reads = _Census(source).reads
    problems, allowed = [], {}
    for key, treat, kind, fn, line in reads:
        if key not in keys:
            problems.append("new key %r at %s line %d" % (key, fn, line))
            continue
        cls = OVERRIDES.get((fn, key), (keys[key],))[0]
        if cls not in RULE:
            continue
        if (fn, key) in ALLOW and treat is None:
            allowed[(fn, key)] = allowed.get((fn, key), 0) + 1
            continue
        want = None if kind == "plain" else RULE[cls]
        if treat == want or (treat == "qdig" and cls == "name" and fn.startswith(QDIG_PREFIX)):
            continue
        problems.append("%s key %r reaches a %s slot %s at %s line %d" % (
            cls, key, kind, "raw" if treat is None else "through the %s helper" % treat, fn, line))
    for k, (n, _why) in ALLOW.items():
        if allowed.get(k, 0) != n:
            problems.append("ALLOW %s covers %d reads, not %d" % (k, allowed.get(k, 0), n))
    return problems


def test_every_api_value_reaching_a_discord_slot_has_its_helper():
    """The census: every key read on the way to a Discord slot stands in
    KEY_CLASSES, and every name, free and admin key reaches a markdown slot
    through its helper and a plain slot raw. A new key, or a typed key that
    reaches a slot raw, fails here with the function and the line."""
    assert _census_problems(TEXT) == []


def test_the_census_has_no_unused_keys():
    seen = {r[0] for r in _Census(TEXT).reads}
    assert sorted(set(KEYS) - seen) == []
    assert all((fn, k) in {(r[3], r[0]) for r in _Census(TEXT).reads} for fn, k in OVERRIDES)


CENSUS_CONTROLS = [
    ("name", "_escape_md(f.get('p1_name'), 120)", "(f.get('p1_name'))", "'p1_name' reaches a md slot raw"),
    ("free", "_escape_text(content, 1900)", "(content)", "'message' reaches a md slot raw"),
    ("admin", "Reason: **{_escape_text(b.get('reason') or 'violation')}**",
     "Reason: **{(b.get('reason') or 'violation')}**", "'reason' reaches a md slot raw"),
]


@pytest.mark.parametrize("cls,escaped,raw,word", CENSUS_CONTROLS, ids=[c[0] for c in CENSUS_CONTROLS])
def test_the_census_finds_a_removed_helper_of_each_class(cls, escaped, raw, word):
    assert TEXT.count(escaped) == 1, escaped
    problems = _census_problems(TEXT.replace(escaped, raw))
    assert problems and all(word in p and p.startswith(cls) for p in problems), problems


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
