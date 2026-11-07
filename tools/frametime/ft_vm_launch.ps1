# ft_vm_launch.ps1 -Mode menu|match -Out <file>: one FrameTime launch on the VM seat (ruling FRAME-TIME-ROUND-R4),
# run UNDER the broadcast pause lease by ft_vm_leased.sh, never alone. Launches ROUNDS, captures the new PID, polls
# BepInEx\LogOutput.log every 15 s for the run's end line (menu: the terminal settled line after menu_done; match:
# "flushed g=16", the last game's lines written after its settle), copies the whole log to -Out, then closes the game
# it launched BY IDENTITY through ft_close_lib.ps1 (ruling R6-A3.11.9, FIX-6b): the pid file below must name the
# running ROUNDS (pid, and a start inside [launch epoch, stamp]); a graceful close request (CloseMainWindow) first,
# Stop-Process on that pid only at the lib's named bound. It never calls C:\broadcast\quit_game.ps1: that lever is the
# broadcast rig's and keeps its full refusal.
# A1 (ruling R6-A3.11.18): the launched game is ONE process object. It is captured from a reading of the whole
# process table by image name (before any identity exists), its handle is taken at once and kept, and every later
# question about it (has it exited) goes through that object; the close goes through the lib's one identity read.
# While the handle is held, Windows never gives the captured id to another process. No process is read by number
# here. A process-table reading that fails is never "no ROUNDS": the pre-launch check refuses on it.
# Exit: 0 end line seen and log copied; 3 refused (ROUNDS already running, or the process table unreadable);
# 4 no process; 5 end line not seen (also when the captured process's handle could not be held); 6 the pid file could
# not be written (the game closed through the held object; the caller's exit chain proves its exit and restores).
# The moment the pid is captured it writes <dir of -Out>\launch-<Mode>.pid, one line
# "FT-VM-LAUNCH-PID pid=<pid> epoch=<launch epoch s> stamp=<utc>" (temp file, then rename): the signal a watcher
# starts from (ruling R6-A3.11.4; this script's stdout reaches its caller through a buffered pipe).
param([Parameter(Mandatory = $true)][ValidateSet('menu', 'match')][string]$Mode,
      [Parameter(Mandatory = $true)][string]$Out)
function St { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }
$log = 'C:\Program Files (x86)\Steam\steamapps\common\ROUNDS\BepInEx\LogOutput.log'
# menu: 200 polls of 15 s = 50 min for the 200-segment menu check of about 34.4 min plus the game's start (ruling
# FRAME-TIME-ROUND-R6-A3.2 (1), FtMenu's summary); match: 150 min (17 games and the settle)
$polls = if ($Mode -eq 'menu') { 200 } else { 600 }
function ReadShared($p) {
    $fs = [System.IO.File]::Open($p, 'Open', 'Read', 'ReadWrite')
    try { $sr = New-Object System.IO.StreamReader($fs); return $sr.ReadToEnd() } finally { $fs.Close() }
}
function EndSeen($t) {
    if ($Mode -eq 'match') { return $t.Contains('[FRAME-TIME] flushed g=16 ') }
    $i = $t.IndexOf('[FRAME-TIME] menu_done ')
    return ($i -ge 0) -and ($t.IndexOf('[FRAME-TIME] settled g=-1 ', $i) -ge 0)
}
function RoundsNow {
    # one reading of the whole table by image name; throws when the table cannot be read (never an empty answer)
    return @(Get-Process -ErrorAction Stop | Where-Object { $_.ProcessName -eq 'ROUNDS' })
}
try { $before = @(RoundsNow | ForEach-Object { $_.Id }) } catch { echo "$(St) FT-VM-LAUNCH REFUSED: the process table could not be read ($($_.Exception.Message))"; exit 3 }
if ($before.Count -gt 0) { echo "$(St) FT-VM-LAUNCH REFUSED: ROUNDS already running ($($before -join ','))"; exit 3 }
$t0 = (Get-Date).ToUniversalTime()
echo "$(St) FT-VM-LAUNCH $Mode Start-Process steam://rungameid/1557740"
Start-Process 'steam://rungameid/1557740'
$procId = $null; $p = $null
for ($i = 0; $i -lt 60 -and -not $procId; $i++) {
    Start-Sleep -Seconds 3
    try { $p = RoundsNow | Select-Object -First 1 } catch { echo "$(St) FT-VM-LAUNCH capture read failed ($($_.Exception.Message)); reading again"; $p = $null }
    if ($p) { $procId = $p.Id }
}
if (-not $procId) { echo "$(St) FT-VM-LAUNCH no ROUNDS process within 180 s"; exit 4 }
# the object's handle, taken now and kept: every later HasExited reads through it
$held = $true
try { $null = $p.Handle } catch { $held = $false; echo "$(St) FT-VM-LAUNCH handle of pid $procId NOT held ($($_.Exception.Message)): no wait on it; straight to the close" }
function Exited { if (-not $held) { return $false }; try { return [bool]$p.HasExited } catch { return $false } }
echo "$(St) FT-VM-LAUNCH captured ROUNDS pid $procId (handle held: $held)"
$pidFile = Join-Path (Split-Path -Parent $Out) "launch-$Mode.pid"
try {
    $epoch = ([DateTimeOffset]$t0).ToUnixTimeSeconds()
    # every write error is terminating (-ErrorAction Stop: under the default Continue a failed write would print and
    # go on), and the file is read back and compared before "pid file written" (F9-R3 finding 4, sitting W32i)
    $pidLine = "FT-VM-LAUNCH-PID pid={0} epoch={1} stamp={2}" -f $procId, $epoch, (St)
    Set-Content -LiteralPath ($pidFile + '.tmp') -Value $pidLine -Encoding ASCII -ErrorAction Stop
    Move-Item -LiteralPath ($pidFile + '.tmp') -Destination $pidFile -Force -ErrorAction Stop
    $back = @(Get-Content -LiteralPath $pidFile -ErrorAction Stop)
    if ($back.Count -ne 1 -or $back[0] -ne $pidLine) { throw "the pid file read back differs ('$($back -join '|')')" }
    echo "$(St) FT-VM-LAUNCH pid file written: $pidFile"
} catch {
    # without the pid file no caller can close this game by identity and window 9's +20 CHECK has no input (F9-R2
    # finding 3, sitting W32h): the launcher does not go on to the match; it closes the game it launched through the
    # held object (a graceful close request, then Kill on that object at the bound) and exits 6
    echo "$(St) FT-VM-LAUNCH pid file FAILED: $($_.Exception.Message); no identity: the game is closed through the held object"
    if ($held) {
        try { $null = $p.CloseMainWindow() } catch { }
        try { if (-not $p.WaitForExit(60000)) { $p.Kill(); $null = $p.WaitForExit(30000) } } catch { echo "$(St) FT-VM-LAUNCH close through the held object failed ($($_.Exception.Message))" }
    }
    echo "$(St) FT-VM-LAUNCH exit 6 (pid file not written; captured process exited: $(Exited))"
    exit 6
}
$seen = $false
for ($i = 1; $i -le $polls -and $held; $i++) {
    Start-Sleep -Seconds 15
    if (Exited) { echo "$(St) FT-VM-LAUNCH poll ${i}: pid $procId exited early"; break }
    # only the new run's log: BepInEx recreates LogOutput.log at the game's start, and nothing else writes it, so a
    # write time after the launch means the new run's text (an older run's end line never counts)
    try { if ((Get-Item -LiteralPath $log).LastWriteTimeUtc -le $t0) { continue }; $t = ReadShared $log } catch { continue }
    if (EndSeen $t) { $seen = $true; echo "$(St) FT-VM-LAUNCH poll ${i}: end line seen"; break }
}
Start-Sleep -Seconds 5
try { $t = ReadShared $log; [System.IO.File]::WriteAllText($Out, $t); echo "$(St) FT-VM-LAUNCH log copied: $Out" }
catch { echo "$(St) FT-VM-LAUNCH log copy FAILED: $($_.Exception.Message)"; $seen = $false }
if (-not (Exited)) {
    . (Join-Path $PSScriptRoot 'ft_close_lib.ps1')
    # the emitter writes to the console directly: a Write-Output inside it would join the function's return value
    $crc = Close-FtLeasedGame $pidFile { param($s) [Console]::Out.WriteLine("$(St) FT-VM-LAUNCH $s") }
    echo "$(St) FT-VM-LAUNCH close by identity rc=$crc (0 graceful, 2 stopped at the bound, 3 still running, 7 identity not shown)"
}
echo "$(St) FT-VM-LAUNCH $Mode end line seen: $(if ($seen) { 'yes' } else { 'no' })"
if ($seen) { exit 0 } else { exit 5 }
