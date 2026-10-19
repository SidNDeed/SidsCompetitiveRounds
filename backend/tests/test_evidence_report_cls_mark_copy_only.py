"""Admin evidence report, phase 1a item 9: the privacy pass, 1a scope (design 6.4).

A privacy-specific AST dataflow pass over the report's seeds, not the route
manifest walker (that one follows data bindings only). Seeds: every function
and module constant of backend/api/admin_evidence.py, every `_aer_*` function
of backend/discord_bot.py, and the render worker module
backend/aer_render_worker.py.

Closure. Every reference is followed into the seed modules: module functions,
dispatch dicts and sequences of callables, aliases, `functools.partial`,
lambdas, decorators, default arguments, methods of the module's own classes
and literal `getattr` names. A call target that cannot be resolved
(non-literal `getattr`, `globals()`, `vars()`, `eval`, `exec`, `compile`,
`importlib`, `__import__`, non-literal `attrgetter` or `methodcaller`, or a
callable value with no known origin) is a finding: the pass fails closed.

Labels. Each value carries the roots it may come from:
  C  fixed chrome: a literal or a module constant;
  S  structural order: the plan's item kind, a position or count in the plan,
     the page number and page count, a length;
  E  displayable: an `_aer_enc` return (api), the bot's duplicate of it, or a
     BotPage display slot;
  P  a decoded BotPage (its display slots are E, its page fields S);
  F  a number formatted into text (`%d`, `%f`, `{:.2f}`, ...);
  D  any other data (database row, process input, untyped API argument);
  R  structural request data from an API entry point's Request annotation;
  Q  the bot's request and delivery data (command arguments, the api's
     status and refusal detail); cell data reaches the bot only inside a
     served body and leaves the 1a decoder as P;
  K  a value classified by an ordering comparison of E or D data against a
     bound (the shape a class rule has);
  O  a value-keyed order (a sort or min/max keyed on E or D data).
Labels flow through assignment, arithmetic, formatting, calls, indexing and
iteration (explicit), and from every test, loop or filter a value is chosen
under (implicit). A loop over a named sequence is a structural loop: only the
sequence's D, K and O labels become implicit.

Sinks (default deny). Every parameter of every third-party call is an
APPEARANCE sink unless the closed table AER_PARAM_CLASS names its class:
  layout     box positions and extents, alignment, axis limits;
  data       sparkline arrays;
  display    a displayed string (text call, message, attachment name, a
             plan item's text);
  transport  bytes moved and not drawn (database, http, pipe, JSON);
  value      a pure function whose result carries its arguments' labels.
Appearance and layout sinks accept C and S only, explicit or implicit (and Q
implicitly: which delivery path runs follows the api's status, never a cell).
Display sinks accept C, S, E, F and P explicitly; showing data as text is
permitted, so a display sink reads its explicit roots only, but a value chosen
by a class-shaped comparison (K) is itself K, so a displayed word chosen that
way is refused.
Every key, keyword or attribute named `cls` or `mark` is an appearance sink;
phase 1a accepts only chrome there. The api's free-text display slots
(`name`, `reason`, `invalidated`) are display sinks. Also refused: an SQL
literal naming `c1`, `c2`, `c3`, `cls` or `mark`; a text call without
`parse_math=False`; and a numeric literal outside CONTRACT_BOUNDS,
DISPLAY_DEFAULTS and AER_NUMERIC_ALLOW compared with, or combined by
arithmetic with, E or D data (the place a copied threshold would sit).

The worker is a separate process: its plan arrives over a pipe as JSON. The
contract AER_CONTRACTS declares what the bot side proves: every item kind is
chrome (AerItem's `kind` parameter is an appearance sink) and every item text
is display text (AerItem's `text` parameter is a display sink), so the
worker's `render(plan)` reads kinds as S and texts as E.

Deviations from the design's wording are recorded in the lane notes (D11).
"""

import ast
import os
import re

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.path.join(BACKEND, "api", "admin_evidence.py")
BOT = os.path.join(BACKEND, "discord_bot.py")
WORKER = os.path.join(BACKEND, "aer_render_worker.py")

C, S, E, P, F, D, R, Q, K, O = "C", "S", "E", "P", "F", "D", "R", "Q", "K", "O"
APPEARANCE_OK = frozenset({C, S})
DISPLAY_OK = frozenset({C, S, E, F, P})

# ── The closed parameter table ─────────────────────────────────────────────
# Key: (callable, parameter). A callable is a dotted name rooted at an import
# (`json.dumps`), a builtin (`len`), a module class (`AerItem`) or, for a
# method of an object whose type the pass does not resolve, `.<method>`.
# A parameter is a keyword name, `#<n>` for the n-th positional argument, or
# `*` for every parameter. `<module>.*` covers every callable of a module.
LAYOUT, DATA, DISPLAY, TRANSPORT, VALUE, APPEAR = (
    "layout", "data", "display", "transport", "value", "appearance")

_VALUE_BUILTINS = (
    "str", "int", "float", "bool", "repr", "len", "abs", "min", "max", "sum", "round",
    "sorted", "reversed", "enumerate", "zip", "range", "tuple", "list", "dict", "set",
    "frozenset", "isinstance", "any", "all", "ord", "chr", "hex", "divmod", "iter",
    "next", "map", "filter", "type", "id", "hash", "format", "bytes", "slice", "object",
    "super", "print")
_VALUE_EXCEPTIONS = (
    "ValueError", "TypeError", "KeyError", "RuntimeError", "Exception", "AssertionError",
    "LookupError", "IndexError", "OverflowError", "ZeroDivisionError")
_VALUE_METHODS = (
    "get", "items", "keys", "values", "split", "rsplit", "strip", "lstrip", "rstrip",
    "lower", "upper", "replace", "startswith", "endswith", "isdigit", "isalnum", "join",
    "encode", "decode", "index", "count", "copy", "isoformat", "group", "groups",
    "to_bytes", "from_bytes", "hexdigest", "digest", "fullmatch", "match", "search",
    "total_seconds", "timestamp", "astimezone", "pop", "popitem", "union", "intersection",
    "difference", "issubset", "issuperset", "__le__", "__ge__", "format", "zfill", "ljust",
    "rjust", "find",
    "partition", "rpartition", "casefold", "title", "tolist", "tobytes", "hex",
    "most_common", "elements", "bit_length", "getvalue", "get_text", "get_window_extent",
    "get_renderer", "translate", "removeprefix", "removesuffix", "move_to_end",
    "is_integer", "date", "time", "utcoffset", "lower_bound", "fetchall", "fetchone",
    "first", "all", "one", "one_or_none", "scalar", "scalars", "mappings", "keys",
    "_asdict", "_replace", "result", "done", "locked", "cancelled", "exception")
_MUTATORS = ("append", "extend", "add", "update", "insert", "setdefault", "appendleft",
             "discard", "remove", "clear", "sort", "__setitem__")
_SET_CONTAINMENT_CALLS = frozenset({
    ".issubset", ".issuperset", ".__le__", ".__ge__", "operator.le", "operator.ge"})
_SET_ORDERED_CALLS = frozenset({".__le__", ".__ge__", "operator.le", "operator.ge"})
_TRANSPORT_METHODS = (
    "execute", "stream", "commit", "rollback", "close", "begin", "begin_nested", "flush",
    "write", "drain", "read", "readexactly", "wait", "kill", "terminate", "acquire",
    "release", "set", "clear", "send", "send_message", "defer", "edit", "add_item",
    "add_command", "info", "warning", "error", "exception", "debug", "log", "cancel",
    "set_result", "wait_for", "add_done_callback", "connection", "get_raw_connection",
    "run_sync", "notify", "put", "put_nowait", "get_nowait", "__aenter__", "__aexit__",
    "readline", "seek", "tell", "truncate", "savefig", "canvas_draw", "draw", "close_fig",
    "headers_items", "json", "text_body")

AER_PARAM_CLASS = {}
for _n in _VALUE_BUILTINS + _VALUE_EXCEPTIONS:
    AER_PARAM_CLASS[(_n, "*")] = VALUE
for _n in _VALUE_METHODS:
    AER_PARAM_CLASS[("." + _n, "*")] = VALUE
for _n in _TRANSPORT_METHODS:
    AER_PARAM_CLASS[("." + _n, "*")] = TRANSPORT
for _mod in ("math", "time", "hashlib", "hmac", "itertools", "collections", "json",
             "base64", "datetime", "_dt", "re", "urllib.parse", "array", "dataclasses",
             "typing", "functools", "os.path", "struct", "sys", "io", "inspect",
             "tracemalloc", "resource", "statistics", "decimal", "operator", "uuid"):
    AER_PARAM_CLASS[(_mod + ".*", "*")] = VALUE
for _mod in ("asyncio", "logging", "sqlalchemy", "fastapi", "aiohttp", "os"):
    AER_PARAM_CLASS[(_mod + ".*", "*")] = TRANSPORT
AER_PARAM_CLASS.update({
    # the api: routing, responses, database
    ("APIRouter", "*"): TRANSPORT, ("Depends", "*"): TRANSPORT,
    ("HTTPException", "*"): TRANSPORT, ("JSONResponse", "*"): TRANSPORT,
    ("Response", "*"): TRANSPORT, ("text", "*"): TRANSPORT,
    ("database.get_db", "*"): TRANSPORT, ("field", "*"): VALUE, ("dataclass", "*"): VALUE,
    ("Optional", "*"): VALUE, ("array", "*"): VALUE,
    (".get", "*"): VALUE, (".head", "*"): TRANSPORT, (".post", "*"): TRANSPORT,
    # the bot: discord, http, the worker process
    ("discord.File", "#0"): TRANSPORT, ("discord.File", "fp"): TRANSPORT,
    ("discord.File", "filename"): DISPLAY,
    ("discord.ui.View", "timeout"): TRANSPORT,
    ("discord.ui.Button", "style"): APPEAR, ("discord.ui.Button", "label"): DISPLAY,
    ("discord.ui.Button", "custom_id"): TRANSPORT, ("discord.ui.Button", "disabled"): LAYOUT,
    ("discord.AllowedMentions.none", "*"): TRANSPORT,
    ("app_commands.Group", "*"): DISPLAY, ("app_commands.describe", "*"): DISPLAY,
    (".command", "name"): DISPLAY, (".command", "description"): DISPLAY,
    (".send", "#0"): DISPLAY, (".send", "content"): DISPLAY,
    (".send", "files"): TRANSPORT, (".send", "file"): TRANSPORT,
    (".send", "view"): TRANSPORT, (".send", "allowed_mentions"): TRANSPORT,
    # `ephemeral` is the delivery scope the api's answer selects (design 9.2
    # Q4: refusals ephemeral, served pages public), not a drawn property
    (".send", "ephemeral"): TRANSPORT,
    (".send_message", "#0"): DISPLAY, (".send_message", "content"): DISPLAY,
    (".send_message", "ephemeral"): TRANSPORT,
    (".edit", "content"): DISPLAY, (".edit", "attachments"): TRANSPORT,
    (".edit", "view"): TRANSPORT, (".edit", "allowed_mentions"): TRANSPORT,
    (".defer", "ephemeral"): TRANSPORT,
    ("int.from_bytes", "*"): VALUE, ("ctypes.*", "*"): VALUE, ("wintypes.*", "*"): VALUE,
    ("ctypes.wintypes.*", "*"): VALUE, ("starlette.call_next", "*"): TRANSPORT,
    (".write", "*"): TRANSPORT, (".read", "*"): TRANSPORT,
    ("AerItem", "#0"): APPEAR, ("AerItem", "kind"): APPEAR,
    ("AerItem", "#1"): DATA, ("AerItem", "fields"): DATA,
    ("AerItem", "#2"): DISPLAY, ("AerItem", "parts"): DISPLAY,
    ("AerItem", "#3"): DISPLAY, ("AerItem", "text"): DISPLAY,
    ("BotPage", "*"): VALUE, ("AerSchemaError", "*"): VALUE,
    ("urllib.parse.quote", "*"): VALUE,
    # the worker: matplotlib, fixed chrome only
    ("matplotlib.use", "#0"): APPEAR,
    ("matplotlib.pyplot.figure", "figsize"): LAYOUT, ("matplotlib.pyplot.figure", "dpi"): LAYOUT,
    ("matplotlib.pyplot.close", "#0"): TRANSPORT,
    (".add_axes", "#0"): LAYOUT, (".set_axis_off", "*"): LAYOUT,
    (".set_xlim", "*"): LAYOUT, (".set_ylim", "*"): LAYOUT,
    (".set_facecolor", "#0"): APPEAR,
    (".text", "#0"): LAYOUT, (".text", "#1"): LAYOUT, (".text", "#2"): DISPLAY,
    (".text", "ha"): LAYOUT, (".text", "va"): LAYOUT, (".text", "transform"): LAYOUT,
    (".text", "zorder"): LAYOUT, (".text", "clip_on"): LAYOUT,
    (".savefig", "#0"): TRANSPORT, (".savefig", "format"): APPEAR,
    (".savefig", "facecolor"): APPEAR,
    (".draw", "*"): TRANSPORT,
    (".get_window_extent", "renderer"): VALUE,
    ("base64.b64encode", "*"): VALUE, ("base64.b64decode", "*"): VALUE,
})
# `.text`'s color, fontsize, fontweight, family, bbox, parse_math and every
# other parameter stay appearance sinks (accept chrome and structure only).

# Numeric literals allowed beside the allowlist of the design (0, 1, 2, -1,
# 0.5, 1000), CONTRACT_BOUNDS and DISPLAY_DEFAULTS: HTTP status words of the
# api's closed refusal set (4.2), compared with a response status.
AER_NUMERIC_ALLOW = frozenset({0, 1, 2, -1, 0.5, 1000,
                               200, 400, 403, 404, 409, 429, 500, 503})

# Declared roots and contracts.
AER_ROOTS = {
    ("api", "_aer_enc"): frozenset({E}),          # the api's one display writer
    ("bot", "_aer_enc_text"): frozenset({E}),     # its duplicate, under an equality test
    ("bot", "_aer_decode_response"): frozenset({P}),   # the 1a decoder's BotPage
}
AER_STRUCTURAL_SLOTS = frozenset({"page", "pages", "shape"})   # BotPage fields that are S
AER_CONTRACTS = {
    # worker render(plan): kinds are chrome checked at AerItem, texts are display
    # text checked at AerItem (the bot's `_aer_render` sends exactly those two).
    ("worker", "render", "plan"): ("seq", ("tup", (S, E))),
    # the ASGI middleware's next handler, supplied by the framework
    ("api", "evidence_key_gate", "call_next"): ("third_party", "starlette.call_next"),
}

UNRESOLVABLE = frozenset({"globals", "vars", "eval", "exec", "compile", "__import__",
                          "locals", "setattr", "delattr"})
SQL_WORDS = re.compile(r"\b(SELECT|FROM|WHERE|INSERT|UPDATE)\b")
SQL_BAD = re.compile(r"\b(c1|c2|c3|cls|mark)\b")


# ── Values ─────────────────────────────────────────────────────────────────

class DictRef:
    """One allocation-site identity and its monotone mutable dictionary state."""

    __slots__ = ("token", "initialized", "keys", "must_keys", "vals", "item")

    def __init__(self, token):
        self.token = token
        self.initialized = False
        self.keys = None
        self.must_keys = frozenset()
        self.vals = ()
        self.item = None

    def seed(self, keys, vals):
        keys = tuple(keys)
        vals = tuple(vals)
        if not self.initialized:
            self.initialized = True
            self.keys = keys
            self.must_keys = frozenset(keys)
            self.vals = vals
        elif self.keys is None:
            self.item = vjoin(self.item, *vals)
        else:
            current_keys = list(self.keys)
            current_vals = list(self.vals)
            for key, value in zip(keys, vals):
                if key in current_keys:
                    pos = current_keys.index(key)
                    current_vals[pos] = vjoin(current_vals[pos], value)
                else:
                    current_keys.append(key)
                    current_vals.append(value)
            self.keys = tuple(current_keys)
            self.vals = tuple(current_vals)

    def element(self):
        if self.keys is not None:
            return vjoin(*self.vals)
        return self.item if self.item is not None else V()

    def read(self, key):
        if self.keys is None:
            return self.element()
        if key not in self.keys:
            return None
        return self.vals[self.keys.index(key)]

    def slot_update(self, key, new, only_if_missing=False):
        if self.keys is None:
            self.item = vjoin(self.item, new)
            return
        keys = list(self.keys)
        vals = list(self.vals)
        if key in keys:
            if only_if_missing and key in self.must_keys:
                return
            pos = keys.index(key)
            vals[pos] = vjoin(vals[pos], new)
        else:
            keys.append(key)
            vals.append(new)
        self.keys = tuple(keys)
        self.vals = tuple(vals)

    def dynamic_update(self, new):
        self.item = vjoin(self.element(), new)
        self.keys = None
        self.vals = ()

    def key(self, seen=frozenset()):
        if self.token in seen:
            return ("dict_ref", self.token)
        nested = seen | {self.token}
        return ("dict_ref", self.token, self.keys, self.must_keys,
                tuple(v.key(nested) for v in self.vals),
                self.item.key(nested) if self.item is not None else None)


class V:
    """An abstract value: explicit labels, implicit labels, the functions it
    may name, and (for fixed tuples and homogeneous sequences) its parts."""
    __slots__ = ("ex", "im", "funcs", "elems", "item", "alias")

    def __init__(self, ex=(), im=(), funcs=(), elems=None, item=None, alias=None):
        self.ex = frozenset(ex)
        self.im = frozenset(im)
        self.funcs = frozenset(funcs)
        self.elems = elems
        self.item = item
        self.alias = alias

    def flat(self):
        return self.ex_all() | self.im_all()

    def parts(self):
        out = list(self.elems or ())
        if self.item is not None:
            out.append(self.item)
        if self.alias is not None and self.alias[0] == "dict":
            ref = self.alias[1]
            out.extend(ref.vals if ref.keys is not None else (ref.element(),))
        elif self.alias is not None and self.alias[0] == "dict_alternatives":
            out.extend(self.alias[1])
        return out

    def ex_all(self):
        """Explicit labels, nested parts included."""
        out = set(self.ex)
        for e in self.parts():
            out |= e.ex_all()
        return frozenset(out)

    def im_all(self):
        """Implicit labels, nested parts included."""
        out = set(self.im)
        for e in self.parts():
            out |= e.im_all()
        return frozenset(out)

    def key(self, seen=frozenset()):
        alias = self.alias
        if alias is not None and alias[0] == "dict":
            alias = alias[1].key(seen)
        elif alias is not None and alias[0] == "dict_alternatives":
            alias = ("dict_alternatives", tuple(arm.key(seen) for arm in alias[1]))
        elif alias is not None:
            alias = _alias_key(alias)
        return (self.ex, self.im, self.funcs,
                tuple(e.key(seen) for e in self.elems) if self.elems is not None else None,
                self.item.key(seen) if self.item is not None else None, alias)


def vjoin(*vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return V()
    if len(vals) == 1:
        return vals[0]
    ex = set().union(*[v.ex for v in vals])
    im = set().union(*[v.im for v in vals])
    funcs = set().union(*[v.funcs for v in vals])
    elems = None
    lens = {len(v.elems) if v.elems is not None else None for v in vals}
    if len(lens) == 1 and None not in lens:
        elems = tuple(vjoin(*[v.elems[i] for v in vals]) for i in range(lens.pop()))
    else:
        for v in vals:
            for e in v.elems or ():
                ex |= e.ex_all()
                im |= e.im_all()
    items = [v.item for v in vals if v.item is not None]
    item = vjoin(*items) if items else None
    aliases = [v.alias for v in vals]
    scalar_arms = all(a is not None or
                      (v.ex in (frozenset(), frozenset({C})) and v.im <= {S} and not v.funcs and
                       v.elems is None and v.item is None)
                      for v, a in zip(vals, aliases))
    alias = _join_alias(aliases) if scalar_arms else None
    if alias is None:
        alias = _dict_alternatives(vals)
        if alias is not None:
            for v in vals:
                if not _dict_arms(v):
                    ex |= v.ex_all()
                    im |= v.im_all()
        else:
            # Tuple/sequence parts are retained or folded above. A discarded
            # alias must contribute all its labels, even beside aliasless arms.
            for v in vals:
                if v.alias is not None:
                    ex |= v.ex_all()
                    im |= v.im_all()
    return V(ex, im, funcs, elems, item, alias)


def _alias_key(a):
    return None if a is None else tuple(x if not isinstance(x, (V, ast.AST)) else id(x)
                                         if isinstance(x, ast.AST) else None for x in a)


def _dict_aliases(alias):
    """Every constant-key dictionary arm retained by an alias."""
    if alias is None:
        return ()
    if alias[0] == "dict":
        return (alias,)
    if alias[0] == "dict_alternatives":
        return tuple(arm.alias for arm in alias[1])
    return ()


def _dict_arms(value):
    if value.alias is None:
        return ()
    if value.alias[0] == "dict":
        return (value,)
    if value.alias[0] == "dict_alternatives":
        return value.alias[1]
    return ()


def _dict_alternatives(values):
    """Retain incompatible dictionary arms without folding their sibling slots."""
    arms = []
    seen = set()
    for value in values:
        for arm in _dict_arms(value):
            key = arm.key()
            if key not in seen:
                seen.add(key)
                arms.append(arm)
    if not arms:
        return None
    return ("dict_alternatives", tuple(arms))


def _join_alias(aliases):
    """One alias when the named alternatives agree; aliasless optional
    alternatives do not erase it, and distinct dictionaries stay distinct."""
    present = [a for a in aliases if a is not None]
    if not present:
        return None
    dicts = [_dict_aliases(a) for a in present]
    if all(dicts):
        arms = [arm for group in dicts for arm in group]
        refs = {a[1].token: a[1] for a in arms}
        if len(refs) == 1:
            return ("dict", next(iter(refs.values())))
    if len({_alias_key(a) for a in present}) == 1:
        return present[0]
    return None


def add_im(v, labels):
    """`v` with more implicit labels, its structure kept."""
    if not labels:
        return v
    alias = v.alias
    if alias is not None and alias[0] == "dict_alternatives":
        alias = ("dict_alternatives", tuple(add_im(arm, labels) for arm in alias[1]))
    return V(v.ex, v.im | frozenset(labels), v.funcs, v.elems, v.item, alias)


def contract_value(spec):
    if isinstance(spec, str):
        return V({spec})
    kind, inner = spec
    if kind == "seq":
        return V((), (), (), None, contract_value(inner))
    if kind == "third_party":
        return V({C}, alias=("import", inner))
    return V((), (), (), tuple(contract_value(x) for x in inner))


def element(v):
    """The value of one element of `v` when iterated or indexed by a value."""
    dicts = _dict_arms(v)
    if dicts:
        return vjoin(V(v.ex, v.im),
                     *[add_im(arm.alias[1].element(), arm.im) for arm in dicts])
    if v.item is not None:
        return add_im(v.item, v.ex | v.im)
    if v.elems is not None:
        return add_im(vjoin(*v.elems), v.im)
    out = V(v.ex, v.im, v.funcs)
    if P in out.ex:
        out = V((out.ex - {P}) | {E}, out.im, out.funcs)
    return out


def _dict_slot_update(value, key, new, only_if_missing=False):
    """Join `new` into one literal dictionary slot while retaining siblings."""
    refs = {arm.alias[1].token: arm.alias[1] for arm in _dict_arms(value)}
    if not refs:
        return None
    for ref in refs.values():
        ref.slot_update(key, new, only_if_missing)
    return value


def _dict_dynamic_update(value, new):
    """Forget a dictionary's slots after a dynamic mutation, but keep their
    joined element structure for conservative reads."""
    refs = {arm.alias[1].token: arm.alias[1] for arm in _dict_arms(value)}
    if not refs:
        return None
    for ref in refs.values():
        ref.dynamic_update(new)
    return value


def _dict_literal_slots(value):
    """Literal slots for every possible dictionary identity, or None if folded."""
    refs = {arm.alias[1].token: arm.alias[1] for arm in _dict_arms(value)}
    if not refs or any(ref.keys is None for ref in refs.values()):
        return None
    return [(key, slot) for ref in refs.values()
            for key, slot in zip(ref.keys, ref.vals)]


def annotation_origin(mod, node):
    """The import-resolved dotted name of a direct annotation node."""
    if isinstance(node, ast.Name):
        return mod.imports.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = annotation_origin(mod, node.value)
        return (base + "." + node.attr) if base else None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return mod.imports.get(node.value, node.value)
    return None


def is_request_annotation(mod, node):
    """Whether an annotation denotes the framework's structural request."""
    origin = annotation_origin(mod, node)
    if origin in ("fastapi.Request", "starlette.requests.Request"):
        return True
    if isinstance(node, ast.Subscript):
        return is_request_annotation(mod, node.slice)
    if isinstance(node, ast.BinOp):
        return is_request_annotation(mod, node.left) or is_request_annotation(mod, node.right)
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(is_request_annotation(mod, item) for item in node.elts)
    return False


# ── Modules and the closure ────────────────────────────────────────────────

class Module:
    def __init__(self, kind, source, path, seed):
        self.kind = kind
        self.path = path
        self.tree = ast.parse(source)
        self.seed = seed
        self.funcs = {}         # name -> FunctionDef (module level and class methods)
        self.methods = {}       # method name -> [qualified names]
        self.classes = set()
        self.imports = {}       # local name -> dotted origin
        self.consts = {}        # module-level name -> assignment value node
        self.state = set()      # module names written through `global`
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs[node.name] = node
            elif isinstance(node, ast.ClassDef):
                self.classes.add(node.name)
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        q = node.name + "." + sub.name
                        self.funcs[q] = sub
                        self.methods.setdefault(sub.name, []).append(q)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    self.imports[(a.asname or a.name).split(".")[0]] = (
                        a.name if a.asname else a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    self.imports[a.asname or a.name] = "%s.%s" % (node.module, a.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    for n in ast.walk(t):
                        if isinstance(n, ast.Name):
                            self.consts[n.id] = node.value
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Global):
                self.state.update(node.names)
            if isinstance(node, (ast.Import, ast.ImportFrom)) and node not in self.tree.body:
                for a in node.names:
                    local = (a.asname or a.name).split(".")[0]
                    if isinstance(node, ast.Import):
                        self.imports.setdefault(local, a.name if a.asname else local)
                    else:
                        self.imports.setdefault(local, "%s.%s" % (node.module, a.name))

    def seeds(self):
        return [q for q in self.funcs if self.seed(q)]


class Finding(tuple):
    def __str__(self):
        return "%s:%d %s" % self


class Pass:
    def __init__(self, modules):
        self.mods = {m.kind: m for m in modules}
        self.params = {}        # (kind, qname) -> {param: V}
        self.ctx_in = {}        # (kind, qname) -> frozenset implicit labels
        self.returns = {}       # (kind, qname) -> V
        self.closure = set()
        self.lambdas = {}       # id -> (kind, node)
        self.findings = set()
        self.recording = False
        self.state_vals = {}    # (kind, name) -> V for `global` module state
        self.dict_refs = {}     # (function, literal site) -> shared mutable dictionary
        self.called = set()     # functions with a call site inside the closure
        self.entries = set()    # functions no closure function calls

    # -- driver --
    def run(self, max_rounds=60):
        """Fixpoint over the closure. A function called from inside the closure
        takes its arguments from its call sites only; one that no closure
        function calls is an entry point, whose arguments are data."""
        for m in self.mods.values():
            for q in m.seeds():
                self.closure.add((m.kind, q))
        for _ in range(max_rounds):
            before = self.snapshot()
            for fk in sorted(self.closure, key=str):
                self.analyze(fk)
            entries = {fk for fk in self.closure if fk not in self.called}
            if self.snapshot() == before and entries == self.entries:
                break
            self.entries = entries
        self.recording = True
        for fk in sorted(self.closure, key=str):
            self.analyze(fk)
        for m in self.mods.values():
            self.scan_module(m)
        return sorted(self.findings)

    def snapshot(self):
        return (frozenset(self.closure),
                tuple(sorted((str(k), tuple(sorted((p, v.key()) for p, v in d.items())))
                             for k, d in self.params.items())),
                tuple(sorted((str(k), v.key()) for k, v in self.returns.items())),
                tuple(sorted((str(k), tuple(sorted(v))) for k, v in self.ctx_in.items())),
                tuple(sorted((str(k), v.key()) for k, v in self.state_vals.items())),
                tuple(sorted((str(k), v.key()) for k, v in self.dict_refs.items())))

    def dict_value(self, fk, node, keys, vals):
        token = (fk[0], str(fk[1]), node.lineno, node.col_offset)
        ref = self.dict_refs.setdefault(token, DictRef(token))
        ref.seed(keys, vals)
        return V((), (), vjoin(*vals).funcs, None, None, ("dict", ref))

    def flag(self, mod, node, msg):
        if self.recording:
            self.findings.add(Finding((os.path.basename(mod.path), getattr(node, "lineno", 0),
                                       msg)))

    def func_node(self, fk):
        kind, q = fk
        if isinstance(q, int):
            return self.lambdas[q][1]
        return self.mods[kind].funcs[q]

    def add_func(self, fk):
        self.closure.add(fk)

    # -- one function --
    def analyze(self, fk):
        kind, q = fk
        mod = self.mods[kind]
        node = self.func_node(fk)
        env = {}
        args = node.args
        named_args = args.posonlyargs + args.args
        names = [a.arg for a in named_args]
        params = self.params.setdefault(fk, {})
        defaults = list(args.defaults)
        dnames = names[len(names) - len(defaults):] if defaults else []
        fa = Frame(self, mod, fk, env, frozenset(self.ctx_in.get(fk, ())))
        for n, dnode in zip(dnames, defaults):
            params[n] = vjoin(params.get(n), fa.expr(dnode))
        for a, dnode in zip(args.kwonlyargs, args.kw_defaults):
            if dnode is not None:
                params[a.arg] = vjoin(params.get(a.arg), fa.expr(dnode))
        allp = names + [a.arg for a in args.kwonlyargs]
        annotations = {a.arg: a.annotation for a in named_args + args.kwonlyargs}
        if args.vararg:
            allp.append(args.vararg.arg)
            annotations[args.vararg.arg] = args.vararg.annotation
        if args.kwarg:
            allp.append(args.kwarg.arg)
            annotations[args.kwarg.arg] = args.kwarg.annotation
        for n in allp:
            contract = AER_CONTRACTS.get((kind, q, n))
            if contract is not None:
                env[n] = contract_value(contract)
            elif n in params:
                env[n] = params[n]
            elif fk not in self.entries:
                env[n] = V()             # no call site has reached it yet
            else:
                # an entry point's argument: data; in the bot it is request
                # and delivery data (Q), never cell data, which reaches the
                # bot only inside a response body and leaves the decoder as P
                if kind == "bot":
                    env[n] = V({Q})
                elif kind == "api" and is_request_annotation(mod, annotations.get(n)):
                    env[n] = V({R})
                else:
                    env[n] = V({D})
        if isinstance(node, ast.Lambda):
            ret = fa.expr(node.body)
            fa.ret = vjoin(fa.ret, V(ret.ex, ret.im | fa.ctx, ret.funcs, ret.elems, ret.item,
                                     ret.alias))
        else:
            for dec in node.decorator_list:
                fa.expr(dec)
            for _ in range(6):
                before = tuple(sorted((k, v.key()) for k, v in env.items()))
                fa.block(node.body)
                if tuple(sorted((k, v.key()) for k, v in env.items())) == before:
                    break
        self.returns[fk] = fa.ret if fa.ret is not None else V({C})

    def call_func(self, fk, argvals, kwvals, ctx):
        """Join a call site's arguments into the callee's parameters."""
        self.add_func(fk)
        self.called.add(fk)
        node = self.func_node(fk)
        args = node.args
        names = [a.arg for a in args.posonlyargs + args.args]
        params = self.params.setdefault(fk, {})
        if not isinstance(fk[1], int) and "." in fk[1] and names and names[0] in ("self", "cls"):
            # a method of the module's own class: its instance is data
            params[names[0]] = vjoin(params.get(names[0]), V({D}))
            names = names[1:]
        for i, v in enumerate(argvals):
            if i < len(names):
                params[names[i]] = vjoin(params.get(names[i]), v)
            elif args.vararg:
                params[args.vararg.arg] = vjoin(params.get(args.vararg.arg), V((), (), (), None, v))
        for k, v in kwvals.items():
            if k is None:
                for n in names:
                    params[n] = vjoin(params.get(n), element(v))
                continue
            params[k] = vjoin(params.get(k), v)
        self.ctx_in[fk] = frozenset(self.ctx_in.get(fk, frozenset()) | ctx)
        ret = self.returns.get(fk)
        root = AER_ROOTS.get(fk)
        if root is not None and ret is not None:
            inherited = set(self.ctx_in.get(fk, ()))
            for v in params.values():
                inherited |= v.flat()
            current = set(ctx)
            for v in list(argvals) + list(kwvals.values()):
                current |= v.flat()
            intrinsic = set(ret.flat()) - inherited
            return V(root, (current | intrinsic) & {K, O})
        return ret if ret is not None else V()

    # -- module-level scans (literals) --
    def scan_module(self, mod):
        bounds_nodes = set()
        for name in ("CONTRACT_BOUNDS", "DISPLAY_DEFAULTS"):
            if name in mod.consts:
                for n in ast.walk(mod.consts[name]):
                    bounds_nodes.add(id(n))
        scope = []
        for node in mod.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if (mod.kind, node.name) in self.closure:
                    scope.append(node)
            elif isinstance(node, ast.ClassDef):
                if any((mod.kind, node.name + "." + s.name) in self.closure for s in node.body
                       if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))):
                    scope.append(node)
            elif mod.kind != "bot" or self._bot_const(node):
                scope.append(node)
        for top in scope:
            for n in ast.walk(top):
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    if SQL_WORDS.search(n.value) and SQL_BAD.search(n.value):
                        self.flag(mod, n, "SQL literal names a class or mark column (%s)"
                                  % SQL_BAD.search(n.value).group(1))
                if isinstance(n, ast.Call):
                    fn = n.func
                    if isinstance(fn, ast.Attribute) and fn.attr in ("text", "annotate"):
                        # every text call in the seeds' scope (ax, fig, plt)
                        pm = [k for k in n.keywords if k.arg == "parse_math"]
                        if not pm or not (isinstance(pm[0].value, ast.Constant)
                                          and pm[0].value.value is False):
                            self.flag(mod, n, "text call without parse_math=False")

    def _bot_const(self, node):
        if isinstance(node, ast.Assign):
            names = [n.id for t in node.targets for n in ast.walk(t) if isinstance(n, ast.Name)]
            return any(n.startswith(("AER_", "_AER_", "_aer_", "Aer", "BotPage")) for n in names)
        return False


class Frame:
    """The walk of one function body: an environment, the implicit context."""

    def __init__(self, ps, mod, fk, env, ctx):
        self.ps = ps
        self.mod = mod
        self.fk = fk
        self.env = env
        self.ctx = ctx
        self.order_ctx = frozenset()
        self.ret = None
        self.globals = set()

    # -- statements --
    def block(self, stmts):
        for s in stmts:
            self.stmt(s)

    def with_ctx(self, labels, fn):
        old = self.ctx
        self.ctx = frozenset(old | labels)
        try:
            fn()
        finally:
            self.ctx = old

    def stmt(self, s):
        t = type(s)
        if t in (ast.Expr,):
            self.expr(s.value)
        elif t is ast.Assign:
            v = self.expr(s.value)
            for tgt in s.targets:
                self.assign(tgt, v)
        elif t is ast.AnnAssign:
            if s.value is not None:
                self.assign(s.target, self.expr(s.value))
        elif t is ast.AugAssign:
            v = vjoin(self.expr(s.target), self.expr(s.value))
            self.assign(s.target, v)
        elif t is ast.Return:
            v = self.expr(s.value) if s.value is not None else V({C})
            v = V(v.ex, v.im | self.ctx | self.order_ctx, v.funcs, v.elems, v.item, v.alias)
            self.ret = vjoin(self.ret, v) if self.ret is not None else v
        elif t is ast.If:
            tv = self.test(s.test)
            self.with_ctx(tv.flat(), lambda: (self.block(s.body), self.block(s.orelse)))
        elif t is ast.While:
            tv = self.test(s.test)
            self.with_ctx(tv.flat(), lambda: (self.block(s.body), self.block(s.orelse)))
        elif t in (ast.For, ast.AsyncFor):
            it = self.expr(s.iter)
            self.assign(s.target, element(it))
            labels = self.loop_labels(s.iter, it)
            old_order = self.order_ctx
            self.order_ctx = frozenset(old_order | (labels & {O}))
            try:
                self.with_ctx(labels - {O},
                              lambda: (self.block(s.body), self.block(s.orelse)))
            finally:
                self.order_ctx = old_order
        elif t in (ast.With, ast.AsyncWith):
            for item in s.items:
                v = self.expr(item.context_expr)
                if item.optional_vars is not None:
                    self.assign(item.optional_vars, v)
            self.block(s.body)
        elif t is ast.Try or t.__name__ == "TryStar":
            self.block(s.body)
            for h in s.handlers:
                if h.name:
                    self.env[h.name] = V({D})
                self.block(h.body)
            self.block(s.orelse)
            self.block(s.finalbody)
        elif t is ast.Raise:
            if s.exc is not None:
                self.expr(s.exc)
        elif t is ast.Global:
            self.globals.update(s.names)
        elif t in (ast.FunctionDef, ast.AsyncFunctionDef):
            self.ps.flag(self.mod, s, "nested function definition (not followed)")
        elif t is ast.ClassDef:
            # a nested data-only class (a ctypes structure layout): its body is
            # evaluated; a nested class with methods is not followed
            for sub in s.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.ps.flag(self.mod, sub, "method of a nested class (not followed)")
                else:
                    self.stmt(sub)
            self.env[s.name] = V({C}, alias=("builtin", "nested_class"))
        elif t is ast.Assert:
            self.expr(s.test)
        elif t is ast.Delete:
            pass
        elif t in (ast.Pass, ast.Break, ast.Continue, ast.Nonlocal, ast.Import,
                   ast.ImportFrom):
            pass
        elif t is ast.Match:
            sv = self.expr(s.subject)
            for case in s.cases:
                self.with_ctx(sv.flat(), lambda case=case: self.block(case.body))
        else:
            self.ps.flag(self.mod, s, "statement kind %s not handled" % t.__name__)

    def loop_labels(self, node, it):
        """A loop over a named sequence is structural: only its D, K and O
        labels become implicit; any other iterable is implicit whole."""
        inner = node
        while isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and \
                inner.func.id in ("enumerate", "sorted", "reversed", "tuple", "list") and \
                inner.args and not any(k.arg == "key" for k in inner.keywords):
            inner = inner.args[0]
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and \
                inner.func.attr in ("items", "keys", "values") and not inner.args:
            inner = inner.func.value
        labels = it.flat()
        if isinstance(inner, (ast.Name, ast.Attribute, ast.Subscript, ast.Tuple, ast.List)):
            return frozenset(labels & {D, K, O})
        return labels

    def assign(self, tgt, v):
        v = add_im(v, self.order_ctx)
        if isinstance(tgt, ast.Name):
            name = tgt.id
            if name in self.globals:
                key = (self.mod.kind, name)
                self.ps.state_vals[key] = vjoin(self.ps.state_vals.get(key),
                                                V(v.ex_all(), v.im_all() | self.ctx, v.funcs))
                return
            old = self.env.get(name)
            nv = V(v.ex, v.im | self.ctx, v.funcs, v.elems, v.item, v.alias)
            self.env[name] = vjoin(old, nv) if old is not None else nv
        elif isinstance(tgt, (ast.Tuple, ast.List)):
            for i, t in enumerate(tgt.elts):
                if isinstance(t, ast.Starred):
                    self.assign(t.value, V((), (), (), None, element(v)))
                elif v.elems is not None and len(v.elems) == len(tgt.elts):
                    self.assign(t, add_im(v.elems[i], v.im))
                else:
                    self.assign(t, element(v))
        elif isinstance(tgt, ast.Subscript):
            base = tgt.value
            self.expr(tgt.slice)
            cur = self.expr(base)
            incoming = add_im(v, self.ctx)
            dicts = _dict_arms(cur)
            if dicts:
                if isinstance(tgt.slice, ast.Constant) and isinstance(tgt.slice.value, str):
                    _dict_slot_update(cur, tgt.slice.value, incoming)
                else:
                    _dict_dynamic_update(cur, incoming)
            elif isinstance(base, ast.Name) and base.id in self.env:
                self.env[base.id] = vjoin(cur, V((), (), v.funcs, None, incoming))
            elif isinstance(base, ast.Name) and base.id in self.mod.state:
                key = (self.mod.kind, base.id)
                self.ps.state_vals[key] = vjoin(self.ps.state_vals.get(key), V(v.flat() | self.ctx))
            self.cls_mark_slot(tgt.slice, v, tgt)
        elif isinstance(tgt, ast.Attribute):
            self.expr(tgt.value)
            if tgt.attr in ("cls", "mark"):
                self.sink(tgt, "attribute ." + tgt.attr, v, APPEAR)
        elif isinstance(tgt, ast.Starred):
            self.assign(tgt.value, v)

    def cls_mark_slot(self, slice_node, v, node):
        if isinstance(slice_node, ast.Constant) and slice_node.value in ("cls", "mark"):
            self.sink(node, "slot %r" % slice_node.value, v, APPEAR)

    # -- expressions --
    def test(self, node):
        return self.expr(node)

    def expr(self, n):
        if n is None:
            return V({C})
        m = getattr(self, "e_" + type(n).__name__, None)
        if m is None:
            self.ps.flag(self.mod, n, "expression kind %s not handled" % type(n).__name__)
            return V({D})
        return m(n)

    def e_Constant(self, n):
        return V({C})

    def e_JoinedStr(self, n):
        parts = [self.expr(v) for v in n.values]
        return vjoin(V({C}), *parts)

    def e_FormattedValue(self, n):
        v = self.expr(n.value)
        spec = ""
        if n.format_spec is not None:
            spec = "".join(x.value for x in n.format_spec.values if isinstance(x, ast.Constant))
        if spec and spec[-1:] in "dfeEgGx%no" and n.conversion == -1:
            return self.numeric_format(v)
        return v

    def numeric_format(self, v):
        ex = set(v.ex_all())
        if ex & {D, R, Q}:
            ex = (ex - {D, R, Q}) | {F}
        return V(ex, v.im_all())

    def e_Name(self, n):
        name = n.id
        if name in self.env:
            return self.env[name]
        mod = self.mod
        if name in mod.funcs:
            return V({C}, (), {(mod.kind, name)})
        if name in mod.classes:
            return V({C}, (), self.class_funcs(name), alias=("class", name))
        if name in mod.state or name in self.globals:
            return vjoin(V({C}), self.ps.state_vals.get((mod.kind, name)))
        if name in mod.consts:
            return self.const_value(name)
        if name in mod.imports:
            return V({C}, alias=("import", mod.imports[name]))
        return V({C}, alias=("builtin", name))

    def class_funcs(self, cname):
        q = cname + ".__init__"
        return {(self.mod.kind, q)} if q in self.mod.funcs else set()

    def const_value(self, name):
        node = self.mod.consts[name]
        funcs = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id in self.mod.funcs:
                funcs.add((self.mod.kind, sub.id))
            if isinstance(sub, ast.Lambda):
                funcs.add(self.lambda_key(sub))
        return V({C}, (), funcs)

    def lambda_key(self, node):
        key = (self.mod.kind, id(node))
        self.ps.lambdas[id(node)] = (self.mod.kind, node)
        return key

    def e_Lambda(self, n):
        return V({C}, (), {self.lambda_key(n)})

    def e_Attribute(self, n):
        base = self.expr(n.value)
        if base.alias and base.alias[0] in ("import", "builtin"):
            return V(base.ex, base.im, (), alias=(base.alias[0], base.alias[1] + "." + n.attr))
        if base.alias and base.alias[0] == "class":
            q = base.alias[1] + "." + n.attr
            if q in self.mod.funcs:
                return V({C}, (), {(self.mod.kind, q)})
            return V({C})
        if P in base.ex:
            lab = S if n.attr in AER_STRUCTURAL_SLOTS else E
            return V((base.ex - {P}) | {lab}, base.im)
        return V(base.ex, base.im, (), None, None, ("method", n.attr, base, n.value))

    def e_Subscript(self, n):
        base = self.expr(n.value)
        idx = self.expr(n.slice)
        dicts = _dict_arms(base)
        if dicts and isinstance(n.slice, ast.Constant):
            slots = [add_im(slot, arm.im) for arm in dicts
                     for slot in (arm.alias[1].read(n.slice.value),) if slot is not None]
            if slots:
                return vjoin(V(base.ex, base.im), *slots)
        if base.elems is not None and isinstance(n.slice, ast.Constant) and \
                isinstance(n.slice.value, int) and -len(base.elems) <= n.slice.value < len(base.elems):
            return add_im(base.elems[n.slice.value], base.im)
        if isinstance(n.slice, ast.Slice):
            return V(base.ex, base.im | (idx.flat() - {C}), base.funcs, None, base.item)
        el = element(base)
        return V(el.ex | (idx.ex - {C}), el.im | idx.im, el.funcs | base.funcs, el.elems, el.item,
                 el.alias if _dict_arms(el) else None)

    def e_Slice(self, n):
        return vjoin(V({C}), self.expr(n.lower), self.expr(n.upper), self.expr(n.step))

    def e_Tuple(self, n):
        vals = [self.expr(e) for e in n.elts]
        return V((), (), set().union(*[v.funcs for v in vals]) if vals else (), tuple(vals))

    e_List = e_Tuple

    def e_Set(self, n):
        vals = [self.expr(e) for e in n.elts]
        return V((), (), (), None, vjoin(*vals) if vals else V({C}))

    def e_Dict(self, n):
        out = []
        vals = []
        for k, v in zip(n.keys, n.values):
            vv = self.expr(v)
            vals.append(vv)
            if k is not None:
                kv = self.expr(k)
                out.append(kv)
                if isinstance(k, ast.Constant) and k.value in ("cls", "mark"):
                    self.sink(n, "key %r" % k.value, vv, APPEAR)
                if self.mod.kind == "api" and isinstance(k, ast.Constant) and \
                        k.value in ("name", "reason", "invalidated"):
                    self.sink(v, "api display slot %r" % k.value, vv, DISPLAY)
            out.append(vv)
        j = vjoin(*out) if out else V({C})
        if all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in n.keys):
            # One allocation identity is shared by every view of this literal.
            return self.ps.dict_value(
                self.fk, n, tuple(k.value for k in n.keys), tuple(vals))
        return V(j.ex_all(), j.im_all(), j.funcs)

    def e_Starred(self, n):
        return element(self.expr(n.value))

    def e_BinOp(self, n):
        lv, rv = self.expr(n.left), self.expr(n.right)
        if isinstance(n.op, ast.Mod) and isinstance(n.left, ast.Constant) and \
                isinstance(n.left.value, str):
            return self.percent_format(n.left.value, n.right, rv)
        return vjoin(lv, rv)

    def percent_format(self, fmt, rnode, rv):
        specs = re.findall(r"%[-#0 +]*(?:\d+|\*)?(?:\.\d+)?([a-zA-Z%])", fmt)
        specs = [s for s in specs if s != "%"]
        vals = list(rv.elems) if rv.elems is not None else [rv] * len(specs)
        out = [V({C})]
        for spec, v in zip(specs, vals):
            out.append(self.numeric_format(v) if spec in "dioufeEgGxX" else v)
        if len(vals) > len(specs):
            out.extend(vals[len(specs):])
        return vjoin(*out)

    def e_UnaryOp(self, n):
        return self.expr(n.operand)

    def e_BoolOp(self, n):
        return vjoin(*[self.expr(v) for v in n.values])

    def containment_result(self, vals, ordering=True):
        ex = set()
        im = set()
        for v in vals:
            ex |= v.ex_all()
            im |= v.im_all()
        if P in ex:
            ex = (ex - {P}) | {E}
        if ordering and (ex | im) & {E, D}:
            ex |= {K}
        return V(ex, im)

    def e_Compare(self, n):
        vals = [self.expr(n.left)] + [self.expr(c) for c in n.comparators]
        operands = [n.left] + list(n.comparators)
        ordering = any(isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for op in n.ops)
        self.numeric_check(n, operands, vals)
        return self.containment_result(vals, ordering)

    def numeric_check(self, node, operands, vals):
        """A numeric literal compared with E or D data (the place a copied
        threshold sits) must be allowlisted or a CONTRACT_BOUNDS or
        DISPLAY_DEFAULTS read."""
        if not any(v.flat() & {E, D, R, P} for v in vals):
            return
        for o in operands:
            lit = o.operand if isinstance(o, ast.UnaryOp) else o
            if isinstance(lit, ast.Constant) and type(lit.value) in (int, float):
                val = -lit.value if isinstance(o, ast.UnaryOp) else lit.value
                if val not in AER_NUMERIC_ALLOW:
                    self.ps.flag(self.mod, node, "numeric literal %r compared with cell or "
                                 "response data outside CONTRACT_BOUNDS and DISPLAY_DEFAULTS"
                                 % (val,))

    def e_IfExp(self, n):
        """A value chosen by a test carries the test implicitly; one chosen by
        a class-shaped test (K) is itself classified."""
        tv = self.expr(n.test)
        a, b = self.expr(n.body), self.expr(n.orelse)
        j = vjoin(a, b)
        return V(j.ex | (tv.ex & {K}), j.im | tv.flat(), j.funcs, j.elems, j.item, j.alias)

    def e_Await(self, n):
        return self.expr(n.value)

    def e_NamedExpr(self, n):
        v = self.expr(n.value)
        self.assign(n.target, v)
        return v

    def comp(self, n, elts):
        saved = dict(self.env)
        implicit = set()
        for g in n.generators:
            it = self.expr(g.iter)
            self.assign(g.target, element(it))
            implicit |= self.loop_labels(g.iter, it)
            for cond in g.ifs:
                implicit |= self.expr(cond).flat()
        old = self.ctx
        old_order = self.order_ctx
        self.ctx = frozenset(old | (implicit - {O}))
        self.order_ctx = frozenset(old_order | (implicit & {O}))
        try:
            vals = [self.expr(e) for e in elts]
        finally:
            self.ctx = old
            self.order_ctx = old_order
        for k in list(self.env):
            if k not in saved:
                del self.env[k]
        v = vjoin(*vals)
        return V((), (), v.funcs, None,
                 V(v.ex, v.im | implicit, v.funcs, v.elems, v.item, v.alias))

    def e_ListComp(self, n):
        return self.comp(n, [n.elt])

    e_SetComp = e_ListComp
    e_GeneratorExp = e_ListComp

    def e_DictComp(self, n):
        return self.comp(n, [n.key, n.value])

    # -- calls --
    def e_Call(self, n):
        argvals = []
        for a in n.args:
            v = self.expr(a.value if isinstance(a, ast.Starred) else a)
            argvals.append(element(v) if isinstance(a, ast.Starred) else v)
        kwvals = {}
        for k in n.keywords:
            kwvals[k.arg] = self.expr(k.value)
            if k.arg in ("cls", "mark"):
                self.sink(k.value, "keyword %s=" % k.arg, kwvals[k.arg], APPEAR)
        fn = self.expr(n.func)
        # unresolvable targets
        name = self.callable_name(n.func, fn)
        if name in UNRESOLVABLE or (name or "").startswith("importlib") or \
                name in ("getattr", "operator.attrgetter", "operator.methodcaller",
                         "attrgetter", "methodcaller"):
            literal = all(isinstance(a, ast.Constant) for a in n.args[1:]) if name == "getattr" \
                else all(isinstance(a, ast.Constant) for a in n.args)
            if name in UNRESOLVABLE or name.startswith("importlib") or not literal:
                self.ps.flag(self.mod, n, "unresolvable call target (%s)" % name)
                return V({D})
            if name == "getattr":
                return V(argvals[0].ex, argvals[0].im, (), None, None,
                         ("method", n.args[1].value, argvals[0]))
        if name == "functools.partial" or name == "partial":
            if not argvals:
                return V({D})
            return V({C}, (), argvals[0].funcs, None, None, ("partial", tuple(argvals[1:])))
        if fn.alias and fn.alias[0] == "partial":
            argvals = list(fn.alias[1]) + argvals
        if fn.funcs:
            out = []
            for fk in sorted(fn.funcs, key=str):
                out.append(self.ps.call_func(fk, argvals, kwvals,
                                             self.ctx | self.order_ctx))
            # a call of a module function: methods of the module's classes
            # receive their instance as data
            return vjoin(*out)
        if fn.alias and fn.alias[0] == "method":
            meth, recv = fn.alias[1], fn.alias[2]
            # methods of the module's own classes are followed
            if meth in self.mod.methods and not (recv.alias and recv.alias[0] in
                                                 ("import", "builtin")):
                out = [self.ps.call_func((self.mod.kind, q), argvals, kwvals,
                                         self.ctx | self.order_ctx)
                       for q in self.mod.methods[meth]]
                return vjoin(*out)
            if meth in _MUTATORS:
                # `items.append(x)`, or `add = items.append` then `add(x)`
                return self.mutate(meth, recv, fn.alias[3], n, argvals, kwvals)
            return self.third_party("." + meth, n, argvals, kwvals, recv)
        if name is None:
            self.ps.flag(self.mod, n, "unresolvable call target (a callable value of no "
                         "known origin)")
            return V({D})
        return self.third_party(name, n, argvals, kwvals, None)

    def callable_name(self, node, fv):
        if fv.alias and fv.alias[0] in ("import", "builtin"):
            name = fv.alias[1]
            if fv.alias[0] == "import" and name.startswith(("fastapi.", "fastapi.responses.",
                                                            "sqlalchemy.ext.asyncio.")):
                name = name.rsplit(".", 1)[1]
            return name
        if fv.alias and fv.alias[0] == "class":
            return fv.alias[1]
        if fv.alias and fv.alias[0] == "method":
            return "." + fv.alias[1]
        if isinstance(node, ast.Name) and node.id in self.mod.consts:
            return node.id
        return None

    def literal_mutation_slots(self, meth, node, argvals, kwvals):
        """The exact slots changed by a supported literal-key dictionary call.
        None means that the mutation must conservatively forget key identity."""
        if meth == "update":
            slots = []
            for value in argvals:
                literal = _dict_literal_slots(value)
                if literal is None:
                    return None
                slots.extend((key, slot, False)
                             for key, slot in literal)
            for key, value in kwvals.items():
                if key is None:
                    literal = _dict_literal_slots(value)
                    if literal is None:
                        return None
                    slots.extend((slot_key, slot, False)
                                 for slot_key, slot in literal)
                else:
                    slots.append((key, value, False))
            return slots
        if meth in ("setdefault", "__setitem__") and node.args and \
                isinstance(node.args[0], ast.Constant) and \
                isinstance(node.args[0].value, str):
            if meth == "__setitem__" and len(argvals) < 2:
                return None
            value = argvals[1] if len(argvals) > 1 else V({C})
            return [(node.args[0].value, value, meth == "setdefault")]
        return None

    def setdefault_result(self, recv, node, argvals):
        """The existing slot, inserted default, or conservative dynamic element."""
        default = argvals[1] if len(argvals) > 1 else V({C})
        dicts = _dict_arms(recv)
        if node.args and isinstance(node.args[0], ast.Constant) and \
                isinstance(node.args[0].value, str) and dicts:
            key = node.args[0].value
            selected = []
            for arm in dicts:
                ref = arm.alias[1]
                if ref.keys is None:
                    value = vjoin(ref.element(), default)
                else:
                    value = ref.read(key)
                    if value is None:
                        value = default
                    elif key not in ref.must_keys:
                        value = vjoin(value, default)
                selected.append(add_im(value, arm.im))
            return vjoin(V(recv.ex, recv.im), *selected)
        key_value = argvals[0] if argvals else V({C})
        value = vjoin(element(recv), default)
        return V(value.ex | (key_value.ex - {C}), value.im | key_value.im,
                 value.funcs, value.elems, value.item, value.alias)

    def mutate(self, meth, recv, recv_node, node, argvals, kwvals):
        v = vjoin(*(list(argvals) + list(kwvals.values()))) if (argvals or kwvals) else V({C})
        v = add_im(v, self.order_ctx)
        slots = self.literal_mutation_slots(meth, node, argvals, kwvals)
        result = self.setdefault_result(recv, node, argvals) \
            if meth == "setdefault" else V({C})
        dicts = _dict_arms(recv)
        if dicts:
            if slots is not None:
                for key, slot, only_if_missing in slots:
                    _dict_slot_update(
                        recv, key, add_im(slot, self.ctx | self.order_ctx), only_if_missing)
            else:
                _dict_dynamic_update(recv, add_im(v, self.ctx))
            return result
        tgt = recv_node
        if isinstance(tgt, ast.Name):
            name = tgt.id
            if name in self.env:
                cur = self.env[name]
                self.env[name] = vjoin(cur, V((), (), v.funcs, None,
                                              V(v.ex, v.im | self.ctx, v.funcs, v.elems, v.item,
                                                v.alias)))
            elif name in self.mod.state or name in self.mod.consts:
                key = (self.mod.kind, name)
                self.ps.state_vals[key] = vjoin(self.ps.state_vals.get(key),
                                                V(v.flat() | self.ctx))
        else:
            self.expr(tgt)
        return result

    def lookup_class(self, name, param):
        for key in ((name, param), (name, "*")):
            if key in AER_PARAM_CLASS:
                return AER_PARAM_CLASS[key]
        if name in self.mod.classes:
            # the module's own data class or exception (no __init__ of its
            # own): its constructor stores its arguments and draws nothing
            return VALUE
        parts = name.split(".")
        for i in range(len(parts) - 1, 0, -1):
            key = (".".join(parts[:i]) + ".*", "*")
            if key in AER_PARAM_CLASS:
                return AER_PARAM_CLASS[key]
        return APPEAR

    def third_party(self, name, node, argvals, kwvals, recv):
        # The result carries every argument's labels (an object built from a
        # checked argument still holds it); each argument was checked here.
        result = [recv] if recv is not None else []
        transported = []
        for i, v in enumerate(argvals):
            klass = self.lookup_class(name, "#%d" % i)
            self.sink(node, "%s #%d" % (name, i), v, klass)
            (transported if klass == TRANSPORT else result).append(v)
        for k, v in kwvals.items():
            klass = self.lookup_class(name, k if k is not None else "*")
            self.sink(node, "%s %s=" % (name, k), v, klass)
            (transported if klass == TRANSPORT else result).append(v)
        if name in _SET_ORDERED_CALLS:
            operands = [a.value if isinstance(a, ast.Starred) else a for a in node.args]
            if recv is not None and isinstance(node.func, ast.Attribute):
                operands.insert(0, node.func.value)
            operands.extend(k.value for k in node.keywords)
            self.numeric_check(node, operands, result + transported)
        if name in _SET_CONTAINMENT_CALLS:
            return self.containment_result(result + transported)
        # a function handed to a third-party callable (a sort key, a callback)
        # is followed, called with an element of the first argument
        first = [element(argvals[0])] if argvals else []
        called = {}
        for v in list(argvals) + list(kwvals.values()):
            for fk in v.funcs:
                called[fk] = self.ps.call_func(fk, first, {}, self.ctx | self.order_ctx)
        out = vjoin(V({C}), *result) if result else V({C})
        if name in ("sorted", "min", "max", ".sort") and "key" in kwvals:
            keyret = vjoin(*[called.get(fk, V()) for fk in kwvals["key"].funcs])
            if keyret.flat() & {E, D, P, Q}:
                out = V(out.ex | {O}, out.im, out.funcs, out.elems, out.item)
        if name in ("len",):
            return V({S})
        if name in ("enumerate",) and argvals:
            el = element(argvals[0])
            return V((), (), (), None, V((), (), (), (V({S}), el)))
        if name in ("zip",) and argvals:
            return V((), (), (), None, V((), (), (), tuple(element(a) for a in argvals)))
        if name in ("tuple", "list", "sorted", "reversed", "frozenset", "set") and argvals and \
                "key" not in kwvals:
            a = argvals[0]
            return V(a.ex if a.item is None and a.elems is None else (), a.im, a.funcs,
                     None, element(a) if (a.item is not None or a.elems is not None) else None)
        ex = set(out.ex)
        im = set(out.im)
        for v in result:
            ex |= v.ex_all()
            im |= v.im_all()
        for v in transported:
            ex |= v.ex
            im |= v.im
        if P in ex:
            ex = (ex - {P}) | {E}
        return V(ex, im, out.funcs)

    def sink(self, node, what, v, klass):
        if klass in (VALUE, TRANSPORT, DATA):
            return
        labels_ex = set(v.ex_all())
        labels_im = set(v.im_all()) | set(self.ctx)
        if klass == DISPLAY:
            labels_im |= set(self.order_ctx)
            implicit_bad = labels_im & {K, O}
            bad = (labels_ex - DISPLAY_OK) | implicit_bad
        else:
            appearance_im = labels_im | set(self.order_ctx)
            bad = (labels_ex - APPEARANCE_OK) | (appearance_im - APPEARANCE_OK - {Q})
        if bad:
            self.ps.flag(self.mod, node, "%s sink %s reads %s" % (klass, what,
                                                                   "".join(sorted(bad))))


# ── Running the pass ───────────────────────────────────────────────────────

def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _bot_seed(q):
    return q.startswith("_aer_")


def seed_modules(api=None, bot=None, worker=None):
    return [Module("api", api if api is not None else _read(API), API, lambda q: True),
            Module("bot", bot if bot is not None else _read(BOT), BOT, _bot_seed),
            Module("worker", worker if worker is not None else _read(WORKER), WORKER,
                   lambda q: True)]


def run_pass(modules):
    return Pass(modules).run()


def _fmt(findings):
    # one line, so a failing run's first error line names every finding
    return " | ".join(str(f) for f in findings)


def test_the_report_seeds_copy_no_class_or_mark_and_draw_only_chrome():
    """The privacy pass over the real seeds: no finding."""
    findings = run_pass(seed_modules())
    assert findings == [], "privacy pass findings: " + _fmt(findings)


def test_the_closure_reaches_every_seed_and_its_helpers():
    ps = Pass(seed_modules())
    ps.run()
    names = {q for _k, q in ps.closure if isinstance(q, str)}
    for want in ("_aer_plan", "_aer_render", "_aer_fallback", "_aer_message", "_aer_word",
                 "render", "serve", "_aer_enc", "_text", "flag_list"):
        assert want in names, want
    assert ("worker", "render") in ps.closure


# ── Fixtures: the permitted shapes are green, the refused ones red ─────────

_WORKER_FIXTURE = '''
FILL = "#3a3c42"
SIZES = {"cell": 9, "title": 13}


def render(plan):
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(14.0, 0.6 + len(plan) * 0.22), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    for i, (kind, text) in enumerate(plan):
        ax.text(0.01, len(plan) - i, text, ha="left", va="center", color=FILL,
                fontsize=SIZES[kind], parse_math=False)
    return fig
'''

_BOT_PERMITTED = '''
AerItem = collections.namedtuple("AerItem", ("kind", "fields", "parts", "text"))


def _aer_decode_response(body, phase="1a"):
    return BotPage(body)


def _aer_txt(value):
    if isinstance(value, float):
        return "%.3f" % value
    return value


def _aer_plan(page):
    items = []
    items.append(AerItem("title", (), (), "EVIDENCE page %d of %d" % (page.page, page.pages)))
    for cell in page.cells:
        rank = cell[3]
        items.append(AerItem("cell", (), (_aer_txt(rank),),
                             "rank " + _aer_txt(rank) + " " + _aer_enc_text(cell[0])))
        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))
    return tuple(items)


def _aer_enc_text(value):
    return "".join(ch for ch in str(value))


async def _aer_go(body):
    page = _aer_decode_response(body)
    plan = _aer_plan(page)
    return "\\n".join(item.text for item in plan)
'''

_API_PERMITTED = '''
def _aer_enc(value):
    return str(value)


def _text(value):
    return _aer_enc(value)


def subject(r):
    return {"name": _text(r["display_name"]) if r else None, "n": r["n"]}
'''


def _fixture(api="", bot="", worker=""):
    return run_pass([Module("api", api, "fixture_api.py", lambda q: True),
                     Module("bot", bot, "fixture_bot.py", _bot_seed),
                     Module("worker", worker, "fixture_worker.py", lambda q: True)])


def test_the_permitted_fixture_is_green():
    """Numeric formatting, rank display as text, encoded text, a word chosen by
    a display slot's truthiness, fixed chrome at every sink, page arithmetic."""
    assert _fixture(_API_PERMITTED, _BOT_PERMITTED, _WORKER_FIXTURE) == []


@pytest.mark.parametrize("label,api,bot,worker,needle", [
    ("rank to fill", "", "", _WORKER_FIXTURE.replace(
        "color=FILL", "color=(float(text[-4:]), 0, 0, 1)"), "appearance sink .text color="),
    ("raw display name", _API_PERMITTED.replace('_text(r["display_name"])',
                                                'str(r["display_name"])'), "", "",
     "api display slot 'name'"),
    ("class word by threshold", "", _BOT_PERMITTED.replace(
        '"ranked" if cell[2] else "casual"', '"HOT" if cell[3] > 0.83 else "COLD"'), "",
     "display sink AerItem #3"),
    ("class word by statement branch", "", _BOT_PERMITTED.replace(
        '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))',
        '        word = "COLD"\n'
        '        if cell[3] > 0.5:\n'
        '            word = "HOT"\n'
        '        items.append(AerItem("cell", (), (), word))'), "",
     "display sink AerItem #3 reads K"),
    ("value order through helper return", "", _BOT_PERMITTED.replace(
        "def _aer_plan(page):",
        "def _order_value(cell):\n"
        "    return cell[3]\n\n\n"
        "def _aer_plan(page):").replace(
        "    for cell in page.cells:",
        '    order_word = "COLD"\n'
        '    for _unused in sorted(page.cells, key=_order_value):\n'
        '        order_word = "HOT"\n'
        '    items.append(AerItem("cell", (), (), order_word))\n'
        "    for cell in page.cells:"), "",
     "display sink AerItem #3 reads O"),
    ("unresolvable getattr", "", _BOT_PERMITTED.replace(
        "plan = _aer_plan(page)", "plan = getattr(page, body['k'])()"), "",
     "unresolvable call target (getattr)"),
    ("no parse_math", "", "", _WORKER_FIXTURE.replace(", parse_math=False", ""),
     "text call without parse_math=False"),
    ("cls slot in 1a", "", _BOT_PERMITTED.replace(
        'items.append(AerItem("cell", (), (), "ranked"',
        'items.append(dict(cls=rank)) or items.append(AerItem("cell", (), (), "ranked"'), "",
     "keyword cls="),
])
def test_each_refused_shape_is_a_finding(label, api, bot, worker, needle):
    """Negative controls of the fixture: each one refused shape, one finding."""
    findings = _fixture(api or _API_PERMITTED, bot or _BOT_PERMITTED, worker or _WORKER_FIXTURE)
    assert any(needle in str(f) for f in findings), (label, _fmt(findings))


@pytest.mark.parametrize("label,api,bot,needle", [
    ("explicit E under rank", "", _BOT_PERMITTED.replace(
        '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))',
        '        shown = _aer_enc_text(cell[0])\n'
        '        if cell[3] > 0.5:\n'
        '            shown = _aer_enc_text(cell[1])\n'
        '        items.append(AerItem("cell", (), (), shown))'), "reads K"),
    ("explicit F under rank", _API_PERMITTED + '''


def formatted(r):
    shown = "%d" % r["left"]
    if r["rank"] > 0.5:
        shown = "%d" % r["right"]
    return {"name": shown}
''', "", "reads K"),
    ("explicit P under rank", "", _BOT_PERMITTED.replace(
        '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))',
        '        shown = page\n'
        '        if page.cells[0][3] > 0.5:\n'
        '            shown = page\n'
        '        items.append(AerItem("cell", (), (), shown))'), "reads K"),
    ("explicit E under value order", "", _BOT_PERMITTED.replace(
        "def _aer_plan(page):",
        "def _order_value(cell):\n"
        "    return cell[3]\n\n\n"
        "def _aer_plan(page):").replace(
        "    for cell in page.cells:",
        '    shown = _aer_enc_text(page.cells[0][0])\n'
        '    for ordered in sorted(page.cells, key=_order_value):\n'
        '        shown = _aer_enc_text(ordered[0])\n'
        '    items.append(AerItem("cell", (), (), shown))\n'
        "    for cell in page.cells:"), "reads O"),
])
def test_display_rejects_implicit_rank_or_order_with_explicit_display_root(
        label, api, bot, needle):
    """Explicit display roots do not hide rank or value-order selection."""
    findings = _fixture(api or _API_PERMITTED, bot or _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and needle in str(findings[0]), (label, _fmt(findings))


_API_ROOT_RANK = _API_PERMITTED + '''


def direct_rank(r):
    return {"name": _aer_enc(r["left"] if r["rank"] > 0.5 else r["right"])}
'''

_API_ROOT_ORDER = _API_PERMITTED + '''


def _order_value(row):
    return row["rank"]


def _ordered_value(rows):
    for row in sorted(rows, key=_order_value):
        return row["name"]
    return ""


def direct_order(r):
    return {"name": _aer_enc(_ordered_value(r["rows"]))}
'''

_API_ROOT_EXPLICIT_RANK = _API_PERMITTED + '''


def direct_explicit_rank(r):
    return {"name": _aer_enc(r["rank"] > 0.5)}
'''

_API_ROOT_INDEXED_ORDER = _API_PERMITTED + '''


def _order_value(row):
    return row["rank"]


def direct_indexed_order(r):
    return {"name": _aer_enc(sorted(r["rows"], key=_order_value)[0]["name"])}
'''

_BOT_ROOT_RANK = _BOT_PERMITTED.replace(
    '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))',
    '        items.append(AerItem("cell", (), (),\n'
    '                             _aer_enc_text(cell[0] if cell[3] > 0.5 else cell[1])))')

_ORDER_HELPER = '''def _order_value(cell):
    return cell[3]


def _ordered_value(page):
    for cell in sorted(page.cells, key=_order_value):
        return cell[0]
    return ""


'''

_BOT_ROOT_ORDER = _BOT_PERMITTED.replace(
    "def _aer_plan(page):", _ORDER_HELPER + "def _aer_plan(page):").replace(
    '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))',
    '        items.append(AerItem("cell", (), (), _aer_enc_text(_ordered_value(page))))')

_DIRECT_ORDER_HELPER = '''def _order_value(cell):
    return cell[3]


'''

_BOT_ROOT_EXPLICIT_RANK = _BOT_PERMITTED.replace(
    '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))',
    '        items.append(AerItem("cell", (), (), _aer_enc_text(cell[3] > 0.5)))')

_BOT_ROOT_INDEXED_ORDER = _BOT_PERMITTED.replace(
    "def _aer_plan(page):", _DIRECT_ORDER_HELPER + "def _aer_plan(page):").replace(
    '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))',
    '        items.append(AerItem("cell", (), (),\n'
    '                             _aer_enc_text(sorted(page.cells, key=_order_value)[0][0])))')

_BOT_DECODER_RANK = _BOT_PERMITTED.replace(
    '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))',
    '        again = _aer_decode_response(\n'
    '            page.left if page.cells[0][3] > 0.5 else page.right)\n'
    '        items.append(AerItem("cell", (), (), again))')

_BOT_DECODER_ORDER = _BOT_PERMITTED.replace(
    "def _aer_plan(page):", _ORDER_HELPER + "def _aer_plan(page):").replace(
    '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))',
    '        again = _aer_decode_response(_ordered_value(page))\n'
    '        items.append(AerItem("cell", (), (), again))')

_BOT_DECODER_EXPLICIT_RANK = _BOT_PERMITTED.replace(
    '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))',
    '        again = _aer_decode_response(page.cells[0][3] > 0.5)\n'
    '        items.append(AerItem("cell", (), (), again))')

_BOT_DECODER_INDEXED_ORDER = _BOT_PERMITTED.replace(
    "def _aer_plan(page):", _DIRECT_ORDER_HELPER + "def _aer_plan(page):").replace(
    '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))',
    '        again = _aer_decode_response(sorted(page.cells, key=_order_value)[0][0])\n'
    '        items.append(AerItem("cell", (), (), again))')


@pytest.mark.parametrize("label,api,bot,needle", [
    ("api encoder direct rank", _API_ROOT_RANK, "", "reads K"),
    ("api encoder direct order", _API_ROOT_ORDER, "", "reads O"),
    ("bot encoder direct rank", "", _BOT_ROOT_RANK, "reads K"),
    ("bot encoder direct order", "", _BOT_ROOT_ORDER, "reads O"),
    ("decoder direct rank", "", _BOT_DECODER_RANK, "reads K"),
    ("decoder direct order", "", _BOT_DECODER_ORDER, "reads O"),
    ("api encoder explicit rank", _API_ROOT_EXPLICIT_RANK, "", "reads K"),
    ("api encoder indexed order", _API_ROOT_INDEXED_ORDER, "", "reads O"),
    ("bot encoder explicit rank", "", _BOT_ROOT_EXPLICIT_RANK, "reads K"),
    ("bot encoder indexed order", "", _BOT_ROOT_INDEXED_ORDER, "reads O"),
    ("decoder explicit rank", "", _BOT_DECODER_EXPLICIT_RANK, "reads K"),
    ("decoder indexed order", "", _BOT_DECODER_INDEXED_ORDER, "reads O"),
])
def test_declared_roots_preserve_direct_rank_and_order_selection(
        label, api, bot, needle):
    findings = _fixture(api or _API_PERMITTED, bot or _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and needle in str(findings[0]), (label, _fmt(findings))


_CASUAL_ITEM = '        items.append(AerItem("cell", (), (), "ranked" if cell[2] else "casual"))'


def _dict_fixture(statement, helper=""):
    source = _BOT_PERMITTED.replace(
        "def _aer_plan(page):", helper + "def _aer_plan(page):")
    return source.replace(_CASUAL_ITEM, statement)


_DICT_HELPER = '''def _box(cell):
    return {"rank": cell[3]}


'''

_DICT_NEGATIVES = [
    ("helper return rank", _dict_fixture(
        '        box = _box(cell)\n'
        '        word = "COLD"\n'
        '        if box["rank"] > 0.5:\n'
        '            word = "HOT"\n'
        '        items.append(AerItem("cell", (), (), word))', _DICT_HELPER), "reads K"),
    ("helper return keyed order", _dict_fixture(
        '        word = "COLD"\n'
        '        for _unused in sorted(page.cells, key=_box_order):\n'
        '            word = "HOT"\n'
        '        items.append(AerItem("cell", (), (), word))',
        _DICT_HELPER + '''def _box_order(cell):
    return _box(cell)["rank"]


'''), "reads O"),
    ("lambda return", _dict_fixture(
        '        box = (lambda value: {"rank": value[3]})(cell)\n'
        '        word = "COLD"\n'
        '        if box["rank"] > 0.5:\n'
        '            word = "HOT"\n'
        '        items.append(AerItem("cell", (), (), word))'), "reads K"),
    ("conditional return", _dict_fixture(
        '        box = ({"rank": cell[3], "x": cell[0]} if cell[2]\n'
        '               else {"rank": cell[3], "x": cell[1]})\n'
        '        word = "COLD"\n'
        '        if box["rank"] > 0.5:\n'
        '            word = "HOT"\n'
        '        items.append(AerItem("cell", (), (), word))'), "reads K"),
    ("unjoinable conditional aliases", _dict_fixture(
        '        box = ({"rank": cell[3], "x": cell[0]} if cell[2]\n'
        '               else {"x": cell[1], "rank": cell[3]})\n'
        '        word = "COLD"\n'
        '        if box["rank"] > 0.5:\n'
        '            word = "HOT"\n'
        '        items.append(AerItem("cell", (), (), word))'), "reads K"),
    ("comprehension return", _dict_fixture(
        '        boxes = [{"rank": value[3]} for value in page.cells]\n'
        '        word = "COLD"\n'
        '        if boxes[0]["rank"] > 0.5:\n'
        '            word = "HOT"\n'
        '        items.append(AerItem("cell", (), (), word))'), "reads K"),
    ("global return", _dict_fixture(
        '        _store_box(cell)\n'
        '        word = "COLD"\n'
        '        if BOX["rank"] > 0.5:\n'
        '            word = "HOT"\n'
        '        items.append(AerItem("cell", (), (), word))', '''BOX = {}


def _store_box(cell):
    global BOX
    BOX = {"rank": cell[3]}


'''), "reads K"),
    ("appended return", _dict_fixture(
        '        boxes = []\n'
        '        boxes.append({"rank": cell[3]})\n'
        '        word = "COLD"\n'
        '        if boxes[0]["rank"] > 0.5:\n'
        '            word = "HOT"\n'
        '        items.append(AerItem("cell", (), (), word))'), "reads K"),
]


@pytest.mark.parametrize("label,bot,needle", _DICT_NEGATIVES,
                         ids=[row[0] for row in _DICT_NEGATIVES])
def test_constant_key_dict_labels_survive_structural_boundaries(label, bot, needle):
    findings = _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE)
    assert len(findings) == 1 and needle in str(findings[0]), (label, _fmt(findings))


def test_exact_constant_key_read_does_not_smear_a_rank_sibling():
    bot = _dict_fixture(
        '        box = _shown_box(cell)\n'
        '        items.append(AerItem("cell", (), (), box["shown"]))', '''def _shown_box(cell):
    return {"shown": _aer_enc_text(cell[0]), "rank": cell[3]}


''')
    assert _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE) == []


_OPTIONAL_BOX_HELPER = '''def _optional_box(cell):
    if cell[2]:
        return {"rank": cell[3], "shown": _aer_enc_text(cell[0])}
    return None


'''

_SCALAR_BOX_HELPER = _OPTIONAL_BOX_HELPER.replace("return None", 'return "EMPTY"')


_EXPLICIT_OPTIONAL_BOX_HELPER = '''def _explicit_optional_box(cell):
    if cell[2]:
        return {"rank": cell[3], "shown": _aer_enc_text(cell[0])}
    else:
        return None


'''

_EXPLICIT_SCALAR_BOX_HELPER = _EXPLICIT_OPTIONAL_BOX_HELPER.replace(
    "return None", 'return "EMPTY"')

_INCOMPATIBLE_SCALAR_BOX_HELPER = '''def _incompatible_scalar_box(cell):
    if cell[2]:
        return {"rank": cell[3], "shown": _aer_enc_text(cell[0])}
    elif cell[1]:
        return {"shown": _aer_enc_text(cell[1]), "rank": cell[3]}
    else:
        return "EMPTY"


'''


def _mixed_box_use(box_expr, sink):
    return (
        '        box = %s\n' % box_expr
        + ('        word = "COLD"\n'
           '        if isinstance(box, dict) and box["rank"] > 0.5:\n'
           '            word = "HOT"\n'
           '        items.append(AerItem("cell", (), (), word))'
           if sink == "rank" else
           '        items.append(AerItem("cell", (), (), box["shown"]))'))


_MIXED_JOIN_CASES = [
    ("helper dict or None", "_optional_box(cell)", _OPTIONAL_BOX_HELPER),
    ("helper dict or scalar", "_optional_box(cell)", _SCALAR_BOX_HELPER),
    ("conditional dict or None",
     '({"rank": cell[3], "shown": _aer_enc_text(cell[0])} if cell[2] else None)', ""),
    ("conditional dict or scalar",
     '({"rank": cell[3], "shown": _aer_enc_text(cell[0])} if cell[2] else "EMPTY")', ""),
]


@pytest.mark.parametrize("label,box_expr,helper", _MIXED_JOIN_CASES,
                         ids=[row[0] for row in _MIXED_JOIN_CASES])
def test_constant_key_alias_survives_mixed_optional_and_union_joins(
        label, box_expr, helper):
    bot = _dict_fixture(_mixed_box_use(box_expr, "rank"), helper)
    findings = _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), (label, _fmt(findings))
    bot = _dict_fixture(_mixed_box_use(box_expr, "shown"), helper)
    assert _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE) == [], label


@pytest.mark.parametrize("label,box_expr,helper", [
    ("explicit-else dict or None", "_explicit_optional_box(cell)",
     _EXPLICIT_OPTIONAL_BOX_HELPER),
    ("explicit-else dict or scalar", "_explicit_optional_box(cell)",
     _EXPLICIT_SCALAR_BOX_HELPER),
    ("incompatible dictionaries plus scalar", "_incompatible_scalar_box(cell)",
     _INCOMPATIBLE_SCALAR_BOX_HELPER),
], ids=["explicit-else dict or None", "explicit-else dict or scalar",
        "incompatible dictionaries plus scalar"])
def test_unresolved_mixed_joins_keep_nested_labels_from_every_dict_arm(
        label, box_expr, helper):
    bot = _dict_fixture(_mixed_box_use(box_expr, "rank"), helper)
    findings = _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), (label, _fmt(findings))
    bot = _dict_fixture(_mixed_box_use(box_expr, "shown"), helper)
    assert _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE) == [], label


def test_compatible_joined_dict_siblings_do_not_smear_exact_key_reads():
    bot = _dict_fixture(_mixed_box_use(
        '({"rank": cell[3], "shown": _aer_enc_text(cell[0])} if cell[2] '
        'else {"rank": cell[3], "shown": _aer_enc_text(cell[1])})', "shown"))
    assert _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE) == []


def test_dynamic_mapping_join_keeps_nested_exact_key_precision():
    bot = _dict_fixture(
        '        boxes = {}\n'
        '        boxes[cell[1]] = {"shown": _aer_enc_text(cell[0]), "rank": cell[3]}\n'
        '        items.append(AerItem("cell", (), (), boxes[cell[1]]["shown"]))')
    assert _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE) == []


_REQUEST_AGGREGATE_API = '''from fastapi import Request


def _order_value(row):
    return row["rank"]


def evidence_report(request: Request, row, rows):
%s    if request.path_params["mode"]:
        box = {"word": %s}
    else:
        box = None
    return {"name": %s}
'''


@pytest.mark.parametrize("label,setup,nested,needle", [
    ("nested D", "", 'row["name"]', "D"),
    ("nested K", "", '"HOT" if row["rank"] > 0.5 else "COLD"', "K"),
    ("nested O", "    ordered = sorted(rows, key=_order_value)\n", "ordered", "DO"),
], ids=["nested D", "nested K", "nested O"])
@pytest.mark.parametrize("sink", ["box", "str(box)"], ids=["direct DISPLAY", "VALUE str"])
def test_request_controlled_dictionary_alternatives_reach_aggregate_sinks(
        label, setup, nested, needle, sink):
    api = _REQUEST_AGGREGATE_API % (setup, nested, sink)
    findings = _fixture(api, _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads %s" % needle in str(findings[0]), (
        label, sink, _fmt(findings))


def test_request_ifexp_dictionary_or_none_keeps_its_single_alias_coverage():
    api = '''from fastapi import Request


def evidence_report(request: Request, row):
    box = ({"word": "HOT" if row["rank"] > 0.5 else "COLD"}
           if request.path_params["mode"] else None)
    return {"name": str(box)}
'''
    findings = _fixture(api, _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), _fmt(findings)


@pytest.mark.parametrize("kind,sibling", [
    ("E", '_aer_enc(row["name"])'),
    ("F", '"%.2f" % row["rank"]'),
    ("constant", '("EMPTY",)'),
], ids=["E", "F", "constant"])
@pytest.mark.parametrize("nested,needle", [
    ('row["name"]', "D"),
    ('"HOT" if row["rank"] > 0.5 else "COLD"', "K"),
    ('sorted(rows, key=_order_value)', "DO"),
], ids=["D", "K", "O"])
@pytest.mark.parametrize("sink", ["box", "str(box)"], ids=["direct", "str"])
def test_m14_request_mixed_arms_keep_nested_labels(kind, sibling, nested, needle, sink):
    api = (_REQUEST_AGGREGATE_API % ("", nested, sink)).replace(
        "        box = None", "        box = " + sibling)
    api += '\n\ndef _aer_enc(value):\n    return str(value)\n'
    findings = _fixture(api, _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads %s" % needle in str(findings[0]), (
        kind, sink, _fmt(findings))


@pytest.mark.parametrize("kind", [C, E, F, P])
@pytest.mark.parametrize("aliased", [False, True], ids=["plain", "alias"])
@pytest.mark.parametrize("label", [D, K, O])
@pytest.mark.parametrize("sink", ["box", "str(box)"], ids=["direct", "str"])
def test_m14_every_sibling_kind_keeps_the_dictionary_bound(kind, aliased, label, sink):
    mod = Module("api", "", "fixture.py", lambda q: True)
    ps = Pass([mod])
    ps.recording = True
    # A constant tuple exercises a non-scalar constant arm; both views must
    # preserve the dictionary even when no common alias can represent them.
    sibling = V({kind}, elems=(V({C}),) if kind == C else None,
                alias=("import", "constant") if aliased else None)
    nested = V({D}) if label == D else V({C}, {label})
    frame = Frame(ps, mod, ("api", "probe"),
                  {"request": V({R}), "sibling": sibling, "nested": nested}, frozenset())
    branch = ast.parse('({"word": nested, "safe": "SAFE"} if request else sibling)',
                       mode="eval").body
    frame.env["box"] = frame.expr(branch)
    value = frame.expr(ast.parse(sink, mode="eval").body)
    frame.sink(branch, "mixed arm", value, DISPLAY)
    assert len(ps.findings) == 1 and label in str(next(iter(ps.findings))), _fmt(ps.findings)
    assert label in frame.env["box"].flat()
    # The exact safe slot stays local to each retained dictionary arm.
    safe = frame.expr(ast.parse('box["safe"]', mode="eval").body)
    assert not safe.flat() & {D, K, O}


@pytest.mark.parametrize("sink", ["box", "str(box)"])
def test_m14_report_ifexp_with_encoded_sibling_refuses_classified_word(sink):
    api = '''from fastapi import Request


def _aer_enc(value):
    return str(value)


def evidence_report(request: Request, row):
    box = ({"word": "HOT" if row["rank"] > 0.5 else "COLD"}
           if request.path_params["mode"] else _aer_enc(row["name"]))
    return {"name": %s}
''' % sink
    findings = _fixture(api, _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), _fmt(findings)


def test_m14_unrepresented_dictionary_arm_folds_all_its_labels(monkeypatch):
    ref = DictRef(("fixture", "unrepresented"))
    ref.seed(("word",), (V({D}, {K, O}),))
    dictionary = V(alias=("dict", ref))
    # Exercise the defensive fallback independently of structural admission.
    monkeypatch.setitem(vjoin.__globals__, "_dict_alternatives", lambda values: None)
    joined = vjoin(dictionary, V({E}))
    assert D in joined.ex_all() and {K, O} <= joined.im_all()


def test_m14_retained_sequence_parts_do_not_smear_structural_positions():
    row = V(elems=(V({S}), V({E})))
    joined = vjoin(V(item=row), V(item=row))
    assert joined.ex == frozenset() and joined.im == frozenset()
    first, second = element(joined).elems
    assert first.flat() == {S} and second.flat() == {E}


@pytest.mark.parametrize("selection", ["box[key]", 'box["safe"]',
                                       'box.setdefault("safe", "DEFAULT")'])
@pytest.mark.parametrize("label", [D, K, O])
def test_m14_selection_keeps_labels_folded_from_a_non_dictionary_arm(selection, label):
    mod = Module("api", "", "fixture.py", lambda q: True)
    ps = Pass([mod])
    frame = Frame(ps, mod, ("api", "probe"), {"key": V({C})}, frozenset())
    clean = frame.expr(ast.parse('{"safe": "SAFE"}', mode="eval").body)
    sibling = V(item=V({label}))
    frame.env["box"] = vjoin(clean, sibling)
    selected = frame.expr(ast.parse(selection, mode="eval").body)
    assert label in selected.flat()


def test_m14_exact_read_keeps_the_outer_conditional_selection():
    api = '''from fastapi import Request


def evidence_report(request: Request, row):
    box = ({"word": "HOT"} if row["rank"] > 0.5 else {"word": "COLD"})
    return {"name": box["word"]}
'''
    findings = _fixture(api, _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), _fmt(findings)


def test_m14_nested_dynamic_selection_and_repeated_joins_keep_alternatives():
    mod = Module("api", "", "fixture.py", lambda q: True)
    ps = Pass([mod])
    frame = Frame(ps, mod, ("api", "probe"), {"rank": V({D}), "key": V({C})}, frozenset())
    first = frame.expr(ast.parse('{"rank": rank, "safe": "ONE"}', mode="eval").body)
    second = frame.expr(ast.parse('\n{"rank": rank, "safe": "TWO"}', mode="eval").body)
    joined = vjoin(vjoin(first, V({E})), second, V({P}))
    frame.env["boxes"] = V(item=joined)
    selected = frame.expr(ast.parse('boxes[key]', mode="eval").body)
    assert len(_dict_arms(selected)) == 2 and D in selected.flat()
    frame.env["selected"] = selected
    safe = frame.expr(ast.parse('selected["safe"]', mode="eval").body)
    assert not safe.flat() & {D, K, O}


def test_transport_results_do_not_aggregate_nested_payload_labels():
    api = '''from fastapi import Request


DB = object()


async def evidence_report(request: Request, row):
    if request.path_params["mode"]:
        params = {"word": "HOT" if row["rank"] > 0.5 else "COLD"}
    else:
        params = None
    result = await DB.execute("query", params)
    return {"name": str(result)}
'''
    assert _fixture(api, _BOT_PERMITTED, _WORKER_FIXTURE) == []


_LITERAL_MUTATIONS = [
    ("subscript assignment", 'box["shown"] = "CHANGED"',
     'box["rank"] = cell[3]', 'box["rank"] = cell[3] > 0.5', True),
    ("augmented subscript assignment", 'box["shown"] += "X"',
     'box["rank"] += cell[3]', 'box["rank"] += cell[3] > 0.5', False),
    ("update mapping", 'box.update({"shown": "CHANGED"})',
     'box.update({"rank": cell[3]})', 'box.update({"rank": cell[3] > 0.5})', True),
    ("update keyword", 'box.update(shown="CHANGED")',
     'box.update(rank=cell[3])', 'box.update(rank=cell[3] > 0.5)', True),
    ("setdefault", 'box.setdefault("shown", "CHANGED")',
     'box.setdefault("rank", cell[3])', 'box.setdefault("rank", cell[3] > 0.5)', True),
    ("dunder setitem", 'box.__setitem__("shown", "CHANGED")',
     'box.__setitem__("rank", cell[3])',
     'box.__setitem__("rank", cell[3] > 0.5)', True),
]


def _literal_mutation_rank(mutation, rank_absent=False):
    initial = '{"shown": "SAFE"}' if rank_absent else '{"rank": 0.0, "shown": "SAFE"}'
    return _dict_fixture(
        '        box = %s\n' % initial
        + '        %s\n' % mutation
        + '        word = "COLD"\n'
          '        if box["rank"] > 0.5:\n'
          '            word = "HOT"\n'
          '        items.append(AerItem("cell", (), (), word))')


@pytest.mark.parametrize("label,preserve,update,no_smear,rank_absent", _LITERAL_MUTATIONS,
                         ids=[row[0] for row in _LITERAL_MUTATIONS])
def test_literal_dict_mutation_updates_only_the_matching_slot(
        label, preserve, update, no_smear, rank_absent):
    findings = _fixture(
        _API_PERMITTED, _literal_mutation_rank(update, rank_absent), _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), (label, _fmt(findings))
    bot = _dict_fixture(
        '        box = {"rank": cell[3], "shown": "SAFE"}\n'
        '        %s\n' % preserve
        + '        word = "COLD"\n'
          '        if box["rank"] > 0.5:\n'
          '            word = "HOT"\n'
          '        items.append(AerItem("cell", (), (), word))')
    findings = _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), (label, _fmt(findings))
    initial = '{"shown": _aer_enc_text(cell[0]), "rank": False}'
    bot = _dict_fixture(
        '        box = %s\n' % initial
        + '        %s\n' % no_smear
        + '        items.append(AerItem("cell", (), (), box["shown"]))')
    assert _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE) == [], label


_DYNAMIC_MUTATIONS = [
    ("subscript assignment", 'box[cell[1]] = "CHANGED"'),
    ("update mapping", 'box.update({cell[1]: "CHANGED"})'),
    ("setdefault", 'box.setdefault(cell[1], "CHANGED")'),
    ("dunder setitem", 'box.__setitem__(cell[1], "CHANGED")'),
]


@pytest.mark.parametrize("label,mutation", _DYNAMIC_MUTATIONS,
                         ids=[row[0] for row in _DYNAMIC_MUTATIONS])
def test_dynamic_dict_mutation_folds_all_old_and_new_slots(label, mutation):
    bot = _dict_fixture(
        '        box = {"shown": _aer_enc_text(cell[0]),\n'
        '               "classified": cell[3] > 0.5}\n'
        '        %s\n' % mutation
        + '        items.append(AerItem("cell", (), (), box["shown"]))')
    findings = _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), (label, _fmt(findings))


_SHARED_DICT_ASSIGN_HELPER = '''def _mutate_box(box, cell):
    box["rank"] = cell[3]


'''

_SHARED_DICT_UPDATE_HELPER = '''def _mutate_box(box, cell):
    box.update(rank=cell[3])


'''

_SHARED_DICT_MUTATIONS = [
    ("local alias subscript",
     '        box = {"rank": 0.0}\n'
     '        other = box\n'
     '        other["rank"] = cell[3]\n', ""),
    ("local alias update",
     '        box = {"rank": 0.0}\n'
     '        other = box\n'
     '        other.update(rank=cell[3])\n', ""),
    ("nested alias subscript",
     '        box = {"rank": 0.0}\n'
     '        boxes = [box]\n'
     '        boxes[0]["rank"] = cell[3]\n', ""),
    ("nested alias update",
     '        box = {"rank": 0.0}\n'
     '        boxes = [box]\n'
     '        boxes[0].update(rank=cell[3])\n', ""),
    ("callee parameter subscript",
     '        box = {"rank": 0.0}\n'
     '        _mutate_box(box, cell)\n', _SHARED_DICT_ASSIGN_HELPER),
    ("callee parameter update",
     '        box = {"rank": 0.0}\n'
     '        _mutate_box(box, cell)\n', _SHARED_DICT_UPDATE_HELPER),
]


@pytest.mark.parametrize("label,setup,helper", _SHARED_DICT_MUTATIONS,
                         ids=[row[0] for row in _SHARED_DICT_MUTATIONS])
def test_mutable_dictionary_identity_updates_every_later_view(label, setup, helper):
    bot = _dict_fixture(
        setup
        + '        word = "COLD"\n'
          '        if box["rank"] > 0.5:\n'
          '            word = "HOT"\n'
          '        items.append(AerItem("cell", (), (), word))', helper)
    findings = _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), (label, _fmt(findings))


def test_independent_equal_dictionary_literals_keep_distinct_identities():
    bot = _dict_fixture(
        '        changed = {"rank": 0.0}\n'
        '        untouched = {"rank": 0.0}\n'
        '        changed["rank"] = cell[3]\n'
        '        word = "COLD"\n'
        '        if untouched["rank"] > 0.5:\n'
        '            word = "HOT"\n'
        '        items.append(AerItem("cell", (), (), word))')
    assert _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE) == []


_SETDEFAULT_RESULTS = [
    ("present slot",
     '        box = {"rank": cell[3]}\n'
     '        result = box.setdefault("rank", 0.0)\n'),
    ("inserted default",
     '        box = {}\n'
     '        result = box.setdefault("rank", cell[3])\n'),
    ("dynamic key",
     '        box = {"rank": cell[3]}\n'
     '        key = "rank"\n'
     '        result = box.setdefault(key, 0.0)\n'),
]


@pytest.mark.parametrize("label,setup", _SETDEFAULT_RESULTS,
                         ids=[row[0] for row in _SETDEFAULT_RESULTS])
def test_setdefault_returns_the_selected_shared_dictionary_value(label, setup):
    bot = _dict_fixture(
        setup
        + '        word = "COLD"\n'
          '        if result > 0.5:\n'
          '            word = "HOT"\n'
          '        items.append(AerItem("cell", (), (), word))')
    findings = _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), (label, _fmt(findings))


def test_setdefault_present_slot_does_not_return_or_insert_its_default():
    bot = _dict_fixture(
        '        box = {"rank": 0.0}\n'
        '        result = box.setdefault("rank", cell[3])\n'
        '        word = "COLD"\n'
        '        if result > 0.5:\n'
        '            word = "HOT"\n'
        '        items.append(AerItem("cell", (), (), word))')
    assert _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE) == []


@pytest.mark.parametrize("call", [
    'box.update(rank=cell[3])',
    'box.__setitem__("rank", cell[3])',
], ids=["update", "dunder setitem"])
def test_non_setdefault_mutators_keep_their_constant_return(call):
    bot = _dict_fixture(
        '        box = {"rank": 0.0}\n'
        '        result = %s\n' % call
        + '        items.append(AerItem("cell", (), (), result))')
    assert _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE) == []


def _setdefault_api(setup, selected="result", helper=""):
    return helper + '''def evidence_report(row):
%s    word = "COLD"
    if %s > 0.5:
        word = "HOT"
    return {"name": word}
''' % (setup, selected)


@pytest.mark.parametrize("selected", ["result", 'box["rank"]'],
                         ids=["returned result", "stored slot"])
def test_setdefault_on_an_api_key_that_may_be_present_joins_the_default(selected):
    api = _setdefault_api(
        '    box = {}\n'
        '    result = box.setdefault("rank", row["rank"])\n', selected)
    findings = _fixture(api, _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), (
        selected, _fmt(findings))


def test_setdefault_result_directly_joins_a_may_present_slot_and_default():
    ref = DictRef(("fixture", "may-present"))
    ref.seed((), ())
    ref.slot_update("rank", V({C}))
    recv = V(alias=("dict", ref))
    node = ast.parse('box.setdefault("rank", default)').body[0].value
    result = Frame.setdefault_result(None, recv, node, [V({C}), V({D})])
    assert result.flat() == {C, D}


def test_setdefault_same_site_runtime_instances_join_later_defaults():
    helper = '''def _remember(value):
    box = {}
    return box.setdefault("rank", value)


'''
    api = _setdefault_api(
        '    _remember(0.0)\n'
        '    result = _remember(row["rank"])\n', helper=helper)
    findings = _fixture(api, _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), _fmt(findings)


def test_setdefault_after_a_request_controlled_path_keeps_the_data_default():
    api = '''from fastapi import Request


def evidence_report(request: Request, row):
    box = {}
    if request.path_params["mode"]:
        box.setdefault("rank", 0.0)
    result = box.setdefault("rank", row["rank"])
    word = "COLD"
    if result > 0.5:
        word = "HOT"
    return {"name": word}
'''
    findings = _fixture(api, _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), _fmt(findings)


@pytest.mark.parametrize("setup", [
    '    box = row["mapping"]\n'
    '    result = box.setdefault("rank", 0.0)\n',
    '    box = dict()\n'
    '    result = box.setdefault("rank", row["rank"])\n',
], ids=["receiver element", "default value"])
def test_setdefault_on_a_non_literal_mapping_returns_element_plus_default(setup):
    findings = _fixture(
        _setdefault_api(setup), _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), (
        setup, _fmt(findings))


@pytest.mark.parametrize("selected", ["result", 'box["rank"]'],
                         ids=["returned result", "stored slot"])
def test_setdefault_on_a_definitely_present_literal_key_suppresses_the_default(selected):
    api = _setdefault_api(
        '    box = {"rank": 0.0}\n'
        '    result = box.setdefault("rank", row["rank"])\n', selected)
    assert _fixture(api, _BOT_PERMITTED, _WORKER_FIXTURE) == []


def test_setdefault_state_does_not_merge_distinct_empty_literal_sites():
    api = _setdefault_api(
        '    changed = {}\n'
        '    untouched = {}\n'
        '    changed.setdefault("rank", row["rank"])\n'
        '    result = untouched.setdefault("rank", 0.0)\n')
    assert _fixture(api, _BOT_PERMITTED, _WORKER_FIXTURE) == []


_BOT_GO = '''async def _aer_go(body):
    page = _aer_decode_response(body)
    plan = _aer_plan(page)
    return "\\n".join(item.text for item in plan)
'''

_ORDER_VALUE = '''def _order_value(cell):
    return cell[3]


'''


def _order_context_fixture(go, helper=""):
    source = _BOT_PERMITTED.replace(
        "def _aer_plan(page):", _ORDER_VALUE + helper + "def _aer_plan(page):")
    return source.replace(_BOT_GO, go)


_ORDER_CONTEXT_NEGATIVES = [
    ("direct display sink", _order_context_fixture('''async def _aer_go(body, channel):
    page = _aer_decode_response(body)
    for cell in sorted(page.cells, key=_order_value):
        channel.send(content="DIRECT")
    plan = _aer_plan(page)
    return "\\n".join(item.text for item in plan)
''')),
    ("module helper display sink", _order_context_fixture('''async def _aer_go(body, channel):
    page = _aer_decode_response(body)
    for cell in sorted(page.cells, key=_order_value):
        _show(channel)
    plan = _aer_plan(page)
    return "\\n".join(item.text for item in plan)
''', '''def _show(channel):
    channel.send(content="HELPER")


''')),
    ("local method display sink", _order_context_fixture('''async def _aer_go(body, channel, helper):
    page = _aer_decode_response(body)
    for cell in sorted(page.cells, key=_order_value):
        helper.show(channel)
    plan = _aer_plan(page)
    return "\\n".join(item.text for item in plan)
''', '''class Helper:
    def show(self, channel):
        channel.send(content="METHOD")


''')),
    ("callback display sink", _order_context_fixture('''async def _aer_go(body, channels):
    page = _aer_decode_response(body)
    for cell in sorted(page.cells, key=_order_value):
        sorted(channels, key=_callback)
    plan = _aer_plan(page)
    return "\\n".join(item.text for item in plan)
''', '''def _callback(channel):
    channel.send(content="CALLBACK")
    return 0


''')),
    ("return in ordered loop", _order_context_fixture('''async def _aer_go(body, channel):
    page = _aer_decode_response(body)
    _ordered(page.cells, channel)
    plan = _aer_plan(page)
    return "\\n".join(item.text for item in plan)
''', '''def _show(channel):
    return channel.send(content="RETURN")


def _ordered(cells, channel):
    for cell in sorted(cells, key=_order_value):
        return _show(channel)
    return None


''')),
]


@pytest.mark.parametrize("label,bot", _ORDER_CONTEXT_NEGATIVES,
                         ids=[row[0] for row in _ORDER_CONTEXT_NEGATIVES])
def test_order_context_reaches_display_callees_and_callbacks(label, bot):
    findings = _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE)
    assert len(findings) == 1 and ".send content= reads O" in str(findings[0]), (
        label, _fmt(findings))


def test_report_data_set_containment_is_a_classification_flow():
    bot = _dict_fixture(
        '        word = "HOT" if set(cell[0]) <= {"x"} else "COLD"\n'
        '        items.append(AerItem("cell", (), (), word))')
    findings = _fixture(_API_PERMITTED, bot, _WORKER_FIXTURE)
    assert len(findings) == 1 and "reads K" in str(findings[0]), _fmt(findings)


_SET_CALL_SPELLINGS = (
    "issubset", "issuperset", "operator.le", "operator.ge", "__le__", "__ge__")
_SET_CALL_PROVENANCE = (
    ("E", 'set(_aer_enc(r["value"]))'),
    ("D", 'set(r["value"])'),
)


def _set_call_expr(spelling, left, right):
    if spelling.startswith("operator."):
        return "%s(%s, %s)" % (spelling, left, right)
    return "%s.%s(%s)" % (left, spelling, right)


def _set_call_api(expr):
    return '''import operator


def _aer_enc(value):
    return str(value)


def evidence_report(r):
    selected = %s
    return {"name": "HOT" if selected else "COLD"}
''' % expr


_SET_CALL_NEGATIVES = [
    ("%s %s %s" % (spelling, provenance, side), spelling, provenance,
     _set_call_expr(spelling, value if side == "receiver" else '{"x"}',
                    value if side == "argument" else '{"x"}'))
    for spelling in _SET_CALL_SPELLINGS
    for provenance, value in _SET_CALL_PROVENANCE
    for side in ("receiver", "argument")
]


@pytest.mark.parametrize("label,spelling,_provenance,expr", _SET_CALL_NEGATIVES,
                         ids=[row[0] for row in _SET_CALL_NEGATIVES])
def test_set_containment_call_spellings_classify_e_or_d_from_either_operand(
        label, spelling, _provenance, expr):
    findings = _fixture(_set_call_api(expr), _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "api display slot 'name' reads K" in str(findings[0]), (
        label, _fmt(findings))
    fixed = _set_call_expr(spelling, '{"x"}', '{"x"}')
    assert _fixture(_set_call_api(fixed), _BOT_PERMITTED, _WORKER_FIXTURE) == [], label
    if label == "issubset E receiver":
        generic = _API_PERMITTED.replace('_text(r["display_name"])',
                                         '_text(r["display_name"]).lower()')
        assert _fixture(generic, _BOT_PERMITTED, _WORKER_FIXTURE) == []


_SET_ORDER_SPELLINGS = ("native",) + _SET_CALL_SPELLINGS
_SET_IMPLICIT_PROVENANCE = (
    ("E", '_aer_enc(r["value"])'),
    ("D", 'r["value"]'),
)


def _set_order_expr(spelling, left, right):
    if spelling == "native":
        return "%s <= %s" % (left, right)
    return _set_call_expr(spelling, left, right)


_SET_IMPLICIT_NEGATIVES = [
    ("%s implicit %s %s" % (spelling, provenance, side),
     _set_order_expr(
         spelling,
         conditional if side == "left" else '{"z"}',
         conditional if side == "right" else '{"z"}'))
    for spelling in _SET_ORDER_SPELLINGS
    for provenance, source in _SET_IMPLICIT_PROVENANCE
    for conditional in ['({"x"} if %s else {"y"})' % source]
    for side in ("left", "right")
]


@pytest.mark.parametrize("label,expr", _SET_IMPLICIT_NEGATIVES,
                         ids=[row[0] for row in _SET_IMPLICIT_NEGATIVES])
def test_set_ordering_classifies_implicit_e_or_d_from_either_operand(label, expr):
    findings = _fixture(_set_call_api(expr), _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "api display slot 'name' reads K" in str(findings[0]), (
        label, _fmt(findings))


_ORDERED_CALL_SPELLINGS = ("operator.le", "operator.ge", "__le__", "__ge__")
_ORDERED_NUMERIC_PROVENANCE = (
    ("E", 'set(_aer_enc(r["value"]))'),
    ("D", 'set(r["value"])'),
)


def _unused_set_call_api(expr, bound=False):
    bounds = 'CONTRACT_BOUNDS = {"limit": 0.83}\n\n' if bound else ""
    return '''import operator


%sdef _aer_enc(value):
    return str(value)


def evidence_report(r):
    %s
    return {"name": "SAFE"}
''' % (bounds, expr)


_ORDERED_NUMERIC_NEGATIVES = [
    ("%s %s literal %s" % (spelling, provenance, side),
     _set_call_expr(spelling,
                    value if side == "receiver" else "(0.83)",
                    value if side == "argument" else "0.83"))
    for spelling in _ORDERED_CALL_SPELLINGS
    for provenance, value in _ORDERED_NUMERIC_PROVENANCE
    for side in ("receiver", "argument")
]


@pytest.mark.parametrize("label,expr", _ORDERED_NUMERIC_NEGATIVES,
                         ids=[row[0] for row in _ORDERED_NUMERIC_NEGATIVES])
def test_ordered_call_spellings_audit_non_allowlisted_numeric_literals(label, expr):
    findings = _fixture(_unused_set_call_api(expr), _BOT_PERMITTED, _WORKER_FIXTURE)
    assert len(findings) == 1 and "numeric literal 0.83" in str(findings[0]), (
        label, _fmt(findings))


def test_ordered_call_numeric_audit_keeps_allowlisted_and_bound_values():
    value = 'set(_aer_enc(r["value"]))'
    allowlisted = _set_call_expr("operator.le", value, "0.5")
    assert _fixture(_unused_set_call_api(allowlisted),
                    _BOT_PERMITTED, _WORKER_FIXTURE) == []
    bound = _set_call_expr("operator.ge", value, 'CONTRACT_BOUNDS["limit"]')
    assert _fixture(_unused_set_call_api(bound, bound=True),
                    _BOT_PERMITTED, _WORKER_FIXTURE) == []


@pytest.mark.parametrize("spelling", ["issubset", "issuperset"])
def test_non_ordered_set_containment_calls_do_not_gain_numeric_audits(spelling):
    value = 'set(_aer_enc(r["value"]))'
    expr = _set_call_expr(spelling, value, "0.83")
    assert _fixture(_unused_set_call_api(expr), _BOT_PERMITTED, _WORKER_FIXTURE) == []


_REQUEST_IDENT_API = '''from fastapi import Request

_HEX = frozenset("0123456789abcdef")


def _aer_enc(value):
    return str(value)


def _aer_ident(raw):
    s = (raw or "").strip().lower().replace("-", "")
    if s and set(s) <= _HEX and set(s).issubset(_HEX):
        if len(s) == 32:
            return "full", s
        if len(s) == 12:
            return "code", s
    return None


def evidence_report(request: Request):
    ident = _aer_ident(request.path_params["code"])
    return {"name": _aer_enc(ident[1])}
'''


def test_structural_request_identifier_validation_keeps_request_provenance():
    ps = Pass([Module("api", _REQUEST_IDENT_API, "fixture_api.py", lambda q: True)])
    findings = ps.run()
    labels = ps.returns[("api", "_aer_ident")].flat()
    assert "R" in labels and K not in labels and findings == [], (labels, _fmt(findings))
