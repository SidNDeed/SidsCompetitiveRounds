"""Discord fix round 4: the mutation campaign for round 4's fixes.

Round 3's runner (discord-fix-r3-mutation-runner.py) with two changes:

- the rows are round 4's: M1 (the journal's one locked read-modify-write),
  LOW 2 (a settled entry revealed for its journaled player), LOW 3 (one
  eligibility domain), LOW 5 (the notice queue and feed on that domain),
  LOW 4 (the pre-send check) and LOW 1 (the delivery-attempt mark).
- each mutation runs the tests it names (pytest node ids in its target
  file), not the whole file; the unmutated control of every target file
  still runs WHOLE, and must pass, before any mutation runs.

    python backend/tests/evidence/discord-fix-r4-mutation-runner.py \\
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
    # -- round 4, M1: every journal change is one locked read-modify-write --------------------------
    multi("M1r4-a", "r4", "the write-ahead entry is written from the command's own earlier read (round 3's shape)",
          [(BOT, "_pc_buy_and_show", "    readable, held = _pc_buy_entry(me)\n",
            "    pending = _pc_buy_pending()   # mutation M1r4-a\n"
            "    readable, held = pending is not None, (pending or {}).get(me)\n"),
           (BOT, "_pc_buy_and_show", '        if not _pc_buy_record(me, {**key, "player": player}):\n',
            '        if not _pc_buy_pending_write({**pending, me: {**key, "player": player}}):   # M1r4-a\n')],
          PACK, ["test_m1r4_two_buyers_racing_the_journal_keep_each_others_nonces"]),
    mutation("M1r4-b", "r4", "the journal lock removed", BOT, "_pc_buy_journal_lock",
             "_pc_buy_journal_lock = threading.Lock()\n",
             '_pc_buy_journal_lock = type("NoLock", (), {"__enter__": lambda s: None, "__exit__": lambda s, *a: None,'
             ' "locked": lambda s: False})()   # mutation M1r4-b\n',
             PACK, ["test_m1r4_the_journal_lock_serializes_two_writers_on_two_threads"]),
    # -- round 4, LOW 2: a settled entry is revealed for the player it was bought for ------------------
    mutation("L2r4-a", "r4", "the settled reveal reads through the Discord id's current player", BOT, "_pc_buy_deliver",
             '                                      if earlier else head, player=entry["player"],\n',
             "                                      if earlier else head,   # mutation L2r4-a\n",
             PACK, ["test_low2r4_a_settled_entry_waits_for_its_player_and_is_revealed_when_the_binding_matches"]),
    # -- round 4, LOW 3: one eligibility domain, the lock's ---------------------------------------------
    mutation("L3r4-a", "r4", "the speculative entrant counted again", TOURN, "_ELIGIBLE_ENTRANT_SQL",
             '"""ts.is_speculative = FALSE\n', '"""TRUE   -- mutation L3r4-a\n',
             QUORUM, ["test_low3r4_seven_confirmed_and_one_speculative_vote_is_no_quorum_on_any_surface",
                      "test_low3r4_the_eligible_entrants_are_the_confirmed_unbanned_ones"]),
    # -- round 4, LOW 5: the notices go to exactly the eligible entrants -------------------------------
    multi("L5r4-a", "r4", "the ban filter removed from the notice queue and the feed (round 3's gate, INSERT, check)",
          [(TOURN, "_queue_availability_notices",
            "        if len(await _eligible_entrant_ids(db, t.id)) < t.min_players:\n",
            "        if await _confirmed_count(db, t.id) < t.min_players:   # mutation L5r4-a\n"),
           (TOURN, "_queue_availability_notices",
            '            f" WHERE ts.tournament_id = :tid AND {_ELIGIBLE_ENTRANT_SQL} "\n',
            '            " WHERE ts.tournament_id = :tid AND ts.is_speculative = FALSE "   # mutation L5r4-a\n'),
           (MAIN, "_tournament_availability_live_sql", '            f" AND {_ELIGIBLE_ENTRANT_SQL})")\n',
            '            ")")   # mutation L5r4-a\n')],
          QUORUM, ["test_low5r4_the_notices_reach_the_eligible_entrants_the_banned_one_absent_the_replacement_present",
                   "test_low5r4_the_queue_counts_and_queues_only_eligible_entrants"]),
    # -- round 4, LOW 4: the pre-send check -------------------------------------------------------------
    mutation("L4r4-a", "r4", "the availability check sent without its pre-send check", BOT, "poll_tournament_notices",
             "                live = await _tavail_still_live(nid)\n",
             "                live = True   # mutation L4r4-a\n",
             QUORUM, ["test_low4r4_an_unsignup_between_the_feed_read_and_the_send_gets_no_dm"]),
    # -- round 4, LOW 1: the delivery-attempt mark ------------------------------------------------------
    mutation("L1r4-a", "r4", "the delivery-attempt mark removed", BOT, "_pc_buy_deliver",
             '                                      before_send=lambda: _pc_buy_mark_revealing(me, entry["nonce"]))\n',
             "                                      before_send=lambda: True)   # mutation L1r4-a\n",
             PACK, ["test_low1r4_a_reveal_whose_send_may_have_been_seen_is_never_posted_twice",
                    "test_low1r4_a_reveal_whose_mark_cannot_be_written_is_not_sent"]),
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
    w(f"=== discord-fix round 4 mutation campaign, start {now()}")
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
    jdir = tempfile.mkdtemp(prefix="dfr4-mut-")
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
