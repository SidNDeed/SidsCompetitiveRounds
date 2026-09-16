"""No SteamID64, no card (v4.13; Sid, 2026-09-15).

A players row whose id is not a public individual SteamID64 is an opponent a
match report named. From v4.13:
  * one pool word, _PC_POOL_MEMBER_SQL, carries steamid64's rule, and every
    reader that decides who is in the pool reads it: the snapshot's pool CTE,
    the open's live re-check, the public pool summary, the bot's /card and
    that card's face preview (its id clause is steamid64's text, written out
    so the janitor's boot self-test can resolve the two janitor reads that
    carry it). Since the 2026-09-15 merge the word is an INTERSECTION -- the
    id rule AND "has run the mod" (_PC_POOL_RULE = 3) -- so a reader that
    carries one half of it is a reader that admits members the pool does not;
  * the open re-rolls such a member an older snapshot still holds, and the
    janitor re-takes a snapshot that holds one ('rule'): re-rolls keep such a
    member from being dealt, but they do not keep an open from being refused;
  * the public pool summary neither counts nor names such a member, and the
    bot's /card answers not_in_pool for one;
  * the bot's /card face preview re-applies the whole pool word with the rest
    of /card's gate, whichever snapshot the caller pins;
  * the events deliverable word carries the rule on the subject: the
    handout's skip marks a pending pull of such a subject posted, and it is
    never handed out;
  * the delivery lease refuses such a subject when it is taken, whatever the
    lease names (a print, events, both or neither), and its re-check before
    a send withdraws a lease on one; the bot's picture source for a print
    answers 404 for a print of one (review r15);
  * migration 320 creates its record table in a transaction of its own, then
    reads once the owners of such subjects' live prints, locks them, and
    retires only the prints they hold, through the two discard columns,
    paying what a discard pays under the 'shards' switch (Sid's decision) and
    nothing under 'none'; it raises unless those owners' shards moved by
    exactly the shards it recorded.
There is no database here. The readers run against sessions that evaluate the
clauses a statement carries from the text it receives; migration 320 is
pinned as text and has not run on PostgreSQL in these tests.
"""
import hashlib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import inspect  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402
import player_cards as pc  # noqa: E402
import steamid64  # noqa: E402
from steamid64_pg_parity import VECTORS  # noqa: E402
from test_player_cards_server import MAIN_PY, Scripted, _Res, _Rng, _due_row, _main_code, _member, _run  # noqa: E402

SQL320 = Path(HERE).parent / "sql" / "320_player_cards_no_steam_no_card.sql"

STEAM_SUBJECT = UUID("11111111-1111-1111-1111-111111111111")
OTHER_SUBJECT = UUID("22222222-2222-2222-2222-222222222222")
OWNER = UUID("99999999-9999-9999-9999-999999999999")
# a subject whose id is 7656119 followed by ten Arabic-Indic digits (test_steamid64_consumers.py's ARABIC_TAIL):
# seventeen characters that str.isdigit() accepts and int() reads as the SteamID64 subject's own id, and that the
# rule refuses, since its digits are [0-9] only. It is the one swept id the parity vectors do not carry -- theirs
# is Arabic-Indic throughout, so a rule reading the 7656119 prefix refuses that one and admits this one.
ARABIC_TAIL_SUBJECT = UUID("88888888-8888-8888-8888-888888888888")
# A perfectly good SteamID64 belonging to a registered player who has never run the mod: the OTHER half
# of the merged pool word (_PC_POOL_RULE = 3). It is what separates "carries the Steam id rule" from
# "carries the pool word" -- 3692 of the 4165 members the id rule alone admits are exactly this player.
MOD_UNSEEN_SUBJECT = UUID("77777777-7777-7777-7777-777777777777")
PLAYERS = {
    str(STEAM_SUBJECT): {"steam_id": "76561198040410653", "deleted": False, "banned": False, "announce": True, "mod_seen": True},
    str(OTHER_SUBJECT): {"steam_id": "2535425419861127", "deleted": False, "banned": False, "announce": True, "mod_seen": True},   # another platform's id
    str(MOD_UNSEEN_SUBJECT): {"steam_id": "76561198000000042", "deleted": False, "banned": False, "announce": True, "mod_seen": False},
    str(OWNER): {"steam_id": "76561197960265729", "deleted": False, "banned": False, "announce": True, "mod_seen": True},
    str(ARABIC_TAIL_SUBJECT): {"steam_id": "7656119" + "\u0668\u0660\u0664\u0660\u0664\u0661\u0660\u0666\u0665\u0663",
                               "deleted": False, "banned": False, "announce": True, "mod_seen": True},
}
# The acquisition is swept over the ids the validator and PostgreSQL are themselves held to: every spelling in
# steamid64_pg_parity's VECTORS gets a subject of its own, in VECTORS' order -- 22 the rule refuses, 5 it admits.
# A hand-picked few separate the shared rule only from the near-misses someone thought of; these carry the leading
# zero, the terminal newline and the Arabic-Indic seventeen as well, which is what closes the class. Separately
# from those three, five of the refused spellings are seventeen ASCII digits (two behind the 7656119 prefix)
# that fail the rule on its interval alone. So a form-only check admits all five and an interval-only check
# admits each of the three, and the sweep carries both kinds -- where a hand-picked list carries whichever
# near-misses its author thought of.
_VECTOR_SUBJECTS = tuple(UUID("aaaaaaaa-0000-0000-0000-%012d" % i) for i in range(len(VECTORS)))
PLAYERS.update({str(s): {"steam_id": spelling, "deleted": False, "banned": False, "announce": True, "mod_seen": True}
                for s, (spelling, _) in zip(_VECTOR_SUBJECTS, VECTORS)})
REFUSED_SUBJECTS = tuple(s for s, (_, admitted) in zip(_VECTOR_SUBJECTS, VECTORS) if not admitted)
ADMITTED_SUBJECTS = tuple(s for s, (_, admitted) in zip(_VECTOR_SUBJECTS, VECTORS) if admitted)
NOW = datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc)

# ── the clauses a statement carries, evaluated from its text ─────────────────

_BAN_CLAUSE = main._PC_NOT_BANNED_SQL.format(a="p")
_LIVE_PREFIX = "SELECT 1 FROM players p WHERE p.id = CAST(:pid AS uuid)"


def _admits(sql, row, alias="p"):
    """What a statement's WHERE says of one players row under `alias`, from the
    clauses its text carries for that alias: deleted_at IS NULL, mod_seen_at IS
    NOT NULL, pc_announce, the ban NOT EXISTS, and each Steam id clause (its
    pattern searched as PostgreSQL's ~ does, then its bounds).

    mod_seen_at is here because the 2026-09-15 merge put it in the pool word:
    an evaluator one clause short reads the whole word and silently ignores the
    half of it that removes seven eighths of the pool, so every reader would
    have looked correct while carrying only the other half (which is the defect
    the face preview actually had). Every row must therefore carry `mod_seen` --
    a KeyError here is the fixture's bug, not a reason for a default."""
    a = re.escape(alias)
    if re.search(r"(?<![\w.])" + a + r"\.deleted_at IS NULL", sql) and row["deleted"]:
        return False
    if re.search(r"(?<![\w.])" + a + r"\.mod_seen_at IS NOT NULL", sql) and not row["mod_seen"]:
        return False
    if re.search(r"(?<![\w.])" + a + r"\.pc_announce\b", sql) and not row["announce"]:
        return False
    if main._PC_NOT_BANNED_SQL.format(a=alias) in sql and row["banned"]:
        return False
    clause = (r"\(CASE WHEN " + a + r"\.steam_id ~ '([^']*)' THEN CAST\(" + a + r"\.steam_id AS bigint\) "
              r"BETWEEN (\d+) AND (\d+) ELSE false END\)")
    for pattern, lo, hi in re.findall(clause, sql):
        sid = row["steam_id"]
        if re.search(pattern, sid) is None or not int(lo) <= int(sid) <= int(hi):
            return False
    return True


class _PoolSession:
    """One snapshot's members by band and the players they name: answers the
    roll's four statements (band sizes, the member at an offset, the subject
    hold, the live check) and records every live check it answered."""

    def __init__(self, bands):
        self.bands = bands
        self.checked = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if "GROUP BY rarity" in sql:
            return _Res([{"rarity": r, "n": len(m)} for r, m in self.bands.items()])
        if sql.startswith("SELECT m.player_id, m.pool_rank"):
            members = self.bands.get(params["rarity"], [])
            k = int(params["k"])
            return _Res(members[k:k + 1])
        if "pg_try_advisory_xact_lock_shared" in sql:
            return _Res([{"held": True}])
        if sql.startswith(_LIVE_PREFIX):
            ok = _admits(sql, PLAYERS[params["pid"]])
            self.checked.append((params["pid"], ok))
            return _Res([{"x": 1}] if ok else [])
        raise AssertionError("unexpected statement: " + sql[:120])


def test_a_non_steam_member_of_an_older_snapshot_is_rerolled_and_never_dealt():
    # An older snapshot's Common band: the non-SteamID64 member first, then a Steam one.
    db = _PoolSession({"common": [_member(OTHER_SUBJECT, 41, "common"), _member(STEAM_SUBJECT, 42, "common")]})
    # per print: two band rolls (both Common), then the foil and signed misses; the offsets alternate 0, 1
    prints, why = _run(main._pc_roll_prints(db, 7, OWNER, rng=_Rng([0.5, 0.5, 0.9, 0.9] * 5, [0, 1] * 5)))
    assert why is None and len(prints) == 5
    assert {p["player_id"] for p in prints} == {str(STEAM_SUBJECT)}
    assert db.checked == [(str(OTHER_SUBJECT), False), (str(STEAM_SUBJECT), True)] * 5
    # the evaluator is not what refuses: the pre-v4.13 text of the same check admits that member
    old = ("SELECT 1 FROM players p WHERE p.id = CAST(:pid AS uuid) AND p.deleted_at IS NULL AND " + _BAN_CLAUSE)
    assert _admits(old, PLAYERS[str(OTHER_SUBJECT)]) is True
    # re-rolls are not a bound: a band of such members alone exhausts them and the open is refused
    only = _PoolSession({"common": [_member(OTHER_SUBJECT, 41, "common")]})
    assert _run(main._pc_roll_prints(only, 7, OWNER, rng=_Rng([0.5], [0]))) == (None, "pool_changed")
    assert len(only.checked) == 1 + pc.PC_ECONOMY["reroll_attempts"]


def test_a_member_who_never_ran_the_mod_is_rerolled_like_one_the_id_rule_refuses():
    """The merged word is an INTERSECTION, so the open's live re-check refuses a
    member on either half of it. A snapshot an older api took can hold a
    registered player who never ran the mod -- 3692 of the 4165 members the id
    rule alone admits are exactly that -- and the roll treats them as it treats
    a non-SteamID64 member: re-rolled, never dealt."""
    db = _PoolSession({"common": [_member(MOD_UNSEEN_SUBJECT, 41, "common"), _member(STEAM_SUBJECT, 42, "common")]})
    prints, why = _run(main._pc_roll_prints(db, 7, OWNER, rng=_Rng([0.5, 0.5, 0.9, 0.9] * 5, [0, 1] * 5)))
    assert why is None and len(prints) == 5
    assert {p["player_id"] for p in prints} == {str(STEAM_SUBJECT)}
    assert db.checked == [(str(MOD_UNSEEN_SUBJECT), False), (str(STEAM_SUBJECT), True)] * 5
    # the evaluator is not what refuses (#391): the PRE-MERGE text of the same check --
    # the id rule without the mod-runner clause -- admits that member
    pre_merge = (_LIVE_PREFIX + " AND p.deleted_at IS NULL AND " + main._PC_POOL_STEAM_ID_SQL
                 + " AND " + _BAN_CLAUSE)
    assert _admits(pre_merge, PLAYERS[str(MOD_UNSEEN_SUBJECT)]) is True


class _SummarySession:
    """Answers /pc/pool's two reads: the latest snapshot, then the live CTE,
    whose WHERE is evaluated from its own text over the snapshot's members;
    the band and top rows are what the statement's UNION returns for them."""

    def __init__(self, members):
        self.members = members   # [(player id, pool_rank, rarity)]
        self.live = None

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if "FROM pc_pool_snapshots ORDER BY id DESC" in sql:
            return _Res([{"id": 7, "taken_at": NOW, "member_count": len(self.members)}])
        if sql.startswith("WITH live AS"):
            live = [m for m in self.members if _admits(sql, PLAYERS[str(m[0])])]
            self.live = [str(pid) for pid, _rank, _rarity in live]
            rows = [{"kind": "band", "rarity": rarity, "n": sum(1 for m in live if m[2] == rarity),
                     "pool_rank": None, "board_rank": None, "rating": None, "display_name": None}
                    for rarity in sorted({m[2] for m in live})]
            rows += [{"kind": "top", "rarity": rarity, "n": None, "pool_rank": rank, "board_rank": rank,
                      "rating": 1700.0, "display_name": "Player %d" % rank}
                     for _pid, rank, rarity in live if rank <= int(params["top"])]
            return _Res(rows)
        raise AssertionError("unexpected statement: " + sql[:120])


def test_the_pool_summary_leaves_out_a_non_steam_member():
    # a snapshot an older api took: the non-SteamID64 member at rank 1, a SteamID64 one at rank 2, both Common
    db = _SummarySession([(OTHER_SUBJECT, 1, "common"), (STEAM_SUBJECT, 2, "common")])
    ans = _run(main.pc_pool_summary(db=db))
    assert db.live == [str(STEAM_SUBJECT)]
    assert ans["snapshot"]["member_count"] == 1 and ans["bands"]["common"] == 1
    assert [t["pool_rank"] for t in ans["top"]] == [2]   # counted nowhere, named nowhere
    # the evaluator is not what refuses: the pre-v4.13 text of the same WHERE admits that member
    old = "WHERE m.snapshot_id = CAST(:sid AS integer) AND p.deleted_at IS NULL AND " + _BAN_CLAUSE
    assert _admits(old, PLAYERS[str(OTHER_SUBJECT)]) is True


class _CardSession:
    """Answers the bot's /card: the member read, whose WHERE is evaluated from
    its own text for the subject, then the circulation count."""

    def __init__(self):
        self.circulation_reads = 0

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if "FROM pc_pool_members m JOIN pc_pool_snapshots s" in sql:
            if not _admits(sql, PLAYERS[params["pid"]]):
                return _Res([])
            return _Res([dict(_member(params["pid"], 12, "rare"), taken_at=NOW, snapshot_id=7)])
        if "FROM pc_prints pr JOIN pc_cards c" in sql:
            self.circulation_reads += 1
            return _Res([{"prints": 2, "holders": 1, "foil": 0, "signed": 0}])
        raise AssertionError("unexpected statement: " + sql[:120])


def test_card_answers_not_in_pool_for_a_non_steam_subject(monkeypatch):
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    linked = {"d-steam": STEAM_SUBJECT, "d-other": OTHER_SUBJECT}

    async def _by_discord(_db, discord_id):
        return SimpleNamespace(id=linked[discord_id], display_name="Linked player", deleted_at=None)

    monkeypatch.setattr(main, "_pc_player_by_discord", _by_discord)
    db = _CardSession()
    with pytest.raises(HTTPException) as ex:
        _run(main.internal_pc_card(discord_id="d-other", x_internal_key="k", db=db))
    assert ex.value.status_code == 404 and ex.value.detail == {"error": "not_in_pool"}
    assert db.circulation_reads == 0
    card = _run(main.internal_pc_card(discord_id="d-steam", x_internal_key="k", db=db))
    assert card["player_ref"] == str(STEAM_SUBJECT) and card["pool_rank"] == 12 and card["rarity"] == "rare"
    assert db.circulation_reads == 1 and card["in_circulation"]["prints"] == 2


class _PreviewSession:
    """Answers the face preview's subject read from the pool clauses its text
    carries (a row, or none), and counts the member reads after it."""

    def __init__(self, row):
        self.row = row
        self.member_reads = 0

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if "AS subject_banned" in sql:
            if not _admits(sql, self.row):
                return _Res([])
            return _Res([{"display_name": "Sid", "subject_deleted": False, "subject_banned": False}])
        if "FROM pc_pool_members m" in sql:
            self.member_reads += 1
            return _Res([])
        raise AssertionError("unexpected statement: " + sql[:120])


def test_the_face_preview_refuses_a_subject_the_pool_word_refuses_before_the_member_read(monkeypatch):
    """The preview answers not_in_pool, so it decides membership, so it carries
    the WHOLE pool word -- not the Steam half of it.

    It carried `_PC_POOL_STEAM_ID_SQL` alone until 2026-09-15 (found in the
    coherence review of the merge): the id rule admits 4165 players where the
    merged word admits 473, so a subject who has never run the mod reached the
    member read and was answered as a pool member for as long as an older
    snapshot still held their row."""
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    monkeypatch.setattr(main, "_pc_require_renderer", lambda: None)

    async def _prime(_ids):
        return None

    monkeypatch.setattr(main, "_pc_steam_prime", _prime)
    for pid, reads in ((OTHER_SUBJECT, 0), (MOD_UNSEEN_SUBJECT, 0), (STEAM_SUBJECT, 1)):
        db = _PreviewSession(PLAYERS[str(pid)])
        with pytest.raises(HTTPException) as ex:
            _run(main.internal_pc_face_preview(player_ref=str(pid), locale="en", x_internal_key="k", db=db))
        assert ex.value.status_code == 404 and ex.value.detail == {"error": "not_in_pool"}
        # a subject the word refuses -- no SteamID64, or never ran the mod -- stops at the gate,
        # pinned snapshot or not; a member reaches the member read (answered empty here, hence its 404)
        assert db.member_reads == reads, pid


def test_one_pool_word_carries_the_steam_id_rule_for_every_membership_reader():
    rule = steamid64.individual_id_sql("p.steam_id")
    assert main._PC_POOL_STEAM_ID_SQL == rule
    word = main._PC_POOL_MEMBER_SQL
    assert word.startswith("(") and word.endswith(")")
    assert word.count(rule) == 1 and word.count("p.deleted_at IS NULL") == 1
    assert word.count(_BAN_CLAUSE) == 1
    snap = main._PC_SNAPSHOT_SELECT_SQL
    pool = snap[snap.index("WITH pool AS ("):snap.index("series AS (")]
    assert pool.count("WHERE " + word) == 1 and snap.count(word) == 1
    # board_rank stays the leaderboard's own rank, over the leaderboard's own rows
    board = snap[snap.index("board AS ("):snap.index("SELECT pool.player_id")]
    assert rule not in board
    live = " ".join(main._PC_LIVE_POOL_CHECK_SQL.split())
    assert live == " ".join((_LIVE_PREFIX + " AND " + word).split())
    # Every reader that DECIDES membership -- answers not_in_pool, or leaves a
    # member out -- carries the one word, in whatever quoting its own statement is
    # built from. The face preview is in this tuple because it is the reader that
    # drifted: it carried the id clause alone until 2026-09-15.
    for fn in (main.pc_pool_summary, main.internal_pc_card, main.internal_pc_face_preview):
        src = inspect.getsource(fn)
        assert len(re.findall(r'AND (?:"""|") \+ _PC_POOL_MEMBER_SQL', src)) == 1, fn.__name__
        assert "_PC_NOT_BANNED_SQL" not in src and "p.deleted_at IS NULL" not in src, fn.__name__
    # ...and no reader anywhere tests the id clause on its own, which is a property
    # of the MODULE rather than of a tuple someone remembered to extend. The id
    # clause exists to be part of the word, so the counts below enumerate the
    # spellings a site can reach it by: the constant, the qualified call, and the
    # bare call under any import form.
    #
    # Only the constant's count was pinned until 2026-09-15 (coherence r3), and
    # that is not the class the comment claimed. main.py reaches the same rule
    # four more times through _sid64.individual_id_sql(...), so a seventh
    # membership reader written as
    #     "... WHERE p.id = CAST(:pid AS uuid) AND " + _sid64.individual_id_sql("p.steam_id")
    # decides membership on the id half alone and adds NOTHING to the constant's
    # count, so the guard that stood here could not see it; the same reader
    # spelled with the constant went red at once.
    #
    # A THIRD spelling was demonstrated on 2026-09-16 and evaded both of those:
    # `from steamid64 import individual_id_sql` followed by a BARE
    # `individual_id_sql("p.steam_id")` leaves the constant at 2, the qualified
    # call at 4 and the hand-copied CASE at 1, all unmoved. The bare count is
    # what closes it, and it is measurable rather than asserted: main.py reaches
    # the rule only through `_sid64.`, so in comment-stripped source the bare
    # count equals the qualified one -- 4 as measured here on 2026-09-16, a
    # number re-derived rather than carried over from a brief. Any new site
    # moves it, under any import form and any alias.
    code = _main_code()
    assert code.count("_PC_POOL_STEAM_ID_SQL") == 2, "the pool's id clause decides membership somewhere on its own"
    # The four calls, by the alias each reads -- the events word's subject (su),
    # the bot's face row (s), the Steam sweep's eligibility and the delivery
    # lease's subject (p). None of them decides POOL membership: they gate a
    # Discord handout, a picture read, whom the sweep may ask Steam about, and
    # whether a lease's subject still has an id. A fifth call moves the total
    # even under an alias nobody listed here.
    assert code.count('_sid64.individual_id_sql("p.steam_id")') == 2
    assert code.count('_sid64.individual_id_sql("s.steam_id")') == 1
    assert code.count('_sid64.individual_id_sql("su.steam_id")') == 1
    assert code.count("_sid64.individual_id_sql(") == 4, "a new site spells the id rule under some other alias"
    # the bare call, which the two counts above cannot see: equal to the
    # qualified count exactly while every reach goes through `_sid64.`
    assert code.count("individual_id_sql(") == 4, \
        "a site reaches the id rule through a bare individual_id_sql(...) -- a `from steamid64 import` form"
    # ...and nothing hand-copies the rule PAST both names: its text exists once,
    # in the constant above, and so do the interval's two edges.
    assert code.count("CASE WHEN p.steam_id") == 1
    for edge in ("76561197960265728", "76561202255233023"):
        assert code.count(edge) == 1, edge


# The pool word this build carries, and the rule number that stands for it.
# pc_pool_snapshots.rule records which WORD a snapshot was taken under, so the two
# are one fact kept in two places; the test below holds them together.
_POOL_WORD_RULE = 3
_POOL_WORD_SHA = "8c4a06b4101e8c2bc89f76dfaa5d90cfa28c2132e5cbf66bb01ccdc86b8f73fd"


def test_the_rule_number_and_the_membership_word_cannot_move_without_each_other():
    """The versioned retake rests on one sentence -- "bump _PC_POOL_RULE with
    every change to the membership text" -- and until now nothing enforced it.
    Main's old mechanism scanned the latest snapshot's MEMBERS, so it needed no
    bump: it read the data. The replacement is more general and strictly less
    automatic. Demonstrated on a private mirror, 2026-09-15: one more clause in
    _PC_POOL_MEMBER_SQL with the constant left at 3, and 214 Player Cards tests
    passed green while the pool would have kept serving yesterday's members.

    So the pair is pinned, and either half moving alone fails here. The rule
    number is also a STAMP -- the column holds the number and nothing else --
    so its two decoders, main.py's enumeration and migration 316's header, are
    required to list the rule this build writes."""
    word = " ".join(main._PC_POOL_MEMBER_SQL.split())
    sha = hashlib.sha256(word.encode("utf-8")).hexdigest()
    assert (main._PC_POOL_RULE, sha) == (_POOL_WORD_RULE, _POOL_WORD_SHA), (
        "The pool's membership word and its rule number are ONE fact and one of them moved alone.\n"
        "  word now:      " + word + "\n"
        "  sha256 now:    " + sha + "   (pinned " + _POOL_WORD_SHA + ")\n"
        "  _PC_POOL_RULE: " + str(main._PC_POOL_RULE) + "   (pinned " + str(_POOL_WORD_RULE) + ")\n"
        "If you changed the word: BUMP main._PC_POOL_RULE, add the new rule to its enumeration in\n"
        "main.py and to backend/sql/316_pc_pool_snapshot_rule.sql's header, then update both\n"
        "constants above. Without the bump nothing is retaken -- _pc_snapshot_due compares the\n"
        "latest snapshot's recorded rule against this constant -- so the pool keeps serving the\n"
        "members the new word refuses until 00:05 UTC, and every open that rolls one of them is\n"
        "re-rolled or refused pool_changed.")
    # Both decoders must define EVERY rule up to the one this build stamps -- the
    # column holds old numbers too, and a list with a gap decodes none of them.
    # Pinned on the enumeration's own line shape, not on the number appearing
    # somewhere in the prose: 316's header names rule 3 in a sentence as well,
    # so a looser check passed the mutation that removed the entry (2026-09-15).
    enumeration = MAIN_PY.read_text(encoding="utf-8")
    sql316 = (Path(HERE).parent / "sql" / "316_pc_pool_snapshot_rule.sql").read_text(encoding="utf-8")
    for r in range(1, main._PC_POOL_RULE + 1):
        assert ("#   %d  " % r) in enumeration, "main.py's enumeration does not define rule %d" % r
        assert ("-- Rule %d (" % r) in sql316, "migration 316's header does not define rule %d" % r


def test_a_snapshot_holding_a_non_steam_member_is_retaken_at_the_next_pass(monkeypatch):
    """The SAME property as before the 2026-09-15 merge, through the mechanism
    the merge kept: the pool rule is VERSIONED (pc_pool_snapshots.rule,
    migration 316) instead of the latest snapshot being scanned for a member
    the Steam id rule refuses.

    A snapshot can hold a non-SteamID64 member only if an api took it under a
    pool word without the Steam id clause -- the select this api runs cannot
    admit one -- and every such api recorded a LOWER rule than this one, since
    the rule is bumped with every change to the membership text. So 'a snapshot
    holding a non-Steam member is retaken' is exactly 'a snapshot taken under
    an older rule is retaken', and the versioned form also catches rule changes
    the members scan never could."""
    today = datetime(2026, 9, 15, 0, 5, tzinfo=timezone.utc)
    # rule 3 IS the one that added the Steam id clause (the merge), so a
    # snapshot recorded at rule 2 is one an api without that clause took.
    assert main._PC_POOL_RULE == 3 and main._PC_POOL_STEAM_ID_SQL in main._PC_POOL_MEMBER_SQL
    pre_steam = main._PC_POOL_RULE - 1
    # read before the monkeypatch below replaces the taker: the retake CLEARS
    # the condition rather than firing every pass, because the taker writes
    # this build's rule onto the snapshot it just took
    taker = " ".join(inspect.getsource(main._pc_take_snapshot).split())
    assert ('"INSERT INTO pc_pool_snapshots (member_count, rule) " '
            '"VALUES (CAST(:n AS integer), CAST(:rule AS integer)) RETURNING id"') in taker
    assert '{"n": len(rows), "rule": int(_PC_POOL_RULE)}' in taker

    def due(row):
        return _run(main._pc_snapshot_due(Scripted({"SELECT (SELECT MAX(taken_at)": [row]})))

    # the rule outranks the daily clock both ways: after today's snapshot, and before 00:05
    assert due(_due_row(today + timedelta(seconds=30), today + timedelta(hours=5), today, last_rule=pre_steam)) == "rule"
    assert due(_due_row(today - timedelta(days=1), today - timedelta(minutes=2), today, last_rule=pre_steam)) == "rule"
    # a snapshot the rule admits keeps the daily cadence, and no snapshot at all is still 'first'
    assert due(_due_row(today + timedelta(seconds=30), today + timedelta(hours=5), today)) is None
    assert due(_due_row(today - timedelta(days=1), today + timedelta(minutes=1), today)) == "daily"
    assert due(_due_row(None, today, today, last_rule=pre_steam)) == "first"
    # the janitor takes it, under its try-lock, with the due state re-read there (c3 F)
    db = Scripted({"SELECT (SELECT MAX(taken_at)": [
        _due_row(today + timedelta(seconds=30), today + timedelta(hours=5), today, last_rule=pre_steam)],
        "pg_try_advisory_xact_lock": [True]})
    monkeypatch.setattr(database, "async_session", lambda: db)
    taken = []

    async def _take(_db, *, reason):
        taken.append(reason)
        return {"snapshot_id": 5, "members": 1}

    monkeypatch.setattr(main, "_pc_take_snapshot", _take)
    _run(main._pc_snapshot_janitor_step())
    assert taken == ["rule"] and db.count("SELECT (SELECT MAX(taken_at)") == 2
    # the term reads the LATEST snapshot's own recorded rule and compares it to
    # this build's constant -- and the members scan it replaced is GONE, so the
    # retake cannot come back to depending on one rule change in particular
    read = " ".join(inspect.getsource(main._pc_snapshot_due).split())
    assert ('(SELECT rule FROM pc_pool_snapshots ORDER BY taken_at DESC, id DESC LIMIT 1) AS last_rule,') in read
    assert 'if int(due["last_rule"] or 0) < int(_PC_POOL_RULE): return "rule"' in read
    assert "pc_pool_members" not in read and "stale_rule" not in read
    assert read.index('return "first"') < read.index('return "rule"') < read.index('return "daily"')


def test_the_boot_self_test_explains_both_of_the_janitors_pool_reads():
    """The janitor's boot self-test (_janitor_sql_from_sources) resolves SQL
    statically and fails on a site it cannot resolve, so the pool's id clause
    is written out in main.py (pinned to steamid64's text above) rather than
    called, and both janitor reads of the pool are in the inventory the
    self-test EXPLAINs at boot.

    Since the 2026-09-15 merge the two reads carry different things: the
    snapshot's select carries the whole membership word, id clause and all,
    and the due read carries no membership text at all -- it asks the latest
    snapshot which RULE it was taken under (migration 316). Both still have to
    resolve statically, which is the property this test exists for."""
    inv = main._janitor_sql_inventory()
    assert inv["dynamic"] == [], inv["dynamic"]
    by_func = {}
    for s in inv["statements"]:
        by_func.setdefault(s["func"], []).append(" ".join(s["sql"].split()))
    rule = " ".join(steamid64.individual_id_sql("p.steam_id").split())
    word = " ".join(main._PC_POOL_MEMBER_SQL.split())
    assert rule in word
    # the snapshot's select: the word resolved down to the id clause's own text
    assert sum(("WHERE " + word + " ), series AS (") in q for q in by_func["_pc_take_snapshot"]) == 1
    # the writer half of the versioned rule is a janitor statement too
    assert sum("INSERT INTO pc_pool_snapshots (member_count, rule)" in q
               for q in by_func["_pc_take_snapshot"]) == 1
    # the due read: the rule column, and no membership predicate of its own --
    # a second copy of the word here is exactly the drift the one word prevents
    due = by_func["_pc_snapshot_due"]
    assert sum("(SELECT rule FROM pc_pool_snapshots ORDER BY taken_at DESC, id DESC LIMIT 1) AS last_rule" in q
               for q in due) == 1
    assert not any(rule in q or "pc_pool_members" in q for q in due)


def _deliverable(sql, event):
    return (_admits(sql, PLAYERS[event["player_id"]], "pl")
            and _admits(sql, PLAYERS[event["subject_player_id"]], "su"))


class _EventsSession:
    """The handout's two statements over unposted pc_events rows that name no
    print: the skip marks posted every event the word its text carries
    refuses, and the page hands out every unposted event the word admits --
    for the puller (pl) and the subject (su), each evaluated from the
    statement's own text."""

    def __init__(self, events):
        self.events = events
        self.steps = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if sql.startswith("UPDATE pc_events e SET posted_at = now()"):
            self.steps.append("skip")
            for e in self.events:
                if e["posted_at"] is None and not _deliverable(sql, e):
                    e["posted_at"] = NOW
            return _Res([])
        if sql.startswith("WITH page AS"):
            self.steps.append("page")
            return _Res([{"id": e["id"], "kind": "pull", "created_at": NOW, "print_id": None,
                          "puller_name": "Puller", "puller_ref": e["player_id"],
                          "subject_name": "Subject", "subject_ref": e["subject_player_id"], "dup_at_pull": None,
                          "rarity": None, "foil": None, "signed": None, "pool_rank": None, "rating": None,
                          "title": None, "face_ready": True}
                         for e in self.events if e["posted_at"] is None and _deliverable(sql, e)])
        raise AssertionError("unexpected statement: " + sql[:120])

    async def commit(self):
        self.steps.append("commit")


def test_a_pending_pull_of_a_non_steam_subject_is_marked_posted_and_never_handed_out(monkeypatch):
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    events = [{"id": 1, "player_id": str(OWNER), "subject_player_id": str(OTHER_SUBJECT), "posted_at": None},
              {"id": 2, "player_id": str(OWNER), "subject_player_id": str(STEAM_SUBJECT), "posted_at": None}]
    db = _EventsSession(events)
    ans = _run(main.internal_pc_events_pending(x_internal_key="k", db=db))
    assert [e["id"] for e in ans["events"]] == [2]
    assert events[0]["posted_at"] == NOW and events[1]["posted_at"] is None
    # the skip is committed before the page is read, so such a pull never waits in the hold
    assert db.steps == ["skip", "commit", "page"]
    # the evaluator is not what refuses: without the id term the same skip leaves that pull to be sent
    term = steamid64.individual_id_sql("su.steam_id")
    skip = " ".join(main._PC_EVENTS_SKIP_SQL.split())
    old = " ".join(main._PC_EVENTS_SKIP_SQL.replace("AND " + term, "").split())
    assert old != skip and _deliverable(old, events[0]) is True and _deliverable(skip, events[0]) is False
    # one word at all three moments: the skip, the handout's selection, the lease re-check before a send
    assert main._PC_EVENT_DELIVERABLE_SQL.count(term) == 1
    for sql in (main._PC_EVENTS_SKIP_SQL, main._PC_EVENTS_PENDING_SQL, main._PC_LEASE_EVENTS_OK):
        assert sql.count(main._PC_EVENT_DELIVERABLE_SQL) == 1 and sql.count(term) == 1


# ── the delivery lease and the bot's picture source (review r15) ────────────

PRINT = UUID("33333333-3333-3333-3333-333333333333")
LEASE = UUID("44444444-4444-4444-4444-444444444444")
# the lease shapes the bot takes: a print alone, none (the /card lease), events alone, a print and events
LEASE_SHAPES = ({"print_id": str(PRINT)}, {}, {"event_ids": [7]}, {"print_id": str(PRINT), "event_ids": [7]})


def _lease_session(subject):
    """The acquisition's statements for `subject`: the subject's live steam_id first; after it, what an
    acquisition that goes through reads -- the identity try-lock taken, the subject live with a picture, the
    print depicting the subject, event 7 resolving with OWNER as its puller and `subject` as its subject, OWNER's
    shared try-lock taken, the lease row written."""
    return Scripted({
        "SELECT steam_id FROM players": [[{"steam_id": PLAYERS[str(subject)]["steam_id"]}]],
        "pg_try_advisory_xact_lock_shared": [[{"held": True}]],
        "pg_try_advisory_xact_lock": [[{"got": True}]],
        "AS subject_banned": [[{"subject_deleted": False, "portrait_hash": "ef" * 32, "subject_banned": False}]],
        "FROM pc_prints pr JOIN pc_cards c": [[{"one": 1}]],
        "SELECT e.id, pl.steam_id AS puller": [[{"id": 7, "puller": PLAYERS[str(OWNER)]["steam_id"],
                                                 "subject": PLAYERS[str(subject)]["steam_id"]}]],
        "INSERT INTO pc_delivery_leases": [[{"id": LEASE, "until": NOW + timedelta(seconds=60)}]],
    })


def test_a_lease_on_a_non_steam_subject_is_refused_before_the_identity_lock_whatever_it_names(monkeypatch):
    """The acquisition refuses a subject whose id is not a SteamID64 with the answer it gives a missing subject
    (404 not_found), for every lease shape, after its one read of the subject's id: no identity lock, no other
    statement, no commit. The subjects refused are not a hand-picked few: they are every one of the parity
    vectors' 22 refused spellings, plus the mixed Arabic-Indic tail those vectors do not carry -- other platforms'
    ids, five that fail the rule only on its interval (two behind the 7656119 prefix), and the three that separate
    the rule from a near-miss of itself: the Arabic-Indic seventeen (str.isdigit() and int() read it as this very
    SteamID64), the leading zero (eighteen ASCII digits int() reads as one), and the terminal newline (re's "$"
    matches before it). So a rule that reads the form or a prefix alone, the interval through str.isdigit() and
    int(), or one that drops the length or anchors with "$", admits one of these. The same leases on each admitted
    spelling are written, the first lock on the subject's id."""
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    assert (len(REFUSED_SUBJECTS), len(ADMITTED_SUBJECTS)) == (22, 5)
    swept = REFUSED_SUBJECTS + (ARABIC_TAIL_SUBJECT,)
    refused = [PLAYERS[str(s)]["steam_id"] for s in swept]
    for sid in refused:
        assert steamid64.is_individual_id(sid) is False, ascii(sid)
    for subject in ADMITTED_SUBJECTS:
        assert steamid64.is_individual_id(PLAYERS[str(subject)]["steam_id"]) is True, subject
    steam = PLAYERS[str(STEAM_SUBJECT)]["steam_id"]
    assert PLAYERS[str(OTHER_SUBJECT)]["steam_id"] in refused
    # the three spellings that separate the shared rule from a near-miss of it, each swept exactly once
    vtail = "\u0667\u0666\u0665\u0666\u0661\u0661\u0669\u0668\u0660\u0664\u0660\u0664\u0661\u0660\u0666\u0665\u0663"
    assert len(vtail) == 17 and vtail.isdigit() and not vtail.isascii() and int(vtail) == int(steam), ascii(vtail)
    assert ("0" + steam).isascii() and ("0" + steam).isdigit() and int("0" + steam) == int(steam)
    assert re.match(r"[0-9]{17}$", steam + "\n") is not None
    assert [refused.count(s) for s in (vtail, "0" + steam, steam + "\n")] == [1, 1, 1]
    tail = PLAYERS[str(ARABIC_TAIL_SUBJECT)]["steam_id"]
    assert len(tail) == 17 and tail.isdigit() and not tail.isascii() and int(tail) == int(steam), ascii(tail)
    # the ids that fail the rule only on its interval, the prefix no defence
    interval = [s for s in refused if len(s) == 17 and s.isascii() and s.isdigit()]
    assert len(interval) == 5 and sum(s.startswith("7656119") for s in interval) == 2
    for sid in interval:
        assert not steamid64.INDIVIDUAL_MIN <= int(sid) <= steamid64.INDIVIDUAL_MAX, sid
    for shape in LEASE_SHAPES:
        for subject in swept:
            db = _lease_session(subject)
            with pytest.raises(HTTPException) as ex:
                _run(main.internal_pc_lease({"subject_ref": str(subject), **shape}, "k", db))
            assert (ex.value.status_code, ex.value.detail) == (404, {"error": "not_found"}), (shape, subject)
            assert len(db.log) == 1 and db.log[0][0].startswith("SELECT steam_id FROM players WHERE id ="), (
                shape, subject, db.log)
            assert db.committed == 0, (shape, subject)
        for subject in ADMITTED_SUBJECTS:
            sid = PLAYERS[str(subject)]["steam_id"]
            db = _lease_session(subject)
            ans = _run(main.internal_pc_lease({"subject_ref": str(subject), **shape}, "k", db))
            assert ans["lease_id"] == str(LEASE) and db.count("INSERT INTO pc_delivery_leases") == 1, (shape, sid)
            assert db.log[1] == ("SELECT pg_try_advisory_xact_lock(hashtext(CAST(:sid AS text)))", {"sid": sid})
            assert db.committed == 1, (shape, sid)


_SUBJECT_ID_OK = re.compile(r"\(CASE WHEN p\.steam_id ~ '([^']*)' THEN CAST\(p\.steam_id AS bigint\) "
                            r"BETWEEN (\d+) AND (\d+) ELSE false END\) AS subject_id_ok")


class _LeaseCheckSession:
    """The re-check's one statement for a lease on `subject`: every column answers as for a lease that still
    authorises its picture (the print and events words true, as for a bare lease), except subject_id_ok, which is
    evaluated from the id clause the statement's text carries under that name (no such clause: no such column)."""

    def __init__(self, subject):
        self.subject = subject
        self.log = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.log.append(sql)
        assert "FROM pc_delivery_leases l JOIN players p ON p.id = l.subject_id" in sql, sql[:120]
        row = {"until": NOW, "unexpired": True, "leased_hash": "ef" * 32, "print_deliverable": True,
               "subject_deleted": False, "portrait_hash": "ef" * 32, "subject_banned": False, "events_ok": True}
        for pattern, lo, hi in _SUBJECT_ID_OK.findall(sql):
            sid = PLAYERS[str(self.subject)]["steam_id"]
            row["subject_id_ok"] = re.search(pattern, sid) is not None and int(lo) <= int(sid) <= int(hi)
        return _Res([row])


def test_the_lease_re_check_withdraws_a_lease_on_a_subject_whose_id_is_not_a_steam_id(monkeypatch):
    """The re-check right before the bot's send reads the subject's id rule again, in its one statement, for every
    lease, and answers 404 lease_gone for a subject whose id is not a SteamID64 -- whatever the lease names, since
    its print and events words answer true here. The same lease on a SteamID64 subject is live."""
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    db = _LeaseCheckSession(OTHER_SUBJECT)
    with pytest.raises(HTTPException) as ex:
        _run(main.internal_pc_lease_check(str(LEASE), "k", db))
    assert (ex.value.status_code, ex.value.detail) == (404, {"error": "lease_gone"}) and len(db.log) == 1
    db = _LeaseCheckSession(STEAM_SUBJECT)
    assert _run(main.internal_pc_lease_check(str(LEASE), "k", db)) == {
        "lease_id": str(LEASE), "until": NOW.isoformat(), "live": True}
    # the column is steamid64's text on the lease's subject row, once in the statement
    assert len(_SUBJECT_ID_OK.findall(db.log[0])) == 1
    assert main._PC_LEASE_SUBJECT_ID_OK.count(steamid64.individual_id_sql("p.steam_id")) == 1


class _FaceSession:
    """The face row read for PRINT, a live print of `subject`: the row, unless the statement's text carries an id
    clause on the subject row `s` that the subject's id fails."""

    def __init__(self, subject):
        self.subject = subject
        self.log = []

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.log.append(sql)
        assert "FROM pc_prints pr JOIN pc_cards c ON c.id = pr.card_id JOIN players s ON s.id = c.subject_player_id" in sql
        if not _admits(sql, PLAYERS[str(self.subject)], "s"):
            return _Res([])
        return _Res([{"print_id": str(PRINT), "subject_player_id": str(self.subject), "discarded_at": None}])


def test_the_bots_picture_source_answers_404_for_a_print_of_a_non_steam_subject(monkeypatch):
    """/internal/pc/face/print reads the print's face row with the subject's id rule added, so a live print of a
    subject whose id is not a SteamID64 answers 404 before any render, and a SteamID64 subject's print renders.
    The public face route keeps its read without the rule (_pc_face_row): the same row still answers there."""
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    monkeypatch.setattr(main, "_pc_require_renderer", lambda: None)
    monkeypatch.setattr(main, "_pc_served_locales", lambda: set())
    rendered = []

    async def ctx(_db, locale):
        return {"locale": locale}

    async def render(_db, row, _ctx, size, want=None):
        rendered.append(row["subject_player_id"])
        return "f" * 16, b"\x89PNG"

    monkeypatch.setattr(main, "_pc_face_ctx", ctx)
    monkeypatch.setattr(main, "_pc_render_face", render)
    db = _FaceSession(OTHER_SUBJECT)
    with pytest.raises(HTTPException) as ex:
        _run(main.internal_pc_face_print(str(PRINT), "en", "card", "k", db))
    assert ex.value.status_code == 404 and rendered == [] and len(db.log) == 1
    resp = _run(main.internal_pc_face_print(str(PRINT), "en", "card", "k", _FaceSession(STEAM_SUBJECT)))
    assert resp.headers["x-face-rev"] == "f" * 16 and rendered == [str(STEAM_SUBJECT)]
    assert _run(main._pc_face_row(_FaceSession(OTHER_SUBJECT), str(PRINT))) is not None
    assert "row = await _pc_face_row(db, print_id)" in inspect.getsource(main.pc_face_png)
    assert main._PC_FACE_SUBJECT_ID_SQL == steamid64.individual_id_sql("s.steam_id")


# ── migration 320 ────────────────────────────────────────────────────────────

RULE_S = "NOT " + steamid64.individual_id_sql("s.steam_id")
SHARDS_CASE = "CASE pr.rarity " + " ".join("WHEN '%s' THEN %d" % (r, pc.shards_for(r)) for r in pc.RARITIES) + " END"


def _flat320():
    """The file without its -- comments, whitespace collapsed."""
    raw = SQL320.read_text(encoding="utf-8").replace("\r\n", "\n")
    return " ".join("\n".join(line.split("--", 1)[0] for line in raw.split("\n")).split())


def _body320(flat):
    return flat[flat.index("DO $m320$"):flat.index("END $m320$;")]


def _span(body, start, end):
    """The one statement of the DO block that begins with `start`, through the first `end` after it."""
    assert body.count(start) == 1, (body.count(start), start)
    i = body.index(start)
    return body[i:body.index(end, i) + len(end)]


def test_migration_320_reads_first_creates_its_table_alone_then_retires_in_one_transaction():
    flat = _flat320()
    # two explicit transactions, because psql does not open one for a file (#340)
    assert flat.count("BEGIN;") == 2 and flat.count("COMMIT;") == 2 and flat.endswith("END $m320$; COMMIT;")
    first = flat.index("BEGIN;")
    first_end = flat.index("COMMIT;", first) + len("COMMIT;")
    second = flat.index("BEGIN;", first_end)
    # the first holds the record table alone, under the lock timeout: the lock its REFERENCES takes on
    # pc_prints ends at this COMMIT, before the retirement takes any lock
    tx1 = flat[first:first_end]
    assert tx1.startswith("BEGIN; SET LOCAL lock_timeout = '5s'; CREATE TABLE IF NOT EXISTS pc_print_retirements (")
    assert tx1.endswith(" ); COMMIT;") and tx1.count(";") == 4, tx1
    # the retirement: nothing between its BEGIN and the DO block but the timeout, and no DDL in it, so the
    # first locks it takes are the owners' (their order is pinned in the retirement test below)
    assert flat[second:flat.index("DO $m320$")] == "BEGIN; SET LOCAL lock_timeout = '5s'; "
    assert not re.search(r"\b(CREATE|ALTER|DROP|TRUNCATE|LOCK)\b", flat[second:]), flat[second:]
    head = flat[:first]
    # the dry run: one SELECT, before both transactions, that writes nothing and names every print the write retires
    assert head.startswith("SELECT pr.owner_player_id,") and head.count(";") == 1
    assert not re.search(r"\b(UPDATE|INSERT|DELETE|CREATE|ALTER|DROP)\b", head)
    assert ("SUM(" + SHARDS_CASE + ") AS shards_if_compensated") in head
    assert ("FROM pc_prints pr JOIN pc_cards c ON c.id = pr.card_id JOIN players s ON s.id = c.subject_player_id "
            "JOIN players o ON o.id = pr.owner_player_id WHERE pr.discarded_at IS NULL AND " + RULE_S +
            " GROUP BY pr.owner_player_id") in head
    # one rule wherever the file selects by it: the dry run, the owners' read, the retirement, the last check
    assert flat.count(RULE_S) == 4 and flat.count("~ '") == 4


def test_migration_320_pays_what_a_discard_pays_by_a_delta_under_one_switch():
    raw = SQL320.read_text(encoding="utf-8")
    switches = re.findall(r"v_compensation CONSTANT text := '([a-z_]+)';", raw)
    # one switch, holding Sid's decision (2026-09-15): A, the shards a discard pays
    assert switches == ["shards"], switches
    flat = _flat320()
    body = _body320(flat)
    assert flat.count(SHARDS_CASE) == 2    # the dry run and the retirement, both from PC_ECONOMY (#229)
    assert ("discard_shards = CASE WHEN v_compensation = 'shards' THEN " + SHARDS_CASE + " ELSE 0 END") in body
    # the switch is read where it is declared, by the payout, by the record and by the closing notice, and the block
    # raises in two places only (the shards check and the last check): no check on the switch's own value (r15 LOW 7)
    assert body.count("v_compensation") == 4 and body.count("RAISE EXCEPTION") == 2, (
        body.count("v_compensation"), body.count("RAISE EXCEPTION"))
    # the owner's balance moves by a delta (#326), and only by what the retirement returned
    assert body.count("pc_shards =") == 1
    assert ("UPDATE players o SET pc_shards = o.pc_shards + d.shards FROM (SELECT r.owner_player_id, "
            "CAST(SUM(r.discard_shards) AS integer) AS shards FROM retired r GROUP BY r.owner_player_id) d "
            "WHERE o.id = d.owner_player_id AND d.shards > 0 ), released AS (") in body


def test_migration_320_retires_live_prints_of_non_steam_subjects_through_the_discard_columns():
    flat = _flat320()
    body = _body320(flat)
    # the record goes with its print: the data deletion deletes prints, and a record must not refuse it
    assert ("CREATE TABLE IF NOT EXISTS pc_print_retirements ( print_id UUID PRIMARY KEY "
            "REFERENCES pc_prints(id) ON DELETE CASCADE,") in flat
    assert "compensation TEXT NOT NULL CHECK (compensation IN ('shards', 'none'))" in flat
    # the owners of the prints to retire, read once: each later statement reads a snapshot of its own, so the
    # locks, both balance readings and the retirement are restricted to this set; only the last check reads
    # beyond it
    owners = _span(body, "SELECT array_agg(DISTINCT pr.owner_player_id) INTO v_owner_ids", ";")
    assert owners == ("SELECT array_agg(DISTINCT pr.owner_player_id) INTO v_owner_ids FROM pc_prints pr JOIN pc_cards c "
                      "ON c.id = pr.card_id JOIN players s ON s.id = c.subject_player_id WHERE pr.discarded_at IS NULL "
                      "AND " + RULE_S + ";")
    # their locks in the discard route's order, the identity lock (shared) then the players row, and from
    # there v_owner_ids holds the ids of the rows locked. The identity locks are one statement per owner, all
    # before the first row lock, in sorted steam_id order under COLLATE "C": byte order, the order Python's
    # sorted() gives _mail_lock_identities and the api's other loops over several identity locks (#197). Taken
    # in the plan's scan order instead, the PostgreSQL 16 run (round 1) reproduced a lock-wait cycle between
    # this block and a writer taking two owners' identity locks exclusively in sorted order.
    ident = _span(body, "FOR v_sid IN SELECT o.steam_id", "END LOOP;")
    assert ident == ('FOR v_sid IN SELECT o.steam_id FROM players o WHERE o.id = ANY(v_owner_ids) '
                     'ORDER BY o.steam_id COLLATE "C" LOOP '
                     'PERFORM pg_advisory_xact_lock_shared(hashtext(CAST(v_sid AS text))); END LOOP;')
    assert body.count("pg_advisory_xact_lock") == 1 and body.count(" v_sid text;") == 1
    rows = _span(body, "SELECT array_agg(q.id) INTO v_owner_ids", ";")
    assert rows == ("SELECT array_agg(q.id) INTO v_owner_ids FROM (SELECT o.id FROM players o "
                    "WHERE o.id = ANY(v_owner_ids) ORDER BY o.id FOR NO KEY UPDATE OF o) q;")
    # SET names the two discard columns, which pc_prints_immutable freezes once discarded_at is set, and
    # nothing else; the WHERE retires only prints held by the owners whose rows are locked above
    retire = _span(body, "WITH retired AS (", "INTO v_retired, v_owners, v_leases, v_ids;")
    assert retire.startswith("WITH retired AS ( UPDATE pc_prints pr SET discarded_at = now(), discard_shards = CASE "
                             "WHEN v_compensation = 'shards' THEN " + SHARDS_CASE + " ELSE 0 END FROM pc_cards c, "
                             "players s WHERE c.id = pr.card_id AND s.id = c.subject_player_id AND "
                             "pr.discarded_at IS NULL AND " + RULE_S + " AND pr.owner_player_id = ANY(v_owner_ids) "
                             "RETURNING pr.id, pr.owner_player_id, pr.discard_shards ), recorded AS (")
    assert retire.count("AND pr.owner_player_id = ANY(v_owner_ids)") == 1 and retire.count("= ANY(") == 1
    assert ("INSERT INTO pc_print_retirements (print_id, reason, compensation, shards) SELECT r.id, "
            "'no_steam_id', v_compensation, r.discard_shards FROM retired r ), paid AS (") in retire
    assert "DELETE FROM pc_delivery_leases l USING retired r WHERE l.print_id = r.id RETURNING l.id" in retire
    assert retire.endswith("(SELECT array_agg(r.id) FROM retired r) INTO v_retired, v_owners, v_leases, v_ids;")
    # after it, a live print of such a subject visible to that statement raises: one this run did not retire, left
    # after the owners' read by a writer other than v4.13 code (a print committed since, or a subject's id changed
    # since); the file's ORDER prerequisite excludes one, and a print not yet committed when that statement begins
    # is not visible to it
    last = _span(body, "IF EXISTS (SELECT 1 FROM pc_prints pr", "END IF;")
    assert last.startswith("IF EXISTS (SELECT 1 FROM pc_prints pr JOIN pc_cards c ON c.id = pr.card_id JOIN players s "
                           "ON s.id = c.subject_player_id WHERE pr.discarded_at IS NULL AND " + RULE_S +
                           ") THEN RAISE EXCEPTION")
    order = [body.index(s) for s in (owners, ident, rows, retire, last)]
    assert order == sorted(order), order
    # the DO block selects by the rule in exactly those three statements, and reads the set everywhere else
    assert body.count(RULE_S) == 3 and body.count("= ANY(v_owner_ids)") == 5
    assert body.count("UPDATE pc_prints") == 1 and body.count("INTO v_owner_ids") == 2


def test_migration_320_raises_unless_the_locked_owners_shards_moved_by_the_shards_recorded():
    body = _body320(_flat320())
    reading = "SELECT COALESCE(SUM(o.pc_shards), 0) INTO %s FROM players o WHERE o.id = ANY(v_owner_ids);"
    before, after = reading % "v_before", reading % "v_after"
    recorded = ("SELECT COALESCE(SUM(rt.shards), 0) INTO v_recorded FROM pc_print_retirements rt "
                "WHERE rt.print_id = ANY(v_ids);")
    # two readings of the same locked rows and the records' total: the only balance reads in the block
    assert body.count(before) == 1 and body.count(after) == 1 and body.count(recorded) == 1
    assert body.count("SUM(o.pc_shards)") == 2
    # one comparison: what moved against what was recorded, raising on any difference either way
    check = _span(body, "IF v_after - v_before <> v_recorded THEN", "END IF;")
    assert check == ("IF v_after - v_before <> v_recorded THEN RAISE EXCEPTION '320: the owners'' shards moved by % "
                     "but % shard(s) are recorded for the prints retired here; the retirement is not applied', "
                     "v_after - v_before, v_recorded; END IF;")
    assert body.count("<> v_recorded") == 1 and body.count("v_recorded") == 4
    # the first reading after the owners' rows are locked, so only this transaction moves them until COMMIT;
    # then the write; then the records it made and the second reading; then the comparison; then the last check
    locked = body.index("FOR NO KEY UPDATE OF o) q;")
    write = body.index("WITH retired AS (")
    written = body.index("INTO v_retired, v_owners, v_leases, v_ids;")
    last = body.index("IF EXISTS (SELECT 1 FROM pc_prints pr")
    order = [locked, body.index(before), write, written, body.index(recorded), body.index(after), body.index(check), last]
    assert order == sorted(order), order
    # the check never reads the write's own arithmetic: the payment returns nothing, and the NOTICE reports
    # the shards that moved
    assert "RETURNING d.shards" not in body and "v_paid" not in body
    assert body.endswith("RAISE NOTICE '320: compensation %: % print(s) retired from % owner(s), % shard(s) paid, "
                         "% lease(s) released', v_compensation, v_retired, v_owners, v_after - v_before, v_leases; ")
