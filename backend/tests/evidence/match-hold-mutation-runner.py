"""Mutation evidence for the 2v2 and 1v2 readmission server half (Stage 2
design V3): every planted defect turns its named test red, and an inert edit
at the same site keeps the same selection green.

Each mutant is a COPY of backend/api/match_hold.py and match_report_window.py
written under MATCH_HOLD_SCRATCH/<mutant id>/{mutant,control}/ with exact
anchor replacements (every anchor must occur exactly once in the file it
edits, or the runner refuses). The tracked files are only ever read. The
test modules put MATCH_HOLD_SRC first on sys.path and their module census
proves the copy is the module the routes run (#742, #838); the census must
stay green inside a mutant run, so a red census is a runner failure, not a
kill.

usage: python match-hold-mutation-runner.py --piece N2 [--piece N3 ...]
       python match-hold-mutation-runner.py --mutant M1.7 [--mutant ...]
MATCH_HOLD_SCRATCH must name an existing directory outside the worktree.
Exit 0 only when every mutant is red with a named selected test failing and
every control is green.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", ".."))
API = os.path.join(BACKEND, "api")
TESTS = os.path.join(BACKEND, "tests")
SQL = os.path.join(BACKEND, "sql")
MODULES = ("match_hold.py", "match_report_window.py")

HOLD_T = "test_match_hold_pg.py"
WIN_T = "test_match_report_window.py"
MIG_T = "test_match_hold_migration_pg.py"
M383 = "383_match_hold_stage2.sql"

# id: (piece, module file, [(anchor, mutant text)], [(anchor, control text)],
#      test file, -k selection of the tests that must fail)
MUTANTS = {
    # N2 - the game id chain and the hold latch
    "M1.7": ("N2", "match_hold.py",
             [('"   AND prev_game = CAST(:prev AS uuid)"), key)',
               '"   AND id = CAST(:prev AS uuid)"), key)')],
             [('"   AND prev_game = CAST(:prev AS uuid)"), key)',
               '"   AND  prev_game = CAST(:prev AS uuid)"), key)')],
             HOLD_T, "t1_4_game_id_chain"),
    "M1.8": ("N2", "match_hold.py",
             [("    if found is not None:\n        await db.commit()",
               "    if False:\n        await db.commit()")],
             [("    if found is not None:\n        await db.commit()",
               "    if (found is not None):\n        await db.commit()")],
             HOLD_T, "t1_4_game_id_chain"),
    "M1.L1": ("N2", "match_hold.py",
              [('hold_v2 = (SELECT count(*) = {n} FROM',
                'hold_v2 = (SELECT count(*) >= 1 FROM')],
              [('hold_v2 = (SELECT count(*) = {n} FROM',
                'hold_v2 = (SELECT count(*)  = {n} FROM')],
              HOLD_T, "hold_latch_helper"),
    "M1.L2": ("N2", "match_hold.py",
              [('        f" WHERE s.id = CAST(:sid AS uuid)"\n'
                '        f"   AND s.hold_room IS DISTINCT FROM CAST(:room AS varchar)")',
                '        f" WHERE s.id = CAST(:sid AS uuid)")')],
              [('        f" WHERE s.id = CAST(:sid AS uuid)"\n'
                '        f"   AND s.hold_room IS DISTINCT FROM CAST(:room AS varchar)")',
                '        f" WHERE s.id = CAST(:sid AS uuid)"\n'
                '        f"   AND  s.hold_room IS DISTINCT FROM CAST(:room AS varchar)")')],
              HOLD_T, "hold_latch_helper"),
    # N3 (the constraint half of S2): one hold per seat per game, in the file
    "M2.1": ("N3", M383,
             [("  CONSTRAINT uq_msh_room_game_player UNIQUE (room_name, game_id, player_id),\n",
               ""),
              ("            ('match_seat_holds', 'uq_msh_room_game_player'),\n", "")],
             [("  CONSTRAINT uq_msh_room_game_player UNIQUE (room_name, game_id, player_id),\n",
               "  CONSTRAINT  uq_msh_room_game_player UNIQUE (room_name, game_id, player_id),\n")],
             MIG_T, "first_apply_rerun"),
}


def _plant(src_text, edits, mid, kind):
    out = src_text
    for anchor, repl in edits:
        n = out.count(anchor)
        if n != 1:
            raise SystemExit(f"REFUSED {mid} {kind}: anchor occurs {n} times: {anchor!r}")
        out = out.replace(anchor, repl)
    if out == src_text:
        raise SystemExit(f"REFUSED {mid} {kind}: the edit changed nothing")
    return out


def _write_copy(dest, module, text_out):
    os.makedirs(dest, exist_ok=False)
    if module.endswith(".sql"):
        with open(os.path.join(dest, module), "w", encoding="utf-8", newline="") as f:
            f.write(text_out)
        return
    for m in MODULES:
        p = os.path.join(API, m)
        if not os.path.exists(p):
            continue
        if m == module:
            with open(os.path.join(dest, m), "w", encoding="utf-8", newline="") as f:
                f.write(text_out)
        else:
            shutil.copyfile(p, os.path.join(dest, m))


def _run(dest, module, test_file, sel):
    env = dict(os.environ)
    env.pop("MATCH_HOLD_SRC", None)
    env.pop("MATCH_HOLD_M383", None)
    if module.endswith(".sql"):
        env["MATCH_HOLD_M383"] = os.path.join(dest, module)
    else:
        env["MATCH_HOLD_SRC"] = dest
    cmd = [sys.executable, "-m", "pytest", "--rootdir", BACKEND, "-p", "no:cacheprovider",
           "-q", "-rf", os.path.join(TESTS, test_file), "-k", f"census or ({sel})"]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    out = p.stdout + p.stderr
    failed = sorted(set(re.findall(r"^FAILED \S+::(\w+)", out, re.M)))
    return p.returncode, failed, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--piece", action="append", default=[])
    ap.add_argument("--mutant", action="append", default=[])
    a = ap.parse_args()
    scratch = os.environ.get("MATCH_HOLD_SCRATCH") or ""
    if not scratch or not os.path.isdir(scratch):
        raise SystemExit("REFUSED: MATCH_HOLD_SCRATCH must name an existing directory")
    if os.path.normcase(os.path.abspath(scratch)).startswith(
            os.path.normcase(os.path.dirname(BACKEND))):
        raise SystemExit("REFUSED: MATCH_HOLD_SCRATCH is inside the worktree")
    ids = [m for m, v in MUTANTS.items() if v[0] in a.piece] + a.mutant
    if not ids:
        raise SystemExit("REFUSED: no mutant selected")
    bad = 0
    for mid in ids:
        piece, module, medits, cedits, test_file, sel = MUTANTS[mid]
        src_dir = SQL if module.endswith(".sql") else API
        with open(os.path.join(src_dir, module), encoding="utf-8", newline="") as f:
            base = f.read()
        root = os.path.join(scratch, mid)
        if os.path.exists(root):
            raise SystemExit(f"REFUSED {mid}: {root} exists (never overwrite evidence)")
        mdir, cdir = os.path.join(root, "mutant"), os.path.join(root, "control")
        _write_copy(mdir, module, _plant(base, medits, mid, "mutant"))
        _write_copy(cdir, module, _plant(base, cedits, mid, "control"))
        mrc, mfail, mout = _run(mdir, module, test_file, sel)
        crc, cfail, cout = _run(cdir, module, test_file, sel)
        with open(os.path.join(root, "mutant.out"), "w", encoding="utf-8") as f:
            f.write(mout)
        with open(os.path.join(root, "control.out"), "w", encoding="utf-8") as f:
            f.write(cout)
        killed = (mrc == 1 and mfail and not any("census" in t for t in mfail)
                  and all(re.search(sel.replace(" or ", "|"), t) for t in mfail))
        green = crc == 0 and not cfail
        verdict = "OK" if (killed and green) else "BAD"
        bad += verdict != "OK"
        print(f"{verdict} {mid} {piece} mutant rc={mrc} red={','.join(mfail) or '-'}"
              f" | control rc={crc} {'green' if green else 'NOT GREEN ' + ','.join(cfail)}")
    print(f"SUMMARY {len(ids) - bad}/{len(ids)} mutants red with controls green")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
