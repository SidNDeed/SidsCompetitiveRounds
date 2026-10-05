#!/usr/bin/env python3
"""Kept-view census (V7, F1; V8, F2; V9, N5): every consumer of the room's player/actor set.

Usage: python kept_view_census.py PLUGIN_DIR [CLASSES_TSV [--structure]]
Without CLASSES_TSV it prints one TSV row per (file, class chain, member, identifier): the hit
count, the first line and (V9) every hit's line. With CLASSES_TSV (rows: file, class chain,
member, identifier, class, reason, optional guard span "File.cs|Class|Member", optional required
accessors "Name|Name") it also checks the classification and exits 1 on any of:
  UNCLASSIFIED  a census row with no classification row;
  STALE         a classification row the census no longer finds;
  BADCLASS      a class other than V, F, R or N, an empty reason, a guard that names no span, or
                required accessors that are not identifiers joined by "|";
  NOVIEW        (V9: per occurrence) an occurrence in a V row that no view accessor (VIEW below)
                dominates, in a member whose guard span, if named, reads none either;
  NOFENCE       (V9: per occurrence) an occurrence in an F row that none of MasterMaySend(,
                MasterKept(, MasterFenced(, FenceMaster( dominates, likewise.
V9 (N5): "RoomPlayers" is every member access named Players, whatever its receiver (a local alias
of PhotonNetwork.CurrentRoom, a parameter, the literal CurrentRoom), and "GetPlayer" is every
.GetPlayer( call; and the guard check is per OCCURRENCE, not per member-and-identifier aggregate.
An occurrence is dominated by an accessor set G when G is called (a) in the occurrence's own
statement, (b) in the header of any block of the same member that encloses it, (c) in an earlier
top-level early-exit statement ("if (...) ... return|continue|break|throw|yield break") of any
such block, or (d) in the condition of the first statement of the block the occurrence's own
statement controls (a loop or if header whose body starts by testing G); or (e) the occurrence is
itself a call of G. So a guarded branch no longer masks an unguarded sibling in the same member.
The member's own name never guards it: a call of the member itself is not a read of G, and an
occurrence whose identifier IS the member's name (its declaration, e.g. a view accessor's own, or
a callback's) is not a consumer, so it passes only when the member's span reads G (V8's rule);
the body's own occurrences are each checked by dominance.
A row whose identifier is written "Ident#n" classifies only the n-th occurrence of Ident in that
member (1-based, in file order) and overrides the member's row for it.
A row that names required accessors (V8) passes its V or F check only on a call of one of THOSE
names, so a span shared with an unrelated view or fence read cannot pass through that read.
--structure checks only UNCLASSIFIED, STALE and BADCLASS (classification completeness).
Exit 0 when the census is clean, 1 when it is not, 3 on a usage or read error.
Comments and string literals are blanked first (the code inside an interpolated string's
holes is kept), so a mention in a comment or a log string is not a consumer.
A span is the member (method, accessor, lambda-bodied member or field initialiser) that owns
the hit. The check is necessary, not sufficient: dominance is read from the block structure,
not from a control-flow graph (a negated early exit reads as a guard), and it proves the consumer
is wired to the view or the fence; the per-site controls prove what it does with it.
"""
import bisect
import os
import re
import sys

IDENTS = [
    ("players", r"\.players\b"),
    ("PlayerList", r"PhotonNetwork\s*\.\s*PlayerList\b"),
    ("PlayerListOthers", r"PhotonNetwork\s*\.\s*PlayerListOthers\b"),
    ("RoomPlayers", r"\.\s*Players\b"),
    ("GetPlayer", r"\.\s*GetPlayer\s*\("),
    ("ActiveFighters", r"\bActiveFighters\s*\("),
    ("ActiveFighterCount", r"\bActiveFighterCount\s*\("),
    ("OtherActiveFighterCount", r"\bOtherActiveFighterCount\s*\("),
    ("OtherActiveFighters", r"\bOtherActiveFighters\s*\("),
    ("AlivePlayers", r"\bAlivePlayers\s*\("),
    ("GetPlayerWithActorID", r"\bGetPlayerWithActorID\s*\("),
    ("GetPlayerWithID", r"\bGetPlayerWithID\s*\("),
    ("GetPlayersInTeam", r"\bGetPlayersInTeam\s*\("),
    ("PlayerCount", r"\.PlayerCount\b"),
    ("PresentNonSpectators", r"\bPresentNonSpectators\s*\("),
    ("KeptPlayers", r"\bKeptPlayers\s*\("),
    ("IsKeptActor", r"\bIsKeptActor\s*\("),
    ("MasterMaySend", r"\bMasterMaySend\s*\("),
    ("MasterKept", r"\bMasterKept\s*\("),
    ("MasterFenced", r"\bMasterFenced\s*\("),
    ("IsMasterClient", r"\bIsMasterClient\b"),
    ("MasterClient", r"PhotonNetwork\s*\.\s*MasterClient\b"),
    ("SetMasterClient", r"\bSetMasterClient\s*\("),
    ("OnPlayerEnteredRoom", r"\bOnPlayerEnteredRoom\s*\("),
    ("OnPlayerLeftRoom", r"\bOnPlayerLeftRoom\s*\("),
    ("NotifyPlayerLeftRoom", r"\bNotifyPlayerLeftRoom\s*\("),
    ("OnPlayerPropertiesUpdate", r"\bOnPlayerPropertiesUpdate\s*\("),
    ("OnMasterClientSwitched", r"\bOnMasterClientSwitched\s*\("),
    ("Sender", r"\.Sender\b"),
    ("RecordLeaver", r"\bRecordLeaver\s*\("),
    ("Leavers", r"\bLeavers\b"),
]
IDENTS = [(n, re.compile(p)) for n, p in IDENTS]
VIEW = re.compile(r"\b(?:KeptPlayers|IsKeptActor|IsQuarantined|IsQuarantinedActor|LocalSitsOut"
                  r"|ActiveFighters|ActiveFighterCount|OtherActiveFighterCount|OtherActiveFighters"
                  r"|AlivePlayers)\s*\(")
FENCE = re.compile(r"\b(?:MasterMaySend|MasterKept|MasterFenced|FenceMaster)\s*\(")
EXIT = re.compile(r"\b(?:return|continue|break|throw)\b|\byield\s+break\b")
CONTROL = re.compile(r"\s*(?:else\s+)?(?:if|for|foreach|while|using|lock)\s*\(")


def _sp(ch):
    return ch if ch == "\n" else " "


class _Blank:
    def __init__(self, s):
        self.s, self.n, self.out = s, len(s), []

    def code(self, i, hole=False):
        s, n, depth = self.s, self.n, 0
        while i < n:
            c = s[i]
            nx = s[i + 1] if i + 1 < n else ""
            if c == "/" and nx == "/":
                j = s.find("\n", i)
                j = n if j < 0 else j
                self.out.extend(_sp(x) for x in s[i:j])
                i = j
                continue
            if c == "/" and nx == "*":
                j = s.find("*/", i + 2)
                j = n if j < 0 else j + 2
                self.out.extend(_sp(x) for x in s[i:j])
                i = j
                continue
            if c in "$@" or c == '"':
                k, verb, interp = i, False, False
                while k < n and s[k] in "$@":
                    verb = verb or s[k] == "@"
                    interp = interp or s[k] == "$"
                    k += 1
                if k < n and s[k] == '"':
                    self.out.extend(_sp(x) for x in s[i:k + 1])
                    i = self.string(k + 1, verb, interp)
                    continue
                self.out.append(c)
                i += 1
                continue
            if c == "'":
                j = i + 1
                while j < n and s[j] != "'" and s[j] != "\n":
                    j += 2 if s[j] == "\\" else 1
                j = min(j + 1, n)
                self.out.extend(_sp(x) for x in s[i:j])
                i = j
                continue
            if hole:
                if c == "{":
                    depth += 1
                elif c == "}":
                    if depth == 0:
                        return i
                    depth -= 1
            self.out.append(c)
            i += 1
        return n

    def string(self, i, verbatim, interp):
        s, n = self.s, self.n
        while i < n:
            c = s[i]
            if interp and c == "{":
                if i + 1 < n and s[i + 1] == "{":
                    self.out.extend("  ")
                    i += 2
                    continue
                self.out.append(" ")
                end = self.code(i + 1, hole=True)
                if end < n:
                    self.out.append(" ")
                i = end + 1
                continue
            if interp and c == "}" and i + 1 < n and s[i + 1] == "}":
                self.out.extend("  ")
                i += 2
                continue
            if verbatim:
                if c == '"':
                    if i + 1 < n and s[i + 1] == '"':
                        self.out.extend("  ")
                        i += 2
                        continue
                    self.out.append(" ")
                    return i + 1
                self.out.append(_sp(c))
                i += 1
            else:
                if c == "\\" and i + 1 < n:
                    self.out.append(" ")
                    self.out.append(_sp(s[i + 1]))
                    i += 2
                    continue
                if c == '"':
                    self.out.append(" ")
                    return i + 1
                if c == "\n":
                    self.out.append("\n")
                    return i + 1
                self.out.append(" ")
                i += 1
        return n


def blank(src):
    b = _Blank(src)
    b.code(0)
    out = "".join(b.out)
    assert len(out) == len(src) and out.count("\n") == src.count("\n")
    return out


CLASS_RE = re.compile(r"\b(class|struct|interface|enum)\s+(\w+)")
NS_RE = re.compile(r"\bnamespace\b")
NAME_PAREN = re.compile(r"(\w+)\s*(?:<[^()]*>)?\s*\(")
LAST_IDENT = re.compile(r"(\w+)\s*$")
KEYWORDS = ("if", "for", "foreach", "while", "switch", "using", "lock", "catch")


def member_name(decl):
    d = re.sub(r"^(\[[^\]]*\]\s*)+", "", " ".join(decl.split()))
    if "=>" in d:
        d = d.split("=>")[0]
    m = next(NAME_PAREN.finditer(d), None)
    if m and m.group(1) not in KEYWORDS:
        return m.group(1)
    m = LAST_IDENT.search(d)
    return m.group(1) if m else "?"


def spans(clean):
    owner, stack, start = [None] * len(clean), [], 0
    for i, c in enumerate(clean):
        top = stack[-1][0] if stack else "ns"
        if c == "{":
            decl = clean[start:i]
            cm = CLASS_RE.search(decl)
            if cm and top in ("ns", "class", "namespace"):
                stack.append(("class", cm.group(2)))
            elif NS_RE.search(decl) and top in ("ns", "namespace"):
                stack.append(("namespace", ""))
            elif top == "class":
                stack.append(("member", member_name(decl)))
                chain = tuple(e[1] for e in stack if e[0] == "class")
                for k in range(start, i):
                    owner[k] = (chain, stack[-1][1])
            else:
                stack.append(("block", ""))
            start = i + 1
        elif c == "}":
            if stack:
                stack.pop()
            start = i + 1
        elif c == ";":
            if top == "class":
                decl = clean[start:i]
                name = member_name(decl) if ("=>" in decl or "(" in decl) else "field:" + member_name(decl.split("=")[0])
                chain = tuple(e[1] for e in stack if e[0] == "class")
                for k in range(start, i + 1):
                    owner[k] = (chain, name)
            start = i + 1
        if owner[i] is None:
            chain = tuple(e[1] for e in stack if e[0] == "class")
            mem = next((e[1] for e in reversed(stack) if e[0] == "member"), "?")
            owner[i] = (chain, mem)
    return owner, len(stack)


def braces(clean):
    match, st = {}, []
    for i, c in enumerate(clean):
        if c == "{":
            st.append(i)
        elif c == "}" and st:
            j = st.pop()
            match[j], match[i] = i, j
    return match


def _prev_sep(clean, i, lo):
    k = i - 1
    while k >= lo and clean[k] not in ";{}":
        k -= 1
    return k


def _next_sep(clean, i, hi):
    k = i
    while k < hi and clean[k] not in ";{}":
        k += 1
    return k


def _top_statements(clean, match, a, b):
    """Top-level statements of the block body clean[a:b], as (start, end) pairs."""
    out, k, s, paren = [], a, a, 0
    while k < b:
        c = clean[k]
        if c == "(":
            paren += 1
        elif c == ")":
            paren = max(0, paren - 1)
        elif c == "{" and k in match:
            k = match[k]
            rest = clean[k + 1:b].lstrip()
            if paren == 0 and not re.match(r"(?:else|catch|finally|while)\b", rest):
                out.append((s, k + 1))
                s = k + 1
        elif c == ";" and paren == 0:
            out.append((s, k + 1))
            s = k + 1
        k += 1
    return out


def dominated(ctx, o, rx):
    clean, match, owner = ctx
    own = owner[o]
    selfcall = re.compile(r"\b" + re.escape(own[1]) + r"\s*\(")

    def hit(t):
        # the member's own name is never its own guard (V8's reads() rule): a view accessor's
        # declaration does not guard the body that must itself read the view
        return rx.search(selfcall.sub(" ", t)) is not None

    lo = o
    while lo > 0 and owner[lo - 1] == own:
        lo -= 1
    hi = o
    while hi < len(clean) and owner[hi] == own:
        hi += 1
    for at in (o, o + 1):
        m = rx.match(clean, at)
        if m and not selfcall.match(clean, at):
            return True
    s = _prev_sep(clean, o, lo) + 1
    e = _next_sep(clean, o, hi)
    if hit(clean[s:e]):
        return True
    for p in range(lo, o):
        if clean[p] != "{" or match.get(p, -1) <= o:
            continue
        h = _prev_sep(clean, p, lo) + 1
        if hit(clean[h:p]):
            return True
        for (a, b) in _top_statements(clean, match, p + 1, o):
            if b > o:
                break
            st = clean[a:b]
            if CONTROL.match(st) and hit(st) and EXIT.search(st):
                return True
    if e < hi and clean[e] == "{" and CONTROL.match(clean[s:e]) and e in match:
        body = _top_statements(clean, match, e + 1, match[e])
        if body:
            first = clean[body[0][0]:body[0][1]]
            m = re.match(r"\s*if\s*\(", first)
            if m:
                depth, k = 1, m.end()
                while k < len(first) and depth:
                    depth += {"(": 1, ")": -1}.get(first[k], 0)
                    k += 1
                if hit(first[m.end():k]):
                    return True
    return False


def census(root):
    rows, text, occ, ctx = {}, {}, {}, {}
    for fn in sorted(os.listdir(root)):
        if not fn.endswith(".cs"):
            continue
        with open(os.path.join(root, fn), encoding="utf-8", errors="replace") as fh:
            src = fh.read().replace("\r\n", "\n")
        clean = blank(src)
        owner, depth = spans(clean)
        if depth:
            sys.stderr.write("UNBALANCED %s depth=%d\n" % (fn, depth))
        ctx[fn] = (clean, braces(clean), owner)
        starts = [0] + [k + 1 for k, ch in enumerate(clean) if ch == "\n"]
        run = 0
        for k in range(1, len(owner) + 1):
            if k == len(owner) or owner[k] != owner[run]:
                chain, mem = owner[run]
                text.setdefault((fn, ".".join(chain), mem), []).append(clean[run:k])
                run = k
        for ident, rx in IDENTS:
            for m in rx.finditer(clean):
                chain, mem = owner[m.start()]
                key = (fn, ".".join(chain), mem, ident)
                line = bisect.bisect_right(starts, m.start())
                if key not in rows:
                    rows[key] = [0, line]
                rows[key][0] += 1
                occ.setdefault(key, []).append((m.start(), line))
    return rows, {k: "".join(v) for k, v in text.items()}, occ, ctx


def reads(rx, span, own):
    if own:
        span = re.sub(r"\b" + re.escape(own) + r"\s*\(", " ", span)
    return rx.search(span) is not None


def check(rows, text, occ, ctx, tsv, structure):
    classes, guards, needs, bad = {}, {}, {}, []
    with open(tsv, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            f = line.rstrip("\n").split("\t")
            if len(f) < 6 or f[4] not in ("V", "F", "R", "N") or not f[5].strip():
                bad.append("BADCLASS " + line.strip())
                continue
            guard = tuple(f[6].split("|")) if len(f) > 6 and f[6].strip() else None
            if guard is not None and guard not in text:
                bad.append("BADCLASS guard names no span: " + line.strip())
                continue
            need = f[7].strip() if len(f) > 7 and f[7].strip() else None
            if need is not None and not re.fullmatch(r"\w+(?:\|\w+)*", need):
                bad.append("BADCLASS required accessors: " + line.strip())
                continue
            classes[tuple(f[:4])] = f[4]
            guards[tuple(f[:4])] = guard
            needs[tuple(f[:4])] = re.compile(r"\b(?:" + need + r")\s*\(") if need else None
    seen = set()
    for key in sorted(rows):
        for n, (o, line) in enumerate(occ[key], 1):
            okey = key[:3] + ("%s#%d" % (key[3], n),)
            ckey = okey if okey in classes else key
            cls = classes.get(ckey)
            if cls is None:
                bad.append("UNCLASSIFIED %s|%s|%s|%s line %d" % (key + (line,)))
                continue
            seen.add(ckey)
            if structure or cls not in ("V", "F"):
                continue
            rx = needs.get(ckey) or (VIEW if cls == "V" else FENCE)
            if key[3] == key[2]:
                # the member's own name (its declaration, or a call of itself) is not a
                # consumer: the member-level rule applies to it (V8, own name excluded),
                # and the body's own occurrences are each checked on their own
                ok = reads(rx, text[key[:3]], key[2])
            else:
                ok = dominated(ctx[key[0]], o, rx)
            if not ok and guards.get(ckey) is not None:
                ok = reads(rx, text[guards[ckey]], guards[ckey][2])
            if not ok:
                bad.append(("NOVIEW" if cls == "V" else "NOFENCE") + " %s|%s|%s|%s line %d" % (key + (line,)))
    for key in sorted(classes):
        if key not in seen and key not in rows:
            bad.append("STALE %s|%s|%s|%s" % key)
    return bad


def main(argv):
    if len(argv) < 2 or not os.path.isdir(argv[1]):
        print(__doc__)
        return 3
    rows, text, occ, ctx = census(argv[1])
    if len(argv) < 3:
        for key, (count, line) in sorted(rows.items()):
            print("\t".join(list(key) + [str(count), str(line), ",".join(str(l) for _, l in occ[key])]))
        return 0
    try:
        bad = check(rows, text, occ, ctx, argv[2], "--structure" in argv[3:])
    except OSError as exc:
        print("cannot read %s: %s" % (argv[2], exc))
        return 3
    for b in bad:
        print(b)
    hits = sum(len(v) for v in occ.values())
    print("kept-view census: %d rows, %d spans, %d occurrences, %d problem(s)"
          % (len(rows), len({k[:3] for k in rows}), hits, len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
