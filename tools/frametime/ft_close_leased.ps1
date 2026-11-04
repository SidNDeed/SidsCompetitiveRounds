# ft_close_leased.ps1 -PidFile <launch-<mode>.pid> [-BoundMs <ms>]: closes the leased game a frame-time launch started,
# by identity, through ft_close_lib.ps1 (ruling FRAME-TIME R6-A3.11.9, FIX-6b). The caller is ft_vm_leased.sh's
# cleanup. Exit: the lib's code (0 graceful, 2 stopped at the bound, 3 still running after the stop, 7 identity not
# shown and nothing closed).
param([Parameter(Mandatory = $true)][string]$PidFile, [int]$BoundMs = 0)
. (Join-Path $PSScriptRoot 'ft_close_lib.ps1')
if ($BoundMs -le 0) { $BoundMs = $script:FtCloseBoundMs }
# the emitter writes to the console directly: a Write-Output inside it would join the function's return value
$rc = Close-FtLeasedGame $PidFile { param($s) [Console]::Out.WriteLine(((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) + ' ' + $s) } $BoundMs
exit $rc
