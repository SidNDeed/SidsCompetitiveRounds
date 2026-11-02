#!/usr/bin/env python3
"""mark_insert.py: B3's heavy-operation marks (plugin/FtHeavy.cs; METHOD-V4.md 3.9), each one
#if SCR_FRAMETIME block holding one statement, leaving every original line as it was.

Spec rows (file, class_line, signature, where, statement):
  where "open"          : right after the method's opening "{" line
  where "close"         : right before the method's closing "}" line (the first later line equal to the "{"
                          line's indentation plus "}")
  where "before:<text>" : right before the first line inside the method whose stripped text starts with <text>
The method is found as gate_insert.py finds it (its class line, then the first later line containing the
signature). Every anchor must resolve exactly once and a statement already present in the method is refused,
so a rerun cannot double it. hunk_check.py then proves the Release and Thunderstore texts unchanged.

Usage: python -I -B mark_insert.py <worktree>
"""
import sys

MARK = "#if SCR_FRAMETIME"
CE, CD, IC, SE = ("plugin/CombatEvidence.cs", "plugin/CardDrawEvidence.cs", "plugin/IdentityClockEvidence.cs",
                  "plugin/SeatEvidence.cs")
SPECS = [
    (CE, "internal static class CombatEvidence", "private static void BuildCaptures(bool quitting)", "open",
     "FtHeavy.Mark(FtHeavy.CeBuild);"),
    (SE, "internal static class SeatEvidence", "private static void BuildCaptures(bool quitting)", "open",
     "FtHeavy.Mark(FtHeavy.SeBuild);"),
    (CD, "internal static class CardDrawEvidence", "private static void BuildPending(bool now)", "open",
     "FtHeavy.Mark(FtHeavy.CdBuild);"),
    (IC, "internal static class IdentityClockEvidence", "private static string BuildEnv(Capture c, out string text)",
     "open", "FtHeavy.Mark(FtHeavy.IcBuild);"),
    (SE, "internal static class SeatEvidence", "private static bool Enqueue(string route, string body)", "open",
     "FtHeavy.Mark(FtHeavy.Enqueue);"),
    (SE, "internal static class SeatEvidence", "internal static bool SpoolClosing(string route, string body)", "open",
     "FtHeavy.Mark(FtHeavy.Spool);"),
    (SE, "internal static class SeatEvidence", "private static void Pump(long nowMs)", "open",
     "FtHeavy.Mark(FtHeavy.Pump);"),
    (SE, "internal static class SeatEvidence", "private static void Answer(string route,", "open",
     "FtHeavy.Mark(FtHeavy.Answer);"),
    (SE, "internal static class SeatEvidence", "internal static void StartHashing()", "before:var t = new Thread(HashPending);",
     "FtHeavy.Mark(FtHeavy.HashStart);"),
    (SE, "internal static class SeatEvidence", "internal static void CompleteIdentityNow()", "open",
     "FtHeavy.Mark(FtHeavy.HashNow);"),
    (SE, "internal static class SeatEvidence", "private static void HashPending()", "open", "FtHeavy.HashBegin();"),
    (SE, "internal static class SeatEvidence", "private static void HashPending()", "close", "FtHeavy.HashDone();"),
]


def insert(text, class_line, signature, where, stmt):
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
    if any(ln.strip() == stmt for ln in lines[op:cl]):
        raise SystemExit("REFUSED: %r already carries %r" % (signature, stmt))
    if where == "open":
        at, body_ind = op + 1, ind + "    "
    elif where == "close":
        at, body_ind = cl, ind + "    "
    elif where.startswith("before:"):
        hits = [i for i in range(op + 1, cl) if lines[i].strip().startswith(where[7:])]
        if len(hits) != 1:
            raise SystemExit("REFUSED: %r matched %d times in %r" % (where, len(hits), signature))
        at = hits[0]
        body_ind = lines[at][:len(lines[at]) - len(lines[at].lstrip())]
    else:
        raise SystemExit("REFUSED: unknown where %r" % where)
    lines = lines[:at] + [MARK, body_ind + stmt, "#endif"] + lines[at:]
    return nl.join(lines)


def main():
    w = sys.argv[1]
    files = {}
    for f, class_line, signature, where, stmt in SPECS:
        p = w + "/" + f
        if p not in files:
            files[p] = open(p, encoding="utf-8", newline="").read()
        files[p] = insert(files[p], class_line, signature, where, stmt)
    for p, t in files.items():
        open(p, "w", encoding="utf-8", newline="").write(t)
    print("mark_insert: %d marks in %d files" % (len(SPECS), len(files)))


if __name__ == "__main__":
    main()
