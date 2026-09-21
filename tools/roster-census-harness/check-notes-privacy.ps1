# Are the lane notes free of local user paths?
#
# WHY THIS EXISTS
# ---------------
# The notes are the artifact most likely to leave this machine by being READ
# rather than by being committed: a passage gets pasted into a bug-report
# comment, a commit body or a handoff. The pre-commit privacy guard cannot see
# that - it inspects what is staged, and the notes live under a directory git
# ignores, so they are never staged and never inspected. The guard is real and
# it is simply not on this path.
#
# Round 3 recorded two local user paths in the notes' opening section as a
# DEVIATION and left them in place, on the grounds that the file is ignored and
# that an earlier section is never rewritten. Ignored is not the same as safe
# here, and "recorded" is not a mechanism: the next reader copies the passage
# and the directory layout travels with it. So the paths are gone, and this
# check is what keeps them gone.
#
# WHAT IT REJECTS
# ---------------
# Any of the five users-directory spellings tools/scan-build-markers.ps1 scans
# the artifact for, anywhere in the notes file. Same needles, same reason, a
# different carrier - the DLL is scanned for them because a build can embed
# them, the notes are scanned for them because a person can type them.
#
# WHICH WAY THE UNHANDLED CASE FAILS (#276 / #430). A notes file that cannot be
# read is VOID and exits 3, never a pass: an unread file is not a clean one. A
# refusal here costs a reworded line, which is why it is set to refuse.
#
# Every run ends with its own two controls, EXECUTED, so the check is never
# reported as clean without having been shown it can redden (#391): a copy with
# a users-directory path inserted must FAIL, and a copy with a repo-relative
# path of the same shape inserted at the same place must stay GREEN.

param(
    [Parameter(Mandatory = $true)][string]$Notes,
    [string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) 'scr-r3-notes-privacy-controls')
)

$ErrorActionPreference = 'Stop'

# The same five spellings the artifact scan uses. Each is a prefix or a path
# segment and carries no person's name: the thing being rejected is the local
# directory LAYOUT, not any particular account.
$needles = @(
    @{ Text = 'C:\Users';  Why = 'local user directory, backslash spelling' },
    @{ Text = 'C:/Users';  Why = 'local user directory, forward-slash spelling' },
    @{ Text = 'C:\\Users'; Why = 'local user directory, escaped-backslash spelling' },
    @{ Text = '\Users\';   Why = 'any users path segment, backslash spelling' },
    @{ Text = '/Users/';   Why = 'any users path segment, forward-slash spelling' }
)

function Test-NotesFile {
    param([string]$Path)

    $result = [pscustomobject]@{ Hits = 0; Lines = 0; Report = (New-Object System.Collections.ArrayList) }
    $lines = @(Get-Content -LiteralPath $Path)
    $result.Lines = $lines.Count

    for ($i = 0; $i -lt $lines.Count; $i++) {
        foreach ($n in $needles) {
            if ($lines[$i].IndexOf($n.Text, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                $result.Hits = $result.Hits + 1
                # The whole line, not a summary of it: a check that hides what
                # it matched leaves the reader unable to act on it (#441).
                [void]$result.Report.Add(("line {0}: {1}  [{2}]" -f ($i + 1), $lines[$i].Trim(), $n.Why))
            }
        }
    }
    return $result
}

Write-Output "=== roster-census lane-notes privacy check ==="
Write-Output ("invocation:      " + [Environment]::CommandLine)
Write-Output ("invocation-utc:  " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ("notes:           " + $Notes)
Write-Output ""
Write-Output "--- the spellings this check rejects, anywhere in the notes ---"
foreach ($n in $needles) { Write-Output ("needle:          " + $n.Text + "   (" + $n.Why + ")") }
Write-Output ""

if (-not (Test-Path -LiteralPath $Notes)) {
    Write-Output ("FAIL | no such notes file: " + $Notes)
    Write-Output "NOTES VOID | the notes could not be read - an unread file is not a clean one"
    exit 3
}

$failures = 0

Write-Output "--- the notes as they stand ---"
$live = Test-NotesFile -Path $Notes
foreach ($row in $live.Report) { Write-Output ("FAIL | " + $row) }
if ($live.Hits -gt 0) { $failures = $failures + 1 }
Write-Output ("{0,-4} | lines read={1} | users-directory paths found={2}, expected 0" -f `
    $(if ($live.Hits -eq 0) { 'ok' } else { 'FAIL' }), $live.Lines, $live.Hits)

# ---- the controls, executed -------------------------------------------------

# The controls measure the CHECKER, and the scan above measures the NOTES.
# Keeping them apart matters: controls built by editing the live notes can only
# demonstrate anything while those notes are already clean, so a dirty file
# would make the mutation and its twin red together and the pair would stop
# being evidence at exactly the moment it was needed. The baseline below is a
# synthetic, known-clean file instead, so the pair says the same thing whatever
# state the notes are in.
Write-Output ""
Write-Output "--- controls (the mutation must FAIL, the inert twin must stay GREEN) ---"

if (Test-Path -LiteralPath $WorkDir) { Remove-Item -LiteralPath $WorkDir -Recurse -Force }
[void](New-Item -ItemType Directory -Path $WorkDir -Force)

$baseline = @(
    '# Lane notes - synthetic control baseline',
    '',
    '- Branch: claude/bug391-client',
    '- Logs: ai-collab/bugs/bug391-client-r3-tests-final.log',
    '- Source: plugin/RosterCensus.cs',
    ''
)
$baselinePath = Join-Path $WorkDir 'baseline.md'
[System.IO.File]::WriteAllText($baselinePath, ($baseline -join "`r`n"))

$baselineCheck = Test-NotesFile -Path $baselinePath
if ($baselineCheck.Hits -ne 0) {
    Write-Output "VOID | the synthetic control baseline is not clean - the pair below would measure nothing"
    Write-Output "NOTES VOID | the controls could not be established"
    exit 3
}
Write-Output ("ok   | control baseline is clean: lines={0} hits=0" -f $baselineCheck.Lines)

$controls = @(
    @{ Name = 'N1-inserts-a-users-directory-path'; Expect = 'FAIL';
       Insert = '- Worktree: ' + 'C:' + '/Users/<account>/Documents/scr-wt-bug391-client';
       Why = 'lens finding 7: a user path anywhere in the notes must red' },
    @{ Name = 'N1-twin-inserts-a-repo-relative-path'; Expect = 'PASS';
       Insert = '- Worktree: the lane worktree beside this repository, named for the branch';
       Why = 'inert twin: the same line, saying the same thing without the layout, stays green' }
)

foreach ($c in $controls) {
    $copy = Join-Path $WorkDir ($c.Name + '.md')
    $out = New-Object System.Collections.ArrayList
    [void]$out.Add($baseline[0])
    [void]$out.Add($c.Insert)
    for ($i = 1; $i -lt $baseline.Count; $i++) { [void]$out.Add($baseline[$i]) }
    [System.IO.File]::WriteAllText($copy, ($out -join "`r`n"))

    $got = Test-NotesFile -Path $copy
    $verdict = if ($got.Hits -eq 0) { 'PASS' } else { 'FAIL' }
    $ok = ($verdict -eq $c.Expect)
    if (-not $ok) { $failures = $failures + 1 }

    Write-Output ("{0,-4} | control={1,-38} | expected={2,-4} got={3,-4} hits={4} | {5}" -f `
        $(if ($ok) { 'ok' } else { 'BAD' }), $c.Name, $c.Expect, $verdict, $got.Hits, $c.Why)
    Write-Output ("     | inserted: " + $c.Insert)
    foreach ($row in $got.Report) { Write-Output ("     | reddened: " + $row) }
}

Write-Output ""
Write-Output ("notesLines=" + $live.Lines + " hits=" + $live.Hits + " controls=" + $controls.Count `
    + " failures=" + $failures)

if ($failures -gt 0) {
    Write-Output "NOTES FAIL"
    exit 1
}
Write-Output "NOTES PASS"
exit 0
