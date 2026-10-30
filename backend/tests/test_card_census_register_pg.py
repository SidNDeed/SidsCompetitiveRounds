"""The census mode of tools/register_release_digests.py against the api's own route, live.

Through `main.app` (its whole middleware chain, then the census route's admin
check, its body checks and card_evidence.register_census) with the session
dependency pointed at a throwaway schema holding `admin_users` (built from the
model) and card_pool_registry (its CREATE TABLE, its sequence and its gen
column read verbatim from migration 370):

  Q1  for every fixture in card_census_fixture, the route's own answer to the
      file's bytes signed over its digest agrees with the step: every dump the
      step refuses the route refuses (status and detail as the fixture states)
      and stores nothing; every dump the step accepts the route registers;
  Q2  a step run registers the census, the stored row is exactly the one the
      step printed, and a re-run inserts nothing and leaves the row as it was;
  Q3  a run signed with a secret the server does not hold, or by a non-admin,
      is refused (exit 1) and inserts nothing;
  Q4  the --emit-sql file, applied to a fresh schema as one script, holds the
      row the route stored (every column but registered_at and gen), and
      applied again inserts nothing;
  Q5  its post-check raises, and nothing commits, when run alone against an
      empty registry and when the digest is held for another game build.

The DSN and opt-out are test_release_digests_pg.py's (RELEASE_DIGESTS_TEST_PG_DSN,
a database whose name carries `release_digests`; RELEASE_DIGESTS_TEST_PG_OPTOUT=1).
Unset and not waived, every live case FAILS.
"""

import asyncio
import hashlib
import hmac
import io
import json
import os
import re
import sys
import uuid
from contextlib import redirect_stdout
from urllib.parse import urlencode, urlsplit

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import card_census_fixture as cf  # noqa: E402
import register_release_digests as rrd  # noqa: E402

DSN_VAR = "RELEASE_DIGESTS_TEST_PG_DSN"
OPTOUT_VAR = "RELEASE_DIGESTS_TEST_PG_OPTOUT"
DSN = os.environ.get(DSN_VAR) or ""
OPTOUT = str(os.environ.get(OPTOUT_VAR) or "").strip().lower() in {"1", "true", "yes", "on"}
SQL_370 = os.path.join(HERE, "..", "sql", "370_card_evidence.sql")
COLS = "digest, census::text, card_count, slot_count, game_dll_sha256, source"
VERSION = "1.41.0"


def require_pg():
    if DSN:
        name = urlsplit(DSN).path.lstrip("/")
        if "release_digests" not in name:
            pytest.fail("%s points at %r; this module creates and drops schemas there" % (DSN_VAR, name))
        return
    if OPTOUT:
        pytest.skip("%s is set: the live census cases are deliberately not run" % OPTOUT_VAR)
    pytest.fail("%s is not set, so no census registration ran against the api's route and a database; "
                "set it, or %s=1 to waive the coverage deliberately" % (DSN_VAR, OPTOUT_VAR))


def _sa_url():
    return re.sub(r"^postgresql(\+asyncpg)?://", "postgresql+asyncpg://", DSN)


def _ddl():
    import models
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable
    out = [str(CreateTable(models.AdminUser.__table__).compile(dialect=postgresql.dialect()))]
    with open(SQL_370, encoding="utf-8") as f:
        text = f.read()
    for pattern in (r"CREATE TABLE IF NOT EXISTS card_pool_registry \(.*?\n\);",
                    r"CREATE SEQUENCE IF NOT EXISTS card_input_gen;",
                    r"ALTER TABLE card_pool_registry ADD COLUMN IF NOT EXISTS gen [^\n]*;"):
        found = re.findall(pattern, text, re.S)
        assert len(found) == 1, pattern
        out.append(found[0])
    return out


def _steam_id():
    return "9" + str(uuid.uuid4().int)[:16]


class Rig:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.schemas = []
        self.secret = "cc-" + uuid.uuid4().hex

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    async def new_schema(self):
        from sqlalchemy import text
        name = "cc_%s" % uuid.uuid4().hex[:12]
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

    def registry(self, schema=None, stamped=False):
        extra = ", registered_at, gen" if stamped else ""
        return self.run(self.fetch("SELECT %s%s FROM card_pool_registry ORDER BY 1" % (COLS, extra), schema))

    async def add_admin(self, steam_id):
        from sqlalchemy import text
        async with self.seed.connect() as conn:
            await conn.execute(text('SET search_path TO "%s"' % self.name))
            await conn.execute(text("INSERT INTO admin_users (steam_id, granted_at) VALUES (:s, now())"),
                               {"s": steam_id})
            await conn.commit()

    async def script(self, sql, schema):
        import asyncpg
        conn = await asyncpg.connect(re.sub(r"^postgresql\+asyncpg://", "postgresql://", DSN),
                                     server_settings={"search_path": schema})
        try:
            return await conn.execute(sql)
        finally:
            await conn.close()

    def transport(self, url, headers, body=b""):
        import httpx
        import main

        async def go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                         base_url="http://t") as c:
                r = await c.post(url, headers=headers, content=body)
            return r.status_code, r.text

        return self.run(go())

    def post_raw(self, admin, data, digest):
        """The route's own answer to these bytes, signed over `digest`, bypassing the step."""
        sig = hmac.new(self.secret.encode(), ("admin:%s:card_census:%s" % (admin, digest)).encode(),
                       hashlib.sha256).hexdigest()
        url = rrd.CENSUS_ROUTE + "?" + urlencode([("admin_steam_id", admin), ("hmac_signature", sig),
                                                  ("digest", digest)])
        return self.transport(url, {"X-Mod-Version": VERSION, "Content-Type": "application/json"}, data)


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


def _run(argv, environ, transport=None):
    out = io.StringIO()
    with redirect_stdout(out):
        code = rrd.main(argv, environ=environ, transport=transport)
    return code, out.getvalue()


def _file(tmp_path, data, name="CompetitiveRounds.card-census.json"):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def _signed_digest(data):
    """The digest the route is signed over for these bytes: the dump's own when it states a string."""
    try:
        doc = json.loads(data)
    except Exception:
        return "0" * 64
    d = doc.get("digest") if isinstance(doc, dict) else None
    return d if isinstance(d, str) else "0" * 64


def _row(row):
    return (row["digest"], json.dumps(json.loads(row["census"]), sort_keys=True), row["card_count"],
            row["slot_count"], row["game_dll_sha256"], "admin")


def _normal(rows):
    return [(d, json.dumps(json.loads(c), sort_keys=True), n, s, g, src) for d, c, n, s, g, src in rows]


def test_q1_the_route_and_the_step_agree_on_every_fixture(rig, tmp_path):
    admin = _steam_id()
    rig.run(rig.add_admin(admin))
    for name, (data, (status, detail)) in sorted(cf.REFUSED.items()):
        code, out = _run(["--census", _file(tmp_path, data), "--dry-run"], {})
        assert code == rrd.EXIT_REFUSED, (name, out)
        got_status, got_text = rig.post_raw(admin, data, _signed_digest(data))
        assert got_status == status, (name, got_status, got_text)
        if detail is not None:
            assert json.loads(got_text) == {"detail": detail}, (name, got_text)
        assert rig.registry() == [], name
    for name, data in sorted(cf.VALID.items()):
        code, out = _run(["--census", _file(tmp_path, data), "--dry-run"], {})
        assert code == rrd.EXIT_OK, (name, out)
        _body, row = rrd.census_plan(_file(tmp_path, data))
        got_status, got_text = rig.post_raw(admin, data, row["digest"])
        assert got_status == 200, (name, got_text)
        assert json.loads(got_text)["status"] in rrd.CENSUS_STATUSES, (name, got_text)
        assert _row(row) in _normal(rig.registry()), name


def test_q2_a_run_registers_the_printed_row_and_a_rerun_inserts_nothing(rig, tmp_path):
    admin = _steam_id()
    rig.run(rig.add_admin(admin))
    path = _file(tmp_path, cf.VALID["client_file"])
    env = {"ADMIN_HMAC_SECRET": rig.secret, "SCR_API_BASE": "http://t"}
    argv = ["--census", path, "--admin", admin, "--mod-version", VERSION]
    code, out = _run(argv, env, rig.transport)
    assert code == rrd.EXIT_OK, out
    assert "DONE     1 row: 1 inserted." in out
    _body, row = rrd.census_plan(path)
    assert _normal(rig.registry()) == [_row(row)]
    stored = rig.run(rig.fetch("SELECT census::text FROM card_pool_registry"))[0][0]
    assert json.loads(stored) == json.loads(row["census"])
    before = rig.registry(stamped=True)
    code, out = _run(argv, env, rig.transport)
    assert code == rrd.EXIT_OK, out
    assert "(already registered)" in out
    assert rig.registry(stamped=True) == before


def test_q3_an_unverified_signature_or_a_non_admin_inserts_nothing(rig, tmp_path):
    admin = _steam_id()
    rig.run(rig.add_admin(admin))
    path = _file(tmp_path, cf.VALID["client_file"])
    code, out = _run(["--census", path, "--admin", admin, "--mod-version", VERSION],
                     {"ADMIN_HMAC_SECRET": rig.secret + "x", "SCR_API_BASE": "http://t"}, rig.transport)
    assert code == rrd.EXIT_SERVER and "HTTP 403" in out and "Bad admin signature" in out, out
    code, out = _run(["--census", path, "--admin", _steam_id(), "--mod-version", VERSION],
                     {"ADMIN_HMAC_SECRET": rig.secret, "SCR_API_BASE": "http://t"}, rig.transport)
    assert code == rrd.EXIT_SERVER and "HTTP 403" in out and "Not an admin" in out, out
    assert rig.registry() == []


@pytest.mark.parametrize("name", sorted(cf.VALID))
def test_q4_the_emitted_migration_holds_the_routes_row_and_reruns_to_nothing(rig, tmp_path, name):
    admin = _steam_id()
    rig.run(rig.add_admin(admin))
    data = cf.VALID[name]
    path = _file(tmp_path, data)
    code, out = _run(["--census", path, "--admin", admin, "--mod-version", VERSION],
                     {"ADMIN_HMAC_SECRET": rig.secret, "SCR_API_BASE": "http://t"}, rig.transport)
    assert code == rrd.EXIT_OK and "1 inserted" in out, out
    target = tmp_path / "401_card_pool_census.sql"
    code, out = _run(["--census", path, "--emit-sql", str(target)], {})
    assert code == rrd.EXIT_OK, out
    sql = target.read_text(encoding="ascii")
    fresh = rig.run(rig.new_schema())
    assert rig.run(rig.script(sql, fresh)) == "COMMIT"
    assert len(rig.registry(fresh)) == 1
    # byte-level: the jsonb text PostgreSQL stores is identical, not only equal as JSON
    assert rig.registry(fresh) == rig.registry()
    before = rig.registry(fresh, stamped=True)
    assert rig.run(rig.script(sql, fresh)) == "COMMIT"
    assert rig.registry(fresh, stamped=True) == before


def test_q5_the_post_check_raises_on_an_absent_row_and_on_another_game_build(rig, tmp_path):
    admin = _steam_id()
    rig.run(rig.add_admin(admin))
    path = _file(tmp_path, cf.VALID["client_file"])
    target = tmp_path / "401_card_pool_census.sql"
    code, out = _run(["--census", path, "--emit-sql", str(target)], {})
    assert code == rrd.EXIT_OK, out
    sql = target.read_text(encoding="ascii")
    block = re.search(r"DO \$\$.*?END \$\$;", sql, re.S).group(0)
    fresh = rig.run(rig.new_schema())
    with pytest.raises(Exception) as raised:
        rig.run(rig.script("BEGIN;\n" + block + "\nCOMMIT;\n", fresh))
    assert "is absent or holds another card count, slot count or game build" in str(raised.value)
    assert rig.registry(fresh) == []
    # the same pool dumped on another game build, registered first through the route: the file's insert
    # is skipped by ON CONFLICT and its post-check must refuse the whole file
    other = cf.client_bytes(cf.dump(game_sha=cf.OTHER_GAME_SHA))
    _b, other_row = rrd.census_plan(_file(tmp_path, other, "other.json"))
    _b, row = rrd.census_plan(path)
    assert other_row["digest"] == row["digest"] and other_row["game_dll_sha256"] != row["game_dll_sha256"]
    status, text = rig.post_raw(admin, other, other_row["digest"])
    assert status == 200 and json.loads(text)["status"] == "registered", text
    before = rig.registry(stamped=True)
    with pytest.raises(Exception) as raised:
        rig.run(rig.script(sql, rig.name))
    assert "is absent or holds another card count, slot count or game build" in str(raised.value)
    assert rig.registry(stamped=True) == before
