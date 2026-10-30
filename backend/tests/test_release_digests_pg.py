"""The release digest step against the api's own admin routes, live.

Through `main.app` (its whole middleware chain: the rate limiter, the
maintenance and version gates, the replica write gate, then each route's admin
check and insert) with the session dependency pointed at a throwaway schema
holding `admin_users` (built from the model) and the two registries (their
CREATE TABLE statements read verbatim from migrations 368 and 372):

  P1  a run registers the release row and the 17 game-file rows a fixture DLL
      and a fixture install produce, and each stored row holds exactly what
      the client would report: the lower-case variant, the 12-character
      commit, the DLL's SHA-256, each file's SHA-256 under its client file id;
  P2  a second run with the same inputs inserts nothing, says so, and leaves
      every row, registered_at included, as it was;
  P3  a run signed with a secret the server does not hold, or by a steam id
      that is not an admin, is refused at its first row (exit 1) and inserts
      nothing: the routes' admin check is live, not stubbed;
  P4  the --emit-sql file, applied to a fresh schema as one script, holds the
      same rows as the api path, and applied again inserts nothing.

RELEASE_DIGESTS_TEST_PG_DSN names a database whose name carries
`release_digests` (the module creates and drops schemas there), written
postgresql:// or postgresql+asyncpg://; RELEASE_DIGESTS_TEST_PG_OPTOUT=1 waives
the live cases deliberately. Unset and not waived, every live case FAILS: a
skipped live case reports exit 0 for coverage that did not run.
"""

import asyncio
import hashlib
import io
import os
import re
import sys
import uuid
from contextlib import redirect_stdout
from urllib.parse import urlsplit

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import register_release_digests as rrd  # noqa: E402
import release_digests_fixture as fx  # noqa: E402

DSN_VAR = "RELEASE_DIGESTS_TEST_PG_DSN"
OPTOUT_VAR = "RELEASE_DIGESTS_TEST_PG_OPTOUT"
DSN = os.environ.get(DSN_VAR) or ""
OPTOUT = str(os.environ.get(OPTOUT_VAR) or "").strip().lower() in {"1", "true", "yes", "on"}
SQL_DIR = os.path.join(HERE, "..", "sql")
REGISTRIES = (("368_seat_evidence.sql", "mod_release_digests"),
              ("372_identity_clock_evidence.sql", "game_file_digests"))
RELEASE_COLS = "version, variant, commit_sha, dll_sha256, source"
GAME_COLS = "file_id, game_version, sha256"


def require_pg():
    if DSN:
        name = urlsplit(DSN).path.lstrip("/")
        if "release_digests" not in name:
            pytest.fail("%s points at %r; this module creates and drops schemas there" % (DSN_VAR, name))
        return
    if OPTOUT:
        pytest.skip("%s is set: the live registration cases are deliberately not run" % OPTOUT_VAR)
    pytest.fail("%s is not set, so no registration ran against the api's routes and a database; "
                "set it, or %s=1 to waive the coverage deliberately" % (DSN_VAR, OPTOUT_VAR))


def _sa_url():
    return re.sub(r"^postgresql(\+asyncpg)?://", "postgresql+asyncpg://", DSN)


def _ddl():
    import models
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable
    out = [str(CreateTable(models.AdminUser.__table__).compile(dialect=postgresql.dialect()))]
    for fname, table in REGISTRIES:
        with open(os.path.join(SQL_DIR, fname), encoding="utf-8") as f:
            found = re.findall(r"CREATE TABLE IF NOT EXISTS %s \(.*?\n\);" % table, f.read(), re.S)
        assert len(found) == 1, (fname, table)
        out.append(found[0])
    return out


def _steam_id():
    """A generated 17-digit id (no fixed literal)."""
    return "9" + str(uuid.uuid4().int)[:16]


class Rig:
    """Throwaway schemas, an engine for the app with its search_path pinned to
    the first, and the app as the step's transport."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.schemas = []
        self.secret = "rd-" + uuid.uuid4().hex

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    async def new_schema(self):
        from sqlalchemy import text
        name = "rd_%s" % uuid.uuid4().hex[:12]
        self.schemas.append(name)
        async with self.seed.connect() as conn:
            await conn.execute(text('CREATE SCHEMA "%s"' % name))
            await conn.execute(text('SET search_path TO "%s"' % name))
            for stmt in _ddl():
                await conn.execute(text(stmt))
            await conn.commit()
        return name

    async def up(self):
        from sqlalchemy.ext.asyncio import create_async_engine
        self.seed = create_async_engine(_sa_url())
        self.name = await self.new_schema()
        self.engine = create_async_engine(_sa_url(), connect_args={"server_settings": {"search_path": self.name}})

    async def down(self):
        from sqlalchemy import text
        try:
            await self.engine.dispose()
            async with self.seed.connect() as conn:
                for name in self.schemas:
                    await conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % name))
                await conn.commit()
        finally:
            await self.seed.dispose()

    async def db(self):
        from sqlalchemy.ext.asyncio import AsyncSession
        async with AsyncSession(self.engine, expire_on_commit=False) as s:
            yield s

    async def fetch(self, sql, schema=None):
        from sqlalchemy import text
        async with self.seed.connect() as conn:
            await conn.execute(text('SET search_path TO "%s"' % (schema or self.name)))
            rows = (await conn.execute(text(sql))).all()
            await conn.rollback()
        return [tuple(r) for r in rows]

    def registries(self, schema=None, stamped=False):
        extra = ", registered_at" if stamped else ""
        return (self.run(self.fetch("SELECT %s%s FROM mod_release_digests ORDER BY 1, 2, 3, 4"
                                    % (RELEASE_COLS, extra), schema)),
                self.run(self.fetch("SELECT %s%s FROM game_file_digests ORDER BY 1, 2, 3"
                                    % (GAME_COLS, extra), schema)))

    async def add_admin(self, steam_id):
        from sqlalchemy import text
        async with self.seed.connect() as conn:
            await conn.execute(text('SET search_path TO "%s"' % self.name))
            await conn.execute(text("INSERT INTO admin_users (steam_id, granted_at) VALUES (:s, now())"),
                               {"s": steam_id})
            await conn.commit()

    async def script(self, sql, schema):
        """A migration file sent whole, as psql -f sends it: one simple-protocol call."""
        import asyncpg
        conn = await asyncpg.connect(re.sub(r"^postgresql\+asyncpg://", "postgresql://", DSN),
                                     server_settings={"search_path": schema})
        try:
            return await conn.execute(sql)
        finally:
            await conn.close()

    def transport(self, url, headers):
        import httpx
        import main

        async def go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                         base_url="http://t") as c:
                r = await c.post(url, headers=headers)
            return r.status_code, r.text

        return self.run(go())


@pytest.fixture()
def rig(monkeypatch):
    require_pg()
    import database
    import main
    r = Rig()
    r.run(r.up())
    monkeypatch.setattr(main, "ADMIN_HMAC_SECRET", r.secret)
    monkeypatch.setitem(main.app.dependency_overrides, database.get_db, r.db)
    try:
        yield r
    finally:
        r.run(r.down())
        r.loop.close()


@pytest.fixture()
def release(tmp_path):
    root, expected = fx.make_install(str(tmp_path / "lib"))
    data = fx.build_assembly(version="1.41.0")
    dll = tmp_path / "CompetitiveRounds.dll"
    dll.write_bytes(data)
    rows = ([("1.41.0", "standalone", fx.FULL_SHA[:12], hashlib.sha256(data).hexdigest(), "release")],
            [(fid, "steam." + fx.BUILD_ID, sha) for fid, (_name, sha) in sorted(expected.items())])
    argv = ["--dll", str(dll), "--version", "1.41.0", "--variant", "standalone", "--commit", fx.FULL_SHA,
            "--game-root", root]
    return argv, rows


def _run(argv, environ, transport=None):
    out = io.StringIO()
    with redirect_stdout(out):
        code = rrd.main(argv, environ=environ, transport=transport)
    return code, out.getvalue()


def test_p1_p2_registers_every_row_then_a_rerun_inserts_nothing(rig, release):
    argv, expected = release
    admin = _steam_id()
    rig.run(rig.add_admin(admin))
    env = {"ADMIN_HMAC_SECRET": rig.secret, "SCR_API_BASE": "http://t"}
    code, out = _run(argv + ["--admin", admin], env, rig.transport)
    assert code == rrd.EXIT_OK, out
    assert "DONE     18 rows: 18 inserted, 0 already registered." in out
    assert rig.registries() == expected
    before = rig.registries(stamped=True)
    code, out = _run(argv + ["--admin", admin], env, rig.transport)
    assert code == rrd.EXIT_OK, out
    assert "DONE     18 rows: nothing inserted, every row was already registered." in out
    assert out.count("(already registered)") == 18
    assert rig.registries(stamped=True) == before


def test_p3_an_unverified_signature_or_a_non_admin_inserts_nothing(rig, release):
    argv, _expected = release
    admin = _steam_id()
    rig.run(rig.add_admin(admin))
    calls = []

    def counted(url, headers):
        calls.append(url)
        return rig.transport(url, headers)

    code, out = _run(argv + ["--admin", admin],
                     {"ADMIN_HMAC_SECRET": rig.secret + "x", "SCR_API_BASE": "http://t"}, counted)
    assert code == rrd.EXIT_SERVER and len(calls) == 1, out
    assert "HTTP 403" in out and "Bad admin signature" in out
    code, out = _run(argv + ["--admin", _steam_id()],
                     {"ADMIN_HMAC_SECRET": rig.secret, "SCR_API_BASE": "http://t"}, counted)
    assert code == rrd.EXIT_SERVER and len(calls) == 2, out
    assert "HTTP 403" in out and "Not an admin" in out
    assert rig.registries() == ([], [])


def test_p4_the_emitted_migration_holds_the_api_rows_and_reruns_to_nothing(rig, release, tmp_path):
    argv, expected = release
    admin = _steam_id()
    rig.run(rig.add_admin(admin))
    code, out = _run(argv + ["--admin", admin],
                     {"ADMIN_HMAC_SECRET": rig.secret, "SCR_API_BASE": "http://t"}, rig.transport)
    assert code == rrd.EXIT_OK, out
    path = tmp_path / "fixture_release_digests.sql"
    code, out = _run(argv + ["--emit-sql", str(path)], {})
    assert code == rrd.EXIT_OK, out
    sql = path.read_text(encoding="ascii")
    fresh = rig.run(rig.new_schema())
    assert rig.run(rig.script(sql, fresh)) == "COMMIT"
    assert rig.registries(fresh) == expected == rig.registries()
    before = rig.registries(fresh, stamped=True)
    assert rig.run(rig.script(sql, fresh)) == "COMMIT"
    assert rig.registries(fresh, stamped=True) == before
