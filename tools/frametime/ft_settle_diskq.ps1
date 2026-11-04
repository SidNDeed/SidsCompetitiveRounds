# ft_settle_diskq.ps1 [-IntervalS 10] [-Count 12] [-Readings <q1,q2,...>]: the settle window of the gate under the
# broadcast pause lease (ruling FRAME-TIME R6-A3.11.10, FIX-8). ft_vm_leased.sh runs it right after the bot's game has
# exited and before s0_gate.ps1 (unchanged). A reading taken right after the quit measures the quit's own exit
# writes, so the window reads the disk queue (the counter s0_gate.ps1 reads: \PhysicalDisk(_Total)\Current Disk Queue
# Length) every -IntervalS seconds, -Count readings in all (10 s x 12 = the 120 s window), and passes on the first two
# CONSECUTIVE readings below 3. It refuses only when the window ends without them. Every reading is printed with its
# stamp. Exit 0 pass, 1 refuse.
# -Readings (dry controls only): a supplied comma-separated sequence replaces the counter; with it the interval is
# not slept unless -IntervalS is given explicitly.
param([int]$IntervalS = 10, [int]$Count = 12, [string]$Readings = '')
function St { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ') }
$supplied = @()
if ($Readings -ne '') {
    $supplied = @($Readings.Split(',') | ForEach-Object { [double]$_.Trim() })
    if (-not $PSBoundParameters.ContainsKey('IntervalS')) { $IntervalS = 0 }
}
"$(St) FT-SETTLE window begin: disk queue every $IntervalS s, $Count readings ($($IntervalS * $Count) s), pass on two consecutive < 3$(if ($supplied.Count) { ' (SUPPLIED readings: ' + $Readings + ')' })"
$prev = $null
for ($i = 1; $i -le $Count; $i++) {
    if ($i -gt 1 -and $IntervalS -gt 0) { Start-Sleep -Seconds $IntervalS }
    if ($supplied.Count) {
        if ($i -gt $supplied.Count) { "$(St) FT-SETTLE REFUSE: the supplied sequence ended at reading $($i - 1) of $Count"; exit 1 }
        $q = $supplied[$i - 1]
    } else {
        try { $q = [math]::Round((Get-Counter '\PhysicalDisk(_Total)\Current Disk Queue Length').CounterSamples.CookedValue, 2) }
        catch { $q = $null }
    }
    if ($null -eq $q) { "$(St) FT-SETTLE reading $i/$Count unreadable (counts as not below 3)"; $prev = $null; continue }
    "$(St) FT-SETTLE reading $i/$Count = $q"
    if ($q -lt 3 -and $null -ne $prev -and $prev -lt 3) {
        "$(St) FT-SETTLE PASS at reading $i of ${Count}: $prev, $q (two consecutive < 3)"
        exit 0
    }
    $prev = $q
}
"$(St) FT-SETTLE REFUSE: the window ended after $Count readings without two consecutive < 3"
exit 1
