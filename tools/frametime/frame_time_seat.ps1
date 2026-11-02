<#
frame_time_seat.ps1: the FrameTime sitting on the laptop seat (FORMAT-M-PLAN.md V2 part e; BUILD-BRIEF.md section 4).

The laptop runner starts it with no arguments (laptop_job.sh <job> frame_time_seat.ps1 7200). The laptop's session
stages it once into the runner's script folder and writes its sha256 to scr-seat/runner/frame_time_seat.sha256; the
script refuses when that file is missing or names another digest. Six steps:
  1. pre-image: the sha256 and a copy of the cfg and of the five log files (LogOutput.log, LogOutput-prev.log,
     output_log.txt, Player.log, Player-prev.log, in the folders the mod's log bundle resolves), VR6's first listing
     (BepInEx/config: the seat-evidence queue, its .tmp, every closing file and its .unverified set-aside, the
     pending and refused report files, the cfg), and the installed DLL's sha256, which must equal one staged FrameTime
     lane's digest (scr-seat/incoming/frametime-*/sha256.txt);
  2. the sentinel BepInEx/frametime/arm (seed, f18) and the launch; the game's pid is captured;
  3. a wait for "[FRAME-TIME] sitting complete" until its own deadline (TimeoutS minus 600 s), then a graceful quit,
     and a kill by the captured pid only when the game still runs 60 s later;
  4. in every outcome the sentinel removed, then printed in this order: the runs/<stamp> token (UTC), "=== log lines"
     (every [FRAME-TIME] line but the window lines), "=== saved slice" (the slice's class headers, METHOD-V4.md 3.11;
     the slice itself is saved whole in the run folder with its line count and sha256), "=== component slice" (every
     saved-slice line that carries no [FRAME-TIME] tag, verbatim: queue writes, builds, voids, refusals, the
     component tags, Failed to patch, the BepInEx banner; it sits after "=== log lines", so pull_result.py keeps it
     in log-lines.txt), "=== VR6" (VR6's second listing), then "=== restored" (step 5);
  5. the sitting's logs moved into runs/<stamp>/sitting/, the pre-image copies put back, their sha256s printed and
     compared; LogOutput-prev.log must not change during the sitting (this build makes no prev copy);
  6. not here: the Release DLL goes back by `laptop_push.sh release-restore-<sha8>` (or the backup install_remote.sh
     made), and the sitting counts as complete only when the installed sha256 equals the pre-sitting one.
The cleanups are independent (function Sitting): the shutdown runs in its own finally around the launch and the wait,
the sentinel removal in a finally around that, and step 5 in a finally around step 4; an error in any of them is
caught after its cleanup ran, printed, and mapped to an exit code, so a wait error still shuts the game down and
restores, and a step-4 error still runs step 5.
-SelfTest runs steps 1, 4 and 5 and function Sitting (with a simulated launch, wait and shutdown) against a scratch
folder of fixtures (no launch, no game file touched), once clean and once for each mutant: keep_prev_copy (the sitting
writes LogOutput-prev.log) and closing_file (the sitting writes a closing file) must fail VR6; no_component_slice
(step 4 drops "=== component slice") must fail the component check; throw_in_wait (the wait throws) and
throw_in_step4 (step 4 throws) must still print the shutdown marker, remove the sentinel, print "=== restored" with
every sha256 equal, and end with exit code 3 and 4. It prints SELFTEST PASS only when the clean run passes and every
mutant behaves as wanted.
Exit codes: 0 pass, 2 refused before the launch (a step-1 error included), 3 the sitting did not complete (a launch,
wait or shutdown error included), 4 VR6 failed (a step-4 error included), 5 a restore mismatch (a step-5 error
included), 6 the self-test failed.
#>
[CmdletBinding()]
param(
    [switch]$SelfTest,
    [int]$TimeoutS = 7200,
    [int]$Seed = 1,
    [ValidateSet('A', 'B')][string]$F18 = 'A',
    [string]$GameRoot = 'C:\Program Files (x86)\Steam\steamapps\common\ROUNDS',
    [string]$SeatRoot = (Join-Path $env:USERPROFILE 'scr-seat'),
    [string]$LocalLow = (Join-Path $env:USERPROFILE 'AppData\LocalLow')
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

$SliceClasses = @('[FRAME-TIME]', '[FPSCAP]', '[COMBAT-PERF]', '[HIT-EVIDENCE]', '[SEAT-EV]', '[HP-POINT-END]',
    '[SAW-POINT]', '[IDENTITY-CLOCK]', '[CARD-EV]', '[COMBAT-EV]', '[PEER-BUILD]', '[BUILD-PROP]', 'record queued',
    'record kept for the next launch', 'refused', 'voided', 'Failed to patch', 'BepInEx 5.')
$Vr6Named = @('CompetitiveRounds.seat-evidence.jsonl', 'CompetitiveRounds.seat-evidence.jsonl.tmp',
    'CompetitiveRounds.pending-reports.jsonl', 'CompetitiveRounds.pending-reports.jsonl.tmp',
    'CompetitiveRounds.refused-reports.jsonl', 'com.competitiverounds.mod.cfg')
$Vr6Patterns = @('CompetitiveRounds.seat-evidence.*', 'CompetitiveRounds.pending-reports.*', 'CompetitiveRounds.refused-reports.*')
# the self-test's mutant; only -SelfTest sets anything but 'none'
$script:Mutant = 'none'

$script:Out = New-Object System.Collections.Generic.List[string]
# Console.Out, never the output stream: a function's output-stream writes would become part of its return value
function Say([string]$s) { $script:Out.Add($s); [Console]::Out.WriteLine($s) }
function Print([string]$s) { [Console]::Out.WriteLine($s) }

function Sha([string]$p) {
    if (Test-Path -LiteralPath $p -PathType Leaf) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLowerInvariant() }
    return 'absent'
}

function ReadShared([string]$p) {
    # the game holds LogOutput.log open: read it with ReadWrite sharing
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { return @() }
    $fs = [System.IO.File]::Open($p, 'Open', 'Read', 'ReadWrite')
    try { $sr = New-Object System.IO.StreamReader($fs); $t = $sr.ReadToEnd() } finally { $fs.Dispose() }
    return $t -split "`r?`n"
}

function NewCtx([string]$game, [string]$seat, [string]$low) {
    $bep = Join-Path $game 'BepInEx'
    $pl = Join-Path $low 'Landfall Games\ROUNDS'
    foreach ($pub in @('Landfall Games', 'Landfall')) {
        $d = Join-Path $low ($pub + '\ROUNDS')
        if (Test-Path -LiteralPath (Join-Path $d 'Player.log')) { $pl = $d; break }
    }
    $logs = [ordered]@{
        'LogOutput.log'      = (Join-Path $bep 'LogOutput.log')
        'LogOutput-prev.log' = (Join-Path $bep 'LogOutput-prev.log')
        'output_log.txt'     = (Join-Path $game 'output_log.txt')
        'Player.log'         = (Join-Path $pl 'Player.log')
        'Player-prev.log'    = (Join-Path $pl 'Player-prev.log')
    }
    return @{
        Game = $game; Seat = $seat; Bep = $bep; Config = (Join-Path $bep 'config')
        Cfg = (Join-Path $bep 'config\com.competitiverounds.mod.cfg')
        Dll = (Join-Path $bep 'plugins\CompetitiveRounds\CompetitiveRounds.dll')
        Arm = (Join-Path $bep 'frametime\arm'); Logs = $logs
    }
}

function Vr6Listing($C) {
    if (-not (Test-Path -LiteralPath $C.Config -PathType Container)) { throw "config folder missing: $($C.Config)" }
    $l = [ordered]@{}
    foreach ($n in $Vr6Named) { $l[$n] = Sha (Join-Path $C.Config $n) }
    foreach ($pat in $Vr6Patterns) {
        foreach ($f in @(Get-ChildItem -LiteralPath $C.Config -Filter $pat -File | Sort-Object Name)) { $l[$f.Name] = Sha $f.FullName }
    }
    return $l
}

# ---- step 1
function Step1($C, [string]$run) {
    $pre = Join-Path $run 'pre'
    New-Item -ItemType Directory -Force -Path $pre | Out-Null
    $p = @{ Logs = [ordered]@{}; Cfg = (Sha $C.Cfg); Vr6 = (Vr6Listing $C); Run = $run }
    if ($p.Cfg -eq 'absent') { throw "the cfg is missing: $($C.Cfg)" }
    Copy-Item -LiteralPath $C.Cfg -Destination (Join-Path $pre 'com.competitiverounds.mod.cfg')
    foreach ($k in $C.Logs.Keys) {
        $s = Sha $C.Logs[$k]
        $p.Logs[$k] = $s
        if ($s -ne 'absent') { Copy-Item -LiteralPath $C.Logs[$k] -Destination (Join-Path $pre $k) }
        if ($s -ne 'absent' -and (Sha (Join-Path $pre $k)) -ne $s) { throw "the pre-image copy of $k differs from its source" }
        Say ("pre-image {0} {1} {2}" -f $k, $s, $C.Logs[$k])
    }
    Say ("pre-image cfg {0}" -f $p.Cfg)
    foreach ($k in $p.Vr6.Keys) { Say ("vr6 first {0} {1}" -f $k, $p.Vr6[$k]) }
    $dll = Sha $C.Dll
    $lanes = @()
    $inc = Join-Path $C.Seat 'incoming'
    if (Test-Path -LiteralPath $inc) {
        foreach ($d in @(Get-ChildItem -LiteralPath $inc -Directory -Filter 'frametime-*')) {
            $f = Join-Path $d.FullName 'sha256.txt'
            if (-not (Test-Path -LiteralPath $f)) { continue }
            $m = [regex]::Match((Get-Content -LiteralPath $f -TotalCount 1), '^[0-9a-fA-F]{64}')
            if ($m.Success -and $m.Value.ToLowerInvariant() -eq $dll) { $lanes += $d.Name }
        }
    }
    Say ("installed dll {0}; staged FrameTime lanes with that digest: {1}" -f $dll, ($(if ($lanes.Count) { $lanes -join ',' } else { 'none' })))
    $p.Dll = $dll
    $p.LaneOk = $lanes.Count -ge 1
    return $p
}

# ---- step 4
function Step4($C, $p) {
    $lines = ReadShared $C.Logs['LogOutput.log']
    Say '=== log lines'
    foreach ($ln in $lines) { if ($ln.Contains('[FRAME-TIME]') -and -not $ln.Contains('[FRAME-TIME] w ')) { Say $ln } }
    if ($script:Mutant -eq 'throw_in_step4') { throw 'mutant throw_in_step4: an error inside step 4' }
    $slice = New-Object System.Collections.Generic.List[string]
    $count = [ordered]@{}
    foreach ($cls in $SliceClasses) { $count[$cls] = 0 }
    foreach ($ln in $lines) {
        $hit = $false
        foreach ($cls in $SliceClasses) { if ($ln.Contains($cls)) { $count[$cls]++; $hit = $true } }
        if ($hit) { $slice.Add($ln) }
    }
    $sp = Join-Path $p.Run 'slice.log'
    [System.IO.File]::WriteAllLines($sp, $slice)
    Say '=== saved slice'
    foreach ($cls in $SliceClasses) { Say ("slice class {0}: {1} lines" -f $cls.Trim('[', ']'), $count[$cls]) }
    Say ("slice saved: {0} lines, sha256 {1}" -f $slice.Count, (Sha $sp))
    # the component evidence itself (3.11): every slice line without [FRAME-TIME], whose lines are under "=== log lines"
    # already (the window lines stay in slice.log on the laptop, F05)
    $comp = @($slice | Where-Object { -not $_.Contains('[FRAME-TIME]') })
    if ($script:Mutant -ne 'no_component_slice') {
        Say '=== component slice'
        Say ("component slice: {0} lines, every saved-slice line without [FRAME-TIME]" -f $comp.Count)
        foreach ($ln in $comp) { Say $ln }
    }
    Say '=== VR6'
    $after = Vr6Listing $C
    $bad = @()
    foreach ($k in (@($p.Vr6.Keys) + @($after.Keys) | Sort-Object -Unique)) {
        $a = if ($p.Vr6.Contains($k)) { $p.Vr6[$k] } else { 'absent' }
        $b = if ($after.Contains($k)) { $after[$k] } else { 'absent' }
        Say ("vr6 {0} {1} -> {2}{3}" -f $k, $a, $b, $(if ($a -ne $b) { ' CHANGED' } else { '' }))
        if ($a -ne $b) { $bad += $k }
    }
    $prev = Sha $C.Logs['LogOutput-prev.log']
    if ($prev -ne $p.Logs['LogOutput-prev.log']) { $bad += 'LogOutput-prev.log (changed during the sitting)' }
    Say ("vr6 LogOutput-prev.log during the sitting {0} -> {1}" -f $p.Logs['LogOutput-prev.log'], $prev)
    if ($bad.Count) { Say ('VR6 files FAIL: ' + ($bad -join '; ')) } else { Say 'VR6 files PASS (route counts: the parser reads the refusals lines above)' }
    return $bad.Count -eq 0
}

# ---- step 5
function Step5($C, $p) {
    $pre = Join-Path $p.Run 'pre'
    $sit = Join-Path $p.Run 'sitting'
    Say '=== restored'
    $ok = $true
    try {
        New-Item -ItemType Directory -Force -Path $sit | Out-Null
        foreach ($k in $C.Logs.Keys) {
            # each log on its own: one log's error leaves the others' restore and comparison standing
            try {
                $path = $C.Logs[$k]
                if (Test-Path -LiteralPath $path -PathType Leaf) { Move-Item -LiteralPath $path -Destination (Join-Path $sit $k) -Force }
                if ($p.Logs[$k] -ne 'absent') { Copy-Item -LiteralPath (Join-Path $pre $k) -Destination $path }
                $r = Sha $path
                $eq = $r -eq $p.Logs[$k]
                if (-not $eq) { $ok = $false }
                Say ("restored {0} {1} pre {2} {3}" -f $k, $r, $p.Logs[$k], $(if ($eq) { 'equal' } else { 'DIFFERENT' }))
            }
            catch { $ok = $false; Say ("restored {0} error: {1} DIFFERENT" -f $k, $_.Exception.Message) }
        }
    }
    finally {
        # the cfg goes back whatever happened to the logs
        try {
            if ((Sha $C.Cfg) -ne $p.Cfg) { Copy-Item -LiteralPath (Join-Path $pre 'com.competitiverounds.mod.cfg') -Destination $C.Cfg -Force }
            $rc = Sha $C.Cfg
            if ($rc -ne $p.Cfg) { $ok = $false }
            Say ("restored cfg {0} pre {1} {2}" -f $rc, $p.Cfg, $(if ($rc -eq $p.Cfg) { 'equal' } else { 'DIFFERENT' }))
        }
        catch { $ok = $false; Say ("restored cfg error: {0} DIFFERENT" -f $_.Exception.Message) }
    }
    return $ok
}

function NewRun([string]$seat) {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
    $run = Join-Path $seat ('runs\' + $stamp)
    if (Test-Path -LiteralPath $run) { throw "run folder exists: $run" }
    New-Item -ItemType Directory -Force -Path $run | Out-Null
    Say ('runs/' + $stamp)
    return $run
}

# ---- steps 2 to 5, one structure for the sitting and the self-test. $Launch ($C) returns the game process or
# nothing; $Wait ($C, $proc) returns whether the sitting completed; $Shutdown ($proc) prints a line starting
# "shutdown:". Every cleanup sits in its own finally; errors are caught after their cleanup ran and become exit codes.
function Sitting($C, $p, [scriptblock]$Launch, [scriptblock]$Wait, [scriptblock]$Shutdown) {
    $st = @{ Code = 0; Proc = $null; V = $false; R = $false }
    try {
        try {
            try {
                New-Item -ItemType Directory -Force -Path (Split-Path $C.Arm) | Out-Null
                Set-Content -LiteralPath $C.Arm -Value @("seed=$Seed", "f18=$F18") -Encoding ascii
                Say ("sentinel written: seed={0} f18={1}" -f $Seed, $F18)
                $st.Proc = & $Launch $C
                if (-not $st.Proc) { Say 'launch: no ROUNDS process within 120 s'; $st.Code = 3 }
                else {
                    Say ("launched pid {0}" -f $st.Proc.Id)
                    if (-not (& $Wait $C $st.Proc)) { $st.Code = 3 }
                }
            }
            finally {
                try { & $Shutdown $st.Proc }
                catch { Say ('shutdown error: ' + $_.Exception.Message); $st.Code = 3 }
            }
        }
        finally {
            if (Test-Path -LiteralPath $C.Arm) { Remove-Item -LiteralPath $C.Arm -Force }
            Say ("sentinel removed: {0}" -f (-not (Test-Path -LiteralPath $C.Arm)))
        }
    }
    catch { Say ('sitting error (launch, wait or sentinel): ' + $_.Exception.Message); $st.Code = 3 }
    try {
        try { $st.V = Step4 $C $p }
        catch { Say ('step 4 error: ' + $_.Exception.Message); $st.V = $false }
    }
    finally {
        try { $st.R = Step5 $C $p }
        catch { Say ('step 5 error: ' + $_.Exception.Message); $st.R = $false }
    }
    if ($st.Code -eq 0 -and -not $st.V) { $st.Code = 4 }
    if ($st.Code -eq 0 -and -not $st.R) { $st.Code = 5 }
    return $st
}

# ---- the self-test
function SelfTestOne([string]$root, [string]$mutant) {
    $script:Out = New-Object System.Collections.Generic.List[string]
    $game = Join-Path $root 'game'; $seat = Join-Path $root 'seat'; $low = Join-Path $root 'LocalLow'
    foreach ($d in @("$game\BepInEx\config", "$game\BepInEx\plugins\CompetitiveRounds", "$low\Landfall Games\ROUNDS",
            "$seat\incoming\frametime-0badc0de", "$seat\runs")) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
    $C = NewCtx $game $seat $low
    Set-Content -LiteralPath $C.Cfg -Value @('[Data]', 'AutoLogUpload = true') -Encoding ascii
    Set-Content -LiteralPath $C.Logs['LogOutput.log'] -Value 'previous session' -Encoding ascii
    Set-Content -LiteralPath $C.Logs['LogOutput-prev.log'] -Value 'session before that' -Encoding ascii
    Set-Content -LiteralPath $C.Logs['Player.log'] -Value 'unity log' -Encoding ascii
    Set-Content -LiteralPath $C.Logs['Player-prev.log'] -Value 'unity log before' -Encoding ascii
    Set-Content -LiteralPath (Join-Path $C.Config 'CompetitiveRounds.seat-evidence.jsonl') -Value '{"q":1}' -Encoding ascii
    [System.IO.File]::WriteAllBytes($C.Dll, [byte[]](1..64))
    Set-Content -LiteralPath "$seat\incoming\frametime-0badc0de\sha256.txt" -Value (Sha $C.Dll) -Encoding ascii
    $run = NewRun $seat
    $p = Step1 $C $run
    # the simulated sitting: Unity's rotation, the game's own log, and the mutant's write
    $launch = {
        param($C)
        Move-Item -LiteralPath $C.Logs['Player.log'] -Destination $C.Logs['Player-prev.log'] -Force
        Set-Content -LiteralPath $C.Logs['Player.log'] -Value 'unity log of the sitting' -Encoding ascii
        $sim = @('[Message:   BepInEx] BepInEx 5.4.19 - ROUNDS', '[Info   :CompetitiveRounds] [FRAME-TIME] settled g=-1 seed=1',
            '[Info   :CompetitiveRounds] [FRAME-TIME] w pt=1.1.1 arm=ON plant=0 partial=0 n=120',
            '[Info   :CompetitiveRounds] [FRAME-TIME] p pt=1.1.1 arm=ON gate=0 n=500',
            '[Info   :CompetitiveRounds] [FRAME-TIME] refusals why=quit pairs=1 closing:/api/v1/x=1')
        foreach ($cls in $SliceClasses) { if ($cls -notmatch 'FRAME-TIME|BepInEx') { $sim += "[Info   :CompetitiveRounds] fixture line $cls" } }
        Set-Content -LiteralPath $C.Logs['LogOutput.log'] -Value $sim -Encoding ascii
        if ($script:Mutant -eq 'keep_prev_copy') { Copy-Item -LiteralPath $C.Logs['LogOutput.log'] -Destination $C.Logs['LogOutput-prev.log'] -Force }
        if ($script:Mutant -eq 'closing_file') { Set-Content -LiteralPath (Join-Path $C.Config 'CompetitiveRounds.seat-evidence.closing-1') -Value 'x' -Encoding ascii }
        return [pscustomobject]@{ Id = 0; HasExited = $false }
    }
    $wait = {
        param($C, $proc)
        if ($script:Mutant -eq 'throw_in_wait') { throw 'mutant throw_in_wait: an error inside the wait' }
        Say 'wait ended: complete True, exited False'
        return $true
    }
    $shutdown = { param($proc) Say ("shutdown: simulated pid {0}" -f $(if ($proc) { $proc.Id } else { 'none' })) }
    $script:Mutant = $mutant
    $threw = ''
    $st = $null
    try { $st = Sitting $C $p $launch $wait $shutdown }
    catch { $threw = $_.Exception.Message }
    finally { $script:Mutant = 'none' }
    $o = @($script:Out)
    $iTok = [array]::IndexOf($o, ($o | Where-Object { $_ -like 'runs/*' } | Select-Object -First 1))
    $iLog = [array]::IndexOf($o, '=== log lines'); $iVr6 = [array]::IndexOf($o, '=== VR6'); $iRes = [array]::IndexOf($o, '=== restored')
    $iSav = [array]::IndexOf($o, '=== saved slice'); $iComp = [array]::IndexOf($o, '=== component slice')
    $order = $iTok -eq 0 -and $iTok -lt $iLog -and $iLog -lt $iSav -and $iSav -lt $iVr6 -and $iVr6 -lt $iRes
    $headers = @($o | Where-Object { $_ -like 'slice class *' }).Count -eq $SliceClasses.Count
    $allSeen = @($o | Where-Object { $_ -like 'slice class *: 0 lines' }).Count -eq 0
    $noWindow = @($o | Where-Object { $_.Contains('[FRAME-TIME] w ') }).Count -eq 0
    # the component section: after the class headers, before VR6, non-empty, one line at least per non-FRAME-TIME
    # class, and no [FRAME-TIME] line in it
    $compLines = @()
    if ($iComp -ge 0 -and $iVr6 -gt $iComp + 1) { $compLines = @($o[($iComp + 1)..($iVr6 - 1)] | Where-Object { $_ -notlike 'component slice: *' }) }
    $component = $iComp -gt $iSav -and $iComp -lt $iVr6 -and $compLines.Count -gt 0 -and
        @($compLines | Where-Object { $_.Contains('[FRAME-TIME]') }).Count -eq 0
    foreach ($cls in $SliceClasses) {
        if ($cls -eq '[FRAME-TIME]') { continue }
        if (@($compLines | Where-Object { $_.Contains($cls) }).Count -eq 0) { $component = $false }
    }
    $shut = @($o | Where-Object { $_ -like 'shutdown:*' }).Count -ge 1
    $sentinelGone = (-not (Test-Path -LiteralPath $C.Arm)) -and @($o | Where-Object { $_ -eq 'sentinel removed: True' }).Count -eq 1
    $restoredLines = @($o | Where-Object { $_ -like 'restored *' })
    $restoredAll = $iRes -ge 0 -and $restoredLines.Count -eq ($C.Logs.Count + 1) -and
        @($restoredLines | Where-Object { $_ -notlike '* equal' }).Count -eq 0
    return @{ Vr6 = $(if ($st) { $st.V } else { $false }); Restored = $(if ($st) { $st.R } else { $false }) -and $restoredAll
        Order = $order; Headers = $headers; AllSeen = $allSeen; NoWindow = $noWindow; Lane = $p.LaneOk; Component = $component
        Shutdown = $shut; SentinelGone = $sentinelGone; Threw = $threw; Code = $(if ($st) { $st.Code } else { 'none' })
    }
}

if ($SelfTest) {
    $base = Join-Path ([System.IO.Path]::GetTempPath()) ('ft-seat-selftest-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss'))
    $fail = @()
    foreach ($m in @('none', 'keep_prev_copy', 'closing_file', 'no_component_slice', 'throw_in_wait', 'throw_in_step4')) {
        Print "=== self-test run: mutant $m"
        $r = SelfTestOne (Join-Path $base $m) $m
        Print ("self-test {0}: order {1}, slice headers {2}, every class seen {3}, no window line {4}, lane {5}, VR6 {6}, component slice {7}, shutdown {8}, sentinel removed {9}, restored {10}, exit code {11}, threw '{12}'" -f
            $m, $r.Order, $r.Headers, $r.AllSeen, $r.NoWindow, $r.Lane, $r.Vr6, $r.Component, $r.Shutdown, $r.SentinelGone,
            $r.Restored, $r.Code, $r.Threw)
        # every run, the mutants that throw included: no error escapes, the game is shut down, the sentinel is removed,
        # the restore runs with every sha256 equal
        $cleanup = $r.Threw -eq '' -and $r.Shutdown -and $r.SentinelGone -and $r.Restored -and $r.Lane
        if (-not $cleanup) { $fail += "$m (an error escaped, or the shutdown, sentinel removal or restore did not happen)" }
        $full = $r.Order -and $r.Headers -and $r.AllSeen -and $r.NoWindow
        switch ($m) {
            'none' {
                if (-not $full) { $fail += 'clean run: order, headers or window lines' }
                if (-not $r.Vr6) { $fail += 'clean run: VR6 failed' }
                if (-not $r.Component) { $fail += 'clean run: the component slice is missing or incomplete' }
                if ($r.Code -ne 0) { $fail += "clean run: exit code $($r.Code)" }
            }
            { $_ -in @('keep_prev_copy', 'closing_file') } {
                if (-not ($full -and $r.Component)) { $fail += "$m (order, headers, window lines or component slice)" }
                if ($r.Vr6) { $fail += "mutant ${m}: VR6 passed (control FAILED)" }
                if ($r.Code -ne 4) { $fail += "mutant ${m}: exit code $($r.Code), not 4" }
            }
            'no_component_slice' {
                if (-not ($full -and $r.Vr6)) { $fail += "$m (order, headers, window lines or VR6)" }
                if ($r.Component) { $fail += "mutant ${m}: the component check passed (control FAILED)" }
            }
            'throw_in_wait' { if ($r.Code -ne 3) { $fail += "mutant ${m}: exit code $($r.Code), not 3" } }
            'throw_in_step4' { if ($r.Code -ne 4) { $fail += "mutant ${m}: exit code $($r.Code), not 4" } }
        }
    }
    Print "self-test scratch: $base"
    if ($fail.Count) { Print ('SELFTEST FAIL: ' + ($fail -join '; ')); exit 6 }
    Print 'SELFTEST PASS'
    exit 0
}

# ---- the sitting
$C = NewCtx $GameRoot $SeatRoot $LocalLow
$run = NewRun $SeatRoot
$own = Sha $PSCommandPath
$want = Join-Path $SeatRoot 'runner\frame_time_seat.sha256'
$rec = if (Test-Path -LiteralPath $want) { ([regex]::Match([string](Get-Content -LiteralPath $want -TotalCount 1), '(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])')).Value.ToLowerInvariant() } else { 'absent' }
Say ("script sha256 {0}; recorded at staging {1}" -f $own, $rec)
if ($rec -ne $own) { Say 'REFUSED: the script is not the staged one (step 0)'; exit 2 }
if (@(Get-Process -Name 'Rounds' -ErrorAction SilentlyContinue).Count) { Say 'REFUSED: ROUNDS is running'; exit 2 }
if (Test-Path -LiteralPath $C.Arm) { Say 'REFUSED: a sentinel is already present'; exit 2 }
try { $p = Step1 $C $run }
catch { Say ('REFUSED: step 1 failed: ' + $_.Exception.Message); exit 2 }
if (-not $p.LaneOk) { Say 'REFUSED: the installed DLL is no staged FrameTime lane (push the lane first)'; exit 2 }
$launch = {
    param($C)
    Start-Process 'steam://rungameid/1557740'
    $pr = $null
    for ($i = 0; $i -lt 60 -and -not $pr; $i++) {
        Start-Sleep -Seconds 2
        $pr = Get-Process -Name 'Rounds' -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    return $pr
}
$wait = {
    param($C, $proc)
    $deadline = (Get-Date).AddSeconds($TimeoutS - 600)
    $done = $false
    for ($i = 0; $i -lt [int](($TimeoutS - 600) / 15) + 1 -and -not $done; $i++) {
        if ((Get-Date) -gt $deadline -or $proc.HasExited) { break }
        Start-Sleep -Seconds 15
        $done = @((ReadShared $C.Logs['LogOutput.log']) | Where-Object { $_.Contains('[FRAME-TIME] sitting complete') }).Count -gt 0
    }
    Say ("wait ended: complete {0}, exited {1}" -f $done, $proc.HasExited)
    return $done
}
$shutdown = {
    param($proc)
    if (-not $proc) {
        Say ("shutdown: no pid captured (a kill only by a captured pid); ROUNDS processes now {0}" -f @(Get-Process -Name 'Rounds' -ErrorAction SilentlyContinue).Count)
        return
    }
    if (-not $proc.HasExited) {
        [void]$proc.CloseMainWindow()
        if (-not $proc.WaitForExit(60000)) { Say ("kill pid {0} after 60 s" -f $proc.Id); Stop-Process -Id $proc.Id -Force; [void]$proc.WaitForExit(30000) }
    }
    Say ("shutdown: pid {0} exited {1}" -f $proc.Id, $proc.HasExited)
    Start-Sleep -Seconds 5
}
$code = 3
try { $code = (Sitting $C $p $launch $wait $shutdown).Code }
catch { Say ('sitting error outside the steps: ' + $_.Exception.Message) }
finally {
    $bk = Get-ChildItem -LiteralPath (Join-Path $SeatRoot 'backups') -Filter 'CompetitiveRounds-*.dll' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Say ("step 6 (not here): restore the Release DLL; newest backup {0}; installed now {1}" -f $(if ($bk) { $bk.Name } else { 'none' }), (Sha $C.Dll))
    Say ("SEAT EXIT {0}" -f $code)
}
exit $code
