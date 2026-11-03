"""The covered set of the read-only bound and its role harness (ruling
REHEARSAL-FOUR-R7-A1 M1).

COVERED is the frozen list of every SQL position the (since retired) S
analysis classified as 'read' inside a span the a1 walk or the gate walk
walks, enumerated mechanically at 3130bb9d by the ro_spy plugin while those
walks ran. WRITERS is the same enumeration's 'lock' positions: a lock is a
writer, so none is in the read-only claim. Each entry: (walk, file, line,
end_line, span). Round 8 (M1): the walks classify an execute by a frozen
lookup over these tables (an execute reads only at a COVERED position whose
OUTCOME is 'ok'); test_r8_ro_covered_pg re-enumerates every position the
walks ask the lookup about and asserts that set equals COVERED and WRITERS
together, both ways.

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

from sqlalchemy import event, text
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
    ('a1', 'main.py', 16871, 16871, '_lease_admission_gate'): ('ok-under-grant', ('UPDATE players',), 0, ('not reached', 'main.py:16851', '25006')),
    ('a1', 'main.py', 16886, 16891, '_lease_admission_gate'): ('ok-under-grant', ('UPDATE players',), 0, ('not reached', 'main.py:16851', '25006')),
    ('a1', 'main.py', 16897, 16909, '_lease_admission_gate'): ('ok-under-grant', ('UPDATE players',), 0, ('not reached', 'main.py:16851', '25006')),
    ('a1', 'main.py', 16924, 16934, '_lease_admission_gate'): ('ok-under-grant', ('UPDATE players',), 0, ('not reached', 'main.py:16851', '25006')),
    ('a1', 'main.py', 17433, 17436, '_lease_live_claim_strict'): 'ok',
    ('a1', 'main.py', 18718, 18721, '_group_region'): 'ok',
    ('a1', 'main.py', 20479, 20481, 'queue_poll'): ('not reached', 'main.py:19936', '25006'),
    ('a1', 'main.py', 20482, 20484, 'queue_poll'): ('not reached', 'main.py:19936', '25006'),
    ('a1', 'main.py', 49791, 49794, 'team_queue_poll'): ('not reached', 'main.py:16393', '25006'),
    ('a1', 'main.py', 49822, 49824, 'team_queue_poll'): ('not reached', 'main.py:16393', '25006'),
    ('a1', 'main.py', 49946, 49950, 'team_queue_poll'): ('not reached', 'main.py:16393', '25006'),
    ('a1', 'main.py', 49951, 49952, 'team_queue_poll'): ('not reached', 'main.py:16393', '25006'),
    ('a1', 'main.py', 50001, 50003, 'team_queue_poll'): ('ok-under-grant', ('UPDATE team_queue',), 0, ('not reached', 'main.py:16393', '25006')),
    ('a1', 'main.py', 51115, 51119, '_reconcile_team_series_bets'): ('not reached', 'main.py:51089', '25006'),
    ('a1', 'main.py', 51761, 51763, '_team_lock_family_pick'): 'ok',
    ('a1', 'main.py', 51793, 51793, '_team_lock_family_pick'): ('ok-under-grant', ('UPDATE team_series',), 0, ('not reached', 'main.py:51768', '25006')),
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
    ('a1', 'match_hold.py', 381, 384, '_hold_latch'): ('ok-under-grant', ('UPDATE team_series',), 0, ('not reached', 'match_hold.py:380', '25006')),
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
# Ruling R-A: every WRITERS position answers 'lock' in the walks' lookup,
# and each lock moves to the bound measured here: refused under the role
# (25006) for the 10 reached (16390, 16393, 16396, 16399, 16851, 17406,
# 51089, 51768, 63719, match_hold.py:569); not reached for 16857 (after
# 16851) and 51112 (after 51089); and for main.py:16839 (a transaction-local
# set_config of lock_timeout) and main.py:51703 (pg_advisory_xact_lock),
# 'ok' under the role, so their bound is the walk's lock rule alone (a
# QUESTION for the reviewer).
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

# Ruling R-C: the 28 execute positions the walks visit that are in neither
# table. Each answers 'write' (the conservative default, no bound needed).
# Evidence that the retired S analysis answered 'write' at each: ro's
# baseline spy records at 3130bb9d (RF/r8/ro/spy-a1.json, spy-gate.json;
# main.py and match_hold.py unchanged at these lines since) hold only
# 'write' for every one; the visited set is the round-8 enumeration
# (RF/r8/sr/enum-sr.json at 0ef7ccbf).
VISITED_WRITES = (
    ('a1', 'main.py', 4342, 4346, '_team_clear_dc_fallback_marker'),
    ('a1', 'main.py', 16958, 16978, '_lease_acquire'),
    ('a1', 'main.py', 20525, 20533, 'queue_poll'),
    ('a1', 'main.py', 28339, 28341, '_credit_bet_fighter_tax'),
    ('a1', 'main.py', 37851, 37855, '_return_stake_exactly'),
    ('a1', 'main.py', 50104, 50118, 'team_queue_poll'),
    ('a1', 'main.py', 50137, 50145, 'team_queue_poll'),
    ('a1', 'main.py', 50148, 50167, 'team_queue_poll'),
    ('a1', 'main.py', 51136, 51141, '_reconcile_team_series_bets'),
    ('a1', 'main.py', 51144, 51147, '_reconcile_team_series_bets'),
    ('a1', 'main.py', 51153, 51155, '_reconcile_team_series_bets'),
    ('a1', 'main.py', 51821, 51826, '_team_lock_family_pick'),
    ('a1', 'main.py', 51911, 51922, '_team_relock_existing_series'),
    ('a1', 'main.py', 51931, 51953, '_team_relock_existing_series'),
    ('a1', 'main.py', 51960, 51962, '_team_relock_existing_series'),
    ('a1', 'main.py', 53839, 53846, 'ovt_queue_poll'),
    ('a1', 'main.py', 53852, 53857, 'ovt_queue_poll'),
    ('a1', 'main.py', 57268, 57274, '_stamp_team_series_colors'),
    ('a1', 'main.py', 65280, 65288, '_ffa_queue_poll_inner'),
    ('a1', 'main.py', 65290, 65296, '_ffa_queue_poll_inner'),
    ('a1', 'match_hold.py', 380, 380, '_hold_latch'),
    ('gate', 'main.py', 61254, 61266, '_asm_deferred_departure'),
    ('gate', 'main.py', 61269, 61271, '_asm_deferred_departure'),
    ('gate', 'main.py', 61272, 61274, '_asm_deferred_departure'),
    ('gate', 'main.py', 63338, 63340, '_rdm_attempt'),
    ('gate', 'main.py', 63439, 63443, '_rdm_end_hold'),
    ('gate', 'main.py', 63448, 63452, '_rdm_end_hold'),
    ('gate', 'main.py', 63454, 63459, '_rdm_end_hold'),
)


def green(outcome):
    """Whether a COVERED position's OUTCOME admits it as a read: 'ok' under
    the read-only role, or ('ok-under-grant', grants, delta) measured with
    the path's refusing statements granted and a zero write delta around the
    position (ruling R-B)."""
    return outcome == "ok" or (isinstance(outcome, tuple) and outcome[0] == "ok-under-grant"
                               and outcome[2] == 0)


def lookup_table():
    """The walks' frozen lookup table (ruling R-A): {(file, line, end):
    'read' | 'lock'}; 'lock' for every WRITERS position, 'read' for every
    COVERED position whose OUTCOME is green. An absent position is a write."""
    table = {e[1:4]: "lock" for e in WRITERS}
    table.update({e[1:4]: "read" for e in COVERED if green(OUTCOME[e])})
    return table


def role_outcome(entry):
    """A COVERED position's outcome under the read-only role itself: OUTCOME,
    or, for a position read under a grant (ruling R-B), the role outcome it
    carries as its last element."""
    o = OUTCOME[entry]
    return o[3] if isinstance(o, tuple) and o[0] == "ok-under-grant" else o


# Ruling R-B: the grant run's measured outcome at every position the role
# did not reach that stays a write (not reached, refused, or a nonzero
# delta under its grants): the reason, as measured.
GRANT_OUTCOME = {
    ('a1', 'main.py', 16868, 16868, '_lease_admission_gate'):
        ('not reached under grant', ('UPDATE players',), None),
    ('a1', 'main.py', 20479, 20481, 'queue_poll'):
        ('not reached under grant', ('DELETE queue_blocks',), 'main.py:19936 42501'),
    ('a1', 'main.py', 20482, 20484, 'queue_poll'):
        ('not reached under grant', ('DELETE queue_blocks',), 'main.py:19936 42501'),
    ('a1', 'main.py', 49791, 49794, 'team_queue_poll'):
        ('not reached under grant', ('UPDATE team_queue',), None),
    ('a1', 'main.py', 49822, 49824, 'team_queue_poll'):
        ('not reached under grant', ('UPDATE team_queue',), None),
    ('a1', 'main.py', 49946, 49950, 'team_queue_poll'):
        ('not reached under grant', ('UPDATE team_queue',), None),
    ('a1', 'main.py', 49951, 49952, 'team_queue_poll'):
        ('not reached under grant', ('UPDATE team_queue',), None),
    ('a1', 'main.py', 51115, 51119, '_reconcile_team_series_bets'):
        ('not reached under grant', ('UPDATE team_series',), None),
    ('a1', 'main.py', 51859, 51861, '_team_resolve_live_family'):
        ('not reached under grant', ('UPDATE team_series',), None),
    ('a1', 'main.py', 53768, 53770, 'ovt_queue_poll'):
        ('not reached under grant', ('UPDATE ovt_queue',), 'main.py:53536 42501'),
    ('a1', 'main.py', 53808, 53811, 'ovt_queue_poll'):
        ('not reached under grant', ('UPDATE ovt_queue',), 'main.py:53536 42501'),
    ('a1', 'main.py', 65184, 65186, '_ffa_queue_poll_inner'):
        ('not reached under grant', ('UPDATE ffa_lobbies',), 'main.py:16399 42501'),
    ('a1', 'main.py', 65206, 65208, '_ffa_queue_poll_inner'):
        ('not reached under grant', ('UPDATE ffa_lobbies',), 'main.py:16399 42501'),
    ('a1', 'main.py', 65249, 65253, '_ffa_queue_poll_inner'):
        ('not reached under grant', ('UPDATE ffa_lobbies',), 'main.py:16399 42501'),
    ('a1', 'main.py', 65263, 65265, '_ffa_queue_poll_inner'):
        ('not reached under grant', ('UPDATE ffa_lobbies',), 'main.py:16399 42501'),
}


SKIP_TESTS = ("::test_r8_sr_the_lookup_reads_only_the_covered_ok_positions",)


def enumerate_positions(python=sys.executable, timeout=7200):
    """Run both walks under the ro_spy plugin (a subprocess pytest in this
    directory) and return (positions, ambiguous, synthetic_count, rc):
    positions the set of (walk, file, line, end_line, span, kind) of every
    'real' record whose module is under backend/api, whatever the lookup
    answered; ambiguous the 'ambiguous' records under backend/api and every
    record whose kind is not the answer of the table the walk passed for
    its position ('write' when absent).
    The lookup's own unit test (SKIP_TESTS) asks about every table position
    by construction and walks nothing; its records are left out.
    RO8_ENUM_SAVE names a file the enumeration is also written to (the
    mutant runs read it back through RO8_ENUM_FROM)."""
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
        if not under_api or test.split("[")[0].endswith(SKIP_TESTS):
            continue
        if r["kind"] != r["table_kind"]:
            ambiguous.append(r)
        positions.add((walk, os.path.basename(path), r["line"], r["end"], r["span"],
                       r["kind"]))
    save = os.environ.get("RO8_ENUM_SAVE")
    if save:
        with open(save, "w", encoding="utf-8") as fh:
            json.dump({"positions": sorted(positions), "ambiguous": ambiguous}, fh)
    return positions, ambiguous, synthetic, (proc.returncode, proc.stdout[-2000:])


WHO_SQL = "SELECT current_user, session_user"


class IdentityError(AssertionError):
    pass


def role_engine(dsn, schema, expect, checked, read_write=False):
    """A NullPool engine on `dsn` with search_path `schema`; every new
    connection asserts its identity is `expect` (appending to `checked`).
    `read_write` (the grant run, ruling R-B) sets the session's transactions
    READ WRITE after the identity check, so the grant layer (42501) is what
    refuses a write the run did not grant."""
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
        if read_write:
            dbapi_conn.run_async(lambda c: c.execute(
                "SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE"))

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


def role_sessionmaker(engine, cls=None):
    return async_sessionmaker(engine, class_=cls or RecordingSession,
                              expire_on_commit=False)


# Ruling R-B: the transaction's own write counters, read on the session's
# connection immediately before and after a target position's statement.
WRITES_SQL = (
    "SELECT (SELECT COALESCE(SUM(n_tup_ins + n_tup_upd + n_tup_del), 0)"
    " FROM pg_catalog.pg_stat_xact_user_tables)"
    " + (SELECT COALESCE(SUM(n_tup_ins + n_tup_upd + n_tup_del), 0)"
    " FROM pg_catalog.pg_stat_xact_sys_tables)")


class CountingSession(RecordingSession):
    """A RecordingSession that, at a statement whose production site is in
    one of self.info['targets'] ((file, line, end) spans), records the write
    delta of the transaction around it in self.info['deltas'] as (file,
    line, delta); a statement that fails records no delta."""

    async def writes(self):
        return int((await AsyncSession.execute(self, text(WRITES_SQL))).scalar())

    async def execute(self, statement, params=None, **kw):
        site = _site()
        hit = [t for t in self.info.get("targets", ()) if site[0] == t[0]
               and site[1] is not None and t[1] <= site[1] <= t[2]]
        if not hit:
            return await super().execute(statement, params, **kw)
        before = await self.writes()
        res = await super().execute(statement, params, **kw)
        after = await self.writes()
        self.info.setdefault("deltas", []).append((site[0], site[1], after - before))
        return res


# Ruling R-B: the table privileges of each statement that refused first on a
# path holding an unreached COVERED position (the sites OUTCOME names), each
# granted to the role in the clone, as its owner, for that path's run only.
REFUSER_GRANTS = {
    "main.py:16851": ("UPDATE players",),
    "main.py:16393": ("UPDATE team_queue",),
    "main.py:16396": ("UPDATE ovt_queue",),
    "main.py:17406": ("UPDATE ffa_lobbies",),
    "main.py:19936": ("DELETE queue_blocks",),
    "main.py:51089": ("UPDATE team_series",),
    "main.py:51768": ("UPDATE team_series",),
    "match_hold.py:380": ("UPDATE team_series",),
}


def under_grant(log, deltas, entry, grants):
    """The grant run's outcome at `entry`: ('ok-under-grant', grants, delta)
    when every run of the position succeeded, delta the largest write delta
    measured around it; otherwise ('not reached under grant', grants, the
    first refused statement 'file:line sqlstate' of the run, or None)."""
    _walk, f, line, end, _span = entry
    outs = outcome_at(log, entry)
    ds = [d for (df, dl, d) in deltas if df == f and line <= dl <= end]
    if outs and all(o == "ok" for o in outs) and len(ds) == len(outs):
        return ("ok-under-grant", tuple(grants), max(ds))
    if outs:
        return ("refused under grant", tuple(grants), sorted(set(outs))[0])
    refused = [(lf, ll, o) for (lf, ll, o) in log if o != "ok"]
    first = "%s:%s %s" % refused[0] if refused else None
    return ("not reached under grant", tuple(grants), first)


def outcome_at(log, entry):
    """The outcomes recorded at the position `entry` (its file and line
    span)."""
    _walk, f, line, end, _span = entry
    return [o for (lf, ll, o) in log if lf == f and ll is not None and line <= ll <= end]
