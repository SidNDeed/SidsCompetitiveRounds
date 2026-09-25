"""TICKET-REDACTION controls: plant each named mutation and its inert twin,
run the named checks, put the file back, record the result.

Every receive path, every read-back door, the /health marker and three
properties of the rule itself are carried below as DATA: the file, the exact
text a plant replaces, the text it writes, and the test nodes it must turn RED
(a mutant, which bypasses or weakens the function at that site) or leave
GREEN (an inert twin at the same site, #391). Each plant is printed as a
unified diff beside the run it produced, so the evidence is the diff and the
failing assertion, not a summary line (the shape of rj_triage_controls.py and
mutation_runner.py beside this file).

Per plant, refusing rather than continuing at each step:
  1. `git status --porcelain` over the worktree must be EMPTY;
  2. `git rev-parse HEAD` is printed (and compared with --expect-head);
  3. each edit's old text must occur EXACTLY ONCE in its file (#432);
  4. each target's sha256 is printed before the write;
  5. the edits are applied and printed as unified diffs;
  6. the check runs (pytest, the named nodes only, no bytecode written) and
     its outcome is read per node from pytest's JUnit XML: RED means EVERY
     named node FAILED on an assertion, GREEN means every named node PASSED.
     An ERROR node, a failure that is not an assertion, or a missing node is
     neither, and the plant FAILS;
  7. each target is restored from the bytes read in step 4, its sha256 must
     equal the one before, and the tree must be clean again;
  8. `RESULT <name>: RED as required | GREEN as required | FAILED (...)`.
Restoration is in a `finally`.

The route checks need TICKET_REDACTION_TEST_PG_DSN (the lane database):
without it every PostgreSQL test FAILS by design, which would read as a kill,
so the runner refuses to start when it is unset. It also refuses when a
__pycache__ directory exists under backend/api or backend/tests: a stale
compiled module could stand in for a planted source file.

Usage:
    python backend/tests/ticket_redaction_controls.py --log <path>
        [--expect-head REF] [--only NAME ...] [--sites]
--sites checks step 3 for every plant and writes nothing.
Exit codes: 0 every plant produced its required result, 1 at least one did
not, 2 the runner refused.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import namedtuple
from pathlib import Path

HERE = Path(__file__).resolve().parent
WT = HERE.parents[1]
MAIN = "backend/api/main.py"
RULE = "backend/api/log_redaction.py"
T = "test_ticket_redaction.py::"

R1 = T + "test_pg_submit_stores_the_marker_and_never_the_value"
DETAIL = T + "test_pg_legacy_row_detail_pane_serves_the_marker"
DOWNLOAD = T + "test_pg_legacy_row_log_download_serves_the_marker"
LIST = T + "test_pg_legacy_row_admin_list_serves_the_marker"
DISCORD = T + "test_pg_legacy_row_discord_feed_serves_the_marker"
EVENTS = T + "test_pg_legacy_row_event_feed_redacts_before_the_140_character_cut"
HEALTH = T + "test_pg_ticket_redaction_health_carries_the_marker_on_both_arms"
UNIT_SCRUB = T + "test_the_bundle_scrub_redacts_credentials_first_and_counts_them"
UNIT_31 = T + "test_31_hex_characters_are_untouched"
UNIT_LOWER = T + "test_lowercase_hex_is_a_ticket_and_is_digested_as_logged"
UNIT_KAT = T + "test_the_marker_matches_the_known_answer_and_the_client_format"

Plant = namedtuple("Plant", "name control kind what edits checks")
PLANTS = []


def mutant(name, control, what, edits, checks):
    PLANTS.append(Plant(name, control, "mutant", what, edits, checks))


def twin(name, control, what, edits, checks):
    PLANTS.append(Plant(name, control, "twin", what, edits, checks))


def pair(control, site, old, new, note, checks):
    """A mutant replacing `old` with `new`, and its twin: the same line with a
    trailing comment, which changes nothing the code does."""
    mutant(f"{control}-mutant", control, site, [(MAIN if control[0] != "U" else RULE, old, new)], checks)
    commented = old[:-1] + "  # " + note + "\n"
    twin(f"{control}-twin", control, f"a comment on the same line ({site})",
         [(MAIN if control[0] != "U" else RULE, old, commented)], checks)


# ── the receive path: POST /api/v1/bug-reports ────────────────────────────
pair("R1-log", "the bundle is stored without the rule",
     '    log_blob = await asyncio.to_thread(_logred.redact_credentials, (req.log_text or "").strip())\n',
     '    log_blob = (req.log_text or "").strip()\n',
     "the bundle's pass", [R1])
pair("R1-description", "the description is stored without the rule",
     "    description = _logred.redact_credentials(req.description.strip())\n",
     "    description = req.description.strip()\n",
     "the description's pass", [R1])
pair("R1-repro", "the repro steps are stored without the rule",
     '    repro_steps = _logred.redact_credentials((req.repro_steps or "").strip()) or None\n',
     '    repro_steps = (req.repro_steps or "").strip() or None\n',
     "the repro steps' pass", [R1])

# ── the bundle scrub: detail pane and log download (and the auto upload) ───
pair("S1-bundle", "the bundle scrub no longer applies the rule (its counter stays)",
     '    body, counts["credential"] = _logred.redact_credentials_counted(body)\n',
     '    counts["credential"] = 0\n',
     "credentials first", [DETAIL, DOWNLOAD, UNIT_SCRUB])

# ── read time, the free-text fields ───────────────────────────────────────
pair("D1-detail-description", "the detail pane serves the stored description raw",
     '    out["description"] = _logred.redact_credentials(out["description"])\n',
     '    out["description"] = out["description"]\n',
     "read-time rule", [DETAIL])
pair("D2-detail-repro", "the detail pane serves the stored repro steps raw",
     '    out["repro_steps"] = _logred.redact_credentials(out["repro_steps"])\n',
     '    out["repro_steps"] = out["repro_steps"]\n',
     "read-time rule", [DETAIL])
pair("D3-list", "the admin list serves the stored description raw",
     '                description=_logred.redact_credentials(r["description"]),\n',
     '                description=r["description"],\n',
     "read-time rule", [LIST])
pair("D4-discord", "the Discord feed serves the stored description raw",
     '                "description": _logred.redact_credentials(r["description"]),\n',
     '                "description": r["description"],\n',
     "read-time rule", [DISCORD])
pair("D5-events", "the event feed cuts at 140 characters BEFORE the rule",
     '                "description_snippet": (_logred.redact_credentials(r["description"]) or "")[:140],\n',
     '                "description_snippet": _logred.redact_credentials((r["description"] or "")[:140]),\n',
     "rule, then cut", [EVENTS])

# ── the /health marker, both arms and the value (the M1 shape) ─────────────
H_KEY = "                              ticket_redaction=_TICKET_REDACTION_MARKER,\n"
H_KEY_NOTE = "                              ticket_redaction=_TICKET_REDACTION_MARKER,  # the build marker\n"
H_CONNECTED = ("                              pc_steam_render=_pc_steam_render_word(),\n"
               "                              pc_fold=PC_FOLD, pc_pool_rule=int(_PC_POOL_RULE),\n"
               "                              ffa_hold_fences=_FFA_HOLD_FENCES,\n"
               "                              rj_triage=_RJ_TRIAGE_MARKER,\n")
H_DEGRADED = ('        return HealthResponse(status="degraded", database="disconnected", replica=IS_REPLICA,\n'
              "                              pc_fold=PC_FOLD, pc_pool_rule=int(_PC_POOL_RULE),\n"
              "                              ffa_hold_fences=_FFA_HOLD_FENCES,\n"
              "                              rj_triage=_RJ_TRIAGE_MARKER,\n")
mutant("H1-connected-arm-mutant", "H1", "the connected arm of /health no longer carries ticket_redaction",
       [(MAIN, H_CONNECTED + H_KEY, H_CONNECTED)], [HEALTH])
twin("H1-connected-arm-twin", "H1", "a comment on the connected arm's key line",
     [(MAIN, H_CONNECTED + H_KEY, H_CONNECTED + H_KEY_NOTE)], [HEALTH])
mutant("H2-degraded-arm-mutant", "H2", "the degraded arm of /health no longer carries ticket_redaction",
       [(MAIN, H_DEGRADED + H_KEY, H_DEGRADED)], [HEALTH])
twin("H2-degraded-arm-twin", "H2", "a comment on the degraded arm's key line",
     [(MAIN, H_DEGRADED + H_KEY, H_DEGRADED + H_KEY_NOTE)], [HEALTH])
mutant("H3-value-mutant", "H3", "the marker's value becomes 0",
       [(MAIN, "_TICKET_REDACTION_MARKER = 1\n", "_TICKET_REDACTION_MARKER = 0\n")], [HEALTH])
twin("H3-value-twin", "H3", "a comment on the marker's own line",
     [(MAIN, "_TICKET_REDACTION_MARKER = 1\n", "_TICKET_REDACTION_MARKER = 1  # the build marker\n")], [HEALTH])

# ── the rule itself ───────────────────────────────────────────────────────
RULE_LINE = 'TICKET_PATTERN = r"(Session Ticket:[ \\t]*)([0-9A-Fa-f]{32,})"\n'
pair("U1-floor", "the floor drops from 32 hex characters to 31",
     RULE_LINE, RULE_LINE.replace("{32,}", "{31,}"), "the floor", [UNIT_31])
pair("U2-case", "lowercase hex stops counting as a ticket",
     RULE_LINE, RULE_LINE.replace("[0-9A-Fa-f]", "[0-9A-F]"), "either case", [UNIT_LOWER])
pair("U3-digest", "the marker carries 7 digest characters instead of 8",
     '    digest8 = _lr_hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]\n',
     '    digest8 = _lr_hashlib.sha256(value.encode("utf-8")).hexdigest()[:7]\n',
     "first 8 hex", [UNIT_KAT])


# ── the runner ────────────────────────────────────────────────────────────


class Refused(Exception):
    pass


def git(*args) -> str:
    return subprocess.run(["git", "-C", str(WT), *args], capture_output=True, text=True,
                          check=True).stdout


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render(text_: str, crlf: bool) -> str:
    return text_.replace("\n", "\r\n") if crlf else text_


_TOTALS = re.compile(r"^=+ .* in [0-9.]+s.* =+$")


def node_outcomes(junit_path, checks):
    """{node: (outcome, detail)} for the named nodes, read from pytest's JUnit
    XML: a failure's detail is the crash message pytest recorded for it. (The
    -rA summary line drops that message whenever the node id alone fills the
    terminal width, which it does for these names.)"""
    got = {}
    try:
        root = ET.parse(junit_path).getroot()
    except (OSError, ET.ParseError):
        return got
    for case in root.iter("testcase"):
        node = case.get("classname", "").replace(".", "/") + ".py::" + case.get("name", "")
        if node not in checks:
            continue
        outcome, detail = "PASSED", ""
        for tag, word in (("failure", "FAILED"), ("error", "ERROR"), ("skipped", "SKIPPED")):
            el = case.find(tag)
            if el is not None:
                outcome, detail = word, " ".join((el.get("message") or "").split())
                break
        got[node] = (outcome, detail)
    return got


def run_checks(checks, timeout_s=900):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    fd, junit = tempfile.mkstemp(prefix="ticket-redaction-controls-", suffix=".xml")
    os.close(fd)
    try:
        proc = subprocess.run([sys.executable, "-B", "-m", "pytest", *checks, "-rA", "-p", "no:cacheprovider",
                               "--rootdir", str(HERE), "--junitxml", junit], cwd=str(HERE), env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout_s)
        output = proc.stdout + proc.stderr
        totals = [ln.strip() for ln in output.splitlines() if _TOTALS.match(ln.strip())]
        return proc.returncode, (totals[-1] if totals else "(no totals line)"), node_outcomes(junit, checks)
    finally:
        os.unlink(junit)


def verdict(plant, outcomes):
    missing = [c for c in plant.checks if c not in outcomes]
    if missing:
        return False, f"missing node(s) {missing}"
    if plant.kind == "mutant":
        bad = [c for c in plant.checks
               if outcomes[c][0] != "FAILED" or "assert" not in outcomes[c][1].lower()]
        return (not bad), ("RED as required" if not bad else f"not RED on an assertion: {bad}")
    bad = [c for c in plant.checks if outcomes[c][0] != "PASSED"]
    return (not bad), ("GREEN as required" if not bad else f"not GREEN: {bad}")


def plan(plant):
    """(path, before bytes, after bytes) per target file; step 3's refusal."""
    out = []
    for rel, old, new in plant.edits:
        path = WT / rel
        data = path.read_bytes()
        crlf = b"\r\n" in data
        text_ = data.decode("utf-8")
        old_r, new_r = render(old, crlf), render(new, crlf)
        n = text_.count(old_r)
        if n != 1:
            raise Refused(f"{plant.name}: old text occurs {n} times in {rel}, not exactly once")
        out.append((path, rel, data, text_.replace(old_r, new_r, 1).encode("utf-8")))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=False)
    ap.add_argument("--expect-head")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--sites", action="store_true")
    args = ap.parse_args(argv)
    plants = [p for p in PLANTS if not args.only or p.name in args.only]
    if args.only and len(plants) != len(args.only):
        print("refused: --only names a plant that does not exist")
        return 2
    if args.sites:
        try:
            for p in plants:
                plan(p)
                print(f"site ok: {p.name}")
        except Refused as ex:
            print(f"refused: {ex}")
            return 2
        print(f"{len(plants)} plants, every old text found exactly once")
        return 0
    if not args.log:
        print("refused: --log is required for a campaign")
        return 2
    log = open(args.log, "a", encoding="utf-8")

    def say(line=""):
        print(line)
        log.write(line + "\n")
        log.flush()

    if not os.environ.get("TICKET_REDACTION_TEST_PG_DSN"):
        say("refused: TICKET_REDACTION_TEST_PG_DSN is unset -- every live check would FAIL and read as a kill")
        return 2
    caches = [str(p) for p in (WT / "backend" / "api", HERE) if (p / "__pycache__").exists()]
    if caches:
        say(f"refused: __pycache__ present under {caches} -- remove it before a campaign")
        return 2
    results = []
    say(f"== ticket_redaction_controls: {len(plants)} plants ==")
    for p in plants:
        say("")
        say(f"-- PLANT {p.name} ({p.kind}, control {p.control}): {p.what}")
        try:
            status = git("status", "--porcelain")
            say(f"   1. git status --porcelain: {'EMPTY' if not status.strip() else 'NOT EMPTY'}")
            if status.strip():
                raise Refused("tree not clean")
            head = git("rev-parse", "HEAD").strip()
            say(f"   2. HEAD {head}")
            if args.expect_head and not head.startswith(args.expect_head):
                raise Refused(f"HEAD {head} is not --expect-head {args.expect_head}")
            targets = plan(p)
            say("   3. every old text found exactly once")
            for path, rel, before, after in targets:
                say(f"   4. sha256 before {rel}: {sha(before)}")
            try:
                for path, rel, before, after in targets:
                    path.write_bytes(after)
                    diff = difflib.unified_diff(before.decode("utf-8").splitlines(),
                                                after.decode("utf-8").splitlines(),
                                                f"a/{rel}", f"b/{rel}", lineterm="", n=1)
                    say("   5. planted:")
                    for line in diff:
                        say("      " + line)
                code, totals, outcomes = run_checks(p.checks)
                say(f"   6. pytest exit {code}: {totals}")
                for c in p.checks:
                    o, d = outcomes.get(c, ("MISSING", ""))
                    say(f"      {o} {c}" + (f" - {d[:300]}" if d else ""))
            finally:
                for path, rel, before, after in targets:
                    path.write_bytes(before)
                    now = sha(path.read_bytes())
                    say(f"   7. sha256 after  {rel}: {now} ({'equal' if now == sha(before) else 'DIFFERENT'})")
                    if now != sha(before):
                        raise Refused(f"{rel} did not restore")
                if git("status", "--porcelain").strip():
                    raise Refused("tree not clean after restore")
                say("      git status --porcelain: EMPTY")
            ok, why = verdict(p, outcomes)
            say(f"   8. RESULT {p.name}: {why if ok else 'FAILED (' + why + ')'}")
            results.append((p.name, ok))
        except Refused as ex:
            say(f"   REFUSED {p.name}: {ex}")
            log.close()
            return 2
    passed = sum(1 for _, ok in results if ok)
    say("")
    say(f"== {passed} of {len(results)} plants produced their required result ==")
    for name, ok in results:
        if not ok:
            say(f"   NOT AS REQUIRED: {name}")
    log.close()
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
