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
# WHY THERE IS A SALTED POSITIVE CONTROL
# --------------------------------------
# A scan that reports "absent" is worthless until it has been shown it can
# report "present" (#342). Every needle - including the ones that MUST be
# absent from the real DLL - is appended to a salted copy in both encodings, at
# a deliberately ODD offset, and the same scanner is run over that copy. If any
# needle goes unfound there, the scanner is broken and the whole scan is void,
# whatever it said about the real file.

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

# ---- the salted positive control ------------------------------------------
# Pad so the first salted needle starts at an ODD offset, which is exactly the
# case #157 says a naive UTF-16 reader cannot see.
$salt = New-Object System.Collections.Generic.List[byte]
$salt.AddRange($bytes)
if ((($salt.Count) % 2) -eq 0) { $salt.Add([byte]0x00) }
foreach ($needle in $needles) {
    foreach ($variant in (Get-Variants $needle.Text)) {
        $salt.AddRange($variant.Bytes)
        $salt.Add([byte]0x00)
    }
}

$realHay = $latin1.GetString($bytes)
$saltHay = $latin1.GetString($salt.ToArray())

$sha = (Get-FileHash -LiteralPath $Dll -Algorithm SHA256).Hash.ToLowerInvariant()

Write-Output "=== build marker scan ==="
Write-Output ("dll:    " + (Resolve-Path -LiteralPath $Dll).Path)
Write-Output ("bytes:  " + $bytes.Length)
Write-Output ("sha256: " + $sha)
Write-Output ("method: raw bytes mapped through Latin-1, case-insensitive, both UTF-16LE and UTF-8, any offset")
Write-Output ""

$failures = 0
$controlFailures = 0
$gated = 0

foreach ($needle in $needles) {
    foreach ($variant in (Get-Variants $needle.Text)) {
        $expect = $needle.Utf8
        if ($variant.Name -eq 'utf16le') { $expect = $needle.Utf16 }

        $foundReal = Test-Haystack -Haystack $realHay -NeedleBytes $variant.Bytes
        $foundSalt = Test-Haystack -Haystack $saltHay -NeedleBytes $variant.Bytes

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
        # is not allowed to report anything about it.
        $control = 'ok'
        if (-not $foundSalt) {
            $control = 'CONTROL-FAIL'
            $controlFailures = $controlFailures + 1
        }

        Write-Output ("{0,-4} | control={1,-12} | needle={2,-31} | enc={3,-7} | expect={4,-7} | actual={5,-7} | {6}" -f `
            $verdict, $control, $needle.Text, $variant.Name, $expect, $actual, $needle.Why)
    }
}

Write-Output ""
Write-Output ("needles=" + $needles.Count + " variants=" + ($needles.Count * 2) + " gatedVariants=" + $gated + " scanFailures=" + $failures + " controlFailures=" + $controlFailures)

if ($controlFailures -gt 0) {
    Write-Output "SCAN VOID | the salted control did not find every needle - the scanner cannot be trusted about the real file"
    exit 3
}
if ($failures -gt 0) {
    Write-Output "SCAN FAIL"
    exit 1
}
Write-Output "SCAN PASS"
exit 0
