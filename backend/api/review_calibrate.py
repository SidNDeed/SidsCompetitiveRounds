"""Rule calibration over recorded evidence (tier 2), read only.

Run in the api container against its database, with a NAMED rules revision:

  python -B review_calibrate.py --revision <root>/rules-<12 hex> --days <n> [--deadline-s <s>]

For every rule of scope card, identity and combat in that revision, alone,
the tool counts how many games (a card window rule: how many windows) it was
evaluated on, how many of them it fired on and how many rule errors it
raised, over the games whose match ended within the last <n> days. It prints
one line per rule and one line per evidence domain (games walked, games
skipped by the word of the step that skipped them). It never prints a Steam
id, a player name, a game key or a match id. Its summary line says whether
the run is whole or was cut, by its own deadline (--deadline-s, default
DEFAULT_DEADLINE_S) or by SIGTERM, with how many games of how many it read;
in a cut run every count line begins with `cut`, so no count of it reads as
whole.

What it never does:

  * read the review root's `current` pointer: the revision is named by its
    directory (`rules-` and exactly twelve lower-case hex), never `current`
    or `rules-none`, and never a symbolic link; it is loaded whole by
    review_rules.load_dir (seal, closure fingerprint, every self-test), and a
    refusal ends the run with a non-zero status;
  * write or lock: the run is ONE database transaction whose first statement
    is the api's read-only start (REPEATABLE READ, READ ONLY) and which ends
    with a rollback. The evidence passes' per-game functions write their
    game rows and lock them, which a read-only transaction refuses, so they
    are not called: the same rows are re-read here with lock-free SELECTs
    (same columns and filters) and the passes' own lock-free helpers do the
    rest, in the passes' order;
  * use the passes' processing state (finalized, evaluated revision, retry,
    park): games are selected by when their match ended.

This module is outside the review code closure; nothing here changes what a
revision's closure fingerprint covers.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import os
import re
import signal
import sys
import time
from datetime import timedelta, timezone

from sqlalchemy import text

import review_boot  # noqa: F401 -- FIRST: the closure modules execute from source only (review_boot.py:13)
import card_measures as cm
import combat_measures as cbm
import review_rules as rr
import card_evidence as ce
import combat_evidence as cev
import identity_clock_evidence as ice
import seat_evidence as se

DOMAINS = ("card", "identity", "combat")
COUNTED_SCOPES = DOMAINS
EXIT_USAGE = 2
EXIT_REFUSED = 1

# The run's own deadline (--deadline-s): checked before each domain, after
# every game and before every card window. A run it ends prints the word
# `cut` on its summary line and on every count line, with how many games of
# how many it read, so no count of a cut run reads as whole. A time limit
# that stops the process with SIGTERM ends the walk the same way at the next
# check (word `stopped`); one that kills it outright leaves no count printed
# at all, because the counts are printed only after the walk.
DEFAULT_DEADLINE_S = 1200
DEADLINE_MAX_S = 7200

_STOP = {"word": None}


def _on_term(signum, frame):
    """SIGTERM during the walk: end it at the next check, as a cut run."""
    _STOP["word"] = "stopped"


def _ended(deadline_at, clock):
    """The word that ends the walk now, or None."""
    if _STOP["word"]:
        return _STOP["word"]
    if deadline_at is not None and clock() >= deadline_at:
        return "deadline"
    return None

# The api's read-only transaction start, the statement main.py's quarantine
# triage read issues first (main.py _triage_read_txn).
READ_ONLY_START = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"

_REVISION_NAME = re.compile(r"rules-[0-9a-f]{%d}" % rr.CONTRACT_BOUNDS["rev_hex"], re.ASCII)
_REFUSED_NAMES = (rr.POINTER, rr.NONE_TARGET)


class PathRefused(Exception):
    def __init__(self, word: str):
        super().__init__(word)
        self.word = word


def revision_path(path: str) -> str:
    """The revision directory to load, or PathRefused: a last part other than
    `rules-` and exactly twelve lower-case hex (so never `current` nor
    `rules-none`), or a symbolic link (or a directory junction). The pointer
    is never read."""
    if not isinstance(path, str) or not path:
        raise PathRefused("name")
    norm = os.path.normpath(path)
    base = os.path.basename(norm)
    if base in _REFUSED_NAMES:
        raise PathRefused("pointer")
    if not _REVISION_NAME.fullmatch(base):
        raise PathRefused("name")
    junction = getattr(os.path, "isjunction", None)
    if os.path.islink(norm) or (junction is not None and junction(norm)):
        raise PathRefused("link")
    return norm


# -- the read-only session ---------------------------------------------------------

@contextlib.asynccontextmanager
async def read_only(session_factory):
    """ONE session; its first statement makes the transaction REPEATABLE READ
    and READ ONLY, everything the caller runs is inside it, and it always
    ends with a rollback (nothing is written, nothing is committed)."""
    async with session_factory() as db:
        try:
            await db.execute(text(READ_ONLY_START))
            yield db
        finally:
            await db.rollback()


# -- game selection ------------------------------------------------------------------
#
# Per domain, the distinct games (stable game key and seat pair) one of whose
# records names, by its own attach key, a ranked match of the same pair that
# ended within the last :days days, and none of whose records has had its
# lists purged; in a stable order. Never the passes' processing state.

_TABLES = {"card": "card_evidence", "identity": "identity_clock_evidence",
           "combat": "combat_evidence"}

_GAMES_SQL = (
    "SELECT DISTINCT e.stable_game_key AS k, LEAST(e.seat_player_id, e.other_player_id) AS lo, "
    "       GREATEST(e.seat_player_id, e.other_player_id) AS hi "
    "  FROM {t} e JOIN matches m ON m.photon_room_id = e.attach_key AND m.is_ranked IS TRUE "
    "   AND ((m.player1_id = e.seat_player_id AND m.player2_id = e.other_player_id) "
    "     OR (m.player1_id = e.other_player_id AND m.player2_id = e.seat_player_id)) "
    " WHERE m.ended_at > now() - make_interval(days => CAST(:days AS int)) "
    "   AND NOT EXISTS (SELECT 1 FROM {t} p WHERE p.stable_game_key = e.stable_game_key "
    "       AND LEAST(p.seat_player_id, p.other_player_id) = LEAST(e.seat_player_id, e.other_player_id) "
    "       AND GREATEST(p.seat_player_id, p.other_player_id) "
    "           = GREATEST(e.seat_player_id, e.other_player_id) "
    "       AND p.lists_purged_at IS NOT NULL) "
    " ORDER BY k, lo, hi")

# The passes' per-game reads without their row locks. Card: the evidence rows
# of card_evidence.evaluate_card_game (card_evidence.py:634) with the same
# columns, filter and order; the match is read through card_evidence._MATCH
# itself (no lock clause). Identity: identity_clock_evidence.ice_evaluate_one's
# rows and match (identity_clock_evidence.py:579 and :589). Combat:
# combat_evidence.evaluate_game's rows and match (combat_evidence.py:302 and
# :318).
_CARD_ROWS = text(
    "SELECT id, seat_player_id, other_player_id, attach_key, payload, pool_digest, conflict_at, "
    "       received_at, gen FROM card_evidence "
    "WHERE stable_game_key = :k AND LEAST(seat_player_id, other_player_id) = :lo "
    "  AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id")

_ICE_ROWS = text(
    "SELECT id, seat_player_id, other_player_id, attach_key, payload, header_mod_version, "
    "       conflict_at, conn_class, conn_ranges, post_clock, post_proc, lists_purged_at "
    "  FROM identity_clock_evidence "
    " WHERE stable_game_key = :k AND LEAST(seat_player_id, other_player_id) = :lo "
    "   AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id")

_ICE_MATCH = text(
    "SELECT id, player1_id, player2_id, ended_at, photon_room_id FROM matches "
    "WHERE photon_room_id = ANY(CAST(:keys AS varchar[])) AND is_ranked IS TRUE "
    "  AND ((player1_id = :lo AND player2_id = :hi) OR (player1_id = :hi AND player2_id = :lo)) "
    "  AND ended_at <= now() - make_interval(secs => CAST(:lag AS int)) "
    "ORDER BY ended_at LIMIT CAST(:one AS int)")

_COMBAT_ROWS = text(
    "SELECT id, seat_player_id, other_player_id, attach_key, payload, conflict_at "
    "  FROM combat_evidence WHERE stable_game_key = :k "
    "   AND LEAST(seat_player_id, other_player_id) = :lo "
    "   AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id")

_COMBAT_MATCH = text(
    "SELECT id, photon_room_id, player1_id, player2_id, ended_at FROM matches "
    "WHERE photon_room_id = ANY(CAST(:keys AS varchar[])) AND is_ranked IS TRUE "
    "  AND ((player1_id = :lo AND player2_id = :hi) OR (player1_id = :hi AND player2_id = :lo)) "
    "  AND ended_at <= now() - make_interval(secs => CAST(:lag AS int)) "
    "ORDER BY ended_at LIMIT 1")


def _skip(word):
    return ("skip", word)


class DbFetch:
    """The fetch layer over one read-only session: per domain, one item per
    selected game, either ("skip", word) or ("game", payload). Payloads:
    card (view, UTC day of the match's end), identity (views, registries),
    combat (records)."""

    def __init__(self, db, days: int):
        self.db = db
        self.days = int(days)
        self.selected = {}

    async def games(self, domain):
        if domain not in self.selected:
            sql = text(_GAMES_SQL.format(t=_TABLES[domain]))
            self.selected[domain] = (await self.db.execute(sql, {"days": self.days})).all()
        return self.selected[domain]

    async def totals(self):
        """The number of selected games per domain, read before the walk so
        a cut run can say how many of how many it read."""
        return {d: len(await self.games(d)) for d in DOMAINS}

    async def items(self, domain, rs):
        regs = await ice.ice_registries(self.db) if domain == "identity" else None
        one = {"card": self._card, "identity": self._identity, "combat": self._combat}[domain]
        for key, lo, hi in await self.games(domain):
            yield await one(rs, key, lo, hi, regs)

    async def _card(self, rs, key, lo, hi, _regs):
        # card_evidence.evaluate_card_game with a revision, from its row read
        # on, minus every write: rows, match, attached records, registry,
        # records, the purge check, the report, the view.
        b = {"k": key, "lo": lo, "hi": hi}
        rows = (await self.db.execute(_CARD_ROWS, b)).mappings().all()
        if not rows:
            return _skip("empty")
        keys = sorted({r["attach_key"] for r in rows})
        match = (await self.db.execute(ce._MATCH, {"keys": keys, "lo": lo, "hi": hi,
                                                   "lag": se.READY_LAG_S})).mappings().first()
        if match is None:
            return _skip("nomatch")
        named, _other = se.attached_records(rows, match)
        if not named:
            return _skip("unnamed")
        digests = {r["pool_digest"] for r in rows if r["pool_digest"]}
        registry = await ce._registry(self.db, digests, {})
        records = ce._records(named)
        if any(not ce._has_lists(r["rec"]) for r in records):
            return _skip("purged")
        report = await ce._report(self.db, match["id"])
        try:
            view = cm.card_view(records, registry, match["sc"], rs.params.get(cm.WEIGHTS), report)
        except Exception:                     # noqa: BLE001 -- the pass records it as a fault
            return _skip("fault")
        return ("game", (view, match["ended_at"].astimezone(timezone.utc).date()))

    async def _identity(self, rs, key, lo, hi, regs):
        # identity_clock_evidence.ice_evaluate_one with a revision: evaluated
        # only with a match, at least one named record and no named record
        # whose lists are purged (identity_clock_evidence.py:634).
        rows = (await self.db.execute(_ICE_ROWS, {"k": key, "lo": lo, "hi": hi})).mappings().all()
        if not rows:
            return _skip("empty")
        keys = sorted({r["attach_key"] for r in rows})
        match = (await self.db.execute(_ICE_MATCH, {"keys": keys, "lo": lo, "hi": hi,
                                                    "lag": ice.ICE_READY_LAG_S, "one": 1})
                 ).mappings().first()
        if match is None:
            return _skip("nomatch")
        named, _other = se.attached_records(rows, match)
        if not named:
            return _skip("unnamed")
        if any(r["lists_purged_at"] is not None for r in named):
            return _skip("purged")
        views = await ice.ice_views(self.db, key, named)
        return ("game", (views, regs))

    async def _combat(self, rs, key, lo, hi, _regs):
        # combat_evidence.evaluate_game with a revision: only the records
        # whose attach key IS the match's room (combat_evidence.py:356), none
        # with a purged list (PURGED_LISTS). A game with a match and no such
        # record is skipped as unnamed here (the pass would hand the empty
        # list to the evaluator).
        rows = (await self.db.execute(_COMBAT_ROWS, {"k": key, "lo": lo, "hi": hi})).mappings().all()
        if not rows:
            return _skip("empty")
        keys = sorted({r["attach_key"] for r in rows})
        match = (await self.db.execute(_COMBAT_MATCH, {"keys": keys, "lo": lo, "hi": hi,
                                                       "lag": se.READY_LAG_S})).mappings().first()
        if match is None:
            return _skip("nomatch")
        attach = match["photon_room_id"]
        records = [{"seat": r["seat_player_id"], "other": r["other_player_id"],
                    "rec": cev._jsonv(r["payload"])} for r in rows if r["attach_key"] == attach]
        if not records:
            return _skip("unnamed")
        if any(not cev._has_lists(r["rec"]) for r in records):
            return _skip("purged")
        # The pass rebuilds each record's fault rows before it evaluates, in
        # the same try: when a rebuild raises it stores the fault and
        # evaluates nothing (combat_evidence.py:369-376). Neither does the
        # tool: the game is counted under its own word.
        try:
            for r in records:
                cbm.rebuild_faults(r["rec"], "s")
                cbm.rebuild_faults(r["rec"], "o")
                cbm.section_faults(r["rec"])
        except Exception:                     # noqa: BLE001 -- the pass's fault, not a rule error
            return _skip("rebuild_fault")
        return ("game", records)


# -- the card windows, rebuilt in memory ----------------------------------------------
#
# A revision the server has not loaded has no daily rows, so the windows are
# rebuilt here from each walked game's contributions, keyed and summed as the
# pass keys and sums them:
#   * contributions: card_measures.contributions(view), one row per
#     (recorder, dealer, source, profile) (card_measures.py:1062), on the UTC
#     date of the match's end (card_evidence._write_contrib,
#     card_evidence.py:407-422);
#   * daily rows: card_evidence._recompute_daily (card_evidence.py:382-401),
#     keyed (subject, day, source, coverage, profile, revision) -- one
#     revision here, so the revision drops out of the key -- summing every
#     _DAILY_COLS column and counting the distinct games;
#   * windows: card_evidence._windows (card_evidence.py:457-504): with the
#     revision's window width w, a window ends on every day a class (subject,
#     source, coverage, profile) has a daily row and sums the class's daily
#     rows of the w days ending there; without the window parameter there is
#     no window.
# Games before the selected days are not read, so a window ending in the
# first w - 1 selected days sums only the selected part of it.

_DAILY_COLS = ce._DAILY_COLS
_SUM_COLS = ce._SUM_COLS


def add_contributions(daily: dict, view, day, game) -> None:
    """Add one game's contributions to the in-memory daily rows. `game` is an
    opaque per-walk game number (it stands for the stable key and pair the
    pass counts DISTINCT)."""
    for c in cm.contributions(view):
        key = (c["subject"], day, c["source"], c["coverage"], c["profile"])
        row = daily.get(key)
        if row is None:
            row = daily[key] = dict.fromkeys(_DAILY_COLS, 0)
            row["games"] = set()
        row["games"].add(game)
        row["hands"] += c["hands"]
        row["slots"] += c["slots"]
        row["notrun_hands"] += c["notrun_hands"]
        for part in ("obs", "exp", "var"):
            for i, name in enumerate(cm.RARITIES):
                row[part + "_" + name] += c[part][i]


def rebuild_windows(daily: dict, rs) -> list:
    """[((subject, end day, source, coverage, profile), agg)] in the pass's
    order (class, then end day); agg in the form card_measures.window_row
    reads. Empty without the revision's window parameter."""
    win = rs.params.get(cm.WINDOW)
    if not win:
        return []
    w = int(win[cm.WINDOW_KEY])
    classes = {}
    for (subject, day, source, coverage, profile), row in daily.items():
        classes.setdefault((subject, source, coverage, profile), {})[day] = row
    out = []
    for cls in sorted(classes):
        subject, source, coverage, profile = cls
        by_day = classes[cls]
        for e in sorted(by_day):
            sums = dict.fromkeys(_SUM_COLS, 0)
            for d, r in by_day.items():
                if e - timedelta(days=w) < d <= e:
                    sums["games"] += len(r["games"])
                    for c in _DAILY_COLS:
                        sums[c] += int(r[c])
            agg = {c: sums[c] for c in ("games", "hands", "slots", "notrun_hands")}
            agg.update(source=source, coverage=coverage)
            for part in ("obs", "exp", "var"):
                agg[part] = [sums[part + "_" + name] for name in cm.RARITIES]
            out.append(((subject, e, source, coverage, profile), agg))
    return out


# -- the counting core ---------------------------------------------------------------

def one_rule(rs, rule):
    """A shallow copy of the ruleset holding only `rule` (the scope lists are
    computed from .rules, review_rules.py:353-371)."""
    single = copy.copy(rs)
    single.rules = [rule]
    return single


class Tally:
    """Per rule, alone: evaluated, fired, errors. Per domain: games walked and
    games skipped by word."""

    def __init__(self, rs):
        self.rs = rs
        self.rules = [r for r in rs.rules if r.scope in COUNTED_SCOPES]
        self.uncounted = len(rs.rules) - len(self.rules)
        self.single = {r.id: one_rule(rs, r) for r in self.rules}
        self.counts = {r.id: {"scope": r.scope, "evaluated": 0, "fired": 0, "errors": 0}
                       for r in self.rules}
        self.domains = {d: {"walked": 0, "skipped": {}} for d in DOMAINS}
        self.daily = {}
        self.windows = 0              # card windows evaluated
        self.windows_total = None     # card windows rebuilt (None: none rebuilt)
        self.totals = {d: None for d in DOMAINS}
        self.cut = None               # the word of what ended the walk early, or None

    def _scope(self, scope):
        return [r for r in self.rules if r.scope == scope]

    def _count(self, rule, call):
        row = self.counts[rule.id]
        row["evaluated"] += 1
        try:
            res = call(self.single[rule.id])
        except Exception:                     # noqa: BLE001 -- counted as the rule's error
            row["errors"] += 1
            return
        *_findings, fired, errors = res
        if rule.id in fired:
            row["fired"] += 1
        row["errors"] += errors

    def skip(self, domain, word):
        sk = self.domains[domain]["skipped"]
        sk[word] = sk.get(word, 0) + 1

    def game(self, domain, payload):
        self.domains[domain]["walked"] += 1
        getattr(self, "_" + domain)(payload)

    def _card(self, payload):
        view, day = payload
        subjects = cm.card_subjects(view, [])
        for rule in self._scope("card"):
            if rule.subject != cm.WINDOW_SUBJECT:
                self._count(rule, lambda s: s.evaluate_card(subjects))
        add_contributions(self.daily, view, day, self.domains["card"]["walked"])

    def _identity(self, payload):
        views, regs = payload
        for rule in self._scope("identity"):
            self._count(rule, lambda s: s.evaluate_identity(views, regs))

    def _combat(self, records):
        for rule in self._scope("combat"):
            self._count(rule, lambda s: s.evaluate_combat(records))

    def finish(self, deadline_at=None, clock=time.monotonic):
        """The card windows: every rebuilt window, each card.window rule
        evaluated once per window, until the deadline (checked before every
        window). A walk already cut rebuilds no window."""
        if self.cut:
            return self
        wins = rebuild_windows(self.daily, self.rs)
        self.windows_total = len(wins)
        rules = [r for r in self._scope("card") if r.subject == cm.WINDOW_SUBJECT]
        for _key, agg in wins:
            self.cut = _ended(deadline_at, clock)
            if self.cut:
                break
            self.windows += 1
            subjects = cm.card_subjects({}, [cm.window_row(agg)])
            for rule in rules:
                self._count(rule, lambda s: s.evaluate_card(subjects))
        return self


async def walk(rs, fetch, deadline_at=None, clock=time.monotonic) -> Tally:
    """Every domain's items from `fetch` (each domain in its own pass)
    through the counting core, until the deadline or a stop signal: checked
    before each domain and after every game or skip; a walk either ends is
    marked cut and reads nothing more."""
    tally = Tally(rs)
    totals = getattr(fetch, "totals", None)
    if totals is not None:
        tally.totals.update(await totals())
    for domain in DOMAINS:
        tally.cut = _ended(deadline_at, clock)
        if tally.cut:
            break
        items = fetch.items(domain, rs)
        try:
            async for kind, payload in items:
                if kind == "skip":
                    tally.skip(domain, payload)
                else:
                    tally.game(domain, payload)
                tally.cut = _ended(deadline_at, clock)
                if tally.cut:
                    break
        finally:
            await items.aclose()
        if tally.cut:
            break
    return tally.finish(deadline_at, clock)


async def walk_db(rs, session_factory, days: int, deadline_at=None) -> Tally:
    async with read_only(session_factory) as db:
        return await walk(rs, DbFetch(db, days), deadline_at)


def render(tally: Tally) -> list:
    """The report. First the summary line: `run whole` with the games read
    of the games selected, or `run cut (<word>)` (deadline: the run's own
    deadline; stopped: SIGTERM) with how many games of how many it read and
    how many card windows of how many it evaluated. Then one line per counted rule, one per domain and
    one for the rules not counted, each beginning `cut ` in a cut run, so no
    count of a cut run reads as whole. Rule ids, scopes, words and counts
    only."""
    read = {d: tally.domains[d]["walked"] + sum(tally.domains[d]["skipped"].values())
            for d in DOMAINS}
    tot = {d: read[d] if tally.totals[d] is None else tally.totals[d] for d in DOMAINS}
    parts = ", ".join("%s %d of %d" % (d, read[d], tot[d]) for d in DOMAINS)
    if tally.cut:
        lines = ["run cut (%s): games read %d of %d (%s); card windows evaluated %d of %s; "
                 "every count below covers only what was read"
                 % (tally.cut, sum(read.values()), sum(tot.values()), parts, tally.windows,
                    "none rebuilt" if tally.windows_total is None else tally.windows_total)]
    else:
        lines = ["run whole: games read %d of %d (%s)" % (sum(read.values()), sum(tot.values()),
                                                           parts)]
    pre = "cut " if tally.cut else ""
    for rule in tally.rules:
        c = tally.counts[rule.id]
        lines.append(pre + "rule %s scope=%s evaluated=%d fired=%d errors=%d"
                     % (rule.id, c["scope"], c["evaluated"], c["fired"], c["errors"]))
    for domain in DOMAINS:
        d = tally.domains[domain]
        line = "domain %s walked=%d" % (domain, d["walked"])
        if domain == "card":
            line += " windows=%d" % tally.windows
        line += " skipped=%d" % sum(d["skipped"].values())
        for word in sorted(d["skipped"]):
            line += " %s=%d" % (word, d["skipped"][word])
        lines.append(pre + line)
    lines.append(pre + "game and sitting rules not counted: %d" % tally.uncounted)
    return lines


async def _run(rs, days, deadline_at=None):
    import database                           # the api's engine and session factory
    try:
        return await walk_db(rs, database.async_session, days, deadline_at)
    finally:
        await database.engine.dispose()


def main(argv=None) -> int:
    start = time.monotonic()                  # the deadline counts the whole run, loading included
    p = argparse.ArgumentParser(prog="review_calibrate.py",
                                description="Count each card, identity and combat rule of a "
                                            "named revision over recorded evidence, read only.")
    p.add_argument("--revision", required=True)
    p.add_argument("--days", required=True, type=int)
    p.add_argument("--deadline-s", type=int, default=DEFAULT_DEADLINE_S, dest="deadline_s",
                   help="end the walk after this many seconds and say it was cut "
                        "(default %d, at most %d)" % (DEFAULT_DEADLINE_S, DEADLINE_MAX_S))
    args = p.parse_args(argv)
    if not 0 < args.days <= cm.WINDOW_DAYS_MAX:
        print("refused (days)")
        return EXIT_USAGE
    if not 0 < args.deadline_s <= DEADLINE_MAX_S:
        print("refused (deadline)")
        return EXIT_USAGE
    try:
        path = revision_path(args.revision)
    except PathRefused as e:
        print("refused (path %s)" % e.word)
        return EXIT_USAGE
    try:
        rs = rr.load_dir(path)
    except rr.Refused as e:
        print("refused (%s)" % e.cls)
        return EXIT_REFUSED
    print("revision %s days %d deadline_s %d" % (rs.rev, args.days, args.deadline_s), flush=True)
    _STOP["word"] = None
    before = signal.signal(signal.SIGTERM, _on_term)
    try:
        tally = asyncio.run(_run(rs, args.days, start + args.deadline_s))
    finally:
        signal.signal(signal.SIGTERM, before)
    for line in render(tally):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
