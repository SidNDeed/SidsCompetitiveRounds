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
# different things about one answer, and nothing compared them, because one is
# a table cell and the other is a paragraph four hundred lines away.
#
# ROUND 14 REVERSES THE DISPOSITION THIS INSTRUMENT HOLDS, and the reason is a
# ruling rather than a rewording. A refusal carrying `settled_game` is given by
# two deliveries the server cannot tell apart -- a behind seat's LATER physical
# game, and a CONFLICTING second account of the game already settled at that
# number -- so re-keying such a delivery at the free number can settle the
# conflicting account as a game of its own: a second row, a second rating, a
# second payout. The conservative disposition is the only one the integrity bar
# admits, so the arm is TERMINAL for the entry: it is dropped, the server has
# already quarantined the payload for review, and the seat derives its NEXT key
# from the advertised number.
#
# The facts this asks for are that rule, read off the document rather than
# restated:
#
#   1. the `409 with settled_game` row's DISPOSITION is TERMINAL for the entry;
#   2. that disposition says the entry is DROPPED and that the server kept it;
#   3. it does NOT say REDIRECT -- nothing in it re-signs or resends;
#   4. the same row says the seat's NEXT key comes from `expected_game`;
#   5. the recovery section states the same disposition in its own words;
#   6. the terminal-vs-retryable section states it a THIRD time, in its own.
#
# A document where 5 holds and 1 does not is the contradiction this exists for,
# and a document that redirects is the round-9 HIGH: that is what the MUTANT
# restores.
#
# FACT 6 AND THE SECOND PAIR EXIST BECAUSE OF THE ROUND-8 FINDING that this
# instrument was only PARTIAL against: it compared the arm table with the
# recovery section and read nothing else, while the document states the same
# disposition a third time in the section an implementer reaches when asking
# which answers are retryable. Two statements compared and a third left loose
# is the same defect one seat over, and the round-9 HIGH would have been half
# as visible if the loose one had been the one that drifted. So there are TWO
# mutant/inert pairs: the first rewrites the TABLE cell and leaves both
# paragraphs alone, the second rewrites the STATUS SECTION's sentence and
# leaves the table alone. Each must red, and each has an inert twin at the same
# site that must stay green. All four copies are written into a temporary
# directory; the real document is read and never written.
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
  local line disp nextkey recov sec4 verdict why
  line="$(row "$1")"
  if [ -z "${line}" ]; then
    echo "  $2: the document carries no 409-with-settled_game row at all"
    [ "$3" = "contradiction" ] || RC=1
    return
  fi
  disp="$(disposition "$1")"
  nextkey=0
  recov=0
  sec4=0
  printf '%s' "${line}" | grep -q 'derives its NEXT key from `expected_game`' \
    && printf '%s' "${line}" | grep -q 'quarantine record' && nextkey=1
  grep -q 'The refused entry is dropped and kept for review; the seat derives its NEXT key from the advertised number' "$1" \
    && recov=1
  # THE THIRD PLACE, which is the round-8 finding this instrument was PARTIAL
  # on: it read the arm table and the recovery section and nothing else, while
  # the document states the same rule again in the terminal-vs-retryable
  # section an implementer reaches from the other direction. Two statements
  # compared and a third left loose is the same defect one seat over.
  grep -q 'an answer carrying `settled_game` is TERMINAL for the entry' "$1" \
    && grep -q 'Never retried, and never re-signed' "$1" && sec4=1
  why=""
  printf '%s' "${disp}" | grep -q 'TERMINAL for the entry' || why="${why} no-TERMINAL"
  printf '%s' "${disp}" | grep -q 'drop it' || why="${why} no-drop"
  printf '%s' "${disp}" | grep -q 'kept it for review' || why="${why} no-capture"
  printf '%s' "${disp}" | grep -q 'REDIRECT' && why="${why} says-redirect"
  [ "${nextkey}" -eq 1 ] || why="${why} no-next-key-rule"
  [ "${recov}" -eq 1 ] || why="${why} no-recovery-rule"
  [ "${sec4}" -eq 1 ] || why="${why} no-status-section-rule"
  if [ -z "${why}" ]; then
    verdict="CONSISTENT"
  else
    verdict="CONTRADICTION -${why}"
  fi
  echo "  $2: disposition ->${disp}"
  echo "  $2: next-key rule stated in the row: ${nextkey}; recovery section drops the same entry: ${recov}; status section states it too: ${sec4}"
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

echo "MUTANT 1 the table row REDIRECTS again (the round-9 HIGH, restored)"
awk -F'|' 'BEGIN{OFS="|"} /^\| \*\*409 with `settled_game`\*\*/ {$3=" REDIRECT - keep the entry, re-sign it ONCE at the advertised expected_game, submit "} 1' \
    "${CONTRACT}" > "${TMP}/mutant.md"
if cmp -s "${CONTRACT}" "${TMP}/mutant.md"; then
  echo "  REFUSED: the mutation changed nothing, so it cannot prove anything"
  RC=1
else
  check "${TMP}/mutant.md" "mutant 1" contradiction
fi
echo

echo "INERT 1  a doubled space inside that same cell, the rule left alone"
sed 's/^\(| \*\*409 with `settled_game`\*\* | TERMINAL for the entry\) /\1  /' \
    "${CONTRACT}" > "${TMP}/inert.md"
if cmp -s "${CONTRACT}" "${TMP}/inert.md"; then
  echo "  REFUSED: the inert edit changed nothing, so it is not a control"
  RC=1
else
  check "${TMP}/inert.md" "inert 1 " consistent
fi
echo

echo "MUTANT 2 the STATUS SECTION makes the same answer retryable, table intact"
sed 's|^- \*\*an answer carrying `settled_game` is TERMINAL for the entry\.\*\*|- **an answer carrying `settled_game` is RETRYABLE - re-sign the entry ONCE at the advertised number.**|' \
    "${CONTRACT}" > "${TMP}/mutant2.md"
if cmp -s "${CONTRACT}" "${TMP}/mutant2.md"; then
  echo "  REFUSED: the mutation changed nothing, so it cannot prove anything"
  RC=1
else
  check "${TMP}/mutant2.md" "mutant 2" contradiction
fi
echo

echo "INERT 2  a doubled space after that same sentence, the rule left alone"
sed 's|^\(- \*\*an answer carrying `settled_game` is TERMINAL for the entry\.\*\*\) |\1  |' \
    "${CONTRACT}" > "${TMP}/inert2.md"
if cmp -s "${CONTRACT}" "${TMP}/inert2.md"; then
  echo "  REFUSED: the inert edit changed nothing, so it is not a control"
  RC=1
else
  check "${TMP}/inert2.md" "inert 2 " consistent
fi
echo

if [ "${RC}" -eq 0 ]; then
  echo "RESULT: live CONSISTENT; BOTH mutants CONTRADICTION (red); BOTH inert"
  echo "        twins CONSISTENT (green). The check reds on the disposition"
  echo "        this arm was ruled out of -- a redirect the server cannot make"
  echo "        safe, because it cannot tell a later game from a conflicting"
  echo "        account of the settled one -- and it reds on it from EITHER of"
  echo "        the two places that could drift, not only the table cell."
  echo "        Neither inert twin reds, so it is the rule being read and not"
  echo "        the whitespace around it."
else
  echo "RESULT: FAILURES above"
fi
echo "finished  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit "${RC}"
