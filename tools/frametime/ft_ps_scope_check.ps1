<#
ft_ps_scope_check.ps1 <file.ps1> [<file.ps1> ...]

Reads each file with PowerShell's parser (no code of the file runs) and lists every assignment whose target is a name
that is already taken in the scope the assignment runs in. PowerShell names are case-insensitive, so "$cultureGate"
IS the parameter "$CultureGate". Two kinds of taken names are read:
  - a parameter of that scope. A parameter declared with a type keeps the type for its whole scope:
    "$cultureGate = <a table>" in the scope of "[switch]$CultureGate" is a conversion at run time, an error for a
    switch and a silent change of the value for a string. That fault ended the laptop seat script one second into
    sitting V's first try (12 Nov 2026): the line had never run in a test. An untyped parameter takes any value, so
    an assignment to it is no error; it is listed too (type 'untyped'), because it replaces the caller's value.
  - a name this PowerShell itself holds constant or read-only ($PID, $Host, $HOME, ...; read from the running
    PowerShell, not from a list here).

Scopes: the file's top level (its param block), each function (its param block and its parenthesised parameters) and
each script block literal that has a param block of its own. A script block literal without a param block is counted
under the scope around it: ForEach-Object and Where-Object run their blocks in the caller's scope, and a block run
with & has a scope of its own, so this is the side that reports more. A target written $script:<name> is held against
the file's parameters from any scope; $local: and $private: are read as the scope they stand in; $global:<name> is
held against the constant names only. A target on a drive ($env:) or with another scope word is not read.
Targets: the left side of every assignment statement (=, += and the like; a cast and a list of targets are read
through; a member or an index target is no assignment to the variable) and the loop variable of every foreach
statement. A variable set through a cmdlet (Set-Variable, New-Variable) is not read.

A dot-sourced file runs in the scope of the statement that names it. Each statement of the one form
". (Join-Path $PSScriptRoot '<name>.ps1')" is followed: the named file's top-level assignments are held against the
parameters of the scope the statement stands in, and its $script: assignments against the file's parameters. A
dot-source statement of another form is refused, never passed over.

Output, per file: one line per finding
  SCOPE-ASSIGN <file>:<line> $<name> is assigned in the scope of its own parameter [<type>]$<Name> (<scope>)
  SCOPE-CONST <file>:<line> $<name> is assigned, and this PowerShell holds $<Name> <options> (<scope>)
then 'SCOPE-CHECK <file> parameters <n> targets <n> dot-sourced <n> findings <n>'. The last line:
  'SCOPE-CHECK-ALL files <n> findings <n>'.
Exit codes: 0 no finding; 1 one finding or more; 2 a file was not read or did not parse, or a dot-source statement
was not followed (the line starts 'SCOPE-CHECK-REFUSED'), or no file was named. 2 goes before 1.
#>
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

function Out1([string]$text) { [Console]::Out.WriteLine($text) }

# lower-case name -> @{ Name; Type } for each parameter ('untyped' where it carries no type)
function ParamsOf($paramAsts) {
    $m = @{}
    foreach ($pa in @($paramAsts)) {
        if ($null -eq $pa) { continue }
        $tc = @($pa.Attributes | Where-Object { $_ -is [System.Management.Automation.Language.TypeConstraintAst] })
        $nm = $pa.Name.VariablePath.UserPath
        $ty = 'untyped'
        if ($tc.Count) { $ty = $tc[0].TypeName.FullName }
        $m[$nm.ToLowerInvariant()] = @{ Name = $nm; Type = $ty }
    }
    return $m
}

# the parameters of the file's top level
function RootParams($root) {
    if ($root.ParamBlock) { return (ParamsOf @($root.ParamBlock.Parameters)) }
    return @{}
}

# the scope a statement at $node runs in: @{ What; Params; Top }
function ScopeOf($node, $root) {
    $up = $node.Parent
    while ($null -ne $up) {
        if ($up -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
            $ps = @()
            if ($up.Parameters) { $ps += @($up.Parameters) }
            if ($up.Body.ParamBlock) { $ps += @($up.Body.ParamBlock.Parameters) }
            return @{ What = ('function {0}' -f $up.Name); Params = (ParamsOf $ps); Top = $false }
        }
        if (($up -is [System.Management.Automation.Language.ScriptBlockExpressionAst]) -and $up.ScriptBlock.ParamBlock) {
            return @{ What = ('the script block at line {0}' -f $up.Extent.StartLineNumber)
                Params = (ParamsOf @($up.ScriptBlock.ParamBlock.Parameters)); Top = $false }
        }
        $up = $up.Parent
    }
    return @{ What = "the file's top level"; Params = (RootParams $root); Top = $true }
}

# the variable expressions that an assignment's left side writes
function TargetsOf($e) {
    if ($e -is [System.Management.Automation.Language.VariableExpressionAst]) { return @($e) }
    if ($e -is [System.Management.Automation.Language.AttributedExpressionAst]) { return @(TargetsOf $e.Child) }
    if ($e -is [System.Management.Automation.Language.ArrayLiteralAst]) {
        $all = @()
        foreach ($el in $e.Elements) { $all += @(TargetsOf $el) }
        return $all
    }
    return @()
}

# every variable a file's statements write, in the file's order
function WritesOf($ast) {
    $w = @()
    foreach ($a in $ast.FindAll({ param($x) $x -is [System.Management.Automation.Language.AssignmentStatementAst] }, $true)) {
        $w += @(TargetsOf $a.Left)
    }
    foreach ($fe in $ast.FindAll({ param($x) $x -is [System.Management.Automation.Language.ForEachStatementAst] }, $true)) {
        $w += @($fe.Variable)
    }
    return @($w | Sort-Object { $_.Extent.StartOffset })
}

# what a written variable names: @{ Name; Kind }, Kind 'here' (the scope it stands in), 'script' or 'global';
# $null for a target that is not read (a drive, another scope word)
function NameOf($v) {
    $vp = $v.VariablePath
    if (-not $vp.IsVariable) { return $null }
    $full = $vp.UserPath
    $bare = $full.Substring($full.IndexOf(':') + 1)
    if ($vp.IsUnqualified) { return @{ Name = $full; Kind = 'here' } }
    if ($vp.IsScript) { return @{ Name = $bare; Kind = 'script' } }
    if ($vp.IsGlobal) { return @{ Name = $bare; Kind = 'global' } }
    if ($vp.IsLocal -or $vp.IsPrivate) { return @{ Name = $bare; Kind = 'here' } }
    return $null
}

# one file through the parser: @{ Ast; Full; Err }
function ParseOne([string]$path) {
    $tokens = $null
    $errs = $null
    $full = $null
    $ast = $null
    try {
        $full = (Resolve-Path -LiteralPath $path).ProviderPath
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($full, [ref]$tokens, [ref]$errs)
    }
    catch { return @{ Ast = $null; Full = $full; Err = ('not read ({0})' -f $_.Exception.Message) } }
    if ($errs -and @($errs).Count) {
        return @{ Ast = $null; Full = $full; Err = ('{0} parse error(s), the first at line {1}: {2}' -f @($errs).Count,
                $errs[0].Extent.StartLineNumber, $errs[0].Message) }
    }
    return @{ Ast = $ast; Full = $full; Err = $null }
}

# the names this PowerShell holds constant or read-only: lower-case name -> @{ Name; Options }
$held = @{}
foreach ($gv in @(Get-Variable -Scope Global)) {
    $opt = [string]$gv.Options
    if ($opt -match 'Constant|ReadOnly') { $held[$gv.Name.ToLowerInvariant()] = @{ Name = $gv.Name; Options = $opt } }
}

$named = @($args)
if ($named.Count -eq 0) { Out1 'SCOPE-CHECK-REFUSED no file was named'; exit 2 }
$findings = 0
$refused = 0
foreach ($f in $named) {
    $p = ParseOne $f
    if ($p.Err) { Out1 ('SCOPE-CHECK-REFUSED {0}: {1}' -f $f, $p.Err); $refused++; continue }
    $ast = $p.Ast
    $root = RootParams $ast
    $writes = @(WritesOf $ast)
    $here = 0
    foreach ($v in $writes) {
        $nm = NameOf $v
        if ($null -eq $nm) { continue }
        $key = $nm.Name.ToLowerInvariant()
        $line = $v.Extent.StartLineNumber
        $hit = $null
        if ($nm.Kind -eq 'here') {
            $sc = ScopeOf $v $ast
            $what = $sc.What
            $hit = $sc.Params[$key]
        }
        elseif ($nm.Kind -eq 'script') {
            $what = "the file's top level, through `$script:"
            $hit = $root[$key]
        }
        else { $what = 'the global scope, through $global:' }
        if ($hit) {
            $here++
            Out1 ('SCOPE-ASSIGN {0}:{1} ${2} is assigned in the scope of its own parameter [{3}]${4} ({5})' -f $f, $line,
                $nm.Name, $hit.Type, $hit.Name, $what)
        }
        $con = $held[$key]
        if ($con) {
            $here++
            Out1 ('SCOPE-CONST {0}:{1} ${2} is assigned, and this PowerShell holds ${3} {4} ({5})' -f $f, $line, $nm.Name,
                $con.Name, $con.Options, $what)
        }
    }
    # the files this one dot-sources: their statements run in the scope of the statement that names them
    $dots = @($ast.FindAll({ param($x) ($x -is [System.Management.Automation.Language.CommandAst]) -and
                ($x.InvocationOperator -eq [System.Management.Automation.Language.TokenKind]::Dot) }, $true))
    $followed = 0
    foreach ($d in $dots) {
        $dl = $d.Extent.StartLineNumber
        $dm = [regex]::Match($d.CommandElements[0].Extent.Text, '^\(Join-Path \$PSScriptRoot ''([A-Za-z0-9_.-]+\.ps1)''\)$')
        if (-not $dm.Success) {
            Out1 ('SCOPE-CHECK-REFUSED {0}:{1} a dot-source statement is not of the form read here: {2}' -f $f, $dl,
                $d.Extent.Text)
            $refused++
            continue
        }
        $leaf = $dm.Groups[1].Value
        $sp = ParseOne (Join-Path (Split-Path -Parent $p.Full) $leaf)
        if ($sp.Err) { Out1 ('SCOPE-CHECK-REFUSED {0}:{1} dot-sourced {2}: {3}' -f $f, $dl, $leaf, $sp.Err); $refused++; continue }
        $followed++
        $at = ScopeOf $d $ast
        foreach ($v in @(WritesOf $sp.Ast)) {
            $nm = NameOf $v
            if ($null -eq $nm) { continue }
            $key = $nm.Name.ToLowerInvariant()
            $hit = $null
            if ($nm.Kind -eq 'here') { if ((ScopeOf $v $sp.Ast).Top) { $hit = $at.Params[$key] } }
            elseif ($nm.Kind -eq 'script') { $hit = $root[$key] }
            if ($hit) {
                $here++
                Out1 ('SCOPE-ASSIGN {0}:{1} ${2} is assigned in the scope of its own parameter [{3}]${4} ({5} of {6}, dot-sourced at line {7})' -f
                    $sp.Full, $v.Extent.StartLineNumber, $nm.Name, $hit.Type, $hit.Name, $at.What, $f, $dl)
            }
        }
    }
    Out1 ('SCOPE-CHECK {0} parameters {1} targets {2} dot-sourced {3} findings {4}' -f $f, @($root.GetEnumerator()).Count,
        @($writes).Count, $followed, $here)
    $findings += $here
}
Out1 ('SCOPE-CHECK-ALL files {0} findings {1}' -f $named.Count, $findings)
if ($refused) { exit 2 }
if ($findings) { exit 1 }
exit 0
