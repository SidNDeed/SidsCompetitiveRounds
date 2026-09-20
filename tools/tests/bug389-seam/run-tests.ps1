# Bug 389 - run the victim-choice seam clean, then under twelve mutations. Each
# mutation names a test that MUST redden and a control that MUST stay green
# (#391): a suite that reddens at any change measures nothing, and one with no
# control cannot tell "the mutation was detected" from "the build broke".
#
# Takes no arguments and contains no absolute path: everything is resolved from
# this script's own location, so the harness runs from any clone.
#
#   pwsh -File tools/tests/bug389-seam/run-tests.ps1
#
# Generated mutants and build output go under work/, which is gitignored. The
# seam itself is never written to - a mutation is a COPY with one line changed,
# so a crashed run can never leave the shipped file mutated.
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$work = Join-Path $root 'work'
$seam = (Resolve-Path (Join-Path $root (Join-Path '..' (Join-Path '..' (Join-Path '..' (Join-Path 'plugin' 'ProximityVictimSeam.cs')))))).Path
$overall = 0

function Say([string]$text) { [Console]::WriteLine($text) }

function New-RunDir([string]$name) {
    $dir = Join-Path $work ('run-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    Copy-Item (Join-Path $root 'FixTests.csproj') $dir
    Copy-Item (Join-Path $root 'Program.cs') $dir
    return $dir
}

function Invoke-Suite([string]$name, [string]$seamSource) {
    $dir  = New-RunDir $name
    $proj = Join-Path $dir 'FixTests.csproj'
    Say ('--- build ' + $name + ' (seam: ' + (Split-Path -Leaf $seamSource) + ')')
    $build = & dotnet build $proj -c Release --nologo -p:SeamSource=$seamSource 2>&1
    $buildCode = $LASTEXITCODE
    Say (($build | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
    if ($buildCode -ne 0) { throw ('build failed for variant ' + $name) }
    $exe = Join-Path $dir (Join-Path 'bin' (Join-Path 'Release' (Join-Path 'net10.0' 'FixTests.exe')))
    if (-not (Test-Path $exe)) { throw ('no test binary produced for variant ' + $name) }
    Say ('--- run ' + $name)
    $out = & $exe 2>&1
    $code = $LASTEXITCODE
    $lines = @($out | ForEach-Object { [string]$_ })
    Say ($lines -join [Environment]::NewLine)
    Say ('--- exit ' + $name + ' = ' + $code)
    return [pscustomobject]@{ Name = $name; Code = $code; Lines = $lines }
}

function Test-Result([object]$run, [string]$testPrefix, [string]$wanted) {
    foreach ($line in $run.Lines) {
        $text = [string]$line
        if ($text -match ('^(PASS|FAIL)\s+' + [regex]::Escape($testPrefix) + '\s')) {
            return $text.StartsWith($wanted)
        }
    }
    return $false
}

# $pairs is an array of two-element arrays: @(@('find','replace'), ...). Every
# pair must match EXACTLY ONE site, or the mutation is not the one intended and
# the run is void.
function New-Mutant([string]$name, [object[]]$pairs) {
    if (-not (Test-Path $work)) { New-Item -ItemType Directory -Path $work -Force | Out-Null }
    $dst  = Join-Path $work ('mutant-' + $name + '.cs')
    $text = [System.IO.File]::ReadAllText($seam)
    # A single nested pair is flattened on the way into an [object[]] parameter,
    # which turns $pair into a STRING and $pair[0] into its first CHARACTER - a
    # one-space "anchor" that matches everywhere. Re-nest it.
    if ($pairs.Count -eq 2 -and ($pairs[0] -is [string])) { $pairs = @(, $pairs) }
    foreach ($pair in $pairs) {
        $find    = [string]$pair[0]
        $replace = [string]$pair[1]
        $hits = ([regex]::Matches($text, [regex]::Escape($find))).Count
        if ($hits -ne 1) {
            throw ('mutation ' + $name + ' anchor matched ' + $hits + ' sites, expected 1: ' + $find)
        }
        $text = $text.Replace($find, $replace)
    }
    [System.IO.File]::WriteAllText($dst, $text)
    Say ('--- mutant ' + $name + ': ' + $pairs.Count + ' anchor(s), 1 site each')
    return $dst
}

function Assert-Mutation([string]$label, [object]$run, [string]$redTest, [string]$controlTest) {
    $red = Test-Result $run $redTest 'FAIL'
    $ctl = Test-Result $run $controlTest 'PASS'
    if ($red -and $ctl) {
        Say ('RESULT ' + $label + ': OK - ' + $redTest + ' reddened, ' + $controlTest + ' control stayed green')
        return $true
    }
    Say ('RESULT ' + $label + ': FAILED - ' + $redTest + ' red=' + $red + ' ' + $controlTest + ' green=' + $ctl)
    return $false
}

Say ('date-utc: ' + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Say ('seam:     ' + (Split-Path -Leaf $seam))
Say ('seam sha256: ' + (Get-FileHash -Algorithm SHA256 $seam).Hash)
Say ''

# ---------- 1. clean ----------
$clean = Invoke-Suite 'clean' $seam
if ($clean.Code -ne 0) { Say 'RESULT clean: FAILED (expected every test to pass)'; $overall = 1 }
else { Say 'RESULT clean: OK - every test passed' }
Say ''

# ---------- 2. restore the cache ----------
# THE defect, put back: remember the first answer per holder and return it
# forever. This is the mutation that proves the suite measures the bug and not
# merely that a function is reachable.
# Every replacement stays on ONE line: a mutation that has to splice newlines
# into the source is a second thing that can go wrong inside the tool that is
# supposed to be checking the tests.
$cachePairs = @(
    @('        internal const int None = -1;',
      '        internal const int None = -1; internal static readonly System.Collections.Generic.Dictionary<int, int> MutantCache = new System.Collections.Generic.Dictionary<int, int>();'),
    @('            if (candidates == null || candidates.Count == 0) return None;',
      '            if (candidates == null || candidates.Count == 0) return None; { int mutantMemo; if (MutantCache.TryGetValue(holderId, out mutantMemo)) return mutantMemo; }'),
    @('            return chosen.Id;',
      '            MutantCache[holderId] = chosen.Id; return chosen.Id;')
)
$mutCache = New-Mutant 'cache' $cachePairs
$runCache = Invoke-Suite 'mut-cache' $mutCache
if (-not (Assert-Mutation 'cache mutation' $runCache 'F1' 'F2')) { $overall = 1 }
Say ''

# ---------- 3. make the capability gate vacuous ----------
$mutGate = New-Mutant 'gate' @(
    @('            return roomCapable && targetsOther;', '            return targetsOther;')
)
$runGate = Invoke-Suite 'mut-gate' $mutGate
if (-not (Assert-Mutation 'gate mutation' $runGate 'G1' 'G2')) { $overall = 1 }
Say ''

# ---------- 4. remove the range bound ----------
$mutRange = New-Mutant 'range' @(
    @('            if (!(Distance3D(triggerX, triggerY, triggerZ, chosen.X, chosen.Y, chosen.Z) < effectiveRange)) return None;',
      '            if (false) return None;')
)
$runRange = Invoke-Suite 'mut-range' $mutRange
if (-not (Assert-Mutation 'range mutation' $runRange 'F3a' 'F3b')) { $overall = 1 }
Say ''

# ---------- 5. flatten the predicate ----------
# Measure the range test in the plane instead of in three dimensions, which is
# what an earlier draft did. F3a is the control: a candidate out of range in the
# plane is still refused, so the control cannot notice the z term - which is
# exactly what makes F8 a measurement of the z term specifically.
$mutFlat = New-Mutant 'flat' @(
    @('            if (!(Distance3D(triggerX, triggerY, triggerZ, chosen.X, chosen.Y, chosen.Z) < effectiveRange)) return None;',
      '            if (!((float)Math.Sqrt(DistanceSquared(triggerX, triggerY, chosen.X, chosen.Y)) < effectiveRange)) return None;')
)
$runFlat = Invoke-Suite 'mut-flat' $mutFlat
if (-not (Assert-Mutation 'flat-predicate mutation' $runFlat 'F8' 'F3a')) { $overall = 1 }
Say ''

# ---------- 6. select the NearestAny path by transform position ----------
# The other half of the same defect: vanilla's GetClosestPlayer measures
# data.playerVel.position, not transform.position. F5 is the control - it uses
# candidates whose two positions coincide, so it cannot see this mutation.
$mutSel = New-Mutant 'selpos' @(
    @('                    float d2a = DistanceSquared(selectX, selectY, c.AnyX, c.AnyY);',
      '                    float d2a = DistanceSquared(selectX, selectY, c.X, c.Y);')
)
$runSel = Invoke-Suite 'mut-selpos' $mutSel
if (-not (Assert-Mutation 'selection-position mutation' $runSel 'F9' 'F5')) { $overall = 1 }
Say ''

# ---------- 7. "tidy up" the mis-indexed liveness gate ----------
# Outside FFA the trigger runs stock GetClosestPlayerInTeam, which reads its
# liveness test from the GLOBAL roster at the enemy subset's ordinal
# (PlayerManager.cs:113 vs :115). The seam reproduces that. This mutation
# replaces it with the per-candidate check a tidier loop would use - the exact
# change that makes the seam select enemies the trigger never looked at.
# F11 is the control: the same board with nobody dead, where both gates agree,
# so it cannot see the mutation and F10 is left measuring the indexing itself.
$mutMis = New-Mutant 'misindex' @(
    @('                    bool gateAlive = teamIndex < candidates.Count && !candidates[teamIndex].Dead;',
      '                    bool gateAlive = !c.Dead;')
)
$runMis = Invoke-Suite 'mut-misindex' $mutMis
if (-not (Assert-Mutation 'mis-index mutation' $runMis 'F10' 'F11')) { $overall = 1 }
Say ''


# ---------- 8. admit an unreadable roster entry at its defaults ----------
# The r1 HIGH put back: let a candidate the marshaller could not read through
# to the selection, where its defaulted team of zero decides which subset the
# enemy branch walks. F15 is the control - the same board with every entry
# read, so no entry carries the flag and the mutation is invisible to it.
$mutUnread = New-Mutant 'unread' @(
    @('                if (candidates[i].Unreadable) return Defer;',
      '                if (false) return Defer;')
)
$runUnread = Invoke-Suite 'mut-unread' $mutUnread
if (-not (Assert-Mutation 'unreadable-entry mutation' $runUnread 'F14' 'F15')) { $overall = 1 }
Say ''

# ---------- 9. key the capability cache on the frame alone ----------
# The r1 HIGH on the gate: drop the change stamp, so a join, a leave or a
# property delivery inside one frame cannot reach the cached answer. C2 is the
# control - both key terms are unchanged there, so a frame-only key reuses the
# answer exactly as the real one does.
$mutCapKey = New-Mutant 'capkey' @(
    @('            if (_has && frame == _frame && stamp == _stamp) return _value;',
      '            if (_has && frame == _frame) return _value;')
)
$runCapKey = Invoke-Suite 'mut-capkey' $mutCapKey
if (-not (Assert-Mutation 'capability-cache-key mutation' $runCapKey 'C1' 'C2')) { $overall = 1 }
Say ''

# ---------- 10. collapse the outcome signals onto one budget ----------
# Drop the reason from the diagnostic key, so two different reasons under one
# outcome share a budget and the second is never printed. S2 is the control: the
# LINE still names all three things, so it cannot see the key change.
$mutReason = New-Mutant 'reason' @(
    @('            return DiagKeyRoot + "/" + site + "/" + outcome + "/" + reason;',
      '            return DiagKeyRoot + "/" + site;')
)
$runReason = Invoke-Suite 'mut-reason' $mutReason
if (-not (Assert-Mutation 'outcome-signal mutation' $runReason 'S1' 'S2')) { $overall = 1 }
Say ''

# ---------- 11. compare the predicate in squares ----------
# Restore the squared comparison. It agrees with vanilla almost everywhere,
# which is the point: only at exact overlap with a range small enough for the
# product to underflow does it refuse where vanilla arms. F3a is the control -
# its candidate is far outside the ring, where both forms agree.
$mutSqRange = New-Mutant 'sqrange' @(
    @('            if (!(Distance3D(triggerX, triggerY, triggerZ, chosen.X, chosen.Y, chosen.Z) < effectiveRange)) return None;',
      '            { float mutRange = effectiveRange * effectiveRange; float mutDist = Distance3D(triggerX, triggerY, triggerZ, chosen.X, chosen.Y, chosen.Z); if (mutDist * mutDist >= mutRange) return None; }')
)
$runSqRange = Invoke-Suite 'mut-sqrange' $mutSqRange
if (-not (Assert-Mutation 'squared-predicate mutation' $runSqRange 'F16' 'F3a')) { $overall = 1 }
Say ''

# ---------- 12. stop clearing the fighter capability on spectator staging ----------
# Empty the list the spectator pre-join merge loops over, so a seat that fought
# a match keeps advertising the fighter capability while watching one. K2 is the
# control - the key's own name and value are untouched by the list.
$mutKeys = New-Mutant 'fighterkeys' @(
    @('        internal static readonly string[] FighterCapabilityKeys = new string[] { CapabilityProp };',
      '        internal static readonly string[] FighterCapabilityKeys = new string[0];')
)
$runKeys = Invoke-Suite 'mut-fighterkeys' $mutKeys
if (-not (Assert-Mutation 'fighter-capability-keys mutation' $runKeys 'K1' 'K2')) { $overall = 1 }
Say ''

# ---------- 13. write vanilla's field without a victim ----------
# Drop the victim term from the prefix decision, so a Victim resolution with
# nothing resolved still writes. Vanilla dereferences that field with no null
# guard. P1 is the control: the Defer branch is untouched.
$mutPrefix = New-Mutant 'prefixwrite' @(
    @('            if (outcome != ProximityResolution.Victim || !victimKnown) return ProximityPrefixAction.SkipOriginal;',
      '            if (outcome != ProximityResolution.Victim) return ProximityPrefixAction.SkipOriginal;')
)
$runPrefix = Invoke-Suite 'mut-prefixwrite' $mutPrefix
if (-not (Assert-Mutation 'prefix-write mutation' $runPrefix 'P2' 'P1')) { $overall = 1 }
Say ''

if ($overall -eq 0) { Say 'BUG 389 SEAM SUITE: ALL CHECKS PASSED' }
else { Say 'BUG 389 SEAM SUITE: FAILURES PRESENT' }
exit $overall
