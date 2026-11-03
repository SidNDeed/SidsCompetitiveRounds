"""A pytest plugin (`-p ro_spy`) that records, while the a1 and gate walks
run, every execute position the walks ask closed_walk's frozen lookup
about (round 8, M1: the static S analysis is retired): each call of
closed_walk.Bindings.execute_kind, with the position the lookup itself
places the call at (closed_walk._position: the walked function's module
file, the call's line and end line), the innermost enclosing function of
that module, the answer the table the walk passed holds for the position
('write' when absent), and the kind the lookup returned ('read', 'lock' or
'write') or the exception it raised.

A call the lookup cannot place is recorded with line None: status
'synthetic' when the walked definition is in no definition of its module
(a planted or synthetic program), 'ambiguous' otherwise (a real definition
whose call the lookup cannot place uniquely).

Used by test_r8_ro_covered_pg (the enumeration of the visited set,
ruling REHEARSAL-FOUR-R7-A1 M1). Output: JSON at $RO_SPY_OUT.
"""

import json
import os

import closed_walk as _cw

RECORDS = []
_STATE = {"test": None}
_ORIG_KIND = _cw.Bindings.execute_kind


def _status(bindings):
    """'ambiguous' when the walked definition is exactly one definition of
    its module (so the call is real code the lookup could not place),
    'synthetic' otherwise."""
    tree = _cw._module_tree(bindings.scope)
    d = getattr(bindings, "where", None)
    if tree is None or d is None:
        return "synthetic"
    top = [x for x in _cw._defs(tree) if _cw._named_as(x, d) and _cw._same(x, d)]
    return "ambiguous" if len(top) == 1 else "synthetic"


def _span(bindings, line):
    """The innermost definition of the module enclosing `line`."""
    best = None
    for d in _cw._defs(_cw._module_tree(bindings.scope)):
        if d.lineno <= line <= d.end_lineno and (best is None or d.lineno > best.lineno):
            best = d
    return best.name if best is not None else None


def _kind(self, call, reads, *args, **kwargs):
    pos = _cw._position(self, call)
    mod = self.scope
    path = getattr(mod, "__file__", None) or getattr(mod, "__name__", "?")
    rec = {"test": _STATE["test"], "path": os.path.abspath(path) if pos else path,
           "line": pos[1] if pos else None, "end": pos[2] if pos else None,
           "span": _span(self, pos[1]) if pos else None,
           "status": "real" if pos else _status(self),
           "table_kind": reads.get(pos, "write") if pos is not None else "write"}
    try:
        kind = _ORIG_KIND(self, call, reads, *args, **kwargs)
    except Exception as e:
        rec["kind"] = "raised " + type(e).__name__
        RECORDS.append(rec)
        raise
    rec["kind"] = kind
    RECORDS.append(rec)
    return kind


def pytest_runtest_setup(item):
    _STATE["test"] = item.nodeid


def pytest_sessionfinish(session, exitstatus):
    out = os.environ.get("RO_SPY_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"exitstatus": int(exitstatus), "records": RECORDS}, fh)


_cw.Bindings.execute_kind = _kind
