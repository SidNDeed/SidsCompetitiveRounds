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
#   * a RESULT line is not bound, INSIDE ITS OWN SECTION, to a self-printed
#     invocation line that names the process the result came from (R1).
#
#   * a section header (`--- invocation ---`) is not followed by the echoed
#     command it announces, or the two counts disagree (R1b).
#
#   * the build log does not carry one rebuild section per rebuild it claims,
#     the exact command once per rebuild, one hash per rebuild, equal hash
#     values, and a MATCH verdict that AGREES with the comparison this script
#     performs itself (R2, R3, R6).
#
#   * -Head is given and the artifact's InformationalVersion does not carry it
#     (R5). This project's build embeds the git HEAD in the assembly, so the
#     hash is a function of the COMMIT as well as of the source text; a hash
#     that does not name the commit certifies a tree nobody can identify.
#
# WHAT CHANGED IN R1, AND WHY IT IS A METHOD CHANGE AND NOT A PATCH
# ------------------------------------------------------------------
# R1b was written because the first R1 draft accepted a result whose own echoed
# command had been deleted: the PREVIOUS section's command was still above it,
# and nothing separated the two. The lesson was written down and applied to
# R1b - and R1 itself kept the identical weakness, scanning a WINDOW that ran
# from the previous result rather than from its own section's header. A flag
# names a line and the defect is a class (#432); the sibling went unswept.
#
# R1 now binds a result to its OWN SECTION, and to an invocation line that
# NAMES the process that produced it:
#
#   - the section is the text from the nearest `--- invocation` header at or
#     above the result to that result. A result with no header above it at all
#     FAILS rather than borrowing the file's first one.
#   - the self-printed `invocation:` line must lie inside that section, so a
#     neighbouring section's line can no longer satisfy it. A preparatory step
#     that self-prints an invocation and produces no result cannot stand in for
#     the checker that follows it.
#   - that line must contain the process token this result kind requires. An
#     invocation line whose path has been replaced by placeholder text no
#     longer binds anything, which is what "bound to a process" has to mean if
#     it means anything.
#
# A filter must never discard the line it measures (#441), so every result line
# this finds is PRINTED with the line numbers that bind it, passing or failing.

param(
    [Parameter(Mandatory = $true)][string]$TestsLog,
    [Parameter(Mandatory = $true)][string]$BuildLog,
    [string]$Head = ''
)

$ErrorActionPreference = 'Stop'

# The result lines a lane log can end a section with, and the token the
# invocation above each one must carry. A result kind absent from a given log is
# not a failure - different logs carry different sections - but a log with NO
# result at all is void, because then this script checked nothing.
$resultPatterns = @(
    @{ Name = 'harness';               Pattern = '^roster-census-harness baselineRun='; Token = 'roster-census-harness' },
    @{ Name = 'source-claims';         Pattern = '^CLAIMS (PASS|FAIL|VOID)';            Token = 'check-source-claims.ps1' },
    @{ Name = 'source-claim-controls'; Pattern = '^SOURCE-CLAIM CONTROLS (PASS|FAIL)';  Token = 'run-source-claim-controls.ps1' },
    @{ Name = 'marker-scan';           Pattern = '^SCAN (PASS|FAIL|VOID)';              Token = 'scan-build-markers.ps1' },
    @{ Name = 'census-tokens';         Pattern = '^TOKENS (PASS|FAIL|VOID)';            Token = 'check-dll-census-tokens.ps1' },
    @{ Name = 'scan-controls';         Pattern = '^SCAN CONTROLS (PASS|FAIL)';          Token = 'run-scan-controls.ps1' },
    @{ Name = 'evidence-log';          Pattern = '^EVIDENCE (PASS|FAIL|VOID)';          Token = 'check-evidence-log.ps1' },
    @{ Name = 'evidence-log-controls'; Pattern = '^EVIDENCE-LOG CONTROLS (PASS|FAIL)';  Token = 'run-evidence-log-controls.ps1' },
    @{ Name = 'notes-privacy';         Pattern = '^NOTES (PASS|FAIL|VOID)';             Token = 'check-notes-privacy.ps1' },
    @{ Name = 'notes-citations';       Pattern = '^CITATIONS (PASS|FAIL|VOID)';         Token = 'check-notes-citations.ps1' },
    # The citation gate's controls-only half prints a DIFFERENT verdict, so a
    # run that did not read the notes cannot be swept as one that did.
    @{ Name = 'citation-controls';     Pattern = '^CITATION-CONTROLS (PASS|FAIL|VOID)'; Token = 'check-notes-citations.ps1' },
    @{ Name = 'warning-baseline';      Pattern = '^WARNING-BASELINE (PASS|FAIL|VOID)';  Token = 'check-warning-baseline.ps1' },
    @{ Name = 'harness-inventory';     Pattern = '^HARNESS-INVENTORY (PASS|FAIL|VOID)'; Token = 'check-harness-inventory.ps1' },
    @{ Name = 'artifact-bind-controls';Pattern = '^ARTIFACT-BIND CONTROLS (PASS|FAIL|VOID)'; Token = 'run-artifact-bind-controls.ps1' },
    # The build log's own two verdicts. They are results here because a process
    # computes and prints them above its own invocation line - which is what
    # made the build log sweepable at all. The process that prints them is now
    # the one that RAN the rebuilds, so the token names it.
    @{ Name = 'artifact-hash-match';   Pattern = '^(MATCH|MISMATCH) \|';                Token = 'build-and-bind-artifact.ps1' },
    @{ Name = 'artifact-commit-bound'; Pattern = '^(BOUND|UNBOUND) \|';                 Token = 'build-and-bind-artifact.ps1' }
)

$selfPrintedPattern = '^invocation:'
$echoedCommandPattern = '^\$ '
$sectionHeaderPattern = '^--- invocation'
$rebuildHeaderPattern = '^--- invocation \(rebuild (\d+) of (\d+)\) ---'
$buildCommand = 'dotnet build plugin/CompetitiveRounds.csproj -c Release -t:Rebuild -p:SkipCopyToPlugins=true'

Write-Output "=== roster-census evidence-log check ==="
Write-Output ("invocation:      " + [Environment]::CommandLine)
Write-Output ("invocation-utc:  " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ("tests-log:       " + $TestsLog)
Write-Output ("build-log:       " + $BuildLog)
Write-Output ("head:            " + $(if ($Head -eq '') { '(not asserted)' } else { $Head }))
Write-Output ""
Write-Output "--- the rules this check enforces ---"
Write-Output ("R1  every result is bound, INSIDE ITS OWN SECTION, to " + $selfPrintedPattern + " naming the process that produced it")
Write-Output ("R1b every " + $sectionHeaderPattern + " header is followed by the command it announces (" + $echoedCommandPattern + "), and the counts agree")
Write-Output "R1c every verdict-shaped line is claimed by one of the named result patterns above, so a gate nobody listed cannot pass unswept"
Write-Output ("R2  the build log carries one rebuild section per rebuild, indices 1..n, and the exact command n times: " + $buildCommand)
Write-Output "R3  one sha256 line per rebuild, indices 1..n, all values equal"
Write-Output "R4  the build log carries 0 Error(s)"
Write-Output "R5  when -Head is given, InformationalVersion names that commit"
Write-Output "R6  the build log's own MATCH/BOUND verdicts AGREE with the comparison made here"
Write-Output ""

$failures = 0

# ---- R1 ---------------------------------------------------------------------

if (-not (Test-Path -LiteralPath $TestsLog)) {
    Write-Output ("FAIL | R1 | no such file: " + $TestsLog)
    Write-Output "EVIDENCE VOID | the tests log could not be read"
    exit 3
}

$testLines = @(Get-Content -LiteralPath $TestsLog)

Write-Output "--- R1: every result bound to its own section's invocation ---"

$resultsFound = 0
for ($i = 0; $i -lt $testLines.Count; $i++) {
    $line = $testLines[$i]
    $kind = $null
    $token = $null
    foreach ($p in $resultPatterns) {
        if ($line -match $p.Pattern) { $kind = $p.Name; $token = $p.Token; break }
    }
    if ($null -eq $kind) { continue }

    $resultsFound = $resultsFound + 1

    # The result's OWN section: from the nearest header at or above it. Not
    # from the previous result - that window spans whatever sections happen to
    # lie between, which is how a neighbour's invocation line came to satisfy a
    # rule about this result.
    $sectionAt = -1
    for ($j = $i - 1; $j -ge 0; $j--) {
        if ($testLines[$j] -match $sectionHeaderPattern) { $sectionAt = $j; break }
    }

    $selfAt = -1
    if ($sectionAt -ge 0) {
        for ($j = $sectionAt + 1; $j -lt $i; $j++) {
            if ($testLines[$j] -match $selfPrintedPattern) { $selfAt = $j }
        }
    }

    $named = ($selfAt -ge 0) -and ($testLines[$selfAt].Contains($token))
    $ok = ($sectionAt -ge 0) -and ($selfAt -ge 0) -and $named
    if (-not $ok) { $failures = $failures + 1 }

    Write-Output ("{0,-4} | R1 | result={1,-22} at line {2,-5} | section header line={3,-5} | self-printed invocation line={4,-5} | names '{5}'={6}" -f `
        $(if ($ok) { 'ok' } else { 'FAIL' }), $kind, ($i + 1),
        $(if ($sectionAt -ge 0) { $sectionAt + 1 } else { 'none' }),
        $(if ($selfAt -ge 0) { $selfAt + 1 } else { 'none' }),
        $token, $(if ($named) { 'yes' } else { 'NO' }))
    Write-Output ("     | result: " + $line.Trim())
    if ($selfAt -ge 0) { Write-Output ("     | invocation: " + $testLines[$selfAt].Trim()) }
}

if ($resultsFound -eq 0) {
    Write-Output "FAIL | R1 | the tests log carries no result line at all"
    Write-Output "EVIDENCE VOID | nothing was checked - a log with no results is not a passing log"
    exit 3
}

# ---- R1c --------------------------------------------------------------------
#
# $resultPatterns is a hand-maintained list, and nothing asserted it was
# complete. That is the same shape as the hand-kept span list the claims checker
# was rebuilt to remove: a gate can print a verdict this sweep has no pattern
# for, and the sweep reports a clean PASS over the sections it happens to know
# about. It happened. check-notes-citations.ps1 was added, printed CITATIONS
# PASS at the foot of its own section, and R1 swept four results past it without
# a word.
#
# So the named list is reconciled against a GENERIC verdict shape: an
# unindented, upper-case, PASS/FAIL/VOID line. Anything shaped like a verdict
# that no named pattern claims is a gate nobody is binding, and it fails here.
# Indented lines are excluded by the anchor, which is what keeps a verdict
# echoed inside another section's control output from counting (the runners
# indent those deliberately).
#
# WHICH WAY THE UNHANDLED CASE FAILS (#276 / #430). A new gate is UNCOVERED
# until someone lists it, and uncovered is a failure rather than a silent pass.
# The cost of that refusal is one line in the list above.

$verdictShape = '^[A-Z][A-Z0-9 -]* (PASS|FAIL|VOID)$'
Write-Output ""
Write-Output "--- R1c: every verdict-shaped line is claimed by a named result pattern ---"

$uncovered = 0
$verdictLines = 0
for ($i = 0; $i -lt $testLines.Count; $i++) {
    $line = $testLines[$i]
    if (-not ($line -match $verdictShape)) { continue }
    $verdictLines = $verdictLines + 1
    $claimedBy = $null
    foreach ($p in $resultPatterns) {
        if ($line -match $p.Pattern) { $claimedBy = $p.Name; break }
    }
    if ($null -eq $claimedBy) {
        $uncovered = $uncovered + 1
        $failures = $failures + 1
        Write-Output ("FAIL | R1c | line {0}: '{1}' is shaped like a verdict and no named result pattern claims it - a gate whose result nothing binds" -f ($i + 1), $line.Trim())
    } else {
        Write-Output ("ok   | R1c | line {0,-5} | {1,-34} | claimed by '{2}'" -f ($i + 1), $line.Trim(), $claimedBy)
    }
}
Write-Output ("     | R1c | verdict-shaped lines={0} uncovered={1} named patterns={2}" -f $verdictLines, $uncovered, $resultPatterns.Count)

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

# ---- R2 to R6 ---------------------------------------------------------------

if (-not (Test-Path -LiteralPath $BuildLog)) {
    Write-Output ("FAIL | R2 | no such file: " + $BuildLog)
    Write-Output "EVIDENCE VOID | the build log could not be read"
    exit 3
}

$buildLines = @(Get-Content -LiteralPath $BuildLog)
$buildText = ($buildLines -join "`n")

Write-Output "--- R2 to R6: the build log binds a repeatable artifact to a commit ---"

# The rebuild SECTIONS, which are what says how many builds actually ran. A hash
# line is evidence about a rebuild only if that rebuild has a section of its own:
# two hash lines above one rebuild are one measurement written twice.
$rebuildIndices = New-Object System.Collections.ArrayList
$rebuildTotals = New-Object System.Collections.ArrayList
for ($i = 0; $i -lt $buildLines.Count; $i++) {
    $m = [System.Text.RegularExpressions.Regex]::Match($buildLines[$i], $rebuildHeaderPattern)
    if ($m.Success) {
        [void]$rebuildIndices.Add([int]$m.Groups[1].Value)
        [void]$rebuildTotals.Add([int]$m.Groups[2].Value)
        Write-Output ("     | R2 | rebuild section {0} of {1} at line {2}" -f `
            $m.Groups[1].Value, $m.Groups[2].Value, ($i + 1))
    }
}

$rebuilds = $rebuildIndices.Count
$sortedRebuilds = @($rebuildIndices | Sort-Object)
$expected = @(1..([Math]::Max($rebuilds, 1)))
$indicesOk = ($rebuilds -ge 2) -and (($sortedRebuilds -join ',') -eq ($expected -join ','))
$totalsOk = ($rebuilds -ge 1) -and (@($rebuildTotals | Sort-Object -Unique).Count -eq 1) -and ($rebuildTotals[0] -eq $rebuilds)

if (-not $indicesOk) { $failures = $failures + 1 }
if (-not $totalsOk) { $failures = $failures + 1 }
Write-Output ("{0,-4} | R2 | rebuild sections={1}, indices={2}, expected at least 2 numbered 1..n" -f `
    $(if ($indicesOk) { 'ok' } else { 'FAIL' }), $rebuilds, ($sortedRebuilds -join ','))
Write-Output ("{0,-4} | R2 | every header agrees on the total: {1}" -f `
    $(if ($totalsOk) { 'ok' } else { 'FAIL' }), $(if ($rebuildTotals.Count -gt 0) { ($rebuildTotals | Sort-Object -Unique) -join ',' } else { 'none' }))

$commandHits = 0
foreach ($line in $buildLines) { if ($line.Contains($buildCommand)) { $commandHits = $commandHits + 1 } }
$r2 = ($rebuilds -ge 2) -and ($commandHits -eq $rebuilds)
if (-not $r2) { $failures = $failures + 1 }
Write-Output ("{0,-4} | R2 | the exact rebuild command appears {1} time(s), expected once per rebuild section ({2})" -f `
    $(if ($r2) { 'ok' } else { 'FAIL' }), $commandHits, $rebuilds)

$hashes = New-Object System.Collections.ArrayList
for ($i = 0; $i -lt $buildLines.Count; $i++) {
    $m = [System.Text.RegularExpressions.Regex]::Match($buildLines[$i], 'sha256\((\d+)\):\s*([0-9a-fA-F]{64})')
    if ($m.Success) {
        [void]$hashes.Add([pscustomobject]@{ Index = [int]$m.Groups[1].Value; Value = $m.Groups[2].Value.ToLowerInvariant(); Line = $i + 1 })
    }
}

foreach ($h in $hashes) {
    Write-Output ("     | R3 | sha256(" + $h.Index + ") at line " + $h.Line + " = " + $h.Value)
}

$distinct = @($hashes | ForEach-Object { $_.Value } | Sort-Object -Unique)
$sortedHashIndices = @($hashes | ForEach-Object { $_.Index } | Sort-Object)

# The indices must be 1..n and there must be one per rebuild section. This is
# what a duplicated-and-renumbered hash line cannot satisfy: the second copy
# either repeats an index or has no rebuild of its own to belong to.
$r3count = ($hashes.Count -ge 2) -and ($hashes.Count -eq $rebuilds)
$r3indices = ($hashes.Count -ge 2) -and (($sortedHashIndices -join ',') -eq (@(1..([Math]::Max($hashes.Count, 1))) -join ','))
$r3same = ($distinct.Count -eq 1)

if (-not $r3count) { $failures = $failures + 1 }
if (-not $r3indices) { $failures = $failures + 1 }
if (-not $r3same) { $failures = $failures + 1 }

Write-Output ("{0,-4} | R3 | sha256 lines found={1}, rebuild sections={2}, expected one per rebuild and at least 2" -f `
    $(if ($r3count) { 'ok' } else { 'FAIL' }), $hashes.Count, $rebuilds)
Write-Output ("{0,-4} | R3 | sha256 indices={1}, expected 1..{2} with no repeat" -f `
    $(if ($r3indices) { 'ok' } else { 'FAIL' }), ($sortedHashIndices -join ','), $hashes.Count)
Write-Output ("{0,-4} | R3 | distinct hash values={1}, expected exactly 1" -f `
    $(if ($r3same) { 'ok' } else { 'FAIL' }), $distinct.Count)

$r4 = ($buildText -match '0 Error\(s\)')
if (-not $r4) { $failures = $failures + 1 }
Write-Output ("{0,-4} | R4 | the build log reports 0 Error(s)" -f $(if ($r4) { 'ok' } else { 'FAIL' }))

$r5 = $true
if ($Head -ne '') {
    $wanted = 'InformationalVersion: 1.0.0+' + $Head
    $r5 = $false
    foreach ($line in $buildLines) { if ($line.Contains($wanted)) { $r5 = $true } }
    if (-not $r5) { $failures = $failures + 1 }
    Write-Output ("{0,-4} | R5 | the artifact names the commit: {1}" -f $(if ($r5) { 'ok' } else { 'FAIL' }), $wanted)
} else {
    Write-Output "     | R5 | no -Head given, the commit binding is not asserted by this run"
}

# ---- R6: the claimed verdicts must equal the computed ones ------------------

# A verdict word is only evidence if something can contradict it. These two
# compare what the build log SAYS against what this script worked out from the
# same numbers, so a MATCH written over two different hashes reds on the
# disagreement and not merely on the hashes.
$computedMatch = ($r3same -and $r3count -and $r3indices)
$claimsMatch = ($buildText -match '(?m)^MATCH \|')
$claimsMismatch = ($buildText -match '(?m)^MISMATCH \|')
$r6match = ($claimsMatch -eq $computedMatch) -and ($claimsMismatch -ne $computedMatch)
if (-not $r6match) { $failures = $failures + 1 }
Write-Output ("{0,-4} | R6 | the log claims MATCH={1} MISMATCH={2}; computed from its own numbers: {3}" -f `
    $(if ($r6match) { 'ok' } else { 'FAIL' }), $claimsMatch, $claimsMismatch, $computedMatch)

$claimsBound = ($buildText -match '(?m)^BOUND \|')
$claimsUnbound = ($buildText -match '(?m)^UNBOUND \|')
$computedBound = ($Head -ne '') -and $r5
$r6bound = $true
if ($Head -ne '') {
    $r6bound = ($claimsBound -eq $computedBound) -and ($claimsUnbound -ne $computedBound)
    if (-not $r6bound) { $failures = $failures + 1 }
    Write-Output ("{0,-4} | R6 | the log claims BOUND={1} UNBOUND={2}; computed from its own version line: {3}" -f `
        $(if ($r6bound) { 'ok' } else { 'FAIL' }), $claimsBound, $claimsUnbound, $computedBound)
} else {
    Write-Output "     | R6 | no -Head given, the claimed commit binding is not reconciled by this run"
}

Write-Output ""
Write-Output ("results=" + $resultsFound + " rebuilds=" + $rebuilds + " hashes=" + $hashes.Count + " failures=" + $failures)

if ($failures -gt 0) {
    Write-Output "EVIDENCE FAIL"
    exit 1
}
Write-Output "EVIDENCE PASS"
exit 0
