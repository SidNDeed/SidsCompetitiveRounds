"""Stage 2 (2v2 and 1v2 readmission) client rules harness.

Builds the REAL plugin/SeatDeckLog.cs, plugin/TeamHoldRules.cs and
plugin/TeamHoldNet.cs, as they ship, with Program.cs, and runs every scripted
fixture, each in its own process. Then mutants planted into COPIES of those
files (the tracked files are never written): each mutant's target fixture
must FAIL and its negative control fixture must PASS (#391). Exit 0 only when
everything holds.

    python tools/tests/rj-stage2-client/run_stage2.py --work <scratch dir> [--piece K0]

--work is required: every build output and mutant copy goes there, never into
the tree. --piece limits the fixtures and mutants to one piece (K0 to K6);
without it every piece runs. The K0 run also runs the S0 inventory check (the
application sites of RPCA_Pick and OFFLINE_Pick) and its negative control.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PLUGIN = os.path.join(REPO, "plugin")
PROJ = os.path.join(HERE, "Stage2Tests.csproj")
FILES = {"seat": "SeatDeckLog.cs", "rules": "TeamHoldRules.cs", "net": "TeamHoldNet.cs"}
PROPS = {"seat": "SeatSource", "rules": "RulesSource", "net": "NetSource"}

# Fixture name prefix per piece.
PIECES = {
    "K0": ("t01_", "t02_", "t0_"),
    "K1": ("t11_", "t12_", "t15_", "t16_", "t1_"),
    "K2": ("t23_", "t24_", "t25_", "t26_", "t29_", "t2_"),
    "K3": ("t33_", "t37_", "t38_", "t39_", "t3_"),
    "K4": ("t43_", "t45_", "t4_"),
    "K5": ("t52_", "t56_", "t58_", "t5_"),
    "K6": ("t6_",),
}

# (name, piece, file, [(old, new), ...], target fixture, control fixture);
# each old occurs exactly once in the file.
MUTANTS = [
    # K0, S0
    ("M0.1", "K0", "seat", [
        ("            for (int i = 0; i < it.Slots.Length; i++)\n                Commit(ViewKey(it.ViewId), it.Slots[i], it.Name);\n        }",
         "        }"),
        ("internal static void ObserveEndPick(int slot, string name) { }",
         "internal static void ObserveEndPick(int slot, string name) { Commit(\"e\" + SeatOf(slot).Deals, slot, name); }")],
     "t01_opening_2v2", "t02_dup_die"),
    ("M0.2", "K0", "seat", [
        ("_intents.Push(new Intent { ViewId = viewId, Name = name, Slots = slots ?? new int[0] });",
         "_intents.Push(new Intent { ViewId = viewId, Name = name, Slots = slots ?? new int[0] });\n"
         "            foreach (var s in slots ?? new int[0]) Commit(ViewKey(viewId), s, name);")],
     "t01_throw", "t01_opening_2v2"),
    ("M0.3", "K0", "seat", [
        ("internal static void ObserveEndPick(int slot, string name) { }",
         "internal static void ObserveEndPick(int slot, string name) { Commit(\"e\" + SeatOf(slot).Deals, slot, name); }")],
     "t01_duplicate", "t01_opening_2v2"),
    ("M0.4", "K0", "seat", [
        ("internal static void ObserveOfflinePick(int slot, string name) { _replays++; }",
         "internal static void ObserveOfflinePick(int slot, string name) { _replays++; Commit(\"o\" + _replays, slot, name); }")],
     "t01_replay", "t01_opening_2v2"),
    ("M0.5", "K0", "seat", [
        ("var c = TryClaim(slot, tuple, CLAIM_DEPART);",
         "var c = TryClaim(slot, \"departure|\" + tuple, CLAIM_DEPART);")],
     "t02_leave_then_die", "t02_dup_die"),
    ("M0.6", "K0", "seat", [
        ("return TryClaim(slot, tuple, CLAIM_PHOENIX);", "return Claim.Won;")],
     "t02_phoenix_then_leave", "t02_dup_die"),
    # K1, S1
    ("M1.1", "K1", "rules", [
        ("if (i == null || i.Pin == null || !i.Pin.Hold) return false;",
         "if (i == null || i.Pin == null || !(i.Pin.Hold || i.QuorumCapable)) return false;")],
     "t11_quorum_not_flag", "t11_gate_all_true"),
    ("M1.2", "K1", "rules", [
        ("if (i.IsSpec) return false;",
         "if (i.IsSpec) return false;\n                if (i.LocalUnauthorized || !i.LocalInMatch) return false;")],
     "t11_stale_cache", "t11_gate_all_true"),
    ("M1.3", "K1", "rules", [
        ("string mode = i.Pin.Mode;",
         "string mode = (i.RoomName ?? \"\").StartsWith(\"ovt_\") ? MODE_OVT : (i.RoomName ?? \"\").StartsWith(\"team_\") ? MODE_TEAM : \"\";")],
     "t11_hosted_lobby", "t11_gate_all_true"),
    ("M1.4", "K1", "rules", [
        ("catch { r = false; }", "catch { r = true; }")],
     "t12_three_clients_throw", "t11_gate_all_true"),
    ("M1.9", "K1", "rules", [
        ("internal const bool ViaMasterArm = true;", "internal const bool ViaMasterArm = false;")],
     "t15_2v2_team_down", "t15_2v2_partner_alive"),
    ("M1.10", "K1", "rules", [
        ("            if (observed != 'p' && observed != 'o' && observed != 'x') return Resolve.Wait;\n", "")],
     "t15_handover_wait", "t15_2v2_team_down"),
    # K1, lane-added: the extracted election must answer as the base callback did.
    ("M1.E", "K1", "rules", [
        ("int nonDcCount = 0, dcTeamCount = 1;", "int nonDcCount = 0, dcTeamCount = 0;")],
     "t1_dc_equiv", "t11_gate_all_true"),
    # K2, S2
    ("M2.8", "K2", "rules", [
        ("if (room.State == 'p') return Verdict.Act;", "return Verdict.Act;")],
     "t23_forged_b_e_x", "t23_verified_o"),
    ("M2.9", "K2", "rules", [
        ("if (observed != 'p' && observed != 'o' && observed != 'x') return Resolve.Wait;",
         "if (observed == '\\u0001') return Resolve.Wait;")],
     "t24_resolve_waits", "t24_promote_before_p"),
    ("M2.10", "K2", "rules", [
        ("if (P == Phase.Pending && now - PendingAt >= OpenTimeoutS) return End(now, \"no_answer\");", "")],
     "t24_404_by_room_ends", "t24_during_post"),
    ("M2.11", "K2", "rules", [
        ("if (FirstP >= 0 && VerifiedO < 0 && now - FirstP >= PendingS) return true;", "")],
     "t25_pending_ceiling", "t25_bind_ceiling"),
    ("M2.12", "K2", "rules", [
        ("Step.Visualize, Step.Wait1, Step.LoadNext, Step.Wait05, Step.Fence, Step.SyncUp,",
         "Step.Visualize, Step.Wait1, Step.LoadNext, Step.Wait05, Step.SyncUp,")],
     "t26_point_fenced", "t26_round_pick_inside"),
    # K2, lane-added: a state is not refuted before this client's own read answers.
    ("M2.E", "K2", "rules", [
        ("if (server == null) return Verdict.Inert;", "if (server == null) server = new TeamHoldNet.StateAnswer();")],
     "t23_read_pending", "t23_verified_o"),
    # K3, S3
    ("M3.5", "K3", "rules", [
        ("internal static string SnapshotDigest(Snapshot s) { return Fnv64Hex(s.Format()); }",
         "internal static string SnapshotDigest(Snapshot s) { return Fnv64Hex(s.HoldId + \":\" + s.G + \":\" + s.Boundary()); }")],
     "t33_mutations", "t33_honest"),
    ("M3.6", "K3", "rules", [
        ("if (expectedPeers < 1 || present < expectedPeers) return \"digest missing\";",
         "if (expectedPeers < 1 || present < expectedPeers - 1) return \"digest missing\";")],
     "t33_ovt_digest_absent", "t33_honest"),
    ("M3.7", "K3", "rules", [
        ("if (BoundaryDigest(snap.BR0, snap.BR1, snap.BP0, snap.BP1, snap.BNames) != serverBoundaryDigest) return \"boundary checkpoint mismatch\";", "")],
     "t33_colluding_duo", "t33_honest"),
    ("M3.16", "K3", "rules", [
        ("if (string.IsNullOrEmpty(rdt) || string.IsNullOrEmpty(holdId) || string.IsNullOrEmpty(verifierHex)) return false;",
         "return true;")],
     "t37_token", "t37_genuine"),
]

# The S0 inventory (V3 S0 step 2): every line under plugin/ that CALLS an
# application (not a patch attribute, a hook-table string or a comment) is in a
# file whose calls are FFA-only or spectator replays. Anything else names a new
# writer the seat log does not see.
CALL = re.compile(r'(\.OFFLINE_Pick\s*\(|\.RPCA_Pick\s*\(|RPC\(\s*"RPCA_Pick")')
ALLOWED_CALLERS = {"plugin/FfaMode.cs", "plugin/SpectatorSync.cs"}


def inventory(lines):
    bad = []
    for ln in lines:
        parts = ln.split(":", 2)
        if len(parts) < 3:
            continue
        path, code = parts[0], parts[2].strip()
        if code.startswith("//") or code.startswith("///") or code.startswith("*"):
            continue
        if CALL.search(code) and path not in ALLOWED_CALLERS:
            bad.append(ln)
    return bad


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def build(work, tag, overrides):
    out = os.path.join(work, tag)
    cmd = ["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
           "-p:IntermediateOutputPath=" + os.path.join(out, "obj") + os.sep,
           "-p:OutDir=" + os.path.join(out, "bin") + os.sep]
    for key, path in overrides.items():
        cmd.append("-p:" + PROPS[key] + "=" + path)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-4000:], r.stderr[-2000:])
        return None
    return os.path.join(out, "bin", "Stage2Tests.dll")


def run_case(dll, case):
    r = subprocess.run(["dotnet", dll, case], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--piece", default=None)
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    print("commit", head)
    print("tree", "clean" if not dirty else "DIRTY:\n" + dirty)
    print("piece", a.piece or "all")
    tracked = [f for f in FILES.values() if os.path.exists(os.path.join(PLUGIN, f))]
    before = {f: sha(os.path.join(PLUGIN, f)) for f in tracked}
    ok = True

    if a.piece in (None, "K0"):
        g = subprocess.run(["git", "-C", REPO, "grep", "-n", r"RPCA_Pick\|OFFLINE_Pick", "--", "plugin/"],
                           capture_output=True, text=True)
        lines = [ln for ln in g.stdout.splitlines() if ln.strip()]
        bad = inventory(lines)
        print("inventory: %d lines name RPCA_Pick or OFFLINE_Pick; %d unexpected application call(s)" % (len(lines), len(bad)))
        for ln in bad:
            print("  UNEXPECTED", ln)
        planted = lines + ["plugin/Plugin.cs:1:                acs.OFFLINE_Pick(new[] { player });"]
        control = inventory(planted)
        control_ok = len(control) == len(bad) + 1
        print("inventory negative control (one planted call in plugin/Plugin.cs): %s" % ("CAUGHT" if control_ok else "MISSED"))
        ok = ok and len(lines) > 0 and not bad and control_ok

    dll = build(work, "base", {})
    if dll is None:
        print("BUILD FAILED (base)")
        return 1
    listed = subprocess.run(["dotnet", dll, "--list"], capture_output=True, text=True).stdout.split()
    prefixes = PIECES[a.piece] if a.piece else tuple(p for v in PIECES.values() for p in v)
    cases = [c for c in listed if c.startswith(prefixes)]
    passed = 0
    for case in cases:
        rc, out = run_case(dll, case)
        print(out)
        passed += rc == 0
        ok = ok and rc == 0
    print("fixtures: %d of %d pass" % (passed, len(cases)))
    ok = ok and len(cases) > 0

    mutants = [m for m in MUTANTS if a.piece is None or m[1] == a.piece]
    caught = 0
    for name, piece, key, edits, target, control in mutants:
        src = os.path.join(PLUGIN, FILES[key])
        raw = open(src, "rb").read().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw
        good = True
        for old, new in edits:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            count = text.count(o)
            if count != 1:
                print("BAD mutant %s: anchor occurs %d times" % (name, count))
                good = False
                break
            text = text.replace(o, n)
        if not good:
            ok = False
            continue
        path = os.path.join(work, "mut_" + name.replace(".", "_") + "_" + FILES[key])
        open(path, "wb").write(text.encode("utf-8"))
        mdll = build(work, "mut_" + name.replace(".", "_"), {key: path})
        if mdll is None:
            print("BAD mutant %s: does not build" % name)
            ok = False
            continue
        if target not in listed or control not in listed:
            print("BAD mutant %s: fixture missing" % name)
            ok = False
            continue
        trc, tout = run_case(mdll, target)
        crc, _ = run_case(mdll, control)
        hit = trc != 0 and crc == 0
        caught += hit
        ok = ok and hit
        print("%s mutant %s (%s): target %s=%s; control %s=%s%s" % (
            "CAUGHT" if hit else "MISSED", name, piece, target, "FAIL" if trc else "PASS", control,
            "PASS" if crc == 0 else "FAIL", "" if hit else " (" + tout[-200:] + ")"))
    print("mutants: %d of %d caught" % (caught, len(mutants)))

    unchanged = all(sha(os.path.join(PLUGIN, f)) == before[f] for f in tracked)
    print("tracked plugin files unchanged:", unchanged)
    ok = ok and unchanged
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
