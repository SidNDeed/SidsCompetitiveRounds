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
import hashlib
import os

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

# Round 8 (ruling REHEARSAL-FOUR-R7-A1, M3): shapes taken OUT of the frozen
# whitelist by hand, each after the real spans were conformed so that none
# uses it (the completeness test re-proves every real refusal list empty).
# Narrowing only: nothing is ever added here or to the literal above.
#   Call.func>Attribute(value=Name,attr='commit')  match_hold.match_hold_open's
#     refusal branch and match_hold._refuse_attempt committed their fresh
#     refusal transaction with `await db.commit()`; both now await
#     match_hold._commit_fresh(db), a function of the module the walks do not
#     descend into (like _attempt, the fresh transaction's own write), so no
#     walked span or body commits by a session method, and finding gate:136's
#     committing refusal is refused by this shape.
NARROWED = frozenset({
    "Call.func>Attribute(value=Name,attr='commit',ctx=Load)",
})
SHAPES = SHAPES - NARROWED

# Round 8 (M6): while set to a list, every node a site span's check admitted
# is appended as (file, line, col, node type) (nodes(), after its check).
ADMITTED = {"sink": None}

# Round 9 (ruling REHEARSAL-R8-A1, G2): two nodes the shapes above leave
# free are bound.
#
# ORDER. A shape is one node's; the order of a span's statements was a
# sentence of the walk (finding gate:1981: `n = int(req.n)` between the
# gate and `if not admitted:` was admitted by every shape and refused only
# by "the gate's answer is not refused at once"). An ADMISSION SPAN is a
# site span whose first statement calls an admission callee (ADMISSION:
# the gate and its two acquirers, by the spellings MEANINGFUL binds); its
# SEQUENCE (sequence()) is the shape of each of its statements in order,
# then the shape of the first statement of its refusal branch (the span's
# last statement when that is an `if`, else "-"). SEQUENCES holds the
# sequences of the real admission spans, one per design form: shared
# (`if (await <acquirer>(...)) is False:` opening with `await
# db.rollback()`), direct, acquirer and hold (the gate's unpacked answer
# followed AT ONCE by `if not admitted:`, opening with its refusal). Any
# other order, an inserted statement included, refuses by the shape at
# which it leaves every frozen sequence.
#
# SQL TEXT. A `text(...)` argument was `Constant(value=str)` whatever the
# statement (finding gate:1808: COMMIT and ROLLBACK as the text of a real
# read were shape-admitted and refused only by "writes before the gate").
# Every call of `text` under a checked node takes exactly one argument: a
# string constant whose value is one of SQL_TEXTS, the complete statements
# the real walked spans and bodies execute (any other value refuses as the
# spelled shape `Call.args>Constant(value=str)#<value>`), or a name of
# SQL_NAMES whose every binding inside the checked node is one of its
# frozen statements (the two real ones: main._rdm_attempt's module
# constant `_RDM_ATTEMPT_SQL`, bound by no statement of the body, and
# match_hold._hold_row's `sql`, bound by its f-string and its `+=`); any
# other argument refuses, naming the name and the binding.
#
# Both literals were taken ONCE from the real walks at effc36c6 by
# RF/r9/gr/gen_gate_r9.py (R9_RECORD) and frozen; each sequence was read
# against its form's design sentence (the walk's docstring). Never
# regenerated: code is conformed to them.
ADMISSION = frozenset({"_lease_admission_gate", "_lease_acquire",
                       "_lease_acquire_many"})
SEQUENCES = frozenset({
    (
        '<root>>Assign(targets=[Tuple],value=Await,type_comment=-)',
        '<root>>If(test=UnaryOp,body=[Assign|Expr|If|Return],orelse=[])',
        'If.body>Expr(value=Await)',
    ),
    (
        '<root>>Assign(targets=[Tuple],value=Await,type_comment=-)',
        '<root>>If(test=UnaryOp,body=[Return],orelse=[])',
        'If.body>Return(value=Await)',
    ),
    (
        '<root>>Assign(targets=[Tuple],value=Await,type_comment=-)',
        '<root>>If(test=UnaryOp,body=[Return],orelse=[])',
        'If.body>Return(value=Constant)',
    ),
    (
        '<root>>If(test=Compare,body=[Expr|Raise],orelse=[])',
        'If.body>Expr(value=Await)',
    ),
})
SQL_TEXTS = frozenset({
    "\n        UPDATE ffa_lobbies\n           SET departed_ids = (SELECT ARRAY(SELECT DISTINCT e FROM unnest(departed_ids || CAST(:pid AS uuid)) e)),\n               departure_causes = CASE WHEN CAST(:cause AS text) = ''\n                                       THEN departure_causes\n                                       ELSE jsonb_build_object(CAST(:pidt AS text),\n                                                               CAST(:cause AS text))\n                                            || departure_causes END\n         WHERE id = :lid AND status = 'active'\n        RETURNING cardinality(departed_ids)\n                  >= COALESCE(player_count, cardinality(member_ids)) - 1\n    ",
    'DELETE FROM ffa_queue WHERE series_id = :lid AND player_id != :pid',
    "DELETE FROM queue_leases WHERE mode = 'ffa' AND group_id = :lid AND player_id != :pid",
    'INSERT INTO match_hold_open_attempts (request_id, room_name, game_id,        held_player_id, opener_player_id, at, outcome, reason, hold_id) VALUES (CAST(:rid AS varchar), CAST(:room AS varchar), CAST(:g AS uuid),         CAST(:held AS uuid), CAST(:opener AS uuid), CAST(:now AS timestamptz),         CAST(:outcome AS varchar), CAST(:reason AS varchar), CAST(:hid AS uuid)) ON CONFLICT (request_id) DO NOTHING RETURNING request_id',
    'SELECT * FROM ffa_seat_readmissions WHERE lobby_id = :lid AND player_id = :pid AND n = CAST(:n AS smallint)',
    'SELECT clock_timestamp()',
    'SELECT id, steam_id FROM players WHERE steam_id = ANY(CAST(:steams AS varchar[])) AND deleted_at IS NULL',
    'SELECT mode, group_id FROM queue_leases WHERE player_id = :pid AND expires_at > CAST(:now AS timestamptz)',
    'SELECT pg_advisory_xact_lock(hashtext(:sid))',
    'SELECT room_name, game_id, held_player_id, opener_player_id, outcome, reason, hold_id  FROM match_hold_open_attempts WHERE request_id = CAST(:rid AS varchar)',
    'SELECT status, series_id FROM ffa_queue WHERE player_id = :pid FOR UPDATE',
    'UPDATE ffa_assembly_seats SET hold_n = NULL, hold_anchor_at = NULL, hold_until = NULL WHERE lobby_id = :lid AND player_id = :pid AND hold_n = CAST(:n AS smallint) RETURNING left_at, left_cause, slot',
    'UPDATE ffa_seat_readmissions SET lapsed_at = CAST(:now AS timestamptz) WHERE lobby_id = :lid AND player_id = :pid AND n = CAST(:n AS smallint)   AND lapsed_at IS NULL AND refused_at IS NULL AND bound_at IS NULL',
    "UPDATE ffa_seat_readmissions SET refused_at = CAST(:now AS timestamptz),       refused_reason = 'declined' WHERE lobby_id = :lid AND player_id = :pid AND n = CAST(:n AS smallint)   AND lapsed_at IS NULL AND refused_at IS NULL AND bound_at IS NULL",
})
SQL_NAMES = {
    '_RDM_ATTEMPT_SQL': frozenset({
    }),
    'sql': frozenset({
        "sql += ' FOR NO KEY UPDATE'",
        "sql = f'SELECT {_HOLD_COLS} FROM match_seat_holds WHERE id = CAST(:hid AS uuid)'",
    }),
}
# The module constants among SQL_NAMES (W30b at the round-9 merge, the gr
# child's question 1): a name the checked body reads but binds nowhere is
# bound in its module, and that binding is frozen too. The module's source
# (read from its file, never imported) must hold exactly ONE binding of the
# name of any kind shape_grammar.bindings reads (store, del, parameter,
# def, import, except, global, nonlocal, match), and it must be a top-level
# `NAME = <one string constant>` whose value is the frozen text; and no
# attribute store of the name and no string constant spelling it (the
# setattr, getattr and globals() routes) anywhere in the module. The value
# was taken once from main.py at 70d7a8e0 by
# RF/r9/tip/bind_module_sql.py and frozen. It does not bound writes from
# other modules (none of the walked code imports main's constants).
MODULE_SQL = {
    '_RDM_ATTEMPT_SQL': ("api/main.py", 'INSERT INTO ffa_readmit_attempts (lobby_id, player_id, n, attempt_no, kind, at, outcome,                                  reason) SELECT CAST(:lid AS uuid), CAST(:pid AS uuid), CAST(:n AS smallint),        COALESCE(MAX(a.attempt_no), 0) + 1, CAST(:kind AS varchar),        CAST(:at AS timestamptz), CAST(:outcome AS varchar), CAST(:reason AS varchar)   FROM ffa_readmit_attempts a  WHERE a.lobby_id = CAST(:lid AS uuid) AND a.player_id = CAST(:pid AS uuid)    AND a.n = CAST(:n AS smallint)'),
}
_MODULE_SQL_SEEN = {}


def module_sql_problem(name, src=None):
    """None, or why the module binding of MODULE_SQL name `name` is not
    exactly its one frozen top-level assignment. `src` replaces the
    module's file text (the controls); results are cached by text digest."""
    rel, want = MODULE_SQL[name]
    if src is None:
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), *rel.split("/"))
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
    key = (name, hashlib.sha256(src.encode("utf-8")).hexdigest())
    if key not in _MODULE_SQL_SEEN:
        _MODULE_SQL_SEEN[key] = _module_sql_problem(name, rel, want, src)
    return _MODULE_SQL_SEEN[key]


def _module_sql_problem(name, rel, want, src):
    tree = ast.parse(src)
    found = [(ln, how) for ln, s, how in _sg.bindings(tree) if s == name]
    if len(found) != 1:
        return f"bound {len(found)} times in {rel}: {found[:3]}"
    top = [st for st in tree.body if isinstance(st, ast.Assign)
           and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)
           and st.targets[0].id == name]
    if len(top) != 1:
        return f"its one binding in {rel} is not a top-level assignment: {found[0]}"
    value = top[0].value
    if not (isinstance(value, ast.Constant) and value.value == want):
        return (f"its {rel} value is not the frozen text: "
                f"{ast.unparse(value)[:60]}")
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr == name:
            return f"{rel}:{n.lineno} names it as an attribute"
        if isinstance(n, ast.Constant) and n.value == name:
            return f"{rel}:{n.lineno} spells it as a string"
    return None


# The one-time generator's sink: while a dict, sequences and texts are
# collected into it and nothing is refused by these two rules.
R9_RECORD = {"sink": None}


def sequence(stmts):
    """The admission-to-refusal sequence of span `stmts`."""
    last = stmts[-1]
    first = "-"
    if isinstance(last, ast.If) and last.body:
        first = _sg.shape(last.body[0], last, "body")
    return tuple(_sg.shape(st) for st in stmts) + (first,)


def sequence_problem(stmts, filename, offset):
    """None, or the refusal of admission span `stmts` whose sequence is
    not a frozen one, naming the line and shape at which it leaves every
    frozen sequence; None for a span that is not an admission span."""
    if not ADMISSION & callees(stmts[:1]):
        return None
    seq = sequence(stmts)
    sink = R9_RECORD.get("sink")
    if sink is not None:
        sink["sequences"].add(seq)
        return None
    if seq in SEQUENCES:
        return None
    at = 0
    while any(s[:at + 1] == seq[:at + 1] for s in SEQUENCES):
        at += 1
    last = stmts[-1]
    nodes_at = list(stmts) + [last.body[0] if isinstance(last, ast.If)
                              and last.body else last]
    line = getattr(nodes_at[min(at, len(nodes_at) - 1)], "lineno", 0) + offset
    return (f"grammar {filename}:{line}: the admission-to-refusal sequence "
            f"at {seq[min(at, len(seq) - 1)]}")


def name_bindings(root, spelling):
    """The frozen form of every binding of `spelling` inside root: the
    text of each statement that stores or deletes it, and `<how>
    <spelling>` for any other binding (a parameter, an import, ...)."""
    parent = {id(n): p for n, p, _f in _sg.visit(root)}
    out = set()
    for n, _p, _f in _sg.visit(root):
        if (isinstance(n, ast.Name) and n.id == spelling
                and not isinstance(n.ctx, ast.Load)):
            st = n
            while st is not None and not isinstance(st, ast.stmt):
                st = parent.get(id(st))
            out.add(ast.unparse(st) if st is not None else spelling)
    for _ln, s, how in _sg.bindings(root):
        if s == spelling and how not in ("store", "del"):
            out.add(f"{how} {s}")
    return frozenset(out)


def sql_problem(root, filename, offset, module_src=None):
    """None, or the refusal of the first call of `text` under root whose
    argument is not exactly one frozen SQL text (SQL_TEXTS) or one frozen
    name bound only by its frozen statements (SQL_NAMES) and, for a module
    constant (MODULE_SQL), by its one frozen module assignment
    (`module_src` replaces the module's text: the controls)."""
    sink = R9_RECORD.get("sink")
    for n, _p, _f in _sg.visit(root):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "text"):
            continue
        arg = n.args[0] if len(n.args) == 1 and not n.keywords else None
        value = arg.value if isinstance(arg, ast.Constant) else None
        name = arg.id if isinstance(arg, ast.Name) else None
        if sink is not None:
            if isinstance(value, str):
                sink["texts"].add(value)
            elif name is not None:
                sink["names"].setdefault(name, set()).update(
                    name_bindings(root, name))
            else:
                sink["texts"].add(None)
            continue
        if isinstance(value, str) and value in SQL_TEXTS:
            continue
        if name is not None and name in SQL_NAMES:
            extra = sorted(name_bindings(root, name) - SQL_NAMES[name])
            mod = None
            if not extra and name in MODULE_SQL:
                mod = module_sql_problem(name, module_src)
            if not extra and mod is None:
                continue
            what = (f"Call.args>Name(id=str,ctx=Load)#{name} {mod}" if mod else
                    f"Call.args>Name(id=str,ctx=Load)#{name} bound by an "
                    f"unlisted statement: {extra[0][:80]}")
        elif name is not None:
            what = f"Call.args>Name(id=str,ctx=Load)#{name}"
        elif isinstance(value, str):
            what = f"Call.args>Constant(value=str)#{value!r}"
        else:
            what = (f"a text() argument that is not one string constant "
                    f"or frozen name: {ast.unparse(n)[:60]}")
        return f"grammar {filename}:{n.lineno + offset}: {what}"
    return None


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
        n = _sg.check(root, SHAPES, filename)
    except _sg.Refused as e:
        f, line, shape = e.args[0]
        raise Refusal(f"grammar {f}:{line + offset}: {shape}") from None
    sql = sql_problem(root, filename, offset)
    if sql is not None:
        raise Refusal(sql)
    sink = ADMITTED.get("sink")
    if sink is not None:
        sink.extend(node_key(filename, x) for x, _p, _f in _sg.visit(root))
    return n


def node_key(filename, node):
    """(file, line, col, node type): how the M6 assertion compares an
    inspected node with an admitted one."""
    return (filename, getattr(node, "lineno", None),
            getattr(node, "col_offset", None), type(node).__name__)


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
    if record is None:
        order = sequence_problem(stmts, filename, offset)
        if order is not None:
            raise Refusal(order)
    _bind(fn, "site", stmts, filename, offset, record)
    return count


def prefix_span(fn, stop):
    """Every statement of fn the prefix walk inspects: from the first to the
    first one holding a call of the plain name `stop` (included) and, when
    that statement is an `if` (a path may pass it without the call), every
    statement after it as well, since the walk reads each of them for a
    second call of `stop` (round 8, finding gate:1140: a suffix statement
    inspected was never admitted); all of them when none holds the call."""
    out = []
    for i, st in enumerate(fn.body):
        out.append(st)
        if stop in callees([st]):
            if isinstance(st, ast.If):
                out.extend(fn.body[i + 1:])
            break
    return out
