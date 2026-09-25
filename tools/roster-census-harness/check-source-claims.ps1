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
# WHAT REPLACED THE SPAN LIST, AND WHY
# ------------------------------------
# The allow-list that replaced it fixed the WORDING dimension and left the
# LOCATION dimension alone. Its sweep ran over six hand-maintained spans, so
# the refuted reading survived 1050 lines away in the same file, in a self-test
# remark no span covered, and the check still reported CLAIMS PASS. A rule that
# only reaches the places someone remembered to list is a rule about the list
# (#432): the flag named a line and the defect was a class.
#
# So the sweep no longer runs over spans. It runs over TERRITORIES, and two
# further rules make the territory set answer for itself:
#
#   1. THE REGION, per sample site. Each site carries exactly ONE
#      interpretation sentence, between SCR_CENSUS_MOVE_CLAIM_BEGIN and
#      SCR_CENSUS_MOVE_CLAIM_END. Those markers exist for no other purpose than
#      to be found (#306). The canonical sentence is written out below, and the
#      normalised text between the markers must equal it EXACTLY. A site with
#      no region, two regions, or a region that says anything else, FAILS.
#
#   2. THE TERRITORY. A territory is a WHOLE FILE, or a region of a file marked
#      by SCR_CENSUS_PROSE_BEGIN / SCR_CENSUS_PROSE_END. Anywhere inside a
#      territory, outside a canonical region, none of the stated vocabulary may
#      appear at all. plugin/RosterCensus.cs is a territory in its entirety
#      because the file exists for nothing but the census; the census block of
#      plugin/GameStateWatcher.cs is a marked territory because the rest of
#      that file is another lane's.
#
#   3. THE CENSUS. Across the lane's source files, the claim markers must occur
#      exactly as many times as there are sample sites - so a FOURTH
#      interpretation region cannot appear anywhere without this failing - and
#      every file that carries one must be a declared territory, so a region
#      cannot escape the sweep by moving to a file nobody listed.
#
# What that makes impossible: at any line of plugin/RosterCensus.cs, and at any
# line of the census block of plugin/GameStateWatcher.cs, no statement using
# the stated vocabulary can exist outside the one canonical sentence, whether or
# not anyone remembered to add a span for it; and no fourth region can be added
# anywhere in the lane's sources without a FAIL.
#
# The one exemption is stated, bounded and PRINTED: ROUNDS' own log markers are
# quoted verbatim in two remarks and contain vocabulary words. Only the exact
# literals in $vocabularyExemptions are removed before the scan, and the checker
# prints each one it removed and where. Any other occurrence fails.
#
# WHAT IT STILL CANNOT DO, STATED RATHER THAN IMPLIED (#310 / #389). A sentence
# inside a territory that describes the same outcome while using none of the
# vocabulary is not caught. And a territory is still a declared thing: lane
# source added in a NEW file is swept only once that file is a territory - which
# is what rule 3's second half exists to force, since a region in an undeclared
# file FAILS rather than passing quietly.
#
# WHAT A SPAN IS
# --------------
# Spans remain, for the PHRASE claims below - the ones that assert a particular
# remark says a particular thing. They are no longer what bounds the vocabulary
# sweep.
#
#   file   the lane source the claim lives in
#   span   an anchored region of that file, start phrase to end phrase. NEVER
#          the whole file: a required phrase searched file-wide would pass on an
#          unrelated paragraph. An anchor that does not match, or that matches
#          more than once, is a FAIL and never a skip - a skipped row and a
#          passed row differ by one word the eye slides past (#679).
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
$proseBegin = 'SCR_CENSUS_PROSE_BEGIN'
$proseEnd = 'SCR_CENSUS_PROSE_END'

# THE ONE SENTENCE A SAMPLE SITE MAY SAY ABOUT THE TRANSITION. Written out here
# so the checker STATES the permitted text rather than merely reacting to text
# it dislikes.
$canonicalClaim = @'
A settled row asserts the delay it measured and never a position in vanilla's transition, so a call-in row and a settled row carrying equal pos fields are two observations that agree and are not a reading that the seat did not move.
'@

# ---- the territories, and the files a region may live in --------------------

# Every source file this lane owns that could carry a canonical region. The
# census rule below counts markers across exactly these, so a region added to
# any of them is seen whether or not it is inside a declared span.
$laneFiles = @(
    'plugin/RosterCensus.cs',
    'plugin/GameStateWatcher.cs',
    'plugin/RoomActors.cs',
    'plugin/NetworkReplicaDiagnostics.cs'
)

# Where the vocabulary sweep runs. Kind 'file' is the whole file; kind 'region'
# is the text between the prose markers, which must occur exactly once each.
$territories = @(
    @{ Name = 'rostercensus/whole-file';          File = 'plugin/RosterCensus.cs';     Kind = 'file';
       Why  = 'the file exists for nothing but the census, so every line of it is in scope' },
    @{ Name = 'gamestatewatcher/census-block';    File = 'plugin/GameStateWatcher.cs'; Kind = 'region';
       Why  = 'the census block only - the rest of the file belongs to other work and is not this lane to police' }
)

# The vocabulary. Inside a territory, outside a canonical region, none of these
# may appear. Word-boundaried so that MovePlayers - a method name - is not a
# hit, and case-insensitive so a claim cannot return in different capitals.
$vocabulary = @(
    '\bmove\b', '\bmoves\b', '\bmoved\b', '\bmoving\b', '\bmovement\b', '\bunmoved\b',
    '\bteleport\w*\b', '\brelocat\w*\b', '\breposition\w*\b',
    '\bfar side\b', '\bpre-move\b', '\bpost-move\b', '\bstayed put\b'
)

# The ONLY literals removed before the vocabulary scan. Each is a verbatim
# quotation of a ROUNDS log marker that a remark has to be able to name. Every
# removal is printed, with the territory it was removed from.
$vocabularyExemptions = @(
    'CALL IN NEW MAP AND MOVE PLAYERS',
    'MOVE PLAYERS START'
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
Write-Output "--- the allow-list this check enforces ---"
Write-Output ("canonical claim: " + $canonicalClaim.Trim())
Write-Output ("region markers:  " + $claimBegin + " .. " + $claimEnd)
Write-Output ("prose markers:   " + $proseBegin + " .. " + $proseEnd)
Write-Output ("vocabulary:      " + ($vocabulary -join '  '))
foreach ($ex in $vocabularyExemptions) {
    Write-Output ("exempt literal:  " + $ex)
}
foreach ($t in $territories) {
    Write-Output ("territory:       {0,-34} | {1,-28} | {2}" -f $t.Name, $t.File, $t.Kind)
}
foreach ($f in $laneFiles) {
    Write-Output ("lane file:       " + $f)
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

# ---- the census of regions --------------------------------------------------

Write-Output ""
Write-Output "--- region census: the markers are counted across every lane file, so a fourth region cannot hide ---"

$territoryFiles = @($territories | ForEach-Object { $_.File })
$totalBegin = 0
$totalEnd = 0
$censusRead = 0

foreach ($file in $laneFiles) {
    $path = Join-Path $Root $file
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Output ("FAIL | census | no such lane file: " + $file)
        $failures = $failures + 1
        continue
    }
    $censusRead = $censusRead + 1
    $text = Get-NormalisedText -Path $path
    $b = Get-Occurrences -Haystack $text -Needle $claimBegin
    $e = Get-Occurrences -Haystack $text -Needle $claimEnd
    $totalBegin = $totalBegin + $b
    $totalEnd = $totalEnd + $e

    $isTerritory = $territoryFiles -contains $file
    $row = 'ok  '
    # A region in a file no territory covers would be policed for its WORDING
    # and swept nowhere, which is the hole the span list left.
    if (($b -gt 0 -or $e -gt 0) -and -not $isTerritory) {
        $row = 'FAIL'
        $failures = $failures + 1
    }
    Write-Output ("{0} | census | {1,-38} | begin={2} end={3} | territory={4}" -f `
        $row, $file, $b, $e, $(if ($isTerritory) { 'yes' } else { 'NO' }))
}

$wantMarkers = $sampleSites.Count
$censusOk = ($totalBegin -eq $wantMarkers -and $totalEnd -eq $wantMarkers)
if (-not $censusOk) { $failures = $failures + 1 }
Write-Output ("{0} | census | totals across the lane files: begin={1} end={2}, expected {3} and {3}" -f `
    $(if ($censusOk) { 'ok  ' } else { 'FAIL' }), $totalBegin, $totalEnd, $wantMarkers)

# ---- the territories --------------------------------------------------------

Write-Output ""
Write-Output "--- territories (every declared territory is READ and printed; one not read is VOID) ---"

$territoriesRead = 0
foreach ($t in $territories) {
    $path = Join-Path $Root $t.File
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Output ("FAIL | territory={0,-34} | no such file: {1}" -f $t.Name, $t.File)
        $failures = $failures + 1
        continue
    }

    $text = Get-NormalisedText -Path $path

    if ($t.Kind -eq 'region') {
        $pb = Get-Occurrences -Haystack $text -Needle $proseBegin
        $pe = Get-Occurrences -Haystack $text -Needle $proseEnd
        if ($pb -ne 1 -or $pe -ne 1) {
            Write-Output ("FAIL | territory={0,-34} | prose markers: begin={1} end={2}, expected 1 and 1" -f `
                $t.Name, $pb, $pe)
            $failures = $failures + 1
            continue
        }
        $tb = $text.IndexOf($proseBegin, [System.StringComparison]::OrdinalIgnoreCase)
        $te = $text.IndexOf($proseEnd, [System.StringComparison]::OrdinalIgnoreCase)
        if ($te -le $tb) {
            Write-Output ("FAIL | territory={0,-34} | the end marker precedes the begin marker" -f $t.Name)
            $failures = $failures + 1
            continue
        }
        $text = $text.Substring($tb, $te - $tb)
    }

    $territoriesRead = $territoriesRead + 1

    # Excise every canonical region in the territory. What is left is
    # everything the vocabulary may not appear in.
    $outside = $text
    $regions = 0
    while ($true) {
        $b = $outside.IndexOf($claimBegin, [System.StringComparison]::OrdinalIgnoreCase)
        if ($b -lt 0) { break }
        $e = $outside.IndexOf($claimEnd, $b, [System.StringComparison]::OrdinalIgnoreCase)
        if ($e -lt 0) {
            Write-Output ("FAIL | territory={0,-34} | a begin marker with no end marker after it" -f $t.Name)
            $failures = $failures + 1
            break
        }
        $regions = $regions + 1
        $outside = $outside.Substring(0, $b) + ' ' + $outside.Substring($e + $claimEnd.Length)
    }

    Write-Output ("ok   | territory={0,-34} | {1,-28} | {2,-6} | chars={3} | canonical regions excised={4}" -f `
        $t.Name, $t.File, $t.Kind, $text.Length, $regions)
    Write-Output ("     | why: " + $t.Why)

    foreach ($ex in $vocabularyExemptions) {
        $n = Get-Occurrences -Haystack $outside -Needle $ex
        if ($n -gt 0) {
            Write-Output ("     | territory={0,-34} | exempt literal removed {1}x before the scan: {2}" -f `
                $t.Name, $n, $ex)
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
                Write-Output ("FAIL | territory={0,-34} | vocabulary outside a canonical region: {1}" -f $t.Name, $m.Value)
                Write-Output ("     | context: ..." + $outside.Substring($at, $len).Trim() + "...")
            }
        }
    }
    if ($hits -gt 0) { $failures = $failures + 1 }
    else { Write-Output ("ok   | territory={0,-34} | no vocabulary outside a canonical region, chars scanned={1}" -f $t.Name, $outside.Length) }
}

# ---- the sample sites -------------------------------------------------------

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
    + " laneFiles=" + $laneFiles.Count + " censusRead=" + $censusRead `
    + " territories=" + $territories.Count + " territoriesRead=" + $territoriesRead `
    + " markers=" + $totalBegin + " claims=" + $claims.Count + " checked=" + $checked `
    + " failures=" + $failures)

if ($sitesRead -ne $sampleSites.Count) {
    Write-Output "CLAIMS VOID | a sample site was not read - a site nobody read is not a site that passed"
    exit 3
}
if ($territoriesRead -ne $territories.Count) {
    Write-Output "CLAIMS VOID | a territory was not read - an unswept territory is not a clean one"
    exit 3
}
if ($censusRead -ne $laneFiles.Count) {
    Write-Output "CLAIMS VOID | a lane file was not read - the region census is only a census if it saw every file"
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
