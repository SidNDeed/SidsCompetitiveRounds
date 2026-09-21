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
# and an INERT TWIN - an edit to the SAME line that leaves the property intact
# - that must keep it PASSING.
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

# Each case names the log it edits, a regex that must match EXACTLY ONE line in
# it, what happens to that line ('remove' or a replacement string built from the
# match), and whether the checker must pass afterwards.
$cases = @(
    @{ Name = 'E1-removes-the-harness-self-printed-invocation'; Expect = 'FAIL'; Log = 'tests';
       Anchor = '^invocation:\s+\S*roster-census-harness\.dll'; Action = 'remove';
       Why = 'round-3 finding 3: removing the invocation line must change a verdict' },
    @{ Name = 'E1-twin-rewords-the-same-invocation-line'; Expect = 'PASS'; Log = 'tests';
       Anchor = '^invocation:\s+\S*roster-census-harness\.dll'; Action = 'reword';
       Replacement = 'invocation:     <harness path, reworded by the inert twin>';
       Why = 'inert twin: the same line, reworded, still binds the result to a process' },

    @{ Name = 'E2-removes-the-echoed-harness-command'; Expect = 'FAIL'; Log = 'tests';
       Anchor = '^\$ dotnet tools/roster-census-harness/bin/'; Action = 'remove';
       Why = 'round-3 finding 3: a section header whose command is gone must red, not fall back on a neighbour' },
    @{ Name = 'E2-twin-rewords-the-same-echoed-command'; Expect = 'PASS'; Log = 'tests';
       Anchor = '^\$ dotnet tools/roster-census-harness/bin/'; Action = 'reword';
       Replacement = '$ dotnet tools/roster-census-harness/bin/Release/net10.0/roster-census-harness.dll --quiet';
       Why = 'inert twin: the same command line, reworded, still says how it was started' },

    @{ Name = 'E3-removes-the-second-build-hash'; Expect = 'FAIL'; Log = 'build';
       Anchor = '^sha256\(2\):'; Action = 'remove';
       Why = 'round-3 finding 3: removing the second hash must change a verdict' },
    @{ Name = 'E3-twin-reformats-the-same-hash-line'; Expect = 'PASS'; Log = 'build';
       Anchor = '^sha256\(2\):'; Action = 'respace';
       Why = 'inert twin: the same hash, respaced, still demonstrates repeatability' }
)

Write-Output "=== evidence-log mutation controls ==="
Write-Output ("invocation:      " + [Environment]::CommandLine)
Write-Output ("invocation-utc:  " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ("tests-log:       " + $TestsLog)
Write-Output ("build-log:       " + $BuildLog)
Write-Output ""

Write-Output "--- baseline (the round's own logs: must PASS) ---"
Write-Output "run: powershell -NoProfile -File check-evidence-log.ps1 -TestsLog <tests> -BuildLog <build> -Head <sha>"
# Indented: a nested verdict is not this section's result.
& powershell -NoProfile -ExecutionPolicy Bypass -File $Checker -TestsLog $TestsLog -BuildLog $BuildLog -Head $Head |
    Select-Object -Last 2 |
    ForEach-Object { Write-Output ('     | ' + $_) }
$baselineExit = $LASTEXITCODE
Write-Output ("baseline exit=" + $baselineExit + " expected=0")
Write-Output ""

$failures = 0
if ($baselineExit -ne 0) { $failures = $failures + 1 }

Write-Output "--- cases (each mutation must FAIL, each inert twin must PASS) ---"

foreach ($case in $cases) {
    $caseRoot = Join-Path $WorkDir $case.Name
    if (Test-Path -LiteralPath $caseRoot) { Remove-Item -LiteralPath $caseRoot -Recurse -Force }
    [void](New-Item -ItemType Directory -Path $caseRoot -Force)

    $testsCopy = Join-Path $caseRoot 'tests.log'
    $buildCopy = Join-Path $caseRoot 'build.log'
    Copy-Item -LiteralPath $TestsLog -Destination $testsCopy -Force
    Copy-Item -LiteralPath $BuildLog -Destination $buildCopy -Force

    $target = if ($case.Log -eq 'tests') { $testsCopy } else { $buildCopy }
    $lines = @(Get-Content -LiteralPath $target)

    $hits = @()
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $case.Anchor) { $hits += $i }
    }

    # An anchor that is absent or ambiguous means the edit did not land where it
    # says, and a mutation that changed nothing reads exactly like one that was
    # caught. Both are VOID, not a result.
    if ($hits.Count -ne 1) {
        Write-Output ("VOID | case={0,-48} | anchor matched {1} line(s), expected 1" -f $case.Name, $hits.Count)
        $failures = $failures + 1
        continue
    }

    $at = $hits[0]
    $before = $lines[$at]
    $out = New-Object System.Collections.ArrayList

    if ($case.Action -eq 'remove') {
        for ($i = 0; $i -lt $lines.Count; $i++) { if ($i -ne $at) { [void]$out.Add($lines[$i]) } }
    }
    elseif ($case.Action -eq 'reword') {
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($i -eq $at) { [void]$out.Add($case.Replacement) } else { [void]$out.Add($lines[$i]) }
        }
    }
    elseif ($case.Action -eq 'respace') {
        # The SAME hash value, written with different spacing and no trailing
        # byte count. Nothing the check measures has been taken away.
        $m = [System.Text.RegularExpressions.Regex]::Match($before, '([0-9a-fA-F]{64})')
        if (-not $m.Success) {
            Write-Output ("VOID | case={0,-48} | the anchor line carries no hash to respace" -f $case.Name)
            $failures = $failures + 1
            continue
        }
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($i -eq $at) { [void]$out.Add('sha256(2):  ' + $m.Groups[1].Value) } else { [void]$out.Add($lines[$i]) }
        }
    }
    else {
        Write-Output ("VOID | case={0,-48} | unknown action {1}" -f $case.Name, $case.Action)
        $failures = $failures + 1
        continue
    }

    $after = ($out -join "`r`n")
    if ($after -eq ($lines -join "`r`n")) {
        Write-Output ("VOID | case={0,-48} | the edit changed nothing" -f $case.Name)
        $failures = $failures + 1
        continue
    }
    [System.IO.File]::WriteAllText($target, $after)

    & powershell -NoProfile -ExecutionPolicy Bypass -File $Checker `
        -TestsLog $testsCopy -BuildLog $buildCopy -Head $Head > (Join-Path $caseRoot 'check.out') 2>&1
    $exit = $LASTEXITCODE
    $got = if ($exit -eq 0) { 'PASS' } else { 'FAIL' }
    $ok = ($got -eq $case.Expect)
    if (-not $ok) { $failures = $failures + 1 }

    Write-Output ("{0,-4} | case={1,-48} | expected={2,-4} got={3,-4} exit={4} | {5}" -f `
        $(if ($ok) { 'ok' } else { 'BAD' }), $case.Name, $case.Expect, $got, $exit, $case.Why)
    Write-Output ("     | line {0} before: {1}" -f ($at + 1), $before.Trim())

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
