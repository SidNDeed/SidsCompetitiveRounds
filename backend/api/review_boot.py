"""Source-only loading of the review code closure.

Every module of the review code closure (SOURCE_ONLY) is executed ONLY from
the bytes of its own source file in this directory: the loader below reads
the file, reads CRLF as LF, compiles exactly those bytes and executes the code
object. It never asks the import system for a bytecode cache, so no cache in
any location or form (beside the source, under a cache prefix, at any
optimisation level) is ever opened for a closure module. The bytes executed
are kept (LOADED) and are what the rules loader fingerprints and checks
against a revision's bound digest (review_rules._code_files), so the bytes
that ran and the bytes that were checked are one buffer.

This module must be imported before any closure module: main.py imports it
first, the test suite's conftest.py imports it, and the command line below
runs it as the script. install() records every closure module already in the
module table, under any name (PRIOR); the rules loader refuses every revision
while PRIOR is not empty, and while the module table holds, under any name, a
closure module this loader did not execute (review_rules._provenance). A
dotted import of a closure module's name is refused by the finder.

This file's own bytes are in every revision's closure fingerprint, but the
code that runs for it is whatever the interpreter loaded when it was
imported: in the api image that is bound by the build (no cache form in the
image), not by anything at run time. Run as a script, the interpreter
compiles it from its source file.

Command line (the seat's build tool and the staging validator):
  python -B <api dir>/review_boot.py validate <revision dir>
  python -B <api dir>/review_boot.py build <draft dir> <store dir> <reason>
  python -B <api dir>/review_boot.py literal <revision dir> <rule id> <days back>
"""

from __future__ import annotations

import os
import sys

SOURCE_ONLY = ("identity_clock_measures", "review_measures", "review_rules")
HERE = os.path.dirname(os.path.abspath(__file__))
LOADED = {}         # stem -> (the module this loader executed, the bytes it executed)
PRIOR = set()       # closure stems found executed by another route


def source_path(stem: str) -> str:
    return os.path.join(HERE, stem + ".py")


def _same_file(path, stem) -> bool:
    """Whether a module file path names the closure source of `stem`."""
    if not isinstance(path, str) or os.path.basename(path).lower() != stem + ".py":
        return False
    return os.path.normcase(os.path.realpath(path)) == os.path.normcase(os.path.realpath(source_path(stem)))


def executed_elsewhere() -> set:
    """Every closure stem a module of this process was executed from, under
    any name, that this loader did not execute."""
    out = set()
    for name, mod in list(sys.modules.items()):
        try:
            path = getattr(mod, "__file__", None)
        except Exception:                   # noqa: BLE001 -- an object without a plain attribute
            continue
        for stem in SOURCE_ONLY:
            if _same_file(path, stem) and not (name == stem and LOADED.get(stem, (None,))[0] is mod):
                out.add(stem)
    return out


class SourceOnly:
    """The meta path finder and loader of the closure modules."""

    def find_spec(self, fullname, path=None, target=None):
        tail = fullname.rpartition(".")[2]
        if tail not in SOURCE_ONLY:
            return None
        if fullname != tail:
            raise ImportError("review closure module %s is imported only as %s" % (fullname, tail))
        import importlib.machinery
        return importlib.machinery.ModuleSpec(fullname, self, origin=source_path(tail))

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        stem = module.__name__
        path = source_path(stem)
        with open(path, "rb") as f:
            raw = f.read().replace(b"\r\n", b"\n")
        module.__file__ = path
        LOADED[stem] = (module, raw)
        try:
            exec(compile(raw, path, "exec", dont_inherit=True), vars(module))
        except BaseException:
            LOADED.pop(stem, None)
            raise


FINDER = SourceOnly()


def install() -> None:
    """Put the finder first on the meta path (once) and record every closure
    module already executed by another route."""
    PRIOR.update(executed_elsewhere())
    if not any(isinstance(f, SourceOnly) for f in sys.meta_path):
        sys.meta_path.insert(0, FINDER)


if __name__ == "__main__":
    sys.modules["review_boot"] = sys.modules["__main__"]
    install()
    import review_rules
    sys.exit(review_rules.cli(sys.argv[1:]))
else:
    install()
