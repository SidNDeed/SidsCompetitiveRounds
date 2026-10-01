"""Discord fix round 5: the mutation campaign for round 5's fixes.

Round 4's runner (discord-fix-r4-mutation-runner.py) with its rows replaced
by round 5's: LOW 1 (every settled entry, marked or not, is checked against
its journaled player before anything is sent or forgotten), LOW 2 (the
pointer's entry leaves only after the acknowledged send) and the deploy
signal (the witness clause). Each mutation runs the tests it names; the
unmutated control of every target file runs WHOLE, and must pass, before
any mutation runs - that is the negative control.

    python backend/tests/evidence/discord-fix-r5-mutation-runner.py \\
        --tree <a clean worktree> --log <log file> [--only IDS] [--anchors-only]

The tree's files are edited in place and given back from byte copies taken
here, never through git (#290, #401). The campaign FAILS, and stops at once,
when a restore does not give a pre-image back byte for byte or the status is
not empty. The database gates come from the environment; the log names each
gate's database, never a host path."""
import argparse
import ast
import datetime
import hashlib
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

PACK = "backend/tests/test_discord_pack_open.py"
PULL = "backend/tests/test_discord_pull_post.py"
RULE = "backend/tests/test_discord_tournament_start_rule.py"
MARK = "backend/tests/test_health_discord_fix_marker.py"
BOT = "backend/discord_bot.py"
MAIN = "backend/api/main.py"
TOURN = "backend/api/tournaments.py"
QUORUM = "backend/tests/test_discord_tournament_quorum.py"
GATES = ("DISCORD_COLLECTION_TEST_PG_DSN", "PC_TRADES_TEST_PG_DSN", "FFA_TEST_PG_DSN", "LADDER_TEST_PG_DSN",
         "PC_EDITION_TEST_PG_DSN", "RJ_TRIAGE_TEST_PG_DSN", "SCR_MIGRATION_TEST_PG_DSN", "TEAM_DC_TEST_PG_DSN",
         "TICKET_REDACTION_TEST_PG_DSN")


def mutation(mid, rnd, what, path, span, old, new, target, red):
    return multi(mid, rnd, what, [(path, span, old, new)], target, red)


def multi(mid, rnd, what, edits, target, red):
    """A mutation of one or more places: edits [(path, span, old, new)]."""
    return {"id": mid, "round": rnd, "what": what,
            "edits": [{"path": p, "span": sp, "old": o, "new": n} for p, sp, o, n in edits],
            "target": target, "red": list(red)}


MUTATIONS = [
    # -- round 5, LOW 1: the player check comes before every branch that sends or forgets -------------
    mutation("L1r5-a", "r5", "the old order: the delivery mark's branch above the player check", BOT, "_pc_buy_deliver",
             "    bound, status, first = await _pc_buy_bound(ctx, me, entry)\n",
             '    if entry.get("revealing"):   # mutation L1r5-a\n'
             "        await ctx.send(_PC_BUY_SHOWN_BEFORE)\n"
             '        _pc_buy_forget(me, entry["nonce"])\n'
             "        return\n"
             "    bound, status, first = await _pc_buy_bound(ctx, me, entry)\n",
             PACK, ["test_low1r5_a_settled_entry_marked_or_not_stays_bound_to_its_journaled_player[marked]",
                    "test_low1r5_a_check_that_cannot_be_answered_sends_no_pointer_and_forgets_nothing[marked]"]),
    mutation("L1r5-b", "r5", "a check the api did not answer for the journaled player taken as bound", BOT,
             "_pc_buy_bound", '    return "unconfirmed", status, body\n',
             '    return "bound", status, body   # mutation L1r5-b\n',
             PACK, ["test_low1r5_a_check_that_cannot_be_answered_sends_no_pointer_and_forgets_nothing[marked]",
                    "test_low1r5_a_check_that_cannot_be_answered_sends_no_pointer_and_forgets_nothing[unmarked]"]),
    # -- round 5, LOW 2: the entry leaves only after the pointer's acknowledged send ---------------------
    mutation("L2r5-a", "r5", "the marked entry forgotten before the pointer's send", BOT, "_pc_buy_deliver",
             "        await ctx.send(_PC_BUY_SHOWN_BEFORE)\n"
             '        _pc_buy_forget(me, entry["nonce"])\n',
             '        _pc_buy_forget(me, entry["nonce"])   # mutation L2r5-a\n'
             "        await ctx.send(_PC_BUY_SHOWN_BEFORE)\n",
             PACK, ["test_low2r5_a_pointer_seen_before_its_send_failed_may_repeat_and_nothing_else_does"]),
    # -- round 5, the deploy signal: the witness clause ----------------------------------------------------
    mutation("W5-a", "r5", "the witness without the player-check clause (the build before)", BOT, "_pc_fix_ready_line",
             '                f"every bought pack is checked against its player before its pointer or reveal; "\n',
             "",
             MARK, ["test_the_witness_names_a_mounted_journal_and_its_unsettled_purchases"]),
]


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(tree, *args):
    return subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True, timeout=120).stdout


def span(text, name):
    """(start, end) character offsets of the top-level def or assignment `name` in LF text."""
    offs = [0]
    for line in text.split("\n"):
        offs.append(offs[-1] + len(line) + 1)
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            return offs[first - 1], offs[node.end_lineno]
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                return offs[node.lineno - 1], offs[node.end_lineno]
    raise LookupError(f"no top-level {name}")


def mutant_bytes(raw, m, path):
    """The bytes of `path` with every edit of mutation `m` on it applied, in
    order: each anchor must occur exactly once inside its span, and the
    result must parse. Line endings kept."""
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    norm = text.replace("\r\n", "\n")
    for ed in (ed for ed in m["edits"] if ed["path"] == path):
        s, e = span(norm, ed["span"])
        n = norm[s:e].count(ed["old"])
        if n != 1:
            raise ValueError(f"{m['id']}: anchor occurs {n} times inside {ed['span']}, expected 1")
        norm = norm[:s] + norm[s:e].replace(ed["old"], ed["new"], 1) + norm[e:]
    ast.parse(norm)
    return (norm.replace("\n", "\r\n") if crlf else norm).encode("utf-8")


def paths_of(m):
    return list(dict.fromkeys(ed["path"] for ed in m["edits"]))


def run_tests(tree, target, tag, jdir, names=None):
    """pytest over one test file in the tree, or over the named tests of it:
    (outcomes {name: outcome}, summary lines)."""
    junit = Path(jdir) / f"{tag}.xml"
    nodes = [target] if not names else [f"{target}::{n}" for n in names]
    proc = subprocess.run([sys.executable, "-m", "pytest", *nodes, "-q", "-rfE", "-p", "no:cacheprovider",
                           f"--junitxml={junit}"], cwd=str(tree), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=3600)
    outcomes = {}
    if junit.exists():
        for tc in ET.parse(junit).getroot().iter("testcase"):
            kinds = {child.tag for child in tc}
            outcome = ("failed" if "failure" in kinds else "error" if "error" in kinds
                       else "skipped" if "skipped" in kinds else "passed")
            outcomes[tc.get("name")] = outcome
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(("FAILED ", "ERROR "))]
    tail = [ln for ln in proc.stdout.splitlines() if ln.strip()][-1:] or ["(no output)"]
    return outcomes, lines + tail


def counts(outcomes):
    out = {}
    for o in outcomes.values():
        out[o] = out.get(o, 0) + 1
    return ", ".join(f"{k} {out[k]}" for k in sorted(out)) or "no tests"


def reddened(outcomes, name):
    return any(o in ("failed", "error") and (t == name or t.startswith(name + "["))
               for t, o in outcomes.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--only", nargs="*", default=None, help="mutation ids (a partial run says so in the log)")
    ap.add_argument("--anchors-only", action="store_true", help="resolve every anchor and stop; no test runs")
    args = ap.parse_args()
    tree = Path(args.tree).resolve()
    chosen = [m for m in MUTATIONS if args.only is None or m["id"] in args.only]
    log = open(args.log, "a", encoding="utf-8", newline="\n")

    def w(line=""):
        text = "".join(ch if ord(ch) < 128 else "?" for ch in line)
        print(text)
        log.write(text + "\n")
        log.flush()

    me = Path(__file__).read_bytes()
    w(f"=== discord-fix round 5 mutation campaign, start {now()}")
    w(f"=== runner sha256 {sha(me)}")
    w(f"=== tree <tree> at {git(tree, 'rev-parse', 'HEAD').strip()}")
    w(f"=== python {sys.version.split()[0]}; mutations chosen {len(chosen)} of {len(MUTATIONS)}"
      + ("" if args.only is None else " (a PARTIAL run: --only)"))
    for g in GATES:
        v = os.environ.get(g)
        w(f"=== gate {g} = {'database ' + v.rsplit('/', 1)[-1] if v else 'NOT SET'}")
    fonts = sorted(p.name for p in (tree / "backend/api/assets/fonts").glob("*") if p.suffix in (".ttf", ".otf"))
    w(f"=== font binaries present {len(fonts)}")
    start = git(tree, "status", "--porcelain")
    w(f"=== porcelain before anything: {start.strip()!r}")
    if start.strip():
        w("=== CAMPAIGN REFUSED: the tree is not clean")
        return 2
    # Every anchor, before any test runs.
    bad = []
    for m in chosen:
        for p in paths_of(m):
            try:
                mutant_bytes((tree / p).read_bytes(), m, p)
            except Exception as ex:
                bad.append(f"{m['id']} [{p}]: {type(ex).__name__}: {ex}")
    w(f"=== anchors checked {len(chosen)} mutations, {sum(len(m['edits']) for m in chosen)} edits, "
      f"unresolved {len(bad)}")
    for b in bad:
        w(f"    {b}")
    if bad:
        w("=== CAMPAIGN REFUSED: an anchor does not resolve exactly once")
        return 2
    if args.anchors_only:
        w("=== anchors only: every anchor resolves exactly once; no test ran")
        return 0
    jdir = tempfile.mkdtemp(prefix="dfr5-mut-")
    # The controls: every target file, unmutated, must pass whole.
    ok_controls = 0
    targets = sorted({m["target"] for m in chosen})
    for t in targets:
        outcomes, lines = run_tests(tree, t, "control-" + Path(t).stem, jdir)
        good = bool(outcomes) and all(o in ("passed", "skipped") for o in outcomes.values()) and \
            any(o == "passed" for o in outcomes.values())
        ok_controls += good
        digest = sha("\n".join(f"{k} {outcomes[k]}" for k in sorted(outcomes)).encode())
        w(f"--- control {t}: {counts(outcomes)}; sorted outcomes sha256 {digest}; {'PASS' if good else 'FAIL'}")
        for ln in lines:
            w(f"    {ln}")
    if ok_controls != len(targets):
        w(f"=== CAMPAIGN FAILED: {len(targets) - ok_controls} control run(s) did not pass whole")
        return 1
    n_equal = n_clean = n_caught = 0
    for m in chosen:
        files = paths_of(m)
        pre = {p: (tree / p).read_bytes() for p in files}
        mutated = {p: mutant_bytes(pre[p], m, p) for p in files}
        where = "; ".join(f"{ed['path']} :: {ed['span']}" for ed in m["edits"])
        w(f"--- {m['id']} ({m['round']}): {m['what']}  [{where}]  {now()}")
        try:
            for p in files:
                (tree / p).write_bytes(mutated[p])
            outcomes, lines = run_tests(tree, m["target"], m["id"], jdir, m["red"])
        finally:
            for p in files:
                (tree / p).write_bytes(pre[p])
        restored = {p: (tree / p).read_bytes() for p in files}
        porcelain = git(tree, "status", "--porcelain")
        equal = all(sha(restored[p]) == sha(pre[p]) for p in files)
        clean = not porcelain.strip()
        missing = [r for r in m["red"] if not reddened(outcomes, r)]
        caught = bool(m["red"]) and not missing
        n_equal += equal
        n_clean += clean
        n_caught += caught
        for p in files:
            w(f"    {p}")
            w(f"      pre-image sha256 {sha(pre[p])}")
            w(f"      mutated   sha256 {sha(mutated[p])}")
            w(f"      restored  sha256 {sha(restored[p])}  equal to the pre-image: "
              f"{'yes' if sha(restored[p]) == sha(pre[p]) else 'NO'}")
        w(f"    porcelain after the restore: {porcelain.strip()!r}  clean: {'yes' if clean else 'NO'}")
        w(f"    {m['target']}: {counts(outcomes)}")
        for ln in lines:
            w(f"    {ln}")
        w(f"    named red {len(m['red'])}, red {len(m['red']) - len(missing)}: {'CAUGHT' if caught else 'NOT CAUGHT'}"
          + (f"; still green: {missing}" if missing else ""))
        if not (equal and clean):
            w(f"=== CAMPAIGN FAILED at {m['id']}: a restore was unequal or the status dirty; nothing further runs")
            return 1
    verdict = n_equal == n_clean == n_caught == len(chosen)
    w(f"=== SUMMARY {now()}: {len(chosen)} mutations, {n_equal} restores equal, {n_clean} statuses clean, "
      f"{n_caught} caught (every named test red); controls {ok_controls} of {len(targets)} passed whole; "
      f"{'CAMPAIGN PASSED' if verdict else 'CAMPAIGN FAILED'}")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
