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
import re
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
    v = fx.judge(main, r, f)
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
    v = fx.judge(main, r, f)
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
    # @ is escaped too since BOT-TEXT-ESCAPE-1 stage 2 (QDIG_MD_CHARS covers _escape_md's set)
    assert "- \\*\\*Du\\_ne\\*\\* \\@everyone: 5, 11, 31 (winner)" in msg


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


# ── review qdig-r1 ─────────────────────────────────────────────────────────

def _needs_a_row(f):
    """Game A held with Juniper's rounds changed: NEEDS A DECISION, its
    reason built on the server with names in it."""
    import test_qdig_classify as tc
    body = fx.payload("A", tc._with(fx.GAMES["A"]["held"], 3, 0, 2))
    return feed_row(fx.row("A", body=body, qid="0a0a0a0a-0000-4000-8000-0000000000aa"), f)


def test_names_inside_the_reason_reach_discord_escaped_and_inert():
    """HIGH 2: a display name enters the reason sentence on the server; in
    the message it is escaped and its link is inert."""
    f = fx.facts("A")
    f["names"][fx.steam(4)]["display_name"] = "**ALERT** https://evil.example"
    feed = FakeFeed([_needs_a_row(f)])
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    (msg,) = texts(channel)
    assert "**ALERT**" not in msg, "a name reached Discord with its markdown live"
    assert "https://" not in msg, "a name reached Discord as a live link"
    assert "\\*\\*ALERT\\*\\* https: //evil.example" in msg


# Keys of a feed row that are structure, not text a person wrote; every
# other string the row carries, at any depth, is a census subject.
STRUCTURAL = {"id", "mode", "group", "family", "created_at", "class", "game_key", "played_at", "malformed",
              "field"}
SENTINEL = "Z**Q_`|>[a](https://s.example)<t:0:R>#" + chr(0x202E) + "\nZQ9"


def _string_paths(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in STRUCTURAL:
                yield from _string_paths(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _string_paths(v, path + (i,))
    elif isinstance(obj, str):
        yield path


def _set(obj, path, value):
    for k in path[:-1]:
        obj = obj[k]
    obj[path[-1]] = value


def test_census_every_string_of_a_feed_row_reaches_discord_through_the_one_function():
    """Each string leaf of each row shape (FFA needs, F5, 2v2, 1v2), set in
    turn to a sentinel full of markdown, a link, a timestamp, a direction
    override and a line break: the sentinel never appears raw, and no
    message carries a live link."""
    f = fx.facts("A", "C2")
    shapes = [_needs_a_row(f), feed_row(fx.row("C2"), f), _side_row("2v2"), _side_row("1v2")]
    seen = 0
    for shape in shapes:
        paths = list(_string_paths(shape))
        assert paths
        for path in paths:
            row = copy.deepcopy(shape)
            _set(row, path, SENTINEL)
            feed = FakeFeed([row])
            ns, channel, _ = new_bot(feed)
            run(ns["poll_quarantine_digest"]())
            for m in texts(channel):
                seen += 1
                assert "Z**Q" not in m and "https://" not in m and chr(0x202E) not in m, (path, m)
                assert not re.search(r"(?<!\\)<t:0:R>", m), (path, m)
                assert "\nZQ9" not in m, path
    assert seen > 30


def test_census_no_format_of_the_renderer_reads_a_row_except_through_the_function():
    """In the bot's QDIG-1 renderer, a format slot that reads a row
    (`.get(...)`) does so inside _qdig_md, _qdig_esc or a number or time
    formatter."""
    allowed = {"_qdig_md", "_qdig_esc", "_qdig_n", "_qdig_when", "_qdig_short_id", "len", "int"}
    fns = {n.name: n for n in qb.TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    names = ["_qdig_entry", "_qdig_diff_line", "_qdig_reminder_line", "_qdig_messages", "_qdig_fit"]
    bad = []
    for name in names:
        for fv in (n for n in ast.walk(fns[name]) if isinstance(n, ast.FormattedValue)):
            def walk(node, guarded):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in allowed:
                    guarded = True
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "get" and not guarded):
                    bad.append((name, ast.unparse(fv.value)))
                for c in ast.iter_child_nodes(node):
                    walk(c, guarded)
            walk(fv.value, False)
    assert bad == []
    assert "_qdig_md" in {n.func.id for n in ast.walk(fns["_qdig_esc"])
                          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


TEN = list(range(21, 31))


def _ten_player_row(monkeypatch, qid="7e070e07-0000-4000-8000-0000000000e7"):
    """The review's case: ten players with 32-character names; recorded
    rounds 5 then nine 2s, held 6 then nine 3s; every player's points 10 to
    11 and kills 20 to 23."""
    for s in TEN:
        monkeypatch.setitem(fx.NAMES, s, f"Player{s:02d}" + "x" * 24)
    monkeypatch.setitem(fx.GAMES, "T", {
        "lobby": fx.LOBBY_AB, "room": "QDIGTEN_200000_r1", "seats": TEN, "match": fx.MATCH_A,
        "recorded": [(5, 10, 20)] + [(2, 10, 20)] * 9, "held": [(6, 11, 23)] + [(3, 11, 23)] * 9,
        "reporters": (21,), "at": fx.T_LIVE, "reason": "ffa_game_contradiction"})
    f = fx.facts("T")
    return feed_row(fx.row("T", qid=qid), f), f


def test_a_ten_player_contradiction_is_posted_within_the_limit(monkeypatch):
    """HIGH 3: the entry is bounded by itself; differences beyond what fits
    become a count."""
    row, _ = _ten_player_row(monkeypatch)
    assert row["class"] == "needs_decision" and len(row["differences"]) == 30
    feed = FakeFeed([row])
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    msgs = texts(channel)
    assert len(msgs) == 1, "the ten-player entry was not posted"
    assert len(msgs[0]) <= 2000
    assert "more differences" in msgs[0]
    assert feed.posts == [("new", [row["id"]], 200)]


def test_an_entry_at_its_bound_does_not_block_the_entry_behind_it(monkeypatch):
    big, _ = _ten_player_row(monkeypatch)
    # The server's reason_text (thirty differences with names) stays; the
    # head the new bot shows is long too.
    big["reason_head"] = "R" * 400
    assert len(big["reason_text"]) > 1000
    big["reporter_name"] = "*" * 64
    big["accept_blocked_reason"] = "_" * 300
    second = feed_row(fx.row("C2"), fx.facts("C2"))
    feed = FakeFeed([big, second])
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    msgs = texts(channel)
    assert all(len(m) <= 2000 for m in msgs)
    stamped = [i for _, ids, _ in feed.posts for i in ids]
    assert second["id"] in stamped, "the entry behind an over-long one was never posted"
    assert big["id"] in stamped


class TwoPageFeed(FakeFeed):
    """D1 with a page size of 2 over three rows: the totals are the first
    page's, as the api computes them."""

    def get(self, url, params=None, headers=None, timeout=None):
        resp = FakeFeed.get(self, url, params, headers, timeout)
        body = resp.body
        all_rows = body["rows"]
        later = bool(params and params.get("after_id"))
        body["page_size"] = 2
        body["rows"] = all_rows[2:] if later else all_rows[:2]
        if not later:
            needs = [r for r in body["rows"] if r.get("class") == "needs_decision"]
            body["totals"]["needs_decision_games"] = len({r["game_key"] for r in needs})
        return resp


def _three_games():
    f = fx.facts("C2")
    rows = []
    for n in range(3):
        r = fx.row("C2", qid=f"{n:08x}-0000-4000-8000-0000000000c2")
        r["photon_room_id"] = f"QDIGPAGE_{n:06d}_r2"
        r["payload"] = dict(r["payload"], photon_room_id=r["photon_room_id"])
        fr = feed_row(r, f)
        fr["posted"] = True
        rows.append(fr)
    return rows


def test_the_reminder_counts_every_page():
    """M3: three games need a decision over two pages; the reminder says 3,
    never the first page's 2."""
    feed = TwoPageFeed(_three_games(), reminder_due=True)
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    (msg,) = texts(channel)
    assert msg.startswith("Held game reports: 3 games still need a decision"), msg
    assert [p[0] for p in feed.posts] == ["reminder"] and len(feed.posts[0][1]) == 3


def test_the_reminder_says_when_it_stopped_counting():
    rows = _three_games()
    rows[2] = {k: rows[2][k] for k in ("id", "mode", "group", "family", "created_at")}
    rows[2].update({"class": None, "detail": False})
    feed = TwoPageFeed(rows, reminder_due=True)
    ns, channel, _ = new_bot(feed)
    run(ns["poll_quarantine_digest"]())
    (msg,) = texts(channel)
    assert msg.startswith("Held game reports: at least 2 games still need a decision (counting stopped: "
                          "1 held report was not yet described)"), msg
