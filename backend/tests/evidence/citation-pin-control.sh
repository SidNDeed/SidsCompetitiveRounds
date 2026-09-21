#!/usr/bin/env bash
# MUTATION CONTROL for a citation that names another document's REVISION, with
# its negative control (#391).
#
#   bash backend/tests/evidence/citation-pin-control.sh <citing-doc> <cited-doc>
#
# BOTH PATHS ARE ARGUMENTS and neither is written down here. The documents this
# lane cites live in the gitignored scratch, and a committed file that names a
# path the repository does not contain is the defect the shipped-file rule
# exists for -- so this instrument names none and the invocation that ran it is
# recorded in the report instead.
#
# WHAT IT CHECKS. The citing document states which revision of the cited
# document it was checked against. The cited document declares its own revision
# on its first line. A citation is stale exactly when those two differ, and a
# stale one is not a cosmetic error: round 8's realignment section was checked
# "gate by gate" against revision 2 of the client-lane method design and carried
# a bullet for a gate -- G5, an operator ordered replay -- that revision 3 had
# already deleted with five named refutations and replaced with a different
# route. A gate-by-gate check against a gate set that no longer exists is a
# check that cannot fail on the thing it is for (#342), and nothing in either
# document could notice, because the number was prose on one side and a heading
# on the other.
#
# THE MUTATION AND ITS NEGATIVE CONTROL both run against COPIES in a temporary
# directory. The real documents are read and never written.
set -u

CITING="${1:?usage: citation-pin-control.sh <citing-doc> <cited-doc>}"
CITED="${2:?usage: citation-pin-control.sh <citing-doc> <cited-doc>}"

echo "script    <repo>/backend/tests/evidence/citation-pin-control.sh"
echo "command   bash <repo>/backend/tests/evidence/citation-pin-control.sh <citing-doc> <cited-doc>"
echo "citing    <the lane's contract, under the gitignored scratch>"
echo "cited     <the client lane's method design, under the gitignored scratch>"
echo "bash      ${BASH_VERSION}"
echo "started   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

for f in "${CITING}" "${CITED}"; do
  [ -f "${f}" ] || { echo "REFUSED: a named document is not a file"; exit 2; }
done

# The revision the CITED document declares for itself, from its first line.
declared() {
  head -1 "$1" | grep -oiE 'revision [0-9]+' | head -1 | tr 'A-Z' 'a-z'
}
# The revision the CITING document says it was checked against. One shape, and
# it has to be a shape that is WRITTEN for this purpose rather than any mention
# of the word: the section states it as `(revision N)` immediately after the
# cited document's file name.
cited_as() {
  grep -oiE 'CLIENT-R4-METHOD-DESIGN\.md` \(revision [0-9]+\)' "$1" \
    | grep -oiE 'revision [0-9]+' | head -1 | tr 'A-Z' 'a-z'
}

RC=0
check() {   # <citing-file> <label> <expect: match|differ>
  local got want
  want="$(declared "${CITED}")"
  got="$(cited_as "$1")"
  if [ -z "${want}" ]; then
    echo "REFUSED: the cited document declares no revision on its first line"
    exit 2
  fi
  if [ -z "${got}" ]; then
    echo "  $2: the citing document states no revision in the pinned shape"
    [ "$3" = "differ" ] || RC=1
    return
  fi
  if [ "${got}" = "${want}" ]; then
    echo "  $2: cites ${got}, cited document declares ${want} -> MATCH"
    [ "$3" = "match" ] || RC=1
  else
    echo "  $2: cites ${got}, cited document declares ${want} -> STALE"
    [ "$3" = "differ" ] || RC=1
  fi
}

echo "cited document declares: $(declared "${CITED}")"
echo

echo "LIVE   the committed state of the two documents"
check "${CITING}" "live    " match
echo

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo "MUTANT the citation is rolled back one revision (the r8 defect, restored)"
sed -E 's/(CLIENT-R4-METHOD-DESIGN\.md` \(revision )[0-9]+\)/\12)/' \
    "${CITING}" > "${TMP}/mutant.md"
if cmp -s "${CITING}" "${TMP}/mutant.md"; then
  echo "  REFUSED: the mutation changed nothing, so it cannot prove anything"
  RC=1
else
  check "${TMP}/mutant.md" "mutant  " differ
fi
echo

echo "INERT  a wording change at the same site, the revision left alone"
sed -E 's/(CLIENT-R4-METHOD-DESIGN\.md` \(revision [0-9]+\)) /\1  /' \
    "${CITING}" > "${TMP}/inert.md"
if cmp -s "${CITING}" "${TMP}/inert.md"; then
  echo "  note: the inert edit found no second space to double; using a"
  echo "        trailing-whitespace edit on the same line instead"
  sed -E 's/(CLIENT-R4-METHOD-DESIGN\.md` \(revision [0-9]+\))/\1 /' \
      "${CITING}" > "${TMP}/inert.md"
fi
if cmp -s "${CITING}" "${TMP}/inert.md"; then
  echo "  REFUSED: the inert edit changed nothing, so it is not a control"
  RC=1
else
  check "${TMP}/inert.md" "inert   " match
fi
echo

if [ "${RC}" -eq 0 ]; then
  echo "RESULT: live MATCH, mutant STALE (red), inert MATCH (green). The check"
  echo "        reds on the edit that actually happens -- a revision moving"
  echo "        under a citation -- and not on a reword beside it."
else
  echo "RESULT: FAILURES above"
fi
echo "finished  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit "${RC}"
