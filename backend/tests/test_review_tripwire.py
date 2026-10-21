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
# Round 17 MEDIUM witnesses: literal syntax triggers a caller hook after install.
# The same sources run with a benign hook for the negative controls.
_M1_CASES = (
    ("list_direct", "__iter__", """
class Caller:
    def __iter__(self):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return iter(())
original = (list[str],)
bases = original
class C(bases[False]):
    pass
def trigger(obj):
    stored = C(obj)
trigger(Caller())
"""),
    ("dict_direct", "__iter__", """
class Caller:
    def __iter__(self):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return iter(())
original = (dict[str, str],)
bases = original
class C(bases[False]):
    pass
def trigger(obj):
    stored = C(obj)
trigger(Caller())
"""),
    ("list_callback", "__iter__", """
class Caller:
    def __iter__(self):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return iter(())
original = (list[str],)
bases = original
class C(bases[False]):
    pass
def trigger(obj):
    stored = list(map(C, (obj,)))
trigger(Caller())
"""),
    ("dict_callback", "__iter__", """
class Caller:
    def __iter__(self):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return iter(())
original = (dict[str, str],)
bases = original
class C(bases[False]):
    pass
def trigger(obj):
    stored = list(map(C, (obj,)))
trigger(Caller())
"""),
)

_M2_HELPER = """
class Meta(type):
    def __instancecheck__(cls, instance):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return False
class C(metaclass=Meta):
    pass
"""
_M2_CASES = (
    ("imported_class", "__instancecheck__", """
from review_witness_pattern_helper import C
def trigger():
    match False:
        case C():
            pass
trigger()
"""),
    ("sequence_value", "__eq__", """
class Caller:
    def __eq__(self, other):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return False
def trigger(obj):
    match [obj]:
        case [0]:
            pass
trigger(Caller())
"""),
    ("mapping_value", "__eq__", """
class Caller:
    def __eq__(self, other):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return False
def trigger(obj):
    match {False: obj}:
        case {False: 0}:
            pass
trigger(Caller())
"""),
)

_M3_CASES = (
    ("mutated_set_expansion", "__hash__", """
class Caller:
    def __hash__(self):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return 0
def trigger(obj):
    items = []
    items.append(obj)
    stored = {*items}
trigger(Caller())
"""),
    ("dictionary_store", "__hash__", """
class Caller:
    def __hash__(self):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return 0
def trigger(obj):
    d = {}
    d[obj] = None
trigger(Caller())
"""),
    ("dictionary_delete", "__hash__", """
class Caller:
    def __init__(self):
        self.armed = False
    def __hash__(self):
        if self.armed:
            if corrupt:
                setattr(os, target, lambda *args, **kwargs: iter(()))
            probe('.')
        return 0
def trigger(obj):
    d = {obj: None}
    obj.armed = True
    del d[obj]
trigger(Caller())
"""),
    ("dictionary_augmented_target", "__hash__", """
class Caller:
    def __init__(self):
        self.armed = False
    def __hash__(self):
        if self.armed:
            if corrupt:
                setattr(os, target, lambda *args, **kwargs: iter(()))
            probe('.')
        return 0
def trigger(obj):
    d = {obj: 0}
    obj.armed = True
    d[obj] += 1
trigger(Caller())
"""),
    ("list_store_index", "__index__", """
class Caller:
    def __index__(self):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return 0
def trigger(obj):
    items = [None]
    items[obj] = False
trigger(Caller())
"""),
    ("list_delete_index", "__index__", """
class Caller:
    def __index__(self):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return 0
def trigger(obj):
    items = [None]
    del items[obj]
trigger(Caller())
"""),
)

_M4_HELPER = """
def decorate(value):
    if corrupt:
        setattr(os, target, lambda *args, **kwargs: iter(()))
    probe('.')
    return value
"""
_M4_CASES = (
    ("function_decorator", "decorate", """
from review_witness_definition_helper import decorate
@decorate
def defined():
    pass
"""),
    ("async_function_decorator", "decorate", """
from review_witness_definition_helper import decorate
@decorate
async def defined():
    pass
"""),
    ("class_decorator", "decorate", """
from review_witness_definition_helper import decorate
@decorate
class Defined:
    pass
"""),
    ("base_mro_entries", "__mro_entries__", """
class BaseValue:
    def __mro_entries__(self, bases):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return (object,)
base = BaseValue()
class Defined(base):
    pass
"""),
    ("base_init_subclass", "__init_subclass__", """
class Base:
    def __init_subclass__(cls):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
class Defined(Base):
    pass
"""),
    ("metaclass_prepare", "__prepare__", """
class Meta(type):
    @classmethod
    def __prepare__(metaclass, name, bases):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return {}
class Defined(metaclass=Meta):
    pass
"""),
    ("metaclass_call", "make_class", """
def make_class(name, bases, namespace):
    if corrupt:
        setattr(os, target, lambda *args, **kwargs: iter(()))
    probe('.')
    return type(name, bases, namespace)
class Defined(metaclass=make_class):
    pass
"""),
    ("descriptor_set_name", "__set_name__", """
class Descriptor:
    def __set_name__(self, owner, name):
        if corrupt:
            setattr(os, target, lambda *args, **kwargs: iter(()))
        probe('.')
class Defined:
    value = Descriptor()
"""),
)


def _run_round17_case(finding, case, target, corrupt):
    """Execute only the literal sources above, with a fresh module per case."""
    label, hook, source = case
    filename = '<review-witness:' + finding + ':' + label + '>'
    module = types.ModuleType('review_witness_' + finding + '_' + label)
    values = dict(os=os, target=target, corrupt=corrupt, probe=os.path.exists)
    module.__dict__.update(values)
    helper_name = 'review_witness_pattern_helper'
    helper_source = None
    if finding == 'm2' and label == 'imported_class':
        helper_source = _M2_HELPER
    elif finding == 'm4' and label.endswith('_decorator'):
        helper_name = 'review_witness_definition_helper'
        helper_source = _M4_HELPER
    missing = object()
    previous = sys.modules.get(helper_name, missing)
    helper = None
    with tw.expected_trip('os.' + target, require=corrupt) as scope:
        try:
            if helper_source is not None:
                helper = types.ModuleType(helper_name)
                helper.__dict__.update(values)
                exec(compile(helper_source, filename, 'exec'), helper.__dict__)
                sys.modules[helper_name] = helper
            exec(compile(source, filename, 'exec'), module.__dict__)
        finally:
            if helper is not None:
                if previous is missing:
                    sys.modules.pop(helper_name, None)
                else:
                    sys.modules[helper_name] = previous
    if corrupt:
        assert any(
            row['kind'] == 'entry'
            and row['name'] == 'os.' + target
            and row['caller']['file'] == filename
            and row['caller']['function'] == hook
            and row['caller']['line'] > 0
            for row in scope.trips
        ), (finding, label, target, scope.trips)
    else:
        assert not scope.trips, (finding, label, target, scope.trips)


@pytest.mark.parametrize('target', ('walk', 'scandir'))
@pytest.mark.parametrize('case', _M1_CASES, ids=[row[0] for row in _M1_CASES])
def test_m1_transitive_container_base_witness(case, target):
    _run_round17_case('m1', case, target, True)


@pytest.mark.parametrize('target', ('walk', 'scandir'))
@pytest.mark.parametrize('case', _M1_CASES, ids=[row[0] for row in _M1_CASES])
def test_m1_transitive_container_base_control(case, target):
    _run_round17_case('m1', case, target, False)


@pytest.mark.parametrize('target', ('walk', 'scandir'))
@pytest.mark.parametrize('case', _M2_CASES, ids=[row[0] for row in _M2_CASES])
def test_m2_structural_pattern_witness(case, target):
    _run_round17_case('m2', case, target, True)


@pytest.mark.parametrize('target', ('walk', 'scandir'))
@pytest.mark.parametrize('case', _M2_CASES, ids=[row[0] for row in _M2_CASES])
def test_m2_structural_pattern_control(case, target):
    _run_round17_case('m2', case, target, False)


@pytest.mark.parametrize('target', ('walk', 'scandir'))
@pytest.mark.parametrize('case', _M3_CASES, ids=[row[0] for row in _M3_CASES])
def test_m3_collection_protocol_witness(case, target):
    _run_round17_case('m3', case, target, True)


@pytest.mark.parametrize('target', ('walk', 'scandir'))
@pytest.mark.parametrize('case', _M3_CASES, ids=[row[0] for row in _M3_CASES])
def test_m3_collection_protocol_control(case, target):
    _run_round17_case('m3', case, target, False)


@pytest.mark.parametrize('target', ('walk', 'scandir'))
@pytest.mark.parametrize('case', _M4_CASES, ids=[row[0] for row in _M4_CASES])
def test_m4_definition_time_witness(case, target):
    _run_round17_case('m4', case, target, True)


@pytest.mark.parametrize('target', ('walk', 'scandir'))
@pytest.mark.parametrize('case', _M4_CASES, ids=[row[0] for row in _M4_CASES])
def test_m4_definition_time_control(case, target):
    _run_round17_case('m4', case, target, False)
