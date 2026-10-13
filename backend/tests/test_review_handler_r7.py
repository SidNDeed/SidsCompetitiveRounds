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
    test, and the newly unresolved sites are exactly the measured ones."""

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


REAL = {"backend/tools/review_needles.py": 13, "backend/api/review_rules.py": 31, "backend/api/review_boot.py": 0}
# (fix pass 12: review_needles.py 12 -> 13, the in-place site pinned by NEW12 below)


def test_m5_fix10_k_the_real_review_modules_keep_their_verdicts():
    """Every surface keeps its round 9 verdict by the same test; the
    real-module rule's measured counts of unresolved-base sites hold; the
    named module is exempt at exactly its measured count, and one more such
    site lapses the exemption."""
    r3.test_m5_no_path_query_turns_a_failure_into_absence()
    root = os.path.join(HERE, "..", "..")
    for rel, count in REAL.items():
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            src = f.read()
        unresolved = [x for x in _named_rows(src, "<source>") if r3._unresolved(x[1])]
        assert len(unresolved) == count, (rel, unresolved)
    with open(os.path.join(root, "backend/tools/review_needles.py"), encoding="utf-8") as f:
        src = f.read()
    assert _named_rows(src, "review_needles.py") == []
    extra = src + "\n\ndef _planted_extra(d):\n    d['k'] = 1\n"
    assert len(_named_rows(extra, "review_needles.py")) == REAL["backend/tools/review_needles.py"] + 1


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
    """A local function returning a copy (dict(x)) whose result is written, one
    returning a constant, one returning a fresh object built from the values
    of x, and timeit on a literal expression that rebinds nothing: nothing
    reaches a namespace, the walk is still proven."""
    src = _plant(header="import tempfile\nimport timeit\n\n\ndef copied(x):\n    return dict(x)\n\n\n"
                        "def blank(x):\n    return {}\n\n\n"
                        'def sized(x):\n    return {"size": len(x), "names": sorted(x)}\n',
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


def test_m5_fix11_l_the_real_review_modules_keep_their_verdicts():
    """Every surface keeps its round 10 verdict by the same test; the sites
    the completed proof newly finds unresolved are exactly the measured,
    named ones (every one a mutator method, none from a local call); the
    named module is exempt at exactly its measured count and one more such
    site lapses the exemption."""
    r3.test_m5_no_path_query_turns_a_failure_into_absence()
    root = os.path.join(HERE, "..", "..")
    for rel, new in NEW11.items():
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            src = f.read()
        unresolved = [x for x in _named_rows(src, "<source>") if r3._unresolved(x[1])]
        assert [x for x in unresolved if x[1].startswith(("method call ", "bound method "))] == new, rel
        assert len(unresolved) == REAL[rel], (rel, unresolved)
    assert r3._MEASURED_CLEAN == {"review_needles.py": REAL["backend/tools/review_needles.py"]}
    with open(os.path.join(root, "backend/tools/review_needles.py"), encoding="utf-8") as f:
        src = f.read()
    assert _named_rows(src, "review_needles.py") == []
    extra = src + "\n\ndef _planted_extra(d):\n    d.update(k=1)\n"
    assert len(_named_rows(extra, "review_needles.py")) == REAL["backend/tools/review_needles.py"] + 1


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


def test_m5_fix12_f_a_benign_module_is_still_trusted():
    """Augmented assignments on a dict copy, a dict display over ns, a local
    counter and a local list; a rebinding ns = ns | {...}; map over a builtin;
    a slice of a literal list and a sort of fresh mappings written through:
    nothing reaches a namespace, the walk is still proven."""
    lines = ("fresh = dict(ns)\nfresh |= %s\nmerged = {**ns}\nmerged |= %s\nns = ns | %s\ncount = 0\ncount += 1\n"
             'names = []\nnames += ["x"]\nlabels = list(map(str, [1, 2]))\nlabels[0] = "x"\nv = "fresh"\n'
             'rows = [{}, {}][0:1]\nrows[0]["k"] = v\nsorted([{}, {}])[0]["k"] = v') % (TDV, TDV, TDV)
    shape, _e = _v("", lines, [])
    src = _plant(**shape)
    assert r3.unwrapped_queries(src, "planted") == []
    assert _named_rows(src) == []


NEW12 = {"backend/tools/review_needles.py": [(999, "augmented assignment += through unresolved base body")],
         "backend/api/review_rules.py": [], "backend/api/review_boot.py": []}


def test_m5_fix12_g_the_real_review_modules_keep_their_verdicts():
    """Every surface keeps its round 11 verdict by the same test; the sites the
    in-place rule newly finds are exactly the measured, named ones (the fix
    11 method sites stand, test l); the named module is exempt at exactly
    its measured count and one more in-place site lapses the exemption."""
    r3.test_m5_no_path_query_turns_a_failure_into_absence()
    root = os.path.join(HERE, "..", "..")
    for rel, new in NEW12.items():
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            src = f.read()
        unresolved = [x for x in _named_rows(src, "<source>") if r3._unresolved(x[1])]
        assert [x for x in unresolved if x[1].startswith(("augmented assignment ", "in-place "))] == new, rel
        assert len(unresolved) == REAL[rel], (rel, unresolved)
    assert r3._MEASURED_CLEAN == {"review_needles.py": REAL["backend/tools/review_needles.py"]}
    with open(os.path.join(root, "backend/tools/review_needles.py"), encoding="utf-8") as f:
        src = f.read()
    assert _named_rows(src, "review_needles.py") == []
    extra = src + "\n\ndef _planted_extra(d):\n    d |= {}\n"
    assert len(_named_rows(extra, "review_needles.py")) == REAL["backend/tools/review_needles.py"] + 1
