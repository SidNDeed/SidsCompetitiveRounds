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
Every planted shape is compiled first: it is real Python."""

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
