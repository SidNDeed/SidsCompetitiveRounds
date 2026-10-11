#!/usr/bin/env python3
"""Item 17 fix pass 1 F1, fix passes 2, 3 and 4 H1: the binding-surface oracle.

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

4. CALLERS (fix pass 3 H1). A reader row is one member; its VALUE travels on
   to every member that calls it. The callers are DERIVED FROM SOURCE, never
   listed by hand. The followed members are every value-returning reader
   except the registry accessors (class Keybinds' value-returning members
   that read the registry: they ARE roots, so every caller of one is a reader
   row already), every producer, and every pass consumer below. Every
   reference to a followed member's name across plugin/ is an edge to the
   member that encloses it (unqualified inside a type whose chain holds the
   member's own type, by name since NativeUI is partial; qualified by that
   type; and for an instance or extension member at every `.Name`, the
   receiver's type not being resolved - more edges, never fewer;
   declarations, enum members, an assignment target when the member is a
   method (a method cannot be assigned: the name is another member's), and
   the member's own body excluded). Every edge is a row of
   tools/keybind_surfaces_callers.tsv: source, consumer, the number of
   references, the digest of the consumer's text (as for a reader row), a
   class and a note. The class is
     display     the consumer puts the value, or a decision taken on it, in
                 front of the player - a display sink (also a member that
                 returns display text to a path the derivation cannot follow
                 by name, a delegate table or a field: the note says which);
     nondisplay  input, a rules verdict, persistence, logging or self-test -
                 a declared non-display sink (a verdict the player sees only
                 as a fixed sentence that names no binding is a rules
                 verdict: the note says so);
     pass        the consumer returns the value (or one computed from it) to
                 its own callers, which are derived and dispositioned in turn
                 (followed caller to caller); it must return a value;
     producer    the consumer is a binding producer, itself followed.
   A derived edge with no row (REVERSE DISCOVERY: a caller in any file, the
   list never consulted), a row whose edge no longer exists (a caller removed
   or moved), a reference count or consumer digest that differs, a class
   that does not fit, and a row with no note are each FATAL. The DISPLAY-
   REACHABLE set of a followed reader is every display consumer reached
   through pass consumers, with those pass consumers; a display reader's via
   must EQUAL it (so via is derived output, and the reader's digest hashes
   every consumer through which its value reaches the player), and a reader
   of any other role but producer whose value reaches a display consumer is
   FATAL. The summary prints a digest of the whole graph.

5. ATTACHMENT (fix pass 4 H1). Section 4 ends at a display consumer; it does
   not prove that consumer is still attached to anything the player sees.
   Every TERMINAL DISPLAY SINK - the consumer of every derived edge classed
   display, and every display reader that renders itself - must reach a
   declared RENDER ROOT by an attachment chain. The roots are declared once,
   in RENDER_ROOTS (file, member, what it renders); each must resolve to
   exactly one member, and each root's entries (the members that reference
   it, one level) are a root row of tools/keybind_surfaces_attach.tsv,
   counted and content-addressed. A chain is a path from the sink up, of any
   length (fix pass 5: the traversal is COMPLETE and has no hop bound), each
   hop one member referencing the member below it (section 4's reference
   rule), classified by where the reference stands:
     ref       a call or a read;
     delegate  inside a lambda, or the member named as a value (a method
               group): a delegate registration, its context the call or
               field that receives the delegate;
     entry     inside an object, collection or array initializer: a table or
               segment entry, its context the entry path (an object named by
               its Key literal, an array element by its index, the field it
               is assigned to);
     dispatch  inside a switch section with a string label: a string-dispatch
               key. At a declared DISPATCHER (DISPATCHERS: InfoViz's visual
               dispatch, whose keys Seg.V("key") calls register) a dispatch
               hop counts only paired with a REGISTRATION leg: a Seg.V call
               with that literal key (hop kind register, its context the
               segment entry) that is itself attached to a root. A string
               dispatch hop of a chain at any other switch is an
               UNRESOLVED hop.
   A hop is the hash of its kind, its context, its two members and the text
   of the statement or entry that holds it (comments stripped, literals
   kept, whitespace collapsed; never its line). The traversal (traverse)
   starts at every sink and expands every member it reaches, once, until
   every path has ended; one visited set over the whole traversal makes it
   cycle-safe. A path ends at a root, at an UNRESOLVED end - a member
   nothing in the source references that is entered from outside it (a
   Harmony patch method, harmony:File.cs:Class.Member(Target.method); a
   Unity message, unity:...; a member whose name is a string literal,
   reflection:...) or a reference at file scope (field:...) - at a member
   nothing references and nothing enters (unreferenced), at a registration
   member with no registration (unregistered), or at a CYCLE END: a hop
   whose two members lie in one strongly connected component, by which a
   path returns to a member it already holds. The paths of a sink are every
   walk up its recorded hops; there are far too many to list one by one
   (the reference rule over-approximates receivers, so the InfoLibrary
   sinks reach ~1,700 members), so they are manifested LOSSLESSLY as the
   rows they are made of: every hop a hop row (lower, hop digest, upper,
   token), every end an end row, every cycle end a cycle row, and every
   sink a sink row (its members, hops, the digest of its whole subgraph,
   attached or ORPHAN, the roots it reaches). A change to any completed path
   changes a row and the digest of every sink it starts from; the summary
   prints a digest of every row, and the path mode names any one path row
   by row. A sink is ATTACHED when the least fixed point reaches it from a
   root or an UNRESOLVED end (a dispatch hop at a declared dispatcher only
   with its registration member attached). Every UNRESOLVED end is an
   unresolved row with its CONTROL - a pytest node that exists and names it
   - and a note. A traversal that would expand more than ATTACH_BUDGET
   members stops and is TRUNCATED: FATAL, naming the path to each member
   never expanded (a truncated traversal is incomplete, never a dead end).
   FATAL also: a declared root that is not one member; a root whose entries
   changed; a sink not attached (ORPHAN: an orphan is never a silent
   terminal); a derived hop, end or cycle with no row (reverse discovery: a
   sink attached anew, or re-attached under another entry, segment, key or
   caller), named with the path it lies on; a row the source no longer
   derives (a detachment or a move), named with its recorded path; a sink
   row that differs; an UNRESOLVED
   hop with no row, a stale row, or a control that is missing or does not
   name the hop; a dispatcher's binding-key table (KeybindRules.InfoVisual
   .BindingKeys, the keys whose failed build is a repaint failure) that
   differs from the keys whose visual is a display sink; and a consumer
   classed retired (a display consumer detached on purpose, in the callers
   manifest) that anything references again.

Every P key must be in all four catalogue blocks with the same placeholders,
and every F payload's keys must be in FIXED_KEYS and occur in the string.

WHAT IT CANNOT SEE (the residual): display text the extractor does not
harvest - a literal rendered without I18n.Tr or a harvested helper, text
composed at run time from fragments, a key name produced by an implicit
ToString of a KeyCode or of a BindSource (whose string form is the config
token); a binding value carried through a parameter or a
field into a member that reads no root itself (the reader that read it is
the row, and its callers are derived only as far as a returned value goes:
a value a consumer stores in a field, hands to a delegate that is invoked
elsewhere, or passes as an argument is followed no further, and the class
of the edge where it leaves is reviewed, not proven); a caller reached by
reflection, by Harmony's own invocation of a patch, through an interface or
a virtual override, or by an unqualified call from a derived type; and a
manifest "feeds" declaration, which is reviewed, not proven. Section 5's
limits: a root is declared, and only its entries one level up are recorded;
a hop is a reference, not a proven invocation (a delegate registration
proves where the delegate is registered, not that it is invoked; a
condition around a hop is hashed as text, never evaluated); the reference
rule does not resolve the receiver of an instance member, so the traversal
follows more paths than the program can take, never fewer (it is complete
over the reference rule, and every extra path is made of rows whose change
is red, so the manifest moves with an edit to any of the ~1,700 members
those paths cross); a member reached on several paths is expanded once and
its hops recorded once, shared by every path through it; a Seg.V
registration whose key is not a literal
is never paired (it is an UNRESOLVED hop, dispatch-key:..., red until
dispositioned); Harmony's application of a patch at load, a Unity message's
delivery and a reflection call are UNRESOLVED hops whose controls pin their
source, not their run time; and a surface that reads no binding is no sink.

USAGE
    python tools/keybind_surfaces.py check [--tree T]
    python tools/keybind_surfaces.py readers [--tree T]   # census, manifest shape
    python tools/keybind_surfaces.py callers [--tree T]   # derived caller graph, manifest shape
    python tools/keybind_surfaces.py attach [--tree T]    # attachment rows, manifest shape
    python tools/keybind_surfaces.py path SINK M1 ... ROOT [--tree T]   # one path, row by row
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
CALLERS_TSV = os.path.join(HERE, "keybind_surfaces_callers.tsv")
CALLER_CLASSES = ("display", "nondisplay", "pass", "producer", "retired")
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


# -- callers (fix pass 3 H1): derived from source, never hand-listed --------

TYPE_OPEN = re.compile(r"\b(?:class|struct|interface)\s+(\w+)")
ENUM_OPEN = re.compile(r"\benum\s+\w+\s*(?::\s*\w+\s*)?\{")
EXTENSION = re.compile(r"\s*(?:<[^<>()]*>)?\s*\(\s*this\b")


def _types(t, fn):
    """[(name, start, end)]: every class, struct and interface body of fn, in
    source order (an enclosing type before the types nested in it)."""
    cache = t.__dict__.setdefault("_type_spans", {})
    if fn not in cache:
        masked = t.ext._mask_cs(t.src[fn])
        out = []
        for m in TYPE_OPEN.finditer(masked):
            ob = masked.find("{", m.end())
            semi = masked.find(";", m.end())
            if ob < 0 or 0 <= semi < ob:
                continue
            out.append((m.group(1), m.start(), t.ext._block_end(masked, ob)))
        cache[fn] = out
    return cache[fn]


def _enums(t, fn):
    cache = t.__dict__.setdefault("_enum_spans", {})
    if fn not in cache:
        masked = t.mask(t.src[fn])
        cache[fn] = [(e.start(), t.ext._block_end(masked, e.end() - 1)) for e in ENUM_OPEN.finditer(masked)]
    return cache[fn]


def _member_by_id(t, fn, mid):
    if fn not in t.src:
        return None
    mem = t.members(fn)
    ids = member_ids(mem)
    for m in mem:
        if ids[m.start] == mid:
            return m
    return None


def value_returning(m):
    """A property, or a method whose return type is not void."""
    return m.kind == "property" or not re.search(r"\bvoid\s*$", m.header)


def caller_sources(st):
    """{"File.cs:Member": (file, member id, Member)}: the members whose value
    the derivation follows - every value-returning member that reads a root,
    except the value-returning readers of the registry class (they ARE roots:
    every reader of one is a reader row already), and every producer."""
    t = st.t
    a0, z0 = class_span(t, REGISTRY_FILE, REGISTRY_CLASS)
    out = {}
    for fn, mid in st.reads:
        if mid == "(file scope)":
            continue
        m = _member_by_id(t, fn, mid)
        if m is None or not value_returning(m):
            continue
        if fn == REGISTRY_FILE and a0 <= m.start < z0 and m.name in st.acc:
            continue
        out["%s:%s" % (fn, mid)] = (fn, mid, m)
    for pfn, pname in PRODUCERS:
        if pfn not in t.src:
            continue
        mem = t.members(pfn)
        ids = member_ids(mem)
        for m in mem:
            if m.name == pname:
                out["%s:%s" % (pfn, ids[m.start])] = (pfn, ids[m.start], m)
    return out


WORD = re.compile(r"(?<![\w@])\w+")


def _word_index(t, fn):
    """{word: [positions]} of every maximal identifier run in fn's masked
    text that no word character or @ precedes: exactly the positions where
    (?<![\\w@])word\\b matches, found in one pass per file instead of one
    pass per file and name (fix pass 5: the complete attachment traversal
    asks for the references of every member it reaches)."""
    cache = t.__dict__.setdefault("_word_index", {})
    if fn not in cache:
        idx = collections.defaultdict(list)
        for w in WORD.finditer(t.mask(t.src[fn])):
            idx[w.group(0)].append(w.start())
        cache[fn] = dict(idx)
    return cache[fn]


def _member_ids_of(t, fn):
    cache = t.__dict__.setdefault("_member_ids", {})
    if fn not in cache:
        cache[fn] = member_ids(t.members(fn))
    return cache[fn]


def caller_refs(t, fn, mid, m):
    """{(file, consumer id): [positions]}: every reference to member m (id mid
    of fn) by its name across plugin/. Unqualified, a reference counts inside
    a type whose chain holds m's own type (by name: NativeUI is partial across
    files); qualified, `T.Name` counts when T is that type, and every `.Name`
    counts when m is an instance or extension member (the receiver's type is
    not resolved: more edges, never fewer). Not references: a declaration of
    the name (a member, field, local or parameter with an initializer), an
    enum member, an assignment target when m is a method (a method cannot be
    assigned: the name is another member's, e.g. a nested type's field), and
    m's own body."""
    name = m.name
    chain = [n for n, a, b in _types(t, fn) if a <= m.start < b]
    if not chain:
        return {}
    own = chain[-1]
    after = t.ext._mask_cs(t.src[fn])[m.name_at + len(name):m.name_at + len(name) + 200]
    receiver_free = bool(re.search(r"\bstatic\b", m.header)) and not EXTENSION.match(after)
    decls = t.__dict__.setdefault("_decl_at", {})
    out = {}
    for fn2 in sorted(t.src):
        found = _word_index(t, fn2).get(name)
        if not found:
            continue
        masked = t.mask(t.src[fn2])
        mem2 = t.members(fn2)
        ids2 = _member_ids_of(t, fn2)
        if fn2 not in decls:
            decls[fn2] = {x.name_at for x in mem2}
        enums = _enums(t, fn2)
        types2 = _types(t, fn2)
        for p in found:
            if p in decls[fn2] or any(a <= p < b for a, b in enums) or _is_declaration(masked, p, len(name)):
                continue
            if m.kind != "property" and re.match(r"\s*(?:=(?![=>])|[-+*/%&|^]=|\?\?=)", masked[p + len(name):p + len(name) + 8]):
                continue
            q = p - 1
            while q >= 0 and masked[q] in " \t\r\n":
                q -= 1
            if q >= 0 and masked[q] == ".":
                if receiver_free:
                    e = q - 1
                    if e >= 0 and masked[e] == "?":
                        e -= 1
                    while e >= 0 and masked[e] in " \t\r\n":
                        e -= 1
                    s = e
                    while s >= 0 and (masked[s].isalnum() or masked[s] == "_"):
                        s -= 1
                    if masked[s + 1:e + 1] != own:
                        continue
            elif own not in [n for n, a, b in types2 if a <= p < b]:
                continue
            cmid, _ = enclosing(mem2, ids2, p)
            if fn2 == fn and cmid == mid:
                continue
            out.setdefault((fn2, cmid), []).append(p)
    return out


def derive_callers(st, cman):
    """The caller graph {(source key, consumer key): [positions]}, each key
    "File.cs:Member". The sources are caller_sources(st); a consumer the
    callers manifest classes `pass` that returns a value becomes a source in
    turn, so a value is followed caller to caller until every path ends at a
    display sink or a declared non-display sink. Sets st.caller_srcs."""
    t = st.t
    srcs = caller_sources(st)
    graph = {}
    queue = sorted(srcs)
    done = set()
    while queue:
        k = queue.pop(0)
        if k in done:
            continue
        done.add(k)
        fn, mid, m = srcs[k]
        for (fn2, cmid), pos in sorted(caller_refs(t, fn, mid, m).items()):
            ck = "%s:%s" % (fn2, cmid)
            graph[(k, ck)] = pos
            row = cman.get((k, ck))
            if row and row[2] == "pass" and ck not in srcs and cmid != "(file scope)":
                cm = _member_by_id(t, fn2, cmid)
                if cm is not None and value_returning(cm):
                    srcs[ck] = (fn2, cmid, cm)
                    queue.append(ck)
    st.caller_srcs = srcs
    return graph


def display_reach(graph, cman):
    """{source key: set of consumer keys}: the consumers through which the
    source's value reaches the player - every display consumer, and every
    pass consumer from which one is reached, with the consumers on that path."""
    outs = collections.defaultdict(set)
    for s, c in graph:
        outs[s].add(c)
    memo = {}

    def reach(s, path):
        if s in memo:
            return memo[s]
        res = set()
        for c in sorted(outs.get(s, ())):
            row = cman.get((s, c))
            cls = row[2] if row else None
            if cls == "display":
                res.add(c)
            elif cls == "pass" and c not in path:
                sub = reach(c, path | {c})
                if sub:
                    res.add(c)
                    res |= sub
        memo[s] = res
        return res

    return {s: reach(s, {s}) for s in sorted(outs)}


def via_name(reader_file, key):
    """A consumer key as a readers-manifest via entry: "Member" in the
    reader's own file, "File.cs:Member" elsewhere."""
    fn, mid = key.split(":", 1)
    return mid if fn == reader_file else key


def caller_digest(t, key, positions):
    fn, mid = key.split(":", 1)
    return kid(member_text(t, fn, mid, positions) or "")


def read_callers(path):
    rows, probs = {}, []
    if not os.path.exists(path):
        return rows, ["callers manifest %s missing" % path]
    for n, line in enumerate(io.open(path, encoding="utf-8").read().split("\n"), 1):
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) < 6 or ":" not in f[0] or ":" not in f[1] or not f[2].isdigit() \
                or not re.fullmatch(r"[0-9a-f]{16}", f[3]):
            probs.append("callers line %d malformed: %r" % (n, line[:80]))
            continue
        if (f[0], f[1]) in rows:
            probs.append("callers line %d: %s of %s twice" % (n, f[1], f[0]))
        rows[(f[0], f[1])] = (int(f[2]), f[3], f[4], f[5])
    return rows, probs


# -- attachment (fix pass 4 H1) ---------------------------------------------
#
# Section 4 proves a binding value reaches a member that shows it. It does not
# prove that member is still attached to anything the player sees: a display
# sink detached from its render root (its call removed, its table entry or
# segment removed, its dispatch key no longer registered) kept every caller
# row and digest. This pass walks UP from every terminal display sink to a
# declared render root and records every attachment path (section 5 of the
# docstring). Fix pass 5: the walk is a COMPLETE traversal - no hop bound -
# and every path it completes is manifested and hashed through its hops, its
# ends and its cycle hops; a traversal cut short is fatal, never a dead end.

ATTACH_TSV = os.path.join(HERE, "keybind_surfaces_attach.tsv")
# The members one traversal may expand. It is a guard against a runaway
# derivation, not a bound on what is checked: a traversal that reaches it
# stops, records every member it did not expand, and the oracle is RED
# (TRUNCATED, the path to each such member named). The fix-5 tip expands
# about 1,700 members.
ATTACH_BUDGET = 20000
# The render roots, declared once: (file, member, what it puts in front of
# the player). The oracle resolves each to exactly one member and prints its
# line; a root's own entries (the members that reference it) are recorded,
# one level, as the manifest's root rows.
RENDER_ROOTS = (
    ("NativeUI.cs", "SelectInfoArticle",
     "the Info tab's reading pane: an article's text and its visuals (the Controls article and its keyboard guide)"),
    ("NativeUI.cs", "BuildPage", "the menu's page build: every tab's first paint and the Info tab's navigation"),
    ("NativeUI.cs", "RefreshCurrentTab", "the open tab's refresh: the Home chat log, the Shop rows"),
    ("NativeUI.Settings.cs", "SettingsRenderPane",
     "the settings pane: the Controls pane and a setting's read-more article"),
    ("NativeUI.Settings.cs", "SettingsShowExtras", "the settings pane's extras: the chat language note"),
    ("NativeUI.Keybinds.cs", "KeybindPaintAll", "the Controls rows' repaint after a binding revision"),
    ("CompetitiveUI.cs", "DrawUI",
     "the IMGUI frame: chat input, quick chat, dance wheel, input overlay, the tab stats overlay"),
    ("BroadcastHud.cs", "Draw", "the broadcast HUD frame: the action rows, the tab stats strings"),
    ("GameStateWatcher.cs", "PollMatchState", "the match-state poll: the round-start keybind toast"),
    ("Keybinds.cs", "CommitRows", "a binding commit: the join and ready prompts painted again"),
)
# The string dispatchers whose keys the source registers: (dispatcher, the
# member whose literal argument registers a key (file, type, member), the
# table naming the keys whose visual reads a binding (file, field)). A
# dispatch hop at a declared dispatcher counts only when its key is
# registered by a site that is itself attached to a root; a string-keyed
# dispatch anywhere else is an UNRESOLVED hop.
DISPATCHERS = (
    ("InfoViz.cs:Dispatch", ("InfoLibrary.cs", "Seg", "V"), ("KeybindRules.cs", "BindingKeys")),
)
KW_PAREN = frozenset(("if", "for", "foreach", "while", "switch", "using", "lock", "catch", "fixed", "return",
                      "typeof", "nameof", "sizeof", "default", "when", "in", "is", "await", "throw", "checked",
                      "unchecked", "out", "ref", "else"))
BLOCK_WORDS = frozenset(("else", "try", "finally", "do", "get", "set", "init", "add", "remove", "unsafe",
                         "checked", "unchecked"))
UNITY_MESSAGES = frozenset(("Awake", "Start", "Update", "LateUpdate", "FixedUpdate", "OnGUI", "OnEnable",
                            "OnDisable", "OnDestroy", "OnApplicationFocus", "OnApplicationQuit"))
Hop = collections.namedtuple("Hop", "callee consumer kind ctx key pos digest")


def _name_before(masked, j):
    """(name, start): the dotted name ending at or before j (generic
    arguments skipped)."""
    while j >= 0 and masked[j] in " \t\r\n":
        j -= 1
    if j >= 1 and masked[j] == ">" and masked[j - 1] != "=":
        depth = 0
        while j >= 0:
            if masked[j] == ">":
                depth += 1
            elif masked[j] == "<":
                depth -= 1
                if depth == 0:
                    j -= 1
                    break
            j -= 1
        while j >= 0 and masked[j] in " \t\r\n":
            j -= 1
    e = j
    while j >= 0 and (masked[j].isalnum() or masked[j] in "_."):
        j -= 1
    return masked[j + 1:e + 1], j + 1


def _match_back(masked, j, opener, closer):
    depth = 0
    while j >= 0:
        if masked[j] == closer:
            depth += 1
        elif masked[j] == opener:
            depth -= 1
            if depth == 0:
                return j
        j -= 1
    return -1


def _bracket_kind(masked, o):
    """(kind, name) of the bracket opened at o: call, ctor, kw, paren, index,
    init (an object or collection initializer of type name), array, switch
    (a switch statement's block), switchx (a switch expression), lambda (a
    lambda's block) or block."""
    c = masked[o]
    j = o - 1
    while j >= 0 and masked[j] in " \t\r\n":
        j -= 1
    prev = masked[j] if j >= 0 else ""
    if c == "(":
        if prev.isalnum() or prev == "_" or (prev == ">" and masked[j - 1] != "="):
            nm, s = _name_before(masked, j)
            if nm in KW_PAREN:
                return "kw", nm
            before, _ = _name_before(masked, s - 1)
            return ("ctor" if before == "new" else "call"), nm
        return "paren", ""
    if c == "[":
        return "index", ""
    if prev == ")":
        k = _match_back(masked, j, "(", ")")
        nm, s = _name_before(masked, k - 1)
        if nm == "switch":
            return "switch", ""
        if nm in KW_PAREN:
            return "block", nm
        before, _ = _name_before(masked, s - 1)
        return ("init" if before == "new" else "block"), nm
    if prev == ">" and j >= 1 and masked[j - 1] == "=":
        return "lambda", ""
    if prev == "]":
        k = _match_back(masked, j, "[", "]")
        nm, s = _name_before(masked, k - 1)
        if nm == "new":
            return "array", ""
        before, _ = _name_before(masked, s - 1)
        return ("array" if before == "new" else "block"), nm
    if prev.isalnum() or prev == "_" or prev == ">":
        nm, s = _name_before(masked, j)
        if nm == "switch":
            return "switchx", ""
        if nm in BLOCK_WORDS:
            return "block", nm
        before, _ = _name_before(masked, s - 1)
        return ("init" if before == "new" else "block"), nm
    if prev == "=" or prev in ",{(":
        return "array", ""
    return "block", ""


def _open_brackets(masked, a, p):
    """The brackets open at p, scanning from a: [char, open position,
    element index (the separators before p at the bracket's own depth),
    element start], outermost first."""
    stack = []
    i = a
    while i < p:
        c = masked[i]
        if c in "([{":
            stack.append([c, i, 0, i + 1])
        elif c in ")]}":
            if stack:
                stack.pop()
            if c == "}" and stack and stack[-1][0] == "{":
                stack[-1][3] = i + 1
        elif c == "," and stack:
            stack[-1][2] += 1
            stack[-1][3] = i + 1
        elif c == ";" and stack and stack[-1][0] == "{":
            stack[-1][3] = i + 1
        i += 1
    return stack


def _arrow(masked, a, b):
    """Whether a lambda arrow stands in masked[a:b] at that range's own depth."""
    depth = 0
    for i in range(a, b - 1):
        c = masked[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "=" and masked[i + 1] == ">" and depth == 0:
            return True
    return False


def _elem_end(masked, p, stops):
    depth = 0
    i, n = p, len(masked)
    while i < n:
        c = masked[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif depth == 0 and c in stops:
            return i
        i += 1
    return n


def _init_key(t, fn, o):
    """The `Key = "..."` literal of the initializer opened at o, if any."""
    masked = t.mask(t.src[fn])
    strip = t.strip(t.src[fn])
    e = t.ext._block_end(masked, o)
    depth = 0
    for i in range(o + 1, e):
        c = masked[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and c == "K" and not (masked[i - 1].isalnum() or masked[i - 1] == "_"):
            mm = re.match(r'Key\s*=\s*"([^"]*)"', strip[i:i + 200])
            if mm:
                return mm.group(1)
    return None


def _case_labels(t, fn, o, upto):
    """The labels of the switch section that holds upto, in the switch block
    opened at o."""
    masked = t.mask(t.src[fn])
    strip = t.strip(t.src[fn])
    depth = 0
    cur, ended = [], False
    i = o + 1
    while i < upto:
        c = masked[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0 and c == "}":
                ended = True
        elif depth == 0 and c == ";":
            ended = True
        elif depth == 0 and c in "cd" and not (masked[i - 1].isalnum() or masked[i - 1] == "_"):
            mm = re.match(r"(case|default)(?![\w])", masked[i:i + 8])
            if mm:
                w = mm.group(1)
                k = _elem_end(masked, i + len(w), ":")
                lab = ws(strip[i + len(w):k]) if w == "case" else "default"
                if ended:
                    cur, ended = [], False
                cur.append(lab)
                i = k
        i += 1
    return cur


def hop_at(t, fn, cm, p, callee):
    """(kind, ctx, text, key) of the reference at p (inside consumer member cm
    of fn, None at file scope) to the member `callee`:
      dispatch  inside a switch section with a string label (key: the label)
      entry     inside an object, collection or array initializer (a table
                entry; ctx: the path of entries, an object named by its Key)
      delegate  inside a lambda, or the member named as a value (a method
                group): a delegate registration (ctx: where it is registered)
      ref       any other reference
      field     at file scope (a field initializer)
    ctx is the path of enclosing calls, entries and switch sections; text is
    the enclosing statement or entry (comments stripped, literals kept,
    whitespace collapsed)."""
    masked = t.mask(t.src[fn])
    strip = t.strip(t.src[fn])
    if cm is None:
        a = max(masked.rfind(";", 0, p), masked.rfind("}", 0, p), masked.rfind("{", 0, p)) + 1
        e = _elem_end(masked, p, ";")
        mm = re.search(r"(\w+)\s*=(?![=>])", masked[a:p])
        return "field", mm.group(1) if mm else "?", ws(strip[a:e]), None
    fr = _open_brackets(masked, cm.start, p)
    parts, kinds = [], set()
    key, textf, lam = None, None, False
    for n, f in enumerate(fr):
        inner = fr[n + 1][1] if n + 1 < len(fr) else p
        fk, nm = _bracket_kind(masked, f[1])
        arr = _arrow(masked, f[3], inner)
        mark = "=>" if arr else ""
        lam = lam or arr
        if fk == "init":
            k0 = _init_key(t, fn, f[1])
            mm = re.match(r"\s*(\w+)\s*=(?![=>])", masked[f[3]:inner])
            parts.append("%s%s.%s%s" % (nm, "{%s}" % k0 if k0 else "", mm.group(1) if mm else "#%d" % f[2], mark))
            kinds.add("entry")
            textf = (f, ",")
        elif fk == "array":
            nxt = fr[n + 1] if n + 1 < len(fr) else None
            keyed = nxt is not None and _bracket_kind(masked, nxt[1])[0] == "init" and _init_key(t, fn, nxt[1])
            parts.append(("" if keyed else "[%d]" % f[2]) + mark)
            kinds.add("entry")
            textf = (f, ",")
        elif fk in ("call", "ctor"):
            parts.append("%s%s(#%d%s)" % ("new " if fk == "ctor" else "", nm, f[2], mark))
        elif fk == "switch":
            labs = _case_labels(t, fn, f[1], inner)
            parts.append("case " + "|".join(labs))
            lits = [x[1:-1] for x in labs if re.fullmatch(r'"[^"\\]*"', x)]
            if lits:
                kinds.add("dispatch")
                key = lits[0]
            textf = (f, ";")
        elif fk == "switchx":
            mm = re.match(r"\s*(.*?)\s*=>", strip[f[3]:inner], re.S)
            lab = ws(mm.group(1)) if mm else "?"
            parts.append("arm " + lab)
            if re.fullmatch(r'"[^"\\]*"', lab):
                kinds.add("dispatch")
                key = lab[1:-1]
            textf = (f, ",")
        elif fk == "lambda":
            parts.append("=>{}")
            textf = (f, ";")
        elif fk == "block":
            textf = (f, ";")
    after = masked[p + len(callee.name):p + len(callee.name) + 40]
    group = callee.kind == "method" and not re.match(r"\s*(?:<[^<>()]*>)?\s*\(", after)
    if group:
        parts.append("&")
    kind = ("dispatch" if "dispatch" in kinds else "entry" if "entry" in kinds
            else "delegate" if (lam or group) else "ref")
    if textf is None:
        text = ws(strip[cm.start:cm.end])
    else:
        f, stops = textf
        text = ws(strip[f[3]:_elem_end(masked, p, stops)])
    return kind, "/".join(x for x in parts if x), text, key


def _refs(t, key):
    """(member, caller_refs) of a "File.cs:Member" key, cached on the tree."""
    memo = t.__dict__.setdefault("_attach_refs", {})
    if key not in memo:
        fn, mid = key.split(":", 1)
        m = None if mid == "(file scope)" else _member_by_id(t, fn, mid)
        memo[key] = (m, {} if m is None else caller_refs(t, fn, mid, m))
    return memo[key]


def up_hops(t, key):
    """Every hop one level up from key: its references grouped per consumer,
    kind and context, each group content-addressed."""
    memo = t.__dict__.setdefault("_attach_up", {})
    if key in memo:
        return memo[key]
    m, refs = _refs(t, key)
    groups = {}
    for (fn2, cmid), pos in sorted(refs.items()):
        ck = "%s:%s" % (fn2, cmid)
        cm = None if cmid == "(file scope)" else _member_by_id(t, fn2, cmid)
        for p in pos:
            kind, ctx, text, dk = hop_at(t, fn2, cm, p, m)
            g = groups.setdefault((ck, kind, ctx), [dk, [], []])
            g[1].append(p)
            g[2].append(text)
    hops = []
    for (ck, kind, ctx), (dk, pos, texts) in sorted(groups.items()):
        hops.append(Hop(key, ck, kind, ctx, dk, pos, kid("\x1f".join([kind, ctx, key, ck] + sorted(texts)))))
    memo[key] = hops
    return hops


def entry_point(t, key):
    """The name of the UNRESOLVED hop that enters an unreferenced member from
    outside the source, or None: harmony:File.cs:Class.Member(Target.method)
    for a Harmony patch method, unity:File.cs:Class.Member for a Unity
    message, reflection:File.cs:Member for a member whose name is a string
    literal somewhere in plugin/."""
    fn, mid = key.split(":", 1)
    m = _member_by_id(t, fn, mid)
    if m is None:
        return None
    types = [(n, a) for n, a, b in _types(t, fn) if a <= m.start < b]
    cls = types[-1][0] if types else "?"
    strip = t.strip(t.src[fn])
    if types:
        a = types[-1][1]
        pre = strip[max(0, a - 400):a]
        pre = pre[max(pre.rfind(";"), pre.rfind("}"), pre.rfind("{")) + 1:]
        hp = re.search(r"\[\s*HarmonyPatch\s*\((.*)\)\s*\]", pre, re.S)
        mpre = strip[max(0, m.start - 200):m.start]
        if hp or re.search(r"\[\s*Harmony(?:Postfix|Prefix|Finalizer|Transpiler)\b", mpre):
            tgt = "?"
            if hp:
                ty = re.search(r"typeof\s*\(\s*([\w.]+)\s*\)", hp.group(1))
                rest = hp.group(1)[ty.end():] if ty else hp.group(1)
                me = re.search(r'nameof\s*\(\s*(?:\w+\.)*(\w+)\s*\)|"(\w+)"', rest)
                tgt = "%s.%s" % (ty.group(1) if ty else "?", (me.group(1) or me.group(2)) if me else "?")
            return "harmony:%s:%s.%s(%s)" % (fn, cls, mid, tgt)
    if base(mid) in UNITY_MESSAGES:
        return "unity:%s:%s.%s" % (fn, cls, mid)
    lit = '"%s"' % base(mid)
    if any(lit in t.strip(s) for s in t.src.values()):
        return "reflection:%s:%s" % (fn, mid)
    return None


def _upper(h):
    """The member a hop leads up to: its consumer, or, for a reference at file
    scope (a field initializer), the virtual member field:File.cs:ctx, which
    is an UNRESOLVED end."""
    if h.kind == "field":
        return "field:%s:%s" % (h.consumer.split(":", 1)[0], h.ctx)
    return h.consumer


def traverse(t, starts, roots, budget=None, leg=None, virtual=None):
    """The COMPLETE, cycle-safe traversal UP from every start (fix pass 5 H1).
    No hop bound: every member reached is expanded, and every hop of every
    member expanded is recorded. Cycle safety is one visited set over the
    whole traversal: a member is expanded once, so a path that comes back to
    a member it already holds ends there (the hop that closes it is a cycle
    hop, found from the graph by _cycle_hops and recorded as such), and the
    traversal never loops. Returns a dict:
      up         {member: [Hop]}: the hops one level up from each member expanded
      ends       {member: end} for each member that ends a path: root:K for a
                 declared root (a root ends a path; its own entries are its
                 root row); for a member with no hop, unresolved:NAME when the
                 member is entered from outside the source (entry_point), else
                 unreferenced; for a field hop's virtual member,
                 unresolved:field:File.cs:ctx; for a registration member with
                 no registration, unregistered
      parent     {member: (lower, Hop)}: the hop by which each member was first
                 reached (breadth first), to name the path to it
      truncated  [member]: reached and never expanded because `budget` members
                 had been expanded: the traversal is INCOMPLETE, and the oracle
                 is red (TRUNCATED), never a silent dead end
    leg(h): for a dispatch hop at a declared dispatcher, the virtual
    registration member register:Dispatcher{key} the hop needs (or None);
    virtual: {that member: [register Hop]}, filled by leg."""
    budget = ATTACH_BUDGET if budget is None else budget
    virtual = {} if virtual is None else virtual
    up, ends, parent, truncated = {}, {}, {}, []
    queue = collections.deque(sorted(set(starts)))
    seen = set(queue)
    expanded = 0

    def reach(node, lower, h):
        if node not in seen:
            seen.add(node)
            parent[node] = (lower, h)
            queue.append(node)

    while queue:
        node = queue.popleft()
        if node in roots:
            up[node] = []
            ends[node] = "root:" + node
            continue
        if node.startswith("field:"):
            up[node] = []
            ends[node] = "unresolved:" + node
            continue
        if expanded >= budget:
            truncated.append(node)
            continue
        expanded += 1
        hops = virtual.get(node, []) if node.startswith("register:") else up_hops(t, node)
        up[node] = hops
        if not hops:
            if node.startswith("register:"):
                ends[node] = "unregistered"
            else:
                en = entry_point(t, node)
                ends[node] = ("unresolved:" + en) if en else "unreferenced"
            continue
        for h in hops:
            reach(_upper(h), node, h)
            v = leg(h) if leg is not None else None
            if v is not None:
                reach(v, node, h)
    return {"up": up, "ends": ends, "parent": parent, "truncated": truncated}


def _succ(tr, legs, node):
    """The members one level up from node in a traversal: each hop's upper
    member and, for a dispatch hop with a registration leg, the leg's
    registration member."""
    out = []
    for h in tr["up"].get(node, ()):
        out.append(_upper(h))
        v = legs.get((node, h.digest))
        if v is not None:
            out.append(v)
    return out


def _cycle_hops(tr):
    """{(lower, hop digest)} of every hop whose two members lie in one
    strongly connected component of the traversed graph: the hop by which a
    path returns to a member it already holds. The traversal expanded that
    member once; the hop is a cycle end, recorded, never dropped."""
    up = tr["up"]
    succ = {n: [_upper(h) for h in hs if _upper(h) in up] for n, hs in up.items()}
    index, low, on, stack, comp = {}, {}, set(), [], {}
    counter = [0]
    for s0 in sorted(succ):
        if s0 in index:
            continue
        index[s0] = low[s0] = counter[0]
        counter[0] += 1
        stack.append(s0)
        on.add(s0)
        work = [(s0, iter(succ[s0]))]
        while work:
            v, it = work[-1]
            w = next(it, None)
            if w is not None:
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(succ[w])))
                elif w in on:
                    low[v] = min(low[v], index[w])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                while True:
                    x = stack.pop()
                    on.discard(x)
                    comp[x] = v
                    if x == v:
                        break
    return {(n, h.digest) for n, hs in up.items() for h in hs
            if _upper(h) in comp and comp[_upper(h)] == comp[n]}


def _hop_token(t, h, lines):
    tok = "%s%s%s>%s" % (h.kind, "[%s]" % h.ctx if h.ctx else "", "{%s}" % h.key if h.key is not None else "",
                         h.consumer)
    if lines:
        fn = h.consumer.split(":", 1)[0]
        tok += " L" + ",".join(str(t.src[fn].count("\n", 0, p) + 1) for p in sorted(h.pos))
    return tok


def _literal_table(t, fn, name):
    """The string literals of a `name = { ... }` array field, or None."""
    if fn not in t.src:
        return None
    mm = re.search(r"\b%s\s*=\s*(?:new\s*(?:string)?\s*\[\s*\]\s*)?\{([^}]*)\}" % re.escape(name), t.strip(t.src[fn]))
    if not mm:
        return None
    return set(re.findall(r'"([^"\\]*)"', mm.group(1)))


def derive_attach(st, sinks, budget=None):
    """The attachment derivation (section 5), a complete traversal (fix pass
    5). sinks: the terminal display sinks ("File.cs:Member"). Returns a dict:
      roots       {key: (line, what)} of the declared roots found
      missing     the declared roots not found exactly once
      entries     {root key: [hops]}: each root's references, one level
      hops        {(lower, hop digest): (lower, Hop)}: every hop the traversal
                  recorded, the manifest's hop rows
      ends        {member: end}: every member that ends a path, its end rows
      cycles      {(lower, hop digest)}: the hops that close a cycle, its cycle rows
      truncated   [(member, the path to it)]: members never expanded (RED)
      sinks       {sink: {"attached": bool, "hops": {(lower, digest)},
                          "nodes": {member}, "ends": {member},
                          "roots": sorted root keys reached,
                          "unregistered": {key}, "digest": its subgraph's digest}}
      unresolved  {name: set of sinks whose paths end or pass there}
      bkeys       the dispatch keys whose visual is a display sink
      tables      {dispatcher: set of keys its binding table declares, or None}
      legs        {(lower, hop digest): registration member} of each dispatch
                  hop at a declared dispatcher
      tr          the traversal itself (up, ends, parent, truncated)
    A path is every walk up the recorded hops from a sink that ends at an end
    member or at a cycle hop; every completed path is therefore manifested and
    hashed through the rows it is made of, and a change to any path changes a
    hop, end or cycle row and the digest of every sink it starts from."""
    t = st.t
    roots, missing = {}, []
    for fn, mid, what in RENDER_ROOTS:
        m = _member_by_id(t, fn, mid)
        if m is None:
            missing.append("%s:%s" % (fn, mid))
            continue
        roots["%s:%s" % (fn, mid)] = (t.src[fn].count("\n", 0, m.name_at) + 1, what)
    rset = set(roots)
    entries = {k: up_hops(t, k) for k in sorted(roots)}
    disp = {d: (reg, tab) for d, reg, tab in DISPATCHERS}
    virtual = {}                                # register:D{key} -> [register Hop]
    nonlit = collections.defaultdict(set)      # dispatch-key:... -> {register:D{key}}
    legs = {}                                   # (lower, digest) -> register:D{key}
    sinks = set(sinks)

    def register_hops(dk, key):
        (rfn, rtype, rname), _ = disp[dk]
        v = "register:%s{%s}" % (dk, key)
        out = []
        cand = [m for m in t.members(rfn) if m.name == rname
                and any(n == rtype and a <= m.start < b for n, a, b in _types(t, rfn))] if rfn in t.src else []
        if len(cand) == 1:
            rk = "%s:%s" % (rfn, member_ids(t.members(rfn))[cand[0].start])
            for h in up_hops(t, rk):
                fn2 = h.consumer.split(":", 1)[0]
                for p in sorted(h.pos):
                    mm = re.match(r'\s*\(\s*"([^"\\]*)"\s*\)', t.strip(t.src[fn2])[p + len(rname):p + len(rname) + 200])
                    if mm is None:
                        nonlit["dispatch-key:%s(%s)" % (h.consumer, h.ctx)].add(v)
                        continue
                    if mm.group(1) != key:
                        continue
                    out.append(Hop(h.callee, h.consumer, "register", h.ctx, key, [p],
                                   kid("register\x1f%s\x1f%s" % (h.digest, key))))
        return out

    def leg(h):
        if h.kind != "dispatch" or h.consumer not in disp:
            return None
        v = "register:%s{%s}" % (h.consumer, h.key)
        if v not in virtual:
            virtual[v] = register_hops(h.consumer, h.key)
        return v

    tr = traverse(t, sinks, rset, budget, leg, virtual)
    up, ends = tr["up"], tr["ends"]
    for n, hs in up.items():
        for h in hs:
            v = leg(h)
            if v is not None:
                legs[(n, h.digest)] = v
    hops = {(n, h.digest): (n, h) for n, hs in up.items() for h in hs}
    cycles = _cycle_hops(tr)

    # attached: the least fixed point over the graph. A member is attached
    # when it is a declared root or an UNRESOLVED end, or one of its hops leads
    # to an attached member - a dispatch hop at a declared dispatcher only when
    # its registration member is attached as well.
    att = {n for n, e in ends.items() if e.startswith(("root:", "unresolved:"))}
    changed = True
    while changed:
        changed = False
        for n, hs in up.items():
            if n in att:
                continue
            for h in hs:
                if _upper(h) not in att:
                    continue
                v = legs.get((n, h.digest))
                if v is not None and v not in att:
                    continue
                att.add(n)
                changed = True
                break

    unresolved = collections.defaultdict(set)
    out_sinks, bkeys = {}, set()
    for s in sorted(sinks):
        nodes, sh, todo = {s}, set(), [s]
        while todo:
            n = todo.pop()
            for h in up.get(n, ()):
                sh.add((n, h.digest))
                for m in [_upper(h)] + ([legs[(n, h.digest)]] if (n, h.digest) in legs else []):
                    if m not in nodes:
                        nodes.add(m)
                        todo.append(m)
        send = {n for n in nodes if n in ends}
        unreg = set()
        for n in nodes:
            e = ends.get(n, "")
            if e.startswith("unresolved:"):
                unresolved[e[len("unresolved:"):]].add(s)
            if n.startswith("register:"):
                if e == "unregistered":
                    unreg.add(n[n.index("{") + 1:-1])
                for name, vs in nonlit.items():
                    if n in vs:
                        unresolved[name].add(s)
        for (n, d) in sh:
            h = hops[(n, d)][1]
            if h.kind == "dispatch" and h.consumer not in disp:
                unresolved["dispatch:%s[%s]" % (h.consumer, h.key)].add(s)
        for h in up.get(s, ()):
            if h.kind == "dispatch" and h.consumer in disp:
                bkeys.add(h.key)
        lines = ["hop\t%s\t%s" % k for k in sorted(sh)] + ["end\t%s\t%s" % (n, ends[n]) for n in sorted(send)]
        lines += ["cycle\t%s\t%s" % k for k in sorted(sh & cycles)]
        out_sinks[s] = {"attached": s in att, "hops": sh, "nodes": nodes, "ends": send,
                        "roots": sorted(ends[n][len("root:"):] for n in send if ends[n].startswith("root:")),
                        "unregistered": unreg, "digest": kid("\n".join(lines))}
    truncated = []
    for n in tr["truncated"]:
        truncated.append((n, _trail(tr, n)))
    tables = {d: _literal_table(t, tab[0], tab[1]) for d, (reg, tab) in disp.items()}
    return {"roots": roots, "missing": missing, "entries": entries, "hops": hops, "ends": dict(ends),
            "cycles": cycles, "truncated": truncated, "sinks": out_sinks, "unresolved": dict(unresolved),
            "bkeys": bkeys, "tables": tables, "legs": legs, "tr": tr}


def _trail(tr, node):
    """The path by which the traversal first reached node, from the start
    member up: "Start <- A <- B <- node"."""
    out = [node]
    seen = {node}
    while node in tr["parent"]:
        node = tr["parent"][node][0]
        if node in seen:
            break
        seen.add(node)
        out.append(node)
    return " <- ".join(reversed(out))


def attach_sinks(st, graph, cman, rman):
    """The terminal display sinks: every derived caller edge classed display
    (its consumer) and every display reader that renders itself."""
    out = {c for (s, c) in graph if cman.get((s, c), (0, "", ""))[2] == "display"}
    out |= {"%s:%s" % k for k, row in rman.items() if k in st.reads and row[2] == "display" and "self" in row[3]}
    return out


def read_attach(path):
    """The attachment manifest (fix pass 5 shape), problems:
      root        {key: (n, digest, note)}
      hop         {(lower, digest): (upper, token)}   hop<TAB>lower<TAB>digest<TAB>upper<TAB>token
      end         {member: end}                       end<TAB>member<TAB>end
      cycle       {(lower, digest): upper}            cycle<TAB>lower<TAB>digest<TAB>upper
      sink        {sink: (nodes, hops, digest, status, roots)}
                                                      sink<TAB>sink<TAB>nodes<TAB>hops<TAB>digest<TAB>attached|ORPHAN<TAB>roots
      unresolved  {name: (control, note)}
      line        {(kind, key): line number}
    A row of any other kind (the fix-4 `chain` row included) is malformed."""
    rows = {"root": {}, "hop": {}, "end": {}, "cycle": {}, "sink": {}, "unresolved": {}, "line": {}}
    probs = []
    if not os.path.exists(path):
        return rows, ["attachment manifest %s missing" % path]
    hx = re.compile(r"[0-9a-f]{16}")
    for n, line in enumerate(io.open(path, encoding="utf-8").read().split("\n"), 1):
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        key = None
        if f[0] == "root" and len(f) >= 5 and f[2].isdigit() and hx.fullmatch(f[3]):
            key, val = f[1], (int(f[2]), f[3], f[4])
        elif f[0] == "hop" and len(f) == 5 and hx.fullmatch(f[2]):
            key, val = (f[1], f[2]), (f[3], f[4])
        elif f[0] == "end" and len(f) == 3:
            key, val = f[1], f[2]
        elif f[0] == "cycle" and len(f) == 4 and hx.fullmatch(f[2]):
            key, val = (f[1], f[2]), f[3]
        elif f[0] == "sink" and len(f) == 7 and f[2].isdigit() and f[3].isdigit() and hx.fullmatch(f[4]):
            key, val = f[1], (int(f[2]), int(f[3]), f[4], f[5], f[6])
        elif f[0] == "unresolved" and len(f) >= 4:
            key, val = f[1], (f[2], f[3])
        if key is None:
            probs.append("attachment line %d malformed: %r" % (n, line[:80]))
            continue
        if key in rows[f[0]]:
            probs.append("attachment line %d: %s row %s twice" % (n, f[0], key))
        rows[f[0]][key] = val
        rows["line"][(f[0], key)] = n
    return rows, probs


def _unresolved_names(name):
    """The names a control must carry to name an UNRESOLVED hop."""
    mm = re.match(r"harmony:[^:]+:(\w+)\.[\w#]+\(([\w.]+)\)$", name)
    if mm:
        return [mm.group(1), mm.group(2).split(".")[-1]]
    mm = re.match(r"(?:unity|reflection):[^:]+:(?:(\w+)\.)?([\w#]+)$", name)
    if mm:
        return [x for x in (mm.group(1), base(mm.group(2))) if x]
    mm = re.match(r"dispatch:[^:]+:([\w#]+)\[(.*)\]$", name)
    if mm:
        return [base(mm.group(1)), mm.group(2)]
    mm = re.match(r"field:[^:]+:(\w+)$", name)
    if mm:
        return [mm.group(1)]
    return [name]


def control_names(root, control, names):
    """None when the control exists and names every one of names, else why
    not. A control is a pytest node, path::function or path::function[param],
    the path relative to the tree."""
    mm = re.fullmatch(r"([\w./-]+\.py)::(\w+)(?:\[([\w.-]+)\])?", control)
    if not mm:
        return "control %r is not a pytest node (path::function[param])" % control
    p = os.path.join(root, *mm.group(1).split("/"))
    if not os.path.exists(p):
        return "control file %s missing" % mm.group(1)
    src = io.open(p, encoding="utf-8").read()
    if not re.search(r"^def %s\(" % re.escape(mm.group(2)), src, re.M):
        return "control %s defines no %s" % (mm.group(1), mm.group(2))
    for x in ([mm.group(3)] if mm.group(3) else []) + list(names):
        if not re.search(r"(?<![\w])%s(?![\w])" % re.escape(x), src):
            return "control %s does not name %s" % (control, x)
    return None


def attach_problems(root, st, att, aman, cman):
    """Section 5's verdicts."""
    t = st.t
    probs = []
    for k in att["missing"]:
        probs.append("ROOT MISSING %s: a declared render root is not one member of the tree" % k)
    for k, hops in sorted(att["entries"].items()):
        dg = kid("\n".join(sorted(h.digest for h in hops)))
        row = aman["root"].get(k)
        ents = ", ".join(_hop_token(t, h, True) for h in hops) or "none"
        if row is None:
            probs.append("NEW root %s (entered from %s) is not in the attachment manifest" % (k, ents))
        elif row[0] != len(hops) or row[1] != dg:
            probs.append("ROOT ENTRY CHANGED %s: entered from %s (%d, %s), manifest %d, %s" % (
                k, ents, len(hops), dg, row[0], row[1]))
        if not hops and entry_point(t, k) is None:
            probs.append("root %s is referenced nowhere and is no entry point" % k)
    for k in sorted(set(aman["root"]) - set(att["entries"])):
        probs.append("STALE root row %s: no declared root of that name" % k)
    for n, trail in att["truncated"]:
        probs.append("TRUNCATED attachment traversal at %s: reached by the path %s and never expanded (the traversal "
                     "expands at most %d members): a truncated traversal is incomplete, never a dead end" % (
                         n, trail, ATTACH_BUDGET))
    for s, rec in sorted(att["sinks"].items()):
        if not rec["attached"]:
            why = []
            if rec["unregistered"]:
                why.append("dispatch key %s registered nowhere attached" % ",".join(sorted(rec["unregistered"])))
            dead = sorted("%s (%s)" % (m, att["ends"][m]) for m in rec["ends"])
            if dead:
                why.append("paths end at %s" % ", ".join(dead[:6]))
            probs.append("ORPHAN display sink %s: no attachment chain to a declared render root or a controlled "
                         "UNRESOLVED end, over the complete traversal%s" % (s, (": " + "; ".join(why)) if why else ""))
    dg = _AttachGraph.derived(att)
    mg = _AttachGraph.recorded(aman)
    rows = attach_rows(t, att)
    for k in sorted(set(rows["hop"]) - set(aman["hop"])):
        n, h = att["hops"][k]
        for s in dg.sinks_through(n):
            probs.append("NEW attachment chain hop %s of display sink %s: %s > %s, on the path %s" % (
                k[1], s, n, _hop_token(t, h, True), dg.path(s, n, k)))
    for k in sorted(set(aman["hop"]) - set(rows["hop"])):
        upper, tok = aman["hop"][k]
        for s in mg.sinks_through(k[0]) or ["-"]:
            probs.append("STALE attachment chain hop %s of display sink %s: the source derives no such hop (%s > %s, "
                         "manifest line %d); the recorded path %s" % (
                             k[1], s, k[0], tok, aman["line"][("hop", k)], mg.path(s, k[0], k) if s != "-" else "-"))
    for kind, label in (("end", "end"), ("cycle", "cycle hop")):
        for k in sorted(set(rows[kind]) | set(aman[kind])):
            a, b = rows[kind].get(k), aman[kind].get(k)
            if a == b:
                continue
            node = k[0] if kind == "cycle" else k
            if b is None:
                sk = dg.sinks_through(node)
                probs.append("NEW attachment %s %s: %s (on the paths of %s)" % (label, "/".join(k) if kind == "cycle" else k,
                                                                                  a, ",".join(sk) or "-"))
            elif a is None:
                probs.append("STALE attachment %s %s: the source derives no such %s (manifest %s, line %d)" % (
                    label, "/".join(k) if kind == "cycle" else k, label, b, aman["line"][(kind, k)]))
            else:
                probs.append("attachment %s CHANGED %s: derived %s, manifest %s" % (label, k, a, b))
    for s in sorted(set(rows["sink"]) | set(aman["sink"])):
        a, b = rows["sink"].get(s), aman["sink"].get(s)
        if a == b:
            continue
        fmt = lambda r: "-" if r is None else "%d member(s), %d hop(s), digest %s, %s, roots %s" % r
        probs.append("SINK CHANGED display sink %s: derived %s; manifest %s" % (s, fmt(a), fmt(b)))
    for name, sk in sorted(att["unresolved"].items()):
        row = aman["unresolved"].get(name)
        if row is None:
            probs.append("UNRESOLVED hop %s (on the chains of %s) has no disposition" % (name, ",".join(sorted(sk))))
            continue
        ctl, note = row
        why = control_names(root, ctl, _unresolved_names(name))
        if why:
            probs.append("UNRESOLVED hop %s: %s" % (name, why))
        if not note.strip():
            probs.append("UNRESOLVED hop %s has no note" % name)
    for name in sorted(set(aman["unresolved"]) - set(att["unresolved"])):
        probs.append("STALE UNRESOLVED disposition %s: no chain ends or passes there" % name)
    for d, keys in sorted(att["tables"].items()):
        if keys is None:
            probs.append("the binding visual table of dispatcher %s is not found" % d)
        elif keys != att["bkeys"]:
            probs.append("BINDING VISUALS DIFFER at %s: the table declares %s, the visuals that are display sinks "
                         "are %s" % (d, ",".join(sorted(keys)) or "-", ",".join(sorted(att["bkeys"])) or "-"))
    for (s, c), row in sorted(cman.items()):
        if row[2] != "retired":
            continue
        m, refs = _refs(t, c)
        n = sum(len(v) for v in refs.values())
        if m is None:
            probs.append("retired consumer %s of %s is not one member of the tree" % (c, s))
        elif n or entry_point(t, c):
            probs.append("RETIRED consumer %s of %s is referenced again (%d place(s)%s): class it display and "
                         "record its attachment" % (c, s, n, ", " + entry_point(t, c) if entry_point(t, c) else ""))
    return probs


def attach_rows(t, att):
    """The derivation in the manifest's row shape (the keys and values
    read_attach returns): hop, end, cycle and sink rows."""
    rows = {"hop": {}, "end": {}, "cycle": {}, "sink": {}}
    for k, (n, h) in att["hops"].items():
        rows["hop"][k] = (_upper(h), _hop_token(t, h, False))
    for n, e in att["ends"].items():
        rows["end"][n] = e
    for k in att["cycles"]:
        rows["cycle"][k] = _upper(att["hops"][k][1])
    for s, rec in att["sinks"].items():
        rows["sink"][s] = (len(rec["nodes"]), len(rec["hops"]), rec["digest"],
                           "attached" if rec["attached"] else "ORPHAN", ",".join(rec["roots"]) or "-")
    return rows


def attach_lines(t, att, aman):
    """The manifest's lines in order: root, hop, end, cycle, sink, unresolved
    (root notes and unresolved dispositions carried from aman)."""
    rows = attach_rows(t, att)
    out = []
    for k, hops in sorted(att["entries"].items()):
        old = aman["root"].get(k)
        out.append("\t".join(["root", k, str(len(hops)), kid("\n".join(sorted(h.digest for h in hops))),
                              old[2] if old else ""]))
    for k, (upper, tok) in sorted(rows["hop"].items()):
        out.append("\t".join(["hop", k[0], k[1], upper, tok]))
    for n, e in sorted(rows["end"].items()):
        out.append("\t".join(["end", n, e]))
    for k, upper in sorted(rows["cycle"].items()):
        out.append("\t".join(["cycle", k[0], k[1], upper]))
    for s, r in sorted(rows["sink"].items()):
        out.append("\t".join(["sink", s, str(r[0]), str(r[1]), r[2], r[3], r[4]]))
    for name in sorted(att["unresolved"]):
        old = aman["unresolved"].get(name)
        out.append("\t".join(["unresolved", name, old[0] if old else "?", old[1] if old else ""]))
    return out


class _AttachGraph:
    """An attachment graph to name paths in: the derived one (the traversal)
    or the recorded one (the manifest's hop, end and sink rows)."""

    def __init__(self, succ, ends, sinks):
        self.succ, self.ends, self.sinks = succ, ends, sorted(sinks)
        self._reach = {}

    @classmethod
    def derived(cls, att):
        succ = collections.defaultdict(list)
        for (n, d), (_, h) in att["hops"].items():
            succ[n].append(((n, d), _upper(h)))
            v = att["legs"].get((n, d))
            if v is not None:
                succ[n].append((None, v))
        return cls(succ, att["ends"], att["sinks"])

    @classmethod
    def recorded(cls, aman):
        disp = {d for d, reg, tab in DISPATCHERS}
        succ = collections.defaultdict(list)
        for (n, d), (upper, tok) in aman["hop"].items():
            succ[n].append(((n, d), upper))
            mm = re.match(r"dispatch\[.*\{([^{}]*)\}>([^>]*)$", tok)
            if mm and mm.group(2) in disp:
                succ[n].append((None, "register:%s{%s}" % (mm.group(2), mm.group(1))))
        return cls(succ, aman["end"], aman["sink"])

    def reach(self, s):
        """{member: (previous member, hop key)} breadth first from s."""
        if s not in self._reach:
            par, q = {s: None}, collections.deque([s])
            while q:
                n = q.popleft()
                for k, m in sorted(self.succ.get(n, ()), key=lambda x: (x[1], x[0] or ("", ""))):
                    if m not in par:
                        par[m] = (n, k)
                        q.append(m)
            self._reach[s] = par
        return self._reach[s]

    def sinks_through(self, n):
        return [s for s in self.sinks if n in self.reach(s)]

    def path(self, s, n, hop):
        """s <- ... <- n, the hop, then up to the nearest end: the path a hop
        lies on, named member by member with its end."""
        par = self.reach(s)
        if n not in par:
            return "(%s does not reach %s)" % (s, n)
        down = [n]
        while par[down[-1]] is not None:
            down.append(par[down[-1]][0])
        down.reverse()
        upper = next((m for k, m in self.succ.get(n, ()) if k == hop), None)
        if upper is None:
            return " <- ".join(down) + " <- (hop gone)"
        nxt = self.toward_end()
        upto, m, seen = [upper], upper, {upper}
        while m not in self.ends and m in nxt and nxt[m] not in seen:
            m = nxt[m]
            seen.add(m)
            upto.append(m)
        tail = upto[-1]
        return " <- ".join(down + upto) + (" (%s)" % self.ends[tail] if tail in self.ends else " (no end)")

    def toward_end(self):
        """{member: the next member on a shortest way up to an end}, one
        breadth-first pass back from every end."""
        if not hasattr(self, "_next"):
            back = collections.defaultdict(list)
            for n, outs in self.succ.items():
                for k, m in outs:
                    back[m].append(n)
            nxt, q = {}, collections.deque(sorted(self.ends))
            done = set(q)
            while q:
                m = q.popleft()
                for n in sorted(back.get(m, ())):
                    if n not in done:
                        done.add(n)
                        nxt[n] = m
                        q.append(n)
            self._next = nxt
        return self._next


def attach_digest(att, t):
    """The digest of every hop, end, cycle and sink row: every completed path
    from every sink is in it."""
    rows = attach_rows(t, att)
    lines = ["hop\t%s\t%s\t%s\t%s" % (k[0], k[1], v[0], v[1]) for k, v in sorted(rows["hop"].items())]
    lines += ["end\t%s\t%s" % kv for kv in sorted(rows["end"].items())]
    lines += ["cycle\t%s\t%s\t%s" % (k[0], k[1], v) for k, v in sorted(rows["cycle"].items())]
    lines += ["sink\t%s\t%d\t%d\t%s\t%s\t%s" % ((s,) + r) for s, r in sorted(rows["sink"].items())]
    return kid("\n".join(lines))


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


def check(root=REPO, disp_path=None, sites_path=None, verbose=True, readers_path=None, callers_path=None,
          state=None, attach_path=None):
    """state: a State of this same tree to reuse (a test that varies only the
    readers, callers or attachment manifest); built afresh when None."""
    st = state if state is not None else State(root)
    t, u, blocks = st.t, st.u, st.blocks
    disp, problems = read_disp(disp_path or os.path.join(root, "tools", "keybind_surfaces.tsv"))
    man, p2 = read_sites(sites_path or os.path.join(root, "tools", "keybind_surfaces_sites.tsv"))
    problems += p2
    rman, p3 = read_readers(readers_path or os.path.join(root, "tools", "keybind_surfaces_readers.tsv"))
    problems += p3
    cman, p4 = read_callers(callers_path or os.path.join(root, "tools", "keybind_surfaces_callers.tsv"))
    problems += p4
    aman, p5 = read_attach(attach_path or os.path.join(root, "tools", "keybind_surfaces_attach.tsv"))
    problems += p5
    # the caller graph, derived from source (section 4 of the docstring)
    graph = derive_callers(st, cman)
    srcs = st.caller_srcs
    reach = display_reach(graph, cman)

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
        # fix pass 3 H1: a followed reader's display consumers are DERIVED
        sk = "%s:%s" % (fn, mid)
        derived = sorted(via_name(fn, c) for c in reach.get(sk, ())) if sk in srcs else None
        if role == "display":
            if not via:
                problems.append("display reader %s:%s names no consumer (via, or self)" % (fn, mid))
            if derived is not None:
                named = sorted(v for v in via if v != "self")
                if named != derived:
                    problems.append("VIA DIFFERS display reader %s:%s: the manifest names %s, the source reaches "
                                    "the player through %s" % (fn, mid, ",".join(named) or "-", ",".join(derived) or "-"))
            else:
                for v in via:
                    if v == "self":
                        continue
                    vfn, m = resolve_member(t, fn, v)
                    if m is None:
                        problems.append("display reader %s:%s consumer %s not found once" % (fn, mid, v))
                    elif not re.search(r"(?<![\w])%s\s*\(" % re.escape(base(mid)),
                                       t.mask(t.src[vfn])[m.start:m.end]):
                        problems.append("display reader %s:%s consumer %s does not call it" % (fn, mid, v))
        elif derived and role != "producer":
            problems.append("reader %s:%s role %s, but its value reaches the player through %s: it is a display "
                            "reader" % (fn, mid, role, ",".join(derived)))
        if not note.strip():
            problems.append("reader %s:%s has no review note" % (fn, mid))
    for k in sorted(set(rman) - set(reads)):
        problems.append("STALE reader %s:%s" % k)

    # 3b. callers (fix pass 3 H1): every edge of the derived graph is a row,
    # counted and content-addressed; every row is an edge (reverse discovery)
    edge_digests = []
    classes = collections.Counter()
    for (s, c), pos in sorted(graph.items()):
        fn2, cmid = c.split(":", 1)
        dg = caller_digest(t, c, pos)
        edge_digests.append("%s>%s=%s" % (s, c, dg))
        row = cman.get((s, c))
        if row is None:
            problems.append("NEW caller %s of %s (%d reference(s)) is not in the callers manifest" % (c, s, len(pos)))
            continue
        cnt, cdg, cls, note = row
        classes[cls] += 1
        if cnt != len(pos):
            problems.append("caller %s of %s references it %d time(s), manifest %d" % (c, s, len(pos), cnt))
        if cdg != dg:
            problems.append("CALLER CHANGED %s of %s content %s, manifest %s: review its class again" % (c, s, dg, cdg))
        is_prod = (fn2, base(cmid)) in prod_set
        if cls not in CALLER_CLASSES:
            problems.append("caller %s of %s class %r unknown" % (c, s, cls))
        elif (cls == "producer") != is_prod:
            problems.append("caller %s of %s class %s, but it is %sa producer" % (c, s, cls, "" if is_prod else "not "))
        elif cls == "pass":
            cm = None if cmid == "(file scope)" else _member_by_id(t, fn2, cmid)
            if cm is None or not value_returning(cm):
                problems.append("caller %s of %s is pass, but it returns no value to follow" % (c, s))
        if not note.strip():
            problems.append("caller %s of %s has no review note" % (c, s))
    for k in sorted(set(cman) - set(graph)):
        problems.append("STALE caller %s of %s: the derived graph has no such edge" % (k[1], k[0]))
    graph_digest = kid("\n".join(edge_digests))

    # 3c. attachment (fix pass 4 H1): every terminal display sink reaches a
    # declared render root by a recorded chain (section 5 of the docstring)
    att = derive_attach(st, attach_sinks(st, graph, cman, rman))
    problems += attach_problems(root, st, att, aman, cman)

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
    summary += " callers=%d [%s] followed=%d graph=%s" % (
        len(graph), " ".join("%s=%d" % kv for kv in sorted(classes.items())), len(srcs), graph_digest)
    summary += (" attach: roots=%d sinks=%d members=%d hops=%d ends=%d cycles=%d unresolved=%d truncated=%d "
                "bkeys=%s digest=%s") % (
        len(att["roots"]), len(att["sinks"]), len(att["tr"]["up"]), len(att["hops"]), len(att["ends"]),
        len(att["cycles"]), len(att["unresolved"]), len(att["truncated"]), ",".join(sorted(att["bkeys"])) or "-",
        attach_digest(att, st.t))
    return problems, summary, (t, u, found, disp)


def _callers_rows(st, cman):
    """The derived caller graph in the callers manifest's shape (class and
    note carried from the manifest when the row exists)."""
    graph = derive_callers(st, cman)
    rows = []
    for (s, c), pos in sorted(graph.items()):
        old = cman.get((s, c))
        rows.append((s, c, len(pos), caller_digest(st.t, c, pos), old[2] if old else "?",
                     old[3] if old else "", pos))
    return rows


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
    ap.add_argument("mode", choices=("check", "candidates", "sites", "readers", "callers", "attach", "path", "review"))
    ap.add_argument("--tree", default=REPO)
    ap.add_argument("members", nargs="*", help="path mode: a sink, then each member up to its end")
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
    if a.mode == "callers":
        # the derived caller graph in the callers manifest's shape, then
        # each reference's line (fix pass 3 H1)
        cman, _ = read_callers(os.path.join(a.tree, "tools", "keybind_surfaces_callers.tsv"))
        rows = _callers_rows(st, cman)
        for s, c, n, dg, cls, note, pos in rows:
            print("\t".join([s, c, str(n), dg, cls, note]))
        for s, c, n, dg, cls, note, pos in rows:
            fn2 = c.split(":", 1)[0]
            src = st.t.strip(st.t.src[fn2])
            for p in pos:
                a0 = src.rfind("\n", 0, p) + 1
                b0 = src.find("\n", p)
                print("#REF %s > %s L%d %s" % (s, c, src.count("\n", 0, p) + 1, ws(src[a0:b0])[:200]))
        return 0
    if a.mode in ("attach", "path"):
        cman, _ = read_callers(os.path.join(a.tree, "tools", "keybind_surfaces_callers.tsv"))
        apath = os.path.join(a.tree, "tools", "keybind_surfaces_attach.tsv")
        aman, _ = read_attach(apath)
        graph = derive_callers(st, cman)
        att = derive_attach(st, attach_sinks(st, graph, cman, rman))
    if a.mode == "path":
        # fix pass 5 H1 control (a): a path given member by member, from a
        # sink up to its end; each hop must be derived, a hop row of the
        # manifest and in the sink's subgraph (so in its digest and the
        # oracle's); the last member must be an end row.
        ms = a.members
        if len(ms) < 2:
            print("path: give a sink and the members up to its end")
            return 2
        rows, ok = attach_rows(st.t, att), True
        sink = ms[0]
        rec = att["sinks"].get(sink)
        print("path %s: sink row line %s, %s" % (" <- ".join(ms), aman["line"].get(("sink", sink), "NONE"),
                                                 "a display sink" if rec else "NOT a display sink"))
        ok &= rec is not None and ("sink", sink) in aman["line"] and rows["sink"].get(sink) == aman["sink"].get(sink)
        for lo, hi in zip(ms, ms[1:]):
            ks = sorted(k for k, (n, h) in att["hops"].items() if n == lo and _upper(h) == hi)
            if not ks:
                print("  %s <- %s: NO derived hop" % (lo, hi))
                ok = False
                continue
            for k in ks:
                ln = aman["line"].get(("hop", k))
                inm = aman["hop"].get(k) == rows["hop"][k]
                ins = rec is not None and k in rec["hops"]
                print("  %s <- %s: hop %s %s, manifest line %s (%s), in the sink's subgraph: %s" % (
                    lo, hi, k[1], _hop_token(st.t, att["hops"][k][1], True), ln, "equal" if inm else "DIFFERS",
                    "yes" if ins else "NO"))
                ok &= ln is not None and inm and ins
        end = att["ends"].get(ms[-1])
        ln = aman["line"].get(("end", ms[-1]))
        print("  end %s: %s, manifest line %s" % (ms[-1], end or "NOT an end", ln))
        ok &= end is not None and ln is not None and aman["end"].get(ms[-1]) == end
        print("path: %s; attach digest %s" % ("PRESENT (derived, manifested, in the sink's digest)" if ok else "ABSENT",
                                               attach_digest(att, st.t)))
        return 0 if ok else 1
    if a.mode == "attach":
        # the attachment derivation in the attachment manifest's shape (root
        # notes and unresolved dispositions carried from the manifest when the
        # row exists), then every root, sink, hop and truncation with its
        # lines (fix pass 4 H1, fix pass 5 H1: the complete traversal)
        for line in attach_lines(st.t, att, aman):
            print(line)
        for fn, mid, what in RENDER_ROOTS:
            k = "%s:%s" % (fn, mid)
            if k in att["roots"]:
                print("#ROOT %s:%d %s - %s; entered from %s" % (fn, att["roots"][k][0], mid, what, ", ".join(
                    _hop_token(st.t, h, True) for h in att["entries"][k]) or "nowhere"))
            else:
                print("#ROOT %s MISSING" % k)
        for s, rec in sorted(att["sinks"].items()):
            print("#SINK %s %s members=%d hops=%d ends=%d roots=%s%s" % (
                s, "attached" if rec["attached"] else "ORPHAN", len(rec["nodes"]), len(rec["hops"]),
                len(rec["ends"]), ",".join(rec["roots"]) or "-", (" unregistered=" + ",".join(
                    sorted(rec["unregistered"]))) if rec["unregistered"] else ""))
        for k, (n, h) in sorted(att["hops"].items()):
            print("#HOP %s %s > %s%s" % (k[1], n, _hop_token(st.t, h, True), " CYCLE" if k in att["cycles"] else ""))
        for n, trail in att["truncated"]:
            print("#TRUNCATED %s via %s" % (n, trail))
        print("#TOTALS members=%d hops=%d ends=%d cycles=%d unresolved=%d truncated=%d" % (
            len(att["tr"]["up"]), len(att["hops"]), len(att["ends"]), len(att["cycles"]), len(att["unresolved"]),
            len(att["truncated"])))
        print("#BINDING-KEYS derived %s; tables %s" % (",".join(sorted(att["bkeys"])) or "-", "; ".join(
            "%s=%s" % (d, ",".join(sorted(k)) if k is not None else "NOT FOUND") for d, k in sorted(att["tables"].items()))))
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
