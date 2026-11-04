#!/usr/bin/env bash
# ft_vm_leased.sh <menu|match> <outdir> <lane-frametime.dll> <lanes-folder> [--dry]: one FrameTime launch on the VM
# seat UNDER the broadcast pause lease (ruling FRAME-TIME-ROUND-R4), the integrator's to run. Round 6 (ruling
# FRAME-TIME-ROUND-R5, the round-5 MEDIUMs at COMMANDS-FT-INGAME.md:45 and ft_vm_leased.sh:24): the INSTALL and its
# RESTORATION sit inside the lease, and VR6's file inventories are written into <outdir>. Order:
#   1. lease acquired as holder frame-time, verified by pause.ps1 -Status (never by an exit code);
#   2. the leased shutdown: the bot's game quit (quit_game.ps1), then ROUNDS proven not running;
#   3. the VM launch gate under the lease (s0_gate.ps1, two disk-queue pairs);
#   4. the PRE inventory (<outdir>/inventory-pre.txt): sha256 of every file in the plugins folder and the config
#      folder and of the five logs (LogOutput.log, LogOutput-prev.log, output_log.txt, Player.log, Player-prev.log);
#      pre-image copies of the cfg and of each present log into <outdir>/pre/, each proven by digest;
#   5. the install (ft_vm_install.sh install: the lane DLL, its digest equal to the lanes folder's), the sentinel
#      armed, ft_vm_launch.ps1;
#   6. in every outcome after step 4 (trap, the lease still held): a ROUNDS still running is closed by identity
#      (ft_close_leased.ps1, R6-A3.11.9 FIX-6b; quit_game.ps1 only when its identity is not shown); the sentinel removed;
#      VR6's second listing (<outdir>/inventory-sitting.txt: the config folder and LogOutput-prev.log as the sitting
#      left them, compared with PRE: any change fails VR6); the install reverted (ft_vm_install.sh revert); the
#      sitting's logs moved into <outdir>/sitting/ and the pre-images put back; the cfg put back; the POST inventory
#      (<outdir>/inventory-post.txt) compared with PRE line for line; then the lease released and the status printed.
# --dry stops after the gate (s0_gate -Dry; nothing inventoried, installed, armed or launched).
# Exit: 0 the launch saw its end line and every check after it held; 10 gate refused; 20 lease not held; 21 ROUNDS
# still running after the leased shutdown; 22 the install refused; 30 VR6 or a restoration or the POST inventory
# failed; otherwise the launch script's code.
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
BEP="$GAME/BepInEx"
CFG="$BEP/config/com.competitiverounds.mod.cfg"
PLUGDIR="$BEP/plugins/CompetitiveRounds"
CONFDIR="$BEP/config"
LOW="${FT_VM_LOCALLOW:-C:/Users/Sid/AppData/LocalLow}"
PL="$LOW/Landfall Games/ROUNDS"
for pub in "Landfall Games" "Landfall"; do [ -f "$LOW/$pub/ROUNDS/Player.log" ] && { PL="$LOW/$pub/ROUNDS"; break; }; done
LOGN=(LogOutput.log LogOutput-prev.log output_log.txt Player.log Player-prev.log)
LOGP=("$BEP/LogOutput.log" "$BEP/LogOutput-prev.log" "$GAME/output_log.txt" "$PL/Player.log" "$PL/Player-prev.log")
st() { date -u +%Y-%m-%dT%H:%M:%SZ; }
sha() { if [ -f "$1" ]; then sha256sum "$1" | cut -c1-64; else echo absent; fi; }
running() { /c/Windows/System32/tasklist.exe 2>/dev/null | grep -i -q 'ROUNDS.exe'; }
# inventory <file>: one line per file, "<area> <path> <sha256>", sorted; the plugins and config folders whole and
# recursive (paths relative to each folder, e.g. "plugins CompetitiveRounds/CompetitiveRounds.dll"), then the five logs
inventory() {
  {
    find "$BEP/plugins" -type f | while IFS= read -r f; do echo "plugins ${f#"$BEP/plugins/"} $(sha "$f")"; done
    find "$CONFDIR" -type f | while IFS= read -r f; do echo "config ${f#"$CONFDIR/"} $(sha "$f")"; done
    for i in 0 1 2 3 4; do echo "log ${LOGN[$i]} $(sha "${LOGP[$i]}")"; done
  } | LC_ALL=C sort > "$1"
}
[ -e "$OUT" ] && { echo "$(st) FT-VM-LEASED REFUSED: $OUT exists (a fresh folder per run)"; exit 2; }
mkdir -p "$OUT" || exit 2
PRE="$OUT/pre"
LEASED=0
INVENTORIED=0
INSTALLED=0
finish() {
  rc=$?
  if [ "$LEASED" = "1" ]; then
    if [ "$INVENTORIED" = "1" ]; then
      bad=0
      if running && [ -f "$OUT/launch-$MODE.pid" ]; then
        # FIX-6b (R6-A3.11.9): the leased game is closed by identity, never through the rig's quit lever
        echo "$(st) FT-VM-LEASED ROUNDS still running at cleanup: close by identity ($OUT/launch-$MODE.pid)"
        powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$HERE/ft_close_leased.ps1")" -PidFile "$(cygpath -w "$OUT/launch-$MODE.pid")" | tr -d '\r'
        echo "$(st) FT-VM-LEASED close by identity rc=${PIPESTATUS[0]}"
      fi
      if running; then
        echo "$(st) FT-VM-LEASED ROUNDS still running at cleanup, identity not shown: quit_game.ps1 -Holder frame-time"
        powershell -NoProfile -File C:/broadcast/quit_game.ps1 -Holder frame-time | tr -d '\r'
        for i in $(seq 1 20); do running || break; sleep 3; done
      fi
      bash "$HERE/ft_vm_install.sh" disarm
      # VR6's second listing: the config folder and LogOutput-prev.log as the sitting left them
      inventory "$OUT/inventory-sitting.txt"
      grep -E "^config |^log LogOutput-prev.log " "$OUT/inventory-pre.txt" > "$OUT/vr6-pre.txt"
      grep -E "^config |^log LogOutput-prev.log " "$OUT/inventory-sitting.txt" > "$OUT/vr6-sitting.txt"
      if cmp -s "$OUT/vr6-pre.txt" "$OUT/vr6-sitting.txt"; then
        echo "$(st) FT-VM-VR6 files PASS (config folder and LogOutput-prev.log unchanged by the sitting)"
      else
        echo "$(st) FT-VM-VR6 files FAIL: $(diff "$OUT/vr6-pre.txt" "$OUT/vr6-sitting.txt" | grep '^[<>]' | tr '\n' ';')"; bad=1
      fi
      if [ "$INSTALLED" = "1" ]; then bash "$HERE/ft_vm_install.sh" revert || bad=1; fi
      # the logs restored like the cfg: the sitting's copies moved aside, the pre-images put back, each proven
      mkdir -p "$OUT/sitting"
      for i in 0 1 2 3 4; do
        n=${LOGN[$i]}; p=${LOGP[$i]}; want=$(grep -E "^log $n " "$OUT/inventory-pre.txt" | awk '{print $3}')
        [ -f "$p" ] && mv -f "$p" "$OUT/sitting/$n"
        [ "$want" != "absent" ] && cp -p "$PRE/$n" "$p"
        got=$(sha "$p")
        if [ "$got" = "$want" ]; then echo "$(st) FT-VM-RESTORE log $n $got equal"
        else echo "$(st) FT-VM-RESTORE log $n $got pre $want DIFFERENT"; bad=1; fi
      done
      cp -p "$PRE/com.competitiverounds.mod.cfg" "$CFG"
      if cmp -s "$CFG" "$PRE/com.competitiverounds.mod.cfg"; then echo "$(st) FT-VM-LEASED cfg restored: byte-identical (cmp)"
      else echo "$(st) FT-VM-LEASED CFG RESTORE MISMATCH"; bad=1; fi
      inventory "$OUT/inventory-post.txt"
      if cmp -s "$OUT/inventory-pre.txt" "$OUT/inventory-post.txt"; then
        echo "$(st) FT-VM-INVENTORY post equals pre: yes ($(wc -l < "$OUT/inventory-post.txt") files, md5 $(md5sum < "$OUT/inventory-post.txt" | cut -c1-32))"
      else
        echo "$(st) FT-VM-INVENTORY post equals pre: NO: $(diff "$OUT/inventory-pre.txt" "$OUT/inventory-post.txt" | grep '^[<>]' | tr '\n' ';')"; bad=1
      fi
      [ "$bad" = "1" ] && [ "$rc" = "0" ] && rc=30
    fi
    echo "$(st) FT-VM-LEASED lease release resume.ps1 -Holder frame-time"
    powershell -NoProfile -File C:/broadcast/resume.ps1 -Holder frame-time | tr -d '\r'
    powershell -NoProfile -File C:/broadcast/pause.ps1 -Status | tr -d '\r'
  fi
  echo "$(st) FT-VM-LEASED $MODE end rc=$rc"
  exit "$rc"
}
trap finish EXIT
echo "$(st) FT-VM-LEASED $MODE lease acquire pause.ps1 -Holder frame-time"
powershell -NoProfile -File C:/broadcast/pause.ps1 -Holder frame-time | tr -d '\r'
if ! powershell -NoProfile -File C:/broadcast/pause.ps1 -Status | tr -d '\r' | grep -q "frame-time"; then
  echo "$(st) FT-VM-LEASED lease NOT held; nothing launched"; exit 20
fi
LEASED=1
echo "$(st) FT-VM-LEASED lease held"
if [ "$DRY" = "--dry" ]; then
  powershell -NoProfile -File "$R/ai-collab/frame-time/s0_gate.ps1" -Launch "$N" -Pairs 2 -Dry | tr -d '\r'
  exit "${PIPESTATUS[0]}"
fi
echo "$(st) FT-VM-LEASED quit_game.ps1 -Holder frame-time (the bot's game: the leased shutdown)"
powershell -NoProfile -File C:/broadcast/quit_game.ps1 -Holder frame-time | tr -d '\r'
for i in $(seq 1 20); do running || break; sleep 3; done
if running; then echo "$(st) FT-VM-LEASED ROUNDS still running after the leased shutdown; nothing installed"; exit 21; fi
echo "$(st) FT-VM-LEASED leased shutdown: ROUNDS not running"
powershell -NoProfile -File "$R/ai-collab/frame-time/s0_gate.ps1" -Launch "$N" -Pairs 2 | tr -d '\r'
g=${PIPESTATUS[0]}
if [ "$g" -ne 0 ]; then echo "$(st) FT-VM-LEASED under-lease gate refused (rc=$g); nothing launched"; exit 10; fi
mkdir -p "$PRE"
inventory "$OUT/inventory-pre.txt"
cp -p "$CFG" "$PRE/com.competitiverounds.mod.cfg" || exit 2
for i in 0 1 2 3 4; do
  if [ -f "${LOGP[$i]}" ]; then
    cp -p "${LOGP[$i]}" "$PRE/${LOGN[$i]}" || exit 2
    [ "$(sha "$PRE/${LOGN[$i]}")" = "$(sha "${LOGP[$i]}")" ] || { echo "$(st) FT-VM-LEASED pre-image of ${LOGN[$i]} differs"; exit 2; }
  fi
done
INVENTORIED=1
echo "$(st) FT-VM-INVENTORY pre written: $(wc -l < "$OUT/inventory-pre.txt") files, md5 $(md5sum < "$OUT/inventory-pre.txt" | cut -c1-32); cfg pre-image $(sha "$PRE/com.competitiverounds.mod.cfg")"
bash "$HERE/ft_vm_install.sh" install "$DLL" "$LANES" || exit 22
INSTALLED=1
bash "$HERE/ft_vm_install.sh" arm "$MODE" || exit 2
powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$HERE/ft_vm_launch.ps1")" -Mode "$MODE" -Out "$(cygpath -w "$OUT/LogOutput-$MODE.log")" | tr -d '\r'
exit "${PIPESTATUS[0]}"
