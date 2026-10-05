#!/usr/bin/env bash
# The PostgreSQL-gated selection, run TWICE against ONE scratch database.
#
# The second run is the point of the file. Round 7 found that the live half
# passed once per scratch database and never again: the SCHEMA block dropped
# `players` without CASCADE, which succeeds on a virgin database and raises
# DependentObjectsStillExistError on every run after it, so fourteen tests were
# red on the second run before a single assertion of their own had executed.
# Nothing in the diff showed it. Running it twice is what showed it.
#
# COMMITTED beside the report it produces, and it takes its DSN from the
# environment, so a reader on a fresh clone can re-derive the numbers:
#
#   FFA_TEST_PG_DSN=postgresql+asyncpg://<user>@<host>:<port>/<scratch-db> \
#     bash backend/tests/evidence/run-pg-controls.sh
#
# ROUND 8: it PRINTS ITS OWN INVOCATION -- the command, the working directory,
# the interpreter and the selection expression -- immediately before the runs,
# for the same reason the mutation runner now does. Two summary lines with no
# record of what produced them are two numbers from a set nobody can rebuild.
# Every path printed is repository-relative: the script cd's to the backend
# directory first and names nothing outside it.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "${HERE}/../.." && pwd)"
DSN="${FFA_TEST_PG_DSN:-}"

if [ -z "${DSN}" ]; then
  echo "REFUSED: FFA_TEST_PG_DSN is unset, so the live checks would be skips" >&2
  exit 2
fi

SELECT_K="pg_ or opt_out or missing_dsn_alone or one_transaction or locked_slot or weakest_mode or wager_cannot_be_inserted or relock_leaves or committed_evidence or round_seven_control or round_eight_control or production_file or counts_the_checks or new_controls_a_report or residual_reach or negation_admits or arms_are_disjoint or repin_trailer or inert_twin"

cd "${BACKEND}" || exit 1

echo "script    <repo>/backend/tests/evidence/run-pg-controls.sh"
echo "cwd       <repo>/backend"
echo "python    $(python -V 2>&1)"
echo "dsn       postgresql+asyncpg://<user>@<host>:<port>/<db>"
# The capture this script is redirected into, named by the producer --
# see the .gitignore block for this directory and the both-directions
# check that compares the two sets.
echo "capture   <repo>/backend/tests/evidence/<round>-pg-controls.log"
echo "command   FFA_TEST_PG_DSN=... python -m pytest tests/test_ffa_game_number_anchor.py -v -p no:cacheprovider -k \"<selection>\""
echo ""
echo "selection (the expression is part of the evidence; a set nobody can"
echo "rebuild is a count nobody can check):"
echo ""
echo "  ${SELECT_K}" | fold -s -w 74 | sed 's/^/  /'
echo ""

# pytest's own header names the interpreter and the rootdir by ABSOLUTE path,
# which is this seat's checkout, and this report is committed. Round 7 removed
# those two lines from its transcript after the fact; a log edited to be true
# is not the same artifact as a log that was true when it was written, so the
# substitution happens HERE, in the instrument, on exactly the two line shapes
# that carry a path. Nothing else is touched: the shapes are anchored at the
# start of the line and keep everything the line says except the path itself,
# so a filter that quietly ate a result line would be visible as a missing
# result rather than as a clean run (#441).
sanitize() {
  sed -e 's#^\(platform .* pluggy-[0-9.]*\) -- .*#\1 -- <python>#' \
      -e 's#^rootdir: .*#rootdir: <repo>/backend#'
}

echo "------------------------------------------------------------------------------"
echo "== RUN 1, against a database that already held the previous run's tables =="
# ROUND 10: the invocation is printed again HERE, immediately above the run
# it names, and not only once in the header. The evidence check requires
# every results line to have an invocation as the nearest substantive line
# above it, because a header shared by two runs is a command line whose
# scope the reader has to guess -- and a third run appended later would
# have inherited it silently.
echo 'command   FFA_TEST_PG_DSN=... python -m pytest tests/test_ffa_game_number_anchor.py -v -p no:cacheprovider -k "<the selection printed above>"'
FFA_TEST_PG_DSN="${DSN}" python -m pytest tests/test_ffa_game_number_anchor.py \
    -v -p no:cacheprovider -k "${SELECT_K}" 2>&1 | sanitize
# The rc is pytest's, taken from PIPESTATUS: `$?` after a pipeline is sed's,
# and sed succeeds whatever pytest did.
echo "run 1 rc=${PIPESTATUS[0]}"

echo ""
echo "------------------------------------------------------------------------------"
echo "== RUN 2, the SAME selection against the SAME database, back to back =="
echo 'command   FFA_TEST_PG_DSN=... python -m pytest tests/test_ffa_game_number_anchor.py -v -p no:cacheprovider -k "<the selection printed above>"'
FFA_TEST_PG_DSN="${DSN}" python -m pytest tests/test_ffa_game_number_anchor.py \
    -v -p no:cacheprovider -k "${SELECT_K}" 2>&1 | sanitize
echo "run 2 rc=${PIPESTATUS[0]}"
