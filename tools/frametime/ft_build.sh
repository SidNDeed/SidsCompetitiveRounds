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
case "$CONF" in Release|Thunderstore|FrameTime|Debug) ;; *) say "REFUSED: configuration $CONF"; exit 2;; esac
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
( cd "$WT" && dotnet build plugin/CompetitiveRounds.csproj -c "$CONF" -t:Rebuild -p:SkipCopyToPlugins=true -v:n "$@" ) > "$LOG.build" 2>&1
rc=$?
say "exit: dotnet build rc=$rc ($(grep -c . "$LOG.build") lines in $LOG.build)"
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
dll=$(ls "$WT"/plugin/bin/"$CONF"/netstandard2.1/CompetitiveRounds.dll 2>/dev/null)
[ -n "$dll" ] && say "dll: $dll sha256 $(sha256sum "$dll" | cut -c1-64) bytes $(stat -c %s "$dll")"
case "$CONF" in
  FrameTime)
    [ "$opt" = "/optimize+" ] && echo "$defs" | grep -q "SCR_FRAMETIME" || { say "REFUSED: FrameTime compile lacks /optimize+ or SCR_FRAMETIME"; exit 4; }
    say "OK FrameTime: optimized, SCR_FRAMETIME defined";;
  Debug)
    [ "$opt" = "/optimize-" ] && { say "REFUSED (negative control, as designed): Debug compiles /optimize-"; exit 4; }
    say "FAIL: Debug did not compile /optimize-"; exit 4;;
  *) say "OK $CONF";;
esac
exit 0
