#!/usr/bin/env bash
# ft_vm_leased.sh <menu|match> <outdir> [--dry]: one FrameTime launch on the VM seat UNDER the broadcast pause lease
# (ruling FRAME-TIME-ROUND-R4), the integrator's to run. Order: lease acquired as holder frame-time and verified by
# pause.ps1 -Status (never by an exit code); the bot's game quit; the VM launch gate under the lease (s0_gate.ps1,
# two disk-queue pairs); the mod cfg's pre-image; the sentinel armed; ft_vm_launch.ps1; in every outcome after the
# lease (trap): the sentinel removed, the cfg restored and compared with cmp, the lease released and the status
# printed. --dry stops after the gate (s0_gate -Dry; nothing armed or launched).
# Exit: 0 the launch saw its end line; 10 gate refused; 20 lease not held; otherwise the launch script's code.
set -u
MODE="${1:?menu|match}"; OUT="${2:?outdir}"; DRY="${3:-}"
case "$MODE" in menu) N=1;; match) N=2;; *) echo "usage: ft_vm_leased.sh <menu|match> <outdir> [--dry]"; exit 2;; esac
R=C:/Users/Sid/Documents/SidsCompetitiveRounds
HERE="$(cd "$(dirname "$0")" && pwd)"
CFG="C:/Program Files (x86)/Steam/steamapps/common/ROUNDS/BepInEx/config/com.competitiverounds.mod.cfg"
st() { date -u +%Y-%m-%dT%H:%M:%SZ; }
[ -e "$OUT" ] && { echo "$(st) FT-VM-LEASED REFUSED: $OUT exists (a fresh folder per run)"; exit 2; }
mkdir -p "$OUT" || exit 2
PRE="$OUT/cfg-preimage.cfg"
LEASED=0
finish() {
  rc=$?
  if [ "$LEASED" = "1" ]; then
    bash "$HERE/ft_vm_install.sh" disarm
    if [ "$DRY" != "--dry" ] && [ -f "$PRE" ]; then
      cp -p "$PRE" "$CFG"
      if cmp -s "$CFG" "$PRE"; then echo "$(st) FT-VM-LEASED cfg restored: byte-identical (cmp)"; else echo "$(st) FT-VM-LEASED CFG RESTORE MISMATCH"; fi
    fi
    echo "$(st) FT-VM-LEASED lease release resume.ps1 -Holder frame-time"
    powershell -NoProfile -File C:/broadcast/resume.ps1 -Holder frame-time | tr -d '\r'
    powershell -NoProfile -File C:/broadcast/pause.ps1 -Status | tr -d '\r'
  fi
  echo "$(st) FT-VM-LEASED $MODE end rc=$rc"
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
echo "$(st) FT-VM-LEASED quit_game.ps1 -Holder frame-time (the bot's game)"
powershell -NoProfile -File C:/broadcast/quit_game.ps1 -Holder frame-time | tr -d '\r'
powershell -NoProfile -File "$R/ai-collab/frame-time/s0_gate.ps1" -Launch "$N" -Pairs 2 | tr -d '\r'
g=${PIPESTATUS[0]}
if [ "$g" -ne 0 ]; then echo "$(st) FT-VM-LEASED under-lease gate refused (rc=$g); nothing launched"; exit 10; fi
cp -p "$CFG" "$PRE" && echo "$(st) FT-VM-LEASED cfg pre-image $(sha256sum "$PRE" | cut -c1-64)"
bash "$HERE/ft_vm_install.sh" arm "$MODE" || exit 2
powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$HERE/ft_vm_launch.ps1")" -Mode "$MODE" -Out "$(cygpath -w "$OUT/LogOutput-$MODE.log")" | tr -d '\r'
exit "${PIPESTATUS[0]}"
