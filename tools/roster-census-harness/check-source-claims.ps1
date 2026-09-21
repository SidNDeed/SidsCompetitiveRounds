# Source-claim check for the roster-census lane.
#
# WHY THIS EXISTS
# ---------------
# Some of this lane's closures are CLAIMS rather than behaviour: remarks about
# what a settled sample does and does not assert, and remarks that said every
# helper tests something only some of them test. A claim asserted about the
# source and never run is exactly the shape #391 rejects, so each of those
# claims is turned into a row here that a mutation can redden.
#
# WHAT REPLACED THE FORBIDDEN-PHRASE LIST, AND WHY
# ------------------------------------------------
# Round 2 policed the settled sample's interpretation with a list of FORBIDDEN
# phrases. That is a check that cannot fail (#342 / #431): it rejects the two
# spellings someone thought of and accepts every other one, and a remark saying
# equal snapshots prove no move passed it untouched while the check reported
# success. A blacklist can only ever name what it has already seen.
#
# The rule here is an ALLOW-LIST instead, in two parts, and it is judged by what
# it makes impossible rather than by what it forbids:
#
#   1. THE REGION. Each sample site carries exactly ONE interpretation
#      sentence, between SCR_CENSUS_MOVE_CLAIM_BEGIN and
#      SCR_CENSUS_MOVE_CLAIM_END. Those markers exist for no other purpose than
#      to be found (#306). The canonical sentence is written out below, and the
#      normalised text between the markers must equal it EXACTLY. A site with
#      no region, two regions, or a region that says anything else, FAILS.
#
#   2. OUTSIDE THE REGION. In the rest of the sample site's span, none of the
#      stated vocabulary may appear at all. So the only place at a sample site
#      where the transition can be written about is the region, and the only
#      thing the region may say is the canonical sentence.
#
# The one exemption is stated, bounded and PRINTED: ROUNDS' own log marker is
# quoted verbatim in one remark and contains a vocabulary word. Only the exact
# literals in $vocabularyExemptions are removed before the scan, and the
# checker prints each one it removed and where. Any other occurrence fails.
#
# WHAT IT STILL CANNOT DO, STATED RATHER THAN IMPLIED (#310 / #389). A sentence
# outside the region that describes the same outcome while using none of the
# vocabulary is not caught. The bound is therefore: at a sample site, no
# statement using the stated vocabulary can exist outside the one canonical
# sentence. That is a bound, not a proof, and it is written here rather than
# left for a reader to discover.
#
# WHAT A SPAN IS
# --------------
#   file   the lane source the claim lives in
#   span   an anchored region of that file, start phrase to end phrase. NEVER
#          the whole file: a flag names a line and the defect is a class, but a
#          forbidden phrase searched file-wide reds on an unrelated paragraph
#          and stops meaning anything (#432). An anchor that does not match, or
#          that matches more than once, is a FAIL and never a skip - a skipped
#          row and a passed row differ by one word the eye slides past (#679).
#   kind   required (must appear at least MinCount times in the span) or
#          forbidden (must appear zero times).
#
# HOW TEXT IS COMPARED
# --------------------
# The file is read whole, the comment markers are stripped and every run of
# whitespace becomes one space. XML doc comments wrap, and the wrap point moves
# whenever a sentence is edited, so a phrase that spans a line break has to be
# matched against normalised text or the check reds on reflow alone and gets
# deleted for being noisy. Comparison is ordinal and case-INSENSITIVE: a
# forbidden phrase must not be able to return by changing its capitalisation.

param(
    [string]$Root = (Resolve-Path -LiteralPath (Join-Path (Join-Path $PSScriptRoot '..') '..')).Path
)

$ErrorActionPreference = 'Stop'

function Get-NormalisedText {
    param([string]$Path)
    $raw = [System.IO.File]::ReadAllText($Path)
    # Strip the comment markers so a phrase can be written as prose rather than
    # as prose plus whatever slashes happen to precede each wrapped line.
    $raw = $raw -replace '///', ' '
    $raw = $raw -replace '//', ' '
    $raw = $raw -replace '\s+', ' '
    return $raw
}

function Get-Occurrences {
    param([string]$Haystack, [string]$Needle)
    $n = 0
    $i = 0
    while ($true) {
        $i = $Haystack.IndexOf($Needle, $i, [System.StringComparison]::OrdinalIgnoreCase)
        if ($i -lt 0) { break }
        $n = $n + 1
        $i = $i + 1
    }
    return $n
}

# ---- the spans --------------------------------------------------------------

$spans = @(
    @{ Name = 'rostercensus/two-samples-remark';      File = 'plugin/RosterCensus.cs';
       Start = 'TWO SAMPLES PER MAP LOAD, AND WHY';   End = 'FAILURE DIRECTION' },
    @{ Name = 'rostercensus/boundary-labels';         File = 'plugin/RosterCensus.cs';
       Start = 'Grep target. See the class remarks';  End = 'internal const string BoundaryGame' },
    @{ Name = 'gamestatewatcher/map-boundary-patch';  File = 'plugin/GameStateWatcher.cs';
       Start = 'The map call-in. Every point and round transition calls'; End = 'internal static class RosterCensus_MapBoundary_Patch' },
    @{ Name = 'roomactors/inertness-remark';          File = 'plugin/RoomActors.cs';
       Start = 'THE INERTNESS GUARANTEE';             End = 'Classification is CACHED BY ActorNumber' },
    @{ Name = 'roomactors/any-spectator-present';     File = 'plugin/RoomActors.cs';
       Start = 'True only if at least one actor in the room declared the'; End = 'internal static bool AnySpectatorPresent' },
    @{ Name = 'roomactors/active-fighters';           File = 'plugin/RoomActors.cs';
       Start = 'Every actor that is playing, ActorNumber-ascending'; End = 'Per-frame result cache' }
)

# ---- the sample sites, the canonical sentence, the vocabulary ---------------

# Every span that documents one of the two map samples. A site listed here MUST
# carry exactly one canonical region; a site that is listed and not read is a
# VOID result, never a pass (#441).
$sampleSites = @(
    'rostercensus/two-samples-remark',
    'rostercensus/boundary-labels',
    'gamestatewatcher/map-boundary-patch'
)

$claimBegin = 'SCR_CENSUS_MOVE_CLAIM_BEGIN'
$claimEnd = 'SCR_CENSUS_MOVE_CLAIM_END'

# THE ONE SENTENCE A SAMPLE SITE MAY SAY ABOUT THE TRANSITION. Written out here
# so the checker STATES the permitted text rather than merely reacting to text
# it dislikes.
$canonicalClaim = @'
A settled row asserts the delay it measured and never a position in vanilla's transition, so a call-in row and a settled row carrying equal pos fields are two observations that agree and are not a reading that the seat did not move.
'@

# The vocabulary. Outside the region, at a sample site, none of these may
# appear. Word-boundaried so that MovePlayers - a method name - is not a hit,
# and case-insensitive so a claim cannot return in different capitals.
$vocabulary = @(
    '\bmove\b', '\bmoves\b', '\bmoved\b', '\bmoving\b', '\bmovement\b', '\bunmoved\b',
    '\bteleport\w*\b', '\brelocat\w*\b', '\breposition\w*\b',
    '\bfar side\b', '\bpre-move\b', '\bpost-move\b', '\bstayed put\b'
)

# The ONLY literals removed before the vocabulary scan. Each is a verbatim
# quotation of something outside this codebase that a remark has to be able to
# name. Every removal is printed.
$vocabularyExemptions = @(
    'CALL IN NEW MAP AND MOVE PLAYERS'
)

# ---- the claims -------------------------------------------------------------

$claims = @(
    # ---- finding 6: settled rows are documented delay-only ----
    @{ Span = 'rostercensus/two-samples-remark'; Kind = 'required'; MinCount = 1;
       Phrase = 'a sample taken about two seconds after the call-in';
       Why = 'finding 6: the settled sample is documented by its DELAY' },
    @{ Span = 'rostercensus/two-samples-remark'; Kind = 'required'; MinCount = 1;
       Phrase = 'carrying the elapsed time it measured';
       Why = 'finding 6: and by the measured elapsed field it carries' },

    @{ Span = 'rostercensus/boundary-labels'; Kind = 'required'; MinCount = 1;
       Phrase = 'taken about two seconds after the call-in';
       Why = 'finding 6: the settled LABEL says only when the sample was taken' },
    @{ Span = 'rostercensus/boundary-labels'; Kind = 'required'; MinCount = 1;
       Phrase = 'carrying the elapsed time it measured as';
       Why = 'finding 6: and that it carries the measured elapsed field' },

    @{ Span = 'gamestatewatcher/map-boundary-patch'; Kind = 'required'; MinCount = 1;
       Phrase = 'taken about two seconds later and carrying the elapsed time it measured';
       Why = 'finding 6: the Postfix remark describes the second sample by its delay' },

    # ---- finding 7: helper-wide comments match every helper gate ----
    @{ Span = 'roomactors/inertness-remark'; Kind = 'forbidden';
       Phrase = 'every helper here';
       Why = 'finding 7: the spectator helpers do not test frozen-roster state' },
    @{ Span = 'roomactors/inertness-remark'; Kind = 'required'; MinCount = 1;
       Phrase = 'The guarantee is about the FIGHTER views';
       Why = 'finding 7: the claim is narrowed to the helpers it is true of' },
    @{ Span = 'roomactors/inertness-remark'; Kind = 'required'; MinCount = 1;
       Phrase = 'It is NOT a claim about the spectator views';
       Why = 'finding 7: and says so of the three it is not true of' },

    @{ Span = 'roomactors/any-spectator-present'; Kind = 'forbidden';
       Phrase = 'Every helper below';
       Why = 'finding 7: the authored every-helper claim was false' },
    @{ Span = 'roomactors/any-spectator-present'; Kind = 'required'; MinCount = 1;
       Phrase = 'short-circuit on THIS ALONE and deliberately do not consult the freeze';
       Why = 'finding 7: the spectator views state their own condition' },

    # ---- finding 8: ActiveFighters states the unfrozen-roster condition ----
    @{ Span = 'roomactors/active-fighters'; Kind = 'required'; MinCount = 1;
       Phrase = 'only when NO spectator is in the room AND the roster is NOT frozen';
       Why = 'finding 8: both conditions, because the fast path tests both' },
    @{ Span = 'roomactors/active-fighters'; Kind = 'forbidden';
       Phrase = 'Identical to PhotonNetwork.PlayerList when no spectator is in the room';
       Why = 'finding 8: a frozen no-spectator room returns a filtered array' }
)

# ---- run --------------------------------------------------------------------

Write-Output "=== roster-census source-claim check ==="
Write-Output ("invocation:     " + [Environment]::CommandLine)
Write-Output ("invocation-root: " + $Root)
Write-Output ("invocation-utc: " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ""
Write-Output "--- the allow-list this check enforces at every sample site ---"
Write-Output ("canonical claim: " + $canonicalClaim.Trim())
Write-Output ("region markers:  " + $claimBegin + " .. " + $claimEnd)
Write-Output ("vocabulary:      " + ($vocabulary -join '  '))
foreach ($ex in $vocabularyExemptions) {
    Write-Output ("exempt literal:  " + $ex)
}
Write-Output ""

$failures = 0
$spanText = @{}

foreach ($span in $spans) {
    $path = Join-Path $Root $span.File
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Output ("FAIL | span={0,-40} | no such file: {1}" -f $span.Name, $span.File)
        $failures = $failures + 1
        continue
    }

    $text = Get-NormalisedText -Path $path
    $startCount = Get-Occurrences -Haystack $text -Needle $span.Start
    $endCount = Get-Occurrences -Haystack $text -Needle $span.End

    # An anchor that cannot be found, or that is not unique, is a FAILURE. A
    # first-match substitution here would silently move every claim below it
    # into a region nobody chose (#679).
    if ($startCount -ne 1 -or $endCount -ne 1) {
        Write-Output ("FAIL | span={0,-40} | anchors not unique: start={1} end={2}" -f $span.Name, $startCount, $endCount)
        $failures = $failures + 1
        continue
    }

    $from = $text.IndexOf($span.Start, [System.StringComparison]::OrdinalIgnoreCase)
    $to = $text.IndexOf($span.End, [System.StringComparison]::OrdinalIgnoreCase)
    if ($to -le $from) {
        Write-Output ("FAIL | span={0,-40} | end anchor precedes start anchor" -f $span.Name)
        $failures = $failures + 1
        continue
    }

    $spanText[$span.Name] = $text.Substring($from, $to - $from)
    Write-Output ("ok   | span={0,-40} | chars={1}" -f $span.Name, ($to - $from))
}

Write-Output ""
Write-Output "--- sample sites (every listed site is READ and printed; a site not read is VOID) ---"

$sitesRead = 0
foreach ($site in $sampleSites) {
    if (-not $spanText.ContainsKey($site)) {
        Write-Output ("FAIL | site={0,-40} | span unavailable - the site could not be read" -f $site)
        $failures = $failures + 1
        continue
    }

    $sitesRead = $sitesRead + 1
    $text = $spanText[$site]

    $beginCount = Get-Occurrences -Haystack $text -Needle $claimBegin
    $endCountMarker = Get-Occurrences -Haystack $text -Needle $claimEnd
    if ($beginCount -ne 1 -or $endCountMarker -ne 1) {
        Write-Output ("FAIL | site={0,-40} | canonical region markers: begin={1} end={2}, expected 1 and 1" -f `
            $site, $beginCount, $endCountMarker)
        $failures = $failures + 1
        continue
    }

    $b = $text.IndexOf($claimBegin, [System.StringComparison]::OrdinalIgnoreCase)
    $e = $text.IndexOf($claimEnd, [System.StringComparison]::OrdinalIgnoreCase)
    if ($e -le $b) {
        Write-Output ("FAIL | site={0,-40} | the end marker precedes the begin marker" -f $site)
        $failures = $failures + 1
        continue
    }

    $regionStart = $b + $claimBegin.Length
    $region = $text.Substring($regionStart, $e - $regionStart)
    $region = ($region -replace '\s+', ' ').Trim()
    $want = ($canonicalClaim -replace '\s+', ' ').Trim()

    $regionOk = [string]::Equals($region, $want, [System.StringComparison]::Ordinal)
    if ($regionOk) {
        Write-Output ("ok   | site={0,-40} | region matches the canonical claim, chars={1}" -f $site, $region.Length)
    } else {
        Write-Output ("FAIL | site={0,-40} | region is not the canonical claim" -f $site)
        Write-Output ("     | want: " + $want)
        Write-Output ("     | got:  " + $region)
        $failures = $failures + 1
    }

    # Everything at this site EXCEPT the region, including the markers.
    $outside = $text.Substring(0, $b) + $text.Substring($e + $claimEnd.Length)

    foreach ($ex in $vocabularyExemptions) {
        $n = Get-Occurrences -Haystack $outside -Needle $ex
        if ($n -gt 0) {
            Write-Output ("     | site={0,-40} | exempt literal removed {1}x before the scan: {2}" -f $site, $n, $ex)
            $outside = [System.Text.RegularExpressions.Regex]::Replace(
                $outside, [System.Text.RegularExpressions.Regex]::Escape($ex), ' ',
                [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        }
    }

    $hits = 0
    foreach ($pattern in $vocabulary) {
        $matches = [System.Text.RegularExpressions.Regex]::Matches(
            $outside, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($matches.Count -gt 0) {
            $hits = $hits + $matches.Count
            foreach ($m in $matches) {
                $at = [Math]::Max(0, $m.Index - 60)
                $len = [Math]::Min(150, $outside.Length - $at)
                Write-Output ("FAIL | site={0,-40} | vocabulary outside the canonical region: {1}" -f $site, $m.Value)
                Write-Output ("     | context: ..." + $outside.Substring($at, $len).Trim() + "...")
            }
        }
    }
    if ($hits -gt 0) { $failures = $failures + 1 }
    else { Write-Output ("ok   | site={0,-40} | no vocabulary outside the region, chars scanned={1}" -f $site, $outside.Length) }
}

Write-Output ""

$checked = 0
foreach ($claim in $claims) {
    if (-not $spanText.ContainsKey($claim.Span)) {
        Write-Output ("FAIL | claim | span={0,-40} | span unavailable | {1}" -f $claim.Span, $claim.Why)
        $failures = $failures + 1
        continue
    }

    $checked = $checked + 1
    $count = Get-Occurrences -Haystack $spanText[$claim.Span] -Needle $claim.Phrase

    $ok = $false
    if ($claim.Kind -eq 'required') { $ok = ($count -ge $claim.MinCount) }
    else { $ok = ($count -eq 0) }

    if (-not $ok) { $failures = $failures + 1 }

    Write-Output ("{0,-4} | {1,-9} | span={2,-40} | count={3} | phrase={4}" -f `
        $(if ($ok) { 'ok' } else { 'FAIL' }), $claim.Kind, $claim.Span, $count, $claim.Phrase)
    if (-not $ok) { Write-Output ("     | why: " + $claim.Why) }
}

Write-Output ""
Write-Output ("spans=" + $spans.Count + " sites=" + $sampleSites.Count + " sitesRead=" + $sitesRead `
    + " claims=" + $claims.Count + " checked=" + $checked + " failures=" + $failures)

if ($sitesRead -ne $sampleSites.Count) {
    Write-Output "CLAIMS VOID | a sample site was not read - a site nobody read is not a site that passed"
    exit 3
}
if ($checked -ne $claims.Count) {
    Write-Output "CLAIMS VOID | a claim was not checked - an unchecked claim is not a passing claim"
    exit 3
}
if ($failures -gt 0) {
    Write-Output "CLAIMS FAIL"
    exit 1
}
Write-Output "CLAIMS PASS"
exit 0
