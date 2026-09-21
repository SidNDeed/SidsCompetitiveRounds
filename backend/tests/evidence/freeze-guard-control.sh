#!/usr/bin/env bash
# MUTATION CONTROL for the suite runner's tree-freeze guard, with its negative
# control (#391).
#
#   bash backend/tests/evidence/freeze-guard-control.sh
#
# The guard's job is to answer one question: did the tree move while the
# 23-minute suite pair ran? A guard that answers "no" for an edit class it
# cannot see is worse than no guard, because the report then carries UNCHANGED
# over a tree the run did not have (#342). So this control does not ask whether
# the guard runs. It performs each edit class and requires the guard to NOTICE,
# and it performs no edit at all and requires the guard to stay quiet.
#
# It also runs ROUND 8'S OWN METHOD over the same two mutations, side by side.
# That half is the negative result that makes the finding concrete rather than
# argued: the captured-once list reports UNCHANGED for both, which is what the
# committed r8-suites.txt line was asserting.
#
# Every file it touches is restored from a byte-exact copy taken here -- never
# `git checkout --` or `git restore`, which are forbidden on a tree carrying
# uncommitted work (#290/#401) -- and the whole tree fingerprint is compared
# against the starting one at the end, so the control proves its own cleanup.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${HERE}/../../.." && pwd)"
FP="${HERE}/tree-fingerprint.sh"

echo "script    <repo>/backend/tests/evidence/freeze-guard-control.sh"
echo "cwd       <repo>"
echo "command   bash <repo>/backend/tests/evidence/freeze-guard-control.sh"
echo "guard     bash <repo>/backend/tests/evidence/tree-fingerprint.sh <repo>"
echo "bash      ${BASH_VERSION}"
echo "started   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

RC=0
note() { echo "$@"; }
fail() { echo "FAILED: $*"; RC=1; }

fingerprint() { bash "${FP}" "${REPO}"; }

# ── round 8's method, reproduced exactly, for the side-by-side ───────────────
R8FILES="$(git -C "${REPO}" diff --name-only HEAD 2>/dev/null | sort)"
r8_hash() {
  printf '%s\n' "${R8FILES}" | grep . | while IFS= read -r f; do
    printf '%s  %s\n' "$(md5sum "${REPO}/${f}" 2>/dev/null | cut -d' ' -f1)" "${f}"
  done
}

# The two probe targets.
UNTRACKED="${REPO}/backend/tests/freeze_guard_probe.tmp"
TRACKED_REL="backend/sql/169_match_report_quarantine.sql"
TRACKED="${REPO}/${TRACKED_REL}"
ASIDE="$(mktemp)"

# PRE-CHECK, before anything is measured: the tracked probe target has to be
# byte-identical to HEAD right now, or the class it stands for is not the class
# being tested and a pass would mean nothing.
if printf '%s\n' "${R8FILES}" | grep -qx "${TRACKED_REL}"; then
  echo "REFUSED: ${TRACKED_REL} already differs from HEAD, so it cannot stand"
  echo "         for the class 'byte-identical at capture, edited mid-run'"
  exit 2
fi
if [ -e "${UNTRACKED}" ]; then
  echo "REFUSED: the untracked probe path already exists"
  exit 2
fi
note "pre-check the tracked probe target is byte-identical to HEAD, and the"
note "          untracked probe path does not exist"
echo

BASE="$(fingerprint)"
R8BASE="$(r8_hash)"
BASE_MD5="$(md5sum "${TRACKED}" | cut -d' ' -f1)"
cp -p "${TRACKED}" "${ASIDE}"
# The command that produced this baseline, immediately above the baseline. The
# header at the top of this log names it too, but a header is shared by every
# block below it, and the rule this directory enforces reads UPWARD from a
# result and requires the command to be the nearest substantive line above it.
# The pre-check notes above break that scan -- correctly, since they are this
# script's own prose rather than a tool's frame. Round 10 added the rule, and
# this baseline is the line it found.
echo "command   bash <repo>/backend/tests/evidence/tree-fingerprint.sh <repo>"
note "baseline  $(printf '%s\n' "${BASE}" | grep -c .) paths fingerprinted; round-8 method holds $(printf '%s\n' "${R8FILES}" | grep -c .) captured paths"
echo

# ── NEGATIVE CONTROL: no edit at all ────────────────────────────────────────
INERT="$(fingerprint)"
if [ "${BASE}" = "${INERT}" ]; then
  note "GREEN  inert    no edit between two calls -> fingerprint unchanged"
else
  fail "the fingerprint moved with no edit; it measures something other than the tree"
  diff <(printf '%s\n' "${BASE}") <(printf '%s\n' "${INERT}") || true
fi
echo

# ── CLASS A: a file CREATED during the run ──────────────────────────────────
printf 'probe\n' > "${UNTRACKED}"
AFTER_A="$(fingerprint)"
R8_A="$(r8_hash)"
if [ "${BASE}" != "${AFTER_A}" ]; then
  note "RED    class A  a file created mid-run -> fingerprint MOVED (detected)"
  diff <(printf '%s\n' "${BASE}") <(printf '%s\n' "${AFTER_A}") | sed 's/^/           /' || true
else
  fail "class A: a file created mid-run did not move the fingerprint"
fi
if [ "${R8BASE}" = "${R8_A}" ]; then
  note "       round 8  the captured-once list reports UNCHANGED for the same edit"
else
  fail "class A: round 8's method detected this, so the finding is misstated"
fi
rm -f "${UNTRACKED}"
echo

# ── CLASS B: a tracked file byte-identical to HEAD, edited during the run ───
printf '\n-- freeze-guard probe line\n' >> "${TRACKED}"
AFTER_B="$(fingerprint)"
R8_B="$(r8_hash)"
if [ "${BASE}" != "${AFTER_B}" ]; then
  note "RED    class B  an unmodified tracked file edited mid-run -> fingerprint MOVED (detected)"
  diff <(printf '%s\n' "${BASE}") <(printf '%s\n' "${AFTER_B}") | sed 's/^/           /' || true
else
  fail "class B: an edit to an unmodified tracked file did not move the fingerprint"
fi
if [ "${R8BASE}" = "${R8_B}" ]; then
  note "       round 8  the captured-once list reports UNCHANGED for the same edit"
else
  fail "class B: round 8's method detected this, so the finding is misstated"
fi

# ── restore, and prove it ───────────────────────────────────────────────────
cp -p "${ASIDE}" "${TRACKED}"
rm -f "${ASIDE}"
echo
END_MD5="$(md5sum "${TRACKED}" | cut -d' ' -f1)"
if [ "${BASE_MD5}" = "${END_MD5}" ]; then
  note "restored ${TRACKED_REL} md5 ${END_MD5} matches the pre-run md5"
else
  fail "restore: ${TRACKED_REL} did not come back byte-identical"
fi
FINAL="$(fingerprint)"
if [ "${BASE}" = "${FINAL}" ]; then
  note "restored the whole-tree fingerprint is back to its pre-control value"
else
  fail "restore: the tree did not come back"
  diff <(printf '%s\n' "${BASE}") <(printf '%s\n' "${FINAL}") || true
fi
echo
if [ "${RC}" -eq 0 ]; then
  echo "RESULT: 1 inert GREEN, 2 mutation classes RED under the new guard and"
  echo "        UNDETECTED under round 8's, every touched file restored"
else
  echo "RESULT: FAILURES above"
fi
echo "finished  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit "${RC}"
