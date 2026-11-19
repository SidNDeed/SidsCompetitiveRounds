"""Typed text for a Discord message the api composes (BOT-TEXT-ESCAPE-1).

The api writes the whole text of three bot feeds: channel posts
(pending_channel_posts, which the bot sends with user mentions allowed),
stream posts (stream_channel_posts) and one-off DMs (pending_dms). A value a
person typed goes into that text through ONE of these two functions, exactly
once, where the text is composed:

  escape_text(value, limit=None, more="...")  free text (a message, a reason,
                                               a note): line breaks kept
  escape_name(value, limit=None, more="...")  a name: one line

They are the bot's own _escape_text and _escape_md, written out again here
because the bot is a separate image and imports nothing from the api.
tests/test_bot_text_escape.py runs both pairs over the same cases and
requires the same output for every one.

Rules, shared with the bot:
  - each of \\ * _ ~ | ` [ ] < > @ gets a backslash, so no markdown construct
    and no mention form (<@id> <@!id> <@&id> <#id> </name:id> <t:..> @everyone
    @here) takes effect, and Discord shows the characters typed. In
    particular typed text can never add a user mention to a channel post:
    every < and every @ in it is escaped;
  - escape_text keeps line breaks (each kind becomes one \\n) and escapes a
    line-opening # - + and the . or ) after leading digits on every line; a
    bare http(s) address is left whole;
  - escape_name turns every line break into a space and escapes the
    line-opening marks once, at the start; a name is never a link: each
    http: or https: (any case) before one or two slashes gets a zero-width
    space after its colon, before the cut;
  - with a limit the result is at most `limit` characters, cut on the escaped
    text and never inside an escape pair, `more` after a cut.
Pure functions, no I/O.
"""
import re

_TEXT_BREAKS = re.compile(r"\r\n|[\r\v\f\x1c-\x1e\x85  ]")
_TEXT_URL = re.compile(r"(?<![0-9A-Za-z_])https?://[^\s<]*[^\s<.,:;\"')\]]", re.IGNORECASE)
_TEXT_LINE_MARK = re.compile(r"([ \t]*)([#+-]|[0-9]+[.)])")
_TEXT_ALWAYS = frozenset("\\*_~|`[]<>@")


def escape_text(text, limit=None, more="..."):
    """Free text a person typed, shown in Discord as the characters typed
    (the bot's _escape_text). None is the empty text."""
    s = _TEXT_BREAKS.sub("\n", "" if text is None else str(text))
    pieces = []
    for n, line in enumerate(s.split("\n")):
        if n:
            pieces.append("\n")
        pos = 0
        m = _TEXT_LINE_MARK.match(line)
        if m:
            pieces.extend(m.group(1))
            mark = m.group(2)
            pieces.append(mark[:-1] + "\\" + mark[-1])
            pos = m.end()
        while pos < len(line):
            u = _TEXT_URL.match(line, pos)
            if u:
                pieces.append(u.group(0))
                pos = u.end()
                continue
            ch = line[pos]
            pieces.append("\\" + ch if ch in _TEXT_ALWAYS else ch)
            pos += 1
    out = "".join(pieces)
    if limit is None or len(out) <= limit:
        return out
    room = max(limit - len(more), 0)
    kept, used = [], 0
    for p in pieces:
        if used + len(p) > room:
            break
        kept.append(p)
        used += len(p)
    return "".join(kept) + more if limit >= len(more) else more[:limit]


def flat(text):
    """Layout only, no escape: every run of white space (line breaks
    included) as one space, for a value shown inside one line of a post."""
    return " ".join(str(text or "").split())


def escape_name(text, limit=None, more="..."):
    """A name a person chose, one line, shown as typed (the bot's _escape_md)."""
    one_line = re.sub(r"\r\n|[\n\r\v\f\x1c-\x1e\x85  ]", " ", str(text))
    escaped = re.sub(r"([\\*_~|`\[\]<>@])", r"\\\1", one_line)
    escaped = re.sub(r"^(\s*)([#+-])", r"\1\\\2", escaped)
    escaped = re.sub(r"^(\s*\d+)([.)])", r"\1\\\2", escaped)
    # A name is never a link: a zero-width space after every address
    # scheme's colon, before the cut (the bot's _escape_md does the same).
    escaped = re.sub(r"(?i)(https?):(/{1,2})", "\\1:\u200b\\2", escaped)
    if limit is None or len(escaped) <= limit:
        return escaped
    if limit < len(more):
        return more[:limit]
    cut = escaped[:limit - len(more)]
    if (len(cut) - len(cut.rstrip("\\"))) % 2:
        cut = cut[:-1]
    return cut + more
