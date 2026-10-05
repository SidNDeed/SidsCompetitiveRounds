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
# fix pass 4: a for loop's bound is a conjunct "v < X_CAP" (or <=, or "X_CAP > v"), optionally +/- a literal
BOUND_CONJ_RE = re.compile(r"^\s*(?P<v>[A-Za-z_][\w.]*)\s*(?P<op><=|<)\s*(?P<cap>(?:[A-Za-z_]\w*\.)*[A-Z][A-Z0-9_]*_CAP)\s*(?:[-+]\s*\d+\s*)?$")
BOUND_CONJ_REV_RE = re.compile(r"^\s*(?P<cap>(?:[A-Za-z_]\w*\.)*[A-Z][A-Z0-9_]*_CAP)\s*(?:[-+]\s*\d+\s*)?(?P<op>>=|>)\s*(?P<v>[A-Za-z_][\w.]*)\s*$")
# fix pass 4: collection fields, their inserts, and what a hook may do to them
COLL_TYPES = ("Dictionary", "List", "HashSet", "Stack", "Queue", "SortedSet", "SortedDictionary", "SortedList",
              "LinkedList", "ConcurrentDictionary", "ConcurrentQueue", "ConcurrentBag")
FIELD_COLL_RE = re.compile(r"(?m)^[ \t]+(?:(?:private|internal|public|protected|static|readonly|volatile)\s+)+(?:[\w.]+\.)?(?:"
                           + "|".join(COLL_TYPES) + r")\s*<[^;=(){}]*?>\s+(?P<n>[A-Za-z_]\w*)\s*[=;]")
INSERT_OPS = ("Add", "Push", "Enqueue", "Insert", "AddRange", "UnionWith", "TryAdd", "AddFirst", "AddLast", "InsertRange")
OTHER_OPS = ("Clear", "Remove", "RemoveAt", "RemoveAll", "RemoveRange", "Pop", "Dequeue", "GetEnumerator", "TrimExcess")
# fix pass 4: a read of one of these through an UNDECLARED receiver ("var x = a.b;
# x.Count") is taken as the framework member (List.Count, KeyValuePair.Value, ...),
# not as every plugin property so named; through a declared plugin receiver it is
# followed like any other property. LAST_FRAMEWORK_NAMED lists the plugin
# properties this leaves to declared receivers.
FRAMEWORK_PROPS = {"Count", "Length", "Key", "Value", "Keys", "Values", "Current"}
NEW_RE = re.compile(r"\bnew\s+(?P<t>[A-Za-z_][\w.]*)\s*(?:<[^;(){}]*>)?\s*[({]")
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


def strip_blocks(body):
    """A type body with every nested brace block removed: what is left is its
    member declarations (fields with their initializers among them)."""
    out, depth = [], 0
    for ch in body:
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)


def type_parts(table, top, tname, tbody):
    """Fix pass 4: the constructor node of type `tname` (explicit constructor
    bodies plus its instance field initializers) and its type-initializer node
    (static constructor plus static field initializers), filed under the
    top-level class `top`."""
    inner = tbody[tbody.index("{") + 1:] if "{" in tbody else tbody
    ctor_re = re.compile(r"(?m)^[ \t]+(?P<st>(?:(?:internal|private|public|protected|static)[ \t]+)*)" + re.escape(tname)
                         + r"\s*\([^;{]*?\)\s*(?::\s*(?:base|this)\s*\([^)]*\)\s*)?\{")
    inst, stat = [], []
    for cm in ctor_re.finditer(inner):
        if inner[:cm.start()].count("{") - inner[:cm.start()].count("}") != 0:
            continue          # a constructor of a type nested deeper
        seg = inner[cm.end() - 1:braced(inner, cm.end() - 1)]
        (stat if "static" in cm.group("st").split() else inst).append(seg)
    # runs of blanks collapsed (a blanked literal is a long run of spaces, and the
    # declaration pattern below would backtrack over it)
    decls = re.sub(r"[ \t]+", " ", strip_blocks(inner))
    for fm in re.finditer(r"(?m)^[ \t]*(?P<mods>(?:(?:private|internal|public|protected|static|readonly|const|volatile)[ \t]+)*)[^;=()\n]+?[ \t]+\w+[ \t]*=(?![=>])(?P<init>[^;]*);", decls):
        mods = fm.group("mods").split()
        if "const" in mods:
            continue
        (stat if "static" in mods else inst).append(fm.group("init"))
    table.setdefault((top, ".ctor:" + tname), []).append(" ".join(inst) if inst else "")
    table.setdefault((top, ".cctor:" + tname), []).append(" ".join(stat) if stat else "")


def methods(text):
    """For one blanked file: {(class, name): [body, ...]} for every method,
    expression-bodied method and property getter of every top-level class,
    and (fix pass 4) every type's constructor and type-initializer nodes;
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
        type_parts(table, name, name, body)
        spans = []
        for nm in NESTED_RE.finditer(body):
            nested_owner.setdefault(nm.group("name"), name)
            if "{" in body[nm.end():]:
                o = body.index("{", nm.end())
                e = braced(body, o)
                spans.append((o, e, nm.group("name")))
                type_parts(table, name, nm.group("name"), body[nm.end():e])

        def scope(p):
            """Fix pass 4: the innermost nested type declaring position p (None: the top-level class)."""
            best = None
            for o, e, n in spans:
                if o < p < e and (best is None or o > best[0]):
                    best = (o, e, n)
            return best[2] if best else None

        for rx, is_prop in ((METHOD_RE, False), (PROP_RE, True)):
            for mm in rx.finditer(body):
                if mm.group("ret").split()[-1] in NOT_TYPES or mm.group("name") in KEYWORDS:
                    continue
                if mm.group("open") == "=>":
                    semi = body.find(";", mm.end())
                    seg = body[mm.end():semi + 1 if semi >= 0 else len(body)]
                else:
                    seg = body[mm.end() - 1:braced(body, mm.end() - 1)] if not is_prop else body[mm.start():braced(body, mm.end() - 1)]
                # fix pass 4: a nested type's members are their own nodes ("Nested.Member"),
                # so a reached method of one nested type does not reach a namesake in another
                sc = scope(mm.start("name"))
                key = (name, (sc + "." if sc else "") + mm.group("name"))
                table.setdefault(key, []).append(seg)
                if is_prop:
                    props.add(key)
                pre = body[:mm.start()]
                nested = pre.count("{") - pre.count("}") > 1
                if nested or "static" not in mm.group("mods").split():
                    by_instance.add(key)
    return table, patches, by_instance, nested_owner, props


# Member uses (F5, combat client lane). Every identifier in a body is read with its RECEIVER, at any depth:
#   None      unqualified;
#   one       one identifier (resolved by its declared type, else by name, as before F5);
#   chain     an identifier chain `a.b.c` (typed hop by hop through the plugin's declarations, see
#             Graph.chain_targets; a framework root or hop ends it; a hop whose type is lost falls back to NAME);
#   result    the result of a call, an index or a generic type (`Make().M(`, `xs[i].M(`): resolved by NAME
#             over the whole plugin, the walk's existing over-approximation for an undeclared receiver;
#   ext       a literal (string or number): a framework type;
#   refused   any other receiver shape: reported as a finding, never skipped.
# Before F5 a one-level pattern was used and `s.Acct.AddShot(` or `Make().Run(` stopped the walk silently.
IDENT_RE = re.compile(r"[A-Za-z_]\w*")
GENERIC_CALL_RE = re.compile(r"\s*<[\w\s,.\[\]?]*(?:<[\w\s,.\[\]?]*>[\w\s,.\[\]?]*)*>\s*\(")
CALL_AFTER_RE = re.compile(r"\s*\(")
DECL_AFTER_RE = re.compile(r"\s*[\(\w]")
SPACE = " \t\r\n"
# called on a receiver of unknown type, these names are the framework's object members; a plugin override of
# one of them is not followed from such a receiver (as FRAMEWORK_PROPS for properties)
FRAMEWORK_METHODS = {"ToString", "Equals", "GetHashCode", "GetType", "CompareTo"}


def _dot_before(body, i):
    """The index of the last character of the receiver when a '.' or '?.' ends just
    before position i+1 (spaces allowed around it), else None."""
    while i >= 0 and body[i] in SPACE:
        i -= 1
    if i < 0 or body[i] != ".":
        return None
    j = i - 1
    if j >= 0 and body[j] == "?":
        j -= 1
    while j >= 0 and body[j] in SPACE:
        j -= 1
    return j


def receiver(body, s):
    """(kind, value) of the receiver of the identifier that starts at s (see above)."""
    j = _dot_before(body, s - 1)
    if j is None:
        return None, None
    segs = []
    while True:
        if j < 0:
            return "refused", None
        c = body[j]
        if c in ")]>":
            return "result", None
        if c == '"':
            return "ext", None
        if not (c.isalnum() or c == "_"):
            return "refused", None
        k = j
        while k >= 0 and (body[k].isalnum() or body[k] == "_"):
            k -= 1
        name = body[k + 1:j + 1]
        if name[0].isdigit():
            return "ext", None
        segs.insert(0, name)
        nj = _dot_before(body, k)
        if nj is None:
            return ("one", name) if len(segs) == 1 else ("chain", segs)
        j = nj


def member_uses(body):
    """(kind, value, m, call) for every identifier use m in body; kind and value as receiver() says."""
    out = []
    for mt in IDENT_RE.finditer(body):
        s, e = mt.start(), mt.end()
        if s > 0 and (body[s - 1].isalnum() or body[s - 1] in "_$@"):
            continue
        if CALL_AFTER_RE.match(body, e) or GENERIC_CALL_RE.match(body, e):
            call = True
        elif DECL_AFTER_RE.match(body, e):
            continue                     # a declaration's type and the like (as the old reference pattern)
        else:
            call = False
        kind, value = receiver(body, s)
        out.append((kind, value, mt.group(0), call))
    return out


LOOP_RE = re.compile(r"\b(?P<kw>foreach|while|for)\s*\(|\bdo\s*\{")
DECL_RE = re.compile(r"(?<![\w.])(?P<type>[A-Za-z_][\w\.]*(?:\s*<[^;=(){}]*?>)?(?:\s*\[\s*\])*\??)\s+(?P<name>[A-Za-z_]\w*)\s*(?=[=;,)])")
VARNEW_RE = re.compile(r"\bvar\s+(?P<name>\w+)\s*=\s*new\s+(?P<type>[\w\.]+)")


def split_top(s, sep):
    """s split at every top-level occurrence of sep (outside parentheses,
    brackets and braces)."""
    parts, depth, cur, i = [], 0, [], 0
    while i < len(s):
        if s[i] in "([{":
            depth += 1
        elif s[i] in ")]}":
            depth -= 1
        if depth == 0 and s.startswith(sep, i):
            parts.append("".join(cur)); cur = []; i += len(sep); continue
        cur.append(s[i]); i += 1
    parts.append("".join(cur))
    return parts


def loop_body(body, header_open):
    """The statement a for header governs: its brace block, or the single
    statement up to the next top-level semicolon."""
    close = header_open + len(paren(body, header_open)) + 2
    j = close
    while j < len(body) and body[j].isspace():
        j += 1
    if j < len(body) and body[j] == "{":
        return body[j:braced(body, j)]
    depth = 0
    for k in range(j, len(body)):
        if body[k] in "([{":
            depth += 1
        elif body[k] in ")]}":
            depth -= 1
        elif body[k] == ";" and depth == 0:
            return body[j:k + 1]
    return body[j:]


def for_bound(header, stmt):
    """Fix pass 4: None when the loop's ACTUAL limit is a cap, else the
    reason. Bounded means: the condition has a top-level conjunct
    "v < X_CAP" (<=, or reversed), v is advanced by exactly one each
    iteration (v++ / ++v / v += 1, in the iterator or the body), nothing else
    in the header or the body writes v, and v starts at a non-negative
    integer literal when the header initialises it. Naming a cap anywhere
    else in the header is not a bound."""
    parts = split_top(header, ";")
    if len(parts) != 3:
        return "loop: for header not of the form init; cond; iter"
    init, cond, it = parts
    var = None
    for conj in split_top(cond, "&&"):
        m = BOUND_CONJ_RE.match(conj) or BOUND_CONJ_REV_RE.match(conj)
        if m:
            var = m.group("v")
            break
    if var is None:
        return "loop: for whose condition has no conjunct bounding a counter by a *_CAP"
    v = re.escape(var)
    step = re.compile(r"(?<![\w.])" + v + r"\s*\+\+|\+\+\s*" + v + r"(?![\w.])|(?<![\w.])" + v + r"\s*\+=\s*1(?!\d)")
    write = re.compile(r"(?<![\w.])" + v + r"\s*(?:--|-=|\+=|\*=|/=|%=|=(?!=))|--\s*" + v + r"(?![\w.])|(?<![\w.])" + v + r"\s*\+\+|\+\+\s*" + v + r"(?![\w.])")
    steps = len(step.findall(it)) + len(step.findall(stmt))
    writes = len(write.findall(it)) + len(write.findall(stmt))
    if steps != 1 or writes != 1:
        return "loop: for counter %s is not advanced by exactly one step per iteration" % var
    im = re.search(r"(?<![\w.])" + v + r"\s*=(?!=)\s*(?P<val>[^,]+)$", init.strip())
    if im and not re.fullmatch(r"\s*\d+\s*", im.group("val")):
        return "loop: for counter %s does not start at a non-negative literal" % var
    return None


def loop_findings(body):
    """Every loop in a blanked body that is not hard-capped."""
    out = []
    for m in LOOP_RE.finditer(body):
        kw = m.group("kw")
        if kw is None:
            out.append("loop: do")
        elif kw in ("foreach", "while"):
            out.append("loop: " + kw)
        else:
            op = body.index("(", m.start())
            why = for_bound(paren(body, op), loop_body(body, op))
            if why:
                out.append(why)
    return out


def coll_ops(body, name):
    """(inserts, others): the insert and the other operations on the
    collection field `name` in a blanked body (unqualified or this.)."""
    n = re.escape(name)
    pre = r"(?:(?<![\w.])|(?<=\bthis\.))"
    ins = len(re.findall(pre + n + r"\s*\[[^\]]*\]\s*=(?![=>])", body))
    ins += len(re.findall(pre + n + r"\.(?:" + "|".join(INSERT_OPS) + r")\s*\(", body))
    oth = len(re.findall(pre + n + r"\.(?:" + "|".join(OTHER_OPS) + r")\s*\(", body))
    oth += len(re.findall(r"\bforeach\s*\([^)]*\bin\s+" + n + r"\s*\)", body))
    return ins, oth


def coll_guarded(body, name):
    """A cap guard on the field's own count in the same body: "name.Count"
    compared with a CONSTANT_NAME or a Cap member."""
    n = re.escape(name)
    k = r"(?:[A-Za-z_]\w*\.)*(?:[A-Z][A-Z0-9_]*|Cap)\b"
    return bool(re.search(r"(?<![\w.])" + n + r"\.Count\s*(?:<=|>=|<|>|==)\s*" + k, body)
                or re.search(k + r"\s*(?:<=|>=|<|>)\s*" + n + r"\.Count\b", body))


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
        self.refused, self.chained = set(), 0
        self.coll_fields, self.cctors = {}, {}
        for f, src in texts.items():
            src = src.replace("\r\n", "\n")
            for a in ALIAS_RE.finditer(src):
                self.aliases[a.group(1)] = a.group(2)
            key = (f, hashlib.sha256(src.encode("utf-8")).hexdigest())
            if key not in _PARSED:          # a file's parse depends on its text alone
                b = blank(src)
                _PARSED[key] = (methods(b), declarations(b), {m.group("n") for m in FIELD_COLL_RE.finditer(b)})
            (t, patches, inst, nested, props), decl, colls = _PARSED[key]
            self.patches[f] = patches
            self.decl[f] = decl
            self.coll_fields[f] = colls
            self.props |= props
            for k, v in t.items():
                self.table.setdefault(k, []).extend(v)
                self.owner[k] = f
                if k[1].startswith(".cctor:"):
                    self.cctors.setdefault(k[0], set()).add(k)
                if k in inst:
                    self.by_name.setdefault(k[1].split(".")[-1], set()).add(k)
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

    def resolve_type(self, tname, f, m, call):
        """Fix pass 4: member m of the type tname names: (top, "Nested.m")
        for a nested type, (top, m) for a top-level class or alias; a
        property only when it is read (call False) or a method when called."""
        last = tname.split(".")[-1]
        out = []
        for top in self.cls_of(tname, f):
            nested = last != top and last not in self.aliases and last in self.nested_owner
            key = (top, last + "." + m) if nested else (top, m)
            if key in self.table and (call or key in self.props):
                out.append(key)
        return out

    def targets(self, k, q, m, call):
        f = self.owner[k]
        if q is None:
            # unqualified: the member of the enclosing nested type, else of the top-level class
            if k[1].startswith(".ctor:") or k[1].startswith(".cctor:"):
                t = k[1].split(":", 1)[1]
                sc = t if t != k[0] else None
            else:
                sc = k[1].rsplit(".", 1)[0] if "." in k[1] else None
            out = []
            for c in ([(k[0], sc + "." + m)] if sc else []) + [(k[0], m)]:
                if c in self.table and (call or c in self.props):
                    out.append(c)
            return out
        types = self.decl[f].get(q) if q not in self.classes and q not in self.aliases else None
        if not types and (q in self.classes or q in self.aliases or q in self.nested_owner):
            return self.resolve_type(q, f, m, call)
        if types:
            out = []
            for t in types:
                # fix pass 4: a property read through a declared receiver runs its getter
                out.extend(self.resolve_type(t, f, m, call))
            return out
        if q[0].isupper() or q in BUILTIN:
            return []          # an external static class (Array, Math, PhotonNetwork, string, ...)
        if not call:
            # fix pass 4: a property read through an undeclared receiver: every plugin
            # instance property of that name (an over-approximation), except the
            # framework collection members FRAMEWORK_PROPS (see there)
            if m in FRAMEWORK_PROPS:
                return []
            hit = sorted(k for k in self.by_name.get(m, ()) if k in self.props)
            if hit:
                self.fallbacks += 1
            return hit
        self.fallbacks += 1
        return sorted(self.by_name.get(m, ()))

    def name_targets(self, m, call):
        """F5: a member of a receiver whose type the walk does not know: every plugin
        instance member of that name (the undeclared-receiver over-approximation)."""
        self.chained += 1
        if not call:
            if m in FRAMEWORK_PROPS:
                return []
            return sorted(x for x in self.by_name.get(m, ()) if x in self.props)
        if m in FRAMEWORK_METHODS:
            return []
        return sorted(self.by_name.get(m, ()))

    def chain_targets(self, k, segs, m, call):
        """F5: member m of the receiver chain segs, typed hop by hop: the root by the
        class, alias or nested type it names, else by its declaration in this file;
        each hop by the member's declaration in the file of the type it is read on.
        A framework root or hop: no plugin target. A hop whose type is lost: by name."""
        f = self.owner[k]
        root = segs[0]
        if root in ("this", "base"):
            types = {k[1].rsplit(".", 1)[0]} if "." in k[1] and not k[1].startswith(".") else {k[0]}
        elif root in self.classes or root in self.aliases or root in self.nested_owner:
            types = {root}
        else:
            d = self.decl[f].get(root)
            if d:
                types = set(d)
            elif root[0].isupper() or root in BUILTIN:
                return []                # a framework class (Encoding.UTF8, Plugin-external statics)
            else:
                return self.name_targets(m, call)
        for seg in segs[1:]:
            nxt, plugin = set(), False
            for t in types:
                for top in self.cls_of(t, f):
                    plugin = True
                    for tf, cl in self.file_classes.items():
                        if top in cl:
                            nxt |= set(self.decl[tf].get(seg) or ())
            if not plugin:
                return []                # read on a framework type
            if seg in self.nested_owner:
                nxt.add(seg)
            if not nxt:
                return self.name_targets(m, call)
            types = nxt
        out = []
        for t in sorted(types):
            out.extend(self.resolve_type(t, f, m, call))
        return out

    def ctor_targets(self, k, body):
        """Fix pass 4: every plugin type a body constructs (`new T(` or
        `new T {`): that type's constructor node."""
        f = self.owner[k]
        out = []
        for nm in NEW_RE.finditer(body):
            t = nm.group("t")
            last = t.split(".")[-1]
            for top in self.cls_of(t, f):
                out.append((top, ".ctor:" + last))
        return out

    def closure(self, entries):
        seen, parent, stack = set(), {}, list(entries)
        while stack:
            k = stack.pop()
            if k in seen or k not in self.table:
                continue
            seen.add(k)
            # fix pass 4: reaching any member of a class may run its type initializers
            for target in sorted(self.cctors.get(k[0], ())):
                if target not in seen:
                    parent.setdefault(target, k)
                    stack.append(target)
            for body in self.table[k]:
                tg = []
                for kind, value, m, call in member_uses(body):
                    if m in KEYWORDS or kind == "ext":
                        continue
                    if kind == "refused":
                        self.refused.add((k, m))
                    elif kind == "chain":
                        tg.extend(self.chain_targets(k, value, m, call))
                    elif kind == "result":
                        tg.extend(self.name_targets(m, call))
                    else:
                        tg.extend(self.targets(k, value, m, call))
                tg.extend(self.ctor_targets(k, body))
                for target in tg:
                    if target in self.table and target not in seen:
                        parent.setdefault(target, k)
                        stack.append(target)
        return seen, parent

    def coll_findings(self, seen):
        """Fix pass 4, the hook-owned collection class. A collection FIELD a
        reached body inserts into, clears, removes from or enumerates is
        hook-owned. Every insert into a hook-owned field, in ANY method of its
        file, must sit in a body that guards the field's own Count against a
        cap; a reached body's insert into any collection field likewise.
        Returns (findings, sweep): sweep rows (file, field, reached ops,
        insert sites, guarded insert sites)."""
        owned = {}
        for k in seen:
            f = self.owner[k]
            for body in self.table[k]:
                for n in self.coll_fields.get(f, ()):
                    ins, oth = coll_ops(body, n)
                    if ins or oth:
                        owned.setdefault((f, n), 0)
                        owned[(f, n)] += ins + oth
        findings, sweep = [], []
        for (f, n), ops in sorted(owned.items()):
            sites = guarded = 0
            for k, bodies in self.table.items():
                if self.owner[k] != f:
                    continue
                for body in bodies:
                    ins, _ = coll_ops(body, n)
                    if not ins:
                        continue
                    sites += 1
                    # guarded by its own count, or by the count of a parallel list the same
                    # body inserts into exactly as often (lists filled in lockstep)
                    if coll_guarded(body, n) or any(
                            m != n and coll_ops(body, m)[0] == ins and coll_guarded(body, m)
                            for m in self.coll_fields.get(f, ())):
                        guarded += 1
                    else:
                        findings.append((f, k[0] + "." + k[1], "uncapped insert into hook-owned collection " + n))
            sweep.append((f, n, ops, sites, guarded))
        return findings, sweep


LAST_SWEEP = []
LAST_CHAINED = []
LAST_FRAMEWORK_NAMED = []


def check(texts, evidence_patch_filter=None, with_paths=False):
    """texts: {filename: source}, every plugin file. Returns (findings,
    closure): findings a list of (file, Class.Method, token), closure the set
    of Class.Method names reached. with_paths: also the parent map. The
    hook-owned collection sweep of the call is left in LAST_SWEEP."""
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
    for k, m in sorted(g.refused):
        findings.append((g.owner[k], k[0] + "." + k[1], "a member use whose receiver the walk cannot read: ." + m))
    LAST_CHAINED[:] = [g.chained]
    cf, sweep = g.coll_findings(seen)
    findings.extend(cf)
    LAST_SWEEP[:] = sweep
    LAST_FRAMEWORK_NAMED[:] = sorted(k[0] + "." + k[1] for k in g.props
                                     if k[1].split(".")[-1] in FRAMEWORK_PROPS and k in set().union(*g.by_name.values()))
    names = {k[0] + "." + k[1] for k in seen}
    if with_paths:
        return findings, names, {a[0] + "." + a[1]: b[0] + "." + b[1] for a, b in parent.items()}, g.fallbacks
    return findings, names
