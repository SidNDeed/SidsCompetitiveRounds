#!/usr/bin/env bash
# The two full backend suites, run SEQUENTIALLY and never concurrently.
#
# They share one local PostgreSQL instance, so a concurrent pair fights over
# the same scratch databases and reports each other's failures. Round 7 also
# learned the other half of that rule the expensive way: a run must not
# overlap an EDIT either. Two 23-minute pairs were thrown away because a file
# was written after the run had started, and a run that overlaps its own tree
# certifies nothing.
#
# COMMITTED beside the report it produces, and it takes everything from its
# own location or from the environment, so a reader on a fresh clone can
# re-derive the numbers in r7-suites.txt:
#
#   FFA_TEST_PG_DSN=postgresql+asyncpg://<user>@<host>:<port>/<scratch-db> \
#     bash backend/tests/evidence/run-both-suites.sh
#
# The opt-out half runs with FFA_TEST_PG_DSN REMOVED from the environment, and
# that is not tidiness -- it is the difference between the two runs. The gate
# is `require_pg()`: it returns the DSN if one is set and only then consults
# FFA_TEST_PG_OPTOUT, so a DSN that leaks into the opt-out invocation makes it
# a second LIVE run wearing the opt-out's name, with the opt-out's own skip
# count silently absent. The first version of this script exported the DSN for
# both halves and produced exactly that: an "opt-out" run reporting 15 skips
# instead of ~37, green and meaningless. `env -u` is what makes the two halves
# two different questions.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "${HERE}/../.." && pwd)"
OUT="${SUITE_OUT:-${TMPDIR:-/tmp}}"
DSN="${FFA_TEST_PG_DSN:-}"

if [ -z "${DSN}" ]; then
  echo "REFUSED: FFA_TEST_PG_DSN is unset, so the live half would be skips" >&2
  exit 2
fi

cd "${BACKEND}" || exit 1

echo "=== opt-out started $(date -u +%H:%M:%S) ==="
env -u FFA_TEST_PG_DSN FFA_TEST_PG_OPTOUT=1 \
    python -m pytest tests/ -q -p no:cacheprovider \
    > "${OUT}/r7-suite-optout.log" 2>&1
echo "opt-out rc=$?"
tail -2 "${OUT}/r7-suite-optout.log"
# The skip count in that line IS the check: an opt-out run that skipped as few
# as the live run did is a live run, whatever the flag said.

echo "=== live DSN started $(date -u +%H:%M:%S) ==="
FFA_TEST_PG_DSN="${DSN}" python -m pytest tests/ -q -p no:cacheprovider \
    > "${OUT}/r7-suite-dsn.log" 2>&1
echo "dsn rc=$?"
tail -2 "${OUT}/r7-suite-dsn.log"

echo "=== done $(date -u +%H:%M:%S) ==="
