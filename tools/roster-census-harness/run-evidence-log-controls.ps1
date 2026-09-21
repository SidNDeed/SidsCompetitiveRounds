# Mutation controls for check-evidence-log.ps1.
#
# The evidence check exists because two round-2 closures had no executable
# rejection: removing the harness's invocation line, or removing the second
# build hash, left every verdict in the lane green. A check written to close
# that has to be SHOWN to reject exactly those two removals, and shown not to
# reject an edit of the same shape that takes nothing away (#712) - otherwise
# all that has been demonstrated is that the script noticed a file changed.
#
# So every site below carries a PAIR: a mutation that must turn the check FAIL,
# and an INERT TWIN - an edit to the SAME line, or of the same shape at the same
# place - that must keep it PASSING.
#
# WHAT THE LENS PASS ADDED, AND WHY
# ---------------------------------
# Four of the round-3 rules turned out to be satisfiable without the thing they
# were meant to demonstrate, and each now has a pair that says so:
#
#   * R3 accepted two hash lines with the same value and never asked whether two
#     builds had run. E4 is the lens's own scenario - one rebuild, its hash line
#     copied and renumbered - and it must red.
#   * The MATCH verdict was free text. E5 claims MATCH over two different
#     artifacts and must red on the disagreement between the claim and the
#     comparison the checker makes itself.
#   * R1 bound a result to any invocation line in a window that could span a
#     NEIGHBOURING section - the exact weakness R1b was written to remove, left
#     in the sibling (#432). E8 is a preparatory step that self-prints an
#     invocation and produces no result, followed by a checker whose own
#     invocation line is gone. This runner also evaluates the OLD window rule
#     over that same mutant and PRINTS what it would have said, so the method
#     change is judged by a measurement rather than by the claim that it helped.
#   * The build log could not be swept at all: it carried no line the checker
#     recognised as a result, so passing it in returned VOID. Its verdicts are
#     computed and self-printed now, and E6 sweeps it.
#
# Nothing here touches the round's real logs. Each case works from a fresh copy
# in a temporary directory, so no restore of anything is ever needed
# (#290 / #401).

param(
    [Parameter(Mandatory = $true)][string]$TestsLog,
    [Parameter(Mandatory = $true)][string]$BuildLog,
    [string]$Head = '',
    [string]$Checker = '',
    [string]$WorkDir = ''
)

$ErrorActionPreference = 'Stop'

# Resolved in the BODY, not in a param default: with Mandatory parameters in the
# same block, $PSScriptRoot is not yet populated when the defaults are
# evaluated on this host, and the failure is a bind error a long way from its
# cause.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrEmpty($Checker)) {
    $Checker = (Resolve-Path -LiteralPath (Join-Path $here 'check-evidence-log.ps1')).Path
}
if ([string]::IsNullOrEmpty($WorkDir)) {
    $WorkDir = Join-Path ([System.IO.Path]::GetTempPath()) 'scr-r3-evidence-log-controls'
}

# The preparatory section E8 inserts: a step that prints its own invocation and
# produces no result line at all. A version probe, a hash helper, an
# environment dump - anything of that shape leaves an invocation line sitting
# above the next section's result.
$preparatorySection = @(
    '--- invocation ---',
    '$ powershell -NoProfile -File tools/roster-census-harness/print-runtime-version.ps1',
    '',
    'invocation:     tools/roster-census-harness/print-runtime-version.ps1',
    'runtime:        10.0.11',
    'exit=0',
    ''
)

# Each case: what it edits, and whether the checker must pass afterwards.
# Sweep says which log is handed in as -TestsLog, so the build log can be put
# through the same rule as everything else.
$cases = @(
    @{ Name = 'E1-removes-the-harness-self-printed-invocation'; Expect = 'FAIL'; Sweep = 'tests';
       Why = 'round-3 finding 3: removing the invocation line must change a verdict';
       Edits = @(@{ Log = 'tests'; Anchor = '^invocation:\s+\S*roster-census-harness\.dll'; Action = 'remove' }) },
    @{ Name = 'E1-twin-respaces-the-same-invocation-line'; Expect = 'PASS'; Sweep = 'tests';
       Why = 'inert twin: the same line, respaced, still names the process that produced the result';
       Edits = @(@{ Log = 'tests'; Anchor = '^invocation:\s+\S*roster-census-harness\.dll'; Action = 'respace-invocation' }) },

    @{ Name = 'E2-removes-the-echoed-harness-command'; Expect = 'FAIL'; Sweep = 'tests';
       Why = 'round-3 finding 3: a section header whose command is gone must red, not fall back on a neighbour';
       Edits = @(@{ Log = 'tests'; Anchor = '^\$ dotnet tools/roster-census-harness/bin/'; Action = 'remove' }) },
    @{ Name = 'E2-twin-rewords-the-same-echoed-command'; Expect = 'PASS'; Sweep = 'tests';
       Why = 'inert twin: the same command line, reworded, still says how it was started';
       Edits = @(@{ Log = 'tests'; Anchor = '^\$ dotnet tools/roster-census-harness/bin/'; Action = 'replace';
                    Replacement = '$ dotnet tools/roster-census-harness/bin/Release/net10.0/roster-census-harness.dll --quiet' }) },

    @{ Name = 'E3-removes-the-second-build-hash'; Expect = 'FAIL'; Sweep = 'tests';
       Why = 'round-3 finding 3: removing the second hash must change a verdict';
       Edits = @(@{ Log = 'build'; Anchor = '^sha256\(2\):'; Action = 'remove' }) },
    @{ Name = 'E3-twin-reformats-the-same-hash-line'; Expect = 'PASS'; Sweep = 'tests';
       Why = 'inert twin: the same hash, respaced, still demonstrates repeatability';
       Edits = @(@{ Log = 'build'; Anchor = '^sha256\(2\):'; Action = 'respace-hash'; Index = '2' }) },

    # THE LENS SCENARIO. One rebuild, its hash line copied and renumbered. The
    # values still agree, because they are the same measurement written twice.
    @{ Name = 'E4-renumbers-one-rebuilds-hash-as-a-second'; Expect = 'FAIL'; Sweep = 'tests';
       Why = 'lens finding 3: two hash lines are repeatability only if two rebuilds ran';
       Edits = @(
           @{ Log = 'build'; Anchor = '^--- invocation \(rebuild 2 of 2\) ---'; Action = 'remove' },
           @{ Log = 'build'; Anchor = '^--- invocation \(rebuild 1 of 2\) ---'; Action = 'replace';
              Replacement = '--- invocation (rebuild 1 of 1) ---' },
           @{ Log = 'build'; Anchor = '^\$ dotnet build plugin/CompetitiveRounds\.csproj'; Action = 'remove'; Occurrence = 2 }) },
    @{ Name = 'E4-twin-exchanges-the-two-hash-index-labels'; Expect = 'PASS'; Sweep = 'tests';
       Why = 'inert twin: the same two hashes and the same two rebuilds, their index labels exchanged';
       Edits = @(
           @{ Log = 'build'; Anchor = '^sha256\(1\):'; Action = 'renumber-hash'; Index = '2' },
           @{ Log = 'build'; Anchor = '^sha256\(2\):'; Action = 'renumber-hash'; Index = '1'; Occurrence = 2 }) },

    @{ Name = 'E5-claims-a-match-over-two-different-artifacts'; Expect = 'FAIL'; Sweep = 'tests';
       Why = 'lens finding 3: a claimed verdict must equal the verdict computed from the same numbers';
       Edits = @(@{ Log = 'build'; Anchor = '^sha256\(2\):'; Action = 'replace-hash-value';
                    Replacement = '0000000000000000000000000000000000000000000000000000000000000000' }) },
    @{ Name = 'E5-twin-rewrites-the-same-hash-in-upper-case'; Expect = 'PASS'; Sweep = 'tests';
       Why = 'inert twin: the same hash value on the same line, in different case';
       Edits = @(@{ Log = 'build'; Anchor = '^sha256\(2\):'; Action = 'upper-hash' }) },

    # The build log put through the same rule as every other log.
    @{ Name = 'E6-removes-the-binders-self-printed-invocation'; Expect = 'FAIL'; Sweep = 'build';
       Why = 'lens finding 5: the build log''s own verdicts must be bound to the process that computed them';
       Edits = @(@{ Log = 'build'; Anchor = '^invocation:\s+.*bind-artifact-hash'; Action = 'remove' }) },
    @{ Name = 'E6-twin-respaces-the-binders-invocation'; Expect = 'PASS'; Sweep = 'build';
       Why = 'inert twin: the same line, respaced, still binds MATCH and BOUND to the process that computed them';
       Edits = @(@{ Log = 'build'; Anchor = '^invocation:\s+.*bind-artifact-hash'; Action = 'respace-invocation' }) },

    # An invocation line that names nothing binds nothing.
    @{ Name = 'E7-replaces-the-invocation-path-with-placeholder-text'; Expect = 'FAIL'; Sweep = 'tests';
       Why = 'lens finding 4: an invocation line must name the process the result came from';
       Edits = @(@{ Log = 'tests'; Anchor = '^invocation:\s+\S*roster-census-harness\.dll'; Action = 'replace';
                    Replacement = 'invocation:     <path withheld>' }) },
    @{ Name = 'E7-twin-rewords-around-the-process-name'; Expect = 'PASS'; Sweep = 'tests';
       Why = 'inert twin: the same line reworded, the process still named';
       Edits = @(@{ Log = 'tests'; Anchor = '^invocation:\s+\S*roster-census-harness\.dll'; Action = 'replace';
                    Replacement = 'invocation:     (re-run) tools/roster-census-harness/bin/Release/net10.0/roster-census-harness.dll --quiet' }) },

    # THE SIBLING R1B WAS FIXED FOR AND R1 WAS NOT. A preparatory step that
    # self-prints and produces no result, and the section after it stripped of
    # its own invocation line.
    @{ Name = 'E8-lets-a-preparatory-section-stand-in-for-a-missing-invocation'; Expect = 'FAIL'; Sweep = 'tests';
       Why = 'lens finding 4: a result is bound by ITS OWN section, never by a neighbour''s';
       OldRule = $true;
       Edits = @(
           @{ Log = 'tests'; Anchor = '^\$ powershell -NoProfile -ExecutionPolicy Bypass -File tools/roster-census-harness/run-source-claim-controls\.ps1';
              Action = 'insert-before-section' },
           @{ Log = 'tests'; Anchor = '^invocation:\s+.*run-source-claim-controls'; Action = 'remove' }) },
    @{ Name = 'E8-twin-inserts-the-same-preparatory-section-only'; Expect = 'PASS'; Sweep = 'tests';
       Why = 'inert twin: the same insertion, the following section keeping its own invocation line';
       OldRule = $true;
       Edits = @(
           @{ Log = 'tests'; Anchor = '^\$ powershell -NoProfile -ExecutionPolicy Bypass -File tools/roster-census-harness/run-source-claim-controls\.ps1';
              Action = 'insert-before-section' }) },

    # THE NAMED RESULT LIST IS HAND-MAINTAINED, AND NOTHING ASSERTED IT WAS
    # COMPLETE. A gate that prints a verdict no pattern claims used to be swept
    # straight past - which is how the citation gate's own verdict went unbound
    # on its first run. E9 renames a verdict to a gate the list does not know;
    # its twin changes the same line's outcome word, which the pattern still
    # claims, so a red proves the rule is about COVERAGE and not about the line
    # having moved.
    @{ Name = 'E9-prints-a-verdict-no-named-pattern-claims'; Expect = 'FAIL'; Sweep = 'tests';
       Why = 'a gate whose result no rule binds must red, not pass unswept';
       Edits = @(@{ Log = 'tests'; Anchor = '^CITATIONS (PASS|FAIL|VOID)$'; Action = 'replace';
                    Replacement = 'CITATIONS-EXTRA FAIL' }) },
    @{ Name = 'E9-twin-changes-the-same-verdicts-outcome-word'; Expect = 'PASS'; Sweep = 'tests';
       Why = 'inert twin: the same verdict line, a different outcome, still claimed by its named pattern';
       Edits = @(@{ Log = 'tests'; Anchor = '^CITATIONS (PASS|FAIL|VOID)$'; Action = 'replace';
                    Replacement = 'CITATIONS VOID' }) }
)

# The ROUND-3 rule, reimplemented here and nowhere else: a result is bound if
# any line matching ^invocation: appears since the PREVIOUS result. It lives in
# this runner rather than behind a flag in the checker, because production code
# carrying a mutation switch is a hazard - the same reason the harness keeps its
# mutants outside the plugin.
function Test-OldWindowRule {
    param([string[]]$Lines)

    $patterns = @('^roster-census-harness baselineRun=', '^CLAIMS (PASS|FAIL|VOID)',
                  '^SOURCE-CLAIM CONTROLS (PASS|FAIL)', '^SCAN (PASS|FAIL|VOID)',
                  '^TOKENS (PASS|FAIL|VOID)', '^SCAN CONTROLS (PASS|FAIL)',
                  '^EVIDENCE (PASS|FAIL|VOID)', '^EVIDENCE-LOG CONTROLS (PASS|FAIL)',
                  '^NOTES (PASS|FAIL|VOID)', '^(MATCH|MISMATCH) \|', '^(BOUND|UNBOUND) \|')

    $previous = -1
    $bound = 0
    $total = 0
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        $isResult = $false
        foreach ($p in $patterns) { if ($Lines[$i] -match $p) { $isResult = $true; break } }
        if (-not $isResult) { continue }
        $total = $total + 1
        for ($j = $previous + 1; $j -lt $i; $j++) {
            if ($Lines[$j] -match '^invocation:') { $bound = $bound + 1; break }
        }
        $previous = $i
    }
    return [pscustomobject]@{ Total = $total; Bound = $bound; Verdict = $(if ($total -gt 0 -and $bound -eq $total) { 'PASS' } else { 'FAIL' }) }
}

function Find-Anchor {
    param([string[]]$Lines, [string]$Anchor, [int]$Occurrence)
    $hits = @()
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        if ($Lines[$i] -match $Anchor) { $hits += $i }
    }
    if ($Occurrence -gt 0) {
        if ($hits.Count -lt $Occurrence) { return @{ Ok = $false; Count = $hits.Count } }
        return @{ Ok = $true; At = $hits[$Occurrence - 1]; Count = $hits.Count }
    }
    if ($hits.Count -ne 1) { return @{ Ok = $false; Count = $hits.Count } }
    return @{ Ok = $true; At = $hits[0]; Count = 1 }
}

Write-Output "=== evidence-log mutation controls ==="
Write-Output ("invocation:      " + [Environment]::CommandLine)
Write-Output ("invocation-utc:  " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ("tests-log:       " + $TestsLog)
Write-Output ("build-log:       " + $BuildLog)
Write-Output ""

Write-Output "--- baseline (the round's own logs: both sweeps must PASS) ---"
Write-Output "run: powershell -NoProfile -File check-evidence-log.ps1 -TestsLog <tests> -BuildLog <build> -Head <sha>"
# Indented: a nested verdict is not this section's result.
& powershell -NoProfile -ExecutionPolicy Bypass -File $Checker -TestsLog $TestsLog -BuildLog $BuildLog -Head $Head |
    Select-Object -Last 2 |
    ForEach-Object { Write-Output ('     | ' + $_) }
$baselineExit = $LASTEXITCODE
Write-Output ("baseline exit=" + $baselineExit + " expected=0")

Write-Output "run: powershell -NoProfile -File check-evidence-log.ps1 -TestsLog <build> -BuildLog <build> -Head <sha>"
& powershell -NoProfile -ExecutionPolicy Bypass -File $Checker -TestsLog $BuildLog -BuildLog $BuildLog -Head $Head |
    Select-Object -Last 2 |
    ForEach-Object { Write-Output ('     | ' + $_) }
$sweepExit = $LASTEXITCODE
Write-Output ("build-log sweep exit=" + $sweepExit + " expected=0")
Write-Output ""

$failures = 0
if ($baselineExit -ne 0) { $failures = $failures + 1 }
if ($sweepExit -ne 0) { $failures = $failures + 1 }

Write-Output "--- cases (each mutation must FAIL, each inert twin must PASS) ---"

foreach ($case in $cases) {
    $caseRoot = Join-Path $WorkDir $case.Name
    if (Test-Path -LiteralPath $caseRoot) { Remove-Item -LiteralPath $caseRoot -Recurse -Force }
    [void](New-Item -ItemType Directory -Path $caseRoot -Force)

    $testsCopy = Join-Path $caseRoot 'tests.log'
    $buildCopy = Join-Path $caseRoot 'build.log'
    Copy-Item -LiteralPath $TestsLog -Destination $testsCopy -Force
    Copy-Item -LiteralPath $BuildLog -Destination $buildCopy -Force

    $void = $false
    $applied = @()

    foreach ($edit in $case.Edits) {
        $target = if ($edit.Log -eq 'tests') { $testsCopy } else { $buildCopy }
        $lines = @(Get-Content -LiteralPath $target)
        $occurrence = 0
        if ($edit.ContainsKey('Occurrence')) { $occurrence = [int]$edit.Occurrence }

        $found = Find-Anchor -Lines $lines -Anchor $edit.Anchor -Occurrence $occurrence
        # An anchor that is absent or ambiguous means the edit did not land
        # where it says, and a mutation that changed nothing reads exactly like
        # one that was caught. Both are VOID, not a result.
        if (-not $found.Ok) {
            Write-Output ("VOID | case={0,-56} | anchor matched {1} line(s): {2}" -f $case.Name, $found.Count, $edit.Anchor)
            $void = $true
            break
        }

        $at = $found.At
        $before = $lines[$at]
        $out = New-Object System.Collections.ArrayList

        switch ($edit.Action) {
            'remove' {
                for ($i = 0; $i -lt $lines.Count; $i++) { if ($i -ne $at) { [void]$out.Add($lines[$i]) } }
            }
            'replace' {
                for ($i = 0; $i -lt $lines.Count; $i++) {
                    if ($i -eq $at) { [void]$out.Add($edit.Replacement) } else { [void]$out.Add($lines[$i]) }
                }
            }
            'respace-invocation' {
                # The SAME text after the key, with the spacing collapsed.
                # Nothing the check measures has been taken away.
                $tail = ($before -replace '^invocation:\s*', '')
                for ($i = 0; $i -lt $lines.Count; $i++) {
                    if ($i -eq $at) { [void]$out.Add('invocation: ' + $tail) } else { [void]$out.Add($lines[$i]) }
                }
            }
            'respace-hash' {
                $m = [System.Text.RegularExpressions.Regex]::Match($before, '([0-9a-fA-F]{64})')
                if (-not $m.Success) { $void = $true; break }
                for ($i = 0; $i -lt $lines.Count; $i++) {
                    if ($i -eq $at) { [void]$out.Add('sha256(' + $edit.Index + '):  ' + $m.Groups[1].Value) }
                    else { [void]$out.Add($lines[$i]) }
                }
            }
            'renumber-hash' {
                $rest = ($before -replace '^sha256\(\d+\):\s*', '')
                for ($i = 0; $i -lt $lines.Count; $i++) {
                    if ($i -eq $at) { [void]$out.Add('sha256(' + $edit.Index + '): ' + $rest) }
                    else { [void]$out.Add($lines[$i]) }
                }
            }
            'replace-hash-value' {
                $new = [System.Text.RegularExpressions.Regex]::Replace(
                    $before, '[0-9a-fA-F]{64}', $edit.Replacement)
                for ($i = 0; $i -lt $lines.Count; $i++) {
                    if ($i -eq $at) { [void]$out.Add($new) } else { [void]$out.Add($lines[$i]) }
                }
            }
            'upper-hash' {
                $m = [System.Text.RegularExpressions.Regex]::Match($before, '[0-9a-f]{64}')
                if (-not $m.Success) { $void = $true; break }
                $new = $before.Replace($m.Value, $m.Value.ToUpperInvariant())
                for ($i = 0; $i -lt $lines.Count; $i++) {
                    if ($i -eq $at) { [void]$out.Add($new) } else { [void]$out.Add($lines[$i]) }
                }
            }
            'insert-before-section' {
                # Walk UP from the anchor to its section header, and insert the
                # preparatory block above that header - so the anchor's own
                # section keeps its header and its command, and only a whole
                # extra section has appeared before it.
                $headerAt = -1
                for ($j = $at; $j -ge 0; $j--) {
                    if ($lines[$j] -match '^--- invocation') { $headerAt = $j; break }
                }
                if ($headerAt -lt 0) { $void = $true; break }
                for ($i = 0; $i -lt $lines.Count; $i++) {
                    if ($i -eq $headerAt) { foreach ($p in $preparatorySection) { [void]$out.Add($p) } }
                    [void]$out.Add($lines[$i])
                }
            }
            default {
                Write-Output ("VOID | case={0,-56} | unknown action {1}" -f $case.Name, $edit.Action)
                $void = $true
            }
        }

        if ($void) { break }

        $after = ($out -join "`r`n")
        # ORDINAL, not -eq. PowerShell's -eq on strings is case-INSENSITIVE, so
        # an edit that changes only case reads as an edit that changed nothing -
        # which voided the upper-case twin below, and would equally have voided
        # a case-only MUTATION that the checker had genuinely failed to catch.
        # The guard exists to separate "changed nothing" from "was caught"
        # (#712) and cannot do that while it is blind to part of the change.
        if ([string]::Equals($after, ($lines -join "`r`n"), [System.StringComparison]::Ordinal)) {
            Write-Output ("VOID | case={0,-56} | the edit changed nothing: {1}" -f $case.Name, $edit.Anchor)
            $void = $true
            break
        }
        [System.IO.File]::WriteAllText($target, $after)
        $applied += ("line {0} {1}: {2}" -f ($at + 1), $edit.Action, $before.Trim())
    }

    if ($void) { $failures = $failures + 1; continue }

    $sweepTarget = if ($case.Sweep -eq 'build') { $buildCopy } else { $testsCopy }

    & powershell -NoProfile -ExecutionPolicy Bypass -File $Checker `
        -TestsLog $sweepTarget -BuildLog $buildCopy -Head $Head > (Join-Path $caseRoot 'check.out') 2>&1
    $exit = $LASTEXITCODE
    $got = if ($exit -eq 0) { 'PASS' } else { 'FAIL' }
    $ok = ($got -eq $case.Expect)
    if (-not $ok) { $failures = $failures + 1 }

    Write-Output ("{0,-4} | case={1,-56} | sweep={2,-5} expected={3,-4} got={4,-4} exit={5} | {6}" -f `
        $(if ($ok) { 'ok' } else { 'BAD' }), $case.Name, $case.Sweep, $case.Expect, $got, $exit, $case.Why)
    foreach ($a in $applied) { Write-Output ("     | " + $a) }

    # What the ROUND-3 rule would have said about the same file. Printed only
    # where it is the point of the case, and it is a measurement, not a claim.
    if ($case.ContainsKey('OldRule') -and $case.OldRule) {
        $old = Test-OldWindowRule -Lines @(Get-Content -LiteralPath $sweepTarget)
        Write-Output ("     | the round-3 window rule over this same file: results={0} bound={1} verdict={2}" -f `
            $old.Total, $old.Bound, $old.Verdict)
    }

    # The rows the mutation actually reddened, so the credit goes to a NAMED
    # rule rather than to "something moved" (#712).
    if ($case.Expect -eq 'FAIL') {
        Get-Content -LiteralPath (Join-Path $caseRoot 'check.out') |
            Where-Object { $_ -like 'FAIL*' } |
            ForEach-Object { Write-Output ("     | reddened: " + $_) }
    }
}

Write-Output ""
Write-Output ("cases=" + $cases.Count + " failures=" + $failures)
if ($failures -gt 0) {
    Write-Output "EVIDENCE-LOG CONTROLS FAIL"
    exit 1
}
Write-Output "EVIDENCE-LOG CONTROLS PASS"
exit 0
