# Source-claim check for the roster-census lane.
#
# WHY THIS EXISTS
# ---------------
# Some of the round-2 closures are CLAIMS rather than behaviour: a remark that
# said the settled sample sits after the move, and two remarks that said every
# helper tests something only some of them test. A claim asserted about the
# source and never run is exactly the shape #391 rejects, so each of those
# claims is turned into a row here that a mutation can redden.
#
# WHAT A ROW IS
# -------------
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

# ---- the claims -------------------------------------------------------------

$claims = @(
    # ---- finding 6: settled rows are documented delay-only ----
    @{ Span = 'rostercensus/two-samples-remark'; Kind = 'required'; MinCount = 1;
       Phrase = 'a sample taken about two seconds after the call-in';
       Why = 'finding 6: the settled sample is documented by its DELAY' },
    @{ Span = 'rostercensus/two-samples-remark'; Kind = 'required'; MinCount = 1;
       Phrase = 'carrying the elapsed time it measured';
       Why = 'finding 6: and by the measured elapsed field it carries' },
    @{ Span = 'rostercensus/two-samples-remark'; Kind = 'forbidden';
       Phrase = 'far side';
       Why = 'finding 6: a stalled transition leaves pre-move data under a post-move claim' },
    @{ Span = 'rostercensus/two-samples-remark'; Kind = 'forbidden';
       Phrase = 'after the move';
       Why = 'finding 6: the row asserts a delay, never a position in the transition' },

    @{ Span = 'rostercensus/boundary-labels'; Kind = 'required'; MinCount = 1;
       Phrase = 'taken about two seconds after the call-in';
       Why = 'finding 6: the settled LABEL says only when the sample was taken' },
    @{ Span = 'rostercensus/boundary-labels'; Kind = 'required'; MinCount = 1;
       Phrase = 'carrying the elapsed time it measured as';
       Why = 'finding 6: and that it carries the measured elapsed field' },
    @{ Span = 'rostercensus/boundary-labels'; Kind = 'forbidden';
       Phrase = 'far side';
       Why = 'finding 6: no move-ordering claim on either map label' },
    @{ Span = 'rostercensus/boundary-labels'; Kind = 'forbidden';
       Phrase = 'after the move';
       Why = 'finding 6: no move-ordering claim on either map label' },

    @{ Span = 'gamestatewatcher/map-boundary-patch'; Kind = 'required'; MinCount = 1;
       Phrase = 'taken about two seconds later and carrying the elapsed time it measured';
       Why = 'finding 6: the Postfix remark describes the second sample by its delay' },
    @{ Span = 'gamestatewatcher/map-boundary-patch'; Kind = 'forbidden';
       Phrase = 'far side';
       Why = 'finding 6: the settled sample is not documented as being past the move' },

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
Write-Output ("spans=" + $spans.Count + " claims=" + $claims.Count + " checked=" + $checked + " failures=" + $failures)

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
