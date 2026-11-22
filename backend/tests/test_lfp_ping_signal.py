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
     warning per kind per 24 hours (counted from the time Discord accepted
     the last one) when one is owed: the role absent, ambiguous or
     duplicate, deliverable no, or delivered not yes;
  R5 print the same line per kind with id=startup once after ready, and
     hold the first ping of a kind until its line has printed, at most
     PING_STARTUP_WAIT_S, never dropping it;
  R6 change nothing else: the content, the allowed mentions and the ack,
     which no warning I/O (the warning is its own task) and no failing
     print delays or stops;
  R7 ping no other role.

discord_bot.py builds the bot at import, so, as in test_bot_text_escape.py,
what runs here is lifted out of its AST and run against fakes: no network,
no database. Each requirement is one check function. MUTANTS holds at least
one source edit per requirement that must turn its check red (FAILS_AT
names, for the mutants of the first review round, the assertion each must
fail first), and the control (a comment-only edit) leaves every check
green. An edit is made in
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
FUNCS = ("_ping_log", "_ping_role_norm", "_ping_role_matches", "_ping_role_resolve", "_ping_deliverable",
         "_ping_delivered", "_ping_line", "_ping_warning_text", "_ping_warn", "_ping_warn_start", "_ping_warn_done",
         "_ping_warning_owed", "_ping_after_send", "_ping_startup_lines", "_ping_startup_wait", "poll_lfp_pings",
         "poll_gambler_pings", "_escape_md", "_escape_text", "_md_name", "_lfp_render_message",
         "_ping_resolved_line")
ASSIGNS = ("PING_WARN_EVERY_S", "PING_ROLES_MAX", "PING_STARTUP_WAIT_S", "PING_STARTUP_STEP_S", "_PING_STARTUP",
           "_PING_ID_RE", "_PING_WORDS", "_PING_MENTIONS", "_PING_KIND_SHOWN", "_PING_ROLE_ENV", "_PING_PERMISSION",
           "_ping_warned_at",
           "_ping_warn_tasks", "_ping_startup_done", "_ping_startup_settled", "_ping_startup_waited",
           "_LFP_EMOJI_TOKEN", "_PING_HINT_WORDS", "PING_HINTS_MAX") + HELPER_PARTS

# The [PING] line, whole. id=startup goes with delivered=unsent and listed=0;
# mentioned agrees with the role word, listed is at most mentioned, and
# delivered is yes exactly when roles were mentioned and the answer lists all.
# kind=casual is the LFP post's casual role (LFP-CASUAL-1, test_lfp_casual.py).
GRAMMAR = re.compile(
    r"\[PING\] kind=(lfp|casual|gambler) id=(startup|[0-9a-f-]{1,64}|invalid) "
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


class Unreadable:
    """An answer whose role mentions cannot be read: the check after the post
    fails, so the check's own fallback line runs."""

    def __init__(self, channel, content, mid):
        self.id, self.channel, self.content = mid, channel, content
        self.jump_url = "https://discord.com/channels/%d/%d/%d" % (channel.guild.id, channel.id, mid)

    @property
    def role_mentions(self):
        raise RuntimeError("the answer cannot be read")


def discord_unreadable(channel, content, kw):
    """No list: Channel.send answers with an Unreadable message."""
    return None


class Channel:
    """A text channel. `answer` gives the roles Discord's answer lists (its
    rule by default). With `flip` the bot's permission here changes right
    after each post, so a check read after the send reads another answer. A
    send first lets the loop run its other tasks once (the request), then is
    accepted and noted in `events`."""

    def __init__(self, cid, guild, mention_everyone=False, answer=discord_rule, flip=False, events=None):
        self.id, self.guild = cid, guild
        self.mention = "<#%d>" % cid
        self.mention_everyone = mention_everyone
        self.answer, self.flip = answer, flip
        self.sent, self.asked = [], []
        self.events = [] if events is None else events

    def permissions_for(self, member):
        self.asked.append(member)
        return Perms(self.mention_everyone)

    async def send(self, content=None, **kw):
        await asyncio.sleep(0)
        self.sent.append((content, kw))
        self.events.append("post %d" % self.id)
        listed, mid = self.answer(self, content, kw), 5000 + len(self.sent)
        msg = Unreadable(self, content, mid) if listed is None else Message(self, content, listed, mid)
        if self.flip:
            self.mention_everyone = not self.mention_everyone
        return msg


class AdminChannel:
    """The admin channel. Its first `fails` sends are refused; each send moves
    the bot's clock by `delay` seconds before Discord accepts it."""

    def __init__(self, fails=0, events=None, clock=None, delay=0.0):
        self.sent, self.fails, self.clock, self.delay = [], fails, clock, delay
        self.events = [] if events is None else events

    async def send(self, content=None, **kw):
        if self.fails:
            self.fails -= 1
            raise RuntimeError("the admin channel refused the post")
        if self.clock is not None:
            self.clock[0] += self.delay
        self.sent.append((content, kw))


class BlockingAdmin(AdminChannel):
    """An admin channel whose send waits until `release`, an asyncio.Event the
    test makes inside its running loop, is set (M1)."""

    release = None

    async def send(self, content=None, **kw):
        self.events.append("admin-start")
        await self.release.wait()
        self.events.append("admin-done")
        await AdminChannel.send(self, content, **kw)


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
    """The client as the two loops read it. A channel id in `slow` is not in
    the cache, and its FIRST fetch (the startup line's, M2) waits until
    `release`, an asyncio.Event made inside the running loop, is set; every
    later fetch answers at once."""

    def __init__(self, channels, slow=()):
        self.channels, self.slow, self.release, self.fetched = dict(channels), set(slow), None, []

    def get_channel(self, cid):
        return None if cid in self.slow else self.channels.get(cid)

    async def fetch_channel(self, cid):
        first = cid in self.slow and cid not in self.fetched
        self.fetched.append(cid)
        if first:
            await self.release.wait()
        if cid in self.channels:
            return self.channels[cid]
        raise NotFound("unknown channel")


QUEUE, BETS, ADMIN = 10, 20, 77
LFP_NAME, GAMBLER_NAME = "Ranked Looking For Player", "Gambler"
CASUAL_NAME = "LookingForPlayer"      # LFP_CASUAL_ROLE's default (LFP-CASUAL-1)
PERMISSION = "Mention @\u200beveryone, @\u200bhere, and All Roles"
PING = {"ping_id": 41, "discord_id": "123456789012345678", "display_name": "Typed*Name",
        "message": "typed words", "expires_unix": 1763700000, "modes": "1v1", "expires_minutes": 60}
SID = "3f2a9c1e-0000-4000-8000-00000000abcd"
SERIES = {"series_id": SID, "p1_name": "Pat*One", "p2_name": "Quinn_Two", "bets_locked": False}
SERIES_2 = dict(SERIES, series_id="3f2a9c1e-0000-4000-8000-00000000abce")
SITES = ("lfp", "gambler")
# main's text for the two posts (the role at id 1 and id 12, the fakes above)
EXPECTED_LFP = ("<@&1> \N{LEFT-POINTING MAGNIFYING GLASS} **Typed\\*Name** (<@123456789012345678>) "
                "LFP: ranked 1v1 for 1h!\n> typed words\nExpires <t:1763700000:R>")
EXPECTED_BET = "<@&12> \U0001F3B2 Bets are open \u2014 **Pat\\*One** vs **Quinn\\_Two**! Place yours below."


def open_roles():
    return [Role(1, LFP_NAME, True), Role(12, GAMBLER_NAME, True)]


class World:
    """One server: a guild with `roles`, the queue channel, the bets channel
    and the admin channel, and the lifted bot code over them. The bot's clock
    moves in its asyncio.sleep, by the seconds asked, and in an admin send
    (`admin_delay`); each printed line keeps the clock's reading (`stamps`).
    `events` is the order in which posts were accepted, the LFP ack ran and a
    blocking admin send began and ended. By default both startup lines have
    printed, as after ready; `startup_printed=False` starts before them. A
    print of a line that begins with `print_fails` raises."""

    def __init__(self, tree=BASE_TREE, roles=(), me=True, mention_everyone=False, answer=discord_rule, flip=False,
                 admin_fails=0, queue_id=QUEUE, lfp_name=LFP_NAME, gambler_name=GAMBLER_NAME, admin_blocks=False,
                 admin_delay=0.0, slow=(), startup_printed=True, print_fails=None, casual_name=CASUAL_NAME):
        self.log, self.stamps, self.events, self.acks, self.seen, self.clock = [], [], [], [], set(), [1000.0]
        self.pings, self.series, self.paths = [], [], []
        self.guild = Guild(roles, Member(not mention_everyone) if me else None)
        self.queue = Channel(QUEUE, self.guild, mention_everyone, answer, flip, self.events)
        self.bets = Channel(BETS, self.guild, mention_everyone, answer, flip, self.events)
        self.admin = (BlockingAdmin if admin_blocks else AdminChannel)(admin_fails, self.events, self.clock,
                                                                        admin_delay)
        self.bot = Bot({QUEUE: self.queue, BETS: self.bets, ADMIN: self.admin}, slow)

        async def api_get(path, timeout=8.0):
            # The api as LFP-CASUAL-1 left it: a row naming casual only for a
            # poller that declares the casual kind.
            self.paths.append(path)
            if path == "/internal/lfp-pings?kinds=casual":
                return {"pings": [dict(p) for p in self.pings]}
            if path == "/internal/lfp-pings":
                return {"pings": [dict(p) for p in self.pings
                                  if "casual" not in str(p.get("modes") or "").split(",")]}
            if path == "/series/active":
                return [dict(s) for s in self.series]
            return None

        async def ack(ids, undeliverable=False):
            self.acks.append((list(ids), bool(undeliverable)))
            self.events.append("ack")

        async def noop(*a, **k):
            return None

        async def sleep(seconds=0, *a, **k):
            self.clock[0] += seconds
            await asyncio.sleep(0)

        def say(*a, **k):
            line = " ".join(str(x) for x in a)
            if print_fails is not None and line.startswith(print_fails):
                raise OSError(32, "Broken pipe")
            self.log.append(line)
            self.stamps.append(self.clock[0])

        self.ns = lift(tree, {
            "discord": DISCORD, "bot": self.bot, "api_get": api_get, "_ack_lfp_pings": ack,
            "_lfp_seen_ids": self.seen, "asyncio": types.SimpleNamespace(sleep=sleep, create_task=asyncio.create_task),
            "time": types.SimpleNamespace(monotonic=lambda: self.clock[0]), "print": say,
            "QUEUE_BEACON_CHANNEL_ID": queue_id, "LIVE_BETS_CHANNEL_ID": BETS, "ADMIN_CHANNEL_ID": ADMIN,
            "LFP_ROLE_NAME": lfp_name, "GAMBLER_ROLE_NAME": gambler_name, "LFP_CASUAL_ROLE_NAME": casual_name,
            "_gambler_signup_checked": True, "_gambler_seeded": True, "_gambler_pinged": set(),
            "_ensure_gambler_signup_message": noop,
        })
        if startup_printed:
            self.ns["_ping_startup_settled"].update(SITES + ("casual",))

    async def settle(self):
        """Waits for every other task the run started (the warnings): the bot's
        loop runs on, where asyncio.run would cancel them."""
        while True:
            rest = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            if not rest:
                return
            await asyncio.gather(*rest)

    def _run(self, name):
        async def go():
            await self.ns[name]()
            await self.settle()
        asyncio.run(go())

    def poll(self, site):
        """The site's poll, as a coroutine, for a test that drives the loop."""
        return self.ns["poll_lfp_pings" if site == "lfp" else "poll_gambler_pings"]()

    def lfp(self, *pings):
        self.pings = list(pings or (PING,))
        self._run("poll_lfp_pings")

    def gambler(self, *series):
        self.series = list(series or (SERIES,))
        self._run("poll_gambler_pings")

    def run(self, site):
        (self.lfp if site == "lfp" else self.gambler)()

    def channel(self, site):
        return self.queue if site == "lfp" else self.bets

    def startup(self):
        self._run("_ping_startup_lines")

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
    # every digit stays, not only the decimal ones (L2): a lone role named Gambler with a superscript two
    assert resolve([Role(33, GAMBLER_NAME + "\N{SUPERSCRIPT TWO}")], GAMBLER_NAME) == ([], "absent"), \
        "L2: a role named Gambler with a superscript two resolved for Gambler"
    # an empty normalised form names nothing and matches nothing (L3, not a defect: a match on nothing would be a
    # guess); the exact name still finds a role so named
    assert resolve([Role(31, "???")], "!!!") == ([], "absent"), "L3: an empty normalised form matched another"
    marks = Role(32, "!!!")
    assert resolve([Role(31, "???"), marks], "!!!") == ([marks], "found")
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
    # M5, not a defect: a mentionable role notifies whatever the bot's member is, so R2's first arm answers yes
    # with no member object; "unknown" belongs to the permission arm alone
    assert deliverable([open_role], chan(False, False)) == "yes" and \
        deliverable([open_role, open_twin], chan(False, False)) == "yes", \
        "M5: mentionable roles with no member object did not read yes"
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
        w = World(tree, roles=open_roles(), me=False)                          # M5: mentionable, no member object
        w.run(site)
        assert one(w.lines(), site).endswith(" mentioned=1 deliverable=yes listed=1 delivered=yes"), w.lines()
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
                ("raffle", 1, "found", 1, "yes", 1, "yes"),
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
    # the bound counts from the time Discord accepted the warning, read after the send (M4): a send that takes ten
    # minutes of the bot's clock moves the bound by ten minutes
    w = World(tree, roles=[], admin_delay=600.0)
    w.lfp()
    accepted = w.stamps[w.log.index("[PING-WARN] kind=lfp warning posted to the admin channel")]
    w.clock[0] = accepted - 600.0 + every + 1           # a day and a second after the send began
    w.lfp(dict(PING, ping_id=42))
    assert len(w.admin.sent) == 1, "M4: the bound ran from before Discord accepted the warning"
    w.clock[0] = accepted + every                       # a day after Discord accepted it
    w.lfp(dict(PING, ping_id=43))
    assert len(w.admin.sent) == 2
    # a warning Discord refused starts no bound: the next post that owes one warns
    w = World(tree, roles=[], admin_fails=1)
    w.lfp()
    assert w.admin.sent == [] and "[PING-CHECK] kind=lfp warning failed: RuntimeError" in w.log, w.log
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

def _startup_race(tree, site, release_after):
    """M2: one ping is pending at `site` while the startup line's fetch of
    that site's channel (not in the cache) waits. The fetch is let go once the
    bot's clock has run `release_after` seconds since the poll began (None:
    only after the poll has ended). Answers the World, the clock when the poll
    began, and the log index of the ping's own [PING] line."""
    w = World(tree, roles=open_roles(), slow=(QUEUE if site == "lfp" else BETS,), startup_printed=False)
    w.pings, w.series = [PING], [SERIES]
    began = w.clock[0]

    async def go():
        w.bot.release = asyncio.Event()
        startup = asyncio.ensure_future(w.ns["_ping_startup_lines"]())     # on_ready's task
        await asyncio.sleep(0)                                             # it reaches its fetch
        poll = asyncio.ensure_future(w.poll(site))
        for _ in range(400):
            if poll.done():
                break
            if release_after is not None and w.clock[0] - began >= release_after:
                w.bot.release.set()
            await asyncio.sleep(0)
        assert poll.done(), "M2: the %s ping was held past the bound" % site
        poll.result()
        w.bot.release.set()
        await startup
        await w.settle()

    asyncio.run(go())
    pid = "41" if site == "lfp" else SID
    posts = [i for i, ln in enumerate(w.log) if ln.startswith("[PING] kind=%s id=%s " % (site, pid))]
    assert len(posts) == 1, "M2: the %s ping was dropped" % site
    return w, began, posts[0]


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
        "[PING] kind=casual id=startup role=absent mentioned=0 deliverable=no listed=0 delivered=unsent",
        "[PING] kind=gambler id=startup role=found mentioned=1 deliverable=yes listed=0 delivered=unsent"]
    assert w.queue.sent == [] and w.bets.sent == [] and w.admin.sent == []
    w.startup()                                     # on_ready runs again on a new READY: nothing more
    assert len(w.lines()) == 3
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
    # the first ping of a kind waits for that kind's startup line (M2), at most the bound, and is never dropped
    bound = World(tree).ns["PING_STARTUP_WAIT_S"]
    assert 0 < bound <= 15
    for site in SITES:
        first = "[PING] kind=%s id=startup " % site
        # the startup line prints 2 s after the poll began: the ping waits for it
        w, began, post = _startup_race(tree, site, 2.0)
        starts = [i for i, ln in enumerate(w.log) if ln.startswith(first)]
        assert len(starts) == 1 and starts[0] < post, "M2: the %s ping posted before its startup line" % site
        assert 2.0 <= w.stamps[post] - began <= bound and not any(" not printed " in ln for ln in w.log), w.log
        # it does not print inside the bound: the ping posts when the bound passes, after a line that says the
        # startup line had not printed, held no longer than the bound; the startup line prints later, once
        w, began, post = _startup_race(tree, site, None)
        late = "[PING-CHECK] kind=%s startup line not printed within %d s: the ping posts without it" % (site, bound)
        assert w.log.count(late) == 1 and w.log.index(late) < post, \
            "M2: no line said the %s startup line had not printed" % site
        assert w.stamps[post] - began == bound, "M2: the %s ping was held %r s" % (site, w.stamps[post] - began)
        starts = [i for i, ln in enumerate(w.log) if ln.startswith(first)]
        assert len(starts) == 1 and starts[0] > post, w.log
        if site == "lfp":
            assert w.acks == [([41], False), ([], True)], w.acks
        else:
            assert len(w.bets.sent) == 1 and SID in w.ns["_gambler_pinged"]


# -- R6: nothing else moves -------------------------------------------------------------------------

def _warning_held(tree, site):
    """M1: the admin channel's send blocks until released, and two posts at
    `site` each owe a warning (no role carries the name). The poll ends, its
    next post and the LFP ack made, while that send is blocked; the warning
    completes after the release; the second, owed while the first was in
    flight, is skipped, not queued. Answers the World."""
    w = World(tree, roles=[], admin_blocks=True)
    w.pings, w.series = [PING, dict(PING, ping_id=42)], [SERIES, SERIES_2]
    post = "post %d" % w.channel(site).id
    order = [post, "admin-start", post] + (["ack", "ack"] if site == "lfp" else [])

    async def go():
        w.admin.release = asyncio.Event()
        poll = asyncio.ensure_future(w.poll(site))
        for _ in range(100):
            if poll.done():
                break
            await asyncio.sleep(0)
        assert poll.done(), "M1: the %s poll waits for the admin channel" % site
        poll.result()
        assert w.events == order, "M1: at %s the posts, the ack and the warning ran as %r" % (site, w.events)
        held = w.ns["_ping_warn_tasks"].get(site)
        assert held is not None and not held.done() and w.admin.sent == [], \
            "M1: the %s warning is not held while its send is blocked" % site
        w.admin.release.set()
        await w.settle()
        assert w.events == order + ["admin-done"] and len(w.admin.sent) == 1, \
            "M1: the %s warning did not complete once, after the release: %r" % (site, w.events)
        assert w.ns["_ping_warn_tasks"] == {}, "M1: the %s warning's reference outlived it" % site

    asyncio.run(go())
    return w


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
    # the warning is its own task (M1): while the admin channel's send is blocked, the next post at each site and
    # the LFP ack go out; the warning completes after the release; a second one owed meanwhile is skipped
    for site in SITES:
        w = _warning_held(tree, site)
        assert "[PING-WARN] kind=%s warning posted to the admin channel" % site in w.log, w.log
    # no failing print stops anything (L1): every line of the ping check fails to print, and Discord's answer
    # cannot be read, so the check's own fallback line runs
    for site in SITES:
        w = World(tree, roles=open_roles(), answer=discord_unreadable, print_fails="[PING")
        try:
            if site == "lfp":
                w.lfp(PING, dict(PING, ping_id=42))
            else:
                w.gambler(SERIES, SERIES_2)
        except Exception as ex:
            raise AssertionError("L1: a logging failure reached the %s poller: %r" % (site, ex))
        assert len(w.channel(site).sent) == 2, "L1: a logging failure stopped the next %s post" % site
        assert site == "gambler" or w.acks[0] == ([41, 42], False), "L1: a logging failure stopped the LFP ack"


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
    # no role but the resolved one is mentioned by the content and the allowed mentions together (L5): the casual
    # roles are mentionable, so any of them written and allowed would ping its members
    casual = [Role(3, "LookingForPlayer", True), Role(14, "Looking For Player", True)]
    for site in SITES:
        w = World(tree, roles=open_roles() + casual)
        w.run(site)
        content, kw = one(w.channel(site).sent, site)
        named = [r.id for r in discord_lists_written(w.channel(site), content, kw)]
        assert named == [1 if site == "lfp" else 12], \
            "L5: the %s post mentions %r, not its resolved role alone" % (site, named)
        assert kw["allowed_mentions"].roles == [w.guild.roles[0 if site == "lfp" else 1]]
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
    ("R1", "isdecimal in place of isdigit (L2: the superscript two dropped)",
     "if ch.isalpha() or ch.isdigit())", "if ch.isalpha() or ch.isdecimal())"),
    ("R1", "an empty normalised form matched (L3's reading, not a defect)",
     "loose = [r for r in named if want and _ping_role_norm(r.name) == want]",
     "loose = [r for r in named if _ping_role_norm(r.name) == want]"),
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
    ("R2", "no member object read as unknown for mentionable roles (M5's reading, not a defect)",
     '    if roles and all(getattr(r, "mentionable", None) is True for r in roles):\n        return "yes"\n'
     '    guild = getattr(channel, "guild", None) if channel is not None else None\n'
     '    me = getattr(guild, "me", None) if guild is not None else None\n'
     '    if me is None:\n        return "unknown"\n',
     '    guild = getattr(channel, "guild", None) if channel is not None else None\n'
     '    me = getattr(guild, "me", None) if guild is not None else None\n'
     '    if me is None:\n        return "unknown"\n'
     '    if roles and all(getattr(r, "mentionable", None) is True for r in roles):\n        return "yes"\n'),
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
     "        if last is not None and now - last < PING_WARN_EVERY_S:\n            return False\n", ""),
    ("R4", "the bound's time read before the awaits (M4)",
     "        _ping_warned_at[kind] = time.monotonic()\n", "        _ping_warned_at[kind] = now\n"),
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
    ("R5", "no wait for the startup line (M2)",
     "    while any(kind not in _ping_startup_settled for kind in kinds):\n", "    while False:\n"),
    ("R5", "an unbounded wait for the startup line (M2)",
     "        left = deadline - time.monotonic()\n        if left <= 0:\n"
     "            for kind in kinds:\n                if kind not in _ping_startup_settled:\n"
     "                    _ping_log(f\"[PING-CHECK] kind={kind} startup line not printed within "
     "{PING_STARTUP_WAIT_S} s: \"\n"
     "                              \"the ping posts without it\")\n            return\n"
     "        await asyncio.sleep(min(PING_STARTUP_STEP_S, left))\n",
     "        await asyncio.sleep(PING_STARTUP_STEP_S)\n"),
    ("R5", "the Gambler ping dropped when its startup line had not printed (M2)",
     "        await _ping_startup_wait(\"gambler\")\n",
     "        if \"gambler\" not in _ping_startup_settled:\n            await _ping_startup_wait(\"gambler\")\n"
     "            continue\n"),
    ("R6", "a post that cannot notify held back",
     "                sent = await channel.send(\n                    content[:2000],\n",
     "                if any(k[4] == \"no\" for k in kinds):\n                    raise RuntimeError(\"held back\")\n"
     "                sent = await channel.send(\n                    content[:2000],\n"),
    ("R6", "the warning awaited in line (M1; the reviewed build's form)",
     "            _ping_warn_start(kind, configured, roles, role_word, deliverable, delivered, channel, message)\n",
     "            await _ping_warn(kind, configured, roles, role_word, deliverable, delivered, channel, message)\n"),
    ("R6", "a second warning of a kind started while one is in flight (M1)",
     "    if running is not None and not running.done():\n        return False\n", ""),
    ("R6", "the bare print in the after-send fallback (L1)",
     '        _ping_log(f"[PING-CHECK] kind={kind} check after the post failed: {type(ex).__name__}")',
     '        print(f"[PING-CHECK] kind={kind} check after the post failed: {type(ex).__name__}")'),
    ("R6", "the LFP post allows every role",
     "everyone=False, roles=list(ping_roles) if ping_roles else False, users=False),",
     "everyone=False, roles=True, users=False),"),
    ("R7", "the allowed mentions widened to the casual role, its mention not written",
     "everyone=False, roles=list(ping_roles) if ping_roles else False, users=False),",
     "everyone=False, roles=list(ping_roles) + [r for r in channel.guild.roles "
     "if _ping_role_norm(r.name) == \"lookingforplayer\"] or False, users=False),"),
    ("R7", "the casual role pinged beside the ranked one, in the content and in the allowed mentions (L5)",
     '            mention = " ".join(mention_parts)\n',
     '            ping_roles = list(ping_roles) + [r for r in channel.guild.roles '
     'if _ping_role_norm(r.name) == "lookingforplayer"]\n'
     '            mention = " ".join(r.mention for r in ping_roles) if ping_roles else f"@{LFP_ROLE_NAME}"\n'),
]

# The assertion each mutant of the first review round (codex-r1, 21 Nov 2026) must fail first, by the start of
# its message: a mutant that turns its check red at another assertion has not shown what it was written to show.
FAILS_AT = {
    "isdecimal in place of isdigit (L2: the superscript two dropped)": "L2: ",
    "an empty normalised form matched (L3's reading, not a defect)": "L3: ",
    "no member object read as unknown for mentionable roles (M5's reading, not a defect)": "M5: ",
    "the bound's time read before the awaits (M4)": "M4: ",
    "no wait for the startup line (M2)": "M2: the lfp ping posted before its startup line",
    "an unbounded wait for the startup line (M2)": "M2: the lfp ping was held past the bound",
    "the Gambler ping dropped when its startup line had not printed (M2)": "M2: the gambler ping was dropped",
    "the warning awaited in line (M1; the reviewed build's form)": "M1: the lfp poll waits for the admin channel",
    "a second warning of a kind started while one is in flight (M1)":
        "M1: at lfp the posts, the ack and the warning ran as",
    "the bare print in the after-send fallback (L1)": "L1: a logging failure stopped the next lfp post",
    "the casual role pinged beside the ranked one, in the content and in the allowed mentions (L5)":
        "L5: the lfp post mentions",
}


@pytest.mark.parametrize("req,what,old,new", MUTANTS, ids=["%s: %s" % (m[0], m[1]) for m in MUTANTS])
def test_each_mutant_turns_its_requirement_red(req, what, old, new):
    tree, shipped, edited = mutate(old, new)
    assert [ast.dump(n) for n in edited] != [ast.dump(shipped)], "the edit changes no code: %s" % what
    try:
        CHECKS[req](tree)
    except AssertionError as ex:
        want = FAILS_AT.get(what)
        assert want is None or str(ex).startswith(want), "%s turned %s red elsewhere: %s" % (what, req, ex)
        return
    raise AssertionError("the mutant left %s green: %s" % (req, what))


def test_every_requirement_has_a_mutant():
    assert sorted({m[0] for m in MUTANTS}) == sorted(CHECKS)
    assert set(FAILS_AT) <= {m[1] for m in MUTANTS}


def test_control_a_comment_only_edit_keeps_every_requirement_green():
    anchor = "def _ping_role_norm(text) -> str:\n"
    tree, shipped, edited = mutate(anchor, "# control: a comment only, no behaviour\n" + anchor)
    assert tree is not BASE_TREE and edited[0] is not shipped
    assert [ast.dump(n) for n in edited] == [ast.dump(shipped)]
    for req in sorted(CHECKS):
        CHECKS[req](tree)
