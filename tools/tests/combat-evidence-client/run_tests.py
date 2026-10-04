"""Combat evidence, client half: the REAL plugin/CombatEvidenceCore.cs against
the SERVER branch's canonical fixture set (backend/tests/fixtures/
combat_evidence, read by path, never written), which is the oracle:

  * gen_wire.py --check: plugin/CombatEvidenceWire.g.cs equals the server's
    COMBAT_WIRE (the layout is the server's source of truth);
  * fixtures: every budget input round-trips, and the client budgeter's
    output equals the server's .out.txt byte for byte and passes the layout
    check;
  * proof, sign, integrator, steering: the byte proof, the signing canonical
    and HMAC, the single-precision flight bit for bit and its residuals, the
    homing and target bounce references;
  * units: crafted budget ties, protected reason bits, the shot cap, the key
    loop bound (cases the fixtures do not reach);
  * accountant: every fixture group replayed through the client's cycle
    accountant reproduces the fixture's groups (at the caps), cycle
    summaries, omit counts and totals.

Then build mutated COPIES of the core (work/, CombatSource override; the
tracked file is never written) and require each mutant's target mode to FAIL
and its control mode to PASS. Exit 0 only when everything holds.

    python tools/tests/combat-evidence-client/run_tests.py [--server-root DIR]
"""
import hashlib
import os
import subprocess
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PROJ = os.path.join(HERE, "CombatEvidenceTests.csproj")
CORE = os.path.join(REPO, "plugin", "CombatEvidenceCore.cs")
WORK = os.path.join(HERE, "work")
DEFAULT_SERVER = os.path.join(os.path.dirname(REPO), "scr-wt-combat-evidence-server")
MODES = ["fixtures", "proof", "sign", "integrator", "steering", "accountant", "units"]

# (name, old text, new text, target mode, control mode); old occurs exactly once in the core
MUTANTS = [
    ("budget_tie_latest", "if (Count(r, k) > 0 && (best == null || Count(r, k) > Count(r, best))) best = k;",
     "if (Count(r, k) > 0 && (best == null || Count(r, k) >= Count(r, best))) best = k;", "units", "integrator"),
    ("protected_fewest_bits_reversed", "bool less = !found || kw < bw ||", "bool less = !found || kw > bw ||", "units", "steering"),
    ("protected_latest_reversed", "long kw = Popcount(e[CX_WHY]), ke = CxExcess(e), ki = -i, kp = -p;",
     "long kw = Popcount(e[CX_WHY]), ke = CxExcess(e), ki = i, kp = -p;", "fixtures", "accountant"),
    ("widest_always_hi", "return lo.ToString(CultureInfo.InvariantCulture).Length >= hi.ToString(CultureInfo.InvariantCulture).Length ? lo : hi;",
     "return hi;", "proof", "sign"),
    ("canonical_seats_swapped", "return W.SIGN_PREFIX + seat + \":\" + other + \":\"", "return W.SIGN_PREFIX + other + \":\" + seat + \":\"",
     "sign", "fixtures"),
    ("drag_unclamped", "float num = F(Math.Min(Math.Max(dt, 0f), clamp));", "float num = F(Math.Max(dt, 0f));", "integrator", "fixtures"),
    ("f32_rounding_dropped", "x = F(x + (double)F((double)F((double)vx * d) * p.Mult));", "x = F(x + (double)vx * d * p.Mult);",
     "integrator", "accountant"),
    ("residual_perp_axis", "perp = Math.Abs(dx * uy - dy * ux);", "perp = Math.Abs(dx * ux - dy * uy);", "integrator", "proof"),
    ("homing_cone_ignored", "on = ang < W.HOMING_CONE_DEG;", "on = ang < 180f;", "steering", "integrator"),
    ("bounce_no_nudge", "float nudge = F(W.BOUNCE_NUDGE);", "float nudge = 0f;", "steering", "accountant"),
    ("exhaustion_below_zero", "if (_count <= 0) { _exh = true; _sx = stamp; _inTail = true; }",
     "if (_count < 0) { _exh = true; _sx = stamp; _inTail = true; }", "accountant", "integrator"),
    ("over_mag_inclusive", "if (_n - tail > _mag + _regen) why |= W.WHY_OVER_MAG;", "if (_n - tail >= _mag + _regen) why |= W.WHY_OVER_MAG;",
     "accountant", "steering"),
    ("gate_not_counted", "if (Own) { Tot[TotIx(\"emit\")]++; if (rep == 0) Tot[TotIx(\"gate\")]++; }",
     "if (Own) { Tot[TotIx(\"emit\")]++; }", "accountant", "fixtures"),
    ("regen_k_late", "_regs[o] = Clamp(_n, 0, 99999);", "_regs[o] = Clamp(_n + 1, 0, 99999);", "accountant", "sign"),
    ("cx_cap_overrun", "if (_nCx < _cxCap)", "if (_nCx <= _cxCap)", "accountant", "integrator"),
    ("shot_cap_overrun", "if (_listed && _nShots[_gi] < _shotCap)", "if (_listed && _nShots[_gi] <= _shotCap)", "units", "proof"),
]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


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


def run(dll, *args):
    r = subprocess.run(["dotnet", dll] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def main():
    root = DEFAULT_SERVER
    if "--server-root" in sys.argv:
        root = sys.argv[sys.argv.index("--server-root") + 1]
    fixtures = os.path.join(root, "backend", "tests", "fixtures", "combat_evidence")
    os.makedirs(WORK, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    server_head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print("commit", head, "| server", root, server_head)
    before = sha(CORE)
    ok = True

    g = subprocess.run([sys.executable, os.path.join(HERE, "gen_wire.py"), "--server-root", root, "--check"], capture_output=True, text=True)
    print(g.stdout.strip(), g.stderr.strip())
    ok = ok and g.returncode == 0

    dll = build("base", CORE)
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    for mode in MODES:
        rc, out = run(dll, mode, fixtures)
        print(out)
        ok = ok and rc == 0

    core = open(CORE, "rb").read().decode("utf-8").replace("\r\n", "\n")
    caught = 0
    for name, old, new, target, control in MUTANTS:
        n = core.count(old)
        if n != 1:
            print("BAD mutant %s: anchor occurs %d times" % (name, n))
            ok = False
            continue
        path = os.path.join(WORK, "mut_" + name + ".cs")
        open(path, "wb").write(core.replace(old, new).encode("utf-8"))
        mdll = build("mut_" + name, path)
        if mdll is None:
            print("BAD mutant %s: does not build" % name)
            ok = False
            continue
        trc, tout = run(mdll, target, fixtures)
        crc, _ = run(mdll, control, fixtures)
        hit = trc != 0 and crc == 0
        caught += hit
        ok = ok and hit
        print("%s mutant %s: target %s=%s; control %s=%s" % ("CAUGHT" if hit else "MISSED", name, target,
                                                            "FAIL" if trc else "PASS", control, "PASS" if crc == 0 else "FAIL"))
        if not hit:
            print("   ", tout[-1500:].replace("\n", "\n    "))
    print("mutants: %d of %d caught" % (caught, len(MUTANTS)))
    unchanged = sha(CORE) == before
    print("tracked core unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
