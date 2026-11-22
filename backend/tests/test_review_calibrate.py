"""The calibration tool (review_calibrate): a named revision counted rule by
rule over recorded evidence, read only.

Every rule bound below is INVENTED for these tests (an unusual value chosen
only to exercise the machinery) and is written as a V(<constant>) call, so a
separate check can read them all. Player ids are obviously synthetic.

The one database case runs against a throwaway database built the way the
combat evidence lane builds its own (combat_evidence_pg.case: the
seat-evidence build with every evidence domain's tables); it FAILS rather
than skips when SEAT_EVIDENCE_TEST_PG_DSN is unset, unless
SEAT_EVIDENCE_TEST_PG_OPTOUT=1 waives it (seat_evidence_pg.require_live_pg).
"""

import asyncio
import copy
import json
import os
import re
import signal
import sys
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import review_boot  # noqa: E402,F401 -- before any closure module
import card_evidence as ce  # noqa: E402
import card_measures as cm  # noqa: E402
import card_revision_kit as kit  # noqa: E402
import combat_evidence_fixtures as cfx  # noqa: E402
import identity_clock_fixtures as ifx  # noqa: E402
import review_calibrate as rc  # noqa: E402
import review_rules as rr  # noqa: E402

# -- the planted revision ----------------------------------------------------------------

ID_DUP = "r7e5ca001"
ID_HELD = "r7e5ca002"
ID_RAISE = "r7e5ca003"
ID_WIN = "r7e5ca004"
ID_IDB = "r7e5cb001"
ID_CMB = "r7e5cc001"
ID_GAME = "r7e5cd001"
WINDOW_DAYS = 11


def M(name):
    return {"m": name}


def V(v):
    return {"v": v}


def cmp(a, rel, b):
    return {"op": "op.cmp", "args": {"a": a, "rel": rel, "b": b}}


def _rule(rid, scope, subject, when, show, line):
    return {"id": rid, "scope": scope, "subject": subject, "effect": "flag", "post": False,
            "post_since": None, "when": when, "show": show, "line": line}


def planted_doc():
    return {
        "format": 1, "nonce": "", "vocabulary": [], "closure": {},
        "measure_params": {cm.WINDOW: {cm.WINDOW_KEY: WINDOW_DAYS}},
        "rules": [
            _rule(ID_DUP, "card", "card.hand", cmp(M("b4.hand.dup"), "gt", V(0.375)),
                  [["dup", "b4.hand.dup"]], "planted dup {dup}"),
            _rule(ID_HELD, "card", "card.hand", cmp(M("b4.hand.heldrej"), "gt", V(7.25)),
                  [["held", "b4.hand.heldrej"]], "planted held {held}"),
            _rule(ID_RAISE, "card", "card.hand", cmp(M("b4.hand.spx"), "ge", V(0.625)),
                  [["spx", "b4.hand.spx"]], "planted spx {spx}"),
            _rule(ID_WIN, "card", "card.window", cmp(M("b4.rar.hands"), "gt", V(4.5)),
                  [["hands", "b4.rar.hands"]], "planted window {hands}"),
            _rule(ID_IDB, "identity", "ic.seat",
                  {"not": {"op": "op.truth", "args": {"a": M("ic.seat.build_registered")}}},
                  [["seat", "ic.seat.index"]], "planted unregistered {seat}"),
            _rule(ID_CMB, "combat", "combat.cycle", cmp(M("b2.cycle.rexp"), "gt", V(913)),
                  [["units", "b2.cycle.units"]], "planted cycle {units}"),
            _rule(ID_GAME, "game", "seat", cmp(M("seat.published_hits"), "ge", V(37.125)),
                  [["p", "seat.published_hits"]], "planted game {p}"),
        ],
    }


def build_planted(tmp, doc=None, name="draft"):
    """A revision built by review_rules.build_revision in a temporary rules
    root. Returns (root, rev)."""
    root = os.path.join(str(tmp), "root")
    os.makedirs(root, exist_ok=True)
    draft = os.path.join(str(tmp), name)
    os.makedirs(draft, exist_ok=True)
    with open(os.path.join(draft, "rules.json"), "w", encoding="utf-8") as f:
        json.dump(planted_doc() if doc is None else doc, f)
    with open(os.path.join(draft, "selftest.json"), "w", encoding="utf-8") as f:
        json.dump({"cases": []}, f)
    return root, rr.build_revision(draft, root, "synthetic")


@pytest.fixture(scope="module")
def planted(tmp_path_factory):
    root, rev = build_planted(tmp_path_factory.mktemp("calib"))
    path = os.path.join(root, "rules-" + rev)
    return path, rr.load_dir(path)


# -- synthetic card views -----------------------------------------------------------------

SEAT_P = "70000000-0000-0000-0000-00000000c0a1"
SEAT_Q = "70000000-0000-0000-0000-00000000c0b2"
SEAT_R = "70000000-0000-0000-0000-00000000c0c3"
PROFILE = "7" * 64
DAY0 = date(2026, 3, 5)


def hand(dup=0, heldrej=0, spx=0, *, recorder=SEAT_P, dealer=SEAT_Q, w=0,
         obs=(3, 1, 0), exp=(2.5, 1.25, 0.25), var=(1.5, 0.75, 0.125), n=5):
    row = {"b4.hand.dup": dup, "b4.hand.heldrej": heldrej, "b4.hand.spx": spx}
    meta = {"recorder": recorder, "dealer": dealer, "w": w, "profile": PROFILE, "weighed": True,
            "exp": (list(obs), list(exp), list(var)), "n": n}
    return row, meta


def view(*hands, two=True):
    return {"hands": list(hands), "phases": [], "records": [], "pairs": [], "game": None,
            "two": two}


class FakeFetch:
    """The injectable fetch layer: per domain, the planted items in order.
    `now` counts the items handed out (a test clock); `before` is called with
    that count just before each item is handed out; `closed` lists the
    domains whose item generator was closed."""

    def __init__(self, by_domain, before=None):
        self.by_domain = by_domain
        self.before = before
        self.now = 0
        self.closed = []

    async def totals(self):
        return {d: len(self.by_domain.get(d, ())) for d in rc.DOMAINS}

    async def items(self, domain, rs):
        try:
            for it in self.by_domain.get(domain, ()):
                self.now += 1
                if self.before is not None:
                    self.before(self.now)
                yield it
        finally:
            self.closed.append(domain)


# -- identity and combat inputs -------------------------------------------------------------

BUILD = ("1.41.0", "STANDALONE", "abcdef123456", "e" * 64)
ID_SEAT_A = "70000000-0000-0000-0000-00000000d1a1"
ID_SEAT_B = "70000000-0000-0000-0000-00000000d1b2"
CMB_SEAT_A = "70000000-0000-0000-0000-00000000e1a1"
CMB_SEAT_B = "70000000-0000-0000-0000-00000000e1b2"


def id_view(seat, other, rec):
    return {"seat": seat, "other": other, "rec": rec, "header_version": "1.41.0",
            "conflict": False, "conn_class": "none", "conn_ranges": "absent", "post_clock": "ok",
            "seat_build": list(BUILD), "relayed_build": "1.41.0|STANDALONE|abcdef123456",
            "fit": None, "fit_rows": 0}


def id_pair():
    return [id_view(ID_SEAT_A, ID_SEAT_B, ifx.base_record()),
            id_view(ID_SEAT_B, ID_SEAT_A, ifx.base_record(proc=ifx.PROC_B))]


def regs(registered):
    return {"release": {BUILD: "release"} if registered else {}, "game_files": set()}


def combat_fire():
    return cfx.records(*cfx.a24_pair(), a=CMB_SEAT_A, b=CMB_SEAT_B)


def combat_quiet():
    return cfx.records(cfx.empty_record(), None, a=CMB_SEAT_A, b=CMB_SEAT_B)


def planted_items():
    """Three card games (dup fires on the first, held on the second, the spx
    rule raises on the third) and two skipped; two identity games (the build
    rule fires on the unregistered one) and one skipped; two combat games
    (the cycle rule fires on the first)."""
    return {
        "card": [
            ("game", (view(hand(dup=3)), DAY0)),
            ("skip", "nomatch"),
            ("game", (view(hand(heldrej=8)), DAY0)),
            ("game", (view(hand(spx="text")), DAY0)),
            ("skip", "purged"),
        ],
        "identity": [
            ("game", (id_pair(), regs(True))),
            ("game", (id_pair(), regs(False))),
            ("skip", "unnamed"),
        ],
        "combat": [
            ("game", combat_fire()),
            ("game", combat_quiet()),
        ],
    }


def counts(tally):
    return {rid: (c["evaluated"], c["fired"], c["errors"]) for rid, c in tally.counts.items()}


def run(coro):
    return asyncio.run(coro)


# -- the counting core ----------------------------------------------------------------------

def test_each_rule_is_counted_alone_over_the_planted_games(planted):
    _path, rs = planted
    tally = run(rc.walk(rs, FakeFetch(planted_items())))
    got = counts(tally)
    assert got[ID_DUP] == (3, 1, 0)
    assert got[ID_HELD] == (3, 1, 0)
    assert got[ID_RAISE] == (3, 0, 1)
    assert got[ID_IDB] == (2, 1, 0)
    assert got[ID_CMB] == (2, 1, 0)
    assert ID_GAME not in got and tally.uncounted == 1


def test_the_full_ruleset_would_change_the_counts(planted, monkeypatch):
    """Negative control of the one-rule copy: evaluated with the whole
    ruleset, the raising rule's error lands on every other card rule."""
    _path, rs = planted
    alone = counts(run(rc.walk(rs, FakeFetch(planted_items()))))
    monkeypatch.setattr(rc, "one_rule", lambda rs_, rule: rs_)
    whole = counts(run(rc.walk(rs, FakeFetch(planted_items()))))
    assert whole != alone
    assert whole[ID_DUP][2] == 1 and alone[ID_DUP][2] == 0


def test_the_one_rule_copy_holds_only_that_rule_and_leaves_the_ruleset_alone(planted):
    _path, rs = planted
    before = [r.id for r in rs.rules]
    rule = rs.rule(ID_HELD)
    single = rc.one_rule(rs, rule)
    assert [r.id for r in single.card_rules] == [ID_HELD] and single.identity_rules == []
    assert [r.id for r in rs.rules] == before and single.core is rs.core


def test_skipped_games_are_counted_by_word_and_never_as_walked(planted):
    _path, rs = planted
    tally = run(rc.walk(rs, FakeFetch(planted_items())))
    assert tally.domains["card"] == {"walked": 3, "skipped": {"nomatch": 1, "purged": 1}}
    assert tally.domains["identity"] == {"walked": 2, "skipped": {"unnamed": 1}}
    assert tally.domains["combat"] == {"walked": 2, "skipped": {}}
    lines = rc.render(tally)
    assert "domain card walked=3 windows=1 skipped=2 nomatch=1 purged=1" in lines
    assert "domain identity walked=2 skipped=1 unnamed=1" in lines
    assert "domain combat walked=2 skipped=0" in lines
    assert "rule %s scope=card evaluated=3 fired=0 errors=1" % ID_RAISE in lines
    assert "game and sitting rules not counted: 1" in lines


# -- the card windows -----------------------------------------------------------------------

def window_items():
    """Contributions over several days for one class (dealer Q, own hands,
    paired, one profile) and one game of another class (dealer R)."""
    return {"card": [
        ("game", (view(hand(), hand()), DAY0)),
        ("game", (view(hand(), hand(), hand()), DAY0 + timedelta(days=1))),
        ("game", (view(hand(recorder=SEAT_R, dealer=SEAT_R)), DAY0 + timedelta(days=1))),
        ("game", (view(hand()), DAY0 + timedelta(days=12))),
    ]}


def test_windows_are_rebuilt_as_the_pass_builds_them_and_each_is_evaluated_once(planted):
    _path, rs = planted
    tally = run(rc.walk(rs, FakeFetch(window_items())))
    wins = rc.rebuild_windows(tally.daily, rs)
    got = [(k[0], k[1], agg["games"], agg["hands"], agg["slots"]) for k, agg in wins]
    # width 11: the class of Q ends windows on days 0, 1 and 12; day 12's window
    # (days 2..12) holds only day 12. R's class has one window.
    assert sorted(got) == sorted([
        (SEAT_Q, DAY0, 1, 2, 10),
        (SEAT_Q, DAY0 + timedelta(days=1), 2, 5, 25),
        (SEAT_Q, DAY0 + timedelta(days=12), 1, 1, 5),
        (SEAT_R, DAY0 + timedelta(days=1), 1, 1, 5),
    ])
    q1 = next(agg for k, agg in wins if k[0] == SEAT_Q and k[1] == DAY0 + timedelta(days=1))
    assert q1["obs"] == [15, 5, 0] and q1["source"] == cm.WORD["self"]
    assert q1["coverage"] == cm.WORD["paired"]
    assert tally.windows == 4
    # the window rule: once per window, fired on the one window over its bound
    assert counts(tally)[ID_WIN] == (4, 1, 0)
    # the game-level card rules are not evaluated on windows
    assert counts(tally)[ID_DUP][0] == 4


class _WindowDb:
    """Answers card_evidence._windows' daily read from in-memory daily rows."""

    def __init__(self, daily, rev):
        self.daily, self.rev = daily, rev

    async def execute(self, stmt, b):
        assert "FROM card_player_daily" in str(stmt) and b["rev"] == self.rev
        rows = []
        for (s, d, src, cov, p), r in sorted(self.daily.items(), key=str):
            if (s, src, cov, p) == (b["s"], b["src"], b["cov"], b["p"]) \
                    and b["a"] - timedelta(days=b["w"]) < d <= b["b"]:
                row = {"day": d, "games": len(r["games"])}
                row.update({c: r[c] for c in ce._DAILY_COLS})
                rows.append(row)
        return FakeResult(rows)


def test_the_window_rebuild_equals_the_pass_window_reader_over_the_same_daily_rows(planted):
    _path, rs = planted
    tally = run(rc.walk(rs, FakeFetch(window_items())))
    keys = [k + (rs.rev,) for k in tally.daily]
    theirs, _owned = run(ce._windows(_WindowDb(tally.daily, rs.rev), keys, rs))
    mine = rc.rebuild_windows(tally.daily, rs)
    assert len(mine) == len(theirs) == 4
    assert sorted(mine, key=str) == sorted(theirs, key=str)


def test_no_window_parameter_means_no_windows(tmp_path):
    doc = planted_doc()
    doc["measure_params"] = {}
    root, rev = build_planted(tmp_path, doc)
    rs = rr.load_dir(os.path.join(root, "rules-" + rev))
    tally = run(rc.walk(rs, FakeFetch(window_items())))
    assert tally.windows == 0 and counts(tally)[ID_WIN] == (0, 0, 0)


# -- the output holds no identifier ---------------------------------------------------------

def test_the_output_holds_no_identifier(planted):
    _path, rs = planted
    items = planted_items()
    items["card"] += window_items()["card"]
    out = "\n".join(rc.render(run(rc.walk(rs, FakeFetch(items)))))
    for ident in (SEAT_P, SEAT_Q, SEAT_R, ID_SEAT_A, ID_SEAT_B, CMB_SEAT_A, CMB_SEAT_B, PROFILE):
        assert ident not in out and ident[-4:] not in out
    assert ID_DUP in out


# -- the read-only session over a statement-recording fake ---------------------------------

_WRITE = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|GRANT|REVOKE|COPY"
                    r"|COMMIT|LOCK|NOTIFY|pg_advisory\w*|nextval|setval)\b", re.I)
_LOCK = re.compile(r"\bFOR\s+(NO\s+KEY\s+UPDATE|UPDATE|SHARE|KEY\s+SHARE)\b", re.I)


def forbidden(sql):
    return bool(_WRITE.search(sql) or _LOCK.search(sql))


class FakeResult:
    def __init__(self, rows):
        self.rows = [dict(r) for r in rows]

    def all(self):
        return [tuple(r.values()) for r in self.rows]

    def first(self):
        return tuple(self.rows[0].values()) if self.rows else None

    def scalar(self):
        return next(iter(self.rows[0].values())) if self.rows else None

    def scalars(self):
        return FakeResult([{"v": next(iter(r.values()))} for r in self.rows])

    def mappings(self):
        return _Mappings(self.rows)


class _Mappings:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None


KEY_C = "calibkeyQX7251card"
KEY_I = "calibkeyQX7251ident"
KEY_B = "calibkeyQX7251cmb"
ROOM_C = "calibroomZQ9137card"
ROOM_I = "calibroomZQ9137ident"
ROOM_B = "calibroomZQ9137cmb"
LO = "70000000-0000-0000-0000-0000000f7a01"
HI = "70000000-0000-0000-0000-0000000f7a02"
MATCH_C = "70000000-0000-0000-0000-0000000fa0c1"
MATCH_I = "70000000-0000-0000-0000-0000000fa0c2"
MATCH_B = "70000000-0000-0000-0000-0000000fa0c3"
ENDED = datetime(2026, 3, 7, 18, 45, tzinfo=timezone.utc)


def full_game_dump():
    """The census of the committed full-game fixture, as an admin registers it."""
    inp = kit.fixture_input("full_game")
    names = {c[0]: c[1] for c in inp["cards"]}
    rarity = {c[0]: c[2] for c in inp["cards"] if 0 <= c[2] < len(cm.RARITIES)}
    return kit.census_dump(kit.census_cards(inp["pool"][0], names=names, rarity=rarity),
                           slots=inp["ns"])


class RecordingSession:
    """A session that records every statement and answers the tool's reads
    from planted rows; any statement it does not know fails the test."""

    def __init__(self):
        self.log = []
        dump = full_game_dump()
        census = cm.census_from_dump(dump)
        self.dump = dump
        self.card_rec = kit.on_census(kit.fixture_record("full_game"), census)
        owner, meas = cfx.a24_pair()
        self.cmb = [(LO, HI, owner), (HI, LO, meas)]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        self.log.append(("COMMIT", None))

    async def rollback(self):
        self.log.append(("ROLLBACK", None))

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.log.append((sql, params))
        return FakeResult(self._answer(sql, params or {}))

    def _answer(self, sql, b):
        if sql == rc.READ_ONLY_START:
            return []
        if "make_interval(days" in sql:
            table = sql.split(" FROM ", 1)[1].split()[0]
            key = {"card_evidence": KEY_C, "identity_clock_evidence": KEY_I,
                   "combat_evidence": KEY_B}[table]
            return [{"k": key, "lo": LO, "hi": HI}]
        if "FROM card_evidence WHERE" in sql:
            assert b["k"] == KEY_C
            return [{"id": 1, "seat_player_id": LO, "other_player_id": HI, "attach_key": ROOM_C,
                     "payload": self.card_rec, "pool_digest": self.dump["digest"],
                     "conflict_at": None, "received_at": ENDED, "gen": 1}]
        if "LEFT JOIN ranked_series" in sql:
            return [{"id": MATCH_C, "ended_at": ENDED, "photon_room_id": ROOM_C, "sc": None}]
        if "FROM card_pool_registry" in sql:
            return [{"census": self.dump, "digest": self.dump["digest"], "gen": 1}]
        if "FROM match_cards" in sql:
            return []
        if "FROM mod_release_digests" in sql or "FROM game_file_digests" in sql:
            return []
        if "FROM identity_clock_evidence WHERE stable_game_key" in sql:
            assert b["k"] == KEY_I
            return [{"id": 2, "seat_player_id": LO, "other_player_id": HI, "attach_key": ROOM_I,
                     "payload": ifx.base_record(), "header_mod_version": "1.41.0",
                     "conflict_at": None, "conn_class": "none", "conn_ranges": "absent",
                     "post_clock": "ok", "post_proc": ifx.PROC_A, "lists_purged_at": None}]
        if "FROM identity_clock_evidence WHERE seat_player_id" in sql:
            return []
        if "FROM seat_evidence WHERE stable_game_key" in sql:
            return []
        if sql.startswith("SELECT id, player1_id, player2_id, ended_at, photon_room_id FROM matches"):
            return [{"id": MATCH_I, "player1_id": LO, "player2_id": HI, "ended_at": ENDED,
                     "photon_room_id": ROOM_I}]
        if "FROM combat_evidence WHERE" in sql:
            assert b["k"] == KEY_B
            return [{"id": 3 + i, "seat_player_id": s, "other_player_id": o, "attach_key": ROOM_B,
                     "payload": rec, "conflict_at": None} for i, (s, o, rec) in enumerate(self.cmb)]
        if sql.startswith("SELECT id, photon_room_id, player1_id, player2_id, ended_at FROM matches"):
            return [{"id": MATCH_B, "photon_room_id": ROOM_B, "player1_id": LO, "player2_id": HI,
                     "ended_at": ENDED}]
        raise AssertionError("the fake does not know this statement: " + sql[:120])


def test_the_forbidden_statement_check_sees_writes_and_locks():
    """Negative control of the checker: every write and lock form is seen,
    the tool's own reads are not."""
    for sql in ("INSERT INTO x VALUES (1)", "update x set y = 1", "DELETE FROM x",
                "SELECT * FROM x FOR UPDATE", "SELECT * FROM x FOR NO KEY UPDATE",
                "SELECT * FROM x FOR SHARE", "SELECT pg_advisory_xact_lock(1)", "COMMIT",
                "CREATE TEMP TABLE t (a int)", "TRUNCATE x"):
        assert forbidden(sql), sql
    assert not forbidden(rc.READ_ONLY_START)
    assert not forbidden(str(ce._MATCH)) and not forbidden(str(rc._CARD_ROWS))
    assert not forbidden(rc._GAMES_SQL)
    # the passes' own per-game statements are exactly what the tool must not run
    assert forbidden("SELECT 1 FROM card_games WHERE true FOR UPDATE")


def test_the_walk_reads_through_one_read_only_transaction_and_writes_nothing(planted, capsys):
    _path, rs = planted
    sess = RecordingSession()
    tally = run(rc.walk_db(rs, lambda: sess, 41))
    printed = capsys.readouterr()
    sqls = [s for s, _b in sess.log]
    assert sqls[0] == rc.READ_ONLY_START
    assert sqls[-1] == "ROLLBACK" and "COMMIT" not in sqls
    bad = [s for s in sqls[1:-1] if forbidden(s)]
    assert bad == [], bad
    # every domain was read through to evaluation
    assert {d: v["walked"] for d, v in tally.domains.items()} == {"card": 1, "identity": 1,
                                                                    "combat": 1}
    assert all(b["days"] == 41 for s, b in sess.log if "make_interval(days" in s)
    assert counts(tally)[ID_CMB] == (1, 1, 0)
    out = "\n".join(rc.render(tally) + [printed.out, printed.err])
    for ident in (KEY_C, KEY_I, KEY_B, ROOM_C, ROOM_I, ROOM_B, LO, HI, MATCH_C, MATCH_I, MATCH_B,
                  "QX7251", "ZQ9137", "f7a0", "fa0c"):
        assert ident not in out, ident


def test_a_purged_record_is_skipped_by_its_own_word(planted):
    _path, rs = planted
    sess = RecordingSession()
    sess.card_rec = {k: v for k, v in sess.card_rec.items() if k != ce.LIST_KEYS[0]}
    tally = run(rc.walk_db(rs, lambda: sess, 41))
    assert tally.domains["card"] == {"walked": 0, "skipped": {"purged": 1}}


@pytest.mark.parametrize("fn", ["rebuild_faults", "section_faults"])
def test_a_combat_game_whose_fault_rebuild_raises_is_not_evaluated_as_the_pass_does_not(
        planted, monkeypatch, fn):
    """The combat pass rebuilds every record's fault rows before it
    evaluates, in one try, and evaluates nothing when a rebuild raises
    (combat_evidence.py:369-376). The tool counts that game under its own
    word and evaluates no rule on it; the other domains are unaffected."""
    _path, rs = planted
    assert rc.cev.cm is rc.cbm               # the tool calls the pass's own rebuild functions

    def planted_fault(*_a, **_k):
        raise ValueError("planted rebuild fault")
    monkeypatch.setattr(rc.cbm, fn, planted_fault)
    tally = run(rc.walk_db(rs, lambda: RecordingSession(), 41))
    assert tally.domains["combat"] == {"walked": 0, "skipped": {"rebuild_fault": 1}}
    assert counts(tally)[ID_CMB] == (0, 0, 0)
    assert "domain combat walked=0 skipped=1 rebuild_fault=1" in rc.render(tally)
    assert tally.domains["card"]["walked"] == 1 and tally.domains["identity"]["walked"] == 1


# -- the bounded run ------------------------------------------------------------------------

CUT_HEAD = ("run cut (deadline): games read 4 of 10 (card 4 of 5, identity 0 of 3, combat 0 of 2); "
            "card windows evaluated 0 of none rebuilt; every count below covers only what was read")


def _reads_as_whole(line):
    return line.startswith(("run whole", "rule ", "domain ", "game and sitting"))


def test_a_run_its_deadline_ends_says_it_was_cut_and_no_count_reads_as_whole(planted):
    _path, rs = planted
    fetch = FakeFetch(planted_items())
    tally = run(rc.walk(rs, fetch, deadline_at=4, clock=lambda: fetch.now))
    assert tally.cut == "deadline" and fetch.closed == ["card"]
    assert tally.domains["card"] == {"walked": 3, "skipped": {"nomatch": 1}}
    assert tally.domains["identity"]["walked"] == tally.domains["combat"]["walked"] == 0
    lines = rc.render(tally)
    assert lines[0] == CUT_HEAD
    assert len(lines) == 1 + len(tally.rules) + len(rc.DOMAINS) + 1
    assert all(line.startswith("cut ") for line in lines[1:])
    assert not any(_reads_as_whole(line) for line in lines)
    assert "cut rule %s scope=card evaluated=3 fired=1 errors=0" % ID_DUP in lines
    assert "cut domain card walked=3 windows=0 skipped=1 nomatch=1" in lines


def test_a_run_its_deadline_does_not_reach_reads_every_game_and_says_whole(planted):
    """Control of the cut test: the same walk with a deadline it never reaches."""
    _path, rs = planted
    fetch = FakeFetch(planted_items())
    tally = run(rc.walk(rs, fetch, deadline_at=10 ** 6, clock=lambda: fetch.now))
    lines = rc.render(tally)
    assert tally.cut is None and fetch.closed == list(rc.DOMAINS)
    assert lines[0] == ("run whole: games read 10 of 10 (card 5 of 5, identity 3 of 3, "
                        "combat 2 of 2)")
    assert not any(line.startswith("cut") for line in lines)


def test_a_deadline_inside_the_card_windows_cuts_them_and_says_how_many_were_evaluated(planted):
    _path, rs = planted
    tally = rc.Tally(rs)
    for _kind, payload in window_items()["card"]:
        tally.game("card", payload)
    ticks = iter([0, 0, 1, 1, 1])
    tally.finish(deadline_at=1, clock=lambda: next(ticks))
    assert (tally.windows, tally.windows_total, tally.cut) == (2, 4, "deadline")
    assert counts(tally)[ID_WIN][0] == 2
    lines = rc.render(tally)
    assert "card windows evaluated 2 of 4" in lines[0] and lines[0].startswith("run cut (deadline)")
    assert all(line.startswith("cut ") for line in lines[1:])


def test_a_stop_signal_ends_the_walk_after_the_game_in_hand_and_the_run_says_so(
        planted, monkeypatch):
    _path, rs = planted
    monkeypatch.setitem(rc._STOP, "word", None)
    fetch = FakeFetch(planted_items(),
                      before=lambda n: n == 2 and rc._on_term(signal.SIGTERM, None))
    tally = run(rc.walk(rs, fetch))
    lines = rc.render(tally)
    assert tally.cut == "stopped" and fetch.closed == ["card"]
    assert lines[0].startswith("run cut (stopped): games read 2 of 10 (card 2 of 5, identity 0 of 3")
    assert all(line.startswith("cut ") for line in lines[1:])
    assert not any(_reads_as_whole(line) for line in lines)


# -- the revision path ----------------------------------------------------------------------

class _Seen(list):
    """The revisions main() walked, plus what each walk was handed."""


@pytest.fixture
def no_db(monkeypatch):
    """main() stops before any database: the walk is a stub."""
    seen = _Seen()
    seen.calls = []

    async def fake_run(rs, days, deadline_at=None):
        seen.append(rs.rev)
        seen.calls.append({"days": days, "deadline_at": deadline_at,
                           "handler": signal.getsignal(signal.SIGTERM)})
        return rc.Tally(rs).finish()
    monkeypatch.setattr(rc, "_run", fake_run)
    return seen


def _main(capsys, path, days="23"):
    code = rc.main(["--revision", path, "--days", days])
    return code, capsys.readouterr().out


def test_the_named_revision_loads_and_reports(planted, no_db, capsys):
    path, rs = planted
    code, out = _main(capsys, path)
    assert code == 0 and no_db == [rs.rev]
    assert "rule %s scope=card evaluated=0 fired=0 errors=0" % ID_DUP in out


@pytest.mark.parametrize("name,word", [
    ("current", "pointer"), ("rules-none", "pointer"), ("rules-0123456789a", "name"),
    ("rules-0123456789abc", "name"), ("rules-0123456789AB", "name"), ("rules-0123456789a٣", "name"),
    ("rules0123456789ab", "name")])
def test_a_pointer_or_a_malformed_name_is_refused_before_loading(tmp_path, no_db, capsys, name, word):
    p = tmp_path / name
    p.mkdir()
    code, out = _main(capsys, str(p))
    assert code == rc.EXIT_USAGE and out.strip() == "refused (path %s)" % word
    assert no_db == []


def test_the_pointer_is_refused_even_naming_a_good_revision(planted, no_db, capsys):
    path, _rs = planted
    root = os.path.dirname(path)
    with open(os.path.join(root, rr.POINTER), "w", encoding="ascii") as f:
        f.write(os.path.basename(path) + "\n")
    code, out = _main(capsys, os.path.join(root, rr.POINTER))
    assert code == rc.EXIT_USAGE and "refused (path pointer)" in out and no_db == []


def test_a_directory_with_a_revision_name_that_is_no_revision_is_refused_by_the_loader(
        tmp_path, no_db, capsys):
    p = tmp_path / "rules-0123456789ab"
    p.mkdir()
    (p / "rules.json").write_text("{}", encoding="utf-8")
    code, out = _main(capsys, str(p))
    assert code == rc.EXIT_REFUSED and out.startswith("refused (") and no_db == []


def test_a_symbolic_link_is_refused(planted, tmp_path, no_db, capsys):
    path, _rs = planted
    link = tmp_path / os.path.basename(path)
    try:
        os.symlink(path, str(link), target_is_directory=True)
    except (OSError, NotImplementedError) as e:
        pytest.skip("this OS refused to create a symbolic link (%s)" % type(e).__name__)
    # control: the link names the good revision (load_dir would refuse it as
    # well; the tool refuses it first, by path)
    assert os.path.realpath(str(link)) == os.path.realpath(path)
    code, out = _main(capsys, str(link))
    assert code == rc.EXIT_USAGE and out.strip() == "refused (path link)" and no_db == []


def test_a_directory_junction_is_refused(planted, tmp_path, no_db, capsys):
    """The Windows form of a directory link (where creating a symbolic link
    needs a privilege a test seat may not hold)."""
    try:
        import _winapi
    except ImportError:
        pytest.skip("directory junctions exist only on Windows")
    if not hasattr(os.path, "isjunction"):
        pytest.skip("this Python cannot tell a junction (os.path.isjunction)")
    path, _rs = planted
    link = tmp_path / os.path.basename(path)
    _winapi.CreateJunction(path, str(link))
    assert os.path.realpath(str(link)) == os.path.realpath(path)    # control: names the revision
    code, out = _main(capsys, str(link))
    assert code == rc.EXIT_USAGE and out.strip() == "refused (path link)" and no_db == []


def test_days_out_of_range_are_refused(planted, no_db, capsys):
    path, _rs = planted
    for days in ("0", "-3", str(cm.WINDOW_DAYS_MAX + 1)):
        code, out = _main(capsys, path, days)
        assert code == rc.EXIT_USAGE and out.strip() == "refused (days)"
    assert no_db == []


def test_the_deadline_has_a_stated_default_a_bound_and_reaches_the_walk(planted, no_db, capsys):
    path, rs = planted
    t0 = time.monotonic()
    code, out = _main(capsys, path)
    t1 = time.monotonic()
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "revision %s days 23 deadline_s %d" % (rs.rev, rc.DEFAULT_DEADLINE_S)
    assert lines[1].startswith("run whole: ")
    got = no_db.calls[0]["deadline_at"]
    assert t0 + rc.DEFAULT_DEADLINE_S <= got <= t1 + rc.DEFAULT_DEADLINE_S
    t0 = time.monotonic()
    code = rc.main(["--revision", path, "--days", "23", "--deadline-s", "77"])
    t1 = time.monotonic()
    assert code == 0 and "deadline_s 77" in capsys.readouterr().out
    assert t0 + 77 <= no_db.calls[1]["deadline_at"] <= t1 + 77
    for bad in ("0", "-5", str(rc.DEADLINE_MAX_S + 1)):
        code = rc.main(["--revision", path, "--days", "23", "--deadline-s", bad])
        assert code == rc.EXIT_USAGE and capsys.readouterr().out.strip() == "refused (deadline)"
    assert len(no_db) == 2


def test_main_holds_the_stop_handler_only_while_it_walks(planted, no_db, capsys):
    path, _rs = planted
    before = signal.getsignal(signal.SIGTERM)
    code, _out = _main(capsys, path)
    assert code == 0 and no_db.calls[0]["handler"] is rc._on_term
    assert signal.getsignal(signal.SIGTERM) is before and rc._STOP["word"] is None


# -- the database (live) ----------------------------------------------------------------------

def test_live_the_session_refuses_a_write_and_an_empty_window_walks_nothing(planted):
    import combat_evidence_pg as cp
    import seat_evidence_pg as sp
    from sqlalchemy.exc import DBAPIError
    sp.require_live_pg()
    _path, rs = planted

    async def go():
        async with cp.case("calib") as (_c, sm, _snaps):
            async with rc.read_only(sm) as db:
                with pytest.raises(DBAPIError) as ei:
                    await db.execute(text(
                        "INSERT INTO runtime_settings (key, value) VALUES ('calib_probe', 'v')"))
                assert "read-only transaction" in str(ei.value)
            async with sm() as db:
                present = (await db.execute(text(
                    "SELECT count(*) FROM pg_tables WHERE schemaname = current_schema() "
                    "AND tablename = ANY(CAST(:t AS text[]))"),
                    {"t": sorted(rc._TABLES.values())})).scalar()
                probe = (await db.execute(text(
                    "SELECT count(*) FROM runtime_settings WHERE key = 'calib_probe'"))).scalar()
            assert present == len(rc._TABLES) and probe == 0
            return await rc.walk_db(rs, sm, 29)
    tally = run(go())
    assert {d: v for d, v in tally.domains.items()} == {d: {"walked": 0, "skipped": {}}
                                                        for d in rc.DOMAINS}
    assert tally.windows == 0 and all(c == (0, 0, 0) for c in counts(tally).values())
    assert rc.render(tally)[0] == ("run whole: games read 0 of 0 (card 0 of 0, identity 0 of 0, "
                                   "combat 0 of 0)")
