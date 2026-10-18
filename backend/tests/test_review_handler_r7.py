"""Fix pass 7 (build round 7, M5) for the os.walk handler proof of the
path-query enumeration (test_review_needles_r3.walk_handler_proven), against
planted fixtures only.

The proof must never credit an os.walk whose refusal an except clause or a
with statement can swallow. Exception and suppression names are resolved
through their aliases at the use site (assignment aliases, import aliases,
attribute aliases, re-exports), and every catcher or suppressor the proof
cannot resolve is treated as catching, so the walk is reported:
  * REPORTED: an assigned-alias catcher, an import-alias catcher, an
    attribute-alias catcher, a chained alias, a re-exported catcher, a
    catcher bound as a parameter, an imported-alias suppressor, an
    assigned-alias suppressor, a re-exported suppressor, a builtin rebound
    through the module namespace or the builtins module, and a module that
    rebinds Exception (NoVerdict's base must be the builtin): each makes the
    proof report os.walk (at 0aa13872 the proof credited each of them);
  * PROVEN: the selftest fixture r3.WALK_OK, literal builtins that cannot
    catch the refusal (one, and a tuple), an alias that resolves to one, a
    literal NoVerdict clause that re-raises, and a literal with open(...) (a
    manager known never to suppress): each is still credited.
Every planted shape is compiled first: it is real Python.

Fix pass 9 (build round 8, M5): a manager known never to suppress is trusted
by its name, so an operation of the module that could rebind such a manager,
a prefix of its dotted path, an alias of either, or the manager itself
refuses the proof (r3._manager_rebinds), and the os.walk row of the report
names each such operation by file, line and kind (r3.Reported.rebinds):
  * REBOUND, the six controls: (a) the round 8 report's scenario verbatim,
    (b) a prefix rebound by an import, (c) the manager's name rebound by an
    import inside the function that holds the walk, (d) an alias chain
    rebound, (e) setattr on the module with a computed name: each reports
    os.walk naming its rebinding line; (f) a benign alias read once and
    used unchanged is still trusted and the walk still proven;
  * REBOUND_MORE: every other operation the requirement lists (a deletion,
    an augmented store, a prefix assignment, a global declaration with its
    store, delattr, vars, globals, __dict__, sys.modules, the manager's own
    __exit__, the module handed to code the proof cannot see, a reflective
    getattr, a store through a prefix alias, a module reached by importlib,
    a star import, a loop target, a parameter): each reports os.walk naming
    its line and kind;
  * the path-query alias map keeps every binding's value, so a name bound to
    two values (control d's shape) is judged under each (at 47669b66 the
    enumeration raised NoFixedPoint on it before judging the walk).

Fix pass 10 (build round 9, M5): a list of rebinding forms was refuted by a
form outside it (a write through a function's __globals__ mapping), so the
proof is BOUNDED by namespace reach (r3._namespace_reach): it is refused, and
the walk reported naming the line, whenever the module holds a write through
a namespace-reaching expression or name or through a base it cannot resolve,
a call of a namespace-reaching callable, an import of a namespace-reaching
module, or a namespace-reaching value leaving its sight. The bound covers the
stated lists, not every conceivable rebinding:
  * REBOUND10, controls a to i (the round 9 report's scenario verbatim, the
    aliased mapping with a container-element variant, vars of the module in
    sys.modules, a string-built getattr name, exec, unittest.mock.patch and
    monkeypatch.setattr, the module dict through sys.modules, importlib,
    types.FunctionType replacing the walk's function): each reports os.walk
    naming its rebinding line and kind;
  * j, a benign module (its own local dict written by subscript, a literal
    plain getattr, the manager used unchanged): still trusted, walk proven;
  * k, the real review modules: each keeps its round 9 verdict by the same
    test, and the real-module rule's measured unresolved-base counts hold.

Fix pass 11 (build round 10, M5): the unresolved-base half of the bound took
every result of a module-local call as fresh, so a local identity function
carried a caller-supplied mapping through unseen; and an in-process string
executor (timeit) was outside the call list. Data now flows through local
calls (r3._Flow), mutator methods on an unresolved receiver are refused like
a store through it, and the executors join the call list and the import rule:
  * REBOUND11, controls a to j (the round 10 report's scenario verbatim, two
    local hops, a conditional return, a container passthrough, a default
    argument, *args and **kwargs forwarding, the mutator methods directly and
    through partial and methodcaller, ChainMap and SimpleNamespace over the
    mapping, timeit, and the other executors): each reports os.walk naming
    the refused line and operation;
  * FORMS11, every other callable form and return path the requirement
    lists (a class instance holding its argument, a lambda binding, a nested
    function, a decorated function, a walrus, an augmented binding, a list,
    a yield from, exec in the body, a call of an unresolved callable, a try
    that swallows and rebinds): each reports the walk naming its line;
  * k, a benign module (a local copy, a local constant, a fresh object built
    from the values, timeit on literal code that binds nothing): still
    trusted, the walk still proven;
  * l, the real review modules: each keeps its round 10 verdict by the same
    test, and the newly unresolved sites are exactly the measured ones.

Fix pass 12 (build round 11, M5): a slice of an unresolved value was taken as
a fresh holder, a module-local callable consumed by map was not followed, and
an augmented assignment to a plain name was only a binding. Element
provenance now survives slices, copies and iteration, callbacks are marked as
if called directly, and every in-place operator on an unresolved receiver is
refused like a store through it:
  * REBOUND12, controls a to e (the round 11 report's scenario verbatim, the
    slice aliases, unpacking and iteration, the higher-order forms, the
    in-place forms): each reports os.walk naming the refused line and
    operation; INPLACE12 runs every augmented operator, its dunder method and
    its operator function;
  * f, a benign module (augmented assignments on copies and fresh values, a
    rebinding, map over a builtin, slices and sorts of fresh lists): still
    trusted, the walk still proven;
  * g, the real review modules: each keeps its round 11 verdict by the same
    test, and the newly unresolved sites are exactly the measured ones.

Fix pass 13 (build round 12, M5): an operator delivered by a loop, a with
target or another binding form was not followed, iter and reversed over an
unresolved value were taken as holders, and a collection mutator off the
fix 11 list on an unresolved receiver was trusted. Every binding form is now
dispatched through one table (r3._BINDING_TABLE, a node outside it refused
by name), calls fail closed (r3._PROVEN_FRESH, r3._ARG_SAFE, an unresolved
callable refused over a marked argument or when itself unresolved), methods
on an unresolved receiver fail closed (r3._PURE_METHODS), and a constant
index into a display selects its own element:
  * REBOUND13, controls a to f (the round 12 report's loop-delivered operator
    verbatim and every other delivering binding form, the identity-preserving
    calls, the collection mutators, the extracted bound methods, the
    fail-closed method gate, the refused constant and non-constant indexes):
    each reports os.walk naming the refused line and operation;
  * the binding table holds every ast class with a binding field, and a node
    outside it (a synthetic class, or the table narrowed) refuses the walk
    naming its line (e);
  * f, the trusted constant-index selections; g, a benign module (every fix
    12 item, iteration, local lists, a dict copy, the pure methods): still
    trusted, the walk still proven;
  * h, the real review modules: each keeps its round 12 verdict by the same
    test, every unresolved site is named per module (REAL: the row the proof
    prints and its enclosing function or class, never a line or a total) and
    review_needles.py's new sites are exactly the measured ones.

Fix pass 14 (build round 13, M5, LOW 1, LOW 2): a write through an imported
namespace object (the report's from os import __dict__ as ns), a name-only get
on an unresolved receiver and a protocol-running allowlisted call over an
untyped value were trusted; a same-name binding in another scope was merged
into the receiver proof; and bytes(b) over an exact bytes b was called fresh.
Stores and mutators through imported objects and imported objects handed to
unlisted code are refused, a pure method name is admitted only on a proven
builtin receiver, a builtin or library call over an argument the proof cannot
type is refused (a type guard of the parameter, a literal or a proven builtin
container admits it), names are read by Python's scopes, and an identity
alias is _IMMUT, never fresh:
  * REBOUND14, a to h (the report's input verbatim, a dynamic member through
    an import alias, stores through imported objects, an imported object
    handed to unlisted code, a mutator through an imported object, the
    name-only get, protocol-running calls and callbacks, a type guard of a
    module class): each reports os.walk naming its line (each admitted at
    a2b5151c);
  * b, the control: a guarded parameter, a local dict's pure methods and an
    argument stored by append: still trusted, the walk still proven;
  * c, the _revision shape trusted with no exemption, the same-scope binding
    and the free name still refused; d, the identity aliases, the operator
    and the mutable alias, and the fix 13 fresh results;
  * the benign controls k (fix 11), f (fix 12), g and the loop of e (fix 13)
    keep their shapes over values the proof can type (each deviation is
    named where it is made), the selftest fixture r3.WALK_OK guards its
    parameter's type, and REAL is re-measured by site identity."""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import test_review_needles_r3 as r3  # noqa: E402

SCAN = "    return list(os.walk(p, onerror=_walk_error))\n"
CATCH = "    try:\n        return list(os.walk(p, onerror=_walk_error))\n    except %s:\n        return []\n"
SUPPRESS = "    with %s(Exception):\n        return list(os.walk(p, onerror=_walk_error))\n"


def _plant(header="", scan=None, edits=()):
    """r3.WALK_OK with `header` after its import, its scan body replaced by
    `scan`, and each (old, new) edit applied; each text it replaces occurs
    exactly once."""
    src = r3.WALK_OK
    if header:
        assert src.count("import os\n") == 1
        src = src.replace("import os\n", "import os\n" + header)
    if scan is not None:
        assert src.count(SCAN) == 1
        src = src.replace(SCAN, scan)
    for old, new in edits:
        assert src.count(old) == 1, old
        src = src.replace(old, new)
    compile(src, "planted", "exec")
    return src


REPORTED = [
    ("assigned_alias_catcher", dict(header="Caught = Exception\n", scan=CATCH % "Caught")),
    ("import_alias_catcher", dict(header="from builtins import Exception as Caught\n", scan=CATCH % "Caught")),
    ("attribute_alias_catcher", dict(header="import builtins\nCaught = builtins.BaseException\n",
                                     scan=CATCH % "Caught")),
    ("chained_alias_catcher", dict(header="Base = Exception\nCaught = Base\n", scan=CATCH % "Caught")),
    ("re_exported_catcher", dict(header="from review_errors import Caught\n", scan=CATCH % "Caught")),
    ("parameter_catcher", dict(scan=CATCH % "Caught", edits=[("def scan(p):", "def scan(p, Caught=Exception):")])),
    ("imported_alias_suppressor", dict(header="from contextlib import suppress as quiet\n",
                                       scan=SUPPRESS % "quiet")),
    ("assigned_alias_suppressor", dict(header="import contextlib\nquiet = contextlib.suppress\n",
                                       scan=SUPPRESS % "quiet")),
    ("re_exported_suppressor", dict(header="from review_tools import quiet\n", scan=SUPPRESS % "quiet")),
    ("builtin_rebound_through_globals", dict(header="globals()['KeyError'] = Exception\n",
                                             scan=CATCH % "KeyError")),
    ("builtin_rebound_on_the_builtins_module", dict(header="import builtins\nbuiltins.KeyError = Exception\n",
                                                    scan=CATCH % "KeyError")),
    ("exception_rebound", dict(header="Exception = ValueError\n")),
]


@pytest.mark.parametrize("name,shape", REPORTED, ids=[r[0] for r in REPORTED])
def test_m5_fix7_an_aliased_or_unresolvable_catcher_or_suppressor_reports_the_walk(name, shape):
    assert [k for _l, k in r3.unwrapped_queries(_plant(**shape))] == ["os.walk"], name


PROVEN = [
    ("selftest_fixture", dict()),
    ("literal_builtin_that_cannot_catch", dict(scan=CATCH % "ValueError")),
    ("literal_tuple_that_cannot_catch", dict(scan=CATCH % "(ValueError, KeyError)")),
    ("alias_resolving_to_a_builtin_that_cannot_catch", dict(header="Missing = KeyError\n",
                                                            scan=CATCH % "Missing")),
    ("literal_noverdict_clause_that_re_raises",
     dict(scan="    try:\n        return list(os.walk(p, onerror=_walk_error))\n    except NoVerdict:\n"
               "        raise\n")),
    ("literal_manager_that_never_suppresses", dict(scan="    with open(p) as f:\n        f.read()\n" + SCAN)),
]


@pytest.mark.parametrize("name,shape", PROVEN, ids=[p[0] for p in PROVEN])
def test_m5_fix7_literal_and_resolved_spellings_that_cannot_swallow_still_prove(name, shape):
    assert r3.unwrapped_queries(_plant(**shape)) == [], name


# -- fix pass 9: a rebound never-suppress manager ---------------------------------------
TD_WALK = SUPPRESS % "tempfile.TemporaryDirectory"


def _line(src, text):
    """The 1-based number of the one line of src that is `text`."""
    lines = src.split("\n")
    assert lines.count(text) == 1, text
    return lines.index(text) + 1


def _named(name, shape, expect):
    """The planted module reports exactly one os.walk, and its row names each
    expected (line text, kind) as (file, line number, kind)."""
    src = _plant(**shape)
    rows = r3.unwrapped_queries(src, "planted")
    assert [k for _l, k in rows] == ["os.walk"], (name, rows)
    for text, kind in expect:
        assert ("planted", _line(src, text), kind) in rows[0].rebinds, (name, text, kind, rows)


REBOUND = [
    ("a_report_scenario_verbatim",
     dict(header="import contextlib\nimport tempfile\ntempfile.TemporaryDirectory = contextlib.suppress\n",
          scan=TD_WALK),
     [("tempfile.TemporaryDirectory = contextlib.suppress", "attribute store rebinds tempfile.TemporaryDirectory")]),
    ("b_prefix_rebound_by_import",
     dict(header="import tempfile\nimport contextlib as tempfile\n", scan=TD_WALK),
     [("import contextlib as tempfile", "import rebinds tempfile")]),
    ("c_name_rebound_by_import_in_the_walks_function",
     dict(header="from tempfile import TemporaryDirectory\n",
          scan="    from contextlib import suppress as TemporaryDirectory\n" + SUPPRESS % "TemporaryDirectory"),
     [("    from contextlib import suppress as TemporaryDirectory", "import rebinds TemporaryDirectory")]),
    ("d_alias_chain_rebound",
     dict(header="import contextlib\nimport tempfile\nTD = tempfile.TemporaryDirectory\nTD = contextlib.suppress\n",
          scan=SUPPRESS % "TD"),
     [("TD = contextlib.suppress", "assignment rebinds TD")]),
    ("e_setattr_with_a_computed_name",
     dict(header="import contextlib\nimport tempfile\nname = 'Temporary' + 'Directory'\n"
                 "setattr(tempfile, name, contextlib.suppress)\n", scan=TD_WALK),
     [("setattr(tempfile, name, contextlib.suppress)", "namespace operation setattr")]),
]


@pytest.mark.parametrize("name,shape,expect", REBOUND, ids=[r[0] for r in REBOUND])
def test_m5_fix9_a_rebound_never_suppress_manager_reports_the_walk_naming_the_line(name, shape, expect):
    _named(name, shape, expect)


def test_m5_fix9_f_a_benign_alias_read_once_and_used_unchanged_is_still_trusted():
    src = _plant(header="import tempfile\nTD = tempfile.TemporaryDirectory\n",
                 scan="    with TD():\n        return list(os.walk(p, onerror=_walk_error))\n")
    assert r3.unwrapped_queries(src, "planted") == []


EXIT_WALK = "    with tempfile.TemporaryDirectory():\n        return list(os.walk(p, onerror=_walk_error))\n"
REBOUND_MORE = [
    ("deletion_of_the_dotted_name", dict(header="import tempfile\ndel tempfile.TemporaryDirectory\n", scan=TD_WALK),
     [("del tempfile.TemporaryDirectory", "attribute deletion rebinds tempfile.TemporaryDirectory")]),
    ("augmented_store_of_the_dotted_name",
     dict(header="import contextlib\nimport tempfile\ntempfile.TemporaryDirectory |= contextlib.suppress\n",
          scan=TD_WALK),
     [("tempfile.TemporaryDirectory |= contextlib.suppress",
       "augmented attribute store rebinds tempfile.TemporaryDirectory")]),
    ("prefix_assignment", dict(header="import contextlib\nimport tempfile\ntempfile = contextlib\n", scan=TD_WALK),
     [("tempfile = contextlib", "assignment rebinds tempfile")]),
    ("global_declaration_then_store",
     dict(header="import contextlib\nimport tempfile\n\n\ndef _patch():\n    global tempfile\n"
                 "    tempfile = contextlib\n", scan=TD_WALK),
     [("    global tempfile", "global declaration rebinds tempfile"),
      ("    tempfile = contextlib", "assignment rebinds tempfile")]),
    ("delattr_on_the_module", dict(header="import tempfile\ndelattr(tempfile, 'TemporaryDirectory')\n", scan=TD_WALK),
     [("delattr(tempfile, 'TemporaryDirectory')", "namespace operation delattr")]),
    ("vars_write", dict(header="import contextlib\nimport tempfile\n"
                               "vars(tempfile)['TemporaryDirectory'] = contextlib.suppress\n", scan=TD_WALK),
     [("vars(tempfile)['TemporaryDirectory'] = contextlib.suppress", "namespace operation vars")]),
    ("globals_write", dict(header="import contextlib\nimport tempfile\nglobals()['tempfile'] = contextlib\n",
                           scan=TD_WALK),
     [("globals()['tempfile'] = contextlib", "namespace operation globals")]),
    ("module_dict_write", dict(header="import contextlib\nimport tempfile\n"
                                      "tempfile.__dict__['TemporaryDirectory'] = contextlib.suppress\n",
                               scan=TD_WALK),
     [("tempfile.__dict__['TemporaryDirectory'] = contextlib.suppress", "namespace operation __dict__")]),
    ("sys_modules_write", dict(header="import contextlib\nimport sys\nsys.modules['tempfile'] = contextlib\n",
                               scan="    import tempfile\n" + TD_WALK),
     [("sys.modules['tempfile'] = contextlib", "namespace operation modules")]),
    ("the_managers_exit_patched",
     dict(header="import tempfile\ntempfile.TemporaryDirectory.__exit__ = lambda *a: True\n", scan=EXIT_WALK),
     [("tempfile.TemporaryDirectory.__exit__ = lambda *a: True",
       "attribute store rebinds tempfile.TemporaryDirectory.__exit__")]),
    ("module_handed_to_unseen_code",
     dict(header="import tempfile\nimport review_patch\nreview_patch.install(tempfile)\n", scan=EXIT_WALK),
     [("review_patch.install(tempfile)", "tempfile escapes as a value")]),
    ("reflective_getattr",
     dict(header="import contextlib\nimport tempfile\n"
                 "getattr(tempfile, '__dict__')['TemporaryDirectory'] = contextlib.suppress\n", scan=TD_WALK),
     [("getattr(tempfile, '__dict__')['TemporaryDirectory'] = contextlib.suppress",
       "getattr with a computed or reflective attribute")]),
    ("store_through_a_prefix_alias",
     dict(header="import contextlib\nimport tempfile\nt = tempfile\nt.TemporaryDirectory = contextlib.suppress\n",
          scan=TD_WALK),
     [("t.TemporaryDirectory = contextlib.suppress", "attribute store rebinds t.TemporaryDirectory")]),
    ("module_reached_by_importlib",
     dict(header="import contextlib\nimport importlib\nimport tempfile\nm = importlib.import_module('tempfile')\n"
                 "m.TemporaryDirectory = contextlib.suppress\n", scan=TD_WALK),
     [("import importlib", "dynamic import"),
      ("m.TemporaryDirectory = contextlib.suppress", "attribute store rebinds m.TemporaryDirectory")]),
    ("star_import", dict(header="import tempfile\nfrom review_patch import *\n", scan=TD_WALK),
     [("from review_patch import *", "star import")]),
    ("loop_target", dict(header="import contextlib\nimport tempfile\nfor tempfile in (contextlib,):\n    pass\n",
                         scan=TD_WALK),
     [("for tempfile in (contextlib,):", "store rebinds tempfile")]),
    ("parameter", dict(header="import tempfile\n", scan=TD_WALK,
                       edits=[("def scan(p):", "def scan(p, tempfile=None):")]),
     [("def scan(p, tempfile=None):", "parameter rebinds tempfile")]),
]


@pytest.mark.parametrize("name,shape,expect", REBOUND_MORE, ids=[r[0] for r in REBOUND_MORE])
def test_m5_fix9_every_listed_rebinding_operation_is_named(name, shape, expect):
    _named(name, shape, expect)


def test_m5_fix9_a_name_bound_to_two_values_is_judged_under_each():
    """The path-query alias map keeps every binding's value: a name assigned
    two different values (control d's shape) is judged under each, where a
    single value flipped between them and the enumeration never settled."""
    for first, second in (("sys", "os.path"), ("os.path", "sys")):
        src = "import os\nimport sys\nq = %s\nq = %s\nx = q.isdir(p)\n" % (first, second)
        assert [k for _l, k in r3.unwrapped_queries(src)] == ["os.path.isdir"], src
    assert r3.unwrapped_queries("import os\nimport sys\nq = sys\nq = os.path\nx = q.join(p)\n") == []


# -- fix pass 10: the proof bounded by namespace reach (r3._namespace_reach) -------------
MAIN = "def main(argv):"
GLOBALS_TD = dict(header="import contextlib\nfrom tempfile import TemporaryDirectory\n",
                  scan=SUPPRESS % "TemporaryDirectory")


def _after_scan(shape, text):
    """shape with `text` as module-level lines between scan and main."""
    return dict(shape, edits=[(MAIN, text + "\n\n\n" + MAIN)])


REBOUND10 = [
    ("a_report_scenario_verbatim", [
        (_after_scan(GLOBALS_TD, 'scan.__globals__["TemporaryDirectory"] = contextlib.suppress'),
         [('scan.__globals__["TemporaryDirectory"] = contextlib.suppress',
           "subscript store through namespace-reaching scan.__globals__")])]),
    ("b_the_aliased_mapping", [
        (_after_scan(GLOBALS_TD, 'g = scan.__globals__\ng["TemporaryDirectory"] = contextlib.suppress'),
         [('g["TemporaryDirectory"] = contextlib.suppress', "subscript store through namespace-reaching g")]),
        (_after_scan(GLOBALS_TD, '[scan.__globals__][0]["TemporaryDirectory"] = contextlib.suppress'),
         [('[scan.__globals__][0]["TemporaryDirectory"] = contextlib.suppress',
           "subscript store through namespace-reaching scan.__globals__")])]),
    ("c_vars_of_the_module_in_sys_modules", [
        (dict(header='import contextlib\nimport sys\nfrom tempfile import TemporaryDirectory\n'
                     'vars(sys.modules[__name__])["TemporaryDirectory"] = contextlib.suppress\n',
              scan=SUPPRESS % "TemporaryDirectory"),
         [('vars(sys.modules[__name__])["TemporaryDirectory"] = contextlib.suppress',
           "subscript store through namespace-reaching vars(sys.modules[__name__])")])]),
    ("d_the_string_built_name", [
        (_after_scan(GLOBALS_TD, 'getattr(scan, "__glo" + "bals__")["TemporaryDirectory"] = contextlib.suppress'),
         [('getattr(scan, "__glo" + "bals__")["TemporaryDirectory"] = contextlib.suppress',
           "subscript store through namespace-reaching getattr(scan, '__glo' + 'bals__')")])]),
    ("e_exec", [
        (dict(header='import contextlib\nimport tempfile\nexec("tempfile.TemporaryDirectory = contextlib.suppress")\n',
              scan=TD_WALK),
         [('exec("tempfile.TemporaryDirectory = contextlib.suppress")', "call of namespace-reaching exec")])]),
    ("f_mock_patch_and_monkeypatch", [
        (dict(header="import contextlib\nimport tempfile\nimport unittest.mock\n",
              scan='    with unittest.mock.patch("tempfile.TemporaryDirectory", contextlib.suppress):\n'
                   "        with tempfile.TemporaryDirectory(Exception):\n"
                   "            return list(os.walk(p, onerror=_walk_error))\n"),
         [('    with unittest.mock.patch("tempfile.TemporaryDirectory", contextlib.suppress):',
           "call of namespace-reaching unittest.mock.patch"),
          ("import unittest.mock", "import of namespace-reaching module unittest.mock")]),
        (dict(header='import contextlib\nimport tempfile\n\n\ndef _patch(monkeypatch):\n'
                     '    monkeypatch.setattr("tempfile.TemporaryDirectory", contextlib.suppress)\n', scan=TD_WALK),
         [('    monkeypatch.setattr("tempfile.TemporaryDirectory", contextlib.suppress)',
           "call of namespace-reaching monkeypatch.setattr")])]),
    ("g_the_module_dict_through_sys_modules", [
        (dict(header='import contextlib\nimport sys\nimport tempfile\n'
                     'sys.modules["tempfile"].__dict__["TemporaryDirectory"] = contextlib.suppress\n', scan=TD_WALK),
         [('sys.modules["tempfile"].__dict__["TemporaryDirectory"] = contextlib.suppress',
           "subscript store through namespace-reaching sys.modules['tempfile'].__dict__")])]),
    ("h_importlib_import_module", [
        (dict(header='import contextlib\nimport importlib\nimport tempfile\n'
                     'importlib.import_module("tempfile").TemporaryDirectory = contextlib.suppress\n', scan=TD_WALK),
         [('importlib.import_module("tempfile").TemporaryDirectory = contextlib.suppress',
           "attribute store through namespace-reaching importlib.import_module('tempfile')")])]),
    ("i_types_function_type_replacing_scan", [
        (_after_scan(dict(GLOBALS_TD, header="import contextlib\nimport types\nfrom tempfile import TemporaryDirectory\n"),
                     'scan = types.FunctionType(scan.__code__, {"TemporaryDirectory": contextlib.suppress, "os": os})'),
         [('scan = types.FunctionType(scan.__code__, {"TemporaryDirectory": contextlib.suppress, "os": os})',
           "call of namespace-reaching types.FunctionType"),
          ("import types", "import of namespace-reaching module types")])]),
]


@pytest.mark.parametrize("name,variants", REBOUND10, ids=[r[0] for r in REBOUND10])
def test_m5_fix10_a_namespace_reaching_rebind_reports_the_walk_naming_the_line(name, variants):
    for shape, expect in variants:
        _named(name, shape, expect)


def test_m5_fix10_j_a_benign_module_is_still_trusted():
    """Its own local dict written by subscript, getattr on a local object
    with a literal plain name, tempfile.TemporaryDirectory used unchanged:
    nothing reaches a namespace, the walk is still proven."""
    src = _plant(header="import tempfile\n\n\nclass _Box:\n    name = 'box'\n",
                 scan='    seen = {}\n    seen["root"] = p\n    box = _Box()\n    label = getattr(box, "name")\n'
                      "    with tempfile.TemporaryDirectory():\n        return list(os.walk(p, onerror=_walk_error))\n")
    assert r3.unwrapped_queries(src, "planted") == []
    assert _named_rows(src) == []


def _named_rows(src, file="planted"):
    tree = r3.ast.parse(src)
    parents = {}
    for n in r3.ast.walk(tree):
        for c in r3.ast.iter_child_nodes(n):
            parents[id(c)] = n
    return r3._namespace_reach(tree, r3._Names(tree, parents), file)


def _sites(src, file="<source>", unresolved_only=True):
    """The rows of the proof over src, each named as a site by r3._site_names:
    the row the proof prints (the rule, the operator or method, the base) and
    its enclosing function or class; sorted, never keyed by line."""
    rows = [(line, kind) for line, kind in _named_rows(src, file) if not unresolved_only or r3._unresolved(kind)]
    return r3._site_names(r3.ast.parse(src), rows)


def _planted(kind):
    return [("_planted_extra", kind + " through unresolved base d")]


NEEDLES = "backend/tools/review_needles.py"
# The unresolved-base sites of each real review module, measured at the tip of
# the lane and named, never counted: each entry is the row the proof prints and
# the function or class that encloses it (<module> outside any), a repeated
# entry once per site. The measured count of a module is the length of its
# list, so a site swapped for another at an equal count fails the pin as one
# more or one fewer does. review_needles.py's list is the exemption the proof
# itself carries (r3._MEASURED_CLEAN), written there independently.
REAL = {
    NEEDLES: [
        ('_Values.__init__', 'attribute store through unresolved base self'),
        ('_Values.add',
         'call of protocol-running callable any through unresolved base (_key_pattern(k) for k in keys)'),
        ('_Values.add', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_Values.add', 'method call add through unresolved base self'),
        ('_Values.add', 'method call append through unresolved base self.items'),
        ('_Values.add', 'method call append through unresolved base self.lists'),
        ('_blob_text', 'unproven pure method call decode through unresolved base raw'),
        ('_data_refs', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_data_refs', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_data_refs', "call of protocol-running callable isinstance through unresolved base node['data']"),
        ('_data_refs', 'call of protocol-running callable set through unresolved base node'),
        ('_data_refs', "call of unresolved callable out.add through unresolved base node['data']"),
        ('_data_refs', 'unproven pure method call values through unresolved base node'),
        ('_derive', 'call of protocol-running callable _PUBLIC.clear through unresolved base _PUBLIC'),
        ('_derive',
         "call of protocol-running callable _PUBLIC.extend through unresolved base sorted({ln.rstrip('\\n') for ln in f if ln.strip() and (not ln.startswith('#'))}, key=len, reverse=True)"),
        ('_derive', 'call of protocol-running callable len through unresolved base name'),
        ('_derive', 'call of protocol-running callable open through unresolved base listed'),
        ('_derive', 'call of protocol-running callable open through unresolved base public'),
        ('_derive', 'call of protocol-running callable os.listdir through unresolved base base'),
        ('_derive', 'call of protocol-running callable os.listdir through unresolved base store'),
        ('_derive', 'call of protocol-running callable os.path.join through unresolved base base'),
        ('_derive', 'call of protocol-running callable os.path.join through unresolved base store'),
        ('_derive', 'call of protocol-running callable os.path.join through unresolved base store'),
        ('_derive', 'call of protocol-running callable os.path.join through unresolved base tests'),
        ('_derive', 'call of protocol-running callable os.path.join through unresolved base tests'),
        ('_derive', 'call of protocol-running callable sorted through unresolved base os.listdir(store)'),
        ('_derive',
         "call of protocol-running callable sorted through unresolved base {ln.rstrip('\\n') for ln in f if ln.strip() and (not ln.startswith('#'))}"),
        ('_derive',
         "callback of sorted (protocol-running callable len) through unresolved base {ln.rstrip('\\n') for ln in f if ln.strip() and (not ln.startswith('#'))}"),
        ('_derive', "method call add through unresolved base out['basename']"),
        ('_derive', 'subscript store through unresolved base out'),
        ('_derive', 'unproven pure method call fullmatch through unresolved base _REV_DIR'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable len through unresolved base rest'),
        ('_dispatch', 'call of protocol-running callable open through unresolved base rest[0]'),
        ('_dispatch',
         "call of protocol-running callable print through unresolved base __doc__.split('Modes:')[1].split('Exit 0')[0].rstrip()"),
        ('_dispatch',
         "unproven pure method call rstrip through unresolved base __doc__.split('Modes:')[1].split('Exit 0')[0]"),
        ('_dispatch', "unproven pure method call split through unresolved base __doc__.split('Modes:')[1]"),
        ('_entries', 'call of protocol-running callable getattr through unresolved base st'),
        ('_entries', 'call of protocol-running callable getattr through unresolved base st'),
        ('_entries', 'call of protocol-running callable os.path.join through unresolved base top'),
        ('_entries', 'call of protocol-running callable os.path.join through unresolved base top'),
        ('_entries', 'call of protocol-running callable os.scandir through unresolved base top'),
        ('_entries', 'call of protocol-running callable sorted through unresolved base (e.name for e in it)'),
        ('_entries', 'call of protocol-running callable stat.S_ISDIR through unresolved base st.st_mode'),
        ('_entries', 'call of protocol-running callable stat.S_ISDIR through unresolved base st.st_mode'),
        ('_entries', 'call of protocol-running callable stat.S_ISLNK through unresolved base st.st_mode'),
        ('_entries', 'call of protocol-running callable stat.S_ISREG through unresolved base st.st_mode'),
        ('_entries', 'call of protocol-running callable str through unresolved base root'),
        ('_expr', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_expr', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_expr', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_expr', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_expr', 'call of protocol-running callable len through unresolved base node'),
        ('_expr', 'method call add through unresolved base vals'),
        ('_expr', 'unproven pure method call items through unresolved base node'),
        ('_finite', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_finite', 'call of protocol-running callable math.isfinite through unresolved base v'),
        ('_git',
         "call of protocol-running callable subprocess.run through unresolved base ['git', '-C', repo, *args]"),
        ('_git', 'unproven pure method call decode through unresolved base out'),
        ('_ident', 'call of protocol-running callable stat.S_IFMT through unresolved base st.st_mode'),
        ('_inside', 'call of protocol-running callable os.path.commonpath through unresolved base [a, b]'),
        ('_inside', 'call of protocol-running callable os.path.realpath through unresolved base path'),
        ('_inside', 'call of protocol-running callable os.path.realpath through unresolved base root'),
        ('_is_dir', 'call of protocol-running callable stat.S_ISDIR through unresolved base st.st_mode'),
        ('_is_file', 'call of protocol-running callable stat.S_ISREG through unresolved base st.st_mode'),
        ('_key_pattern',
         "call of protocol-running callable '[ _-]?'.join through unresolved base (re.escape(w) for w in words)"),
        ('_key_pattern', 'call of protocol-running callable re.escape through unresolved base w'),
        ('_key_pattern', 'call of protocol-running callable re.escape through unresolved base words.pop()'),
        ('_key_pattern', 'call of protocol-running callable re.split through unresolved base key'),
        ('_keys', 'call of protocol-running callable isinstance through unresolved base n'),
        ('_keys', 'call of protocol-running callable len through unresolved base n'),
        ('_manifest_body', "call of protocol-running callable '\\n'.join through unresolved base lines"),
        ('_manifest_body', 'call of protocol-running callable hashlib.md5 through unresolved base data'),
        ('_manifest_body', 'call of protocol-running callable len through unresolved base data'),
        ('_manifest_body', 'call of protocol-running callable open through unresolved base note_file'),
        ('_manifest_body',
         'call of protocol-running callable sorted through unresolved base ((rel, hashlib.md5(data).hexdigest(), len(data)) for rel, data in snap)'),
        ('_manifest_body', 'call of protocol-running callable sum through unresolved base (n for _r, _m, n in rows)'),
        ('_manifest_body', 'call of protocol-running callable time.strftime through unresolved base time.gmtime()'),
        ('_manifest_body', "unproven pure method call encode through unresolved base '\\n'.join(lines) + '\\n'"),
        ('_manifest_body', 'unproven pure method call hexdigest through unresolved base hashlib.md5(data)'),
        ('_manifest_body', "unproven pure method call strip through unresolved base _git(pin, 'rev-parse', 'HEAD')"),
        ('_manifest_body', 'unproven pure method call strip through unresolved base f.read()'),
        ('_manifest_lines_of', 'call of protocol-running callable hashlib.sha256 through unresolved base raw'),
        ('_manifest_lines_of', 'call of protocol-running callable sorted through unresolved base snap'),
        ('_manifest_lines_of', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(raw)'),
        ('_measure_keys', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_measure_keys', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_measure_keys', "call of protocol-running callable isinstance through unresolved base node['m']"),
        ('_measure_keys', 'call of protocol-running callable set through unresolved base node'),
        ('_measure_keys',
         "call of unresolved callable out.append through unresolved base node['m'].rsplit('.', 1)[-1]"),
        ('_measure_keys', "unproven pure method call rsplit through unresolved base node['m']"),
        ('_measure_keys', 'unproven pure method call values through unresolved base node'),
        ('_merge', 'subscript store through unresolved base a'),
        ('_merge', 'unproven pure method call get through unresolved base a'),
        ('_merge', 'unproven pure method call items through unresolved base b'),
        ('_meta', "call of protocol-running callable isinstance through unresolved base r['post']"),
        ('_meta', "call of protocol-running callable isinstance through unresolved base r['post_since']"),
        ('_meta', 'call of protocol-running callable isinstance through unresolved base r[k]'),
        ('_meta', 'call of protocol-running callable isinstance through unresolved base s'),
        ('_meta', 'call of protocol-running callable isinstance through unresolved base show'),
        ('_meta', 'call of protocol-running callable isinstance through unresolved base x'),
        ('_meta', 'call of protocol-running callable set through unresolved base r'),
        ('_meta', 'unproven pure method call get through unresolved base r'),
        ('_num_tokens', 'call of protocol-running callable int through unresolved base v'),
        ('_num_tokens', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_num_tokens', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_num_tokens', 'call of protocol-running callable repr through unresolved base v'),
        ('_num_tokens', 'call of protocol-running callable sorted through unresolved base toks'),
        ('_num_tokens', 'call of protocol-running callable str through unresolved base v'),
        ('_num_tokens', 'unproven pure method call is_integer through unresolved base v'),
        ('_num_tokens', 'unproven pure method call startswith through unresolved base t'),
        ('_num_tokens', 'unproven pure method call startswith through unresolved base t'),
        ('_pred', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_pred', "call of protocol-running callable isinstance through unresolved base node['args']"),
        ('_pred', "call of protocol-running callable isinstance through unresolved base node['op']"),
        ('_pred', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_pred', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_pred', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_pred', "call of protocol-running callable isinstance through unresolved base v['data']"),
        ('_pred', 'call of protocol-running callable set through unresolved base node'),
        ('_pred', 'call of protocol-running callable set through unresolved base node'),
        ('_pred', 'call of protocol-running callable set through unresolved base node'),
        ('_pred', 'call of protocol-running callable set through unresolved base v'),
        ('_pred', 'method call add through unresolved base vals'),
        ('_pred', 'unproven pure method call items through unresolved base node'),
        ('_pred', "unproven pure method call items through unresolved base node['args']"),
        ('_pred', "unproven pure method call rsplit through unresolved base node['op']"),
        ('_read_regular', 'call of protocol-running callable len through unresolved base raw'),
        ('_read_regular', 'call of protocol-running callable open through unresolved base path'),
        ('_read_regular', 'call of protocol-running callable os.fstat through unresolved base f.fileno()'),
        ('_report_line',
         "call of protocol-running callable ', '.join through unresolved base ('%s=%d' % (k, found[k]) for k in sorted(found))"),
        ('_report_line', 'call of protocol-running callable sorted through unresolved base found'),
        ('_report_line', 'call of protocol-running callable sum through unresolved base found.values()'),
        ('_report_line', 'method call pop through unresolved base found'),
        ('_report_line', 'method call pop through unresolved base found'),
        ('_report_line', 'unproven pure method call values through unresolved base found'),
        ('_revision', 'augmented subscript store |= through unresolved base out'),
        ('_revision', 'call of protocol-running callable isinstance through unresolved base doc'),
        ('_revision', "call of protocol-running callable isinstance through unresolved base doc.get('nonce')"),
        ('_revision', "call of protocol-running callable isinstance through unresolved base r.get('id')"),
        ('_revision', 'call of protocol-running callable json.loads through unresolved base text'),
        ('_revision', 'call of protocol-running callable len through unresolved base f'),
        ('_revision', 'call of protocol-running callable len through unresolved base f.strip()'),
        ('_revision', 'call of protocol-running callable len through unresolved base stem'),
        ('_revision', 'call of protocol-running callable open through unresolved base os.path.join(ddir, dn)'),
        ('_revision',
         "call of protocol-running callable open through unresolved base os.path.join(path, 'rules.json')"),
        ('_revision', 'call of protocol-running callable os.listdir through unresolved base ddir'),
        ('_revision', 'call of protocol-running callable os.path.join through unresolved base ddir'),
        ('_revision', 'call of protocol-running callable os.path.join through unresolved base path'),
        ('_revision', 'call of protocol-running callable os.path.join through unresolved base path'),
        ('_revision', 'call of protocol-running callable sorted through unresolved base _data_refs(doc)'),
        ('_revision', 'call of protocol-running callable sorted through unresolved base os.listdir(ddir)'),
        ('_revision', "method call add through unresolved base out['data']"),
        ('_revision', "method call add through unresolved base out['data']"),
        ('_revision', "method call add through unresolved base out['nonce']"),
        ('_revision', "method call add through unresolved base out['rule_id']"),
        ('_revision', "method call add through unresolved base out['wording']"),
        ('_revision', 'unproven pure method call decode through unresolved base f.read()'),
        ('_revision', 'unproven pure method call endswith through unresolved base dn'),
        ('_revision', 'unproven pure method call get through unresolved base doc'),
        ('_revision', 'unproven pure method call get through unresolved base doc'),
        ('_revision', 'unproven pure method call get through unresolved base r'),
        ('_revision', 'unproven pure method call get through unresolved base r'),
        ('_revision', 'unproven pure method call rsplit through unresolved base dn'),
        ('_revision', 'unproven pure method call split through unresolved base _PLACE'),
        ('_revision', 'unproven pure method call strip through unresolved base f'),
        ('_revision', 'unproven pure method call strip through unresolved base f'),
        ('_rx', 'call of protocol-running callable re.compile through unresolved base p'),
        ('_sequence',
         'call of protocol-running callable re.compile through unresolved base gap.join((re.escape(f) for f in frags))'),
        ('_sequence', 'call of protocol-running callable re.escape through unresolved base f'),
        ('_sequence', 'call of unresolved callable gap.join through unresolved base (re.escape(f) for f in frags)'),
        ('_sitting', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_sitting', "call of protocol-running callable isinstance through unresolved base node['args']"),
        ('_sitting', "call of protocol-running callable isinstance through unresolved base node['op']"),
        ('_sitting', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_sitting', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_sitting', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_sitting', 'call of protocol-running callable isinstance through unresolved base x'),
        ('_sitting', 'call of protocol-running callable set through unresolved base node'),
        ('_sitting', 'method call add through unresolved base vals'),
        ('_sitting', "unproven pure method call items through unresolved base node['args']"),
        ('_sitting', "unproven pure method call rsplit through unresolved base node['op']"),
        ('_status', 'call of protocol-running callable os.lstat through unresolved base path'),
        ('_status', 'call of protocol-running callable os.stat through unresolved base path'),
        ('_table', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_table', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_table', 'call of protocol-running callable isinstance through unresolved base x'),
        ('_table', 'call of protocol-running callable isinstance through unresolved base x'),
        ('_table', 'method call add through unresolved base vals'),
        ('_table', 'method call add through unresolved base vals'),
        ('_table', 'method call add through unresolved base vals'),
        ('_table', 'unproven pure method call items through unresolved base node'),
        ('_text_lines', 'unproven pure method call splitlines through unresolved base text'),
        ('_text_lines', 'unproven pure method call strip through unresolved base ln'),
        ('_text_value', 'call of protocol-running callable float through unresolved base tok'),
        ('_text_value', 'call of protocol-running callable int through unresolved base tok'),
        ('_text_value', 'unproven pure method call fullmatch through unresolved base _TEXT_NUM'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base doc'),
        ('_value_items',
         "call of protocol-running callable isinstance through unresolved base doc.get('closure', {})"),
        ('_value_items', "call of protocol-running callable isinstance through unresolved base doc.get('format')"),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base n'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base n'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base params'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base ps'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base r'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base rules'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base table'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base vocab'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base vocab'),
        ('_value_items', 'call of protocol-running callable isinstance through unresolved base vocab'),
        ('_value_items', 'call of protocol-running callable set through unresolved base doc'),
        ('_value_items', 'call of protocol-running callable set through unresolved base vocab'),
        ('_value_items', 'call of protocol-running callable sorted through unresolved base (tables or {}).items()'),
        ('_value_items', 'call of protocol-running callable sorted through unresolved base vocab.items()'),
        ('_value_items', 'call of protocol-running callable str through unresolved base fam'),
        ('_value_items', "call of protocol-running callable str through unresolved base r.get('id')"),
        ('_value_items', 'unproven pure method call get through unresolved base doc'),
        ('_value_items', 'unproven pure method call get through unresolved base doc'),
        ('_value_items', 'unproven pure method call get through unresolved base doc'),
        ('_value_items', 'unproven pure method call get through unresolved base doc'),
        ('_value_items', 'unproven pure method call get through unresolved base r'),
        ('_value_items', 'unproven pure method call items through unresolved base params'),
        ('_value_items', 'unproven pure method call items through unresolved base ps'),
        ('_value_items', 'unproven pure method call items through unresolved base tables or {}'),
        ('_value_items', 'unproven pure method call items through unresolved base vocab'),
        ('_value_items', 'unproven pure method call rsplit through unresolved base name'),
        ('_value_items', 'unproven pure method call rsplit through unresolved base name'),
        ('_value_items', 'unproven pure method call rsplit through unresolved base str(fam)'),
        ('_value_items', 'unproven pure method call split through unresolved base _TEXT_SPLIT'),
        ('_value_items', 'unproven pure method call strip through unresolved base ln'),
        ('_value_items', 'unproven pure method call strip through unresolved base ln'),
        ('_value_needles',
         "call of protocol-running callable '|'.join through unresolved base (re.escape(t) for t in _num_tokens(x))"),
        ('_value_needles',
         "call of protocol-running callable '|'.join through unresolved base (re.escape(x) for x in _num_tokens(v))"),
        ('_value_needles', "call of protocol-running callable '|'.join through unresolved base sorted(alts)"),
        ('_value_needles',
         "call of protocol-running callable any through unresolved base (k.endswith('days') for k in keys)"),
        ('_value_needles',
         "call of protocol-running callable any through unresolved base (k.endswith('ms') for k in keys)"),
        ('_value_needles', 'call of protocol-running callable by_group.setdefault through unresolved base group'),
        ('_value_needles', 'call of protocol-running callable len through unresolved base alts'),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '%s[ \\\\t]?ms\\\\b' % val"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '%s[ \\\\t]{0,3}%s' % (val, _SIGN)"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?<![\\\\w.])(?:%s)(?:[ \\\\t]*[,;/][ \\\\t]*|[ \\\\t]+)(?:%s)(?![\\\\w]|\\\\.\\\\d)' % (x, y)"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?<![\\\\w.])(?:%s)[ \\\\t]?/[ \\\\t]?(?:%s)(?![\\\\w]|\\\\.\\\\d)' % (one, one)"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?i)%s[ \\\\t-]?days?\\\\b' % val"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?i)%s[ \\\\t]{0,3}%s' % (_CMP, val)"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?i)%s[^\\\\n]{0,%d}?\\\\b%s\\\\b' % (val, VALUE_NEAR, kp)"),
        ('_value_needles', "call of protocol-running callable out.add through unresolved base '(?i)' + val"),
        ('_value_needles',
         "call of protocol-running callable out.add through unresolved base '(?i)\\\\b%s\\\\b[^\\\\n]{0,%d}?%s' % (kp, VALUE_NEAR, val)"),
        ('_value_needles', 'call of protocol-running callable re.escape through unresolved base t'),
        ('_value_needles', 'call of protocol-running callable re.escape through unresolved base x'),
        ('_value_needles', 'call of protocol-running callable sorted through unresolved base alts'),
        ('_value_needles', 'call of protocol-running callable zip through unresolved base alts'),
        ('_value_needles', 'method call add through unresolved base by_group.setdefault(group, set())'),
        ('_value_needles', 'unproven pure method call endswith through unresolved base k'),
        ('_value_needles', 'unproven pure method call endswith through unresolved base k'),
        ('_value_rx',
         "call of protocol-running callable '|'.join through unresolved base (re.escape(x) for x in _num_tokens(v))"),
        ('_value_rx', 'call of protocol-running callable re.escape through unresolved base v'),
        ('_value_rx', 'call of protocol-running callable re.escape through unresolved base x'),
        ('_write_manifest', 'call of protocol-running callable f.write through unresolved base body'),
        ('_write_manifest', 'call of protocol-running callable open through unresolved base dst'),
        ('_write_manifest', 'call of protocol-running callable os.path.basename through unresolved base out'),
        ('_write_manifest', 'call of protocol-running callable os.path.join through unresolved base pin'),
        ('_write_manifest', 'call of protocol-running callable os.path.join through unresolved base ri'),
        ('corpus_digest',
         "call of unresolved callable ('%s\\t%d\\t%s\\n' % (name, size, digest)).encode through unresolved base ('%s\\t%d\\t%s\\n' % (name, size, digest)).encode"),
        ('corpus_digest', 'method call update through unresolved base h'),
        ('corpus_digest', 'unproven pure method call hexdigest through unresolved base h'),
        ('count', 'call of protocol-running callable found.get through unresolved base cls'),
        ('count', 'call of protocol-running callable isinstance through unresolved base s'),
        ('count', 'unproven pure method call items through unresolved base needles'),
        ('count', 'unproven pure method call replace through unresolved base public_cut'),
        ('count', 'unproven pure method call search through unresolved base _rx(s[1])'),
        ('count', 'unproven pure method call search through unresolved base _sequence(s)'),
        ('leaf_type', 'call of protocol-running callable abs through unresolved base v'),
        ('leaf_type', 'call of protocol-running callable isinstance through unresolved base v'),
        ('leaf_type', 'call of protocol-running callable isinstance through unresolved base v'),
        ('leaf_type', 'call of protocol-running callable isinstance through unresolved base v'),
        ('leaf_type', 'call of protocol-running callable isinstance through unresolved base v'),
        ('leaf_type', 'call of protocol-running callable len through unresolved base v'),
        ('leaf_type', 'unproven pure method call is_integer through unresolved base v'),
        ('main', 'call of protocol-running callable isinstance through unresolved base e'),
        ('main', 'call of protocol-running callable isinstance through unresolved base e'),
        ('main', 'call of protocol-running callable len through unresolved base argv'),
        ('main',
         "call of protocol-running callable print through unresolved base 'review_needles: no verdict (%s): refused' % (e if isinstance(e, NoVerdict) else type(e).__name__)"),
        ('main',
         "call of protocol-running callable print through unresolved base 'review_needles: no verdict (a read failed: %s): refused, no result' % (e if isinstance(e, NoVerdict) else type(e).__name__)"),
        ('main',
         "call of protocol-running callable print through unresolved base 'review_needles: no verdict (store unreadable: %s): refused, nothing was scanned' % e"),
        ('main',
         "call of protocol-running callable print through unresolved base __doc__.split('Modes:')[1].split('Exit 0')[0].rstrip()"),
        ('main',
         "unproven pure method call rstrip through unresolved base __doc__.split('Modes:')[1].split('Exit 0')[0]"),
        ('main', "unproven pure method call split through unresolved base __doc__.split('Modes:')[1]"),
        ('packet', "call of protocol-running callable '\\n'.join through unresolved base _manifest_lines_of(snap)"),
        ('packet', 'call of protocol-running callable f.write through unresolved base body'),
        ('packet', 'call of protocol-running callable f.write through unresolved base raw'),
        ('packet', 'call of protocol-running callable f.write through unresolved base raw'),
        ('packet',
         "call of protocol-running callable hashlib.sha1 through unresolved base b'blob %d\\x00' % len(got) + got"),
        ('packet', 'call of protocol-running callable hashlib.sha256 through unresolved base body'),
        ('packet', 'call of protocol-running callable hashlib.sha256 through unresolved base got'),
        ('packet', 'call of protocol-running callable hashlib.sha256 through unresolved base raw'),
        ('packet', 'call of protocol-running callable len through unresolved base got'),
        ('packet', 'call of protocol-running callable len through unresolved base parts'),
        ('packet', 'call of protocol-running callable len through unresolved base snap'),
        ('packet', 'call of protocol-running callable open through unresolved base allowlist'),
        ('packet', 'call of protocol-running callable open through unresolved base d'),
        ('packet', 'call of protocol-running callable open through unresolved base dst'),
        ('packet', 'call of protocol-running callable open through unresolved base dst'),
        ('packet', 'call of protocol-running callable open through unresolved base os.path.join(out_dir, MANIFEST)'),
        ('packet', 'call of protocol-running callable os.listdir through unresolved base out_dir'),
        ('packet', 'call of protocol-running callable os.makedirs through unresolved base os.path.dirname(dst)'),
        ('packet', 'call of protocol-running callable os.makedirs through unresolved base os.path.dirname(dst)'),
        ('packet', 'call of protocol-running callable os.makedirs through unresolved base out_dir'),
        ('packet', 'call of protocol-running callable os.path.basename through unresolved base d'),
        ('packet', 'call of protocol-running callable os.path.basename through unresolved base d'),
        ('packet', 'call of protocol-running callable os.path.basename through unresolved base d'),
        ('packet', 'call of protocol-running callable os.path.dirname through unresolved base dst'),
        ('packet', 'call of protocol-running callable os.path.dirname through unresolved base dst'),
        ('packet', 'call of protocol-running callable os.path.isabs through unresolved base parts[1]'),
        ('packet', 'call of protocol-running callable os.path.join through unresolved base out_dir'),
        ('packet', 'call of protocol-running callable os.path.join through unresolved base out_dir'),
        ('packet', 'call of protocol-running callable os.path.join through unresolved base out_dir'),
        ('packet', 'call of protocol-running callable re.fullmatch through unresolved base parts[2]'),
        ('packet',
         "call of protocol-running callable set through unresolved base _git(repo, 'ls-tree', '-r', '--name-only', '-z', commit).split('\\x00')"),
        ('packet', 'call of protocol-running callable sorted through unresolved base pins'),
        ('packet',
         "unproven pure method call encode through unresolved base '\\n'.join(_manifest_lines_of(snap)) + '\\n'"),
        ('packet',
         "unproven pure method call hexdigest through unresolved base hashlib.sha1(b'blob %d\\x00' % len(got) + got)"),
        ('packet', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(body)'),
        ('packet', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(got)'),
        ('packet', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(raw)'),
        ('packet',
         "unproven pure method call split through unresolved base _git(repo, 'ls-tree', '-r', '--name-only', '-z', commit)"),
        ('packet', 'unproven pure method call split through unresolved base ln'),
        ('packet', 'unproven pure method call split through unresolved base p'),
        ('packet', 'unproven pure method call split through unresolved base p'),
        ('packet', 'unproven pure method call startswith through unresolved base ln'),
        ('packet', 'unproven pure method call startswith through unresolved base p'),
        ('packet',
         "unproven pure method call strip through unresolved base _git(repo, 'rev-parse', '%s:%s' % (commit, p))"),
        ('packet', 'unproven pure method call strip through unresolved base ln'),
        ('packet_verify', 'call of protocol-running callable dict through unresolved base snap'),
        ('packet_verify', 'call of protocol-running callable dict(snap).get through unresolved base dict(snap)'),
        ('packet_verify', 'call of protocol-running callable hashlib.sha256 through unresolved base raw'),
        ('packet_verify', 'unproven pure method call decode through unresolved base raw'),
        ('packet_verify', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(raw)'),
        ('packet_verify',
         "unproven pure method call splitlines through unresolved base raw.decode('utf-8', 'replace')"),
        ('report', 'call of protocol-running callable print through unresolved base line'),
        ('scan_range', 'call of protocol-running callable len through unresolved base commits'),
        ('scan_range', 'call of protocol-running callable len through unresolved base tree'),
        ('scan_range', 'call of protocol-running callable set through unresolved base blob'),
        ('scan_range',
         "unproven pure method call split through unresolved base _git(repo, 'diff-tree', '-r', '--no-commit-id', '-z', '--root', c)"),
        ('scan_range',
         "unproven pure method call split through unresolved base _git(repo, 'rev-list', '%s..%s' % (base, tip))"),
        ('scan_range', 'unproven pure method call split through unresolved base meta'),
        ('scan_range', 'unproven pure method call startswith through unresolved base status'),
        ('scan_staged',
         "unproven pure method call split through unresolved base _git(repo, 'diff', '--cached', '--name-only', '-z')"),
        ('scan_staged',
         "unproven pure method call split through unresolved base _git(repo, 'diff', '--cached', '--name-only', '-z', '--diff-filter=d')"),
        ('seal', 'augmented assignment += through unresolved base body'),
        ('seal', "call of protocol-running callable '\\n'.join through unresolved base body"),
        ('seal', 'call of protocol-running callable dict through unresolved base found'),
        ('seal', "call of protocol-running callable f.write through unresolved base '\\n'.join(body) + '\\n'"),
        ('seal', 'call of protocol-running callable len through unresolved base rows'),
        ('seal', 'call of protocol-running callable open through unresolved base seal_file'),
        ('seal', 'call of protocol-running callable os.path.basename through unresolved base out'),
        ('seal', 'call of protocol-running callable os.path.join through unresolved base pin'),
        ('seal', 'call of protocol-running callable sorted through unresolved base snap + [(name, body)]'),
        ('seal_verify',
         'call of protocol-running callable any through unresolved base (cur[k] != was[k] for k in was)'),
        ('seal_verify', 'call of protocol-running callable int through unresolved base lines[2].split()[1]'),
        ('seal_verify', 'call of protocol-running callable int through unresolved base n'),
        ('seal_verify', 'call of protocol-running callable len through unresolved base lines'),
        ('seal_verify', 'call of protocol-running callable open through unresolved base seal_file'),
        ('seal_verify', 'call of protocol-running callable set through unresolved base cur'),
        ('seal_verify', 'call of protocol-running callable set through unresolved base cur'),
        ('seal_verify', 'call of protocol-running callable set through unresolved base was'),
        ('seal_verify', 'call of protocol-running callable set through unresolved base was'),
        ('seal_verify', 'unproven pure method call split through unresolved base lines[0]'),
        ('seal_verify', 'unproven pure method call split through unresolved base lines[2]'),
        ('seal_verify', 'unproven pure method call split through unresolved base ln'),
        ('seal_verify', 'unproven pure method call splitlines through unresolved base f.read()'),
        ('seal_verify', 'unproven pure method call startswith through unresolved base lines[0]'),
        ('seal_verify', 'unproven pure method call startswith through unresolved base lines[2]'),
        ('snapshot', 'call of protocol-running callable os.path.join through unresolved base root'),
        ('snapshot', 'call of protocol-running callable set through unresolved base again'),
        ('snapshot', 'call of protocol-running callable set through unresolved base listed'),
        ('snapshot',
         'call of protocol-running callable sorted through unresolved base (k for k in listed if again[k] != listed[k])'),
        ('snapshot', 'call of protocol-running callable sorted through unresolved base listed'),
        ('snapshot', 'call of protocol-running callable sorted through unresolved base set(again) ^ set(listed)'),
        ('snapshot', 'unproven pure method call split through unresolved base rel'),
        ('snapshot_rows', 'call of protocol-running callable hashlib.sha256 through unresolved base raw'),
        ('snapshot_rows', 'call of protocol-running callable len through unresolved base raw'),
        ('snapshot_rows',
         'call of protocol-running callable sorted through unresolved base ((rel, len(raw), hashlib.sha256(raw).hexdigest()) for rel, raw in snap)'),
        ('snapshot_rows', 'unproven pure method call hexdigest through unresolved base hashlib.sha256(raw)'),
        ('write_manifest', 'call of protocol-running callable os.path.basename through unresolved base out'),
        ('write_manifest', 'call of protocol-running callable os.path.join through unresolved base pin'),
        ('<module>', 'implicit attribute read through unresolved base sys'),
        ('<module>', 'implicit subscript read through unresolved base sys.argv'),
        ('_Values.add', 'implicit attribute read through unresolved base self'),
        ('_Values.add', 'implicit attribute read through unresolved base self'),
        ('_Values.add', 'implicit binary operator through unresolved base where'),
        ('_Values.add', 'implicit comparison through unresolved base x'),
        ('_Values.add', 'implicit iteration through unresolved base keys'),
        ('_Values.add', 'implicit iteration through unresolved base v'),
        ('_Values.add', 'implicit iteration through unresolved base v'),
        ('_Values.add', 'implicit result disposal through unresolved base self.add(x, keys, group, where)'),
        ('_Values.add', 'implicit result disposal through unresolved base self.items.append((keys, v, t, group))'),
        ('_Values.add', 'implicit result disposal through unresolved base self.lists.append(tuple(near))'),
        ('_Values.add', 'implicit subscript read through unresolved base t'),
        ('_Values.add', 'implicit truth test through unresolved base _finite(x)'),
        ('_Values.add', 'implicit truth test through unresolved base _finite(x) and x not in (0, 1, -1)'),
        ('_data_refs', 'implicit comparison through unresolved base set(node)'),
        ('_data_refs', 'implicit iteration through unresolved base node'),
        ('_data_refs', 'implicit iteration through unresolved base node.values()'),
        ('_data_refs', 'implicit subscript read through unresolved base node'),
        ('_data_refs', 'implicit subscript read through unresolved base node'),
        ('_data_refs', "implicit truth test through unresolved base set(node) == {'data'}"),
        ('_data_refs',
         "implicit truth test through unresolved base set(node) == {'data'} and isinstance(node['data'], str)"),
        ('_derive', 'implicit binary operator through unresolved base (name, e)'),
        ('_derive', 'implicit comparison through unresolved base name'),
        ('_derive', 'implicit comparison through unresolved base name'),
        ('_derive', "implicit hashing through unresolved base ln.rstrip('\\n')"),
        ('_derive', 'implicit hashing through unresolved base ln.strip()'),
        ('_derive', 'implicit iteration through unresolved base os.listdir(base)'),
        ('_derive', 'implicit result disposal through unresolved base _revision(path, out)'),
        ('_derive', "implicit result disposal through unresolved base out['basename'].add(name)"),
        ('_derive', 'implicit subscript read through unresolved base out'),
        ('_derive', 'implicit truth test through unresolved base _REV_DIR.fullmatch(name)'),
        ('_derive', 'implicit truth test through unresolved base _is_dir(path)'),
        ('_derive', 'implicit truth test through unresolved base _is_file(os.path.join(base, name))'),
        ('_derive',
         "implicit truth test through unresolved base _is_file(os.path.join(base, name)) and '.' in name and (len(name) >= BASENAME_MIN) and (name not in PUBLIC_NAMES)"),
        ('_derive', "implicit truth test through unresolved base ln.startswith('#')"),
        ('_derive', "implicit truth test through unresolved base ln.startswith('#')"),
        ('_derive', 'implicit truth test through unresolved base ln.strip()'),
        ('_derive', 'implicit truth test through unresolved base ln.strip()'),
        ('_derive', "implicit truth test through unresolved base ln.strip() and (not ln.startswith('#'))"),
        ('_derive', "implicit truth test through unresolved base ln.strip() and (not ln.startswith('#'))"),
        ('_dispatch', 'implicit comparison through unresolved base cmd'),
        ('_dispatch', 'implicit comparison through unresolved base cmd'),
        ('_dispatch', 'implicit comparison through unresolved base cmd'),
        ('_dispatch', 'implicit comparison through unresolved base cmd'),
        ('_dispatch', 'implicit comparison through unresolved base cmd'),
        ('_dispatch', 'implicit comparison through unresolved base cmd'),
        ('_dispatch', 'implicit comparison through unresolved base cmd'),
        ('_dispatch', 'implicit iteration through unresolved base rest'),
        ('_dispatch', 'implicit iteration through unresolved base scan_range(rest[0], rest[1], rest[2], needles)'),
        ('_dispatch', "implicit subscript read through unresolved base __doc__.split('Modes:')"),
        ('_dispatch', "implicit subscript read through unresolved base __doc__.split('Modes:')[1].split('Exit 0')"),
        ('_dispatch', 'implicit subscript read through unresolved base rest'),
        ('_dispatch', 'implicit subscript read through unresolved base rest'),
        ('_dispatch', 'implicit subscript read through unresolved base rest'),
        ('_dispatch', 'implicit subscript read through unresolved base rest'),
        ('_dispatch', 'implicit subscript read through unresolved base rest'),
        ('_dispatch', 'implicit subscript read through unresolved base rest'),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'message'"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'message' and len(rest) == 1"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'packet'"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'packet' and len(rest) == 4"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'packet-verify'"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'packet-verify' and len(rest) == 2"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'range'"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'range' and len(rest) == 3"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'scan-dir'"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'scan-dir' and len(rest) == 1"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'seal'"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'seal' and len(rest) == 6"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'staged'"),
        ('_dispatch', "implicit truth test through unresolved base cmd == 'staged' and len(rest) == 1"),
        ('_entries', 'implicit attribute read through unresolved base e'),
        ('_entries', 'implicit attribute read through unresolved base st'),
        ('_entries', 'implicit attribute read through unresolved base st'),
        ('_entries', 'implicit attribute read through unresolved base st'),
        ('_entries', 'implicit attribute read through unresolved base st'),
        ('_entries', 'implicit attribute read through unresolved base type(e)'),
        ('_entries', "implicit binary operator through unresolved base (type(e).__name__, prefix or '.')"),
        ('_entries', "implicit binary operator through unresolved base getattr(st, 'st_file_attributes', 0)"),
        ('_entries', "implicit binary operator through unresolved base getattr(st, 'st_file_attributes', 0)"),
        ('_entries', 'implicit binary operator through unresolved base prefix'),
        ('_entries', 'implicit binary operator through unresolved base rel'),
        ('_entries', 'implicit binary operator through unresolved base rel'),
        ('_entries', 'implicit binary operator through unresolved base rel'),
        ('_entries', 'implicit binary operator through unresolved base rel'),
        ('_entries', 'implicit binary operator through unresolved base str(root)'),
        ('_entries', 'implicit iteration through unresolved base it'),
        ('_entries', 'implicit iteration through unresolved base todo.pop()'),
        ('_entries', 'implicit truth test through unresolved base prefix'),
        ('_entries',
         "implicit truth test through unresolved base st is None or not stat.S_ISDIR(st.st_mode) or getattr(st, 'st_file_attributes', 0) & _REPARSE_POINT"),
        ('_entries', 'implicit truth test through unresolved base stat.S_ISDIR(st.st_mode)'),
        ('_entries', 'implicit truth test through unresolved base stat.S_ISDIR(st.st_mode)'),
        ('_entries', 'implicit truth test through unresolved base stat.S_ISLNK(st.st_mode)'),
        ('_entries',
         "implicit truth test through unresolved base stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & _REPARSE_POINT"),
        ('_entries', 'implicit truth test through unresolved base stat.S_ISREG(st.st_mode)'),
        ('_expr', 'implicit comparison through unresolved base k'),
        ('_expr', 'implicit comparison through unresolved base k'),
        ('_expr', 'implicit comparison through unresolved base k'),
        ('_expr', 'implicit comparison through unresolved base k'),
        ('_expr', 'implicit iteration through unresolved base node.items()'),
        ('_expr', 'implicit iteration through unresolved base v'),
        ('_expr', 'implicit result disposal through unresolved base _expr(v, keys, group, vals)'),
        ('_expr', 'implicit result disposal through unresolved base _expr(x, keys, group, vals)'),
        ('_expr', "implicit result disposal through unresolved base vals.add(v, keys, group, 'literal')"),
        ('_expr', "implicit truth test through unresolved base k == 'abs'"),
        ('_expr', "implicit truth test through unresolved base k == 'm'"),
        ('_expr', "implicit truth test through unresolved base k == 'v'"),
        ('_git',
         "implicit attribute read through unresolved base subprocess.run(['git', '-C', repo, *args], check=True, capture_output=True)"),
        ('_git', 'implicit iteration through unresolved base args'),
        ('_git', 'implicit truth test through unresolved base binary'),
        ('_ident', 'implicit attribute read through unresolved base st'),
        ('_inside', 'implicit comparison through unresolved base os.path.commonpath([a, b])'),
        ('_is_dir', 'implicit attribute read through unresolved base st'),
        ('_is_file', 'implicit attribute read through unresolved base st'),
        ('_key_pattern', 'implicit binary operator through unresolved base re.escape(words.pop())'),
        ('_key_pattern', 'implicit binary operator through unresolved base unit'),
        ('_key_pattern', 'implicit comparison through unresolved base words[-1]'),
        ('_key_pattern', "implicit iteration through unresolved base re.split('[_\\\\W]+', key)"),
        ('_key_pattern', 'implicit truth test through unresolved base w'),
        ('_keys', 'implicit comparison through unresolved base n'),
        ('_keys', 'implicit iteration through unresolved base names'),
        ('_manifest_body', 'implicit binary operator through unresolved base (len(rows), total)'),
        ('_manifest_body', 'implicit binary operator through unresolved base (m, n, r)'),
        ('_manifest_body', 'implicit binary operator through unresolved base (pin, head)'),
        ('_manifest_body', 'implicit binary operator through unresolved base (title, attester, stamp)'),
        ('_manifest_body', 'implicit binary operator through unresolved base note'),
        ('_manifest_body', 'implicit iteration through unresolved base snap'),
        ('_manifest_body', 'implicit truth test through unresolved base stamp'),
        ('_manifest_lines_of',
         'implicit binary operator through unresolved base (hashlib.sha256(raw).hexdigest(), rel)'),
        ('_manifest_lines_of', 'implicit comparison through unresolved base rel'),
        ('_manifest_lines_of', 'implicit truth test through unresolved base rel != MANIFEST'),
        ('_measure_keys', 'implicit comparison through unresolved base set(node)'),
        ('_measure_keys', 'implicit iteration through unresolved base node'),
        ('_measure_keys', 'implicit iteration through unresolved base node.values()'),
        ('_measure_keys', 'implicit subscript read through unresolved base node'),
        ('_measure_keys', 'implicit subscript read through unresolved base node'),
        ('_measure_keys', "implicit subscript read through unresolved base node['m'].rsplit('.', 1)"),
        ('_measure_keys', "implicit truth test through unresolved base set(node) == {'m'}"),
        ('_measure_keys',
         "implicit truth test through unresolved base set(node) == {'m'} and isinstance(node['m'], str)"),
        ('_merge', 'implicit binary operator through unresolved base a.get(k, 0)'),
        ('_merge', 'implicit iteration through unresolved base b.items()'),
        ('_meta', 'implicit comparison through unresolved base r'),
        ('_meta', 'implicit comparison through unresolved base r'),
        ('_meta', 'implicit comparison through unresolved base r'),
        ('_meta', 'implicit comparison through unresolved base set(r)'),
        ('_meta', 'implicit iteration through unresolved base s'),
        ('_meta', 'implicit iteration through unresolved base show'),
        ('_meta', 'implicit subscript read through unresolved base r'),
        ('_meta', 'implicit subscript read through unresolved base r'),
        ('_meta', 'implicit subscript read through unresolved base r'),
        ('_meta', "implicit truth test through unresolved base set(r) <= RULE_META | {'when', 'sitting'}"),
        ('_num_tokens', 'implicit binary operator through unresolved base t[2:]'),
        ('_num_tokens', 'implicit binary operator through unresolved base v'),
        ('_num_tokens', "implicit hashing through unresolved base '%g' % v"),
        ('_num_tokens', "implicit hashing through unresolved base '-' + t[2:]"),
        ('_num_tokens', 'implicit hashing through unresolved base t[1:]'),
        ('_num_tokens', 'implicit subscript read through unresolved base t'),
        ('_num_tokens', 'implicit subscript read through unresolved base t'),
        ('_num_tokens', 'implicit truth test through unresolved base isinstance(v, float) and v.is_integer()'),
        ('_num_tokens', "implicit truth test through unresolved base t.startswith('-0.')"),
        ('_num_tokens', "implicit truth test through unresolved base t.startswith('0.')"),
        ('_pred', 'implicit comparison through unresolved base set(node)'),
        ('_pred', 'implicit comparison through unresolved base set(node)'),
        ('_pred', 'implicit comparison through unresolved base set(node)'),
        ('_pred', 'implicit comparison through unresolved base set(v)'),
        ('_pred', "implicit iteration through unresolved base _measure_keys(node['args'])"),
        ('_pred', 'implicit iteration through unresolved base node.items()'),
        ('_pred', "implicit iteration through unresolved base node['args'].items()"),
        ('_pred', 'implicit iteration through unresolved base v'),
        ('_pred', 'implicit result disposal through unresolved base _expr(v, keys, group, vals)'),
        ('_pred', "implicit result disposal through unresolved base _pred(node['not'], group, vals)"),
        ('_pred', 'implicit result disposal through unresolved base _pred(x, group, vals)'),
        ('_pred', "implicit result disposal through unresolved base vals.add(v, keys, group, 'predicate argument')"),
        ('_pred', 'implicit subscript read through unresolved base node'),
        ('_pred', 'implicit subscript read through unresolved base node'),
        ('_pred', 'implicit subscript read through unresolved base node'),
        ('_pred', 'implicit subscript read through unresolved base node'),
        ('_pred', "implicit subscript read through unresolved base node['op'].rsplit('.', 1)"),
        ('_pred', 'implicit subscript read through unresolved base v'),
        ('_pred', "implicit truth test through unresolved base _keys(*_measure_keys(node['args']))"),
        ('_pred', "implicit truth test through unresolved base isinstance(v, dict) and set(v) == {'data'}"),
        ('_pred', "implicit truth test through unresolved base set(node) == {'all'}"),
        ('_pred', "implicit truth test through unresolved base set(node) == {'all'} or set(node) == {'any'}"),
        ('_pred', "implicit truth test through unresolved base set(node) == {'not'}"),
        ('_pred', "implicit truth test through unresolved base set(node) == {'op', 'args'}"),
        ('_pred',
         "implicit truth test through unresolved base set(node) == {'op', 'args'} and isinstance(node['op'], str) and isinstance(node['args'], dict)"),
        ('_read_regular', 'implicit binary operator through unresolved base rel'),
        ('_read_regular', 'implicit binary operator through unresolved base rel'),
        ('_read_regular', 'implicit comparison through unresolved base _ident(os.fstat(f.fileno()))'),
        ('_read_regular', 'implicit comparison through unresolved base want[3]'),
        ('_read_regular', 'implicit subscript read through unresolved base want'),
        ('_read_regular', 'implicit truth test through unresolved base _ident(os.fstat(f.fileno())) != want'),
        ('_read_regular', 'implicit truth test through unresolved base len(raw) != want[3]'),
        ('_report_line', 'implicit binary operator through unresolved base (k, found[k])'),
        ('_report_line', "implicit binary operator through unresolved base (label, found['refused'])"),
        ('_report_line',
         "implicit binary operator through unresolved base (label, total, detail, '' if n is None else ' over %d commit(s)' % n, '' if manifest is None else ' manifest ' + manifest, '' if sealed is None else ' seal ' + sealed)"),
        ('_report_line', 'implicit binary operator through unresolved base manifest'),
        ('_report_line', 'implicit binary operator through unresolved base n'),
        ('_report_line', 'implicit binary operator through unresolved base sealed'),
        ('_report_line', 'implicit comparison through unresolved base found'),
        ('_report_line', 'implicit subscript read through unresolved base found'),
        ('_report_line', 'implicit subscript read through unresolved base found'),
        ('_report_line', 'implicit truth test through unresolved base total'),
        ('_revision', 'implicit attribute read through unresolved base type(e)'),
        ('_revision', 'implicit binary operator through unresolved base shipped'),
        ('_revision', "implicit iteration through unresolved base _PLACE.split(r.get('line') or '')"),
        ('_revision', "implicit iteration through unresolved base doc.get('rules') or []"),
        ('_revision', 'implicit iteration through unresolved base shipped'),
        ('_revision', 'implicit iteration through unresolved base shipped + sorted(_data_refs(doc))'),
        ('_revision', "implicit result disposal through unresolved base out['data'].add(dn)"),
        ('_revision', "implicit result disposal through unresolved base out['data'].add(stem)"),
        ('_revision', "implicit result disposal through unresolved base out['nonce'].add(doc['nonce'])"),
        ('_revision', "implicit result disposal through unresolved base out['rule_id'].add(r['id'])"),
        ('_revision', "implicit result disposal through unresolved base out['wording'].add(frags)"),
        ('_revision', "implicit subscript read through unresolved base dn.rsplit('.', 1)"),
        ('_revision', 'implicit subscript read through unresolved base doc'),
        ('_revision', 'implicit subscript read through unresolved base doc'),
        ('_revision', 'implicit subscript read through unresolved base out'),
        ('_revision', 'implicit subscript read through unresolved base out'),
        ('_revision', 'implicit subscript read through unresolved base out'),
        ('_revision', 'implicit subscript read through unresolved base out'),
        ('_revision', 'implicit subscript read through unresolved base out'),
        ('_revision', 'implicit subscript read through unresolved base r'),
        ('_revision', 'implicit truth test through unresolved base _is_dir(ddir)'),
        ('_revision', "implicit truth test through unresolved base dn.endswith('.json')"),
        ('_revision', "implicit truth test through unresolved base doc.get('rules')"),
        ('_revision',
         'implicit truth test through unresolved base frags and sum((len(f) for f in frags)) >= WORDING_MIN'),
        ('_revision',
         "implicit truth test through unresolved base isinstance(doc.get('nonce'), str) and doc['nonce']"),
        ('_revision', "implicit truth test through unresolved base r.get('line')"),
        ('_rx', 'implicit comparison through unresolved base p'),
        ('_rx', 'implicit subscript read through unresolved base _RX'),
        ('_sequence', 'implicit comparison through unresolved base frags'),
        ('_sequence', 'implicit iteration through unresolved base frags'),
        ('_sequence', 'implicit subscript read through unresolved base _SEQ'),
        ('_sitting', 'implicit comparison through unresolved base set(node)'),
        ('_sitting', 'implicit comparison through unresolved base v'),
        ('_sitting', 'implicit comparison through unresolved base x'),
        ('_sitting', "implicit iteration through unresolved base node['args'].items()"),
        ('_sitting', 'implicit iteration through unresolved base v'),
        ('_sitting',
         "implicit result disposal through unresolved base vals.add(v, _keys(name) or _keys(tail), group, 'sitting argument')"),
        ('_sitting', 'implicit subscript read through unresolved base node'),
        ('_sitting', 'implicit subscript read through unresolved base node'),
        ('_sitting', 'implicit subscript read through unresolved base node'),
        ('_sitting', 'implicit subscript read through unresolved base node'),
        ('_sitting', "implicit subscript read through unresolved base node['op'].rsplit('.', 1)"),
        ('_sitting', 'implicit truth test through unresolved base _keys(name)'),
        ('_sitting',
         'implicit truth test through unresolved base isinstance(v, list) and v and all((isinstance(x, str) and x in names for x in v))'),
        ('_sitting',
         "implicit truth test through unresolved base not isinstance(node, dict) or set(node) != {'op', 'args'} or (not isinstance(node['op'], str)) or (not isinstance(node['args'], dict))"),
        ('_sitting', "implicit truth test through unresolved base set(node) != {'op', 'args'}"),
        ('_sitting', 'implicit truth test through unresolved base v'),
        ('_status', 'implicit attribute read through unresolved base type(e)'),
        ('_status', 'implicit truth test through unresolved base follow'),
        ('_table', 'implicit iteration through unresolved base node'),
        ('_table', 'implicit iteration through unresolved base node'),
        ('_table', 'implicit iteration through unresolved base node.items()'),
        ('_table', 'implicit result disposal through unresolved base _table(v, _keys(k) or keys, group, vals)'),
        ('_table', 'implicit result disposal through unresolved base _table(x, keys, group, vals)'),
        ('_table',
         "implicit result disposal through unresolved base vals.add(flat, keys, group, 'data table value')"),
        ('_table', "implicit result disposal through unresolved base vals.add(k, keys, group, 'data table key')"),
        ('_table',
         "implicit result disposal through unresolved base vals.add(node, keys, group, 'data table value')"),
        ('_table', 'implicit truth test through unresolved base _keys(k)'),
        ('_text_lines', 'implicit iteration through unresolved base text.splitlines()'),
        ('_text_lines', 'implicit truth test through unresolved base ln.strip()'),
        ('_text_value', 'implicit comparison through unresolved base tok'),
        ('_text_value', 'implicit truth test through unresolved base _TEXT_NUM.fullmatch(tok)'),
        ('_value_items', 'implicit attribute read through unresolved base vals'),
        ('_value_items', 'implicit binary operator through unresolved base name'),
        ('_value_items', 'implicit comparison through unresolved base ln.strip()'),
        ('_value_items', 'implicit comparison through unresolved base r'),
        ('_value_items', 'implicit comparison through unresolved base r'),
        ('_value_items', 'implicit comparison through unresolved base set(doc)'),
        ('_value_items', 'implicit iteration through unresolved base _TEXT_SPLIT.split(ln)'),
        ('_value_items', 'implicit iteration through unresolved base _text_lines(table)'),
        ('_value_items', 'implicit iteration through unresolved base params.items()'),
        ('_value_items', 'implicit iteration through unresolved base ps.items()'),
        ('_value_items', 'implicit iteration through unresolved base rules'),
        ('_value_items', 'implicit iteration through unresolved base vocab'),
        ('_value_items', 'implicit iteration through unresolved base vocab'),
        ('_value_items', 'implicit result disposal through unresolved base _meta(r)'),
        ('_value_items', "implicit result disposal through unresolved base _pred(r['when'], group, vals)"),
        ('_value_items',
         "implicit result disposal through unresolved base _sitting(r['sitting'], names, group, vals)"),
        ('_value_items', 'implicit result disposal through unresolved base _table(table, keys, group, vals)'),
        ('_value_items',
         "implicit result disposal through unresolved base _table(v, _keys(name, name.rsplit('.', 1)[-1]), 'vocabulary', vals)"),
        ('_value_items', "implicit subscript read through unresolved base name.rsplit('.', 1)"),
        ('_value_items', "implicit subscript read through unresolved base name.rsplit('.', 1)"),
        ('_value_items', 'implicit subscript read through unresolved base r'),
        ('_value_items', 'implicit subscript read through unresolved base r'),
        ('_value_items', "implicit subscript read through unresolved base str(fam).rsplit('.', 1)"),
        ('_value_items', 'implicit truth test through unresolved base _keys(k)'),
        ('_value_items', 'implicit truth test through unresolved base _keys(stem)'),
        ('_value_items', "implicit truth test through unresolved base doc.get('measure_params')"),
        ('_value_items', "implicit truth test through unresolved base doc.get('rules')"),
        ('_value_items', 'implicit truth test through unresolved base ln.strip() != ln'),
        ('_value_items', 'implicit truth test through unresolved base set(doc) <= TOP_KEYS'),
        ('_value_items', 'implicit truth test through unresolved base t'),
        ('_value_items', 'implicit truth test through unresolved base tables'),
        ('_value_needles', 'implicit binary operator through unresolved base (_CMP, val)'),
        ('_value_needles', 'implicit binary operator through unresolved base (kp, VALUE_NEAR, val)'),
        ('_value_needles', 'implicit binary operator through unresolved base (one, one)'),
        ('_value_needles', 'implicit binary operator through unresolved base (val, VALUE_NEAR, kp)'),
        ('_value_needles', 'implicit binary operator through unresolved base (val, _SIGN)'),
        ('_value_needles', 'implicit binary operator through unresolved base (x, y)'),
        ('_value_needles', 'implicit binary operator through unresolved base val'),
        ('_value_needles', 'implicit binary operator through unresolved base val'),
        ('_value_needles', 'implicit binary operator through unresolved base val'),
        ('_value_needles', 'implicit comparison through unresolved base t'),
        ('_value_needles', "implicit hashing through unresolved base ('re', p)"),
        ('_value_needles', 'implicit iteration through unresolved base _num_tokens(v)'),
        ('_value_needles', 'implicit iteration through unresolved base _num_tokens(x)'),
        ('_value_needles', 'implicit iteration through unresolved base _value_items(doc, tables)'),
        ('_value_needles', 'implicit iteration through unresolved base items'),
        ('_value_needles', 'implicit iteration through unresolved base keys'),
        ('_value_needles', 'implicit iteration through unresolved base keys'),
        ('_value_needles', 'implicit iteration through unresolved base keys'),
        ('_value_needles', 'implicit iteration through unresolved base lists'),
        ('_value_needles', 'implicit iteration through unresolved base members'),
        ('_value_needles', 'implicit iteration through unresolved base zip(alts, alts[1:])'),
        ('_value_needles',
         "implicit result disposal through unresolved base by_group.setdefault(group, set()).add('|'.join((re.escape(x) for x in _num_tokens(v))))"),
        ('_value_needles', 'implicit subscript read through unresolved base alts'),
        ('_value_needles', 'implicit subscript read through unresolved base t'),
        ('_value_needles', 'implicit truth test through unresolved base kp'),
        ('_value_needles', "implicit truth test through unresolved base t == 'string'"),
        ('_value_rx', 'implicit binary operator through unresolved base re.escape(v)'),
        ('_value_rx', 'implicit comparison through unresolved base t'),
        ('_value_rx', 'implicit comparison through unresolved base t'),
        ('_value_rx', 'implicit comparison through unresolved base t'),
        ('_value_rx', 'implicit comparison through unresolved base v'),
        ('_value_rx', 'implicit iteration through unresolved base _num_tokens(v)'),
        ('_value_rx', "implicit truth test through unresolved base t == 'bool'"),
        ('_value_rx', "implicit truth test through unresolved base t == 'null'"),
        ('_value_rx', 'implicit truth test through unresolved base v'),
        ('_value_rx', "implicit truth test through unresolved base v == ''"),
        ('corpus_digest', 'implicit binary operator through unresolved base (name, size, digest)'),
        ('corpus_digest', 'implicit iteration through unresolved base rows'),
        ('corpus_digest',
         "implicit result disposal through unresolved base h.update(('%s\\t%d\\t%s\\n' % (name, size, digest)).encode('utf-8'))"),
        ('count', 'implicit comparison through unresolved base cls'),
        ('count', 'implicit comparison through unresolved base cls'),
        ('count', 'implicit comparison through unresolved base s'),
        ('count', 'implicit iteration through unresolved base items'),
        ('count', 'implicit iteration through unresolved base needles.items()'),
        ('count', 'implicit subscript read through unresolved base s'),
        ('count', "implicit truth test through unresolved base cls == 'value'"),
        ('count', 'implicit truth test through unresolved base paths_only'),
        ('count', "implicit truth test through unresolved base paths_only and cls not in ('basename', 'value')"),
        ('count', 'implicit truth test through unresolved base s'),
        ('count',
         "implicit truth test through unresolved base s and (_rx(s[1]).search(public_cut) if cls == 'value' else _sequence(s).search(text) if isinstance(s, tuple) else s in text)"),
        ('derive', 'implicit attribute read through unresolved base type(e)'),
        ('leaf_type', 'implicit attribute read through unresolved base type(v)'),
        ('leaf_type', 'implicit binary operator through unresolved base type(v).__name__'),
        ('leaf_type', 'implicit comparison through unresolved base abs(v)'),
        ('leaf_type', 'implicit truth test through unresolved base _finite(v)'),
        ('leaf_type', 'implicit truth test through unresolved base abs(v) >= VALUE_MIN_BARE'),
        ('leaf_type', 'implicit truth test through unresolved base v.is_integer()'),
        ('main', 'implicit attribute read through unresolved base type(e)'),
        ('main', 'implicit attribute read through unresolved base type(e)'),
        ('main', 'implicit binary operator through unresolved base e'),
        ('main',
         'implicit binary operator through unresolved base e if isinstance(e, NoVerdict) else type(e).__name__'),
        ('main',
         'implicit binary operator through unresolved base e if isinstance(e, NoVerdict) else type(e).__name__'),
        ('main', 'implicit comparison through unresolved base argv[0]'),
        ('main', "implicit subscript read through unresolved base __doc__.split('Modes:')"),
        ('main', "implicit subscript read through unresolved base __doc__.split('Modes:')[1].split('Exit 0')"),
        ('main', 'implicit subscript read through unresolved base argv'),
        ('main', 'implicit subscript read through unresolved base argv'),
        ('main', 'implicit subscript read through unresolved base argv'),
        ('main', 'implicit truth test through unresolved base argv'),
        ('main', "implicit truth test through unresolved base argv[0] == 'seal-verify'"),
        ('main', "implicit truth test through unresolved base argv[0] == 'seal-verify' and len(argv) == 3"),
        ('main', 'implicit truth test through unresolved base store'),
        ('packet', 'implicit binary operator through unresolved base (commit, p)'),
        ('packet', 'implicit binary operator through unresolved base (commit, p)'),
        ('packet', 'implicit binary operator through unresolved base got'),
        ('packet', 'implicit binary operator through unresolved base name'),
        ('packet', 'implicit binary operator through unresolved base snap'),
        ('packet', 'implicit comparison through unresolved base [rel for rel, _raw in snap]'),
        ('packet',
         "implicit comparison through unresolved base hashlib.sha1(b'blob %d\\x00' % len(got) + got).hexdigest()"),
        ('packet', 'implicit comparison through unresolved base hashlib.sha256(got).hexdigest()'),
        ('packet', 'implicit comparison through unresolved base hashlib.sha256(raw).hexdigest()'),
        ('packet', 'implicit comparison through unresolved base kind'),
        ('packet', 'implicit comparison through unresolved base kind'),
        ('packet', 'implicit comparison through unresolved base p'),
        ('packet', "implicit comparison through unresolved base p.split('/')"),
        ('packet', 'implicit comparison through unresolved base parts[0]'),
        ('packet', 'implicit comparison through unresolved base paths'),
        ('packet', 'implicit comparison through unresolved base {os.path.basename(d) for d, _h in docs}'),
        ('packet', 'implicit hashing through unresolved base os.path.basename(d)'),
        ('packet', 'implicit hashing through unresolved base os.path.basename(d)'),
        ('packet', 'implicit iteration through unresolved base f'),
        ('packet', "implicit iteration through unresolved base p.split('/')"),
        ('packet', 'implicit iteration through unresolved base pins[rel]'),
        ('packet', 'implicit iteration through unresolved base snap'),
        ('packet', 'implicit iteration through unresolved base snap'),
        ('packet', 'implicit subscript read through unresolved base parts'),
        ('packet', 'implicit subscript read through unresolved base parts'),
        ('packet', 'implicit subscript read through unresolved base parts'),
        ('packet', 'implicit subscript read through unresolved base parts'),
        ('packet', 'implicit subscript read through unresolved base pins'),
        ('packet', 'implicit truth test through unresolved base _present(out_dir) and os.listdir(out_dir)'),
        ('packet', 'implicit truth test through unresolved base hashlib.sha256(raw).hexdigest() != want'),
        ('packet', "implicit truth test through unresolved base kind == 'blob'"),
        ('packet',
         "implicit truth test through unresolved base kind == 'blob' and hashlib.sha1(b'blob %d\\x00' % len(got) + got).hexdigest() != want"),
        ('packet', "implicit truth test through unresolved base kind == 'doc'"),
        ('packet',
         "implicit truth test through unresolved base kind == 'doc' and hashlib.sha256(got).hexdigest() != want"),
        ('packet',
         'implicit truth test through unresolved base len(snap) != len(paths) + len(docs) or [rel for rel, _raw in snap] != sorted(pins)'),
        ('packet', "implicit truth test through unresolved base ln.startswith('#')"),
        ('packet', 'implicit truth test through unresolved base ln.strip()'),
        ('packet', "implicit truth test through unresolved base ln.strip() and (not ln.startswith('#'))"),
        ('packet', 'implicit truth test through unresolved base os.path.isabs(parts[1])'),
        ('packet',
         "implicit truth test through unresolved base p not in tracked or p.startswith('/') or '..' in p.split('/') or p.startswith('docs/')"),
        ('packet', "implicit truth test through unresolved base p.startswith('/')"),
        ('packet', "implicit truth test through unresolved base parts[0] == 'doc'"),
        ('packet', "implicit truth test through unresolved base re.fullmatch('[0-9a-f]{64}', parts[2])"),
        ('packet_verify', 'implicit comparison through unresolved base _manifest_lines_of(snap)'),
        ('packet_verify', 'implicit comparison through unresolved base hashlib.sha256(raw).hexdigest()'),
        ('packet_verify',
         "implicit truth test through unresolved base _manifest_lines_of(snap) != raw.decode('utf-8', 'replace').splitlines()"),
        ('packet_verify', 'implicit truth test through unresolved base hashlib.sha256(raw).hexdigest() != want'),
        ('report', 'implicit iteration through unresolved base _report_line(label, found, n)'),
        ('scan_range', 'implicit binary operator through unresolved base (base, tip)'),
        ('scan_range', 'implicit comparison through unresolved base set(blob)'),
        ('scan_range', 'implicit iteration through unresolved base commits'),
        ('scan_range',
         "implicit result disposal through unresolved base _merge(found, count(_blob_text(_git(repo, 'cat-file', 'blob', blob, binary=True)), needles))"),
        ('scan_range',
         "implicit result disposal through unresolved base _merge(found, count(_git(repo, 'show', '-s', '--format=%an%n%ae%n%cn%n%ce%n%B', c), needles))"),
        ('scan_range',
         'implicit result disposal through unresolved base _merge(found, count(path, needles, paths_only=True))'),
        ('scan_range', 'implicit subscript read through unresolved base parts'),
        ('scan_range', 'implicit subscript read through unresolved base tree'),
        ('scan_range', 'implicit truth test through unresolved base meta'),
        ('scan_range', "implicit truth test through unresolved base status.startswith('D')"),
        ('scan_range', "implicit truth test through unresolved base status.startswith('D') or set(blob) == {'0'}"),
        ('scan_snapshot', 'implicit iteration through unresolved base snap'),
        ('scan_snapshot',
         'implicit result disposal through unresolved base _merge(found, count(_blob_text(raw), needles))'),
        ('scan_snapshot',
         'implicit result disposal through unresolved base _merge(found, count(rel, needles, paths_only=True))'),
        ('scan_staged', 'implicit binary operator through unresolved base p'),
        ('scan_staged',
         "implicit iteration through unresolved base _git(repo, 'diff', '--cached', '--name-only', '-z').split('\\x00')"),
        ('scan_staged',
         "implicit iteration through unresolved base _git(repo, 'diff', '--cached', '--name-only', '-z', '--diff-filter=d').split('\\x00')"),
        ('scan_staged',
         "implicit result disposal through unresolved base _merge(found, count(_blob_text(_git(repo, 'show', ':' + p, binary=True)), needles))"),
        ('scan_staged',
         'implicit result disposal through unresolved base _merge(found, count(p, needles, paths_only=True))'),
        ('scan_staged', 'implicit truth test through unresolved base p'),
        ('scan_staged', 'implicit truth test through unresolved base p'),
        ('seal', 'implicit binary operator through unresolved base (d, n, name)'),
        ('seal', 'implicit binary operator through unresolved base digest'),
        ('seal', 'implicit binary operator through unresolved base line'),
        ('seal', 'implicit binary operator through unresolved base snap'),
        ('seal', "implicit iteration through unresolved base _report_line('seal', dict(found))"),
        ('seal', 'implicit iteration through unresolved base rows'),
        ('seal', 'implicit truth test through unresolved base _inside(seal_file, ri)'),
        ('seal_verify', 'implicit binary operator through unresolved base set(cur)'),
        ('seal_verify', 'implicit binary operator through unresolved base set(was)'),
        ('seal_verify', 'implicit comparison through unresolved base corpus_digest(sealed)'),
        ('seal_verify', 'implicit comparison through unresolved base cur[k]'),
        ('seal_verify', 'implicit comparison through unresolved base int(lines[2].split()[1])'),
        ('seal_verify', 'implicit hashing through unresolved base r[0]'),
        ('seal_verify', 'implicit iteration through unresolved base lines[3:]'),
        ('seal_verify', "implicit iteration through unresolved base ln.split(' ', 2)"),
        ('seal_verify', 'implicit iteration through unresolved base now'),
        ('seal_verify', 'implicit subscript read through unresolved base cur'),
        ('seal_verify', 'implicit subscript read through unresolved base lines'),
        ('seal_verify', 'implicit subscript read through unresolved base lines'),
        ('seal_verify', 'implicit subscript read through unresolved base lines'),
        ('seal_verify', 'implicit subscript read through unresolved base lines[0].split()'),
        ('seal_verify', 'implicit subscript read through unresolved base lines[2].split()'),
        ('seal_verify', 'implicit subscript read through unresolved base r'),
        ('seal_verify', 'implicit subscript read through unresolved base was'),
        ('seal_verify', 'implicit truth test through unresolved base len(sealed) != int(lines[2].split()[1])'),
        ('seal_verify',
         'implicit truth test through unresolved base len(sealed) != int(lines[2].split()[1]) or corpus_digest(sealed) != lines[0].split()[1]'),
        ('seal_verify', "implicit truth test through unresolved base lines[0].startswith('SEAL ')"),
        ('seal_verify', "implicit truth test through unresolved base lines[2].startswith('FILES ')"),
        ('seal_verify', 'implicit truth test through unresolved base set(cur) - set(was)'),
        ('seal_verify', 'implicit truth test through unresolved base set(was) - set(cur)'),
        ('snapshot', 'implicit binary operator through unresolved base moved[0]'),
        ('snapshot', 'implicit binary operator through unresolved base set(again)'),
        ('snapshot', 'implicit comparison through unresolved base again'),
        ('snapshot', 'implicit comparison through unresolved base again[k]'),
        ('snapshot', 'implicit comparison through unresolved base listed[rel][0]'),
        ('snapshot', 'implicit comparison through unresolved base rel'),
        ('snapshot', 'implicit iteration through unresolved base listed'),
        ('snapshot', "implicit iteration through unresolved base rel.split('/')"),
        ('snapshot', 'implicit subscript read through unresolved base again'),
        ('snapshot', 'implicit subscript read through unresolved base listed'),
        ('snapshot', 'implicit subscript read through unresolved base listed'),
        ('snapshot', 'implicit subscript read through unresolved base listed'),
        ('snapshot', 'implicit subscript read through unresolved base listed[rel]'),
        ('snapshot', 'implicit subscript read through unresolved base moved'),
        ('snapshot', 'implicit truth test through unresolved base again != listed'),
        ('snapshot', 'implicit truth test through unresolved base again[k] != listed[k]'),
        ('snapshot', 'implicit truth test through unresolved base listed[rel][0] == stat.S_IFREG'),
        ('snapshot',
         'implicit truth test through unresolved base listed[rel][0] == stat.S_IFREG and rel not in skip'),
        ('snapshot_rows', 'implicit iteration through unresolved base snap'),
    ],
    "backend/api/review_rules.py": [
        ('<module>',
         "call of protocol-running callable print through unresolved base __doc__.split('Command line')[1].strip()"),
        ('<module>',
         "call of protocol-running callable re.compile through unresolved base '[a-z_]\\\\w{0,%d}' % (rm.CONTRACT_BOUNDS['label_max'] * PAIR)"),
        ('<module>',
         "call of protocol-running callable re.compile through unresolved base '[a-z_]{1,%d}' % rm.CONTRACT_BOUNDS['label_max']"),
        ('<module>', "unproven pure method call strip through unresolved base __doc__.split('Command line')[1]"),
        ('Refused.__init__', 'attribute store through unresolved base self'),
        ('Ruleset.__init__', 'attribute store through unresolved base self'),
        ('Ruleset.__init__', 'attribute store through unresolved base self'),
        ('Ruleset.__init__', 'attribute store through unresolved base self'),
        ('Ruleset.__init__', 'attribute store through unresolved base self'),
        ('Ruleset.__init__', 'attribute store through unresolved base self'),
        ('Ruleset.__init__', 'attribute store through unresolved base self'),
        ('Ruleset.__init__', 'attribute store through unresolved base self'),
        ('Ruleset.__init__', 'attribute store through unresolved base self'),
        ('Ruleset.__init__', 'attribute store through unresolved base self'),
        ('Ruleset.__init__', 'attribute store through unresolved base self'),
        ('Ruleset.evaluate_game',
         "call of unresolved callable self.core['core.game'].impl[0] through unresolved base self"),
        ('Ruleset.horizon_days', 'call of protocol-running callable max through unresolved base days'),
        ('Ruleset.render_line',
         "call of unresolved callable self.core['core.render'].impl[0] through unresolved base rule"),
        ('Ruleset.run_selftest',
         "call of unresolved callable self.core['core.game'].impl[-1] through unresolved base self"),
        ('Ruleset.run_sitting_selftest',
         "call of unresolved callable self.core['core.sitting'].impl[-1] through unresolved base self"),
        ('Ruleset.sitting_items',
         "call of unresolved callable self.core['core.sitting'].impl[0] through unresolved base rule"),
        ('Ruleset.sitting_statement',
         "call of unresolved callable self.core['core.sitting'].impl[1] through unresolved base rule"),
        ('State.__init__', 'attribute store through unresolved base self'),
        ('State.__init__', 'attribute store through unresolved base self'),
        ('State.__init__', 'attribute store through unresolved base self'),
        ('_Binder.__call__', 'call of protocol-running callable isinstance through unresolved base kind'),
        ('_Binder.__call__', 'call of protocol-running callable isinstance through unresolved base name'),
        ('_Binder.__call__', 'call of protocol-running callable rm.REGISTRY.get through unresolved base name'),
        ('_Binder.__call__', 'call of unlisted callable rm.REGISTRY.get through unresolved base name'),
        ('_Binder.__call__', 'subscript store through unresolved base self.kinds'),
        ('_Binder.__call__', 'subscript store through unresolved base self.used'),
        ('_Binder.__init__', 'attribute store through unresolved base self'),
        ('_Binder.__init__', 'attribute store through unresolved base self'),
        ('_Binder.__init__', 'attribute store through unresolved base self'),
        ('_Binder.__init__', 'attribute store through unresolved base self'),
        ('_Budget.__init__', 'attribute store through unresolved base self'),
        ('_Budget.tick', 'augmented attribute store -= through unresolved base self'),
        ('_canon', 'call of protocol-running callable json.dumps through unresolved base obj'),
        ('_canon',
         "unproven pure method call encode through unresolved base json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True)"),
        ('_closure_names',
         "call of protocol-running callable all through unresolved base (isinstance(n, str) and _CODE_NAME.fullmatch(n) for n in closure['code'])"),
        ('_closure_names', 'call of protocol-running callable isinstance through unresolved base closure'),
        ('_closure_names', "call of protocol-running callable isinstance through unresolved base closure['code']"),
        ('_closure_names', "call of protocol-running callable isinstance through unresolved base closure['fp']"),
        ('_closure_names', 'call of protocol-running callable isinstance through unresolved base n'),
        ('_closure_names', "call of protocol-running callable len through unresolved base closure['code']"),
        ('_closure_names', "call of protocol-running callable len through unresolved base closure['fp']"),
        ('_closure_names', 'call of protocol-running callable set through unresolved base closure'),
        ('_closure_names', "call of protocol-running callable set through unresolved base closure['code']"),
        ('_closure_names', "call of protocol-running callable set through unresolved base closure['code']"),
        ('_closure_names', "call of protocol-running callable sorted through unresolved base set(closure['code'])"),
        ('_closure_names', 'unproven pure method call fullmatch through unresolved base _CODE_NAME'),
        ('_closure_names', 'unproven pure method call fullmatch through unresolved base _HEX'),
        ('_code_files', 'call of protocol-running callable len through unresolved base raw'),
        ('_code_files', 'call of protocol-running callable open through unresolved base path'),
        ('_code_files', 'call of protocol-running callable os.path.abspath through unresolved base rb.__file__'),
        ('_code_files', 'call of protocol-running callable os.path.basename through unresolved base rb.__file__'),
        ('_code_files', 'call of protocol-running callable os.path.join through unresolved base api_dir'),
        ('_code_files', 'call of protocol-running callable os.path.splitext through unresolved base name'),
        ('_code_files', 'call of protocol-running callable rb.LOADED.get through unresolved base stem'),
        ('_code_files', 'call of protocol-running callable sys.modules.get through unresolved base stem'),
        ('_code_files', 'call of unlisted callable rb.LOADED.get through unresolved base stem'),
        ('_code_files', 'call of unlisted callable sys.modules.get through unresolved base stem'),
        ('_code_files', 'unproven pure method call replace through unresolved base raw'),
        ('_compile_expr',
         'call of protocol-running callable all through unresolved base (_finite(x) or isinstance(x, str) for x in v)'),
        ('_compile_expr', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_compile_expr', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_compile_expr', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_compile_expr', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_compile_expr', 'call of protocol-running callable isinstance through unresolved base x'),
        ('_compile_expr', 'call of protocol-running callable len through unresolved base node'),
        ('_compile_expr', 'call of protocol-running callable len through unresolved base v'),
        ('_compile_expr', 'call of unresolved callable bind through unresolved base e.family'),
        ('_compile_expr', 'call of unresolved callable bind through unresolved base v'),
        ('_compile_expr', 'unproven pure method call items through unresolved base node'),
        ('_compile_pred',
         'call of protocol-running callable all through unresolved base (_finite(x) or isinstance(x, str) for x in v)'),
        ('_compile_pred', 'call of protocol-running callable isinstance through unresolved base args'),
        ('_compile_pred', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_compile_pred', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_compile_pred', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_compile_pred', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_compile_pred', 'call of protocol-running callable isinstance through unresolved base x'),
        ('_compile_pred', 'call of protocol-running callable set through unresolved base args'),
        ('_compile_pred', 'call of protocol-running callable set through unresolved base node'),
        ('_compile_pred', 'call of protocol-running callable set through unresolved base node'),
        ('_compile_pred', 'call of protocol-running callable set through unresolved base node'),
        ('_compile_pred', 'call of protocol-running callable set through unresolved base v'),
        ('_compile_pred', "call of unresolved callable bind through unresolved base node['op']"),
        ('_compile_pred', 'unproven pure method call items through unresolved base node'),
        ('_compile_sitting', 'call of protocol-running callable all through unresolved base (_finite(x) for x in v)'),
        ('_compile_sitting', 'call of protocol-running callable isinstance through unresolved base args'),
        ('_compile_sitting', 'call of protocol-running callable isinstance through unresolved base node'),
        ('_compile_sitting', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_compile_sitting', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_compile_sitting', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_compile_sitting', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_compile_sitting', 'call of protocol-running callable len through unresolved base v'),
        ('_compile_sitting', 'call of protocol-running callable len through unresolved base v'),
        ('_compile_sitting', 'call of protocol-running callable set through unresolved base args'),
        ('_compile_sitting', 'call of protocol-running callable set through unresolved base node'),
        ('_compile_sitting', 'call of protocol-running callable set through unresolved base v'),
        ('_compile_sitting', 'call of protocol-running callable sorted through unresolved base v'),
        ('_compile_sitting', 'call of unresolved callable entry.impl[0] through unresolved base out'),
        ('_compile_sitting', 'unproven pure method call fullmatch through unresolved base _STRATA'),
        ('_compile_sitting.bind', 'call of unresolved callable bind0 through unresolved base name'),
        ('_compile_template', 'call of protocol-running callable bool through unresolved base none'),
        ('_compile_template', 'call of protocol-running callable int through unresolved base places'),
        ('_compile_template', 'call of protocol-running callable isinstance through unresolved base line'),
        ('_compile_template', 'call of protocol-running callable len through unresolved base line'),
        ('_compile_template', 'method call end through unresolved base m'),
        ('_compile_template', 'method call groups through unresolved base m'),
        ('_compile_template', 'method call start through unresolved base m'),
        ('_compile_template', 'unproven pure method call finditer through unresolved base _PLACE'),
        ('_entries', 'call of protocol-running callable len through unresolved base plan'),
        ('_entries', 'call of protocol-running callable os.path.join through unresolved base path'),
        ('_entries', 'call of protocol-running callable os.scandir through unresolved base path'),
        ('_exists', 'call of protocol-running callable os.lstat through unresolved base path'),
        ('_finite', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_finite', 'call of protocol-running callable math.isfinite through unresolved base v'),
        ('_framed', 'call of protocol-running callable len through unresolved base c'),
        ('_framed', 'call of protocol-running callable len through unresolved base files'),
        ('_framed', 'call of protocol-running callable len through unresolved base p'),
        ('_framed', 'call of protocol-running callable sorted through unresolved base files'),
        ('_framed', 'method call update through unresolved base h'),
        ('_framed', 'method call update through unresolved base h'),
        ('_framed', 'method call update through unresolved base h'),
        ('_framed', 'method call update through unresolved base h'),
        ('_framed', 'method call update through unresolved base h'),
        ('_framed', 'method call update through unresolved base h'),
        ('_framed', 'unproven pure method call encode through unresolved base path'),
        ('_framed', 'unproven pure method call hexdigest through unresolved base h'),
        ('_inventory', 'call of protocol-running callable os.lstat through unresolved base dp'),
        ('_inventory', 'call of protocol-running callable os.lstat through unresolved base path'),
        ('_inventory', 'call of protocol-running callable os.lstat through unresolved base rdir'),
        ('_inventory', 'call of protocol-running callable plan.sort through unresolved base plan'),
        ('_inventory', 'call of protocol-running callable stat.S_ISDIR through unresolved base s.st_mode'),
        ('_inventory', 'call of protocol-running callable stat.S_ISDIR through unresolved base st.st_mode'),
        ('_inventory', 'call of protocol-running callable stat.S_ISLNK through unresolved base ds.st_mode'),
        ('_inventory', 'call of protocol-running callable stat.S_ISLNK through unresolved base s.st_mode'),
        ('_inventory', 'call of protocol-running callable stat.S_ISLNK through unresolved base st.st_mode'),
        ('_inventory', 'call of protocol-running callable stat.S_ISREG through unresolved base ds.st_mode'),
        ('_inventory', 'call of protocol-running callable stat.S_ISREG through unresolved base s.st_mode'),
        ('_inventory', 'call of protocol-running callable sum through unresolved base (p[2] for p in plan)'),
        ('_inventory',
         "call of protocol-running callable {'rules.json': _BOUNDS['rules_bytes_max'], 'selftest.json': _BOUNDS['selftest_bytes_max']}.get through unresolved base name"),
        ('_inventory', 'unproven pure method call fullmatch through unresolved base _DATA_NAME'),
        ('_is_dir', 'call of protocol-running callable os.stat through unresolved base path'),
        ('_is_dir', 'call of protocol-running callable stat.S_ISDIR through unresolved base st.st_mode'),
        ('_log', "call of protocol-running callable print through unresolved base '[REVIEW] rules: %s' % state.word"),
        ('_log',
         "call of protocol-running callable print through unresolved base '[REVIEW] rules: refused (%s)' % state.reason"),
        ('_measure_value', 'call of unresolved callable m.impl[0] through unresolved base ctx'),
        ('_measure_value', 'subscript store through unresolved base memo'),
        ('_measure_value', 'unproven pure method call get through unresolved base rs.params'),
        ('_nt_final', 'call of protocol-running callable os.path.abspath through unresolved base path'),
        ('_nt_final', 'call of protocol-running callable os.path.normcase through unresolved base final'),
        ('_nt_final',
         'call of protocol-running callable os.path.normcase through unresolved base os.path.abspath(path)'),
        ('_nt_final', 'unproven pure method call startswith through unresolved base final'),
        ('_open_nofollow', 'call of protocol-running callable msvcrt.open_osfhandle through unresolved base h'),
        ('_open_nofollow', 'call of protocol-running callable os.open through unresolved base path'),
        ('_open_nofollow', 'call of unlisted callable msvcrt.open_osfhandle through unresolved base h'),
        ('_open_nofollow', 'method call CloseHandle through unresolved base _K32'),
        ('_open_nofollow', 'method call CreateFileW through unresolved base _K32'),
        ('_open_nofollow', 'method call GetFinalPathNameByHandleW through unresolved base _K32'),
        ('_parse_time',
         "call of protocol-running callable datetime.fromisoformat through unresolved base v[:-1] if v.endswith('Z') else v"),
        ('_parse_time', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_parse_time', "call of unlisted callable datetime.fromisoformat through unresolved base "
                        "v[:-1] if v.endswith('Z') else v"),
        ('_parse_time', 'unproven pure method call endswith through unresolved base v'),
        ('_parse_time', 'unproven pure method call endswith through unresolved base v'),
        ('_parse_time', 'unproven pure method call replace through unresolved base t'),
        ('_pointer_key',
         'call of protocol-running callable os.lstat through unresolved base os.path.join(base, target)'),
        ('_pointer_key', 'call of protocol-running callable os.path.join through unresolved base base'),
        ('_pointer_target', 'call of protocol-running callable os.lstat through unresolved base p'),
        ('_pointer_target', 'call of protocol-running callable os.path.join through unresolved base base'),
        ('_pointer_target', 'call of protocol-running callable os.readlink through unresolved base p'),
        ('_pointer_target', 'call of protocol-running callable stat.S_ISLNK through unresolved base st.st_mode'),
        ('_pointer_target', 'call of protocol-running callable stat.S_ISREG through unresolved base st.st_mode'),
        ('_pointer_target', 'call of unresolved callable raw.decode through unresolved base raw.decode'),
        ('_pointer_target', 'unproven pure method call fullmatch through unresolved base _REV_DIR'),
        ('_pointer_target', "unproven pure method call strip through unresolved base raw.decode('ascii', 'replace')"),
        ('_provenance', "call of protocol-running callable ','.join through unresolved base elsewhere"),
        ('_provenance',
         'call of protocol-running callable sorted through unresolved base rb.PRIOR | rb.executed_elsewhere()'),
        ('_py', 'call of protocol-running callable float through unresolved base v'),
        ('_py', 'call of protocol-running callable int through unresolved base v'),
        ('_py', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_py', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_py', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_py', 'call of protocol-running callable round through unresolved base v'),
        ('_py', 'call of protocol-running callable str through unresolved base v'),
        ('_py', 'method call to_integral_value through unresolved base v'),
        ('_read_verified', 'augmented assignment -= through unresolved base left'),
        ('_read_verified', "call of protocol-running callable b''.join through unresolved base chunks"),
        ('_read_verified', 'call of protocol-running callable len through unresolved base b'),
        ('_read_verified', 'call of protocol-running callable len through unresolved base data'),
        ('_read_verified', 'call of protocol-running callable os.close through unresolved base fd'),
        ('_read_verified', 'call of protocol-running callable os.fstat through unresolved base fd'),
        ('_read_verified', 'call of protocol-running callable os.read through unresolved base fd'),
        ('_read_verified', 'call of protocol-running callable stat.S_ISREG through unresolved base fs.st_mode'),
        ('_register_core',
         "call of protocol-running callable rm._register through unresolved base rm.Entry('core', 'core.game', (evaluate_game, eval_pred, eval_expr, _measure_value, run_selftest))"),
        ('_register_core',
         "call of protocol-running callable rm._register through unresolved base rm.Entry('core', 'core.render', (render_line, render_item, _render_value))"),
        ('_register_core',
         "call of protocol-running callable rm._register through unresolved base rm.Entry('core', 'core.sitting', (sitting_items, sitting_statement, norm_pair, _py, _bound_lookup, sitting_selftest))"),
        ('_register_core', "call of unlisted callable rm._register through unresolved base rm.Entry('core', "
                           "'core.game', (evaluate_game, eval_pred, eval_expr, _measure_value, run_selftest))"),
        ('_register_core', "call of unlisted callable rm._register through unresolved base rm.Entry('core', "
                           "'core.render', (render_line, render_item, _render_value))"),
        ('_register_core', "call of unlisted callable rm._register through unresolved base rm.Entry('core', "
                           "'core.sitting', (sitting_items, sitting_statement, norm_pair, _py, _bound_lookup, "
                           "sitting_selftest))"),
        ('_render_value',
         "call of protocol-running callable '/'.join through unresolved base (_render_value(x, places) for x in v)"),
        ('_render_value', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_render_value', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_render_value', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_render_value', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_render_value', 'call of protocol-running callable isinstance through unresolved base v'),
        ('_render_value', 'call of protocol-running callable str through unresolved base v'),
        ('_render_value', 'call of protocol-running callable str through unresolved base v'),
        ('_reparse',
         'call of protocol-running callable bool through unresolved base st.st_file_attributes & _REPARSE'),
        ('build_revision', 'call of protocol-running callable dict through unresolved base doc'),
        ('build_revision',
         "call of protocol-running callable f.write through unresolved base '%s\\t%s\\t%s\\t%s\\t\\n' % (rev, datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), parent, reason.replace('\\t', ' ').replace('\\n', ' '))"),
        ('build_revision',
         "call of protocol-running callable f.write through unresolved base (digest + '\\n').encode()"),
        ('build_revision', 'call of protocol-running callable f.write through unresolved base raw'),
        ('build_revision', 'call of protocol-running callable files.update through unresolved base data_files'),
        ('build_revision',
         "call of protocol-running callable json.loads through unresolved base f.read().decode('utf-8')"),
        ('build_revision',
         "call of protocol-running callable json.loads through unresolved base f.read().decode('utf-8')"),
        ('build_revision', 'call of protocol-running callable json.loads through unresolved base text'),
        ('build_revision', 'call of protocol-running callable open through unresolved base log'),
        ('build_revision', 'call of protocol-running callable open through unresolved base log'),
        ('build_revision', 'call of protocol-running callable open through unresolved base os.path.join(ddir, dn)'),
        ('build_revision',
         "call of protocol-running callable open through unresolved base os.path.join(draft, 'rules.json')"),
        ('build_revision',
         "call of protocol-running callable open through unresolved base os.path.join(draft, 'selftest.json')"),
        ('build_revision',
         "call of protocol-running callable open through unresolved base os.path.join(incoming, 'REVISION')"),
        ('build_revision',
         "call of protocol-running callable open through unresolved base os.path.join(incoming, *rel.split('/'))"),
        ('build_revision', 'call of protocol-running callable os.listdir through unresolved base ddir'),
        ('build_revision',
         'call of protocol-running callable os.makedirs through unresolved base os.path.dirname(staged)'),
        ('build_revision',
         "call of protocol-running callable os.makedirs through unresolved base os.path.join(incoming, 'data') if data_files else incoming"),
        ('build_revision', 'call of protocol-running callable os.path.dirname through unresolved base staged'),
        ('build_revision', 'call of protocol-running callable os.path.dirname through unresolved base staged'),
        ('build_revision', 'call of protocol-running callable os.path.join through unresolved base ddir'),
        ('build_revision', 'call of protocol-running callable os.path.join through unresolved base draft'),
        ('build_revision', 'call of protocol-running callable os.path.join through unresolved base draft'),
        ('build_revision', 'call of protocol-running callable os.path.join through unresolved base draft'),
        ('build_revision', 'call of protocol-running callable os.path.join through unresolved base incoming'),
        ('build_revision', 'call of protocol-running callable os.path.join through unresolved base incoming'),
        ('build_revision', 'call of protocol-running callable os.path.join through unresolved base incoming'),
        ('build_revision', 'call of protocol-running callable os.path.join through unresolved base store'),
        ('build_revision', 'call of protocol-running callable os.path.join through unresolved base store'),
        ('build_revision', 'call of protocol-running callable os.path.join through unresolved base store'),
        ('build_revision', 'call of protocol-running callable os.path.join through unresolved base store'),
        ('build_revision', 'call of protocol-running callable os.rename through unresolved base incoming'),
        ('build_revision', 'call of protocol-running callable os.rename through unresolved base staged'),
        ('build_revision',
         'call of protocol-running callable os.rmdir through unresolved base os.path.dirname(staged)'),
        ('build_revision', 'call of protocol-running callable shutil.rmtree through unresolved base incoming'),
        ('build_revision', 'call of protocol-running callable shutil.rmtree through unresolved base staged'),
        ('build_revision', 'call of protocol-running callable sorted through unresolved base binder.used'),
        ('build_revision', 'call of protocol-running callable sorted through unresolved base os.listdir(ddir)'),
        ('build_revision', 'call of unlisted callable shutil.rmtree through unresolved base incoming'),
        ('build_revision', 'call of unlisted callable shutil.rmtree through unresolved base staged'),
        ('build_revision', 'method call strftime through unresolved base datetime.now(timezone.utc)'),
        ('build_revision', 'unproven pure method call decode through unresolved base f.read()'),
        ('build_revision', 'unproven pure method call decode through unresolved base f.read()'),
        ('build_revision', 'unproven pure method call decode through unresolved base raw'),
        ('build_revision', "unproven pure method call encode through unresolved base digest + '\\n'"),
        ('build_revision', 'unproven pure method call replace through unresolved base reason'),
        ('build_revision', "unproven pure method call replace through unresolved base reason.replace('\\t', ' ')"),
        ('build_revision', "unproven pure method call rsplit through unresolved base rel.split('/', 1)[1]"),
        ('build_revision', 'unproven pure method call split through unresolved base lines[-1]'),
        ('build_revision', 'unproven pure method call split through unresolved base rel'),
        ('build_revision', 'unproven pure method call split through unresolved base rel'),
        ('build_revision', 'unproven pure method call splitlines through unresolved base f.read()'),
        ('build_revision', 'unproven pure method call splitlines through unresolved base text'),
        ('build_revision', 'unproven pure method call strip through unresolved base ln'),
        ('build_revision', 'unproven pure method call strip through unresolved base ln'),
        ('cli', 'call of protocol-running callable int through unresolved base days'),
        ('cli', 'call of protocol-running callable len through unresolved base rest'),
        ('cli', 'call of protocol-running callable list through unresolved base argv[1:]'),
        ('cli', "call of protocol-running callable print through unresolved base 'eval: ' + review_eval()"),
        ('cli', "call of protocol-running callable print through unresolved base 'refused (%s)' % e.cls"),
        ('cli', "call of protocol-running callable print through unresolved base 'rev: ' + rs.rev"),
        ('cli', "call of protocol-running callable print through unresolved base 'verdict: refused (%s)' % e.cls"),
        ('cli',
         "call of protocol-running callable print through unresolved base __doc__.split('Command line')[1].strip()"),
        ('cli',
         'call of protocol-running callable print through unresolved base build_revision(draft, store, reason)'),
        ('cli', 'call of protocol-running callable print through unresolved base literal(rdir, rule_id, int(days))'),
        ('cli', "unproven pure method call strip through unresolved base __doc__.split('Command line')[1]"),
        ('closure_fingerprint', 'call of protocol-running callable dict through unresolved base code_files'),
        ('closure_fingerprint',
         "call of protocol-running callable files.update through unresolved base {'revision/' + k: v for k, v in revision_files.items() if k != 'REVISION'}"),
        ('closure_fingerprint', 'unproven pure method call items through unresolved base revision_files'),
        ('compile_rules',
         'call of protocol-running callable all through unresolved base (_finite(x) for x in values.values())'),
        ('compile_rules',
         'call of protocol-running callable all through unresolved base (isinstance(s, list) and len(s) == PAIR and isinstance(s[0], str) and _RULE_LABEL.fullmatch(s[0]) for s in show)'),
        ('compile_rules', 'call of protocol-running callable dict through unresolved base values'),
        ('compile_rules', 'call of protocol-running callable isinstance through unresolved base doc'),
        ('compile_rules', "call of protocol-running callable isinstance through unresolved base doc['vocabulary']"),
        ('compile_rules', 'call of protocol-running callable isinstance through unresolved base nonce'),
        ('compile_rules', 'call of protocol-running callable isinstance through unresolved base params'),
        ('compile_rules', 'call of protocol-running callable isinstance through unresolved base r.id'),
        ('compile_rules', 'call of protocol-running callable isinstance through unresolved base r.post'),
        ('compile_rules', 'call of protocol-running callable isinstance through unresolved base raw'),
        ('compile_rules', 'call of protocol-running callable isinstance through unresolved base rules'),
        ('compile_rules', 'call of protocol-running callable isinstance through unresolved base s'),
        ('compile_rules', 'call of protocol-running callable isinstance through unresolved base s[0]'),
        ('compile_rules', 'call of protocol-running callable isinstance through unresolved base show'),
        ('compile_rules', 'call of protocol-running callable isinstance through unresolved base values'),
        ('compile_rules', 'call of protocol-running callable len through unresolved base nonce'),
        ('compile_rules', 'call of protocol-running callable len through unresolved base rules'),
        ('compile_rules', 'call of protocol-running callable len through unresolved base s'),
        ('compile_rules', 'call of protocol-running callable len through unresolved base show'),
        ('compile_rules', 'call of protocol-running callable len through unresolved base show'),
        ('compile_rules', 'call of protocol-running callable seen.add through unresolved base r.id'),
        ('compile_rules', 'call of protocol-running callable set through unresolved base doc'),
        ('compile_rules', 'call of protocol-running callable set through unresolved base entry.data'),
        ('compile_rules', 'call of protocol-running callable set through unresolved base raw'),
        ('compile_rules', 'call of protocol-running callable set through unresolved base raw'),
        ('compile_rules', 'call of protocol-running callable set through unresolved base rs.params'),
        ('compile_rules', 'call of protocol-running callable set through unresolved base values'),
        ('compile_rules', 'call of unresolved callable bind through unresolved base bind'),
        ('compile_rules', 'call of unresolved callable bind through unresolved base family'),
        ('compile_rules', 'method call append through unresolved base rs.rules'),
        ('compile_rules', 'unproven pure method call fullmatch through unresolved base _HEX'),
        ('compile_rules', 'unproven pure method call fullmatch through unresolved base _RULE_ID'),
        ('compile_rules', 'unproven pure method call fullmatch through unresolved base _RULE_LABEL'),
        ('compile_rules', 'unproven pure method call get through unresolved base raw'),
        ('compile_rules', 'unproven pure method call get through unresolved base raw'),
        ('compile_rules', 'unproven pure method call get through unresolved base raw'),
        ('compile_rules', 'unproven pure method call get through unresolved base raw'),
        ('compile_rules', 'unproven pure method call get through unresolved base raw'),
        ('compile_rules', 'unproven pure method call get through unresolved base raw'),
        ('compile_rules', 'unproven pure method call items through unresolved base bind.kinds'),
        ('compile_rules', 'unproven pure method call items through unresolved base params'),
        ('compile_rules', 'unproven pure method call values through unresolved base values'),
        ('eval_expr', 'call of protocol-running callable abs through unresolved base rm._num(v)'),
        ('eval_expr', 'call of protocol-running callable rm._num through unresolved base a'),
        ('eval_expr', 'call of protocol-running callable rm._num through unresolved base b'),
        ('eval_expr', 'call of protocol-running callable rm._num through unresolved base v'),
        ('eval_expr', 'call of unlisted callable rm._num through unresolved base a'),
        ('eval_expr', 'call of unlisted callable rm._num through unresolved base b'),
        ('eval_expr', 'call of unlisted callable rm._num through unresolved base v'),
        ('eval_pred', 'call of protocol-running callable isinstance through unresolved base out'),
        ('eval_pred', 'call of unresolved callable entry.impl[0] through unresolved base vals'),
        ('eval_pred', 'method call tick through unresolved base budget'),
        ('evaluate_game', 'call of protocol-running callable len through unresolved base records'),
        ('evaluate_game', 'call of protocol-running callable rm.Ctx through unresolved base records'),
        ('evaluate_game', 'call of protocol-running callable rm.Ctx through unresolved base records'),
        ('evaluate_game', 'call of unlisted callable rm.Ctx through unresolved base records'),
        ('evaluate_game', 'call of unlisted callable rm.Ctx through unresolved base records'),
        ('evaluate_game', 'method call render_line through unresolved base rs'),
        ('literal', "call of protocol-running callable ' '.join through unresolved base sql.split()"),
        ('literal', 'call of protocol-running callable int through unresolved base days_back'),
        ('literal', 'call of protocol-running callable isinstance through unresolved base v'),
        ('literal', 'call of protocol-running callable re.escape through unresolved base k'),
        ('literal', "call of protocol-running callable re.sub through unresolved base ':%s\\\\b' % re.escape(k)"),
        ('literal', 'call of protocol-running callable repr through unresolved base v'),
        ('literal', 'call of protocol-running callable sorted through unresolved base binds'),
        ('literal', "call of unlisted callable re.sub through unresolved base ':%s\\\\b' % re.escape(k)"),
        ('literal', 'callback of sorted (protocol-running callable len) through unresolved base binds'),
        ('literal', 'method call rule through unresolved base rs'),
        ('literal', 'method call sitting_statement through unresolved base rs'),
        ('literal', 'unproven pure method call split through unresolved base sql'),
        ('load_dir', 'call of protocol-running callable isinstance through unresolved base binder.vocab'),
        ('load_dir', 'call of protocol-running callable isinstance through unresolved base doc'),
        ('load_dir', 'call of protocol-running callable isinstance through unresolved base n'),
        ('load_dir', 'call of protocol-running callable isinstance through unresolved base selftest'),
        ('load_dir', "call of protocol-running callable isinstance through unresolved base selftest['cases']"),
        ('load_dir',
         "call of protocol-running callable json.loads through unresolved base files['rules.json'].decode('utf-8')"),
        ('load_dir',
         "call of protocol-running callable json.loads through unresolved base files['selftest.json'].decode('utf-8')"),
        ('load_dir', 'call of protocol-running callable json.loads through unresolved base text'),
        ('load_dir', 'call of protocol-running callable len through unresolved base code'),
        ('load_dir', 'call of protocol-running callable len through unresolved base files'),
        ('load_dir', "call of protocol-running callable len through unresolved base selftest['cases']"),
        ('load_dir', 'call of protocol-running callable list through unresolved base binder.vocab'),
        ('load_dir',
         'call of protocol-running callable os.path.basename through unresolved base os.path.normpath(rdir)'),
        ('load_dir', 'call of protocol-running callable os.path.normpath through unresolved base rdir'),
        ('load_dir', 'call of protocol-running callable set through unresolved base binder.used'),
        ('load_dir', 'call of protocol-running callable set through unresolved base binder.vocab'),
        ('load_dir', 'call of protocol-running callable set through unresolved base binder.vocab'),
        ('load_dir', 'call of protocol-running callable set through unresolved base selftest'),
        ('load_dir', 'call of protocol-running callable sorted through unresolved base set(binder.vocab)'),
        ('load_dir', 'method call run_selftest through unresolved base rs'),
        ('load_dir', 'method call run_sitting_selftest through unresolved base rs'),
        ('load_dir', "unproven pure method call decode through unresolved base files['REVISION']"),
        ('load_dir', "unproven pure method call decode through unresolved base files['rules.json']"),
        ('load_dir', "unproven pure method call decode through unresolved base files['selftest.json']"),
        ('load_dir', 'unproven pure method call decode through unresolved base raw'),
        ('load_dir', 'unproven pure method call fullmatch through unresolved base _REV_DIR'),
        ('load_dir', 'unproven pure method call get through unresolved base doc'),
        ('load_dir', 'unproven pure method call get through unresolved base doc'),
        ('load_dir', 'unproven pure method call items through unresolved base files'),
        ('load_dir', 'unproven pure method call items through unresolved base files'),
        ('load_dir', "unproven pure method call rsplit through unresolved base rel.split('/', 1)[1]"),
        ('load_dir', 'unproven pure method call split through unresolved base rel'),
        ('load_dir', 'unproven pure method call splitlines through unresolved base text'),
        ('load_dir', 'unproven pure method call startswith through unresolved base rel'),
        ('load_dir',
         "unproven pure method call strip through unresolved base files['REVISION'].decode('ascii', 'replace')"),
        ('load_dir', 'unproven pure method call strip through unresolved base ln'),
        ('norm_pair', 'call of protocol-running callable str through unresolved base a'),
        ('norm_pair', 'call of protocol-running callable str through unresolved base b'),
        ('refresh_rules', 'call of protocol-running callable os.path.join through unresolved base base'),
        ('refresh_rules', 'method call acquire through unresolved base _LOCK'),
        ('refresh_rules', 'method call release through unresolved base _LOCK'),
        ('render_item', "call of protocol-running callable ''.join through unresolved base out"),
        ('render_item', 'call of protocol-running callable isinstance through unresolved base p'),
        ('render_item', 'unproven pure method call get through unresolved base item'),
        ('render_line',
         "call of protocol-running callable '\\n'.join through unresolved base (render_item(rule.line, it) for it in list(items)[:_BOUNDS['render_items_max']] if isinstance(it, dict))"),
        ('render_line', 'call of protocol-running callable isinstance through unresolved base it'),
        ('render_line', 'call of protocol-running callable list through unresolved base items'),
        ('run_selftest', 'call of protocol-running callable isinstance through unresolved base case'),
        ('run_selftest', 'call of protocol-running callable set through unresolved base case'),
        ('run_selftest', "call of protocol-running callable sorted through unresolved base case['fire']"),
        ('run_selftest', 'call of protocol-running callable sorted through unresolved base fired'),
        ('run_selftest', 'call of protocol-running callable tuple through unresolved base t'),
        ('run_selftest', 'method call evaluate_game through unresolved base rs'),
        ('sitting_items', 'call of protocol-running callable grouped.setdefault through unresolved base dedup'),
        ('sitting_items', 'call of protocol-running callable sorted through unresolved base grouped'),
        ('sitting_items', "call of protocol-running callable sorted through unresolved base grouped[k]['items']"),
        ('sitting_items', 'call of protocol-running callable str through unresolved base lo'),
        ('sitting_items', "call of protocol-running callable str through unresolved base r['subject']"),
        ('sitting_items', "method call append through unresolved base slot['items']"),
        ('sitting_selftest', 'call of protocol-running callable set through unresolved base _BIND.findall(sql)'),
        ('sitting_selftest', 'call of protocol-running callable set through unresolved base binds'),
        ('sitting_selftest', 'method call sitting_statement through unresolved base rs'),
        ('sitting_selftest', 'unproven pure method call findall through unresolved base _BIND'),
        ('sitting_statement', 'call of protocol-running callable rm.sitting_binds through unresolved base entry'),
        ('sitting_statement', 'call of unlisted callable rm.sitting_binds through unresolved base entry'),
        ('sitting_statement', 'call of unresolved callable entry.impl[0] through unresolved base args'),
        ('<module>', 'implicit attribute read through unresolved base _k'),
        ('<module>', 'implicit attribute read through unresolved base _k'),
        ('<module>', 'implicit attribute read through unresolved base _k'),
        ('<module>', 'implicit attribute read through unresolved base _k'),
        ('<module>', 'implicit attribute read through unresolved base _k'),
        ('<module>', 'implicit attribute read through unresolved base os'),
        ('<module>', 'implicit attribute read through unresolved base rm'),
        ('<module>', 'implicit attribute read through unresolved base rm'),
        ('<module>', 'implicit attribute read through unresolved base rm'),
        ('<module>', 'implicit attribute read through unresolved base wintypes'),
        ('<module>', 'implicit attribute read through unresolved base wintypes'),
        ('<module>', 'implicit attribute read through unresolved base wintypes'),
        ('<module>', 'implicit attribute read through unresolved base wintypes'),
        ('<module>', 'implicit attribute read through unresolved base wintypes'),
        ('<module>', 'implicit attribute read through unresolved base wintypes'),
        ('<module>', 'implicit attribute read through unresolved base wintypes'),
        ('<module>', 'implicit attribute read through unresolved base wintypes'),
        ('<module>', "implicit binary operator through unresolved base rm.CONTRACT_BOUNDS['label_max']"),
        ('<module>', "implicit binary operator through unresolved base rm.CONTRACT_BOUNDS['label_max']"),
        ('<module>', "implicit binary operator through unresolved base rm.CONTRACT_BOUNDS['label_max'] * PAIR"),
        ('<module>', 'implicit comparison through unresolved base os.name'),
        ('<module>', 'implicit comparison through unresolved base rm.REGISTRY'),
        ('<module>', "implicit subscript read through unresolved base __doc__.split('Command line')"),
        ('<module>', 'implicit subscript read through unresolved base rm.CONTRACT_BOUNDS'),
        ('<module>', 'implicit subscript read through unresolved base rm.CONTRACT_BOUNDS'),
        ('<module>', "implicit truth test through unresolved base os.name == 'nt'"),
        ('Refused.__init__', 'implicit binary operator through unresolved base cls'),
        ('Refused.__init__', 'implicit binary operator through unresolved base detail'),
        ('Refused.__init__',
         "implicit result disposal through unresolved base super().__init__(cls + (': ' + detail if detail else ''))"),
        ('Refused.__init__', 'implicit truth test through unresolved base detail'),
        ('Ruleset.evaluate_game', 'implicit attribute read through unresolved base self'),
        ('Ruleset.evaluate_game', "implicit attribute read through unresolved base self.core['core.game']"),
        ('Ruleset.evaluate_game', 'implicit subscript read through unresolved base self.core'),
        ('Ruleset.evaluate_game', "implicit subscript read through unresolved base self.core['core.game'].impl"),
        ('Ruleset.game_rules', 'implicit attribute read through unresolved base r'),
        ('Ruleset.game_rules', 'implicit attribute read through unresolved base self'),
        ('Ruleset.game_rules', 'implicit comparison through unresolved base r.scope'),
        ('Ruleset.game_rules', 'implicit iteration through unresolved base self.rules'),
        ('Ruleset.game_rules', "implicit truth test through unresolved base r.scope == 'game'"),
        ('Ruleset.horizon_days', 'implicit attribute read through unresolved base r'),
        ('Ruleset.horizon_days', 'implicit attribute read through unresolved base self'),
        ('Ruleset.horizon_days', 'implicit iteration through unresolved base self.sitting_rules'),
        ('Ruleset.horizon_days', 'implicit subscript read through unresolved base r.sitting'),
        ('Ruleset.horizon_days', 'implicit subscript read through unresolved base r.sitting[1]'),
        ('Ruleset.render_line', 'implicit attribute read through unresolved base self'),
        ('Ruleset.render_line', "implicit attribute read through unresolved base self.core['core.render']"),
        ('Ruleset.render_line', 'implicit subscript read through unresolved base self.core'),
        ('Ruleset.render_line', "implicit subscript read through unresolved base self.core['core.render'].impl"),
        ('Ruleset.rule', 'implicit attribute read through unresolved base r'),
        ('Ruleset.rule', 'implicit attribute read through unresolved base self'),
        ('Ruleset.rule', 'implicit comparison through unresolved base r.id'),
        ('Ruleset.rule', 'implicit iteration through unresolved base self.rules'),
        ('Ruleset.rule', 'implicit truth test through unresolved base r.id == rule_id'),
        ('Ruleset.run_selftest', 'implicit attribute read through unresolved base self'),
        ('Ruleset.run_selftest', "implicit attribute read through unresolved base self.core['core.game']"),
        ('Ruleset.run_selftest', 'implicit subscript read through unresolved base self.core'),
        ('Ruleset.run_selftest', "implicit subscript read through unresolved base self.core['core.game'].impl"),
        ('Ruleset.run_sitting_selftest', 'implicit attribute read through unresolved base self'),
        ('Ruleset.run_sitting_selftest', "implicit attribute read through unresolved base self.core['core.sitting']"),
        ('Ruleset.run_sitting_selftest', 'implicit subscript read through unresolved base self.core'),
        ('Ruleset.run_sitting_selftest',
         "implicit subscript read through unresolved base self.core['core.sitting'].impl"),
        ('Ruleset.sitting_items', 'implicit attribute read through unresolved base self'),
        ('Ruleset.sitting_items', "implicit attribute read through unresolved base self.core['core.sitting']"),
        ('Ruleset.sitting_items', 'implicit subscript read through unresolved base self.core'),
        ('Ruleset.sitting_items', "implicit subscript read through unresolved base self.core['core.sitting'].impl"),
        ('Ruleset.sitting_rules', 'implicit attribute read through unresolved base r'),
        ('Ruleset.sitting_rules', 'implicit attribute read through unresolved base self'),
        ('Ruleset.sitting_rules', 'implicit comparison through unresolved base r.scope'),
        ('Ruleset.sitting_rules', 'implicit iteration through unresolved base self.rules'),
        ('Ruleset.sitting_rules', "implicit truth test through unresolved base r.scope == 'sitting'"),
        ('Ruleset.sitting_statement', 'implicit attribute read through unresolved base self'),
        ('Ruleset.sitting_statement', "implicit attribute read through unresolved base self.core['core.sitting']"),
        ('Ruleset.sitting_statement', 'implicit subscript read through unresolved base self.core'),
        ('Ruleset.sitting_statement',
         "implicit subscript read through unresolved base self.core['core.sitting'].impl"),
        ('_Binder.__call__', 'implicit attribute read through unresolved base entry'),
        ('_Binder.__call__', 'implicit attribute read through unresolved base entry'),
        ('_Binder.__call__', 'implicit attribute read through unresolved base entry'),
        ('_Binder.__call__', 'implicit attribute read through unresolved base rm'),
        ('_Binder.__call__', 'implicit attribute read through unresolved base self'),
        ('_Binder.__call__', 'implicit attribute read through unresolved base self'),
        ('_Binder.__call__', 'implicit attribute read through unresolved base self'),
        ('_Binder.__call__', 'implicit attribute read through unresolved base self'),
        ('_Binder.__call__', 'implicit comparison through unresolved base entry.kind'),
        ('_Binder.__call__', 'implicit comparison through unresolved base name'),
        ('_Binder.__call__', 'implicit truth test through unresolved base self.build'),
        ('_Binder.__call__', 'implicit truth test through unresolved base self.build'),
        ('_Budget.tick', 'implicit attribute read through unresolved base self'),
        ('_Budget.tick', 'implicit comparison through unresolved base self.left'),
        ('_Budget.tick', 'implicit truth test through unresolved base self.left < 0'),
        ('_bound_lookup.R', 'implicit attribute read through unresolved base e'),
        ('_bound_lookup.R', 'implicit comparison through unresolved base e.kind'),
        ('_bound_lookup.R', 'implicit subscript read through unresolved base refs'),
        ('_bound_lookup.R', 'implicit truth test through unresolved base e.kind != kind'),
        ('_check_time', 'implicit comparison through unresolved base time.monotonic()'),
        ('_check_time', 'implicit truth test through unresolved base time.monotonic() > deadline'),
        ('_closure_names', "implicit comparison through unresolved base closure['code']"),
        ('_closure_names', 'implicit comparison through unresolved base set(closure)'),
        ('_closure_names', "implicit comparison through unresolved base set(closure['code'])"),
        ('_closure_names', "implicit iteration through unresolved base closure['code']"),
        ('_closure_names', 'implicit subscript read through unresolved base closure'),
        ('_closure_names', 'implicit subscript read through unresolved base closure'),
        ('_closure_names', 'implicit subscript read through unresolved base closure'),
        ('_closure_names', 'implicit subscript read through unresolved base closure'),
        ('_closure_names', 'implicit subscript read through unresolved base closure'),
        ('_closure_names', 'implicit subscript read through unresolved base closure'),
        ('_closure_names', 'implicit subscript read through unresolved base closure'),
        ('_closure_names', 'implicit subscript read through unresolved base closure'),
        ('_closure_names', "implicit truth test through unresolved base _HEX.fullmatch(closure['fp'])"),
        ('_closure_names',
         "implicit truth test through unresolved base not isinstance(closure, dict) or set(closure) != {'code', 'fp'} or (not isinstance(closure['code'], list)) or (len(closure['code']) > _BOUNDS['files_max']) or (not all((isinstance(n, str) and _CODE_NAME.fullmatch(n) for n in closure['code']))) or (closure['code'] != sorted(set(closure['code']))) or (not set(CODE_REQUIRED) <= set(closure['code'])) or (not isinstance(closure['fp'], str)) or (len(closure['fp']) != _BOUNDS['digest_hex']) or (not _HEX.fullmatch(closure['fp']))"),
        ('_closure_names', "implicit truth test through unresolved base set(CODE_REQUIRED) <= set(closure['code'])"),
        ('_closure_names', "implicit truth test through unresolved base set(closure) != {'code', 'fp'}"),
        ('_code_files', 'implicit attribute read through unresolved base rb'),
        ('_code_files', 'implicit attribute read through unresolved base rb'),
        ('_code_files', 'implicit attribute read through unresolved base rb'),
        ('_code_files', 'implicit attribute read through unresolved base sys'),
        ('_code_files', 'implicit attribute read through unresolved base type(e)'),
        ('_code_files', 'implicit binary operator through unresolved base name'),
        ('_code_files', 'implicit binary operator through unresolved base name'),
        ('_code_files', 'implicit binary operator through unresolved base type(e).__name__'),
        ('_code_files', 'implicit comparison through unresolved base name'),
        ('_code_files', 'implicit iteration through unresolved base names'),
        ('_code_files', "implicit iteration through unresolved base rb.LOADED.get(stem, (None, b''))"),
        ('_code_files', 'implicit subscript read through unresolved base os.path.splitext(name)'),
        ('_code_files',
         'implicit truth test through unresolved base api_dir is not None or name == os.path.basename(rb.__file__)'),
        ('_compile_expr', 'implicit attribute read through unresolved base e'),
        ('_compile_expr', 'implicit attribute read through unresolved base e'),
        ('_compile_expr', 'implicit attribute read through unresolved base e'),
        ('_compile_expr', 'implicit comparison through unresolved base e.subject'),
        ('_compile_expr', 'implicit comparison through unresolved base k'),
        ('_compile_expr', 'implicit comparison through unresolved base k'),
        ('_compile_expr', 'implicit comparison through unresolved base k'),
        ('_compile_expr', 'implicit comparison through unresolved base k'),
        ('_compile_expr', 'implicit iteration through unresolved base node.items()'),
        ('_compile_expr', 'implicit iteration through unresolved base v'),
        ('_compile_expr', "implicit result disposal through unresolved base bind(e.family, 'params')"),
        ('_compile_expr', 'implicit subscript read through unresolved base v'),
        ('_compile_expr', 'implicit truth test through unresolved base _finite(v)'),
        ('_compile_expr',
         'implicit truth test through unresolved base _finite(v) or isinstance(v, (str, bool)) or v is None or (isinstance(v, list) and all((_finite(x) or isinstance(x, str) for x in v)))'),
        ('_compile_expr', 'implicit truth test through unresolved base _finite(x)'),
        ('_compile_expr', 'implicit truth test through unresolved base e.subject != subject'),
        ('_compile_expr', "implicit truth test through unresolved base k == 'abs'"),
        ('_compile_expr', "implicit truth test through unresolved base k == 'm'"),
        ('_compile_expr', "implicit truth test through unresolved base k == 'v'"),
        ('_compile_pred', 'implicit attribute read through unresolved base entry'),
        ('_compile_pred', 'implicit attribute read through unresolved base entry'),
        ('_compile_pred', 'implicit binary operator through unresolved base depth'),
        ('_compile_pred', 'implicit binary operator through unresolved base depth'),
        ('_compile_pred', 'implicit comparison through unresolved base depth'),
        ('_compile_pred', 'implicit comparison through unresolved base kind'),
        ('_compile_pred', 'implicit comparison through unresolved base kind'),
        ('_compile_pred', 'implicit comparison through unresolved base kind'),
        ('_compile_pred', 'implicit comparison through unresolved base set(args)'),
        ('_compile_pred', 'implicit comparison through unresolved base set(node)'),
        ('_compile_pred', 'implicit comparison through unresolved base set(node)'),
        ('_compile_pred', 'implicit comparison through unresolved base set(node)'),
        ('_compile_pred', 'implicit comparison through unresolved base set(v)'),
        ('_compile_pred', 'implicit comparison through unresolved base v'),
        ('_compile_pred', "implicit comparison through unresolved base v['data']"),
        ('_compile_pred', 'implicit hashing through unresolved base a'),
        ('_compile_pred', 'implicit iteration through unresolved base entry.args'),
        ('_compile_pred', 'implicit iteration through unresolved base entry.args'),
        ('_compile_pred', 'implicit iteration through unresolved base node.items()'),
        ('_compile_pred', 'implicit iteration through unresolved base v'),
        ('_compile_pred', 'implicit iteration through unresolved base v'),
        ('_compile_pred', 'implicit subscript read through unresolved base args'),
        ('_compile_pred', 'implicit subscript read through unresolved base data'),
        ('_compile_pred', 'implicit subscript read through unresolved base node'),
        ('_compile_pred', 'implicit subscript read through unresolved base node'),
        ('_compile_pred', 'implicit subscript read through unresolved base node'),
        ('_compile_pred', 'implicit subscript read through unresolved base v'),
        ('_compile_pred', 'implicit subscript read through unresolved base v'),
        ('_compile_pred', 'implicit truth test through unresolved base _finite(x)'),
        ('_compile_pred', "implicit truth test through unresolved base depth > _BOUNDS['pred_depth_max']"),
        ('_compile_pred', "implicit truth test through unresolved base isinstance(v, dict) and set(v) == {'data'}"),
        ('_compile_pred', "implicit truth test through unresolved base kind == 'expr'"),
        ('_compile_pred', "implicit truth test through unresolved base kind == 'list'"),
        ('_compile_pred', "implicit truth test through unresolved base kind == 'rel'"),
        ('_compile_pred',
         'implicit truth test through unresolved base not isinstance(args, dict) or set(args) != {a for a, _ in entry.args}'),
        ('_compile_pred', "implicit truth test through unresolved base set(node) == {'all'}"),
        ('_compile_pred', "implicit truth test through unresolved base set(node) == {'all'} or set(node) == {'any'}"),
        ('_compile_pred', "implicit truth test through unresolved base set(node) == {'not'}"),
        ('_compile_pred', "implicit truth test through unresolved base set(node) == {'op', 'args'}"),
        ('_compile_pred', 'implicit truth test through unresolved base v'),
        ('_compile_sitting', 'implicit attribute read through unresolved base entry'),
        ('_compile_sitting', 'implicit attribute read through unresolved base entry'),
        ('_compile_sitting', 'implicit attribute read through unresolved base entry'),
        ('_compile_sitting', 'implicit attribute read through unresolved base rm'),
        ('_compile_sitting', 'implicit comparison through unresolved base kind'),
        ('_compile_sitting', 'implicit comparison through unresolved base kind'),
        ('_compile_sitting', 'implicit comparison through unresolved base kind'),
        ('_compile_sitting', 'implicit comparison through unresolved base kind'),
        ('_compile_sitting', 'implicit comparison through unresolved base kind'),
        ('_compile_sitting', 'implicit comparison through unresolved base kind'),
        ('_compile_sitting', 'implicit comparison through unresolved base out'),
        ('_compile_sitting', "implicit comparison through unresolved base out['window_days']"),
        ('_compile_sitting', "implicit comparison through unresolved base rm.CONTRACT_BOUNDS['edges_max']"),
        ('_compile_sitting', 'implicit comparison through unresolved base set(args)'),
        ('_compile_sitting', 'implicit comparison through unresolved base set(node)'),
        ('_compile_sitting', 'implicit comparison through unresolved base sorted(v)'),
        ('_compile_sitting', 'implicit comparison through unresolved base v'),
        ('_compile_sitting', 'implicit hashing through unresolved base a'),
        ('_compile_sitting', 'implicit iteration through unresolved base entry.args'),
        ('_compile_sitting', 'implicit iteration through unresolved base entry.args'),
        ('_compile_sitting', 'implicit iteration through unresolved base v'),
        ('_compile_sitting', 'implicit iteration through unresolved base v'),
        ('_compile_sitting', "implicit result disposal through unresolved base bind(f, 'population')"),
        ('_compile_sitting', 'implicit result disposal through unresolved base bind(v, kind)'),
        ('_compile_sitting',
         'implicit result disposal through unresolved base entry.impl[0](out, _bound_lookup(refs), mode)'),
        ('_compile_sitting', 'implicit subscript read through unresolved base args'),
        ('_compile_sitting', 'implicit subscript read through unresolved base entry.impl'),
        ('_compile_sitting', 'implicit subscript read through unresolved base node'),
        ('_compile_sitting', 'implicit subscript read through unresolved base node'),
        ('_compile_sitting', 'implicit subscript read through unresolved base out'),
        ('_compile_sitting', 'implicit subscript read through unresolved base rm.CONTRACT_BOUNDS'),
        ('_compile_sitting',
         "implicit truth test through unresolved base 'window_days' not in out or out['window_days'] <= 0"),
        ('_compile_sitting', 'implicit truth test through unresolved base _STRATA.fullmatch(v)'),
        ('_compile_sitting', 'implicit truth test through unresolved base _finite(v)'),
        ('_compile_sitting', 'implicit truth test through unresolved base _finite(v)'),
        ('_compile_sitting', 'implicit truth test through unresolved base _finite(v) and isinstance(v, int)'),
        ('_compile_sitting', "implicit truth test through unresolved base kind == 'edges'"),
        ('_compile_sitting', "implicit truth test through unresolved base kind == 'filters'"),
        ('_compile_sitting', "implicit truth test through unresolved base kind == 'int'"),
        ('_compile_sitting', "implicit truth test through unresolved base kind == 'label'"),
        ('_compile_sitting', "implicit truth test through unresolved base kind == 'num'"),
        ('_compile_sitting', "implicit truth test through unresolved base len(v) > rm.CONTRACT_BOUNDS['edges_max']"),
        ('_compile_sitting',
         'implicit truth test through unresolved base not (_finite(v) and isinstance(v, int)) or v < 0'),
        ('_compile_sitting',
         'implicit truth test through unresolved base not isinstance(args, dict) or set(args) != {a for a, _ in entry.args}'),
        ('_compile_sitting',
         "implicit truth test through unresolved base not isinstance(node, dict) or set(node) != {'op', 'args'}"),
        ('_compile_sitting',
         "implicit truth test through unresolved base not isinstance(v, list) or not v or len(v) > rm.CONTRACT_BOUNDS['edges_max'] or (not all((_finite(x) for x in v))) or (sorted(v) != v)"),
        ('_compile_sitting', 'implicit truth test through unresolved base v'),
        ('_compile_template', 'implicit comparison through unresolved base label'),
        ('_compile_template', 'implicit comparison through unresolved base lit'),
        ('_compile_template', 'implicit comparison through unresolved base tail'),
        ('_compile_template', 'implicit iteration through unresolved base _PLACE.finditer(line)'),
        ('_compile_template', 'implicit iteration through unresolved base m.groups()'),
        ('_compile_template', 'implicit subscript read through unresolved base line'),
        ('_compile_template', 'implicit subscript read through unresolved base line'),
        ('_compile_template', 'implicit truth test through unresolved base places'),
        ('_entries', 'implicit attribute read through unresolved base ent'),
        ('_entries', 'implicit iteration through unresolved base it'),
        ('_framed', 'implicit result disposal through unresolved base h.update(c)'),
        ('_framed', 'implicit result disposal through unresolved base h.update(domain)'),
        ('_framed', "implicit result disposal through unresolved base h.update(len(c).to_bytes(w, 'big'))"),
        ('_framed', "implicit result disposal through unresolved base h.update(len(files).to_bytes(w, 'big'))"),
        ('_framed', "implicit result disposal through unresolved base h.update(len(p).to_bytes(w, 'big'))"),
        ('_framed', 'implicit result disposal through unresolved base h.update(p)'),
        ('_framed', 'implicit subscript read through unresolved base files'),
        ('_inventory', 'implicit attribute read through unresolved base ds'),
        ('_inventory', 'implicit attribute read through unresolved base ds'),
        ('_inventory', 'implicit attribute read through unresolved base ds'),
        ('_inventory', 'implicit attribute read through unresolved base s'),
        ('_inventory', 'implicit attribute read through unresolved base s'),
        ('_inventory', 'implicit attribute read through unresolved base s'),
        ('_inventory', 'implicit attribute read through unresolved base s'),
        ('_inventory', 'implicit attribute read through unresolved base st'),
        ('_inventory', 'implicit attribute read through unresolved base type(e)'),
        ('_inventory', 'implicit attribute read through unresolved base type(e)'),
        ('_inventory', 'implicit binary operator through unresolved base dn'),
        ('_inventory', 'implicit binary operator through unresolved base name'),
        ('_inventory', 'implicit comparison through unresolved base name'),
        ('_inventory', 'implicit comparison through unresolved base name'),
        ('_inventory', 'implicit comparison through unresolved base name'),
        ('_inventory', 'implicit comparison through unresolved base size'),
        ('_inventory', 'implicit comparison through unresolved base sum((p[2] for p in plan))'),
        ('_inventory', 'implicit hashing through unresolved base p[0]'),
        ('_inventory', 'implicit iteration through unresolved base _entries(path, deadline, plan)'),
        ('_inventory', 'implicit iteration through unresolved base _entries(rdir, deadline, plan)'),
        ('_inventory', 'implicit subscript read through unresolved base p'),
        ('_inventory', 'implicit subscript read through unresolved base p'),
        ('_inventory', 'implicit truth test through unresolved base _DATA_NAME.fullmatch(dn)'),
        ('_inventory', "implicit truth test through unresolved base name == 'data'"),
        ('_inventory', 'implicit truth test through unresolved base size > cap'),
        ('_inventory', 'implicit truth test through unresolved base stat.S_ISDIR(s.st_mode)'),
        ('_inventory', 'implicit truth test through unresolved base stat.S_ISDIR(st.st_mode)'),
        ('_inventory', 'implicit truth test through unresolved base stat.S_ISLNK(ds.st_mode)'),
        ('_inventory',
         'implicit truth test through unresolved base stat.S_ISLNK(ds.st_mode) or _reparse(ds) or (not stat.S_ISREG(ds.st_mode)) or (not _DATA_NAME.fullmatch(dn))'),
        ('_inventory', 'implicit truth test through unresolved base stat.S_ISLNK(s.st_mode)'),
        ('_inventory', 'implicit truth test through unresolved base stat.S_ISLNK(s.st_mode) or _reparse(s)'),
        ('_inventory', 'implicit truth test through unresolved base stat.S_ISLNK(st.st_mode)'),
        ('_inventory',
         'implicit truth test through unresolved base stat.S_ISLNK(st.st_mode) or _reparse(st) or (not stat.S_ISDIR(st.st_mode))'),
        ('_inventory', 'implicit truth test through unresolved base stat.S_ISREG(ds.st_mode)'),
        ('_inventory', 'implicit truth test through unresolved base stat.S_ISREG(s.st_mode)'),
        ('_inventory',
         "implicit truth test through unresolved base sum((p[2] for p in plan)) > _BOUNDS['total_bytes_max']"),
        ('_is_dir', 'implicit attribute read through unresolved base st'),
        ('_log', 'implicit attribute read through unresolved base state'),
        ('_log', 'implicit attribute read through unresolved base state'),
        ('_log', 'implicit attribute read through unresolved base state'),
        ('_log', 'implicit attribute read through unresolved base state'),
        ('_log', 'implicit binary operator through unresolved base state.reason'),
        ('_log', 'implicit binary operator through unresolved base state.word'),
        ('_log', 'implicit comparison through unresolved base sig'),
        ('_log', 'implicit comparison through unresolved base state.word'),
        ('_log', 'implicit truth test through unresolved base sig != _LOGGED'),
        ('_log', "implicit truth test through unresolved base state.word == 'refused'"),
        ('_measure_value', 'implicit attribute read through unresolved base ctx'),
        ('_measure_value', 'implicit attribute read through unresolved base m'),
        ('_measure_value', 'implicit attribute read through unresolved base m'),
        ('_measure_value', 'implicit attribute read through unresolved base m'),
        ('_measure_value', 'implicit attribute read through unresolved base rs'),
        ('_measure_value', 'implicit comparison through unresolved base key'),
        ('_measure_value', 'implicit subscript read through unresolved base m.impl'),
        ('_measure_value', 'implicit subscript read through unresolved base memo'),
        ('_measure_value', 'implicit truth test through unresolved base m.family'),
        ('_measure_value', 'implicit truth test through unresolved base m.family'),
        ('_measure_value', 'implicit truth test through unresolved base m.family and fam is None'),
        ('_nt_final', 'implicit binary operator through unresolved base final[len(pre):]'),
        ('_nt_final', 'implicit comparison through unresolved base os.path.normcase(final)'),
        ('_nt_final', 'implicit subscript read through unresolved base final'),
        ('_nt_final', 'implicit truth test through unresolved base final.startswith(pre)'),
        ('_open_nofollow', 'implicit attribute read through unresolved base buf'),
        ('_open_nofollow', 'implicit attribute read through unresolved base os'),
        ('_open_nofollow', 'implicit attribute read through unresolved base os'),
        ('_open_nofollow', 'implicit attribute read through unresolved base os'),
        ('_open_nofollow', 'implicit attribute read through unresolved base os'),
        ('_open_nofollow', 'implicit attribute read through unresolved base type(e)'),
        ('_open_nofollow', 'implicit attribute read through unresolved base wintypes.HANDLE(-1)'),
        ('_open_nofollow', 'implicit binary operator through unresolved base os.O_RDONLY'),
        ('_open_nofollow', 'implicit binary operator through unresolved base os.O_RDONLY'),
        ('_open_nofollow', 'implicit binary operator through unresolved base os.O_RDONLY | os.O_NOFOLLOW'),
        ('_open_nofollow', 'implicit comparison through unresolved base h'),
        ('_open_nofollow', 'implicit comparison through unresolved base n'),
        ('_open_nofollow', 'implicit comparison through unresolved base os.name'),
        ('_open_nofollow', 'implicit comparison through unresolved base os.name'),
        ('_open_nofollow', 'implicit result disposal through unresolved base _K32.CloseHandle(h)'),
        ('_open_nofollow', 'implicit truth test through unresolved base _nt_final(path, buf.value)'),
        ('_open_nofollow', 'implicit truth test through unresolved base h is None or h == wintypes.HANDLE(-1).value'),
        ('_open_nofollow', 'implicit truth test through unresolved base n == 0'),
        ('_open_nofollow', "implicit truth test through unresolved base n == 0 or n >= _NT['buffer']"),
        ('_open_nofollow', "implicit truth test through unresolved base os.name != 'nt'"),
        ('_open_nofollow', "implicit truth test through unresolved base os.name != 'nt' or _K32 is None"),
        ('_open_nofollow', "implicit truth test through unresolved base os.name == 'posix'"),
        ('_parse_time', 'implicit attribute read through unresolved base t'),
        ('_parse_time', 'implicit attribute read through unresolved base t'),
        ('_parse_time', 'implicit attribute read through unresolved base timezone'),
        ('_parse_time', 'implicit subscript read through unresolved base v'),
        ('_parse_time', "implicit truth test through unresolved base v.endswith('Z')"),
        ('_parse_time', "implicit truth test through unresolved base v.endswith('Z')"),
        ('_parse_time', "implicit truth test through unresolved base v.endswith('Z') and t.tzinfo is None"),
        ('_pointer_key', 'implicit attribute read through unresolved base st'),
        ('_pointer_key', 'implicit attribute read through unresolved base type(e)'),
        ('_pointer_target', 'implicit attribute read through unresolved base st'),
        ('_pointer_target', 'implicit attribute read through unresolved base st'),
        ('_pointer_target', 'implicit attribute read through unresolved base st'),
        ('_pointer_target', 'implicit attribute read through unresolved base st'),
        ('_pointer_target', 'implicit comparison through unresolved base st.st_size'),
        ('_pointer_target', 'implicit comparison through unresolved base target'),
        ('_pointer_target', 'implicit truth test through unresolved base _REV_DIR.fullmatch(target)'),
        ('_pointer_target', 'implicit truth test through unresolved base _reparse(st)'),
        ('_pointer_target', 'implicit truth test through unresolved base stat.S_ISLNK(st.st_mode)'),
        ('_pointer_target', 'implicit truth test through unresolved base stat.S_ISREG(st.st_mode)'),
        ('_pointer_target',
         "implicit truth test through unresolved base stat.S_ISREG(st.st_mode) and (not _reparse(st)) and (st.st_size <= _BOUNDS['pointer_bytes_max'])"),
        ('_pointer_target', 'implicit truth test through unresolved base target == NONE_TARGET'),
        ('_provenance', 'implicit attribute read through unresolved base mine'),
        ('_provenance', 'implicit attribute read through unresolved base rb'),
        ('_provenance', 'implicit attribute read through unresolved base rb'),
        ('_provenance', 'implicit binary operator through unresolved base rb.PRIOR'),
        ('_provenance', "implicit subscript read through unresolved base rb.LOADED.get(__name__, (None, b''))"),
        ('_py', 'implicit comparison through unresolved base v'),
        ('_py', 'implicit truth test through unresolved base v == v.to_integral_value()'),
        ('_read_verified', 'implicit attribute read through unresolved base fs'),
        ('_read_verified', 'implicit attribute read through unresolved base fs'),
        ('_read_verified', 'implicit attribute read through unresolved base type(e)'),
        ('_read_verified', 'implicit binary operator through unresolved base cap'),
        ('_read_verified', 'implicit comparison through unresolved base (fs.st_dev, fs.st_ino)'),
        ('_read_verified', 'implicit comparison through unresolved base cap'),
        ('_read_verified', 'implicit comparison through unresolved base fs.st_size'),
        ('_read_verified', 'implicit comparison through unresolved base left'),
        ('_read_verified', 'implicit comparison through unresolved base size'),
        ('_read_verified', 'implicit truth test through unresolved base _reparse(fs)'),
        ('_read_verified', 'implicit truth test through unresolved base b'),
        ('_read_verified', 'implicit truth test through unresolved base left > 0'),
        ('_read_verified', 'implicit truth test through unresolved base len(data) > cap'),
        ('_read_verified', 'implicit truth test through unresolved base len(data) > cap or len(data) != size'),
        ('_read_verified',
         'implicit truth test through unresolved base not stat.S_ISREG(fs.st_mode) or _reparse(fs) or (fs.st_dev, fs.st_ino) != ident or (fs.st_size != size)'),
        ('_read_verified', 'implicit truth test through unresolved base stat.S_ISREG(fs.st_mode)'),
        ('_register_core',
         "implicit result disposal through unresolved base rm._register(rm.Entry('core', 'core.game', (evaluate_game, eval_pred, eval_expr, _measure_value, run_selftest)))"),
        ('_register_core',
         "implicit result disposal through unresolved base rm._register(rm.Entry('core', 'core.render', (render_line, render_item, _render_value)))"),
        ('_register_core',
         "implicit result disposal through unresolved base rm._register(rm.Entry('core', 'core.sitting', (sitting_items, sitting_statement, norm_pair, _py, _bound_lookup, sitting_selftest)))"),
        ('_render_value', 'implicit binary operator through unresolved base (places, v)'),
        ('_render_value', 'implicit iteration through unresolved base v'),
        ('_render_value', 'implicit truth test through unresolved base v'),
        ('_reparse', 'implicit attribute read through unresolved base os'),
        ('_reparse', 'implicit attribute read through unresolved base st'),
        ('_reparse', 'implicit binary operator through unresolved base st.st_file_attributes'),
        ('_reparse', 'implicit comparison through unresolved base os.name'),
        ('_reparse', "implicit truth test through unresolved base os.name == 'nt'"),
        ('build_revision', 'implicit attribute read through unresolved base binder'),
        ('build_revision', 'implicit attribute read through unresolved base timezone'),
        ('build_revision',
         "implicit binary operator through unresolved base (rev, datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), parent, reason.replace('\\t', ' ').replace('\\n', ' '))"),
        ('build_revision', 'implicit binary operator through unresolved base digest'),
        ('build_revision', 'implicit binary operator through unresolved base dn'),
        ('build_revision', 'implicit binary operator through unresolved base rev'),
        ('build_revision', 'implicit binary operator through unresolved base rev'),
        ('build_revision',
         "implicit binary operator through unresolved base secrets.token_hex(_BOUNDS['id_hex'] // 2)"),
        ('build_revision',
         "implicit binary operator through unresolved base secrets.token_hex(_BOUNDS['id_hex'] // 2)"),
        ('build_revision', 'implicit comparison through unresolved base ext'),
        ('build_revision', 'implicit iteration through unresolved base f.read().splitlines()'),
        ('build_revision', "implicit iteration through unresolved base rel.split('/')"),
        ('build_revision', "implicit iteration through unresolved base rel.split('/', 1)[1].rsplit('.', 1)"),
        ('build_revision', 'implicit iteration through unresolved base text.splitlines()'),
        ('build_revision', 'implicit result disposal through unresolved base compile_rules(doc, binder, data)'),
        ('build_revision', 'implicit result disposal through unresolved base load_dir(staged)'),
        ('build_revision', 'implicit result disposal through unresolved base shutil.rmtree(incoming)'),
        ('build_revision', 'implicit result disposal through unresolved base shutil.rmtree(staged)'),
        ('build_revision', 'implicit subscript read through unresolved base digest'),
        ('build_revision', "implicit subscript read through unresolved base lines[-1].split('\\t')"),
        ('build_revision', "implicit subscript read through unresolved base rel.split('/', 1)"),
        ('build_revision', 'implicit truth test through unresolved base _exists(final)'),
        ('build_revision', 'implicit truth test through unresolved base _exists(incoming)'),
        ('build_revision', 'implicit truth test through unresolved base _exists(log)'),
        ('build_revision', 'implicit truth test through unresolved base _exists(staged)'),
        ('build_revision', 'implicit truth test through unresolved base _is_dir(ddir)'),
        ('build_revision', "implicit truth test through unresolved base ext == 'json'"),
        ('build_revision', 'implicit truth test through unresolved base ln.strip()'),
        ('build_revision', 'implicit truth test through unresolved base ln.strip()'),
        ('cli', 'implicit attribute read through unresolved base e'),
        ('cli', 'implicit attribute read through unresolved base e'),
        ('cli', 'implicit attribute read through unresolved base rs'),
        ('cli', 'implicit binary operator through unresolved base e.cls'),
        ('cli', 'implicit binary operator through unresolved base e.cls'),
        ('cli', 'implicit binary operator through unresolved base review_eval()'),
        ('cli', 'implicit binary operator through unresolved base rs.rev'),
        ('cli', 'implicit comparison through unresolved base cmd'),
        ('cli', 'implicit comparison through unresolved base cmd'),
        ('cli', 'implicit comparison through unresolved base cmd'),
        ('cli', 'implicit iteration through unresolved base rest'),
        ('cli', 'implicit iteration through unresolved base rest'),
        ('cli', "implicit subscript read through unresolved base __doc__.split('Command line')"),
        ('cli', 'implicit subscript read through unresolved base argv'),
        ('cli', 'implicit subscript read through unresolved base rest'),
        ('cli', 'implicit truth test through unresolved base argv'),
        ('cli', "implicit truth test through unresolved base cmd == 'build'"),
        ('cli', "implicit truth test through unresolved base cmd == 'build' and rest"),
        ('cli', "implicit truth test through unresolved base cmd == 'literal'"),
        ('cli', "implicit truth test through unresolved base cmd == 'literal' and rest"),
        ('cli', "implicit truth test through unresolved base cmd == 'validate'"),
        ('cli', "implicit truth test through unresolved base cmd == 'validate' and len(rest) == 1"),
        ('closure_fingerprint', 'implicit binary operator through unresolved base k'),
        ('closure_fingerprint', 'implicit comparison through unresolved base k'),
        ('closure_fingerprint', "implicit hashing through unresolved base 'revision/' + k"),
        ('closure_fingerprint', 'implicit iteration through unresolved base revision_files.items()'),
        ('closure_fingerprint', "implicit truth test through unresolved base k != 'REVISION'"),
        ('compile_rules', 'implicit attribute read through unresolved base bind'),
        ('compile_rules', 'implicit attribute read through unresolved base entry'),
        ('compile_rules', 'implicit attribute read through unresolved base r'),
        ('compile_rules', 'implicit attribute read through unresolved base r'),
        ('compile_rules', 'implicit attribute read through unresolved base r'),
        ('compile_rules', 'implicit attribute read through unresolved base r'),
        ('compile_rules', 'implicit attribute read through unresolved base r'),
        ('compile_rules', 'implicit attribute read through unresolved base r'),
        ('compile_rules', 'implicit attribute read through unresolved base r'),
        ('compile_rules', 'implicit attribute read through unresolved base r'),
        ('compile_rules', 'implicit attribute read through unresolved base r'),
        ('compile_rules', 'implicit attribute read through unresolved base r.sitting[0]'),
        ('compile_rules', 'implicit attribute read through unresolved base rm'),
        ('compile_rules', 'implicit attribute read through unresolved base rs'),
        ('compile_rules', 'implicit attribute read through unresolved base rs'),
        ('compile_rules', 'implicit attribute read through unresolved base rs'),
        ('compile_rules', 'implicit attribute read through unresolved base rs'),
        ('compile_rules', "implicit comparison through unresolved base doc['format']"),
        ('compile_rules', 'implicit comparison through unresolved base families'),
        ('compile_rules', 'implicit comparison through unresolved base k'),
        ('compile_rules', 'implicit comparison through unresolved base r.effect'),
        ('compile_rules', 'implicit comparison through unresolved base r.id'),
        ('compile_rules', 'implicit comparison through unresolved base r.scope'),
        ('compile_rules', 'implicit comparison through unresolved base r.scope'),
        ('compile_rules', 'implicit comparison through unresolved base r.subject'),
        ('compile_rules', "implicit comparison through unresolved base rm.CONTRACT_BOUNDS['show_max']"),
        ('compile_rules', 'implicit comparison through unresolved base s[1]'),
        ('compile_rules', 'implicit comparison through unresolved base set(doc)'),
        ('compile_rules', 'implicit comparison through unresolved base set(raw)'),
        ('compile_rules', 'implicit comparison through unresolved base set(raw)'),
        ('compile_rules', 'implicit comparison through unresolved base set(values)'),
        ('compile_rules', 'implicit hashing through unresolved base n'),
        ('compile_rules', 'implicit hashing through unresolved base s[0]'),
        ('compile_rules', 'implicit hashing through unresolved base s[0]'),
        ('compile_rules', 'implicit iteration through unresolved base bind.kinds.items()'),
        ('compile_rules', 'implicit iteration through unresolved base params.items()'),
        ('compile_rules', 'implicit iteration through unresolved base rules'),
        ('compile_rules', 'implicit iteration through unresolved base show'),
        ('compile_rules', 'implicit iteration through unresolved base show'),
        ('compile_rules', 'implicit iteration through unresolved base show'),
        ('compile_rules', 'implicit iteration through unresolved base show'),
        ('compile_rules', 'implicit iteration through unresolved base show'),
        ('compile_rules', 'implicit iteration through unresolved base show'),
        ('compile_rules', 'implicit iteration through unresolved base values.values()'),
        ('compile_rules', 'implicit result disposal through unresolved base rs.rules.append(r)'),
        ('compile_rules',
         "implicit subscript read through unresolved base _compile_expr({'m': s[1]}, bind, r.subject)"),
        ('compile_rules', 'implicit subscript read through unresolved base doc'),
        ('compile_rules', 'implicit subscript read through unresolved base doc'),
        ('compile_rules', 'implicit subscript read through unresolved base doc'),
        ('compile_rules', 'implicit subscript read through unresolved base doc'),
        ('compile_rules', 'implicit subscript read through unresolved base doc'),
        ('compile_rules', 'implicit subscript read through unresolved base r.sitting'),
        ('compile_rules', 'implicit subscript read through unresolved base raw'),
        ('compile_rules', 'implicit subscript read through unresolved base raw'),
        ('compile_rules', 'implicit subscript read through unresolved base raw'),
        ('compile_rules', 'implicit subscript read through unresolved base raw'),
        ('compile_rules', 'implicit subscript read through unresolved base rm.CONTRACT_BOUNDS'),
        ('compile_rules', 'implicit subscript read through unresolved base s'),
        ('compile_rules', 'implicit subscript read through unresolved base s'),
        ('compile_rules', 'implicit subscript read through unresolved base s'),
        ('compile_rules', 'implicit subscript read through unresolved base s'),
        ('compile_rules', 'implicit subscript read through unresolved base s'),
        ('compile_rules', 'implicit subscript read through unresolved base s'),
        ('compile_rules', 'implicit truth test through unresolved base _HEX.fullmatch(nonce)'),
        ('compile_rules', 'implicit truth test through unresolved base _RULE_ID.fullmatch(r.id)'),
        ('compile_rules', "implicit truth test through unresolved base doc['format'] != _BOUNDS['format']"),
        ('compile_rules', 'implicit truth test through unresolved base families <= set(rs.params)'),
        ('compile_rules', "implicit truth test through unresolved base k == 'params'"),
        ('compile_rules', "implicit truth test through unresolved base len(show) > rm.CONTRACT_BOUNDS['show_max']"),
        ('compile_rules',
         "implicit truth test through unresolved base not isinstance(doc, dict) or set(doc) != {'format', 'nonce', 'vocabulary', 'closure', 'measure_params', 'rules'}"),
        ('compile_rules',
         "implicit truth test through unresolved base not isinstance(show, list) or not show or len(show) > rm.CONTRACT_BOUNDS['show_max'] or (not all((isinstance(s, list) and len(s) == PAIR and isinstance(s[0], str) and _RULE_LABEL.fullmatch(s[0]) for s in show))) or (len({s[0] for s in show}) != len(show))"),
        ('compile_rules',
         'implicit truth test through unresolved base not isinstance(values, dict) or set(values) != set(entry.data) or (not all((_finite(x) for x in values.values())))'),
        ('compile_rules', "implicit truth test through unresolved base r.scope == 'game'"),
        ('compile_rules', "implicit truth test through unresolved base r.scope == 'sitting'"),
        ('compile_rules', "implicit truth test through unresolved base set(raw) != RULE_KEYS | {'sitting'}"),
        ('compile_rules', "implicit truth test through unresolved base set(raw) != RULE_KEYS | {'subject', 'when'}"),
        ('compile_rules', 'implicit truth test through unresolved base set(values) != set(entry.data)'),
        ('compile_rules', 'implicit truth test through unresolved base show'),
        ('eval_expr', 'implicit binary operator through unresolved base rm._num(a)'),
        ('eval_expr', 'implicit comparison through unresolved base k'),
        ('eval_expr', 'implicit comparison through unresolved base k'),
        ('eval_expr', 'implicit comparison through unresolved base k'),
        ('eval_expr', 'implicit comparison through unresolved base k'),
        ('eval_expr', 'implicit subscript read through unresolved base node'),
        ('eval_expr', 'implicit subscript read through unresolved base node'),
        ('eval_expr', 'implicit subscript read through unresolved base node'),
        ('eval_expr', 'implicit subscript read through unresolved base node'),
        ('eval_expr', 'implicit subscript read through unresolved base node'),
        ('eval_expr', 'implicit subscript read through unresolved base node'),
        ('eval_expr', "implicit truth test through unresolved base k == 'abs'"),
        ('eval_expr', "implicit truth test through unresolved base k == 'add'"),
        ('eval_expr', "implicit truth test through unresolved base k == 'm'"),
        ('eval_expr', "implicit truth test through unresolved base k == 'v'"),
        ('eval_pred', 'implicit attribute read through unresolved base entry'),
        ('eval_pred', 'implicit comparison through unresolved base k'),
        ('eval_pred', 'implicit comparison through unresolved base k'),
        ('eval_pred', 'implicit comparison through unresolved base k'),
        ('eval_pred', 'implicit iteration through unresolved base args'),
        ('eval_pred', 'implicit iteration through unresolved base node[1]'),
        ('eval_pred', 'implicit result disposal through unresolved base budget.tick()'),
        ('eval_pred', 'implicit subscript read through unresolved base entry.impl'),
        ('eval_pred', 'implicit subscript read through unresolved base node'),
        ('eval_pred', 'implicit subscript read through unresolved base node'),
        ('eval_pred', 'implicit subscript read through unresolved base node'),
        ('eval_pred', 'implicit subscript read through unresolved base node'),
        ('eval_pred', "implicit truth test through unresolved base k == 'all'"),
        ('eval_pred', "implicit truth test through unresolved base k == 'not'"),
        ('eval_pred', 'implicit truth test through unresolved base v'),
        ('evaluate_game', 'implicit attribute read through unresolved base rs'),
        ('evaluate_game', 'implicit attribute read through unresolved base rs'),
        ('evaluate_game', 'implicit attribute read through unresolved base rs'),
        ('evaluate_game', 'implicit attribute read through unresolved base rule'),
        ('evaluate_game', 'implicit attribute read through unresolved base rule'),
        ('evaluate_game', 'implicit attribute read through unresolved base rule'),
        ('evaluate_game', 'implicit attribute read through unresolved base rule'),
        ('evaluate_game', 'implicit attribute read through unresolved base rule'),
        ('evaluate_game', 'implicit comparison through unresolved base rule.effect'),
        ('evaluate_game', 'implicit comparison through unresolved base rule.subject'),
        ('evaluate_game', 'implicit hashing through unresolved base label'),
        ('evaluate_game', 'implicit iteration through unresolved base rs.game_rules'),
        ('evaluate_game', 'implicit iteration through unresolved base rule.show'),
        ('evaluate_game', 'implicit iteration through unresolved base subjects'),
        ('evaluate_game', "implicit truth test through unresolved base rule.effect == 'flag'"),
        ('evaluate_game', "implicit truth test through unresolved base rule.subject == 'seat'"),
        ('health_word', 'implicit attribute read through unresolved base _STATE'),
        ('literal', 'implicit attribute read through unresolved base rule'),
        ('literal', 'implicit binary operator through unresolved base re.escape(k)'),
        ('literal', 'implicit binary operator through unresolved base v'),
        ('literal', 'implicit comparison through unresolved base rule.scope'),
        ('literal', "implicit iteration through unresolved base rs.sitting_statement(rule, 'days_back')"),
        ('literal', 'implicit subscript read through unresolved base binds'),
        ('literal', "implicit truth test through unresolved base rule is None or rule.scope != 'sitting'"),
        ('load_dir', 'implicit attribute read through unresolved base binder'),
        ('load_dir', 'implicit attribute read through unresolved base binder'),
        ('load_dir', 'implicit attribute read through unresolved base binder'),
        ('load_dir', 'implicit attribute read through unresolved base binder'),
        ('load_dir', "implicit binary operator through unresolved base digest[:_BOUNDS['rev_hex']]"),
        ('load_dir', 'implicit binary operator through unresolved base time.monotonic()'),
        ('load_dir', 'implicit comparison through unresolved base base'),
        ('load_dir', 'implicit comparison through unresolved base binder.vocab'),
        ('load_dir', 'implicit comparison through unresolved base code_fp'),
        ('load_dir', 'implicit comparison through unresolved base ext'),
        ('load_dir', 'implicit comparison through unresolved base k'),
        ('load_dir', 'implicit comparison through unresolved base set(binder.used)'),
        ('load_dir', 'implicit comparison through unresolved base set(selftest)'),
        ('load_dir', 'implicit comparison through unresolved base stated'),
        ('load_dir', 'implicit hashing through unresolved base k'),
        ('load_dir', 'implicit iteration through unresolved base binder.vocab'),
        ('load_dir', 'implicit iteration through unresolved base files.items()'),
        ('load_dir', 'implicit iteration through unresolved base files.items()'),
        ('load_dir', "implicit iteration through unresolved base rel.split('/', 1)[1].rsplit('.', 1)"),
        ('load_dir', 'implicit iteration through unresolved base text.splitlines()'),
        ('load_dir', "implicit result disposal through unresolved base rs.run_selftest(selftest['cases'], deadline)"),
        ('load_dir', 'implicit result disposal through unresolved base rs.run_sitting_selftest()'),
        ('load_dir', 'implicit subscript read through unresolved base digest'),
        ('load_dir', 'implicit subscript read through unresolved base digest'),
        ('load_dir', 'implicit subscript read through unresolved base doc'),
        ('load_dir', "implicit subscript read through unresolved base doc['closure']"),
        ('load_dir', 'implicit subscript read through unresolved base files'),
        ('load_dir', 'implicit subscript read through unresolved base files'),
        ('load_dir', 'implicit subscript read through unresolved base files'),
        ('load_dir', "implicit subscript read through unresolved base rel.split('/', 1)"),
        ('load_dir', 'implicit subscript read through unresolved base selftest'),
        ('load_dir', 'implicit subscript read through unresolved base selftest'),
        ('load_dir', 'implicit truth test through unresolved base _REV_DIR.fullmatch(base)'),
        ('load_dir', "implicit truth test through unresolved base code_fp != doc['closure']['fp']"),
        ('load_dir', "implicit truth test through unresolved base ext == 'json'"),
        ('load_dir', "implicit truth test through unresolved base k != 'REVISION'"),
        ('load_dir', 'implicit truth test through unresolved base ln.strip()'),
        ('load_dir',
         'implicit truth test through unresolved base not isinstance(binder.vocab, list) or not all((isinstance(n, str) for n in binder.vocab)) or binder.vocab != sorted(set(binder.vocab))'),
        ('load_dir',
         "implicit truth test through unresolved base not isinstance(selftest, dict) or set(selftest) != {'cases'} or (not isinstance(selftest['cases'], list)) or (len(selftest['cases']) > _BOUNDS['cases_max'])"),
        ('load_dir', "implicit truth test through unresolved base rel.startswith('data/')"),
        ('load_dir', 'implicit truth test through unresolved base set(binder.used) != set(binder.vocab)'),
        ('load_dir', "implicit truth test through unresolved base set(selftest) != {'cases'}"),
        ('load_dir', 'implicit truth test through unresolved base stated != digest'),
        ('load_dir',
         "implicit truth test through unresolved base stated != digest or base != 'rules-' + digest[:_BOUNDS['rev_hex']]"),
        ('norm_pair', 'implicit comparison through unresolved base str(a)'),
        ('norm_pair', 'implicit truth test through unresolved base str(a) < str(b)'),
        ('refresh_rules', 'implicit attribute read through unresolved base e'),
        ('refresh_rules', 'implicit attribute read through unresolved base rs'),
        ('refresh_rules', 'implicit attribute read through unresolved base type(e)'),
        ('refresh_rules', 'implicit binary operator through unresolved base type(e).__name__'),
        ('refresh_rules', 'implicit comparison through unresolved base key'),
        ('refresh_rules', 'implicit comparison through unresolved base key'),
        ('refresh_rules', 'implicit comparison through unresolved base key[0]'),
        ('refresh_rules', 'implicit iteration through unresolved base _pointer_key(base)'),
        ('refresh_rules', 'implicit result disposal through unresolved base _LOCK.release()'),
        ('refresh_rules', 'implicit subscript read through unresolved base key'),
        ('refresh_rules', 'implicit truth test through unresolved base _LOCK.acquire(blocking=False)'),
        ('refresh_rules', "implicit truth test through unresolved base key == ('absent',)"),
        ('refresh_rules', 'implicit truth test through unresolved base key == _KEY'),
        ('render_item', 'implicit iteration through unresolved base p'),
        ('render_item', 'implicit iteration through unresolved base parts'),
        ('render_item', 'implicit truth test through unresolved base none'),
        ('render_item', 'implicit truth test through unresolved base none and v is None'),
        ('render_line', 'implicit attribute read through unresolved base rule'),
        ('review_eval', 'implicit attribute read through unresolved base rm'),
        ('review_eval', 'implicit subscript read through unresolved base code_fingerprint()'),
        ('review_eval', 'implicit subscript read through unresolved base rm.CONTRACT_BOUNDS'),
        ('run_selftest', 'implicit comparison through unresolved base set(case)'),
        ('run_selftest', 'implicit comparison through unresolved base sorted(fired)'),
        ('run_selftest', 'implicit hashing through unresolved base tuple(t)'),
        ('run_selftest', "implicit iteration through unresolved base case['registry']"),
        ('run_selftest', 'implicit iteration through unresolved base cases'),
        ('run_selftest',
         "implicit iteration through unresolved base rs.evaluate_game(case['records'], case['match'], registry, budget=budget)"),
        ('run_selftest', 'implicit subscript read through unresolved base case'),
        ('run_selftest', 'implicit subscript read through unresolved base case'),
        ('run_selftest', 'implicit subscript read through unresolved base case'),
        ('run_selftest', 'implicit truth test through unresolved base errors'),
        ('run_selftest',
         "implicit truth test through unresolved base errors or sorted(fired) != sorted(case['fire'])"),
        ('run_selftest',
         "implicit truth test through unresolved base not isinstance(case, dict) or set(case) != {'records', 'match', 'registry', 'fire'}"),
        ('sitting_items', 'implicit attribute read through unresolved base rule'),
        ('sitting_items', "implicit binary operator through unresolved base (lo, hi, r['d'])"),
        ('sitting_items', "implicit comparison through unresolved base str(r['subject'])"),
        ('sitting_items', "implicit iteration through unresolved base norm_pair(r['subject'], r['opponent'])"),
        ('sitting_items', 'implicit iteration through unresolved base rows'),
        ('sitting_items', 'implicit iteration through unresolved base rule.show'),
        ('sitting_items', "implicit result disposal through unresolved base slot['items'].append(det)"),
        ('sitting_items', 'implicit subscript read through unresolved base d'),
        ('sitting_items', 'implicit subscript read through unresolved base grouped'),
        ('sitting_items', 'implicit subscript read through unresolved base grouped[k]'),
        ('sitting_items', 'implicit subscript read through unresolved base r'),
        ('sitting_items', 'implicit subscript read through unresolved base r'),
        ('sitting_items', 'implicit subscript read through unresolved base r'),
        ('sitting_items', 'implicit subscript read through unresolved base r'),
        ('sitting_items', 'implicit subscript read through unresolved base r'),
        ('sitting_items', 'implicit subscript read through unresolved base slot'),
        ('sitting_items', "implicit truth test through unresolved base d['subject_is_lo']"),
        ('sitting_selftest', 'implicit attribute read through unresolved base rs'),
        ('sitting_selftest', 'implicit binary operator through unresolved base set(binds)'),
        ('sitting_selftest', 'implicit comparison through unresolved base set(_BIND.findall(sql))'),
        ('sitting_selftest', 'implicit iteration through unresolved base rs.sitting_rules'),
        ('sitting_selftest', 'implicit iteration through unresolved base rs.sitting_statement(rule, mode)'),
        ('sitting_selftest',
         'implicit truth test through unresolved base set(_BIND.findall(sql)) != set(binds) | extra'),
        ('sitting_statement', 'implicit attribute read through unresolved base entry'),
        ('sitting_statement', 'implicit attribute read through unresolved base rule'),
        ('sitting_statement', 'implicit iteration through unresolved base rule.sitting'),
        ('sitting_statement', 'implicit subscript read through unresolved base entry.impl'),
    ],
    "backend/api/review_boot.py": [
        ('<module>', 'call of protocol-running callable os.path.abspath through unresolved base __file__'),
        ('<module>',
         'call of protocol-running callable os.path.dirname through unresolved base os.path.abspath(__file__)'),
        ('<module>', 'call of protocol-running callable review_rules.cli through unresolved base sys.argv[1:]'),
        ('<module>', 'call of unlisted callable review_rules.cli through unresolved base sys.argv[1:]'),
        ('SourceOnly.exec_module', 'call of protocol-running callable LOADED.pop through unresolved base stem'),
        ('SourceOnly.exec_module', 'call of protocol-running callable compile through unresolved base raw'),
        ('SourceOnly.exec_module',
         "call of protocol-running callable exec through unresolved base compile(raw, path, 'exec', dont_inherit=True)"),
        ('SourceOnly.exec_module', 'call of protocol-running callable open through unresolved base path'),
        ('SourceOnly.exec_module', 'call of protocol-running callable vars through unresolved base module'),
        ('SourceOnly.exec_module', 'call of unlisted callable compile through unresolved base raw'),
        ('SourceOnly.exec_module',
         "call of unlisted callable exec through unresolved base compile(raw, path, 'exec', dont_inherit=True)"),
        ('SourceOnly.exec_module', 'call of unlisted callable vars through unresolved base module'),
        ('SourceOnly.exec_module', 'unproven pure method call replace through unresolved base f.read()'),
        ('SourceOnly.find_spec',
         'call of protocol-running callable importlib.machinery.ModuleSpec through unresolved base fullname'),
        ('SourceOnly.find_spec',
         'call of unlisted callable importlib.machinery.ModuleSpec through unresolved base fullname'),
        ('SourceOnly.find_spec', 'unproven pure method call rpartition through unresolved base fullname'),
        ('_same_file', 'call of protocol-running callable isinstance through unresolved base path'),
        ('_same_file', 'call of protocol-running callable os.path.basename through unresolved base path'),
        ('_same_file',
         'call of protocol-running callable os.path.normcase through unresolved base os.path.realpath(path)'),
        ('_same_file',
         'call of protocol-running callable os.path.normcase through unresolved base os.path.realpath(source_path(stem))'),
        ('_same_file', 'call of protocol-running callable os.path.realpath through unresolved base path'),
        ('_same_file',
         'call of protocol-running callable os.path.realpath through unresolved base source_path(stem)'),
        ('_same_file', 'unproven pure method call lower through unresolved base os.path.basename(path)'),
        ('executed_elsewhere', 'call of protocol-running callable LOADED.get through unresolved base LOADED'),
        ('executed_elsewhere', 'call of protocol-running callable getattr through unresolved base mod'),
        ('executed_elsewhere', 'call of protocol-running callable list through unresolved base sys.modules.items()'),
        ('install', 'call of protocol-running callable isinstance through unresolved base f'),
        ('install', 'call of protocol-running callable sys.meta_path.insert through unresolved base FINDER'),
        ('install', 'call of unlisted callable sys.meta_path.insert through unresolved base FINDER'),
        ('source_path', 'call of protocol-running callable os.path.join through unresolved base HERE'),
        ('<module>', 'implicit attribute read through unresolved base sys'),
        ('<module>', 'implicit attribute read through unresolved base sys'),
        ('<module>', 'implicit subscript read through unresolved base sys.argv'),
        ('<module>', 'implicit subscript read through unresolved base sys.modules'),
        ('SourceOnly.exec_module', 'implicit attribute read through unresolved base module'),
        ('SourceOnly.exec_module', 'implicit result disposal through unresolved base LOADED.pop(stem, None)'),
        ('SourceOnly.exec_module',
         "implicit result disposal through unresolved base exec(compile(raw, path, 'exec', dont_inherit=True), vars(module))"),
        ('SourceOnly.find_spec', 'implicit attribute read through unresolved base importlib'),
        ('SourceOnly.find_spec', 'implicit binary operator through unresolved base (fullname, tail)'),
        ('SourceOnly.find_spec', 'implicit comparison through unresolved base fullname'),
        ('SourceOnly.find_spec', 'implicit comparison through unresolved base tail'),
        ('SourceOnly.find_spec', "implicit subscript read through unresolved base fullname.rpartition('.')"),
        ('SourceOnly.find_spec', 'implicit truth test through unresolved base fullname != tail'),
        ('_same_file', 'implicit binary operator through unresolved base stem'),
        ('_same_file', 'implicit comparison through unresolved base os.path.basename(path).lower()'),
        ('_same_file', 'implicit comparison through unresolved base os.path.normcase(os.path.realpath(path))'),
        ('_same_file',
         "implicit truth test through unresolved base not isinstance(path, str) or os.path.basename(path).lower() != stem + '.py'"),
        ('executed_elsewhere', 'implicit attribute read through unresolved base sys'),
        ('executed_elsewhere', 'implicit comparison through unresolved base name'),
        ('executed_elsewhere', 'implicit truth test through unresolved base _same_file(path, stem)'),
        ('executed_elsewhere',
         'implicit truth test through unresolved base _same_file(path, stem) and (not (name == stem and LOADED.get(stem, (None,))[0] is mod))'),
        ('executed_elsewhere', 'implicit truth test through unresolved base name == stem'),
        ('executed_elsewhere',
         'implicit truth test through unresolved base name == stem and LOADED.get(stem, (None,))[0] is mod'),
        ('install', 'implicit attribute read through unresolved base sys'),
        ('install', 'implicit attribute read through unresolved base sys'),
        ('install', 'implicit iteration through unresolved base sys.meta_path'),
        ('install', 'implicit result disposal through unresolved base sys.meta_path.insert(0, FINDER)'),
        ('source_path', 'implicit binary operator through unresolved base stem'),
    ],
}


def _lapsed(extra, kind):
    """With one planted site more, review_needles.py's exemption lapses: every
    row is reported, and the rows are exactly the REAL sites and the planted
    one, by name. Also: the exemption the proof carries names exactly the REAL
    sites of the module."""
    assert {k: sorted(v) for k, v in r3._MEASURED_CLEAN.items()} == {"review_needles.py": sorted(REAL[NEEDLES])}
    return _sites(extra, "review_needles.py", unresolved_only=False) == sorted(REAL[NEEDLES] + _planted(kind))


def test_m5_fix10_k_the_real_review_modules_keep_their_verdicts():
    """Every surface keeps its round 9 verdict by the same test; the
    real-module rule's measured unresolved-base sites hold, each named; the
    named module is exempt at exactly its measured sites, and one more such
    site lapses the exemption."""
    r3.test_m5_no_path_query_turns_a_failure_into_absence()
    root = os.path.join(HERE, "..", "..")
    for rel, sites in REAL.items():
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            src = f.read()
        assert _sites(src) == sorted(sites), (rel, _sites(src))
    with open(os.path.join(root, "backend/tools/review_needles.py"), encoding="utf-8") as f:
        src = f.read()
    assert _named_rows(src, "review_needles.py") == []
    extra = src + "\n\ndef _planted_extra(d):\n    d['k'] = 1\n"
    assert _lapsed(extra, "subscript store")


# -- fix pass 11: data flow through local calls, mutators, executors (r3._Flow) -------------
def _ns(defs, lines, imports=""):
    """GLOBALS_TD with `imports` and the module-level `defs` before scan,
    scan taking the caller-supplied mapping ns, and `lines` (one per line)
    at the head of scan, before the with around the proven walk."""
    return dict(header="import contextlib\n" + imports + "from tempfile import TemporaryDirectory\n"
                       + ("\n\n" + defs if defs else ""),
                scan="".join("    %s\n" % x for x in lines.split("\n")) + SUPPRESS % "TemporaryDirectory",
                edits=[("def scan(p):", "def scan(p, ns):")])


def _at(lines_text, kind):
    return ("    " + lines_text, kind)


ID = "def identity(x):\n    return x\n"
TD_LINE = '["TemporaryDirectory"] = contextlib.suppress'
EXEC_TEXT = '"import contextlib, tempfile; tempfile.TemporaryDirectory = contextlib.suppress"'
REBOUND11 = [
    ("a_report_scenario_verbatim", [
        (_ns(ID, "identity(ns)" + TD_LINE),
         [_at("identity(ns)" + TD_LINE, "subscript store through unresolved base identity(ns)")])]),
    ("b_two_local_hops", [
        (_ns("def passthrough(x):\n    return x\n\n\ndef identity(x):\n    return passthrough(x)\n",
             "identity(ns)" + TD_LINE),
         [_at("identity(ns)" + TD_LINE, "subscript store through unresolved base identity(ns)")])]),
    ("c_a_conditional_return", [
        (_ns("def pick(x, flag=True):\n    return x if flag else {}\n", "pick(ns)" + TD_LINE),
         [_at("pick(ns)" + TD_LINE, "subscript store through unresolved base pick(ns)")])]),
    ("d_a_container_passthrough", [
        (_ns("def pair(x):\n    return (x, 1)\n", "t = pair(ns)\nt[0]" + TD_LINE),
         [_at("t[0]" + TD_LINE, "subscript store through unresolved base t[0]")]),
        (_ns('def boxed(x):\n    return {"v": x}\n', 'boxed(ns)["v"]' + TD_LINE),
         [_at('boxed(ns)["v"]' + TD_LINE, "subscript store through unresolved base boxed(ns)['v']")])]),
    ("e_a_default_argument_passthrough", [
        (_ns("def either(x, y=None):\n    return y or x\n", "either(ns)" + TD_LINE),
         [_at("either(ns)" + TD_LINE, "subscript store through unresolved base either(ns)")])]),
    ("f_args_and_kwargs_forwarding", [
        (_ns("def first(*a):\n    return a[0]\n", "first(ns)" + TD_LINE),
         [_at("first(ns)" + TD_LINE, "subscript store through unresolved base first(ns)")]),
        (_ns('def named(**kw):\n    return kw["m"]\n', "named(m=ns)" + TD_LINE),
         [_at("named(m=ns)" + TD_LINE, "subscript store through unresolved base named(m=ns)")]),
        (_ns("def first(*a):\n    return a[0]\n\n\ndef fwd(*a, **kw):\n    return first(*a, **kw)\n", "fwd(ns)" + TD_LINE),
         [_at("fwd(ns)" + TD_LINE, "subscript store through unresolved base fwd(ns)")])]),
    ("g_mutator_methods_on_an_unresolved_receiver", [
        (_ns("", 'ns.update({"TemporaryDirectory": contextlib.suppress})'),
         [_at('ns.update({"TemporaryDirectory": contextlib.suppress})', "method call update through unresolved base ns")]),
        (_ns("", 'ns.setdefault("TemporaryDirectory", contextlib.suppress)'),
         [_at('ns.setdefault("TemporaryDirectory", contextlib.suppress)',
              "method call setdefault through unresolved base ns")]),
        (_ns("", 'ns.pop("TemporaryDirectory")'),
         [_at('ns.pop("TemporaryDirectory")', "method call pop through unresolved base ns")]),
        (_ns("", 'functools.partial(ns.__setitem__)("TemporaryDirectory", contextlib.suppress)', "import functools\n"),
         [_at('functools.partial(ns.__setitem__)("TemporaryDirectory", contextlib.suppress)',
              "bound method __setitem__ taken through unresolved base ns")]),
        (_ns("", 'functools.partial(ns.update)({"TemporaryDirectory": contextlib.suppress})', "import functools\n"),
         [_at('functools.partial(ns.update)({"TemporaryDirectory": contextlib.suppress})',
              "bound method update taken through unresolved base ns")]),
        (_ns("", 'operator.methodcaller("update", {"TemporaryDirectory": contextlib.suppress})(ns)', "import operator\n"),
         [_at('operator.methodcaller("update", {"TemporaryDirectory": contextlib.suppress})(ns)',
              "call of namespace-reaching operator.methodcaller")])]),
    ("h_chainmap_and_simplenamespace_over_the_mapping", [
        (_ns("", "ChainMap(ns)" + TD_LINE, "from collections import ChainMap\n"),
         [_at("ChainMap(ns)" + TD_LINE, "subscript store through unresolved base ChainMap(ns)")]),
        (_ns("", "cm = ChainMap(ns)\ncm.update(TemporaryDirectory=contextlib.suppress)", "from collections import ChainMap\n"),
         [_at("cm.update(TemporaryDirectory=contextlib.suppress)", "method call update through unresolved base cm")]),
        (_ns("", 'setattr(types.SimpleNamespace(**ns), "TemporaryDirectory", contextlib.suppress)', "import types\n"),
         [_at('setattr(types.SimpleNamespace(**ns), "TemporaryDirectory", contextlib.suppress)',
              "call of namespace-reaching setattr")])]),
    ("i_timeit", [
        (dict(header="import contextlib\nimport tempfile\nimport timeit\n"
                     'timeit.timeit("tempfile.TemporaryDirectory = contextlib.suppress", globals=globals())\n',
              scan=TD_WALK),
         [('timeit.timeit("tempfile.TemporaryDirectory = contextlib.suppress", globals=globals())',
           "call of namespace-reaching timeit.timeit"),
          ("import timeit", "import of namespace-reaching module timeit")]),
        (dict(header="import tempfile\nimport timeit\ntimeit.Timer(%s).timeit()\n" % EXEC_TEXT, scan=TD_WALK),
         [("timeit.Timer(%s).timeit()" % EXEC_TEXT, "call of namespace-reaching timeit.Timer"),
          ("import timeit", "import of namespace-reaching module timeit")]),
        (dict(header="import tempfile\nfrom timeit import repeat as again\nagain(%s, number=1)\n" % EXEC_TEXT,
              scan=TD_WALK),
         [("again(%s, number=1)" % EXEC_TEXT, "call of namespace-reaching again"),
          ("from timeit import repeat as again", "import of namespace-reaching module timeit")])]),
    ("j_the_other_executors", [
        (dict(header="import code\nimport tempfile\ncode.InteractiveInterpreter().runsource(%s)\n" % EXEC_TEXT,
              scan=TD_WALK),
         [("code.InteractiveInterpreter().runsource(%s)" % EXEC_TEXT,
           "call of namespace-reaching code.InteractiveInterpreter"),
          ("import code", "import of namespace-reaching module code")]),
        (dict(header="import pdb\nimport tempfile\npdb.run(%s)\n" % EXEC_TEXT, scan=TD_WALK),
         [("pdb.run(%s)" % EXEC_TEXT, "call of namespace-reaching pdb.run"),
          ("import pdb", "import of namespace-reaching module pdb")]),
        (dict(header="import cProfile\nimport tempfile\ncProfile.run(%s)\n" % EXEC_TEXT, scan=TD_WALK),
         [("cProfile.run(%s)" % EXEC_TEXT, "call of namespace-reaching cProfile.run"),
          ("import cProfile", "import of namespace-reaching module cProfile")]),
        (dict(header='import contextlib\nimport doctest\nimport tempfile\n\n\ndef _example():\n    """\n'
                     "    >>> tempfile.TemporaryDirectory = contextlib.suppress\n    \"\"\"\n\n\n"
                     'doctest.run_docstring_examples(_example, {"tempfile": tempfile, "contextlib": contextlib})\n',
              scan=TD_WALK),
         [('doctest.run_docstring_examples(_example, {"tempfile": tempfile, "contextlib": contextlib})',
           "call of namespace-reaching doctest.run_docstring_examples"),
          ("import doctest", "import of namespace-reaching module doctest")]),
        (dict(header="import marshal\nimport tempfile\nblob = marshal.dumps(compile(%s, 'm', 'exec'))\n"
                     "exec(marshal.loads(blob))\n" % EXEC_TEXT, scan=TD_WALK),
         [("exec(marshal.loads(blob))", "call of namespace-reaching marshal.loads"),
          ("import marshal", "import of namespace-reaching module marshal")]),
        (dict(header='import pickle\nimport tempfile\npayload = pickle.dumps(("tempfile", "TemporaryDirectory"))\n'
                     "pickle.loads(payload)\n", scan=TD_WALK),
         [("pickle.loads(payload)", "call of namespace-reaching pickle.loads"),
          ("import pickle", "import of namespace-reaching module pickle")])]),
]


@pytest.mark.parametrize("name,variants", REBOUND11, ids=[r[0] for r in REBOUND11])
def test_m5_fix11_a_local_flow_method_or_executor_reports_the_walk_naming_the_line(name, variants):
    for shape, expect in variants:
        _named(name, shape, expect)


FORMS11 = [
    ("class_instance_holding_its_argument",
     "class Box:\n    def __init__(self, x):\n        self.x = x\n", "Box(ns).x", "Box(ns).x"),
    ("lambda_binding", "ident = lambda x: x\n", "ident(ns)", "ident(ns)"),
    ("nested_function", "def outer(x):\n    def inner():\n        return x\n    return inner()\n",
     "outer(ns)", "outer(ns)"),
    ("decorated_function", "def deco(f):\n    return f\n\n\n@deco\ndef plain(x):\n    return {}\n",
     "plain(ns)", "plain(ns)"),
    ("walrus_binding", "def grab(x):\n    return (y := x)\n", "grab(ns)", "grab(ns)"),
    ("augmented_binding", "def gather(x):\n    acc = []\n    acc += [x]\n    return acc\n",
     "gather(ns)[0]", "gather(ns)[0]"),
    ("list_container", "def listed(x):\n    return [x]\n", "listed(ns)[0]", "listed(ns)[0]"),
    ("instance_holding_a_stored_value",
     "class Holder:\n    pass\n\n\ndef held(x):\n    h = Holder()\n    h.v = x\n    return h\n",
     "held(ns).v", "held(ns).v"),
    ("yield_from", "def chain(x):\n    yield from x\n", "next(chain(ns))", "next(chain(ns))"),
    ("exec_in_the_body", 'def run(x):\n    exec("pass")\n    return {}\n', "run(ns)", "run(ns)"),
    ("a_call_of_an_unresolved_callable", "def call(x, f):\n    f()\n    return {}\n", "call(ns, len)", "call(ns, len)"),
    ("a_try_that_swallows_and_rebinds",
     "def guarded(x):\n    try:\n        r = {}\n    except KeyError:\n        r = {}\n    return r\n",
     "guarded(ns)", "guarded(ns)"),
    ("a_global_written_from_a_parameter", "def stash(x):\n    global KEPT\n    KEPT = x\n    return KEPT\n",
     "stash(ns)", "stash(ns)"),
]


@pytest.mark.parametrize("name,defs,base,shown", FORMS11, ids=[f[0] for f in FORMS11])
def test_m5_fix11_every_listed_local_call_form_reports_the_walk_naming_the_line(name, defs, base, shown):
    _named(name, _ns(defs, base + TD_LINE), [_at(base + TD_LINE, "subscript store through unresolved base " + shown)])


def test_m5_fix11_a_write_through_an_unbound_name_stays_refused():
    """As at fix pass 10: a chain that starts at a name the module never binds,
    a builtin name included, is an unresolved base (the flow rates a builtin
    fresh as a callee, never as a base written through)."""
    for line, kind in (("print.marker = contextlib.suppress", "attribute store through unresolved base print"),
                       ("registry" + TD_LINE, "subscript store through unresolved base registry")):
        _named(line, _ns("", line), [_at(line, kind)])


def test_m5_fix11_k_a_benign_module_is_still_trusted():
    """A local function returning a fresh dict holding x whose result is
    written, one returning a constant, one returning a fresh object built
    from x, and timeit on a literal expression that rebinds nothing: nothing
    reaches a namespace, the walk is still proven. Fix pass 14: dict(x),
    len(x) and sorted(x) over a parameter run its protocols and are refused
    (r3 rule (8)'s protocol half), so the copy is a display holding x and the
    size is id(x), which runs no code of x."""
    src = _plant(header="import tempfile\nimport timeit\n\n\ndef copied(x):\n    return {\"v\": x}\n\n\n"
                        "def blank(x):\n    return {}\n\n\n"
                        'def sized(x):\n    return {"size": id(x), "names": [x]}\n',
                 scan='    copied(cfg)["root"] = p\n    blank(cfg)["root"] = p\n    sized(cfg)["size"] = 0\n'
                      '    timeit.timeit("sum(range(10))", number=1)\n'
                      "    with tempfile.TemporaryDirectory():\n        return list(os.walk(p, onerror=_walk_error))\n",
                 edits=[("def scan(p):", "def scan(p, cfg):")])
    assert r3.unwrapped_queries(src, "planted") == []
    assert _named_rows(src) == []


NEW11 = {"backend/tools/review_needles.py": [(933, "method call update through unresolved base h"),
                                             (1036, "method call pop through unresolved base found"),
                                             (1037, "method call pop through unresolved base found")],
         "backend/api/review_rules.py": [(n, "method call update through unresolved base h")
                                         for n in (132, 133, 137, 138, 139, 140)]
         + [(946, "method call update through unresolved base files"),
            (1198, "method call update through unresolved base files")],
         "backend/api/review_boot.py": []}
# Fix pass 14 (round 13 LOW 1): files is read by Python's scope rules, so in build_revision and
# closure_fingerprint it is the local set those functions build, no longer merged with the parameter
# of the same name elsewhere in review_rules.py: both of its fix 11 sites are proven and drop out.
NEW11["backend/api/review_rules.py"] = [(ln, k) for ln, k in NEW11["backend/api/review_rules.py"]
                                        if k != "method call update through unresolved base files"]


def test_m5_fix11_l_the_real_review_modules_keep_their_verdicts():
    """Every surface keeps its round 10 verdict by the same test; the sites
    the completed proof newly finds unresolved are exactly the measured,
    named ones (every one a mutator method, none from a local call); the
    named module is exempt at exactly its measured sites and one more such
    site lapses the exemption."""
    r3.test_m5_no_path_query_turns_a_failure_into_absence()
    root = os.path.join(HERE, "..", "..")
    for rel, new in NEW11.items():
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            src = f.read()
        unresolved = [x for x in _named_rows(src, "<source>") if r3._unresolved(x[1])]
        assert [x for x in unresolved if x[1].startswith(("method call ", "bound method "))
                and x[1].split()[2] in r3._MUTATORS] == new, rel     # fix 13: the fix 11 names (h pins the rest)
        assert _sites(src) == sorted(REAL[rel]), (rel, unresolved)
    with open(os.path.join(root, "backend/tools/review_needles.py"), encoding="utf-8") as f:
        src = f.read()
    assert _named_rows(src, "review_needles.py") == []
    extra = src + "\n\ndef _planted_extra(d):\n    d.update(k=1)\n"
    assert _sites(extra, "review_needles.py", unresolved_only=False) == sorted(
        REAL[NEEDLES] + _planted("method call update")
        + [("_planted_extra",
            "implicit result disposal through unresolved base d.update(k=1)")])


# -- fix pass 12: slices, copies, iteration, callbacks, in-place operators (r3._Flow) -----
TDV = '{"TemporaryDirectory": contextlib.suppress}'
U = " through unresolved base "


def _in(lines_text, kind):
    """An expected row for a line one block deeper than _at's."""
    return ("        " + lines_text, kind)


def _v(defs, lines, expect, imports="", params="p, ns"):
    """One variant: _ns with scan taking `params`, and its expected rows."""
    shape = _ns(defs, lines, imports)
    return (dict(shape, edits=[("def scan(p):", "def scan(%s):" % params)]), expect)


SLICES = ("def head(seq):\n    return seq[0:]\n\n\ndef back(seq):\n    return seq[::-1]\n\n\n"
          "def last(seq):\n    return seq[-1:]\n\n\ndef tail(x):\n    return x[:]\n")
HIGHER = (ID + "\n\ndef apply(f, v):\n    return f(v)\n\n\ndef make(x):\n    def get():\n        return x\n"
          "    return get\n\n\nclass Keeper:\n    def __init__(self, v):\n        self.v = v\n\n"
          "    def get(self, _=None):\n        return self.v\n")
FETCH = "def fetch(_=None):\n    return ns\n"


def _store(base, defs="", imports=""):
    shown = r3.ast.unparse(r3.ast.parse(base).body[0].value)     # the report's own rendering of the base
    return _v(defs, base + TD_LINE, [_at(base + TD_LINE, "subscript store" + U + shown)], imports)


def _fetched(base):
    """A local callback closing over ns, consumed by `base` (round 11 L)."""
    return _v("", FETCH + base + TD_LINE, [_at(base + TD_LINE, "subscript store" + U + base)])


REBOUND12 = [
    ("a_report_scenario_verbatim", [
        _v("", "ns |= " + TDV, [_at("ns |= " + TDV, "augmented assignment |=" + U + "ns")])]),
    ("b_the_slice_aliases", [
        _store("head([ns])[0]", SLICES), _store("back([ns])[0]", SLICES), _store("last([ns])[0]", SLICES),
        _store("tail(ns)", SLICES), _store("[ns][0:][0]"), _store("[ns][::-1][0]"),
        _v(SLICES, "head([ns])[0] |= " + TDV,
           [_at("head([ns])[0] |= " + TDV, "augmented subscript store |=" + U + "head([ns])")]),
        _v(SLICES, "m = last([ns])[0]\nm |= " + TDV, [_at("m |= " + TDV, "augmented assignment |=" + U + "m")]),
        _v("", "[ns][:][0] |= " + TDV, [_at("[ns][:][0] |= " + TDV, "augmented assignment |=" + U + "[ns][:][0]")])]),
    ("c_unpacking_and_iteration", [
        _v("", "first, *rest = [None, ns]\nrest[0]" + TD_LINE, [_at("rest[0]" + TD_LINE, "subscript store" + U + "rest[0]")]),
        _v("", "a, b = [ns, None]\na" + TD_LINE, [_at("a" + TD_LINE, "subscript store" + U + "a")]),
        _v("", "for m in (ns,):\n    m" + TD_LINE, [_in("m" + TD_LINE, "subscript store" + U + "m")]),
        _store("tuple([ns])[0]"), _store("list(reversed([ns]))[0]"), _store("sorted([ns], key=id)[0]"),
        _store("next(iter([ns]))"), _store("next(itertools.islice([ns], 1))", imports="import itertools\n"),
        _store("next(itertools.chain([ns]))", imports="import itertools\n"), _store("next(zip([ns]))[0]"),
        _store("list(enumerate([ns]))[0][1]"), _store("[m for m in [ns]][0]"), _store("next(m for m in [ns])"),
        _store("operator.getitem([ns], 0)", imports="import operator\n"), _store("sum([[ns]], [])[0]"),
        _v("", "with contextlib.nullcontext(ns) as m:\n    m" + TD_LINE,
           [_in("m" + TD_LINE, "subscript store" + U + "m")])]),
    ("d_the_higher_order_forms", [
        _store("list(map(identity, [ns]))[0]", HIGHER), _store("next(filter(None, [ns]))"),
        _v("", "functools.reduce(lambda a, b: b, [ns])" + TD_LINE,
           [_at("functools.reduce(lambda a, b: b, [ns])" + TD_LINE,
                "subscript store through namespace-reaching functools.reduce(lambda a, b: b, [ns])"),
            _at("functools.reduce(lambda a, b: b, [ns])" + TD_LINE, "call of namespace-reaching functools.reduce")],
           "import functools\n"),
        _store("[identity(x) for x in [ns]][0]", HIGHER), _store("apply(identity, ns)", HIGHER),
        _store("apply(lambda m: m, ns)", HIGHER), _store("functools.partial(identity)(ns)", HIGHER, "import functools\n"),
        _v("", "operator.itemgetter(0)([ns])" + TD_LINE,
           [_at("operator.itemgetter(0)([ns])" + TD_LINE,
                "subscript store through namespace-reaching operator.itemgetter(0)([ns])"),
            _at("operator.itemgetter(0)([ns])" + TD_LINE, "call of namespace-reaching operator.itemgetter")],
           "import operator\n"),
        _store("make(ns)()", HIGHER), _store("next(map(Keeper(ns).get, [1]))", HIGHER),
        _store("next(map(lambda _: ns, [1]))"), _store("next(map(make(ns), [1]))", HIGHER),
        _store("next(map(unbound_callable, [1]))"),
        _fetched("next(map(fetch, [1]))"), _fetched("next(iter(fetch, None))"), _fetched("next(filter(fetch, [1]))"),
        _fetched("sorted([1], key=fetch)[0]"), _fetched("max([1], key=fetch)"), _fetched("min([1], key=fetch)")]),
    ("e_the_in_place_forms", [
        _v("", "ns |= " + TDV, [_at("ns |= " + TDV, "augmented assignment |=" + U + "ns")]),
        _v("", "alias = ns\nalias |= " + TDV, [_at("alias |= " + TDV, "augmented assignment |=" + U + "alias")]),
        _v("", "ns.__ior__(%s)" % TDV, [_at("ns.__ior__(%s)" % TDV, "method call __ior__" + U + "ns")]),
        _v("", "merge = ns.__ior__\nmerge(%s)" % TDV, [_at("merge = ns.__ior__", "bound method __ior__ taken" + U + "ns")]),
        _v("", "operator.ior(ns, %s)" % TDV, [_at("operator.ior(ns, %s)" % TDV, "in-place call operator.ior" + U + "ns")],
           "import operator\n"),
        _v("", "merge_in(ns, %s)" % TDV, [_at("merge_in(ns, %s)" % TDV, "in-place call merge_in" + U + "ns")],
           "from operator import ior as merge_in\n"),
        _v("", "functools.partial(operator.ior, ns)(%s)" % TDV,
           [_at("functools.partial(operator.ior, ns)(%s)" % TDV, "in-place operator operator.ior taken as a value")],
           "import functools\nimport operator\n"),
        _v("", "(ns,)[0] |= " + TDV, [_at("(ns,)[0] |= " + TDV, "augmented assignment |=" + U + "(ns,)[0]")]),
        _v("", "for m in [ns]:\n    m |= " + TDV, [_in("m |= " + TDV, "augmented assignment |=" + U + "m")]),
        _v("", "with contextlib.nullcontext(ns) as m:\n    m |= " + TDV,
           [_in("m |= " + TDV, "augmented assignment |=" + U + "m")]),
        _v("", "collections.ChainMap(ns).maps[0] |= " + TDV,
           [_at("collections.ChainMap(ns).maps[0] |= " + TDV,
                "augmented subscript store |=" + U + "collections.ChainMap(ns).maps")], "import collections\n"),
        _v(HIGHER, "list(map(identity, [ns]))[0] |= " + TDV,
           [_at("list(map(identity, [ns]))[0] |= " + TDV, "augmented assignment |=" + U + "list(map(identity, [ns]))[0]")]),
        _v("", FETCH + "m = next(map(fetch, [1]))\nm |= " + TDV, [_at("m |= " + TDV, "augmented assignment |=" + U + "m")]),
        _v("", "handlers += [contextlib.suppress]",
           [_at("handlers += [contextlib.suppress]", "augmented assignment +=" + U + "handlers")],
           params="p, ns, handlers")]),
]


@pytest.mark.parametrize("name,variants", REBOUND12, ids=[r[0] for r in REBOUND12])
def test_m5_fix12_a_slice_callback_or_in_place_form_reports_the_walk_naming_the_line(name, variants):
    for shape, expect in variants:
        _named(name, shape, expect)


INPLACE12 = [(sym, op) for op, sym in [(o, r3._AUG_OPS[t]) for o, t in zip(
    ("add", "sub", "mul", "matmul", "truediv", "floordiv", "mod", "pow", "lshift", "rshift", "and", "xor", "or"),
    (r3.ast.Add, r3.ast.Sub, r3.ast.Mult, r3.ast.MatMult, r3.ast.Div, r3.ast.FloorDiv, r3.ast.Mod, r3.ast.Pow,
     r3.ast.LShift, r3.ast.RShift, r3.ast.BitAnd, r3.ast.BitXor, r3.ast.BitOr))]]


@pytest.mark.parametrize("sym,op", INPLACE12, ids=[o for _s, o in INPLACE12])
def test_m5_fix12_every_in_place_operator_on_an_unresolved_receiver_is_refused(sym, op):
    """No operator is exempt: the augmented assignment, its dunder method and
    its operator function, each on the caller-supplied mapping."""
    for line, kind, imports in (("ns %s %s" % (sym, TDV), "augmented assignment %s%sns" % (sym, U), ""),
                                ("ns.__i%s__(%s)" % (op, TDV), "method call __i%s__%sns" % (op, U), ""),
                                ("operator.i%s(ns, %s)" % (op, TDV), "in-place call operator.i%s%sns" % (op, U),
                                 "import operator\n")):
        shape, expect = _v("", line, [_at(line, kind)], imports)
        _named(op, shape, expect)


def _exact_rebinds(name, shape, expect):
    """One os.walk row carrying exactly the planted implicit-protocol row."""
    src = _plant(**shape)
    rows = r3.unwrapped_queries(src, "planted")
    assert [kind for _line_no, kind in rows] == ["os.walk"], (name, rows)
    row, = rows
    assert row.rebinds == tuple(
        ("planted", _line(src, text), kind) for text, kind in expect), (name, rows)


def test_m5_fix12_f_a_benign_module_is_still_trusted():
    """Augmented assignments on a dict copy, a dict display over a local
    mapping, a local counter and a local list; an exact local binary union;
    map over a builtin; a slice of a literal list and a sort of fresh
    mappings written through: nothing reaches a namespace, the walk is still
    proven. The former unresolved ns union remains paired as an exact red."""
    lines = ("seed = {}\nfresh = dict(seed)\nfresh |= %s\nmerged = {**seed}\nmerged |= %s\n"
             'combined = seed | {}\ncount = 0\n'
             "count += 1\n"
             'names = []\nnames += ["x"]\nlabels = list(map(str, [1, 2]))\nlabels[0] = "x"\nv = "fresh"\n'
             'rows = [{}, {}][0:1]\nrows[0]["k"] = v\nsorted([{}, {}])[0]["k"] = v') % (TDV, TDV)
    shape, _e = _v("", lines, [])
    src = _plant(**shape)
    assert r3.unwrapped_queries(src, "planted") == []
    assert _named_rows(src) == []
    old = "ns = ns | %s" % TDV
    _exact_rebinds("binary", *_v("", old, [_at(old, "implicit binary operator" + U + "ns")]))


NEW12 = {"backend/tools/review_needles.py": [(999, "augmented assignment += through unresolved base body")],
         "backend/api/review_rules.py": [], "backend/api/review_boot.py": []}
# Fix pass 14 (round 13 LOW 2): an operator over an unresolved operand is unresolved, never a holder,
# so _read_verified's left (cap + 1, cap a parameter) joins the in-place sites by its -=; named here by
# site identity (and in REAL), and test g compares the other in-place rows to NEW12 as before.
NEW12_14 = {"backend/api/review_rules.py": [("_read_verified", "augmented assignment -= through unresolved base left")]}


def test_m5_fix12_g_the_real_review_modules_keep_their_verdicts():
    """Every surface keeps its round 11 verdict by the same test; the sites the
    in-place rule newly finds are exactly the measured, named ones (the fix
    11 method sites stand, test l); the named module is exempt at exactly
    its measured sites and one more in-place site lapses the exemption."""
    r3.test_m5_no_path_query_turns_a_failure_into_absence()
    root = os.path.join(HERE, "..", "..")
    for rel, new in NEW12.items():
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            src = f.read()
        unresolved = [x for x in _named_rows(src, "<source>") if r3._unresolved(x[1])]
        inplace = [(ln, k) for ln, k in unresolved if k.startswith(("augmented assignment ", "in-place "))]
        tree, later = r3.ast.parse(src), NEW12_14.get(rel, [])     # fix 14: the operator-result sites
        assert [x for x in inplace if r3._only(r3._site_names(tree, [x])) not in later] == new, rel
        assert sorted(s for s in r3._site_names(tree, inplace) if s in later) == sorted(later), rel
        assert _sites(src) == sorted(REAL[rel]), (rel, unresolved)
    with open(os.path.join(root, "backend/tools/review_needles.py"), encoding="utf-8") as f:
        src = f.read()
    assert _named_rows(src, "review_needles.py") == []
    extra = src + "\n\ndef _planted_extra(d):\n    d |= {}\n"
    assert _lapsed(extra, "augmented assignment |=")


# -- fix pass 13: the binding table, fail-closed calls and methods, the constant index ---------
OPS = "ops = [operator.ior]\n"
OPCALL = "op(ns, %s)" % TDV
SUP = "contextlib.suppress"
IOR = "import operator\n"


def _rows13(line, kinds, defs="", lines=None, imports="", params="p, ns", deep=False):
    """A variant whose refused line is `line` (one block deeper when deep),
    carrying every kind in `kinds` (each a callee or method kind + U + base)."""
    at = _in if deep else _at
    return _v(defs, line if lines is None else lines, [at(line, k) for k in kinds], imports, params)


def _op13(callee, line=None, defs="", lines=None, params="p, ns", deep=False, unresolved=False):
    """An in-place operator delivered to its call site: the call names the
    delivered callee as unlisted and as an in-place call (and as unresolved
    when a caller may supply it)."""
    kinds = ["call of unlisted callable %s%sns" % (callee, U), "in-place call %s%sns" % (callee, U)]
    if unresolved:
        kinds.append("call of unresolved callable %s%sns" % (callee, U))
    return _rows13(line or OPCALL, kinds, defs, lines, IOR, params, deep)


def _mut13(line, method, base, params="p, ns, handlers"):
    return _rows13(line, ["method call %s%s%s" % (method, U, base)], params=params)


H = "p, ns, handlers"
REBOUND13 = [
    ("a_loop_delivered_operators", [
        _op13("op", defs=OPS, lines="for op in ops:\n    " + OPCALL, deep=True),
        _rows13(OPCALL, ["call of unresolved callable op%sns" % U], lines="for op in ops:\n    " + OPCALL,
                params="p, ns, ops", deep=True),
        _op13("op", lines="with contextlib.nullcontext(operator.ior) as op:\n    " + OPCALL, deep=True),
        _op13("(op := operator.ior)", "(op := operator.ior)(ns, %s)" % TDV),
        _op13("op", "[%s for op in ops]" % OPCALL, defs=OPS),
        _op13("last", "last(ns, %s)" % TDV, lines="*first, last = [operator.ior]\nlast(ns, %s)" % TDV),
        _op13("op", lines="def f(op=operator.ior):\n    %s\nf()" % OPCALL, deep=True, unresolved=True),
        _op13("op", lines="if (op := operator.ior):\n    " + OPCALL, deep=True)]),
    ("b_identity_preserving_calls", [
        _rows13("m" + TD_LINE, ["subscript store" + U + "m"], lines="m = iter(ns)\nm" + TD_LINE),
        _rows13("m |= " + TDV, ["augmented assignment |=" + U + "m"], lines="m = reversed(ns)\nm |= " + TDV),
        _rows13("operator.ior(iter(ns), %s)" % TDV, ["in-place call operator.ior" + U + "iter(ns)"], imports=IOR),
        _store("next(iter([ns]))"),
        _rows13("functools.reduce(lambda a, b: b, [ns])" + TD_LINE,
                ["subscript store through namespace-reaching functools.reduce(lambda a, b: b, [ns])"],
                imports="import functools\n"),
        _rows13("m" + TD_LINE, ["subscript store" + U + "m"], lines="m = min([ns], key=id)\nm" + TD_LINE),
        _rows13("m" + TD_LINE, ["subscript store" + U + "m"], lines="m = max(ns, key=len)\nm" + TD_LINE),
        _rows13("m" + TD_LINE, ["subscript store" + U + "m"], lines="m = next(ns)\nm" + TD_LINE),
        _rows13("next(m)" + TD_LINE, ["subscript store" + U + "next(m)"],
                lines="m = iter(lambda: ns, None)\nnext(m)" + TD_LINE),
        _rows13("m" + TD_LINE, ["subscript store" + U + "m"], lines="m = ns.copy()\nm" + TD_LINE),
        _rows13("m" + TD_LINE, ["subscript store" + U + "m"], lines="m = copy.copy(ns)\nm" + TD_LINE,
                imports="import copy\n")]),
    ("c_collection_mutators", [
        _mut13("handlers.append(%s)" % SUP, "append", "handlers"),
        _mut13('ns["handlers"].append(%s)' % SUP, "append", "ns['handlers']"),
        _mut13("ns.group.add(%s)" % SUP, "add", "ns.group"),
        _mut13('ns["handlers"].extend([%s])' % SUP, "extend", "ns['handlers']"),
        _mut13('ns["handlers"].insert(0, %s)' % SUP, "insert", "ns['handlers']"),
        _mut13("ns.group.update({%s})" % SUP, "update", "ns.group"),
        _mut13("handlers.sort(key=id)", "sort", "handlers"),
        _mut13("handlers.reverse()", "reverse", "handlers"),
        _rows13("handlers += [%s]" % SUP, ["augmented assignment +=" + U + "handlers"], params=H),
        _rows13("ns.group |= {%s}" % SUP, ["augmented attribute store |=" + U + "ns"])]),
    ("d_extracted_bound_methods", [
        _v("", "add = handlers.append\nadd(%s)" % SUP,
           [_at("add = handlers.append", "bound method append taken" + U + "handlers"),
            _at("add(%s)" % SUP, "call of unresolved callable add" + U + "add")], params=H),
        _rows13('getattr(handlers, "append")(%s)' % SUP,
                ["call of unresolved callable getattr(handlers, 'append')" + U + "getattr(handlers, 'append')"],
                params=H),
        _rows13('operator.methodcaller("append", %s)(handlers)' % SUP,
                ["call of unresolved callable operator.methodcaller('append', contextlib.suppress)" + U + "handlers"],
                imports=IOR, params=H),
        _rows13("functools.partial(handlers.append, %s)()" % SUP,
                ["bound method append taken" + U + "handlers",
                 "call of unresolved callable functools.partial(handlers.append, contextlib.suppress)" + U
                 + "functools.partial(handlers.append, contextlib.suppress)"], imports="import functools\n", params=H),
        _rows13("list(map(handlers.append, [%s]))" % SUP,
                ["bound method append taken" + U + "handlers", "callback method append of map" + U + "handlers"],
                params=H),
        _v("", "for a in [handlers.append]:\n    a(%s)" % SUP,
           [_at("for a in [handlers.append]:", "bound method append taken" + U + "handlers"),
            _in("a(%s)" % SUP, "call of unresolved callable a" + U + "a")], params=H),
        _v(HIGHER, "apply(handlers.append, %s)" % SUP,
           [_at("apply(handlers.append, %s)" % SUP, "bound method append taken" + U + "handlers"),
            ("    return f(v)", "call of unresolved callable f" + U + "v")], params=H),
        _rows13("[handlers.append][0](%s)" % SUP,
                ["bound method append taken" + U + "handlers",
                 "call of unresolved callable [handlers.append][0]" + U + "[handlers.append][0]"], params=H)]),
    ("e_the_fail_closed_method_gate", [
        _rows13("ns.frobnicate(%s)" % SUP, ["method call frobnicate" + U + "ns"]),
        _rows13("f(%s)" % SUP, ["call of unresolved callable f" + U + "f"], lines="f = ns.frobnicate\nf(%s)" % SUP)]),
    ("f_the_constant_index_refused", [
        _rows13('[ns, {}][0]["k"] = 1', ["subscript store" + U + "[ns, {}][0]"]),
        _rows13('({}, ns)[-1]["k"] = 1', ["subscript store" + U + "({}, ns)[-1]"]),
        _rows13('[ns, {}][i]["k"] = 1', ["subscript store" + U + "[ns, {}][i]"], params="p, ns, i"),
        _rows13('[ns, {}][5]["k"] = 1', ["subscript store" + U + "[ns, {}][5]"])]),
]


@pytest.mark.parametrize("name,variants", REBOUND13, ids=[r[0] for r in REBOUND13])
def test_m5_fix13_a_to_f_each_route_reports_the_walk_naming_the_refused_line(name, variants):
    for shape, expect in variants:
        _named(name, shape, expect)


def test_m5_fix13_every_binding_class_of_the_grammar_is_in_the_table():
    """Every ast node class that carries a binding field is dispatched by the
    binding table (r3._BINDING_TABLE); the enumeration is of the running
    interpreter's ast module, so a new grammar form fails here first."""
    carrying = sorted((c for c in vars(r3.ast).values() if isinstance(c, type) and issubclass(c, r3.ast.AST)
                       and r3._BIND_FIELDS & set(c._fields)), key=lambda c: c.__name__)
    assert len(carrying) >= 25
    assert [c.__name__ for c in carrying if c not in r3._BINDING_TABLE] == []
    for c in (r3.ast.For, r3.ast.AsyncFor, r3.ast.With, r3.ast.AsyncWith, r3.ast.NamedExpr, r3.ast.comprehension,
              r3.ast.ExceptHandler, r3.ast.MatchAs, r3.ast.MatchStar, r3.ast.MatchMapping, r3.ast.Global,
              r3.ast.Nonlocal, r3.ast.Import, r3.ast.ImportFrom, r3.ast.arguments, r3.ast.Assign, r3.ast.AnnAssign,
              r3.ast.AugAssign, r3.ast.Delete, r3.ast.FunctionDef, r3.ast.AsyncFunctionDef, r3.ast.ClassDef):
        assert c in carrying or c in (r3.ast.With, r3.ast.AsyncWith), c.__name__    # a With binds by withitem
    assert r3.ast.withitem in r3._BINDING_TABLE


LOOP13 = "for k in [ns]:\n    id(k)"       # exact local iterable; the unresolved spelling is paired below


class _Loop(r3.ast.For):
    """A binding node of a class the table does not hold (the gate control)."""


def test_m5_fix13_e_a_node_outside_the_table_refuses_the_walk_naming_its_line(monkeypatch):
    """The gate is live: the exact-local loop is trusted as parsed; the same loop
    as a node of a class outside the table, and the plain loop with the
    table narrowed through the seam the proof exposes, each refuse the walk
    naming the loop's line; the old unresolved iterable is an exact red."""
    shape, _e = _v("", LOOP13, [])
    src = _plant(**shape)
    assert r3.unwrapped_queries(src, "planted") == []
    old = "for k in ns:\n    id(k)"
    _exact_rebinds("loop", *_v("", old, [_at("for k in ns:", "implicit iteration" + U + "ns")]))
    line = _line(src, "    for k in [ns]:")
    tree = r3.ast.parse(src)
    loops = [n for n in r3.ast.walk(tree) if isinstance(n, r3.ast.For) and n.lineno == line]
    assert len(loops) == 1
    loops[0].__class__ = _Loop
    rows = r3.unwrapped_queries(src, "planted", tree=tree)
    assert [k for _l, k in rows] == ["os.walk"], rows
    assert ("planted", line, "binding form _Loop outside the binding table") in rows[0].rebinds, rows
    monkeypatch.delitem(r3._BINDING_TABLE, r3.ast.For)
    rows = r3.unwrapped_queries(src, "planted")
    assert [k for _l, k in rows] == ["os.walk"], rows
    assert ("planted", line, "binding form For outside the binding table") in rows[0].rebinds, rows


def test_m5_fix13_f_a_constant_index_selects_its_own_element():
    """Round 12 LOW 1: a constant index into a display selects that element's
    own mark, a negative one resolved statically: both fresh selections are
    trusted, the walk still proven (the refused selections are control f)."""
    shape, _e = _v("", 'fresh = [ns, {}][1]\nfresh["k"] = 1\n[{}, ns][-2]["k"] = 1', [])
    src = _plant(**shape)
    assert r3.unwrapped_queries(src, "planted") == []
    assert _named_rows(src) == []


def test_m5_fix13_g_a_benign_module_is_still_trusted():
    """Every fix 12 (f) item, and: iteration over an exact local list, a local list appended
    to, a dict copy updated, a local operator called on constants, a builtin
    delivered by a loop over a local, the pure methods, len, a membership
    test and a sort of its keys on a local dict, and an element taken by get
    from a local dict and appended to: still trusted, walk proven. Fix pass
    14: the pure methods, len and sorted over ns itself, and a builtin called
    on ns, are refused (an unproven receiver, a protocol-running call), so
    they run on a local dict here."""
    test_m5_fix12_f_a_benign_module_is_still_trusted()
    lines = (LOOP13 + '\nhandlers = []\nhandlers.append(1)\nseed = {"k": []}\nfresh = dict(seed)\nfresh.update(%s)\n'
             'local = [1]\nlocal.append(2)\nop = operator.add\nop(1, 2)\nfor f in [len]:\n    f(seed)\nseed.get("k")\n'
             'seed.keys()\nlen(seed)\n"k" in seed\nx = sorted(seed.keys())\ngot = seed.get("k")\ngot.append(1)') % TDV
    shape, _e = _v("", lines, [], IOR)
    src = _plant(**shape)
    assert r3.unwrapped_queries(src, "planted") == []
    assert _named_rows(src) == []


RULE_NAMES13 = ("subscript store", "attribute store", "subscript deletion", "attribute deletion",
                "augmented subscript store", "augmented attribute store", "augmented assignment", "method call",
                "bound method", "callback method", "callback of", "call of unlisted callable",
                "call of unresolved callable", "in-place call", "implicit",
                "unproven pure method call", "call of protocol-running callable")      # the last two: fix 14


def _rule13(kind):
    return max((r for r in RULE_NAMES13 if kind.startswith(r + " ")), key=len)


NEW13 = sorted([(n, "method call add" + U + b) for n, b in (
    (237, "out['basename']"), (263, "out['nonce']"), (266, "out['rule_id']"), (270, "out['wording']"),
    (272, "out['data']"), (275, "out['data']"))] + [(255, "method call read" + U + "f")] + [
    (381, "method call add" + U + "self"), (384, "method call append" + U + "self.lists"),
    (389, "method call append" + U + "self.items")] + [
    (n, "method call add" + U + "vals") for n in (402, 436, 453, 478, 482, 487)] + [
    (631, "method call add" + U + "by_group.setdefault(group, set())")])
# Fix pass 14 (round 13 LOW 1): _revision's f.read() reads the f its own with statement binds, no
# longer merged with the comprehension variable of the same name: the site is proven and drops out.
NEW13 = [(ln, k) for ln, k in NEW13 if k != "method call read" + U + "f"]


def test_m5_fix13_h_the_real_review_modules_keep_their_verdicts():
    """Every surface keeps its round 12 verdict by the same test; each rule's
    unresolved sites are named per module (the rule, the operator or method,
    the base and the enclosing function or class: REAL), each named row one
    of the rules, and review_needles.py's new sites are exactly the measured,
    named ones (every one a method the fail-closed gate no longer takes as
    pure); the named module is exempt at exactly its measured sites and one
    more unlisted method lapses it."""
    r3.test_m5_no_path_query_turns_a_failure_into_absence()
    root = os.path.join(HERE, "..", "..")
    for rel, sites in REAL.items():
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            src = f.read()
        unresolved = [x for x in _named_rows(src, "<source>") if r3._unresolved(x[1])]
        assert _sites(src) == sorted(sites), (rel, unresolved)
        assert {_rule13(k) for _s, k in sites} <= set(RULE_NAMES13), rel
    with open(os.path.join(root, "backend/tools/review_needles.py"), encoding="utf-8") as f:
        src = f.read()
    rows = [x for x in _named_rows(src, "<source>") if r3._unresolved(x[1])]
    assert [x for x in rows if x[1].startswith("method call ") and x[1].split()[2] not in r3._MUTATORS] == NEW13
    assert _named_rows(src, "review_needles.py") == []
    extra = src + "\n\ndef _planted_extra(d):\n    d.frobnicate(1)\n"
    assert _sites(extra, "review_needles.py", unresolved_only=False) == sorted(
        REAL[NEEDLES] + _planted("method call frobnicate")
        + [("_planted_extra",
            "implicit result disposal through unresolved base d.frobnicate(1)")])


# -- fix pass 14: imported namespaces, unproven receivers and protocols, scopes, identity --------
WALKX = "lambda *args, **kwargs: ()"
NSR = " through namespace-reaching "
IMP = " through imported namespace "
GUARD14 = "    if type(p) is not str:\n"


def _header14(text, line, kind):
    """A variant planted at module level (no parameter), its refused line `line`."""
    return (dict(header=text), [(line, kind)])


REBOUND14 = [
    ("a_report_input_verbatim", [
        _header14('from os import __dict__ as ns\nns["walk"] = %s\n' % WALKX, 'ns["walk"] = ' + WALKX,
                  "subscript store" + NSR + "ns")]),
    ("b_dynamic_member_through_an_import_alias", [
        _header14('from os import __builtins__ as _bi\n_bi["list"] = %s\n' % WALKX, '_bi["list"] = ' + WALKX,
                  "subscript store" + NSR + "_bi")]),
    ("c_store_through_an_imported_object", [
        _header14("import os as _o\n_o.walk = %s\n" % WALKX, "_o.walk = " + WALKX, "attribute store" + IMP + "_o"),
        _header14("from posixpath import os as _o2\n_o2.walk = %s\n" % WALKX, "_o2.walk = " + WALKX,
                  "attribute store" + IMP + "_o2")]),
    ("d_imported_object_handed_to_unlisted_code", [
        _header14("import functools\nimport os.path as _osp\n\n\ndef _fake():\n    pass\n\n\n_fake.islink = %s\n"
                  "functools.update_wrapper(_osp, _fake)\n" % WALKX, "functools.update_wrapper(_osp, _fake)",
                  "call of unlisted callable functools.update_wrapper" + IMP + "_osp")]),
    ("e_mutator_through_an_imported_object", [
        _header14('from os import environ as _env\n_env.update(HOME="x")\n', '_env.update(HOME="x")',
                  "method call update" + IMP + "_env")]),
    ("f_name_only_get", [_v("", 'ns.get("walk")', [_at('ns.get("walk")', "unproven pure method call get" + U + "ns")])]),
    ("g_protocol_running_allowlisted_call", [
        _v("", "os.fspath(ns)", [_at("os.fspath(ns)", "call of protocol-running callable os.fspath" + U + "ns")]),
        _v("", "len(ns)", [_at("len(ns)", "call of protocol-running callable len" + U + "ns")]),
        _v("", "names = list(map(str, [ns]))", [_at("names = list(map(str, [ns]))",
                                                    "callback of map (protocol-running callable str)" + U + "[ns]")])]),
    ("h_a_type_guard_of_a_module_class_proves_nothing", [
        (dict(header="\n\nclass _Path(str):\n    pass\n",
              edits=[(GUARD14, GUARD14.replace("str", "_Path"))]),
         [("    return list(os.walk(p, onerror=_walk_error))", "call of protocol-running callable os.walk" + U + "p")]),
        # an imported class resolves to one dotted name that is no builtin scalar: the guard proves nothing
        (dict(header="from pathlib import PurePath\n",
              edits=[(GUARD14, GUARD14.replace("str", "PurePath"))]),
         [("    return list(os.walk(p, onerror=_walk_error))", "call of protocol-running callable os.walk" + U + "p")])]),
]


@pytest.mark.parametrize("name,variants", REBOUND14, ids=[name for name, _variants in REBOUND14])
def test_m5_fix14_a_each_route_reports_the_walk_naming_the_refused_line(name, variants):
    """Round 13 M5, by class: a write through an imported namespace object (the
    report's import alias of os __dict__, a dynamic member carried by an
    import alias, a store through any imported object, an imported object
    handed to unlisted code, a mutator through an imported object), a
    name-only get on an unresolved receiver, and a protocol-running
    allowlisted call over a value the proof cannot type (a direct call, a
    callback, a parameter whose type guard names a module class): each
    reports os.walk naming its line and kind (each admitted at a2b5151c)."""
    for shape, expect in variants:
        _named(name, shape, expect)


def test_m5_fix14_b_a_proven_builtin_receiver_and_argument_are_still_trusted():
    """The control: a parameter its type guard proves an exact str handed to
    os.fspath, open and str, the pure methods, len and sorted of a local dict,
    an element taken by get and appended to, an argument stored by append:
    still trusted, the walk still proven (the guard is the selftest
    fixture's own)."""
    assert GUARD14 in r3.WALK_OK
    lines = ('seed = {"k": []}\ngot = seed.get("k")\ngot.append("x")\nseen = []\nseen.append(ns)\nsize = len(seed)\n'
             "names = sorted(seed.keys())\n"
             'here = os.fspath(p)\nlabel = str(p).upper()\nwith open(p, "rb") as f:\n    head = f.read()')
    shape, _e = _v("", lines, [])
    src = _plant(**shape)
    assert r3.unwrapped_queries(src, "planted") == []
    assert _named_rows(src) == []


L1_REVISION = 'with open("notes.txt", "rb") as f:\n    t = f.read()\n'


def test_m5_fix14_c_the_receiver_proof_reads_python_scopes():
    """Round 13 LOW 1: the _revision shape (a file opened as f and read, a
    later comprehension variable also named f) is trusted without any
    exemption (refused at a2b5151c); a same-name binding in the SAME scope
    that reaches the use still refuses it; and a free name is no longer
    vouched for by a same-name local of another function (admitted at
    a2b5151c)."""
    shape, _e = _v("", L1_REVISION + "x = [f for f in [ns]]", [])
    src = _plant(**shape)
    assert r3.unwrapped_queries(src, "planted") == []
    assert _named_rows(src) == []
    old = "x = [f for f in ns]"
    _exact_rebinds("comprehension", *_v("", L1_REVISION + old,
                                        [_at(old, "implicit iteration" + U + "ns")]))
    _named("same_scope", *_v("", L1_REVISION + "for f in ns:\n    pass",
                             [_in("t = f.read()", "method call read" + U + "f")]))
    _named("free_name", dict(header="\n\ndef _other():\n    handlers = []\n    return handlers\n",
                             edits=[("    return list(os.walk(", "    handlers.append(p)\n    return list(os.walk(")]),
           [("    handlers.append(p)", "method call append" + U + "handlers")])


def _levels14(lines, defs=""):
    """The flow level of every call at the head of scan, keyed by its text,
    each read in its own scope."""
    shape, _e = _v(defs, lines, [])
    tree = r3.ast.parse(_plant(**shape))
    parents = {id(c): n for n in r3.ast.walk(tree) for c in r3.ast.iter_child_nodes(n)}
    reach = r3._Reach(tree, r3._Names(tree, parents))
    return {r3.ast.unparse(n): reach.level_at(n) for n in r3.ast.walk(tree) if isinstance(n, r3.ast.Call)}


def test_m5_fix14_d_an_identity_alias_is_never_fresh():
    """Round 13 LOW 2: bytes, str, int and tuple over an exact argument may
    return it itself, so each result is an immutable identity alias (_IMMUT:
    it can carry no write), never fresh (the model at a2b5151c said fresh);
    over an unresolved argument the result is unresolved (its own __str__
    returns anything); an operator over an unresolved operand is unresolved
    (it was a holder at a2b5151c, so a write through it was trusted); a
    mutable alias stays refused (a local function returning its argument)
    while a copy of a fresh list stays fresh, as do the fix 13 fresh results."""
    assert r3._FRESH < r3._IMMUT < r3._HOLDS < r3._UNRES
    lv = _levels14('b = b"x"\nm = bytes(b)\ns = "x"\nt = str(s)\ni = len("ab")\nj = int(i)\nu = ("a",)\nv = tuple(u)\n'
                   "w = str(ns)\nl = []\nc = list(l)\nr = repr(ns)\nn = len(ns)", ID)
    for call in ("bytes(b)", "str(s)", "int(i)", "tuple(u)"):
        assert (lv[call], lv[call] == r3._FRESH) == (r3._IMMUT, False), call
    assert lv["str(ns)"] == r3._UNRES
    assert {c: lv[c] for c in ("list(l)", "repr(ns)", "len(ns)")} == dict.fromkeys(("list(l)", "repr(ns)", "len(ns)"),
                                                                                  r3._FRESH)
    _named("operator", *_v("", 'alias = ns + []\nalias["walk"] = None', [_at('alias["walk"] = None',
                                                                           "subscript store" + U + "alias")]))
    _named("mutable_alias", *_v(ID, 'm = identity(ns)\nm["walk"] = None', [_at('m["walk"] = None',
                                                                             "subscript store" + U + "m")]))
