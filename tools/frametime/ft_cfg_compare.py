# ft_cfg_compare.py <pre-image cfg> <sitting cfg>: VR6's RESTORED KIND for com.competitiverounds.mod.cfg (ruling
# R6-A3.11.41 (2)/(3), W32b). Read-only; prints ONE line and exits:
#   0  "RESTORED-KIND comment lines differ: <hunks>"  - only comment lines differ; every other line (sections, keys
#      with their values, blank lines, line endings, the BOM) is byte-identical and in the same order. Each hunk names
#      the key line the changed comment lines sit above ("[Section] Key", or "end of file"), never a value.
#   1  "NOT-RESTORED-KIND: <reasons>"  - a key added, a key removed, a value changed, the order of keys, a section,
#      a blank line, a line ending or the BOM differs (or the two files are byte-identical: nothing to restore).
#   2  "REFUSED: <why>"  - a file unreadable, not UTF-8, or a line that is no kind of line of the file's grammar.
# THE LINES (R6-A3.11.48 M2): the file is cut into lines as .NET File.ReadAllLines cuts it, at CR LF, at LF and at
# a lone CR; a terminator at the end of the file starts no further line. Each line keeps its terminator, so a changed
# line ending still differs. A key written after a lone CR is its own KEY line, not part of a comment.
# THE FILE'S GRAMMAR (the BepInEx 5 ConfigFile reader, which takes each line trimmed of white space): an empty line;
# a COMMENT line (starts with "#"); a SECTION line ("[" ... "]"); a KEY line (holds "="; the key is the text before
# the first "=", trimmed). The reader skips any other line without a word; here such a line is REFUSED (exit 2).
# The caller (ft_vm_restore.sh) counts the restored kind only on exit 0 with exactly this one line; everything else
# fails VR6, which ends HELD. Values are never printed.
import sys
import re
import difflib

LINE_END = re.compile(rb"\r\n|\r|\n")

def lines_of(path):
    raw = open(path, "rb").read()
    out, start = [], 0
    for m in LINE_END.finditer(raw):
        out.append(raw[start:m.end()])
        start = m.end()
    if start < len(raw):
        out.append(raw[start:])
    return raw, out

def kind(b, first):
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        return None, None
    if first and t.startswith("﻿"):
        t = t[1:]
    s = t.strip()
    if s == "":
        return "blank", s
    if s.startswith("#"):
        return "comment", s
    if s.startswith("[") and s.endswith("]"):
        return "section", s[1:-1].strip()
    if "=" in s:
        return "key", s.split("=", 1)[0].strip()
    return None, s

def norm(b):
    return b

def classify(path, tag):
    raw, ls = lines_of(path)
    kinds, keys, sec = [], [], ""
    for i, b in enumerate(ls):
        k, s = kind(b, i == 0)
        if k is None:
            print("REFUSED: line %d of the %s cfg is no kind of line of the file's grammar (not empty, comment, section or key)" % (i + 1, tag))
            sys.exit(2)
        if k == "section":
            sec = s
        kinds.append((k, sec, s))
        if k == "key":
            keys.append((sec, s))
    return raw, ls, kinds, keys

def main():
    if len(sys.argv) != 3:
        print("REFUSED: usage ft_cfg_compare.py <pre-image cfg> <sitting cfg>")
        sys.exit(2)
    try:
        ra, la, ka, keya = classify(sys.argv[1], "pre-image")
        rb, lb, kb, keyb = classify(sys.argv[2], "sitting")
    except OSError as e:
        print("REFUSED: unreadable (%s)" % e.__class__.__name__)
        sys.exit(2)
    if ra == rb:
        print("NOT-RESTORED-KIND: the two files are byte-identical (nothing differs)")
        sys.exit(1)
    na = [norm(b) for b, k in zip(la, ka) if k[0] != "comment"]
    nb = [norm(b) for b, k in zip(lb, kb) if k[0] != "comment"]
    if na == nb and ra.startswith(b"\xef\xbb\xbf") == rb.startswith(b"\xef\xbb\xbf"):
        hunks = []
        sm = difflib.SequenceMatcher(None, la, lb, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                continue
            above = "end of file"
            for j in range(j2, len(lb)):
                if kb[j][0] == "key":
                    above = "[%s] %s" % (kb[j][1], kb[j][2])
                    break
            hunks.append("%d removed, %d added above %s" % (i2 - i1, j2 - j1, above))
        print("RESTORED-KIND comment lines differ: " + "; ".join(hunks))
        sys.exit(0)
    why = []
    sa, sb = set(keya), set(keyb)
    for k in keya:
        if k not in sb:
            why.append("key removed [%s] %s" % k)
    for k in keyb:
        if k not in sa:
            why.append("key added [%s] %s" % k)
    va = {}
    for b, k in zip(la, ka):
        if k[0] == "key":
            va[(k[1], k[2])] = b.rstrip(b"\r\n")
    for b, k in zip(lb, kb):
        if k[0] == "key" and (k[1], k[2]) in va and va[(k[1], k[2])] != b.rstrip(b"\r\n"):
            why.append("key line changed (value or spacing) [%s] %s" % (k[1], k[2]))
    common_a = [k for k in keya if k in sb]
    common_b = [k for k in keyb if k in sa]
    if common_a != common_b:
        why.append("the order of the keys differs")
    if [k[2] for k in ka if k[0] == "section"] != [k[2] for k in kb if k[0] == "section"]:
        why.append("the sections differ")
    if ra.startswith(b"\xef\xbb\xbf") != rb.startswith(b"\xef\xbb\xbf"):
        why.append("the BOM differs")
    if not why:
        why.append("a blank line or a line ending differs outside the comment lines")
    print("NOT-RESTORED-KIND: " + "; ".join(why)[:900])
    sys.exit(1)

main()
