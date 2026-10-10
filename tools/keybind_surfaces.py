#!/usr/bin/env python3
"""Item 17 fix pass 1 F1, fix pass 2 H1: the binding-surface oracle.

Every player-visible string that depends on a binding, and every member that
reads a binding, is ENUMERATED FROM ITS SOURCES, not matched against a
vocabulary, and every one carries its own disposition. Nothing takes a
disposition by default and no file is exempt.

1. STRINGS. The universe is:
     H  the i18n extractor's own harvest (tools/i18n_extract.py
        harvest_source) run over EVERY plugin/*.cs - not only the
        extractor's FILES list - plus the shop snapshot;
     C  every key of the four I18nCatalogues blocks nothing harvests;
     V  every expected-English OCCURRENCE of GameLocaleCatalogues: one row
        per table, path and ordinal (a path repeated in one table keeps an
        ordinal), its identity the hash of all five - table, path, ordinal,
        expected English and translation. One locale's occurrence changed
        beneath an unchanged path is a new id: red until dispositioned, and
        its old row goes stale.
   Each id has exactly one row in tools/keybind_surfaces.tsv (code, note):
     P  a template whose placeholder is fed by a binding producer
     K  a key / mouse / cap name a producer returns
     F  names only inputs that cannot be rebound (FIXED_KEYS)
     G  a vanilla game prompt that names a binding; the payload names the
        site that overrides it, which must be a display reader of the
        readers manifest or one of its consumers (section 3)
     D  a Controls row's "Recommended: the default." line naming that row's
        default key as the default
     O  a catalogue key nothing harvests (never rendered)
     N  names no input binding
   and its note is EITHER a rule the oracle derives and re-checks on every
   run, OR a review by name:
     rule:P   fed by a producer site                       (code P)
     rule:K   harvested only inside producers              (code K)
     rule:O   a catalogue-only key                         (code O)
     rule:N1  code N and ALL of: no input word (CANDIDATE) in the text - for
              a V row in its expected English AND its translation; not fed
              by a producer; not returned by one; and no harvest site inside
              a binding-dependent member (a producer, a member that calls a
              producer, or a reader whose role is display or producer)
     rev:<digest> <payload>   codes F, G, D and N; and K for a msgid a
              producer returns that ANOTHER site also renders (one msgid,
              one translation, serving the key face and the other label:
              payload shared:<the other use>). <digest> is the hash
              of the row's DISPLAY ROLE: an H row's text plus every harvest
              site (file, member, helper, and whether that member is
              binding-dependent); a V row's five-part identity. A new site,
              a site whose member becomes binding-dependent, or any change of
              text makes the review stale (red) until it is done again.
   An undispositioned id, a row for an id that no longer exists, a row with
   no rule and no review, a rule the derivation contradicts, and a stale
   review are each FATAL. A new hardcoded hint is red the moment it is
   written, whatever words it uses: it is a new id.

2. CODE SITES. Every call of a binding producer (the face functions, the cap
   helpers, the board role) outside the producers themselves, by file,
   enclosing member and producer, must be in tools/keybind_surfaces_sites.tsv,
   and every manifest row must still exist. The template a site feeds is read
   from the innermost I18n.TrF around it, or declared in the manifest when the
   value travels through a variable. The P rows must EQUAL the templates the
   sites feed; the K rows must equal the strings harvested only inside
   producers.

3. READERS. Every member of every plugin file that reads a binding ROOT is a
   row of tools/keybind_surfaces_readers.tsv - per member, occurrence-counted
   and content-addressed:
     file, member (Name#k when a file has k same-named members), the number
     of root reads, the digest of the member's text (comments stripped,
     literals kept, whitespace collapsed; "(file scope)" reads digest their
     own lines), the role (producer, display, input, registry, rules, log,
     selftest), the consumers a display row reaches the player through
     ("via": members that must exist and call it, their text in the digest
     too; "self" when it renders itself) and a note.
   The ROOTS are the registry field Keybinds.bound; every value-returning
   member (method or property) of class Keybinds that reads a root, derived
   to a fixed point - the visible ones are roots for every other file,
   qualified, and inside class Keybinds every reference counts; and the
   tables that turn a binding into a face: KeybindRules.KeyIds, MouseIds,
   GlyphFor and BoardCapRole. There is NO whole-file exemption. A new reader,
   a count or digest that differs (a display read added inside a reviewed
   member), a stale row, a producer not marked producer, and a display row
   whose consumers do not call it are each FATAL.

Every P key must be in all four catalogue blocks with the same placeholders,
and every F payload's keys must be in FIXED_KEYS and occur in the string.

WHAT IT CANNOT SEE (the residual): display text the extractor does not
harvest - a literal rendered without I18n.Tr or a harvested helper, text
composed at run time from fragments, a key name produced by an implicit
ToString of a KeyCode; a binding value carried through a parameter or a
field into a member that reads no root itself (the reader that read it is
the row, and a display row names its consumers); and a manifest "feeds"
declaration, which is reviewed, not proven.

USAGE
    python tools/keybind_surfaces.py check [--tree T]
    python tools/keybind_surfaces.py readers [--tree T]   # census, manifest shape
    python tools/keybind_surfaces.py review [--tree T]    # the rows a review must cover
    python tools/keybind_surfaces.py candidates | sites [--tree T]
Exit 0 green, 1 red, 2 usage.
"""
from __future__ import annotations

import argparse
import collections
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
READERS_TSV = os.path.join(HERE, "keybind_surfaces_readers.tsv")
CODES = ("P", "K", "F", "G", "D", "O", "N")
RULES = {"P": "P", "K": "K", "O": "O", "N1": "N"}      # rule -> the code it derives
REVIEWABLE = ("F", "G", "D", "K", "N")   # K only when another site shares the msgid (section 4)
ROLES = ("producer", "display", "input", "registry", "rules", "log", "selftest")
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

# the registry and the face tables
REGISTRY_FILE, REGISTRY_CLASS, REGISTRY_FIELD = "Keybinds.cs", "Keybinds", "bound"
RULES_FILE = "KeybindRules.cs"
FACE_TABLES = ("KeyIds", "MouseIds", "GlyphFor", "BoardCapRole")
FACE_QUAL = re.compile(r"\bKeybindRules\s*\.\s*(?:%s)\b" % "|".join(FACE_TABLES))
FACE_UNQ = re.compile(r"(?<![\w.])(?:%s)\b" % "|".join(FACE_TABLES))
# a word before a name that makes it an expression, never a declaration
NOT_A_TYPE = {"return", "yield", "await", "throw", "else", "case", "in", "out", "ref", "is", "as", "new",
              "typeof", "nameof", "when", "goto", "default", "checked", "unchecked", "lock", "using"}

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


def ws(s):
    return re.sub(r"\s+", " ", s).strip()


def mask_code(src, keep_literals=False):
    """Length-preserving copy of a C# source with comments blanked and, unless
    `keep_literals`, literal TEXT blanked too; the code inside interpolation
    holes is KEPT: in $"<b>{I18n.TrF("x {0}", NativeUI.KeybindRowFace(r))}</b>"
    the call and its arguments stay visible (their own string literals blanked
    in turn), so a producer call or a binding-root read inside a hole is
    enumerated like any other. The extractor's _mask_cs blanks a whole
    interpolated string, hole code included, which is right for its brace and
    signature reading and blind for this oracle's site and reader scans.
    Newlines survive, so an offset into the result is an offset into `src`."""
    out = list(src)
    n = len(src)

    def blank(a, b):
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    def blank_lit(a, b):
        if not keep_literals:
            blank(a, b)

    def string(q, verbatim, interp):
        """q is the opening quote; returns the index after the closing one."""
        j = q + 1
        lit = j
        while j < n:
            ch = src[j]
            if not verbatim and ch == "\\":
                j += 2
                continue
            if ch == '"':
                if verbatim and j + 1 < n and src[j + 1] == '"':
                    j += 2
                    continue
                blank_lit(lit, j)
                return j + 1
            if interp and ch == "{":
                if j + 1 < n and src[j + 1] == "{":
                    j += 2
                    continue
                blank_lit(lit, j + 1)
                e = code(j + 1, True)
                blank_lit(e, e + 1)
                j = e + 1
                lit = j
                continue
            if not verbatim and ch == "\n":
                blank_lit(lit, j)
                return j
            j += 1
        blank_lit(lit, n)
        return n

    def code(i, hole):
        """Scan code from i; in a hole, return the index of its closing brace."""
        depth = 0
        while i < n:
            c = src[i]
            nx = src[i + 1] if i + 1 < n else ""
            nx2 = src[i + 2] if i + 2 < n else ""
            if c == "/" and nx == "/":
                j = src.find("\n", i)
                j = n if j < 0 else j
                blank(i, j)
                i = j
            elif c == "/" and nx == "*":
                j = src.find("*/", i + 2)
                j = n if j < 0 else j + 2
                blank(i, j)
                i = j
            elif c == "'":
                j = i + 1
                j += 2 if j < n and src[j] == "\\" else 1
                k = src.find("'", j)
                k = n if k < 0 else k
                blank_lit(i + 1, k)
                i = k + 1
            elif c == '"' or (c in "@$" and nx == '"') or (c in "@$" and nx in "@$" and nx2 == '"'):
                q = src.index('"', i)
                pre = src[i:q]
                i = string(q, "@" in pre, "$" in pre)
            elif c.isalnum() or c == "_":
                j = i
                while j < n and (src[j].isalnum() or src[j] == "_"):
                    j += 1
                i = j      # an identifier ending in @ or $ is not a prefix
            else:
                if hole:
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        if depth == 0:
                            return i
                        depth -= 1
                i += 1
        return n

    code(0, False)
    return "".join(out)


class Tree:
    def __init__(self, root):
        self.root = root
        self.plugin = os.path.join(root, "plugin")
        self.ext = _load("i18n_extract_f1", os.path.join(root, "tools", "i18n_extract.py"))
        # the masks are pure functions of the text; every pass reuses them
        self.ext._mask_cs = functools.lru_cache(maxsize=None)(self.ext._mask_cs)
        # the site and reader scans read code inside interpolation holes too
        self.mask = functools.lru_cache(maxsize=None)(mask_code)
        self.strip = functools.lru_cache(maxsize=None)(lambda s: mask_code(s, True))
        self.src = {}
        for p in sorted(glob.glob(os.path.join(self.plugin, "*.cs"))):
            self.src[os.path.basename(p)] = self.ext.lf(io.open(p, encoding="utf-8", newline="").read())
        self._members = {}

    def members(self, fn):
        if fn not in self._members:
            self._members[fn] = _members(self, fn)
        return self._members[fn]


# -- members: methods (the extractor's signature) and properties ------------

Member = collections.namedtuple("Member", "start end name name_at header kind")
PROP = re.compile(
    r"(?<![\w.])(?:(?:public|private|protected|internal|static|override|virtual|sealed|new|abstract)\s+)+"
    r"([\w<>\[\],.?]+)\s+(\w+)\s*(\{|=>)")
NOT_PROP_TYPE = {"class", "struct", "interface", "enum", "record", "namespace", "delegate", "event"}


def _members(t, fn):
    src = t.src[fn]
    masked = t.ext._mask_cs(src)
    out = []
    for m in t.ext._SIG.finditer(masked):
        opener = m.end() - len(m.group(2))
        if m.group(2) == "{":
            end = t.ext._block_end(masked, opener)
        else:
            end = masked.find(";", opener)
            end = len(masked) if end < 0 else end + 1
        out.append(Member(m.start(), end, m.group(1), m.start(1), masked[m.start():m.start(1)], "method"))
    for m in PROP.finditer(masked):
        if m.group(1) in NOT_PROP_TYPE:
            continue
        opener = m.end() - len(m.group(3))
        if m.group(3) == "{":
            end = t.ext._block_end(masked, opener)
        else:
            end = masked.find(";", opener)
            end = len(masked) if end < 0 else end + 1
        out.append(Member(m.start(), end, m.group(2), m.start(2), masked[m.start():m.start(2)], "property"))
    out.sort()
    return out


def member_ids(mem):
    """start -> "Name", or "Name#k" (1-based, source order) when the file has
    several members of that name."""
    seen = collections.Counter(m.name for m in mem)
    k = collections.Counter()
    ids = {}
    for m in mem:
        k[m.name] += 1
        ids[m.start] = m.name if seen[m.name] == 1 else "%s#%d" % (m.name, k[m.name])
    return ids


def enclosing(mem, ids, pos):
    best = None
    for m in mem:
        if m.start <= pos < m.end and (best is None or m.start > best.start):
            best = m
    return (ids[best.start], best) if best else ("(file scope)", None)


def base(mid):
    return mid.split("#")[0]


def class_span(t, fn, name):
    masked = t.ext._mask_cs(t.src[fn])
    hits = list(re.finditer(r"\bclass\s+%s\b" % re.escape(name), masked))
    if len(hits) != 1:
        raise SystemExit("FATAL: class %s found %d times in %s" % (name, len(hits), fn))
    ob = masked.index("{", hits[0].end())
    return hits[0].start(), t.ext._block_end(masked, ob)


# -- roots and readers ------------------------------------------------------

def _is_declaration(masked, p, tok_len):
    """A field or property declaration of the token at p: a type word before
    it, `=`, `;`, `{` or `=>` after it."""
    before = re.search(r"([\w\]>?]+)\s+$", masked[max(0, p - 80):p])
    if not before or before.group(1) in NOT_A_TYPE:
        return False
    return re.match(r"\s*(?:=(?![=>])|;|\{|=>)", masked[p + tok_len:p + tok_len + 8]) is not None


def registry_accessors(t):
    """name -> visible, for every value-returning member of the registry
    class that reads the registry field or another accessor (fixed point)."""
    fn = REGISTRY_FILE
    if fn not in t.src:
        raise SystemExit("FATAL: %s missing" % fn)
    masked = t.mask(t.src[fn])
    a0, z0 = class_span(t, fn, REGISTRY_CLASS)
    mem = [m for m in t.members(fn) if a0 <= m.start < z0]
    names = {REGISTRY_FIELD}
    acc = {}
    while True:
        pat = re.compile(r"(?<![\w.])(?:%s)\b" % "|".join(sorted(map(re.escape, names), key=len, reverse=True)))
        grew = False
        for m in mem:
            if m.name in acc or (m.kind == "method" and re.search(r"\bvoid\s*$", m.header)):
                continue
            body_from = m.name_at + len(m.name)
            if any(h.start() >= body_from for h in pat.finditer(masked, m.start, m.end)):
                acc[m.name] = bool(re.search(r"\b(internal|public)\b", m.header)) and \
                    not re.search(r"\bprivate\b", m.header)
                names.add(m.name)
                grew = True
        if not grew:
            return acc


def root_reads(t, acc):
    """{(file, member id): [positions]} - every root read in every plugin file."""
    visible = sorted((n for n, v in acc.items() if v), key=len, reverse=True)
    qual = FACE_QUAL.pattern
    if visible:
        qual += r"|\b%s\s*\.\s*(?:%s)\b" % (REGISTRY_CLASS, "|".join(map(re.escape, visible)))
    QUAL = re.compile(qual)
    UNQ_REG = re.compile(r"(?<![\w.])(?:%s)\b" % "|".join(
        map(re.escape, sorted([REGISTRY_FIELD] + list(acc), key=len, reverse=True))))
    a0, z0 = class_span(t, REGISTRY_FILE, REGISTRY_CLASS)
    out = {}
    for fn, src in t.src.items():
        masked = t.mask(src)
        mem = t.members(fn)
        ids = member_ids(mem)
        names_at = {m.name_at for m in mem}
        hits = {}
        for h in QUAL.finditer(masked):
            hits[h.start()] = h.end() - h.start()
        unq = []
        if fn == REGISTRY_FILE:
            unq = [h for h in UNQ_REG.finditer(masked) if a0 <= h.start() < z0]
        elif fn == RULES_FILE:
            unq = list(FACE_UNQ.finditer(masked))
        # an enum member that shares a root's name declares a constant
        enums = [(e.start(), t.ext._block_end(masked, e.end() - 1))
                 for e in re.finditer(r"\benum\s+\w+\s*(?::\s*\w+\s*)?\{", masked)]
        for h in unq:
            if h.start() in names_at or _is_declaration(masked, h.start(), h.end() - h.start()) \
                    or any(a <= h.start() < b for a, b in enums):
                continue
            hits.setdefault(h.start(), h.end() - h.start())
        for p in sorted(hits):
            mid, _ = enclosing(mem, ids, p)
            out.setdefault((fn, mid), []).append(p)
    return out


def member_text(t, fn, mid, positions=None):
    """The content a reader row is addressed by: the member's text with
    comments stripped and literals kept, whitespace collapsed; for "(file
    scope)", the stripped lines of its root reads."""
    src = t.src[fn]
    stripped = t.strip(src)
    if mid == "(file scope)":
        lines = []
        for p in positions or []:
            a = stripped.rfind("\n", 0, p) + 1
            b = stripped.find("\n", p)
            lines.append(ws(stripped[a:len(stripped) if b < 0 else b]))
        return "\n".join(lines)
    mem = t.members(fn)
    ids = member_ids(mem)
    for m in mem:
        if ids[m.start] == mid:
            return ws(stripped[m.start:m.end])
    return None


def resolve_member(t, fn, ref):
    """A via entry: "Member" in the reader's own file, or "File.cs:Member"."""
    if ":" in ref:
        fn, ref = ref.split(":", 1)
    if fn not in t.src:
        return None, None
    mem = t.members(fn)
    ids = member_ids(mem)
    hits = [m for m in mem if ids[m.start] == ref]
    return (fn, hits[0]) if len(hits) == 1 else (fn, None)


def reader_digest(t, fn, mid, positions, via):
    parts = [member_text(t, fn, mid, positions) or ""]
    for v in via:
        if v == "self":
            continue
        vfn, m = resolve_member(t, fn, v)
        parts.append("%s:%s=%s" % (vfn, v, ws(t.strip(t.src[vfn])[m.start:m.end]) if m else "(missing)"))
    return kid("\x1e".join(parts))


def read_readers(path):
    rows, probs = {}, []
    if not os.path.exists(path):
        return rows, ["readers manifest %s missing" % path]
    for n, line in enumerate(io.open(path, encoding="utf-8").read().split("\n"), 1):
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) < 7 or not f[2].isdigit() or not re.fullmatch(r"[0-9a-f]{16}", f[3]):
            probs.append("readers line %d malformed: %r" % (n, line[:80]))
            continue
        via = [x for x in f[5].split(",") if x and x != "-"]
        if (f[0], f[1]) in rows:
            probs.append("readers line %d: %s:%s twice" % (n, f[0], f[1]))
        rows[(f[0], f[1])] = (int(f[2]), f[3], f[4], via, f[6])
    return rows, probs


# -- strings ----------------------------------------------------------------

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
GAME_TABLE = re.compile(r"\bDictionary<string,\s*string\[\]>\s+(\w+)\s*=\s*new\s+Dictionary<string,\s*string\[\]>\s*\{")
GAME_ENTRY = re.compile(
    r'^[ \t]*\["((?:[^"\\]|\\.)*)"\][ \t]*=[ \t]*new\[\][ \t]*\{[ \t]*"((?:[^"\\]|\\.)*)"[ \t]*,[ \t]*'
    r'"((?:[^"\\]|\\.)*)"[ \t]*\},?[ \t]*$', re.M)


def catalogue(t):
    cat = t.src["I18nCatalogues.cs"]
    parts = cat.split("private static readonly Dictionary<string, string> ")[1:]
    if [p[:2] for p in parts] != list(LOCS):
        raise SystemExit("FATAL: I18nCatalogues blocks %s" % [p[:2] for p in parts])
    return {p[:2]: {t.ext.unescape(m.group(1)): t.ext.unescape(m.group(2)) for m in ENTRY.finditer(p)} for p in parts}


def vanilla(t):
    """[(id, table, path, ordinal, english, translation)] - every occurrence
    of every GameLocaleCatalogues table, in source order. Every entry line of
    a table must parse (a line the parser cannot read is FATAL, never
    skipped), and every table initializer in the file is read."""
    fn = "GameLocaleCatalogues.cs"
    src = t.src.get(fn, "")
    masked = t.ext._mask_cs(src)
    out = []
    tables = list(GAME_TABLE.finditer(masked))
    if len(re.findall(r"=\s*new\s+Dictionary<string,\s*string\[\]>", masked)) != len(tables):
        raise SystemExit("FATAL: %s has a table initializer the oracle cannot read" % fn)
    for tm in tables:
        ob = tm.end() - 1
        end = t.ext._block_end(masked, ob)
        block = src[ob:end]
        lines = [l for l in block.split("\n") if l.strip().startswith('["')]
        entries = list(GAME_ENTRY.finditer(block))
        if len(entries) != len(lines):
            raise SystemExit("FATAL: %s table %s: %d entry lines, %d parsed" % (fn, tm.group(1), len(lines), len(entries)))
        seen = collections.Counter()
        for e in entries:
            path, eng, tr = (t.ext.unescape(e.group(g)) for g in (1, 2, 3))
            seen[path] += 1
            o = seen[path] - 1
            i = kid("V\x1f%s\x1f%s\x1f%d\x1f%s\x1f%s" % (tm.group(1), path, o, eng, tr))
            out.append((i, tm.group(1), path, o, eng, tr))
    return out


def universe(t):
    """id -> (origin, text, sites); a V row's text is
    "V:<table>:<path>#<ordinal> = <english> | <translation>"."""
    hs = harvested(t)
    blocks = catalogue(t)
    u = {}
    for k, s in hs.items():
        u[kid(k)] = ("H", k, s)
    for L in LOCS:
        for k in blocks[L]:
            if kid(k) not in u:
                u[kid(k)] = ("C", k, set())
    vrows = {}
    for i, table, path, o, eng, tr in vanilla(t):
        if i in u:
            raise SystemExit("FATAL: V occurrence id collision %s" % i)
        u[i] = ("V", "V:%s:%s#%d = %s | %s" % (table, path, o, eng, tr), set())
        vrows[i] = (table, path, o, eng, tr)
    return u, blocks, vrows


def producer_spans(t):
    spans = {}
    for fn, name in PRODUCERS:
        if fn not in t.src:
            raise SystemExit("FATAL: producer file %s missing" % fn)
        hits = [(a, b) for a, b, n in t.ext.method_index(t.src[fn]) if n == name]
        if len(hits) != 1:
            raise SystemExit("FATAL: producer %s.%s found %d times" % (fn, name, len(hits)))
        spans[(fn, name)] = hits[0]
    return spans


def trf_calls(t, fn):
    """[(start, end, [template keys])] for every I18n.TrF call in a file."""
    src = t.src[fn]
    masked = t.mask(src)
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
        masked = t.mask(src)
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
            enclosing_calls = [c for c in calls if c[0] <= pos < c[1]]
            tmpl = set(max(enclosing_calls, key=lambda c: c[0])[2]) if enclosing_calls else set()
            key = (fn, t.ext.enclosing_method(mi, pos), m.group(2))
            rec = sites.setdefault(key, [0, set()])
            rec[0] += 1
            rec[1].update(tmpl)
    return sites


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
REV = re.compile(r"rev:([0-9a-f]{16}) (\S.*)$")


class State:
    """Everything one check derived from a tree."""

    def __init__(self, root):
        self.t = t = Tree(root)
        self.u, self.blocks, self.vrows = universe(t)
        self.spans = producer_spans(t)
        self.found = code_sites(t, self.spans)
        self.fed = set()
        for k, (n, tm) in self.found.items():
            self.fed.update(kid(x) for x in tm)
        self.prod_methods = {(fn[:-3], name) for fn, name in PRODUCERS}
        self.k_auto = {i for i, (o, text, s) in self.u.items()
                       if o == "H" and s and all((st, me) in self.prod_methods for st, me, _ in s)}
        self.k_any = {i for i, (o, text, s) in self.u.items()
                      if o == "H" and any((st, me) in self.prod_methods for st, me, _ in s)}
        self.acc = registry_accessors(t)
        self.reads = root_reads(t, self.acc)

    def add_manifest_sites(self, man):
        for k, (n, feeds, _) in man.items():
            if k in self.found:
                self.fed.update(feeds)

    def binding_dependent(self, readers_manifest):
        bdm = set(self.prod_methods)
        bdm |= {(fn[:-3], me) for (fn, me, _) in self.found}
        for (fn, mid), row in readers_manifest.items():
            if (fn, mid) in self.reads and row[2] in ("display", "producer"):
                bdm.add((fn[:-3], base(mid)))
                if mid == "(file scope)" or any(
                        m.kind == "property" and m.name == base(mid) for m in self.t.members(fn)):
                    bdm.add((fn[:-3], "(file scope)"))
        self.bdm = bdm
        return bdm

    def role_digest(self, i):
        o, text, sites = self.u[i]
        if o == "V":
            return kid("V\x1f%s\x1f%s\x1f%d\x1f%s\x1f%s" % self.vrows[i])
        parts = sorted("%s|%s|%s|%s" % (st, me, kd, "B" if (st, me) in self.bdm else "-") for st, me, kd in sites)
        return kid("%s\x1f%s\x1f%s" % (o, text, "\x1e".join(parts)))

    def n1(self, i):
        """(holds, why not)."""
        o, text, sites = self.u[i]
        if o == "C":
            return False, "a catalogue-only key is O"
        if o == "V":
            table, path, ordn, eng, tr = self.vrows[i]
            for what, s in (("expected English", eng), ("translation", tr)):
                m = CANDIDATE.search(s)
                if m:
                    return False, "input word %r in the %s" % (m.group(0), what)
            return True, ""
        m = CANDIDATE.search(text)
        if m:
            return False, "input word %r" % m.group(0)
        if i in self.fed:
            return False, "fed by a producer"
        if i in self.k_auto:
            return False, "returned by a producer"
        b = sorted(s for s in sites if (s[0], s[1]) in self.bdm)
        if b:
            return False, "harvested in binding-dependent %s.%s" % (b[0][0], b[0][1])
        return True, ""


def check(root=REPO, disp_path=None, sites_path=None, verbose=True, readers_path=None):
    st = State(root)
    t, u, blocks = st.t, st.u, st.blocks
    disp, problems = read_disp(disp_path or os.path.join(root, "tools", "keybind_surfaces.tsv"))
    man, p2 = read_sites(sites_path or os.path.join(root, "tools", "keybind_surfaces_sites.tsv"))
    problems += p2
    rman, p3 = read_readers(readers_path or os.path.join(root, "tools", "keybind_surfaces_readers.tsv"))
    problems += p3

    # 1. every id dispositioned, every disposition live
    for i, (origin, text, _) in sorted(u.items()):
        if i not in disp:
            problems.append("UNDISPOSITIONED %s %s %r" % (i, origin, text[:90]))
    for i in sorted(set(disp) - set(u)):
        problems.append("STALE disposition %s %s %r" % (i, disp[i][0], disp[i][2][:60]))

    # 2. code sites == manifest; P == the templates they feed
    found = st.found
    for k, (n, tm) in sorted(found.items()):
        if k not in man:
            problems.append("NEW producer site %s:%s calls %s (%d)" % (k[0], k[1], k[2], n))
        elif man[k][0] != n:
            problems.append("site %s:%s %s count %d, manifest %d" % (k[0], k[1], k[2], n, man[k][0]))
    for k in sorted(set(man) - set(found)):
        problems.append("STALE site %s:%s %s" % k)
    st.add_manifest_sites(man)
    fed = st.fed
    p_set = {i for i, d in disp.items() if d[0] == "P" and i in u}
    for i in sorted(p_set - fed):
        problems.append("P %s %r is fed by no producer site" % (i, u[i][1][:70]))
    for i in sorted(fed - p_set):
        what = u[i][1][:70] if i in u else "(not harvested)"
        problems.append("template %s %r is fed by a producer but not dispositioned P" % (i, what))

    # K: every string harvested only inside producers is K (rule:K); a K row
    # outside that set must still be returned by a producer - a msgid that
    # another site also renders, reviewed by name in section 4
    k_auto = st.k_auto
    k_set = {i for i, d in disp.items() if d[0] == "K" and i in u}
    for i in sorted(k_auto - k_set):
        problems.append("K %s %r is returned by a producer but dispositioned %s" % (i, u[i][1][:60], disp.get(i, ("?",))[0]))
    for i in sorted(k_set - st.k_any):
        problems.append("K %s %r is returned by no producer" % (i, u[i][1][:60]))

    # 3. readers: per member, counted and content-addressed, no exemption
    reads = st.reads
    prod_set = set(PRODUCERS)
    for k, pos in sorted(reads.items()):
        fn, mid = k
        if k not in rman:
            problems.append("NEW binding reader %s:%s (%d root reads) is not in the readers manifest" % (fn, mid, len(pos)))
            continue
        cnt, dg, role, via, note = rman[k]
        if cnt != len(pos):
            problems.append("reader %s:%s reads %d roots, manifest %d" % (fn, mid, len(pos), cnt))
        now = reader_digest(t, fn, mid, pos, via)
        if now != dg:
            problems.append("READER CHANGED %s:%s content %s, manifest %s: review its role again" % (fn, mid, now, dg))
        if role not in ROLES:
            problems.append("reader %s:%s role %r unknown" % (fn, mid, role))
        if ((fn, base(mid)) in prod_set) != (role == "producer"):
            problems.append("reader %s:%s role %s, producer %s" % (fn, mid, role, (fn, base(mid)) in prod_set))
        if role == "display":
            if not via:
                problems.append("display reader %s:%s names no consumer (via, or self)" % (fn, mid))
            for v in via:
                if v == "self":
                    continue
                vfn, m = resolve_member(t, fn, v)
                if m is None:
                    problems.append("display reader %s:%s consumer %s not found once" % (fn, mid, v))
                elif not re.search(r"(?<![\w])%s\s*\(" % re.escape(base(mid)),
                                   t.mask(t.src[vfn])[m.start:m.end]):
                    problems.append("display reader %s:%s consumer %s does not call it" % (fn, mid, v))
        if not note.strip():
            problems.append("reader %s:%s has no review note" % (fn, mid))
    for k in sorted(set(rman) - set(reads)):
        problems.append("STALE reader %s:%s" % k)

    # 4. every row's note: a rule the derivation agrees with, or a live review
    bdm = st.binding_dependent(rman)
    display_sites = set()   # a G row's overriding site must be one of these
    for k, row in rman.items():
        if k in reads and row[2] == "display":
            display_sites.add(base(k[1]))
            display_sites.update(v for v in row[3] if v != "self")
    tally = collections.Counter()
    for i, (code, note, _) in sorted(disp.items()):
        if i not in u:
            continue
        origin, text = u[i][0], u[i][1]
        if note.startswith("rule:"):
            r = note[5:].split(" ")[0]
            tally["rule:" + r] += 1
            if r not in RULES:
                problems.append("%s %s rule %r unknown" % (code, i, r))
            elif RULES[r] != code:
                problems.append("%s %s carries rule:%s, which derives %s" % (code, i, r, RULES[r]))
            elif r == "P" and i not in fed:
                problems.append("P %s rule:P but no producer site feeds it: %r" % (i, text[:60]))
            elif r == "K" and i not in k_auto:
                problems.append("K %s rule:K but it is not harvested only inside producers: %r" % (i, text[:60]))
            elif r == "O" and origin != "C":
                problems.append("O %s rule:O but it is harvested (%s): %r" % (i, origin, text[:60]))
            elif r == "N1":
                ok, why = st.n1(i)
                if not ok:
                    problems.append("N %s rule:N1 does not hold (%s): %r" % (i, why, text[:70]))
        elif note.startswith("rev:"):
            m = REV.match(note)
            tally["rev:" + code] += 1
            if not m:
                problems.append("%s %s review note malformed: %r" % (code, i, note[:60]))
                continue
            if code not in REVIEWABLE:
                problems.append("%s %s is reviewed, but %s is derived (rule:%s)" % (code, i, code, code))
                continue
            now = st.role_digest(i)
            if m.group(1) != now:
                problems.append("REVIEW STALE %s %s: display role digest %s, reviewed %s: %r"
                                % (code, i, now, m.group(1), text[:70]))
            payload = m.group(2)
            if code == "F":
                keys = [k for k in payload.replace("fixed:", "").split(" ")[0].split(",") if k]
                if not payload.startswith("fixed:") or not keys:
                    problems.append("F %s payload must be fixed:<keys>" % i)
                for k in keys:
                    if k not in FIXED_KEYS:
                        problems.append("F %s names %r, not a fixed input" % (i, k))
                    elif k not in text:
                        problems.append("F %s names %r but the string does not" % (i, k))
            elif code == "K":
                if i in k_auto:
                    problems.append("K %s is harvested only inside producers: it takes rule:K, not a review" % i)
                if not payload.startswith("shared:"):
                    problems.append("K %s payload must be shared:<the other use>" % i)
            elif code == "G":
                site = payload.split(" ")[0].split(".")[-1]
                if not re.fullmatch(r"\w+", site or "-"):
                    problems.append("G %s payload must name the overriding site" % i)
                elif not any(re.search(r"\b%s\s*\(" % re.escape(site), s) for s in t.src.values()):
                    problems.append("G %s names site %r that does not exist" % (i, site))
                elif site not in display_sites:
                    problems.append("G %s names site %r, which is no display reader and no consumer of one" % (i, site))
            elif code == "D":
                sites_of = u[i][2]
                if not payload.startswith("default:") or not text.startswith("Recommended: the default.") \
                        or not sites_of or any(me != "KeybindRowRecommended" for _, me, _ in sites_of):
                    problems.append("D %s is not a KeybindRowRecommended default line: %r" % (i, text[:60]))
        else:
            tally["none"] += 1
            problems.append("%s %s has no rule and no review: no row takes a disposition by default: %r"
                            % (code, i, text[:70]))
        # catalogue placement, whatever the note
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

    counts = {c: sum(1 for i, d in disp.items() if d[0] == c and i in u) for c in CODES}
    roles = collections.Counter(rman[k][2] for k in reads if k in rman)
    summary = "universe=%d (H=%d C=%d V=%d) dispositions=%d %s notes[%s] sites=%d fed=%d readers=%d [%s] accessors=%d bdm=%d" % (
        len(u), sum(1 for x in u.values() if x[0] == "H"), sum(1 for x in u.values() if x[0] == "C"),
        sum(1 for x in u.values() if x[0] == "V"), len(disp), " ".join("%s=%d" % (c, counts[c]) for c in CODES),
        " ".join("%s=%d" % kv for kv in sorted(tally.items())), len(found), len(fed), len(reads),
        " ".join("%s=%d" % kv for kv in sorted(roles.items())), len(st.acc), len(bdm))
    return problems, summary, (t, u, found, disp)


def _readers_rows(st, rman):
    rows = []
    for (fn, mid), pos in sorted(st.reads.items()):
        old = rman.get((fn, mid))
        via = old[3] if old else []
        role = old[2] if old else "?"
        note = old[4] if old else ""
        rows.append((fn, mid, len(pos), reader_digest(st.t, fn, mid, pos, via), role,
                     ",".join(via) or "-", note, pos))
    return rows


def main(argv=None):
    try:   # V rows carry their translations; a cp1252 console must not end the run
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("check", "candidates", "sites", "readers", "review"))
    ap.add_argument("--tree", default=REPO)
    a = ap.parse_args(argv)
    if a.mode == "check":
        problems, summary, _ = check(a.tree)
        for p in problems[:200]:
            print("[f1] " + p)
        if len(problems) > 200:
            print("[f1] ... %d more" % (len(problems) - 200))
        print("[f1] %s %s problems=%d" % ("GREEN" if not problems else "RED", summary, len(problems)))
        return 0 if not problems else 1
    st = State(a.tree)
    if a.mode == "sites":
        for k, (n, tm) in sorted(st.found.items()):
            print("\t".join([k[0], k[1], k[2], str(n), ",".join(sorted(kid(x) for x in tm)) or "-"]))
        return 0
    if a.mode == "candidates":
        for i, (o, text, s) in sorted(st.u.items(), key=lambda kv: kv[1][1]):
            if CANDIDATE.search(text):
                print("%s\t%s\t%s" % (i, o, text.replace("\n", "\\n")[:400]))
        return 0
    rman, _ = read_readers(os.path.join(a.tree, "tools", "keybind_surfaces_readers.tsv"))
    if a.mode == "readers":
        # the census in the manifest's shape (roles, via and notes carried
        # from the manifest when the row exists), then each read's line
        for fn, mid, n, dg, role, via, note, pos in _readers_rows(st, rman):
            print("\t".join([fn, mid, str(n), dg, role, via, note]))
        for fn, mid, n, dg, role, via, note, pos in _readers_rows(st, rman):
            src = st.t.strip(st.t.src[fn])
            for p in pos:
                a0 = src.rfind("\n", 0, p) + 1
                b0 = src.find("\n", p)
                print("#READ %s:%s L%d %s" % (fn, mid, src.count("\n", 0, p) + 1, ws(src[a0:b0])[:200]))
        return 0
    # review: every row a rule cannot derive, with the digest a review records
    man, _ = read_sites(os.path.join(a.tree, "tools", "keybind_surfaces_sites.tsv"))
    st.add_manifest_sites(man)
    st.binding_dependent(rman)
    for i, (o, text, s) in sorted(st.u.items(), key=lambda kv: kv[1][1]):
        if o == "C" or i in st.fed or i in st.k_auto:
            continue
        ok, why = st.n1(i)
        if ok:
            continue
        sites = ";".join(sorted("%s.%s%s" % (x[0], x[1], "*" if (x[0], x[1]) in st.bdm else "") for x in s)) or "-"
        print("%s\t%s\t%s\t%s\t%s" % (i, st.role_digest(i), why, sites, text.replace("\t", " ").replace("\n", "\\n")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
