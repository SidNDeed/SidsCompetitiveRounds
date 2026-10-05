"""Identity-clock evidence, client half: the harness runner.

Builds IdentityClockTests (the REAL plugin/IdentityClockCore.cs) into work/,
then:
  1. units: every unit group must pass;
  2. fixtures: the client's records of the SERVER lane's fixture inputs equal
     the server's record.txt byte for byte, and the envelope's fields (record,
     sig) equal the server's envelope.json;
  3. replay: synthetic games' envelopes parse, verify and budget identically
     through the server module (ice_parse_envelope, ice_parse_record,
     ice_verify_sig, ice_budget_record), and carry no planted needle;
  4. clock: the client's X-Seat-Clock strings agree with ice_parse_clock and
     with the server's clock_headers.json;
  5. containment: a static scan of plugin/IdentityClockEvidence.cs (every
     Harmony hook body is a catch-all try, or an allow-listed statement) and
     of each shared registration call site (wrapped in try/catch);
  6. mutants: each mutant (a COPY of the core, or of the scanned text) must be
     caught by its target and pass its control;
  7. perf (only with --perf): the survey over this seat's real files, read only.
The server module is read by path from the server worktree and never written.
Prints EXIT <code> last.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
PROJ = os.path.join(HERE, "IdentityClockTests.csproj")
CORE = os.path.join(REPO, "plugin", "IdentityClockCore.cs")
EVID = os.path.join(REPO, "plugin", "IdentityClockEvidence.cs")
WORK = os.path.join(HERE, "work")
SERVER = os.environ.get("IC_SERVER_TREE", os.path.join(os.path.dirname(REPO), "scr-wt-identity-clock-server"))
SAPI = os.path.join(SERVER, "backend", "api")
SFIX = os.path.join(SERVER, "backend", "tests", "fixtures", "identity_clock")
KEY = "test-hmac-key-seat-evidence"
GAME = "C:/Program Files (x86)/Steam/steamapps/common/ROUNDS"
NEEDLES = ("qxuser", "qxhost7")


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(tag, core):
    out = os.path.join(WORK, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep,
           "-p:CoreSource=" + core]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "IdentityClockTests.dll")


def run(dll, args=(), env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    r = subprocess.run(["dotnet", dll] + list(args), capture_output=True, text=True, env=e)
    return r.returncode, r.stdout.strip()


# -- the server module -------------------------------------------------------------------------

def server():
    sys.path.insert(0, SAPI)
    import identity_clock_evidence as ice  # noqa: E402
    import seat_evidence as se  # noqa: E402
    return ice, se


def fixtures_check(dll, ice):
    out = os.path.join(WORK, "fixtures-out")
    rc, text = run(dll, ["fixtures", SFIX, KEY, out])
    lines = [text]
    ok = rc == 0
    for name in ("base", "over_cap"):
        want = open(os.path.join(SFIX, name, "record.txt"), "rb").read()
        got = open(os.path.join(out, name + ".record.txt"), "rb").read()
        same = want == got
        lines.append("  %s record.txt %s (%d / %d bytes)" % (name, "EQUAL byte for byte" if same else "DIFFERS", len(got), len(want)))
        ok = ok and same
        senv = json.load(open(os.path.join(SFIX, name, "envelope.json"), encoding="utf-8"))
        cenv_text = open(os.path.join(out, name + ".envelope.json"), "rb").read().decode("ascii")
        cenv = json.loads(cenv_text)
        same_env = cenv == senv and cenv["record"].encode("ascii") == want and cenv["sig"] == senv["sig"]
        lines.append("  %s envelope fields %s (sig %s)" % (name, "EQUAL" if same_env else "DIFFER", cenv.get("sig", "")[:16]))
        ok = ok and same_env
        # the server's own budgeter over the same input, as a second reference
        inp = json.load(open(os.path.join(SFIX, name, "input.json"), encoding="utf-8"))
        ref = ice.ice_budget_record(inp)
        lines.append("  %s ice_budget_record(input) == client record: %s" % (name, ref.encode("ascii") == got))
        ok = ok and ref.encode("ascii") == got
    return ok, lines


def replay_check(dll, ice, se):
    out = os.path.join(WORK, "replay-out")
    rc, text = run(dll, ["replay", KEY, out])
    lines = [text]
    ok = rc == 0
    for name in ("game_full", "game_not_yet", "game_postboot", "game_wide"):
        raw = open(os.path.join(out, name + ".envelope.json"), "rb").read().decode("ascii")
        try:
            env = ice.ice_parse_envelope(json.loads(raw))
            rec = ice.ice_parse_record(env)
            sig = ice.ice_verify_sig(KEY, env)
            full = json.load(open(os.path.join(out, name + ".full.json"), encoding="utf-8"))
            same_budget = ice.ice_budget_record(full) == env["record_text"]
            low = raw.lower()
            clean = not any(n in low for n in NEEDLES)
            fine = sig and same_budget and clean
            lines.append("  %s: parsed, sig %s, budget parity %s, bytes %d, pt_o %d, omit %s, needles absent %s" % (
                name, sig, same_budget, len(env["record_bytes"]), len(rec["pt_o"]), json.dumps(rec["omit"], separators=(",", ":")), clean))
            if name == "game_not_yet":
                states = {e[2] for e in rec["gdig"]} | {rec["ldir"]["plugins"][0], rec["ldir"]["patchers"][0], rec["aload"][2]}
                lines.append("    not_yet everywhere: %s" % (states == {3}))
                fine = fine and states == {3}
            if name == "game_postboot":
                finding = any(c[3] == 1 for c in rec["chk"] if c[0] != 0) and "scr.ic.testguid" in rec["plug"]
                lines.append("    after-boot key reaches a later moment as a finding: %s" % finding)
                fine = fine and finding
            if name == "game_wide":
                lines.append("    trimmed under the bound: %s" % (len(env["record_bytes"]) <= 16384 and sum(rec["omit"].values()) > 0))
                fine = fine and sum(rec["omit"].values()) > 0
            ok = ok and fine
        except se.EvidenceRefused as ex:
            lines.append("  %s: REFUSED %s" % (name, ex.args))
            ok = False
    return ok, lines


def clock_check(dll, ice):
    out = os.path.join(WORK, "clock-out")
    rc, _ = run(dll, ["clock", out])
    rows = json.load(open(os.path.join(out, "clock.json"), encoding="utf-8"))
    fix = json.load(open(os.path.join(SFIX, "clock_headers.json"), encoding="utf-8"))
    rec = {"proc": ["0123456789ab", 1, 1, 0, 0]}
    lines = []
    ok = rc == 0
    ok_rows = rows[:4]
    for h in ok_rows:
        st = ice.ice_parse_clock(h, rec)["state"]
        lines.append("  client %r -> server %s" % (h, st))
        ok = ok and st == "ok"
    refused = rows[4:]
    lines.append("  client refuses out-of-bound parts (no header): %s" % all(h == "" for h in refused))
    ok = ok and all(h == "" for h in refused)
    # the server fixture's ok rows are exactly the client's strings for the same parts
    same = rows[0] == fix[0]["header"] and rows[1] == fix[6]["header"]
    lines.append("  equals clock_headers.json rows 0 and 6: %s" % same)
    ok = ok and same
    # what the client would have built for its refused cases is malformed at the server
    would = ["0123456789AB.1.1.1", "0123456789ab.1000000000001.1.1", "0123456789ab.-1.1.1", "0123.1.1.1"]
    mal = all(ice.ice_parse_clock(h, rec)["state"] == "malformed" for h in would)
    lines.append("  the refused cases are malformed at the server: %s" % mal)
    ok = ok and mal
    return ok, lines


# -- containment scan --------------------------------------------------------------------------

HOOK_ATTR = re.compile(r"\[Harmony(Prefix|Postfix|Finalizer)\]")
ALLOWED = {"__state = -1;", "if (__state < 0) return;", "return __exception;"}


def body_after(text, idx):
    """The method body after position idx: (start, end) of the braces' content."""
    b = text.index("{", idx)
    depth, i = 0, b
    while True:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return b + 1, i
        i += 1


def statements(body):
    """Top-level statements of a body; a try statement runs to the end of its catch block."""
    out, i, n = [], 0, len(body)
    while i < n:
        while i < n and body[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        if body.startswith("try", i) and not body[i + 3].isalnum():
            s, e = body_after(body, i)
            j = e + 1
            while j < n and body[j] in " \t\r\n":
                j += 1
            if not body.startswith("catch", j):
                out.append(("try-without-catch", body[i:j]))
                i = j
                continue
            head_end = body.index("{", j)
            head = body[j:head_end].strip()
            s2, e2 = body_after(body, j)
            out.append(("try", head))
            i = e2 + 1
            continue
        if True:
            depth, j = 0, i
            while j < n:
                if body[j] == "{":
                    depth += 1
                elif body[j] == "}":
                    depth -= 1
                elif body[j] == ";" and depth == 0:
                    break
                j += 1
            out.append(("stmt", " ".join(body[i:j + 1].split())))
            i = j + 1
    return out


def scan(evid_text, sites):
    problems = []
    hooks = 0
    for m in HOOK_ATTR.finditer(evid_text):
        s, e = body_after(evid_text, m.end())
        hooks += 1
        for kind, what in statements(evid_text[s:e]):
            if kind == "try":
                if what not in ("catch", "catch (Exception)") and not what.startswith("catch (Exception "):
                    problems.append("hook at %d: catch is not catch-all: %s" % (m.start(), what))
            elif kind == "stmt":
                if what not in ALLOWED:
                    problems.append("hook at %d: statement outside try: %s" % (m.start(), what))
            else:
                problems.append("hook at %d: %s" % (m.start(), kind))
    n_sites = 0
    for path, text in sites:
        for ln in text.splitlines():
            if "IdentityClockEvidence." in ln and "//" not in ln.split("IdentityClockEvidence.")[0]:
                n_sites += 1
                t = ln.strip()
                if "ClockHeaderNow" in t:
                    continue    # a delegate value, invoked by ApiClient inside its own try (checked below)
                if not re.fullmatch(r"try \{ IdentityClockEvidence\.\w+\(.*\); \} catch \{ \}", t):
                    problems.append("%s: call site not wrapped: %s" % (os.path.basename(path), t))
    return hooks, n_sites, problems


def scan_sites():
    sites = []
    for name in ("Plugin.cs", "GameStateWatcher.cs", "SeatEvidence.cs"):
        p = os.path.join(REPO, "plugin", name)
        sites.append((p, open(p, encoding="utf-8").read()))
    return sites


def api_header_contained():
    t = open(os.path.join(REPO, "plugin", "ApiClient.cs"), encoding="utf-8").read()
    return t.count("try { ch = clockHeader(); } catch { ch = null; }") == 1


def quit_wiring(plugin_text, evid_text):
    """A game that ends by quitting keeps its record: the quit handler captures the live game
    (SeatEvidenceOnQuit, whose cut path runs IdentityClockEvidence.Dispatch) BEFORE the
    identity flush runs, and the flush writes each capture to the closing file under route i
    and logs every outcome. Returns the list of problems (empty when wired)."""
    probs = []
    i_cap = plugin_text.find("try { GameStateWatcher.SeatEvidenceOnQuit(); } catch { }")
    i_quit = plugin_text.rfind("Application.quitting += () =>", 0, max(i_cap, 0))
    i_flush = plugin_text.find("try { IdentityClockEvidence.FlushOnQuit(); } catch { }", max(i_cap, 0))
    i_end = plugin_text.find("};", max(i_cap, 0))
    if i_quit < 0 or i_cap < 0 or i_flush < 0 or not (i_cap < i_flush < i_end):
        probs.append("Plugin.cs: the quit handler does not run IdentityClockEvidence.FlushOnQuit after the live-game capture")
    s = evid_text.find("internal static void FlushOnQuit()")
    if s < 0:
        probs.append("IdentityClockEvidence.cs: FlushOnQuit missing")
    else:
        b, e = body_after(evid_text, s)
        body = evid_text[b:e]
        if body.count('SeatEvidence.SpoolClosing("i", env)') != 1:
            probs.append("FlushOnQuit does not write the closing file under route i")
        if body.count("no record at quit") < 3 or "record kept for the next launch" not in body:
            probs.append("FlushOnQuit does not log every outcome")
        # The summary line sits after the capture loop, so a quit with no live game logs too.
        i_sum = body.find('" quit flush ran: "')
        i_loop = body.find("while (_captures.Count > 0")
        loop_end = body_after(body, i_loop)[1] if i_loop >= 0 else -1
        if i_sum < 0 or i_loop < 0 or i_sum < loop_end:
            probs.append("FlushOnQuit leaves no line on a quit with no capture")
        if "RequestSurvey" in body or "_survey.Step" in body:
            probs.append("FlushOnQuit starts disk survey work")
    gsw = open(os.path.join(REPO, "plugin", "GameStateWatcher.cs"), encoding="utf-8").read()
    q = gsw.find("internal static void SeatEvidenceOnQuit()")
    if q < 0 or "SeatEvidenceCut(" not in gsw[q:q + 600]:
        probs.append("GameStateWatcher.SeatEvidenceOnQuit no longer cuts the live game")
    c = gsw.find("void SeatEvidenceCut(")
    if c < 0 or "IdentityClockEvidence.Dispatch(" not in gsw[c:gsw.find("internal static void SeatEvidenceOnQuit()")]:
        probs.append("SeatEvidenceCut does not capture the identity-clock game")
    return probs


# -- mutants -----------------------------------------------------------------------------------
# (name, [(old, new), ...], target, control); target/control: a unit group, "fixtures" or "replay"

MUTANTS = [
    ("m1_combat_gate_removed", [("if (combatLive) { CombatSkips++; return 0; }", "if (combatLive) { CombatSkips++; }")], "gate", "trunc"),
    ("m1_step_unbounded", [("while (_job != null && n < STEP_UNITS_MAX)", "while (_job != null)")], "gate", "trunc"),
    ("m1_reparse_followed", [("if (e.IsReparse) continue;", "if (false) continue;")], "reparse", "trunc"),
    ("m1_truncation_unflagged", [("if (_dlls.Count > PartCap) _partTrunc = true;", "if (false) _partTrunc = true;")], "trunc", "reparse"),
    ("m1_stale_published", [("if (r == null || r.Gen != Wanted)", "if (r == null)")], "stale", "flight"),
    ("m1_not_single_flight", [("if (_job != null && _job.Gen == gen) return;", "")], "flight", "stale"),
    ("l3_result_reused", [("if (_result != null && _result.Gen == gen) return;", "if (_result != null) return;")], "pergame", "l4"),
    ("l4_not_yet_as_ok", [('{ if (n++ >= GDIG_MAX) break; gdig.Add(L((long)f.Id, "", (long)NOT_YET, 0L)); }',
                           '{ if (n++ >= GDIG_MAX) break; gdig.Add(L((long)f.Id, "", (long)OK, 0L)); }')], "l4", "pergame"),
    ("l4_unopenable_as_missing", [("R.AloadDiskState = missing ? NO_FILE : READ_FAILED;", "R.AloadDiskState = NO_FILE;")], "l4", "pergame"),
    ("l5_needle_unchecked", [("&& !HasNeedle(s)) return s;", ") return s;")], "privacy", "boot"),
    ("l5_ldir_unfiltered", [("named.Add(L(priv.NameOrEmpty((string)e[0]), e[1]));", "named.Add(L((string)e[0], e[1]));")], "sweep", "privacy"),
    ("l1_boot_ordinal_zero", [("Ordinal = Math.Min(Boots, ORDINAL_MAX - 1)", "Ordinal = 0")], "boot", "outcome"),
    ("l6_keys_memoized", [("var src = _read();", "var src = _m ?? (_m = _read());"),
                          ("internal KeySource(Func<IList<string>> read) { _read = read; }",
                           "internal KeySource(Func<IList<string>> read) { _read = read; } private IList<string> _m;")], "postboot", "outcome"),
    ("l7_move_on_input", [("if (input) { o.InFirst = relC; o.InFirstArr = arr; }",
                           "if (input) { o.InFirst = relC; o.InFirstArr = arr; if (o.MoveFirst < 0) { o.MoveFirst = relC; o.MoveFirstArr = arr; } }")], "move", "fps"),
    ("l8_fps_substituted", [("PubFps = LastPubFps,", "PubFps = LastPubFps >= 0 ? LastPubFps : 30,")], "fps", "move"),
    ("l8_unpublished_zero", [("if (!published) return -1;", "if (!published) return 0;")], "fps", "move"),
    ("aload_mvid_raw_hex", [('return new Guid(g).ToString("N");', "return Hex(g);")], "mvid", "l4"),
    ("l13_failed_read_none", [('if (!fightersKnown || !cachePresent || !lastReadOk) return "unknown";',
                               'if (!fightersKnown || !cachePresent) return "unknown";')], "series", "budget"),
    ("budget_tie_order", [("foreach (var k in TRIM) { int n = TrimLen(o, k); if (n > best)",
                           "foreach (var k in TRIM) { int n = TrimLen(o, k); if (n >= best)")], "fixtures", "units:budget"),
]

SCAN_MUTANTS = [
    ("hook_unwrapped", "try { IdentityClockEvidence.PointStart(); } catch { }", "IdentityClockEvidence.PointStart();"),
    ("hook_narrow_catch", "try { IdentityClockEvidence.MovePlayers(__0); } catch { }",
     "try { IdentityClockEvidence.MovePlayers(__0); } catch (InvalidOperationException) { }"),
    ("hook_stmt_outside", "            if (__state < 0) return;\n",
     "            if (__state < 0) return;\n            IdentityClockEvidence.Tick();\n"),
]


def judge(dll, what, ice, se):
    if what == "fixtures":
        ok, _ = fixtures_check(dll, ice)
        return ok
    if what == "replay":
        ok, _ = replay_check(dll, ice, se)
        return ok
    group = what.split(":", 1)[-1]
    rc, _ = run(dll, ["units", group], env={"IC_GAME_ASM": os.path.join(GAME, "ROUNDS_Data", "Managed", "Assembly-CSharp.dll")})
    return rc == 0


def main():
    perf = "--perf" in sys.argv
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    shead = subprocess.run(["git", "-C", SERVER, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head, "server tree", shead)
    core_sha = sha(CORE)
    print("plugin/IdentityClockCore.cs sha256", core_sha)
    print("plugin/IdentityClockEvidence.cs sha256", sha(EVID))
    ice, se = server()
    ok = True

    dll = build("base", CORE)
    if dll is None:
        print("BUILD FAILED (base)")
        print("EXIT 1")
        return 1
    rc, out = run(dll, ["units"], env={"IC_GAME_ASM": os.path.join(GAME, "ROUNDS_Data", "Managed", "Assembly-CSharp.dll")})
    print(out)
    n_pass = out.count("PASS ")
    n_fail = out.count("FAIL ")
    print("units: %d pass, %d fail, exit %d" % (n_pass, n_fail, rc))
    ok = ok and rc == 0 and n_fail == 0 and n_pass > 0

    for title, fn in (("fixtures", lambda: fixtures_check(dll, ice)), ("replay", lambda: replay_check(dll, ice, se)),
                      ("clock", lambda: clock_check(dll, ice))):
        fok, lines = fn()
        print("\n".join(lines))
        print("%s check: %s" % (title, "PASS" if fok else "FAIL"))
        ok = ok and fok

    evid = open(EVID, encoding="utf-8").read()
    sites = scan_sites()
    hooks, n_sites, problems = scan(evid, sites)
    api_ok = api_header_contained()
    print("containment: %d hook bodies, %d registration call sites, %d problems, ApiClient clock call contained: %s" % (hooks, n_sites, len(problems), api_ok))
    for p in problems:
        print("  " + p)
    cok = hooks == 6 and n_sites >= 10 and not problems and api_ok
    print("containment check:", "PASS" if cok else "FAIL")
    ok = ok and cok

    plugin_text = open(os.path.join(REPO, "plugin", "Plugin.cs"), encoding="utf-8").read()
    qprobs = quit_wiring(plugin_text, evid)
    for p in qprobs:
        print("  " + p)
    print("quit flush wiring check:", "PASS" if not qprobs else "FAIL")
    ok = ok and not qprobs
    # its mutants: the flush unregistered, and the flush writing the queue instead of the closing file
    q1 = quit_wiring(plugin_text.replace("try { IdentityClockEvidence.FlushOnQuit(); } catch { }", ""), evid)
    q2 = quit_wiring(plugin_text, evid.replace('SeatEvidence.SpoolClosing("i", env)', "SeatEvidence.EnqueueIdentity(env)"))
    print("quit mutant flush_unregistered %s, flush_to_queue %s" % ("CAUGHT" if q1 else "MISSED", "CAUGHT" if q2 else "MISSED"))
    # the summary line removed, and the summary line logged only inside the capture loop
    q3 = quit_wiring(plugin_text, evid.replace('" quit flush ran: "', '" quit flush: "'))
    q4 = quit_wiring(plugin_text, evid.replace('" quit flush ran: "', '" quit flush: "').replace(
        "tried++;", 'tried++; Plugin.Log.LogInfo(TAG + " quit flush ran: ");'))
    print("quit mutant summary_removed %s, summary_in_loop %s" % ("CAUGHT" if q3 else "MISSED", "CAUGHT" if q4 else "MISSED"))
    ok = ok and bool(q1) and bool(q2) and bool(q3) and bool(q4)

    raw = open(CORE, "rb").read().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    caught = 0
    quick = "--quick" in sys.argv
    if quick:
        print("QUICK run: mutants and scan mutants not run (a quick run is never the run of record)")
    for name, pairs, target, control in ([] if quick else MUTANTS):
        text = raw
        bad = False
        for old, new in pairs:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            if text.count(o) != 1:
                print("BAD mutant %s: anchor occurs %d times: %s" % (name, text.count(o), old[:60]))
                bad = True
                break
            text = text.replace(o, n)
        if bad:
            ok = False
            continue
        mdir = os.path.join(WORK, "mut-" + name)
        os.makedirs(mdir, exist_ok=True)
        mcore = os.path.join(mdir, "IdentityClockCore.cs")
        open(mcore, "wb").write(text.encode("utf-8"))
        mdll = build("mut-" + name, mcore)
        if mdll is None:
            print("mutant %s: BUILD FAILED" % name)
            ok = False
            continue
        t_fail = not judge(mdll, target, ice, se)
        c_pass = judge(mdll, control, ice, se)
        print("mutant %-28s target %-14s %s   control %-14s %s" % (name, target, "CAUGHT" if t_fail else "MISSED", control, "passes" if c_pass else "FAILS"))
        if t_fail and c_pass:
            caught += 1
        else:
            ok = False
    print("mutants: %d of %d caught with passing controls" % (caught, len(MUTANTS)))

    enl = "\r\n" if "\r\n" in evid else "\n"
    s_caught = 0
    for name, old, new in ([] if quick else SCAN_MUTANTS):
        o, n = old.replace("\n", enl), new.replace("\n", enl)
        if evid.count(o) != 1:
            print("BAD scan mutant %s: anchor occurs %d times" % (name, evid.count(o)))
            ok = False
            continue
        _, _, probs = scan(evid.replace(o, n), sites)
        hit = len(probs) > 0
        print("scan mutant %-20s %s" % (name, "CAUGHT" if hit else "MISSED"))
        s_caught += 1 if hit else 0
        ok = ok and hit
    # the site mutant: one registration call unwrapped
    site_text = [(p, t.replace("try { IdentityClockEvidence.Tick(); } catch { }", "IdentityClockEvidence.Tick();")) for p, t in sites]
    _, _, probs = scan(evid, site_text)
    print("scan mutant %-20s %s" % ("site_unwrapped", "CAUGHT" if probs else "MISSED"))
    ok = ok and bool(probs)
    print("scan mutants: %d of %d caught (control: the unmutated scan above has %d problems)" % (s_caught + (1 if probs else 0), len(SCAN_MUTANTS) + 1, len(problems)))

    if perf:
        man = os.path.join(GAME, "ROUNDS_Data", "Managed")
        bep = os.path.join(GAME, "BepInEx")
        rc, out = run(dll, ["perf", man, os.path.join(bep, "core"), os.path.join(bep, "plugins"), os.path.join(bep, "patchers"),
                            GAME, os.path.join(man, "Assembly-CSharp.dll")])
        print(out)
        ok = ok and rc == 0

    unchanged = sha(CORE) == core_sha
    print("core unchanged by the run (sha before == sha after):", unchanged)
    ok = ok and unchanged
    code = 0 if ok else 1
    print("EXIT", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
