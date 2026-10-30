"""Admin evidence report, phase 1a item 4: the four report routes.

Live PostgreSQL, through the api's own app (`main.app`, its whole middleware
chain) with the session dependency pointed at a throwaway schema whose
`players`, `admin_users`, `ranked_series`, `matches`, `flagged_matches` and
`admin_actions` tables are built from the models (columns and types, the
`matches` indexes, no foreign keys). A statement recorder on the engine shows
which statements each request ran.

  P3  (4.2) the key gate and the actor gate give one byte-identical refusal
      for a missing or wrong key and a missing, malformed, unlinked or
      non-roster actor, before any argument is parsed (malformed arguments
      are sent), with maintenance off and on; the key gate is the outermost
      middleware; a keyless request to another internal path keeps its
      maintenance answer and its `forbidden` body.
  P5  (4.3) with the recovery probe true every route answers `409
      primary_only` and runs no further statement.
  P6  (4.4) one `admin_actions` row per served page, `details` with the 1a
      key set and `rules` exactly `{"report":"absent"}`, over all seven pages
      of a 30-game pair and player report; page 8 refused with no row; a
      failed insert gives `503 audit_unavailable` and no body; a deadline
      before the audit gives `503 deadline` and no row.
  P11 (1.3) selectors: 12-hex collision, R2 series id first, the series
      bound, interleaved orientations and seats with equal timestamps, a
      distractor, zero cohorts, 1-game cohorts per route; the route
      statements equal the statements the EXPLAIN gates read.
  4.5 size of the seven pages and of a page of full-width escaped text.
  4.6 the per-actor rate bound with `Retry-After`.
  P9  (2.6, through the routes) a duplicate fact refuses with `503
      unavailable (population)` on every route (game set) and on the R3 and
      R4 summary pages (window source), no audit row, no new generation, the
      one-fact twin served before.
  3.5 statement scan: admin_evidence.py writes nothing but the audit insert.
  4.7 (item 1a-5) the admin-authorized-consumer class: all 50 storage
      sentinels served only inside the cells, or the catalog spread, of the
      key that reads them, and none on any refusal path.

Test accounts, steam ids and Discord ids are generated per run.
`ADMIN_EVIDENCE_TEST_PG_DSN` names a database whose name carries
`admin_evidence`; unset, the module fails (an affirmative
`ADMIN_EVIDENCE_TEST_PG_OPTOUT` makes that named skips).
"""

import ast
import asyncio
import datetime as dt
import json
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import admin_evidence as ae  # noqa: E402
import models  # noqa: E402
from test_admin_evidence_cells_pg import DSN, _required_defaults, require_pg  # noqa: E402

KEY = "test-key-" + uuid.uuid4().hex
REFUSED = (403, b'{"detail":"refused"}')
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
ROOT = ae.EVIDENCE_ROOT
TABLES = (models.Player, models.AdminUser, models.RankedSeries, models.Match,
          models.FlaggedMatch, models.AdminAction)
REQUIRED = {m.__table__.name: _required_defaults(m.__table__) for m in TABLES}
AUDIT_KEYS = {"schema", "shape", "games", "page", "pages", "b_pid", "rules", "registry",
              "pop_computed_at", "codes", "via"}
_SEQ = [0]


def _digits(n):
    """A generated all-digit id of `n` digits (no fixed literal)."""
    _SEQ[0] += 1
    body = str(uuid.uuid4().int)[: n - 4] + "%04d" % (_SEQ[0] % 10000)
    return ("9" + body)[:n]


def _ddl():
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable
    dialect = postgresql.dialect()
    out = []
    for m in TABLES:
        t = m.__table__
        out.append(str(CreateTable(t, include_foreign_key_constraints=[]).compile(dialect=dialect)))
        if t.name == "matches":
            for idx in t.indexes:
                out.append(str(CreateIndex(idx).compile(dialect=dialect)))
    return out


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class _ProbeTrue:
    def scalar(self):
        return True


class Rig:
    """A schema, an engine for the app (search_path pinned to the schema,
    every statement recorded) and a seeding connection."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.schema = "ae_routes_%s" % uuid.uuid4().hex[:10]
        self.stmts = []
        self.probe_true = False

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    async def up(self):
        from sqlalchemy import event, text
        from sqlalchemy.ext.asyncio import create_async_engine
        self.seed_engine = create_async_engine(DSN)
        self.conn = await self.seed_engine.connect()
        await self.conn.execute(text('CREATE SCHEMA "%s"' % self.schema))
        await self.conn.execute(text('SET search_path TO "%s"' % self.schema))
        for stmt in _ddl():
            await self.conn.execute(text(stmt))
        await self.conn.commit()
        await self.conn.execute(text('SET search_path TO "%s"' % self.schema))
        self.engine = create_async_engine(
            DSN, connect_args={"server_settings": {"search_path": self.schema}})

        def record(conn, cursor, statement, params, context, executemany):
            self.stmts.append(statement)

        event.listen(self.engine.sync_engine, "before_cursor_execute", record)

    async def down(self):
        from sqlalchemy import text
        try:
            await self.engine.dispose()
            await self.conn.rollback()
            await self.conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % self.schema))
            await self.conn.commit()
        finally:
            await self.conn.close()
            await self.seed_engine.dispose()

    async def db(self):
        from sqlalchemy.ext.asyncio import AsyncSession
        rig = self

        class _Session(AsyncSession):
            async def execute(self, statement, *a, **k):
                if rig.probe_true and "pg_is_in_recovery" in str(statement):
                    rig.stmts.append("SELECT pg_is_in_recovery() -- stubbed true")
                    return _ProbeTrue()
                return await super().execute(statement, *a, **k)

        async with _Session(self.engine, expire_on_commit=False) as s:
            yield s

    async def _insert(self, table, row):
        from sqlalchemy import text
        full = dict(REQUIRED[table])
        full.update(row)
        names = sorted(full)
        vals = ", ".join("CAST(:%s AS jsonb)" % n if n in ("flag_details", "details")
                         else ":%s" % n for n in names)
        await self.conn.execute(text("INSERT INTO %s (%s) VALUES (%s)"
                                     % (table, ", ".join(names), vals)), full)

    async def player(self, admin=False, linked=True, name=None):
        pid, steam = uuid.uuid4(), _digits(17)
        discord = _digits(18) if linked else None
        await self._insert("players", {"id": pid, "steam_id": steam,
                                       "display_name": name or "p-" + pid.hex[:6],
                                       "discord_id": discord})
        if admin:
            await self._insert("admin_users", {"steam_id": steam})
        await self.conn.commit()
        return pid, steam, discord

    async def series(self, p1, p2, sid=None):
        sid = sid or uuid.uuid4()
        await self._insert("ranked_series", {"id": sid, "player1_id": p1, "player2_id": p2,
                                             "status": "complete"})
        await self.conn.commit()
        return sid

    async def match(self, p1, p2, ended, reporter=None, mid=None, series=None, **cols):
        row = {"id": mid or uuid.uuid4(), "player1_id": p1, "player2_id": p2,
               "ended_at": ended, "reported_by": reporter if reporter else p1,
               "series_id": series}
        row.update(cols)
        await self._insert("matches", row)
        return row["id"]

    async def commit(self):
        await self.conn.commit()

    async def audits(self):
        from sqlalchemy import text
        rows = (await self.conn.execute(text(
            "SELECT admin_steam_id, action, target_steam_id, target_match_id, "
            "target_series_id, details FROM admin_actions ORDER BY created_at, id"))).mappings().all()
        await self.conn.commit()
        return [dict(r) for r in rows]

    async def get(self, path, key=KEY, actor=None):
        import httpx
        import main
        headers = {}
        if key is not None:
            headers["X-Internal-Key"] = key
        if actor is not None:
            headers["X-Actor-Discord-Id"] = actor
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://t") as c:
            r = await c.get(path, headers=headers)
        return r.status_code, r.content, r.headers


@pytest.fixture()
def rig(monkeypatch):
    require_pg()
    import database
    import main
    r = Rig()
    r.run(r.up())
    monkeypatch.setenv("API_SECRET_KEY", KEY)
    monkeypatch.setitem(main.app.dependency_overrides, database.get_db, r.db)
    monkeypatch.setattr(ae, "_RATE", {})
    monkeypatch.setattr(ae, "_INFLIGHT", [0])
    monkeypatch.setattr(ae, "_CACHE", [ae.PopulationCache(base_rss_mb=ae.SIZING_BASE_RSS_MB)])
    try:
        yield r
    finally:
        r.run(r.down())
        r.loop.close()


def _body(content):
    return json.loads(content.decode("utf-8"))


async def _admin(rig):
    _pid, _steam, discord = await rig.player(admin=True)
    return discord


async def _pair_games(rig, n, a, b, start):
    """`n` A-B games, newest first by construction, orientations alternating,
    every third pair sharing one ended_at; returns ids newest first."""
    ids = []
    for i in range(n):
        ended = start - dt.timedelta(minutes=(i // 2) * 2 + (0 if i % 3 else 1))
        p1, p2 = (a, b) if i % 2 == 0 else (b, a)
        ids.append((ended, await rig.match(p1, p2, ended)))
    await rig.commit()
    return [m for _e, m in sorted(ids, key=lambda t: (t[0], t[1]), reverse=True)]


def _route_paths(code, steam_a, steam_b, games="abc"):
    return {"game": "%s/game/%s" % (ROOT, code),
            "series": "%s/series/%s" % (ROOT, code),
            "pair": "%s/pair?a=%s&b=%s&games=%s" % (ROOT, steam_a, steam_b, games),
            "player": "%s/player/%s?games=%s" % (ROOT, steam_a, games)}


_READS = ("matches", "ranked_series", "admin_actions", "flagged_matches", "pg_is_in_recovery")


def _read_statements(stmts):
    return [s for s in stmts if any(w in s for w in _READS)]


# ── P3: the gate ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("maintenance", [False, True])
def test_p3_every_refusal_is_identical_and_precedes_parsing(rig, monkeypatch, maintenance):
    import main
    monkeypatch.setattr(main, "_in_maintenance", maintenance)

    async def go():
        admin = await _admin(rig)
        _p, _s, linked = await rig.player(admin=False)
        unlinked = _digits(18)
        paths = _route_paths("zz-not-hex", "x", "y")
        cases = []
        for shape, path in paths.items():
            for label, key, actor in (
                    ("no key", None, admin), ("wrong key", KEY + "x", admin),
                    ("no actor", KEY, None), ("malformed actor", KEY, "12a4"),
                    ("too long actor", KEY, "1" * (ae.AER_CONTRACT_BOUNDS["ACTOR_ID_MAX_DIGITS"] + 1)),
                    ("unlinked actor", KEY, unlinked), ("non-roster actor", KEY, linked)):
                rig.stmts.clear()
                status, content, _h = await rig.get(path, key=key, actor=actor)
                cases.append((shape, label, status, content, list(rig.stmts)))
        rig.stmts.clear()
        parsed = [await rig.get(p, actor=admin) for p in paths.values()]
        other = await rig.get("/api/v1/internal/not-an-evidence-path", key=None)
        return cases, parsed, other

    cases, parsed, other = rig.run(go())
    assert len(cases) == 28
    for shape, label, status, content, stmts in cases:
        assert (status, content) == REFUSED, (shape, label, status, content)
        assert not _read_statements(stmts), (shape, label, stmts)
        if label in ("no key", "wrong key", "no actor", "malformed actor", "too long actor"):
            assert stmts == [], (shape, label, stmts)
    # a valid key and a roster actor reach parsing: each malformed argument
    # is now refused by its own word, in either maintenance state
    assert [(s, _body(c)["detail"]) for s, c, _h in parsed] == [
        (400, "bad_argument"), (400, "bad_argument"), (400, "bad_argument"),
        (400, "bad_argument")]
    if maintenance:
        assert other[0] == 503 and _body(other[1])["error"] == "maintenance"
    else:
        assert (other[0], _body(other[1])) == (403, {"error": "forbidden"})
    print("GATE p3 maintenance=%s: 28 refusals byte-identical %r, none before a read; "
          "valid actor parses (400 x4); other internal path %d"
          % (maintenance, REFUSED, other[0]))


def test_6_2_each_route_refuses_bad_actors_before_any_read(rig):
    """Design 6.2: with VALID arguments, a malformed, an unlinked and a
    non-roster actor are refused on every route before any read (statement
    recorder); twelve refusals, byte-identical. A route whose gate call is
    removed lets these actors reach its reads, and only that route."""
    async def go():
        await _admin(rig)
        _p, _s, linked = await rig.player(admin=False)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        gid = await rig.match(a, b, NOW - dt.timedelta(hours=1))
        await rig.commit()
        out = []
        for shape, path in _route_paths(gid.hex, sa, sb, games="3").items():
            for label, actor in (("malformed", "x1"), ("unlinked", _digits(18)),
                                 ("non-roster", linked)):
                rig.stmts.clear()
                status, content, _h = await rig.get(path, actor=actor)
                out.append((shape, label, status, content, _read_statements(rig.stmts)))
        return out

    out = rig.run(go())
    assert len(out) == 12
    bad = [(shape, label, status, content[:120], reads[:2])
           for shape, label, status, content, reads in out
           if (status, content) != REFUSED or reads]
    assert bad == [], "routes serving a refused actor: %r" % sorted({b[0] for b in bad})
    print("GATE 6.2: twelve refusals (4 routes x malformed, unlinked, non-roster) "
          "byte-identical, no read statement")


def test_p9_one_game_set_serves_every_route_under_a_lease(rig, monkeypatch):
    """No cache key carries a route shape (design 2.6): the four routes share
    one display game set, rebuilt once; each request reads it under a lease
    and releases it."""
    seen = []
    real = ae._game_page

    async def watched(rep, games, cohort, subjects, game_set):
        seen.append(game_set.leases)
        return await real(rep, games, cohort, subjects, game_set)

    monkeypatch.setattr(ae, "_game_page", watched)

    async def go():
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        s = await rig.series(a, b)
        gid = await rig.match(a, b, NOW - dt.timedelta(hours=1), series=s)
        await rig.commit()
        paths = _route_paths(gid.hex, sa, sb, games="1")
        return [await rig.get(paths[k] + ("&page=2" if k in ("pair", "player") else ""),
                              actor=admin) for k in ("game", "series", "pair", "player")]

    served = rig.run(go())
    assert [s for s, _c, _h in served] == [200] * 4, [c[:200] for _s, c, _h in served]
    cache = ae._CACHE[0]
    game_sets = [k for k, g in cache.live.items() if g.kind == "game"]
    assert game_sets == [ae._display_key()], game_sets
    assert cache._gen == 1
    assert seen == [1, 1, 1, 1]
    assert all(g.leases == 0 for g in cache.live.values()) and cache.retired == []
    print("GATE p9 routes: one game set %r, gen 1, leased once per build, released"
          % (game_sets[0][:2],))


def test_p3_the_key_gate_is_the_outermost_middleware():
    import main
    outer = main.app.user_middleware[0]
    assert outer.kwargs.get("dispatch") is ae.evidence_key_gate
    dispatches = [m.kwargs.get("dispatch") for m in main.app.user_middleware]
    assert dispatches.count(ae.evidence_key_gate) == 1
    assert dispatches.index(main.replica_write_gate) == 1
    print("GATE p3 order: evidence_key_gate outermost, replica_write_gate next")


# ── P5: primary only ───────────────────────────────────────────────────────

def test_p5_recovery_probe_true_refuses_every_route_and_reads_nothing_more(rig):
    async def go():
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        gid = await rig.match(a, b, NOW - dt.timedelta(hours=1))
        await rig.commit()
        rig.probe_true = True
        out = []
        for shape, path in _route_paths(gid.hex, sa, sb, games="3").items():
            rig.stmts.clear()
            status, content, _h = await rig.get(path, actor=admin)
            after = rig.stmts[[i for i, s in enumerate(rig.stmts)
                               if "pg_is_in_recovery" in s][0] + 1:]
            out.append((shape, status, content, after))
        return out

    for shape, status, content, after in rig.run(go()):
        assert (status, _body(content)) == (409, {"detail": "primary_only"}), shape
        assert after == [], (shape, after)
    print("GATE p5: four routes 409 primary_only, no statement after the probe")


# ── P6: the audit ──────────────────────────────────────────────────────────

def test_p6_one_audit_row_per_page_over_seven_pages_of_pair_and_player(rig):
    async def go():
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        ids = await _pair_games(rig, 30, a, b, NOW - dt.timedelta(hours=2))
        out = {}
        for shape, path in (("pair", "%s/pair?a=%s&b=%s&games=30" % (ROOT, sa, sb)),
                            ("player", "%s/player/%s?games=30" % (ROOT, sa))):
            pages = []
            for page in range(1, 9):
                before = len(await rig.audits())
                status, content, _h = await rig.get(path + "&page=%d" % page, actor=admin)
                rows = await rig.audits()
                pages.append((page, status, content, rows[before:]))
            out[shape] = pages
        return ids, sa, b, out

    ids, sa, b, out = rig.run(go())
    codes = [ae._code(i) for i in ids]
    for shape, pages in out.items():
        seen = []
        for page, status, content, new in pages:
            if page == 8:
                assert (status, _body(content)) == (400, {"detail": "bad_argument (page)"})
                assert new == [], shape
                continue
            assert status == 200, (shape, page, content[:300])
            assert len(content) <= ae.AER_CONTRACT_BOUNDS["RESPONSE_BYTES_MAX"]
            body = _body(content)
            assert (body["shape"], body["page"], body["pages"]) == (shape, page, 7)
            assert body["rules"] == {"report": "absent"}
            assert len(new) == 1, (shape, page, new)
            d = new[0]["details"]
            d = json.loads(d) if isinstance(d, str) else d
            assert set(d) == AUDIT_KEYS, sorted(d)
            assert d["rules"] == {"report": "absent"}
            assert "loader" not in d["rules"] and "eval" not in d["rules"]
            assert (d["schema"], d["shape"], d["page"], d["pages"], d["games"], d["via"]) == (
                "1a", shape, page, 7, 30, "discord")
            assert new[0]["action"] == "evidence_report"
            assert new[0]["target_steam_id"] == sa
            assert d["b_pid"] == (str(b) if shape == "pair" else None)
            if page == 1:
                assert body["games"] == [] and body["windows"] and body["summary"]
                assert "win_computed_at" in body["population"]
                assert len(body["windows"]) == (2 if shape == "pair" else 1)
                assert all(w["covered"] == 30 and w["games"] == 30 for w in body["windows"])
            else:
                got = [g["code"] for g in body["games"]]
                assert got == d["codes"] and len(got) == 5
                seen += got
        assert seen == codes, shape
    print("GATE p6: pair and player, pages 1-7 one row each with the 1a key set, "
          "rules {report: absent}; page 8 400 no row; games in cohort order")


def test_p9_pair_summary_ttl_boundary_uses_one_window_generation(rig, monkeypatch):
    """Both pair orientations and win_computed_at use one leased source even
    when that source reaches its TTL after the first lease."""
    clock = _Clock()
    cache = ae.PopulationCache(clock=clock, base_rss_mb=ae.SIZING_BASE_RSS_MB)
    monkeypatch.setattr(ae, "_CACHE", [cache])
    window_leases, result_sources = [], []
    original_lease = ae._Report.lease
    original_memo_get = ae.PopulationCache.memo_get

    async def lease(rep, key, basis=None):
        generation = await original_lease(rep, key, basis)
        if basis is not None:
            window_leases.append((generation.gen, generation.computed_at))
            if len(window_leases) == 1:
                clock.t += ae.AER_CONTRACT_BOUNDS["POP_TTL_S"]
        return generation

    def memo_get(self, comp, generation):
        result_sources.append((generation.gen, generation.computed_at))
        return original_memo_get(self, comp, generation)

    monkeypatch.setattr(ae._Report, "lease", lease)
    monkeypatch.setattr(ae.PopulationCache, "memo_get", memo_get)

    async def go():
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        await rig.match(a, b, NOW - dt.timedelta(hours=1), reporter=a,
                        p1_net_hitch50=10)
        await rig.match(b, a, NOW - dt.timedelta(hours=2), reporter=b,
                        p1_net_hitch50=20)
        await rig.commit()
        return await rig.get("%s/pair?a=%s&b=%s&games=2" % (ROOT, sa, sb), actor=admin)

    status, content, _headers = rig.run(go())
    assert status == 200, content[:300]
    body = _body(content)
    assert [w["oi"] for w in body["windows"]] == [0, 1]
    assert [s["oi"] for s in body["summary"]] == [0, 1]
    slots = ae.AER_WIRE["1a"]["summary"]
    decoded = [[dict(zip(slots, row)) for row in s["cells"]] for s in body["summary"]]
    assert all(any(c["state"] == "ok" and c["pop_n"] for c in cells)
               for cells in decoded), decoded
    assert len(window_leases) == 1, window_leases
    assert result_sources and set(result_sources) == {window_leases[0]}, result_sources
    assert body["population"]["win_computed_at"] == ae._iso(window_leases[0][1])
    print("GATE p9 pair TTL boundary: two orientations use window generation %d at %s"
          % window_leases[0])


def test_p6_a_failed_audit_insert_is_503_with_no_body_and_no_row(rig, monkeypatch):
    monkeypatch.setattr(ae, "AUDIT_SQL", ae.AUDIT_SQL.replace(
        "INSERT INTO admin_actions ", "INSERT INTO admin_actions_absent "))

    async def go():
        admin = await _admin(rig)
        a, _s, _d = await rig.player()
        b, _s, _d = await rig.player()
        gid = await rig.match(a, b, NOW - dt.timedelta(hours=1))
        await rig.commit()
        r = await rig.get("%s/game/%s" % (ROOT, gid.hex), actor=admin)
        return r, await rig.audits()

    (status, content, _h), rows = rig.run(go())
    assert (status, _body(content)) == (503, {"detail": "audit_unavailable"})
    assert rows == []
    print("GATE p6 forced insert failure: 503 audit_unavailable, no body, no row")


def test_p6_a_deadline_before_the_audit_is_503_with_no_row(rig, monkeypatch):
    import time
    calls = [0]

    def clock():
        calls[0] += 1
        return time.monotonic() + (0 if calls[0] == 1 else 3600)

    monkeypatch.setattr(ae, "_aer_clock", clock)

    async def go():
        admin = await _admin(rig)
        a, _s, _d = await rig.player()
        b, _s, _d = await rig.player()
        gid = await rig.match(a, b, NOW - dt.timedelta(hours=1))
        await rig.commit()
        r = await rig.get("%s/game/%s" % (ROOT, gid.hex), actor=admin)
        return r, await rig.audits()

    (status, content, _h), rows = rig.run(go())
    assert (status, _body(content)) == (503, {"detail": "deadline"})
    assert rows == [] and calls[0] >= 2
    print("GATE p6 forced deadline before the audit: 503 deadline, no row")


# ── P11: selectors ─────────────────────────────────────────────────────────

def test_p11_route_statements_are_the_explain_gated_statements():
    import test_admin_evidence_explain_pg as ex
    assert ae.R1_CODE_SQL == ex.R1_CODE
    assert ae.R2_SERIES_SQL == ex.R2_SERIES
    assert ae.R3_PAIR_SQL == ex.R3_PAIR
    assert ae.R4_PLAYER_SQL == ex.R4_PLAYER
    assert ae.SEAT_BASELINE_SQL.count("ORDER BY m.ended_at DESC, m.id DESC LIMIT") == 2
    print("GATE p11 statements: R1 code, R2, R3, R4 equal to the EXPLAIN-gated text")


def test_p11_r1_full_id_selects_and_a_shared_code_is_ambiguous(rig):
    async def go():
        admin = await _admin(rig)
        a, _s, _d = await rig.player()
        b, _s, _d = await rig.player()
        prefix = uuid.uuid4().hex[:12]
        g1 = uuid.UUID(prefix + uuid.uuid4().hex[12:])
        g2 = uuid.UUID(prefix + uuid.uuid4().hex[12:])
        await rig.match(a, b, NOW - dt.timedelta(hours=1), mid=g1)
        await rig.match(b, a, NOW - dt.timedelta(hours=2), mid=g2)
        g3 = await rig.match(a, b, NOW - dt.timedelta(hours=3))
        await rig.commit()
        full = await rig.get("%s/game/%s" % (ROOT, str(g1)), actor=admin)
        code = await rig.get("%s/game/%s" % (ROOT, prefix), actor=admin)
        own = await rig.get("%s/game/%s" % (ROOT, ae._code(g3)), actor=admin)
        return g1, g3, full, code, own

    g1, g3, full, code, own = rig.run(go())
    assert full[0] == 200 and _body(full[1])["games"][0]["match_id"] == str(g1)
    assert (code[0], _body(code[1])) == (
        400, {"detail": "bad_argument (code ambiguous; use the full id)"})
    assert own[0] == 200 and _body(own[1])["games"][0]["match_id"] == str(g3)
    print("GATE p11 r1: full id selects, shared 12-hex code ambiguous, own code selects")


def test_p11_r2_series_id_first_bound_and_empty(rig):
    async def go():
        admin = await _admin(rig)
        a, _s, _d = await rig.player()
        b, _s, _d = await rig.player()
        sb = await rig.series(a, b)
        b_games = [await rig.match(a, b, NOW - dt.timedelta(hours=10 - i), series=sb)
                   for i in range(2)]
        sa = await rig.series(a, b, sid=b_games[0])   # series A's id is a series-B game id
        a_games = [await rig.match(b, a, NOW - dt.timedelta(hours=20 - i), series=sa)
                   for i in range(3)]
        s10 = await rig.series(a, b)
        for i in range(10):
            await rig.match(a, b, NOW - dt.timedelta(hours=30, minutes=i), series=s10)
        s11 = await rig.series(a, b)
        for i in range(11):
            await rig.match(a, b, NOW - dt.timedelta(hours=40, minutes=i), series=s11)
        empty = await rig.series(a, b)
        await rig.commit()
        cross = await rig.get("%s/series/%s" % (ROOT, sa.hex), actor=admin)
        by_game = await rig.get("%s/series/%s" % (ROOT, ae._code(a_games[1])), actor=admin)
        ten = await rig.get("%s/series/%s" % (ROOT, s10.hex), actor=admin)
        ten2 = await rig.get("%s/series/%s?page=2" % (ROOT, s10.hex), actor=admin)
        eleven = await rig.get("%s/series/%s" % (ROOT, s11.hex), actor=admin)
        none = await rig.get("%s/series/%s" % (ROOT, empty.hex), actor=admin)
        lone = await rig.match(a, b, NOW - dt.timedelta(hours=50))
        await rig.commit()
        no_series = await rig.get("%s/series/%s" % (ROOT, lone.hex), actor=admin)
        return a_games, cross, by_game, ten, ten2, eleven, none, no_series, await rig.audits()

    a_games, cross, by_game, ten, ten2, eleven, none, no_series, rows = rig.run(go())
    want = [str(g) for g in a_games]          # oldest first
    assert cross[0] == 200
    assert [g["match_id"] for g in _body(cross[1])["games"]] == want
    assert [g["match_id"] for g in _body(by_game[1])["games"]] == want
    assert ten[0] == 200 and _body(ten[1])["pages"] == 2 and len(_body(ten2[1])["games"]) == 5
    assert (eleven[0], _body(eleven[1])) == (500, {"detail": "too_large"})
    assert (none[0], _body(none[1])) == (404, {"detail": "not_found"})
    assert (no_series[0], _body(no_series[1])) == (404, {"detail": "not_found"})
    assert len(rows) == 4          # cross, by_game, ten, ten2; 404 and 500 write none
    print("GATE p11 r2: series id first (A, not B), by game code, 10 serve, 11 too_large, "
          "empty and seriesless 404, rows 4")


@pytest.mark.parametrize("shape", ["pair", "player"])
def test_p11_interleaved_newest_games_in_order_beside_a_distractor(rig, shape):
    async def go():
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        c, _sc, _d = await rig.player()
        ids = await _pair_games(rig, 12, a, b, NOW - dt.timedelta(hours=3))
        # newer A-C games: not A-B (pair) and without B (player B)
        distract = [await rig.match(a, c, NOW - dt.timedelta(hours=1, minutes=i))
                    for i in range(3)]
        await rig.commit()
        # pair: both orientations of the request, so each branch of the pair
        # query binds :a to A, the player who also has the distractor games
        paths = (["%s/pair?a=%s&b=%s&games=10" % (ROOT, sa, sb),
                  "%s/pair?a=%s&b=%s&games=10" % (ROOT, sb, sa)] if shape == "pair"
                 else ["%s/player/%s?games=10" % (ROOT, sb)])
        gots = []
        for path in paths:
            got = []
            for page in (2, 3):
                status, content, _h = await rig.get(path + "&page=%d" % page, actor=admin)
                assert status == 200, content[:300]
                got += [g["match_id"] for g in _body(content)["games"]]
            gots.append(got)
        return ids, distract, gots

    ids, distract, gots = rig.run(go())
    assert len(gots) == (2 if shape == "pair" else 1)
    for got in gots:
        assert got == [str(i) for i in ids[:10]]
        assert not set(got) & {str(d) for d in distract}
    print("GATE p11 %s interleaved: newest 10 of 12 in order, equal timestamps included, "
          "distractor excluded, %d request orientation(s)" % (shape, len(gots)))


def test_p11_zero_and_one_game_cohorts(rig):
    async def go():
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        c, sc, _d = await rig.player()
        s1 = await rig.series(a, b)
        g = await rig.match(a, b, NOW - dt.timedelta(hours=1), series=s1)
        await rig.commit()
        served = [await rig.get(p, actor=admin) for p in (
            "%s/game/%s" % (ROOT, ae._code(g)), "%s/series/%s" % (ROOT, s1.hex),
            "%s/pair?a=%s&b=%s&games=1&page=2" % (ROOT, sa, sb),
            "%s/player/%s?games=1&page=2" % (ROOT, sa))]
        empty = [await rig.get(p, actor=admin) for p in (
            "%s/pair?a=%s&b=%s" % (ROOT, sa, sc), "%s/player/%s" % (ROOT, sc),
            "%s/player/%s" % (ROOT, _digits(17)))]
        return g, served, empty, await rig.audits()

    g, served, empty, rows = rig.run(go())
    for status, content, _h in served:
        assert status == 200, content[:300]
        assert [x["match_id"] for x in _body(content)["games"]] == [str(g)]
    for status, content, _h in empty:
        assert (status, _body(content)) == (404, {"detail": "not_found"})
    assert len(rows) == 4
    print("GATE p11 cohorts: 1-game cohort serves on R1-R4; zero cohorts 404 with no row")


# ── 4.5 size and 4.6 rate ──────────────────────────────────────────────────

def test_size_a_page_of_full_width_escaped_text_stays_under_the_bound(rig):
    # Every character escapes (a stored NUL is not text, so 0x00 is left out).
    cps = "".join(chr(c) for c in sorted(ae.AER_ESC) if c)
    wide = (cps * ae.AER_CONTRACT_BOUNDS["TEXT_MAX"])[: ae.AER_CONTRACT_BOUNDS["TEXT_MAX"]]

    async def go():
        admin = await _admin(rig)
        a, sa, _d = await rig.player(name=wide)
        b, sb, _d = await rig.player(name=wide)
        for i in range(5):
            await rig.match(a, b, NOW - dt.timedelta(hours=1, minutes=i),
                            invalidated_at=NOW, invalidation_reason=wide)
        await rig.commit()
        return await rig.get("%s/player/%s?games=5&page=2" % (ROOT, sa), actor=admin)

    status, content, _h = rig.run(go())
    assert status == 200, content[:300]
    body = _body(content)
    assert body["subjects"][0]["name"] == ae._aer_enc(wide)
    assert len(content) <= ae.AER_CONTRACT_BOUNDS["RESPONSE_BYTES_MAX"]
    print("GATE size: full-width escaped page %d bytes of %d"
          % (len(content), ae.AER_CONTRACT_BOUNDS["RESPONSE_BYTES_MAX"]))


def test_rate_bound_per_actor_with_retry_after(rig):
    async def go():
        admin = await _admin(rig)
        other = await _admin(rig)
        path = "%s/player/%s" % (ROOT, _digits(17))
        first = [(await rig.get(path, actor=admin))[0]
                 for _ in range(ae.AER_CONTRACT_BOUNDS["RATE_MAX"])]
        over = await rig.get(path, actor=admin)
        another = await rig.get(path, actor=other)
        return first, over, another

    first, over, another = rig.run(go())
    assert first == [404] * ae.AER_CONTRACT_BOUNDS["RATE_MAX"]
    assert (over[0], _body(over[1])) == (429, {"detail": "rate"})
    assert 1 <= int(over[2]["Retry-After"]) <= ae.AER_CONTRACT_BOUNDS["RATE_WINDOW_S"]
    assert another[0] == 404
    print("GATE rate: %d served, the next 429 rate Retry-After %s, another actor unaffected"
          % (len(first), over[2]["Retry-After"]))


# ── 4.7 item 3: the admin-authorized-consumer class (1a-5) ─────────────────

def _sentinel_suffix(column):
    return column.split("_", 1)[1]


def _sentinel_hits(body, by_value):
    """Every place a storage sentinel value sits in a served body, as
    `(column, ki or None, slot)`: inside a wire cell (`cells` rows, slot 0 the
    key number) the hit carries that key and its slot number; inside a
    catalog row (a base key's population spread, `p50`/`p90`/`p99`) it
    carries the row's key and the field name; anywhere else `None` and the
    JSON path."""
    hits = []

    def scan(v, ki, slot):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float, str)) and v in by_value:
            hits.append((by_value[v], ki, slot))

    def walk(v, path):
        if isinstance(v, dict) and set(v) >= {"ki", "key", "fam", "unit", "kind"}:
            for k, child in v.items():
                if k != "ki":
                    scan(child, v["ki"], k)
        elif isinstance(v, dict):
            for k, child in v.items():
                if k == "cells" and isinstance(child, list):
                    for row in child:
                        for slot, x in enumerate(row):
                            scan(x, row[0], slot)
                else:
                    walk(child, path + "/" + str(k))
        elif isinstance(v, list):
            for i, child in enumerate(v):
                walk(child, "%s/%d" % (path, i))
        else:
            scan(v, None, path)     # outside any key: the slot names the place

    walk(body, "")
    return hits


def _under_its_key(column, ki):
    """True when key `ki` reads `column`'s family: the registry entry's
    declared column is `{s}_<suffix>` for this column's suffix."""
    if ki is None or not (0 <= ki < len(ae.REPORT_REGISTRY)):
        return False
    decl = ae.REPORT_REGISTRY[ki].decl
    cols = decl.column if isinstance(decl.column, tuple) else (decl.column,)
    return any(c.startswith("{s}_") and c[4:] == _sentinel_suffix(column) for c in cols)


def test_admin_authorized_consumers_serve_sentinels_only_to_admins(rig, monkeypatch):
    """Design 4.7 item 3. Two games of one series between A and B carry all
    50 storage sentinels (`net_seat_contract.storage_sentinels`); the first is
    reported by p1, the second by p2, so each seat's reporter-only columns
    are served once. (a) With the key and an admin actor, every route serves
    the sentinels only inside the cells, or the catalog spread (a base key's
    population p50/p90/p99), of the key that reads them; the game
    route serves the reporter's 25 once each per game (50 over the two), the
    series route all 50 once each among its game cells, and the pair and
    player routes all 50 among their pages. (b) On every 4.2 refusal path
    (no key, wrong key, unset key, no, malformed, unlinked or non-roster
    actor) no sentinel name or value, and no value's text, is in the body or
    the headers."""
    from net_seat_contract import STORAGE_FIELDS, assert_no_net_seat_sentinels, storage_sentinels
    sentinels = storage_sentinels()
    assert len(sentinels) == 50 and set(sentinels) == set(STORAGE_FIELDS)
    by_value = {v: k for k, v in sentinels.items()}

    async def go():
        admin = await _admin(rig)
        _p, _s, linked = await rig.player(admin=False)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        sid = await rig.series(a, b)
        g1 = await rig.match(a, b, NOW - dt.timedelta(hours=2), reporter=a, series=sid,
                             **sentinels)
        g2 = await rig.match(a, b, NOW - dt.timedelta(hours=1), reporter=b, series=sid,
                             **sentinels)
        await rig.commit()
        served = {}
        for label, path in (("game1", "%s/game/%s" % (ROOT, g1.hex)),
                            ("game2", "%s/game/%s" % (ROOT, g2.hex)),
                            ("series", "%s/series/%s" % (ROOT, sid.hex)),
                            ("pair", "%s/pair?a=%s&b=%s&games=2" % (ROOT, sa, sb)),
                            ("player", "%s/player/%s?games=2" % (ROOT, sa))):
            sep = "&" if "?" in path else "?"
            pages, page, total = [], 1, 1
            while page <= total:
                status, content, _h = await rig.get(path + "%spage=%d" % (sep, page),
                                                    actor=admin)
                assert status == 200, (label, page, content[:300])
                body = _body(content)
                total = body["pages"]
                pages.append(body)
                page += 1
            served[label] = pages
        refusals = []
        paths = _route_paths(g1.hex, sa, sb, games="2")
        paths["series"] = "%s/series/%s" % (ROOT, sid.hex)
        for shape, path in paths.items():
            for label, key, actor in (
                    ("no key", None, admin), ("wrong key", KEY + "x", admin),
                    ("no actor", KEY, None), ("malformed actor", KEY, "12a4"),
                    ("unlinked actor", KEY, _digits(18)), ("non-roster actor", KEY, linked)):
                refusals.append((shape, label) + await rig.get(path, key=key, actor=actor))
        monkeypatch.setenv("API_SECRET_KEY", "")
        for shape, path in paths.items():
            refusals.append((shape, "unset key") + await rig.get(path, key="", actor=admin))
        return served, refusals

    served, refusals = rig.run(go())
    p1_cols = sorted(c for c in STORAGE_FIELDS if c.startswith("p1_"))
    p2_cols = sorted(c for c in STORAGE_FIELDS if c.startswith("p2_"))
    counts = {}
    for label, pages in served.items():
        hits = [h for body in pages for h in _sentinel_hits(body, by_value)]
        stray = [h for h in hits if not _under_its_key(h[0], h[1])]
        assert stray == [], (label, stray[:5])
        base = sorted(c for c, ki, _slot in hits
                      if not ae.REPORT_REGISTRY[ki].is_window and _slot == 1)
        counts[label] = (len(hits), len(base))
        if label == "game1":
            assert base == p1_cols, (label, base)
        elif label == "game2":
            assert base == p2_cols, (label, base)
        else:
            assert base == sorted(STORAGE_FIELDS), (label, base)
    # design 3.3: every page the api served meets the bot's 1a schema
    from test_discord_evidence_bot import bot_ns
    decode = bot_ns()["_aer_decode_response"]
    decoded = sum(1 for pages in served.values() for body in pages if decode(body, "1a"))
    assert decoded == sum(len(pages) for pages in served.values())
    assert len(refusals) == 28
    texts = [str(v) for v in sentinels.values()]
    for shape, label, status, content, headers in refusals:
        assert (status, content) == REFUSED, (shape, label, status, content)
        assert_no_net_seat_sentinels(_body(content), sentinels)
        assert_no_net_seat_sentinels(dict(headers), sentinels)
        blob = content.decode("utf-8") + "\n".join(
            "%s: %s" % (k, v) for k, v in headers.items())
        assert not [t for t in texts if t in blob], (shape, label)
        assert not [c for c in STORAGE_FIELDS if c in blob], (shape, label)
    print("GATE 4.7 sentinels: (all hits, base value slots) per route %s; every hit "
          "under its own key; %d served pages decode under the bot's 1a schema; 28 refusals "
          "carry no sentinel name, value or text" % (sorted(counts.items()), decoded))


# ── P9 through the routes (1a-3 route half) ────────────────────────────────

Z_KI = 10000


def _z_branches(entries=None, partner=False, kis=(Z_KI,)):
    po = (", CASE z.seat WHEN 'p1' THEN g.player2_id ELSE g.player1_id END AS po"
          if partner else "")
    return ["SELECT z.ki, z.val, g.ended_at, g.id, 'seat'::text AS sk, "
            "CASE z.seat WHEN 'p1' THEN g.player1_id ELSE g.player2_id END AS sa, "
            "CAST(NULL AS uuid) AS sb%s FROM g JOIN z_facts z ON z.match_id = g.id "
            "WHERE z.ki = %d AND z.val IS NOT NULL" % (po, k) for k in kis]


async def _z_setup(rig, games):
    from sqlalchemy import text
    await rig.conn.execute(text(
        "CREATE TABLE z_facts (match_id uuid NOT NULL, seat text NOT NULL, "
        "ki integer NOT NULL, val double precision)"))
    await rig.conn.execute(text(
        "INSERT INTO z_facts (match_id, seat, ki, val) VALUES (:m, 'p1', :k, :v)"),
        [{"m": g, "k": Z_KI, "v": float(i)} for i, g in enumerate(games)])
    await rig.conn.commit()


async def _z_duplicate(rig, game):
    from sqlalchemy import text
    await rig.conn.execute(text(
        "INSERT INTO z_facts (match_id, seat, ki, val) VALUES (:m, 'p1', :k, 999.0)"),
        {"m": game, "k": Z_KI})
    await rig.conn.commit()


@pytest.mark.parametrize("source", ["game_set", "window_source"])
def test_p9_a_duplicate_refuses_through_the_routes_and_the_twin_served(rig, monkeypatch,
                                                                       source):
    monkeypatch.setattr(ae, "population_branches", _z_branches)
    clock = _Clock()
    cache = ae.PopulationCache(clock=clock, base_rss_mb=ae.SIZING_BASE_RSS_MB)
    monkeypatch.setattr(ae, "_CACHE", [cache])

    async def go():
        admin = await _admin(rig)
        a, sa, _d = await rig.player()
        b, sb, _d = await rig.player()
        s = await rig.series(a, b)
        games = [await rig.match(a, b, NOW - dt.timedelta(hours=1, minutes=i), series=s)
                 for i in range(3)]
        await rig.commit()
        await _z_setup(rig, games)
        paths = _route_paths(ae._code(games[0]), sa, sb, games="3")
        if source == "game_set":
            twin = await rig.get(paths["game"], actor=admin)
            key = ae._display_key()
            g0, gen0 = cache.live[key], cache._gen
            await _z_duplicate(rig, games[1])
            clock.t += ae.AER_CONTRACT_BOUNDS["POP_TTL_S"]
            n0 = len(await rig.audits())
            out = [(shape, await rig.get(p.replace("games=abc", "games=3"), actor=admin))
                   for shape, p in paths.items()]
        else:
            twin = await rig.get(paths["game"], actor=admin)    # publishes the game set
            key = ae._display_key()
            g0, gen0 = cache.live[key], cache._gen
            await _z_duplicate(rig, games[1])
            n0 = len(await rig.audits())
            out = [(shape, await rig.get(paths[shape] + "&page=1", actor=admin))
                   for shape in ("pair", "player")]
        return twin, key, g0, gen0, n0, out, await rig.audits()

    twin, key, g0, gen0, n0, out, rows = rig.run(go())
    assert twin[0] == 200, twin[1][:300]
    for shape, (status, content, _h) in out:
        assert (status, _body(content)) == (503, {"detail": "unavailable (population)"}), (
            source, shape, status, content[:300])
    assert len(rows) == n0
    assert cache.live[key] is g0 and cache._gen == gen0 and not g0.retired
    assert not any(len(k) == 6 for k in cache.live), "a window source published"
    print("GATE p9 %s duplicate through the routes: %s refused 503 unavailable "
          "(population), no row, gen %d unchanged, twin served"
          % (source, [s for s, _r in out], gen0))


# ── 3.5 statement scan ─────────────────────────────────────────────────────

_WRITE_WORDS = ("INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "ALTER", "DROP",
                "CREATE", "GRANT", "COPY")


def test_admin_evidence_writes_nothing_but_the_audit_insert():
    path = os.path.join(HERE, "..", "api", "admin_evidence.py")
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)):
                docstrings.add(id(node.body[0].value))
    writers = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            words = set(node.value.replace("(", " ").split())
            hit = sorted(w for w in _WRITE_WORDS if w in words)
            if hit:
                writers.append((node.lineno, hit, node.value.strip()[:60]))
    assert [w[1] for w in writers] == [["INSERT"]], writers
    assert writers[0][2].startswith("INSERT INTO admin_actions")
    uses = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "AUDIT_SQL"
            and isinstance(n.ctx, ast.Load)]
    assert len(uses) == 1
    print("GATE 3.5 statement scan: one write statement, the admin_actions audit insert, "
          "used once")
