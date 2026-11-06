"""Ruling FOUR-R11-A17: ONE window over test_r7_catalog_diff_pg.py (the
catalog diff), which imports the fixture below as its own module-scoped
autouse fixture. The tables live here; the module keeps the import, the
plant functions and the controls.

The window is ro_census.OpenRecorder in its set-aware mode (freeze_set). The
set: the admin DSN (CF_TEST_PG_DSN) at the admin sites of SITES, and the
databases a maker of MAKERS made in this run (CREATE DATABASE through any
connection), on the admin DSN's server and user, at the clone sites of
SITES. The rule by which a site is taken: the co_qualname of the innermost
frame whose code file is test_r7_catalog_diff_pg.py; a maker: the same,
skipping PLUMBING. Every subprocess.run start is checked before it starts:
its command line and environment (the libpq variables the URI does not
override must be absent, PGCLIENTENCODING may be UTF8), its target (a made
database, never the admin DSN), then its site (STARTS). For each member, the
first open (asyncpg) and the first start (psql, same DSN and environment)
read database, server port and system identifier, which must equal the
member and the cluster the run names at its start (read through the admin
DSN before the freeze). test_r11_rec_pg shows by census that SITES, MAKERS
and STARTS are the module's complete lists.

A run of the WHOLE module asserts the counts per site (OPEN_COUNTS,
START_COUNTS, frozen from a whole run on seat-4: admin scr_gate, CREATEDB, not
a superuser, psql and pg_dump 16.15); a selection asserts the set and the
sites, reports its counts without asserting them and says that it is
partial. With D2_REUSE_DB set the chain is not built in the run: the window
fails, such a run is not one the packet cites.
"""

import asyncio
import contextlib
import json
import os

import pytest

import ro_census

SITES = {
    # the admin DSN: every function holding asyncpg.connect(ADMIN)
    "_template_problem": "admin", "_clone_with_oid": "admin", "_admin": "admin",
    "_whoami": "admin", "_fetchval": "admin", "_r9_databases": "admin",
    "_r10_settings": "admin", "_r10_authid_reading": "admin", "_r10_routes": "admin",
    "_r10_outside_across_drop": "admin", "_r10_inplace_bound": "admin",
    # a database the run made: asyncpg.connect(dsn), create_async_engine,
    # catalog_position.check (its monitor open, catalog_position.py)
    "_probe_problems": "clone", "_connect": "clone", "_orm": "clone",
    "_position_kept": "clone", "_measure_in": "clone", "_language": "clone",
}
MAKERS = frozenset({
    "chain", "_build.<locals>.own_clone", "route_db", "m9_db", "r10_clone", "_measure",
    "test_id_moving_seeds_are_guarded_by_their_foreign_keys",
    "test_m11_alter_behind_the_former_refusal_is_measured",
    "test_migrations_are_applied_from_the_object_store",
    "test_r9_rollback_harnesses_report_a_program_that_ends_them",
    "test_r10_outside_discounts_another_backends_drop_database",
    "test_r10_outside_inplace_bound_refusals",
    "test_zz_rollback_and_resume_files_do_not_change_mail_inbox_rev",
})
PLUMBING = frozenset({"_admin", "_clone", "_clone_with_oid", "_scratch_clone"})
STARTS = {
    "_git": "git", "_blobs": "git",
    "_build": "pg_dump", "_build.<locals>.record": "pg_dump", "_route_run": "pg_dump",
    "_build.<locals>.run": "psql", "_apply_tail": "psql",
    "test_migrations_are_applied_from_the_object_store": "psql",
    "test_zz_rollback_and_resume_files_do_not_change_mail_inbox_rev": "psql",
}
# the controls' own sites and makers: off the lists above by construction
PLANT_SITES = {"_r11_plant_admin_off_list": "admin"}
PLANT_MAKERS = frozenset({"_r11_plant_unlisted_maker"})
PLANT_STARTS = {"test_r11_cat_refuses_a_start_outside_the_set": "pg_dump",
                "test_r11_cat_refuses_a_start_whose_environment_is_not_stated": "pg_dump"}
ENV_ALLOWED = {"PGCLIENTENCODING": "UTF8"}
# frozen from the whole-module run r11-rec-cat2-whole (seat-4, 648f12d5: 158
# passed, 2 skipped, no violation; 1454 opens, 889 starts). A listed site
# absent here opened nothing in that run (catalog_position.check opens its
# monitor only when the session's own connection raises InterfaceError,
# catalog_position.py:116-119; no measured program in that run did so).
OPEN_COUNTS = {
    "_admin": 315, "_clone_with_oid": 2, "_connect": 1114, "_fetchval": 6, "_orm": 1,
    "_probe_problems": 2, "_r10_authid_reading": 1, "_r10_inplace_bound": 1,
    "_r10_outside_across_drop": 2, "_r10_routes": 1, "_r10_settings": 2, "_r9_databases": 1,
    "_template_problem": 3, "_whoami": 3}
START_COUNTS = {
    "_apply_tail": 2, "_blobs": 1, "_build": 1, "_build.<locals>.record": 426,
    "_build.<locals>.run": 377, "_git": 2, "_route_run": 56,
    "test_migrations_are_applied_from_the_object_store": 2,
    "test_zz_rollback_and_resume_files_do_not_change_mail_inbox_rev": 22}

REUSE_REFUSAL = ("D2_REUSE_DB is set: the chain was not built in this run, so the run is not "
                 "one the packet cites (ruling FOUR-R11-A17 (g))")


async def _cluster(admin):
    import asyncpg
    conn = await asyncpg.connect(admin)
    try:
        row = await conn.fetchrow(ro_census.IDENTITY_LINE_SQL)
        return {"database": row["database"], "port": row["port"],
                "system_identifier": str(row["system_identifier"])}
    finally:
        await conn.close()


def partial_reasons(request):
    """Why this session is not a run of the whole module ([] when it is)."""
    cfg, o = request.config, request.config.option
    why = []
    for attr, flag in (("keyword", "-k"), ("markexpr", "-m"), ("deselect", "--deselect"),
                       ("lf", "--lf"), ("stepwise", "--sw")):
        if getattr(o, attr, None):
            why.append(flag)
    if request.session.shouldfail or request.session.shouldstop:
        why.append("the session stopped early")
    here = os.path.normcase(os.path.abspath(request.module.__file__))
    base = str(cfg.invocation_params.dir)
    for a in cfg.args:
        path, sep, _rest = a.partition("::")
        if sep and os.path.normcase(os.path.abspath(os.path.join(base, path))) == here:
            why.append("a node id of the module (%s)" % a)
    return why


def window_refusal(report, partial, reuse):
    """None when the window held, else the message the run fails with."""
    if reuse:
        return REUSE_REFUSAL
    if not report["active"] or not report["starts_active"]:
        return "the catalog window was not active at its thaw: %r" % (
            {k: report[k] for k in ("active", "starts_active")},)
    if report["violations"]:
        return "the catalog window broke the open bound: %r" % (report["violations"],)
    if partial:
        return None
    if report["opens"] == 0:
        return "the catalog window recorded no open in a whole-module run"
    if OPEN_COUNTS is None or START_COUNTS is None:
        return ("the count table is not frozen; measured opens per site %s, starts per site %s"
                % (json.dumps(report["open_counts"]), json.dumps(report["start_counts"])))
    if report["open_counts"] != OPEN_COUNTS or report["start_counts"] != START_COUNTS:
        return "the whole-module run's counts per site differ from the frozen table: %r" % ({
            "opens": _delta(report["open_counts"], OPEN_COUNTS),
            "starts": _delta(report["start_counts"], START_COUNTS)},)
    return None


def _delta(got, want):
    return {k: (got.get(k), want.get(k)) for k in sorted(set(got) | set(want), key=str)
            if got.get(k) != want.get(k)}


def window_lines(cluster, report, partial):
    head = ("R11-CAT-WINDOW PARTIAL RUN (%s): the set and the sites asserted, the counts "
            "reported, not asserted" % ", ".join(partial)) if partial else \
        "R11-CAT-WINDOW whole-module run: the set, the sites and the counts per site asserted"
    lines = [head, "R11-CAT-RUN cluster %s" % json.dumps(cluster, sort_keys=True)]
    for line in report["id_lines"]:
        lines.append("R11-CAT-ID " + json.dumps(line, sort_keys=True, default=str))
    lines += ["R11-CAT-COUNTS opens " + json.dumps(report["open_counts"], default=str),
              "R11-CAT-COUNTS starts " + json.dumps(report["start_counts"], default=str),
              "R11-CAT-MAKERS " + json.dumps(report["makers"], default=str),
              "R11-CAT-MEMBERS " + json.dumps(report["members"], default=str),
              "R11-CAT-ENV libpq variables present at a start: %s" % report["env_present"],
              "R11-CAT-TOTALS " + json.dumps({k: report[k] for k in (
                  "opens", "starts", "built", "planted", "active", "starts_active")}),
              "R11-CAT-VIOLATIONS " + json.dumps(report["violations"], default=str)]
    return lines


def say(request, lines):
    """Write lines to the terminal past the capture (the seat admits no -s)."""
    pm = request.config.pluginmanager
    capman, tr = pm.getplugin("capturemanager"), pm.getplugin("terminalreporter")
    if tr is None:
        return
    with capman.global_and_fixture_disabled() if capman else contextlib.nullcontext():
        tr.write_line("")
        for line in lines:
            tr.write_line(line)


@pytest.fixture(scope="module", autouse=True, name="_cat_open_window")
def _cat_open_window(request):
    mod = request.module
    if not mod.ADMIN:
        pytest.fail("CF_TEST_PG_DSN is unset: the catalog window has no admin DSN to freeze")
    psql = mod.cd.client("D2_TEST_PSQL", "psql")
    pg_dump = mod.cd.client("D2_TEST_PG_DUMP", "pg_dump")
    cluster = asyncio.run(_cluster(mod.ADMIN))
    rec = ro_census.OpenRecorder()
    rec.freeze_set(mod.ADMIN, SITES, MAKERS, PLUMBING, mod.__file__, cluster, STARTS,
                   {"psql": psql, "pg_dump": pg_dump, "git": "git"}, psql, ENV_ALLOWED)
    try:
        yield rec
        report = rec.set_report()
    finally:
        rec.thaw()
    partial = partial_reasons(request)
    say(request, window_lines(cluster, report, partial))
    refusal = window_refusal(report, partial, os.environ.get("D2_REUSE_DB"))
    assert refusal is None, refusal
