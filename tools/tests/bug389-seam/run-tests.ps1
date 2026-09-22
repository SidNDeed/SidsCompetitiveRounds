# Bug 389 - run the seam clean, then under mutation. Each mutation names a test
# that MUST redden and a control that MUST stay green (#391): a suite that
# reddens at any change measures nothing, and one with no control cannot tell
# "the mutation was detected" from "the build broke".
#
# Takes no arguments and contains no absolute path: everything is resolved from
# this script's own location, so the harness runs from any clone.
#
#   powershell -NoProfile -File tools/tests/bug389-seam/run-tests.ps1
#
# EVERY ANCHOR IS RESOLVED INSIDE A NAMED MEMBER, never file-wide (#432). A
# file-wide count cannot tell the site that is where it belongs from the same
# line relocated into another member, and a file-wide Replace would rewrite both.
# Get-MemberSpan bounds the member, the hit count is asserted INSIDE that span,
# and the splice is applied to the span alone - so a matching line elsewhere in
# the file is reported and left untouched. Assert-BuilderRejects is the negative
# control on the builder itself: hand it an anchor that lives in another member
# and it must refuse to produce a mutant at all.
#
# THREE KINDS OF RUN, because the repair has three halves.
#   * SEAM mutations compile a one-line-changed COPY of
#     plugin/ProximityVictimSeam.cs. The seam itself is never written to, so a
#     crashed run cannot leave the shipped file mutated.
#   * WIRING mutations leave the seam alone and point the suite's
#     BUG389_SOURCE_ROOT at a one-line-changed COPY of the shipped files this
#     harness cannot compile - they carry Unity, Photon and MSBuild.
#   * The PRIOR-MECHANISM run points that same root at the round-2 files,
#     recovered from git rather than copied by hand, and requires every N case -
#     the ones that assert round 3's deletions - to redden there while a case
#     untouched by the change stays green. Without it "no selector here" is a
#     statement no run has ever seen fail.
#
# Generated mutants and build output go under work/, which is gitignored.
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$work = Join-Path $root 'work'
$repo = (Resolve-Path (Join-Path $root (Join-Path '..' (Join-Path '..' '..')))).Path
$seam = (Resolve-Path (Join-Path $repo (Join-Path 'plugin' 'ProximityVictimSeam.cs'))).Path
$overall = 0

# The round-2 tip. The N cases must redden against these files.
$priorTip = '93f4db3018048149a5f9dbe2ef76fc28d82ddf52'

# THE ROUND'S EVIDENCE SET. H6 reads the blind-control logs that are actually
# present here and holds both finding documents to that count, because the
# closure table's legend inventoried two logs for a round that ran three and it
# was the last count in those documents still typed. The default is resolved
# from the repository root, so this script still carries no absolute path;
# BUG389_EVIDENCE_DIR overrides it, which is what the two evidence controls use.
$evidence = $env:BUG389_EVIDENCE_DIR
if ([string]::IsNullOrEmpty($evidence)) {
    $evidence = (Join-Path $repo (Join-Path 'ai-collab' 'bugs'))
}

# The shipped files the W, N and S4 cases read. A wiring mutant copies all of
# them and changes one line in one of them, so every other case in the same run
# is an untouched control.
#
# Program.cs IS ON THIS LIST, and it is not a shipped file. W17 asserts that a
# claim deleted from two shipped files is absent, and the round-4 pass left that
# same claim standing in the harness's own comment - outside every file the case
# read, so the suite that certifies the deletion was still making the claim. The
# text under test therefore includes this file. Note what is NOT affected: the
# COMPILED harness in every run comes from $root, so a wiring mutant changes only
# what W17 reads, never what executes.
$wireFiles = @(
    'plugin/SpectatorSession.cs',
    'plugin/Plugin.cs',
    'plugin/RoomActors.cs',
    'plugin/ProximityVictimPatches.cs',
    'plugin/ProximityVictimSeam.cs',
    'plugin/PerfPatches.cs',
    'plugin/ApiClient.cs',
    # N1b reads this one. Round 3's acceptance bar was the seam and the patches
    # and named no third file; what nothing ever scanned was FfaMode.cs, which
    # authors two distance comparisons that PRE-DATE this branch and that the
    # seam INHERITS through its single vanilla call. N1b pins them as inherited,
    # so the file has to be in every mutant root or that case reports "cannot
    # read" instead of a count.
    'plugin/FfaMode.cs',
    # W25's downstream-relation clauses walk the one route that leaves
    # ApiClient.cs: the two tab refreshers are called from NativeUI.Tick,
    # NativeUI.Tick from CompetitiveUI.Tick, and CompetitiveUI.Tick from the
    # persistent tick below its gate. Both files have to be in every mutant root
    # or W25 reports "cannot read" on every wiring run and stops being anyone's
    # inert twin.
    'plugin/NativeUI.cs',
    'plugin/CompetitiveUI.cs',
    'plugin/CompetitiveRounds.csproj',
    'tools/tests/bug389-seam/Program.cs',
    # H1 and H2 read this one: the round's finding bodies, from which the
    # severity census is derived rather than typed, and the streak list, from
    # which the streak ordinal is counted rather than typed.
    'tools/tests/bug389-seam/round-findings.md',
    # H3 reads this one. The round-7 closure table promised a copy at a path
    # inside the gitignored ai-collab tree, so it never reached the pin and the
    # promise a reviewer read could not be resolved. The canonical copy is
    # TRACKED, here beside the harness it describes, so every clone and every pin
    # built from the tip carries it; the two published copies are made from it.
    'tools/tests/bug389-seam/R8-CLOSURES.md',
    # W24 searches this file too. A deletion is not bounded by a search that
    # stops short of a document still making the claim, and the driver's own
    # comments are such a document - the previous deletion survived a round
    # inside one. It has to be in every mutant root or the case reports
    # "cannot read" instead of a count.
    'tools/tests/bug389-seam/run-tests.ps1'
)

function Say([string]$text) { [Console]::WriteLine($text) }

# Paths in this log are printed relative to the repo root: a log is read by
# someone who is not on this machine.
function Rel([string]$p) {
    if ([string]::IsNullOrEmpty($p)) { return '<unset>' }
    $full = [System.IO.Path]::GetFullPath($p)
    if ($full.StartsWith($repo, [System.StringComparison]::OrdinalIgnoreCase)) {
        $r = $full.Substring($repo.Length).TrimStart([char]92, [char]47)
        if ($r -eq '') { return '.' }
        return ($r -replace '\\', '/')
    }
    return $full
}

# ---------------------------------------------------------------------------
# Member spans. Returns @(openBraceIndex, closeBraceIndex) for the C# member
# whose declaration is $signature, or for the region delimited by $signature and
# $endMarker when one is given (project files have no braces to match).
# ---------------------------------------------------------------------------
function Get-MemberSpan([string]$text, [string]$signature, [string]$endMarker) {
    $sigs = ([regex]::Matches($text, [regex]::Escape($signature))).Count
    if ($sigs -ne 1) {
        throw ('member signature matched ' + $sigs + ' site(s), expected 1: ' + $signature)
    }
    $sig = $text.IndexOf($signature, [System.StringComparison]::Ordinal)

    if (-not [string]::IsNullOrEmpty($endMarker)) {
        $close = $text.IndexOf($endMarker, $sig, [System.StringComparison]::Ordinal)
        if ($close -lt 0) { throw ('could not find the end marker after: ' + $signature) }
        return @($sig, $close)
    }

    # Bound the member by INDENTATION, not by counting braces. A literal brace
    # inside a string reads as structure to a counter, and ApiClient.cs carries
    # JSON in string literals - the count never returns to zero and the member
    # cannot be bounded at all. Every member in this tree closes with a brace
    # alone on a line at the declaration's own indentation.
    $open = $text.IndexOf([char]123, $sig)
    if ($open -lt 0) { throw ('could not find a member body for: ' + $signature) }
    $lineStart = $text.LastIndexOf([char]10, $sig) + 1
    $indent = 0
    while ((($lineStart + $indent) -lt $text.Length) -and ($text[$lineStart + $indent] -eq [char]32)) { $indent++ }
    $closer = ([string][char]10) + (' ' * $indent) + '}'
    $close = $text.IndexOf($closer, $open, [System.StringComparison]::Ordinal)
    if ($close -lt 0) { throw ('could not bound the member body for: ' + $signature) }
    return @($open, ($close + $closer.Length - 1))
}

# Splice one anchor inside one member. Asserts EXACTLY ONE hit inside the span,
# reports how many identical lines live elsewhere in the file, and leaves those
# alone.
function Edit-InMember([string]$label, [string]$text, [string]$member, [string]$find, [string]$replace, [string]$endMarker) {
    $span  = Get-MemberSpan $text $member $endMarker
    $open  = [int]$span[0]
    $close = [int]$span[1]
    $body  = $text.Substring($open, $close - $open + 1)
    $inside = ([regex]::Matches($body, [regex]::Escape($find))).Count
    if ($inside -ne 1) {
        throw ('mutation ' + $label + ' anchor matched ' + $inside + ' site(s) inside "' + $member + '", expected 1: ' + $find)
    }
    $total = ([regex]::Matches($text, [regex]::Escape($find))).Count
    Say ('---   anchor in "' + $member + '": 1 site inside, ' + ($total - $inside) + ' elsewhere (left untouched)')
    return $text.Substring(0, $open) + $body.Replace($find, $replace) + $text.Substring($close + 1)
}

function New-RunDir([string]$name, [string]$harnessSource) {
    $dir = Join-Path $work ('run-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    Copy-Item (Join-Path $root 'FixTests.csproj') $dir
    # THE COMPILED HARNESS, which is $root's copy unless a HARNESS MUTANT names
    # another. Every wiring mutant changes only what a case READS; a case that
    # reads the running harness's own objects - H2's permitted-member set - can
    # only be made to fail by changing what EXECUTES, and that is this parameter.
    if ([string]::IsNullOrEmpty($harnessSource)) { $harnessSource = (Join-Path $root 'Program.cs') }
    Copy-Item $harnessSource (Join-Path $dir 'Program.cs')
    return $dir
}

function Invoke-Suite([string]$name, [string]$seamSource, [string]$sourceRoot,
                      [string]$harnessSource, [string]$evidenceDir) {
    $dir  = New-RunDir $name $harnessSource
    $proj = Join-Path $dir 'FixTests.csproj'
    Say ('--- build ' + $name + ' (seam: ' + (Split-Path -Leaf $seamSource) + ')')
    $build = & dotnet build $proj -c Release --nologo -p:SeamSource=$seamSource 2>&1
    $buildCode = $LASTEXITCODE
    Say (($build | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
    if ($buildCode -ne 0) { throw ('build failed for variant ' + $name) }
    $exe = Join-Path $dir (Join-Path 'bin' (Join-Path 'Release' (Join-Path 'net10.0' 'FixTests.exe')))
    if (-not (Test-Path $exe)) { throw ('no test binary produced for variant ' + $name) }
    Say ('--- run ' + $name)
    if ([string]::IsNullOrEmpty($evidenceDir)) { $evidenceDir = $evidence }
    # The invocation, immediately above the results it produced.
    Say ('--- command: ' + (Rel $exe) + '   [BUG389_SOURCE_ROOT=' + (Rel $sourceRoot) +
         '] [BUG389_EVIDENCE_DIR=' + (Rel $evidenceDir) + '] [harness=' +
         (Rel (Join-Path $dir 'Program.cs')) + ']')
    $env:BUG389_SOURCE_ROOT = $sourceRoot
    $env:BUG389_EVIDENCE_DIR = $evidenceDir
    $out = & $exe 2>&1
    $code = $LASTEXITCODE
    $lines = @($out | ForEach-Object { [string]$_ })
    Say ($lines -join [Environment]::NewLine)
    Say ('--- exit ' + $name + ' = ' + $code)
    return [pscustomobject]@{ Name = $name; Code = $code; Lines = $lines }
}

function Test-Result([object]$run, [string]$testPrefix, [string]$wanted) {
    foreach ($line in $run.Lines) {
        $text = [string]$line
        if ($text -match ('^(PASS|FAIL)\s+' + [regex]::Escape($testPrefix) + '\s')) {
            return $text.StartsWith($wanted)
        }
    }
    return $false
}

# $edits is an array of three-element arrays: @(@('member','find','replace'), ...)
function New-Mutant([string]$name, [object[]]$edits) {
    if (-not (Test-Path $work)) { New-Item -ItemType Directory -Path $work -Force | Out-Null }
    $dst  = Join-Path $work ('mutant-' + $name + '.cs')
    $text = [System.IO.File]::ReadAllText($seam)
    # A single nested triple is flattened on the way into an [object[]]
    # parameter, which turns $edit into a STRING and $edit[0] into its first
    # CHARACTER - a one-character "member" that matches everywhere. Re-nest it.
    if ($edits.Count -eq 3 -and ($edits[0] -is [string])) { $edits = @(, $edits) }
    Say ('--- mutant ' + $name + ': ' + $edits.Count + ' edit(s)')
    foreach ($edit in $edits) {
        $text = Edit-InMember $name $text ([string]$edit[0]) ([string]$edit[1]) ([string]$edit[2]) ''
    }
    [System.IO.File]::WriteAllText($dst, $text)
    return $dst
}

# A HARNESS mutation: compile a one-line-changed copy of Program.cs itself and
# leave every file the cases READ alone.
#
# WHY THIS KIND EXISTS. A wiring mutant changes the TEXT a case reads and never
# what executes, which is exactly right for a case whose subject is the shipped
# source - and it is the reason the permitted-member size used to be read off
# source spellings: a count taken from the compiled dictionary would not have
# moved under any mutant this driver could build, so the clause was written to
# measure what the mutant could reach instead of what the round claims. That is a
# measurement chosen by its test harness. H2 reads the running object now, and
# this builder is what can still make it fail: the anchor is resolved inside a
# named member under the same exactly-one-site rule, and the source root handed
# to the run is the untouched tree, so every other case is a control.
#
# THE ANCHOR MUST EXIST AT THE BLIND TIP TOO. A harness mutant is built from
# whatever Program.cs is in the tree, so during a blind control it is built from
# the swapped-in previous harness; an anchor added by this round would throw
# there and take the whole control down with it. That is LENS 8's lesson, applied
# to a new builder rather than re-learned.
# $edits is an array of three-element arrays: @(@('member','find','replace'), ...)
function New-HarnessMutant([string]$name, [object[]]$edits) {
    if (-not (Test-Path $work)) { New-Item -ItemType Directory -Path $work -Force | Out-Null }
    $dst  = Join-Path $work ('harness-' + $name + '.cs')
    $text = [System.IO.File]::ReadAllText((Join-Path $root 'Program.cs'))
    if ($edits.Count -eq 3 -and ($edits[0] -is [string])) { $edits = @(, $edits) }
    Say ('--- harness mutant ' + $name + ': ' + $edits.Count +
         ' edit(s) in tools/tests/bug389-seam/Program.cs (COMPILED, not read)')
    foreach ($edit in $edits) {
        $text = Edit-InMember ('harness-' + $name) $text ([string]$edit[0]) ([string]$edit[1]) ([string]$edit[2]) ''
    }
    [System.IO.File]::WriteAllText($dst, $text)
    return $dst
}

# AN EVIDENCE-SET mutation: copy the round's evidence directory and rename ONE
# file in it. H6 derives the blind-control count from the files that are there,
# so taking a log out of the set must redden it and renaming a file the count
# does not describe must not. Nothing is written to the real evidence set.
function New-EvidenceDir([string]$name, [string]$find, [string]$replace) {
    $dir = Join-Path $work ('evidence-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    if (-not (Test-Path $evidence)) {
        throw ('no evidence set at ' + (Rel $evidence) + ' - H6 derives the blind-control count from it')
    }
    $copied = 0
    foreach ($f in (Get-ChildItem -Path $evidence -File)) {
        $target = $f.Name
        if ($target -eq $find) { $target = $replace }
        Copy-Item $f.FullName (Join-Path $dir $target)
        $copied++
    }
    if (-not (Test-Path (Join-Path $dir $replace))) {
        throw ('evidence mutant ' + $name + ': ' + $find + ' is not in the evidence set, so the ' +
               'rename measured nothing')
    }
    Say ('--- evidence mutant ' + $name + ': ' + $copied + ' file(s) copied, ' + $find + ' -> ' + $replace)
    return $dir
}

# A wiring mutation: copy the shipped files the cases read, change ONE line
# inside ONE named member of ONE of them, and hand the copy to the suite as its
# source root. The shipped tree is never written to.
function Copy-WireFiles([string]$dir) {
    foreach ($rel in $wireFiles) {
        $dst = Join-Path $dir $rel
        New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
        Copy-Item (Join-Path $repo $rel) $dst
    }
}

function New-WireRoot([string]$name, [string]$file, [string]$member, [string]$find, [string]$replace, [string]$endMarker) {
    $dir = Join-Path $work ('wire-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    Copy-WireFiles $dir
    $target = Join-Path $dir $file
    Say ('--- wiring mutant ' + $name + ': in ' + $file)
    $text = [System.IO.File]::ReadAllText($target)
    $text = Edit-InMember ('wire-' + $name) $text $member $find $replace $endMarker
    [System.IO.File]::WriteAllText($target, $text)
    return $dir
}

# The same, for a mutation that is only honest as SEVERAL edits: a genuine swap
# of two exit assignments has to move both, or it is a collapse of one path onto
# another and not a swap. Every edit is resolved inside the named member and
# still has to match EXACTLY ONE site there, so an edit that would rewrite a
# line another edit has already produced is refused rather than applied twice.
# $edits is an array of three-element arrays: @(@('member','find','replace'), ...)
function New-WireRootEdits([string]$name, [string]$file, [object[]]$edits) {
    $dir = Join-Path $work ('wire-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    Copy-WireFiles $dir
    $target = Join-Path $dir $file
    if ($edits.Count -eq 3 -and ($edits[0] -is [string])) { $edits = @(, $edits) }
    Say ('--- wiring mutant ' + $name + ': in ' + $file + ', ' + $edits.Count + ' edit(s)')
    $text = [System.IO.File]::ReadAllText($target)
    foreach ($edit in $edits) {
        $text = Edit-InMember ('wire-' + $name) $text ([string]$edit[0]) ([string]$edit[1]) ([string]$edit[2]) ''
    }
    [System.IO.File]::WriteAllText($target, $text)
    return $dir
}

# The round-2 files, recovered from git rather than copied by hand, so the
# comparison cannot drift and needs no absolute path.
# The same again, for a mutation that is only honest across TWO files. A file
# that declares its own field of a monitored name AND writes the home one
# through a qualified spelling needs the home field to be VISIBLE to it, and
# that visibility lives in the other file; writing only half of it would be a
# mutant that could not compile, which is a different thing from a change a
# maintainer might really make. Each edit is @('file','member','find','replace')
# and is resolved inside the named member of the named file, under the same
# exactly-one-site rule as every other anchor here.
function New-WireRootMulti([string]$name, [object[]]$edits) {
    $dir = Join-Path $work ('wire-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    Copy-WireFiles $dir
    if ($edits.Count -eq 4 -and ($edits[0] -is [string])) { $edits = @(, $edits) }
    $files = @($edits | ForEach-Object { [string]$_[0] } | Sort-Object -Unique)
    Say ('--- wiring mutant ' + $name + ': ' + $edits.Count + ' edit(s) across ' + $files.Count + ' file(s): ' + ($files -join ', '))
    foreach ($edit in $edits) {
        $target = Join-Path $dir ([string]$edit[0])
        $text = [System.IO.File]::ReadAllText($target)
        $text = Edit-InMember ('wire-' + $name) $text ([string]$edit[1]) ([string]$edit[2]) ([string]$edit[3]) ''
        [System.IO.File]::WriteAllText($target, $text)
    }
    return $dir
}

function New-PriorRoot([string]$name, [string]$tip) {
    $dir = Join-Path $work ('prior-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    $missing = @()
    foreach ($rel in $wireFiles) {
        # While $ErrorActionPreference is 'Stop', a native command writing to
        # stderr raises a TERMINATING error, so the exit-code test below is
        # never reached and the whole run dies on the first absent file. The
        # preference is lowered for exactly this call and restored on the next
        # line; the decision is still the exit code, never the text.
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $blob = & git -C $repo show ($tip + ':' + $rel) 2>$null
        $showCode = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        if ($showCode -ne 0) {
            # A file this round ADDED does not exist at the round-2 tip. That is
            # not a reason to abort the one run that proves the N cases can fail;
            # it is omitted and NAMED, and any case that reads it reports "cannot
            # read", which this suite treats as a FAILURE and never as a skip.
            $missing += $rel
            continue
        }
        $dst = Join-Path $dir $rel
        New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
        [System.IO.File]::WriteAllText($dst, (($blob | ForEach-Object { [string]$_ }) -join [Environment]::NewLine))
    }
    if ($missing.Count -ne 0) {
        Say ('---   absent at ' + $tip.Substring(0, 7) + ', omitted and reported by the case that reads it: ' + ($missing -join ', '))
    }
    Say ('--- prior-mechanism root ' + $name + ': ' + $wireFiles.Count + ' files at ' + $tip.Substring(0, 7))
    return $dir
}

function Assert-Mutation([string]$label, [object]$run, [string]$redTest, [string]$controlTest) {
    $red = Test-Result $run $redTest 'FAIL'
    $ctl = Test-Result $run $controlTest 'PASS'
    if ($red -and $ctl) {
        Say ('RESULT ' + $label + ': OK - ' + $redTest + ' reddened, ' + $controlTest + ' control stayed green')
        return $true
    }
    Say ('RESULT ' + $label + ': FAILED - ' + $redTest + ' red=' + $red + ' ' + $controlTest + ' green=' + $ctl)
    return $false
}

function Assert-Mutations([string]$label, [object]$run, [string[]]$redTests, [string]$controlTest) {
    $ok = $true
    $detail = @()
    foreach ($t in $redTests) {
        $red = Test-Result $run $t 'FAIL'
        if (-not $red) { $ok = $false }
        $detail += ($t + '=' + $(if ($red) { 'red' } else { 'GREEN' }))
    }
    $ctl = Test-Result $run $controlTest 'PASS'
    if (-not $ctl) { $ok = $false }
    if ($ok) {
        Say ('RESULT ' + $label + ': OK - ' + ($redTests -join ', ') + ' all reddened, ' + $controlTest + ' control stayed green')
        return $true
    }
    Say ('RESULT ' + $label + ': FAILED - ' + ($detail -join ' ') + ' ' + $controlTest + ' green=' + $ctl)
    return $false
}

# The same again, for a mutation whose edits sit in a file with no braces to
# match - a markdown findings file, a closure table - where each edit's span is
# delimited by a start marker and an end marker instead. Each edit is
# @('start','find','replace','end') and is resolved under the same
# exactly-one-site-inside-the-span rule as every other anchor here.
function New-WireRootSpans([string]$name, [string]$file, [object[]]$edits) {
    $dir = Join-Path $work ('wire-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    Copy-WireFiles $dir
    $target = Join-Path $dir $file
    if ($edits.Count -eq 4 -and ($edits[0] -is [string])) { $edits = @(, $edits) }
    Say ('--- wiring mutant ' + $name + ': in ' + $file + ', ' + $edits.Count + ' edit(s)')
    $text = [System.IO.File]::ReadAllText($target)
    foreach ($edit in $edits) {
        $text = Edit-InMember ('wire-' + $name) $text ([string]$edit[0]) ([string]$edit[1]) ([string]$edit[2]) ([string]$edit[3])
    }
    [System.IO.File]::WriteAllText($target, $text)
    return $dir
}

# The same again, across SEVERAL files. Each edit is
# @('file','start','find','replace','end') and is resolved inside that file's own
# span under the same exactly-one-site rule.
function New-WireRootSpansMulti([string]$name, [object[]]$edits) {
    $dir = Join-Path $work ('wire-' + $name)
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
    Copy-WireFiles $dir
    if ($edits.Count -eq 5 -and ($edits[0] -is [string])) { $edits = @(, $edits) }
    $files = @($edits | ForEach-Object { [string]$_[0] } | Sort-Object -Unique)
    Say ('--- wiring mutant ' + $name + ': ' + $edits.Count + ' edit(s) across ' + $files.Count + ' file(s): ' + ($files -join ', '))
    foreach ($edit in $edits) {
        $target = Join-Path $dir ([string]$edit[0])
        $text = [System.IO.File]::ReadAllText($target)
        $text = Edit-InMember ('wire-' + $name) $text ([string]$edit[1]) ([string]$edit[2]) ([string]$edit[3]) ([string]$edit[4])
        [System.IO.File]::WriteAllText($target, $text)
    }
    return $dir
}

# AN INERT TWIN AS ITS OWN ROOT, not as a second test inside the reddening run.
# The reddening mutant proves the case CAN fail; this proves it does not fail for
# an edit of comparable size in the same file that touches nothing the case
# names. Without both halves a case is either one that cannot fail or one that
# fails on anything, and neither measures the property (#391).
function Assert-Inert([string]$label, [object]$run, [string[]]$greenTests) {
    $ok = $true
    $detail = @()
    foreach ($t in $greenTests) {
        $g = Test-Result $run $t 'PASS'
        if (-not $g) { $ok = $false }
        $detail += ($t + '=' + $(if ($g) { 'green' } else { 'RED' }))
    }
    if ($ok) {
        Say ('RESULT ' + $label + ': OK - ' + ($greenTests -join ', ') + ' stayed green under an inert edit')
        return $true
    }
    Say ('RESULT ' + $label + ': FAILED - ' + ($detail -join ' '))
    return $false
}

# THE NEGATIVE CONTROL ON THE BUILDER ITSELF. Hand it a real anchor that lives
# in a DIFFERENT member and it must refuse: that is the whole difference between
# an anchor resolved inside its member and one counted file-wide.
function Assert-BuilderRejects([string]$label, [string]$member, [string]$find) {
    $threw = $false
    $message = ''
    try {
        New-Mutant ('reject-' + $label) @(, @($member, $find, '// (relocated anchor)')) | Out-Null
    } catch {
        $threw = $true
        $message = [string]$_.Exception.Message
    }
    if ($threw) {
        Say ('RESULT builder rejects a relocated anchor (' + $label + '): OK - ' + $message)
        return $true
    }
    Say ('RESULT builder rejects a relocated anchor (' + $label + '): FAILED - the builder accepted an anchor outside "' + $member + '"')
    return $false
}

Say ('date-utc: ' + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))
Say ('seam:     ' + (Split-Path -Leaf $seam))
Say ('seam sha256: ' + (Get-FileHash -Algorithm SHA256 $seam).Hash)
Say ('source root for the wiring cases: ' + (Rel $repo))
Say ('prior mechanism tip: ' + $priorTip)
Say ''

# ---------- 1. clean ----------
$clean = Invoke-Suite 'clean' $seam $repo
if ($clean.Code -ne 0) { Say 'RESULT clean: FAILED (expected every test to pass)'; $overall = 1 }
else { Say 'RESULT clean: OK - every test passed' }
Say ''

# ---------- 2. the builder's own negative control ----------
# `return runSoFar && prefixReturn;` is a real line of the seam - it lives in
# RunOriginalAfter. Naming ShouldRepair as its member must be refused rather
# than silently spliced somewhere else.
if (-not (Assert-BuilderRejects 'fold-line-in-the-gate' `
    'internal static bool ShouldRepair(ProximityGateState state, bool targetsOther)' `
    '            return runSoFar && prefixReturn;')) { $overall = 1 }
Say ''

# ---------- 2b. the capability key has never been released ----------
# K3 holds the seam's non-rotation argument to one fact: no released build
# advertises cr_prox1. That is a claim about the RELEASE HISTORY, which no
# compiled case can reach, so the runner checks it here.
#
# WITH A POSITIVE CONTROL, because a search that finds nothing proves nothing
# (#342/#441): cr_pois2 is a capability key of the same family that DID ship, so
# the same probe against the same tag must find it. A probe that reports both
# keys absent has told us about the probe, not about the keys.
$baseTag = 'v1.40.3'
& git -C $repo grep -q 'cr_prox1' $baseTag -- plugin 2>&1 | Out-Null
$keyAbsentAtBase = ($LASTEXITCODE -ne 0)
& git -C $repo grep -q 'cr_pois2' $baseTag -- plugin 2>&1 | Out-Null
$controlKeyPresent = ($LASTEXITCODE -eq 0)
if ($keyAbsentAtBase -and $controlKeyPresent) {
    Say ('RESULT capability key never released: OK - cr_prox1 absent at ' + $baseTag + ', control key cr_pois2 present at the same tag')
} else {
    Say ('RESULT capability key never released: FAILED - cr_prox1 absent=' + $keyAbsentAtBase + ', control cr_pois2 present=' + $controlKeyPresent)
    $overall = 1
}
Say ''

# ---------- 3. answer only the first time ----------
# THE DEFECT, PUT BACK. Vanilla resolves its victim once and keeps it; if this
# decision answered only the first time the effect would keep its first victim
# exactly as an unpatched build does. This is the mutation that proves the suite
# measures the bug and not merely that a function is reachable.
$mutOnce = New-Mutant 'once' @(
    @('internal static class ProximityVictim',
      '        internal const int MaxOutcomeSignals = 1;',
      '        internal const int MaxOutcomeSignals = 1; private static bool _mutantAnswered;'),
    @('internal static ProximityPrefixAction VictimAction(',
      '            return ProximityPrefixAction.WriteVictimAndRun;',
      '            { if (_mutantAnswered) return ProximityPrefixAction.RunVanillaUntouched; _mutantAnswered = true; return ProximityPrefixAction.WriteVictimAndRun; }')
)
$runOnce = Invoke-Suite 'mut-once' $mutOnce $repo
if (-not (Assert-Mutation 'answer-once mutation' $runOnce 'V1' 'V2')) { $overall = 1 }
Say ''

# ---------- 4. repair a call no ring drives ----------
# The defect is a field that survives REPEATED invocation, and only a
# PlayerInRangeTrigger invokes these effects repeatedly. Drop the term and an
# AttackTrigger- or DelayEvent-driven call is repaired against a rule this
# repair never measured.
$mutRingless = New-Mutant 'ringless' @(, @(
    'internal static ProximityPrefixAction VictimAction(',
    '            if (!ringDriven) return ProximityPrefixAction.RunVanillaUntouched;',
    '            if (false) return ProximityPrefixAction.RunVanillaUntouched;'))
$runRingless = Invoke-Suite 'mut-ringless' $mutRingless $repo
if (-not (Assert-Mutation 'ring-driven mutation' $runRingless 'V3' 'V2')) { $overall = 1 }
Say ''

# ---------- 5. write an empty resolution ----------
# Vanilla dereferences its victim field with no null guard
# (DealDamageToPlayer.cs:45). Writing the empty answer turns "the game's own
# targeting found nobody" into an exception on a path vanilla, holding its
# cache, never takes.
$mutWriteNull = New-Mutant 'writenull' @(, @(
    'internal static ProximityPrefixAction VictimAction(',
    '            if (!vanillaAnswered) return ProximityPrefixAction.RunVanillaUntouched;',
    '            if (false) return ProximityPrefixAction.RunVanillaUntouched;'))
$runWriteNull = Invoke-Suite 'mut-writenull' $mutWriteNull $repo
if (-not (Assert-Mutation 'empty-resolution mutation' $runWriteNull 'V4' 'V2')) { $overall = 1 }
Say ''

# ---------- 6. let the repair suppress the original ----------
# The bar row the previous design could not meet. A victim repair that can
# return false can turn a change about WHO takes damage into a change about
# WHETHER anyone does.
$mutSuppress = New-Mutant 'suppress' @(, @(
    'internal static ProximityPrefixAction VictimAction(',
    '            if (!ringDriven) return ProximityPrefixAction.RunVanillaUntouched;',
    '            if (!ringDriven) return ProximityPrefixAction.SkipOriginal;'))
$runSuppress = Invoke-Suite 'mut-suppress' $mutSuppress $repo
if (-not (Assert-Mutation 'suppression mutation' $runSuppress 'V5' 'V2')) { $overall = 1 }
Say ''

# ---------- 7. make the capability gate vacuous ----------
$mutGate = New-Mutant 'gate' @(, @(
    'internal static bool ShouldRepair(ProximityGateState state, bool targetsOther)',
    '            return state == ProximityGateState.Capable && targetsOther;',
    '            return targetsOther;'))
$runGate = Invoke-Suite 'mut-gate' $mutGate $repo
if (-not (Assert-Mutation 'gate mutation' $runGate 'G1' 'G2')) { $overall = 1 }
Say ''

# ---------- 8. give two gate states one reason line ----------
# The line is also the budget key, so two causes sharing it means the second is
# never printed and the reader is told the first one instead: "the room does not
# all carry the repair" for a patch that failed to attach on this seat.
$mutGateReason = New-Mutant 'gatereason' @(, @(
    'internal static string GateReason(ProximityGateState state)',
    '                case ProximityGateState.PatchesNotAttached: return "this seat''s repair patches are not attached";',
    '                case ProximityGateState.PatchesNotAttached: return "the room does not all carry the repair";'))
$runGateReason = Invoke-Suite 'mut-gatereason' $mutGateReason $repo
if (-not (Assert-Mutation 'gate-reason mutation' $runGateReason 'G4' 'G2')) { $overall = 1 }
Say ''

# ---------- 8b. let a disabled seat advertise the repair anyway ----------
# THE ROUND-3 HIGH, PUT BACK. Drop the mod-disabled term from the one local
# predicate and a seat whose compat check switched the mod off still answers
# Capable to the advertiser, so it tells the room it will repair while its own
# gate refuses. Its peers then re-resolve the victim every armed tick while this
# seat drains the stale cached one.
$mutLocalGate = New-Mutant 'localgate' @(, @(
    'internal static ProximityGateState LocalGateState(bool modDisabled, bool patchesLive)',
    '            if (modDisabled) return ProximityGateState.ModDisabled;',
    '            if (false) return ProximityGateState.ModDisabled;'))
$runLocalGate = Invoke-Suite 'mut-localgate' $mutLocalGate $repo
if (-not (Assert-Mutation 'local-capability mutation' $runLocalGate 'G6' 'G2')) { $overall = 1 }
Say ''

# ---------- 8c. never withdraw a staged advertisement ----------
# The other half of the same HIGH. Staging correctly is not enough on its own:
# the gate can stop saying Capable AFTER the key has been staged, and a seat that
# never withdraws leaves its peers repairing against a seat that will not.
$mutNoRevoke = New-Mutant 'norevoke' @(, @(
    'internal static bool ShouldRevokeCapability(ProximityGateState local, bool advertised)',
    '            return advertised && local != ProximityGateState.Capable;',
    '            return false;'))
$runNoRevoke = Invoke-Suite 'mut-norevoke' $mutNoRevoke $repo
if (-not (Assert-Mutation 'capability-withdrawal mutation' $runNoRevoke 'G7' 'G2')) { $overall = 1 }
Say ''

# ---------- 8d. repair an effect that targets its own player ----------
# V6's OWN mutant. V6 states that all four terms are required, and until now it
# had no mutation of its own - it only ever reddened alongside V3 or V4, so the
# no-mutant documentation could not honestly list it either way. Dropping the
# polarity term at the CALL SITE leaves ShouldRepair itself intact, so G1, G5 and
# D3 - which ask that function directly - stay green and V6 is the case that
# sees it.
$mutOwnPlayer = New-Mutant 'ownplayer' @(, @(
    'internal static ProximityPrefixAction VictimAction(',
    '            if (!ShouldRepair(gate, targetsOther)) return ProximityPrefixAction.RunVanillaUntouched;',
    '            if (!ShouldRepair(gate, true)) return ProximityPrefixAction.RunVanillaUntouched;'))
$runOwnPlayer = Invoke-Suite 'mut-ownplayer' $mutOwnPlayer $repo
if (-not (Assert-Mutation 'own-player-term mutation' $runOwnPlayer 'V6' 'V2')) { $overall = 1 }
Say ''

# ---------- 8e. give two outcomes of the vanilla call one reason line ----------
# Four paths through the one call into the game's own targeting used to print
# one sentence between them. The line is also the budget key, so two paths
# sharing it means the second cause can never be printed in a session at all.
$mutAnswerReason = New-Mutant 'answerreason' @(, @(
    'internal static string VanillaAnswerReason(ProximityVanillaAnswer vanilla)',
    '                case ProximityVanillaAnswer.NoHolder: return "this effect has no player of its own to target from";',
    '                case ProximityVanillaAnswer.NoHolder: return "the game''s own targeting answered with nobody";'))
$runAnswerReason = Invoke-Suite 'mut-answerreason' $mutAnswerReason $repo
if (-not (Assert-Mutations 'vanilla-outcome-reason mutation' $runAnswerReason @('D4', 'D5') 'D2')) { $overall = 1 }
Say ''

# ---------- 8f. misname ONE outcome, keeping every line distinct ----------
# THE CASE D5 COULD NOT SEE. D5's loop used to compare DeclineReason at its
# fall-through with VanillaAnswerReason - the same expression on both sides - so
# it was true for every assignment of lines to outcomes, and the swap detection
# it claimed lived entirely in three literals covering three of the six
# outcomes. NotAsked's line was pinned nowhere: this mutation gives it a new,
# still-distinct sentence, and before D5 was rebuilt against an independent
# table every single check in the suite stayed green on it. D4 is the control
# and must STAY green - the lines are still all different, which is exactly why
# D4 cannot be the case that catches this.
$mutAnswerLine = New-Mutant 'answerline' @(, @(
    'internal static string VanillaAnswerReason(ProximityVanillaAnswer vanilla)',
    '                case ProximityVanillaAnswer.NotAsked: return "the game''s own targeting was not asked";',
    '                case ProximityVanillaAnswer.NotAsked: return "the proximity ring never armed on this tick";'))
$runAnswerLine = Invoke-Suite 'mut-answerline' $mutAnswerLine $repo
if (-not (Assert-Mutation 'single-outcome-misnaming mutation' $runAnswerLine 'D5' 'D4')) { $overall = 1 }
Say ''

# ---------- 8g. SWAP TWO EXIT ASSIGNMENTS IN THE PATH PLUMBING ----------
# THE SURFACE THE TWO RUNS ABOVE COULD NOT REACH, and the reason this pair
# exists. `answerreason` and `answerline` both edit the SEAM's enum-to-sentence
# table; the code that decides which outcome a PATH gets is VanillaVictimFor in
# the patches file, and nothing in the round-4 suite touched it. A swapped
# assignment there leaves every sentence distinct and every sentence bound to
# its own enum value, so D4, D5 and BOTH advertised mutation runs stayed green
# while a missing PlayerManager would report itself as an effect with no holder.
# A mutant that cannot reach the code its case claims to close is a check that
# cannot fail (#342/#431), which is what this moves.
#
# It is a WIRING mutant because the harness cannot compile that file - it
# carries Unity, Photon and Harmony - so D6 reads its text. Two edits, because a
# swap that moves one assignment is a collapse and not a swap; each is still
# resolved inside VanillaVictimFor and still has to match exactly one site there.
#
# D4 AND D5 ARE THE CONTROLS AND MUST STAY GREEN. That is what says the surface
# actually moved rather than being duplicated: the seam is untouched here, so
# the cases that measure the seam cannot see this and the case that measures the
# path can.
$wirePathSwap = New-WireRootEdits 'pathswap' 'plugin/ProximityVictimPatches.cs' @(
    @('private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)',
      '                if (pm == null) { answer = ProximityVanillaAnswer.NoManager; return null; }',
      '                if (pm == null) { answer = ProximityVanillaAnswer.NoHolder; return null; }'),
    @('private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)',
      '                if (holder == null) { answer = ProximityVanillaAnswer.NoHolder; return null; }',
      '                if (holder == null) { answer = ProximityVanillaAnswer.NoManager; return null; }')
)
$runWirePathSwap = Invoke-Suite 'wire-pathswap' $seam $wirePathSwap
if (-not (Assert-Mutation 'path-to-outcome swap, D4 control' $runWirePathSwap 'D6' 'D4')) { $overall = 1 }
if (-not (Assert-Mutation 'path-to-outcome swap, D5 control (the sentence-table case stays green)' `
    $runWirePathSwap 'D6' 'D5')) { $overall = 1 }
Say ''

# ---------- 8h. report a thrown resolution as one that answered ----------
# The round-3 MEDIUM in its original shape, planted back at the only place that
# can produce it now. A resolution that could not complete is not a resolution
# that ran and found nobody: the second sentence sends a reader to look at who
# was standing where, for a call that never reached the ranking, and the
# sentence is also the budget key so the true cause is then unprintable for the
# session. D4 and D5 are green on it - the seam still names both outcomes
# correctly - and D6 is the case that sees the exit lying about which one it is.
$wirePathThrew = New-WireRoot 'paththrew' 'plugin/ProximityVictimPatches.cs' `
    'private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)' `
    '            catch { answer = ProximityVanillaAnswer.Threw; return null; }' `
    '            catch { answer = ProximityVanillaAnswer.Nobody; return null; }' ''
$runWirePathThrew = Invoke-Suite 'wire-paththrew' $seam $wirePathThrew
if (-not (Assert-Mutation 'thrown-resolution misreported as answered-with-nobody, D4 control' `
    $runWirePathThrew 'D6' 'D4')) { $overall = 1 }
if (-not (Assert-Mutation 'thrown-resolution misreported as answered-with-nobody, D5 control' `
    $runWirePathThrew 'D6' 'D5')) { $overall = 1 }
Say ''

# ---------- 9. collapse the outcome signals onto one budget ----------
# Drop the reason from the key, so two reasons under one outcome share a budget
# and the second is never printed. S2 is the control: the LINE still names all
# three things, so it cannot see the key change.
$mutReasonKey = New-Mutant 'reasonkey' @(, @(
    'internal static string SignalKey(string outcome, string reason)',
    '            return DiagKeyRoot + "/" + outcome + "/" + reason;',
    '            return DiagKeyRoot + "/" + outcome;'))
$runReasonKey = Invoke-Suite 'mut-reasonkey' $mutReasonKey $repo
if (-not (Assert-Mutation 'outcome-signal mutation' $runReasonKey 'S1' 'S2')) { $overall = 1 }
Say ''

# ---------- 10. key the capability cache on the frame alone ----------
$mutCapKey = New-Mutant 'capkey' @(, @(
    'internal bool Evaluate(int frame, long stamp, Func<bool> census)',
    '            if (_has && frame == _frame && stamp == _stamp) return _value;',
    '            if (_has && frame == _frame) return _value;'))
$runCapKey = Invoke-Suite 'mut-capkey' $mutCapKey $repo
if (-not (Assert-Mutation 'capability-cache-key mutation' $runCapKey 'C1' 'C2')) { $overall = 1 }
Say ''

# ---------- 11. stop clearing the fighter capability on spectator staging ----
$mutKeys = New-Mutant 'fighterkeys' @(, @(
    'internal static class ProximityVictim',
    '        internal static readonly string[] FighterCapabilityKeys = new string[] { CapabilityProp };',
    '        internal static readonly string[] FighterCapabilityKeys = new string[0];'))
$runKeys = Invoke-Suite 'mut-fighterkeys' $mutKeys $repo
if (-not (Assert-Mutation 'fighter-capability-keys mutation' $runKeys 'K1' 'K2')) { $overall = 1 }
Say ''

# ---------- 12. make the prefix fold keep the last answer ----------
# HarmonyX ANDs every prefix's return into __runOriginal whichever order it
# called them in - read from the shipped 0Harmony.dll and cited on
# RunOriginalAfter. Fold only the last answer instead and the two orders
# disagree wherever the two SHIPPED prefixes disagree, which is what P3
# composes. P1 is the control: it does not use the fold at all.
$mutChain = New-Mutant 'chainlast' @(, @(
    'internal static bool RunOriginalAfter(bool runSoFar, bool prefixReturn)',
    '            return runSoFar && prefixReturn;',
    '            return prefixReturn;'))
$runChain = Invoke-Suite 'mut-chainlast' $mutChain $repo
# P5 too: the conjunction is what carries the bound on StunPlayer.Go, so a fold
# that keeps only the last answer must be visible to the case that says so.
if (-not (Assert-Mutations 'prefix-fold mutation' $runChain @('P3', 'P5') 'P1')) { $overall = 1 }
Say ''

# ---------- 13. open the sibling null guard ----------
# Moving PerfPatches.StunPlayerGoNullGuard's decision into the seam is a
# refactor and must not change what it decides. P4 is what says so; without a
# mutant it would be a restatement of the code beneath it.
$mutGuard = New-Mutant 'guardopen' @(, @(
    'internal static ProximityPrefixAction NullGuardAction(',
    '            return ProximityPrefixAction.SkipOriginal;',
    '            return ProximityPrefixAction.RunVanillaUntouched;'))
$runGuard = Invoke-Suite 'mut-guardopen' $mutGuard $repo
# P5's second half is that the two shipped prefixes CAN disagree. Open the guard
# and they never do, which would make scoping the bound to a conjunction an
# argument about nothing - so P5 must redden here as well as P4.
if (-not (Assert-Mutations 'null-guard mutation' $runGuard @('P4', 'P5') 'P1')) { $overall = 1 }
Say ''

# ---------- 14-21. the wiring: the halves this harness cannot compile --------
# Each of these changes one shipped line inside one named member of a COPY of
# the tree and points the suite at the copy.

$wireSpec = New-WireRoot 'spec' 'plugin/SpectatorSession.cs' `
    'internal static bool StagePreJoinProperties(string localSteamId)' `
    '                foreach (var capabilityKey in ProximityVictim.FighterCapabilityKeys)' `
    '                foreach (var capabilityKey in new string[0])' ''
$runWireSpec = Invoke-Suite 'wire-spec' $seam $wireSpec
if (-not (Assert-Mutation 'spectator-clearing wiring' $runWireSpec 'W1' 'W5')) { $overall = 1 }
Say ''

$wireProp = New-WireRoot 'prop' 'plugin/Plugin.cs' `
    'public void OnPlayerPropertiesUpdate(Photon.Realtime.Player target, ExitGames.Client.Photon.Hashtable changedProps)' `
    '                    || changedProps.ContainsKey(ProximityVictim.CapabilityProp))' `
    '                    || false)' ''
$runWireProp = Invoke-Suite 'wire-prop' $seam $wireProp
if (-not (Assert-Mutation 'capability-delivery wiring' $runWireProp 'W2' 'W5')) { $overall = 1 }
Say ''

$wireGen = New-WireRoot 'gen' 'plugin/RoomActors.cs' `
    'private static void EnsureCacheRoom()' `
    '                _rosterGeneration++;' `
    '                // (mutant) a room change no longer moves the generation' ''
$runWireGen = Invoke-Suite 'wire-gen' $seam $wireGen
if (-not (Assert-Mutation 'room-change wiring' $runWireGen 'W3' 'W5')) { $overall = 1 }
Say ''

$wireDoc = New-WireRoot 'doc' 'plugin/ProximityVictimPatches.cs' `
    'internal static PlayerInRangeTrigger OwningTrigger(Transform start)' `
    '            // This is the ONLY thing the walk is asked. The repair does not read' `
    '            // (mutant) this block has drifted off the member it describes' ''
$runWireDoc = Invoke-Suite 'wire-doc' $seam $wireDoc
if (-not (Assert-Mutation 'no-ring-reasoning wiring' $runWireDoc 'W8' 'W1')) { $overall = 1 }
Say ''

$wireMsb = New-WireRoot 'msb' 'plugin/CompetitiveRounds.csproj' `
    '<MusicPreviewsToCopy Include="music\*_preview.ogg" />' `
    '    <MusicManifestToCopy Include="music\manifest.json" Condition="Exists(''music\manifest.json'')" />' `
    '    <MusicManifestToCopy Include="music\manifest.json" />' `
    '</ItemGroup>'
$runWireMsb = Invoke-Suite 'wire-msb' $seam $wireMsb
if (-not (Assert-Mutation 'music-manifest-condition wiring' $runWireMsb 'W10' 'W1')) { $overall = 1 }
Say ''

$wirePerf = New-WireRoot 'perf' 'plugin/PerfPatches.cs' `
    'static bool Prefix(StunPlayer __instance)' `
    '            return ProximityVictim.PrefixReturn(action);' `
    '            return action != ProximityPrefixAction.SkipOriginal;' ''
$runWirePerf = Invoke-Suite 'wire-perf' $seam $wirePerf
if (-not (Assert-Mutation 'sibling-prefix-shape wiring' $runWirePerf 'W11' 'W1')) { $overall = 1 }
Say ''

$wireSiteKey = New-WireRoot 'sitekey' 'plugin/ProximityVictimPatches.cs' `
    'internal static void NoteOutcome(string site, string outcome, string why)' `
    '                ProximityVictim.SignalKey(outcome, why),' `
    '                ProximityVictim.SignalKey(site + "/" + outcome, why),' ''
$runWireSiteKey = Invoke-Suite 'wire-sitekey' $seam $wireSiteKey
if (-not (Assert-Mutation 'per-site-budget wiring' $runWireSiteKey 'S4' 'W1')) { $overall = 1 }
Say ''

# Plant a proximity comparison of our own back into the repair. This is the
# negative control for the round's acceptance assertion: without it "no ranking
# here" is a statement no run has ever seen fail.
$wireRank = New-WireRoot 'rank' 'plugin/ProximityVictimPatches.cs' `
    'private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)' `
    '                if (victim == null) { answer = ProximityVanillaAnswer.Nobody; return null; }' `
    '                if (victim == null || Vector2.Distance(holder.transform.position, victim.transform.position) > 99f) { answer = ProximityVanillaAnswer.Nobody; return null; }' ''
$runWireRank = Invoke-Suite 'wire-rank' $seam $wireRank
if (-not (Assert-Mutation 'authored-ranking wiring' $runWireRank 'N1' 'W1')) { $overall = 1 }
Say ''

# Plant a roster read of our own back into the repair.
$wireRoster = New-WireRoot 'roster' 'plugin/ProximityVictimPatches.cs' `
    'private static Player VanillaVictimFor(Component instance, out ProximityVanillaAnswer answer)' `
    '                if (pm == null) { answer = ProximityVanillaAnswer.NoManager; return null; }' `
    '                if (pm == null || pm.players == null) { answer = ProximityVanillaAnswer.NoManager; return null; }' ''
$runWireRoster = Invoke-Suite 'wire-roster' $seam $wireRoster
if (-not (Assert-Mutation 'authored-roster wiring' $runWireRoster 'N2' 'W1')) { $overall = 1 }
Say ''

# Plant a SECOND copy of the local conjunction into the gate. The pure half of
# the round-3 HIGH is G6's; this is the half no case can execute. A member that
# asks the one predicate AND re-derives the conjunction beside it is exactly the
# shape the finding described, and a required-anchor check alone would stay green
# on it.
$wireAdvertise = New-WireRoot 'advertise' 'plugin/ProximityVictimPatches.cs' `
    'internal static ProximityGateState GateState()' `
    '                ProximityGateState local = LocalCapability();' `
    '                ProximityGateState local = Plugin.modDisabled ? ProximityGateState.ModDisabled : LocalCapability();' ''
$runWireAdvertise = Invoke-Suite 'wire-advertise' $seam $wireAdvertise
if (-not (Assert-Mutations 'second-copy-of-the-local-answer wiring' $runWireAdvertise @('W14b', 'W15b') 'W1')) { $overall = 1 }
Say ''

# Plant a SECOND read of the OTHER global, outside every member the suite bounds.
# "One predicate, no second copy" was claimed for both globals and guarded
# file-wide for only one: W14b counted the mod-disabled flag, while PatchesLive
# was forbidden only inside StageInto, GateState and RepublishCapability. A read
# in Census - a member none of those three name - re-creates the two-expressions
# shape with the harness reporting the property intact. W14c is the bound that
# was missing; this is what proves it can fail.
$wirePatchesLive = New-WireRoot 'patcheslive' 'plugin/ProximityVictimPatches.cs' `
    'private static bool Census()' `
    '            PhotonPlayer[] actors = PhotonNetwork.PlayerList;' `
    '            PhotonPlayer[] actors = PatchesLive ? PhotonNetwork.PlayerList : null;' ''
$runWirePatchesLive = Invoke-Suite 'wire-patcheslive' $seam $wirePatchesLive
if (-not (Assert-Mutation 'second-copy-of-the-attachment-answer wiring' $runWirePatchesLive 'W14c' 'W1')) { $overall = 1 }
Say ''

# Put the compat site's overstated claim back. "A pre-join stage may already
# have advertised it" is false on a first initialisation: this key is staged
# pre-join from the queue poll, which cannot run before ApiClient.Initialize,
# and the compat-fail branch returns above that call. A tester pointed at that
# route to validate the withdrawal waits for a line it cannot produce.
$wireCompatClaim = New-WireRoot 'compatclaim' 'plugin/Plugin.cs' `
    'private void DoInitialize()' `
    '                        // staged PRE-JOIN from the queue poll, which cannot run' `
    '                        // A pre-join stage may already have advertised it, and' ''
$runWireCompatClaim = Invoke-Suite 'wire-compatclaim' $seam $wireCompatClaim
if (-not (Assert-Mutation 'compat-site-claim wiring' $runWireCompatClaim 'W17' 'W1')) { $overall = 1 }
Say ''

# Move the attachment-shortfall message and leave the comment quoting the old
# one. That is the state round 4 shipped into: the doc told the maintainer to
# grep for "patches did NOT attach (2/3)" after round 4 had replaced it, so the
# grep returns nothing and the absence reads as a complete attachment count for
# a repair that has gone inert on every seat. W19 binds the quote to the
# expression that builds it.
$wireLogQuote = New-WireRoot 'logquote' 'plugin/ProximityVictimPatches.cs' `
    'internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)' `
    '                        + RequiredAttachments + " patches live); this seat stays on vanilla for the session");' `
    '                        + RequiredAttachments + " patches did NOT attach); this seat stays on vanilla");' ''
$runWireLogQuote = Invoke-Suite 'wire-logquote' $seam $wireLogQuote
if (-not (Assert-Mutation 'quoted-log-line wiring' $runWireLogQuote 'W19' 'W1')) { $overall = 1 }
# W23's INERT TWIN. This run edits StageInto - the same member W23 bounds - on a
# line W23 makes no claim about, so W23 must stay green here while it reddens
# under wire-stagelatch. Without this row "W23 reddens when the advertising
# branch is latched" and "W23 reddens whenever anything in StageInto moves" look
# the same from the log.
if (-not (Assert-Mutation 'quoted-log-line wiring, W23 inert twin' $runWireLogQuote 'W19' 'W23')) { $overall = 1 }
# The same service for the two cases added this round. Both read this file;
# neither makes a claim about the line this mutant moves, so both must stay
# green, or "W24/W25 redden for their own reason" and "they redden whenever the
# patches file moves" would read identically from the log.
if (-not (Assert-Mutation 'quoted-log-line wiring, W24 inert twin' $runWireLogQuote 'W19' 'W24')) { $overall = 1 }
if (-not (Assert-Mutation 'quoted-log-line wiring, W25 inert twin' $runWireLogQuote 'W19' 'W25')) { $overall = 1 }
Say ''

# ---------- latch the ADVERTISEMENT on the shortfall flag ----------
# Put the mechanism two comments claimed into the code that never had it. The
# field's own doc described the flag as settling the question for the rest of
# the session, and the withdrawal's doc carried that latch as a PREMISE for why
# no advertising direction is needed. What the flag actually does is suppress a
# second LogError on the branch that has already declined. A decline IS final on
# this build - but for a different reason, every term of the guard being fixed
# before the first attempt can run (W25) - so this is the shape the comments
# described and W23 has to be able to fail on it (#351/#434).
$wireStageLatch = New-WireRoot 'stagelatch' 'plugin/ProximityVictimPatches.cs' `
    'internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)' `
    '                if (local == ProximityGateState.Capable && !_withdrawn)' `
    '                if (local == ProximityGateState.Capable && !_withdrawn && !_stageFailedPermanently)' ''
$runWireStageLatch = Invoke-Suite 'wire-stagelatch' $seam $wireStageLatch
if (-not (Assert-Mutation 'advertisement-latched-on-the-shortfall-flag wiring' $runWireStageLatch 'W23' 'W1')) { $overall = 1 }
Say ''

# ---------- latch it through the OTHER one-way flag instead ----------
# The same drift, installed where W23's first three assertions cannot see it.
# The guard text does not move; the shortfall flag still occurs on exactly two
# code lines in the member and still after the staging write; and the declining
# branch now latches the withdrawal, so the shortfall flag gates a capability
# after all and the paragraph both files carry is false. W23 stayed green on
# this shape until it grew the assignment assertion - a case that bounds one
# SPELLING of a drift is not a bound on the property (#432).
#
# W25 is its inert twin and must stay GREEN: this write writes true, so the
# one-way premise the reachability argument needs is untouched. That is the
# distinction the two cases are split along, and this row is what shows it.
$wireStageWithdraw = New-WireRoot 'stagewithdraw' 'plugin/ProximityVictimPatches.cs' `
    'internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)' `
    '                    _stageFailedPermanently = true;' `
    '                    _stageFailedPermanently = true; _withdrawn = true;' ''
$runWireStageWithdraw = Invoke-Suite 'wire-stagewithdraw' $seam $wireStageWithdraw
if (-not (Assert-Mutation 'advertisement-latched-through-the-withdrawal-flag wiring' $runWireStageWithdraw 'W23' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'withdrawal-flag latch, W25 inert twin' $runWireStageWithdraw 'W23' 'W25')) { $overall = 1 }
Say ''

# ---------- the SAME latch, spelled without spaces ----------
# THE ROW ABOVE IS THE DRIFT; THIS ONE IS THE PROPERTY. Round 5 closed the
# withdrawal-flag latch with an assertion that counted the text "_withdrawn = ",
# so it recognised the spaced spelling above and nothing else: "_withdrawn=true;"
# installed exactly the same latch and left W23 green. A case that recognises one
# spelling of an operation is a check that cannot fail for the operation it names
# (#342/#431), and a flag names a line while the defect is a class (#432). W23 now
# classifies writes by what follows the identifier, so both spellings - and
# "_withdrawn  =  true;", and the operator on the next line - reach the same bound.
#
# W25 is the inert twin again and must stay GREEN for the same reason as above:
# the write writes true, so the one-way premise is untouched.
$wireStageWithdrawTight = New-WireRoot 'stagewithdrawtight' 'plugin/ProximityVictimPatches.cs' `
    'internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)' `
    '                    _stageFailedPermanently = true;' `
    '                    _stageFailedPermanently = true; _withdrawn=true;' ''
$runWireStageWithdrawTight = Invoke-Suite 'wire-stagewithdrawtight' $seam $wireStageWithdrawTight
if (-not (Assert-Mutation 'withdrawal-flag latch spelled with no spaces' $runWireStageWithdrawTight 'W23' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'no-space withdrawal latch, W25 inert twin' $runWireStageWithdrawTight 'W23' 'W25')) { $overall = 1 }
Say ''

# ---------- put the retracted latch sentence back in a SHIPPED file ----------
# The eighth deletion's absence bound. Until W24 there was none: the latch
# language was recorded as deleted in the notes and held only by W23, which
# reads code and never reads a comment. This plants the retracted sentence back
# into the seam paragraph that used to carry it as a premise - the one place a
# later reader re-derives "there is no advertising direction" from - and leaves
# every line of code alone. Before W24 the whole suite stayed green on this.
#
# THIS FILE IS INSIDE W24'S SURFACE, so the sentence it plants may not be spelled
# whole here either - the case would find it in the driver and could never count
# zero (#342). It is assembled from two halves for exactly the reason the needles
# in Program.cs are, and the concatenation is the point, not a style.
$latchBackLine = '        /// that - an earlier wording had a seat that declined once never ' + 'staging again in that session. It is read only on the branch that has ALREADY declined, where'
$wireLatchProse = New-WireRoot 'latchprose' 'plugin/ProximityVictimSeam.cs' `
    'internal static class ProximityVictim' `
    '        /// that. It is read only on the branch that has ALREADY declined, where' `
    $latchBackLine ''
$runWireLatchProse = Invoke-Suite 'wire-latchprose' $seam $wireLatchProse
if (-not (Assert-Mutation 'retracted-latch-sentence wiring' $runWireLatchProse 'W24' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'retracted-latch-sentence, W23 inert twin' $runWireLatchProse 'W24' 'W23')) { $overall = 1 }
Say ''

# ---------- make the attachment count two-way, ON A PATH THAT RUNS ----------
# The premise W25 exists for. The reachability argument that replaced the latch
# says a seat which declined once cannot become Capable later, and its first
# clause is that the attachment count can only rise. A direct assignment is how
# that stops being true; the count would then be able to fall below the required
# three and climb back after a staging attempt had already been declined, and
# the shortfall message - which W19 pins and the TeleportToOpponent doc tells a
# maintainer to grep for - would be asserting something about the session that
# the state space no longer allows (#438/#443).
#
# THE ROUND-5 FORM OF THIS MUTANT WAS UNREACHABLE AND IS DELETED, not patched.
# It reset the count behind `which == null`, and the writer's only three callers
# are the Harmony cleanup callbacks at ProximityVictimPatches.cs:664, :726 and
# :773, each passing a string LITERAL. No call can be null, so that mutant made
# the source text two-way and left the program one-way: it advertised a failure
# it could not produce, and the only thing its red line proved was that the case
# recognised the spelling "_attached = " (#342/#431).
#
# THIS FORM KEYS ON THE LITERAL THE StunPlayer CLEANUP ACTUALLY PASSES, so on a
# seat where that patch attaches the count really does fall back to zero after
# having risen. It is spelled "_attached=0;" with no spaces on purpose: the same
# mutant then also shows the case is bound to the OPERATION and not to one
# spelling, and it is why the round-5 harness stays green on it in the blind run.
$wireReach = New-WireRoot 'reach' 'plugin/ProximityVictimPatches.cs' `
    'internal static void MarkAttached(string which)' `
    '            _attached++;' `
    '            _attached++; if (which == "StunPlayer.Go") _attached=0;' ''
$runWireReach = Invoke-Suite 'wire-reach' $seam $wireReach
if (-not (Assert-Mutation 'two-way-attachment-count wiring' $runWireReach 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'two-way attachment count, W23 inert twin' $runWireReach 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- the reviewer's own scenario: satisfy the count on the DECLINE ----
# The other half of the same property, and the shape the round-5 case could not
# see at all. Writing the attachment count to RequiredAttachments on the branch
# that has just declined makes the first attempt decline and a LATER pre-join
# attempt advertise, with no patch ever having attached - which is precisely the
# seat the whole-room gate exists to keep out: it carries the key, its peers'
# census returns true, and it runs vanilla while they repair.
#
# Two of W25's clauses move at once here and either alone would be enough: the
# write is not monotone, and it is outside MarkAttached. It is spelled
# "_attached=RequiredAttachments;" with no spaces, as the finding spelled it.
#
# W23 is the inert twin and must stay GREEN: the planted write shares its line
# with the shortfall flag's own write, so the flag still occurs on exactly two
# code lines, is still written exactly once, still writes true, still sits after
# the staging write, and no _withdrawn is assigned. That is what says the two
# cases measure different things rather than one thing twice.
$wireReachDecline = New-WireRoot 'reachdecline' 'plugin/ProximityVictimPatches.cs' `
    'internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)' `
    '                    _stageFailedPermanently = true;' `
    '                    _stageFailedPermanently = true; _attached=RequiredAttachments;' ''
$runWireReachDecline = Invoke-Suite 'wire-reachdecline' $seam $wireReachDecline
if (-not (Assert-Mutation 'attachment count written on the declining branch' $runWireReachDecline 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'decline-branch attachment write, W23 inert twin' $runWireReachDecline 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- the same two-way write, SPLIT BY A COMMENT ----------
# The round-6 case stopped being bound to a spelling of the OPERATOR and stayed
# bound to a spelling of the WHITESPACE. ClassifyWrite reached the operator with
# SkipWs, which skips space, tab, CR and LF and not a comment, so this line
# named the field in a fully recognised spelling, matched no operator, and came
# back as "not a write": the count was two-way again and W25 reported exactly
# one monotone write inside MarkAttached and passed. The classifier now reads a
# comment-blanked copy, which is why this reddens; it is the same defect class
# as the spelling bound, reached by a different typing (#342/#431).
$wireCommentWrite = New-WireRoot 'commentwrite' 'plugin/ProximityVictimPatches.cs' `
    'internal static void MarkAttached(string which)' `
    '            _attached++;' `
    '            _attached++; _attached /* reset on re-attach */ = 0;' ''
$runWireCommentWrite = Invoke-Suite 'wire-commentwrite' $seam $wireCommentWrite
if (-not (Assert-Mutation 'comment-split attachment write' $runWireCommentWrite 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'comment-split write, W23 inert twin' $runWireCommentWrite 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- re-enable the mod from a file the old scan never opened ----------
# The disabled flag's one-way premise was scanned over plugin/Plugin.cs alone,
# and the residual that disclosed the narrow surface mitigated it with "the
# fields are private, so today no unlisted file can write them". True of the two
# counters; FALSE of this one. Plugin.modDisabled is `internal static` and six
# other shipped files already reference it, so any file in the assembly may
# write it. A compat re-enable path spelled here makes the flag two-way: a seat
# that reached ModDisabled can return to Capable after a staging attempt has
# already declined - the state "the guard's terms are settled before the first
# staging attempt" forbids, and the state the whole agreement rests on.
$wireDisabledElsewhere = New-WireRoot 'disabledelsewhere' 'plugin/PerfPatches.cs' `
    'public static void Hit(string patch)' `
    '                _counts.TryGetValue(patch, out long c); _counts[patch] = c + 1;' `
    '                _counts.TryGetValue(patch, out long c); _counts[patch] = c + 1; Plugin.modDisabled = false;' ''
$runWireDisabledElsewhere = Invoke-Suite 'wire-disabledelsewhere' $seam $wireDisabledElsewhere
if (-not (Assert-Mutation 'disabled flag written outside its declaring file' $runWireDisabledElsewhere 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'off-file disabled write, W23 inert twin' $runWireDisabledElsewhere 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- attach the patches a SECOND time, from a second patch site ----------
# The load-bearing limb of the permanence argument, and the one the privateness
# mitigation never touched: nothing restricts a Harmony patch site to one file.
# The two clauses that bound it counted CreateClassProcessor and PatchAll in
# plugin/Plugin.cs while their own failure text said "the assembly". A second
# site driven from a deferred init runs the three cleanup callbacks again AFTER
# ApiClient.Initialize, so a seat whose first pass left the count short declines,
# prints the shortfall line whose closing clause says it stays on vanilla for the
# session, and then reaches three on the late pass - advertising cr_prox1 while
# its peers repair and it runs vanilla. Every clause stayed green on that.
$wireSecondPatchSite = New-WireRoot 'secondpatchsite' 'plugin/PerfPatches.cs' `
    'public static void Hit(string patch)' `
    '                _lifetime.TryGetValue(patch, out long l); _lifetime[patch] = l + 1;' `
    '                _lifetime.TryGetValue(patch, out long l); _lifetime[patch] = l + 1; new Harmony("scr.perf.late").PatchAll();' ''
$runWireSecondPatchSite = Invoke-Suite 'wire-secondpatchsite' $seam $wireSecondPatchSite
if (-not (Assert-Mutation 'a second Harmony patch site in the assembly' $runWireSecondPatchSite 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'second patch site, W23 inert twin' $runWireSecondPatchSite 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- rename the cleanup tag the reachability mutant keys on ----------
# THE MUTANT'S OWN REACHABILITY, MADE A CHECKED PROPERTY. wire-reach is only a
# real test because "StunPlayer.Go" is the literal that cleanup actually passes;
# rename the tag and that mutant matches no call, makes the source two-way and
# leaves the program one-way - the round-5 defect exactly - while W25 goes on
# reddening for the write count, so the RESULT row still prints OK and nothing
# says the reachability claim has reverted. W25 now pins all three literals, so
# the rename itself reddens and the staleness is visible the day it happens.
$wireCleanupTag = New-WireRoot 'cleanuptag' 'plugin/ProximityVictimPatches.cs' `
    'internal static class StunPlayerFreshVictimPatch' `
    '            if (exception == null) ProximityVictimGate.MarkAttached("StunPlayer.Go");' `
    '            if (exception == null) ProximityVictimGate.MarkAttached("StunPlayer.Go (perf)");' ''
$runWireCleanupTag = Invoke-Suite 'wire-cleanuptag' $seam $wireCleanupTag
if (-not (Assert-Mutation 'renamed cleanup tag the reach mutant keys on' $runWireCleanupTag 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'renamed cleanup tag, W23 inert twin' $runWireCleanupTag 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- author a THIRD ranking in the file whose two are inherited ----------
# THE PROVENANCE, CORRECTED. Round 3's acceptance bar was "zero authored
# distance or sqrMagnitude comparisons in the seam and the patches" - the
# round-5 brief, the round-5 report and every place the notes carry the clause
# say the seam and the patches, or "either file", and none names a third file.
# N1's surface IS that bar. What this row answers is a LATER observation: FfaMode
# ranks with Vector2.Distance in its targeting selector and its ring sampler,
# both pre-dating this branch, both INHERITED through the one vanilla call the
# seam makes, and no case in the suite read that file - so "inherited, not
# authored" was a claim with nothing behind it. N1b pins the count so inherited
# stays a claim about something; without it a comparison added here is a ranking
# the branch did not inherit and nothing sees it.
$wireFfaRank = New-WireRoot 'ffarank' 'plugin/FfaMode.cs' `
    'public static Player NearestOpponent(PlayerManager pm, Vector3 position,' `
    '                float d = Vector2.Distance(position, p.transform.position);' `
    '                float d = Vector2.Distance(position, p.transform.position);
                if (Vector2.Distance(position, pm.transform.position) < d) continue;' ''
$runWireFfaRank = Invoke-Suite 'wire-ffarank' $seam $wireFfaRank
if (-not (Assert-Mutation 'a third authored ranking in FfaMode' $runWireFfaRank 'N1b' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'third FFA ranking, N1 inert twin' $runWireFfaRank 'N1b' 'N1')) { $overall = 1 }
Say ''

# ---------- MOVE A STAGING MERGE ABOVE THE INITIALISATION GATE ----------
# THE FIRST OF THE TWO CONDITIONS W25's downstream relation has to reject. The
# clause it replaces counted three StageInto calls and its failure text said
# "and all three are downstream of ApiClient.Initialize" - a count that is true
# of any ORDER, so the check could not reject the change its own message
# forbade. This is that change, made honestly as a MOVE and not a duplication:
# the FFA queue poll is lifted out of its place below "if (!initialized)
# return;" and planted above it, so it can run on a tick before DoInitialize has
# called ApiClient.Initialize. A seat could then stage cr_prox1 while its
# patches were still attaching - the state the whole permanence argument
# forbids. Every clause of the round-6 W25 stayed green on this.
#
# W23 is the inert twin and must stay GREEN: nothing in the patches file moves.
$wireStageAbove = New-WireRootEdits 'stageabove' 'plugin/Plugin.cs' @(
    @('public class CompetitiveRoundsBehaviour : MonoBehaviour',
      '            if (!initialized) return;',
      '            if (ApiClient.IsFfaQueuePolling) { try { ApiClient.UpdateFfaQueuePoll(false); } catch { } }
            if (!initialized) return;'),
    @('public class CompetitiveRoundsBehaviour : MonoBehaviour',
      '                try { ApiClient.UpdateFfaQueuePoll(false); }',
      '                try { /* moved above the gate */ }')
)
$runWireStageAbove = Invoke-Suite 'wire-stageabove' $seam $wireStageAbove
if (-not (Assert-Mutation 'a staging merge moved above the initialisation gate' $runWireStageAbove 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'merge above the gate, W23 inert twin' $runWireStageAbove 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- REACH A STAGING MERGE FROM SOMETHING THAT IS NOT THE INIT PATH ----
# THE SECOND CONDITION. PerfPatches.Hit is a Harmony postfix driven by patched
# game code, not by the persistent tick, so a call to the FFA queue poll planted
# here is a route into the pre-join merge that the initialisation gate does not
# stand in front of at all. The round-6 W25 counted the same three StageInto
# calls and stayed green, because the number of merges does not change when a
# new way of reaching them appears. W25 now closes the caller FILE set - only
# ApiClient.cs, NativeUI.cs and Plugin.cs may reach a staging entry point, with
# the per-file map printed - so this reddens and names the file it found.
#
# W23 is the inert twin and must stay GREEN.
$wireStageCaller = New-WireRoot 'stagecaller' 'plugin/PerfPatches.cs' `
    'public static void Hit(string patch)' `
    '                if (_firstFireLogged.Add(patch))' `
    '                ApiClient.UpdateFfaQueuePoll(true);
                if (_firstFireLogged.Add(patch))' ''
$runWireStageCaller = Invoke-Suite 'wire-stagecaller' $seam $wireStageCaller
if (-not (Assert-Mutation 'a staging entry point reached from outside the init path' $runWireStageCaller 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'off-path staging caller, W23 inert twin' $runWireStageCaller 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- write both guard terms by DECONSTRUCTION, on the decline branch ----
# The classifier removed the SPELLING bound and then the WHITESPACE bound, and
# both times the remaining hole was a form that puts no operator next to the
# name. A deconstruction target is followed by ',' or ')', so
# "(_attached, _withdrawn) = (0, true);" named both monitored fields in full,
# matched no operator, and was filed as a READ by the very pass whose case is
# called "every write in ANY spelling". The csproj sets LangVersion `latest`, so
# the form compiles in this project today.
#
# Planted on the DECLINING branch, which is where it would do the damage: the
# count falls to zero after a staging attempt has declined and the withdrawal
# latch is set from the member whose one property is that it sets no latch. Both
# W25 and W23 must see it - that is correct, not a blunt mutant - so W22, which
# reads the census member and nothing here, is the inert twin.
$wireDeconstructWrite = New-WireRoot 'deconstructwrite' 'plugin/ProximityVictimPatches.cs' `
    'internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)' `
    '                    _stageFailedPermanently = true;' `
    '                    _stageFailedPermanently = true; (_attached, _withdrawn) = (0, true);' ''
$runWireDeconstructWrite = Invoke-Suite 'wire-deconstructwrite' $seam $wireDeconstructWrite
if (-not (Assert-Mutation 'deconstruction write to the attachment count' $runWireDeconstructWrite 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'deconstruction write to the withdrawal latch' $runWireDeconstructWrite 'W23' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'deconstruction write, W22 inert twin' $runWireDeconstructWrite 'W25' 'W22')) { $overall = 1 }
Say ''

# ---------- leave a staging call alive ONLY inside a block comment ----------
# THREE VIEWS OF ONE SOURCE, and this is the line where they disagreed. The
# member anchors counted raw text and CallsTo skipped only a hit on a whole-line
# "//", so a call wrapped in /* ... */ was dead to the compiler and live to both
# of them: the FFA pre-join merge would stage nothing, W7c would report its
# anchor present and W25 would report three staging sites. Every counter of code
# now reads the one comment-blanked view, so both reddens.
#
# W23 is the inert twin and must stay GREEN - the patches file does not move.
$wireBlockCommentCall = New-WireRoot 'blockcommentcall' 'plugin/ApiClient.cs' `
    'public static void UpdateFfaQueuePoll(bool force)' `
    '                            ProximityVictimGate.StageInto(prejoin);' `
    '                            /* ProximityVictimGate.StageInto(prejoin); */' ''
$runWireBlockCommentCall = Invoke-Suite 'wire-blockcommentcall' $seam $wireBlockCommentCall
if (-not (Assert-Mutation 'a staging call left only inside a block comment' $runWireBlockCommentCall 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'block-commented staging call, the member anchor sees it too' $runWireBlockCommentCall 'W7c' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'block-commented staging call, W23 inert twin' $runWireBlockCommentCall 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- stop disclosing the untested lifecycle step in the seam ----------
# The reachability argument has one link no test holds, and until this round only
# the patches file said so; the seam stated the ordering and then said W25 pinned
# the premises. A shipped comment that presents an untested step as pinned tells
# the next reader to stop looking for the thing that would falsify it. Both files
# now carry the same disclosure in the same words; this removes it from one of
# them.
#
# W25 is the inert twin and must stay GREEN: it makes no claim about this
# sentence, which is the whole point of the sentence.
$wireLifecycleDrop = New-WireRoot 'lifecycledrop' 'plugin/ProximityVictimSeam.cs' `
    'internal static class ProximityVictim' `
    '        /// Awake runs before the first tick that can reach DoInitialize.' `
    '        /// (mutant) the lifecycle step is no longer disclosed here.' ''
$runWireLifecycleDrop = Invoke-Suite 'wire-lifecycledrop' $seam $wireLifecycleDrop
if (-not (Assert-Mutation 'the untested lifecycle step dropped from one shipped file' $runWireLifecycleDrop 'W26' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'lifecycle disclosure dropped, W25 inert twin' $runWireLifecycleDrop 'W26' 'W25')) { $overall = 1 }
Say ''

# ============ round-7 COLD LENS: the six rows that close its findings ========

# ---------- move a staging call OUT of the member the route walk pins --------
# THE ROUTE WALK PLACED THREE OF TEN CALL SITES. R3's per-file loop skipped every
# file that was not Plugin.cs before it looked at a position, and R4 closed only
# the FILE set - so the two NativeUI calls and the five ApiClient ones were
# counted, printed in the NOTE, and never placed. This moves the FFA queue poll
# out of the tab refresher R5 pins to the gated tick and into NativeUI.Open,
# which menu construction reaches and the persistent tick does not. Nothing else
# moves: three StageInto merges, the gate flag, the caller FILE set and R5's
# three link counts are all exactly as they were, which is why the round-7 W25
# stayed green on it. R6 places the call by its enclosing member and reddens.
#
# W23 is the inert twin and must stay GREEN: the patches file does not move.
$wireStageMember = New-WireRootEdits 'stagemember' 'plugin/NativeUI.cs' @(
    @('private static void MaybeRefreshFfaTab()',
      '            ApiClient.UpdateFfaQueuePoll(false);   // internally 2s-throttled; no-op when not polling',
      '            // (mutant) the staging call has left this member'),
    @('public static void Open()',
      '            if(!UIFactory.Ready){UIFactory.InitTypes();UIFactory.InitFont();}if(!UIFactory.Ready)return;',
      '            if(!UIFactory.Ready){UIFactory.InitTypes();UIFactory.InitFont();}if(!UIFactory.Ready)return;
            ApiClient.UpdateFfaQueuePoll(false);')
)
$runWireStageMember = Invoke-Suite 'wire-stagemember' $seam $wireStageMember
if (-not (Assert-Mutation 'a staging call moved out of the member the route pins' $runWireStageMember 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'staging call moved within a permitted file, W23 inert twin' $runWireStageMember 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- reach a staging entry point from ApiClient.Initialize ITSELF ------
# THE SAME GAP, IN THE OTHER UNPLACED FILE. wire-stagecaller planted its call in
# PerfPatches.cs, a FOURTH file, so it reddened on the file-set clause and said
# nothing about a caller inside a file already permitted. This plants one in the
# initialisation member the whole relation is measured against: a staging entry
# point reached from ApiClient.Initialize runs BEFORE initialisation has
# finished, which is the exact state the permanence argument forbids, and under
# the round-7 W25 it changed no count, no file and no link.
#
# W23 is the inert twin and must stay GREEN.
$wireStageApiMember = New-WireRoot 'stageapimember' 'plugin/ApiClient.cs' `
    'public static void Initialize(string url)' `
    '            baseUrl = url.TrimEnd(''/'');' `
    '            baseUrl = url.TrimEnd(''/'');
            UpdateFfaQueuePoll(force: true);' ''
$runWireStageApiMember = Invoke-Suite 'wire-stageapimember' $seam $wireStageApiMember
if (-not (Assert-Mutation 'a staging entry point reached from the initialisation member' $runWireStageApiMember 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'staging call inside Initialize, W23 inert twin' $runWireStageApiMember 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- lift a merge OUT of the response callback it runs in -------------
# "AFTER baseUrl" WAS NOT THE PROPERTY. The round-7 clause asked only that a
# merge sit at a larger offset than its member's baseUrl request, and a
# statement written below the whole StartCoroutine call satisfies that while
# running on ENTRY - on whatever tick reached the member, with no reply
# involved at all. This moves the 1v2 merge from inside the callback to just
# after it, inside the same member: R1's ordering clause still passes and R7
# reddens.
#
# W23 is the inert twin and must stay GREEN.
$wireStageUnbound = New-WireRootEdits 'stageunbound' 'plugin/ApiClient.cs' @(
    @('public static void UpdateOvtQueuePoll(bool force)',
      '                            ProximityVictimGate.StageInto(prejoin);',
      '                            // (mutant) the merge has left the response callback'),
    @('public static void UpdateOvtQueuePoll(bool force)',
      '            }));',
      '            }));
            ProximityVictimGate.StageInto(new ExitGames.Client.Photon.Hashtable());')
)
$runWireStageUnbound = Invoke-Suite 'wire-stageunbound' $seam $wireStageUnbound
if (-not (Assert-Mutation 'a merge lifted out of its response callback' $runWireStageUnbound 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'merge outside the callback, W23 inert twin' $runWireStageUnbound 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- give the request prefix a writer outside its closed set ----------
# R7 ties a merge to a REPLY; R8 is what makes a reply downstream of
# initialisation, because the prefix that reply came back from starts empty and
# is written by ApiClient.Initialize and the TLS fallback that runs from it.
# A third writer, in a member the tab refresher reaches on first open, is a
# prefix that can be set without initialisation ever having run - and nothing in
# the round-7 harness read that field at all.
#
# W23 is the inert twin and must stay GREEN.
$wireUrlWriter = New-WireRoot 'urlwriter' 'plugin/ApiClient.cs' `
    'public static void FfaProbeServerState()' `
    '            IsFfaQueuePolling = true;' `
    '            baseUrl = "http://127.0.0.1:1";
            IsFfaQueuePolling = true;' ''
$runWireUrlWriter = Invoke-Suite 'wire-urlwriter' $seam $wireUrlWriter
if (-not (Assert-Mutation 'a request-prefix writer outside the closed set' $runWireUrlWriter 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'third prefix writer, W23 inert twin' $runWireUrlWriter 'W25' 'W23')) { $overall = 1 }
Say ''

# ---------- write the gate flag from a file that declares its own ------------
# THE SURFACE THAT NARROWED WITH NO LINE IN THE LOG. ScanField used to DROP any
# file declaring its own field of the scanned name. plugin/CustomCosmetics.cs
# declares `private static bool initialized;`, so it left the gate flag's scan
# with no output anywhere - the attachment count printed its exclusion, the
# disabled flag made a second declarer fatal, and this one said nothing while
# its failure text named all 91 shipped files. This is the change that hole
# admitted: the flag is given assembly visibility, a second file declares one of
# its own, and writes the HOME flag through the qualified spelling that names it
# outright. Narrowing reads that write; dropping never saw it.
#
# W22 is the inert twin and must stay GREEN: it reads the census member.
$wireQualifiedGateFlag = New-WireRootMulti 'qualifiedgateflag' @(
    @('plugin/Plugin.cs',
      'public class CompetitiveRoundsBehaviour : MonoBehaviour',
      '        private bool initialized = false;',
      '        internal static bool initialized = false;'),
    @('plugin/PerfPatches.cs',
      'internal static class PerfGate',
      '        private static readonly HashSet<string> _firstFireLogged = new HashSet<string>();',
      '        private static readonly HashSet<string> _firstFireLogged = new HashSet<string>();
        private static bool initialized;'),
    @('plugin/PerfPatches.cs',
      'public static void Hit(string patch)',
      '                if (_firstFireLogged.Add(patch))',
      '                Plugin.initialized = true;
                if (_firstFireLogged.Add(patch))')
)
$runWireQualifiedGateFlag = Invoke-Suite 'wire-qualifiedgateflag' $seam $wireQualifiedGateFlag
if (-not (Assert-Mutation 'the gate flag written from a file that declares its own' $runWireQualifiedGateFlag 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'qualified gate-flag write, W22 inert twin' $runWireQualifiedGateFlag 'W25' 'W22')) { $overall = 1 }
Say ''

# ---------- deconstruct into the guard terms through their OWNER -------------
# wire-deconstructwrite plants the BARE form; this plants the QUALIFIED one.
# "(ProximityVictimGate._attached, ProximityVictimGate._withdrawn) = (0, true);"
# is legal from inside the class that owns both, and the recogniser read the
# character before the BARE name - found '.', and filed both as READS. Every
# other form this classifier knows is recognised qualified already, because an
# operator FOLLOWS the name; the deconstruction form is the one that reads
# backwards, so it was the one form where the qualifier decided the answer.
# Planted on the DECLINING branch, where it does the damage: the count falls to
# zero after a staging attempt has declined, and the withdrawal latch is set by
# the member whose one property is that it sets no latch.
#
# W22 is the inert twin and must stay GREEN.
$wireQualifiedDeconstruct = New-WireRoot 'qualifieddeconstruct' 'plugin/ProximityVictimPatches.cs' `
    'internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)' `
    '                    _stageFailedPermanently = true;' `
    '                    _stageFailedPermanently = true; (ProximityVictimGate._attached, ProximityVictimGate._withdrawn) = (0, true);' ''
$runWireQualifiedDeconstruct = Invoke-Suite 'wire-qualifieddeconstruct' $seam $wireQualifiedDeconstruct
if (-not (Assert-Mutation 'qualified deconstruction write to the attachment count' $runWireQualifiedDeconstruct 'W25' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'qualified deconstruction write to the withdrawal latch' $runWireQualifiedDeconstruct 'W23' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'qualified deconstruction write, W22 inert twin' $runWireQualifiedDeconstruct 'W25' 'W22')) { $overall = 1 }
Say ''

# ---------- change ONE finding body's severity and leave the census line ------
# The round-6 log's header said "two MEDIUM, five LOW" while its own bodies read
# three MEDIUM and four LOW. Every other number in that header was counted from
# the run; that one was typed. H1 derives the census from the SEVERITY markers on
# the bodies and fails when the declared line disagrees, so this mutation MOVES
# the printed census - the run's own NOTE line shows the moved value - and the
# declared line can no longer be the thing a reader has to trust.
#
# W25 is the inert twin and must stay GREEN: it reads no findings file.
$wireSeverityCensus = New-WireRoot 'severitycensus' 'tools/tests/bug389-seam/round-findings.md' `
    '### N6 - the BUILD blind-control lead said twelve rows over a body of fourteen' `
    'SEVERITY: LOW' `
    'SEVERITY: MEDIUM' `
    '### N7 '
$runWireSeverityCensus = Invoke-Suite 'wire-severitycensus' $seam $wireSeverityCensus
if (-not (Assert-Mutation 'a finding body severity changed under the declared census' $runWireSeverityCensus 'H1' 'W1')) { $overall = 1 }
if (-not (Assert-Mutation 'moved severity census, W25 inert twin' $runWireSeverityCensus 'H1' 'W25')) { $overall = 1 }
Say ''

# ---------- put the deleted compat claim back in the HARNESS'S own text ----------
# The round-4 pass deleted "the one transition that exists today" from the
# patches file and "A pre-join stage may already have advertised it" from the
# compat site, and left the same claim standing in this suite's own comment -
# outside every file W17 read. So the document certifying the deletion was still
# making the claim, and a tester reading it would still wait for a line a plain
# compat disable cannot produce. W17's surface now includes this file; this is
# what proves that half can fail.
#
# THE ANCHOR IS DELIBERATELY A LINE THAT EXISTS IN BOTH THE CURRENT HARNESS AND
# THE PREVIOUS TIP'S. The blindness run re-executes these mutants against the
# harness as it stood at the previous tip, and an anchor that only this round's
# file carries would abort that whole run at this line instead of producing the
# FAILED row it exists to produce (#342: a control that cannot be executed
# reports nothing about anything).
$wireCompatHarness = New-WireRoot 'compatharness' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '        // W16 - the withdrawal can only withdraw. The capable value reaches a peer' `
    '        // W16 - the withdrawal can only withdraw, and the compat site is the one transition that exists today. The capable value reaches a peer' ''
$runWireCompatHarness = Invoke-Suite 'wire-compatharness' $seam $wireCompatHarness
if (-not (Assert-Mutation 'deleted-compat-claim-in-the-harness wiring' $runWireCompatHarness 'W17' 'W1')) { $overall = 1 }
Say ''

# Read the property write as if failure could only arrive as an exception.
# Player.SetCustomProperties returns a bool and a refused op comes back false
# having sent nothing, cached nothing and thrown nothing. Ignoring it clears
# _advertised and latches _withdrawn on a withdrawal that never left the
# process: the per-tick driver and StageInto then refuse for the rest of the
# session while cr_prox1 stays set on every peer.
$wireBlindWrite = New-WireRoot 'blindwrite' 'plugin/ProximityVictimPatches.cs' `
    'internal static void RepublishCapability()' `
    '                if (!sent)' `
    '                if (false)' ''
$runWireBlindWrite = Invoke-Suite 'wire-blindwrite' $seam $wireBlindWrite
if (-not (Assert-Mutation 'unchecked-property-write wiring' $runWireBlindWrite 'W20' 'W1')) { $overall = 1 }
Say ''

# Put the refuted monotonicity paragraph back. "The attachment count only ever
# increments, so the local answer moves from Capable to not-Capable and never
# back" is refuted by its own second premise, and G6 executes the refutation.
# The paragraph nominated itself as the place reversibility has to be answered,
# so it is the one site a later reader would check.
$wireMonotone = New-WireRoot 'monotone' 'plugin/ProximityVictimSeam.cs' `
    'internal static class ProximityVictim' `
    '        /// THE LOCAL ANSWER IS NOT MONOTONIC, AND THIS FUNCTION DOES NOT REST ON' `
    '        /// increments, so the local answer moves from Capable to not-Capable and' ''
$runWireMonotone = Invoke-Suite 'wire-monotone' $seam $wireMonotone
if (-not (Assert-Mutation 'monotonicity-claim wiring' $runWireMonotone 'W21' 'W1')) { $overall = 1 }
Say ''

# Put the refuted key argument back. The claim that a round-2 seat and a round-3
# seat resolve the same player is false - round 2 ranked with a selector of its
# own and deferred on an Any-target ring - and it was the stated reason for not
# rotating cr_prox1. K3 is the case that holds the seam to the fact that
# replaced it; without a mutant it would be a restatement of the comment.
$wireKeyClaim = New-WireRoot 'keyclaim' 'plugin/ProximityVictimSeam.cs' `
    'internal static class ProximityVictim' `
    '        /// released build advertises it at all. The key is absent from the base' `
    '        /// comparing like with like. The key is absent from the base' ''
$runWireKeyClaim = Invoke-Suite 'wire-keyclaim' $seam $wireKeyClaim
if (-not (Assert-Mutation 'key-non-rotation-claim wiring' $runWireKeyClaim 'K3' 'W1')) { $overall = 1 }
Say ''

# Put the unscoped composition bound back. "Under ANY composition the worst a
# foreign fold could do is fail to run them" is true of the two methods this
# repair patches alone and false of StunPlayer.Go, which also carries the perf
# null guard. W13 is the case that holds the prose to what P5 measured.
$wireBoundClaim = New-WireRoot 'boundclaim' 'plugin/ProximityVictimSeam.cs' `
    'internal static class ProximityVictim' `
    '        /// StunPlayer.Go is NOT covered by that bound, and the wording this' `
    '        /// under ANY composition nothing here needs scoping, and the wording this' ''
$runWireBoundClaim = Invoke-Suite 'wire-boundclaim' $seam $wireBoundClaim
if (-not (Assert-Mutation 'composition-bound-claim wiring' $runWireBoundClaim 'W13' 'W1')) { $overall = 1 }
Say ''

# =====================  ROUND 8  =====================
# Every mutant below closes one numbered round-7 finding. Each has an anchor
# resolved INSIDE the member that holds the behaviour the finding names, a test
# that must redden, and a SEPARATE inert root of comparable size in the same file
# that must leave that test green.
#
# ANCHORS IN Program.cs ARE DELIBERATELY LINES THAT EXIST AT THE PREVIOUS TIP
# TOO. The blindness run re-executes these mutants with the previous round's
# harness swapped into the tree, and that file is also the copy the wiring roots
# carry - so an anchor only this round's file has would abort the whole run at
# this line instead of producing the FAILED row it exists to produce.
$nl = [string][char]10
# AND EVERY ELEMENT BUILT WITH $nl IS PARENTHESISED. PowerShell's comma binds
# TIGHTER than binary +, so @('a', 'b' + $nl + 'c', 'd') is not a three-element
# array: it reads as ('a','b') + ($nl) + ('c','d'), six elements, and the edit
# arrives with every argument shifted. It cost a run to find, and it found it by
# ABORTING rather than by reddening - the anchor named in the refusal was the
# right one and the string beside it was a bare newline.

# ---------- N1: a second call to an allowed writer, in another member ----------
# R8 closed who may WRITE the request prefix and nothing closed who may CALL the
# writers. W25c requires only that the existing ApiClient.Initialize call SIT
# inside DoInitialize, so initialising the client from Start() - an ordinary
# startup refactor - left every clause green. R9 resolves every call site of each
# allowed writer to its enclosing member and compares the set with a closed one.
#
# W1 is the inert twin and must stay GREEN.
$wireCallerExtra = New-WireRoot 'callerextra' 'plugin/Plugin.cs' `
    'private void Start()' `
    '            CacheTmpReferences();' `
    '            CacheTmpReferences(); ApiClient.Initialize(Plugin.ApiBaseUrl.Value);' ''
$runWireCallerExtra = Invoke-Suite 'wire-callerextra' $seam $wireCallerExtra
if (-not (Assert-Mutation 'a second call to an allowed writer, from an unbound member' $runWireCallerExtra 'W25' 'W1')) { $overall = 1 }
Say ''

# ---------- N1: the permitted FFA wrapper called from an unbound member --------
# FfaProbeServerState is a permitted MEMBER of the staging entry-point set and is
# not itself an entry point, so R6 never placed its callers. Moved into the 1v2
# tab refresher it changes no count R6 takes.
$wireProbeCaller = New-WireRoot 'probecaller' 'plugin/NativeUI.cs' `
    'private static void MaybeRefreshOvtTab()' `
    '            ApiClient.UpdateOvtQueuePoll(false);   // safe no-op when not polling' `
    '            ApiClient.UpdateOvtQueuePoll(false); ApiClient.FfaProbeServerState();   // safe no-op when not polling' ''
$runWireProbeCaller = Invoke-Suite 'wire-probecaller' $seam $wireProbeCaller
if (-not (Assert-Mutation 'the permitted FFA wrapper called from an unbound member' $runWireProbeCaller 'W25' 'W1')) { $overall = 1 }
Say ''

# ---------- N1: the inert twin - same file, same size, no call site ------------
$wireCallerInert = New-WireRoot 'callerinert' 'plugin/Plugin.cs' `
    'private void Start()' `
    '            // Cache the TMP component and text property for text enforcement' `
    '            // Cache the TMP component and the text property for enforcement' ''
$runWireCallerInert = Invoke-Suite 'wire-callerinert' $seam $wireCallerInert
if (-not (Assert-Inert 'the permitted-caller set, inert edit' $runWireCallerInert @('W25', 'W1'))) { $overall = 1 }
Say ''

# ---------- N2: a QUALIFIED pre-decrement and a qualified out write ------------
# ClassifyWrite's backward half read the character immediately before the BARE
# name, found the '.' of a qualifier and filed the occurrence as a READ - so the
# attachment count could be driven below the required three, and passed by
# reference, by a pass whose case is called "every write in ANY spelling".
# Planted on the DECLINING branch, where it does the damage. Both backward forms
# are in the one edit because one line fixed them both.
#
# W1 is the inert twin and must stay GREEN.
$wireQualifiedPrefix = New-WireRoot 'qualifiedprefix' 'plugin/ProximityVictimPatches.cs' `
    'internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)' `
    '                    _stageFailedPermanently = true;' `
    '                    _stageFailedPermanently = true; --ProximityVictimGate._attached; int.TryParse("0", out ProximityVictimGate._attached);' ''
$runWireQualifiedPrefix = Invoke-Suite 'wire-qualifiedprefix' $seam $wireQualifiedPrefix
if (-not (Assert-Mutation 'qualified pre-decrement and out write to the attachment count' $runWireQualifiedPrefix 'W25' 'W1')) { $overall = 1 }
Say ''

$wireQualifiedPrefixInert = New-WireRoot 'qualifiedprefixinert' 'plugin/ProximityVictimPatches.cs' `
    'internal static void StageInto(ExitGames.Client.Photon.Hashtable prejoin)' `
    '                    // declining, and printing it would name a cause that has been' `
    '                    // declining, and printing it would name a cause that was' ''
$runWireQualifiedPrefixInert = Invoke-Suite 'wire-qualifiedprefixinert' $seam $wireQualifiedPrefixInert
if (-not (Assert-Inert 'the qualified backward classifier, inert edit' $runWireQualifiedPrefixInert @('W25', 'W23', 'W1'))) { $overall = 1 }
Say ''

# ---------- N3: the TLS fallback rewritten to ??= ------------------------------
# The request prefix is declared with the EMPTY string, which is not null, so
# `baseUrl ??= ...` reads as a writer and leaves the previous value standing.
# ClassifyWrite did not know the operator at all, so the write was invisible;
# R8 now also requires every write to that field to be a form that retargets.
$wireNullCoalesceAssign = New-WireRoot 'nullcoalesceassign' 'plugin/ApiClient.cs' `
    'private static IEnumerator ProbeEndpointThenStart()' `
    '                baseUrl = Plugin.LegacyApiUrl.TrimEnd(''/'');' `
    '                baseUrl ??= Plugin.LegacyApiUrl.TrimEnd(''/'');' ''
$runWireNullCoalesceAssign = Invoke-Suite 'wire-nullcoalesceassign' $seam $wireNullCoalesceAssign
if (-not (Assert-Mutation 'a null-coalescing write to the request prefix' $runWireNullCoalesceAssign 'W25' 'W1')) { $overall = 1 }
Say ''

$wireNullCoalesceInert = New-WireRoot 'nullcoalesceinert' 'plugin/ApiClient.cs' `
    'private static IEnumerator ProbeEndpointThenStart()' `
    '                UsingLegacyFallback = true;' `
    '                UsingLegacyFallback = true;   // session only' ''
$runWireNullCoalesceInert = Invoke-Suite 'wire-nullcoalesceinert' $seam $wireNullCoalesceInert
if (-not (Assert-Inert 'the null-coalescing classifier, inert edit' $runWireNullCoalesceInert @('W25', 'W1'))) { $overall = 1 }
Say ''

# ---------- N4: a finding body with no SEVERITY marker -------------------------
# The census was derived FROM the markers, so a body written without one moved
# neither the derived number nor the declared one: H1 stayed green and the body
# left the round unrecorded. H1 now counts the bodies by their own heading, off
# different evidence, and requires the two counts to agree.
#
# W25 is the inert twin and stays GREEN: it reads no findings file.
# THE CLOSURE TRAVELS WITH THE BODY. H4 holds the closure table's CLOSES: lines
# and the finding bodies to each other, so a body planted alone reddens H4 as
# well and this mutant would stop measuring H1 alone.
$wireBodyNoMarker = New-WireRootSpansMulti 'bodynomarker' `
    @(@('tools/tests/bug389-seam/round-findings.md',
        '### N9 - the untouched-selection streak was called both sixth and fifth',
        'SEVERITY: LOW',
        ('SEVERITY: LOW' + $nl + $nl + '### N11 - a body added without its severity marker' + $nl + $nl + 'This body carries no marker at all.'),
        '### N10 '),
      @('tools/tests/bug389-seam/R8-CLOSURES.md',
        'N10 LOW - THE PROMISED REPOSITORY COPY NEVER REACHED THE PIN.',
        'CLOSES: N10',
        'CLOSES: N10, N11',
        "THIS PASS'S COLD LENS, read on the build tip ed3b1e5."))
$runWireBodyNoMarker = Invoke-Suite 'wire-bodynomarker' $seam $wireBodyNoMarker
if (-not (Assert-Mutation 'a finding body written with no severity marker' $runWireBodyNoMarker 'H1' 'H4')) { $overall = 1 }
if (-not (Assert-Mutation 'an unmarked body, W25 inert twin' $runWireBodyNoMarker 'H1' 'W25')) { $overall = 1 }
Say ''

# The same body, WITH its marker and with the declared census moved to match:
# the case must pass, or it would be failing on "the file changed" rather than on
# the property it names.
#
# THE CENSUS LINE IS READ, NOT TYPED (round 9). This mutant carried the census
# spelled out - "20 findings: 1 HIGH, 4 MEDIUM, 15 LOW" - so the round that added
# five findings did not fail a case, it brought the whole driver down on a
# missing anchor. A number typed in a mutant is the same defect as a number typed
# in a report (#431): it is read out of the file it describes now, and the
# replacement is that line with one LOW added.
$censusFile = Join-Path $repo (Join-Path 'tools' (Join-Path 'tests' (Join-Path 'bug389-seam' 'round-findings.md')))
$censusLine = @([System.IO.File]::ReadAllText($censusFile).Split([char]10) |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_.StartsWith('CENSUS: ') })
if ($censusLine.Count -ne 1) {
    throw ('the findings file must declare the census exactly once; found ' + $censusLine.Count)
}
$censusNow = [string]$censusLine[0]
$censusMatch = [regex]::Match($censusNow, '^CENSUS: (\d+) findings: (\d+) HIGH, (\d+) MEDIUM, (\d+) LOW$')
if (-not $censusMatch.Success) {
    throw ('cannot read the declared census to build wire-bodymarked: ' + $censusNow)
}
$censusPlus = ('CENSUS: ' + ([int]$censusMatch.Groups[1].Value + 1) + ' findings: ' +
               $censusMatch.Groups[2].Value + ' HIGH, ' + $censusMatch.Groups[3].Value + ' MEDIUM, ' +
               ([int]$censusMatch.Groups[4].Value + 1) + ' LOW')
Say ('--- census read from the findings file: "' + $censusNow + '" -> "' + $censusPlus + '"')
$wireBodyMarked = New-WireRootSpansMulti 'bodymarked' `
    @(@('tools/tests/bug389-seam/round-findings.md',
        '### N9 - the untouched-selection streak was called both sixth and fifth',
        'SEVERITY: LOW',
        ('SEVERITY: LOW' + $nl + $nl + '### N11 - a body added with its severity marker' + $nl + $nl + 'SEVERITY: LOW' + $nl + $nl + 'This one is counted by both.'),
        '### N10 '),
      @('tools/tests/bug389-seam/round-findings.md',
        'CENSUS: ',
        $censusNow,
        $censusPlus,
        '## The selection-method streak'),
      @('tools/tests/bug389-seam/R8-CLOSURES.md',
        'N10 LOW - THE PROMISED REPOSITORY COPY NEVER REACHED THE PIN.',
        'CLOSES: N10',
        'CLOSES: N10, N11',
        "THIS PASS'S COLD LENS, read on the build tip ed3b1e5."))
$runWireBodyMarked = Invoke-Suite 'wire-bodymarked' $seam $wireBodyMarked
if (-not (Assert-Inert 'a finding body added with its marker' $runWireBodyMarked @('H1', 'H4', 'W25'))) { $overall = 1 }
Say ''

# ---------- N5: a counter that blanks raw text of its own ----------------------
# The deletion register named one cached CODE view read by every code counter,
# and four counters plus three call sites blanked raw text again. Nothing was
# wrong - blanking is deterministic and every caller held a .cs file - but the
# register entry was not true of the code, and an absence bound whose named
# replacement is not present is one a reader cannot use.
#
# W25 is the inert twin and stays GREEN.
# RE-SITED. This mutant used to land inside the counter whose NAME carried a
# view; that counter is retired (LENS 7), so a blanking site planted there could
# not exist at all. It lands beside a cached read instead - which is where a
# re-blank would really be written - and still puts a second blanking site in the
# file while the register names one cached view.
$wireUncachedView = New-WireRoot 'uncachedview' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '        string apiBlank = LoadBlanked(apiRel);' `
    '        string apiBlank = LoadBlanked(apiRel); string apiRaw = BlankComments(LoadSource(apiRel));' ''
$runWireUncachedView = Invoke-Suite 'wire-uncachedview' $seam $wireUncachedView
if (-not (Assert-Mutation 'a counter that blanks raw text of its own' $runWireUncachedView 'W27' 'W25')) { $overall = 1 }
Say ''

$wireViewInert = New-WireRoot 'viewinert' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '        // An earlier wording of this comment reached that corner by the other' `
    '        // An earlier version of this comment reached that corner by the other' ''
$runWireViewInert = Invoke-Suite 'wire-viewinert' $seam $wireViewInert
if (-not (Assert-Inert 'the single blanking site, inert edit' $runWireViewInert @('W27', 'W25'))) { $overall = 1 }
Say ''

# ---------- N6-N9: a derived artifact moved under a typed prose count ----------
# Four prose counts disagreed with the numbers their own artifacts derive. The
# closure is not four corrections but reading each number OUT of the thing it
# counts: H2 counts permittedMembers from the file's own text and requires both
# route sentences to carry that count.
# RESHAPED INTO A HARNESS MUTANT (round 9). This was a wiring mutant that added a
# ninth signature to the source-root COPY of Program.cs, which is what H2 used to
# read. H2 reads the running collection now, so a text-only edit moves nothing;
# the ninth member is added to the COMPILED harness, and it is added the way a
# maintainer really would - a signature extracted to a constant and named in the
# array - which is precisely the route the old spelling-bound count could not see.
$harnessNinthMember = New-HarnessMutant 'ninthmember' `
    @(@('private static int Main()',
        '        var permittedMembers = new Dictionary<string, string[]>(StringComparer.Ordinal);',
        ('        const string extractedSignature = "public static void FfaProbeAgain()";' + $nl +
         '        var permittedMembers = new Dictionary<string, string[]>(StringComparer.Ordinal);')),
      @('private static int Main()',
        '            "public static void FfaProbeServerState()",',
        ('            "public static void FfaProbeServerState()",' + $nl + '            extractedSignature,')))
$runHarnessNinthMember = Invoke-Suite 'harness-ninthmember' $seam $repo $harnessNinthMember
if (-not (Assert-Mutation 'a ninth permitted member reached through an extracted constant' $runHarnessNinthMember 'H2' 'W25')) { $overall = 1 }
Say ''

# The other direction of the same binding: a member the declared list still names
# is taken OUT of the array. W25 reddens here too - the staging call inside that
# member is no longer inside a placed one - so the control is W1, a case that
# reads a file neither edit touches.
$harnessMemberDropped = New-HarnessMutant 'memberdropped' `
    @(, @('private static int Main()',
          '            "public static void FfaKickFromLobby(string targetSteamId)"',
          ''))
$runHarnessMemberDropped = Invoke-Suite 'harness-memberdropped' $seam $repo $harnessMemberDropped
if (-not (Assert-Mutation 'a declared permitted member dropped from the array' $runHarnessMemberDropped 'H2' 'W1')) { $overall = 1 }
Say ''

# And the case where the COUNT cannot see it at all: one member renamed, so the
# collection still holds eight and only the both-ways binding to the declared
# list can tell. This is the control the count-only clause could never have had.
$harnessMemberSwapped = New-HarnessMutant 'memberswapped' `
    @(, @('private static int Main()',
          '            "public static void FfaKickFromLobby(string targetSteamId)"',
          '            "public static void FfaKickFromLobbyLater(string targetSteamId)"'))
$runHarnessMemberSwapped = Invoke-Suite 'harness-memberswapped' $seam $repo $harnessMemberSwapped
if (-not (Assert-Mutation 'a permitted member renamed under an unchanged count' $runHarnessMemberSwapped 'H2' 'W1')) { $overall = 1 }
Say ''

# The inert twin for all three: the DECLARED list respelled with different
# spacing. The keys are collapsed on both sides, so a respelling is not a
# finding - and a case that reddened on one would be measuring the typist.
$wireMemberSpacing = New-WireRootSpans 'memberspacing' 'tools/tests/bug389-seam/round-findings.md' `
    @(, @('## The permitted staging-entry members',
          'PERMITTED-MEMBER: plugin/ApiClient.cs :: public static void FfaProbeServerState()',
          'PERMITTED-MEMBER:  plugin/ApiClient.cs  ::  public static void   FfaProbeServerState()',
          '## The selection-method streak'))
$runWireMemberSpacing = Invoke-Suite 'wire-memberspacing' $seam $wireMemberSpacing
if (-not (Assert-Inert 'a declared permitted member respelled' $runWireMemberSpacing @('H2', 'W25'))) { $overall = 1 }
Say ''

# The other half of the same case: the streak list is the artifact, and the
# declared streak is counted from it rather than typed as an ordinal twice.
$wireStreakRow = New-WireRootSpans 'streakrow' 'tools/tests/bug389-seam/round-findings.md' `
    @(, @('## The selection-method streak',
          'STREAK-ROUND: R8',
          ('STREAK-ROUND: R8' + $nl + 'STREAK-ROUND: R9'),
          '### N1 - '))
$runWireStreakRow = Invoke-Suite 'wire-streakrow' $seam $wireStreakRow
if (-not (Assert-Mutation 'a round added to the streak list under a typed streak' $runWireStreakRow 'H2' 'W25')) { $overall = 1 }
Say ''

$wireProseInert = New-WireRoot 'proseinert' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '        // route - a seat whose patches complete after its first staging attempt -' `
    '        // path - a seat whose patches complete after its first staging attempt -' ''
$runWireProseInert = Invoke-Suite 'wire-proseinert' $seam $wireProseInert
if (-not (Assert-Inert 'the derived prose counts, inert edit' $runWireProseInert @('H2', 'W25'))) { $overall = 1 }
Say ''

# ---------- N10: the promised repository copy left unnamed ---------------------
# The round-7 closure table promised an identical copy inside the repository and
# named a path in the gitignored ai-collab tree, so a pin-only read found neither
# the file nor the directory. The canonical copy is tracked beside the harness
# now, and this is what holds it to naming each published copy.
$wireClosuresMissing = New-WireRootSpans 'closuresmissing' 'tools/tests/bug389-seam/R8-CLOSURES.md' `
    @(, @('WHY THIS FILE IS HERE AND NOT IN ai-collab.',
          'ai-collab/bugs/BUG389-R8-CLOSURES.md',
          'ai-collab/bugs/R7-CLOSURES.md',
          'Keys as in the round-8 brief.'))
$runWireClosuresMissing = Invoke-Suite 'wire-closuresmissing' $seam $wireClosuresMissing
if (-not (Assert-Mutation 'the promised repository copy left unnamed' $runWireClosuresMissing 'H3' 'W25')) { $overall = 1 }
Say ''

$wireClosuresInert = New-WireRootSpans 'closuresinert' 'tools/tests/bug389-seam/R8-CLOSURES.md' `
    @(, @('WHY THIS FILE IS HERE AND NOT IN ai-collab.',
          'tracked beside the harness it describes',
          'tracked next to the harness it describes',
          'Keys as in the round-8 brief.'))
$runWireClosuresInert = Invoke-Suite 'wire-closuresinert' $seam $wireClosuresInert
if (-not (Assert-Inert 'the closure table, inert edit' $runWireClosuresInert @('H3', 'W25'))) { $overall = 1 }
Say ''

# ================= THE COLD LENS ON THIS ROUND'S OWN BUILD TIP ================
# Four findings, read on 7786d7c. Three of them are checkable and have mutants
# here; the fourth - the two source views drifting apart in membership - fires
# on a sparse root, which prior-r2 already is, so it has no mutant of its own
# and says so rather than inventing one that cannot fail.

# ---------- lens 1: the permitted-member size read off part of the set --------
# DELETED WITH ITS CLAUSE (round 9). wire-prosemember planted an assignment
# outside the span H2 read its size from, which was the right mutant for a size
# read out of a bounded region of SOURCE TEXT. There is no span and no region
# any more: H2 enumerates the collection the harness built, so "inside the
# block" and "outside the block" have stopped being different states and a
# mutant naming them would be a mutant of a mechanism that no longer exists
# (#310). Its successors are harness-ninthmember, harness-memberdropped and
# harness-memberswapped above, which change what EXECUTES.

# ---------- lens 2: two spellings of the severity marker ----------------------
# H1 holds a body count and a marker count to each other, which is only evidence
# while the two are taken off DIFFERENT evidence. Counting the markers twice
# from two copies of the same rule is two counters of one thing (#342).
$wireSecondMarker = New-WireRoot 'secondmarker' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '        string findText = LoadSource(findRel);' `
    '        string findText = LoadSource(findRel); string sevSecond = "SEVERITY:";' ''
$runWireSecondMarker = Invoke-Suite 'wire-secondmarker' $seam $wireSecondMarker
if (-not (Assert-Mutation 'a second literal spelling of the severity marker' $runWireSecondMarker 'W28' 'W25')) { $overall = 1 }
Say ''

# RE-SITED. Its anchor was a line this round's harness introduced, so the whole
# driver could not run against the round-7 harness and the BUILD blind control had
# to use an older copy of this file - which is the mechanism behind LENS 8. The
# rule at the head of this section already required an anchor present at the
# previous tip; this now keeps it.
$wireMarkerInert = New-WireRoot 'markerinert' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '        // ---- V2: NEGATIVE CONTROL for "once", and for every V mutation. -------' `
    '        // ---- V2: NEGATIVE CONTROL for "once", and for every V mutant. ---------' ''
$runWireMarkerInert = Invoke-Suite 'wire-markerinert' $seam $wireMarkerInert
if (-not (Assert-Inert 'the single marker spelling, inert edit' $runWireMarkerInert @('W28', 'W25'))) { $overall = 1 }
Say ''

# ---------- lens 3: the premise the bare-name rule rests on -------------------
# The caller bound searches the writers' owner by ONE name and admits the bare
# form only in the declaring file. Both halves assume no shipped file aliases
# that owner and none imports its members statically. That was true, and it was
# written in a comment instead of checked.
$wireAliasUsing = New-WireRootSpans 'aliasusing' 'plugin/NativeUI.cs' `
    @(, @('using System;',
          'using Photon.Pun;',
          ('using Photon.Pun;' + $nl + 'using AC = CompetitiveRounds.ApiClient;'),
          'namespace CompetitiveRounds'))
$runWireAliasUsing = Invoke-Suite 'wire-aliasusing' $seam $wireAliasUsing
if (-not (Assert-Mutation 'a second name for the writers own type' $runWireAliasUsing 'W25' 'W1')) { $overall = 1 }
Say ''

$wireAliasInert = New-WireRootSpans 'aliasinert' 'plugin/NativeUI.cs' `
    @(, @('using System;',
          'using Photon.Pun;',
          ('using Photon.Pun;' + $nl + 'using System.Globalization;'),
          'namespace CompetitiveRounds'))
$runWireAliasInert = Invoke-Suite 'wire-aliasinert' $seam $wireAliasInert
if (-not (Assert-Inert 'an ordinary using added, inert edit' $runWireAliasInert @('W25', 'W1'))) { $overall = 1 }
Say ''

# ============== THE COLD LENS ON THE ROUND-8 BUILD TIP ed3b1e5 ===============
# Six findings, read on the tip the build stage returned: one HIGH, two MEDIUM
# and three LOW. Five of the six are checkable and carry a mutant here; LENS 4's
# successor pair (LENS 6 and LENS 9) is ONE defect read twice and carries ONE
# mutant, which is stated rather than counted twice.

# ---------- lens 5: a call site spelled across a line break -------------------
# CallSitesIn matched a qualified name as one contiguous substring, so the
# ordinary member-access continuation was invisible to every scan built on it.
# This plants exactly that spelling of a SECOND call to the allowed writer, in a
# member outside the bound caller set: under the round-8 counter it left W25
# green and the printed map unchanged.
$wireSplitCall = New-WireRoot 'splitcall' 'plugin/CompetitiveUI.cs' `
    'public static void Tick()' `
    '            NativeUI.Tick();' `
    ('            ApiClient' + $nl + '                .Initialize(Plugin.ApiBaseUrl.Value);' + $nl + '            NativeUI.Tick();') ''
$runWireSplitCall = Invoke-Suite 'wire-splitcall' $seam $wireSplitCall
if (-not (Assert-Mutation 'an allowed writer called across a line break' $runWireSplitCall 'W25' 'W1')) { $overall = 1 }
Say ''

# ---------- lens 5: the same spelling, on a staging entry point ---------------
# The other half of the same hole: the file-grain clause that says which files
# may reach a staging entry point reads the same counter.
$wireSplitEntry = New-WireRoot 'splitentry' 'plugin/CompetitiveUI.cs' `
    'public static void Tick()' `
    '            NativeUI.Tick();' `
    ('            ApiClient' + $nl + '                .UpdateFfaQueuePoll(false);' + $nl + '            NativeUI.Tick();') ''
$runWireSplitEntry = Invoke-Suite 'wire-splitentry' $seam $wireSplitEntry
if (-not (Assert-Mutation 'a staging entry point reached across a line break' $runWireSplitEntry 'W25' 'W1')) { $overall = 1 }
Say ''

$wireSplitInert = New-WireRoot 'splitinert' 'plugin/CompetitiveUI.cs' `
    'public static void Tick()' `
    '            // Bug 213: keep the published chat-mute marker in step with the' `
    '            // Bug 213: keep the published chat-mute marker aligned with the' ''
$runWireSplitInert = Invoke-Suite 'wire-splitinert' $seam $wireSplitInert
if (-not (Assert-Inert 'the segment-wise call matcher, inert edit' $runWireSplitInert @('W25', 'W1'))) { $overall = 1 }
Say ''

# ---------- lens 6 / lens 9: a second membership for the scan surface ---------
# The clause that closed LENS 4 could not fire on any input, and the reason given
# for its having no mutant was refuted by the suite's own log. The closure is
# structural - one read, one pair, one dictionary - and W29 is what holds it.
# This builds the pair a second time, outside its loader.
$wireSecondSurface = New-WireRoot 'secondsurface' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '        var answerOwner = new Dictionary<string, string>();' `
    '        var answerOwner = new Dictionary<string, string>(); var surfaceAgain = new SurfaceFile(LoadSource(apiRel), LoadBlanked(apiRel));' ''
$runWireSecondSurface = Invoke-Suite 'wire-secondsurface' $seam $wireSecondSurface
if (-not (Assert-Mutation 'a second membership for the scan surface' $runWireSecondSurface 'W29' 'W25')) { $overall = 1 }
Say ''

$wireSurfaceInert = New-WireRoot 'surfaceinert' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '        // of it: four facts in, one action out, and no selector anywhere.' `
    '        // of it: four facts in, one action out, and no selector at all.' ''
$runWireSurfaceInert = Invoke-Suite 'wire-surfaceinert' $seam $wireSurfaceInert
if (-not (Assert-Inert 'the one-membership surface, inert edit' $runWireSurfaceInert @('W29', 'W25'))) { $overall = 1 }
Say ''

# ---------- lens 7: a counter whose NAME carries the view --------------------
# After the single-blanking-site change the old counter was CountOf under a name
# that still promised a blanking, with nothing holding a caller to the cached
# CODE view. This puts a call to it back, handed the PROSE text of a file.
$wireViewByName = New-WireRoot 'viewbyname' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '            string stated = ProximityVictim.VanillaAnswerReason(answer);' `
    '            string stated = ProximityVictim.VanillaAnswerReason(answer); int live = CountOnCodeLines(LoadSource(apiRel), "baseUrl");' ''
$runWireViewByName = Invoke-Suite 'wire-viewbyname' $seam $wireViewByName
if (-not (Assert-Mutation 'a counter whose name carries the view it does not take' $runWireViewByName 'W30' 'W25')) { $overall = 1 }
Say ''

$wireViewByNameInert = New-WireRoot 'viewbynameinert' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '        // V - THE REPAIR DECISION. ProximityVictim.VictimAction is the whole' `
    '        // V - THE REPAIR DECISION. ProximityVictim.VictimAction is the sum' ''
$runWireViewByNameInert = Invoke-Suite 'wire-viewbynameinert' $seam $wireViewByNameInert
if (-not (Assert-Inert 'the view-taking counter, inert edit' $runWireViewByNameInert @('W30', 'W25'))) { $overall = 1 }
Say ''

# ---------- lens 10: a finding closed with no body in the findings file ------
# The findings file called itself the one place the round's findings are written
# down and the census counted only what was in it, so four findings closed in the
# same pass counted nowhere. H4 holds the closure table's CLOSES: lines and the
# bodies to each other; this closes a finding that has no body.
$wireClosureNoBody = New-WireRootSpans 'closurenobody' 'tools/tests/bug389-seam/R8-CLOSURES.md' `
    @(, @('N10 LOW - THE PROMISED REPOSITORY COPY NEVER REACHED THE PIN.',
          'CLOSES: N10',
          'CLOSES: N10, N11',
          "THIS PASS'S COLD LENS, read on the build tip ed3b1e5."))
$runWireClosureNoBody = Invoke-Suite 'wire-closurenobody' $seam $wireClosureNoBody
if (-not (Assert-Mutation 'a finding closed with no body in the findings file' $runWireClosureNoBody 'H4' 'W25')) { $overall = 1 }
Say ''

$wireClosureBodyInert = New-WireRootSpans 'closurebodyinert' 'tools/tests/bug389-seam/R8-CLOSURES.md' `
    @(, @('N10 LOW - THE PROMISED REPOSITORY COPY NEVER REACHED THE PIN.',
          'naming all three paths. See the head of this file.',
          'naming all three paths. See the head of this table.',
          "THIS PASS'S COLD LENS, read on the build tip ed3b1e5."))
$runWireClosureBodyInert = Invoke-Suite 'wire-closurebodyinert' $seam $wireClosureBodyInert
if (-not (Assert-Inert 'the closed-set of findings, inert edit' $runWireClosureBodyInert @('H4', 'W25'))) { $overall = 1 }
Say ''

# ============ THE COLD LENS ON THE ROUND-8 APPLY TIP 934b35e ================
# The round-8 gate returned one MEDIUM and four LOW, every one of them in the
# test surface or in the closure documents. The MEDIUM's three controls are the
# harness mutants above; these are the rest.

# ---------- R8-new-L1: the guard read a line prefix, not a directive ---------
# The alias and static-import guard tested StartsWith('using static') and
# StartsWith('using '), so the file-spanning forms walked past it. This plants
# the static one: a bare writer name brought into a file where the caller bound
# searches qualified only.
$wireGlobalStatic = New-WireRootSpans 'globalstatic' 'plugin/NativeUI.cs' `
    @(, @('using System;',
          'using Photon.Pun;',
          ('using Photon.Pun;' + $nl + 'global using static CompetitiveRounds.ApiClient;'),
          'namespace CompetitiveRounds'))
$runWireGlobalStatic = Invoke-Suite 'wire-globalstatic' $seam $wireGlobalStatic
if (-not (Assert-Mutation 'a global static import of the writers own type' $runWireGlobalStatic 'W25' 'W1')) { $overall = 1 }
Say ''

# And the alias half: a second name for the owner, in the form the shipped tree
# already uses at plugin/MusicEngine.cs.
$wireGlobalAlias = New-WireRootSpans 'globalalias' 'plugin/NativeUI.cs' `
    @(, @('using System;',
          'using Photon.Pun;',
          ('using Photon.Pun;' + $nl + 'global using GAC = CompetitiveRounds.ApiClient;'),
          'namespace CompetitiveRounds'))
$runWireGlobalAlias = Invoke-Suite 'wire-globalalias' $seam $wireGlobalAlias
if (-not (Assert-Mutation 'a global alias for the writers own type' $runWireGlobalAlias 'W25' 'W1')) { $overall = 1 }
Say ''

# The twin: an ordinary global using, which names no member and no second name
# for the owner. The shipped tree carries one of these already, so a guard that
# reddened here would redden on the tree it is run against.
$wireGlobalInert = New-WireRootSpans 'globalinert' 'plugin/NativeUI.cs' `
    @(, @('using System;',
          'using Photon.Pun;',
          ('using Photon.Pun;' + $nl + 'global using System.Globalization;'),
          'namespace CompetitiveRounds'))
$runWireGlobalInert = Invoke-Suite 'wire-globalinert' $seam $wireGlobalInert
if (-not (Assert-Inert 'an ordinary global using added' $runWireGlobalInert @('W25', 'W1'))) { $overall = 1 }
Say ''

# ---------- R8-new-L2: the construction count was a substring count ----------
# W29 searched the literals 'new SurfaceFile(' and 'new Dictionary<string,
# SurfaceFile>'. This builds the pair a second time in the form the language
# offers for exactly this declaration, which the literals cannot see.
$wireSurfaceTargetTyped = New-WireRoot 'surfacetargettyped' 'tools/tests/bug389-seam/Program.cs' `
    'private static int Main()' `
    '        var answerOwner = new Dictionary<string, string>();' `
    '        var answerOwner = new Dictionary<string, string>(); SurfaceFile surfaceTargetTyped = new(LoadSource(apiRel), LoadBlanked(apiRel));' ''
$runWireSurfaceTargetTyped = Invoke-Suite 'wire-surfacetargettyped' $seam $wireSurfaceTargetTyped
if (-not (Assert-Mutation 'a target-typed second construction of the surface pair' $runWireSurfaceTargetTyped 'W29' 'W25')) { $overall = 1 }
Say ''

# The twin for the same change: the ONE real construction, respelled with
# different spacing. A structural reader must still find exactly one and still
# find it inside its loader; a literal search finds none and reddens on the
# typist.
$wireSurfaceSpacing = New-WireRoot 'surfacespacing' 'tools/tests/bug389-seam/Program.cs' `
    'internal static SurfaceFile Load(string relative)' `
    '            return new SurfaceFile(prose, LoadBlanked(relative));' `
    '            return new  SurfaceFile (prose, LoadBlanked(relative));' ''
$runWireSurfaceSpacing = Invoke-Suite 'wire-surfacespacing' $seam $wireSurfaceSpacing
if (-not (Assert-Inert 'the one construction, respelled' $runWireSurfaceSpacing @('W29', 'W25'))) { $overall = 1 }
Say ''

# ---------- R8-new-L3: a residual the code had already closed ----------------
# Both finding documents said a null-conditional dot stayed invisible to the call
# walker, which has stepped over it since the LENS 5 rewrite. H5 asks the walker
# and holds both documents to its answer; this restores the stale verdict.
$wireFormStale = New-WireRootSpans 'formstale' 'tools/tests/bug389-seam/R8-CLOSURES.md' `
    @(, @('WHAT THE CALL WALKER ACTUALLY SEES',
          'WALKER-FORM: ?. = SEEN',
          'WALKER-FORM: ?. = UNSEEN',
          'ROUND-7 FINDINGS, BY NUMBER.'))
$runWireFormStale = Invoke-Suite 'wire-formstale' $seam $wireFormStale
if (-not (Assert-Mutation 'a residual naming a form the walker already handles' $runWireFormStale 'H5' 'W25')) { $overall = 1 }
Say ''

$wireFormInert = New-WireRootSpans 'forminert' 'tools/tests/bug389-seam/R8-CLOSURES.md' `
    @(, @('WHAT THE CALL WALKER ACTUALLY SEES',
          'the forms are answered by the walker itself',
          'the forms are answered by the walker alone',
          'ROUND-7 FINDINGS, BY NUMBER.'))
$runWireFormInert = Invoke-Suite 'wire-forminert' $seam $wireFormInert
if (-not (Assert-Inert 'the walker-form verdicts, inert edit' $runWireFormInert @('H5', 'W25'))) { $overall = 1 }
Say ''

# ---------- R8-new-L4: a legend that inventoried two logs of three -----------
# H6 counts the blind-control logs that are in the evidence set and holds both
# documents to that count. This takes one log out of the set.
$evidenceLogRenamed = New-EvidenceDir 'logrenamed' `
    'bug389-r8-lens2-prior-harness.log' 'bug389-r8-lens2-prior-harness.log.kept'
$runEvidenceLogRenamed = Invoke-Suite 'evidence-logrenamed' $seam $repo '' $evidenceLogRenamed
if (-not (Assert-Mutation 'a blind-control log taken out of the evidence set' $runEvidenceLogRenamed 'H6' 'W25')) { $overall = 1 }
Say ''

# The twin: the same log RENAMED to another name the count still describes. The
# count is of files, not of names, so this must not move it - a case that
# reddened here would be reading the legend and not the set.
$evidenceOtherFile = New-EvidenceDir 'otherfile' `
    'bug389-r8-lens2-prior-harness.log' 'bug389-r8-lens3-prior-harness.log'
$runEvidenceOtherFile = Invoke-Suite 'evidence-otherfile' $seam $repo '' $evidenceOtherFile
if (-not (Assert-Inert 'a blind-control log renamed within the set' $runEvidenceOtherFile @('H6', 'W25'))) { $overall = 1 }
Say ''

# ---------- 22. the prior mechanism ----------
# The round-2 files, recovered from git. Every N case asserts something round 3
# DELETED, so every one of them must redden here; W1 reads a file the change
# never touched and must stay green, which is what stops this run from passing
# for the trivial reason that the root is wrong.
$priorRoot = New-PriorRoot 'r2' $priorTip
$runPrior = Invoke-Suite 'prior-r2' $seam $priorRoot
if (-not (Assert-Mutations 'round-2 mechanism' $runPrior `
    @('N1', 'N2', 'N3', 'N4', 'N5', 'N6a', 'N6b', 'N6c') 'W1')) { $overall = 1 }
Say ''

if ($overall -eq 0) { Say 'BUG 389 SEAM SUITE: ALL CHECKS PASSED' }
else { Say 'BUG 389 SEAM SUITE: FAILURES PRESENT' }
exit $overall
