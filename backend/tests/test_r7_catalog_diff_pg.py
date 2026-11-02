"""D2, what DDL a migration performs: measured at the database.

Ruling REHEARSAL-FOUR-R6 (1)(a) and (2). The claims test_mail.py used to
read from migration TEXT with a hand-written lexer are measured here, by
execution:

  * mail_inbox_rev's columns, types, nullability, defaults and constraints
    equal the model's (models.MailInboxRev), read from the catalog after
    migration 300 and after the whole chain;
  * no migration except 300 changes mail_inbox_rev, over every file in
    backend/sql (the six files whose EXECUTEs test_mail used to read by
    hand, 086 192 195 198 336 373, included);
  * table_ddl (migration_table_ddl.py), which the a1 live fixtures use to
    copy a table's CREATE statement out of its migration, reproduces the
    relation that migration produced.

How. The test creates its own database through CF_TEST_PG_DSN (an admin DSN
that may CREATE DATABASE; the database named in it is only used to connect)
and drops it afterwards. It installs catalog_diff.PROBE_SQL (two event
triggers that log every DDL command), then applies backend/sql in order, each
numbered file whole with psql (ON_ERROR_STOP, as a migration is applied),
and reads the catalog (catalog_diff.CATALOG_SQL) and pg_dump --schema-only
after each step. The difference after a step is the DDL that step performed,
whatever language, dynamic EXECUTE, format() or function call performed it.

The chain cannot be applied standalone. Migration 020 already reads
players.total_xp, and ranked_series, bets, tournament_matches,
flagged_matches and other tables are created only by the ORM. Data-repair
migrations also refuse on an empty database by design, through their own
gates. So the chain is the faithful build of cf_pg.build(faithful=True), with
whole files in place of its split statements: pass 1 applies every numbered
file in order; then the ORM's create_all and the widen step add what only
the ORM defines; then the files refused in pass 1 are applied again, in
order, up to twice. Every step, the ORM and widen included, is measured and
attributed. The files still refused after pass 3 are UNMEASURED (each with
its SQLSTATE). For them only the command log of what each ran before its
refusal is checked.

Run (fails, never skips, without a server and psql):
    CF_TEST_PG_DSN=postgresql+asyncpg://postgres@127.0.0.1:55432/postgres \
    D2_TEST_PSQL=<psql> D2_TEST_PG_DUMP=<pg_dump> \
    D2_CATALOG_OUT=<dir for the diffs> D2_DB_PREFIX=<scratch db prefix> \
        python -m pytest -q -p no:cacheprovider test_r7_catalog_diff_pg.py
D2_TEST_PSQL / D2_TEST_PG_DUMP name the clients, else PATH is searched.
Without pg_dump the catalog query stands alone. The pg_dump cross-check then
fails unless D2_PG_DUMP_ABSENT_OK=1 records that it is waived.
D2_KEEP_DB=1 keeps the chain database and writes <out>/state.json.
D2_REUSE_DB=<db> with D2_REUSE_STATE=<state.json> runs the tests against
that kept chain without rebuilding it. Mutant runs use this.
"""

import asyncio
import datetime
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import catalog_diff as cd  # noqa: E402
import models  # noqa: E402
from migration_table_ddl import table_ddl  # noqa: E402

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

ADMIN = (os.environ.get("CF_TEST_PG_DSN") or "").replace("postgresql+asyncpg://", "postgresql://")
SQL_DIR = os.path.normpath(os.path.join(HERE, "..", "sql"))
MAIL = "public.mail_inbox_rev"
M300 = "300_mail_inbox_rev.sql"
M373 = "373_bug_reports_auto_number.sql"
# The declared claim: 300 is the only migration that changes mail_inbox_rev.
DECLARED_CHANGERS = [M300]
# The files whose EXECUTEs test_mail.py used to read by hand.
HAND_READ = ["086_bug_report_number.sql", "192_chat_moderation.sql",
             "195_merge_dotless_card_names.sql", "198_merge_dotless_card_names_offers_only.sql",
             "336_bug_reports_kind.sql", M373]
# The (migration, table) pairs the a1 live fixtures read through table_ddl.
A1_PAIRS = [("053_2v2_schema.sql", "team_queue"), ("120_1v2_schema.sql", "ovt_queue"),
            ("154_ffa_schema.sql", "ffa_queue"), ("383_match_hold_stage2.sql", "match_games"),
            ("383_match_hold_stage2.sql", "match_seat_holds")]
KEEP_FILES = {M300} | {m for m, _t in A1_PAIRS}
KEEP_RELS = {MAIL} | {"public." + t for _m, t in A1_PAIRS}

# DECLARED: the relations (or 'kind:ident' for an object on no relation)
# each covered migration's own DDL changes on this build, read from the
# file: 300 creates mail_inbox_rev, its bump function and the trigger on
# mail_recipients, and adds mail_messages.recipient_count.
DECLARED_DDL = {
    M300: ["proc:public.mail_inbox_rev_bump()", MAIL, "public.mail_inbox_rev_pkey",
           "public.mail_messages", "public.mail_recipients"],
    # 086: bug_reports.bug_number (column, default, NOT NULL), its sequence
    # (the format() EXECUTE), OWNED BY, the unique index
    "086_bug_report_number.sql": ["public.bug_reports", "public.bug_reports_number_seq",
                                  "public.idx_bug_reports_number"],
    # 192: chat_mutes (table, sequence, key, index), chat_messages' column,
    # admin_actions' two indexes and the FK its format() EXECUTE drops
    "192_chat_moderation.sql": ["public.admin_actions", "public.chat_messages", "public.chat_mutes",
                                "public.chat_mutes_id_seq", "public.chat_mutes_pkey",
                                "public.ix_admin_actions_created", "public.ix_admin_actions_target",
                                "public.ix_chat_mutes_active"],
    # 195, 198: data only; their one DDL is a temporary map (command log)
    "195_merge_dotless_card_names.sql": [],
    "198_merge_dotless_card_names_offers_only.sql": [],
    # 336: bug_reports.kind (column, comment) and two indexes; its format()
    # EXECUTE builds a temporary probe (command log)
    "336_bug_reports_kind.sql": ["public.bug_reports", "public.idx_bug_reports_kind_created",
                                 "public.idx_bug_reports_steam_kind_created"],
    # 373: bug_reports and the auto-number sequence; its format() EXECUTEs
    # read, and build a temporary probe (command log)
    M373: ["public.bug_reports", "public.bug_reports_auto_number_seq"],
}

# DECLARED: the files the faithful build cannot run to their end, each with
# the SQLSTATE of its refusal in the last pass.
DECLARED_UNMEASURED = {
    # A pass-1 partial application (no BEGIN) left the FK its pass-2 re-run adds.
    "047_tournaments.sql": "42710",
    # data repairs of production rows that do not exist here
    "099_resolve_stuck_2v2_series.sql": "23503",
    "100_rebuild_2v2_glicko.sql": "23503",
    "108_fix_2v2_series_9369b7a5_dc_forfeit.sql": "23503",
    "115_backfill_july12_lost_matches.sql": "23503",
    "168_ffa_recover_wiped_games.sql": "23502",
    # each file's own gate or post-check (RAISE EXCEPTION) on production rows
    "149_release_spooky_head_bouncers.sql": "P0001",
    "172_publish_tattered_cape_rev2.sql": "P0001",
    "175_release_v1355_cosmetics.sql": "P0001",
    "190_release_v1360_cosmetics.sql": "P0001",
    "197_publish_magical_hat_animated.sql": "P0001",
    "211_release_twisted_topper.sql": "P0001",
    "213_seed_machine_translations_uk_sv.sql": "P0001",
    "214_translator_titles.sql": "P0001",
    "217_fix_animated_submission_metadata.sql": "P0001",
    "223_seed_vocab_and_new_shop_strings.sql": "P0001",
    "228_release_poison_set.sql": "P0001",
    "231_grant_notnic_gold.sql": "P0001",
    "239_seed_machine_translations_v1391.sql": "P0001",
    "240_release_spring_nuclear.sql": "P0001",
    "243_seed_machine_translations_forfeit.sql": "P0001",
    "247_release_v1392_cosmetics.sql": "P0001",
    "248_i18n_keys_v1392.sql": "P0001",
    "249_seed_machine_translations_v1392.sql": "P0001",
    "260_release_five_faces.sql": "P0001",
    "264_release_five_faces_v2.sql": "P0001",
    "265_seed_machine_translations_chatmod.sql": "P0001",
    "266_i18n_keys_v1396.sql": "P0001",
    "268_publish_party_crown_rev2.sql": "P0001",
    "281_clavar_activation.sql": "P0001",
    "282_i18n_keys_v1400.sql": "P0001",
    "285_clavar_track_count_14.sql": "P0001",
    "287_release_notes_v1401.sql": "P0001",
    "304_release_straw_hat_florabelle.sql": "P0001",
    "321_pc_rank2_legendary.sql": "P0001",
    "366_title_refunds_voidshot_kingslayer.sql": "P0001",
    "376_i18n_337_demonic_proposals.sql": "P0001",
    "387_ffa_rating_restore_2f60481d.sql": "P0001",
    "388_ffa_rating_restore_2f60481d.sql": "P0001",
    "398_release_five_faces_v1410.sql": "P0001",
    "399_shop_face_descriptions.sql": "P0001",
}


def _require():
    if not ADMIN:
        pytest.fail("CF_TEST_PG_DSN is unset: D2 is measured at a database, so this file needs "
                    "an admin DSN that may CREATE DATABASE")
    if asyncpg is None:
        pytest.fail("asyncpg is not installed")
    if cd.client("D2_TEST_PSQL", "psql") is None:
        pytest.fail("no psql: set D2_TEST_PSQL or put psql on PATH; migrations are applied "
                    "with psql, as they are deployed")


def _dsn(name):
    return ADMIN.rsplit("/", 1)[0] + "/" + name


async def _connect(dsn):
    return await asyncpg.connect(dsn, server_settings={"search_path": "public"})


async def _snap(dsn):
    conn = await _connect(dsn)
    try:
        return await cd.snapshot(conn)
    finally:
        await conn.close()


async def _admin(sql, *args):
    conn = await asyncpg.connect(ADMIN)
    try:
        await conn.execute(sql, *args)
    finally:
        await conn.close()


async def _drop_db(name):
    await _admin("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 "
                 "AND pid <> pg_backend_pid() AND backend_type = 'client backend' "
                 "AND usename = current_user", name)
    await _admin('DROP DATABASE IF EXISTS "%s"' % name)


def _files():
    names = sorted(n for n in os.listdir(SQL_DIR) if n.endswith(".sql"))
    numbered = [n for n in names if re.match(r"^\d{3}_", n)]
    return numbered, [n for n in names if n not in numbered]


def _jsonable(d):
    return {"added": [list(r) for r in d["added"]], "removed": [list(r) for r in d["removed"]]}


def _undiff(d):
    return {"added": [tuple(r) for r in d["added"]], "removed": [tuple(r) for r in d["removed"]]}


async def _orm(dsn):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    engine = create_async_engine(dsn.replace("postgresql://", "postgresql+asyncpg://", 1),
                                 poolclass=NullPool,
                                 connect_args={"server_settings": {"search_path": "public"}})
    try:
        async with engine.begin() as c:
            await c.run_sync(models.Base.metadata.create_all)
    finally:
        await engine.dispose()


async def _widen(dsn):
    """Every column a model maps, added nullable where the build lacks it
    (test_title_ladder_hooks_live._widen, in the public schema)."""
    from sqlalchemy.dialects import postgresql
    dialect = postgresql.dialect()
    conn = await _connect(dsn)
    try:
        for table in models.Base.metadata.sorted_tables:
            have = {r[0] for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = $1", table.name)}
            for col in table.columns:
                if col.name not in have:
                    await conn.execute('ALTER TABLE public."%s" ADD COLUMN "%s" %s'
                                       % (table.name, col.name, col.type.compile(dialect=dialect)))
    finally:
        await conn.close()


def _kept_rows(rows):
    return frozenset(r for r in rows if r[1] in KEEP_RELS)


async def _build(dsn, out, psql, pg_dump):
    """Apply the chain to dsn, measuring every step. Returns (steps, kept,
    unmeasured): steps are dicts with the step's catalog diff, kept maps a
    KEEP_FILES file (and '<end>') to the catalog rows of KEEP_RELS right
    after it, unmeasured maps each file still refused to its SQLSTATE."""
    conn = await _connect(dsn)
    try:
        await conn.execute(cd.PROBE_SQL)
    finally:
        await conn.close()
    numbered, _aux = _files()
    state = {"prev": await _snap(dsn), "dump": cd.dump(pg_dump, dsn) if pg_dump else None}
    if pg_dump:
        _write(out, "dump_base.sql", state["dump"])
    os.makedirs(os.path.join(out, "diffs"), exist_ok=True)
    steps, kept = [], {}
    log = open(os.path.join(out, "steps.jsonl"), "w", encoding="utf-8")

    async def record(label, npass, outcome):
        cur = await _snap(dsn)
        d = cd.diff(state["prev"], cur)
        dd = None
        if pg_dump:
            now = cd.dump(pg_dump, dsn)
            dd = cd.dump_diff(state["dump"], now)
            state["dump"] = now
        step = dict(outcome, n=len(steps), label=label, npass=npass, diff=d, dump=dd)
        steps.append(step)
        state["prev"] = cur
        added, removed, changed = cd.changes(d)
        log.write(json.dumps({
            "n": step["n"], "label": label, "pass": npass, "rc": outcome["rc"],
            "sqlstate": outcome["sqlstate"], "error": outcome["error"],
            "error_line": outcome.get("error_line"),
            "added": len(added), "removed": len(removed), "changed": len(changed),
            "touched": cd.touched(d), "commands": outcome["commands"],
            "dump": dd}) + "\n")
        if not cd.empty(d):
            _write(out, os.path.join("diffs", "%04d_%s.json" % (step["n"], label.strip("<>").replace(" ", "_"))),
                   json.dumps({"label": label, "pass": npass, "added": added, "removed": removed,
                               "changed": changed, "rows": _jsonable(d)}, indent=1))
        return cur

    def run(name):
        outcome = cd.apply_file(psql, dsn, os.path.join(SQL_DIR, name))
        if outcome["rc"] not in (0, 3):
            raise AssertionError("psql could not run %s (rc %d): %s" % (name, outcome["rc"], outcome["error"]))
        return outcome

    try:
        refused = []
        for name in numbered:
            outcome = run(name)
            cur = await record(name, 1, outcome)
            if outcome["rc"]:
                refused.append(name)
            elif name in KEEP_FILES:
                kept[name] = _kept_rows(cur)
            if name == M300:
                _write(out, "snapshot_after_300.json", json.dumps(sorted(cur), indent=0))
                if pg_dump:
                    _write(out, "dump_after_300.sql", state["dump"])
        await _orm(dsn)
        await record("<orm create_all>", 0, {"rc": 0, "sqlstate": None, "error": None, "error_line": None, "commands": []})
        await _widen(dsn)
        await record("<widen>", 0, {"rc": 0, "sqlstate": None, "error": None, "error_line": None, "commands": []})
        last = {}
        for npass in (2, 3):
            again = []
            for name in refused:
                outcome = run(name)
                cur = await record(name, npass, outcome)
                if outcome["rc"]:
                    again.append(name)
                    last[name] = outcome["sqlstate"]
                elif name in KEEP_FILES and name not in kept:
                    kept[name] = _kept_rows(cur)
            refused = again
        kept["<end>"] = _kept_rows(state["prev"])
        _write(out, "snapshot_end.json", json.dumps(sorted(state["prev"]), indent=0))
        if pg_dump:
            _write(out, "dump_end.sql", state["dump"])
    finally:
        log.close()
    return steps, kept, {name: last[name] for name in refused}


def _write(out, rel, text):
    path = os.path.join(out, rel)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


async def _model_rows(dsn):
    """The catalog of the model's own table, created from models.MailInboxRev
    in a scratch schema inside a transaction that is rolled back."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateTable
    ddl = str(CreateTable(models.MailInboxRev.__table__).compile(dialect=postgresql.dialect()))
    conn = await _connect(dsn)
    tr = conn.transaction()
    await tr.start()
    try:
        await conn.execute("CREATE SCHEMA d2_model; SET LOCAL search_path = d2_model, public")
        await conn.execute(ddl)
        await conn.execute("SET LOCAL search_path = public")
        return await cd.snapshot(conn)
    finally:
        await tr.rollback()
        await conn.close()


class Chain:
    pass


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    _require()
    psql = cd.client("D2_TEST_PSQL", "psql")
    pg_dump = cd.client("D2_TEST_PG_DUMP", "pg_dump")
    out = os.environ.get("D2_CATALOG_OUT") or str(tmp_path_factory.mktemp("d2catalog"))
    os.makedirs(out, exist_ok=True)
    c = Chain()
    c.out, c.psql, c.pg_dump = out, psql, pg_dump
    reuse = os.environ.get("D2_REUSE_DB")
    if reuse:
        with open(os.environ["D2_REUSE_STATE"], encoding="utf-8") as fh:
            st = json.load(fh)
        c.db, c.dsn, c.reused = reuse, _dsn(reuse), True
        c.steps = [dict(s, diff=_undiff(s["diff"])) for s in st["steps"]]
        c.kept = {k: frozenset(tuple(r) for r in v) for k, v in st["kept"].items()}
        c.unmeasured = st["unmeasured"]
    else:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
        c.db = ("%s_%s_%d" % (os.environ.get("D2_DB_PREFIX", "d2catalog"), stamp, os.getpid())).lower()
        c.dsn, c.reused = _dsn(c.db), False
        asyncio.run(_admin('CREATE DATABASE "%s"' % c.db))
    _write(out, "run.json", json.dumps({
        "db": c.db, "reused": c.reused, "psql": psql, "pg_dump": pg_dump or "(absent)",
        "admin_dsn_host": ADMIN.split("@")[-1].rsplit("/", 1)[0]}, indent=1))
    try:
        if not c.reused:
            c.steps, c.kept, c.unmeasured = asyncio.run(_build(c.dsn, out, psql, pg_dump))
            if os.environ.get("D2_KEEP_DB") == "1":
                _write(out, "state.json", json.dumps({
                    "steps": [dict(s, diff=_jsonable(s["diff"])) for s in c.steps],
                    "kept": {k: sorted(v) for k, v in c.kept.items()},
                    "unmeasured": c.unmeasured}))
        c.model = asyncio.run(_model_rows(c.dsn))
        yield c
    finally:
        if not c.reused and os.environ.get("D2_KEEP_DB") != "1":
            asyncio.run(_drop_db(c.db))


def _attribution(steps):
    return [(s["label"], s["diff"]) for s in steps]


def _model_shape(c):
    return cd.shape(c.model, "d2_model.mail_inbox_rev")


async def _evaluate(dsn, exprs):
    conn = await _connect(dsn)
    try:
        return {col: await conn.fetchval("SELECT " + e) for col, e in exprs.items()}
    finally:
        await conn.close()


def _default_mismatches(values):
    """Where the evaluated catalog defaults differ from the model's defaults:
    a scalar model default must equal the value, a callable one (now) must
    land within five minutes of it, and a column without a model default
    must have none in the catalog."""
    out = []
    for col in models.MailInboxRev.__table__.columns:
        assert col.server_default is None, col.name
        d = col.default
        if d is None:
            if col.name in values:
                out.append((col.name, "catalog default where the model has none", values[col.name]))
            continue
        if col.name not in values:
            out.append((col.name, "no catalog default", None))
            continue
        want = d.arg(None) if d.is_callable else d.arg
        got = values[col.name]
        if isinstance(want, datetime.datetime):
            ok = (isinstance(got, datetime.datetime) and got.tzinfo is not None
                  and abs((got - want).total_seconds()) < 300)
        else:
            ok = got == want
        if not ok:
            out.append((col.name, want, got))
    return out


def _table_matches_model(c, rows, rel):
    """[] when rel in rows has the model's shape and defaults; otherwise what
    differs."""
    got, want = cd.shape(rows, rel), _model_shape(c)
    problems = []
    if got != want:
        problems.append(("shape", sorted(set(got) - set(want)), sorted(set(want) - set(got))))
    problems += _default_mismatches(asyncio.run(_evaluate(c.dsn, cd.defaults(rows, rel))))
    return problems


# --- the chain ------------------------------------------------------------


def test_the_chain_was_applied_and_every_file_is_measured_or_declared(chain):
    numbered, _aux = _files()
    applied = {s["label"] for s in chain.steps if s["rc"] == 0}
    assert set(numbered) - applied == set(chain.unmeasured), (
        sorted(set(numbered) - applied), chain.unmeasured)
    # each unmeasured file's command log (every pass) names nothing of
    # mail_inbox_rev; where each stopped is recorded (unmeasured.json)
    rows = []
    for name in sorted(chain.unmeasured):
        mine = [s for s in chain.steps if s["label"] == name]
        cmds = [c for s in mine for c in s["commands"]]
        with open(os.path.join(SQL_DIR, name), encoding="utf-8") as fh:
            lines = len(fh.read().splitlines())
        rows.append({"file": name, "lines": lines,
                     "passes": [{"pass": s["npass"], "sqlstate": s["sqlstate"],
                                 "error_line": s.get("error_line"), "error": s["error"]} for s in mine],
                     "commands_before_refusal": len(cmds)})
        assert not [c for c in cmds if "mail_inbox_rev" in c[2]], (name, cmds)
    _write(chain.out, "unmeasured.json", json.dumps(rows, indent=1))
    assert chain.unmeasured == DECLARED_UNMEASURED, chain.unmeasured


def test_only_the_declared_migration_changes_mail_inbox_rev(chain):
    got = cd.changers(_attribution(chain.steps), MAIL)
    assert sorted(set(got)) == DECLARED_CHANGERS, got
    # 300 changes it in one step: the pass-1 application that creates it
    assert got == [M300], got


def test_mail_inbox_rev_equals_the_model_after_300(chain):
    assert chain.kept[M300], "no catalog rows of mail_inbox_rev after 300"
    assert _table_matches_model(chain, chain.kept[M300], MAIL) == []


def test_mail_inbox_rev_equals_the_model_after_the_chain(chain):
    assert _table_matches_model(chain, chain.kept["<end>"], MAIL) == []


def test_the_model_shape_is_read_whole(chain):
    """The comparison's own positive control: the model's table has the
    three columns, the primary key and the foreign key, read from the
    catalog."""
    kinds = {}
    for k, ident, _d in _model_shape(chain):
        kinds.setdefault(k, []).append(ident)
    assert kinds["attribute"] == ["recipient_id", "rev", "updated_at"], kinds
    assert sorted(kinds["constraint"]) == ["mail_inbox_rev_pkey", "mail_inbox_rev_recipient_id_fkey"]
    assert kinds["index"] == ["mail_inbox_rev_pkey"] and kinds["class"] == ["r"]


def test_declared_ddl_of_the_covered_migrations(chain):
    table = {}
    for name in [M300] + HAND_READ:
        mine = [s for s in chain.steps if s["label"] == name]
        assert [s["rc"] for s in mine][-1:] == [0], (name, [(s["npass"], s["sqlstate"]) for s in mine])
        d = {"added": [], "removed": []}
        for s in mine:
            d["added"] += s["diff"]["added"]
            d["removed"] += s["diff"]["removed"]
        table[name] = {"measured": cd.touched(d),
                       "commands": sorted({"%s %s" % (c[0], c[2]) for s in mine for c in s["commands"]}),
                       "changes_mail_inbox_rev": bool(cd.rows_on(d, MAIL))}
    _write(chain.out, "declared_vs_measured.json", json.dumps(
        {n: dict(v, declared=DECLARED_DDL.get(n)) for n, v in table.items()}, indent=1))
    assert {n: v["measured"] for n, v in table.items()} == DECLARED_DDL
    assert [n for n, v in table.items() if v["changes_mail_inbox_rev"]] == DECLARED_CHANGERS


def test_catalog_query_and_pg_dump_agree_on_every_step(chain):
    if not chain.pg_dump:
        assert os.environ.get("D2_PG_DUMP_ABSENT_OK") == "1", (
            "no pg_dump: set D2_TEST_PG_DUMP or put it on PATH, or record the waiver with "
            "D2_PG_DUMP_ABSENT_OK=1")
        _write(chain.out, "pg_dump_absent.txt", "pg_dump absent; the catalog query stands alone\n")
        return
    # pg_dump prints no oid, so a relation dropped and recreated with the
    # same definition changes the catalog (its oid) and not the dump; those
    # steps are listed, and the agreement is judged without the oid
    oid_only = [(s["n"], s["label"]) for s in chain.steps
                if not cd.empty(s["diff"]) and cd.empty(cd.without_oid(s["diff"]))]
    _write(chain.out, "oid_only_steps.json", json.dumps(oid_only, indent=1))
    disagree = [(s["n"], s["label"], cd.touched(s["diff"]), s["dump"]) for s in chain.steps
                if cd.empty(cd.without_oid(s["diff"])) != (not any(s["dump"].values()))]
    assert disagree == [], disagree


async def _in_schema(dsn, schema, sql):
    """sql run in a fresh schema inside a transaction that is rolled back;
    returns the catalog after it."""
    conn = await _connect(dsn)
    tr = conn.transaction()
    await tr.start()
    try:
        await conn.execute("CREATE SCHEMA %s; SET LOCAL search_path = %s, public" % (schema, schema))
        await conn.execute(sql)
        await conn.execute("SET LOCAL search_path = public")
        return await cd.snapshot(conn)
    finally:
        await tr.rollback()
        await conn.close()


@pytest.mark.parametrize("migration,table", A1_PAIRS)
def test_table_ddl_reproduces_the_relation_its_migration_produced(chain, migration, table):
    """table_ddl's statements, run in a scratch schema, produce the relation
    the migration produced (catalog right after it): the measured bound that
    replaces table_ddl's old executable-body refusal."""
    stmts = table_ddl(migration, table)
    rows = asyncio.run(_in_schema(chain.dsn, "d2_a1", ";\n".join(stmts) + ";"))
    want = chain.kept[migration]
    # the scratch schema is not on the reading search_path, so a reference to
    # the copy's own relation (a self-referencing FK, a serial's sequence)
    # prints qualified; the public original prints bare
    strip = re.compile(r"\bd2_a1\.")
    assert [(k, i, strip.sub("", d)) for k, i, d in cd.shape(rows, "d2_a1." + table)] == \
        cd.shape(want, "public." + table)
    assert {k: strip.sub("", v) for k, v in cd.defaults(rows, "d2_a1." + table).items()} == \
        cd.defaults(want, "public." + table)


# --- controls -------------------------------------------------------------
#
# Each control is SQL run in one transaction on the chain database (rolled
# back), measured by the same catalog query. "caught" means the diff has
# rows on mail_inbox_rev; "clean" means it has none (the negative and kept
# cases); "refused" means PostgreSQL refused the program, with the SQLSTATE
# pinned here.

ALTER = "ALTER TABLE mail_inbox_rev ADD COLUMN x int"
GUARD_CONTROLS = [
    # ruling (2): the three named controls (the language one is below)
    ("c1_do_dynamic_execute", "R6 ruling",
     "DO $$ BEGIN EXECUTE '%s'; END $$;" % ALTER, "caught"),
    ("c2_function_creates_index_when_called", "R6 ruling",
     "CREATE FUNCTION d2c_mk() RETURNS void LANGUAGE plpgsql AS $$ BEGIN "
     "CREATE INDEX d2c_idx ON mail_inbox_rev (rev); END $$; SELECT d2c_mk();", "caught"),
    ("k_function_created_not_called", "kept",
     "CREATE FUNCTION d2c_mk() RETURNS void LANGUAGE plpgsql AS $$ BEGIN "
     "CREATE INDEX d2c_idx ON mail_inbox_rev (rev); END $$;", "clean"),
    # round 1, test_mail:2350: a column deleted from the table
    ("r1_2350_drop_rev", "r1 test_mail.py:2350", "ALTER TABLE mail_inbox_rev DROP COLUMN rev;", "caught"),
    ("r1_2350_drop_updated_at", "r1 test_mail.py:2350",
     "ALTER TABLE mail_inbox_rev DROP COLUMN updated_at;", "caught"),
    # round 2, test_mail:2346: quoted names, comments between TABLE and the name
    ("r2_2346_quoted", "r2 test_mail.py:2346", 'ALTER TABLE "mail_inbox_rev" ADD COLUMN x INT;', "caught"),
    ("r2_2346_block_comment", "r2 test_mail.py:2346",
     "ALTER TABLE /* c */ mail_inbox_rev ADD COLUMN x INT;", "caught"),
    ("r2_2346_line_comment", "r2 test_mail.py:2346",
     "ALTER TABLE -- c\n mail_inbox_rev ADD COLUMN x INT;", "caught"),
    ("r2_2346_drop_qualified", "r2 test_mail.py:2346",
     'DROP TABLE IF EXISTS /* ; */ public."mail_inbox_rev";', "caught"),
    ("r2_2346_drop_list", "r2 test_mail.py:2346",
     "CREATE TABLE d2c_other (a int); DROP TABLE d2c_other, mail_inbox_rev;", "caught"),
    ("r2_2346_rename_away", "r2 test_mail.py:2346",
     "ALTER TABLE mail_inbox_rev RENAME TO mail_inbox_rev_old;", "caught"),
    ("r2_2346_rename_into", "r2 test_mail.py:2346",
     "ALTER TABLE mail_inbox_rev RENAME TO d2c_keep; CREATE TABLE d2c_new (recipient_id uuid); "
     "ALTER TABLE d2c_new RENAME TO mail_inbox_rev;", "caught"),
    ("r2_2346_do_quoted", "r2 test_mail.py:2346",
     'DO $$ BEGIN ALTER TABLE "mail_inbox_rev" DROP COLUMN rev; END $$;', "caught"),
    ("r2_2346_do_unicode_tag", "r2 test_mail.py:2346",
     "DO $é$ BEGIN EXECUTE 'ALTER TABLE mail_inbox_rev DROP COLUMN rev'; END $é$;", "caught"),
    # round 3, migration_table_ddl:322 and :326
    ("r3_322_do_standard_string_body", "r3 migration_table_ddl.py:322",
     "DO 'BEGIN %s; END';" % ALTER, "caught"),
    ("r3_326_escaped_name", "r3 migration_table_ddl.py:326",
     "DO $$ BEGIN EXECUTE E'ALTER TABLE mail\\u005finbox_rev ADD COLUMN x int'; END $$;", "caught"),
    ("r3_326_unicode_identifier", "r3 migration_table_ddl.py:326",
     'DO $$ BEGIN ALTER TABLE U&"mail\\005finbox_rev" ADD COLUMN x int; END $$;', "caught"),
    ("r3_326_newline_continuation", "r3 migration_table_ddl.py:326",
     "DO $$ BEGIN EXECUTE 'ALTER TABLE mail_inbox_'\n 'rev ADD x int'; END $$;", "caught"),
    ("r3_326_no_newline", "r3 migration_table_ddl.py:326",
     "DO $$ BEGIN EXECUTE 'ALTER TABLE mail_inbox_' 'rev ADD x int'; END $$;", "refused"),
    # round 4, migration_table_ddl:364: prefixed DO and AS bodies
    ("r4_364_do_E", "r4 migration_table_ddl.py:364", "DO E'BEGIN %s; END';" % ALTER, "caught"),
    ("r4_364_do_U", "r4 migration_table_ddl.py:364", "DO U&'BEGIN %s; END';" % ALTER, "caught"),
    ("r4_364_do_B", "r4 migration_table_ddl.py:364", "DO B'BEGIN %s; END';" % ALTER, "refused"),
    ("r4_364_do_X", "r4 migration_table_ddl.py:364", "DO X'BEGIN %s; END';" % ALTER, "refused"),
    ("r4_364_do_N", "r4 migration_table_ddl.py:364", "DO N'BEGIN %s; END';" % ALTER, "refused"),
    ("r4_364_do_language_e", "r4 migration_table_ddl.py:364",
     "DO LANGUAGE plpgsql e'BEGIN %s; END';" % ALTER, "caught"),
    ("r4_364_function_E_called", "r4 migration_table_ddl.py:364",
     "CREATE FUNCTION d2c_f() RETURNS void LANGUAGE plpgsql AS E'BEGIN %s; END'; SELECT d2c_f();"
     % ALTER, "caught"),
    ("r4_364_procedure_U_called", "r4 migration_table_ddl.py:364",
     "CREATE PROCEDURE d2c_p() LANGUAGE plpgsql AS U&'BEGIN %s; END'; CALL d2c_p();" % ALTER, "caught"),
    ("r4_364_nested_do", "r4 migration_table_ddl.py:364",
     "DO $$ BEGIN EXECUTE 'DO E''BEGIN ALTER TABLE mail_inbox_rev ADD x int; END'''; END $$;", "caught"),
    # round 4, migration_table_ddl:430: EXECUTE composition
    ("r4_430_concat", "r4 migration_table_ddl.py:430",
     "DO $$ BEGIN EXECUTE 'ALTER TABLE mail_inbox_' || 'rev ADD COLUMN x int'; END $$;", "caught"),
    ("r4_430_concat_dollar", "r4 migration_table_ddl.py:430",
     "DO $$ BEGIN EXECUTE 'ALTER TABLE mail_' || 'inbox_' || $q$rev ADD COLUMN x int$q$; END $$;",
     "caught"),
    ("r4_430_format", "r4 migration_table_ddl.py:430",
     "DO $$ BEGIN EXECUTE format('ALTER TABLE %I ADD x int', 'mail_inbox_rev'); END $$;", "caught"),
    ("r4_430_variable", "r4 migration_table_ddl.py:430",
     "DO $$ DECLARE s text := 'ALTER TABLE mail_inbox_rev ADD x int'; BEGIN EXECUTE s; END $$;",
     "caught"),
    ("r4_430_parenthesised", "r4 migration_table_ddl.py:430",
     "DO $$ BEGIN EXECUTE ('ALTER TABLE mail_inbox_' || 'rev ADD x int'); END $$;", "caught"),
    ("r4_430_cast", "r4 migration_table_ddl.py:430",
     "DO $$ BEGIN EXECUTE 'ALTER TABLE mail_inbox_' || 'rev ADD x int'::text; END $$;", "caught"),
    ("r4_430_set_config_template", "r4 migration_table_ddl.py:430",
     "SELECT set_config('d2c.sql', 'ALTER TABLE mail_inbox_rev ADD x int', true); "
     "DO $$ BEGIN EXECUTE current_setting('d2c.sql'); END $$;", "caught"),
    # round 5, migration_table_ddl:399 and :422
    ("r5_399_dollar_language", "r5 migration_table_ddl.py:399",
     "DO LANGUAGE $lang$plpgsql$lang$ $body$ BEGIN %s; END $body$;" % ALTER, "caught"),
    ("r5_399_dollar_language_bare", "r5 migration_table_ddl.py:399",
     "DO LANGUAGE $$plpgsql$$ $body$ BEGIN %s; END $body$;" % ALTER, "caught"),
    ("r5_422_function_collate", "r5 migration_table_ddl.py:422",
     "DO $$ DECLARE function text := 'ALTER TABLE mail_inbox_rev ADD x int'; "
     "BEGIN EXECUTE function COLLATE \"C\"; END $$;", "caught"),
    ("r5_422_procedure_collate", "r5 migration_table_ddl.py:422",
     "DO $$ DECLARE procedure text := 'ALTER TABLE mail_inbox_rev ADD x int'; "
     "BEGIN EXECUTE procedure COLLATE \"C\"; END $$;", "caught"),
    ("r5_422_function_into", "r5 migration_table_ddl.py:422",
     "DO $$ DECLARE function text := 'ALTER TABLE mail_inbox_rev ADD x int'; r int; "
     "BEGIN EXECUTE function INTO r; END $$;", "refused"),
    ("r5_422_function_using", "r5 migration_table_ddl.py:422",
     "DO $$ DECLARE function text := 'ALTER TABLE mail_inbox_rev ADD x int'; "
     "BEGIN EXECUTE function USING 1; END $$;", "caught"),
    ("r5_do_language_string_E", "r5 migration_table_ddl.py:399",
     "DO LANGUAGE 'plpgsql' E'BEGIN %s; END';" % ALTER, "caught"),
    ("r5_do_language_quoted_ident", "r5 migration_table_ddl.py:399",
     'DO LANGUAGE "plpgsql" $b$ BEGIN %s; END $b$;' % ALTER, "caught"),
    ("r5_do_language_after_dollar", "r5 migration_table_ddl.py:399",
     "DO $b$ BEGIN %s; END $b$ LANGUAGE $l$plpgsql$l$;" % ALTER, "caught"),
    ("r5_do_two_bodies", "r5 migration_table_ddl.py:399",
     "DO $b$ BEGIN END $b$ $c$ BEGIN %s; END $c$;" % ALTER, "refused"),
    # one control per catalog rule the guard reads
    ("rule_check_constraint", "rule pg_constraint",
     "ALTER TABLE mail_inbox_rev ADD CONSTRAINT d2c_chk CHECK (rev >= 0);", "caught"),
    ("rule_trigger", "rule pg_trigger",
     "CREATE FUNCTION d2c_t() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$; "
     "CREATE TRIGGER d2c_trg BEFORE UPDATE ON mail_inbox_rev FOR EACH ROW EXECUTE FUNCTION d2c_t();",
     "caught"),
    ("rule_policy", "rule pg_policy", "CREATE POLICY d2c_pol ON mail_inbox_rev USING (true);", "caught"),
    ("rule_class_rls", "rule pg_class", "ALTER TABLE mail_inbox_rev ENABLE ROW LEVEL SECURITY;", "caught"),
    ("rule_default", "rule pg_attrdef", "ALTER TABLE mail_inbox_rev ALTER COLUMN rev SET DEFAULT 1;",
     "caught"),
    ("rule_nullability", "rule pg_attribute.attnotnull",
     "ALTER TABLE mail_inbox_rev ALTER COLUMN updated_at DROP NOT NULL;", "caught"),
    ("rule_type", "rule pg_attribute type", "ALTER TABLE mail_inbox_rev ALTER COLUMN rev TYPE integer;",
     "caught"),
    ("rule_recreated_same_shape", "rule pg_class oid",
     "DROP TABLE mail_inbox_rev; CREATE TABLE mail_inbox_rev (recipient_id UUID PRIMARY KEY "
     "REFERENCES players(id) ON DELETE CASCADE, rev BIGINT NOT NULL DEFAULT 0, "
     "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());", "caught"),
    ("rule_comment", "rule pg_description", "COMMENT ON COLUMN mail_inbox_rev.rev IS 'd2c';", "caught"),
    ("rule_rewrite", "rule pg_rewrite",
     "CREATE RULE d2c_rule AS ON DELETE TO mail_inbox_rev DO INSTEAD NOTHING;", "caught"),
    ("rule_dropped_column", "rule pg_attribute dropped",
     "ALTER TABLE mail_inbox_rev ADD COLUMN d2c int; ALTER TABLE mail_inbox_rev DROP COLUMN d2c;",
     "caught"),
    ("rule_index", "rule pg_index", "CREATE INDEX d2c_idx2 ON mail_inbox_rev (updated_at);", "caught"),
    ("rule_statistics", "rule pg_statistic_ext",
     "CREATE STATISTICS d2c_st ON rev, updated_at FROM mail_inbox_rev;", "caught"),
    # negative controls: no DDL on mail_inbox_rev
    ("k_select", "kept", "SELECT count(*) FROM mail_inbox_rev;", "clean"),
    ("k_dml", "kept", "UPDATE mail_inbox_rev SET rev = rev + 1;", "clean"),
    ("k_other_table_column_named_like_it", "kept",
     "ALTER TABLE mail_messages ADD COLUMN d2c_mail_inbox_rev int;", "clean"),
    ("k_string_spelling_it", "kept", "SELECT 'ALTER TABLE mail_inbox_rev DROP COLUMN rev';", "clean"),
    ("k_temp_table_of_the_same_name", "kept", "CREATE TEMP TABLE mail_inbox_rev (a int);", "clean"),
]

# PostgreSQL's SQLSTATE for each program it refuses (recorded by the first run).
REFUSED_SQLSTATE = {
    "r3_326_no_newline": "42601",       # two literals with no newline between them
    "r4_364_do_B": "42601",             # a bit-string constant is not a DO body
    "r4_364_do_X": "42601",
    "r4_364_do_N": "42601",             # N'' is not a DO body either
    "r5_422_function_into": "42601",    # INTO used with a command that cannot return data
    "r5_do_two_bodies": "42601",        # conflicting or redundant options
}


async def _measure(dsn, program, schema=None):
    """program run in one transaction (rolled back), catalog before and after."""
    conn = await _connect(dsn)
    logs = []
    conn.add_log_listener(lambda _c, msg: logs.append(msg.message))
    tr = conn.transaction()
    await tr.start()
    try:
        if schema:
            await conn.execute("CREATE SCHEMA %s" % schema)
        before = await cd.snapshot(conn)
        if schema:
            await conn.execute("SET LOCAL search_path = %s, public" % schema)
        try:
            await conn.execute(program)
        except asyncpg.PostgresError as exc:
            return {"refused": exc.sqlstate, "error": str(exc).splitlines()[0][:200],
                    "commands": cd.commands("\n".join(logs))}
        await conn.execute("SET LOCAL search_path = public")
        after = await cd.snapshot(conn)
        return {"refused": None, "diff": cd.diff(before, after), "after": after,
                "commands": cd.commands("\n".join(logs))}
    finally:
        await tr.rollback()
        await conn.close()


def _record_control(chain, name, finding, result, outcome):
    with open(os.path.join(chain.out, "controls.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"control": name, "finding": finding, "outcome": outcome,
                             "sqlstate": result.get("refused"), "error": result.get("error"),
                             "rows_on_mail_inbox_rev": [list(r) for r in
                                                        cd.rows_on(result["diff"], MAIL)]
                             if result.get("diff") else [],
                             "commands": result.get("commands")}) + "\n")


def _guard_outcome(result):
    if result["refused"]:
        return "refused"
    return "caught" if cd.changers([("control", result["diff"])], MAIL) else "clean"


@pytest.mark.parametrize("name,finding,program,expect", GUARD_CONTROLS,
                         ids=[c[0] for c in GUARD_CONTROLS])
def test_guard_control(chain, name, finding, program, expect):
    result = asyncio.run(_measure(chain.dsn, program))
    outcome = _guard_outcome(result)
    _record_control(chain, name, finding, result, outcome)
    assert outcome == expect, (name, outcome, result.get("refused"), result.get("error"))
    if expect == "refused":
        assert result["refused"] == REFUSED_SQLSTATE.get(name), (name, result["refused"], result["error"])


# ruling (2): a DO in another language, if the cluster can install one.
LANGUAGE_CONTROLS = [
    ("r6_636_plpython_getattr", "r6 migration_table_ddl.py:636", "plpython3u",
     "DO $$ getattr(plpy, 'execute')('ALTER TABLE mail_inbox_rev ADD x int') $$ LANGUAGE plpython3u;"),
    ("c3_plperl_spi", "R6 ruling", "plperl",
     "DO $$ spi_exec_query('ALTER TABLE mail_inbox_rev ADD x int'); $$ LANGUAGE plperl;"),
    ("c3_pltcl_spi", "R6 ruling", "pltcl",
     "DO $$ spi_exec \"ALTER TABLE mail_inbox_rev ADD x int\" $$ LANGUAGE pltcl;"),
]


async def _language(dsn, extension, program):
    conn = await _connect(dsn)
    tr = conn.transaction()
    await tr.start()
    try:
        before = await cd.snapshot(conn)
        res = {"extension": None, "refused": None}
        try:
            async with conn.transaction():
                await conn.execute("CREATE EXTENSION IF NOT EXISTS %s" % extension)
        except asyncpg.PostgresError as exc:
            res["extension"] = exc.sqlstate
            res["error"] = str(exc).splitlines()[0][:200]
        try:
            async with conn.transaction():
                await conn.execute(program)
        except asyncpg.PostgresError as exc:
            res["refused"] = exc.sqlstate
            res["error"] = (res.get("error") or "") + " | " + str(exc).splitlines()[0][:200]
        res["diff"] = cd.diff(before, await cd.snapshot(conn))
        return res
    finally:
        await tr.rollback()
        await conn.close()


@pytest.mark.parametrize("name,finding,extension,program", LANGUAGE_CONTROLS,
                         ids=[c[0] for c in LANGUAGE_CONTROLS])
def test_language_control(chain, name, finding, extension, program):
    """Either the language installs and its DO's ALTER is caught by its
    effect, or PostgreSQL refuses to create the language (SQLSTATE recorded)
    and then refuses the DO (42704, the language does not exist). There is
    no third outcome. No language is lexed: the walker's language lexing is
    deleted."""
    res = asyncio.run(_language(chain.dsn, extension, program))
    if res["extension"] is None:
        outcome = "caught" if cd.rows_on(res["diff"], MAIL) else "clean"
        _record_control(chain, name, finding, res, outcome)
        assert res["refused"] is None and outcome == "caught", res
    else:
        _record_control(chain, name, finding, dict(res, refused="%s/%s" % (res["extension"], res["refused"])),
                        "refused")
        assert res["refused"] == "42704" and not cd.rows_on(res["diff"], MAIL), res


def _read(name):
    with open(os.path.join(SQL_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def _edited(src, edit):
    """src with its one BEGIN; and COMMIT; line removed (the control runs in
    its own transaction) and edit (old, new) applied exactly once."""
    for line in ("BEGIN;\n", "COMMIT;\n"):
        assert src.count("\n" + line) == 1, line
        src = src.replace("\n" + line, "\n", 1)
    if edit is not None:
        old, new = edit
        assert src.count(old) == 1, old
        src = src.replace(old, new, 1)
    return src


MODEL_CONTROLS = [
    # (name, finding, edit of 300, the comparison rules that must catch it, or
    # "refused:<SQLSTATE>" when PostgreSQL refuses the edited file: 300's own
    # backfill INSERT names rev, so 300 without rev cannot run)
    ("k_300_unchanged", "kept", None, None),
    ("r1_2350_rev_deleted", "r1 test_mail.py:2350",
     ("    rev          BIGINT      NOT NULL DEFAULT 0,\n", ""), "refused:42703"),
    ("r1_2350_updated_at_deleted", "r1 test_mail.py:2350",
     (",\n    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()\n", "\n"), "default,shape"),
    ("r4_2448_nullability", "r4 test_mail.py:2448",
     ("NOT NULL DEFAULT 0", "DEFAULT CASE WHEN NULL IS NOT NULL THEN 1 ELSE 0 END"), "shape"),
    ("r5_2572_exclude_first", "r5 test_mail.py:2572",
     ("CREATE TABLE IF NOT EXISTS mail_inbox_rev (\n",
      "CREATE TABLE IF NOT EXISTS mail_inbox_rev (\n    exclude INTEGER,\n"), "shape"),
    ("r5_2572_exclude_last", "r5 test_mail.py:2572",
     ("TIMESTAMPTZ NOT NULL DEFAULT NOW()\n);",
      "TIMESTAMPTZ NOT NULL DEFAULT NOW(),\n    exclude INTEGER NOT NULL DEFAULT 0\n);"), "shape"),
    ("rule_type_rev_integer", "rule attribute type",
     ("rev          BIGINT      NOT NULL", "rev          INTEGER     NOT NULL"), "shape"),
    ("rule_default_value", "rule default value",
     ("NOT NULL DEFAULT 0,", "NOT NULL DEFAULT 1,"), "default"),
    ("rule_foreign_key_action", "rule constraint",
     ("REFERENCES players(id) ON DELETE CASCADE", "REFERENCES players(id)"), "shape"),
]


@pytest.mark.parametrize("name,finding,edit,rule", MODEL_CONTROLS, ids=[c[0] for c in MODEL_CONTROLS])
def test_model_control(chain, name, finding, edit, rule):
    """300's own text, edited, applied in a scratch schema: the comparison
    with the model catches the edit, by the named rule; unedited, it does
    not."""
    result = asyncio.run(_measure(chain.dsn, _edited(_read(M300), edit), schema="d2_ctl"))
    if result["refused"]:
        _record_control(chain, name, finding, result, "refused")
        assert rule == "refused:" + result["refused"], (name, result)
        return
    problems = _table_matches_model(chain, result["after"], "d2_ctl.mail_inbox_rev")
    kinds = sorted({"shape" if p[0] == "shape" else "default" for p in problems})
    _record_control(chain, name, finding, dict(result, diff=None, refused=None),
                    "caught by %s" % kinds if problems else "equal to the model")
    if rule is None:
        assert problems == [], problems
    else:
        assert ",".join(kinds) == rule, (name, problems)


ATTRIBUTION_CONTROLS = [
    ("k_373_rerun", "kept", None, "clean"),
    ("r5_2617_template", "r5 test_mail.py:2617",
     ("c_accounted_sql CONSTANT text := 'SELECT ",
      "c_accounted_sql CONSTANT text := 'ALTER TABLE mail_inbox_rev DROP COLUMN rev; SELECT "), "caught"),
    ("r5_2617_binding", "r5 test_mail.py:2617",
     ("PERFORM set_config('m373.accounted_sql', c_accounted_sql, true);",
      "PERFORM set_config('m373.accounted_sql', 'ALTER TABLE mail_inbox_rev DROP COLUMN rev', true);"),
     "refused:42601"),
]


@pytest.mark.parametrize("name,finding,edit,expect", ATTRIBUTION_CONTROLS,
                         ids=[c[0] for c in ATTRIBUTION_CONTROLS])
def test_attribution_control(chain, name, finding, edit, expect):
    """Migration 373, edited as round 5 edited it, re-run on the chain: the
    per-migration attribution names it beside 300, so the declared list no
    longer holds; unedited, 373 changes nothing of mail_inbox_rev."""
    result = asyncio.run(_measure(chain.dsn, _edited(_read(M373), edit)))
    if result["refused"]:
        # the ALTER ran (command log) and the migration then failed: nothing
        # of it survives the rollback, as a failed migration leaves nothing
        _record_control(chain, name, finding, result, "refused")
        assert expect == "refused:" + result["refused"], (name, result)
        assert [c for c in result["commands"] if c[2] == MAIL], result["commands"]
        return
    steps = _attribution(chain.steps + [{"label": M373 + " (" + name + ")", "diff": result["diff"]}])
    got = cd.changers(steps, MAIL)
    outcome = "clean" if got == DECLARED_CHANGERS else "caught"
    _record_control(chain, name, finding, result, outcome)
    assert outcome == expect, (name, got)


# --- the files outside the chain --------------------------------------------


def test_zz_rollback_and_resume_files_do_not_change_mail_inbox_rev(chain):
    """Every other file in backend/sql (rollback_*, resume_*), applied in
    order with psql to a copy of the chain database: none changes
    mail_inbox_rev. Their own refusals are recorded."""
    _numbered, aux = _files()
    assert aux, "no rollback or resume files found"
    copy = (chain.db + "_aux")[:63]
    asyncio.run(_admin('CREATE DATABASE "%s" TEMPLATE "%s"' % (copy, chain.db)))
    dsn = _dsn(copy)
    try:
        prev, steps, rows = asyncio.run(_snap(dsn)), [], []
        for name in aux:
            outcome = cd.apply_file(chain.psql, dsn, os.path.join(SQL_DIR, name))
            assert outcome["rc"] in (0, 3), (name, outcome)
            cur = asyncio.run(_snap(dsn))
            d = cd.diff(prev, cur)
            prev = cur
            steps.append((name, d))
            rows.append({"file": name, "rc": outcome["rc"], "sqlstate": outcome["sqlstate"],
                         "error": outcome["error"], "touched": cd.touched(d),
                         "commands": outcome["commands"]})
        _write(chain.out, "aux_files.json", json.dumps(rows, indent=1))
        assert cd.changers(steps, MAIL) == []
        assert not [(r["file"], c) for r in rows for c in r["commands"] if "mail_inbox_rev" in c[2]]
    finally:
        asyncio.run(_drop_db(copy))
