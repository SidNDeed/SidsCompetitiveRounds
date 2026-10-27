# Bugs 437-439 - run the FFA resolver harness clean, then under mutation.
# Each mutant names the cases that MUST redden and a control that MUST stay
# green (#391). Each anchor must occur EXACTLY ONCE in its file or the run
# refuses to build that mutant: a mutant that changed nothing would pass as
# "detected" for the wrong reason.
#
#   powershell -NoProfile -File tools/tests/ffa-targeting-seam/run-tests.ps1
#
# No absolute path: everything resolves from this script's own location.
# Mutants and build output go under work/, which is gitignored; the shipped
# seam files are only ever read.
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$work = Join-Path $root 'work'
$repo = (Resolve-Path (Join-Path $root (Join-Path '..' (Join-Path '..' '..')))).Path
$proj = Join-Path $root 'FfaTargetingTests.csproj'
$ffaSeam = (Resolve-Path (Join-Path $repo (Join-Path 'plugin' 'FfaTargetingSeam.cs'))).Path
$victimSeam = (Resolve-Path (Join-Path $repo (Join-Path 'plugin' 'ProximityVictimSeam.cs'))).Path
$overall = 0

if (Test-Path $work) { Remove-Item -Recurse -Force $work }
New-Item -ItemType Directory -Path $work | Out-Null

function Invoke-Suite([string]$name, [string[]]$props) {
    $out = Join-Path $work (Join-Path $name 'bin')
    $buildArgs = @('build', $proj, '-c', 'Release', '-o', $out, '--no-incremental', '-nologo', '-v', 'q') + $props
    & dotnet @buildArgs | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "build failed for run '$name'" }
    $lines = & dotnet (Join-Path $out 'FfaTargetingTests.dll')
    $lines | Out-Host
    return ,$lines
}

function Get-Verdict([string[]]$lines, [string]$case) {
    foreach ($l in $lines) {
        if ($l.StartsWith('PASS ' + $case)) { return 'PASS' }
        if ($l.StartsWith('FAIL ' + $case)) { return 'FAIL' }
    }
    return 'MISSING'
}

function New-Mutant([string]$source, [string]$name, [string]$anchor, [string]$replacement) {
    $text = [System.IO.File]::ReadAllText($source)
    $nl = "`n"
    if ($text.Contains("`r`n")) { $nl = "`r`n" }
    $a = $anchor.Replace('<NL>', $nl)
    $r = $replacement.Replace('<NL>', $nl)
    $hits = ([regex]::Matches($text, [regex]::Escape($a))).Count
    if ($hits -ne 1) { throw "mutant '$name': anchor found $hits times, need exactly 1" }
    $dir = Join-Path $work $name
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $dest = Join-Path $dir ([System.IO.Path]::GetFileName($source))
    [System.IO.File]::WriteAllText($dest, $text.Replace($a, $r))
    return $dest
}

# ---- clean run: every case green ------------------------------------------
$clean = Invoke-Suite 'clean' @()
if ($LASTEXITCODE -ne 0) { Write-Host 'CLEAN RUN FAILED'; $overall = 1 }

# ---- mutants ----------------------------------------------------------------
$mutants = @(
    @{ Name = 'twoteam'; Source = $ffaSeam; Prop = 'FfaSeamSource';
       Anchor = 'if (excludeTeam >= 0 && team == excludeTeam) return false;';
       Replace = 'if (team != (excludeTeam == 0 ? 1 : 0)) return false;';
       MustFail = @('T DealDamageToPlayer.Go', 'T PlayerInRangeTrigger.Update', 'T StunPlayer.Go',
                    'T TeleportToOpponent.Go', 'T FollowPlayer.LateUpdate', 'T AimForPlayer.Update',
                    'T ActivateSciptWhenCanSeeOtherPlayer.Update', 'T SpawnObjectEffect.DoEffect',
                    'T Chase.Update', 'T LineOfSightTrigger.Update', 'T RadarShot.Go',
                    'T ZapEffect.Start');
       Control = 'C1' },
    @{ Name = 'positional'; Source = $ffaSeam; Prop = 'FfaSeamSource';
       Anchor = 'if (!identityKnown && dist < SelfRadius) return false;';
       Replace = 'if (dist < SelfRadius) return false;';
       MustFail = @('P1'); Control = 'P2' },
    @{ Name = 'noreask'; Source = $victimSeam; Prop = 'VictimSeamSource';
       Anchor = 'if (!vanillaAnswered) return ProximityPrefixAction.RunVanillaUntouched;<NL>            return ProximityPrefixAction.WriteVictimAndRun;';
       Replace = 'if (!vanillaAnswered) return ProximityPrefixAction.RunVanillaUntouched;<NL>            return ProximityPrefixAction.RunVanillaUntouched;';
       MustFail = @('T DealDamageToPlayer.Go', 'T StunPlayer.Go', 'T TeleportToOpponent.Go');
       Control = 'C1' },
    @{ Name = 'noredirect'; Source = $victimSeam; Prop = 'VictimSeamSource';
       Anchor = 'return previousPlayerId >= 0 && previousPlayerId != freshPlayerId;';
       Replace = 'return false;';
       MustFail = @('A3'); Control = 'A2' }
)

foreach ($m in $mutants) {
    $path = New-Mutant $m.Source $m.Name $m.Anchor $m.Replace
    $lines = Invoke-Suite $m.Name @("-p:$($m.Prop)=$path")
    foreach ($case in $m.MustFail) {
        $v = Get-Verdict $lines $case
        if ($v -ne 'FAIL') { Write-Host "MUTANT $($m.Name): $case was $v, must FAIL"; $overall = 1 }
    }
    $c = Get-Verdict $lines $m.Control
    if ($c -ne 'PASS') { Write-Host "MUTANT $($m.Name): control $($m.Control) was $c, must PASS"; $overall = 1 }
    # R1 reproduces the reported room through the FFA rule; the twoteam mutant
    # replaces that rule, so R1 is only an untouched twin under the others.
    if ($m.Name -ne 'twoteam') {
        $r = Get-Verdict $lines 'R1'
        if ($r -ne 'PASS') { Write-Host "MUTANT $($m.Name): reproduction R1 was $r, must PASS"; $overall = 1 }
    }
}

if ($overall -eq 0) { Write-Host 'ALL RUNS AS EXPECTED' } else { Write-Host 'HARNESS VERDICT: FAILED' }
exit $overall
