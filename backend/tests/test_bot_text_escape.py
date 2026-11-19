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
    ns = _lift(("poll_new_bans", "_ban_end_line", "_escape_text"), HELPER_PARTS + ("_BAN_END_LINE_UNREAD",), {
        "discord": _discord(), "datetime": _dt.datetime, "http_session": types.SimpleNamespace(get=lambda *a, **k: _Get()),
        "API_SECRET_KEY": "k", "API_BASE_URL": "http://api", "ADMIN_CHANNEL_ID": 3,
        "aiohttp": types.SimpleNamespace(ClientTimeout=lambda **k: None),
        "bot": types.SimpleNamespace(get_channel=lambda i: channel),
        "_last_ban_id_posted": "b1", "_ban_poller_initialized": True})
    _run(ns["poll_new_bans"]())
    (embed,) = channel.sent
    assert "\nReason: **" + SHOWN + "**\n" in embed.description, embed.description
