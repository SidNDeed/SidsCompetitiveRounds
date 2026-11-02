#!/usr/bin/env python3
"""gate_insert.py: insert format M's gate and outermost span into named methods, leaving every original line as it
was (FORMAT-M-PLAN.md part a; the census and spans of METHOD-V4.md M3, M4). For each spec the method is found by
its class declaration line and, after it, the first line containing the method's signature text; the method's own
braces are the next line holding only "{" and the first later line holding only "}" at that same indentation.
The insertion, all inside #if SCR_FRAMETIME blocks:

    {
    #if SCR_FRAMETIME
        <guard>                       e.g. if (FtCensus.Skip(FtE.HE_p2)) { __state = false; return; }
        bool ftSpan = FtSpan.Open(FtSpan.Hit, FtSpan.Gated);
        try
        {
    #endif
        <original body, unchanged>
    #if SCR_FRAMETIME
        }
        finally { FtSpan.Close(ftSpan); }
    #endif
    }

Each anchor must resolve exactly once and a method already carrying a gate is refused, so a rerun cannot double
it. hunk_check.py then proves the Release and Thunderstore texts unchanged.

Usage: python -I -B gate_insert.py <worktree> <spec.py>; spec.py defines SPECS = [(file, class_line, signature,
guard, component, kind), ...] with file relative to the worktree.
"""
import runpy
import sys

MARK = "#if SCR_FRAMETIME"


def insert(text, class_line, signature, guard, component, kind):
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
    if lines[op + 1].strip() == MARK:
        raise SystemExit("REFUSED: %r already carries a gate" % signature)
    cl = next((i for i in range(op + 1, len(lines)) if lines[i] == ind + "}"), None)
    if cl is None:
        raise SystemExit("REFUSED: no closing brace for %r" % signature)
    body_ind = ind + "    "
    head = [MARK,
            body_ind + guard,
            body_ind + "bool ftSpan = FtSpan.Open(FtSpan.%s, FtSpan.%s);" % (component, kind),
            body_ind + "try",
            body_ind + "{",
            "#endif"]
    tail = [MARK,
            body_ind + "}",
            body_ind + "finally { FtSpan.Close(ftSpan); }",
            "#endif"]
    lines = lines[:op + 1] + head + lines[op + 1:cl] + tail + lines[cl:]
    return nl.join(lines)


def main():
    w, spec = sys.argv[1], sys.argv[2]
    specs = runpy.run_path(spec)["SPECS"]
    files = {}
    for f, class_line, signature, guard, component, kind in specs:
        p = w + "/" + f
        if p not in files:
            files[p] = open(p, encoding="utf-8", newline="").read()
        files[p] = insert(files[p], class_line, signature, guard, component, kind)
    for p, t in files.items():
        open(p, "w", encoding="utf-8", newline="").write(t)
    print("gate_insert: %d methods in %d files" % (len(specs), len(files)))


if __name__ == "__main__":
    main()
