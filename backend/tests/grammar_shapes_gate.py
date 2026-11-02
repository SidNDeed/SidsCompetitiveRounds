"""The frozen grammar of the H3 admission-gate walks (rehearsal-four round 7,
ruling REHEARSAL-FOUR-R6 (1)(b); used by test_match_hold_admission_gate_pg).

Four frozen literals, generated ONCE from the real spans the gate walks visit
at a30d37f6 (the generator: rehearsal-four scratch r7/gg/gen_shapes.py); never
regenerated to fit a file. Pruning removed nothing: every entry is a real
span's, none was added by hand, so no shape a prior finding's program needs
and the real spans do not use is present:

  SHAPES     every node shape (shape_grammar.shape) a walked span or a walked
             function body may hold;
  ANCESTORS  every `<parent>.<field>><class>` a statement enclosing a site
             span (the span's first statement included) may have;
  BINDINGS   per role ("site": a function holding a walked span; "helper": a
             body closed_walk descends into; "answer": a refusal answer or
             the hold replay), each (spelling, how) a function of that role
             may bind among the spellings the walks give a meaning to, with
             the most times one function binds it;
  IMPORTS    every import statement a checked function may hold, exactly:
             (kind, module, level, ((name, asname), ...)).

MEANINGFUL is hand-written: the spellings every walk gives a meaning to. A
function's meaningful spellings are these plus every plain-name callee of
its walked span (a name the walks resolve as the module's).

Nothing here reasons about what a name denotes (rule (1)(c)): a shape is
syntax, a binding is a spelling and how it is bound, an import is its text.
"""
import ast
import collections

import shape_grammar as _sg


class Refusal(Exception):
    """args[0]: the sentence, `grammar <file>:<line>: <shape>` or
    `binding <file>:<line>: <what>`."""


MEANINGFUL = frozenset({
    "_lease_admission_gate", "_lease_acquire", "_lease_acquire_many",
    "_rdm_claim", "_rdm_refuse", "HTTPException", "reason", "admitted",
    "db", "ctx", "text", "_refused", "_refuse_attempt", "_open_replay",
})

# --- FROZEN (generated once at a30d37f6, 2026-11-02T18:11:21Z, by the round-7 gg
# generator from the real walks; nothing added by hand; never regenerated) ---
SHAPES = frozenset({
    '<root>>Assign(targets=[Name],value=Await,type_comment=-)',
    '<root>>Assign(targets=[Name],value=Call,type_comment=-)',
    '<root>>Assign(targets=[Tuple],value=Await,type_comment=-)',
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|For|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|If],decorator_list=[],returns=-,type_comment=-,type_params=[])',
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|If],decorator_list=[],returns=Constant,type_comment=-,type_params=[])',
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|Expr|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Assign|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr],decorator_list=[],returns=Constant,type_comment=-,type_params=[])',
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Expr|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',
    '<root>>AsyncFunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',
    '<root>>Expr(value=Constant)',
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Expr|If|Return],decorator_list=[],returns=-,type_comment=-,type_params=[])',
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|If|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',
    '<root>>FunctionDef(name=str,args=arguments,body=[Assign|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',
    '<root>>FunctionDef(name=str,args=arguments,body=[Expr|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',
    '<root>>FunctionDef(name=str,args=arguments,body=[If|Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',
    '<root>>FunctionDef(name=str,args=arguments,body=[Return],decorator_list=[],returns=Name,type_comment=-,type_params=[])',
    '<root>>If(test=BoolOp,body=[Return],orelse=[])',
    '<root>>If(test=Compare,body=[Expr|Raise],orelse=[])',
    '<root>>If(test=Compare,body=[Return],orelse=[])',
    '<root>>If(test=UnaryOp,body=[Assign|Expr|If|Return],orelse=[])',
    '<root>>If(test=UnaryOp,body=[Return],orelse=[])',
    'Assign.targets>Name(id=str,ctx=Store)',
    'Assign.targets>Subscript(value=Name,slice=Constant,ctx=Store)',
    'Assign.targets>Tuple(elts=[Name],ctx=Store)',
    'Assign.value>Await(value=Call)',
    'Assign.value>BinOp(left=Subscript,op=Add,right=Call)',
    'Assign.value>Call(func=Attribute,args=[Constant],keywords=[])',
    'Assign.value>Call(func=Attribute,args=[Name],keywords=[])',
    'Assign.value>Call(func=Attribute,args=[],keywords=[])',
    'Assign.value>Call(func=Name,args=[Attribute],keywords=[])',
    'Assign.value>Call(func=Name,args=[BoolOp],keywords=[])',
    'Assign.value>Call(func=Name,args=[Name],keywords=[])',
    'Assign.value>Call(func=Name,args=[SetComp],keywords=[])',
    'Assign.value>Constant(value=int)',
    'Assign.value>Dict(keys=[Constant],values=[Call|Constant|Name])',
    'Assign.value>JoinedStr(values=[Constant|FormattedValue])',
    'Assign.value>Subscript(value=Name,slice=Constant,ctx=Load)',
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[Constant])',
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',
    'AsyncFunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[arg],kw_defaults=[NoneType],kwarg=-,defaults=[])',
    'AsyncFunctionDef.body>Assign(targets=[Name],value=Await,type_comment=-)',
    'AsyncFunctionDef.body>Assign(targets=[Name],value=Call,type_comment=-)',
    'AsyncFunctionDef.body>Assign(targets=[Name],value=Dict,type_comment=-)',
    'AsyncFunctionDef.body>Assign(targets=[Name],value=JoinedStr,type_comment=-)',
    'AsyncFunctionDef.body>Expr(value=Await)',
    'AsyncFunctionDef.body>Expr(value=Call)',
    'AsyncFunctionDef.body>Expr(value=Constant)',
    'AsyncFunctionDef.body>For(target=Name,iter=Name,body=[Expr],orelse=[],type_comment=-)',
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Expr],orelse=[])',
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Raise],orelse=[])',
    'AsyncFunctionDef.body>If(test=BoolOp,body=[Return],orelse=[])',
    'AsyncFunctionDef.body>If(test=Compare,body=[Assign],orelse=[])',
    'AsyncFunctionDef.body>If(test=Compare,body=[Expr],orelse=[Expr])',
    'AsyncFunctionDef.body>If(test=Compare,body=[Expr|Raise],orelse=[])',
    'AsyncFunctionDef.body>If(test=Compare,body=[Expr|Return],orelse=[])',
    'AsyncFunctionDef.body>If(test=Compare,body=[Raise],orelse=[])',
    'AsyncFunctionDef.body>If(test=Compare,body=[Return],orelse=[])',
    'AsyncFunctionDef.body>If(test=Name,body=[AugAssign],orelse=[])',
    'AsyncFunctionDef.body>If(test=Name,body=[Expr],orelse=[])',
    'AsyncFunctionDef.body>If(test=UnaryOp,body=[Expr|Return],orelse=[])',
    'AsyncFunctionDef.body>If(test=UnaryOp,body=[Return],orelse=[])',
    'AsyncFunctionDef.body>Return(value=Call)',
    'AsyncFunctionDef.body>Return(value=Compare)',
    'AsyncFunctionDef.body>Return(value=Constant)',
    'AsyncFunctionDef.body>Return(value=Dict)',
    'AsyncFunctionDef.body>Return(value=DictComp)',
    'AsyncFunctionDef.body>Return(value=Name)',
    'AsyncFunctionDef.returns>Constant(value=NoneType)',
    'AsyncFunctionDef.returns>Name(id=str,ctx=Load)',
    'Attribute.ctx>Load()',
    "Attribute.value>Attribute(value=Name,attr='db',ctx=Load)",
    "Attribute.value>Attribute(value=Name,attr='prints',ctx=Load)",
    'Attribute.value>Await(value=Call)',
    'Attribute.value>BinOp(left=Subscript,op=Sub,right=Name)',
    'Attribute.value>Call(func=Attribute,args=[],keywords=[])',
    'Attribute.value>Name(id=str,ctx=Load)',
    'Attribute.value>Subscript(value=Name,slice=Constant,ctx=Load)',
    'AugAssign.op>Add()',
    'AugAssign.target>Name(id=str,ctx=Store)',
    'AugAssign.value>Constant(value=str)',
    'Await.value>Call(func=Attribute,args=[Call],keywords=[])',
    'Await.value>Call(func=Attribute,args=[Call|Dict],keywords=[])',
    'Await.value>Call(func=Attribute,args=[],keywords=[])',
    'Await.value>Call(func=Name,args=[Attribute],keywords=[])',
    'Await.value>Call(func=Name,args=[Attribute|Call|Constant|Subscript],keywords=[])',
    'Await.value>Call(func=Name,args=[Attribute|Constant|List],keywords=[])',
    'Await.value>Call(func=Name,args=[Attribute|Constant|List|Name],keywords=[keyword])',
    'Await.value>Call(func=Name,args=[Attribute|Constant|Name],keywords=[])',
    'Await.value>Call(func=Name,args=[Attribute|Name],keywords=[])',
    'Await.value>Call(func=Name,args=[Attribute|Name|Subscript],keywords=[])',
    'Await.value>Call(func=Name,args=[BinOp|Constant|Name],keywords=[])',
    'Await.value>Call(func=Name,args=[Call|Constant|Name|Subscript],keywords=[])',
    'Await.value>Call(func=Name,args=[Constant|ListComp|Name],keywords=[])',
    'Await.value>Call(func=Name,args=[Constant|ListComp|Name],keywords=[keyword])',
    'Await.value>Call(func=Name,args=[Constant|ListComp|Name|Subscript],keywords=[])',
    'Await.value>Call(func=Name,args=[Constant|List|Name],keywords=[])',
    'Await.value>Call(func=Name,args=[Constant|List|Name],keywords=[keyword])',
    'Await.value>Call(func=Name,args=[Constant|Name],keywords=[])',
    'Await.value>Call(func=Name,args=[Constant|Name],keywords=[keyword])',
    'Await.value>Call(func=Name,args=[Dict|Name],keywords=[])',
    'Await.value>Call(func=Name,args=[List|Name],keywords=[keyword])',
    'Await.value>Call(func=Name,args=[List|Name|Subscript],keywords=[keyword])',
    'Await.value>Call(func=Name,args=[Name],keywords=[])',
    'Await.value>Call(func=Name,args=[Name],keywords=[keyword])',
    'Await.value>Call(func=Name,args=[Name|Subscript],keywords=[])',
    'Await.value>Call(func=Name,args=[Name|Tuple],keywords=[])',
    'BinOp.left>Name(id=str,ctx=Load)',
    'BinOp.left>Subscript(value=Name,slice=Constant,ctx=Load)',
    'BinOp.op>Add()',
    'BinOp.op>BitOr()',
    'BinOp.op>Sub()',
    'BinOp.right>Call(func=Name,args=[],keywords=[keyword])',
    'BinOp.right>Constant(value=NoneType)',
    'BinOp.right>Name(id=str,ctx=Load)',
    'BoolOp.op>And()',
    'BoolOp.op>Or()',
    'BoolOp.values>BoolOp(op=And,values=[Compare])',
    'BoolOp.values>Call(func=Attribute,args=[Constant],keywords=[])',
    'BoolOp.values>Compare(left=Call,ops=[Is],comparators=[Constant])',
    'BoolOp.values>Compare(left=Call,ops=[NotEq],comparators=[Call])',
    'BoolOp.values>Compare(left=Call,ops=[NotEq],comparators=[Name])',
    'BoolOp.values>Compare(left=Name,ops=[In],comparators=[Call])',
    'BoolOp.values>Compare(left=Name,ops=[IsNot],comparators=[Constant])',
    'BoolOp.values>Compare(left=Name,ops=[Is],comparators=[Constant])',
    'BoolOp.values>Compare(left=Name,ops=[LtE],comparators=[Name])',
    'BoolOp.values>Compare(left=Name,ops=[Lt],comparators=[Name])',
    'BoolOp.values>Compare(left=Subscript,ops=[IsNot],comparators=[Constant])',
    'BoolOp.values>Compare(left=Subscript,ops=[Is],comparators=[Constant])',
    'BoolOp.values>Compare(left=Subscript,ops=[NotEq],comparators=[Attribute])',
    'BoolOp.values>Compare(left=Subscript,ops=[NotEq],comparators=[Constant])',
    'BoolOp.values>Constant(value=int)',
    'BoolOp.values>Constant(value=str)',
    'BoolOp.values>List(elts=[],ctx=Load)',
    'BoolOp.values>Name(id=str,ctx=Load)',
    'BoolOp.values>Subscript(value=Attribute,slice=Constant,ctx=Load)',
    'BoolOp.values>Subscript(value=Name,slice=Constant,ctx=Load)',
    "Call.args>Attribute(value=Name,attr='db',ctx=Load)",
    "Call.args>Attribute(value=Name,attr='game_id',ctx=Load)",
    "Call.args>Attribute(value=Name,attr='held_steam_id',ctx=Load)",
    "Call.args>Attribute(value=Name,attr='id',ctx=Load)",
    "Call.args>Attribute(value=Name,attr='lid',ctx=Load)",
    "Call.args>Attribute(value=Name,attr='lobby',ctx=Load)",
    "Call.args>Attribute(value=Name,attr='n',ctx=Load)",
    "Call.args>Attribute(value=Name,attr='now',ctx=Load)",
    "Call.args>Attribute(value=Name,attr='opener_steam_id',ctx=Load)",
    "Call.args>Attribute(value=Name,attr='request_id',ctx=Load)",
    "Call.args>Attribute(value=Name,attr='steam_id',ctx=Load)",
    'Call.args>BinOp(left=Name,op=Add,right=Name)',
    'Call.args>BoolOp(op=And,values=[Call|Compare])',
    'Call.args>BoolOp(op=Or,values=[Constant|Name])',
    'Call.args>BoolOp(op=Or,values=[Constant|Subscript])',
    'Call.args>BoolOp(op=Or,values=[List|Subscript])',
    'Call.args>Call(func=Attribute,args=[Name],keywords=[])',
    'Call.args>Call(func=Attribute,args=[],keywords=[])',
    'Call.args>Call(func=Name,args=[Attribute|JoinedStr],keywords=[])',
    'Call.args>Call(func=Name,args=[Call],keywords=[])',
    'Call.args>Call(func=Name,args=[Constant],keywords=[])',
    'Call.args>Call(func=Name,args=[Name],keywords=[])',
    'Call.args>Constant(value=NoneType)',
    'Call.args>Constant(value=int)',
    'Call.args>Constant(value=str)',
    'Call.args>Dict(keys=[Constant],values=[Attribute|Call|IfExp|Name])',
    'Call.args>Dict(keys=[Constant],values=[Attribute|Call|Name])',
    'Call.args>Dict(keys=[Constant],values=[Attribute|Call|Name|Subscript])',
    'Call.args>Dict(keys=[Constant],values=[Attribute|Call|Subscript])',
    'Call.args>Dict(keys=[Constant],values=[Attribute|Name])',
    'Call.args>Dict(keys=[Constant],values=[Attribute|Subscript])',
    'Call.args>Dict(keys=[Constant],values=[Call])',
    'Call.args>Dict(keys=[Constant],values=[Call|Name])',
    'Call.args>Dict(keys=[Constant],values=[Compare|Constant])',
    'Call.args>Dict(keys=[Constant],values=[Constant])',
    'Call.args>Dict(keys=[Constant],values=[Name])',
    'Call.args>Dict(keys=[Constant],values=[Subscript])',
    'Call.args>JoinedStr(values=[Constant|FormattedValue])',
    'Call.args>List(elts=[Attribute|Subscript],ctx=Load)',
    'Call.args>List(elts=[Name],ctx=Load)',
    'Call.args>List(elts=[Name|Subscript],ctx=Load)',
    'Call.args>ListComp(elt=Subscript,generators=[comprehension])',
    'Call.args>Name(id=str,ctx=Load)',
    'Call.args>SetComp(elt=Call,generators=[comprehension])',
    'Call.args>Subscript(value=Name,slice=Constant,ctx=Load)',
    'Call.args>Tuple(elts=[Attribute],ctx=Load)',
    "Call.func>Attribute(value=Attribute,attr='append',ctx=Load)",
    "Call.func>Attribute(value=Attribute,attr='execute',ctx=Load)",
    "Call.func>Attribute(value=Await,attr='mappings',ctx=Load)",
    "Call.func>Attribute(value=Await,attr='scalar',ctx=Load)",
    "Call.func>Attribute(value=BinOp,attr='total_seconds',ctx=Load)",
    "Call.func>Attribute(value=Call,attr='all',ctx=Load)",
    "Call.func>Attribute(value=Call,attr='first',ctx=Load)",
    "Call.func>Attribute(value=Name,attr='ceil',ctx=Load)",
    "Call.func>Attribute(value=Name,attr='commit',ctx=Load)",
    "Call.func>Attribute(value=Name,attr='execute',ctx=Load)",
    "Call.func>Attribute(value=Name,attr='get',ctx=Load)",
    "Call.func>Attribute(value=Name,attr='log',ctx=Load)",
    "Call.func>Attribute(value=Name,attr='mappings',ctx=Load)",
    "Call.func>Attribute(value=Name,attr='rollback',ctx=Load)",
    "Call.func>Attribute(value=Name,attr='seat_of',ctx=Load)",
    "Call.func>Attribute(value=Name,attr='update',ctx=Load)",
    "Call.func>Attribute(value=Subscript,attr='isoformat',ctx=Load)",
    'Call.func>Name(id=str,ctx=Load)',
    "Call.keywords>keyword(arg='allowed_group_ids',value=Name)",
    "Call.keywords>keyword(arg='allowed_group_ids',value=Tuple)",
    "Call.keywords>keyword(arg='allowed_hold_ids',value=IfExp)",
    "Call.keywords>keyword(arg='allowed_hold_ids',value=Name)",
    "Call.keywords>keyword(arg='allowed_hold_ids',value=Tuple)",
    "Call.keywords>keyword(arg='allowed_keys',value=Name)",
    "Call.keywords>keyword(arg='allowed_keys',value=Tuple)",
    "Call.keywords>keyword(arg='depart',value=Constant)",
    "Call.keywords>keyword(arg='detail',value=Constant)",
    "Call.keywords>keyword(arg='hold_entry_bound_seconds',value=Name)",
    "Call.keywords>keyword(arg='lock',value=Constant)",
    "Call.keywords>keyword(arg='seconds',value=Name)",
    "Call.keywords>keyword(arg='status_code',value=Constant)",
    "Call.keywords>keyword(arg='strict_team_ovt_queue',value=Constant)",
    "Call.keywords>keyword(arg='strict_team_ovt_queue',value=Name)",
    "Compare.comparators>Attribute(value=Name,attr='lid',ctx=Load)",
    "Compare.comparators>Attribute(value=Name,attr='now',ctx=Load)",
    'Compare.comparators>Call(func=Name,args=[BoolOp],keywords=[])',
    'Compare.comparators>Call(func=Name,args=[Name],keywords=[])',
    'Compare.comparators>Constant(value=NoneType)',
    'Compare.comparators>Constant(value=bool)',
    'Compare.comparators>Constant(value=str)',
    'Compare.comparators>Name(id=str,ctx=Load)',
    'Compare.comparators>Tuple(elts=[Attribute|Name],ctx=Load)',
    'Compare.comparators>Tuple(elts=[Constant],ctx=Load)',
    "Compare.left>Attribute(value=Name,attr='step',ctx=Load)",
    'Compare.left>Await(value=Call)',
    'Compare.left>BoolOp(op=Or,values=[Constant|Name])',
    'Compare.left>Call(func=Attribute,args=[Attribute],keywords=[])',
    'Compare.left>Call(func=Attribute,args=[Constant],keywords=[])',
    'Compare.left>Call(func=Name,args=[Name],keywords=[])',
    'Compare.left>Call(func=Name,args=[Subscript],keywords=[])',
    'Compare.left>Name(id=str,ctx=Load)',
    'Compare.left>Subscript(value=Attribute,slice=Constant,ctx=Load)',
    'Compare.left>Subscript(value=Name,slice=Constant,ctx=Load)',
    'Compare.left>Tuple(elts=[Subscript],ctx=Load)',
    'Compare.ops>Eq()',
    'Compare.ops>In()',
    'Compare.ops>Is()',
    'Compare.ops>IsNot()',
    'Compare.ops>Lt()',
    'Compare.ops>LtE()',
    'Compare.ops>NotEq()',
    'Dict.keys>Constant(value=str)',
    "Dict.values>Attribute(value=Name,attr='lid',ctx=Load)",
    "Dict.values>Attribute(value=Name,attr='now',ctx=Load)",
    "Dict.values>Attribute(value=Name,attr='request_id',ctx=Load)",
    "Dict.values>Attribute(value=Name,attr='step',ctx=Load)",
    'Dict.values>Call(func=Name,args=[Attribute],keywords=[])',
    'Dict.values>Call(func=Name,args=[Attribute|Name],keywords=[])',
    'Dict.values>Call(func=Name,args=[BoolOp],keywords=[])',
    'Dict.values>Call(func=Name,args=[Name],keywords=[])',
    'Dict.values>Call(func=Name,args=[Subscript],keywords=[])',
    'Dict.values>Compare(left=Subscript,ops=[Eq],comparators=[Constant])',
    'Dict.values>Constant(value=NoneType)',
    'Dict.values>Constant(value=int)',
    'Dict.values>Constant(value=str)',
    'Dict.values>Dict(keys=[Constant],values=[Attribute|Call|Constant])',
    'Dict.values>IfExp(test=Compare,body=Subscript,orelse=Constant)',
    'Dict.values>IfExp(test=Name,body=Call,orelse=Constant)',
    'Dict.values>IfExp(test=Name,body=Subscript,orelse=Constant)',
    'Dict.values>Name(id=str,ctx=Load)',
    'Dict.values>Subscript(value=Name,slice=Constant,ctx=Load)',
    'DictComp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',
    'DictComp.key>Subscript(value=Name,slice=Constant,ctx=Load)',
    'DictComp.value>Subscript(value=Name,slice=Constant,ctx=Load)',
    'Expr.value>Await(value=Call)',
    'Expr.value>Call(func=Attribute,args=[Call],keywords=[])',
    'Expr.value>Call(func=Attribute,args=[Dict],keywords=[])',
    'Expr.value>Call(func=Attribute,args=[JoinedStr],keywords=[])',
    'Expr.value>Constant(value=str)',
    'For.body>Expr(value=Await)',
    'For.iter>Name(id=str,ctx=Load)',
    'For.target>Name(id=str,ctx=Store)',
    'FormattedValue.value>Call(func=Name,args=[Name],keywords=[])',
    'FormattedValue.value>IfExp(test=Name,body=Constant,orelse=Constant)',
    'FormattedValue.value>Name(id=str,ctx=Load)',
    'FormattedValue.value>Subscript(value=Name,slice=Constant,ctx=Load)',
    'FunctionDef.args>arguments(posonlyargs=[],args=[arg],vararg=-,kwonlyargs=[],kw_defaults=[],kwarg=-,defaults=[])',
    'FunctionDef.body>Assign(targets=[Name],value=Call,type_comment=-)',
    'FunctionDef.body>Assign(targets=[Name],value=Subscript,type_comment=-)',
    'FunctionDef.body>Expr(value=Constant)',
    'FunctionDef.body>If(test=BoolOp,body=[Assign|If],orelse=[])',
    'FunctionDef.body>If(test=Compare,body=[Return],orelse=[])',
    'FunctionDef.body>If(test=UnaryOp,body=[Return],orelse=[])',
    'FunctionDef.body>Return(value=Call)',
    'FunctionDef.body>Return(value=Compare)',
    'FunctionDef.body>Return(value=Constant)',
    'FunctionDef.body>Return(value=Dict)',
    'FunctionDef.body>Return(value=IfExp)',
    'FunctionDef.body>Return(value=JoinedStr)',
    'FunctionDef.body>Return(value=Subscript)',
    'FunctionDef.returns>Name(id=str,ctx=Load)',
    'If.body>Assign(targets=[Name],value=Await,type_comment=-)',
    'If.body>Assign(targets=[Name],value=BinOp,type_comment=-)',
    'If.body>Assign(targets=[Subscript],value=Constant,type_comment=-)',
    'If.body>AugAssign(target=Name,op=Add,value=Constant)',
    'If.body>Expr(value=Await)',
    'If.body>If(test=BoolOp,body=[Return],orelse=[])',
    'If.body>If(test=Compare,body=[Raise],orelse=[])',
    'If.body>If(test=UnaryOp,body=[Return],orelse=[])',
    'If.body>Raise(exc=Call,cause=-)',
    'If.body>Return(value=Await)',
    'If.body>Return(value=Call)',
    'If.body>Return(value=Constant)',
    'If.body>Return(value=Dict)',
    'If.body>Return(value=IfExp)',
    'If.body>Return(value=Name)',
    'If.body>Return(value=Tuple)',
    'If.orelse>Expr(value=Await)',
    'If.test>BoolOp(op=And,values=[Compare])',
    'If.test>BoolOp(op=And,values=[Compare|Name])',
    'If.test>BoolOp(op=Or,values=[BoolOp])',
    'If.test>BoolOp(op=Or,values=[Compare])',
    'If.test>Compare(left=Attribute,ops=[Eq],comparators=[Constant])',
    'If.test>Compare(left=Await,ops=[Is],comparators=[Constant])',
    'If.test>Compare(left=Call,ops=[Is],comparators=[Constant])',
    'If.test>Compare(left=Name,ops=[Eq],comparators=[Constant])',
    'If.test>Compare(left=Name,ops=[IsNot],comparators=[Constant])',
    'If.test>Compare(left=Name,ops=[Is],comparators=[Constant])',
    'If.test>Compare(left=Name,ops=[LtE],comparators=[Name])',
    'If.test>Compare(left=Subscript,ops=[Eq],comparators=[Constant])',
    'If.test>Compare(left=Subscript,ops=[IsNot],comparators=[Constant])',
    'If.test>Compare(left=Subscript,ops=[LtE],comparators=[Attribute])',
    'If.test>Compare(left=Subscript,ops=[NotEq],comparators=[Constant])',
    'If.test>Name(id=str,ctx=Load)',
    'If.test>UnaryOp(op=Not,operand=Await)',
    'If.test>UnaryOp(op=Not,operand=Call)',
    'If.test>UnaryOp(op=Not,operand=Name)',
    'IfExp.body>BoolOp(op=Or,values=[Constant|Name])',
    'IfExp.body>Call(func=Attribute,args=[],keywords=[])',
    'IfExp.body>Call(func=Name,args=[Name],keywords=[])',
    'IfExp.body>Constant(value=int)',
    'IfExp.body>Constant(value=str)',
    'IfExp.body>Subscript(value=Name,slice=Constant,ctx=Load)',
    'IfExp.body>Tuple(elts=[Name],ctx=Load)',
    'IfExp.orelse>Constant(value=NoneType)',
    'IfExp.orelse>Constant(value=int)',
    'IfExp.orelse>Constant(value=str)',
    'IfExp.orelse>Tuple(elts=[],ctx=Load)',
    'IfExp.test>Compare(left=BoolOp,ops=[In],comparators=[Name])',
    'IfExp.test>Compare(left=Name,ops=[In],comparators=[Tuple])',
    'IfExp.test>Compare(left=Name,ops=[IsNot],comparators=[Constant])',
    'IfExp.test>Compare(left=Subscript,ops=[Eq],comparators=[Constant])',
    'IfExp.test>Name(id=str,ctx=Load)',
    'JoinedStr.values>Constant(value=str)',
    'JoinedStr.values>FormattedValue(value=Call,conversion=-1,format_spec=-)',
    'JoinedStr.values>FormattedValue(value=IfExp,conversion=-1,format_spec=-)',
    'JoinedStr.values>FormattedValue(value=Name,conversion=-1,format_spec=-)',
    'JoinedStr.values>FormattedValue(value=Subscript,conversion=-1,format_spec=-)',
    'List.ctx>Load()',
    "List.elts>Attribute(value=Name,attr='id',ctx=Load)",
    'List.elts>Name(id=str,ctx=Load)',
    'List.elts>Subscript(value=Name,slice=Constant,ctx=Load)',
    'ListComp.elt>Subscript(value=Name,slice=Constant,ctx=Load)',
    'ListComp.elt>Subscript(value=Name,slice=Name,ctx=Load)',
    'ListComp.generators>comprehension(target=Name,iter=BinOp,ifs=[],is_async=0)',
    'ListComp.generators>comprehension(target=Name,iter=Name,ifs=[],is_async=0)',
    'Name.ctx>Load()',
    'Name.ctx>Store()',
    'Raise.exc>Call(func=Name,args=[Constant],keywords=[])',
    'Raise.exc>Call(func=Name,args=[],keywords=[keyword])',
    'Return.value>Await(value=Call)',
    'Return.value>Call(func=Attribute,args=[],keywords=[])',
    'Return.value>Call(func=Name,args=[BoolOp],keywords=[])',
    'Return.value>Call(func=Name,args=[Call|Constant],keywords=[])',
    'Return.value>Call(func=Name,args=[Constant],keywords=[])',
    'Return.value>Call(func=Name,args=[Name],keywords=[])',
    'Return.value>Call(func=Name,args=[Subscript],keywords=[])',
    'Return.value>Compare(left=Call,ops=[Is],comparators=[Constant])',
    'Return.value>Compare(left=Name,ops=[IsNot],comparators=[Constant])',
    'Return.value>Compare(left=Tuple,ops=[Eq],comparators=[Tuple])',
    'Return.value>Constant(value=NoneType)',
    'Return.value>Constant(value=bool)',
    'Return.value>Constant(value=int)',
    'Return.value>Constant(value=str)',
    'Return.value>Dict(keys=[Constant],values=[Call|IfExp|Name|Subscript])',
    'Return.value>Dict(keys=[Constant],values=[Constant|Name])',
    'Return.value>Dict(keys=[Constant],values=[Dict])',
    'Return.value>Dict(keys=[Constant],values=[Name])',
    'Return.value>Dict(keys=[],values=[])',
    'Return.value>DictComp(key=Subscript,value=Subscript,generators=[comprehension])',
    'Return.value>IfExp(test=Compare,body=BoolOp,orelse=Constant)',
    'Return.value>IfExp(test=Compare,body=Constant,orelse=Constant)',
    'Return.value>JoinedStr(values=[Constant|FormattedValue])',
    'Return.value>Name(id=str,ctx=Load)',
    'Return.value>Subscript(value=Call,slice=Slice,ctx=Load)',
    'Return.value>Tuple(elts=[Constant|Name],ctx=Load)',
    'Return.value>Tuple(elts=[Subscript],ctx=Load)',
    'SetComp.elt>Call(func=Name,args=[Name],keywords=[])',
    'SetComp.generators>comprehension(target=Name,iter=Name,ifs=[Compare],is_async=0)',
    'Slice.upper>Constant(value=int)',
    'Subscript.ctx>Load()',
    'Subscript.ctx>Store()',
    'Subscript.slice>Constant(value=int)',
    'Subscript.slice>Constant(value=str)',
    'Subscript.slice>Name(id=str,ctx=Load)',
    'Subscript.slice>Slice(lower=-,upper=Constant,step=-)',
    "Subscript.value>Attribute(value=Name,attr='lobby',ctx=Load)",
    'Subscript.value>Call(func=Name,args=[Name],keywords=[])',
    'Subscript.value>Name(id=str,ctx=Load)',
    'Tuple.ctx>Load()',
    'Tuple.ctx>Store()',
    "Tuple.elts>Attribute(value=Name,attr='game_id',ctx=Load)",
    "Tuple.elts>Attribute(value=Name,attr='held_steam_id',ctx=Load)",
    "Tuple.elts>Attribute(value=Name,attr='id',ctx=Load)",
    "Tuple.elts>Attribute(value=Name,attr='opener_steam_id',ctx=Load)",
    'Tuple.elts>Constant(value=NoneType)',
    'Tuple.elts>Constant(value=str)',
    'Tuple.elts>Name(id=str,ctx=Load)',
    'Tuple.elts>Name(id=str,ctx=Store)',
    'Tuple.elts>Subscript(value=Name,slice=Constant,ctx=Load)',
    'Tuple.elts>Tuple(elts=[Attribute|Constant],ctx=Load)',
    'Tuple.elts>Tuple(elts=[Constant],ctx=Load)',
    'UnaryOp.op>Not()',
    'UnaryOp.operand>Await(value=Call)',
    'UnaryOp.operand>Call(func=Name,args=[Name],keywords=[])',
    'UnaryOp.operand>Name(id=str,ctx=Load)',
    'arg.annotation>BinOp(left=Name,op=BitOr,right=Constant)',
    'arg.annotation>Name(id=str,ctx=Load)',
    'arguments.args>arg(arg=str,annotation=-,type_comment=-)',
    'arguments.args>arg(arg=str,annotation=BinOp,type_comment=-)',
    'arguments.args>arg(arg=str,annotation=Name,type_comment=-)',
    'arguments.defaults>Constant(value=NoneType)',
    'arguments.defaults>Constant(value=bool)',
    'arguments.kwonlyargs>arg(arg=str,annotation=Name,type_comment=-)',
    'comprehension.ifs>Compare(left=Name,ops=[IsNot],comparators=[Constant])',
    'comprehension.iter>BinOp(left=Name,op=Add,right=Name)',
    'comprehension.iter>Name(id=str,ctx=Load)',
    'comprehension.target>Name(id=str,ctx=Store)',
    'keyword.value>Constant(value=bool)',
    'keyword.value>Constant(value=int)',
    'keyword.value>Constant(value=str)',
    'keyword.value>IfExp(test=Compare,body=Tuple,orelse=Tuple)',
    'keyword.value>Name(id=str,ctx=Load)',
    'keyword.value>Tuple(elts=[Name],ctx=Load)',
    'keyword.value>Tuple(elts=[Subscript],ctx=Load)',
    'keyword.value>Tuple(elts=[Tuple],ctx=Load)',
})
ANCESTORS = frozenset({
    'AsyncFunctionDef.body>Assign',
    'AsyncFunctionDef.body>Expr',
    'AsyncFunctionDef.body>For',
    'AsyncFunctionDef.body>If',
    'For.body>If',
    'If.body>Assign',
    'If.body>If',
})
BINDINGS = {
    'answer': {
        ('_open_replay', 'def'): 1,
        ('_refuse_attempt', 'def'): 1,
        ('_refused', 'def'): 1,
        ('db', 'parameter'): 1,
        ('reason', 'parameter'): 1,
    },
    'helper': {
        ('_rdm_refuse', 'def'): 1,
        ('_refused', 'def'): 1,
        ('ctx', 'parameter'): 1,
        ('db', 'parameter'): 1,
        ('reason', 'parameter'): 1,
    },
    'site': {
        ('_lease_acquire', 'def'): 1,
        ('_lease_acquire', 'import'): 1,
        ('_lease_acquire_many', 'def'): 1,
        ('_lease_admission_gate', 'import'): 1,
        ('_rdm_claim', 'def'): 1,
        ('admitted', 'store'): 1,
        ('ctx', 'parameter'): 1,
        ('db', 'parameter'): 1,
        ('reason', 'parameter'): 1,
        ('reason', 'store'): 7,
    },
}
IMPORTS = frozenset({
    ('from', 'main', 0, (('_lease_acquire', None), ('_lease_admission_gate', None), ('LEASE_TTL_ASSEMBLY', None))),
    ('from', 'main', 0, (('_lease_admission_gate', None), ('_lease_release', None))),
    ('import', None, 0, (('uuid', 'uuid_mod'),)),
})
# --- END FROZEN ---


def callees(nodes):
    """The plain-name callees under `nodes` (a list of trees)."""
    return frozenset(n.func.id for root in nodes for n in ast.walk(root)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name))


def import_key(n):
    """An import statement's exact text, as IMPORTS holds it."""
    if isinstance(n, ast.ImportFrom):
        return ("from", n.module, n.level,
                tuple((a.name, a.asname) for a in n.names))
    return ("import", None, 0, tuple((a.name, a.asname) for a in n.names))


def path_to(fn, target):
    """[(node, parent, field)] from fn's own statements down to `target`
    (target included), through statements and their handlers and cases
    only; None when target is not a statement under fn."""
    for f, v in ast.iter_fields(fn):
        for c in (v if isinstance(v, list) else [v]):
            if c is target:
                return [(c, fn, f)]
            if isinstance(c, ast.AST) and not isinstance(c, ast.expr):
                sub = path_to(c, target)
                if sub:
                    return [(c, fn, f)] + sub
    return None


def ancestor_shape(node, parent, field):
    return f"{type(parent).__name__}.{field}>{type(node).__name__}"


def nodes(root, filename, offset, record=None):
    """Check every node under `root` against SHAPES (shape_grammar.check);
    the node count. With `record` (the generator), collect instead."""
    if record is not None:
        record["shapes"].update(_sg.shape(n, p, f) for n, p, f in _sg.visit(root))
        return len(_sg.visit(root))
    try:
        return _sg.check(root, SHAPES, filename)
    except _sg.Refused as e:
        f, line, shape = e.args[0]
        raise Refusal(f"grammar {f}:{line + offset}: {shape}") from None


def binding_problems(fn, role, meaningful, filename, offset, record=None):
    """[(file, line, what)] of the binding rule over the whole function fn:
    a meaningful spelling bound other than as a frozen (spelling, how) pair
    of `role` (shape_grammar.binding_refusals), or more times than frozen;
    and any import statement that is not exactly a frozen one."""
    counts, first = collections.Counter(), {}
    for ln, s, how in _sg.bindings(fn):
        if s in meaningful:
            counts[(s, how)] += 1
            first.setdefault((s, how), ln)
    imports = [n for n in ast.walk(fn) if isinstance(n, (ast.Import, ast.ImportFrom))]
    if record is not None:
        seen = record["bindings"].setdefault(role, {})
        for k, c in counts.items():
            seen[k] = max(seen.get(k, 0), c)
        record["imports"].update(import_key(n) for n in imports)
        return []
    allowed = BINDINGS.get(role, {})
    out = [(f, ln + offset, what) for f, ln, what in _sg.binding_refusals(
        fn, meaningful, frozenset(allowed), filename)]
    for k, c in sorted(counts.items()):
        if k in allowed and c > allowed[k]:
            out.append((filename, first[k] + offset,
                        f"binds {k[0]} ({k[1]}) {c} times, frozen at most {allowed[k]}"))
    for n in imports:
        if import_key(n) not in IMPORTS:
            out.append((filename, n.lineno + offset,
                        f"an import outside the frozen imports: {import_key(n)}"))
    return out


def _bind(fn, role, span, filename, offset, record):
    problems = binding_problems(fn, role, MEANINGFUL | callees(span), filename,
                                offset, record)
    if problems:
        f, line, what = problems[0]
        raise Refusal(f"binding {f}:{line}: {what}")


def check_body(d, role, filename, offset, record=None):
    """A function body a walk descends into, whole: every node, then the
    binding rule; the node count."""
    n = nodes(d, filename, offset, record)
    _bind(d, role, [d], filename, offset, record)
    return n


def check_site(fn, stmts, filename, offset, record=None):
    """A site span: the statements `stmts` (siblings) of function fn. The
    ancestor shapes from fn down to stmts[0], each statement whole, then the
    binding rule over fn whole; the node count (ancestors included)."""
    path = path_to(fn, stmts[0])
    if path is None:
        raise Refusal(f"grammar {filename}:?: the span is not a statement of its function")
    count = 0
    for node, parent, field in path:
        s = ancestor_shape(node, parent, field)
        count += 1
        if record is not None:
            record["ancestors"].add(s)
        elif s not in ANCESTORS:
            raise Refusal(f"grammar {filename}:{node.lineno + offset}: {s}")
    for st in stmts:
        count += nodes(st, filename, offset, record)
    _bind(fn, "site", stmts, filename, offset, record)
    return count


def prefix_span(fn, stop):
    """fn's statements from the first to the first one holding a call of the
    plain name `stop` (included); all of them when none does."""
    out = []
    for st in fn.body:
        out.append(st)
        if stop in callees([st]):
            break
    return out
