#!/usr/bin/env python3
"""hunk_check.py - the FrameTime source check (FORMAT-M-PLAN.md V2 part d, F09). Stdlib only.

It does not inspect diff hunks; it evaluates the C# preprocessor. For every file under plugin/ that differs between
the base (main) and the lane, it computes the ACTIVE text of each version under each shipping symbol set (Release,
Thunderstore): #if/#elif/#else/#endif evaluated with !, &&, ||, ==, != and parentheses, nested to any depth, #define
and #undef honoured in active regions, inactive regions and directive lines dropped, everything else kept exactly
(comments and whitespace included: strict). The check passes only if, under both symbol sets, the base's and the lane's
active texts are identical for every .cs file (a new file must have an empty active text, a deleted file must have had
one), no other file under plugin/ changed except the csproj, and the csproj changed by exactly the three allowed edits.

Usage:
  python -I -B hunk_check.py --self-test
  python -I -B hunk_check.py --parse-tree <repo> <ref> <symbols>       (every plugin/*.cs at ref must parse)
  python -I -B hunk_check.py <repo> <base> <lane> --release "<defines>" --thunderstore "<defines>"
The defines are the /define: lists from the Csc command lines of the lane's Release and Thunderstore builds (-v:n).
Exit 0 = PASS (or self-test all as expected), 1 = FAIL, 3 = refused (git error, unbalanced or unparsable directive).
"""
import re
import subprocess
import sys

CSPROJ = "plugin/CompetitiveRounds.csproj"
CONF_OLD = "<Configurations>Debug;Release;Thunderstore;G3</Configurations>"
CONF_NEW = "<Configurations>Debug;Release;Thunderstore;G3;FrameTime</Configurations>"
COPY_OLD = "Condition=\"'$(SkipCopyToPlugins)' != 'true' and '$(Configuration)' != 'G3'\""
COPY_NEW = ("Condition=\"'$(SkipCopyToPlugins)' != 'true' and '$(Configuration)' != 'G3'"
            " and '$(Configuration)' != 'FrameTime'\"")
GROUP_OPEN = "  <PropertyGroup Condition=\"'$(Configuration)' == 'FrameTime'\">"
GROUP_CLOSE = "  </PropertyGroup>"


MUTANT = False  # --mutant: a whole chain headed by an SCR_FRAMETIME test is treated as lane-only


class Refuse(Exception):
    pass


# ------------------------------------------------------------------ the preprocessor

_TOK = re.compile(r"\s*(\|\||&&|==|!=|!|\(|\)|[A-Za-z_][A-Za-z0-9_]*)")


def eval_expr(expr, syms):
    toks, pos = [], 0
    expr = expr.split("//", 1)[0].strip()
    while pos < len(expr):
        m = _TOK.match(expr, pos)
        if not m:
            raise Refuse("unparsable directive expression: %r" % expr)
        toks.append(m.group(1))
        pos = m.end()
        while pos < len(expr) and expr[pos].isspace():
            pos += 1
    i = [0]

    def peek():
        return toks[i[0]] if i[0] < len(toks) else None

    def take():
        t = peek()
        i[0] += 1
        return t

    def primary():
        t = take()
        if t == "!":
            return not primary()
        if t == "(":
            v = p_or()
            if take() != ")":
                raise Refuse("unbalanced parentheses: %r" % expr)
            return v
        if t is None or not re.match(r"[A-Za-z_]", t):
            raise Refuse("bad token in %r" % expr)
        return True if t == "true" else False if t == "false" else (t in syms)

    def p_eq():
        v = primary()
        while peek() in ("==", "!="):
            op = take()
            w = primary()
            v = (v == w) if op == "==" else (v != w)
        return v

    def p_and():
        v = p_eq()
        while peek() == "&&":
            take()
            w = p_eq()
            v = v and w
        return v

    def p_or():
        v = p_and()
        while peek() == "||":
            take()
            w = p_and()
            v = v or w
        return v

    if not toks:
        raise Refuse("empty directive expression")
    v = p_or()
    if peek() is not None:
        raise Refuse("trailing tokens in %r" % expr)
    return v


_DIR = re.compile(r"^\s*#\s*(if|elif|else|endif|define|undef|region|endregion|pragma|nullable|line|error|warning)\b(.*)$")


def active_text(text, symbols):
    """The text the compiler sees under the symbol set: active lines only, directive lines dropped."""
    syms = set(symbols)
    stack = []          # per #if: [parent_active, this_branch_active, any_branch_taken]
    active = True
    out = []
    for ln in text.replace("\r\n", "\n").split("\n"):
        m = _DIR.match(ln)
        if not m:
            if active:
                out.append(ln)
            continue
        d, rest = m.group(1), m.group(2)
        if d == "if":
            v = active and eval_expr(rest, syms)
            ft = MUTANT and "SCR_FRAMETIME" in rest
            v = False if ft else v
            stack.append([active, v, v, ft])
            active = v
        elif d == "elif":
            if not stack:
                raise Refuse("#elif without #if")
            parent, _cur, taken, ft = stack[-1]
            v = parent and not taken and eval_expr(rest, syms) and not ft
            stack[-1] = [parent, v, taken or v, ft]
            active = v
        elif d == "else":
            if not stack:
                raise Refuse("#else without #if")
            parent, _cur, taken, ft = stack[-1]
            v = parent and not taken and not ft
            stack[-1] = [parent, v, True, ft]
            active = v
        elif d == "endif":
            if not stack:
                raise Refuse("#endif without #if")
            active = stack.pop()[0]
        elif d in ("define", "undef") and active:
            name = rest.split("//", 1)[0].strip()
            (syms.add if d == "define" else syms.discard)(name)
    if stack:
        raise Refuse("unterminated #if")
    return "\n".join(out)


def csproj_restored(lane_text):
    """The lane's csproj with the three allowed edits undone, or a refusal naming the edit that is missing."""
    t = lane_text.replace("\r\n", "\n")
    if t.count(CONF_NEW) != 1 or t.count(COPY_NEW) != 1 or t.count(GROUP_OPEN) != 1:
        raise ValueError("csproj: the three FrameTime edits are not each present exactly once")
    t = t.replace(CONF_NEW, CONF_OLD).replace(COPY_NEW, COPY_OLD)
    i0 = t.index(GROUP_OPEN + "\n")
    i1 = t.index(GROUP_CLOSE + "\n", i0) + len(GROUP_CLOSE) + 1
    if t[i1:i1 + 1] == "\n":
        i1 += 1
    return t[:i0] + t[i1:]


def compare(files_base, files_lane, sym_sets, csproj_base=None, csproj_lane=None):
    """files_*: {path: text or None (absent)}. Returns (ok, [reason lines])."""
    reasons = []
    for path in sorted(set(files_base) | set(files_lane)):
        a, b = files_base.get(path), files_lane.get(path)
        if a == b:
            continue
        if not path.endswith(".cs"):
            reasons.append("FAIL %s: a non-source file under plugin/ changed" % path)
            continue
        for name, syms in sym_sets:
            ta = active_text(a, syms) if a is not None else ""
            tb = active_text(b, syms) if b is not None else ""
            if ta != tb:
                reasons.append("FAIL %s: active text differs under %s" % (path, name))
    if csproj_base is not None and csproj_lane is not None and csproj_base != csproj_lane:
        try:
            if csproj_restored(csproj_lane) != csproj_base.replace("\r\n", "\n"):
                reasons.append("FAIL %s: a change beyond the three FrameTime edits" % CSPROJ)
        except ValueError as e:
            reasons.append("FAIL %s: %s" % (CSPROJ, e))
    return (not reasons), reasons


# ------------------------------------------------------------------ fixtures (the self-test)

REL = ("TRACE", "RELEASE", "NETSTANDARD2_1")
THU = ("TRACE", "NETSTANDARD2_1", "THUNDERSTORE")
SETS = (("Release", REL), ("Thunderstore", THU))
BASE = "class A {\n    void F() { X(); }\n#if THUNDERSTORE\n    string V() => \"T\";\n#else\n    string V() => \"S\";\n#endif\n}\n"
CSP = ("<Project>\n  <PropertyGroup>\n    " + CONF_OLD + "\n  </PropertyGroup>\n\n"
       "  <Target Name=\"CopyToPlugins\" " + COPY_OLD + ">\n  </Target>\n</Project>\n")
CSP_LANE = ("<Project>\n  <PropertyGroup>\n    " + CONF_NEW + "\n  </PropertyGroup>\n\n" + GROUP_OPEN + "\n"
            "    <DefineConstants>$(DefineConstants);SCR_FRAMETIME</DefineConstants>\n    <Optimize>true</Optimize>\n"
            + GROUP_CLOSE + "\n\n  <Target Name=\"CopyToPlugins\" " + COPY_NEW + ">\n  </Target>\n</Project>\n")


def fx(name, lane_files, expect, base_files=None, csp_lane=None):
    return (name, base_files if base_files is not None else {"plugin/A.cs": BASE}, lane_files, csp_lane, expect)


def tail_block(block):
    """BASE with a block inserted before its final closing brace, every other line untouched."""
    assert BASE.endswith("}\n")
    return BASE[:-2] + block + "}\n"


FIXTURES = [
    fx("new lines inside #if SCR_FRAMETIME", {"plugin/A.cs": BASE.replace(
        "    void F() { X(); }\n", "    void F() { X(); }\n#if SCR_FRAMETIME\n    void Gate() { }\n#endif\n")}, True),
    fx("a split Release line around #if SCR_FRAMETIME", {"plugin/A.cs": BASE.replace(
        "    void F() { X(); }\n", "    void F() { X();\n#if SCR_FRAMETIME\n        Gate();\n#endif\n    }\n")}, False),
    fx("#elif SCR_FRAMETIME section in an existing chain", {"plugin/A.cs": BASE.replace(
        "#else\n", "#elif SCR_FRAMETIME\n    string V() => \"F\";\n#else\n")}, True),
    fx("change in the #else of #if SCR_FRAMETIME", {"plugin/A.cs": BASE.replace(
        "    void F() { X(); }\n", "#if SCR_FRAMETIME\n    void F() { X(); Gate(); }\n#else\n    void F() { X(); Y(); }\n"
        "#endif\n")}, False),
    fx("change inside #if !SCR_FRAMETIME", {"plugin/A.cs": BASE.replace(
        "    void F() { X(); }\n", "#if !SCR_FRAMETIME\n    void F() { X(); Y(); }\n#endif\n")}, False),
    fx("nested #if inside #if SCR_FRAMETIME", {"plugin/A.cs": tail_block(
        "#if SCR_FRAMETIME\n#if THUNDERSTORE\n    int Q;\n#else\n    int R;\n#endif\n#endif\n")}, True),
    fx("a deleted Release line", {"plugin/A.cs": BASE.replace("    void F() { X(); }\n", "")}, False),
    fx("a new file wholly inside #if SCR_FRAMETIME", {"plugin/A.cs": BASE,
                                                      "plugin/FT.cs": "#if SCR_FRAMETIME\nclass FT { }\n#endif\n"}, True),
    fx("a new file with code outside the block", {"plugin/A.cs": BASE,
                                                  "plugin/FT.cs": "using X;\n#if SCR_FRAMETIME\nclass FT { }\n#endif\n"},
       False),
    fx("a deleted file that had active code", {}, False),
    fx("a comment edit outside any block", {"plugin/A.cs": BASE.replace("{ X(); }", "{ X(); } // note")}, False),
    fx("#if SCR_FRAMETIME || THUNDERSTORE", {"plugin/A.cs": tail_block(
        "#if SCR_FRAMETIME || THUNDERSTORE\n    int Q;\n#endif\n")}, False),
    fx("#if SCR_FRAMETIME && THUNDERSTORE (never active when shipping)", {"plugin/A.cs": tail_block(
        "#if SCR_FRAMETIME && THUNDERSTORE\n    int Q;\n#endif\n")}, True),
    fx("#define SCR_FRAMETIME outside any block", {"plugin/A.cs": "#define SCR_FRAMETIME\n" + tail_block(
        "#if SCR_FRAMETIME\n    int Q;\n#endif\n")}, False),
    fx("a non-source file under plugin/ changed", {"plugin/A.cs": BASE, "plugin/data.json": "{}"}, False,
       base_files={"plugin/A.cs": BASE, "plugin/data.json": "[]"}),
    fx("the three csproj edits", {"plugin/A.cs": BASE}, True, csp_lane=CSP_LANE),
    fx("the csproj edits plus a stray change", {"plugin/A.cs": BASE}, False,
       csp_lane=CSP_LANE.replace("<Optimize>true</Optimize>\n" + GROUP_CLOSE + "\n\n",
                                 "<Optimize>true</Optimize>\n" + GROUP_CLOSE + "\n\n  <Foo>1</Foo>\n")),
    fx("only two of the three csproj edits", {"plugin/A.cs": BASE}, False,
       csp_lane=CSP_LANE.replace(COPY_NEW, COPY_OLD)),
    fx("no change at all (identity)", {"plugin/A.cs": BASE}, True),
]


def self_test():
    good = 0
    for name, fb, fl, csp_lane, expect in FIXTURES:
        try:
            ok, why = compare(fb, fl, SETS, CSP, csp_lane if csp_lane is not None else CSP)
        except Refuse as e:
            ok, why = None, ["REFUSED %s" % e]
        hit = ok == expect
        good += hit
        print("  %s %-62s expected %-4s got %s%s" % ("ok  " if hit else "MISS", name, "PASS" if expect else "FAIL",
                                                    "PASS" if ok else "FAIL" if ok is False else "REFUSED",
                                                    "" if ok else " (" + "; ".join(why) + ")"))
    refusals = 0
    for bad in ("#if A\nx\n", "#endif\n", "#if (A\n#endif\n", "#if A &&\n#endif\n"):
        try:
            active_text(bad, ())
        except Refuse:
            refusals += 1
    print("  refusals on malformed directives: %d/4" % refusals)
    ok = good == len(FIXTURES) and refusals == 4
    print("SELF-TEST %d/%d verdicts as expected; %s" % (good, len(FIXTURES), "PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ------------------------------------------------------------------ the real check

def git(repo, *args):
    p = subprocess.run(["git", "-C", repo] + list(args), capture_output=True)
    if p.returncode != 0:
        raise Refuse("git %s: %s" % (" ".join(args), p.stderr.decode("utf-8", "replace").strip()))
    return p.stdout.decode("utf-8")


def show(repo, ref, path):
    p = subprocess.run(["git", "-C", repo, "show", "%s:%s" % (ref, path)], capture_output=True)
    return p.stdout.decode("utf-8") if p.returncode == 0 else None


def parse_tree(repo, ref, symbols):
    files = [f for f in git(repo, "ls-tree", "-r", "--name-only", ref, "--", "plugin/").split("\n")
             if f.endswith(".cs")]
    n = 0
    for f in files:
        active_text(show(repo, ref, f), symbols)
        n += 1
    print("PARSE-TREE %s: %d plugin .cs files parsed under {%s} without a refusal" % (ref, n, ";".join(symbols)))
    return 0


def main(argv):
    try:
        if argv[1:] == ["--self-test"]:
            return self_test()
        if argv[1:] == ["--self-test", "--mutant"]:
            global MUTANT
            MUTANT = True
            print("MUTANT armed: a chain headed by an SCR_FRAMETIME test counts as lane-only (the hunk-shape reading)")
            return self_test()
        if argv[1] == "--parse-tree":
            return parse_tree(argv[2], argv[3], tuple(s for s in argv[4].split(";") if s))
        repo, base, lane = argv[1], argv[2], argv[3]
        rel = tuple(s for s in argv[argv.index("--release") + 1].split(";") if s)
        thu = tuple(s for s in argv[argv.index("--thunderstore") + 1].split(";") if s)
        changed = [ln.split("\t") for ln in git(repo, "diff", "--name-status", "--no-renames", base, lane, "--",
                                                 "plugin/").split("\n") if ln.strip()]
        fb, fl = {}, {}
        for st, path in changed:
            if path == CSPROJ:
                continue
            fb[path] = show(repo, base, path)
            fl[path] = show(repo, lane, path)
        ok, why = compare(fb, fl, (("Release", rel), ("Thunderstore", thu)),
                          show(repo, base, CSPROJ), show(repo, lane, CSPROJ))
        for w in why:
            print("  " + w)
        print("HUNK CHECK %s..%s: %d changed paths; %s" % (base, lane, len(changed), "PASS" if ok else "FAIL"))
        return 0 if ok else 1
    except Refuse as e:
        print("REFUSED: %s" % e)
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
