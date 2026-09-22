# Does the BUILT artifact actually carry this round's census change?
#
# WHY THIS EXISTS
# ---------------
# Round 2 closes two findings by changing what a zero-seat boundary prints: the
# four causes stopped sharing one reason token. Nothing else in this lane's
# evidence binds that change to the DLL. The harness executes the rule from
# source; the marker scan is about the build gate and about privacy; and a
# deterministic build does not move its own hash when only comments change, so
# two matching hashes say nothing about which reason tokens are inside. An
# acceptance bar has to be a POSITIVE signal the change emits (#438), and this
# is it: the new tokens must be IN the assembly's literal heap, and the retired
# shared token must be OUT of it.
#
# SAME CONTROL DISCIPLINE AS THE MARKER SCAN
# ------------------------------------------
# Every needle is planted in two salted copies of the artifact, one at ODD
# offsets and one at EVEN offsets, in BOTH encodings, and a verdict is only
# reported for a needle whose control fired in both - because "absent" from a
# search that cannot see anything is not a reading (#342, #157). A sentinel
# planted in neither copy must read absent everywhere, which is what catches a
# search that answers "found" to everything.

param(
    [Parameter(Mandatory = $true)][string]$Dll
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Dll)) {
    Write-Output "TOKENS FAIL | no such file: $Dll"
    exit 2
}

$bytes = [System.IO.File]::ReadAllBytes($Dll)
$latin1 = [System.Text.Encoding]::GetEncoding(28591)
$utf16 = [System.Text.Encoding]::Unicode
$utf8 = [System.Text.Encoding]::UTF8

# Utf16 is the expectation that matters: a C# string literal lands in the #US
# heap and only there (#123). Utf8 is recorded as a note, never asserted, so
# this check makes no claim about heaps it does not control.
$needles = @(
    @{ Text = 'roster-read-threw';           Utf16 = 'present';
       Why = 'finding 1: a roster read that raised has its own token' },
    @{ Text = 'roster-list-null';            Utf16 = 'present';
       Why = 'finding 1: a read that returned no list has its own token' },
    @{ Text = 'roster-read-empty';           Utf16 = 'present';
       Why = 'finding 1: a room that really held no actors has its own token' },
    @{ Text = 'every-actor-is-a-spectator';  Utf16 = 'present';
       Why = 'finding 1: an all-spectator roster has its own token' },
    @{ Text = 'roster-empty-unclassified';   Utf16 = 'present';
       Why = 'findings 1-2: the unclassified cause fails toward saying something true' },
    @{ Text = 'roster-entry-null';           Utf16 = 'present';
       Why = 'round-3 finding 1: a null roster entry has its own token instead of being skipped' },
    @{ Text = 'roster-seats-present';        Utf16 = 'present';
       Why = 'round-3 finding 1: the observation mapping is total, so the seats-present arm is a token too' },
    @{ Text = 'SCR_ROSTER_PROBE=1';          Utf16 = 'present';
       Why = 'the census probe token is still in the build (#306)' },
    @{ Text = 'roster-read-failed';          Utf16 = 'absent';
       Why = 'finding 1: the RETIRED shared token, which a thrown read and a null list used to share' }
)

$sentinel = 'SCR_TOKEN_SENTINEL_NEVER_PLANTED_K3WD'

function Get-Variants {
    param([string]$Text)
    $out = New-Object System.Collections.ArrayList
    [void]$out.Add(@{ Name = 'utf16le'; Bytes = $utf16.GetBytes($Text) })
    [void]$out.Add(@{ Name = 'utf8';    Bytes = $utf8.GetBytes($Text) })
    return $out
}

function Test-Haystack {
    param([string]$Haystack, [byte[]]$NeedleBytes)
    $probe = $latin1.GetString($NeedleBytes)
    return ($Haystack.IndexOf($probe, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
}

function New-SaltedCopy {
    param([byte[]]$Base, [int]$Parity)
    $salt = New-Object System.Collections.Generic.List[byte]
    $salt.AddRange($Base)
    $planted = @{}
    foreach ($needle in $needles) {
        foreach ($variant in (Get-Variants $needle.Text)) {
            while ((($salt.Count) % 2) -ne $Parity) { $salt.Add([byte]0x00) }
            $planted[($needle.Text + '|' + $variant.Name)] = $salt.Count
            $salt.AddRange($variant.Bytes)
            $salt.Add([byte]0x00)
        }
    }
    return [pscustomobject]@{ Bytes = $salt.ToArray(); Planted = $planted }
}

function Test-Planted {
    param([byte[]]$Haystack, $Offset, [byte[]]$NeedleBytes, [int]$Parity)
    if ($null -eq $Offset) { return $false }
    $at = [int]$Offset
    if (($at % 2) -ne $Parity) { return $false }
    if ($at -lt 0 -or ($at + $NeedleBytes.Length) -gt $Haystack.Length) { return $false }
    for ($i = 0; $i -lt $NeedleBytes.Length; $i++) {
        if ($Haystack[$at + $i] -ne $NeedleBytes[$i]) { return $false }
    }
    return $true
}

$oddSalt  = New-SaltedCopy -Base $bytes -Parity 1
$evenSalt = New-SaltedCopy -Base $bytes -Parity 0

$realHay = $latin1.GetString($bytes)
$oddHay  = $latin1.GetString($oddSalt.Bytes)
$evenHay = $latin1.GetString($evenSalt.Bytes)

$sha = (Get-FileHash -LiteralPath $Dll -Algorithm SHA256).Hash.ToLowerInvariant()

Write-Output "=== census token check ==="
# Self-printed, for the same reason as the marker scan: a verdict with no
# invocation above it is not bound to the run that produced it.
Write-Output ("invocation:     " + [Environment]::CommandLine)
Write-Output ("invocation-utc: " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ("dll:      " + (Resolve-Path -LiteralPath $Dll).Path)
Write-Output ("bytes:    " + $bytes.Length)
Write-Output ("sha256:   " + $sha)
Write-Output ("sentinel: " + $sentinel + " - planted in neither copy, must read absent everywhere")
Write-Output ""

$failures = 0
$controlFailures = 0
$gated = 0
$controlsFired = 0

foreach ($needle in $needles) {
    foreach ($variant in (Get-Variants $needle.Text)) {
        $expect = 'any'
        if ($variant.Name -eq 'utf16le') { $expect = $needle.Utf16 }

        $key = $needle.Text + '|' + $variant.Name
        $oddOffset  = $oddSalt.Planted[$key]
        $evenOffset = $evenSalt.Planted[$key]

        $foundReal = Test-Haystack -Haystack $realHay -NeedleBytes $variant.Bytes
        $foundOdd  = Test-Haystack -Haystack $oddHay  -NeedleBytes $variant.Bytes
        $foundEven = Test-Haystack -Haystack $evenHay -NeedleBytes $variant.Bytes

        $plantedOdd  = Test-Planted -Haystack $oddSalt.Bytes  -Offset $oddOffset  -NeedleBytes $variant.Bytes -Parity 1
        $plantedEven = Test-Planted -Haystack $evenSalt.Bytes -Offset $evenOffset -NeedleBytes $variant.Bytes -Parity 0

        $actual = 'absent'
        if ($foundReal) { $actual = 'present' }

        $verdict = 'ok'
        if ($expect -eq 'any') {
            $verdict = 'note'
        }
        else {
            $gated = $gated + 1
            if ($actual -ne $expect) {
                $verdict = 'FAIL'
                $failures = $failures + 1
            }
        }

        $control = 'ok'
        if ($plantedOdd -and $plantedEven -and $foundOdd -and $foundEven) {
            $controlsFired = $controlsFired + 1
        }
        else {
            $control = 'CONTROL-FAIL'
            $controlFailures = $controlFailures + 1
        }

        Write-Output ("{0,-4} | control={1,-12} | odd@{2,-9} even@{3,-9} | needle={4,-27} | enc={5,-7} | expect={6,-7} | actual={7,-7} | {8}" -f `
            $verdict, $control, $oddOffset, $evenOffset, $needle.Text, $variant.Name, $expect, $actual, $needle.Why)
    }
}

$sentinelFailures = 0
foreach ($variant in (Get-Variants $sentinel)) {
    $inReal = Test-Haystack -Haystack $realHay -NeedleBytes $variant.Bytes
    $inOdd  = Test-Haystack -Haystack $oddHay  -NeedleBytes $variant.Bytes
    $inEven = Test-Haystack -Haystack $evenHay -NeedleBytes $variant.Bytes
    $clean = (-not $inReal) -and (-not $inOdd) -and (-not $inEven)
    if (-not $clean) { $sentinelFailures = $sentinelFailures + 1 }
    Write-Output ("{0,-4} | sentinel     | never planted        | enc={1,-7} | real={2,-5} | oddSalt={3,-5} | evenSalt={4,-5}" -f `
        $(if ($clean) { 'ok' } else { 'FAIL' }), $variant.Name, $inReal, $inOdd, $inEven)
}

Write-Output ""
Write-Output ("needles=" + $needles.Count + " variants=" + ($needles.Count * 2) + " gatedVariants=" + $gated `
    + " controlsFired=" + $controlsFired + " tokenFailures=" + $failures + " controlFailures=" + $controlFailures `
    + " sentinelFailures=" + $sentinelFailures)

if ($controlFailures -gt 0) {
    Write-Output "TOKENS VOID | a salted control did not fire at both alignments"
    exit 3
}
if ($sentinelFailures -gt 0) {
    Write-Output "TOKENS VOID | the sentinel was reported found - the search is matching indiscriminately"
    exit 3
}
if ($controlsFired -ne ($needles.Count * 2)) {
    Write-Output "TOKENS VOID | fewer controls fired than there are variants"
    exit 3
}
if ($failures -gt 0) {
    Write-Output "TOKENS FAIL"
    exit 1
}
Write-Output "TOKENS PASS"
exit 0
