"""A pytest plugin (`-p ro_spy`) that records, while the a1 and gate walks
run, every SQL position closed_walk's S analysis classifies: each call of
closed_walk.Bindings.execute_kind, with the walked function's module file,
the call's line in that file, the innermost enclosing function, and the kind
S returned ('read', 'lock', 'write') or the exception it raised.

The position's line is found by its AST, never by a name: the call node's
dump is looked up among the Call nodes of its module's parsed source; when
the dump occurs more than once, the walked function's own definition (equal
by dump) gives the line offset. A position that resolves to no line or to
more than one is recorded with line None and status 'ambiguous'; a call
of a planted or synthetic program (its walked definition in no definition
of the module) has status 'synthetic'.

Used by test_r8_ro_covered_pg (the enumeration of the covered set,
ruling REHEARSAL-FOUR-R7-A1 M1). Output: JSON at $RO_SPY_OUT.
"""

import ast
import inspect
import json
import os

import closed_walk as _cw

RECORDS = []
_TREES = {}
_STATE = {"test": None}


def _tree(mod):
    key = id(mod)
    if key not in _TREES:
        try:
            _TREES[key] = (mod, ast.parse(inspect.getsource(mod)))
        except (OSError, TypeError):
            _TREES[key] = (mod, None)
    return _TREES[key][1]


_ORIG_INIT = _cw.Bindings.__init__
_ORIG_KIND = _cw.Bindings.execute_kind


def _init(self, scope, fn=None, *args, **kwargs):
    _ORIG_INIT(self, scope, fn, *args, **kwargs)
    self._ro_spy_fn = fn


def _defs(tree, fn):
    return [d for d in ast.walk(tree)
            if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))
            and d.name == fn.name and ast.dump(d) == ast.dump(fn)]


def _locate(bindings, call):
    """(path, line, end_line, span, status): status 'real' when the call is
    one node of its module's source (the walked definition, when there is
    one, equal by dump to exactly one definition of the module); 'synthetic'
    when the walked definition, or the call, is in no definition of the
    module (a planted or synthetic program); 'ambiguous' otherwise."""
    mod = bindings.scope
    path = getattr(mod, "__file__", None) or getattr(mod, "__name__", "?")
    tree = _tree(mod)
    if tree is None:
        return path, None, None, None, "synthetic"
    want = ast.dump(call)
    hits = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and ast.dump(n) == want]
    fn = getattr(bindings, "_ro_spy_fn", None)
    if fn is not None:
        defs = _defs(tree, fn)
        if not defs:
            return path, None, None, None, "synthetic"
        if len(defs) > 1:
            return path, None, None, None, "ambiguous"
        off = defs[0].lineno - fn.lineno
        hits = [h for h in hits if h.lineno == call.lineno + off]
    if not hits:
        return path, None, None, None, "synthetic"
    if len(hits) != 1:
        return path, None, None, None, "ambiguous"
    line, end = hits[0].lineno, hits[0].end_lineno
    best = None
    for d in ast.walk(tree):
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                d.lineno <= line <= d.end_lineno):
            if best is None or d.lineno > best.lineno:
                best = d
    return path, line, end, (best.name if best is not None else None), "real"


def _kind(self, call, lists, *args, **kwargs):
    path, line, end, span, status = _locate(self, call)
    rec = {"test": _STATE["test"], "path": os.path.abspath(path) if line else path,
           "line": line, "end": end, "span": span, "status": status}
    try:
        kind = _ORIG_KIND(self, call, lists, *args, **kwargs)
    except Exception as e:
        rec["kind"] = "raised " + type(e).__name__
        RECORDS.append(rec)
        raise
    rec["kind"] = kind
    RECORDS.append(rec)
    return kind


_cw.Bindings.__init__ = _init
_cw.Bindings.execute_kind = _kind


def pytest_runtest_setup(item):
    _STATE["test"] = item.nodeid


def pytest_sessionfinish(session, exitstatus):
    out = os.environ.get("RO_SPY_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"exitstatus": int(exitstatus), "records": RECORDS}, fh)
