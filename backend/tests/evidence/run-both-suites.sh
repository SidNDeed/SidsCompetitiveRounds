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
# re-derive the numbers in this round's suites report. Its OWN stdout is
# what that report is assembled from (assemble-evidence.py), so the caller
# captures this script's output to a file and commits it beside the report:
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
#
# ROUND 8: each half PRINTS THE COMMAND it is about to run, the working
# directory it runs in and the interpreter, immediately before running it. A
# committed report that shows two summary lines and no invocation is two
# numbers from a selection nobody can reconstruct, which is what the round-5
# gate found in round 7's own logs. Every path printed is repository-relative
# by construction: the script cd's to the backend directory first and names
# nothing outside it.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "${HERE}/../.." && pwd)"
OUT="${SUITE_OUT:-${TMPDIR:-/tmp}}"
# The per-half pytest logs are named for the round that runs them, and the
# round is an INPUT rather than a literal here: a tag baked into the script
# is a thing to remember to bump, and a forgotten one makes this round's
# report name last round's capture.
#
# ROUND 11: and it has no DEFAULT either. A default round tag is a baked-in
# one with a longer fuse. It read `r10`, so a caller who forgot the variable
# would have had this round's two halves overwrite the previous round's
# captures, under the previous round's names, with a green run and nothing to
# see. There is nothing to fall back to, so the script refuses.
TAG="${SUITE_TAG:-}"
DSN="${FFA_TEST_PG_DSN:-}"

if [ -z "${TAG}" ]; then
  echo "REFUSED: SUITE_TAG is unset. It names the round these captures" >&2
  echo "         belong to, and a default would let one round overwrite" >&2
  echo "         another round's logs under that round's own name." >&2
  exit 2
fi

if [ -z "${DSN}" ]; then
  echo "REFUSED: FFA_TEST_PG_DSN is unset, so the live half would be skips" >&2
  exit 2
fi

REPO="$(cd "${BACKEND}/.." && pwd)"

cd "${BACKEND}" || exit 1

echo "script    <repo>/backend/tests/evidence/run-both-suites.sh"
echo "cwd       <repo>/backend"
echo "python    $(python -V 2>&1)"
# THE CAPTURE THIS SCRIPT IS REDIRECTED INTO, named by the producer.
# The .gitignore negation for this directory admits one pattern per
# producer, and the pattern is checked against the name the producer
# itself prints -- so a capture nothing here writes is not admitted, and
# a producer whose capture is not admitted reds (both directions in
# test_the_evidence_log_negation_admits_only_produced_logs).
echo "capture   <repo>/backend/tests/evidence/${TAG}-suite-run.log"

# THE TREE THIS RUN CERTIFIES, fingerprinted by the instrument rather than
# asserted afterwards in prose. A suite that overlaps an edit to its own tree
# certifies nothing (#308), and a sentence in the report saying it did not is a
# claim written from the one state its author had in mind (#351). So the tree is
# fingerprinted HERE, again at the end, and the two are compared by the
# script -- names relative to the repository root, which is also what keeps this
# seat's checkout out of a committed log.
#
# ROUND 9: the fingerprint moved OUT of this script and stopped being a list
# captured once. Round 8 fixed the set at this point -- the tracked files that
# ALREADY differed from HEAD -- and hashed that same fixed set before and after,
# so a tracked file byte-identical to HEAD at this line and edited mid-run, and
# any file CREATED mid-run, were hashed by neither pass and compared equal. Both
# printed UNCHANGED over a tree the run did not have. They are also the two most
# likely edits to make, since writing a NEW test file is how a round adds a
# control and `pytest tests/` collects a directory. tree-fingerprint.sh
# re-derives the set at every call and carries the paths inside the value; its
# header says what each command covers and why ignored paths stay out.
FINGERPRINT="${HERE}/tree-fingerprint.sh"
[ -f "${FINGERPRINT}" ] || { echo "REFUSED: tree-fingerprint.sh is missing" >&2; exit 3; }
fingerprint() {
  bash "${FINGERPRINT}" "${REPO}"
}
BEFORE="$(fingerprint)"
COUNT="$(printf '%s\n' "${BEFORE}" | grep -c . || true)"
# An empty fingerprint compares equal to an empty one for ever, so the
# instrument has to have produced something before it is trusted (#342). A tree
# with nothing uncommitted and nothing untracked is not the tree a round runs
# its own new tests on.
if [ "${COUNT}" -eq 0 ]; then
  echo "REFUSED: the tree fingerprint is empty, so it could not detect a change" >&2
  exit 4
fi
echo "command   bash <repo>/backend/tests/evidence/tree-fingerprint.sh <repo>"
echo "tree      ${COUNT} paths differ from HEAD or are untracked; fingerprinted before and after"
printf '%s\n' "${BEFORE}" | sed 's/^/  /'

echo "=== opt-out started $(date -u +%H:%M:%S) ==="
echo 'command   env -u FFA_TEST_PG_DSN FFA_TEST_PG_OPTOUT=1 python -m pytest tests/ -q -p no:cacheprovider'
env -u FFA_TEST_PG_DSN FFA_TEST_PG_OPTOUT=1 \
    python -m pytest tests/ -q -p no:cacheprovider \
    > "${OUT}/${TAG}-suite-optout.log" 2>&1
echo "opt-out rc=$?"
# ROUND 11: the tail is stripped of carriage returns HERE, in the instrument,
# rather than at the copy-in step. These two lines are the only ones in this
# script's stdout that arrive as CRLF -- they are read back from a pytest log
# the interpreter wrote through a translating stream, while everything else
# here and every other file under this directory is LF. Round 10 normalised
# them when the capture was copied into the report and recorded that as a
# deviation, because a report that mixes the two conventions cannot survive
# the control that mutates it: the runner records a file's convention when it
# first reads it and writes that one back, so a mixed file returns uniform and
# is reported as not restored. Normalising in the instrument means the capture
# and the report are the same bytes with no step in between.
tail -2 "${OUT}/${TAG}-suite-optout.log" | tr -d '\r'
# The skip count in that line IS the check: an opt-out run that skipped as few
# as the live run did is a live run, whatever the flag said.

echo "=== live DSN started $(date -u +%H:%M:%S) ==="
echo 'command   FFA_TEST_PG_DSN=postgresql+asyncpg://<user>@<host>:<port>/<db> python -m pytest tests/ -q -p no:cacheprovider'
FFA_TEST_PG_DSN="${DSN}" python -m pytest tests/ -q -p no:cacheprovider \
    > "${OUT}/${TAG}-suite-dsn.log" 2>&1
echo "dsn rc=$?"
tail -2 "${OUT}/${TAG}-suite-dsn.log" | tr -d '\r'

echo "=== tree re-fingerprinted $(date -u +%H:%M:%S) ==="
# The invocation again, immediately above the verdict it produces:
# the evidence check requires every results line to name the command
# that produced it, and the closing UNCHANGED/MOVED line is a result.
echo "command   bash <repo>/backend/tests/evidence/tree-fingerprint.sh <repo>"
AFTER="$(fingerprint)"
AFTER_COUNT="$(printf '%s\n' "${AFTER}" | grep -c . || true)"
if [ "${BEFORE}" = "${AFTER}" ]; then
  echo "UNCHANGED: the same ${COUNT} paths, each byte-identical to the pre-run fingerprint"
else
  echo "MOVED: ${COUNT} paths before, ${AFTER_COUNT} after; the tree changed under the run, so neither summary certifies it"
  diff <(printf '%s\n' "${BEFORE}") <(printf '%s\n' "${AFTER}") || true
fi

echo "=== done $(date -u +%H:%M:%S) ==="
