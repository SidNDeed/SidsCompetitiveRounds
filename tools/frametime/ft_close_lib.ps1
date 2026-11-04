# ft_close_lib.ps1: dot-sourced by ft_vm_launch.ps1, ft_close_leased.ps1 and the F8 room watcher (ruling
# FRAME-TIME R6-A3.11.9, FIX-6b). It closes the leased game a frame-time launch started, BY IDENTITY, and nothing
# else. The identity is the launcher's pid file, one line "FT-VM-LAUNCH-PID pid=<pid> epoch=<launch epoch s>
# stamp=<utc>": the named pid must be running as ROUNDS and that process must have started inside
# [launch epoch, stamp] (whole seconds). Then:
#   1. a graceful close request (Process.CloseMainWindow: the window gets WM_CLOSE, Unity runs Application.Quit, so
#      the game's and the mod's quit hooks flush their files);
#   2. a wait of at most the bound for the process to exit;
#   3. only if it is still running at the bound, Stop-Process on that pid alone.
# It never calls C:\broadcast\quit_game.ps1: that lever belongs to the broadcast rig and keeps its full refusal.
# Any identity failure (no file, malformed line, pid not running, not ROUNDS, start outside the window) closes
# nothing. No lookup or kill by process name, ever.
#
# THE BOUND, measured from 2026-11-04's graceful game quits on this VM (quit_game.ps1's own "ROUNDS exited after ~N s"
# lines): 36 s (10:04:52Z, runs-4836fefe), 21 s (10:19:56Z, runs-4836fefe), 18 s (13:35:32Z, runs-5f460de5); the
# slowest is 36 s. 60 s is that slowest quit plus 24 s of margin for the loaded VM.
$script:FtCloseBoundMs = 60000
#
# Dry tests only: with FT_CLOSE_TEST_DIR set, the process table is <dir>\procs.txt ("<name>:<pid>:<start unix s>"
# per line), a close request is appended to <dir>\close-requested.txt and a stop to <dir>\stopped.txt (the stop also
# drops the pid from procs.txt). Nothing live is read or touched in that mode.

function FtcStamp { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ') }

function FtcProc([int]$procId) {
    # -> @{ Name; StartUnix } for a running pid, or $null
    if ($env:FT_CLOSE_TEST_DIR) {
        $f = Join-Path $env:FT_CLOSE_TEST_DIR 'procs.txt'
        foreach ($l in @(Get-Content -LiteralPath $f -ErrorAction SilentlyContinue)) {
            $a = $l.Trim().Split(':')
            if ($a.Count -eq 3 -and $a[1] -eq [string]$procId) { return @{ Name = $a[0]; StartUnix = [long]$a[2] } }
        }
        return $null
    }
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if (-not $p) { return $null }
    try { $s = [long][math]::Floor(([DateTimeOffset]$p.StartTime.ToUniversalTime()).ToUnixTimeMilliseconds() / 1000.0) } catch { $s = -1 }
    return @{ Name = $p.ProcessName; StartUnix = $s }
}

function FtcRequestClose([int]$procId) {
    if ($env:FT_CLOSE_TEST_DIR) { Add-Content -LiteralPath (Join-Path $env:FT_CLOSE_TEST_DIR 'close-requested.txt') -Value "$procId"; return $true }
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if (-not $p) { return $false }
    try { return [bool]$p.CloseMainWindow() } catch { return $false }
}

function FtcStop([int]$procId) {
    if ($env:FT_CLOSE_TEST_DIR) {
        Add-Content -LiteralPath (Join-Path $env:FT_CLOSE_TEST_DIR 'stopped.txt') -Value "$procId"
        $f = Join-Path $env:FT_CLOSE_TEST_DIR 'procs.txt'
        $keep = @(Get-Content -LiteralPath $f -ErrorAction SilentlyContinue | Where-Object { $_.Trim().Split(':')[1] -ne [string]$procId })
        Set-Content -LiteralPath $f -Value $keep
        return
    }
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}

function Test-FtLeasedIdentity([string]$PidFile) {
    # -> @{ Ok; Pid; Line }. Read only.
    $r = @{ Ok = $false; Pid = 0; Line = '' }
    if (-not $PidFile -or -not (Test-Path -LiteralPath $PidFile)) { $r.Line = "pid file absent ($PidFile)"; return $r }
    try { $line = ([IO.File]::ReadAllText($PidFile)).Trim() } catch { $r.Line = 'pid file unreadable'; return $r }
    $m = [regex]::Match($line, '^FT-VM-LAUNCH-PID pid=(\d+) epoch=(\d+) stamp=(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)$')
    if (-not $m.Success) { $r.Line = "pid file line malformed [$line]"; return $r }
    $fpid = [int]$m.Groups[1].Value; $epoch = [long]$m.Groups[2].Value
    $stamp = [DateTimeOffset]::Parse($m.Groups[3].Value, [Globalization.CultureInfo]::InvariantCulture).ToUnixTimeSeconds()
    $r.Pid = $fpid
    $p = FtcProc $fpid
    if (-not $p) { $r.Line = "pid $fpid is not running"; return $r }
    if ($p.Name -ne 'ROUNDS') { $r.Line = "pid $fpid is $($p.Name), not ROUNDS"; return $r }
    if ($p.StartUnix -lt $epoch -or $p.StartUnix -gt $stamp) { $r.Line = "pid $fpid started at $($p.StartUnix), outside [launch epoch $epoch, stamp $stamp]"; return $r }
    $r.Ok = $true
    $r.Line = "pid $fpid is the leased ROUNDS by identity (launch epoch $epoch <= start $($p.StartUnix) <= stamp $stamp)"
    return $r
}

function Close-FtLeasedGame([string]$PidFile, [scriptblock]$Emit, [int]$BoundMs = $script:FtCloseBoundMs, [int]$PollMs = 100) {
    # -> 0 graceful exit within the bound; 2 stopped at the bound and gone; 3 stopped at the bound, still running
    #    10 s later; 7 identity not shown, nothing closed. Every line goes through $Emit with "FT-CLOSE".
    $id = Test-FtLeasedIdentity $PidFile
    if (-not $id.Ok) { & $Emit "FT-CLOSE REFUSED: identity not shown ($($id.Line)); nothing closed"; return 7 }
    $procId = $id.Pid
    & $Emit "FT-CLOSE identity: $($id.Line)"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $req = FtcStamp
    $sent = FtcRequestClose $procId
    & $Emit "FT-CLOSE close-request=$req pid $procId CloseMainWindow=$sent bound=${BoundMs}ms"
    $cap = [int]($BoundMs / $PollMs) + 1
    for ($i = 0; $i -lt $cap -and $sw.ElapsedMilliseconds -lt $BoundMs; $i++) {
        if (-not (FtcProc $procId)) {
            $ms = $sw.ElapsedMilliseconds
            & $Emit "FT-CLOSE exited=$(FtcStamp) pid $procId graceful close_to_exit_ms=$ms bound=${BoundMs}ms"
            return 0
        }
        Start-Sleep -Milliseconds $PollMs
    }
    if (-not (FtcProc $procId)) {
        & $Emit "FT-CLOSE exited=$(FtcStamp) pid $procId graceful close_to_exit_ms=$($sw.ElapsedMilliseconds) bound=${BoundMs}ms"
        return 0
    }
    & $Emit "FT-CLOSE stop-at-bound=$(FtcStamp) pid $procId still running after $($sw.ElapsedMilliseconds) ms (bound ${BoundMs}ms): Stop-Process on that pid"
    FtcStop $procId
    for ($i = 0; $i -lt 100 -and (FtcProc $procId); $i++) { Start-Sleep -Milliseconds 100 }
    if (FtcProc $procId) { & $Emit "FT-CLOSE pid $procId STILL RUNNING 10 s after the stop"; return 3 }
    & $Emit "FT-CLOSE exited=$(FtcStamp) pid $procId stopped close_to_exit_ms=$($sw.ElapsedMilliseconds) bound=${BoundMs}ms"
    return 2
}
