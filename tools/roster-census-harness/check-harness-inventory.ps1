# Does the harness inventory the notes state equal the harness on disk?
#
# WHY THIS EXISTS
# ---------------
# Round 2's notes said two new scripts and listed four. Round 3 corrected the
# sentence to nine and listed nine, and the round-3 review accepted the
# correction as CORRECT BY READING - with no mutation that reddens and no inert
# twin beside it. An inventory is the kind of claim that goes stale by itself:
# the next round adds a script and the sentence is wrong again with nobody
# having touched it. A correction with no executable rejection behind it is a
# claim about the list, not a property of it (#391).
#
# THE RULE
# --------
# The notes carry a block delimited by SCR-HARNESS-INVENTORY BEGIN dir=<path>
# and SCR-HARNESS-INVENTORY END - markers that exist for no other purpose than
# to be found (#306). Inside it, every backticked token that looks like a
# PowerShell script path is a LISTED script, and the first bold number is the
# CLAIMED count.
#
# The directory named by dir= is then ENUMERATED, and:
#
#   * every *.ps1 on disk must be listed - a script added to the harness and
#     not written down is drift, and drift is what this exists to catch;
#   * every listed path must be on disk and must live under that directory;
#   * no script may be listed twice;
#   * the claimed count must equal BOTH the number listed and the number on
#     disk, so a miscount reddens even when the list itself is complete.
#
# The rule is not "there must be nine scripts" - that is the hardcoded target
# that passes forever (#342 / #431). It is that the claim and the directory must
# be the same set and the same number.
#
# WHAT IT DOES NOT DO, STATED RATHER THAN IMPLIED (#310). It governs the one
# directory the block names. A script this lane added somewhere else is outside
# it, and the reconciliation line says which directory was read and how many
# entries it held, so a reader can see the scope rather than infer it.
#
# WHICH WAY THE UNHANDLED CASE FAILS (#276 / #430). A missing notes file, a
# missing block, a block that lists nothing, or a directory that cannot be read
# are each VOID with exit 3 - never a pass. The cost of the refusal is one line
# added to a list.
#
# Every run ends with its own controls, EXECUTED against a SYNTHETIC directory
# and a SYNTHETIC block. The controls measure the CHECKER; the scan above them
# measures this lane's real harness. A filter must never discard the line it
# measures (#441), so every red names the script it is about.

param(
    [string]$Notes = '',
    [string]$Root = (Resolve-Path -LiteralPath (Join-Path (Join-Path $PSScriptRoot '..') '..')).Path,
    [string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) 'scr-r4-harness-inventory-controls')
)

$ErrorActionPreference = 'Stop'

$script:Open = 'SCR-HARNESS-INVENTORY BEGIN'
$script:Shut = 'SCR-HARNESS-INVENTORY END'

function Invoke-InventoryScan {
    param([string]$NotesPath, [string]$RootPath)

    $out = New-Object System.Collections.Generic.List[string]
    $res = [pscustomobject]@{ Lines = $out; Failures = 0; Void = $false; VoidWhy = ''
                              Listed = 0; OnDisk = 0; Dir = '' }

    if (-not (Test-Path -LiteralPath $NotesPath)) {
        $res.Void = $true; $res.VoidWhy = "no such notes file: $NotesPath"; return $res
    }
    $notes = @([System.IO.File]::ReadAllLines($NotesPath))

    $open = -1; $shut = -1
    for ($i = 0; $i -lt $notes.Count; $i++) {
        if ($notes[$i].Contains($script:Open)) {
            if ($open -ge 0) { $res.Void = $true; $res.VoidWhy = 'two inventory blocks in the notes'; return $res }
            $open = $i
        } elseif ($notes[$i].Contains($script:Shut)) {
            if ($shut -ge 0) { $res.Void = $true; $res.VoidWhy = 'two inventory block ends in the notes'; return $res }
            $shut = $i
        }
    }
    if ($open -lt 0 -or $shut -lt 0 -or $shut -le $open) {
        $res.Void = $true
        $res.VoidWhy = 'the notes carry no harness-inventory block; an absent inventory is a refusal here, not a vacuous pass'
        return $res
    }

    $md = [regex]::Match($notes[$open], 'dir=([A-Za-z0-9/._-]+)')
    if (-not $md.Success) {
        $res.Void = $true; $res.VoidWhy = 'the inventory block names no directory (dir=...), so it governs nothing'
        return $res
    }
    $dir = $md.Groups[1].Value
    $res.Dir = $dir
    $out.Add(("     | inventory block at notes line {0}, governing {1}" -f ($open + 1), $dir))

    $abs = Join-Path $RootPath $dir
    if (-not (Test-Path -LiteralPath $abs)) {
        $res.Void = $true; $res.VoidWhy = "the directory the block names does not exist: $dir"; return $res
    }

    $onDisk = @(Get-ChildItem -LiteralPath $abs -Filter '*.ps1' -File | ForEach-Object { $dir + '/' + $_.Name } | Sort-Object)
    $res.OnDisk = $onDisk.Count
    $out.Add(("     | the directory holds {0} PowerShell script(s)" -f $onDisk.Count))

    $claimed = $null
    $listed = New-Object System.Collections.Generic.List[string]
    $listedAt = @{}
    for ($i = $open + 1; $i -lt $shut; $i++) {
        $line = $notes[$i]
        if ($null -eq $claimed) {
            $mc = [regex]::Match($line, '\*\*(\d+)\*\*')
            if ($mc.Success) {
                $claimed = [int]$mc.Groups[1].Value
                $out.Add(("     | notes line {0} claims {1} script(s)" -f ($i + 1), $claimed))
            }
        }
        foreach ($m in [regex]::Matches($line, '`([A-Za-z0-9/._-]+\.ps1)`')) {
            $p = $m.Groups[1].Value
            if ($listed.Contains($p)) {
                $out.Add(("FAIL | notes line {0} lists {1} a second time; an inventory that counts one script twice is not a count" -f ($i + 1), $p))
                $res.Failures++
                continue
            }
            [void]$listed.Add($p)
            $listedAt[$p] = ($i + 1)
        }
    }
    $res.Listed = $listed.Count

    if ($listed.Count -eq 0) {
        $res.Void = $true; $res.VoidWhy = 'the inventory block lists no script, so the rule would pass vacuously'
        return $res
    }

    foreach ($p in $onDisk) {
        if (-not $listed.Contains($p)) {
            $out.Add(("FAIL | {0} is in the harness directory and the inventory does not list it" -f $p))
            $res.Failures++
        } else {
            $out.Add(("ok   | {0} | on disk, listed at notes line {1}" -f $p, $listedAt[$p]))
        }
    }
    foreach ($p in $listed) {
        if (-not ($p.StartsWith($dir + '/', [System.StringComparison]::OrdinalIgnoreCase))) {
            $out.Add(("FAIL | the inventory lists {0}, which is not under the directory the block governs" -f $p))
            $res.Failures++
            continue
        }
        if ($onDisk -notcontains $p) {
            $out.Add(("FAIL | the inventory lists {0} and the harness directory has no such script" -f $p))
            $res.Failures++
        }
    }

    if ($null -eq $claimed) {
        $out.Add('FAIL | the inventory block states no count, so nothing reconciles the list against the directory')
        $res.Failures++
    } elseif ($claimed -ne $listed.Count -or $claimed -ne $onDisk.Count) {
        $out.Add(("FAIL | the block claims {0}; the list holds {1} and the directory holds {2}" -f `
            $claimed, $listed.Count, $onDisk.Count))
        $res.Failures++
    } else {
        $out.Add(("ok   | count: claimed {0}, listed {0}, on disk {0}" -f $claimed))
    }

    return $res
}

Write-Output '=== roster-census harness-inventory check ==='
Write-Output ('invocation:     ' + [Environment]::CommandLine)
Write-Output ('invocation-utc: ' + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ('notes:          ' + $Notes)
Write-Output ('root:           ' + $Root)
Write-Output ''

if ($Notes -eq '') {
    Write-Output 'VOID | a notes file is required'
    Write-Output 'HARNESS-INVENTORY VOID'
    exit 3
}

Write-Output '--- the inventory as the notes state it, against the directory as it stands ---'
$live = Invoke-InventoryScan -NotesPath $Notes -RootPath $Root
foreach ($l in $live.Lines) { Write-Output $l }
if ($live.Void) {
    Write-Output ('VOID | ' + $live.VoidWhy)
    Write-Output 'HARNESS-INVENTORY VOID'
    exit 3
}

# ---- the controls, executed -------------------------------------------------
Write-Output ''
Write-Output '--- controls (the mutation must FAIL, the inert twin must stay GREEN) ---'

if (Test-Path -LiteralPath $WorkDir) { Remove-Item -LiteralPath $WorkDir -Recurse -Force }
$synDir = 'tools/syn-harness'
[void](New-Item -ItemType Directory -Path (Join-Path $WorkDir $synDir) -Force)
foreach ($name in @('alpha.ps1', 'beta.ps1', 'gamma.ps1')) {
    [System.IO.File]::WriteAllText((Join-Path (Join-Path $WorkDir $synDir) $name), "# synthetic control script`r`n")
}

$baseNotes = @(
    '# Synthetic notes - control baseline',
    '',
    ('<!-- SCR-HARNESS-INVENTORY BEGIN dir=' + $synDir + ' -->'),
    'The synthetic harness directory carries **3** PowerShell scripts:',
    '',
    ('1. `' + $synDir + '/alpha.ps1`'),
    ('2. `' + $synDir + '/beta.ps1`'),
    ('3. `' + $synDir + '/gamma.ps1`'),
    '<!-- SCR-HARNESS-INVENTORY END -->',
    ''
)
$basePath = Join-Path $WorkDir 'baseline-notes.md'
[System.IO.File]::WriteAllLines($basePath, $baseNotes)

$check = Invoke-InventoryScan -NotesPath $basePath -RootPath $WorkDir
if ($check.Void -or $check.Failures -gt 0) {
    Write-Output ("VOID | the synthetic baseline is not clean (failures={0} void={1}) - every pair below would measure nothing" -f `
        $check.Failures, $check.Void)
    Write-Output 'HARNESS-INVENTORY VOID | the controls could not be established'
    exit 3
}
Write-Output 'ok   | control baseline is clean: the synthetic block and the synthetic directory agree'

$controls = @(
    @{ Name = 'I1-drops-a-script-the-directory-holds'; Target = 'notes'; Expect = 'FAIL'
       From = ('3. `' + $synDir + '/gamma.ps1`'); To = '3. (and one more)'
       Why = 'round-3 finding L3: a script present and unlisted is exactly the drift reading could not catch' },
    @{ Name = 'I1-twin-exchanges-two-entries-in-the-same-list'; Target = 'notes'; Expect = 'PASS'
       From = ("1. ``" + $synDir + "/alpha.ps1``" + "`r`n" + "2. ``" + $synDir + "/beta.ps1``")
       To   = ("1. ``" + $synDir + "/beta.ps1``" + "`r`n" + "2. ``" + $synDir + "/alpha.ps1``")
       Why = 'inert twin: the same three entries, two of them exchanged' },

    @{ Name = 'I2-lists-a-script-the-directory-does-not-hold'; Target = 'notes'; Expect = 'FAIL'
       From = ('3. `' + $synDir + '/gamma.ps1`')
       To   = ("3. ``" + $synDir + "/gamma.ps1``" + "`r`n" + "4. ``" + $synDir + "/delta.ps1``")
       Why = 'an inventory naming a script nobody can open is as wrong as one omitting a script that exists' },
    @{ Name = 'I2-twin-marks-up-the-same-entry'; Target = 'notes'; Expect = 'PASS'
       From = ('3. `' + $synDir + '/gamma.ps1`'); To = ('3. **`' + $synDir + '/gamma.ps1`**')
       Why = 'inert twin: the same entry, emphasised' },

    @{ Name = 'I3-states-a-count-the-list-does-not-hold'; Target = 'notes'; Expect = 'FAIL'
       From = 'carries **3** PowerShell'; To = 'carries **4** PowerShell'
       Why = 'the miscount round 2 shipped: a complete list under a wrong number is still a wrong claim' },
    @{ Name = 'I3-twin-respells-the-same-count'; Target = 'notes'; Expect = 'PASS'
       From = 'carries **3** PowerShell'; To = 'carries **03** PowerShell'
       Why = 'inert twin: the same count, spelled differently' },

    @{ Name = 'I4-adds-a-script-to-the-directory-without-touching-the-notes'; Target = 'dir'; Expect = 'FAIL'
       Add = 'delta.ps1'
       Why = 'the drift this exists for: the harness grows and the sentence beside it does not' },
    @{ Name = 'I4-twin-adds-a-file-of-another-kind-to-the-same-directory'; Target = 'dir'; Expect = 'PASS'
       Add = 'notes.md'
       Why = 'inert twin: the same kind of change to the same directory, of a file the inventory does not govern' },

    @{ Name = 'I5-lists-one-script-twice'; Target = 'notes'; Expect = 'FAIL'
       From = ('2. `' + $synDir + '/beta.ps1`'); To = ('2. `' + $synDir + '/alpha.ps1`')
       Why = 'a list that counts one script twice has the right length and the wrong contents' },
    @{ Name = 'I5-twin-adds-a-line-naming-no-script'; Target = 'notes'; Expect = 'PASS'
       From = ('2. `' + $synDir + '/beta.ps1`')
       To   = ("2. ``" + $synDir + "/beta.ps1``" + "`r`n" + "   (each of these was added by this lane)")
       Why = 'inert twin: an insertion of the same kind at the same site, naming no script' }
)

$failures = 0
$n = 0
foreach ($c in $controls) {
    $n++
    $caseRoot = Join-Path $WorkDir ("case{0}" -f $n)
    [void](New-Item -ItemType Directory -Path (Join-Path $caseRoot $synDir) -Force)
    Copy-Item -Path (Join-Path (Join-Path $WorkDir $synDir) '*') -Destination (Join-Path $caseRoot $synDir) -Force
    $caseNotes = Join-Path $caseRoot 'notes.md'

    $edited = ''
    if ($c.Target -eq 'dir') {
        [System.IO.File]::WriteAllText($caseNotes, [System.IO.File]::ReadAllText($basePath))
        [System.IO.File]::WriteAllText((Join-Path (Join-Path $caseRoot $synDir) $c.Add), "# added by a control`r`n")
        $edited = 'added ' + $synDir + '/' + $c.Add + ' to the directory'
    } else {
        $text = [System.IO.File]::ReadAllText($basePath)
        if ($text.IndexOf($c.From, [System.StringComparison]::Ordinal) -lt 0) {
            Write-Output ('VOID | control={0} | its target text is not in the baseline - the control would measure nothing' -f $c.Name)
            Write-Output 'HARNESS-INVENTORY VOID | a control could not be applied'
            exit 3
        }
        $at = $text.IndexOf($c.From, [System.StringComparison]::Ordinal)
        $mutated = $text.Substring(0, $at) + $c.To + $text.Substring($at + $c.From.Length)
        if ([string]::Equals($mutated, $text, [System.StringComparison]::Ordinal)) {
            Write-Output ('VOID | control={0} | the edit changed no bytes' -f $c.Name)
            Write-Output 'HARNESS-INVENTORY VOID | a control changed no bytes'
            exit 3
        }
        [System.IO.File]::WriteAllText($caseNotes, $mutated)
        $edited = ($c.From -replace "`r`n", ' / ') + '   ->   ' + ($c.To -replace "`r`n", ' / ')
    }

    $r = Invoke-InventoryScan -NotesPath $caseNotes -RootPath $caseRoot
    $got = if ($r.Void) { 'VOID' } elseif ($r.Failures -gt 0) { 'FAIL' } else { 'PASS' }
    $ok = ($got -eq $c.Expect)
    if (-not $ok) { $failures++ }

    Write-Output ('{0,-4} | control={1,-62} | target={2,-5} expected={3,-4} got={4,-4} | {5}' -f `
        $(if ($ok) { 'ok' } else { 'BAD' }), $c.Name, $c.Target, $c.Expect, $got, $c.Why)
    Write-Output ('     | edited: ' + $edited)
    if ($c.Expect -eq 'FAIL') {
        foreach ($l in $r.Lines) { if ($l -like 'FAIL*') { Write-Output ('     | reddened: ' + $l) } }
    }
}

Write-Output ''
Write-Output ('dir=' + $live.Dir + ' listed=' + $live.Listed + ' onDisk=' + $live.OnDisk `
    + ' liveFailures=' + $live.Failures + ' controls=' + $controls.Count `
    + ' reds=' + @($controls | Where-Object { $_.Expect -eq 'FAIL' }).Count `
    + ' twins=' + @($controls | Where-Object { $_.Expect -eq 'PASS' }).Count `
    + ' controlFailures=' + $failures)

if ($live.Failures -gt 0 -or $failures -gt 0) {
    Write-Output 'HARNESS-INVENTORY FAIL'
    exit 1
}
Write-Output 'HARNESS-INVENTORY PASS'
exit 0
