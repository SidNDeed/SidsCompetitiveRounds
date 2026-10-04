"""Combat evidence replay: synthetic games through the REAL client accountant
and budgeter, read back by the SERVER branch's own combat_measures.py (read
by path, never written; no bytecode is written beside it).

The client harness (../combat-evidence-client, mode "replay") plays seeded
games through plugin/CombatEvidenceCore.cs (both guns, several points,
volleys of one to three projectiles, leading non-first projectiles, own
repeat emissions, regenerations, every refill kind, refills with nothing
open, gate calls with no ammo init, a stamp clock that wraps, and every
fifth game far over the record bound) and writes each record whole and
budgeted. For every record the server must:

  * check_record accept the budgeted record (the route's layout check);
  * budget_record(whole) equal the client's budgeted bytes, and
    budget_record(budgeted) equal them again (the budget is a fixed point);
  * rebuild_faults(record, "s") and (record, "o") be empty on the budgeted
    record AND on the whole one: the server's own rebuild of every listed
    cycle agrees with the client's cycle summaries and whole-game totals.

Non-vacuity: the run prints how many records took the whole-totals branch,
and how many cycles had a tail, a regeneration, each reason bit. Mutants of
the accountant (copies of the core, CombatSource override) must each make a
rebuild fault appear (target) while check_record and both budget parities
still hold on the same records (control).

    python tools/tests/combat-evidence-replay/run_replay.py [--server-root DIR] [--n N]
"""
import hashlib
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PROJ = os.path.join(REPO, "tools", "tests", "combat-evidence-client", "CombatEvidenceTests.csproj")
CORE = os.path.join(REPO, "plugin", "CombatEvidenceCore.cs")
WORK = os.path.join(HERE, "work")
DEFAULT_SERVER = os.path.join(os.path.dirname(REPO), "scr-wt-combat-evidence-server")

# (name, old, new); old occurs exactly once in the core
MUTANTS = [
    ("tail_counts_markers", "if (_inTail && !marker) _tail++;", "if (_inTail) _tail++;"),
    ("exhaustion_late", "if (_count <= 0) { _exh = true; _sx = stamp; _inTail = true; }",
     "if (_count < 0) { _exh = true; _sx = stamp; _inTail = true; }"),
    ("regen_not_in_count", "_count += amt; _regen += amt; _nrg++;", "_regen += amt; _nrg++;"),
    ("volley_per_projectile", "if (!_hasVolLast || stamp != _volLast) { _vol++;", "if (true) { _vol++;"),
    ("in_reload_tail_only", "if (reloading) _inRl++;", "if (reloading && _inTail) _inRl++;"),
    ("gap_from_cycle_start", "_gaps[_gapN++] = Wrap(stamp - _sx);", "_gaps[_gapN++] = Wrap(stamp - _s0);"),
    ("found_reloading_late", "if (reloading) _foundRl = true;", "if (reloading && _count > 1) _foundRl = true;"),
    ("gate_reloading_forced", "(fl & W.FL_FORCED) == 0) _gateRl = true;", "(fl & W.FL_FORCED) >= 0) _gateRl = true;"),
    ("marker_rep_zero_only", "bool marker = Own ? rep != -1 : am != -1;", "bool marker = Own ? rep == 0 : am != -1;"),
    ("noinit_not_gate", "Tot[TotIx(\"atk_noinit\")]++;\n                if (Own) Tot[TotIx(\"gate\")]++; else Tot[TotIx(\"atk_msg\")]++;",
     "Tot[TotIx(\"atk_noinit\")]++;"),
    ("excess_without_regen", "long excess = Math.Max(0, _n - _mag - _regen - tail);", "long excess = Math.Max(0, _n - _mag - tail);"),
    ("short_gap_any_end", "if (timer && g0 >= 0 && g0 < _rexp) why |= W.WHY_SHORT_GAP;", "if (g0 >= 0 && g0 < _rexp) why |= W.WHY_SHORT_GAP;"),
    ("omitted_groups_uncounted", "else GroupsOmitted++;", "else { }"),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_server(root):
    sys.path.insert(0, os.path.join(root, "backend", "api"))
    import combat_measures
    return combat_measures


def build(tag, core):
    out = os.path.join(WORK, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep, "-p:CombatSource=" + core]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "CombatEvidenceTests.dll")


def produce(dll, tag, n):
    path = os.path.join(WORK, tag + ".records.tsv")
    r = subprocess.run(["dotnet", dll, "replay", path, str(n)], capture_output=True, text=True)
    print("  client:", r.stdout.strip().replace("\n", "\n  client: "))
    if r.returncode != 0 or not os.path.isfile(path):
        return None
    rows = []
    for line in open(path, "rb").read().decode("ascii").split("\n"):
        if line:
            name, full, budgeted = line.split("\t")
            rows.append((name, full, budgeted))
    return rows


def judge(cm, rows, stats=None):
    """(serializer faults, rebuild faults): lists of (record, what)."""
    ser, reb = [], []
    for name, full, budgeted in rows:
        whole, rec = json.loads(full), json.loads(budgeted)
        try:
            cm.check_record(rec)
        except Exception as ex:   # the route's refusal
            ser.append((name, "check_record: %s" % ex))
        if cm.budget_record(whole) != budgeted:
            ser.append((name, "budget_record(whole) differs from the client's bytes"))
        if cm.budget_record(rec) != budgeted:
            ser.append((name, "the budget is not a fixed point"))
        for which, r in (("budgeted", rec), ("whole", whole)):
            for side in ("s", "o"):
                f = cm.rebuild_faults(r, side)
                if f:
                    reb.append((name, "%s %s: %s" % (which, side, ",".join(f))))
        if stats is not None:
            for side in ("s", "o"):
                cyc = cm.rebuild_side(rec, side)
                stats["cycles"] += len(cyc)
                stats["cx"] += len(rec["cx_" + side])
                whole_branch = rec["omit"]["sh_" + side] == 0 and all(c["not_run"] is None for c in cyc)
                stats["whole_totals_branch"] += whole_branch
                stats["omitted_groups"] += rec["omit"]["sh_" + side]
                for c in cyc:
                    if c["not_run"] is not None:
                        stats["not_run"] += 1
                        continue
                    stats["tail"] += c["tail"] > 0
                    stats["regen"] += (c["regen"] or 0) > 0
                    stats["exhausted"] += c["exh"] is not None
                    for wname, bit in cm.WHY.items():
                        stats["why_" + wname] += (c["why"] & bit) != 0
            stats["over_bound_whole"] += len(full) > cm.W["record_max_bytes"]
    return ser, reb


def main():
    root = DEFAULT_SERVER
    n = 60
    if "--server-root" in sys.argv:
        root = sys.argv[sys.argv.index("--server-root") + 1]
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    server_head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head, "| server", root, server_head)
    cm = load_server(root)
    before = sha(CORE)
    ok = True

    dll = build("base", CORE)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    rows = produce(dll, "base", n)
    if rows is None or len(rows) != n:
        print("BASE: the client wrote no records")
        return 1
    stats = {k: 0 for k in ("cycles", "cx", "whole_totals_branch", "omitted_groups", "not_run", "tail", "regen", "exhausted",
                            "over_bound_whole")}
    for wname in cm.WHY:
        stats["why_" + wname] = 0
    ser, reb = judge(cm, rows, stats)
    for x in ser + reb:
        print("  FAULT %s: %s" % x)
    print("base: %d records; serializer faults %d; rebuild faults %d" % (len(rows), len(ser), len(reb)))
    print("non-vacuity:", ", ".join("%s=%d" % kv for kv in sorted(stats.items())))
    vacuous = [k for k, v in stats.items() if v == 0 and k != "not_run"]
    if vacuous:
        print("VACUOUS: no record exercised", vacuous)
    ok = ok and not ser and not reb and not vacuous

    core = open(CORE, "rb").read().decode("utf-8")
    caught = 0
    for name, old, new in MUTANTS:
        if core.count(old) != 1:
            print("BAD mutant %s: anchor occurs %d times" % (name, core.count(old)))
            ok = False
            continue
        path = os.path.join(WORK, "mut_" + name + ".cs")
        open(path, "wb").write(core.replace(old, new).encode("utf-8"))
        mdll = build("mut_" + name, path)
        mrows = produce(mdll, "mut_" + name, n) if mdll else None
        if mrows is None:
            print("BAD mutant %s: no records" % name)
            ok = False
            continue
        mser, mreb = judge(cm, mrows)
        hit = bool(mreb) and not mser
        caught += hit
        ok = ok and hit
        print("%s mutant %s: rebuild faults %d (first: %s); control (layout check and budget parity) faults %d" % (
            "CAUGHT" if hit else "MISSED", name, len(mreb), mreb[0] if mreb else "-", len(mser)))
    print("mutants: %d of %d caught" % (caught, len(MUTANTS)))
    unchanged = sha(CORE) == before
    print("tracked core unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
