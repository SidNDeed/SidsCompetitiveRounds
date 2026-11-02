#!/usr/bin/env bash
# ft_proof.sh <base-sha40> <lane-sha40> <proofA> <proofB> <outdir> [--stage]
#
# Format M's integrity bar (FORMAT-M-PLAN.md V2 part d, F09 F10): nothing of format M can reach a shipped DLL.
# Five steps, each with a logged verdict; the first failure stops the proof (exit 1); a refusal before any
# verdict exits 2. Every build goes through ft_build.sh (the disk gate, the suite lock per build, -t:Rebuild,
# -p:SkipCopyToPlugins=true, -v:n, the installed DLL hashed before and after) with
# -p:IncludeSourceRevisionInInformationalVersion=false, so the commit stamp cannot make a pair differ.
#
# The caller creates the two proof worktrees beforehand, both detached at <base>, at different paths, clean
# (this script creates and removes no worktree). Step 3 moves proofB to <lane> with a detached checkout of a
# commit (never a path checkout) after checking it is clean.
#
#   1. pinned inputs: per build, `dotnet --version`, the sha256 of every /reference: on the Csc command line and
#      the Krafs.Publicizer version in the csproj; within each pair they must be equal, or the pair is refused;
#   2. path-neutral baseline: <base> built in Release in proofA and in proofB; the two DLLs must be equal; if not,
#      ft_dll_diff.py dumps both and the proof stops;
#   3. the pairs: Release and Thunderstore, <base> in proofA against <lane> in proofB; each pair equal;
#   4. the source check: hunk_check.py <base> <lane> with the Release and Thunderstore /define lists read from
#      step 3's own Csc lines;
#   5. the scans: <lane> built in FrameTime in proofB must scan -Build FrameTime clean; step 3's lane Release DLL
#      must scan Standalone clean. Only with --stage (the integrator's go, build brief) is the lane folder
#      C:/shared/builds/lanes/frametime-<sha8>/ written: the DLL, sha256.txt, then README.txt last.
set -u
[ $# -ge 5 ] || { echo "usage: ft_proof.sh <base-sha40> <lane-sha40> <proofA> <proofB> <outdir> [--stage]"; exit 2; }
BASE=$1; LANE=$2; A=$3; B=$4; OUT=$5; STAGE=${6:-}
HERE=$(cd "$(dirname "$0")" && pwd)
BUILD="$HERE/ft_build.sh"
SCAN="$HERE/../scan-build-markers.ps1"
mkdir -p "$OUT" || exit 2
LOGF="$OUT/proof.log"
say() { echo "[ft_proof $(date -u +%FT%TZ)] $*" | tee -a "$LOGF"; }
fail() { say "PROOF FAIL: $*"; exit 1; }
refuse() { say "REFUSED: $*"; exit 2; }

[[ $BASE =~ ^[0-9a-f]{40}$ ]] || refuse "base is not 40 hex digits"
[[ $LANE =~ ^[0-9a-f]{40}$ ]] || refuse "lane is not 40 hex digits"
[ -z "$(ls -A "$OUT" | grep -v '^proof.log$')" ] || refuse "outdir $OUT is not empty"
[ "$A" != "$B" ] || refuse "the two proof worktrees must be different paths"
for w in "$A" "$B"; do
  [ "$(git -C "$w" rev-parse HEAD 2>/dev/null)" = "$BASE" ] || refuse "$w is not at $BASE"
  [ -z "$(git -C "$w" status --porcelain)" ] || refuse "$w is not clean"
done
say "base $BASE lane $LANE; proofA $A; proofB $B"

EXTRA="-p:IncludeSourceRevisionInInformationalVersion=false"
dll_of() { echo "$1/plugin/bin/$2/netstandard2.1/CompetitiveRounds.dll"; }

# one build: $1 worktree, $2 configuration, $3 name. Writes OUT/<name>.{inputs,sha,dll}.
build() {
  local w=$1 conf=$2 name=$3
  { echo "dotnet $(cd "$w" && dotnet --version)"
    grep -oE 'Krafs.Publicizer"[^>]*Version="[^"]+"' "$w/plugin/CompetitiveRounds.csproj"; } > "$OUT/$name.inputs"
  bash "$BUILD" "$conf" "$w" "$OUT/$name.log" "$EXTRA" >> "$LOGF" 2>&1 || fail "build $name ($conf in $w) exited $?"
  local csc
  csc=$(grep -E "csc(\.exe|\.dll)? .*/define:" "$OUT/$name.log.build" | tail -1)
  [ -n "$csc" ] || fail "build $name: no Csc command line"
  echo "$csc" > "$OUT/$name.csc"
  echo "$csc" | grep -oE '/reference:("[^"]+"|[^ ]+)' | sed -e 's#^/reference:##' -e 's#"##g' | sort | while read -r r; do
    echo "ref $(sha256sum "$r" | cut -c1-64) $(basename "$r")"
  done >> "$OUT/$name.inputs"
  local d; d=$(dll_of "$w" "$conf")
  [ -f "$d" ] || fail "build $name: no DLL at $d"
  cp "$d" "$OUT/$name.dll"
  sha256sum "$d" | cut -c1-64 > "$OUT/$name.sha"
  say "built $name: $(cat "$OUT/$name.sha"), $(grep -c '^ref ' "$OUT/$name.inputs") references"
}

# a pair: $1 $2 names; step 1's input check, then the sha256 comparison, with the dump on a mismatch
pair() {
  if ! cmp -s "$OUT/$1.inputs" "$OUT/$2.inputs"; then
    diff "$OUT/$1.inputs" "$OUT/$2.inputs" | head -20 >> "$LOGF"
    refuse "step 1: pinned inputs differ between $1 and $2 (see the log)"
  fi
  say "step 1 PASS for $1/$2: dotnet, $(grep -c '^ref ' "$OUT/$1.inputs") reference hashes and the publicizer equal"
  if [ "$(cat "$OUT/$1.sha")" != "$(cat "$OUT/$2.sha")" ]; then
    python -I -B "$HERE/ft_dll_diff.py" "$OUT/$1.dll" "$OUT/$2.dll" >> "$LOGF" 2>&1
    return 1
  fi
  return 0
}

# 2. path-neutral baseline
build "$A" Release base-A-release
build "$B" Release base-B-release
pair base-A-release base-B-release || fail "step 2: main's Release DLL differs between the two paths (dump in the log)"
say "step 2 PASS: main's Release DLL equal at both paths"

# 3. the pairs
[ -z "$(git -C "$B" status --porcelain)" ] || fail "proofB changed during step 2"
git -C "$B" checkout -q --detach "$LANE" || fail "could not move proofB to the lane"
[ "$(git -C "$B" rev-parse HEAD)" = "$LANE" ] || fail "proofB is not at the lane"
build "$B" Release lane-release
pair base-A-release lane-release || fail "step 3: Release DLLs differ between main and the lane (dump in the log)"
build "$A" Thunderstore base-thunderstore
build "$B" Thunderstore lane-thunderstore
pair base-thunderstore lane-thunderstore || fail "step 3: Thunderstore DLLs differ between main and the lane (dump in the log)"
say "step 3 PASS: Release and Thunderstore DLLs equal between main and the lane"

# 4. the source check, with each configuration's own /define list
R=$(grep -oE "/define:[^ ]+" "$OUT/lane-release.csc" | tail -1 | sed 's#^/define:##')
T=$(grep -oE "/define:[^ ]+" "$OUT/lane-thunderstore.csc" | tail -1 | sed 's#^/define:##')
[ -n "$R" ] && [ -n "$T" ] || fail "step 4: no /define list in step 3's Csc lines"
python -I -B "$HERE/hunk_check.py" "$B" "$BASE" "$LANE" --release "$R" --thunderstore "$T" >> "$LOGF" 2>&1 \
  || fail "step 4: hunk_check.py failed (see the log)"
say "step 4 PASS: hunk_check.py"

# 5. the scans, then staging only with --stage
build "$B" FrameTime lane-frametime
powershell -NoProfile -ExecutionPolicy Bypass -File "$SCAN" -Dll "$(cygpath -w "$OUT/lane-frametime.dll")" -Build FrameTime \
  > "$OUT/scan-frametime.log" 2>&1 || fail "step 5: the FrameTime DLL's scan failed (scan-frametime.log)"
powershell -NoProfile -ExecutionPolicy Bypass -File "$SCAN" -Dll "$(cygpath -w "$OUT/lane-release.dll")" \
  > "$OUT/scan-release.log" 2>&1 || fail "step 5: the lane Release DLL's scan failed (scan-release.log)"
say "step 5 PASS: FrameTime DLL scans FrameTime; lane Release DLL scans Standalone"
if [ "$STAGE" = "--stage" ]; then
  S8=${LANE:0:8}
  DEST="C:/shared/builds/lanes/frametime-$S8"
  [ -e "$DEST" ] && fail "staging: $DEST exists"
  mkdir -p "$DEST" && cp "$OUT/lane-frametime.dll" "$DEST/CompetitiveRounds.dll" \
    && sha256sum "$DEST/CompetitiveRounds.dll" | cut -c1-64 > "$DEST/sha256.txt" \
    && printf 'FrameTime lane build of %s (format M). Not a release. Proof log: %s\n' "$LANE" "$LOGF" > "$DEST/README.txt" \
    || fail "staging failed"
  say "staged $DEST"
else
  say "not staged (no --stage: the lane folder waits for the integrator's go)"
fi
say "PROOF PASS"
exit 0
