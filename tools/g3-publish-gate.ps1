# G3 publish gate (connect-failure V11 sec5.1; control K46).
#
# ITS ONLY JOB: refuse a CompetitiveRounds.dll that carries the G3 build-variant
# marker, SCR_BUILD_VARIANT=G3, for EVERY publish destination (the desktop drop,
# a release asset). A G3 build advertises the admission capability before the
# production-enabling release; it reaches the five enrolled seats through a lane
# folder only, never through a publisher. Every publisher runs this gate as its
# first check and publishes nothing unless it exits 0.
#
# METHOD (the scanner's, tools/scan-build-markers.ps1): the raw bytes are mapped
# through Latin-1, a lossless byte-to-char mapping, and searched for the needle
# in UTF-16LE and in UTF-8 at ANY offset. Reading the file as UTF-16 from byte 0
# (Select-String -Encoding unicode, findstr) makes every wide string at an odd
# offset invisible (#157), so it is never used here.
#
# CONTROLS: an absence counts only after the scan has shown it can see the
# needle. Each encoding of the needle is planted in two salted copies of the
# DLL, at an ODD offset in one and an EVEN offset in the other; a control fires
# only when the planted bytes read back at the stated parity AND the search
# finds them in both copies. A sentinel planted nowhere must read absent in the
# DLL and in both copies; if it reads present the search matches
# indiscriminately and the scan is void.
#
# EXITS (every exit except 0 is a refusal):
#   0  the marker is absent and every control fired
#      [G3-GATE] pass dll={name} controls={n}
#   1  the marker is present            [G3-GATE] refused dll={name} why=marker
#   2  the file is missing              [G3-GATE] refused dll={name} why=missing
#   3  a control failed, or the sentinel read present (a void scan)
#                                       [G3-GATE] refused dll={name} why=void
#
# -SuppressControl utf16le|utf8 plants no copy of that encoding's control. It
# exists for K46's fixture (iv) only: the gate must then refuse as void.

param(
    [Parameter(Mandatory = $true)][string]$Dll,
    [ValidateSet('', 'utf16le', 'utf8')][string]$SuppressControl = ''
)

$ErrorActionPreference = 'Stop'

$name = [System.IO.Path]::GetFileName($Dll)
if (-not (Test-Path -LiteralPath $Dll -PathType Leaf)) {
    Write-Output ("[G3-GATE] refused dll=" + $name + " why=missing")
    exit 2
}

$bytes = [System.IO.File]::ReadAllBytes($Dll)
$latin1 = [System.Text.Encoding]::GetEncoding(28591)

$marker = 'SCR_BUILD_VARIANT=G3'
# Planted nowhere and present in no build; it exists only to be probed (#306).
$sentinel = 'SCR_G3_GATE_SENTINEL_NEVER_PLANTED_K46'

function Get-Variants {
    param([string]$Text)
    return @(
        @{ Name = 'utf16le'; Bytes = [System.Text.Encoding]::Unicode.GetBytes($Text) },
        @{ Name = 'utf8';    Bytes = [System.Text.Encoding]::UTF8.GetBytes($Text) }
    )
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
    foreach ($variant in (Get-Variants $marker)) {
        if ($variant.Name -eq $SuppressControl) { continue }
        # Padded per needle, so no needle inherits the previous one's parity.
        while (($salt.Count % 2) -ne $Parity) { $salt.Add([byte]0x00) }
        $planted[$variant.Name] = $salt.Count
        $salt.AddRange($variant.Bytes)
        $salt.Add([byte]0x00)
    }
    return [pscustomobject]@{ Bytes = $salt.ToArray(); Planted = $planted }
}

# The recorded offset is a claim; reading the bytes back makes it a reading.
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

$present = $false
$controls = 0
foreach ($variant in (Get-Variants $marker)) {
    if (Test-Haystack -Haystack $realHay -NeedleBytes $variant.Bytes) { $present = $true }
    $okOdd  = (Test-Planted -Haystack $oddSalt.Bytes  -Offset $oddSalt.Planted[$variant.Name]  -NeedleBytes $variant.Bytes -Parity 1) -and
              (Test-Haystack -Haystack $oddHay -NeedleBytes $variant.Bytes)
    $okEven = (Test-Planted -Haystack $evenSalt.Bytes -Offset $evenSalt.Planted[$variant.Name] -NeedleBytes $variant.Bytes -Parity 0) -and
              (Test-Haystack -Haystack $evenHay -NeedleBytes $variant.Bytes)
    if ($okOdd -and $okEven) { $controls = $controls + 1 }
}

$sentinelSeen = $false
foreach ($variant in (Get-Variants $sentinel)) {
    foreach ($hay in @($realHay, $oddHay, $evenHay)) {
        if (Test-Haystack -Haystack $hay -NeedleBytes $variant.Bytes) { $sentinelSeen = $true }
    }
}

if ($sentinelSeen) {
    Write-Output ("[G3-GATE] refused dll=" + $name + " why=void")
    exit 3
}
if ($present) {
    Write-Output ("[G3-GATE] refused dll=" + $name + " why=marker")
    exit 1
}
if ($controls -ne 2) {
    Write-Output ("[G3-GATE] refused dll=" + $name + " why=void")
    exit 3
}
Write-Output ("[G3-GATE] pass dll=" + $name + " controls=" + $controls)
exit 0
