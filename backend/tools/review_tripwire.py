"""Runtime evidence for review filesystem queries, installed before subjects.

This is a process-local observation bound, not a Python sandbox. Call records
contain code locations only, never arguments, results, or filesystem contents.
The static review scanner remains a separate, informative census.
"""

import contextlib
import functools
import importlib.machinery
import os
import pathlib
import sys
import threading


PATH_QUERIES = (
    "exists", "lexists", "isdir", "isfile", "islink", "ismount", "isjunction",
    "getsize", "getmtime", "getatime", "getctime", "samefile", "access",
)
PATHLIB_QUERIES = ("exists", "is_dir", "is_file", "is_symlink", "is_mount")
GUARDS = tuple(
    [("os.path." + name, os.path, name) for name in PATH_QUERIES]
    + [("os." + name, os, name) for name in
       ("access", "walk", "scandir", "listdir", "stat", "lstat")]
    + [("pathlib.Path." + name, pathlib.Path, name) for name in PATHLIB_QUERIES]
)
_SUBJECTS = frozenset(("review_needles.py", "review_rules.py", "review_boot.py",
                       "test_review_tripwire.py"))
# CPython's importer holds a native listdir reference for its module cache.
# Its own enumeration is not a subject call merely because a subject imports
# a module. Match the actual emitter's code, never a caller name or stack prefix.
_IMPORT_CACHE_CODE = importlib.machinery.FileFinder._fill_cache.__code__
_state = threading.local()
_bindings = {}
_calls = []
_trips = []
_imports = []
installed = False
INSTALL_MODULES = frozenset()
UNAVAILABLE = ()


def _location(frame):
    return {"file": frame.f_code.co_filename, "function": frame.f_code.co_name,
            "line": frame.f_lineno}


def _record(kind, name, frame):
    row = {"kind": kind, "name": name, "caller": _location(frame),
           "_scope": getattr(_state, "scope", None)}
    _trips.append(row)
    return row


def _identity(kind, frame):
    for name, (owner, attr, original, wrapper) in _bindings.items():
        if name.startswith("os.path."):
            live = (getattr(sys.modules.get("os"), "path", None),
                    sys.modules.get("os.path"))
        elif name.startswith("pathlib.Path."):
            live = (getattr(sys.modules.get("pathlib"), "Path", None),)
        else:
            live = (sys.modules.get("os"),)
        if (getattr(owner, attr, None) is not wrapper
                or any(getattr(current, attr, None) is not wrapper for current in live)):
            _record(kind, name, frame)


def _guarded_frame(frame):
    while frame is not None:
        filename = frame.f_code.co_filename.replace("\\", "/")
        if (filename.rsplit("/", 1)[-1] in _SUBJECTS
                or filename.startswith("<review-witness:")):
            return frame
        frame = frame.f_back
    return None


def _audit(event, args):
    if event == "import":
        _imports.append({"name": args[0], "caller": _location(sys._getframe(1))})
    elif event in ("os.scandir", "os.listdir"):
        caller = sys._getframe(1)
        # A path-conversion callback can replace a binding after wrapper entry.
        # Even an active wrapper must not bless that replacement's native event.
        _identity("entry", caller)
        if getattr(_state, "active", 0):
            return
        if caller.f_code is _IMPORT_CACHE_CODE:
            return
        frame = _guarded_frame(caller)
        if frame is not None:
            _record("audit", event, frame)


@contextlib.contextmanager
def _active():
    depth = getattr(_state, "active", 0)
    _state.active = depth + 1
    try:
        yield
    finally:
        _state.active = depth


class _WalkIterator:
    """Activate a lazy walk only while advancing it, never across a yield."""

    def __init__(self, iterator):
        self._iterator = iterator

    def __iter__(self):
        return self

    def _advance(self, method, *args):
        _entry("os.walk", sys._getframe(2))
        with _active():
            return method(*args)

    def __next__(self):
        return self._advance(next, self._iterator)

    def send(self, value):
        return self._advance(self._iterator.send, value)

    def throw(self, *args):
        return self._advance(self._iterator.throw, *args)

    def close(self):
        return self._advance(self._iterator.close)


def _entry(name, frame):
    _calls.append({"name": name, "caller": _location(frame)})
    _identity("entry", frame)


def _wrapper(name, original):
    @functools.wraps(original)
    def call(*args, **kwargs):
        frame = sys._getframe(1)
        _entry(name, frame)
        with _active():
            result = original(*args, **kwargs)
        return _WalkIterator(result) if name == "os.walk" else result
    return call


def install():
    """Install once; subsequent calls never bless or repair a replacement."""
    global installed, INSTALL_MODULES, UNAVAILABLE
    if installed:
        return
    INSTALL_MODULES = frozenset(sys.modules)
    unavailable = []
    for name, owner, attr in GUARDS:
        original = getattr(owner, attr, None)
        if not callable(original):
            unavailable.append(name)
            continue
        wrapper = _wrapper(name, original)
        _bindings[name] = (owner, attr, original, wrapper)
        setattr(owner, attr, wrapper)
    UNAVAILABLE = tuple(unavailable)
    sys.addaudithook(_audit)
    installed = True


def calls():
    """Snapshot every call's immediate caller, without retaining live frames."""
    return list(_calls)


def imports():
    return list(_imports)


def verdict():
    """Accumulate end identity failures and return all unconsumed trips."""
    _identity("end", sys._getframe(1))
    return list(_trips)


class _ExpectedTrip:
    def __init__(self, names, require):
        self.names = frozenset(names)
        self.require = require
        self.trips = []

    def __enter__(self):
        # Pre-existing failures remain outside this scope's consumable rows.
        verdict()
        self.prior = {id(row) for row in _trips}
        self.previous_scope = getattr(_state, "scope", None)
        self.token = object()
        _state.scope = self.token
        self.saved = [(owner, attr, getattr(owner, attr))
                      for name, owner, attr in GUARDS
                      if name in self.names and hasattr(owner, attr)]
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            verdict()
            fresh = [row for row in _trips if id(row) not in self.prior
                     and row["_scope"] is self.token]
            self.trips = [row for row in fresh if row["name"] in self.names]
            unexpected = [row for row in fresh if row["name"] not in self.names]
            if exc_type is None:
                assert not unexpected, "unexpected trip inside expected scope"
                if self.require:
                    assert self.trips, "expected trip was not recorded"
                else:
                    assert not self.trips, "benign control tripped"
                consumed = {id(row) for row in self.trips}
                _trips[:] = [row for row in _trips if id(row) not in consumed]
        finally:
            for owner, attr, original in self.saved:
                setattr(owner, attr, original)
            _state.scope = self.previous_scope
        return False


def expected_trip(*names, require=True):
    """Assert and consume only this scope's named trips; always restore names.

    An unexpected name or a failure already present on entry is never cleared.
    A failed block also retains its trips for the final session verdict.
    """
    return _ExpectedTrip(names, require)


install()
