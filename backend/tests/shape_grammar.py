"""The default-deny shape grammar of rehearsal-four round 7 (ruling
REHEARSAL-FOUR-R6 (1)(b)).

A walk over source is admitted only when EVERY node it visits has a shape in
a frozen whitelist; any other shape refuses, naming the file, the line and
the shape. Nothing here reasons about what a name denotes: no alias
tracking, no import resolution, no metaclass or mapping reasoning, no branch
merging. A shape is purely syntactic:

    <Parent>.<field>><Class>(<field>=<child shape>, ...)

  * the parent's class and the field the node sits in (so a `return` in a
    `finally` body is a different shape from a `return` in a function body);
  * the node's class;
  * per field, in the class's field order: a child node's class; a list's
    sorted set of child classes ("[]" when empty); "-" for None; the literal
    text of the identity fields IDENTITY names (an attribute's name, a
    keyword's name, an import's module, names and alias, a format
    conversion); the type name of a constant's value; "str" for any other
    string field.

Name spellings are not part of a shape (a whitelist keyed by every local
variable would be a list of the file). Spellings are judged by one separate
syntactic rule, `bindings`: every place a span BINDS a spelling (a store, a
deletion, a parameter, a def or class name, an import, an except name, a
global or nonlocal) is listed, and a corpus refuses a binding of a spelling
it gives a meaning to.
"""
import ast
import hashlib

# Identity fields whose literal value is part of the shape.
IDENTITY = {
    ("Attribute", "attr"), ("keyword", "arg"), ("alias", "name"),
    ("alias", "asname"), ("ImportFrom", "module"), ("ImportFrom", "level"),
    ("Import", "names"), ("FormattedValue", "conversion"),
    ("comprehension", "is_async"),
}


class Refused(Exception):
    """A node outside the whitelist: args[0] is (file, line, shape)."""


def _child(v):
    if isinstance(v, ast.AST):
        return type(v).__name__
    return type(v).__name__


def header(node):
    """A statement's own nodes as text (closed_walk's ORDER rule): every
    field, recursively, with each nested list of statements replaced by its
    length; line and column attributes are not fields and are not read."""
    if isinstance(node, list):
        if node and all(isinstance(x, ast.stmt) for x in node):
            return f"<{len(node)} statements>"
        return "[" + ", ".join(header(x) for x in node) + "]"
    if not isinstance(node, ast.AST):
        return repr(node)
    parts = [f"{f}={header(v)}" for f, v in ast.iter_fields(node)]
    return f"{type(node).__name__}(" + ", ".join(parts) + ")"


def header_digest(node):
    """The first 16 hex digits of the sha256 of header(node)."""
    return hashlib.sha256(header(node).encode("utf-8")).hexdigest()[:16]


def shape(node, parent=None, field=None):
    """The shape string of `node` sitting in `parent`.`field`."""
    cls = type(node).__name__
    where = f"{type(parent).__name__}.{field}" if parent is not None else "<root>"
    parts = []
    for f, v in ast.iter_fields(node):
        if (cls, f) in IDENTITY:
            if isinstance(v, list):
                parts.append(f"{f}=[{','.join(sorted(repr(getattr(a, 'name', a)) for a in v))}]")
            else:
                parts.append(f"{f}={v!r}")
        elif cls == "Constant" and f == "value":
            parts.append(f"value={type(v).__name__}")
        elif cls == "Constant" and f == "kind":
            continue
        elif isinstance(v, ast.AST):
            parts.append(f"{f}={type(v).__name__}")
        elif isinstance(v, list):
            parts.append(f"{f}=[{'|'.join(sorted({_child(x) for x in v}))}]")
        elif v is None:
            parts.append(f"{f}=-")
        elif isinstance(v, str):
            parts.append(f"{f}=str")
        else:
            parts.append(f"{f}={v!r}")
    return f"{where}>{cls}({','.join(parts)})"


def visit(root):
    """Every (node, parent, field) under `root`, root included (parent None),
    in a deterministic pre-order."""
    out = [(root, None, None)]
    stack = [root]
    while stack:
        n = stack.pop()
        kids = []
        for f, v in ast.iter_fields(n):
            if isinstance(v, ast.AST):
                kids.append((v, n, f))
            elif isinstance(v, list):
                kids.extend((x, n, f) for x in v if isinstance(x, ast.AST))
        out.extend(kids)
        stack.extend(k[0] for k in reversed(kids))
    return out


def _line(node, parent):
    return getattr(node, "lineno", None) or getattr(parent, "lineno", 0) or 0


def shapes(root):
    """{shape: first line} over every node under root (the generator's view)."""
    out = {}
    for n, p, f in visit(root):
        out.setdefault(shape(n, p, f), _line(n, p))
    return out


def refusals(root, whitelist, filename):
    """[(file, line, shape)] for every node under root whose shape is not in
    whitelist, in visit order."""
    return [(filename, _line(n, p), s) for n, p, f in visit(root)
            for s in (shape(n, p, f),) if s not in whitelist]


def check(root, whitelist, filename):
    """Raise Refused for the first node under root outside the whitelist;
    return the number of nodes visited (the completeness count)."""
    seen = 0
    for n, p, f in visit(root):
        seen += 1
        s = shape(n, p, f)
        if s not in whitelist:
            raise Refused((filename, _line(n, p), s))
    return seen


def bindings(root):
    """[(line, spelling, how)] for every syntactic binding under root (the
    root's own name and parameters included)."""
    out = []
    for n, p, f in visit(root):
        ln = _line(n, p)
        if isinstance(n, ast.Name) and not isinstance(n.ctx, ast.Load):
            out.append((ln, n.id, type(n.ctx).__name__.lower()))
        elif isinstance(n, ast.arg):
            out.append((ln, n.arg, "parameter"))
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append((ln, n.name, "def"))
        elif isinstance(n, ast.alias):
            out.append((ln, n.asname or n.name.split(".")[0], "import"))
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.append((ln, n.name, "except"))
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            out.extend((ln, s, type(n).__name__.lower()) for s in n.names)
        elif type(n).__name__ in ("MatchAs", "MatchStar") and getattr(n, "name", None):
            out.append((ln, n.name, "match"))
        elif type(n).__name__ == "MatchMapping" and getattr(n, "rest", None):
            out.append((ln, n.rest, "match"))
    return out


def binding_refusals(root, meaningful, allowed, filename):
    """[(file, line, 'binds <spelling> (<how>)')] for every binding under
    root of a spelling in `meaningful` whose (spelling, how) is not in
    `allowed`."""
    return [(filename, ln, f"binds {s} ({how})") for ln, s, how in bindings(root)
            if s in meaningful and (s, how) not in allowed]
