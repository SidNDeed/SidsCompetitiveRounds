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
#
# WHAT CHANGED AFTER THE ROUND-4 LENS
# -----------------------------------
# This baseline used to write `output=(synthetic)` into both provenance lines -
# a value that is not a path at all - and it bound. That was not a flaw in the
# baseline; it was the demonstration that `output` was stated and never read.
# The binder now declares a FIELD LEDGER (P2c), requires the recorded output to
# RESOLVE to the artifact the run was asked to bind (P2d), and hashes that
# artifact against the last proven capture (P8). So the baseline names a real
# synthetic artifact, the run is pointed at it with -Root and -Output, and four
# new pairs exercise the three new rules.
#
# Two of those pairs cannot be expressed as an edit to the log, because what
# they move is the ARTIFACT rather than the record. A control may therefore
# carry OutputBytes, written to the artifact before the binder runs; the
# canonical bytes are restored before EVERY control, so each pair measures only
# its own change. A control may also carry no text edit at all, and the line
# printed beside it says so rather than implying an edit that did not happen.

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

function Utc { param([datetime]$W) return $W.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ') }

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

# The artifact the synthetic rebuilds claim to have produced. The binder is
# pointed at it by -Root and -Output, so the baseline states a real subject
# instead of the unread placeholder this file used to carry.
$outName  = 'synthetic-output.dll'
$outFile  = Join-Path $WorkDir $outName
Copy-Item -LiteralPath $Donor -Destination $outFile -Force
$canonicalBytes = [System.IO.File]::ReadAllBytes($outFile)
$outRecorded = [System.IO.Path]::GetFullPath($outFile)

# A second real artifact, for the pair that repoints the recorded output at a
# path that is not the one under test.
$otherOut = Join-Path $WorkDir 'another-output.dll'
Copy-Item -LiteralPath $Donor -Destination $otherOut -Force

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
    ("provenance(1): buildId={0} startUtc={1} endUtc={2} exit=0 output={6} capture={3} captureBytes={4} captureWriteUtc={5}" -f `
        $id1, (Utc $start1), (Utc $end1), $cap1, $bytes, (Utc $wrote1), $outRecorded),
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
    ("provenance(2): buildId={0} startUtc={1} endUtc={2} exit=0 output={6} capture={3} captureBytes={4} captureWriteUtc={5}" -f `
        $id2, (Utc $start2), (Utc $end2), $cap2, $bytes, (Utc $wrote2), $outRecorded)
)

$basePath = Join-Path $WorkDir 'baseline-build.log'
[System.IO.File]::WriteAllLines($basePath, $baseline)

$psExe = (Get-Process -Id $PID).Path

function Invoke-Binder {
    param([string]$LogPath)
    $out = & $psExe -NoProfile -ExecutionPolicy Bypass -File $Binder -Mode Verify -BuildLog $LogPath `
        -Root $WorkDir -Output $outName -Head $head 2>&1
    $code = $LASTEXITCODE
    return [pscustomobject]@{ Code = $code; Lines = @($out | ForEach-Object { [string]$_ }) }
}

function Reset-Artifact {
    [System.IO.File]::WriteAllBytes($outFile, $canonicalBytes)
}

Write-Output ''
Write-Output '--- the synthetic baseline: two distinct invocations, two distinct captures ---'
Write-Output ('     $ ' + $psExe + ' -NoProfile -ExecutionPolicy Bypass -File ' + $Binder + ' -Mode Verify -BuildLog ' + $basePath + ' -Root ' + $WorkDir + ' -Output ' + $outName + ' -Head ' + $head)
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
    @{ Name = 'A3-twin-replaces-a-line-nothing-binds-in-the-same-section'; Expect = 'BIND'
       From = 'Build succeeded.'; To = '(rebuild 2 completed)'; Occurrence = 2
       Why = 'inert twin: a replacement of the same kind in the same section, of a line no rule reads' },

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
       Why = 'inert twin: the same field, the same value, spelled differently' },

    # ---- the round-4 lens: the subject of the evidence, P2c, P2d and P8 ------
    # O1 and O2 are the same rule read from both ends: a section that names a
    # different artifact, and a section that names the value this baseline used
    # to carry when nothing read the field at all.
    @{ Name = 'O1-repoints-rebuild-2s-output-at-a-different-artifact'; Expect = 'REFUSE'
       From = 'output=' + $outRecorded; To = 'output=' + ([System.IO.Path]::GetFullPath($otherOut)); Occurrence = 2
       Why = 'a section that built something else is evidence about something else; the sections must name the artifact under test' },
    @{ Name = 'O1-twin-respells-the-same-output-path-at-the-same-site'; Expect = 'BIND'
       From = 'output=' + $outRecorded; To = 'output=' + $outRecorded.Replace('\', '/'); Occurrence = 2
       Why = 'inert twin: the same artifact, the separators written the other way - the rule is about the path, not its spelling' },

    @{ Name = 'O2-restores-the-unread-placeholder-this-baseline-used-to-carry'; Expect = 'REFUSE'
       From = 'output=' + $outRecorded; To = 'output=(synthetic)'; Occurrence = 1
       Why = 'the round-4 lens: this exact value bound while nothing read the field, so it must now red' },
    @{ Name = 'O2-twin-writes-the-same-path-through-a-redundant-segment'; Expect = 'BIND'
       From = 'output=' + $outRecorded
       To = 'output=' + (Join-Path (Split-Path -Parent $outRecorded) ('.\' + $outName)); Occurrence = 1
       Why = 'inert twin: the same artifact reached by a path that resolves to it' },

    @{ Name = 'O3-states-a-field-no-rule-reads-and-the-ledger-does-not-declare'; Expect = 'REFUSE'
       From = 'provenance(2): buildId=' + $id2; To = 'provenance(2): recapture=no buildId=' + $id2
       Why = 'the class behind the lens finding: a field in the record that nothing exercises must not be able to exist' },
    @{ Name = 'O3-twin-rewrites-the-field-the-ledger-declares-informational'; Expect = 'BIND'
       From = 'captureWriteUtc=' + (Utc $wrote2); To = 'captureWriteUtc=' + (Utc $t0.AddSeconds(-999))
       Why = 'inert twin: the ledger says P6 reads the write time from DISK, so rewriting the recorded one changes nothing' },

    # O4 moves the ARTIFACT, not the record: the log is handed over unedited.
    @{ Name = 'O4-replaces-the-artifact-at-the-recorded-output-path'; Expect = 'REFUSE'
       OutputBytes = ($canonicalBytes + [byte]0)
       Why = 'captures that agree with each other but not with the artifact the recorded command produces must not bind' },
    @{ Name = 'O4-twin-rewrites-that-artifact-with-byte-identical-content'; Expect = 'BIND'
       OutputBytes = $canonicalBytes
       Why = 'inert twin: the same file rewritten at the same site; P8 measures the content, not when it was written' }
)

$failures = 0
$n = 0
foreach ($c in $controls) {
    $n++
    $text = [System.IO.File]::ReadAllText($basePath)
    $occurrence = 1
    if ($c.ContainsKey('Occurrence')) { $occurrence = [int]$c.Occurrence }

    # Every control starts from the canonical artifact, so a pair that moves the
    # file cannot leak into the next one.
    Reset-Artifact
    $edited = ''

    if ($c.ContainsKey('From')) {
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
        $edited = 'edited: ' + $c.From + '   ->   ' + $c.To
    } else {
        # An artifact-only control: the record is handed over exactly as the
        # baseline wrote it, and the line below says so rather than implying an
        # edit that did not happen (#441).
        $mutated = $text
        $edited = 'edited: nothing in the build log - this pair moves the ARTIFACT at the recorded output path'
    }

    if ($c.ContainsKey('OutputBytes')) {
        $wanted = [byte[]]$c.OutputBytes
        [System.IO.File]::WriteAllBytes($outFile, $wanted)
        $same = ($wanted.Length -eq $canonicalBytes.Length)
        if ($same) {
            for ($b = 0; $b -lt $wanted.Length; $b++) { if ($wanted[$b] -ne $canonicalBytes[$b]) { $same = $false; break } }
        }
        $edited = $edited + '   |   artifact: ' + $wanted.Length + ' bytes, ' +
            $(if ($same) { 'byte-identical to the canonical one' } else { 'different from the canonical one' })
    }

    $p = Join-Path $WorkDir ('case{0}-build.log' -f $n)
    [System.IO.File]::WriteAllText($p, $mutated)

    Write-Output ''
    Write-Output ('     $ ' + $psExe + ' -NoProfile -ExecutionPolicy Bypass -File ' + $Binder + ' -Mode Verify -BuildLog ' + $p + ' -Root ' + $WorkDir + ' -Output ' + $outName + ' -Head ' + $head)
    $r = Invoke-Binder -LogPath $p
    $got = if ($r.Code -eq 0) { 'BIND' } else { 'REFUSE' }
    $ok = ($got -eq $c.Expect)
    if (-not $ok) { $failures++ }

    Write-Output ('{0,-4} | control={1,-72} | expected={2,-6} got={3,-6} exit={4} | {5}' -f `
        $(if ($ok) { 'ok' } else { 'BAD' }), $c.Name, $c.Expect, $got, $r.Code, $c.Why)
    Write-Output ('     | ' + $edited)
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
