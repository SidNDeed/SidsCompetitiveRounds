"""The one child process of the ban census's VALUE form (RULING-CENSUS-5 section 4, RULING-CENSUS-6).

usage: python -I ban_sweep_values_child.py <api dir> <requests.json> <out.json> [<main text file>]

It imports the read modules (no database) and evaluates each request in its module: a module-level name, a
constant-key subscript of one, or a call of a module-level function with constant arguments that the
resolver found closed (a call that is not closed is never evaluated). For each answer it writes the value
when it is a str, or a tuple, list or set of str, and otherwise its type (a module also names itself), which
is how a module-level receiver of a str or pattern method is confirmed by type. An import that fails is a
failure of every request of that module, never a skip. With a main text file, main is that text (a mutant)
compiled into a module registered as `main` before anything imports it. The request "__sitting__" lists
review_measures' registry for the judged sitting place (J11): each sitting operator's name, and every part of
every entry of the kinds side, row, reporter and population, with POP_BASE, DAY, SCOPE_DIRTY and
SCOPE_DAYS_BACK."""
import importlib
import json
import re
import sys
import types


def _main_from_text(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    mod = types.ModuleType("main")
    mod.__file__ = path
    sys.modules["main"] = mod
    exec(compile(text, "main.py", "exec"), mod.__dict__)  # noqa: S102 - the test's own mutant of main
    return mod


def _registry_columns():
    """RULING-CENSUS-9 3 (d): every string c.format(s=s) over each REPORT_REGISTRY entry's decl.column and both
    seats; MATCH_COLUMNS; the strings outside MATCH_COLUMNS; the names of MATCH_COLUMNS that do not stand as
    m.<name> (a whole word) in SEAT_BASELINE_SQL."""
    ae = importlib.import_module("admin_evidence")
    strs = set()
    for e in ae.REPORT_REGISTRY:
        col = e.decl.column
        for c in (col if isinstance(col, tuple) else (col,)):
            for s in ae.AER_SEATS:
                strs.add(c.format(s=s))
    cols = list(ae.MATCH_COLUMNS)
    seat = ae.SEAT_BASELINE_SQL
    return {"registry": sorted(strs), "match_columns": cols,
            "not_in_match_columns": sorted(strs - set(cols)),
            "not_in_seat_baseline": [n for n in cols if not re.search(
                r"(?<![A-Za-z0-9_])m\." + re.escape(n) + r"(?![A-Za-z0-9_])", seat)]}


def _sitting():
    rm = importlib.import_module("review_measures")
    out = {"operators": [], "parts": {}, "constants": {}}
    for name, entry in sorted(rm.REGISTRY.items(), key=lambda kv: str(kv[0])):
        kind = getattr(entry, "kind", None)
        if kind == "sitting":
            out["operators"].append([entry.name, entry.impl[0].__name__])
        elif kind in ("side", "row", "reporter", "population"):
            out["parts"][entry.name] = [kind, [str(x) for x in (entry.data or [])]]
    for c in ("POP_BASE", "DAY", "SCOPE_DIRTY", "SCOPE_DAYS_BACK"):
        out["constants"][c] = getattr(rm, c)
    return out


def main():
    api, req_path, out_path = sys.argv[1:4]
    sys.path.insert(0, api)
    mods = {}
    if len(sys.argv) > 4 and sys.argv[4]:
        try:
            mods["main"] = _main_from_text(sys.argv[4])
        except BaseException as ex:  # noqa: BLE001
            mods["main"] = ex
    with open(req_path, encoding="utf-8") as fh:
        req = json.load(fh)
    out = {}
    for key, (m, src, closed) in sorted(req.items()):
        if key == "__registry_columns__":
            try:
                out[key] = {"type": "registry_columns", "value": _registry_columns()}
            except BaseException as ex:  # noqa: BLE001
                out[key] = {"error": "%s: %s" % (type(ex).__name__, str(ex)[:200]), "value": None}
            continue
        if key == "__sitting__":
            try:
                out[key] = {"type": "sitting", "value": _sitting()}
            except BaseException as ex:  # noqa: BLE001
                out[key] = {"error": "%s: %s" % (type(ex).__name__, str(ex)[:200]), "value": None}
            continue
        if m not in mods:
            try:
                mods[m] = importlib.import_module(m)
            except BaseException as ex:  # noqa: BLE001
                mods[m] = ex
        mo = mods[m]
        if isinstance(mo, BaseException):
            out[key] = {"error": "import failed: %s: %s" % (type(mo).__name__, str(mo)[:200]), "value": None}
            continue
        if "(" in src.split("[")[0] and not closed:
            out[key] = {"error": "a call that is not closed is not evaluated", "value": None}
            continue
        try:
            v = eval(src, vars(mo))  # noqa: S307 - a name, a constant-key subscript or a closed call
        except BaseException as ex:  # noqa: BLE001
            out[key] = {"error": "%s: %s" % (type(ex).__name__, str(ex)[:200]), "value": None}
            continue
        if isinstance(v, str):
            out[key] = {"type": "str", "value": v}
        elif isinstance(v, (tuple, list)) and all(isinstance(s, str) for s in v):
            out[key] = {"type": type(v).__name__, "value": list(v)}
        elif isinstance(v, (set, frozenset)) and all(isinstance(s, str) for s in v):
            out[key] = {"type": type(v).__name__, "value": sorted(v)}
        elif isinstance(v, types.ModuleType):
            out[key] = {"type": "module", "module": v.__name__, "value": None}
        else:
            out[key] = {"type": type(v).__name__, "value": None}
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
