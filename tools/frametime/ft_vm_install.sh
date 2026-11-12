#!/usr/bin/env bash
# ft_vm_install.sh: the lane's own install step on the VM seat (ruling FRAME-TIME-ROUND-R4), for the in-game executed
# calibration run. Run by the integrator only, under the run's sheet; it never reads or writes the C:/shared drop root.
#
#   ft_vm_install.sh install <proof-outdir>/lane-frametime.dll <lanes-folder>   install the FrameTime DLL
#   ft_vm_install.sh revert                                                     restore the DLL the install replaced
#   ft_vm_install.sh arm <profile>                                              write the sentinel BepInEx/frametime/arm
#   ft_vm_install.sh disarm                                                     remove the sentinel
#   ft_vm_install.sh status                                                     installed digest, sentinel, open install
#
# install refuses while ROUNDS runs, when an earlier install was never reverted, when the DLL's sha256 differs from the
# lanes folder's sha256.txt (the bytes the laptop seat receives: both seats must carry the same DLL, whose digest names
# the room), or when ft_absent.py does not find the FrameTime build in it. Its order: the installed DLL backed up into
# a fresh folder under ai-collab/frame-time/vm-install/, the backup's digest record written and read back, the
# backup's digest proven, the open-install record CURRENT written and read back, and only then the copy and its digest
# check. A failure before CURRENT stands leaves the plugin DLL untouched; a failure after it leaves the record open
# (its FAIL line says so) for revert. revert proves the records and the backup's digest before it writes, copies that
# backup back, proves the digest, removes the sentinel and closes the record (renamed, never deleted); OK only when the
# sentinel is gone and the record closed, else FAIL with the install left open.
# arm writes exactly what ft_arm_text.sh <profile> prints (that file is the one table of the profiles: menu, match,
# match-on, the control boots) and refuses, writing nothing, when it refuses; it prints its written line only after
# the write succeeded and the file's bytes compared equal to that text, else one "FT-VM-ARM FAIL" line and exit 3. It
# refuses when the open install's digest record is unreadable. The match profiles arm seed 2, f18 A:
# each seat its own seed (METHOD-V4 3.3; ruling R6-A3.11.54 Q3); the laptop runner keeps frame_time_seat.ps1's
# defaults, seed 1, f18 A. The menu and boot profiles are one seat's self-check and keep seed 1.
# Exit: 0 done; 2 usage or refused; 3 a write, a read-back or a digest check failed.
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
# the digest read from standard input: sha256sum escapes a file NAME holding a backslash (its line then starts "\"),
# so a "\"-joined path would yield a shifted digest
sha() { sha256sum < "$1" | cut -c1-64; }
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
    # each record is read back before the next step relies on it (ruling R6-A3.11.151 (2) class C)
    printf '%s\n' "$prior" > "$BK/installed.sha256" && [ "$(cat "$BK/installed.sha256" 2>/dev/null)" = "$prior" ] \
      || { echo "FT-VM-INSTALL FAIL backup record $BK/installed.sha256 not written (nothing installed)"; exit 3; }
    [ "$(sha "$BK/CompetitiveRounds.dll")" = "$prior" ] || { echo "FT-VM-INSTALL FAIL backup digest (nothing installed)"; exit 3; }
    # the open-install record is written and read back BEFORE the plugin DLL changes: a record that could not be
    # written leaves the plugin DLL untouched (a partial record removed), and every failure after it leaves the record
    # open, so revert restores the backup it names
    printf '%s\n' "$BK" > "$CUR" && [ "$(cat "$CUR" 2>/dev/null)" = "$BK" ] \
      || { rm -f "$CUR" 2>/dev/null
           echo "FT-VM-INSTALL FAIL the open-install record $CUR not written (nothing installed: the plugin DLL is untouched; the backup is $BK; $([ -e "$CUR" ] && echo "a partial record remains at $CUR" || echo "no record left"))"; exit 3; }
    cp "$DLL" "$PLUG" || { echo "FT-VM-INSTALL FAIL copy (the install record stays open: run revert)"; exit 3; }
    now=$(sha "$PLUG")
    [ "$now" = "$want" ] || { echo "FT-VM-INSTALL FAIL installed $now, wanted $want (the install record stays open: run revert)"; exit 3; }
    echo "$(st) FT-VM-INSTALL OK installed $now prior $prior backup $BK"
    ;;
  revert)
    [ -e "$CUR" ] || refuse "no open install to revert"
    running && refuse "ROUNDS is running"
    BK=$(cat "$CUR" 2>/dev/null); want=$(cat "$BK/installed.sha256" 2>/dev/null)
    # the records and the backup's bytes are proven before the plugin DLL is written: an unreadable record, or a
    # backup that does not hold the recorded digest, changes nothing
    [ -n "$BK" ] && [ "${#want}" = 64 ] || refuse "the open install's records are unreadable ($CUR names '$BK'; its installed.sha256 holds '$want'): nothing restored"
    [ "$(sha "$BK/CompetitiveRounds.dll" 2>/dev/null)" = "$want" ] \
      || { echo "FT-VM-REVERT FAIL the backup $BK/CompetitiveRounds.dll does not hold the recorded digest $want (nothing restored; the install stays open)"; exit 3; }
    cp "$BK/CompetitiveRounds.dll" "$PLUG" || { echo "FT-VM-REVERT FAIL copy (the install stays open)"; exit 3; }
    now=$(sha "$PLUG")
    [ "$now" = "$want" ] || { echo "FT-VM-REVERT FAIL restored $now, wanted $want (the install stays open)"; exit 3; }
    # the revert is OK only with the sentinel gone and the record closed; otherwise the install stays open, so the
    # status reads it and revert can be run again
    rm -f "$ARM"
    [ -e "$ARM" ] && { echo "FT-VM-REVERT FAIL restored $now, but the sentinel $ARM is still present (the install stays open)"; exit 3; }
    done_rec="$REC/CURRENT.reverted-$(date -u +%Y%m%dT%H%M%SZ)"
    mv -n -T "$CUR" "$done_rec"
    [ ! -e "$CUR" ] && [ "$(cat "$done_rec" 2>/dev/null)" = "$BK" ] \
      || { echo "FT-VM-REVERT FAIL restored $now, sentinel absent, but the record $CUR was not closed as $done_rec"; exit 3; }
    echo "$(st) FT-VM-REVERT OK restored $now sentinel $([ -e "$ARM" ] && echo present || echo absent)"
    ;;
  arm)
    mode="${2:-}"
    [ -e "$CUR" ] || refuse "no open install: the sentinel arms only the lane's FrameTime DLL"
    rec=$(cat "$(cat "$CUR")/installed.sha256" 2>/dev/null)
    [ "${#rec}" = 64 ] || refuse "the open install's record of the backed-up DLL's digest is unreadable"
    [ "$(sha "$PLUG")" = "$rec" ] && refuse "the installed DLL is the backed-up one, not the lane's"
    # the text read whole before anything is written; the x keeps its trailing newlines through the substitution
    txt=$(bash "$HERE/ft_arm_text.sh" "$mode" && printf x) || refuse "usage: arm <profile> (ft_arm_text.sh refused '$mode')"
    # the write is checked and its bytes read back and compared with the text before the success line (ruling
    # R6-A3.11.151 (2) class C): a sentinel that could not be written, or holds other bytes, is a FAIL, exit 3
    mkdir -p "$(dirname "$ARM")" || { echo "FT-VM-ARM FAIL $mode: the folder of $ARM could not be made"; exit 3; }
    printf '%s' "${txt%x}" > "$ARM" || { echo "FT-VM-ARM FAIL $mode: the sentinel $ARM could not be written"; exit 3; }
    printf '%s' "${txt%x}" | cmp -s - "$ARM" || { echo "FT-VM-ARM FAIL $mode: the sentinel $ARM does not read back as the profile's text"; exit 3; }
    echo "$(st) FT-VM-ARM $mode written: $(tr '\n' ' ' < "$ARM")"
    ;;
  disarm)
    if [ -e "$ARM" ]; then rm -f "$ARM"; fi
    echo "$(st) FT-VM-DISARM sentinel $([ -e "$ARM" ] && echo STILL-PRESENT || echo absent)"
    [ -e "$ARM" ] && exit 3
    ;;
  status)
    # writes nothing; an open install also names the prior DLL's recorded digest, so a reader sees whether the lane's
    # DLL is in place (an install that failed after its record was written leaves the record open over the prior DLL).
    # The line ends "open none" exactly when no install is open (ft_vm_leased.sh reads that)
    o=none
    if [ -e "$CUR" ]; then
      ob=$(cat "$CUR" 2>/dev/null); op=$(cat "$ob/installed.sha256" 2>/dev/null)
      [ "${#op}" = 64 ] || op=unreadable
      o="$ob prior $op"
    fi
    echo "$(st) FT-VM-STATUS installed $(sha "$PLUG") sentinel $([ -e "$ARM" ] && echo present || echo absent) open $o"
    ;;
  *)
    refuse "usage: install|revert|arm|disarm|status"
    ;;
esac
exit 0
