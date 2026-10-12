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
    enumeration raised NoFixedPoint on it before judging the walk)."""

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
