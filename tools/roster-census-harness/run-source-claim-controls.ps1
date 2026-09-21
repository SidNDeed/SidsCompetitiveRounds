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
    [string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) 'scr-r2-source-claim-controls')
)

$ErrorActionPreference = 'Stop'

$checker = Join-Path $PSScriptRoot 'check-source-claims.ps1'
$sources = @('plugin/RosterCensus.cs', 'plugin/GameStateWatcher.cs', 'plugin/RoomActors.cs')

# Each case: the file it edits, the EXACT line it replaces, what it replaces it
# with, and whether the checker must pass afterwards.
$cases = @(
    @{ Name = 'M1-reinstates-the-far-side-claim'; Expect = 'FAIL'; File = 'plugin/RosterCensus.cs';
       Find = "    /// nothing about whether the move ran.";
       Into = "    /// the settled row is on the far side of the move and the revive.";
       Why  = 'finding 6: a move-ordering claim on the settled sample must red' },
    @{ Name = 'M1-twin-rewords-the-same-line'; Expect = 'PASS'; File = 'plugin/RosterCensus.cs';
       Find = "    /// nothing about whether the move ran.";
       Into = "    /// nothing about whether the move ran at all.";
       Why  = 'inert twin: the same line, reworded, asserts no ordering' },

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
& powershell -NoProfile -ExecutionPolicy Bypass -File $checker -Root $Root | Select-Object -Last 2
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
    if ($after -eq $before) {
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
