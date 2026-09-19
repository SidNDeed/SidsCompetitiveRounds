"""Item 5 -- Mail <-> Discord relay.

Two kinds of test here, and the split is deliberate.

STRUCTURAL (always run, no database). The relay's whole safety argument is
that it cannot reach a rule the in-game path applies. That is a property of
SHAPE -- which function calls which, which SQL reads which rows -- so it is
checked as shape, from outside, rather than by replaying the rules and
hoping the replay stays faithful. A behavioural test that re-implements a
gate passes happily after the real gate is deleted.

LIVE (MAIL_RELAY_TEST_PG_DSN). The fan-out is one INSERT ... SELECT whose
whole job is deciding WHO gets a DM. That is a question about rows, so it
is answered against a real PostgreSQL:

    MAIL_RELAY_TEST_PG_DSN="postgresql://postgres@127.0.0.1:55432/mailtest" \
        python -m pytest backend/tests/test_mail_discord_relay.py -q

Set MAIL_RELAY_TESTS_REQUIRED=1 to turn "no DSN" into a hard failure rather
than a skip -- a near-miss variable name otherwise reads as a clean run
(learning #521 family).
"""
import ast
import asyncio
import copy
import os
import re as _sql_re
import sys
import types
import urllib.parse as _urlparse
import uuid

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))

import mail_discord  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402

DSN_VAR = "MAIL_RELAY_TEST_PG_DSN"
DSN = os.environ.get(DSN_VAR)
REQUIRED = os.environ.get("MAIL_RELAY_TESTS_REQUIRED") == "1"

if REQUIRED and not DSN:
    raise RuntimeError(
        "MAIL_RELAY_TESTS_REQUIRED=1 but %s is unset -- refusing to report a "
        "green run for tests that would not collect. Check the variable NAME."
        % DSN_VAR)

def _refuse_unless_throwaway(dsn):
    """`_seed` runs DROP TABLE ... CASCADE on players, mail_messages,
    mail_recipients and pending_dms. The ONLY thing standing between this
    module and a real database is one environment variable, so the DSN has
    to name itself disposable before anything here runs. An inherited or
    mistyped production DSN must fail at import, loudly, rather than at the
    first DROP -- by which point the damage is done and the assertion is
    only reporting it (#721)."""
    # ALLOWLIST the host. A denylist of five fragments admitted every
    # other remote address there is -- `postgresql://u:p@10.0.0.50/mailtest`
    # named itself disposable, named no listed host, and would have had
    # four tables dropped on whatever answered. "Is not one of five known
    # production names" is not "is a throwaway"; only loopback is.
    parsed = _urlparse.urlsplit(dsn)
    try:
        host = (parsed.hostname or "").lower()
    except ValueError:                       # malformed authority
        host = "?"
    if host not in ("", "localhost", "127.0.0.1", "::1"):
        raise RuntimeError(
            "%s points at host %r. These tests DROP core tables and run "
            "against a database on this machine only." % (DSN_VAR, host))
    tail = (parsed.path or "").lstrip("/").split("?")[0].strip().lower()
    if not tail:
        tail = dsn.rsplit("/", 1)[-1].split("?")[0].strip().lower()
    if not (tail.startswith("mailtest") or tail.startswith("scratch")
            or tail.startswith("test")):
        raise RuntimeError(
            "%s names database %r. These tests DROP core tables, so they run "
            "only against a database named mailtest*/scratch*/test*."
            % (DSN_VAR, tail))
    # Kept underneath the allowlist rather than replaced by it: these name
    # real hosts wherever they appear, including in a socket directory that
    # carries no hostname at all.
    low = dsn.lower()
    for marker in ("192.168.", "duckdns", "competitive-rounds", "scr-a", "scr-b"):
        if marker in low:
            raise RuntimeError(
                "%s contains %r, which names a real host. These tests DROP "
                "core tables and run against a local throwaway only."
                % (DSN_VAR, marker))


if DSN:
    _refuse_unless_throwaway(DSN)


needs_pg = pytest.mark.skipif(
    not DSN, reason="%s unset; live relay fan-out check" % DSN_VAR)

# Exactly this many tests in this module need the DSN. Pinned from OUT here
# so that moving one behind the gate is a deliberate edit and not a silent
# "1 skipped" that still reads as a clean run.
LIVE_TESTS = 10


def _read(path):
    return open(path, encoding="utf-8").read()


MAIN_SRC = _read(main.__file__)
MODULE_SRC = _read(mail_discord.__file__)
BOT_SRC = _read(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "discord_bot.py"))


def _func(src, name):
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == name:
            return node
    raise AssertionError("no function named %s" % name)


def _called_names(node):
    """Calls in the function's BODY only. Walking the whole node would also
    collect the route's @app.post decorator and the Depends(get_db) in its
    signature, which are wiring rather than logic."""
    out = []
    for stmt in node.body:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Call):
                f = n.func
                if isinstance(f, ast.Name):
                    out.append(f.id)
                elif isinstance(f, ast.Attribute):
                    out.append(f.attr)
    return out


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeDb:
    """Answers db.execute() from a scripted list, in order, and keeps every
    statement it was handed. Enough to RUN mail_reply_from_discord, which
    is a sequence of reads around one call into the bound core -- and a
    test that runs the route cannot be satisfied by a shape the route no
    longer has."""

    def __init__(self, results):
        self._results = list(results)
        self.sql, self.params = [], []

    async def execute(self, stmt, params=None):
        self.sql.append(str(stmt))
        self.params.append(params)
        return _FakeResult(self._results.pop(0) if self._results else [])


def _run(coro):
    import asyncio
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


PLAYER_ROW = {"id": "00000001-0000-0000-0000-000000000000", "steam_id": "1",
              "display_name": "A", "mod_seen_at": None, "mail_from": "everyone"}


def _lift_bot(name, ns):
    """One function out of discord_bot.py, executed against fakes. The
    module builds a live bot at import, so it cannot be imported here --
    the same lift test_mail_bot.py and test_leaderboard_boards.py use."""
    node = copy.deepcopy(_func(BOT_SRC, name))
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 "discord_bot.py", "exec"), ns)
    return ns[name]


BOT_ID = 999


class _Ref:
    """A referenced message, in the three states Discord actually delivers:
    resolved, deleted, or absent (which forces the one fetch)."""

    def __init__(self, message_id, content=None, author=BOT_ID,
                 resolved=True, deleted=False, fetch_raises=False):
        self.message_id = message_id
        self.fetch_raises = fetch_raises
        self._msg = types.SimpleNamespace(
            content=content or "", id=message_id,
            author=types.SimpleNamespace(id=author))
        if deleted:
            self.resolved = _DeletedRef()
        elif resolved:
            self.resolved = self._msg
        else:
            self.resolved = None


class _DeletedRef:
    """Stands in for discord.DeletedReferencedMessage."""


class _Msg:
    """The parts of a discord.Message these handlers touch."""

    def __init__(self, content, ref=None, mid=77, author=5):
        self.content, self.id = content, mid
        self.reference = ref if isinstance(ref, _Ref) else (
            _Ref(ref) if ref else None)
        self.author = types.SimpleNamespace(id=author)
        self.sent, self.views, self.fetched = [], [], []
        msg = self

        async def send(text_, **kw):
            msg.sent.append(text_)
            msg.views.append(kw.get("view"))
            return types.SimpleNamespace(id=5000 + len(msg.sent))

        async def fetch_message(mid_):
            msg.fetched.append(int(mid_))
            r = msg.reference
            if r is not None and getattr(r, "fetch_raises", False):
                raise RuntimeError("404 Not Found")
            return getattr(r, "_msg", None)

        self.channel = types.SimpleNamespace(send=send,
                                             fetch_message=fetch_message)


def _lift_bot_names(names, ns):
    """Module-level ASSIGNMENTS out of discord_bot.py, into `ns`.

    The patterns and the alphabet are lifted rather than retyped for the same
    reason the functions are: a copy in the test proves the test agrees with
    itself (#342/#431)."""
    want = set(names)
    body = [nd for nd in ast.parse(BOT_SRC).body
            if isinstance(nd, ast.Assign) and len(nd.targets) == 1
            and isinstance(nd.targets[0], ast.Name)
            and nd.targets[0].id in want]
    assert len(body) == len(want), (
        "wanted %s, lifted %d" % (sorted(want), len(body)))
    ns.setdefault("re", _sql_re)
    exec(compile(ast.Module(body=body, type_ignores=[]), "discord_bot.py",
                 "exec"), ns)
    return ns


class _FakeButton:
    def __init__(self, style=None, label=None, custom_id=None, disabled=False):
        self.style, self.label = style, label
        self.custom_id, self.disabled = custom_id, disabled


class _FakeView:
    def __init__(self, timeout=None):
        self.timeout, self.children = timeout, []

    def add_item(self, item):
        self.children.append(item)


def _fake_discord():
    return types.SimpleNamespace(
        DeletedReferencedMessage=_DeletedRef,
        ButtonStyle=types.SimpleNamespace(secondary="secondary"),
        ui=types.SimpleNamespace(View=_FakeView, Button=_FakeButton))


def _mail_dm(status=200, data=None, threads=None, thread_status=200):
    """The whole DM routing path, lifted, with only the network faked.

    `_post_mail_reply` and `_ask_which_mail` are the REAL ones -- the refusal
    wording and the decision to refuse are exactly what these tests are about,
    and stubbing either would be supplying the answer. Returns (fn, posted,
    asked, ns)."""
    posted, asked = [], []

    async def _post(payload):
        posted.append(payload)
        return status, (data if data is not None else {})

    async def _threads(discord_id):
        asked.append(str(discord_id))
        if thread_status == 404:
            return "not_linked"
        if thread_status != 200:
            return None
        return list(threads or [])

    ns = {"_mail_reply_post": _post, "_relay_threads": _threads,
          "_mailpick": {}, "_MAILPICK_MAX": 500,
          "discord": _fake_discord(),
          "bot": types.SimpleNamespace(user=types.SimpleNamespace(id=BOT_ID)),
          "print": lambda *a, **k: None}
    _lift_bot_names(("RELAY_CODE_ALPHABET", "RELAY_CODE_LEN", "_CODE_BODY",
                     "RELAY_CODE_RE", "RELAY_CODE_ANY_RE",
                     "_RELAY_CODE_LEAD_RE"), ns)
    for fname in ("relay_code_line", "normalize_relay_code", "_mail_sent_line",
                  "_mailpick_view", "_post_mail_reply", "_ask_which_mail",
                  "_mailpick_click", "_handle_mail_dm"):
        _lift_bot(fname, ns)
    return ns["_handle_mail_dm"], posted, asked, ns


def _thread(code, sender="Bob", subject="Hi"):
    return {"relay_code": code, "sender_name": sender, "subject": subject,
            "created_at": "2026-09-18T00:00:00+00:00"}


def _slash_reply(status=200, data=None, guild=None, threads=None,
                 thread_status=200):
    """`cmd_mail_reply` against a fake ctx. Returns
    (fn, ctx, posted, said, deferred) -- `deferred` records how many posts
    had already happened when the defer ran, because deferring AFTER the
    request is the same as not deferring at all."""
    said, deferred = [], []
    _fn, posted, _asked, ns = _mail_dm(status=status, data=data,
                                       threads=threads,
                                       thread_status=thread_status)

    async def _defer(_ctx):
        deferred.append(len(posted))

    class _Ctx:
        def __init__(self):
            self.guild = guild
            self.author = types.SimpleNamespace(id=4242)
            self.message = None
            self.interaction = types.SimpleNamespace(id=555)

        async def send(self, content, **_kw):
            said.append(content)
            return types.SimpleNamespace(id=6000 + len(said))

    ns["_maybe_defer"] = _defer
    return _lift_bot("cmd_mail_reply", ns), _Ctx(), posted, said, deferred


class _Interaction:
    """The parts of a component interaction `_mailpick_click` touches."""

    def __init__(self, user_id, message_id):
        self.user = types.SimpleNamespace(id=user_id)
        self.said, self.ephemeral, self.edited = [], [], []
        inter = self

        class _Resp:
            async def send_message(self, content, ephemeral=False):
                inter.said.append(content)
                inter.ephemeral.append(bool(ephemeral))

            async def defer(self):
                pass

        async def _edit(**kw):
            inter.edited.append(kw.get("view"))

        self.response = _Resp()
        self.message = types.SimpleNamespace(id=message_id, edit=_edit)
        self.channel = types.SimpleNamespace(
            send=self._send, fetch_message=None)

    async def _send(self, content, **kw):
        self.said.append(content)
        self.ephemeral.append(False)
        return types.SimpleNamespace(id=7000)


class _AckResp:
    def __init__(self, status, body=""):
        self.status, self._body = status, body

    async def text(self):
        return self._body


class _AckPost:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


class _AckSession:
    """The one call `_ack_pending_dms` makes, with a status we choose."""

    def __init__(self, status, boom=False):
        self.status, self.boom, self.posts = status, boom, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append(json)
        if self.boom:
            raise RuntimeError("gateway down")
        return _AckPost(_AckResp(self.status, "server said no"))


def _ack_fn(status=200, boom=False):
    sess = _AckSession(status, boom)
    ns = {"http_session": sess, "API_SECRET_KEY": "k",
          "API_BASE_URL": "http://api:8000",
          "aiohttp": types.SimpleNamespace(
              ClientTimeout=lambda total=None: None),
          "print": lambda *a, **k: None}
    return _lift_bot("_ack_pending_dms", ns), sess


def _drain(rows, ack_ok=True, seen=None, unacked=None, boom_after=None):
    """`poll_pending_dms` against fakes. Returns (fn, ns, sent, acks, out)
    -- the loop's whole observable behaviour, so the map it builds while
    sending is tested where it is WRITTEN and not only where it is read."""
    sent, acks, out = [], [], []

    class _User:
        def __init__(self, uid):
            self.id = uid

        async def send(self, content):
            sent.append((self.id, content))
            return types.SimpleNamespace(id=1000 + len(sent))

        def __str__(self):
            return "user%s" % self.id

    class _Bot:
        def get_user(self, uid):
            return _User(uid)

        async def fetch_user(self, uid):
            return _User(uid)

    async def _ack(dm_ids, undeliverable=False, claims=None,
                   retry_ids=None, not_attempted_ids=None):
        acks.append({"ids": list(dm_ids), "und": bool(undeliverable),
                     "claims": dict(claims or {}),
                     "retried": list(retry_ids or []),
                     "unreached": list(not_attempted_ids or [])})
        return ack_ok

    async def _get(_path):
        return {"dms": [dict(r) for r in rows]}

    sleeps = []

    async def _sleep(secs):
        # The one await in the row loop that is not already inside a
        # try -- so this is how a batch gets cut short without the
        # process dying, which is the only state the credit-back exists
        # for. Real asyncio unless a test asks for the interruption.
        sleeps.append(secs)
        if boom_after is not None and len(sleeps) >= boom_after:
            raise RuntimeError("the gateway went away mid-batch")

    ns = {"api_get": _get, "bot": _Bot(),
          "asyncio": (asyncio if boom_after is None
                      else types.SimpleNamespace(sleep=_sleep)),
          "discord": types.SimpleNamespace(
              NotFound=type("NotFound", (Exception,), {}),
              Forbidden=type("Forbidden", (Exception,), {})),
          "_pdm_seen": seen if seen is not None else {},
          "_pdm_unacked": unacked if unacked is not None else set(),
          "_ack_pending_dms": _ack,
          "print": lambda *a, **k: out.append(" ".join(str(x) for x in a))}
    return _lift_bot("poll_pending_dms", ns), ns, sent, acks, out


def _queue_row(dm_id, mail_id=None, did="4242", content="you have new mail",
               claim=None):
    return {"dm_id": dm_id, "steam_id": "1", "discord_id": did,
            "display_name": "A", "content": content,
            "mail_id": mail_id, "attempts": 1,
            # Every hand-out carries one. A settlement that does not quote it
            # is one the server cannot match to a hand-out, and drops.
            "claim": claim or ("claim-%s" % dm_id)}


def _identifiers(src):
    """Every name the module actually REFERENCES. Parsed, never grepped:
    mail_discord.py's docstring explains at length why it must not call the
    send core, so it names it -- and a source grep cannot tell an
    explanation from a call (#342, #441)."""
    names = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Name):
            names.add(n.id)
        elif isinstance(n, ast.Attribute):
            names.add(n.attr)
    return names


# ── The gate count itself ────────────────────────────────────────────────

def test_the_live_test_count_is_what_this_module_declares():
    """LIVE_TESTS is load-bearing: it is the only thing that distinguishes
    "the database tests ran" from "the database tests were skipped and the
    run was green anyway". Counted from the source, so moving a test across
    the gate fails here rather than quietly shrinking the suite."""
    tree = ast.parse(_read(os.path.abspath(__file__)))
    gated = 0
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in node.decorator_list:
            name = d.attr if isinstance(d, ast.Attribute) else getattr(d, "id", "")
            if name == "needs_pg":
                gated += 1
    assert gated == LIVE_TESTS, (
        "LIVE_TESTS says %d, the module defines %d DSN-gated tests"
        % (LIVE_TESTS, gated))


# ── Structural: the reply path cannot diverge ────────────────────────────

def test_the_in_game_reply_route_only_resolves_identity_and_delegates():
    """The route must do nothing but work out WHO is speaking and hand over
    to the shared core. If a gate is ever added to the route instead of the
    core, the Discord path silently stops obeying it -- and that is exactly
    what this assertion is here to make impossible to do quietly."""
    called = _called_names(_func(MAIN_SRC, "mail_reply"))
    assert called == ["_mail_caller", "_mail_reply_core"], (
        "mail_reply should call _mail_caller then _mail_reply_core and "
        "nothing else; it calls %s. Anything extra here is a rule the "
        "Discord reply route will not run." % called)


def test_the_discord_route_cannot_reach_the_send_core_directly():
    """_mail_finish_send is the SEND core; it does not carry the reply
    gates (idempotency, the identity and sender locks, the sender gates,
    the authorization lookup, the "Re: " subject). Those live in
    _mail_reply_core. A Discord path that called the send core directly
    would skip all of them, so the module must not name it at all."""
    names = _identifiers(MODULE_SRC)
    assert "_mail_finish_send" not in names, (
        "mail_discord.py REFERENCES _mail_finish_send -- the Discord reply "
        "must go through _mail_reply_core, which is what applies the reply "
        "gates. (The module docstring may mention it; this checks code.)")
    assert "_mail_reply_core" not in names, (
        "mail_discord.py should reach the core through bind(), not by name")
    # ...and the route does not merely MENTION a reply core, it resolves the
    # bound one and awaits it. An identifier being present proves nothing:
    # the previous version of this assertion would have passed against a
    # route that never called anything.
    fn = _func(MODULE_SRC, "mail_reply_from_discord")
    resolved = [n for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_need"
                and n.args and isinstance(n.args[0], ast.Constant)
                and n.args[0].value == "reply_core"]
    assert resolved, "the route never resolves the bound reply core"
    awaited = [n for n in ast.walk(fn)
               if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
               and isinstance(n.value.func, ast.Name)
               and n.value.func.id == "reply_core"]
    assert awaited, "the bound reply core is resolved and never awaited"
    kw = {k.arg: getattr(k.value, "value", None) for k in awaited[0].value.keywords}
    assert kw.get("via") == "discord", (
        "the Discord route must record its provenance: via=%r" % kw.get("via"))
    assert kw.get("reply_all") is False, (
        "reply-all from a DM would fan a private answer out to a thread the "
        "player cannot see; via=%r reply_all=%r" % (kw.get("via"), kw.get("reply_all")))


def test_the_relay_fanout_inherits_suppression_instead_of_restating_it():
    """Who may receive a mail is decided once, by _MAIL_FANOUT_SQL, which
    writes 'delivered' or 'suppressed' per recipient. The relay selects
    those rows rather than re-deriving blocks and mail_from, so a
    suppressed copy produces no DM by construction. Re-deriving would be a
    second copy of the rule, free to drift."""
    sql = mail_discord._RELAY_FANOUT_SQL
    assert "mail_recipients" in sql and "delivery = 'delivered'" in sql, (
        "the relay must select from the fan-out's own rows, filtered to "
        "delivered; it reads: %s" % sql)
    for leaked in ("mail_blocks", "mail_from"):
        assert leaked not in sql, (
            "the relay restates %s instead of inheriting the fan-out's "
            "decision" % leaked)
    assert "p.mail_discord_relay" in sql and "p.discord_id IS NOT NULL" in sql


# ── Structural: the DM precedence chain ──────────────────────────────────

def test_there_is_exactly_one_definition_of_a_bug_report_dm():
    """on_message must ask whether the ticket handler WOULD parse a message
    before letting the relay claim it. Asking with a second copy of the
    regex would let the two drift, and the drift would show up as a
    player's bug report silently becoming a mail reply."""
    assert BOT_SRC.count("(?:ticket") == 1, (
        "the bug-report DM pattern is written %d times; both the handler "
        "and the precedence chain must test the same compiled object"
        % BOT_SRC.count("(?:ticket"))
    assert "_TICKET_DM_RE" in BOT_SRC



def test_a_working_ticket_comment_outranks_the_mail_path():
    """Precedence, and the order is the whole design:
       1. a Discord Reply aimed at a relay DM -> mail (above the "!" region)
       2. '#N <text>'                         -> ticket comment
       3. a leading thread code, else ASK     -> mail
       4. otherwise                           -> ticket usage text
    2 outranks 3 so no ticket comment that works today can be swallowed.

    MUTATION: move the `_handle_mail_dm` call above `_TICKET_DM_RE`. Must
    fail."""
    node = _func(BOT_SRC, "on_message")
    order = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == "match" and "_TICKET_DM_RE" in ast.unparse(n):
            order.append(("ticket", n.lineno))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == "_handle_mail_dm":
            order.append(("mail", n.lineno))
    order.sort(key=lambda x: x[1])
    assert [k for k, _ in order] == ["mail", "ticket", "mail"], order
    # ...and the two can never both match anyway: a code starts with "S" and
    # the ticket pattern needs a digit after an optional "#".
    ns = {}
    exec(compile(ast.Module(body=[n for n in ast.parse(BOT_SRC).body
                                  if isinstance(n, ast.Assign)
                                  and getattr(n.targets[0], "id", "") == "_TICKET_DM_RE"],
                            type_ignores=[]), "b", "exec"),
         {"_faq_re": _sql_re}, ns)
    tdm = ns["_TICKET_DM_RE"]
    assert tdm.match("#12 still broken")
    assert not tdm.match("%s still broken" % CODE_A), (
        "a thread code is being read as a bug-report number")



def test_an_unlinked_player_falls_through_rather_than_being_swallowed():
    """`not_linked` is not a mail failure: the player has no account behind
    this Discord id, so the ticket chain must still get its chance at the
    message exactly as it does today."""
    fn, _posted, _asked, _ns = _mail_dm(status=404, data={"detail": "not_linked"})
    msg = _Msg("yes", ref=_Ref(31, content=_dm_body(CODE_A)))
    assert _run(fn(msg)) == "NOT_MAIL"
    assert msg.sent == [], "falling through must be silent"



@pytest.mark.parametrize("verdict,fall_through", [
    ("HANDLED", False), ("ASK", False), ("NOT_MAIL", True), ("NOT_LINKED", True)])
def test_on_message_stops_only_for_the_two_verdicts_that_answered(verdict,
                                                                  fall_through):
    """The dispatcher's three-plus-one verdicts have to be read the same way
    at both call sites, and the READING is a source property: `in ("HANDLED",
    "ASK")`. A verdict that answered the player must not also reach the
    ticket handler, and one that did not must."""
    node = _func(BOT_SRC, "on_message")
    tests = [ast.unparse(n.test) for n in ast.walk(node) if isinstance(n, ast.If)]
    guards = [t for t in tests if "_handle_mail_dm" in t]
    assert len(guards) == 2, guards
    for g in guards:
        assert "'HANDLED', 'ASK'" in g.replace('"', "'"), g
    assert (verdict in ("HANDLED", "ASK")) is not fall_through



def test_a_refusal_is_reported_and_not_passed_to_the_ticket_path():
    """A real refusal from the core -- blocked, too long, rate-limited -- is
    this path's business and is reported here. Falling through would hand the
    player a bug-report usage message for a mail problem."""
    fn, posted, _asked, _ns = _mail_dm(status=429, data={"detail": "rate_limited"})
    msg = _Msg("yes", ref=_Ref(31, content=_dm_body(CODE_A)))
    assert _run(fn(msg)) == "HANDLED"
    assert "rate_limited" in msg.sent[0]
    assert posted, "the refusal must come from the server, not from a guess here"


def test_a_code_the_server_does_not_know_asks_rather_than_failing():
    """`unknown_code` means the player typed or quoted something that names
    no mail of theirs. That is the case the listing exists for.

    MUTATION: report the raw detail instead of offering the list. The
    wording assertion must fail."""
    fn, posted, _asked, _ns = _mail_dm(
        status=404, data={"detail": "unknown_code"}, threads=[_thread(CODE_B)])
    msg = _Msg("%s hello" % CODE_A)
    assert _run(fn(msg)) == "ASK"
    assert len(posted) == 1, "it must have tried the code the player gave"
    assert "doesn\u2019t match any mail sent to you" in msg.sent[0]
    assert CODE_B in msg.sent[0]



def test_a_reply_to_a_deleted_mail_says_so():
    """Specifically NOT the blocks/length/rate line: nothing the player did
    was refused, the mail they are answering is gone."""
    fn, _posted, _asked, _ns = _mail_dm(status=404, data={"detail": "not_found"})
    msg = _Msg("yes", ref=_Ref(31, content=_dm_body(CODE_A)))
    assert _run(fn(msg)) == "HANDLED"
    assert "isn\u2019t there any more" in msg.sent[0]
    assert "rate limit" not in msg.sent[0]


def test_the_confirmation_carries_the_thread_it_answered():
    """Replying to the CONFIRMATION must stay on the same thread, so the
    confirmation needs a marker of its own -- exactly one, or the router
    would refuse it as ambiguous.

    MUTATION: drop the relay_code_line append. The findall must fail."""
    fn, _posted, _asked, _ns = _mail_dm(data={"replied_to": {
        "known": True, "subject": "Hi", "sender_name": "Bob",
        "relay_code": CODE_A}})
    msg = _Msg("yes", ref=_Ref(31, content=_dm_body(CODE_A)))
    assert _run(fn(msg)) == "HANDLED"
    assert mail_discord.RELAY_CODE_RE.findall(msg.sent[0]) == [CODE_A]
    assert "Bob" in msg.sent[0] and "Hi" in msg.sent[0]


def test_a_server_that_cannot_name_the_thread_does_not_invent_one():
    """`known` false means the read-back failed AFTER the reply committed.
    Saying "to them - (no subject)" would state two facts it does not have,
    about a reply that did send."""
    fn, _posted, _asked, _ns = _mail_dm(data={"replied_to": {"known": False}})
    msg = _Msg("yes", ref=_Ref(31, content=_dm_body(CODE_A)))
    assert _run(fn(msg)) == "HANDLED"
    assert msg.sent[0] == "\u2709\ufe0f Sent your reply."



CODE_A = "SCR-AAAAAAAAAAAA"
CODE_B = "SCR-BBBBBBBBBBBB"


def _dm_body(code, lead="mail from Bob"):
    """What one of our relay DMs looks like: anything, then the marker."""
    return "%s\n-# \u21a9 %s" % (lead, code)


def test_the_posted_body_is_the_text_the_player_typed():
    """Posted UNTRIMMED. The core judges prohibited control characters before
    any trim, so trimming here would make Discord quietly more permissive
    than the in-game path it has to match. The strip only ever decides
    whether there is anything worth posting."""
    fn, posted, _asked, _ns = _mail_dm()
    msg = _Msg(" hi \n", ref=_Ref(31, content=_dm_body(CODE_A)))
    assert _run(fn(msg)) == "HANDLED"
    assert posted[0]["body"] == " hi \n", posted[0]["body"]
    assert posted[0]["relay_code"] == CODE_A
    assert posted[0]["source_message_id"] == "77", (
        "the key that survives a Discord redelivery must be the message id")
    # ...and a message with nothing in it is not a reply at all.
    fn2, posted2, _a2, _n2 = _mail_dm()
    assert _run(fn2(_Msg("   ", ref=_Ref(31, content=_dm_body(CODE_A))))) == "NOT_MAIL"
    assert posted2 == []


def test_exactly_one_marker_resolves_and_two_refuse():
    """T4. Our own messages carry exactly one marker line. Two means the
    router cannot tell which thread was named, and picking either would
    answer a thread the player did not point at -- with their words.

    NEGATIVE CONTROL: the one-marker case immediately below POSTs, so this
    is not passing because nothing ever posts (#391).

    MUTATION: take found[0] or found[-1] when len(found) > 1. Must fail."""
    fn, posted, _asked, _ns = _mail_dm(threads=[_thread(CODE_A), _thread(CODE_B)])
    two = _dm_body(CODE_A) + "\n-# \u21a9 %s" % CODE_B
    assert _run(fn(_Msg("yes", ref=_Ref(31, content=two)))) == "ASK"
    assert posted == [], "a reply was sent to a thread nobody named"
    # negative control
    fn2, posted2, _a2, _n2 = _mail_dm()
    assert _run(fn2(_Msg("yes", ref=_Ref(31, content=_dm_body(CODE_A))))) == "HANDLED"
    assert [p["relay_code"] for p in posted2] == [CODE_A]


def test_a_code_in_the_body_never_outranks_the_reference():
    """T5. The player pointed at a message; that outranks anything quoted
    inside their own text -- including a whole relay DM pasted in, which is
    exactly what a mobile client does when you quote.

    MUTATION: consult the body before the reference. Must fail."""
    fn, posted, _asked, _ns = _mail_dm()
    pasted = "here is what you sent me:\n" + _dm_body(CODE_A)
    msg = _Msg(pasted, ref=_Ref(31, content=_dm_body(CODE_B)))
    assert _run(fn(msg)) == "HANDLED"
    assert posted[0]["relay_code"] == CODE_B, (
        "the reply went to the thread the player QUOTED, not the one they "
        "replied to")


def test_a_reference_the_bot_cannot_read_asks_instead_of_guessing():
    """One boolean used to mean both "not our DM" and "we could not look",
    and those need opposite outcomes (#430). An unreadable reference is
    UNKNOWN: the router asks, and never silently re-routes the message.

    MUTATION: return "NOT_MAIL" on the fetch failure. Must fail."""
    fn, posted, asked, _ns = _mail_dm(threads=[_thread(CODE_A)])
    msg = _Msg("yes", ref=_Ref(31, resolved=False, fetch_raises=True))
    assert _run(fn(msg)) == "ASK"
    assert msg.fetched == [31], "the one fallback fetch was not attempted"
    assert posted == []
    assert asked == ["5"], "the listing was not requested for this player"
    assert "couldn\u2019t read" in msg.sent[0]


def test_a_deleted_reference_still_gets_its_one_fetch():
    """`reference.resolved` is a DeletedReferencedMessage when Discord knows
    the message is gone. That is not a resolved message and must take the
    same fallback path as an absent one."""
    fn, posted, _asked, _ns = _mail_dm()
    msg = _Msg("yes", ref=_Ref(31, content=_dm_body(CODE_A), deleted=True))
    assert _run(fn(msg)) == "HANDLED"
    assert msg.fetched == [31]
    assert posted[0]["relay_code"] == CODE_A


def test_a_reply_to_someone_elses_message_is_not_ours():
    """A Reply aimed at another bot's DM, or at the player's own message, is
    not mail -- and must fall through so the ticket path still gets it."""
    fn, posted, asked, _ns = _mail_dm(threads=[_thread(CODE_A)])
    msg = _Msg("yes", ref=_Ref(31, content=_dm_body(CODE_A), author=4242))
    assert _run(fn(msg)) == "NOT_MAIL"
    assert posted == [] and asked == [] and msg.sent == []


def test_a_reply_to_our_own_listing_asks_again_rather_than_picking():
    """The listing prints several codes. Replying to IT names no thread, and
    the loose pattern is what tells the router the message was one of ours.

    MUTATION: use RELAY_CODE_ANY_RE where RELAY_CODE_RE belongs, so the
    listing resolves to whichever code appears first. Must fail."""
    fn, posted, _asked, _ns = _mail_dm(threads=[_thread(CODE_A), _thread(CODE_B)])
    listing = "Tap the one you meant\n**Bob** - *Hi* - `%s`\n**Ann** - *Yo* - `%s`" \
        % (CODE_A, CODE_B)
    assert _run(fn(_Msg("the first one", ref=_Ref(31, content=listing)))) == "ASK"
    assert posted == []


def test_a_plain_dm_leading_with_a_code_is_a_reply_to_that_thread():
    """No reference at all -- mobile, or a cleared conversation. A LEADING
    code is an instruction; the rest of the line is the message."""
    fn, posted, _asked, _ns = _mail_dm()
    assert _run(fn(_Msg("%s thanks, fixed" % CODE_A))) == "HANDLED"
    assert posted[0]["relay_code"] == CODE_A
    assert posted[0]["body"] == "thanks, fixed"
    # lowercase, and the separators people actually type
    fn2, posted2, _a2, _n2 = _mail_dm()
    assert _run(fn2(_Msg("scr aaaaaaaaaaaa: ok"))) == "HANDLED"
    assert posted2[0]["relay_code"] == CODE_A, posted2[0]


def test_a_plain_dm_with_no_code_offers_the_list_and_sends_nothing():
    """The ONE behavioural loss in this change, pinned so it stays a loss of
    a guess and not of the reply: the player is asked, and nothing is sent
    until they say which thread."""
    fn, posted, _asked, ns = _mail_dm(threads=[_thread(CODE_A), _thread(CODE_B)])
    msg = _Msg("it still happens")
    assert _run(fn(msg)) == "ASK"
    assert posted == []
    said = msg.sent[0]
    assert "couldn\u2019t tell which mail" in said
    assert CODE_A in said and CODE_B in said, (
        "the codes must be in the TEXT as well as on the buttons -- a "
        "restart takes the buttons and leaves the message")
    view = msg.views[0]
    assert [c.custom_id for c in view.children] == \
        ["scrmail:%s" % CODE_A, "scrmail:%s" % CODE_B]
    # ...and the words the player already typed are carried forward.
    assert list(ns["_mailpick"].values())[0]["body"] == "it still happens"


def test_a_player_with_no_relay_threads_still_reaches_the_ticket_path():
    """The refusal costs one tap only because there is something to tap. With
    nothing to offer there is nothing this path can do that the ticket path
    cannot, so it must get out of the way."""
    for kwargs in ({"threads": []}, {"thread_status": 500},
                   {"thread_status": 404}):
        fn, posted, _asked, _ns = _mail_dm(**kwargs)
        msg = _Msg("hello?")
        assert _run(fn(msg)) in ("NOT_MAIL", "NOT_LINKED"), kwargs
        assert posted == [] and msg.sent == [], kwargs



def test_a_real_command_in_a_reply_is_left_to_the_command():
    """A player replying to a relay DM with `!link ABC123` means the command.
    Mailing that line to whoever sent the mail both loses the command and
    sends an answer nobody asked for -- and the line carries a link code."""
    guards = _registered_command_guards()
    gate_a = [g for g in guards if g[1] and "reference" in g[0]]
    assert len(gate_a) == 1, guards
    # The Reply branch sits ABOVE the "!" region on purpose, and is gated on
    # there actually BEING a reference -- otherwise it would claim every DM.
    assert "message_id" in gate_a[0][0], gate_a[0][0]


def test_the_orm_declares_the_columns_the_migration_added():
    """An ORM assignment to an undeclared column is a silent no-op (#346),
    which is why players.mail_from was declared when 297 landed. 330's two
    columns were not."""
    assert "mail_discord_relay" in models.Player.__table__.c, \
        "players.mail_discord_relay exists in SQL and not in the ORM"
    assert "via" in models.MailMessage.__table__.c, \
        "mail_messages.via exists in SQL and not in the ORM"


# ── Structural: hostile text ─────────────────────────────────────────────

HOSTILE = [
    ("@everyone", "everyone"),
    ("@here", "here"),
    ("<@&12345>", "(@&12345)"),
    ("`fence`", "'fence'"),
    ("<http://example.com>", "(http://example.com)"),
    # Markdown. `-#` is the subtext syntax the relay's own footer uses, so a
    # sender who can emit it unescaped can write a line that renders as the
    # bot's own; the rest are formatting a mail body has no business
    # carrying into a DM.
    ("**bold**", "\\*\\*bold\\*\\*"),
    ("__under__", "\\_\\_under\\_\\_"),
    ("~~strike~~", "\\~\\~strike\\~\\~"),
    ("||spoiler||", "\\|\\|spoiler\\|\\|"),
    ("# heading", "\\# heading"),
    ("-# subtext", "-\\# subtext"),
]


@pytest.mark.parametrize("raw,expected", HOSTILE)
def test_keep_lines_changes_whitespace_only(raw, expected):
    """keep_lines exists so a relayed mail keeps its paragraphs. It must not
    become a second, weaker escaping path: every neutralisation has to hold
    identically in both modes.

    EQUALITY, not containment. "everyone" is a substring of "@everyone", so
    `expected in out` passed whether or not the mention was neutralised --
    a check that could not fail (#342)."""
    assert main._mail_discord_safe(raw, 200) == expected, raw
    assert main._mail_discord_safe(raw, 200, keep_lines=True) == expected, raw


def test_the_default_is_byte_identical_for_the_existing_callers():
    """Three moderation/report sinks already call this helper. `keep_lines`
    must not move them, so the default path is pinned against literals --
    not against a re-implementation of the transformation, which would
    silently follow the helper wherever it went."""
    for raw, want in [("a  b", "a b"),
                      ("a\nb\nc", "a b c"),
                      ("  x  ", "x"),
                      ("@everyone\n@here", "everyone here"),
                      ("<@1> `x` **b**", "(@1) 'x' \\*\\*b\\*\\*")]:
        assert main._mail_discord_safe(raw, 64) == want, repr(raw)


def test_the_bound_holds_after_escaping_not_before():
    """Escaping can only GROW the string, so a helper that truncates first
    returns more characters than the caller asked for -- and the relay's
    budget is what keeps a whole DM under Discord's 2000-character limit.
    A worst case is a body that is nothing but escapable characters."""
    for n in (8, 40, 200):
        out = main._mail_discord_safe("*" * 500, n)
        assert len(out) <= n, (n, len(out))
        # ...and never ends mid-escape, which would escape the next thing
        # the message appends -- the footer.
        assert (len(out) - len(out.rstrip("\\"))) % 2 == 0, repr(out)



def test_a_relayed_mail_cannot_forge_the_footers_own_syntax():
    """The footer is how a player learns they can answer. A body that
    renders as subtext, or as a heading, lets a sender write a line that
    reads like the bot's."""
    out = mail_discord.relay_dm_text(
        main._mail_discord_safe, sender_name="N", sender_steam_id="7",
        subject="S", body="-# Reply to this message to answer in-game",
        code="SCR-ABCDEFGHJKMN")
    assert "\n-# Reply to this message to answer in-game" in out, \
        "the real footer must still be there"
    assert out.count("-# Reply to this message to answer in-game") == 1, \
        "the body's imitation of the footer was not escaped"


def test_keep_lines_bounds_blank_runs_so_the_footer_stays_visible():
    out = main._mail_discord_safe("a\n\n\n\n\n\nb", 200, keep_lines=True)
    assert out == "a\n\nb", repr(out)



def test_a_worst_case_relayed_mail_fits_in_one_discord_message():
    """Discord refuses a message over 2000 characters. Every field here is
    player-controlled and at its maximum, so this is the real ceiling, not
    an estimate. The MARKER is what must survive the clip now -- the footer
    only teaches, while the marker is what makes the DM answerable at all."""
    text = mail_discord.relay_dm_text(
        main._mail_discord_safe,
        sender_name="N" * 400, sender_steam_id="7" * 20,
        subject="S" * 400, body="B" * 2000, code="SCR-ABCDEFGHJKMN")
    assert len(text) <= 2000, len(text)
    assert mail_discord.RELAY_CODE_RE.findall(text) == ["SCR-ABCDEFGHJKMN"], (
        "the marker is what a reply resolves from; it must survive the "
        "clipping of every other field")
    assert "Reply to this message" in text, (
        "the footer is what tells a player how to answer")


# ── Live: the fan-out decides the right recipients ───────────────────────

# The shape as it exists BEFORE migration 330 -- no mail_discord_relay, no
# via, no mail_id/dm_message_id/attempts. Every column the relay depends on
# is then added by applying the real migration file on top, so these tests
# exercise the artifact that will be deployed rather than my description of
# it. (The previous version of this block re-typed the post-330 shape by
# hand, which could only ever confirm what I already believed.)
BASE_SCHEMA = """
DROP TABLE IF EXISTS pending_dms, mail_recipients, mail_messages, players CASCADE;
CREATE TABLE players (
    id UUID PRIMARY KEY,
    steam_id VARCHAR(20) UNIQUE NOT NULL,
    discord_id VARCHAR(20) UNIQUE,
    display_name VARCHAR(64)
);
CREATE TABLE mail_messages (
    id UUID PRIMARY KEY,
    sender_id UUID NOT NULL REFERENCES players(id),
    subject VARCHAR(120) NOT NULL,
    body VARCHAR(2000) NOT NULL
);
CREATE TABLE mail_recipients (
    message_id UUID NOT NULL REFERENCES mail_messages(id) ON DELETE CASCADE,
    recipient_id UUID NOT NULL REFERENCES players(id),
    kind TEXT NOT NULL,
    delivery TEXT NOT NULL CHECK (delivery IN ('delivered', 'suppressed')),
    read_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
);
CREATE TABLE pending_dms (
    id BIGSERIAL PRIMARY KEY,
    steam_id VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ,
    undeliverable BOOLEAN NOT NULL DEFAULT false
);
"""

SQL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sql")
MIGRATION_330 = _read(os.path.join(SQL_DIR, "330_mail_discord_relay.sql"))


def _pg(sql, *names):
    """SQLAlchemy ':name' binds -> asyncpg '$n', in the order given.

    The point is not convenience: it is that the statement under test stays
    the module's own string. A retyped copy stops being evidence the moment
    the real one changes, which is exactly how a schema assumption survives
    a migration edit."""
    for i, nm in enumerate(names, 1):
        sql = _sql_re.sub(r":%s\b" % nm, "$%d" % i, sql)
    assert ":" not in sql.replace("::", ""), "an unbound :name survived: " + sql
    return sql

async def _claim(conn, lim=None):
    """The poll route's own claim statement, bound as the route binds it.

    NOT a read: it locks and charges the rows it returns, which is the
    whole of HIGH r3-6 and is why no test here may substitute a plain
    SELECT for it -- the charge and the selection being one statement is
    the property."""
    return await conn.fetch(
        _pg(main._PENDING_DM_CLAIM_SQL, "lim", "k_op", "k_relay", "claim_secs"),
        main.PENDING_DM_BATCH if lim is None else lim,
        main._PDM_K_OP, main._PDM_K_RELAY, main.PENDING_DM_CLAIM_SECONDS)


_code_seq = [0]


def _code():
    """A distinct thread code per seeded relay row.

    Distinct because `idx_pending_dms_relay_code` is UNIQUE on (relay_code,
    steam_id): two rows of one player sharing a code is exactly what the
    index forbids, and a seed that produced it would be asserting against a
    schema the migration does not create."""
    _code_seq[0] += 1
    return "SCR-%012d" % _code_seq[0]


MAIL = "33333333-3333-3333-3333-333333333333"
# (id, steam_id, discord_id, relay_on, delivery, should_get_a_dm)
CAST = [
    ("a", "1", "d1", True, "delivered", True),
    ("b", "2", "d2", True, "suppressed", False),   # blocked / mail_from
    ("c", "3", "d3", False, "delivered", False),   # relay turned off
    ("d", "4", None, True, "delivered", False),    # no Discord linked
]


async def _seed(conn, apply_twice=True):
    """Pre-330 tables, then the REAL migration -- applied twice by default,
    because "idempotent and re-runnable" is a claim in the migration's own
    header and a claim is not a test."""
    await conn.execute(BASE_SCHEMA)
    await conn.execute(MIGRATION_330)
    if apply_twice:
        await conn.execute(MIGRATION_330)
    await conn.execute(
        "INSERT INTO players (id, steam_id, discord_id, mail_discord_relay)"
        " VALUES ('99999999-9999-9999-9999-999999999999', '0', 'd0', true)")
    for tag, steam, did, relay, _delivery, _want in CAST:
        await conn.execute(
            "INSERT INTO players (id, steam_id, discord_id, mail_discord_relay)"
            " VALUES ($1, $2, $3, $4)",
            "0000000%s-0000-0000-0000-000000000000" % tag.replace("a", "1")
            .replace("b", "2").replace("c", "3").replace("d", "4"),
            steam, did, relay)
    await conn.execute(
        "INSERT INTO mail_messages (id, sender_id, subject, body)"
        " VALUES ($1, '99999999-9999-9999-9999-999999999999', 'subj', 'body')",
        MAIL)
    for tag, steam, _d, _r, delivery, _want in CAST:
        pid = ("0000000%s-0000-0000-0000-000000000000"
               % tag.replace("a", "1").replace("b", "2")
               .replace("c", "3").replace("d", "4"))
        await conn.execute(
            "INSERT INTO mail_recipients (message_id, recipient_id, kind, delivery)"
            " VALUES ($1, $2, 'to', $3)", MAIL, pid, delivery)


def _asyncpg_sql():
    """The module's SQL is written for SQLAlchemy's :name binds; asyncpg
    speaks $1. Rewriting it here rather than keeping a second copy is the
    point -- the statement under test is the one production runs."""
    sql = mail_discord._RELAY_FANOUT_SQL
    return sql.replace("CAST(:content AS text)", "$1").replace(
        "CAST(:mid AS uuid)", "$2").replace("CAST(:code AS text)", "$3")


@needs_pg
def test_the_fanout_dms_exactly_the_recipients_who_should_get_one():
    import asyncio
    import asyncpg

    async def run():
        conn = await asyncpg.connect(DSN)
        try:
            await _seed(conn)
            await conn.execute(_asyncpg_sql(), "the DM body", MAIL, _code())
            rows = await conn.fetch(
                "SELECT steam_id FROM pending_dms WHERE mail_id = $1"
                " ORDER BY steam_id", MAIL)
            return [r["steam_id"] for r in rows]
        finally:
            await conn.close()

    got = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(run())
    want = sorted(s for _t, s, _d, _r, _dl, wants in CAST if wants)
    assert got == want, (
        "relayed to %s, expected %s -- suppressed, relay-off and unlinked "
        "recipients must all produce no DM" % (got, want))


def test_every_column_330_defaults_is_declared_so_the_orm_lets_sql_supply_it():
    """A NOT NULL column that the migration gives a DEFAULT, and that the ORM
    declares with neither a Python default nor a server_default, is not "left
    to SQL" -- SQLAlchemy sends it as an explicit NULL, PostgreSQL never
    applies its own DEFAULT, and the row is refused. Creating a player would
    fail at flush() on first contact from a new Steam ID.

    Established by running it, not by reading the ORM docs: an unset column of
    that shape emits `INSERT ... (col_a) VALUES ($1)` with `None`, while the
    same column declared `server_default=FetchedValue()` is left out of the
    statement entirely and read back afterwards.

    This asserts the class rather than the one column the review named: every
    NOT NULL column migration 330 adds with a DEFAULT must declare one side or
    the other.
    """
    import sqlalchemy

    added = _sql_re.findall(
        r"ALTER TABLE\s+(\w+)\s+ADD COLUMN(?:\s+IF NOT EXISTS)?\s+(\w+)\s+"
        r"([^;]*?DEFAULT[^;]*?);",
        MIGRATION_330, _sql_re.I | _sql_re.S)
    assert added, ("no defaulted ADD COLUMN found in migration 330; this test "
                   "has stopped reading the migration it names")

    mapped = {m.local_table.name: m.local_table
              for m in models.Base.registry.mappers}

    missing, checked = [], []
    for table, column, decl in added:
        if "NOT NULL" not in decl.upper():
            continue
        tbl = mapped.get(table)
        if tbl is None or column not in tbl.c:
            continue          # not every migrated table is mapped in the ORM
        col = tbl.c[column]
        checked.append("%s.%s" % (table, column))
        if col.default is None and col.server_default is None:
            missing.append("%s.%s" % (table, column))

    assert checked, ("the migration's defaulted NOT NULL columns matched no "
                     "mapped ORM column; the join between them has broken and "
                     "this test is now asserting nothing")
    assert not missing, (
        "%r declare neither a Python default nor a server_default, so "
        "SQLAlchemy sends NULL for them and PostgreSQL never applies its own "
        "DEFAULT -- creating a row without setting them fails at flush()"
        % (missing,))
    # named explicitly so a rename cannot quietly empty the loop above
    assert "players.mail_discord_relay" in checked, checked
    assert isinstance(
        models.Player.__table__.c.mail_discord_relay.server_default,
        sqlalchemy.FetchedValue), (
        "mail_discord_relay must let the database supply its value")


@needs_pg
def test_the_via_check_refuses_anything_but_game_or_discord():
    import asyncio
    import asyncpg

    # The constraint is `CHECK (via IN ('game', 'discord'))` (330:94). Trying
    # ONE rejected value cannot tell that apart from `CHECK (via <> 'email')`,
    # which admits 'slack', '' and every case variant. So the oracle is the
    # whole boundary: every accepted value accepted, every neighbouring value
    # refused. 'slack' and '' are the mutation control -- they are the values
    # a <>-shaped constraint would let through.
    ACCEPT = ("game", "discord")
    REFUSE = ("email", "slack", "", "GAME", "Discord", " game", "game ")

    async def run():
        conn = await asyncpg.connect(DSN)
        out = {}
        try:
            await _seed(conn)
            # asyncpg runs each execute in its own implicit transaction, so a
            # refused one does not poison the next.
            for value in ACCEPT + REFUSE:
                try:
                    await conn.execute(
                        "UPDATE mail_messages SET via = $2 WHERE id = $1",
                        MAIL, value)
                    out[value] = "accepted"
                except asyncpg.CheckViolationError:
                    out[value] = "refused"
            return out
        finally:
            await conn.close()

    got = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(run())
    wrong_accept = [v for v in REFUSE if got.get(v) != "refused"]
    wrong_refuse = [v for v in ACCEPT if got.get(v) != "accepted"]
    assert not wrong_accept, (
        "via accepted %r, outside ('game','discord'); the client renders this "
        "as provenance and must not be handed an unknown one" % (wrong_accept,))
    assert not wrong_refuse, (
        "via refused %r, which the feature actually writes" % (wrong_refuse,))


@needs_pg
def test_deleting_a_mail_takes_its_queued_dms_and_nothing_else():
    import asyncio
    import asyncpg

    async def run():
        conn = await asyncpg.connect(DSN)
        try:
            await _seed(conn)
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content) VALUES ('9', 'generic')")
            await conn.execute(_asyncpg_sql(), "the DM body", MAIL, _code())
            await conn.execute("DELETE FROM mail_messages WHERE id = $1", MAIL)
            return (
                await conn.fetchval(
                    "SELECT COUNT(*) FROM pending_dms WHERE mail_id IS NOT NULL"),
                await conn.fetchval(
                    "SELECT COUNT(*) FROM pending_dms WHERE mail_id IS NULL"))
        finally:
            await conn.close()

    mail_rows, generic_rows = asyncio.get_event_loop_policy() \
        .new_event_loop().run_until_complete(run())
    assert mail_rows == 0, "the cascade left %d orphaned relay rows" % mail_rows
    assert generic_rows == 1, (
        "the cascade removed %d generic queue rows; it must touch only rows "
        "that belong to the deleted mail" % (1 - generic_rows))


@pytest.mark.parametrize("dsn", [
    "postgresql://u:p@192.168.72.199:5432/mailtest",        # right name, real host
    "postgresql://u:p@localhost:55432/competitive_rounds",  # local, real database
    "postgresql://u:p@localhost:55432/postgres",
    "postgresql://u:p@competitive-rounds.duckdns.org:5432/testdb",
    # Codex r2's control: a throwaway NAME on a host the denylist never
    # heard of. The old guard admitted this and dropped four tables on it.
    "postgresql://u:p@10.0.0.50:5432/mailtest_prod",
    "postgresql://u:p@db.internal:5432/testdb",
    "postgresql://u:p@[2001:db8::1]:5432/scratch",
])
def test_the_live_gate_refuses_a_dsn_that_is_not_a_throwaway(dsn):
    """The guard is the whole safety property, so it is exercised rather than
    trusted: each of these is a plausible paste or an inherited variable."""
    with pytest.raises(RuntimeError):
        _refuse_unless_throwaway(dsn)


@pytest.mark.parametrize("dsn", [
    "postgresql://u:p@localhost:55432/mailtest",
    "postgresql://u:p@127.0.0.1:55432/scratch_relay",
    "postgresql://u:p@localhost:55432/testdb?sslmode=disable",
])
def test_the_live_gate_admits_a_throwaway(dsn):
    """...and a guard that refuses everything is the same as no tests (#342):
    the names the runbook actually uses must pass."""
    _refuse_unless_throwaway(dsn)



def test_a_failed_fanout_never_takes_the_mail_with_it():
    """The fan-out runs INSIDE the caller's sending transaction. PostgreSQL
    aborts the whole transaction on a failed statement, so catching the
    exception without a SAVEPOINT leaves a dead transaction and the caller's
    COMMIT of the mail itself then fails -- the handler written to protect
    the mail would be the thing that lost it.

    Run, not read: a structural check cannot tell a re-raise that is caught
    by an outer handler from one that escapes (#313)."""
    class _Boom:
        """Fails every INSERT, the way a code collision would."""

        def __init__(self, exc):
            self.exc, self.nested, self.codes = exc, 0, []

        def begin_nested(self):
            outer = self

            class _Cm:
                async def __aenter__(self_):
                    outer.nested += 1

                async def __aexit__(self_, *a):
                    return False
            return _Cm()

        async def execute(self, stmt, params=None):
            self.codes.append((params or {}).get("code"))
            raise self.exc

    from sqlalchemy.exc import IntegrityError as _IE
    prev = mail_discord._BOUND.get("discord_safe")
    mail_discord._BOUND["discord_safe"] = main._mail_discord_safe
    try:
        db = _Boom(_IE("insert", {}, Exception("duplicate key")))
        out = _run(mail_discord.queue_mail_relay(
            db, mail_id=MAIL, sender_name="N", sender_steam_id="7",
            subject="S", body="B"))
        assert out == -1, "the fan-out escaped into the send path"
        assert db.nested == 2, (
            "each attempt must get its own savepoint: %s" % db.nested)
        assert len(db.codes) == 2 and db.codes[0] != db.codes[1], (
            "the retry reused the colliding code: %s" % db.codes)
        # ...and an error that is NOT a collision is still fail-soft, with
        # only one attempt -- retrying a real fault would just do it twice.
        db2 = _Boom(RuntimeError("the database went away"))
        assert _run(mail_discord.queue_mail_relay(
            db2, mail_id=MAIL, sender_name="N", sender_steam_id="7",
            subject="S", body="B")) == -1
        assert db2.nested == 1, db2.nested
    finally:
        mail_discord._BOUND["discord_safe"] = prev


def test_the_fanout_is_wrapped_in_a_savepoint_and_not_a_bare_try():
    """The behaviour above is produced by begin_nested specifically, and a
    bare try/except would pass a green suite while breaking production --
    there is no in-process transaction for it to abort."""
    node = _func(MODULE_SRC, "queue_mail_relay")
    assert any(isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "begin_nested"
               for n in ast.walk(node)), \
        "no db.begin_nested() around the fan-out INSERT"
    assert any(isinstance(n, ast.Name) and n.id == "_RELAY_FANOUT_SQL"
               for n in ast.walk(node))



def test_a_reply_from_discord_derives_its_key_from_the_message():
    """A reply can commit while its confirmation fails, and Discord may
    redeliver a message; both are a repeat of the SAME message and must not
    become two mails (#172). The key is derived from the message id, so it
    survives the retry boundary."""
    a = mail_discord.reply_idempotency_key("77")
    assert a == mail_discord.reply_idempotency_key("77"), "not stable"
    assert a != mail_discord.reply_idempotency_key("78")
    assert uuid.UUID(str(a)).version == 5, "must be derived, not minted"
    # Every bot caller supplies a source, and the same one on the retry path.
    for name in ("_post_mail_reply", "cmd_mail_reply", "_mailpick_click"):
        body = ast.unparse(_func(BOT_SRC, name))
        assert "source_message_id" in body, name
    # A tap reuses the source id of the message that asked, so tapping twice
    # collapses onto one reply rather than sending a second.
    fn, posted, _asked, ns = _mail_dm(threads=[_thread(CODE_A)])
    msg = _Msg("it broke again")
    assert _run(fn(msg)) == "ASK"
    assert posted == []
    key = str(list(ns["_mailpick"])[0])
    click = ns["_mailpick_click"]
    inter = _Interaction(user_id=5, message_id=key)
    _run(click(inter, "scrmail:%s" % CODE_A))
    assert len(posted) == 1
    assert posted[0]["source_message_id"] == "77", posted[0]
    assert posted[0]["body"] == "it broke again"
    # ...and the second tap spends no request at all.
    _run(click(_Interaction(user_id=5, message_id=key), "scrmail:%s" % CODE_A))
    assert len(posted) == 1, "a double tap became two replies"


def test_a_tap_from_somebody_else_is_refused():
    """The listing lives in one player's DMs, so this is belt-and-braces --
    but the check costs nothing and the thing it protects is a mail sent in
    someone else's name."""
    fn, posted, _asked, ns = _mail_dm(threads=[_thread(CODE_A)])
    msg = _Msg("mine", mid=77)
    assert _run(fn(msg)) == "ASK"
    key = str(list(ns["_mailpick"])[0])
    other = _Interaction(user_id=9999, message_id=key)
    _run(ns["_mailpick_click"](other, "scrmail:%s" % CODE_A))
    assert posted == []
    assert other.ephemeral == [True]
    assert "isn\u2019t your reply" in other.said[0]


def test_a_tap_the_process_has_forgotten_says_what_to_type():
    """The state is process-local by design, and its loss must cost a retype
    rather than a red "interaction failed" (#430). The code is still printed
    in the message above the buttons, so the instruction is actionable."""
    _fn, posted, _asked, ns = _mail_dm()
    inter = _Interaction(user_id=5, message_id="nosuch")
    _run(ns["_mailpick_click"](inter, "scrmail:%s" % CODE_A))
    assert posted == []
    assert inter.ephemeral == [True]
    assert CODE_A in inter.said[0] and "expired" in inter.said[0]



def test_a_reacked_queue_row_keeps_the_outcome_it_had():
    """A set could only say "seen". Re-acking from a set therefore reported
    every remembered row as DELIVERED -- including one whose DM was refused.
    The message id that used to be recorded beside the outcome is gone with
    the maps: the DM carries its own thread code now, so there is nothing
    left to replay."""
    assert "_pdm_seen_ids" not in BOT_SRC, "the membership-only set is back"
    src_ = ast.get_source_segment(BOT_SRC, _func(BOT_SRC, "poll_pending_dms")) or ""
    assert "_pdm_seen[did_key] = True" in src_, \
        "an undeliverable outcome is not being recorded"
    assert "_pdm_seen[did_key] = False" in src_, \
        "a delivered row does not record its outcome, so a re-ack re-DMs it"
    assert "(dead if _pdm_seen[did_key] else delivered)" in " ".join(src_.split()), \
        "the re-ack path does not read the recorded outcome"
    # ...and by running it: a refused row re-acks as undeliverable, not as
    # delivered, which is the whole of the defect.
    seen, unacked = {}, set()
    fn, ns, _sent, _acks, _out = _drain(
        [_queue_row("r1", did="nonsense")], ack_ok=False,
        seen=seen, unacked=unacked)
    _run(fn())
    assert seen == {"r1": True}, seen
    fn2, _n2, sent2, acks2, _o2 = _drain(
        [_queue_row("r1", did="nonsense")], seen=seen, unacked=unacked)
    _run(fn2())
    assert sent2 == []
    assert [a for a in acks2 if a["ids"] == ["r1"]][0]["und"] is True, acks2



def test_the_migration_states_the_bot_before_api_order():
    """The header is the only place the order is written down, and it is read
    by whoever runs the deploy."""
    head = MIGRATION_330[:4000]
    assert "DEPLOY ORDER" in head
    assert "then the BOT, then the api" in head, head[:600]
    # The reason the order was once a HAZARD is retracted rather than
    # deleted: a header that just states a conclusion invites the next reader
    # to re-derive it wrongly.
    assert "preference rather than a hazard" in head, head[:600]
    # ...and nothing this migration REMOVES is still promised by it. Read
    # from the SQL, not from the file: the header names `dm_message_id` and
    # "most recent mail" on purpose, because retracting a mechanism means
    # saying which one, and a check that cannot tell a retraction from a
    # promise would forbid the explanation (#342/#441).
    sql_only = "\n".join(
        l for l in MIGRATION_330.split("\n") if not l.lstrip().startswith("--"))
    for gone in ("dm_message_id", "idx_pending_dms_dm_message",
                 "idx_pending_dms_recent"):
        assert gone not in sql_only, (
            "%s is still in the executable half of the migration" % gone)
    # The retraction itself has to be there, or the next reader re-derives
    # the hazard wrongly (#351/#432).
    assert "dm_message_id" in MIGRATION_330, (
        "the header no longer says what was removed")


def test_the_dm_footer_promises_a_command_that_exists():
    """The relay DM tells every player to type `/mail relay off`. A footer
    is a claim, and a claim that cannot be traced to code is a finding
    (#302) -- here it would be one the player finds first."""
    assert "/mail relay off" in mail_discord.RELAY_FOOTER
    tree = ast.parse(BOT_SRC)
    groups, subs = set(), set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in node.decorator_list:
            if not isinstance(d, ast.Call):
                continue
            name = d.func.attr if isinstance(d.func, ast.Attribute) else ""
            val = ""
            for kw in d.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    val = kw.value.value
            if name == "hybrid_group" and val:
                groups.add(val)
            elif name == "command" and val:
                subs.add(val)
    assert "mail" in groups, "no `/mail` group; the footer points at nothing"
    assert "relay" in subs, "no `relay` subcommand; `/mail relay off` is a dead promise"
# ── The remaining round-1 MEDIUMs, pinned ────────────────────────────────



def test_the_bot_does_not_pre_judge_text_the_core_must_judge():
    """Neither bot caller may strip the body it POSTS. The core judges
    prohibited control characters before any trim, so a body ending in LF,
    U+0085 or U+2028 is refused in game -- and a bot that trimmed first would
    be quietly more permissive than the path it has to match.

    A strip is allowed where it decides whether there is anything worth
    sending at all; it is not allowed on the value that is sent. So the
    assertion is about the ARGUMENT to the post, not about the presence of
    the word `strip` anywhere in the function."""
    for name in ("_post_mail_reply", "cmd_mail_reply", "_mailpick_click"):
        node = _func(BOT_SRC, name)
        for n in ast.walk(node):
            if not isinstance(n, ast.Call):
                continue
            for kw in n.keywords:
                if kw.arg == "body":
                    assert "strip" not in ast.unparse(kw.value), \
                        "%s posts a trimmed body: %s" % (name, ast.unparse(kw.value))
            for key in [k for k in getattr(n, "keywords", [])]:
                pass
        # dict literals too -- the payload is built as one
        for n in ast.walk(node):
            if isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values):
                    if isinstance(k, ast.Constant) and k.value == "body":
                        assert "strip" not in ast.unparse(v), \
                            "%s posts a trimmed body" % name
    # ...and by running it: the body arrives byte-identical.
    fn, posted, _asked, _ns = _mail_dm()
    raw_body = " leading and trailing \u2028\n"
    assert _run(fn(_Msg(raw_body, ref=_Ref(31, content=_dm_body(CODE_A))))) == "HANDLED"
    assert posted[0]["body"] == raw_body



def test_the_drain_order_is_total():
    """Rows queued by one fan-out share a created_at to the microsecond, so
    without a tiebreaker LIMIT could split them differently on consecutive
    polls -- which is how a row at the boundary is handed out twice or not
    at all."""
    sql = main._PENDING_DM_CLAIM_SQL
    # Four: each class orders its LIMIT subquery and numbers its rows by the
    # same total order, or the two halves disagree about which row is
    # "oldest" and the weighting lands on a different row each poll.
    assert sql.count("ORDER BY created_at, id") == 4, (
        "one of the four orderings in the claim has lost its tiebreaker")
    # ...and the order the rows are HANDED OUT in is total as well. `k` is
    # the interleave key, `cls` separates the two classes at an equal k, and
    # the row id breaks any remaining tie.
    assert "ORDER BY pk.k, pk.cls, c.id" in " ".join(sql.split()), (
        "the rows are handed to the bot in an order LIMIT can split "
        "differently on consecutive polls")


def test_the_claim_locks_inside_the_limit_and_not_beside_the_window():
    """`FOR UPDATE SKIP LOCKED` has to sit INSIDE the LIMIT block: PostgreSQL
    rejects a locking clause alongside a window function, so `row_number()`
    is computed over the already-locked set rather than over the whole table.

    MUTATION: hoist the locking clause out to the outer query. PostgreSQL
    refuses the statement, which the live claim tests then catch."""
    flat = " ".join(main._PENDING_DM_CLAIM_SQL.split())
    assert flat.count("FOR UPDATE SKIP LOCKED") == 2, flat
    # Bound to its own LIMIT block, both times. Hoisted out to the outer
    # query it would sit beside `row_number()`, which PostgreSQL refuses --
    # so this shape is what makes the window compute over the LOCKED set.
    assert len(_sql_re.findall(
        r"LIMIT :lim FOR UPDATE SKIP LOCKED", flat)) == 2, (
        "a locking clause is no longer bound to its LIMIT block")



def test_a_malformed_thread_code_is_a_400_before_any_statement_sees_it():
    """`normalize_relay_code` is the gate, and it runs before the lookup --
    so a code that is not one never reaches a bind at all."""
    db = _FakeDb([[PLAYER_ROW]])
    req = mail_discord._ReplyFromDiscord(
        discord_id="d1", relay_code="'; DROP TABLE players;--",
        body="yes", source_message_id="77")
    with pytest.raises(HTTPException) as err:
        _reply_route(db, req)
    assert err.value.status_code == 400
    assert err.value.detail == "target_required"
    assert len(db.sql) == 1, "the thread lookup ran with a malformed code"


def test_a_failed_ack_is_not_forgotten_by_the_trim():
    """The >2000 trim cleared everything. A delivered row whose ack had
    just failed was therefore forgotten while the server still had it
    queued, and the next poll DMed it again -- a duplicate with no crash
    involved, which is wider than the at-least-once window this queue
    documents."""
    src = (ast.get_source_segment(
        BOT_SRC, _func(BOT_SRC, "poll_pending_dms")) or "").replace("\r\n", "\n")
    i_keep = src.find("keep = {k: v for k, v in _pdm_seen.items() if k in _pdm_unacked}")
    i_clear = src.find("_pdm_seen.clear()")
    assert -1 < i_keep < i_clear, (
        "the trim forgets rows whose ack never landed")
    assert "_pdm_seen.update(keep)" in src, "the kept rows are not put back"
    assert "_pdm_unacked.add(k)" in src and "_pdm_unacked.discard(k)" in src, (
        "nothing records whether an ack landed, so every row looks the same "
        "to the trim")
    # Whether the ack ANSWERS correctly is a question about its paths, and
    # a set of its return values cannot tell them apart -- flipping the
    # non-200 path to True left {True, False} unchanged. Run instead, in
    # test_the_ack_reports_whether_the_server_took_it.


@pytest.mark.parametrize("status,landed", [(200, True), (500, False), (403, False)])
def test_the_ack_reports_whether_the_server_took_it(status, landed):
    """The trim keeps exactly the rows whose ack did not land, so a helper
    that says every ack landed hands it back the original defect: a
    delivered row forgotten while the server still has it queued, and
    DMed again on the next poll."""
    ack, sess = _ack_fn(status)
    assert _run(ack(["1"])) is landed, (
        "an ack the server answered %d reported %r" % (status, not landed))
    assert sess.posts and sess.posts[0]["dm_ids"] == ["1"]


def test_an_ack_that_never_reached_the_server_did_not_land():
    ack, _sess = _ack_fn(200, boom=True)
    assert _run(ack(["1"])) is False, (
        "a transport failure reported the ack as landed")
    # Nothing to say is vacuously fine, and must not cost a request.
    ack2, sess2 = _ack_fn(200)
    assert _run(ack2([])) is True and sess2.posts == []



def test_a_row_whose_ack_failed_is_re_acked_and_not_delivered_twice():
    """The at-least-once window this queue documents is a crash between
    send and ack. A failed ack is not a crash, and must not widen it."""
    seen, unacked = {}, set()
    rows = [_queue_row("r1", mail_id=MAIL)]
    fn, _ns, sent, _acks, _out = _drain(
        rows, ack_ok=False, seen=seen, unacked=unacked)
    _run(fn())
    assert len(sent) == 1 and unacked == {"r1"}, (sent, unacked)
    # The server still has it queued, so the next poll is handed it again.
    fn2, _ns2, sent2, acks2, _out2 = _drain(rows, ack_ok=True, seen=seen,
                                            unacked=unacked)
    _run(fn2())
    assert sent2 == [], "the row was delivered a second time"
    assert acks2[0]["ids"] == ["r1"], acks2
    assert acks2[0]["claims"].get("r1") == "claim-r1", (
        "the re-ack did not quote the claim this hand-out was made under, so "
        "the server cannot match it: %s" % acks2)
    assert unacked == set(), "the landed ack did not clear the row"


def test_the_relay_does_not_dm_a_deleted_envelope():
    """Every other reader of mail_recipients carries the soft-delete
    predicate. Inside the sending transaction it cannot yet matter, which
    is exactly why its absence would go unnoticed by whoever reuses the
    statement next."""
    assert "r.deleted_at IS NULL" in mail_discord._RELAY_FANOUT_SQL


def test_provenance_is_written_and_actually_read():
    """`via` was set by the Discord route and selected by nothing, so a
    reply that arrived from a DM was indistinguishable in game from one
    typed at F5 and the column's CHECK guarded a value no reader could
    observe. A column nothing reads is storage, not provenance."""
    detail = _func(MAIN_SRC, "mail_detail")
    src = ast.get_source_segment(MAIN_SRC, detail) or ""
    assert "m.via" in src, "the detail query does not select via"
    assert '"via"' in src, "the detail payload does not carry via"
    # The client has to bind it, or the server is talking to nobody.
    client = _read(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "plugin", "MailClient.cs"))
    ui = _read(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "plugin", "MailUI.cs"))
    assert 'Str(m, "via")' in client, "the C# parser does not read via"
    assert 'm.via == "discord"' in ui, "nothing renders the provenance"


def test_the_settings_row_can_say_it_does_not_know_yet():
    """DiscordLinked is a server fact that starts false, and the first poll
    can be most of a minute away -- so "not linked" and "not asked yet"
    were the same value and the row told a linked player to go and link.
    One boolean must not mean two things (#430)."""
    client = _read(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "plugin", "MailClient.cs"))
    ui = _read(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "plugin", "MailUI.cs"))
    assert "StatusEverSeen" in client and "StatusEverSeen = true" in client
    # The LABEL branch specifically. `!MailClient.StatusEverSeen` also
    # appears in two other methods, so its mere presence said nothing about
    # what the row renders -- deleting the label branch left the assertion
    # green and the row lying again.
    # Matched on the whole CALL, not on the words. The comment above this
    # branch in MailUI.cs quotes the label it replaced, so a bare substring
    # search finds the prose and reports the order backwards -- the same
    # trap as #342/#441, and there is no C# parser here to appeal to.
    lbl = 'I18n.Tr("Discord relay: <color=#AAAAAA>%s'
    assert lbl % "checking..." in ui, \
        "the row has no way to say it does not know yet"
    assert ui.index(lbl % "checking...") < ui.index(lbl % "link Discord first"), \
        "the not-linked label still wins while the answer is unknown"
    # ...and the row asks, rather than waiting out the poll interval.
    assert "MailClient.PollNow()" in ui
    # ...and a poll that CHANGES either flag repaints, or the row keeps
    # showing the answer from before a `/mail relay off` in Discord.
    assert "NativeUI.MarkDirty()" in client, \
        "nothing marks the settings row dirty when a status poll moves it"
    poll = client.split("StatusEverSeen = true", 1)[1][:1200]
    assert "NativeUI.MarkDirty()" in poll, \
        "MarkDirty is in the file but not on the status path"



def test_a_reply_beginning_with_a_bang_is_still_a_reply():
    """Its BODY is mail text, which may perfectly well start with "!". The
    branch is hoisted above the command region so that stays true -- and the
    hoisting is a source property, because the ordering is the whole design."""
    node = _func(BOT_SRC, "on_message")
    guards = _registered_command_guards()
    gate_a = [g for g in guards if g[1] and "reference" in g[0]][0]
    gate_b = [g for g in guards if g[1] and "reference" not in g[0]][0]
    order = [ast.unparse(n.test) for n in ast.walk(node) if isinstance(n, ast.If)]
    assert order.index(gate_a[0]) < order.index(gate_b[0]), (
        "the Reply branch must be evaluated before the generic DM region")
    # ...and running it, a reply whose text starts with "!" is mail.
    fn, posted, _asked, _ns = _mail_dm()
    msg = _Msg("!important \u2014 the bug is back",
               ref=_Ref(31, content=_dm_body(CODE_A)))
    assert _run(fn(msg)) == "HANDLED"
    assert posted[0]["body"].startswith("!important")



def test_the_queue_has_a_durable_retry_bound():
    """A DM nobody can deliver must be given up on, and the count has to
    survive a bot restart -- so it lives on the row, not in the process.

    What changed: nothing is charged at HAND-OUT any more. A row handed out
    and never attempted costs nothing, and the bot's report is what spends an
    attempt. That closes the case where an interrupted poll retired a DM
    nothing ever tried to send, without the credit-back statement that used
    to patch it afterwards."""
    ids = _identifiers(MAIN_SRC)
    for gone in ("_PENDING_DM_EXHAUST_SQL", "_PENDING_DM_UNCHARGE_SQL",
                 "_PENDING_DM_STAMP_SQL"):
        assert gone not in ids, "%s survived the redesign" % gone
    for need in ("_PENDING_DM_RETIRE_SQL", "_PENDING_DM_SETTLE_SQL"):
        assert need in ids, need
    assert main.PENDING_DM_MAX_ATTEMPTS >= 1
    # The claim charges on a RE-claim and not on a first hand-out, and the
    # distinction is the whole bound. Measured against PostgreSQL: a fresh
    # row comes back at attempts 0, and a row whose claim EXPIRED unsettled
    # comes back at 1.
    #
    # Both halves matter. Charging at every hand-out spent an attempt on a
    # row nothing ever tried to send, which is what retired DMs during an
    # interrupted poll. Charging at NO hand-out would let a bot that dies
    # mid-batch every time loop on the same row forever, because the
    # settlement that charges never arrives -- a hand-out nobody reported on
    # IS a failed attempt, and it is the only witness there will be.
    claim = " ".join(main._PENDING_DM_CLAIM_SQL.split())
    assert ("attempts = u.attempts + CASE WHEN u.claim_until IS NOT NULL "
            "THEN 1 ELSE 0 END") in claim, claim
    # An unconditional charge is the mutation this kills, so say so.
    assert "attempts = u.attempts + 1," not in claim, (
        "the claim charges every hand-out again; a row nobody tried is spent")
    # The settlement is what charges, and it charges what the caller says.
    settle = " ".join(main._PENDING_DM_SETTLE_SQL.split())
    # Typed bind, not bare interpolation (#275/#448) -- and a DELTA, never
    # an absolute write (#326), so two settlements cannot lose one another.
    assert "attempts = u.attempts + CAST(:charge AS INTEGER)" in settle, settle
    # ...and it only ever applies to the hand-out it names.
    assert "claim_id" in settle and "sclaim" in settle, settle
    # Retirement covers BOTH ways a row leaves: the attempt cap, and a claim
    # that was never settled. An expiring-by-default bound self-heals; a
    # blocking one needs a cleanup that always runs (#276/#430).
    retire = " ".join(main._PENDING_DM_RETIRE_SQL.split())
    assert ":cap" in retire and ":max_age" in retire, retire
    assert main.PENDING_DM_CLAIM_SECONDS < main.PENDING_DM_MAX_AGE_SECONDS, (
        "a claim outliving the retirement age would retire live rows")


def test_a_settlement_that_names_no_claim_is_dropped_rather_than_applied():
    """The ack builds (ids, claims) in matching order and drops any id it
    cannot pair. An id with no claim cannot be matched to a hand-out, and
    applying it to the row's CURRENT state is how a replayed report spent an
    attempt on a delivery that was still in flight.

    MUTATION: fall back to applying the id without its claim. Must fail."""
    node = _func(MAIN_SRC, "ack_pending_dms")
    body = ast.unparse(node)
    assert "claims.get(i)" in body, body[:400]
    # Both buckets go through the same pairing helper AT THE SAME CALL SITE
    # -- one definition, one call, inside a loop over the two buckets. Two
    # call sites would be two places for a looser path to the same statement
    # to appear (#432); the loop is what makes that impossible rather than
    # merely absent today.
    assert body.count("_settle_pairs") == 2, (
        "expected one definition and one call site, found %d references"
        % body.count("_settle_pairs"))
    loops = [ast.unparse(x) for x in ast.walk(node) if isinstance(x, ast.For)
             and "_settle_pairs" in ast.unparse(x)]
    assert len(loops) == 1, loops
    assert "retry_ids" in loops[0] and "not_attempted_ids" in loops[0], loops[0]
    # ...and the two charges are 1 and 0, in that order against those buckets.
    assert "(body.retry_ids, 1)" in loops[0].replace(" ", "") \
        or "body.retry_ids, 1" in loops[0], loops[0]
    assert "body.not_attempted_ids, 0" in loops[0], loops[0]



def test_an_operational_dm_is_not_queued_behind_a_relay_burst():
    """A burst of relay DMs must not delay a queue beacon or a match result.
    The two classes are WEIGHTED against each other rather than aged: at
    k = 1 an operational row advances one place per rank and a relay row
    advances four, so a full batch is split in that proportion.

    The split itself is measured against real PostgreSQL by the live test
    below; this pins the shape that produces it."""
    flat = " ".join(main._PENDING_DM_CLAIM_SQL.split())
    assert "rn * :k_op" in flat and "rn * :k_relay" in flat, flat
    assert main._PDM_K_OP == 1, main._PDM_K_OP
    assert main._PDM_K_RELAY == main.PENDING_DM_RELAY_WEIGHT - 1, (
        main._PDM_K_RELAY, main.PENDING_DM_RELAY_WEIGHT)
    # The weights are what the ratio is made of, so the arithmetic is stated
    # here too -- a silent change to either constant changes the split.
    share_op = main.PENDING_DM_BATCH * main._PDM_K_RELAY // (
        main._PDM_K_OP + main._PDM_K_RELAY)
    assert (share_op, main.PENDING_DM_BATCH - share_op) == (40, 10), (
        "the documented 40/10 split no longer follows from the constants")
    # The rows themselves are in
    # test_neither_dm_class_starves_or_overtakes_the_other.



def test_the_mail_group_offers_the_command_the_plan_specified():
    """The command still exists, still refuses to answer in public, and its
    description no longer promises the behaviour this change removed -- a
    description a player reads IS the contract (#351)."""
    node = _func(BOT_SRC, "cmd_mail_reply")
    deco = " ".join(ast.unparse(d) for d in node.decorator_list)
    assert "name='reply'" in deco.replace('"', "'"), deco
    for gone in ("most recently DMed", "most recent"):
        assert gone not in deco, deco
        assert gone not in (ast.get_docstring(node) or "")
    assert "thread code" in deco, "the describe string must say how to target"
    # ...and in a guild it posts nothing and says why.
    fn, ctx, posted, said, deferred = _slash_reply(guild=object())
    _run(fn(ctx, text="private business"))
    assert posted == [] and deferred == []
    assert said and "DM" in said[0].upper() or "private" in said[0].lower()


# ── Round 3: one test per finding ────────────────────────────────────────

REPLY_ID = "44444444-4444-4444-4444-444444444444"


def _reply_route(db, req, core=None):
    """Run the Discord reply route against a scripted db. Returns whatever
    it returns; raises its HTTPException unchanged."""
    seen = {}

    async def _core(_db, _me, **kw):
        seen.update(kw)
        return {"id": REPLY_ID, "accepted": True}

    os.environ["API_SECRET_KEY"] = "test-internal-key"
    prev = mail_discord._BOUND.get("reply_core")
    mail_discord._BOUND["reply_core"] = core or _core
    try:
        out = _run(mail_discord.mail_reply_from_discord(
            req, "test-internal-key", db))
    finally:
        mail_discord._BOUND["reply_core"] = prev
        os.environ.pop("API_SECRET_KEY", None)
    return out, seen



def test_the_reference_is_fetched_at_most_once():
    """The fallback fetch is a request against Discord on a path a player can
    repeat. One, and only when `resolved` did not already answer.

    MUTATION: drop the `resolved` check and always fetch. Must fail."""
    fn, _posted, _asked, _ns = _mail_dm()
    msg = _Msg("yes", ref=_Ref(31, content=_dm_body(CODE_A)))
    assert _run(fn(msg)) == "HANDLED"
    assert msg.fetched == [], "resolved was already in hand; the fetch was waste"



CODE_OK = "SCR-ABCDEFGHJKMN"


def _route_db(extra=None):
    """The reads the route makes, in order: the player, then the thread."""
    return _FakeDb([[PLAYER_ROW], [{"mail_id": MAIL}]] + list(extra or []))


def test_a_reply_with_nothing_to_key_on_is_refused_not_quietly_made_unsafe():
    """`reply_idempotency_key("")` mints a fresh uuid4 per call, so a retry
    of a request carrying neither a key nor a source writes a SECOND reply
    -- the exact defect the derivation exists to prevent."""
    req = mail_discord._ReplyFromDiscord(
        discord_id="d1", relay_code=CODE_OK, body="yes")
    with pytest.raises(HTTPException) as err:
        _reply_route(_route_db(), req)
    assert err.value.status_code == 400
    assert err.value.detail == "idempotency_source_required"
    # ...and the same request WITH a source is accepted, or this is just a
    # broken route.
    req2 = mail_discord._ReplyFromDiscord(
        discord_id="d1", relay_code=CODE_OK, body="yes", source_message_id="77")
    out, _seen = _reply_route(
        _route_db([[{"id": MAIL, "subject": "s", "sender_name": "n",
                     "relay_code": CODE_OK}]]), req2)
    assert out["accepted"] is True


def test_a_reply_that_names_no_thread_is_refused_rather_than_routed():
    """There is ONE path. No ladder, no fallback, no third branch -- every
    additional way of arriving at a target was another way of arriving at the
    wrong one.

    MUTATION: fall back to the most recent row when the code is empty. The
    target_required assertion must fail."""
    for bad in ("", "   ", "not-a-code", "SCR-UUUUUUUUUUUU", "SCR-TOOSHORT"):
        req = mail_discord._ReplyFromDiscord(
            discord_id="d1", relay_code=bad, body="yes", source_message_id="77")
        with pytest.raises(HTTPException) as err:
            _reply_route(_FakeDb([[PLAYER_ROW]]), req)
        assert err.value.detail == "target_required", bad


@pytest.mark.parametrize("rows,detail", [([], "unknown_code"),
                                         ([{"mail_id": MAIL}, {"mail_id": MAIL}],
                                          "unknown_code")])
def test_a_code_that_does_not_resolve_to_exactly_one_thread_is_refused(rows, detail):
    """Zero names no thread of this player's. Two is unreachable while the
    unique index exists, and is REFUSED rather than resolved so it stays
    unreachable instead of quietly becoming "pick one" (#177)."""
    req = mail_discord._ReplyFromDiscord(
        discord_id="d1", relay_code=CODE_OK, body="yes", source_message_id="77")
    with pytest.raises(HTTPException) as err:
        _reply_route(_FakeDb([[PLAYER_ROW], rows]), req)
    assert err.value.status_code == 404
    assert err.value.detail == detail



def test_the_confirmation_read_cannot_fail_a_reply_that_already_committed():
    """The read runs AFTER the reply committed. Letting a transient failure
    there become a 500 tells the player their reply did not send, and the
    retry that invites is a second mail."""
    class _BoomDb(_FakeDb):
        async def execute(self, stmt, params=None):
            self.sql.append(str(stmt))
            if len(self.sql) >= 3:
                raise RuntimeError("the read-back went away")
            return _FakeResult(self._results.pop(0) if self._results else [])

    req = mail_discord._ReplyFromDiscord(
        discord_id="d1", relay_code=CODE_OK, body="yes", source_message_id="77")
    out, _seen = _reply_route(_BoomDb([[PLAYER_ROW], [{"mail_id": MAIL}]]), req)
    assert out["accepted"] is True
    assert (out.get("replied_to") or {}).get("known") is False, (
        "it must say it does not know, not invent a thread")



def test_the_thread_the_confirmation_names_is_escaped_for_discord():
    """Subject and sender are player-authored and the bot interpolates them
    into markdown. Escaped, but still legible -- the same neutralisation the
    DM text uses, so no surface is the permissive one (#412)."""
    req = mail_discord._ReplyFromDiscord(
        discord_id="d1", relay_code=CODE_OK, body="yes", source_message_id="77")
    out, _seen = _reply_route(_route_db([[{
        "id": MAIL, "subject": "**bold** `code`", "sender_name": "_Bob_",
        "relay_code": CODE_OK}]]), req)
    info = out["replied_to"]
    assert info["known"] is True
    assert "bold" in info["subject"] and "Bob" in info["sender_name"]
    assert "**" not in info["subject"], info["subject"]
    # The code comes back so the confirmation can carry its own marker.
    assert info["relay_code"] == CODE_OK


def test_the_confirmation_does_not_invent_a_thread_it_could_not_read():
    """A confirmation reading `to them - (no subject)` states two facts
    the bot does not have, about a reply that did send."""
    line = _lift_bot("_mail_sent_line", {})
    assert line({"known": False, "subject": "", "sender_name": ""}) \
        == "\u2709\ufe0f Sent your reply."
    assert "(no subject)" not in line({"known": False})
    known = line({"known": True, "subject": "subj", "sender_name": "Bob"})
    assert "Bob" in known and "subj" in known


def test_a_private_reply_is_refused_in_public():
    """`!mail reply <private text>` in a bridged channel is relayed into
    in-game chat before dispatch, and answering there had the bot name the
    sender and subject to everyone reading."""
    fn, ctx, posted, said, _def = _slash_reply(
        guild=types.SimpleNamespace(id=1))
    _run(fn(ctx, text="something private"))
    assert posted == [], "a mail reply was sent from a public channel"
    assert said and "direct message" in said[0].lower(), said



def test_the_slash_reply_defers_before_the_request_and_names_no_thread_itself():
    """A slash interaction hard-fails at 3s while this request is allowed 8,
    so a slow api turned a reply that DID send into "the application did not
    respond" -- and the retry that invites carries a NEW interaction id, so
    it is a new key and a second mail.

    It also no longer guesses. Without a leading code it asks, exactly as the
    DM path does."""
    fn, ctx, posted, said, deferred = _slash_reply(threads=[_thread(CODE_A)])
    _run(fn(ctx, text="it is still broken"))
    assert deferred == [0], (
        "the defer must happen before any request, or it is not a defer")
    assert posted == [], "the slash path guessed a thread"
    assert "couldn\u2019t tell which mail" in said[0]
    assert CODE_A in said[0]


def test_the_slash_reply_uses_a_leading_code_when_the_player_gives_one():
    fn, ctx, posted, said, deferred = _slash_reply(data={"replied_to": {
        "known": True, "subject": "s", "sender_name": "Bob",
        "relay_code": CODE_A}})
    _run(fn(ctx, text="%s yes please" % CODE_A))
    assert deferred == [0]
    assert [p["relay_code"] for p in posted] == [CODE_A]
    assert posted[0]["body"] == "yes please"
    # The interaction id is the idempotency source when there is no message.
    assert posted[0]["source_message_id"] == "555"
    assert "Bob" in said[0]


def test_the_slash_reply_tells_an_unlinked_player_how_to_link():
    """In a DM this falls through to the ticket chain, but here the player
    asked for mail by name, so silence would be the wrong answer."""
    fn, ctx, posted, said, _d = _slash_reply(thread_status=404)
    _run(fn(ctx, text="hello"))
    assert posted == []
    assert "linked" in said[0] and "!link" in said[0]


def test_the_slash_reply_says_so_when_there_is_no_mail_at_all():
    fn, ctx, posted, said, _d = _slash_reply(threads=[])
    _run(fn(ctx, text="hello"))
    assert posted == []
    assert "No mail has been relayed to you" in said[0]



def _registered_command_guards():
    """Every use of `_is_registered_command` inside on_message, with the
    polarity it is used at. Parsed, not grepped: the comments around these
    guards discuss the predicate at length (#342/#441)."""
    node = _func(BOT_SRC, "on_message")
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.If):
            t = ast.unparse(n.test)
            if "_is_registered_command" not in t:
                continue
            negated = "not _is_registered_command" in t
            out.append((t, negated, ast.unparse(n.body[0])[:90]))
    return out



def test_one_definition_of_a_command_serves_every_gate_that_asks():
    """There were two answers to "is this text a command": this helper, which
    consults the bot's own command table, and a bare `startswith("!")` on the
    second DM gate. They disagreed -- "!important" is not a command, but the
    crude test withheld it from the whole chain anyway, after which dispatch
    found nothing and the message did nothing at all.

    A flag names a LINE; the defect is a CLASS (#432), so this asserts the
    COUNT and every polarity rather than the one line that was reported.

    SCOPE, stated rather than filtered silently (#342/#431): the prefix test
    in the chat-lockdown branch is deliberately NOT included. It answers a
    different question -- "may I delete this message in a locked channel" --
    about guild messages rather than DMs, and it errs toward leaving a
    message standing. Folding an unrelated moderation path into a mail change
    is how a behaviour change ends up somewhere nobody would look for it.

    MUTATION: put `message.content.startswith("!")` back on either DM gate.
    Must fail."""
    guards = _registered_command_guards()
    assert len(guards) == 3, [g[0] for g in guards]
    positive = [g for g in guards if not g[1]]
    negative = [g for g in guards if g[1]]
    assert len(positive) == 1 and len(negative) == 2, guards
    # The two DM gates ask the same question; the bridge asks the opposite
    # one. Opposite polarity is CORRECT and is pinned as such: the bridge
    # declines to relay a command, the DM gates decline to treat one as mail.
    assert "_relay_lang" in positive[0][0], positive[0][0]
    assert all("_handle_mail_dm" in g[2] or "_TICKET_DM_RE" in g[2]
               for g in negative), negative
    # ...and neither DM gate answers the question the crude way any more.
    for text_, _neg, _body in negative:
        assert "startswith" not in text_, text_
    dm_region = [n for n in ast.walk(_func(BOT_SRC, "on_message"))
                 if isinstance(n, ast.If) and "DMChannel" in ast.unparse(n.test)]
    for n in dm_region:
        assert 'startswith("!")' not in ast.unparse(n.test), ast.unparse(n.test)


def test_a_reply_that_only_looks_like_a_command_is_mail():
    """`!important` is not a command. Left inside a "!" guard it reached
    dispatch, matched nothing, and was lost -- so it must reach the mail
    path, which is what the helper's answer produces."""
    ns = {"bot": types.SimpleNamespace(
        command_prefix="!",
        get_command=lambda w: object() if w in ("link", "mail") else None)}
    fn = _lift_bot("_is_registered_command", ns)
    assert fn("!important") is False
    assert fn("!link ABC123") is True
    # Fails CLOSED: an unanswerable question must not mail `!link <code>` to
    # another player.
    ns2 = {"bot": types.SimpleNamespace(
        command_prefix="!",
        get_command=lambda w: (_ for _ in ()).throw(RuntimeError("boom")))}
    assert _lift_bot("_is_registered_command", ns2)("!link ABC123") is True
    # No lstrip and no lowercasing: this has to agree with the parser that
    # will actually run, and discord.py leaves both at their False defaults.
    assert fn("  !link x") is False
    assert fn("!LINK x") is False


def test_a_batch_cut_short_acks_what_it_sent_and_credits_what_it_never_tried():
    """A row is charged when it is handed out, so a batch the bot never
    finishes charges rows it never tried -- ten of those retire an
    operational DM nothing ever attempted. The bot reports them and they
    are credited back. This is the state the credit-back exists for and
    the only one that produces it, so a poll whose loop escapes past the
    ack block has the fix and none of its effect."""
    rows = [_queue_row("r1", mail_id=MAIL),
            _queue_row("g1", did="4243", content="answered"),
            _queue_row("g2", did="4244", content="answered too")]
    fn, _ns, sent, acks, out = _drain(rows, boom_after=1)
    _run(fn())
    assert len(sent) == 1, sent
    assert [ln for ln in out if "cut short" in ln], out
    # The row it DID send is acked -- losing that ack is a second DM.
    live = [a for a in acks if a["ids"] == ["r1"]]
    assert live and live[0]["und"] is False, acks
    # ...and the two it never reached are credited back, by id.
    credited = [a for a in acks if a["unreached"]]
    assert credited, "nothing was credited back, so the charge stands"
    assert sorted(credited[0]["unreached"]) == ["g1", "g2"], credited
    assert credited[0]["ids"] == [], (
        "the credit-back also acked rows, marking them delivered")
    # A batch that finishes credits nothing: every row was attempted.
    fn2, _ns2, sent2, acks2, _o2 = _drain(rows)
    _run(fn2())
    assert len(sent2) == 3 and not [a for a in acks2 if a["unreached"]], acks2



def test_the_unacked_set_does_not_grow_once_a_row_is_retired():
    """An id the server has stopped handing back hit the cap, or another
    path acked it. Nothing will mention it again, so keeping it grows the
    set until restart."""
    seen, unacked = {}, set()
    fn, _ns, _s, _a, _o = _drain(
        [_queue_row("r1", mail_id=MAIL)], ack_ok=False,
        seen=seen, unacked=unacked)
    _run(fn())
    assert unacked == {"r1"}, unacked
    # The server retires r1 (cap) and hands back something else.
    fn2, _ns2, _s2, _a2, _o2 = _drain(
        [_queue_row("g9", did="4243", content="answered")],
        seen=seen, unacked=unacked)
    _run(fn2())
    assert unacked == set(), (
        "a row the server has stopped mentioning is still held: %s" % unacked)


# ── Live: the whole path, against the real migration ─────────────────────

def _live(coro_factory):
    import asyncio
    return asyncio.get_event_loop_policy().new_event_loop() \
        .run_until_complete(coro_factory())



@needs_pg
def test_the_migration_applies_to_a_pre_330_database_and_is_rerunnable():
    """The migration's header claims it is idempotent and re-runnable.
    `_seed` applies it twice on every live test, and this one checks what it
    actually produced -- columns, CHECKs, defaults and indexes -- against a
    database that started without any of them."""
    import asyncpg

    async def run():
        conn = await asyncpg.connect(DSN)
        try:
            await _seed(conn)                       # applies 330 twice
            cols = {(r["table_name"], r["column_name"]): r for r in await conn.fetch(
                "SELECT table_name, column_name, data_type, column_default, is_nullable"
                "  FROM information_schema.columns"
                " WHERE table_name IN ('players','mail_messages','pending_dms')")}
            checks = sorted(r["conname"] for r in await conn.fetch(
                "SELECT conname FROM pg_constraint WHERE conname LIKE 'ck_%'"
                "   AND conrelid::regclass::text IN ('mail_messages','pending_dms')"))
            idx = {r["indexname"]: r["indexdef"] for r in await conn.fetch(
                "SELECT indexname, indexdef FROM pg_indexes"
                " WHERE tablename = 'pending_dms'")}
            return cols, checks, idx
        finally:
            await conn.close()

    cols, checks, idx = _live(run)
    # The flag defaults ON for EVERY row, linked or not -- the decision
    # recorded in the migration, and the one the client mirrors.
    flag = cols[("players", "mail_discord_relay")]
    assert flag["is_nullable"] == "NO" and "true" in (flag["column_default"] or "")
    via = cols[("mail_messages", "via")]
    assert via["is_nullable"] == "NO" and "game" in (via["column_default"] or "")
    att = cols[("pending_dms", "attempts")]
    assert att["is_nullable"] == "NO" and "0" in (att["column_default"] or "")
    assert cols[("pending_dms", "mail_id")]["data_type"] == "uuid"
    # The thread code, and the claim it is handed out under.
    assert cols[("pending_dms", "relay_code")]["data_type"] == "text"
    assert cols[("pending_dms", "claim_id")]["data_type"] == "uuid"
    assert "time zone" in cols[("pending_dms", "claim_until")]["data_type"]
    assert "time zone" in cols[("pending_dms", "cancelled_at")]["data_type"]
    # The mechanisms this migration REMOVES must be gone from the table, not
    # merely unused by the code.
    for gone in ("dm_message_id",):
        assert ("pending_dms", gone) not in cols, (
            "%s survived the migration" % gone)
    assert checks == ["ck_mail_messages_via", "ck_pending_dms_attempts_nonneg",
                      "ck_pending_dms_claim_paired", "ck_pending_dms_relay_code"], (
        "the CHECKs did not survive a re-run: %s" % checks)
    # All six indexes, by name -- and the one that carries the whole
    # uniqueness argument is checked by its DEFINITION, because a
    # same-named non-unique index would pass a name check and let two rows
    # of one player share a code.
    for want in ("idx_pending_dms_mail", "idx_pending_dms_relay_code",
                 "idx_pending_dms_relay_recent", "idx_pending_dms_drain_op",
                 "idx_pending_dms_drain_relay", "idx_pending_dms_retire"):
        assert want in idx, "%s is missing (have %s)" % (want, sorted(idx))
    for gone in ("idx_pending_dms_dm_message", "idx_pending_dms_recent"):
        assert gone not in idx, "%s survived the migration" % gone
    code_idx = idx["idx_pending_dms_relay_code"]
    assert "UNIQUE" in code_idx.upper(), code_idx
    assert "relay_code" in code_idx and "steam_id" in code_idx, code_idx


@needs_pg
def test_a_relayed_mail_survives_the_whole_queue_and_comes_back_answerable():
    """The one test that is not about shape. Send -> fan-out -> the poll the
    bot really runs -> the ack and stamp the bot really posts -> the lookup
    a Reply really resolves through. Every statement is the module's own;
    none is retyped here."""
    import asyncpg

    async def run():
        conn = await asyncpg.connect(DSN)
        try:
            await _seed(conn)
            await conn.execute(_asyncpg_sql(), "the DM body", MAIL, _code())

            # 1. The poll hands the bot exactly one row, and it knows the row
            #    is a mail relay because mail_id is set.
            polled = await _claim(conn)
            if len(polled) != 1:
                return ("poll", len(polled), None, None, None)
            row = polled[0]
            dm_id = str(row["dm_id"])

            # 2. The bot DMs it and acks. Nothing is stamped: the code was
            #    already on the row before the DM existed.
            # NOT from the claim: the bot never needs the code as a field,
            # because it is already inside the `content` it is about to send.
            # Reading it from the row here is the test standing in for the
            # player, who reads it off the DM.
            code = await conn.fetchval(
                "SELECT relay_code FROM pending_dms WHERE id::text = $1", dm_id)
            assert mail_discord.RELAY_CODE_ANY_RE.fullmatch(code or ""), code
            await conn.execute(_pg(main._PENDING_DM_ACK_SQL, "und", "ids"),
                               False, [dm_id])

            # 3. The player replies quoting that code, and it resolves.
            pid = await conn.fetchval(
                "SELECT id::text FROM players WHERE steam_id = '1'")
            pid2 = await conn.fetchval(
                "SELECT id::text FROM players WHERE steam_id = '2'")
            hit = await conn.fetchrow(
                _pg(mail_discord._REPLY_BY_CODE_SQL, "c", "s", "pid"),
                code, "1", pid)
            # ...and only for the player it was sent to. Same code, another
            # player: the envelope join is what refuses it.
            other = await conn.fetchrow(
                _pg(mail_discord._REPLY_BY_CODE_SQL, "c", "s", "pid"),
                code, "2", pid2)

            # 4. The row is drained: a second poll returns nothing.
            again = await _claim(conn)
            return (row["discord_id"], str(row["mail_id"]), int(row["attempts"]),
                    (hit and str(hit["mail_id"]), other), len(again))
        finally:
            await conn.close()

    did, mail_id, attempts, resolved, again = _live(run)
    assert did == "d1", did
    assert mail_id == MAIL
    # ZERO, and the old assertion here said 1. Charging at hand-out is what
    # made an interrupted poll retire a DM nothing ever tried to send, and
    # the credit-back statement that patched it afterwards was reachable only
    # through a handler that did not always run. Nothing is spent until
    # something is actually attempted -- either the bot reports a failure, or
    # its claim expires unsettled and the next claim charges for it.
    assert attempts == 0, (
        "the claim charged an attempt at hand-out again, so a row nobody "
        "tried is spent: %s" % attempts)
    assert resolved[0] == MAIL, "the Reply did not resolve back to its mail"
    assert resolved[1] is None, \
        "another player's steam_id resolved someone else's DM"
    assert again == 0, "the acked row came back on the next poll"


@needs_pg
def test_a_row_nothing_can_classify_is_given_up_on_at_the_cap():
    """A failure the bot cannot name is left queued on purpose. Unbounded,
    it is refetched every 60s forever while holding a slot in the drain
    window -- so the api counts the attempts the bot reports and, at the
    cap, gives the row up itself."""
    import asyncpg

    async def run():
        conn = await asyncpg.connect(DSN)
        try:
            await _seed(conn)
            await conn.execute(_asyncpg_sql(), "the DM body", MAIL, _code())
            dm_id = str((await conn.fetchrow(
                "SELECT id FROM pending_dms LIMIT 1"))["id"])
            seen = []
            for _ in range(main.PENDING_DM_MAX_ATTEMPTS + 3):
                # Exactly what the poll route does, in its order: retire
                # anything past the bound, then claim a batch. The bot never
                # reports anything in this scenario -- that IS the scenario --
                # so each claim expires unsettled, which is what the next
                # claim charges for.
                await conn.execute(
                    _pg(main._PENDING_DM_RETIRE_SQL, "cap", "max_age"),
                    main.PENDING_DM_MAX_ATTEMPTS,
                    main.PENDING_DM_MAX_AGE_SECONDS)
                handed = await _claim(conn)
                seen.append(len(handed))
                # The bot died holding it. Nothing settles, and the claim
                # runs out -- which is the only evidence this row will ever
                # produce, and is therefore what has to count.
                await conn.execute(
                    "UPDATE pending_dms SET claim_until = NOW()"
                    " - interval '1 second' WHERE claim_until IS NOT NULL")
            row = await conn.fetchrow(
                "SELECT attempts, undeliverable, delivered_at IS NOT NULL AS done"
                "  FROM pending_dms WHERE id::text = $1", dm_id)
            return seen, dict(row)
        finally:
            await conn.close()

    seen, row = _live(run)
    cap = main.PENDING_DM_MAX_ATTEMPTS
    # cap + 1 hand-outs: the FIRST is free, because at that point nothing has
    # been attempted and a row nobody tried must not be spent. Each of the
    # next `cap` re-claims an expired, unsettled claim, and that is what is
    # charged. Then it is retired and never handed out again.
    assert seen[:cap + 1] == [1] * (cap + 1), (
        "the row was abandoned before the cap: %s" % seen)
    assert set(seen[cap + 1:]) == {0}, (
        "the row is still being handed out past the cap: %s" % seen)
    assert row["undeliverable"] is True and row["done"] is True
    assert row["attempts"] == cap, row["attempts"]
    # ...and the ROUTE runs those statements. Driving the constants proves
    # they work; it says nothing about whether anything calls them, and a
    # route whose call was replaced by a no-op left this test green.
    poll = _identifiers(
        ast.get_source_segment(MAIN_SRC, _func(MAIN_SRC, "internal_pending_dms")) or "")
    for name in ("_PENDING_DM_CLAIM_SQL", "_PENDING_DM_RETIRE_SQL"):
        assert name in poll, "the poll route never executes %s" % name


@needs_pg
def test_neither_dm_class_starves_or_overtakes_the_other():
    """The weighted fair queue, against rows. One-way aging failed in BOTH
    directions and each half here is the one the other version passed: a
    fresh relay row behind a standing operational queue was never picked
    at all, and a ticket answer queued a second ago sat behind a bulk
    grant's aged notifications. A fixed share per class is symmetric, so
    neither state exists."""
    import asyncpg

    async def run():
        conn = await asyncpg.connect(DSN)
        try:
            await _seed(conn)
            # 1. A queue that never empties of operational rows, and one
            #    relay row queued just now -- the state where aging had
            #    not yet let it in, so it was never picked.
            for i in range(60):
                await conn.execute(
                    "INSERT INTO pending_dms (steam_id, content, created_at)"
                    " VALUES ('1', $1, now() - interval '10 minutes')",
                    "operational %d" % i)
            await conn.execute(_asyncpg_sql(), "relay body", MAIL, _code())
            held = [r["content"] for r in await _claim(conn)]
            await conn.execute("DELETE FROM pending_dms")
            # 2. The inversion: a bulk grant, every row of it past any age
            #    threshold, with one ticket answer queued LAST.
            for i in range(200):
                await conn.execute(
                    "INSERT INTO pending_dms (steam_id, content, mail_id,"
                    " relay_code, created_at)"
                    " VALUES ('1', $1, $2, $3, now() - interval '10 minutes')",
                    "relay %d" % i, MAIL, _code())
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content)"
                " VALUES ('1', 'your bug report was answered')")
            inverted = [r["content"] for r in await _claim(conn)]
            await conn.execute("DELETE FROM pending_dms")
            # 3. BOTH deeper than one batch. Only here is the share
            #    visible: with one class short, whichever weights are in
            #    force the other simply fills the batch, and equal
            #    weights look identical to the intended 4:1.
            for i in range(200):
                await conn.execute(
                    "INSERT INTO pending_dms (steam_id, content) VALUES ('1', $1)",
                    "operational %d" % i)
                await conn.execute(
                    "INSERT INTO pending_dms (steam_id, content, mail_id,"
                    " relay_code) VALUES ('1', $1, $2, $3)",
                    "relay %d" % i, MAIL, _code())
            both = [r["content"] for r in await _claim(conn)]
            return held, inverted, both
        finally:
            await conn.close()

    held, inverted, both = _live(run)
    assert len(held) == main.PENDING_DM_BATCH, len(held)
    assert "relay body" in held, (
        "a relay row is held out by a queue of operational rows that never "
        "empties, however long it waits: %s" % held[:3])
    ops = sum(1 for c in held if c.startswith("operational"))
    assert ops >= 40, (
        "the relay class took %d of %d slots; an operational DM is a "
        "player waiting on an answer" % (len(held) - ops, len(held)))
    assert len(inverted) == main.PENDING_DM_BATCH, len(inverted)
    assert "your bug report was answered" in inverted, (
        "a ticket answer queued a second ago is not in the batch at all, "
        "behind a bulk grant's notifications: %s" % inverted[:3])
    assert inverted[0] == "your bug report was answered", (
        "...and it is not first out of the batch either: %s" % inverted[:3])
    assert sum(1 for c in inverted if c.startswith("relay")) >= 40, (
        "the relay class got no share of a batch it otherwise fills")
    # The share itself. Weight 5 puts the Nth relay row at 5N and the Nth
    # operational row at N, so a full batch with both queues deep is
    # about 42 operational and 8 relay. Equal weights give 25/25, which
    # every assertion above still passes -- a player waiting on a ticket
    # answer would be behind twice as many notifications as intended.
    ops_both = sum(1 for c in both if c.startswith("operational"))
    assert len(both) == main.PENDING_DM_BATCH, len(both)
    assert ops_both >= 38, (
        "operational rows took %d of %d slots; weight %d reserves about "
        "%d" % (ops_both, len(both), main.PENDING_DM_RELAY_WEIGHT,
                len(both) - len(both) // main.PENDING_DM_RELAY_WEIGHT))
    assert len(both) - ops_both >= 5, (
        "the relay class took %d slots of %d; with weight %d it is "
        "entitled to about %d"
        % (len(both) - ops_both, len(both), main.PENDING_DM_RELAY_WEIGHT,
           len(both) // main.PENDING_DM_RELAY_WEIGHT))


@needs_pg
def test_an_operational_dm_jumps_a_queue_full_of_relay_notifications():
    """The ordering change, against rows rather than against the SQL text: a
    ticket reply queued LAST still drains first, because a player waiting on
    an answer must not sit behind a bulk mail's notifications."""
    import asyncpg

    async def run():
        conn = await asyncpg.connect(DSN)
        try:
            await _seed(conn)
            await conn.execute(_asyncpg_sql(), "relay body", MAIL, _code())
            # A generic (operational) row, queued a minute LATER.
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content, created_at)"
                " VALUES ('1', 'your bug report was answered', now() + interval '1 minute')")
            return [(r["content"], r["mail_id"] is not None)
                    for r in await _claim(conn)]
        finally:
            await conn.close()

    order = _live(run)
    assert [c for c, _ in order] == ["your bug report was answered", "relay body"], order
    assert [is_mail for _, is_mail in order] == [False, True]


@needs_pg
def test_deleting_a_mail_cancels_the_dm_that_has_not_gone_out_yet():
    """A relay DM already queued is a copy of the mail, held outside the
    envelope tables where the reader's deleted_at cannot reach it: the
    player deletes the mail in game and the bot DMs them the full text
    afterwards, with a footer whose Reply then resolves to not_found.

    NOT the FK cascade -- that fires when the mail ROW is removed, and
    this route soft-deletes, so the cascade never runs on this path. Three
    predicates and one row of each kind they exclude."""
    import asyncpg

    async def run():
        conn = await asyncpg.connect(DSN)
        try:
            await _seed(conn)
            # theirs, queued -- the one that must go
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content, mail_id,"
                " relay_code) VALUES ('1', 'queued relay', $1, $2)",
                MAIL, _code())
            # theirs, already DMed: it is out, and its row is the mapping
            # a Reply to that DM resolves through
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content, mail_id,"
                " relay_code, delivered_at)"
                " VALUES ('1', 'sent relay', $1, $2, now())", MAIL, _code())
            # someone else's copy of the same mail -- their mail, not this
            # player's to cancel
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content, mail_id,"
                " relay_code) VALUES ('2', 'other player relay', $1, $2)",
                MAIL, _code())
            # this player's operational DM -- nothing to do with any mail
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content)"
                " VALUES ('1', 'your bug report was answered')")
            await conn.execute(
                _pg(main._MAIL_CANCEL_PENDING_DM_SQL, "mid", "sid"),
                MAIL, "1")
            # CANCELLED, not deleted: the row is what makes the code in an
            # already-sent DM resolve, so it has to survive. What changes is
            # whether the drain will still pick it up.
            return sorted(
                "%s%s" % (r["content"], "" if r["cancelled_at"] is None else " [cancelled]")
                for r in await conn.fetch(
                    "SELECT content, cancelled_at FROM pending_dms"))
        finally:
            await conn.close()

    left = _live(run)
    # The row SURVIVES and is marked cancelled. Deleting it would take the
    # thread code with it, and the DM already in the player's client quotes
    # that code -- so a reply to a mail they deleted would stop resolving at
    # all, instead of being told the mail is gone.
    assert "queued relay [cancelled]" in left, (
        "the queued copy of a deleted mail was not withdrawn: %s" % left)
    assert "queued relay" not in left, (
        "the queued copy is still live and will be DMed in full: %s" % left)
    assert left == ["other player relay", "queued relay [cancelled]",
                    "sent relay", "your bug report was answered"], (
        "the cancellation reached rows that are not this player's queued "
        "copy of this mail: %s" % left)
    # Said positively, because three of those four are the negative controls:
    # another player's copy of the same mail, this player's already-SENT
    # copy, and an operational DM that has nothing to do with any mail.
    assert sum(1 for x in left if "[cancelled]" in x) == 1, left



@needs_pg
def test_turning_the_relay_off_withdraws_only_this_players_queued_mail():
    """The relay-off withdrawal, executed rather than read.

    Its predicate was asserted only as TEXT -- four clauses looked for in
    the statement string -- against a scripted database that re-implements
    the predicate in Python instead of running it. A statement can carry all
    four clauses and still match the wrong rows, and a fake that models the
    rule agrees with whatever the rule is said to be (#313/#340).

    Five rows: one of each kind the predicate has to separate, plus one that
    is out with the bot at the moment the player flips the switch."""
    import asyncpg

    async def run():
        conn = await asyncpg.connect(DSN)
        try:
            await _seed(conn)
            # theirs, queued -- the one that must go
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content, mail_id,"
                " relay_code) VALUES ('1', 'queued relay', $1, $2)",
                MAIL, _code())
            # theirs, already DMed: it is out, and its row is what makes the
            # thread code printed in that DM resolve. Withdrawing it would
            # turn a reply into one that names nothing at all.
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content, mail_id,"
                " relay_code, delivered_at)"
                " VALUES ('1', 'sent relay', $1, $2, now())", MAIL, _code())
            # theirs, operational -- not a mail, so not this preference's
            # business. Silencing MAIL must not silence the answer to their
            # own bug report.
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content)"
                " VALUES ('1', 'your bug report was answered')")
            # someone else's queued copy of the same mail
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content, mail_id,"
                " relay_code) VALUES ('2', 'other player relay', $1, $2)",
                MAIL, _code())
            # theirs, queued AND claimed: handed to the bot seconds ago and
            # not yet settled. Withdrawn like any other queued row, and the
            # claim cleared with it -- the settlement quotes the claim, so a
            # bot that sends this one anyway settles nothing.
            await conn.execute(
                "INSERT INTO pending_dms (steam_id, content, mail_id,"
                " relay_code, claim_id, claim_until)"
                " VALUES ('1', 'in flight relay', $1, $2,"
                "         gen_random_uuid(), now() + interval '60 seconds')",
                MAIL, _code())
            tag = await conn.execute(
                _pg(mail_discord.RELAY_OFF_CANCEL_SQL, "sid"), "1")
            rows = await conn.fetch(
                "SELECT content, cancelled_at, claim_id FROM pending_dms")
            return tag, {r["content"]: (r["cancelled_at"] is not None,
                                        r["claim_id"] is not None)
                         for r in rows}
        finally:
            await conn.close()

    tag, state = _live(run)
    # Reported positively: a predicate matching nothing would satisfy every
    # "was not withdrawn" assertion below on its own.
    assert tag == "UPDATE 2", (
        "the withdrawal matched %r rows, not the two queued ones: %s"
        % (tag, state))
    assert state["queued relay"][0], (
        "the backlog was not withdrawn: %s" % (state,))
    assert state["in flight relay"][0], (
        "a row already handed to the bot was left live: %s" % (state,))
    assert not state["sent relay"][0], (
        "a DM already sent was withdrawn; the code it printed no longer "
        "resolves: %s" % (state,))
    assert not state["your bug report was answered"][0], (
        "a MAIL relay preference withdrew an operational DM: %s" % (state,))
    assert not state["other player relay"][0], (
        "the withdrawal reached another player's queue: %s" % (state,))
    # The rows SURVIVE -- cancelled, not deleted, for the same reason the
    # delete path cancels: the row is the thread identity.
    assert len(state) == 5, state
    # ...and the claim goes with the withdrawal, so the sweep does not have
    # to wait out a lease on a row nobody will ever send.
    assert not state["in flight relay"][1], (
        "a withdrawn row kept its claim: %s" % (state,))


def test_the_delete_route_cancels_only_for_the_player_who_deleted():
    """Deleting a mail withdraws the DM that has not gone out yet -- and
    CANCELS it rather than deleting the row, because the row is what makes
    the code in an already-sent DM resolve."""
    src_ = ast.get_source_segment(MAIN_SRC, _func(MAIN_SRC, "mail_delete")) or ""
    assert "_MAIL_CANCEL_PENDING_DM_SQL" in _identifiers(src_), (
        "the delete route never withdraws the queued DM")
    assert "_MAIL_DELETE_PENDING_DM_SQL" not in _identifiers(src_), (
        "the old hard-delete statement is back; an already-sent DM's code "
        "would stop resolving")
    # Scoped to the deleting player: the statement binds their steam id, so
    # one recipient deleting a mail cannot withdraw another's copy.
    flat = " ".join(main._MAIL_CANCEL_PENDING_DM_SQL.split())
    assert ":sid" in flat and "cancelled_at" in flat, flat
    assert "DELETE" not in flat.upper(), flat


# ── Tests deleted with the mechanisms they pinned ──────────────────────────
#
# Recorded rather than quietly dropped (#327/#393). Each was a real test of a
# real property; the property survived and the mechanism did not, so the test
# was rewritten against the new one rather than kept passing against a shape
# nothing has any more.
#
#   test_a_reference_nobody_can_resolve_still_answers_when_a_fallback_was_offered
#       gone: there is no fallback to offer
#       now:  an unreadable reference asks instead of guessing
#   test_a_reply_names_the_mail_while_the_bot_still_knows_it
#       gone: the process map it reads is deleted
#       now:  a reply names its thread from the DM text
#   test_a_reply_to_a_dm_from_before_the_restart_asks_only_about_ours
#       gone: `_is_our_relay_dm` is deleted
#       now:  a restart changes nothing: the code is in the message
#   test_a_second_copy_of_a_dm_does_not_orphan_the_first
#       gone: there is no stamp to orphan
#       now:  the unique index on (relay_code, steam_id)
#   test_the_ack_stamp_cannot_mark_a_generic_queue_row_answerable
#       gone: the ack no longer stamps anything
#       now:  the marker is written in the mail's own transaction
#   test_the_confirmation_names_the_mail_the_reply_actually_answered
#       gone: `inferred` is gone from the response
#       now:  the confirmation carries the thread's own code
#   test_the_drain_remembers_the_mail_behind_every_dm_it_sends
#       gone: the drain remembers nothing now
#       now:  the code is in the message it sent
#   test_the_inferred_reply_target_is_one_the_player_saw
#       gone: nothing is inferred
#       now:  the pick-a-thread listing
#   test_the_inferred_target_is_a_mail_the_player_saw_and_can_still_answer
#       gone: nothing is inferred
#       now:  the live round-trip test
#   test_the_mail_id_the_bot_already_knows_is_not_thrown_away
#       gone: the bot never knows a mail id
#       now:  relay_code is the only target
#   test_the_relay_map_evicts_the_oldest_and_never_the_newest
#       gone: the map is deleted
#       now:  nothing is held across the send
#   test_two_rows_stamped_with_one_message_id_resolve_to_neither
#       gone: message ids are not a key any more
#       now:  one code resolves one row, by unique index
