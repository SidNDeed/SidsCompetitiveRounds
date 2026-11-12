# frame_time_seat_trial.ps1: a control run of the laptop seat script on the real seat, without a partner (the job
# runner passes no arguments). It starts frame_time_seat.ps1 from this folder with -ArmForce ON and -TimeoutS 780, so
# the seat launches, waits 180 s for a sitting that cannot complete, quits, exports and restores: every step of the
# sitting's own path but the match. It ends with that script's exit code; 3 (the sitting did not complete) with a
# proven restore is the wanted one. No measurement is read from it.
$seat = Join-Path $PSScriptRoot 'frame_time_seat.ps1'
if (-not (Test-Path -LiteralPath $seat -PathType Leaf)) { [Console]::Out.WriteLine("REFUSED: frame_time_seat.ps1 is not beside frame_time_seat_trial.ps1 ($seat)"); exit 2 }
# The exit code. An error that ends frame_time_seat.ps1 sets no exit code, and sitting V's entry as it was on
# 12 Nov 2026 ended 0 on one. So 1 is set first (it stands when that script sets no code), an error is printed here
# and ends this entry 1, and the one-pass loop takes a stray break or continue of that script, which would
# otherwise end this entry too. A LABELLED break or continue whose label names no loop passes the loop and the catch
# and would end this entry without its last line (the host process then ends 0): $seatReturned is set once the loop
# is left normally, $seatFailed in the catch, and the finally prints a SEAT-SCRIPT-ERROR line and ends the process 1
# when neither is set.
$global:LASTEXITCODE = 1
$seatReturned = $false
$seatFailed = $false
try { do { & $seat -ArmForce ON -TimeoutS 780 } while ($false); $seatReturned = $true }
catch { $seatFailed = $true; [Console]::Out.WriteLine('SEAT-SCRIPT-ERROR: frame_time_seat.ps1 ended by an error: ' + $_.Exception.Message); exit 1 }
finally { if (-not ($seatReturned -or $seatFailed)) { [Console]::Out.WriteLine('SEAT-SCRIPT-ERROR: frame_time_seat.ps1 ended by a control transfer that left the entry'); [Environment]::Exit(1) } }
exit $LASTEXITCODE
