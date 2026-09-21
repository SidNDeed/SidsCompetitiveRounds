# Mutation controls for tools/scan-build-markers.ps1.
#
# The scanner's own salted controls prove it can SEE a needle. They do not
# prove that the two alignment legs are load-bearing, or that the sentinel is
# doing anything - a scanner rewritten to answer "found" to everything would
# still print a page of ok rows. So each site below carries a PAIR: a mutation
# that must turn the scan VOID or FAIL, and an INERT TWIN on the same line that
# must keep it PASSING.
#
# Nothing here touches the worktree copy of the scanner: each case works from a
# fresh copy in a temporary directory, so no restore of a dirty tree is ever
# needed (#290 / #401).

param(
    [Parameter(Mandatory = $true)][string]$Dll,
    [string]$Scanner = '',
    [string]$WorkDir = ''
)

$ErrorActionPreference = 'Stop'

# Resolved in the BODY, not in a param default: with a Mandatory parameter in
# the same block, $PSScriptRoot is not yet populated when the defaults are
# evaluated on this host, and the failure is a bind error a long way from its
# cause.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrEmpty($Scanner)) {
    $Scanner = (Resolve-Path -LiteralPath (Join-Path (Join-Path $here '..') 'scan-build-markers.ps1')).Path
}
if ([string]::IsNullOrEmpty($WorkDir)) {
    $WorkDir = Join-Path ([System.IO.Path]::GetTempPath()) 'scr-r2-scan-controls'
}

$padLine  = '            while ((($salt.Count) % 2) -ne $Parity) { $salt.Add([byte]0x00) }'
$findLine = '    return ($Haystack.IndexOf($probe, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)'
$oddLine  = '$oddSalt  = New-SaltedCopy -Base $bytes -Parity 1'
$evenLine = '$evenSalt = New-SaltedCopy -Base $bytes -Parity 0'

$cases = @(
    @{ Name = 'S1-drops-the-per-needle-padding'; Expect = 'BAD'; Find = $padLine;
       Into = '            if ($false) { $salt.Add([byte]0x00) }';
       Why  = 'finding 5: without per-needle padding the planted offsets have no chosen parity' },
    @{ Name = 'S1-twin-pads-with-a-different-byte'; Expect = 'GOOD'; Find = $padLine;
       Into = '            while ((($salt.Count) % 2) -ne $Parity) { $salt.Add([byte]0x20) }';
       Why  = 'inert twin: the same line, a different filler, the same alignment' },

    @{ Name = 'S2-makes-the-search-answer-found-always'; Expect = 'BAD'; Find = $findLine;
       Into = '    return $true';
       Why  = 'the sentinel is what catches a search that matches indiscriminately' },
    @{ Name = 'S2-twin-rewrites-the-same-comparison'; Expect = 'GOOD'; Find = $findLine;
       Into = '    return ($Haystack.IndexOf($probe, [System.StringComparison]::OrdinalIgnoreCase) -gt -1)';
       Why  = 'inert twin: the same line, the same comparison spelled differently' },

    @{ Name = 'S3-builds-the-odd-salt-at-even-parity'; Expect = 'BAD'; Find = $oddLine;
       Into = '$oddSalt  = New-SaltedCopy -Base $bytes -Parity 0';
       Why  = 'finding 5: the ODD alignment leg must be load-bearing (#157)' },
    @{ Name = 'S3-twin-reorders-the-same-arguments'; Expect = 'GOOD'; Find = $oddLine;
       Into = '$oddSalt  = New-SaltedCopy -Parity 1 -Base $bytes';
       Why  = 'inert twin: the same call, arguments named in the other order' },

    @{ Name = 'S4-builds-the-even-salt-at-odd-parity'; Expect = 'BAD'; Find = $evenLine;
       Into = '$evenSalt = New-SaltedCopy -Base $bytes -Parity 1';
       Why  = 'finding 5: the EVEN alignment leg must be load-bearing too' },
    @{ Name = 'S4-twin-reorders-the-same-arguments'; Expect = 'GOOD'; Find = $evenLine;
       Into = '$evenSalt = New-SaltedCopy -Parity 0 -Base $bytes';
       Why  = 'inert twin: the same call, arguments named in the other order' }
)

Write-Output "=== build-marker scan mutation controls ==="
Write-Output ("invocation:     " + [Environment]::CommandLine)
Write-Output ("invocation-dll: " + (Resolve-Path -LiteralPath $Dll).Path)
Write-Output ("invocation-utc: " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ""

Write-Output "--- baseline (the scanner as it stands: must PASS, exit 0) ---"
& powershell -NoProfile -ExecutionPolicy Bypass -File $Scanner -Dll $Dll | Select-Object -Last 3
$baselineExit = $LASTEXITCODE
Write-Output ("baseline exit=" + $baselineExit + " expected=0")
Write-Output ""

$failures = 0
if ($baselineExit -ne 0) { $failures = $failures + 1 }

$scannerText = [System.IO.File]::ReadAllText($Scanner)

Write-Output "--- cases (each mutation must stop the scan, each inert twin must not) ---"

if (-not (Test-Path -LiteralPath $WorkDir)) { [void](New-Item -ItemType Directory -Path $WorkDir -Force) }

foreach ($case in $cases) {
    $hits = 0
    $i = 0
    while ($true) {
        $i = $scannerText.IndexOf($case.Find, $i, [System.StringComparison]::Ordinal)
        if ($i -lt 0) { break }
        $hits = $hits + 1
        $i = $i + 1
    }
    if ($hits -ne 1) {
        Write-Output ("VOID | case={0,-42} | anchor occurs {1} times, expected 1" -f $case.Name, $hits)
        $failures = $failures + 1
        continue
    }

    $mutated = $scannerText.Replace($case.Find, $case.Into)
    if ($mutated -eq $scannerText) {
        Write-Output ("VOID | case={0,-42} | the edit changed nothing" -f $case.Name)
        $failures = $failures + 1
        continue
    }

    $path = Join-Path $WorkDir ($case.Name + '.ps1')
    [System.IO.File]::WriteAllText($path, $mutated)

    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $path -Dll $Dll 2>&1
    $exit = $LASTEXITCODE
    $got = if ($exit -eq 0) { 'GOOD' } else { 'BAD' }
    $ok = ($got -eq $case.Expect)
    if (-not $ok) { $failures = $failures + 1 }

    $verdictLine = ($out | Where-Object { $_ -like 'SCAN *' } | Select-Object -Last 1)

    Write-Output ("{0,-4} | case={1,-42} | expected={2,-4} got={3,-4} exit={4} | {5}" -f `
        $(if ($ok) { 'ok' } else { 'BAD ' }), $case.Name, $case.Expect, $got, $exit, $case.Why)
    Write-Output ("     | verdict: " + $verdictLine)
}

Write-Output ""
Write-Output ("cases=" + $cases.Count + " failures=" + $failures)
if ($failures -gt 0) {
    Write-Output "SCAN CONTROLS FAIL"
    exit 1
}
Write-Output "SCAN CONTROLS PASS"
exit 0
