"""Rule calibration over recorded evidence (tier 2), read only.

Run in the api container against its database. Three modes:

  count         --revision <root>/rules-<12 hex> --days <n> [--deadline-s <s>]
  cohort        --cohort --days <n> [--deadline-s <s>]
  cohort check  --cohort-check --rev <12 hex> --at <YYYY-MM-DDTHH:MM:SSZ> --digest <sha-256 hex>
                --days <n> [--deadline-s <s>]

COUNT. For every rule of scope card, identity and combat in the named
revision, alone, the tool counts how many games (a card window rule: how
many windows) it was evaluated on, how many of them it fired on and how many
rule errors it raised, over the games whose CANONICAL match (below) ended
within the last <n> days. It prints one line per rule and one line per
evidence domain (games walked, games skipped by the word of the step that
skipped them).

COHORT. The install signal's population (design section g): the games a
pass would evaluate, fixed at one instant T: per domain, the games with a
record received by T whose canonical match as of T ended within <n> days of
T and whose attached records were not purged by T. It prints T, the member
count per domain and ONE digest over the member set; never a member.
COHORT CHECK re-derives the same set from T, refuses (`cohort differs`) when
its digest is not the one given, and otherwise counts, for those members
only, how many the revision (--rev) has evaluated, how many wait, how many
had their lists purged after T and how many failed, each apart.

THE CANONICAL MATCH of a game (stable key and seat pair) in a domain is the
match each evidence pass picks: among the ranked matches of the pair that
one of the game's records names by its own attach key and that ended at
least the pass's ready lag ago, the one that ended first. The tool chooses
it FIRST, in its selection statement; the days bound applies to that match
alone (a game admitted through a recent attachment whose canonical match is
older is counted under `outside` and not evaluated), and that same match is
the one the walk reads for the game. Retention is checked on the records
attached to that match, as the passes check it (card_evidence.py:668,
identity_clock_evidence.py:630, combat_evidence.py:361): a purged record
that names another match does not remove the game.

WHAT THE TOOL REPRODUCES OF THE PASSES, and what it does not. It
reproduces their attachment (the canonical match, the attached records),
their retention check on the attached records, the card fault on building
the view and the combat fault on rebuilding the fault rows (each counted
under its own word, nothing evaluated). It does NOT reproduce their
processing state: finalized games, the evaluated revision, retries, parking
and worker switches are ignored, so the tool counts games a pass would skip
as already done, and its card windows are rebuilt once over the selected
games (see the window section) where a pass's stored windows change as
contributions arrive and retire.

OUTPUT. Rule ids, scopes, fixed words, counts, the instant T and the one
digest; never a Steam id, a player name, a game key, a match id, an
address, a path, a supplied argument value or an exception's text. Every
refusal and every failure prints ONE fixed line on standard output and
nothing on standard error: the arguments are read by the tool's own reader
(no library diagnostics), and one outermost handler turns any exception into
`failed (<class word>)` with a non-zero status. While main() runs, standard
error is a sink, warnings are off and unraisable exceptions are dropped.

The count report is written as ONE write after the walk, ending with the
line `report end`. A run killed before that write leaves only the first
line (`revision ... days ... deadline_s ...`); a kill during the write can
leave a prefix of the report, which lacks its `report end` line: a report
without that last line is incomplete and is not read.

THE DEADLINE (--deadline-s, default DEFAULT_DEADLINE_S, at most
DEADLINE_MAX_S, counted from the start of main()). The walk runs as one task
under a timer: at the deadline the task is cancelled, which cancels the
statement in flight (the driver sends PostgreSQL's cancel request), and the
run is reported as cut. Inside the walk the deadline is also checked before
each domain, after every game, inside the card window rebuild (per class and
end day) and before every window. SIGTERM cancels the walk the same way
(word `stopped`). The connection's own statement_timeout and
idle_in_transaction_session_timeout are the deadline plus CANCEL_SLACK_S, so
the server ends any statement of this run by then whatever the client does.
The report is printed at most CANCEL_SLACK_S after the deadline: when a
cancelled task has not ended by then it is abandoned (its connection is
dropped with the process). THE OUTER BOUND IS PART OF THE CONTRACT: the
server verb that runs this tool runs it under a time limit of the deadline
plus VERB_SLACK_S seconds, sending SIGTERM, and kills it VERB_KILL_AFTER_S
seconds later (`timeout -s TERM -k <VERB_KILL_AFTER_S> <deadline + VERB_SLACK_S>`).

WHAT IT NEVER DOES:

  * follow the review root's `current` pointer: the revision argument's
    FORM is checked before any filesystem lookup -- exactly the fixed review
    root (review_rules.rules_root()), one separator, then one component
    `rules-` and twelve lower-case hex -- so no component of it can be the
    pointer; that one component is then examined with lstat (a link or a
    junction is refused, never followed) and loaded whole by
    review_rules.load_dir (seal, closure fingerprint, every self-test);
  * write, lock or change a session setting: its connection is opened with
    the startup parameters default_transaction_read_only=on,
    default_transaction_isolation=repeatable read, statement_timeout,
    idle_in_transaction_session_timeout and jit=off, so EVERY transaction on
    it, the driver's own included, is read-only from the first statement.
    The first statement the connection sends is the BEGIN of the SQL
    dialect's first-connect initialization; the run's own transaction is
    begun as REPEATABLE READ READ ONLY and always ends with a rollback.
    The driver's type introspection would otherwise send set_config('jit')
    around its catalog read; with jit off at startup the tool marks the
    connection as one without JIT (asyncpg's server capability flag), so the
    introspection is a plain catalog SELECT and no statement that changes a
    setting is sent. The per-game reads are the passes' reads without their
    row locks; the passes' per-game functions, which write and lock, are not
    called.

This module is outside the review code closure; nothing here changes what a
revision's closure fingerprint covers.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import logging
import os
import re
import signal
import stat
import sys
import time
import warnings
from datetime import datetime, timedelta, timezone

DOMAINS = ("card", "identity", "combat")
COUNTED_SCOPES = DOMAINS
EXIT_REFUSED = 1
EXIT_USAGE = 2
EXIT_FAILED = 3

try:
    from sqlalchemy import text

    import review_boot  # noqa: F401 -- FIRST: the closure modules execute from source only (review_boot.py:13)
    import card_measures as cm
    import combat_measures as cbm
    import review_rules as rr
    import card_evidence as ce
    import combat_evidence as cev
    import identity_clock_evidence as ice
    import seat_evidence as se
except BaseException:                         # noqa: BLE001 -- a run prints a fixed word, an import re-raises
    if __name__ == "__main__":
        sys.stdout.write("failed (import)\n")
        sys.stdout.flush()
        os._exit(EXIT_FAILED)
    raise

DEFAULT_DEADLINE_S = 1200
DEADLINE_MAX_S = 7200
CANCEL_SLACK_S = 5          # after the deadline: the cancelled walk's own end, at most
CLOSE_SLACK_S = 5           # after the report: the engine's disposal, at most
VERB_SLACK_S = 30           # the server verb's time limit is the deadline plus this
VERB_KILL_AFTER_S = 10      # and it kills the process this long after its SIGTERM

# Fixed words. Every refusal and failure line is built from these alone.
ARG_WORDS = ("arguments", "days", "deadline", "rev", "at", "digest")
PATH_WORDS = ("root", "pointer", "name", "missing", "link")
FAILURE_WORDS = ("interrupted", "exit", "memory", "timeout", "config", "driver", "database",
                 "system", "internal")
_LOADER_CLASS = re.compile(r"[a-z][a-z_]{0,31}", re.ASCII)

_STOP = {"word": None, "task": None}


class Refused(Exception):
    """A refusal: `line` is printed, `code` is the exit status."""

    def __init__(self, line: str, code: int):
        super().__init__(line)
        self.line = line
        self.code = code


class PathRefused(Exception):
    def __init__(self, word: str):
        super().__init__(word)
        self.word = word


class ConfigRefused(Exception):
    """The database address carries options the tool does not pass on."""


class DriverRefused(Exception):
    """The driver connection lacks the capability flag the tool clears."""


def _on_term(signum, frame):
    """SIGTERM: end the walk now, as a cut run (the task in flight is cancelled)."""
    _STOP["word"] = "stopped"
    held = _STOP.get("task")
    if held is not None:
        loop, task = held
        loop.call_soon_threadsafe(task.cancel)


def _ended(deadline_at, clock):
    """The word that ends the walk now, or None."""
    if _STOP["word"]:
        return _STOP["word"]
    if deadline_at is not None and clock() >= deadline_at:
        return "deadline"
    return None


# -- the arguments ----------------------------------------------------------------------
#
# The tool's own reader: `--name value` pairs and two bare flags, nothing
# else. Every refusal is a fixed word; no value is ever repeated.

_VALUED = ("--revision", "--days", "--deadline-s", "--rev", "--at", "--digest")
_FLAGS = ("--cohort", "--cohort-check")
_MODES = {
    "count": ({"--revision", "--days"}, {"--deadline-s"}),
    "cohort": ({"--cohort", "--days"}, {"--deadline-s"}),
    "check": ({"--cohort-check", "--rev", "--at", "--digest", "--days"}, {"--deadline-s"}),
}
_DIGITS = re.compile(r"[0-9]{1,5}", re.ASCII)
_REV = re.compile(r"[0-9a-f]{12}", re.ASCII)
_AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}", re.ASCII)


def _refuse(word):
    return Refused("refused (%s)" % word, EXIT_USAGE)


def parse_args(argv) -> dict:
    """{'mode': ..., option: value} or Refused with a fixed word."""
    if not isinstance(argv, (list, tuple)) or not all(isinstance(a, str) for a in argv):
        raise _refuse("arguments")
    seen = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in seen:
            raise _refuse("arguments")
        if tok in _FLAGS:
            seen[tok] = True
            i += 1
        elif tok in _VALUED:
            if i + 1 >= len(argv):
                raise _refuse("arguments")
            seen[tok] = argv[i + 1]
            i += 2
        else:
            raise _refuse("arguments")
    modes = [m for m, (need, _opt) in _MODES.items() if need <= set(seen)]
    if len(modes) != 1:
        raise _refuse("arguments")
    mode = modes[0]
    need, opt = _MODES[mode]
    if set(seen) - need - opt:
        raise _refuse("arguments")
    out = {"mode": mode}
    days = seen["--days"]
    if not _DIGITS.fullmatch(days) or not 0 < int(days) <= cm.WINDOW_DAYS_MAX:
        raise _refuse("days")
    out["days"] = int(days)
    dl = seen.get("--deadline-s", str(DEFAULT_DEADLINE_S))
    if not _DIGITS.fullmatch(dl) or not 0 < int(dl) <= DEADLINE_MAX_S:
        raise _refuse("deadline")
    out["deadline_s"] = int(dl)
    if mode == "count":
        out["revision"] = seen["--revision"]
    if mode == "check":
        if not _REV.fullmatch(seen["--rev"]):
            raise _refuse("rev")
        out["rev"] = seen["--rev"]
        at = seen["--at"]
        try:
            ok = bool(_AT.fullmatch(at)) and time.strptime(at, "%Y-%m-%dT%H:%M:%SZ") is not None
        except ValueError:
            ok = False
        if not ok:
            raise _refuse("at")
        out["at"] = at
        if not _DIGEST.fullmatch(seen["--digest"]):
            raise _refuse("digest")
        out["digest"] = seen["--digest"]
    return out


# -- the revision path --------------------------------------------------------------------

_REVISION_NAME = re.compile(r"rules-[0-9a-f]{%d}" % rr.CONTRACT_BOUNDS["rev_hex"], re.ASCII)
_REFUSED_NAMES = (rr.POINTER, rr.NONE_TARGET)
_SEPS = tuple(sorted({"/", os.sep}))


def _is_link(st) -> bool:
    if stat.S_ISLNK(st.st_mode):
        return True
    tag = getattr(st, "st_reparse_tag", 0)        # Windows: a junction or other reparse point
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(tag) or bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def revision_path(arg: str) -> str:
    """The revision directory to load, or PathRefused. The FORM is checked
    first, with no filesystem call: the fixed root exactly, one separator,
    then exactly one component, which is neither the pointer nor
    `rules-none` and is `rules-` and twelve lower-case hex. Only then is that
    one component examined, with lstat (never followed): a link or a
    junction is refused, as is anything but a directory."""
    if not isinstance(arg, str) or not arg:
        raise PathRefused("name")
    root = rr.rules_root().rstrip("".join(_SEPS))
    rest = None
    for sep in _SEPS:
        if arg.startswith(root + sep):
            rest = arg[len(root) + 1:]
            break
    if rest is None or not root:
        raise PathRefused("root")
    first = re.split("|".join(re.escape(s) for s in _SEPS), rest, maxsplit=1)[0]
    if first in _REFUSED_NAMES:
        raise PathRefused("pointer")
    if first != rest or not _REVISION_NAME.fullmatch(rest):
        raise PathRefused("name")
    path = root + os.sep + rest
    try:
        st = os.lstat(path)
    except OSError:
        raise PathRefused("missing") from None
    if _is_link(st):
        raise PathRefused("link")
    if not stat.S_ISDIR(st.st_mode):
        raise PathRefused("missing")
    return path


# -- the connection ---------------------------------------------------------------------

def server_settings(deadline_s: int) -> dict:
    """The connection's startup parameters (sent in the startup packet, not as
    statements)."""
    ms = str((int(deadline_s) + CANCEL_SLACK_S) * 1000)
    return {"default_transaction_read_only": "on",
            "default_transaction_isolation": "repeatable read",
            "statement_timeout": ms,
            "idle_in_transaction_session_timeout": ms,
            "jit": "off"}


class _RecordingProtocol:
    """The driver protocol with every SQL text it is handed recorded (tests):
    prepare (every statement with parameters and every prepared one),
    query (the simple-query path: BEGIN, ROLLBACK, statements without
    parameters), copy_out and copy_in. Everything else passes through."""

    def __init__(self, proto, log):
        self._proto = proto
        self._log = log

    def __getattr__(self, name):
        return getattr(self._proto, name)

    def prepare(self, stmt_name, query, *a, **k):
        self._log.append(query)
        return self._proto.prepare(stmt_name, query, *a, **k)

    def query(self, query, *a, **k):
        self._log.append(query)
        return self._proto.query(query, *a, **k)

    def copy_out(self, copy_stmt, *a, **k):
        self._log.append(copy_stmt)
        return self._proto.copy_out(copy_stmt, *a, **k)

    def copy_in(self, copy_stmt, *a, **k):
        self._log.append(copy_stmt)
        return self._proto.copy_in(copy_stmt, *a, **k)


async def _connect(args: dict, settings: dict, recorder=None):
    import asyncpg
    conn = await asyncpg.connect(**args, server_settings=settings)
    try:
        caps = conn._server_caps
        conn._server_caps = caps._replace(jit=False)
    except Exception:                         # noqa: BLE001 -- refused by a fixed word
        conn.terminate()
        raise DriverRefused() from None
    if recorder is not None:
        conn._protocol = _RecordingProtocol(conn._protocol, recorder)
    return conn


def session_factory(deadline_s: int, url=None, recorder=None, extra_settings=None):
    """(engine, session maker) over the api's database (or `url`): one
    connection per session (NullPool), opened by _connect with the read-only
    startup parameters; every session's transaction is REPEATABLE READ READ
    ONLY. `recorder` (a list) receives every SQL text the connection sends;
    `extra_settings` adds startup parameters (tests: the case schema's
    search_path)."""
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool
    import database                           # the api's engine builder (hide_parameters=True)
    u = make_url(database.DATABASE_URL if url is None else url)
    if u.query:
        raise ConfigRefused()
    args = u.translate_connect_args(username="user")
    settings = server_settings(deadline_s)
    settings.update(extra_settings or {})
    engine = database.create_async_engine(
        u, poolclass=NullPool, isolation_level="REPEATABLE READ",
        execution_options={"postgresql_readonly": True},
        async_creator=lambda: _connect(args, settings, recorder))
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@contextlib.asynccontextmanager
async def read_only(session_factory):
    """ONE session; everything the caller runs is inside its one transaction,
    which always ends with a rollback (nothing is written, nothing is
    committed). The read-only property is the connection's (session_factory);
    nothing here sends a statement of its own."""
    async with session_factory() as db:
        try:
            yield db
        finally:
            await db.rollback()


# -- game selection: the canonical match first ----------------------------------------------
#
# Per domain: the games (stable game key and seat pair) one of whose records
# names, by its own attach key, a ranked match of the same pair that ended
# within the last :days days (the candidates), each with its CANONICAL match
# (the pass's choice: the earliest ranked match of the pair, named by any of
# the game's records, that ended at least :lag seconds ago) and whether THAT
# match ended within :days days. No purge filter here: retention is checked
# per game on the attached records. Never the passes' processing state.

_TABLES = {"card": "card_evidence", "identity": "identity_clock_evidence",
           "combat": "combat_evidence"}
_GAMES_TABLES = {"card": "card_games", "identity": "identity_clock_games",
                 "combat": "combat_games"}

_PAIR_E = ("LEAST(e.seat_player_id, e.other_player_id)", "GREATEST(e.seat_player_id, e.other_player_id)")

_GAMES_SQL = (
    "WITH cand AS ("
    " SELECT DISTINCT e.stable_game_key AS k, " + _PAIR_E[0] + " AS lo, " + _PAIR_E[1] + " AS hi"
    "   FROM {t} e JOIN matches m ON m.photon_room_id = e.attach_key AND m.is_ranked IS TRUE"
    "    AND ((m.player1_id = e.seat_player_id AND m.player2_id = e.other_player_id)"
    "      OR (m.player1_id = e.other_player_id AND m.player2_id = e.seat_player_id))"
    "  WHERE m.ended_at > now() - make_interval(days => CAST(:days AS int))), "
    "canon AS ("
    " SELECT DISTINCT ON (c.k, c.lo, c.hi) c.k, c.lo, c.hi, m.id AS mid, m.ended_at AS ended"
    "   FROM cand c JOIN {t} e ON e.stable_game_key = c.k"
    "    AND " + _PAIR_E[0] + " = c.lo AND " + _PAIR_E[1] + " = c.hi"
    "   JOIN matches m ON m.photon_room_id = e.attach_key AND m.is_ranked IS TRUE"
    "    AND ((m.player1_id = c.lo AND m.player2_id = c.hi) OR (m.player1_id = c.hi AND m.player2_id = c.lo))"
    "    AND m.ended_at <= now() - make_interval(secs => CAST(:lag AS int))"
    "  ORDER BY c.k, c.lo, c.hi, m.ended_at) "
    "SELECT c.k, c.lo, c.hi, n.mid, "
    "       (n.ended > now() - make_interval(days => CAST(:days AS int))) AS recent"
    "  FROM cand c LEFT JOIN canon n ON n.k = c.k AND n.lo = c.lo AND n.hi = c.hi"
    " ORDER BY c.k, c.lo, c.hi")

_LAGS = {"card": se.READY_LAG_S, "identity": ice.ICE_READY_LAG_S, "combat": se.READY_LAG_S}

# The passes' per-game reads without their row locks. Card: the evidence rows
# of card_evidence.evaluate_card_game (card_evidence.py:634) with the same
# columns, filter and order. Identity: identity_clock_evidence.ice_evaluate_one's
# rows (identity_clock_evidence.py:579). Combat: combat_evidence.evaluate_game's
# rows (combat_evidence.py:302). The match is the canonical one, read by its id
# with the columns each pass reads (card: card_evidence._MATCH's select list,
# series classification included).
_CARD_ROWS = text(
    "SELECT id, seat_player_id, other_player_id, attach_key, payload, pool_digest, conflict_at, "
    "       received_at, gen FROM card_evidence "
    "WHERE stable_game_key = :k AND LEAST(seat_player_id, other_player_id) = :lo "
    "  AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id")

_CARD_MATCH = text(ce._MATCH.text.split(" WHERE ", 1)[0] + " WHERE m.id = :mid")

_ICE_ROWS = text(
    "SELECT id, seat_player_id, other_player_id, attach_key, payload, header_mod_version, "
    "       conflict_at, conn_class, conn_ranges, post_clock, post_proc, lists_purged_at "
    "  FROM identity_clock_evidence "
    " WHERE stable_game_key = :k AND LEAST(seat_player_id, other_player_id) = :lo "
    "   AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id")

_ICE_MATCH = text("SELECT id, player1_id, player2_id, ended_at, photon_room_id FROM matches "
                  "WHERE id = :mid")

_COMBAT_ROWS = text(
    "SELECT id, seat_player_id, other_player_id, attach_key, payload, conflict_at "
    "  FROM combat_evidence WHERE stable_game_key = :k "
    "   AND LEAST(seat_player_id, other_player_id) = :lo "
    "   AND GREATEST(seat_player_id, other_player_id) = :hi ORDER BY id")

_COMBAT_MATCH = text("SELECT id, photon_room_id, player1_id, player2_id, ended_at FROM matches "
                     "WHERE id = :mid")


def _skip(word):
    return ("skip", word)


class DbFetch:
    """The fetch layer over one read-only session: per domain, one item per
    selected game, either ("skip", word) or ("game", payload). Payloads:
    card (view, UTC day of the canonical match's end), identity (views,
    registries), combat (records)."""

    def __init__(self, db, days: int):
        self.db = db
        self.days = int(days)
        self.selected = {}

    async def games(self, domain):
        if domain not in self.selected:
            sql = text(_GAMES_SQL.format(t=_TABLES[domain]))
            self.selected[domain] = (await self.db.execute(
                sql, {"days": self.days, "lag": _LAGS[domain]})).all()
        return self.selected[domain]

    async def totals(self):
        """The number of selected games per domain, read before the walk so
        a cut run can say how many of how many it read."""
        return {d: len(await self.games(d)) for d in DOMAINS}

    async def items(self, domain, rs):
        regs = await ice.ice_registries(self.db) if domain == "identity" else None
        one = {"card": self._card, "identity": self._identity, "combat": self._combat}[domain]
        for key, lo, hi, mid, recent in await self.games(domain):
            if mid is None:
                yield _skip("nomatch")
            elif not recent:
                yield _skip("outside")
            else:
                yield await one(rs, key, lo, hi, mid, regs)

    async def _card(self, rs, key, lo, hi, mid, _regs):
        # card_evidence.evaluate_card_game with a revision, from its row read
        # on, minus every write: rows, the canonical match, attached records,
        # registry, records, the purge check, the report, the view.
        b = {"k": key, "lo": lo, "hi": hi}
        rows = (await self.db.execute(_CARD_ROWS, b)).mappings().all()
        if not rows:
            return _skip("empty")
        match = (await self.db.execute(_CARD_MATCH, {"mid": mid})).mappings().first()
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

    async def _identity(self, rs, key, lo, hi, mid, regs):
        # identity_clock_evidence.ice_evaluate_one with a revision: evaluated
        # only with a match, at least one attached record and no attached
        # record whose lists are purged (identity_clock_evidence.py:634).
        rows = (await self.db.execute(_ICE_ROWS, {"k": key, "lo": lo, "hi": hi})).mappings().all()
        if not rows:
            return _skip("empty")
        match = (await self.db.execute(_ICE_MATCH, {"mid": mid})).mappings().first()
        if match is None:
            return _skip("nomatch")
        named, _other = se.attached_records(rows, match)
        if not named:
            return _skip("unnamed")
        if any(r["lists_purged_at"] is not None for r in named):
            return _skip("purged")
        views = await ice.ice_views(self.db, key, named)
        return ("game", (views, regs))

    async def _combat(self, rs, key, lo, hi, mid, _regs):
        # combat_evidence.evaluate_game with a revision: only the records
        # whose attach key IS the match's room (combat_evidence.py:356), none
        # with a purged list (PURGED_LISTS). A game with a match and no such
        # record is skipped as unnamed here (the pass would hand the empty
        # list to the evaluator).
        rows = (await self.db.execute(_COMBAT_ROWS, {"k": key, "lo": lo, "hi": hi})).mappings().all()
        if not rows:
            return _skip("empty")
        match = (await self.db.execute(_COMBAT_MATCH, {"mid": mid})).mappings().first()
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
#     date of the canonical match's end (card_evidence._write_contrib,
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
# first w - 1 selected days sums only the selected part of it; each window is
# rebuilt once from the final contributions of the selected games.

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


def rebuild_windows(daily: dict, rs, deadline_at=None, clock=time.monotonic) -> tuple:
    """([((subject, end day, source, coverage, profile), agg)], cut word or
    None) in the pass's order (class, then end day); agg in the form
    card_measures.window_row reads. Empty without the revision's window
    parameter. The deadline is checked per class and per end day; a rebuild
    it cuts returns what it rebuilt with the cut word."""
    win = rs.params.get(cm.WINDOW)
    if not win:
        return [], None
    w = int(win[cm.WINDOW_KEY])
    classes = {}
    for (subject, day, source, coverage, profile), row in daily.items():
        classes.setdefault((subject, source, coverage, profile), {})[day] = row
    out = []
    for cls in sorted(classes):
        word = _ended(deadline_at, clock)
        if word:
            return out, word
        subject, source, coverage, profile = cls
        by_day = classes[cls]
        for e in sorted(by_day):
            word = _ended(deadline_at, clock)
            if word:
                return out, word
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
    return out, None


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
        self.windows_total = None     # card windows rebuilt (None: none rebuilt, or the rebuild was cut)
        self.totals = {d: None for d in DOMAINS}
        self.cut = None               # the word of what ended the walk early, or None
        self.abandoned = False        # a cancelled walk that had not ended within CANCEL_SLACK_S

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
        evaluated once per window, until the deadline (checked inside the
        rebuild and before every window). A walk already cut rebuilds no
        window."""
        if self.cut:
            return self
        wins, word = rebuild_windows(self.daily, self.rs, deadline_at, clock)
        if word:
            self.cut = word
            return self
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


async def walk(rs, fetch, deadline_at=None, clock=time.monotonic, tally=None) -> Tally:
    """Every domain's items from `fetch` (each domain in its own pass)
    through the counting core, until the deadline or a stop signal: checked
    before each domain and after every game or skip; a walk either ends is
    marked cut and reads nothing more. `tally` (optional) is filled in
    place, so a caller that cancels the walk keeps what it counted: every
    count of one game is made with no await between, so a cancellation
    never leaves a game half counted."""
    tally = Tally(rs) if tally is None else tally
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


async def bounded(coro, tally, deadline_at, clock=time.monotonic):
    """Run `coro` as one task until it ends, the deadline passes or SIGTERM
    cancels it. At the deadline the task is cancelled (the statement in
    flight with it) and `tally.cut` becomes `deadline`; SIGTERM makes it
    `stopped`. A cancelled task gets CANCEL_SLACK_S to end; one that has not
    ended by then is abandoned (tally.abandoned). A failure of the task is
    raised here."""
    loop = asyncio.get_running_loop()
    task = loop.create_task(coro)
    _STOP["task"] = (loop, task)
    try:
        if _STOP["word"]:
            task.cancel()
        timeout = None if deadline_at is None else max(0.0, deadline_at - clock())
        done, _pending = await asyncio.wait({task}, timeout=timeout)
        if not done:
            tally.cut = tally.cut or _STOP["word"] or "deadline"
            task.cancel()
            await asyncio.wait({task}, timeout=CANCEL_SLACK_S)
            tally.abandoned = not task.done()
            return tally
        if task.cancelled():
            tally.cut = tally.cut or _STOP["word"] or "stopped"
            return tally
        exc = task.exception()
        if exc is not None and _STOP["word"]:
            # SIGTERM cancelled it and the unwinding raised: a cut run, not a failure
            tally.cut = tally.cut or _STOP["word"]
            return tally
        if exc is not None:
            raise exc
        return tally
    finally:
        _STOP["task"] = None


async def walk_db(rs, session_factory, days: int, deadline_at=None, clock=time.monotonic,
                  tally=None) -> Tally:
    tally = Tally(rs) if tally is None else tally

    async def inner():
        async with read_only(session_factory) as db:
            await walk(rs, DbFetch(db, days), deadline_at, clock, tally=tally)
    await bounded(inner(), tally, deadline_at, clock)
    return tally


def render(tally: Tally) -> list:
    """The report. First the summary line: `run whole` with the games read
    of the games selected, or `run cut (<word>)` (deadline: the run's own
    deadline; stopped: SIGTERM) with how many games of how many it read and
    how many card windows of how many it evaluated. Then one line per
    counted rule, one per domain and one for the rules not counted, each
    beginning `cut ` in a cut run, so no count of a cut run reads as whole;
    last, `report end`. Rule ids, scopes, words and counts only."""
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
    lines.append("report end")
    return lines


# -- the cohort (design section g) --------------------------------------------------------
#
# The members at instant T, per domain: games with a record received by T
# whose canonical match as of T (ranked, of the pair, named by a record
# received by T, created and ended by T, at least the lag before T) ended
# within :days days of T, with at least one record attached to it and none of
# those attached records purged by T. For each member, its state now: whether
# an attached record has been purged since, the games row's evaluated
# revision and its fault marks. Members are hashed, never printed.

_AT_SQL = "SELECT to_char(date_trunc('second', now() AT TIME ZONE 'UTC'), 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')"

_FAULTS = {
    "card": "(g.derive_fault IS NOT NULL OR g.parked_at IS NOT NULL)",
    "identity": "false",
    "combat": "(COALESCE(g.record_faults, CAST('{{}}' AS jsonb)) "
              "NOT IN (CAST('{{}}' AS jsonb), CAST('[]' AS jsonb), CAST('null' AS jsonb)))",
}

_PAIR_M = "((m.player1_id = {a}.lo AND m.player2_id = {a}.hi) OR (m.player1_id = {a}.hi AND m.player2_id = {a}.lo))"

_COHORT_SQL = (
    "WITH rec AS ("
    " SELECT e.stable_game_key AS k, " + _PAIR_E[0] + " AS lo, " + _PAIR_E[1] + " AS hi,"
    "        e.attach_key AS room, e.lists_purged_at AS purged"
    "   FROM {t} e WHERE e.received_at <= CAST(:at AS timestamptz)), "
    "cand AS ("
    " SELECT DISTINCT r.k, r.lo, r.hi FROM rec r"
    "   JOIN matches m ON m.photon_room_id = r.room AND m.is_ranked IS TRUE AND " + _PAIR_M.format(a="r") +
    "  WHERE m.created_at <= CAST(:at AS timestamptz) AND m.ended_at <= CAST(:at AS timestamptz)"
    "    AND m.ended_at > CAST(:at AS timestamptz) - make_interval(days => CAST(:days AS int))), "
    "canon AS ("
    " SELECT DISTINCT ON (c.k, c.lo, c.hi) c.k, c.lo, c.hi, m.photon_room_id AS room, m.ended_at AS ended"
    "   FROM cand c JOIN rec r ON r.k = c.k AND r.lo = c.lo AND r.hi = c.hi"
    "   JOIN matches m ON m.photon_room_id = r.room AND m.is_ranked IS TRUE AND " + _PAIR_M.format(a="c") +
    "  WHERE m.created_at <= CAST(:at AS timestamptz)"
    "    AND m.ended_at <= CAST(:at AS timestamptz) - make_interval(secs => CAST(:lag AS int))"
    "  ORDER BY c.k, c.lo, c.hi, m.ended_at), "
    "member AS ("
    " SELECT n.k, n.lo, n.hi, n.room FROM canon n"
    "  WHERE n.ended > CAST(:at AS timestamptz) - make_interval(days => CAST(:days AS int))"
    "    AND EXISTS (SELECT 1 FROM rec r WHERE r.k = n.k AND r.lo = n.lo AND r.hi = n.hi AND r.room = n.room)"
    "    AND NOT EXISTS (SELECT 1 FROM rec r WHERE r.k = n.k AND r.lo = n.lo AND r.hi = n.hi"
    "                    AND r.room = n.room AND r.purged <= CAST(:at AS timestamptz))) "
    "SELECT b.k, b.lo, b.hi,"
    "       EXISTS (SELECT 1 FROM {t} e WHERE e.stable_game_key = b.k AND " + _PAIR_E[0] + " = b.lo"
    "               AND " + _PAIR_E[1] + " = b.hi AND e.attach_key = b.room"
    "               AND e.lists_purged_at IS NOT NULL) AS purged_now,"
    "       g.evaluated_rev AS rev, " + "{faults}" + " AS failed"
    "  FROM member b LEFT JOIN {g} g ON g.stable_game_key = b.k AND g.pair_lo = b.lo AND g.pair_hi = b.hi"
    " ORDER BY b.k, b.lo, b.hi")


def cohort_sql(domain: str) -> str:
    return _COHORT_SQL.format(t=_TABLES[domain], g=_GAMES_TABLES[domain],
                              faults=_FAULTS[domain].format())


def cohort_digest(members: dict) -> str:
    """ONE digest over every member of every domain (domain, key, pair), in
    a fixed order."""
    h = hashlib.sha256()
    for domain in DOMAINS:
        for k, lo, hi in sorted((str(m[0]), str(m[1]), str(m[2])) for m in members[domain]):
            h.update(("%s|%s|%s|%s\n" % (domain, k, lo, hi)).encode("utf-8"))
    return h.hexdigest()


def classify(row, rev) -> str:
    """A member's state for the check: purged (an attached record's lists
    were purged after T), evaluated (the games row carries the revision),
    failed (a fault mark), or waiting."""
    if row[3]:
        return "purged"
    if rev is not None and row[4] == rev:
        return "evaluated"
    if row[5]:
        return "failed"
    return "waiting"


async def read_cohort(db, days: int, at=None) -> tuple:
    """(T, {domain: rows}) at T (now, to the second, when `at` is None)."""
    if at is None:
        at = (await db.execute(text(_AT_SQL))).scalar()
    # The driver binds a timestamptz parameter from a datetime only (a text
    # value is refused), so T is bound as the UTC instant its text names.
    t = datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    out = {}
    for domain in DOMAINS:
        out[domain] = (await db.execute(text(cohort_sql(domain)), {
            "at": t, "days": int(days), "lag": _LAGS[domain]})).all()
    return at, out


_STATES = ("evaluated", "waiting", "purged", "failed")


def render_cohort(at, days, members) -> list:
    n = {d: len(members[d]) for d in DOMAINS}
    return ["cohort at %s days %d: members %d (%s) digest %s"
            % (at, days, sum(n.values()), ", ".join("%s %d" % (d, n[d]) for d in DOMAINS),
               cohort_digest(members)),
            "report end"]


def render_check(rev, at, members) -> list:
    per = {d: dict.fromkeys(_STATES, 0) for d in DOMAINS}
    for d in DOMAINS:
        for row in members[d]:
            per[d][classify(row, rev)] += 1
    tot = {s: sum(per[d][s] for d in DOMAINS) for s in _STATES}
    n = sum(len(members[d]) for d in DOMAINS)
    done = tot["evaluated"] + tot["purged"] + tot["failed"] == n
    lines = ["cohort check rev %s at %s: members %d; evaluated %d; waiting %d; purged %d; "
             "failed %d; complete %s" % (rev, at, n, tot["evaluated"], tot["waiting"],
                                         tot["purged"], tot["failed"], "yes" if done else "no")]
    for d in DOMAINS:
        lines.append("cohort %s members %d evaluated %d waiting %d purged %d failed %d"
                     % (d, len(members[d]), per[d]["evaluated"], per[d]["waiting"],
                        per[d]["purged"], per[d]["failed"]))
    lines.append("report end")
    return lines


# -- the runs ---------------------------------------------------------------------------

def _remaining_s(deadline_at) -> int:
    if deadline_at is None:
        return DEFAULT_DEADLINE_S
    return max(1, int(deadline_at - time.monotonic()) + 1)


async def _dispose(engine):
    try:
        await asyncio.wait_for(engine.dispose(), CLOSE_SLACK_S)
    except BaseException:                     # noqa: BLE001 -- the report is out; the process ends
        pass


async def _run(rs, days, deadline_at=None):
    engine, factory = session_factory(_remaining_s(deadline_at))
    try:
        return await walk_db(rs, factory, days, deadline_at)
    finally:
        await _dispose(engine)


async def _run_cohort(days, deadline_at=None, at=None):
    """(T, members) or None when the deadline or SIGTERM ended it first."""
    engine, factory = session_factory(_remaining_s(deadline_at))
    box = {}

    async def inner():
        async with read_only(factory) as db:
            box["v"] = await read_cohort(db, days, at)
    probe = type("Cut", (), {"cut": None, "abandoned": False})()
    try:
        await bounded(inner(), probe, deadline_at)
    finally:
        await _dispose(engine)
    return None if probe.cut else box.get("v")


def _run_loop(coro):
    """The coroutine on a fresh event loop, which is closed WITHOUT waiting
    for a task the deadline abandoned (asyncio.run would wait for it)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _say(lines) -> None:
    sys.stdout.write("".join(line + "\n" for line in lines))
    sys.stdout.flush()


def failure_word(exc) -> str:
    """The fixed class word of a failure."""
    if isinstance(exc, KeyboardInterrupt):
        return "interrupted"
    if isinstance(exc, SystemExit):
        return "exit"
    if isinstance(exc, MemoryError):
        return "memory"
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "timeout"
    if isinstance(exc, ConfigRefused):
        return "config"
    if isinstance(exc, DriverRefused):
        return "driver"
    try:
        from sqlalchemy.exc import SQLAlchemyError
        if isinstance(exc, SQLAlchemyError):
            return "database"
    except Exception:                         # noqa: BLE001
        pass
    try:
        import asyncpg
        if isinstance(exc, (asyncpg.PostgresError, asyncpg.InterfaceError)):
            return "database"
    except Exception:                         # noqa: BLE001
        pass
    if isinstance(exc, OSError):
        return "system"
    return "internal"


class _Sink:
    def write(self, s):
        return len(s)

    def flush(self):
        pass

    def isatty(self):
        return False


@contextlib.contextmanager
def quiet_streams():
    """Standard error a sink, warnings off, unraisable exceptions dropped,
    logging's own error reports off; all restored on exit."""
    saved = (sys.stderr, sys.unraisablehook, list(warnings.filters), logging.raiseExceptions)
    sys.stderr = _Sink()
    sys.unraisablehook = lambda _u: None
    warnings.simplefilter("ignore")
    logging.raiseExceptions = False
    try:
        yield
    finally:
        sys.stderr, sys.unraisablehook = saved[0], saved[1]
        warnings.filters[:] = saved[2]
        logging.raiseExceptions = saved[3]


def _main(argv, start) -> int:
    opts = parse_args(argv)
    deadline_at = start + opts["deadline_s"]
    _STOP["word"] = None
    if opts["mode"] == "count":
        try:
            path = revision_path(opts["revision"])
        except PathRefused as e:
            raise Refused("refused (path %s)" % e.word, EXIT_USAGE) from None
        try:
            rs = rr.load_dir(path)
        except rr.Refused as e:
            cls = e.cls if isinstance(e.cls, str) and _LOADER_CLASS.fullmatch(e.cls) else "revision"
            raise Refused("refused (%s)" % cls, EXIT_REFUSED) from None
        _say(["revision %s days %d deadline_s %d" % (rs.rev, opts["days"], opts["deadline_s"])])
    before = signal.signal(signal.SIGTERM, _on_term)
    try:
        if opts["mode"] == "count":
            tally = _run_loop(_run(rs, opts["days"], deadline_at))
            _say(render(tally))
            return 0
        got = _run_loop(_run_cohort(opts["days"], deadline_at, opts.get("at")))
    finally:
        signal.signal(signal.SIGTERM, before)
        _STOP["task"] = None
    if got is None:
        _say(["cohort cut (%s): nothing counted" % (_STOP["word"] or "deadline"), "report end"])
        return EXIT_REFUSED
    at, members = got
    if opts["mode"] == "cohort":
        _say(render_cohort(at, opts["days"], members))
        return 0
    if cohort_digest(members) != opts["digest"]:
        _say(["refused (cohort differs)"])
        return EXIT_REFUSED
    _say(render_check(opts["rev"], at, members))
    return 0


def main(argv=None) -> int:
    start = time.monotonic()                  # the deadline counts the whole run, loading included
    with quiet_streams():
        try:
            return _main(sys.argv[1:] if argv is None else argv, start)
        except Refused as e:
            _say([e.line])
            return e.code
        except BaseException as e:            # noqa: BLE001 -- THE outermost handler
            _say(["failed (%s)" % failure_word(e)])
            return EXIT_FAILED


if __name__ == "__main__":
    _hold = quiet_streams()
    _hold.__enter__()                         # for the whole process, interpreter exit included
    _code = main(sys.argv[1:])
    sys.stdout.flush()
    os._exit(_code)
