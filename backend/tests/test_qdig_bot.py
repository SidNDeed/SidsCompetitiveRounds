"""QDIG-1: the #scr-admin digest in plain words, EXECUTED.

The bot's digest functions are lifted out of discord_bot.py's AST and run
against fakes (the harness of test_quarantine_digest_bot.py: its clock,
channel and bot). The feed's rows are built by the api's own functions
(main._qdig_classify, main._qdig_feed_keys) from qdig_fixtures, the six live
rows of 16 Nov 2026 with invented names, so the texts pinned here are the
texts the two halves produce together.

The old bot is the digest section of discord_bot.py at 85a7d0b0, frozen in
qdig_base_bot_digest.txt (its hash is pinned): it is replayed against the new
feed's answer, the minutes between the api's deploy and the bot's.
"""

import ast
import asyncio
import copy
import hashlib
import os
import types
from datetime import datetime, timedelta, timezone

import main
import qdig_fixtures as fx
import test_quarantine_digest_bot as qb

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIGEST = os.path.join(HERE, "qdig_base_bot_digest.txt")
BASE_DIGEST_SHA256 = "c89161eab92eebf520d5931ea4f93dd58e3be0d365a1bd6e45c6eac2cf4a377a"
POSTED_URL = "http://api:8000/api/v1/internal/quarantine/digest/posted"


def run(coro):
    return asyncio.run(coro)


# ── the feed's rows, built by the api's own functions ──────────────────────

def feed_row(r, f, gate=(40, 6)):
    v = main._qdig_classify(r, f)
    out = {"id": str(r["id"]), "mode": r["mode"], "group": str(r["group_id"]) if r.get("group_id") else None,
           "family": main._triage_family(r["mode"], r["reason"], v["match"] is not None),
           "created_at": r["created_at"].isoformat()}
    out.update(main._qdig_feed_keys(r, v, f, gate))
    return out


def live_feed():
    f = fx.facts("A", "B", "C2", "C3")
    return [feed_row(r, f) for r in fx.live_rows()]


class _Resp:
    def __init__(self, status, body):
        self.status, self.body = status, body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self.body


class FakeFeed:
    """D1 in the QDIG-1 form over a list of feed rows (one page), and the
    posted route over the same rows. `form` None answers today's form."""

    def __init__(self, rows, form=1, reminder_due=False, post_status=200):
        self.rows, self.form, self.reminder_due = rows, form, reminder_due
        self.post_status = list(post_status) if isinstance(post_status, (list, tuple)) else [post_status]
        self.posts, self.gets = [], 0

    def get(self, url, params=None, headers=None, timeout=None):
        assert url == qb.URL and headers == {"X-Internal-Key": qb.KEY}
        self.gets += 1
        rows = [dict(r) for r in self.rows]
        needs = [r for r in rows if r.get("class") == "needs_decision"]
        body = {"hw": "2026-11-16T12:00:00+00:00", "page_size": 500, "rows": rows,
                "totals": {"pending": len(rows), "by_mode": {}, "groups": 1, "quota": 50, "at_quota": [],
                           "oldest": None}}
        if self.form is not None:
            body["qdig"] = self.form
            body["totals"].update({"needs_decision_games": len({r["game_key"] for r in needs}),
                                   "needs_decision_oldest": min((r["played_at"] for r in needs), default=None),
                                   "reminder_due": self.reminder_due})
        return _Resp(200, body)

    def post(self, url, json=None, headers=None, timeout=None):
        assert url == POSTED_URL and headers == {"X-Internal-Key": qb.KEY}
        status = self.post_status.pop(0) if len(self.post_status) > 1 else self.post_status[0]
        self.posts.append((json["kind"], list(json["ids"]), status))
        if status == 200 and json["kind"] == "new":
            for r in self.rows:
                if r["id"] in json["ids"]:
                    r["posted"] = True
        return _Resp(status, {})


def _fake_tasks():
    return types.SimpleNamespace(loop=lambda **kw: (lambda fn: fn))


def _namespace(clock, feed, channel, source_tree, names):
    out = []

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            v = qb.BASE + timedelta(seconds=clock.t)
            return v if tz is None else v.astimezone(tz)

    async def sleep(s):
        clock.advance(s)
    ns = {"discord": qb.FAKE_DISCORD, "aiohttp": qb.FAKE_AIOHTTP, "bot": qb.FakeBot(channel),
          "http_session": feed, "API_SECRET_KEY": qb.KEY, "API_BASE_URL": "http://api:8000",
          "ADMIN_CHANNEL_ID": qb.ADMIN_CHANNEL, "time": types.SimpleNamespace(monotonic=lambda: clock.t),
          "asyncio": types.SimpleNamespace(sleep=sleep), "datetime": FakeDatetime, "timezone": timezone,
          "timedelta": timedelta, "tasks": _fake_tasks(),
          "print": lambda *a, **k: out.append(" ".join(str(x) for x in a))}
    body = []
    for node in source_tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and names(t.id) for t in node.targets):
            body.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and names(node.name):
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            body.append(fn)
    exec(compile(ast.Module(body=body, type_ignores=[]), "digest", "exec"), ns)
    ns["_out"] = out
    return ns


def new_bot(feed, channel=None, clock=None):
    clock = clock or qb.Clock(1000.0)
    channel = channel or qb.FakeChannel(clock)
    ns = _namespace(clock, feed, channel, qb.TREE,
                    lambda n: n.startswith(("_qdigest", "_qdig", "QDIGEST_", "QDIG_"))
                    or n == "poll_quarantine_digest")
    return ns, channel, clock


def old_bot(feed, channel=None, clock=None):
    raw = open(BASE_DIGEST, "rb").read().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == BASE_DIGEST_SHA256, "the frozen base digest changed"
    clock = clock or qb.Clock(1000.0)
    channel = channel or qb.FakeChannel(clock)
    ns = _namespace(clock, feed, channel, ast.parse(raw.decode("utf-8")), lambda n: True)
    return ns, channel, clock


def texts(channel):
    return [c for _, c in channel.accepted]


# ── the six live rows ──────────────────────────────────────────────────────

C2_UNIX = int(fx.GAMES["C2"]["at"].timestamp())
C3_UNIX = int(fx.GAMES["C3"]["at"].timestamp())

GOLDEN = (
    "Held game reports: results a player's game sent that the server did not record as sent. "
    "2 games need a decision.\n"
    "\n"
    f"**FFA, 6 players, ranked** - game 2 of its lobby - played <t:{C2_UNIX}:f>\n"
    "Why held: The lobby had already been closed when this report arrived, so the game was never recorded.\n"
    "Numbers (rounds, points, kills), winner first:\n"
    "- Dune: 5, 11, 31 (winner)\n"
    "- Elm: 2, 5, 20\n"
    "- Ash: 0, 2, 8\n"
    "- Birch: 0, 2, 7\n"
    "- Cedar: 0, 2, 13\n"
    "- Fern: 0, 0, 10\n"
    "Reported by Ash. 1 report.\n"
    "What you can do: in the Admin tab, Rejected Reports. Accept only marks the report as approved for a "
    "later ordered replay; it records nothing now. Discard marks it as dismissed. Accept is blocked: "
    "6 players have played rated games since; adding this game now would need a full replay.\n"
    "[c2c2c2c2]\n"
    "\n"
    f"**FFA, 6 players, ranked** - game 3 of its lobby - played <t:{C3_UNIX}:f>\n"
    "Why held: The lobby had already been closed when this report arrived, so the game was never recorded.\n"
    "Numbers (rounds, points, kills), winner first:\n"
    "- Dune: 5, 11, 34 (winner)\n"
    "- Cedar: 1, 4, 10\n"
    "- Ash: 1, 2, 12\n"
    "- Elm: 0, 4, 10\n"
    "- Birch: 0, 3, 20\n"
    "- Fern: 0, 0, 3\n"
    "Reported by Ash. 1 report.\n"
    "What you can do: in the Admin tab, Rejected Reports. Accept only marks the report as approved for a "
    "later ordered replay; it records nothing now. Discard marks it as dismissed. Accept is blocked: "
    "6 players have played rated games since; adding this game now would need a full replay.\n"
    "[c3c3c3c3]")


def test_the_six_live_rows_post_two_entries_in_plain_words():
    feed = FakeFeed(live_feed())
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    assert texts(channel) == [GOLDEN]
    assert GOLDEN.isascii() and len(GOLDEN) <= 2000
    assert feed.posts == [("new", ["c2c2c2c2-0000-4000-8000-0000000000c2",
                                   "c3c3c3c3-0000-4000-8000-0000000000c3"], 200)]


def test_no_uuid_and_no_steam_id_in_the_body():
    feed = FakeFeed(live_feed())
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    import re
    for t in texts(channel):
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", t)
        assert not re.search(r"\d{17}", t)


def test_two_reports_of_one_game_are_one_entry():
    f = fx.facts("A", "B", "C2", "C3")
    rows = [fx.row("C2", qid=f"c2c2c2c{n}-0000-4000-8000-0000000000c2") for n in (1, 2)]
    rows[1]["photon_room_id"] = None          # the variant row of the same room
    feed = FakeFeed([feed_row(r, f) for r in rows])
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    (msg,) = texts(channel)
    assert msg.count("**FFA") == 1
    assert "Reported by Ash. 2 reports, same numbers." in msg
    assert "[c2c2c2c1, c2c2c2c2]" in msg


# ── no repeats; the reminder's clock is the rows' ──────────────────────────

def test_a_restart_posts_nothing_when_nothing_is_new():
    rows = live_feed()
    for r in rows:
        r["posted"] = True
    feed = FakeFeed(rows, reminder_due=False)
    ns, channel, _ = new_bot(feed)            # a fresh process
    for _ in range(3):
        run(ns["poll_quarantine_digest"]())
    assert texts(channel) == [] and feed.posts == []


def test_a_fresh_bot_with_a_reminder_one_hour_old_posts_nothing():
    """The api says whether the reminder is due, from the rows' stamps; a
    stamp one hour old is not due, so a restart posts nothing."""
    f = fx.facts("C2")
    hw = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
    r = fx.row("C2", posted=hw - timedelta(days=3), reminded=hw - timedelta(hours=1))
    v = main._qdig_classify(r, f)
    fr = feed_row(r, f)
    assert main._qdig_totals([(r, v, fr)], hw, True)["reminder_due"] is False
    r25 = fx.row("C2", posted=hw - timedelta(days=3), reminded=hw - timedelta(hours=25))
    assert main._qdig_totals([(r25, v, feed_row(r25, f))], hw, True)["reminder_due"] is True
    unposted = fx.row("C2")
    assert main._qdig_totals([(unposted, v, feed_row(unposted, f))], hw, True)["reminder_due"] is False
    assert main._qdig_totals([], hw, True)["reminder_due"] is False
    fr["posted"] = True
    feed = FakeFeed([fr], reminder_due=False)
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    assert texts(channel) == [] and feed.posts == []


def test_a_due_reminder_is_one_line_and_is_stamped():
    rows = live_feed()
    for r in rows:
        r["posted"] = True
    feed = FakeFeed(rows, reminder_due=True)
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    assert texts(channel) == [
        f"Held game reports: 2 games still need a decision; the oldest was played <t:{C2_UNIX}:f>. "
        "See the Admin tab, Rejected Reports."]
    assert feed.posts == [("reminder", ["c2c2c2c2-0000-4000-8000-0000000000c2",
                                        "c3c3c3c3-0000-4000-8000-0000000000c3"], 200)]


def test_a_failed_stamp_is_retried_and_the_message_is_not_posted_again():
    feed = FakeFeed(live_feed(), post_status=[503, 200])
    ns, channel, clock = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    clock.advance(60)
    run(ns["poll_quarantine_digest"]())
    assert len(texts(channel)) == 1
    assert [p[0] for p in feed.posts] == ["new", "new"] and [p[2] for p in feed.posts] == [503, 200]


# ── packing ────────────────────────────────────────────────────────────────

def test_messages_stay_under_2000_characters_by_whole_entries():
    f = fx.facts("C2")
    rows = []
    for n in range(30):
        r = fx.row("C2", qid=f"{n:08x}-0000-4000-8000-0000000000c2")
        r["photon_room_id"] = f"QDIGPACK_{n:06d}_r2"
        r["payload"] = dict(r["payload"], photon_room_id=r["photon_room_id"])
        rows.append(feed_row(r, f))
    feed = FakeFeed(rows)
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    msgs = texts(channel)
    assert len(msgs) > 1
    assert msgs[0].startswith(main_header := "Held game reports: results a player's game sent")
    assert all(m.startswith("Held game reports (continued):") for m in msgs[1:])
    assert all(len(m) <= 2000 for m in msgs)
    entries = [e for m in msgs for e in m.split("\n\n")[1:]]
    assert len(entries) == 30 and all(e.startswith("**FFA") and e.endswith("]") for e in entries)
    assert sorted(i for k, ids, s in feed.posts for i in ids) == sorted(r["id"] for r in rows)
    assert main_header


# ── the other shapes ───────────────────────────────────────────────────────

def _side_row(shape):
    import test_qdig_classify as tc
    r = tc._team_row(shape)
    r["created_at"] = fx.T_LIVE
    return feed_row(r, fx.facts("A"), gate=(0, 0))


def test_a_2v2_entry_names_both_teams_and_their_score():
    feed = FakeFeed([_side_row("2v2")])
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    (msg,) = texts(channel)
    assert "**2v2, ranked** - played" in msg
    assert "Why held: The series was already completed when this report arrived" in msg
    assert "- Gale + Heron: 3, 25 (winner)\n- Iris + Juniper: 1, 12" in msg
    assert "Accept is blocked" not in msg


def test_a_1v2_entry_names_both_sides_and_their_score():
    feed = FakeFeed([_side_row("1v2")])
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    (msg,) = texts(channel)
    assert "**1v2, casual** - played" in msg
    assert "- Gale: 2, 18\n- Heron + Iris: 3, 26 (winner)" in msg


def test_names_are_escaped_and_kept_to_one_line():
    rows = live_feed()
    for r in rows:
        for p in r["players"]:
            if p["name"] == "Dune":
                p["name"] = "**Du_ne**\n@everyone"
        if r.get("winner_name") == "Dune":
            r["winner_name"] = "**Du_ne**\n@everyone"
    feed = FakeFeed(rows)
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    (msg,) = texts(channel)
    assert "- \\*\\*Du\\_ne\\*\\* @everyone: 5, 11, 31 (winner)" in msg


# ── the two compatibility directions ───────────────────────────────────────

def test_the_new_bot_falls_back_to_todays_form_without_the_new_keys():
    rows = [{k: r[k] for k in ("id", "mode", "group", "family", "created_at")} for r in live_feed()]
    feed = FakeFeed(rows, form=None)
    ns, channel, _ = new_bot(feed)
    qb.settle_state(ns, types.SimpleNamespace(t=1000.0))
    run(ns["poll_quarantine_digest"]())
    (msg,) = texts(channel)
    assert msg.startswith("quarantined reports pending review, new since the last round: 6")
    assert qb.ids_in(msg) == [r["id"] for r in rows]
    assert feed.posts == []


def test_the_old_bot_keeps_working_against_the_new_answer():
    """The api deploys first: the bot at 85a7d0b0 reads the QDIG-1 answer and
    posts today's one-line form for every pending row, without error."""
    feed = FakeFeed(live_feed())
    ns, channel, _ = old_bot(feed)
    qb.settle_state(ns, types.SimpleNamespace(t=1000.0))
    run(ns["poll_quarantine_digest"]())
    (msg,) = texts(channel)
    assert msg.startswith("quarantined reports pending review, new since the last round: 6")
    assert qb.ids_in(msg) == [r["id"] for r in live_feed()]
    assert not [line for line in ns["_out"] if "error" in line]
    assert feed.posts == []
