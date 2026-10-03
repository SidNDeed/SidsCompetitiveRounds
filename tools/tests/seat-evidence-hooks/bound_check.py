"""F4 bound check (seat evidence fix passes 1 and 2): what the evidence path
may do while a game method waits.

Entry points are every method of every evidence [HarmonyPatch] class (the
patch-time TargetMethod/Prepare/Cleanup excluded) plus the game-over and cut
dispatches (SeatEvidence.Dispatch, CardDrawEvidence.Dispatch, which
GameStateWatcher calls from its result paths) and the room-exit edges. The
check follows every call it can resolve to a method of the scanned files:
  * qualified by a class name ("Class.Method("), or by a using alias of one
    ("C.Method(" for SeatEvidenceCore, "K.Method(" for CardDrawEvidenceCore);
  * unqualified, within the same top-level class (nested classes' methods are
    filed under their top-level class);
  * qualified by a field or local ("_samples.AgeBuckets("): to EVERY scanned
    method of that name such a call can reach: every instance method, and
    every static method of a nested class (a top-level class's static method
    is reachable only through its class name, above). An over-approximation:
    it can only add methods.
It requires of every method in that closure:
  1. no FORBIDDEN token: logging, file or directory work, assembly scans,
     patch-info reads, reflection lookups, budgeting, hashing and signing, the
     census, queue loads and saves, string building and formatting,
     coroutines, sends, and the named variable aggregations (age buckets,
     drift, cadence, percentiles);
  2. no loop that is not hard-capped (fix pass 2): no foreach, no while, no
     do; a for loop only when its header names a *_CAP constant, the hard
     bound of the snapshot it copies.
Comments and string literals are blanked before scanning, so a token named in
prose is not a finding.

    import bound_check; bound_check.check(texts) -> (findings, closure)
"""
import re

FORBIDDEN = [
    "Plugin.Log", "Debug.Log", "File.", "Directory.", "FileStream", "StreamWriter", "GetAssemblies",
    "GetPatchInfo", "AccessTools.", "Budget(", "Sha256Hex(", "Hmac(", "SeatEvidenceSig(", "Envelope(",
    "CensusText(", "CensusDigest(", "Save(", "Load(", "Enqueue", "StringBuilder", "string.Format", "$\"",
    "HitRecvLine(", "ShotObsLine(", "BlockMissLine(", "Json(", "StartCoroutine", "SeatEvidencePost",
    # fix pass 2: the variable aggregations a game-over dispatch used to run
    "AgeBuckets(", "DriftTriple(", "Five(", "Four(", "Three(", "Percentile(", "OtherCaps(", "CloseHand(",
]

PATCH_TIME = {"TargetMethod", "Prepare", "Cleanup"}
EXTRA_ENTRIES = [("SeatEvidence", "Dispatch"), ("CardDrawEvidence", "Dispatch"),
                 ("SeatEvidence", "RoomExit"), ("CardDrawEvidence", "RoomExit")]
KEYWORDS = {"if", "for", "foreach", "while", "switch", "catch", "using", "lock", "return", "new", "typeof",
            "sizeof", "nameof", "default", "when", "base", "this"}
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


CLASS_RE = re.compile(r"(?m)^(?P<attrs>(?:    \[[^\n]*\]\n)*)    (?:internal|public)\s+(?:static\s+)?(?:sealed\s+)?class\s+(?P<name>\w+)\b")
METHOD_RE = re.compile(r"(?m)^\s+(?:\[[^\n]*\]\s*\n\s+)*(?P<mods>(?:(?:internal|private|public|protected|static|override|unsafe|extern)\s+)+)"
                       r"(?P<ret>[\w<>\[\],\. ?]+?)\s+(?P<name>\w+)\s*\([^;{]*?\)\s*(?:where[^{]*)?\{")


def methods(text):
    """{(class, method): [body, ...]} for every top-level class in a blanked
    file, the set of top-level classes carrying [HarmonyPatch], and the set of
    keys an instance-qualified call can reach (an instance method, or a static
    method of a nested class)."""
    table, patches, by_instance = {}, set(), set()
    for m in CLASS_RE.finditer(text):
        name = m.group("name")
        end = braced(text, m.end())
        body = text[m.end():end]
        if "[HarmonyPatch" in m.group("attrs"):
            patches.add(name)
        for mm in METHOD_RE.finditer(body):
            mend = braced(body, mm.end() - 1)
            key = (name, mm.group("name"))
            table.setdefault(key, []).append(body[mm.end() - 1:mend])
            pre = body[:mm.start()]
            nested = pre.count("{") - pre.count("}") > 1
            if nested or "static" not in mm.group("mods").split():
                by_instance.add(key)
    return table, patches, by_instance


CALL_RE = re.compile(r"(?<![\w.])(?:(?P<q>\w+)\.)?(?P<m>\w+)\s*\(")
LOOP_RE = re.compile(r"\b(?P<kw>foreach|while|for)\s*\(|\bdo\s*\{")


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


def check(texts, evidence_patch_filter=None):
    """texts: {filename: source}. Returns (findings, closure) where findings
    is a list of (file, Class.Method, token) and closure the set of
    Class.Method names reached."""
    table, owner, entries, aliases = {}, {}, [], {}
    by_name = {}
    for f, src in texts.items():
        src = src.replace("\r\n", "\n")
        for a in ALIAS_RE.finditer(src):
            aliases[a.group(1)] = a.group(2)
        t, patches, inst = methods(blank(src))
        for k, v in t.items():
            table.setdefault(k, []).extend(v)
            owner[k] = f
            if k in inst:
                by_name.setdefault(k[1], set()).add(k)
        for cls in patches:
            if evidence_patch_filter and not evidence_patch_filter(f, cls):
                continue
            for (c, m) in t:
                if c == cls and m not in PATCH_TIME:
                    entries.append((c, m))
    classes = {k[0] for k in table}
    for e in EXTRA_ENTRIES:
        if e in table:
            entries.append(e)
    seen, stack = set(), list(entries)
    while stack:
        k = stack.pop()
        if k in seen or k not in table:
            continue
        seen.add(k)
        for body in table[k]:
            for c in CALL_RE.finditer(body):
                q, m = c.group("q"), c.group("m")
                if m in KEYWORDS:
                    continue
                if q is None:
                    targets = [(k[0], m)]
                elif q in classes:
                    targets = [(q, m)]
                elif q in aliases:
                    targets = [(aliases[q], m)]
                else:
                    targets = sorted(by_name.get(m, ()))
                for target in targets:
                    if target in table and target not in seen:
                        stack.append(target)
    findings = []
    for k in sorted(seen):
        for body in table[k]:
            for tok in FORBIDDEN:
                if tok in body:
                    findings.append((owner[k], k[0] + "." + k[1], tok))
            for tok in loop_findings(body):
                findings.append((owner[k], k[0] + "." + k[1], tok))
    return findings, {k[0] + "." + k[1] for k in seen}
