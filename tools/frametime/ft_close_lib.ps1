# ft_close_lib.ps1: dot-sourced by ft_vm_launch.ps1, ft_close_leased.ps1 and the F8 room watcher (ruling
# FRAME-TIME R6-A3.11.9, FIX-6b; R6-A3.11.18 A1). It closes the leased game a frame-time launch started, BY IDENTITY,
# and nothing else. The identity is the launcher's pid file, one line "FT-VM-LAUNCH-PID pid=<pid> epoch=<launch
# epoch s> stamp=<utc>".
#
# A1 (R6-A3.11.18): the leased game is ONE process object. The identity read is the only read by number: the pid
# file's pid is opened once ([Diagnostics.Process]::GetProcessById) and that object's handle is taken at once and
# kept (Process.Handle stores it in the object; every later HasExited, Kill and wait on the object uses that same
# handle). The image name and the start time are then read THROUGH THAT HANDLE (QueryFullProcessImageNameW,
# GetProcessTimes): the name must be ROUNDS and the start must lie inside [launch epoch, stamp] (whole seconds).
# The close request, the wait and the stop at the bound act on that object only:
#   1. a graceful close request (Process.CloseMainWindow on the object: the window gets WM_CLOSE, Unity runs
#      Application.Quit, so the game's and the mod's quit hooks flush their files). The window is found by the
#      object's own id while its handle is held open, and Windows never gives an id to a new process while a handle
#      to the old one is open, so that id cannot name another process;
#   2. a wait of at most the bound for the object to exit (HasExited through the held handle);
#   3. only if it is still running at the bound, Kill on the object (TerminateProcess through the held handle).
# No process is read, found, closed or stopped by number after the identity read, and none by name, ever. It never
# calls C:\broadcast\quit_game.ps1: that lever belongs to the broadcast rig and keeps its full refusal. Any identity
# failure (no file, malformed line, pid not running, no handle, a read through the handle failing, not ROUNDS, start
# outside the window) closes nothing (code 7).
# A read that fails is never taken as "exited": HasExited throwing counts as still running, so a failed read can
# only lengthen the wait to the bound and lead to the stop, never end the close as graceful.
#
# THE BOUND, measured from 2026-11-04's graceful game quits on this VM (quit_game.ps1's own "ROUNDS exited after ~N s"
# lines): 36 s (10:04:52Z, runs-4836fefe), 21 s (10:19:56Z, runs-4836fefe), 18 s (13:35:32Z, runs-5f460de5); the
# slowest is 36 s. 60 s is that slowest quit plus 24 s of margin for the loaded VM.
$script:FtCloseBoundMs = 60000
$script:FtcWantName = 'ROUNDS'
#
# Dry tests only (never set on a real run):
#   FT_CLOSE_TEST_DIR: the process table is <dir>\procs.txt, one "<name>:<pid>:<start unix s>" per line. A
#     test object is bound to its (pid, start) pair: it has exited when no line carries that pair, so an entry that
#     takes the same pid with another start (a stand-in for a pid given to another process) is a different object
#     and is never touched. A close request appends "<pid>:<start>" to <dir>\close-requested.txt, a stop appends it
#     to <dir>\stopped.txt and drops the object's own line (a stand-in that re-adds it is a stop that fails).
#     With <dir>\procs.unreadable present every read of the table fails. FT_CLOSE_TEST_BOUND_MS sets the bound.
#   FT_CLOSE_TEST_LIVE_NAME: the live path (real handle, real close) expects this image name instead of ROUNDS, so a
#     control can run it against a harmless stand-in process.
if ($env:FT_CLOSE_TEST_DIR -and $env:FT_CLOSE_TEST_BOUND_MS) { $script:FtCloseBoundMs = [int]$env:FT_CLOSE_TEST_BOUND_MS }
if ($env:FT_CLOSE_TEST_LIVE_NAME -and -not $env:FT_CLOSE_TEST_DIR) { $script:FtcWantName = $env:FT_CLOSE_TEST_LIVE_NAME }

function FtcStamp { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ') }

function FtcTestTable {
    # -> the dry table's lines, or $null when the table cannot be read (never an empty table on a failed read)
    $d = $env:FT_CLOSE_TEST_DIR
    if (Test-Path -LiteralPath (Join-Path $d 'procs.unreadable')) { return $null }
    $f = Join-Path $d 'procs.txt'
    if (-not (Test-Path -LiteralPath $f)) { return ,@() }
    try { return ,@(Get-Content -LiteralPath $f -ErrorAction Stop) } catch { return $null }
}

function FtcNativeLoad {
    if ('FtcNative' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class FtcNative {
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool QueryFullProcessImageNameW(IntPtr h, int flags, StringBuilder name, ref int size);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetProcessTimes(IntPtr h, out long creation, out long exit, out long kernel, out long user);
    public static string ImagePath(IntPtr h) {
        StringBuilder sb = new StringBuilder(1024); int n = sb.Capacity;
        return QueryFullProcessImageNameW(h, 0, sb, ref n) ? sb.ToString(0, n) : null;
    }
    public static long StartFileTime(IntPtr h) {
        long c, e, k, u;
        return GetProcessTimes(h, out c, out e, out k, out u) ? c : -1;
    }
}
'@
}

function FtcOpen([int]$procId) {
    # THE identity read, the only read by number: -> @{ Ok; Err; Pid; Name; StartUnix; Proc (live) | Start (dry) }
    $r = @{ Ok = $false; Err = ''; Pid = $procId; Name = ''; StartUnix = -1; Proc = $null; Start = -1; Dry = $false }
    if ($env:FT_CLOSE_TEST_DIR) {
        $r.Dry = $true
        $t = FtcTestTable
        if ($null -eq $t) { $r.Err = 'the process table could not be read'; return $r }
        foreach ($l in $t) {
            $a = $l.Trim().Split(':')
            if ($a.Count -ge 3 -and $a[1] -eq [string]$procId) { $r.Ok = $true; $r.Name = $a[0]; $r.StartUnix = [long]$a[2]; $r.Start = [long]$a[2]; return $r }
        }
        $r.Err = "pid $procId is not running"; return $r
    }
    try { $p = [Diagnostics.Process]::GetProcessById($procId) } catch { $r.Err = "pid $procId is not running"; return $r }
    try { $h = $p.Handle } catch { $r.Err = "pid ${procId}: no handle ($($_.Exception.Message))"; return $r }
    try { FtcNativeLoad } catch { $r.Err = "the handle reader did not load ($($_.Exception.Message))"; return $r }
    $path = [FtcNative]::ImagePath($h)
    $ft = [FtcNative]::StartFileTime($h)
    if (-not $path -or $ft -le 0) { $r.Err = "pid ${procId}: the read through its handle failed (image '$path', start $ft)"; return $r }
    $r.Proc = $p
    $r.Name = [IO.Path]::GetFileNameWithoutExtension($path)
    $r.StartUnix = [long][math]::Floor([DateTimeOffset]::FromFileTime($ft).ToUnixTimeMilliseconds() / 1000.0)
    $r.Ok = $true
    return $r
}

function FtcExited($o) {
    # through the object only; a failed read is "not exited"
    if ($o.Dry) {
        $t = FtcTestTable
        if ($null -eq $t) { return $false }
        foreach ($l in $t) {
            $a = $l.Trim().Split(':')
            if ($a.Count -ge 3 -and $a[1] -eq [string]$o.Pid -and $a[2] -eq [string]$o.Start) { return $false }
        }
        return $true
    }
    try { return [bool]$o.Proc.HasExited } catch { return $false }
}

function FtcRequestClose($o) {
    if ($o.Dry) { Add-Content -LiteralPath (Join-Path $env:FT_CLOSE_TEST_DIR 'close-requested.txt') -Value "$($o.Pid):$($o.Start)"; return $true }
    try { return [bool]$o.Proc.CloseMainWindow() } catch { return $false }
}

function FtcStop($o) {
    # -> the stop's own result text (the exit is proven by FtcExited afterwards, never by this)
    if ($o.Dry) {
        $d = $env:FT_CLOSE_TEST_DIR
        Add-Content -LiteralPath (Join-Path $d 'stopped.txt') -Value "$($o.Pid):$($o.Start)"
        $t = FtcTestTable
        if ($null -eq $t) { return 'table unreadable' }
        $keep = @($t | Where-Object { $a = $_.Trim().Split(':'); -not ($a.Count -ge 3 -and $a[1] -eq [string]$o.Pid -and $a[2] -eq [string]$o.Start) })
        Set-Content -LiteralPath (Join-Path $d 'procs.txt') -Value $keep
        return 'stop sent'
    }
    try { $o.Proc.Kill(); return 'Kill sent' } catch { return "Kill failed: $($_.Exception.Message)" }
}

function Test-FtLeasedIdentity([string]$PidFile) {
    # -> @{ Ok; Pid; Line; Obj }. Read only. Obj is the one process object every later step acts on.
    $r = @{ Ok = $false; Pid = 0; Line = ''; Obj = $null }
    if (-not $PidFile -or -not (Test-Path -LiteralPath $PidFile)) { $r.Line = "pid file absent ($PidFile)"; return $r }
    try { $line = ([IO.File]::ReadAllText($PidFile)).Trim() } catch { $r.Line = 'pid file unreadable'; return $r }
    $m = [regex]::Match($line, '^FT-VM-LAUNCH-PID pid=(\d+) epoch=(\d+) stamp=(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)$')
    if (-not $m.Success) { $r.Line = "pid file line malformed [$line]"; return $r }
    $fpid = [int]$m.Groups[1].Value; $epoch = [long]$m.Groups[2].Value
    $stamp = [DateTimeOffset]::Parse($m.Groups[3].Value, [Globalization.CultureInfo]::InvariantCulture).ToUnixTimeSeconds()
    $r.Pid = $fpid
    $o = FtcOpen $fpid
    if (-not $o.Ok) { $r.Line = $o.Err; return $r }
    if ($o.Name -ne $script:FtcWantName) { $r.Line = "pid $fpid is $($o.Name), not $($script:FtcWantName)"; return $r }
    if ($o.StartUnix -lt $epoch -or $o.StartUnix -gt $stamp) { $r.Line = "pid $fpid started at $($o.StartUnix), outside [launch epoch $epoch, stamp $stamp]"; return $r }
    $r.Ok = $true
    $r.Obj = $o
    $r.Line = "pid $fpid is the leased $($script:FtcWantName) by identity, read through its handle (launch epoch $epoch <= start $($o.StartUnix) <= stamp $stamp)"
    return $r
}

function Close-FtLeasedObject($id, [scriptblock]$Emit, [int]$BoundMs = $script:FtCloseBoundMs, [int]$PollMs = 100) {
    # $id: a shown identity from Test-FtLeasedIdentity. -> 0 graceful exit within the bound; 2 stopped at the bound
    # and gone; 3 stopped at the bound, still running 10 s later. Acts on $id.Obj only.
    $o = $id.Obj
    $procId = $id.Pid
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $req = FtcStamp
    $sent = FtcRequestClose $o
    & $Emit "FT-CLOSE close-request=$req pid $procId CloseMainWindow=$sent bound=${BoundMs}ms"
    $cap = [int]($BoundMs / $PollMs) + 1
    for ($i = 0; $i -lt $cap -and $sw.ElapsedMilliseconds -lt $BoundMs; $i++) {
        if (FtcExited $o) {
            $ms = $sw.ElapsedMilliseconds
            & $Emit "FT-CLOSE exited=$(FtcStamp) pid $procId graceful close_to_exit_ms=$ms bound=${BoundMs}ms"
            return 0
        }
        Start-Sleep -Milliseconds $PollMs
    }
    if (FtcExited $o) {
        & $Emit "FT-CLOSE exited=$(FtcStamp) pid $procId graceful close_to_exit_ms=$($sw.ElapsedMilliseconds) bound=${BoundMs}ms"
        return 0
    }
    & $Emit "FT-CLOSE stop-at-bound=$(FtcStamp) pid $procId still running after $($sw.ElapsedMilliseconds) ms (bound ${BoundMs}ms): stop on that object"
    $sr = FtcStop $o
    & $Emit "FT-CLOSE stop result: $sr"
    for ($i = 0; $i -lt 100 -and -not (FtcExited $o); $i++) { Start-Sleep -Milliseconds 100 }
    if (-not (FtcExited $o)) { & $Emit "FT-CLOSE pid $procId STILL RUNNING 10 s after the stop"; return 3 }
    & $Emit "FT-CLOSE exited=$(FtcStamp) pid $procId stopped close_to_exit_ms=$($sw.ElapsedMilliseconds) bound=${BoundMs}ms"
    return 2
}

function Close-FtLeasedGame([string]$PidFile, [scriptblock]$Emit, [int]$BoundMs = $script:FtCloseBoundMs, [int]$PollMs = 100) {
    # -> 0 graceful exit within the bound; 2 stopped at the bound and gone; 3 stopped at the bound, still running
    #    10 s later; 7 identity not shown, nothing closed. Every line goes through $Emit with "FT-CLOSE".
    $id = Test-FtLeasedIdentity $PidFile
    if (-not $id.Ok) { & $Emit "FT-CLOSE REFUSED: identity not shown ($($id.Line)); nothing closed"; return 7 }
    & $Emit "FT-CLOSE identity: $($id.Line)"
    return (Close-FtLeasedObject $id $Emit $BoundMs $PollMs)
}
