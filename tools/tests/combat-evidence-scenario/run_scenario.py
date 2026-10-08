"""Combat evidence scenario harness (fix pass 3: A1 is the wire; M1, M6, M7, M9, M11, M12, M13).

Builds the REAL plugin/CombatEvidence.cs and CombatEvidencePerf.cs with the
REAL core, wire and SeatEvidenceCore against Stubs.cs (ScenarioTests.csproj)
and drives Program.cs's scripted 1v1 once from each seat. Every record the
client emits is an A1 record (amendment A1 is the wire). Then:

  * the REFERENCE: the server's combat_measures.py (from --server-root, read
    by path, never written, no bytecode). When it carries the amendment
    (COMBAT_WIRE_A1) its budget_record is the byte reference; when it does
    not, the client-side mirror below is (the A1 rules of
    COMBAT-WIRE-AMENDMENT-A1.md written in Python over the server's own
    serializer and removal rule) and the run says so;
  * every record: the mirror's layout check (A1 bounds, the section (f)
    fields), the reference budgeter reproduces the client's bytes, the
    record's legacy projection (A1 part and section (f) fields removed, bits
    16 and 32 cleared) passes the server's check_record with no section
    fault, and the two seats' projections PAIR through pushes, chains,
    velocity_changes and deaths with the values the script implies;
  * fixtures/ (the A1 records: both seats and the four variant records) are
    reproduced by every build (cost timings masked), and fixtures-legacy/
    (the previous wire, bits 16 and 32 clear: the shape clients in the field
    send) is accepted by the server reference byte for byte;
  * G1 checks (M2 to M6), the A1 part (keys, F2, F4), the reaction rows
    (M7: bit 16 with real rows when the sampler ran, clear and NOT-COLLECTED
    when it did not), M6's overflow counter, M9's ring and gone-before-scan
    UNKNOWN masks, M11's integrator rows (gravity, steering), M12's force
    stage joined into the chain, M13's force identities on deaths;
  * the capability bits: a dropped force patch clears push, chain and death;
    a dropped integrator patch clears vchg; an unanchored hit voids push
    and chain (and death with them);
  * M1: one throwing build (a throw planted at the head of every collector
    entry's contained body, armed per cost row at run time). For each of the
    twenty-one rows: the game witness digest equals the unplanted run's, the
    EMITTED cost row (rows 0..12 in `cost`, 13..20 in `cost_a1`) shows calls
    > 0 and faults == calls, no other emitted row faults, no exception leaves
    a hook, and the sections fed by that row lose their bit. A mutant that
    serializes the fault field as 0 must turn it red;
  * A14: the menu measurement (A/A, planted control) on the stub clock, and
    a mutant without the plant that must report detected=no;
  * per-collector mutants (copies, never the tracked file): each must turn
    its target check red while a control check stays green.

    python run_scenario.py [--server-root DIR | --server-api DIR] [--red COMMIT] [--write-fixtures]

--server-api names the directory the reference is imported from (a
REFERENCE-server-<commit>-api directory holding that commit's
combat_measures.py and review_measures.py); --server-root a server worktree.
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

ROWS = ["K1", "K2", "K3", "K4", "K5", "N1", "N2", "N3", "N4", "N5", "N6", "N7", "T", "P1", "D1", "X1", "S1", "H1", "E1", "RX", "G1"]
ENTRIES = {"RpcSent": "K1", "InitEnter": "K2", "InitExit": "K2", "HitEnter": "K3", "BlockDone": "K4", "Dealt": "K5",
           "AttackEnter": "N1", "AttackExit": "N1", "ReloadEnter": "N2", "TargetBounce": "N3", "EdgeBounce": "N4",
           "SyncRead": "N5", "TryBlockEnter": "N6", "TryBlockExit": "N6", "ContactEnter": "N7", "Tick": "T",
           "ForceEnter": "P1", "ForceExit": "P1", "DamageEnter": "D1", "DamageExit": "D1", "Die": "X1",
           "FindTarget": "S1", "HitExit": "H1", "EdgeBounceExit": "E1", "RxSample": "RX", "MoveEnter": "G1", "MoveExit": "G1"}
COLLECTORS = 13
# the rows each section's rows depend on (CombatEvidence.SECTION_ROWS); bits push 1, vchg 2, chain 4, death 8
SECTION_ROWS = {1: ["K2", "K3", "H1", "P1", "T"], 2: ["K2", "K3", "H1", "N3", "N4", "E1", "S1", "G1"],
                4: ["K1", "K2", "K3", "H1", "D1", "N7", "N1", "T"], 8: ["K2", "K3", "D1", "X1"]}
NEEDS_PUSH = 4 | 8                      # chain and death carry the force (A1 f): only with push
CAPS_PUSH, CAPS_VCHG, CAPS_CHAIN, CAPS_DEATH, CAPS_RX, CAPS_A1 = 1, 2, 4, 8, 16, 32
SEAT = {1: "76561190000000001", 2: "76561190000000002"}

# -- the amendment A1 as COMBAT-WIRE-AMENDMENT-A1.md states it (the client-side mirror) ----------------
A1_KEYS = ("drop", "a1_tot", "cost_a1")
DROP_FIELDS = ("mask", "aim", "res", "pack", "vol_s", "vol_o", "wait", "c_unpaired", "c_outside", "push_expired",
               "force_unkeyed", "unkeyed", "ray_full", "res_mask_unknown", "res_incomparable", "mask_unscanned")
TOT_FIELDS = ("b5_h", "rx_on_s", "rx_on_o", "rx_samples")
A1_HI = 9999999
COST_A1_ROWS = 8
FORCE3 = ["f%d_%s" % (i, n) for i in (1, 2, 3) for n in ("pid", "s_init", "cord", "snd", "age")]
EXT = {"ch_s": ["t_frc_rcv"], "ch_o": ["t_frc"], "bd_s": FORCE3, "bd_o": FORCE3}

# the script's facts (Program.cs Script)
A_SHOTS = [1101, 1102, 1103]
B_SHOTS = [2101, 2102, 2103]
STEERED = {1: 1101, 2: 2101}
PRESS_TB = [102000, 107200]
M6_STAMPS = [105100, 105150]
RING_LAST = 2329


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


def emitted_cost(rec):
    """The cost rows as the record carries them: rows 0..12 from `cost`, 13..20 from `cost_a1` (M1)."""
    rows = list(rec.get("cost", [])) + list(rec.get("cost_a1", []))
    return {i: (row[0], row[3]) for i, row in enumerate(rows)}


def run(dll, tag, seat, *opts):
    path = os.path.join(WORK, "out_%s_s%d.txt" % (tag, seat))
    if os.path.exists(path):
        os.remove(path)
    r = subprocess.run(["dotnet", dll, str(seat), path] + list(opts), capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(path):
        return {"fail": "exit %d %s" % (r.returncode, (r.stdout + r.stderr)[-1500:])}
    res = {"err": [], "env": [], "log": [], "digest": None, "dropix": None}
    for ln in read(path).split("\n"):
        kind, _, rest = ln.partition(" ")
        if kind == "ERR":
            res["err"].append(rest)
        elif kind == "ENV":
            res["env"].append(rest)
        elif kind == "LOG":
            res["log"].append(rest)
        elif kind == "DIGEST":
            res["digest"] = rest
        elif kind == "DROPIX":
            res["dropix"] = [int(x) for x in rest.split()]
    res["text"] = [json.loads(e)["record"] for e in res["env"]]
    res["rec"] = [json.loads(t) for t in res["text"]]
    res["cost"] = emitted_cost(res["rec"][0]) if res["rec"] else {}
    return res


def untimed(rec):
    """A record with the measured-time fields of its cost rows (ticks, max ticks) set to 0."""
    out = dict(rec)
    for k in ("cost", "cost_a1"):
        if k in out:
            out[k] = [[row[0], 0, 0] + list(row[3:]) for row in out[k]]
    return out


def load_server(api_dir):
    """The server module from `api_dir` (the directory holding combat_measures.py and review_measures.py:
    a server worktree's backend/api, or a REFERENCE-server-<commit>-api directory extracted from a commit)."""
    sys.path.insert(0, api_dir)
    import combat_measures
    return combat_measures


# -- the reference: the server's amended budgeter, or the client-side mirror ----------------------------

def server_amended(cm):
    return hasattr(cm, "COMBAT_WIRE_A1") and hasattr(cm, "amended")


def ext_fields(cm, key):
    """Section (f) fields with their bounds: t_frc_rcv as t_dmg_rcv, t_frc as t_dmg, a force
    identity as a recent hit's (pid one lower for the unkeyed mark -2; snd -1..1)."""
    own = {f[0]: (f[1], f[2]) for f in cm.SPEC[key][3]}
    out = []
    for n in EXT[key]:
        if n.endswith("_snd"):
            out.append((n, -1, 1))
            continue
        src = {"t_frc_rcv": "t_dmg_rcv", "t_frc": "t_dmg"}.get(n, "h1_" + n[3:])
        lo, hi = own[src]
        if n.endswith("_pid"):
            lo = min(lo, -2)
        out.append((n, lo, hi))
    return out


def ext_ix(cm, key, name):
    return len(cm.SPEC[key][3]) + EXT[key].index(name)


def _row_ok(v, fields):
    return (isinstance(v, list) and len(v) == len(fields)
            and all(isinstance(x, int) and not isinstance(x, bool) and f[1] <= x <= f[2] for x, f in zip(v, fields)))


def mirror_check(cm, rec):
    """The amended layout check (A1 and its section f): None, or the first key outside it."""
    if list(rec.keys()) != list(cm.KEYS) + list(A1_KEYS):
        return "key_order"
    caps = rec["caps"]
    if not (isinstance(caps, int) and 0 <= caps <= 63 and caps & CAPS_A1):
        return "caps"
    for k in cm.KEYS:
        if k == "caps":
            continue
        v = rec[k]
        if k in EXT or k == "p3top":
            fields = list(cm.SPEC[k][3])
            if k in EXT:
                fields += ext_fields(cm, k)
            else:
                fields = [(f[0], -1 if f[0] == "mask" else f[1], f[2]) for f in fields]
            ok = isinstance(v, list) and len(v) <= cm.SPEC[k][1] and all(_row_ok(x, fields) for x in v)
        else:
            ok = cm.check_field(k, v)
        if not ok:
            return k
    cnt = [("c", 0, A1_HI)]
    if not _row_ok(rec["drop"], cnt * len(DROP_FIELDS)):
        return "drop"
    if not _row_ok(rec["a1_tot"], cnt * len(TOT_FIELDS)):
        return "a1_tot"
    ca = rec["cost_a1"]
    if not (isinstance(ca, list) and len(ca) == COST_A1_ROWS and all(_row_ok(x, cm.SPEC["cost"][2]) for x in ca)):
        return "cost_a1"
    return None


def mirror_budget(cm, rec, limit=None):
    """budget_record with the amendment: the A1 part after `omit`, never trimmed, its
    bytes counted; the server's own step one, serializer and removal rule on the rest."""
    limit = cm.RECORD_MAX_BYTES if limit is None else limit
    out = {}
    for k in cm.KEYS:
        v = rec[k]
        out[k] = [list(x) if isinstance(x, list) else x for x in v] if isinstance(v, list) else v
    omit = {k: rec["omit"][k] for k in cm.OMIT_KEYS}
    for k in cm.LISTS:
        s = cm.SPEC[k]
        lst = list(out[k])
        if len(lst) > s[1]:
            omit[k] += len(lst) - s[1]
            lst = lst[: s[1]]
        if s[0] == "groups":
            lst = [[list(g[0]), [list(x) for x in g[1][: s[4]]], [list(x) for x in g[2][: s[6]]]] for g in lst]
        out[k] = lst
    out["omit"] = omit
    for k in A1_KEYS:
        out[k] = rec[k]
    body = cm.dumps(out)
    while len(body) > limit:
        if not cm._trim_one(out, omit):
            raise ValueError("the never-trimmed part alone exceeds the record bound")
        body = cm.dumps(out)
    return body


def ref_budget(cm, rec):
    return cm.budget_record(rec) if server_amended(cm) else mirror_budget(cm, rec)


def legacy(cm, rec):
    """The record as the previous wire reads it: no A1 part, the four lists at their layout
    width, an UNKNOWN mask read as 0, bits 16 and 32 cleared (the measures pair on this)."""
    out = {}
    mi = cm.IX["p3top"]["mask"]
    for k in cm.KEYS:
        v = rec[k]
        if k in EXT:
            n = len(cm.SPEC[k][3])
            v = [list(r[:n]) for r in v]
        elif k == "p3top":
            v = [[0 if (j == mi and x == -1) else x for j, x in enumerate(r)] for r in v]
        out[k] = v
    out["caps"] = rec["caps"] & 15
    return out


def rx_reading(cm, rec):
    """The reaction measure's reading: NOT-COLLECTED without bit 16 (the server's has_rx when it has one)."""
    has = cm.has_rx(rec) if hasattr(cm, "has_rx") else bool(rec["caps"] & CAPS_RX)
    return "rows" if has else "NOT-COLLECTED"


def named(rec, key, name):
    return DROP_FIELDS.index(name) if key == "drop" else TOT_FIELDS.index(name)


# -- the checks: name -> fn(cm, s1, s2) -> (ok, detail); s = (legacy projection, text, full record) --------

def f(cm, key, e, name):
    return e[cm.IX[key][name]]


def chk_server(cm, s1, s2):
    bad, info = [], []
    for n, (proj, text, rec) in (("s1", s1), ("s2", s2)):
        why = mirror_check(cm, rec)
        if why:
            bad.append("%s amended layout refuses %s" % (n, why))
        if ref_budget(cm, rec) != text:
            bad.append("%s the reference budgeter differs from the client's bytes" % n)
        try:
            cm.check_record(proj)
        except Exception as ex:
            bad.append("%s legacy projection check_record %s" % (n, ex))
        sf = cm.section_faults(proj)
        if sf:
            bad.append("%s section_faults %s" % (n, sf))
        if rec["caps"] != 63:
            bad.append("%s caps %d" % (n, rec["caps"]))
        if server_amended(cm):
            try:
                cm.check_record(rec)
                info.append("%s server check_record accepts" % n)
            except Exception as ex:
                info.append("%s server check_record refuses %s (A1 section f owed to the server lane)" % (n, ex))
    ref = "server A1 budget_record" if server_amended(cm) else "client-side mirror"
    return not bad, "; ".join(bad) or ("both records: amended layout ok, %s reproduces the bytes, projection accepted, "
                                       "no section fault, caps 63%s" % (ref, ("; " + "; ".join(info)) if info else ""))


def chk_a1(cm, s1, s2):
    A, B = s1[2], s2[2]
    keys = all(list(r.keys())[-3:] == list(A1_KEYS) for r in (A, B))
    tot = A["a1_tot"]
    f2 = tot[0] == len(A["b5_h"]) + A["omit"]["b5_h"] and tot[0] > 0
    f4 = B["drop"][DROP_FIELDS.index("res_incomparable")] >= 1
    ok = keys and f2 and f4
    return ok, "A1 part after omit on both: %s; F2 b5_h total %d == rows %d + omit %d; F4 seat 2 res_incomparable %d" % (
        keys, tot[0], len(A["b5_h"]), A["omit"]["b5_h"], B["drop"][DROP_FIELDS.index("res_incomparable")])


def chk_rx_real(cm, s1, s2):
    out, ok = [], True
    for n, (_p, _t, rec) in (("s1", s1), ("s2", s2)):
        tot = rec["a1_tot"]
        rx = rec["rx_s"]
        good = (rec["caps"] & CAPS_RX and rx_reading(cm, rec) == "rows" and len(rx) >= 1 and rx[0][2] >= 0 and tot[3] > 0
                and tot[1] == len(rx) + rec["omit"]["rx_s"])
        ok = ok and bool(good)
        out.append("%s bit16 %s, rx_s %d rows (first %s), samples %d, rx_on_s %d" % (
            n, bool(rec["caps"] & CAPS_RX), len(rx), rx[0] if rx else None, tot[3], tot[1]))
    return ok, "; ".join(out)


def chk_pushes(cm, s1, s2):
    a, b = s1[0], s2[0]
    rows = cm.pushes(b, a) + cm.pushes(a, b)
    keys = sorted((r["pid"], r["cord"]) for r in rows)
    bad = [r for r in rows if r["not_run"] is not None or any(r["d_" + k] != 0 for k in ("fx", "fy", "vax", "vay", "pax", "pay"))]
    # the after-position is read a tick later: a surviving body has moved; 2103 is lethal (the body dies, stays put)
    moved = [r for r in rows if r["pid"] != 2103 and r["self"]["pax"] == r["self"]["pbx"] and r["self"]["pay"] == r["self"]["pby"]]
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


def chk_chain_force(cm, s1, s2):
    """M12: the force stage joined into the chain: the shooter's t_frc (its force message's
    creation stamp) and the victim's t_frc_rcv (its receipt there), keyed by the hit, equal to
    the keyed push rows' stamps on each seat, the force transit 40 like the others."""
    pairs, bad = [], []
    for shooter, victim in ((s1[2], s2[2]), (s2[2], s1[2])):
        po = {(e[0], e[1], e[2]): e[3] for e in shooter["push_o"]}
        ps = {(e[0], e[1], e[2]) for e in victim["push_s"]}
        vrow = {(e[0], e[1], e[2]): e for e in victim["ch_s"]}
        for e in shooter["ch_o"]:
            key = (e[0], e[1], e[2])
            t_frc = e[ext_ix(cm, "ch_o", "t_frc")]
            v = vrow.get(key)
            t_rcv = v[ext_ix(cm, "ch_s", "t_frc_rcv")] if v else None
            pairs.append((e[0], e[2], t_frc, t_rcv))
            if t_frc == -1 or po.get(key) != t_frc:
                bad.append((key, "creation", t_frc, po.get(key)))
            if v is None or key not in ps or t_rcv is None or t_rcv - t_frc != 40 or t_rcv < v[3]:
                bad.append((key, "receipt", t_rcv))
    keys = sorted((p[0], p[1]) for p in pairs)
    ok = keys == [(1101, 0), (1103, 0), (2103, 0)] and not bad
    return ok, "force stage (pid, cord, t_frc, t_frc_rcv) %s; joined to the keyed push rows, transit 40: %s" % (
        sorted(pairs), "yes" if not bad else bad)


def chk_vchg(cm, s1, s2):
    out = cm.velocity_changes(s1[0], s2[0])
    by = {}
    for c in out["changes"]:
        if set(c["causes"]) <= {"gravity", "steering"}:
            continue                    # the integrator's rows: chk_g1
        by.setdefault(c["pid"], []).append(tuple(c["causes"]))
    want = {1101: [("collider",)], 1102: [("retarget",), ("surface", "destruction")], 1103: [("surface",), ("collider",)]}
    norm = {k: sorted(tuple(sorted(x)) for x in v) for k, v in by.items()}
    wantn = {k: sorted(tuple(sorted(x)) for x in v) for k, v in want.items()}
    return norm == wantn, "owner message changes by projectile %s (want %s)" % (norm, wantn)


def chk_g1(cm, s1, s2):
    """M11: every own projectile's integrator rows: a gravity row (x unchanged, y falling) for
    each, steering (with gravity, the same frames) on the steered projectile only."""
    out, ok = [], True
    for seat, own in ((1, A_SHOTS), (2, B_SHOTS)):
        rec = (s1 if seat == 1 else s2)[2]
        grav, steer, bad = set(), set(), []
        for e in rec["vchg"]:
            pid, cause, ovx, ovy, nvx, nvy = e[0], e[3], e[4], e[5], e[6], e[7]
            if cause == 4:
                grav.add(pid)
                if nvx != ovx or nvy >= ovy:
                    bad.append(e)
            if cause & 8:
                steer.add(pid)
                if cause != 12:
                    bad.append(e)
        good = set(own) <= grav and steer == {STEERED[seat]} and not bad and rec["caps"] & CAPS_VCHG
        ok = ok and bool(good)
        out.append("seat %d gravity rows for %s, steering rows for %s (want %s), malformed %d" % (
            seat, sorted(grav), sorted(steer), [STEERED[seat]], len(bad)))
    return ok, "; ".join(out)


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


def forces(cm, key, e):
    base = len(cm.SPEC[key][3])
    return [tuple(e[base + 5 * h: base + 5 * h + 5]) for h in range(3)]


def chk_death_force(cm, s1, s2):
    """M13: a death's last three forces, newest first: the out-of-bounds death of seat 2 shows its
    own unkeyed out-of-bounds push (pid -2, sent by the dying seat), then the keyed pushes of 1103
    and 1101; seat 1's death by 2103 shows 2103's keyed push (sent by the other seat)."""
    a, b = s1[2], s2[2]
    s2own = forces(cm, "bd_s", b["bd_s"][0]) if b["bd_s"] else []
    s1opp = forces(cm, "bd_o", a["bd_o"][0]) if a["bd_o"] else []
    s1own = forces(cm, "bd_s", a["bd_s"][0]) if a["bd_s"] else []
    ok = (len(s2own) == 3 and s2own[0][0] == -2 and s2own[0][3] == 0 and s2own[0][4] >= 0
          and s2own[1][0] == 1103 and s2own[1][3] == 1 and s2own[2][0] == 1101 and s2own[2][3] == 1
          and len(s1opp) == 3 and s1opp[0][0] == -2 and s1opp[0][3] == 1 and s1opp[1][0] == 1103 and s1opp[1][3] == 0
          and len(s1own) == 3 and s1own[0][0] == 2103 and s1own[0][3] == 1 and s1own[1][0] == -1)
    return ok, "seat 2 own death forces %s; seat 1's view of it %s; seat 1 own death forces %s" % (s2own, s1opp, s1own)


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


CHECKS = [("server", chk_server), ("a1", chk_a1), ("rx_real", chk_rx_real), ("pair_view", chk_pairview), ("pushes", chk_pushes),
          ("chains", chk_chains), ("chain_force", chk_chain_force), ("vchg", chk_vchg), ("g1", chk_g1), ("bsel", chk_bsel),
          ("death_oob", chk_death_oob), ("death_hit", chk_death_hit), ("death_force", chk_death_force), ("m2_aim", chk_m2),
          ("m3_locked", chk_m3), ("m4_reps", chk_m4), ("m5_keys", chk_m5), ("m6_order", chk_m6)]
G1_CHECKS = ["m2_aim", "m3_locked", "m4_reps", "m5_keys", "m6_order"]


def seats(cm, r1, r2):
    if "fail" in r1 or "fail" in r2 or len(r1["rec"]) != 1 or len(r2["rec"]) != 1:
        return None
    return ((legacy(cm, r1["rec"][0]), r1["text"][0], r1["rec"][0]), (legacy(cm, r2["rec"][0]), r2["text"][0], r2["rec"][0]))


def evaluate(cm, r1, r2, names=None):
    out = {}
    s = seats(cm, r1, r2)
    for n, fn in CHECKS:
        if names is not None and n not in names:
            continue
        if s is None:
            out[n] = (False, "no record")
            continue
        try:
            out[n] = fn(cm, s[0], s[1])
        except Exception as ex:
            out[n] = (False, "%s %s" % (type(ex).__name__, ex))
    return out


# -- the variant runs: name -> (options, check fn(cm, v1, v2)) -------------------------------------------

def boot_of(r):
    b = [l for l in r.get("log", []) if "combat evidence patches attached" in l]
    return b[0] if b else ""


def vk_drop_force(cm, v1, v2):
    rec = v1["rec"][0]
    bl = boot_of(v1)
    want = CAPS_VCHG | CAPS_RX | CAPS_A1
    ok = (bl.startswith("E ") and "attached 18/19" in bl and "NOT attached: HealthHandler.RPCA_SendTakeForce" in bl
          and rec["caps"] == want and not cm.section_faults(legacy(cm, rec))
          and not any(rec[k] for k in ("push_s", "push_o", "ch_s", "ch_o", "bd_s", "bd_o")))
    return ok, "boot %s; caps %d (want %d: push withheld, chain and death with it, their lists empty)" % (bl[:60], rec["caps"], want)


def vk_drop_move(cm, v1, v2):
    rec = v1["rec"][0]
    bl = boot_of(v1)
    want = CAPS_PUSH | CAPS_CHAIN | CAPS_DEATH | CAPS_RX | CAPS_A1
    ok = (bl.startswith("E ") and "attached 18/19" in bl and "NOT attached: MoveTransform.Update" in bl
          and rec["caps"] == want and not rec["vchg"] and not rec["bsel"])
    return ok, "boot %s; caps %d (want %d: vchg withheld without its integrator producer)" % (bl[:60], rec["caps"], want)


def vk_unkeyed(cm, v1, v2):
    caps = [v["rec"][0]["caps"] for v in (v1, v2)]
    want = CAPS_VCHG | CAPS_RX | CAPS_A1
    ok = caps == [want, want] and all(not cm.section_faults(legacy(cm, v["rec"][0])) for v in (v1, v2))
    return ok, "caps %s (want %d both: push and chain voided, death with push)" % (caps, want)


def vk_norx(cm, v1, v2):
    out, ok = [], True
    for n, v in (("s1", v1), ("s2", v2)):
        rec = v["rec"][0]
        tot = rec["a1_tot"]
        cost_rx = emitted_cost(rec)[19]
        good = (rec["caps"] == 15 | CAPS_A1 and rx_reading(cm, rec) == "NOT-COLLECTED" and rec["rx_s"] == [] and rec["rx_o"] == []
                and tot[1:] == [0, 0, 0] and cost_rx[0] == 0)
        ok = ok and good
        out.append("%s caps %d, reading %s, rx rows %d/%d, totals %s, RX calls %d" % (
            n, rec["caps"], rx_reading(cm, rec), len(rec["rx_s"]), len(rec["rx_o"]), tot[1:], cost_rx[0]))
    return ok, "; ".join(out)


def vk_m6over(cm, v1, v2):
    rec = v1["rec"][0]
    d = dict(zip(DROP_FIELDS, rec["drop"]))
    names = [x[0] for x in cm.SPEC["b5_c"][3]]
    i_since = names.index("own_since")
    rows = [e for e in rec["b5_c"] if e[0] == 2104]
    paired = [e[i_since] != -2 for e in rows]
    ok = d["c_outside"] == 2 and d["c_unpaired"] == 0 and paired == [False, False] + [True] * 8
    return ok, "seat 1 c_outside %d (want 2), c_unpaired %d; contacts of 2104 paired %s" % (d["c_outside"], d["c_unpaired"], paired)


def vk_m9ring(cm, v1, v2):
    rec = v1["rec"][0]
    d = dict(zip(DROP_FIELDS, rec["drop"]))
    mi = cm.IX["p3top"]["mask"]
    top = [(e[0], e[mi]) for e in rec["p3top"] if e[0] == RING_LAST]
    ok = d["mask"] == 2 and top == [(RING_LAST, -1)] and d["res_mask_unknown"] >= 1
    return ok, "seat 1 drop.mask %d (want 2), res_mask_unknown %d, p3top of %d %s (want mask -1)" % (
        d["mask"], d["res_mask_unknown"], RING_LAST, top)


def vk_m9gone(cm, v1, v2):
    rec = v1["rec"][0]
    d = dict(zip(DROP_FIELDS, rec["drop"]))
    mi = cm.IX["p3top"]["mask"]
    top = [(e[0], e[mi]) for e in rec["p3top"] if e[0] == 2105]
    ok = d["mask_unscanned"] == 1 and top == [(2105, -1)] and d["res_mask_unknown"] >= 1
    return ok, "seat 1 mask_unscanned %d (want 1), res_mask_unknown %d, p3top of 2105 %s (want mask -1)" % (
        d["mask_unscanned"], d["res_mask_unknown"], top)


VARIANTS = [("drop_force", ["--drop", "CombatEvidence_ForcePatch"], vk_drop_force),
            ("drop_move", ["--drop", "CombatEvidence_MovePatch"], vk_drop_move),
            ("unkeyed", ["--unkeyed"], vk_unkeyed),
            ("norx", ["--norx"], vk_norx),
            ("m6over", ["--m6over"], vk_m6over),
            ("m9ring", ["--m9ring"], vk_m9ring),
            ("m9gone", ["--m9gone"], vk_m9gone)]
VNAMES = [v[0] for v in VARIANTS]
VFIXTURES = ["norx", "m6over", "m9ring", "m9gone"]          # seat 1's record is committed for each


def run_variant(dll, tag, name):
    opts = [o for n, o, _fn in VARIANTS if n == name][0]
    return run(dll, "%s_%s" % (tag, name), 1, *opts), run(dll, "%s_%s" % (tag, name), 2, *opts)


def check_variant(cm, name, v1, v2):
    fn = [f_ for n, _o, f_ in VARIANTS if n == name][0]
    if "fail" in v1 or "fail" in v2 or not v1.get("rec") or not v2.get("rec"):
        return False, "no record %s" % (v1.get("fail") or v2.get("fail") or "")
    if v1["err"] or v2["err"]:
        return False, "hook errors %s %s" % (v1["err"], v2["err"])
    try:
        return fn(cm, v1, v2)
    except Exception as ex:
        return False, "%s %s" % (type(ex).__name__, ex)


def check_any(cm, dll, tag, name, cache):
    """One named check on a build: a base check on the two seats' base runs, or a variant check."""
    if name in VNAMES:
        if name not in cache:
            cache[name] = run_variant(dll, tag, name)
        return check_variant(cm, name, *cache[name])
    if "base" not in cache:
        cache["base"] = (run(dll, tag, 1), run(dll, tag, 2))
    return evaluate(cm, cache["base"][0], cache["base"][1], [name])[name]


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


def m1_want(row):
    want = 15
    for bit, rows in SECTION_ROWS.items():
        if row in rows:
            want &= ~bit
    if not want & CAPS_PUSH:
        want &= ~NEEDS_PUSH
    return want | CAPS_A1 | (CAPS_RX if row not in ("RX", "T") else 0)


def m1_row(pdll, tag, i, base_digest):
    row = ROWS[i]
    r = run(pdll, "%s_%s" % (tag, row), 1, "--plant", str(i))
    if "fail" in r or not r["rec"]:
        return False, "no record %s" % r.get("fail")
    c, fl = r["cost"].get(i, (0, 0))
    others = [ROWS[j] for j, (cc, ff) in r["cost"].items() if j != i and ff]
    caps = r["rec"][0]["caps"]
    want = m1_want(row)
    good = (r["digest"] == base_digest and c > 0 and fl == c and not others and not r["err"] and caps == want
            and len(r["rec"][0]["cost"]) == COLLECTORS and len(r["rec"][0]["cost_a1"]) == COST_A1_ROWS)
    return good, "digest %s; emitted calls %d faults %d; other emitted rows faulted %s; hook errors %d; caps %s (want %s)" % (
        "same" if r["digest"] == base_digest else "DIFFERS", c, fl, others or "none", len(r["err"]), caps, want)


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
    # fix pass 3
    ("m6_outside_uncounted", "{ g.Drop[D_C_OUTSIDE]++; return; }", "{ g.Drop[D_C_UNPAIRED]++; return; }", "m6over", "m9gone"),
    ("m7_rx_bit_always", "if (c.Cost[RX][0] > 0 && c.Cost[RX][3] == 0 && c.Cost[T][3] == 0) caps |= E.CAPS_RX;", "caps |= E.CAPS_RX;",
     "norx", "rx_real"),
    ("m7_sampler_silent", "g.RxRowS = RxOpen(g.RxS, _ownP, a, b, now);", "g.RxRowS = -1;", "rx_real", "norx"),
    ("m9_ring_drop_uncounted", "if (i < 0) { g.Drop[D_MASK]++; return; }", "if (i < 0) { return; }", "m9ring", "m9gone"),
    ("m9_unscanned_uncounted", "if (obj == null) { g.Drop[D_MASK_UNSCANNED]++; continue; }", "if (obj == null) { continue; }",
     "m9gone", "m9ring"),
    ("m9_unknown_as_zero", "bool unknown = !known;", "bool unknown = false;", "m9gone", "m6over"),
    ("m11_gravity_missed", "(x != g.SgLx[k] || y != g.SgLy[k] ? (long)W.CAUSE_GRAVITY : 0L)", "0L", "g1", "chains"),
    ("m11_steering_missed", "g.SgSteer[k] = x != g.SgLx[k] || y != g.SgLy[k];", "g.SgSteer[k] = false;", "g1", "chains"),
    ("m11_bit_without_integrator", "new[] { 1, 2, 3, 5, 10, 11, 17, 18 },", "new[] { 1, 2, 3, 5, 10, 11, 17 },", "drop_move", "drop_force"),
    ("m12_chain_without_push", "if ((caps & W.CAPS_PUSH) == 0) caps &= ~NEEDS_PUSH;", "if ((caps & W.CAPS_PUSH) == 0) caps &= ~W.CAPS_DEATH;",
     "drop_force", "drop_move"),
    ("m12_force_receipt_dropped", "if (g.VcChRow >= 0) g.ChS.Raw[g.VcChRow + 8] = ServerNow();", "", "chain_force", "pushes"),
    ("m12_force_creation_dropped", "if (g.ScChRow >= 0) g.ChO.Raw[g.ScChRow + 6] = stamp;", "", "chain_force", "pushes"),
    ("m13_death_without_push", "if ((caps & W.CAPS_PUSH) == 0) caps &= ~NEEDS_PUSH;", "if ((caps & W.CAPS_PUSH) == 0) caps &= ~W.CAPS_CHAIN;",
     "drop_force", "drop_move"),
    ("m13_force_identity_dropped", "RecentForce(own, pid, sInit, cord, snd, stamp);", "", "death_force", "death_oob"),
]
# M1's control: the emitted fault field serialized as 0 (CostRow), in the throwing build
M1_SER_OLD = "E.Clamp(c[3], 0, 99999999) };"
M1_SER_NEW = "0L };"


def main():
    root = DEFAULT_SERVER
    if "--server-root" in sys.argv:
        root = sys.argv[sys.argv.index("--server-root") + 1]
    api = os.path.join(root, "backend", "api")
    if "--server-api" in sys.argv:
        api = sys.argv[sys.argv.index("--server-api") + 1]
    red = sys.argv[sys.argv.index("--red") + 1] if "--red" in sys.argv else None
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    print("commit", head, "tree", "clean" if not dirty else "DIRTY")
    print("server reference", api, "combat_measures.py sha256", sha(os.path.join(api, "combat_measures.py")),
          "review_measures.py sha256", sha(os.path.join(api, "review_measures.py")))
    print("python", sys.version.split()[0])
    cm = load_server(api)
    print("reference:", ("the server's amended budget_record (COMBAT_WIRE_A1 cost_rows %s)" % cm.COMBAT_WIRE_A1.get("cost_rows"))
          if server_amended(cm) else "the client-side mirror (this server reference carries no amendment: owed to the server lane)")
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
        for n, _ in CHECKS:
            print("%s %s at %s: %s" % ("RED  " if not res[n][0] else "green", n, red[:8], res[n][1][:400]))
        for name in VNAMES:
            v = run_variant(dll, "red", name)
            vr = check_variant(cm, name, *v)
            print("%s %s at %s: %s" % ("RED  " if not vr[0] else "green", name, red[:8], vr[1][:400]))
        print("errors:", (r1.get("err"), r2.get("err")))
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
    bl = boot_of(r1)
    bok = bl.startswith("I ") and "attached 19/19" in bl and "frame 2/2" in bl and "producers push vchg chain death" in bl
    print("%s boot line: %s" % ("PASS" if bok else "FAIL", bl[:160] + ("..." if len(bl) > 160 else "")))
    dok = r1["dropix"] is not None and r1["dropix"][1] == 0 and r1["dropix"][0] == r1["dropix"][2] == 16
    print("%s drop constants against the layout names: %s" % ("PASS" if dok else "FAIL", r1["dropix"]))
    ok = ok and bok and dok

    # the variants: capability bits, M7, M6, M9
    vruns = {}
    for name, _opts, _fn in VARIANTS:
        vruns[name] = run_variant(dll, "v", name)
        vok, detail = check_variant(cm, name, *vruns[name])
        print("%s variant %s: %s" % ("PASS" if vok else "FAIL", name, detail))
        ok = ok and vok

    # fixtures: the A1 set (fixtures/), the legacy set (fixtures-legacy/)
    current = {"seat1": r1, "seat2": r2}
    for name in VFIXTURES:
        current["%s.seat1" % name] = vruns[name][0]
    fdir = os.path.join(HERE, "fixtures")
    if "--write-fixtures" in sys.argv:
        os.makedirs(fdir, exist_ok=True)
        for fn_, r in current.items():
            open(os.path.join(fdir, "%s.rec.txt" % fn_), "wb").write(r["text"][0].encode("ascii"))
        print("fixtures written: fixtures/%s" % ", ".join("%s.rec.txt" % k for k in current))
    fok = True
    for fn_, r in current.items():
        p = os.path.join(fdir, "%s.rec.txt" % fn_)
        if not os.path.exists(p):
            print("FAIL fixtures/%s.rec.txt absent (run once with --write-fixtures)" % fn_)
            fok = False
            continue
        t = read(p)
        frec = json.loads(t)
        # every value equal (the cost rows' two measured-time fields masked); the reference reproduces the bytes
        same = untimed(frec) == untimed(r["rec"][0])
        lay = mirror_check(cm, frec)
        byte = ref_budget(cm, frec) == t
        print("%s fixtures/%s.rec.txt: reproduced by this build %s; amended layout %s; reference budgeter reproduces it %s" % (
            "PASS" if same and not lay and byte else "FAIL", fn_, same, lay or "ok", byte))
        fok = fok and same and not lay and byte
    for i in (1, 2):
        p = os.path.join(HERE, "fixtures-legacy", "seat%d.rec.txt" % i)
        t = read(p)
        lrec = json.loads(t)
        try:
            cm.check_record(lrec)
            acc = True
        except Exception as ex:
            acc = "refused %s" % ex
        same = cm.budget_record(lrec) == t
        clear = lrec["caps"] & (CAPS_RX | CAPS_A1) == 0 and not any(k in lrec for k in A1_KEYS)
        print("%s fixtures-legacy/seat%d.rec.txt (the previous wire, bits 16 and 32 clear %s): server check_record %s, "
              "budget_record reproduces it %s" % ("PASS" if acc is True and same and clear else "FAIL", i, clear, acc, same))
        fok = fok and acc is True and same and clear
    ok = ok and fok

    # M1: the throwing build, read from the EMITTED cost rows
    text = read(SOURCE)
    planted, n = plant_source(text)
    ppath = os.path.join(WORK, "plant_CombatEvidence.cs")
    open(ppath, "wb").write(planted.encode("utf-8"))
    pdll = build("plant", combat=ppath)
    if pdll is None:
        print("BUILD FAILED (plant)")
        return 1
    print("throwing build: %d entries planted" % n)
    p0 = run(pdll, "plant_none", 1)
    same0 = p0.get("digest") == r1["digest"]
    print("%s the game witness digest: base %s, throwing build unarmed %s" % (
        "PASS" if same0 else "FAIL", r1["digest"][:16], (p0.get("digest") or "")[:16]))
    ok = ok and same0
    m1 = 0
    for i, row in enumerate(ROWS):
        good, detail = m1_row(pdll, "plant", i, r1["digest"])
        m1 += good
        ok = ok and good
        print("%s M1 %s: %s" % ("PASS" if good else "FAIL", row, detail))
    print("M1: %d of %d rows contained (identical game, every call faulted and counted in the emitted row, bits withheld)" % (m1, len(ROWS)))
    # M1's control: the serialization mutant (the emitted fault field written as 0) must turn M1 red
    cnt = text.count(M1_SER_OLD)
    sok = False
    if cnt == 1:
        sp = os.path.join(WORK, "mut_m1_fault_serialized_zero.cs")
        open(sp, "wb").write(plant_source(text.replace(M1_SER_OLD, M1_SER_NEW))[0].encode("utf-8"))
        sdll = build("mut_m1_fault_serialized_zero", combat=sp)
        if sdll:
            red_p1, d_red = m1_row(sdll, "mut_m1", ROWS.index("P1"), r1["digest"])
            u = run(sdll, "mut_m1_none", 1)
            sok = not red_p1 and u.get("digest") == r1["digest"]
            print("%s mutant m1_fault_serialized_zero: M1 P1 %s (%s); control digest %s" % (
                "CAUGHT" if sok else "MISSED", "FAIL" if not red_p1 else "PASS", d_red, "same" if u.get("digest") == r1["digest"] else "DIFFERS"))
    else:
        print("BAD mutant m1_fault_serialized_zero: anchor occurs %d times" % cnt)
    ok = ok and sok

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
        cache = {}
        t_ok, t_d = check_any(cm, mdll, "mut_" + name, target, cache)
        c_ok, c_d = check_any(cm, mdll, "mut_" + name, control, cache)
        hit = not t_ok and c_ok
        caught += hit
        ok = ok and hit
        print("%s mutant %s: target %s=%s; control %s=%s" % ("CAUGHT" if hit else "MISSED", name, target,
                                                            "FAIL" if not t_ok else "PASS", control, "PASS" if c_ok else "FAIL"))
        if not hit:
            print("    ", t_d[:300], "|", c_d[:300])
    print("mutants: %d of %d caught (and the M1 serialization mutant %s)" % (caught, len(MUTANTS), "caught" if sok else "MISSED"))

    unchanged = all(sha(p) == before[p] for p in TRACKED)
    print("tracked plugin files unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
