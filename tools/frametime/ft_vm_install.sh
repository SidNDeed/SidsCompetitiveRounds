#!/usr/bin/env bash
# ft_vm_install.sh: the lane's own install step on the VM seat (ruling FRAME-TIME-ROUND-R4), for the in-game executed
# calibration run. Run by the integrator only, under the run's sheet; it never reads or writes the C:/shared drop root.
#
#   ft_vm_install.sh install <proof-outdir>/lane-frametime.dll <lanes-folder>   install the FrameTime DLL
#   ft_vm_install.sh revert                                                     restore the DLL the install replaced
#   ft_vm_install.sh arm <menu|match>                                           write the sentinel BepInEx/frametime/arm
#   ft_vm_install.sh disarm                                                     remove the sentinel
#   ft_vm_install.sh status                                                     installed digest, sentinel, open install
#
# install refuses while ROUNDS runs, when an earlier install was never reverted, when the DLL's sha256 differs from the
# lanes folder's sha256.txt (the bytes the laptop seat receives: both seats must carry the same DLL, whose digest names
# the room), or when ft_absent.py does not find the FrameTime build in it. It backs the installed DLL up into a fresh
# folder under ai-collab/frame-time/vm-install/ with its digest, copies, and proves the copy by digest. revert copies
# that backup back, proves the digest, removes the sentinel and closes the record (renamed, never deleted).
# The match sentinel arms seed 2, f18 A: each seat its own seed (METHOD-V4 3.3; ruling R6-A3.11.54 Q3); the laptop
# runner keeps frame_time_seat.ps1's defaults, seed 1, f18 A. The menu sentinel is one seat's self-check and keeps seed 1.
# Exit: 0 done; 2 usage or refused; 3 a digest check failed.
set -u
R=C:/Users/Sid/Documents/SidsCompetitiveRounds
GAME="C:/Program Files (x86)/Steam/steamapps/common/ROUNDS"
PLUGDIR="$GAME/BepInEx/plugins/CompetitiveRounds"
PLUG="$PLUGDIR/CompetitiveRounds.dll"
ARM="$GAME/BepInEx/frametime/arm"
REC="$R/ai-collab/frame-time/vm-install"
CUR="$REC/CURRENT"
HERE="$(cd "$(dirname "$0")" && pwd)"
st() { date -u +%Y-%m-%dT%H:%M:%SZ; }
sha() { sha256sum "$1" | cut -c1-64; }
running() { /c/Windows/System32/tasklist.exe 2>/dev/null | grep -i -q 'ROUNDS.exe'; }
refuse() { echo "FT-VM-INSTALL REFUSED: $*"; exit 2; }

cmd="${1:-}"
case "$cmd" in
  install)
    DLL="${2:-}"; LANES="${3:-}"
    [ -f "$DLL" ] && [ -f "$LANES/sha256.txt" ] || refuse "usage: install <proof-outdir>/lane-frametime.dll <lanes-folder>"
    case "$LANES" in C:/shared/builds/lanes/frametime-*) ;; *) refuse "the lanes folder must be C:/shared/builds/lanes/frametime-<sha8>";; esac
    running && refuse "ROUNDS is running"
    [ -e "$CUR" ] && refuse "an earlier install is open ($(cat "$CUR")); revert it first"
    want=$(cut -c1-64 "$LANES/sha256.txt"); got=$(sha "$DLL"); staged=$(sha "$LANES/CompetitiveRounds.dll")
    echo "$(st) dll $got; lanes sha256.txt $want; lanes dll $staged"
    [ "$got" = "$want" ] && [ "$staged" = "$want" ] || refuse "digest differs from the lanes folder (both seats need the same bytes)"
    python -I -B "$HERE/ft_absent.py" "$DLL" present > /dev/null 2>&1 || refuse "ft_absent.py does not find the FrameTime build in $DLL"
    BK="$REC/$(date -u +%Y%m%dT%H%M%SZ)"
    [ -e "$BK" ] && refuse "$BK exists"
    mkdir -p "$BK" || refuse "cannot create $BK"
    prior=$(sha "$PLUG")
    cp -p "$PLUG" "$BK/CompetitiveRounds.dll" || refuse "backup copy failed"
    echo "$prior" > "$BK/installed.sha256"
    [ "$(sha "$BK/CompetitiveRounds.dll")" = "$prior" ] || { echo "FT-VM-INSTALL FAIL backup digest"; exit 3; }
    cp "$DLL" "$PLUG" || { echo "FT-VM-INSTALL FAIL copy"; exit 3; }
    now=$(sha "$PLUG")
    [ "$now" = "$want" ] || { echo "FT-VM-INSTALL FAIL installed $now, wanted $want"; exit 3; }
    echo "$BK" > "$CUR"
    echo "$(st) FT-VM-INSTALL OK installed $now prior $prior backup $BK"
    ;;
  revert)
    [ -e "$CUR" ] || refuse "no open install to revert"
    running && refuse "ROUNDS is running"
    BK=$(cat "$CUR"); want=$(cat "$BK/installed.sha256")
    cp "$BK/CompetitiveRounds.dll" "$PLUG" || { echo "FT-VM-REVERT FAIL copy"; exit 3; }
    now=$(sha "$PLUG")
    [ "$now" = "$want" ] || { echo "FT-VM-REVERT FAIL restored $now, wanted $want"; exit 3; }
    [ -e "$ARM" ] && rm -f "$ARM"
    mv "$CUR" "$REC/CURRENT.reverted-$(date -u +%Y%m%dT%H%M%SZ)"
    echo "$(st) FT-VM-REVERT OK restored $now sentinel $([ -e "$ARM" ] && echo present || echo absent)"
    ;;
  arm)
    mode="${2:-}"
    [ -e "$CUR" ] || refuse "no open install: the sentinel arms only the lane's FrameTime DLL"
    [ "$(sha "$PLUG")" = "$(cat "$(cat "$CUR")/installed.sha256")" ] && refuse "the installed DLL is the backed-up one, not the lane's"
    mkdir -p "$(dirname "$ARM")"
    case "$mode" in
      menu)  printf 'seed=1\nforce=none\nmenu=1\n' > "$ARM";;
      match) printf 'seed=2\nf18=A\n' > "$ARM";;
      *) refuse "usage: arm <menu|match>";;
    esac
    echo "$(st) FT-VM-ARM $mode written: $(tr '\n' ' ' < "$ARM")"
    ;;
  disarm)
    if [ -e "$ARM" ]; then rm -f "$ARM"; fi
    echo "$(st) FT-VM-DISARM sentinel $([ -e "$ARM" ] && echo STILL-PRESENT || echo absent)"
    [ -e "$ARM" ] && exit 3
    ;;
  status)
    echo "$(st) FT-VM-STATUS installed $(sha "$PLUG") sentinel $([ -e "$ARM" ] && echo present || echo absent) open $([ -e "$CUR" ] && cat "$CUR" || echo none)"
    ;;
  *)
    refuse "usage: install|revert|arm|disarm|status"
    ;;
esac
exit 0
