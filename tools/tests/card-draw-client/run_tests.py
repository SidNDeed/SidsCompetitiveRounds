"""Card draw evidence (B4), client half: build the cases over the REAL
plugin/CardDrawEvidenceCore.cs and plugin/SeatEvidenceCore.cs, run them, then
check the canonical fixtures the build writes with an INDEPENDENT Python
reference (this file; it shares no code with the C# core):

  * reference_budget(input) == the client's record text, byte for byte;
  * the record is canonical JSON (json.dumps(separators=(",", ":"),
    ensure_ascii=True) of itself), at most 8192 bytes, keys in the wire
    layout order, every list entry of its declared width, every pool index
    the record names present in "cards";
  * the envelope's keys and bounds, and its sig is HMAC-SHA256 under the
    fixture key of "card-evidence:v1:" + seat + ":" + other + ":" +
    sha256(stable) + ":" + sha256(attach) + ":" + sha256(record);
  * the fixtures equal the committed fixtures/ byte for byte. No server
    parser for card records exists yet: the server half must accept these
    committed files byte for byte (CARD-DRAW-CLIENT-BUILD-NOTES.md, "Wire
    layout").

Then build mutated COPIES of either core (work/; CoreSource / SeatCoreSource
overrides; the tracked files are never written) and require each mutant's
target to FAIL and its control to PASS. The target "fixtures" is the
reference check above. Exit 0 only when everything holds.

    python tools/tests/card-draw-client/run_tests.py [--write-fixtures]
"""
import hashlib
import hmac
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PROJ = os.path.join(HERE, "CardDrawTests.csproj")
CORE = os.path.join(REPO, "plugin", "CardDrawEvidenceCore.cs")
SEAT_CORE = os.path.join(REPO, "plugin", "SeatEvidenceCore.cs")
WORK = os.path.join(HERE, "work")
GOLDEN = os.path.join(HERE, "fixtures")
FIXTURE_KEY = b"fixture-key-not-a-secret"
LIMIT = 8192

RECORD_KEYS = ["schema", "g", "ns", "pool", "prof", "po", "sc", "inc", "cards", "held0", "ph", "hd", "ap", "apx", "tot", "cost", "omit"]
POOL_STATES = ("ok", "collision", "changed", "not_run")
HASH_STATES = ("ok", "no_location", "read_failed")
SEMANTICS = "cd-sem:2"
BUILD_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._+-")
OMIT_KEYS = ["cards", "held0", "ph", "hd", "ap", "sl", "sp"]
ENVELOPE_KEYS = ["contract", "seat_steam_id", "other_steam_id", "stable_game_key", "attach_key", "record", "sig"]
END_KINDS = ("left", "other_left", "lost", "closing")
TRIM_ORDER = ["ap", "cards", "held0", "ph", "hd"]

# (name, file "core"|"seat", old text, new text, target case, control case).
# Each old text must occur exactly once in its shipped file.
MUTANTS = [
    ("census_null_as_empty", "core", "if (a == null) return null;", "if (a == null) return new List<object>();", "census", "opening"),
    ("census_digest_truncated", "core", 'return SeatEvidenceCore.Sha256Hex(Encoding.ASCII.GetBytes(censusText ?? ""));',
     'return SeatEvidenceCore.Sha256Hex(Encoding.ASCII.GetBytes(censusText ?? "")).Substring(0, 16);', "census", "opening"),
    ("collision_same_object", "core", "if (id != kv.Key) return true;", "return true;", "census", "opening"),
    ("an_wrong_role", "core", "An = _phaseW >= 0 ? AppsTo[_phaseW] : -1,", "An = _phaseW >= 0 ? AppsTo[1 - _phaseW] : -1,", "held", "census"),
    # -- fix pass 2 --
    # CD-M1: sealed at the dispatch; only completed applications
    ("seal_ignored", "core", "internal void Seal() { _sealed = true; }", "internal void Seal() { }", "seal", "census"),
    ("skipped_recorded", "core", "if (outcome != APPLY_DONE)", "if (outcome == APPLY_FAULTED)", "apps", "census"),
    ("faulted_recorded", "core", "if (outcome != APPLY_DONE)", "if (outcome == APPLY_SKIPPED)", "apps", "census"),
    ("apx_dropped", "core", ".Add(\"apx\", new long[] { Cnt(ApSkipped), Cnt(ApFaulted) })", ".Add(\"apx\", new long[] { 0, 0 })", "apps", "census"),
    # CD-M3: a first phase not captured whole emits no po / held0
    ("inc_first_po_kept", "core", '.Add("po", first ? new List<long>() : new List<long>(Po))', '.Add("po", new List<long>(Po))', "inc_first", "census"),
    ("inc_first_held_kept", "core", "List<long> h0 = first ? null : Held0[0], h1 = first ? null : Held0[1];",
     "List<long> h0 = Held0[0], h1 = Held0[1];", "inc_first", "census"),
    ("inc_masked", "core", "(long)(Inc & (INC_FIRST | INC_LOST | INC_FAULT))", "(long)(Inc & INC_FIRST)", "inc_first", "census"),
    # CD-M4: the pool state
    ("pool_state_dropped", "core", "digestOk ? PoolStateOf(PoolState) : POOL_NOT_RUN", "digestOk ? POOL_OK : POOL_NOT_RUN", "pool_states", "census"),
    ("pool_ok_without_digest", "core", "digestOk ? PoolStateOf(PoolState) : POOL_NOT_RUN", "PoolStateOf(PoolState)", "pool_states", "census"),
    # CD-M5: the identity
    ("prof_semantics_missing", "core", "SEMANTICS, Printable(Rules, RULES_CAP),", "\"\", Printable(Rules, RULES_CAP),", "prof", "census"),
    ("prof_mod_unchecked", "core", 'bool m = ModState == "ok" && ModSha != null && ModSha.Length == 64;', 'bool m = ModState == "ok";', "prof", "census"),
    ("prof_rules_uncapped", "core", "Printable(Rules, RULES_CAP),", "Rules ?? \"\",", "prof", "census"),
    ("prof_fixture_semantics", "core", 'internal const string SEMANTICS = "cd-sem:2";', 'internal const string SEMANTICS = "cd-sem:1";', "fixtures", "census"),
    # CD-M2: NOT-RUN
    ("sc_unbounded", "core", "scVerdict >= 0 && scVerdict <= 2 ? scVerdict : -1", "scVerdict", "sc_not_run", "census"),
    # F4: the true slot count beside the kept slots
    # CD-L3: a repeated slot is recorded as dealt
    ("repeat_deduped", "core", "_hand.Spawns.Add(Ix(ix));", "if (!_hand.Spawns.Contains(Ix(ix))) _hand.Spawns.Add(Ix(ix));", "repeated_slot", "census"),
    ("n_from_kept", "core", "long n = h.HasEndPick ? h.SlN : h.Spawns.Count;", "long n = sl.Count;", "true_n", "census"),
    ("gl_dropped", "core", "Gl = f.Gl == 0 || f.Gl == 1 ? f.Gl : -1,", "Gl = -1,", "held", "census"),
    ("sq_other_seat", "core", "Sq = _phaseW == 0 && f.Sq >= 0 ? f.Sq : -1,", "Sq = f.Sq,", "src_gen", "census"),
    ("foreign_counted", "core", "if (creator == 0) { _hand.Foreign = true; return; }", "if (creator == 0) { _hand.Foreign = true; }", "foreign", "census"),
    ("unresolved_spawn_dropped", "core", "_hand.Spawns.Add(Ix(ix));", "if (ix >= 0) _hand.Spawns.Add(Ix(ix));", "unresolved", "census"),
    ("slots_from_spawns", "core", "var sl = h.HasEndPick ? h.Sl : h.Spawns;", "var sl = h.Spawns;", "spawn_order", "census"),
    ("same_without_spawns", "core", "bool same = h.Spawns.Count == 0 || (h.Spawns.Count == n && SamePrefix(h.Spawns, sl));",
     "bool same = h.Spawns.Count == n && SamePrefix(h.Spawns, sl);", "endpick_only", "census"),
    ("ds_sender_ignored", "core", "if (h.Foreign || (h.HasEndPick && h.SenderOk == 0)) ds = 0;", "if (h.Foreign) ds = 0;", "sender", "census"),
    ("ds_unknown_trusted", "core", "else if (h.CreatorUnknown || !h.HasEndPick || h.SenderOk < 0) ds = -1;", "else if (!h.HasEndPick) ds = -1;", "sender", "census"),
    ("nopick_as_absent", "core", "Wp = -1, Pk = -2,", "Wp = -1, Pk = -1,", "nopick", "census"),
    ("done_not_marked", "core", "if (_phase != null) _phase[6] = 1;", "", "opening", "census"),
    ("src_counts", "core", "if (d == 1) mask |= 1L << i;", "if (d == 1) mask += 1;", "src_gen", "census"),
    ("src_tolerates_jump", "core", "else if (d != 0) return -1;", "", "src_gen", "census"),
    ("gen_opening_bound", "core", "return sq <= openingDraws ? 1 : 2;", "return sq < openingDraws ? 1 : 2;", "src_gen", "census"),
    ("sl_uncapped", "core", "for (int i = 0; i < sl.Count && i < SL_CAP; i++) slOut.Add(sl[i]);", "for (int i = 0; i < sl.Count; i++) slOut.Add(sl[i]);", "caps", "census"),
    ("n_capped", "core", "Clamp(n, 0, BIG), slOut,", "(long)slOut.Count, slOut,", "caps", "census"),
    ("held_cap_uncounted", "core", "else Held0Omit[r]++;", "", "held", "census"),
    ("tot_capped", "core", "if (_phaseW >= 0) Tot[_phaseW][0]++;", "if (_phaseW >= 0 && _phase != null) Tot[_phaseW][0]++;", "caps", "census"),
    ("apps_not_counted", "core", "if (r >= 0) { AppsTo[r]++; Tot[r][4]++; }", "if (r >= 0) { Tot[r][4]++; }", "apps", "census"),
    ("kind_dropped", "core", "kind == 1 ? 1 : 0, Clamp(vid, -1, int.MaxValue) });", "0, Clamp(vid, -1, int.MaxValue) });", "apps", "census"),
    ("name_uncapped", "core", "if (nm.Length > NAME_CAP) nm = nm.Substring(0, NAME_CAP);", "", "caps", "census"),
    ("po_uncapped", "core", "i < po.Count && i < PO_CAP;", "i < po.Count;", "po", "census"),
    ("prof_without_sha", "core", 'bool g = GameState == "ok" && GameSha != null && GameSha.Length == 64;', 'bool g = GameState == "ok";', "opening", "census"),
    ("end_any_text", "core", 'if (SeatEvidenceCore.IsEndKind(end)) o.Add("end", end);', 'if (end != null) o.Add("end", end);', "end", "census"),
    ("cards_unsorted", "core", "var kept = new SortedSet<long>();", "var kept = new HashSet<long>();", "opening", "census"),
    ("cards_miss_spawn_refs", "core", "foreach (var s in (List<long>)entry[8]) if (s >= 0) into.Add(s);", "", "spawn_order", "census"),
    # fix pass 3, CD-A16: above CARDS_CAP every entry naming an unnamed index is omitted
    # and counted, and "cards" is exactly the indices the kept entries name
    ("cards_dependents_kept", "core", "if (hr.IsSubsetOf(named)) hd.Add(e); else hdDrop++;", "hd.Add(e);", "cards_over_cap", "census"),
    ("cards_hd_drop_uncounted", "core", "if (hr.IsSubsetOf(named)) hd.Add(e); else hdDrop++;", "if (hr.IsSubsetOf(named)) hd.Add(e);", "cards_over_cap", "census"),
    ("cards_held_drop_uncounted", "core", "heldOut[r].Add(s); else heldDrop[r]++; }", "heldOut[r].Add(s); }", "cards_over_cap", "census"),
    ("cards_ap_drop_uncounted", "core", "ap.Add(e); else apDrop++; }", "ap.Add(e); }", "cards_over_cap", "census"),
    ("cards_not_rebuilt", "core", "foreach (var ix in kept)", "foreach (var ix in new SortedSet<long>(named))", "cards_over_cap", "census"),
    ("cards_named_highest", "core", "foreach (var ix in refs) { if (named.Count < CARDS_CAP)", "foreach (var ix in refs.Reverse()) { if (named.Count < CARDS_CAP)", "cards_over_cap", "census"),
    # fix pass 3, CD-M4: two readings leave the more severe state
    ("worst_pool_latest", "core", "return PoolRank(a) >= PoolRank(b) ? PoolStateOf(a) : PoolStateOf(b);", "return PoolStateOf(b);", "worst_pool", "census"),
    ("budget_tie_latest", "core", "if (counts[i] > 0 && (pick < 0 || counts[i] > counts[pick])) pick = i;",
     "if (counts[i] > 0 && (pick < 0 || counts[i] >= counts[pick])) pick = i;", "budget_ties", "census"),
    ("budget_removes_referenced_card", "core", "if (c <= 0) { lastFreeCard = i; break; }", "{ lastFreeCard = i; break; }", "budget_cards", "census"),
    ("budget_removes_first_ap", "core", "ap.RemoveAt(ap.Count - 1); lenAp.RemoveAt(lenAp.Count - 1); oAp++;",
     "addRef(((long[])ap[ap.Count - 1])[1], 1); addRef(((long[])ap[0])[1], -1); ap.RemoveAt(0); lenAp.RemoveAt(0); oAp++;", "fixtures", "census"),
    ("budget_held_own_first", "core", "if (h1 != null && h1.Count > 0)", "if (h0 == null || h0.Count == 0)", "fixtures", "census"),
    ("budget_hd_uncounted", "core", "hd.RemoveAt(hd.Count - 1); lenHd.RemoveAt(lenHd.Count - 1); oHd++;",
     "hd.RemoveAt(hd.Count - 1); lenHd.RemoveAt(lenHd.Count - 1);", "fixtures", "census"),
    ("canonical_raw_record", "core", "+ SeatEvidenceCore.Sha256Hex(Encoding.ASCII.GetBytes(recordText));", "+ recordText;", "fixtures", "census"),
    ("canonical_seat_domain", "core", 'CANON_PREFIX = "card-evidence:v1:";', 'CANON_PREFIX = "seat-evidence:v2:";', "fixtures", "census"),
    ("envelope_control_chars", "core", "if (recordText[i] > '~' || recordText[i] < ' ') return null;", "if (recordText[i] > '~') return null;", "envelope", "census"),
    ("envelope_limit_off_by_one", "core", "Encoding.UTF8.GetByteCount(recordText) > RECORD_MAX_BYTES) return null;\n            for (int i = 0; i < recordText.Length; i++) if (recordText[i] > '~' ||",
     "Encoding.UTF8.GetByteCount(recordText) >= RECORD_MAX_BYTES) return null;\n            for (int i = 0; i < recordText.Length; i++) if (recordText[i] > '~' ||", "envelope", "census"),
    ("cut_card_not_recognised", "seat", 'if (p != null && p.Route == "k") return IsCutCardBody(p.Body);', "", "end", "census"),
    ("cut_card_anchor_without_g", "seat", 'const string H = "\\\\\\"schema\\\\\\":1,\\\\\\"g\\\\\\":";', 'const string H = "\\\\\\"schema\\\\\\":1,";', "end", "census"),
    ("queue_line_drops_card_route", "seat", '(route != "e" && route != "c" && route != "k" && route != "i")', '(route != "e" && route != "c" && route != "i")', "end", "census"),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def dumps(v):
    return json.dumps(v, separators=(",", ":"), ensure_ascii=True)


def build(tag, core, seat_core):
    out = os.path.join(WORK, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep,
           "-p:CoreSource=" + core, "-p:SeatCoreSource=" + seat_core]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "CardDrawTests.dll")


def run(dll, args=()):
    r = subprocess.run(["dotnet", dll] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


# -- the independent reference -------------------------------------------------------------------

def refs_of(rec):
    """Every pool index the record names (hd sl and sp, held0, ap ix), counted."""
    c = {}
    def add(ix, d=1):
        if ix >= 0:
            c[ix] = c.get(ix, 0) + d
    for h in rec["hd"]:
        for s in h[6] + h[8]:
            add(s)
    for l in rec["held0"]:
        for s in (l or []):
            add(s)
    for a in rec["ap"]:
        add(a[1])
    return c


def reference_budget(rec, limit=LIMIT):
    """The budgeter as the design states it, by re-dumping after every step:
    while the text is over the limit, of the lists with a removable entry the
    longest (held0 = both lists together; ties: earliest in TRIM_ORDER)
    loses its LAST removable entry (cards: the last entry nothing names;
    held0: the last of [own list, other list]); omit counts each."""
    rec = json.loads(dumps(rec))
    om = rec["omit"]
    while len(dumps(rec)) > limit:
        refs = refs_of(rec)
        free = [i for i, c in enumerate(rec["cards"]) if refs.get(c[0], 0) <= 0]
        h0, h1 = rec["held0"]
        counts = {
            "ap": len(rec["ap"]),
            "cards": len(rec["cards"]) if free else -1,
            "held0": len(h0 or []) + len(h1 or []),
            "ph": len(rec["ph"]),
            "hd": len(rec["hd"]),
        }
        pick = None
        for k in TRIM_ORDER:
            if counts[k] > 0 and (pick is None or counts[k] > counts[pick]):
                pick = k
        if pick is None:
            raise ValueError("fixed fields alone exceed the limit")
        if pick == "cards":
            del rec["cards"][free[-1]]
        elif pick == "held0":
            if h1:
                h1.pop()
                om["held0"][1] += 1
                continue
            h0.pop()
            om["held0"][0] += 1
            continue
        else:
            rec[pick].pop()
        om[pick] += 1
    return dumps(rec)


def validate_record(text):
    errs = []
    if len(text.encode("ascii", "replace")) > LIMIT:
        errs.append("record over %d bytes" % LIMIT)
    try:
        rec = json.loads(text)
    except ValueError as e:
        return ["record not JSON: %s" % e]
    if dumps(rec) != text:
        errs.append("record is not canonical")
    keys = list(rec.keys())
    want = list(RECORD_KEYS)
    if "end" in rec:
        want.insert(2, "end")
        if rec["end"] not in END_KINDS:
            errs.append("end kind %r" % rec["end"])
    if keys != want:
        errs.append("keys %s" % keys)
        return errs
    if rec["schema"] != 1:
        errs.append("schema")
    pool = rec["pool"]
    if not (isinstance(pool, list) and len(pool) == 3 and len(pool[1]) in (0, 64) and pool[2] in POOL_STATES
            and (pool[2] == "not_run" or len(pool[1]) == 64)):
        errs.append("pool")
    prof = rec["prof"]
    if not (isinstance(prof, list) and len(prof) == 9):
        errs.append("prof arity")
    else:
        for i in (0, 2):
            if not (prof[i + 1] in HASH_STATES and (len(prof[i]) == 64) == (prof[i + 1] == "ok")
                    and (prof[i] == "" or all(c in "0123456789abcdef" for c in prof[i]))):
                errs.append("prof hash %d" % i)
        for i, cap in ((4, 16), (5, 16), (6, 12)):
            if len(prof[i]) > cap or not set(prof[i]) <= BUILD_CHARS:
                errs.append("prof build %d" % i)
        if prof[7] != SEMANTICS:
            errs.append("prof semantics")
        if len(prof[8]) > 32 or any(c < " " or c > "~" or c in '"\\' for c in prof[8]):
            errs.append("prof rules")
    if len(rec["po"]) > 8 or any(p not in (-1, 0, 1) for p in rec["po"]):
        errs.append("po")
    if not (len(rec["sc"]) == 2 and rec["sc"][0] in (-1, 0, 1) and rec["sc"][1] in (-1, 0, 1, 2)):
        errs.append("sc")
    if not (isinstance(rec["inc"], int) and 0 <= rec["inc"] <= 7):
        errs.append("inc")
    elif rec["inc"] & 1 and (rec["po"] != [] or rec["held0"] != [None, None] or rec["omit"]["held0"] != [0, 0]):
        errs.append("inc first: po / held0 emitted for a first phase not captured")
    if not (len(rec["apx"]) == 2 and all(isinstance(v, int) and v >= 0 for v in rec["apx"])):
        errs.append("apx")
    widths = {"cards": 3, "ph": 7, "hd": 18, "ap": 4}
    caps = {"cards": 128, "ph": 40, "hd": 40, "ap": 64}
    for k, w in widths.items():
        if len(rec[k]) > caps[k]:
            errs.append("%s over its cap" % k)
        for e in rec[k]:
            if len(e) != w:
                errs.append("%s entry width %d" % (k, len(e)))
                break
    for h in rec["hd"]:
        if len(h[6]) > 16 or len(h[8]) > 16:
            errs.append("hd slot list over 16")
    ixs = [c[0] for c in rec["cards"]]
    if ixs != sorted(set(ixs)):
        errs.append("cards not ascending and unique")
    missing = [ix for ix in refs_of(rec) if ix not in set(ixs)]
    if missing:
        errs.append("referenced cards missing: %s" % missing[:5])
    if len(rec["held0"]) != 2 or any(l is not None and len(l) > 64 for l in rec["held0"]):
        errs.append("held0")
    if len(rec["tot"]) != 2 or any(len(t) != 7 for t in rec["tot"]):
        errs.append("tot")
    if len(rec["cost"]) != 6 or any(len(c) != 5 for c in rec["cost"]):
        errs.append("cost")
    if list(rec["omit"].keys()) != OMIT_KEYS or len(rec["omit"]["held0"]) != 2:
        errs.append("omit keys")
    return errs


def validate_envelope(env_text, record_text):
    errs = []
    env = json.loads(env_text)
    if dumps(env) != env_text:
        errs.append("envelope not canonical")
    if list(env.keys()) != ENVELOPE_KEYS:
        errs.append("envelope keys %s" % list(env.keys()))
        return errs
    if env["contract"] != 2:
        errs.append("contract")
    if env["record"] != record_text:
        errs.append("envelope record differs from the record text")
    if not env["attach_key"].startswith(env["stable_game_key"] + "_r"):
        errs.append("attach key")
    canon = "card-evidence:v1:%s:%s:%s:%s:%s" % (
        env["seat_steam_id"], env["other_steam_id"],
        hashlib.sha256(env["stable_game_key"].encode("ascii")).hexdigest(),
        hashlib.sha256(env["attach_key"].encode("ascii")).hexdigest(),
        hashlib.sha256(env["record"].encode("ascii")).hexdigest())
    want = hmac.new(FIXTURE_KEY, canon.encode("utf-8"), hashlib.sha256).hexdigest()
    if env["sig"] != want:
        errs.append("sig does not verify under the card-evidence:v1 canonical")
    return errs


def fixture_check(dll, tag, verbose, write_golden=False):
    out = os.path.join(WORK, tag, "fixtures")
    rc, txt = run(dll, ["fixtures", out])
    lines = []
    if rc != 0:
        return False, ["fixtures: generator exit %d %s" % (rc, txt)]
    names = open(os.path.join(out, "cases.txt"), "rb").read().decode("ascii").split()
    ok = True
    for n in names:
        inp = open(os.path.join(out, n + ".input.json"), "rb").read().decode("ascii")
        rec = open(os.path.join(out, n + ".record.txt"), "rb").read().decode("ascii")
        env = open(os.path.join(out, n + ".envelope.json"), "rb").read().decode("ascii")
        errs = []
        ref = reference_budget(json.loads(inp))
        if ref != rec:
            i = next((k for k in range(min(len(ref), len(rec))) if ref[k] != rec[k]), min(len(ref), len(rec)))
            errs.append("reference budget differs at byte %d: ref ...%s... client ...%s..." % (i, ref[max(0, i - 40):i + 40], rec[max(0, i - 40):i + 40]))
        errs += validate_record(rec)
        errs += validate_envelope(env, rec)
        full = len(dumps(json.loads(inp)))
        omitted = json.loads(rec)["omit"]
        lines.append("  fixture %s: input %d bytes, record %d bytes, omit %s: %s" % (
            n, full, len(rec), dumps(omitted), "PASS" if not errs else "FAIL " + "; ".join(errs)))
        ok = ok and not errs
    files = sorted(os.listdir(out))
    if write_golden:
        os.makedirs(GOLDEN, exist_ok=True)
        for f in files:
            open(os.path.join(GOLDEN, f), "wb").write(open(os.path.join(out, f), "rb").read())
        lines.append("  wrote %d golden files to %s" % (len(files), GOLDEN))
    gold = sorted(os.listdir(GOLDEN)) if os.path.isdir(GOLDEN) else []
    if gold != files:
        ok = False
        lines.append("  golden file set differs: %s vs %s" % (gold, files))
    else:
        diff = [f for f in files if open(os.path.join(GOLDEN, f), "rb").read() != open(os.path.join(out, f), "rb").read()]
        if diff:
            ok = False
            lines.append("  differs from the committed fixtures: %s" % diff)
        else:
            lines.append("  %d files equal the committed fixtures byte for byte" % len(files))
    return ok, lines


def main():
    write = "--write-fixtures" in sys.argv
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    before = {CORE: sha(CORE), SEAT_CORE: sha(SEAT_CORE)}
    for p, h in before.items():
        print(os.path.relpath(p, REPO).replace(os.sep, "/"), "sha256", h)
    ok = True

    dll = build("base", CORE, SEAT_CORE)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    rc, out = run(dll)
    print(out)
    ok = ok and rc == 0
    fok, lines = fixture_check(dll, "base", True, write)
    print("\n".join(lines))
    print("fixture reference check:", "PASS" if fok else "FAIL")
    ok = ok and fok

    raws = {}
    for key, path in (("core", CORE), ("seat", SEAT_CORE)):
        raws[key] = open(path, "rb").read().decode("utf-8")
    caught = 0
    for name, which, old, new, target, control in MUTANTS:
        raw = raws[which]
        nl = "\r\n" if "\r\n" in raw else "\n"
        o, n = old.replace("\n", nl), new.replace("\n", nl)
        count = raw.count(o)
        if count != 1:
            print("BAD mutant %s: anchor occurs %d times" % (name, count))
            ok = False
            continue
        path = os.path.join(WORK, "mut_" + name + ".cs")
        open(path, "wb").write(raw.replace(o, n).encode("utf-8"))
        mdll = build("mut_" + name, path if which == "core" else CORE, path if which == "seat" else SEAT_CORE)
        if mdll is None:
            print("BAD mutant %s: does not build" % name)
            ok = False
            continue
        if target == "fixtures":
            t_ok, _ = fixture_check(mdll, "mut_" + name, False)
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

    # negative control of the reference itself: a one-byte change to a good
    # record must fail the reference comparison and the signature check
    good = os.path.join(WORK, "base", "fixtures")
    rec = open(os.path.join(good, "full_game.record.txt"), "rb").read().decode("ascii")
    env = open(os.path.join(good, "full_game.envelope.json"), "rb").read().decode("ascii")
    bad = rec.replace('"g":1', '"g":2', 1)
    neg = bad != rec and bool(validate_envelope(env.replace(dumps(rec)[1:-1], dumps(bad)[1:-1]), bad))
    neg = neg and bool(validate_record(rec[:-1]))
    print("negative control (altered record refused by the reference):", neg)
    ok = ok and neg

    unchanged = all(sha(p) == h for p, h in before.items())
    print("tracked cores unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
