#!/usr/bin/env bash
# ft_vm_restore.sh: sourced by ft_vm_leased.sh and by its dry harness (ruling R6-A3.11.14, FIX-10). The checks and the
# restoration that run in the leased script's cleanup after the sitting, taken out of finish() so they run unchanged
# against a planted tree. The caller sets BEP CONFDIR CFG OUT PRE RUNSTAMP and the arrays LOGN LOGP.
#   ft_vr6_check        VR6's second listing (the config folder and LogOutput-prev.log as the sitting left them)
#                       compared with PRE; any change prints "FT-VM-VR6 files FAIL" and sets bad=1
#                       (FIX-11, R6-A3.11.15: one proven comment-only cfg rewrite passes, recorded; see ft_cfg_known_rewrite)
#   ft_restore_check    (c) every file the restoration replaces is first MOVED, mtime kept, into
#                       <outdir>/sitting/<RUNSTAMP>/ (a file already there is never overwritten: refused, bad=1), then
#                       the pre-image is put back and proven: the five logs (moved whenever present) and the cfg
#                       (moved when it differs from its pre-image); then the POST inventory against PRE line for line
#   ft_rc_verdict       (a) bad=1 sets rc 30, whatever the launch code was (0, 5 or any other), and says so
st() { date -u +%Y-%m-%dT%H:%M:%SZ; }
sha() { if [ -f "$1" ]; then sha256sum "$1" | cut -c1-64; else echo absent; fi; }
# inventory <file>: one line per file, "<area> <path> <sha256>", sorted; the plugins and config folders whole and
# recursive (paths relative to each folder, e.g. "plugins CompetitiveRounds/CompetitiveRounds.dll"), then the five logs
inventory() {
  {
    find "$BEP/plugins" -type f | while IFS= read -r f; do echo "plugins ${f#"$BEP/plugins/"} $(sha "$f")"; done
    find "$CONFDIR" -type f | while IFS= read -r f; do echo "config ${f#"$CONFDIR/"} $(sha "$f")"; done
    for i in 0 1 2 3 4; do echo "log ${LOGN[$i]} $(sha "${LOGP[$i]}")"; done
  } | LC_ALL=C sort > "$1"
}
ft_vr6_check() {
  inventory "$OUT/inventory-sitting.txt"
  grep -E "^config |^log LogOutput-prev.log " "$OUT/inventory-pre.txt" > "$OUT/vr6-pre.txt"
  grep -E "^config |^log LogOutput-prev.log " "$OUT/inventory-sitting.txt" > "$OUT/vr6-sitting.txt"
  if cmp -s "$OUT/vr6-pre.txt" "$OUT/vr6-sitting.txt"; then
    echo "$(st) FT-VM-VR6 files PASS (config folder and LogOutput-prev.log unchanged by the sitting)"
  elif ft_cfg_known_rewrite; then
    echo "$(st) FT-VM-VR6 files PASS with a known launch-time rewrite (R6-A3.11.15 FIX-11): com.competitiverounds.mod.cfg lost only the [Debug] ProfileCardParseSelfTest description block (the lazy bind, ProfileCard.cs:452; every launch's Bind-save writes it without one); sections, keys and values unchanged; diff (values masked): $FT_KNOWN_DIFF"
  else
    echo "$(st) FT-VM-VR6 files FAIL: $(diff "$OUT/vr6-pre.txt" "$OUT/vr6-sitting.txt" | grep '^[<>]' | tr '\n' ';')"; bad=1
  fi
}
# FIX-11 (R6-A3.11.15): the ONE proven launch-time rewrite. True only when (1) the cfg's inventory line is the only
# VR6 difference, (2) the cfg's sections and "key = value" lines (comment and blank lines ignored) are identical, and
# (3) the sitting's cfg is byte-identical to the pre-image with exactly the three-line description block of
# [Debug] ProfileCardParseSelfTest removed (its "##" text, "# Setting type: Boolean", "# Default value: false",
# directly above its key line). Any other comment-only shape is a difference and fails VR6 as before.
FT_PC_DESC="## Development only: once at startup, run the hover profile card's response parser over hostile display names and log a [CARD] verdict line."
ft_semantic() { tr -d '\r' < "$1" | grep -vE '^#|^[[:space:]]*$'; }
ft_cfg_known_rewrite() {
  local pc="$PRE/com.competitiverounds.mod.cfg" exp="$OUT/vr6-cfg-known-form.cfg"
  FT_KNOWN_DIFF=""
  [ -f "$pc" ] && [ -f "$CFG" ] || return 1
  [ "$(diff "$OUT/vr6-pre.txt" "$OUT/vr6-sitting.txt" | grep '^[<>]' | grep -vc ' com.competitiverounds.mod.cfg ')" = 0 ] || return 1
  [ "$(ft_semantic "$pc" | md5sum)" = "$(ft_semantic "$CFG" | md5sum)" ] || return 1
  awk -v d="$FT_PC_DESC" '
    { raw[NR] = $0; s = $0; sub(/\r$/, "", s); t[NR] = s }
    END {
      sec = ""; hit = 0
      for (i = 1; i <= NR; i++) {
        if (substr(t[i], 1, 1) == "[") sec = t[i]
        if (sec == "[Debug]" && index(t[i], "ProfileCardParseSelfTest = ") == 1 && i > 3 \
            && index(t[i-3], d) == 1 && t[i-2] == "# Setting type: Boolean" && t[i-1] == "# Default value: false") { hit++; k = i }
      }
      if (hit != 1) exit 1
      print k
    }' "$pc" > "$exp.line" || return 1
  # the expected form is cut with head and tail, which copy bytes as they are (awk on this seat drops the CR of a
  # CRLF line on output, so an awk-built form would accept a whole-file line-ending change: FIX-11 dry run 1)
  local k; k=$(tr -d '\r' < "$exp.line"); [ -n "$k" ] && [ "$k" -gt 3 ] || return 1
  { head -n $((k - 4)) "$pc"; tail -n +"$k" "$pc"; } > "$exp"
  cmp -s "$exp" "$CFG" || return 1
  FT_KNOWN_DIFF=$(diff "$pc" "$CFG" | tr -d '\r' | awk '{ if ($0 ~ /^[<>] [A-Za-z0-9_ .-]+ = /) sub(/ = .*/, " = <masked>"); print }' | tr '\n' ';' | cut -c1-600)
  return 0
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
  local i n p want got
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
    [ -f "$CFG" ] && { ft_move_aside "$CFG" "com.competitiverounds.mod.cfg" || return 0; }
  fi
  cp -p "$PRE/com.competitiverounds.mod.cfg" "$CFG"
  if cmp -s "$CFG" "$PRE/com.competitiverounds.mod.cfg"; then echo "$(st) FT-VM-LEASED cfg restored: byte-identical (cmp)"
  else echo "$(st) FT-VM-LEASED CFG RESTORE MISMATCH"; bad=1; fi
  inventory "$OUT/inventory-post.txt"
  if cmp -s "$OUT/inventory-pre.txt" "$OUT/inventory-post.txt"; then
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
