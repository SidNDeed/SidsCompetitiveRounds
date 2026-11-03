"""The covered set of the read-only bound and its role harness (ruling
REHEARSAL-FOUR-R7-A1 M1).

COVERED is the frozen list of every SQL position the S analysis (closed_walk
sql_tokens / sql_kind / sql_text / execute_kind / local_sql, through
Bindings.execute_kind) classifies as 'read' inside a span the a1 walk or the
gate walk walks, enumerated mechanically at 3130bb9d by the ro_spy plugin
while those walks ran (test_r8_ro_covered_pg re-enumerates and asserts
equality both ways). WRITERS is the same enumeration's 'lock' positions:
S itself calls them locks, and a lock is a writer, so none is in the
read-only claim. Each entry: (walk, file, line, end_line, span).

The harness: a role engine whose every new connection asserts SELECT
current_user, session_user equals the role before any statement, and a
session class that records, for every execute the production code issues,
the production frame's file and line (the first frame under backend/api)
and the outcome ('ok' or the SQLSTATE).
"""

import json
import os
import subprocess
import sys
import tempfile

from sqlalchemy import event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

HERE = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.normcase(os.path.normpath(os.path.join(HERE, "..", "api")))

# The two walks, as pytest node ids relative to backend/tests: the tests
# whose walks the enumeration runs (every test of the a1 file and the gate
# file's source walks; the gate file's live cases open a database and walk
# nothing).
A1_WALK = ("test_a1_identity_formation.py",)
GATE_WALK = (
    "test_match_hold_admission_gate_pg.py::test_h3_every_admission_site_uses_shared_gate_recheck_and_rollback",
    "test_match_hold_admission_gate_pg.py::test_h3_direct_refusal_is_the_claims_first_write",
    "test_match_hold_admission_gate_pg.py::test_h3_real_hold_replay_is_read_and_classified",
    "test_match_hold_admission_gate_pg.py::test_r7_prior_findings_are_refused",
    "test_match_hold_admission_gate_pg.py::test_r7_grammar_covers_every_walked_span_and_body",
)

# Frozen at 3130bb9d from the ro_spy enumeration of both walks (35 positions).
COVERED = (
    ('a1', 'main.py', 16828, 16828, '_lease_admission_gate'),
    ('a1', 'main.py', 16868, 16868, '_lease_admission_gate'),
    ('a1', 'main.py', 16871, 16871, '_lease_admission_gate'),
    ('a1', 'main.py', 16886, 16891, '_lease_admission_gate'),
    ('a1', 'main.py', 16897, 16909, '_lease_admission_gate'),
    ('a1', 'main.py', 16924, 16934, '_lease_admission_gate'),
    ('a1', 'main.py', 17433, 17436, '_lease_live_claim_strict'),
    ('a1', 'main.py', 18718, 18721, '_group_region'),
    ('a1', 'main.py', 20479, 20481, 'queue_poll'),
    ('a1', 'main.py', 20482, 20484, 'queue_poll'),
    ('a1', 'main.py', 49791, 49794, 'team_queue_poll'),
    ('a1', 'main.py', 49822, 49824, 'team_queue_poll'),
    ('a1', 'main.py', 49946, 49950, 'team_queue_poll'),
    ('a1', 'main.py', 49951, 49952, 'team_queue_poll'),
    ('a1', 'main.py', 50001, 50003, 'team_queue_poll'),
    ('a1', 'main.py', 51115, 51119, '_reconcile_team_series_bets'),
    ('a1', 'main.py', 51761, 51763, '_team_lock_family_pick'),
    ('a1', 'main.py', 51793, 51793, '_team_lock_family_pick'),
    ('a1', 'main.py', 51859, 51861, '_team_resolve_live_family'),
    ('a1', 'main.py', 53768, 53770, 'ovt_queue_poll'),
    ('a1', 'main.py', 53808, 53811, 'ovt_queue_poll'),
    ('a1', 'main.py', 56363, 56368, '_rules_members'),
    ('a1', 'main.py', 57195, 57201, '_player_body_color'),
    ('a1', 'main.py', 65184, 65186, '_ffa_queue_poll_inner'),
    ('a1', 'main.py', 65206, 65208, '_ffa_queue_poll_inner'),
    ('a1', 'main.py', 65249, 65253, '_ffa_queue_poll_inner'),
    ('a1', 'main.py', 65263, 65265, '_ffa_queue_poll_inner'),
    ('a1', 'main.py', 73522, 73525, '_service_player_uuids'),
    ('a1', 'match_hold.py', 381, 384, '_hold_latch'),
    ('a1', 'match_report_window.py', 87, 89, 'series_holds'),
    ('a1', 'tournaments.py', 301, 307, '_region_candidate_volumes'),
    ('gate', 'main.py', 63623, 63626, '_rdm_row'),
    ('gate', 'main.py', 63709, 63712, '_rdm_claim'),
    ('gate', 'match_hold.py', 243, 243, '_ctx_now'),
    ('gate', 'match_hold.py', 818, 821, '_open_attempt_row'),
)

# The same enumeration's 'lock' positions (14): writers, never in the claim.
WRITERS = (
    ('a1', 'main.py', 16390, 16391, '_lock_queue_rows_ordered'),
    ('a1', 'main.py', 16393, 16394, '_lock_queue_rows_ordered'),
    ('a1', 'main.py', 16396, 16397, '_lock_queue_rows_ordered'),
    ('a1', 'main.py', 16399, 16400, '_lock_queue_rows_ordered'),
    ('a1', 'main.py', 16839, 16849, '_lease_admission_gate'),
    ('a1', 'main.py', 16851, 16853, '_lease_admission_gate'),
    ('a1', 'main.py', 16857, 16859, '_lease_admission_gate'),
    ('a1', 'main.py', 17406, 17409, '_lock_snapshot_rows'),
    ('a1', 'main.py', 51089, 51093, '_reconcile_team_series_bets'),
    ('a1', 'main.py', 51112, 51114, '_reconcile_team_series_bets'),
    ('a1', 'main.py', 51703, 51705, '_team_quartet_lock'),
    ('a1', 'main.py', 51768, 51783, '_team_lock_family_pick'),
    ('gate', 'main.py', 63719, 63721, '_rdm_claim'),
    ('gate', 'match_hold.py', 569, 569, '_hold_row'),
)


# Measured (test_r8_ro_covered_pg, under scr_seat_ro on a granted clone of
# scr_seat_ro_tmpl): 'ok', or ('not reached', <the statement that the role
# refused first on the driven path>, SQLSTATE). A 'not reached' position
# leaves the read-only claim (a QUESTION in the hand-back).
OUTCOME = {
    ('a1', 'main.py', 16828, 16828, '_lease_admission_gate'): 'ok',
    ('a1', 'main.py', 16868, 16868, '_lease_admission_gate'): ('not reached', 'main.py:16851', '25006'),
    ('a1', 'main.py', 16871, 16871, '_lease_admission_gate'): ('not reached', 'main.py:16851', '25006'),
    ('a1', 'main.py', 16886, 16891, '_lease_admission_gate'): ('not reached', 'main.py:16851', '25006'),
    ('a1', 'main.py', 16897, 16909, '_lease_admission_gate'): ('not reached', 'main.py:16851', '25006'),
    ('a1', 'main.py', 16924, 16934, '_lease_admission_gate'): ('not reached', 'main.py:16851', '25006'),
    ('a1', 'main.py', 17433, 17436, '_lease_live_claim_strict'): 'ok',
    ('a1', 'main.py', 18718, 18721, '_group_region'): 'ok',
    ('a1', 'main.py', 20479, 20481, 'queue_poll'): ('not reached', 'main.py:19936', '25006'),
    ('a1', 'main.py', 20482, 20484, 'queue_poll'): ('not reached', 'main.py:19936', '25006'),
    ('a1', 'main.py', 49791, 49794, 'team_queue_poll'): ('not reached', 'main.py:16393', '25006'),
    ('a1', 'main.py', 49822, 49824, 'team_queue_poll'): ('not reached', 'main.py:16393', '25006'),
    ('a1', 'main.py', 49946, 49950, 'team_queue_poll'): ('not reached', 'main.py:16393', '25006'),
    ('a1', 'main.py', 49951, 49952, 'team_queue_poll'): ('not reached', 'main.py:16393', '25006'),
    ('a1', 'main.py', 50001, 50003, 'team_queue_poll'): ('not reached', 'main.py:16393', '25006'),
    ('a1', 'main.py', 51115, 51119, '_reconcile_team_series_bets'): ('not reached', 'main.py:51089', '25006'),
    ('a1', 'main.py', 51761, 51763, '_team_lock_family_pick'): 'ok',
    ('a1', 'main.py', 51793, 51793, '_team_lock_family_pick'): ('not reached', 'main.py:51768', '25006'),
    ('a1', 'main.py', 51859, 51861, '_team_resolve_live_family'): ('not reached', 'main.py:51768', '25006'),
    ('a1', 'main.py', 53768, 53770, 'ovt_queue_poll'): ('not reached', 'main.py:16396', '25006'),
    ('a1', 'main.py', 53808, 53811, 'ovt_queue_poll'): ('not reached', 'main.py:16396', '25006'),
    ('a1', 'main.py', 56363, 56368, '_rules_members'): 'ok',
    ('a1', 'main.py', 57195, 57201, '_player_body_color'): 'ok',
    ('a1', 'main.py', 65184, 65186, '_ffa_queue_poll_inner'): ('not reached', 'main.py:17406', '25006'),
    ('a1', 'main.py', 65206, 65208, '_ffa_queue_poll_inner'): ('not reached', 'main.py:17406', '25006'),
    ('a1', 'main.py', 65249, 65253, '_ffa_queue_poll_inner'): ('not reached', 'main.py:17406', '25006'),
    ('a1', 'main.py', 65263, 65265, '_ffa_queue_poll_inner'): ('not reached', 'main.py:17406', '25006'),
    ('a1', 'main.py', 73522, 73525, '_service_player_uuids'): 'ok',
    ('a1', 'match_hold.py', 381, 384, '_hold_latch'): ('not reached', 'match_hold.py:380', '25006'),
    ('a1', 'match_report_window.py', 87, 89, 'series_holds'): 'ok',
    ('a1', 'tournaments.py', 301, 307, '_region_candidate_volumes'): 'ok',
    ('gate', 'main.py', 63623, 63626, '_rdm_row'): 'ok',
    ('gate', 'main.py', 63709, 63712, '_rdm_claim'): 'ok',
    ('gate', 'match_hold.py', 243, 243, '_ctx_now'): 'ok',
    ('gate', 'match_hold.py', 818, 821, '_open_attempt_row'): 'ok',
}

# Measured for the writer positions: the role's refusal (25006), a position
# the driven path did not reach, or 'ok' where the role cannot refuse the
# statement (a transaction-local set_config, an advisory transaction lock):
# those two are writers by S whose bound the role does not measure.
WRITER_OUTCOME = {
    ('a1', 'main.py', 16390, 16391, '_lock_queue_rows_ordered'): '25006',
    ('a1', 'main.py', 16393, 16394, '_lock_queue_rows_ordered'): '25006',
    ('a1', 'main.py', 16396, 16397, '_lock_queue_rows_ordered'): '25006',
    ('a1', 'main.py', 16399, 16400, '_lock_queue_rows_ordered'): '25006',
    ('a1', 'main.py', 16839, 16849, '_lease_admission_gate'): 'ok',
    ('a1', 'main.py', 16851, 16853, '_lease_admission_gate'): '25006',
    ('a1', 'main.py', 16857, 16859, '_lease_admission_gate'): ('not reached', 'main.py:16851', '25006'),
    ('a1', 'main.py', 17406, 17409, '_lock_snapshot_rows'): '25006',
    ('a1', 'main.py', 51089, 51093, '_reconcile_team_series_bets'): '25006',
    ('a1', 'main.py', 51112, 51114, '_reconcile_team_series_bets'): ('not reached', 'main.py:51089', '25006'),
    ('a1', 'main.py', 51703, 51705, '_team_quartet_lock'): 'ok',
    ('a1', 'main.py', 51768, 51783, '_team_lock_family_pick'): '25006',
    ('gate', 'main.py', 63719, 63721, '_rdm_claim'): '25006',
    ('gate', 'match_hold.py', 569, 569, '_hold_row'): '25006',
}

def enumerate_positions(python=sys.executable, timeout=7200):
    """Run both walks under the ro_spy plugin (a subprocess pytest in this
    directory) and return (positions, ambiguous, synthetic_count, rc):
    positions the set of (walk, file, line, end_line, span, kind) of every
    'real' record whose module is under backend/api and whose kind S gave
    is 'read' or 'lock'; ambiguous the 'ambiguous' records under
    backend/api."""
    fd, out = tempfile.mkstemp(prefix="ro_spy_", suffix=".json")
    os.close(fd)
    env = dict(os.environ, RO_SPY_OUT=out)
    env.pop("PYTEST_ADDOPTS", None)
    try:
        proc = subprocess.run(
            [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "ro_spy"]
            + list(A1_WALK) + list(GATE_WALK),
            cwd=HERE, env=env, capture_output=True, text=True, timeout=timeout)
        with open(out, encoding="utf-8") as fh:
            data = json.load(fh)
    finally:
        os.unlink(out)
    positions, ambiguous, synthetic = set(), [], 0
    for r in data["records"]:
        test = r["test"] or ""
        walk = "gate" if test.startswith("test_match_hold_admission_gate_pg") else "a1"
        path = os.path.normcase(os.path.normpath(r["path"] or ""))
        under_api = path.startswith(API_DIR + os.sep)
        if r["status"] == "synthetic":
            synthetic += 1
            continue
        if r["status"] == "ambiguous":
            if under_api:
                ambiguous.append(r)
            continue
        if under_api and r["kind"] in ("read", "lock"):
            positions.add((walk, os.path.basename(path), r["line"], r["end"], r["span"],
                           r["kind"]))
    return positions, ambiguous, synthetic, (proc.returncode, proc.stdout[-2000:])


WHO_SQL = "SELECT current_user, session_user"


class IdentityError(AssertionError):
    pass


def role_engine(dsn, schema, expect, checked):
    """A NullPool engine on `dsn` with search_path `schema`; every new
    connection asserts its identity is `expect` (appending to `checked`)."""
    engine = create_async_engine(
        dsn.replace("postgresql://", "postgresql+asyncpg://"), poolclass=NullPool,
        connect_args={"server_settings": {"search_path": '"%s"' % schema}})

    @event.listens_for(engine.sync_engine, "connect")
    def _who(dbapi_conn, _rec):
        row = dbapi_conn.run_async(lambda c: c.fetchrow(WHO_SQL))
        got = (row[0], row[1])
        if got != (expect, expect):
            raise IdentityError(
                "a covered connection runs as current_user=%s session_user=%s, "
                "not as %s" % (got[0], got[1], expect))
        checked.append(got)

    return engine


def _site():
    f = sys._getframe(2)
    while f is not None:
        path = os.path.normcase(os.path.normpath(f.f_code.co_filename))
        if path.startswith(API_DIR + os.sep):
            return os.path.basename(path), f.f_lineno
        f = f.f_back
    return None, None


def _sqlstate(exc):
    for e in (exc, getattr(exc, "orig", None),
              getattr(getattr(exc, "orig", None), "__cause__", None)):
        s = getattr(e, "sqlstate", None)
        if isinstance(s, str) and len(s) == 5:
            return s
    return None


class RecordingSession(AsyncSession):
    """Every execute records (file, line, outcome) in self.info['log']."""

    async def execute(self, statement, params=None, **kw):
        site = _site()
        log = self.info.setdefault("log", [])
        try:
            res = await super().execute(statement, params, **kw)
        except DBAPIError as e:
            log.append((site[0], site[1], _sqlstate(e) or "error"))
            raise
        log.append((site[0], site[1], "ok"))
        return res


def role_sessionmaker(engine):
    return async_sessionmaker(engine, class_=RecordingSession, expire_on_commit=False)


def outcome_at(log, entry):
    """The outcomes recorded at the position `entry` (its file and line
    span)."""
    _walk, f, line, end, _span = entry
    return [o for (lf, ll, o) in log if lf == f and ll is not None and line <= ll <= end]
