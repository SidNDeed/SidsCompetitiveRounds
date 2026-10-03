"""F4 bound check (seat evidence fix passes 1 to 3): what the evidence path
may do while a game method waits.

Entry points are every method of every evidence [HarmonyPatch] class (the
patch-time TargetMethod/Prepare/Cleanup excluded) plus the game-over and cut
dispatches (SeatEvidence.Dispatch, CardDrawEvidence.Dispatch, which
GameStateWatcher calls from its result paths) and the room-exit edges.

Fix pass 3: the walk is TRANSITIVE over the whole plugin, not the evidence
files alone. `texts` is every plugin source file; every method, expression-
bodied method and property getter of every top-level class (nested classes
filed under their top-level class) is a node. From each reached node the
check follows:
  * "Class.Method(" and "Class.Property" for any plugin class, a using alias
    of one ("C." for SeatEvidenceCore, "K." for CardDrawEvidenceCore) or a
    nested class name;
  * unqualified calls and property reads within the same top-level class;
  * "receiver.Method(": the receiver's DECLARED type in that file (field,
    local, parameter, or "var x = new T(") selects the class; a receiver
    declared only with non-plugin types (List, string, Dictionary, ...) is
    not plugin code; a receiver whose type is not declared in the file
    (a "var" from an expression, a foreach variable) goes to EVERY plugin
    instance method of that name: an over-approximation, it can only add
    methods.
It requires of every method in that closure:
  1. no FORBIDDEN token: logging, file or directory work, assembly scans,
     patch-info reads, reflection lookups, sorting, budgeting, hashing and
     signing, the census, queue loads and saves, string building and
     formatting, coroutines, sends, and the named variable aggregations (age
     buckets, drift, cadence, percentiles);
  2. no loop that is not hard-capped: no foreach, no while, no do; a for loop
     only when its header names a *_CAP constant, the hard bound of the
     snapshot it copies.
Comments and string literals are blanked before scanning, so a token named in
prose is not a finding.

    import bound_check; bound_check.check(texts, entry_filter) -> (findings, closure)
"""
import hashlib
import re

_PARSED = {}

FORBIDDEN = [
    "Plugin.Log", "Debug.Log", "File.", "Directory.", "FileStream", "StreamWriter", "GetAssemblies",
    "GetPatchInfo", "AccessTools.", "Budget(", "Sha256Hex(", "Hmac(", "SeatEvidenceSig(", "Envelope(",
    "CensusText(", "CensusDigest(", "Save(", "Load(", "Enqueue", "StringBuilder", "string.Format", "$\"",
    "HitRecvLine(", "ShotObsLine(", "BlockMissLine(", "Json(", "StartCoroutine", "SeatEvidencePost",
    # fix pass 2: the variable aggregations a game-over dispatch used to run
    "AgeBuckets(", "DriftTriple(", "Five(", "Four(", "Three(", "Percentile(", "OtherCaps(", "CloseHand(",
    # fix pass 3: reflection and sorting (a build lookup, a room classification)
    "GetCustomAttribute", "GetCustomAttributes", ".GetField(", ".GetMethod(", ".GetProperty(", "Sort(",
    "OrderBy", "ThenBy",
]

PATCH_TIME = {"TargetMethod", "Prepare", "Cleanup"}
EXTRA_ENTRIES = [("SeatEvidence", "Dispatch"), ("CardDrawEvidence", "Dispatch"),
                 ("SeatEvidence", "RoomExit"), ("CardDrawEvidence", "RoomExit")]
KEYWORDS = {"if", "for", "foreach", "while", "switch", "catch", "using", "lock", "return", "new", "typeof",
            "sizeof", "nameof", "default", "when", "base", "this"}
NOT_TYPES = {"return", "new", "else", "throw", "case", "in", "out", "ref", "is", "as", "await", "yield", "goto",
             "using", "namespace", "class", "struct", "enum", "interface", "const", "static", "readonly", "private",
             "internal", "public", "protected", "override", "sealed", "abstract", "virtual", "event", "params",
             "var", "get", "set", "where", "operator", "implicit", "explicit", "unchecked", "checked", "fixed"}
BUILTIN = {"string", "int", "long", "float", "double", "bool", "object", "char", "byte", "short", "uint", "ulong",
           "decimal", "sbyte", "ushort"}
CAP_RE = re.compile(r"\b[A-Z][A-Z0-9_]*_CAP\b")
ALIAS_RE = re.compile(r"(?m)^using\s+(\w+)\s*=\s*CompetitiveRounds\.(\w+)\s*;")


def blank(text):
    """Comments and string/char literals replaced by spaces (newlines kept)."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j])); i = j
        elif c == '"' or (c == "@" and i + 1 < n and text[i + 1] == '"') or (c == "$" and i + 1 < n and text[i + 1] == '"'):
            # keep an interpolated string's opening "$\"" visible: it is itself a forbidden token
            verbatim = c == "@"
            if c in "@$":
                out.append(c); i += 1
            out.append('"'); i += 1
            while i < n:
                if not verbatim and text[i] == "\\":
                    out.append("  "); i += 2; continue
                if text[i] == '"':
                    if verbatim and i + 1 < n and text[i + 1] == '"':
                        out.append("  "); i += 2; continue
                    break
                out.append("\n" if text[i] == "\n" else " "); i += 1
            out.append('"'); i += 1
        elif c == "'":
            j = i + 1
            while j < n and text[j] != "'":
                j += 2 if text[j] == "\\" else 1
            out.append(" " * (j + 1 - i)); i = j + 1
        else:
            out.append(c); i += 1
    return "".join(out)


def braced(text, i):
    """Index just past the brace block that opens at or after i."""
    i = text.index("{", i)
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(text)


def paren(text, i):
    """The text inside the parenthesis that opens at text[i] == "("."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return text[i + 1:j]
    return text[i + 1:]


MODS = r"(?P<mods>(?:(?:internal|private|public|protected|static|override|unsafe|extern|readonly|virtual|sealed|new)\s+)+)"
CLASS_RE = re.compile(r"(?m)^(?P<attrs>(?:    \[[^\n]*\]\n)*)    (?:internal|public)\s+(?:static\s+)?(?:sealed\s+)?(?:partial\s+)?class\s+(?P<name>\w+)\b")
NESTED_RE = re.compile(r"\b(?:class|struct|enum)\s+(?P<name>\w+)\b")
METHOD_RE = re.compile(r"(?m)^\s+(?:\[[^\n]*\]\s*\n\s+)*" + MODS +
                       r"(?P<ret>[\w<>\[\],\. ?]+?)\s+(?P<name>\w+)\s*\([^;{]*?\)\s*(?:where[^{;]*)?(?P<open>\{|=>)")
PROP_RE = re.compile(r"(?m)^\s+" + MODS + r"(?P<ret>[\w<>\[\],\. ?]+?)\s+(?P<name>\w+)\s*(?P<open>=>|\{\s*get\b)")


def methods(text):
    """For one blanked file: {(class, name): [body, ...]} for every method,
    expression-bodied method and property getter of every top-level class;
    the set of top-level classes carrying [HarmonyPatch]; the keys an
    instance-qualified call can reach; {nested type name: top-level class};
    the set of property keys."""
    table, patches, by_instance, nested_owner, props = {}, set(), set(), {}, set()
    for m in CLASS_RE.finditer(text):
        name = m.group("name")
        end = braced(text, m.end())
        body = text[m.end():end]
        if "[HarmonyPatch" in m.group("attrs"):
            patches.add(name)
        for nm in NESTED_RE.finditer(body):
            nested_owner.setdefault(nm.group("name"), name)
        for rx, is_prop in ((METHOD_RE, False), (PROP_RE, True)):
            for mm in rx.finditer(body):
                if mm.group("ret").split()[-1] in NOT_TYPES or mm.group("name") in KEYWORDS:
                    continue
                if mm.group("open") == "=>":
                    semi = body.find(";", mm.end())
                    seg = body[mm.end():semi + 1 if semi >= 0 else len(body)]
                else:
                    seg = body[mm.end() - 1:braced(body, mm.end() - 1)] if not is_prop else body[mm.start():braced(body, mm.end() - 1)]
                key = (name, mm.group("name"))
                table.setdefault(key, []).append(seg)
                if is_prop:
                    props.add(key)
                pre = body[:mm.start()]
                nested = pre.count("{") - pre.count("}") > 1
                if nested or "static" not in mm.group("mods").split():
                    by_instance.add(key)
    return table, patches, by_instance, nested_owner, props


CALL_RE = re.compile(r"(?<![\w.])(?:(?P<q>\w+)\.)?(?P<m>\w+)\s*\(")
REF_RE = re.compile(r"(?<![\w.])(?:(?P<q>\w+)\.)?(?P<m>\w+)\b(?!\s*[\(\w])")
LOOP_RE = re.compile(r"\b(?P<kw>foreach|while|for)\s*\(|\bdo\s*\{")
DECL_RE = re.compile(r"(?<![\w.])(?P<type>[A-Za-z_][\w\.]*(?:\s*<[^;=(){}]*?>)?(?:\s*\[\s*\])*\??)\s+(?P<name>[A-Za-z_]\w*)\s*(?=[=;,)])")
VARNEW_RE = re.compile(r"\bvar\s+(?P<name>\w+)\s*=\s*new\s+(?P<type>[\w\.]+)")


def loop_findings(body):
    """Every loop in a blanked body that is not hard-capped."""
    out = []
    for m in LOOP_RE.finditer(body):
        kw = m.group("kw")
        if kw is None:
            out.append("loop: do")
        elif kw in ("foreach", "while"):
            out.append("loop: " + kw)
        elif not CAP_RE.search(paren(body, body.index("(", m.start()))):
            out.append("loop: for without a *_CAP bound")
    return out


def declarations(text):
    """{name: set of declared base type names} for one blanked file; a name
    declared by "var" from anything but "new T(" maps to None (undeclared)."""
    d = {}
    for m in DECL_RE.finditer(text):
        t = m.group("type")
        base = re.sub(r"<.*", "", t).replace("[", "").replace("]", "").replace("?", "").strip()
        if base in NOT_TYPES or not base:
            continue
        d.setdefault(m.group("name"), set()).add(base)
        # "Type a = x, b = y, c;": every name of the declaration list
        if text[m.end():m.end() + 1] in "=,;" or text[m.end():].lstrip()[:1] in ("=", ","):
            depth, j, seg = 0, m.end(), []
            while j < len(text):
                ch = text[j]
                if ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    if depth == 0:
                        break
                    depth -= 1
                elif ch == ";" and depth == 0:
                    break
                elif ch == "," and depth == 0:
                    seg.append(j + 1)
                j += 1
            for s in seg:
                mm = re.match(r"\s*([A-Za-z_]\w*)\s*(?:=|,|;|$)", text[s:j + 1])
                if mm:
                    d.setdefault(mm.group(1), set()).add(base)
    for m in VARNEW_RE.finditer(text):
        d.setdefault(m.group("name"), set()).add(m.group("type"))
    return d


class Graph:
    """The whole plugin's call graph, as the check resolves it."""

    def __init__(self, texts):
        self.table, self.owner, self.patches, self.aliases = {}, {}, {}, {}
        self.by_name, self.nested_owner, self.props, self.decl = {}, {}, set(), {}
        self.fallbacks, self.file_classes = 0, {}
        for f, src in texts.items():
            src = src.replace("\r\n", "\n")
            for a in ALIAS_RE.finditer(src):
                self.aliases[a.group(1)] = a.group(2)
            key = (f, hashlib.sha256(src.encode("utf-8")).hexdigest())
            if key not in _PARSED:          # a file's parse depends on its text alone
                b = blank(src)
                _PARSED[key] = (methods(b), declarations(b))
            (t, patches, inst, nested, props), decl = _PARSED[key]
            self.patches[f] = patches
            self.decl[f] = decl
            self.props |= props
            for k, v in t.items():
                self.table.setdefault(k, []).extend(v)
                self.owner[k] = f
                if k in inst:
                    self.by_name.setdefault(k[1], set()).add(k)
            for n, top in nested.items():
                self.nested_owner.setdefault(n, set()).add(top)
            self.file_classes.setdefault(f, set()).update(k[0] for k in t)
        self.classes = {k[0] for k in self.table}

    def cls_of(self, name, f):
        """The top-level plugin classes a type or qualifier names, seen from
        file f: a nested type name nested in a class of f means that class;
        one nested in several classes elsewhere means all of them."""
        parts = name.split(".")
        for p in (parts[0], parts[-1]):
            if p in self.classes:
                return [p]
            if p in self.aliases:
                return [self.aliases[p]]
            if p in self.nested_owner:
                own = self.nested_owner[p] & self.file_classes.get(f, set())
                return sorted(own or self.nested_owner[p])
        return []

    def targets(self, k, q, m, call):
        f = self.owner[k]
        if q is None:
            if call or (k[0], m) in self.props:
                return [(k[0], m)]
            return []
        types = self.decl[f].get(q) if q not in self.classes and q not in self.aliases else None
        if not types and (q in self.classes or q in self.aliases or q in self.nested_owner):
            return [(c, m) for c in self.cls_of(q, f)]
        if not call:
            return []
        if types:
            out = []
            for t in types:
                for tc in self.cls_of(t, f):
                    out.append((tc, m))
            return out
        if q[0].isupper() or q in BUILTIN:
            return []          # an external static class (Array, Math, PhotonNetwork, string, ...)
        self.fallbacks += 1
        return sorted(self.by_name.get(m, ()))

    def closure(self, entries):
        seen, parent, stack = set(), {}, list(entries)
        while stack:
            k = stack.pop()
            if k in seen or k not in self.table:
                continue
            seen.add(k)
            for body in self.table[k]:
                found = [(c.group("q"), c.group("m"), True) for c in CALL_RE.finditer(body)]
                found += [(c.group("q"), c.group("m"), False) for c in REF_RE.finditer(body)]
                for q, m, call in found:
                    if m in KEYWORDS:
                        continue
                    for target in self.targets(k, q, m, call):
                        if target in self.table and target not in seen:
                            parent.setdefault(target, k)
                            stack.append(target)
        return seen, parent


def check(texts, evidence_patch_filter=None, with_paths=False):
    """texts: {filename: source}, every plugin file. Returns (findings,
    closure): findings a list of (file, Class.Method, token), closure the set
    of Class.Method names reached. with_paths: also the parent map."""
    g = Graph(texts)
    entries = []
    for f, patches in g.patches.items():
        for cls in patches:
            if evidence_patch_filter and not evidence_patch_filter(f, cls):
                continue
            for (c, m) in g.table:
                if c == cls and m not in PATCH_TIME:
                    entries.append((c, m))
    for e in EXTRA_ENTRIES:
        if e in g.table:
            entries.append(e)
    seen, parent = g.closure(entries)
    findings = []
    for k in sorted(seen):
        for body in g.table[k]:
            for tok in FORBIDDEN:
                if tok in body:
                    findings.append((g.owner[k], k[0] + "." + k[1], tok))
            for tok in loop_findings(body):
                findings.append((g.owner[k], k[0] + "." + k[1], tok))
    names = {k[0] + "." + k[1] for k in seen}
    if with_paths:
        return findings, names, {a[0] + "." + a[1]: b[0] + "." + b[1] for a, b in parent.items()}, g.fallbacks
    return findings, names
