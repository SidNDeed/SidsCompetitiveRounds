"""Seat evidence (contract V2), client half: build the cases over the REAL
plugin/SeatEvidenceCore.cs, run them, then hand the fixtures the build writes
to the SERVER branch's own backend/api/seat_evidence.py (read by path, never
written) and require:

  * budget_record(input) == the client's record text, byte for byte;
  * parse_envelope + parse_record accept the client's envelope (check_record
    included) and verify_sig accepts its signature under the fixture key;
  * check_compat + verify_compat_sig accept the client's compat body.

Then build mutated COPIES of the core (work/, CoreSource override; the tracked
file is never written) and require each mutant's target to FAIL and its
control case to PASS. The target "server" is the comparison above. Exit 0
only when everything holds.

    python tools/tests/seat-evidence-client/run_tests.py [--server-root DIR]
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PROJ = os.path.join(HERE, "SeatEvidenceTests.csproj")
CORE = os.path.join(REPO, "plugin", "SeatEvidenceCore.cs")
WORK = os.path.join(HERE, "work")
DEFAULT_SERVER = os.path.join(os.path.dirname(REPO), "scr-wt-seat-evidence-server")
FIXTURE_KEY = "fixture-key-not-a-secret"

# (name, old text, new text, target case, control case). Each old text must
# occur exactly once in the shipped file.
MUTANTS = [
    ("json_upper_hex", 'ToString("x4", CultureInfo.InvariantCulture)', 'ToString("X4", CultureInfo.InvariantCulture)', "json", "budget"),
    ("budget_tie_latest", "if (longest < 0 || lists[i].Count > lists[longest].Count) longest = i;",
     "if (longest < 0 || lists[i].Count >= lists[longest].Count) longest = i;", "budget", "json"),
    ("budget_removes_first", "lists[longest].RemoveAt(lists[longest].Count - 1);\n                entryLen[longest].RemoveAt(entryLen[longest].Count - 1);",
     "lists[longest].RemoveAt(0);\n                entryLen[longest].RemoveAt(0);", "server", "json"),
    ("hitsent_last_kind_zero", "hasLast ? Clamp(lastKind, 0, 9) : -1", "hasLast ? Clamp(lastKind, 0, 9) : 0", "entries", "json"),
    ("since_rounds", "double ms = Math.Floor((double)sinceBlockS * 1000.0);", "double ms = Math.Round((double)sinceBlockS * 1000.0);", "entries", "decide"),
    ("since_no_never", "if (!everReset || float.IsNaN(sinceBlockS)) return -1;", "if (float.IsNaN(sinceBlockS)) return -1;", "entries", "json"),
    ("drift_most_delayed", "if (!bestY.TryGetValue(b, out cur) || y > cur)", "if (!bestY.TryGetValue(b, out cur) || y < cur)", "congestion", "drift"),
    ("drift_sign", "double slope = sxy / sxx;", "double slope = -sxy / sxx;", "drift", "congestion"),
    ("drift_raw_jumps", "double r = ys[i] - (icept + slope * xs[i]);", "double r = ys[i];", "drift", "congestion"),
    ("bucket_truncates", "if ((x % d != 0) && (x < 0)) q--;", "", "buckets", "cadence"),
    ("cadence_counts_reorder", "if (gap <= 0) return;", "if (gap == 0) return;", "cadence", "buckets"),
    ("ordinal_uncapped", "return n > 255 ? 255 : n;", "return n;", "ordinals", "window"),
    ("window_hi_exclusive", "if (d >= LO && d <= HI) return true;", "if (d >= LO && d < HI) return true;", "window", "ordinals"),
    ("decide_conflict_retried", 'if (status == 409 && body.Contains("\\"conflict\\"")) { reason = "conflict"; return Act.Drop; }', "", "decide", "line"),
    ("decide_sixth_401", "if (p.SessionRetries >= MAX_SESSION_RETRIES)", "if (p.SessionRetries > MAX_SESSION_RETRIES)", "decide", "line"),
    ("decide_no_expiry", 'if (expired) { reason = "expired"; return Act.Drop; }\n            if (status == 404)',
     "if (status == 404)", "decide", "line"),
    ("line_attempts_reset", "Attempts = att,", "Attempts = 0,", "line", "decide"),
    ("build_commit_13", "IsBuildPart(commit, 12)", "IsBuildPart(commit, 13)", "build", "json"),
    ("other_build_cut", 'if (relayed == null || relayed.Length > 46) return "";',
     'if (relayed == null) return ""; if (relayed.Length > 46) relayed = relayed.Substring(0, 46);', "build", "json"),
    ("reservoir_never_replaces", "if (j < Cap) Items[(int)j] = v;", "", "reservoir", "cadence"),
    ("envelope_same_seat", "|| seat == other) return null;", ") return null;", "envelope", "json"),
    ("canonical_raw_attach", "Sha256Hex(Encoding.ASCII.GetBytes(attach))", "attach", "server", "json"),
    ("dll_ok_without_sha", 'bool ok = state == "ok" && sha != null && sha.Length == 64;', 'bool ok = state == "ok";', "server", "json"),
    ("age_ms_unclamped", "r[i] = i == a.Length - 1 ? Cnt(a[i]) : Ms(a[i]);", "r[i] = Cnt(a[i]);", "server", "json"),
    ("end_null_emitted", 'if (IsEndKind(End)) o.Add("end", End);', 'o.Add("end", End);', "server", "json"),
    ("end_after_build", 'if (IsEndKind(End)) o.Add("end", End);\n                o.Add("build", new List<object> { Build[0], Build[1], Build[2] });',
     'o.Add("build", new List<object> { Build[0], Build[1], Build[2] });\n                if (IsEndKind(End)) o.Add("end", End);', "server", "json"),
    ("cutscore_awards_self", "return new[] { self, 5 };", "return new[] { 5, other };", "end", "json"),
    ("cutscore_ignores_departure", "if (!otherLeft && self == other && self >= 4)", "if (self == other && self >= 4)", "end", "json"),
    # fix pass 1, F2: only the accepted tied state is awarded
    ("cutscore_untied", "&& self == other && self >= 4)", "&& self >= 4 && other >= 4)", "end", "json"),
    # fix pass 1, F6: the limits before every transmission, the count and next time persisted
    ("refusal_no_expiry", 'if (nowUnix - p.FirstUnix >= EXPIRY_S) return "expired";', "", "refusal", "line"),
    ("refusal_no_attempt_limit", 'if (p.Attempts >= MAX_ATTEMPTS) return "attempts_spent";', "", "refusal", "line"),
    ("transmission_not_counted", "t.Attempts = p.Attempts + 1;", "t.Attempts = p.Attempts;", "refusal", "line"),
    ("transmission_no_next_time", "t.NotBeforeUnix = nowUnix + Backoff(t.Attempts);", "", "refusal", "line"),
    ("line_next_time_dropped", '+ p.NotBeforeUnix.ToString(CultureInfo.InvariantCulture) + "\\t" + p.Route', '+ "0" + "\\t" + p.Route', "line", "refusal"),
    # fix pass 1, F8: the trailer verified, the newest whole copy recovered
    ("queue_hash_unchecked", "&& count == bodyLines && t[3] == QueueHash(sb.ToString());", ";", "queue", "line"),
    ("queue_primary_always", "if (pw && tw) return temp.Generation > primary.Generation ? 2 : 1;", "if (pw && tw) return 1;", "queue", "line"),
    ("queue_legacy_refused", "c.Whole = trailed || (allowLegacy && !sawTrailer);", "c.Whole = trailed;", "queue", "line"),
    ("sender_no_limit", "if (elapsedMs > COMPAT_SEND_LIMIT_MS) return SendStep.GiveUp;", "", "sender", "end"),
    ("sender_ignores_consent", "if (!consent) return SendStep.NoConsent;", "", "sender", "end"),
    ("sender_runs_enabled", "if (!disabled || !queued) return SendStep.Stop;", "if (!queued) return SendStep.Stop;", "sender", "end"),
    ("cut422_dropped", "if (status == 422 && IsCutRecord(p))", "if (false && IsCutRecord(p))", "cut422", "decide"),
    ("cut422_no_expiry", 'if (expired) { reason = "expired"; return Act.Drop; }\n                if (p.Attempts >= MAX_ATTEMPTS)',
     "if (p.Attempts >= MAX_ATTEMPTS)", "cut422", "decide"),
    ("cut_record_end_anywhere", "return j > 0 && j + 1 + E.Length <= p.Body.Length && string.CompareOrdinal(p.Body, j + 1, E, 0, E.Length) == 0;",
     "return p.Body.Contains(E);", "cut422", "decide"),
]

# Amendment A1 (build notes, "Contract amendments for the integrator"): an
# optional "end" key right after "rounds", one of these kinds.
END_KINDS = ("left", "other_left", "lost", "closing")


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
    return os.path.join(out, "bin", "SeatEvidenceTests.dll")


def run(dll, args=()):
    r = subprocess.run(["dotnet", dll] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def load_server(root):
    path = os.path.join(root, "backend", "api", "seat_evidence.py")
    spec = importlib.util.spec_from_file_location("server_seat_evidence", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


def amended_budget(sev, full):
    """The reference budgeter with amendment A1. Without an "end" key it IS
    budget_record. With one, budget_record runs over the record without it
    under a limit smaller by the bytes the key adds, and the key goes back
    after "rounds": the same removal sequence the reference would make, since
    the key's bytes are a constant."""
    if "end" not in full:
        return sev.budget_record(full)
    keys = list(full.keys())
    if keys.index("end") != keys.index("rounds") + 1 or full["end"] not in END_KINDS:
        raise ValueError("end key misplaced or unknown")
    rest = {k: v for k, v in full.items() if k != "end"}
    ins = ',"end":' + json.dumps(full["end"])
    text = sev.budget_record(rest, limit=sev.RECORD_MAX_BYTES - len(ins))
    at = text.index(',"build":')
    return text[:at] + ins + text[at:]


def amended_parse(sev, env):
    """parse_record with amendment A1: an "end" key, when present, must sit
    right after "rounds" and name a known kind; the rest is the reference's
    own check_record, unchanged."""
    rec = json.loads(env["record_text"], parse_float=sev._refuse_float, parse_constant=sev._refuse_float)
    if isinstance(rec, dict) and "end" in rec:
        keys = list(rec.keys())
        if keys.index("end") != keys.index("rounds") + 1 or rec["end"] not in END_KINDS:
            raise sev.EvidenceRefused(422, "end")
        sev.check_record({k: v for k, v in rec.items() if k != "end"})
    else:
        sev.check_record(rec)
    return rec


def server_check(sev, dll, tag, verbose):
    """The comparison against the server's own functions. Returns (ok, lines).
    A record without "end" goes through the server's functions unchanged; one
    with "end" through the amendment-A1 wrappers above (and the line says
    what the unamended server answers)."""
    d = os.path.join(WORK, tag, "fixtures")
    if os.path.isdir(d):
        shutil.rmtree(d)
    rc, out = run(dll, ["fixtures", d])
    if rc != 0:
        return False, ["fixtures: exit %d %s" % (rc, out[-500:])]
    lines, ok = [], True
    for name in open(os.path.join(d, "cases.txt"), encoding="ascii").read().split():
        p = lambda ext: os.path.join(d, name + ext)  # noqa: E731
        try:
            full = json.loads(open(p(".input.json"), encoding="ascii").read())
            mine = open(p(".record.txt"), "rb").read()
            has_end = "end" in full
            ref = (amended_budget(sev, full) if has_end else sev.budget_record(full)).encode("ascii")
            same = ref == mine
            env = sev.parse_envelope(json.loads(open(p(".envelope.json"), encoding="ascii").read()))
            note = ""
            if has_end:
                amended_parse(sev, env)
                try:
                    sev.parse_record(env)
                    note = ", unamended server: accepts"
                except Exception as ex:  # expected until the server adopts A1
                    note = ", unamended server: refuses %s" % getattr(ex, "field", ex)
            else:
                sev.parse_record(env)
            sig_ok = sev.verify_sig(FIXTURE_KEY, env)
            text_ok = env["record_bytes"] == mine
            good = same and sig_ok and text_ok
            lines.append("%s %s: %d bytes, %sbudget_record equal=%s, parse+check ok, verify_sig=%s, envelope record equal=%s%s"
                         % ("OK " if good else "BAD", name, len(mine), "A1 " if has_end else "", same, sig_ok, text_ok, note))
            ok = ok and good
        except Exception as ex:  # a refusal names its field
            lines.append("BAD %s: %s %s" % (name, type(ex).__name__, getattr(ex, "field", ex)))
            ok = False
    try:
        c = sev.check_compat(json.loads(open(os.path.join(d, "compat.json"), encoding="ascii").read()))
        csig = sev.verify_compat_sig(FIXTURE_KEY, c)
        lines.append("%s compat: check_compat ok, plugins=%s, verify_compat_sig=%s" % ("OK " if csig else "BAD", c["plugins"], csig))
        ok = ok and csig
    except Exception as ex:
        lines.append("BAD compat: %s %s" % (type(ex).__name__, getattr(ex, "field", ex)))
        ok = False
    return ok, lines


def main():
    root = DEFAULT_SERVER
    if "--server-root" in sys.argv:
        root = sys.argv[sys.argv.index("--server-root") + 1]
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    shead = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    sev, spath = load_server(root)
    print("server", shead, spath, "sha256", sha(spath))
    before, before_server = sha(CORE), sha(spath)
    print("plugin/SeatEvidenceCore.cs sha256", before)
    ok = True

    dll = build("base", CORE)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    rc, out = run(dll)
    print(out)
    ok = ok and rc == 0
    sok, lines = server_check(sev, dll, "base", True)
    print("\n".join(lines))
    print("server comparison:", "PASS" if sok else "FAIL")
    ok = ok and sok

    raw = open(CORE, "rb").read().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    caught = 0
    for name, old, new, target, control in MUTANTS:
        o, n = old.replace("\n", nl), new.replace("\n", nl)
        count = raw.count(o)
        if count != 1:
            print("BAD mutant %s: anchor occurs %d times" % (name, count))
            ok = False
            continue
        path = os.path.join(WORK, "mut_" + name + ".cs")
        open(path, "wb").write(raw.replace(o, n).encode("utf-8"))
        mdll = build("mut_" + name, path)
        if mdll is None:
            print("BAD mutant %s: does not build" % name)
            ok = False
            continue
        if target == "server":
            t_ok, _ = server_check(sev, mdll, "mut_" + name, False)
            trc = 0 if t_ok else 1
        else:
            trc, _ = run(mdll, [target])
        crc, _ = run(mdll, [control])
        hit = trc != 0 and crc == 0
        caught += hit
        ok = ok and hit
        print("%s mutant %s: target %s=%s; control %s=%s" % (
            "CAUGHT" if hit else "MISSED", name, target, "FAIL" if trc else "PASS", control, "PASS" if crc == 0 else "FAIL"))
    print("mutants: %d of %d caught" % (caught, len(MUTANTS)))
    unchanged = sha(CORE) == before and sha(spath) == before_server
    print("tracked core and server module unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
