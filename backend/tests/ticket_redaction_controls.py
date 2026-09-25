"""TICKET-REDACTION controls: plant each named mutation and its inert twin,
run the named checks, put the file back, record the result.

Every receive path, every read-back door, the /health marker and three
properties of the rule itself -- and, from round 2, every comment path and
the comment store (M1), the rule-before-the-cut order at every cut and the
over-ceiling read's hold-back (M2), the harness's two refusals (M3) and the
automatic upload's contract through its stand-in (L6); and, from round 3,
the harness's census of every schema and its one-schema binding (R2
finding 1) -- are carried below as DATA: the file, the exact
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
SCHEMAS = "backend/api/schemas.py"
TESTS = "backend/tests/test_ticket_redaction.py"
STANDIN = "backend/tests/ticket_redaction_autolog_standin.py"
T = "test_ticket_redaction.py::"

R1 = T + "test_pg_submit_stores_the_marker_and_never_the_value"
R1_NEG = T + "test_pg_submit_check_fails_when_the_rule_is_bypassed"
DETAIL = T + "test_pg_legacy_row_detail_pane_serves_the_marker"
DOWNLOAD = T + "test_pg_legacy_row_log_download_serves_the_marker"
LIST = T + "test_pg_legacy_row_admin_list_serves_the_marker"
DISCORD = T + "test_pg_legacy_row_discord_feed_serves_the_marker"
EVENTS = T + "test_pg_legacy_row_event_feed_redacts_before_the_140_character_cut"
LEGACY_NEG = T + "test_pg_legacy_check_fails_when_the_rule_is_bypassed"
HEALTH = T + "test_pg_ticket_redaction_health_carries_the_marker_on_both_arms"
UNIT_SCRUB = T + "test_the_bundle_scrub_redacts_credentials_first_and_counts_them"
UNIT_31 = T + "test_31_hex_characters_are_untouched"
UNIT_LOWER = T + "test_lowercase_hex_is_a_ticket_and_is_digested_as_logged"
UNIT_KAT = T + "test_the_marker_matches_the_known_answer_and_the_client_format"
# round 2
ADMIN_COMMENT = T + "test_pg_admin_comment_stores_the_marker_and_never_the_value"
STATUS_COMMENTS = T + "test_pg_status_change_comments_store_the_marker_and_never_the_value"
INTERNAL_COMMENT = T + "test_pg_internal_comment_stores_the_marker_and_never_the_value"
REPLY = T + "test_pg_reporter_reply_redacts_before_the_2000_character_cut"
FEED_COMMENT = T + "test_pg_legacy_comment_is_served_redacted_on_the_bots_own_feed"
DETAIL_COMMENT = T + "test_pg_legacy_comment_is_served_redacted_in_the_detail_timeline"
CLAMPS = T + "test_pg_submit_redacts_before_every_clamp"
WINDOW = T + "test_pg_legacy_bundle_over_the_read_ceiling_is_redacted_before_the_window"
SETTLED = T + "test_settled_length_holds_back_only_an_unfinished_end"
PIECES = T + "test_the_rule_over_pieces_equals_the_rule_over_the_whole"
SPLIT_READ = T + "test_the_over_ceiling_read_holds_a_ticket_split_between_two_reads"
CARRY_BOUND = T + "test_the_over_ceiling_read_refuses_an_unfinished_run_longer_than_the_carry"
NAME_REFUSAL = T + "test_pg_the_harness_refuses_a_database_without_the_scratch_marker"
POPULATED = [T + "test_pg_the_harness_refuses_a_populated_scratch_database[%s]" % i
             for i in ("players", "events", "shop_items", "foreign_table")]
STANDIN_CONTRACT = T + "test_pg_auto_log_contract_holds_on_the_stand_in"
# round 3
SHADOW = [T + "test_pg_the_harness_refuses_a_same_named_object_ahead_of_public[%s]" % i
          for i in ("user_schema_table", "database_path_table", "user_schema_sequence")]
BIND = T + "test_pg_every_harness_connection_is_bound_to_one_schema"
# Every live case that enters the harness on this tree. The two L6 cases
# against the real auto-upload route are not here: without the route they
# skip before the harness is entered, on every tree this file can see.
EVERY_PG_CASE = [R1, R1_NEG, DETAIL, DOWNLOAD, LIST, DISCORD, EVENTS, LEGACY_NEG, HEALTH,
                 ADMIN_COMMENT, STATUS_COMMENTS, INTERNAL_COMMENT, REPLY, FEED_COMMENT, DETAIL_COMMENT,
                 CLAMPS, WINDOW, NAME_REFUSAL, *POPULATED, STANDIN_CONTRACT, *SHADOW, BIND]
# Of those, the cases that get past the refusals on the lane database: each
# asserts from its own record that every refusal ran before its first
# terminate or DROP.
ENTERING = [c for c in EVERY_PG_CASE if c != NAME_REFUSAL and c not in POPULATED and c not in SHADOW]

Plant = namedtuple("Plant", "name control kind what edits checks")
PLANTS = []


def mutant(name, control, what, edits, checks):
    PLANTS.append(Plant(name, control, "mutant", what, edits, checks))


def twin(name, control, what, edits, checks):
    PLANTS.append(Plant(name, control, "twin", what, edits, checks))


def pair(control, site, old, new, note, checks, target=None):
    """A mutant replacing `old` with `new`, and its twin: the same text with a
    trailing comment on its last line, which changes nothing the code does.
    The target is main.py unless named (the rule's own "U" controls default
    to log_redaction.py)."""
    target = target or (MAIN if control[0] != "U" else RULE)
    mutant(f"{control}-mutant", control, site, [(target, old, new)], checks)
    commented = old[:-1] + "  # " + note + "\n"
    twin(f"{control}-twin", control, f"a comment on the same line ({site})",
         [(target, old, commented)], checks)


# ── the receive path: POST /api/v1/bug-reports ────────────────────────────
# Round 2 moved the rule from the handler into BugReportRequest's validators
# (it has to run before their clamps), so the receive-path plants live there.
# The description and the repro steps share one validator: one plant.
LOG_RULE = "            v = _schema_logred.redact_credentials(v)    # the rule, over the log as sent\n"
TEXT_RULE = "            v = _schema_logred.redact_credentials(v)    # the rule, over the text as sent\n"
LOG_CUT = ("            if len(v) > 12_000_000:\n"
           "                v = v[-12_000_000:]                     # then the tail is kept\n")
TEXT_CUT = ("            if len(v) > 8000:\n"
            "                v = v[:8000]                            # then the head is kept\n")
pair("R1-log", "the log is received without the rule",
     LOG_RULE, "            v = v\n", "the log's pass", [R1], SCHEMAS)
pair("R1-text", "the description and the repro steps are received without the rule",
     TEXT_RULE, "            v = v\n", "the free text's pass", [R1], SCHEMAS)

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

# ── round 2, M1: every comment path and the comment store ─────────────────
pair("M1-store", "the comment store no longer applies the rule",
     "    comment = _logred.redact_credentials(comment)\n", "",
     "the store's pass", [ADMIN_COMMENT, STATUS_COMMENTS, INTERNAL_COMMENT])
pair("D6-feed-comment", "the bot's event feed serves a stored comment raw",
     '                "comment": _logred.redact_credentials(r["comment"]),\n',
     '                "comment": r["comment"],\n',
     "read-time rule", [FEED_COMMENT])
pair("D7-detail-comment", "the detail pane's timeline serves a stored comment raw",
     '            "comment": _logred.redact_credentials(e["comment"]),\n',
     '            "comment": e["comment"],\n',
     "read-time rule", [DETAIL_COMMENT])

# ── round 2, M2: the rule BEFORE every cut (each mutant cuts first) ───────
pair("M2-log-order", "the log's tail clamp runs before the rule",
     LOG_RULE + LOG_CUT, LOG_CUT + LOG_RULE, "rule, then clamp", [CLAMPS], SCHEMAS)
pair("M2-text-order", "the free text's head clamp runs before the rule",
     TEXT_RULE + TEXT_CUT, TEXT_CUT + TEXT_RULE, "rule, then clamp", [CLAMPS], SCHEMAS)
pair("M2-window-order", "the over-ceiling read cuts its window from raw text (the rule then "
     "runs only in the bundle scrub, after the cut)",
     "            window += _logred.redact_credentials(pending[:settled])\n",
     "            window += pending[:settled]\n",
     "rule, then window", [WINDOW])
pair("M2-comment-order", "the reporter's reply is cut at 2000 characters before the rule (the "
     "rule then runs only at the store, after the cut)",
     '    comment = _logred.redact_credentials((req.comment or "").strip())\n',
     '    comment = (req.comment or "").strip()\n',
     "rule, then cut", [REPLY])
pair("M2-carry", "the over-ceiling read holds nothing back between pieces",
     "    m = _UNSETTLED_TAIL_RE.search(text)\n", "    return len(text)\n",
     "the hold-back", [SETTLED, PIECES, SPLIT_READ], RULE)
pair("M2-carry-bound", "the hold-back is unbounded",
     "            if len(pending) - settled > _BUG_LOG_CARRY_MAX:\n", "            if False:\n",
     "the bound", [CARRY_BOUND])

# ── round 2, M3: the harness's two refusals ────────────────────────────────
# Removing the call leaves the terminate and the DROP first in every case's
# own record, so every case that enters the harness goes RED on its entry
# assertion, and the two refusal cases on theirs.
pair("M3-gate", "Env.__aenter__ no longer calls the scratch-name and population refusals",
     "        await _refuse_unless_scratch(self.url, self.sent)\n", "",
     "the refusals", EVERY_PG_CASE, TESTS)

# ── round 3, R2 finding 1: the census and the one-schema binding ──────────
# Without the census call: every case that enters the harness goes RED on its
# own entry assertion (the census did not run first); the foreign-table case
# is entered; and the three same-named objects ahead of public are ACCEPTED --
# the harness sends its terminate and its drops.
pair("M3-census", "_refuse_unless_scratch no longer calls the census",
     "        await _refuse_unless_only_fixtures(conn, name, lost)\n", "",
     "the census", ENTERING + [POPULATED[3]] + SHADOW, TESTS)
# The census narrowed to the public schema, round 2's scope: it still runs
# first and still refuses a foreign public table, so only the three
# same-named objects in a schema ahead of public show the difference.
pair("M3-census-scope", "the census reads the public schema only (round 2's scope)",
     "    \" AND (n.nspname::text !~ '^pg_' OR n.nspname = ANY (pg_catalog.current_schemas(false)))\"\n",
     "    \" AND n.nspname::text = 'public'\"\n",
     "the census's scope", SHADOW, TESTS)
pair("M3-bind-seed", "the seed engine is no longer bound to one schema at connect",
     "                                        connect_args=_BOUND_CONNECT,\n", "",
     "the seed engine's binding", [BIND], TESTS)
pair("M3-bind-routes", "database.py's engines, as the routes get them, are no longer bound at connect",
     '        cparams["server_settings"] = dict(cparams.get("server_settings") or {}, search_path=BOUND_SCHEMA)\n',
     "", "the routes' binding", [BIND], TESTS)
# A drop line is SQL, so its inert twin is a SQL comment inside the statement.
M3_DROP_LINE = "DROP TABLE IF EXISTS public.players RESTRICT;\n"
mutant("M3-qualify-mutant", "M3-qualify", "one drop names its table without the schema",
       [(TESTS, M3_DROP_LINE, "DROP TABLE IF EXISTS players RESTRICT;\n")], [BIND])
twin("M3-qualify-twin", "M3-qualify", "a SQL comment inside the same drop",
     [(TESTS, M3_DROP_LINE, "DROP TABLE IF EXISTS public.players RESTRICT /* the twin */;\n")], [BIND])

# ── round 2, L6: the automatic upload's contract, planted in the stand-in ──
L6_SCRUB = "    scrubbed, counts, _ids = await asyncio.to_thread(_scrub_pass_one, log_blob)\n"
L6_WRITE = ("    report_id = uuid.uuid4()\n"
            '    data = gzip.compress(scrubbed.encode("utf-8", errors="replace"))\n'
            "    path = _bug_report_log_path(str(report_id))\n"
            '    with open(path, "wb") as f:\n'
            "        f.write(data)\n")
L6_RAW_FIRST = ("    report_id = uuid.uuid4()\n"
                "    path = _bug_report_log_path(str(report_id))\n"
                '    with open(path, "wb") as f:\n'
                '        f.write(gzip.compress(log_blob.encode("utf-8", errors="replace")))\n'
                + L6_SCRUB +
                '    data = gzip.compress(scrubbed.encode("utf-8", errors="replace"))\n'
                '    with open(path, "wb") as f:\n'
                "        f.write(data)\n")
L6_RULE = "            v = log_redaction.redact_credentials(v)     # the rule, over the log as sent\n"
L6_CUT = ("            if len(v) > LOG_MAX_CHARS:\n"
          "                v = v[-LOG_MAX_CHARS:]                  # then the tail is kept\n")
mutant("L6-never-mutant", "L6", "the upload never calls the shared scrub",
       [(STANDIN, L6_SCRUB, "    scrubbed = log_blob\n")], [STANDIN_CONTRACT])
mutant("L6-after-write-mutant", "L6", "the upload writes its bundle raw first, then scrubs and "
       "rewrites it (what is finally stored is scrubbed; only the order is wrong)",
       [(STANDIN, L6_SCRUB + L6_WRITE, L6_RAW_FIRST)], [STANDIN_CONTRACT])
twin("L6-extra-call-twin", "L6", "an extra, inert scrub call after the write (the contract asks "
     "for a scrub BEFORE the write, not for exactly one)",
     [(STANDIN, "        f.write(data)\n",
       "        f.write(data)\n"
       "    await asyncio.to_thread(_scrub_pass_one, log_blob)    # an extra pass, its result unused\n")],
     [STANDIN_CONTRACT])
pair("L6-clamp-first", "the upload's tail clamp runs before the rule",
     L6_RULE + L6_CUT, L6_CUT + L6_RULE, "rule, then clamp", [STANDIN_CONTRACT], STANDIN)


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
