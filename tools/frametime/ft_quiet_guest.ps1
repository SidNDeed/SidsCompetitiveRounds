<#
ft_quiet_guest.ps1 -Out <trace file> -StopFile <file> -MaxSeconds <n>: the guest half of the quiet trace (method-v52.md
section 6), sampled once a second until the stop file appears or MaxSeconds samples are written. ft_vm_leased.sh
starts it after the leased shutdown and stops it at its exit; ft_quiet.py judges the trace.

Line 1: "QG v1 ncpu=<logical processors> disks=<PhysicalDisk instances, spaces as _>". Then one line a second:
  G utc=<epoch ms> mono=<Stopwatch ns> total=<Processor(_Total)\% Processor Time> rpid=<ROUNDS pid> rstart=<its
  start, FILETIME ticks> rcpu=<ROUNDS cores over the interval, from its TotalProcessorTime> dq=<Avg. Disk Queue Length
  per disk, in header order> avail=<Available MBytes> commit=<% Committed Bytes In Use> pin=<Pages Input/sec>
  prd=<Page Reads/sec> pout=<Pages Output/sec>
rpid and rstart are "-" while no ROUNDS process runs and "NA" while more than one does; a counter that cannot be read
is "NA" (ft_quiet.py refuses it). The counters are opened once and read each second, so the sampler's own cost stays
small, and it is counted: it is non-game work like any other. Nothing in the trace names the machine.
#>
param(
    [Parameter(Mandatory = $true)][string]$Out,
    [Parameter(Mandatory = $true)][string]$StopFile,
    [Parameter(Mandatory = $true)][int]$MaxSeconds
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$inv = [System.Globalization.CultureInfo]::InvariantCulture
function PC([string]$cat, [string]$ctr, [string]$inst) { return New-Object System.Diagnostics.PerformanceCounter($cat, $ctr, $inst, $true) }
$disks = @((New-Object System.Diagnostics.PerformanceCounterCategory('PhysicalDisk')).GetInstanceNames() | Where-Object { $_ -ne '_Total' } | Sort-Object)
$c = [ordered]@{
    total  = PC 'Processor' '% Processor Time' '_Total'
    avail  = PC 'Memory' 'Available MBytes' ''
    commit = PC 'Memory' '% Committed Bytes In Use' ''
    pin    = PC 'Memory' 'Pages Input/sec' ''
    prd    = PC 'Memory' 'Page Reads/sec' ''
    pout   = PC 'Memory' 'Pages Output/sec' ''
}
$dq = @($disks | ForEach-Object { PC 'PhysicalDisk' 'Avg. Disk Queue Length' $_ })
function Read1($pc) { try { return $pc.NextValue().ToString('0.####', $inv) } catch { return 'NA' } }
$w = New-Object System.IO.StreamWriter($Out, $false, (New-Object System.Text.UTF8Encoding($false)))
$w.AutoFlush = $true
try {
    $w.WriteLine(('QG v1 ncpu={0} disks={1}' -f [Environment]::ProcessorCount, (($disks | ForEach-Object { $_ -replace '\s', '_' }) -join ',')))
    # the rate counters' first reading is 0: prime them, then sample on a one-second grid
    foreach ($k in $c.Keys) { [void](Read1 $c[$k]) }
    foreach ($d in $dq) { [void](Read1 $d) }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $nsPerTick = 1e9 / [System.Diagnostics.Stopwatch]::Frequency
    $prev = $null
    for ($i = 1; $i -le $MaxSeconds; $i++) {
        $wait = [int]($i * 1000 - $sw.ElapsedMilliseconds)
        if ($wait -gt 0) { Start-Sleep -Milliseconds $wait }
        $t = $sw.ElapsedTicks
        $utc = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        $v = [ordered]@{}
        foreach ($k in $c.Keys) { $v[$k] = Read1 $c[$k] }
        $q = @($dq | ForEach-Object { Read1 $_ })
        $ps = @(Get-Process -Name 'ROUNDS' -ErrorAction SilentlyContinue)
        $rpid = '-'; $rstart = '-'; $rcpu = '0'; $cur = $null
        if ($ps.Count -gt 1) { $rpid = 'NA'; $rstart = 'NA'; $rcpu = 'NA' }
        elseif ($ps.Count -eq 1) {
            try {
                $cur = @{ Id = $ps[0].Id; Start = $ps[0].StartTime.ToFileTimeUtc(); Cpu = $ps[0].TotalProcessorTime.Ticks; T = $t }
                $rpid = [string]$cur.Id; $rstart = [string]$cur.Start
                if ($prev -and $prev.Id -eq $cur.Id -and $prev.Start -eq $cur.Start) {
                    # TotalProcessorTime ticks are 100 ns
                    $rcpu = (($cur.Cpu - $prev.Cpu) * 100.0 / (($cur.T - $prev.T) * $nsPerTick)).ToString('0.######', $inv)
                }
                else { $rcpu = 'NA' }   # the first sample of a process has no interval
            }
            catch { $rpid = 'NA'; $rstart = 'NA'; $rcpu = 'NA'; $cur = $null }
        }
        $prev = $cur
        $w.WriteLine(('G utc={0} mono={1} total={2} rpid={3} rstart={4} rcpu={5} dq={6} avail={7} commit={8} pin={9} prd={10} pout={11}' -f
                $utc, [long]($t * $nsPerTick), $v.total, $rpid, $rstart, $rcpu, ($q -join ','), $v.avail, $v.commit, $v.pin, $v.prd, $v.pout))
        if (Test-Path -LiteralPath $StopFile) { break }
    }
}
finally { $w.Dispose() }
exit 0
