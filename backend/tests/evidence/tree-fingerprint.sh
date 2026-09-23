#!/usr/bin/env bash
# THE STATE OF THE WORKING TREE, as one value, recomputed from scratch at every
# call.
#
#   bash backend/tests/evidence/tree-fingerprint.sh <repository-root>
#
# Printed as `<md5>  <repository-relative path>` lines, sorted. A caller takes
# it before a long run and again after, and compares the two.
#
# WHY IT IS ITS OWN INSTRUMENT, AND WHY IT RE-DERIVES THE SET EVERY TIME.
# Round 8 did this inline in run-both-suites.sh and captured the file list ONCE,
# from `git diff --name-only HEAD` -- the tracked files that already differed
# from HEAD when the run started -- then hashed that same captured list before
# and after. Two whole edit classes were therefore invisible to it:
#
#   * a tracked file that was byte-identical to HEAD at capture and is edited
#     during the run is in neither list, so neither hash covers it;
#   * a file CREATED during the run is not tracked, was not in the capture, and
#     is never hashed at all -- and `pytest tests/` collects a directory, so a
#     new test file means the second half ran a different selection than the
#     first.
#
# In both cases the two hashes compared equal and the run printed UNCHANGED over
# a tree it did not have: a check that cannot fail on the class it exists for
# (#342), which is the same shape as a hand-written list of a set that grows.
# The fix is not a longer list. The SET is derived at each call, and the paths
# are part of the printed value, so an addition or a removal moves the
# fingerprint even when every file that survives is untouched.
#
# Two commands make the set, and between them they cover everything a run can
# read out of this repository:
#   git diff --name-only HEAD        tracked files differing from HEAD, now
#   git ls-files --others            files present but not tracked
#         --exclude-standard
#
# IGNORED PATHS ARE DELIBERATELY OUT. `--exclude-standard` drops what
# .gitignore drops, which is what lets a round edit its own notes and its
# contract under the gitignored scratch while a 23-minute suite pair runs --
# no suite reads them. The consequence is a rule for the caller rather than a
# hole: anything a run WRITES inside the repository and does not ignore will
# move this value, correctly, so a suite runner must write its logs outside the
# repository. Round 8 learned that the other way round, from a run that wrote
# its report into the directory a test inspects.
#
# It reads the tree and writes nothing.
set -u

REPO="${1:?usage: tree-fingerprint.sh <repository-root>}"
cd "${REPO}" || exit 1

{
  git diff --name-only HEAD 2>/dev/null
  git ls-files --others --exclude-standard 2>/dev/null
} | sort -u | while IFS= read -r f; do
  [ -n "${f}" ] || continue
  # A path that is listed but cannot be read -- a tracked file deleted from the
  # worktree -- prints an EMPTY hash rather than being skipped. Skipping it
  # would let a deletion mid-run compare equal, which is the same blindness one
  # class over.
  printf '%s  %s\n' "$(md5sum -- "${f}" 2>/dev/null | cut -d' ' -f1)" "${f}"
done
