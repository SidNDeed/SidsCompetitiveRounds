"""Structural reading of C# sources for the source-shape gates.

Five test modules used to carry their own copy of a brace walk that counted
every `{` in the raw text, plus a comment stripper that only dropped lines
*starting* with `//`. Both are wrong in ways that matter here:

* A brace inside a comment, a string, a char literal or an inactive `#if`
  branch counted as structure. `plugin/Plugin.cs` carries a doc comment
  containing `for (...) { if (pickrID != -1) {` - two unmatched opens - so any
  walk crossing it silently returned the wrong block, and an assertion made
  against that block was testing text nobody chose. Measured: that file's raw
  brace balance is +2 and its masked balance is 0.
* A needle sitting in a *trailing* comment satisfied a code assertion, because
  the stripper never looked past the first token of a line. That is the
  "a check that cannot fail" shape (learnings #342/#431/#441).

Everything here works on a MASK: a copy of the source with the same length and
the same newlines, where every non-code region is replaced by spaces. Offsets
into the mask are therefore offsets into the original, so structure is decided
on the mask and text is read from the source.

There is ONE walk (`_walk`), parameterised by whether literals survive it.
Two near-identical copies of a scanner is the defect this module was written
to remove; it would be a poor showing to reintroduce it here.

`naive_block` at the bottom is the old algorithm, kept deliberately broken as
the standing negative control for `test_cs_structure.py` (learning #391): the
masker's properties are only meaningful while something still demonstrates the
failure they prevent.
"""

from __future__ import annotations

from pathlib import Path


class CsParseError(AssertionError):
    """The source could not be read structurally. Never a skip - always a failure.

    A parse refusal that degrades to a skip converts a real gate into silence
    the next time a compiler feature lands, which is the defect this module
    exists to remove one level up.
    """


# Symbols defined by the Release build. `THUNDERSTORE` is the shipped build
# gate and is NOT defined here: the Release DLL is the artifact these gates
# describe, so the inactive branch must read as absent, not as code.
RELEASE_SYMBOLS: frozenset = frozenset()


def _blank(text: str) -> str:
    """Same length, same line breaks, no content."""
    return "".join("\n" if ch == "\n" else " " for ch in text)


# ── preprocessor ─────────────────────────────────────────────────────────────

def _eval_condition(expr: str, defined: frozenset) -> bool:
    """Evaluate a C# preprocessor condition over `defined`.

    Supports the forms this repository actually uses - an identifier, `!`,
    `&&`, `||`, parentheses, `true`/`false`. Anything else raises rather than
    guessing, because guessing wrong silently masks live code.
    """
    tokens: list = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch.isspace():
            i += 1
        elif expr.startswith("&&", i) or expr.startswith("||", i):
            tokens.append(expr[i : i + 2])
            i += 2
        elif ch in "!()":
            tokens.append(ch)
            i += 1
        elif ch.isalnum() or ch == "_":
            j = i
            while j < len(expr) and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            tokens.append(expr[i:j])
            i = j
        else:
            raise CsParseError(f"unsupported preprocessor condition: {expr!r}")

    pos = 0

    def parse_or() -> bool:
        nonlocal pos
        value = parse_and()
        while pos < len(tokens) and tokens[pos] == "||":
            pos += 1
            value = parse_and() or value
        return value

    def parse_and() -> bool:
        nonlocal pos
        value = parse_unary()
        while pos < len(tokens) and tokens[pos] == "&&":
            pos += 1
            value = parse_unary() and value
        return value

    def parse_unary() -> bool:
        nonlocal pos
        if pos < len(tokens) and tokens[pos] == "!":
            pos += 1
            return not parse_unary()
        if pos < len(tokens) and tokens[pos] == "(":
            pos += 1
            value = parse_or()
            if pos >= len(tokens) or tokens[pos] != ")":
                raise CsParseError(f"unbalanced parentheses in condition: {expr!r}")
            pos += 1
            return value
        if pos >= len(tokens):
            raise CsParseError(f"truncated preprocessor condition: {expr!r}")
        name = tokens[pos]
        pos += 1
        if name == "true":
            return True
        if name == "false":
            return False
        return name in defined

    result = parse_or()
    if pos != len(tokens):
        raise CsParseError(f"trailing tokens in preprocessor condition: {expr!r}")
    return result


# ── literals ─────────────────────────────────────────────────────────────────

def _line_of(src: str, i: int) -> int:
    return src.count("\n", 0, i) + 1


def _string_end(src: str, i: int) -> int:
    """Index just past the literal beginning at `i`.

    Handles plain, verbatim (`@`), interpolated (`$`), interpolated-verbatim
    (`$@` / `@$`) strings and char literals. Interpolation holes are walked
    rather than skipped, because a hole may contain further literals - this
    repository has `$"...{(chan == null ? "null" : $"...")}..."` at
    `plugin/ApiClient.cs:5608`, and a scanner that stops at the first quote
    ends the outer string in the middle of the expression.
    """
    n = len(src)
    verbatim = False
    interpolated = False
    j = i
    if src.startswith("$@", j) or src.startswith("@$", j):
        verbatim = interpolated = True
        j += 2
    elif src[j] == "@":
        verbatim = True
        j += 1
    elif src[j] == "$":
        interpolated = True
        j += 1

    if j >= n:
        raise CsParseError(f"truncated literal at line {_line_of(src, i)}")

    if src[j] == "'":
        j += 1
        while j < n:
            if src[j] == "\\":
                j += 2
                continue
            if src[j] == "'":
                return j + 1
            j += 1
        raise CsParseError(f"unterminated char literal at line {_line_of(src, i)}")

    if src[j] != '"':
        raise CsParseError(f"not a literal at line {_line_of(src, i)}")

    # A raw string is three quotes NOT introduced by `@`. `@""` opens a
    # verbatim string whose first content character is an escaped quote.
    if not verbatim and src.startswith('"""', j):
        raise CsParseError(
            f"C# 11 raw string literal at line {_line_of(src, i)}: this masker "
            "does not model raw strings. Teach it the form rather than skipping."
        )

    j += 1
    hole = 0
    while j < n:
        ch = src[j]
        if not verbatim and ch == "\\":
            j += 2
            continue
        if interpolated and ch == "{":
            if j + 1 < n and src[j + 1] == "{":
                j += 2
                continue
            hole += 1
            j += 1
            continue
        if interpolated and ch == "}":
            if hole > 0:
                hole -= 1
                j += 1
                continue
            if j + 1 < n and src[j + 1] == "}":
                j += 2
                continue
            j += 1
            continue
        if ch == '"':
            if hole > 0:
                # A literal nested inside an interpolation hole.
                j = _string_end(src, j)
                continue
            if verbatim and j + 1 < n and src[j + 1] == '"':
                j += 2
                continue
            return j + 1
        if hole > 0 and (ch == "'" or ch == "@" or ch == "$"):
            # A char literal, or a nested verbatim/interpolated string, inside
            # a hole. `@`/`$` only start one when a quote follows.
            if ch == "'" or (j + 1 < n and src[j + 1] in '"@$'):
                j = _string_end(src, j)
                continue
        if not verbatim and ch == "\n" and hole == 0:
            raise CsParseError(
                f"unterminated string literal at line {_line_of(src, i)}"
            )
        j += 1
    raise CsParseError(f"unterminated literal at line {_line_of(src, i)}")


# ── the one walk ─────────────────────────────────────────────────────────────

def _walk(src: str, defined: frozenset, keep_literals: bool) -> str:
    """Blank comments and inactive `#if` branches; blank literals unless kept.

    Length and newline positions are preserved in both modes, so an offset into
    the result is an offset into `src`.
    """
    out: list = []
    i = 0
    n = len(src)
    cond_stack: list = []          # [this_branch_active, any_branch_taken, line]
    at_line_start = True

    def emitting() -> bool:
        return all(frame[0] for frame in cond_stack)

    while i < n:
        ch = src[i]

        if at_line_start and ch == "#":
            end = src.find("\n", i)
            end = n if end == -1 else end
            body = src[i:end].strip()[1:].lstrip()
            keyword = body.split(None, 1)[0] if body else ""
            argument = body[len(keyword) :].strip()
            line_no = _line_of(src, i)
            if keyword == "if":
                active = _eval_condition(argument, defined) if emitting() else False
                cond_stack.append([active, active, line_no])
            elif keyword == "elif":
                if not cond_stack:
                    raise CsParseError(f"#elif without #if at line {line_no}")
                frame = cond_stack[-1]
                outer = all(f[0] for f in cond_stack[:-1])
                active = (
                    _eval_condition(argument, defined)
                    if outer and not frame[1]
                    else False
                )
                frame[0] = active
                frame[1] = frame[1] or active
            elif keyword == "else":
                if not cond_stack:
                    raise CsParseError(f"#else without #if at line {line_no}")
                frame = cond_stack[-1]
                outer = all(f[0] for f in cond_stack[:-1])
                frame[0] = outer and not frame[1]
                frame[1] = True
            elif keyword == "endif":
                if not cond_stack:
                    raise CsParseError(f"#endif without #if at line {line_no}")
                cond_stack.pop()
            # `#region`, `#pragma`, `#nullable` carry no structure either.
            out.append(_blank(src[i:end]))
            i = end
            continue

        if ch == "\n":
            out.append("\n")
            i += 1
            at_line_start = True
            continue
        if not ch.isspace():
            at_line_start = False

        if not emitting():
            out.append(" ")
            i += 1
            continue

        if src.startswith("//", i):
            end = src.find("\n", i)
            end = n if end == -1 else end
            out.append(_blank(src[i:end]))
            i = end
            continue

        if src.startswith("/*", i):
            end = src.find("*/", i + 2)
            if end == -1:
                raise CsParseError(f"unterminated block comment at line {_line_of(src, i)}")
            end += 2
            out.append(_blank(src[i:end]))
            i = end
            continue

        starts_literal = (
            ch in "\"'"
            or (ch in "@$" and i + 1 < n and (src[i + 1] in "\"'@$"))
        )
        if starts_literal:
            end = _string_end(src, i)
            out.append(src[i:end] if keep_literals else _blank(src[i:end]))
            i = end
            continue

        out.append(ch)
        i += 1

    if cond_stack:
        raise CsParseError(f"unclosed #if from line {cond_stack[-1][2]}")

    result = "".join(out)
    if len(result) != len(src):
        raise CsParseError("walk changed length; offsets would be wrong")
    return result


def mask_code(src: str, defined: frozenset = RELEASE_SYMBOLS) -> str:
    """Blank comments, literals, and inactive `#if` branches; keep offsets.

    Use for every structural decision: brace depth, statement position,
    operator splitting. A brace or a `//` inside a string is not structure.
    """
    return _walk(src, defined, keep_literals=False)


def strip_comments_only(src: str, defined: frozenset = RELEASE_SYMBOLS) -> str:
    """Blank comments and inactive branches, KEEP string literals.

    For needle assertions where the needle may legitimately live inside a
    literal (a log line, an SQL fragment, a route). Unlike the line-prefix
    stripper this replaces, it also removes TRAILING comments, so a needle in
    prose can no longer satisfy a code assertion.
    """
    return _walk(src, defined, keep_literals=True)


# ── spans ────────────────────────────────────────────────────────────────────

def _read(source) -> str:
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8")
    return source


def method_spans(source, signature: str, defined: frozenset = RELEASE_SYMBOLS):
    """Yield `(open_brace, close_brace_exclusive)` for EVERY `signature` block.

    Plural and iterating, because the single-block form is what let a caller
    hold a stale body when a walk overran. An unbalanced crossing raises here;
    it can never be returned.
    """
    src = _read(source)
    masked = mask_code(src, defined)
    search = 0
    while True:
        start = masked.find(signature, search)
        if start == -1:
            return
        open_brace = masked.find("{", start + len(signature))
        if open_brace == -1:
            raise CsParseError(f"no block opens after {signature!r}")
        depth = 0
        end = None
        for i in range(open_brace, len(masked)):
            if masked[i] == "{":
                depth += 1
            elif masked[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            raise CsParseError(f"unbalanced braces after {signature!r}")
        yield (open_brace, end)
        search = end


def _single_span(src: str, signature: str, defined: frozenset):
    spans = list(method_spans(src, signature, defined))
    if not spans:
        raise CsParseError(f"signature not found: {signature!r}")
    if len(spans) > 1:
        raise CsParseError(
            f"{len(spans)} blocks match {signature!r}; name the one you mean"
        )
    return spans[0]


def cs_block(source, signature: str, defined: frozenset = RELEASE_SYMBOLS) -> str:
    """The single brace-balanced block following `signature`.

    Raises when the signature appears more than once: two matches means the
    caller's assertion was about whichever came first by accident.
    """
    src = _read(source)
    open_brace, end = _single_span(src, signature, defined)
    return src[open_brace:end]


def code_of(source, signature: str = None,
            defined: frozenset = RELEASE_SYMBOLS) -> str:
    """A block (or a whole file) with comments and inactive branches removed."""
    src = _read(source)
    text = cs_block(src, signature, defined) if signature else src
    return strip_comments_only(text, defined)


# ── expressions ──────────────────────────────────────────────────────────────

def and_terms(expr: str) -> list:
    """Split a boolean expression on top-level `&&`.

    Raises on a top-level `||`: the callers all assert a conjunction, and an
    `&&` quietly becoming `||` is exactly the mutation a substring assertion
    cannot see.
    """
    masked = mask_code(expr)
    terms: list = []
    depth = 0
    start = 0
    i = 0
    while i < len(masked):
        ch = masked[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif depth == 0 and masked.startswith("||", i):
            raise CsParseError(f"top-level `||` in a conjunction: {expr!r}")
        elif depth == 0 and masked.startswith("&&", i):
            terms.append(expr[start:i].strip())
            i += 2
            start = i
            continue
        i += 1
    terms.append(expr[start:].strip())
    return [t for t in terms if t]


def initialiser(source, signature: str, declaration: str,
                defined: frozenset = RELEASE_SYMBOLS) -> str:
    """The text of `declaration`'s initialiser, up to its terminating `;`."""
    src = _read(source)
    block = cs_block(src, signature, defined)
    masked = mask_code(block, defined)
    at = masked.find(declaration)
    if at == -1:
        raise CsParseError(f"{declaration!r} not found in {signature!r}")
    eq = masked.find("=", at + len(declaration))
    if eq == -1:
        raise CsParseError(f"{declaration!r} has no initialiser")
    semi = masked.find(";", eq)
    if semi == -1:
        raise CsParseError(f"{declaration!r} initialiser is unterminated")
    return block[eq + 1 : semi].strip()


def guard_chain(source, signature: str, needle: str,
                defined: frozenset = RELEASE_SYMBOLS) -> list:
    """The `if` conditions that DOMINATE `needle` inside `signature`'s block.

    Text order and indentation prove nothing about nesting - an already-closed
    block followed by a deeper unrelated one satisfies both. This walks the
    mask and returns the conditions actually enclosing the statement, outermost
    first, so a test can assert a write is reachable only under those terms.
    """
    src = _read(source)
    open_brace, end = _single_span(src, signature, defined)
    block = src[open_brace:end]
    masked = mask_code(src, defined)[open_brace:end]

    target = masked.find(needle)
    if target == -1:
        raise CsParseError(
            f"{needle!r} not found in {signature!r} (searched code, not comments)"
        )
    if masked.find(needle, target + 1) != -1:
        raise CsParseError(f"{needle!r} appears more than once in {signature!r}")

    stack: list = []
    i = 0
    while i < target:
        if masked[i] == "{":
            stack.append(_condition_before(masked, block, i))
        elif masked[i] == "}":
            if stack:
                stack.pop()
        i += 1
    conditions = [c for c in stack if c]

    inline = _condition_before(masked, block, target)
    if inline:
        conditions.append(inline)
    return conditions


def _condition_before(masked: str, block: str, at: int):
    """The `if (...)` condition immediately preceding position `at`, if any."""
    j = at - 1
    while j >= 0 and masked[j].isspace():
        j -= 1
    if j < 0 or masked[j] != ")":
        return None
    depth = 0
    k = j
    while k >= 0:
        if masked[k] == ")":
            depth += 1
        elif masked[k] == "(":
            depth -= 1
            if depth == 0:
                break
        k -= 1
    if k < 0:
        return None
    word_end = k
    while word_end > 0 and masked[word_end - 1].isspace():
        word_end -= 1
    word_start = word_end
    while word_start > 0 and (
        masked[word_start - 1].isalnum() or masked[word_start - 1] == "_"
    ):
        word_start -= 1
    if masked[word_start:word_end] != "if":
        return None
    return block[k + 1 : j].strip()


# ── the negative control ─────────────────────────────────────────────────────

def naive_block(source, signature: str) -> str:
    """The pre-2026-09-06 algorithm: count braces in RAW source.

    Kept, and kept broken, so `test_cs_structure.py` always has something that
    demonstrates the failure the masker prevents. If this ever stops being
    wrong, the properties above stopped being tested.
    """
    src = _read(source)
    start = src.index(signature)
    open_brace = src.index("{", start)
    depth = 0
    for i in range(open_brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace : i + 1]
    raise AssertionError(f"unbalanced braces after {signature}")
