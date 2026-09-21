# Bug 389 - run the seam clean, then under mutation. Each mutation names a test
# that MUST redden and a control that MUST stay green (#391): a suite that
# reddens at any change measures nothing, and one with no control cannot tell
# "the mutation was detected" from "the build broke".
#
# Takes no arguments and contains no absolute path: everything is resolved from
# this script's own location, so the harness runs from any clone.
#
#   powershell -NoProfile -File tools/tests/bug389-seam/run-tests.ps1
#
# EVERY ANCHOR IS RESOLVED INSIDE A NAMED MEMBER, never file-wide (#432). A
# file-wide count cannot tell the site that is where it belongs from the same
# line relocated into another member, and a file-wide Replace would rewrite both.
# Get-MemberSpan bounds the member, the hit count is asserted INSIDE that span,
# and the splice is applied to the span alone - so a matching line elsewhere in
# the file is reported and left untouched. Assert-BuilderRejects is the negative
# control on the builder itself: hand it an anchor that lives in another member
# and it must refuse to produce a mutant at all.
#
# THREE KINDS OF RUN, because the repair has three halves.
#   * SEAM mutations compile a one-line-changed COPY of
#     plugin/ProximityVictimSeam.cs. The seam itself is never written to, so a
#     crashed run cannot leave the shipped file mutated.
#   * WIRING mutations leave the seam alone and point the suite's
#     BUG389_SOURCE_ROOT at a one-line-changed COPY of the shipped files this
#     harness cannot compile - they carry Unity, Photon and MSBuild.
#   * The PRIOR-MECHANISM run points that same root at the round-2 files,
#     recovered from git rather than copied by hand, and requires every N case -
#     the ones that assert round 3's deletions - to redden there while a case
#     untouched by the change stays green. Without it "no selector here" is a
#     statement no run has ever seen fail.
#
# Generated mutants and build output go under work/, which is gitignored.
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$work = Join-Path $root 'work'
$repo = (Resolve-Path (Join-Path $root (Join-Path '..' (Join-Path '..' '..')))).Path
$seam = (Resolve-Path (Join-Path $repo (Join-Path 'plugin' 'ProximityVictimSeam.cs'))).Path
$overall = 0

# The round-2 tip. The N cases must redden against these files.
$priorTip = '93f4db3018048149a5f9dbe2ef76fc28d82ddf52'

# The shipped files the W, N and S4 cases read. A wiring mutant copies all of
# them and changes one line in one of them, so every other case in the same run
# is an untouched control.
#
# Program.cs IS ON THIS LIST, and it is not a shipped file. W17 asserts that a
# claim deleted from two shipped files is absent, and the round-4 pass left that
# same claim standing in the harness's own comment - outside every file the case
# read, so the suite that certifies the deletion was still making the claim. The
# text under test therefore includes this file. Note what is NOT affected: the
# COMPILED harness in every run comes from $root, so a wiring mutant changes only
# what W17 reads, never what executes.
$wireFiles = @(
    'plugin/SpectatorSession.cs',
    'plugin/Plugin.cs',
    'plugin/RoomActors.cs',
    'plugin/ProximityVictimPatches.cs',
    'plugin/ProximityVictimSeam.cs',
    'plugin/PerfPatches.cs',
    'plugin/ApiClient.cs',
    'plugin/CompetitiveRounds.csproj',
    'tools/tests/bug389-seam/Program.cs'
)

function Say([string]$text) { [Console]::WriteLine($text) }

# Paths in this log are printed relative to the repo root: a log is read by
# someone who is not on this machine.
function Rel([string]$p) {
    if ([string]::IsNullOrEmpty($p)) { return '<unset>' }
    $full = [System.IO.Path]::GetFullPath($p)
    if ($full.StartsWith($repo, [System.StringComparison]::OrdinalIgnoreCase)) {
        $r = $full.Substring($repo.Length).TrimStart([char]92, [char]47)
        if ($r -eq '') { return '.' }
        return ($r -replace '\\', '/')
    }
    return $full
}

# ---------------------------------------------------------------------------
# Member spans. Returns @(openBraceIndex, closeBraceIndex) for the C# member
# whose declaration is $signature, or for the region delimited by $signature and
# $endMarker when one is given (project files have no braces to match).
# ---------------------------------------------------------------------------
function Get-MemberSpan([string]$text, [string]$signature, [string]$endMarker) {
    $sigs = ([regex]::Matches($text, [regex]::Escape($signature))).Count
    if ($sigs -ne 1) {
        throw ('member signature matched ' + $sigs + ' site(s), expected 1: ' + $signature)
    }
    $sig = $text.IndexOf($signature, [System.StringComparison]::Ordinal)

    if (-not [string]::IsNullOrEmpty($endMarker)) {
        $close = $text.IndexOf($endMarker, $sig, [System.StringComparison]::Ordinal)
        if ($close -lt 0) { throw ('could not find the end marker after: ' + $signature) }
        return @($sig, $close)
    }

    # Bound the member by INDENTATION, not by counting braces. A literal brace
    # inside a string reads as structure to a counter, and ApiClient.cs carries
    # JSON in string literals - the count never returns to zero and the member
    # cannot be bounded at all. Every member in this tree closes with a brace
    # alone on a line at the declaration's own indentation.
    $open = $text.IndexOf([char]123, $sig)
    if ($open -lt 0) { throw ('could not find a member body for: ' + $signature) }
    $lineStart = $text.LastIndexOf([char]10, $sig) + 1
    $indent = 0
    while ((($lineStart + $indent) -lt $text.Length) -and ($text[$lineStart + $indent] -eq [char]32)) { $indent++ }
    $closer = ([string][char]10) + (' ' * $indent) + '}'
    $close = $text.IndexOf($closer, $open, [System.StringComparison]::Ordinal)
    if ($close -lt 0) { throw ('could not bound the member body for: ' + $signature) }
    return @($open, ($close + $closer.Length - 1))
}

# Splice one anchor inside one member. Asserts EXACTLY ONE hit inside the span,
# reports how many identical lines live elsewhere in the file, and leaves those
# alone.
function Edit-InMember([string]$label, [string]$text, [string]$member, [string]$find, [string]$replace, [string]$endMarker) {
    $span  = Get-MemberSpan $text $member $endMarker
    $open  = [int]$span[0]
    $close = [int]$span[1]
    $body  = $text.Substring($open, $close - $open + 1)
    $inside = ([regex]::Matches($body, [regex]::Escape($find))).Count
    if ($inside -ne 1) {
        throw ('mutation ' + $label + ' anchor matched ' + $inside + ' site(s) inside "' + $member + '", expected 1: ' + $find)
    }
    $total = ([regex]::Matches($text, [regex]::Escape($find))).Count
    Say ('---   anchor in "' + $member + '": 1 site inside, ' + ($total - $inside) + ' elsewhere (left untouched)')
    return $text.Substring(0, $open) + $body.Replace($find, $replace) + $text.Substring($close + 1)
}

function New-RunDir([string]$name) {
    $dir = Join-Path $work ('run-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    Copy-Item (Join-Path $root 'FixTests.csproj') $dir
    Copy-Item (Join-Path $root 'Program.cs') $dir
    return $dir
}

function Invoke-Suite([string]$name, [string]$seamSource, [string]$sourceRoot) {
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
    # The invocation, immediately above the results it produced.
    Say ('--- command: ' + (Rel $exe) + '   [BUG389_SOURCE_ROOT=' + (Rel $sourceRoot) + ']')
    $env:BUG389_SOURCE_ROOT = $sourceRoot
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

# $edits is an array of three-element arrays: @(@('member','find','replace'), ...)
function New-Mutant([string]$name, [object[]]$edits) {
    if (-not (Test-Path $work)) { New-Item -ItemType Directory -Path $work -Force | Out-Null }
    $dst  = Join-Path $work ('mutant-' + $name + '.cs')
    $text = [System.IO.File]::ReadAllText($seam)
    # A single nested triple is flattened on the way into an [object[]]
    # parameter, which turns $edit into a STRING and $edit[0] into its first
    # CHARACTER - a one-character "member" that matches everywhere. Re-nest it.
    if ($edits.Count -eq 3 -and ($edits[0] -is [string])) { $edits = @(, $edits) }
    Say ('--- mutant ' + $name + ': ' + $edits.Count + ' edit(s)')
    foreach ($edit in $edits) {
        $text = Edit-InMember $name $text ([string]$edit[0]) ([string]$edit[1]) ([string]$edit[2]) ''
    }
    [System.IO.File]::WriteAllText($dst, $text)
    return $dst
}

# A wiring mutation: copy the shipped files the cases read, change ONE line
# inside ONE named member of ONE of them, and hand the copy to the suite as its
# source root. The shipped tree is never written to.
function Copy-WireFiles([string]$dir) {
    foreach ($rel in $wireFiles) {
        $dst = Join-Path $dir $rel
        New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
        Copy-Item (Join-Path $repo $rel) $dst
    }
}

function New-WireRoot([string]$name, [string]$file, [string]$member, [string]$find, [string]$replace, [string]$endMarker) {
    $dir = Join-Path $work ('wire-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    Copy-WireFiles $dir
    $target = Join-Path $dir $file
    Say ('--- wiring mutant ' + $name + ': in ' + $file)
    $text = [System.IO.File]::ReadAllText($target)
    $text = Edit-InMember ('wire-' + $name) $text $member $find $replace $endMarker
    [System.IO.File]::WriteAllText($target, $text)
    return $dir
}

# The same, for a mutation that is only honest as SEVERAL edits: a genuine swap
# of two exit assignments has to move both, or it is a collapse of one path onto
# another and not a swap. Every edit is resolved inside the named member and
# still has to match EXACTLY ONE site there, so an edit that would rewrite a
# line another edit has already produced is refused rather than applied twice.
# $edits is an array of three-element arrays: @(@('member','find','replace'), ...)
function New-WireRootEdits([string]$name, [string]$file, [object[]]$edits) {
    $dir = Join-Path $work ('wire-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    Copy-WireFiles $dir
    $target = Join-Path $dir $file
    if ($edits.Count -eq 3 -and ($edits[0] -is [string])) { $edits = @(, $edits) }
    Say ('--- wiring mutant ' + $name + ': in ' + $file + ', ' + $edits.Count + ' edit(s)')
    $text = [System.IO.File]::ReadAllText($target)
    foreach ($edit in $edits) {
        $text = Edit-InMember ('wire-' + $name) $text ([string]$edit[0]) ([string]$edit[1]) ([string]$edit[2]) ''
    }
    [System.IO.File]::WriteAllText($target, $text)
    return $dir
}

# The round-2 files, recovered from git rather than copied by hand, so the
# comparison cannot drift and needs no absolute path.
function New-PriorRoot([string]$name, [string]$tip) {
    $dir = Join-Path $work ('prior-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    foreach ($rel in $wireFiles) {
        $blob = & git -C $repo show ($tip + ':' + $rel) 2>&1
        if ($LASTEXITCODE -ne 0) { throw ('could not read ' + $rel + ' at ' + $tip) }
        $dst = Join-Path $dir $rel
        New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
        [System.IO.File]::WriteAllText($dst, (($blob | ForEach-Object { [string]$_ }) -join [Environment]::NewLine))
    }
    Say ('--- prior-mechanism root ' + $name + ': ' + $wireFiles.Count + ' files at ' + $tip.Substring(0, 7))
    return $dir
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

function Assert-Mutations([string]$label, [object]$run, [string[]]$redTests, [string]$controlTest) {
    $ok = $true
    $detail = @()
    foreach ($t in $redTests) {
        $red = Test-Result $run $t 'FAIL'
        if (-not $red) { $ok = $false }
        $detail += ($t + '=' + $(if ($red) { 'red' } else { 'GREEN' }))
    }
    $ctl = Test-Result $run $controlTest 'PASS'
    if (-not $ctl) { $ok = $false }
    if ($ok) {
        Say ('RESULT ' + $label + ': OK - ' + ($redTests -join ', ') + ' all reddened, ' + $controlTest + ' control stayed green')
        return $true
    }
    Say ('RESULT ' + $label + ': FAILED - ' + ($detail -join ' ') + ' ' + $controlTest + ' green=' + $ctl)
    return $false
}

# THE NEGATIVE CONTROL ON THE BUILDER ITSELF. Hand it a real anchor that lives
# in a DIFFERENT member and it must refuse: that is the whole difference between
# an anchor resolved inside its member and one counted file-wide.
function Assert-BuilderRejects([string]$label, [string]$member, [string]$find) {
    $threw = $false
    $message = ''
    try {
        New-Mutant ('reject-' + $label) @(, @($member, $find, '// (relocated anchor)')) | Out-Null
    } catch {
        $threw = $true
        $message = [string]$_.Exception.Message
    }
    if ($threw) {
        Say ('RESULT builder rejects a relocated anchor (' + $label + '): OK - ' + $message)
        return $true
    }
    Say ('RESULT builder rejects a relocated anchor (' + $label + '): FAILED - the builder accepted an anchor outside "' + $member + '"')
    return $false
}

Say ('date-utc: ' + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Say ('seam:     ' + (Split-Path -Leaf $seam))
Say ('seam sha256: ' + (Get-FileHash -Algorithm SHA256 $seam).Hash)
Say ('source root for the wiring cases: ' + (Rel $repo))
Say ('prior mechanism tip: ' + $priorTip)
Say ''

# ---------- 1. clean ----------
$clean = Invoke-Suite 'clean' $seam $repo
if ($clean.Code -ne 0) { Say 'RESULT clean: FAILED (expected every test to pass)'; $overall = 1 }
else { Say 'RESULT clean: OK - every test passed' }
Say ''

# ---------- 2. the builder's own negative control ----------
# `return runSoFar && prefixReturn;` is a real line of the seam - it lives in
# RunOriginalAfter. Naming ShouldRepair as its member must be refused rather
# than silently spliced somewhere else.
if (-not (Assert-BuilderRejects 'fold-line-in-the-gate' `
    'internal static bool ShouldRepair(ProximityGateState state, bool targetsOther)' `
    '            return runSoFar && prefixReturn;')) { $overall = 1 }
Say ''

# ---------- 2b. the capability key has never been released ----------
# K3 holds the seam's non-rotation argument to one fact: no released build
# advertises cr_prox1. That is a claim about the RELEASE HISTORY, which no
# compiled case can reach, so the runner checks it here.
#
# WITH A POSITIVE CONTROL, because a search that finds nothing proves nothing
# (#342/#441): cr_pois2 is a capability key of the same family that DID ship, so
# the same probe against the same tag must find it. A probe that reports both
# keys absent has told us about the probe, not about the keys.
$baseTag = 'v1.40.3'
& git -C $repo grep -q 'cr_prox1' $baseTag -- plugin 2>&1 | Out-Null
$keyAbsentAtBase = ($LASTEXITCODE -ne 0)
& git -C $repo grep -q 'cr_pois2' $baseTag -- plugin 2>&1 | Out-Null
$controlKeyPresent = ($LASTEXITCODE -eq 0)
if ($keyAbsentAtBase -and $controlKeyPresent) {
    Say ('RESULT capability key never released: OK - cr_prox1 absent at ' + $baseTag + ', control key cr_pois2 present at the same tag')
} else {
    Say ('RESULT capability key never released: FAILED - cr_prox1 absent=' + $keyAbsentAtBase + ', control cr_pois2 present=' + $controlKeyPresent)
    $overall = 1
}
Say ''

# ---------- 3. answer only the first time ----------
# THE DEFECT, PUT BACK. Vanilla resolves its victim once and keeps it; if this
# decision answered only the first time the effect would keep its first victim
# exactly as an unpatched build does. This is the mutation that proves the suite
# measures the bug and not merely that a function is reachable.
$mutOnce = New-Mutant 'once' @(
    @('internal static class ProximityVictim',
      '        internal const int MaxOutcomeSignals = 1;',
      '        internal const int MaxOutcomeSignals = 1; private static bool _mutantAnswered;'),
    @('internal static ProximityPrefixAction VictimAction(',
      '            return ProximityPrefixAction.WriteVictimAndRun;',
      '            { if (_mutantAnswered) return ProximityPrefixAction.RunVanillaUntouched; _mutantAnswered = true; return ProximityPrefixAction.WriteVictimAndRun; }')
)
$runOnce = Invoke-Suite 'mut-once' $mutOnce $repo
if (-not (Assert-Mutation 'answer-once mutation' $runOnce 'V1' 'V2')) { $overall = 1 }
Say ''

# ---------- 4. repair a call no ring drives ----------
# The defect is a field that survives REPEATED invocation, and only a
# PlayerInRangeTrigger invokes these effects repeatedly. Drop the term and an
# AttackTrigger- or DelayEvent-driven call is repaired against a rule this
# repair never measured.
$mutRingless = New-Mutant 'ringless' @(, @(
    'internal static ProximityPrefixAction VictimAction(',
    '            if (!ringDriven) return ProximityPrefixAction.RunVanillaUntouched;',
    '            if (false) return ProximityPrefixAction.RunVanillaUntouched;'))
$runRingless = Invoke-Suite 'mut-ringless' $mutRingless $repo
if (-not (Assert-Mutation 'ring-driven mutation' $runRingless 'V3' 'V2')) { $overall = 1 }
Say ''

# ---------- 5. write an empty resolution ----------
# Vanilla dereferences its victim field with no null guard
# (DealDamageToPlayer.cs:45). Writing the empty answer turns "the game's own
# targeting found nobody" into an exception on a path vanilla, holding its
# cache, never takes.
$mutWriteNull = New-Mutant 'writenull' @(, @(
    'internal static ProximityPrefixAction VictimAction(',
    '            if (!vanillaAnswered) return ProximityPrefixAction.RunVanillaUntouched;',
    '            if (false) return ProximityPrefixAction.RunVanillaUntouched;'))
$runWriteNull = Invoke-Suite 'mut-writenull' $mutWriteNull $repo
if (-not (Assert-Mutation 'empty-resolution mutation' $runWriteNull 'V4' 'V2')) { $overall = 1 }
Say ''

# ---------- 6. let the repair suppress the original ----------
# The bar row the previous design could not meet. A victim repair that can
# return false can turn a change about WHO takes damage into a change about
# WHETHER anyone does.
$mutSuppress = New-Mutant 'suppress' @(, @(
    'internal static ProximityPrefixAction VictimAction(',
    '            if (!ringDriven) return ProximityPrefixAction.RunVanillaUntouched;',
    '            if (!ringDriven) return ProximityPrefixAction.SkipOriginal;'))
$runSuppress = Invoke-Suite 'mut-suppress' $mutSuppress $repo
if (-not (Assert-Mutation 'suppression mutation' $runSuppress 'V5' 'V2')) { $overall = 1 }
Say ''

# ---------- 7. make the capability gate vacuous ----------
$mutGate = New-Mutant 'gate' @(, @(
    'internal static bool ShouldRepair(ProximityGateState state, bool targetsOther)',
    '            return state == ProximityGateState.Capable && targetsOther;',
    '            return targetsOther;'))
$runGate = Invoke-Suite 'mut-gate' $mutGate $repo
if (-not (Assert-Mutation 'gate mutation' $runGate 'G1' 'G2')) { $overall = 1 }
Say ''

# ---------- 8. give two gate states one reason line ----------
# The line is also the budget key, so two causes sharing it means the second is
# never printed and the reader is told the first one instead: "the room does not
# all carry the repair" for a patch that failed to attach on this seat.
$mutGateReason = New-Mutant 'gatereason' @(, @(
    'internal static string GateReason(ProximityGateState state)',
    '                case ProximityGateState.PatchesNotAttached: return "this seat''s repair patches are not attached";',
    '                case ProximityGateState.PatchesNotAttached: return "the room does not all carry the repair";'))
$runGateReason = Invoke-Suite 'mut-gatereason' $mutGateReason $repo
if (-not (Assert-Mutation 'gate-reason mutation' $runGateReason 'G4' 'G2')) { $overall = 1 }
Say ''

# ---------- 8b. let a disabled seat advertise the repair anyway ----------
# THE ROUND-3 HIGH, PUT BACK. Drop the mod-disabled term from the one local
# predicate and a seat whose compat check switched the mod off still answers
# Capable to the advertiser, so it tells the room it will repair while its own
# gate refuses. Its peers then re-resolve the victim every armed tick while this
# seat drains the stale cached one.
$mutLocalGate = New-Mutant 'localgate' @(, @(
    'internal static ProximityGateState LocalGateState(bool modDisabled, bool patchesLive)',
    '            if (modDisabled) return ProximityGateState.ModDisabled;',
    '            if (false) return ProximityGateState.ModDisabled;'))
$runLocalGate = Invoke-Suite 'mut-localgate' $mutLocalGate $repo
if (-not (Assert-Mutation 'local-capability mutation' $runLocalGate 'G6' 'G2')) { $overall = 1 }
Say ''

# ---------- 8c. never withdraw a staged advertisement ----------
# The other half of the same HIGH. Staging correctly is not enough on its own:
# the gate can stop saying Capable AFTER the key has been staged, and a seat that
# never withdraws leaves its peers repairing against a seat that will not.
$mutNoRevoke = New-Mutant 'norevoke' @(, @(
    'internal static bool ShouldRevokeCapability(ProximityGateState local, bool advertised)',
    '            return advertised && local != ProximityGateState.Capable;',
    '            return false;'))
$runNoRevoke = Invoke-Suite 'mut-norevoke' $mutNoRevoke $repo
if (-not (Assert-Mutation 'capability-withdrawal mutation' $runNoRevoke 'G7' 'G2')) { $overall = 1 }
Say ''

# ---------- 8d. repair an effect that targets its own player ----------
# V6's OWN mutant. V6 states that all four terms are required, and until now it
# had no mutation of its own - it only ever reddened alongside V3 or V4, so the
# no-mutant documentation could not honestly list it either way. Dropping the
# polarity term at the CALL SITE leaves ShouldRepair itself intact, so G1, G5 and
# D3 - which ask that function directly - stay green and V6 is the case that
# sees it.
$mutOwnPlayer = New-Mutant 'ownplayer' @(, @(
    'internal static ProximityPrefixAction VictimAction(',
    '            if (!ShouldRepair(gate, targetsOther)) return ProximityPrefixAction.RunVanillaUntouched;',
    '            if (!ShouldRepair(gate, true)) return ProximityPrefixAction.RunVanillaUntouched;'))
$runOwnPlayer = Invoke-Suite 'mut-ownplayer' $mutOwnPlayer $repo
if (-not (Assert-Mutation 'own-player-term mutation' $runOwnPlayer 'V6' 'V2')) { $overall = 1 }
Say ''

# ---------- 8e. give two outcomes of the vanilla call one reason line ----------
# Four paths through the one call into the game's own targeting used to print
# one sentence between them. The line is also the budget key, so two paths
# sharing it means the second cause can never be printed in a session at all.
$mutAnswerReason = New-Mutant 'answerreason' @(, @(
    'internal static string VanillaAnswerReason(ProximityVanillaAnswer vanilla)',
    '                case ProximityVanillaAnswer.NoHolder: return "this effect has no player of its own to target from";',
    '                case ProximityVanillaAnswer.NoHolder: return "the game''s own targeting answered with nobody";'))
$runAnswerReason = Invoke-Suite 'mut-answerreason' $mutAnswerReason $repo
if (-not (Assert-Mutations 'vanilla-outcome-reason mutation' $runAnswerReason @('D4', 'D5') 'D2')) { $overall = 1 }
Say ''

# ---------- 8f. misname ONE outcome, keeping every line distinct ----------
# THE CASE D5 COULD NOT SEE. D5's loop used to compare DeclineReason at its
# fall-through with VanillaAnswerReason - the same expression on both sides - so
# it was true for every assignment of lines to outcomes, and the swap detection
# it claimed lived entirely in three literals covering three of the six
# outcomes. NotAsked's line was pinned nowhere: this mutation gives it a new,
# still-distinct sentence, and before D5 was rebuilt against an independent
# table every single check in the suite stayed green on it. D4 is the control
# and must STAY green - the lines are still all different, which is exactly why
# D4 cannot be the case that catches this.
$mutAnswerLine = New-Mutant 'answerline' @(, @(
    'internal static string VanillaAnswerReason(ProximityVanillaAnswer vanilla)',
    '                case ProximityVanillaAnswer.NotAsked: return "the game''s own targeting was not asked";',
    '                case ProximityVanillaAnswer.NotAsked: return "the proximity ring never armed on this tick";'))
$runAnswerLine = Invoke-Suite 'mut-answerline' $mutAnswerLine $repo
if (-not (Assert-Mutation 'single-outcome-misnaming mutation' $runAnswerLine 'D5' 'D4')) { $overall = 1 }
Say ''

# ---------- 8g. SWAP TWO EXIT ASSIGNMENTS IN THE PATH PLUMBING ----------
# THE SURFACE THE TWO RUNS ABOVE COULD NOT REACH, and the reason this pair
# exists. `answerreason` and `answerline` both edit the SEAM's enum-to-sentence
# table; the code that decides which outcome a PATH gets is VanillaVictimFor in
# the patches file, and nothing in the round-4 suite touched it. A swapped
# assignment there leaves every sentence distinct and every sentence bound to
# its own enum value, so D4, D5 and BOTH advertised mutation runs stayed green
# while a missing PlayerManager would report itself as an effect with no holder.
# A mutant that cannot reach the code its case claims to close is a check that
# cannot fail (#342/#431), which is what this moves.
#
# It is a WIRING mutant because the harness cannot compile that file - it
# carries Unity, Photon and Harmony - so D6 reads its text. Two edits, because a
# swap that moves one assignment is a collapse and not a swap; each is still
# resolved inside VanillaVictimFor and still has to match exactly one site there.
#
# D4 AND D5 ARE THE CONTROLS AND MUST STAY GREEN. That is what says the surface
# actually moved rather than being duplicated: the seam is untouched here, so
# the cases that measure the seam cannot see this and the case that measures the
# path can.
$wirePathSwap = New-WireRootEdits 'pathswap' 'plugin/ProximityVictimPatches.cs' @(
    @('private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)',
      '                if (pm == null) { answer = ProximityVanillaAnswer.NoManager; return null; }',
      '                if (pm == null) { answer = ProximityVanillaAnswer.NoHolder; return null; }'),
    @('private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)',
      '                if (holder == null) { answer = ProximityVanillaAnswer.NoHolder; return null; }',
      '                if (holder == null) { answer = ProximityVanillaAnswer.NoManager; return null; }')
)
$runWirePathSwap = Invoke-Suite 'wire-pathswap' $seam $wirePathSwap
if (-not (Assert-Mutation 'path-to-outcome swap, D4 control' $runWirePathSwap 'D6' 'D4')) { $overall = 1 }
if (-not (Assert-Mutation 'path-to-outcome swap, D5 control (the sentence-table case stays green)' `
    $runWirePathSwap 'D6' 'D5')) { $overall = 1 }
Say ''

# ---------- 8h. report a thrown resolution as one that answered ----------
# The round-3 MEDIUM in its original shape, planted back at the only place that
# can produce it now. A resolution that could not complete is not a resolution
# that ran and found nobody: the second sentence sends a reader to look at who
# was standing where, for a call that never reached the ranking, and the
# sentence is also the budget key so the true cause is then unprintable for the
# session. D4 and D5 are green on it - the seam still names both outcomes
# correctly - and D6 is the case that sees the exit lying about which one it is.
$wirePathThrew = New-WireRoot 'paththrew' 'plugin/ProximityVictimPatches.cs' `
    'private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)' `
    '            catch { answer = ProximityVanillaAnswer.Threw; return null; }' `
    '            catch { answer = ProximityVanillaAnswer.Nobody; return null; }' ''
$runWirePathThrew = Invoke-Suite 'wire-paththrew' $seam $wirePathThrew
if (-not (Assert-Mutation 'thrown-resolution misreported as answered-with-nobody, D4 control' `
    $runWirePathThrew 'D6' 'D4')) { $overall = 1 }
if (-not (Assert-Mutation 'thrown-resolution misreported as answered-with-nobody, D5 control' `
    $runWirePathThrew 'D6' 'D5')) { $overall = 1 }
Say ''

# ---------- 9. collapse the outcome signals onto one budget ----------
# Drop the reason from the key, so two reasons under one outcome share a budget
# and the second is never printed. S2 is the control: the LINE still names all
# three things, so it cannot see the key change.
$mutReasonKey = New-Mutant 'reasonkey' @(, @(
    'internal static string SignalKey(string outcome, string reason)',
    '            return DiagKeyRoot + "/" + outcome + "/" + reason;',
    '            return DiagKeyRoot + "/" + outcome;'))
$runReasonKey = Invoke-Suite 'mut-reasonkey' $mutReasonKey $repo
if (-not (Assert-Mutation 'outcome-signal mutation' $runReasonKey 'S1' 'S2')) { $overall = 1 }
Say ''

# ---------- 10. key the capability cache on the frame alone ----------
$mutCapKey = New-Mutant 'capkey' @(, @(
    'internal bool Evaluate(int frame, long stamp, Func<bool> census)',
    '            if (_has && frame == _frame && stamp == _stamp) return _value;',
    '            if (_has && frame == _frame) return _value;'))
$runCapKey = Invoke-Suite 'mut-capkey' $mutCapKey $repo
if (-not (Assert-Mutation 'capability-cache-key mutation' $runCapKey 'C1' 'C2')) { $overall = 1 }
Say ''

# ---------- 11. stop clearing the fighter capability on spectator staging ----
$mutKeys = New-Mutant 'fighterkeys' @(, @(
    'internal static class ProximityVictim',
    '        internal static readonly string[] FighterCapabilityKeys = new string[] { CapabilityProp };',
    '        internal static readonly string[] FighterCapabilityKeys = new string[0];'))
$runKeys = Invoke-Suite 'mut-fighterkeys' $mutKeys $repo
if (-not (Assert-Mutation 'fighter-capability-keys mutation' $runKeys 'K1' 'K2')) { $overall = 1 }
Say ''

# ---------- 12. make the prefix fold keep the last answer ----------
# HarmonyX ANDs every prefix's return into __runOriginal whichever order it
# called them in - read from the shipped 0Harmony.dll and cited on
# RunOriginalAfter. Fold only the last answer instead and the two orders
# disagree wherever the two SHIPPED prefixes disagree, which is what P3
# composes. P1 is the control: it does not use the fold at all.
$mutChain = New-Mutant 'chainlast' @(, @(
    'internal static bool RunOriginalAfter(bool runSoFar, bool prefixReturn)',
    '            return runSoFar && prefixReturn;',
    '            return prefixReturn;'))
$runChain = Invoke-Suite 'mut-chainlast' $mutChain $repo
# P5 too: the conjunction is what carries the bound on StunPlayer.Go, so a fold
# that keeps only the last answer must be visible to the case that says so.
if (-not (Assert-Mutations 'prefix-fold mutation' $runChain @('P3', 'P5') 'P1')) { $overall = 1 }
Say ''

# ---------- 13. open the sibling null guard ----------
# Moving PerfPatches.StunPlayerGoNullGuard's decision into the seam is a
# refactor and must not change what it decides. P4 is what says so; without a
# mutant it would be a restatement of the code beneath it.
$mutGuard = New-Mutant 'guardopen' @(, @(
    'internal static ProximityPrefixAction NullGuardAction(',
    '            return ProximityPrefixAction.SkipOriginal;',
    '            return ProximityPrefixAction.RunVanillaUntouched;'))
$runGuard = Invoke-Suite 'mut-guardopen' $mutGuard $repo
# P5's second half is that the two shipped prefixes CAN disagree. Open the guard
# and they never do, which would make scoping the bound to a conjunction an
# argument about nothing - so P5 must redden here as well as P4.
if (-not (Assert-Mutations 'null-guard mutation' $runGuard @('P4', 'P5') 'P1')) { $overall = 1 }
Say ''

# ---------- 14-21. the wiring: the halves this harness cannot compile --------
# Each of these changes one shipped line inside one named member of a COPY of
# the tree and points the suite at the copy.

$wireSpec = New-WireRoot 'spec' 'plugin/SpectatorSession.cs' `
    'internal static bool StagePreJoinProperties(string localSteamId)' `
    '                foreach (var capabilityKey in ProximityVictim.FighterCapabilityKeys)' `
    '                foreach (var capabilityKey in new string[0])' ''
$runWireSpec = Invoke-Suite 'wire-spec' $seam $wireSpec
if (-not (Assert-Mutation 'spectator-clearing wiring' $runWireSpec 'W1' 'W5')) { $overall = 1 }
Say ''

$wireProp = New-WireRoot 'prop' 'plugin/Plugin.cs' `
    'public void OnPlayerPropertiesUpdate(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changedProps)' `
    '                    || changedProps.ContainsKey(ProximityVictim.CapabilityProp))' `
    '                    || false)' ''
$runWireProp = Invoke-Suite 'wire-prop' $seam $wireProp
if (-not (Assert-Mutation 'capability-delivery wiring' $runWireProp 'W2' 'W5')) { $overall = 1 }
Say ''

$wireGen = New-WireRoot 'gen' 'plugin/RoomActors.cs' `
    'private static void EnsureCacheRoom()' `
    '                _rosterGeneration++;' `
    '                // (mutant) a room change no longer moves the generation' ''
$runWireGen = Invoke-Suite 'wire-gen' $seam $wireGen
if (-not (Assert-Mutation 'room-change wiring' $runWireGen 'W3' 'W5')) { $overall = 1 }
Say ''

$wireDoc = New-WireRoot 'doc' 'plugin/ProximityVictimPatches.cs' `
    'internal static PlayerInRangeTrigger OwningTrigger(Transform start)' `
    '            // This is the ONLY thing the walk is asked. The repair does not read' `
    '            // (mutant) this block has drifted off the member it describes' ''
$runWireDoc = Invoke-Suite 'wire-doc' $seam $wireDoc
if (-not (Assert-Mutation 'no-ring-reasoning wiring' $runWireDoc 'W8' 'W1')) { $overall = 1 }
Say ''

$wireMsb = New-WireRoot 'msb' 'plugin/CompetitiveRounds.csproj' `
    '<MusicPreviewsToCopy Include="music\*_preview.ogg" />' `
    '    <MusicManifestToCopy Include="music\manifest.json" Condition="Exists(''music\manifest.json'')" />' `
    '    <MusicManifestToCopy Include="music\manifest.json" />' `
    '</ItemGroup>'
$runWireMsb = Invoke-Suite 'wire-msb' $seam $wireMsb
if (-not (Assert-Mutation 'music-manifest-condition wiring' $runWireMsb 'W10' 'W1')) { $overall = 1 }
Say ''

$wirePerf = New-WireRoot 'perf' 'plugin/PerfPatches.cs' `
    'static bool Prefix(StunPlayer __instance)' `
    '            return ProximityVictim.PrefixReturn(action);' `
    '            return action != ProximityPrefixAction.SkipOriginal;' ''
$runWirePerf = Invoke-Suite 'wire-perf' $seam $wirePerf
if (-not (Assert-Mutation 'sibling-prefix-shape wiring' $runWirePerf 'W11' 'W1')) { $overall = 1 }
Say ''

$wireSiteKey = New-WireRoot 'sitekey' 'plugin/ProximityVictimPatches.cs' `
    'internal static void NoteOutcome(string site, string outcome, string why)' `
    '                ProximityVictim.SignalKey(outcome, why),' `
    '                ProximityVictim.SignalKey(site + "/" + outcome, why),' ''
$runWireSiteKey = Invoke-Suite 'wire-sitekey' $seam $wireSiteKey
if (-not (Assert-Mutation 'per-site-budget wiring' $runWireSiteKey 'S4' 'W1')) { $overall = 1 }
Say ''

# Plant a proximity comparison of our own back into the repair. This is the
# negative control for the round's acceptance assertion: without it "no ranking
# here" is a statement no run has ever seen fail.
$wireRank = New-WireRoot 'rank' 'plugin/ProximityVictimPatches.cs' `
    'private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)' `
    '                if (victim == null) { answer = ProximityVanillaAnswer.Nobody; return null; }' `
    '                if (victim == null || Vector2.Distance(holder.transform.position, victim.transform.position) > 99f) { answer = ProximityVanillaAnswer.Nobody; return null; }' ''
$runWireRank = Invoke-Suite 'wire-rank' $seam $wireRank
if (-not (Assert-Mutation 'authored-ranking wiring' $runWireRank 'N1' 'W1')) { $overall = 1 }
Say ''

# Plant a roster read of our own back into the repair.
$wireRoster = New-WireRoot 'roster' 'plugin/ProximityVictimPatches.cs' `
    'private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)' `
    '                if (pm == null) { answer = ProximityVanillaAnswer.NoManager; return null; }' `
    '                if (pm == null || pm.players == null) { answer = ProximityVanillaAnswer.NoManager; return null; }' ''
$runWireRoster = Invoke-Suite 'wire-roster' $seam $wireRoster
if (-not (Assert-Mutation 'authored-roster wiring' $runWireRoster 'N2' 'W1')) { $overall = 1 }
Say ''

# Plant a SECOND copy of the local conjunction into the gate. The pure half of
# the round-3 HIGH is G6's; this is the half no case can execute. A member that
# asks the one predicate AND re-derives the conjunction beside it is exactly the
# shape the finding described, and a required-anchor check alone would stay green
# on it.
$wireAdvertise = New-WireRoot 'advertise' 'plugin/ProximityVictimPatches.cs' `
    'internal static ProximityGateState GateState()' `
    '                ProximityGateState local = LocalCapability();' `
    '                ProximityGateState local = Plugin.modDisabled ? ProximityGateState.ModDisabled : LocalCapability();' ''
$runWireAdvertise = Invoke-Suite 'wire-advertise' $seam $wireAdvertise
if (-not (Assert-Mutations 'second-copy-of-the-local-answer wiring' $runWireAdvertise @('W14b', 'W15b') 'W1')) { $overall = 1 }
Say ''

# Plant a SECOND read of the OTHER global, outside every member the suite bounds.
# "One predicate, no second copy" was claimed for both globals and guarded
# file-wide for only one: W14b counted the mod-disabled flag, while PatchesLive
# was forbidden only inside StageInto, GateState and RepublishCapability. A read
# in Census - a member none of those three name - re-creates the two-expressions
# shape with the harness reporting the property intact. W14c is the bound that
# was missing; this is what proves it can fail.
$wirePatchesLive = New-WireRoot 'patcheslive' 'plugin/ProximityVictimPatches.cs' `
    'private static bool Census()' `
    '            PhotonPlayer[] actors = PhotonNetwork.PlayerList;' `
    '            PhotonPlayer[] actors = PatchesLive ? PhotonNetwork.PlayerList : null;' ''
$runWirePatchesLive = Invoke-Suite 'wire-patcheslive' $seam $wirePatchesLive
if (-not (Assert-Mutation 'second-copy-of-the-attachment-answer wiring' $runWirePatchesLive 'W14c' 'W1')) { $overall = 1 }
Say ''

# Put the compat site's overstated claim back. "A pre-join stage may already
# have advertised it" is false on a first initialisation: this key is staged
# pre-join from the queue poll, which cannot run before ApiClient.Initialize,
# and the compat-fail branch returns above that call. A tester pointed at that
# route to validate the withdrawal waits for a line it cannot produce.
$wireCompatClaim = New-WireRoot 'compatclaim' 'plugin/Plugin.cs' `
    'private void DoInitialize()' `
    '                        // staged PRE-JOIN from the queue poll, which cannot run' `
    '                        // A pre-join stage may already have advertised it, and' ''
$runWireCompatClaim = Invoke-Suite 'wire-compatclaim' $seam $wireCompatClaim
if (-not (Assert-Mutation 'compat-site-claim wiring' $runWireCompatClaim 'W17' 'W1')) { $overall = 1 }
Say ''

# Move the attachment-shortfall message and leave the comment quoting the old
# one. That is the state round 4 shipped into: the doc told the maintainer to
# grep for "patches did NOT attach (2/3)" after round 4 had replaced it, so the
# grep returns nothing and the absence reads as a complete attachment count for
# a repair that has gone inert on every seat. W19 binds the quote to the
# expression that builds it.
$wireLogQuote = New-WireRoot 'logquote' 'plugin/ProximityVictimPatches.cs' `
    'internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)' `
    '                        + RequiredAttachments + " patches live); this seat stays on vanilla for the session");' `
    '                        + RequiredAttachments + " patches did NOT attach); this seat stays on vanilla");' ''
$runWireLogQuote = Invoke-Suite 'wire-logquote' $seam $wireLogQuote
if (-not (Assert-Mutation 'quoted-log-line wiring' $runWireLogQuote 'W19' 'W1')) { $overall = 1 }
# W23's INERT TWIN. This run edits StageInto - the same member W23 bounds - on a
# line W23 makes no claim about, so W23 must stay green here while it reddens
# under wire-stagelatch. Without this row "W23 reddens when the advertising
# branch is latched" and "W23 reddens whenever anything in StageInto moves" look
# the same from the log.
if (-not (Assert-Mutation 'quoted-log-line wiring, W23 inert twin' $runWireLogQuote 'W19' 'W23')) { $overall = 1 }
Say ''

# ---------- latch the ADVERTISEMENT on the shortfall flag ----------
# Put the mechanism two comments claimed into the code that never had it. The
# field's own doc said "once we have declined to advertise, we never advertise
# later in the session", and the withdrawal's doc carried that latch as a
# PREMISE for why no advertising direction is needed. What the flag actually
# does is suppress a second LogError on the branch that has already declined; a
# seat whose third patch attaches after a declined attempt is Capable and its
# next pre-join merge stages the key, which is the design. This is the shape the
# comments described, so W23 has to be able to fail on it (#351/#434).
$wireStageLatch = New-WireRoot 'stagelatch' 'plugin/ProximityVictimPatches.cs' `
    'internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)' `
    '                if (local == ProximityGateState.Capable && !_withdrawn)' `
    '                if (local == ProximityGateState.Capable && !_withdrawn && !_stageFailedPermanently)' ''
$runWireStageLatch = Invoke-Suite 'wire-stagelatch' $seam $wireStageLatch
if (-not (Assert-Mutation 'advertisement-latched-on-the-shortfall-flag wiring' $runWireStageLatch 'W23' 'W1')) { $overall = 1 }
Say ''

# ---------- put the deleted compat claim back in the HARNESS'S own text ----------
# The round-4 pass deleted "the one transition that exists today" from the
# patches file and "A pre-join stage may already have advertised it" from the
# compat site, and left the same claim standing in this suite's own comment -
# outside every file W17 read. So the document certifying the deletion was still
# making the claim, and a tester reading it would still wait for a line a plain
# compat disable cannot produce. W17's surface now includes this file; this is
# what proves that half can fail.
#
# THE ANCHOR IS DELIBERATELY A LINE THAT EXISTS IN BOTH THE CURRENT HARNESS AND
# THE PREVIOUS TIP'S. The blindness run re-executes these mutants against the
# harness as it stood at the previous tip, and an anchor that only this round's
# file carries would abort that whole run at this line instead of producing the
# FAILED row it exists to produce (#342: a control that cannot be executed
# reports nothing about anything).
$wireCompatHarness = New-WireRoot 'compatharness' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '        // W16 - the withdrawal can only withdraw. The capable value reaches a peer' `
    '        // W16 - the withdrawal can only withdraw, and the compat site is the one transition that exists today. The capable value reaches a peer' ''
$runWireCompatHarness = Invoke-Suite 'wire-compatharness' $seam $wireCompatHarness
if (-not (Assert-Mutation 'deleted-compat-claim-in-the-harness wiring' $runWireCompatHarness 'W17' 'W1')) { $overall = 1 }
Say ''

# Read the property write as if failure could only arrive as an exception.
# Player.SetCustomProperties returns a bool and a refused op comes back false
# having sent nothing, cached nothing and thrown nothing. Ignoring it clears
# _advertised and latches _withdrawn on a withdrawal that never left the
# process: the per-tick driver and StageInto then refuse for the rest of the
# session while cr_prox1 stays set on every peer.
$wireBlindWrite = New-WireRoot 'blindwrite' 'plugin/ProximityVictimPatches.cs' `
    'internal static void RepublishCapability()' `
    '                if (!sent)' `
    '                if (false)' ''
$runWireBlindWrite = Invoke-Suite 'wire-blindwrite' $seam $wireBlindWrite
if (-not (Assert-Mutation 'unchecked-property-write wiring' $runWireBlindWrite 'W20' 'W1')) { $overall = 1 }
Say ''

# Put the refuted monotonicity paragraph back. "The attachment count only ever
# increments, so the local answer moves from Capable to not-Capable and never
# back" is refuted by its own second premise, and G6 executes the refutation.
# The paragraph nominated itself as the place reversibility has to be answered,
# so it is the one site a later reader would check.
$wireMonotone = New-WireRoot 'monotone' 'plugin/ProximityVictimSeam.cs' `
    'internal static class ProximityVictim' `
    '        /// THE LOCAL ANSWER IS NOT MONOTONIC, AND THIS FUNCTION DOES NOT REST ON' `
    '        /// increments, so the local answer moves from Capable to not-Capable and' ''
$runWireMonotone = Invoke-Suite 'wire-monotone' $seam $wireMonotone
if (-not (Assert-Mutation 'monotonicity-claim wiring' $runWireMonotone 'W21' 'W1')) { $overall = 1 }
Say ''

# Put the refuted key argument back. The claim that a round-2 seat and a round-3
# seat resolve the same player is false - round 2 ranked with a selector of its
# own and deferred on an Any-target ring - and it was the stated reason for not
# rotating cr_prox1. K3 is the case that holds the seam to the fact that
# replaced it; without a mutant it would be a restatement of the comment.
$wireKeyClaim = New-WireRoot 'keyclaim' 'plugin/ProximityVictimSeam.cs' `
    'internal static class ProximityVictim' `
    '        /// released build advertises it at all. The key is absent from the base' `
    '        /// comparing like with like. The key is absent from the base' ''
$runWireKeyClaim = Invoke-Suite 'wire-keyclaim' $seam $wireKeyClaim
if (-not (Assert-Mutation 'key-non-rotation-claim wiring' $runWireKeyClaim 'K3' 'W1')) { $overall = 1 }
Say ''

# Put the unscoped composition bound back. "Under ANY composition the worst a
# foreign fold could do is fail to run them" is true of the two methods this
# repair patches alone and false of StunPlayer.Go, which also carries the perf
# null guard. W13 is the case that holds the prose to what P5 measured.
$wireBoundClaim = New-WireRoot 'boundclaim' 'plugin/ProximityVictimSeam.cs' `
    'internal static class ProximityVictim' `
    '        /// StunPlayer.Go is NOT covered by that bound, and the wording this' `
    '        /// under ANY composition nothing here needs scoping, and the wording this' ''
$runWireBoundClaim = Invoke-Suite 'wire-boundclaim' $seam $wireBoundClaim
if (-not (Assert-Mutation 'composition-bound-claim wiring' $runWireBoundClaim 'W13' 'W1')) { $overall = 1 }
Say ''

# ---------- 22. the prior mechanism ----------
# The round-2 files, recovered from git. Every N case asserts something round 3
# DELETED, so every one of them must redden here; W1 reads a file the change
# never touched and must stay green, which is what stops this run from passing
# for the trivial reason that the root is wrong.
$priorRoot = New-PriorRoot 'r2' $priorTip
$runPrior = Invoke-Suite 'prior-r2' $seam $priorRoot
if (-not (Assert-Mutations 'round-2 mechanism' $runPrior `
    @('N1', 'N2', 'N3', 'N4', 'N5', 'N6a', 'N6b', 'N6c') 'W1')) { $overall = 1 }
Say ''

if ($overall -eq 0) { Say 'BUG 389 SEAM SUITE: ALL CHECKS PASSED' }
else { Say 'BUG 389 SEAM SUITE: FAILURES PRESENT' }
exit $overall
