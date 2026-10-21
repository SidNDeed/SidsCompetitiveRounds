"""Runtime witnesses for the filesystem observation bound (fix pass 19).

Only literal synthetic Python is compiled here. Every corrupt shape has a
benign twin; expected-trip scopes restore bindings before another test runs.
"""

import os
import pathlib
from pathlib import Path
import sys
import types

import pytest
import review_tripwire as tw
import review_needles
import review_rules
import review_boot


P4_NAMES = (
    "os.path.exists", "os.path.lexists", "os.path.isdir", "os.path.isfile",
    "os.path.islink", "os.path.ismount", "os.path.isjunction", "os.path.getsize",
    "os.path.getmtime", "os.path.getatime", "os.path.getctime", "os.path.samefile",
    "os.path.access", "os.access", "os.walk", "os.scandir", "os.listdir",
    "os.stat", "os.lstat", "pathlib.Path.exists", "pathlib.Path.is_dir",
    "pathlib.Path.is_file", "pathlib.Path.is_symlink", "pathlib.Path.is_mount",
)


def _binding(name):
    prefix, _, attr = name.rpartition(".")
    owner = {"os": os, "os.path": os.path, "pathlib.Path": Path}[prefix]
    return owner, attr


def test_install_precedes_subject_and_test_imports():
    assert tw.installed
    assert not any(name.rsplit(".", 1)[-1].startswith("test_")
                   for name in tw.INSTALL_MODULES)
    subjects = {"review_needles", "review_rules", "review_boot"}
    assert not subjects.intersection(tw.INSTALL_MODULES)
    assert subjects <= {event["name"] for event in tw.imports()}


def test_install_is_idempotent_and_preserves_all_guarded_names():
    assert set(P4_NAMES) == {name for name, _, _ in tw.GUARDS}
    before = {name: getattr(*_binding(name), None) for name in P4_NAMES}
    tw.install()
    assert before == {name: getattr(*_binding(name), None) for name in P4_NAMES}
    assert set(tw.UNAVAILABLE) == {name for name, value in before.items() if value is None}
    assert "os.path.access" in tw.UNAVAILABLE  # the census includes this absent name


@pytest.mark.parametrize("name", P4_NAMES)
def test_each_guarded_name_has_an_identity_trip(name):
    owner, attr = _binding(name)
    if not hasattr(owner, attr):
        assert name in tw.UNAVAILABLE
        return
    with tw.expected_trip(name) as scope:
        setattr(owner, attr, lambda *a, **k: None)
    assert any(row["kind"] == "end" and row["name"] == name for row in scope.trips)


@pytest.mark.parametrize("name", P4_NAMES)
def test_each_guarded_name_benign_control(name):
    owner, attr = _binding(name)
    with tw.expected_trip(name, require=False):
        if hasattr(owner, attr):
            original = getattr(owner, attr)
            setattr(owner, attr, original)


@pytest.mark.parametrize("name", P4_NAMES)
def test_each_guarded_call_records_its_caller(name, tmp_path):
    owner, attr = _binding(name)
    if not hasattr(owner, attr):
        assert name in tw.UNAVAILABLE
        return
    fn = getattr(owner, attr)
    args = (tmp_path,)
    if name == "os.access":
        args += (os.F_OK,)
    elif name == "os.path.samefile":
        args += (tmp_path,)
    start = len(tw.calls())
    result = fn(*args)
    if name == "os.scandir":
        result.close()
    elif name == "os.walk":
        list(result)
    rows = [row for row in tw.calls()[start:] if row["name"] == name]
    assert rows and rows[0]["caller"]["function"] == "test_each_guarded_call_records_its_caller"
    assert rows[0]["caller"]["line"] > 0
    assert rows[0]["caller"]["file"].endswith("test_review_tripwire.py")


def test_identity_is_checked_at_entry_even_if_restored():
    saved = os.walk
    with tw.expected_trip("os.walk") as scope:
        os.walk = lambda *a, **k: iter(())
        os.path.exists(".")
        os.walk = saved
    assert any(row["kind"] == "entry" for row in scope.trips)
    assert not any(row["kind"] == "end" for row in scope.trips)


def test_identity_is_checked_at_end_without_another_call():
    with tw.expected_trip("os.walk") as scope:
        os.walk = lambda *a, **k: iter(())
    assert any(row["kind"] == "end" for row in scope.trips)
    assert not any(row["kind"] == "entry" for row in scope.trips)


@pytest.mark.parametrize("name", ("os.scandir", "os.listdir"))
def test_replace_use_restore_is_caught_by_audit(name, tmp_path):
    owner, attr = _binding(name)
    saved = getattr(owner, attr)
    # Captured native callable models a helper imported before installation.
    native = tw._bindings[name][2]
    with tw.expected_trip(name) as scope:
        setattr(owner, attr, native)
        result = getattr(owner, attr)(tmp_path)
        if name == "os.scandir":
            result.close()
        setattr(owner, attr, saved)
    assert any(row["kind"] == "audit" and row["caller"]["function"] ==
               "test_replace_use_restore_is_caught_by_audit" for row in scope.trips)
    assert not any(row["kind"] == "end" for row in scope.trips)


def test_clean_enumeration_and_lazy_walk_do_not_trip(tmp_path):
    (tmp_path / "leaf").write_text("synthetic", encoding="utf-8")
    with tw.expected_trip("os.scandir", "os.listdir", require=False):
        assert os.listdir(tmp_path) == ["leaf"]
        walk = os.walk(tmp_path)
        assert next(walk)[2] == ["leaf"]
        assert not getattr(tw._state, "active", 0)
        walk.close()
        assert not getattr(tw._state, "active", 0)


def test_lazy_walk_rechecks_identity_on_every_advance(tmp_path):
    walker = os.walk(tmp_path)
    next(walker)
    saved = os.walk
    with tw.expected_trip("os.walk") as scope:
        os.walk = lambda *a, **k: iter(())
        with pytest.raises(StopIteration):
            next(walker)
        os.walk = saved
    assert any(row["kind"] == "entry" and row["caller"]["function"] ==
               "test_lazy_walk_rechecks_identity_on_every_advance" for row in scope.trips)
    assert not any(row["kind"] == "end" for row in scope.trips)


def test_active_call_does_not_hide_replacement_in_path_conversion(tmp_path):
    saved = os.scandir

    class ReplacingPath:
        def __fspath__(self):
            os.scandir = tw._bindings["os.scandir"][2]
            return str(tmp_path)

    with tw.expected_trip("os.scandir") as scope:
        os.listdir(ReplacingPath())
        os.scandir = saved
    assert any(row["kind"] == "entry" for row in scope.trips)
    assert not any(row["kind"] in ("end", "audit") for row in scope.trips)


PREFIX_TARGETS = (
    ("os.path", "os.path.exists"),
    ("pathlib.Path", "pathlib.Path.exists"),
    ("module_os", "os.walk"),
    ("module_path", "os.path.exists"),
)


def _qualified_case(prefix, target, corrupt):
    if prefix == "pathlib.Path":
        saved = pathlib.Path
        replacement = type("SyntheticPath", (saved,), {"exists": lambda self: False} if corrupt else {})
    else:
        saved = os if prefix == "module_os" else os.path
        replacement = types.SimpleNamespace(**vars(saved))
        if corrupt:
            setattr(replacement, target.rsplit(".", 1)[-1], lambda *a, **k: False)
    with tw.expected_trip(target, require=corrupt) as scope:
        try:
            if prefix == "os.path":
                os.path = replacement
            elif prefix == "pathlib.Path":
                pathlib.Path = replacement
            elif prefix == "module_os":
                sys.modules["os"] = replacement
            else:
                sys.modules["os.path"] = replacement
            os.listdir(".")
        finally:
            if prefix == "os.path":
                os.path = saved
            elif prefix == "pathlib.Path":
                pathlib.Path = saved
            elif prefix == "module_os":
                sys.modules["os"] = saved
            else:
                sys.modules["os.path"] = saved
    return scope


@pytest.mark.parametrize("prefix, target", PREFIX_TARGETS)
def test_identity_follows_live_qualified_names(prefix, target):
    scope = _qualified_case(prefix, target, True)
    assert any(row["kind"] == "entry" and row["name"] == target for row in scope.trips)
    assert not any(row["kind"] == "end" for row in scope.trips)


@pytest.mark.parametrize("prefix, target", PREFIX_TARGETS)
def test_live_qualified_name_benign_control(prefix, target):
    assert not _qualified_case(prefix, target, False).trips


def test_captured_owner_remains_guarded_after_prefix_replacement():
    saved, saved_exists = os.path, os.path.exists
    replacement = types.SimpleNamespace(**vars(saved))
    with tw.expected_trip("os.path.exists") as scope:
        try:
            os.path = replacement
            sys.modules["os.path"] = replacement
            saved.exists = lambda *a, **k: False
            os.listdir(".")
        finally:
            saved.exists = saved_exists
            os.path = saved
            sys.modules["os.path"] = saved
    assert any(row["kind"] == "entry" for row in scope.trips)


def test_module_level_decorator_is_recorded_before_import_finishes():
    module = types.ModuleType("review_witness_install")
    with tw.expected_trip("os.walk") as scope:
        exec(compile("""
import os
def decorate(function):
    os.walk = lambda *a, **k: iter(())
    os.path.exists('.')
    return function
@decorate
def defined():
    pass
""", "<review-witness:install-order>", "exec"), vars(module))
    assert any(row["kind"] == "entry" and row["caller"]["function"] == "decorate"
               and row["caller"]["file"] == "<review-witness:install-order>"
               for row in scope.trips)


def test_module_level_decorator_benign_control():
    module = types.ModuleType("review_witness_install_control")
    with tw.expected_trip("os.walk", require=False):
        exec(compile("""
import os
def decorate(function):
    os.path.exists('.')
    return function
@decorate
def defined():
    pass
""", "<review-witness:install-control>", "exec"), vars(module))
