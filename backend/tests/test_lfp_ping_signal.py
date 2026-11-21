"""The bot's two role pings tell whether they pinged (LFP-PING-1).

Sid's report (21 Nov 2026): the Ranked Looking For Player ping notifies
nobody he can see, and nothing in the bot said so. Discord notifies a role's
members only when the role is mentionable or the bot holds the Mention
Everyone permission in the channel (Discord's Allowed Mentions Object), and
the message Discord returns lists in mention_roles the roles it mentioned.
The bot read neither. Its two role pings (the LFP ping, poll_lfp_pings, and
the Gambler ping, poll_gambler_pings) now:

  R1 resolve the role through ONE helper: the exact name, else the one role
     whose normalised name matches; two or more normalised matches with no
     exact name are ambiguous (no role); when several roles carry the exact
     name each is mentioned (duplicate), at most five, the oldest first;
  R2 read before the send whether the ping can notify (deliverable): every
     mentioned role mentionable, or the bot holds the permission;
  R3 read after the send how many of the mentioned roles Discord's answer
     lists (listed) and whether it lists every one (delivered), from that
     answer and never from the bot's own text;
  R4 print one [PING] line per post in a closed grammar, and post one admin
     warning per kind per 24 hours when one is owed: the role absent,
     ambiguous or duplicate, deliverable no, or delivered not yes;
  R5 print the same line per kind with id=startup once after ready;
  R6 change nothing else: the content, the allowed mentions and the ack;
  R7 ping no other role.

discord_bot.py builds the bot at import, so, as in test_bot_text_escape.py,
what runs here is lifted out of its AST and run against fakes: no network,
no database. Each requirement is one check function. MUTANTS holds at least
one source edit per requirement that must turn its check red, and the
control (a comment-only edit) leaves every check green. An edit is made in
the source of the one top-level statement it falls in, which is parsed again
and stands in place of the shipped statement (mutate, below).
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
BASE_TREE = ast.parse(TEXT)

HELPER_PARTS = ("_TEXT_BREAKS", "_TEXT_URL", "_TEXT_LINE_MARK", "_TEXT_ALWAYS")
FUNCS = ("_ping_role_norm", "_ping_role_matches", "_ping_role_resolve", "_ping_deliverable",
         "_ping_delivered", "_ping_line", "_ping_warning_text", "_ping_warn", "_ping_warning_owed",
         "_ping_after_send", "_ping_startup_lines", "poll_lfp_pings", "poll_gambler_pings",
         "_escape_md", "_escape_text", "_md_name", "_lfp_render_message")
ASSIGNS = ("PING_WARN_EVERY_S", "PING_ROLES_MAX", "_PING_STARTUP", "_PING_ID_RE", "_PING_WORDS", "_PING_MENTIONS",
           "_PING_KIND_SHOWN", "_PING_PERMISSION", "_ping_warned_at", "_ping_startup_done",
           "_LFP_EMOJI_TOKEN") + HELPER_PARTS

# The [PING] line, whole. id=startup goes with delivered=unsent and listed=0;
# mentioned agrees with the role word, listed is at most mentioned, and
# delivered is yes exactly when roles were mentioned and the answer lists all.
GRAMMAR = re.compile(
    r"\[PING\] kind=(lfp|gambler) id=(startup|[0-9a-f-]{1,64}|invalid) "
    r"role=(found|duplicate|normalised|absent|ambiguous) mentioned=([0-5]) "
    r"deliverable=(yes|no|unknown) listed=([0-5]) delivered=(yes|no|unsent)")
MENTIONED = {"found": (1, 1), "normalised": (1, 1), "duplicate": (2, 5), "absent": (0, 0), "ambiguous": (0, 0)}


def in_grammar(line):
    m = GRAMMAR.fullmatch(line)
    if not m:
        return False
    startup, role, delivered = m.group(2) == "startup", m.group(3), m.group(7)
    mentioned, listed = int(m.group(4)), int(m.group(6))
    least, most = MENTIONED[role]
    if startup != (delivered == "unsent") or not least <= mentioned <= most or listed > mentioned:
        return False
    if delivered == "unsent":
        return listed == 0
    return (delivered == "yes") == (mentioned > 0 and listed == mentioned)


def field(line, name):
    """One field's value in a [PING] line."""
    return line.split(" %s=" % name, 1)[1].split(" ", 1)[0]


LINES = TEXT.split("\n")      # the parser's lines (str.splitlines would also break at FF, U+2028, ...)
_KEEP = {}      # (kind, id(obj)) -> (obj, what was made from it); obj is kept, so its id is never reused


def _cached(kind, obj, make):
    key = (kind, id(obj))
    if key not in _KEEP:
        _KEEP[key] = (obj, make(obj))
    return _KEEP[key][1]


def _first_line(node):
    return min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", ())])


def mutate(old, new):
    """The shipped tree with ONE source edit: the top-level statement the edit
    falls in is parsed again from its edited source and stands in place of
    the shipped one; every other statement is the shipped one (parsing the
    whole module again for each mutant costs seconds). Answers the tree, the
    shipped statement and the statements that replace it."""
    assert TEXT.count(old) == 1, old
    start = TEXT.index(old)
    first, last = TEXT.count("\n", 0, start) + 1, TEXT.count("\n", 0, start + len(old) - 1) + 1
    for i, node in enumerate(BASE_TREE.body):
        if _first_line(node) <= first and last <= node.end_lineno:
            break
    else:
        raise AssertionError("the edit is not inside one top-level statement: %r" % old)
    top = _first_line(node)
    segment = "\n".join(LINES[top - 1:node.end_lineno]) + "\n"
    assert segment.count(old) == 1, old
    part = ast.parse(segment.replace(old, new, 1))
    ast.increment_lineno(part, top - 1)
    return ast.Module(body=BASE_TREE.body[:i] + part.body + BASE_TREE.body[i + 1:], type_ignores=[]), node, part.body


def lift(tree, extra):
    """The bot's ping code and the helpers it calls, lifted out of `tree` and
    run in a namespace of fakes (compiled once per tree)."""
    ns = {"re": re}
    ns.update(extra)
    exec(_cached("code", tree, _lifted_code), ns)
    return ns


def _lifted_code(tree):
    picked, seen = [], set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FUNCS:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            picked.append(fn)
            seen.add(node.name)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ASSIGNS
                                                  for t in node.targets):
            picked.append(node)
            seen.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id in ASSIGNS:
            picked.append(node)
            seen.add(node.target.id)
    missing = (set(FUNCS) | set(ASSIGNS)) - seen
    assert not missing, "not found in the bot: %s" % sorted(missing)
    return compile(ast.Module(body=picked, type_ignores=[]), SRC, "exec")


def one(seq, what):
    assert len(seq) == 1, (what, seq)
    return seq[0]


# -- fakes: Discord as far as these two loops read it --------------------------------------------

class Role:
    def __init__(self, rid, name, mentionable=False):
        self.id, self.name, self.mentionable = rid, name, mentionable

    @property
    def mention(self):
        return "<@&%d>" % self.id

    def __repr__(self):
        return "Role(%d, %r, %r)" % (self.id, self.name, self.mentionable)


class Perms:
    def __init__(self, mention_everyone):
        self.mention_everyone = mention_everyone


class Member:
    """The bot's own member. Its guild-level permission is set to the opposite
    of what the channel answers, so a check that reads the guild level in
    place of channel.permissions_for reads the wrong answer."""

    def __init__(self, guild_level):
        self.guild_permissions = Perms(guild_level)


class Guild:
    def __init__(self, roles, me):
        self.id, self.roles, self.me, self.emojis = 900, list(roles), me, []


class Message:
    """What channel.send returns, as far as the bot reads it: role_mentions is
    Discord's answer (the payload's mention_roles); content and
    raw_role_mentions are the bot's own text, as discord.py derives them."""

    def __init__(self, channel, content, role_mentions, mid):
        self.id, self.channel, self.content = mid, channel, content
        self.role_mentions = list(role_mentions)
        self.jump_url = "https://discord.com/channels/%d/%d/%d" % (channel.guild.id, channel.id, mid)

    @property
    def raw_role_mentions(self):
        return [int(x) for x in re.findall(r"<@&([0-9]+)>", self.content or "")]


def discord_rule(channel, content, kw):
    """Discord's rule (its Allowed Mentions Object): a role written in the
    content and allowed by allowed_mentions is mentioned when it is
    mentionable or the bot holds Mention Everyone in the channel."""
    allowed = getattr(kw.get("allowed_mentions"), "roles", False)
    allowed = allowed if isinstance(allowed, list) else []
    return [r for r in channel.guild.roles
            if r.mention in (content or "") and r in allowed and (r.mentionable or channel.mention_everyone)]


def discord_lists_none(channel, content, kw):
    return []


def discord_lists_one(channel, content, kw):
    """An answer that lists only the first of the roles Discord's rule lists."""
    return discord_rule(channel, content, kw)[:1]


def discord_lists_written(channel, content, kw):
    """An answer that lists every allowed role the content names, whether or
    not Discord's rule lets it notify (its documentation does not say that
    mention_roles leaves out a role that notified nobody)."""
    allowed = getattr(kw.get("allowed_mentions"), "roles", False)
    allowed = allowed if isinstance(allowed, list) else []
    return [r for r in channel.guild.roles if r.mention in (content or "") and r in allowed]


class Channel:
    """A text channel. `answer` gives the roles Discord's answer lists (its
    rule by default). With `flip` the bot's permission here changes right
    after each post, so a check read after the send reads another answer."""

    def __init__(self, cid, guild, mention_everyone=False, answer=discord_rule, flip=False):
        self.id, self.guild = cid, guild
        self.mention = "<#%d>" % cid
        self.mention_everyone = mention_everyone
        self.answer, self.flip = answer, flip
        self.sent, self.asked = [], []

    def permissions_for(self, member):
        self.asked.append(member)
        return Perms(self.mention_everyone)

    async def send(self, content=None, **kw):
        self.sent.append((content, kw))
        msg = Message(self, content, self.answer(self, content, kw), 5000 + len(self.sent))
        if self.flip:
            self.mention_everyone = not self.mention_everyone
        return msg


class AdminChannel:
    def __init__(self, fails=0):
        self.sent, self.fails = [], fails

    async def send(self, content=None, **kw):
        if self.fails:
            self.fails -= 1
            raise RuntimeError("the admin channel refused the post")
        self.sent.append((content, kw))


class NotFound(Exception):
    pass


class Forbidden(Exception):
    pass


class AllowedMentions:
    def __init__(self, everyone=True, users=True, roles=True, replied_user=True):
        self.everyone, self.users, self.roles, self.replied_user = everyone, users, roles, replied_user

    @classmethod
    def none(cls):
        return cls(everyone=False, users=False, roles=False, replied_user=False)


def _utils_get(iterable, **attrs):
    """discord.utils.get: the first element whose attributes all match."""
    for x in iterable:
        if all(getattr(x, k, None) == v for k, v in attrs.items()):
            return x
    return None


DISCORD = types.SimpleNamespace(AllowedMentions=AllowedMentions, Forbidden=Forbidden, NotFound=NotFound,
                                utils=types.SimpleNamespace(get=_utils_get))


class Bot:
    def __init__(self, channels):
        self.channels = dict(channels)

    def get_channel(self, cid):
        return self.channels.get(cid)

    async def fetch_channel(self, cid):
        if cid in self.channels:
            return self.channels[cid]
        raise NotFound("unknown channel")


async def _sleep(*a, **k):
    return None


QUEUE, BETS, ADMIN = 10, 20, 77
LFP_NAME, GAMBLER_NAME = "Ranked Looking For Player", "Gambler"
PERMISSION = "Mention @\u200beveryone, @\u200bhere, and All Roles"
PING = {"ping_id": 41, "discord_id": "123456789012345678", "display_name": "Typed*Name",
        "message": "typed words", "expires_unix": 1763700000, "modes": "1v1", "expires_minutes": 60}
SID = "3f2a9c1e-0000-4000-8000-00000000abcd"
SERIES = {"series_id": SID, "p1_name": "Pat*One", "p2_name": "Quinn_Two", "bets_locked": False}
SITES = ("lfp", "gambler")
# main's text for the two posts (the role at id 1 and id 12, the fakes above)
EXPECTED_LFP = ("<@&1> \N{LEFT-POINTING MAGNIFYING GLASS} **Typed\\*Name** (<@123456789012345678>) "
                "LFP: ranked 1v1 for 1h!\n> typed words\nExpires <t:1763700000:R>")
EXPECTED_BET = "<@&12> \U0001F3B2 Bets are open \u2014 **Pat\\*One** vs **Quinn\\_Two**! Place yours below."


def open_roles():
    return [Role(1, LFP_NAME, True), Role(12, GAMBLER_NAME, True)]


class World:
    """One server: a guild with `roles`, the queue channel, the bets channel
    and the admin channel, and the lifted bot code over them."""

    def __init__(self, tree=BASE_TREE, roles=(), me=True, mention_everyone=False, answer=discord_rule, flip=False,
                 admin_fails=0, queue_id=QUEUE, lfp_name=LFP_NAME, gambler_name=GAMBLER_NAME):
        self.guild = Guild(roles, Member(not mention_everyone) if me else None)
        self.queue = Channel(QUEUE, self.guild, mention_everyone, answer, flip)
        self.bets = Channel(BETS, self.guild, mention_everyone, answer, flip)
        self.admin = AdminChannel(admin_fails)
        self.bot = Bot({QUEUE: self.queue, BETS: self.bets, ADMIN: self.admin})
        self.log, self.acks, self.seen, self.clock = [], [], set(), [1000.0]
        self.pings, self.series = [], []

        async def api_get(path, timeout=8.0):
            if path == "/internal/lfp-pings":
                return {"pings": [dict(p) for p in self.pings]}
            if path == "/series/active":
                return [dict(s) for s in self.series]
            return None

        async def ack(ids, undeliverable=False):
            self.acks.append((list(ids), bool(undeliverable)))

        async def noop(*a, **k):
            return None

        self.ns = lift(tree, {
            "discord": DISCORD, "bot": self.bot, "api_get": api_get, "_ack_lfp_pings": ack,
            "_lfp_seen_ids": self.seen, "asyncio": types.SimpleNamespace(sleep=_sleep),
            "time": types.SimpleNamespace(monotonic=lambda: self.clock[0]),
            "print": lambda *a, **k: self.log.append(" ".join(str(x) for x in a)),
            "QUEUE_BEACON_CHANNEL_ID": queue_id, "LIVE_BETS_CHANNEL_ID": BETS, "ADMIN_CHANNEL_ID": ADMIN,
            "LFP_ROLE_NAME": lfp_name, "GAMBLER_ROLE_NAME": gambler_name,
            "_gambler_signup_checked": True, "_gambler_seeded": True, "_gambler_pinged": set(),
            "_ensure_gambler_signup_message": noop,
        })

    def lfp(self, *pings):
        self.pings = list(pings or (PING,))
        asyncio.run(self.ns["poll_lfp_pings"]())

    def gambler(self, *series):
        self.series = list(series or (SERIES,))
        asyncio.run(self.ns["poll_gambler_pings"]())

    def run(self, site):
        (self.lfp if site == "lfp" else self.gambler)()

    def channel(self, site):
        return self.queue if site == "lfp" else self.bets

    def startup(self):
        asyncio.run(self.ns["_ping_startup_lines"]())

    def lines(self):
        out = [ln for ln in self.log if ln.startswith("[PING]")]
        assert all(in_grammar(ln) for ln in out), out
        return out

    def warnings(self):
        return [c for c, _kw in self.admin.sent]


def _raises_value_error(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


def _calls_in(top):
    """(innermost function name, call) for every call in one top-level statement."""
    found, stack = [], [(None, top)]
    while stack:
        fn, node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
        if isinstance(node, ast.Call):
            found.append((fn, node))
        stack.extend((fn, child) for child in ast.iter_child_nodes(node))
    return found


def _calls_by_function(tree):
    """Every call in the module; a statement a mutant shares with the shipped
    tree is walked once."""
    for top in tree.body:
        yield from _cached("calls", top, _calls_in)


# -- R1: one role resolution, used by both sites ------------------------------------------------

def check_r1(tree):
    ns = World(tree).ns
    resolve = ns["_ping_role_resolve"]
    assert ns["PING_ROLES_MAX"] == 5
    exact, loose = Role(1, LFP_NAME), Role(2, "RankedLookingForPlayer")
    assert resolve([loose, exact], LFP_NAME) == ([exact], "found")              # the exact name first
    assert resolve([loose, Role(3, "LookingForPlayer")], LFP_NAME) == ([loose], "normalised")
    odd = Role(4, "ranked_looking.for-player!")
    assert resolve([odd], LFP_NAME) == ([odd], "normalised")                    # marks and the underscore go
    fold = Role(5, "STRASSE CREW")
    assert resolve([fold], "Stra\u00dfe Crew") == ([fold], "normalised")         # casefold, not lower
    two = Role(6, "TEAM-2")
    assert resolve([Role(7, "Team 3"), two], "Team 2") == ([two], "normalised")  # digits stay
    assert resolve([Role(3, "LookingForPlayer"), Role(8, GAMBLER_NAME)], LFP_NAME) == ([], "absent")
    assert resolve([], LFP_NAME) == ([], "absent") and resolve(None, LFP_NAME) == ([], "absent")
    assert resolve([loose, Role(9, "ranked looking for player")], LFP_NAME) == ([], "ambiguous")
    # several roles carry the exact name: each is mentioned, the oldest (lowest id) first, at most five
    twin, first = Role(11, GAMBLER_NAME), Role(10, GAMBLER_NAME)
    assert resolve([twin, Role(13, "gambler"), first], GAMBLER_NAME) == ([first, twin], "duplicate")
    seven = {rid: Role(rid, LFP_NAME) for rid in (27, 21, 25, 23, 22, 26, 24)}
    assert resolve(list(seven.values()) + [loose], LFP_NAME) == ([seven[i] for i in range(21, 26)], "duplicate")
    # both sites resolve through it: a role found by its normalised name alone is named and allowed
    w = World(tree, roles=[Role(2, "RankedLookingForPlayer", True), Role(12, "GAMBLER", True)])
    w.lfp()
    w.gambler()
    lfp_content, lfp_kw = one(w.queue.sent, "lfp posts")
    bet_content, bet_kw = one(w.bets.sent, "gambler posts")
    assert lfp_content.startswith("<@&2> ") and lfp_kw["allowed_mentions"].roles == [w.guild.roles[0]]
    assert bet_content.startswith("<@&12> ") and bet_kw["allowed_mentions"].roles == [w.guild.roles[1]]
    assert w.lines() == [
        "[PING] kind=lfp id=41 role=normalised mentioned=1 deliverable=yes listed=1 delivered=yes",
        "[PING] kind=gambler id=%s role=normalised mentioned=1 deliverable=yes listed=1 delivered=yes" % SID]
    # two normalised matches and no exact name at each site: no role is named and none is allowed (never a guess)
    w = World(tree, roles=[Role(2, "RankedLookingForPlayer", True), Role(9, "ranked looking for player", True),
                           Role(12, "GAMBLER", True), Role(13, "gambler", True)])
    w.lfp()
    w.gambler()
    lfp_content, lfp_kw = one(w.queue.sent, "lfp posts")
    bet_content, bet_kw = one(w.bets.sent, "gambler posts")
    assert lfp_content.startswith("@Ranked Looking For Player ") and lfp_kw["allowed_mentions"].roles is False
    assert bet_content.startswith("@Gambler ") and bet_kw["allowed_mentions"].roles is False
    assert [field(ln, "role") for ln in w.lines()] == ["ambiguous", "ambiguous"]
    # two roles of the exact name at each site (the integrator's ruling, 21 Nov 2026): both are named and
    # allowed, the oldest first, and no other role
    w = World(tree, roles=[Role(11, LFP_NAME, True), Role(1, LFP_NAME, True), Role(13, GAMBLER_NAME, True),
                           Role(12, GAMBLER_NAME, True), Role(3, "LookingForPlayer", True)])
    w.lfp()
    w.gambler()
    lfp_content, lfp_kw = one(w.queue.sent, "lfp posts")
    bet_content, bet_kw = one(w.bets.sent, "gambler posts")
    assert lfp_content.startswith("<@&1> <@&11> ") and lfp_content.count("<@&") == 2, lfp_content
    assert bet_content.startswith("<@&12> <@&13> ") and bet_content.count("<@&") == 2, bet_content
    assert [r.id for r in lfp_kw["allowed_mentions"].roles] == [1, 11]
    assert [r.id for r in bet_kw["allowed_mentions"].roles] == [12, 13]
    assert w.lines() == [
        "[PING] kind=lfp id=41 role=duplicate mentioned=2 deliverable=yes listed=2 delivered=yes",
        "[PING] kind=gambler id=%s role=duplicate mentioned=2 deliverable=yes listed=2 delivered=yes" % SID]
    # seven of them: the five oldest are named and allowed, and no other
    w = World(tree, roles=[Role(rid, LFP_NAME, True) for rid in (27, 21, 25, 23, 22, 26, 24)])
    w.lfp()
    content, kw = one(w.queue.sent, "lfp posts")
    assert content.startswith("<@&21> <@&22> <@&23> <@&24> <@&25> ") and content.count("<@&") == 5, content
    assert [r.id for r in kw["allowed_mentions"].roles] == [21, 22, 23, 24, 25]
    assert one(w.lines(), "seven") == \
        "[PING] kind=lfp id=41 role=duplicate mentioned=5 deliverable=yes listed=5 delivered=yes"


# -- R2: deliverable, read before the send -------------------------------------------------------

def check_r2(tree):
    deliverable = World(tree).ns["_ping_deliverable"]
    open_role, closed, open_twin = Role(1, LFP_NAME, True), Role(2, LFP_NAME, False), Role(3, LFP_NAME, True)

    def chan(me, allowed):
        return Channel(QUEUE, Guild([], Member(not allowed) if me else None), allowed)

    assert deliverable([open_role], chan(True, False)) == "yes"               # the role is mentionable
    c = chan(True, True)
    assert deliverable([closed], c) == "yes" and c.asked == [c.guild.me]       # the bot's member, this channel
    assert deliverable([closed], chan(True, False)) == "no"                    # guild level says yes, channel no
    assert deliverable([closed], chan(False, True)) == "unknown"               # no member object: never a yes
    assert deliverable([], chan(True, True)) == "yes" and deliverable([], chan(True, False)) == "no"
    assert deliverable([closed], None) == "unknown"
    # several roles: yes only when every one is mentionable, or by the permission
    assert deliverable([open_role, open_twin], chan(True, False)) == "yes"
    assert deliverable([open_role, closed], chan(True, False)) == "no"
    assert deliverable([closed, open_role], chan(True, True)) == "yes"

    class Unreadable(Channel):
        def permissions_for(self, member):
            raise RuntimeError("no permissions to read")

    assert deliverable([closed], Unreadable(QUEUE, Guild([], Member(True)), True)) == "unknown"
    for site in SITES:
        # the bot gains the permission only after the post: read before the send it is "no"
        w = World(tree, roles=[Role(1, LFP_NAME), Role(12, GAMBLER_NAME)], flip=True)
        w.run(site)
        assert one(w.lines(), site).endswith(" mentioned=1 deliverable=no listed=0 delivered=no"), w.lines()
        w = World(tree, roles=[Role(1, LFP_NAME), Role(12, GAMBLER_NAME)], mention_everyone=True)
        w.run(site)
        assert one(w.lines(), site).endswith(" mentioned=1 deliverable=yes listed=1 delivered=yes"), w.lines()
        w = World(tree, roles=[Role(1, LFP_NAME), Role(12, GAMBLER_NAME)], me=False, mention_everyone=True)
        w.run(site)
        assert one(w.lines(), site).endswith(" mentioned=1 deliverable=unknown listed=1 delivered=yes"), w.lines()
        # two roles of the exact name, one of them not mentionable, and the bot lacks the permission
        w = World(tree, roles=[Role(1, LFP_NAME, True), Role(11, LFP_NAME), Role(12, GAMBLER_NAME, True),
                               Role(13, GAMBLER_NAME)])
        w.run(site)
        assert one(w.lines(), site).endswith(" mentioned=2 deliverable=no listed=1 delivered=no"), w.lines()


# -- R3: delivered, from Discord's answer ---------------------------------------------------------

def check_r3(tree):
    delivered = World(tree).ns["_ping_delivered"]
    role, other, twin = Role(1, LFP_NAME), Role(2, "Other"), Role(11, LFP_NAME)
    ch = Channel(QUEUE, Guild([role, other, twin], Member(False)))
    said = Message(ch, role.mention + " hello", [role], 1)
    silent = Message(ch, role.mention + " hello", [], 2)      # our text names it; Discord's answer lists none
    elsewhere = Message(ch, role.mention, [other], 3)
    assert silent.raw_role_mentions == [1]                     # the fake's own text does carry the role
    assert delivered([role], said) == (1, "yes")
    assert delivered([role], silent) == (0, "no")
    assert delivered([role], elsewhere) == (0, "no")
    assert delivered([], said) == (0, "no") and delivered([role], None) == (0, "no")
    assert delivered([role], types.SimpleNamespace(content=role.mention)) == (0, "no")   # an answer with no list
    # several roles: yes only when the answer lists every one; a role listed twice counts once
    both = role.mention + " " + twin.mention + " hello"
    assert delivered([role, twin], Message(ch, both, [twin, role], 4)) == (2, "yes")
    assert delivered([role, twin], Message(ch, both, [role], 5)) == (1, "no")
    assert delivered([role, twin], Message(ch, both, [role, role], 6)) == (1, "no")
    assert delivered([role, twin], Message(ch, both, [], 7)) == (0, "no")
    for site in SITES:
        w = World(tree, roles=open_roles(), answer=discord_lists_none)
        w.run(site)
        assert one(w.lines(), site).endswith(" mentioned=1 deliverable=yes listed=0 delivered=no"), w.lines()
        assert "<@&" in one(w.channel(site).sent, site)[0]
        w = World(tree, roles=open_roles())
        w.run(site)
        assert one(w.lines(), site).endswith(" mentioned=1 deliverable=yes listed=1 delivered=yes"), w.lines()
        # Discord's answer lists one of two roles of the exact name
        w = World(tree, roles=open_roles() + [Role(11, LFP_NAME, True), Role(13, GAMBLER_NAME, True)],
                  answer=discord_lists_one)
        w.run(site)
        assert one(w.lines(), site).endswith(" mentioned=2 deliverable=yes listed=1 delivered=no"), w.lines()


# -- R4: the line and the warning -----------------------------------------------------------------

def check_r4(tree):
    w = World(tree)
    line, start = w.ns["_ping_line"], w.ns["_PING_STARTUP"]
    ids = ((41, "41"), (SID, SID), ("Bob <@&1> @here", "invalid"), ("startup", "invalid"),
           ("1" * 65, "invalid"), (True, "invalid"))
    counts = {"found": (1,), "normalised": (1,), "duplicate": (2, 3, 5), "absent": (0,), "ambiguous": (0,)}
    for kind in SITES:
        for role, options in counts.items():
            for mentioned in options:
                for dv in ("yes", "no", "unknown"):
                    for listed in range(mentioned + 1):
                        dd = "yes" if mentioned and listed == mentioned else "no"
                        for pid, shown in ids:
                            ln = line(kind, pid, role, mentioned, dv, listed, dd)
                            assert in_grammar(ln) and " id=%s " % shown in ln, ln
                    ln = line(kind, start, role, mentioned, dv, 0, "unsent")
                    assert in_grammar(ln) and " id=startup " in ln, ln
    for bad in (("lfp", 1, "found", 1, "maybe", 1, "yes"),          # a word outside its set
                ("casual", 1, "found", 1, "yes", 1, "yes"),
                ("lfp", 1, "guessed", 1, "yes", 1, "yes"),
                ("lfp", 1, "found", 1, "yes", 0, "unsent"),         # unsent is the startup line's alone
                ("lfp", start, "found", 1, "yes", 1, "yes"),
                ("lfp", start, "found", 1, "yes", 1, "unsent"),     # nothing listed at startup
                ("lfp", 1, "found", 2, "yes", 2, "yes"),            # mentioned agrees with the role word
                ("lfp", 1, "duplicate", 1, "yes", 1, "yes"),
                ("lfp", 1, "duplicate", 6, "yes", 6, "yes"),
                ("lfp", 1, "absent", 1, "no", 0, "no"),
                ("lfp", 1, "duplicate", 2, "yes", 3, "no"),         # listed is at most mentioned
                ("lfp", 1, "duplicate", 2, "yes", 1, "yes"),        # yes only when every role is listed
                ("lfp", 1, "found", 1, "yes", 1, "no"),
                ("lfp", 1, "absent", 0, "no", 0, "yes"),
                ("lfp", 1, "found", True, "yes", 1, "yes"),         # counts are whole numbers
                ("lfp", 1, "found", 1, "yes", "1", "yes")):
        assert _raises_value_error(line, *bad), bad
    # one line per post; all in order: no warning
    w = World(tree, roles=open_roles())
    w.lfp(PING, dict(PING, ping_id=42))
    assert w.lines() == ["[PING] kind=lfp id=41 role=found mentioned=1 deliverable=yes listed=1 delivered=yes",
                         "[PING] kind=lfp id=42 role=found mentioned=1 deliverable=yes listed=1 delivered=yes"]
    assert w.warnings() == []
    # the role absent: two posts that notified nobody, one warning, in the admin channel
    w = World(tree, roles=[Role(3, "LookingForPlayer", True)])
    w.lfp(PING, dict(PING, ping_id=42))
    nobody = "absent mentioned=0 deliverable=no listed=0 delivered=no"
    assert [ln.split(" role=")[1] for ln in w.lines()] == [nobody, nobody]
    assert len(w.queue.sent) == 2 and len(w.admin.sent) == 1, (w.queue.sent, w.admin.sent)
    warn, kw = w.admin.sent[0]
    am = kw["allowed_mentions"]
    assert (am.everyone, am.users, am.roles) == (False, False, False) and kw.get("suppress_embeds") is True
    assert "Ranked Looking For Player ping" in warn and "https://discord.com/channels/900/10/5001" in warn
    assert "**Cause: the role was not found.** No role in this server is named **Ranked Looking For Player**" in warn
    assert "**Fix:** Server Settings \u2192 Roles: give exactly one role the name **Ranked Looking For Player**." in warn
    for typed in ("Typed", "typed words", PING["discord_id"]):
        assert typed not in warn, typed
    # the bound: once per kind per 24 hours
    every = w.ns["PING_WARN_EVERY_S"]
    assert every == 24 * 60 * 60
    w.clock[0] += every - 1
    w.lfp(dict(PING, ping_id=43))
    assert len(w.admin.sent) == 1
    w.clock[0] += 1
    w.lfp(dict(PING, ping_id=44))
    assert len(w.admin.sent) == 2
    w.gambler()                                     # the Gambler ping's first warning is its own
    assert len(w.admin.sent) == 3 and "Gambler ping" in w.warnings()[2]
    for typed in ("Pat", "Quinn"):
        assert typed not in w.warnings()[2], typed
    # a warning Discord refused starts no bound: the next post that owes one warns
    w = World(tree, roles=[], admin_fails=1)
    w.lfp()
    assert w.admin.sent == [] and any(ln.startswith("[PING-CHECK] kind=lfp ") for ln in w.log), w.log
    w.lfp(dict(PING, ping_id=42))
    assert len(w.admin.sent) == 1
    # the role ambiguous: two normalised matches and no exact name
    w = World(tree, roles=[Role(2, "RankedLookingForPlayer"), Role(9, "ranked looking for player")])
    w.lfp()
    warn = one(w.warnings(), "ambiguous")
    assert ("**Cause: the role was not found.** 2 roles match the name **Ranked Looking For Player** with spaces "
            "and capitals ignored and none has exactly that name") in warn
    assert "give exactly one role the name **Ranked Looking For Player**" in warn
    # the configured name passes the name helper
    w = World(tree, roles=[], lfp_name="*Ranked* @everyone")
    w.lfp()
    assert "**\\*Ranked\\* \\@everyone**" in one(w.warnings(), "configured name")
    # deliverable no: the role is not mentionable and the bot lacks the permission in the channel
    w = World(tree, roles=[Role(1, "Ranked_Looking_For_Player")], lfp_name="Ranked_Looking_For_Player")
    w.lfp()
    warn = one(w.warnings(), "deliverable no")
    assert "**Cause: the bot may not mention the role.**" in warn
    assert "The role **Ranked\\_Looking\\_For\\_Player** is not mentionable" in warn
    assert PERMISSION in warn and "<#10> \u2192 Edit Channel \u2192 Permissions" in warn
    assert "The role stays closed to members." in warn
    assert "@everyone" not in warn and "@here" not in warn          # the permission's name cannot mention
    # deliverable no, and Discord's answer lists the role all the same: the warning is owed (the integrator's
    # ruling, 21 Nov 2026), for by Discord's rule the ping notified nobody
    for site in SITES:
        w = World(tree, roles=[Role(1, LFP_NAME), Role(12, GAMBLER_NAME)], answer=discord_lists_written)
        w.run(site)
        assert one(w.lines(), site).endswith(" role=found mentioned=1 deliverable=no listed=1 delivered=yes")
        assert "**Cause: the bot may not mention the role.**" in one(w.warnings(), "deliverable no, " + site)
    # delivered no: the check said yes, Discord's answer lists no role
    w = World(tree, roles=open_roles(), answer=discord_lists_none)
    w.lfp()
    warn = one(w.warnings(), "delivered no")
    assert "**Cause: Discord did not mention the role.**" in warn and "could not read" not in warn
    # delivered no when the bot could not tell
    w = World(tree, roles=[Role(1, LFP_NAME)], me=False)
    w.lfp()
    warn = one(w.warnings(), "delivered no, unknown")
    assert "**Cause: Discord did not mention the role.**" in warn
    assert "(the bot could not read its own permissions there)" in warn
    # several roles of the exact name (the integrator's ruling, 21 Nov 2026): a warning though Discord's answer
    # lists every one, with the count and the fix; the name through the name helper; it mentions nobody
    dup = "Ranked_Looking_For_Player"
    w = World(tree, roles=[Role(11, dup, True), Role(1, dup, True)], lfp_name=dup)
    w.lfp()
    assert one(w.lines(), "twins").endswith(" role=duplicate mentioned=2 deliverable=yes listed=2 delivered=yes")
    warn, kw = one(w.admin.sent, "twins")
    am = kw["allowed_mentions"]
    assert (am.everyone, am.users, am.roles) == (False, False, False)
    assert ("**Cause: 2 roles have the same name.** Each is named **Ranked\\_Looking\\_For\\_Player**, and the post "
            "mentioned every one of them.") in warn
    assert ("**Fix:** Server Settings \u2192 Roles: rename or remove the extra roles, so that one role alone is "
            "named **Ranked\\_Looking\\_For\\_Player**.") in warn
    assert "Cause: the bot may not" not in warn and "Cause: Discord did not" not in warn
    # seven of them, and Discord's answer lists none: the five oldest were mentioned; both findings
    w = World(tree, roles=[Role(rid, LFP_NAME) for rid in range(27, 20, -1)], mention_everyone=True,
              answer=discord_lists_none)
    w.lfp()
    assert one(w.lines(), "seven").endswith(" role=duplicate mentioned=5 deliverable=yes listed=0 delivered=no")
    warn = one(w.warnings(), "seven")
    assert "**Cause: 7 roles have the same name.**" in warn
    assert "the post mentioned the 5 oldest of them (one ping mentions at most 5)." in warn
    assert "**Cause: Discord did not mention every role.**" in warn
    # a twin that is not mentionable, and the bot lacks the permission: both findings
    w = World(tree, roles=[Role(1, LFP_NAME, True), Role(11, LFP_NAME)])
    w.lfp()
    assert one(w.lines(), "closed twin").endswith(" role=duplicate mentioned=2 deliverable=no listed=1 delivered=no")
    warn = one(w.warnings(), "closed twin")
    assert "**Cause: 2 roles have the same name.**" in warn
    assert "**Cause: the bot may not mention every role.**" in warn and "The roles stay closed to members." in warn
    # no new setting: the ping code reads no environment key
    for fn in tree.body:
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name.startswith("_ping_"):
            src = ast.unparse(fn)
            assert "getenv" not in src and "environ" not in src, fn.name


# -- R5: the startup line --------------------------------------------------------------------------

def check_r5(tree):
    ready = one([n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_ready"], "on_ready")
    stmts = [ast.unparse(s) for s in ready.body]
    assert stmts.count("asyncio.create_task(_ping_startup_lines())") == 1, "on_ready does not start it"
    assert stmts.index("asyncio.create_task(_ping_startup_lines())") < len(stmts) - 1
    calls = [c for _fn, c in _calls_by_function(tree)
             if isinstance(c.func, ast.Name) and c.func.id == "_ping_startup_lines"]
    assert len(calls) == 1
    w = World(tree, roles=[Role(2, "RankedLookingForPlayer"), Role(12, GAMBLER_NAME, True)])
    w.startup()
    assert w.lines() == [
        "[PING] kind=lfp id=startup role=normalised mentioned=1 deliverable=no listed=0 delivered=unsent",
        "[PING] kind=gambler id=startup role=found mentioned=1 deliverable=yes listed=0 delivered=unsent"]
    assert w.queue.sent == [] and w.bets.sent == [] and w.admin.sent == []
    w.startup()                                     # on_ready fires again on a resume: nothing more
    assert len(w.lines()) == 2
    # a channel the bot cannot reach still gets its line, which says it cannot tell
    absent = "[PING] kind=lfp id=startup role=absent mentioned=0 deliverable=unknown listed=0 delivered=unsent"
    w = World(tree, roles=[Role(1, LFP_NAME, True)], queue_id=31)
    w.startup()
    assert w.lines()[0] == absent
    assert any(ln.startswith("[PING-CHECK] kind=lfp startup: channel 31 unavailable") for ln in w.log), w.log
    w = World(tree, roles=[Role(1, LFP_NAME, True)], queue_id=0)
    w.startup()
    assert w.lines()[0] == absent
    assert "[PING-CHECK] kind=lfp startup: no channel configured" in w.log


# -- R6: nothing else moves -------------------------------------------------------------------------

def check_r6(tree):
    w = World(tree, roles=open_roles())
    w.lfp()
    content, kw = one(w.queue.sent, "lfp posts")
    assert content == EXPECTED_LFP, content
    assert set(kw) == {"suppress_embeds", "allowed_mentions"} and kw["suppress_embeds"] is True
    am = kw["allowed_mentions"]
    assert (am.everyone, am.users, am.roles) == (False, False, [w.guild.roles[0]])
    assert w.acks == [([41], False), ([], True)] and 41 in w.seen
    assert "[LFP] posted ping 41 for Typed*Name" in w.log
    w.gambler()
    body, kw = one(w.bets.sent, "gambler posts")
    assert body == EXPECTED_BET, body
    am = kw["allowed_mentions"]
    assert set(kw) == {"allowed_mentions"} and (am.everyone, am.users, am.roles) == (False, False, [w.guild.roles[1]])
    # a ping that cannot notify still goes out, is acked as posted, and is not retried
    w = World(tree, roles=[Role(1, LFP_NAME)])
    w.lfp()
    assert len(w.queue.sent) == 1 and w.acks == [([41], False), ([], True)]
    w.lfp()                                         # served again before its ack lands: re-acked, not re-posted
    assert len(w.queue.sent) == 1 and w.acks[2] == ([41], False)
    # a warning that fails moves nothing
    w = World(tree, roles=[], admin_fails=5)
    w.lfp()
    assert len(w.queue.sent) == 1 and w.acks == [([41], False), ([], True)]
    w = World(tree, roles=[], admin_fails=5)
    w.gambler()
    assert len(w.bets.sent) == 1 and SID in w.ns["_gambler_pinged"]


# -- R7: no other role is pinged ------------------------------------------------------------------

def check_r7(tree):
    widened = []
    for fn, call in _calls_by_function(tree):
        f = call.func
        name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
        if name == "all" and isinstance(f, ast.Attribute) and ast.unparse(f.value).endswith("AllowedMentions"):
            widened.append((fn, "AllowedMentions.all()"))
        if name != "AllowedMentions":
            continue
        roles = [k.value for k in call.keywords if k.arg == "roles"]
        if not roles or not (isinstance(roles[0], ast.Constant) and roles[0].value is False):
            widened.append((fn, ast.unparse(roles[0]) if roles else "(the default: every role)"))
    assert sorted(widened) == [("poll_gambler_pings", "list(ping_roles) if ping_roles else False"),
                               ("poll_lfp_pings", "list(ping_roles) if ping_roles else False")], widened
    casual = [Role(3, "LookingForPlayer", True), Role(14, "Looking For Player", True)]
    w = World(tree, roles=open_roles() + casual)
    w.lfp()
    content, kw = one(w.queue.sent, "lfp posts")
    assert kw["allowed_mentions"].roles == [w.guild.roles[0]]
    assert all(r.mention not in content for r in casual)


CHECKS = {"R1": check_r1, "R2": check_r2, "R3": check_r3, "R4": check_r4, "R5": check_r5, "R6": check_r6,
          "R7": check_r7}


@pytest.mark.parametrize("req", sorted(CHECKS))
def test_each_requirement_holds(req):
    CHECKS[req](BASE_TREE)


# (requirement, what the edit does, the text it replaces, the new text). Each must turn its check red.
MUTANTS = [
    ("R1", "the Gambler site keeps the library's exact-name lookup",
     "ping_roles, role_word = _ping_role_resolve(guild.roles if guild else (), GAMBLER_ROLE_NAME)",
     "ping_roles, role_word = [r for r in [discord.utils.get(guild.roles, name=GAMBLER_ROLE_NAME)] if r] "
     "if guild else [], \"found\""),
    ("R1", "two normalised matches resolved as a guess",
     "    if len(loose) == 1:\n", "    if len(loose) >= 1:\n"),
    ("R1", "lower() in place of casefold()",
     'folded = str(text or "").casefold()', 'folded = str(text or "").lower()'),
    ("R1", "several roles of the exact name mention none (the first build)",
     '        return sorted(exact, key=lambda r: r.id)[:PING_ROLES_MAX], "duplicate"\n',
     '        return [], "ambiguous"\n'),
    ("R1", "one role of the exact name mentioned, not each",
     "sorted(exact, key=lambda r: r.id)[:PING_ROLES_MAX]", "sorted(exact, key=lambda r: r.id)[:1]"),
    ("R1", "no bound on the roles one ping mentions",
     "sorted(exact, key=lambda r: r.id)[:PING_ROLES_MAX]", "sorted(exact, key=lambda r: r.id)"),
    ("R1", "the roles in the server's order, not the oldest first",
     "sorted(exact, key=lambda r: r.id)[:PING_ROLES_MAX]", "exact[:PING_ROLES_MAX]"),
    ("R2", "no member object read as a yes",
     '    if me is None:\n        return "unknown"\n', '    if me is None:\n        return "yes"\n'),
    ("R2", "the guild-level permission in place of the channel's",
     "perms = channel.permissions_for(me)", "perms = me.guild_permissions"),
    ("R2", "deliverable read again after the send",
     "        listed, delivered = _ping_delivered(roles, message)\n",
     "        deliverable = _ping_deliverable(roles, channel)\n"
     "        listed, delivered = _ping_delivered(roles, message)\n"),
    ("R2", "one mentionable role taken for all of them",
     'if roles and all(getattr(r, "mentionable", None) is True for r in roles):',
     'if roles and any(getattr(r, "mentionable", None) is True for r in roles):'),
    ("R3", "raw_role_mentions, a pattern over the bot's own text",
     'answered = {getattr(r, "id", None) for r in (getattr(message, "role_mentions", None) or ())}',
     "answered = set(message.raw_role_mentions)"),
    ("R3", "the roles' mentions looked for in the content",
     'answered = {getattr(r, "id", None) for r in (getattr(message, "role_mentions", None) or ())}',
     'answered = {r.id for r in roles if r.mention in (message.content or "")}'),
    ("R3", "yes when the answer lists any one of the roles",
     '("yes" if listed == len(roles) else "no")', '("yes" if listed else "no")'),
    ("R4", "an id that is not checked against the grammar",
     '        if not _PING_ID_RE.fullmatch(shown):\n            shown = "invalid"\n', ""),
    ("R4", "a count not checked against its role word",
     '    if type(mentioned) is not int or not least <= mentioned <= most:\n        raise ValueError("mentioned")\n',
     ""),
    ("R4", "delivered not checked against the counts",
     '    elif (delivered == "yes") != (mentioned > 0 and listed == mentioned):\n'
     '        raise ValueError("delivered")\n', ""),
    ("R4", "no warning when the check before the send says no (the first build's condition)",
     ' or deliverable == "no" or delivered != "yes"', ' or delivered != "yes"'),
    ("R4", "no warning for several roles of the exact name that Discord's answer lists",
     '("absent", "ambiguous", "duplicate")', '("absent", "ambiguous")'),
    ("R4", "the warning counts the roles mentioned, not the roles that carry the name",
     "count = max(len(exact), len(roles))", "count = len(roles)"),
    ("R4", "the 24-hour bound dropped",
     "    if last is not None and now - last < PING_WARN_EVERY_S:\n        return False\n", ""),
    ("R4", "the post's own text, a player's name and message, in the warning",
     '    lines.append("At most one such warning',
     '    lines.append(str(getattr(message, "content", "")))\n    lines.append("At most one such warning'),
    ("R4", "the role's name shown raw",
     "shown = _escape_md(role.name, 100)", "shown = role.name"),
    ("R4", "the configured name shown raw",
     "cfg = _escape_md(configured, 100)", "cfg = configured"),
    ("R4", "the warning posted in the ping's own channel",
     "admin = bot.get_channel(ADMIN_CHANNEL_ID) or await bot.fetch_channel(ADMIN_CHANNEL_ID)",
     "admin = channel"),
    ("R5", "on_ready does not start the startup lines",
     "    asyncio.create_task(_ping_startup_lines())\n", ""),
    ("R5", "the startup lines printed on every ready",
     "    if _ping_startup_done:\n        return\n", ""),
    ("R6", "a post that cannot notify held back",
     "                sent = await channel.send(\n                    content[:2000],\n",
     "                if deliverable == \"no\":\n                    raise RuntimeError(\"held back\")\n"
     "                sent = await channel.send(\n                    content[:2000],\n"),
    ("R6", "the warning sent before the ack",
     "                _lfp_seen_ids.add(ping_id)\n                posted.append(ping_id)\n"
     "                print(f\"[LFP] posted ping {ping_id} for {display_name}\")\n",
     "                await _ping_warn(\"lfp\", LFP_ROLE_NAME, ping_roles, role_word, deliverable, \"no\", channel, "
     "sent)\n"
     "                _lfp_seen_ids.add(ping_id)\n                posted.append(ping_id)\n"
     "                print(f\"[LFP] posted ping {ping_id} for {display_name}\")\n"),
    ("R6", "the LFP post allows every role",
     "everyone=False, roles=list(ping_roles) if ping_roles else False, users=False),",
     "everyone=False, roles=True, users=False),"),
    ("R7", "the casual role pinged beside the ranked one",
     "everyone=False, roles=list(ping_roles) if ping_roles else False, users=False),",
     "everyone=False, roles=list(ping_roles) + [r for r in channel.guild.roles "
     "if _ping_role_norm(r.name) == \"lookingforplayer\"] or False, users=False),"),
]


@pytest.mark.parametrize("req,what,old,new", MUTANTS, ids=["%s: %s" % (m[0], m[1]) for m in MUTANTS])
def test_each_mutant_turns_its_requirement_red(req, what, old, new):
    tree, shipped, edited = mutate(old, new)
    assert [ast.dump(n) for n in edited] != [ast.dump(shipped)], "the edit changes no code: %s" % what
    try:
        CHECKS[req](tree)
    except AssertionError:
        return
    raise AssertionError("the mutant left %s green: %s" % (req, what))


def test_every_requirement_has_a_mutant():
    assert sorted({m[0] for m in MUTANTS}) == sorted(CHECKS)


def test_control_a_comment_only_edit_keeps_every_requirement_green():
    anchor = "def _ping_role_norm(text) -> str:\n"
    tree, shipped, edited = mutate(anchor, "# control: a comment only, no behaviour\n" + anchor)
    assert tree is not BASE_TREE and edited[0] is not shipped
    assert [ast.dump(n) for n in edited] == [ast.dump(shipped)]
    for req in sorted(CHECKS):
        CHECKS[req](tree)
