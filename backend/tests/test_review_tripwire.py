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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
                setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
                setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
        setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
        probe('.')
class Defined(Base):
    pass
"""),
    ("metaclass_prepare", "__prepare__", """
class Meta(type):
    @classmethod
    def __prepare__(metaclass, name, bases):
        if corrupt:
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
        probe('.')
        return {}
class Defined(metaclass=Meta):
    pass
"""),
    ("metaclass_call", "make_class", """
def make_class(name, bases, namespace):
    if corrupt:
        setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
    probe('.')
    return type(name, bases, namespace)
class Defined(metaclass=make_class):
    pass
"""),
    ("descriptor_set_name", "__set_name__", """
class Descriptor:
    def __set_name__(self, owner, name):
        if corrupt:
            setattr(mutation_owner, target, lambda *args, **kwargs: iter(()))
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
    values = dict(os=os, mutation_owner=os, target=target, corrupt=corrupt, probe=os.path.exists)
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


@pytest.mark.parametrize("args, clean_code", (([], 2), (["scan-dir", "."], 4)))
def test_command_verdict_overrides_early_returns(args, clean_code, monkeypatch, capsys):
    monkeypatch.setattr(review_needles, "STORE_ENV", "D4_SYNTHETIC_STORE")
    monkeypatch.delenv("D4_SYNTHETIC_STORE", raising=False)
    assert review_needles.main(args) == clean_code
    clean_output = capsys.readouterr().out
    with tw.expected_trip("os.walk"):
        os.walk = lambda *a, **k: iter(())
        assert review_needles.main(args) == 3
        assert capsys.readouterr().out == clean_output


@pytest.mark.parametrize("corrupt", (False, True), ids=("control", "replacement"))
def test_snapshot_path_conversion_exit_check(tmp_path, corrupt):
    """A replacement surviving lstat must be recorded before it restores itself."""
    (tmp_path / "leaf").write_bytes(b"synthetic")
    saved = os.scandir

    class Empty:
        def __enter__(self):
            return iter(())

        def __exit__(self, *exc):
            os.scandir = saved

    class Root:
        def __fspath__(self):
            if corrupt:
                os.scandir = lambda path: Empty()
            return str(tmp_path)

    with tw.expected_trip("os.scandir", require=corrupt) as scope:
        result = review_needles.snapshot(Root())
        assert result == ([] if corrupt else [("leaf", b"synthetic")])
        assert os.scandir is saved
        assert bool(tw.verdict()) is corrupt
    if corrupt:
        assert any(row["kind"] == "exit" and row["caller"]["function"] == "_status"
                   for row in scope.trips)
        assert not any(row["kind"] in ("entry", "end", "audit") for row in scope.trips)


@pytest.mark.parametrize("corrupt", (False, True), ids=("control", "replacement"))
@pytest.mark.parametrize("fails", (False, True), ids=("return", "raise"))
def test_call_exit_check_preserves_result_and_exception(corrupt, fails):
    saved = os.scandir
    result = object()
    error = RuntimeError("synthetic")

    def original():
        if corrupt:
            os.scandir = lambda path: iter(())
        if fails:
            raise error
        return result

    call = tw._wrapper("os.lstat", original)
    with tw.expected_trip("os.scandir", require=corrupt) as scope:
        try:
            if fails:
                with pytest.raises(RuntimeError) as caught:
                    call()
                assert caught.value is error
            else:
                assert call() is result
        finally:
            os.scandir = saved
    if corrupt:
        assert all(row["kind"] == "exit" and row["caller"]["function"] ==
                   "test_call_exit_check_preserves_result_and_exception" for row in scope.trips)


@pytest.mark.parametrize("corrupt", (False, True), ids=("control", "replacement"))
@pytest.mark.parametrize("fails", (False, True), ids=("return", "raise"))
@pytest.mark.parametrize("method", ("__next__", "send", "throw", "close"))
def test_lazy_exit_check_preserves_result_and_exception(method, fails, corrupt):
    saved = os.scandir
    result = object()
    error = RuntimeError("synthetic")

    class Iterator:
        def advance(self, *args):
            if corrupt:
                os.scandir = lambda path: iter(())
            if fails:
                raise error
            return result

        __next__ = send = throw = close = advance

    walk = tw._WalkIterator(Iterator())
    args = (None,) if method in ("send", "throw") else ()
    with tw.expected_trip("os.scandir", require=corrupt) as scope:
        try:
            if fails:
                with pytest.raises(RuntimeError) as caught:
                    getattr(walk, method)(*args)
                assert caught.value is error
            else:
                assert getattr(walk, method)(*args) is result
        finally:
            os.scandir = saved
    if corrupt:
        assert all(row["kind"] == "exit" and row["caller"]["function"] ==
                   "test_lazy_exit_check_preserves_result_and_exception" for row in scope.trips)


_HANDLER_CASES = tuple(
    (finding, case, helper_source, helper_name)
    for finding, cases, helper_source, helper_name in (
        ("m1", _M1_CASES, None, None),
        ("m2", _M2_CASES, _M2_HELPER, "review_witness_pattern_helper"),
        ("m3", _M3_CASES, None, None),
        ("m4", _M4_CASES, _M4_HELPER, "review_witness_definition_helper"),
    )
    for case in cases
)


@pytest.mark.parametrize("corrupt", (False, True), ids=("raising-control", "suppressed"))
@pytest.mark.parametrize("item", _HANDLER_CASES, ids=[row[0] + ":" + row[1][0] for row in _HANDLER_CASES])
def test_round17_handler_mutation_with_real_enumeration(item, corrupt, tmp_path):
    """The original hook forms change only the synthetic walk's handler."""
    finding, (label, hook, source), helper_source, helper_name = item
    filename = "<review-witness:handler:" + finding + ":" + label + ">"
    module = types.ModuleType("review_witness_handler")
    error = review_needles.NoVerdict("synthetic")
    calls = []

    def raising(error_seen):
        calls.append(error_seen)
        raise error

    module._walk_error = raising
    file_root = tmp_path / "ordinary-file"
    file_root.write_bytes(b"synthetic")
    with tw.expected_trip("os.walk", require=False):
        with pytest.raises(review_needles.NoVerdict) as caught:
            list(os.walk(file_root, onerror=module._walk_error))
        assert caught.value is error
    assert len(calls) == 1 and isinstance(calls[0], OSError)
    # The literal hooks mutate this module's handler, with no artificial
    # guarded probe and no OS-binding replacement to stand in for suppression.
    values = dict(os=os, mutation_owner=module, target="_walk_error", corrupt=corrupt,
                  probe=lambda path: None)
    module.__dict__.update(values)
    helper_needed = (finding == "m2" and label == "imported_class"
                     or finding == "m4" and label.endswith("_decorator"))
    missing = object()
    previous = sys.modules.get(helper_name, missing)
    with tw.expected_trip("os.walk", require=corrupt) as scope:
        try:
            if helper_needed:
                helper = types.ModuleType(helper_name)
                helper.__dict__.update(values)
                exec(compile(helper_source, filename, "exec"), vars(helper))
                sys.modules[helper_name] = helper
            exec(compile(source, filename, "exec"), vars(module))
            if corrupt:
                assert list(os.walk(file_root, onerror=module._walk_error)) == []
            else:
                with pytest.raises(review_needles.NoVerdict) as caught:
                    list(os.walk(file_root, onerror=module._walk_error))
                assert caught.value is error
        finally:
            if helper_needed:
                if previous is missing:
                    sys.modules.pop(helper_name, None)
                else:
                    sys.modules[helper_name] = previous
    if corrupt:
        assert len(scope.trips) == 1
        row = scope.trips[0]
        assert row["kind"] == "suppressed-error" and row["name"] == "os.walk"
        assert set(row) == {"kind", "name", "caller", "_scope"}
        assert set(row["caller"]) == {"file", "function", "line"}


@pytest.mark.parametrize("form", ("positional", "keyword", "omitted", "none"))
@pytest.mark.parametrize("fails", (False, True), ids=("healthy-control", "enumeration-error"))
def test_walk_error_observation_covers_handler_forms(form, fails, tmp_path):
    root = tmp_path / "ordinary-file" if fails else tmp_path
    if fails:
        root.write_bytes(b"synthetic")
    calls = []
    with tw.expected_trip("os.walk", require=fails) as scope:
        if form == "positional":
            result = list(os.walk(root, True, calls.append))
        elif form == "keyword":
            result = list(os.walk(root, onerror=calls.append))
        elif form == "none":
            result = list(os.walk(root, onerror=None))
        else:
            result = list(os.walk(root))
    assert bool(result) is not fails
    assert len(calls) == int(fails and form in ("positional", "keyword"))
    assert all(row["kind"] == "suppressed-error" for row in scope.trips)


@pytest.mark.parametrize("positional", (False, True))
def test_walk_raising_handler_preserves_exception(positional, tmp_path):
    root = tmp_path / "ordinary-file"
    root.write_bytes(b"synthetic")
    error = KeyboardInterrupt("synthetic")

    def raising(actual):
        assert isinstance(actual, OSError)
        raise error

    with tw.expected_trip("os.walk", require=False):
        with pytest.raises(KeyboardInterrupt) as caught:
            list(os.walk(root, True, raising) if positional else os.walk(root, onerror=raising))
        assert caught.value is error


def test_non_subject_walk_suppression_keeps_ordinary_policy(tmp_path):
    module = types.ModuleType("ordinary_walk_caller")
    exec(compile("def collect():\n    results.append(list(os.walk(root)))\n",
                 "<ordinary-walk-caller>", "exec"), vars(module))
    module.os = os
    root = tmp_path / "ordinary-file"
    root.write_bytes(b"synthetic")
    # The worker has only ordinary caller frames, without a subject frame.
    import threading
    results = []
    module.root, module.results = root, results
    worker = threading.Thread(target=module.collect)
    before = tw.verdict()
    worker.start()
    worker.join()
    assert results == [[]]
    assert tw.verdict() == before

# Exact inventory and scope-preservation controls.
# Scope unit tests isolate only the record sink, preserving the session sink.

@pytest.mark.parametrize("listed", (True, False))
def test_inventory_count_exact_scope_preserves_the_count_cap(tmp_path, monkeypatch, capsys, listed):
    import conftest
    import test_review_rules as rules
    key = ("test_review_rules", "test_l3_enumeration_is_incremental_under_the_count_cap")
    records = []
    monkeypatch.setattr(tw, "_trips", records)
    if not listed:
        monkeypatch.delitem(conftest._REVIEW_FAULTS, key, raising=False)
    with pytest.MonkeyPatch.context() as patch:
        with conftest._review_fault_scope(*key):
            rules.test_l3_enumeration_is_incremental_under_the_count_cap(tmp_path, patch)
    assert bool(tw.verdict()) is not listed
    assert review_needles.main([]) == (2 if listed else 3)
    capsys.readouterr()


def test_unlisted_replacement_is_not_consumed(tmp_path, monkeypatch):
    import conftest
    records = []
    monkeypatch.setattr(tw, "_trips", records)
    saved = os.scandir
    try:
        with conftest._review_fault_scope("test_review_rules", "UNLISTED"):
            os.scandir = lambda path: saved(path)
            os.scandir(tmp_path).close()
    finally:
        os.scandir = saved
    assert records and all(row["name"] == "os.scandir" for row in records)
    assert tw.verdict() == records


def test_expected_scope_retains_prior_trips(monkeypatch):
    records = []
    monkeypatch.setattr(tw, "_trips", records)
    saved = os.walk
    try:
        os.walk = lambda *args, **kwargs: iter(())
        tw.verdict()
    finally:
        os.walk = saved
    prior = tuple(records)
    with tw.expected_trip("os.walk"):
        os.walk = lambda *args, **kwargs: iter(())
    assert tuple(records) == prior and prior


def test_expected_scope_retains_unexpected_names(monkeypatch):
    records = []
    monkeypatch.setattr(tw, "_trips", records)
    saved = os.scandir
    try:
        with pytest.raises(AssertionError, match="unexpected trip"):
            with tw.expected_trip("os.walk"):
                os.scandir = lambda *args, **kwargs: iter(())
    finally:
        os.scandir = saved
    assert records and all(row["name"] == "os.scandir" for row in records)


def test_expected_scope_retains_failed_block_trips(monkeypatch):
    records = []
    monkeypatch.setattr(tw, "_trips", records)
    failure = ValueError("synthetic scope failure")
    with pytest.raises(ValueError) as caught:
        with tw.expected_trip("os.walk"):
            os.walk = lambda *args, **kwargs: iter(())
            raise failure
    assert caught.value is failure
    assert records and all(row["name"] == "os.walk" for row in records)


def test_expected_scope_retains_foreign_thread_trips(monkeypatch):
    import threading
    records = []
    monkeypatch.setattr(tw, "_trips", records)
    with tw.expected_trip("os.walk"):
        os.walk = lambda *args, **kwargs: iter(())
        worker = threading.Thread(target=tw.verdict)
        worker.start()
        worker.join()
    assert records and all(row["_scope"] is None for row in records)
    assert all(row["name"] == "os.walk" for row in records)


def test_expected_scope_benign_control(monkeypatch):
    records = []
    monkeypatch.setattr(tw, "_trips", records)
    with tw.expected_trip("os.walk", require=False):
        pass
    assert not records


def test_restore_before_observation_walk_has_no_positive_scope(monkeypatch):
    import conftest
    import test_review_needles_r3 as r3
    key = ("test_review_needles_r3", "test_m5_fix17_a_exact_oserror_errno_masks_cover_direct_and_callback_routes")
    records = []
    monkeypatch.setattr(tw, "_trips", records)
    saved = os.walk
    with pytest.MonkeyPatch.context() as patch:
        with conftest._review_fault_scope(*key):
            r3.test_m5_fix17_a_exact_oserror_errno_masks_cover_direct_and_callback_routes(patch)
        assert os.walk is saved
        assert not tw.verdict()
    # Undo replays the manual restoration and then the original replacement.
    assert os.walk is saved
    assert not tw.verdict()
