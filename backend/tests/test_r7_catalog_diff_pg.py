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

How. Every database this file measures is a CLONE of the template database
D2_TEMPLATE (default scr_seat_d2_tmpl; ruling REHEARSAL-FOUR-R7-A2), made
through CF_TEST_PG_DSN (an admin DSN that may CREATE DATABASE; it need not
be a superuser, the database named in it is only used to connect) and
dropped afterwards. The template carries catalog_diff's probe (two event
triggers that log every DDL command, which only a superuser can create);
the test reads the template from the cluster and fails with a sentence when
it is absent, is not a template, or its clone does not carry exactly
catalog_diff.PROBE_SQL's probe. No test creates a role, an event trigger or
changes a pg_catalog ACL.

The chain is applied ONCE, in order, each numbered file whole with psql
(ON_ERROR_STOP, as a migration is applied), and the catalog
(catalog_diff.CATALOG_SQL) and pg_dump --schema-only are read after each
step. The difference after a step is the DDL that step performed, whatever
language, dynamic EXECUTE, format() or function call performed it.

The chain was never applied to an empty database in one go: some files read
tables and columns only the ORM defines, and the data repairs, releases and
seeds check production rows through their own gates and post-checks. Ruling
R7-A1 (M11): the harness supplies those prerequisites (d2_seed.PREREQS),
under the admin role, right before the file that needs them, each as its own
measured step labelled "<prereq FILE>", so that EVERY numbered file runs to
its end (rc 0, every statement). There are no declared failures. After the
last file the ORM's create_all and the widen step run, also measured.

Ruling REHEARSAL-R8-A1 (E1): the snapshot also reads every pg_catalog
relation of kind 'r', taken at run time (catalog_all), whole except what
catalog_all declares one by one. Every changed raw row of every step must be
accounted for by an object change of that step (match(), so the per-step
agreement test refuses the rest), no step may change a cluster row (a role,
its defaults, the database), the probe is read again after the chain, and
the steps whose command log names mail_inbox_rev are attributed beside the
catalog rows. The E1 controls carry the report's two examples in a
migration.

Run (fails, never skips, without a server, the template and psql):
    CF_TEST_PG_DSN=postgresql+asyncpg://<admin>@127.0.0.1:55432/postgres \
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

import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import catalog_all as ca  # noqa: E402
import catalog_diff as cd  # noqa: E402
import catalog_position  # noqa: E402
import d2_seed  # noqa: E402
import models  # noqa: E402
from migration_table_ddl import table_ddl  # noqa: E402

try:
    import asyncpg
except ImportError:                                    # pragma: no cover
    asyncpg = None

ADMIN = (os.environ.get("CF_TEST_PG_DSN") or "").replace("postgresql+asyncpg://", "postgresql://")
SQL_DIR = os.path.normpath(os.path.join(HERE, "..", "sql"))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
# Every migration is applied from the OBJECT STORE (ruling R8-CRLF): the
# blob of backend/sql/<file> at one revision frozen for the session (the
# checkout's HEAD, or D2_SQL_REV), written byte for byte to the run's out
# directory, never the working copy (an autocrlf checkout carries CR in every
# dollar-quoted body, and the files that hash their own text, e.g. 287's
# release notes, then refuse at their post-checks) and never a CR strip.
CRLF_FILE = "287_release_notes_v1401.sql"
_REV = {}
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

# The template every measured database is cloned from (ruling R7-A2).
TEMPLATE = os.environ.get("D2_TEMPLATE", "scr_seat_d2_tmpl")

# The M11 control's file: a file the round-7 build declared unmeasured (it
# stopped at its own post-check, P0001 at line 153), the last of the chain.
TAIL_FILE = "399_shop_face_descriptions.sql"
TAIL_AFTER = "END $$;\n\nCOMMIT;\n"
TAIL_ALTER = "ALTER TABLE mail_inbox_rev ADD COLUMN d2c_tail int;\n"

# RECORD ONLY: the 41 files round 7 declared unmeasured, each with the
# SQLSTATE of its refusal. Nothing accepts a failure by this list; it names
# the files completion.json marks "declared in round 7".
R7_DECLARED = {
    "047_tournaments.sql": "42710", "099_resolve_stuck_2v2_series.sql": "23503",
    "100_rebuild_2v2_glicko.sql": "23503", "108_fix_2v2_series_9369b7a5_dc_forfeit.sql": "23503",
    "115_backfill_july12_lost_matches.sql": "23503", "168_ffa_recover_wiped_games.sql": "23502",
    "149_release_spooky_head_bouncers.sql": "P0001", "172_publish_tattered_cape_rev2.sql": "P0001",
    "175_release_v1355_cosmetics.sql": "P0001", "190_release_v1360_cosmetics.sql": "P0001",
    "197_publish_magical_hat_animated.sql": "P0001", "211_release_twisted_topper.sql": "P0001",
    "213_seed_machine_translations_uk_sv.sql": "P0001", "214_translator_titles.sql": "P0001",
    "217_fix_animated_submission_metadata.sql": "P0001", "223_seed_vocab_and_new_shop_strings.sql": "P0001",
    "228_release_poison_set.sql": "P0001", "231_grant_notnic_gold.sql": "P0001",
    "239_seed_machine_translations_v1391.sql": "P0001", "240_release_spring_nuclear.sql": "P0001",
    "243_seed_machine_translations_forfeit.sql": "P0001", "247_release_v1392_cosmetics.sql": "P0001",
    "248_i18n_keys_v1392.sql": "P0001", "249_seed_machine_translations_v1392.sql": "P0001",
    "260_release_five_faces.sql": "P0001", "264_release_five_faces_v2.sql": "P0001",
    "265_seed_machine_translations_chatmod.sql": "P0001", "266_i18n_keys_v1396.sql": "P0001",
    "268_publish_party_crown_rev2.sql": "P0001", "281_clavar_activation.sql": "P0001",
    "282_i18n_keys_v1400.sql": "P0001", "285_clavar_track_count_14.sql": "P0001",
    "287_release_notes_v1401.sql": "P0001", "304_release_straw_hat_florabelle.sql": "P0001",
    "321_pc_rank2_legendary.sql": "P0001", "366_title_refunds_voidshot_kingslayer.sql": "P0001",
    "376_i18n_337_demonic_proposals.sql": "P0001", "387_ffa_rating_restore_2f60481d.sql": "P0001",
    "388_ffa_rating_restore_2f60481d.sql": "P0001", "398_release_five_faces_v1410.sql": "P0001",
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
    problem = asyncio.run(_template_problem())
    if problem:
        pytest.fail(problem)


async def _template_problem():
    """None when TEMPLATE exists in the cluster as a template database owned
    by a superuser (only a superuser can have installed its event
    triggers); otherwise the sentence naming what is missing."""
    conn = await asyncpg.connect(ADMIN)
    try:
        row = await conn.fetchrow(
            "SELECT d.datistemplate, r.rolsuper, r.rolname FROM pg_database d "
            "JOIN pg_roles r ON r.oid = d.datdba WHERE d.datname = $1", TEMPLATE)
    finally:
        await conn.close()
    if row is None:
        return ("the template database %s does not exist in this cluster: provision it with "
                "ai-collab/rehearsal-1410/seat-ro-d2/provision.sql (it carries catalog_diff's probe)" % TEMPLATE)
    if not row["datistemplate"]:
        return "the database %s exists but is not marked as a template (datistemplate false)" % TEMPLATE
    if not row["rolsuper"]:
        return "the template database %s is owned by %s, not a superuser" % (TEMPLATE, row["rolname"])
    return None


async def _probe_problems(dsn):
    """[] when the database carries exactly catalog_diff.PROBE_SQL's probe:
    both event triggers, enabled ('O'), on their events, calling their
    d2_probe functions, whose bodies equal PROBE_SQL's byte for byte."""
    conn = await asyncpg.connect(dsn)
    try:
        trig = {r["evtname"]: r for r in await conn.fetch(
            "SELECT e.evtname, e.evtevent, e.evtenabled::text AS evtenabled, n.nspname, p.proname "
            "FROM pg_event_trigger e JOIN pg_proc p ON p.oid = e.evtfoid "
            "JOIN pg_namespace n ON n.oid = p.pronamespace")}
        body = {r["proname"]: r["prosrc"] for r in await conn.fetch(
            "SELECT p.proname, p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = $1", cd.PROBE_SCHEMA)}
    finally:
        await conn.close()
    problems = []
    want_bodies = cd.probe_bodies()
    for name, (event, fn) in sorted(cd.PROBE_TRIGGERS.items()):
        t = trig.get(name)
        if t is None:
            problems.append("event trigger %s is missing from the clone of %s" % (name, TEMPLATE))
            continue
        if (t["evtevent"], t["evtenabled"], t["nspname"], t["proname"]) != (event, "O", cd.PROBE_SCHEMA, fn):
            problems.append("event trigger %s is %s/%s calling %s.%s, not %s/O calling %s.%s" % (
                name, t["evtevent"], t["evtenabled"], t["nspname"], t["proname"], event, cd.PROBE_SCHEMA, fn))
        if body.get(fn) != want_bodies.get(fn):
            problems.append("function %s.%s differs from catalog_diff.PROBE_SQL's body" % (cd.PROBE_SCHEMA, fn))
    return problems


async def _clone(name, template=None):
    """CREATE DATABASE name TEMPLATE template (TEMPLATE by default); CREATEDB
    suffices."""
    await _admin('CREATE DATABASE "%s" TEMPLATE "%s"' % (name, template or TEMPLATE))


def _dsn(name):
    return ADMIN.rsplit("/", 1)[0] + "/" + name


async def _connect(dsn):
    return await asyncpg.connect(dsn, server_settings={"search_path": "public"})


INTERNAL_NOT_ENABLED_SQL = ("SELECT t.tgrelid::pg_catalog.regclass::text AS rel, t.tgname::text AS name, "
                            "t.tgenabled::text AS enabled FROM pg_catalog.pg_trigger t "
                            "WHERE t.tgisinternal AND t.tgenabled <> 'O' ORDER BY 1, 2")


async def _internal_not_enabled(dsn=None, conn=None):
    """[[relation, trigger, tgenabled]] of every internal trigger that is not
    enabled ('O'). catalog_all accounts for an internal trigger row CREATED
    with its relation or constraint by that creation, whatever its enabled
    state; this reading closes that state for the whole database (ruling
    R8-A1, E1: no object, and no pg_dump block, renders it)."""
    own = conn is None
    if own:
        conn = await _connect(dsn)
    try:
        return [[r["rel"], r["name"], r["enabled"]] for r in await conn.fetch(INTERNAL_NOT_ENABLED_SQL)]
    finally:
        if own:
            await conn.close()


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


def _git(*args):
    proc = subprocess.run(["git", "-C", REPO] + list(args), capture_output=True)
    if proc.returncode:
        raise AssertionError("git %s failed: %s" % (" ".join(args), proc.stderr.decode("utf-8", "replace")[-300:]))
    return proc.stdout


def sql_rev():
    """The revision every migration is read from, frozen once per session."""
    if "rev" not in _REV:
        want = os.environ.get("D2_SQL_REV") or "HEAD"
        _REV["rev"] = _git("rev-parse", "--verify", want + "^{commit}").decode().strip()
    return _REV["rev"]


def _blobs():
    """{file name: bytes} of every blob under backend/sql at sql_rev(), read
    once per session from the object store (ls-tree, then one cat-file
    --batch)."""
    if "blobs" not in _REV:
        rows = []
        for line in _git("ls-tree", sql_rev(), "backend/sql/").decode("utf-8").splitlines():
            meta, path = line.split("\t", 1)
            mode, kind, oid = meta.split()
            if kind == "blob":
                rows.append((os.path.basename(path), oid))
        proc = subprocess.run(["git", "-C", REPO, "cat-file", "--batch"],
                              input="".join(oid + "\n" for _n, oid in rows).encode(), capture_output=True)
        if proc.returncode:
            raise AssertionError("git cat-file failed: %s" % proc.stderr.decode("utf-8", "replace")[-300:])
        data, pos, blobs = proc.stdout, 0, {}
        for name, oid in rows:
            end = data.index(b"\n", pos)
            got_oid, kind, size = data[pos:end].decode().split()
            assert got_oid == oid and kind == "blob", (name, data[pos:end])
            blobs[name] = data[end + 1:end + 1 + int(size)]
            pos = end + 1 + int(size) + 1
        _REV["blobs"] = blobs
    return _REV["blobs"]


def _blob(name):
    """The bytes of backend/sql/<name> in the object store at sql_rev()."""
    blobs = _blobs()
    if name not in blobs:
        raise AssertionError("backend/sql/%s is not in the object store at %s" % (name, sql_rev()))
    return blobs[name]


def _blob_file(out, name):
    """Path of the blob of <name>, written byte for byte under out/sql_blobs."""
    path = os.path.join(out, "sql_blobs", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(_blob(name))
    return path


def _crlf_db(pre_db):
    """The database cloned right before CRLF_FILE (the object-store control)."""
    return (pre_db + "_crlf")[:63]


def _files():
    names = sorted(n for n in _blobs() if n.endswith(".sql"))
    numbered = [n for n in names if re.match(r"^\d{3}_", n)]
    return numbered, [n for n in names if n not in numbered]


def _jsonable(d):
    return {"added": [list(r) for r in d["added"]], "removed": [list(r) for r in d["removed"]]}


def _row(r):
    return tuple(tuple(v) if isinstance(v, list) else v for v in r)


def _undiff(d):
    return {"added": [_row(r) for r in d["added"]], "removed": [_row(r) for r in d["removed"]]}


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


async def _prereq(dsn, step):
    """One d2_seed prerequisite step on its own connection; returns the
    step's outcome (rc 0, or rc 3 with the SQLSTATE when PostgreSQL refused
    it) and its command log."""
    conn = await _connect(dsn)
    logs = []
    conn.add_log_listener(lambda _c, msg: logs.append(msg.message))
    try:
        guard = await d2_seed.apply(conn, step, models)
        out = {"rc": 0, "sqlstate": None, "error": None, "error_line": None, "guard": guard}
    except asyncpg.PostgresError as exc:
        out = {"rc": 3, "sqlstate": exc.sqlstate, "error": str(exc).splitlines()[0][:300], "error_line": None}
    except AssertionError as exc:
        # d2_seed's own refusal (the id-move guard, a seed file's md5): a
        # refused step, recorded like PostgreSQL's
        out = {"rc": 3, "sqlstate": "GUARD", "error": str(exc)[:300], "error_line": None}
    finally:
        await conn.close()
    out["commands"] = cd.commands("\n".join(logs))
    return out


async def _build(dsn, out, psql, pg_dump, pre_db):
    """Apply the chain to dsn ONCE, in order, measuring every step: each
    numbered file preceded by its d2_seed prerequisites (each its own step,
    labelled '<prereq FILE>'), then the ORM's create_all and the widen step.
    Right before TAIL_FILE's prerequisites the database is cloned to pre_db
    (the M11 control's starting state). Returns (steps, kept): steps are
    dicts with the step's catalog diff and, with pg_dump, its object match;
    kept maps a KEEP_FILES file (and '<end>') to the catalog rows of
    KEEP_RELS right after it."""
    numbered, _aux = _files()
    state = {"prev": await _snap(dsn), "dump": cd.dump(pg_dump, dsn) if pg_dump else None}
    if pg_dump:
        _write(out, "dump_base.sql", state["dump"])
    os.makedirs(os.path.join(out, "diffs"), exist_ok=True)
    steps, kept = [], {}
    log = open(os.path.join(out, "steps.jsonl"), "w", encoding="utf-8")

    async def record(label, kind, outcome):
        cur = await _snap(dsn)
        d = cd.diff(state["prev"], cur)
        outcome = dict(outcome, internal_not_enabled=await _internal_not_enabled(dsn))
        dd = mt = None
        if pg_dump:
            now = cd.dump(pg_dump, dsn)
            dd = cd.dump_diff(state["dump"], now)
            mt = cd.match(d, state["dump"], now)
            state["dump"] = now
        step = dict(outcome, n=len(steps), label=label, kind=kind, diff=d, dump=dd, match=mt)
        steps.append(step)
        state["prev"] = cur
        added, removed, changed = cd.changes(d)
        log.write(json.dumps({
            "n": step["n"], "label": label, "kind": kind, "rc": outcome["rc"],
            "sqlstate": outcome["sqlstate"], "error": outcome["error"],
            "error_line": outcome.get("error_line"),
            "added": len(added), "removed": len(removed), "changed": len(changed),
            "touched": cd.touched(d), "raw": ca.keys(d), "commands": outcome["commands"],
            "dump": dd, "match": mt}) + "\n")
        if not cd.empty(d):
            _write(out, os.path.join("diffs", "%04d_%s.json" % (
                step["n"], re.sub(r"[^\w.]+", "_", label.strip("<>")))),
                json.dumps({"label": label, "kind": kind, "added": added, "removed": removed,
                            "changed": changed, "rows": _jsonable(d)}, indent=1))
        return cur

    def run(name):
        outcome = cd.apply_file(psql, dsn, _blob_file(out, name))
        if outcome["rc"] not in (0, 3):
            raise AssertionError("psql could not run %s (rc %d): %s" % (name, outcome["rc"], outcome["error"]))
        return outcome

    try:
        for name in numbered:
            if name == TAIL_FILE:
                await _clone(pre_db, dsn.rsplit("/", 1)[1])
            if name == CRLF_FILE:
                await _clone(_crlf_db(pre_db), dsn.rsplit("/", 1)[1])
            for step in d2_seed.steps_for(name):
                await record("<prereq %s>" % name, "prereq", await _prereq(dsn, step))
            outcome = run(name)
            cur = await record(name, "migration", outcome)
            if name in KEEP_FILES:
                kept[name] = _kept_rows(cur)
            if name == M300:
                _write(out, "snapshot_after_300.json", json.dumps(sorted(cur), indent=0))
                if pg_dump:
                    _write(out, "dump_after_300.sql", state["dump"])
        none = {"rc": 0, "sqlstate": None, "error": None, "error_line": None, "commands": []}
        await _orm(dsn)
        await record("<orm create_all>", "orm", none)
        await _widen(dsn)
        await record("<widen>", "orm", none)
        kept["<end>"] = _kept_rows(state["prev"])
        _write(out, "snapshot_end.json", json.dumps(sorted(state["prev"]), indent=0))
        if pg_dump:
            _write(out, "dump_end.sql", state["dump"])
    finally:
        log.close()
    return steps, kept


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


async def _whoami():
    conn = await asyncpg.connect(ADMIN)
    try:
        return dict(await conn.fetchrow(
            "SELECT current_user AS admin_user, r.rolsuper AS superuser, r.rolcreatedb AS createdb, "
            "r.rolcreaterole AS createrole, version() AS server FROM pg_roles r WHERE r.rolname = current_user"))
    finally:
        await conn.close()


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    _require()
    psql = cd.client("D2_TEST_PSQL", "psql")
    pg_dump = cd.client("D2_TEST_PG_DUMP", "pg_dump")
    out = os.environ.get("D2_CATALOG_OUT") or str(tmp_path_factory.mktemp("d2catalog"))
    os.makedirs(out, exist_ok=True)
    c = Chain()
    c.out, c.psql, c.pg_dump = out, psql, pg_dump
    c.who = asyncio.run(_whoami())
    reuse = os.environ.get("D2_REUSE_DB")
    if reuse:
        with open(os.environ["D2_REUSE_STATE"], encoding="utf-8") as fh:
            st = json.load(fh)
        c.db, c.dsn, c.reused = reuse, _dsn(reuse), True
        c.pre_db = st["pre_db"]
        c.steps = [dict(s, diff=_undiff(s["diff"])) for s in st["steps"]]
        c.kept = {k: frozenset(_row(r) for r in v) for k, v in st["kept"].items()}
    else:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
        c.db = ("%s_%s_%d" % (os.environ.get("D2_DB_PREFIX", "d2catalog"), stamp, os.getpid())).lower()
        c.pre_db = (c.db + "_pre")[:63]
        c.dsn, c.reused = _dsn(c.db), False
        asyncio.run(_clone(c.db))
    _write(out, "run.json", json.dumps(dict(c.who, **{
        "db": c.db, "pre_db": c.pre_db, "crlf_db": _crlf_db(c.pre_db), "sql_rev": sql_rev(),
        "template": TEMPLATE, "reused": c.reused, "psql": psql,
        "pg_dump": pg_dump or "(absent)", "admin_dsn_host": ADMIN.split("@")[-1].rsplit("/", 1)[0]}),
        indent=1))
    try:
        c.probe = asyncio.run(_probe_problems(c.dsn))
        if not c.reused:
            c.steps, c.kept = asyncio.run(_build(c.dsn, out, psql, pg_dump, c.pre_db))
            if os.environ.get("D2_KEEP_DB") == "1":
                _write(out, "state.json", json.dumps({
                    "pre_db": c.pre_db,
                    "steps": [dict(s, diff=_jsonable(s["diff"])) for s in c.steps],
                    "kept": {k: sorted(v) for k, v in c.kept.items()}}))
        c.model = asyncio.run(_model_rows(c.dsn))
        # the probe read again after the whole chain: a step that changed it
        # (its functions, its event triggers) is named here, whatever else
        # the step did (catalog_all accounts for the probe's rows by kind only)
        c.probe_end = asyncio.run(_probe_problems(c.dsn))
        yield c
    finally:
        if not c.reused and os.environ.get("D2_KEEP_DB") != "1":
            asyncio.run(_drop_db(c.db))
            asyncio.run(_drop_db(c.pre_db))
            asyncio.run(_drop_db(_crlf_db(c.pre_db)))


def _attribution(steps):
    return [(s["label"], s["diff"]) for s in steps]


def _model_shape(c):
    return cd.shape(c.model, "d2_model.mail_inbox_rev")


async def _evaluate(dsn, exprs):
    """Each catalog default expression evaluated INSIDE one transaction,
    beside that transaction's own clock: {column: (value,
    transaction_timestamp())} (ruling R7-A1, M10). The transaction's first
    statement is a short sleep, so the statement and wall clocks have
    moved past the transaction clock by the time the defaults run: only an
    expression that IS the transaction clock (now(), CURRENT_TIMESTAMP,
    transaction_timestamp()) returns it exactly."""
    conn = await _connect(dsn)
    try:
        async with conn.transaction():
            await conn.execute("SELECT pg_sleep(0.01)")
            out = {}
            for col, e in exprs.items():
                row = await conn.fetchrow("SELECT (%s) AS value, transaction_timestamp() AS clock" % e)
                out[col] = (row["value"], row["clock"])
            return out
    finally:
        await conn.close()


def _default_mismatches(values):
    """Where the evaluated catalog defaults differ from the model's defaults:
    a scalar model default must equal the value; a callable one that
    returns the current time must equal the DATABASE clock of the
    transaction the default ran in, exactly (no tolerance window); a
    column without a model default must have none in the catalog."""
    out = []
    for col in models.MailInboxRev.__table__.columns:
        assert col.server_default is None, col.name
        d = col.default
        if d is None:
            if col.name in values:
                out.append((col.name, "catalog default where the model has none", values[col.name][0]))
            continue
        if col.name not in values:
            out.append((col.name, "no catalog default", None))
            continue
        want = d.arg(None) if d.is_callable else d.arg
        got, clock = values[col.name]
        if d.is_callable and isinstance(want, datetime.datetime):
            ok = isinstance(got, datetime.datetime) and got.tzinfo is not None and got == clock
            want = "transaction clock %s" % clock
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


def test_the_measured_database_is_a_clone_carrying_the_probe(chain):
    """Ruling R7-A2: the chain database is a clone of TEMPLATE and carries
    exactly catalog_diff.PROBE_SQL's probe (triggers enabled 'O', bodies
    byte-equal); the command log below is that probe's."""
    assert chain.probe == [], chain.probe


def _completion(steps):
    """[(file, rc, sqlstate, error_line, error, commands, prereq steps)] per
    numbered file, in chain order."""
    rows, pre = [], []
    for s in steps:
        if s["kind"] == "prereq":
            pre.append((s["rc"], s["sqlstate"], s["error"]))
        elif s["kind"] == "migration":
            rows.append((s["label"], s["rc"], s["sqlstate"], s.get("error_line"), s["error"],
                         len(s["commands"]), pre))
            pre = []
    return rows


def test_every_migration_file_runs_to_its_end(chain):
    """Ruling R7-A1 (M11): every numbered file in backend/sql is applied
    exactly once and exits 0 (every statement executed), its prerequisites
    included; there are no declared failures. The per-file table
    (completion.json) records each file's rc, command log and
    prerequisite steps."""
    numbered, _aux = _files()
    rows = _completion(chain.steps)
    _write(chain.out, "completion.json", json.dumps(
        [{"file": f, "rc": rc, "sqlstate": st, "error_line": ln, "error": er, "commands": nc,
          "prereq_steps": [list(p) for p in pre], "declared_in_round_7": R7_DECLARED.get(f)}
         for f, rc, st, ln, er, nc, pre in rows], indent=1))
    assert [r[0] for r in rows] == numbered, "not every numbered file was applied exactly once, in order"
    incomplete = [(f, rc, st, ln, er) for f, rc, st, ln, er, _nc, _pre in rows if rc != 0 or st is not None]
    assert incomplete == [], incomplete
    refused_prereqs = [(f, p) for f, *_x, pre in rows for p in pre if p[0] != 0]
    assert refused_prereqs == [], refused_prereqs
    # the prerequisites are fixture steps: none of them changes mail_inbox_rev
    pre_steps = [(s["label"], s["diff"]) for s in chain.steps if s["kind"] == "prereq"]
    assert pre_steps, "no prerequisite step ran"
    assert cd.changers(pre_steps, MAIL) == []
    assert not [c for s in chain.steps if s["kind"] == "prereq" for c in s["commands"]
                if "mail_inbox_rev" in c[2]]


def test_only_the_declared_migration_changes_mail_inbox_rev(chain):
    got = cd.changers(_attribution(chain.steps), MAIL)
    assert sorted(set(got)) == DECLARED_CHANGERS, got
    # 300 changes it in one step: its one application, which creates it
    assert got == [M300], got
    # ruling R8-A1 (catalog_diff.py:325): the recorded commands are
    # attributed too. Every step whose command log names mail_inbox_rev
    # (the relation, or one of its columns) is a declared changer.
    named = [s["label"] for s in chain.steps
             if [c for c in s["commands"] if c[2] == MAIL or c[2].startswith(MAIL + ".")]]
    assert named == [M300], named


def test_no_internal_trigger_is_disabled_after_any_step(chain):
    """Ruling R8-A1 (catalog_diff.py:325): after every step of the chain
    every internal trigger (the foreign keys' own triggers) is enabled."""
    got = [(s["n"], s["label"], s.get("internal_not_enabled", "unmeasured")) for s in chain.steps
           if s.get("internal_not_enabled", "unmeasured") != []]
    assert got == [], got


def test_the_probe_is_intact_after_the_chain(chain):
    """catalog_all accounts for a changed row of the probe's functions or
    event triggers by object kind only; the probe itself is read again after
    the last step and must still be exactly PROBE_SQL's."""
    assert chain.probe_end == [], chain.probe_end


def test_no_step_changes_a_cluster_row(chain):
    """Ruling R8-A1 (E1): no step of the chain changes a row of a shared
    catalog within catalog_all.RESTRICT (a role, its defaults, its
    memberships, the database, a shared comment or label, a tablespace, a
    parameter ACL, a replication origin), other than pg_shdepend's rows for
    the measured database's own objects."""
    got = [(s["n"], s["label"], ca.cluster_rows(s["diff"])) for s in chain.steps if ca.cluster_rows(s["diff"])]
    assert got == [], got


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
        assert [s["rc"] for s in mine][-1:] == [0], (name, [(s["kind"], s["sqlstate"]) for s in mine])
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


def _unmatched(step):
    """The objects one side of a step changed and the other did not."""
    m = step["match"]
    return {"catalog_only": m["catalog_only"], "dump_only": m["dump_only"]}


def test_catalog_query_and_pg_dump_agree_on_every_step(chain):
    """Ruling R7-A1 (M9): on every step of the chain the catalog diff and the
    pg_dump diff change the SAME object set; an object either side changed
    and the other did not fails the test. pg_dump prints no oid, so rows
    differing only in oid (a relation dropped and recreated with the same
    definition) are listed apart (oid_only_steps.json) and are not objects."""
    if not chain.pg_dump:
        assert os.environ.get("D2_PG_DUMP_ABSENT_OK") == "1", (
            "no pg_dump: set D2_TEST_PG_DUMP or put it on PATH, or record the waiver with "
            "D2_PG_DUMP_ABSENT_OK=1")
        _write(chain.out, "pg_dump_absent.txt", "pg_dump absent; the catalog query stands alone\n")
        return
    oid_only = [(s["n"], s["label"], [list(r[:3]) for r in cd.oid_only(s["diff"])]) for s in chain.steps
                if cd.oid_only(s["diff"])]
    _write(chain.out, "oid_only_steps.json", json.dumps(oid_only, indent=1))
    _write(chain.out, "object_match.json", json.dumps(
        [{"n": s["n"], "label": s["label"], "matched": s["match"]["matched"],
          "unmatched": _unmatched(s)} for s in chain.steps if s["match"]["matched"] or any(_unmatched(s).values())],
        indent=1))
    disagree = [(s["n"], s["label"], _unmatched(s)) for s in chain.steps if any(_unmatched(s).values())]
    assert disagree == [], disagree
    assert sum(len(s["match"]["matched"]) for s in chain.steps) > 0


def test_every_pg_dump_type_is_swept(chain):
    """Every pg_dump object type the chain's dumps contain is in
    catalog_diff.DUMP_SWEEP with the catalog CATALOG_SQL reads it from."""
    if not chain.pg_dump:
        pytest.skip("covered by the D2_PG_DUMP_ABSENT_OK waiver above")      # pragma: no cover
    with open(os.path.join(chain.out, "dump_end.sql"), encoding="utf-8") as fh:
        types = cd.dump_types(fh.read())
    _write(chain.out, "dump_types_end.json", json.dumps(types, indent=1))
    assert [t for t in types if not cd.DUMP_SWEEP.get(t)] == []


# --- object-set controls (M9), one per catalog route --------------------------
#
# Each control runs, in order, on its OWN clone of the template (not the
# chain), as the admin DSN's user. A control is (name, SQL, kind, object):
# after the SQL the catalog diff and the pg_dump diff must change the same
# object set, the object named must be among the matched ones, and the
# catalog diff must hold a row of the named kind (so every arm of
# CATALOG_SQL has a route of its own). {me} is the admin user. Controls
# marked SU need a superuser: under a non-superuser DSN PostgreSQL refuses
# them (42501) and the refusal is the outcome recorded.

SU = "su"
ROUTE_CONTROLS = [
    ("rt_namespace", "CREATE SCHEMA d2r_s", "namespace", "SCHEMA|-|d2r_s", None),
    ("rt_acl_schema", "GRANT USAGE ON SCHEMA d2r_s TO PUBLIC", "acl", "ACL|-|SCHEMA d2r_s", None),
    ("rt_class_create", "CREATE TABLE d2r_t (id serial PRIMARY KEY, n int NOT NULL DEFAULT 1, m text)",
     "class", "TABLE|public|d2r_t", None),
    ("rt_class_option", "ALTER TABLE d2r_t SET (fillfactor = 70)", "class", "TABLE|public|d2r_t", None),
    ("rt_rls", "ALTER TABLE d2r_t ENABLE ROW LEVEL SECURITY", "rls", "ROW SECURITY|public|d2r_t", None),
    ("rt_acl_table", "GRANT SELECT ON d2r_t TO PUBLIC", "acl", "ACL|public|TABLE d2r_t", None),
    ("rt_attribute", "ALTER TABLE d2r_t ADD COLUMN x int", "attribute", "TABLE|public|d2r_t", None),
    ("rt_acl_column", "GRANT SELECT (m) ON d2r_t TO PUBLIC", "acl", "ACL|public|COLUMN d2r_t.m", None),
    ("rt_default_inline", "ALTER TABLE d2r_t ALTER COLUMN x SET DEFAULT 7", "default", "TABLE|public|d2r_t", None),
    ("rt_default_separate", "ALTER SEQUENCE d2r_t_id_seq RENAME TO d2r_t_id_seq2", "default",
     "DEFAULT|public|d2r_t id", None),
    ("rt_constraint_check", "ALTER TABLE d2r_t ADD CONSTRAINT d2r_chk CHECK (x > 0)", "constraint",
     "TABLE|public|d2r_t", None),
    ("rt_constraint_unique", "ALTER TABLE d2r_t ADD CONSTRAINT d2r_uq UNIQUE (m)", "constraint",
     "CONSTRAINT|public|d2r_t d2r_uq", None),
    ("rt_index_create", "CREATE INDEX d2r_idx ON d2r_t (x)", "index", "INDEX|public|d2r_idx", None),
    ("rt_index_cluster", "ALTER TABLE d2r_t CLUSTER ON d2r_idx", "index", "INDEX|public|d2r_idx", None),
    ("rt_proc", "CREATE FUNCTION d2r_f(a int) RETURNS int LANGUAGE sql AS $$ SELECT a $$", "proc",
     "FUNCTION|public|d2r_f(integer)", None),
    ("rt_proc_atomic_body", "CREATE OR REPLACE FUNCTION d2r_f(a int) RETURNS int LANGUAGE sql "
     "BEGIN ATOMIC SELECT a + 1; END", "proc", "FUNCTION|public|d2r_f(integer)", None),
    ("rt_acl_proc", "REVOKE EXECUTE ON FUNCTION d2r_f(int) FROM PUBLIC", "acl",
     "ACL|public|FUNCTION d2r_f(a integer)", None),
    ("rt_trigger", "CREATE FUNCTION d2r_tf() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$; "
     "CREATE TRIGGER d2r_trg BEFORE UPDATE ON d2r_t FOR EACH ROW EXECUTE FUNCTION d2r_tf()", "trigger",
     "TRIGGER|public|d2r_t d2r_trg", None),
    ("rt_policy", "CREATE POLICY d2r_pol ON d2r_t USING (true)", "policy", "POLICY|public|d2r_t d2r_pol", None),
    ("rt_rule", "CREATE RULE d2r_rule AS ON DELETE TO d2r_t DO INSTEAD NOTHING", "rule",
     "RULE|public|d2r_t d2r_rule", None),
    ("rt_view_rule", "CREATE VIEW d2r_v AS SELECT id FROM d2r_t; CREATE OR REPLACE VIEW d2r_v AS "
     "SELECT id, x FROM d2r_t", "rule", "VIEW|public|d2r_v", None),
    ("rt_type", "CREATE TYPE d2r_mood AS ENUM ('a')", "type", "TYPE|public|d2r_mood", None),
    ("rt_type_label", "ALTER TYPE d2r_mood ADD VALUE 'b'", "type", "TYPE|public|d2r_mood", None),
    ("rt_acl_type", "REVOKE USAGE ON TYPE d2r_mood FROM PUBLIC", "acl", "ACL|public|TYPE d2r_mood", None),
    ("rt_sequence", "ALTER SEQUENCE d2r_t_id_seq2 INCREMENT BY 2", "sequence",
     "SEQUENCE|public|d2r_t_id_seq2", None),
    ("rt_owned", "CREATE SEQUENCE d2r_free; ALTER SEQUENCE d2r_free OWNED BY d2r_t.x", "owned",
     "SEQUENCE OWNED BY|public|d2r_free", None),
    ("rt_inherits", "CREATE TABLE d2r_parent (a int); CREATE TABLE d2r_child (b int) INHERITS (d2r_parent); "
     "ALTER TABLE d2r_child NO INHERIT d2r_parent", "attribute", "TABLE|public|d2r_child", None),
    ("rt_inherits_add", "ALTER TABLE d2r_child INHERIT d2r_parent", "inherits", "TABLE|public|d2r_child", None),
    ("rt_partition", "CREATE TABLE d2r_p (k int) PARTITION BY RANGE (k); "
     "CREATE TABLE d2r_p1 PARTITION OF d2r_p FOR VALUES FROM (0) TO (10)", "partition",
     "TABLE ATTACH|public|d2r_p1", None),
    ("rt_partition_bound", "ALTER TABLE d2r_p DETACH PARTITION d2r_p1; "
     "ALTER TABLE d2r_p ATTACH PARTITION d2r_p1 FOR VALUES FROM (0) TO (5)", "partition",
     "TABLE ATTACH|public|d2r_p1", None),
    ("rt_statistics", "CREATE STATISTICS d2r_st ON n, x FROM d2r_t", "statistics", "STATISTICS|public|d2r_st", None),
    ("rt_extension", 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"', "extension", "EXTENSION|-|uuid-ossp", None),
    ("rt_default_acl", "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO PUBLIC",
     "default_acl", "DEFAULT ACL|public|DEFAULT PRIVILEGES FOR TABLES|{me}", None),
    ("rt_default_acl_global", "ALTER DEFAULT PRIVILEGES GRANT USAGE ON SEQUENCES TO PUBLIC",
     "default_acl", "DEFAULT ACL|-|DEFAULT PRIVILEGES FOR SEQUENCES|{me}", None),
    ("rt_collation", "CREATE COLLATION d2r_coll (provider = icu, locale = 'und')", "collation",
     "COLLATION|public|d2r_coll", None),
    ("rt_conversion", "CREATE CONVERSION d2r_conv FOR 'LATIN1' TO 'UTF8' FROM iso8859_1_to_utf8",
     "conversion", "CONVERSION|public|d2r_conv", None),
    ("rt_operator", "CREATE OPERATOR === (leftarg = int, rightarg = int, function = int4eq)", "operator",
     "OPERATOR|public|===", None),
    ("rt_cast", "CREATE TYPE d2r_pair AS (x int); CREATE CAST (d2r_pair AS text) WITH INOUT", "cast",
     "CAST|-|CAST (public.d2r_pair AS text)", None),
    ("rt_ts_config", "CREATE TEXT SEARCH CONFIGURATION d2r_cfg (COPY = english)", "ts_config",
     "TEXT SEARCH CONFIGURATION|public|d2r_cfg", None),
    ("rt_ts_dict", "CREATE TEXT SEARCH DICTIONARY d2r_dict (TEMPLATE = simple)", "ts_dict",
     "TEXT SEARCH DICTIONARY|public|d2r_dict", None),
    ("rt_publication", "CREATE PUBLICATION d2r_pub", "publication", "PUBLICATION|-|d2r_pub", None),
    ("rt_publication_rel", "ALTER PUBLICATION d2r_pub ADD TABLE d2r_t", "publication_rel",
     "PUBLICATION TABLE|public|d2r_pub d2r_t", None),
    ("rt_comment", "COMMENT ON TABLE d2r_t IS 'd2r'", "comment", "COMMENT|public|TABLE d2r_t", None),
    ("rt_comment_column", "COMMENT ON COLUMN d2r_t.x IS 'd2r'", "comment", "COMMENT|public|COLUMN d2r_t.x", None),
    ("rt_publication_ns", "ALTER PUBLICATION d2r_pub ADD TABLES IN SCHEMA d2r_s", "publication_ns",
     "PUBLICATION TABLES IN SCHEMA|d2r_s|d2r_pub d2r_s", SU),
    ("rt_event_trigger", "CREATE EVENT TRIGGER d2r_evt ON sql_drop EXECUTE FUNCTION d2_probe.log_drop()",
     "event_trigger", "EVENT TRIGGER|-|d2r_evt", SU),
    ("rt_opfamily", "CREATE OPERATOR FAMILY d2r_fam USING btree", "opfamily", "OPERATOR FAMILY|public|d2r_fam", SU),
    ("rt_opclass", "CREATE OPERATOR CLASS d2r_opc FOR TYPE int4 USING btree FAMILY d2r_fam AS "
     "OPERATOR 1 <, FUNCTION 1 btint4cmp(int4, int4)", "opclass", "OPERATOR CLASS|public|d2r_opc", SU),
    ("rt_ts_parser", "CREATE TEXT SEARCH PARSER d2r_prs (START = prsd_start, GETTOKEN = prsd_nexttoken, "
     "END = prsd_end, LEXTYPES = prsd_lextype)", "ts_parser", "TEXT SEARCH PARSER|public|d2r_prs", SU),
    ("rt_ts_template", "CREATE TEXT SEARCH TEMPLATE d2r_tmpl (LEXIZE = dsimple_lexize)", "ts_template",
     "TEXT SEARCH TEMPLATE|public|d2r_tmpl", SU),
    ("rt_language", "CREATE LANGUAGE d2r_lang HANDLER plpgsql_call_handler", "language",
     "PROCEDURAL LANGUAGE|-|d2r_lang", SU),
    ("rt_transform", "CREATE FUNCTION d2r_tf_from(internal) RETURNS internal LANGUAGE internal IMMUTABLE STRICT "
     "AS 'int4recv'; CREATE FUNCTION d2r_tf_to(internal) RETURNS int LANGUAGE internal IMMUTABLE STRICT "
     "AS 'int4recv'; CREATE TRANSFORM FOR int LANGUAGE d2r_lang (FROM SQL WITH FUNCTION d2r_tf_from(internal), "
     "TO SQL WITH FUNCTION d2r_tf_to(internal))", "transform", "TRANSFORM|-|TRANSFORM FOR integer LANGUAGE d2r_lang",
     SU),
    ("rt_fdw", "CREATE FOREIGN DATA WRAPPER d2r_fdw", "fdw", "FOREIGN DATA WRAPPER|-|d2r_fdw", SU),
    ("rt_server", "CREATE SERVER d2r_srv FOREIGN DATA WRAPPER d2r_fdw", "server", "SERVER|-|d2r_srv", SU + "<rt_fdw"),
    ("rt_user_mapping", "CREATE USER MAPPING FOR PUBLIC SERVER d2r_srv", "user_mapping",
     "USER MAPPING|-|USER MAPPING public SERVER d2r_srv", SU + "<rt_server"),
    ("rt_foreign_table", "CREATE FOREIGN TABLE d2r_ft (a int) SERVER d2r_srv", "class",
     "FOREIGN TABLE|public|d2r_ft", SU + "<rt_server"),
    ("rt_access_method", "CREATE ACCESS METHOD d2r_am TYPE TABLE HANDLER heap_tableam_handler", "access_method",
     "ACCESS METHOD|-|d2r_am", SU),
    ("rt_subscription", "CREATE SUBSCRIPTION d2r_sub CONNECTION 'dbname=postgres' PUBLICATION d2r_pub "
     "WITH (connect = false)", "subscription", "SUBSCRIPTION|-|d2r_sub", SU),
    ("rt_subscription_drop", "ALTER SUBSCRIPTION d2r_sub DISABLE; ALTER SUBSCRIPTION d2r_sub SET (slot_name = NONE); "
     "DROP SUBSCRIPTION d2r_sub", "subscription", "SUBSCRIPTION|-|d2r_sub", SU + "<rt_subscription"),
    # an owner change rewrites the Owner field of the comment block's header
    # and not its text: that block is not a changed object
    # a column under a UNIQUE constraint widened in place: the constraint's
    # index carries the column too, and that index column is the table's
    # (pg_dump re-renders the TABLE, not the CONSTRAINT); found by the chain
    # at 183_widen_bracket_side.sql
    ("rt_index_column_setup", "CREATE TABLE d2r_w (a varchar(4), CONSTRAINT d2r_w_a_key UNIQUE (a))",
     "class", "TABLE|public|d2r_w", None),
    ("rt_index_column_widen", "ALTER TABLE d2r_w ALTER COLUMN a TYPE varchar(16)", "attribute",
     "TABLE|public|d2r_w", None),
    ("rt_owner_only_header", "ALTER TABLE d2r_t OWNER TO pg_database_owner", "class", "TABLE|public|d2r_t", None),
    # no object changes: a temporary table, a read
    ("rt_none_temp", "CREATE TEMP TABLE d2r_tmp (a int)", None, None, None),
    ("rt_none_select", "SELECT 1", None, None, None),
]


async def _route_run(dsn, pg_dump, controls, me, superuser, wrap=None):
    """Run the controls in order on dsn; per control: refused SQLSTATE, or
    the object match with whether the named object and row kind are there.
    wrap(name, diff, before_dump, after_dump) may replace the comparison
    inputs (the rejection controls below use it)."""
    conn = await _connect(dsn)
    out = []
    try:
        prev, pdump = await cd.snapshot(conn), cd.dump(pg_dump, dsn)
        for name, sql, kind, obj, su in controls:
            obj = obj.replace("{me}", me) if obj else None
            try:
                await conn.execute(sql)
            except asyncpg.PostgresError as exc:
                out.append({"control": name, "refused": exc.sqlstate, "su": su,
                            "error": str(exc).splitlines()[0][:200]})
                continue
            cur, cdump = await cd.snapshot(conn), cd.dump(pg_dump, dsn)
            d = cd.diff(prev, cur)
            args = wrap(name, d, pdump, cdump) if wrap else (d, pdump, cdump)
            m = cd.match(*args)
            kinds = sorted({r[0] for r in args[0]["added"] + args[0]["removed"]})
            out.append({"control": name, "refused": None, "su": su, "object": obj, "kind": kind,
                        "matched": m["matched"], "catalog_only": m["catalog_only"], "dump_only": m["dump_only"],
                        "kinds": kinds})
            prev, pdump = cur, cdump
    finally:
        await conn.close()
    return out


def _route_verdict(r, superuser, accepted=frozenset()):
    """'ok' or the reason the control failed. Under an admin role that is not
    a superuser, a superuser-only control (SU) is accepted when PostgreSQL
    refuses it for privilege (42501); a control that needs a superuser-only
    control's object (SU + "<" + that control) is accepted when it is
    refused because the object is missing (42704) AND that control's own
    refusal was accepted (accepted: the names of accepted refusals, earlier
    in the run). Under a superuser no refusal is accepted."""
    if r["refused"]:
        if not superuser and r["su"] == SU and r["refused"] == "42501":
            return "ok"
        if (not superuser and r["su"] and r["su"].startswith(SU + "<") and r["refused"] == "42704"
                and r["su"][len(SU) + 1:] in accepted):
            return "ok"
        return "refused %s: %s" % (r["refused"], r["error"])
    if r["catalog_only"] or r["dump_only"]:
        return "unmatched: catalog_only %s dump_only %s" % (sorted(r["catalog_only"]), r["dump_only"])
    if r["object"] is None:
        return "ok" if not r["matched"] else "changed %s" % r["matched"]
    if r["object"] not in r["matched"]:
        return "object %s not matched (matched %s)" % (r["object"], r["matched"])
    if r["kind"] not in r["kinds"]:
        return "no %s row in the catalog diff (kinds %s)" % (r["kind"], r["kinds"])
    return "ok"


def _scratch_clone(tag):
    _require()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    db = ("%s_%s_%s_%d" % (os.environ.get("D2_DB_PREFIX", "d2catalog"), tag, stamp, os.getpid())).lower()
    asyncio.run(_clone(db))
    return db


@pytest.fixture(scope="module")
def route_db():
    """A clone of the template for the object-set controls, dropped after."""
    db = _scratch_clone("rt")
    try:
        yield db
    finally:
        asyncio.run(_drop_db(db))


@pytest.fixture(scope="module")
def m9_db():
    """A clone of the template for the report's example, dropped after."""
    db = _scratch_clone("m9")
    try:
        yield db
    finally:
        asyncio.run(_drop_db(db))


def _route_out():
    out = os.environ.get("D2_CATALOG_OUT")
    if out:
        os.makedirs(out, exist_ok=True)
    return out


_KEYED = ("--\n-- PostgreSQL database dump\n--\n\n\\restrict %s\n\n"
          "SET statement_timeout = 0;\n\n"
          "--\n-- Name: f(); Type: FUNCTION; Schema: public; Owner: postgres\n--\n\n"
          "CREATE FUNCTION public.f() RETURNS text LANGUAGE sql AS $$\n"
          "\\restrict notakey\n$$;\n\n"
          "--\n-- Name: e; Type: EVENT TRIGGER; Schema: -; Owner: postgres\n--\n\n"
          "CREATE EVENT TRIGGER e ON sql_drop EXECUTE FUNCTION public.g();\n\n"
          "--\n-- PostgreSQL database dump complete\n--\n\n\\unrestrict %s\n\n")


def test_pg_dump_session_key_belongs_to_no_object():
    """Database-free (the seat-4 finding of round 8): two dumps that differ
    only in pg_dump's per-dump session key change no object; a key line
    inside an object's body is the object's text; a pair that does not
    match is refused; a dump without the pair is unchanged."""
    a, b = _KEYED % ("KeyA1", "KeyA1"), _KEYED % ("KeyB2", "KeyB2")
    assert cd.dump_objects(a, b) == ["(preamble)", "EVENT TRIGGER|-|e"]  # control: unnormalised
    na, nb = cd.without_session_key(a), cd.without_session_key(b)
    assert cd.dump_objects(na, nb) == []
    assert "\\restrict notakey\n" in na and "\\restrict KeyA1" not in na and "unrestrict" not in na
    changed = cd.without_session_key(b.replace("RETURNS text", "RETURNS int"))
    assert cd.dump_objects(na, changed) == ["FUNCTION|public|f()"]
    for bad in (_KEYED % ("KeyA1", "KeyB2"), (_KEYED % ("KeyA1", "KeyA1")).replace("\\restrict KeyA1\n", ""),
                (_KEYED % ("KeyA1", "KeyA1")).replace("\\unrestrict KeyA1\n", "")):
        with pytest.raises(AssertionError, match="session key"):
            cd.without_session_key(bad)
    plain = (_KEYED % ("K", "K")).replace("\\restrict K\n", "").replace("\\unrestrict K\n", "")
    assert cd.without_session_key(plain) == plain


def test_route_verdict_accepts_only_privilege_refusals_and_their_dependents():
    """The refusal rule of _route_verdict, without a database: what it
    accepts under a non-superuser admin role, and everything it rejects."""
    base = {"control": "c", "error": "e", "object": None, "kind": None, "matched": [],
            "catalog_only": {}, "dump_only": [], "kinds": []}
    v = lambda refused, su, superuser, accepted=(): _route_verdict(
        dict(base, refused=refused, su=su), superuser, set(accepted))
    assert v("42501", SU, False) == "ok"
    assert v("42704", SU + "<p", False, {"p"}) == "ok"
    rejected = [
        v("42501", SU, True),                      # a superuser is never refused
        v("42704", SU + "<p", True, {"p"}),
        v("42704", SU + "<p", False),              # its prerequisite was not refused-and-accepted
        v("42704", SU + "<p", False, {"q"}),
        v("42501", SU + "<p", False, {"p"}),       # a dependent is accepted only as missing-object
        v("42704", SU, False),                     # a plain SU control only for privilege
        v("42501", None, False),                   # a control not marked SU
        v("42704", None, False, {"p"}),
    ]
    assert all(x != "ok" for x in rejected), rejected


def test_route_controls_match_object_sets(route_db):
    """M9's route controls: every arm of CATALOG_SQL has a control whose
    change pg_dump renders as the named object and the catalog diff holds
    as a row of that arm's kind; catalog and dump change the same objects."""
    pg_dump = cd.client("D2_TEST_PG_DUMP", "pg_dump")
    assert pg_dump, "the object-set controls need pg_dump (D2_TEST_PG_DUMP or PATH)"
    who = asyncio.run(_whoami())
    res = asyncio.run(_route_run(_dsn(route_db), pg_dump, ROUTE_CONTROLS, who["admin_user"], who["superuser"]))
    verdicts, accepted = [], set()
    for r in res:
        v = _route_verdict(r, who["superuser"], accepted)
        if r["refused"] and v == "ok":
            accepted.add(r["control"])
        verdicts.append((r["control"], v))
    out = _route_out()
    if out:
        _write(out, "route_controls.json", json.dumps(
            [dict(r, verdict=v) for r, (_n, v) in zip(res, verdicts)], indent=1, default=str))
    assert [r["control"] for r in res] == [c[0] for c in ROUTE_CONTROLS]
    assert [(n, v) for n, v in verdicts if v != "ok"] == []
    # every kind CATALOG_SQL emits has a control naming it
    arms = set(re.findall(r"^SELECT '(\w+)'", cd.CATALOG_SQL, re.M))
    assert arms - {c[2] for c in ROUTE_CONTROLS} == set(), arms - {c[2] for c in ROUTE_CONTROLS}


# The report's own example (M9): an ALTER DEFAULT PRIVILEGES beside ordinary
# DDL. Matched with the whole catalog query; and the comparison REJECTS the
# same step when the catalog side lacks pg_default_acl, or when the two
# sides measure different spans, although neither side is empty.
M9_EXAMPLE = [
    ("m9_default_acl_beside_ddl", "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO PUBLIC; "
     "CREATE TABLE d2m9_t (a int)", "default_acl", "DEFAULT ACL|public|DEFAULT PRIVILEGES FOR TABLES|{me}", None),
]


def _without_default_acl(name, d, before, after):
    # the catalog side without pg_default_acl: its object arm AND its raw
    # rows (catalog_all reads every catalog)
    keep = lambda rows: [r for r in rows if r[0] != "default_acl"  # noqa: E731
                         and not (r[0] == "raw" and r[2] == "pg_default_acl")]
    return {"added": keep(d["added"]), "removed": keep(d["removed"])}, before, after


def _dump_span_without_change(name, d, before, after):
    return d, before, before


def test_m9_report_example_and_its_rejections(m9_db):
    pg_dump = cd.client("D2_TEST_PG_DUMP", "pg_dump")
    assert pg_dump, "the object-set controls need pg_dump (D2_TEST_PG_DUMP or PATH)"
    who = asyncio.run(_whoami())
    me = who["admin_user"]
    want = "DEFAULT ACL|public|DEFAULT PRIVILEGES FOR TABLES|%s" % me
    results = {}
    # each variant grants a privilege the earlier ones did not, so each
    # changes the default ACL again
    for label, wrap, suffix, priv in (("whole", None, "a", "SELECT"),
                                      ("no_default_acl", _without_default_acl, "b", "INSERT"),
                                      ("dump_unchanged", _dump_span_without_change, "c", "UPDATE")):
        controls = [(n + "_" + label, s.replace("d2m9_t", "d2m9_" + suffix).replace("SELECT ON TABLES",
                                                                                   priv + " ON TABLES"), k, o, su)
                    for n, s, k, o, su in M9_EXAMPLE]
        results[label] = asyncio.run(_route_run(_dsn(m9_db), pg_dump, controls, me, who["superuser"], wrap))[0]
    out = _route_out()
    if out:
        _write(out, "m9_example.json", json.dumps(results, indent=1, default=str))
    whole = results["whole"]
    assert _route_verdict(whole, who["superuser"]) == "ok", whole
    assert want in whole["matched"] and "TABLE|public|d2m9_a" in whole["matched"], whole
    # the catalog side without pg_default_acl: the dump's DEFAULT ACL is unmatched
    nod = results["no_default_acl"]
    assert nod["dump_only"] == [want] and not nod["catalog_only"], nod
    # the dump side measuring no change: every catalog object is unmatched
    unch = results["dump_unchanged"]
    assert unch["dump_only"] == [] and want in unch["catalog_only"], unch


# --- M11: a tail behind a former refusal is measured ---------------------------


async def _apply_tail(db, path, with_prereqs, psql):
    """On database db: TAIL_FILE's prerequisites (or none), then the file at
    path; returns the file's outcome and its own catalog diff."""
    dsn = _dsn(db)
    pre = []
    if with_prereqs:
        for step in d2_seed.steps_for(TAIL_FILE):
            pre.append(await _prereq(dsn, step))
    before = await _snap(dsn)
    outcome = cd.apply_file(psql, dsn, path)
    after = await _snap(dsn)
    return dict(outcome, prereqs=[(p["rc"], p["sqlstate"]) for p in pre], diff=cd.diff(before, after))


def test_id_moving_seeds_are_guarded_by_their_foreign_keys(chain):
    """The 398 and 399 seeds move rows to other ids (d2_seed.ID_MOVES). In
    the chain each ran under d2_seed's guard, which recorded every foreign
    key (pg_constraint) into the moved table and the moved ids. Control on a
    clone of the state right before TAIL_FILE, with a table referencing the
    row TAIL_FILE's seed moves: a plain foreign key makes the seed refuse
    (23503) and leaves every id where it was; an ON UPDATE CASCADE foreign
    key lets it run, recorded as cascading, the reference moved with the
    row."""
    for name in sorted(d2_seed.ID_MOVES):
        got = [s for s in chain.steps if s["label"] == "<prereq %s>" % name and s.get("guard")]
        assert len(got) == 1 and got[0]["rc"] == 0, (name, got)
        assert set(got[0]["guard"]) == set(d2_seed.ID_MOVES[name]), got[0]["guard"]
    step = [st for st in d2_seed.steps_for(TAIL_FILE) if st[0] == "sql"]
    assert len(step) == 1 and len(step[0]) == 3, step
    db = ("%s_fkg" % chain.pre_db)[:63]
    asyncio.run(_clone(db, chain.pre_db))
    dsn = _dsn(db)

    async def ids():
        conn = await _connect(dsn)
        try:
            return {r[0]: r[1] for r in await conn.fetch("SELECT id, sku FROM shop_items")}
        finally:
            await conn.close()

    async def ddl(sql):
        conn = await _connect(dsn)
        try:
            if sql.lstrip().upper().startswith("SELECT"):
                return await conn.fetch(sql)
            return await conn.execute(sql)
        finally:
            await conn.close()

    try:
        start = asyncio.run(ids())
        target = 250
        assert start.get(target) not in (None, "face_detail_spooky_head_bouncers"), start.get(target)
        asyncio.run(ddl("CREATE TABLE d2fk_plain (item int REFERENCES shop_items(id)); "
                        "INSERT INTO d2fk_plain VALUES (%d)" % target))
        plain = asyncio.run(_prereq(dsn, step[0]))
        after_plain = asyncio.run(ids())
        asyncio.run(ddl("DROP TABLE d2fk_plain; CREATE TABLE d2fk_cascade (item int REFERENCES shop_items(id) "
                        "ON UPDATE CASCADE); INSERT INTO d2fk_cascade VALUES (%d)" % target))
        cascade = asyncio.run(_prereq(dsn, step[0]))
        moved_to = [r[0] for r in asyncio.run(ddl("SELECT item FROM d2fk_cascade"))]
    finally:
        asyncio.run(_drop_db(db))
    _write(chain.out, "id_move_guard_control.json", json.dumps({
        "plain": {k: plain[k] for k in ("rc", "sqlstate", "error")},
        "cascade": {k: cascade[k] for k in ("rc", "sqlstate", "error", "guard")},
        "reference_after_cascade": moved_to}, indent=1, default=str))
    assert plain["rc"] == 3 and plain["sqlstate"] == "23503", plain
    assert after_plain == start, "the refused seed moved ids"
    assert cascade["rc"] == 0, cascade
    fks = cascade["guard"]["shop_items"]["foreign_keys"]
    assert [f for f in fks if f[1] == "d2fk_cascade" and f[4]], fks
    assert target in cascade["guard"]["shop_items"]["moved"], cascade["guard"]
    assert moved_to == [870000 + target], moved_to


def test_m11_alter_behind_the_former_refusal_is_measured(chain):
    """TAIL_FILE stopped at its post-check in round 7 (declared P0001, its
    tail unmeasured). Here an ALTER of mail_inbox_rev is placed right after
    that refusing statement. With the prerequisites the file runs to its
    end, the ALTER runs, and the per-file attribution names the file beside
    300 (caught). Without them (the round-7 method) the file stops before
    the ALTER: no row and no command of mail_inbox_rev, so the declared
    list would still have held (missed)."""
    src = _read(TAIL_FILE)
    assert src.count(TAIL_AFTER) == 1, TAIL_AFTER
    edited = src.replace(TAIL_AFTER, "END $$;\n\n" + TAIL_ALTER + "\nCOMMIT;\n", 1)
    path = os.path.join(chain.out, "m11_tail_" + TAIL_FILE)
    _write(chain.out, "m11_tail_" + TAIL_FILE, edited)
    res = {}
    for label, with_prereqs in (("prereqs", True), ("round7_method", False)):
        db = ("%s_m11%s" % (chain.db, label[0]))[:63]
        asyncio.run(_clone(db, chain.pre_db))
        try:
            res[label] = asyncio.run(_apply_tail(db, path, with_prereqs, chain.psql))
        finally:
            asyncio.run(_drop_db(db))
    label = TAIL_FILE + " (m11 tail)"
    got = cd.changers(_attribution(chain.steps) + [(label, res["prereqs"]["diff"])], MAIL)
    old = res["round7_method"]
    _write(chain.out, "m11_control.json", json.dumps({
        k: dict(v, diff=None, rows_on_mail=[list(r) for r in cd.rows_on(v["diff"], MAIL)])
        for k, v in res.items()} | {"changers_with_prereqs": got}, indent=1))
    assert res["prereqs"]["rc"] == 0 and res["prereqs"]["sqlstate"] is None, res["prereqs"]
    assert got == [M300, label], got
    assert [c for c in res["prereqs"]["commands"] if c[2] == MAIL], res["prereqs"]["commands"]
    # the round-7 method: refused before the ALTER, no trace of it
    assert old["rc"] == 3 and old["sqlstate"] == "P0001", old
    assert not cd.rows_on(old["diff"], MAIL) and not [c for c in old["commands"] if "mail_inbox_rev" in c[2]]


async def _in_schema(dsn, schema, sql):
    """sql run in a fresh schema inside a REPEATABLE READ transaction that is
    rolled back; returns the catalog after it. The position is bound to its
    transaction at both ends (catalog_position, round 10): a program that
    ends it raises 'AssertionError: _in_schema: ENDED:...', on the success
    path and the error path alike. The connection is closed after it."""
    conn = await _connect(dsn)
    tr = conn.transaction(isolation="repeatable_read")
    await tr.start()
    try:
        pos = await catalog_position.start(conn)
        await conn.execute("CREATE SCHEMA %s; SET LOCAL search_path = %s, public" % (schema, schema))
        try:
            await conn.execute(sql)
        except asyncpg.PostgresError as exc:
            await _position_kept(conn, pos, dsn, "_in_schema", exc)
            raise
        await _position_kept(conn, pos, dsn, "_in_schema")
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
    # the catalog is read with search_path '' (as pg_dump reads it), so a
    # reference to the copy's own relation (a self-referencing FK, a
    # serial's sequence) prints d2_a1-qualified where the original prints
    # public-qualified
    strip = re.compile(r"\bd2_a1\.")
    assert [(k, i, strip.sub("public.", d)) for k, i, d in cd.shape(rows, "d2_a1." + table)] == \
        cd.shape(want, "public." + table)
    assert {k: strip.sub("public.", v) for k, v in cd.defaults(rows, "d2_a1." + table).items()} == \
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


async def _after_ended(conn):
    """A position the program ended may leave the program's own transaction
    in the failed state (its error after a COMMIT; BEGIN, or a refused
    return to the harness savepoint): rolled back, so the diff can be read.
    Nothing in a failed transaction can commit; what the program committed
    before it stays committed and is in the diff."""
    try:
        await conn.fetchval("SELECT 1")
    except asyncpg.InFailedSQLTransactionError:
        await conn.execute("ROLLBACK")


def _ended(seen):
    """'ENDED:<what changed>' for a position whose transaction the program
    ended (catalog_position.check), else None."""
    return catalog_position.ended_effect(seen["ended"]) if seen["ended"] else None


async def _position_kept(conn, pos, monitor_dsn, where, exc=None):
    """The rollback harness's position must still be in the transaction that
    opened it (round 10, report test_r7_ro_role_pg.py:257: round 9 checked
    only that SOME transaction was open, conn.is_in_transaction(), so
    COMMIT; BEGIN passed). A program that ended it has committed or
    discarded outside the harness: reported by the harness's name, an
    effect, never a read."""
    seen = await catalog_position.check(conn, pos, monitor_dsn)
    if seen["ended"]:
        raise AssertionError("%s: %s" % (where, _ended(seen))) from exc
    return seen


_MEASURE_CLONES = [0]


async def _measure(dsn, program, schema=None):
    """program run on a throwaway clone of the database `dsn` names, in one
    transaction that is rolled back, catalog before and after; the clone is
    dropped after. A migration file carries its own transaction control
    (373 ends with COMMIT), and that COMMIT ends this transaction: what the
    program runs after it commits, and the rollback undoes nothing the
    program committed. The clone keeps the measured database unchanged
    whatever the program does (round 9: the two DISABLE TRIGGER ALL
    controls, appended after 373's COMMIT, persisted in the chain database
    under a superuser and changed every later reading of it)."""
    base = dsn.rsplit("/", 1)[1]
    _MEASURE_CLONES[0] += 1
    clone = "%s_m%d" % (base[:52], _MEASURE_CLONES[0])
    await _clone(clone, base)
    try:
        return await _measure_in(_dsn(clone), program, schema)
    finally:
        await _drop_db(clone)


async def _measure_in(dsn, program, schema):
    """program in one REPEATABLE READ transaction, rolled back. The position
    is bound to its transaction at both ends (catalog_position, round 10):
    'ended' is 'ENDED:...' when the program ended it (an effect, reported on
    the success and the error path; the diff is still returned, read after
    the program in whatever transaction it left), else None. When the
    position kept its transaction, 'outside' lists the shared catalogs whose
    rows outside catalog_all.RESTRICT differ (catalog_all.outside, one
    snapshot at both ends); when it ended, they are not comparable and
    'outside' is None. 'xid' is the transaction's xid when one was assigned.
    The connection is closed after it."""
    conn = await _connect(dsn)
    logs = []
    conn.add_log_listener(lambda _c, msg: logs.append(msg.message))
    tr = conn.transaction(isolation="repeatable_read")
    await tr.start()
    try:
        pos = await catalog_position.start(conn)
        if schema:
            await conn.execute("CREATE SCHEMA %s" % schema)
        before = await cd.snapshot(conn)
        shared = await ca.outside(conn)
        if schema:
            await conn.execute("SET LOCAL search_path = %s, public" % schema)
        try:
            await conn.execute(program)
        except asyncpg.PostgresError as exc:
            seen = await catalog_position.check(conn, pos, dsn)
            return {"refused": exc.sqlstate, "error": str(exc).splitlines()[0][:200],
                    "commands": cd.commands("\n".join(logs)), "ended": _ended(seen), "xid": seen["xid"],
                    "outside": None}
        seen = await catalog_position.check(conn, pos, dsn)
        ended = _ended(seen)
        if ended:
            await _after_ended(conn)
        await conn.execute("SELECT pg_catalog.set_config('search_path', 'public', false)")
        after = await cd.snapshot(conn)
        out = {"refused": None, "diff": cd.diff(before, after), "after": after,
               "commands": cd.commands("\n".join(logs)),
               "internal_not_enabled": await _internal_not_enabled(conn=conn),
               "ended": ended, "xid": seen["xid"], "outside": None}
        if not ended:
            out["outside"] = sorted(ca.keys(ca.outside_diff(shared, await ca.outside(conn))))
        return out
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
    if result.get("ended"):
        return "ended"
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
    """The extension and the program, each in its own savepoint, inside one
    REPEATABLE READ transaction rolled back after. The position is bound to
    its transaction (catalog_position, round 10): res['ended'] is
    'ENDED:...' when the program ended it, else None."""
    conn = await _connect(dsn)
    tr = conn.transaction(isolation="repeatable_read")
    await tr.start()
    try:
        pos = await catalog_position.start(conn)
        before = await cd.snapshot(conn)
        res = {"extension": None, "refused": None, "ended": None}
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
        res["ended"] = _ended(await catalog_position.check(conn, pos, dsn))
        if res["ended"]:
            await _after_ended(conn)
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
    assert res["ended"] is None, res
    if res["extension"] is None:
        outcome = "caught" if cd.rows_on(res["diff"], MAIL) else "clean"
        _record_control(chain, name, finding, res, outcome)
        assert res["refused"] is None and outcome == "caught", res
    else:
        _record_control(chain, name, finding, dict(res, refused="%s/%s" % (res["extension"], res["refused"])),
                        "refused")
        assert res["refused"] == "42704" and not cd.rows_on(res["diff"], MAIL), res


def test_migrations_are_applied_from_the_object_store(chain):
    """Ruling R8-CRLF. Every migration is applied from the blob at the frozen
    revision. Control on a clone of the state right before CRLF_FILE (whose
    post-check hashes its own release-note text): the file with CRLF line
    ends (what an autocrlf checkout holds) refuses at that post-check with
    P0001 and changes nothing; the file as the chain applies it (_blob_file)
    then runs to its end."""
    rev = sql_rev()
    with open(os.path.join(chain.out, "run.json"), encoding="utf-8") as fh:
        assert json.load(fh)["sql_rev"] == rev
    blob = _blob(CRLF_FILE)
    assert b"\r" not in blob, "the blob of %s at %s carries CR" % (CRLF_FILE, rev)
    crlf = blob.replace(b"\n", b"\r\n")
    crlf_path = os.path.join(chain.out, "crlf_" + CRLF_FILE)
    with open(crlf_path, "wb") as fh:
        fh.write(crlf)
    with open(os.path.join(SQL_DIR, CRLF_FILE), "rb") as fh:
        working = fh.read()
    step = [s for s in chain.steps if s["label"] == CRLF_FILE]
    assert len(step) == 1 and step[0]["rc"] == 0, step
    db = (_crlf_db(chain.pre_db) + "_t")[:63]
    asyncio.run(_clone(db, _crlf_db(chain.pre_db)))
    dsn = _dsn(db)
    try:
        before = asyncio.run(_snap(dsn))
        refused = cd.apply_file(chain.psql, dsn, crlf_path)
        after_refusal = asyncio.run(_snap(dsn))
        for st in d2_seed.steps_for(CRLF_FILE):
            assert asyncio.run(_prereq(dsn, st))["rc"] == 0
        route = cd.apply_file(chain.psql, dsn, _blob_file(chain.out, CRLF_FILE))
    finally:
        asyncio.run(_drop_db(db))
    _write(chain.out, "object_store_control.json", json.dumps({
        "sql_rev": rev, "file": CRLF_FILE, "working_copy_is_crlf": working == crlf,
        "working_copy_is_blob": working == blob,
        "crlf": {k: refused[k] for k in ("rc", "sqlstate", "error", "error_line")},
        "route": {k: route[k] for k in ("rc", "sqlstate", "error", "error_line")}}, indent=1))
    assert refused["rc"] == 3 and refused["sqlstate"] == "P0001", refused
    assert cd.empty(cd.diff(before, after_refusal)), "the refused CRLF copy changed the catalog"
    assert route["rc"] == 0, route


def _read(name):
    return _blob(name).decode("utf-8")


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
    # round 7, :455 (M10): a shifted updated_at default, measured against the
    # database clock with no window; the report's example and its siblings
    ("r7_455_updated_at_four_minutes_ahead", "r7 test_r7_catalog_diff_pg.py:455",
     ("TIMESTAMPTZ NOT NULL DEFAULT NOW()", "TIMESTAMPTZ NOT NULL DEFAULT NOW() + interval '4 minutes'"), "default"),
    ("r8_updated_at_one_second_behind", "r7 test_r7_catalog_diff_pg.py:455",
     ("TIMESTAMPTZ NOT NULL DEFAULT NOW()", "TIMESTAMPTZ NOT NULL DEFAULT NOW() - interval '1 second'"), "default"),
    ("r8_updated_at_clock_timestamp", "r7 test_r7_catalog_diff_pg.py:455",
     ("TIMESTAMPTZ NOT NULL DEFAULT NOW()", "TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()"), "default"),
    ("r8_updated_at_statement_timestamp", "r7 test_r7_catalog_diff_pg.py:455",
     ("TIMESTAMPTZ NOT NULL DEFAULT NOW()", "TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp()"), "default"),
    ("k_updated_at_current_timestamp", "kept",
     ("TIMESTAMPTZ NOT NULL DEFAULT NOW()", "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"), None),
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


# --- ruling R8-A1 (E1): every pg_catalog relation ----------------------------
#
# The two report examples, each carried by a MIGRATION (373 with the
# statement appended), run on the chain database in one transaction that is
# rolled back, as the attribution controls run. "exposed" means the step's
# diff holds the effect as raw rows AND the chain's own claims refuse it:
# match() returns it as unmatched (catalog_diff.unexplained_raw), a role
# default is a cluster row (test_no_step_changes_a_cluster_row), and a
# disabled trigger of mail_inbox_rev makes 373 a changer beside 300. The
# internal triggers of a table cannot be disabled by a role that is not a
# superuser: under such an admin PostgreSQL refuses it (42501), the refusal
# being the bound there. The ALTER ROLE control RESETs exactly its key in a
# finally block (never the whole role) and the admin role's setconfig must
# read the same before and after.

E1_CONTROLS = [
    # (name, finding, statement appended to 373, needs a superuser)
    ("e1_role_default_work_mem", "r8 catalog_diff.py:153",
     "ALTER ROLE CURRENT_USER SET work_mem = '63MB';", False),
    ("e1_disable_trigger_all_mail", "r8 catalog_diff.py:325",
     "ALTER TABLE public.mail_inbox_rev DISABLE TRIGGER ALL;", True),
    ("e1_disable_trigger_all_other_table", "r8 catalog_diff.py:325 (the class, on another table)",
     "ALTER TABLE public.mail_recipients DISABLE TRIGGER ALL;", True),
    ("k_e1_373_accounted", "kept", "", False),
]


async def _fetchval(sql, *args):
    conn = await asyncpg.connect(ADMIN)
    try:
        return await conn.fetchval(sql, *args)
    finally:
        await conn.close()


async def _own_setconfig():
    got = await _fetchval("SELECT s.setconfig FROM pg_catalog.pg_db_role_setting s JOIN pg_catalog.pg_roles r "
                          "ON r.oid = s.setrole WHERE s.setdatabase = 0 AND r.rolname = current_user")
    return list(got) if got is not None else None


@pytest.mark.parametrize("name,finding,stmt,su_only", E1_CONTROLS, ids=[c[0] for c in E1_CONTROLS])
def test_e1_control(chain, name, finding, stmt, su_only):
    superuser = chain.who["superuser"]
    me_oid = asyncio.run(_fetchval("SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user"))
    plants_role = stmt.startswith("ALTER ROLE")
    if plants_role:
        cfg_before = asyncio.run(_own_setconfig())
        # round 10 (report catalog_all.py:99, swept by class): the role's
        # settings in every database, not only the database-independent ones
        every_before = asyncio.run(_r10_settings(chain.who["admin_user"]))
        assert not [s for s in cfg_before or [] if s.startswith("work_mem=")], (
            "%s already carries work_mem in its setconfig %s: the control does not plant over it"
            % (chain.who["admin_user"], cfg_before))
    try:
        result = asyncio.run(_measure(chain.dsn, _read(M373) + "\n" + stmt + "\n"))
    finally:
        if plants_role:
            asyncio.run(_admin("ALTER ROLE CURRENT_USER RESET work_mem"))
            cfg_after = asyncio.run(_own_setconfig())
            every_after = asyncio.run(_r10_settings(chain.who["admin_user"]))
    if plants_role:
        assert cfg_after == cfg_before, (cfg_before, cfg_after)
        assert every_after == every_before, (every_before, every_after)
    label = M373 + " (" + name + ")"
    # 373 carries its own COMMIT: the measuring position is reported ENDED
    # (round 10), and the diff, read after the program, is still measured
    assert result["ended"] and result["ended"].startswith("ENDED:"), (name, result["ended"])
    if result["refused"]:
        _record_control(chain, name, finding, result, "refused")
        assert su_only and not superuser and result["refused"] == "42501", (name, result)
        return
    d = result["diff"]
    unexplained = ca.unexplained(d)
    changers = cd.changers(_attribution(chain.steps + [{"label": label, "diff": d}]), MAIL)
    outcome = {"unexplained": unexplained, "cluster": ca.cluster_rows(d), "changers": changers,
               "unmatched": sorted(cd.unexplained_raw(d))}
    _record_control(chain, name, finding, dict(result, error=json.dumps(outcome)[:4000]), "measured")
    assert not (su_only and not superuser), ("ran under an admin that is not a superuser", name)
    if name == "k_e1_373_accounted":
        assert unexplained == [] and outcome["cluster"] == [] and changers == [M300], outcome
    elif name == "e1_role_default_work_mem":
        # the row is the session role's own database-independent setting:
        # inside catalog_all.RESTRICT's pg_db_role_setting predicate
        want = [["added", "pg_db_role_setting", "(0,%d,{work_mem=63MB})" % me_oid, []]]
        assert [u for u in unexplained if u[1] == "pg_db_role_setting"] == want, unexplained
        assert outcome["cluster"] == [w[:3] for w in want], outcome["cluster"]
        assert "RAW|pg_db_role_setting" in outcome["unmatched"], outcome
    else:
        table = "public.mail_inbox_rev" if name.endswith("_mail") else "public.mail_recipients"
        internal = [u for u in unexplained if u[1] == "pg_trigger/internal"]
        assert internal and all(table in u[3] for u in internal), unexplained
        # changed IN PLACE: as many rows removed as added (the same triggers)
        sides = [u[0] for u in internal]
        assert sides.count("added") == sides.count("removed") > 0, internal
        assert "RAW|pg_trigger/internal" in outcome["unmatched"], outcome
        assert result["internal_not_enabled"] and all(
            t[0] == table.split(".", 1)[1] and t[2] == "D" for t in result["internal_not_enabled"]), result
        assert changers == ([M300, label] if table == MAIL else [M300]), changers


def test_every_pg_catalog_relation_is_measured_or_declared(route_db):
    """Ruling R8-A1 (E1): catalog_all's plan of this server, from the
    relations pg_class lists at run time: their number equals the frozen
    count for the major version, every declaration names a relation or
    column the server has, and every relation is measured unless EXCLUDED
    declares it whole (or UNREADABLE does, for a session that may not read
    it and has no view to read it through). The plan refuses a catalog it
    does not know: one more relation fails the frozen count and has no
    EXPLAINS entry; one more unreadable column has no declaration."""
    async def body():
        conn = await _connect(_dsn(route_db))
        try:
            return (await conn.fetchrow(ca.SESSION_SQL), [dict(r) for r in await conn.fetch(ca.COLUMNS_SQL)])
        finally:
            await conn.close()
    s, meta = asyncio.run(body())
    p = ca.plan(meta, s["major"])
    rels = sorted({m["rel"] for m in meta})
    out = _route_out()
    if out:
        _write(out, "catalog_all_plan.json", json.dumps({
            "major": s["major"], "count": p["count"], "measured": sorted(p["relations"]),
            "not_measured": [r for r in rels if r not in p["relations"]],
            "substituted": {r: e["source"] for r, e in p["relations"].items() if e["source"] != r},
            "excluded": [list(e) for e in ca.EXCLUDED], "unreadable": [list(e) for e in ca.UNREADABLE],
            "restrict": {k: list(v) for k, v in ca.RESTRICT.items()},
            "routes": asyncio.run(_r10_routes())}, indent=1, default=list))
    assert p["problems"] == [], p["problems"]
    assert p["count"] == ca.FROZEN_COUNT[s["major"]] == len(rels)
    whole = {e[0] for e in ca.EXCLUDED if e[1] is None}
    for r in rels:
        if r in p["relations"]:
            continue
        assert r in whole or (not _reads_whole(meta, r) and r in {e[0] for e in ca.UNREADABLE if e[1] is None}), r
    for r in ("pg_db_role_setting", "pg_authid", "pg_shdescription", "pg_shseclabel", "pg_trigger"):
        assert r in p["relations"], r
    assert all(e[2] for e in ca.EXCLUDED + ca.UNREADABLE) and all(v[1] for v in ca.RESTRICT.values())
    # the plan's own refusals
    extra = meta + [{"rel": "pg_rf9_new", "shared": False, "col": "x", "typ": "oid", "can": True}]
    got = ca.plan(extra, s["major"])["problems"]
    assert any("frozen at" in g for g in got) and any(g.startswith("pg_rf9_new has no EXPLAINS") for g in got), got
    hidden = [dict(m, can=False) if (m["rel"], m["col"]) == ("pg_class", "relname") else m for m in meta]
    got = ca.plan(hidden, s["major"])["problems"]
    assert got == ["the session may not read pg_class.relname and no declaration names it"], got


def _reads_whole(meta, rel):
    """True when the session may read every column of rel."""
    return all(m["can"] for m in meta if m["rel"] == rel)


R9_PROBE = "r9_measure_probe"


async def _r9_probe_in(dsn):
    conn = await _connect(dsn)
    try:
        return await conn.fetchval("SELECT pg_catalog.to_regclass($1)::text", "public." + R9_PROBE)
    finally:
        await conn.close()


async def _r9_drop_probe(dsn):
    conn = await _connect(dsn)
    try:
        await conn.execute("DROP TABLE IF EXISTS public.%s" % R9_PROBE)
    finally:
        await conn.close()


async def _r9_databases():
    conn = await asyncpg.connect(ADMIN)
    try:
        return [r[0] for r in await conn.fetch("SELECT datname::text FROM pg_catalog.pg_database")]
    finally:
        await conn.close()


def test_r9_measure_leaves_the_measured_database_unchanged(chain):
    """_measure's clone (round 9). A program that ends the measuring
    transaction, as 373's own COMMIT does, and then creates a table commits
    into the clone only: the table is in the measured diff (the program
    ran), absent from the chain database afterwards, and no clone of the
    chain database is left. The probe table exists for this test alone."""
    result = asyncio.run(_measure(chain.dsn, "COMMIT;\nCREATE TABLE public.%s (x int);\n" % R9_PROBE))
    try:
        assert result["refused"] is None, result
        # round 10: the program ended the measuring transaction, reported as
        # an effect; its diff is still returned
        assert result["ended"] and result["ended"].startswith("ENDED:"), result["ended"]
        assert R9_PROBE in repr(result["diff"]), "the probe program did not run"
        assert asyncio.run(_r9_probe_in(chain.dsn)) is None, (
            "the program's committed table reached the measured database")
        left = [n for n in asyncio.run(_r9_databases())
                if re.match(re.escape(chain.db[:52]) + r"_m\d+$", n)]
        assert left == [], left
    finally:
        asyncio.run(_r9_drop_probe(chain.dsn))


def test_r9_rollback_harnesses_report_a_program_that_ends_them(chain):
    """_in_schema and _language (round 9's refusal, restated in round 10):
    each reports, by name, a program that ends its transaction, as
    'ENDED:...'. Run on a clone of the chain database dropped after, so what
    the ended transaction committed lands there and not in the chain."""
    clone = "%s_h" % chain.db[:52]
    asyncio.run(_clone(clone, chain.db))
    try:
        dsn = _dsn(clone)
        with pytest.raises(AssertionError, match="^_in_schema: ENDED:"):
            asyncio.run(_in_schema(dsn, "d2_r9h", "COMMIT"))
        res = asyncio.run(_language(dsn, "plpgsql", "COMMIT"))
        assert res["ended"] and res["ended"].startswith("ENDED:"), res
    finally:
        asyncio.run(_drop_db(clone))


# --- round 10 (ruling REHEARSAL-R9-A1): identity and continuity -------------
#
# Report test_r7_ro_role_pg.py:257, carried to this file's harness family:
# each program below ends the harness transaction; every harness reports it,
# on the success path and on the error path. The harnesses run on a clone of
# the chain database, dropped after.

R10_ENDING = [
    ("commit_begin", "SET application_name = 'r9_probe'; COMMIT; BEGIN; RESET application_name"),
    ("commit_and_chain", "COMMIT AND CHAIN"),
    ("rollback_and_chain", "ROLLBACK AND CHAIN"),
    ("rollback", "ROLLBACK"),
    ("end_begin", "END; BEGIN"),
    ("abort_begin", "ABORT; BEGIN"),
    ("prepare_transaction", "PREPARE TRANSACTION 'rf10_cat_prep'"),
    ("commit_begin_error", "COMMIT; BEGIN; SELECT 1 / 0"),
]
R10_HARNESSES = ("_in_schema", "_language", "_measure")


_R10_SCHEMAS = [0]


async def _r10_harness(harness, dsn, program):
    """The harness's report for program: 'ENDED:...', or 'kept'. Each call
    uses a schema of its own: a program that ended the transaction has
    committed the schema the harness created before it."""
    if harness == "_in_schema":
        _R10_SCHEMAS[0] += 1
        try:
            await _in_schema(dsn, "d2_r10h_%d" % _R10_SCHEMAS[0], program)
        except AssertionError as exc:
            if str(exc).startswith("_in_schema: ENDED:"):
                return str(exc).split(": ", 1)[1]
            raise
        except asyncpg.PostgresError:
            return "kept"
        return "kept"
    if harness == "_language":
        return (await _language(dsn, "plpgsql", program))["ended"] or "kept"
    return (await _measure_in(dsn, program, None))["ended"] or "kept"


@pytest.fixture(scope="module")
def r10_clone(chain):
    clone = "%s_r10" % chain.db[:52]
    asyncio.run(_clone(clone, chain.db))
    try:
        yield _dsn(clone)
    finally:
        asyncio.run(_drop_db(clone))


@pytest.mark.parametrize("harness", R10_HARNESSES)
@pytest.mark.parametrize("name,program", R10_ENDING, ids=[c[0] for c in R10_ENDING])
def test_r10_n_ro_role_257_catalog_harness(r10_clone, harness, name, program):
    got = asyncio.run(_r10_harness(harness, r10_clone, program))
    assert got.startswith("ENDED:"), (harness, name, got)


@pytest.mark.parametrize("harness", R10_HARNESSES)
def test_r10_ro_role_257_catalog_harness_negative_control(r10_clone, harness):
    """The same harnesses, programs that keep their transaction (one of them
    failing inside it): 'kept'."""
    for program in ("SELECT 1; SELECT 2", "SELECT 1 / 0"):
        assert asyncio.run(_r10_harness(harness, r10_clone, program)) == "kept", (harness, program)


PLANT_VALUE = "rf10_cat_fixed_value"
# Round-10 plants run only on a role whose name starts with PLANT_PREFIX: a
# role created for a run, by any lane (rf10_cat_*, rf10_w30b_*). The seat
# objects and the administrators are never one; NEVER_PLANTED names them
# again so a refusal states them. A measurer that is neither a superuser nor
# an rf10_* stand-in (a seat's scr_gate: CREATEDB, not a superuser, not
# CREATEROLE) could plant only on its own role, so these cases SKIP there
# with SEAT_SKIP and run on 55432 only.
PLANT_PREFIX = "rf10_"
NEVER_PLANTED = ("postgres", "scr_gate", "scr_seat_ro", "scr_seat_ro_tmpl", "scr_seat_d2_tmpl")
SEAT_SKIP = ("round-10 plant: the measurer %s is neither a superuser nor an rf10_* stand-in, so the only role "
             "it could plant on is its own (a seat administrator's); this case runs on 55432 only, as an "
             "rf10_* stand-in or as a superuser with R10_CAT_ROLE naming an rf10_* role")


def _plant_decision(me, superuser, named):
    """The role a round-10 case plants on: an rf10_* measurer (a stand-in)
    plants on itself; a superuser plants only on the rf10_* role
    R10_CAT_ROLE names, and fails when it names none; any other measurer is
    skipped with SEAT_SKIP, never failed and never planted on."""
    if me.startswith(PLANT_PREFIX) and me not in NEVER_PLANTED:
        return me
    if not superuser:
        pytest.skip(SEAT_SKIP % me)
    if not named.startswith(PLANT_PREFIX) or named in NEVER_PLANTED:
        pytest.fail("round-10 plants run only on an rf10_* role created for the run: the measurer %s is a "
                    "superuser and R10_CAT_ROLE=%r does not name one" % (me, named))
    return named


def _other_role(me):
    """Under a stand-in, the rf10_* role R10_CAT_ROLE names, other than the
    stand-in (the target of the 42501 case)."""
    other = os.environ.get("R10_CAT_ROLE") or ""
    assert other.startswith(PLANT_PREFIX) and other not in NEVER_PLANTED and other != me, (
        "R10_CAT_ROLE must name an rf10_* role other than the stand-in: %r" % other)
    return other


def test_r10_plant_decision_admits_any_rf10_role_and_skips_a_seat_admin():
    """W30b's form: any lane's rf10_* stand-in or planted role is admitted;
    a seat administrator (not a superuser, not rf10_*) is skipped with the
    stated reason; a superuser with no rf10_* R10_CAT_ROLE fails; no seat
    object, administrator or other role is ever returned."""
    assert _plant_decision("rf10_w30b_gate", False, "") == "rf10_w30b_gate"
    assert _plant_decision("rf10_cat_gate", False, "rf10_cat_pw_1") == "rf10_cat_gate"
    assert _plant_decision("postgres", True, "rf10_w30b_pw_1") == "rf10_w30b_pw_1"
    for seat_admin in ("scr_gate", "scr_seat_ro"):
        with pytest.raises(pytest.skip.Exception) as e:
            _plant_decision(seat_admin, False, "rf10_w30b_pw_1")
        assert "55432 only" in str(e.value) and seat_admin in str(e.value), e.value
    for named in ("", "scr_seat_ro", "postgres", "scr_gate", "scr_seat_d2_tmpl", "rf9_x", "RF10_x", "xrf10_"):
        with pytest.raises(pytest.fail.Exception):
            _plant_decision("postgres", True, named)


def _r10_plant_role(chain):
    """(measurer, planted role), by _plant_decision."""
    me = chain.who["admin_user"]
    return me, _plant_decision(me, chain.who["superuser"], os.environ.get("R10_CAT_ROLE") or "")


async def _r10_settings(role):
    conn = await asyncpg.connect(ADMIN)
    try:
        rows = await conn.fetch(
            "SELECT s.setdatabase::int8 AS db, s.setconfig::text AS cfg FROM pg_catalog.pg_db_role_setting s "
            "JOIN pg_catalog.pg_roles r ON r.oid = s.setrole WHERE r.rolname = $1 ORDER BY 1", role)
        return [(r["db"], r["cfg"]) for r in rows]
    finally:
        await conn.close()


async def _r10_authid_reading():
    """(the outside() query text, the pg_authid row texts it returns)."""
    conn = await asyncpg.connect(ADMIN)
    try:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            p, rows, _names, _temp, _s = await ca.read(conn, outside=True)
            return ca.query(p, True), [r["body"] for r in rows if r["rel"] == "pg_authid"]
    finally:
        await conn.close()


async def _r10_routes():
    conn = await asyncpg.connect(ADMIN)
    try:
        return await ca.routes(conn)
    finally:
        await conn.close()


def test_r10_n_catalog_all_99_role_setting_in_another_database(chain):
    """ALTER ROLE <role> IN DATABASE postgres SET application_name, measured
    by _measure on a clone of the chain database. Round 9 kept only this
    database's and the database-independent settings, so the row was in no
    reading. Now the measurer's own settings in every database are in the
    diff (stand-in: the row is unexplained and a cluster row); another
    role's are among the shared rows outside RESTRICT (superuser:
    result['outside'] names pg_db_role_setting)."""
    me, role = _r10_plant_role(chain)
    target = "CURRENT_USER" if role == me else '"%s"' % role
    before = asyncio.run(_r10_settings(role))
    try:
        result = asyncio.run(_measure(chain.dsn, "ALTER ROLE %s IN DATABASE postgres SET application_name = "
                                                 "'r9_probe';" % target))
    finally:
        asyncio.run(_admin("ALTER ROLE %s IN DATABASE postgres RESET application_name" % target))
    assert asyncio.run(_r10_settings(role)) == before, before
    assert result["refused"] is None and result["ended"] is None, result
    rows = [u for u in ca.unexplained(result["diff"]) if u[1] == "pg_db_role_setting"]
    print("r10 catalog_all.py:99 measurer %s planted %s: unexplained %s outside %s"
          % (me, role, rows, result["outside"]))
    if role == me:
        assert len(rows) == 1 and rows[0][0] == "added" and "application_name=r9_probe" in rows[0][2], rows
        assert [c for c in ca.cluster_rows(result["diff"]) if c[1] == "pg_db_role_setting"], result["diff"]
    else:
        assert rows == [] and result["outside"] == ["pg_db_role_setting"], (rows, result["outside"])


def test_r10_n_catalog_all_138_stored_password(chain):
    """ALTER ROLE <role> PASSWORD '<fixed value>', measured by _measure.
    Superuser (rolpassword route 'digest'): the planted role's stored value
    is compared as its md5 among the shared rows outside RESTRICT, so
    result['outside'] names pg_authid; the value itself is printed nowhere.
    Stand-in (route 'unmeasured': pg_roles masks it): the measurer's own
    password change reaches no catalog reading (no unexplained row, nothing
    outside), and the route is stated; another role's password is out of
    reach (42501). Round 9 read pg_authid through pg_roles under every
    measurer, so the change was in no reading under a superuser either."""
    me, role = _r10_plant_role(chain)
    routes = asyncio.run(_r10_routes())
    su = chain.who["superuser"]
    assert routes["rolpassword"] == ("digest" if su else "unmeasured"), routes
    target = "CURRENT_USER" if role == me else '"%s"' % role
    try:
        result = asyncio.run(_measure(chain.dsn, "ALTER ROLE %s PASSWORD '%s';" % (target, PLANT_VALUE)))
    finally:
        asyncio.run(_admin("ALTER ROLE %s PASSWORD NULL" % target))
    assert PLANT_VALUE not in repr(result), "the planted value reached the result"
    rows = [u for u in ca.unexplained(result["diff"]) if u[1] == "pg_authid"]
    print("r10 catalog_all.py:138 measurer %s rolpassword route %s planted %s: unexplained %s outside %s xid %s"
          % (me, routes["rolpassword"], role, rows, result["outside"], bool(result["xid"])))
    assert result["refused"] is None and result["ended"] is None, result
    if su:
        assert rows == [] and result["outside"] == ["pg_authid"], (rows, result["outside"])
    else:
        assert rows == [] and result["outside"] == [] and result["xid"], (rows, result["outside"])
        assert ("pg_authid", "rolpassword") in [(u[0], u[1]) for u in routes["unmeasured"]], routes
        other = _other_role(me)
        refused = asyncio.run(_measure(chain.dsn, "ALTER ROLE \"%s\" PASSWORD '%s';" % (other, PLANT_VALUE)))
        assert refused["refused"] == "42501", refused


R10_INDEX_PLANT = ("CREATE INDEX r9_cover ON public.players (id); "
                   "UPDATE pg_catalog.pg_index SET indislive = false WHERE indexrelid = "
                   "(SELECT c.conindid FROM pg_catalog.pg_constraint c "
                   "WHERE c.conrelid = 'public.players'::pg_catalog.regclass AND c.contype = 'p');")
R10_INDEX_ONLY = "CREATE INDEX r9_cover ON public.players (id);"


async def _r10_pk_oid(dsn):
    conn = await _connect(dsn)
    try:
        return str(await conn.fetchval(
            "SELECT c.conindid::pg_catalog.oid FROM pg_catalog.pg_constraint c "
            "WHERE c.conrelid = 'public.players'::pg_catalog.regclass AND c.contype = 'p'"))
    finally:
        await conn.close()


def _r10_row_text(values):
    """A ROW text of field values (record_out's quoting for the values these
    cases carry)."""
    def q(v):
        if v is None:
            return ""
        if v == "" or any(ch in v for ch in ',()" ' + chr(92)):
            return '"' + v.replace(chr(92), chr(92) * 2).replace('"', '""') + '"'
        return v
    return "(" + ",".join(q(v) for v in values) + ")"


def _r10_identity_cases(chain, alone):
    """Report catalog_all.py:532, the binding itself, on the measured rows of
    the index-only control (round 9 explained a row by the KIND of any
    changed object). Built from players_pkey's own pg_index raw row in the
    clone's catalog, beside the added index r9_cover:
      in place: the row changed in a listed column (indisclustered) with
        players_pkey's own index object unchanged: unexplained; with that
        object changed too: explained (control);
      whole: the row added with no object of its identity: unexplained."""
    pk = asyncio.run(_r10_pk_oid(chain.dsn))
    mine = [r for r in alone["after"] if r[0] == "raw" and r[2] == "pg_index" and r[5][1] == pk]
    assert mine, ("no pg_index raw row of players_pkey", pk)
    obj = [r for r in alone["after"] if r[0] == "index" and r[4] == pk]
    assert len(obj) == 1, obj
    cols = ca.BODY_COLUMNS["pg_index"]
    k = cols.index("indisclustered")
    flipped = []
    for r in mine:
        f = ca.fields(r[3])
        assert ca.changed_columns("pg_index", r[3], _r10_row_text(f)) == [], (r[3], _r10_row_text(f))
        f[k] = "f" if f[k] == "t" else "t"
        flipped.append(r[:3] + (_r10_row_text(f),) + r[4:])
    assert ca.changed_columns("pg_index", mine[0][3], flipped[0][3]) == ["indisclustered"]
    base = alone["diff"]
    rows = len({(r[2], r[3], r[5]) for r in mine})   # one per row, whatever relations it names
    in_place = {"added": base["added"] + flipped, "removed": base["removed"] + mine}
    got = ca.unexplained(in_place)
    assert sorted((u[0], u[1]) for u in got) == sorted([("added", "pg_index")] * rows
                                                       + [("removed", "pg_index")] * rows), got
    control = {"added": in_place["added"] + obj, "removed": in_place["removed"]}
    assert ca.unexplained(control) == [], ca.unexplained(control)
    whole = {"added": base["added"] + mine, "removed": base["removed"]}
    got = ca.unexplained(whole)
    assert sorted((u[0], u[1]) for u in got) == [("added", "pg_index")] * rows, got
    print("r10 catalog_all.py:532 identity cases: in place %d unexplained, control 0, whole %d unexplained"
          % (2 * rows, rows))


def test_r10_n_catalog_all_532_explanation_bound_to_identity(chain):
    """An added index explains only its own rows (round 10, report
    catalog_all.py:532: round 9 explained every pg_index row by the KIND of
    an added object). The planted change of another index's indislive
    (superuser: a direct catalog UPDATE in the rolled-back transaction of a
    throwaway clone) is unexplained beside the added index; under the
    stand-in PostgreSQL refuses the UPDATE (42501). The index alone is
    explained (negative control)."""
    alone = asyncio.run(_measure(chain.dsn, R10_INDEX_ONLY))
    assert alone["refused"] is None and alone["ended"] is None, alone
    assert ca.unexplained(alone["diff"]) == [], ca.unexplained(alone["diff"])
    _r10_identity_cases(chain, alone)
    result = asyncio.run(_measure(chain.dsn, R10_INDEX_PLANT))
    print("r10 catalog_all.py:532 superuser %s: refused %s unexplained %s"
          % (chain.who["superuser"], result["refused"],
             ca.unexplained(result["diff"]) if result.get("diff") else None))
    if not chain.who["superuser"]:
        assert result["refused"] == "42501", result
        return
    assert result["refused"] is None and result["ended"] is None, result
    u = ca.unexplained(result["diff"])
    assert sorted(x[0] for x in u) == ["added", "removed"] and {x[1] for x in u} == {"pg_index"}, u


def test_r10_sweep_counts():
    """Ruling R9-A1 (E): the sites of each class in the four files of the
    lane, counted per file, equal the frozen counts (catalog_r10_sweep); a
    new site fails here until it is fixed or held with a reason."""
    import catalog_r10_sweep as sw
    got = {k: len(v) for k, v in sw.sweep(HERE).items()}
    assert got == sw.FROZEN, {k: (got.get(k), sw.FROZEN.get(k)) for k in set(got) | set(sw.FROZEN)
                              if got.get(k) != sw.FROZEN.get(k)}


def test_r10_routes_state_this_run(chain):
    """The measurer and its routes for the log of record (catalog_all.routes):
    rolpassword 'digest' under a superuser, else 'unmeasured' with
    pg_authid.rolpassword listed; the shared rows outside RESTRICT measured
    in every harness position, not between chain readings."""
    r = asyncio.run(_r10_routes())
    print("r10 routes: measurer %s superuser %s rolpassword %s; outside RESTRICT: %s; unmeasured: %s"
          % (r["measurer"], r["superuser"], r["rolpassword"], r["outside_restrict"], r["unmeasured"]))
    assert r["measurer"] == chain.who["admin_user"] and r["superuser"] == chain.who["superuser"], r
    assert r["rolpassword"] == ("digest" if r["superuser"] else "unmeasured"), r
    assert (("pg_authid", "rolpassword") in [(u[0], u[1]) for u in r["unmeasured"]]) == (not r["superuser"]), r
    # the digest route reads the stored value as its md5 and never the value
    q, rows = asyncio.run(_r10_authid_reading())
    if r["superuser"]:
        assert "pg_catalog.md5(t.rolpassword)" in q, q[:400]
    else:
        assert "rolpassword" not in q, q[:400]
    assert rows and not [x for x in rows if "SCRAM-SHA-256$" in x], len(rows)


async def _r10_outside_across_drop(db, program):
    """One REPEATABLE READ position on the admin database: outside() read,
    the position's program run, database <db> dropped by ANOTHER backend,
    outside() read again. (the plain set difference's catalogs,
    outside_diff()'s catalogs)."""
    conn = await asyncpg.connect(ADMIN)
    try:
        async with conn.transaction(isolation="repeatable_read"):
            before = await ca.outside(conn)
            if program:
                await conn.execute(program)
            await _drop_db(db)
            after = await ca.outside(conn)
            plain = sorted(ca.keys({"added": sorted(after - before), "removed": sorted(before - after)}))
            return plain, sorted(ca.keys(ca.outside_diff(before, after)))
    finally:
        await conn.close()


@pytest.mark.parametrize("program", ("", "ALTER DATABASE {other} CONNECTION LIMIT 7"))
def test_r10_outside_discounts_another_backends_drop_database(program):
    """PostgreSQL 16 DROP DATABASE marks the row invalid (datconnlimit -2) by
    an in-place update, visible inside the position's REPEATABLE READ
    snapshot; the record run of a5d71da0 read a concurrent lane's drop as the
    position's own 'SHARED:pg_database'. outside() leaves invalid rows out
    and outside_diff() discounts the removal that leaves; a change the
    position makes to another database's row (the second case, an ALTER
    DATABASE on a database it owns) is still reported."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    prefix = os.environ.get("D2_DB_PREFIX", "d2catalog")
    db = ("%s_inplace_%s_%d" % (prefix, stamp, os.getpid())).lower()
    other = ("%s_other_%s_%d" % (prefix, stamp, os.getpid())).lower()
    asyncio.run(_admin('CREATE DATABASE "%s"' % db))
    asyncio.run(_admin('CREATE DATABASE "%s"' % other))
    try:
        plain, got = asyncio.run(_r10_outside_across_drop(db, program.format(other='"%s"' % other)))
    finally:
        asyncio.run(_drop_db(db))
        asyncio.run(_drop_db(other))
    print("r10 outside across another backend's DROP DATABASE, program %r: set difference %s, "
          "outside_diff %s" % (program, plain, got))
    assert plain == ["pg_database"], plain
    assert got == (["pg_database"] if program else []), got


# --- the files outside the chain --------------------------------------------


def test_zz_rollback_and_resume_files_do_not_change_mail_inbox_rev(chain):
    """Every other file in backend/sql (rollback_*, resume_*), applied in
    order with psql to a copy of the chain database, each after its own
    d2_seed prerequisites (if any): every file runs to its end (rc 0; ruling
    R7-A1's class, no declared refusals) and none changes mail_inbox_rev."""
    _numbered, aux = _files()
    assert aux, "no rollback or resume files found"
    # newest first, as rollbacks are undone (rollback_399 before rollback_398 ...)
    aux = sorted(aux, key=lambda n: (re.sub(r"\D", "", n.split("_")[1]) or "0", n), reverse=True)
    copy = (chain.db + "_aux")[:63]
    asyncio.run(_admin('CREATE DATABASE "%s" TEMPLATE "%s"' % (copy, chain.db)))
    dsn = _dsn(copy)
    try:
        prev, steps, rows = asyncio.run(_snap(dsn)), [], []
        for name in aux:
            for st in d2_seed.steps_for(name):
                pre = asyncio.run(_prereq(dsn, st))
                rows.append({"file": "<prereq %s>" % name, "rc": pre["rc"], "sqlstate": pre["sqlstate"],
                             "error": pre["error"], "touched": [], "commands": pre["commands"]})
            outcome = cd.apply_file(chain.psql, dsn, _blob_file(chain.out, name))
            assert outcome["rc"] in (0, 3), (name, outcome)
            cur = asyncio.run(_snap(dsn))
            d = cd.diff(prev, cur)
            prev = cur
            steps.append((name, d))
            rows.append({"file": name, "rc": outcome["rc"], "sqlstate": outcome["sqlstate"],
                         "error": outcome["error"], "touched": cd.touched(d), "raw": ca.keys(d),
                         "unexplained": ca.unexplained(d), "cluster": ca.cluster_rows(d),
                         "internal_not_enabled": asyncio.run(_internal_not_enabled(dsn)),
                         "commands": outcome["commands"]})
        _write(chain.out, "aux_files.json", json.dumps(rows, indent=1))
        incomplete = [(r["file"], r["sqlstate"], r["error"]) for r in rows if r["rc"] != 0]
        assert incomplete == [], incomplete
        assert cd.changers(steps, MAIL) == []
        # ruling R8-A1 (E1): every catalog row these files change is
        # accounted for by an object change, and none is a cluster row
        assert [(r["file"], r["unexplained"]) for r in rows if r.get("unexplained")] == []
        assert [(r["file"], r["cluster"]) for r in rows if r.get("cluster")] == []
        assert [(r["file"], r["internal_not_enabled"]) for r in rows if r.get("internal_not_enabled")] == []
        assert not [(r["file"], c) for r in rows for c in r["commands"] if "mail_inbox_rev" in c[2]]
    finally:
        asyncio.run(_drop_db(copy))
