# Mutation controls for check-source-claims.ps1.
#
# A claim check that has never been shown to FAIL is decoration (#342), and a
# check shown to fail on any edit at all only proves it noticed the file
# changed (#712). So every site below carries a PAIR: a mutation that must turn
# that site's row RED, and an INERT TWIN - an edit of the same shape, on the
# same line - that must stay GREEN. The red is evidence only beside the green.
#
# Nothing here touches the worktree. Each case starts from a fresh copy of the
# lane sources in a temporary root and the checker is pointed at that root, so
# no `git checkout --` or `git restore` is ever needed on a tree with
# uncommitted work (#290 / #401).

param(
    [string]$Root = (Resolve-Path -LiteralPath (Join-Path (Join-Path $PSScriptRoot '..') '..')).Path,
    [string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) 'scr-r3-source-claim-controls')
)

$ErrorActionPreference = 'Stop'

$checker = Join-Path $PSScriptRoot 'check-source-claims.ps1'
# Every file the checker reads. NetworkReplicaDiagnostics.cs carries no claim
# and no territory, but the checker COUNTS the claim markers across all four
# lane files, so a temporary root missing one would VOID every case - making
# each mutation look caught and each twin look broken at the same time.
$sources = @('plugin/RosterCensus.cs', 'plugin/GameStateWatcher.cs', 'plugin/RoomActors.cs',
             'plugin/NetworkReplicaDiagnostics.cs')

# Each case: the file it edits, the EXACT line it replaces, what it replaces it
# with, and whether the checker must pass afterwards.
$cases = @(
    @{ Name = 'M1-reinstates-the-far-side-claim'; Expect = 'FAIL'; File = 'plugin/RosterCensus.cs';
       Find = "    /// but a sample's TIMING is a timing and never an ORDERING.";
       Into = "    /// but the settled row sits on the far side of the transition.";
       Why  = 'round-3 finding 2: vocabulary outside the canonical region must red' },
    @{ Name = 'M1-twin-rewords-the-same-line'; Expect = 'PASS'; File = 'plugin/RosterCensus.cs';
       Find = "    /// but a sample's TIMING is a timing and never an ORDERING.";
       Into = "    /// but a sample's TIMING is a timing and is never an ORDERING.";
       Why  = 'inert twin: the same line, reworded, asserts no ordering' },

    # The claim the round-2 blacklist accepted, reinstated WORD FOR WORD. The
    # old check listed 'far side' and 'after the move' and this sentence used
    # neither, so it passed while saying the thing the check existed to reject.
    @{ Name = 'M5-reinstates-the-equal-snapshots-claim'; Expect = 'FAIL'; File = 'plugin/RosterCensus.cs';
       Find = "    /// a claim untrue of it.";
       Into = "    /// a claim untrue of it. The PAIR is the instrument: a settled row whose positions still equal its call-in row's is a seat that never got moved.";
       Why  = 'round-3 finding 2: the exact claim the phrase blacklist accepted must now red' },
    @{ Name = 'M5-twin-rewords-the-same-line'; Expect = 'PASS'; File = 'plugin/RosterCensus.cs';
       Find = "    /// a claim untrue of it.";
       Into = "    /// a claim that is untrue of it.";
       Why  = 'inert twin: the same line, reworded, makes no outcome claim' },

    # The region itself is an allow-list: the ONE canonical sentence, exactly.
    @{ Name = 'M6-alters-the-canonical-claim'; Expect = 'FAIL'; File = 'plugin/RosterCensus.cs';
       Find = "    /// equal pos fields are two observations that agree and are not a";
       Into = "    /// equal pos fields are two observations that agree and are a";
       Why  = 'round-3 finding 2: the canonical region admits one sentence and no other' },
    @{ Name = 'M6-twin-rewords-the-line-beside-the-region'; Expect = 'PASS'; File = 'plugin/RosterCensus.cs';
       Find = "    /// itself: between the markers the text must match it exactly, and";
       Into = "    /// itself: between those markers the text must match it exactly, and";
       Why  = 'inert twin: the same remark, reworded outside the region, stays green' },

    # A site with no region is not a site that passed.
    @{ Name = 'M7-removes-a-sample-site-region'; Expect = 'FAIL'; File = 'plugin/GameStateWatcher.cs';
       Find = "    /// SCR_CENSUS_MOVE_CLAIM_BEGIN";
       Into = "    /// (this site carries no canonical interpretation)";
       Why  = 'round-3 finding 2: a sample site that states no canonical claim must red, never skip' },
    @{ Name = 'M7-twin-rewords-the-line-above-the-region'; Expect = 'PASS'; File = 'plugin/GameStateWatcher.cs';
       Find = "    /// timing is a timing, never an ordering (#351). See that class's";
       Into = "    /// timing is a timing and never an ordering (#351). See that class's";
       Why  = 'inert twin: the same remark, reworded beside the region, stays green' },

    # THE LENS FINDING. The allow-list fixed the WORDING and left the LOCATION
    # alone: this site is 1050 lines below the nearest span, and the refuted
    # reading sat here while the check reported success. It is caught now
    # because the sweep runs over the WHOLE FILE and not over a span list.
    @{ Name = 'M8-reinstates-the-pair-as-proof-reading-outside-every-span'; Expect = 'FAIL';
       File = 'plugin/RosterCensus.cs';
       Find = "            //     file, and is not restated here or anywhere else.";
       Into = "            //     file. In practice: a settled row whose pos fields equal its call-in row's is a seat that never moved.";
       Why  = 'lens finding 1: an outcome claim far from every span must red on the territory sweep' },
    @{ Name = 'M8-twin-rewords-the-same-line'; Expect = 'PASS'; File = 'plugin/RosterCensus.cs';
       Find = "            //     file, and is not restated here or anywhere else.";
       Into = "            //     file, and is not restated here nor anywhere else.";
       Why  = 'inert twin: the same line, reworded, makes no outcome claim' },

    # A FOURTH canonical region, carrying the canonical sentence word for word.
    # Nothing about its WORDING is wrong - the vocabulary inside a region is
    # excised before the sweep - so the only thing that can catch it is the
    # census of markers across the lane files.
    @{ Name = 'M9-adds-a-fourth-canonical-region'; Expect = 'FAIL'; File = 'plugin/RosterCensus.cs';
       Find = "            // 9. Degenerate inputs are empty, not exceptions.";
       Into = "            // SCR_CENSUS_MOVE_CLAIM_BEGIN`r`n            // A settled row asserts the delay it measured and never a position in vanilla's transition, so a call-in row and a settled row carrying equal pos fields are two observations that agree and are not a reading that the seat did not move.`r`n            // SCR_CENSUS_MOVE_CLAIM_END`r`n            // 9. Degenerate inputs are empty, not exceptions.";
       Why  = 'lens finding 1: an interpretation region at an undeclared site must red on the marker census' },
    @{ Name = 'M9-twin-adds-the-same-note-without-markers'; Expect = 'PASS'; File = 'plugin/RosterCensus.cs';
       Find = "            // 9. Degenerate inputs are empty, not exceptions.";
       Into = "            // A reader is told once, at the top of this file, how to read a`r`n            // pair of rows; this note adds nothing to that.`r`n            // 9. Degenerate inputs are empty, not exceptions.";
       Why  = 'inert twin: the same remark at the same site, carrying no region, stays green' },

    # A territory that stops being marked is a territory nobody swept.
    @{ Name = 'M10-unmarks-the-census-territory'; Expect = 'FAIL'; File = 'plugin/GameStateWatcher.cs';
       Find = "    // SCR_CENSUS_PROSE_BEGIN";
       Into = "    // (the census block is no longer marked as a territory)";
       Why  = 'lens finding 1: an unswept territory is VOID, never a pass (#441)' },
    @{ Name = 'M10-twin-rewords-the-line-below-the-marker'; Expect = 'PASS'; File = 'plugin/GameStateWatcher.cs';
       Find = "    // Everything between this marker and its matching end marker, at the very";
       Into = "    // Everything between this marker and the matching end marker, at the very";
       Why  = 'inert twin: the same remark, reworded beside the marker, stays green' },

    @{ Name = 'M2-reinstates-the-every-helper-claim'; Expect = 'FAIL'; File = 'plugin/RoomActors.cs';
       Find = "        /// on an unfrozen roster, so with no spectator present and no frozen";
       Into = "        /// on an unfrozen roster. Every helper below does the same, so with no spectator present and no frozen";
       Why  = 'finding 7: a helper-wide claim the spectator helpers do not meet must red' },
    @{ Name = 'M2-twin-rewords-the-same-line'; Expect = 'PASS'; File = 'plugin/RoomActors.cs';
       Find = "        /// on an unfrozen roster, so with no spectator present and no frozen";
       Into = "        /// on an unfrozen roster, so with no spectator there and no frozen";
       Why  = 'inert twin: the same line, reworded, still scopes the claim' },

    @{ Name = 'M3-reinstates-the-spectator-only-condition'; Expect = 'FAIL'; File = 'plugin/RoomActors.cs';
       Find = "        /// roster is NOT frozen. Both conditions, because the fast path below";
       Into = "        /// roster is NOT frozen. Identical to PhotonNetwork.PlayerList when no spectator is in the room. Because the fast path below";
       Why  = 'finding 8: restating the claim without the freeze condition must red' },
    @{ Name = 'M3-twin-rewords-the-same-line'; Expect = 'PASS'; File = 'plugin/RoomActors.cs';
       Find = "        /// roster is NOT frozen. Both conditions, because the fast path below";
       Into = "        /// roster is NOT frozen. Both conditions hold, because the fast path below";
       Why  = 'inert twin: the same line, reworded, keeps both conditions' },

    # The first attempt at this pair used ActorNumbers, which still CONTAINS
    # the anchor - an inert mutation that the expectation column caught and
    # that a suite crediting "something reddened" would have banked (#712).
    @{ Name = 'M4-moves-a-span-anchor'; Expect = 'FAIL'; File = 'plugin/RoomActors.cs';
       Find = "    /// Classification is CACHED BY ActorNumber at first sight and is";
       Into = "    /// Classification is cached per actor at first sight and is";
       Why  = 'an anchor that cannot be found is a failure, never a skip (#679)' },
    @{ Name = 'M4-twin-rewords-the-same-anchor-line'; Expect = 'PASS'; File = 'plugin/RoomActors.cs';
       Find = "    /// Classification is CACHED BY ActorNumber at first sight and is";
       Into = "    /// Classification is CACHED BY ActorNumber at first sighting and is";
       Why  = 'inert twin: the same line, reworded, keeps the anchor findable' }
)

Write-Output "=== source-claim mutation controls ==="
Write-Output ("invocation:      " + [Environment]::CommandLine)
Write-Output ("invocation-root: " + $Root)
Write-Output ("invocation-utc:  " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ""

# ---- the baseline, first: an unmutated tree must PASS -----------------------
Write-Output "--- baseline (the worktree as it stands: must PASS) ---"
Write-Output ("run: powershell -NoProfile -File check-source-claims.ps1 -Root <worktree>")
# The nested run's own verdict is INDENTED. An un-indented result line here
# would read as this section's result to a log reader and to
# check-evidence-log.ps1, which binds each result to the invocation above it:
# a baseline echoed inside another section is not that section's result.
& powershell -NoProfile -ExecutionPolicy Bypass -File $checker -Root $Root |
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
    [void](New-Item -ItemType Directory -Path (Join-Path $caseRoot 'plugin') -Force)

    foreach ($rel in $sources) {
        Copy-Item -LiteralPath (Join-Path $Root $rel) -Destination (Join-Path $caseRoot $rel) -Force
    }

    $target = Join-Path $caseRoot $case.File
    $before = [System.IO.File]::ReadAllText($target)

    # An ambiguous or absent anchor means the edit did not land where it says,
    # and a mutation that changed nothing reads exactly like one that was
    # caught. Both are VOID, not a result.
    $hits = 0
    $i = 0
    while ($true) {
        $i = $before.IndexOf($case.Find, $i, [System.StringComparison]::Ordinal)
        if ($i -lt 0) { break }
        $hits = $hits + 1
        $i = $i + 1
    }
    if ($hits -ne 1) {
        Write-Output ("VOID | case={0,-46} | anchor occurs {1} times, expected 1" -f $case.Name, $hits)
        $failures = $failures + 1
        continue
    }

    $after = $before.Replace($case.Find, $case.Into)
    # ORDINAL, not -eq: PowerShell's -eq on strings is case-INSENSITIVE, so an
    # edit that changes only case would read here as an edit that changed
    # nothing. The guard exists to separate "changed nothing" from "was caught"
    # (#712) and cannot do that while it is blind to part of the change. The
    # sibling guard in run-evidence-log-controls.ps1 had the same defect and
    # was swept at the same time (#432).
    if ([string]::Equals($after, $before, [System.StringComparison]::Ordinal)) {
        Write-Output ("VOID | case={0,-46} | the edit changed nothing" -f $case.Name)
        $failures = $failures + 1
        continue
    }
    [System.IO.File]::WriteAllText($target, $after)

    & powershell -NoProfile -ExecutionPolicy Bypass -File $checker -Root $caseRoot > (Join-Path $caseRoot 'check.out') 2>&1
    $exit = $LASTEXITCODE
    $got = if ($exit -eq 0) { 'PASS' } else { 'FAIL' }
    $ok = ($got -eq $case.Expect)
    if (-not $ok) { $failures = $failures + 1 }

    Write-Output ("{0,-4} | case={1,-46} | expected={2,-4} got={3,-4} exit={4} | {5}" -f `
        $(if ($ok) { 'ok' } else { 'BAD' }), $case.Name, $case.Expect, $got, $exit, $case.Why)

    # The rows the mutation actually reddened, so the credit goes to a NAMED
    # row rather than to "something moved" (#712).
    if ($case.Expect -eq 'FAIL') {
        Get-Content -LiteralPath (Join-Path $caseRoot 'check.out') |
            Where-Object { $_ -like 'FAIL*' } |
            ForEach-Object { Write-Output ("     | reddened: " + $_) }
    }
}

Write-Output ""
Write-Output ("cases=" + $cases.Count + " failures=" + $failures)
if ($failures -gt 0) {
    Write-Output "SOURCE-CLAIM CONTROLS FAIL"
    exit 1
}
Write-Output "SOURCE-CLAIM CONTROLS PASS"
exit 0
