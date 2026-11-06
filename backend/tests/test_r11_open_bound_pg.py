"""The DSN census's runtime BOUND (ruling FOUR-R10-A2 (3) FIX-R11-OPEN,
findings F5 and F6). The census grammar (ro_census, test_r7) stays the
FILTER; this is the GUARANTEE.

The measured run is test_r8's execution of the covered production code,
composed from test_r8's own pieces, with every harness connection that is
not the frozen identity opened BEFORE the freeze:

  before the freeze  a clone of scr_seat_ro_tmpl, test_r8's seed rows (as
                     admin), the role's grants, the harness's one admin
                     connection on the clone (it grants and revokes the
                     grant runs' privileges; no other admin open follows);
  the freeze         ro_census.OpenRecorder installed on the asyncpg module
                     attribute `connect`, and the frozen DSN taken: the role
                     DSN of the clone (scr_seat_ro);
  the measured run   (1) production's own engines: api/database.py executed
                     afresh with DATABASE_URL set to the frozen DSN, so every
                     engine it builds comes from its own code (a rebinding of
                     DATABASE_URL anywhere in that module changes what they
                     open), each engine opened once, and every engine and
                     session factory of the live `database` module replaced
                     by the fresh module's, so a production route that opens
                     its own session in the run opens through them;
                     (2) the role run: every test_r8 driver on a role
                     session (ro_covered.role_engine);
                     (3) the grant runs: test_r8's grant plan, each driver on
                     a READ WRITE role session with its grants;
  the thaw           the recorder removed.

The bound: every open recorded during the run resolves to the frozen
identity (asyncpg's own resolution of its arguments: addresses, user,
password, database, TLS mode, target session attributes, connection and
record classes) with server settings the run allows (none, or the role
engine's search_path), and the asyncpg connections constructed during the
run are exactly the recorded opens' connections, by identity and in number,
so no open happened outside the recorder. A positive signal is required: the
run opens at least once per driver, per grant run and per production engine.

The controls (test_r11_bound_controls) prove each refusal route on the real
cluster: an open of another identity through asyncpg.__dict__, an open with
server settings the run does not allow, an open through
asyncpg.connection.connect, a pool, and an alias captured before the freeze;
and the frozen open itself, clean.

Runs under CF_TEST_PG_DSN naming an admin DSN, as test_r8. Never skips.
"""

import asyncio
import collections
import datetime
import importlib.util
import os
import sys

import asyncpg
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(HERE, "..", "api")
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import cf_asm  # noqa: E402
import cf_pg  # noqa: E402
import database  # noqa: E402
import ro_census  # noqa: E402
import ro_covered  # noqa: E402
import ro_role  # noqa: E402
import test_r8_ro_covered_pg as t8  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

ADMIN_DSN = ro_role.pg_dsn(os.environ.get("CF_TEST_PG_DSN") or "")


def run(coro):
    return asyncio.run(coro)


def _require_cluster():
    if not ADMIN_DSN:
        pytest.fail("CF_TEST_PG_DSN is unset: name an admin DSN (a superuser, or a "
                    "LOGIN CREATEDB role) on the local cluster; this module never skips")
    missing = run(ro_role.read_cluster(ADMIN_DSN))
    if missing:
        pytest.fail("the cluster is not provisioned for the read-only bound: "
                    + "; ".join(missing))


def _clone_name(tag):
    # ro_role.clone admits only rf8_ro_* names (its DB_RE)
    return "rf8_ro_r11%s_%s_%s" % (tag, datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%d%H%M%S"), os.urandom(2).hex())


def _production_engines(mp, frozen_dsn):
    """api/database.py executed afresh with DATABASE_URL = the frozen DSN
    (asyncpg dialect form); every engine its own code builds is collected at
    construction (SQLAlchemy's create_async_engine, as the module imports
    it), and the live `database` module's engines, session factories and
    DATABASE_URL are replaced by the fresh module's."""
    import sqlalchemy.ext.asyncio as sa_asyncio
    built = []
    real = sa_asyncio.create_async_engine

    def collect(*a, **k):
        engine = real(*a, **k)
        built.append(engine)
        return engine

    mp.setenv("DATABASE_URL", frozen_dsn.replace("postgresql://", "postgresql+asyncpg://"))
    mp.setattr(sa_asyncio, "create_async_engine", collect)
    try:
        spec = importlib.util.spec_from_file_location(
            "_r11_database_measured", os.path.join(API, "database.py"))
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
    finally:
        mp.setattr(sa_asyncio, "create_async_engine", real)
    swapped = []
    for name, value in vars(fresh).items():
        if name == "DATABASE_URL" or any(value is e for e in built) or (
                isinstance(value, async_sessionmaker)
                and any(value.kw.get("bind") is e for e in built)):
            mp.setattr(database, name, value, raising=False)
            swapped.append(name)
    return fresh, built, swapped


def _grant_plan():
    plan = collections.OrderedDict()
    for e in t8.UNREACHED:
        grants = ro_covered.REFUSER_GRANTS[ro_covered.role_outcome(e)[1]]
        for name in t8.DRIVERS:
            if name.split()[0].split(".")[-1] == e[4]:
                g, es = plan.setdefault(name, (set(), []))
                g.update(grants)
                es.append(e)
    return plan


async def _measured(admin_dsn, clone, mp, rec):
    out = {"errors": {}, "engine_errors": {}, "engines": 0, "engine_opens": 0, "swapped": [],
           "checked": [], "drivers": 0, "grant_runs": 0}
    clone_dsn = ro_role.dsn_for(admin_dsn, clone)
    async with cf_pg.case("rf11op", dsn=clone_dsn) as (c, sm):
        env = cf_asm.Env(c, sm, mp)
        try:
            s = await t8.seed(env)
            await ro_role.grant(admin_dsn, clone)
            t8._prepare(mp)
            role_dsn = ro_role.dsn_for(admin_dsn, clone, user=ro_role.ROLE)
            plan = _grant_plan()
            admin = await asyncpg.connect(clone_dsn)   # the harness's, before the freeze
            try:
                rec.freeze(role_dsn, [None, {"search_path": '"%s"' % c.schema}])
                try:
                    # (1) production's own engines, from the frozen DSN
                    _fresh, built, out["swapped"] = _production_engines(mp, role_dsn)
                    out["engines"] = len(built)
                    try:
                        for i, engine in enumerate(built):
                            try:
                                async with engine.connect() as conn:
                                    await conn.exec_driver_sql("SELECT 1")
                                out["engine_opens"] += 1
                            except Exception as e:   # noqa: BLE001 -- the bound reads it
                                out["engine_errors"][i] = "%s: %s" % (
                                    type(e).__name__, str(e).splitlines()[0][:200])
                        # (2) the role run
                        for name, drive in t8.DRIVERS.items():
                            engine = ro_covered.role_engine(role_dsn, c.schema, ro_role.ROLE,
                                                            out["checked"])
                            try:
                                async with ro_covered.role_sessionmaker(engine)() as db:
                                    db.info["lock_targets"] = t8.LOCK_TARGETS
                                    try:
                                        await drive(db, s, mp)
                                    except BaseException as e:   # noqa: BLE001 -- recorded
                                        out["errors"][name] = "%s: %s" % (
                                            type(e).__name__, str(e).splitlines()[0][:200]
                                            if str(e) else "")
                                    finally:
                                        try:
                                            await db.rollback()
                                        except BaseException:   # noqa: BLE001
                                            pass
                            finally:
                                await engine.dispose()
                            out["drivers"] += 1
                        # (3) the grant runs
                        for name, (grants, entries) in plan.items():
                            await t8._grants(admin, c.schema, grants, "GRANT")
                            try:
                                await t8._counted(role_dsn, c.schema, out["checked"],
                                                  t8.DRIVERS[name], s, mp,
                                                  {e[1:4] for e in entries})
                            finally:
                                await t8._grants(admin, c.schema, grants, "REVOKE")
                            out["grant_runs"] += 1
                    finally:
                        # every task the run left behind ends INSIDE the
                        # window, so an open it was making is recorded
                        pending = [t for t in asyncio.all_tasks()
                                   if t is not asyncio.current_task()]
                        out["pending_tasks"] = len(pending)
                        for t in pending:
                            t.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        for engine in built:
                            await engine.dispose()
                finally:
                    rec.thaw()
            finally:
                await admin.close()
        finally:
            env.close()
    return out


@pytest.fixture(scope="module")
def measured():
    _require_cluster()
    clone = _clone_name("op")
    run(ro_role.clone(ADMIN_DSN, clone))
    rec = ro_census.OpenRecorder()
    try:
        with pytest.MonkeyPatch.context() as mp:
            out = run(_measured(ADMIN_DSN, clone, mp, rec))
        yield rec, out
    finally:
        rec.thaw()
        run(ro_role.drop_clone(ADMIN_DSN, clone))


def _report(rec):
    return [(i, e["identity"] if not isinstance(e["identity"], dict) else {
        k: v for k, v in e["identity"].items() if k != "params"}, e["error"])
        for i, e in enumerate(rec.opens)]


def test_r11_open_bound_holds(measured):
    rec, out = measured
    assert rec.violations() == [], (rec.violations(), _report(rec))
    assert not out["engine_errors"], out["engine_errors"]


def test_r11_open_bound_positive_signal(measured):
    """The run did open: every production engine once, at least one open per
    driver and per grant run, every open through the recorder, and the role
    engine's identity check ran."""
    rec, out = measured
    assert out["engines"] >= 1 and out["engine_opens"] == out["engines"], out
    assert {"engine", "async_session", "DATABASE_URL"} <= set(out["swapped"]), out["swapped"]
    assert out["drivers"] == len(t8.DRIVERS) and out["grant_runs"] == len(_grant_plan()), out
    assert len(rec.opens) >= out["engines"] + out["drivers"] + out["grant_runs"], (
        len(rec.opens), out)
    assert len(rec.built) == len([e for e in rec.opens if e["conn"] is not None]) > 0
    assert out["checked"], "no role connection asserted its identity"


# ------------------------------------------------------------ the controls

async def _control(kind, frozen_dsn, other_dsn):
    """One planted open between a freeze and a thaw; the violation kinds."""
    rec = ro_census.OpenRecorder()
    captured = asyncpg.connect          # an alias taken BEFORE the freeze
    rec.freeze(frozen_dsn, [None])
    conns, pool = [], None
    try:
        if kind == "frozen":
            conns.append(await asyncpg.connect(frozen_dsn))
        elif kind == "dict_alias":
            table = getattr(asyncpg, "__dict__")
            dial = table["con" + "nect"]
            conns.append(await dial(other_dsn))
        elif kind == "settings":
            conns.append(await asyncpg.connect(
                frozen_dsn, server_settings={"application_name": "rf11_control"}))
        elif kind == "module_function":
            import asyncpg.connection as apc
            conns.append(await apc.connect(frozen_dsn))
        elif kind == "pool":
            pool = await asyncpg.create_pool(frozen_dsn, min_size=1, max_size=1)
        elif kind == "captured_alias":
            conns.append(await captured(frozen_dsn))
        else:
            raise KeyError(kind)
    finally:
        rec.thaw()
        for conn in conns:
            await conn.close()
        if pool is not None:
            await pool.close()
    return sorted({v[0] for v in rec.violations()}), len(rec.opens), len(rec.built)


CONTROLS = (
    ("frozen", [], 1, 1),
    ("dict_alias", ["open not the frozen DSN"], 1, 1),
    ("settings", ["open with server settings the run does not allow"], 1, 1),
    ("module_function", ["open outside the recorder"], 0, 1),
    ("pool", ["open outside the recorder"], 0, 1),
    ("captured_alias", ["open outside the recorder"], 0, 1),
)


@pytest.fixture(scope="module")
def control_clone():
    """The controls' frozen DSN is the admin on a clone of their own; the
    other identity is the admin DSN as given (its own database), which the
    admin can always open."""
    _require_cluster()
    clone = _clone_name("ctl")
    run(ro_role.clone(ADMIN_DSN, clone))
    try:
        yield ro_role.dsn_for(ADMIN_DSN, clone)
    finally:
        run(ro_role.drop_clone(ADMIN_DSN, clone))


@pytest.mark.parametrize("kind", [c[0] for c in CONTROLS])
def test_r11_bound_controls(kind, control_clone):
    want, opens, built = next(c[1:] for c in CONTROLS if c[0] == kind)
    got = run(_control(kind, control_clone, ADMIN_DSN))
    assert got == (want, opens, built), got
    assert asyncpg.connect is asyncpg.connection.connect, "the thaw did not restore connect"
