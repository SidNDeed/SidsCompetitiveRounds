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
# Ruling REHEARSAL-R8-A1 E2: 'ok' also requires that the lock read inside
# the transaction at the end of every run of the position found no row
# beyond the declared expected ones (unexpected_locks); a position that ran
# but whose read found one is ('lock', rows) and leaves the claim: measured
# at 51761 (the advisory transaction lock 51703 took earlier in the same
# transaction; r9-ro-measure1, RF/r9/ro). A position read under a grant whose
# read found one keeps its role outcome here and its grant outcome in
# GRANT_OUTCOME ('lock under grant'): 16871, 16886, 16897, 16924 (the
# FOR NO KEY UPDATE of 16851), 51793 (51768's FOR UPDATE), 65184 (an
# advisory lock and ffa_queue row locks) and match_hold.py:381 (380's
# UPDATE).
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
    ('a1', 'main.py', 50001, 50003, 'team_queue_poll'): ('ok-under-grant', ('UPDATE team_queue',), 0, ('not reached', 'main.py:16393', '25006')),
    ('a1', 'main.py', 51115, 51119, '_reconcile_team_series_bets'): ('not reached', 'main.py:51089', '25006'),
    ('a1', 'main.py', 51761, 51763, '_team_lock_family_pick'): ('lock', ('advisory ExclusiveLock',)),
    ('a1', 'main.py', 51793, 51793, '_team_lock_family_pick'): ('not reached', 'main.py:51768', '25006'),
    ('a1', 'main.py', 51859, 51861, '_team_resolve_live_family'): ('not reached', 'main.py:51768', '25006'),
    ('a1', 'main.py', 53768, 53770, 'ovt_queue_poll'): ('not reached', 'main.py:16396', '25006'),
    ('a1', 'main.py', 53808, 53811, 'ovt_queue_poll'): ('ok-under-grant', ('DELETE ovt_queue', 'UPDATE ovt_queue'), 0, ('not reached', 'main.py:16396', '25006')),
    ('a1', 'main.py', 56363, 56368, '_rules_members'): 'ok',
    ('a1', 'main.py', 57195, 57201, '_player_body_color'): 'ok',
    ('a1', 'main.py', 65184, 65186, '_ffa_queue_poll_inner'): ('not reached', 'main.py:17406', '25006'),
    ('a1', 'main.py', 65206, 65208, '_ffa_queue_poll_inner'): ('ok-under-grant', ('DELETE ffa_queue', 'UPDATE ffa_assembly_seats', 'UPDATE ffa_lobbies', 'UPDATE ffa_queue'), 0, ('not reached', 'main.py:17406', '25006')),
    ('a1', 'main.py', 65249, 65253, '_ffa_queue_poll_inner'): ('ok-under-grant', ('DELETE ffa_queue', 'UPDATE ffa_assembly_seats', 'UPDATE ffa_lobbies', 'UPDATE ffa_queue'), 0, ('not reached', 'main.py:17406', '25006')),
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
# Ruling R-A: every WRITERS position answers 'lock' in the walks' lookup,
# and each lock moves to the bound measured here: refused under the role
# (25006) for the 10 reached (16390, 16393, 16396, 16399, 16851, 17406,
# 51089, 51768, 63719, match_hold.py:569); not reached for 16857 (after
# 16851) and 51112 (after 51089); and for main.py:16839 (a transaction-local
# set_config of lock_timeout) and main.py:51703 (pg_advisory_xact_lock),
# 'ok' under the role, so their bound is the walk's lock rule alone (a
# QUESTION for the reviewer). Round 9 (E2): the lock read now measures the
# writers too: 51703 is ('lock', ('advisory ExclusiveLock',)), its advisory
# lock measured; 16839 holds no lock beyond the expected rows. Round 10
# (REHEARSAL-R9-A1 (B)): its transaction-local set_config of lock_timeout
# is now MEASURED as an effect by the continuity bracket's residue reading
# (pg_settings lock_timeout 0 -> 1000 across the position; r10-ro-measure1,
# RF/r10/ro), so its bound is a measurement, no longer the walk's lock rule
# alone; it stays 'lock' in the lookup (every WRITERS position does).
WRITER_OUTCOME = {
    ('a1', 'main.py', 16390, 16391, '_lock_queue_rows_ordered'): '25006',
    ('a1', 'main.py', 16393, 16394, '_lock_queue_rows_ordered'): '25006',
    ('a1', 'main.py', 16396, 16397, '_lock_queue_rows_ordered'): '25006',
    ('a1', 'main.py', 16399, 16400, '_lock_queue_rows_ordered'): '25006',
    ('a1', 'main.py', 16839, 16849, '_lease_admission_gate'):
        ('continuity', ('setting lock_timeout=0', 'setting lock_timeout=1000')),
    ('a1', 'main.py', 16851, 16853, '_lease_admission_gate'): '25006',
    ('a1', 'main.py', 16857, 16859, '_lease_admission_gate'): ('not reached', 'main.py:16851', '25006'),
    ('a1', 'main.py', 17406, 17409, '_lock_snapshot_rows'): '25006',
    ('a1', 'main.py', 51089, 51093, '_reconcile_team_series_bets'): '25006',
    ('a1', 'main.py', 51112, 51114, '_reconcile_team_series_bets'): ('not reached', 'main.py:51089', '25006'),
    ('a1', 'main.py', 51703, 51705, '_team_quartet_lock'): ('lock', ('advisory ExclusiveLock',)),
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
    position (ruling R-B). Both are measured outcomes that already carry the
    lock read (ruling REHEARSAL-R8-A1 E2): 'ok' and 'ok-under-grant' are
    given only when every run of the position was followed by a lock read
    inside its transaction that found no row beyond the declared expected
    ones (unexpected_locks); a position whose read found one is ('lock',
    rows) or ('lock under grant', grants, rows), never green."""
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
# delta under its grants): the reason, as measured. Ruling REHEARSAL-R8-A1
# E2: or reached with a zero delta but holding, at the end of the position
# inside its transaction, a lock beyond the declared expected rows ('lock
# under grant', grants, the unexpected rows as measured on PostgreSQL 16.9:
# a row-locking SELECT holds RowShareLock on the table AND on every index of
# it, plus the transaction id the row lock assigned; no tuple row appears
# without a waiter). The first seven entries were 'ok-under-grant' in
# round 8 and leave the read-only claim (r9-ro-measure1, RF/r9/ro).
GRANT_OUTCOME = {
    ('a1', 'main.py', 16871, 16871, '_lease_admission_gate'):
        ('lock under grant', ('UPDATE players',), ('relation RowShareLock idx_players_active', 'relation RowShareLock idx_players_discord', 'relation RowShareLock idx_players_last_seen', 'relation RowShareLock idx_players_mod_version', 'relation RowShareLock idx_players_steam', 'relation RowShareLock players', 'relation RowShareLock players_discord_id_key', 'relation RowShareLock players_pc_game_portrait_hash_idx', 'relation RowShareLock players_pc_steam_portrait_hash_idx', 'relation RowShareLock players_pc_steam_portrait_next_at_idx', 'relation RowShareLock players_pkey', 'relation RowShareLock players_steam_id_key', 'transactionid ExclusiveLock')),
    ('a1', 'main.py', 16886, 16891, '_lease_admission_gate'):
        ('lock under grant', ('UPDATE players',), ('relation RowShareLock idx_players_active', 'relation RowShareLock idx_players_discord', 'relation RowShareLock idx_players_last_seen', 'relation RowShareLock idx_players_mod_version', 'relation RowShareLock idx_players_steam', 'relation RowShareLock players', 'relation RowShareLock players_discord_id_key', 'relation RowShareLock players_pc_game_portrait_hash_idx', 'relation RowShareLock players_pc_steam_portrait_hash_idx', 'relation RowShareLock players_pc_steam_portrait_next_at_idx', 'relation RowShareLock players_pkey', 'relation RowShareLock players_steam_id_key', 'transactionid ExclusiveLock')),
    ('a1', 'main.py', 16897, 16909, '_lease_admission_gate'):
        ('lock under grant', ('UPDATE players',), ('relation RowShareLock idx_players_active', 'relation RowShareLock idx_players_discord', 'relation RowShareLock idx_players_last_seen', 'relation RowShareLock idx_players_mod_version', 'relation RowShareLock idx_players_steam', 'relation RowShareLock players', 'relation RowShareLock players_discord_id_key', 'relation RowShareLock players_pc_game_portrait_hash_idx', 'relation RowShareLock players_pc_steam_portrait_hash_idx', 'relation RowShareLock players_pc_steam_portrait_next_at_idx', 'relation RowShareLock players_pkey', 'relation RowShareLock players_steam_id_key', 'transactionid ExclusiveLock')),
    ('a1', 'main.py', 16924, 16934, '_lease_admission_gate'):
        ('lock under grant', ('UPDATE players',), ('relation RowShareLock idx_players_active', 'relation RowShareLock idx_players_discord', 'relation RowShareLock idx_players_last_seen', 'relation RowShareLock idx_players_mod_version', 'relation RowShareLock idx_players_steam', 'relation RowShareLock players', 'relation RowShareLock players_discord_id_key', 'relation RowShareLock players_pc_game_portrait_hash_idx', 'relation RowShareLock players_pc_steam_portrait_hash_idx', 'relation RowShareLock players_pc_steam_portrait_next_at_idx', 'relation RowShareLock players_pkey', 'relation RowShareLock players_steam_id_key', 'transactionid ExclusiveLock')),
    ('a1', 'main.py', 51793, 51793, '_team_lock_family_pick'):
        ('lock under grant', ('UPDATE team_series',), ('relation RowShareLock idx_team_series_dc_fallback_at', 'relation RowShareLock idx_team_series_dc_grace', 'relation RowShareLock idx_team_series_status', 'relation RowShareLock idx_team_series_t1a', 'relation RowShareLock idx_team_series_t1b', 'relation RowShareLock idx_team_series_t2a', 'relation RowShareLock idx_team_series_t2b', 'relation RowShareLock team_series', 'relation RowShareLock team_series_pkey', 'transactionid ExclusiveLock')),
    ('a1', 'main.py', 65184, 65186, '_ffa_queue_poll_inner'):
        ('lock under grant', ('DELETE ffa_queue', 'UPDATE ffa_assembly_seats', 'UPDATE ffa_lobbies', 'UPDATE ffa_queue'), ('advisory ExclusiveLock', 'relation RowShareLock ffa_queue', 'relation RowShareLock ffa_queue_pkey', 'relation RowShareLock idx_ffa_queue_held_until', 'relation RowShareLock idx_ffa_queue_lobby', 'relation RowShareLock idx_ffa_queue_status', 'transactionid ExclusiveLock')),
    ('a1', 'match_hold.py', 381, 384, '_hold_latch'):
        ('lock under grant', ('UPDATE team_series',), ('relation RowExclusiveLock idx_team_series_dc_fallback_at', 'relation RowExclusiveLock idx_team_series_dc_grace', 'relation RowExclusiveLock idx_team_series_status', 'relation RowExclusiveLock idx_team_series_t1a', 'relation RowExclusiveLock idx_team_series_t1b', 'relation RowExclusiveLock idx_team_series_t2a', 'relation RowExclusiveLock idx_team_series_t2b', 'relation RowExclusiveLock team_series', 'relation RowExclusiveLock team_series_pkey', 'transactionid ExclusiveLock')),
    ('a1', 'main.py', 16868, 16868, '_lease_admission_gate'):
        ('not reached under grant', ('UPDATE players',), None),
    ('a1', 'main.py', 20479, 20481, 'queue_poll'):
        ('not reached under grant', ('DELETE queue_blocks', 'UPDATE queue_blocks', 'UPDATE ranked_queue'), None),
    ('a1', 'main.py', 20482, 20484, 'queue_poll'):
        ('not reached under grant', ('DELETE queue_blocks', 'UPDATE queue_blocks', 'UPDATE ranked_queue'), None),
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
        ('not reached under grant', ('DELETE ovt_queue', 'UPDATE ovt_queue'), None),
    ('a1', 'main.py', 65263, 65265, '_ffa_queue_poll_inner'):
        ('not reached under grant', ('DELETE ffa_queue', 'UPDATE ffa_assembly_seats', 'UPDATE ffa_lobbies', 'UPDATE ffa_queue'), None),
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


# Ruling REHEARSAL-R8-A1 E2: the locks the backend holds, read inside the
# transaction at the end of every measured position (after its statement,
# before the transaction ends).
LOCKS_SQL = (
    "SELECT locktype, mode, granted, relation::pg_catalog.regclass::text,"
    " virtualxid, virtualtransaction"
    " FROM pg_catalog.pg_locks WHERE pid = pg_catalog.pg_backend_pid()")

# The declared expected rows, one by one with the reason; every other row
# refuses the read classification (the direction rule: refuse by default):
#   virtualxid ExclusiveLock on the backend's OWN virtual transaction id
#       (virtualxid = virtualtransaction): every transaction holds it from
#       its first statement; it locks nothing another session uses;
#   relation AccessShareLock (granted): the lock every plain SELECT takes on
#       each relation it reads (pg_locks itself included); it conflicts only
#       with ACCESS EXCLUSIVE.
# Refused, among the rest: RowShareLock (SELECT FOR UPDATE / FOR NO KEY
# UPDATE / FOR SHARE / FOR KEY SHARE), RowExclusiveLock and stronger
# relation locks, tuple and transactionid locks (a row lock assigns the
# transaction an id), advisory locks (pg_advisory_lock and
# pg_advisory_xact_lock, either key form), object, page and extend locks,
# another backend's virtualxid, and any row not granted.


def unexpected_locks(rows):
    """The rows of a LOCKS_SQL read that refuse a read classification, each
    as 'locktype mode[ relation][ waiting]', sorted and distinct."""
    out = set()
    for locktype, mode, granted, rel, vxid, vtx in rows:
        if (granted and locktype == "virtualxid" and mode == "ExclusiveLock"
                and vxid is not None and vxid == vtx):
            continue
        if granted and locktype == "relation" and mode == "AccessShareLock":
            continue
        desc = "%s %s" % (locktype, mode)
        if rel is not None:
            desc += " " + rel
        if locktype == "virtualxid":
            desc += " (another backend's)"
        if not granted:
            desc += " waiting"
        out.add(desc)
    return tuple(sorted(out))


def _in(site, spans):
    return site[0] is not None and site[1] is not None and any(
        site[0] == t[0] and t[1] <= site[1] <= t[2] for t in spans)


# Ruling REHEARSAL-R9-A1 (B), transaction continuity: IDENTITY, never
# presence. A measured position is one production statement at a site in
# self.info['lock_targets'] or self.info['targets']. Inside its transaction,
# before the statement, the harness sets a position token the program cannot
# know (a transaction-local setting, POSITION_GUC, to a fresh random value)
# and reads the backend's own virtual transaction id (pg_locks, locktype
# virtualxid, this pid, virtualxid = virtualtransaction) and the session's
# residue; after the statement and after every measurement read of the
# position (the write counters, the lock read), still before any harness
# rollback, it reads all three again. The position is the SAME transaction
# only when the token reads back unchanged AND exactly one own virtualxid row
# was read at each end AND they are equal. A transaction-local setting ends
# with its transaction, and every transaction has a new virtual transaction
# id, so COMMIT, COMMIT AND CHAIN, ROLLBACK, ROLLBACK AND CHAIN, END, ABORT,
# PREPARE TRANSACTION (and any other form that ends the transaction) all fail
# it, whatever the program does next. Such a position is an EFFECT
# (('txn ended', ...) / ('txn ended under grant', ...)), never a read and
# never 'ok'.
# Session residue: each driver runs on its own NullPool engine, disposed
# after the driver (the connection a driver's positions ran on is never
# reused by another driver: discarded). Within one driver the residue is
# MEASURED at both ends of every position and a difference refuses it
# ('residue'): every server setting (pg_settings: a SET, SET LOCAL or
# set_config by the program, RESET), SQL-level prepared statements, holdable
# cursors, LISTEN channels and objects in the session's temporary schema;
# session-level advisory locks are the lock read's. And once a position on a
# session failed continuity or left residue, every later measured position
# on that session is refused too ('after txn ended', the first failing site):
# whatever it ran in is no longer the transaction the driver began.
POSITION_GUC = "rf10.position"
POSITION_START_SQL = (
    "SELECT pg_catalog.set_config('rf10.position', :token, true),"
    " ARRAY(SELECT virtualxid FROM pg_catalog.pg_locks"
    " WHERE pid = pg_catalog.pg_backend_pid() AND locktype = 'virtualxid'"
    " AND virtualxid = virtualtransaction AND granted ORDER BY 1),"
    " pg_catalog.pg_backend_pid() || ' ' || (SELECT backend_start::text"
    " FROM pg_catalog.pg_stat_activity WHERE pid = pg_catalog.pg_backend_pid())")
POSITION_END_SQL = (
    "SELECT pg_catalog.current_setting('rf10.position', true),"
    " ARRAY(SELECT virtualxid FROM pg_catalog.pg_locks"
    " WHERE pid = pg_catalog.pg_backend_pid() AND locktype = 'virtualxid'"
    " AND virtualxid = virtualtransaction AND granted ORDER BY 1)")
RESIDUE_SQL = (
    "SELECT ARRAY(SELECT name || '=' || setting FROM pg_catalog.pg_settings ORDER BY 1),"
    " (SELECT count(*) FROM pg_catalog.pg_prepared_statements WHERE from_sql),"
    " (SELECT count(*) FROM pg_catalog.pg_cursors WHERE is_holdable),"
    " (SELECT count(*) FROM pg_catalog.pg_listening_channels()),"
    " (SELECT count(*) FROM pg_catalog.pg_class"
    "  WHERE relnamespace = pg_catalog.pg_my_temp_schema())")


def same_transaction(start, end):
    """Continuity of one position from its two readings, each (token,
    [own virtualxid rows]): (same, detail). `same` only when the token read
    at the end is the one set at the start and the own virtualxid was read
    exactly once at each end and is equal."""
    token_ok = end[0] == start[0]
    vxid_ok = len(start[1]) == 1 and len(end[1]) == 1 and start[1] == end[1]
    detail = tuple(n for n, ok in (("token", token_ok), ("virtualxid", vxid_ok)) if not ok)
    return token_ok and vxid_ok, detail


def residue_changes(start, end):
    """The residue a position left: every pg_settings row that differs and
    every residue count that differs, sorted ('setting name=value' for a
    changed or added setting, 'prepared'/'holdable cursors'/'listen'/'temp
    objects' for a count)."""
    out = set()
    s0, s1 = set(start[0]), set(end[0])
    out |= {"setting " + r for r in s1 ^ s0}
    for name, a, b in zip(("prepared", "holdable cursors", "listen", "temp objects"),
                          start[1:], end[1:]):
        if a != b:
            out.add("%s %s->%s" % (name, a, b))
    return tuple(sorted(out))


class RecordingSession(AsyncSession):
    """Every execute records (file, line, outcome) in self.info['log']. At a
    measured position (a statement whose production site is in one of
    self.info['lock_targets'] or, on a COUNTING session, self.info['targets'],
    (file, line, end) spans) the statement runs inside the continuity bracket
    (ruling REHEARSAL-R9-A1 (B)): position start, then (COUNTING, at a
    target) the write counters, the statement, the counters again
    (self.info['deltas'] gets (file, line, delta)), then (at a lock target)
    the lock read (self.info['locks'] gets (file, line, unexpected_locks);
    ruling REHEARSAL-R8-A1 E2), then the position end: self.info['continuity']
    gets (file, line, same, detail), detail the failed identity parts, the
    residue changes, or ('after txn ended', first failing site). A statement
    that fails records its SQLSTATE and no measurement."""

    COUNTING = False

    async def execute(self, statement, params=None, **kw):
        site = _site()
        log = self.info.setdefault("log", [])
        lock_at = _in(site, self.info.get("lock_targets", ()))
        count_at = self.COUNTING and _in(site, self.info.get("targets", ()))
        start = None
        if lock_at or count_at:
            try:
                start = await self.position_start()
            except DBAPIError as e:
                # the transaction refuses any statement (an earlier refusal
                # aborted it): the position cannot be bracketed, so it is
                # unmeasured and never 'ok' (the statement itself is run
                # and recorded as the program issued it)
                start = ("unmeasured", "unmeasured " + (_sqlstate(e) or "error"))
                count_at = False
        before = await self.writes() if count_at else None
        try:
            res = await self.run_statement(site, statement, params, **kw)
        except DBAPIError as e:
            log.append((site[0], site[1], _sqlstate(e) or "error"))
            raise
        log.append((site[0], site[1], "ok"))
        if count_at:
            self.info.setdefault("deltas", []).append(
                (site[0], site[1], await self.writes() - before))
        if lock_at:
            await self.lock_read(site)
        if start is not None:
            await self.position_end(site, start)
        return res

    async def run_statement(self, site, statement, params=None, **kw):
        """The production statement itself (a control's session plants here)."""
        return await AsyncSession.execute(self, statement, params, **kw)

    async def position_start(self):
        token = os.urandom(16).hex()
        row = (await AsyncSession.execute(self, text(POSITION_START_SQL),
                                          {"token": token})).one()
        # the connections a session's positions ran on (backend pid and its
        # start time: a connection's identity), never one another driver's
        # (test_r10_driver_connections_discarded)
        self.info.setdefault("pids", set()).add(row[2])
        return (token, list(row[1])), await self.residue()

    async def residue(self):
        row = (await AsyncSession.execute(self, text(RESIDUE_SQL))).one()
        return (tuple(row[0]),) + tuple(int(x) for x in row[1:])

    async def position_end(self, site, start):
        if start[0] == "unmeasured":
            same, detail, left = False, (start[1],), ()
        else:
            try:
                row = (await AsyncSession.execute(self, text(POSITION_END_SQL))).one()
                same, detail = same_transaction(start[0], (row[0], list(row[1])))
                left = residue_changes(start[1], await self.residue())
            except DBAPIError as e:
                same, detail, left = False, ("unmeasured " + (_sqlstate(e) or "error"),), ()
        tainted = self.info.get("tainted")
        if tainted is not None and same and not left:
            same, detail = False, ("after txn ended at " + tainted,)
        elif not same or left:
            same, detail = False, detail + left
        if not same and tainted is None:
            self.info["tainted"] = "%s:%s" % site
        self.info.setdefault("continuity", []).append((site[0], site[1], same, detail))

    async def lock_read(self, site):
        rows = (await AsyncSession.execute(self, text(LOCKS_SQL))).all()
        self.info.setdefault("locks", []).append(
            (site[0], site[1], unexpected_locks(rows)))


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
    line, delta), inside the position's continuity bracket (the delta is
    admitted only with a 'same' continuity record); a statement that fails
    records no delta."""

    COUNTING = True

    async def writes(self):
        return int((await AsyncSession.execute(self, text(WRITES_SQL))).scalar())


# Ruling R-B: the table privileges of each statement that refused first on a
# path holding an unreached COVERED position (the sites OUTCOME names), each
# granted to the role in the clone, as its owner, for that path's run only.
# The ruling extends this along the same path: each successive statement
# refused with 42501 gets its exact privileges, one at a time, until the
# position is reached or a refusal other than 42501 occurs; each added
# grant carries the measured refusal that required it.
REFUSER_GRANTS = {
    "main.py:16851": ("UPDATE players",),
    "main.py:16393": ("UPDATE team_queue",),
    # then main.py:53536 (DELETE ovt_queue ... FOR UPDATE), 42501 under
    # UPDATE ovt_queue alone (rb-measure-2)
    "main.py:16396": ("UPDATE ovt_queue", "DELETE ovt_queue"),
    # then main.py:16399 (ffa_queue FOR UPDATE, a WRITERS lock), 42501
    # under UPDATE ffa_lobbies alone (rb-measure-2); then main.py:64692
    # (DELETE FROM ffa_queue ... FOR UPDATE SKIP LOCKED), 42501 under those
    # two (r8-w30b-sr-widen-measure-1)
    # then main.py:62975 (UPDATE ffa_assembly_seats), 42501 under the grants before it (r8-w30b-sr-widen-measure-2)
    "main.py:17406": (
        "UPDATE ffa_lobbies",
        "UPDATE ffa_queue",
        "DELETE ffa_queue",
        "UPDATE ffa_assembly_seats",
    ),
    # 19936 is a DELETE whose subquery locks FOR UPDATE SKIP LOCKED: 42501
    # under DELETE queue_blocks alone (rb-measure-2), so UPDATE too; then
    # main.py:16390 (ranked_queue FOR UPDATE, a WRITERS lock), 42501 under
    # those two (r8-w30b-sr-widen-measure-1)
    "main.py:19936": ("DELETE queue_blocks", "UPDATE queue_blocks", "UPDATE ranked_queue"),
    "main.py:51089": ("UPDATE team_series",),
    "main.py:51768": ("UPDATE team_series",),
    "match_hold.py:380": ("UPDATE team_series",),
}


def locks_at(locks, entry):
    """The lock reads recorded at the position `entry`: one tuple of
    unexpected rows per successful run of it."""
    _walk, f, line, end, _span = entry
    return [u for (lf, ll, u) in locks if lf == f and ll is not None and line <= ll <= end]


def continuity_at(conts, entry):
    """The continuity records at the position `entry`: one (same, detail)
    per successful run of it (ruling REHEARSAL-R9-A1 (B))."""
    _walk, f, line, end, _span = entry
    return [(same, d) for (cf, cl, same, d) in conts
            if cf == f and cl is not None and line <= cl <= end]


def broken_continuity(conts, runs):
    """None when every one of `runs` successful runs has a continuity record
    and each says the SAME transaction; otherwise the refusal's detail: the
    sorted failed parts of every record, or ('unmeasured', records, runs)."""
    if len(conts) != runs:
        return ("unmeasured", len(conts), runs)
    broken = tuple(sorted({x for same, d in conts if not same for x in d}))
    if any(not same for same, _d in conts):
        return broken or ("not the same transaction",)
    return None


def ran_outcome(outs, reads, conts):
    """The outcome of a position every run of which succeeded (`outs`, all
    'ok'), from its continuity records (`conts`, one per run; ruling
    REHEARSAL-R9-A1 (B)) and its lock reads (`reads`, one per run; ruling
    REHEARSAL-R8-A1 E2): ('continuity', detail) when a run did not stay in
    the transaction it began in (a transaction-ending statement, a replaced
    token, residue, or a session a previous position already broke): an
    effect, checked FIRST because a lock read of a replacement transaction
    measures nothing about the position; then 'ok' only when every run was
    read and no read found an unexpected row; ('lock', rows) when a read
    found one; ('lock unmeasured', reads, runs) when a run has no lock
    read."""
    broken = broken_continuity(conts, len(outs))
    if broken is not None:
        return ("continuity", broken)
    return lock_outcome(outs, reads)


def lock_outcome(outs, reads):
    """The lock decision of a position whose runs all succeeded and stayed
    in their transaction (ruling REHEARSAL-R8-A1 E2): 'ok' only when every
    run was read and no read found an unexpected row; ('lock', rows) when a
    read found one; ('lock unmeasured', reads, runs) when a run has no lock
    read. Callers decide continuity first (ran_outcome, under_grant)."""
    if len(reads) != len(outs):
        return ("lock unmeasured", len(reads), len(outs))
    held = tuple(sorted({row for u in reads for row in u}))
    return ("lock", held) if held else "ok"


def under_grant(log, deltas, entry, grants, locks, conts):
    """The grant run's outcome at `entry`: ('continuity under grant', grants,
    detail) when every run succeeded but a run did not stay in the
    transaction it began in (ruling REHEARSAL-R9-A1 (B); see ran_outcome);
    ('ok-under-grant', grants, delta) when every run of the position
    succeeded, stayed in its transaction and every run's lock read found
    only expected rows, delta the largest write delta measured around it;
    ('lock under grant', grants, rows) when a lock read found an unexpected
    row (or ('lock under grant', grants, ('unmeasured', reads, runs)));
    otherwise ('refused under grant', grants, sqlstate) when a run of it was
    refused, or ('not reached under grant', grants, the first refused
    statement 'file:line sqlstate' of the run, or None)."""
    _walk, f, line, end, _span = entry
    outs = outcome_at(log, entry)
    ds = [d for (df, dl, d) in deltas if df == f and line <= dl <= end]
    if outs and all(o == "ok" for o in outs):
        # REHEARSAL-R9-A1 (B): continuity first; a delta or a lock read of a
        # replacement transaction measures nothing about the position
        broken = broken_continuity(continuity_at(conts, entry), len(outs))
        if broken is not None:
            return ("continuity under grant", tuple(grants), broken)
    if outs and all(o == "ok" for o in outs) and len(ds) == len(outs):
        ran = lock_outcome(outs, locks_at(locks, entry))
        if ran == "ok":
            return ("ok-under-grant", tuple(grants), max(ds))
        rows = ran[1] if ran[0] == "lock" else ("unmeasured",) + ran[1:]
        return ("lock under grant", tuple(grants), rows)
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
