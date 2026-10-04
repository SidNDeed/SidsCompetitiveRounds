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

Amended B7 (SEAT-EVIDENCE-CONTRACT-V2.md, AMENDMENT 2026-10-04: `reset` at
hit_sent index 9, none / keyed / unkeyed). The server module this compares
against predates the amendment, so B7 is checked by b7_check below, written
from the amended contract text; every hit_sent entry the client emits goes
through it (every fixture record, and b7_states.json, the state space), the
refused combinations (b7_negative.json) must each be refused with the field
the contract names, and each rule of b7_check has a mutant. The server's own
check_record then reads the record with hit_sent cut back to nine elements.

Contract A2 (hit_recv is path 0 only; a path-0 key has pid 0) is checked by
a2_check on every fixture record, by the field names the amended server
uses (hit_recv.path, hit_recv.pid), with two core mutants.

The AMENDED server (the seat evidence server lane, B7 and A2 in its own
parser; --amended-root, default the sibling scr-wt-seat-evidence-server-v2,
read by path, never written) is then run on the unmutated build: its
parse_envelope + parse_record must accept every fixture record with the
client's exact bytes and verify_sig its signature, and the client's budgeter
over its shared budget fixture (backend/tests/fixtures/seat_evidence_budget.json)
must produce the fixture's sha256 and byte count. A missing amended tree is
a FAIL, never a skip. The fixtures the unmutated build writes must equal the
committed set in server_fixtures/ byte for byte (pinned_check), so the files
handed to the server lane are the files this run checked.

    python tools/tests/seat-evidence-client/run_tests.py [--server-root DIR] [--amended-root DIR]
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
DEFAULT_AMENDED = os.path.join(os.path.dirname(REPO), "scr-wt-seat-evidence-server-v2")
PINNED = os.path.join(HERE, "server_fixtures")
FIXTURE_KEY = "fixture-key-not-a-secret"

# (name, old text, new text, target case, control case). Each old text must
# occur exactly once in the shipped file.
MUTANTS = [
    ("json_upper_hex", 'ToString("x4", CultureInfo.InvariantCulture)', 'ToString("X4", CultureInfo.InvariantCulture)', "json", "budget"),
    ("budget_tie_latest", "if (longest < 0 || lists[i].Count > lists[longest].Count) longest = i;",
     "if (longest < 0 || lists[i].Count >= lists[longest].Count) longest = i;", "budget", "json"),
    ("budget_removes_first", "lists[longest].RemoveAt(lists[longest].Count - 1);\n                entryLen[longest].RemoveAt(entryLen[longest].Count - 1);",
     "lists[longest].RemoveAt(0);\n                entryLen[longest].RemoveAt(0);", "server", "json"),
    # fix pass 5, amended B7: one factory maps the copy's state to the five fields
    ("hitsent_last_kind_zero", "if (ms < 0) return new LastReset(-1, 0, -1, 0, NONE);", "if (ms < 0) return new LastReset(-1, 0, 0, 0, NONE);",
     "entries", "json"),
    ("lastreset_none_with_since", "if (ms < 0) return new LastReset(-1, 0, -1, 0, NONE);", "if (ms < 0) return new LastReset(0, 0, -1, 0, NONE);",
     "server", "json"),
    ("lastreset_unkeyed_labelled_none", "return new LastReset(ms, 0, -1, 0, UNKEYED);", "return new LastReset(ms, 0, -1, 0, NONE);",
     "server", "json"),
    # merge pass 6, contract A2: the hit_recv entry factory writing path 1, or a
    # pid, must be refused by a2_check in the fixture comparison
    ("hit_recv_entry_path1", "return new long[] { Clamp(path, 0, 1), stamp, Clamp(pid, 0, I32_MAX), Clamp(ord, 0, 255), arr,",
     "return new long[] { 1, stamp, Clamp(pid, 0, I32_MAX), Clamp(ord, 0, 255), arr,", "server", "json"),
    ("hit_recv_entry_pid", "return new long[] { Clamp(path, 0, 1), stamp, Clamp(pid, 0, I32_MAX), Clamp(ord, 0, 255), arr,",
     "return new long[] { Clamp(path, 0, 1), stamp, 7, Clamp(ord, 0, 255), arr,", "server", "json"),
    ("lastreset_unkeyed_written_none","return new LastReset(ms, 0, -1, 0, UNKEYED);", "return new LastReset(-1, 0, -1, 0, NONE);",
     "b7", "json"),
    ("lastreset_key_ignored", "if (hasLast) return new LastReset(", "if (false) return new LastReset(", "b7", "json"),
    ("lastreset_keyed_without_key", "(int)Clamp(lastKind, 0, 9), (int)Clamp(lastOrd, 0, 255), KEYED);",
     "-1, (int)Clamp(lastOrd, 0, 255), KEYED);", "server", "json"),
    ("lastreset_unkeyed_keeps_tb", "return new LastReset(ms, 0, -1, 0, UNKEYED);", "return new LastReset(ms, lastTb, -1, 0, UNKEYED);",
     "server", "json"),
    ("hitsent_reset_dropped", "r.Tb, r.Kind, r.Ord, r.Reset };", "r.Tb, r.Kind, r.Ord };", "server", "json"),
    ("lastreset_default_since_zero", "internal long Since { get { return _sinceP1 - 1; } }", "internal long Since { get { return _sinceP1; } }",
     "b7", "json"),
    ("since_rounds", "double ms = Math.Floor((double)sinceBlockS * 1000.0);", "double ms = Math.Round((double)sinceBlockS * 1000.0);", "entries", "decide"),
    ("since_no_never", "if (!everReset || float.IsNaN(sinceBlockS)) return -1;", "if (float.IsNaN(sinceBlockS)) return -1;", "entries", "json"),
    ("drift_most_delayed", "if (!bestY.TryGetValue(b, out cur) || y > cur)", "if (!bestY.TryGetValue(b, out cur) || y < cur)", "congestion", "drift"),
    ("drift_sign", "double slope = sxy / sxx;", "double slope = -sxy / sxx;", "drift", "congestion"),
    ("drift_raw_jumps", "double r = ys[i] - (icept + slope * xs[i]);", "double r = ys[i];", "drift", "congestion"),
    ("bucket_truncates", "if ((x % d != 0) && (x < 0)) q--;", "", "buckets", "cadence"),
    ("cadence_counts_reorder", "if (gap <= 0) return;", "if (gap == 0) return;", "cadence", "buckets"),
    ("ordinal_uncapped", "return n > 255 ? 255 : n;", "return n;", "ordinals", "window"),
    # fix pass 2, F4: the hook-side structures are hard-capped
    ("ordinals_never_forget", "if (_seen.Count >= KEEP) _seen.Remove(_ring[_head]);", "", "ordinals", "window"),
    ("recent_uncapped", "if (RecentBlocks.Count > RECENT_CAP) RecentBlocks.RemoveAt(0);", "", "window_caps", "window"),
    ("pending_uncapped", "if (Pending.Count > PENDING_CAP) Pending.RemoveAt(0);", "", "window_caps", "window"),
    # fix pass 4, F4: the capped map refuses and counts a new key at the cap, never a present one
    ("capped_map_inserts_past_cap", "if (_d.Count >= Cap && !_d.ContainsKey(key)) { Refused++; return false; }", "", "capped_map", "window"),
    ("capped_map_uncounted", "{ Refused++; return false; }", "{ return false; }", "capped_map", "window"),
    ("capped_map_refuses_present", "if (_d.Count >= Cap && !_d.ContainsKey(key))", "if (_d.Count >= Cap)", "capped_map", "window"),
    ("capped_map_admit_uncounted", "if (_d.Count < Cap || _d.ContainsKey(key)) return true;\n                Refused++;",
     "if (_d.Count < Cap || _d.ContainsKey(key)) return true;", "capped_map", "window"),
    ("capped_map_cap_zero", "Cap = cap < 1 ? 1 : cap;", "Cap = cap;", "capped_map", "window"),
    # fix pass 4, F4: one forward pass keeps both lists in arrival order
    ("block_order_admitted", "if (d >= LO && d <= HI) admitted.Add(h);", "if (d >= LO && d <= HI) admitted.Insert(0, h);", "window_block_order", "ordinals"),
    ("block_order_pending", "if (kept < n) Pending.RemoveRange(kept, n - kept);", "if (kept < n) Pending.RemoveRange(0, n - kept);",
     "window_block_order", "ordinals"),
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


# -- amended B7, written from SEAT-EVIDENCE-CONTRACT-V2.md (section 2.4 hit_sent row and B7 AMENDMENT 2026-10-04) --
# hit_sent = [path, stamp, pid, ord, since_ms, blocked, last_tb, last_kind, last_ord, reset], exactly ten integers;
# reset 0 none (since -1, last [0,-1,0]), 1 keyed (since 0..600000, last_kind 0..9), 2 unkeyed (since 0..600000,
# last [0,-1,0]); every other combination refused, the FIRST failing rule named, in the contract's order.
I32 = (-2 ** 31, 2 ** 31 - 1)
HIT_SENT_BOUNDS = [(0, 1), I32, (0, 2 ** 31 - 1), (0, 255), (-1, 600000), (0, 1), I32, (-1, 9), (0, 255), (0, 2)]
SENTINEL = [0, -1, 0]
B7_RULES = ["shape", "reset_none_since", "reset_none_last", "reset_keyed_since", "reset_keyed_last",
            "reset_unkeyed_since", "reset_unkeyed_last"]


def _is_int(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def b7_check(e, off=()):
    """None when the amended contract admits the entry, else the field it
    names. `off` switches rules off (the per-rule mutants only)."""
    if "shape" not in off:
        if not isinstance(e, list) or len(e) != 10 or not all(_is_int(v, lo, hi) for v, (lo, hi) in zip(e, HIT_SENT_BOUNDS)):
            return "hit_sent"
    if not isinstance(e, list) or len(e) < 10:
        return None                               # shape switched off: nothing further to read
    since, last, reset = e[4], list(e[6:9]), e[9]
    if reset == 0:
        if "reset_none_since" not in off and since >= 0:
            return "hit_sent.reset_none_since"
        if "reset_none_last" not in off and last != SENTINEL:
            return "hit_sent.reset_none_last"
    elif reset == 1:
        if "reset_keyed_since" not in off and since == -1:
            return "hit_sent.reset_keyed_since"
        if "reset_keyed_last" not in off and last[1] == -1:
            return "hit_sent.reset_keyed_last"
    elif reset == 2:
        if "reset_unkeyed_since" not in off and since == -1:
            return "hit_sent.reset_unkeyed_since"
        if "reset_unkeyed_last" not in off and last != SENTINEL:
            return "hit_sent.reset_unkeyed_last"
    return None


def b7_fixture_check(d, off=()):
    """(ok, lines) over the B7 fixtures in d: every state-space entry
    admitted, every refused combination refused with exactly its field."""
    lines, ok = [], True
    states = json.loads(open(os.path.join(d, "b7_states.json"), encoding="ascii").read())
    bad = [(i, e, b7_check(e, off)) for i, e in enumerate(states) if b7_check(e, off) is not None]
    per = [0, 0, 0]
    for e in states:
        if isinstance(e, list) and len(e) == 10 and e[9] in (0, 1, 2):
            per[e[9]] += 1
    good = not bad and len(states) > 0 and all(per)
    lines.append("%s b7 states: %d entries admitted=%d (none %d, keyed %d, unkeyed %d)%s" % (
        "OK " if good else "BAD", len(states), len(states) - len(bad), per[0], per[1], per[2],
        "" if not bad else "; first refused #%d %s: %s" % (bad[0][0], bad[0][1], bad[0][2])))
    ok = ok and good
    neg = json.loads(open(os.path.join(d, "b7_negative.json"), encoding="ascii").read())
    wrong = [(f, e, b7_check(e, off)) for f, e in neg if b7_check(e, off) != f]
    named = sorted(set(f for f, _ in neg))
    good = not wrong and set("hit_sent." + r for r in B7_RULES[1:]) <= set(named) and "hit_sent" in named
    lines.append("%s b7 refused: %d combinations, each refused with its field: %s; fields %s%s" % (
        "OK " if good else "BAD", len(neg), not wrong, ",".join(named),
        "" if not wrong else "; first wrong %s want %s got %s" % (wrong[0][1], wrong[0][0], wrong[0][2])))
    return ok and good, lines


def a2_check(rec):
    """None when every hit_recv entry has path 0 and pid 0 (contract A2: the
    victim never lists a path-1 hit; a path-0 key carries pid 0), else the
    field the amended server names for the first entry that breaks it."""
    for e in rec.get("hit_recv", []) if isinstance(rec, dict) else []:
        if isinstance(e, list) and len(e) > 2:
            if e[0] != 0:
                return "hit_recv.path"
            if e[2] != 0:
                return "hit_recv.pid"
    return None


def amended_parse(sev, env):
    """parse_record with amendment A1 and the amended B7: an "end" key, when
    present, must sit right after "rounds" and name a known kind; every
    hit_sent entry must pass b7_check (the amended contract); the rest is the
    reference's own check_record, unchanged, over the record with hit_sent
    cut back to the nine elements that module knows."""
    rec = json.loads(env["record_text"], parse_float=sev._refuse_float, parse_constant=sev._refuse_float)
    if not isinstance(rec, dict):
        sev.check_record(rec)
        return rec
    f = a2_check(rec)
    if f is not None:
        raise sev.EvidenceRefused(422, f)
    hs = rec.get("hit_sent")
    if isinstance(hs, list):
        for e in hs:
            f = b7_check(e)
            if f is not None:
                raise sev.EvidenceRefused(422, f)
    view = dict(rec)
    if isinstance(hs, list):
        view["hit_sent"] = [e[:9] for e in hs]
    if "end" in rec:
        keys = list(rec.keys())
        if keys.index("end") != keys.index("rounds") + 1 or rec["end"] not in END_KINDS:
            raise sev.EvidenceRefused(422, "end")
        sev.check_record({k: v for k, v in view.items() if k != "end"})
    else:
        sev.check_record(view)
    return rec


def server_check(sev, dll, tag, verbose):
    """The comparison against the server's own functions. Returns (ok, lines).
    budget_record (shape-agnostic) is compared unchanged, through the A1
    wrapper when "end" is present; every record is read through amended_parse
    (A1 and the amended B7 over every hit_sent entry) and each line says what
    the unamended server answers; then the B7 state-space and refused-
    combination fixtures go through b7_fixture_check."""
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
            rec = amended_parse(sev, env)
            n_hs = len(rec.get("hit_sent", []))
            n_hr = len(rec.get("hit_recv", []))
            try:
                sev.parse_record(env)
                note = ", unamended server: accepts"
            except Exception as ex:  # expected until the server adopts A1 and the amended B7
                note = ", unamended server: refuses %s" % getattr(ex, "field", ex)
            sig_ok = sev.verify_sig(FIXTURE_KEY, env)
            text_ok = env["record_bytes"] == mine
            good = same and sig_ok and text_ok
            lines.append("%s %s: %d bytes, %sbudget_record equal=%s, parse+check ok (A2: %d hit_recv entries path 0 pid 0; B7 amended: %d hit_sent entries admitted), verify_sig=%s, envelope record equal=%s%s"
                         % ("OK " if good else "BAD", name, len(mine), "A1 " if has_end else "", same, n_hr, n_hs, sig_ok, text_ok, note))
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
    try:
        bok, blines = b7_fixture_check(d)
    except Exception as ex:
        bok, blines = False, ["BAD b7 fixtures: %s %s" % (type(ex).__name__, ex)]
    lines.extend(blines)
    ok = ok and bok
    return ok, lines


def pinned_check():
    """The committed server-comparison fixtures (server_fixtures/, the set the
    server lane copies into backend/tests/fixtures/seat_evidence_client_b7/)
    equal, file for file and byte for byte, what the unmutated build just
    wrote into work/base/fixtures. A difference in either direction FAILS."""
    d = os.path.join(WORK, "base", "fixtures")
    have, made = set(os.listdir(PINNED)), set(os.listdir(d))
    ok = have == made and len(have) > 0
    for f in sorted(have | made):
        a = sha(os.path.join(PINNED, f)) if f in have else "absent"
        b = sha(os.path.join(d, f)) if f in made else "absent"
        ok = ok and a == b
        print("%s pinned %s: committed %s built %s" % ("OK " if a == b else "BAD", f, a[:16], b[:16]))
    return ok


def amended_check(root, dll):
    """The amended server's own parser and budget fixture over the unmutated
    build's fixtures (written by server_check into work/base/fixtures).
    Prints one line per check; True only when every one holds."""
    api = os.path.join(root, "backend", "api")
    path = os.path.join(api, "seat_evidence.py")
    bfx = os.path.join(root, "backend", "tests", "fixtures", "seat_evidence_budget.json")
    if not (os.path.isfile(path) and os.path.isfile(bfx)):
        print("BAD amended server: %s or its budget fixture is missing (not run)" % path)
        return False
    shead = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    before = (sha(path), sha(bfx))
    sys.path.insert(0, api)                       # its sibling imports (review_measures, review_rules)
    try:
        spec = importlib.util.spec_from_file_location("amended_seat_evidence", path)
        sev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sev)
    finally:
        sys.path.remove(api)
    print("amended server", shead, path, "sha256", before[0])
    ok = True
    d = os.path.join(WORK, "base", "fixtures")
    names = open(os.path.join(d, "cases.txt"), encoding="ascii").read().split()
    for name in names:
        p = lambda ext: os.path.join(d, name + ext)  # noqa: E731
        mine = open(p(".record.txt"), "rb").read()
        try:
            env = sev.parse_envelope(json.loads(open(p(".envelope.json"), encoding="ascii").read()))
            rec = sev.parse_record(env)            # the whole check: A2 and the amended B7 included
            good = env["record_bytes"] == mine and sev.verify_sig(FIXTURE_KEY, env)
            print("%s amended %s: parse_record accepts, %d hit_recv, %d hit_sent, record bytes equal and signature verified=%s"
                  % ("OK " if good else "BAD", name, len(rec["hit_recv"]), len(rec["hit_sent"]), good))
        except Exception as ex:
            good = False
            print("BAD amended %s: refused %s %s" % (name, type(ex).__name__, getattr(ex, "field", ex)))
        ok = ok and good
    fx = json.loads(open(bfx, encoding="utf-8").read())
    out = os.path.join(WORK, "base", "budget_fixture.record.txt")
    rc, txt = run(dll, ["budgetfile", bfx, out])
    if rc != 0:
        print("BAD budget fixture: budgetfile exit %d %s" % (rc, txt[-300:]))
        return False
    got = open(out, "rb").read()
    good = hashlib.sha256(got).hexdigest() == fx["sha256"] and len(got) == fx["bytes"]
    print("%s budget fixture %s: the client budgeter writes %d bytes sha256 %s; the fixture pins %d bytes sha256 %s"
          % ("OK " if good else "BAD", os.path.basename(bfx), len(got), hashlib.sha256(got).hexdigest(), fx["bytes"], fx["sha256"]))
    ok = ok and good
    unchanged = (sha(path), sha(bfx)) == before
    print("amended server module and budget fixture unchanged:", unchanged)
    return ok and unchanged and len(names) > 0


def main():
    root = DEFAULT_SERVER
    if "--server-root" in sys.argv:
        root = sys.argv[sys.argv.index("--server-root") + 1]
    amended_root = DEFAULT_AMENDED
    if "--amended-root" in sys.argv:
        amended_root = sys.argv[sys.argv.index("--amended-root") + 1]
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
    fok = pinned_check()
    print("committed server fixtures:", "PASS" if fok else "FAIL")
    ok = ok and fok
    aok = amended_check(amended_root, dll)
    print("amended server conformance:", "PASS" if aok else "FAIL")
    ok = ok and aok

    # one mutant per rule of b7_check: that rule switched off must let a refused combination through (target:
    # the refused list FAILS) while every state-space entry stays admitted (control PASSES)
    bd = os.path.join(WORK, "base", "fixtures")
    rcaught = 0
    for rule in B7_RULES:
        try:
            _, rl = b7_fixture_check(bd, off=(rule,))
            states_ok, neg_ok = rl[0].startswith("OK "), rl[1].startswith("OK ")
        except Exception as ex:
            states_ok, neg_ok, rl = False, True, ["error %s" % ex, ""]
        hit = (not neg_ok) and states_ok
        rcaught += hit
        ok = ok and hit
        print("%s b7 rule mutant %s off: target refused-list=%s; control states=%s" % (
            "CAUGHT" if hit else "MISSED", rule, "FAIL" if not neg_ok else "PASS", "PASS" if states_ok else "FAIL"))
    print("b7 rule mutants: %d of %d caught" % (rcaught, len(B7_RULES)))

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
