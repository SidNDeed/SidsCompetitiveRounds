"""Combat evidence scenario harness (fix pass 2: M1, G1 red/green, G2, A1, L1, A14).

Builds the REAL plugin/CombatEvidence.cs and CombatEvidencePerf.cs with the
REAL core, wire and SeatEvidenceCore against Stubs.cs (ScenarioTests.csproj)
and drives Program.cs's scripted 1v1 once from each seat. Then:

  * SERVER reference (the server worktree's combat_measures.py, read by path,
    never written, no bytecode): every unamended record passes check_record,
    budget_record reproduces the client's bytes, section_faults is empty, and
    the two seats' records PAIR through pushes, chains, velocity_changes and
    deaths with the values the script implies;
  * G1 checks on the records: M2 (aim against the body), M3 (a locked gun's
    spread and projectiles), M4 (repeat ordinals), M5 (own block keys), M6
    (oldest contact first);
  * the capability bits: all four with every producer attached; a dropped
    patch class withholds its section (and the boot line says N-1/18); a hit
    by a projectile this seat never saw initialised voids push and chain;
  * M1: one throwing build (a throw planted at the head of every collector
    entry's contained body, armed per cost row at run time). For each of the
    twenty rows: the game witness digest equals the unplanted run's, the row
    shows calls > 0 and faults == calls, no other row faults, no exception
    leaves a hook, and the sections fed by that row lose their bit;
  * A1 (client side): the amended records (fixtures-a1/) carry the A1 part,
    their drop counters and totals; the unamended records carry none of it;
  * A14: the menu measurement (A/A, planted control) on the stub clock, and
    a mutant without the plant that must report detected=no;
  * per-collector mutants (copies, never the tracked file): each must turn
    its target check red while a control check stays green.

    python run_scenario.py [--server-root DIR] [--red COMMIT] [--write-fixtures]

--red COMMIT builds that commit's CombatEvidence.cs and core instead and
reports which G1 checks are red there (a development run: it is cited only
as the red half of red-then-green).
"""
import hashlib
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PROJ = os.path.join(HERE, "ScenarioTests.csproj")
PLUGIN = os.path.join(REPO, "plugin")
SOURCE = os.path.join(PLUGIN, "CombatEvidence.cs")
PERF = os.path.join(PLUGIN, "CombatEvidencePerf.cs")
CORE = os.path.join(PLUGIN, "CombatEvidenceCore.cs")
WORK = os.path.join(HERE, "work")
DEFAULT_SERVER = os.path.join(os.path.dirname(REPO), "scr-wt-combat-evidence-server")
TRACKED = [SOURCE, PERF, CORE, os.path.join(PLUGIN, "CombatEvidenceWire.g.cs"), os.path.join(PLUGIN, "SeatEvidenceCore.cs")]

ROWS = ["K1", "K2", "K3", "K4", "K5", "N1", "N2", "N3", "N4", "N5", "N6", "N7", "T", "P1", "D1", "X1", "S1", "H1", "E1", "RX"]
ENTRIES = {"RpcSent": "K1", "InitEnter": "K2", "InitExit": "K2", "HitEnter": "K3", "BlockDone": "K4", "Dealt": "K5",
           "AttackEnter": "N1", "AttackExit": "N1", "ReloadEnter": "N2", "TargetBounce": "N3", "EdgeBounce": "N4",
           "SyncRead": "N5", "TryBlockEnter": "N6", "TryBlockExit": "N6", "ContactEnter": "N7", "Tick": "T",
           "ForceEnter": "P1", "ForceExit": "P1", "DamageEnter": "D1", "DamageExit": "D1", "Die": "X1",
           "FindTarget": "S1", "HitExit": "H1", "EdgeBounceExit": "E1", "RxSample": "RX"}
# the rows each section's rows depend on (CombatEvidence.SECTION_ROWS); bits push 1, vchg 2, chain 4, death 8
SECTION_ROWS = {1: ["K2", "K3", "H1", "P1", "T"], 2: ["K2", "K3", "H1", "N3", "N4", "E1", "S1"],
                4: ["K1", "K2", "K3", "H1", "D1", "N7", "N1", "T"], 8: ["K2", "K3", "D1", "X1"]}
CAPS_A1, CAPS_RX = 32, 16
SEAT = {1: "76561190000000001", 2: "76561190000000002"}

# the script's facts (Program.cs Script)
A_SHOTS = [1101, 1102, 1103]
PRESS_TB = [102000, 107200]
M6_STAMPS = [105100, 105150]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def read(path):
    return open(path, "rb").read().decode("utf-8").replace("\r\n", "\n")


def build(tag, combat=None, perf=None, core=None):
    out = os.path.join(WORK, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep]
    if combat:
        cmd.append("-p:CombatSource=" + combat)
    if perf:
        cmd.append("-p:PerfSource=" + perf)
    if core:
        cmd.append("-p:CoreSource=" + core)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-4000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "CombatScenario.dll")


def run(dll, tag, seat, *opts):
    path = os.path.join(WORK, "out_%s_s%d.txt" % (tag, seat))
    if os.path.exists(path):
        os.remove(path)
    r = subprocess.run(["dotnet", dll, str(seat), path] + list(opts), capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(path):
        return {"fail": "exit %d %s" % (r.returncode, (r.stdout + r.stderr)[-1500:])}
    res = {"err": [], "env": [], "log": [], "cost": {}, "digest": None, "dropix": None}
    for ln in read(path).split("\n"):
        kind, _, rest = ln.partition(" ")
        if kind == "ERR":
            res["err"].append(rest)
        elif kind == "ENV":
            res["env"].append(rest)
        elif kind == "LOG":
            res["log"].append(rest)
        elif kind == "COST":
            i, c, f = rest.split()
            res["cost"][int(i)] = (int(c), int(f))
        elif kind == "DIGEST":
            res["digest"] = rest
        elif kind == "DROPIX":
            res["dropix"] = [int(x) for x in rest.split()]
    res["text"] = [json.loads(e)["record"] for e in res["env"]]
    res["rec"] = [json.loads(t) for t in res["text"]]
    return res


def load_server(root):
    sys.path.insert(0, os.path.join(root, "backend", "api"))
    import combat_measures
    return combat_measures


# -- the checks: name -> fn(cm, s1, s2) -> (ok, detail); s1/s2 the two seats' unamended records ---------

def f(cm, key, e, name):
    return e[cm.IX[key][name]]


def chk_server(cm, s1, s2):
    bad = []
    for n, (rec, text) in (("s1", s1), ("s2", s2)):
        try:
            cm.check_record(rec)
        except Exception as ex:
            bad.append("%s check_record %s" % (n, ex))
            continue
        if cm.budget_record(rec) != text:
            bad.append("%s budget_record differs from the client's bytes" % n)
        sf = cm.section_faults(rec)
        if sf:
            bad.append("%s section_faults %s" % (n, sf))
        if rec["caps"] != 15:
            bad.append("%s caps %d" % (n, rec["caps"]))
    return not bad, "; ".join(bad) or "both records: check_record ok, budget_record reproduces the bytes, no section fault, caps 15"


def chk_pushes(cm, s1, s2):
    a, b = s1[0], s2[0]
    rows = cm.pushes(b, a) + cm.pushes(a, b)
    keys = sorted((r["pid"], r["cord"]) for r in rows)
    bad = [r for r in rows if r["not_run"] is not None or any(r["d_" + k] != 0 for k in ("fx", "fy", "vax", "vay", "pax", "pay"))]
    moved = [r for r in rows if r["self"]["pax"] == r["self"]["pbx"] and r["self"]["pay"] == r["self"]["pby"]]
    ok = keys == [(1101, 0), (1103, 0), (2103, 0)] and not bad and not moved
    return ok, "pairs %s; unpaired or differing %d; after-position not later %d" % (keys, len(bad), len(moved))


def chk_chains(cm, s1, s2):
    a, b = s1[0], s2[0]
    rows = cm.chains(b, a) + cm.chains(a, b)
    want = {"dec_to_msg": 10, "msg_transit": 40, "dmg_transit": 40}
    bad = [r for r in rows if r["not_run"] is not None or any(r[k] != v for k, v in want.items()) or r["hp_d"] == 0]
    keys = sorted((r["pid"], r["cord"]) for r in rows)
    ok = keys == [(1101, 0), (1103, 0), (2103, 0)] and not bad
    return ok, "chains %s; dec_to_msg 10, transits 40, a health change on every row: %s" % (keys, "yes" if not bad else bad)


def chk_vchg(cm, s1, s2):
    out = cm.velocity_changes(s1[0], s2[0])
    by = {}
    for c in out["changes"]:
        by.setdefault(c["pid"], []).append(tuple(c["causes"]))
    want = {1101: [("collider",)], 1102: [("retarget",), ("surface", "destruction")], 1103: [("surface",), ("collider",)]}
    norm = {k: sorted(tuple(sorted(x)) for x in v) for k, v in by.items()}
    wantn = {k: sorted(tuple(sorted(x)) for x in v) for k, v in want.items()}
    return norm == wantn, "owner changes by projectile %s (want %s)" % (norm, wantn)


def chk_bsel(cm, s1, s2):
    out = cm.velocity_changes(s1[0], s2[0])
    b = out["bounces"]
    ok = (len(b) == 1 and b[0]["pid"] == 1102 and b[0]["stamp"] == 106000 and b[0]["meas"] is not None
          and b[0]["target"] == "other" and b[0]["los_other"] == 1 and b[0]["d_other"] >= 0 and not out["meas_unpaired"])
    return ok, "selections %s; unpaired measured %d" % ([(x["pid"], x["stamp"], x["target"], x["meas"] is not None) for x in b],
                                                       len(out["meas_unpaired"]))


def chk_death_oob(cm, s1, s2):
    rows = cm.deaths(s2[0], s1[0])
    ok = (len(rows) == 1 and rows[0]["self"]["cause"] == 1 and rows[0]["self"]["edge"] == 2 and rows[0]["meas"] is not None
          and rows[0]["meas"]["cause"] == 1 and rows[0]["meas"]["edge"] == 2 and rows[0]["not_run"] is None)
    return ok, "seat 2's deaths %s" % [(r["self"]["ord"], r["self"]["cause"], r["self"]["edge"], r["meas"] is not None) for r in rows]


def chk_death_hit(cm, s1, s2):
    rows = cm.deaths(s1[0], s2[0])
    ok = (len(rows) == 1 and rows[0]["self"]["cause"] == 2 and rows[0]["self"]["edge"] == 0 and rows[0]["meas"] is not None
          and rows[0]["hits"] and rows[0]["hits"][0]["pid"] == 2103 and rows[0]["hits"][0]["push_listed"] is True)
    return ok, "seat 1's deaths %s" % [(r["self"]["ord"], r["self"]["cause"], r["self"]["edge"],
                                        [(h["pid"], h["cord"], h["push_listed"]) for h in r["hits"]]) for r in rows]


def chk_m2(cm, s1, s2):
    m = []
    for rec in (s1[0], s2[0]):
        row = rec["a1sum"][0]
        m.append((row[0], row[1]))
    ok = all(n >= 1 and abs(mean) <= 5 for n, mean in m)
    return ok, "a1s (n, mean mrad) per seat %s: aimed straight at the other body" % m


def chk_m3(cm, s1, s2):
    a, b = s1[0], s2[0]
    gs, go, go2 = a["gun_s"][0], a["gun_o"][0], b["gun_o"][0]
    vals = (f(cm, "gun_s", gs, "spr"), f(cm, "gun_s", gs, "nproj"), f(cm, "gun_o", go, "spr"), f(cm, "gun_o", go, "nproj"),
            f(cm, "gun_o", go2, "spr"), f(cm, "gun_o", go2, "nproj"))
    ok = vals[0] == 0 and vals[1] == 1 and vals[2] > 0 and vals[3] == 2 and vals[4] == 0 and vals[5] == 1
    return ok, "locked gun spr/nproj on its own seat %s, on the other %s; unlocked %s" % (vals[0:2], vals[4:6], vals[2:4])


def chk_m4(cm, s1, s2):
    reps = []
    for g in s1[0]["sh_s"]:
        for sh in g[1]:
            reps.append(sh[cm.SHOT["s"]["rep"]])
    return reps == [0, 1, 2], "own emissions' repeat ordinals %s (want [0, 1, 2])" % reps


def chk_m5(cm, s1, s2):
    own = [f(cm, "b5_s", e, "tb") for e in s1[0]["b5_s"]]
    other = [f(cm, "b5_o", e, "tb") for e in s2[0]["b5_o"]]
    return own == PRESS_TB and other == PRESS_TB, "own press keys %s, the other seat's %s (want %s)" % (own, other, PRESS_TB)


def chk_m6(cm, s1, s2):
    names = [x[0] for x in cm.SPEC["b5_c"][3]]
    rows = [e for e in s1[0]["b5_c"] if e[0] == 2102]
    got = [e[5] for e in rows]
    return got == M6_STAMPS, "contacts of 2102 paired to hit stamps %s (want %s; field %s)" % (got, M6_STAMPS, names[5])


def chk_pairview(cm, s1, s2):
    """The server's whole two-record view (A17's rebuild, A9's block pairing, A5's stat pairing as structure)."""
    view = cm.pair_view([{"seat": SEAT[1], "other": SEAT[2], "rec": s1[0]}, {"seat": SEAT[2], "other": SEAT[1], "rec": s2[0]}])
    faults = {k: {n: v for n, v in f_.items() if v} for k, f_ in view["faults"].items()}
    faults = {k: v for k, v in faults.items() if v}
    blk = view["blocks"]
    bad_blocks = [(b.get("tb"), b.get("not_run")) for b in blk if b.get("not_run") is not None]
    gun_pair = s1[0]["gun_s"] == s2[0]["gun_o"] and s2[0]["gun_s"] == s1[0]["gun_o"]
    ok = view["paired"] and not faults and len(blk) == 2 and not bad_blocks and gun_pair
    return ok, "paired %s; rebuild/section faults %s; own blocks paired %d of %d %s; gun rows equal across seats %s" % (
        view["paired"], faults or "none", len(blk) - len(bad_blocks), len(blk), bad_blocks or "", gun_pair)


CHECKS = [("server", chk_server), ("pair_view", chk_pairview),("pushes", chk_pushes), ("chains", chk_chains), ("vchg", chk_vchg), ("bsel", chk_bsel),
          ("death_oob", chk_death_oob), ("death_hit", chk_death_hit), ("m2_aim", chk_m2), ("m3_locked", chk_m3),
          ("m4_reps", chk_m4), ("m5_keys", chk_m5), ("m6_order", chk_m6)]
G1_CHECKS = ["m2_aim", "m3_locked", "m4_reps", "m5_keys", "m6_order"]


def evaluate(cm, r1, r2):
    out = {}
    if "fail" in r1 or "fail" in r2 or len(r1["rec"]) != 1 or len(r2["rec"]) != 1:
        return {n: (False, "no record") for n, _ in CHECKS}
    s1, s2 = (r1["rec"][0], r1["text"][0]), (r2["rec"][0], r2["text"][0])
    for n, fn in CHECKS:
        try:
            out[n] = fn(cm, s1, s2)
        except Exception as ex:
            out[n] = (False, "%s %s" % (type(ex).__name__, ex))
    return out


# -- the throwing build (M1) -------------------------------------------------------------------------

def plant_source(text):
    count = 0
    for name, row in ENTRIES.items():
        m = re.search(r"(?m)^        internal static \w+ " + name + r"\(", text)
        i = text.index("long t0 = Stamp();", m.end())
        j = text.index("try", i)
        k = text.index("{", j)
        ins = ' if (ScenarioPlant.Row == %s) throw new System.InvalidOperationException("planted");' % row
        text = text[:k + 1] + ins + text[k + 1:]
        count += 1
    return text, count


# -- per-collector mutants: (name, old, new, target check, control check) -----------------------------
MUTANTS = [
    ("push_cord_shift", "g.VcPush = true; rows = g.PushS; pid = g.VcPid; sInit = g.VcSInit; cord = g.VcCord;",
     "g.VcPush = true; rows = g.PushS; pid = g.VcPid; sInit = g.VcSInit; cord = g.VcCord + 1;", "pushes", "death_oob"),
    ("push_after_never_waits", "Wait(g, 0, rows, o, (state & 2) == 0 ? 0 : 1);", "", "pushes", "chains"),
    ("chain_receipt_dropped", "a[o] = pid; a[o + 1] = sInit; a[o + 2] = cord; a[o + 3] = ServerNow(); a[o + 4] = -1;",
     "a[o] = pid; a[o + 1] = sInit; a[o + 2] = cord; a[o + 3] = -1; a[o + 4] = -1;", "chains", "pushes"),
    ("chain_decision_dropped", "c[oc + 3] = g.OwnDecOn[k] ? g.OwnDec[k] : -1;", "c[oc + 3] = -1;", "chains", "vchg"),
    ("vchg_retarget_as_surface", "VchgRow(g, pid, g.OwnSInit[k], stamp, W.CAUSE_RETARGET,", "VchgRow(g, pid, g.OwnSInit[k], stamp, W.CAUSE_SURFACE,",
     "vchg", "bsel"),
    ("vchg_edge_missed", "VchgRow(g, g.EvPid, g.EvSInit, g.EvStamp, W.CAUSE_SURFACE,", "if (false) VchgRow(g, g.EvPid, g.EvSInit, g.EvStamp, W.CAUSE_SURFACE,",
     "vchg", "bsel"),
    ("bsel_stamp_shift", "a[o] = pid; a[o + 1] = g.OwnSInit[k]; a[o + 2] = stamp; a[o + 3] = g.Bs[b];",
     "a[o] = pid; a[o + 1] = g.OwnSInit[k]; a[o + 2] = stamp + 1; a[o + 3] = g.Bs[b];", "bsel", "vchg"),
    ("death_edge_swapped", "(pos.x >= OOB_X ? W.EDGE_RIGHT", "(pos.x >= OOB_X ? W.EDGE_LEFT", "death_oob", "death_hit"),
    ("death_cause_dropped", "int cause = own ? g.LastSrcOwn : g.LastSrcOpp;", "int cause = W.DEATH_CAUSE_UNKNOWN;", "death_oob", "pushes"),
    ("death_guard_dropped", "if (data == null || !data.isPlaying || data.dead || data.playerVel == null) return;",
     "if (data == null || !data.isPlaying || data.playerVel == null) return;", "death_hit", "death_oob"),
    ("m2_root_transform", "pos = p.data.playerVel.position;", "pos = p.transform.position;", "m2_aim", "m5_keys"),
    ("m3_lock_ignored", "long spr = 0;\n            if (!locked)", "long spr = 0;\n            if (true)", "m3_locked", "m4_reps"),
    ("m4_refused_renumbers", "if (s.AttackEmits == 0) { s.AttackEmits = s.SavedEmits;", "if (false) { s.AttackEmits = s.SavedEmits;",
     "m4_reps", "m3_locked"),
    ("m5_never_armed", "            g.OwnPressPending = true;\n        }", "        }", "m5_keys", "m6_order"),
    ("m6_newest_first", "for (int i = start, n = 0; i < count && n < PAIR_CAP; i++, n++)",
     "for (int i = count - 1, n = 0; i >= start && n < PAIR_CAP; i--, n++)", "m6_order", "m5_keys"),
]


def main():
    root = DEFAULT_SERVER
    if "--server-root" in sys.argv:
        root = sys.argv[sys.argv.index("--server-root") + 1]
    red = sys.argv[sys.argv.index("--red") + 1] if "--red" in sys.argv else None
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    shead = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    sdirty = subprocess.run(["git", "-C", root, "status", "--porcelain", "--", "backend/api/combat_measures.py"],
                            capture_output=True, text=True).stdout.strip()
    print("commit", head, "tree", "clean" if not dirty else "DIRTY")
    print("server", root, shead, "combat_measures.py", "clean" if not sdirty else "MODIFIED IN THE WORKTREE")
    print("python", sys.version.split()[0])
    cm = load_server(root)
    before = {p: sha(p) for p in TRACKED}
    ok = True

    if red:
        src = os.path.join(WORK, "red_CombatEvidence.cs")
        core = os.path.join(WORK, "red_CombatEvidenceCore.cs")
        for path, rel in ((src, "plugin/CombatEvidence.cs"), (core, "plugin/CombatEvidenceCore.cs")):
            body = subprocess.run(["git", "-C", REPO, "show", "%s:%s" % (red, rel)], capture_output=True).stdout
            open(path, "wb").write(body)
        dll = build("red", combat=src, perf="none", core=core)
        if dll is None:
            print("RED BUILD FAILED")
            return 1
        r1, r2 = run(dll, "red", 1), run(dll, "red", 2)
        res = evaluate(cm, r1, r2)
        for n in G1_CHECKS:
            print("%s %s at %s: %s" % ("RED  " if not res[n][0] else "green", n, red[:8], res[n][1]))
        print("errors:", (r1.get("err"), r2.get("err")))
        print("RED-RUN", "every G1 check red" if all(not res[n][0] for n in G1_CHECKS) else "NOT every G1 check red")
        return 0

    dll = build("base")
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    r1, r2 = run(dll, "base", 1), run(dll, "base", 2)
    for r in (r1, r2):
        if "fail" in r:
            print("RUN FAILED", r["fail"])
            return 1
    print("records: seat 1 %d, seat 2 %d; errors %s %s" % (len(r1["rec"]), len(r2["rec"]), r1["err"], r2["err"]))
    ok = ok and not r1["err"] and not r2["err"]
    res = evaluate(cm, r1, r2)
    for n, _ in CHECKS:
        print("%s %s: %s" % ("PASS" if res[n][0] else "FAIL", n, res[n][1]))
        ok = ok and res[n][0]

    # L1: the boot line, and the drop counters' names
    boot = [l for l in r1["log"] if "combat evidence patches attached" in l]
    bl = boot[0] if boot else ""
    bok = len(boot) == 1 and bl.startswith("I ") and "attached 18/18" in bl and "frame 2/2" in bl and "producers push vchg chain death" in bl
    print("%s boot line: %s" % ("PASS" if bok else "FAIL", bl[:160] + ("..." if len(bl) > 160 else "")))
    dok = r1["dropix"] is not None and r1["dropix"][1] == 0 and r1["dropix"][0] == r1["dropix"][2] == 16
    print("%s drop constants against the layout names: %s" % ("PASS" if dok else "FAIL", r1["dropix"]))
    ok = ok and bok and dok

    # capability bits: a dropped producer, an unkeyed hit
    rd = run(dll, "drop", 1, "--drop", "CombatEvidence_ForcePatch")
    dboot = [l for l in rd.get("log", []) if "combat evidence patches attached" in l]
    dcaps = rd["rec"][0]["caps"] if rd.get("rec") else None
    cok = (dboot and dboot[0].startswith("E ") and "attached 17/18" in dboot[0] and "NOT attached: HealthHandler.RPCA_SendTakeForce" in dboot[0]
           and dcaps == 14 and not cm.section_faults(rd["rec"][0]))
    print("%s a dropped force patch: boot line %s; caps %s (want 14: push withheld, its lists empty)" % (
        "PASS" if cok else "FAIL", dboot[0][:80] if dboot else None, dcaps))
    ru1, ru2 = run(dll, "unkeyed", 1, "--unkeyed"), run(dll, "unkeyed", 2, "--unkeyed")
    ucaps = [r["rec"][0]["caps"] if r.get("rec") else None for r in (ru1, ru2)]
    uok = ucaps == [10, 10] and all(not cm.section_faults(r["rec"][0]) for r in (ru1, ru2))
    print("%s an unanchored hit voids push and chain on both seats: caps %s (want 10, 10)" % ("PASS" if uok else "FAIL", ucaps))
    ok = ok and cok and uok

    # A1 (client side)
    a1, a2 = run(dll, "a1", 1, "--a1"), run(dll, "a1", 2, "--a1")
    aok = True
    for n, r in (("s1", a1), ("s2", a2)):
        if not r.get("rec") or r["err"]:
            print("FAIL A1 %s: no record or errors %s" % (n, r.get("err") or r.get("fail")))
            aok = False
    if aok:
        A, B = a1["rec"][0], a2["rec"][0]
        u = r1["rec"][0]
        names = ("drop", "a1_tot", "cost_a1")
        a1keys = all(k in A and k in B for k in names) and not any(k in u for k in names)
        caps_ok = A["caps"] == 15 | CAPS_A1 | CAPS_RX and B["caps"] == 15 | CAPS_A1 | CAPS_RX
        drop = dict(zip(["mask", "aim", "res", "pack", "vol_s", "vol_o", "wait", "c_unpaired", "c_outside", "push_expired",
                         "force_unkeyed", "unkeyed", "ray_full", "res_mask_unknown", "res_incomparable", "mask_unscanned"], B["drop"]))
        tot = A["a1_tot"]
        rx = A["rx_s"]
        print("%s A1 amended keys present only under A1: %s; caps %s %s" % ("PASS" if a1keys and caps_ok else "FAIL", a1keys, A["caps"], B["caps"]))
        print("%s A1 F4: seat 2 marks the residual after an edge bounce incomparable: res_incomparable=%d" % (
            "PASS" if drop["res_incomparable"] >= 1 else "FAIL", drop["res_incomparable"]))
        print("%s A1 F2: b5_h never-trimmed total %d == seat 1's b5_h rows %d" % (
            "PASS" if tot[0] == len(A["b5_h"]) and tot[0] > 0 else "FAIL", tot[0], len(A["b5_h"])))
        rxok = len(rx) >= 1 and rx[0][2] >= 0 and tot[3] > 0 and tot[1] == len(rx)
        print("%s A1 reaction rows: seat 1 rx_s %s, samples %d, rx totals %s" % ("PASS" if rxok else "FAIL", rx[:3], tot[3], tot[1:3]))
        diff = sorted(k for k in u if k not in ("cost", "rx_s", "rx_o", "caps", "omit", "frame_p50_us") and A[k] != u[k])
        print("info: seat 1's A1 record differs from its unamended record outside the A1 lists in %s (A1 changes the residual"
              " and mask rules by design; the bits-clear proof is the byte reproduction below)" % (diff or "nothing"))
        print("    seat 2 drop counters:", {k: v for k, v in drop.items() if v})
        aok = a1keys and caps_ok and drop["res_incomparable"] >= 1 and tot[0] == len(A["b5_h"]) and tot[0] > 0 and rxok
        if "--write-fixtures" in sys.argv:
            for d, rs in (("fixtures", (r1, r2)), ("fixtures-a1", (a1, a2))):
                os.makedirs(os.path.join(HERE, d), exist_ok=True)
                for i, r in enumerate(rs, 1):
                    open(os.path.join(HERE, d, "seat%d.rec.txt" % i), "wb").write(r["text"][0].encode("ascii"))
            print("fixtures written: fixtures/seat1-2.rec.txt (unamended, server-reproduced), fixtures-a1/seat1-2.rec.txt (A1)")
        for d, rs in (("fixtures", (r1, r2)), ("fixtures-a1", (a1, a2))):
            for i, r in enumerate(rs, 1):
                p = os.path.join(HERE, d, "seat%d.rec.txt" % i)
                if os.path.exists(p):
                    same = read(p) == r["text"][0]
                    print("%s %s/seat%d.rec.txt reproduced byte for byte by this build: %s" % ("PASS" if same else "FAIL", d, i, same))
                    aok = aok and same
                else:
                    print("FAIL %s/seat%d.rec.txt absent (run once with --write-fixtures)" % (d, i))
                    aok = False
        # the committed unamended fixtures are also the server's: budget_record reproduces them
        for i in (1, 2):
            p = os.path.join(HERE, "fixtures", "seat%d.rec.txt" % i)
            if os.path.exists(p):
                t = read(p)
                same = cm.budget_record(json.loads(t)) == t
                print("%s server budget_record reproduces fixtures/seat%d.rec.txt: %s" % ("PASS" if same else "FAIL", i, same))
                aok = aok and same
    ok = ok and aok

    # M1: the throwing build
    text = read(SOURCE)
    planted, n = plant_source(text)
    ppath = os.path.join(WORK, "plant_CombatEvidence.cs")
    open(ppath, "wb").write(planted.encode("utf-8"))
    pdll = build("plant", combat=ppath)
    if pdll is None:
        print("BUILD FAILED (plant)")
        return 1
    print("throwing build: %d entries planted" % n)
    p0 = run(pdll, "plant_none", 1, "--a1")
    digest = a1["digest"] if a1.get("digest") else None
    same0 = p0.get("digest") == digest == r1["digest"]
    print("%s the game witness digest: unamended %s, A1 %s, throwing build unarmed %s" % (
        "PASS" if same0 else "FAIL", r1["digest"][:16], (digest or "")[:16], (p0.get("digest") or "")[:16]))
    ok = ok and same0
    m1 = 0
    for i, row in enumerate(ROWS):
        r = run(pdll, "plant_" + row, 1, "--a1", "--plant", str(i))
        if "fail" in r:
            print("FAIL M1 %s: %s" % (row, r["fail"]))
            ok = False
            continue
        c, fl = r["cost"].get(i, (0, 0))
        others = [ROWS[j] for j, (cc, ff) in r["cost"].items() if j != i and ff]
        rec = r["rec"][0] if r["rec"] else None
        want = 15
        for bit, rows in SECTION_ROWS.items():
            if row in rows:
                want &= ~bit
        want |= CAPS_A1 | (CAPS_RX if row not in ("RX", "T") else 0)
        caps = rec["caps"] if rec else None
        good = (r["digest"] == r1["digest"] and c > 0 and fl == c and not others and not r["err"] and caps == want)
        m1 += good
        ok = ok and good
        print("%s M1 %s: digest %s; calls %d faults %d; other rows faulted %s; hook errors %d; caps %s (want %s)" % (
            "PASS" if good else "FAIL", row, "same" if r["digest"] == r1["digest"] else "DIFFERS", c, fl, others or "none",
            len(r["err"]), caps, want))
    print("M1: %d of %d rows contained (identical game, every call faulted and counted, bits withheld)" % (m1, len(ROWS)))

    # A14: the menu measurement on the stub clock, and its control
    pf = run(dll, "perf", 1, "--perf")
    lines = [l for l in pf.get("log", []) if "[COMBAT-PERF]" in l]
    det = [l for l in lines if "planted control" in l]
    pok = det and "detected=yes" in det[0] and any("A/A:" in l for l in lines) and any("menu run complete" in l for l in lines)
    for l in lines:
        print("   ", l)
    nop = os.path.join(WORK, "perf_noplant.cs")
    open(nop, "wb").write(read(PERF).replace("Spin(PLANT_MS);", "Spin(0);").encode("utf-8"))
    ndll = build("perf_noplant", perf=nop)
    nf = run(ndll, "perf_noplant", 1, "--perf") if ndll else {}
    ndet = [l for l in nf.get("log", []) if "planted control" in l]
    nok = bool(ndet) and "detected=no" in ndet[0]
    print("%s A14 menu run: A/A, planted control detected; %s mutant without the plant reports detected=no: %s" % (
        "PASS" if pok else "FAIL", "CAUGHT" if nok else "MISSED", ndet[0] if ndet else None))
    ok = ok and pok and nok

    # per-collector mutants
    caught = 0
    for name, old, new, target, control in MUTANTS:
        cnt = text.count(old)
        if cnt != 1:
            print("BAD mutant %s: anchor occurs %d times" % (name, cnt))
            ok = False
            continue
        mp = os.path.join(WORK, "mut_%s.cs" % name)
        open(mp, "wb").write(text.replace(old, new).encode("utf-8"))
        mdll = build("mut_" + name, combat=mp)
        if mdll is None:
            print("BAD mutant %s: does not build" % name)
            ok = False
            continue
        m1r, m2r = run(mdll, "mut_" + name, 1), run(mdll, "mut_" + name, 2)
        mres = evaluate(cm, m1r, m2r)
        hit = not mres[target][0] and mres[control][0]
        caught += hit
        ok = ok and hit
        print("%s mutant %s: target %s=%s; control %s=%s" % ("CAUGHT" if hit else "MISSED", name, target,
                                                            "FAIL" if not mres[target][0] else "PASS", control,
                                                            "PASS" if mres[control][0] else "FAIL"))
        if not hit:
            print("    ", mres[target][1][:300], "|", mres[control][1][:300])
    print("mutants: %d of %d caught" % (caught, len(MUTANTS)))

    unchanged = all(sha(p) == before[p] for p in TRACKED)
    print("tracked plugin files unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
