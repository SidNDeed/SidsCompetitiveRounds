#!/usr/bin/env bash
# ft_build.sh <configuration> <worktree> <log> [extra msbuild args...]
#
# One lane build of plugin/CompetitiveRounds.csproj, as the FrameTime build brief section 3 requires:
#   1. the VM disk gate: two readings of the AVERAGED 'Avg. Disk Queue Length' (5 s sample each, lesson 946),
#      one minute apart, both below 3; at most 10 tries, then a refusal;
#   2. the suite lock (SUITE-SEAT-PROTOCOL.md, amendment of 12 October: held per run): absent, the queue empty or
#      this lane first, then taken atomically, and released at process exit in every outcome (trap);
#   3. the build itself, always with -t:Rebuild -p:SkipCopyToPlugins=true -v:n;
#   4. the compile check: the Csc command line must be present; FrameTime must carry /optimize+ and SCR_FRAMETIME
#      in /define; Debug carries /optimize- and is reported as the negative control (exit 4, by design);
#   5. the plugins folder's installed DLL hashed before and after: it must not change.
# FrameTimeRef (B11 D3, the no-collector reference): no configuration of its own and no csproj edit. Step 3 builds
# FrameTime first and reads its define set from that compile's Csc line (the csproj's FrameTime DefineConstants as
# MSBuild resolved them, never a typed copy); it then builds -c FrameTime again with DefineConstants = that set plus
# SCR_FT_NOCOLLECTORS (a global property: the csproj cannot append to it), into its own folders (obj/FrameTimeRef/,
# bin/FrameTimeRef/). Step 4 requires the reference's /define set to equal FrameTime's plus SCR_FT_NOCOLLECTORS,
# exactly, and /optimize+ on both. Every configuration then gets the marker scan (lessons 306, 157): the two boot
# lines' literals as #US heap entries (length, UTF-16LE text, flag byte) and the UTF-16LE SCR_FT_REF=NOCOLLECTORS at
# any offset. FrameTime holds its own literal and not the marker; the reference holds the marker and its own literal
# and not FrameTime's; Release, Thunderstore and Debug hold neither. FrameTime and FrameTimeRef must also NOT hold the
# test dealer's marker SCR_CARD_EVIDENCE_TEST_DEALER_ON (UTF-16LE, any offset). Exit 6 = the marker scan refused.
# Stamps: take, exit and release, from date -u. Exit 0 = built and checked; 2 = refused before building;
# 3 = build failed; 4 = compile check refused; 5 = the installed DLL changed.
set -u
CONF="${1:?configuration}"; WT="${2:?worktree}"; LOG="${3:?log}"; shift 3
LANE=frame-time
LOCK=C:/Users/Sid/Documents/SidsCompetitiveRounds/ai-collab/session-tools/SUITE-SEAT.lock
QUEUE=C:/Users/Sid/Documents/SidsCompetitiveRounds/ai-collab/session-tools/SUITE-QUEUE.txt
PLUG="C:/Program Files (x86)/Steam/steamapps/common/ROUNDS/BepInEx/plugins/CompetitiveRounds/CompetitiveRounds.dll"
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
say() { echo "[ft_build $(stamp)] $*" | tee -a "$LOG"; }
readq() { powershell -NoProfile -Command "[math]::Round((Get-Counter '\PhysicalDisk(_Total)\Avg. Disk Queue Length' -SampleInterval 5 -MaxSamples 1).CounterSamples[0].CookedValue, 2)" | tr -d '\r'; }
below3() { awk -v q="$1" 'BEGIN { exit !(q != "" && q + 0 < 3) }'; }
plugsha() { if [ -f "$PLUG" ]; then sha256sum "$PLUG" | cut -c1-64; else echo absent; fi; }

: > "$LOG"
case "$CONF" in Release|Thunderstore|FrameTime|FrameTimeRef|Debug) ;; *) say "REFUSED: configuration $CONF"; exit 2;; esac
[ -f "$WT/plugin/CompetitiveRounds.csproj" ] || { say "REFUSED: no csproj under $WT"; exit 2; }
case "$WT" in *SidsCompetitiveRounds) say "REFUSED: the main worktree is not a lane worktree"; exit 2;; esac
say "build $CONF in $WT at $(git -C "$WT" rev-parse HEAD)"

# 1. disk gate
ok=0
for try in 1 2 3 4 5 6 7 8 9 10; do
  q1=$(readq); say "disk gate try $try: reading 1 = $q1"
  if below3 "$q1"; then
    sleep 60
    q2=$(readq); say "disk gate try $try: reading 2 = $q2"
    if below3 "$q2"; then ok=1; break; fi
  fi
  sleep 30
done
[ "$ok" = 1 ] || { say "REFUSED: the disk gate did not pass in 10 tries"; exit 2; }

# 2. suite lock
if [ -e "$LOCK" ]; then say "REFUSED: lock held: $(cat "$LOCK")"; exit 2; fi
if [ -s "$QUEUE" ] && ! head -n 1 "$QUEUE" | grep -q "^$LANE "; then
  say "REFUSED: SUITE-QUEUE.txt is not empty and does not name $LANE first: $(head -n 1 "$QUEUE")"; exit 2
fi
release() {
  if [ -e "$LOCK" ] && grep -q "^$LANE " "$LOCK"; then rm -f "$LOCK"; fi
  if [ -e "$LOCK" ]; then say "release: lock present and not ours: $(cat "$LOCK")"; else say "release: lock absent (proven by test -e)"; fi
}
if ( set -C; echo "$LANE $(stamp)" > "$LOCK" ) 2>/dev/null; then
  trap release EXIT
  say "take: $(cat "$LOCK")"
else
  say "REFUSED: another lane took the lock first"; exit 2
fi

# 3. build
before=$(plugsha); say "installed DLL before: $before"
csc_defs() { grep -E "csc(\.exe|\.dll)? .*/define:" "$1" | tail -1 | grep -oE "/define:[^ ]+" | tail -1 | sed 's#^/define:##; s#"##g'; }
if [ "$CONF" = FrameTimeRef ]; then
  ( cd "$WT" && dotnet build plugin/CompetitiveRounds.csproj -c FrameTime -t:Rebuild -p:SkipCopyToPlugins=true -v:n "$@" ) > "$LOG.ft.build" 2>&1
  rc=$?
  say "exit: dotnet build FrameTime (the define set's source) rc=$rc"
  FTDEFS=$(csc_defs "$LOG.ft.build")
  if [ "$rc" = 0 ] && [ -n "$FTDEFS" ]; then
    say "FrameTime define set, from its Csc line: $FTDEFS"
    ( cd "$WT" && dotnet build plugin/CompetitiveRounds.csproj -c FrameTime -t:Rebuild -p:SkipCopyToPlugins=true -v:n \
        "-p:DefineConstants=$(printf '%s' "$FTDEFS;SCR_FT_NOCOLLECTORS" | sed 's/;/%3B/g')" \
        -p:IntermediateOutputPath=obj/FrameTimeRef/ -p:OutputPath=bin/FrameTimeRef/ "$@" ) > "$LOG.build" 2>&1
    rc=$?
  elif [ "$rc" = 0 ]; then
    say "REFUSED: the FrameTime build's log holds no Csc /define"; rc=4
  fi
else
  ( cd "$WT" && dotnet build plugin/CompetitiveRounds.csproj -c "$CONF" -t:Rebuild -p:SkipCopyToPlugins=true -v:n "$@" ) > "$LOG.build" 2>&1
  rc=$?
fi
say "exit: dotnet build rc=$rc ($(grep -c . "$LOG.build" 2>/dev/null || echo 0) lines in $LOG.build)"
after=$(plugsha); say "installed DLL after: $after"
release; trap - EXIT
[ "$before" = "$after" ] || { say "FAIL: the installed DLL changed"; exit 5; }
[ "$rc" = 0 ] || { grep -E " error | error[A-Z]*[0-9]+:" "$LOG.build" | head -20 | tee -a "$LOG"; say "FAIL: build"; exit 3; }
grep -E "Warn|warn" "$LOG.build" | grep -oE "[0-9]+ Warning\(s\)" | tail -1 | while read -r w; do say "warnings: $w"; done

# 4. compile check
csc=$(grep -E "csc(\.exe|\.dll)? .*/define:" "$LOG.build" | tail -1)
[ -n "$csc" ] || { say "REFUSED: no Csc command line in the build log"; exit 4; }
defs=$(echo "$csc" | grep -oE "/define:[^ ]+" | tail -1)
opt=$(echo "$csc" | grep -oE "/optimize[+-]" | tail -1)
say "csc: $opt $defs"
if [ "$CONF" = FrameTimeRef ]; then dll=$(ls "$WT"/plugin/bin/FrameTimeRef/CompetitiveRounds.dll 2>/dev/null)
else dll=$(ls "$WT"/plugin/bin/"$CONF"/netstandard2.1/CompetitiveRounds.dll 2>/dev/null); fi
[ -n "$dll" ] && say "dll: $dll sha256 $(sha256sum "$dll" | cut -c1-64) bytes $(stat -c %s "$dll")"
[ -n "$dll" ] || { say "REFUSED: no output DLL for $CONF"; exit 4; }
# the marker scan (every configuration): which of the three probes the DLL holds
markers() {
  python -I -B - "$1" <<'PY'
import sys
b = open(sys.argv[1], "rb").read()
def us(s):
    # an exact #US heap entry: compressed blob length, UTF-16LE text, then the flag byte (0 or 1)
    n = 2 * len(s) + 1
    head = bytes([n]) if n < 0x80 else bytes([0x80 | (n >> 8), n & 0xFF])
    t = head + s.encode("utf-16-le")
    return any(t + f in b for f in (b"\x00", b"\x01"))
ft = us("[FRAME-TIME] build variant=FrameTime")
ref = us("[FRAME-TIME] build variant=FrameTimeRef SCR_FT_REF=NOCOLLECTORS")
mark = "SCR_FT_REF=NOCOLLECTORS".encode("utf-16-le") in b
dealer = "SCR_CARD_EVIDENCE_TEST_DEALER_ON".encode("utf-16-le") in b
print("ft=%d ref=%d marker=%d dealer=%d" % (ft, ref, mark, dealer))
PY
}
# the test dealer's absence: CardDrawEvidenceTestDealer.cs compiles only under SCR_CARD_EVIDENCE_TEST_DEALER, which no
# configuration defines, so FtRefSkip lists none of its classes; FrameTime and FrameTimeRef must not hold its marker
# SCR_CARD_EVIDENCE_TEST_DEALER_ON (UTF-16LE, any offset). Other configurations print the reading only.
dealer_ok() { case "$1" in FrameTime|FrameTimeRef) case "$2" in *" dealer=0") return 0;; *) return 1;; esac;; *) return 0;; esac; }
mk=$(markers "$dll" | tr -d '\r')
say "markers: $mk"
case "$CONF" in FrameTime) want="ft=1 ref=0 marker=0";; FrameTimeRef) want="ft=0 ref=1 marker=1";; *) want="ft=0 ref=0 marker=0";; esac
[ "${mk% dealer=*}" = "$want" ] || { say "REFUSED: the marker scan reads '$mk', $CONF needs '$want'"; exit 6; }
dealer_ok "$CONF" "$mk" || { say "REFUSED: the marker scan reads '$mk': the test dealer's marker is in the $CONF DLL"; exit 6; }
case "$CONF" in
  FrameTime)
    [ "$opt" = "/optimize+" ] && echo "$defs" | grep -q "SCR_FRAMETIME" || { say "REFUSED: FrameTime compile lacks /optimize+ or SCR_FRAMETIME"; exit 4; }
    say "OK FrameTime: optimized, SCR_FRAMETIME defined";;
  FrameTimeRef)
    # the reference's /define set equals FrameTime's plus SCR_FT_NOCOLLECTORS, exactly (as sets), both /optimize+
    ftopt=$(grep -E "csc(\.exe|\.dll)? .*/define:" "$LOG.ft.build" | tail -1 | grep -oE "/optimize[+-]" | tail -1)
    a=$(printf '%s;SCR_FT_NOCOLLECTORS' "$FTDEFS" | tr ';' '\n' | grep -v '^$' | sort -u | tr '\n' ';')
    b=$(csc_defs "$LOG.build" | tr ';' '\n' | grep -v '^$' | sort -u | tr '\n' ';')
    say "define sets: FrameTime+SCR_FT_NOCOLLECTORS {$a}; reference {$b}"
    [ "$a" = "$b" ] && [ "$opt" = "/optimize+" ] && [ "$ftopt" = "/optimize+" ] || { say "REFUSED: the reference's define set or optimization differs from FrameTime's plus SCR_FT_NOCOLLECTORS"; exit 4; }
    say "OK FrameTimeRef: optimized, FrameTime's define set plus SCR_FT_NOCOLLECTORS, exactly";;
  Debug)
    [ "$opt" = "/optimize-" ] && { say "REFUSED (negative control, as designed): Debug compiles /optimize-"; exit 4; }
    say "FAIL: Debug did not compile /optimize-"; exit 4;;
  *) say "OK $CONF";;
esac
exit 0
