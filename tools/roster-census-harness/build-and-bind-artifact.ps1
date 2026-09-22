# Runs the rebuilds, captures each one's artifact, and binds the hash to a
# commit only when TWO DISTINCT BUILD INVOCATIONS are proven.
#
# WHY THIS EXISTS
# ---------------
# The build log used to carry its two verdicts - that the rebuilds MATCHED, and
# that the artifact was BOUND to the commit - as free text the author typed
# under the numbers. Both happened to be true. Neither was a value any process
# had computed, and nothing downstream could tell the difference: the evidence
# check looked for a line beginning MATCH, which a keyboard produces as easily
# as a comparison does. So the verdicts became computed, by a process that
# prints its own invocation above them.
#
# WHAT THE ROUND-3 REVIEW FOUND, AND WHY THIS IS A METHOD CHANGE
# --------------------------------------------------------------
# Computing the verdicts fixed the TYPED dimension and left the PROVENANCE
# dimension alone. The repeatability guard was:
#
#     if ($Artifacts.Count -lt 2) { REFUSED }
#
# which COUNTS ARGUMENTS. It does not establish artifact identity, and it does
# not establish that a second build ever ran. Handing the same DLL path twice
# produced two indexed hashes, one distinct value, MATCH and BOUND - a green
# repeatability verdict over one measurement written twice. A guard whose
# refusal cannot be provoked by the situation it names is a claim about the
# evidence, not a property of it (#342 / #391), and the flag named a line while
# the defect was the class: "two inputs" is not "two invocations" (#432).
#
# So the mechanism is replaced rather than patched. This script no longer
# accepts artifact paths at all. It either RUNS each rebuild itself, or it
# VERIFIES a build log in which each rebuild has its OWN section carrying the
# command it announced, the window it ran in, and the SECTION-TAGGED copy of
# the artifact taken immediately after it.
#
# WHAT IT MAKES IMPOSSIBLE
# ------------------------
# * The same artifact cannot be presented twice: the two captures must be
#   DISTINCT PATHS, and the refusal prints the two provenance lines observed.
# * One build plus a copy of its output cannot pass: a capture's own
#   LastWriteTimeUtc on disk must fall inside the build window recorded for ITS
#   OWN section and inside no other section's window. A file copied out of
#   rebuild 1 carries rebuild 1's write time wherever it is later placed, so it
#   reddens against rebuild 2's window. The windows are recorded to the
#   MILLISECOND and compared with no slack, because two rebuilds run back to
#   back are adjacent to within a few tens of milliseconds: at second
#   granularity, or with a second of slack, every capture lies inside both
#   windows and the rule stops distinguishing anything. That is not a
#   hypothetical - it is how this tool's first trial run failed.
#
# The captureWriteUtc field in the record is INFORMATIONAL. The value this
# rule reads is the one on disk now, so replacing the file cannot be hidden by
# rewriting the record, and no rule is stated over the field that a control
# does not exercise.
# * Evidence cannot simply be absent: a rebuild section with no provenance line,
#   a provenance line with a missing field, a capture that is no longer on disk,
#   or a capture whose size no longer matches what was recorded, are each a
#   refusal rather than a skipped row.
# * Two hash lines cannot outnumber the rebuild sections, because the hashes are
#   computed HERE, one per section, from that section's own capture.
#
# THE SUBJECT OF THE EVIDENCE - P2c, P2d and P8, added after the round-4 lens
# ---------------------------------------------------------------------------
# Everything above proves that TWO INVOCATIONS happened and that the two files
# hashed are two files. None of it said WHICH ARTIFACT those invocations were
# supposed to produce. `output` was required to be present and non-empty, was
# named in the per-section ok line as though it had been checked, and no rule
# compared it to anything - so the control baseline could write
# `output=(synthetic)`, which is not a path at all, and bind. A field a tool
# prints as evidence and never reads is a claim about the evidence rather than
# a property of it: the same shape as the argument-counting guard this file
# replaced, one dimension over (#342 / #391).
#
# The instance is `output`; the class is "a field the record states that no
# rule exercises". So the closure is a FIELD LEDGER rather than one more rule.
# Every field the record may carry is declared below beside the rule that
# READS it, or declared INFORMATIONAL with the reason no rule reads it. A field
# in the record the ledger does not name is a refusal; a ledger field the
# record omits is a refusal; and the ledger is PRINTED, so a reader is told
# which fields are checked instead of inferring it from an ok line (#432/#302).
#
# With the ledger in place, `output` gets the rule it lacked, in two halves:
#
# * P2d - the path each section records must RESOLVE to the artifact this run
#   was asked to bind. A log kept from a run against a different -Output, or a
#   record whose value is not that artifact, refuses and prints both the value
#   read and the path this run resolved. Because every section is measured
#   against that one resolved path, two sections naming different outputs
#   cannot both pass either.
# * P8 - the artifact standing at that path is hashed HERE and must equal the
#   hash the proven captures produced. That is what ties the bound hash to the
#   tree: captures agreeing with each other but not with the artifact the
#   recorded command produces no longer bind.
#
# WHAT THAT MAKES IMPOSSIBLE: binding a hash whose stated origin nothing
# verified. Verifying a build log against a different output path, binding a
# record whose `output` is not a path, binding captures that no longer
# correspond to the artifact in the tree, and adding a field to the record
# without either giving it a rule or declaring it unread, are each refusals
# that print the line they read.
#
# BYTE-IDENTICAL CONTENT IS THE EXPECTED OUTCOME, NOT THE DEFECT. Deterministic
# builds are meant to agree. What must be proven is that two invocations
# happened, not that their outputs differ - so two distinct invocations whose
# captures are byte-identical are GREEN, and that is the twin the controls run
# beside the copy refusal.
#
# WHAT THIS STILL CANNOT DO, STATED RATHER THAN IMPLIED (#310 / #389)
# -------------------------------------------------------------------
# It bounds ACCIDENT and ABSENCE, not fabrication. A build log whose provenance
# lines were composed by hand, beside capture files whose timestamps had been
# set to match, would satisfy every rule here. The rules are chosen so that no
# ordinary mistake - re-running the binder over one DLL, copying an artifact
# aside, forgetting the second build - can pass, and so that every refusal
# names the line it read.
#
# WHICH WAY THE UNHANDLED CASE FAILS (#276 / #430)
# ------------------------------------------------
# Every refusal is loud and exits non-zero, and each prints the observed line
# that produced it (#441). Fewer than two rebuild sections is a refusal, not a
# trivially satisfied comparison. An unreadable build log is a refusal, not a
# pass. The cost of a refusal here is one re-run of two builds.

param(
    [ValidateSet('Build', 'Verify')][string]$Mode = 'Verify',
    [Parameter(Mandatory = $true)][string]$BuildLog,
    [string]$Root = '',
    [string]$Command = 'dotnet build plugin/CompetitiveRounds.csproj -c Release -t:Rebuild -p:SkipCopyToPlugins=true',
    [string]$Output = 'plugin/bin/Release/netstandard2.1/CompetitiveRounds.dll',
    [int]$Rebuilds = 2,
    [string]$CaptureDir = '',
    [string]$Head = ''
)

$ErrorActionPreference = 'Stop'

# $Root is resolved HERE and not in the param block: a script with a Mandatory
# parameter binds its other defaults before $PSScriptRoot is populated, so the
# same expression written as a default silently resolves against an empty path.
if ($Root -eq '') {
    $Root = (Resolve-Path -LiteralPath (Join-Path (Join-Path $PSScriptRoot '..') '..')).Path
}

# THE FIELD LEDGER. Each field a provenance record may carry, beside the rule
# that reads it - or an explicit statement that no rule reads it and why. The
# record and this ledger must name the SAME set of fields: an undeclared field
# and a missing field are both refusals. This is what keeps "a field stated and
# never checked" from recurring at a sibling (#432): a new field cannot be
# added to the record without being given a rule here or declared unread here.
$script:FieldLedger = [ordered]@{
    'buildId'         = 'READ by P3 - pairwise distinct across sections, so one invocation cannot be counted twice'
    'startUtc'        = 'READ by P5 and P6 - the lower bound of the window its own capture must fall inside'
    'endUtc'          = 'READ by P5 and P6 - the upper bound of that window'
    'exit'            = 'READ by P2 - required to be 0 before anything else is measured'
    'output'          = 'READ by P2d and P8 - must resolve to the artifact THIS run was asked to bind, and that artifact is hashed'
    'capture'         = 'READ by P4, P6 and P7 - distinct per section, on disk, and the file whose sha256 is computed'
    'captureBytes'    = 'READ by P6 - reconciled against the length the file has on disk'
    'captureWriteUtc' = 'INFORMATIONAL - P6 reads the write time from DISK, never from this field, so rewriting it cannot hide a replaced file'
}

$script:RebuildHeaderRe = '^--- invocation \(rebuild (\d+) of (\d+)\) ---$'
$script:AnyHeaderRe     = '^--- invocation'
$script:ProvenanceRe    = '^provenance\((\d+)\):\s+(.+)$'
$script:EchoRe          = '^\$ (.+)$'
$script:ExitRe          = '^exit=(-?\d+)$'

function Get-Utc {
    param([datetime]$When)
    return $When.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
}

function Read-Utc {
    param([string]$Text)
    $parsed = [datetime]::MinValue
    $ok = [datetime]::TryParseExact($Text, 'yyyy-MM-ddTHH:mm:ss.fffZ',
        [System.Globalization.CultureInfo]::InvariantCulture,
        ([System.Globalization.DateTimeStyles]::AdjustToUniversal -bor [System.Globalization.DateTimeStyles]::AssumeUniversal),
        [ref]$parsed)
    if (-not $ok) { return $null }
    return $parsed
}

# ---------------------------------------------------------------------------
# BUILD MODE - runs each rebuild and writes its own section
# ---------------------------------------------------------------------------

function Invoke-BuildPhase {
    $lines = New-Object System.Collections.Generic.List[string]
    $captures = $CaptureDir
    if ($captures -eq '') {
        $captures = Join-Path ([System.IO.Path]::GetTempPath()) 'scr-r4-rebuild-captures'
    }
    if (Test-Path -LiteralPath $captures) { Remove-Item -LiteralPath $captures -Recurse -Force }
    [void](New-Item -ItemType Directory -Path $captures -Force)

    # Recorded in canonical form, so the value a later Verify reads is the same
    # shape as the one it resolves for itself (P2d compares resolved paths, so
    # this is a courtesy to the reader rather than a load-bearing step).
    $outAbs = [System.IO.Path]::GetFullPath((Join-Path $Root $Output))

    for ($i = 1; $i -le $Rebuilds; $i++) {
        $lines.Add('')
        $lines.Add(("--- invocation (rebuild {0} of {1}) ---" -f $i, $Rebuilds))
        $lines.Add('$ ' + $Command)
        $lines.Add('')

        # The previous rebuild's artifact is removed first, so a build that
        # silently did nothing cannot leave a stale file to be captured (#431).
        if (Test-Path -LiteralPath $outAbs) { Remove-Item -LiteralPath $outAbs -Force }

        $buildId = [guid]::NewGuid().ToString('N')
        $start = (Get-Date).ToUniversalTime()

        $parts = $Command.Split(' ')
        $exe = $parts[0]
        $rest = @($parts[1..($parts.Length - 1)])
        $captured = & $exe @rest 2>&1
        $code = $LASTEXITCODE
        foreach ($l in $captured) { $lines.Add([string]$l) }

        $end = (Get-Date).ToUniversalTime()
        $lines.Add(("exit={0}" -f $code))

        if (-not (Test-Path -LiteralPath $outAbs)) {
            $lines.Add(("REFUSED | rebuild {0}: the build produced no artifact at {1}" -f $i, $Output))
            foreach ($l in $lines) { Write-Output $l }
            [System.IO.File]::AppendAllLines($BuildLog, [string[]]$lines, (New-Object System.Text.UTF8Encoding($false)))
            exit 1
        }

        # SECTION-TAGGED capture, taken IMMEDIATELY after this build. The copy
        # preserves the artifact's LastWriteTimeUtc, which is what later ties
        # this file to THIS build's window and to no other.
        $capture = Join-Path $captures ("CompetitiveRounds.rebuild{0}.dll" -f $i)
        Copy-Item -LiteralPath $outAbs -Destination $capture -Force
        $item = Get-Item -LiteralPath $capture

        $lines.Add(("provenance({0}): buildId={1} startUtc={2} endUtc={3} exit={4} output={5} capture={6} captureBytes={7} captureWriteUtc={8}" -f `
            $i, $buildId, (Get-Utc $start), (Get-Utc $end), $code, $outAbs, $capture,
            $item.Length, (Get-Utc $item.LastWriteTimeUtc)))
    }

    foreach ($l in $lines) { Write-Output $l }
    [System.IO.File]::AppendAllLines($BuildLog, [string[]]$lines, (New-Object System.Text.UTF8Encoding($false)))
}

# ---------------------------------------------------------------------------
# VERIFY MODE - reads the sections back and refuses unless they prove two
# distinct invocations
# ---------------------------------------------------------------------------

function Invoke-VerifyPhase {
    $out = New-Object System.Collections.Generic.List[string]
    $failures = 0

    function Add-Refusal {
        param([string]$Why, [string[]]$Observed)
        $out.Add("REFUSED | " + $Why)
        foreach ($o in $Observed) { $out.Add("        | observed: " + $o) }
    }

    if (-not (Test-Path -LiteralPath $BuildLog)) {
        $out.Add("REFUSED | no such build log: " + $BuildLog)
        return [pscustomobject]@{ Lines = $out; Failures = 1; Refused = $true; Rebuilds = 0 }
    }
    $log = @([System.IO.File]::ReadAllLines($BuildLog))

    # ---- the sections -------------------------------------------------------
    $headers = New-Object System.Collections.ArrayList
    for ($i = 0; $i -lt $log.Count; $i++) {
        $m = [regex]::Match($log[$i], $script:RebuildHeaderRe)
        if ($m.Success) {
            [void]$headers.Add([pscustomobject]@{
                At = $i; Index = [int]$m.Groups[1].Value; Total = [int]$m.Groups[2].Value; Text = $log[$i] })
        }
    }

    $out.Add('--- the rebuild sections this log carries ---')
    foreach ($h in $headers) {
        $out.Add(("     | rebuild section {0} of {1} at build-log line {2}" -f $h.Index, $h.Total, ($h.At + 1)))
    }

    if ($headers.Count -lt 2) {
        Add-Refusal -Why ("{0} rebuild section(s) in the log; proving two distinct build invocations needs at least 2" -f $headers.Count) `
            -Observed @($(if ($headers.Count -eq 1) { $headers[0].Text } else { '(no line matched the rebuild-section header)' }))
        return [pscustomobject]@{ Lines = $out; Failures = 1; Refused = $true; Rebuilds = $headers.Count }
    }

    $n = $headers.Count
    $indices = @($headers | ForEach-Object { $_.Index })
    $wanted = @(1..$n)
    if (((@($indices | Sort-Object)) -join ',') -ne ($wanted -join ',')) {
        Add-Refusal -Why ("the rebuild sections are indexed {0}; 1..{1} is required so a section cannot be counted twice" -f `
            ($indices -join ','), $n) -Observed @($headers[0].Text)
        $failures++
    }
    $badTotals = @($headers | Where-Object { $_.Total -ne $n })
    if ($badTotals.Count -gt 0) {
        Add-Refusal -Why ("a rebuild section announces a total that is not the {0} sections present" -f $n) `
            -Observed @($badTotals[0].Text)
        $failures++
    }

    # Each section runs from its header to the next header of any kind.
    $records = New-Object System.Collections.ArrayList
    for ($s = 0; $s -lt $headers.Count; $s++) {
        $from = $headers[$s].At
        $to = $log.Count - 1
        for ($j = $from + 1; $j -lt $log.Count; $j++) {
            if ($log[$j] -match $script:AnyHeaderRe) { $to = $j - 1; break }
        }

        $echoes = @(); $provs = @(); $exits = @()
        for ($j = $from + 1; $j -le $to; $j++) {
            $me = [regex]::Match($log[$j], $script:EchoRe)
            if ($me.Success) { $echoes += ,@($j, $me.Groups[1].Value) }
            $mp = [regex]::Match($log[$j], $script:ProvenanceRe)
            if ($mp.Success) { $provs += ,@($j, [int]$mp.Groups[1].Value, $mp.Groups[2].Value, $log[$j]) }
            $mx = [regex]::Match($log[$j], $script:ExitRe)
            if ($mx.Success) { $exits += ,@($j, [int]$mx.Groups[1].Value, $log[$j]) }
        }

        [void]$records.Add([pscustomobject]@{
            Index = $headers[$s].Index; Header = $headers[$s].Text; HeaderAt = $from
            Echoes = $echoes; Provs = $provs; Exits = $exits })
    }

    # ---- P1: the command each section announced -----------------------------
    $out.Add('')
    $out.Add('--- P1: each section announces the exact build command, once ---')
    foreach ($r in $records) {
        if ($r.Echoes.Count -ne 1) {
            Add-Refusal -Why ("rebuild {0}: its section echoes {1} command(s); exactly one is required" -f $r.Index, $r.Echoes.Count) `
                -Observed @($r.Header)
            $failures++
            continue
        }
        if ($r.Echoes[0][1] -ne $Command) {
            Add-Refusal -Why ("rebuild {0}: the command it announces is not the required build command" -f $r.Index) `
                -Observed @($log[$r.Echoes[0][0]])
            $failures++
            continue
        }
        $out.Add(("ok   | P1 | rebuild {0} | build-log line {1} announces the required command" -f $r.Index, ($r.Echoes[0][0] + 1)))
    }

    # ---- P2a: exit status ---------------------------------------------------
    $out.Add('')
    $out.Add('--- P2: each section records a successful exit and its own provenance ---')
    foreach ($r in $records) {
        if ($r.Exits.Count -lt 1) {
            Add-Refusal -Why ("rebuild {0}: its section records no exit status" -f $r.Index) -Observed @($r.Header)
            $failures++
            continue
        }
        $code = $r.Exits[0][1]
        if ($code -ne 0) {
            Add-Refusal -Why ("rebuild {0}: the build exited {1}" -f $r.Index, $code) -Observed @($log[$r.Exits[0][0]])
            $failures++
            continue
        }
        $out.Add(("ok   | P2 | rebuild {0} | build-log line {1}: exit=0" -f $r.Index, ($r.Exits[0][0] + 1)))
    }

    # ---- P2b, P2c, P2d: the provenance record -------------------------------
    # ABSENCE IS A REFUSAL, never a skipped row: a section with no provenance
    # line is a rebuild nothing can be bound to. The field set is the LEDGER's
    # (P2c), and the one field that used to be printed without being read now
    # has to name the artifact this run binds (P2d).
    $fields = @($script:FieldLedger.Keys)

    # The artifact this run was asked to bind, resolved ONCE. A run that cannot
    # say what it is verifying cannot verify anything, so that is a refusal
    # rather than a skipped rule (#276 / #430).
    $expectedOut = ''
    try { $expectedOut = [System.IO.Path]::GetFullPath((Join-Path $Root $Output)) } catch { $expectedOut = '' }
    if ($expectedOut -eq '') {
        $out.Add("REFUSED | the artifact this run was asked to bind does not resolve to a path: -Root '" + $Root + "' -Output '" + $Output + "'")
        return [pscustomobject]@{ Lines = $out; Failures = ($failures + 1); Refused = $true; Rebuilds = $n }
    }
    $out.Add('     | the artifact this run binds, resolved from -Root and -Output: ' + $expectedOut)

    $prov = @{}
    foreach ($r in $records) {
        if ($r.Provs.Count -ne 1) {
            Add-Refusal -Why ("rebuild {0}: its section carries {1} provenance line(s); the distinct-invocation evidence is ABSENT or duplicated" -f `
                $r.Index, $r.Provs.Count) -Observed @($r.Header)
            $failures++
            continue
        }
        $p = $r.Provs[0]
        if ($p[1] -ne $r.Index) {
            Add-Refusal -Why ("rebuild {0}: its provenance line is indexed {1}" -f $r.Index, $p[1]) -Observed @($p[3])
            $failures++
            continue
        }
        $bag = @{}
        foreach ($tok in ($p[2] -split '\s+')) {
            $eq = $tok.IndexOf('=')
            if ($eq -gt 0) { $bag[$tok.Substring(0, $eq)] = $tok.Substring($eq + 1) }
        }
        $missing = @($fields | Where-Object { -not $bag.ContainsKey($_) -or $bag[$_] -eq '' })
        if ($missing.Count -gt 0) {
            Add-Refusal -Why ("rebuild {0}: its provenance line is missing {1}" -f $r.Index, ($missing -join ', ')) `
                -Observed @($p[3])
            $failures++
            continue
        }

        # P2c: no field may be stated that the ledger does not account for. A
        # field nothing reads is exactly the defect this stage exists to make
        # impossible, so an unknown key refuses rather than being ignored.
        $unknown = @(@($bag.Keys) | Where-Object { -not $script:FieldLedger.Contains($_) } | Sort-Object)
        if ($unknown.Count -gt 0) {
            Add-Refusal -Why ("rebuild {0}: its provenance line states {1}, which no rule reads and the field ledger does not declare" -f `
                $r.Index, ($unknown -join ', ')) -Observed @($p[3])
            $failures++
            continue
        }

        # P2d: the artifact the section says it built must be the artifact this
        # run binds. Presence was never a rule about the value (#342).
        $recorded = $bag['output']
        $resolved = ''
        try { $resolved = [System.IO.Path]::GetFullPath($recorded) } catch { $resolved = '' }
        if ($resolved -eq '' -or -not [string]::Equals($resolved, $expectedOut, [System.StringComparison]::OrdinalIgnoreCase)) {
            Add-Refusal -Why ("rebuild {0}: it records output={1}, which is not the artifact this run was asked to bind ({2})" -f `
                $r.Index, $recorded, $expectedOut) -Observed @($p[3])
            $failures++
            continue
        }

        $bag['__line'] = $p[3]
        $prov[$r.Index] = $bag
        $out.Add(("ok   | P2 | rebuild {0} | build-log line {1} records every ledger field, and its output is the artifact this run binds" -f `
            $r.Index, ($p[0] + 1)))
    }

    if ($prov.Count -ne $n) {
        $out.Add(("REFUSED | {0} of {1} rebuild sections carry a usable provenance record" -f $prov.Count, $n))
        return [pscustomobject]@{ Lines = $out; Failures = ($failures + 1); Refused = $true; Rebuilds = $n }
    }

    # ---- P3 and P4: two DISTINCT invocations --------------------------------
    $out.Add('')
    $out.Add('--- P3 and P4: the invocations and the artifacts they produced are distinct ---')

    $ids = @{}
    foreach ($k in (@($prov.Keys) | Sort-Object)) {
        $id = $prov[$k]['buildId']
        if ($ids.ContainsKey($id)) {
            Add-Refusal -Why ("rebuilds {0} and {1} record the SAME buildId, so one invocation is being counted twice" -f $ids[$id], $k) `
                -Observed @($prov[$ids[$id]]['__line'], $prov[$k]['__line'])
            $failures++
        } else { $ids[$id] = $k }
    }
    $out.Add(("{0,-4} | P3 | distinct buildIds={1} over {2} rebuild sections" -f `
        $(if ($ids.Count -eq $n) { 'ok' } else { 'FAIL' }), $ids.Count, $n))

    $paths = @{}
    foreach ($k in (@($prov.Keys) | Sort-Object)) {
        $key = $prov[$k]['capture'].ToLowerInvariant()
        if ($paths.ContainsKey($key)) {
            Add-Refusal -Why ("rebuilds {0} and {1} name the SAME artifact path, so one file is being read twice rather than two being compared" -f `
                $paths[$key], $k) -Observed @($prov[$paths[$key]]['__line'], $prov[$k]['__line'])
            $failures++
        } else { $paths[$key] = $k }
    }
    $out.Add(("{0,-4} | P4 | distinct capture paths={1} over {2} rebuild sections" -f `
        $(if ($paths.Count -eq $n) { 'ok' } else { 'FAIL' }), $paths.Count, $n))

    # ---- P5 and P6: the windows, and the capture that belongs to each -------
    $out.Add('')
    $out.Add('--- P5 and P6: each capture was taken inside its OWN build window and no other ---')

    $win = @{}
    foreach ($k in (@($prov.Keys) | Sort-Object)) {
        $s = Read-Utc $prov[$k]['startUtc']
        $e = Read-Utc $prov[$k]['endUtc']
        if ($null -eq $s -or $null -eq $e) {
            Add-Refusal -Why ("rebuild {0}: its window timestamps are not readable" -f $k) -Observed @($prov[$k]['__line'])
            $failures++; continue
        }
        if ($e -lt $s) {
            Add-Refusal -Why ("rebuild {0}: its window ends before it starts" -f $k) -Observed @($prov[$k]['__line'])
            $failures++; continue
        }
        $win[$k] = @{ Start = $s; End = $e }
    }

    if ($win.Count -eq $n) {
        for ($k = 1; $k -lt $n; $k++) {
            if ($win[$k].End -gt $win[$k + 1].Start) {
                Add-Refusal -Why ("rebuilds {0} and {1} overlap in time, so neither window identifies one invocation" -f $k, ($k + 1)) `
                    -Observed @($prov[$k]['__line'], $prov[$k + 1]['__line'])
                $failures++
            }
        }
    }

    # NO SLACK, and millisecond window bounds. Two rebuilds run back to back
    # are adjacent to within a few milliseconds, so a window widened by a
    # second would contain both captures and P6 would stop distinguishing the
    # thing it exists to distinguish - the first trial run of this tool failed
    # exactly that way. The bounds are safe without slack because the artifact
    # is written DURING the build and the window is recorded around it.
    $slack = [timespan]::Zero
    foreach ($k in (@($prov.Keys) | Sort-Object)) {
        $cp = $prov[$k]['capture']
        if (-not (Test-Path -LiteralPath $cp)) {
            Add-Refusal -Why ("rebuild {0}: its capture is no longer on disk, so nothing can be hashed for it" -f $k) `
                -Observed @($prov[$k]['__line'])
            $failures++
            continue
        }
        $item = Get-Item -LiteralPath $cp
        $declared = [int64]$prov[$k]['captureBytes']
        if ($item.Length -ne $declared) {
            Add-Refusal -Why ("rebuild {0}: its capture is {1} bytes on disk and {2} were recorded" -f $k, $item.Length, $declared) `
                -Observed @($prov[$k]['__line'])
            $failures++
            continue
        }
        $wrote = $item.LastWriteTimeUtc
        $inOwn = $false
        $inOther = @()
        foreach ($j in (@($win.Keys) | Sort-Object)) {
            if ($wrote -ge ($win[$j].Start - $slack) -and $wrote -le ($win[$j].End + $slack)) {
                if ($j -eq $k) { $inOwn = $true } else { $inOther += $j }
            }
        }
        if (-not $inOwn) {
            Add-Refusal -Why ("rebuild {0}: its capture was last written {1}, which is outside the window that rebuild recorded - an artifact produced by another invocation, or copied from one, carries that invocation's write time" -f `
                $k, (Get-Utc $wrote)) -Observed @($prov[$k]['__line'])
            $failures++
            continue
        }
        if ($inOther.Count -gt 0) {
            Add-Refusal -Why ("rebuild {0}: its capture's write time also falls inside rebuild {1}'s window, so it identifies no single invocation" -f `
                $k, ($inOther -join ' and ')) -Observed @($prov[$k]['__line'])
            $failures++
            continue
        }
        $out.Add(("ok   | P6 | rebuild {0} | capture written {1}, inside its own window {2}..{3} and no other" -f `
            $k, (Get-Utc $wrote), $prov[$k]['startUtc'], $prov[$k]['endUtc']))
    }

    if ($failures -gt 0) {
        $out.Add('')
        $out.Add(("REFUSED | two distinct build invocations are NOT proven; {0} rule(s) refused, so no hash is bound" -f $failures))
        return [pscustomobject]@{ Lines = $out; Failures = $failures; Refused = $true; Rebuilds = $n }
    }

    # ---- P7: the hashes, computed here, one per proven invocation -----------
    $out.Add('')
    $hashes = New-Object System.Collections.ArrayList
    foreach ($k in (@($prov.Keys) | Sort-Object)) {
        $cp = $prov[$k]['capture']
        $h = (Get-FileHash -LiteralPath $cp -Algorithm SHA256).Hash.ToLowerInvariant()
        [void]$hashes.Add($h)
        $out.Add(("sha256({0}): {1}   bytes {2}" -f $k, $h, (Get-Item -LiteralPath $cp).Length))
    }
    $distinct = @($hashes | Sort-Object -Unique)

    # ---- P8: the captures are the artifact this run binds -------------------
    # The captures could agree with each other and with nothing else. The
    # artifact standing at the recorded output path is hashed HERE and compared
    # with the LAST rebuild's capture, because that is the one the last build
    # left behind. A build log kept from another run, or over another output,
    # cannot reach this line with a matching hash.
    $out.Add('')
    if (-not (Test-Path -LiteralPath $expectedOut)) {
        $out.Add("REFUSED | P8 | no artifact stands at " + $expectedOut + ", so the hashes above are bound to nothing in this tree")
        return [pscustomobject]@{ Lines = $out; Failures = ($failures + 1); Refused = $true; Rebuilds = $n }
    }
    $liveHash = (Get-FileHash -LiteralPath $expectedOut -Algorithm SHA256).Hash.ToLowerInvariant()
    $lastHash = $hashes[$hashes.Count - 1]
    if ($liveHash -ne $lastHash) {
        $out.Add("REFUSED | P8 | the artifact at " + $expectedOut + " hashes " + $liveHash +
            ", and rebuild " + $n + "'s capture hashes " + $lastHash + " - the captures are not the artifact the recorded command produces")
        return [pscustomobject]@{ Lines = $out; Failures = ($failures + 1); Refused = $true; Rebuilds = $n }
    }
    $out.Add(("ok   | P8 | the artifact at the recorded output path hashes {0}, the same value rebuild {1}'s capture carries" -f $liveHash, $n))

    $reference = $prov[$n]['capture']
    $product = ''
    try { $product = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($reference).ProductVersion } catch { $product = '' }
    if ([string]::IsNullOrWhiteSpace($product)) {
        $out.Add('REFUSED | the artifact carries no ProductVersion - the commit binding cannot be read')
        return [pscustomobject]@{ Lines = $out; Failures = ($failures + 1); Refused = $true; Rebuilds = $n }
    }
    $out.Add('InformationalVersion: ' + $product)
    if ($Head -ne '') { $out.Add('head:                 ' + $Head) }
    $out.Add('')

    if ($distinct.Count -eq 1) {
        $out.Add(("MATCH | {0} of {0} proven-distinct rebuild invocations produced one sha256: {1}" -f $n, $distinct[0]))
    } else {
        $out.Add(("MISMATCH | {0} proven-distinct rebuild invocations produced {1} distinct sha256 values" -f $n, $distinct.Count))
        $failures++
    }

    if ($Head -eq '') {
        $out.Add('UNBOUND | no head was given, so the artifact is bound to no commit by this run')
        $failures++
    } elseif ($product.Contains($Head)) {
        $out.Add('BOUND | the artifact''s InformationalVersion names the commit ' + $Head)
    } else {
        $out.Add(("UNBOUND | the artifact names {0}, which does not carry {1}" -f $product, $Head))
        $failures++
    }

    return [pscustomobject]@{ Lines = $out; Failures = $failures; Refused = $false
        Rebuilds = $n; DistinctIds = $ids.Count; DistinctPaths = $paths.Count; DistinctHashes = $distinct.Count }
}

# ---------------------------------------------------------------------------

if ($Mode -eq 'Build') {
    Invoke-BuildPhase
    exit 0
}

Write-Output '=== roster-census rebuild provenance and artifact binding ==='
Write-Output ("invocation:     " + [Environment]::CommandLine)
Write-Output ("invocation-utc: " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Write-Output ("build-log:      " + $BuildLog)
Write-Output ("head:           " + $(if ($Head -eq '') { '(not asserted)' } else { $Head }))
Write-Output ''
Write-Output '--- what must hold before a hash is bound to anything ---'
Write-Output 'P1  at least two rebuild SECTIONS, indexed 1..n, each announcing the exact build command once'
Write-Output 'P2  each section records exit=0 and its own provenance line; an absent record is a refusal'
Write-Output 'P2c the record states the ledger''s fields and no others - a field no rule reads is a refusal'
Write-Output 'P2d the output each section records resolves to the artifact THIS run was asked to bind'
Write-Output 'P3  the buildIds are pairwise distinct, so one invocation cannot be counted twice'
Write-Output 'P4  the capture paths are pairwise distinct, so one file cannot be read twice'
Write-Output 'P5  the build windows do not overlap'
Write-Output 'P6  each capture is on disk at its recorded size, and its own LastWriteTimeUtc falls inside its'
Write-Output '    OWN window and no other - which is what a copy of another rebuild output cannot do'
Write-Output 'P7  only then: one sha256 per proven invocation, MATCH over them, and BOUND against the head'
Write-Output 'P8  the artifact standing at that output path hashes to the last proven capture''s value, so the'
Write-Output '    bound hash is the artifact the recorded command produces and not merely two agreeing files'
Write-Output ''
Write-Output '--- the field ledger: every field the record may carry, and the rule that reads it ---'
foreach ($k in $script:FieldLedger.Keys) {
    Write-Output ("     | {0,-16} | {1}" -f $k, $script:FieldLedger[$k])
}
Write-Output ''

$r = Invoke-VerifyPhase
foreach ($l in $r.Lines) { Write-Output $l }

Write-Output ''
if ($r.Refused) {
    Write-Output ('rebuilds=' + $r.Rebuilds + ' failures=' + $r.Failures)
    exit 1
}
Write-Output ('rebuilds=' + $r.Rebuilds + ' distinctBuildIds=' + $r.DistinctIds `
    + ' distinctCaptures=' + $r.DistinctPaths + ' distinctHashes=' + $r.DistinctHashes `
    + ' failures=' + $r.Failures)
if ($r.Failures -gt 0) { exit 1 }
exit 0
