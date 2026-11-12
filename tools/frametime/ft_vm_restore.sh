#!/usr/bin/env bash
# ft_vm_restore.sh: sourced by ft_vm_leased.sh and by its dry harness (ruling R6-A3.11.14, FIX-10). The checks and the
# restoration that run in the leased script's cleanup after the sitting, taken out of finish() so they run unchanged
# against a planted tree. The caller sets BEP CONFDIR CFG OUT PRE RUNSTAMP and the arrays LOGN LOGP.
#   ft_vr6_check        VR6's second listing (the config folder and LogOutput-prev.log as the sitting left them)
#                       compared with PRE; any change, or a listing that could not be written, prints
#                       "FT-VM-VR6 files FAIL" and sets bad=1
#                       (R6-A3.11.41: the cfg's RESTORED KIND passes, recorded; see ft_cfg_restored_kind)
#   ft_restore_check    (c) every file the restoration replaces is first MOVED, mtime kept, into
#                       <outdir>/sitting/<RUNSTAMP>/ (a file already there is never overwritten: refused, bad=1), then
#                       the pre-image is put back and proven: the five logs (moved whenever present) and the cfg
#                       (moved when it differs from its pre-image); then the POST inventory against PRE line for line
#                       and sets POST_EQ=1 only when they are equal (R6-A3.11.18 A5 reads it); an occupied destination
#                       leaves that file unrestored, but the POST inventory is still written and compared
#   ft_rc_verdict       (a) bad=1 sets rc 30, whatever the launch code was (0, 5 or any other), and says so
# CLASS B (R6-A3.11.18): a read that fails never reads as equal. sha prints a token unique to that reading when the
# digest cannot be read (two failed readings never compare equal); inventory returns 1 when a folder is absent, a
# listing fails, any digest is unreadable or a line of it could not be written.
st() { date -u +%Y-%m-%dT%H:%M:%SZ; }
sha() {
  local s
  if [ -f "$1" ]; then
    s=$(sha256sum "$1" | cut -c1-64)
    if [ "${#s}" = 64 ]; then echo "$s"; else echo "unreadable-$(date +%s%N)-$RANDOM"; fi
  else echo absent; fi
}
# inventory <file>: one line per file, "<area> <path> <sha256>", sorted; the plugins and config folders whole and
# recursive (paths relative to each folder, e.g. "plugins CompetitiveRounds/CompetitiveRounds.dll"), then the five logs
inventory() {
  local tmp="$1.part" area dir list f s ok=0
  : > "$tmp" || return 1
  for area in plugins config; do
    if [ "$area" = plugins ]; then dir="$BEP/plugins"; else dir="$CONFDIR"; fi
    [ -d "$dir" ] || { echo "$(st) FT-VM-INVENTORY $area folder absent ($dir)"; return 1; }
    list=$(find "$dir" -type f) || { echo "$(st) FT-VM-INVENTORY listing of $dir FAILED"; return 1; }
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      s=$(sha "$f"); case "$s" in unreadable-*) echo "$(st) FT-VM-INVENTORY digest of $f unreadable"; ok=1;; esac
      echo "$area ${f#"$dir/"} $s" >> "$tmp" || { echo "$(st) FT-VM-INVENTORY write of $tmp FAILED"; return 1; }
    done <<< "$list"
  done
  for i in 0 1 2 3 4; do
    s=$(sha "${LOGP[$i]}"); case "$s" in unreadable-*) echo "$(st) FT-VM-INVENTORY digest of ${LOGN[$i]} unreadable"; ok=1;; esac
    echo "log ${LOGN[$i]} $s" >> "$tmp" || { echo "$(st) FT-VM-INVENTORY write of $tmp FAILED"; return 1; }
  done
  LC_ALL=C sort "$tmp" > "$1" || return 1
  rm -f "$tmp"
  return "$ok"
}
ft_vr6_check() {
  inventory "$OUT/inventory-sitting.txt" || { echo "$(st) FT-VM-VR6 files FAIL: the sitting's inventory could not be read whole"; bad=1; return 0; }
  # VR6's two listings, each file first proven writable (a redirection that fails also ends 1 in bash): grep then
  # exits 0 (lines) or 1 (none); 2 is a read or write that failed. Two listings that failed alike never compare equal
  local g1=2 g2=2
  : > "$OUT/vr6-pre.txt" && { grep -E "^config |^log LogOutput-prev.log " "$OUT/inventory-pre.txt" > "$OUT/vr6-pre.txt"; g1=$?; }
  : > "$OUT/vr6-sitting.txt" && { grep -E "^config |^log LogOutput-prev.log " "$OUT/inventory-sitting.txt" > "$OUT/vr6-sitting.txt"; g2=$?; }
  if [ "$g1" -gt 1 ] || [ "$g2" -gt 1 ]; then
    echo "$(st) FT-VM-VR6 files FAIL: VR6's listings could not be written (grep rc $g1, $g2)"; bad=1; return 0
  fi
  if cmp -s "$OUT/vr6-pre.txt" "$OUT/vr6-sitting.txt"; then
    echo "$(st) FT-VM-VR6 files PASS (config folder and LogOutput-prev.log unchanged by the sitting)"
  elif ft_cfg_restored_kind; then
    echo "$(st) FT-VM-VR6 files PASS restored kind (R6-A3.11.41): com.competitiverounds.mod.cfg is the only changed file and only its comment lines differ (every key, value and the order equal to the pre-image; the restore below must still prove the pre-image back by cmp): $FT_KIND_LINE"
  else
    echo "$(st) FT-VM-VR6 files FAIL: $(diff "$OUT/vr6-pre.txt" "$OUT/vr6-sitting.txt" | grep '^[<>]' | tr '\n' ';') cfg: ${FT_KIND_LINE:-not compared}"; bad=1
  fi
}
# R6-A3.11.41 (2): THE RESTORED KIND of VR6 for the mod cfg, which replaces FIX-11 (R6-A3.11.15). FIX-11 accepted one
# text, whole, and that text lacked the description's last sentence, so it never matched the file the game writes
# (control 2026-11-06T17:42Z: HELD). True only when (1) the cfg's inventory line is the ONLY difference among VR6's
# lines (any other config file or LogOutput-prev.log changed: false), and (2) ft_cfg_compare.py, beside this file,
# exits 0 with exactly one line "RESTORED-KIND ...": only comment lines differ, every other line of the file's
# grammar byte-identical and in order; a line of no kind is refused. The restore (ft_restore_check) still puts the
# pre-image back and proves it by cmp, and the POST inventory must equal PRE; either failing ends HELD.
# FT_KIND_LINE carries the comparer's one line (key names only, never a value) into VR6's PASS or FAIL line.
FT_CFG_COMPARE="$HERE/ft_cfg_compare.py"   # pinned beside this file, by the lane commit; no override
ft_cfg_restored_kind() {
  local pc="$PRE/com.competitiverounds.mod.cfg" out crc
  FT_KIND_LINE=""
  [ -f "$pc" ] && [ -f "$CFG" ] || { FT_KIND_LINE="a cfg absent"; return 1; }
  [ "$(diff "$OUT/vr6-pre.txt" "$OUT/vr6-sitting.txt" | grep '^[<>]' | grep -vc '^[<>] config com\.competitiverounds\.mod\.cfg ')" = 0 ] || { FT_KIND_LINE="not compared: another file differs"; return 1; }
  [ -f "$FT_CFG_COMPARE" ] || { FT_KIND_LINE="not compared: $FT_CFG_COMPARE absent"; return 1; }
  out=$(python -I "$FT_CFG_COMPARE" "$pc" "$CFG" 2>&1); crc=$?
  FT_KIND_LINE="$(printf '%s\n' "$out" | head -n 1 | tr -d '\r' | cut -c1-600) (compare rc $crc, md5 $(md5sum < "$FT_CFG_COMPARE" | cut -c1-8))"
  [ "$crc" = 0 ] && [ "$(printf '%s\n' "$out" | grep -c .)" = 1 ] || return 1
  case "$out" in "RESTORED-KIND comment lines differ: "*) return 0;; esac
  return 1
}
# ft_move_aside <file> <name>: move <file> into $SITDIR/<name>, never over an existing file; proven by digest
ft_move_aside() {
  local src="$1" dst="$SITDIR/$2" s m
  mkdir -p "$SITDIR" || { echo "$(st) FT-VM-RESTORE move of $2 REFUSED: $SITDIR not made"; bad=1; return 1; }
  if [ -e "$dst" ]; then echo "$(st) FT-VM-RESTORE move of $2 REFUSED: $dst exists (never overwritten)"; bad=1; return 1; fi
  s=$(sha "$src"); m=$(stat -c %Y "$src")
  mv -n "$src" "$dst"
  if [ ! -e "$src" ] && [ "$(sha "$dst")" = "$s" ] && [ "$(stat -c %Y "$dst")" = "$m" ]; then
    echo "$(st) FT-VM-RESTORE moved $2 to sitting/$RUNSTAMP/ ($s, mtime $(date -u -d "@$m" +%Y-%m-%dT%H:%M:%SZ) kept)"
  else
    echo "$(st) FT-VM-RESTORE move of $2 FAILED (src present: $([ -e "$src" ] && echo yes || echo no); dst $(sha "$dst") want $s)"; bad=1; return 1
  fi
}
ft_restore_check() {
  local i n p want got cfgskip=0
  POST_EQ=0
  SITDIR="$OUT/sitting/$RUNSTAMP"
  for i in 0 1 2 3 4; do
    n=${LOGN[$i]}; p=${LOGP[$i]}; want=$(grep -E "^log $n " "$OUT/inventory-pre.txt" | awk '{print $3}')
    if [ -f "$p" ]; then ft_move_aside "$p" "$n" || continue; fi
    [ "$want" != "absent" ] && cp -p "$PRE/$n" "$p"
    got=$(sha "$p")
    if [ "$got" = "$want" ]; then echo "$(st) FT-VM-RESTORE log $n $got equal"
    else echo "$(st) FT-VM-RESTORE log $n $got pre $want DIFFERENT"; bad=1; fi
  done
  if [ "$(sha "$CFG")" != "$(sha "$PRE/com.competitiverounds.mod.cfg")" ]; then
    echo "$(st) FT-VM-LEASED cfg differs from its pre-image ($(sha "$CFG") vs $(sha "$PRE/com.competitiverounds.mod.cfg")): moved aside before the restore"
    [ -f "$CFG" ] && { ft_move_aside "$CFG" "com.competitiverounds.mod.cfg" || cfgskip=1; }
  fi
  if [ "$cfgskip" = 1 ]; then
    echo "$(st) FT-VM-LEASED cfg NOT restored: its move aside was refused (the run's cfg left in place)"; bad=1
  else
    cp -p "$PRE/com.competitiverounds.mod.cfg" "$CFG"
    if cmp -s "$CFG" "$PRE/com.competitiverounds.mod.cfg"; then echo "$(st) FT-VM-LEASED cfg restored: byte-identical (cmp)"
    else echo "$(st) FT-VM-LEASED CFG RESTORE MISMATCH"; bad=1; fi
  fi
  if ! inventory "$OUT/inventory-post.txt"; then
    echo "$(st) FT-VM-INVENTORY post equals pre: NO: the POST inventory could not be read whole"; bad=1
  elif cmp -s "$OUT/inventory-pre.txt" "$OUT/inventory-post.txt"; then
    POST_EQ=1
    echo "$(st) FT-VM-INVENTORY post equals pre: yes ($(wc -l < "$OUT/inventory-post.txt") files, md5 $(md5sum < "$OUT/inventory-post.txt" | cut -c1-32))"
  else
    echo "$(st) FT-VM-INVENTORY post equals pre: NO: $(diff "$OUT/inventory-pre.txt" "$OUT/inventory-post.txt" | grep '^[<>]' | tr '\n' ';')"; bad=1
  fi
}
ft_rc_verdict() {
  if [ "${bad:-0}" = "1" ]; then
    echo "$(st) FT-VM-LEASED failure code 30: VR6, a restoration or the POST inventory failed (the launch code was $rc)"
    rc=30
  fi
}
# the leased script's last line, here so the dry harness prints it through the same code
ft_end_line() { echo "$(st) FT-VM-LEASED $MODE end rc=$rc"; }
