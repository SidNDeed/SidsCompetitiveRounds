#!/usr/bin/env bash
# ft_vm_leased.sh <menu|match> <outdir> <lane-frametime.dll> <lanes-folder> [--dry]: one FrameTime launch on the VM
# seat UNDER the broadcast pause lease (ruling FRAME-TIME-ROUND-R4), the integrator's to run. Round 6 (ruling
# FRAME-TIME-ROUND-R5): the INSTALL and its RESTORATION sit inside the lease, and VR6's file inventories are written
# into <outdir>. Order:
#   1. the lease: pause.ps1 -Holder frame-time. A4 (R6-A3.11.18): the lease counts as HELD from the moment the pause
#      returns success (exit 0, or its "Broadcast bot PAUSED; holder" line); the -Status reading after it only
#      confirms (its holder table names frame-time). A refused pause is followed by one status reading: a lease it
#      shows, or a reading that fails, also counts as held, so the exit path below releases it;
#   2. the leased shutdown: the bot's game quit (quit_game.ps1), then ROUNDS proven not running;
#   3. the VM launch gate under the lease: first the settle window (ft_settle_diskq.ps1, R6-A3.11.10 FIX-8), then
#      s0_gate.ps1, unchanged (two disk-queue pairs);
#   4. the PRE inventory (<outdir>/inventory-pre.txt): sha256 of every file in the plugins folder and the config
#      folder and of the five logs; pre-image copies of the installed DLL, the cfg and each present log into
#      <outdir>/pre/, each proven; the sentinel proven absent; ft_vm_install.sh status proven to show no open install;
#   5. A3: the rollback is ARMED (INSTALL_STARTED=1) before the install's first write; then the install
#      (ft_vm_install.sh install), the sentinel armed, ft_vm_launch.ps1.
# THE EXIT PATH (trap EXIT, R6-A3.11.18 CLASS A): an ordered chain of PROVEN states with exactly two ends.
#   - lease not held: nothing to release.
#   - the run ended before the first write (INSTALL_STARTED=0): the release, proven (A5).
#   - otherwise A2, the exit proven first: while one reading of the process table does not show "no ROUNDS", a ROUNDS
#     is closed BY IDENTITY when the pid file exists (ft_close_leased.ps1: one process object, A1); identity shown
#     and the close failed: that object was stopped at the bound and the rig's lever is NEVER used; identity not
#     shown (no pid file, or the close lib's code 7): the lever (quit_game.ps1, R6-A3.11.10). Then one reading must
#     find no ROUNDS process, else the end is HELD and no disarm, VR6, revert or restore step runs.
#     Then: the sentinel removed (proven absent); VR6 (ft_vr6_check); A3 the revert (ft_vm_install.sh revert, then
#     the pre-image copied back if the installed DLL still differs; it ends with the installed DLL's digest equal to
#     the pre-image's, else HELD); the restoration and the POST inventory (ft_restore_check). The revert's pre-image
#     copy and the restoration each read the process table again first (ft_still_gone, R6-A3.11.48 M1): a ROUNDS
#     present or a table unread there ends HELD with nothing more written.
#   - A5: the release only on proof: no failure (bad=0), POST inventory equal to PRE over every file, the installed
#     DLL's digest equal to its pre-image's and the sentinel absent. The release itself is proven by resume.ps1's
#     exit code 0 AND a -Status reading (exit 0, its holder table printed) without the holder frame-time:
#     "FT-VM-LEASE RELEASED proven"; otherwise "FT-VM-LEASE RELEASE-UNPROVEN" and rc 31. Every other case is HELD:
#     the lease kept, the bot stays paused, "FT-VM-LEASE HELD reason=<r>" and rc 30; the integrator restores from
#     <outdir>/pre and releases by hand. A VR6 failure is one of those cases (bad=1): HELD, never released.
# --dry stops after the gate (s0_gate -Dry; nothing inventoried, installed, armed or launched; the release follows).
# Exit: 0 the launch saw its end line and every check after it held; 2 usage, or a step before the first write
# refused; 10 gate refused; 20 lease not confirmed; 21 ROUNDS still running after the leased shutdown; 22 the install
# refused or an install is already open; 30 HELD; 31 the release unproven; otherwise the launch script's code. Every
# end prints "FT-VM-LEASED <mode> end rc=<n>" as its last line.
#
# Dry tests only (never set on a real run): FT_VM_TEST_DIR re-roots the game at $FT_VM_TEST_DIR/game, runs the
# install step from $FT_VM_TEST_DIR/bin/ft_vm_install.sh, reads the process table from $FT_CLOSE_TEST_DIR/procs.txt
# (the close lib's dry table; with $FT_CLOSE_TEST_DIR/procs.unreadable present the reading fails), shortens the 3 s
# waits, and may fix the run stamp (FT_VM_TEST_RUNSTAMP). It refuses unless FT_CLOSE_TEST_DIR is set and the
# first powershell on PATH is $FT_VM_TEST_DIR/shim/powershell (the stand-in dispatcher), so a test run can reach no
# C:\broadcast lever and no game file.
set -u
MODE="${1:?menu|match}"; OUT="${2:?outdir}"; DLL="${3:-}"; LANES="${4:-}"; DRY="${5:-}"
case "$MODE" in menu) N=1;; match) N=2;; *) echo "usage: ft_vm_leased.sh <menu|match> <outdir> <dll> <lanes> [--dry]"; exit 2;; esac
if [ "$DLL" = "--dry" ]; then DRY="--dry"; DLL=""; LANES=""; fi
if [ "$DRY" != "--dry" ] && { [ ! -f "$DLL" ] || [ ! -d "$LANES" ]; }; then
  echo "usage: ft_vm_leased.sh <menu|match> <outdir> <lane-frametime.dll> <lanes-folder> [--dry]"; exit 2
fi
R=C:/Users/Sid/Documents/SidsCompetitiveRounds
HERE="$(cd "$(dirname "$0")" && pwd)"
GAME="C:/Program Files (x86)/Steam/steamapps/common/ROUNDS"
INSTALL="$HERE/ft_vm_install.sh"
NAP=3
if [ -n "${FT_VM_TEST_DIR:-}" ]; then
  [ -n "${FT_CLOSE_TEST_DIR:-}" ] || { echo "ft_vm_leased.sh: FT_VM_TEST_DIR without FT_CLOSE_TEST_DIR: refused"; exit 2; }
  [ "$(command -v powershell)" = "$FT_VM_TEST_DIR/shim/powershell" ] || { echo "ft_vm_leased.sh: test mode without the stand-in shim first on PATH: refused"; exit 2; }
  GAME="$FT_VM_TEST_DIR/game"; INSTALL="$FT_VM_TEST_DIR/bin/ft_vm_install.sh"; NAP=0.1
fi
BEP="$GAME/BepInEx"
CFG="$BEP/config/com.competitiverounds.mod.cfg"
PLUGDIR="$BEP/plugins/CompetitiveRounds"
PLUG="$PLUGDIR/CompetitiveRounds.dll"
ARM="$BEP/frametime/arm"
CONFDIR="$BEP/config"
LOW="${FT_VM_LOCALLOW:-C:/Users/Sid/AppData/LocalLow}"
PL="$LOW/Landfall Games/ROUNDS"
for pub in "Landfall Games" "Landfall"; do [ -f "$LOW/$pub/ROUNDS/Player.log" ] && { PL="$LOW/$pub/ROUNDS"; break; }; done
LOGN=(LogOutput.log LogOutput-prev.log output_log.txt Player.log Player-prev.log)
LOGP=("$BEP/LogOutput.log" "$BEP/LogOutput-prev.log" "$GAME/output_log.txt" "$PL/Player.log" "$PL/Player-prev.log")
RUNSTAMP=$(date -u +%Y%m%dT%H%M%SZ)
[ -n "${FT_VM_TEST_DIR:-}" ] && [ -n "${FT_VM_TEST_RUNSTAMP:-}" ] && RUNSTAMP=$FT_VM_TEST_RUNSTAMP
# st, sha, inventory, ft_vr6_check, ft_restore_check, ft_rc_verdict (FIX-10, R6-A3.11.14)
. "$HERE/ft_vm_restore.sh" || { echo "ft_vm_leased.sh: ft_vm_restore.sh not loaded"; exit 2; }
# rounds_state: yes | no | unknown. One reading of the whole process table by image name (tasklist without /FI,
# lesson 799); nothing is read by number. A reading that fails, or a listing too short to be the table, is
# "unknown", never "no".
rounds_state() {
  local out rc
  if [ -n "${FT_VM_TEST_DIR:-}" ]; then
    if [ -e "$FT_CLOSE_TEST_DIR/procs.unreadable" ]; then echo unknown; return; fi
    if [ -f "$FT_CLOSE_TEST_DIR/procs.txt" ] && grep -q '^ROUNDS:' "$FT_CLOSE_TEST_DIR/procs.txt"; then echo yes; else echo no; fi
    return
  fi
  out=$(/c/Windows/System32/tasklist.exe); rc=$?
  if [ "$rc" -ne 0 ] || [ "$(printf '%s\n' "$out" | grep -ci '\.exe ')" -lt 5 ]; then echo unknown; return; fi
  if printf '%s\n' "$out" | grep -qi '^ROUNDS\.exe '; then echo yes; else echo no; fi
}
# rig <name> <args...>: one call to C:\broadcast\<name>.ps1, its output CR-stripped; returns that script's exit code
rig() { local s="$1"; shift; powershell -NoProfile -File "C:/broadcast/$s.ps1" "$@" | tr -d '\r'; return "${PIPESTATUS[0]}"; }
holder_shown() { printf '%s\n' "$1" | grep -qE '^  frame-time  \(since '; }
table_shown() { printf '%s\n' "$1" | grep -qE '^holders(: none| \([0-9]+\):)$'; }
[ -e "$OUT" ] && { echo "$(st) FT-VM-LEASED REFUSED: $OUT exists (a fresh folder per run)"; exit 2; }
mkdir -p "$OUT" || exit 2
PRE="$OUT/pre"
PIDF="$OUT/launch-$MODE.pid"
LEASED=0
INSTALL_STARTED=0
PRE_DLL=""
DLL_EQ=0
POST_EQ=0
bad=0
# A5: the release and its proof
ft_release() {
  local rrc srcv out
  echo "$(st) FT-VM-LEASED lease release resume.ps1 -Holder frame-time"
  rig resume -Holder frame-time; rrc=$?
  out=$(rig pause -Status); srcv=$?
  printf '%s\n' "$out"
  if [ "$rrc" = 0 ] && [ "$srcv" = 0 ] && table_shown "$out" && ! holder_shown "$out"; then
    echo "FT-VM-LEASE RELEASED proven: resume.ps1 rc 0; pause.ps1 -Status rc 0, its holder table without frame-time; at $(st)"
  else
    echo "FT-VM-LEASE RELEASE-UNPROVEN resume.ps1 rc=$rrc; pause.ps1 -Status rc=$srcv, holder table $(table_shown "$out" && echo printed || echo ABSENT), frame-time $(holder_shown "$out" && echo STILL-SHOWN || echo not-shown); at $(st)"
    rc=31
  fi
}
ft_hold() {
  echo "FT-VM-LEASE HELD reason=$1: the lease kept (holder frame-time), the bot stays paused; restore from $PRE and release by hand; at $(st)"
  rc=30
}
# A2: no disarm, VR6, revert or restore step runs while any ROUNDS process exists
ft_exit_proven() {
  local s crc i
  s=$(rounds_state)
  if [ "$s" != no ]; then
    echo "$(st) FT-VM-LEASED a ROUNDS process may exist at cleanup (reading: $s)"
    crc=7
    if [ -f "$PIDF" ]; then
      echo "$(st) FT-VM-LEASED close by identity ($PIDF)"
      powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$HERE/ft_close_leased.ps1")" -PidFile "$(cygpath -w "$PIDF")" | tr -d '\r'
      crc=${PIPESTATUS[0]}
      echo "$(st) FT-VM-LEASED close by identity rc=$crc"
    else
      echo "$(st) FT-VM-LEASED no pid file: identity not shown"
    fi
    if [ "$crc" = 7 ]; then
      echo "$(st) FT-VM-LEASED identity not shown: the rig's lever, quit_game.ps1 -Holder frame-time (R6-A3.11.10)"
      rig quit_game -Holder frame-time; crc=$?
      echo "$(st) FT-VM-LEASED lever rc=$crc"
      for i in $(seq 1 20); do [ "$(rounds_state)" = no ] && break; sleep "$NAP"; done
    else
      echo "$(st) FT-VM-LEASED identity shown (close rc $crc): the lever is not used"
    fi
  fi
  s=$(rounds_state)
  if [ "$s" = no ]; then echo "$(st) FT-VM-LEASED exit proven: no ROUNDS process in one reading of the process table"; return 0; fi
  echo "$(st) FT-VM-LEASED exit NOT proven (reading: $s): no disarm, VR6, revert or restore step runs"
  [ "$s" = unknown ] && GONE="process-table-unreadable" || GONE="rounds-still-running"
  return 1
}
# A2 at the writes after the exit was proven (R6-A3.11.48 M1): a ROUNDS can appear after ft_exit_proven's reading
# (a Steam launch request still outstanding). ft_vm_install.sh revert refuses while ROUNDS runs (its line 59); the
# copy below and the restoration must refuse the same way. ft_still_gone <step> reads the table once more with
# rounds_state, this script's one reader of it, which reads a failed reading as "unknown", and returns 0 only on
# "no". Otherwise it sets GONE to the step's reason token and returns 1, and the caller writes nothing more: the end
# is HELD.
ft_still_gone() {
  local s; s=$(rounds_state)
  [ "$s" = no ] && return 0
  echo "$(st) FT-VM-LEASED $1 REFUSED: the process table reads '$s' (a ROUNDS process, or the table unread): nothing copied, no restoration step runs"
  [ "$s" = unknown ] && GONE="process-table-unreadable-at-$1" || GONE="rounds-running-at-$1"
  return 1
}
# A3: the revert ends with the installed DLL's digest equal to the pre-image's. Returns 2 when the pre-image copy is
# refused by ft_still_gone (nothing copied); 0 otherwise.
ft_revert() {
  local r now
  bash "$INSTALL" revert; r=$?
  echo "$(st) FT-VM-LEASED revert rc=$r"
  now=$(sha "$PLUG")
  if [ "$now" != "$PRE_DLL" ]; then
    ft_still_gone revert || return 2
    echo "$(st) FT-VM-LEASED installed DLL $now is not the pre-image $PRE_DLL: the pre-image copied back"
    cp -p "$PRE/CompetitiveRounds.dll" "$PLUG"
    now=$(sha "$PLUG")
  fi
  if [ "$now" = "$PRE_DLL" ]; then DLL_EQ=1; echo "$(st) FT-VM-REVERT proven: the installed DLL $now equals its pre-image"
  else echo "$(st) FT-VM-REVERT FAILED: the installed DLL $now, its pre-image $PRE_DLL"; bad=1; fi
  return 0
}
ft_exit_chain() {
  local why
  [ "$LEASED" = 1 ] || { echo "$(st) FT-VM-LEASED no lease held: nothing to release"; return 0; }
  if [ "$INSTALL_STARTED" = 0 ]; then
    echo "$(st) FT-VM-LEASED the run ended before the first write (nothing installed, armed or launched): the release"
    ft_release; return 0
  fi
  GONE=""
  ft_exit_proven || { ft_hold "$GONE"; return 0; }
  bash "$INSTALL" disarm
  if [ -e "$ARM" ]; then echo "$(st) FT-VM-LEASED sentinel STILL PRESENT after the disarm"; bad=1; fi
  ft_vr6_check
  ft_revert || { ft_hold "$GONE"; return 0; }
  ft_still_gone restore || { ft_hold "$GONE"; return 0; }
  ft_restore_check
  if [ "$bad" = 0 ] && [ "$POST_EQ" = 1 ] && [ "$DLL_EQ" = 1 ] && [ ! -e "$ARM" ]; then
    echo "$(st) FT-VM-LEASED install proven equal to the pre-image: POST inventory equals PRE ($(wc -l < "$OUT/inventory-post.txt") files), DLL digest equal, sentinel absent"
    ft_release; return 0
  fi
  ft_rc_verdict
  why=""
  [ "$POST_EQ" = 1 ] || why="${why}post-inventory-differs,"
  [ "$DLL_EQ" = 1 ] || why="${why}dll-not-pre-image,"
  [ -e "$ARM" ] && why="${why}sentinel-present,"
  [ "$bad" = 1 ] && why="${why}vr6-or-restoration-failed,"
  ft_hold "${why%,}"
}
finish() {
  rc=$?
  trap - EXIT
  ft_exit_chain
  ft_end_line
  exit "$rc"
}
trap finish EXIT
echo "$(st) FT-VM-LEASED $MODE lease acquire pause.ps1 -Holder frame-time"
pout=$(rig pause -Holder frame-time); prc=$?
printf '%s\n' "$pout"
if [ "$prc" = 0 ] || printf '%s\n' "$pout" | grep -q 'Broadcast bot PAUSED; holder'; then
  LEASED=1
  echo "$(st) FT-VM-LEASED lease counted held from the pause's success (rc $prc)"
else
  sout=$(rig pause -Status); src=$?
  printf '%s\n' "$sout"
  if [ "$src" = 0 ] && table_shown "$sout" && ! holder_shown "$sout"; then
    echo "$(st) FT-VM-LEASED lease NOT held (pause rc $prc; the status reading shows no frame-time); nothing launched"; exit 20
  fi
  LEASED=1
  echo "$(st) FT-VM-LEASED pause rc $prc, but the status reading (rc $src) shows the holder or could not be read: counted held; nothing launched"; exit 20
fi
sout=$(rig pause -Status); src=$?
printf '%s\n' "$sout"
if [ "$src" != 0 ] || ! holder_shown "$sout"; then
  echo "$(st) FT-VM-LEASED lease not confirmed by the status reading (rc $src); nothing launched"; exit 20
fi
echo "$(st) FT-VM-LEASED lease held (confirmed by the status reading)"
if [ "$DRY" = "--dry" ]; then
  powershell -NoProfile -File "$R/ai-collab/frame-time/s0_gate.ps1" -Launch "$N" -Pairs 2 -Dry | tr -d '\r'
  exit "${PIPESTATUS[0]}"
fi
echo "$(st) FT-VM-LEASED quit_game.ps1 -Holder frame-time (the bot's game: the leased shutdown)"
rig quit_game -Holder frame-time
for i in $(seq 1 20); do [ "$(rounds_state)" = no ] && break; sleep "$NAP"; done
s=$(rounds_state)
if [ "$s" != no ]; then echo "$(st) FT-VM-LEASED ROUNDS not proven gone after the leased shutdown (reading: $s); nothing installed"; exit 21; fi
echo "$(st) FT-VM-LEASED leased shutdown: ROUNDS not running"
# FIX-8 (R6-A3.11.10): a reading right after the quit measures the quit's own writes; settle first
powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$HERE/ft_settle_diskq.ps1")" | tr -d '\r'
sg=${PIPESTATUS[0]}
if [ "$sg" -ne 0 ]; then echo "$(st) FT-VM-LEASED settle window refused (rc=$sg); nothing launched"; exit 10; fi
powershell -NoProfile -File "$R/ai-collab/frame-time/s0_gate.ps1" -Launch "$N" -Pairs 2 | tr -d '\r'
g=${PIPESTATUS[0]}
if [ "$g" -ne 0 ]; then echo "$(st) FT-VM-LEASED under-lease gate refused (rc=$g); nothing launched"; exit 10; fi
mkdir -p "$PRE" || exit 2
inventory "$OUT/inventory-pre.txt" || { echo "$(st) FT-VM-LEASED PRE inventory not read whole; nothing installed"; exit 2; }
cp -p "$CFG" "$PRE/com.competitiverounds.mod.cfg" && cmp -s "$CFG" "$PRE/com.competitiverounds.mod.cfg" || { echo "$(st) FT-VM-LEASED cfg pre-image not proven"; exit 2; }
for i in 0 1 2 3 4; do
  if [ -f "${LOGP[$i]}" ]; then
    cp -p "${LOGP[$i]}" "$PRE/${LOGN[$i]}" || exit 2
    [ "$(sha "$PRE/${LOGN[$i]}")" = "$(sha "${LOGP[$i]}")" ] || { echo "$(st) FT-VM-LEASED pre-image of ${LOGN[$i]} differs"; exit 2; }
  fi
done
cp -p "$PLUG" "$PRE/CompetitiveRounds.dll" || { echo "$(st) FT-VM-LEASED DLL pre-image copy failed"; exit 2; }
PRE_DLL=$(sha "$PRE/CompetitiveRounds.dll")
[ "$PRE_DLL" = "$(sha "$PLUG")" ] || { echo "$(st) FT-VM-LEASED DLL pre-image not proven"; exit 2; }
[ -e "$ARM" ] && { echo "$(st) FT-VM-LEASED a sentinel exists before the install (not this run's); nothing installed"; exit 2; }
ist=$(bash "$INSTALL" status); isr=$?
echo "$ist"
if [ "$isr" != 0 ] || ! printf '%s\n' "$ist" | grep -qE ' open none$'; then
  echo "$(st) FT-VM-LEASED the install status does not show 'open none' (rc $isr): an earlier install is open or unread; nothing installed"; exit 22
fi
echo "$(st) FT-VM-INVENTORY pre written: $(wc -l < "$OUT/inventory-pre.txt") files, md5 $(md5sum < "$OUT/inventory-pre.txt" | cut -c1-32); cfg pre-image $(sha "$PRE/com.competitiverounds.mod.cfg"); DLL pre-image $PRE_DLL"
# A3: the rollback is armed BEFORE the first write; from here every end reverts
INSTALL_STARTED=1
bash "$INSTALL" install "$DLL" "$LANES" || exit 22
bash "$INSTALL" arm "$MODE" || exit 2
powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$HERE/ft_vm_launch.ps1")" -Mode "$MODE" -Out "$(cygpath -w "$OUT/LogOutput-$MODE.log")" | tr -d '\r'
exit "${PIPESTATUS[0]}"
