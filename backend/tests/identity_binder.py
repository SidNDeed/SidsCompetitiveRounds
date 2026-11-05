"""The one identity binder of the a1 and gate walks (rehearsal-four round 11,
ruling FOUR-R10-A2, FIX-R11-ID; findings gate:842, closed_walk:1949,
closed_walk:1125, closed_walk:1775, a1:5655).

Round 10 bound a walked name to its provider by a DESCRIPTION (a module name
and a qualified name, a callee spelling and its argument shape). A
description is writable: functools.wraps copies __module__, __qualname__ and
__name__ onto a wrapper, so a wrapper with its own body kept every check.
This module makes OBJECT IDENTITY the evidence and leaves spelling as a
filter only:

  * trusted(obj, module, qualname): whether `obj` IS the definition the
    description addresses. The description is only the address; the proof is
    a property a rebinding cannot copy:
      - a module: sys.modules holds that very object;
      - a C function (builtin_function_or_method): its C name (read-only) and
        its __self__, which must itself be trusted (the builtins module, a
        trusted module or a trusted class);
      - an immutable type (CPython's Py_TPFLAGS_IMMUTABLETYPE: a type defined
        in C; Python code cannot set the flag, and its __module__ and
        __qualname__ cannot be assigned): its type name;
      - a Python function: no __wrapped__ layer, no closure, its __globals__
        IS the addressed module's namespace, and its code object EQUALS a
        code object compiled afresh from that module's own source file (the
        file its import spec names), at the same name and first line;
      - a Python class: the addressed module binds it at that name, its
        metaclass and every base are trusted, the module's source defines a
        class of that name, and every function in the class namespace is a
        trusted function of the module that defines it (a function the
        class's own body does not define, such as a metaclass-installed
        constructor, must be a trusted function of a module in the class's
        resolution order);
      - a bound method: its function trusted and its receiver the addressed
        module-level instance.
    Anything else is not trusted.
  * chain(obj): the wrapper chain of a callable read from the object itself,
    layer by layer through __wrapped__ (never inspect.unwrap, which discards
    the layers it passes): ((layer, its code object or None), ...).
  * Deps: a dependency record. A walk that is cached records every
    module-scope binding it read (the namespace object, the name, the object
    or _MISSING) and every callee chain it walked; a cache hit is honoured only
    while every recorded binding still IS the recorded object and every chain
    is equal layer by layer (valid()), otherwise the entry is dropped and the
    walk runs again.
  * observe(): the walks' one reporting point. Bindings.resolve (a module
    scope read) and Bindings.listed (a builtins fallback) report each read
    here; every active Deps on the stack records it.
"""
import ast as _ast
import builtins as _builtins
import importlib.util as _ilu
import os as _os
import sys as _sys
import types as _types

_MISSING = object()

# Literal-derived types: a rebinding of a builtins name cannot change them.
_BUILTIN_FN = type([].append)
_FUNCTION = type(lambda: 0)
_METHOD = type(_ast.NodeVisitor().visit)
_MODULE = type(_sys)
_IMMUTABLETYPE = 1 << 8

_CODES = {}
_CODE_OK = {}
_INDEX = {}

# Round 11 (ruling FOUR-R11-A1 (2), GROUP 1): modules a test builds from
# source text it holds (no file to recompile). id(module) -> [module,
# filename, text, frozen]. A registration is closed at freeze: the first
# proof that reads the module's text freezes it, after which a registration
# for that module (a second text, a re-registration) refuses.
_REGISTERED = {}
_TESTS_DIR = _os.path.normcase(_os.path.dirname(_os.path.realpath(__file__)))
_MEASURED = ("main",)


class RegistrationRefused(Exception):
    """register_source refused (after freeze, from the measured module, from
    the module itself, or for a module with a source file of its own)."""


def register_source(mod, src, filename):
    """Record that module `mod` is built from exactly `src`, compiled under
    `filename` (the module's __file__). The proof of such a module's
    definitions is code equality against a fresh compile of this text.

    Refused: after the module's freeze (its first proof), a module that has
    a source file of its own (a spec origin), a module already registered,
    a call made from the module's own namespace or from a measured module
    (main), and a call from any module that is not a test module of this
    directory."""
    if type(mod) is not _MODULE:
        raise RegistrationRefused("not a module")
    caller = _sys._getframe(1).f_globals
    if caller is vars(mod):
        raise RegistrationRefused("a registration from the module itself")
    if caller.get("__name__") in _MEASURED or any(
            caller is vars(m) for m in (_module(n) for n in _MEASURED)
            if m is not None):
        raise RegistrationRefused("a registration from the measured module")
    cf = caller.get("__file__")
    if not isinstance(cf, str) or _os.path.normcase(_os.path.dirname(
            _os.path.realpath(cf))) != _TESTS_DIR:
        raise RegistrationRefused("a registration from outside the tests")
    hit = _REGISTERED.get(id(mod))
    if hit is not None and hit[0] is mod:
        raise RegistrationRefused("the module is registered already"
                                  + (" and frozen" if hit[3] else ""))
    spec = vars(mod).get("__spec__")
    if getattr(spec, "origin", None) is not None:
        raise RegistrationRefused("the module has a source of its own")
    if vars(mod).get("__file__") != filename or not isinstance(src, str):
        raise RegistrationRefused("the filename is not the module's __file__")
    _REGISTERED[id(mod)] = [mod, filename, src, False]


def _registered(mod):
    hit = _REGISTERED.get(id(mod))
    return hit if hit is not None and hit[0] is mod else None


def _origin(mod):
    """The source the module's import spec names: a normalised .py path,
    "frozen" for a module frozen into the interpreter, ("registered",
    filename) for a module a test registered (register_source), or None (a
    built-in or extension module: no Python source). The spec is read from
    the module's own namespace."""
    reg = _registered(mod)
    if reg is not None:
        return ("registered", reg[1])
    spec = vars(mod).get("__spec__")
    origin = getattr(spec, "origin", None)
    if origin == "frozen":
        return "frozen"
    if not isinstance(origin, str) or not origin.endswith(".py"):
        return None
    return _os.path.normcase(_os.path.realpath(origin))


def _code_file_ok(code, mod, origin):
    if origin == "frozen":
        return True
    if isinstance(origin, tuple):
        return code.co_filename == origin[1]
    return _os.path.normcase(_os.path.realpath(code.co_filename)) == origin


def _fresh(mod):
    """Every code object of module `mod`'s own source, compiled afresh from
    the file its spec names (or, for a frozen module, read afresh from the
    interpreter's frozen table; for a registered module, from its registered
    text, which freezes the registration). None when the module has no
    Python source.

    Round 11 (ruling FOUR-R11-A1 (4)): a module's proof is made once and
    memoised by its path plus the size and md5 of the bytes compiled; a
    later call reuses it while the file's size and modification time are
    the ones read (a change re-reads, re-hashes and recompiles)."""
    origin = _origin(mod)
    if origin is None:
        return None
    name = vars(mod).get("__name__")
    if isinstance(origin, tuple):
        reg = _registered(mod)
        key = ("registered", id(mod))
        hit = _CODES.get(key)
        if hit is not None and hit[0] is mod:
            return hit[1]
        reg[3] = True                      # frozen: no registration after
        top = compile(reg[2], reg[1], "exec", dont_inherit=True)
        codes = _all_codes(top)
        _CODES[key] = (mod, codes)
        return codes
    key = (name, origin)
    hit = _CODES.get(key)
    if origin == "frozen":
        if hit is not None:
            return hit[1]
        import importlib.machinery as _im
        codes = _all_codes(_im.FrozenImporter.get_code(name))
        _CODES[key] = (None, codes)
        return codes
    st = _os.stat(origin)
    if hit is not None and hit[0][:2] == (st.st_size, st.st_mtime_ns):
        return hit[1]
    import hashlib as _hl
    with open(origin, "rb") as f:
        data = f.read()
    digest = (len(data), _hl.md5(data).hexdigest())
    if hit is not None and hit[0][2:] == digest:
        _CODES[key] = ((st.st_size, st.st_mtime_ns) + digest, hit[1])
        return hit[1]
    codes = _all_codes(compile(data, origin, "exec", dont_inherit=True))
    _CODES[key] = ((st.st_size, st.st_mtime_ns) + digest, codes)
    return codes


def _all_codes(top):
    codes, todo = [], [top]
    while todo:
        c = todo.pop()
        codes.append(c)
        todo.extend(k for k in c.co_consts if isinstance(k, _types.CodeType))
    return codes


def _module(name):
    m = _sys.modules.get(name)
    return m if type(m) is _MODULE else None


def _owner_module(fn):
    """The module whose namespace IS fn.__globals__ (by identity), or None."""
    g = fn.__globals__
    m = _module(g.get("__name__"))
    if m is not None and vars(m) is g:
        return m
    return None


def code_defined(code, mod):
    """Whether code object `code` equals one compiled afresh from module
    `mod`'s own source (same qualified name, same first line; for a .py
    module the same file)."""
    codes = _fresh(mod)
    if codes is None:
        return False
    if not _code_file_ok(code, mod, _origin(mod)):
        return False
    key = (id(code), id(mod))
    hit = _CODE_OK.get(key)
    if hit is not None and hit[0] is code and hit[1] is mod:
        return hit[2]
    index = _INDEX.get(id(codes))
    if index is None or index[0] is not codes:
        table = {}
        for c in codes:
            table.setdefault((c.co_qualname, c.co_firstlineno), []).append(c)
        index = _INDEX[id(codes)] = (codes, table)
    ok = any(c == code for c in index[1].get(
        (code.co_qualname, code.co_firstlineno), ()))
    # code objects are immutable: the verdict is kept with both objects held
    _CODE_OK[key] = (code, mod, ok)
    return ok


def trusted_function(fn, mod=None):
    """Whether `fn` is a plain Python function defined by module `mod`'s own
    source (by default the module whose namespace is its globals), with no
    wrapper layer and no closure."""
    if type(fn) is not _FUNCTION:
        return False
    if "__wrapped__" in vars(fn) or fn.__closure__ is not None:
        return False
    owner = _owner_module(fn)
    if owner is None or (mod is not None and owner is not mod):
        return False
    return code_defined(fn.__code__, owner)


def _class_functions(cls):
    """Every function object the class namespace holds, directly or inside a
    staticmethod, classmethod or property."""
    out = []
    for v in vars(cls).values():
        if isinstance(v, (staticmethod, classmethod)):
            v = v.__func__
        if isinstance(v, property):
            out.extend(x for x in (v.fget, v.fset, v.fdel) if x is not None)
            continue
        if type(v) is _FUNCTION:
            out.append(v)
    return out


def _attr_path(root, qualname):
    obj = root
    for part in qualname.split("."):
        obj = vars(obj).get(part, _MISSING) if hasattr(obj, "__dict__") else _MISSING
        if obj is _MISSING:
            return _MISSING
    return obj


# C descriptor types (a class defined in C holds only these as callables).
_C_DESCRIPTORS = (type(str.join), type(object.__init__), type(int.real),
                  type(vars(dict)["fromkeys"]),
                  type(_types.FunctionType.__code__))


def _c_member(cls, v):
    """Whether class-namespace value `v` is a C-level member of `cls`
    itself, which Python code cannot construct for another class."""
    if isinstance(v, _C_DESCRIPTORS):
        return getattr(v, "__objclass__", None) is cls
    if type(v) is _BUILTIN_FN:
        return v.__self__ is cls
    return False


def _generated_init(cls, fn):
    """SQLAlchemy's instrumented constructor: trusted when sqlalchemy's own
    generator (a trusted function), run afresh on the same class, manager
    and original constructor, yields an equal code object, and the
    function's globals hold exactly those inputs."""
    ins = _module("sqlalchemy.orm.instrumentation")
    if ins is None or fn.__globals__.get("__name__") != ins.__name__:
        return False
    gen = vars(ins).get("_generate_init")
    orig = vars(fn).get("_sa_original_init", _MISSING)
    mgr = vars(cls).get("_sa_class_manager", _MISSING)
    if not trusted_function(gen, ins) or orig is _MISSING or mgr is _MISSING:
        return False
    if not trusted_function(orig, None):
        return False
    fresh = gen(cls, mgr, orig)
    return (fresh.__code__ == fn.__code__
            and fn.__globals__.get("original_init") is orig
            and fn.__globals__.get("class_manager") is mgr
            and fn.__closure__ is None and "__wrapped__" not in vars(fn))


def trusted_class(cls, _seen=None):
    """Whether class `cls` is the class its own module defines (see the
    module docstring), or an immutable (C) type."""
    if not isinstance(cls, type):
        return False
    if cls.__flags__ & _IMMUTABLETYPE:
        return True
    seen = _seen if _seen is not None else set()
    if id(cls) in seen:
        return True
    seen.add(id(cls))
    mod = _module(vars(cls).get("__module__"))
    qual = vars(cls).get("__qualname__", cls.__qualname__)
    if mod is None or _attr_path(mod, qual) is not cls:
        return False
    if not trusted_class(type(cls), seen):
        return False
    if not all(trusted_class(b, seen) for b in cls.__bases__):
        return False
    codes = _fresh(mod) or ()
    leaf = qual.split(".")[-1]
    body = [c for c in codes if c.co_qualname == qual and c.co_name == leaf]
    if not body:
        # No class statement of this name in the module's source: a class
        # defined in C (a heap type). Every callable it holds must be a C
        # member of this very class; it may hold no Python function.
        if _class_functions(cls):
            return False
        return all(_c_member(cls, v) or not (callable(v) or hasattr(
            type(v), "__get__")) for k, v in vars(cls).items()
            if k not in ("__module__", "__doc__", "__qualname__"))
    own = {c.co_name for c in codes if c.co_qualname == qual + "." + c.co_name}
    for k, v in vars(cls).items():
        if k in ("__module__", "__doc__", "__qualname__"):
            continue
        if isinstance(v, (staticmethod, classmethod)):
            if type(v.__func__) is not _FUNCTION:
                return False
            continue
        if type(v) is _FUNCTION or isinstance(v, property) or _c_member(cls, v):
            continue
        # any other callable or descriptor runs code of its own type: that
        # type must be trusted (sqlalchemy's column attributes, pydantic's
        # class attributes)
        if (callable(v) or hasattr(type(v), "__get__")) and not (
                isinstance(v, type) and trusted_class(v, seen)
                or trusted_class(type(v), seen)):
            return False
    for fn in _class_functions(cls):
        if "__wrapped__" in vars(fn) and not _generated_init(cls, fn):
            return False
        owner = _owner_module(fn)
        if owner is None:
            if not _generated_init(cls, fn):
                return False
            continue
        if not code_defined(fn.__code__, owner):
            return False
        if owner is mod and fn.__code__.co_qualname.startswith(qual + "."):
            if fn.__code__.co_name not in own:
                return False
        elif _attr_path(owner, fn.__code__.co_qualname) is not fn:
            # Not the class body's own: an alias of a definition another
            # module's source makes, bound there at its qualified name.
            return False
    return True


_CONSTS = {}


def _top_constants(mod):
    """{name: the constant} for every name module `mod`'s own top-level
    code binds exactly once, by a constant loaded straight into that one
    store (`NAME = <literal>`, `NAME: T = <literal>`), and that no nested
    code of the module writes (STORE_GLOBAL, DELETE_GLOBAL). Read from the
    module's fresh code objects (_fresh: compiled once per path, size and
    md5), never from an AST kept in memory (round 11: main.py's AST held
    for this outgrew the seats' memory bound). Memoised by the identity of
    the fresh code list."""
    codes = _fresh(mod)
    if not codes:
        return {}
    hit = _CONSTS.get(id(codes))
    if hit is not None and hit[0] is codes:
        return hit[1]
    import dis as _dis
    top = codes[0]
    stores, out, prev = {}, {}, None
    for ins in _dis.get_instructions(top):
        if ins.opname in ("STORE_NAME", "DELETE_NAME", "STORE_GLOBAL",
                          "DELETE_GLOBAL"):
            stores[ins.argval] = stores.get(ins.argval, 0) + 1
            if (ins.opname == "STORE_NAME" and prev is not None
                    and prev.opname == "LOAD_CONST"):
                out.setdefault(ins.argval, []).append(prev.argval)
        prev = ins
    nested = set()
    for c in codes[1:]:
        for ins in _dis.get_instructions(c):
            if ins.opname in ("STORE_GLOBAL", "DELETE_GLOBAL"):
                nested.add(ins.argval)
    table = {k: v[0] for k, v in out.items()
             if len(v) == 1 and stores.get(k) == 1 and k not in nested}
    _CONSTS[id(codes)] = (codes, table)
    return table


def trusted_constant(v, mod, name):
    """Whether data value `v` is the literal module `mod`'s own source binds
    `name` to: exactly one binding of `name` in the module's code, a
    constant stored straight into it, of exactly v's type and equal to it,
    and no function of the module writes `name` (_top_constants)."""
    origin = _origin(mod)
    if origin is None or origin == "frozen":
        return False
    table = _top_constants(mod)
    if name not in table:
        return False
    lit = table[name]
    return type(v) is type(lit) and v == lit


def trusted(obj, module, qualname):
    """Whether `obj` IS the definition addressed by (module, qualname);
    module "<module>" addresses a module named `qualname`."""
    if module == "<module>":
        return type(obj) is _MODULE and _module(qualname) is obj
    if isinstance(obj, _C_DESCRIPTORS):
        # a method of a type defined in C (dict.get): its defining type,
        # read-only on the descriptor, is immutable and named by the
        # description, and the name is the descriptor's own
        owner = getattr(obj, "__objclass__", None)
        cls_q, _, leaf = qualname.rpartition(".")
        return (isinstance(owner, type) and bool(owner.__flags__ & _IMMUTABLETYPE)
                and owner.__module__ == module and owner.__qualname__ == cls_q
                and obj.__name__ == leaf and vars(owner).get(leaf) is obj)
    if type(obj) is _BUILTIN_FN:
        owner = obj.__self__
        leaf = qualname.split(".")[-1]
        if obj.__name__ != leaf:
            return False
        if owner is _builtins:
            return module == "builtins"
        if type(owner) is _MODULE:
            return _module(module) is owner
        if isinstance(owner, type):
            return (trusted_class(owner)
                    and qualname == owner.__qualname__ + "." + leaf)
        return False
    if isinstance(obj, type):
        if obj.__flags__ & _IMMUTABLETYPE:
            return obj.__module__ == module and obj.__qualname__ == qualname
        mod = _module(module)
        return (mod is not None and _attr_path(mod, qualname) is obj
                and trusted_class(obj))
    if type(obj) is _METHOD:
        fn, inst = obj.__func__, obj.__self__
        mod = _module(module)
        if mod is None or not trusted_function(fn, None):
            return False
        cls_q, _, leaf = qualname.rpartition(".")
        cls = _attr_path(_module(fn.__globals__["__name__"]), cls_q)
        return (fn.__name__ == leaf and isinstance(cls, type)
                and type(inst) is cls and trusted_class(cls)
                and vars(cls).get(leaf) is fn
                and any(v is inst for v in vars(mod).values()))
    if type(obj) in (type(0), type(""), type(0.0), type(True), type(()),
                     type(frozenset()), type(b""), type(None)):
        mod = _module(module)
        return mod is not None and "." not in qualname and trusted_constant(
            obj, mod, qualname)
    if type(obj) is _FUNCTION:
        mod = _module(module)
        return (mod is not None and trusted_function(obj, None)
                and _attr_path(_owner_module(obj), qualname) is obj
                and (_owner_module(obj) is mod
                     or vars(mod).get(qualname.split(".")[-1]) is obj))
    return False


def chain(obj):
    """The wrapper chain of `obj`, read from the object: ((layer, code or
    None), ...), outermost first, through each layer's own __wrapped__."""
    out, seen = [], set()
    while obj is not None and id(obj) not in seen:
        seen.add(id(obj))
        out.append((obj, getattr(obj, "__code__", None)))
        nxt = vars(obj).get("__wrapped__", None) if hasattr(obj, "__dict__") else None
        obj = nxt
    return tuple(out)


def same_chain(a, b):
    """Whether two chains are equal layer by layer: the same objects, the
    same code objects."""
    return len(a) == len(b) and all(
        x[0] is y[0] and x[1] is y[1] for x, y in zip(a, b))


class Deps:
    """The bindings and chains one cached walk read (see the module
    docstring), each kept once: reads by (namespace, name), chains by the
    function object."""

    __slots__ = ("reads", "chains")

    def __init__(self):
        self.reads = {}
        self.chains = {}

    def valid(self):
        for ns, name, obj in self.reads.values():
            if _lookup(ns, name) is not obj:
                return False
        for fn, ch in self.chains.values():
            if not same_chain(chain(fn), ch):
                return False
        return True

    def extend(self, other):
        for k, v in other.reads.items():
            self.reads.setdefault(k, v)
        for k, v in other.chains.items():
            self.chains.setdefault(k, v)


_STACK = []


def _lookup(ns, name):
    if isinstance(ns, dict):
        return ns.get(name, _MISSING)
    return getattr(ns, name, _MISSING)


def observe(ns, name, obj):
    """A module-scope read by a walk (ns a module or a builtins mapping):
    every active Deps records it (the first object read is kept; the
    namespace object is held, so its id stays its own)."""
    key = (id(ns), name)
    for d in _STACK:
        d.reads.setdefault(key, (ns, name, obj))


def observe_chain(fn):
    """A callee chain the walk walked: every active Deps records it."""
    ch = chain(fn)
    for d in _STACK:
        d.chains.setdefault(id(fn), (fn, ch))
    return ch


def carry(deps):
    """A cached walk's Deps, honoured as a hit: every active Deps takes
    them over, so an enclosing cached walk depends on them too."""
    for d in _STACK:
        if d is not deps:
            d.extend(deps)


class recording:
    """with recording() as deps: the walk's reads go into `deps` (and into
    every enclosing recording)."""

    def __enter__(self):
        self.deps = Deps()
        _STACK.append(self.deps)
        return self.deps

    def __exit__(self, *exc):
        _STACK.remove(self.deps)
        return False
