"""The in-game looking-for-players ping can also ping the casual role (LFP-CASUAL-1).

Sid's ask (22 Nov 2026): when a casual mode is picked, the in-game button
also pings the casual role, with the ranked ping's cooldown. What this file
holds, one check per requirement:

  C1 the route accepts the word "casual" in modes, from the closed list
     extended by exactly that word, stored in the fixed order after the
     ranked modes;
  C2 a request whose ONLY mode is casual is not refused for ranked_enabled
     false; any request naming a ranked mode (the 1v1 fallback included)
     keeps today's check;
  C3 one per-player cooldown for both kinds: a player cannot ping twice
     within it by alternating ranked and casual;
  C4 older clients: today's exact request bodies, through main's route as
     it stood at BASE_COMMIT and through the route as it stands, give the
     same answer, the same stored row, the same statements and the same
     commits (a differential; the two sources must differ, or the
     comparison proves nothing);
  B1 the bot: a row whose modes include casual mentions the casual role,
     resolved by name from LFP_CASUAL_ROLE_NAME (env LFP_CASUAL_ROLE), and
     the compose file passes that key with the same non-empty default;
  B2 a row with ranked and casual modes mentions both roles in ONE message;
  B3 the [PING] line names the kind, one per kind the row names, each saying
     whether its own role was pinged;
  B4 the startup check covers kind=casual: its [PING] startup line, and a
     [PING-CHECK] line saying in plain words whether the role resolved and
     which env key sets it; the first casual ping waits for it;
  B5 a row without casual is posted exactly as before.

The route runs lifted out of main.py by text (the span from
LFP_COOLDOWN_SECONDS to the next route's decorator) against a fake session:
no database, no network, and main is never imported. The bot code runs in
test_lfp_ping_signal's World, lifted out of discord_bot.py's AST. MUTANTS
holds source edits that must each turn their check red; the controls (a
comment-only edit in each source) leave every check green.
"""

import asyncio
import functools
import os
import re
import subprocess
import types

import pydantic
import pytest

import test_lfp_ping_signal as S

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
REPO = os.path.normpath(os.path.join(BACKEND, ".."))
MAIN = os.path.join(BACKEND, "api", "main.py")
COMPOSE = os.path.join(BACKEND, "docker-compose.yml")
# main as it stood when this lane began: the route before the casual word.
BASE_COMMIT = "edfbc7f52426ce9d4b7fb434e90d480e90e0ccf4"
START, END = "LFP_COOLDOWN_SECONDS = 3600\n", '@app.get("/api/v1/internal/lfp-pings"'


def _segment(text):
    text = text.replace("\r\n", "\n")
    assert text.count(START) == 1 and text.count(END) == 1, "the route's span is not found once"
    start = text.index(START)
    return text[start:text.index(END, start)]


with open(MAIN, encoding="utf-8") as _fh:
    ROUTE_SRC = _segment(_fh.read())


@functools.lru_cache(maxsize=1)
def base_src():
    out = subprocess.run(["git", "-C", REPO, "show", "%s:backend/api/main.py" % BASE_COMMIT],
                         capture_output=True, check=True, timeout=120)
    return _segment(out.stdout.decode("utf-8"))


# -- fakes: the session and the names the route reads ---------------------------------------------

class _Col:
    def __eq__(self, other):
        return ("steam_id", other)

    __hash__ = object.__hash__


class _Player:
    steam_id = _Col()


class _Select:
    def __init__(self, cond=None):
        self.cond = cond

    def where(self, cond):
        return _Select(cond)


def _select(model):
    assert model is _Player
    return _Select()


class _Sql(str):
    pass


class _App:
    def post(self, *a, **k):
        return lambda fn: fn

    get = post


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar(self):
        return self.value


class FakeDb:
    """The session as the route reads it. The cooldown read answers whole
    seconds since the player's newest row, None with no row; an insert
    stores a row stamped with the fake clock. Any other statement fails."""

    def __init__(self, players, rows=(), now=1000000.0):
        self.players, self.rows, self.now = players, [dict(r) for r in rows], now
        self.log, self.commits = [], 0

    async def execute(self, stmt, params=None):
        if isinstance(stmt, _Select):
            _key, sid = stmt.cond
            self.log.append(("select players", sid))
            return _Result(self.players.get(sid))
        sql = str(stmt)
        self.log.append((sql, dict(params or {})))
        if "MAX(created_at)" in sql:
            mine = [r["created"] for r in self.rows if r["steam_id"] == params["sid"]]
            return _Result(int(self.now - max(mine)) if mine else None)
        if sql.startswith("INSERT INTO lfp_pings"):
            self.rows.append({"steam_id": params["sid"], "message": params["msg"], "expires_minutes": params["m"],
                              "modes": params["modes"], "created": self.now})
            return _Result(None)
        raise AssertionError("a statement the fake does not know: %r" % sql)

    async def commit(self):
        self.commits += 1


async def _session_ok(request, steam_id, db):
    return None


def route(src):
    ns = {"__name__": "lfp_route_lifted", "BaseModel": pydantic.BaseModel, "Field": pydantic.Field,
          "Request": object, "AsyncSession": object, "Depends": lambda dep=None: None, "get_db": None,
          "app": _App(), "select": _select, "Player": _Player, "text": _Sql, "_re": re,
          "_check_steam_session": _session_ok}
    exec(compile(src, MAIN, "exec"), ns)
    return ns


SID = "10000000000000001"       # not Steam64-shaped
LINKED = dict(deleted_at=None, discord_id="123456789012345678", ranked_enabled=True)


def player(**over):
    return types.SimpleNamespace(**dict(LINKED, **over))


def call(ns, body, db):
    req = ns["LfpPingRequest"](**body)
    return asyncio.run(ns["lfp_ping"](req, None, db))


def ping(ns, modes=None, ranked=True, rows=(), now=1000000.0):
    body = {"steam_id": SID, "message": "", "expires_minutes": 60}
    if modes is not None:
        body["modes"] = modes
    db = FakeDb({SID: player(ranked_enabled=ranked)}, rows, now)
    return call(ns, body, db), db


QUEUED = {"status": "queued", "cooldown_seconds": 3600}


# -- C1: the casual word -------------------------------------------------------------------------

def check_c1(src):
    ns = route(src)
    assert ns["LFP_MODE_ORDER"] == ("1v1", "2v2", "ffa", "casual")
    for modes, stored in (("casual", "casual"), ("1v1,casual", "1v1,casual"), ("CASUAL , ffa", "ffa,casual"),
                          ("casual,casual,2v2", "2v2,casual"), ("ffa,2v2,1v1,casual", "1v1,2v2,ffa,casual"),
                          ("casualx", "1v1"), ("casual!", "1v1"), ("", "1v1")):
        answer, db = ping(ns, modes)
        assert answer == QUEUED, (modes, answer)
        assert [r["modes"] for r in db.rows] == [stored], (modes, db.rows)
    longest = ",".join(ns["LFP_MODE_ORDER"])
    assert len(longest) <= 20, "the longest canonical value no longer fits lfp_pings.modes VARCHAR(20)"


# -- C2: the ranked gate ---------------------------------------------------------------------------

def check_c2(src):
    ns = route(src)
    for modes in ("casual", " Casual ", "casual,casual", "casual,bogus"):
        answer, db = ping(ns, modes, ranked=False)
        assert answer == QUEUED, (modes, answer)
        assert [r["modes"] for r in db.rows] == ["casual"] and db.commits == 1
    for modes in ("1v1,casual", "casual,ffa", "2v2", "1v1", "", "bogus", None):
        answer, db = ping(ns, modes, ranked=False)
        assert answer == {"status": "ranked_disabled"}, (modes, answer)
        assert db.rows == [] and db.commits == 0, modes
    # the other gate stands for casual too: an unlinked player is refused first
    db = FakeDb({SID: player(discord_id=None, ranked_enabled=False)})
    assert call(ns, {"steam_id": SID, "modes": "casual"}, db) == {"status": "not_linked"} and db.rows == []


# -- C3: one cooldown for both kinds ---------------------------------------------------------------

def check_c3(src):
    ns = route(src)
    for first, second in (("casual", "1v1"), ("1v1", "casual"), ("ffa,casual", "casual"), ("casual", "2v2,casual")):
        answer, db = ping(ns, first)
        assert answer == QUEUED, (first, answer)
        db.now += 600
        assert call(ns, {"steam_id": SID, "modes": second}, db) == {"status": "cooldown", "seconds_left": 3000}, \
            (first, second)
        assert len(db.rows) == 1, (first, second, db.rows)
        db.now += 3000
        assert call(ns, {"steam_id": SID, "modes": second}, db) == QUEUED, (first, second)
        assert [r["modes"] for r in db.rows] == [first, second], (first, second, db.rows)
    # a player with ranked off is held by the same cooldown for casual
    answer, db = ping(ns, "casual", ranked=False)
    assert answer == QUEUED
    db.now += 1
    assert call(ns, {"steam_id": SID, "modes": "casual"}, db) == {"status": "cooldown", "seconds_left": 3599}


# -- C4: older clients, byte for byte --------------------------------------------------------------

# Today's client builds modes from three toggles in a fixed order, "1v1" when none is picked; a client older
# than the toggles sends no modes at all. A few hand-made forms (case, spaces, unknown words) ride along.
_TODAY_MODES = ("1v1", "2v2", "ffa", "1v1,2v2", "1v1,ffa", "2v2,ffa", "1v1,2v2,ffa")
_ODD_MODES = ("", "FFA", " 2v2 , 1v1 ", "solo", ",,", "1v1,1v1")
_MESSAGES = ("", "need a 2v2 partner", "x <@&1> @everyone @Here https://example.org/a\r\nnext line " + "y" * 230)
_EXPIRIES = (15, 30, 60, 180, 45)


def _bodies():
    for modes in (None,) + _TODAY_MODES + _ODD_MODES:
        for msg in _MESSAGES:
            for exp in _EXPIRIES:
                body = {"steam_id": SID, "message": msg, "expires_minutes": exp}
                if modes is not None:
                    body["modes"] = modes
                yield body


def _states():
    yield "linked", {SID: player()}, ()
    yield "ranked off", {SID: player(ranked_enabled=False)}, ()
    yield "not linked", {SID: player(discord_id=None)}, ()
    yield "deleted", {SID: player(deleted_at="2026-11-01")}, ()
    yield "no player", {}, ()
    yield "in cooldown", {SID: player()}, ({"steam_id": SID, "created": 1000000.0 - 120, "modes": "1v1"},)
    yield "ranked off, in cooldown", {SID: player(ranked_enabled=False)}, \
        ({"steam_id": SID, "created": 1000000.0 - 120, "modes": "1v1"},)
    yield "cooldown over", {SID: player()}, ({"steam_id": SID, "created": 1000000.0 - 3600, "modes": "ffa"},)


def check_c4(src, base=None):
    base = base_src() if base is None else base
    assert base != src, "the route at BASE_COMMIT is the route as it stands: the comparison proves nothing"
    old, new = route(base), route(src)
    compared = 0
    for name, players, rows in _states():
        for body in _bodies():
            dbs = []
            for ns in (old, new):
                db = FakeDb(players, rows)
                answer = call(ns, body, db)
                dbs.append((answer, db))
            (a_old, d_old), (a_new, d_new) = dbs
            assert a_new == a_old and repr(a_new) == repr(a_old), (name, body, a_old, a_new)
            assert d_new.rows == d_old.rows, (name, body, d_old.rows, d_new.rows)
            assert d_new.log == d_old.log and d_new.commits == d_old.commits, (name, body)
            compared += 1
    assert compared == 8 * 14 * 3 * 5
    # the comparison is not of two empty runs: today's answers, written out
    answer, db = ping(new, "1v1,ffa")
    assert answer == QUEUED and db.rows[0]["modes"] == "1v1,ffa" and db.rows[0]["expires_minutes"] == 60
    db = FakeDb({SID: player()})
    assert call(new, {"steam_id": SID}, db) == QUEUED and db.rows[0]["modes"] == "1v1"
    assert ping(new, "ffa", ranked=False)[0] == {"status": "ranked_disabled"}


ROUTE_CHECKS = {"C1": check_c1, "C2": check_c2, "C3": check_c3, "C4": check_c4}


# -- the bot ---------------------------------------------------------------------------------------

CASUAL = S.CASUAL_NAME
GLASS = "\N{LEFT-POINTING MAGNIFYING GLASS}"


def casual_role():
    return S.Role(3, CASUAL, True)


def post_text(mention, what):
    return ("%s %s **Typed\\*Name** (<@123456789012345678>) LFP: %s for 1h!\n> typed words\n"
            "Expires <t:1763700000:R>" % (mention, GLASS, what))


def found(kind):
    return "[PING] kind=%s id=41 role=found mentioned=1 deliverable=yes listed=1 delivered=yes" % kind


def check_b1(tree, bot_text=S.TEXT, compose_text=None):
    role = casual_role()
    w = S.World(tree, roles=S.open_roles() + [role])
    w.lfp(dict(S.PING, modes="casual"))
    content, kw = S.one(w.queue.sent, "casual posts")
    assert content == post_text("<@&3>", "casual"), content
    assert kw["allowed_mentions"].roles == [role] and kw["suppress_embeds"] is True
    assert w.acks == [([41], False), ([], True)] and w.warnings() == []
    # resolved by name from the configured name: another name resolves another role
    crew = S.Role(5, "Casual Crew", True)
    w = S.World(tree, roles=S.open_roles() + [role, crew], casual_name="Casual Crew")
    w.lfp(dict(S.PING, modes="casual"))
    content, kw = S.one(w.queue.sent, "configured name")
    assert content.startswith("<@&5> " + GLASS) and kw["allowed_mentions"].roles == [crew], content
    # no role of that name: the name as plain text, no role allowed, and the casual kind's warning
    w = S.World(tree, roles=S.open_roles())
    w.lfp(dict(S.PING, modes="casual"))
    content, kw = S.one(w.queue.sent, "casual absent")
    assert content == post_text("@" + CASUAL, "casual") and kw["allowed_mentions"].roles is False, content
    warn = S.one(w.warnings(), "casual absent")
    assert "It is the casual Looking For Player ping" in warn and "named **LookingForPlayer**" in warn, warn
    # the env key, its default, and the compose file passing it with that default repeated
    m = re.search(r'^LFP_CASUAL_ROLE_NAME = os\.getenv\("LFP_CASUAL_ROLE", "([^"]+)"\)$', bot_text, re.M)
    assert m and m.group(1) == CASUAL, "the bot's casual role key or its default moved"
    if compose_text is None:
        with open(COMPOSE, encoding="utf-8") as fh:
            compose_text = fh.read()
    bot_block = compose_text[compose_text.index("\n  bot:\n"):]
    bot_block = bot_block[:bot_block.index("\n    volumes:")]
    c = re.search(r"^      LFP_CASUAL_ROLE: (.+?)\s*$", bot_block, re.M)
    assert c, "compose does not pass LFP_CASUAL_ROLE into the bot container"
    assert c.group(1) == "${LFP_CASUAL_ROLE:-%s}" % CASUAL, \
        "compose must pass ${LFP_CASUAL_ROLE:-<the bot's default>}; found %r" % c.group(1)


def check_b2(tree):
    role = casual_role()
    w = S.World(tree, roles=S.open_roles() + [role])
    w.lfp(dict(S.PING, modes="1v1,ffa,casual"))
    content, kw = S.one(w.queue.sent, "one message for both kinds")
    assert content == post_text("<@&1> <@&3>", "ranked 1v1+FFA and casual"), content
    assert kw["allowed_mentions"].roles == [w.guild.roles[0], role]
    assert w.acks == [([41], False), ([], True)]
    # the ranked role absent: its name as plain text beside the casual mention, still one message
    w = S.World(tree, roles=[role])
    w.lfp(dict(S.PING, modes="2v2,casual"))
    content, kw = S.one(w.queue.sent, "ranked absent")
    assert content == post_text("@Ranked Looking For Player <@&3>", "ranked 2v2 and casual"), content
    assert kw["allowed_mentions"].roles == [role]
    # both names resolve to one role: it is written and allowed once
    w = S.World(tree, roles=S.open_roles(), casual_name=S.LFP_NAME)
    w.lfp(dict(S.PING, modes="2v2,casual"))
    content, kw = S.one(w.queue.sent, "one shared role")
    assert content == post_text("<@&1>", "ranked 2v2 and casual"), content
    assert kw["allowed_mentions"].roles == [w.guild.roles[0]]


def check_b3(tree):
    role = casual_role()
    w = S.World(tree, roles=S.open_roles() + [role])
    w.lfp(dict(S.PING, modes="1v1,casual"))
    assert w.lines() == [found("lfp"), found("casual")], w.lines()
    w = S.World(tree, roles=S.open_roles() + [role])
    w.lfp(dict(S.PING, modes="casual"))
    assert w.lines() == [found("casual")], w.lines()
    # the casual role absent: the ranked line says pinged, the casual line says not, and the warning is the
    # casual kind's alone
    w = S.World(tree, roles=S.open_roles())
    w.lfp(dict(S.PING, modes="1v1,casual"))
    assert w.lines() == [found("lfp"),
                         "[PING] kind=casual id=41 role=absent mentioned=0 deliverable=no listed=0 delivered=no"]
    assert "casual Looking For Player ping" in S.one(w.warnings(), "casual absent")
    assert "[PING-WARN] kind=casual warning posted to the admin channel" in w.log
    # Discord's answer lists the ranked role alone: each kind reads its own roles from it
    w = S.World(tree, roles=S.open_roles() + [role], answer=S.discord_lists_one)
    w.lfp(dict(S.PING, modes="1v1,casual"))
    assert w.lines() == [found("lfp"),
                         "[PING] kind=casual id=41 role=found mentioned=1 deliverable=yes listed=0 delivered=no"]


def check_b4(tree):
    role = casual_role()
    w = S.World(tree, roles=S.open_roles() + [role])
    w.startup()
    assert w.lines() == [
        "[PING] kind=lfp id=startup role=found mentioned=1 deliverable=yes listed=0 delivered=unsent",
        "[PING] kind=casual id=startup role=found mentioned=1 deliverable=yes listed=0 delivered=unsent",
        "[PING] kind=gambler id=startup role=found mentioned=1 deliverable=yes listed=0 delivered=unsent"]
    said = [ln for ln in w.log if ln.startswith("[PING-CHECK] kind=casual startup: role resolved")]
    assert said == ["[PING-CHECK] kind=casual startup: role resolved: yes (found, 1 role(s) for the name "
                    "'LookingForPlayer'; env LFP_CASUAL_ROLE)"], w.log
    w = S.World(tree, roles=S.open_roles())
    w.startup()
    assert ("[PING-CHECK] kind=casual startup: role resolved: NO (absent): no role is mentioned for the name "
            "'LookingForPlayer', so these pings notify nobody until env LFP_CASUAL_ROLE gives the role's exact name"
            ) in w.log, w.log
    assert "[PING] kind=casual id=startup role=absent mentioned=0 deliverable=no listed=0 delivered=unsent" \
        in w.lines()
    assert w.queue.sent == [] and w.admin.sent == []
    # the first casual ping waits for the casual startup line, at most the bound, and posts all the same
    w = S.World(tree, roles=S.open_roles() + [role], startup_printed=False)
    w.ns["_ping_startup_settled"].update(("lfp", "gambler"))
    w.lfp(dict(S.PING, modes="casual"))
    bound = w.ns["PING_STARTUP_WAIT_S"]
    late = "[PING-CHECK] kind=casual startup line not printed within %d s: the ping posts without it" % bound
    assert w.log.count(late) == 1 and len(w.queue.sent) == 1, w.log


def check_b5(tree):
    role = casual_role()
    w = S.World(tree, roles=S.open_roles() + [role])
    w.lfp()
    content, kw = S.one(w.queue.sent, "a ranked row")
    assert content == S.EXPECTED_LFP, content
    assert kw["allowed_mentions"].roles == [w.guild.roles[0]] and w.lines() == [found("lfp")]
    for modes, what in (("2v2,ffa", "ranked 2v2+FFA"), ("1v1,2v2,ffa", "ranked 1v1+2v2+FFA"), (",", "ranked "),
                        ("", "ranked 1v1")):
        w = S.World(tree, roles=S.open_roles() + [role])
        w.lfp(dict(S.PING, modes=modes))
        content, kw = S.one(w.queue.sent, modes)
        assert content == post_text("<@&1>", what), (modes, content)
        assert kw["allowed_mentions"].roles == [w.guild.roles[0]] and w.lines() == [found("lfp")]


BOT_CHECKS = {"B1": check_b1, "B2": check_b2, "B3": check_b3, "B4": check_b4, "B5": check_b5}


@pytest.mark.parametrize("req", sorted(ROUTE_CHECKS))
def test_each_route_requirement_holds(req):
    ROUTE_CHECKS[req](ROUTE_SRC)


@pytest.mark.parametrize("req", sorted(BOT_CHECKS))
def test_each_bot_requirement_holds(req):
    BOT_CHECKS[req](S.BASE_TREE)


# (requirement, what the edit does, the text it replaces, the new text). Each must turn its check red.
ROUTE_MUTANTS = [
    ("C1", "casual left off the closed list",
     'LFP_MODE_ORDER = LFP_RANKED_MODES + ("casual",)', "LFP_MODE_ORDER = LFP_RANKED_MODES"),
    ("C1", "the casual word stored before the ranked modes",
     'LFP_MODE_ORDER = LFP_RANKED_MODES + ("casual",)', 'LFP_MODE_ORDER = ("casual",) + LFP_RANKED_MODES'),
    ("C2", "the ranked gate refuses casual too",
     'if not player.ranked_enabled and modes != "casual":', "if not player.ranked_enabled:"),
    ("C2", "a ranked mode beside casual passes the gate",
     'modes != "casual"', '"casual" not in modes'),
    ("C3", "casual skips the cooldown",
     "if elapsed is not None and int(elapsed) < LFP_COOLDOWN_SECONDS:",
     'if modes != "casual" and elapsed is not None and int(elapsed) < LFP_COOLDOWN_SECONDS:'),
    ("C4", "the fallback for nothing valid becomes casual",
     'or "1v1"\n', 'or "casual"\n'),
    ("C4", "mode words no longer folded to lower case",
     "picked = {m.strip().lower() for m in", "picked = {m.strip() for m in"),
    ("C4", "the ranked gate dropped",
     '    if not player.ranked_enabled and modes != "casual":\n        return {"status": "ranked_disabled"}\n',
     '    if not player.ranked_enabled and modes != "casual" and False:\n'
     '        return {"status": "ranked_disabled"}\n'),
]

BOT_MUTANTS = [
    ("B1", "the casual role resolved from the ranked role's name",
     '("casual", casual, LFP_CASUAL_ROLE_NAME)', '("casual", casual, LFP_ROLE_NAME)'),
    ("B1", "the casual word never read from the row",
     'casual = "casual" in mode_parts', "casual = False"),
    ("B2", "the second kind's roles written but not allowed",
     "ping_roles.extend(fresh)", "ping_roles.extend(fresh if not ping_roles else [])"),
    ("B2", "the first kind's mention alone written",
     '            mention = " ".join(mention_parts)\n', "            mention = mention_parts[0]\n"),
    ("B3", "one [PING] line for the first kind alone",
     "for kind, configured, roles_k, word_k, dv_k in kinds:",
     "for kind, configured, roles_k, word_k, dv_k in kinds[:1]:"),
    ("B3", "every kind's line read over all the post's roles",
     "await _ping_after_send(kind, ping_id, configured, roles_k, word_k, dv_k, channel, sent)",
     "await _ping_after_send(kind, ping_id, configured, ping_roles, word_k, dv_k, channel, sent)"),
    ("B4", "no casual startup line",
     '                                         ("casual", QUEUE_BEACON_CHANNEL_ID, LFP_CASUAL_ROLE_NAME),\n', ""),
    ("B4", "no plain resolved line at startup",
     "            _ping_log(_ping_resolved_line(kind, configured, role_word, len(ping_roles)))\n", ""),
    ("B4", "the first casual ping does not wait for its startup line",
     '            if casual:\n                await _ping_startup_wait("casual")\n', ""),
    ("B5", "a ranked row's headline changed",
     '                what_label = f"ranked {modes_label}"\n',
     '                what_label = f"ranked {modes_label} only"\n'),
    ("B5", "a row with no mode word pings no role",
     "ranked = bool(ranked_parts) or not casual", "ranked = bool(ranked_parts)"),
]

# Mutants of the env key and the compose file, on their text (B1).
TEXT_MUTANTS = [
    ("B1", "compose passes the key with an empty default", "compose",
     "LFP_CASUAL_ROLE: ${LFP_CASUAL_ROLE:-LookingForPlayer}", "LFP_CASUAL_ROLE: ${LFP_CASUAL_ROLE:-}"),
    ("B1", "compose does not pass the key", "compose",
     "      LFP_CASUAL_ROLE: ${LFP_CASUAL_ROLE:-LookingForPlayer}\n", ""),
    ("B1", "the bot's default drifts from compose", "bot",
     'os.getenv("LFP_CASUAL_ROLE", "LookingForPlayer")', 'os.getenv("LFP_CASUAL_ROLE", "Looking For Player")'),
]


def _mutated_route(old, new):
    assert ROUTE_SRC.count(old) == 1, old
    return ROUTE_SRC.replace(old, new, 1)


def _expect_red(check, *args, what):
    try:
        check(*args)
    except AssertionError:
        return
    raise AssertionError("the mutant left its check green: %s" % what)


@pytest.mark.parametrize("req,what,old,new", ROUTE_MUTANTS, ids=["%s: %s" % (m[0], m[1]) for m in ROUTE_MUTANTS])
def test_each_route_mutant_turns_its_requirement_red(req, what, old, new):
    _expect_red(ROUTE_CHECKS[req], _mutated_route(old, new), what=what)


@pytest.mark.parametrize("req,what,old,new", BOT_MUTANTS, ids=["%s: %s" % (m[0], m[1]) for m in BOT_MUTANTS])
def test_each_bot_mutant_turns_its_requirement_red(req, what, old, new):
    tree, shipped, edited = S.mutate(old, new)
    _expect_red(BOT_CHECKS[req], tree, what=what)


@pytest.mark.parametrize("req,what,where,old,new", TEXT_MUTANTS, ids=["%s: %s" % (m[0], m[1]) for m in TEXT_MUTANTS])
def test_each_text_mutant_turns_its_requirement_red(req, what, where, old, new):
    with open(COMPOSE, encoding="utf-8") as fh:
        compose = fh.read()
    bot = S.TEXT
    if where == "compose":
        assert compose.count(old) == 1, old
        compose = compose.replace(old, new, 1)
    else:
        assert bot.count(old) == 1, old
        bot = bot.replace(old, new, 1)
    _expect_red(check_b1, S.BASE_TREE, bot, compose, what=what)


def test_every_requirement_has_a_mutant():
    assert sorted({m[0] for m in ROUTE_MUTANTS}) == sorted(ROUTE_CHECKS)
    assert sorted({m[0] for m in BOT_MUTANTS}) == sorted(BOT_CHECKS)


def test_control_comment_only_edits_keep_every_requirement_green():
    anchor = "class LfpPingRequest(BaseModel):\n"
    src = _mutated_route(anchor, "# control: a comment only, no behaviour\n" + anchor)
    assert src != ROUTE_SRC
    for req in sorted(ROUTE_CHECKS):
        ROUTE_CHECKS[req](src)
    anchor = "def _ping_resolved_line(kind, configured, role_word, mentioned) -> str:\n"
    tree, shipped, edited = S.mutate(anchor, "# control: a comment only, no behaviour\n" + anchor)
    assert tree is not S.BASE_TREE
    for req in sorted(BOT_CHECKS):
        BOT_CHECKS[req](tree)
