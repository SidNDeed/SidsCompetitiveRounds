#!/usr/bin/env bash
# MUTATION CONTROL for the client contract's settlement rules, with its
# negative controls (#391).
#
#   bash backend/tests/evidence/contract-arm-consistency.sh <contract> [<previous revision>]
#
# THE PATHS ARE ARGUMENTS and are not written down here. The document this lane
# specifies the client half in lives under the gitignored scratch, and a
# committed file that names a path the repository does not contain is the
# defect the shipped-file rule exists for -- so this instrument names none and
# the invocation that ran it is recorded in the report instead.
#
# THE RULE IT HOLDS. A refusal carrying `settled_game` is TERMINAL for the
# entry: it is dropped, the server has already quarantined the payload for
# review, and the seat derives its NEXT key from the advertised number. A
# retryable answer is retried with the SAME body, unchanged, whatever number it
# advertised; the advertisement moves the NEXT game's field only. No report
# entry is ever re-signed, re-keyed or redirected. Both halves exist for one
# reason: a delivery moved to another number can settle one physical game a
# second time -- a second row, a second rating, a second payout -- and the
# server cannot undo that.
#
# TWO CHECKS, because the rule was held by one and the class survived it.
#
#   1. THE STATEMENTS (round 14). The arm table's `409 with settled_game` row
#      says TERMINAL, drop, kept for review, next key from `expected_game`, and
#      no REDIRECT; the recovery section says the same in its own words; the
#      terminal-versus-retryable section says it a third time. Two
#      mutant/inert pairs hold these: one rewrites the table cell, one the
#      status section's sentence.
#
#   2. THE CLASS (round 15), over the WHOLE document. Round 14's check read the
#      three statements above and nothing else, while the document still
#      carried the refuted design elsewhere -- a precedent passage calling the
#      client's one-shot re-signed resend the shape the report path needs, and
#      a redelivery rule that re-signed a retryable entry at its advertised
#      number. Nothing read those sections, so the class survived a check that
#      could not fail on it (#432, #342). contract_arm_rules.py reads every
#      section outside a code fence, finds every re-signing, re-keying,
#      re-filing or redirecting word, every `rewriteOnRefusal`, every send at a
#      moved number and every adoption not said to be the next game's, and
#      requires each to be admitted by its own clause. Its controls PLANT a
#      redirect sentence at three sites the round-14 check never read -- inside
#      section 4's precedent passage, inside the redelivery table, and in the
#      last hundred lines -- and each must red, AT THE PLANTED LINE; each has a
#      twin planted at the same site stating the unchanged resend, which must
#      stay green. The round-14 statement check is run on every plant too, and
#      reads each one CONSISTENT: that is the blindness this round closes,
#      shown rather than asserted.
#
#   A <previous revision>, when given, is the document as the round-10 review
#   read it, and the class scan must RED on it: a scan that passes the
#   revision whose findings it exists for is a scan that cannot see them.
#
# Every copy is written into a temporary directory; the real documents are read
# and never written.
set -u

CONTRACT="${1:?usage: contract-arm-consistency.sh <contract> [<previous revision>]}"
PREVIOUS="${2:-}"
RULES="$(dirname "${BASH_SOURCE[0]}")/contract_arm_rules.py"
PY="${PYTHON:-python}"

echo "script    <repo>/backend/tests/evidence/contract-arm-consistency.sh"
# The capture this script is redirected into, named by the producer --
# see the .gitignore block for this directory.
echo "capture   <repo>/backend/tests/evidence/<round>-contract-arms.log"
echo "command   bash <repo>/backend/tests/evidence/contract-arm-consistency.sh <contract> <previous revision>"
echo "contract  <the lane's client resync contract, under the gitignored scratch>"
if [ -n "${PREVIOUS}" ]; then
  echo "previous  <the same contract as the round-10 review read it, a scratch copy>"
else
  echo "previous  (not supplied)"
fi
echo "rules     <repo>/backend/tests/evidence/contract_arm_rules.py"
echo "bash      ${BASH_VERSION}"
echo "python    $("${PY}" -c 'import sys; print(sys.version.split()[0])')"
echo "started   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

[ -f "${CONTRACT}" ] || { echo "REFUSED: the named document is not a file"; exit 2; }
[ -f "${RULES}" ] || { echo "REFUSED: the class rules are not beside this script"; exit 2; }
if [ -n "${PREVIOUS}" ] && [ ! -f "${PREVIOUS}" ]; then
  echo "REFUSED: the named previous revision is not a file"; exit 2
fi

ROW_RE='^\| \*\*409 with `settled_game`\*\*'

# The row, and its DISPOSITION cell: the pipe-delimited table's third field.
row() { grep -E "${ROW_RE}" "$1" | head -1; }
disposition() { row "$1" | awk -F'|' '{print $3}'; }

RC=0
REDS=0
GREENS=0

# CHECK 1 -- the three statements of the terminal arm.
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
  echo "  $2 statements: disposition ->${disp}"
  echo "  $2 statements: next-key rule stated in the row: ${nextkey}; recovery section drops the same entry: ${recov}; status section states it too: ${sec4}"
  echo "  $2 statements: ${verdict}"
  case "$3" in
    consistent)   [ "${verdict}" = "CONSISTENT" ] || RC=1 ;;
    contradiction) [ "${verdict}" = "CONSISTENT" ] && RC=1 ;;
  esac
}

# CHECK 2 -- the class, over the whole document. The invocation is printed
# before the scan runs, so the result below it can be told from any other.
# <file> <label> <expect: clean|red> [<planted line>] [--all]
classcheck() {
  local file="$1" label="$2" expect="$3" planted="${4:-}" all="${5:-}"
  local out rc unadmitted at_plant shown
  # The two real documents are named by role, never by path; a temporary copy
  # by its own name, which is what the lines above it wrote.
  if [ "${file}" = "${CONTRACT}" ]; then
    shown="<contract>"
  elif [ -n "${PREVIOUS}" ] && [ "${file}" = "${PREVIOUS}" ]; then
    shown="<previous revision>"
  else
    shown="<$(basename "${file}")>"
  fi
  if [ -n "${all}" ]; then
    echo "  invoke   ${PY} <repo>/backend/tests/evidence/contract_arm_rules.py --all ${shown}"
    out="$("${PY}" "${RULES}" --all "${file}")"
  else
    echo "  invoke   ${PY} <repo>/backend/tests/evidence/contract_arm_rules.py ${shown}"
    out="$("${PY}" "${RULES}" "${file}")"
  fi
  rc=$?
  printf '%s\n' "${out}"
  unadmitted="$(printf '%s\n' "${out}" | grep -c '^  UNADMITTED line ')"
  case "${expect}" in
    clean)
      if [ "${rc}" -eq 0 ] && [ "${unadmitted}" -eq 0 ]; then
        echo "  ${label} class: CLEAN (rc=${rc}, unadmitted ${unadmitted}) -- GREEN as expected"
        GREENS=$((GREENS + 1))
      else
        echo "  ${label} class: RED (rc=${rc}, unadmitted ${unadmitted}) -- expected CLEAN"
        RC=1
      fi
      ;;
    red)
      at_plant=0
      if [ -n "${planted}" ]; then
        at_plant="$(printf '%s\n' "${out}" | grep -c "^  UNADMITTED line ${planted} ")"
      fi
      # A planted sentence can carry more than one operation (a re-key AND a
      # send at the moved number), so "at the planted line and nowhere else"
      # is every unadmitted occurrence being on that line, however many.
      if [ "${rc}" -eq 1 ] && [ "${unadmitted}" -ge 1 ] \
         && { [ -z "${planted}" ] || [ "${at_plant}" -eq "${unadmitted}" ]; }; then
        if [ -n "${planted}" ]; then
          echo "  ${label} class: RED at the planted line ${planted} and nowhere else (rc=${rc}, unadmitted ${unadmitted}) -- RED as expected"
        else
          echo "  ${label} class: RED (rc=${rc}, unadmitted ${unadmitted}) -- RED as expected"
        fi
        REDS=$((REDS + 1))
      else
        echo "  ${label} class: rc=${rc}, unadmitted ${unadmitted}, at the planted line ${at_plant} -- expected RED at line ${planted:-any}"
        RC=1
      fi
      ;;
  esac
}

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo "LIVE     the document as this round leaves it"
check "${CONTRACT}" "live    " consistent
classcheck "${CONTRACT}" "live    " clean "" --all
echo

if [ -n "${PREVIOUS}" ]; then
  echo "PREVIOUS the revision the round-10 review read, which this scan exists to see"
  check "${PREVIOUS}" "previous" consistent
  classcheck "${PREVIOUS}" "previous" red
  echo
fi

echo "MUTANT 1 the table row REDIRECTS again (the round-9 HIGH, restored)"
echo "  invoke   awk: rewrite the 409-with-settled_game row's disposition cell to REDIRECT, into <mutant.md>"
awk -F'|' 'BEGIN{OFS="|"} /^\| \*\*409 with `settled_game`\*\*/ {$3=" REDIRECT - keep the entry, re-sign it ONCE at the advertised expected_game, submit "} 1' \
    "${CONTRACT}" > "${TMP}/mutant.md"
if cmp -s "${CONTRACT}" "${TMP}/mutant.md"; then
  echo "  REFUSED: the mutation changed nothing, so it cannot prove anything"
  RC=1
else
  check "${TMP}/mutant.md" "mutant 1" contradiction
  classcheck "${TMP}/mutant.md" "mutant 1" red
fi
echo

echo "INERT 1  a doubled space inside that same cell, the rule left alone"
echo "  invoke   sed: double the space after the cell's TERMINAL phrase, into <inert.md>"
sed 's/^\(| \*\*409 with `settled_game`\*\* | TERMINAL for the entry\) /\1  /' \
    "${CONTRACT}" > "${TMP}/inert.md"
if cmp -s "${CONTRACT}" "${TMP}/inert.md"; then
  echo "  REFUSED: the inert edit changed nothing, so it is not a control"
  RC=1
else
  check "${TMP}/inert.md" "inert 1 " consistent
  classcheck "${TMP}/inert.md" "inert 1 " clean
fi
echo

echo "MUTANT 2 the STATUS SECTION makes the same answer retryable, table intact"
echo "  invoke   sed: rewrite the status section's TERMINAL sentence to RETRYABLE with a re-sign, into <mutant2.md>"
sed 's|^- \*\*an answer carrying `settled_game` is TERMINAL for the entry\.\*\*|- **an answer carrying `settled_game` is RETRYABLE - re-sign the entry ONCE at the advertised number.**|' \
    "${CONTRACT}" > "${TMP}/mutant2.md"
if cmp -s "${CONTRACT}" "${TMP}/mutant2.md"; then
  echo "  REFUSED: the mutation changed nothing, so it cannot prove anything"
  RC=1
else
  check "${TMP}/mutant2.md" "mutant 2" contradiction
  classcheck "${TMP}/mutant2.md" "mutant 2" red
fi
echo

echo "INERT 2  a doubled space after that same sentence, the rule left alone"
echo "  invoke   sed: double the space after that sentence, into <inert2.md>"
sed 's|^\(- \*\*an answer carrying `settled_game` is TERMINAL for the entry\.\*\*\) |\1  |' \
    "${CONTRACT}" > "${TMP}/inert2.md"
if cmp -s "${CONTRACT}" "${TMP}/inert2.md"; then
  echo "  REFUSED: the inert edit changed nothing, so it is not a control"
  RC=1
else
  check "${TMP}/inert2.md" "inert 2 " consistent
  classcheck "${TMP}/inert2.md" "inert 2 " clean
fi
echo

# THE PLANTS. Each site is one the round-14 statement check never read, and
# each plant is followed by its same-site twin.
for SITE in A B C; do
  for KIND in redirect unchanged; do
    if [ "${KIND}" = "redirect" ]; then
      echo "PLANT ${SITE}  a redirect sentence, written as a rule"
    else
      echo "TWIN ${SITE}   the unchanged-resend sentence at the same site"
    fi
    COPY="${TMP}/plant-${SITE}-${KIND}.md"
    echo "  invoke   ${PY} <repo>/backend/tests/evidence/contract_arm_rules.py --plant ${SITE} ${KIND} <contract> <$(basename "${COPY}")>"
    PLANTED_OUT="$("${PY}" "${RULES}" --plant "${SITE}" "${KIND}" "${CONTRACT}" "${COPY}")"
    PRC=$?
    printf '%s\n' "${PLANTED_OUT}"
    LINE="$(printf '%s\n' "${PLANTED_OUT}" | sed -n 's/^  planted  [a-z]* sentence at line \([0-9][0-9]*\) of .*/\1/p')"
    if [ "${PRC}" -ne 0 ] || [ -z "${LINE}" ] || cmp -s "${CONTRACT}" "${COPY}"; then
      echo "  REFUSED: the plant did not land, so it cannot prove anything"
      RC=1
      echo
      continue
    fi
    if [ "${KIND}" = "redirect" ]; then
      check "${COPY}" "plant ${SITE} " consistent
      classcheck "${COPY}" "plant ${SITE} " red "${LINE}"
    else
      check "${COPY}" "twin ${SITE}  " consistent
      classcheck "${COPY}" "twin ${SITE}  " clean
    fi
    echo
  done
done

echo "tally     class scans RED as expected: ${REDS}; class scans CLEAN as expected: ${GREENS}"
if [ "${RC}" -eq 0 ]; then
  echo "RESULT: live CONSISTENT and CLEAN; both statement mutants CONTRADICTION"
  echo "        and RED on the class scan; both statement twins CONSISTENT and"
  echo "        CLEAN; each of the three planted redirect sentences RED at its"
  echo "        own planted line and nowhere else, while the round-14 statement"
  echo "        check read every one of them CONSISTENT; each same-site"
  echo "        unchanged-resend twin CLEAN. The class is read over the whole"
  echo "        document, so a redirect written back into any section reds, and"
  echo "        a sentence stating the unchanged resend in the same words does"
  echo "        not."
else
  echo "RESULT: FAILURES above"
fi
echo "finished  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit "${RC}"
