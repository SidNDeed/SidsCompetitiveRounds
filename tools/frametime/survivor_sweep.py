#!/usr/bin/env python3
"""survivor_sweep.py - the stated write sweep behind tools/frametime/SURVIVORS.md.

Read-only over plugin/*.cs. Deterministic: files, fields and sites are walked in sorted order.

Per component it (1) declares every field (static fields of every class declared in the component's
files; instance fields of every class the component HOLDS, found by type closure from those static
fields), (2) counts the write operations per field on comment- and string-blanked code, (3) classifies
each written field as CONSTRUCTION-ONLY, RESET AT THE POINT or SURVIVES, (4) marks a survivor READ LIVE
when a non-store access of it sits in a member reached from a live hook or tick.

Then it parses SURVIVORS.md and fails (exit 1) when the table disagrees with the sweep.

  python -I -B survivor_sweep.py             sweep + table check; prints SURVIVOR SWEEP PASS on agreement
  python -I -B survivor_sweep.py --detail    also prints every survivor with its write and live-read sites
  python -I -B survivor_sweep.py --selftest  negative controls on in-memory copies of the table
  python -I -B survivor_sweep.py --write-md  regenerate the sweep's own text in SURVIVORS.md (blanked-line counts,
                                             counts table, declared / writers / live-readers columns, capacity lines)

It also checks gate_specs/a3.py against the table (ruling FRAME-TIME-ROUND-R2): every row's kind and proof, a zero
row only where no write of its fields is reachable live, and every live reader of a dependent row counting it with
FtA3.Read in its FrameTime text (`--detail` lists the readers per row).
"""
import bisect
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PLUGIN = os.path.join(ROOT, "plugin")
MD_PATH = os.path.join(HERE, "SURVIVORS.md")

# Compile symbols treated as UNDEFINED (the release build). Every other #if symbol keeps all branches.
UNDEFINED = {"SCR_FRAMETIME", "SCR_CARD_EVIDENCE_TEST_DEALER", "SCR_CARD_EVIDENCE_TEST_GATE"}

# Source of each component. A slice is (file, first-line regex, end-line regex): the slice runs from the
# first match up to (not including) the end match. Everything outside a slice is blanked.
COMPONENTS = [
    ("CombatEvidence", ["CombatEvidence.cs", "CombatEvidenceCore.cs", "CombatEvidencePerf.cs",
                        "CombatEvidenceWire.g.cs"]),
    ("SeatEvidence", ["SeatEvidence.cs", "SeatEvidenceCore.cs"]),
    ("HitEvidence", ["HitEvidence.cs", "HitEvidenceCore.cs"]),
    ("PointEvidence", [("PoisonSync.cs", r"^\s*internal static class PointEvidence\b",
                        r"^\s*internal static class PoisonPointBoundaryPatch\b")]),
    ("IdentityClockEvidence", ["IdentityClockEvidence.cs", "IdentityClockCore.cs"]),
    ("CardDrawEvidence", ["CardDrawEvidence.cs", "CardDrawEvidenceCore.cs"]),
    ("PeerBuild", ["PeerBuild.cs", "PeerBuildCore.cs"]),
]
COMP_NAMES = [c[0] for c in COMPONENTS]

# LIVE ROOTS: the entries INVENTORY.md marks live "yes" or "both" (hooks and ticks reached in live combat).
# ("Class", "*") = every member of that patch class. ("Class", "Name") = members of that name.
LIVE_ROOTS = [
    # CombatEvidence: CE-c7 Tick, CE-c8 RpcSent, CE-p1..CE-p19 (all yes)
    ("CombatEvidence", "Tick"), ("CombatEvidence", "RpcSent"),
    ("CombatEvidence_AttackPatch", "*"), ("CombatEvidence_InitAmmoPatch", "*"),
    ("CombatEvidence_InitNoAmmoPatch", "*"), ("CombatEvidence_InitSeparatePatch", "*"),
    ("CombatEvidence_ReloadPatch", "*"), ("CombatEvidence_HitPatch", "*"), ("CombatEvidence_ContactPatch", "*"),
    ("CombatEvidence_BlockPatch", "*"), ("CombatEvidence_TryBlockPatch", "*"), ("CombatEvidence_DealtPatch", "*"),
    ("CombatEvidence_TargetBouncePatch", "*"), ("CombatEvidence_EdgeBouncePatch", "*"),
    ("CombatEvidence_SyncPatch", "*"), ("CombatEvidence_ForcePatch", "*"), ("CombatEvidence_DamagePatch", "*"),
    ("CombatEvidence_DiePatch", "*"), ("CombatEvidence_DiePhoenixPatch", "*"),
    ("CombatEvidence_FindTargetPatch", "*"), ("CombatEvidence_MovePatch", "*"),
    # SeatEvidence: SE-c2/c16/c17/c24 CombatLive, c14 SwMs, c15 RpcTop, c32 AddPush, c34..c44, c45 CombatState,
    # c50 NoteView, c52 CompatTick, c53 Tick; SE-p1..p3
    ("SeatEvidence", "CombatLive"), ("SeatEvidence", "SwMs"), ("SeatEvidence", "RpcTop"),
    ("SeatEvidence", "AddPush"), ("SeatEvidence", "EnterRpc"), ("SeatEvidence", "ExitRpc"),
    ("SeatEvidence", "DamageGate"), ("SeatEvidence", "DamageArrived"), ("SeatEvidence", "BlockEnter"),
    ("SeatEvidence", "BlockExit"), ("SeatEvidence", "ShotArrived"), ("SeatEvidence", "HitEnter"),
    ("SeatEvidence", "HitExit"), ("SeatEvidence", "CombatState"), ("SeatEvidence", "NoteView"),
    ("SeatEvidence", "CompatTick"), ("SeatEvidence", "Tick"),
    ("SeatEvidence_RpcSendPatch", "*"), ("SeatEvidence_DoBlockPatch", "*"), ("SeatEvidence_TryBlockMePatch", "*"),
    # HitEvidence: HE-c5 Drain; HE-p1..HE-p9 (HE-p10/p11 are game-start boundaries)
    ("HitEvidence", "Drain"),
    ("HitEvidence_ExecuteRpcPatch", "*"), ("HitEvidence_DamagePatch", "*"), ("HitEvidence_ForcePatch", "*"),
    ("HitEvidence_DotPatch", "*"), ("HitEvidence_BlockPatch", "*"), ("HitEvidence_SpawnAmmoPatch", "*"),
    ("HitEvidence_SpawnNoAmmoPatch", "*"), ("HitEvidence_SpawnSeparatePatch", "*"), ("HitEvidence_ImpactPatch", "*"),
    # PointEvidence: PT-c1 Point (read by CombatEvidence.PointStart: a boundary, so not a root), PT-c5 Drain, PT-p1
    ("PointEvidence", "Drain"), ("SawPointEvidencePatch", "*"),
    # IdentityClockEvidence: IC-c6 Tick, IC-p1, IC-p4, IC-p5 (the post-boot no-op postfix on live targets)
    ("IdentityClockEvidence", "Tick"), ("IdentityClock_ExecuteRpcPatch", "*"), ("IdentityClock_MovementPatch", "*"),
    ("PostBoot", "Noop"),
    # CardDrawEvidence: CD-c6 Tick, CD-c7 EnsureCensusDump (every frame); CD-p1..p6 are pick phase ("no")
    ("CardDrawEvidence", "Tick"), ("CardDrawEvidence", "EnsureCensusDump"),
    # PeerBuild: PB-c2 StageBuildProp, PB-c3 Tick
    ("PeerBuild", "StageBuildProp"), ("PeerBuild", "Tick"),
]

# POINT-BOUNDARY ROOTS: the members that run once at a point start or a point end (ZERO-STATE.md "reset").
POINT_ROOTS = [
    ("CombatEvidence", "PointStart"), ("CombatEvidence", "PointEnd"), ("CombatEvidence", "PointReset"),
    ("CombatEvidence", "PointClose"),
    ("HitEvidence", "PointEnd"),
    ("PointEvidence", "PointEnd"), ("PointEndEvidencePatch", "*"),
    ("IdentityClockEvidence", "PointStart"), ("IdentityClock_PointStartPatch", "*"),
    ("IdentityClock_MovePlayersPatch", "*"), ("ClockBook", "PointStart"), ("ClockBook", "ClosePoint"),
]

# STOP: members reached from a live root only on a non-live branch (or at a game/room/quit boundary).
# Not traversed and not live. Each carries its reason (the guard that keeps it out of live combat).
STOP = [
    ("CombatEvidence", "BuildCaptures", "Tick calls it only after `if (SeatEvidence.CombatLive()) return;`"),
    ("CombatEvidence", "BeginGame", "game boundary (OnMatchStarted)"),
    ("CombatEvidence", "Dispatch", "game boundary (OnGameOver / SeatEvidenceCut)"),
    ("CombatEvidence", "RoomExit", "room boundary"),
    ("CombatEvidence", "FlushOnQuit", "Application.quitting"),
    ("SeatEvidence", "BeginGame", "game boundary"), ("SeatEvidence", "ResetGame", "game boundary"),
    ("SeatEvidence", "Handover", "game boundary"), ("SeatEvidence", "RoomExit", "room boundary"),
    ("SeatEvidence", "Dispatch", "game boundary"), ("SeatEvidence", "FlushOnQuit", "quitting"),
    ("SeatEvidence", "BuildCaptures", "SeatEvidence.Tick runs it behind the combat return"),
    ("SeatEvidence", "Aggregate", "from BuildCaptures, behind the combat return"),
    ("SeatEvidence", "Pump", "SeatEvidence.Tick runs it behind the combat return"),
    ("HitEvidence", "GameEnd", "game boundary"), ("HitEvidence", "ResetForRoomExit", "room boundary"),
    ("PointEvidence", "GameOverCheck", "game boundary (RPCA_NextRound postfix)"),
    ("PointEvidence", "ResetForRoomExit", "room boundary"),
    ("IdentityClockEvidence", "BeginGame", "game boundary"), ("IdentityClockEvidence", "Dispatch", "game boundary"),
    ("IdentityClockEvidence", "FlushOnQuit", "quitting"),
    ("IdentityClockEvidence", "BuildCaptures", "Tick runs it behind the combat return"),
    ("IdentityClockEvidence", "RequestSurvey", "only when picking and not in combat"),
    ("CardDrawEvidence", "BuildPending", "Tick runs it behind the combat return"),
    ("CardDrawEvidence", "Dispatch", "game boundary"), ("CardDrawEvidence", "RoomExit", "room boundary"),
    ("CardDrawEvidence", "FlushOnQuit", "quitting"),
]

# LIVE_CUT: a live root whose body is live only up to its combat gate. Calls and reads after the gate's
# match are not live. (Class, Member, gate regex, reason).
LIVE_CUT = [
    ("CombatEvidence", "Tick", r"if\s*\(\s*SeatEvidence\.CombatLive\(\)\s*\)\s*return\s*;", "combat return"),
    ("SeatEvidence", "Tick", r"if\s*\(\s*CombatLive\(\)\s*\)\s*return\s*;", "combat return"),
    ("IdentityClockEvidence", "Tick", r"if\s*\(\s*combat\s*\)\s*\{[^}]*return\s*;\s*\}", "combat return"),
    ("CardDrawEvidence", "Tick", r"if\s*\(\s*SeatEvidence\.CombatLive\(\)\s*\)\s*return\s*;", "combat return"),
    ("CardDrawEvidence", "EnsureCensusDump", r"PhotonNetwork\.InRoom\s*\)\s*return\s*;",
     "returns in a room; live combat is always in a room"),
    ("PeerBuild", "StageBuildProp", r"if\s*\(\s*PhotonNetwork\.InRoom\s*\)\s*return\s*;",
     "returns in a room"),
    ("SeatEvidence", "CompatTick", r"if\s*\(\s*CombatLive\(\)\s*\)\s*return\s*;", "combat return (first line)"),
    ("Survey", "Step", r"if\s*\(\s*C\.CombatRead\.Live\(combatState\)\s*\)\s*\{[^}]*return\s+0\s*;\s*\}",
     "combat return (the in-combat Step call passes a live state)"),
]

# GUARDED_EDGES: a call inside a live member that sits behind a non-live guard. (Class, Member, callee, reason)
GUARDED_EDGES = [
    ("IdentityClockEvidence", "Slice", "CheckRun", "behind `picking && !_wasPicking && !combat`"),
    ("IdentityClockEvidence", "Slice", "ReadPubFps", "behind `!combat && SwMs >= _nextFpsReadMs`"),
]

# BCL collection types whose mutating methods count as writes of the field itself.
BCL_COLL = re.compile(r"^(System\.Collections\.Generic\.)?(List|Dictionary|HashSet|Queue|Stack|SortedDictionary|"
                      r"SortedList|SortedSet|LinkedList)\s*<")
MUTATORS = ("Add|Insert|RemoveAt|Clear|Remove|RemoveAll|RemoveRange|AddRange|InsertRange|Enqueue|Dequeue|"
            "Push|Pop|Sort|Reverse|TryAdd|TryDequeue|UnionWith|ExceptWith|IntersectWith|TrimExcess")
LINEAR_CALLS = re.compile(r"\.\s*(IndexOf|Contains|ContainsValue|Remove|RemoveAt|RemoveAll|Insert|Clear|Sort|"
                          r"ToArray|ToList|CopyTo|Sum|Max|Min|Any|All|Where|Select|Count\s*\(|Find|Exists)\b")
KEYWORDS = set("""abstract as base bool break byte case catch char checked class const continue decimal default
delegate do double else enum event explicit extern false finally fixed float for foreach goto if implicit in int
interface internal is lock long namespace new null object operator out override params private protected public
readonly ref return sbyte sealed short sizeof stackalloc static string struct switch this throw true try typeof
uint ulong unchecked unsafe ushort using virtual void volatile while var nameof when get set value yield await
async partial where""".split())
MODIFIERS = {"internal", "public", "private", "protected", "static", "readonly", "volatile", "new", "unsafe"}


# ----------------------------------------------------------------------------------------------- text layer
def blank_comments_strings(src):
    """Replace comment and string/char literal contents with spaces (newlines kept). Interpolation holes of
    $-strings stay code (with their delimiting braces blanked)."""
    out = list(src)
    n = len(src)
    i = 0
    stack = []  # entries: ('interp', depth) when inside an interpolation hole

    def blank(a, b):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    def scan_string(i, verbatim, interp):
        # i points at the opening quote. Returns the index after the string. Holes are scanned as code.
        start = i
        i += 1
        seg = start
        while i < n:
            c = src[i]
            if verbatim:
                if c == '"':
                    if i + 1 < n and src[i + 1] == '"':
                        i += 2
                        continue
                    blank(seg, i + 1)
                    return i + 1
            else:
                if c == "\\":
                    i += 2
                    continue
                if c == '"':
                    blank(seg, i + 1)
                    return i + 1
                if c == "\n":
                    blank(seg, i)
                    return i
            if interp and c == "{":
                if i + 1 < n and src[i + 1] == "{":
                    i += 2
                    continue
                blank(seg, i + 1)
                i = scan_code(i + 1, hole=True)  # returns index of the closing '}'
                if i < n:
                    out[i] = " "
                i += 1
                seg = i
                continue
            i += 1
        blank(seg, n)
        return n

    def scan_code(i, hole=False):
        depth = 0
        while i < n:
            c = src[i]
            if c == "/" and i + 1 < n and src[i + 1] == "/":
                j = src.find("\n", i)
                j = n if j < 0 else j
                blank(i, j)
                i = j
                continue
            if c == "/" and i + 1 < n and src[i + 1] == "*":
                j = src.find("*/", i + 2)
                j = n if j < 0 else j + 2
                blank(i, j)
                i = j
                continue
            if c == '"' or (c in "$@" and i + 1 < n and src[i + 1] in '"$@'):
                k = i
                verb = interp = False
                while k < n and src[k] in "$@":
                    verb |= src[k] == "@"
                    interp |= src[k] == "$"
                    k += 1
                if k < n and src[k] == '"':
                    blank(i, k)
                    i = scan_string(k, verb, interp)
                    continue
            if c == "'":
                j = i + 1
                if j < n and src[j] == "\\":
                    j += 2
                    while j < n and src[j] != "'" and src[j] != "\n":
                        j += 1
                else:
                    j += 1
                if j < n and src[j] == "'":
                    blank(i, j + 1)
                    i = j + 1
                    continue
            if hole:
                if c == "{":
                    depth += 1
                elif c == "}":
                    if depth == 0:
                        return i
                    depth -= 1
            i += 1
        return n

    scan_code(0)
    return "".join(out)


def eval_cond(expr, defined=()):
    """True/False when the #if condition is decidable from UNDEFINED (and `defined`, the FrameTime view's DEFINED
    symbols) alone, else None (keep all branches)."""
    e = expr.strip()
    m = re.fullmatch(r"(!?)\s*(\w+)", e)
    if m and m.group(2) in defined:
        return not m.group(1)
    if m and m.group(2) in UNDEFINED:
        return bool(m.group(1))
    return None


def apply_preprocessor(text, stats, defined=()):
    """Blank directive lines and the branches excluded under UNDEFINED (and `defined`). stats counts blanked code
    lines."""
    lines = text.split("\n")
    stack = []  # (decidable, active_parent, branch_taken, current_active)
    active = True
    blanked = 0
    for idx, ln in enumerate(lines):
        m = re.match(r"\s*#\s*(if|elif|else|endif|region|endregion|pragma|define|undef|nullable)\b(.*)", ln)
        if m:
            kw, rest = m.group(1), m.group(2)
            if kw == "if":
                v = eval_cond(rest, defined)
                if v is None:
                    stack.append((False, active, True, active))
                else:
                    stack.append((True, active, v, active and v))
                    active = active and v
            elif kw == "elif" and stack:
                dec, par, taken, cur = stack[-1]
                if dec:
                    v = eval_cond(rest, defined)
                    if v is None:
                        stack[-1] = (False, par, True, par)
                        active = par
                    else:
                        now = par and (not taken) and v
                        stack[-1] = (True, par, taken or v, now)
                        active = now
            elif kw == "else" and stack:
                dec, par, taken, cur = stack[-1]
                if dec:
                    now = par and not taken
                    stack[-1] = (True, par, True, now)
                    active = now
            elif kw == "endif" and stack:
                dec, par, taken, cur = stack.pop()
                active = par
            lines[idx] = " " * len(ln)
            continue
        if not active:
            if ln.strip():
                blanked += 1
            lines[idx] = " " * len(ln)
    stats["blanked"] = stats.get("blanked", 0) + blanked
    return "\n".join(lines)


class Src:
    def __init__(self, name, slice_spec=None):
        self.name = name
        path = os.path.join(PLUGIN, name)
        with open(path, "r", encoding="utf-8-sig") as f:
            self.raw = f.read().replace("\r\n", "\n")
        self.stats = {}
        code = blank_comments_strings(self.raw)
        code = apply_preprocessor(code, self.stats)
        if slice_spec:
            a_re, b_re = slice_spec
            ls = code.split("\n")
            raw_ls = self.raw.split("\n")
            a = next(i for i, l in enumerate(raw_ls) if re.match(a_re, l))
            b = next(i for i, l in enumerate(raw_ls) if i > a and re.match(b_re, l))
            for i in range(len(ls)):
                if i < a or i >= b:
                    ls[i] = " " * len(ls[i])
            code = "\n".join(ls)
            self.slice = (a + 1, b)
        else:
            self.slice = None
        self.code = code
        self.nl = [i for i, c in enumerate(code) if c == "\n"]
        self.raw_lines = self.raw.split("\n")

    def line(self, pos):
        return bisect.bisect_left(self.nl, pos) + 1


# ----------------------------------------------------------------------------------------------- structure
class TypeDecl:
    def __init__(self, src, name, kind, start, parent, is_static):
        self.src, self.name, self.kind, self.start, self.parent, self.is_static = src, name, kind, start, parent, is_static
        self.end = None
        self.fields = []
        self.members = []

    @property
    def top(self):
        t = self
        while t.parent is not None:
            t = t.parent
        return t

    @property
    def path(self):
        return (self.parent.path + "." if self.parent else "") + self.name


class Member:
    def __init__(self, src, name, kind, owner, start, body_start, end):
        self.src, self.name, self.kind, self.owner = src, name, kind, owner
        self.start, self.body_start, self.end = start, body_start, end

    @property
    def key(self):
        return "%s.%s@%s:%d" % (self.owner.path, self.name, self.src.name, self.src.line(self.start))


class Field:
    def __init__(self, src, name, type_s, owner, pos, is_static, is_readonly):
        self.src, self.name, self.type_s, self.owner, self.pos = src, name, type_s, owner, pos
        self.is_static, self.is_readonly = is_static, is_readonly
        self.writes = []      # (src, pos, kind, member)
        self.reads = []       # (src, pos, member, flag)

    @property
    def qual(self):
        return "%s.%s" % (self.owner.name, self.name)

    @property
    def decl(self):
        return "%s:%d" % (self.src.name, self.src.line(self.pos))


def top_level_split(s, sep=","):
    parts, depth, cur = [], 0, []
    for c in s:
        if c in "<([{":
            depth += 1
        elif c in ">)]}":
            depth -= 1
        if c == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append("".join(cur))
    return parts


def find_assign(s):
    """Index of the first top-level standalone '=' (not ==, =>, <=, >=, !=), or -1; and of '=>'."""
    depth = 0
    eq = arrow = -1
    for i, c in enumerate(s):
        if c in "([{<":
            depth += 1 if c != "<" else 0
        elif c in ")]}":
            depth -= 1
        if depth == 0 and c == "=":
            nxt = s[i + 1] if i + 1 < len(s) else ""
            prv = s[i - 1] if i > 0 else ""
            if nxt == ">":
                if arrow < 0:
                    arrow = i
            elif nxt != "=" and prv not in "=!<>+-*/%&|^?":
                if eq < 0:
                    eq = i
    return eq, arrow


def parse_structure(src):
    code = src.code
    types, members = [], []
    stack = []  # frames: (kind, obj, stmt_start_for_type_frames)
    stmt_start = 0
    i, n = 0, len(code)
    # frame kinds: 'ns', 'type', 'member', 'init', 'block'
    stack.append(["ns", None])
    pending_member = None
    while i < n:
        c = code[i]
        top = stack[-1]
        if c == "{":
            if top[0] in ("ns", "type"):
                header = code[stmt_start:i]
                hs = re.sub(r"\[[^\]]*\]", " ", header)
                tm = re.search(r"\b(class|struct|interface|enum|record)\s+(\w+)", hs)
                eq, arrow = find_assign(hs)
                if tm and eq < 0 and arrow < 0:
                    parent = top[1] if top[0] == "type" else None
                    td = TypeDecl(src, tm.group(2), tm.group(1), i, parent, bool(re.search(r"\bstatic\b", hs)))
                    types.append(td)
                    if parent:
                        parent.members  # noqa
                    stack.append(["type", td])
                    stmt_start = i + 1
                elif re.search(r"\bnamespace\b", hs):
                    stack.append(["ns", None])
                    stmt_start = i + 1
                elif top[0] == "type" and (eq >= 0 or arrow >= 0):
                    stack.append(["init", None])
                elif top[0] == "type":
                    name, kind = member_name(hs, top[1].name)
                    m = Member(src, name, kind, top[1], stmt_start + (len(header) - len(header.lstrip())), i, None)
                    stack.append(["member", m])
                else:
                    stack.append(["block", None])
            else:
                stack.append(["block", None])
        elif c == "}":
            fr = stack.pop() if len(stack) > 1 else stack[0]
            if fr[0] == "type":
                fr[1].end = i
                stmt_start = i + 1
            elif fr[0] == "member":
                m = fr[1]
                m.end = i
                body = code[m.body_start + 1:i].strip()
                if m.kind == "property" and re.fullmatch(r"((private|internal|protected|public)\s+)?(get|set|init)\s*;"
                                                          r"(\s*((private|internal|protected|public)\s+)?(get|set|init)\s*;)?", body):
                    m.kind = "autoprop"
                members.append(m)
                m.owner.members.append(m)
                stmt_start = i + 1
            elif fr[0] == "ns":
                stmt_start = i + 1
        elif c == ";" and top[0] == "type":
            stmt = code[stmt_start:i]
            handle_statement(src, stmt, stmt_start, top[1], members)
            stmt_start = i + 1
        i += 1
    return types, members


def member_name(header, owner_name):
    h = header.strip()
    if re.search(r"\bthis\s*\[", h):
        return "this[]", "indexer"
    if "(" in h:
        pre = h[:h.index("(")]
        ids = re.findall(r"[A-Za-z_]\w*", pre)
        name = ids[-1] if ids else "?"
        if name == "operator":
            return "operator", "method"
        return name, ("ctor" if name == owner_name else "method")
    ids = re.findall(r"[A-Za-z_]\w*", h)
    return (ids[-1] if ids else "?"), "property"


def handle_statement(src, stmt, start, owner, members):
    s = stmt
    am = re.match(r"(\s*\[[^\]]*\])+", s)  # leading attributes only; `int[]` and `new int[N]` stay
    if am:
        s = " " * am.end() + s[am.end():]
    if not s.strip() or s.strip().startswith("="):
        return
    eq, arrow = find_assign(s)
    if arrow >= 0 and (eq < 0 or arrow < eq):
        pre = s[:arrow]
        if "(" in pre:
            ids = re.findall(r"[A-Za-z_]\w*", pre[:pre.index("(")])
        else:
            ids = re.findall(r"[A-Za-z_]\w*", pre)
        name = ids[-1] if ids else "?"
        lead = len(stmt) - len(stmt.lstrip())
        m = Member(src, name, "exprbody", owner, start + lead, start + arrow, start + len(stmt))
        members.append(m)
        owner.members.append(m)
        return
    words = re.findall(r"[A-Za-z_]\w*", s[:eq] if eq >= 0 else s)
    if any(w in ("const", "delegate", "event", "using", "extern", "abstract", "operator") for w in words):
        return
    pre = s[:eq] if eq >= 0 else s
    if "(" in pre:
        return  # a method declaration without body (extern/partial) or a tuple; not a field
    parts = top_level_split(s)
    first = parts[0]
    e1, _ = find_assign(first)
    head = first[:e1] if e1 >= 0 else first
    toks = head.split()
    mods = set()
    while toks and toks[0] in MODIFIERS:
        mods.add(toks.pop(0))
    if len(toks) < 2:
        return
    name = toks[-1]
    type_s = " ".join(toks[:-1])
    if not re.fullmatch(r"[A-Za-z_]\w*", name):
        return
    is_static = "static" in mods
    ro = "readonly" in mods
    off = 0
    for idx, part in enumerate(parts):
        e, _ = find_assign(part)
        h = part[:e] if e >= 0 else part
        nm = h.split()[-1] if idx else name
        local = h.rfind(nm)
        pos = start + off + local
        if re.fullmatch(r"[A-Za-z_]\w*", nm):
            owner.fields.append(Field(src, nm, type_s, owner, pos, is_static, ro))
        off += len(part) + 1


# ----------------------------------------------------------------------------------------------- universe
class LazyPlugin:
    """Every plugin/*.cs, read raw on demand and blanked only when a check needs its code."""
    def __init__(self):
        self.names = sorted(f for f in os.listdir(PLUGIN) if f.endswith(".cs"))
        self._raw, self._src = {}, {}

    def raw(self, f):
        if f not in self._raw:
            with open(os.path.join(PLUGIN, f), "r", encoding="utf-8-sig") as h:
                self._raw[f] = h.read().replace("\r\n", "\n")
        return self._raw[f]

    def get(self, f):
        if f not in self.names:
            return None
        if f not in self._src:
            self._src[f] = Src(f)
        return self._src[f]

    def containing(self, needle_re):
        rx = re.compile(needle_re)
        return [f for f in self.names if rx.search(self.raw(f))]

    def dotted_files(self, cls, name):
        """Files whose raw text carries `cls.name` (one indexing pass over plugin/*.cs, then lookups)."""
        if not hasattr(self, "_dot"):
            self._dot = {}
            rx = re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\b")
            for f in self.names:
                for pair in set(rx.findall(self.raw(f))):
                    self._dot.setdefault(pair, []).append(f)
        return self._dot.get((cls, name), [])

    def assigned_files(self, name):
        """Files whose raw text carries `name =` (one indexing pass)."""
        if not hasattr(self, "_asg"):
            self._asg = {}
            rx = re.compile(r"\b([A-Z_][A-Z0-9_]*)\s*=[^=]")
            for f in self.names:
                for nm in set(rx.findall(self.raw(f))):
                    self._asg.setdefault(nm, []).append(f)
        return self._asg.get(name, [])


class Universe:
    def __init__(self):
        self.srcs = {}
        self.comp_srcs = {}
        for comp, files in COMPONENTS:
            lst = []
            for f in files:
                if isinstance(f, tuple):
                    s = Src(f[0], (f[1], f[2]))
                    key = f[0] + "#" + comp
                else:
                    s = Src(f)
                    key = f
                self.srcs[key] = s
                lst.append(s)
            self.comp_srcs[comp] = lst
        self.types, self.members = [], []
        self.type_comp = {}
        for comp in COMP_NAMES:
            for s in self.comp_srcs[comp]:
                t, m = parse_structure(s)
                for td in t:
                    self.type_comp[id(td)] = comp
                self.types += t
                self.members += m
        self.by_name = {}
        for td in self.types:
            self.by_name.setdefault(td.name, []).append(td)
        self.mem_by_name = {}
        for m in self.members:
            self.mem_by_name.setdefault(m.name, []).append(m)
        self.aliases = {}
        for s in self.srcs.values():
            for a, t in re.findall(r"^using\s+(\w+)\s*=\s*[\w.]*?\.?(\w+)\s*;", s.raw, re.M):
                self.aliases[a] = t
        # members sorted per source for position lookup
        self.mem_index = {}
        for m in self.members:
            self.mem_index.setdefault(id(m.src), []).append(m)
        for k in self.mem_index:
            self.mem_index[k].sort(key=lambda m: m.start)
        self.all_plugin = LazyPlugin()
        self.field_by_name = {}
        for td in self.types:
            for fd in td.fields:
                self.field_by_name.setdefault(fd.name, []).append(fd)
        self.resolver = Resolver(self)
        self.mem_starts = {k: [m.start for m in v] for k, v in self.mem_index.items()}

    def member_at(self, src, pos):
        starts = self.mem_starts.get(id(src))
        if not starts:
            return None
        i = bisect.bisect_right(starts, pos) - 1
        while i >= 0:
            m = self.mem_index[id(src)][i]
            if m.start <= pos <= m.end:
                return m
            i -= 1
            if i >= 0 and self.mem_index[id(src)][i].end < pos - 200000:
                break
        return None

    def resolve_type(self, ident, ctx):
        if ident in self.aliases:
            ident = self.aliases[ident]
        cands = self.by_name.get(ident, [])
        if not cands:
            return []
        same = [t for t in cands if t.top is ctx.top]
        if same:
            return same
        return cands

    def resolve_member(self, qual, name, ctx_type, is_call):
        if qual:
            q = self.aliases.get(qual, qual)
            cls = self.by_name.get(q)
            if cls:
                out = []
                for td in cls:
                    out += [m for m in td.members if m.name == name]
                return out
            if qual in KEYWORDS and qual != "this":
                return []
            if qual == "this":
                return [m for m in ctx_type.members if m.name == name]
            return [m for m in self.mem_by_name.get(name, [])
                    if is_call or m.kind in ("property", "exprbody", "autoprop", "indexer")]
        cands = self.mem_by_name.get(name, [])
        top = ctx_type.top
        same = [m for m in cands if m.owner.top is top]
        return same


def match_roots(uni, roots):
    out = set()
    for cls, name in roots:
        for td in uni.by_name.get(cls, []):
            for m in td.members:
                if name == "*" or m.name == name:
                    out.add(m)
    return out


BCL_OUTER = {"List", "Dictionary", "HashSet", "Queue", "Stack", "SortedDictionary", "SortedList", "SortedSet",
             "LinkedList", "IEnumerable", "IList", "ICollection", "IDictionary", "string", "String", "int", "long",
             "float", "double", "bool", "byte", "object", "Object", "StringBuilder", "Stopwatch", "Hashtable",
             "Func", "Action", "Array", "Random", "Stream", "FileStream", "Exception", "Type", "Vector2", "Vector3",
             "GameObject", "Transform", "Player", "PhotonView", "Gun", "GunAmmo", "Block", "HealthHandler",
             "CharacterData", "Rigidbody2D", "RaycastHit2D", "SyncProjectile", "ProjectileHit", "MoveTransform"}


def type_classes(uni, type_s, ctx, element=False):
    """Universe classes a value of declared type `type_s` can be. A BCL outer type (List<...>, arrays,
    primitives, Unity/Photon/ROUNDS types) has no universe members; with element=True (the value was indexed)
    the element/generic-argument types are used instead."""
    t = type_s.strip()
    if element:
        if t.endswith("]"):
            t = re.sub(r"\[[\s,]*\]\s*$", "", t)
        else:
            m = re.search(r"<(.*)>\s*$", t)
            if not m:
                return []
            t = top_level_split(m.group(1))[-1]
    if t.endswith("]"):
        return []
    outer = re.match(r"\s*(?:[\w]+\s*\.\s*)*([A-Za-z_]\w*)", t)
    if not outer:
        return []
    name = outer.group(1)
    q = re.match(r"\s*(\w+)\s*\.", t)
    if name in BCL_OUTER and not q:
        return []
    return uni.resolve_type(name, ctx)


LOCAL_DECL = re.compile(r"(?:^|[(;{},]|\bforeach\s*\()\s*(?:(?:ref|out|in|readonly|const)\s+)?"
                        r"([A-Za-z_][\w.]*(?:\s*<[^;=(){}]*?>)?(?:\s*\[[\s,]*\])*)\s+([A-Za-z_]\w*)\s*(?=[=;,)]|\bin\b)")
VAR_NEW = re.compile(r"\bvar\s+([A-Za-z_]\w*)\s*=\s*new\s+([A-Za-z_][\w.]*)")
VAR_FROM = re.compile(r"\bvar\s+([A-Za-z_]\w*)\s*=\s*(?:[\w.]+\s*\.\s*)?([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*;")
VAR_IN = re.compile(r"\bforeach\s*\(\s*var\s+([A-Za-z_]\w*)\s+in\s+(?:[\w.]+\s*\.\s*)?([A-Za-z_]\w*)\s*\)")


def member_locals(uni, m):
    """Local name -> list of universe classes, from the member's header and body declarations."""
    code = m.src.code
    text = code[m.start:m.end + 1]
    loc = {}
    for t, n in LOCAL_DECL.findall(text):
        if t in KEYWORDS and t not in ("var",):
            if t not in ("int", "long", "float", "double", "bool", "string", "byte", "object"):
                continue
        if t == "var" or t in ("return", "new", "else", "case", "throw", "using", "await", "yield", "goto"):
            continue
        loc.setdefault(n, []).extend(type_classes(uni, t, m.owner) or [None])
    for n, t in VAR_NEW.findall(text):
        loc.setdefault(n, []).extend(uni.resolve_type(t.split(".")[-1], m.owner) or [None])
    for n, f, idx in VAR_FROM.findall(text):
        fds = uni.field_by_name.get(f, [])
        if not fds and not any(x.kind in ("property", "autoprop", "exprbody") for x in uni.mem_by_name.get(f, [])):
            loc.setdefault(n, []).append(None)  # `var n = a.b.f;` with f no universe field/property: external
        for fd in fds:
            loc.setdefault(n, []).extend(type_classes(uni, fd.type_s, fd.owner, element=bool(idx)) or [None])
    for n, f in VAR_IN.findall(text):
        for fd in uni.field_by_name.get(f, []):
            loc.setdefault(n, []).extend(type_classes(uni, fd.type_s, fd.owner, element=True) or [None])
    return loc


def qualifier_at(code, p):
    """For the identifier at p: (kind, text, indexed). kind: None (unqualified), 'ident' (a.b), 'expr' (call
    result or other expression)."""
    k = p
    while k > 0 and code[k - 1] in " \t\n":
        k -= 1
    if k == 0 or code[k - 1] != ".":
        return None, None, False
    k -= 1
    while k > 0 and code[k - 1] in " \t\n":
        k -= 1
    indexed = False
    if k > 0 and code[k - 1] == "]":
        depth = 0
        while k > 0:
            k -= 1
            if code[k] == "]":
                depth += 1
            elif code[k] == "[":
                depth -= 1
                if depth == 0:
                    break
        indexed = True
        while k > 0 and code[k - 1] in " \t\n":
            k -= 1
    if k > 0 and (code[k - 1].isalnum() or code[k - 1] == "_"):
        e = k
        while k > 0 and (code[k - 1].isalnum() or code[k - 1] == "_"):
            k -= 1
        return "ident", code[k:e], indexed
    return "expr", None, indexed


class Resolver:
    def __init__(self, uni):
        self.uni = uni
        self.fallbacks = 0
        self.fallback_sites = []
        self._locals = {}

    def locals_of(self, m):
        if m not in self._locals:
            self._locals[m] = member_locals(self.uni, m)
        return self._locals[m]

    def classes_of_ident(self, ident, indexed, m):
        """Universe classes the identifier `ident` (used as a qualifier inside member m) can be; None = unknown."""
        uni = self.uni
        q = uni.aliases.get(ident, ident)
        if not indexed and q in uni.by_name:
            return ("static", uni.by_name[q])
        if ident == "this":
            return ("inst", [m.owner])
        if ident == "base":
            return ("inst", [])
        loc = self.locals_of(m)
        if ident in loc:
            vals = loc[ident]
            if None in vals:
                return ("inst", [v for v in vals if v is not None]) if any(vals) else ("inst", [])
            return ("inst", vals)
        fds = uni.field_by_name.get(ident)
        if fds:
            out = []
            for fd in fds:
                out += type_classes(uni, fd.type_s, fd.owner, element=indexed)
            return ("inst", out)
        props = [x for x in uni.mem_by_name.get(ident, []) if x.kind in ("property", "autoprop", "exprbody")]
        if props:
            out = []
            for pm in props:
                hdr = pm.src.code[pm.start:pm.body_start]
                ids = re.findall(r"[A-Za-z_][\w.]*(?:<[^>]*>)?(?:\[\])?", hdr)
                if len(ids) >= 2:
                    out += type_classes(uni, ids[-2], pm.owner, element=indexed)
            return ("inst", out)
        return None

    def resolve(self, code, p, name, is_call, is_new, m):
        uni = self.uni
        if is_new:
            out = []
            for td in uni.resolve_type(name, m.owner):
                out += [x for x in td.members if x.kind == "ctor"]
            return out
        kind, qtext, indexed = qualifier_at(code, p)
        if kind is None:
            return [x for x in uni.mem_by_name.get(name, []) if x.owner.top is m.owner.top]
        if kind == "ident":
            if qtext in KEYWORDS and qtext not in ("this", "base"):
                return []
            cl = self.classes_of_ident(qtext, indexed, m)
            if cl is not None:
                out = []
                for td in cl[1]:
                    out += [x for x in td.members if x.name == name]
                return out
            if qtext[:1].isupper() and not indexed:
                return []  # a capitalised name that is no universe class, field, local or property: an external type
        # unknown qualifier: every universe member of that name that a value could expose
        cands = [x for x in uni.mem_by_name.get(name, [])
                 if (is_call and x.kind in ("method",)) or x.kind in ("property", "exprbody", "autoprop")]
        if cands:
            self.fallbacks += 1
            self.fallback_sites.append("%s:%d %s.%s" % (m.src.name, m.src.line(p), qtext or "(expr)", name))
        return cands


def edges(uni, m, upto=None, guarded=()):
    code = m.src.code
    end = m.end + 1 if upto is None else upto
    res = set()
    rs = uni.resolver
    for mt in re.finditer(r"(\bnew\s+)?\b([A-Za-z_]\w*)\b\s*(<[\w\s,.<>\[\]]*>)?\s*(\()?", code[m.body_start:end]):
        new, name, _g, call = mt.group(1), mt.group(2), mt.group(3), mt.group(4)
        if name in KEYWORDS:
            continue
        if name in guarded:
            continue
        p = m.body_start + mt.start(2)
        res.update(rs.resolve(code, p, name, bool(call), bool(new), m))
    res.discard(m)
    return res


def closure(uni, roots, stop, cuts=None, guards=None):
    cuts = cuts or {}
    guards = guards or {}
    seen = {}
    work = sorted(roots - stop, key=lambda x: x.key)
    for w in work:
        seen[w] = None
    while work:
        m = work.pop()
        for e in sorted(edges(uni, m, cuts.get(m), guards.get(m, ())), key=lambda x: x.key):
            if e in seen or e in stop:
                continue
            seen[e] = m
            work.append(e)
    return seen


# ----------------------------------------------------------------------------------------------- sweep
CLEAR_RHS = re.compile(r"\s*(-?\d[\w.]*|true|false|null|default(\([^)]*\))?|int\.MinValue|int\.MaxValue|"
                       r"long\.MinValue|long\.MaxValue|float\.\w+|string\.Empty|\"\s*\"|new\b.*|[A-Z_][A-Z0-9_]*|-[A-Z_]\w*)\s*$")


def chain_start(code, p):
    k = p
    while k > 0 and (code[k - 1].isalnum() or code[k - 1] in "._"):
        k -= 1
    return k


def classify_occurrence(code, p, name, type_s):
    """Return (write_kind or None, is_access). write kinds: store, istore, compound, incdec, mutate, outarg,
    arraycall. is_access = a non-store access (a read)."""
    n = len(code)
    q = p + len(name)
    j = q
    while j < n and code[j] in " \t\n":
        j += 1
    # a ternary branch `(c ? a.F : b.G)[i]++`: classify from after the parenthesised conditional
    if j < n and code[j] in ":)":
        k0, d0 = chain_start(code, p) - 1, 0
        while k0 >= 0:
            c0 = code[k0]
            if c0 in ")]":
                d0 += 1
            elif c0 in "([":
                if d0 == 0:
                    break
                d0 -= 1
            elif c0 in ";{}":
                k0 = -1
                break
            k0 -= 1
        if k0 >= 0 and code[k0] == "(":
            e0, d1 = k0, 0
            while e0 < n:
                if code[e0] == "(":
                    d1 += 1
                elif code[e0] == ")":
                    d1 -= 1
                    if d1 == 0:
                        break
                e0 += 1
            inner = code[k0 + 1:e0]
            if "?" in inner and ":" in inner and e0 < n and not re.search(r"[A-Za-z_]\w*\s*$", code[max(0, k0 - 40):k0]):
                j = e0 + 1  # (the paren is not a call's argument list)
                while j < n and code[j] in " \t\n":
                    j += 1
    indexed = False
    if j < n and code[j] == "[":
        depth = 0
        while j < n:
            if code[j] == "[":
                depth += 1
            elif code[j] == "]":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        indexed = True
        while j < n and code[j] in " \t\n":
            j += 1
    rest = code[j:j + 4]
    cs = chain_start(code, p)
    k = cs
    while k > 0 and code[k - 1] in " \t\n":
        k -= 1
    before2 = code[k - 2:k]
    before_word = re.search(r"([A-Za-z_]\w*)\s*$", code[max(0, cs - 12):cs])
    if rest.startswith("++") or rest.startswith("--"):
        return "incdec", True
    if before2 in ("++", "--") and code[k - 3:k - 2] not in ("+", "-"):
        return "incdec", True
    m = re.match(r"(\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<=|>>=|\?\?=)", code[j:j + 3])
    if m:
        return "compound", True
    if rest[:1] == "=" and rest[1:2] not in ("=", ">"):
        rhs_end = code.find(";", j)
        rhs = code[j + 1:rhs_end if rhs_end > 0 else j + 80]
        return ("istore" if indexed else "store", rhs), False
    if before_word and before_word.group(1) in ("out",):
        return "outarg", False
    if before_word and before_word.group(1) in ("ref",):
        return "outarg", True
    if not indexed and BCL_COLL.match(type_s):
        mm = re.match(r"\.\s*(" + MUTATORS + r")\s*\(", code[j:j + 40])
        if mm:
            return ("mutate", mm.group(1)), True
    return None, True


def is_reference_type(type_s):
    """Arrays and BCL collections: a local or a parameter holding one aliases the field's storage."""
    t = type_s.strip()
    return t.endswith("]") or bool(BCL_COLL.match(t))


def unwrap(wk):
    """A write made through an alias is ("via:name", inner kind); classification reads the inner kind."""
    if isinstance(wk, tuple) and isinstance(wk[0], str) and wk[0].startswith("via:"):
        return wk[1]
    return wk


def is_declaration(code, p, cs):
    """True when the token at p is a local declaration or a lambda/foreach variable (a preceding type token)."""
    if cs != p:
        return False
    pre = code[max(0, p - 60):p]
    m = re.search(r"([A-Za-z_]\w*|>|\])\s*(\?)?\s*$", pre)
    if not m:
        return False
    w = m.group(1)
    if w in (">", "]"):
        # generic or array type followed by the name: List<int> x / int[] x ; exclude indexer results a[i] x (rare)
        return bool(re.search(r"(<[\w\s,.<>\[\]]*>|\w\s*\[\s*,*\s*\])\s*$", pre))
    if w in KEYWORDS and w not in ("int", "long", "float", "double", "bool", "string", "byte", "short", "uint",
                                    "ulong", "char", "object", "var", "decimal", "sbyte", "ushort"):
        return False
    return True


def array_call_dests(code):
    """Positions (start, end) of the destination argument of Array.Copy/Clear/Fill/Reverse/Sort/Resize and
    Buffer.BlockCopy calls."""
    out = []
    for mt in re.finditer(r"\b(Array\s*\.\s*(Copy|Clear|Fill|Reverse|Sort|Resize|ConstrainedCopy)|"
                          r"Buffer\s*\.\s*BlockCopy)\s*\(", code):
        a = mt.end()
        depth, k, args, cur = 1, a, [], a
        while k < len(code) and depth:
            c = code[k]
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
                if depth == 0:
                    args.append((cur, k))
                    break
            elif c == "," and depth == 1:
                args.append((cur, k))
                cur = k + 1
            k += 1
        op = mt.group(2) or "BlockCopy"
        if op in ("Copy", "ConstrainedCopy"):
            idx = 2 if len(args) >= 5 else 1
        elif op == "BlockCopy":
            idx = 2
        else:
            idx = 0
        if idx < len(args):
            out.append((args[idx][0], args[idx][1], op))
    return out


class Sweep:
    def __init__(self, uni):
        self.uni = uni
        stop_set = set()
        self.stop_reason = {}
        for cls, name, why in STOP:
            for m in match_roots(uni, [(cls, name)]):
                stop_set.add(m)
                self.stop_reason[m] = why
        self.point_roots = match_roots(uni, POINT_ROOTS)
        self.live_roots = match_roots(uni, LIVE_ROOTS)
        self.cuts, self.cut_lines = {}, []
        for cls, name, rx, why in LIVE_CUT:
            for m in match_roots(uni, [(cls, name)]):
                mt = re.compile(rx).search(m.src.code, m.body_start, m.end)
                if not mt:
                    raise SystemExit("LIVE_CUT %s.%s: gate %r not found" % (cls, name, rx))
                self.cuts[m] = mt.end()
                self.cut_lines.append("%s.%s cut at %s:%d (%s)" % (cls, name, m.src.name, m.src.line(mt.start()), why))
        self.guards, self.guard_lines = {}, []
        for cls, name, callee, why in GUARDED_EDGES:
            ms = match_roots(uni, [(cls, name)])
            if not ms:
                raise SystemExit("GUARDED_EDGES %s.%s not found" % (cls, name))
            for m in ms:
                if not re.search(r"\b%s\b" % callee, m.src.code[m.body_start:m.end]):
                    raise SystemExit("GUARDED_EDGES %s.%s does not call %s" % (cls, name, callee))
                self.guards.setdefault(m, set()).add(callee)
                self.guard_lines.append("%s.%s -/-> %s (%s)" % (cls, name, callee, why))
        self.live_parent = closure(uni, self.live_roots, stop_set | self.point_roots, self.cuts, self.guards)
        self.live = set(self.live_parent)
        bnd = closure(uni, self.point_roots, stop_set)
        self.boundary = {m for m in bnd if m not in self.live}
        self.stop_set = stop_set
        self.arraydest = {}
        for key, s in uni.srcs.items():
            self.arraydest[id(s)] = array_call_dests(s.code)
        self.comp_fields = {}
        for comp in COMP_NAMES:
            self.comp_fields[comp] = self.fields_of(comp)
        for comp in COMP_NAMES:
            for fd in self.comp_fields[comp]:
                self.scan_field(comp, fd)

    def is_live_read(self, r):
        s, p, m, fl = r
        return m in self.live and p < self.cuts.get(m, m.end + 1)

    def fields_of(self, comp):
        uni = self.uni
        srcs = uni.comp_srcs[comp]
        own_types = [t for t in uni.types if t.src in srcs]
        fields = []
        held = []
        seen_types = set()
        for t in own_types:
            for fd in t.fields:
                if fd.is_static:
                    fields.append(fd)
        work = [fd for fd in fields]
        while work:
            fd = work.pop(0)
            for ident in re.findall(r"[A-Za-z_]\w*", fd.type_s):
                for td in uni.resolve_type(ident, fd.owner):
                    if id(td) in seen_types or td.kind == "enum":
                        continue
                    seen_types.add(id(td))
                    held.append(td)
                    for f2 in td.fields:
                        if not f2.is_static:
                            fields.append(f2)
                            work.append(f2)
        uniq, seen = [], set()
        for fd in fields:
            k = (fd.src.name, fd.pos)
            if k in seen:
                continue
            seen.add(k)
            uniq.append(fd)
        uniq.sort(key=lambda f: (f.src.name, f.pos))
        return uniq

    def scan_field(self, comp, fd):
        uni = self.uni
        # Clone per component: the same held class can be swept under more than one component.
        fd_writes, fd_reads = [], []
        scopes = []
        owner_span = (fd.owner.start, fd.owner.end)
        comp_srcs = list(uni.comp_srcs[comp])
        if fd.src not in comp_srcs:
            comp_srcs.append(fd.src)
        for s in comp_srcs:
            scopes.append((s, s is fd.src))
        if fd.is_static:
            for f in uni.all_plugin.dotted_files(fd.owner.name, fd.name):
                if any(f == x.name and x.slice is None for x in comp_srcs):
                    continue
                scopes.append((uni.all_plugin.get(f), "qualified"))
        pat = re.compile(r"\b%s\b" % re.escape(fd.name))
        seen = set()
        for s, mode in scopes:
            code = s.code
            for mt in pat.finditer(code):
                p = mt.start()
                if p == fd.pos and s is fd.src:
                    continue
                k = p
                while k > 0 and code[k - 1] in " \t\n":
                    k -= 1
                dotted = k > 0 and code[k - 1] == "."
                if mode == "qualified":
                    qm = re.search(r"(\w+)\s*\.\s*$", code[max(0, p - 80):p])
                    if not (dotted and qm and uni.aliases.get(qm.group(1), qm.group(1)) == fd.owner.name):
                        continue
                    m = None  # outside the universe: writes counted, reads not live
                else:
                    if not dotted:
                        if not (mode is True and owner_span[0] <= p <= owner_span[1]):
                            continue
                m = uni.member_at(s, p) if mode != "qualified" else None
                if mode != "qualified" and m is None:
                    continue  # class-level text (another field's initializer); not a write site
                if m is not None and p < m.body_start and m.kind not in ("exprbody",):
                    continue  # a parameter in a member header
                if dotted and m is not None and mode != "qualified":
                    qk, qt, qi = qualifier_at(code, p)
                    if qk == "ident" and qt not in ("this", "base"):
                        cl = uni.resolver.classes_of_ident(qt, qi, m)
                        if cl is not None and fd.owner not in cl[1]:
                            continue  # the qualifier's type is known and is not the field's class
                cs = chain_start(code, p)
                if not dotted and is_declaration(code, p, cs):
                    continue
                key = (s.name, p)
                if key in seen:
                    continue
                seen.add(key)
                wk, access = classify_occurrence(code, p, fd.name, fd.type_s)
                if id(s) not in self.arraydest:
                    self.arraydest[id(s)] = array_call_dests(s.code)
                for a, b, op in self.arraydest[id(s)]:
                    if a <= p < b and re.search(r"\b%s\s*$" % re.escape(fd.name), code[a:b].rstrip()):
                        wk, access = ("arraycall", op), True
                if wk is not None:
                    fd_writes.append((s, p, wk, m))
                if access and m is not None:
                    fd_reads.append((s, p, m, read_flag(code, p, m)))
                if wk is None and m is not None and is_reference_type(fd.type_s):
                    self.follow_alias(fd, s, p, cs, m, fd_writes, fd_reads, 0)
        fd.__dict__.setdefault("by_comp", {})[comp] = (fd_writes, fd_reads)

    def follow_alias(self, fd, s, p, cs, m, fd_writes, fd_reads, depth):
        """A reference-typed field (array or BCL collection) handed on unchanged: (a) as a call argument to a
        universe member -> that member's parameter; (b) as the initializer of a local -> that local. Every
        occurrence of the alias is classified like the field itself (writes and reads, at the alias's own
        position and member). Depth-capped at 3 hops."""
        if depth >= 3:
            return
        code = s.code
        q = p
        while q < len(code) and (code[q].isalnum() or code[q] == "_"):
            q += 1
        # (b) local alias: `var x = <chain>;` or `var x = c ? <chain> : <chain>;`
        stmt_a = max(code.rfind(";", 0, cs), code.rfind("{", 0, cs), code.rfind("}", 0, cs)) + 1
        stmt_b = code.find(";", q)
        lm = re.match(r"\s*(?:var|[A-Za-z_][\w.<>\[\], ]*?)\s+([A-Za-z_]\w*)\s*=(?!=)\s*(.*)$",
                      code[stmt_a:stmt_b], re.S)
        if lm and stmt_a + lm.start(2) <= cs and re.fullmatch(r"[\w.\s?:!<>=&|]*", lm.group(2)):
            alias = lm.group(1)
            for am in re.finditer(r"\b%s\b" % re.escape(alias), code[stmt_b:m.end + 1]):
                ap = stmt_b + am.start()
                k = ap
                while k > 0 and code[k - 1] in " \t\n":
                    k -= 1
                if code[k - 1] == ".":
                    continue
                self.alias_hit(fd, s, ap, alias, m, fd_writes, fd_reads, depth)
            return
        # (a) call argument
        depth_p, k = 0, cs - 1
        while k > stmt_a - 1 and k >= 0:
            c = code[k]
            if c in ")]":
                depth_p += 1
            elif c in "([":
                if depth_p == 0:
                    break
                depth_p -= 1
            k -= 1
        if k < 0 or code[k] != "(":
            return
        argstart = k + 1
        pre = code[max(0, k - 80):k]
        cm = re.search(r"([A-Za-z_]\w*)\s*$", pre)
        if not cm or cm.group(1) in KEYWORDS:
            return
        cname = cm.group(1)
        # arg text must be exactly the chain
        e, d2 = argstart, 0
        args, cur = [], argstart
        while e < len(code):
            c = code[e]
            if c in "([{":
                d2 += 1
            elif c in ")]}":
                if d2 == 0:
                    args.append((cur, e))
                    break
                d2 -= 1
            elif c == "," and d2 == 0:
                args.append((cur, e))
                cur = e + 1
            e += 1
        idx = next((i for i, (a, b) in enumerate(args) if a <= p < b), None)
        if idx is None:
            return
        argtxt = code[args[idx][0]:args[idx][1]].strip()
        if not re.fullmatch(r"(?:(?:ref|in)\s+)?[\w.]*\b%s" % re.escape(fd.name if depth == 0 else code[p:q]), argtxt):
            return
        fb0 = self.uni.resolver.fallbacks
        callees = self.uni.resolver.resolve(code, k - (len(pre) - cm.start(1)), cname, True, False, m)
        if self.uni.resolver.fallbacks != fb0:
            return  # the callee was not resolved by type (a name-only fallback): no alias is followed
        for cal in callees:
            hdr = cal.src.code[cal.start:cal.body_start]
            if "(" not in hdr:
                continue
            plist = hdr[hdr.index("(") + 1:hdr.rindex(")")] if ")" in hdr else ""
            params = [x.strip() for x in top_level_split(plist)] if plist.strip() else []
            if idx >= len(params):
                continue
            pids = re.findall(r"[A-Za-z_]\w*", params[idx].split("=")[0])
            if not pids:
                continue
            pname = pids[-1]
            ccode = cal.src.code
            for am in re.finditer(r"\b%s\b" % re.escape(pname), ccode[cal.body_start:cal.end + 1]):
                ap = cal.body_start + am.start()
                kk = ap
                while kk > 0 and ccode[kk - 1] in " \t\n":
                    kk -= 1
                if ccode[kk - 1] == ".":
                    continue
                self.alias_hit(fd, cal.src, ap, pname, cal, fd_writes, fd_reads, depth)

    def alias_hit(self, fd, s, ap, alias, m, fd_writes, fd_reads, depth):
        code = s.code
        wk, access = classify_occurrence(code, ap, alias, fd.type_s)
        if id(s) not in self.arraydest:
            self.arraydest[id(s)] = array_call_dests(code)
        for a, b, op in self.arraydest[id(s)]:
            if a <= ap < b and re.search(r"\b%s\s*$" % re.escape(alias), code[a:b].rstrip()):
                wk, access = ("arraycall", op), True
        if wk is not None:
            fd_writes.append((s, ap, ("via:" + alias, wk), m))
        if access:
            fd_reads.append((s, ap, m, read_flag(code, ap, m)))
        if wk is None:
            self.follow_alias(fd, s, ap, chain_start(code, ap), m, fd_writes, fd_reads, depth + 1)

    def classify(self, comp, fd):
        writes, reads = fd.by_comp[comp]
        if not writes:
            return "unwritten", writes, reads
        if all(m is not None and m.kind == "ctor" and m.owner is fd.owner for (_, _, _, m) in writes):
            return "construction", writes, reads
        for (s, p, wk, m) in writes:
            if m is None or m not in self.boundary:
                continue
            wk = unwrap(wk)
            kind = wk[0] if isinstance(wk, tuple) else wk
            if kind == "store" and CLEAR_RHS.match(wk[1]):
                return "reset", writes, reads
            if kind == "store":
                return "reset", writes, reads  # whole-value overwrite at the point
            if kind == "mutate" and wk[1] in ("Clear",):
                return "reset", writes, reads
            if kind == "arraycall" and wk[1] in ("Clear", "Fill"):
                return "reset", writes, reads
        return "survives", writes, reads


def read_flag(code, p, m):
    """LOOP when the access sits inside a for/while/foreach of its member, LINEAR when a linear call follows
    it, else O1."""
    flag = "O1"
    for mt in re.finditer(r"\b(for|foreach|while)\s*\(|\bdo\b\s*\{", code[m.body_start:p]):
        a = m.body_start + mt.start()
        if mt.group(1) is None:
            k = m.body_start + mt.end() - 1  # the do block's '{'
        else:
            k = m.body_start + mt.end() - 1  # the header's '('
            depth = 0
            while k < len(code):
                if code[k] == "(":
                    depth += 1
                elif code[k] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            if a <= p <= k:
                flag = "LOOP"  # in the loop header (the bound or the step)
                break
            k += 1
            while k < len(code) and code[k] in " \t\n":
                k += 1
        if k < len(code) and code[k] == "{":
            depth, e = 0, k
            while e < len(code):
                if code[e] == "{":
                    depth += 1
                elif code[e] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                e += 1
        else:
            e = code.find(";", k)
        if a <= p <= e:
            flag = "LOOP"
            break
    tail = code[p:p + 60]
    if LINEAR_CALLS.match(re.sub(r"^\w+(\s*\[[^\]]*\])?", "", tail)):
        flag = "LINEAR" if flag == "O1" else flag
    return flag


# ----------------------------------------------------------------------------------------------- results
def sweep_results(uni, sw, overrides):
    """overrides: {(comp, qual): (rule, arg)} from the reclassification table. Returns per comp stats, the
    per-field classification and override failures."""
    stats, fields_out, fails = {}, {}, []
    for comp in COMP_NAMES:
        st = dict(declared=0, written=0, write_sites=0, construction=0, reset=0, reclassified=0, survivors=0,
                  live=0)
        cls_map = {}
        for fd in sw.comp_fields[comp]:
            st["declared"] += 1
            c, writes, reads = sw.classify(comp, fd)
            cls_map[fd.qual] = c
        for fd in sw.comp_fields[comp]:
            c, writes, reads = sw.classify(comp, fd)
            if c == "unwritten":
                fields_out[(comp, fd.qual)] = (c, fd, writes, reads)
                continue
            st["written"] += 1
            st["write_sites"] += len(writes)
            if c == "construction":
                st["construction"] += 1
            elif c == "reset":
                st["reset"] += 1
            else:
                ov = overrides.get((comp, fd.qual))
                if ov:
                    ok, why = check_override(uni, sw, comp, fd, ov, cls_map)
                    if ok:
                        c = "reclassified"
                        st["reclassified"] += 1
                    else:
                        fails.append("override %s %s refused: %s" % (comp, fd.qual, why))
                if c == "survives":
                    st["survivors"] += 1
                    live_reads = [r for r in reads if sw.is_live_read(r)]
                    if live_reads:
                        c = "survives_live"
                        st["live"] += 1
            fields_out[(comp, fd.qual)] = (c, fd, writes, reads)
        stats[comp] = st
    for (comp, qual) in overrides:
        if (comp, qual) not in fields_out:
            fails.append("override names %s %s, which the sweep does not declare" % (comp, qual))
    return stats, fields_out, fails


def check_override(uni, sw, comp, fd, ov, cls_map):
    rule, arg = ov
    if rule == "companion-reset":
        cq = arg.strip("`")
        if not cq.startswith(fd.owner.name + "."):
            return False, "companion %s is not in class %s" % (cq, fd.owner.name)
        if cls_map.get(cq) != "reset":
            return False, "companion %s is %s, not reset at the point" % (cq, cls_map.get(cq))
        return True, ""
    if rule in ("cleared-at-point", "cleared-each-live-call"):
        m = re.fullmatch(r"([\w.]+\.cs):(\d+)", arg.strip())
        if not m:
            return False, "evidence %r is not file:line" % arg
        writes, _ = fd.by_comp[comp]
        want = uni_line_ok = False
        for (s, p, wk, mem) in writes:
            if s.name == m.group(1) and s.line(p) == int(m.group(2)):
                wk = unwrap(wk)
                kind = wk[0] if isinstance(wk, tuple) else wk
                clears = (kind in ("store", "istore") and CLEAR_RHS.match(wk[1])) or \
                         (kind == "mutate" and wk[1] == "Clear") or (kind == "arraycall" and wk[1] in ("Clear", "Fill"))
                if not clears:
                    continue
                if rule == "cleared-at-point" and mem in sw.boundary:
                    want = True
                if rule == "cleared-each-live-call" and mem in sw.live:
                    want = True
        if not want:
            return False, "no clearing write of %s at %s in a %s member" % (
                fd.qual, arg, "point-boundary" if rule == "cleared-at-point" else "live")
        return True, ""
    return False, "unknown rule %r" % rule


# ----------------------------------------------------------------------------------------------- table
def parse_md(text):
    rows, counts, overrides, errs = [], {}, {}, []
    for ln in text.split("\n"):
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if re.fullmatch(r"S\d{2,3}", cells[0]):
            if len(cells) < 9:
                errs.append("row %s has %d columns, wants 9" % (cells[0], len(cells)))
                continue
            rows.append(cells)
        elif re.fullmatch(r"R\d{2,3}", cells[0]):
            if len(cells) < 5:
                errs.append("reclassification %s has %d columns" % (cells[0], len(cells)))
                continue
            for q in re.findall(r"`(\w+\.\w+)`", cells[2]):
                rm = re.match(r"(companion-reset|cleared-at-point|cleared-each-live-call)\s+(.+)$", cells[3])
                if not rm:
                    errs.append("reclassification %s rule %r unparsed" % (cells[0], cells[3]))
                    continue
                overrides[(cells[1], q)] = (rm.group(1), rm.group(2).strip())
        elif cells[0] in COMP_NAMES and len(cells) >= 9 and re.fullmatch(r"\d+", cells[1] or "x"):
            try:
                counts[cells[0]] = [int(x) for x in cells[1:9]]
            except ValueError:
                errs.append("counts row %s unparsed" % cells[0])
    return rows, counts, overrides, errs


CAP_ITEM = r"\b([A-Z][A-Z0-9_]*[A-Z0-9])\s*=\s*(-?\d+)\s*\(([\w.]+\.cs):(\d+)\)"


def const_on_line(uni, s, line, name):
    """Value of constant `name` as declared on line `line` of source s (aliases resolved), else None."""
    code_line = s.code.split("\n")[line - 1]
    m = re.search(CONST_RE % re.escape(name), code_line)
    if not m:
        return None
    expr = m.group(1).strip()
    if re.fullmatch(r"-?\d+", expr):
        return int(expr)
    v, _ = const_value(uni, expr)
    return v


CONST_RE = r"\b(?:const\s+(?:int|long)|static\s+readonly\s+(?:int|long))\s+(?:[^;]*?[,\s])?%s\s*=\s*([^,;]+)"


def const_value(uni, name, depth=0):
    if depth > 6:
        return None, None
    name = name.split(".")[-1]
    for f in uni.all_plugin.assigned_files(name):
        s = uni.all_plugin.get(f)
        m = re.search(CONST_RE % re.escape(name), s.code)
        if m:
            expr = m.group(1).strip()
            if re.fullmatch(r"-?\d+", expr):
                return int(expr), "%s:%d" % (f, s.line(m.start()))
            ids = re.fullmatch(r"([\w.]+)", expr)
            if ids:
                v, _ = const_value(uni, ids.group(1), depth + 1)
                return v, "%s:%d" % (f, s.line(m.start()))
            mm = re.fullmatch(r"([\w.]+)\s*([*+\-])\s*(\d+|[\w.]+)", expr)
            if mm:
                a, _ = const_value(uni, mm.group(1), depth + 1) if not mm.group(1).isdigit() else (int(mm.group(1)), 0)
                b, _ = const_value(uni, mm.group(3), depth + 1) if not mm.group(3).isdigit() else (int(mm.group(3)), 0)
                if a is None or b is None:
                    return None, None
                return {"*": a * b, "+": a + b, "-": a - b}[mm.group(2)], "%s:%d" % (f, s.line(m.start()))
            return None, None
    return None, None


# ----------------------------------------------------------------------------------------------- A3 rows
# Ruling FRAME-TIME-ROUND-R2: (1) a row's kind is DEFAULT-DENY: "zero" only when this sweep proves that no write site of
# any of the row's fields is reachable in the measured span (no write inside a live member, before its cut); every other
# row the build cannot prove drained is DEPENDENT. H1: every live reader member of a dependent row counts its reads:
# its FrameTime text (SCR_FRAMETIME defined) carries FtA3.Read(FtA3.<row>), directly or through a FrameTime-only helper
# that does; and no FtA3.Read of a row sits anywhere but in that row's live readers (or a helper only they call).
A3_PATH = os.path.join(HERE, "gate_specs", "a3.py")
FT_DEFINED = {"SCR_FRAMETIME"}
# FtA3.Read(FtA3.<row>) and FtA3.ReadOnce(FtA3.<row>, ref serial) (a growth row, once per instance per game)
READ_CALL = re.compile(r"\bFtA3\s*\.\s*Read(?:Once)?\s*\(\s*FtA3\s*\.\s*(\w+)\s*[,)]")
ZERO_PROOFS = ("sweep:no-live-write",)

# COVERED: a live reader member whose reads of one dependent row are counted by the callers that hand it that row's
# structure. (row, Class, Member, covering callers, reason). The check: every covering caller is a live reader of the
# row carrying its FtA3.Read and calls the member; every live caller of the member is a covering caller of some
# COVERED entry for that member (so no call reaches it uncounted); the member is not a live root.
COVERED = [
    ("CE_Top", "CombatEvidence", "TopInsert", ("DrainResiduals",),
     "DrainResiduals counts FtA3.Read(CE_Top) right before its TopInsert(g.Top, ...) call; HtUpsert's call hands it "
     "g.Ht, which CE_Ht counts"),
    ("CE_Ht", "CombatEvidence", "TopInsert", ("HtUpsert",),
     "HtUpsert counts FtA3.Read(CE_Ht) on entry, before its TopInsert(g.Ht, ...) call; DrainResiduals's call hands it "
     "g.Top, which CE_Top counts"),
    ("IC_Clock", "ClockBook", "Median", ("FlushBucket",),
     "the two Medians over _gapHist and _tdHist run inside FlushBucket, which counts FtA3.Read(IC_Clock) on entry and "
     "whose calibration (FtCalClock) runs both Medians at their costliest content"),
]


def load_a3():
    import runpy
    return runpy.run_path(A3_PATH)["A3"]


class FtView:
    """The FrameTime text of one source: comments and strings blanked, SCR_FRAMETIME DEFINED (its #if branches kept,
    its #else branches blanked), the component slice as in Src. Every offset equals Src's (blanking keeps them)."""
    line = Src.line

    def __init__(self, s):
        self.name, self.raw, self.slice, self.stats = s.name, s.raw, s.slice, {}
        code = apply_preprocessor(blank_comments_strings(s.raw), {}, defined=FT_DEFINED)
        if s.slice:
            ls = code.split("\n")
            for i in range(len(ls)):
                if i < s.slice[0] - 1 or i >= s.slice[1]:
                    ls[i] = " " * len(ls[i])
            code = "\n".join(ls)
        self.code = code
        self.nl = [i for i, c in enumerate(code) if c == "\n"]


class A3Index:
    """The FtA3.Read sites of the FrameTime text, per member. A FrameTime member with a release twin (same type path
    and name; the same body when the #if sits inside it, else the nearest by position: an #if/#else pair of whole
    members) stands for that twin; one without is a FrameTime-only HELPER, reached through calls by name."""

    def __init__(self, uni, drop=None, plant=None):
        self.uni = uni
        self.reads = []          # (view, pos, const, ft member)
        self.twin = {}           # id(ft member) -> release member
        self.helpers = {}        # name -> [ft member]
        self.direct = {}         # id(ft member) -> {const}
        self.ft_of = {}          # release member -> [ft member]
        self.outside = []        # (file, line, const): a Read outside any component member
        for key in sorted(uni.srcs):
            s = uni.srcs[key]
            v = FtView(s)
            _types, mems = parse_structure(v)
            rel = uni.mem_index.get(id(s), [])
            by_name = {}
            for m in rel:
                by_name.setdefault((m.owner.path, m.name), []).append(m)
            mems.sort(key=lambda m: m.start)
            for fm in mems:
                cands = by_name.get((fm.owner.path, fm.name), [])
                tw = next((m for m in cands if m.body_start == fm.body_start), None)
                if tw is None and cands:
                    tw = min(cands, key=lambda m: abs(m.start - fm.start))
                if tw is not None:
                    self.twin[id(fm)] = tw
                    self.ft_of.setdefault(tw, []).append(fm)
                else:
                    self.helpers.setdefault(fm.name, []).append(fm)
            for mt in READ_CALL.finditer(v.code):
                p, const = mt.start(), mt.group(1)
                if drop is not None and (s.name, v.line(p)) == drop:
                    continue
                fm = None
                for m in mems:
                    if m.start <= p <= m.end:
                        if fm is None or m.start > fm.start:
                            fm = m
                if fm is None:
                    self.outside.append((s.name, v.line(p), const))
                    continue
                self.reads.append((v, p, const, fm))
                self.direct.setdefault(id(fm), set()).add(const)
        if plant is not None:
            # selftest: count one FtA3.Read of `const` inside release member `m` (a planted site)
            const, m = plant
            fm = self.ft_of[m][0]
            self.reads.append((None, m.body_start, const, fm))
            self.direct.setdefault(id(fm), set()).add(const)
        # FtA3.Read in a plugin file outside every component source (FtA3.cs itself defines Read, not FtA3.Read)
        comp_files = {s.name for s in uni.srcs.values() if not s.slice}
        sliced = [s for s in uni.srcs.values() if s.slice]
        for f in sorted(os.listdir(PLUGIN)):
            if not f.endswith(".cs") or f in comp_files:
                continue
            raw = uni.all_plugin.raw(f) if hasattr(uni.all_plugin, "raw") else None
            if raw is None:
                continue
            code = blank_comments_strings(raw)
            for mt in READ_CALL.finditer(code):
                ln = code.count("\n", 0, mt.start()) + 1
                if any(s.name == f and s.slice[0] <= ln <= s.slice[1] for s in sliced):
                    continue
                self.outside.append((f, ln, mt.group(1)))

    def calls_in(self, fm):
        code = fm.src.code[fm.body_start:fm.end]
        return {n for n in re.findall(r"\b([A-Za-z_]\w*)\s*\(", code) if n in self.helpers}

    def helper_rows(self, name, depth=0, seen=None):
        seen = set() if seen is None else seen
        if name in seen or depth > 3:
            return set()
        seen.add(name)
        rows = set()
        for h in self.helpers.get(name, []):
            rows |= self.direct.get(id(h), set())
            for c in self.calls_in(h):
                rows |= self.helper_rows(c, depth + 1, seen)
        return rows

    def effective(self, m):
        """{const: "direct" | "helper:<name>"} counted inside release member m."""
        out = {}
        for fm in self.ft_of.get(m, []):
            for c in self.direct.get(id(fm), set()):
                out[c] = "direct"
            for h in sorted(self.calls_in(fm)):
                for c in self.helper_rows(h):
                    out.setdefault(c, "helper:" + h)
        return out

    def callers_of_helper(self, name):
        out = []
        for key, fms in self.ft_of.items():
            for fm in fms:
                if name in self.calls_in(fm):
                    out.append(("release", key))
        for hn, hs in self.helpers.items():
            for h in hs:
                if name in self.calls_in(h) and hn != name:
                    out.append(("helper", hn))
        return out


def a3_rows_of_md(text):
    """{survivor id: (component, [Class.Field])} from SURVIVORS.md's rows."""
    rows, _c, _o, _e = parse_md(text)
    return {r[0]: (r[1], re.findall(r"`(\w+\.\w+)`", r[2])) for r in rows}


def live_callers(uni, sw):
    """{callee: {live caller}} over the live call graph (cuts and guards applied)."""
    if getattr(sw, "_live_callers", None) is None:
        out = {}
        for c in sw.live:
            for e in edges(uni, c, sw.cuts.get(c), sw.guards.get(c, ())):
                out.setdefault(e, set()).add(c)
        sw._live_callers = out
    return sw._live_callers


LIVE_PROOF = "live:executed"


def a3_check(uni, sw, text, fields_out, spec=None, drop=None, plant=None, noscope=None):
    """The A3 checks: (i) a3.py names every SURVIVORS.md row once, as a 5-tuple with a known kind; (ii) every zero row
    carries a sweep proof this function re-derives (no live write of any of its fields); (iii) every live reader member
    of every dependent row counts it (FtA3.Read, direct, through a helper, or COVERED by its callers), and every
    FtA3.Read sits in a live reader of its row; (iv) ruling FRAME-TIME-ROUND-R4: every FtA3.Read of a live row
    (proof live:executed, calibrated in game) sits inside its member's timing scope, FtA3.TEnter() before it and
    FtA3.TExit(ftScope) after it in the same member (noscope: a (file, line) read treated as unscoped, the selftest's
    control). Returns (fails, report) where report is per row."""
    fails = []
    spec = load_a3() if spec is None else spec
    md = a3_rows_of_md(text)
    names = {}
    for row in spec:
        if len(row) != 5:
            fails.append("a3.py row %r: needs (name, survivor id, kind, reason, proof)" % (row,))
            continue
        n, sid, kind, why, proof = row
        if sid in names.values():
            fails.append("a3.py: %s named twice" % sid)
        names[n] = sid
        if sid not in md:
            fails.append("a3.py row %s names %s, which SURVIVORS.md does not list" % (n, sid))
        if kind not in ("dependent", "drained", "zero"):
            fails.append("a3.py row %s: kind %r" % (n, kind))
        if kind == "drained" and proof != "probe:a3drain":
            fails.append("a3.py row %s: drained needs proof probe:a3drain, got %r" % (n, proof))
        if kind == "zero" and proof not in ZERO_PROOFS:
            fails.append("a3.py row %s: zero needs a sweep proof this sweep checks (%s), got %r"
                         % (n, "|".join(ZERO_PROOFS), proof))
        # ruling FRAME-TIME-ROUND-R5: the scratch A3 is retired; every dependent row is calibrated only by its in-game
        # executed lines, so its proof is live:executed and nothing else
        if kind == "dependent" and proof != LIVE_PROOF:
            fails.append("a3.py row %s: a dependent row is calibrated only in game (ruling FRAME-TIME-ROUND-R5), its "
                         "proof is %s, got %r" % (n, LIVE_PROOF, proof))
    for sid in md:
        if sid not in names.values():
            fails.append("SURVIVORS.md row %s has no a3.py row" % sid)
    idx = A3Index(uni, drop=drop, plant=plant)
    live_rows = {row[0] for row in spec if len(row) == 5 and row[2] == "dependent" and row[4] == LIVE_PROOF}
    scoped = 0
    # noscope: one (file, line) or a set of them, treated as unscoped (the selftest's controls)
    ns = {noscope} if isinstance(noscope, tuple) else set(noscope or ())

    def in_scope(view, mem, pos):
        a = view.code.rfind("FtA3.TEnter()", mem.body_start, pos)
        b = view.code.find("FtA3.TExit(ftScope)", pos, mem.end + 1)
        return a >= 0 and b >= 0 and (view.name, view.line(pos)) not in ns

    ft_members = [m for ms in idx.ft_of.values() for m in ms] + [m for ms in idx.helpers.values() for m in ms]

    def helper_sites(name, depth=0):
        """Round 6 (ruling FRAME-TIME-ROUND-R5): a Read inside a FrameTime-only HELPER marks the innermost open scope,
        which must be its caller's: [(view, member, pos)] of every call of the helper from a release twin, through
        nested helpers (depth 3)."""
        out = []
        if depth > 3:
            return out
        for m in ft_members:
            for mt in re.finditer(r"\b%s\s*\(" % re.escape(name), m.src.code[m.body_start:m.end]):
                pos = m.body_start + mt.start()
                if id(m) in idx.twin:
                    out.append((m.src, m, pos))
                else:
                    out += helper_sites(m.name, depth + 1)
        return out

    for (v, p, const, fm) in idx.reads:
        if const not in live_rows or v is None:
            continue
        if id(fm) not in idx.twin:
            # a helper's Read: the helper itself carries no scope (its scope would take the read's cost from its
            # reader), and every call reaching it from a reader sits in that reader's scope
            sites = helper_sites(fm.name)
            if "FtA3.TEnter()" in v.code[fm.body_start:fm.end + 1]:
                fails.append("a3 row %s: the helper %s at %s:%d opens its own timing scope; its Read must mark its "
                             "caller's" % (const, fm.name, v.name, v.line(p)))
            elif not sites:
                fails.append("a3 row %s: the helper %s at %s:%d has no caller in a release member"
                             % (const, fm.name, v.name, v.line(p)))
            else:
                out = [(sv, sm, sp) for (sv, sm, sp) in sites if not in_scope(sv, sm, sp)]
                for (sv, sm, sp) in out:
                    fails.append("a3 row %s: the call of helper %s at %s:%d sits outside a timing scope (FtA3.TEnter ... "
                                 "FtA3.TExit(ftScope) in its member %s)" % (const, fm.name, sv.name, sv.line(sp), sm.name))
                if not out:
                    scoped += 1
            continue
        if not in_scope(v, fm, p):
            fails.append("a3 row %s: the live read at %s:%d sits outside a timing scope (FtA3.TEnter ... "
                         "FtA3.TExit(ftScope) in its member %s)" % (const, v.name, v.line(p), fm.name))
        else:
            scoped += 1
    if live_rows and not scoped:
        fails.append("a3.py marks %s live, but no FtA3.Read of them was found" % sorted(live_rows))
    callers = live_callers(uni, sw)
    report = []
    readers_of = {}
    for row in spec:
        if len(row) != 5 or row[1] not in md:
            continue
        n, sid, kind, why, proof = row
        comp, quals = md[sid]
        lw, lr = {}, {}
        for q in quals:
            st = fields_out.get((comp, q))
            if st is None:
                continue
            for (s, p, wk, m) in st[2]:
                if m is not None and m in sw.live and p < sw.cuts.get(m, m.end + 1):
                    lw.setdefault(m, []).append("%s:%d" % (s.name, s.line(p)))
            for r in st[3]:
                if sw.is_live_read(r):
                    lr.setdefault(r[2], []).append("%s:%d" % (r[0].name, r[0].line(r[1])))
        readers_of[n] = set(lr)
        ent = dict(name=n, sid=sid, kind=kind, proof=proof, writers=lw, readers={}, covered={})
        if kind == "zero":
            if lw:
                fails.append("a3.py row %s (%s) is zero (%s) but the sweep finds live writes: %s" % (
                    n, sid, proof, "; ".join("%s %s" % (m.key, ",".join(v[:3])) for m, v in
                                             sorted(lw.items(), key=lambda kv: kv[0].key))))
        if kind == "dependent":
            for m in sorted(lr, key=lambda m: m.key):
                eff = idx.effective(m)
                if n in eff:
                    ent["readers"][m] = eff[n]
                    continue
                cov = [c for c in COVERED if c[0] == n and c[2] == m.name and m.owner.name == c[1]]
                if cov:
                    ent["covered"][m] = cov[0]
                    continue
                fails.append("a3 row %s (%s): live reader %s (reads at %s) carries no FtA3.Read(FtA3.%s)" % (
                    n, sid, m.key, ",".join(lr[m][:3]), n))
        report.append(ent)
    # COVERED entries: covering callers read and call; every live caller of the member covers it
    for ent in report:
        for m, cov in ent["covered"].items():
            n, _cls, _mn, by, why = cov
            if m in sw.live_roots:
                fails.append("COVERED %s %s: a live root has no caller to count it" % (n, m.key))
            union = set()
            for c in COVERED:
                if c[2] == m.name and c[1] == m.owner.name:
                    union |= set(c[3])
            for c in sorted(callers.get(m, set()), key=lambda c: c.key):
                if c.name not in union:
                    fails.append("COVERED %s %s: live caller %s is no covering caller" % (n, m.key, c.key))
            for cn in by:
                cs = [c for c in callers.get(m, set()) if c.name == cn]
                if not cs:
                    fails.append("COVERED %s %s: covering caller %s does not call it live" % (n, m.key, cn))
                for c in cs:
                    if c not in readers_of.get(n, set()) or n not in idx.effective(c):
                        fails.append("COVERED %s %s: covering caller %s is not a counting reader of %s" % (
                            n, m.key, c.key, n))
    for c in COVERED:
        if not any(c[0] == e["name"] and any(v is c for v in e["covered"].values()) for e in report):
            fails.append("COVERED %s %s.%s matches no uncounted live reader" % (c[0], c[1], c[2]))
    # every FtA3.Read sits in a live reader of its row (or a helper only such readers reach)
    dep = {row[0] for row in spec if len(row) == 5 and row[2] == "dependent"}

    def helper_ok(name, const, depth=0):
        cl = idx.callers_of_helper(name)
        if not cl:
            return ["helper %s is never called" % name]
        bad = []
        for kind, x in cl:
            if kind == "release":
                if x not in readers_of.get(const, set()):
                    bad.append("helper %s is called from %s, no live reader of %s" % (name, x.key, const))
            elif depth < 3:
                bad += helper_ok(x, const, depth + 1)
            else:
                bad.append("helper chain too deep at %s" % x)
        return bad

    nsites = 0
    for (v, p, const, fm) in idx.reads:
        nsites += 1
        where = "%s:%d" % (v.name, v.line(p)) if v is not None else "a planted site in %s" % idx.twin.get(id(fm), fm).key
        if const not in dep:
            fails.append("FtA3.Read(FtA3.%s) at %s: %s is no dependent a3 row" % (const, where, const))
            continue
        tw = idx.twin.get(id(fm))
        if tw is not None:
            if tw not in readers_of.get(const, set()):
                fails.append("FtA3.Read(FtA3.%s) at %s sits in %s, which is no live reader of %s" % (
                    const, where, tw.key, const))
        else:
            for b in helper_ok(fm.name, const):
                fails.append("FtA3.Read(FtA3.%s) at %s: %s" % (const, where, b))
    for f, ln, const in idx.outside:
        fails.append("FtA3.Read(FtA3.%s) at %s:%d sits outside every component member" % (const, f, ln))
    return fails, dict(rows=report, sites=nsites)


def a3_summary(rep):
    dep = [e for e in rep["rows"] if e["kind"] == "dependent"]
    nr = sum(len(e["readers"]) for e in dep)
    nd = sum(1 for e in dep for v in e["readers"].values() if v == "direct")
    nh = nr - nd
    nc = sum(len(e["covered"]) for e in dep)
    z = [e for e in rep["rows"] if e["kind"] == "zero"]
    dr = [e for e in rep["rows"] if e["kind"] == "drained"]
    return ("A3 rows: %d dependent, %d drained, %d zero (proof re-derived: no live write); dependent live readers %d, "
            "every one counted: %d carry FtA3.Read directly, %d through a FrameTime helper, %d covered by their callers; "
            "%d FtA3.Read sites, each in a live reader of its row" % (len(dep), len(dr), len(z), nr + nc, nd, nh, nc,
                                                                      rep["sites"]))


def print_a3_detail(rep):
    for e in rep["rows"]:
        print("A3 %-15s %s %-9s proof=%s live writers %d, live readers %d" % (
            e["name"], e["sid"], e["kind"], e["proof"] or "-", len(e["writers"]),
            len(e["readers"]) + len(e["covered"])))
        for m, how in sorted(e["readers"].items(), key=lambda kv: kv[0].key):
            print("      R %s %s" % (m.key, how))
        for m, cov in sorted(e["covered"].items(), key=lambda kv: kv[0].key):
            print("      R %s covered by %s" % (m.key, ",".join(cov[3])))
        if e["kind"] == "zero":
            print("      live write sites: %d" % sum(len(v) for v in e["writers"].values()))


# ----------------------------------------------------------------------------------------------- generated text
BLANK_LEAD = "The script prints the blanked line count per file ("


def blanked_counts(uni):
    return [(key, uni.srcs[key].stats.get("blanked", 0)) for key in sorted(uni.srcs)]


def blanked_text(uni):
    return ", ".join("%s %d" % kv for kv in blanked_counts(uni))


def check_blanked(uni, text):
    i = text.find(BLANK_LEAD)
    if i < 0:
        return ["SURVIVORS.md Method: no '%s...)' sentence" % BLANK_LEAD]
    j = text.find(")", i + len(BLANK_LEAD))
    got = re.findall(r"([\w.#]+)\s+(\d+)", text[i + len(BLANK_LEAD):j])
    want = [(k, str(v)) for k, v in blanked_counts(uni)]
    if got != want:
        diff = sorted(set(got) ^ set(want))
        return ["SURVIVORS.md blanked-line counts differ from the sweep: md %s, sweep %s (differing items %s)" % (
            ", ".join("%s %s" % g for g in got), ", ".join("%s %s" % w for w in want), diff)]
    return []


def site_text(entries):
    by = {}
    for (s, p, m) in entries:
        by.setdefault(m.name if m is not None else "?", set()).add("%s:%d" % (s.name, s.line(p)))
    parts = []
    for name in sorted(by):
        locs = sorted(by[name], key=lambda x: (x.split(":")[0], int(x.split(":")[1])))
        parts.append("%s %s" % (name, locs[0] + (" +%d" % (len(locs) - 1) if len(locs) > 1 else "")))
    return "; ".join(parts[:8]) + ("; +%d more members" % (len(parts) - 8) if len(parts) > 8 else "")


def row_sites(sw, fields_out, comp, quals):
    """(declared, writers, live readers) as the sweep writes them for one row."""
    fds, w, r = [], [], []
    for q in quals:
        st = fields_out.get((comp, q))
        if st is None:
            return None
        fds.append(st[1])
        w += [(s, p, m) for (s, p, wk, m) in st[2]]
        r += [(s, p, m) for (s, p, m, fl) in st[3] if sw.is_live_read((s, p, m, fl))]
    first = min(fds, key=lambda f: (f.src.name, f.pos))
    return first.decl, site_text(w), site_text(r)


def check_sites(sw, fields_out, text):
    fails = []
    rows, _c, _o, _e = parse_md(text)
    for r in rows:
        quals = re.findall(r"`(\w+\.\w+)`", r[2])
        got = row_sites(sw, fields_out, r[1], quals)
        if got is None:
            continue
        for col, name, want in ((3, "declared", got[0]), (5, "writers", got[1]), (6, "live readers", got[2])):
            if r[col] != want:
                fails.append("row %s: %s column is %r, the sweep writes %r" % (r[0], name, r[col][:120], want[:120]))
    return fails


def write_md(uni, sw, text, fields_out, stats, rows_per):
    """Regenerate the sweep's own text in SURVIVORS.md: the blanked-line counts, the counts table, and per row the
    declared / writers / live-readers columns and the line of every cited capacity constant."""
    i = text.find(BLANK_LEAD)
    if i < 0:
        raise SystemExit("--write-md: SURVIVORS.md has no '%s...)' sentence; nothing written" % BLANK_LEAD)
    j = text.find(")", i + len(BLANK_LEAD))
    words = blanked_text(uni).split(" ")
    lines, cur = [], ""
    width = 105 - (i + len(BLANK_LEAD) - (text.rfind("\n", 0, i) + 1))
    for wd in words:
        if len(cur) + len(wd) + 1 > width and cur:
            lines.append(cur)
            cur = "   " + wd
            width = 105
        else:
            cur = (cur + " " + wd) if cur else wd
    lines.append(cur)
    text = text[:i + len(BLANK_LEAD)] + "\n".join(lines) + text[j:]
    out = []
    for ln in text.split("\n"):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")] if ln.startswith("|") else None
        if cells and re.fullmatch(r"S\d{2,3}", cells[0]) and len(cells) >= 9:
            quals = re.findall(r"`(\w+\.\w+)`", cells[2])
            got = row_sites(sw, fields_out, cells[1], quals)
            if got is not None:
                cells[3], cells[5], cells[6] = got

                def repin(mt):
                    nm, val, f, l = mt.group(1), mt.group(2), mt.group(3), int(mt.group(4))
                    s = uni.all_plugin.get(f)
                    cands = [k + 1 for k, cl in enumerate(s.code.split("\n")) if re.search(CONST_RE % re.escape(nm), cl)]
                    if cands:
                        l = min(cands, key=lambda c: abs(c - l))
                    return "%s = %s (%s:%d)" % (nm, val, f, l)
                cells[4] = re.sub(CAP_ITEM, repin, cells[4])
                ln = "| " + " | ".join(cells) + " |"
        elif cells and cells[0] in COMP_NAMES and len(cells) >= 9 and re.fullmatch(r"\d+", cells[1] or "x"):
            st = stats[cells[0]]
            ln = "| %s | %d | %d | %d | %d | %d | %d | %d | %d |" % (
                cells[0], st["declared"], st["written"], st["write_sites"], st["construction"],
                st["reset"] + st["reclassified"], st["survivors"], st["live"], rows_per.get(cells[0], 0))
        out.append(ln)
    return "\n".join(out)


def check_table(uni, sw, text, quiet=False):
    rows, counts, overrides, errs = parse_md(text)
    fails = list(errs)
    stats, fields_out, ofails = sweep_results(uni, sw, overrides)
    fails += ofails
    want = {k: v for k, v in fields_out.items() if v[0] == "survives_live"}
    named = {}
    for r in rows:
        comp = r[1]
        if comp not in COMP_NAMES:
            fails.append("row %s: unknown component %r" % (r[0], comp))
            continue
        quals = re.findall(r"`(\w+\.\w+)`", r[2])
        if not quals:
            fails.append("row %s names no `Class.Field`" % r[0])
        for q in quals:
            if (comp, q) in named:
                fails.append("row %s: %s %s already in row %s" % (r[0], comp, q, named[(comp, q)]))
            named[(comp, q)] = r[0]
            if (comp, q) not in want:
                st = fields_out.get((comp, q))
                fails.append("row %s: %s %s is not a survivor read live in the sweep (%s)" % (
                    r[0], comp, q, st[0] if st else "not declared"))
        # declared file:line must declare one of the row's fields
        dm = re.findall(r"([\w.]+\.cs):(\d+)", r[3])
        if not dm:
            fails.append("row %s: declared column has no file:line" % r[0])
        for f, l in dm:
            s = uni.all_plugin.get(f)
            if s is None or int(l) > len(s.raw_lines):
                fails.append("row %s: declared %s:%s does not exist" % (r[0], f, l))
                continue
            line = s.raw_lines[int(l) - 1]
            if not any(re.search(r"\b%s\b" % re.escape(q.split(".")[1]), line) for q in quals):
                fails.append("row %s: %s:%s declares none of %s" % (r[0], f, l, ", ".join(quals)))
        # capacity: each `NAME = int (File.cs:NNN)` must name a constant declared on that line whose value
        # (aliases resolved) equals int; any other number in the column is a hand-typed capacity
        cap = r[4]
        cited = re.findall(CAP_ITEM, cap)
        for nm, val, f, l in cited:
            s = uni.all_plugin.get(f)
            if s is None or int(l) > len(s.raw_lines):
                fails.append("row %s: capacity citation %s:%s does not exist" % (r[0], f, l))
                continue
            v = const_on_line(uni, s, int(l), nm)
            if v is None:
                fails.append("row %s: capacity constant %s is not declared at %s:%s" % (r[0], nm, f, l))
            elif v != int(val):
                fails.append("row %s: capacity %s = %s in the table, %d in code (%s:%s)" % (r[0], nm, val, v, f, l))
        rest = re.sub(r"[\w.]+\.cs:\d+", " ", re.sub(CAP_ITEM, " ", cap))  # file:line citations carry digits
        if re.search(r"\d", rest):
            fails.append("row %s: capacity column carries a number not tied to a cited named constant: %r" % (r[0], cap))
    for (comp, q), v in sorted(want.items(), key=lambda kv: kv[0]):
        if (comp, q) not in named:
            fails.append("survivor read live with no row: %s %s (declared %s)" % (comp, q, v[1].decl))
    rows_per = {c: len({named[k] for k in named if k[0] == c}) for c in COMP_NAMES}
    fails += check_blanked(uni, text)
    fails += check_sites(sw, fields_out, text)
    for comp in COMP_NAMES:
        st = stats[comp]
        got = [st["declared"], st["written"], st["write_sites"], st["construction"], st["reset"] + st["reclassified"],
               st["survivors"], st["live"], rows_per[comp]]
        tab = counts.get(comp)
        if tab is None:
            fails.append("counts table has no row for %s" % comp)
        elif tab != got:
            fails.append("counts for %s: table %s, sweep %s" % (comp, tab, got))
    return fails, stats, fields_out, rows_per


def print_stats(uni, sw, stats, rows_per):
    print("SCR_FRAMETIME / test-only branches blanked (code lines):")
    for key in sorted(uni.srcs):
        s = uni.srcs[key]
        extra = " slice %d-%d" % s.slice if s.slice else ""
        print("  %-34s %4d%s" % (key, s.stats.get("blanked", 0), extra))
    print("live members %d (roots %d), point-boundary members %d (roots %d), stop members %d" % (
        len(sw.live), len(sw.live_roots), len(sw.boundary), len(sw.point_roots), len(sw.stop_set)))
    print("| component | fields declared | fields written | write sites | construction-only | reset at point "
          "| survivors | survivors read live | rows |")
    print("|---|---|---|---|---|---|---|---|---|")
    for comp in COMP_NAMES:
        st = stats[comp]
        print("| %s | %d | %d | %d | %d | %d | %d | %d | %d |" % (
            comp, st["declared"], st["written"], st["write_sites"], st["construction"],
            st["reset"] + st["reclassified"], st["survivors"], st["live"], rows_per.get(comp, 0)))


def print_detail(sw, fields_out, which):
    for (comp, q), (c, fd, writes, reads) in sorted(fields_out.items(), key=lambda kv: (kv[0][0], kv[1][1].src.name, kv[1][1].pos)):
        if c not in which:
            continue
        lr = [r for r in reads if sw.is_live_read(r)]
        wsites = sorted({"%s:%d(%s)" % (s.name, s.line(p), (m.name if m else "?")) for (s, p, wk, m) in writes})
        rsites = sorted({"%s:%d(%s,%s)" % (s.name, s.line(p), m.name, fl) for (s, p, m, fl) in lr})
        print("%s %-6s %-34s decl %-28s type %s" % (comp[:4], c[:6], q, fd.decl, fd.type_s))
        print("      W %d: %s" % (len(writes), " ".join(wsites[:12]) + (" ..." if len(wsites) > 12 else "")))
        if lr:
            print("      R %d: %s" % (len(lr), " ".join(rsites[:12]) + (" ..." if len(rsites) > 12 else "")))


def selftest(uni, sw, text):
    ok = True
    f0, _, _, _ = check_table(uni, sw, text, quiet=True)
    c_pass = not f0
    print("  (c) unchanged table: %s" % ("PASS" if c_pass else "FAIL (%d failures)" % len(f0)))
    ok &= c_pass
    lines = text.split("\n")
    idx = next((i for i, l in enumerate(lines) if re.match(r"\|\s*S\d+\s*\|", l)), None)
    if idx is None:
        print("  (a) no survivor row to remove")
        return False
    a_text = "\n".join(lines[:idx] + lines[idx + 1:])
    fa, _, _, _ = check_table(uni, sw, a_text, quiet=True)
    a_ok = any("no row" in x for x in fa)
    print("  (a) one survivor row removed: %s" % ("FAILS as required (%d failures, e.g. %s)" % (len(fa), fa[0])
                                                   if a_ok else "did NOT fail on a missing row"))
    ok &= a_ok
    b_text, done = None, False
    out = []
    for l in lines:
        if not done and re.match(r"\|\s*S\d+\s*\|", l):
            cells = l.split("|")
            if len(cells) > 6:
                cap = cells[5]
                m = re.search(r"\b([A-Z][A-Z0-9_]*[A-Z0-9])\s*=\s*(-?\d+)", cap)
                if m:
                    cells[5] = cap[:m.start(2)] + str(int(m.group(2)) + 1) + cap[m.end(2):]
                    l = "|".join(cells)
                    done = True
        out.append(l)
    if not done:
        print("  (b) no capacity constant in the table")
        return False
    fb, _, _, _ = check_table(uni, sw, "\n".join(out), quiet=True)
    b_ok = any("capacity" in x and "in code" in x for x in fb)
    print("  (b) one capacity changed by 1: %s" % ("FAILS as required (%s)" % next(x for x in fb if "capacity" in x)
                                                   if b_ok else "did NOT fail on the capacity"))
    ok &= b_ok
    ok &= selftest_a3(uni, sw, text)
    return ok


def selftest_a3(uni, sw, text):
    """Controls of the round-2 checks (ruling FRAME-TIME-ROUND-R2): each mutation must fail for its own reason."""
    ok = True
    _f, _s, fields_out, _r = check_table(uni, sw, text, quiet=True)
    spec = load_a3()
    f0, rep = a3_check(uni, sw, text, fields_out, spec=spec)
    c_ok = not f0
    print("  (c2) unchanged a3.py and FrameTime text: %s" % ("PASS" if c_ok else "FAIL (%s)" % f0[:3]))
    ok &= c_ok
    # (d) one FtA3.Read site removed: a live reader whose only count of its row was that site
    idx = A3Index(uni)
    readers = {e["name"]: e["readers"] for e in rep["rows"]}
    pick = None
    for (v, p, const, fm) in idx.reads:
        tw = idx.twin.get(id(fm))
        if tw is None or readers.get(const, {}).get(tw) != "direct":
            continue
        same = [r for r in idx.reads if r[3] is fm and r[2] == const]
        line_reads = [r for r in idx.reads if r[0] is v and v.line(r[1]) == v.line(p)]
        if len(same) == 1 and len(line_reads) == 1 and not any(const in idx.helper_rows(h) for h in idx.calls_in(fm)):
            pick = (v.name, v.line(p), const, tw)
            break
    if pick is None:
        print("  (d) no single-site FtA3.Read to remove")
        return False
    fd, _ = a3_check(uni, sw, text, fields_out, spec=spec, drop=(pick[0], pick[1]))
    d_ok = any("carries no FtA3.Read(FtA3.%s)" % pick[2] in x and pick[3].key in x for x in fd)
    print("  (d) FtA3.Read(FtA3.%s) at %s:%d removed: %s" % (pick[2], pick[0], pick[1], "FAILS as required (%s)" % next(
        x for x in fd if "carries no" in x) if d_ok else "did NOT fail on the uncounted reader (%s)" % fd[:2]))
    ok &= d_ok
    # (d2) an FtA3.Read planted in a live member that reads nothing of that row
    dep = [e for e in rep["rows"] if e["kind"] == "dependent"]
    row = dep[0]
    others = sorted((m for m in idx.ft_of if m in sw.live and m not in row["readers"] and m not in row["covered"]),
                    key=lambda m: m.key)
    fp, _ = a3_check(uni, sw, text, fields_out, spec=spec, plant=(row["name"], others[0]))
    p_ok = any("is no live reader of %s" % row["name"] in x for x in fp)
    print("  (d2) FtA3.Read(FtA3.%s) planted in %s: %s" % (row["name"], others[0].key, "FAILS as required (%s)" % next(
        x for x in fp if "no live reader" in x) if p_ok else "did NOT fail on the misplaced read (%s)" % fp[:2]))
    ok &= p_ok
    # (h) ruling FRAME-TIME-ROUND-R4: a live row's read treated as unscoped fails; a calibrated row marked live,
    # whose readers carry no timing scope, fails for every one of its reads
    lr = [(v, p, const, fm) for (v, p, const, fm) in idx.reads
          if v is not None and any(r[0] == const and r[2] == "dependent" and r[4] == LIVE_PROOF for r in spec)]
    if not lr:
        print("  (h) no live row's read in the FrameTime text: the scope control has no subject")
        return False
    v_, p_, c_, fm_ = lr[0]
    fh, _ = a3_check(uni, sw, text, fields_out, spec=spec, noscope=(v_.name, v_.line(p_)))
    h_ok = any("sits outside a timing scope" in x and "%s:%d" % (v_.name, v_.line(p_)) in x for x in fh)
    print("  (h) the live read of %s at %s:%d unscoped: %s" % (c_, v_.name, v_.line(p_), "FAILS as required"
                                                             if h_ok else "did NOT fail (%s)" % fh[:2]))
    ok &= h_ok
    # (h2) round 6 (ruling FRAME-TIME-ROUND-R5): every dependent row is live; a row whose every read is unscoped fails
    # once per read, and a dependent row given the retired scratch proof "" fails
    calr = next(e for e in dep if len([r for r in lr if r[2] == e["name"]]) >= 2)
    sites = {(v.name, v.line(p)) for (v, p, const, fm) in lr if const == calr["name"]}
    fh2, _ = a3_check(uni, sw, text, fields_out, spec=spec, noscope=sites)
    nfail = sum(1 for x in fh2 if "a3 row %s: the live read" % calr["name"] in x)
    h2_ok = nfail == len([r for r in lr if r[2] == calr["name"]])
    print("  (h2) every read of %s unscoped (%d sites): %s" % (calr["name"], len(sites), "FAILS as required, %d reads"
                                                             % nfail if h2_ok else "did NOT fail per read (%s)" % fh2[:2]))
    ok &= h2_ok
    spec_s = [(n, sid, k, w, "") if n == calr["name"] else (n, sid, k, w, pf) for (n, sid, k, w, pf) in spec]
    fs, _ = a3_check(uni, sw, text, fields_out, spec=spec_s)
    s_ok = any("a3.py row %s: a dependent row is calibrated only in game" % calr["name"] in x for x in fs)
    print("  (h3) %s given the retired scratch proof \"\": %s" % (calr["name"], "FAILS as required" if s_ok
                                                                  else "did NOT fail (%s)" % fs[:2]))
    ok &= s_ok
    # (h4) a helper's Read is judged at its callers: one caller's call treated as unscoped fails, naming the helper
    hr = [(v, p, const, fm) for (v, p, const, fm) in lr if id(fm) not in idx.twin]
    if not hr:
        print("  (h4) no helper read of a live row: the helper control has no subject")
        return False
    hv, hp, hc, hfm = hr[0]
    calls = []
    for ms in idx.ft_of.values():
        for m in ms:
            for mt in re.finditer(r"\b%s\s*\(" % re.escape(hfm.name), m.src.code[m.body_start:m.end]):
                calls.append((m.src.name, m.src.line(m.body_start + mt.start())))
    hcalls = sorted(set(calls))
    fh4, _ = a3_check(uni, sw, text, fields_out, spec=spec, noscope=set(hcalls[:1])) if hcalls else ([], None)
    h4_ok = bool(hcalls) and any("the call of helper %s at %s:%d" % (hfm.name, hcalls[0][0], hcalls[0][1]) in x
                                 for x in fh4)
    print("  (h4) helper %s's call at %s unscoped: %s" % (hfm.name, hcalls[:1], "FAILS as required" if h4_ok
                                                          else "did NOT fail (%s)" % fh4[:2]))
    ok &= h4_ok
    # (e) a dependent row with live writes declared zero by sweep proof
    flip = next(e for e in dep if e["writers"])
    spec_e = [(n, sid, "zero", "control", "sweep:no-live-write") if n == flip["name"] else (n, sid, k, w, pf)
              for (n, sid, k, w, pf) in spec]
    fe, _ = a3_check(uni, sw, text, fields_out, spec=spec_e)
    e_ok = any("is zero" in x and flip["name"] in x and "live writes" in x for x in fe)
    print("  (e) %s declared zero (sweep:no-live-write): %s" % (flip["name"], "FAILS as required (%s)" % next(
        x for x in fe if "is zero" in x)[:160] if e_ok else "did NOT fail on the unproven zero row"))
    ok &= e_ok
    # (e+) the proof can pass: a survivor read live whose writes are all outside the live members, as a zero row
    md = a3_rows_of_md(text)
    quiet = None
    for (comp, q), (c, fd_, writes, reads) in sorted(fields_out.items(), key=lambda kv: (kv[0][0], kv[1][1].src.name,
                                                                                         kv[1][1].pos)):
        if c == "survives_live" and not any(m is not None and m in sw.live and p < sw.cuts.get(m, m.end + 1)
                                            for (s, p, wk, m) in writes):
            quiet = (comp, q)
            break
    if quiet is None:
        print("  (e+) no survivor read live without live writes: the positive control has no subject")
        return False
    sid = next(k for k, (comp, quals) in md.items() if comp == quiet[0] and quiet[1] in quals)
    lines = []
    for ln in text.split("\n"):
        if re.match(r"\|\s*%s\s*\|" % sid, ln):
            cells = ln.split("|")
            cells[3] = " `%s` " % quiet[1]
            ln = "|".join(cells)
        lines.append(ln)
    spec_p = [(n, s_, "zero", "control", "sweep:no-live-write") if s_ == sid else (n, s_, k, w, pf)
              for (n, s_, k, w, pf) in spec]
    fpz, _ = a3_check(uni, sw, "\n".join(lines), fields_out, spec=spec_p)
    pz_ok = not any("is zero" in x for x in fpz)
    print("  (e+) %s %s alone as a zero row: %s" % (sid, quiet[1], "the proof PASSES (no live write)" if pz_ok else
                                                   "the proof did NOT pass (%s)" % [x for x in fpz if "is zero" in x][:1]))
    ok &= pz_ok
    # (f) one blanked-line count in the Method text changed by 1
    i = text.find(BLANK_LEAD)
    m = re.compile(r"([\w.#]+)\s+(\d+)").search(text, i + len(BLANK_LEAD))
    f_text = text[:m.start(2)] + str(int(m.group(2)) + 1) + text[m.end(2):]
    ff = check_blanked(uni, f_text)
    f_ok = bool(ff)
    print("  (f) blanked-line count of %s changed by 1: %s" % (m.group(1), "FAILS as required" if f_ok else
                                                                "did NOT fail on the stale count"))
    ok &= f_ok
    # (g) one writer pin changed by 1
    g_lines, done = [], False
    for ln in text.split("\n"):
        if not done and re.match(r"\|\s*S\d+\s*\|", ln):
            cells = ln.split("|")
            mm = re.search(r"\.cs:(\d+)", cells[6])
            if mm:
                cells[6] = cells[6][:mm.start(1)] + str(int(mm.group(1)) + 1) + cells[6][mm.end(1):]
                ln = "|".join(cells)
                done = True
        g_lines.append(ln)
    fg = check_sites(sw, fields_out, "\n".join(g_lines))
    g_ok = any("writers column" in x for x in fg)
    print("  (g) one writer pin changed by 1: %s" % ("FAILS as required" if g_ok else "did NOT fail on the stale pin"))
    ok &= g_ok
    return ok


def main(argv):
    uni = Universe()
    sw = Sweep(uni)
    try:
        with open(MD_PATH, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        text = ""
    if "--selftest" in argv:
        ok = selftest(uni, sw, text)
        print("SELFTEST PASS" if ok else "SELFTEST FAIL")
        return 0 if ok else 1
    if "--write-md" in argv:
        _f, stats, fields_out, rows_per = check_table(uni, sw, text, quiet=True)
        new = write_md(uni, sw, text, fields_out, stats, rows_per)
        with open(MD_PATH, "rb") as f:
            crlf = b"\r\n" in f.read()
        with open(MD_PATH, "w", encoding="utf-8", newline="") as f:
            f.write(new.replace("\n", "\r\n") if crlf else new)
        print("SURVIVORS.md regenerated (%s); run the sweep to check it" % ("changed" if new != text else "unchanged"))
        return 0
    fails, stats, fields_out, rows_per = check_table(uni, sw, text)
    afails, arep = a3_check(uni, sw, text, fields_out)
    fails += afails
    print_stats(uni, sw, stats, rows_per)
    print(a3_summary(arep))
    if "--detail" in argv:
        print_detail(sw, fields_out, {"survives_live"})
        print_a3_detail(arep)
    if "--detail-all" in argv:
        print_detail(sw, fields_out, {"survives", "survives_live", "reset", "reclassified", "construction"})
    if "--live" in argv:
        print("fallback resolutions:", uni.resolver.fallbacks)
        for x in sorted(set(uni.resolver.fallback_sites)):
            print("FALLBACK", x)
        for x in sw.cut_lines + sw.guard_lines:
            print("CUT/GUARD", x)
        for m in sorted(sw.live, key=lambda m: m.key):
            par = sw.live_parent.get(m)
            print("LIVE", m.key, "<-", par.key if par else "ROOT")
        for m in sorted(sw.boundary, key=lambda m: m.key):
            print("BOUNDARY", m.key)
    if fails:
        for x in fails:
            print("FAIL:", x)
        print("SURVIVOR SWEEP FAIL (%d)" % len(fails))
        return 1
    print("SURVIVOR SWEEP PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
