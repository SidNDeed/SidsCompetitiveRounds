# Does this round's EVIDENCE hold up as evidence?
#
# WHY THIS EXISTS
# ---------------
# Two of round 2's closures were asserted and never run. The harness printed
# its own invocation above its results, and the build log carried a second
# matching hash - both true, and neither had an executable rejection behind it.
# Removing the invocation line, or removing the second hash, left every check
# in the lane green. A closure whose removal changes no verdict is a claim
# about the evidence, not a property of it (#342 / #391).
#
# So this script is the rejection. It reads the logs a round produced and fails
# when:
#
#   * a RESULT line has no SELF-PRINTED invocation above it, since the previous
#     result. That line is printed by the process about itself, so it cannot
#     drift from what actually ran the way a hand-written log header can.
#
#   * a section header (`--- invocation ---`) is not followed by the echoed
#     command it announces, or the two counts disagree. This is checked as a
#     PAIRING and not as "a command line appears somewhere above the result":
#     the first version of this rule accepted a result whose own echoed command
#     had been deleted, because the command of the PREVIOUS section was still
#     above it and nothing separated the two. A rule a neighbouring section can
#     satisfy is a rule about the file, not about the result (#342).
#
#   * the build log does not carry the exact rebuild command, TWO sha256 lines
#     with the SAME value, and an explicit MATCH verdict. One hash demonstrates
#     neither the flags nor repeatability.
#
#   * -Head is given and the artifact's InformationalVersion does not carry it.
#     This project's build embeds the git HEAD in the assembly, so the hash is
#     a function of the COMMIT as well as of the source text; a hash that does
#     not name the commit certifies a tree nobody can identify.
#
# A filter must never discard the line it measures (#441), so every result line
# this finds is PRINTED with the line numbers that bind it, passing or failing.

param(
    [Parameter(Mandatory = $true)][string]$TestsLog,
    [Parameter(Mandatory = $true)][string]$BuildLog,
    [string]$Head = ''
)

$ErrorActionPreference = 'Stop'

# The result lines a lane log can end a section with. A result kind absent from
# a given log is not a failure - different logs carry different sections - but a
# log with NO result at all is void, because then this script checked nothing.
$resultPatterns = @(
    @{ Name = 'harness';               Pattern = '^roster-census-harness baselineRun=' },
    @{ Name = 'source-claims';         Pattern = '^CLAIMS (PASS|FAIL|VOID)' },
    @{ Name = 'source-claim-controls'; Pattern = '^SOURCE-CLAIM CONTROLS (PASS|FAIL)' },
    @{ Name = 'marker-scan';           Pattern = '^SCAN (PASS|FAIL|VOID)' },
    @{ Name = 'census-tokens';         Pattern = '^TOKENS (PASS|FAIL|VOID)' },
    @{ Name = 'scan-controls';         Pattern = '^SCAN CONTROLS (PASS|FAIL)' },
    @{ Name = 'evidence-log';          Pattern = '^EVIDENCE (PASS|FAIL|VOID)' },
    @{ Name = 'evidence-log-controls'; Pattern = '^EVIDENCE-LOG CONTROLS (PASS|FAIL)' }
)

$selfPrintedPattern = '^invocation:'
$echoedCommandPattern = '^\$ '
$sectionHeaderPattern = '^--- invocation ---'
$buildCommand = 'dotnet build plugin/CompetitiveRounds.csproj -c Release -t:Rebuild -p:SkipCopyToPlugins=true'

Write-Output "=== roster-census evidence-log check ==="
Write-Output ("invocation:      " + [Environment]::CommandLine)
Write-Output ("invocation-utc:  " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ("tests-log:       " + $TestsLog)
Write-Output ("build-log:       " + $BuildLog)
Write-Output ("head:            " + $(if ($Head -eq '') { '(not asserted)' } else { $Head }))
Write-Output ""
Write-Output "--- the rules this check enforces ---"
Write-Output ("R1  every result line is preceded, since the previous result, by " + $selfPrintedPattern + " printed by the process itself")
Write-Output ("R1b every " + $sectionHeaderPattern + " header is followed by the command it announces (" + $echoedCommandPattern + "), and the counts agree")
Write-Output ("R2 the build log carries the exact command: " + $buildCommand)
Write-Output "R3 the build log carries two sha256 lines with the SAME value, and a MATCH verdict"
Write-Output "R4 the build log carries 0 Error(s)"
Write-Output "R5 when -Head is given, InformationalVersion names that commit"
Write-Output ""

$failures = 0

# ---- R1 ---------------------------------------------------------------------

if (-not (Test-Path -LiteralPath $TestsLog)) {
    Write-Output ("FAIL | R1 | no such file: " + $TestsLog)
    Write-Output "EVIDENCE VOID | the tests log could not be read"
    exit 3
}

$testLines = @(Get-Content -LiteralPath $TestsLog)

Write-Output "--- R1: every result bound to an invocation ---"

$resultsFound = 0
$previousResultIndex = -1
for ($i = 0; $i -lt $testLines.Count; $i++) {
    $line = $testLines[$i]
    $kind = $null
    foreach ($p in $resultPatterns) {
        if ($line -match $p.Pattern) { $kind = $p.Name; break }
    }
    if ($null -eq $kind) { continue }

    $resultsFound = $resultsFound + 1

    $selfAt = -1
    for ($j = $previousResultIndex + 1; $j -lt $i; $j++) {
        if ($testLines[$j] -match $selfPrintedPattern) { $selfAt = $j }
    }

    $ok = ($selfAt -ge 0)
    if (-not $ok) { $failures = $failures + 1 }

    Write-Output ("{0,-4} | R1 | result={1,-22} at line {2,-5} | self-printed invocation line={3,-5}" -f `
        $(if ($ok) { 'ok' } else { 'FAIL' }), $kind, ($i + 1),
        $(if ($selfAt -ge 0) { $selfAt + 1 } else { 'none' }))
    Write-Output ("     | result: " + $line.Trim())

    $previousResultIndex = $i
}

if ($resultsFound -eq 0) {
    Write-Output "FAIL | R1 | the tests log carries no result line at all"
    Write-Output "EVIDENCE VOID | nothing was checked - a log with no results is not a passing log"
    exit 3
}

Write-Output ""
Write-Output "--- R1b: every section header paired with the command it announces ---"

$headerCount = 0
$echoCount = 0
foreach ($line in $testLines) {
    if ($line -match $sectionHeaderPattern) { $headerCount = $headerCount + 1 }
    if ($line -match $echoedCommandPattern) { $echoCount = $echoCount + 1 }
}

$unpaired = 0
for ($i = 0; $i -lt $testLines.Count; $i++) {
    if (-not ($testLines[$i] -match $sectionHeaderPattern)) { continue }

    # The next NON-BLANK line after the header is the command it announces.
    $next = -1
    for ($j = $i + 1; $j -lt $testLines.Count; $j++) {
        if ($testLines[$j].Trim() -ne '') { $next = $j; break }
    }
    $paired = ($next -ge 0) -and ($testLines[$next] -match $echoedCommandPattern)
    if (-not $paired) {
        $unpaired = $unpaired + 1
        Write-Output ("FAIL | R1b | header at line {0} announces no command; next non-blank line {1}: {2}" -f `
            ($i + 1), $(if ($next -ge 0) { $next + 1 } else { 'none' }),
            $(if ($next -ge 0) { $testLines[$next].Trim() } else { '(end of file)' }))
    } else {
        Write-Output ("ok   | R1b | header at line {0} -> command at line {1}: {2}" -f `
            ($i + 1), ($next + 1), $testLines[$next].Trim())
    }
}

if ($unpaired -gt 0) { $failures = $failures + 1 }

$countsAgree = ($headerCount -eq $echoCount)
if (-not $countsAgree) { $failures = $failures + 1 }
Write-Output ("{0,-4} | R1b | headers={1} echoed commands={2}" -f `
    $(if ($countsAgree) { 'ok' } else { 'FAIL' }), $headerCount, $echoCount)

Write-Output ""

# ---- R2 to R5 ---------------------------------------------------------------

if (-not (Test-Path -LiteralPath $BuildLog)) {
    Write-Output ("FAIL | R2 | no such file: " + $BuildLog)
    Write-Output "EVIDENCE VOID | the build log could not be read"
    exit 3
}

$buildLines = @(Get-Content -LiteralPath $BuildLog)
$buildText = ($buildLines -join "`n")

Write-Output "--- R2 to R5: the build log binds a repeatable artifact to a commit ---"

$commandHits = 0
foreach ($line in $buildLines) { if ($line.Contains($buildCommand)) { $commandHits = $commandHits + 1 } }
$r2 = $commandHits -ge 1
if (-not $r2) { $failures = $failures + 1 }
Write-Output ("{0,-4} | R2 | the exact rebuild command appears {1} time(s)" -f $(if ($r2) { 'ok' } else { 'FAIL' }), $commandHits)

$hashes = New-Object System.Collections.ArrayList
for ($i = 0; $i -lt $buildLines.Count; $i++) {
    $m = [System.Text.RegularExpressions.Regex]::Match($buildLines[$i], 'sha256\((\d+)\):\s*([0-9a-fA-F]{64})')
    if ($m.Success) {
        [void]$hashes.Add([pscustomobject]@{ Index = $m.Groups[1].Value; Value = $m.Groups[2].Value.ToLowerInvariant(); Line = $i + 1 })
    }
}

foreach ($h in $hashes) {
    Write-Output ("     | R3 | sha256(" + $h.Index + ") at line " + $h.Line + " = " + $h.Value)
}

$distinct = @($hashes | ForEach-Object { $_.Value } | Sort-Object -Unique)
$r3count = ($hashes.Count -ge 2)
$r3same = ($distinct.Count -eq 1)
$r3match = ($buildText -match '(?m)^MATCH \|')

if (-not $r3count) { $failures = $failures + 1 }
if (-not $r3same) { $failures = $failures + 1 }
if (-not $r3match) { $failures = $failures + 1 }

Write-Output ("{0,-4} | R3 | sha256 lines found={1}, expected at least 2" -f $(if ($r3count) { 'ok' } else { 'FAIL' }), $hashes.Count)
Write-Output ("{0,-4} | R3 | distinct hash values={1}, expected exactly 1" -f $(if ($r3same) { 'ok' } else { 'FAIL' }), $distinct.Count)
Write-Output ("{0,-4} | R3 | an explicit MATCH verdict line is present" -f $(if ($r3match) { 'ok' } else { 'FAIL' }))

$r4 = ($buildText -match '0 Error\(s\)')
if (-not $r4) { $failures = $failures + 1 }
Write-Output ("{0,-4} | R4 | the build log reports 0 Error(s)" -f $(if ($r4) { 'ok' } else { 'FAIL' }))

if ($Head -ne '') {
    $wanted = 'InformationalVersion: 1.0.0+' + $Head
    $r5 = $false
    foreach ($line in $buildLines) { if ($line.Contains($wanted)) { $r5 = $true } }
    if (-not $r5) { $failures = $failures + 1 }
    Write-Output ("{0,-4} | R5 | the artifact names the commit: {1}" -f $(if ($r5) { 'ok' } else { 'FAIL' }), $wanted)
} else {
    Write-Output "     | R5 | no -Head given, the commit binding is not asserted by this run"
}

Write-Output ""
Write-Output ("results=" + $resultsFound + " hashes=" + $hashes.Count + " failures=" + $failures)

if ($failures -gt 0) {
    Write-Output "EVIDENCE FAIL"
    exit 1
}
Write-Output "EVIDENCE PASS"
exit 0
