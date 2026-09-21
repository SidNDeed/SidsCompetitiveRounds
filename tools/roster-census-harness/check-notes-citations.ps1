# Does every file:line citation in the lane notes' round-3 section still point
# at a line that says what the note says it says?
#
# WHY THIS EXISTS
# ---------------
# A citation is a claim about a LOCATION, and locations move. This round proved
# the cost twice over. The round-2 review asked for the EMITTING statement
# behind each witness row; the round-3 lens pass found the cardinality row still
# naming a method DECLARATION rather than the Append that writes " seats=".
# Then two more commits landed, RosterCensus.cs gained a hundred lines, and
# every citation into it came to name a different statement than the one the
# sentence beside it described. Nothing reddened either time, because nothing
# was checking: a citation was prose, and prose is not evidence (#302).
#
# A flag names a line; the defect is a class (#432). So the rule here is not
# "the cardinality row must cite line N" - that is the hardcoded target which
# passes forever (#342 / #431). It is that EVERY citation in the section must be
# pinned by the text printed beside it.
#
# THE RULE
# --------
# In the policed section, a backticked token of the form
#
#     `plugin/Foo.cs:120`     `tools/bar/baz.ps1:44-46`     `some-run.log:317`
#
# is a CITATION. Every other backticked token on that same notes line is an
# ANCHOR candidate. A citation holds when some anchor on its line occurs
# ORDINALLY - case-sensitively, byte for byte - inside the cited line or range
# of the cited file. When one notes line carries several citations, each must be
# satisfied by a DISTINCT anchor; otherwise a line citing :569 and :570 beside
# the anchors " fighters=" and " seats=" would accept both citations pointing at
# :570, which is the drift this exists to catch.
#
# So a citation naming a declaration where the note claims an emitter FAILS -
# the declaration does not contain the emitted text. A citation that drifts by
# one line FAILS - the anchor is no longer there. A citation with no anchor
# beside it FAILS rather than passing, because it asserts nothing checkable.
#
# WHAT IT DOES NOT DO, stated rather than implied (#310 / #302)
# ------------------------------------------------------------
# It does not judge whether the anchor is the RIGHT thing to quote. A note that
# cites a real line and quotes a real fragment of it is accepted whatever the
# prose around it argues. This bounds DRIFT and MIS-POINTING; it is not a
# reading of the argument. And it polices one section: a citation elsewhere in
# the file is out of scope and the reconciliation line says how many it read.
#
# A citation on a notes line carrying the literal marker "(r2 line)" is a
# HISTORICAL pointer into the tree an earlier round read. Those cannot be
# resolved against this tree, so they are not - but they are COUNTED and
# PRINTED, and the file they name must still exist, so a typo cannot hide among
# them.
#
# WHICH WAY THE UNHANDLED CASE FAILS (#276 / #430). Unreadable input, a section
# pattern that matches nothing, zero citations found, or a checked count that
# does not equal the found count are all VOID with exit 3 - never a pass. A rule
# that found nothing to check has not passed, and a refusal here costs one
# re-pinned line.
#
# Every run ends with its own controls, EXECUTED against a SYNTHETIC tree, so
# the check is never reported clean without having been shown it can redden
# (#391). The controls measure the CHECKER; the live scan above them measures
# the NOTES. Keeping the two apart is deliberate: controls built by editing the
# live notes can only mutate what happens to be there today.

param(
    [Parameter(Mandatory = $true)][string]$Notes,
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$LogDir,
    [string]$SectionPattern = '^#\s+Round 3\b',
    [string]$WorkDir = (Join-Path ([System.IO.Path]::GetTempPath()) 'scr-r3-notes-citation-controls')
)

$ErrorActionPreference = 'Stop'

# A citation: a lane source path, or a log named by its bare file name.
$script:CitationRe = '^(?<t>(?:plugin|tools)/[A-Za-z0-9/._-]+|[A-Za-z0-9._-]+\.log):(?<a>[0-9]+)(?:-(?<b>[0-9]+))?$'

# Perfect matching on the citation side: every citation needs its OWN anchor.
function Test-Matching {
    param([object[]]$Cands, [int]$Idx, [bool[]]$Used)
    if ($Idx -ge $Cands.Length) { return $true }
    foreach ($a in $Cands[$Idx]) {
        if (-not $Used[$a]) {
            $Used[$a] = $true
            if (Test-Matching -Cands $Cands -Idx ($Idx + 1) -Used $Used) { return $true }
            $Used[$a] = $false
        }
    }
    return $false
}

function Invoke-CitationScan {
    param(
        [string]$NotesPath,
        [string]$RootPath,
        [string]$LogPath,
        [string]$Pattern,
        [switch]$Quiet
    )

    $out = New-Object System.Collections.Generic.List[string]
    $res = [pscustomobject]@{
        Found = 0; Checked = 0; Historical = 0; Failures = 0
        Void = $false; VoidWhy = ''; Lines = $out
    }

    if (-not (Test-Path -LiteralPath $NotesPath)) {
        $res.Void = $true; $res.VoidWhy = "notes file not found: $NotesPath"; return $res
    }
    $notesLines = [System.IO.File]::ReadAllLines($NotesPath)

    $start = -1
    for ($i = 0; $i -lt $notesLines.Length; $i++) {
        if ($notesLines[$i] -match $Pattern) { $start = $i; break }
    }
    if ($start -lt 0) {
        $res.Void = $true; $res.VoidWhy = "no line matched the section pattern $Pattern"; return $res
    }
    $out.Add("section: notes line " + ($start + 1) + " to " + $notesLines.Length + "  (" + $notesLines[$start].Trim() + ")")

    $cache = @{}
    function Get-TargetLines([string]$target) {
        if ($cache.ContainsKey($target)) { return $cache[$target] }
        if ($target -match '\.log$') { $p = Join-Path $LogPath $target } else { $p = Join-Path $RootPath $target }
        if (-not (Test-Path -LiteralPath $p)) { $cache[$target] = $null; return $null }
        $cache[$target] = [System.IO.File]::ReadAllLines($p)
        return $cache[$target]
    }

    for ($i = $start; $i -lt $notesLines.Length; $i++) {
        $line = $notesLines[$i]
        if ($line -notmatch '`') { continue }

        $spans = @([regex]::Matches($line, '`([^`]+)`') | ForEach-Object { $_.Groups[1].Value })
        if ($spans.Count -eq 0) { continue }

        $cites = @(); $anchors = @()
        foreach ($s in $spans) {
            if ($s -match $script:CitationRe) { $cites += $s } else { $anchors += $s }
        }
        if ($cites.Count -eq 0) { continue }

        $isHistorical = $line.Contains('(r2 line)')
        $no = $i + 1

        $perCite = @(); $anchored = @()
        foreach ($c in $cites) {
            $res.Found++
            $m = [regex]::Match($c, $script:CitationRe)
            $target = $m.Groups['t'].Value
            $a = [int]$m.Groups['a'].Value
            $b = if ($m.Groups['b'].Success) { [int]$m.Groups['b'].Value } else { $a }

            $tl = Get-TargetLines $target
            $res.Checked++
            $perCite += ,@()

            if ($null -eq $tl) {
                $res.Failures++; $out.Add("FAIL | notes:$no | $c | the cited file does not exist"); continue
            }
            if ($isHistorical) {
                $res.Historical++
                $out.Add("hist | notes:$no | $c | a line in the tree an earlier round read; the file exists, the line is not resolved here")
                continue
            }
            if ($a -lt 1 -or $b -lt $a -or $b -gt $tl.Length) {
                $res.Failures++; $out.Add("FAIL | notes:$no | $c | out of range: that file has " + $tl.Length + " lines"); continue
            }
            if ($anchors.Count -eq 0) {
                $res.Failures++; $out.Add("FAIL | notes:$no | $c | no backticked anchor on this line, so the citation asserts nothing checkable"); continue
            }

            $hay = [string]::Join("`n", $tl[($a - 1)..($b - 1)])
            $ok = @()
            for ($k = 0; $k -lt $anchors.Count; $k++) {
                if ($hay.IndexOf($anchors[$k], [System.StringComparison]::Ordinal) -ge 0) { $ok += $k }
            }
            if ($ok.Count -eq 0) {
                $res.Failures++
                $shown = ($anchors | ForEach-Object { "'" + $_ + "'" }) -join ', '
                $out.Add("FAIL | notes:$no | $c | no anchor on this line occurs at the cited location: $shown")
                continue
            }

            $perCite[$perCite.Count - 1] = $ok
            $anchored += ($perCite.Count - 1)
            $names = ($ok | ForEach-Object { "'" + $anchors[$_] + "'" }) -join ', '
            $out.Add("ok   | notes:$no | $c | anchored by $names")
        }

        if ($anchored.Count -gt 1) {
            $cands = @()
            foreach ($j in $anchored) { $cands += ,$perCite[$j] }
            $used = New-Object 'bool[]' ($anchors.Count)
            if (-not (Test-Matching -Cands $cands -Idx 0 -Used $used)) {
                $res.Failures++
                $names = (($anchored | ForEach-Object { $cites[$_] }) -join ' + ')
                $out.Add("FAIL | notes:$no | $names | these citations cannot be satisfied by DISTINCT anchors, so at least one is not pinned by the text beside it")
            }
        }
    }

    if ($res.Found -eq 0) { $res.Void = $true; $res.VoidWhy = 'no citation found in the section - the rule would pass vacuously' }
    elseif ($res.Checked -ne $res.Found) { $res.Void = $true; $res.VoidWhy = "checked=" + $res.Checked + " does not equal found=" + $res.Found }
    return $res
}

# ---- self-printed invocation ------------------------------------------------
# A result with no invocation above it is not evidence, and this verdict is a
# result like any other.
Write-Output '=== check-notes-citations ==='
$psExe = (Get-Process -Id $PID).Path
Write-Output ("invocation:     " + $psExe + " -NoProfile -ExecutionPolicy Bypass -File " + $PSCommandPath + " -Notes " + $Notes + " -Root " + $Root + " -LogDir " + $LogDir)
Write-Output ("invocation-utc: " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ''

# ---- the live scan ----------------------------------------------------------
$live = Invoke-CitationScan -NotesPath $Notes -RootPath $Root -LogPath $LogDir -Pattern $SectionPattern
foreach ($l in $live.Lines) { Write-Output $l }
if ($live.Void) {
    Write-Output ("VOID | " + $live.VoidWhy)
    Write-Output 'CITATIONS VOID'
    exit 3
}
Write-Output ''

# ---- the controls, executed -------------------------------------------------
Write-Output '--- controls (the mutation must FAIL, the inert twin must stay GREEN) ---'

if (Test-Path -LiteralPath $WorkDir) { Remove-Item -LiteralPath $WorkDir -Recurse -Force }
New-Item -ItemType Directory -Path (Join-Path $WorkDir 'plugin') -Force | Out-Null

# A synthetic target with the shape the real defect had: a DECLARATION line and,
# below it, the statements that actually emit the two fields.
$demo = @(
    'internal static class Demo',
    '{',
    '    private static void AppendBoundaryFields(StringBuilder sb, BoundaryContext ctx)',
    '    {',
    '        sb.Append(" fighters=").Append(ctx.Fighters);',
    '        sb.Append(" seats=").Append(ctx.Seats);',
    '    }',
    '}'
)
[System.IO.File]::WriteAllLines((Join-Path $WorkDir 'plugin/Demo.cs'), $demo)

$baseNotes = @(
    '# Bug notes - synthetic control baseline',
    'Nothing above the section header is in scope.',
    '# Round 3 - synthetic control baseline',
    '| seats | `" seats="` is emitted at `plugin/Demo.cs:6` |',
    '| fighters | `" fighters="` is emitted at `plugin/Demo.cs:5` |',
    '| both | `" fighters="` at `plugin/Demo.cs:5` and `" seats="` at `plugin/Demo.cs:6` |'
)
$basePath = Join-Path $WorkDir 'baseline.md'
[System.IO.File]::WriteAllLines($basePath, $baseNotes)

$baseRes = Invoke-CitationScan -NotesPath $basePath -RootPath $WorkDir -LogPath $WorkDir -Pattern '^#\s+Round 3\b'
if ($baseRes.Void -or $baseRes.Failures -gt 0) {
    Write-Output ("VOID | the synthetic control baseline is not clean (failures=" + $baseRes.Failures + " void=" + $baseRes.Void + ") - the pairs below would measure nothing")
    Write-Output 'CITATIONS VOID | the controls could not be established'
    exit 3
}
Write-Output ("ok   | control baseline is clean: found=" + $baseRes.Found + " failures=0")

$controls = @(
    @{ Name = 'C1-repoints-an-emitter-citation-at-the-declaration'; Expect = 'FAIL'
       From = '`" seats="` is emitted at `plugin/Demo.cs:6`'
       To   = '`" seats="` is emitted at `plugin/Demo.cs:3`'
       Why  = 'lens finding 6: a row claiming an emitter may not cite the method declaration' }
    @{ Name = 'C1-twin-rewords-the-prose-around-the-same-citation'; Expect = 'PASS'
       From = '`" seats="` is emitted at `plugin/Demo.cs:6`'
       To   = 'the field `" seats="` reaches the line at `plugin/Demo.cs:6`'
       Why  = 'inert twin: the same citation and the same anchor, the sentence rewritten' }
    @{ Name = 'C2-drifts-a-citation-by-one-line';                   Expect = 'FAIL'
       From = '`" fighters="` is emitted at `plugin/Demo.cs:5`'
       To   = '`" fighters="` is emitted at `plugin/Demo.cs:4`'
       Why  = 'a commit that shifts a file must redden its citations, which is how this round found 70 stale ones' }
    @{ Name = 'C2-twin-emphasises-the-same-citation';               Expect = 'PASS'
       From = '`" fighters="` is emitted at `plugin/Demo.cs:5`'
       To   = '`" fighters="` is emitted at **`plugin/Demo.cs:5`**'
       Why  = 'inert twin: the same citation, marked up' }
    @{ Name = 'C3-removes-the-anchor-beside-a-citation';            Expect = 'FAIL'
       From = '| fighters | `" fighters="` is emitted at `plugin/Demo.cs:5` |'
       To   = '| fighters | the count is emitted at `plugin/Demo.cs:5` |'
       Why  = 'a citation with nothing quoted beside it asserts nothing checkable' }
    @{ Name = 'C3-twin-swaps-in-another-anchor-from-the-same-line'; Expect = 'PASS'
       From = '`" fighters="` is emitted at `plugin/Demo.cs:5`'
       To   = '`ctx.Fighters` is read at `plugin/Demo.cs:5`'
       Why  = 'inert twin: a different quotation, also present at the cited line' }
    @{ Name = 'C4-makes-two-citations-lean-on-one-anchor';          Expect = 'FAIL'
       From = '`" fighters="` at `plugin/Demo.cs:5` and `" seats="` at `plugin/Demo.cs:6`'
       To   = '`" fighters="` at `plugin/Demo.cs:6` and `" seats="` at `plugin/Demo.cs:6`'
       Why  = 'two citations on one line must be pinned by DISTINCT anchors' }
    @{ Name = 'C4-twin-exchanges-the-two-citations-on-that-line';   Expect = 'PASS'
       From = '`" fighters="` at `plugin/Demo.cs:5` and `" seats="` at `plugin/Demo.cs:6`'
       To   = '`" seats="` at `plugin/Demo.cs:6` and `" fighters="` at `plugin/Demo.cs:5`'
       Why  = 'inert twin: the same two citations and anchors, their order exchanged' }
)

$failures = 0
$n = 0
foreach ($c in $controls) {
    $n++
    $text = [System.IO.File]::ReadAllText($basePath)
    if ($text.IndexOf($c.From, [System.StringComparison]::Ordinal) -lt 0) {
        Write-Output ("VOID | control={0} | its target text is not in the baseline - the control would measure nothing" -f $c.Name)
        Write-Output 'CITATIONS VOID | a control could not be applied'
        exit 3
    }
    $mutated = $text.Replace($c.From, $c.To)
    # Compare ORDINALLY: a mutation that changed no bytes reads exactly like one
    # the checker caught, and -eq on strings is case-insensitive.
    if ([string]::Equals($mutated, $text, [System.StringComparison]::Ordinal)) {
        Write-Output ("VOID | control={0} | the edit changed nothing" -f $c.Name)
        Write-Output 'CITATIONS VOID | a control changed no bytes'
        exit 3
    }
    $p = Join-Path $WorkDir ("case{0}.md" -f $n)
    [System.IO.File]::WriteAllText($p, $mutated)

    $r = Invoke-CitationScan -NotesPath $p -RootPath $WorkDir -LogPath $WorkDir -Pattern '^#\s+Round 3\b'
    $got = if ($r.Void) { 'VOID' } elseif ($r.Failures -gt 0) { 'FAIL' } else { 'PASS' }
    $ok = ($got -eq $c.Expect)
    if (-not $ok) { $failures++ }
    Write-Output ("{0,-4} | control={1,-50} | expected={2,-4} got={3,-4} failures={4} | {5}" -f `
        $(if ($ok) { 'ok' } else { 'FAIL' }), $c.Name, $c.Expect, $got, $r.Failures, $c.Why)
    if ($c.Expect -eq 'FAIL') {
        foreach ($l in $r.Lines) { if ($l -like 'FAIL*') { Write-Output ("     | reddened: " + $l) } }
    }
}

Write-Output ''
Write-Output ("citationsFound=" + $live.Found + " citationsChecked=" + $live.Checked `
    + " historical=" + $live.Historical + " liveFailures=" + $live.Failures `
    + " controls=" + $controls.Count + " controlFailures=" + $failures)

if ($live.Failures -gt 0 -or $failures -gt 0) { Write-Output 'CITATIONS FAIL'; exit 1 }
Write-Output 'CITATIONS PASS'
exit 0
