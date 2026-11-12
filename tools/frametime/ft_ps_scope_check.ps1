<#
ft_ps_scope_check.ps1 <file.ps1> [<file.ps1> ...]

Reads each file with PowerShell's parser (no code of the file runs) and lists every write whose target is a name that
is already taken in the scope the write runs in. PowerShell names are case-insensitive, so "$cultureGate" IS the
parameter "$CultureGate". Two kinds of taken names are read:
  - a parameter of that scope. A parameter declared with a type keeps the type for its whole scope:
    "$cultureGate = <a table>" in the scope of "[switch]$CultureGate" is a conversion at run time, an error for a
    switch and a silent change of the value for a string. That fault ended the laptop seat script one second into
    sitting V's first try (12 Nov 2026): the line had never run in a test. An untyped parameter takes any value, so
    a write to it is no error; it is listed too (type 'untyped'), because it replaces the caller's value.
  - a name this PowerShell itself holds constant or read-only ($PID, $Host, $HOME, ...; read from the running
    PowerShell, not from a list here).

Scopes. A function body is a scope of its own (its param block and its parenthesised parameters). A script block
literal is NOT taken as a boundary, with or without a param block: ForEach-Object, Where-Object and the dot operator
run a block in the caller's scope, and the checker cannot tell which runner a block meets, so it takes the side that
reports more. A write inside a block is held against the block's own parameters and against the parameters of every
scope around it, up to and including the first function around it (or the file's top level when there is none); the
innermost scope that holds the name is reported. A block's parameter names are bound in the caller's scope too
(ForEach-Object, Where-Object, the dot operator), so a block parameter whose name is a parameter of a scope around it
(the same walk) is listed, as "bound as a parameter of the script block at line N". A target written $script:<name>
is held against the file's parameters from any scope; $local:, $private: and $variable: are read as the scope they
stand in; $global:<name> is held against the constant names only. A target on another drive ($env:) is not read.

Write targets read:
  - the left side of every assignment statement (=, += and the like; a cast and a list of targets are read through;
    a member or an index target is no write to the variable), the loop variable of every foreach statement, and the
    operand of ++ and -- (prefix and postfix);
  - Set-Variable, New-Variable, Clear-Variable, Remove-Variable (sv, nv, clv, rv) whose -Name (or first positional
    argument) is a plain string literal or bare word; a literal -Scope of global, script, local or private is read;
  - the value of -OutVariable, -ErrorVariable, -WarningVariable, -InformationVariable, -PipelineVariable (-ov -ev -wv
    -iv -pv, or a prefix that reaches the V of Variable) of any command, when it is a literal (a leading + is
    stripped).
A reference: every [ref]$<name> whose name is a parameter in the scope chain or a held name is listed (SCOPE-REF):
a write through ([ref]$x).Value is not read, so the reference itself is the finding.
A parameter (of the file, a function or a block) whose own name is a held name is listed (SCOPE-CONST).
Counted as UNREAD (one SCOPE-UNREAD line each, a finding): a splatted argument (@name) of any command; one of the
four variable cmdlets whose name is not a literal (or holds a wildcard), or whose -Scope is not one of the four
words; one of the five common variable parameters whose value is not a literal; Invoke-Expression / iex; and
[scriptblock]::Create. Anything else that writes a variable is not read and not listed.

A dot-sourced file runs in the scope of the statement that names it. Each statement of the one form
". (Join-Path $PSScriptRoot '<name>.ps1')" is followed, resolved against the folder of the file it stands in; the
followed file's own dot-source statements are followed the same way (a file already on the chain is not read
again). A followed file's writes that reach its top level are held against its own blocks and top-level parameters
and then against the scope of the statement that sourced it (for a chain, the scope of the chain's first statement
in the named file when every link stands at its file's top level); its $script: writes against the named file's
parameters; all its writes and references (in its functions too) against the held names; its unread constructs are
listed. A dot-source statement of another form is refused, never passed over.

Flow (information only, no finding, no change of the exit code), per named file:
  SCOPE-STRAY <file>:<line> <statement>   a break or continue that stands in no loop or switch (and no trap) of its
      own function / script block / file scope, or a labelled one whose label names no loop or switch around it there
  SCOPE-FLOW <file> stray <n> top-returns <n> last <exit|other>   top-returns: return statements outside every
      function and script block; last: whether the file's last top-level statement is an exit statement.

Output, per file: one line per finding
  SCOPE-ASSIGN <file>:<line> $<name> is assigned in the scope of its own parameter [<type>]$<Name> (<scope>)
  SCOPE-ASSIGN <file>:<line> $<name> is bound as a parameter of the script block at line <n> in the scope of its own
      parameter [<type>]$<Name> (<scope>)
  SCOPE-CONST <file>:<line> $<name> is assigned, and this PowerShell holds $<Name> <options> (<scope>)
  SCOPE-CONST <file>:<line> $<name> is a parameter, and this PowerShell holds $<Name> <options> (<scope>)
  SCOPE-REF <file>:<line> [ref]$<name> takes a reference to its own parameter [<type>]$<Name> (<scope>)
  SCOPE-REF <file>:<line> [ref]$<name> takes a reference to $<Name>, which this PowerShell holds <options> (<scope>)
  SCOPE-UNREAD <file>:<line> <what>
then the flow lines and 'SCOPE-CHECK <file> parameters <n> targets <n> dot-sourced <n> findings <n>'. The last line:
  'SCOPE-CHECK-ALL files <n> findings <n>'.
Exit codes: 0 no finding; 1 one finding or more; 2 a file was not read or did not parse, or a dot-source statement
was not followed (the line starts 'SCOPE-CHECK-REFUSED'), or no file was named. 2 goes before 1.
#>
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

function Out1([string]$text) { [Console]::Out.WriteLine($text) }

# the first line of a statement's text, at most 100 characters
function Short([string]$text) {
    $one = ($text -split "`r?`n")[0]
    if ($one.Length -gt 100) { $one = $one.Substring(0, 100) + '...' }
    return $one
}

# lower-case name -> @{ Name; Type; Line } for each parameter ('untyped' where it carries no type)
function ParamsOf($paramAsts) {
    $m = @{}
    foreach ($pa in @($paramAsts)) {
        if ($null -eq $pa) { continue }
        $tc = @($pa.Attributes | Where-Object { $_ -is [System.Management.Automation.Language.TypeConstraintAst] })
        $nm = $pa.Name.VariablePath.UserPath
        $ty = 'untyped'
        if ($tc.Count) { $ty = $tc[0].TypeName.FullName }
        $m[$nm.ToLowerInvariant()] = @{ Name = $nm; Type = $ty; Line = $pa.Extent.StartLineNumber }
    }
    return $m
}

# the parameters of the file's top level
function RootParams($root) {
    if ($root.ParamBlock) { return (ParamsOf @($root.ParamBlock.Parameters)) }
    return @{}
}

# one scope: @{ What; File; Params }
function FunctionScope($fd, [string]$file) {
    $ps = @()
    if ($fd.Parameters) { $ps += @($fd.Parameters) }
    if ($fd.Body.ParamBlock) { $ps += @($fd.Body.ParamBlock.Parameters) }
    return @{ What = ('function {0}' -f $fd.Name); File = $file; Params = (ParamsOf $ps) }
}

function BlockScope($sbe, [string]$file) {
    $ps = @()
    if ($sbe.ScriptBlock.ParamBlock) { $ps = @($sbe.ScriptBlock.ParamBlock.Parameters) }
    return @{ What = ('the script block at line {0}' -f $sbe.Extent.StartLineNumber); File = $file; Params = (ParamsOf $ps) }
}

# the scopes a statement at $node is held against, innermost first: @{ Chain; Top }. Every script block literal on
# the way up is one (it ends no walk); the first function around the node is the last one; with no function the
# file's top level is, followed by $outer (the scope chain a dot-sourced file runs in). Top: the walk reached the
# file's top level.
function ChainOf($node, $root, [string]$file, $outer) {
    $chain = @()
    $up = $node.Parent
    while ($null -ne $up) {
        if ($up -is [System.Management.Automation.Language.FunctionDefinitionAst]) {
            $chain += @(FunctionScope $up $file)
            return @{ Chain = $chain; Top = $false }
        }
        if ($up -is [System.Management.Automation.Language.ScriptBlockExpressionAst]) { $chain += @(BlockScope $up $file) }
        $up = $up.Parent
    }
    $chain += @(@{ What = "the file's top level"; File = $file; Params = (RootParams $root) })
    if ($null -ne $outer) { $chain += @($outer) }
    return @{ Chain = $chain; Top = $true }
}

# the innermost scope of a chain whose parameters hold $key: @{ Scope; Par }, or $null
function HitIn($chain, [string]$key) {
    foreach ($sc in @($chain)) {
        if ($sc.Params.ContainsKey($key)) { return @{ Scope = $sc; Par = $sc.Params[$key] } }
    }
    return $null
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

# what a variable path names: @{ Name; Kind }, Kind 'here' (the scope it stands in), 'script' or 'global'; $null for
# a path that is not read (another drive, another scope word)
function NameOfPath($vp) {
    if (-not $vp.IsVariable) { return $null }
    $full = $vp.UserPath
    $bare = $full.Substring($full.IndexOf(':') + 1)
    if ($vp.IsUnqualified) { return @{ Name = $full; Kind = 'here' } }
    if ($vp.IsScript) { return @{ Name = $bare; Kind = 'script' } }
    if ($vp.IsGlobal) { return @{ Name = $bare; Kind = 'global' } }
    if ($vp.IsLocal -or $vp.IsPrivate) { return @{ Name = $bare; Kind = 'here' } }
    if ($full -match '^variable:[^:]+$') { return @{ Name = $bare; Kind = 'here' } }
    return $null
}

# one record: @{ How ('write', 'ref' or 'unread'); Node (where the scope walk starts); Line; Offset; Name; Kind; What }
function Rec([string]$how, $node, $nm, [string]$what) {
    $r = @{ How = $how; Node = $node; Line = $node.Extent.StartLineNumber; Offset = $node.Extent.StartOffset
        Name = $null; Kind = $null; What = $what }
    if ($null -ne $nm) { $r.Name = $nm.Name; $r.Kind = $nm.Kind }
    return $r
}

function VarRec([string]$how, $v) {
    $nm = NameOfPath $v.VariablePath
    if ($null -eq $nm) { return @() }
    return (Rec $how $v $nm '')
}

# a literal variable name given to a command: a write record, or an unread record when it is not a plain literal.
# $scopeWord: '' or a literal -Scope value.
function NameRec($cmd, $val, [string]$what, [bool]$plus, [string]$scopeWord) {
    $bad = Rec 'unread' $cmd $null ('{0}: the variable it names is not read: {1}' -f $what, (Short $cmd.Extent.Text))
    if ($val -isnot [System.Management.Automation.Language.StringConstantExpressionAst]) { return $bad }
    $s = $val.Value
    if ($plus -and $s.StartsWith('+')) { $s = $s.Substring(1) }
    if ((-not $s) -or ($s -match '[*?\[\]]')) { return $bad }
    $nm = $null
    try { $nm = NameOfPath ([System.Management.Automation.VariablePath]::new($s)) } catch { $nm = $null }
    if ($null -eq $nm) { return $bad }
    if ($scopeWord) {
        $w = $scopeWord.ToLowerInvariant()
        if ($w -eq 'global') { $nm.Kind = 'global' }
        elseif ($w -eq 'script') { $nm.Kind = 'script' }
        elseif (($w -eq 'local') -or ($w -eq 'private')) { $nm.Kind = 'here' }
        else { return $bad }
    }
    return (Rec 'write' $cmd $nm '')
}

$VarCmds = @('set-variable', 'sv', 'new-variable', 'nv', 'clear-variable', 'clv', 'remove-variable', 'rv')
$VarParamAlias = @('ov', 'ev', 'wv', 'iv', 'pv')
$VarParamStem = @('out', 'error', 'warning', 'information', 'pipeline')
$SwitchNames = @('passthru', 'force', 'whatif', 'confirm', 'verbose', 'debug', 'vb', 'db', 'wi', 'cf')
$ValueNames = @('name', 'value', 'scope', 'description', 'option', 'visibility', 'include', 'exclude', 'erroraction',
    'warningaction', 'informationaction', 'errorvariable', 'warningvariable', 'informationvariable', 'outvariable',
    'outbuffer', 'pipelinevariable', 'ea', 'wa', 'infa', 'ev', 'wv', 'iv', 'ov', 'ob', 'pv')

# whether a parameter name is one of the five common variable parameters (an alias, or a prefix that reaches the V)
function IsVarParam([string]$pn) {
    $p = $pn.ToLowerInvariant()
    if ($VarParamAlias -contains $p) { return $true }
    foreach ($stem in $VarParamStem) {
        $whole = $stem + 'variable'
        if (($p.Length -gt $stem.Length) -and $whole.StartsWith($p)) { return $true }
    }
    return $false
}

# whether a parameter of a variable cmdlet takes no value (a switch, by a prefix no value parameter shares)
function IsSwitchName([string]$pn) {
    $sw = @($SwitchNames | Where-Object { $_.StartsWith($pn) })
    $va = @($ValueNames | Where-Object { $_.StartsWith($pn) })
    return (($sw.Count -gt 0) -and ($va.Count -eq 0))
}

# the records one command gives
function CommandRecs($cmd) {
    $out = @()
    $els = @($cmd.CommandElements)
    $cn = $cmd.GetCommandName()
    if ($cn) { $cn = $cn.Substring($cn.LastIndexOf('\') + 1).ToLowerInvariant() }
    for ($i = 0; $i -lt $els.Count; $i++) {
        $e = $els[$i]
        if ($e -isnot [System.Management.Automation.Language.CommandParameterAst]) { continue }
        if (-not (IsVarParam $e.ParameterName)) { continue }
        $val = $e.Argument
        if (($null -eq $val) -and ($i + 1 -lt $els.Count)) { $val = $els[$i + 1] }
        $out += @(NameRec $cmd $val ('-' + $e.ParameterName) $true '')
    }
    if ($cn -and ($VarCmds -contains $cn)) {
        $byName = @{}
        $pos = @()
        for ($i = 1; $i -lt $els.Count; $i++) {
            $e = $els[$i]
            if ($e -is [System.Management.Automation.Language.CommandParameterAst]) {
                $pn = $e.ParameterName.ToLowerInvariant()
                if ($null -ne $e.Argument) { $byName[$pn] = $e.Argument; continue }
                if (IsSwitchName $pn) { $byName[$pn] = $null; continue }
                if ($i + 1 -lt $els.Count) { $byName[$pn] = $els[$i + 1]; $i++ }
                else { $byName[$pn] = $null }
                continue
            }
            $pos += @($e)
        }
        $nameVal = $null
        $scopeVal = $null
        $hasScope = $false
        foreach ($k in @($byName.Keys)) {
            if ('name'.StartsWith($k)) { $nameVal = $byName[$k] }
            if ('scope'.StartsWith($k)) { $scopeVal = $byName[$k]; $hasScope = $true }
        }
        if (($null -eq $nameVal) -and $pos.Count) { $nameVal = $pos[0] }
        $word = ''
        if ($hasScope) {
            if ($scopeVal -is [System.Management.Automation.Language.StringConstantExpressionAst]) { $word = $scopeVal.Value }
            else { $word = '(not a literal)' }
        }
        $out += @(NameRec $cmd $nameVal $els[0].Extent.Text $false $word)
    }
    if ($cn -and (($cn -eq 'invoke-expression') -or ($cn -eq 'iex'))) {
        $out += @(Rec 'unread' $cmd $null ('Invoke-Expression: {0}' -f (Short $cmd.Extent.Text)))
    }
    return $out
}

# every record of a file, in the file's order
function RecordsOf($ast) {
    $w = @()
    foreach ($a in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] }, $true)) {
        foreach ($v in @(TargetsOf $a.Left)) { $w += @(VarRec 'write' $v) }
    }
    foreach ($fe in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.ForEachStatementAst] }, $true)) {
        $w += @(VarRec 'write' $fe.Variable)
    }
    $steps = @([System.Management.Automation.Language.TokenKind]::PlusPlus, [System.Management.Automation.Language.TokenKind]::MinusMinus,
        [System.Management.Automation.Language.TokenKind]::PostfixPlusPlus, [System.Management.Automation.Language.TokenKind]::PostfixMinusMinus)
    foreach ($un in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.UnaryExpressionAst] }, $true)) {
        if ($steps -contains $un.TokenKind) { foreach ($v in @(TargetsOf $un.Child)) { $w += @(VarRec 'write' $v) } }
    }
    foreach ($cv in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.ConvertExpressionAst] }, $true)) {
        if ((($cv.Type.TypeName.FullName -as [type]) -eq [ref]) -and
            ($cv.Child -is [System.Management.Automation.Language.VariableExpressionAst])) { $w += @(VarRec 'ref' $cv.Child) }
    }
    foreach ($sp in $ast.FindAll({ param($n) ($n -is [System.Management.Automation.Language.VariableExpressionAst]) -and $n.Splatted }, $true)) {
        $w += @(Rec 'unread' $sp $null ('a splatted argument @{0}' -f $sp.VariablePath.UserPath))
    }
    foreach ($cmd in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true)) {
        $w += @(CommandRecs $cmd)
    }
    foreach ($im in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.InvokeMemberExpressionAst] }, $true)) {
        if ($im.Static -and ($im.Expression -is [System.Management.Automation.Language.TypeExpressionAst]) -and
            (($im.Expression.TypeName.FullName -as [type]) -eq [scriptblock]) -and
            ($im.Member -is [System.Management.Automation.Language.StringConstantExpressionAst]) -and ($im.Member.Value -eq 'Create')) {
            $w += @(Rec 'unread' $im $null ('[scriptblock]::Create: {0}' -f (Short $im.Extent.Text)))
        }
    }
    return @($w | Sort-Object { $_.Offset })
}

# how a scope is named in a finding: in the named file its own words; in a followed file with the file it stands in
# and the line of the chain's first dot-source statement in the named file
function Where1($sc, $dl, [string]$via) {
    if ($null -eq $dl) { return ($sc.What + $via) }
    return ('{0} of {1}{2}, dot-sourced at line {3}' -f $sc.What, $sc.File, $via, $dl)
}

# the findings of one file's records, parameters and blocks. $named: the file was named (else it is followed, and
# only what reaches its top level is held against parameters). $outer: the chain a followed file runs in.
function CheckFile($ast, [string]$label, $outer, $dl, $ctx, [bool]$named) {
    $recs = @(RecordsOf $ast)
    if ($named) { $ctx.Targets = @($recs | Where-Object { $_.How -eq 'write' }).Count }
    $scriptScope = @{ What = "the file's top level"; File = $ctx.File; Params = $ctx.Root }
    foreach ($r in $recs) {
        if ($r.How -eq 'unread') {
            $ctx.Here++
            Out1 ('SCOPE-UNREAD {0}:{1} {2}' -f $label, $r.Line, $r.What)
            continue
        }
        $key = $r.Name.ToLowerInvariant()
        $hit = $null
        $via = ''
        if ($r.Kind -eq 'here') {
            $c = ChainOf $r.Node $ast $label $outer
            $inner = $c.Chain[0]
            if ($named -or $c.Top) { $hit = HitIn $c.Chain $key }
        }
        elseif ($r.Kind -eq 'script') {
            $via = ', through $script:'
            $inner = $scriptScope
            $hit = HitIn @($scriptScope) $key
        }
        else {
            $via = ', through $global:'
            $inner = @{ What = 'the global scope'; File = $ctx.File }
        }
        if ($hit) {
            $ctx.Here++
            $wh = Where1 $hit.Scope $dl $via
            if ($r.How -eq 'ref') {
                Out1 ('SCOPE-REF {0}:{1} [ref]${2} takes a reference to its own parameter [{3}]${4} ({5})' -f $label, $r.Line,
                    $r.Name, $hit.Par.Type, $hit.Par.Name, $wh)
            }
            else {
                Out1 ('SCOPE-ASSIGN {0}:{1} ${2} is assigned in the scope of its own parameter [{3}]${4} ({5})' -f $label,
                    $r.Line, $r.Name, $hit.Par.Type, $hit.Par.Name, $wh)
            }
        }
        $con = $held[$key]
        if ($con) {
            $ctx.Here++
            $wh = Where1 $inner $dl $via
            if ($r.How -eq 'ref') {
                Out1 ('SCOPE-REF {0}:{1} [ref]${2} takes a reference to ${3}, which this PowerShell holds {4} ({5})' -f $label,
                    $r.Line, $r.Name, $con.Name, $con.Options, $wh)
            }
            else {
                Out1 ('SCOPE-CONST {0}:{1} ${2} is assigned, and this PowerShell holds ${3} {4} ({5})' -f $label, $r.Line,
                    $r.Name, $con.Name, $con.Options, $wh)
            }
        }
    }
    # a block's parameter names are bound in the caller's scope when ForEach-Object, Where-Object or the dot runs it
    $blocks = @($ast.FindAll({ param($n) ($n -is [System.Management.Automation.Language.ScriptBlockExpressionAst]) -and
                ($null -ne $n.ScriptBlock.ParamBlock) }, $true))
    foreach ($b in $blocks) {
        $c = ChainOf $b $ast $label $outer
        if (-not ($named -or $c.Top)) { continue }
        foreach ($pa in @($b.ScriptBlock.ParamBlock.Parameters)) {
            $pn = $pa.Name.VariablePath.UserPath
            $hit = HitIn $c.Chain $pn.ToLowerInvariant()
            if ($hit) {
                $ctx.Here++
                Out1 ('SCOPE-ASSIGN {0}:{1} ${2} is bound as a parameter of the script block at line {3} in the scope of its own parameter [{4}]${5} ({6})' -f
                    $label, $pa.Extent.StartLineNumber, $pn, $b.Extent.StartLineNumber, $hit.Par.Type, $hit.Par.Name,
                    (Where1 $hit.Scope $dl ''))
            }
        }
    }
    # a parameter whose own name is a held name (the named file only: a followed file is read for this when named)
    if ($named) {
        $scopes = @(@{ What = "the file's top level"; File = $label; Params = (RootParams $ast) })
        foreach ($fd in $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
            $scopes += @(FunctionScope $fd $label)
        }
        foreach ($b in $blocks) { $scopes += @(BlockScope $b $label) }
        foreach ($sc in $scopes) {
            foreach ($pv in @($sc.Params.Values)) {
                $con = $held[$pv.Name.ToLowerInvariant()]
                if ($con) {
                    $ctx.Here++
                    Out1 ('SCOPE-CONST {0}:{1} ${2} is a parameter, and this PowerShell holds ${3} {4} ({5})' -f $label,
                        $pv.Line, $pv.Name, $con.Name, $con.Options, $sc.What)
                }
            }
        }
    }
}

# the files a file dot-sources, followed recursively; $chainFiles: the files already on this chain (lower-case paths)
function Follow($ast, [string]$full, [string]$label, $outer, $chainFiles, $ctx, $dl) {
    $dots = @($ast.FindAll({ param($n) ($n -is [System.Management.Automation.Language.CommandAst]) -and
                ($n.InvocationOperator -eq [System.Management.Automation.Language.TokenKind]::Dot) }, $true))
    foreach ($d in $dots) {
        $line = $d.Extent.StartLineNumber
        $dm = [regex]::Match($d.CommandElements[0].Extent.Text, '^\(Join-Path \$PSScriptRoot ''([A-Za-z0-9_.-]+\.ps1)''\)$')
        if (-not $dm.Success) {
            Out1 ('SCOPE-CHECK-REFUSED {0}:{1} a dot-source statement is not of the form read here: {2}' -f $label, $line,
                $d.Extent.Text)
            $ctx.Refused++
            continue
        }
        $leaf = $dm.Groups[1].Value
        $sp = ParseOne (Join-Path (Split-Path -Parent $full) $leaf)
        if ($sp.Err) {
            Out1 ('SCOPE-CHECK-REFUSED {0}:{1} dot-sourced {2}: {3}' -f $label, $line, $leaf, $sp.Err)
            $ctx.Refused++
            continue
        }
        $lk = $sp.Full.ToLowerInvariant()
        if ($chainFiles -contains $lk) { continue }
        $ctx.Followed++
        $at = ChainOf $d $ast $label $outer
        $first = $dl
        if ($null -eq $first) { $first = $line }
        CheckFile $sp.Ast $sp.Full $at.Chain $first $ctx $false
        Follow $sp.Ast $sp.Full $sp.Full $at.Chain (@($chainFiles) + @($lk)) $ctx $first
    }
}

# break, continue and return of a file: @{ Stray; TopReturns; Last }
function FlowOf($root) {
    $stray = @()
    $jumps = @($root.FindAll({ param($n) ($n -is [System.Management.Automation.Language.BreakStatementAst]) -or
                ($n -is [System.Management.Automation.Language.ContinueStatementAst]) }, $true))
    foreach ($j in $jumps) {
        $lab = $null
        $dyn = $false
        if ($null -ne $j.Label) {
            if ($j.Label -is [System.Management.Automation.Language.StringConstantExpressionAst]) { $lab = $j.Label.Value }
            else { $dyn = $true }
        }
        $caught = $false
        $up = $j.Parent
        while ($null -ne $up) {
            if (($up -is [System.Management.Automation.Language.FunctionDefinitionAst]) -or
                ($up -is [System.Management.Automation.Language.ScriptBlockExpressionAst])) { break }
            if ($up -is [System.Management.Automation.Language.TrapStatementAst]) { $caught = $true; break }
            if ($up -is [System.Management.Automation.Language.LabeledStatementAst]) {
                if ($null -eq $j.Label) { $caught = $true; break }
                if ((-not $dyn) -and $up.Label -and ($up.Label -eq $lab)) { $caught = $true; break }
            }
            $up = $up.Parent
        }
        if (-not $caught) { $stray += @($j) }
    }
    $tops = 0
    foreach ($rs in $root.FindAll({ param($n) $n -is [System.Management.Automation.Language.ReturnStatementAst] }, $true)) {
        $inside = $false
        $up = $rs.Parent
        while ($null -ne $up) {
            if (($up -is [System.Management.Automation.Language.FunctionDefinitionAst]) -or
                ($up -is [System.Management.Automation.Language.ScriptBlockExpressionAst]) -or
                ($up -is [System.Management.Automation.Language.TrapStatementAst])) { $inside = $true; break }
            $up = $up.Parent
        }
        if (-not $inside) { $tops++ }
    }
    $last = 'other'
    if ($root.EndBlock -and @($root.EndBlock.Statements).Count) {
        $st = @($root.EndBlock.Statements)
        if ($st[$st.Count - 1] -is [System.Management.Automation.Language.ExitStatementAst]) { $last = 'exit' }
    }
    return @{ Stray = $stray; TopReturns = $tops; Last = $last }
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
    $ctx = @{ Here = 0; Refused = 0; Followed = 0; Targets = 0; Root = $root; File = $f }
    CheckFile $ast $f $null $null $ctx $true
    # the files this one dot-sources: their statements run in the scope of the statement that names them
    Follow $ast $p.Full $f $null @($p.Full.ToLowerInvariant()) $ctx $null
    $flow = FlowOf $ast
    foreach ($j in @($flow.Stray)) { Out1 ('SCOPE-STRAY {0}:{1} {2}' -f $f, $j.Extent.StartLineNumber, (Short $j.Extent.Text)) }
    Out1 ('SCOPE-FLOW {0} stray {1} top-returns {2} last {3}' -f $f, @($flow.Stray).Count, $flow.TopReturns, $flow.Last)
    Out1 ('SCOPE-CHECK {0} parameters {1} targets {2} dot-sourced {3} findings {4}' -f $f, @($root.GetEnumerator()).Count,
        $ctx.Targets, $ctx.Followed, $ctx.Here)
    $findings += $ctx.Here
    $refused += $ctx.Refused
}
Out1 ('SCOPE-CHECK-ALL files {0} findings {1}' -f $named.Count, $findings)
if ($refused) { exit 2 }
if ($findings) { exit 1 }
exit 0
