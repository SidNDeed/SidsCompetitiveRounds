"""Fixture machinery for the connect-failure server controls (DESIGN V11,
evidence sec8.1), used by test_ffa_assembly_pg.py.

One Env per case schema (cf_pg.case). It freezes the assembly clock
(main._asm_clock) and the monotonic clock main reads, so every threshold is
exact: "time t" means the frozen clock reads created_at + t, and Env.at()
shifts the lobby's own timestamps so that instant is the database's real now
(the closers' record fragment and the notice window compare with SQL NOW(),
so the two clocks must agree). The session check is a no-op unless a test
patches it.

Every route runs on its own session from Env.sm, a sessionmaker whose
sessions record, for the inert-twin comparison of cf_controls.py, each
statement's shape (verb, table, the columns it writes, its lock clause and
the transaction it commits in) and the relation locks held before each
COMMIT. Env.trace() writes those, the answers, the [FFA-ASM] lines and the
fixture's rows, normalised, to CF_TRACE_DIR when that is set.

Steam ids are synthetic: 765611900355xxxxx lies below the first individual
Steam account id, so no fixture id is anyone's.
"""

import contextvars
import copy
import datetime as _dt
import decimal as _decimal
import io
import json
import os
import re
import sys
import time as _time
import types
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import event, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

STEAM_BASE = 76561190035500000
UTC = _dt.timezone.utc

# Fixture ids are derived, never random: a query that orders by a player
# or lobby id (the bet settlement orders by player_id::text) then walks the
# fixture's rows in the same order in every run, so two runs of the same
# code write the same trace (the twin rule).
_ID_NS = uuid.UUID("5c0f5e1e-2b1d-4c55-9a55-000000000355")


def fixture_uuid(kind, key):
    return uuid.uuid5(_ID_NS, "%s:%s" % (kind, key))


# The process memory main keeps between requests (TTL caches, last-seen
# and last-run memos), captured at import. Every case starts from it, so
# no statement depends on which cases ran earlier in the process or how
# long ago: the region volumes (a 600 s cache) and the service-account
# UUIDs (an hourly cache) each issue their query only when cold. A name
# that reads as a constant (upper case, a number) is configuration, not
# state, and is left alone. "state" covers the janitor arms' cadence
# dicts: the mail retention arm runs when time.monotonic() passes
# _MAIL_RETENTION_STATE["next"], so without it the arm ran in whichever
# case reached the janitor first in a process, and S36's statements
# depended on which rows shared the process. The rule adds exactly five
# names over the old one: that dict, _PC_STEAM_RENDER_STATE,
# _PC_STEAM_SWEEP_STATE, _triage_gc_state (a balanced depth counter) and
# the constant _ASM_SQLSTATE_STAGE, whose restore changes nothing.
_STATE_RE = re.compile(r"(?i)cache|seen|last|mono|prune|state")
_MAIN_STATE = {}
for _name, _val in list(vars(main).items()):
    if _name.startswith("__") or not _STATE_RE.search(_name):
        continue
    if isinstance(_val, bool) or not isinstance(_val, (dict, set, list, float, int, type(None))):
        continue
    if _name.lstrip("_").isupper() and not isinstance(_val, (dict, set, list)):
        continue
    _MAIN_STATE[_name] = copy.deepcopy(_val)

_LOCKS_SQL = (
    "SELECT /*cf-locks*/ l.locktype, COALESCE(c.relname, ''), l.mode FROM pg_locks l"
    "  LEFT JOIN pg_class c ON c.oid = l.relation"
    " WHERE l.pid = pg_backend_pid() AND l.granted"
    "   AND l.locktype IN ('relation', 'tuple', 'advisory')"
    "   AND COALESCE(c.relname, '') NOT LIKE 'pg\\_%'"
    # An index's AccessShareLock depends on the plan the planner chose,
    # which two runs of the same code need not share; tables, tuples and
    # advisory locks are what a twin must keep.
    "   AND COALESCE(c.relkind, 'r') NOT IN ('i', 'I')"
    " ORDER BY 1, 2, 3")

_REC = {"on": None}

# The buffer of the route call running in the current task (Env._call).
_OUT = contextvars.ContextVar("cf_out", default=None)


class _TaskStdout:
    """sys.stdout while an Env lives: a route call's prints go to the buffer
    its own task set, so two calls running at once (S63 (iv)) never swap each
    other's redirection, which contextlib.redirect_stdout would when they
    exit out of order; every other write goes to the stream it wraps."""

    def __init__(self, base):
        self.base = base

    def write(self, s):
        return (_OUT.get() or self.base).write(s)

    def flush(self):
        (_OUT.get() or self.base).flush()

    def __getattr__(self, k):
        return getattr(self.base, k)


class RecSession(AsyncSession):
    """A session that records the relation locks it holds before each
    COMMIT (the twin comparison's lock set)."""

    async def commit(self):
        rec = _REC["on"]
        if rec is not None and self.in_transaction():
            try:
                rows = (await self.execute(text(_LOCKS_SQL))).all()
                rec.locks.append(sorted({(r[0], r[1], r[2]) for r in rows}))
            except Exception as exc:                   # pragma: no cover
                rec.locks.append([("error", type(exc).__name__, "")])
        await super().commit()


_VERB = re.compile(r"^\s*(?:/\*.*?\*/\s*)?(\w+)", re.S)
_UPD = re.compile(r"^\s*UPDATE\s+(\w+)\s+SET\s+(.*?)(?:\sWHERE\s|\sRETURNING\s|$)", re.S | re.I)
_INS = re.compile(r"^\s*INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)", re.S | re.I)
_DEL = re.compile(r"^\s*DELETE\s+FROM\s+(\w+)", re.S | re.I)
_FROM = re.compile(r"\sFROM\s+(\w+)", re.S | re.I)
_LOCKCL = re.compile(r"FOR\s+(?:NO\s+KEY\s+)?(?:UPDATE|SHARE)(?:\s+SKIP\s+LOCKED|\s+NOWAIT)?", re.I)


def _set_columns(body):
    """The column names a SET list assigns, at parenthesis depth 0."""
    cols, depth, cur = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            cols.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    cols.append("".join(cur))
    out = []
    for c in cols:
        m = re.match(r"\s*(\w+)\s*=", c)
        if m:
            out.append(m.group(1).lower())
    return sorted(out)


def _main_statement(s):
    """The statement a leading WITH list prefixes: the text from the first
    SELECT/INSERT/UPDATE/DELETE at parenthesis depth 0 after the WITH, or s
    itself when it has no WITH list."""
    if not re.match(r"^\s*WITH\b", s, re.I):
        return s
    depth = 0
    i = re.match(r"^\s*WITH\b", s, re.I).end()
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            m = re.match(r"(SELECT|INSERT|UPDATE|DELETE)\b", s[i:], re.I)
            if m and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_")):
                return s[i:]
        i += 1
    return s


def shape(sql):
    """verb, table, written columns, lock clause: a statement's shape. A
    statement wrapped in a WITH list has the shape of the statement the list
    prefixes (its verb, and for a SELECT the first table its text reads), so
    a twin that moves a predicate into a named CTE "inside the same
    statement" (evidence section 8) leaves the shape unchanged."""
    whole = sql.strip()
    s = _main_statement(whole)
    verb = (_VERB.match(s).group(1) if _VERB.match(s) else "?").upper()
    table, cols = "", []
    m = _UPD.match(s)
    if m:
        table, cols = m.group(1).lower(), _set_columns(m.group(2))
    else:
        m = _INS.match(s)
        if m:
            table = m.group(1).lower()
            cols = sorted(c.strip().lower() for c in m.group(2).split(","))
        else:
            m = _DEL.match(s) or _FROM.search(whole)
            if m:
                table = m.group(1).lower()
    lk = _LOCKCL.search(whole)
    return [verb, table, cols, re.sub(r"\s+", " ", lk.group(0).upper()) if lk else ""]


class Recorder:
    def __init__(self):
        self.stmts = []
        self.locks = []
        self.txn = 0

    def before(self, conn, cursor, statement, parameters, context, executemany):
        if "/*cf-locks*/" in statement:
            return
        self.stmts.append(shape(statement) + [self.txn])

    def on_commit(self, conn):
        self.txn += 1
        self.stmts.append(["COMMIT", "", [], "", self.txn])

    def on_rollback(self, conn):
        self.txn += 1
        self.stmts.append(["ROLLBACK", "", [], "", self.txn])


class Answer:
    """A route's outcome as (status, body)."""

    def __init__(self, status, body):
        self.status = status
        self.body = body

    def __getitem__(self, k):
        # A body that is not a dict or a list (an error's detail string)
        # has no fields: None, so the test's own named assertion fails on
        # it instead of a TypeError inside the subscript.
        return self.body[k] if isinstance(self.body, (dict, list)) else None

    def get(self, k, d=None):
        return self.body.get(k, d) if isinstance(self.body, dict) else d

    def __repr__(self):
        return "Answer(%r, %r)" % (self.status, self.body)


class _NoHeaders(dict):
    def get(self, k, d=None):
        return d


class FakeRequest:
    """Only what the handlers read off a request once the session check is
    replaced (the ladder suite's own shape)."""
    headers = _NoHeaders()
    client = None
    url = "http://cf.test/"

    def __init__(self):
        self.state = types.SimpleNamespace()


class Lob:
    def __init__(self, lid, sids, pids, region, admission, gated):
        self.lid = lid
        self.sids = sids
        self.pids = pids
        self.region = region
        self.admission = admission
        self.gated = gated
        self.n = len(sids)

    def slot_of(self, pid):
        return self.pids.index(pid)


class Env:
    """The case's frozen clocks, route callers and second-session readers."""

    def __init__(self, c, sm, mp):
        self.c = c
        self.conn = c.conn
        self.engine = sm.kw["bind"]
        self.sm = async_sessionmaker(self.engine, expire_on_commit=False, class_=RecSession)
        self.mp = mp
        self.now = None
        # Far past process start, so _in_match_evidence_trustworthy() holds and
        # no young-process veto depends on when the test runs.
        self.mono = _time.monotonic() + 1000000.0
        self.lines = []
        self.answers = []
        self.serial = 0
        self.lobbies = []
        self.rec = Recorder()
        _REC["on"] = self.rec
        event.listen(self.engine.sync_engine, "before_cursor_execute", self.rec.before)
        event.listen(self.engine.sync_engine, "commit", self.rec.on_commit)
        event.listen(self.engine.sync_engine, "rollback", self.rec.on_rollback)
        mp.setattr(main, "_asm_clock", self._clock)
        proxy = types.SimpleNamespace(**{k: getattr(_time, k) for k in dir(_time)
                                         if not k.startswith("__")})
        proxy.monotonic = lambda: self.mono
        mp.setattr(main, "time", proxy)

        async def _no_session(request, steam_id, db):
            return None
        mp.setattr(main, "_check_steam_session", _no_session)
        # Reports are submitted unsigned (the ladder suite's `opened`): the
        # HMAC is not what these controls test.
        mp.setattr(main, "MATCH_HMAC_SECRET", "")
        # Presence is process memory keyed by steam id, and every case reuses
        # the same synthetic ids: each case starts with nobody online.
        mp.setattr(main, "_presence_seen", {})
        for name, val in _MAIN_STATE.items():
            mp.setattr(main, name, copy.deepcopy(val))
        mp.setattr(sys, "stdout", _TaskStdout(sys.stdout))

    def close(self):
        _REC["on"] = None
        for name, fn in (("before_cursor_execute", self.rec.before),
                         ("commit", self.rec.on_commit), ("rollback", self.rec.on_rollback)):
            try:
                event.remove(self.engine.sync_engine, name, fn)
            except Exception:                          # pragma: no cover
                pass

    async def _clock(self, db):
        if self.now is None:
            row = (await db.execute(text("SELECT clock_timestamp()"))).scalar()
            return row, self.mono
        return self.now, self.mono

    # -- the clock ------------------------------------------------------------

    async def _shift(self, lid, delta):
        """Move every timestamp of the lobby, its seat rows and its kept
        epochs by `delta` (the lobby's own history moves; nothing else)."""
        for table, key in (("ffa_lobbies", "id"), ("ffa_assembly_seats", "lobby_id"),
                           ("ffa_kept_epochs", "lobby_id")):
            cols = [r[0] for r in await self.conn.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = current_schema() AND table_name = $1"
                "   AND data_type = 'timestamp with time zone' ORDER BY 1", table)]
            if not cols:
                continue
            sets = ", ".join("%s = %s + $2" % (c, c) for c in cols)
            await self.conn.execute("UPDATE %s SET %s WHERE %s = $1" % (table, sets, key),
                                    lid, delta)

    async def at(self, lob, t):
        """Freeze the clock at created_at + t, with that instant the real now."""
        real = await self.conn.fetchval("SELECT clock_timestamp()")
        old = await self.conn.fetchval("SELECT created_at FROM ffa_lobbies WHERE id = $1",
                                       lob.lid)
        new = real - _dt.timedelta(seconds=t)
        await self._shift(lob.lid, new - old)
        self.now = new + _dt.timedelta(seconds=t)
        return self.now

    async def ts(self, lob, t):
        """The absolute instant created_at + t (for seeding stamps)."""
        created = await self.conn.fetchval("SELECT created_at FROM ffa_lobbies WHERE id = $1",
                                           lob.lid)
        return created + _dt.timedelta(seconds=t)

    # -- fixtures -------------------------------------------------------------

    async def lobby(self, n=5, *, admission=False, gated=True, ranked=True, region="eu",
                    offered=None, t=0.0, joined=None, caps=None, host_slot=0,
                    queue=True, lease=True, games_played=0, player_count=None, lid=None):
        """An active locked lobby of n seats at lobby age t: players, the
        lobby row, ready_join queue rows (joined_at in `joined` order, default
        slot order), ffa leases, and one seat row per member with
        lock_offered_at set for the slots in `offered` (default every slot)."""
        self.serial += 1
        base = STEAM_BASE + self.serial * 20
        sids = [str(base + i) for i in range(n)]
        pids = []
        for i, sid in enumerate(sids):
            pids.append(await self.conn.fetchval(
                "INSERT INTO players (id, steam_id, display_name, mod_version)"
                " VALUES ($3, $1, $2, '1.41.0') RETURNING id", sid, "cf s%d-%d" % (self.serial, i),
                fixture_uuid("player", sid)))
        lid = lid if lid is not None else fixture_uuid("lobby", self.serial)
        room = "ffa_cf%06d" % self.serial
        await self.conn.execute(
            "INSERT INTO ffa_lobbies (id, status, photon_room_id, region, player_count,"
            "  member_ids, created_at, host_player_id, is_ranked, assembly_v1, admission_v1,"
            "  games_played)"
            " VALUES ($1, 'active', $2, $3, $4, $5, clock_timestamp() - make_interval(secs => $6),"
            "         $7, $8, $9, $10, $11)",
            lid, room, region, player_count if player_count is not None else n, pids, float(t),
            pids[host_slot], ranked, gated, admission and gated, games_played)
        order = joined if joined is not None else list(range(n))
        caps = caps if caps is not None else (["ffa_asm1,ffa_adm1"] * n)
        if queue:
            for rank, slot in enumerate(order):
                await self.conn.execute(
                    "INSERT INTO ffa_queue (player_id, steam_id, display_name, status, series_id,"
                    "  slot, room_name, room_region, matched_at, joined_at, last_polled, caps,"
                    "  mod_version)"
                    " VALUES ($1, $2, $3, 'ready_join', $4, $5, $6, $7, clock_timestamp(),"
                    "         clock_timestamp() - make_interval(secs => $8), clock_timestamp(),"
                    "         $9, '1.41.0')",
                    pids[slot], sids[slot], "cf s%d-%d" % (self.serial, slot), lid, slot, room,
                    region, float(600 - rank), caps[slot])
        if lease:
            async with self.sm() as db:
                await main._lease_acquire_many(db, list(pids), "ffa", lid,
                                               main.LEASE_TTL_ASSEMBLY)
                await db.commit()
        offered = set(range(n)) if offered is None else set(offered)
        for slot in range(n):
            await self.conn.execute(
                "INSERT INTO ffa_assembly_seats (lobby_id, player_id, slot, locked_at,"
                "  lock_offered_at)"
                " VALUES ($1, $2, $3, (SELECT created_at FROM ffa_lobbies WHERE id = $1),"
                "         CASE WHEN $4 THEN (SELECT created_at FROM ffa_lobbies WHERE id = $1)"
                "         END)", lid, pids[slot], slot, slot in offered)
        lob = Lob(lid, sids, pids, region, admission and gated, gated)
        self.lobbies.append(lob)
        await self.at(lob, t)
        return lob

    async def census_row(self, lob, slot, entries, *, t_at=None, seen=None, region=None,
                         game=0, anon=0, claim=None, bind=False):
        """Write a seat's census columns directly (a fixture's stored census):
        entries are (slot, actor, b, k). t_at is the lobby age of census_at
        (default now); seen that of census_seen_at (default t_at). claim is
        the seat's own actor claim; bind=True also binds it."""
        now_t = (self.now - await self.ts(lob, 0)).total_seconds()
        t_at = now_t if t_at is None else t_at
        seen = t_at if seen is None else seen
        region = region or lob.region
        cs = [e[0] for e in entries]
        ca = [e[1] for e in entries]
        cn = sorted({e[0] for e in entries if e[2] == 0})
        cu = sorted({e[0] for e in entries if e[3] == 0})
        await self.conn.execute(
            "UPDATE ffa_assembly_seats SET census_slots = $3, census_actors = $4,"
            "  census_nobody = $5, census_unkept = $6, census_anon = $7, census_region = $8,"
            "  census_game = $9, census_at = $10, census_seen_at = $11"
            " WHERE lobby_id = $1 AND slot = $2",
            lob.lid, slot, cs, ca, cn, cu, anon, region, game,
            await self.ts(lob, t_at), await self.ts(lob, seen))
        if claim is not None:
            await self.conn.execute(
                "UPDATE ffa_assembly_seats SET actor_claim = $3, claim_region = $4"
                " WHERE lobby_id = $1 AND slot = $2", lob.lid, slot, claim, region)
            if bind:
                await self.conn.execute(
                    "UPDATE ffa_assembly_seats SET actor_nr = $3, actor_region = $4"
                    " WHERE lobby_id = $1 AND slot = $2", lob.lid, slot, claim, region)

    async def ready_all(self, lob, slots, *, actor0=1, bodied=True, t_at=None):
        """Make `slots` READY: each bound to actor actor0 + slot with a fresh
        census listing every seat of `slots` (bodied unless bodied=False)."""
        entries = [(s, actor0 + s, 1 if bodied else 0, 1) for s in slots]
        for s in slots:
            await self.census_row(lob, s, entries, t_at=t_at, claim=actor0 + s, bind=True)
        if bodied:
            await self.conn.execute(
                "UPDATE ffa_assembly_seats SET body_seen_at = $3"
                " WHERE lobby_id = $1 AND slot = ANY($2::smallint[])",
                lob.lid, list(slots), self.now)

    async def set_seat(self, lob, slot, **cols):
        """Set seat columns; a float value for a *_at column is a lobby age."""
        sets, args = [], [lob.lid, slot]
        for k, v in cols.items():
            if k.endswith("_at") and isinstance(v, (int, float)) and not isinstance(v, bool):
                v = await self.ts(lob, v)
            args.append(v)
            sets.append("%s = $%d" % (k, len(args)))
        await self.conn.execute("UPDATE ffa_assembly_seats SET %s WHERE lobby_id = $1 AND slot = $2"
                                % ", ".join(sets), *args)

    async def set_lobby(self, lob, **cols):
        sets, args = [], [lob.lid]
        for k, v in cols.items():
            if k.endswith("_at") and isinstance(v, (int, float)) and not isinstance(v, bool):
                v = await self.ts(lob, v)
            args.append(v)
            sets.append("%s = $%d" % (k, len(args)))
        await self.conn.execute("UPDATE ffa_lobbies SET %s WHERE id = $1" % ", ".join(sets), *args)

    # -- readers (a second session) -------------------------------------------

    async def seat(self, lob, slot):
        r = await self.conn.fetchrow(
            "SELECT * FROM ffa_assembly_seats WHERE lobby_id = $1 AND slot = $2", lob.lid, slot)
        return dict(r) if r is not None else None

    async def seats(self, lob):
        return [dict(r) for r in await self.conn.fetch(
            "SELECT * FROM ffa_assembly_seats WHERE lobby_id = $1 ORDER BY slot", lob.lid)]

    async def lobby_row(self, lid):
        lid = lid.lid if isinstance(lid, Lob) else lid
        r = await self.conn.fetchrow("SELECT * FROM ffa_lobbies WHERE id = $1", lid)
        return dict(r) if r is not None else None

    async def queue_row(self, lob, slot):
        r = await self.conn.fetchrow("SELECT * FROM ffa_queue WHERE player_id = $1",
                                     lob.pids[slot])
        return dict(r) if r is not None else None

    async def lease(self, lob, slot):
        r = await self.conn.fetchrow("SELECT * FROM queue_leases WHERE player_id = $1",
                                     lob.pids[slot])
        return dict(r) if r is not None else None

    # -- route callers --------------------------------------------------------

    async def _call(self, coro_fn):
        buf = io.StringIO()
        tok = _OUT.set(buf)
        try:
            try:
                out = await coro_fn()
            except HTTPException as exc:
                out = Answer(exc.status_code, exc.detail)
        finally:
            _OUT.reset(tok)
            for line in buf.getvalue().splitlines():
                self.lines.append(line)
        if isinstance(out, Answer):
            ans = out
        elif hasattr(out, "status_code") and hasattr(out, "body"):
            ans = Answer(out.status_code, json.loads(bytes(out.body).decode("utf-8")))
        else:
            ans = Answer(200, out)
        self.answers.append(ans)
        return ans

    async def connect(self, lob, slot, step, **kw):
        kw.setdefault("client_ms", 100)
        req = main._AsmConnectReq(steam_id=lob.sids[slot], step=step, **kw)

        async def go():
            async with self.sm() as db:
                return await main.ffa_lobby_connect(lob.lid, req, None, db=db)
        return await self._call(go)

    def entry(self, lob, slot, actor, b=1, k=1, anon=False):
        return {"a": actor, "s": "" if anon else lob.sids[slot], "b": b, "k": k}

    async def assembly(self, lob, slot, actor, census, *, region=None, game=0,
                       seen_age_ms=None, epoch_seen=0, lobby_id=None):
        """census: a list of entry() dicts. seen_age_ms defaults to the
        server's age at receipt (the frozen clock)."""
        if seen_age_ms is None:
            seen_age_ms = int(round((self.now - await self.ts(lob, 0)).total_seconds() * 1000))
        req = main._AsmAssemblyReq(steam_id=lob.sids[slot], actor=actor,
                                   region=region or lob.region, game=game,
                                   seen_age_ms=seen_age_ms, epoch_seen=epoch_seen,
                                   census=census, client_ms=100)

        async def go():
            async with self.sm() as db:
                return await main.ffa_lobby_assembly(lobby_id or lob.lid, req, None, db=db)
        return await self._call(go)

    async def census_of(self, lob, slot, present, *, actor0=1, b=1, k=1, region=None,
                        game=0, seen_age_ms=None, actor=None):
        """An assembly POST from `slot` listing the seats of `present` with
        actor actor0 + seat (the ready_all numbering)."""
        entries = [self.entry(lob, s, actor0 + s, b=b, k=k) for s in present]
        return await self.assembly(lob, slot, actor if actor is not None else actor0 + slot,
                                   entries, region=region, game=game, seen_age_ms=seen_age_ms)

    async def release(self, lob, slot, why, *, lobby_id=None, steam_id=None):
        req = main._AsmReleaseReq(steam_id=steam_id or lob.sids[slot], why=why)

        async def go():
            async with self.sm() as db:
                return await main.ffa_lobby_release(lobby_id or lob.lid, req, None, db=db)
        return await self._call(go)

    async def leave(self, lob, slot, *, cause="", label="", expected=None, steam_id=None):
        exp = str(lob.lid) if expected is None else expected

        async def go():
            async with self.sm() as db:
                return await main.ffa_queue_leave(None, steam_id=steam_id or lob.sids[slot],
                                                  expected_lobby_id=exp, cause=cause,
                                                  label=label, db=db)
        return await self._call(go)

    async def poll(self, lob, slot, *, steam_id=None):
        async def go():
            async with self.sm() as db:
                return await main.ffa_queue_poll(steam_id or lob.sids[slot], None, db=db)
        return await self._call(go)

    async def verdict_direct(self, lob, trigger="assembly"):
        """_ffa_assembly_verdict called directly, in its own transaction under
        the lobby lock (deviation 12's function-level fixtures)."""
        async def go():
            async with self.sm() as db:
                ctx = await main._asm_ctx_slot(db, lob.lid, route=trigger, trigger=trigger)
                out = await main._ffa_assembly_verdict(ctx, trigger)
                await db.commit()
                ctx.emit()
                return out
        return await self._call(go)

    def asm_lines(self, needle=""):
        return [ln for ln in self.lines if ln.startswith("[FFA-ASM]") and needle in ln]

    # -- reports, bettors, wagers ---------------------------------------------

    async def report(self, lid, g, results, *, reporter=None, room=None, left=(),
                     absent=(), gp_leave=None, omit=()):
        """Submit game g of lobby `lid` unsigned. `results` maps steam id to
        (rounds, points) for the members it names (others 0, 0); slots are the
        lobby's member_ids order. `left`/`absent` name steam ids reported as
        early leavers / absent; gp_leave maps steam id to game_points_at_leave;
        `omit` names steam ids whose rows the report leaves out."""
        rep = await self.report_req(lid, g, results, reporter=reporter, room=room, left=left,
                                    absent=absent, gp_leave=gp_leave, omit=omit)
        return await self.submit(rep)

    async def report_req(self, lid, g, results, *, reporter=None, room=None, left=(),
                         absent=(), gp_leave=None, omit=()):
        """The report body report() submits, built from the second session;
        a caller that submits it from a concurrent task builds it first."""
        import schemas
        lid = lid.lid if isinstance(lid, Lob) else lid
        row = await self.lobby_row(lid)
        members = list(row["member_ids"])
        sid_of = {r["id"]: r["steam_id"] for r in await self.conn.fetch(
            "SELECT id, steam_id FROM players WHERE id = ANY($1::uuid[])", members)}
        gp_leave = gp_leave or {}
        entries = []
        for slot, pid in enumerate(members):
            sid = sid_of[pid]
            if sid in omit:
                continue
            rounds, points = results.get(sid, (0, 0))
            entries.append(schemas.FfaPlayerEntry(
                steam_id=sid, slot=slot, rounds_won=rounds, points_total=points,
                left_early=sid in left, absent=sid in absent,
                game_points_at_leave=gp_leave.get(sid)))
        winner = max(results, key=lambda s: (results[s][0], results[s][1]))
        return schemas.FfaMatchReport(
            lobby_id=str(lid), photon_room_id=room or "%s_r%d" % (row["photon_room_id"], g),
            winner_steam_id=winner, reported_by_steam_id=reporter or winner,
            is_ranked=bool(row["is_ranked"]), players=entries)

    async def submit(self, rep):
        """Submit a report body; touches only its own session."""
        async def go():
            async with self.sm() as db:
                out = await main.submit_ffa_match(rep, FakeRequest(), db)
                return out.model_dump() if hasattr(out, "model_dump") else out
        return await self._call(go)

    async def bettor(self, gold=5000):
        """A player outside every fixture lobby, holding `gold`."""
        self.serial += 1
        sid = str(STEAM_BASE + self.serial * 20 + 19)
        pid = await self.conn.fetchval(
            "INSERT INTO players (id, steam_id, display_name, mod_version, gold_earned)"
            " VALUES ($4, $1, $2, '1.41.0', $3) RETURNING id", sid, "cf bettor %d" % self.serial, gold,
            fixture_uuid("player", sid))
        return pid, sid

    async def wager(self, lid, bettor_pid, on_pid, *, game=1, amount=100, odds=2.5):
        """An unsettled ffa_bets row, inserted directly, with the stake moved
        the way the bet POST moves it (gold_spent and the ledger row), so a
        later refund finds the balance it returns."""
        lid = lid.lid if isinstance(lid, Lob) else lid
        await self.conn.execute(
            "UPDATE players SET gold_spent = COALESCE(gold_spent, 0) + $2 WHERE id = $1",
            bettor_pid, amount)
        await self.conn.execute(
            "INSERT INTO gold_transactions (player_id, amount, reason, reference_id, created_at)"
            " VALUES ($1, $2, 'ffa_bet_stake', $3, now())", bettor_pid, -amount, str(lid))
        return await self.conn.fetchval(
            "INSERT INTO ffa_bets (lobby_id, game_number, player_id, bet_on_player_id, amount,"
            "  odds_multiplier) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
            lid, game, bettor_pid, on_pid, amount, odds)

    async def bets(self, lid):
        lid = lid.lid if isinstance(lid, Lob) else lid
        return [dict(r) for r in await self.conn.fetch(
            "SELECT * FROM ffa_bets WHERE lobby_id = $1 ORDER BY id", lid)]

    async def refunds(self, lid):
        lid = lid.lid if isinstance(lid, Lob) else lid
        return await self.conn.fetchval(
            "SELECT count(*) FROM gold_transactions WHERE reason = 'ffa_bet_refund'"
            "   AND reference_id = $1", str(lid))

    # -- the twin comparison's trace -------------------------------------------

    async def snapshot(self):
        """Every row of the fixture's lobbies (and lobbies re-formed from them),
        their seats, epochs, queue rows, leases and wagers."""
        lids = [lob.lid for lob in self.lobbies]
        lids += [r[0] for r in await self.conn.fetch(
            "SELECT id FROM ffa_lobbies WHERE reformed_from = ANY($1::uuid[])", lids)]
        pids = [p for lob in self.lobbies for p in lob.pids]
        out = {}
        for name, sql, arg in (
                ("lobbies", "SELECT * FROM ffa_lobbies WHERE id = ANY($1::uuid[])"
                            " ORDER BY created_at, id", lids),
                ("seats", "SELECT * FROM ffa_assembly_seats WHERE lobby_id = ANY($1::uuid[])"
                          " ORDER BY lobby_id, slot", lids),
                ("epochs", "SELECT * FROM ffa_kept_epochs WHERE lobby_id = ANY($1::uuid[])"
                           " ORDER BY lobby_id, epoch_no", lids),
                ("queue", "SELECT * FROM ffa_queue WHERE player_id = ANY($1::uuid[])"
                          " ORDER BY steam_id", pids),
                ("leases", "SELECT player_id, mode, group_id FROM queue_leases"
                           " WHERE player_id = ANY($1::uuid[]) ORDER BY player_id", pids),
                ("bets", "SELECT * FROM ffa_bets WHERE lobby_id = ANY($1::uuid[])"
                         " ORDER BY created_at, id", lids)):
            try:
                out[name] = [dict(r) for r in await self.conn.fetch(sql, arg)]
            except Exception as exc:                   # pragma: no cover
                out[name] = "error %s" % type(exc).__name__
        return out

    async def trace(self, name):
        """Write the normalised trace for cf_controls.py (CF_TRACE_DIR)."""
        d = os.environ.get("CF_TRACE_DIR")
        if not d:
            return None
        rows = await self.snapshot()
        # Names seeded from the fixture (lobby i is L{i}, its seat j L{i}P{j}),
        # so two runs name the same row the same way however the random
        # UUIDs happen to sort.
        seed = []
        for i, lob in enumerate(self.lobbies):
            seed.append((lob.lid, "L%d" % i))
            for j, p in enumerate(lob.pids):
                seed.append((p, "L%dP%d" % (i, j)))
        body = normalise({"statements": self.rec.stmts, "locks": self.rec.locks,
                          "answers": [[a.status, a.body] for a in self.answers],
                          "lines": _sort_runs([ln for ln in self.lines if ln.startswith("[FFA")]),
                          "rows": rows}, seed=seed)
        path = os.path.join(d, re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".json")
        with io.open(path, "w", encoding="ascii", newline="\n") as fh:
            fh.write(json.dumps(body, sort_keys=True, indent=1))
        return path


_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# No \b before the token: between a space and '-' there is no word boundary,
# so "\b->" never matched and every "-> {id8}" stayed raw.
_ID8_RE = re.compile(r"(?<![0-9A-Za-z_])(lobby|->) ([0-9a-f]{8})(?![0-9A-Za-z_])")
_ROOM_RE = re.compile(r"\bffa_[0-9a-f]{12}\b")
# Columns whose value is read from the real clock (SQL NOW()) rather than the
# frozen one. Compared to the second, they still split at a second's edge
# (dissolve_after_ms read 3703 and 3702 in two runs of one code), so they
# compare by presence, like the answer ages below.
_REAL_CLOCK_INTS = set()
# Answer fields computed from the route's monotonic clock at build time: two
# runs of the same code differ by scheduling, so a twin compares presence.
# xp_gained and gold_gained are the report's pay, metered by the pace
# ceiling against elapsed = clock_timestamp() - the lobby's anchor (the
# report handler's economy meter): a real-clock value against a fixture
# lobby created in the past, so the same code pays 11 or 12 by scheduling.
_REAL_CLOCK_MASK = {"server_age_ms", "admit_left_ms", "dissolve_after_ms",
                    "xp_gained", "gold_gained"}
# The erasure's random placeholder name (deleted_ + 8 hex): named by first
# appearance, like a UUID.
_PLACEHOLDER_RE = re.compile(r"\bdeleted_[0-9a-f]{8}\b")
# A timestamp a route formats into a string (an answer's expires_at, a
# log line's expires=) is SQL NOW() plus an interval, a real-clock value:
# compared by presence, like every datetime.
_ISO_TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?")
# The deadline and slow-commit lines print the route's real elapsed time
# (_asm_elapsed_ms against the wall clock), which scheduling moves: the
# number compares by presence; the route, the stage and the line stay.
_ELAPSED_RE = re.compile(r"(?<![0-9A-Za-z_])(ms|pre_ms)=\d+")
_ELAPSED_LINE_RE = re.compile(r"^\[FFA-ASM\] lobby \S+ (?:deadline|slow_commit) route=")


def _line_template(ln):
    return re.sub(r"[0-9a-f]{8,}|[0-9]+", "#", _UUID_RE.sub("U", ln))


def _sort_runs(lines):
    """Each run of consecutive lines of one template (the same text once
    ids and numbers are masked) in a fixed order: one loop's lines over an
    unordered result (a DELETE ... RETURNING) keep their set, not the
    order the rows came back in."""
    out, i = [], 0
    while i < len(lines):
        t = _line_template(lines[i])
        j = i + 1
        while j < len(lines) and _line_template(lines[j]) == t:
            j += 1
        out.extend(sorted(lines[i:j], key=lambda s: _UUID_RE.sub("U", s)))
        i = j
    return out


def normalise(obj, seed=()):
    """UUIDs by the fixture's seeded names (seed: (uuid, name) pairs), any
    other UUID by first appearance; an 8-hex lobby prefix by the name of the
    seeded UUID it prefixes, else by first appearance; room names masked;
    timestamps to presence; real-clock integers to seconds, and the answer's
    real-clock ages to presence. A row table is walked in the order of its
    rows' masked form, never in the order the random ids sorted it."""
    names = {}
    for u, n in seed:
        names.setdefault(str(u), n)
    seeded = list(names.items())

    def uname(u):
        u = str(u)
        if u not in names:
            names[u] = "U%d" % len(names)
        return names[u]

    def id8name(h):
        for u, n in seeded:
            if u.startswith(h):
                return "I" + n
        return "I" + uname(h)

    def masked(o, key=None):
        """The sort key's form: seeded names kept, every other UUID blank."""
        if isinstance(o, dict):
            return {str(k): masked(v, k) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [masked(v) for v in o]
        if isinstance(o, uuid.UUID):
            return dict(seeded).get(str(o), "U?")
        if isinstance(o, (_dt.datetime, _dt.date)):
            return "ts"
        if isinstance(o, str):
            sd = dict(seeded)
            return _ISO_TS_RE.sub("ts", _PLACEHOLDER_RE.sub(
                "deleted_?", _UUID_RE.sub(lambda m: sd.get(m.group(0), "U?"), o)))
        if key in _REAL_CLOCK_MASK or key in _REAL_CLOCK_INTS:
            return "rt"
        if isinstance(o, (bytes, bytearray, _decimal.Decimal, float)):
            return str(o)
        return o

    def walk(o, key=None):
        if isinstance(o, dict):
            if key == "rows":
                return {str(k): walk(sorted(v, key=lambda r: json.dumps(
                    masked(r), sort_keys=True, default=str)) if isinstance(v, list) else v, k)
                    for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))}
            return {str(k): walk(v, k) for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))}
        if isinstance(o, (list, tuple)):
            return [walk(v) for v in o]
        if isinstance(o, uuid.UUID):
            return uname(o)
        if isinstance(o, (_dt.datetime, _dt.date)):
            return "ts"
        if isinstance(o, str):
            s = _UUID_RE.sub(lambda m: uname(m.group(0)), o)
            s = _ID8_RE.sub(lambda m: "%s %s" % (m.group(1), id8name(m.group(2))), s)
            s = _ROOM_RE.sub("ffa_ROOM", s)
            s = _PLACEHOLDER_RE.sub(lambda m: "deleted_" + uname("ph:" + m.group(0)), s)
            s = _ISO_TS_RE.sub("ts", s)
            if _ELAPSED_LINE_RE.match(s):
                s = _ELAPSED_RE.sub(lambda m: m.group(1) + "=rt", s)
            return s
        if key in _REAL_CLOCK_MASK and isinstance(o, int):
            return "rt"
        if key in _REAL_CLOCK_INTS and isinstance(o, int):
            return round(o / 1000.0)
        if isinstance(o, float):
            return round(o, 6)
        if isinstance(o, _decimal.Decimal):
            return "dec %s" % o
        if isinstance(o, (bytes, bytearray)):
            return "bytes"
        return o
    return walk(obj)
