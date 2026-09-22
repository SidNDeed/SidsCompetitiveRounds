# Can the rebuild-provenance binder actually refuse?
#
# WHY THIS EXISTS
# ---------------
# build-and-bind-artifact.ps1 replaced a guard that COUNTED ARGUMENTS with one
# that must PROVE two distinct build invocations. A replacement is a claim until
# something shows it reddening on the exact situations it names, beside a change
# of the same shape that must stay green - otherwise a red only proves that
# something moved (#391).
#
# So every rule the binder states is exercised here against a SYNTHETIC build
# log and synthetic captures whose write times this script sets itself. The
# controls measure the CHECKER; the real r4 build log measures the build. Two
# real rebuilds going green is demonstrated by that real log; what cannot be
# demonstrated there is a refusal, because a refusal would mean the round had no
# artifact - which is exactly why the refusals live here.
#
# EACH RED HAS AN INERT TWIN AT THE SAME SITE. The twin edits the same field of
# the same line, by the same kind of edit, in a way that must stay GREEN. The
# most important pair is the copy pair: rebuild 2 pointed at a copy of rebuild
# 1's output REDS, while rebuild 2 pointed at a byte-identical artifact carrying
# its own build's write time stays GREEN. Identical bytes are the expected
# outcome of a deterministic build; what must be proven is the second
# invocation, and that pair is what says the binder measures the invocation and
# not the bytes.
#
# WHICH WAY THE UNHANDLED CASE FAILS (#276 / #430). A control whose target text
# is not in the baseline, an edit that changes no bytes, or a baseline that is
# not itself green, are each VOID with exit 3 rather than a pass: a control that
# measured nothing has not passed. A filter must never discard the line it
# measures (#441), so every refusal the binder printed is echoed here, indented.

param(
    [string]$Root = (Resolve-Path -LiteralPath (Join-Path (Join-Path $PSScriptRoot '..') '..')).Path,
    [string]$Binder = '',
    [string]$Donor = '',
    [string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) 'scr-r4-artifact-bind-controls')
)

$ErrorActionPreference = 'Stop'

if ($Binder -eq '') { $Binder = Join-Path $PSScriptRoot 'build-and-bind-artifact.ps1' }
if ($Donor -eq '') { $Donor = Join-Path $PSScriptRoot 'bin/Release/net10.0/roster-census-harness.dll' }

$buildCommand = 'dotnet build plugin/CompetitiveRounds.csproj -c Release -t:Rebuild -p:SkipCopyToPlugins=true'

Write-Output '=== roster-census artifact-bind controls ==='
Write-Output ('invocation:     ' + [Environment]::CommandLine)
Write-Output ('invocation-utc: ' + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ('binder:         ' + $Binder)
Write-Output ''

if (-not (Test-Path -LiteralPath $Binder)) {
    Write-Output ('VOID | the binder under test is not at ' + $Binder)
    Write-Output 'ARTIFACT-BIND CONTROLS VOID'
    exit 3
}
if (-not (Test-Path -LiteralPath $Donor)) {
    Write-Output ('VOID | no donor assembly to stand in for a rebuild artifact at ' + $Donor)
    Write-Output 'ARTIFACT-BIND CONTROLS VOID'
    exit 3
}

# The synthetic captures must be real managed assemblies, because the binder
# reads an InformationalVersion off the last one. The donor's own product
# version is used as the head, so the binding half of the baseline is green for
# a reason this script can state rather than assume.
$head = ''
try { $head = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($Donor).ProductVersion } catch { $head = '' }
if ([string]::IsNullOrWhiteSpace($head)) {
    Write-Output 'VOID | the donor assembly carries no ProductVersion, so no baseline binding can be established'
    Write-Output 'ARTIFACT-BIND CONTROLS VOID'
    exit 3
}
Write-Output ('donor ProductVersion (used as the synthetic head): ' + $head)

if (Test-Path -LiteralPath $WorkDir) { Remove-Item -LiteralPath $WorkDir -Recurse -Force }
[void](New-Item -ItemType Directory -Path $WorkDir -Force)

function Utc { param([datetime]$W) return $W.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }

$t0 = (Get-Date).ToUniversalTime()
$start1 = $t0.AddSeconds(-200); $end1 = $t0.AddSeconds(-180); $wrote1 = $t0.AddSeconds(-190)
$start2 = $t0.AddSeconds(-160); $end2 = $t0.AddSeconds(-140); $wrote2 = $t0.AddSeconds(-150)

function New-Capture {
    param([string]$Name, [datetime]$WriteUtc)
    $p = Join-Path $WorkDir $Name
    Copy-Item -LiteralPath $Donor -Destination $p -Force
    $item = Get-Item -LiteralPath $p
    $item.LastWriteTimeUtc = $WriteUtc
    return $p
}

# rebuild 1's artifact, rebuild 2's artifact, a third distinct artifact carrying
# rebuild 2's write time, a byte-copy of rebuild 1 (rebuild 1's write time), and
# a second-invocation artifact whose bytes are identical to rebuild 1's.
$cap1  = New-Capture 'CompetitiveRounds.rebuild1.dll' $wrote1
$cap2  = New-Capture 'CompetitiveRounds.rebuild2.dll' $wrote2
$cap3  = New-Capture 'CompetitiveRounds.rebuild2-alt.dll' $wrote2
$copy1 = New-Capture 'CompetitiveRounds.copy-of-rebuild1.dll' $wrote1
$twin2 = New-Capture 'CompetitiveRounds.rebuild2-identical-bytes.dll' $wrote2

$bytes = (Get-Item -LiteralPath $cap1).Length
$id1 = '1111111111111111111111111111aaaa'
$id2 = '2222222222222222222222222222bbbb'

$baseline = @(
    '=== bug 391 CLIENT lane - SYNTHETIC build log for the artifact-bind controls ===',
    'This file is written by run-artifact-bind-controls.ps1 and exists for no other',
    'purpose than to be mutated (#306).',
    '',
    ('--- invocation (rebuild 1 of 2) ---'),
    ('$ ' + $buildCommand),
    '',
    '  Determining projects to restore...',
    '  CompetitiveRounds -> (synthetic output path)',
    '',
    'Build succeeded.',
    '    10 Warning(s)',
    '    0 Error(s)',
    '',
    'exit=0',
    ("provenance(1): buildId={0} startUtc={1} endUtc={2} exit=0 output=(synthetic) capture={3} captureBytes={4} captureWriteUtc={5}" -f `
        $id1, (Utc $start1), (Utc $end1), $cap1, $bytes, (Utc $wrote1)),
    '',
    ('--- invocation (rebuild 2 of 2) ---'),
    ('$ ' + $buildCommand),
    '',
    '  Determining projects to restore...',
    '  CompetitiveRounds -> (synthetic output path)',
    '',
    'Build succeeded.',
    '    10 Warning(s)',
    '    0 Error(s)',
    '',
    'exit=0',
    ("provenance(2): buildId={0} startUtc={1} endUtc={2} exit=0 output=(synthetic) capture={3} captureBytes={4} captureWriteUtc={5}" -f `
        $id2, (Utc $start2), (Utc $end2), $cap2, $bytes, (Utc $wrote2))
)

$basePath = Join-Path $WorkDir 'baseline-build.log'
[System.IO.File]::WriteAllLines($basePath, $baseline)

$psExe = (Get-Process -Id $PID).Path

function Invoke-Binder {
    param([string]$LogPath)
    $out = & $psExe -NoProfile -ExecutionPolicy Bypass -File $Binder -Mode Verify -BuildLog $LogPath -Head $head 2>&1
    $code = $LASTEXITCODE
    return [pscustomobject]@{ Code = $code; Lines = @($out | ForEach-Object { [string]$_ }) }
}

Write-Output ''
Write-Output '--- the synthetic baseline: two distinct invocations, two distinct captures ---'
Write-Output ('     $ ' + $psExe + ' -NoProfile -ExecutionPolicy Bypass -File ' + $Binder + ' -Mode Verify -BuildLog ' + $basePath + ' -Head ' + $head)
$base = Invoke-Binder -LogPath $basePath
foreach ($l in $base.Lines) { Write-Output ('     | ' + $l) }
if ($base.Code -ne 0) {
    Write-Output 'VOID | the synthetic baseline does not bind - every pair below would measure nothing'
    Write-Output 'ARTIFACT-BIND CONTROLS VOID'
    exit 3
}
Write-Output ('ok   | baseline | the binder returns 0 over two proven-distinct invocations')

# ---- the pairs --------------------------------------------------------------

$controls = @(
    @{ Name = 'A1-names-the-same-capture-path-for-both-rebuilds'; Expect = 'REFUSE'
       From = 'capture=' + $cap2; To = 'capture=' + $cap1
       Why = 'the MEDIUM: one artifact presented twice is one measurement written twice, not repeatability' },
    @{ Name = 'A1-twin-repoints-the-same-field-at-a-distinct-artifact'; Expect = 'BIND'
       From = 'capture=' + $cap2; To = 'capture=' + $cap3
       Why = 'inert twin: the same field rewritten, still naming an artifact of its own with its own write time' },

    @{ Name = 'A2-substitutes-a-copy-of-rebuild-1s-output-for-rebuild-2s'; Expect = 'REFUSE'
       From = 'capture=' + $cap2; To = 'capture=' + $copy1
       Why = 'one build plus a copy: the copy carries rebuild 1s write time, which is outside rebuild 2s window' },
    @{ Name = 'A2-twin-substitutes-a-byte-identical-artifact-from-the-second-invocation'; Expect = 'BIND'
       From = 'capture=' + $cap2; To = 'capture=' + $twin2
       Why = 'inert twin: identical BYTES are the expected outcome of a deterministic build; the invocation is what must be distinct' },

    @{ Name = 'A3-removes-rebuild-2s-provenance-line'; Expect = 'REFUSE'
       From = 'provenance(2): buildId=' + $id2; To = '(rebuild 2 completed)'
       Why = 'absent distinct-invocation evidence is a refusal, never a skipped row' },
    @{ Name = 'A3-twin-adds-an-unrecognised-field-to-the-same-provenance-line'; Expect = 'BIND'
       From = 'provenance(2): buildId=' + $id2; To = 'provenance(2): recapture=no buildId=' + $id2
       Why = 'inert twin: the same record with a field the reader does not know; the required fields are all still there' },

    @{ Name = 'A4-records-the-same-buildId-for-both-rebuilds'; Expect = 'REFUSE'
       From = 'buildId=' + $id2; To = 'buildId=' + $id1
       Why = 'one invocation counted twice must red even when two captures exist' },
    @{ Name = 'A4-twin-rewrites-the-same-buildId-field-as-another-distinct-value'; Expect = 'BIND'
       From = 'buildId=' + $id2; To = 'buildId=3333333333333333333333333333cccc'
       Why = 'inert twin: the same field, a different value, still distinct from rebuild 1s' },

    @{ Name = 'A5-removes-the-second-rebuild-section-header'; Expect = 'REFUSE'
       From = '--- invocation (rebuild 2 of 2) ---'; To = '(rebuild 2 header removed)'
       Why = 'fewer than two rebuild sections cannot demonstrate repeatability whatever else the log says' },
    @{ Name = 'A5-twin-removes-a-line-that-carries-no-evidence-from-the-same-section'; Expect = 'BIND'
       From = '  Determining projects to restore...'; To = ''; Occurrence = 2
       Why = 'inert twin: a deletion of the same kind inside the same section, of a line nothing binds' },

    @{ Name = 'A6-overlaps-the-two-build-windows'; Expect = 'REFUSE'
       From = 'startUtc=' + (Utc $start2); To = 'startUtc=' + (Utc $t0.AddSeconds(-185))
       Why = 'overlapping windows identify no single invocation, so neither capture can be tied to one' },
    @{ Name = 'A6-twin-moves-the-same-window-start-later-without-overlapping'; Expect = 'BIND'
       From = 'startUtc=' + (Utc $start2); To = 'startUtc=' + (Utc $t0.AddSeconds(-165))
       Why = 'inert twin: the same field moved by the same kind of edit, the windows still disjoint' },

    @{ Name = 'A7-claims-a-capture-size-that-is-not-the-file-on-disk'; Expect = 'REFUSE'
       From = 'captureBytes=' + $bytes + ' captureWriteUtc=' + (Utc $wrote2)
       To = 'captureBytes=' + ($bytes + 1) + ' captureWriteUtc=' + (Utc $wrote2)
       Why = 'a record that no longer describes the file on disk is evidence about neither' },
    @{ Name = 'A7-twin-rewrites-the-same-size-field-with-a-leading-zero'; Expect = 'BIND'
       From = 'captureBytes=' + $bytes + ' captureWriteUtc=' + (Utc $wrote2)
       To = 'captureBytes=0' + $bytes + ' captureWriteUtc=' + (Utc $wrote2)
       Why = 'inert twin: the same field, the same value, spelled differently' }
)

$failures = 0
$n = 0
foreach ($c in $controls) {
    $n++
    $text = [System.IO.File]::ReadAllText($basePath)
    $occurrence = 1
    if ($c.ContainsKey('Occurrence')) { $occurrence = [int]$c.Occurrence }

    $at = -1
    $from = 0
    for ($k = 0; $k -lt $occurrence; $k++) {
        $at = $text.IndexOf($c.From, $from, [System.StringComparison]::Ordinal)
        if ($at -lt 0) { break }
        $from = $at + 1
    }
    if ($at -lt 0) {
        Write-Output ('VOID | control={0} | occurrence {1} of its target text is not in the baseline - the control would measure nothing' -f $c.Name, $occurrence)
        Write-Output 'ARTIFACT-BIND CONTROLS VOID'
        exit 3
    }
    $mutated = $text.Substring(0, $at) + $c.To + $text.Substring($at + $c.From.Length)
    if ([string]::Equals($mutated, $text, [System.StringComparison]::Ordinal)) {
        Write-Output ('VOID | control={0} | the edit changed no bytes' -f $c.Name)
        Write-Output 'ARTIFACT-BIND CONTROLS VOID'
        exit 3
    }

    $p = Join-Path $WorkDir ('case{0}-build.log' -f $n)
    [System.IO.File]::WriteAllText($p, $mutated)

    Write-Output ''
    Write-Output ('     $ ' + $psExe + ' -NoProfile -ExecutionPolicy Bypass -File ' + $Binder + ' -Mode Verify -BuildLog ' + $p + ' -Head ' + $head)
    $r = Invoke-Binder -LogPath $p
    $got = if ($r.Code -eq 0) { 'BIND' } else { 'REFUSE' }
    $ok = ($got -eq $c.Expect)
    if (-not $ok) { $failures++ }

    Write-Output ('{0,-4} | control={1,-72} | expected={2,-6} got={3,-6} exit={4} | {5}' -f `
        $(if ($ok) { 'ok' } else { 'BAD' }), $c.Name, $c.Expect, $got, $r.Code, $c.Why)
    Write-Output ('     | edited: ' + $c.From + '   ->   ' + $c.To)
    foreach ($l in $r.Lines) {
        if ($l -like 'REFUSED*' -or $l -like '        | observed:*') { Write-Output ('     | ' + $l) }
    }
    if ($c.Expect -eq 'BIND') {
        foreach ($l in $r.Lines) { if ($l -like 'MATCH*' -or $l -like 'BOUND*') { Write-Output ('     | ' + $l) } }
    }
}

Write-Output ''
Write-Output ('controls=' + $controls.Count + ' reds=' + @($controls | Where-Object { $_.Expect -eq 'REFUSE' }).Count `
    + ' twins=' + @($controls | Where-Object { $_.Expect -eq 'BIND' }).Count + ' failures=' + $failures)

if ($failures -gt 0) {
    Write-Output 'ARTIFACT-BIND CONTROLS FAIL'
    exit 1
}
Write-Output 'ARTIFACT-BIND CONTROLS PASS'
exit 0
