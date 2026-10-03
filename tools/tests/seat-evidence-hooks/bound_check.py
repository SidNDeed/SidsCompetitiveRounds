"""F4 bound check (seat evidence fix pass 1): what the evidence path may do
while a game method waits.

Entry points are every method of every evidence [HarmonyPatch] class (the
patch-time TargetMethod/Prepare/Cleanup excluded) plus the two game-over
dispatches (SeatEvidence.Dispatch, CardDrawEvidence.Dispatch). The check
follows every call it can resolve to a method of the scanned classes
(qualified "Class.Method(" or unqualified within the same class), and
requires that no method in that closure contains a FORBIDDEN token:
logging, file or directory work, assembly scans, patch-info reads,
reflection lookups, budgeting, hashing and signing, the census text, queue
loads and saves, string building and formatting, coroutines and sends.
Comments and string literals are blanked before scanning, so a token named
in prose is not a finding.

    import bound_check; bound_check.check(texts) -> (findings, closure)
"""
import re

FORBIDDEN = [
    "Plugin.Log", "Debug.Log", "File.", "Directory.", "FileStream", "StreamWriter", "GetAssemblies",
    "GetPatchInfo", "AccessTools.", "Budget(", "Sha256Hex(", "Hmac(", "SeatEvidenceSig(", "Envelope(",
    "CensusText(", "CensusDigest(", "Save(", "Load(", "Enqueue", "StringBuilder", "string.Format", "$\"",
    "HitRecvLine(", "ShotObsLine(", "BlockMissLine(", "Json(", "StartCoroutine", "SeatEvidencePost",
]

PATCH_TIME = {"TargetMethod", "Prepare", "Cleanup"}
EXTRA_ENTRIES = [("SeatEvidence", "Dispatch"), ("CardDrawEvidence", "Dispatch")]
KEYWORDS = {"if", "for", "foreach", "while", "switch", "catch", "using", "lock", "return", "new", "typeof",
            "sizeof", "nameof", "default", "when", "base", "this"}


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
            start = i
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
            del start
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


CLASS_RE = re.compile(r"(?m)^(?P<attrs>(?:    \[[^\n]*\]\n)*)    (?:internal|public)\s+(?:static\s+)?(?:sealed\s+)?class\s+(?P<name>\w+)\b")
METHOD_RE = re.compile(r"(?m)^\s+(?:\[[^\n]*\]\s*\n\s+)*(?:(?:internal|private|public|protected|static|override|unsafe|extern)\s+)+"
                       r"(?P<ret>[\w<>\[\],\. ?]+?)\s+(?P<name>\w+)\s*\([^;{]*?\)\s*(?:where[^{]*)?\{")


def methods(text):
    """{(class, method): [body, ...]} for every top-level class in a blanked
    file, and the set of top-level classes carrying [HarmonyPatch]."""
    table, patches = {}, set()
    for m in CLASS_RE.finditer(text):
        name = m.group("name")
        end = braced(text, m.end())
        body = text[m.end():end]
        if "[HarmonyPatch" in m.group("attrs"):
            patches.add(name)
        for mm in METHOD_RE.finditer(body):
            mend = braced(body, mm.end() - 1)
            table.setdefault((name, mm.group("name")), []).append(body[mm.end() - 1:mend])
    return table, patches


CALL_RE = re.compile(r"(?<![\w.])(?:(?P<q>\w+)\.)?(?P<m>\w+)\s*\(")


def check(texts, evidence_patch_filter=None):
    """texts: {filename: source}. Returns (findings, closure) where findings
    is a list of (file, Class.Method, token) and closure the set of
    Class.Method names reached."""
    table, owner, entries = {}, {}, []
    for f, src in texts.items():
        t, patches = methods(blank(src.replace("\r\n", "\n")))
        for k, v in t.items():
            table.setdefault(k, []).extend(v)
            owner[k] = f
        for cls in patches:
            if evidence_patch_filter and not evidence_patch_filter(f, cls):
                continue
            for (c, m) in t:
                if c == cls and m not in PATCH_TIME:
                    entries.append((c, m))
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
                target = (q, m) if q else (k[0], m)
                if target in table and target not in seen:
                    stack.append(target)
    findings = []
    for k in sorted(seen):
        for body in table[k]:
            for tok in FORBIDDEN:
                if tok in body:
                    findings.append((owner[k], k[0] + "." + k[1], tok))
    return findings, {k[0] + "." + k[1] for k in seen}
