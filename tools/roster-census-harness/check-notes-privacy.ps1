# Are the lane notes free of a local user path, a bare address, and a co-author
# attribution?
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
# WHAT ROUND 3 LEFT, AND WHY THE RULE SET GREW
# --------------------------------------------
# The path rules passed while the notes still carried a co-author name and an
# address in the same opening section. The check was reported clean because
# nothing in it was about attribution at all - a rule set that cannot fail on
# the thing in front of it is a rule set about the wrong thing (#342), and the
# flag named a spelling while the defect was the class: an identity in the
# notes, however it is carried (#432). The sanctioned maintainer name is Sid
# and only that; a commit trailer belongs on the commit, not in prose that
# travels by being copied.
#
# WHAT IT REJECTS
# ---------------
# 1. Any of the five users-directory spellings tools/scan-build-markers.ps1
#    scans the artifact for, anywhere in the notes. Same needles, same reason, a
#    different carrier - the DLL is scanned for them because a build can embed
#    them, the notes are scanned for them because a person can type them.
# 2. Any e-mail address anywhere in the notes. This is a SHAPE and not a list of
#    known addresses: a blacklist of the addresses somebody remembered would
#    pass forever on the next one (#342 / #431).
# 3. Any co-author attribution line: the trailer key followed by a colon, or by
#    an angle-bracketed value. That is the form a trailer takes when it is
#    copied out of a commit message into prose.
#
# WHAT IT DOES NOT DO, STATED RATHER THAN IMPLIED (#310 / #389). Rule 3 governs
# the trailer FORM, so the notes can still discuss the trailer as a thing - the
# key written alone, with no colon and no address after it, is not an
# attribution and stays green. And a person's name written as ordinary prose,
# with no address and no trailer key, is not caught by any of the three: no
# total rule over "is this a name" exists, and a blacklist of names would be
# the check that cannot fail. What is bounded here is every carrier that has a
# SHAPE.
#
# WHICH WAY THE UNHANDLED CASE FAILS (#276 / #430). A notes file that cannot be
# read is VOID and exits 3, never a pass: an unread file is not a clean one. A
# refusal here costs a reworded line, which is why it is set to refuse.
#
# Every run ends with its own controls, EXECUTED, so the check is never
# reported as clean without having been shown it can redden (#391). Each rule
# has a mutation that must FAIL and an INERT TWIN at the same place, of the
# same shape, that must stay GREEN.

param(
    [string]$Notes = '',
    [string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) 'scr-r4-notes-privacy-controls')
)

$ErrorActionPreference = 'Stop'

# Each rule is a LITERAL spelling or a SHAPE. Neither names a person: what is
# rejected is the local directory LAYOUT, the address FORM, and the attribution
# FORM.
$rules = @(
    @{ Kind = 'literal'; Text = 'C:\Users';  Why = 'local user directory, backslash spelling' },
    @{ Kind = 'literal'; Text = 'C:/Users';  Why = 'local user directory, forward-slash spelling' },
    @{ Kind = 'literal'; Text = 'C:\\Users'; Why = 'local user directory, escaped-backslash spelling' },
    @{ Kind = 'literal'; Text = '\Users\';   Why = 'any users path segment, backslash spelling' },
    @{ Kind = 'literal'; Text = '/Users/';   Why = 'any users path segment, forward-slash spelling' },
    @{ Kind = 'regex';   Text = '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}';
       Why = 'an e-mail address in any spelling - a shape, not a list of addresses somebody remembered' },
    @{ Kind = 'regex';   Text = '(?i)co-authored-by\s*(:|<)';
       Why = 'a co-author attribution line - the trailer belongs on the commit, not in prose that travels by being read' }
)

function Test-NotesFile {
    param([string]$Path)

    $result = [pscustomobject]@{ Hits = 0; Lines = 0; Report = (New-Object System.Collections.ArrayList) }
    $lines = @(Get-Content -LiteralPath $Path)
    $result.Lines = $lines.Count

    for ($i = 0; $i -lt $lines.Count; $i++) {
        foreach ($r in $rules) {
            $hit = $false
            if ($r.Kind -eq 'literal') {
                $hit = ($lines[$i].IndexOf($r.Text, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
            } else {
                $hit = [regex]::IsMatch($lines[$i], $r.Text)
            }
            if ($hit) {
                $result.Hits = $result.Hits + 1
                # The whole line, not a summary of it: a check that hides what
                # it matched leaves the reader unable to act on it (#441).
                [void]$result.Report.Add(("line {0}: {1}  [{2}]" -f ($i + 1), $lines[$i].Trim(), $r.Why))
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
Write-Output "--- what this check rejects, anywhere in the notes ---"
foreach ($r in $rules) { Write-Output ("rule ({0,-7}): {1}   ({2})" -f $r.Kind, $r.Text, $r.Why) }
Write-Output ""

if ($Notes -eq '' -or -not (Test-Path -LiteralPath $Notes)) {
    Write-Output ("FAIL | no such notes file: " + $Notes)
    Write-Output "NOTES VOID | the notes could not be read - an unread file is not a clean one"
    exit 3
}

$failures = 0

Write-Output "--- the notes as they stand ---"
$live = Test-NotesFile -Path $Notes
foreach ($row in $live.Report) { Write-Output ("FAIL | " + $row) }
if ($live.Hits -gt 0) { $failures = $failures + 1 }
Write-Output ("{0,-4} | lines read={1} | rules={2} | rejected patterns found={3}, expected 0" -f `
    $(if ($live.Hits -eq 0) { 'ok' } else { 'FAIL' }), $live.Lines, $rules.Count, $live.Hits)

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
    '- Logs: ai-collab/bugs/bug391-client-r4-tests-final.log',
    '- Source: plugin/RosterCensus.cs',
    ''
)
$baselinePath = Join-Path $WorkDir 'baseline.md'
[System.IO.File]::WriteAllText($baselinePath, ($baseline -join "`r`n"))

$baselineCheck = Test-NotesFile -Path $baselinePath
if ($baselineCheck.Hits -ne 0) {
    Write-Output "VOID | the synthetic control baseline is not clean - the pairs below would measure nothing"
    Write-Output "NOTES VOID | the controls could not be established"
    exit 3
}
Write-Output ("ok   | control baseline is clean: lines={0} hits=0" -f $baselineCheck.Lines)

# Every inserted string is ASSEMBLED from fragments rather than written out, so
# that this file does not itself carry the shapes it rejects.
$atSign = [char]64
$colon = [char]58
$coKey = 'Co-Authored' + '-By'

$controls = @(
    @{ Name = 'N1-inserts-a-users-directory-path'; Expect = 'FAIL';
       Insert = '- Worktree: ' + 'C:' + '/Users/<account>/Documents/scr-wt-bug391-client';
       Why = 'round-3 lens finding 7: a user path anywhere in the notes must red' },
    @{ Name = 'N1-twin-inserts-a-repo-relative-path'; Expect = 'PASS';
       Insert = '- Worktree: the lane worktree beside this repository, named for the branch';
       Why = 'inert twin: the same line, saying the same thing without the layout, stays green' },

    @{ Name = 'N2-inserts-a-bare-address'; Expect = 'FAIL';
       Insert = '- Reported by' + $colon + ' someone' + $atSign + 'example.org';
       Why = 'round-3 finding L3: an address anywhere in the notes must red, whatever it belongs to' },
    @{ Name = 'N2-twin-inserts-the-same-line-naming-a-role'; Expect = 'PASS';
       Insert = '- Reported by' + $colon + ' the lane maintainer, Sid';
       Why = 'inert twin: the same line at the same place, a sanctioned name and no address' },

    @{ Name = 'N3-inserts-a-co-author-attribution-line'; Expect = 'FAIL';
       Insert = '- ' + $coKey + $colon + ' A Name';
       Why = 'round-3 finding L3: the trailer belongs on the commit; reproduced in the notes it is an identity that travels' },
    @{ Name = 'N3-twin-refers-to-the-trailer-without-reproducing-it'; Expect = 'PASS';
       Insert = '- The commits carry the standing ' + $coKey + ' trailer the session rule requires';
       Why = 'inert twin: the same subject at the same place, the trailer named rather than reproduced' }
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

    Write-Output ("{0,-4} | control={1,-52} | expected={2,-4} got={3,-4} hits={4} | {5}" -f `
        $(if ($ok) { 'ok' } else { 'BAD' }), $c.Name, $c.Expect, $verdict, $got.Hits, $c.Why)
    Write-Output ("     | inserted: " + $c.Insert)
    foreach ($row in $got.Report) { Write-Output ("     | reddened: " + $row) }
}

Write-Output ""
Write-Output ("notesLines=" + $live.Lines + " rules=" + $rules.Count + " hits=" + $live.Hits `
    + " controls=" + $controls.Count `
    + " reds=" + @($controls | Where-Object { $_.Expect -eq 'FAIL' }).Count `
    + " twins=" + @($controls | Where-Object { $_.Expect -eq 'PASS' }).Count `
    + " failures=" + $failures)

if ($failures -gt 0) {
    Write-Output "NOTES FAIL"
    exit 1
}
Write-Output "NOTES PASS"
exit 0
