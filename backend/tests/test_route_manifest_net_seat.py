"""Exhaustive API-route and formatter non-consumer gate for W1 telemetry."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha1
import ast
import inspect
import contextlib
import re
import sys
import textwrap
import json
import typing
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.routing import Mount

import flag_evidence
import main
from net_seat_contract import (
    STORAGE_FIELDS,
    assert_no_net_seat_sentinels,
    storage_sentinels,
)


MANIFEST_PATH = Path(__file__).with_name("route_manifest_net_seat.json")
# The enumeration is only exhaustive on the PINNED FastAPI: 0.141+ wraps
# include_router() targets as _IncludedRouter entries that app.routes never
# flattens, which silently drops every tournaments route from this gate.
PINNED_FASTAPI = next(
    line.split("==")[1].strip()
    for line in (Path(__file__).parents[1] / "api" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    if line.startswith("fastapi==")
)

API_DIR = (Path(__file__).parents[1] / "api").resolve()

# ── The binding index ────────────────────────────────────────────────────
#
# r14 M7. Every previous version of this walk resolved a NAME to an OBJECT and
# then asked `inspect` for that object's source. An object has already thrown
# away the statement that bound it, and that erasure was the defect: a
# dataclass default that decides every persisted bracket row survived only
# because it happens to live inside a class, whose statement inspect can still
# recover. A raw SQL string 32 routes execute, a rank-tier table, a rate-limit
# tuple and a partial are the identical defect with no class to hide in -- all
# of them outside every fingerprint while this gate reported all-clear.
#
# So the node type is a first-party module-level BINDING, not a first-party
# object, and the source comes from parsing the module rather than from
# introspecting a value. The rule then never has to ask what KIND of thing a
# name denotes.
#
# Measured on this tree: 8 modules, 1282 bindings, ~5.3 s to build once per
# process. Re-measure when the index changes shape; a stale figure here is the
# kind of claim this gate exists to catch.

_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_BINDING_INDEX = {}

# ── Class bodies: the conservative bound (combat fix pass 3, M-9) ─────────
#
# A class-body read is charged to the class binding alone only when the walk
# KNOWS the name is bound there: a top-level statement of a type it models
# exactly (_CLASS_EXACT) bound it earlier, and no later statement may have
# touched it. Every other construct that binds or unbinds a name in a class
# body -- augmented assignment (which reads the name first), an exception
# alias (unbound again when its handler ends), `del`, a loop or `with`
# target, a walrus, a match capture, and any node type not listed here --
# clears that certainty and CHARGES the module-level name as a load. What a
# statement touches is read generically (`_class_touched`): every name it
# stores or deletes and every identifier field of every node in it, the
# identifier fields read from the interpreter's own node signatures, so a
# node type added by a later Python is charged by default. What a modelled
# assignment binds EXACTLY is read by lexical ownership (combat fix pass 4,
# `_class_target_names`): the current scope's Name, Starred, Tuple and List
# target elements only, never a name inside a subscript or attribute target
# or in a nested scope; an oracle test runs generated class bodies in the
# interpreter and proves the walk charges every module read it observes.

# Top-level class-body statements whose binding the walk models exactly.
_CLASS_EXACT = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom,
                ast.Assign, ast.AnnAssign)

# (node type, identifier or context field) the walk models as binding NOTHING
# in the class namespace, each with the reason; every entry has a control in
# _CLASS_FIELD_CONTROLS below. Every other identifier field is charged.
_CLASS_NOT_BINDING = {
    ("Attribute", "attr"): "an attribute of an object; the name read is a load",
    ("Attribute", "ctx"): "a store into an object, not into the class namespace",
    ("Subscript", "ctx"): "a store into an object, not into the class namespace",
    ("List", "ctx"): "a container target; each name in it is a Name, charged",
    ("Tuple", "ctx"): "a container target; each name in it is a Name, charged",
    ("Starred", "ctx"): "a container target; each name in it is a Name, charged",
    ("keyword", "arg"): "a call's keyword",
    ("ImportFrom", "module"): "the source module; the bound names are read from the aliases",
    ("MatchClass", "kwd_attrs"): "attribute names a class pattern matches",
    ("arg", "arg"): "a parameter of a nested function or lambda, bound in that scope",
    ("Global", "names"): "a declaration the walk reads into its declared-global set",
    ("Nonlocal", "names"): "a declaration the walk reads into its declared-nonlocal set",
}


def _ast_name_fields():
    """{node type name: (field, ...)} for EVERY node type whose signature the
    interpreter states (each node class's docstring is its ASDL line): the
    fields of type `identifier` or `expr_context`, possibly none. A node type
    missing here has no readable signature."""
    out = {}
    for name in dir(ast):
        cls = getattr(ast, name)
        if not (isinstance(cls, type) and issubclass(cls, ast.AST)):
            continue
        sig = (cls.__doc__ or "").strip().split("\n")[0]
        m = re.fullmatch(r"(\w+)(?:\((.*)\))?", sig)
        if not m or m.group(1) != name:
            continue
        out[name] = tuple(part.split()[1] for part in (m.group(2) or "").split(",")
                          if len(part.split()) == 2
                          and part.split()[0].rstrip("?*") in ("identifier", "expr_context"))
    return out


_AST_NAME_FIELDS = _ast_name_fields()


def _class_touched(st):
    """Every name a class-body statement may bind or unbind in the class
    namespace, read generically: each Name it stores or deletes, the local
    names its imports bind, and the value of every identifier field of every
    node in it, except the fields _CLASS_NOT_BINDING models as binding
    nothing. A node type the signatures do not describe has every string
    field read as an identifier. The bodies and parameters of nested
    functions, lambdas and classes (their own scopes) and comprehension
    targets are not read; their decorators, defaults, annotations, bases and
    first iterables are, since the class body evaluates those. An annotation
    alone (`x: int`) binds nothing and its target is not read."""
    out, stack = set(), [st]
    while stack:
        n = stack.pop()
        kind = type(n).__name__
        if isinstance(n, ast.Name):
            if not isinstance(getattr(n, "ctx", None), ast.Load):
                out.add(n.id)
            continue
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            out.update(a.asname or a.name.split(".")[0] for a in getattr(n, "names", ())
                       if a.name != "*")
            continue
        fields = _AST_NAME_FIELDS.get(kind)
        for field, value in ast.iter_fields(n):
            if fields is not None and field not in fields:
                continue
            if (kind, field) in _CLASS_NOT_BINDING:
                continue
            if isinstance(value, str):
                out.add(value)
            elif isinstance(value, list):
                out.update(v for v in value if isinstance(v, str))
        if isinstance(n, ast.AnnAssign) and getattr(n, "value", None) is None:
            stack.extend(x for x in (getattr(n, "annotation", None),) if x is not None)
            target = getattr(n, "target", None)
            if target is not None and not isinstance(target, ast.Name):
                stack.append(target)
            continue
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = getattr(n, "args", None)
            heads = list(getattr(n, "decorator_list", ())) + list(getattr(n, "type_params", ()))
            if getattr(n, "returns", None) is not None:
                heads.append(n.returns)
            if args is not None:
                heads += list(args.defaults) + [d for d in args.kw_defaults if d is not None]
                heads += [a.annotation for a in (args.posonlyargs + args.args + args.kwonlyargs
                                                 + [args.vararg, args.kwarg])
                          if a is not None and a.annotation is not None]
            stack.extend(heads)
            continue
        if isinstance(n, ast.ClassDef):
            stack.extend(list(getattr(n, "decorator_list", ())) + list(getattr(n, "bases", ()))
                         + list(getattr(n, "keywords", ())) + list(getattr(n, "type_params", ())))
            continue
        if isinstance(n, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            gens = getattr(n, "generators", None)
            if gens:
                stack.append(gens[0].iter)
            continue
        stack.extend(ast.iter_child_nodes(n))
    return out


def _class_target_names(target):
    """The names an assignment target binds in the CURRENT scope, by
    lexical ownership (combat fix pass 4, M-9): a Name stored into, and the
    elements of a Starred, Tuple or List target, recursively. Nothing else:
    never a name inside a subscript or attribute target's expressions (an
    object is stored into, the class namespace is not), and never a name
    in a nested scope those expressions open (a comprehension target binds
    in the comprehension, a lambda parameter in the lambda). A walrus there
    binds in the class, but it is no target element: `_class_touched` sees
    it and the walk charges it."""
    if isinstance(target, ast.Name):
        return {target.id} if isinstance(target.ctx, ast.Store) else set()
    if isinstance(target, ast.Starred):
        return _class_target_names(target.value)
    if isinstance(target, (ast.Tuple, ast.List)):
        out = set()
        for elt in target.elts:
            out |= _class_target_names(elt)
        return out
    return set()


# ── The reference walk: the default visit (combat fix pass 5, M-9) ───────
#
# Through fix pass 4 the reference walk was a hand-written visitor: for each
# scope-opening node it read the fields its author listed, and each review
# round found one more position it did not read (the last: the type
# parameters of a generic class or function, whose lazily evaluated bounds
# read module names). The method is replaced, not patched. The walk reads
# EVERY field the interpreter reports for a node's class (`_node_fields`,
# from the class's own `_fields`): a field holding nodes is visited, a
# string is charged as a name read (or, in a node stored into or deleted,
# bound), and any other value (an int, a bool, None) cannot spell a name.
# Exactly two tables say what differs from that default:
#
#   _FIELD_SCOPE   the scope a field's names are read in when that is not
#                  the scope the node stands in (a body, a parameter
#                  default, a type parameter's annotation scope, a
#                  comprehension's first iterable). A placement moves a
#                  field; it never drops one.
#   _NOT_CHARGED   the (class, field) rows whose string is NOT charged as a
#                  read, each with its role (what the walk does with it
#                  instead) and a one-line reason; every row has its own
#                  control (`_NOT_CHARGED_CONTROLS`).
#
# A field nobody thought about is therefore charged, never skipped. A test
# enumerates every (class, field) of the pinned interpreter and proves each
# is charged by the default visit or is a row of _NOT_CHARGED, and it fails
# when the interpreter gains a class or a field
# (test_f5_every_node_field_is_charged_by_the_default_visit_or_excluded).

_FIELD_SCOPE = {
    # A definition: its decorators where it stands (the default); its
    # parameters' annotations, its return annotation and its type parameters
    # in its annotation scope (the scope it stands in when it has no type
    # parameters); its parameters' defaults where it stands; its body in its
    # own scope.
    ("FunctionDef", "args"): "annotation",
    ("FunctionDef", "returns"): "annotation",
    ("FunctionDef", "type_params"): "annotation",
    ("FunctionDef", "body"): "inner",
    ("AsyncFunctionDef", "args"): "annotation",
    ("AsyncFunctionDef", "returns"): "annotation",
    ("AsyncFunctionDef", "type_params"): "annotation",
    ("AsyncFunctionDef", "body"): "inner",
    ("arguments", "defaults"): "outer",
    ("arguments", "kw_defaults"): "outer",
    ("Lambda", "body"): "inner",
    # A class: its bases, keywords and type parameters in its annotation
    # scope; its body as a class body, read in execution order.
    ("ClassDef", "bases"): "annotation",
    ("ClassDef", "keywords"): "annotation",
    ("ClassDef", "type_params"): "annotation",
    ("ClassDef", "body"): "class_body",
    # A type alias: its type parameters and its lazily evaluated value in an
    # annotation scope of its own.
    ("TypeAlias", "type_params"): "annotation",
    ("TypeAlias", "value"): "annotation",
    # A comprehension: its first iterable where it stands, the rest in its
    # own scope.
    ("ListComp", "elt"): "inner",
    ("ListComp", "generators"): "generators",
    ("SetComp", "elt"): "inner",
    ("SetComp", "generators"): "generators",
    ("GeneratorExp", "elt"): "inner",
    ("GeneratorExp", "generators"): "generators",
    ("DictComp", "key"): "inner",
    ("DictComp", "value"): "inner",
    ("DictComp", "generators"): "generators",
    ("comprehension", "iter"): "iter",
    # A walrus binds in the nearest enclosing scope that is no comprehension.
    ("NamedExpr", "target"): "home",
}

# The node classes that open a scope of their own, and its kind.
_OPENS = {"FunctionDef": "function", "AsyncFunctionDef": "function", "Lambda": "function",
          "ClassDef": "class", "ListComp": "comp", "SetComp": "comp", "GeneratorExp": "comp",
          "DictComp": "comp"}

_TYPE_COMMENT = "a type comment: text the interpreter never evaluates"
_NOT_CHARGED = {
    ("Attribute", "attr"): ("attr", "an attribute name: charged as `a.attr` on a bare-name "
                                    "base (through the module `a` imports), never as a variable"),
    ("keyword", "arg"): ("label", "a keyword argument's name, never a variable"),
    ("MatchClass", "kwd_attrs"): ("label", "the attribute names a class pattern matches"),
    ("alias", "name"): ("import", "what an import names: read from the statement (import_refs)"),
    ("alias", "asname"): ("import", "the name an import binds: read from the statement"),
    ("ImportFrom", "module"): ("import", "the module imported from: read from the statement"),
    ("Global", "names"): ("global", "a declaration: the name read or written here is the module's"),
    ("Nonlocal", "names"): ("nonlocal", "a declaration: the name is an enclosing function's"),
    ("FunctionDef", "name"): ("bind", "binds the name where the definition stands"),
    ("AsyncFunctionDef", "name"): ("bind", "binds the name where the definition stands"),
    ("ClassDef", "name"): ("bind", "binds the name where the definition stands"),
    ("ExceptHandler", "name"): ("bind", "the handler's alias: binds in the current scope"),
    ("MatchAs", "name"): ("bind", "a capture: binds in the current scope"),
    ("MatchStar", "name"): ("bind", "a capture: binds in the current scope"),
    ("MatchMapping", "rest"): ("bind", "a capture: binds in the current scope"),
    ("arg", "arg"): ("param", "a parameter: binds in the function or lambda it belongs to"),
    ("TypeVar", "name"): ("bind", "a type parameter: binds in its annotation scope"),
    ("ParamSpec", "name"): ("bind", "a type parameter: binds in its annotation scope"),
    ("TypeVarTuple", "name"): ("bind", "a type parameter: binds in its annotation scope"),
    ("Constant", "value"): ("literal", "a literal: a string constant is text, not a name"),
    ("Constant", "kind"): ("literal", "the `u` prefix of a string literal"),
    ("MatchSingleton", "value"): ("literal", "True, False or None in a pattern"),
    ("Assign", "type_comment"): ("literal", _TYPE_COMMENT),
    ("For", "type_comment"): ("literal", _TYPE_COMMENT),
    ("AsyncFor", "type_comment"): ("literal", _TYPE_COMMENT),
    ("With", "type_comment"): ("literal", _TYPE_COMMENT),
    ("AsyncWith", "type_comment"): ("literal", _TYPE_COMMENT),
    ("FunctionDef", "type_comment"): ("literal", _TYPE_COMMENT),
    ("AsyncFunctionDef", "type_comment"): ("literal", _TYPE_COMMENT),
    ("arg", "type_comment"): ("literal", _TYPE_COMMENT),
    ("TypeIgnore", "tag"): ("literal", "a `type: ignore` comment's tag"),
}


def _node_fields(n):
    """(field, value) for EVERY field the interpreter reports for the node's
    class, in its own order: the one place the reference walk reads a node.
    A field the node does not carry reads as None."""
    for field in type(n)._fields:
        yield field, getattr(n, field, None)


def _strings(value):
    """The strings a field holds: itself, or each string of a list."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _store_bases(st):
    """The name at the base of every attribute or subscript a statement
    stores into or deletes (`X.a = ...`, `X[k] += ...`, `del X[k]`): the
    object a module-level statement changes, as the module indexer charges
    an assignment's (combat fix pass 5)."""
    out = set()
    for sub in ast.walk(st):
        if isinstance(sub, (ast.Attribute, ast.Subscript)) \
                and isinstance(getattr(sub, "ctx", None), (ast.Store, ast.Del)):
            base = sub.value
            while isinstance(base, (ast.Attribute, ast.Subscript)):
                base = base.value
            if isinstance(base, ast.Name):
                out.add(base.id)
    return out


def _is_script_guard(node):
    """`if __name__ == ...:` -- a block that does not exist when the api imports
    the module.

    Indexed like any other guard until r15, which is how ordinary names from a
    bracket self-test (rows, ids, extras, sus) ended up inside two hundred route
    fingerprints: the cross-module walk resolves a handler's local name against
    every module, and a script-only binding is a binding as far as the index is
    concerned."""
    return (isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            # r16: the exemption is for the canonical script guard ONLY. A `!=`
            # or an `in` on __name__ RUNS at import and stays indexed.
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Eq)
            and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value == "__main__")


def _index_module(path, references_of=None):
    """{name: (kind, source segment, referenced names)} for every MODULE-SCOPE
    binding in one file. With `references_of` (a node), no file is read: the
    references the walk charges for that node alone are returned (`_references`,
    the completeness test's synthetic probes).

    `kind` is "def" for FunctionDef/AsyncFunctionDef/ClassDef and "data" for
    Assign/AnnAssign and for every other statement that binds a name at module
    scope (combat fix pass 5: a `type` alias, an augmented assignment, a loop
    target, a `del`, a store into an object's attribute or item; read by
    `_class_touched` and `_store_bases`, so a statement type nobody listed
    binds what it binds). A statement that binds no name is no binding. A
    def's segment starts at its first DECORATOR line, so a
    route's own decorator -- which carries its path and response_model -- is
    inside its fingerprint.

    Module-level If/Try/With bodies are recursed into, which is not optional:
    main binds `_PIL_AVAILABLE`/`_PILImage` inside a try/except, and 4 routes
    cover them. The block's CONTROLLING HEADER is prepended to every binding
    inside it, because the condition a binding exists under is part of what was
    reviewed -- without it the except clause deciding whether Pillow is
    available could be rewritten with no fingerprint moving.

    `if __name__ == "__main__":` is the one guard NOT recursed into. Its body
    does not exist when the api imports the module, and tournament_bracket's
    self-test binds ordinary names -- rows, ids, real, extras, s1, s2, sus --
    that a handler's own locals reference. Measured before this exclusion: 1008
    occurrences over 10 names, `sus` inside 194 route fingerprints. Editing a
    bracket self-test moved two hundred routes.

    A name bound more than once at module scope CONCATENATES its segments rather
    than replacing them, so a conditional rebinding cannot hide half its
    source."""
    source = "" if references_of is not None else path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    table = {}

    def segment(node):
        start = node.lineno
        for decorator in getattr(node, "decorator_list", ()):
            start = min(start, decorator.lineno)
        # `ast` ends a node at its last STATEMENT, but a binding's SOURCE runs
        # to the end of its block -- so a comment sitting after the last
        # statement, still inside the function, is dropped. That is exactly
        # where a rule gets written down, and the fidelity control below caught
        # it on this file's first run. Absorb trailing lines that are blank or
        # comments indented INSIDE the binding, and stop at the first line that
        # is anything else; buffered, so trailing blanks alone are not swept in.
        end = node.end_lineno
        pending = []
        for offset in range(node.end_lineno, len(lines)):
            stripped = lines[offset].strip()
            if not stripped:
                pending.append(offset)
                continue
            indent = len(lines[offset]) - len(lines[offset].lstrip())
            if stripped.startswith("#") and indent > node.col_offset:
                pending.append(offset)
                end = offset + 1
                continue
            break
        del pending
        return "".join(lines[start - 1:end])

    def referenced(node):
        """The references a binding's source makes, in three forms the walk
        resolves to bindings (2026-10-02, the binding-resolved closure):

          "n"        a bare name, resolved in the module it is written in;
          "a.attr"   an attribute read on a bare name, resolved through the
                     module the name `a` imports, if it imports one of ours;
          "X:n"      binding `n` of module `X` directly -- what a function-
                     local `from X import n` binds, and `a.attr` where `a` is a
                     function-local `import X as a`.

        Read per LEXICAL SCOPE (combat fix pass 1, M-9). Every function,
        lambda, class body and comprehension is its own scope, holding the
        names it binds: parameters, assignment and loop targets, `with` and
        `except` names, match captures, the names its defs and classes bind,
        and its imports. A name read inside a scope that binds it (or inside
        a function nested in one that does; a class body's names are not
        visible to the functions in it) is LOCAL and charges no module
        binding: a local `case` is not the module's `case` import. A name no
        enclosing scope binds (or one declared `global`) is a module global,
        charged as before.

        A CLASS BODY is read in execution order (combat fix pass 2, M-9): at
        each name read in it, a class binding counts as certain only when an
        unconditional statement of the body bound it earlier and no `del`
        since may have removed it. A certain class binding is the only
        binding charged; otherwise the class binding AND the module global
        are both charged (a name a class body binds anywhere is looked up in
        the class namespace and then in the module's globals, never in an
        enclosing function), so a read before a late binding, beside a
        conditional one, or after a delete charges the module binding too. A
        name the class body never binds resolves as before. Methods, lambdas
        and comprehensions inside the class still skip its names.

        Certainty is CONSERVATIVE (combat fix pass 3, M-9): only a top-level
        statement of a type in _CLASS_EXACT makes a binding certain. Every
        name any statement may touch beyond that (`_class_touched`: an
        augmented assignment's target, an exception alias, a `del`, a loop,
        `with` or walrus target, a match capture, an identifier of a node
        type the walk does not model) loses certainty before the statement
        and is charged as a load there, so its module binding is charged.

        Every function-local import target is retained,
        on EVERY branch: `from X import n` charges "X:n" wherever it sits,
        and `a.attr` on a local alias charges "X:attr" for each module the
        alias is bound to anywhere in its scope, so a reused alias keeps both
        targets.

        An attribute read on anything else (a local value, a call result)
        names no module-level binding and is not a reference.

        The walk is the DEFAULT VISIT (combat fix pass 5, M-9): every field
        of every node is read (`_node_fields`), placed by `_FIELD_SCOPE` and
        exempted from charging only by a row of `_NOT_CHARGED`. A generic
        definition, class or type alias opens an ANNOTATION scope holding its
        type parameters; its bounds and constraints, its annotations, bases
        and keywords, and a type alias's value are read there. Inside a class
        body such a scope also sees the class's names, never as certain (a
        bound is evaluated lazily, against the class namespace as it is when
        it is read): a read there charges the class binding and goes on to
        the binding the enclosing scopes give it, so the module's is charged
        unless an enclosing function binds the name."""

        class Scope:
            def __init__(self, parent, kind):
                self.parent, self.kind = parent, kind
                self.bound, self.loads = {}, []
                self.declared_global, self.declared_nonlocal = set(), set()
                self.certain = set()        # class body: names certainly bound here

        def load(scope, name, attr):
            scope.loads.append((name, attr, scope.kind == "class" and name in scope.certain))

        def certain_binds(st):
            """The names a top-level class-body statement of a type the walk
            models exactly (_CLASS_EXACT) binds once it ran; none for any
            other statement."""
            if not isinstance(st, _CLASS_EXACT):
                return set()
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return {st.name}
            if isinstance(st, (ast.Import, ast.ImportFrom)):
                return set(import_refs(st))
            if isinstance(st, ast.AnnAssign) and st.value is None:
                return set()                      # an annotation alone binds nothing
            targets = getattr(st, "targets", None) or [st.target]
            out = set()
            for tg in targets:
                out |= _class_target_names(tg)
            return out

        def bind_name(scope, name, refs=()):
            scope.bound.setdefault(name, set()).update(refs)

        def import_refs(sub):
            out = {}
            if isinstance(sub, ast.Import):
                for alias in sub.names:
                    local = alias.asname or alias.name.split(".")[0]
                    target = alias.name if alias.asname else alias.name.split(".")[0]
                    out.setdefault(local, set()).add(target + ":")
            elif isinstance(sub, ast.ImportFrom):
                for alias in sub.names:
                    if alias.name == "*":
                        continue
                    refs = ({f"{sub.module}:{alias.name}"}
                            if sub.module and not sub.level else set())
                    out.setdefault(alias.asname or alias.name, set()).update(refs)
            return out

        def class_body(inner, body):
            """A class body, statement by statement. The conservative bound
            (fix pass 3): every name the statement may touch beyond what it
            is modelled to bind exactly loses certainty BEFORE the statement
            runs and is charged as a load, so its module binding is in."""
            for st in body:
                exact = certain_binds(st)
                touched = _class_touched(st) - exact
                for name in sorted(touched):
                    inner.certain.discard(name)
                    bind_name(inner, name)
                    load(inner, name, None)
                visit(st, inner)
                inner.certain -= touched
                inner.certain |= exact

        def visit(n, scope, env=None):
            """The default visit: every field of `n` (`_node_fields`), read
            in the scope `_FIELD_SCOPE` places it in (the current one unless
            a row says otherwise); a string field is a read, or a binding in
            a node stored into or deleted, unless `_NOT_CHARGED` gives it
            another role. `env` carries what a definition's parameters need:
            the scope they bind in and the scope their defaults are read in,
            and a comprehension's first-iterable scope."""
            if isinstance(n, list):
                for item in n:
                    visit(item, scope, env)
                return
            if not isinstance(n, ast.AST):
                return                                    # None, an int, a bool: no name
            kind = type(n).__name__
            places = dict(env or {})
            opens = _OPENS.get(kind)
            if opens is not None or kind == "TypeAlias":
                places, env = {}, None
                ann = None
                if kind == "TypeAlias" or getattr(n, "type_params", None):
                    ann = Scope(scope, "annotation")
                    scopes.append(ann)
                places["annotation"] = ann or scope
                if opens is not None:
                    inner = Scope(ann or scope, opens)
                    scopes.append(inner)
                    places.update(inner=inner, class_body=inner, generators=inner)
                    env = {"outer": scope, "params": inner}
            if kind == "NamedExpr":
                home = scope
                while home.kind == "comp" and home.parent is not None:
                    home = home.parent
                places["home"] = home
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for name, refs in import_refs(n).items():
                    bind_name(scope, name, refs)
            stored = isinstance(getattr(n, "ctx", None), (ast.Store, ast.Del))
            for field, value in _node_fields(n):
                row = _NOT_CHARGED.get((kind, field))
                if row is not None:
                    role, names = row[0], _strings(value)
                    if role == "attr":
                        base = getattr(n, "value", None)
                        if isinstance(base, ast.Name) and isinstance(base.ctx, ast.Load):
                            for name in names:
                                load(scope, base.id, name)
                    elif role == "bind":
                        for name in names:
                            bind_name(scope, name)
                    elif role == "param":
                        for name in names:
                            bind_name(places.get("params", scope), name)
                    elif role == "global":
                        scope.declared_global.update(names)
                    elif role == "nonlocal":
                        scope.declared_nonlocal.update(names)
                    continue                     # "label", "literal", "import": nothing read
                for name in _strings(value):
                    if stored and name not in scope.declared_global:
                        bind_name(scope, name)   # a `del` in a class body: charged above
                    else:
                        load(scope, name, None)  # a read, or a write to a global
                place = _FIELD_SCOPE.get((kind, field), "here")
                if place == "class_body":
                    class_body(places["class_body"],
                               [st for st in (value or ()) if isinstance(st, ast.AST)])
                elif place == "generators":
                    for i, g in enumerate(value or ()):
                        visit(g, places["generators"],
                              {"iter": scope if i == 0 else places["generators"]})
                else:
                    visit(value, places.get(place, scope), env)

        def owners(scope, name, certain):
            """Every scope whose binding `name` may denote when read in
            `scope` (None for the module global): the first binding scope,
            and beside a class body's binding that is not certain at the
            read, the module global (a name a class body binds is looked up
            in the class namespace and then in the module's globals, never
            in an enclosing function). A class directly enclosing an
            annotation scope the read passed through is read too, never as
            certain, and the lookup goes on past it (fix pass 5)."""
            out = []
            s, first, through_annotation = scope, True, False
            while s is not None and s.kind != "module":
                if name in s.declared_global:
                    break
                if name in s.bound and name not in s.declared_nonlocal \
                        and (s.kind != "class" or first):
                    out.append(s)
                    if s.kind == "class" and not certain:
                        out.append(None)
                    return out
                if s.kind == "class" and through_annotation and name in s.bound:
                    out.append(s)
                through_annotation = s.kind == "annotation"
                first = False
                s = s.parent
            out.append(None)
            return out

        module = Scope(None, "module")
        scopes = [module]
        visit(node, module)
        names = set()
        for scope in scopes:
            if scope.kind != "module":
                for refs in scope.bound.values():
                    names.update(r for r in refs if not r.endswith(":"))
            for name, attr, certain in scope.loads:
                for home in owners(scope, name, certain):
                    if home is None:
                        names.add(name if attr is None else f"{name}.{attr}")
                    elif attr is not None:
                        names.update(r + attr for r in home.bound[name] if r.endswith(":"))
        return names

    def import_target(node, alias):
        """What one module-level import alias denotes, as a reference: "X:"
        for a module, "X:n" for a name imported from one. A relative or star
        import denotes nothing the walk can name."""
        if isinstance(node, ast.Import):
            return {alias.name.split(".")[0] + ":"}
        if node.module and not node.level and alias.name != "*":
            return {f"{node.module}:{alias.name}"}
        return set()

    def header_refs(node):
        """r2 (Sept 6): the names a block HEADER references -- the `if` test,
        the `with` expressions. `try:` has none of its own; each handler adds
        its exception type below. A header's TEXT was already fingerprinted,
        but the object a name in it denotes was not part of the closure: a
        tuple of exception classes or a feature flag could change what the
        block admits with no fingerprint moving."""
        if isinstance(node, ast.If):
            return referenced(node.test)
        if isinstance(node, ast.With):
            names = set()
            for item in node.items:
                names |= referenced(item.context_expr)
            return names
        return set()

    def guard_header(node):
        """The controlling line(s) of a module-level block -- `if ...:`,
        `try:`, `with ...:` -- down to its first statement. Prepended to every
        binding inside, because the condition a binding exists under is part
        of what was reviewed."""
        return "".join(lines[node.lineno - 1:node.body[0].lineno - 1])

    def handler_header(handler):
        """r16: an `except ...:` header, down to the handler's first
        statement. `guard_header` alone reused the `try:` line for every
        handler, so `except Exception` could become `except ImportError` --
        a different set of failures reaching a different binding -- with no
        fingerprint moving."""
        return "".join(lines[handler.lineno - 1:handler.body[0].lineno - 1])

    def part_header(previous, part):
        """r16: the `else:` / `finally:` header of a block's later part. The
        ast gives those parts no node of their own, so the header is the
        source between the last statement of the part before and the first
        statement of this one."""
        if not part:
            return ""
        return "".join(lines[previous.end_lineno:part[0].lineno - 1])

    def bind(name, kind, node, guard="", guard_refs=frozenset(), own_refs=None):
        own = referenced(node) if own_refs is None else own_refs
        text, refs = guard + segment(node), set(own) | set(guard_refs)
        if name in table:
            prev_kind, prev_text, prev_refs = table[name]
            table[name] = (prev_kind, prev_text + text, prev_refs | refs)
        else:
            table[name] = (kind, text, refs)

    def visit(body, guard="", guard_refs=frozenset()):
        for node in body:
            if isinstance(node, _DEF_NODES):
                bind(node.name, "def", node, guard, guard_refs)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    for sub in ast.walk(target):
                        if isinstance(sub, ast.Name):
                            bind(sub.id, "data", node, guard, guard_refs)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    bind(node.target.id, "data", node, guard, guard_refs)
                else:
                    for name in sorted(_store_bases(node)):          # fix pass 5
                        bind(name, "data", node, guard, guard_refs)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                # r15. An import binds a name, and WHICH object a name denotes
                # is part of what a handler does. Removing a batch-added
                # `DBAPIError` import moved no fingerprint at all, while the
                # deadlock path naming it stopped being a rollback-and-retry.
                #
                # Given their own kind so the affordability bound can count
                # them separately: a route references ~40 imported names, which
                # inflates the CLOSURE without inflating the DRIFT, because
                # import lines change far more rarely than code does.
                #
                # Each alias carries what IT denotes ("X:" or "X:n"), not the
                # whole statement's names, so `from X import a, b` does not
                # make `a` reach `b`.
                for alias in node.names:
                    bind(alias.asname or alias.name.split(".")[0], "import", node,
                         guard, guard_refs, own_refs=import_target(node, alias))
            elif isinstance(node, (ast.If, ast.Try, ast.With)):
                if _is_script_guard(node):
                    continue
                if isinstance(node, ast.With):
                    # Fix pass 5: the names its `as` targets bind, with the
                    # whole statement as their source.
                    bound = set()
                    for item in node.items:
                        if item.optional_vars is not None:
                            bound |= _class_touched(item.optional_vars) \
                                | _store_bases(item.optional_vars)
                    for name in sorted(bound):
                        bind(name, "data", node, guard, guard_refs)
                inner = guard + guard_header(node)
                inner_refs = guard_refs | header_refs(node)
                visit(node.body, inner, inner_refs)
                # r16: each later part carries ITS OWN header on top of the
                # block's, walked in source order so "the statement before"
                # is always the one the header follows.
                last = node.body[-1]
                for handler in getattr(node, "handlers", []):
                    handler_refs = inner_refs | (
                        referenced(handler.type) if handler.type is not None else set())
                    visit(handler.body, inner + handler_header(handler), handler_refs)
                    last = handler.body[-1]
                orelse = getattr(node, "orelse", [])
                if orelse:
                    visit(orelse, inner + part_header(last, orelse), inner_refs)
                    last = orelse[-1]
                finalbody = getattr(node, "finalbody", [])
                if finalbody:
                    visit(finalbody, inner + part_header(last, finalbody), inner_refs)
            else:
                # Combat fix pass 5 (M-9), the default: any other statement
                # binds every name it may bind at module scope (a `type`
                # alias, an augmented assignment, a loop or `with` target, a
                # walrus, a `del`, a match capture, and anything a later
                # Python adds: `_class_touched` reads it generically) and the
                # object it stores into; each such binding carries the whole
                # statement and its references. A statement that binds no
                # name (a call, an assert) is no binding of anything.
                for name in sorted(_class_touched(node) | _store_bases(node)):
                    bind(name, "data", node, guard, guard_refs)

    if references_of is not None:
        return referenced(references_of)
    visit(ast.parse(source).body)
    return {name: (kind, text, frozenset(refs))
            for name, (kind, text, refs) in table.items()}


def _references(node):
    """The references the walk charges for one node, read as a module-level
    binding's source is read (the same walk, no file)."""
    return _index_module(None, references_of=node)


def _binding_index():
    """{module stem: bindings} over every .py file in backend/api.

    Discovered from the DIRECTORY rather than from the modules the app happens
    to have imported: which files serve routes is a fact about today's routing
    table, and a helper does not stop being ours because the route that reached
    it moved."""
    if not _BINDING_INDEX:
        for path in sorted(API_DIR.glob("*.py")):
            _BINDING_INDEX[path.stem] = _index_module(path)
    return _BINDING_INDEX


_SEGMENT_MEMO = {}


def _segment(module, name):
    """THE source-text seam.

    Every byte that reaches a fingerprint comes through here, and every
    mutation control in this file patches THIS rather than `inspect.getsource`.
    That is what makes the controls test the shipped rule: a control that
    patches a function the rule no longer calls passes for the wrong reason.
    The memo is keyed, so a control evicts one key and restores it."""
    key = (module, name)
    if key not in _SEGMENT_MEMO:
        binding = _binding_index().get(module, {}).get(name)
        _SEGMENT_MEMO[key] = "" if binding is None else binding[1]
    return _SEGMENT_MEMO[key]


@contextlib.contextmanager
def _mutated_segment(module, name):
    """Edit ONE binding's source through the seam every fingerprint reads.

    Every mutation control in this file uses this. The previous controls
    patched `inspect.getsource`, which the rule called until this range and
    does not call now -- so they would have gone on passing while testing
    nothing at all. Patching the memo instead means a control can only pass if
    the shipped rule really does read that binding's text."""
    key = (module, name)
    original = _segment(module, name)
    assert original, f"{module}.{name} is not an indexed binding"
    _SEGMENT_MEMO[key] = original + "\n# mutation\n"
    try:
        yield
    finally:
        _SEGMENT_MEMO[key] = original


def _route_fingerprint(route):
    for entry in _route_identities([route]):
        return entry["source_sha1"]
    raise AssertionError("the route did not enumerate")


def _binding_kind(module, name):
    binding = _binding_index().get(module, {}).get(name)
    return None if binding is None else binding[0]


def _is_ours(obj):
    """Whether an object's source is ours to review. Used only to turn the
    app's own objects (endpoints, dependencies, response models, middleware)
    into index keys -- never to decide what the walk may step through."""
    try:
        return Path(inspect.getfile(obj)).resolve().parent == API_DIR
    except (TypeError, OSError):
        return False


def _binding_key(obj):
    """(module, name) for a first-party object, or None."""
    if not _is_ours(obj):
        return None
    module = getattr(obj, "__module__", None)
    name = getattr(obj, "__name__", None)
    if not module or not name:
        return None
    return (module, name)


def _walk_bindings(seeds, index=None):
    """{(module, name): kind} for every binding the seeds reach, seeds included.

    THREE TIERS, and the middle one is what keeps this affordable. A def or
    class is EXPANDED THROUGH -- every name inside it is followed. A data
    binding is followed only into OTHER DATA BINDINGS. An import is a leaf,
    except for the guards that SELECT it (Group 2 review, Sept 6).

    The middle tier is the whole cost control, not a compromise: letting a data
    binding follow names of any kind makes `app = FastAPI(...)` a hub that every
    route decorator references, and the measured median closure goes from 20 to
    179 -- every route dragging in most of the app, a fingerprint that certifies
    nothing because it always moves.

    Data-into-data was missing until r15 found what it cost: a data binding
    COMPOSED from other data bindings showed only the NAME of what it composed.
    `_DC_ELIGIBLE_TERMS` is built by concatenating `_DC_EVIDENCE_TERM`, so
    rewriting the rule that decides whether a disconnect report is accepted
    moved NO route fingerprint -- measured, 0 of 309 routes covered it. That is
    exactly the raw-SQL hole this method exists to close, one level of
    indirection further down.

    A reference is resolved to the binding it denotes (2026-10-02, the
    binding-resolved closure; see `_resolve`): a bare name in the module it is
    written in, an imported name through its import to the binding in the
    module it comes from, `a.attr` through the module `a` imports. A name is
    charged to a route only when the route's closure binds it: `json.dumps` and
    `combat_measures.dumps` are different names, and an import in a module the
    route does not reach charges that route nothing. Until this change a bare
    name was resolved in every indexed module and an attribute by its last
    part alone, so one new module importing `text` or defining `dumps` entered
    hundreds of route closures it is not part of."""
    index = _binding_index() if index is None else index
    reached = {}
    frontier = list(seeds)
    while frontier:
        key = frontier.pop()
        if key in reached:
            continue
        module, name = key
        binding = index.get(module, {}).get(name)
        if binding is None:
            continue
        kind, _text, refs = binding
        reached[key] = kind
        # An import names something defined outside this api. Its own line is
        # fingerprinted; there is nothing of ours beneath it to follow -- EXCEPT
        # the guards that select it (Group 2 review, Sept 6): under
        # `if FEATURE: import fast as engine / else: import slow as engine`
        # FEATURE decides which implementation a route runs. An import's refs
        # are only ever its block headers' names (r2), so following them costs
        # nothing on an unguarded import and closes the hole on a guarded one.
        # An import of one of OUR modules is followed to the binding it names
        # ("X:n"); that is how a route reaches a helper in another module.
        for ref in refs:
            for target in _resolve(index, module, ref):
                if target in reached:
                    continue
                if kind == "data" and index[target[0]][target[1]][0] != "data":
                    continue
                frontier.append(target)
    return reached


def _resolve(index, module, ref):
    """The bindings one reference written in `module` denotes (forms in
    `_index_module.referenced`).

      "X:n"     binding n of module X, if X is one of ours and binds n;
      "a.attr"  binding attr of module X, when `a` is a module-level import of
                X in `module` (every X, when guarded imports bind `a` twice);
      "n"       the binding n of `module` itself and, when that binding is an
                import, the binding it imports -- so a data binding composed
                from an imported constant still reaches that constant.

    Anything else -- a builtin, a local, a name `module` does not bind --
    denotes no binding of ours."""
    table = index.get(module, {})
    if ":" in ref:
        target, _, name = ref.partition(":")
        return [(target, name)] if name and name in index.get(target, {}) else []
    if "." in ref:
        base, _, attr = ref.partition(".")
        binding = table.get(base)
        if binding is None or binding[0] != "import":
            return []
        return [(r[:-1], attr) for r in sorted(binding[2])
                if r.endswith(":") and attr in index.get(r[:-1], {})]
    binding = table.get(ref)
    if binding is None:
        return []
    keys = [(module, ref)]
    if binding[0] == "import":
        for r in sorted(binding[2]):
            if ":" in r:
                keys.extend(_resolve(index, module, r))
    return keys


def _route_seeds(route):
    """Every first-party binding a route enters through, not just its handler.

    Recovered computedly from the app, never listed. A route's behaviour is
    also decided by the dependencies FastAPI resolves before the handler runs
    and by the response model it serialises through, and neither of those is
    referenced by name inside the handler body -- they are written in the
    decorator and the signature."""
    seeds = []
    endpoint = getattr(route, "endpoint", None)
    if endpoint is not None:
        key = _binding_key(endpoint)
        if key is not None:
            seeds.append(key)
    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        stack = list(getattr(dependant, "dependencies", ()) or ())
        while stack:
            dependency = stack.pop()
            call = getattr(dependency, "call", None)
            if call is not None:
                key = _binding_key(call)
                if key is not None:
                    seeds.append(key)
            stack.extend(getattr(dependency, "dependencies", ()) or ())
    model = getattr(route, "response_model", None)
    if model is not None:
        pending = [model]
        while pending:
            annotation = pending.pop()
            args = typing.get_args(annotation)
            if args:
                pending.extend(a for a in args if a is not type(None))
                continue
            key = _binding_key(annotation)
            if key is not None:
                seeds.append(key)
    return sorted(set(seeds))


_CLOSURE_CACHE = {}


def _reached(seeds):
    """Memoised: the same seeds are asked for by the manifest build, by the
    affordability bound and by several assertions below."""
    key = tuple(seeds)
    cached = _CLOSURE_CACHE.get(key)
    if cached is None:
        cached = _walk_bindings(seeds)
        _CLOSURE_CACHE[key] = cached
    return cached


def _fingerprint_text(seeds):
    """The reviewed surface as text: every reached binding's segment, in a
    fixed order so the fingerprint does not depend on walk order."""
    return "".join(_segment(module, name)
                   for module, name in sorted(_reached(seeds)))


def _helper_closure(endpoint):
    """The identities a ROUTE HANDLER reaches, sorted, excluding its own seeds.
    Kept in this shape because several assertions below are written against
    it."""
    seeds = [_binding_key(endpoint)] if _binding_key(endpoint) else []
    return sorted(set(_reached(seeds)) - set(seeds))


# ── Entry points that are not routes ─────────────────────────────────────
#
# A route table is not the whole app. Middleware runs on every request,
# exception handlers decide what a failure returns, and the lifespan starts
# the background work. None of them appears in `app.routes`, so before this
# range every one of them was outside every fingerprint: editing the
# rate-limit gate moved nothing anywhere.


def _middleware_entry_points():
    """The first-party dispatch functions of the app's own middleware."""
    keys = []
    for middleware in getattr(main.app, "user_middleware", ()) or ():
        dispatch = (getattr(middleware, "kwargs", None) or {}).get("dispatch")
        if dispatch is not None:
            key = _binding_key(dispatch)
            if key is not None:
                keys.append(key)
    # SORTED, not `sorted(set(...))`. How many times a dispatch is registered
    # is part of what the app does to a request: registering the rate-limit
    # gate twice sends every request through the limiter twice, so a nominal
    # 20-per-10-seconds starts refusing at 11 — and a set erased the second
    # registration, leaving the manifest unmoved and this gate silent.
    return sorted(keys)


def _exception_handler_entry_points():
    """First-party exception handlers.

    The day predicted below arrived: RJ-4 registered
    `main._ffa_report_refusal_handler` for `FfaReportRefusal`, and the
    exhaustiveness assertion below caught it exactly as it was written to --
    two red tests on a manifest nobody had edited, which is what a gate that
    fails closed is for. It is a REQUEST-PATH surface: every FFA report
    refusal is serialised by it, so its body shape is reviewed here and
    fingerprinted like a route.

    The assertion this replaces was "the section is empty". That was correct
    while it was true and is now the wrong shape, because it would have to be
    re-written for every handler ever added. What is asserted instead is the
    property that made the old one safe: the RAW handler set must be non-empty,
    proving the recovery still sees handlers at all, and the recovered
    first-party set must equal the manifest -- which the generic loop already
    checks for every section. A handler appearing or leaving therefore stays a
    review item, answerable only by editing the manifest's identity list by
    hand (repin_route_manifest.py refuses to do it)."""
    keys = []
    for handler in (getattr(main.app, "exception_handlers", None) or {}).values():
        key = _binding_key(handler)
        if key is not None:
            keys.append(key)
    return sorted(set(keys))


def _background_entry_points():
    """The first-party lifespan, recovered through the wrappers FastAPI puts
    around it.

    `app.router.lifespan_context` is not the app's lifespan: FastAPI merges
    lifespans, so what is stored is `merged_lifespan` closing over another
    `merged_lifespan` closing over ours. A one-level `__closure__` read finds
    nothing at all, which is a recovery that silently fingerprints an empty
    set. The walk below descends through nested closures and through
    `__wrapped__`/`func` wrappers, bounded by identity and depth.

    THE DEPTH IS NOT A COST CONTROL AND MUST NOT BE TUNED LIKE ONE. `seen` is
    what bounds the work -- every object is visited once -- so depth only
    decides how deep the chain may be before the recovery gives up. The chain
    grows by ONE LEVEL PER `include_router`, and `lifespan` itself is behind a
    `@asynccontextmanager` wrapper, so the real function sits one hop below the
    level that carries its name. At a bound of 8 it sat exactly at the edge:
    mounting one more router pushed it past, `_is_ours` refused the contextlib
    helper that was left, and this returned [] -- the empty set this docstring
    warns about, arrived at by a number rather than by a missing lifespan.
    (Measured on the wave B/C tree: four routers, the wrapper at depth 8 and
    the function at 9.) The bound is now far above any plausible router count,
    and `test_the_manifest_covers_every_non_route_entry_point` asserts the
    recovery is NON-EMPTY, so a future chain that outgrows even this fails
    loudly instead of fingerprinting nothing."""
    found, seen = [], set()

    def descend(obj, depth):
        if depth > 64 or id(obj) in seen or not callable(obj):
            return
        seen.add(id(obj))
        key = _binding_key(obj)
        if key is not None:
            found.append(key)
        for cell in (getattr(obj, "__closure__", None) or ()):
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if callable(value):
                descend(value, depth + 1)
        for attribute in ("__wrapped__", "func"):
            wrapped = getattr(obj, attribute, None)
            if callable(wrapped):
                descend(wrapped, depth + 1)

    descend(getattr(main.app.router, "lifespan_context", None), 0)
    return sorted(set(found))


def _entry_point_sections():
    """{section name: [(module, name)]} -- the three non-route sections."""
    return {
        "middleware": _middleware_entry_points(),
        "exception_handlers": _exception_handler_entry_points(),
        "background_entry_points": _background_entry_points(),
    }


MODULE_SRC = (Path(__file__).parents[1] / "api" / "main.py").read_text(encoding="utf-8")

SENTINEL_ROUTE = {
    "path": "/api/v1/matches/by-code/{code}",
    "methods": ["GET"],
    "module": "main",
    "qualname": "get_match_by_code",
}


def _joined_path(prefix: str, path: str) -> str:
    if not prefix:
        return path
    if path == "/":
        return prefix or "/"
    return prefix.rstrip("/") + "/" + path.lstrip("/")


def _route_identities(routes, prefix=""):
    identities = []
    for route in routes:
        if isinstance(route, Mount):
            identities.extend(
                _route_identities(route.routes, _joined_path(prefix, route.path))
            )
            continue
        if not isinstance(route, (APIRoute, APIWebSocketRoute)):
            continue
        path = _joined_path(prefix, route.path)
        if not path.startswith("/api/v1/"):
            continue
        endpoint = route.endpoint
        # A handler's fingerprint covers every module-level BINDING it reaches,
        # transitively — an extracted helper must not become a fingerprint
        # hole, and neither must a raw SQL string or a table of constants moved
        # out of the body. Sorted inside _fingerprint_text, so the value does
        # not depend on walk order.
        source_text = _fingerprint_text(_route_seeds(route))
        identities.append(
            {
                "path": path,
                "methods": sorted(getattr(route, "methods", ()) or ()),
                "module": endpoint.__module__,
                "qualname": endpoint.__qualname__,
                "source_sha1": sha1(source_text.encode("utf-8")).hexdigest(),
            }
        )
    return sorted(
        identities,
        key=lambda item: (
            item["path"],
            item["methods"],
            item["module"],
            item["qualname"],
        ),
    )


def _route_registration_order():
    """Route identities in the order Starlette will try to match them.

    r15. The manifest sorts, and sorting discards the one property that decides
    WHICH handler a request reaches: first match wins. Moving a dynamic
    `/players/{steam_id}` above a static `/players/search` leaves every identity
    and every fingerprint in this file untouched, while `/players/search`
    quietly starts being served as `steam_id="search"`.

    Rendered as strings so a reordering shows up in a diff as the two lines that
    swapped, rather than as a wall of moved JSON."""
    order = []

    def walk(routes, prefix=""):
        for route in routes:
            if isinstance(route, Mount):
                walk(route.routes, _joined_path(prefix, route.path))
                continue
            if not isinstance(route, (APIRoute, APIWebSocketRoute)):
                continue
            path = _joined_path(prefix, route.path)
            if not path.startswith("/api/v1/"):
                continue
            methods = ",".join(sorted(getattr(route, "methods", ()) or ())) or "WS"
            order.append("%s %s -> %s.%s" % (methods, path,
                                             route.endpoint.__module__,
                                             route.endpoint.__qualname__))

    walk(main.app.routes)
    return order


def _shadowing_pairs(order):
    """Pairs where an earlier dynamic path can swallow a later literal one.

    The concrete harm, not a general worry about ordering: `/a/{x}` registered
    before `/a/search` means `/a/search` is dead."""
    parsed = []
    for position, line in enumerate(order):
        methods, path = line.split(" ", 1)[0], line.split(" ")[1]
        parsed.append((position, frozenset(methods.split(",")), path.split("/")))
    pairs = []
    for early, early_methods, early_parts in parsed:
        if not any(part.startswith("{") for part in early_parts):
            continue
        for late, late_methods, late_parts in parsed:
            if late <= early or not (early_methods & late_methods):
                continue
            if len(early_parts) != len(late_parts):
                continue
            if all(a == b or (a.startswith("{") and not b.startswith("{"))
                   for a, b in zip(early_parts, late_parts)):
                pairs.append((order[early], order[late]))
    return pairs


def _manifest_id(entry):
    return {key: entry[key] for key in ("path", "methods", "module", "qualname")}


def _load_manifest():
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    identity_fields = document["identity_fields"]
    assert identity_fields == ["path", "methods", "module", "qualname"]
    static_review_fields = document["static_review_fields"]
    assert static_review_fields == ["source_sha1"]
    entries = []
    for group in document["groups"]:
        classification = group["classification"]
        route_fields = identity_fields + (
            static_review_fields if classification == "statically-nonconsumer" else []
        )
        for route_values in group["routes"]:
            entry = dict(zip(route_fields, route_values, strict=True))
            entry["classification"] = group["classification"]
            entry["reason"] = group["reason"]
            entries.append(entry)
    return entries


def test_route_manifest_net_seat_is_exhaustive_and_fails_closed_on_drift():
    import fastapi
    assert fastapi.__version__ == PINNED_FASTAPI, (
        f"route enumeration requires fastapi=={PINNED_FASTAPI} (installed {fastapi.__version__})"
    )
    manifest = _load_manifest()
    live_routes = _route_identities(main.app.routes)
    actual = [_manifest_id(entry) for entry in live_routes]
    expected = sorted(
        (_manifest_id(entry) for entry in manifest),
        key=lambda item: (
            item["path"],
            item["methods"],
            item["module"],
            item["qualname"],
        ),
    )

    assert actual == expected
    # main d889294's history: 886bed8 r5: +1, the read-only team series status route (377 before); card trading: +7 (the five player trade routes and the two admin trade routes; 370 before); Discord collection reveal: +4 (the packs JSON and strip image routes, the binder JSON and page image routes; 366 before); title-ladder read route: +1 (365 before); quarantine triage: +3 (the two admin triage views and the internal digest; 362 before); Sept 12 pack history: +1 (361 before); portraits: +9 (the writer, the admin clear, the lease triple, four face routes; 352 before); Sept 10 Player Cards: +15 (pc/*, admin/pc/snapshot, internal/pc/*); room rules: +3 (334 before)
    # lane be70f04's history: connect-failure: +4 (the three assembly routes and the G3 seat admin route; 366 before); title-ladder read route: +1 (365 before); quarantine triage: +3 (the two admin triage views and the internal digest; 362 before); Sept 12 pack history: +1 (361 before); portraits: +9 (the writer, the admin clear, the lease triple, four face routes; 352 before); Sept 10 Player Cards: +15 (pc/*, admin/pc/snapshot, internal/pc/*); room rules: +3 (334 before)
    # connect-failure LAND (2026-09-29): main d889294's 378 + the lane's 4 new routes, the union, confirmed by the re-pin dry run
    # main cd8d846's history (via claude/janitor-selftest 17ca44d): dance cards: +5 (the motion upload, the selection, the motion read, the atlas, the motion preview GIF; 378 before); 886bed8 r5: +1, the read-only team series status route (377 before); card trading: +7 (the five player trade routes and the two admin trade routes; 370 before); Discord collection reveal: +4 (the packs JSON and strip image routes, the binder JSON and page image routes; 366 before); title-ladder read route: +1 (365 before); quarantine triage: +3 (the two admin triage views and the internal digest; 362 before); Sept 12 pack history: +1 (361 before); portraits: +9 (the writer, the admin clear, the lease triple, four face routes; 352 before); Sept 10 Player Cards: +15 (pc/*, admin/pc/snapshot, internal/pc/*); room rules: +3 (334 before)
    # lane side before sitting 3: 387 (connect-failure LAND, sitting 2 (2026-09-30): main cd8d846's 383 + the lane's 4 new routes, the union, confirmed by the re-pin dry run)
    # main 0e751993's side: 384 (LAND of main cd8d846: dance cards' +5 (the motion upload, the selection, the motion read, the atlas, the motion preview GIF; 379 before); LAND of main 82c0da6: 886bed8 r5's +1, the read-only team series status route (378 before); Discord fix round 1: +1 (the bot's pack open, internal/pc/packs/open; 377 before); card trading: +7 (the five player trade routes and the two admin trade routes; 370 before); Discord collection reveal: +4 (the packs JSON and strip image routes, the binder JSON and page image routes; 366 before); title-ladder read route: +1 (365 before); quarantine triage: +3 (the two admin triage views and the internal digest; 362 before); Sept 12 pack history: +1 (361 before); portraits: +9 (the writer, the admin clear, the lease triple, four face routes; 352 before); Sept 10 Player Cards: +15 (pc/*, admin/pc/snapshot, internal/pc/*); room rules: +3 (334 before))
    # connect-failure LAND, sitting 3 (2026-09-30): the union of the lane's 387 and main 0e751993's 384 over
    # their shared 383 (main cd8d846) is 388: the lane's 4 new routes plus the Discord fix's 1, confirmed by
    # the re-pin dry run
    # seat evidence V2 (claude/seat-evidence-server-v2): +4 (the seat record and compat outcome routes, the
    # admin seat-evidence view and the release digest registration; 388 before)
    # combat evidence (claude/combat-evidence-server): +2 (the combat record route and the admin
    # combat-evidence view; 392 before)
    assert len(manifest) == 394
    assert len({json.dumps(item, sort_keys=True) for item in expected}) == len(expected)
    assert all(
        entry["classification"] in {"sentinel-exercised", "statically-nonconsumer"}
        for entry in manifest
    )
    assert all(isinstance(entry["reason"], str) and entry["reason"].strip() for entry in manifest)

    exercised = [entry for entry in manifest if entry["classification"] == "sentinel-exercised"]
    static = [entry for entry in manifest if entry["classification"] == "statically-nonconsumer"]
    assert len(exercised) == 1
    # main d889294's history: 886bed8 r5: +1, the read-only team series status route -- a fixed projection of team_series columns, no private Match column reachable (376 before); card trading: +7 (369 before); Discord collection reveal: +4 (365 before); title-ladder read route: +1 (364 before); quarantine triage: +3 (361 before); Sept 12 pack history: +1 (360 before); portraits: +9 (351 before); Sept 10 Player Cards: +15; room rules: +3 (333 before)
    # lane be70f04's history: connect-failure: +4 (365 before); title-ladder read route: +1 (364 before); quarantine triage: +3 (361 before); Sept 12 pack history: +1 (360 before); portraits: +9 (351 before); Sept 10 Player Cards: +15; room rules: +3 (333 before)
    # connect-failure LAND (2026-09-29): main d889294's 377 + the lane's 4 (all statically-nonconsumer), confirmed by the re-pin dry run
    # main cd8d846's history (via claude/janitor-selftest 17ca44d): dance cards: +5 (377 before); 886bed8 r5: +1, the read-only team series status route -- a fixed projection of team_series columns, no private Match column reachable (376 before); card trading: +7 (369 before); Discord collection reveal: +4 (365 before); title-ladder read route: +1 (364 before); quarantine triage: +3 (361 before); Sept 12 pack history: +1 (360 before); portraits: +9 (351 before); Sept 10 Player Cards: +15; room rules: +3 (333 before)
    # lane side before sitting 3: 386 (connect-failure LAND, sitting 2 (2026-09-30): main cd8d846's 382 + the lane's 4 (all statically-nonconsumer), confirmed by the re-pin dry run)
    # main 0e751993's side: 383 (LAND of main cd8d846: dance cards' +5 (378 before); LAND of main 82c0da6: 886bed8 r5's +1, the read-only team series status route -- a fixed projection of team_series columns, no private Match column reachable (377 before); Discord fix round 1: +1 (376 before); card trading: +7 (369 before); Discord collection reveal: +4 (365 before); title-ladder read route: +1 (364 before); quarantine triage: +3 (361 before); Sept 12 pack history: +1 (360 before); portraits: +9 (351 before); Sept 10 Player Cards: +15; room rules: +3 (333 before))
    # connect-failure LAND, sitting 3 (2026-09-30): the union of the lane's 386 and main 0e751993's 383 over
    # their shared 382 is 387: the lane's 4 plus the Discord fix's 1 (all statically-nonconsumer), confirmed
    # by the re-pin dry run
    # seat evidence V2 (claude/seat-evidence-server-v2): +4, all statically-nonconsumer (387 before)
    # combat evidence (claude/combat-evidence-server): +2, both statically-nonconsumer (391 before)
    assert len(static) == 393
    assert _manifest_id(exercised[0]) == SENTINEL_ROUTE

    actual_by_identity = {
        json.dumps(_manifest_id(entry), sort_keys=True): entry for entry in live_routes
    }
    for entry in static:
        identity = _manifest_id(entry)
        live = actual_by_identity[json.dumps(identity, sort_keys=True)]
        assert entry["source_sha1"] == live["source_sha1"], (
            f"{identity['methods']} {identity['path']} source fingerprint changed; "
            "re-review this handler"
        )


def test_the_helper_surface_is_computed_and_not_hand_curated():
    """r11. The coverage rule was a dict with one entry, so it failed exactly
    where it was written to help: this range moved _pick_room_region, which
    decides the region both seats of a pair are told to connect to, and the two
    routes that return it kept their pre-range fingerprints because their own
    source had not changed. A list of exceptions is a hole the next extraction
    reopens silently."""
    assert not hasattr(main, "ROUTE_HELPER_DEPENDENCIES")
    assert "ROUTE_HELPER_DEPENDENCIES" not in MODULE_SRC, (
        "the hand-curated list came back"
    )
    # The closure is real: the two queue routes now carry the region helpers
    # they delegate to, transitively.
    for route_name, expected in (
        ("queue_poll", {"_pick_room_region", "_region_agreed", "_region_corroborated"}),
        ("queue_ready", {"_pick_room_region", "_region_agreed", "_region_corroborated"}),
        # the sighting moved off queue_join in r13: an established session
        # binds the speaker, not the region named in the sentence
        ("submit_match", {"_note_region_seen", "_region_token"}),
    ):
        closure = set(_helper_closure(getattr(main, route_name)))
        want = {("main", name) for name in expected}
        assert want <= closure, (
            f"{route_name} does not cover {sorted(want - closure)}"
        )

    # r12 MEDIUM: and the closure leaves `main`. A tournaments route reaches
    # the tournaments helpers that compose its response, so editing one of
    # those moves that route's fingerprint.
    tournament_routes = [
        r for r in main.app.routes
        if isinstance(r, APIRoute)
        and getattr(r.endpoint, "__module__", "") == "tournaments"
    ]
    assert tournament_routes, "the tournaments router is part of this app"
    crossed = [(m, n) for r in tournament_routes
               for (m, n) in _helper_closure(r.endpoint) if m != "main"]
    assert crossed, "the closure never left main -- helpers there are unfingerprinted"

    # r13 MEDIUM: and it reaches helpers that are IMPORTED rather than defined
    # in the module serving the route. `tournaments` calls
    # tournament_bracket.build_double_elim_bracket from a route; keeping only
    # functions whose __module__ matched the module they were found in put that
    # function -- which decides a bracket's shape -- in no fingerprint at all.
    imported = [ident for r in tournament_routes
                for ident in _helper_closure(r.endpoint)
                if ident[0] not in ("main", "tournaments")]
    assert imported, "the closure never left the two route-serving modules"


def test_a_helper_in_another_module_moves_its_routes_fingerprint():
    """The mutation the previous test's shape is for. Edit a binding in
    `tournaments` that a route reaches and that route's source_sha1 must move;
    the negative control is the same route with nothing edited."""
    target = None
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if getattr(route.endpoint, "__module__", "") != "tournaments":
            continue
        reached = [n for (m, n) in _helper_closure(route.endpoint) if m == "tournaments"]
        if reached:
            target = (route, sorted(reached)[0])
            break
    assert target, "no tournaments route reaches a tournaments binding"
    route, name = target

    before = _route_fingerprint(route)
    assert before == _route_fingerprint(route), (
        "negative control: unedited source must not move"
    )
    with _mutated_segment("tournaments", name):
        after = _route_fingerprint(route)
    assert after != before, (
        f"editing tournaments.{name} left {route.path} certified unchanged"
    )
    assert _route_fingerprint(route) == before, (
        "the mutation did not unwind -- every later assertion in this file "
        "would be reading a poisoned memo"
    )


def test_the_helper_closure_stays_affordable():
    """A fingerprint that pulls half the app in drifts on every commit, and a
    gate that always fires is a gate nobody reads.

    MEASURED when these bounds were set (Sept 4 batch, r14 M7) at the shipped
    two-tier rule: median 15, p90 49, worst 190 (/api/v1/matches) of 1282
    indexed bindings, with the walk itself taking 0.1 s once the index is built
    (~5.3 s, once per process). The bounds below sat above those with room, so
    this fails on a walk that has gone wrong rather than on ordinary growth;
    the worst-route bounds, and the two p90 bounds (on the card trading lane
    and, independently and to the same values, at the Discord collection
    landing, then at the merge of the two), have since moved for measured
    growth in bindings routes really run, each move recorded with its
    measurement at its assertion.

    The second tier is exactly what these numbers pay for. Expanding data
    bindings as well as def/class ones makes `app = FastAPI(...)` a hub that
    every route decorator references, and the same measurement gives median
    179 / worst 279 -- every route dragging in most of the app, which is a
    fingerprint that certifies nothing because it always moves."""
    routes = [r for r in main.app.routes
              if isinstance(r, APIRoute) and r.path.startswith("/api/v1/")]
    assert routes
    total = sum(len(names) for names in _binding_index().values())

    def percentiles(counts):
        counts = sorted(counts)
        return (counts[len(counts) // 2],
                counts[min(len(counts) - 1, int(len(counts) * 0.9))],
                counts[-1])

    reached = [_reached(_route_seeds(route)) for route in routes]
    code_median, code_p90, code_worst = percentiles(
        sum(1 for kind in r.values() if kind != "import") for r in reached)
    all_median, all_p90, all_worst = percentiles(len(r) for r in reached)

    # The CODE tier is the one that drifts, and the r15 repairs left its bounds
    # alone: measured 20 / 55 / 198 with data-into-data expansion, against
    # 16 / 48 / 191 before it.
    assert code_median <= 24, f"median code closure {code_median} of {total}"
    # Discord collection landing (2026-09-26): the p90 moved for measured
    # growth. The same walk with the same route seeds over each tree:
    #
    #   tree                               routes   code median / p90 / worst
    #   main 9a1dd9d                          365   21 / 69 / 326
    #   lane 5868131                          369   21 / 73 / 326
    #   LAND-1 74af3f6 (7541261 merged)       369   21 / 73 / 326
    #   LAND-2 852f4be through 9f52e03        369   21 / 76 / 326
    #
    # Main alone passes and the lane alone passes; the landed tree is the sum
    # of the two landings. The p90 is a rank statistic -- the value at sorted
    # position int(0.9 * n) -- and it moved while the route AT that position
    # did not: GET /api/v1/admin/quarantine/triage/{mode}/{group_id} measures
    # 76 on every tree above. What moved is how many routes sit above 75: 37
    # of 369 on the landed tree, exactly the count that puts position 332 on
    # that route (main: 33 of 365; the lane: 35 of 369). Four of the 37 are
    # the lane's new internal routes: the collection binder (117) and its page
    # image (280), the pack list (123) and its strip image (280), the two
    # images reaching the card-face rendering their tiles are composited from.
    # Two crossed 75 on main's title-ladder hook: POST
    # /api/v1/team/series/{series_id}/report-dc 72 -> 80 and POST
    # /api/v1/admin/team/series/{series_id}/resolve 74 -> 82, each +8 in
    # title_ladders (record_completed_games, the three lookups it runs and the
    # four rung tables they read) -- the ladder credit their completion paths
    # now give. Every one is a binding its route really runs, and the median
    # has not moved, which is where a walk gone wrong shows first (the hub
    # case in the docstring measured median 179).
    #
    # The bound moves to 80, 5% over the measurement -- the ~5-6% headroom the
    # worst bounds keep over theirs; the median and worst bounds stay.
    #
    # Card trading LAND (2026-09-27): measured 21 / 76 / 326 of 2654 indexed
    # bindings over 372 routes at the merge of main 9a1dd9d into the trading
    # lane, against 21 / 73 / 326 over the lane tip 93227a8 (372 routes) and
    # 21 / 69 / 326 over main 9a1dd9d (365 routes), the same walk with the
    # same route seeds over each tree's own backend/api. Neither side passes
    # 75; the composition does. The ladder hook gives two routes at the
    # lane's p90 rank the eight title_ladders bindings a rated completion
    # really runs (POST /api/v1/team/series/{series_id}/report-dc 72 -> 80,
    # POST /api/v1/admin/team/series/{series_id}/resolve 74 -> 82), both rise
    # past the rank, and the 90th percentile becomes the next route up, GET
    # /api/v1/admin/quarantine/triage/{mode}/{group_id} at 76, unchanged
    # itself. On main alone the rank sits lower (69); the five player trade
    # routes above it are what put it in this band.
    #
    # The bound moves to 80 -- ~5% over the measurement, the headroom the
    # other moves in this test gave -- for that reason and no other; the
    # median and worst bounds stay.
    #
    # The two moves above were made independently, one on each side of the
    # merge of main 36e8493 into the card trading lane (2026-09-27), and both
    # chose 80.
    #
    # Card trading LAND, second merge (2026-09-27): measured 22 / 82 / 326
    # of 2716 indexed bindings over 376 routes at the merge of main 36e8493
    # into the trading lane (9a5b081), against 21 / 76 / 326 over the lane
    # tip a666517 (372 routes) and over main 36e8493 (369 routes), the same
    # walk with the same route seeds over each tree's own backend/api.
    # Neither side passes 80; the composition does, by rank alone. The p90
    # is the value at sorted position int(0.9 * n), the 38th route from the
    # top at n = 376. Each side adds routes far above it -- the lane its five
    # player trade routes (132 to 158), main its four collection routes (117
    # to 280) -- and each side alone keeps 76 at its rank (37 and 36 routes
    # above 76); the merged tree carries all nine, 38 routes sit above 80,
    # and the 38th from the top is POST
    # /api/v1/admin/team/series/{series_id}/resolve at 82, 82 on both sides
    # too. No count is the merge's own: every route measures what it
    # measures on the side that has it (the six that differ from main are
    # the lane's trading reads, at their lane counts).
    #
    # The bound moves to 86 -- ~5% over the measurement, the headroom the
    # moves above gave -- for that reason and no other; the median (22) and
    # worst bounds stay.
    #
    # Connect-failure lane (2026-09-27): the p90 moved for measured growth.
    # The same walk with the same route seeds over each tree's own
    # backend/api:
    #
    #   tree                               routes   code median / p90 / worst
    #   main 9a1dd9d                          365   21 / 69 / 326
    #   lane f25c084 (api code)               369   21 / 76 / 326
    #
    # The p90 is a rank statistic, the value at sorted position int(0.9 * n),
    # and it moved while no route near that position did: 37 of 369 routes
    # sit above 75 on the lane (33 of 365 on main), which puts position 332
    # on GET /api/v1/admin/quarantine/triage/{mode}/{group_id}, 76 on both
    # trees. The four that crossed are the lane's three new assembly routes
    # (POST /api/v1/ffa/lobby/{lobby_id}/connect 268, .../assembly 266 and
    # .../release 93) and POST /api/v1/ffa/queue/leave, 53 -> 234: the leave
    # now runs the assembly leave plan (the gone test and its witness census,
    # the dissolve with the closers' record, and the re-form, which locks the
    # next roster through the start's own _ffa_lock_roster, with its region
    # pick, wager binding and titles). Every one is a binding its route
    # really runs, and the median has not moved.
    #
    # The bound moves to 80, ~5% over the measurement; the median and worst
    # bounds stay.
    #
    # Connect-failure LAND, merge main d889294 into the lane (2026-09-29):
    # the same walk with the same route seeds over each tree's own
    # backend/api:
    #
    #   tree                               routes   code median / p90 / worst
    #   fork 9a1dd9d                          365   21 / 69 / 326
    #   main d889294                          377   21 / 82 / 326
    #   lane be70f04                          369   21 / 76 / 326
    #   merge a234c91 (measured at 8652bdf)   381   22 / 83 / 326
    #
    # Neither side passes 83; the composition does, by rank alone. At
    # n = 381 the p90 is the 39th route from the top and 38 routes sit above
    # 83 on the merged tree: main's nine trade and collection routes (117 to
    # 280) and the lane's four (POST /api/v1/ffa/lobby/{lobby_id}/connect
    # 268, .../assembly 266, .../release 93, and POST
    # /api/v1/ffa/queue/leave, 53 on main and 234 on the lane) are above it
    # together for the first time. The route at the rank is GET
    # /api/v1/spectate/games, 83 on both sides too. No count is the merge's
    # own: checked route by route, every count at the merge is main's plus
    # the lane's minus the fork's (or the one side's, for a route only one
    # side has); the median moves 21 -> 22 the same way, by rank, under its
    # bound of 24.
    #
    # The bound moves to 88 -- ~6% over the measurement, the headroom the
    # moves above gave -- for that reason and no other; the median and
    # worst bounds stay.
    #
    # Connect-failure LAND, sitting 2, merge claude/janitor-selftest 17ca44d
    # (main cd8d846, the dance cards) into the lane (2026-09-30): the same
    # walk with the same route seeds over each tree's own backend/api:
    #
    #   tree                               routes   code median / p90 / worst
    #   base 82c0da6                          377   21 / 82 / 326
    #   lane e966ed7                          381   22 / 83 / 326
    #   trunk 17ca44d                         382   22 / 83 / 326
    #   merge c8ffa2f                         386   22 / 90 / 326
    #
    # Again the rank alone: at n = 386 the p90 is the 39th route from the
    # top. The trunk's five dance motion routes (the motion PNG 285, the
    # motion preview GIF 282, GET /api/v1/pc-face/motion 125, POST
    # /api/v1/pc/portrait/motion 118, POST /api/v1/pc/dance 32) now sit in
    # the ranking beside the lane's four (connect 268, assembly 266, release
    # 93, POST /api/v1/admin/ffa-g3-seats 14): four of the trunk's five are
    # above the lane's rank and three of the lane's four above the trunk's,
    # and the route at the rank is now GET /api/v1/ovt/queue/poll/{steam_id}
    # at 90 (90 on both sides), with the lane's release at 93 just above it.
    # Checked route by route, every count at the merge is the trunk's plus
    # the lane's minus the base's (or the one side's, for a route only one
    # side has): the merge adds no binding of its own. The bound moves to 95,
    # ~6% over the measurement, for that reason and no other; the median and
    # worst bounds stay (22 against 24, 326 against 335).
    #
    # Discord fix round 4 LAND (2026-09-30): measured 22 / 88 / 328 of 2940
    # indexed bindings over 383 routes at the lane tip after its merges of
    # main 82c0da6 and cd8d846, against 22 / 85 / 328 over the lane before
    # them (ceddd3d, 377 routes) and 22 / 83 / 326 over main cd8d846 (382
    # routes), the same walk with the same route seeds over each tree's own
    # backend/api. Neither side passes 86; the composition does. The p90 is
    # the value at sorted position int(0.9 * n), the 39th route from the top
    # at n = 383. The lane's tournament routes keep their lane counts, above
    # main's (signup 95 / 88, unsignup 90 / 82, time-vote 85 / 82, play-now
    # 83 / 79, spectate/games 87 / 83: the row-32 start rule and round 4's
    # one eligibility predicate), and main's dance cards add five routes and
    # take POST /api/v1/pc/portrait from 86 to 88 (its motion writer); the
    # 39th from the top is that route, at 88, 88 on main. Every count is the
    # one its side measures; the only composed count, GET /api/v1/health (83:
    # both sides' health words), sits below the rank.
    #
    # The bound moves to 92 -- ~5% over the measurement, the headroom the
    # moves above gave -- for that reason and no other; the median (22) and
    # worst bounds stay.
    #
    # Connect-failure LAND, sitting 3, merge main 0e751993 (the Discord fix)
    # into the lane (2026-09-30): the same walk with the same route seeds over
    # each tree's own backend/api:
    #
    #   tree                               routes   code median / p90 / worst
    #   base 69a3599b                         382   22 / 83 / 326
    #   lane a7e3d385                         386   22 / 90 / 326
    #   trunk 0e751993                        383   22 / 88 / 328
    #   merge                                 387   22 / 95 / 328
    #
    # At n = 387 the p90 is sorted position 348, and it holds POST
    # /api/v1/tournaments/{tournament_id}/signup at 95, the trunk's own count
    # (88 on the lane and the base); the lane's release (93) and the trunk's
    # unsignup (90) sit just below it. Route by route, every count at the
    # merge is the trunk's plus the lane's minus the base's (or the one side's,
    # for a route only one side has) except four lane routes, each +4 over
    # the lane: POST /api/v1/ffa/queue/leave, .../connect, .../assembly and
    # GET /api/v1/ffa/queue/poll/{steam_id}. Those four reach
    # tournaments._build_current_response, which the trunk changed to reach
    # _eligible_slot_tallies, _ELIGIBLE_SLOT_TALLY_SQL, _ELIGIBLE_ENTRANT_SQL
    # and MIN_SLOT_NOTICE_HOURS; the trunk's copies of those routes do not
    # reach it, so the four bindings appear only when both sides are present.
    # None of the four routes is at the rank. The bound moves to 100, ~5% over
    # the measurement, for that reason and no other; the median and worst
    # bounds stay (22 against 24, 328 against 335).
    #
    # Discord card render parity LAND, merge main 5062f4c4 (the
    # connect-failure landing) into the lane (2026-10-01): the same walk with
    # the same route seeds over each tree's own backend/api:
    #
    #   tree                               routes   code median / p90 / worst
    #   base 0e751993                         383   22 / 88 / 328
    #   lane fb9081c2                         383   22 / 90 / 370
    #   trunk 5062f4c4                        387   22 / 95 / 328
    #   merge                                 387   22 / 105 / 370
    #
    # Route by route, every count at the merge is the trunk's plus the lane's
    # minus the base's (the trunk's, for its four new routes); no binding
    # appears only when both sides are present. A rank effect: two routes
    # that sat below the trunk's p90 crossed it with the lane's card art
    # layer -- GET /api/v1/health 89 -> 265 (the pc_card_art self-test draws a
    # face) and POST /api/v1/pc/portrait 88 -> 126 (the lane's card art
    # bindings it reaches) -- so position 348 moves two ranks up the trunk's own ordering,
    # from POST /api/v1/tournaments/{tournament_id}/signup (95, unmoved) to
    # POST /api/v1/spectate/grant (105, unmoved on every tree). 39 routes sit
    # above 100 on the merge, 35 on the trunk. The bound moves to 111, ~6%
    # over the measurement, for that reason and no other; the median and
    # worst bounds stay (22 against 24, 370 against 380).
    assert code_p90 <= 111, f"p90 code closure {code_p90} of {total}"
    # Player Cards v4.13 (2026-09-15): measured 20 / 64 / 278 on e894c45 and
    # 20 / 64 / 282 on the v4.13 fold, the worst both times POST
    # /api/v1/pc/packs/open. What it gained are bindings that route runs: the
    # shared SteamID64 check (is_individual_id and its three constants, +4, in
    # place of the two id regexes, -2) and the pool membership word with its
    # Steam id clause (+2). That moved the worst bound to 300.
    #
    # Sept 14 batch merge (2026-09-15): measured 21 / 64 / 315 of 2319 indexed
    # bindings, the worst still POST /api/v1/pc/packs/open. The same walk with
    # the same route seeds over MAIN's backend/api gives 21 / 64 / 282, so the
    # merge's own delta is +33 on the worst route and 0 on the median and p90.
    #
    # All 33 are bindings that DID NOT EXIST on main, and nothing main reached
    # stopped being reached: 18 in pc_face (the autograph layout -- _autograph_box,
    # _hex_rgb, _sign_case/_fill/_ink_height/_layout/_mask/_pieces/_style/_width
    # and the eight _SIGN_* constants) and 15 in the new pc_signature module
    # (signature_style, _hex and the style tables it decides from). That is the
    # signed-print face work, which this route runs when an opened pack mints a
    # signed print.
    #
    # It is NOT the pool predicate, and the pool predicate cannot move this
    # number: the clause the merge added to _PC_POOL_MEMBER_SQL
    # (`p.mod_seen_at IS NOT NULL`) is literal SQL inside a data binding and
    # names nothing the walk can follow. The +2 the v4.13 note above counts is
    # the two data bindings themselves, and there are still exactly two.
    #
    # The bound moves to 335 -- the same ~6% headroom over the measurement that
    # 300 gave over 282 -- so it goes on failing a walk that has gone wrong (the
    # data-into-data hub case measured worst 279 at MEDIAN 179, i.e. a runaway
    # shows up in the median long before it shows up here) rather than on a
    # feature module a route genuinely runs. The median and p90 bounds stay.
    #
    # Discord card render parity (2026-10-01): the same walk with the same
    # route seeds measured 22 / 88 / 328 of 2949 over main 0e75199's
    # backend/api and 22 / 90 / 357 of 2988 over the lane tip, the worst still
    # POST /api/v1/pc/packs/open. Its +29 are all bindings that did not exist
    # on main, all in pc_face -- the card art layer (_draw_badge_art,
    # card_art_bundle/_patch/_names/_check_entry/_index_bytes, the bundle
    # reader's _card_art_* helpers, the CardArtBundle record, top_card_name,
    # _kit_pngs and the CARD_ART_* / _CARD_ART_* constants) -- and nothing
    # main reached stopped being reached. 26 routes moved, none shrank: the
    # face, strip, grid, motion and pack routes by 25 to 41 each, and GET
    # /api/v1/health by 163 (87 -> 250), because the pc_card_art health word
    # runs card_art_selftest, which draws a face to prove the layer. The
    # bound moves to 380, ~6% over the measurement, for that reason and no
    # other; the median and p90 bounds stay.
    assert code_worst <= 380, f"worst code closure {code_worst} of {total}"

    # Imports are counted separately rather than folded in or waved through.
    # They roughly triple the closure -- measured 69 / 119 / 308 -- and that is
    # honest, because a route really does reference ~40 imported names. What
    # they do not triple is the DRIFT: an import line changes far more rarely
    # than the code around it. A walk that has gone wrong still has to fail
    # here, so the bound is real and not merely raised to fit.
    #
    # Binding-resolved closure (2026-10-02): until then a bare name was
    # resolved in every indexed module and an attribute by its last part alone,
    # so the combat evidence lane's two modules -- importing text, datetime,
    # hashlib, hmac and json, and defining a `dumps` that every `json.dumps`
    # matched -- grew 386 of 391 existing routes and took this median from 86
    # (base 43a6316c) to 92. Each reference now resolves to the binding it
    # denotes (`_resolve`). The same walk measures 45 / 137 / 457 all kinds and
    # 22 / 88 / 369 code over base 43a6316c (391 routes) AND over the lane tip
    # (393 routes): identical, and the only existing routes whose closure moved
    # are the two whose code the lane changed (health and the seat record).
    # The difference from 86 is what the old walk charged by name alone: on
    # the lane tip it dropped 243 code and data bindings, each a same-named
    # binding the route's code does not name (main._PNG_MAX_CHUNKS reached
    # through pc_face's own, title_ladders.router through tournaments' own),
    # and reached 24 it had missed: imported helpers it treated as leaves
    # (region_pick's selection rule behind main's import of
    # pick_region_for_group). The bound stays.
    assert all_median <= 90, f"median closure {all_median} of {total}"
    # Card trading (2026-09-26): measured 73 / 151 / 457 of 2648 indexed
    # bindings over 372 routes, against 72 / 140 / 457 of 2567 over 365 for
    # the same walk with the same route seeds over main 7541261's backend/api.
    # The same walk over this tree WITHOUT the seven trade routes gives
    # 72 / 140 / 457 again, so the move is those seven routes and nothing
    # else. (The code tier: p90 69 -> 73, median 21 and worst 326 unmoved,
    # all under the bounds above, which stay.)
    #
    # The five player trade routes reach 229 to 257 bindings each, 83 of them
    # in the face modules, and they enter those modules through the bindings
    # GET /api/v1/pc/collection enters them through (_pc_print_dict,
    # _pc_face_inputs, _pc_labels, _pc_face_ctx, _pc_locale, _pc_renderer_fp;
    # the same 83 face-module bindings): a trade answers with the binder's
    # own print projection. The two admin trade routes reach 91 and 73. Seven
    # routes join a population of 365, five of them above the old p90, and
    # the 90th percentile moves from 140 to 151.
    #
    # The bound moves to 160 -- ~6% over the measurement, the headroom 335
    # gave over 315 and 300 over 282 at the code-worst moves -- for that
    # reason and no other. A walk that has gone wrong still fails at the
    # median bounds first (the data-into-data hub case measured median 179),
    # and those stay, as does the worst bound.
    #
    # Discord collection landing (2026-09-26): the same walk, whole closure:
    #
    #   tree                               routes   median / p90 / worst
    #   main 9a1dd9d                          365   72 / 140 / 457
    #   lane 5868131                          369   73 / 150 / 457
    #   LAND-1 74af3f6 (7541261 merged)       369   73 / 151 / 457
    #   LAND-2 852f4be through 9f52e03        369   73 / 151 / 457
    #
    # The same rank effect as the code p90 above, and it crossed at the first
    # landing: 37 of 369 routes sit above 150 on the landed tree (main: 33 of
    # 365; the lane: 36 of 369), which puts position 332 on POST
    # /api/v1/ovt/matches, 151 on every tree above. Four of the 37 are the
    # lane's new internal routes (216, 410, 222, 409); the one that crossed on
    # main is POST /api/v1/team/series/{series_id}/report-dc, 146 -> 153 on
    # the lead-forfeit hotfix -- seven code bindings, _team_game_crossed_two
    # with the four helpers and two constants beside it, the per-game
    # evidence that route now settles from. The bound moves to 160, 6% over
    # the measurement; the median and worst bounds stay.
    #
    # The two moves above were made independently, one on each side of the
    # merge of main 36e8493 into the card trading lane (2026-09-27), and both
    # chose 160.
    #
    # Card trading LAND, second merge (2026-09-27): measured 75 / 164 / 459
    # over the same 376 routes of the merge 9a5b081, against 75 / 153 / 459
    # over the lane tip a666517 and 73 / 151 / 457 over main 36e8493. The
    # same rank effect as the code p90: 38 routes sit above 160 on the
    # merged tree, nine of them the two sides' new routes, and the 38th from
    # the top is POST /api/v1/team/series/{series_id}/report-dc at 164 (162
    # on main; the +2 is models.deferred and models.text, the two import
    # bindings F63's Player mapping added, which every route reaching the
    # model reaches). The bound moves to 174, ~6% over the measurement; the
    # median and worst bounds stay (the worst route, POST
    # /api/v1/pc/packs/open, measures 459 against 460).
    #
    # Connect-failure lane (2026-09-27), the same walk, whole closure:
    #
    #   tree                               routes   median / p90 / worst
    #   main 9a1dd9d                          365   72 / 140 / 457
    #   lane f25c084 (api code)               369   73 / 151 / 457
    #
    # The same rank effect as the code p90 above: 37 of 369 routes sit above
    # 150 (33 of 365 on main), which puts position 332 on POST
    # /api/v1/ovt/matches, 151 on both trees. The four that crossed are the
    # same four: connect 377, assembly 375, release 152, and POST
    # /api/v1/ffa/queue/leave 118 -> 341. The bound moves to 160, ~6% over
    # the measurement; the median and worst bounds stay.
    #
    # Connect-failure LAND, merge main d889294 into the lane (2026-09-29),
    # the same walk, whole closure:
    #
    #   tree                               routes   median / p90 / worst
    #   fork 9a1dd9d                          365   72 / 140 / 457
    #   main d889294                          377   75 / 165 / 459
    #   lane be70f04                          369   73 / 151 / 457
    #   merge a234c91 (measured at 8652bdf)   381   76 / 167 / 459
    #
    # The same rank effect as the code p90 above: 37 routes sit above 167 on
    # the merged tree, and the 39th from the top is GET
    # /api/v1/spectate/games (with POST
    # /api/v1/tournaments/{tournament_id}/matches/{match_id}/play-now) at
    # 167, 167 on main too and 165 on the lane. Above it sit main's nine new
    # routes and the lane's connect (379), assembly (377) and POST
    # /api/v1/ffa/queue/leave (343; 120 on main), beside GET
    # /api/v1/ffa/queue/poll/{steam_id} (377 on the merge, 183 on main).
    # Every count on a route both sides have is main's plus the lane's minus
    # the fork's; the lane's four new routes each measure 1 or 2 above their
    # lane counts (connect 377 -> 379, assembly 375 -> 377, release
    # 152 -> 153, POST /api/v1/admin/ffa-g3-seats 54 -> 55): models.text on
    # all four and models.deferred on connect and assembly, the import
    # bindings main's Player mapping added, which every route reaching the
    # model reaches. The bound moves to 177, ~6% over the measurement; the
    # median and worst bounds stay (the worst route measures 459 against
    # 460).
    #
    # Connect-failure LAND, sitting 2, merge claude/janitor-selftest 17ca44d
    # (main cd8d846) into the lane (2026-09-30), the same walk, whole
    # closure:
    #
    #   tree                               routes   median / p90 / worst
    #   base 82c0da6                          377   75 / 165 / 459
    #   lane e966ed7                          381   76 / 167 / 459
    #   trunk 17ca44d                         382   76 / 167 / 459
    #   merge c8ffa2f                         386   76 / 175 / 459
    #
    # The same rank effect: the trunk's five motion routes (397, 394, 216,
    # 204, 100) and the lane's four (connect 379, assembly 377, release 153,
    # admin G3 seats 55) are in one ranking, and the 39th from the top is
    # POST /api/v1/admin/team/series/{series_id}/resolve at 175, 175 on both
    # sides. Every count on a route both sides have is the trunk's plus the
    # lane's minus the base's. The measurement is inside the old bound of
    # 177 by 2; the bound moves to 185, ~6% over it, the headroom
    # convention of every entry above; the median and worst bounds stay (76
    # against 90, 459 against 460).
    #
    # Discord card render parity (2026-10-01): 76 / 171 / 461 over the 383
    # routes of main 0e75199, 76 / 177 / 490 over the lane tip. A rank
    # effect again: two routes that sat at or below main's p90 crossed it --
    # GET /api/v1/health 137 -> 332 (the pc_card_art self-test draws a face)
    # and GET /api/v1/internal/pc/face/back 157 -> 183 (the face module's art
    # layer) -- so position 344 moves from GET /api/v1/spectate/games (171,
    # unmoved) to POST /api/v1/ffa/lobby/start (177, unmoved). 40 routes sit
    # above 174 on the tip, 38 on main. The lane's bound was 188, ~6% over
    # that measurement; the median bound stayed.
    #
    # Discord card render parity LAND, merge main 5062f4c4 (the
    # connect-failure landing) into the lane (2026-10-01), the same walk,
    # whole closure:
    #
    #   tree                               routes   median / p90 / worst
    #   base 0e751993                         383   76 / 171 / 461
    #   lane fb9081c2                         383   76 / 177 / 503
    #   trunk 5062f4c4                        387   76 / 178 / 461
    #   merge                                 387   76 / 197 / 503
    #
    # Every count at the merge is the trunk's plus the lane's minus the
    # base's (the trunk's, for its four new routes). The same rank effect as
    # the code p90 above: GET /api/v1/health (139 on the trunk, 347 on the
    # merge) and GET /api/v1/internal/pc/face/back (157 -> 197) crossed the
    # trunk's p90, so position 348 is now the face back route itself at 197; POST /api/v1/spectate/grant (200,
    # unmoved on every tree) sits one rank above it. 39 routes sit above 185
    # on the merge, 36 on the trunk. The bound moves to 209, ~6% over the
    # measurement, for that reason and no other; the median and worst bounds
    # stay (76 against 90, 503 against 520).
    assert all_p90 <= 209, f"p90 closure {all_p90} of {total}"
    # Steam pictures (2026-09-12): a pack open now primes the subjects'
    # Steam pictures, and that chain (claim, feed, download, the bound write
    # and its blob locks) is ~20 real bindings on top of the face path the
    # route already reached -- measured 383 on /api/v1/pc/packs/open. The
    # bound moves to 400 for that reason and no other; p90 and the median
    # stay where they were.
    # Player Cards v4.13 (2026-09-15): the same route measured 394 on e894c45
    # and 401 on the v4.13 fold -- the code bindings above plus the three
    # import lines they are reached through (steamid64 in main, pc_steam and
    # pc_portrait); p90 126 -> 129, median 64. That moved the bound to 420.
    # Sept 14 batch merge (2026-09-15): the same route measured 439, against 401
    # for the same walk over MAIN's backend/api -- +38, and median 65 / p90 129
    # both unmoved. Of the 38, 33 are the signed-print face code bindings
    # accounted for at the code bound above; 4 are the import lines they arrive
    # through (main._pcsig, pc_face.ImageFilter, pc_face._SIGN_RAINBOW,
    # pc_signature.Iterable); and 1 is main.case -- sqlalchemy's `case`, already
    # imported, newly reached because the new signature code writes the bare
    # name `case` and the walk folds in EVERY module that binds a shared name.
    # That last one widens the reviewed surface rather than narrowing it, which
    # is the only direction this gate may be wrong in. The bound moves to 460,
    # the same ~5% headroom 420 gave over 401 and 400 gave over 383.
    # Discord fix (2026-09-28): the same route measured 459 at the lane base
    # 64885ef, 460 at the round-1 tip d4a284d and 461 at round 2's 12952d5 -
    # one code binding per round, each one the route really runs:
    # main._pc_open_for (round 1: the open path this route and the bot's
    # POST /api/v1/internal/pc/packs/open share, keyed by the purchase's
    # nonce) and main._pc_committed_answer (round 2: the recorded outcome a
    # replayed key, a pack voided at open and /pc/packs/result answer, so no
    # work after a purchase commits can fail its answer). Code tier 326 ->
    # 327 -> 328, under its bound; median 75 and p90 164 -> 166 under
    # theirs. The bound moves to 484, the same ~5% headroom 460 gave over
    # 439, for that reason and no other.
    # Discord card render parity (2026-10-01): the same route measured 461 on
    # main 0e75199 and 490 on the lane tip -- +29, exactly the 29 card art
    # code bindings accounted for at the code bound above, with no import
    # line added. The bound moves to 520, ~6% over the measurement, for that
    # reason and no other.
    # Seat evidence V2 (claude/seat-evidence-server-v2, 2026-10-02): the same
    # route measured 503 at the base 14127702 and 526 on the lane -- +23, and
    # all 23 are IMPORT leaves: the five new modules (seat_evidence and the
    # four review modules) each bind stdlib names every route already
    # references (json, os, hashlib, datetime, timezone, time, math, hmac,
    # uuid, secrets, stat, text), and the walk folds in every module that binds
    # a shared name. No code binding of the new modules reaches an existing
    # route: after the review modules' generic function names were made
    # distinctive, the code tier moves only on the four new routes and
    # /api/v1/health (median 22 / p90 97 / worst 370, all under their bounds).
    # Whole closure over 391 routes: median 76 -> 86, p90 197 -> 196. The
    # bound moves to 556, ~6% over the measurement, for that reason and no
    # other; the median and p90 bounds stay.
    assert all_worst <= 556, f"worst closure {all_worst} of {total}"


def _route_covering(module, name):
    """The routes whose reviewed surface contains one binding."""
    return [r for r in main.app.routes
            if isinstance(r, APIRoute) and r.path.startswith("/api/v1/")
            and (module, name) in _reached(_route_seeds(r))]


def test_the_route_seed_recovery_still_sees_what_it_recovers():
    """A route is entered through more than its handler: FastAPI resolves the
    dependencies first and serialises through the response model, and neither
    is called from the handler body.

    MEASURED on this tree, both are REDUNDANT: every route names its response
    model in its own decorator and its dependencies in its own signature, both
    of which are inside the handler's segment, so the walk reaches them anyway
    -- 0 of 309 routes gain a single binding from these seeds. That is why this
    gate asserts the RECOVERY and not a fingerprint delta: deleting either seed
    source moves no fingerprint anywhere, so a drift assertion for them is a
    check that cannot fail, and both mutants proved exactly that.

    They stay because the redundancy is a property of how these routes happen
    to be written, not of the framework: a dependency declared on the router
    rather than in a signature, or a response model composed at import time, is
    named nowhere in the handler's own source."""
    routes = [r for r in main.app.routes
              if isinstance(r, APIRoute) and r.path.startswith("/api/v1/")]
    assert routes

    models, dependencies = set(), set()
    for route in routes:
        endpoint_key = _binding_key(route.endpoint)
        for key in _route_seeds(route):
            if key == endpoint_key:
                continue
            if _binding_kind(*key) == "def" and key[0] == "schemas":
                models.add(key)
            else:
                dependencies.add(key)

    assert len(models) >= 25, (
        f"only {len(models)} first-party response models were recovered from "
        "309 routes; measured 29 -- the recovery has stopped seeing them"
    )
    assert ("database", "get_db") in dependencies, sorted(dependencies)
    assert all(_binding_kind(*key) is not None for key in models | dependencies), (
        "a recovered seed is not an indexed binding, so its source is not in "
        "any fingerprint"
    )


def test_a_module_level_data_binding_moves_the_fingerprint_of_its_routes():
    """r14 M7, GATE A -- the defect that motivated the whole method change.

    `_PODIUM_QUERY` is a raw SQL string bound at module scope and executed by
    32 routes. Under object introspection it was in no fingerprint at all:
    resolving the name gave back a `str`, and a str has no source. Rewriting
    the query -- changing what every one of those routes returns -- moved
    nothing and this gate reported all-clear.

    THE MUTATION THIS MUST FAIL ON: restricting expansion to def/class
    bindings, i.e. the shape a fingerprint over objects can express. The sha
    then stops moving."""
    covering = _route_covering("main", "_PODIUM_QUERY")
    assert len(covering) >= 20, (
        f"only {len(covering)} routes reach _PODIUM_QUERY; measured 32 -- "
        "either the query moved or the walk narrowed"
    )
    assert _binding_kind("main", "_PODIUM_QUERY") == "data", (
        "the point of this gate is that it is NOT a def or a class"
    )
    route = covering[0]
    before = _route_fingerprint(route)
    assert before == _route_fingerprint(route), "negative control"
    with _mutated_segment("main", "_PODIUM_QUERY"):
        after = _route_fingerprint(route)
    assert after != before, (
        f"rewriting the SQL that {route.path} executes left it certified unchanged"
    )


def test_a_class_level_default_moves_the_fingerprint_of_the_route_that_persists_it():
    """r14 M7, GATE B. `MatchRow` carries the field defaults every persisted
    bracket row is built from. It survived the old rule only because it happens
    to be a CLASS, whose statement `inspect` can still recover -- an accident of
    what kind of value the name denotes, which is exactly what this method stops
    depending on.

    THE MUTATION THIS MUST FAIL ON: dropping ClassDef from the index. The
    covering assertion then finds no route at all."""
    covering = _route_covering("tournament_bracket", "MatchRow")
    assert covering, "no route covers tournament_bracket.MatchRow"
    assert _binding_kind("tournament_bracket", "MatchRow") == "def", (
        "classes are indexed under the def tier and expanded through"
    )
    route = covering[0]
    before = _route_fingerprint(route)
    with _mutated_segment("tournament_bracket", "MatchRow"):
        after = _route_fingerprint(route)
    assert after != before, (
        f"editing MatchRow left {route.path} certified unchanged"
    )


def _entry_point_sha(module, name):
    return sha1(_fingerprint_text([(module, name)]).encode("utf-8")).hexdigest()


def _load_entry_points():
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    sections = document["entry_points"]
    assert set(sections) == {"middleware", "exception_handlers",
                             "background_entry_points"}, sorted(sections)
    return {name: [tuple(row) for row in rows] for name, rows in sections.items()}


def _entry_point_drift(manifest, sha_of=_entry_point_sha):
    """EVERY pinned entry point whose fingerprint has moved, not the first.

    This used to be an `assert` inside the loop, which stops at the first
    mismatch it meets. The sections are walked in a fixed order and middleware
    comes first, so a drift in the background entry point sat behind a
    middleware drift owned by another lane and was reported by nothing: the
    failure line named one function, and a reader had no way to tell whether
    it was the only one. A gate that reports a subset of what it found is a
    gate that certifies the rest by silence.

    `sha_of` is a seam, so a control can hand this a scripted oracle and check
    that a SECOND drifted entry is actually named.
    """
    drifted = []
    for section in sorted(manifest):
        for module, name, sha in manifest[section]:
            live = sha_of(module, name)
            if live != sha:
                drifted.append((section, module, name, sha, live))
    return drifted


def test_the_manifest_covers_every_non_route_entry_point():
    """r14 M7, GATE C. A route table is not the whole app.

    Middleware runs on every request, exception handlers decide what a failure
    returns, and the lifespan starts the background work -- and none of them
    appears in `app.routes`, so before this range every one of them sat outside
    every fingerprint. Editing the rate-limit gate moved nothing anywhere.

    Each recovered set is compared to the manifest by identity AND by
    fingerprint, so a reshaping of the app that stops the recovery seeing
    anything fails loudly instead of certifying an empty set.

    THE MUTATIONS THIS MUST FAIL ON: appending a comment to `rate_limit_gate`
    (its sha must move -- today nothing anywhere moves), and making the
    recovery return nothing (the non-empty assertions fire)."""
    manifest = _load_entry_points()
    live = _entry_point_sections()

    assert live["middleware"], "no first-party middleware dispatch was recovered"
    assert ("main", "rate_limit_gate") in live["middleware"], sorted(live["middleware"])
    assert live["background_entry_points"], "the lifespan was not recovered"
    assert live["background_entry_points"] == [("main", "lifespan")], (
        sorted(live["background_entry_points"])
    )

    # The raw recovery must be non-empty -- proof the mechanism still sees
    # handlers at all, so that a first-party one added later is picked up
    # rather than silently skipped. (FastAPI's own three are always there; the
    # recovery keeps only the first-party ones, which is why this is asserted
    # on the RAW set and not on the section.)
    raw_handlers = getattr(main.app, "exception_handlers", None) or {}
    assert raw_handlers, "the exception-handler recovery sees nothing at all"
    # ...and the first-party set is what the manifest says it is. The generic
    # loop below asserts that for every section; this names the one handler
    # this app registers, so DELETING it from both the app and the manifest --
    # which the loop would call agreement -- still reddens here.
    assert live["exception_handlers"] == [("main", "_ffa_report_refusal_handler")], (
        "the first-party exception-handler set changed. A handler is a "
        "request-path surface: adding, removing or renaming one is a review "
        "item, not a re-pin (repin_route_manifest.py refuses to do it)."
    )

    for section, entries in live.items():
        recorded = [(m, n) for (m, n, _sha) in manifest[section]]
        assert recorded == entries, f"{section}: manifest {recorded} vs live {entries}"

    # Reported TOGETHER. One drifted fingerprint used to hide every later one,
    # and the sections are walked in a fixed order, so whichever came first
    # decided what a reader was told (#342: a check whose report is a subset of
    # what it found).
    drifted = _entry_point_drift(manifest)
    assert not drifted, (
        "%d pinned entry point(s) have moved; every one of them needs "
        "re-reviewing and re-pinning:\n%s"
        % (len(drifted), "\n".join(
            "  %-24s %s.%s  %s -> %s" % (section, module, name, sha[:12], now[:12])
            for section, module, name, sha, now in drifted)))

    before = _entry_point_sha("main", "rate_limit_gate")
    with _mutated_segment("main", "rate_limit_gate"):
        after = _entry_point_sha("main", "rate_limit_gate")
    assert after != before, "editing the rate-limit gate moved no fingerprint"


def test_a_drifted_entry_point_does_not_hide_the_ones_behind_it():
    """The gate above reports EVERY moved fingerprint, not the first.

    Why it needs its own test: on this tree one middleware entry has already
    drifted, and the sections are walked in a fixed order with middleware
    first. A `main.lifespan` drift therefore sat behind it and was named by
    nothing -- so "one function is listed" carried no information about the
    others, and a background entry point could ship stale behind a failure
    somebody else was expected to clear.

    The oracle is scripted rather than taken from the live tree: a test that
    depends on which entry points happen to be drifting today stops testing
    this the moment somebody re-pins.
    """
    manifest = {
        "middleware": [("main", "rate_limit_gate", "aaaa")],
        "background_entry_points": [("main", "lifespan", "bbbb")],
    }
    both = _entry_point_drift(manifest, sha_of=lambda m, n: "cccc")
    named = {(module, name) for _section, module, name, _sha, _now in both}
    assert named == {("main", "rate_limit_gate"), ("main", "lifespan")}, (
        "two entry points drifted and the gate reported %r -- the ones it "
        "does not name are certified by its silence" % (sorted(named),))

    # ...and it still says nothing when nothing moved, or the assertion above
    # would be reporting drift that is not there.
    assert _entry_point_drift(
        manifest, sha_of=lambda m, n: "aaaa" if n == "rate_limit_gate" else "bbbb") == []


def test_the_admission_rule_is_computed_for_every_module_not_just_main():
    """r14 M7, GATE D -- the assertion the old GATE 8 should have been.

    The previous rule's coverage was decided by a hand-written notion of which
    modules mattered, and every version of that shape has failed the same way:
    it is right about the modules whoever wrote it was thinking of. This
    re-derives each module's module-scope bindings with an INDEPENDENT parse
    written here, and demands the index agree exactly -- so a carve-out added
    anywhere in the admission rule fails on the module it carves out.

    THE MUTATION THIS MUST FAIL ON: any name-conditional in the admission rule
    (`and stem != "models"`), or dropping a node kind from it."""
    files = {p.stem: p for p in sorted(API_DIR.glob("*.py"))}
    index = _binding_index()
    assert set(index) == set(files), (
        f"indexed {sorted(set(index) ^ set(files))} differs from backend/api"
    )
    assert len(files) >= 8, f"only {len(files)} modules found in {API_DIR}"

    for stem, path in files.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        expected = set()

        def stored(node):
            """Combat fix pass 5: what any other module-level statement
            binds, read here independently of `_class_touched`: every name
            it stores or deletes and the base name of every attribute or
            subscript it stores into or deletes, outside the nested scopes
            (a definition's body, a lambda, a comprehension past its first
            iterable)."""
            out, stack = set(), [node]
            while stack:
                n = stack.pop()
                ctx = getattr(n, "ctx", None)
                if isinstance(ctx, (ast.Store, ast.Del)):
                    base = n
                    while isinstance(base, (ast.Attribute, ast.Subscript, ast.Starred)):
                        base = base.value
                    if isinstance(base, ast.Name) and base is not n or isinstance(n, ast.Name):
                        out.add(base.id)
                for name in ("name", "rest"):
                    if isinstance(n, (ast.MatchAs, ast.MatchStar, ast.MatchMapping)) \
                            and isinstance(getattr(n, name, None), str):
                        out.add(getattr(n, name))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                  ast.Lambda)):
                    continue
                if isinstance(n, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                    stack.append(n.generators[0].iter)
                    continue
                stack.extend(ast.iter_child_nodes(n))
            return out

        def collect(body):
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    expected.add(node.name)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        for sub in ast.walk(target):
                            if isinstance(sub, ast.Name):
                                expected.add(sub.id)
                elif isinstance(node, ast.AnnAssign):
                    if isinstance(node.target, ast.Name):
                        expected.add(node.target.id)
                    else:
                        expected.update(stored(node.target))
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        expected.add(alias.asname or alias.name.split(".")[0])
                elif isinstance(node, (ast.If, ast.Try, ast.With)):
                    if _is_script_guard(node):
                        continue
                    for item in getattr(node, "items", []):
                        if item.optional_vars is not None:
                            expected.update(stored(item.optional_vars))
                    collect(node.body)
                    collect(getattr(node, "orelse", []))
                    collect(getattr(node, "finalbody", []))
                    for handler in getattr(node, "handlers", []):
                        collect(handler.body)
                else:
                    expected.update(stored(node))

        collect(tree.body)
        assert set(index[stem]) == expected, (
            f"{stem}: index and an independent parse disagree on "
            f"{sorted(set(index[stem]) ^ expected)[:8]}"
        )
        assert expected, f"{stem}: no module-scope bindings found at all"


def test_a_name_bound_twice_keeps_both_halves_of_its_source(tmp_path):
    """A conditional rebinding must not hide half its source.

    Every module in backend/api binds each module-scope name once, so this
    branch has no live case -- and an unexercised guard is one that is wrong on
    the day it is first needed. Driven on a synthetic module rather than
    asserted about. Also pins the two behaviours the index depends on that no
    production file demonstrates: bindings inside a module-level `try` and
    inside an `if` both count as module scope."""
    module = tmp_path / "synthetic.py"
    module.write_text(
        "LIMIT = 1  # first\n"
        "if True:\n"
        "    LIMIT = 2  # second\n"
        "try:\n"
        "    GUARDED = 3\n"
        "except Exception:\n"
        "    GUARDED = 4\n"
        "def only_here():\n"
        "    return LIMIT\n",
        encoding="utf-8",
    )
    bindings = _index_module(module)
    assert set(bindings) == {"LIMIT", "GUARDED", "only_here"}, sorted(bindings)

    kind, text, _refs = bindings["LIMIT"]
    assert kind == "data"
    assert "# first" in text and "# second" in text, (
        "a rebound name kept only one of its two statements: " + repr(text)
    )
    guarded_kind, guarded_text, _ = bindings["GUARDED"]
    assert "3" in guarded_text and "4" in guarded_text, guarded_text
    assert bindings["only_here"][0] == "def"


def test_the_indexed_segment_is_the_source_the_interpreter_would_show():
    """r14 M7, the fidelity control. The index is only sound if the text it
    hands back for a name is the text that name's statement really is.

    Checked against `inspect.getsource` for every def/class binding in the
    seven non-main modules, plus a fixed sample of main-defined classes. Only
    main's getsource is expensive (measured ~4.8 s for one class, because it
    re-tokenises a 25k-line file), which is why the sample there is fixed and
    small rather than exhaustive.

    NEGATIVE CONTROL: a segment sliced one line short must NOT compare equal --
    otherwise this assertion is satisfied by any two strings."""
    index = _binding_index()
    compared = 0
    for stem, bindings in sorted(index.items()):
        if stem == "main":
            continue
        module = sys.modules.get(stem)
        if module is None:
            continue
        for name, (kind, text, _refs) in sorted(bindings.items()):
            if kind != "def":
                continue
            obj = getattr(module, name, None)
            if obj is None or not _is_ours(obj):
                continue
            try:
                actual = inspect.getsource(obj)
            except (OSError, TypeError):
                continue
            assert text == actual, f"{stem}.{name}: indexed segment != real source"
            compared += 1
    assert compared >= 40, f"only {compared} bindings were actually compared"

    # main's own classes, sampled rather than swept: `inspect.getsource` costs
    # ~4.8 s per class there because it re-tokenises a 25k-line file, and three
    # is enough to prove the same parse behaves the same way in the big module.
    # The sample is COMPUTED, not listed -- the first attempt listed three
    # names of which two are imported into main rather than defined in it, so
    # it compared an empty segment against a real class and would have gone on
    # doing that for as long as the names existed anywhere.
    main_defined = sorted(
        name for name, (kind, _t, _r) in index["main"].items()
        if kind == "def" and _binding_key(getattr(main, name, None)) == ("main", name)
        and inspect.isclass(getattr(main, name, None))
    )
    assert len(main_defined) >= 3, f"main defines only {len(main_defined)} classes"
    for name in main_defined[:3]:
        assert _segment("main", name) == inspect.getsource(getattr(main, name)), name

    # The control that makes the equality above mean something.
    source = (API_DIR / "glicko2.py").read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    node = next(n for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    short = "".join(lines[node.lineno - 1:node.end_lineno - 1])
    assert short != _segment("glicko2", node.name), (
        "a one-line-short slice compared equal -- this control proves nothing"
    )


# str.splitlines() breaks on eleven separators. Python's tokenizer breaks on
# three. Everything in this file that turns a line number into source text
# indexes a splitlines() list with an ast line number, so one character from
# the difference anywhere in a file silently shifts every binding below it.
_SPLITLINES_ONLY = "\v\f\x1c\x1d\x1e\x85\u2028\u2029"


def test_no_api_source_contains_a_line_break_only_str_splitlines_sees():
    """The precondition every segment in this file rests on.

    Found in the field: pc_portrait.py wrote its control-character class with
    the characters themselves, so the two separators inside it put ast and
    splitlines() two lines apart and the index handed back the wrong source
    for every binding below. The fidelity control above caught it, but only
    for the bindings it compares -- the fingerprints went on covering shifted
    text either way. Write these as escapes (`\\u2028`), never as themselves.

    NEGATIVE CONTROL: a constructed source carrying one must be flagged, or
    this reads as "no file has one" when it may mean the scan never fires.
    """
    offenders = []
    for path in sorted(API_DIR.glob("*.py")):
        with path.open(encoding="utf-8", newline="") as handle:
            source = handle.read()
        for index, character in enumerate(source):
            if character in _SPLITLINES_ONLY:
                offenders.append("%s:%d U+%04X"
                                 % (path.name, source.count("\n", 0, index) + 1,
                                    ord(character)))
    assert not offenders, (
        "these characters are line breaks to str.splitlines() and not to the "
        "tokenizer, so every segment below them is indexed off by one: %s"
        % ", ".join(offenders[:10]))

    planted = "x = 1\u2028y = 2\n"
    assert any(c in _SPLITLINES_ONLY for c in planted), "the detector is inert"
    assert len(planted.splitlines()) != len(planted.split("\n")) - 1, (
        "the constructed counterexample does not actually shift the count, so "
        "an always-empty scan would pass this test")


def test_request_key_counterexample_is_rejected():
    fake_response = {"local_net_writes": 0}
    with pytest.raises(AssertionError, match="local_net_writes"):
        assert_no_net_seat_sentinels(fake_response)


class _ScriptedResult:
    def __init__(self, *, row=None, rows=()):
        self.row = row
        self.rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self.row

    def all(self):
        return self.rows


class _ScriptedSession:
    def __init__(self, results):
        self.results = list(results)
        self.executions = []

    async def execute(self, statement, params=None):
        self.executions.append((statement, params))
        assert self.results, "unexpected database execute"
        return self.results.pop(0)


def _match_by_code_row(sentinels):
    p1_id = UUID("11111111-1111-1111-1111-111111111111")
    p2_id = UUID("22222222-2222-2222-2222-222222222222")
    row = defaultdict(lambda: None)
    row.update(
        {
            "id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "ended_at": datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
            "is_ranked": True,
            "invalidated_at": None,
            "invalidation_reason": None,
            "p1_rounds_won": 5,
            "p2_rounds_won": 3,
            "p1_points_total": 12,
            "p2_points_total": 8,
            "duration_seconds": 240,
            "player1_id": p1_id,
            "player2_id": p2_id,
            "winner_id": p1_id,
            "p1_sid": "76561193000000001",
            "p2_sid": "76561193000000002",
            "p1_name": "Player One",
            "p2_name": "Player Two",
            "s_p1_id": None,
            "series_status": None,
        }
    )
    row.update(sentinels)
    return row


def test_sentinel_exercised_match_lookup_never_serializes_private_columns():
    sentinels = storage_sentinels()
    session = _ScriptedSession(
        [
            _ScriptedResult(row=_match_by_code_row(sentinels)),
            _ScriptedResult(rows=[]),
            _ScriptedResult(rows=[]),
        ]
    )
    payload = asyncio.run(main.get_match_by_code("aaaaaaaaaaaa", db=session))

    assert payload["mode"] == "1v1"
    assert len(session.executions) == 3
    assert_no_net_seat_sentinels(payload, sentinels)
    source = inspect.getsource(main.get_match_by_code)
    assert all(name not in source for name in STORAGE_FIELDS)


class _DiscordContext:
    def __init__(self):
        self.deferred = False
        self.sent = []

    async def defer(self):
        self.deferred = True

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


def _discord_game(sentinels):
    game = {
        "mode": "1v1",
        "code": "AAAAAAAAAAAA",
        "match_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "ended_at": "2026-09-02T12:00:00Z",
        "is_ranked": True,
        "invalidated": False,
        "invalidation_reason": None,
        "duration_seconds": 240,
        "series_status": "completed",
        "players": [
            {
                "steam_id": "76561193000000001",
                "name": "Player One",
                "rounds_won": 5,
                "points_total": 12,
                "won": True,
                "cards": ["Grow"],
            },
            {
                "steam_id": "76561193000000002",
                "name": "Player Two",
                "rounds_won": 3,
                "points_total": 8,
                "won": False,
                "cards": ["Quick Reload"],
            },
        ],
    }
    # Deliberately hand the formatter private fields at multiple depths. It
    # must still render from its explicit allowlist rather than stringifying.
    game.update(sentinels)
    game["players"][0].update(sentinels)
    return game


def test_discord_game_formatter_does_not_consume_net_seat_columns(monkeypatch):
    import discord_bot

    sentinels = storage_sentinels()
    game = _discord_game(sentinels)

    async def fake_api_get(_path):
        return game

    monkeypatch.setattr(discord_bot, "api_get", fake_api_get)
    monkeypatch.setattr(discord_bot, "_MPL_AVAILABLE", False)
    context = _DiscordContext()
    callback = getattr(discord_bot.cmd_game, "callback", discord_bot.cmd_game)
    asyncio.run(callback(context, "aaaaaaaaaaaa"))

    assert context.deferred
    assert len(context.sent) == 1
    embed = context.sent[0][1]["embed"]
    assert_no_net_seat_sentinels(embed.to_dict(), sentinels)
    source = inspect.getsource(callback)
    assert all(name not in source for name in STORAGE_FIELDS)


def _flag_row(sentinels, reviewed: bool):
    row = defaultdict(lambda: None)
    row.update(
        {
            "id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "discord_evidence_revision": 1,
            "match_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "context_series_id": None,
            "flag_reason": "inactive_player",
            "flag_details": {
                "reporter_steam": "76561193000000001",
                "shots": 0,
                "blocks": 0,
                "cards_picked": 0,
            },
            "auto_invalidated": False,
            "invalidated_at": None,
            "invalidation_reason": None,
            "restoration_required": False,
            "p1_steam_id": "76561193000000001",
            "p2_steam_id": "76561193000000002",
            "p1_name": "Player One",
            "p2_name": "Player Two",
            "is_ranked": True,
            "duration": 240,
            "p1_rounds_won": 5,
            "p2_rounds_won": 3,
            "p1_points_total": 12,
            "p2_points_total": 8,
            "p1_card_count": 1,
            "p2_card_count": 1,
            "p1_cards": "Grow",
            "p2_cards": "Quick Reload",
            "point_timeline": None,
            "point_times": None,
            "reporter_name": "Player One",
            "reporter_steam_id": "76561193000000001",
            "reporter_mod_version": "1.40.0",
            "game_version": "1.40.0",
            "region": "us",
            "photon_room_id": "ranked_fixture",
            "reviewed_at": (
                datetime(2026, 9, 2, 13, tzinfo=timezone.utc) if reviewed else None
            ),
            "review_action": "confirmed" if reviewed else None,
            "created_at": datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
        }
    )
    row.update(sentinels)
    return row


def test_flag_and_review_formatters_do_not_consume_net_seat_columns():
    sentinels = storage_sentinels()
    for reviewed in (False, True):
        payload = flag_evidence.flag_payload(_flag_row(sentinels, reviewed))
        if reviewed:
            assert payload["reviewed_at"] is not None
        else:
            assert payload["reviewed_at"] is None
        assert_no_net_seat_sentinels(payload, sentinels)

    source = inspect.getsource(flag_evidence.flag_payload)
    query_source = inspect.getsource(flag_evidence.fetch_flag_context_rows)
    assert all(name not in source for name in STORAGE_FIELDS)
    assert all(name not in query_source for name in STORAGE_FIELDS)


def test_an_imported_helper_moves_the_fingerprint_of_the_route_that_calls_it():
    """r13 MEDIUM, mutation-proven on the case the finding names: a binding
    DEFINED in tournament_bracket and IMPORTED into tournaments, reached from a
    route. Editing it must move that route's fingerprint; the negative control
    is the same route with nothing edited."""
    target = None
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        outside = [i for i in _helper_closure(route.endpoint)
                   if i[0] == "tournament_bracket"]
        if outside:
            target = (route, sorted(outside)[0])
            break
    assert target, "no route reaches a binding defined in tournament_bracket"
    route, (module, name) = target

    before = _route_fingerprint(route)
    assert before == _route_fingerprint(route), (
        "negative control: unedited source must not move"
    )
    with _mutated_segment(module, name):
        after = _route_fingerprint(route)
    assert after != before, (
        f"editing {module}.{name} left {route.path} certified unchanged"
    )


def test_an_import_is_part_of_the_surface_a_route_was_reviewed_with():
    """r15: which object a name denotes decides what the handler does.

    A rollback-and-retry around a database deadlock names `DBAPIError`. Drop
    that import and the retry becomes a NameError on the one path nothing
    routinely exercises -- while every route SHA in this manifest is unchanged,
    because imports were not part of the fingerprint at all."""
    index = _binding_index()
    assert index["main"]["DBAPIError"][0] == "import", (
        "imports must be indexed, and as their own kind"
    )
    covering = _route_covering("main", "DBAPIError")
    assert covering, "no route's fingerprint covers an import it depends on"

    before = _route_fingerprint(covering[0])
    with _mutated_segment("main", "DBAPIError"):
        assert _route_fingerprint(covering[0]) != before, (
            "editing an import moved no route fingerprint"
        )
    assert _route_fingerprint(covering[0]) == before


def test_a_data_binding_composed_from_another_moves_the_fingerprint():
    """r15: the raw-SQL hole, one level of indirection further down.

    `_DC_ELIGIBLE_TERMS` is a SQL fragment built by concatenating
    `_DC_EVIDENCE_TERM` -- the predicate deciding whether a disconnect report is
    accepted. Because data bindings were included but never expanded, the
    composed binding showed only the NAME of what it composed, and rewriting
    that predicate moved nothing. Measured at the time: 0 of 309 routes."""
    index = _binding_index()
    assert index["main"]["_DC_EVIDENCE_TERM"][0] == "data"

    covering = _route_covering("main", "_DC_EVIDENCE_TERM")
    assert covering, (
        "no route covers the disconnect evidence predicate -- the composed "
        "binding is showing the name and not the text again"
    )
    before = _route_fingerprint(covering[0])
    with _mutated_segment("main", "_DC_EVIDENCE_TERM"):
        assert _route_fingerprint(covering[0]) != before
    assert _route_fingerprint(covering[0]) == before


def test_a_data_binding_does_not_drag_in_the_whole_app():
    """The other half of the same rule, and the reason it is worth a test.

    Data-into-data is safe only because it stops at data. `app = FastAPI(...)`
    is a data binding that every route decorator references; letting it follow
    the def it names would put most of the app inside every route's
    fingerprint, which is the failure mode the affordability bound exists to
    catch."""
    index = _binding_index()
    assert index["main"]["app"][0] == "data"
    reached = _reached({("main", "app")})
    assert all(kind == "data" for kind in reached.values()), sorted(
        key for key, kind in reached.items() if kind != "data"
    )[:5]


def test_the_manifest_records_the_order_requests_are_matched_in():
    """r15: sorting the manifest discards which handler actually answers.

    Starlette matches in REGISTRATION order, first match wins. Every identity
    and every fingerprint in this file survives a reordering intact, so without
    this the manifest certifies that a route exists and stays silent about
    whether it is reachable."""
    document = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    recorded = document["route_order"]
    live = _route_registration_order()

    assert live == recorded, (
        "route registration order changed; first match wins, so confirm the "
        "moved route is still the one that answers before rebaselining"
    )
    assert sorted(recorded) != recorded or len(recorded) < 2, (
        "the recorded order is sorted, which is the one order that proves "
        "nothing -- it would survive any reordering of the real routes"
    )
    assert len(recorded) == len(_load_manifest()), (
        "the order section and the identity groups disagree on route count"
    )


def test_no_dynamic_route_is_registered_ahead_of_a_literal_it_swallows():
    """The concrete harm the order section exists to catch.

    `/players/{steam_id}` ahead of `/players/search` makes the literal route
    dead: it returns whatever the dynamic handler does with `steam_id="search"`,
    with no error anywhere. Asserted as a real emptiness, and the detector is
    checked against a constructed pair so an always-empty result cannot pass."""
    live = _route_registration_order()
    assert not _shadowing_pairs(live), _shadowing_pairs(live)[:3]

    # Negative control. Without it this reads as "no shadowing" when what it
    # may mean is that the detector never fires (#342/#441).
    planted = ["GET /api/v1/players/{steam_id} -> main.a",
               "GET /api/v1/players/search -> main.b"]
    assert _shadowing_pairs(planted) == [(planted[0], planted[1])]
    assert not _shadowing_pairs(list(reversed(planted))), (
        "the literal registered FIRST is correct and must not be flagged"
    )


def test_a_module_level_guards_condition_is_part_of_what_it_guards():
    """r15: the block's header was in nobody's segment.

    main binds `_PIL_AVAILABLE` and `_PILImage` inside a try/except, and four
    routes cover them. Without the header the except clause that decides
    whether Pillow is importable could be rewritten with no route fingerprint
    moving -- the condition under which a binding exists is part of what was
    reviewed, not scaffolding around it."""
    index = _binding_index()
    assert "_PIL_AVAILABLE" in index["main"], (
        "the try-guarded binding left the index entirely"
    )
    text = index["main"]["_PIL_AVAILABLE"][1]
    assert text.lstrip().startswith("try:"), (
        "the controlling header is not part of the binding's source: " + text[:80]
    )

    covering = _route_covering("main", "_PIL_AVAILABLE")
    assert covering, "no route covers the Pillow availability flag"
    before = _route_fingerprint(covering[0])
    with _mutated_segment("main", "_PIL_AVAILABLE"):
        assert _route_fingerprint(covering[0]) != before
    assert _route_fingerprint(covering[0]) == before


def test_a_script_only_block_is_in_no_routes_reviewed_surface():
    """r15: `if __name__ == "__main__":` was indexed like any other guard.

    tournament_bracket's self-test binds ordinary names — rows, ids, real,
    extras, s1, s2, sus — and a handler's own locals reference names like those,
    so the cross-module walk resolved routes into a block that never executes
    under the api. Measured before the exclusion: 1008 occurrences over 10
    names, `sus` in 194 route fingerprints. Editing a bracket self-test moved
    two hundred routes."""
    source = (API_DIR / "tournament_bracket.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    script_only = set()
    for node in tree.body:
        if not _is_script_guard(node):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Store):
                script_only.add(inner.id)
    # A positive control on the SAMPLE, not just on the absence: if the block
    # stops being found, an empty set makes every assertion below vacuous.
    assert len(script_only) >= 10, sorted(script_only)
    assert {"rows", "ids", "extras"} <= script_only, sorted(script_only)

    index = _binding_index()
    top_level = {node.name for node in tree.body
                 if isinstance(node, _DEF_NODES)}
    leaked = sorted((script_only - top_level) & set(index["tournament_bracket"]))
    assert not leaked, (
        "script-only bindings are in the index and can be reached by a route: "
        + ", ".join(leaked)
    )


def test_a_later_part_of_a_block_carries_its_own_header(tmp_path):
    """r16: `guard_header` reused the `try:` line for every handler, so
    `except Exception` could become `except ImportError` -- a different set of
    failures reaching a different binding -- with no fingerprint moving, and
    `else`/`finally` bodies had no header at all. Each later part now carries
    its own header on top of the block's."""
    module = tmp_path / "m.py"
    module.write_text(
        "try:\n"
        "    import nothing_here\n"
        "    FLAG = True\n"
        "except Exception:\n"
        "    FLAG = False\n"
        "else:\n"
        "    MODE = 'have'\n"
        "finally:\n"
        "    DONE = 1\n",
        encoding="utf-8")
    before = _index_module(module)
    assert "except Exception:" in before["FLAG"][1], before["FLAG"][1]
    assert "else:" in before["MODE"][1], before["MODE"][1]
    assert "finally:" in before["DONE"][1], before["DONE"][1]
    # The block's own header is still on every part.
    for name in ("FLAG", "MODE", "DONE"):
        assert before[name][1].lstrip().startswith("try:"), before[name][1]

    module.write_text(module.read_text(encoding="utf-8").replace(
        "except Exception:", "except ImportError:"), encoding="utf-8")
    after = _index_module(module)
    assert after["FLAG"][1] != before["FLAG"][1]
    # A header change in one part moves only that part's bindings.
    assert after["MODE"][1] == before["MODE"][1]
    assert after["DONE"][1] == before["DONE"][1]


def test_only_the_canonical_script_guard_is_exempt():
    """r16: `_is_script_guard` accepted any comparison whose left side was
    `__name__`, so `if __name__ != "__main__":` -- a block that RUNS at import
    -- was excluded from every fingerprint while its work still happened."""
    canonical = ast.parse('if __name__ == "__main__":\n    pass\n').body[0]
    assert _is_script_guard(canonical)
    for text in ('if __name__ != "__main__":\n    pass\n',
                 'if __name__ in ("__main__", "x"):\n    pass\n',
                 'if __name__ == "not_main":\n    pass\n',
                 'if "__main__" == __name__:\n    pass\n'):
        assert not _is_script_guard(ast.parse(text).body[0]), text


def test_a_name_referenced_only_by_a_block_header_is_in_the_closure(tmp_path):
    """r2 (Sept 6): a header's TEXT was fingerprinted (r16), but a name it
    references was not in the binding's closure. `except ERRORS:` with
    `ERRORS = (ImportError,)` -- changing the tuple changes which failures
    reach the handler's binding with no fingerprint moving; the same for a
    feature flag in an `if`. The header's names join the closure; the text
    seam is unchanged."""
    module = tmp_path / "m.py"
    module.write_text(
        "ERRORS = (ImportError,)\n"
        "FEATURE = True\n"
        "LOCK = object()\n"
        "try:\n"
        "    import nothing_here\n"
        "    FLAG = True\n"
        "except ERRORS:\n"
        "    FLAG = False\n"
        "else:\n"
        "    MODE_TRY = 'have'\n"
        "if FEATURE:\n"
        "    MODE = 'on'\n"
        "with LOCK:\n"
        "    HELD = 1\n",
        encoding="utf-8")
    index = _index_module(module)
    assert "ERRORS" in index["FLAG"][2], sorted(index["FLAG"][2])
    assert "FEATURE" in index["MODE"][2], sorted(index["MODE"][2])
    assert "LOCK" in index["HELD"][2], sorted(index["HELD"][2])
    # The handler's type belongs to the handler's bindings only: the `else`
    # part of the same try did not run under `except ERRORS`.
    assert "ERRORS" not in index["MODE_TRY"][2], sorted(index["MODE_TRY"][2])
    # The text seam is what it was: the header is still on the binding.
    assert "except ERRORS:" in index["FLAG"][1], index["FLAG"][1]


def test_a_guarded_import_follows_its_guard(tmp_path):
    """Group 2 review (Sept 6): the closure walk treated every import as a leaf
    BEFORE following its refs, and an import's refs are exactly the names of
    the block headers that select it (r2). `if FEATURE: import fast as engine`
    / `else: import slow as engine` -- FEATURE decides which implementation a
    route runs, so it belongs in the route's closure; an unguarded import stays
    a leaf."""
    module = tmp_path / "m.py"
    module.write_text(
        "FEATURE = True\n"
        "if FEATURE:\n"
        "    import json as engine\n"
        "else:\n"
        "    import re as engine\n"
        "import os\n",
        encoding="utf-8")
    index = {"m": _index_module(module)}
    reached = _walk_bindings([("m", "engine")], index=index)
    assert ("m", "FEATURE") in reached, sorted(reached)
    assert reached[("m", "engine")] == "import"
    assert _walk_bindings([("m", "os")], index=index) == {("m", "os"): "import"}


def _tmp_index(tmp_path, **sources):
    index = {}
    for stem, text in sources.items():
        path = tmp_path / f"{stem}.py"
        path.write_text(text, encoding="utf-8")
        index[stem] = _index_module(path)
    return index


def test_a_reference_resolves_to_the_binding_it_denotes(tmp_path):
    """2026-10-02, the binding-resolved closure. A name is charged to a route
    only when the route's closure binds it: `json.dumps` is not `b.dumps`, a
    name a module does not bind denotes nothing in it, and an import in a
    module the route does not reach charges the route nothing. Through an
    import of one of ours -- module-level or function-local, `import X as a`
    or `from X import n` -- the walk reaches the binding in X."""
    index = _tmp_index(
        tmp_path,
        a=("import json\n"
           "import b as bee\n"
           "from b import helper\n"
           "def route():\n"
           "    return json.dumps(bee.thing()), helper()\n"
           "def late_route():\n"
           "    import b as late\n"
           "    from b import unused as u\n"
           "    return late.thing(), u(), text\n"),
        b=("def dumps(x):\n    return x\n"
           "def thing():\n    return 1\n"
           "def helper():\n    return 2\n"
           "def unused():\n    return 3\n"),
        c=("import json\n"
           "from sqlalchemy import text\n"
           "def dumps(x):\n    return json.dumps(x)\n"
           "def helper():\n    return text\n"
           "def route():\n    return 0\n"))
    reached = set(_walk_bindings([("a", "route")], index=index))
    assert reached == {("a", "route"), ("a", "json"), ("a", "bee"), ("a", "helper"),
                       ("b", "thing"), ("b", "helper")}, sorted(reached)
    late = set(_walk_bindings([("a", "late_route")], index=index))
    assert late == {("a", "late_route"), ("b", "thing"), ("b", "unused")}, sorted(late)
    # Mutation: the route names b's dumps through its import -- now it is in.
    index["a"]["route"] = _tmp_index(tmp_path, a2=(
        "def route():\n"
        "    return json.dumps(bee.thing()), helper(), bee.dumps(1)\n"))["a2"]["route"]
    grown = set(_walk_bindings([("a", "route")], index=index))
    assert grown == reached | {("b", "dumps")}, sorted(grown)


def test_an_unrelated_module_with_common_imports_moves_no_route():
    """Negative control on the real app: a module no route imports, binding
    the names the app's own code uses most (`json`, `text`, `datetime`, a
    `dumps`, a `router`, a `W`), enters no route's closure. Non-vacuous: the
    app's routes do name `json.dumps`, `text` and `router`."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "zz_unrelated.py"
        path.write_text(
            "import hashlib\nimport hmac\nimport json\nimport math\n"
            "from datetime import datetime, timedelta, timezone\n"
            "from sqlalchemy import text\n"
            "W = {}\nrouter = None\nSIZES = ()\n"
            "def dumps(obj):\n    return json.dumps(obj)\n"
            "def ready():\n    return text\n", encoding="utf-8")
        extra = _index_module(path)
    index = dict(_binding_index())
    index["zz_unrelated"] = extra
    named = set()
    routes = [r for r in main.app.routes
              if isinstance(r, APIRoute) and r.path.startswith("/api/v1/")]
    for route in routes:
        seeds = _route_seeds(route)
        base = _reached(seeds)
        assert _walk_bindings(seeds, index=index) == base, route.path
        for module, name in base:
            named |= _binding_index()[module][name][2] & {"json.dumps", "text", "router"}
    assert named == {"json.dumps", "text", "router"}, sorted(named)


def test_a_real_route_whose_code_names_another_helper_grows():
    """Positive control on the real app: one real route's handler, re-indexed
    with one more line naming a seat evidence helper through main's own import
    of that module, reaches that helper and its fingerprint text moves."""
    index = {module: dict(table) for module, table in _binding_index().items()}
    target = ("seat_evidence", "budget_record")
    for route in main.app.routes:
        if not (isinstance(route, APIRoute) and route.path.startswith("/api/v1/")):
            continue
        seeds = _route_seeds(route)
        key = _binding_key(route.endpoint)
        if key and key[0] == "main" and target not in _reached(seeds):
            break
    else:
        raise AssertionError("no main route without the helper")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "main_mutant.py"
        path.write_text(_segment(*key).rstrip("\r\n") + "\n    _sev.budget_record\n",
                        encoding="utf-8")
        index["main"][key[1]] = _index_module(path)[key[1]]
    before = _reached(seeds)
    after = _walk_bindings(seeds, index=index)
    assert target in after and set(before) < set(after), route.path
    text = lambda idx, reached: "".join(idx[m][n][1] for m, n in sorted(reached))  # noqa: E731
    assert text(index, after) != text(_binding_index(), before)


def _closure_text(index, reached):
    return "".join(index[m][n][1] for m, n in sorted(reached))


def _with_segment(index, module, name, text):
    """A copy of `index` with one binding's source text replaced."""
    out = {m: dict(t) for m, t in index.items()}
    kind, _old, refs = out[module][name]
    out[module][name] = (kind, text, refs)
    return out


def test_a_reused_local_alias_keeps_every_branch_target(tmp_path):
    """Combat fix pass 1, M-9. A function-local alias bound on two branches
    (`import b as m` / `import c as m`, and `from b import helper as h` /
    `from c import helper as h`) reaches BOTH targets, so editing either
    side's helper moves the route's fingerprint text. Negative control: an
    edit to a binding neither branch reaches moves nothing."""
    index = _tmp_index(
        tmp_path,
        a=("def route(flag):\n"
           "    if flag:\n"
           "        import b as m\n"
           "    else:\n"
           "        import c as m\n"
           "    return m.helper()\n"
           "def from_route(flag):\n"
           "    if flag:\n"
           "        from b import helper as h\n"
           "    else:\n"
           "        from c import helper as h\n"
           "    return h()\n"),
        b="def helper():\n    return 1\ndef other():\n    return 3\n",
        c="def helper():\n    return 2\n")
    for seed in (("a", "route"), ("a", "from_route")):
        reached = set(_walk_bindings([seed], index=index))
        assert {("b", "helper"), ("c", "helper")} <= reached, (seed, sorted(reached))
        base = _closure_text(index, reached)
        for side in ("b", "c"):
            moved = _with_segment(index, side, "helper", "def helper():\n    return 9\n")
            assert _closure_text(moved, set(_walk_bindings([seed], index=moved))) != base, side
        still = _with_segment(index, "b", "other", "def other():\n    return 9\n")
        assert _closure_text(still, set(_walk_bindings([seed], index=still))) == base


def test_a_local_shadow_does_not_charge_the_module_binding(tmp_path):
    """Combat fix pass 1, M-9. A name a function binds locally is not the
    module's binding of that name: `route` assigns its own `case` and reads
    it, and the module's `case` import is NOT in its closure, so editing that
    import moves `route` not at all; `uses_import` reads the module's `case`
    and does move (positive control). A name declared `global` and a name
    read in a nested function stay resolved as before."""
    index = _tmp_index(
        tmp_path,
        a=("from sqlalchemy import case\n"
           "import d\n"
           "G = 1\n"
           "def route(x):\n"
           "    case = d.lookup(x)\n"
           "    return case.id, [c for c in case]\n"
           "def uses_import():\n"
           "    return case(1)\n"
           "def writes_global():\n"
           "    global G\n"
           "    G = 2\n"
           "def nested():\n"
           "    def inner():\n"
           "        return G\n"
           "    return inner\n"),
        d="def lookup(x):\n    return x\n")
    route = set(_walk_bindings([("a", "route")], index=index))
    assert ("a", "case") not in route and ("d", "lookup") in route, sorted(route)
    assert "case" not in index["a"]["route"][2] and "case.id" not in index["a"]["route"][2]
    uses = set(_walk_bindings([("a", "uses_import")], index=index))
    assert ("a", "case") in uses
    moved = _with_segment(index, "a", "case", "from sqlalchemy import case as case\n")
    assert _closure_text(moved, route) == _closure_text(index, route)
    assert _closure_text(moved, uses) != _closure_text(index, uses)
    assert ("a", "G") in set(_walk_bindings([("a", "writes_global")], index=index))
    assert ("a", "G") in set(_walk_bindings([("a", "nested")], index=index))


_CLASS_ORDER_SRC = (
    "from pydantic import BaseModel\n"
    "LIMIT = 5\n"
    "FLAG = True\n"
    "class Late(BaseModel):\n"
    "    n: int = LIMIT\n"
    "    LIMIT = 9\n"
    "class Cond(BaseModel):\n"
    "    if FLAG:\n"
    "        LIMIT = 9\n"
    "    n: int = LIMIT\n"
    "class Deleted(BaseModel):\n"
    "    LIMIT = 9\n"
    "    del LIMIT\n"
    "    n: int = LIMIT\n"
    "    LIMIT = 3\n"
    "class Rebound(BaseModel):\n"
    "    LIMIT = 9\n"
    "    del LIMIT\n"
    "    LIMIT = 3\n"
    "    n: int = LIMIT\n"
    "class Plain(BaseModel):\n"
    "    LIMIT = 9\n"
    "    n: int = LIMIT\n"
    "class Method(BaseModel):\n"
    "    LIMIT = 9\n"
    "    def method(self):\n"
    "        return LIMIT\n"
    "class Lam(BaseModel):\n"
    "    LIMIT = 9\n"
    "    f = lambda: LIMIT\n"
    "class Comp(BaseModel):\n"
    "    LIMIT = 9\n"
    "    xs = [LIMIT for _ in (1,)]\n"
    "def outer_bound():\n"
    "    LIMIT = 7\n"
    "    class Inner(BaseModel):\n"
    "        n: int = LIMIT\n"
    "        LIMIT = 9\n"
    "    return Inner\n"
    "def outer_free():\n"
    "    LIMIT = 7\n"
    "    class Free(BaseModel):\n"
    "        n: int = LIMIT\n"
    "    return Free\n")


def test_a_class_body_read_charges_every_binding_it_may_denote(tmp_path):
    """Combat fix pass 2, M-9. A response model's class body runs top to
    bottom: a read before a late class binding (`Late`), beside a
    conditional one (`Cond`) or after a `del` (`Deleted`) may denote the
    module's binding, so the module's `LIMIT` is in that model's closure and
    an edit to it moves the model's fingerprint text. Control: a class
    binding made certain before the read (`Plain`) charges the module
    nothing and an edit to the module's `LIMIT` moves nothing. Fix pass 3:
    a `del` CHARGES the module binding where it stands (the conservative
    class-body bound), so `Rebound` (delete, rebind, read) is charged too,
    a deliberate over-approximation. A method, a lambda and a
    comprehension inside a class still skip its names (`Method`, `Lam`,
    `Comp`). Inside a function, a read of a name the class binds falls back
    to the module, never the function (`outer_bound`); a name the class
    does not bind is the function's own (`outer_free`)."""
    index = _tmp_index(tmp_path, a=_CLASS_ORDER_SRC)
    moved = _with_segment(index, "a", "LIMIT", "LIMIT = 6\n")
    for model, charged in (("Late", True), ("Cond", True), ("Deleted", True), ("Method", True),
                           ("Lam", True), ("Comp", True), ("Plain", False), ("Rebound", True)):
        reached = set(_walk_bindings([("a", model)], index=index))
        assert (("a", "LIMIT") in reached) is charged, (model, sorted(reached))
        base = _closure_text(index, reached)
        after = _closure_text(moved, set(_walk_bindings([("a", model)], index=moved)))
        assert (after != base) is charged, model
    assert "LIMIT" in index["a"]["outer_bound"][2]
    assert "LIMIT" not in index["a"]["outer_free"][2]                    # the function's own


def test_the_class_order_reading_is_what_the_interpreter_does(tmp_path):
    """The reading above is the interpreter's: each model built from the
    same source gives the value of the binding the walk charges."""
    ns = {}
    exec(compile(_CLASS_ORDER_SRC.replace("from pydantic import BaseModel\n",
                                          "BaseModel = object\n"), "a", "exec"), ns)
    assert ns["Late"].n == 5 and ns["Cond"].n == 9 and ns["Deleted"].n == 5
    assert ns["Rebound"].n == 3 and ns["Plain"].n == 9
    assert ns["Method"]().method() == 5 and ns["Lam"].f() == 5 and ns["Comp"].xs == [5]
    assert ns["outer_bound"]().n == 5 and ns["outer_free"]().n == 7


def test_the_tip_witness_local_case_is_not_charged_to_the_sqlalchemy_import():
    """The real app: `_moderation_case_act` binds its own `case` (the row it
    reads) while main imports sqlalchemy's `case` at module scope. The local
    is not a reference to the import."""
    table = _binding_index()["main"]
    assert table["case"][0] == "import"
    witness = table["_moderation_case_act"]
    assert "case" in witness[1] and "case" not in witness[2]
    assert "case_id" not in witness[2]                     # a parameter is local too


# ── Combat fix pass 3, M-9: the conservative class-body bound ────────────

_CLASS_BOUND_SRC = (
    "from pydantic import BaseModel\n"
    "LIMIT = 5\n"
    "class NS:\n"
    "    pass\n"
    "ns = NS()\n"
    "table = {}\n"
    "def f(**kw):\n"
    "    return kw\n"
    "class AugOnly(BaseModel):\n"
    "    LIMIT += 1\n"
    "class Aug(BaseModel):\n"
    "    LIMIT += 1\n"
    "    n: int = LIMIT\n"
    "class Exc(BaseModel):\n"
    "    LIMIT = 9\n"
    "    try:\n"
    "        raise ValueError\n"
    "    except ValueError as LIMIT:\n"
    "        pass\n"
    "    n: int = LIMIT\n"
    "class ExcFinally(BaseModel):\n"
    "    LIMIT = 9\n"
    "    try:\n"
    "        raise ValueError\n"
    "    except ValueError as LIMIT:\n"
    "        pass\n"
    "    finally:\n"
    "        m = LIMIT\n"
    "class Capture(BaseModel):\n"
    "    LIMIT = 9\n"
    "    match 0:\n"
    "        case LIMIT:\n"
    "            pass\n"
    "    n: int = LIMIT\n"
    "class Loop(BaseModel):\n"
    "    LIMIT = 9\n"
    "    for LIMIT in (1,):\n"
    "        pass\n"
    "    n: int = LIMIT\n"
    "class Walrus(BaseModel):\n"
    "    LIMIT = 9\n"
    "    x = (LIMIT := 3)\n"
    "    n: int = LIMIT\n"
    "class AttrStore(BaseModel):\n"
    "    LIMIT = 9\n"
    "    ns.LIMIT = 1\n"
    "    n: int = LIMIT\n"
    "class SubStore(BaseModel):\n"
    "    LIMIT = 9\n"
    "    table['LIMIT'] = 1\n"
    "    n: int = LIMIT\n"
    "class Unpack(BaseModel):\n"
    "    LIMIT = 9\n"
    "    [a, *b] = (1, 2)\n"
    "    c, d = 3, 4\n"
    "    n: int = LIMIT\n"
    "class Keyword(BaseModel):\n"
    "    LIMIT = 9\n"
    "    x = f(LIMIT=1)\n"
    "    n: int = LIMIT\n"
    "class Pattern(BaseModel):\n"
    "    LIMIT = 9\n"
    "    match 0:\n"
    "        case NS(LIMIT=1):\n"
    "            pass\n"
    "    n: int = LIMIT\n"
    "class Param(BaseModel):\n"
    "    LIMIT = 9\n"
    "    def method(self, LIMIT=LIMIT):\n"
    "        return LIMIT\n"
    "    n: int = LIMIT\n"
    "class Glob(BaseModel):\n"
    "    global LIMIT\n"
    "    n: int = LIMIT\n"
    "class CompTarget(BaseModel):\n"
    "    table[[LIMIT for LIMIT in (0,)][0]] = 1\n"
    "    n = LIMIT\n"
    "    LIMIT = 9\n"
    "class GenTarget(BaseModel):\n"
    "    [table[next(LIMIT for LIMIT in (0,))], c] = 1, 2\n"
    "    n = LIMIT\n"
    "    LIMIT = 9\n"
    "class LambdaTarget(BaseModel):\n"
    "    table[(lambda LIMIT=0: LIMIT)()] = 1\n"
    "    n = LIMIT\n"
    "    LIMIT = 9\n"
    "def outer_nonlocal():\n"
    "    LIMIT = 7\n"
    "    class NonLocal(BaseModel):\n"
    "        nonlocal LIMIT\n"
    "        n: int = LIMIT\n"
    "    return NonLocal\n")

# Walker-only rows (the interpreter cannot import a module named LIMIT).
_CLASS_WALK_ONLY_SRC = (
    "LIMIT = 5\n"
    "class FromModule:\n"
    "    LIMIT = 9\n"
    "    from LIMIT import thing\n"
    "    n = LIMIT\n")

# Each identifier or context field the walk models as binding nothing, with
# the binding that controls it: (source, model, module LIMIT charged?).
_CLASS_FIELD_CONTROLS = {
    ("Attribute", "attr"): ("bound", "AttrStore", False),
    ("Attribute", "ctx"): ("bound", "AttrStore", False),
    ("Subscript", "ctx"): ("bound", "SubStore", False),
    ("List", "ctx"): ("bound", "Unpack", False),
    ("Tuple", "ctx"): ("bound", "Unpack", False),
    ("Starred", "ctx"): ("bound", "Unpack", False),
    ("keyword", "arg"): ("bound", "Keyword", False),
    ("ImportFrom", "module"): ("walk", "FromModule", False),
    ("MatchClass", "kwd_attrs"): ("bound", "Pattern", False),
    ("arg", "arg"): ("bound", "Param", False),
    ("Global", "names"): ("bound", "Glob", True),               # the declared global: the module's
    ("Nonlocal", "names"): ("bound", "outer_nonlocal", False),  # the function's own
}

# The charged constructs, read through the same response-model check: the
# reviewer's two scenarios (an augmented assignment, with and without a later
# read; a read after an exception alias, after the statement and inside it)
# and a match capture, a loop target and a walrus.
_CLASS_CHARGED_ROWS = (("AugOnly", True), ("Aug", True), ("Exc", True), ("ExcFinally", True),
                       ("Capture", True), ("Loop", True), ("Walrus", True),
                       # fix pass 4: the reviewer's comprehension target inside a
                       # subscript target, verbatim, and two siblings
                       ("CompTarget", True), ("GenTarget", True), ("LambdaTarget", True))


def test_every_ast_name_field_is_modelled_with_a_control_or_charged():
    """Combat fix pass 3, M-9. The node types that can bind or unbind a name
    are ENUMERATED from the interpreter (every node signature with an
    `identifier` or `expr_context` field); each (type, field) is either
    modelled as binding nothing, with a control row, or charged: a node of
    that type carrying the identifier is touched by `_class_touched`, which
    the walk charges. A node type the signatures do not describe is charged
    on every string field (the default for a future construct); a described
    non-identifier string (a constant) is not."""
    generated = {(kind, field) for kind, fields in _AST_NAME_FIELDS.items() for field in fields}
    known = {("Name", "id"), ("Name", "ctx"), ("ExceptHandler", "name"), ("MatchAs", "name"),
             ("MatchStar", "name"), ("MatchMapping", "rest"), ("FunctionDef", "name"),
             ("ClassDef", "name"), ("alias", "name"), ("alias", "asname")}
    assert known <= generated, sorted(known - generated)        # the signatures were read
    assert set(_CLASS_NOT_BINDING) <= generated, sorted(set(_CLASS_NOT_BINDING) - generated)
    assert set(_CLASS_NOT_BINDING) == set(_CLASS_FIELD_CONTROLS)
    charged = sorted(generated - set(_CLASS_NOT_BINDING))
    assert charged, "nothing charged"
    for kind, field in charged:
        node = getattr(ast, kind)()
        if field == "ctx":
            for ctx in (ast.Store(), ast.Del()):
                node.id, node.ctx = "PROBE", ctx
                assert "PROBE" in _class_touched(node), (kind, field, ctx)
            node.ctx = ast.Load()
            assert "PROBE" not in _class_touched(node)                  # a read binds nothing
            continue
        setattr(node, field, "PROBE")
        if kind == "Name":
            node.ctx = ast.Store()
        assert "PROBE" in _class_touched(node), (kind, field)
    for kind, field in _CLASS_NOT_BINDING:
        if field != "ctx":
            node = getattr(ast, kind)()
            setattr(node, field, "PROBE")
            assert "PROBE" not in _class_touched(node), (kind, field)

    class FutureBinder(ast.stmt):
        _fields = ("label",)
    assert "FutureBinder" not in _AST_NAME_FIELDS
    assert _class_touched(FutureBinder(label="PROBE")) == {"PROBE"}
    assert _class_touched(ast.Constant(value="PROBE")) == set()         # described, no identifier


@pytest.mark.parametrize("model, charged", list(_CLASS_CHARGED_ROWS)
                         + [(row[1], row[2]) for row in _CLASS_FIELD_CONTROLS.values()])
def test_a_class_body_construct_charges_the_module_binding_unless_modelled(tmp_path, model,
                                                                           charged):
    """Combat fix pass 3, M-9, response-model controls. Each model binds
    `LIMIT` in its body and then runs one construct: the charged constructs
    put the module's `LIMIT` in the model's closure, and an edit to it moves
    the model's fingerprint text; the constructs modelled as binding nothing
    leave a certain class binding certain, and the edit moves nothing (a
    declared global reads the module's, a declared nonlocal the function's)."""
    walk_only = any(row[1] == model and row[0] == "walk" for row in _CLASS_FIELD_CONTROLS.values())
    index = _tmp_index(tmp_path, a=_CLASS_WALK_ONLY_SRC if walk_only else _CLASS_BOUND_SRC)
    assert ("LIMIT" in index["a"][model][2]) is charged, (model, sorted(index["a"][model][2]))
    reached = set(_walk_bindings([("a", model)], index=index))
    assert (("a", "LIMIT") in reached) is charged, (model, sorted(reached))
    moved = _with_segment(index, "a", "LIMIT", "LIMIT = 6\n")
    after = _closure_text(moved, set(_walk_bindings([("a", model)], index=moved)))
    assert (after != _closure_text(index, reached)) is charged, model


def test_the_class_bound_rows_are_what_the_interpreter_does():
    """The same source run: the charged rows read the module's `LIMIT` (5)
    where the reviewer's scenarios say they do, and an edit to it changes
    the value; the modelled rows read the class's (9)."""
    def run(src):
        ns = {}
        exec(compile(src.replace("from pydantic import BaseModel\n", "BaseModel = object\n"),
                     "a", "exec"), ns)
        return ns
    ns = run(_CLASS_BOUND_SRC)
    assert ns["AugOnly"].LIMIT == 6 and ns["Aug"].n == 6
    assert ns["Exc"].n == 5 and ns["ExcFinally"].m == 5
    assert ns["Capture"].n == 0 and ns["Loop"].n == 1 and ns["Walrus"].n == 3
    for model in ("AttrStore", "SubStore", "Unpack", "Keyword", "Pattern", "Param"):
        assert ns[model].n == 9, model
    assert ns["Glob"].n == 5 and ns["outer_nonlocal"]().n == 7
    for model in ("CompTarget", "GenTarget", "LambdaTarget"):            # fix pass 4
        assert ns[model].n == 5 and ns[model].LIMIT == 9, model
    edited = run(_CLASS_BOUND_SRC.replace("LIMIT = 5\n", "LIMIT = 6\n", 1))
    assert edited["AugOnly"].LIMIT == 7 and edited["Exc"].n == 6 and edited["ExcFinally"].m == 6
    for model in ("CompTarget", "GenTarget", "LambdaTarget"):
        assert edited[model].n == 6, model


# ── Combat fix pass 4, M-9: lexical ownership, proved against the interpreter ──

# Sub-expressions that carry the name LIMIT in every role it can take inside
# an expression: a comprehension, generator or dict-comprehension target
# (bound in that nested scope), a read inside a comprehension or a lambda (of
# the module's, the class's names are not visible there), a lambda parameter,
# an attribute name, a string subscript key, a keyword.
_ORACLE_SUBS = {
    "plain": "0",
    "comp_bind": "[LIMIT for LIMIT in (0,)][0]",
    "comp_read": "[LIMIT for _ in (0,)][0]",
    "gen_bind": "next(LIMIT for LIMIT in (0,))",
    "dictcomp_bind": "len({LIMIT: 0 for LIMIT in (0,)})",
    "lambda_param": "(lambda LIMIT=0: LIMIT)()",
    "lambda_read": "(lambda: LIMIT)()",
    "attribute": "ns.LIMIT",
    "subscript": "table['LIMIT']",
    "keyword": "dict(LIMIT=0)['LIMIT']",
}

# Each statement form the walk models exactly (_CLASS_EXACT: assignment in
# every target shape, annotated assignment with a value, def, async def,
# class, import, from-import), the sub-expression `{e}` placed in its value,
# its subscript or attribute target, its annotation, defaults, decorator or
# bases. Continuation lines carry their own indentation.
_ORACLE_STMTS = {
    "assign_name": "LIMIT = {e}",
    "assign_other": "other = {e}",
    "assign_subscript": "table[{e}] = 1",
    "assign_attribute": "(ns, {e})[0].attr = 1",
    "assign_attr_value": "ns.LIMIT = {e}",
    "assign_tuple": "LIMIT, other = {e}, 1",
    "assign_list_sub": "[table[{e}], other] = 1, 2",
    "assign_starred": "[LIMIT, *rest] = ({e}, 1)",
    "assign_starred_sub": "[other, *table[{e}]] = (1, 2)",
    "assign_chain": "LIMIT = other = {e}",
    "annassign_name": "LIMIT: int = {e}",
    "annassign_subscript": "table[{e}]: int = 1",
    "annassign_attribute": "(ns, {e})[0].attr: int = 1",
    "annassign_annotation": "other: ({e}) = 1",
    "def_name": "def LIMIT(a={e}):\n        return a",
    "def_other": "def g(a={e}):\n        return a",
    "def_decorated": "@(lambda f: ({e}, f)[1])\n    def LIMIT():\n        pass",
    "asyncdef_name": "async def LIMIT(a={e}):\n        return a",
    "class_name": "class LIMIT((object, {e})[0]):\n        pass",
    "class_other": "class K((object, {e})[0]):\n        x = {e}",
    "import_name": "import os as LIMIT",
    "from_import": "from os import sep as LIMIT",
    "import_other": "import os",
}

_ORACLE_HELPERS = ("class NS:\n"
                   "    LIMIT = 0\n"
                   "ns = NS()\n"
                   "table = {'LIMIT': 0}\n")

# The reviewer's class body, verbatim (round 4, M-9).
_ORACLE_REVIEWER = ("    table[[LIMIT for LIMIT in (0,)][0]] = 1\n"
                    "    n = LIMIT\n"
                    "    LIMIT = 9\n")


def _oracle_family():
    """[(label, class body)] for every statement form, every sub-expression
    (once for a form without one), with and without an earlier class
    binding, with and without a later one; each body reads LIMIT after the
    statement."""
    out = []
    for sname, stmt in _ORACLE_STMTS.items():
        subs = _ORACLE_SUBS.items() if "{e}" in stmt else [("none", "")]
        for xname, e in subs:
            for pre in ("", "    LIMIT = 7\n"):
                for late in ("", "    LIMIT = 9\n"):
                    body = pre + "    " + stmt.replace("{e}", e) + "\n    n = LIMIT\n" + late
                    out.append(((sname, xname, bool(pre), bool(late)), body))
    return out


class _ModuleReads(dict):
    """A builtins mapping that records every name looked up in it. The
    module-level LIMIT lives here instead of in the module's globals, so
    every read the interpreter makes past the class namespace and the
    globals (a class-body read, a comprehension's or a lambda's) is seen."""

    def __init__(self, values):
        super().__init__(values)
        self.seen = set()

    def __getitem__(self, key):
        self.seen.add(key)
        return super().__getitem__(key)


def _interpreter_reads_module_limit(body):
    """True when executing the class body reads the module's LIMIT (fix
    pass 5: and forcing every lazy part of what it made, `_force`)."""
    return "LIMIT" in _interpreter_reads("class C:\n" + body)


def _force(values, depth=0):
    """Make the reads a later use of these objects would make (combat fix
    pass 5): each type parameter's bound and constraints and each type
    alias's value (evaluated lazily, on first access), and one call with no
    arguments of each function the executed source defined (a coroutine is
    driven to its end); a class is entered, its namespace forced in turn."""
    for v in list(values):
        if isinstance(v, (staticmethod, classmethod)):
            v = v.__func__
        if isinstance(v, type) and depth < 3:
            _force([x for k, x in vars(v).items() if not k.startswith("__")], depth + 1)
        for tp in getattr(v, "__type_params__", None) or ():
            if isinstance(tp, typing.TypeVar):
                for attr in ("__bound__", "__constraints__"):
                    with contextlib.suppress(Exception):
                        getattr(tp, attr)
        if isinstance(v, typing.TypeAliasType):
            with contextlib.suppress(Exception):
                v.__value__
        if inspect.isfunction(v) and v.__code__.co_filename == "a":
            with contextlib.suppress(Exception):
                result = v()
                if inspect.iscoroutine(result):
                    with contextlib.suppress(BaseException):
                        result.send(None)
                    result.close()


def _interpreter_reads(src, value=5, helpers=None):
    """The names the interpreter reads past the module's own globals when it
    executes `src` after the helpers and forces what it made (`_force`): the
    module's LIMIT (= `value`) lives in a recording builtins mapping, so every
    read of it is seen. A runtime error ends the execution; the reads before
    it stand (a read that leads to an error is still a read)."""
    import builtins
    rec = _ModuleReads(dict(vars(builtins), LIMIT=value))
    glb = {"__builtins__": rec}
    exec(compile(_ORACLE_HELPERS if helpers is None else helpers, "a", "exec",
                 dont_inherit=True), glb)
    rec.seen.clear()
    code = compile(src, "a", "exec", dont_inherit=True)
    with contextlib.suppress(Exception):
        exec(code, glb)
    _force([v for k, v in glb.items() if k != "__builtins__"])
    return set(rec.seen)


def test_the_walk_charges_every_module_read_the_interpreter_makes(tmp_path, capsys):
    """Combat fix pass 4, M-9, the ORACLE. A generated family of class
    bodies (every statement form the walk models exactly, every
    sub-expression carrying the name LIMIT, with and without an earlier and
    a later class binding) is executed by the interpreter with the module's
    LIMIT behind a recording mapping, and the walk's charge for each class
    is compared with what the interpreter actually read: the walk must
    charge a SUPERSET. The reviewer's body verbatim is one member and reads
    the module. Controls: the recorder sees a plain read and not a read
    after a class binding, and the family has both outcomes."""
    family = _oracle_family()
    assert len(family) == (20 * len(_ORACLE_SUBS) + 3) * 4 == 812
    assert any(body == _ORACLE_REVIEWER for _label, body in family)
    src = "LIMIT = 5\n" + _ORACLE_HELPERS + "".join(
        "class C%d:\n%s" % (k, body) for k, (_label, body) in enumerate(family))
    index = _tmp_index(tmp_path, a=src)
    missed, reads = [], 0
    for k, (label, body) in enumerate(family):
        read = _interpreter_reads_module_limit(body)
        reads += read
        if read and "LIMIT" not in index["a"]["C%d" % k][2]:
            missed.append(label)
        if body == _ORACLE_REVIEWER:
            assert read, "the reviewer's body reads the module's LIMIT"
    assert missed == [], missed[:20]
    assert 0 < reads < len(family), reads
    assert _interpreter_reads_module_limit("    other = 0\n    n = LIMIT\n")
    assert not _interpreter_reads_module_limit("    LIMIT = 7\n    n = LIMIT\n")
    with capsys.disabled():
        print("\nPROOF SIZE f4_m9 oracle: %d class bodies executed, %d read the module's LIMIT, "
              "%d missed by the walk" % (len(family), reads, len(missed)))


# ── Combat fix pass 5, M-9: the default visit, proved complete ───────────

_DOCKERFILE = Path(__file__).parents[1] / "api" / "Dockerfile"

# The census of the pinned interpreter's node classes: (classes, (class,
# field) pairs, SHA-1 of the sorted "Class.field:type" lines). An interpreter
# that gains or loses a class or a field fails the completeness test until
# its new rows are read and this pin is renewed.
_CENSUS_PIN = (132, 188, "7dc7188805358ffd1214e6b21b21cae213b07582")
_STRING_TYPES = ("identifier", "string", "constant")


def _pinned_minor():
    """(major, minor) of the interpreter the api image is built on."""
    m = re.search(r"^FROM python:(\d+)\.(\d+)", _DOCKERFILE.read_text(encoding="utf-8"), re.M)
    assert m, "the Dockerfile names no python base image"
    return int(m.group(1)), int(m.group(2))


def _node_census():
    """{class name: ((field, ASDL type, quantifier), ...)} for EVERY node
    class the running interpreter's `ast` module defines (an AST subclass;
    one without fields maps to ()), fields in the class's own `_fields`
    order, each type read from the class's ASDL line (its docstring)."""
    out = {}
    for name, cls in sorted(vars(ast).items()):
        if not (isinstance(cls, type) and issubclass(cls, ast.AST)):
            continue
        if not cls._fields:
            out[name] = ()
            continue
        sig = (cls.__doc__ or "").strip().split("\n")[0]
        m = re.fullmatch(r"(\w+)\((.*)\)", sig)
        assert m and m.group(1) == name, (name, sig)
        typed = {}
        for part in m.group(2).split(","):
            asdl, field = part.split()
            typed[field] = asdl
        assert set(typed) == set(cls._fields), (name, cls._fields, typed)
        out[name] = tuple((f, typed[f].rstrip("?*"), typed[f][-1] if typed[f][-1] in "?*" else "")
                          for f in cls._fields)
    return out


def _classes_of(census, t):
    """The parser's node classes a value of ASDL type `t` may be: the class
    of that name when it has fields (a product type), else every class of
    the parser's own module derived from the type's base class."""
    import _ast
    if census.get(t):
        return [t]
    base = getattr(ast, t, None)
    if not (isinstance(base, type) and issubclass(base, ast.AST)):
        return []
    return sorted(n for n in census if n != t and n in vars(_ast)
                  and issubclass(getattr(ast, n), base))


def _carries(census, t, seen=frozenset()):
    """Whether a value of ASDL type `t` can hold a name the walk must
    charge: a string type can (its row decides), an int never; a node type
    when one of its classes has a field outside _NOT_CHARGED of a type that
    can."""
    if t in _STRING_TYPES:
        return True
    if t == "int" or t in seen:
        return False
    return any((c, f) not in _NOT_CHARGED and _carries(census, ft, seen | {t})
               for c in _classes_of(census, t) for f, ft, _q in census[c])


def _neutral(census, t, q):
    """A value of type `t` that holds no name the probe looks for: an empty
    list, None for an optional, "n_", 0, a read context, or the first
    field-less class of the type (an operator)."""
    if q == "*":
        return []
    if q == "?":
        return None
    if t in _STRING_TYPES:
        return "n_"
    if t == "int":
        return 0
    if t == "expr_context":
        return ast.Load()
    leaves = [c for c in _classes_of(census, t) if not census[c]]
    return getattr(ast, leaves[0])() if leaves else None


def _probe(census, t, q, name, seen=frozenset()):
    """A value of type `t` (quantifier `q`) holding `name` at a position the
    walk must charge, built from the census alone: a string is the name; a
    node is the first class of the type with a chargeable field, that field
    probed in turn and every other field neutral."""
    value = None
    if t in _STRING_TYPES:
        value = name
    else:
        for c in _classes_of(census, t):
            f = next((f for f, ft, _q in census[c]
                      if (c, f) not in _NOT_CHARGED and _carries(census, ft, seen | {t})), None)
            if f is not None:
                value = _probe_node(census, c, f, name, seen | {t})
                break
    if q == "*":
        return [] if value is None else [value]
    return value


def _probe_node(census, c, f, name, seen=frozenset()):
    """A node of class `c` whose field `f` holds `name` (`_probe`), every
    other field neutral."""
    node = getattr(ast, c)()
    for g, gt, gq in census[c]:
        setattr(node, g, _neutral(census, gt, gq))
    ft, fq = next((gt, gq) for g, gt, gq in census[c] if g == f)
    setattr(node, f, _probe(census, ft, fq, name, seen))
    return node


def test_f5_every_node_field_is_charged_by_the_default_visit_or_excluded(monkeypatch, capsys):
    """Combat fix pass 5, M-9, the BOUND. Every node class the pinned
    interpreter defines and every one of its fields is enumerated (the
    census); the interpreter running this test is the minor the api image
    pins, and the census is pinned, so a new class or field fails here. For
    each (class, field):
      * a field that can hold a name the walk must charge (a string, or a
        node type that can carry one) and is no row of _NOT_CHARGED gets a
        probe built from the census, and the walk CHARGES the probe;
      * a row of _NOT_CHARGED sits on a string field (a node field is never
        dropped: placement moves it, nothing removes it), has a role and a
        one-line reason;
      * every field of every class is READ by the walk (`_node_fields`,
        recorded), including the fields that cannot hold a name.
    A field nobody listed is charged by default, so the next unvisited
    position cannot exist without this test going red."""
    import _ast
    census = _node_census()
    pairs = [(c, f, t) for c, fields in census.items() for f, t, _q in fields]
    digest = sha1("".join("%s.%s:%s\n" % p for p in sorted(pairs)).encode("ascii")).hexdigest()
    assert sys.version_info[:2] == _pinned_minor(), (sys.version_info[:2], _pinned_minor())
    assert (len(census), len(pairs), digest) == _CENSUS_PIN, (len(census), len(pairs), digest)
    for c, f, t in pairs:
        assert t in _STRING_TYPES or t == "int" or _classes_of(census, t), (c, f, t)
    types = {(c, f): t for c, f, t in pairs}
    for row, (role, reason) in _NOT_CHARGED.items():
        assert types.get(row) in _STRING_TYPES, row
        assert role in ("attr", "label", "import", "global", "nonlocal", "bind", "param",
                        "literal"), row
        assert reason and "\n" not in reason, row
    for row, place in _FIELD_SCOPE.items():
        assert row in types and row not in _NOT_CHARGED, row
        assert place in ("inner", "annotation", "outer", "class_body", "generators", "iter",
                         "home"), row
    read = set()
    real = _node_fields

    def recording(n):
        for field, value in real(n):
            read.add((type(n).__name__, field))
            yield field, value

    monkeypatch.setitem(globals(), "_node_fields", recording)
    charged, excluded, nameless, uncharged = [], [], [], []
    for c, f, t in sorted(pairs):
        if (c, f) in _NOT_CHARGED:
            excluded.append((c, f))
        elif not _carries(census, t):
            nameless.append((c, f))
        else:
            probe = "PROBE_%s_%s" % (c, f)
            if probe in _references(_probe_node(census, c, f, probe)):
                charged.append((c, f))
            else:
                uncharged.append((c, f))
    for c, fields in census.items():
        if fields and c in vars(_ast):
            _references(_probe_node(census, c, fields[0][0], "n_"))
    unread = sorted({(c, f) for c, f, _t in pairs if c in vars(_ast)} - read)
    assert uncharged == [], uncharged
    assert unread == [], unread
    assert len(charged) + len(excluded) + len(nameless) == len(pairs)
    assert charged and nameless and len(excluded) == len(_NOT_CHARGED)
    with capsys.disabled():
        print("\nPROOF SIZE f5_m9 census: python %d.%d (the api image pins %d.%d), %d node classes, "
              "%d (class, field) pairs: %d charged by the default visit, %d rows of the exclusion "
              "table, %d that hold no name; %d read by the walk"
              % (sys.version_info[0], sys.version_info[1], *_pinned_minor(), len(census),
                 len(pairs), len(charged), len(excluded), len(nameless), len(read)))


# Each excluded row's own control: a module whose function `f` holds the
# row's field with the name the row must not charge, and whether the
# interpreter can run it (f is then called and must read no module value of
# that name). None: the parser fills the field only with type comments on.
_NOT_CHARGED_CONTROLS = {
    ("Attribute", "attr"): ("def f():\n    return ns.LIMIT\n", "LIMIT", True),
    ("keyword", "arg"): ("def f():\n    return dict(LIMIT=0)\n", "LIMIT", True),
    ("MatchClass", "kwd_attrs"): ("def f():\n    match ns:\n        case NS(LIMIT=0):\n"
                                  "            return 1\n", "LIMIT", True),
    ("alias", "name"): ("def f():\n    import LIMIT as other\n    return other\n", "LIMIT", False),
    ("alias", "asname"): ("class f:\n    import os as LIMIT\n", "LIMIT", True),
    ("ImportFrom", "module"): ("def f():\n    from LIMIT import thing as other\n    return other\n",
                               "LIMIT", False),
    ("Global", "names"): ("def f():\n    global LIMIT\n", "LIMIT", True),
    ("Nonlocal", "names"): ("def f():\n    LIMIT = 0\n    def g():\n        nonlocal LIMIT\n"
                            "        LIMIT = 1\n    return g\n", "LIMIT", True),
    ("FunctionDef", "name"): ("def f():\n    def LIMIT():\n        pass\n", "LIMIT", True),
    ("AsyncFunctionDef", "name"): ("def f():\n    async def LIMIT():\n        pass\n", "LIMIT",
                                   True),
    ("ClassDef", "name"): ("def f():\n    class LIMIT:\n        pass\n", "LIMIT", True),
    ("ExceptHandler", "name"): ("def f():\n    try:\n        raise ValueError\n"
                                "    except ValueError as LIMIT:\n        pass\n", "LIMIT", True),
    ("MatchAs", "name"): ("def f():\n    match 0:\n        case LIMIT:\n            pass\n",
                          "LIMIT", True),
    ("MatchStar", "name"): ("def f():\n    match (0,):\n        case [*LIMIT]:\n            pass\n",
                            "LIMIT", True),
    ("MatchMapping", "rest"): ("def f():\n    match {}:\n        case {**LIMIT}:\n"
                               "            pass\n", "LIMIT", True),
    ("arg", "arg"): ("def f(LIMIT=0):\n    pass\n", "LIMIT", True),
    ("TypeVar", "name"): ("def f[LIMIT]():\n    pass\n", "LIMIT", True),
    ("ParamSpec", "name"): ("def f[**LIMIT]():\n    pass\n", "LIMIT", True),
    ("TypeVarTuple", "name"): ("def f[*LIMIT]():\n    pass\n", "LIMIT", True),
    ("Constant", "value"): ("def f():\n    return 'LIMIT'\n", "LIMIT", True),
    ("Constant", "kind"): ("def f():\n    return u'x'\n", "u", True),
    ("MatchSingleton", "value"): ("def f():\n    match 0:\n        case None:\n"
                                  "            pass\n", "None", True),
    ("Assign", "type_comment"): None,
    ("For", "type_comment"): None,
    ("AsyncFor", "type_comment"): None,
    ("With", "type_comment"): None,
    ("AsyncWith", "type_comment"): None,
    ("FunctionDef", "type_comment"): None,
    ("AsyncFunctionDef", "type_comment"): None,
    ("arg", "type_comment"): None,
    ("TypeIgnore", "tag"): None,
}


def test_f5_every_excluded_row_has_its_own_control():
    """Combat fix pass 5, M-9: the exclusion table and its controls name the
    same rows, so a row cannot be added without a test, and a control whose
    row was removed fails in its own test below."""
    assert set(_NOT_CHARGED_CONTROLS) == set(_NOT_CHARGED), \
        sorted(set(_NOT_CHARGED) ^ set(_NOT_CHARGED_CONTROLS))


@pytest.mark.parametrize("row", sorted(_NOT_CHARGED_CONTROLS), ids="%s_%s".__mod__)
def test_f5_an_excluded_field_is_not_charged_and_its_control_agrees(row, tmp_path):
    """Combat fix pass 5, M-9, one test per row of the exclusion table: the
    row's field holding a probe string is not charged (were the row gone,
    the default visit would charge it and this fails), and the row's source
    control holds the name in that field: the walk does not charge it, and
    where the interpreter can run the control, it reads no module value of
    that name either (the row's reason is the interpreter's)."""
    census = _node_census()
    assert "PROBE_ROW" not in _references(_probe_node(census, row[0], row[1], "PROBE_ROW")), row
    control = _NOT_CHARGED_CONTROLS[row]
    if control is not None:
        src, name, runs = control
        assert name in src, row
        index = _tmp_index(tmp_path, a=_ORACLE_HELPERS + src)
        assert name not in index["a"]["f"][2], (row, sorted(index["a"]["f"][2]))
        if runs:
            assert name not in _interpreter_reads(src), row
    assert row in _NOT_CHARGED, row


# ── Combat fix pass 5, M-9: the oracle grows with the walk ───────────────

class _LimitMeta(type):
    """The metaclass of the module value the new oracle families read: a
    class that is iterable (empty), subscriptable, truthy and a context
    manager, so a read of it in most positions is followed by the rest of
    the statement rather than by an error."""

    def __iter__(cls):
        return iter(())

    def __getitem__(cls, key):
        return cls

    def __bool__(cls):
        return True

    def __enter__(cls):
        return cls

    def __exit__(cls, *exc):
        return False


class _LimitValue(metaclass=_LimitMeta):
    """The module's LIMIT in the new families: a class (a base, a bound, a
    class pattern), callable with anything (a decorator, a metaclass), with
    the attributes the skeletons' dotted values name."""
    x_ = 1
    y_ = 0
    __match_args__ = ("x_",)

    def __init__(self, *args, **kwargs):
        pass

    def __init_subclass__(cls, **kwargs):
        pass


_ORACLE_HELPERS_5 = _ORACLE_HELPERS + "NS.x_ = 1\nNS.y_ = 0\nNS.__match_args__ = ('y_',)\n"

# PEP-695 forms inside a class body, `{e}` in a bound, a constraint, a base,
# a keyword, an annotation, a default, a body or a type alias's value; each
# forced after the class is made (`_force`), with and without an earlier and
# a later class binding, and with an earlier one deleted after the form (the
# lazy bound then reads the module).
_ORACLE_STMTS_695 = {
    "class_bound": "class K[T: {e}]:\n        pass",
    "class_constraints": "class K[T: ({e}, int)]:\n        pass",
    "class_base": "class K[T]((object, {e})[0]):\n        pass",
    "class_keyword": "class K[T](metaclass=(type, {e})[0]):\n        pass",
    "class_name": "class LIMIT[T: {e}]:\n        pass",
    "class_body": "class K[T]:\n        x = {e}",
    "def_bound": "def g[T: {e}](a: T = None) -> T:\n        return a",
    "def_constraints": "def g[T: ({e}, int)]():\n        pass",
    "def_annotation": "def g[T](a: (T, {e})[0] = None) -> (T, {e})[0]:\n        return a",
    "def_default": "def g[T](a={e}):\n        return a",
    "def_name": "def LIMIT[T: {e}]():\n        pass",
    "def_body": "def g[T]():\n        return {e}",
    "asyncdef_bound": "async def g[T: {e}]():\n        pass",
    "alias_value": "type A = {e}",
    "alias_bound": "type A[T: {e}] = T",
    "alias_constraints": "type A[T: ({e}, int)] = T",
    "alias_name": "type LIMIT = {e}",
    "alias_params": "type A[**P, *Ts] = {e}",
}
_VARIANTS_695 = (("", ""), ("    LIMIT = 7\n", ""), ("", "    LIMIT = 9\n"),
                 ("    LIMIT = 7\n", "    LIMIT = 9\n"), ("    LIMIT = 7\n", "    del LIMIT\n"))

# The same forms at module scope, each binding G; `{e}` as above. The
# reviewer's case (round 5) is added verbatim.
_ORACLE_MODULE_695 = {
    "class_bound": "class G[T: {e}]:\n    pass\n",
    "class_constraints": "class G[T: ({e}, int)]:\n    pass\n",
    "class_base": "class G[T]((object, {e})[0]):\n    pass\n",
    "class_keyword": "class G[T](metaclass=(type, {e})[0]):\n    pass\n",
    "class_body": "class G[T]:\n    x = {e}\n",
    "def_bound": "def G[T: {e}](a: T = None) -> T:\n    return a\n",
    "def_constraints": "def G[T: ({e}, int)]():\n    pass\n",
    "def_annotation": "def G[T](a: (T, {e})[0] = None) -> (T, {e})[0]:\n    return a\n",
    "def_default": "def G[T](a={e}):\n    return a\n",
    "def_body": "def G[T]():\n    return {e}\n",
    "asyncdef_bound": "async def G[T: {e}]():\n    pass\n",
    "alias_value": "type G = {e}\n",
    "alias_bound": "type G[T: {e}] = T\n",
    "alias_constraints": "type G[T: ({e}, int)] = T\n",
    "alias_params": "type G[**P, *Ts] = {e}\n",
}
_ORACLE_REVIEWER_5 = "class Response[T: LIMIT]: pass\n"      # round 5, M-9, verbatim

# The grammar family: for each class the brief names (definitions, class,
# lambda, the comprehensions, the type alias, the match statement and its
# patterns), a skeleton statement that fills every field the census gives
# that class; `_slots` reads the expression positions from the census and
# one body is made per position, the expression there replaced by LIMIT.
_GRAMMAR_SKELETONS = {
    ("ClassDef", "plain"): ("@(lambda c: c)\nclass K_[T_: int, *Ts_, **P_](NS, metaclass=type):\n"
                            "    x_ = ns.x_\n", "K_"),
    ("FunctionDef", "plain"): ("@(lambda f: f)\ndef K_[T_: int](a_: int = 0, /, b_: int = 0, "
                               "*c_: int, d_: int = 0, **e_: int) -> int:\n    return ns.x_\n",
                               "K_"),
    ("AsyncFunctionDef", "plain"): ("@(lambda f: f)\nasync def K_[T_: int](a_: int = 0, /, "
                                    "b_: int = 0, *c_: int, d_: int = 0, **e_: int) -> int:\n"
                                    "    return ns.x_\n", "K_"),
    ("Lambda", "plain"): ("K_ = (lambda a_=0, /, b_=0, *c_, d_=0, **e_: ns.x_)\n", "K_"),
    ("ListComp", "plain"): ("K_ = [ns.x_ for ns.y_ in (0,) if ns.x_ for z_ in (0,) if ns.x_]\n",
                            "K_"),
    ("SetComp", "plain"): ("K_ = {ns.x_ for ns.y_ in (0,) if ns.x_ for z_ in (0,) if ns.x_}\n",
                           "K_"),
    ("GeneratorExp", "plain"): ("K_ = list(ns.x_ for ns.y_ in (0,) if ns.x_ for z_ in (0,) "
                                "if ns.x_)\n", "K_"),
    ("DictComp", "plain"): ("K_ = {ns.x_: ns.x_ for ns.y_ in (0,) if ns.x_ for z_ in (0,) "
                            "if ns.x_}\n", "K_"),
    ("TypeAlias", "plain"): ("type K_[T_: int, *Ts_, **P_] = ns.x_\n", "K_"),
    ("Match", "sequence"): ("match [1, 2]:\n    case [ns.x_, *s_] if ns.x_:\n"
                            "        K_ = ns.x_\n", "K_"),
    ("Match", "mapping"): ("match {1: 1}:\n    case {ns.x_: ns.x_, **r_}:\n        K_ = ns.x_\n",
                           "K_"),
    ("Match", "class"): ("match ns:\n    case NS(ns.y_, x_=ns.x_):\n        K_ = ns.x_\n", "K_"),
    ("Match", "or_as"): ("match 1:\n    case (ns.x_ | ns.x_) as v_ if ns.x_:\n        K_ = ns.x_\n",
                         "K_"),
}

# A field the grammar admits no read in: the type alias's own name (a Name
# it binds; the parser accepts nothing else there).
_GRAMMAR_UNREADABLE = {("TypeAlias", "name")}


def _slots(node, census, path=()):
    """(path, parent, field, index) of every expression in a read position
    inside `node` (an expression not stored into or deleted), found through
    the census's fields; `path` is the (class, field) pairs from `node` down
    to it."""
    kind = type(node).__name__
    for field, _t, _q in census.get(kind, ()):
        value = getattr(node, field, None)
        items = list(enumerate(value)) if isinstance(value, list) else [(None, value)]
        for i, item in items:
            if not isinstance(item, ast.AST):
                continue
            here = path + ((kind, field),)
            if isinstance(item, ast.expr) \
                    and not isinstance(getattr(item, "ctx", None), (ast.Store, ast.Del)):
                yield here, node, field, i
            yield from _slots(item, census, here)


def _grammar_fields(census):
    """Every (class, field) a read can sit in under the classes the
    skeletons are named for: those classes and every class reachable from
    them through a field of a type other than expr, stmt or a primitive
    (parameters, keywords, type parameters, comprehensions, cases,
    patterns), each field whose type can hold an expression."""
    def holds(t, seen=frozenset()):
        if t in ("expr", "stmt"):
            return True
        if t in _STRING_TYPES or t == "int" or t in seen:
            return False
        return any(holds(ft, seen | {t}) for c in _classes_of(census, t)
                   for _f, ft, _q in census[c])
    classes, todo = set(), sorted({k[0] for k in _GRAMMAR_SKELETONS})
    while todo:
        c = todo.pop()
        if c in classes:
            continue
        classes.add(c)
        for _f, ft, _q in census[c]:
            if ft not in ("expr", "stmt", "int") and ft not in _STRING_TYPES:
                todo.extend(_classes_of(census, ft))
    return {(c, f) for c in classes for f, ft, _q in census[c] if holds(ft)}


def _grammar_family(census):
    """[(label, path, statement, bound name)]: per skeleton, one statement
    per read position (`_slots` of the skeleton's node of its class), the
    expression there replaced by LIMIT (by `LIMIT.x_` where a pattern needs
    a value pattern: a bare name there would be a capture, or refused)."""
    out = []
    for (target, variant), (src, bound) in _GRAMMAR_SKELETONS.items():
        count = None
        k = 0
        while count is None or k < count:
            tree = ast.parse(src)
            node = next(n for n in ast.walk(tree) if type(n).__name__ == target)
            slots = list(_slots(node, census))
            count = len(slots)
            if not slots:
                break
            path, parent, field, i = slots[k]
            new = ast.Name(id="LIMIT", ctx=ast.Load())
            if isinstance(parent, (ast.MatchValue, ast.MatchMapping)):
                new = ast.Attribute(value=new, attr="x_", ctx=ast.Load())
            if i is None:
                setattr(parent, field, new)
            else:
                getattr(parent, field)[i] = new
            out.append(((target, variant, k), path, ast.unparse(ast.fix_missing_locations(tree))
                        + "\n", bound))
            k += 1
    return out


def _indent(stmt):
    return "".join("    " + line + "\n" for line in stmt.rstrip("\n").split("\n"))


def _compiles(src):
    try:
        compile(src, "a", "exec", dont_inherit=True)
    except SyntaxError:
        return False
    return True


def test_f5_the_walk_charges_every_module_read_of_generics_and_the_grammar(tmp_path, capsys):
    """Combat fix pass 5, M-9, the ORACLE grown with the walk. Three
    families, each executed by the interpreter (the module's LIMIT behind
    the recording builtins mapping) and FORCED afterwards (`_force`: every
    lazy bound, constraint and alias value evaluated, every function the
    body made called), the walk's charge compared with the reads:
      * PEP-695 forms in a class body (`_ORACLE_STMTS_695` times every
        sub-expression, five class-binding variants, one deleting the class
        binding after the form so a forced bound reads the module);
      * the same forms at module scope, each binding G, and the reviewer's
        round 5 body verbatim (`class Response[T: LIMIT]: pass`);
      * the GRAMMAR family: a body per expression position of each skeleton
        (`_slots`, read from the census), in a class body (four variants)
        and at module scope; every field the census gives the named classes
        and the classes under them (`_grammar_fields`) lies on the path of
        a body whose execution READ the module's LIMIT, so the family is
        derived from the grammar: a field it does not reach fails here.
    In every body the interpreter compiles, the walk charges a SUPERSET of
    what the interpreter read. A body the interpreter refuses to compile is
    counted, never silently dropped."""
    census = _node_census()
    missed, refused, reads, executed = [], [], 0, 0
    # 1. PEP-695 forms in a class body.
    bodies = []
    for sname, stmt in _ORACLE_STMTS_695.items():
        for xname, e in _ORACLE_SUBS.items():
            for vi, (pre, post) in enumerate(_VARIANTS_695):
                body = pre + "    " + stmt.replace("{e}", e) + "\n    n = LIMIT\n" + post
                if _compiles("class C:\n" + body):
                    bodies.append((("695", sname, xname, vi), body))
                else:
                    refused.append(("695", sname, xname, vi))
    # 3a. The grammar family in a class body.
    grammar = _grammar_family(census)
    grammar_read = set()
    for label, path, stmt, _bound in grammar:
        for vi, (pre, post) in enumerate(_VARIANTS_695[:4]):
            body = pre + _indent(stmt) + "    n = LIMIT\n" + post
            if _compiles("class C:\n" + body):
                bodies.append((("grammar",) + label + (vi,), body, path))
            else:
                refused.append(("grammar",) + label + (vi,))
    src = "LIMIT = 5\n" + _ORACLE_HELPERS_5 + "".join(
        "class C%d:\n%s" % (k, item[1]) for k, item in enumerate(bodies))
    index = _tmp_index(tmp_path, a=src)
    for k, item in enumerate(bodies):
        label, body = item[0], item[1]
        read = "LIMIT" in _interpreter_reads("class C:\n" + body, _LimitValue, _ORACLE_HELPERS_5)
        executed += 1
        reads += read
        if read and len(item) > 2:
            grammar_read.update(item[2])
        if read and "LIMIT" not in index["a"]["C%d" % k][2]:
            missed.append(label)
    # 2 and 3b. Module scope: each body its own module, its binding checked.
    modules = [(("module", s, x), stmt.replace("{e}", e), "G", None)
               for s, stmt in _ORACLE_MODULE_695.items() for x, e in _ORACLE_SUBS.items()]
    modules.append((("module", "reviewer"), _ORACLE_REVIEWER_5, "Response", None))
    modules += [(("grammar-module",) + label, stmt, bound, path)
                for label, path, stmt, bound in grammar]
    reviewer_read = None
    for k, (label, body, bound, path) in enumerate(modules):
        if not _compiles(body):
            refused.append(label)
            continue
        read = "LIMIT" in _interpreter_reads(body, _LimitValue, _ORACLE_HELPERS_5)
        executed += 1
        reads += read
        if path is not None and read:
            grammar_read.update(path)
        if label == ("module", "reviewer"):
            reviewer_read = read
        stem = "m%d" % k
        table = _tmp_index(tmp_path, **{stem: "LIMIT = 5\n" + _ORACLE_HELPERS_5 + body})[stem]
        if read and (bound not in table or "LIMIT" not in table[bound][2]):
            missed.append(label)
    fields = _grammar_fields(census)
    unexercised = sorted(fields - _GRAMMAR_UNREADABLE - grammar_read)
    assert reviewer_read, "the reviewer's body reads the module's LIMIT once its bound is forced"
    assert missed == [], missed[:20]
    assert unexercised == [], unexercised
    assert 0 < reads < executed, (reads, executed)
    with capsys.disabled():
        print("\nPROOF SIZE f5_m9 oracle: %d bodies executed and forced (%d PEP-695 class-body, "
              "%d module-scope, %d grammar positions over %d skeletons, each in a class body "
              "and at module scope), %d read the module's LIMIT, %d refused by the compiler, "
              "%d missed by the walk; %d grammar fields, every one read in some body"
              % (executed, sum(1 for b in bodies if b[0][0] == "695"),
                 len(modules) - len(grammar), len(grammar), len(_GRAMMAR_SKELETONS), reads,
                 len(refused), len(missed), len(fields)))


# The response-model controls for the type-parameter bound (fix pass 5,
# d): a module edit under a bound moves the fingerprint of every binding
# whose bound may read it.
_GENERIC_SRC = (
    "from pydantic import BaseModel\n"
    "LIMIT = int\n"
    "class Response[T: LIMIT]: pass\n"
    "class Model(BaseModel):\n"
    "    class Inner[T: LIMIT]:\n"
    "        pass\n"
    "def handler[T: LIMIT](x: T) -> T:\n"
    "    return x\n"
    "type Alias[T: LIMIT] = list[T]\n"
    "type Plain = LIMIT\n"
    "class Late(BaseModel):\n"
    "    class Inner[T: LIMIT]:\n"
    "        pass\n"
    "    LIMIT = str\n"
    "class Deleted(BaseModel):\n"
    "    LIMIT = str\n"
    "    class Inner[T: LIMIT]:\n"
    "        pass\n"
    "    del LIMIT\n"
    "def outer():\n"
    "    LIMIT = str\n"
    "    def inner[T: LIMIT]():\n"
    "        pass\n"
    "    return inner\n")


def test_f5_a_module_edit_under_a_type_parameter_bound_moves_the_fingerprint(tmp_path):
    """Combat fix pass 5, M-9 (d). The reviewer's generic response model,
    a generic class inside a model, a generic handler, two type aliases: an
    edit to the module's LIMIT moves each one's closure text. `Late` binds
    LIMIT after its generic, so its lazily evaluated bound reads the class's
    value: the walk charges the module there too, deliberately (a read
    through an annotation scope is never certain). `Deleted` deletes its
    binding, so the bound reads the module. Inside a function the bound
    reads the function's own LIMIT and the module is not charged. The same
    source run by the interpreter, before and after the edit, agrees."""
    index = _tmp_index(tmp_path, a=_GENERIC_SRC)
    moved = _with_segment(index, "a", "LIMIT", "LIMIT = float\n")
    for name in ("Response", "Model", "handler", "Alias", "Plain", "Late", "Deleted"):
        reached = set(_walk_bindings([("a", name)], index=index))
        assert ("a", "LIMIT") in reached, (name, sorted(reached))
        after = _closure_text(moved, set(_walk_bindings([("a", name)], index=moved)))
        assert after != _closure_text(index, reached), name
    assert "LIMIT" not in index["a"]["outer"][2], sorted(index["a"]["outer"][2])

    def run(src):
        ns = {}
        exec(compile(src.replace("from pydantic import BaseModel\n", "BaseModel = object\n"),
                     "a", "exec", dont_inherit=True), ns)
        return ns
    for value, src in ((int, _GENERIC_SRC),
                       (float, _GENERIC_SRC.replace("LIMIT = int\n", "LIMIT = float\n", 1))):
        ns = run(src)
        assert ns["Response"].__type_params__[0].__bound__ is value
        assert ns["Model"].Inner.__type_params__[0].__bound__ is value
        assert ns["handler"].__type_params__[0].__bound__ is value
        assert ns["Alias"].__type_params__[0].__bound__ is value
        assert ns["Plain"].__value__ is value
        assert ns["Late"].Inner.__type_params__[0].__bound__ is str
        assert ns["Deleted"].Inner.__type_params__[0].__bound__ is value
        assert ns["outer"]().__type_params__[0].__bound__ is str


def test_f5_a_module_level_statement_of_any_type_binds_what_it_binds(tmp_path):
    """Combat fix pass 5, M-9: the module index's default. A `type` alias,
    an augmented assignment, a loop target, a `with` target, a walrus, a
    match capture and a store into an object's item are bindings carrying
    their whole statement, so an edit to any of them moves the routes that
    read the name; a call that binds nothing is no binding."""
    index = _tmp_index(tmp_path, a=(
        "LIMIT = 5\n"
        "TABLE = {}\n"
        "type Alias = LIMIT\n"
        "LIMIT += 1\n"
        "for LOOPED in (LIMIT,):\n"
        "    pass\n"
        "with open(__file__) as HANDLE:\n"
        "    pass\n"
        "(WALRUS := LIMIT)\n"
        "match LIMIT:\n"
        "    case CAPTURED:\n"
        "        pass\n"
        "TABLE['k'] += LIMIT\n"
        "print(LIMIT)\n"
        "def route():\n"
        "    return Alias, LIMIT, LOOPED, HANDLE, WALRUS, CAPTURED, TABLE\n"))
    table = index["a"]
    for name in ("Alias", "LOOPED", "HANDLE", "WALRUS", "CAPTURED"):
        assert table[name][0] == "data" and "LIMIT" in table[name][2] or name == "HANDLE", name
    assert "LIMIT += 1" in table["LIMIT"][1] and "TABLE['k'] += LIMIT" in table["TABLE"][1]
    assert "print" not in table
    reached = set(_walk_bindings([("a", "route")], index=index))
    for name in ("Alias", "LIMIT", "LOOPED", "HANDLE", "WALRUS", "CAPTURED", "TABLE"):
        assert ("a", name) in reached, (name, sorted(reached))
    moved = _with_segment(index, "a", "Alias", "type Alias = str\n")
    assert _closure_text(moved, reached) != _closure_text(index, reached)


_TYPE_PARAM_SRC = (
    "LIMIT = int\n"
    "def handler[LIMIT](x: LIMIT) -> LIMIT:\n"
    "    return x\n"
    "class Box[LIMIT](list[LIMIT]):\n"
    "    pass\n"
    "type Alias[LIMIT] = list[LIMIT]\n")


def test_f5_a_type_parameter_is_local_to_its_annotation_scope(tmp_path):
    """Combat fix pass 5, M-9: a generic definition's type parameters bind
    in its annotation scope, not where the definition stands. A type
    parameter named like a module binding (here LIMIT) is read from that
    scope by its annotations, bases and alias value, and a module-level
    generic charges no module binding of that name. The interpreter agrees:
    executing and forcing the source reads no module LIMIT. (Inside a class
    body the fix pass 3 bound still touches a nested definition's type
    parameter names conservatively: an over-charge, never a missed read.)"""
    index = _tmp_index(tmp_path, a=_TYPE_PARAM_SRC)
    for name in ("handler", "Box", "Alias"):
        assert "LIMIT" not in index["a"][name][2], (name, sorted(index["a"][name][2]))
        assert ("a", "LIMIT") not in set(_walk_bindings([("a", name)], index=index)), name
    assert "LIMIT" not in _interpreter_reads(_TYPE_PARAM_SRC.split("\n", 1)[1])
