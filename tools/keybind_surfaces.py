#!/usr/bin/env python3
"""Item 17 fix pass 1 F1: the binding-surface oracle.

Every player-visible string that depends on a binding is ENUMERATED FROM
ITS SOURCES, not matched against a vocabulary. The oracle is the union of
three enumerations, each total over what it reads:

1. HARVESTED STRINGS. The i18n extractor's own harvest (tools/i18n_extract.py
   harvest_source) run over EVERY plugin/*.cs - not only the extractor's
   FILES list - plus the shop snapshot, every key of the four I18nCatalogues
   blocks and every expected-English entry of GameLocaleCatalogues. Each one
   must carry exactly one disposition in tools/keybind_surfaces.tsv:
     P  a template whose placeholder is fed by a binding producer
     K  a key / mouse / cap name a producer returns
     F  names only inputs that cannot be rebound (the note lists them)
     G  a vanilla game prompt that names a binding; the note names the site
        that overrides it
     D  a Controls row's "Recommended: the default." line naming that
        row's default key as the default
     O  a catalogue key nothing harvests (never rendered)
     N  names no input binding
   A harvested string with no disposition, or a disposition for a string
   that no longer exists, is FATAL. A new hardcoded hint is therefore red
   the moment it is written, whatever words it uses.
2. CODE SITES. Every call of a binding producer (the face functions, the
   cap helpers, the board role) outside the producers themselves, by file,
   enclosing method and producer, must be in tools/keybind_surfaces_sites.tsv,
   and every manifest row must still exist. The template a site feeds is
   read from the innermost I18n.TrF around it, or declared in the manifest
   when the value travels through a variable. The P dispositions must EQUAL
   the templates the sites feed; the K dispositions must equal the strings
   harvested only inside producers.
3. ROOTS. Every method in the plugin that reads a binding root (the key and
   mouse name tables, the glyph table, the bound registry, the board role)
   is either a producer or a declared non-display reader (logs, config,
   self-tests). A new reader is FATAL.

Every P key must be in all four catalogue blocks with the same
placeholders, and every F note's keys must be in FIXED_KEYS and occur in
the string.

WHAT IT CANNOT SEE (the residual): display text the extractor does not
harvest - a literal rendered without I18n.Tr or a harvested helper, text
composed at run time from fragments, a key name produced by an implicit
ToString of a KeyCode - and a manifest "feeds" declaration, which is
reviewed, not proven. The N dispositions that predate this oracle were
assigned with a review aid (the `candidates` mode lists every string with
an input word for reading); the rest default to N.

USAGE
    python tools/keybind_surfaces.py check
    python tools/keybind_surfaces.py candidates      # review aid
    python tools/keybind_surfaces.py draft --out F   # refuses to overwrite
Exit 0 green, 1 red, 2 usage.
"""
from __future__ import annotations

import argparse
import functools
import glob
import hashlib
import importlib.util
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DISP = os.path.join(HERE, "keybind_surfaces.tsv")
SITES_TSV = os.path.join(HERE, "keybind_surfaces_sites.tsv")
CODES = ("P", "K", "F", "G", "D", "O", "N")
LOCS = ("ES", "RU", "UK", "SV")

# (file, method) - each returns a binding face, a cap or a board role
PRODUCERS = (
    ("NativeUI.Keybinds.cs", "KeybindKeyName"),
    ("NativeUI.Keybinds.cs", "KeybindMouseName"),
    ("NativeUI.Keybinds.cs", "KeybindFace"),
    ("NativeUI.Keybinds.cs", "KeybindRowFace"),
    ("NativeUI.Keybinds.cs", "KeybindOverlayCap"),
    ("NativeUI.Keybinds.cs", "KeybindSemanticCap"),
    ("NativeUI.Keybinds.cs", "KbMoveAndJumpFaces"),
    ("InfoViz.cs", "Cap"),
    ("InfoViz.cs", "MoveCaps"),
    ("InfoViz.cs", "Fill"),
    ("Keybinds.cs", "BoardCapRole"),
)
def CLASS_OF_FILE(fn):
    """The class an unqualified call in this file resolves to (NativeUI is
    partial across NativeUI*.cs)."""
    if fn == "NativeUI.cs" or fn.startswith("NativeUI."):
        return "NativeUI"
    return fn[:-3]


PRODUCER_KEYS = {(CLASS_OF_FILE(fn), name) for fn, name in PRODUCERS}

# tokens that read a binding (the roots the producers stand on)
ROOTS = re.compile(r"\bKeybindRules\s*\.\s*(KeyIds|MouseIds|GlyphFor|BoardCapRole)\b|\bKeybinds\s*\.\s*(Bound|BoundSnapshot|BoardCapRole)\s*\(")
# (file, method): readers of a root that render nothing to a player
NON_DISPLAY = (
    ("KeybindRules.cs", "*"),            # the Unity-free rules and their self-test
    ("Keybinds.cs", "*"),                # the registry, its config and its in-game self-test
)
# inputs that are not rebindable: a string may name these as plain text.
# Escape and Enter are reserved (KeybindRules rule 2), F5 is the permanent
# menu rescue (rule 3), B adds a practice bot in a lobby and F8 opens the
# game's own character editor - none of them is a row.
FIXED_KEYS = ("Esc", "Escape", "ESC", "Enter", "ENTER", "enter", "F5", "F8", "B")
CANDIDATE = re.compile(
    r"(?i:\b(press(?:ing)?|hold(?:ing)?|tap|click(?:s|ing)?|keys?|keyboard|buttons?|mouse|wheel|bind(?:s|ing)?|"
    r"bound|rebind\w*|hotkey|shortcut|controls?|esc|escape|enter|space(?:bar)?|tab|shift|ctrl|alt|lmb|rmb)\b)"
    r"|\bF\d{1,2}\b|\[[A-Z]\]|\b[WQETMBSD]\b|\bWASD\b")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def kid(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


class Tree:
    def __init__(self, root):
        self.root = root
        self.plugin = os.path.join(root, "plugin")
        self.ext = _load("i18n_extract_f1", os.path.join(root, "tools", "i18n_extract.py"))
        # the mask is a pure function of the text; every pass reuses it
        self.ext._mask_cs = functools.lru_cache(maxsize=None)(self.ext._mask_cs)
        self.src = {}
        for p in sorted(glob.glob(os.path.join(self.plugin, "*.cs"))):
            self.src[os.path.basename(p)] = self.ext.lf(io.open(p, encoding="utf-8", newline="").read())


def harvested(t):
    """key -> set of (stem, method, kind), over every plugin file + shop."""
    found, sites = {}, {}
    cwd_ext = t.ext
    old = cwd_ext.REPO, cwd_ext.PLUGIN
    cwd_ext.REPO, cwd_ext.PLUGIN = t.root, t.plugin
    try:
        f0, s0 = cwd_ext.extract()
    finally:
        cwd_ext.REPO, cwd_ext.PLUGIN = old
    found.update(f0)
    for k, v in s0.items():
        sites.setdefault(k, set()).update(v)
    for fn, src in t.src.items():
        if fn in cwd_ext.FILES:
            continue
        cwd_ext.harvest_source(fn, src, found, sites)
    return sites


ENTRY = re.compile(r'^            \["((?:[^"\\]|\\.)*)"\] = "((?:[^"\\]|\\.)*)",$', re.M)
GAME_ENTRY = re.compile(r'^\s*\["((?:[^"\\]|\\.)*)"\]\s*=\s*new\[\]\s*\{\s*"((?:[^"\\]|\\.)*)"', re.M)


def catalogue(t):
    cat = t.src["I18nCatalogues.cs"]
    parts = cat.split("private static readonly Dictionary<string, string> ")[1:]
    if [p[:2] for p in parts] != list(LOCS):
        raise SystemExit("FATAL: I18nCatalogues blocks %s" % [p[:2] for p in parts])
    return {p[:2]: {t.ext.unescape(m.group(1)): t.ext.unescape(m.group(2)) for m in ENTRY.finditer(p)} for p in parts}


def vanilla(t):
    out = {}
    for m in GAME_ENTRY.finditer(t.src.get("GameLocaleCatalogues.cs", "")):
        out["V:" + t.ext.unescape(m.group(1))] = t.ext.unescape(m.group(2))
    return out


def universe(t):
    """id -> (origin, text, sites)."""
    hs = harvested(t)
    blocks = catalogue(t)
    u = {}
    for k, s in hs.items():
        u[kid(k)] = ("H", k, s)
    for L in LOCS:
        for k in blocks[L]:
            if kid(k) not in u:
                u[kid(k)] = ("C", k, set())
    for vk, eng in vanilla(t).items():
        u[kid(vk)] = ("V", vk + " = " + eng, set())
    return u, blocks


def methods_of(t, fn):
    return t.ext.method_index(t.src[fn])


def producer_spans(t):
    spans = {}
    for fn, name in PRODUCERS:
        if fn not in t.src:
            raise SystemExit("FATAL: producer file %s missing" % fn)
        hits = [(a, b) for a, b, n in methods_of(t, fn) if n == name]
        if len(hits) != 1:
            raise SystemExit("FATAL: producer %s.%s found %d times" % (fn, name, len(hits)))
        spans[(fn, name)] = hits[0]
    return spans


def trf_calls(t, fn):
    """[(start, end, [template keys])] for every I18n.TrF call in a file."""
    src = t.src[fn]
    masked = t.ext._mask_cs(src)
    out = []
    for m in re.finditer(r"I18n\s*\.\s*TrF\s*\(", masked):
        op = m.end() - 1
        body = t.ext.find_call_body(src, op)
        if not body:
            continue
        args = t.ext.split_top_level_args(body)
        lits = [t.ext.lf(x) for x in t.ext.arg_literals(args[0].strip())] if args else []
        out.append((m.start(), op + len(body) + 2, lits))
    return out


def code_sites(t, spans):
    """{(file, method, producer): [count, set(templates)]} for every producer
    call outside the producers."""
    names = sorted({n for _, n in PRODUCERS}, key=len, reverse=True)
    call = re.compile(r"(?<![\w.])(?:(NativeUI|InfoViz|Keybinds)\s*\.\s*)?(%s)\s*\(" % "|".join(names))
    sites = {}
    for fn, src in t.src.items():
        masked = t.ext._mask_cs(src)
        mi = t.ext.method_index(src)
        calls = None
        for m in call.finditer(masked):
            pos = m.start(2)
            owner = m.group(1) or CLASS_OF_FILE(fn)
            if (owner, m.group(2)) not in PRODUCER_KEYS:
                continue   # a same-named method of another class
            inside = [k for k, (a, b) in spans.items() if k[0] == fn and a <= pos < b]
            if inside:
                continue
            # the declaration itself
            before = masked[max(0, pos - 60):pos]
            if re.search(r"\b(string|int|Color|bool)\s+$", before):
                continue
            if calls is None:
                calls = trf_calls(t, fn)
            enclosing = [c for c in calls if c[0] <= pos < c[1]]
            tmpl = set(max(enclosing, key=lambda c: c[0])[2]) if enclosing else set()
            key = (fn, t.ext.enclosing_method(mi, pos), m.group(2))
            rec = sites.setdefault(key, [0, set()])
            rec[0] += 1
            rec[1].update(tmpl)
    return sites


def root_readers(t, spans):
    out = set()
    for fn, src in t.src.items():
        masked = t.ext._mask_cs(src)
        mi = t.ext.method_index(src)
        for m in ROOTS.finditer(masked):
            meth = t.ext.enclosing_method(mi, m.start())
            if any(k[0] == fn and a <= m.start() < b for k, (a, b) in spans.items()):
                continue
            if (fn, "*") in NON_DISPLAY or (fn, meth) in NON_DISPLAY:
                continue
            out.add((fn, meth))
    return out


def read_disp(path):
    rows = {}
    if not os.path.exists(path):
        return rows, ["dispositions file %s missing" % path]
    probs = []
    for n, line in enumerate(io.open(path, encoding="utf-8").read().split("\n"), 1):
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) < 3 or f[1] not in CODES:
            probs.append("tsv line %d malformed: %r" % (n, line[:80]))
            continue
        if f[0] in rows:
            probs.append("tsv line %d: id %s twice" % (n, f[0]))
        rows[f[0]] = (f[1], f[2] if len(f) > 2 else "", f[3] if len(f) > 3 else "")
    return rows, probs


def read_sites(path):
    rows = {}
    probs = []
    if not os.path.exists(path):
        return rows, ["sites manifest %s missing" % path]
    for n, line in enumerate(io.open(path, encoding="utf-8").read().split("\n"), 1):
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) < 5:
            probs.append("sites line %d malformed" % n)
            continue
        feeds = set(x for x in f[4].split(",") if x and x != "-")
        rows[(f[0], f[1], f[2])] = (int(f[3]), feeds, f[5] if len(f) > 5 else "")
    return rows, probs


PH = re.compile(r"\{\d+(?::[^}]*)?\}")


def check(root=REPO, disp_path=None, sites_path=None, verbose=True):
    t = Tree(root)
    u, blocks = universe(t)
    spans = producer_spans(t)
    disp, problems = read_disp(disp_path or os.path.join(root, "tools", "keybind_surfaces.tsv"))
    man, p2 = read_sites(sites_path or os.path.join(root, "tools", "keybind_surfaces_sites.tsv"))
    problems += p2

    # 1. every harvested string dispositioned, every disposition live
    for i, (origin, text, _) in sorted(u.items()):
        if i not in disp:
            problems.append("UNDISPOSITIONED %s %s %r" % (i, origin, text[:90]))
    for i in sorted(set(disp) - set(u)):
        problems.append("STALE disposition %s %s %r" % (i, disp[i][0], disp[i][2][:60]))

    # 2. code sites == manifest; P == the templates they feed
    found = code_sites(t, spans)
    for k, (n, tm) in sorted(found.items()):
        if k not in man:
            problems.append("NEW producer site %s:%s calls %s (%d)" % (k[0], k[1], k[2], n))
        elif man[k][0] != n:
            problems.append("site %s:%s %s count %d, manifest %d" % (k[0], k[1], k[2], n, man[k][0]))
    for k in sorted(set(man) - set(found)):
        problems.append("STALE site %s:%s %s" % k)
    fed = set()
    for k, (n, tm) in found.items():
        fed.update(kid(x) for x in tm)
        if k in man:
            fed.update(man[k][1])
    p_set = {i for i, d in disp.items() if d[0] == "P" and i in u}
    for i in sorted(p_set - fed):
        problems.append("P %s %r is fed by no producer site" % (i, u[i][1][:70]))
    for i in sorted(fed - p_set):
        what = u[i][1][:70] if i in u else "(not harvested)"
        problems.append("template %s %r is fed by a producer but not dispositioned P" % (i, what))

    # K == strings harvested only inside producers
    prod_methods = {(fn[:-3], name) for fn, name in PRODUCERS}
    k_auto = {i for i, (o, text, s) in u.items() if o == "H" and s and all((st, me) in prod_methods for st, me, _ in s)}
    k_set = {i for i, d in disp.items() if d[0] == "K" and i in u}
    for i in sorted(k_auto - k_set):
        problems.append("K %s %r is returned by a producer but dispositioned %s" % (i, u[i][1][:60], disp.get(i, ("?",))[0]))
    for i in sorted(k_set - k_auto):
        problems.append("K %s %r is not harvested only inside producers" % (i, u[i][1][:60]))

    # 3. roots
    for fn, meth in sorted(root_readers(t, spans)):
        problems.append("NEW binding reader %s:%s is neither a producer nor declared non-display" % (fn, meth))

    # P in every locale, placeholders kept; O only for catalogue-only; F notes
    for i, (code, note, _) in sorted(disp.items()):
        if i not in u:
            continue
        origin, text = u[i][0], u[i][1]
        if code == "P":
            if not PH.search(text):
                problems.append("P %s has no placeholder: %r" % (i, text[:60]))
            for L in LOCS:
                if text not in blocks[L]:
                    problems.append("P %s missing from %s: %r" % (i, L, text[:60]))
                elif sorted(PH.findall(text)) != sorted(PH.findall(blocks[L][text])):
                    problems.append("P %s placeholders differ in %s" % (i, L))
        if code == "O" and origin != "C":
            problems.append("O %s is harvested (%s): %r" % (i, origin, text[:60]))
        if code != "O" and origin == "C":
            problems.append("%s %s is a catalogue-only key; it must be O: %r" % (code, i, text[:60]))
        if code == "F":
            keys = [k for k in note.replace("fixed:", "").split(",") if k]
            if not note.startswith("fixed:") or not keys:
                problems.append("F %s note must be fixed:<keys>" % i)
            for k in keys:
                if k not in FIXED_KEYS:
                    problems.append("F %s names %r, not a fixed input" % (i, k))
                elif k not in text:
                    problems.append("F %s names %r but the string does not" % (i, k))
        if code == "D":
            # a Controls row's recommendation, naming that row's DEFAULT as the default
            sites_of = u[i][2]
            if not text.startswith("Recommended: the default.") or not sites_of or \
                    any(me != "KeybindRowRecommended" for _, me, _ in sites_of):
                problems.append("D %s is not a KeybindRowRecommended default line: %r" % (i, text[:60]))
        if code == "G" and not re.fullmatch(r"\w+(\.\w+)?", note.split(" ")[0] or "-"):
            problems.append("G %s note must name the overriding site" % i)
        if code == "G":
            site = note.split(" ")[0].split(".")[-1]
            if not any(re.search(r"\b%s\s*\(" % re.escape(site), s) for s in t.src.values()):
                problems.append("G %s names site %r that does not exist" % (i, site))

    counts = {c: sum(1 for i, d in disp.items() if d[0] == c and i in u) for c in CODES}
    summary = "universe=%d dispositions=%d %s sites=%d fed=%d" % (
        len(u), len(disp), " ".join("%s=%d" % (c, counts[c]) for c in CODES), len(found), len(fed))
    return problems, summary, (t, u, found, disp)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("check", "candidates", "draft", "sites"))
    ap.add_argument("--tree", default=REPO)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.mode == "check":
        problems, summary, _ = check(a.tree)
        for p in problems[:200]:
            print("[f1] " + p)
        if len(problems) > 200:
            print("[f1] ... %d more" % (len(problems) - 200))
        print("[f1] %s %s problems=%d" % ("GREEN" if not problems else "RED", summary, len(problems)))
        return 0 if not problems else 1
    t = Tree(a.tree)
    u, blocks = universe(t)
    spans = producer_spans(t)
    if a.mode == "sites":
        for k, (n, tm) in sorted(code_sites(t, spans).items()):
            print("\t".join([k[0], k[1], k[2], str(n), ",".join(sorted(kid(x) for x in tm)) or "-"]))
        return 0
    if a.mode == "candidates":
        for i, (o, text, s) in sorted(u.items(), key=lambda kv: kv[1][1]):
            if CANDIDATE.search(text):
                print("%s\t%s\t%s" % (i, o, text.replace("\n", "\\n")[:400]))
        return 0
    if not a.out or os.path.exists(a.out):
        print("draft needs --out to a new file", file=sys.stderr)
        return 2
    found = code_sites(t, spans)
    fed = set()
    for k, (n, tm) in found.items():
        fed.update(kid(x) for x in tm)
    prod_methods = {(fn[:-3], name) for fn, name in PRODUCERS}
    lines = ["# id\tcode\tnote\texcerpt  (tools/keybind_surfaces.py; codes P K F G O N)"]
    for i, (o, text, s) in sorted(u.items(), key=lambda kv: kv[1][1]):
        if o == "C":
            code = "O"
        elif i in fed:
            code = "P"
        elif o == "H" and s and all((st, me) in prod_methods for st, me, _ in s):
            code = "K"
        elif CANDIDATE.search(text):
            code = "?"
        else:
            code = "N"
        ex = re.sub(r"\s+", " ", text)[:60]
        lines.append("%s\t%s\t\t%s" % (i, code, ex))
    io.open(a.out, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print("draft %d rows -> %s" % (len(lines) - 1, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
