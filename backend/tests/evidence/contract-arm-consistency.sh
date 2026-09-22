#!/usr/bin/env bash
# MUTATION CONTROL for the client contract's own arm table, with its negative
# control (#391).
#
#   bash backend/tests/evidence/contract-arm-consistency.sh <contract>
#
# THE PATH IS AN ARGUMENT and is not written down here. The document this lane
# specifies the client half in lives under the gitignored scratch, and a
# committed file that names a path the repository does not contain is the
# defect the shipped-file rule exists for -- so this instrument names none and
# the invocation that ran it is recorded in the report instead.
#
# WHAT IT CHECKS, and why a check was needed at all. The contract states the
# disposition of every answer twice: once in the arm table, which is what an
# implementer reads, and once in the recovery section, which is what the
# server's behaviour is specified against. Round 12 left the two saying
# different things about one answer -- the table said a refusal carrying
# `settled_game` is TERMINAL and the entry is dropped, while the recovery
# section had the same entry re-signed at the advertised number and
# redelivered -- and nothing compared them, because one is a table cell and
# the other is a paragraph four hundred lines away. A behind seat that obeyed
# the table dropped a real game, so its result, rating and gold never settled.
#
# The four facts this asks for are the reconciled rule, and they are read off
# the document rather than restated:
#
#   1. the `409 with settled_game` row's DISPOSITION is REDIRECT;
#   2. that disposition does not also say the entry is dropped;
#   3. the same row states the bound -- a SECOND such refusal of that entry is
#      TERMINAL for it;
#   4. the recovery section says the SAME parked entry is re-signed with the
#      advertised number and redelivered.
#
# A document where 4 holds and 1 does not is the round-8 HIGH itself, and that
# is what the MUTANT restores. Both the mutant and the inert twin run against
# COPIES in a temporary directory; the real document is read and never written.
set -u

CONTRACT="${1:?usage: contract-arm-consistency.sh <contract>}"

echo "script    <repo>/backend/tests/evidence/contract-arm-consistency.sh"
# The capture this script is redirected into, named by the producer --
# see the .gitignore block for this directory.
echo "capture   <repo>/backend/tests/evidence/<round>-contract-arms.log"
echo "command   bash <repo>/backend/tests/evidence/contract-arm-consistency.sh <contract>"
echo "contract  <the lane's client resync contract, under the gitignored scratch>"
echo "bash      ${BASH_VERSION}"
echo "started   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

[ -f "${CONTRACT}" ] || { echo "REFUSED: the named document is not a file"; exit 2; }

ROW_RE='^\| \*\*409 with `settled_game`\*\*'

# The row, and its DISPOSITION cell: the pipe-delimited table's third field.
row() { grep -E "${ROW_RE}" "$1" | head -1; }
disposition() { row "$1" | awk -F'|' '{print $3}'; }

RC=0
check() {   # <file> <label> <expect: consistent|contradiction>
  local line disp bound recov verdict why
  line="$(row "$1")"
  if [ -z "${line}" ]; then
    echo "  $2: the document carries no 409-with-settled_game row at all"
    [ "$3" = "contradiction" ] || RC=1
    return
  fi
  disp="$(disposition "$1")"
  bound=0
  recov=0
  printf '%s' "${line}" | grep -q 'SECOND' \
    && printf '%s' "${line}" | grep -q 'TERMINAL for the entry' && bound=1
  grep -q 'The SAME parked entry is re-signed with the advertised number' "$1" \
    && recov=1
  why=""
  printf '%s' "${disp}" | grep -q 'REDIRECT' || why="${why} no-REDIRECT"
  printf '%s' "${disp}" | grep -q 'drop the entry' && why="${why} says-drop"
  [ "${bound}" -eq 1 ] || why="${why} no-second-refusal-bound"
  [ "${recov}" -eq 1 ] || why="${why} no-recovery-rule"
  if [ -z "${why}" ]; then
    verdict="CONSISTENT"
  else
    verdict="CONTRADICTION -${why}"
  fi
  echo "  $2: disposition ->${disp}"
  echo "  $2: second-refusal bound stated: ${bound}; recovery re-signs the same entry: ${recov}"
  echo "  $2: ${verdict}"
  case "$3" in
    consistent)   [ "${verdict}" = "CONSISTENT" ] || RC=1 ;;
    contradiction) [ "${verdict}" = "CONSISTENT" ] && RC=1 ;;
  esac
}

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo "LIVE   the document as this round leaves it"
check "${CONTRACT}" "live    " consistent
echo

echo "MUTANT the table row says drop again (the round-8 HIGH, restored)"
awk -F'|' 'BEGIN{OFS="|"} /^\| \*\*409 with `settled_game`\*\*/ {$3=" TERMINAL - drop the entry "} 1' \
    "${CONTRACT}" > "${TMP}/mutant.md"
if cmp -s "${CONTRACT}" "${TMP}/mutant.md"; then
  echo "  REFUSED: the mutation changed nothing, so it cannot prove anything"
  RC=1
else
  check "${TMP}/mutant.md" "mutant  " contradiction
fi
echo

echo "INERT  a doubled space inside that same cell, the rule left alone"
sed 's/^\(| \*\*409 with `settled_game`\*\* | REDIRECT\) /\1  /' \
    "${CONTRACT}" > "${TMP}/inert.md"
if cmp -s "${CONTRACT}" "${TMP}/inert.md"; then
  echo "  REFUSED: the inert edit changed nothing, so it is not a control"
  RC=1
else
  check "${TMP}/inert.md" "inert   " consistent
fi
echo

if [ "${RC}" -eq 0 ]; then
  echo "RESULT: live CONSISTENT, mutant CONTRADICTION (red), inert CONSISTENT"
  echo "        (green). The check reds on the edit that actually happened --"
  echo "        a disposition cell written in one pass against a recovery rule"
  echo "        written in another -- and not on a reword beside it."
else
  echo "RESULT: FAILURES above"
fi
echo "finished  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit "${RC}"
