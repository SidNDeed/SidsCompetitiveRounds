#!/usr/bin/env python3
"""entry_insert.py: format M's variant-only branches at a method's entry or before one named line, each one
#if SCR_FRAMETIME block, leaving every original line as it was (FORMAT-M-PLAN.md V2 part b).

Spec rows (file, class_line, signature, where, [statement lines]):
  where "entry"         : after the method's opening "{" line and after any #if SCR_FRAMETIME ... #endif blocks
                          that immediately follow it (the B3 mark, a span's head), so those still run first
  where "before:<text>" : right before the one line inside the method whose stripped text starts with <text>
  where "pair:<text>"   : the one line inside the method whose stripped text starts with <text> becomes the #else
                          half of an #if SCR_FRAMETIME / #else / #endif pair whose FrameTime half is the statements
The method is found as gate_insert.py finds it. Every anchor must resolve exactly once, and a method whose text
already holds the first statement is refused, so a rerun cannot double it. hunk_check.py then proves the Release
and Thunderstore texts unchanged.

Usage: python -I -B entry_insert.py <worktree> <spec.py>; spec.py defines SPECS.
"""
import runpy
import sys

MARK = "#if SCR_FRAMETIME"


def insert(text, class_line, signature, where, stmts):
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    cls = [i for i, ln in enumerate(lines) if ln.strip() == class_line.strip()]
    if len(cls) != 1:
        raise SystemExit("REFUSED: class line %r matched %d times" % (class_line, len(cls)))
    sig = next((i for i in range(cls[0], len(lines)) if signature in lines[i]), None)
    if sig is None:
        raise SystemExit("REFUSED: signature %r not found after %r" % (signature, class_line))
    op = sig + 1
    if lines[op].strip() != "{":
        raise SystemExit("REFUSED: %r is not followed by a line holding only '{'" % signature)
    ind = lines[op][:len(lines[op]) - len(lines[op].lstrip())]
    cl = next((i for i in range(op + 1, len(lines)) if lines[i] == ind + "}"), None)
    if cl is None:
        raise SystemExit("REFUSED: no closing brace for %r" % signature)
    if any(ln.strip() == stmts[0].strip() for ln in lines[op:cl]):
        raise SystemExit("REFUSED: %r already carries %r" % (signature, stmts[0]))
    if where == "entry":
        at = op + 1
        while lines[at].strip() == MARK:
            end = next(i for i in range(at + 1, cl) if lines[i].strip() == "#endif")
            at = end + 1
        body_ind = ind + "    "
        # inside a span's try the body sits one level deeper than the method's own body
        if at > op + 1 and lines[at - 2].strip() == "{" and lines[at - 3].strip() == "try":
            body_ind = lines[at - 2][:len(lines[at - 2]) - len(lines[at - 2].lstrip())] + "    "
        lines = lines[:at] + [MARK] + [body_ind + s for s in stmts] + ["#endif"] + lines[at:]
    elif where.startswith("before:") or where.startswith("pair:"):
        key = where.split(":", 1)[1]
        hits = [i for i in range(op + 1, cl) if lines[i].strip().startswith(key)]
        if len(hits) != 1:
            raise SystemExit("REFUSED: %r matched %d times in %r" % (where, len(hits), signature))
        at = hits[0]
        body_ind = lines[at][:len(lines[at]) - len(lines[at].lstrip())]
        new = [MARK] + [body_ind + s for s in stmts]
        if where.startswith("before:"):
            lines = lines[:at] + new + ["#endif"] + lines[at:]
        else:
            lines = lines[:at] + new + ["#else", lines[at], "#endif"] + lines[at + 1:]
    else:
        raise SystemExit("REFUSED: unknown where %r" % where)
    return nl.join(lines)


def main():
    w, spec = sys.argv[1], sys.argv[2]
    specs = runpy.run_path(spec)["SPECS"]
    files = {}
    for f, class_line, signature, where, stmts in specs:
        p = w + "/" + f
        if p not in files:
            files[p] = open(p, encoding="utf-8", newline="").read()
        files[p] = insert(files[p], class_line, signature, where, stmts)
    for p, t in files.items():
        open(p, "w", encoding="utf-8", newline="").write(t)
    print("entry_insert: %d branches in %d files" % (len(specs), len(files)))


if __name__ == "__main__":
    main()
