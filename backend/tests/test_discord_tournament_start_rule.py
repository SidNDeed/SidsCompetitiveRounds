"""Board row 32 (2026-09-28): the synchronized tournament's start rule, stated
in every message the bot composes about a sync tournament in voting.

A sync tournament starts only when min_players (8) players agree on ONE of
the offered start times; signing up is not agreeing. The report: the channel
text implied that sign-ups start it, and the bot DMed an availability check
when 8 had signed up with no time consensus. Pinned here, each against the
bot's own lifted code over a fake Discord client and a fake api:

(a) the signups-open channel post states the rule, how far the vote has got
    ("N of 8 agree on <time> so far") and how to vote in the F5 tab;
(b) the tournament board's sync embed does the same, its "How it works"
    blurb states the rule, and the two embeds still fit one message's
    6000-character budget (re-measured here: 5837);
(c) the availability-check DM goes out only when its premise holds - some
    start time has 8 votes - and names that time; until then the notice
    stays queued (no DM, no ack), and a notice whose tournament is no longer
    the sync one in voting is dropped unsent;
(d) the tournaments FAQ answer carries the live tally in Discord.

The tally is /tournaments/current's public time_slot_tallies, read with a
registered player's Steam id: that route computes tallies only for a caller.
The signup-count line and the push-back post are composed by the server
(tournaments.py) and only relayed by the bot; they are the server half of
row 32 and are not changed here.

Guards that pass on the pre-row-32 code by construction (the locked board,
the async check, the FAQ without a sync tournament in voting) say so in
their docstrings; every other test here is red on that code.
"""

import ast
import json
import urllib.parse
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import discord_collection_harness as H

FUNCS = {
    "api_get", "_announce_in_channel", "_fmt_pt", "_unix_ts",
    "_tsync_tally", "_tsync_tally_for", "_tsync_times", "_tsync_progress", "_tsync_rule",
    "_tsync_signups_open_text", "poll_tournaments", "_tavail_embed", "_ack_tournament_notices",
    "poll_tournament_notices", "_build_tournament_board_embed", "_publish_tournament_board",
    "_faq_tournaments", "_faq_resolve_answer",
}
ASSIGNS = {
    "ASYNC_DEADLINE_DAYS", "_TSYNC_VOTE_HOW", "_tournament_state", "_notified_completed",
    "_notified_prestart", "_watch_cache", "_tavail_seen_notice_ids", "_tavail_held",
    "_TMATCH_NOTICE_KINDS", "_TOURNEY_HOW_IT_WORKS", "_tournament_board_ids",
}

TID = "5a5a5a5a-0000-4000-8000-000000000032"
OTHER_TID = "5b5b5b5b-0000-4000-8000-000000000033"
ANNOUNCE = 5501   # TOURNAMENT_CHANNEL_ID
BOARD = 5502      # SCR_TOURNAMENTS_CHANNEL
LOCK = 1790524800
DEFAULT = 1790697600
S1, S2, S3 = 1790708400, 1790712000, 1790715600
HOW_TO_VOTE = "Vote for every time you can make in F5 -> Tournaments."
RULE = "It starts when 8 players agree on one start time"


def iso(unix):
    return datetime.fromtimestamp(unix, timezone.utc).isoformat()


class Api:
    """The api routes these paths read, in their shapes. /tournaments/current
    carries tallies only when the read names a caller (steam_id), as the
    route does."""

    def __init__(self, tallies=(), *, current_tid=TID, current_status="voting", min_players=8,
                 current_reply=None, watch=(), notices=()):
        self.tallies = list(tallies)          # [(slot unix, votes)]
        self.current_tid, self.current_status = current_tid, current_status
        self.min_players = min_players
        self.current_reply = current_reply    # a Reply answering every /current read instead
        self.watch = list(watch)
        self.notices = list(notices)
        self.acked = []
        self.current_reads = []               # the query of every /tournaments/current read

    async def __call__(self, call):
        parts = urllib.parse.urlsplit(call.path)
        path, query = parts.path, dict(urllib.parse.parse_qsl(parts.query))
        if call.method == "GET" and path == "/tournaments/current":
            self.current_reads.append(query)
            if self.current_reply is not None:
                return self.current_reply
            tallies = ([{"slot_ts": iso(slot), "votes": votes} for slot, votes in self.tallies]
                       if query.get("steam_id") else [])
            return H.Reply(200, json={
                "tournament_id": self.current_tid, "status": self.current_status, "kind": "sync",
                "min_players": self.min_players, "max_players": 16, "time_slot_tallies": tallies})
        if call.method == "GET" and path == "/tournaments/internal/watch":
            return H.Reply(200, json={"tournaments": self.watch})
        if call.method == "GET" and path == "/internal/tournament-notices":
            return H.Reply(200, json={"notices": [n for n in self.notices if n["notice_id"] not in self.acked]})
        if call.method == "POST" and path == "/internal/tournament-notices/ack":
            self.acked.extend(call.payload["notice_ids"])
            return H.Reply(200, json={"acked": len(call.payload["notice_ids"])})
        raise AssertionError(f"unexpected {call.method} {call.path}")


class Embed:
    def __init__(self, title=None, description=None, color=None, **kw):
        self.title, self.description, self.color, self.fields = title, description, color, []

    def add_field(self, *, name, value, inline=True):
        self.fields.append(SimpleNamespace(name=name, value=value, inline=inline))
        return self


NotFound = type("NotFound", (Exception,), {})
Forbidden = type("Forbidden", (Exception,), {})


class Channel:
    def __init__(self, cid):
        self.id, self.sent, self.last_message_id = cid, [], None

    async def send(self, content=None, **kw):
        self.sent.append(SimpleNamespace(content=content, kw=kw))
        return SimpleNamespace(id=9000 + len(self.sent))

    def history(self, limit=50):
        async def none_yet():
            return
            yield
        return none_yet()


class Client:
    """The fake Discord client: channels record what is posted, users record their DMs."""

    def __init__(self):
        self.channels = {cid: Channel(cid) for cid in (ANNOUNCE, BOARD)}
        self.dms = []
        self.user = SimpleNamespace(id=1)

    def get_channel(self, cid):
        return self.channels.get(cid)

    async def fetch_channel(self, cid):
        raise NotFound(cid)

    def get_user(self, uid):
        client = self

        async def send(content=None, embed=None, view=None, allowed_mentions=None):
            client.dms.append(SimpleNamespace(uid=uid, content=content, embed=embed, view=view))
        return SimpleNamespace(id=uid, send=send)

    async def fetch_user(self, uid):
        return self.get_user(uid)

    def texts(self, cid):
        return [s.content for s in self.channels[cid].sent]


def rig_for(api):
    client = Client()
    fake_discord = SimpleNamespace(Embed=Embed, NotFound=NotFound, Forbidden=Forbidden,
                                   HTTPException=Exception,
                                   AllowedMentions=SimpleNamespace(none=lambda: "none"))
    extra = {"discord": fake_discord, "bot": client, "urllib": urllib,
             "TOURNAMENT_CHANNEL_ID": ANNOUNCE, "SCR_TOURNAMENTS_CHANNEL": BOARD,
             "_tavail_view": lambda tid, steam: ("view", str(tid), str(steam))}
    rig = H.BotRig(api, funcs=FUNCS, assigns=ASSIGNS, extra=extra)
    rig.client, rig.api = client, api
    return rig


def clean(rig):
    """No lifted loop swallowed an exception: each of them logs and returns
    on one, which would read as 'nothing was sent'."""
    bad = [ln for ln in rig.logs if "error" in ln.lower() or "failed" in ln.lower()]
    assert bad == []


def sync_watch(status="voting", signups=3, tid=TID, name="Entrant {i}", **kw):
    t = {"tournament_id": tid, "status": status, "kind": "sync", "min_players": 8, "max_players": 16,
         "default_start_ts": iso(DEFAULT), "scheduled_start_ts": None, "lock_at": iso(LOCK),
         "signups": [{"signup_id": f"s{i}", "steam_id": H.steam_of(i), "display_name": name.format(i=i),
                      "is_speculative": False} for i in range(1, signups + 1)],
         "prize_gold": [1000, 500, 250], "prize_xp": [5000, 2500, 1250], "prize_players": 8}
    t.update(kw)
    return t


def async_watch(signups=3, name="Async entrant {i}"):
    t = sync_watch(signups=signups, tid="6c6c6c6c-0000-4000-8000-000000000034", name=name)
    t["kind"] = "async"
    return t


def notice(nid, n, kind="sync", tid=TID):
    return {"notice_id": nid, "notice_type": "availability_check", "discord_id": H.discord_of(n),
            "tournament_id": tid, "steam_id": H.steam_of(n), "kind": kind,
            "default_start_ts": iso(DEFAULT), "lock_at": iso(LOCK),
            "payload": json.dumps({"kind": kind, "start_ts": DEFAULT, "lock_ts": LOCK,
                                   "label": "Sync tournament", "tournament_id": tid})}


def tick(rig):
    H.run(rig.ns["poll_tournament_notices"]())
    clean(rig)


def held_lines(rig):
    return [ln for ln in rig.logs if "held until" in ln]


# -- (a) the signups-open channel post --------------------------------------------------------------

def test_row32_a_the_signups_open_post_states_the_rule_the_tally_and_how_to_vote():
    api = Api(tallies=[(S1, 3), (S2, 1)], watch=[sync_watch()])
    rig = rig_for(api)
    H.run(rig.ns["poll_tournaments"]())
    clean(rig)
    assert rig.client.texts(ANNOUNCE) == [
        f"**Tournament signups open.** {RULE}: 3 of 8 agree on <t:{S1}:F> so far. "
        f"Default start: <t:{DEFAULT}:F>. {HOW_TO_VOTE} Signups close <t:{LOCK}:F>."]
    # The tally is the in-game tab's own, read as a registered entrant.
    assert api.current_reads == [{"kind": "sync", "steam_id": H.steam_of(1)}]


def test_row32_a_an_unreadable_tally_still_states_the_rule_and_how_to_vote():
    api = Api(watch=[sync_watch()], current_reply=H.Reply(503, json={"detail": "busy"}))
    rig = rig_for(api)
    H.run(rig.ns["poll_tournaments"]())
    clean(rig)
    assert rig.client.texts(ANNOUNCE) == [
        f"**Tournament signups open.** {RULE}. Default start: <t:{DEFAULT}:F>. {HOW_TO_VOTE} "
        f"Signups close <t:{LOCK}:F>."]


def test_row32_a_a_tournament_nobody_has_joined_says_nobody_agrees_yet():
    api = Api(tallies=[(S1, 2)], watch=[sync_watch(signups=0)])
    rig = rig_for(api)
    H.run(rig.ns["poll_tournaments"]())
    clean(rig)
    assert rig.client.texts(ANNOUNCE) == [
        f"**Tournament signups open.** {RULE}: 0 of 8 agree on a time so far. "
        f"Default start: <t:{DEFAULT}:F>. {HOW_TO_VOTE} Signups close <t:{LOCK}:F>."]
    assert api.current_reads == [{"kind": "sync"}]


# -- (b) the tournament board ------------------------------------------------------------------------

def publish(rig, *tournaments):
    rig.ns["_watch_cache"] = {"tournaments": list(tournaments)}
    H.run(rig.ns["_publish_tournament_board"]())
    clean(rig)
    sent = rig.client.channels[BOARD].sent
    assert len(sent) == 1
    return sent[0].kw["embeds"]


def test_row32_b_the_board_states_the_rule_the_tally_and_how_to_vote():
    api = Api(tallies=[(S1, 3), (S2, 1)])
    rig = rig_for(api)
    sync_em, async_em = publish(rig, sync_watch(), async_watch())
    lines = sync_em.description.split("\n")
    assert f"{RULE}: 3 of 8 agree on <t:{S1}:F> so far." in lines
    assert HOW_TO_VOTE in lines
    assert not [ln for ln in lines if "voting is open in-game" in ln]
    how = sync_em.fields[0].value
    assert "vote for every start time you can make: it starts when 8 players agree on one time." in how
    assert api.current_reads == [{"kind": "sync", "steam_id": H.steam_of(1)}]
    assert RULE not in async_em.description


@pytest.mark.parametrize("tallies, progress", [
    ([(S1, 4), (S2, 4), (S3, 4)], f"4 of 8 agree on <t:{S1}:F> or 2 other times so far"),
    ([(S1, 8), (S2, 8), (S3, 2)], f"8 players agree on <t:{S1}:F> or <t:{S2}:F> so far - enough to lock it"),
])
def test_row32_b_tied_times_are_named_together(tallies, progress):
    rig = rig_for(Api(tallies=tallies))
    sync_em, _ = publish(rig, sync_watch(), async_watch())
    assert f"{RULE}: {progress}." in sync_em.description.split("\n")


def test_row32_b_a_locked_board_reads_no_tally():
    """Guard (passes on the pre-row-32 code too): once locked, the time is
    decided, so the board neither reads the tally nor states the vote."""
    api = Api(tallies=[(S1, 8)])
    rig = rig_for(api)
    sync_em, _ = publish(rig, sync_watch(status="locked", scheduled_start_ts=iso(S1)), async_watch())
    assert api.current_reads == []
    assert RULE not in sync_em.description


def test_row32_b_the_two_board_embeds_still_fit_one_message():
    """Worst case, measured: two descriptions cut at the cap, the two 'How
    it works' fields and the two titles. The comment above the cap in
    discord_bot.py states the same total."""
    rig = rig_for(Api())
    tally = {"tournament_id": TID, "status": "voting", "min_players": 8, "votes": 3, "slots": [S1]}
    long_name = "Entrant {i:02d} " + "with a display name long enough to reach the cap " * 3
    sync_em = rig.ns["_build_tournament_board_embed"](sync_watch(signups=40, name=long_name), "sync", tally)
    async_em = rig.ns["_build_tournament_board_embed"](async_watch(signups=40, name=long_name), "async")
    assert [len(em.description) for em in (sync_em, async_em)] == [2582, 2582]
    total = sum(len(em.title) + len(em.description) + sum(len(f.name) + len(f.value) for f in em.fields)
                for em in (sync_em, async_em))
    assert total == 5837
    assert total < 6000
    assert "titles = 5837" in H.bot_source()


# -- (c) the availability-check DM ---------------------------------------------------------------------

def test_row32_c_no_dm_while_no_time_has_8_votes_then_the_same_notices_go_out_naming_it():
    api = Api(tallies=[(S1, 5), (S2, 2)], notices=[notice("n1", 1), notice("n2", 2), notice("n3", 3)])
    rig = rig_for(api)
    tick(rig)
    assert rig.client.dms == []
    assert api.acked == []
    assert not [c for c in rig.calls if c.path == "/internal/tournament-notices/ack"]
    # one tally read for the tick, whatever the number of notices, as the recipient
    assert api.current_reads == [{"kind": "sync", "steam_id": H.steam_of(1)}]
    assert held_lines(rig) == [
        f"[TAVAIL] availability checks for tournament {TID[:8]} held until a start time has 8 votes: "
        f"5 of 8 agree on <t:{S1}:F> so far"]
    tick(rig)   # the same tally: still held, logged once
    assert rig.client.dms == [] and api.acked == []
    assert len(held_lines(rig)) == 1 and len(api.current_reads) == 2
    api.tallies = [(S1, 6), (S2, 2)]
    tick(rig)   # the tally moved: held, logged again
    assert rig.client.dms == [] and api.acked == []
    assert held_lines(rig)[-1].endswith(f"held until a start time has 8 votes: 6 of 8 agree on <t:{S1}:F> so far")
    api.tallies = [(S1, 8), (S2, 2)]
    tick(rig)   # a time reached 8: the queued notices go out, naming it
    assert [d.uid for d in rig.client.dms] == [int(H.discord_of(n)) for n in (1, 2, 3)]
    assert {d.content for d in rig.client.dms} == {
        f"Are you still available to play in the **Synchronized tournament** at <t:{S1}:F>?"}
    assert api.acked == ["n1", "n2", "n3"]
    assert len(api.current_reads) == 4


def test_row32_c_the_dm_names_the_time_it_asks_about_and_states_the_rule():
    api = Api(tallies=[(S1, 8), (S2, 3)], notices=[notice("n1", 1)])
    rig = rig_for(api)
    tick(rig)
    assert len(rig.client.dms) == 1
    dm = rig.client.dms[0]
    assert dm.uid == int(H.discord_of(1))
    assert dm.content == f"Are you still available to play in the **Synchronized tournament** at <t:{S1}:F>?"
    lines = dm.embed.description.split("\n")
    assert lines[0] == f"Asked about: <t:{S1}:F>"
    assert lines[1] == (f"{RULE}: 8 players agree on <t:{S1}:F> so far - enough to lock it. "
                        f"The time locks in <t:{LOCK}:F>, always at least a day before play. {HOW_TO_VOTE}")
    assert dm.view == ("view", TID, H.steam_of(1))
    assert api.acked == ["n1"]


def test_row32_c_tied_times_at_8_are_both_named():
    api = Api(tallies=[(S1, 8), (S2, 8)], notices=[notice("n1", 1)])
    rig = rig_for(api)
    tick(rig)
    assert [d.content for d in rig.client.dms] == [
        f"Are you still available to play in the **Synchronized tournament** at <t:{S1}:F> or <t:{S2}:F>?"]


@pytest.mark.parametrize("current_tid, current_status", [(OTHER_TID, "voting"), (TID, "locked")])
def test_row32_c_a_notice_whose_tournament_left_voting_is_dropped_unsent(current_tid, current_status):
    api = Api(tallies=[(S1, 8)], current_tid=current_tid, current_status=current_status,
              notices=[notice("n1", 1)])
    rig = rig_for(api)
    tick(rig)
    assert rig.client.dms == []
    assert api.acked == ["n1"]
    assert (f"[TAVAIL] availability check n1 for tournament {TID[:8]} dropped: it is no longer the sync "
            "tournament in voting") in rig.logs


def test_row32_c_an_unreadable_tally_holds_the_notice():
    api = Api(current_reply=H.Reply(500, b"unavailable"), notices=[notice("n1", 1)])
    rig = rig_for(api)
    tick(rig)
    assert rig.client.dms == []
    assert api.acked == []
    assert "API GET /tournaments/current -> HTTP 500" in rig.logs


def test_row32_c_the_async_check_is_unchanged_and_reads_no_tally():
    """Guard (passes on the pre-row-32 code too): the async check asks
    nothing about a start time."""
    api = Api(tallies=[(S1, 1)], notices=[notice("a1", 1, kind="async")])
    rig = rig_for(api)
    tick(rig)
    assert [d.content for d in rig.client.dms] == ["Are you still in for the **Async tournament**?"]
    assert api.current_reads == []
    assert api.acked == ["a1"]


def test_row32_c_the_check_without_a_tally_names_the_default_start():
    rig = rig_for(Api())
    em = rig.ns["_tavail_embed"]("sync", DEFAULT, LOCK)
    lines = em.description.split("\n")
    assert lines[0] == f"Asked about: <t:{DEFAULT}:F>"
    assert lines[1].startswith(f"{RULE}. The time locks in <t:{LOCK}:F>")


# -- (d) the tournaments FAQ answer --------------------------------------------------------------------

def faq_entry(rig):
    """The tournaments entry of FAQ_ENTRIES, evaluated in the rig (the list's
    other entries name handlers this rig does not lift)."""
    for node in ast.parse(H.bot_source()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FAQ_ENTRIES"
                                                for t in node.targets):
            for elt in node.value.elts:
                keys = {k.value: v for k, v in zip(elt.keys, elt.values) if isinstance(k, ast.Constant)}
                if isinstance(keys.get("key"), ast.Constant) and keys["key"].value == "tournaments":
                    entry = eval(compile(ast.Expression(body=elt), str(H.BOT_PATH), "eval"), rig.ns)
                    rig.ns["FAQ_ENTRIES"] = [entry]
                    return entry
    raise AssertionError("FAQ_ENTRIES has no tournaments entry")


def test_row32_d_the_faq_answer_carries_the_live_tally_in_discord():
    api = Api(tallies=[(S1, 3)])
    rig = rig_for(api)
    entry = faq_entry(rig)
    rig.ns["_watch_cache"] = {"tournaments": [async_watch(), sync_watch()]}
    answer = H.run(rig.ns["_faq_resolve_answer"](entry, {"content": "how do tournaments work"}))
    clean(rig)
    assert answer.endswith(f"\n**Current sync tournament:** {RULE}: 3 of 8 agree on <t:{S1}:F> so far. "
                           f"{HOW_TO_VOTE}")
    assert ("Once 8 players agree on one time you'll get an availability-check DM that names that time"
            in answer)
    assert api.current_reads == [{"kind": "sync", "steam_id": H.steam_of(1)}]
    # In-game (no Discord message): the static answer, no read.
    assert H.run(rig.ns["_faq_resolve_answer"](entry, None)) == entry["answer"]
    assert len(api.current_reads) == 1


def test_row32_d_without_a_sync_tournament_in_voting_the_faq_answer_is_static():
    """Guard (passes on the pre-row-32 code too): nothing to tally, no read."""
    api = Api(tallies=[(S1, 3)])
    rig = rig_for(api)
    entry = faq_entry(rig)
    rig.ns["_watch_cache"] = {"tournaments": [sync_watch(status="locked"), async_watch()]}
    answer = H.run(rig.ns["_faq_resolve_answer"](entry, {"content": "how do tournaments work"}))
    assert answer == entry["answer"]
    assert api.current_reads == []


# -- (e) and (f): the server-composed lines (Discord fix round 3, item 6) ---------------------------
#
# tournaments.py composes two channel lines about a sync tournament that the
# bot only relays: the signup-count line (every signup and unsignup) and the
# push-back. Both now carry the start rule with the lock's eligible tally and
# how to vote, and the push-back names the consensus, not the count. The
# sentence is tournaments._tsync_rule, one function for both lines, and it is
# byte-equal to the bot's _tsync_rule (the bot image carries discord_bot.py
# alone, so the two cannot share an import): (e) pins that equality over every
# progress shape, the bot's side read through its own tally parse.

def _server_tallies(tallies):
    return [(datetime.fromtimestamp(slot, timezone.utc), votes) for slot, votes in tallies]


@pytest.mark.parametrize("tallies", [
    None, [], [(S1, 3), (S2, 1)], [(S1, 4), (S2, 4)], [(S1, 4), (S2, 4), (S3, 4)],
    [(S1, 8), (S2, 8), (S3, 2)], [(S1, 9), (S2, 3)],
], ids=["unread", "no-votes", "below", "tie-2", "tie-3", "at-quorum-tie", "above"])
def test_row32_e_the_server_states_the_bots_start_rule_sentence_byte_for_byte(tallies):
    import tournaments as T
    rig = rig_for(Api(tallies=tallies or []))
    bot_tally = None if tallies is None else H.run(rig.ns["_tsync_tally"](H.steam_of(1)))
    server = T._tsync_rule(8, None if tallies is None else _server_tallies(tallies))
    assert server == rig.ns["_tsync_rule"](8, bot_tally), server
    assert server.startswith(RULE) and server.isascii()
    assert T.TSYNC_VOTE_HOW == rig.ns["_TSYNC_VOTE_HOW"] == HOW_TO_VOTE


def test_row32_e_the_signup_count_line_states_the_rule_not_a_signup_count_to_start():
    """A sync tournament in voting: the count of entrants stays, "8 players
    required to start" goes, the rule with the tally and how to vote come in.
    Locked sync and async lines are unchanged (guards)."""
    import tournaments as T
    t = SimpleNamespace(kind="sync", status="voting", max_players=16, min_players=8,
                        default_start_ts=datetime.fromtimestamp(DEFAULT, timezone.utc),
                        scheduled_start_ts=None, lock_at=datetime.fromtimestamp(LOCK, timezone.utc))
    line = T._signup_count_line(t, 8, _server_tallies([(S1, 3), (S2, 1)]))
    assert line == (f"( 8 / 16 ) players have entered the Synchronized tournament. {RULE}: 3 of 8 agree on"
                    f" <t:{S1}:F> so far. {HOW_TO_VOTE} Default start: <t:{DEFAULT}:F>."), line
    assert "required to start" not in line and line.isascii()
    t.status, t.scheduled_start_ts = "locked", datetime.fromtimestamp(S1, timezone.utc)
    assert T._signup_count_line(t, 8) == ("( 8 / 16 ) players have entered the Synchronized tournament. 8 players"
                                          f" required to start. Current start time is <t:{S1}:F>.")
    t.kind, t.status = "async", "voting"
    assert T._signup_count_line(t, 3) == ("( 3 / 16 ) players have entered the Asynchronous tournament. 8 players"
                                          f" required to start. Signups close <t:{LOCK}:F>.")


def test_row32_f_the_unsignup_line_and_the_push_back_state_the_rule_and_name_the_consensus(monkeypatch, tmp_path):
    """The real app on the lane database: eight entrants, five vote for the
    one slot; a voter leaves through the unsignup route - its channel line
    states the rule at 4 of 8 on that slot; the lock pushes back - its post
    names the consensus ("no start time had 8 players agreeing on it", not
    the best slot's count), the new start, the rule with the carried votes at
    their new time (4 of 8, a week later) and how to vote."""
    import test_discord_tournament_quorum as Q
    from datetime import timedelta

    async def body(env):
        people = await Q.entrants_of(env, 8)
        tid, slot = await Q.sync_tournament(env, people, 5)
        unix = int(slot.timestamp())
        leaver = people[1]
        r = await env.client.post(f"/api/v1/tournaments/{tid}/unsignup", json={"steam_id": leaver.steam},
                                  headers=env.mod_headers(leaver))
        assert r.status_code == 200, (r.status_code, r.text[:300])
        posts = lambda: env.rows(f"SELECT content FROM {Q.SCHEMA}.pending_channel_posts ORDER BY created_at, id")
        left = [p["content"] for p in await posts()]
        assert left[-1] == ("A player left the Synchronized tournament \u2014 ( 7 / 16 ) players have entered the"
                            f" Synchronized tournament. {RULE}: 4 of 8 agree on <t:{unix}:F> so far. {HOW_TO_VOTE}"
                            f" Default start: <t:{unix}:F>."), left[-1]
        status, _start = await Q.lock(env, tid)
        assert status == "voting"
        pushed = (await posts())[-1]["content"]
        later = unix + 7 * 86400
        tail = pushed.split(" \u2014 the ", 1)[-1]
        assert tail == ("Synchronized tournament has been pushed back: no start time had 8 players agreeing on"
                        f" it. New start time is <t:{later}:F>. {RULE}: 4 of 8 agree on <t:{later}:F> so far."
                        f" {HOW_TO_VOTE} Your time votes carried over to the same times next week \u2014 update"
                        " them in the F5 tab if that no longer works for you."), pushed
        assert "best slot had" not in pushed
    Q.e2e(monkeypatch, tmp_path, body)


def test_row32_f_a_force_start_push_back_keeps_the_eligible_count(monkeypatch, tmp_path):
    """A force start skips the time vote, so when the ban filter leaves it
    short its push-back says so (7 of 8 eligible), not that no time had 8
    agreeing; the rule and how to vote follow as on every sync push-back."""
    import test_discord_tournament_quorum as Q
    import models

    async def body(env):
        people = await Q.entrants_of(env, 8)
        tid, slot = await Q.sync_tournament(env, people, 0)
        await env.ban(people[5])

        async def go(db, T):
            t = await db.get(models.Tournament, tid)
            await T.lock_tournament(db, t, force=True)
            return t.status
        assert await Q.in_app(env, go) == "voting"
        pushed = (await env.rows(f"SELECT content FROM {Q.SCHEMA}.pending_channel_posts"
                                 " ORDER BY created_at, id"))[-1]["content"]
        later = int(slot.timestamp()) + 7 * 86400
        assert ("pushed back: not enough players (7 of 8 required signed up). New start time is"
                f" <t:{later}:F>. {RULE}: 0 of 8 agree on a time so far. {HOW_TO_VOTE}") in pushed, pushed
    Q.e2e(monkeypatch, tmp_path, body)
