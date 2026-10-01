"""Client structure gates for the connect-failure build (evidence V11
sec8.2 K1-K50, sec8.3 WP1-WP12; the build brief's C1-C9; sec12 N11).

Every read goes through the structure module (_cs_structure): brace
structure from mask_code, needles from strip_comments_only, so a comment or a
string never satisfies a code assertion and a literal needle is found only
where the code has it. Each assertion's message is a tuple whose first element
is its control tag (cf_controls.py reads it). Each test first writes its
observable facts to CF_TRACE_DIR (when set), which a twin must leave
byte-equal, then asserts them in a fixed order.

Not here, BLOCKED on this lane (the upload hook AutoLogUpload.OnConnectFailure
does not exist): K9, K19 and the I4 half of K25 (brief C8).
"""

from __future__ import annotations

import ast
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _cs_structure as cs  # noqa: E402

ROOT = HERE.parents[1]
PLUGIN = ROOT / "plugin"
TOOLS = ROOT / "tools"
MAIN_PY = ROOT / "backend" / "api" / "main.py"

VIEW = r"IsKeptActor|KeptPlayers|IsQuarantined|IsQuarantinedActor|LocalSitsOut"
FENCE = r"MasterMaySend|MasterKept|MasterFenced|FenceMaster"


# ---------------------------------------------------------------- reading

_SRC = {}


def src(name):
    if name not in _SRC:
        _SRC[name] = (PLUGIN / name).read_text(encoding="utf-8")
    return _SRC[name]


def block(name, *sigs):
    """The block reached by narrowing through each signature in turn."""
    text = src(name)
    for s in sigs:
        text = cs.cs_block(text, s)
    return text


def kept(t):
    return cs.strip_comments_only(t)


def masked(t):
    return cs.mask_code(t)


def norm(s):
    return " ".join((s or "").split())


def calls(t, name):
    """Calls of `name` (a regex alternation allowed) in code, not comments or strings."""
    return len(re.findall(r"(?<![A-Za-z0-9_])(?:" + name + r")\s*\(", masked(t)))


def offsets(t, pattern):
    """Offsets of `pattern` in the comment-stripped text (literals kept)."""
    return [m.start() for m in re.finditer(pattern, kept(t))]


def first(t, pattern):
    o = offsets(t, pattern)
    return o[0] if o else -1


def _paren(m, raw, p):
    """(inner raw text, index of the closing paren) for the `(` at m[p]."""
    depth = 0
    for i in range(p, len(m)):
        if m[i] == "(":
            depth += 1
        elif m[i] == ")":
            depth -= 1
            if depth == 0:
                return raw[p + 1:i], i
    return None, -1


def _brace_end(m, ob):
    depth = 0
    for i in range(ob, len(m)):
        if m[i] == "{":
            depth += 1
        elif m[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


_KW = re.compile(r"\s*(else\b|if\s*\(|while\s*\(|for\s*\(|foreach\s*\(|using\s*\(|lock\s*\(|case\b|default\s*:)")


def _classify(m, raw, s, e):
    out = []
    i = s
    while i < e:
        mm = _KW.match(m, i, e)
        if not mm:
            if m[i:e].strip():
                out.append(("other", norm(raw[i:e])))
            break
        word = mm.group(1)
        if word.startswith("else"):
            out.append(("else", ""))
            i = mm.end()
            continue
        if word.startswith("case"):
            colon = m.find(":", mm.end(), e)
            if colon < 0:
                break
            out.append(("case", norm(raw[mm.end():colon])))
            i = colon + 1
            continue
        if word.startswith("default"):
            out.append(("case", "default"))
            i = mm.end()
            continue
        body, close = _paren(m, raw, mm.end() - 1)
        if close < 0 or close >= e:
            break
        out.append(("if" if word.startswith("if") else "loop", norm(body)))
        i = close + 1
    return out


def heads(t, at):
    """Every header enclosing offset `at` of t, outermost first, then the
    unbraced prefix of the statement at `at`: ('if', cond), ('else', ''),
    ('loop', header), ('case', label) or ('other', header)."""
    m = masked(t)
    raw = kept(t)
    stack = []
    for i in range(at):
        if m[i] == "{":
            stack.append(i)
        elif m[i] == "}" and stack:
            stack.pop()
    out = []
    for ob in stack:
        k = ob - 1
        while k >= 0 and m[k] not in ";{}":
            k -= 1
        out.extend(_classify(m, raw, k + 1, ob))
    k = at - 1
    while k >= 0 and m[k] not in ";{}":
        k -= 1
    out.extend(_classify(m, raw, k + 1, at))
    return out


def conds(t, at):
    return [c for kind, c in heads(t, at) if kind == "if"]


def if_blocks(t, pattern):
    """(start, end) of the body of every `if` whose condition matches `pattern`."""
    m = masked(t)
    raw = kept(t)
    out = []
    for mm in re.finditer(r"(?<![A-Za-z0-9_])if\s*\(", m):
        body, close = _paren(m, raw, mm.end() - 1)
        if close < 0 or not re.search(pattern, body):
            continue
        j = close + 1
        while j < len(m) and m[j].isspace():
            j += 1
        if j < len(m) and m[j] == "{":
            out.append((j, _brace_end(m, j)))
        else:
            out.append((j, m.find(";", j) + 1))
    return out


def own_level(t, at):
    """The text of the innermost block holding `at`, nested blocks blanked."""
    m = masked(t)
    stack = []
    for i in range(at):
        if m[i] == "{":
            stack.append(i)
        elif m[i] == "}" and stack:
            stack.pop()
    ob = stack[-1]
    cb = _brace_end(m, ob)
    res = []
    depth = 0
    for c in kept(t)[ob + 1:cb - 1]:
        if c == "{":
            depth += 1
            res.append(" ")
        elif c == "}":
            depth -= 1
            res.append(" ")
        else:
            res.append(c if depth == 0 else " ")
    return "".join(res)


def args_at(t, open_paren):
    """The top-level arguments of the call whose `(` is at open_paren."""
    m = masked(t)
    raw = kept(t)
    body, close = _paren(m, raw, open_paren)
    mb = m[open_paren + 1:close]
    parts, depth, start = [], 0, 0
    for i, c in enumerate(mb):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(body[start:i])
            start = i + 1
    parts.append(body[start:])
    return [norm(p) for p in parts if p.strip()]


def call_args(t, name):
    """[(offset, args)] for every call of `name` in t."""
    m = masked(t)
    out = []
    for mm in re.finditer(r"(?<![A-Za-z0-9_])" + name + r"\s*\(", m):
        out.append((mm.start(), args_at(t, mm.end() - 1)))
    return out


_DECL = re.compile(r"(?:\b(?:public|private|internal|protected|static|override|virtual|async|unsafe)\s+)+"
                   r"[\w<>\[\],.?\s]*?\b([A-Za-z_]\w*)\s*(?:<[^>]*>)?\s*\(")


def member_of(t, at):
    """The innermost declared method (a header with a modifier) holding `at`."""
    m = masked(t)
    stack = []
    for i in range(at):
        if m[i] == "{":
            stack.append(i)
        elif m[i] == "}" and stack:
            stack.pop()
    name = None
    for ob in stack:
        k = ob - 1
        while k >= 0 and m[k] not in ";{}":
            k -= 1
        mm = _DECL.search(norm(m[k + 1:ob]))
        if mm:
            name = mm.group(1)
    return name


def statement_at(t, at):
    """The statement holding `at`: from the previous ; { } to the next ;."""
    m = masked(t)
    s = at - 1
    while s >= 0 and m[s] not in ";{}":
        s -= 1
    e = m.find(";", at)
    return norm(kept(t)[s + 1:e + 1])


def and_terms(expr):
    try:
        return [norm(x) for x in cs.and_terms(expr)]
    except cs.CsParseError:
        return [norm(expr)]


def trace(facts):
    d = os.environ.get("CF_TRACE_DIR")
    if not d:
        return
    node = os.environ.get("PYTEST_CURRENT_TEST", "case").split(" ")[0].rsplit("/", 1)[-1]
    path = os.path.join(d, re.sub(r"[^A-Za-z0-9_.-]", "_", node) + ".json")
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write(json.dumps(facts, sort_keys=True, indent=1))


def run(cmd, timeout=900, cwd=None):
    p = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=cwd)
    out = p.stdout.decode("utf-8", "replace").replace("\r\n", "\n")
    err = p.stderr.decode("utf-8", "replace").replace("\r\n", "\n")
    return p.returncode, out, err


def dotnet():
    exe = shutil.which("dotnet")
    if exe:
        return exe
    home = Path(os.path.expanduser("~")) / ".dotnet" / "dotnet.exe"
    return str(home) if home.exists() else None


# ---------------------------------------------------------------- the server

_AST = {}


def main_ast():
    if "m" not in _AST:
        _AST["m"] = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    return _AST["m"]


def server_def(name):
    for node in main_ast().body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return node
    return None


def server_const(name):
    for node in main_ast().body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            v = node.value
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "frozenset":
                return frozenset(ast.literal_eval(v.args[0]))
            return ast.literal_eval(v)
    return None


def written_keys(node):
    """String keys a function writes: dict literal keys, x["k"] = ..., and
    x.update(k=...)."""
    keys = set()
    if node is None:
        return keys
    for n in ast.walk(node):
        if isinstance(n, ast.Dict):
            for k in n.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) \
                        and isinstance(t.slice.value, str):
                    keys.add(t.slice.value)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "update":
            for kw in n.keywords:
                if kw.arg:
                    keys.add(kw.arg)
    return keys


def _outcomes(v):
    """The string constants an expression can evaluate to: a conditional's
    two results, never its test (`"s" if s["verdict"] == "granted" else "l"`
    is {"s", "l"})."""
    if isinstance(v, ast.IfExp):
        return _outcomes(v.body) | _outcomes(v.orelse)
    return {c.value for c in ast.walk(v) if isinstance(c, ast.Constant) and isinstance(c.value, str)}


def dict_values_for(node, key):
    """Constant values stored under `key` in the function's dict literals."""
    vals = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value == key:
                    vals |= _outcomes(v)
    return vals


def model_fields(name):
    node = server_def(name)
    return {n.target.id for n in node.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}


def client_reads(files, key):
    """Count of ExtractJson*(<expr>, "key" and Window(<map>, "key" reads across
    the named files (the lock payload's windows go through Window)."""
    n = 0
    for f in files:
        n += len(re.findall(r"(?:ExtractJson\w*|Window)\(\s*\w+\s*,\s*\"" + re.escape(key) + r"\"",
                            kept(src(f))))
    return n


# ================================================================ K1

K1_ANCHORS = [
    ("lock_seen", "JoinTimeline.cs", ("static void Seen(",)),
    ("lock_rx", "JoinTimeline.cs", ("static void Arm(",)),
    ("countdown_fired", "ApiClient.cs", ("IEnumerator DelayedFfaRoomJoin(",)),
    ("countdown_aborted", "ApiClient.cs", ("IEnumerator DelayedFfaRoomJoin(",)),
    ("reform_fired", "ApiClient.cs", ("IEnumerator DelayedFfaRoomJoin(",)),
    ("reform_aborted", "ApiClient.cs", ("IEnumerator DelayedFfaRoomJoin(",)),
    ("poll_fail", "ApiClient.cs", ("void UpdateFfaQueuePoll(",)),
    ("poll_drop", "ApiClient.cs", ("void FfaPollDrop(",)),
    ("pending_set", "Plugin.cs", ("SetPendingRoom(string roomName, string region, string rulesProp, string rulesSrc)",)),
    ("leave_room", "Plugin.cs", ("class QueueRoomJoiner", "void Update(")),
    ("left_room", "Plugin.cs", ("class QueueRoomJoiner", "void Update(")),
    ("attempt_timeout", "Plugin.cs", ("class QueueRoomJoiner", "void Update(")),
    ("give_up", "Plugin.cs", ("class QueueRoomJoiner", "void Update(")),
    ("cstate", "Plugin.cs", ("void CstateTick(",)),
    ("nch_start", "Plugin.cs", ("void StartNCHConnect(",)),
    ("master_hold", "Plugin.cs", ("IEnumerator JoinWhenMasterReady(",)),
    ("master_ready", "Plugin.cs", ("IEnumerator JoinWhenMasterReady(",)),
    ("region_check", "Plugin.cs", ("bool RegionCheck(",)),
    ("join_issued", "Plugin.cs", ("void IssueJoinOrCreate(",)),
    ("join_result", "Plugin.cs", ("void IssueJoinOrCreate(",)),
    ("join_failed", "Plugin.cs", ("class Cr2v2DiagCallbacks", "void OnJoinRoomFailed(")),
    ("joined_room", "Plugin.cs", ("class Cr2v2DiagCallbacks", "void OnJoinedRoom(")),
    ("in_ranked_room", "Plugin.cs", ("void OnJoinedRankedRoom(",)),
    ("spawned", "Plugin.cs", ("IEnumerator Auto2v2SpawnCoroutine(",)),
    ("spawn_timeout", "Plugin.cs", ("IEnumerator Auto2v2SpawnCoroutine(",)),
    ("guard_timeout", "Plugin.cs", ("IEnumerator Force2v2StartGameWhenReady(",)),
    ("restart", "Plugin.cs", ("class NetworkConnectionHandler_NetworkRestart_Diag_Patch", "Prefix(")),
    ("region_rearm", "FfaAssembly.cs", ("void OnWrongRegion(",)),
    ("region_rearm", "FfaAssembly.cs", ("void AfterHandoffExit(",)),
    ("id_publish", "FfaAssembly.cs", ("void OnArrived(",)),
    ("arrive_answer", "FfaAssembly.cs", ("void ArriveAnswerLine(",)),
    ("spawn_hold", "FfaAssembly.cs", ("void SpawnHoldLine(",)),
    ("spawn_open", "FfaAssembly.cs", ("void SpawnOpenLine(",)),
    ("spawn_window_missed", "FfaAssembly.cs", ("void SpawnGate(",)),
    ("join_timeout", "FfaAssembly.cs", ("void JoinDeadlineTick(",)),
    ("guard_owed_shown", "FfaAssembly.cs", ("void OwedToastTick(",)),
    ("verdict", "FfaAssembly.cs", ("void HandleAnswer(",)),
    ("post_fail", "FfaAssembly.cs", ("void PostFail(",)),
    ("short_start", "FfaAssembly.cs", ("void ShortStart(",)),
    ("start_grant", "FfaAssembly.cs", ("void StartGrantLine(",)),
    ("load_hold", "FfaAssembly.cs", ("void HoldScene(",)),
    ("load_grant", "FfaAssembly.cs", ("void ReplayHeld(",)),
    ("release", "FfaAssembly.cs", ("void ReleaseLine(",)),
    ("release_handoff", "FfaAssembly.cs", ("bool ConsumeRelease(",)),
    ("notice", "FfaAssembly.cs", ("void OnNotice(",)),
    ("cfg_apply", "FfaAssembly.cs", ("bool ApplyLockConfig(",)),
    ("cfg_missing", "FfaAssembly.cs", ("bool ApplyLockConfig(",)),
    ("gate", "FfaAssembly.cs", ("void OnGateChanged(",)),
    ("start_hold", "FfaMode.cs", ("IEnumerator FfaDoStartGame(",)),
    ("game_start", "FfaMode.cs", ("public static void OnGameStart(",)),
    ("late_admitted", "FfaLateEntry.cs", ("void LateAdmittedLine(",)),
    ("late_load", "FfaLateEntry.cs", ("void OnBoundaryLoad(",)),
    ("late_seeded", "FfaLateEntry.cs", ("void CheckPendingSnapshot(",)),
    ("late_digest", "FfaLateEntry.cs", ("void CheckPendingSnapshot(",)),
    ("late_scale", "FfaLateEntry.cs", ("void CheckPendingSnapshot(",)),
    ("late_cards", "FfaLateEntry.cs", ("void OnSelfKept(",)),
    ("game_join", "FfaLateEntry.cs", ("void OnSelfKept(",)),
    ("late_spawn", "FfaLateEntry.cs", ("void LateSpawn(",)),
    ("late_wait", "FfaLateEntry.cs", ("IEnumerator MasterBoundary(",)),
    ("epoch_ready", "FfaLateEntry.cs", ("IEnumerator MasterBoundary(",)),
    ("epoch_raise", "FfaLateEntry.cs", ("IEnumerator MasterBoundary(",)),
    ("epoch_ack", "FfaLateEntry.cs", ("IEnumerator MasterBoundary(",)),
    ("epoch_unacked", "FfaLateEntry.cs", ("IEnumerator MasterBoundary(",)),
    ("callin_stamp", "FfaLateEntry.cs", ("IEnumerator MasterBoundary(",)),
    ("seed_pub", "FfaLateEntry.cs", ("void SendSnapshot(",)),
    ("epoch_rx", "FfaLateEntry.cs", ("void OnEpochAnswer(",)),
    ("epoch_bad", "FfaLateEntry.cs", ("void OnEpochAnswer(",)),
    ("epoch_ready_tx", "FfaLateEntry.cs", ("void ReadyTick(",)),
    ("kept", "FfaLateEntry.cs", ("void KeptLine(",)),
    ("epoch_refused", "FfaLateEntry.cs", ("void OnProposal(",)),
    ("epoch_ack_tx", "FfaLateEntry.cs", ("void OnProposal(",)),
    ("master_fence", "FfaLateEntry.cs", ("void FenceLine(",)),
    ("stamp_rx", "FfaLateEntry.cs", ("void PairStamp(",)),
    ("stamp_refused", "FfaLateEntry.cs", ("void Refused(FfaLateRules.Stamp s, string why)",)),
    ("stamp_late", "FfaLateEntry.cs", ("void ApplyPair(",)),
    ("stamp_superseded", "FfaLateEntry.cs", ("bool OnCallIn(",)),
    ("lag_out", "FfaLateEntry.cs", ("void LagLine(",)),
    ("lag_out_end", "FfaLateEntry.cs", ("void LagOutEnd(",)),
    ("master_ack", "FfaLateEntry.cs", ("void OnMasterEvent(",)),
    ("scale_refused", "FfaLateEntry.cs", ("void OnScale(",)),
    ("scale_refused", "FfaLateEntry.cs", ("int ConsumeLoadCount(",)),
    ("quarantine", "FfaLateEntry.cs", ("void QuarantineLine(",)),
    ("quarantine_refused", "FfaLateEntry.cs", ("void Refused(string site, int actor)",)),
    ("ledger_skip", "GameStateWatcher.cs", ("void NotifyPlayerLeftRoom(",)),
    ("seq_mismatch", "FfaCardSequence.cs", ("void CompareSeedProp(",)),
]

K1_WITHDRAWN = ("kept_ack", "kept_refused", "kept_lag")
_STEP = r"(?<![A-Za-z0-9_])(?:Step|Emit)\(\s*\"%s\""


def test_k01_every_step_once_in_its_anchor():
    """K1: each I1 token once in its anchor span (scale_refused and
    region_rearm once in each of two); lag_out in LagLine, which LagOutStart
    calls once; the withdrawn tokens appear nowhere; the banner reads v11;
    every Step call in plugin/ is one of the table's."""
    per = {}
    for tok, f, sigs in K1_ANCHORS:
        n = len(re.findall(_STEP % re.escape(tok), kept(block(f, *sigs))))
        per.setdefault(tok, []).append(n)
    lagstart = calls(block("FfaLateEntry.cs", "void LagOutStart("), "LagLine")
    withdrawn = []
    literal_steps = {}
    computed = 0
    for f in sorted(PLUGIN.glob("*.cs")):
        text = kept(f.read_text(encoding="utf-8"))
        for w in K1_WITHDRAWN:
            if re.search(r"\"" + w + r"\"", text):
                withdrawn.append(f.name + ":" + w)
        for mm in re.finditer(r"JoinTimeline\.Step\(\s*\"([a-z_0-9]+)\"", text):
            literal_steps[mm.group(1)] = literal_steps.get(mm.group(1), 0) + 1
        computed += len(re.findall(r"JoinTimeline\.Step\((?!\s*\")", text))
    banner = re.search(r"const string Banner = \"([^\"]*)\"", kept(src("JoinTimeline.cs")))
    table = {tok: len(v) for tok, v in per.items()}
    untracked = sorted(t for t in literal_steps if t not in table)
    outside = sorted(t for t, n in literal_steps.items() if t in table and n != table[t]
                     and t not in ("lock_seen", "lock_rx"))
    facts = {"per_anchor": per, "lagstart_calls_lagline": lagstart, "withdrawn": withdrawn,
             "banner": banner.group(1) if banner else None, "untracked": untracked,
             "outside_anchor": outside, "computed_steps": computed}
    trace(facts)
    bad = {t: v for t, v in per.items() if any(n != 1 for n in v)}
    assert not bad, ("K1 anchor count", bad)
    assert lagstart == 1, ("K1 lag_out via LagOutStart", lagstart)
    assert not withdrawn, ("K1 withdrawn tokens", withdrawn)
    assert banner and "armed v11" in banner.group(1), ("K1 banner", facts["banner"])
    assert not untracked and computed == 0, ("K1 untracked step", untracked, computed)
    assert not outside, ("K1 step outside its anchor", outside)


# ================================================================ K2, K26 (joiner)

def test_k02_eight_resets_read_realtime():
    """K2: Elapsed reads realtime under JoinGate; the timeout branch reads
    Elapsed; every in-method `stateTimer = 0f;` has the realtime stamp in the
    same block (eight); `stateTimer += Time.deltaTime` once."""
    qrj = block("Plugin.cs", "class QueueRoomJoiner")
    el = re.search(r"float\s+Elapsed\s*=>\s*([^;]*);", kept(qrj))
    elapsed = norm(el.group(1)) if el else None
    upd = cs.cs_block(qrj, "void Update(")
    at = first(upd, _STEP % "attempt_timeout")
    tconds = conds(upd, at) if at >= 0 else []
    m = masked(qrj)
    resets = []
    for mm in re.finditer(r"(?<![A-Za-z0-9_.])stateTimer\s*=\s*0f\s*;", m):
        if statement_at(qrj, mm.start()).startswith("private"):
            continue
        lvl = own_level(qrj, mm.start())
        resets.append(bool(re.search(r"stateStartedRt\s*=\s*Time\.realtimeSinceStartup\s*;", lvl)))
    delta = len(re.findall(r"stateTimer\s*\+=\s*Time\.deltaTime", kept(qrj)))
    facts = {"elapsed_gated": elapsed == "JoinGate ? Time.realtimeSinceStartup - stateStartedRt : stateTimer",
             "timeout_reads_elapsed": any(re.search(r"\bElapsed\s*>\s*30f", c) for c in tconds),
             "resets": len(resets), "resets_with_rt": sum(resets), "delta_once": delta}
    trace(facts)
    assert facts["elapsed_gated"], ("K2 elapsed", elapsed)
    assert facts["timeout_reads_elapsed"], ("K2 timeout reads Elapsed", tconds)
    assert len(resets) == 8, ("K2 eight resets", len(resets))
    assert all(resets), ("K2 reset rt", resets)
    assert delta == 1, ("K2 deltaTime once", delta)


def test_k03_k26_end_attempt_behind_join_gate():
    """K3: EndAttemptNow in OnJoinRoomFailed and in the returned-false branch,
    each behind JoinGate. K26: JoinGate is set only in SetPendingRoom from its
    `gated` argument and cleared with the pending room; EndAttemptNow starts
    with `if (!JoinGate) return;`."""
    jf = block("Plugin.cs", "class Cr2v2DiagCallbacks", "void OnJoinRoomFailed(")
    at_f = first(jf, r"EndAttemptNow\(")
    ij = block("Plugin.cs", "void IssueJoinOrCreate(")
    at_i = first(ij, r"EndAttemptNow\(\s*\"join_false\"\s*\)")
    ican = conds(ij, at_i) if at_i >= 0 else []
    ean = kept(block("Plugin.cs", "class QueueRoomJoiner", "void EndAttemptNow("))
    sets = []
    for f in sorted(PLUGIN.glob("*.cs")):
        t = f.read_text(encoding="utf-8")
        for mm in re.finditer(r"(?<![A-Za-z0-9_])JoinGate\s*=(?!=)\s*([^;]*);", masked(t)):
            val = norm(kept(t)[mm.start(1):mm.end(1)])
            sets.append((f.name, member_of(t, mm.start()), val,
                         any("gated" in c for c in conds(t, mm.start()))))
    facts = {
        "failed_calls": calls(jf, "EndAttemptNow"),
        "failed_gated": at_f >= 0 and any("QueueRoomJoiner.JoinGate" in c for c in conds(jf, at_f)),
        "false_calls": calls(ij, "EndAttemptNow"),
        "false_gated": any(re.fullmatch(r"JoinGate", c) for c in ican),
        "false_branch": any(k == "else" for k, _ in heads(ij, at_i)) if at_i >= 0 else False,
        "end_attempt_first": norm(masked(ean)[1:]).startswith("if (!JoinGate) return;"),
        "sets": sorted(sets),
    }
    trace(facts)
    assert facts["failed_calls"] == 1 and facts["failed_gated"], ("K3 join failed", facts)
    assert facts["false_calls"] == 1 and facts["false_gated"] and facts["false_branch"], ("K3 returned false", facts)
    assert facts["end_attempt_first"], ("K26 end attempt gate", ean[:120])
    want = [("Plugin.cs", "ClearPendingRoom", "false", False), ("Plugin.cs", "SetPendingRoom", "false", False),
            ("Plugin.cs", "SetPendingRoom", "true", True)]
    assert facts["sets"] == want, ("K26 join gate writers", facts["sets"])


def test_k04_region_check_position_and_guard():
    """K4: the region check sits after the cancellation check and before the
    JoinOrCreate log and call; its early return is behind JoinGate and the
    join_region_guard flag; its log line is behind neither."""
    ij = block("Plugin.cs", "void IssueJoinOrCreate(")
    order = [first(ij, r"if \(!string\.Equals\(Plugin\.PendingRankedRoom, capturedRoom"),
             first(ij, r"if \(!RegionCheck\(\)\) return;"),
             first(ij, r"Connected! JoinOrCreate"),
             first(ij, r"PhotonNetwork\.JoinOrCreateRoom\(")]
    rc = block("Plugin.cs", "bool RegionCheck(")
    end = cs.initialiser(rc, "{", "bool end") if False else None
    em = re.search(r"bool\s+end\s*=\s*([^;]*);", kept(rc))
    end = and_terms(em.group(1)) if em else []
    ret = first(rc, r"if \(!end\) return true;")
    call = first(rc, r"EndAttemptNow\(\s*\"region\"\s*\)")
    warn = first(rc, r"Plugin\.Log\.LogWarning\(")
    wconds = conds(rc, warn) if warn >= 0 else ["missing"]
    facts = {"ordered": all(x >= 0 for x in order) and order == sorted(order),
             "end_terms": sorted(end), "return_before_end": 0 <= ret < call,
             "log_conds": wconds}
    trace(facts)
    assert facts["ordered"], ("K4 position", order)
    assert "JoinGate" in end and "ApiClient.ServerJoinRegionGuard" in end, ("K4 end guard", end)
    assert facts["return_before_end"], ("K4 early return", ret, call)
    assert not any(re.search(r"JoinGate|ServerJoinRegionGuard|\bend\b", c) for c in wconds), \
        ("K4 log unguarded", wconds)


# ================================================================ K5, K50 (exit hook, release)

def test_k05_k50_exit_hook_consumes():
    """K5/K50: in the ffa_ exit hook FfaLeaveQueue sits behind both one-shot
    consumes (handoff and release), ClearPendingFfaSlot behind the handoff
    only, OnRoomLeft behind neither, AfterHandoffExit behind the handoff;
    ConsumeRelease clears ReleaseRoom before it compares the lobby."""
    prs = block("GameStateWatcher.cs", "void PollRoomState(")
    lo = first(prs, r"asmHandoff\s*=\s*FfaAssembly\.ConsumeHandoff\(photonRoomId\)")
    rel = first(prs, r"asmReleased\s*=\s*FfaAssembly\.ConsumeRelease\(photonRoomId\)")
    hi = first(prs, r"FfaAssembly\.AfterHandoffExit\(photonRoomId\)")
    seg = lambda pat: [o for o in offsets(prs, pat) if lo < o < hi]  # noqa: E731
    leave = seg(r"label:\s*\"room_exit\"")
    clear = seg(r"Plugin\.ClearPendingFfaSlot\(")
    left = seg(r"FfaMode\.OnRoomLeft\(")
    cl = lambda o: conds(prs, o)  # noqa: E731
    leave_terms = [and_terms(c) for c in cl(leave[0])] if len(leave) == 1 else []
    cr = kept(block("FfaAssembly.cs", "bool ConsumeRelease("))
    facts = {
        "consumes": lo >= 0 and rel >= 0 and lo < rel < hi,
        "leave_behind_both": any("!asmHandoff" in t and "!asmReleased" in t for t in leave_terms),
        "clear_one": len(clear) == 1,
        "clear_handoff_only": len(clear) == 1 and any("!asmHandoff" in and_terms(c) for c in cl(clear[0]))
        and not any("asmReleased" in c for c in cl(clear[0])),
        "left_free": len(left) == 1 and not any("asm" in c for c in cl(left[0])),
        "after_handoff": any(re.fullmatch(r"asmHandoff", c) for c in cl(hi)),
        "release_cleared_first": 0 <= cr.find("ReleaseRoom = null;") < cr.find("RoomOfLobby("),
    }
    trace(facts)
    assert facts["consumes"], ("K5 consumes", lo, rel, hi)
    assert len(leave) == 1 and facts["leave_behind_both"], ("K5 leave behind consumes", leave_terms)
    assert facts["clear_one"] and facts["clear_handoff_only"], ("K5 clear keeps release", facts)
    assert facts["left_free"], ("K5 room left", facts)
    assert facts["after_handoff"], ("K5 handoff consumer", cl(hi))
    assert facts["release_cleared_first"], ("K50 release consumed once", cr[:200])


def test_k50_exit_routes_release_and_leave():
    """K50: Exit holds one Release( (fence_expired, or join_timeout while the
    seat holds admitted_late, read locally) and one FfaLeaveQueue( for every
    other why; Release does the client clears, records the intent, sets
    ReleaseRoom and sends single-flight with the 4 s timeout; three tries
    then dropped, a 404 gone; the re-send comes only from the queue's
    recovery sites."""
    ex = block("FfaAssembly.cs", "internal static void Exit(")
    rm = re.search(r"bool\s+release\s*=\s*([^;]*);", kept(ex))
    rel_expr = norm(rm.group(1)) if rm else ""
    r_at = first(ex, r"(?<![A-Za-z0-9_.])Release\(\s*why\s*\)")
    l_at = first(ex, r"ApiClient\.FfaLeaveQueue\(")
    rl = kept(block("FfaAssembly.cs", "internal static void Release("))
    sr = block("FfaAssembly.cs", "void SendRelease(")
    srk = kept(sr)
    resend = []
    for f in sorted(PLUGIN.glob("*.cs")):
        t = f.read_text(encoding="utf-8")
        for mm in re.finditer(r"(?<![A-Za-z0-9_])ResendRelease\s*\(", masked(t)):
            if not statement_at(t, mm.start()).startswith("internal static"):
                resend.append((f.name, member_of(t, mm.start())))
    facts = {
        "release_expr": rel_expr == 'why == "fence_expired" || (why == "join_timeout" && '
                                   '!string.IsNullOrEmpty(FfaLateEntry.AdmittedLateLobby))',
        "release_calls": calls(ex, r"(?<!\.)Release"),
        "leave_calls": calls(ex, "FfaLeaveQueue"),
        "release_behind": r_at >= 0 and "release" in conds(ex, r_at),
        "leave_else": l_at >= 0 and any(k == "else" for k, _ in heads(ex, l_at)),
        "clears": "ApiClient.FfaClientClears();" in rl,
        "room_set": "ReleaseRoom = lobby;" in rl,
        "single_flight": norm(masked(sr)[1:]).startswith("if (_releaseInFlight"),
        "timeout": "timeout: PostTimeout" in srk,
        "cap3": bool(re.search(r"if \(tryNo >= 3\)", srk)) and "\"dropped\"" in srk,
        "gone404": bool(re.search(r"code == 404 \? \"gone\"", srk)),
        "resend_sites": sorted(set(resend)),
    }
    trace(facts)
    assert facts["release_expr"], ("K50 release routing", rel_expr)
    assert facts["release_calls"] == 1 and facts["release_behind"], ("K50 one release", facts)
    assert facts["leave_calls"] == 1 and facts["leave_else"], ("K50 one leave", facts)
    assert facts["clears"] and facts["room_set"], ("K50 release clears", facts)
    assert facts["single_flight"] and facts["timeout"], ("K50 single flight", facts)
    assert facts["cap3"] and facts["gone404"], ("K50 try cap", facts)
    assert facts["resend_sites"] == [("ApiClient.cs", "UpdateFfaQueuePoll")], ("K50 resend sites", resend)


# ================================================================ K6, K20 (barrier position)

def test_k06_k20_barrier_position():
    """K6/K20: in FfaDoStartGame, after the spectator return: the MovedOutOf
    check, the re-entry check, the hold, then GameStartedInRoom = true."""
    ds = block("FfaMode.cs", "IEnumerator FfaDoStartGame(")
    pos = [first(ds, r"if \(RoomActors\.LocalIsSpectator\) yield break;"),
           first(ds, r"if \(asmRoom == FfaAssembly\.MovedOutOf\) yield break;"),
           first(ds, r"if \(FfaAssembly\.StartHoldActive\) yield break;"),
           first(ds, r"FfaAssembly\.StartHoldActive = true;"),
           first(ds, r"(?<![A-Za-z0-9_.])GameStartedInRoom = true;")]
    facts = {"found": [p >= 0 for p in pos], "ordered": all(p >= 0 for p in pos) and pos == sorted(pos),
             "started_once": len(offsets(ds, r"(?<![A-Za-z0-9_.])GameStartedInRoom = true;"))}
    trace(facts)
    assert all(facts["found"][i] for i in (0, 1, 4)), ("K6 found", facts["found"])
    assert pos[1] < pos[4], ("K6 moved-out before started", pos)
    assert all(facts["found"][i] for i in (2, 3)), ("K20 found", facts["found"])
    assert facts["ordered"], ("K20 barrier order", pos)
    assert facts["started_once"] == 1, ("K20 started once", facts["started_once"])


# ================================================================ K7, K7b, K24 (toasts, lease)

def test_k07_guard_toast_behind_suppression():
    """K7: the guard toast is behind SuppressGuardToast (owed instead); the
    timeout warning is not."""
    fs = block("Plugin.cs", "IEnumerator Force2v2StartGameWhenReady(")
    warn = first(fs, r"Force-StartGame timed out")
    owe = re.search(r"bool\s+owe\s*=\s*([^;]*);", kept(fs))
    ob = if_blocks(fs, r"^\s*owe\s*$")
    obt = kept(fs)[ob[0][0]:ob[0][1]] if len(ob) == 1 else ""
    toast = offsets(fs, r"ShowGuardToast\(present, wanted\)")
    facts = {
        "warn_conds": [c for c in conds(fs, warn)] if warn >= 0 else ["missing"],
        "owe_from_flag": bool(owe) and norm(owe.group(1)) == "FfaAssembly.SuppressGuardToast",
        "owe_returns": "OweGuardToast(" in obt and "yield break" in obt,
        "toast_after": len(toast) == 1 and len(ob) == 1 and toast[0] > ob[0][1],
        "warn_before_owe": bool(owe) and 0 <= warn < owe.start(),
    }
    trace(facts)
    assert not any(re.search(r"Suppress|\bowe\b", c) for c in facts["warn_conds"]), \
        ("K7 warning unsuppressed", facts["warn_conds"])
    assert facts["warn_before_owe"], ("K7 warning first", warn)
    assert facts["owe_from_flag"] and facts["owe_returns"], ("K7 owed branch", facts)
    assert facts["toast_after"], ("K7 toast behind flag", toast)


def test_k07b_owed_toast_and_stall_warning():
    """K7b: the suppressed branch owes the toast; the lease-end tick shows it
    once, with the full-room deferral; the QUEUE-STALL if carries
    !SuppressStallWarn beside !rankedRoomStallWarned; admitted_late and
    game_join (and game_start) clear it."""
    owe = kept(block("FfaAssembly.cs", "void OweGuardToast("))
    tick = block("FfaAssembly.cs", "void OwedToastTick(")
    tk = kept(tick)
    prs = block("GameStateWatcher.cs", "void PollRoomState(")
    stall = [and_terms(kept(prs)[s:e]) for s, e in []]
    stall_conds = []
    m = masked(prs)
    for mm in re.finditer(r"(?<![A-Za-z0-9_])if\s*\(", m):
        body, close = _paren(m, kept(prs), mm.end() - 1)
        if body and "!rankedRoomStallWarned" in body:
            stall_conds.append(and_terms(body))
    ha = kept(block("FfaAssembly.cs", "void HandleAnswer("))

    def case_seg(label):
        s = ha.find("case \"%s\":" % label)
        return ha[s:ha.find("break;", s)] if s >= 0 else ""
    facts = {
        "owe_sets": "GuardToastOwed = true;" in owe,
        "tick_first": norm(masked(tick)[1:]).startswith("if (!GuardToastOwed || SuppressActive) return;"),
        "tick_shows": calls(tick, "ShowGuardToast"),
        "tick_full_room": "present >= n" in tk and "15f" in tk,
        "stall": [sorted(t) for t in stall_conds],
        "clear_admitted_late": "GuardToastOwed = false;" in case_seg("admitted_late"),
        "clear_start_ok": "GuardToastOwed = false;" in case_seg("start_ok"),
        "clear_game_join": calls(block("FfaLateEntry.cs", "void OnSelfKept("), "ClearOwedToast"),
        "clear_game_start": calls(block("FfaAssembly.cs", "internal static void AfterGameStart("), "ClearOwedToast"),
    }
    trace(facts)
    assert facts["owe_sets"], ("K7b owed", owe[:120])
    assert facts["tick_shows"] == 1 and facts["tick_first"], ("K7b re-show", facts)
    assert facts["tick_full_room"], ("K7b full-room deferral", tk[:200])
    assert len(stall_conds) == 1 and "!FfaAssembly.SuppressStallWarn" in stall_conds[0], \
        ("K7b stall condition", stall_conds)
    assert facts["clear_admitted_late"] and facts["clear_start_ok"], ("K7b clear on grant", facts)
    assert facts["clear_game_join"] == 1 and facts["clear_game_start"] == 1, ("K7b clear on join", facts)


def test_k24_suppression_lease():
    """K24: SuppressUntil is assigned only from a hold = 1 answer as receipt
    + 6 s; the suppression predicate reads only the lease, the start hold and
    the admitting or late-armed state."""
    t = src("FfaAssembly.cs")
    writes = []
    for mm in re.finditer(r"(?<![A-Za-z0-9_.])SuppressUntil\s*=(?!=)\s*([^;]*);", masked(t)):
        st = statement_at(t, mm.start())
        if st.startswith(("private", "internal", "public")):
            continue
        writes.append((norm(kept(t)[mm.start(1):mm.end(1)]), conds(t, mm.start())))
    lease = re.search(r"const float SuppressLeaseS = ([0-9.]+)f;", kept(t))
    sa = re.search(r"internal static bool SuppressActive\s*\{\s*get\s*\{\s*return\s*([^;]*);", kept(t))
    pred = re.sub(r"\"[^\"]*\"", "", sa.group(1)) if sa else ""
    idents = sorted(set(re.findall(r"[A-Za-z_][A-Za-z_0-9.]*", pred))) if sa else []
    facts = {"writes": len(writes),
             "rhs": [w[0] for w in writes],
             "hold_gated": all(any(re.search(r"a\.Hold == 1", c) for c in w[1]) for w in writes),
             "lease_s": lease.group(1) if lease else None, "predicate_idents": idents}
    trace(facts)
    assert facts["writes"] == 1 and facts["rhs"] == ["a.Rt + SuppressLeaseS"], ("K24 one writer", writes)
    assert facts["hold_gated"], ("K24 hold gated", writes)
    assert facts["lease_s"] == "6", ("K24 six seconds", facts["lease_s"])
    assert idents == ["FfaLateEntry.LateArmed", "StartHoldActive", "SuppressUntil", "Time.realtimeSinceStartup",
                      "_latestStatus"], ("K24 predicate", idents)


# ================================================================ K8, K33, K43 (spawn)

PIN_SPAWN_COND = "Plugin.Pending2v2Slot >= 0 || Plugin.PendingOvtSlot >= 0 || Plugin.PendingFfaSlot >= 0"


def test_k08_k33_spawn_sites():
    """K8: the direct spawn keeps exactly its pin condition, and OnArrived
    sits beside it behind the gated-room check. K33: an admission room starts
    GatedSpawn(Auto2v2SpawnCoroutine) instead."""
    jr = block("Plugin.cs", "void OnJoinedRankedRoom(")
    g = re.search(r"bool\s+gatedRoom\s*=\s*([^;]*);", kept(jr))
    direct = offsets(jr, r"StartCoroutine\(\s*Auto2v2SpawnCoroutine\(\)\s*\)")
    gated = offsets(jr, r"StartCoroutine\(\s*FfaAssembly\.GatedSpawn\(\s*Auto2v2SpawnCoroutine\s*\)\s*\)")
    arrived = offsets(jr, r"FfaAssembly\.OnArrived\(")
    dconds = conds(jr, direct[0]) if len(direct) == 1 else []
    facts = {
        "gated_flag": norm(g.group(1)) if g else None,
        "direct": len(direct), "gated": len(gated), "arrived": len(arrived),
        "direct_cond": dconds[:1],
        "direct_in_else": len(direct) == 1 and any(k == "else" for k, _ in heads(jr, direct[0])),
        "gated_cond": conds(jr, gated[0]) if len(gated) == 1 else [],
        "arrived_cond": conds(jr, arrived[0]) if len(arrived) == 1 else [],
    }
    trace(facts)
    assert facts["gated_flag"] == "FfaAssembly.IsGatedRoom(roomName)", ("K8 gated flag", facts["gated_flag"])
    assert facts["direct"] == 1 and facts["direct_cond"] == [PIN_SPAWN_COND] and facts["direct_in_else"], \
        ("K8 pin condition", facts)
    assert facts["arrived"] == 1 and "gatedRoom" in facts["arrived_cond"], ("K8 arrived", facts)
    assert facts["gated"] == 1 and "gatedRoom && FfaAssembly.IsAdmissionRoom(roomName)" in facts["gated_cond"], \
        ("K33 gated spawn", facts)


def test_k33_k43_spawn_gate_and_late_spawn():
    """K43: the state-A pass tests server_age_ms - spawn_ok_age_ms against
    spawn_open_s from that answer; the first state-A spawn_ok answer is the
    only one judged; no clock is read in the gate or GatedSpawn. K33: the only
    CreatePlayer in FfaLateEntry is LateSpawn's, called once, after MaySpawn."""
    sg = block("FfaAssembly.cs", "void SpawnGate(")
    sk = kept(sg)
    om = re.search(r"int\s+openMs\s*=\s*([^;]*);", sk)
    win = if_blocks(sg, r"openMs\s*<=\s*SpawnOpenS\s*\*\s*1000f")
    win_at = win[0][0] if len(win) == 1 else -1
    first_a = first(sg, r"_spawnFirstA = true;")
    stA = if_blocks(sg, r"a\.SpawnOk == 1 && !_spawnFirstA")
    wcond = [c for c in conds(sg, win_at)] if win_at >= 0 else []
    gs = block("FfaAssembly.cs", "internal static IEnumerator GatedSpawn(")
    le = src("FfaLateEntry.cs")
    creates = [member_of(le, mm.start()) for mm in re.finditer(r"(?<![A-Za-z0-9_])CreatePlayer\s*\(", masked(le))]
    ls_calls = [member_of(le, mm.start()) for mm in re.finditer(r"(?<![A-Za-z0-9_])LateSpawn\s*\(", masked(le))
                if not statement_at(le, mm.start()).startswith("private")]
    cps = kept(block("FfaLateEntry.cs", "void CheckPendingSnapshot("))
    facts = {
        "open_ms": norm(om.group(1)) if om else None,
        "window_test": len(win) == 1,
        "window_same_answer": any("a.SpawnOkAgeMs >= 0" in c and "a.ServerAgeMs >= 0" in c for c in wcond),
        "first_a_before_test": len(stA) == 1 and stA[0][0] < first_a < win_at,
        "state_a": bool(re.search(r"if \(a\.Status == \"assembling\" \|\| a\.Status == \"admitted\"\)", sk)),
        "clock_reads": len(re.findall(r"\bTime\.", masked(sg))) + len(re.findall(r"\bTime\.", masked(gs))),
        "creates": creates, "late_spawn_callers": ls_calls,
        "may_before_spawn": 0 <= cps.find("FfaLateRules.MaySpawn(") < cps.find("LateSpawn();"),
        "may_once": calls(block("FfaLateEntry.cs", "void CheckPendingSnapshot("), r"FfaLateRules\.MaySpawn") == 1,
        "opens": len(re.findall(r"_spawnOpenRoom = room;", sk)),
    }
    trace(facts)
    assert facts["open_ms"] == "a.ServerAgeMs - a.SpawnOkAgeMs", ("K43 open ms", facts["open_ms"])
    assert facts["window_test"] and facts["window_same_answer"], ("K43 window test", wcond)
    assert facts["first_a_before_test"], ("K43 judged once", first_a, stA, win_at)
    assert facts["state_a"], ("K43 state A", sk[:160])
    assert facts["clock_reads"] == 0, ("K43 no clock", facts["clock_reads"])
    assert facts["opens"] == 2, ("K33 gate opens", facts["opens"])
    assert creates == ["LateSpawn"], ("K33 one create", creates)
    assert ls_calls == ["CheckPendingSnapshot"] and facts["may_before_spawn"] and facts["may_once"], \
        ("K33 spawn behind MaySpawn", facts)


# ================================================================ K10, K13, N11, WP2 (labels)

I3_SITES = {
    "room_exit": ("GameStateWatcher.cs", "PollRoomState", 'FfaMode.GameStartedInRoom ? ApiClient.FfaInRoomExitCause() : ""'),
    "stall_bail": ("GameStateWatcher.cs", "PollRoomState", '"assembly_bail"'),
    "seat_abandon": ("GameStateWatcher.cs", "PollRoomState", '"seat_abandon"'),
    "fresh_cancel": ("FfaMode.cs", "LeaveBelowMinimum", '"fresh_cancel"'),
    "end_sitting": ("FfaMode.cs", "EndSittingBelowMinimum", "ApiClient.FfaInRoomExitCause()"),
    "rematch_abort": ("FfaMode.cs", "FfaDoStartGame", "ApiClient.FfaInRoomExitCause()"),
    "join_gave_up": ("Plugin.cs", "Update", None),
    "enroll_in_comp": ("ApiClient.cs", "FfaEnrollResult", None),
    "stale_lobby": ("ApiClient.cs", "UpdateFfaQueuePoll", None),
    "intent_retry": ("ApiClient.cs", "UpdateFfaQueuePoll", None),
    "held_in_comp": ("ApiClient.cs", "UpdateFfaQueuePoll", None),
    "leave_intent": ("ApiClient.cs", "UpdateFfaQueuePoll", None),
    "rejoin_refused": ("ApiClient.cs", "UpdateFfaQueuePoll", None),
    "lock_declined": ("ApiClient.cs", "UpdateFfaQueuePoll", None),
    "loop_breaker": ("ApiClient.cs", "ArmFfaLock", None),
    "menu_leave": ("NativeUI.cs", "BuildFfaTab", None),
    "asm_exit": ("FfaAssembly.cs", "Exit", None),
    "reform_abort": ("ApiClient.cs", "DelayedFfaRoomJoin", None),
    "wrong_region": ("FfaAssembly.cs", "Exit", None),
    "start_timeout": ("FfaAssembly.cs", "Exit", None),
    "join_timeout": ("FfaAssembly.cs", "Exit", None),
}


def leave_sites():
    """{label: (file, member, cause)} for every FfaLeaveQueue( call in plugin/,
    LabelFor's values expanded; and the calls with no label argument."""
    sites, unlabelled, dup = {}, [], []
    lf = kept(block("FfaAssembly.cs", "string LabelFor("))
    label_for = re.findall(r"return \"([a-z_]+)\";", lf)
    for f in sorted(PLUGIN.glob("*.cs")):
        t = f.read_text(encoding="utf-8")
        for at, args in call_args(t, "FfaLeaveQueue"):
            if statement_at(t, at).startswith("public static void"):
                continue
            named = {}
            cause = None
            for a in args:
                mm = re.match(r"^([A-Za-z_]\w*)\s*:(?!:)\s*(.*)$", a)
                if mm:
                    named[mm.group(1)] = mm.group(2)
                else:
                    cause = a
            if "cause" in named:
                cause = named["cause"]
            lab = named.get("label")
            if lab is None:
                unlabelled.append((f.name, member_of(t, at)))
                continue
            labs = re.findall(r"^\"([a-z_]+)\"$", lab) or (label_for if lab == "LabelFor(why)" else [lab])
            for x in labs:
                if x in sites:
                    dup.append(x)
                sites[x] = (f.name, member_of(t, at), cause)
    return sites, unlabelled, dup


def test_k10_n11_wp2_every_leave_labelled():
    """K10: every FfaLeaveQueue( call passes a label. N11 (binding): the 21
    I3 site-to-label values, each at its site with its unchanged cause, equal
    the server's _PREROOM_LEAVE_LABELS (WP2), each at most 14 characters."""
    sites, unlabelled, dup = leave_sites()
    server = server_const("_PREROOM_LEAVE_LABELS")
    wrong = sorted(lab for lab, want in I3_SITES.items() if sites.get(lab) != want)
    facts = {"labels": sorted(sites), "unlabelled": unlabelled, "dup": dup, "wrong_site": wrong,
             "server": sorted(server or []), "long": sorted(x for x in sites if len(x) > 14)}
    trace(facts)
    assert not unlabelled, ("K10 labelled", unlabelled)
    assert not dup, ("N11 one site per label", dup)
    assert sorted(sites) == sorted(I3_SITES), ("N11 label census", sorted(set(sites) ^ set(I3_SITES)))
    assert not wrong, ("N11 site table", {k: sites.get(k) for k in wrong})
    assert set(sites) == set(server or []), ("WP2 server labels", sorted(set(sites) ^ set(server or [])))
    assert not facts["long"], ("N11 label length", facts["long"])


def test_k13_label_reaches_only_its_parameter():
    """K13: in FfaLeaveQueue, `label` appears once, in the &label= expression,
    and never feeds the cause."""
    fq = block("ApiClient.cs", "public static void FfaLeaveQueue(")
    m = masked(fq)
    uses = [mm.start() for mm in re.finditer(r"(?<![A-Za-z0-9_])label(?![A-Za-z0-9_])", m)]
    st = [statement_at(fq, u) for u in uses]
    cause_st = [statement_at(fq, mm.start()) for mm in re.finditer(r"_ffaLeaveCause|&cause=", kept(fq))]
    facts = {"uses": len(uses), "in_label_param": bool(st) and "&label=" in st[0],
             "cause_clean": not any(re.search(r"(?<![A-Za-z0-9_&])label(?![A-Za-z0-9_=])", s) for s in cause_st)}
    trace(facts)
    assert facts["uses"] == 1 and facts["in_label_param"], ("K13 label once", st)
    assert facts["cause_clean"], ("K13 label not cause", cause_st)


# ================================================================ K11, K46, WP1 (caps, G3)

def test_k11_wp1_caps():
    """K11: ffa_asm1 needs all six conditions (the sixth: item 13's patches);
    ffa_adm1 needs the admission list and AdvertiseAdm, which is
    AdmProductionEnabled || G3Build; AdmProductionEnabled is false; G3Build is
    true only under SCR_G3. WP1: the tokens equal the server's."""
    fa = src("FfaAssembly.cs")
    caps = kept(block("FfaAssembly.cs", "internal static string Caps("))
    adm = re.search(r"bool\s+adm\s*=\s*([^;]*);", caps)
    asm = re.search(r"return\s+([^;]*);", kept(block("FfaAssembly.cs", "internal static bool AsmCapable(")))
    qa = re.search(r"return\s+([^;]*);", kept(block("FfaLateEntry.cs", "internal static bool QuarantineAttached(")))
    rel = re.search(r"const bool G3Build = (\w+);", cs.strip_comments_only(fa))
    g3 = re.search(r"const bool G3Build = (\w+);", cs.strip_comments_only(fa, frozenset({"SCR_G3"})))
    tok = dict(re.findall(r"(?:(?:internal|public|const|static)\s+)+string\s+(CapsToken|AdmCapsToken)\s*=\s*"
                          r"\"([^\"]*)\"\s*;", kept(fa)))
    facts = {
        "asm_source": bool(re.search(r"bool\s+asm\s*=\s*AsmCapable\(\);", caps)),
        "asm_terms": sorted(and_terms(asm.group(1))) if asm else [],
        "quarantine_terms": sorted(and_terms(qa.group(1))) if qa else [],
        "adm_terms": sorted(and_terms(adm.group(1))) if adm else [],
        "returns": re.findall(r"if \(([^)]*)\) return ([^;]*);", caps),
        "adm_production": bool(re.search(r"const bool AdmProductionEnabled = false;", kept(fa))),
        "advertise": bool(re.search(r"bool AdvertiseAdm => AdmProductionEnabled \|\| G3Build;", kept(fa))),
        "g3_release": rel.group(1) if rel else None, "g3_g3": g3.group(1) if g3 else None,
        "enroll_calls": calls(src("ApiClient.cs"), r"FfaAssembly\.Caps"),
        "tokens": tok,
    }
    trace(facts)
    assert facts["asm_terms"] == sorted(["Initialised", "DoStartPrefixAttached", "LoadGateAttached",
                                         "ExitHookHandoffCompiled", "BarrierCompiled",
                                         "FfaLateEntry.QuarantineAttached()"]), ("K11 asm six", facts["asm_terms"])
    assert facts["asm_source"], ("K11 asm source", caps[:200])
    assert facts["quarantine_terms"] == sorted(["PickPrefixAttached", "ForcePrefixAttached", "SyncPrefixAttached",
                                                "MapReportPrefixAttached", "VisiblePostfixAttached",
                                                "SimulatedPostfixAttached", "RegisterPostfixAttached", "damage"]), \
        ("K11 quarantine attached", facts["quarantine_terms"])
    assert facts["adm_terms"] == sorted(["asm", "AdmissionListComplete()", "CallInHoldAttached", "AdvertiseAdm"]), \
        ("K11 adm terms", facts["adm_terms"])
    assert facts["returns"] == [("asm && adm", 'CapsToken + "," + AdmCapsToken'), ("asm", "CapsToken")], \
        ("K11 advertise", facts["returns"])
    assert facts["adm_production"] and facts["advertise"], ("K11 production flag", facts)
    assert facts["g3_release"] == "false" and facts["g3_g3"] == "true", ("K11 g3 build", facts)
    assert facts["enroll_calls"] == 1, ("K11 enroll", facts["enroll_calls"])
    assert tok.get("CapsToken") == server_const("ASM_CAPS_TOKEN") and \
        tok.get("AdmCapsToken") == server_const("ADM_CAPS_TOKEN"), ("WP1 tokens", tok)


def _gate_fixture(path, marker, offset):
    rnd = random.Random(46)
    data = bytearray(rnd.getrandbits(8) for _ in range(4096))
    # printable bytes cannot spell a needle by chance: keep the noise high-bit
    for i in range(len(data)):
        data[i] |= 0x80
    enc = marker.encode("utf-16-le")
    data[offset:offset + len(enc)] = enc
    path.write_bytes(bytes(data))


def test_k46_g3_build_and_gate():
    """K46: the csproj declares G3, only it defines SCR_G3, CopyToPlugins
    excludes it; the marker branch returns the G3 literal under SCR_G3; the
    tracked gate refuses a G3 marker at an odd and at an even offset (exit 1),
    passes a STANDALONE DLL with both controls (exit 0), refuses as void with
    one control suppressed (exit 3), and a missing path (exit 2)."""
    proj = (PLUGIN / "CompetitiveRounds.csproj").read_text(encoding="utf-8")
    groups = re.findall(r"<PropertyGroup Condition=\"([^\"]*)\">(.*?)</PropertyGroup>", proj, re.S)
    defines = sorted(c for c, body in groups if "SCR_G3" in body)
    configs = re.search(r"<Configurations>([^<]*)</Configurations>", proj)
    copy = re.search(r"<Target Name=\"CopyToPlugins\"[^>]*Condition=\"([^\"]*)\"", proj)
    api = src("ApiClient.cs")
    marker = {sym: re.search(r"BuildVariantMarker\s*=\s*\"([^\"]*)\"", cs.strip_comments_only(api, sym))
              for sym in (frozenset(), frozenset({"SCR_G3"}), frozenset({"THUNDERSTORE"}))}
    marker = {",".join(sorted(k)) or "release": (v.group(1) if v else None) for k, v in marker.items()}
    gate = TOOLS / "g3-publish-gate.ps1"
    tmp = Path(tempfile.mkdtemp(prefix="cf_k46_"))
    results = {}
    try:
        _gate_fixture(tmp / "G3Odd.dll", "SCR_BUILD_VARIANT=G3", 1001)
        _gate_fixture(tmp / "G3Even.dll", "SCR_BUILD_VARIANT=G3", 1000)
        _gate_fixture(tmp / "Standalone.dll", "SCR_BUILD_VARIANT=STANDALONE", 2001)
        runs = {"i": ["-Dll", str(tmp / "G3Odd.dll")], "ii": ["-Dll", str(tmp / "G3Even.dll")],
                "iii": ["-Dll", str(tmp / "Standalone.dll")],
                "iv": ["-Dll", str(tmp / "Standalone.dll"), "-SuppressControl", "utf16le"],
                "missing": ["-Dll", str(tmp / "Absent.dll")]}
        for k, a in runs.items():
            rc, out, _ = run(["powershell.exe", "-NoProfile", "-File", str(gate)] + a, timeout=120)
            results[k] = [rc, out.strip().splitlines()[-1] if out.strip() else ""]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    facts = {"configs": configs.group(1) if configs else None, "defines": defines,
             "copy": copy.group(1) if copy else None, "marker": marker, "gate": results}
    trace(facts)
    assert facts["configs"] and "G3" in facts["configs"].split(";"), ("K46 configuration", facts["configs"])
    assert defines == ["'$(Configuration)' == 'G3'"], ("K46 SCR_G3 only in G3", defines)
    assert facts["copy"] and "'$(Configuration)' != 'G3'" in facts["copy"], ("K46 copy exclusion", facts["copy"])
    assert marker == {"release": "SCR_BUILD_VARIANT=STANDALONE", "SCR_G3": "SCR_BUILD_VARIANT=G3",
                      "THUNDERSTORE": "SCR_BUILD_VARIANT=THUNDERSTORE"}, ("K46 marker", marker)
    assert results["i"] == [1, "[G3-GATE] refused dll=G3Odd.dll why=marker"], ("K46 odd offset", results["i"])
    assert results["ii"] == [1, "[G3-GATE] refused dll=G3Even.dll why=marker"], ("K46 even offset", results["ii"])
    assert results["iii"] == [0, "[G3-GATE] pass dll=Standalone.dll controls=2"], ("K46 standalone", results["iii"])
    assert results["iv"] == [3, "[G3-GATE] refused dll=Standalone.dll why=void"], ("K46 void", results["iv"])
    assert results["missing"] == [2, "[G3-GATE] refused dll=Absent.dll why=missing"], ("K46 missing", results)


# ================================================================ K12, K14, K15, K16 (countdown, attempts, rearm)

PIN_ABORT = ("gen != ffaGen || _ffaLeaveIntent || string.IsNullOrEmpty(ActiveFfaLobbyId) || "
             "ActiveFfaLobbyId != lobbyId || foreignPending || inCompetitiveRoomNow")


def test_k12_countdown_abort_exemption():
    """K12: the competitive-room abort is skipped only for allowedRoom; every
    other clause of the pin's abort is unchanged; the reform passes MovedOutOf
    and the ungated call null; ArmFfaLock sets ActiveFfaLobbyId first."""
    dj = block("ApiClient.cs", "IEnumerator DelayedFfaRoomJoin(")
    asg = [mm for mm in re.finditer(r"(?<!bool )inCompetitiveRoomNow\s*=\s*([^;]*);", kept(dj))
           if "false" != norm(mm.group(1))]
    terms = and_terms(asg[0].group(1)) if len(asg) == 1 else []
    ab = [norm(b) for b in re.findall(r"if \((gen != ffaGen[^{]*?)\)\s*\{", kept(dj))]
    al = block("ApiClient.cs", "void ArmFfaLock(")
    dcall = call_args(al, "DelayedFfaRoomJoin")
    set_at = first(al, r"ActiveFfaLobbyId\s*=\s*ExtractJsonString\(resp,\s*\"lobby_id\"\)")
    facts = {"terms": terms, "abort": ab,
             "allowed_arg": dcall[0][1][6] if len(dcall) == 1 and len(dcall[0][1]) > 6 else None,
             "set_first": len(dcall) == 1 and 0 <= set_at < dcall[0][0]}
    trace(facts)
    assert terms == ["PhotonNetwork.InRoom", "!PhotonNetwork.OfflineMode", "CompetitiveRoomDetect.IsCompetitiveRoom()",
                     "(allowedRoom == null || PhotonNetwork.CurrentRoom?.Name != allowedRoom)"], \
        ("K12 exemption", terms)
    assert ab == [PIN_ABORT], ("K12 abort unchanged", ab)
    assert facts["allowed_arg"] == "reform ? FfaAssembly.MovedOutOf : null", ("K12 allowed room", facts)
    assert facts["set_first"], ("K12 lobby first", set_at, dcall)


def test_k14_attempt_posts():
    """K14: the attempt POST beside both joiner state entries, behind
    JoinGate, sending joinAttempts + 1."""
    qrj = block("Plugin.cs", "class QueueRoomJoiner")
    sites = []
    for at, args in call_args(qrj, r"FfaAssembly\.PostAttempt"):
        k = kept(qrj)
        prev = k.rfind(";", 0, at)
        prev2 = k.rfind(";", 0, prev)
        sites.append({"args": args, "state": norm(k[prev2 + 1:prev + 1]), "between": norm(k[prev + 1:at]),
                      "gated": "JoinGate" in conds(qrj, at)})
    facts = {"sites": sites}
    trace(facts)
    assert len(sites) == 2, ("K14 two posts", len(sites))
    assert [s["args"] for s in sites] == [["joinAttempts + 1", '"leave"'], ["joinAttempts + 1", '"connect"']], \
        ("K14 ordinal", [s["args"] for s in sites])
    assert [s["state"] for s in sites] == ["state = JoinState.LeavingRoom;", "state = JoinState.Connecting;"] and \
        all(s["between"] == "if (JoinGate)" and s["gated"] for s in sites), ("K14 beside the state entry", sites)


def test_k15_k16_region_rearm():
    """K15: the wrong_region handler leaves and never re-arms; the only
    re-arm SetPendingRoom is in the exit hook's handoff consumer; one re-arm
    per lobby. K16: HandoffRoom is set only at the reform fire and the region
    exit."""
    wr = block("FfaAssembly.cs", "void OnWrongRegion(")
    once = if_blocks(wr, r"^_rearmedLobby == lobby$")
    ot = kept(wr)[once[0][0]:once[0][1]] if len(once) == 1 else ""
    fa = src("FfaAssembly.cs")
    spr = [member_of(fa, mm.start()) for mm in re.finditer(r"(?<![A-Za-z0-9_])SetPendingRoom\s*\(", masked(fa))]
    hand = []
    for f in sorted(PLUGIN.glob("*.cs")):
        t = f.read_text(encoding="utf-8")
        for mm in re.finditer(r"(?<![A-Za-z0-9_])HandoffRoom\s*=(?!=)\s*([^;]*);", masked(t)):
            if statement_at(t, mm.start()).startswith(("internal", "private", "public")):
                continue
            hand.append((f.name, member_of(t, mm.start()), norm(kept(t)[mm.start(1):mm.end(1)])))
    facts = {"leaves": calls(wr, r"PhotonNetwork\.LeaveRoom"), "rearms_here": calls(wr, "SetPendingRoom"),
             "once_exits": 'Exit("wrong_region")' in ot and "return;" in ot,
             "marks_lobby": "_rearmedLobby = lobby;" in kept(wr), "set_pending": spr,
             "handoff": sorted(hand)}
    trace(facts)
    assert facts["leaves"] == 1 and facts["rearms_here"] == 0, ("K15 leave only", facts)
    assert facts["once_exits"] and facts["marks_lobby"], ("K15 once per lobby", ot)
    assert spr == ["AfterHandoffExit"], ("K15 re-arm site", spr)
    assert sorted(hand) == [("FfaAssembly.cs", "ConsumeHandoff", "null"),
                            ("FfaAssembly.cs", "OnReformFire", "MovedOutOf"),
                            ("FfaAssembly.cs", "OnWrongRegion", "room")], ("K16 handoff writers", hand)


# ================================================================ K17, K18, K25, K27, K35 (the poll)

def test_k17_k25_poll_fail_notice_drops():
    """K17: poll_fail is gated on IsFfaQueuePolling, not ActiveFfaLobbyId;
    poll_drop sits on the two discard returns. K25: the notice read sits
    after the !ok return and before both discards; OnNotice clears only under
    an id-equality guard."""
    up = block("ApiClient.cs", "void UpdateFfaQueuePoll(")
    pf = first(up, _STEP % "poll_fail")
    pfc = conds(up, pf) if pf >= 0 else []
    drops = [(at, args, conds(up, at)) for at, args in call_args(up, "FfaPollDrop")]
    notok = if_blocks(up, r"^!ok \|\| string\.IsNullOrEmpty\(resp\)$")
    note = first(up, r"FfaAssembly\.OnPollNotice\(resp\)")
    on = block("FfaAssembly.cs", "internal static void OnNotice(")
    clr = first(on, r"ApiClient\.FfaClientClears\(\)")
    facts = {
        "fail_gated": any("IsFfaQueuePolling" in and_terms(c) for c in pfc),
        "fail_not_lobby": not any("ActiveFfaLobbyId" in c for c in pfc),
        "drops": [(args, [c for c in cc if c in ("!IsFfaQueuePolling", "gen != ffaGen")]) for _, args, cc in drops],
        "notice_order": len(notok) == 1 and len(drops) == 2 and notok[0][1] <= note < min(d[0] for d in drops),
        "clear_guard": clr >= 0 and "lobby == ApiClient.ActiveFfaLobbyId || lobby == ApiClient.OpenFfaLobbyId"
        in conds(on, clr),
    }
    trace(facts)
    assert facts["fail_gated"] and facts["fail_not_lobby"], ("K17 poll_fail gate", pfc)
    assert facts["drops"] == [(['"polling"', "resp"], ["!IsFfaQueuePolling"]), (['"gen"', "resp"], ["gen != ffaGen"])], \
        ("K17 poll_drop sites", facts["drops"])
    assert facts["notice_order"], ("K25 notice position", notok, note, [d[0] for d in drops])
    assert facts["clear_guard"], ("K25 notice guard", conds(on, clr) if clr >= 0 else None)


def test_k18_k27_k35_ready_join():
    """K27: JoinTimeline.Seen( is the first statement of the ready_join
    block. K18: the reformed_from check and Move precede the competitive-room
    decline. K35: admissible: 1 skips the game_in_progress refusal and the
    unknown wait, not the decline."""
    up = block("ApiClient.cs", "void UpdateFfaQueuePoll(")
    rj = if_blocks(up, r"^status == \"ready_join\"$")
    s, e = rj[0] if len(rj) == 1 else (0, 0)
    body = up[s:e]
    k = kept(body)
    refm = first(body, r"reformedFrom == ActiveFfaLobbyId")
    move = first(body, r"FfaAssembly\.Move\(")
    dec = first(body, r"label:\s*\"lock_declined\"")
    ref = first(body, r"label:\s*\"rejoin_refused\"")
    unk = if_blocks(body, r"game_in_progress\\\":null")
    adm = re.search(r"bool\s+admissibleSeat\s*=\s*([^;]*);", k)
    facts = {
        "blocks": len(rj),
        "seen_first": norm(masked(body)[1:]).startswith("JoinTimeline.Seen("),
        "move_before_decline": 0 <= refm < move < dec,
        "admissible": norm(adm.group(1)) if adm else None,
        "refusal_bypass": ref >= 0 and any("!admissibleSeat" in and_terms(c) for c in conds(body, ref)),
        "unknown_bypass": len(unk) == 1 and any("!admissibleSeat" in and_terms(c)
                                                 for c in conds(body, unk[0][0] + 1)),
        "decline_kept": dec >= 0 and not any("admissible" in c for c in conds(body, dec)),
    }
    trace(facts)
    assert facts["blocks"] == 1 and facts["seen_first"], ("K27 pre-arm first", k[:160])
    assert facts["move_before_decline"], ("K18 move before decline", refm, move, dec)
    assert facts["admissible"] == 'ExtractJsonInt(resp, "admissible") == 1', ("K35 flag", facts["admissible"])
    assert facts["refusal_bypass"] and facts["unknown_bypass"], ("K35 bypass", facts)
    assert facts["decline_kept"], ("K35 decline kept", conds(body, dec) if dec >= 0 else None)


# ================================================================ K21, K22, K23, K41 (barrier)

def test_k21_k22_k41_barrier_run():
    """K21: the barrier passes only on this seat's grant (its own start_ok or
    an admitted_late), exits on reformed/dissolved/excluded/MovedOutOf and on
    the lease's expiry; no age estimate. K22: the start POST at the hold's
    first frame, then every 2 s while the latest answer is assembling with
    pending 0, else 5 s. K41: the lease is realtime, set at the hold, renewed
    only by a renewing answer; step 3 reads MasterKept() afresh and exits
    master_unkept after start_hold_s from the grant, which no answer re-sets."""
    br = block("FfaAssembly.cs", "class Barrier", "internal IEnumerator Run(")
    bk = kept(br)
    fa = src("FfaAssembly.cs")
    ha = kept(block("FfaAssembly.cs", "void HandleAnswer("))
    grant_cases = []
    for mm in re.finditer(r"_grantRoom = room;", ha):
        cs_at = [c for c in re.findall(r"case \"([a-z_]+)\":", ha[:mm.start()])]
        grant_cases.append(cs_at[-1] if cs_at else None)
    lease = []
    for mm in re.finditer(r"(?<![A-Za-z0-9_.])StartLeaseUntilRt\s*=(?!=)\s*([^;]*);", masked(fa)):
        if statement_at(fa, mm.start()).startswith(("internal", "private")):
            continue
        lease.append((member_of(fa, mm.start()), norm(kept(fa)[mm.start(1):mm.end(1)]),
                      [c for c in conds(fa, mm.start()) if "IsRenewing" in c or "fresh" in c]))
    ren = re.findall(r"status == \"([a-z_]+)\"", kept(block("FfaAssembly.cs", "bool IsRenewing(")))
    exp = if_blocks(br, r"^now >= StartLeaseUntilRt$")
    et = kept(br)[exp[0][0]:exp[0][1]] if len(exp) == 1 else ""
    mk = if_blocks(br, r"Time\.realtimeSinceStartup - _grantRt > StartHoldS")
    mt = kept(br)[mk[0][0]:mk[0][1]] if len(mk) == 1 else ""
    grt = [norm(statement_at(fa, mm.start())) for mm in re.finditer(r"(?<![A-Za-z0-9_.])_grantRt\s*=(?!=)",
                                                                   masked(fa))]
    lat = kept(block("FfaAssembly.cs", "bool LatestIsAssemblingPending0("))
    facts = {
        "no_age": not re.search(r"\bub\b|StartEarlyMs|start_early_s", bk),
        "no_hint": not re.search(r"PropAsmHint|cr_asm_hint|Hint", bk),
        "pass_once": len(re.findall(r"Passed = true;", bk)),
        "grant_cases": grant_cases,
        "exit_statuses": bool(re.search(r"_room == MovedOutOf \|\| st == \"reformed\" \|\| st == \"dissolved\" "
                                        r"\|\| st == \"excluded\"", bk)),
        "expiry": 'StartGrantLine("timeout", t0);' in et and 'Exit("start_timeout");' in et,
        "lease": sorted(lease), "renewing": sorted(ren), "no_game_time": not re.search(r"\bTime\.time\b",
                                                                                          masked(fa)),
        "cadence": bool(re.search(r"float period = LatestIsAssemblingPending0\(\) \? 2f : 5f;", bk))
        and bool(re.search(r"if \(!_startInFlight && now - _startSentRt >= period\)\s*SendStart\(\);", bk)),
        "first_frame": bool(re.search(r"float _startSentRt = -999f;", kept(fa))),
        "latest": "a.Status == \"assembling\" && a.Pending == 0" in lat and "_latest" in lat,
        "step3": bool(re.search(r"while \(!FfaLateEntry\.MasterKept\(\)\)", bk)),
        "unkept_exit": 'StartGrantLine("master_unkept", t0);' in mt and 'Exit("master_unkept");' in mt,
        "grant_rt": sorted(grt),
    }
    trace(facts)
    assert facts["no_age"] and facts["pass_once"] == 1, ("K21 pass", facts)
    assert facts["no_hint"], ("K21 no hint", "hint")
    assert grant_cases == ["start_ok", "admitted_late"], ("K21 grant only own start", grant_cases)
    assert facts["exit_statuses"] and facts["expiry"], ("K21 exits", facts)
    assert facts["lease"] == [("HandleAnswer", "a.Rt + StartHoldS", ["IsRenewing(a.Status)"]),
                              ("HoldScene", "Time.realtimeSinceStartup + StartHoldS", ["fresh && !StartHoldActive"]),
                              ("Run", "t0 + StartHoldS", [])], ("K41 lease writers", facts["lease"])
    assert facts["renewing"] == ["admitted_late", "admitting", "assembling", "start_ok"], ("K41 renewing", ren)
    assert facts["no_game_time"], ("K41 realtime", "Time.time")
    assert facts["cadence"] and facts["first_frame"] and facts["latest"], ("K22 cadence", facts)
    assert facts["step3"] and facts["unkept_exit"], ("K41 step 3", mt[:200])
    assert facts["grant_rt"] == ["_grantRt = 0f;", "if (_grantRt <= 0f) _grantRt = a.Rt;",
                                 "if (_grantRt <= 0f) _grantRt = a.Rt;"], ("K41 grant clock", grt)


def test_k23_timeouts_and_single_flight():
    """K23: every assembly, presence and connect POST passes timeout: 4; each
    loop's in-flight flag is cleared only in its callback; the defaults stay
    20."""
    fa = src("FfaAssembly.cs")
    posts = []
    for f in sorted(PLUGIN.glob("*.cs")):
        t = f.read_text(encoding="utf-8")
        for at, args in call_args(t, r"ApiClient\.AsmPost"):
            posts.append((f.name, member_of(t, at), "timeout: PostTimeout" in args))
    pt = re.search(r"const int PostTimeout = (\d+);", kept(fa))
    api = kept(src("ApiClient.cs"))
    defaults = re.findall(r"(?:public|private|internal) static \w+ (AsmPost|PostRequest)\([^)]*int timeout = (\d+)\)",
                          api)
    flags = {}
    for flag in ("_censusInFlight", "_startInFlight", "_releaseInFlight"):
        clears = []
        for mm in re.finditer(r"(?<![A-Za-z0-9_])" + flag + r"\s*=\s*false\s*;", masked(fa)):
            if statement_at(fa, mm.start()).startswith(("private", "internal")):
                continue
            clears.append(any(kind == "other" and "=>" in h for kind, h in heads(fa, mm.start())))
        flags[flag] = clears
    facts = {"posts": sorted(posts), "post_timeout": pt.group(1) if pt else None,
             "defaults": sorted(defaults), "flags": flags}
    trace(facts)
    assert posts and all(p[2] for p in posts), ("K23 timeout 4", posts)
    assert facts["post_timeout"] == "4", ("K23 four seconds", facts["post_timeout"])
    assert sorted(defaults) == [("AsmPost", "20"), ("PostRequest", "20")], ("K23 defaults", defaults)
    assert all(v and all(v) for v in flags.values()), ("K23 single flight", flags)


# ================================================================ K28, K48, K29, K30, K31, WP9 (census, arrival)

def test_k28_k48_wp9_census_body():
    """K48: the census lists PresentNonSpectators() and reads no fighter view.
    K28: each entry {a, s, b, k}: s from SteamIdOf (empty when absent), b from
    a body whose view's owner actor is that actor, k from the kept view; no
    entry dropped for an empty s. WP9: the keys equal the server model's."""
    cb = block("FfaAssembly.cs", "internal static string CensusBody(")
    k = kept(cb)
    keys = sorted(set(re.findall(r"\\\"([a-z_]+)\\\":", k)))
    facts = {
        "present": calls(cb, r"RoomActors\.PresentNonSpectators") == 1,
        "fighter_views": calls(cb, r"ActiveFighters|ActiveFighterCount|KeptPlayers") + len(
            re.findall(r"PhotonNetwork\.PlayerList", k)),
        "bodies": "PlayerManager.instance.players" in k and "data.view.OwnerActorNr" in k,
        "steam": bool(re.search(r"RoomActors\.SteamIdOf\(a\) \?\? \"\"", k)),
        "kept": calls(cb, r"FfaLateEntry\.IsKeptActor") == 1,
        "b_from_bodies": "int b = bodies.Contains(an) ? 1 : 0;" in k,
        "empty_dropped": bool(re.search(r"IsNullOrEmpty\(s\)\)\s*continue", k)),
        "keys": keys,
    }
    trace(facts)
    assert facts["present"] and facts["fighter_views"] == 0, ("K48 census list", facts)
    assert facts["bodies"] and facts["steam"] and facts["kept"] and facts["b_from_bodies"], ("K28 entry", facts)
    assert not facts["empty_dropped"], ("K28 empty s kept", k[:200])
    server = model_fields("_AsmAssemblyReq") | model_fields("_AsmCensusEntry")
    assert set(keys) == server, ("WP9 census keys", sorted(set(keys) ^ server))


def test_k29_k30_k31_arrival_master_ready_tick():
    """K29: the u_id check and republish precede the arrived POST, which
    carries actor, region and uid_missing. K30: master_ready sits after the
    readiness loop, in no if, before the conditional log and the join. K31:
    FfaAssembly.Tick() is the joiner Update's first statement."""
    oa = block("FfaAssembly.cs", "internal static void OnArrived(")
    order = [first(oa, r"ContainsKey\(\"u_id\"\)"), first(oa, r"SetCustomProperties\(StagedPrejoin\)"),
             first(oa, r"ConnectBody\(\"arrived\"")]
    ok_ = kept(oa)
    jw = block("Plugin.cs", "IEnumerator JoinWhenMasterReady(")
    wl = if_blocks(jw, r"^waitedFrames > 0$")
    loop = [mm for mm in re.finditer(r"while \(true\)", kept(jw))]
    loop_end = _brace_end(masked(jw), masked(jw).find("{", loop[0].end())) if len(loop) == 1 else -1
    mr = first(jw, _STEP % "master_ready")
    iss = first(jw, r"IssueJoinOrCreate\(capturedRoom\)")
    upd = block("Plugin.cs", "class QueueRoomJoiner", "void Update(")
    facts = {
        "arrival_order": all(o >= 0 for o in order) and order == sorted(order),
        "extra": all(("\\\"%s\\\"" % x) in ok_ for x in ("actor", "region", "uid_missing")),
        "master_ready": loop_end >= 0 and len(wl) == 1 and loop_end <= mr < wl[0][0] < iss,
        "master_ready_free": mr >= 0 and conds(jw, mr) == [],
        "tick_first": re.sub(r"\s+", "", masked(upd)[1:]).startswith("FfaAssembly.Tick();"),
    }
    trace(facts)
    assert facts["arrival_order"], ("K29 repair first", order)
    assert facts["extra"], ("K29 arrived fields", ok_[:200])
    assert facts["master_ready"] and facts["master_ready_free"], ("K30 unconditional", facts)
    assert facts["tick_first"], ("K31 tick first", norm(masked(upd)[:80]))


# ================================================================ K32 (join deadline)

def test_k32_join_deadline():
    """K32: set only on a gated lock (admission: receipt + admit_left + 10 s,
    re-derived from each answer; fallback: the join cap; a reform: 130 s);
    disarmed in an admission room only on start_ok, admitted_late or a final
    answer (and at the game start), in a fallback room on the first answer
    from inside it; no AdmitDeadlineRt."""
    lp = block("FfaAssembly.cs", "internal static bool OnLockPayload(")
    arms = [(args, conds(lp, at)) for at, args in call_args(lp, "ArmDeadline")]
    ha = block("FfaAssembly.cs", "void HandleAnswer(")
    dl = if_blocks(ha, r"^JoinDeadlineRt > 0f && _deadlineLobby == a\.Lobby$")
    d = ha[dl[0][0]:dl[0][1]] if len(dl) == 1 else ""
    sets = []
    for mm in re.finditer(r"JoinDeadlineRt\s*=\s*([^;]*);", kept(d)):
        sets.append((norm(mm.group(1)), conds(d, mm.start())))
    disarm = [c for v, cc in sets if v == "0f" for c in cc if "a.Status ==" in c]
    statuses = sorted(set(re.findall(r"a\.Status == \"([a-z_]+)\"", " ".join(disarm))))
    consts = dict(re.findall(r"const float (ReformCapS|JoinCapS) = ([0-9.]+)f;", kept(src("FfaAssembly.cs"))))
    facts = {
        "arms": [a[0][0] if a[0] else None for a in arms],
        "consts": consts,
        "rederive": any(v == "a.Rt + a.AdmitLeftMs / 1000f + 10f" and any("a.AdmitLeftMs >= 0" in c for c in cc)
                        for v, cc in sets),
        "disarm_statuses": statuses,
        "fallback": any(v == "0f" and any(c == 'postEntry && a.Status != "reformed"' for c in cc) for v, cc in sets),
        "game_start": bool(re.search(r"JoinDeadlineRt = 0f;",
                                     kept(block("FfaAssembly.cs", "internal static void AfterGameStart(")))),
        "no_admit_deadline": not any("AdmitDeadlineRt" in kept(f.read_text(encoding="utf-8"))
                                     for f in PLUGIN.glob("*.cs")),
        "disarm_members": sorted(member_of(t, mm.start()) for t in [f.read_text(encoding="utf-8")
                                                                      for f in sorted(PLUGIN.glob("*.cs"))]
                                 for mm in re.finditer(r"(?<![A-Za-z0-9_.])(?:FfaAssembly\.)?JoinDeadlineRt\s*=\s*0f\s*;",
                                                       masked(t))),
    }
    trace(facts)
    assert facts["arms"] == ["now + ReformCapS", "now + l.AdmitLeftMs / 1000f + 10f", "now + JoinCapS"], \
        ("K32 arm", facts["arms"])
    assert consts == {"ReformCapS": "130", "JoinCapS": "125"}, ("K32 caps", consts)
    assert facts["rederive"], ("K32 re-derivation", sets)
    assert statuses == ["admitted_late", "dissolved", "excluded", "start_ok"], ("K32 disarm statuses", statuses)
    assert facts["fallback"] and facts["game_start"], ("K32 fallback disarm", facts)
    assert facts["no_admit_deadline"], ("K32 no AdmitDeadlineRt", "present")
    assert facts["disarm_members"] == ["AfterGameStart", "Exit", "HandleAnswer", "HandleAnswer", "JoinDeadlineTick",
                                       "OnLockPayload", "OnQueueCleared"], ("K32 disarm sites", facts["disarm_members"])


# ================================================================ K34 (latch)

def test_k34_stall_latch():
    """K34: in a gated room the latch reads GameStartedInRoom and
    GameRunningFor( only; in an ungated room bodies >= fullAt; no grant flag."""
    prs = block("GameStateWatcher.cs", "void PollRoomState(")
    g = if_blocks(prs, r"^FfaAssembly\.SittingGated\(\)$")
    found = []
    for s, e in g:
        body = kept(prs)[s:e]
        if "rankedRoomEverFull = true" not in body:
            continue
        inner = re.findall(r"if \(([^{]*?)\)\s*rankedRoomEverFull = true;", body)
        tail = kept(prs)[e:e + 200]
        alt = re.match(r"\s*else if \(([^)]*)\)\s*rankedRoomEverFull = true;", tail)
        found.append(([norm(x) for x in inner], norm(alt.group(1)) if alt else None))
    facts = {"latch": found}
    trace(facts)
    assert len(found) == 1, ("K34 one latch", found)
    assert found[0][0] == ["FfaMode.GameStartedInRoom || FfaLateEntry.GameRunningFor(photonRoomId)"], \
        ("K34 gated latch", found)
    assert found[0][1] == "bodies >= fullAt", ("K34 ungated latch", found)


# ================================================================ K36, K37 (load gate, force start)

def test_k36_load_gate():
    """K36: a first-priority prefix on RPCA_LoadLevel returns LoadGate: true
    for the one-shot replay, a spectator, an ungated room; a grant's load is
    held until its own game starts, else the scene is held and false returned;
    the replay is a local call, never an RPC; no hint is read."""
    fa = src("FfaAssembly.cs")
    k = kept(fa)
    patch = re.search(r"\[HarmonyPatch\(typeof\(MapManager\), \"RPCA_LoadLevel\"\)\]\s*"
                      r"internal static class (\w+)", k)
    pre = kept(block("FfaAssembly.cs", "class " + patch.group(1), "static bool Prefix(")) if patch else ""
    lg = block("FfaAssembly.cs", "internal static bool LoadGate(")
    order = [first(lg, r"_replayBypass"), first(lg, r"RoomActors\.LocalIsSpectator"),
             first(lg, r"!SittingGated\(\)"), first(lg, r"MovedOutOf")]
    rh = kept(block("FfaAssembly.cs", "void ReplayHeld("))
    spans = [kept(block("FfaAssembly.cs", s)) for s in ("internal static bool LoadGate(", "void ReplayHeld(",
                                                         "void OnLoadGrant(", "internal static bool HoldsStartGrant(")]
    facts = {
        "patched": bool(patch),
        "priority": bool(re.search(r"\[HarmonyPriority\(Priority\.First\)\]\s*private static bool Prefix\(",
                                   kept(block("FfaAssembly.cs", "class " + patch.group(1))))) if patch else False,
        "prefix": "return FfaAssembly.LoadGate(sceneName);" in pre,
        "order": all(o >= 0 for o in order) and order == sorted(order),
        "replay_local": bool(re.search(r"_replayBypass = true;\s*(?:try\s*\{\s*)?MapManager\.instance\.RPCA_LoadLevel\(",
                                       rh)),
        "rpc": len(re.findall(r"\.RPC\(|RpcTarget", k)),
        "hint_reads": sum(len(re.findall(r"PropAsmHint|cr_asm_hint", s)) for s in spans),
        "age_reads": sum(len(re.findall(r"\w*AgeMs\w*|StartEarlyMs|\bub\b", s)) for s in spans),
        "held": bool(re.search(r"HoldScene\([^;]*\);\s*NoteTrigger\([^;]*\);\s*return false;", kept(lg))),
    }
    trace(facts)
    assert facts["patched"] and facts["priority"] and facts["prefix"], ("K36 prefix", facts)
    assert facts["order"], ("K36 pass order", order)
    assert facts["replay_local"] and facts["rpc"] == 0, ("K36 local replay", facts)
    assert facts["hint_reads"] == 0, ("K36 no hint", facts["hint_reads"])
    assert facts["age_reads"] == 0, ("K36 no age grant", facts["age_reads"])
    assert facts["held"], ("K36 held", kept(lg)[-300:])


def test_k37_force_start():
    """K37: gm.StartGame() once per room, behind start_n >= 3, the started
    and playing checks, and a count of bodies whose owner actor is a roster
    actor reaching start_n; re-evaluated from each start_ok (ShortStart)."""
    tf = block("FfaAssembly.cs", "void TryForceStart(")
    k = kept(tf)
    order = [first(tf, r"_forceStarted\.Contains\(room\) \|\| a\.StartN < 3\) return;"),
             first(tf, r"if \(bodies < a\.StartN\) return;"), first(tf, r"_forceStarted\.Add\(room\)"),
             first(tf, r"gm\.StartGame\(\)")]
    facts = {
        "order": all(o >= 0 for o in order) and order == sorted(order),
        "roster_count": "roster.Contains(p.data.view.OwnerActorNr)" in k,
        "started_checks": "GameStartedInRoom" in k and "isPlaying" in k,
        "start_calls": calls(tf, r"gm\.StartGame"),
        "from_short_start": calls(block("FfaAssembly.cs", "void ShortStart("), "TryForceStart"),
    }
    trace(facts)
    assert facts["order"] and facts["start_calls"] == 1, ("K37 once", order)
    assert facts["roster_count"], ("K37 roster bodies", k[:300])
    assert facts["started_checks"], ("K37 started", k[:300])
    assert facts["from_short_start"] == 1, ("K37 re-evaluated", facts)


# ================================================================ K38 (the boundary)

def test_k38_master_boundary():
    """K38: MasterBoundary is called immediately before each call-in while
    MasterMaySend() holds; after its single wait BarrierEpoch once; proposes
    above PointEpoch only while kind s; EVT_EPOCH to the others; waits for
    AckComplete within the ack window; the stamp just before the call-in; the
    ack only from a grant holder to the proposer; late requests of kind l,
    listed, roster-matched, answered only when the record lists them;
    late_closed after two waits; a statement's late entry is listed only
    with an actor (I2 writer 6)."""
    fm = src("FfaMode.cs")
    sites = []
    for mm in re.finditer(r"if \(FfaLateEntry\.MasterMaySend\(\)\) yield return FfaLateEntry\.MasterBoundary\(\);",
                          kept(fm)):
        nxt = norm(masked(fm)[mm.end():mm.end() + 400])
        sites.append(nxt.startswith("try { MapManager.instance.CallInNewMapAndMovePlayers(")
                     or nxt.startswith("MapManager.instance.CallInNewMapAndMovePlayers("))
    mb = block("FfaLateEntry.cs", "IEnumerator MasterBoundary(")
    k = kept(mb)
    wait = first(mb, r"while \(ReadyEpochNow\(grants, self\) < held")
    op = kept(block("FfaLateEntry.cs", "void OnProposal("))
    olr = kept(block("FfaLateEntry.cs", "internal static void OnLateRequest("))
    facts = {
        "call_sites": sites,
        "first": norm(masked(mb)[1:]).startswith("if (!AdmissionRoomNow() || !MasterMaySend()) yield break;"),
        "barrier_once": calls(mb, r"FfaLateRules\.BarrierEpoch") == 1 and wait < first(mb, r"FfaLateRules\.BarrierEpoch"),
        "propose": bool(re.search(r"FfaLateRules\.MayPropose\(nStar, PointEpoch, selfKindS\) && MasterMaySend\(\)", k)),
        "epoch_others": bool(re.search(r"Raise\(EVT_EPOCH, [^;]*Receivers = ReceiverGroup\.Others", k)),
        "ack_wait": "FfaLateRules.AckComplete(" in k and "FfaAssembly.EpochAckS" in k,
        "stamp_fence": 0 <= first(mb, r"if \(!MasterMaySend\(\)\) yield break;\s*"
                                      r"(?:var stamp = new FfaLateRules\.Stamp \{[^;]*;\s*)?Raise\(EVT_CALLIN"),
        "callin_once": len(re.findall(r"Raise\(EVT_CALLIN", k)),
        "ack_grant": norm(masked(block("FfaLateEntry.cs", "void OnProposal("))[1:]).startswith("if (!HoldsGrant) return;"),
        "ack_target": bool(re.search(r"Raise\(EVT_EPOCH_ACK, [^;]*TargetActors = new\[\] \{ e\.Sender \}", op)),
        "validate_once": len(re.findall(r"FfaLateRules\.ValidateEpoch\(", op)),
        "refusal_returns": bool(re.search(r"Step\(\"epoch_refused\"[^;]*;\s*return;", op)),
        "late_kind_l": "e.Kind == 'l'" in olr and "LateList" in olr and "steam_id != sid" in olr,
        "listed": "FfaLateRules.ListedIn(actor, Record" in k,
        "closed_after_two": bool(re.search(r"if \(waits >= 2\)\s*\{\s*SendSnapshot\(actor, kv\.Value, true\);", k)),
        "third_load_exit": 'FfaAssembly.Exit("join_timeout");' in kept(block("FfaLateEntry.cs", "void LateGiveUp(")),
        "late_actor": bool(re.search(r'int actor = ExtractJsonInt\(e, "actor", 0\);\s*if \(actor > 0\)\s*a\.Late\.Add\(',
                                     kept(block("FfaAssembly.cs", "internal static Answer ParseAnswer(")))),
    }
    trace(facts)
    assert sites == [True, True], ("K38 call sites", sites)
    assert facts["first"] and facts["barrier_once"], ("K38 barrier once", facts)
    assert facts["propose"] and facts["epoch_others"], ("K38 proposal", facts)
    assert facts["ack_wait"] and facts["stamp_fence"] and facts["callin_once"] == 1, ("K38 stamp", facts)
    assert facts["ack_grant"] and facts["ack_target"] and facts["validate_once"] == 1 \
        and facts["refusal_returns"], ("K38 ack", facts)
    assert facts["late_kind_l"] and facts["listed"] and facts["closed_after_two"], ("K38 late request", facts)
    assert facts["third_load_exit"], ("K38 third load exit", facts)
    assert facts["late_actor"], ("K38 late entry actor", facts["late_actor"])


# ================================================================ K39, K40 (report)

def test_k39_k40_reporter_rule_and_ghosts():
    """K39: the report skips a game equal to LagGame; the election skips
    cr_late and cr_lag seats; the self-fallback is barred by the local
    records (AdmittedLateLobby, LagGame), never the seat's own properties.
    K40: every locked slot neither present nor a Leaver is added absent;
    the relay records a leave only for an actor the quarantine does not name."""
    rb = block("GameStateWatcher.cs", "bool TryReportFfaMatch(")
    k = kept(rb)
    lag = first(rb, r"FfaLateEntry\.LagGame == reportGame")
    sits = first(rb, r"FfaLateEntry\.LocalSitsOut\(\)")
    elect = first(rb, r"FfaLateRules\.ElectReporter\(")
    li = kept(block("FfaLateEntry.cs", "internal static bool LateInSitting("))
    lg = kept(block("FfaLateEntry.cs", "internal static bool LaggedInGame("))
    nl = block("GameStateWatcher.cs", "void NotifyPlayerLeftRoom(")
    rec = first(nl, r"FfaMode\.RecordLeaver\(")
    facts = {
        "lag_skip": 0 <= lag < sits < elect and "report_skip why=lag_out" in k,
        "elect_args": bool(re.search(r"ElectReporter\(candActors, a => FfaLateEntry\.LaggedInGame\(a, reportGame\), "
                                     r"a => FfaLateEntry\.LateInSitting\(a\)\)", norm(k))),
        "self_barred": bool(re.search(r"selfBarred = FfaLateEntry\.LateInSitting\(ownActor\) \|\| "
                                      r"FfaLateEntry\.LaggedInGame\(ownActor, reportGame\);", k)),
        "fallback": "if (lowest == null && !selfBarred) lowest = localSteamId;" in norm(k),
        "own_late_local": "if (actor == OwnActor()) return !string.IsNullOrEmpty(AdmittedLateLobby);" in norm(li),
        "own_lag_local": "if (actor == OwnActor()) return LagGame == g && g > 0;" in norm(lg),
        "late_lobby": "return !string.IsNullOrEmpty(v) && v == Lobby8;" in norm(li),
        "lag_game": bool(re.search(r"FfaLateRules\.LagNames\([^;]*,\s*Lobby8,\s*g,\s*0\)", lg)),
        "ghosts": all(x in k for x in ("leftEarly = true", "absent = true", "gamePointsAtLeave = -1")),
        "ghost_source": "ApiClient.FfaLockedRoster" in k,
        "ghost_skip": "if (presentSteams.Contains(gm.steam_id) || FfaMode.Leavers.ContainsKey(gm.steam_id)) continue;"
        in norm(k),
        "relay": rec >= 0 and any(c in ("!FfaLateEntry.IsQuarantinedActor(p.ActorNumber)",
                                        "FfaLateEntry.IsKeptActor(p.ActorNumber)") for c in conds(nl, rec)),
    }
    trace(facts)
    assert facts["lag_skip"], ("K39 lag skip", lag, sits, elect)
    assert facts["elect_args"] and facts["self_barred"] and facts["fallback"], ("K39 election", facts)
    assert facts["own_late_local"] and facts["own_lag_local"], ("K39 local records", facts)
    assert facts["late_lobby"], ("K39 late lobby", li[-200:])
    assert facts["lag_game"], ("K39 lag lobby", lg[-200:])
    assert facts["ghosts"] and facts["ghost_source"] and facts["ghost_skip"], ("K40 ghosts", facts)
    assert facts["relay"], ("K40 relay", conds(nl, rec) if rec >= 0 else None)


# ================================================================ K42 (the kept view)

K42_SITES = [
    ("1 pickers", "FfaMode.cs", ("IEnumerator FfaPickPhase(",), VIEW, 1),
    ("1 ApplyManifestPick", "FfaMode.cs", ("IEnumerator ApplyManifestPick(",), VIEW, 1),
    ("1 CollectPicks", "FfaMode.cs", ("Dictionary<int, string> CollectPicks(",), VIEW, 1),
    ("1 CountStillPresent", "FfaMode.cs", ("int CountStillPresent(",), VIEW, 1),
    ("1 DetectAheadPickIdentity", "FfaMode.cs", ("Tuple<int, int> DetectAheadPickIdentity(",), VIEW, 1),
    ("2 RPCA_Pick prefix", "FfaLateEntry.cs", ("class FfaLate_PickQuarantine_Patch", " Prefix("), VIEW, 1),
    ("3 DoDamage refusal", "VanillaFixes.cs", ("class DamageRulesGate", " BeforeDoDamage("), VIEW, 1),
    ("3 force receiver", "FfaLateEntry.cs", ("class FfaLate_ForceQuarantine_Patch", " Prefix("), VIEW, 1),
    ("3 kill credit", "FfaMode.cs", ("void RecordKillFor(",), VIEW, 1),
    ("4 MovePlayers prefix", "FfaMapScale.cs", ("class PlayerManager_MovePlayers_FfaScale_Patch", " Prefix("), VIEW, 1),
    ("5 ApplyQuarantine", "FfaLateEntry.cs", ("void ApplyQuarantine(",), VIEW, 1),
    ("5 SetPlayersVisible", "FfaLateEntry.cs", ("class FfaLate_Visible_Patch", " Postfix("), "ApplyQuarantine", 1),
    ("5 SetPlayersSimulated", "FfaLateEntry.cs", ("class FfaLate_Simulated_Patch", " Postfix("), "ApplyQuarantine", 1),
    ("5 RegisterPlayer", "FfaLateEntry.cs", ("class FfaLate_Register_Patch", " Postfix("), "ApplyQuarantine", 1),
    ("6 AlivePlayers", "FfaMode.cs", ("List<Player> AlivePlayers(",), VIEW, 1),
    ("6 MasterPublishCount", "FfaMapScale.cs", ("void MasterPublishCount(",), VIEW, 1),
    ("6 ActiveFighters", "RoomActors.cs", ("PhotonPlayer[] ActiveFighters(",), VIEW, 1),
    ("6 OtherActiveFighterCount", "RoomActors.cs", ("int OtherActiveFighterCount(",), VIEW, 1),
    ("6 death count prefix", "FfaMode.cs", ("class PlayerManager_PlayerDied_Ffa_Patch", " Prefix("), VIEW, 1),
    ("7 NearestOpponent", "FfaMode.cs", ("Player NearestOpponent(",), VIEW, 1),
    ("8 report present entries", "GameStateWatcher.cs", ("bool TryReportFfaMatch(",), "ActiveFighters", 1),
    ("9 SuddenDeathSuppresses", "FfaMode.cs", ("bool SuddenDeathSuppresses(",), VIEW, 1),
    ("10 line-range prefix", "FfaMode.cs", ("class LineRangeEffect_FfaOwnerExclusion_Patch", " Prefix("), VIEW, 1),
    ("11 SafeRespawn", "VanillaFixes.cs", ("IEnumerator SafeRespawn(",), VIEW, 1),
    ("S BoundedSyncUp", "FfaMode.cs", ("IEnumerator BoundedSyncUp(",), VIEW, 1),
    ("S RPCO_RequestSyncUp prefix", "FfaLateEntry.cs", ("class FfaLate_NoSyncReply_Patch", " Prefix("), VIEW, 1),
    ("S ReportMapLoaded prefix", "FfaLateEntry.cs", ("class FfaLate_NoMapReport_Patch", " Prefix("), VIEW, 1),
    ("S CheckRoundAfterLeave cancel, resolve, last exit", "FfaMode.cs", ("IEnumerator CheckRoundAfterLeave(",), VIEW, 3),
    ("S HandlePlayerDied", "FfaMode.cs", ("void HandlePlayerDied(",), VIEW, 1),
    ("S RoomCount", "FfaMode.cs", ("int RoomCount(",), VIEW, 1),
    ("S rematch minimum and anchor", "FfaMode.cs", ("void HandleNextRound(",), VIEW, 2),
    ("S report builder", "GameStateWatcher.cs", ("bool TryReportFfaMatch(",), VIEW, 1),
]

K42_SENDERS = [
    ("FfaLateEntry.cs", ("IEnumerator MasterBoundary(",)),
    ("FfaLateEntry.cs", ("internal static void OnLateRequest(",)),
    ("FfaMapScale.cs", ("void MasterPublishCount(",)),
    ("FfaCardSequence.cs", ("void MasterPublishSeed(",)),
    ("FfaMode.cs", ("void MasterPublishConfig(",)),
    ("FfaMode.cs", ("IEnumerator FfaDoStartGame(",)),
    ("FfaMode.cs", ("IEnumerator FfaPickPhase(",)),
    ("FfaMode.cs", ("void HandleNextRound(",)),
    ("FfaMode.cs", ("void HandlePlayerDied(",)),
    ("SpectatorSync.cs", ("void HandleRequest(",)),
    ("SpectatorSync.cs", ("void MasterSweepUnvalidated(",)),
]

K42_RECEIVERS = [
    ("call-in observer", "FfaLateEntry.cs", ("internal static bool OnCallIn(",), ("MasterKept", "RefusedAuthority")),
    ("load gate", "FfaAssembly.cs", ("internal static bool LoadGate(",), ("MasterKept", "RefusedAuthority")),
    ("next-round prefix", "FfaMode.cs", ("class GMArmsRace_NextRound_Ffa_Patch", "Prefix("),
     ("MasterKept", "RefusedAuthority")),
    ("snapshot", "SpectatorSync.cs", ("void HandleSnapshot(",), ("MasterKept",)),
    ("scale", "FfaLateEntry.cs", ("void OnScale(",), ("Kept", r"FfaLateRules\.ScaleRecordDecision")),
    ("stamp", "FfaLateEntry.cs", ("string Validate(",), (r"FfaLateRules\.ValidateStamp", "Kept")),
]


def target_into_switch(ftk, var):
    """SetMasterClient's argument is FenceTarget's result, or a local whose
    initialiser reads it."""
    sm = re.search(r"SetMasterClient\(\s*(\w+)\s*\)", ftk)
    if not var or not sm:
        return False
    if sm.group(1) == var:
        return True
    init = re.search(r"var\s+" + re.escape(sm.group(1)) + r"\s*=\s*([^;]*);", ftk)
    return bool(init and re.search(r"\b" + re.escape(var) + r"\b", init.group(1)))


def test_k42_per_site_views_and_fence():
    """K42 per site: one view call in each listed span (#432; sub-sites
    counted where a span holds several), ActiveFighterCount's gated path, the
    fence reads of every master sender, the three map-authority prefixes, the
    FenceMaster sites, FenceTarget into SetMasterClient, and each receiver's
    refusal of a rejected master."""
    counts = {}
    for label, f, sigs, names, want in K42_SITES:
        counts[label] = [calls(block(f, *sigs), names), want]
    afc = block("RoomActors.cs", "int ActiveFighterCount(")
    gated = first(afc, r"if \(FfaLateEntry\.GatedRunning\) return ActiveFighters\(\)\.Length;")
    fast = first(afc, r"return room\.PlayerCount;")
    senders = {"%s:%s" % (f, sigs[-1]): calls(block(f, *sigs), "MasterMaySend") for f, sigs in K42_SENDERS}
    prefixes = {}
    for cls in ("Spectator_NoMapAuthority_Load_Patch", "Spectator_NoMapAuthority_CallIn_Patch",
                "Spectator_NoMapAuthority_CallInBare_Patch"):
        r = re.search(r"return\s+([^;]*);", kept(block("SpectatorPatches.cs", "class " + cls, "Prefix(")))
        prefixes[cls] = sorted(and_terms(r.group(1))) if r else []
    fence_sites = {
        "switch": calls(block("Plugin.cs", "class Cr2v2DiagCallbacks", "void OnMasterClientSwitched("), "FenceMaster"),
        "grant": calls(block("FfaLateEntry.cs", "void OnGrantedChanged("), "FenceMaster"),
        "answer": calls(block("FfaAssembly.cs", "void HandleAnswer("), "FenceMaster"),
        "gate": calls(block("FfaAssembly.cs", "void OnGateChanged("), "FenceMaster"),
        "keep": calls(block("FfaLateEntry.cs", "void AfterPair("), "FenceMaster"),
    }
    ft = block("FfaLateEntry.cs", "void FenceTick(")
    le = src("FfaLateEntry.cs")
    smc = [member_of(le, mm.start()) for mm in re.finditer(r"SetMasterClient\s*\(", masked(le))]
    tgt = re.search(r"var\s+(\w+)\s*=\s*FfaLateRules\.FenceTarget\(", kept(ft))
    receivers = {label: [calls(block(f, *sigs), n) for n in names] for label, f, sigs, names in K42_RECEIVERS}
    polarity = {}
    for label, f, sigs, names in K42_RECEIVERS:
        if "RefusedAuthority" not in names:
            continue
        b = block(f, *sigs)
        polarity[label] = [any(re.search(r"^!\s*(?:FfaLateEntry\.)?MasterKept\(\)$", c) for c in conds(b, o))
                           for o in offsets(b, r"(?<![A-Za-z0-9_])RefusedAuthority\s*\(")]
    ra = kept(block("FfaLateEntry.cs", "internal static void RefusedAuthority("))
    facts = {"counts": counts, "afc": 0 <= gated < fast, "senders": senders, "prefixes": prefixes,
             "fence_sites": fence_sites, "set_master": smc,
             "target_into_switch": target_into_switch(kept(ft), tgt.group(1) if tgt else None),
             "receivers": receivers, "polarity": polarity,
             "refused_authority": 'Refused("authority", MasterActor());' in ra}
    trace(facts)
    bad = {k: v for k, v in counts.items() if v[0] != v[1]}
    assert not bad, ("K42 per-site view", bad)
    assert facts["afc"], ("K42 fighter count fast path", gated, fast)
    assert all(v >= 1 for v in senders.values()), ("K42 sender fence", senders)
    assert all("!FfaLateEntry.MasterFenced()" in v for v in prefixes.values()), ("K42 map authority", prefixes)
    assert all(v >= 1 for v in fence_sites.values()), ("K42 fence sites", fence_sites)
    assert smc == ["FenceTick"] and facts["target_into_switch"], ("K42 fence target", smc)
    assert all(all(n >= 1 for n in v) for v in receivers.values()) and facts["refused_authority"] \
        and len(polarity) == 3 and all(v and all(v) for v in polarity.values()), ("K42 receivers", receivers, polarity)


CENSUS = TOOLS / "kept_view_census" / "kept_view_census.py"
CLASSES = TOOLS / "kept_view_census" / "classes.tsv"

_PROBE_HEAD = "using System.Collections.Generic;\nnamespace CompetitiveRounds\n{\n    internal static class ProbeK42\n    {\n"
_PROBE_TAIL = "    }\n}\n"
PROBES = {
    # the RED pair's function, unguarded, and its twin through the view
    "red": "        internal static int ProbeCount()\n        {\n            int n = 0;\n"
           "            foreach (var p in PlayerManager.instance.players) n++;\n            return n;\n        }\n",
    "red_twin": "        internal static int ProbeCount()\n        {\n            int n = 0;\n"
                "            foreach (var p in PlayerManager.instance.players)\n"
                "                if (FfaLateEntry.IsKeptActor(p.data.view.OwnerActorNr)) n++;\n"
                "            return n;\n        }\n",
    # fixture (b): a required-accessor row whose span reads an unrelated view
    "req": "        internal static int ProbeCount()\n        {\n            int n = 0;\n"
           "            foreach (var p in PlayerManager.instance.players)\n"
           "                if (FfaLateEntry.IsKeptActor(p.data.view.OwnerActorNr)) n++;\n"
           "            return n;\n        }\n",
    "req_twin": "        internal static int ProbeCount()\n        {\n            int n = 0;\n"
                "            if (FfaLateEntry.LocalSitsOut()) return 0;\n"
                "            foreach (var p in PlayerManager.instance.players) n++;\n"
                "            return n;\n        }\n",
    # the alias pair: a room alias counted in a V member and closed in an F member
    "alias": "        internal static int ProbeCount()\n        {\n            var room = Photon.Pun.PhotonNetwork.CurrentRoom;\n"
             "            return room.Players.Count;\n        }\n"
             "        internal static void ProbeClose(int actor)\n        {\n"
             "            var room = Photon.Pun.PhotonNetwork.CurrentRoom;\n"
             "            var pl = room.GetPlayer(actor);\n        }\n",
    "alias_twin": "        internal static int ProbeCount()\n        {\n            var room = Photon.Pun.PhotonNetwork.CurrentRoom;\n"
                  "            if (FfaLateEntry.LocalSitsOut()) return 0;\n"
                  "            return room.Players.Count;\n        }\n"
                  "        internal static void ProbeClose(int actor)\n        {\n"
                  "            if (!FfaLateEntry.MasterMaySend()) return;\n"
                  "            var room = Photon.Pun.PhotonNetwork.CurrentRoom;\n"
                  "            var pl = room.GetPlayer(actor);\n        }\n",
    # the multi-branch pair: the first branch guarded, the second not
    "branch": "        internal static int ProbeCount(bool x)\n        {\n            int n = 0;\n"
              "            if (x)\n            {\n                foreach (var p in PlayerManager.instance.players)\n"
              "                    if (FfaLateEntry.IsKeptActor(p.data.view.OwnerActorNr)) n++;\n            }\n"
              "            else\n            {\n                foreach (var p in PlayerManager.instance.players) n++;\n"
              "            }\n            return n;\n        }\n",
    "branch_twin": "        internal static int ProbeCount(bool x)\n        {\n            int n = 0;\n"
                   "            if (x)\n            {\n                foreach (var p in PlayerManager.instance.players)\n"
                   "                    if (FfaLateEntry.IsKeptActor(p.data.view.OwnerActorNr)) n++;\n            }\n"
                   "            else\n            {\n                foreach (var p in PlayerManager.instance.players)\n"
                   "                    if (FfaLateEntry.IsKeptActor(p.data.view.OwnerActorNr)) n++;\n"
                   "            }\n            return n;\n        }\n",
}
ROWS = {
    "red": [("ProbeCount", "players", "V", "")],
    "red_twin": [("ProbeCount", "players", "V", ""), ("ProbeCount", "IsKeptActor", "V", "")],
    "req": [("ProbeCount", "players", "V", "LocalSitsOut"), ("ProbeCount", "IsKeptActor", "V", "")],
    "req_twin": [("ProbeCount", "players", "V", "LocalSitsOut")],
    "alias": [("ProbeCount", "RoomPlayers", "V", ""), ("ProbeClose", "GetPlayer", "F", "")],
    "alias_twin": [("ProbeCount", "RoomPlayers", "V", ""), ("ProbeClose", "GetPlayer", "F", ""),
                   ("ProbeClose", "MasterMaySend", "F", "")],
    "branch": [("ProbeCount", "players", "V", ""), ("ProbeCount", "IsKeptActor", "V", "")],
    "branch_twin": [("ProbeCount", "players", "V", ""), ("ProbeCount", "IsKeptActor", "V", "")],
}


def _census(plugin_dir, classes, structure=False):
    cmd = [sys.executable, str(CENSUS), str(plugin_dir), str(classes)] + (["--structure"] if structure else [])
    rc, out, _ = run(cmd, timeout=1500)
    lines = out.strip().splitlines()
    kinds = sorted(set(re.findall(r"\b(UNCLASSIFIED|STALE|BADCLASS|NOVIEW|NOFENCE)\b", out)))
    summary = next((ln for ln in reversed(lines) if ln.startswith("kept-view census:")), "")
    n = re.search(r"(\d+) problem\(s\)", summary)
    return [rc, int(n.group(1)) if n else -1, kinds]


def _census_fixture(name, root, with_row, structure):
    d = Path(root) / name
    shutil.copytree(PLUGIN, d / "plugin", ignore=shutil.ignore_patterns("bin", "obj"))
    (d / "plugin" / "ProbeK42.cs").write_text(_PROBE_HEAD + PROBES[name] + _PROBE_TAIL, encoding="ascii",
                                              newline="\n")
    rows = CLASSES.read_text(encoding="utf-8")
    if with_row:
        for member, ident, cls, req in ROWS[name]:
            rows += "ProbeK42.cs\tProbeK42\t%s\t%s\t%s\tK42 census fixture probe\t\t%s\n" % (member, ident, cls, req)
    (d / "classes.tsv").write_text(rows, encoding="utf-8", newline="\n")
    return _census(d / "plugin", d / "classes.tsv", structure)


def test_k42_census_clean():
    """K42: the census over plugin/ exits 0 in full and with --structure."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        full = pool.submit(_census, PLUGIN, CLASSES, False)
        struct = pool.submit(_census, PLUGIN, CLASSES, True)
        facts = {"full": full.result(), "structure": struct.result()}
    trace(facts)
    assert facts["full"] == [0, 0, []], ("K42 census full", facts["full"])
    assert facts["structure"] == [0, 0, []], ("K42 census structure", facts["structure"])


def test_k42_census_red_pairs():
    """K42's census RED pairs on copies of plugin/: an unclassified consumer
    fails --structure (UNCLASSIFIED, 1); classed V without a view read, the
    full check (NOVIEW, 1); a required-accessor row served only by an
    unrelated view (NOVIEW, 1); the alias pair (NOVIEW and NOFENCE, 2); the
    multi-branch pair (NOVIEW, 1). Each twin, classified, exits 0 with no
    problem, --structure included."""
    root = tempfile.mkdtemp(prefix="cf_k42_")
    jobs = {"unclassified": ("red", False, True), "noview": ("red", True, False),
            "twin_structure": ("red_twin", True, True), "twin": ("red_twin", True, False),
            "req": ("req", True, False), "req_twin": ("req_twin", True, False),
            "alias": ("alias", True, False), "alias_twin": ("alias_twin", True, False),
            "branch": ("branch", True, False), "branch_twin": ("branch_twin", True, False)}
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            fut = {k: pool.submit(_census_fixture, v[0], os.path.join(root, k), v[1], v[2]) for k, v in jobs.items()}
            res = {k: f.result() for k, f in fut.items()}
    finally:
        shutil.rmtree(root, ignore_errors=True)
    trace(res)
    assert res["unclassified"] == [1, 1, ["UNCLASSIFIED"]], ("K42 census unclassified", res["unclassified"])
    assert res["noview"] == [1, 1, ["NOVIEW"]], ("K42 census noview", res["noview"])
    assert res["req"] == [1, 1, ["NOVIEW"]], ("K42 census required accessor", res["req"])
    assert res["alias"] == [1, 2, ["NOFENCE", "NOVIEW"]], ("K42 census alias", res["alias"])
    assert res["branch"] == [1, 1, ["NOVIEW"]], ("K42 census branch", res["branch"])
    twins = {k: v for k, v in res.items() if "twin" in k}
    assert all(v == [0, 0, []] for v in twins.values()), ("K42 census twins", twins)


# ================================================================ K42 (the view's key, the gate, fixtures c and f)

def test_k42_view_key_and_gate():
    """K42: the view keys a body by its current owner actor - OwnerOf reads
    data.view.OwnerActorNr, and both IsQuarantined overloads and KeptPlayers
    key through it - never by its Steam id or slot (a same-identity return
    would then play); GatedRunning reads only SittingStarted(), which reads
    only CurrentGate(), the current room's GateOf (V9, N2): no short-start
    flag and no grant (V5's short-start condition admitted an ungranted body
    in a full-granted or fallback room)."""
    oo = kept(block("FfaLateEntry.cs", "internal static int OwnerOf("))
    iq = norm(kept(block("FfaLateEntry.cs", "internal static bool IsQuarantined(Player p)")))
    iqs = norm(kept(block("FfaLateEntry.cs", "internal static bool IsQuarantined(params Player[] bodies)")))
    kp = norm(kept(block("FfaLateEntry.cs", "internal static List<Player> KeptPlayers(")))
    gr = block("FfaLateEntry.cs", "internal static bool GatedRunning")
    ss = norm(kept(block("FfaAssembly.cs", "internal static bool SittingStarted(")))
    cg = norm(kept(block("FfaAssembly.cs", "internal static FfaLateRules.Gate CurrentGate(")))
    facts = {
        "owner": "p.data.view.OwnerActorNr : -1" in norm(oo)
        and not re.search(r"playerID|SteamId|ActorOfSteam|[Ss]lot", oo),
        "keyed": ["int a = OwnerOf(p);" in t and bool(re.search(r"IsQuarantinedActor\(a\)|!IsKeptActor\(a\)", t))
                  for t in (iq, iqs, kp)],
        "gated_calls": re.findall(r"[A-Za-z_][\w.]*(?=\s*\()", masked(gr)),
        "gated_names": sorted(set(re.findall(r"Short\w*|Grant\w*|Latch\w*|Restart\w*", kept(gr)))),
        "started": ss == "{ return CurrentGate() == FfaLateRules.Gate.Started; }",
        "current": "string room = CurrentRoomName();" in cg and "_gateNow = GateOf(room);" in cg,
    }
    trace(facts)
    assert facts["owner"] and facts["keyed"] == [True, True, True], ("K42 view key", facts)
    assert facts["gated_calls"] == ["FfaAssembly.SittingStarted"] and not facts["gated_names"] \
        and facts["started"] and facts["current"], ("K42 gated running", facts)


def test_k42_fixture_c_late_join_reads():
    """K42 fixture (c), a late join after an unkept master published (V7-F4),
    as structure: in a gated room the load consumes its EVT_SCALE record and
    never reads the count property; EVT_SCALE is recorded only from the
    current master at the dispatch or the point's LatchMaster (V9, N3; V10,
    N7); a gated fighter derives the seed itself and only compares the
    property (seq_mismatch); a gated fighter applies its lock's config at the
    start, and only a spectator or an ungated seat latches it from the room
    (V9, N4)."""
    rp = block("FfaMapScale.cs", "private static int ReadPublishedCount(")
    osc = norm(kept(block("FfaLateEntry.cs", "private static void OnScale(")))
    srd = norm(kept(block("FfaLateRules.cs", "internal static string ScaleRecordDecision(")))
    lfg = block("FfaCardSequence.cs", "public static void LatchForGame(")
    gb = kept(block("FfaCardSequence.cs", "public static void LatchForGame(", "if (gatedFighter)"))
    ogs = norm(kept(block("FfaMode.cs", "public static void OnGameStart(")))
    slc = block("FfaMode.cs", "private static void SpectatorLatchConfigOnce(")
    gated_ret = first(rp, r"if \(gatedRoom\) return FfaLateEntry\.ConsumeLoadCount\(\);")
    prop = first(rp, r"CustomProperties")
    facts = {
        "count": "bool gatedRoom = FfaAssembly.SittingGated();" in norm(kept(rp)) and 0 <= gated_ret < prop,
        "scale_sender": "FfaLateRules.ScaleRecordDecision(l8, Lobby8, e.Sender, MasterActor(), latch, keptSender)"
        in osc and "_latchMaster.TryGetValue(Key(game, k), out latch)" in osc
        and 'if (from != dispatchMaster && from != latchMaster) return "sender";' in srd,
        "seed": "gatedFighter = FfaAssembly.SittingGated() && !RoomActors.LocalIsSpectator;" in norm(kept(lfg))
        and 'seed = DeriveSeed(room?.Name ?? "", game, myHash);' in norm(gb)
        and "CompareSeedProp(raw, game, seed, myHash);" in norm(gb)
        and not re.search(r"raw\.Split|Parse\(", gb),
        "config": 'if (!RoomActors.LocalIsSpectator && FfaAssembly.SittingGated()) FfaAssembly.ApplyLockConfig("start"); '
                  "else LatchConfigFromRoom();" in ogs
        and calls(src("FfaMode.cs"), "LatchConfigFromRoom") == 3 and calls(slc, "LatchConfigFromRoom") == 1,
    }
    trace(facts)
    assert facts["count"], ("K42 fixture c count", gated_ret, prop)
    assert facts["scale_sender"], ("K42 fixture c scale sender", facts)
    assert facts["seed"], ("K42 fixture c seed", facts)
    assert facts["config"], ("K42 fixture c config", facts)


def test_k42_fixture_f_held_config():
    """K42 fixture (f), the held config (V9, N4), as structure: the lock
    routine captures the lock's config in LockConfig (a reform's lock
    included, through Move's re-arm); ApplyLockConfig reads LockConfig,
    applies it only in its own room (cfg_missing otherwise) and sets the
    pending config from it, at exactly the arrival, the barrier and the
    start, so the pending slot, which the old room's exit resets, never
    carries the config across a room change."""
    olp = norm(kept(block("FfaAssembly.cs", "internal static bool OnLockPayload(")))
    ac = kept(block("FfaAssembly.cs", "internal static bool ApplyLockConfig("))
    sites = sorted(re.findall(r'ApplyLockConfig\("(\w+)"\)', kept(src("FfaAssembly.cs")) + kept(src("FfaMode.cs"))))
    facts = {
        "captured": bool(re.search(r'LockConfig = new LockCfg \{ Lobby = lobby, Room = room, '
                                   r'Target = ExtractJsonInt\(m, "score_target", 0\), '
                                   r'Candidates = ExtractJsonInt\(m, "card_candidates", 0\),', olp)),
        "held": "var c = LockConfig;" in norm(ac) and "c.Room != room" in norm(ac) and "cfg_missing" in ac,
        "applied": "FfaMode.SetPendingConfig(" in ac and "c.Target" in ac,
        "sites": sites,
    }
    trace(facts)
    assert facts["captured"] and facts["held"] and facts["applied"] \
        and sites == ["arrived", "barrier", "start"], ("K42 fixture f held config", facts)


# ================================================================ K44 (digest)

def test_k44_digest():
    """K44: the digest covers g, k, the level and each slot's rounds, points,
    point total and cards, and no kills; the late seat calls DigestGate once;
    only a kept grant holder publishes cr_bd, after each next round and each
    applied pick."""
    bd = kept(block("FfaLateRules.cs", "internal static string BoundaryDigest("))
    dt = kept(block("FfaLateEntry.cs", "void DigestTick("))
    fields = re.findall(r"\.Append\(s\.(\w+)", bd)
    facts = {
        "head": bool(re.search(r"sb\.Append\(g\.ToString\([^)]*\)\)\.Append\('\|'\)\s*\.Append\(k\.ToString\([^)]*\)\)"
                               r"\.Append\('\|'\)\s*\.Append\(levelId \?\? \"\"\)", bd)),
        "fields": fields, "cards": "string.Join(\",\", s.Cards" in bd, "kills": "Kills" in bd,
        "gate_once": calls(block("FfaLateEntry.cs", "void CheckPendingSnapshot("), r"FfaLateRules\.DigestGate"),
        "kept_only": "if (!(HoldsGrant && Kept(own))) return;" in norm(dt),
        "dirty_sites": [calls(src("FfaMode.cs"), r"FfaLateEntry\.MarkDigestDirty"),
                        len(re.findall(r"_bdDirty = true;", kept(src("FfaLateEntry.cs"))))],
    }
    trace(facts)
    assert facts["head"] and fields == ["Slot", "Rounds", "Points", "PointsTotal"] and facts["cards"], \
        ("K44 digest fields", fields)
    assert not facts["kills"], ("K44 no kills", "Kills")
    assert facts["gate_once"] == 1, ("K44 gate once", facts["gate_once"])
    assert facts["kept_only"], ("K44 kept publisher", dt[:200])
    assert facts["dirty_sites"][0] >= 1 and facts["dirty_sites"][1] >= 2, ("K44 publish points", facts["dirty_sites"])


# ================================================================ K45 (the late-rules harness, the model)

def test_k45_harness_and_boundary_model():
    """K45: the late-rules harness passes its baseline, every mutant turns its
    named fixture red and every twin stays inert; its N9 enumeration reads
    I7 = I8 = 0; the boundary model reports 0 failures."""
    exe = dotnet()
    if exe is None:
        pytest.skip("no dotnet on this seat")
    proj = TOOLS / "late-rules-harness" / "late-rules-harness.csproj"
    rc, out, err = run([exe, "run", "--project", str(proj), "-c", "Release"], timeout=1500)
    lines = [ln for ln in out.splitlines() if not ln.startswith("invocation")]
    result = next((ln for ln in lines if ln.startswith("RESULT")), "")
    n9 = next((ln for ln in lines if ln.startswith("K45.xii.e n9 runs=")), "")
    n7 = [ln for ln in lines if ln.startswith("K45.xi.n7 n7")]
    mism = [ln for ln in lines if "verdict=MISMATCH" in ln or "verdict=NOT-INERT" in ln]
    brc, bout, _ = run([sys.executable, str(TOOLS / "boundary_model" / "boundary_model.py")], timeout=600)
    bsum = [ln for ln in bout.splitlines() if ln.startswith("boundary model:")]
    bn9 = [ln for ln in bout.splitlines() if ln.startswith("ok   N9 V11 pairing")]
    facts = {"rc": rc, "result": result, "n9": n9, "n7": n7, "mismatch": mism, "model_rc": brc,
             "model": bsum, "model_n9": bn9}
    trace(facts)
    assert rc == 0 and "baseline=GREEN" in result and "verdict=PASS" in result, ("K45 harness", result, err[-400:])
    m = re.search(r"mutants=(\d+)/(\d+) twins=(\d+)/(\d+)", result)
    assert m and m.group(1) == m.group(2) and m.group(3) == m.group(4) and int(m.group(2)) > 0, \
        ("K45 harness controls", result)
    assert n9.endswith("I7=0 I8=0") and all(ln.endswith("I1=0 I2=0 I6=0") for ln in n7) and n7, \
        ("K45 enumeration", n9, n7)
    assert brc == 0 and bsum == ["boundary model: 0 failure(s)"] and len(bn9) == 1, ("K45 boundary model", bsum)


# ================================================================ K47 (the frozen roster)

def test_k47_gated_roster_freeze():
    """K47: each of the three roster freezes passes the lock roster's ids in
    a gated room and reads a fighter view only when ungated."""
    gw = src("GameStateWatcher.cs")
    freezes = []
    for mm in re.finditer(r"RoomActors\.FreezeFighterRoster\(", masked(gw)):
        args = args_at(gw, mm.end() - 1)
        freezes.append(args[0] if args else None)
    fighter_reads = []
    for mm in re.finditer(r"if \(lockIds == null\)\s*foreach \(var f in RoomActors\.ActiveFighters\(\)\)", kept(gw)):
        fighter_reads.append(member_of(gw, mm.start()))
    gf = kept(block("GameStateWatcher.cs", "List<string> GatedFreezeIds("))
    facts = {"freezes": freezes, "fighter_reads_ungated": len(fighter_reads),
             "gated_ids": "FfaAssembly.IsGatedRoom(" in gf and "ApiClient.FfaLockedRoster" in gf
             and "ActiveFighters" not in gf,
             "lock_ids": len(re.findall(r"var lockIds = GatedFreezeIds\(\);", kept(gw)))}
    trace(facts)
    assert freezes == ["lockIds ?? sids", "ids", "ids"], ("K47 three freezes", freezes)
    assert facts["fighter_reads_ungated"] == 2 and facts["lock_ids"] == 3, ("K47 ungated only", facts)
    assert facts["gated_ids"], ("K47 lock roster", gf[:200])


# ================================================================ K49 (the claim census)

CLAIMS = TOOLS / "claim_census" / "claim_census.py"


def _main_checkout():
    env = os.environ.get("CF_MAIN_CHECKOUT")
    if env and Path(env).is_dir():
        return Path(env)
    try:
        p = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    common = p.stdout.strip()
    return Path(common).parent if p.returncode == 0 and common else None


def _claims(*paths):
    rc, out, _ = run([sys.executable, str(CLAIMS)] + [str(p) for p in paths], timeout=300)
    hits = []
    for ln in out.splitlines():
        m = re.match(r"^(.*):(\d+): ([A-Z]+): ", ln)
        if m:
            hits.append((Path(m.group(1)).name, int(m.group(2)), m.group(3)))
    return rc, hits


def test_k49_claim_census():
    """K49: the claim census over the design and the build brief exits 0; a
    planted NOEXC or FIG sentence in a copy of the design exits 1 with 1 hit
    at the planted line; each twin sentence exits 0."""
    main = _main_checkout()
    bugs = main / "ai-collab" / "bugs" if main else None
    design = bugs / "CONNECT-FAILURE-DESIGN-V11.md" if bugs else None
    brief = bugs / "CONNECT-FAILURE-BUILD-BRIEF.md" if bugs else None
    if not (design and design.exists() and brief.exists()):
        pytest.skip("the design and brief are local-only files of the main checkout")
    plants = {"noexc": "The deadline holds with no exceptions.",
              "fig": "Rule B is decided by T0+55 in an admission lobby.",
              "noexc_twin": "`The deadline holds with no exceptions.`",
              "fig_twin": "Rule B is decided by T0+55 in an admission lobby on a completed eligible round trip."}
    tmp = Path(tempfile.mkdtemp(prefix="cf_k49_"))
    res = {}
    try:
        base_rc, base_hits = _claims(design, brief)
        text = design.read_text(encoding="utf-8")
        line_no = text.count("\n") + 2
        for k, sentence in plants.items():
            p = tmp / ("design_%s.md" % k)
            p.write_text(text + "\n" + sentence + "\n", encoding="utf-8", newline="\n")
            rc, hits = _claims(p)
            res[k] = [rc, [(h[1] == line_no, h[2]) for h in hits]]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    facts = {"base": [base_rc, len(base_hits)], "plants": res}
    trace(facts)
    assert base_rc == 0 and not base_hits, ("K49 design and brief clean", base_hits[:5])
    assert res["noexc"] == [1, [(True, "NOEXC")]], ("K49 plant noexc", res["noexc"])
    assert res["fig"] == [1, [(True, "FIG")]], ("K49 plant fig", res["fig"])
    assert res["noexc_twin"] == [0, []] and res["fig_twin"] == [0, []], ("K49 twins", res)


# ================================================================ WP3, WP4, WP8 (payload and answer keys)

WP3_KEYS = ("assembly", "admission", "admissible", "admit_left_ms", "reformed_from", "spawn_open_s",
            "asm_started", "epoch_ack_s", "stamp_wait_s", "fence_s")
WP4_KEYS = ("server_age_ms", "start_hold_s", "late_wait_s", "spawn_ok", "hold", "pending", "wait_ms", "start_n",
            "roster", "late", "game", "admit_left_ms", "spawn_ok_age_ms", "granted", "epoch", "assembly",
            "asm_started")
WP4_ENTRY = ("slot", "actor", "kind", "n", "chain", "kept")


def test_wp3_payload_keys():
    """WP3: each payload key the client reads is one the lock payload writes."""
    server = written_keys(server_def("_asm_payload_fields")) | written_keys(server_def("_ffa_poll_locked_payload"))
    files = ("FfaAssembly.cs", "ApiClient.cs")
    facts = {k: [k in server, client_reads(files, k)] for k in WP3_KEYS}
    trace(facts)
    assert all(v[0] for v in facts.values()), ("WP3 server writes", [k for k, v in facts.items() if not v[0]])
    assert all(v[1] >= 1 for v in facts.values()), ("WP3 client reads", [k for k, v in facts.items() if not v[1]])


def test_wp4_wp8_answer_keys():
    """WP4: each answer key (and the granted, roster and epoch entry keys and
    the kind values) the client reads is one the answer builders write. WP8:
    the deadline answer's error value is the literal the client maps to
    post_fail err=deadline."""
    fns = ("_asm_answer_plan", "_asm_answer_build", "_asm_answer_lists", "_asm_epoch", "_asm_payload_fields")
    server = set()
    for f in fns:
        server |= written_keys(server_def(f))
    files = ("FfaAssembly.cs", "FfaLateEntry.cs")
    facts = {k: [k in server, client_reads(files, k)] for k in WP4_KEYS + WP4_ENTRY}
    kinds_server = dict_values_for(server_def("_asm_answer_lists"), "kind")
    pa = kept(block("FfaAssembly.cs", "internal static Answer ParseAnswer("))
    kinds_client = sorted(set(re.findall(r"kind == \"([a-z])\"", pa)))
    dl = dict_values_for(server_def("_asm_deadline_answer"), "error")
    pf = kept(block("FfaAssembly.cs", "void PostFail("))
    facts.update({"kinds": [sorted(kinds_server), kinds_client], "deadline": sorted(dl),
                  "client_deadline": bool(re.search(r"\"asm_deadline\"[^;]*\"deadline\"", pf))})
    trace(facts)
    missing_s = [k for k in WP4_KEYS + WP4_ENTRY if not facts[k][0]]
    missing_c = [k for k in WP4_KEYS + WP4_ENTRY if not facts[k][1]]
    assert not missing_s, ("WP4 server writes", missing_s)
    assert not missing_c, ("WP4 client reads", missing_c)
    assert facts["kinds"] == [["l", "s"], ["l", "s"]], ("WP4 kind values", facts["kinds"])
    assert facts["deadline"] == ["asm_deadline"] and facts["client_deadline"], ("WP8 deadline", facts)


# ================================================================ WP5, WP6 (properties, the late tail)

def test_wp5_room_and_player_properties():
    """WP5: every writer and reader of cr_asm_hint, cr_late, cr_bd and cr_lag
    names one constant; no other literal remains; no cr_gv; the formats:
    cr_late {lobby8}, cr_bd {g}:{k}:{hash}, cr_lag {lobby8}:{g}:{k}."""
    consts = {}
    literals = {}
    uses = {}
    for f in sorted(PLUGIN.glob("*.cs")):
        t = kept(f.read_text(encoding="utf-8"))
        for name, val in re.findall(r"(?:(?:internal|public|const|static)\s+)+string\s+(Prop\w+)\s*=\s*"
                                    r"\"(cr_[a-z_]+)\"\s*;", t):
            consts[name] = val
        for lit in ("cr_asm_hint", "cr_late", "cr_bd", "cr_lag", "cr_gv"):
            n = len(re.findall(r"\"" + lit + r"\"", t))
            if n:
                literals[f.name + ":" + lit] = n
        for name in ("PropAsmHint", "PropLate", "PropBd", "PropLag"):
            n = len(re.findall(r"(?<![A-Za-z0-9_])" + name + r"(?![A-Za-z0-9_])(?!\s*=\s*\")", t))
            if n:
                uses[f.name + ":" + name] = n
    # The four WP5 constants and any other constant naming their literals; a
    # pre-existing Prop constant of another property is not WP5's.
    consts = {k: v for k, v in consts.items()
              if k in ("PropAsmHint", "PropLate", "PropBd", "PropLag")
              or v in ("cr_asm_hint", "cr_late", "cr_bd", "cr_lag", "cr_gv")}
    le = kept(src("FfaLateEntry.cs"))
    lr = kept(src("FfaLateRules.cs"))
    facts = {
        "consts": consts, "literals": literals, "uses": uses,
        "late_format": "h[PropLate] = Lobby8;" in le and "v == Lobby8" in le,
        "bd_format": bool(re.search(r"string bd = I\(FfaMode\.GameNumber\) \+ \":\" \+ I\(PointK\) \+ \":\"\s*\+ "
                                    r"FfaLateRules\.BoundaryDigest\(", le)) and "ParseBd(p.Bd" in lr,
        "lag_format": bool(re.search(r"return lobby8 \+ \":\" \+ g\.ToString\([^)]*\) \+ \":\"\s*\+ k\.ToString",
                                     lr)) and "parts.Length != 3 || parts[0] != lobby8" in lr,
    }
    trace(facts)
    assert consts == {"PropAsmHint": "cr_asm_hint", "PropLate": "cr_late", "PropBd": "cr_bd",
                      "PropLag": "cr_lag"}, ("WP5 constants", consts)
    assert literals == {"FfaAssembly.cs:cr_asm_hint": 1, "FfaLateEntry.cs:cr_bd": 1, "FfaLateEntry.cs:cr_lag": 1,
                        "FfaLateEntry.cs:cr_late": 1}, ("WP5 one literal each", literals)
    assert uses == {"FfaAssembly.cs:PropAsmHint": 2, "FfaLateEntry.cs:PropBd": 2, "FfaLateEntry.cs:PropLag": 3,
                    "FfaLateEntry.cs:PropLate": 2}, ("WP5 writers and readers", uses)
    assert facts["late_format"] and facts["bd_format"] and facts["lag_format"], ("WP5 formats", facts)


# The base (== the pin, for plugin/) spectator parse of the snapshot, measured
# from git show 9a1dd9d:plugin/SpectatorSync.cs: HandleSnapshot's index reads
# and length tests, and BuildSnapshot's comment-stripped body digest.
PIN_SNAPSHOT_INDEXES = [0, 0, 1, 2, 3, 6, 7, 9, 10, 11, 12, 16, 17]
PIN_SNAPSHOT_LENGTHS = ["a.Length<16", "a.Length>=18"]
PIN_BUILD_SNAPSHOT_MD5 = "7c4bb1a127357abd8c9b499118735cd1"
WP6_TAIL = ["marker", "pointsTotal", "kills", "game", "levelId", "picks", "seed", "k", "n", "scale"]
WP6_EXPR = {"LateMarker": "marker", "ptot": "pointsTotal", "kl": "kills", "g": "game", "level": "levelId",
            "new string[0]": "picks", "(int)seed": "seed", "PointK": "k", "PointEpoch": "n",
            "AppliedScaleTag()": "scale"}


def test_wp6_late_snapshot_tail():
    """WP6: the master's append and the late seat's parse name the same
    fields in the same order after the snapshot's 18; the spectator's parse
    of BuildSnapshot is unchanged."""
    import hashlib
    ss = block("FfaLateEntry.cs", "void SendSnapshot(")
    tail = re.search(r"var tail = new object\[\] \{([^}]*)\};", kept(ss))
    order = [WP6_EXPR.get(norm(x), "?" + norm(x)) for x in tail.group(1).split(",")] if tail else []
    lvl = re.search(r"int level = ([^;]*);", kept(ss))
    pos = {f: 18 + i for i, f in enumerate(WP6_TAIL)}
    ol = kept(block("FfaLateEntry.cs", "void OnLateSnapshot("))
    cp = kept(block("FfaLateEntry.cs", "void CheckPendingSnapshot("))
    sd = kept(block("FfaLateEntry.cs", "string SnapshotDigest("))
    reads = {
        "length": bool(re.search(r"a\.Length < %d \|\| S\(a, %d\) != LateMarker" % (len(WP6_TAIL) + 18, pos["marker"]), ol)),
        "level": "int level = N(a, %d, -1);" % pos["levelId"] in ol and "level = N(a, %d, -1)" % pos["levelId"] in cp,
        "k": "_snapK = N(a, %d, -1);" % pos["k"] in ol and "k = N(a, %d, 0)" % pos["k"] in cp,
        "game": "int g = N(a, %d, 0)" % pos["game"] in cp,
        "seed": "int theirs = N(a, %d, 0);" % pos["seed"] in cp,
        "scale": "string scale = S(a, %d)" % pos["scale"] in cp,
        "totals": "a[%d] as int[], a[%d] as int[]" % (pos["pointsTotal"], pos["kills"]) in cp
        and "a[%d] as int[]" % pos["pointsTotal"] in sd,
    }
    hs_src = src("SpectatorSync.cs")
    hs = cs.code_of(hs_src, "private static void HandleSnapshot(")
    idx = sorted(int(m.group(1)) for m in re.finditer(r"(?<![A-Za-z0-9_])a\[(\d+)\]", hs))
    lens = sorted(m.group(0).replace(" ", "") for m in re.finditer(r"a\.Length\s*(?:<=|>=|<|>|==)\s*\d+", hs))
    bs = cs.code_of(hs_src, "private static object[] BuildSnapshot(")
    md5 = hashlib.md5("\n".join(ln.rstrip() for ln in bs.split("\n") if ln.strip()).encode("ascii")).hexdigest()
    facts = {"order": order, "level_source": norm(lvl.group(1)) if lvl else None, "reads": reads,
             "spectator": [idx == PIN_SNAPSHOT_INDEXES, lens == PIN_SNAPSHOT_LENGTHS, md5 == PIN_BUILD_SNAPSHOT_MD5]}
    trace(facts)
    assert order == WP6_TAIL, ("WP6 append order", order)
    assert facts["level_source"] == "N(snap, 5, -1)", ("WP6 level source", facts["level_source"])
    assert all(reads.values()), ("WP6 parse positions", reads)
    assert all(facts["spectator"]), ("WP6 spectator parse unchanged", idx, lens, md5)


# ================================================================ WP7, WP10, WP11, WP12 (events, chain, release)

def test_wp7_wp10_wp11_events():
    """WP7/WP10/WP11: the event codes 53-58, distinct from 51 and 52; each
    sender's payload order and each receiver's parse order; the stamp's
    result literals at the master's send and ValidateStamp's reader; the lag
    step and its game key on both sides."""
    le = kept(src("FfaLateEntry.cs"))
    lr = kept(src("FfaLateRules.cs"))
    decl = r"(?:(?:internal|public|const|static)\s+)+byte\s+(EVT_\w+)\s*=\s*(\d+)\s*;"
    codes = dict((n, int(v)) for n, v in re.findall(decl, le))
    spec = dict((n, int(v)) for n, v in re.findall(decl, kept(src("SpectatorSync.cs"))))
    payload = {}
    for name in ("EVT_READY", "EVT_EPOCH", "EVT_SCALE", "EVT_EPOCH_ACK", "EVT_CALLIN", "EVT_MASTER"):
        payload[name] = [norm(x) for x in re.findall(r"Raise\(" + name + r", new object\[\] \{([^}]*)\}", le)]
    dispatch = dict(re.findall(r"case (EVT_\w+): (\w+)\(e\); break;", le))
    parse = {
        "OnReady": bool(re.search(r"S\(a, 0\) != Lobby8\) return;\s*int n = N\(a, 1, -1\);",
                                  kept(block("FfaLateEntry.cs", "void OnReady(")))),
        "OnProposal": "Lobby8 = S(a, 0), N = N(a, 1, -1), Chain = S(a, 2), G = N(a, 3, -1), K = N(a, 4, -1)"
                      in kept(block("FfaLateEntry.cs", "void OnProposal(")),
        "OnAck": "Lobby8 = S(a, 0), N = N(a, 1, -1), Chain = S(a, 2), G = N(a, 3, -1), K = N(a, 4, -1)"
                 in kept(block("FfaLateEntry.cs", "void OnAck(")),
        "OnStamp": "Lobby8 = S(a, 0), G = N(a, 1, -1), K = N(a, 2, -1), N = N(a, 3, -1), Chain = S(a, 4), "
                   "Result = S(a, 5)" in kept(block("FfaLateEntry.cs", "void OnStamp(")),
        "OnScale": "string l8 = S(a, 0);" in kept(block("FfaLateEntry.cs", "void OnScale(")) and
                   "int game = N(a, 1, -1), k = N(a, 2, -1), count = N(a, 3, -1);" in
                   kept(block("FfaLateEntry.cs", "void OnScale(")),
        "OnMasterEvent": "if (S(a, 0) != Lobby8) return;" in kept(block("FfaLateEntry.cs", "void OnMasterEvent(")),
    }
    msd = kept(block("FfaLateRules.cs", "internal static void MasterStampDecision("))
    send = sorted(set(re.findall(r"result = \"([a-z]+)\"", msd)))
    vs = kept(block("FfaLateRules.cs", "internal static string ValidateStamp("))
    reader = sorted(set(re.findall(r"s\.Result == \"([a-z]+)\"", vs)))
    scale_senders = calls(src("FfaMode.cs"), r"FfaMapScale\.MasterPublishCount")
    raise_scale = calls(src("FfaMapScale.cs"), r"FfaLateEntry\.RaiseScale")
    lag_client = bool(re.search(r'FfaAssembly\.Receipt\(lobby, "lag", "\\"game\\":"', kept(src("FfaLateEntry.cs"))))
    steps = server_const("_ASM_STEPS") or frozenset()
    handler = server_def("_asm_connect_problem")
    htxt = ast.get_source_segment(MAIN_PY.read_text(encoding="utf-8"), handler) if handler else ""
    facts = {"codes": codes, "spec": spec, "payload": payload, "dispatch": dispatch, "parse": parse,
             "result_send": send, "result_read": reader, "scale_senders": scale_senders,
             "raise_scale": raise_scale, "lag": [lag_client, "lag" in steps,
                                                 'if s in ("entered", "lag") and req.game is None' in (htxt or "")]}
    trace(facts)
    assert codes == {"EVT_READY": 53, "EVT_EPOCH": 54, "EVT_SCALE": 55, "EVT_EPOCH_ACK": 56, "EVT_CALLIN": 57,
                     "EVT_MASTER": 58} and spec.get("EVT_REQUEST") == 51 and spec.get("EVT_SNAPSHOT") == 52, \
        ("WP7 codes", codes, spec)
    assert payload == {"EVT_READY": ["Lobby8, r, ChainAt(r)"],
                       "EVT_EPOCH": ["proposal.Lobby8, proposal.N, proposal.Chain, g, k"],
                       "EVT_SCALE": ["Lobby8, g, k, count"],
                       "EVT_EPOCH_ACK": ["p.Lobby8, p.N, p.Chain, p.G, p.K"],
                       "EVT_CALLIN": ["stamp.Lobby8, g, k, n, stamp.Chain, result"],
                       "EVT_MASTER": ["Lobby8, newMaster.ActorNumber, FfaMode.GameNumber, PointK"]}, \
        ("WP7 payload order", payload)
    assert dispatch == {"EVT_READY": "OnReady", "EVT_EPOCH": "OnProposal", "EVT_SCALE": "OnScale",
                        "EVT_EPOCH_ACK": "OnAck", "EVT_CALLIN": "OnStamp", "EVT_MASTER": "OnMasterEvent"}, \
        ("WP11 receivers", dispatch)
    assert all(parse.values()), ("WP11 parse order", parse)
    assert send == ["carry", "commit", "unacked"] and set(reader) <= set(send) and reader, \
        ("WP11 result literals", send, reader)
    assert scale_senders == 2 and raise_scale == 1, ("WP10 senders", scale_senders, raise_scale)
    assert all(facts["lag"]), ("WP11 lag step", facts["lag"])


WP7_VECTORS = [("0", "1a2b3c4d", 1, 2, 7, "19de52a1bf1b36a9"),
               ("19de52a1bf1b36a9", "1a2b3c4d", 2, 4, 9, "b92768aebf890ca6")]


def test_wp7_chain_vectors():
    """WP7: the server's _ffa_epoch_chain and the client's ChainOf (run by the
    harness's --wp7 mode) return the same FNV-1a 64 digests on the vectors,
    and the client's hash gives the empty-string and "a" vectors."""
    fn = server_def("_ffa_epoch_chain")
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "main.py", "exec"), ns)  # noqa: S102
    server = [ns["_ffa_epoch_chain"](p, l8, n, s, a) for p, l8, n, s, a, _ in WP7_VECTORS]
    exe = dotnet()
    if exe is None:
        pytest.skip("no dotnet on this seat")
    proj = TOOLS / "late-rules-harness" / "late-rules-harness.csproj"
    rc, out, err = run([exe, "run", "--project", str(proj), "-c", "Release", "--", "--wp7"], timeout=1500)
    client = dict(re.findall(r"^wp7 (chain n=1|chain n=2|fnv empty|fnv a) ([0-9a-f]{16})$", out, re.M))
    facts = {"server": server, "client": client, "rc": rc}
    trace(facts)
    want = [v[5] for v in WP7_VECTORS]
    assert server == want, ("WP7 server chain", server)
    assert rc == 0 and [client.get("chain n=1"), client.get("chain n=2")] == want, ("WP7 client chain", client, err[-300:])
    assert client.get("fnv empty") == "cbf29ce484222325" and client.get("fnv a") == "af63dc4c8601ec8c", \
        ("WP7 hash vectors", client)


def test_wp12_release_route():
    """WP12: the client's release POST path, body keys and why values equal
    the route's path, request model and allowed values."""
    sr = kept(block("FfaAssembly.cs", "void SendRelease("))
    path = bool(re.search(r"\"/api/v1/ffa/lobby/\" \+ lobby \+ \"/release\"", sr))
    body = sorted(set(re.findall(r"\\\"([a-z_]+)\\\":", sr)))
    ex = kept(block("FfaAssembly.cs", "internal static void Exit("))
    rm = re.search(r"bool\s+release\s*=\s*([^;]*);", ex)
    whys = sorted(set(re.findall(r"why == \"([a-z_]+)\"", rm.group(1)))) if rm else []
    route = None
    for node in main_ast().body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "ffa_lobby_release":
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant):
                    route = d.args[0].value
    facts = {"path": path, "body": body, "whys": whys, "route": route,
             "model": sorted(model_fields("_AsmReleaseReq")), "allowed": sorted(server_const("_ASM_RELEASE_WHY") or [])}
    trace(facts)
    assert path and route == "/api/v1/ffa/lobby/{lobby_id}/release", ("WP12 path", path, route)
    assert body == facts["model"] == ["steam_id", "why"], ("WP12 body keys", body, facts["model"])
    assert whys == facts["allowed"] == ["fence_expired", "join_timeout"], ("WP12 why values", whys, facts["allowed"])
