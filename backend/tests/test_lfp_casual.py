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
     [PING-CHECK] line saying in plain words what the check saw and which
     env key sets the name, with the guild's near role names when none was
     found; the first casual ping waits for it, and a row of two kinds waits
     once, the bound in all;
  B5 a row without casual is posted exactly as before;
  B6 the bot declares the casual kind on every poll of pending pings;
  B7 when the casual and ranked names resolve to one role, startup says so
     in one line naming both env keys, and the ping still posts.

After review round 2: C6 (the cooldown compares a floored age; the fake
applies each cooldown text's own arithmetic) and the base text of the
differentials read from the tracked fixture lfp_casual_base_spans.json.

After review round 1: C5 (the admission lock, once, before the cooldown
read, then the insert and the commit) and a fake session that knows its
statements by exact text, applies the cooldown read's predicates and keeps
rows pending until the commit. The lock's effect on two sessions, the
cross-kind cooldown and the pending-pings filter run on the real database
in test_lfp_casual_pg.py.

The route runs lifted out of main.py by text (the span from
LFP_COOLDOWN_SECONDS to the next route's decorator, plus the lane's helpers
appended at the end of main.py, which stays line-neutral above them)
against a fake session:
no database, no network, and main is never imported. The bot code runs in
test_lfp_ping_signal's World, lifted out of discord_bot.py's AST. MUTANTS
holds source edits that must each turn their check red; the controls (a
comment-only edit in each source) leave every check green.
"""

import asyncio
import functools
import hashlib
import json
import math
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


TAIL_START = "# ── LFP-CASUAL-1: helpers of the looking-for-players routes "
TAIL_END = "# ── end of LFP-CASUAL-1 helpers "


def _tail(text):
    text = text.replace("\r\n", "\n")
    assert text.count(TAIL_START) == 1 and text.count(TAIL_END) == 1, "the helpers' span is not found once"
    start = text.index(TAIL_START)
    return text[start:text.index(TAIL_END, start)]


def route_source(text):
    """The route as the module runs it: its span, then the helpers it reads at call time."""
    return _segment(text) + "\n" + _tail(text)


with open(MAIN, encoding="utf-8") as _fh:
    ROUTE_SRC = route_source(_fh.read())


# The base text of both differentials (this file's C4, test_lfp_casual_pg.py's P1) is a TRACKED fixture
# (review round 2, F8): `git show` has no such object on a seat or in a copied tree, and a differential
# against nothing measures nothing. The fixture holds the two route spans of main.py at BASE_COMMIT, with
# LF newlines; each is checked against its sha256 here before use, and against `git show` where git has
# the object (test_the_base_fixture_is_main_at_base_commit).
BASE_FIXTURE = os.path.join(HERE, "lfp_casual_base_spans.json")
BASE_SHA256 = {"lfp_ping": "1715d953f3eb246d28257a5237a1b95753e239e3dd334df2209fe432579f9f41",
               "internal_lfp_pings": "eb25d686484f56cad4664379498b82ad3209b06d388ebe87309168715b0f6ced"}
PEND_START, PEND_END = '@app.get("/api/v1/internal/lfp-pings"', "class _LfpPingAck(BaseModel):"


def pending_segment(text):
    text = text.replace("\r\n", "\n")
    assert text.count(PEND_START) == 1 and text.count(PEND_END) == 1, "the pending-pings route is not found once"
    start = text.index(PEND_START)
    return text[start:text.index(PEND_END, start)]


@functools.lru_cache(maxsize=2)
def base_span(name):
    with open(BASE_FIXTURE, encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["commit"] == BASE_COMMIT and doc["file"] == "backend/api/main.py", (doc["commit"], doc["file"])
    span = doc["spans"][name]
    assert hashlib.sha256(span.encode("utf-8")).hexdigest() == BASE_SHA256[name], "the base fixture changed: " + name
    return span


def base_src():
    return base_span("lfp_ping")


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


# The statements the fake session knows, by their exact text and exact parameter names (review round 1,
# findings 5 and 6). A statement whose text differs by one character is refused, never matched on a fragment.
LOCK_SQL = "SELECT pg_advisory_xact_lock(CAST(:cls AS integer), hashtext(CAST(:who AS text)))"
# The cooldown read in two texts: the route at BASE_COMMIT rounds the age (::int), the route as it stands
# floors it (review round 2, F1). The trace names both "cooldown read", so the differential compares what the
# two routes do; the fake applies each text's own arithmetic.
COOLDOWN_SQL_ROUNDED = ("SELECT EXTRACT(EPOCH FROM (NOW() - MAX(created_at)))::int   FROM lfp_pings "
                        "WHERE steam_id = :sid")
COOLDOWN_SQL = ("SELECT FLOOR(EXTRACT(EPOCH FROM (NOW() - MAX(created_at))))::int   FROM lfp_pings "
                "WHERE steam_id = :sid")
COOLDOWN = "cooldown read"
INSERT_SQL = ("INSERT INTO lfp_pings (steam_id, message, expires_minutes, expires_at, modes) "
              "VALUES (:sid, :msg, :m, NOW() + make_interval(mins => :m), :modes)")
KNOWN = {LOCK_SQL: {"cls", "who"}, COOLDOWN_SQL: {"sid"}, COOLDOWN_SQL_ROUNDED: {"sid"},
         INSERT_SQL: {"sid", "msg", "m", "modes"}}


def _pg_int(seconds):
    """numeric::int in PostgreSQL rounds half away from zero."""
    return int(seconds + 0.5) if seconds >= 0 else -int(-seconds + 0.5)


class FakeDb:
    """The session as the route reads it, one transaction of it.

    It knows three statements by exact text (KNOWN) and refuses any other.
    The cooldown read applies its own predicates: the rows of steam_id = :sid
    that this session can see (every committed row, and its own rows not yet
    committed), of any modes, and answers MAX(created_at) as whole seconds
    before now, floored by the FLOOR text and rounded as ::int rounds by the
    other, or None with no row. An insert
    stores its row as PENDING; commit() makes the pending rows durable; close()
    is the session's end and drops what is still pending, as a rollback does.
    `trace` is ONE ordered record of statements and commits."""

    def __init__(self, players, rows=(), now=1000000.0):
        self.players, self.rows, self.now = players, [dict(r) for r in rows], now
        self.pending, self.trace = [], []

    @property
    def commits(self):
        return self.trace.count(("COMMIT",))

    async def execute(self, stmt, params=None):
        if isinstance(stmt, _Select):
            _key, sid = stmt.cond
            self.trace.append(("select players", sid))
            return _Result(self.players.get(sid))
        sql, params = str(stmt), dict(params or {})
        if sql not in KNOWN:
            raise AssertionError("a statement the fake does not know: %r" % sql)
        assert set(params) == KNOWN[sql], ("the parameters of a known statement changed", sql, sorted(params))
        self.trace.append((COOLDOWN if sql in (COOLDOWN_SQL, COOLDOWN_SQL_ROUNDED) else sql, params))
        if sql == LOCK_SQL:
            assert isinstance(params["cls"], int) and params["who"] == SID, params
            return _Result(None)
        if sql in (COOLDOWN_SQL, COOLDOWN_SQL_ROUNDED):
            mine = [r["created"] for r in self.rows + self.pending if r["steam_id"] == params["sid"]]
            if not mine:
                return _Result(None)
            age = self.now - max(mine)
            return _Result(math.floor(age) if sql == COOLDOWN_SQL else _pg_int(age))
        self.pending.append({"steam_id": params["sid"], "message": params["msg"], "expires_minutes": params["m"],
                             "modes": params["modes"], "created": self.now})
        return _Result(None)

    async def commit(self):
        self.trace.append(("COMMIT",))
        self.rows.extend(self.pending)
        self.pending = []

    def close(self):
        self.pending = []

    @property
    def log(self):
        """The trace without the admission lock: what the route at BASE_COMMIT, which took no lock, also does."""
        return [t for t in self.trace if t[0] != LOCK_SQL]


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
    """One request: the route, then the session's end (get_db closes it, dropping what is uncommitted)."""
    req = ns["LfpPingRequest"](**body)
    try:
        return asyncio.run(ns["lfp_ping"](req, None, db))
    finally:
        db.close()


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
            # the one statement the route adds is the admission lock, just before the cooldown read, and only there
            assert all(t[0] != LOCK_SQL for t in d_old.trace), (name, body)
            reads = [i for i, t in enumerate(d_new.trace) if t[0] == COOLDOWN]
            locks = [i for i, t in enumerate(d_new.trace) if t[0] == LOCK_SQL]
            assert locks == [i - 1 for i in reads], (name, body, d_new.trace)
            compared += 1
    assert compared == 8 * 14 * 3 * 5
    # the comparison is not of two empty runs: today's answers, written out
    answer, db = ping(new, "1v1,ffa")
    assert answer == QUEUED and db.rows[0]["modes"] == "1v1,ffa" and db.rows[0]["expires_minutes"] == 60
    db = FakeDb({SID: player()})
    assert call(new, {"steam_id": SID}, db) == QUEUED and db.rows[0]["modes"] == "1v1"
    assert ping(new, "ffa", ranked=False)[0] == {"status": "ranked_disabled"}


# -- C5: one admission, in order -------------------------------------------------------------------

def check_c5(src):
    """The order the route works in, from the fake's one trace: the player read, the admission lock, the
    cooldown read, the insert, then the commit, and the row durable after the session ends. The lock's
    effect (a second request of the player waits until the first one's transaction ends, and after its
    commit answers cooldown) is proven on the real database in test_lfp_casual_pg.py; here, that the
    lock is taken, once, with the class constant, before the read."""
    ns = route(src)
    for modes, ranked in (("1v1", True), ("casual", False), ("ffa,casual", True)):
        answer, db = ping(ns, modes, ranked=ranked)
        assert answer == QUEUED, (modes, answer)
        assert [t[0] for t in db.trace] == ["select players", LOCK_SQL, COOLDOWN, INSERT_SQL, "COMMIT"], \
            (modes, db.trace)
        assert db.trace[1][1] == {"cls": ns["LFP_ADMISSION_LOCK_CLASS"], "who": SID}, db.trace[1]
        assert [r["modes"] for r in db.rows] == [modes] and db.pending == [], (modes, db.rows)
    # a refused request takes the lock only when it reaches the cooldown read, and stores nothing
    answer, db = ping(ns, "casual", rows=({"steam_id": SID, "created": 1000000.0 - 5, "modes": "1v1"},))
    assert answer == {"status": "cooldown", "seconds_left": 3595}
    assert [t[0] for t in db.trace] == ["select players", LOCK_SQL, COOLDOWN] and len(db.rows) == 1


# -- C6: the floored age (review round 2, F1) ------------------------------------------------------

def check_c6(src):
    """The cooldown compares a FLOORED age: a row 3599.5 s old is still inside the hour, one second left,
    for either kind; a row 3600 s old is past it. (The rounded ::int read 3600 and admitted a second row.)
    The real database proves the same, for both readers, in test_lfp_casual_pg.py (B1, B2)."""
    ns = route(src)
    for kind, ranked in (("1v1", True), ("casual", False)):
        for age, want in ((3599.5, {"status": "cooldown", "seconds_left": 1}), (3599.999, {"status": "cooldown",
                          "seconds_left": 1}), (3600.0, QUEUED), (3600.5, QUEUED)):
            answer, db = ping(ns, kind, ranked=ranked, rows=({"steam_id": SID, "created": 1000000.0 - age,
                                                               "modes": kind},))
            assert answer == want, (kind, age, answer)


ROUTE_CHECKS = {"C1": check_c1, "C2": check_c2, "C3": check_c3, "C4": check_c4, "C5": check_c5, "C6": check_c6}


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
    # what the check saw, and no claim that an env change is needed (finding 10): the guild's role names near
    # the configured one, at most five, by repr cut at 60 characters, oldest role first
    no_line = ("[PING-CHECK] kind=casual startup: role resolved: NO (absent): the startup check found no role to "
               "mention for the name 'LookingForPlayer' (env LFP_CASUAL_ROLE); role names containing look, casual "
               "or lfp: ")
    w = S.World(tree, roles=[S.Role(12, S.GAMBLER_NAME, True)])
    w.startup()
    assert no_line + "none" in w.log, w.log
    assert "[PING] kind=casual id=startup role=absent mentioned=0 deliverable=no listed=0 delivered=unsent" \
        in w.lines()
    assert w.queue.sent == [] and w.admin.sent == []
    long_name = "Casual " + "x" * 70
    planted = [S.Role(40, "LFP crew"), S.Role(9, "Moderators"), S.Role(30, "casual gamers"),
               S.Role(1, S.LFP_NAME, True), S.Role(50, long_name), S.Role(20, "Look-Out"),
               S.Role(60, "Casual Too Many"), S.Role(12, S.GAMBLER_NAME, True)]
    w = S.World(tree, roles=planted)
    w.startup()
    said = [ln for ln in w.log if ln.startswith("[PING-CHECK] kind=casual startup: role resolved")]
    assert said == [no_line + "'Ranked Looking For Player', 'Look-Out', 'casual gamers', 'LFP crew', "
                    + repr(long_name)[:60]], said
    assert all("env LFP_CASUAL_ROLE gives" not in ln and "until" not in ln for ln in said), said
    # the first casual ping waits for the casual startup line, at most the bound, and posts all the same
    w = S.World(tree, roles=S.open_roles() + [role], startup_printed=False)
    w.ns["_ping_startup_settled"].update(("lfp", "gambler"))
    w.lfp(dict(S.PING, modes="casual"))
    bound = w.ns["PING_STARTUP_WAIT_S"]
    late = "[PING-CHECK] kind=%s startup line not printed within %d s: the ping posts without it"
    assert w.log.count(late % ("casual", bound)) == 1 and len(w.queue.sent) == 1, w.log
    # a row of both kinds with neither startup line printed waits ONCE: one deadline, the bound in all
    # (finding 4), measured on the bot's fake monotonic clock
    w = S.World(tree, roles=S.open_roles() + [role], startup_printed=False)
    w.ns["_ping_startup_settled"].update(("gambler",))
    began = w.clock[0]
    w.lfp(dict(S.PING, modes="1v1,casual"))
    assert w.log.count(late % ("lfp", bound)) == 1 and w.log.count(late % ("casual", bound)) == 1, w.log
    # both late lines print when the one deadline passes; the post follows them
    waited = [w.stamps[w.log.index(late % (k, bound))] - began for k in ("lfp", "casual")]
    assert waited == [bound, bound], ("the first ping of two kinds waited %r s, the bound is %r s" % (waited, bound))
    assert len(w.queue.sent) == 1, w.queue.sent


# -- B6: the bot declares the casual kind ----------------------------------------------------------

def check_b6(tree):
    """The api gives a row naming casual only to a poller that declares the casual kind (F3). This bot
    declares it on every poll; the World's api_get answers as the api does, with and without it."""
    role = casual_role()
    w = S.World(tree, roles=S.open_roles() + [role])
    w.lfp(dict(S.PING, modes="1v1,casual"))
    assert w.paths and set(w.paths) == {"/internal/lfp-pings?kinds=casual"}, w.paths
    content, kw = S.one(w.queue.sent, "a declaring poll")
    assert content == post_text("<@&1> <@&3>", "ranked 1v1 and casual"), content


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


# -- B7: two kinds, one role (review round 2, F7) --------------------------------------------------

SHARED = ("[PING-CHECK] kind=casual startup: the casual and the ranked role names resolve to the same role "
          "('Ranked Looking For Player'): a casual-only ping mentions that role, as a ranked ping does "
          "(env LFP_CASUAL_ROLE and env LFP_ROLE)")


def check_b7(tree):
    """When the casual and the ranked names resolve to the SAME role (configured so, or by a normalised
    alias), startup prints ONE plain line naming both env keys, after both kinds' checks; the ping still
    posts, mentioning that role. Two different roles, or no casual role, print no such line."""
    for casual_name in (S.LFP_NAME, "ranked-looking-for-player"):
        w = S.World(tree, roles=S.open_roles(), casual_name=casual_name)
        w.startup()
        shared = [ln for ln in w.log if "resolve to the same role" in ln]
        assert shared == [SHARED], (casual_name, w.log)
        checks = [i for i, ln in enumerate(w.log) if ln.startswith("[PING-CHECK] kind=casual startup: role resolved")]
        assert checks and w.log.index(SHARED) > checks[0], w.log
        w.lfp(dict(S.PING, modes="casual"))
        content, kw = S.one(w.queue.sent, "a casual ping on the shared role")
        assert content == post_text("<@&1>", "casual"), content
    for roles in (S.open_roles() + [casual_role()], S.open_roles()):
        w = S.World(tree, roles=roles)
        w.startup()
        assert not [ln for ln in w.log if "resolve to the same role" in ln], w.log


BOT_CHECKS = {"B1": check_b1, "B2": check_b2, "B3": check_b3, "B4": check_b4, "B5": check_b5, "B6": check_b6,
              "B7": check_b7}


@pytest.mark.parametrize("req", sorted(ROUTE_CHECKS))
def test_each_route_requirement_holds(req):
    ROUTE_CHECKS[req](ROUTE_SRC)


@pytest.mark.parametrize("req", sorted(BOT_CHECKS))
def test_each_bot_requirement_holds(req):
    BOT_CHECKS[req](S.BASE_TREE)


# Route edits shared with the real-database proof (test_lfp_casual_pg.py runs the same texts).
COOLDOWN_MUTANT_OLD = '"  FROM lfp_pings WHERE steam_id = :sid"\n'
COOLDOWN_MUTANT_NEW = '"  FROM lfp_pings WHERE steam_id = :sid AND position(\'casual\' in modes) = 0"\n'
INSERT_STMT = ('    await db.execute(text(\n'
               '        "INSERT INTO lfp_pings (steam_id, message, expires_minutes, expires_at, modes) "\n'
               '        "VALUES (:sid, :msg, :m, NOW() + make_interval(mins => :m), :modes)"\n'
               '    ), {"sid": req.steam_id, "msg": msg, "m": exp_min, "modes": modes})\n')
COMMIT_MUTANT_OLD = INSERT_STMT + '    await db.commit()\n'
COMMIT_MUTANT_NEW = '    await db.commit()\n' + INSERT_STMT
LOCK_MUTANT_OLD = ('    await db.execute(text(\n'
                   '        "SELECT pg_advisory_xact_lock(CAST(:cls AS integer), hashtext(CAST(:who AS text)))"\n'
                   '    ), {"cls": LFP_ADMISSION_LOCK_CLASS, "who": steam_id})\n')
COOLDOWN_READ_OLD = ('    return (await db.execute(text(\n'
                     '        "SELECT FLOOR(EXTRACT(EPOCH FROM (NOW() - MAX(created_at))))::int "\n'
                     '        "  FROM lfp_pings WHERE steam_id = :sid"\n'
                     '    ), {"sid": steam_id})).scalar()\n')
# review round 2, F1: the floor removed from the admission's read (the stats reader's twin: STATS_FLOOR_*)
FLOOR_MUTANT_OLD = '        "SELECT FLOOR(EXTRACT(EPOCH FROM (NOW() - MAX(created_at))))::int "\n'
FLOOR_MUTANT_NEW = '        "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(created_at)))::int "\n'
STATS_FLOOR_OLD = '            "SELECT FLOOR(EXTRACT(EPOCH FROM (NOW() - MAX(created_at))))::int "\n'
STATS_FLOOR_NEW = '            "SELECT EXTRACT(EPOCH FROM (NOW() - MAX(created_at)))::int "\n'
LOCK_AFTER_READ = COOLDOWN_READ_OLD.replace("    return (await", "    elapsed = (await") + LOCK_MUTANT_OLD \
    + "    return elapsed\n"
GATE_OLD = '    if (modes := _lfp_modes(req.modes)) != "casual" and not player.ranked_enabled:\n'

# (requirement, what the edit does, the text it replaces, the new text). Each must turn its check red.
ROUTE_MUTANTS = [
    ("C1", "casual left off the closed list",
     'LFP_MODE_ORDER = LFP_RANKED_MODES + ("casual",)', "LFP_MODE_ORDER = LFP_RANKED_MODES"),
    ("C1", "the casual word stored before the ranked modes",
     'LFP_MODE_ORDER = LFP_RANKED_MODES + ("casual",)', 'LFP_MODE_ORDER = ("casual",) + LFP_RANKED_MODES'),
    ("C2", "the ranked gate refuses casual too",
     GATE_OLD, '    if (modes := _lfp_modes(req.modes)) and not player.ranked_enabled:\n'),
    ("C2", "a ranked mode beside casual passes the gate",
     GATE_OLD, '    if "casual" not in (modes := _lfp_modes(req.modes)) and not player.ranked_enabled:\n'),
    ("C3", "casual skips the cooldown",
     "if elapsed is not None and int(elapsed) < LFP_COOLDOWN_SECONDS:",
     'if modes != "casual" and elapsed is not None and int(elapsed) < LFP_COOLDOWN_SECONDS:'),
    ("C4", "the fallback for nothing valid becomes casual",
     'or "1v1"\n', 'or "casual"\n'),
    ("C4", "mode words no longer folded to lower case",
     "picked = {m.strip().lower() for m in", "picked = {m.strip() for m in"),
    ("C4", "the ranked gate dropped",
     GATE_OLD, GATE_OLD.replace(" and not player.ranked_enabled:", " and not player.ranked_enabled and False:")),
    # review round 1, finding 5: the cooldown read restricted to the request's own kind
    ("C3", "the cooldown read restricted to one kind (finding 5)",
     COOLDOWN_MUTANT_OLD, COOLDOWN_MUTANT_NEW),
    # review round 1, finding 6: the commit before the insert leaves the row to the session's rollback
    ("C1", "the commit moved before the insert (finding 6)", COMMIT_MUTANT_OLD, COMMIT_MUTANT_NEW),
    ("C6", "the floor removed from the admission's read (round 2, F1)", FLOOR_MUTANT_OLD, FLOOR_MUTANT_NEW),
    ("C5", "the admission lock removed", LOCK_MUTANT_OLD, ""),
    ("C5", "the admission lock taken after the cooldown read", LOCK_MUTANT_OLD + COOLDOWN_READ_OLD,
     LOCK_AFTER_READ),
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
     "            _ping_log(_ping_resolved_line(kind, configured, role_word, len(ping_roles),\n"
     "                                          guild.roles if guild is not None else ()))\n", ""),
    ("B4", "the first casual ping does not wait for its startup line",
     '(("lfp", ranked), ("casual", casual)) if wanted]', '(("lfp", ranked),) if wanted]'),
    ("B4", "two sequential startup waits, one per kind (finding 4)",
     '            await _ping_startup_wait(*[kind for kind, wanted in (("lfp", ranked), ("casual", casual)) '
     'if wanted])\n',
     '            for kind_w in [k for k, wanted in (("lfp", ranked), ("casual", casual)) if wanted]:\n'
     '                await _ping_startup_wait(kind_w)\n'),
    ("B4", "the NO line lists no role names (finding 10)",
     '    seen = ", ".join(repr(r.name)[:60] for r in near) if near else "none"\n', '    seen = "none"\n'),
    ("B4", "the NO line lists every near name, uncut",
     ")][:PING_HINTS_MAX]\n    seen = \", \".join(repr(r.name)[:60] for r in near)",
     ")]\n    seen = \", \".join(repr(r.name) for r in near)"),
    ("B4", "the NO line's names in the guild's order, not a stable one",
     "for r in sorted(named, key=lambda r: (getattr(r, \"id\", 0), r.name))", "for r in named"),
    ("B7", "no line when both kinds resolve to one role (round 2, F7)",
     "            _ping_log(shared_line)\n", "            pass\n"),
    ("B7", "the shared-role test inverted",
     'if getattr(r, "id", None) in ranked_ids]', 'if getattr(r, "id", None) not in ranked_ids]'),
    ("B6", "the bot's declaration of the casual kind dropped",
     'api_get("/internal/lfp-pings?kinds=casual")', 'api_get("/internal/lfp-pings")'),
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
    anchor = "def _ping_resolved_line(kind, configured, role_word, mentioned, roles=()) -> str:\n"
    tree, shipped, edited = S.mutate(anchor, "# control: a comment only, no behaviour\n" + anchor)
    assert tree is not S.BASE_TREE
    for req in sorted(BOT_CHECKS):
        BOT_CHECKS[req](tree)


# -- the client, by its text (no build on this machine) --------------------------------------------
# K1 (finding 1): the LFP button is active whenever the player is not in a ranked match, ranked on or off;
#    every place that sets it active says so, and its click opens the prompt on Casual alone with ranked off.
# K2 (finding 7): the refusal of a ranked pick while ranked is off is drawn INSIDE the open prompt, by the
#    prompt's own draw code, from the same predicate SubmitLfpPing refuses on.

PLUGIN = os.path.join(REPO, "plugin")
REFUSAL = ("Ranked is off - only the Casual ping can be sent. Untick the ranked modes, or press Enable on the "
           "RANKED row first.")


def _plugin_texts():
    out = {}
    for name in ("NativeUI.cs", "CompetitiveUI.cs"):
        with open(os.path.join(PLUGIN, name), encoding="utf-8") as fh:
            out[name] = fh.read().replace("\r\n", "\n")
    return out


def _body(src, head):
    """The text of the method that starts at `head`, to its matching closing brace."""
    assert src.count(head) == 1, head
    i = src.index(head)
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        depth += {"{": 1, "}": -1}.get(src[k], 0)
        if depth == 0:
            return src[i:k + 1]
    raise AssertionError("no end of " + head)


def check_k1(texts):
    nat = texts["NativeUI.cs"]
    sets = re.findall(r"lfpBtn\.SetActive\(([^;]*)\);", nat)
    assert sets == ["!inRankedMatch"], sets
    assert re.findall(r"lfpBtn\s*=", nat) == ["lfpBtn="], "the button is created once"
    on = _body(nat, "private static void OnLfpButton()")
    assert "LfpPromptOpen = true;" in on and "RankedEnabled" not in on.replace("LfpRankedOn()", ""), on
    assert "bool rankedOn = LfpRankedOn();" in on and "LfpModeSel[LfpCasualIdx] = !rankedOn;" in on, on
    assert "LfpModeSel[0] = rankedOn; LfpModeSel[1] = false; LfpModeSel[2] = false;" in on, on


def check_k2(texts):
    nat, ui = texts["NativeUI.cs"], texts["CompetitiveUI.cs"]
    pred = _body(nat, "public static bool LfpRankedPickRefused()")
    assert ("bool rankedPicked = LfpModeSel[0] || LfpModeSel[1] || LfpModeSel[2] || !LfpModeSel[LfpCasualIdx];"
            in pred and "return rankedPicked && !LfpRankedOn();" in pred), pred
    submit = _body(nat, "public static void SubmitLfpPing()")
    assert "if (LfpRankedPickRefused())" in submit and REFUSAL in submit, submit
    assert submit.index("if (LfpRankedPickRefused())") < submit.index("LfpPromptOpen = false;"), submit
    draw = _body(ui, "private static void DrawLfpPrompt()")
    guard = "if (NativeUI.LfpRankedPickRefused())\n                    GUI.Label("
    assert draw.count(guard) == 1, "the prompt does not draw the standing refusal line"
    line = draw[draw.index(guard):].split(";", 1)[0]
    assert 'I18n.Tr("%s")' % REFUSAL in line, line
    # the line sits between the mode row (y + 166, 26 high) and the buttons, inside the box
    assert "new Rect(x + 16f, y + 198f, w - 32f, 32f)" in line and "float w = 520f, h = 288f;" in draw, line
    assert draw.count("y + 236f, 180f, 32f)") == 2, "Send and Cancel moved under the line"


CLIENT_CHECKS = {"K1": check_k1, "K2": check_k2}
CLIENT_MUTANTS = [
    ("K1", "the button hidden while ranked is off (finding 1)", "NativeUI.cs",
     "lfpBtn.SetActive(!inRankedMatch);", "lfpBtn.SetActive(ranked&&!inRankedMatch);"),
    ("K1", "the prompt opens on 1v1 with ranked off", "NativeUI.cs",
     "LfpModeSel[LfpCasualIdx] = !rankedOn;", "LfpModeSel[LfpCasualIdx] = false;"),
    ("K2", "no standing refusal line in the prompt (finding 7)", "CompetitiveUI.cs",
     "                if (NativeUI.LfpRankedPickRefused())\n", "                if (false)\n"),
    ("K2", "the predicate forgets the empty pick's 1v1 fallback", "NativeUI.cs",
     " || !LfpModeSel[LfpCasualIdx];", ";"),
    ("K2", "SubmitLfpPing refuses on its own test, not the shared predicate", "NativeUI.cs",
     "            if (LfpRankedPickRefused())\n", "            if (!LfpRankedOn() && LfpModeSel[0])\n"),
]


@pytest.mark.parametrize("req", sorted(CLIENT_CHECKS))
def test_each_client_requirement_holds(req):
    CLIENT_CHECKS[req](_plugin_texts())


@pytest.mark.parametrize("req,what,where,old,new", CLIENT_MUTANTS,
                         ids=["%s: %s" % (m[0], m[1]) for m in CLIENT_MUTANTS])
def test_each_client_mutant_turns_its_requirement_red(req, what, where, old, new):
    texts = _plugin_texts()
    assert texts[where].count(old) == 1, old
    texts[where] = texts[where].replace(old, new, 1)
    _expect_red(CLIENT_CHECKS[req], texts, what=what)


# -- the base fixture against git (review round 2, F8) ---------------------------------------------

def test_the_base_fixture_is_main_at_base_commit():
    """The fixture's two spans are main.py's at BASE_COMMIT, read with `git show`, where git has that
    object. On a seat or in a copied tree there is no such object: this ONE check is skipped there, with
    that reason; the differentials themselves run from the fixture everywhere."""
    try:
        out = subprocess.run(["git", "-C", REPO, "show", "%s:backend/api/main.py" % BASE_COMMIT],
                             capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as ex:
        pytest.skip("git is not usable here (%s): the fixture is checked against git where it is" % ex)
    if out.returncode != 0:
        pytest.skip("git has no object %s:backend/api/main.py here (exit %d): a seat or a copied tree"
                    % (BASE_COMMIT[:12], out.returncode))
    text = out.stdout.decode("utf-8")
    assert base_span("lfp_ping") == _segment(text)
    assert base_span("internal_lfp_pings") == pending_segment(text)
