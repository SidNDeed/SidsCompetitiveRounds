#!/usr/bin/env bash
# The assembler's closing run, COMMITTED as a producer rather than typed.
#
# The r7 lens found the last thing in this directory that was still orchestrated
# by hand: every number in every report is derived from a committed instrument's
# stdout, and the report that says so was itself assembled from a log no
# committed file produces. A log with no producer is a log whose blocks can
# drift without a diff -- one could be dropped, re-ordered or re-run against a
# different report and nothing here would notice.
#
# So this script IS that producer. Its stdout is the log the round's assembly
# report names, and the report is rebuilt from those bytes by
# assemble-evidence.py like every other report here:
#
#   bash backend/tests/evidence/run-assembly.sh \
#     > backend/tests/evidence/r<round>-suites-assembly-run.log
#
# THE ROUND IS DERIVED, never passed and never baked in. A round number written
# into a script is a thing to remember to bump, and a forgotten one makes this
# round's run check the previous round's reports and report success -- the
# defect this directory has now closed four times (SUITES, the re-pin names,
# SUITE_TAG, the new-controls anchors). The newest `-suites.txt` in this
# directory is this round's by construction: the suite pair runs before the
# assembly, and every earlier round's reports are committed.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(cd "${HERE}/../.." && pwd)"
REPO="$(cd "${BACKEND}/.." && pwd)"

cd "${REPO}" || exit 1

ROUND="$(ls "${HERE}" \
  | sed -n 's/^r\([0-9][0-9]*\)-suites\.txt$/\1/p' | sort -n | tail -1)"
if [ -z "${ROUND}" ]; then
  echo "REFUSED: this directory carries no round-numbered suites report, so" >&2
  echo "         the round this assembly belongs to cannot be derived." >&2
  exit 2
fi

ASSEMBLER="backend/tests/evidence/assemble-evidence.py"

# One block per check: the title, the working directory, THE COMMAND, then the
# output it produced and its rc. The command line is last of the three header
# lines and immediately above its own output, because the invocation rule this
# directory enforces reads upward from a result and stops at the first line it
# does not recognise as a tool's own frame.
block() {
  local title="$1"; shift
  local tag="$1"; shift
  echo "== ${title} =="
  echo "cwd       <repo>"
  echo "command   $*"
  "$@"
  echo "${tag} rc=$?"
  echo ""
}

echo "== the producer of this log =="
echo "script    <repo>/backend/tests/evidence/run-assembly.sh"
echo "cwd       <repo>"
echo "python    $(python -V 2>&1)"
# The capture this script is redirected into, named by the producer -- see the
# .gitignore block for this directory, which admits one pattern per producer.
echo "capture   <repo>/backend/tests/evidence/r${ROUND}-suites-assembly-run.log"
echo "round     r${ROUND}, derived from the newest -suites.txt beside this script"
echo ""

block "the assembler's own self-test, both directions on every rule" \
      "selftest" python "${ASSEMBLER}" --selftest

# EVERY REPORT OF THIS ROUND, derived from the directory rather than listed.
# A report added to the round and left out of a hand-written list would be the
# one report nobody re-derived.
for report in $(ls "${HERE}" | sed -n "s/^\(r${ROUND}-.*\.txt\)$/\1/p" | sort); do
  case "${report}" in
    *-suites-assembly.txt|*-repin.txt) continue ;;   # written after this run
  esac
  block "${report}, re-derived from the stdout it names" "check" \
        python "${ASSEMBLER}" --check "backend/tests/evidence/${report}"
done

# THE REFUSAL, EXECUTED. A rule nobody has seen refuse is a rule nobody has
# seen. The pair is fabricated here so the direction is proved on the RULE
# rather than on whatever this directory happens to hold.
echo "== the REFUSAL, executed rather than described =="
echo "cwd       <repo>"
UNDRIVABLE='import sys; sys.stdout.reconfigure(newline=chr(10)); import importlib.util as u; s=u.spec_from_file_location("a","backend/tests/evidence/assemble-evidence.py"); m=u.module_from_spec(s); s.loader.exec_module(m); print("undrivable  ->", m.undrivable("the run hashed 12 paths", "9 paths"))'
echo "command   python -c \"${UNDRIVABLE}\""
python -c "${UNDRIVABLE}"
echo "refusal rc=$?"
echo ""

echo "== ...and the same rule stays quiet on a claim the run DID print =="
echo "cwd       <repo>"
DERIVABLE='import sys; sys.stdout.reconfigure(newline=chr(10)); import importlib.util as u; s=u.spec_from_file_location("a","backend/tests/evidence/assemble-evidence.py"); m=u.module_from_spec(s); s.loader.exec_module(m); print("derivable   ->", m.undrivable("the run hashed 9 paths", "9 paths"))'
echo "command   python -c \"${DERIVABLE}\""
python -c "${DERIVABLE}"
echo "clean rc=$?"
echo ""

# THE CLOSING CHECK, which RUNS the assembler rather than describing it. It
# also gives this log the one thing the committed-evidence rule requires of
# every report of a round: an EXECUTED result. A report whose run carries no
# result line is a narrative, and the rule refuses it -- which is how the
# absence of this block was found.
echo "== the closing evidence check, which RUNS the assembler =="
echo "The assembler is not a step somebody remembers to take: the committed"
echo "check below runs its self-test and re-checks every assembled report of"
echo "the newest round, so a report that stopped matching its own stdout reds"
echo "in the suite rather than in a log nobody re-reads."
echo "cwd       <repo>/backend"
echo 'command   python -m pytest tests/test_ffa_game_number_anchor.py -q -p no:cacheprovider -k "committed_evidence or assembled_from_its_run"'
( cd "${BACKEND}" && python -m pytest tests/test_ffa_game_number_anchor.py -q -p no:cacheprovider -k "committed_evidence or assembled_from_its_run" )
echo "closing rc=$?"
echo ""

echo "== done =="
