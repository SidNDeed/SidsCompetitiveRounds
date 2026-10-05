#!/usr/bin/env bash
# Migration 327 applied TWICE through `psql -f`, the way the deploy applies it,
# with the rows dumped after each run and diffed.
#
# psql, not asyncpg's simple-query path: the file carries its own BEGIN/COMMIT
# (#340 -- `psql -f` does not wrap a file in a transaction, it autocommits each
# statement), and running it the way the box runs it is the only execution that
# proves that.
#
# COMMITTED beside the report it produces, and it reads its connection from the
# environment rather than carrying one machine's paths, so a reader on a fresh
# clone can re-derive the report:
#
#   PSQL=/path/to/psql PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres \
#     bash backend/tests/evidence/migration-327-twice.sh > out.txt
#
# The fixture beside it (migration-327-fixture.sql) is the table this runs
# against: two rooms whose tails collide inside one lobby, a tail outside the
# 1..999 domain, a tail of zero, rows with no tail at all, and one row with no
# lobby.
set -u

PSQL="${PSQL:-psql}"
HOST="${PGHOST:-127.0.0.1}"
PORT="${PGPORT:-5432}"
USER="${PGUSER:-postgres}"
DB="${MIG327_DB:-rj327check}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/../../.." && pwd)"
# ROUND 8: run FROM the repository root and name both files RELATIVE to it.
# psql echoes the path it was handed in every NOTICE it raises, so an absolute
# path here writes this seat's checkout into a committed evidence file -- which
# round 7 handled by editing the log afterwards. A path is a fact about the run,
# so the fix belongs at the site that produces it and not in the transcript.
cd "${REPO}" || exit 1
FIXTURE="backend/tests/evidence/migration-327-fixture.sql"
MIG="backend/sql/327_ffa_game_number.sql"
ROWS1="$(mktemp)"
ROWS2="$(mktemp)"
trap 'rm -f "${ROWS1}" "${ROWS2}"' EXIT

"$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d postgres -q \
        -c "DROP DATABASE IF EXISTS ${DB};" -c "CREATE DATABASE ${DB};"

DUMP="SELECT photon_room_id, game_number, game_number_source
        FROM ffa_matches ORDER BY photon_room_id;"

{
  # THE INVOCATION, immediately above the results it produced. A log that
  # prints two runs and no record of what produced them is two transcripts
  # from a command nobody can rebuild; round 7 carried the usage template
  # above instead of the line that actually ran.
  echo "== invocation =="
  echo "script    backend/tests/evidence/migration-327-twice.sh"
  echo "cwd       <repo> (the script cd's there; every path below is relative to it)"
  echo "psql      $("$PSQL" --version 2>&1)"
  echo "fixture   ${FIXTURE}"
  echo "migration ${MIG}"
  echo "database  ${DB} on <host>:<port> as <user>, dropped and recreated above"
  # The relative path is written out rather than taken from $0, which carries
  # whatever the caller typed and would put an absolute path here the moment
  # someone invoked the script by one.
  echo "command   PSQL=<psql> PGHOST=<host> PGPORT=<port> PGUSER=<user> \\"
  echo "            MIG327_DB=${DB} bash backend/tests/evidence/migration-327-twice.sh"
  echo "started   $(date -u '+%Y-%m-%d %H:%M:%S') UTC"
  echo

  echo "== fixture =="
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -v ON_ERROR_STOP=1 -q -f "$FIXTURE" \
    && echo "fixture applied"

  echo
  echo "== migration 327, run 1 =="
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -v ON_ERROR_STOP=1 -f "$MIG"
  echo "run 1 rc=$?"

  echo
  echo "== rows after run 1 =="
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -q -c "$DUMP" | tee "${ROWS1}"

  echo
  echo "== migration 327, run 2 (idempotence) =="
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -v ON_ERROR_STOP=1 -f "$MIG"
  echo "run 2 rc=$?"

  echo
  echo "== rows after run 2 =="
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -q -c "$DUMP" | tee "${ROWS2}"

  echo
  echo "== diff of the two dumps (empty means row-identical) =="
  if diff "${ROWS1}" "${ROWS2}"; then
    echo "IDENTICAL: the second run changed no row"
  else
    echo "DIFFERENT: the second run was not a no-op"
  fi

  echo
  echo "== the column's guarantees, after two runs =="
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -q -c \
    "SELECT COUNT(*) AS rows_total,
            COUNT(*) FILTER (WHERE game_number IS NULL) AS still_null,
            COUNT(*) FILTER (WHERE game_number NOT BETWEEN 1 AND 999) AS out_of_domain
       FROM ffa_matches;"
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -q -c \
    "SELECT conname FROM pg_constraint
      WHERE conrelid = 'ffa_matches'::regclass
        AND conname = 'ck_ffa_matches_game_number_domain';"
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -q -c \
    "SELECT attnotnull FROM pg_attribute
      WHERE attrelid = 'ffa_matches'::regclass AND attname = 'game_number';"

  echo
  echo "== the WRITER row: a number the inserting statement supplied is kept =="
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -q -c \
    "INSERT INTO ffa_matches (id, lobby_id, photon_room_id, ended_at, game_number)
     VALUES (gen_random_uuid(), '00000000-0000-0000-0000-0000000000a1',
             'rmA_writer_r9', NOW(), 42);"
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -q -c \
    "SELECT photon_room_id, game_number, game_number_source
       FROM ffa_matches WHERE photon_room_id = 'rmA_writer_r9';"

  echo
  echo "== the OLD api's unnumbered insert, during the migration-first window =="
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -q -c \
    "INSERT INTO ffa_matches (id, lobby_id, photon_room_id, ended_at)
     VALUES (gen_random_uuid(), '00000000-0000-0000-0000-0000000000a1',
             'rmA_oldapi_r7', NOW());"
  "$PSQL" -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" -q -c \
    "SELECT photon_room_id, game_number, game_number_source
       FROM ffa_matches WHERE photon_room_id = 'rmA_oldapi_r7';"
} 2>&1
