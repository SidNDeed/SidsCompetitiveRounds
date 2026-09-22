# Byte-level marker scan for a built CompetitiveRounds.dll.
#
# WHY IT SCANS BYTES AND NOT TEXT
# -------------------------------
# `Select-String -Encoding unicode` reads the file as UTF-16 from byte 0, so an
# odd-offset #US heap makes every wide string invisible and an UNGATED build
# reads clean (#157). `findstr` fails the same way. This script maps the raw
# bytes through Latin-1 - a lossless byte-to-char mapping - and searches that,
# so a needle is found at ANY offset, odd or even, in either encoding.
#
# WHY THERE ARE SALTED POSITIVE CONTROLS AT BOTH ALIGNMENTS
# ---------------------------------------------------------
# A scan that reports "absent" is worthless until it has been shown it can
# report "present" (#342). Every needle - including the ones that MUST be
# absent from the real DLL - is planted in a salted copy in both encodings and
# the same scanner is run over that copy; if any needle goes unfound there the
# scanner is broken and the whole scan is void, whatever it said about the real
# file.
#
# ONE PAD AT THE FRONT IS NOT ENOUGH. It fixes only the FIRST needle's
# alignment: every needle after it starts wherever the running length happens
# to land, so the later UTF-8 and UTF-16LE controls can all be EVEN-aligned and
# the odd-offset case #157 is actually about then goes untested. Each needle is
# therefore padded INDIVIDUALLY into TWO salted copies - one in which every
# needle starts at an ODD offset, one in which every needle starts at an EVEN
# offset - and a control counts as fired only when the scanner finds the needle
# in BOTH, at an offset whose parity was verified by reading the bytes back.
#
# WHY THERE IS ALSO A SENTINEL
# ----------------------------
# A control that only ever fires proves nothing about a scanner that answers
# "found" to everything. The sentinel is a token planted in NEITHER salted copy
# and present in no build - it exists for no other purpose than to be probed
# (#306) - and it must read ABSENT in the real file and in both salts. If it
# reads present anywhere, every "present" above it is worthless and the scan is
# void.

param(
    [Parameter(Mandatory = $true)][string]$Dll
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Dll)) {
    Write-Output "SCAN FAIL | no such file: $Dll"
    exit 2
}

$bytes = [System.IO.File]::ReadAllBytes($Dll)
$latin1 = [System.Text.Encoding]::GetEncoding(28591)
$utf16 = [System.Text.Encoding]::Unicode
$utf8 = [System.Text.Encoding]::UTF8

# Each needle carries a PER-ENCODING expectation, because the two encodings are
# two different heaps and mean different things (#123):
#
#   utf16le  the #US literal heap. A C# string literal lands here and only
#            here, so this is where the build-variant marker must be found.
#   utf8     the #Strings heap (type and member names) and the PE directories,
#            including the debug directory a PDB path would leak through. A
#            local path can reach the file by EITHER route, so every privacy
#            needle is gated on both; the variant marker is a literal, is not a
#            type name, and is therefore not expected here - 'any' records that
#            rather than asserting a fact about the compiler's heaps.
$needles = @(
    @{ Text = 'SCR_BUILD_VARIANT=STANDALONE';    Utf16 = 'present'; Utf8 = 'any';    Why = 'build gate: this is the standalone variant' },
    @{ Text = 'SCR_BUILD_VARIANT=THUNDERSTORE';  Utf16 = 'absent';  Utf8 = 'absent'; Why = 'build gate: the Thunderstore variant must not be in this build' },
    @{ Text = 'C:\Users';                        Utf16 = 'absent';  Utf8 = 'absent'; Why = 'privacy: local user directory, backslash spelling' },
    @{ Text = 'C:/Users';                        Utf16 = 'absent';  Utf8 = 'absent'; Why = 'privacy: local user directory, forward-slash spelling' },
    @{ Text = 'C:\\Users';                       Utf16 = 'absent';  Utf8 = 'absent'; Why = 'privacy: local user directory, escaped-backslash spelling' },
    @{ Text = '\Users\';                         Utf16 = 'absent';  Utf8 = 'absent'; Why = 'privacy: any users path segment, backslash spelling' },
    @{ Text = '/Users/';                         Utf16 = 'absent';  Utf8 = 'absent'; Why = 'privacy: any users path segment, forward-slash spelling' },
    @{ Text = 'Documents\SidsCompetitiveRounds'; Utf16 = 'absent';  Utf8 = 'absent'; Why = 'privacy: this checkout path, backslash spelling' },
    @{ Text = 'Documents/SidsCompetitiveRounds'; Utf16 = 'absent';  Utf8 = 'absent'; Why = 'privacy: this checkout path, forward-slash spelling' },
    @{ Text = 'scr-wt-bug391-client';            Utf16 = 'absent';  Utf8 = 'absent'; Why = 'privacy: this worktree directory name' }
)

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

# The sentinel: planted nowhere, expected absent everywhere. See the header.
$sentinel = 'SCR_SCAN_SENTINEL_NEVER_PLANTED_Q7XV'

# ---- the salted positive controls, one copy per alignment -------------------

function New-SaltedCopy {
    param([byte[]]$Base, [int]$Parity)

    $salt = New-Object System.Collections.Generic.List[byte]
    $salt.AddRange($Base)
    $planted = @{}

    foreach ($needle in $needles) {
        foreach ($variant in (Get-Variants $needle.Text)) {
            # Pad THIS needle to the wanted parity. Recomputed per needle, so
            # no needle inherits the alignment the previous one happened to
            # leave behind.
            while ((($salt.Count) % 2) -ne $Parity) { $salt.Add([byte]0x00) }
            $planted[($needle.Text + '|' + $variant.Name)] = $salt.Count
            $salt.AddRange($variant.Bytes)
            # A separator, so two planted needles cannot run together into a
            # third string that was never planted.
            $salt.Add([byte]0x00)
        }
    }

    return [pscustomobject]@{ Bytes = $salt.ToArray(); Planted = $planted }
}

# Reads the planted bytes back. The recorded offset is a CLAIM about where the
# needle went; this is what turns it into a reading, and it is also what fails
# if the padding above ever stops doing its job.
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

Write-Output "=== build marker scan ==="
# THE INVOCATION, PRINTED BY THE PROCESS ABOUT ITSELF, ABOVE THE RESULTS. A
# verdict with no invocation above it is a number a reader cannot bind to the
# run that produced it, and check-evidence-log.ps1 rejects exactly that.
Write-Output ("invocation:     " + [Environment]::CommandLine)
Write-Output ("invocation-utc: " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ("dll:    " + (Resolve-Path -LiteralPath $Dll).Path)
Write-Output ("bytes:  " + $bytes.Length)
Write-Output ("sha256: " + $sha)
Write-Output ("method: raw bytes mapped through Latin-1, case-insensitive, both UTF-16LE and UTF-8, any offset")
Write-Output ("control: every variant planted at an ODD and at an EVEN offset in two salted copies; both must be found")
Write-Output ("sentinel: " + $sentinel + " - planted in neither copy, must read absent everywhere")
Write-Output ""

$failures = 0
$controlFailures = 0
$gated = 0
$controlsFired = 0

foreach ($needle in $needles) {
    foreach ($variant in (Get-Variants $needle.Text)) {
        $expect = $needle.Utf8
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

        # The control is asserted for EVERY variant, including the ones whose
        # real-file reading is only a note: a scanner that cannot see a needle
        # is not allowed to report anything about it. All four legs must hold -
        # planted at the stated ODD offset, planted at the stated EVEN offset,
        # and FOUND by the same search in each copy - so no absent verdict on
        # this line rests on a control that did not actually fire.
        $control = 'ok'
        if ($plantedOdd -and $plantedEven -and $foundOdd -and $foundEven) {
            $controlsFired = $controlsFired + 1
        }
        else {
            $control = 'CONTROL-FAIL'
            $controlFailures = $controlFailures + 1
        }

        Write-Output ("{0,-4} | control={1,-12} | odd@{2,-9} even@{3,-9} | needle={4,-31} | enc={5,-7} | expect={6,-7} | actual={7,-7} | {8}" -f `
            $verdict, $control, $oddOffset, $evenOffset, $needle.Text, $variant.Name, $expect, $actual, $needle.Why)

        if ($control -eq 'CONTROL-FAIL') {
            Write-Output ("     | control detail: plantedOdd=" + $plantedOdd + " plantedEven=" + $plantedEven `
                + " foundOdd=" + $foundOdd + " foundEven=" + $foundEven)
        }
    }
}

# ---- the sentinel: the control ON the controls ------------------------------
$sentinelFailures = 0
foreach ($variant in (Get-Variants $sentinel)) {
    $inReal = Test-Haystack -Haystack $realHay -NeedleBytes $variant.Bytes
    $inOdd  = Test-Haystack -Haystack $oddHay  -NeedleBytes $variant.Bytes
    $inEven = Test-Haystack -Haystack $evenHay -NeedleBytes $variant.Bytes
    $clean = (-not $inReal) -and (-not $inOdd) -and (-not $inEven)
    if (-not $clean) { $sentinelFailures = $sentinelFailures + 1 }
    Write-Output ("{0,-4} | sentinel     | never planted           | enc={1,-7} | real={2,-5} | oddSalt={3,-5} | evenSalt={4,-5}" -f `
        $(if ($clean) { 'ok' } else { 'FAIL' }), $variant.Name, $inReal, $inOdd, $inEven)
}

Write-Output ""
Write-Output ("needles=" + $needles.Count + " variants=" + ($needles.Count * 2) + " gatedVariants=" + $gated `
    + " controlsFired=" + $controlsFired + " scanFailures=" + $failures + " controlFailures=" + $controlFailures `
    + " sentinelFailures=" + $sentinelFailures)

if ($controlFailures -gt 0) {
    Write-Output "SCAN VOID | a salted control did not fire at both alignments - the scanner cannot be trusted about the real file"
    exit 3
}
if ($sentinelFailures -gt 0) {
    Write-Output "SCAN VOID | the sentinel was reported found - the search is matching indiscriminately and every present verdict is worthless"
    exit 3
}
if ($controlsFired -ne ($needles.Count * 2)) {
    Write-Output "SCAN VOID | fewer controls fired than there are variants - a variant was scanned with no control behind it"
    exit 3
}
if ($failures -gt 0) {
    Write-Output "SCAN FAIL"
    exit 1
}
Write-Output "SCAN PASS"
exit 0
