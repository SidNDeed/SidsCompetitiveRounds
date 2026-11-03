# ft_vm_launch.ps1 -Mode menu|match -Out <file>: one FrameTime launch on the VM seat (ruling FRAME-TIME-ROUND-R4),
# run UNDER the broadcast pause lease by ft_vm_leased.sh, never alone. Launches ROUNDS, captures the new PID, polls
# BepInEx\LogOutput.log every 15 s for the run's end line (menu: the terminal settled line after menu_done; match:
# "flushed g=16", the last game's lines written after its settle), copies the whole log to -Out, then quits gracefully
# (C:\broadcast\quit_game.ps1); Stop-Process by the captured PID only if the graceful quit fails.
# Exit: 0 end line seen and log copied; 3 refused (ROUNDS already running); 4 no process; 5 end line not seen.
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
$before = @(Get-Process -Name ROUNDS -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
if ($before.Count -gt 0) { echo "$(St) FT-VM-LAUNCH REFUSED: ROUNDS already running ($($before -join ','))"; exit 3 }
$t0 = (Get-Date).ToUniversalTime()
echo "$(St) FT-VM-LAUNCH $Mode Start-Process steam://rungameid/1557740"
Start-Process 'steam://rungameid/1557740'
$procId = $null
for ($i = 0; $i -lt 60 -and -not $procId; $i++) {
    Start-Sleep -Seconds 3
    $p = Get-Process -Name ROUNDS -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($p) { $procId = $p.Id }
}
if (-not $procId) { echo "$(St) FT-VM-LAUNCH no ROUNDS process within 180 s"; exit 4 }
echo "$(St) FT-VM-LAUNCH captured ROUNDS pid $procId"
$seen = $false
for ($i = 1; $i -le $polls; $i++) {
    Start-Sleep -Seconds 15
    if (-not (Get-Process -Id $procId -ErrorAction SilentlyContinue)) { echo "$(St) FT-VM-LAUNCH poll ${i}: pid $procId exited early"; break }
    # only the new run's log: BepInEx recreates LogOutput.log at the game's start, and nothing else writes it, so a
    # write time after the launch means the new run's text (an older run's end line never counts)
    try { if ((Get-Item -LiteralPath $log).LastWriteTimeUtc -le $t0) { continue }; $t = ReadShared $log } catch { continue }
    if (EndSeen $t) { $seen = $true; echo "$(St) FT-VM-LAUNCH poll ${i}: end line seen"; break }
}
Start-Sleep -Seconds 5
try { $t = ReadShared $log; [System.IO.File]::WriteAllText($Out, $t); echo "$(St) FT-VM-LAUNCH log copied: $Out" }
catch { echo "$(St) FT-VM-LAUNCH log copy FAILED: $($_.Exception.Message)"; $seen = $false }
if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
    & powershell -NoProfile -File 'C:\broadcast\quit_game.ps1' -Holder frame-time | ForEach-Object { "quit_game: $_" }
    for ($i = 0; $i -lt 20 -and (Get-Process -Id $procId -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Seconds 3 }
    if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $procId -Force; echo "$(St) FT-VM-LAUNCH quit: stopped pid $procId"
    } else { echo "$(St) FT-VM-LAUNCH quit: graceful" }
}
echo "$(St) FT-VM-LAUNCH $Mode end line seen: $(if ($seen) { 'yes' } else { 'no' })"
if ($seen) { exit 0 } else { exit 5 }
