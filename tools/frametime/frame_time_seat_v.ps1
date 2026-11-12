# frame_time_seat_v.ps1: the laptop seat's entry for sitting V (the job runner passes no arguments). It starts
# frame_time_seat.ps1 from this folder with -ArmForce ON and nothing else, and ends with that script's exit code.
$seat = Join-Path $PSScriptRoot 'frame_time_seat.ps1'
if (-not (Test-Path -LiteralPath $seat -PathType Leaf)) { [Console]::Out.WriteLine("REFUSED: frame_time_seat.ps1 is not beside frame_time_seat_v.ps1 ($seat)"); exit 2 }
& $seat -ArmForce ON
exit $LASTEXITCODE
