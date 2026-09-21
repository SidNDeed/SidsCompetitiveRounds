# Hashes the rebuild artifacts, compares them, and binds them to a commit.
#
# WHY THIS EXISTS
# ---------------
# The build log used to carry its two verdicts - that the rebuilds MATCHED, and
# that the artifact was BOUND to the commit - as free text the author typed
# under the numbers. Both happened to be true. Neither was a value any process
# had computed, and nothing downstream could tell the difference: the evidence
# check looked for a line beginning MATCH, which a keyboard produces as easily
# as a comparison does.
#
# Worse, the build log was the one log in the lane that could not be swept at
# all. The evidence check binds each RESULT line to the invocation printed above
# it, and the build log had no result line it recognised - so passing it to that
# check returned VOID rather than a verdict, and its two hand-written verdicts
# sat above no invocation of anything.
#
# So the verdicts are computed here, by a process that prints its own invocation
# above them. That makes them results in the sense the evidence check means, and
# makes the build log an ordinary sweepable log rather than an exception the
# notes had to apologise for.
#
# WHICH WAY THE UNHANDLED CASE FAILS (#276 / #430)
# ------------------------------------------------
# Every refusal here is loud and exits non-zero. An artifact that cannot be read,
# a hash that cannot be taken, a version string that is absent: each prints what
# it could not do and refuses. The one thing this must never do is print MATCH
# because it had nothing to compare - so fewer than two artifacts is a refusal,
# not a trivially satisfied comparison.

param(
    [Parameter(Mandatory = $true)][string[]]$Artifacts,
    [string]$Head = ''
)

$ErrorActionPreference = 'Stop'

Write-Output "=== roster-census artifact hash binding ==="
Write-Output ("invocation:     " + [Environment]::CommandLine)
Write-Output ("invocation-utc: " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ("artifacts:      " + $Artifacts.Count)
Write-Output ("head:           " + $(if ($Head -eq '') { '(not asserted)' } else { $Head }))
Write-Output ""

$failures = 0

# Two is the minimum that can demonstrate anything. One artifact compared with
# itself is not repeatability, and printing MATCH over it would be the claim
# this script exists to stop being typed by hand.
if ($Artifacts.Count -lt 2) {
    Write-Output ("REFUSED | {0} artifact(s) given; repeatability needs at least 2" -f $Artifacts.Count)
    exit 1
}

$hashes = New-Object System.Collections.ArrayList
for ($i = 0; $i -lt $Artifacts.Count; $i++) {
    $path = $Artifacts[$i]
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Output ("REFUSED | rebuild {0}: no such artifact: {1}" -f ($i + 1), $path)
        exit 1
    }
    $bytes = (Get-Item -LiteralPath $path).Length
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    [void]$hashes.Add($hash)
    Write-Output ("sha256({0}): {1}   bytes {2}" -f ($i + 1), $hash, $bytes)
}

$distinct = @($hashes | Sort-Object -Unique)

# The reference artifact for the commit binding is the LAST rebuild, because
# that is the one left on disk and the one every downstream scan reads.
$reference = $Artifacts[$Artifacts.Count - 1]
$product = ''
try { $product = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($reference).ProductVersion } catch { $product = '' }
if ([string]::IsNullOrWhiteSpace($product)) {
    Write-Output "REFUSED | the artifact carries no ProductVersion - the commit binding cannot be read"
    exit 1
}
Write-Output ("InformationalVersion: " + $product)
if ($Head -ne '') { Write-Output ("head:                 " + $Head) }
Write-Output ""

if ($distinct.Count -eq 1) {
    Write-Output ("MATCH | {0} of {0} rebuild artifacts share one sha256: {1}" -f $Artifacts.Count, $distinct[0])
} else {
    Write-Output ("MISMATCH | {0} rebuild artifacts produced {1} distinct sha256 values" -f `
        $Artifacts.Count, $distinct.Count)
    $failures = $failures + 1
}

if ($Head -eq '') {
    Write-Output "UNBOUND | no head was given, so the artifact is bound to no commit by this run"
    $failures = $failures + 1
} elseif ($product.Contains($Head)) {
    Write-Output ("BOUND | the artifact's InformationalVersion names the commit " + $Head)
} else {
    Write-Output ("UNBOUND | the artifact names {0}, which does not carry {1}" -f $product, $Head)
    $failures = $failures + 1
}

Write-Output ""
Write-Output ("artifacts=" + $Artifacts.Count + " distinctHashes=" + $distinct.Count + " failures=" + $failures)
if ($failures -gt 0) { exit 1 }
exit 0
