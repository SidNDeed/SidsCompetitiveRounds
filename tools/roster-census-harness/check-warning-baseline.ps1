# Does the warning baseline the notes state equal the one the compiler printed?
#
# WHY THIS EXISTS
# ---------------
# Round 2's notes said ten CS0414. The build log showed nine CS0414 and one
# CS0162. Round 3 corrected the sentence, and the round-3 review accepted the
# correction as VERIFIED BY READING - with no mutation that reddens and no
# inert twin beside it. A correction verified by reading is a correction until
# someone reads it again; nothing in the lane would have reddened if the next
# round wrote eight, or eleven, or dropped the CS0162 row (#391).
#
# A warning count is also the single number in this project most likely to be
# quoted from a build that never compiled: an up-to-date tree prints
# "0 Warning(s)" without invoking the compiler, so the figure and the absence of
# work are indistinguishable in the one line everybody cites (#431). That is why
# the figures here are DERIVED from the compiler's own diagnostic lines rather
# than read off the summary alone, and why the summary is then required to
# agree with them.
#
# THE RULE
# --------
# From the BUILD LOG, per rebuild section:
#
#   * every diagnostic line of the form  <file>(<line>,<col>): warning CSxxxx:
#     is read, and warnings are counted by DISTINCT IDENTITY - file, line,
#     column and code. MSBuild prints each warning twice, inline and again
#     under the summary, so a raw line count is four times the truth over two
#     rebuilds; distinct identity is the quantity the notes mean.
#   * the section's own "N Warning(s)" and "N Error(s)" summary is read, and the
#     distinct count must EQUAL the summary. A log that disagrees with itself is
#     not a baseline.
#   * the sections must agree with each other, code for code.
#
# From the NOTES, inside the block delimited by
# SCR-WARNING-BASELINE BEGIN / SCR-WARNING-BASELINE END - markers that exist for
# no other purpose than to be found (#306) - the claimed per-code figures, the
# claimed per-rebuild total and error count, and the claimed number of rebuilds.
#
# Then: every code the log shows must be claimed with the right figure, every
# code claimed must be in the log, the total must equal both the sum and the
# summary, the errors must match, and the rebuild count must equal the number of
# sections. The rule is not "CS0414 must be 9" - that is the hardcoded target
# that passes forever once the tree moves (#342 / #431). It is that the claim
# and the measurement must be the same number.
#
# WHICH WAY THE UNHANDLED CASE FAILS (#276 / #430). An unreadable log, an
# unreadable notes file, a missing block, a block with no figures, or a log with
# no rebuild section are each VOID with exit 3 - never a pass. A rule that found
# nothing to check has not passed, and the cost of the refusal is one figure
# re-read off the log.
#
# Every run ends with its own controls, EXECUTED against a SYNTHETIC log and a
# SYNTHETIC block, so the check is never reported clean without having been
# shown it can redden. The controls measure the CHECKER; the scan above them
# measures this round's real log and real notes. A filter must never discard the
# line it measures (#441), so each red prints the line that produced it.

param(
    [string]$BuildLog = '',
    [string]$Notes = '',
    [string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) 'scr-r4-warning-baseline-controls')
)

$ErrorActionPreference = 'Stop'

$script:WarnRe    = '^(?<file>.+)\((?<line>\d+),(?<col>\d+)\): warning (?<code>CS\d+):'
$script:SummaryW  = '^\s+(\d+) Warning\(s\)\s*$'
$script:SummaryE  = '^\s+(\d+) Error\(s\)\s*$'
$script:SectionRe = '^--- invocation \(rebuild (\d+) of (\d+)\) ---$'
$script:AnyHeader = '^--- invocation'
$script:BlockOpen = 'SCR-WARNING-BASELINE BEGIN'
$script:BlockShut = 'SCR-WARNING-BASELINE END'

function Measure-BuildLog {
    param([string]$Path)

    $res = [pscustomobject]@{ Void = $false; VoidWhy = ''; Sections = 0
                              Codes = @{}; Total = 0; Errors = 0; Lines = (New-Object System.Collections.Generic.List[string]) }
    if (-not (Test-Path -LiteralPath $Path)) {
        $res.Void = $true; $res.VoidWhy = "no such build log: $Path"; return $res
    }
    $log = @([System.IO.File]::ReadAllLines($Path))

    $starts = @()
    for ($i = 0; $i -lt $log.Count; $i++) { if ($log[$i] -match $script:SectionRe) { $starts += $i } }
    if ($starts.Count -lt 1) {
        $res.Void = $true; $res.VoidWhy = 'the log carries no rebuild section, so there is no per-rebuild baseline to read'
        return $res
    }
    $res.Sections = $starts.Count

    $perSection = @()
    for ($s = 0; $s -lt $starts.Count; $s++) {
        $from = $starts[$s]
        $to = $log.Count - 1
        for ($j = $from + 1; $j -lt $log.Count; $j++) {
            if ($log[$j] -match $script:AnyHeader) { $to = $j - 1; break }
        }

        $ids = @{}
        $sumW = $null; $sumE = $null
        for ($j = $from + 1; $j -le $to; $j++) {
            $m = [regex]::Match($log[$j], $script:WarnRe)
            if ($m.Success) {
                $key = ($m.Groups['file'].Value.ToLowerInvariant() + '|' + $m.Groups['line'].Value + '|' +
                        $m.Groups['col'].Value + '|' + $m.Groups['code'].Value.ToUpperInvariant())
                $ids[$key] = $m.Groups['code'].Value.ToUpperInvariant()
                continue
            }
            $mw = [regex]::Match($log[$j], $script:SummaryW)
            if ($mw.Success) { $sumW = [int]$mw.Groups[1].Value }
            $me = [regex]::Match($log[$j], $script:SummaryE)
            if ($me.Success) { $sumE = [int]$me.Groups[1].Value }
        }

        $byCode = @{}
        foreach ($k in $ids.Keys) {
            $c = $ids[$k]
            if ($byCode.ContainsKey($c)) { $byCode[$c] = $byCode[$c] + 1 } else { $byCode[$c] = 1 }
        }
        $distinct = $ids.Count

        $shown = (@($byCode.Keys | Sort-Object | ForEach-Object { $_ + '=' + $byCode[$_] }) -join ' ')
        $res.Lines.Add(("     | rebuild {0} at build-log line {1} | distinct warnings={2} ({3}) | summary: {4} Warning(s), {5} Error(s)" -f `
            ($s + 1), ($from + 1), $distinct, $shown,
            $(if ($null -ne $sumW) { $sumW } else { 'none' }), $(if ($null -ne $sumE) { $sumE } else { 'none' })))

        $perSection += ,[pscustomobject]@{ Index = ($s + 1); ByCode = $byCode; Distinct = $distinct
                                           SummaryW = $sumW; SummaryE = $sumE; Shown = $shown }
    }

    $res | Add-Member -NotePropertyName PerSection -NotePropertyValue $perSection
    return $res
}

function Read-NotesBlock {
    param([string]$Path)

    $res = [pscustomobject]@{ Void = $false; VoidWhy = ''; Codes = @{}; Total = $null
                              Errors = $null; Rebuilds = $null; At = 0
                              Lines = (New-Object System.Collections.Generic.List[string]) }
    if (-not (Test-Path -LiteralPath $Path)) {
        $res.Void = $true; $res.VoidWhy = "no such notes file: $Path"; return $res
    }
    $notes = @([System.IO.File]::ReadAllLines($Path))

    $open = -1; $shut = -1
    for ($i = 0; $i -lt $notes.Count; $i++) {
        if ($notes[$i].Contains($script:BlockOpen)) { if ($open -ge 0) { $res.Void = $true; $res.VoidWhy = 'two baseline blocks in the notes'; return $res } ; $open = $i }
        elseif ($notes[$i].Contains($script:BlockShut)) { if ($shut -ge 0) { $res.Void = $true; $res.VoidWhy = 'two baseline block ends in the notes'; return $res } ; $shut = $i }
    }
    if ($open -lt 0 -or $shut -lt 0 -or $shut -le $open) {
        $res.Void = $true
        $res.VoidWhy = 'the notes carry no warning-baseline block; an absent claim is a refusal here, not a vacuous pass'
        return $res
    }
    $res.At = $open + 1

    for ($i = $open + 1; $i -lt $shut; $i++) {
        $line = $notes[$i]
        foreach ($m in [regex]::Matches($line, '`(CS\d+)`[^*]*\*\*(\d+)\*\*')) {
            $code = $m.Groups[1].Value.ToUpperInvariant()
            if ($res.Codes.ContainsKey($code)) {
                $res.Void = $true; $res.VoidWhy = "the block claims $code twice"; return $res
            }
            $res.Codes[$code] = [int]$m.Groups[2].Value
            $res.Lines.Add(("     | notes line {0} claims {1}={2}" -f ($i + 1), $code, [int]$m.Groups[2].Value))
        }
        if ($line -match '(?i)total') {
            $nums = @([regex]::Matches($line, '\*\*(\d+)\*\*') | ForEach-Object { [int]$_.Groups[1].Value })
            if ($nums.Count -ge 2) {
                $res.Total = $nums[0]; $res.Errors = $nums[1]
                $res.Lines.Add(("     | notes line {0} claims a per-rebuild total of {1} warnings and {2} errors" -f ($i + 1), $nums[0], $nums[1]))
            }
        }
        if ($line -match '(?i)rebuild') {
            $nums = @([regex]::Matches($line, '\*\*(\d+)\*\*') | ForEach-Object { [int]$_.Groups[1].Value })
            if ($nums.Count -eq 1 -and $line -notmatch '(?i)total' -and $line -notmatch 'CS\d+') {
                $res.Rebuilds = $nums[0]
                $res.Lines.Add(("     | notes line {0} claims {1} rebuilds" -f ($i + 1), $nums[0]))
            }
        }
    }

    if ($res.Codes.Count -eq 0) {
        $res.Void = $true; $res.VoidWhy = 'the baseline block claims no per-code figure, so the rule would pass vacuously'
    }
    return $res
}

function Compare-Baseline {
    param([string]$LogPath, [string]$NotesPath)

    $out = New-Object System.Collections.Generic.List[string]
    $failures = 0

    $log = Measure-BuildLog -Path $LogPath
    foreach ($l in $log.Lines) { $out.Add($l) }
    if ($log.Void) { return [pscustomobject]@{ Lines = $out; Failures = 1; Void = $true; VoidWhy = $log.VoidWhy } }

    # the sections must agree with each other
    $ref = $log.PerSection[0]
    for ($i = 1; $i -lt $log.PerSection.Count; $i++) {
        $s = $log.PerSection[$i]
        if ($s.Shown -ne $ref.Shown) {
            $out.Add(("FAIL | rebuild {0} counted {1} and rebuild {2} counted {3}; two rebuilds of one tree must agree code for code" -f `
                $ref.Index, $ref.Shown, $s.Index, $s.Shown))
            $failures++
        }
    }
    foreach ($s in $log.PerSection) {
        if ($null -eq $s.SummaryW -or $null -eq $s.SummaryE) {
            $out.Add(("FAIL | rebuild {0} prints no warning/error summary, so its distinct count answers to nothing" -f $s.Index))
            $failures++
            continue
        }
        if ($s.Distinct -ne $s.SummaryW) {
            $out.Add(("FAIL | rebuild {0}: {1} distinct warnings were printed and the summary line says {2} Warning(s)" -f `
                $s.Index, $s.Distinct, $s.SummaryW))
            $failures++
        } else {
            $out.Add(("ok   | rebuild {0}: {1} distinct warnings, and the summary line agrees" -f $s.Index, $s.Distinct))
        }
    }

    $claim = Read-NotesBlock -Path $NotesPath
    foreach ($l in $claim.Lines) { $out.Add($l) }
    if ($claim.Void) { return [pscustomobject]@{ Lines = $out; Failures = ($failures + 1); Void = $true; VoidWhy = $claim.VoidWhy } }

    foreach ($code in (@($ref.ByCode.Keys) | Sort-Object)) {
        $measured = $ref.ByCode[$code]
        if (-not $claim.Codes.ContainsKey($code)) {
            $out.Add(("FAIL | the log shows {0} {1} warning(s) and the baseline block claims none - an omitted code is a wrong baseline" -f $measured, $code))
            $failures++
            continue
        }
        if ($claim.Codes[$code] -ne $measured) {
            $out.Add(("FAIL | {0}: the baseline block claims {1} and the log shows {2}" -f $code, $claim.Codes[$code], $measured))
            $failures++
        } else {
            $out.Add(("ok   | {0}: claimed {1}, measured {1}" -f $code, $measured))
        }
    }
    foreach ($code in (@($claim.Codes.Keys) | Sort-Object)) {
        if (-not $ref.ByCode.ContainsKey($code)) {
            $out.Add(("FAIL | the baseline block claims {0} {1} warning(s) and the log shows none of that code" -f $claim.Codes[$code], $code))
            $failures++
        }
    }

    if ($null -eq $claim.Total -or $null -eq $claim.Errors) {
        $out.Add('FAIL | the baseline block states no per-rebuild total and error count')
        $failures++
    } else {
        $sum = 0
        foreach ($c in $ref.ByCode.Keys) { $sum += $ref.ByCode[$c] }
        if ($claim.Total -ne $sum -or $claim.Total -ne $ref.SummaryW) {
            $out.Add(("FAIL | the block claims a per-rebuild total of {0}; the codes sum to {1} and the summary line says {2}" -f `
                $claim.Total, $sum, $ref.SummaryW))
            $failures++
        } else {
            $out.Add(("ok   | per-rebuild total: claimed {0}, codes sum to {0}, summary line says {0}" -f $claim.Total))
        }
        if ($claim.Errors -ne $ref.SummaryE) {
            $out.Add(("FAIL | the block claims {0} error(s) per rebuild and the log's summary says {1}" -f $claim.Errors, $ref.SummaryE))
            $failures++
        } else {
            $out.Add(("ok   | per-rebuild errors: claimed {0}, summary line says {0}" -f $claim.Errors))
        }
    }

    if ($null -eq $claim.Rebuilds) {
        $out.Add('FAIL | the baseline block states no rebuild count, so "per rebuild" answers to nothing')
        $failures++
    } elseif ($claim.Rebuilds -ne $log.Sections) {
        $out.Add(("FAIL | the block claims {0} rebuild(s) and the log carries {1} rebuild section(s)" -f $claim.Rebuilds, $log.Sections))
        $failures++
    } else {
        $out.Add(("ok   | rebuilds: claimed {0}, the log carries {0} rebuild section(s)" -f $claim.Rebuilds))
    }

    return [pscustomobject]@{ Lines = $out; Failures = $failures; Void = $false; VoidWhy = '' }
}

# ---- self-printed invocation ------------------------------------------------
Write-Output '=== roster-census warning-baseline check ==='
Write-Output ('invocation:     ' + [Environment]::CommandLine)
Write-Output ('invocation-utc: ' + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ('build-log:      ' + $BuildLog)
Write-Output ('notes:          ' + $Notes)
Write-Output ''

if ($BuildLog -eq '' -or $Notes -eq '') {
    Write-Output 'VOID | both a build log and a notes file are required'
    Write-Output 'WARNING-BASELINE VOID'
    exit 3
}

Write-Output '--- this round''s build log and this round''s claimed baseline ---'
$live = Compare-Baseline -LogPath $BuildLog -NotesPath $Notes
foreach ($l in $live.Lines) { Write-Output $l }
if ($live.Void) {
    Write-Output ('VOID | ' + $live.VoidWhy)
    Write-Output 'WARNING-BASELINE VOID'
    exit 3
}

# ---- the controls, executed -------------------------------------------------
Write-Output ''
Write-Output '--- controls (the mutation must FAIL, the inert twin must stay GREEN) ---'

if (Test-Path -LiteralPath $WorkDir) { Remove-Item -LiteralPath $WorkDir -Recurse -Force }
[void](New-Item -ItemType Directory -Path $WorkDir -Force)

$w414 = @(
    'SYN\Alpha.cs(11,5): warning CS0414: The field is assigned but never used [SYN\Syn.csproj]',
    'SYN\Alpha.cs(12,5): warning CS0414: The field is assigned but never used [SYN\Syn.csproj]',
    'SYN\Beta.cs(20,9): warning CS0414: The field is assigned but never used [SYN\Syn.csproj]'
)
$w162 = @('SYN\Gamma.cs(30,17): warning CS0162: Unreachable code detected [SYN\Syn.csproj]')
$cmd = '$ dotnet build plugin/CompetitiveRounds.csproj -c Release -t:Rebuild -p:SkipCopyToPlugins=true'

$syntheticLog = New-Object System.Collections.Generic.List[string]
$syntheticLog.Add('=== SYNTHETIC build log, written by check-warning-baseline.ps1 to be mutated (#306) ===')
for ($s = 1; $s -le 2; $s++) {
    $syntheticLog.Add('')
    $syntheticLog.Add(("--- invocation (rebuild {0} of 2) ---" -f $s))
    $syntheticLog.Add($cmd)
    $syntheticLog.Add('')
    foreach ($w in $w162) { $syntheticLog.Add($w) }
    foreach ($w in $w414) { $syntheticLog.Add($w) }
    $syntheticLog.Add('')
    $syntheticLog.Add('Build succeeded.')
    $syntheticLog.Add('')
    # MSBuild prints every warning a second time under the summary; the
    # baseline must be unmoved by that, which is why identity and not line
    # count is what is measured.
    foreach ($w in $w162) { $syntheticLog.Add($w) }
    foreach ($w in $w414) { $syntheticLog.Add($w) }
    $syntheticLog.Add('    4 Warning(s)')
    $syntheticLog.Add('    0 Error(s)')
    $syntheticLog.Add('')
    $syntheticLog.Add('exit=0')
}
$baseLog = Join-Path $WorkDir 'baseline-build.log'
[System.IO.File]::WriteAllLines($baseLog, $syntheticLog)

$syntheticNotes = @(
    '# Synthetic notes - control baseline',
    '',
    '<!-- SCR-WARNING-BASELINE BEGIN -->',
    'The warning baseline, exactly as the compiler printed it:',
    '',
    '- `CS0414`: **3** per rebuild',
    '- `CS0162`: **1** per rebuild',
    '- per-rebuild total: **4** warnings and **0** errors',
    '- counted over **2** rebuilds',
    '<!-- SCR-WARNING-BASELINE END -->',
    ''
)
$baseNotes = Join-Path $WorkDir 'baseline-notes.md'
[System.IO.File]::WriteAllLines($baseNotes, $syntheticNotes)

$check = Compare-Baseline -LogPath $baseLog -NotesPath $baseNotes
if ($check.Void -or $check.Failures -gt 0) {
    Write-Output ("VOID | the synthetic baseline is not clean (failures={0} void={1}) - every pair below would measure nothing" -f `
        $check.Failures, $check.Void)
    Write-Output 'WARNING-BASELINE VOID | the controls could not be established'
    exit 3
}
Write-Output 'ok   | control baseline is clean: the synthetic block and the synthetic log agree'

$controls = @(
    @{ Name = 'W1-claims-a-per-code-figure-the-log-does-not-show'; Target = 'notes'; Expect = 'FAIL'
       From = '`CS0414`: **3**'; To = '`CS0414`: **2**'
       Why = 'round-3 finding L2: a wrong baseline figure must redden, which is what reading alone could not do' },
    @{ Name = 'W1-twin-respells-the-same-figure-at-the-same-site'; Target = 'notes'; Expect = 'PASS'
       From = '`CS0414`: **3**'; To = '`CS0414`: **03**'
       Why = 'inert twin: the same field, the same value, spelled differently' },

    @{ Name = 'W2-claims-a-per-rebuild-total-the-codes-do-not-sum-to'; Target = 'notes'; Expect = 'FAIL'
       From = 'total: **4** warnings'; To = 'total: **5** warnings'
       Why = 'a total is a second claim about the same measurement and must agree with it' },
    @{ Name = 'W2-twin-exchanges-the-two-per-code-rows'; Target = 'notes'; Expect = 'PASS'
       From = "- ``CS0414``: **3** per rebuild`r`n- ``CS0162``: **1** per rebuild"
       To   = "- ``CS0162``: **1** per rebuild`r`n- ``CS0414``: **3** per rebuild"
       Why = 'inert twin: the same two figures, their order exchanged' },

    @{ Name = 'W3-claims-an-error-count-the-summary-does-not-show'; Target = 'notes'; Expect = 'FAIL'
       From = 'and **0** errors'; To = 'and **1** errors'
       Why = 'the error count is part of the baseline and is read from the log like the rest of it' },
    @{ Name = 'W3-twin-rewords-the-total-line-around-the-same-figures'; Target = 'notes'; Expect = 'PASS'
       From = '- per-rebuild total: **4** warnings and **0** errors'
       To   = '- the per-rebuild total is **4** warnings and **0** errors'
       Why = 'inert twin: the same line reworded, the same two figures' },

    @{ Name = 'W4-drops-a-code-the-log-shows-from-the-block'; Target = 'notes'; Expect = 'FAIL'
       From = '- `CS0162`: **1** per rebuild'; To = '- (the unreachable-code warning is not listed here)'
       Why = 'an omitted code is a wrong baseline; the block must account for every code the log prints' },
    @{ Name = 'W4-twin-adds-a-line-that-claims-no-figure'; Target = 'notes'; Expect = 'PASS'
       From = '- `CS0162`: **1** per rebuild'; To = "- ``CS0162``: **1** per rebuild`r`n- none of them is in lane code"
       Why = 'inert twin: an insertion of the same kind at the same site, claiming no figure' },

    @{ Name = 'W5-removes-a-warning-identity-from-the-log-itself'; Target = 'log'; Expect = 'FAIL'; All = $true
       From = 'SYN\Beta.cs(20,9): warning CS0414: The field is assigned but never used [SYN\Syn.csproj]'
       To   = '  Beta.cs is up to date.'
       Why = 'the figures are read from the LOG, so a log that no longer shows them must red against the claim' },
    @{ Name = 'W5-twin-rewrites-the-same-warnings-message-text'; Target = 'log'; Expect = 'PASS'; All = $true
       From = 'SYN\Beta.cs(20,9): warning CS0414: The field is assigned but never used [SYN\Syn.csproj]'
       To   = 'SYN\Beta.cs(20,9): warning CS0414: The field is never read [SYN\Syn.csproj]'
       Why = 'inert twin: the same warning identity at the same place, its message text rewritten' },

    @{ Name = 'W6-makes-the-logs-summary-disagree-with-its-own-diagnostics'; Target = 'log'; Expect = 'FAIL'; All = $true
       From = '    4 Warning(s)'; To = '    5 Warning(s)'
       Why = 'a log that disagrees with itself is not a baseline whatever the notes say' },
    @{ Name = 'W6-twin-respells-the-same-summary-figure'; Target = 'log'; Expect = 'PASS'; All = $true
       From = '    4 Warning(s)'; To = '    04 Warning(s)'
       Why = 'inert twin: the same summary figure, spelled differently' }
)

$failures = 0
$n = 0
foreach ($c in $controls) {
    $n++
    $logText = [System.IO.File]::ReadAllText($baseLog)
    $notesText = [System.IO.File]::ReadAllText($baseNotes)
    $text = if ($c.Target -eq 'log') { $logText } else { $notesText }

    if ($text.IndexOf($c.From, [System.StringComparison]::Ordinal) -lt 0) {
        Write-Output ('VOID | control={0} | its target text is not in the synthetic {1} - the control would measure nothing' -f $c.Name, $c.Target)
        Write-Output 'WARNING-BASELINE VOID | a control could not be applied'
        exit 3
    }
    $all = $false
    if ($c.ContainsKey('All')) { $all = [bool]$c.All }
    if ($all) {
        $mutated = $text.Replace($c.From, $c.To)
    } else {
        $at = $text.IndexOf($c.From, [System.StringComparison]::Ordinal)
        $mutated = $text.Substring(0, $at) + $c.To + $text.Substring($at + $c.From.Length)
    }
    if ([string]::Equals($mutated, $text, [System.StringComparison]::Ordinal)) {
        Write-Output ('VOID | control={0} | the edit changed no bytes' -f $c.Name)
        Write-Output 'WARNING-BASELINE VOID | a control changed no bytes'
        exit 3
    }

    $caseLog = Join-Path $WorkDir ("case{0}-build.log" -f $n)
    $caseNotes = Join-Path $WorkDir ("case{0}-notes.md" -f $n)
    if ($c.Target -eq 'log') {
        [System.IO.File]::WriteAllText($caseLog, $mutated)
        [System.IO.File]::WriteAllText($caseNotes, $notesText)
    } else {
        [System.IO.File]::WriteAllText($caseLog, $logText)
        [System.IO.File]::WriteAllText($caseNotes, $mutated)
    }

    $r = Compare-Baseline -LogPath $caseLog -NotesPath $caseNotes
    $got = if ($r.Void) { 'VOID' } elseif ($r.Failures -gt 0) { 'FAIL' } else { 'PASS' }
    $ok = ($got -eq $c.Expect)
    if (-not $ok) { $failures++ }

    Write-Output ('{0,-4} | control={1,-62} | target={2,-5} expected={3,-4} got={4,-4} | {5}' -f `
        $(if ($ok) { 'ok' } else { 'BAD' }), $c.Name, $c.Target, $c.Expect, $got, $c.Why)
    Write-Output ('     | edited: ' + ($c.From -replace "`r`n", ' / ') + '   ->   ' + ($c.To -replace "`r`n", ' / '))
    if ($c.Expect -eq 'FAIL') {
        foreach ($l in $r.Lines) { if ($l -like 'FAIL*') { Write-Output ('     | reddened: ' + $l) } }
    }
}

Write-Output ''
Write-Output ('controls=' + $controls.Count + ' reds=' + @($controls | Where-Object { $_.Expect -eq 'FAIL' }).Count `
    + ' twins=' + @($controls | Where-Object { $_.Expect -eq 'PASS' }).Count `
    + ' liveFailures=' + $live.Failures + ' controlFailures=' + $failures)

if ($live.Failures -gt 0 -or $failures -gt 0) {
    Write-Output 'WARNING-BASELINE FAIL'
    exit 1
}
Write-Output 'WARNING-BASELINE PASS'
exit 0
