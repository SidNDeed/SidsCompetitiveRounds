"""Runs the client rule self-tests. Not a source-shape gate - an execution.

`plugin/LogScrub.cs` and `plugin/TopStripBand.cs` are kept free of Unity,
Photon and BepInEx so that what a log bundle stops carrying, and which y each
surface gets when several paint in the top-centre column at once, can be
EXECUTED rather than asserted about as source text -- the arrangement
`tools/h2h-harness` already uses for H2HRules, and the reason LogScrub's own
class comment gives for the shape it is written in. Until now nothing in the
repository ran the scrub: its self-test existed behind a Debug config lever
that fires once at startup on a developer's machine, so its numbers were not
reproducible from a checkout and no pytest run ever touched them. The column
allocator had no self-test at all -- it stored a plain maximum for a job that
needed a layout, and the only gate over it read the source.

Three separate ways this can look green while proving nothing, and one
assertion each: a suite that stopped running cases (run == the lines printed),
a case that ran and failed (fail == 0), and a harness that threw before its
summary (exit 0 and a PASS verdict).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "tools" / "client-rules-harness" / "client-rules-harness.csproj"
MAIN_CS = REPO / "tools" / "client-rules-harness" / "Main.cs"

SUMMARY = re.compile(
    r"^(\w[\w-]*)(?: suites=\d+)? run=(\d+) fail=(\d+) verdict=(\w+)$", re.M)


def _dotnet():
    """The dotnet CLI, or None. On the build seat it is user-local."""
    found = shutil.which("dotnet")
    if found:
        return found
    candidate = Path(os.path.expanduser("~")) / ".dotnet" / "dotnet.exe"
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def harness_run():
    dotnet = _dotnet()
    if dotnet is None:
        pytest.skip("dotnet CLI not on this machine")
    proc = subprocess.run(
        [dotnet, "run", "--project", str(HARNESS), "-c", "Release", "--"],
        cwd=str(REPO), capture_output=True, text=True, timeout=900,
    )
    return proc


def _suites(proc):
    return {m.group(1): (int(m.group(2)), int(m.group(3)), m.group(4))
            for m in SUMMARY.finditer(proc.stdout)}


def test_the_harness_ran_at_all(harness_run):
    assert harness_run.returncode == 0, (
        "client-rules-harness exited %d\n--- stdout ---\n%s\n--- stderr ---\n%s"
        % (harness_run.returncode, harness_run.stdout[-4000:], harness_run.stderr[-4000:]))
    suites = _suites(harness_run)
    assert "client-rules-harness" in suites, "no combined summary line was printed"
    _, fail, verdict = suites["client-rules-harness"]
    assert (fail, verdict) == (0, "PASS")


def test_the_log_scrub_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "logscrub" in suites, "the LogScrub suite did not report"
    run, fail, verdict = suites["logscrub"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    # A suite that quietly stops running cases still prints fail=0. The
    # per-case lines are the independent count.
    printed = len(re.findall(r"^\[logscrub\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # A floor, not an equality: cases get added. Below this, coverage that
    # exists today has been deleted.
    assert run >= 26, "the LogScrub suite shrank to %d cases" % run


def test_the_top_strip_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "topstrip" in suites, "the TopStripBand suite did not report"
    run, fail, verdict = suites["topstrip"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[topstrip\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    assert run >= 14, "the TopStripBand suite shrank to %d cases" % run


def test_the_ffa_report_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "ffareport" in suites, "the FfaReportRules suite did not report"
    run, fail, verdict = suites["ffareport"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[ffareport\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    assert run >= 21, "the FfaReportRules suite shrank to %d cases" % run


def test_the_roster_census_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "rostercensus" in suites, "the RosterCensusRules suite did not report"
    run, fail, verdict = suites["rostercensus"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[rostercensus\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    assert run >= 12, "the RosterCensusRules suite shrank to %d cases" % run


def test_the_binder_sort_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "bindersort" in suites, "the BinderSortRules suite did not report"
    run, fail, verdict = suites["bindersort"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[bindersort\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # A floor near the real count, not far below it: the suite ran 41 cases on
    # the commit that added it, and a floor 25 below that is a gate that cannot
    # fail (#342). Raise it when cases are added.
    assert run >= 38, "the BinderSortRules suite shrank to %d cases" % run


def test_the_quick_shard_suite_ran_every_case_and_none_failed(harness_run):
    """Item 18: the pull strip's per-card shard rules (PcQuickShardRules)."""
    suites = _suites(harness_run)
    assert "quickshard" in suites, "the PcQuickShardRules suite did not report"
    run, fail, verdict = suites["quickshard"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[quickshard\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # The suite ran 27 cases on the commit that added it, 45 once fix pass 1
    # added the batch shard's generation cases (PcShardFlight, finding 2)
    # (#342: a floor near the real count). Raise it when cases are added.
    assert run >= 45, "the PcQuickShardRules suite shrank to %d cases" % run


@pytest.mark.parametrize("name", [
    # the ordering rule itself
    "a ranked subject precedes an off-board subject",
    "off the board, the order flips (group key, not rating)",
    "rank 100 is in the front group",
    "rank 101 is NOT in the front group",
    "rank 5 AND inactive sorts to the back",
    "clearing inactive on the same fixture makes it front",
    "the back group orders by current rating, descending",
    "the frozen mint numbers order the SAME pair the other way",
    "an unrated subject sorts behind a rated one on 0",
    "two copies of one subject sit together, not split by a third",
    "copies order by the shared tail, and swapping rarity flips them",
    "a print compares equal to itself",
    # the cycler, and the "% 5" literal's grave
    "Next skips RatingPosition when the answer carried no standings",
    "Next skips RatingPosition before any answer has been read",
    "the same call returns RatingPosition once standings are present",
    "the cycle visits every member and returns to Name",
    "a hardcoded modulus cannot reach the sixth mode (control)",
    # the deferred restore
    "a pending RatingPosition SURVIVES the pre-fetch paint",
    "it applies once standings are present",
    "it is dropped for the session when the answer carried none",
    "folding Unknown into Absent would change the first outcome (control)",
    "Restore has exactly Keep/Apply/DropForSession and no write outcome",
    # the stored value
    "a stored member name round-trips",
    "a numeric string is not a member name",
    "the stored value is a name, never an ordinal",
])
def test_the_binder_sort_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "bindersort")
    assert line.startswith("[bindersort] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


def test_the_ladder_shop_suite_ran_every_case_and_none_failed(harness_run):
    """Item 12 follow-up: the title ladders as entries of the Shop's
    Titles section. TitleLadderRules decides which lines render (each once),
    which listing rows they replace, which tier is held and what the Buy /
    Upgrade / Maxed button says and why; its cases live in the harness-only
    TitleLadderRulesSelfTest.cs."""
    suites = _suites(harness_run)
    assert "laddershop" in suites, "the TitleLadderRules suite did not report"
    run, fail, verdict = suites["laddershop"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[laddershop\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # The suite ran 38 cases on the commit that added it, 51 once the
    # popup's IMGUI event shield joined it (r2), and 38 again when the
    # five-tier build replaced the popup with a dropdown under the entry
    # (no modal, so no shield); the floor is that count, not one far below
    # it (#342). Raise it when cases are added.
    assert run >= 38, "the TitleLadderRules suite shrank to %d cases" % run


@pytest.mark.parametrize("name", [
    # the section plan: every ladder exactly once, and what it folds
    "eight lines render eight entries, each once and in answer order",
    "every rung of every rendered line is folded",
    "a title outside every ladder is not folded",
    "a repeated line id renders once",
    "with no answer in hand nothing renders and nothing is folded",
    "a line past the pool renders nowhere and keeps its listing rows",
    "a pool the size of the answer renders and folds every line (control)",
    # Buy
    "nothing held, entry listed and affordable: Buy, enabled",
    "one gold short: Buy, disabled, not enough gold (control)",
    "a disabled button carries no target sku",
    "the entry is not in the listing: Buy, disabled, not on sale",
    "the listing has not answered: Buy, disabled, shop loading",
    "the stats have not answered: Buy, disabled, shop loading",
    "no account: Buy, disabled, no account",
    "the listing's price decides the funds check, not the answer's",
    "the same balance buys at the answer's price when the listing agrees (control)",
    # Upgrade
    "entry held, tier 2 granted by play: Upgrade, disabled, earned by play",
    "funds and a listing never enable a tier the answer does not sell",
    "seven series in: three to go",
    "past the threshold before the grant lands: zero to go, never negative",
    "a priced and listed next tier enables Upgrade (control)",
    # Maxed
    "top tier held: Maxed, disabled",
    "Maxed does not depend on the account, the listing or the stats",
    "the same line without its top rung is Upgrade toward tier 6 (control)",
    # the held tier
    "held is the highest OWNED tier, not the tier the games imply",
    "an account that owns nothing holds no tier and reads Buy",
    "owning only a tier-3 rung reads Upgrade toward tier 4",
    "either of two tier-4 rungs holds tier 4",
    "the worn rung names the held tier",
    "with none worn, the first owned rung of the tier names it (control)",
    "nothing held names no rung",
    # the dropdown's tier rows and bar
    "tier rows read Owned, Current, Next, then Locked",
    "not started: the entry rung is Next and every other rung Locked",
    "a line held at the top has one Current row and no Next row (control)",
    "80 series held at tier 4 fills 5 of 75",
    "not started draws an empty bar",
    "the top draws a full bar",
    "a line with no rungs: Buy, disabled, no rungs",
])
def test_the_ladder_shop_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "laddershop")
    assert line.startswith("[laddershop] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


def test_the_settings_model_suite_ran_every_case_and_none_failed(harness_run):
    """Item 13: the settings page's split and reset-scope rules
    (plugin/SettingsModel.cs). Its cases live in the harness-only
    SettingsModelSelfTest.cs."""
    suites = _suites(harness_run)
    assert "settingsmodel" in suites, "the SettingsModel suite did not report"
    run, fail, verdict = suites["settingsmodel"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[settingsmodel\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # The count on the commit that added the suite, not a floor far below
    # it (#342). Raise it when cases are added.
    assert run >= 44, "the SettingsModel suite shrank to %d cases" % run


@pytest.mark.parametrize("name", [
    # T2a, the design's four cases
    "T2a the ordinary case",
    "T2a parentheses in the value",
    "T2a a colon in the value half stays in the value (control)",
    "T2a a disclosure never splits",
    # A6, the legs the generated table decides
    "A6 every row has a reason",
    "A6 every row that stores no value has a when-to-press line",
    "A6 no row's help target is its own actuating control",
    # T5-g's selection half: one exact set per sub-tab, never a total
    "T5-g ingame writes exactly its 5",
    "T5-g chatmail writes exactly its 3",
    "T5-g sound writes exactly its 3",
    "T5-g visuals writes exactly its 9",
    "T5-g perf writes exactly its 11",
    "T5-g langmenus writes exactly its 2",
    "T5-g privacy writes exactly its 0",
    # M1 (design 6.3): a destructive row takes Enter only; each key keeps its source
    "M1 Space never arms or confirms a destructive row",
    "M1 Enter arms and confirms a destructive row",
    "M1 Enter activates an action row",
    "M1 Space activates an action row",
    "M1 Enter opens a dropdown",
    "M1 Space opens a dropdown",
    "M1 Enter and Space never activate a switch, a segmented row or a slider",
    # L3 (design 6.3): a disclosure steps with Left/Right, never Enter/Space
    "L3 Enter and Space never toggle a disclosure row",
    # L2 (design 6.3, W7's source route): the controller's buttons
    "L2 the shoulders move the sub-tab and the activate button activates the focused row",
    "L2 the shoulders wrap at both ends of the bar",
    "L2 the activate button never arms or confirms a destructive row",
    "L2 the activate button activates an action row",
    "L2 the activate button opens a dropdown",
    "L2 the activate button never activates a switch, a segmented row, a slider or a disclosure",
    "M1 the Space key reaches the row as Space, never as Enter",
    "M1 the Enter key reaches the row as Enter",
    "Tab moves to the next sub-tab and wraps",
    "Shift+Tab moves to the previous sub-tab and wraps",
    "Up/Down move the focus, Left/Right step the row, F1 pins, no key does nothing",
])
def test_the_settings_model_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "settingsmodel")
    assert line.startswith("[settingsmodel] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


def test_the_secure_route_suite_ran_every_case_and_none_failed(harness_run):
    """Board row 27: the secure-route checks behind the Translate portal
    button and the timer that retries while the session runs on the plaintext
    backup. SecureRouteRules decides; its cases live in the harness-only
    SecureRouteRulesSelfTest.cs with a fake transport and a fake clock, and
    the sentences come from the shipped SecureRouteText.cs, looked up in the
    shipped catalogues."""
    suites = _suites(harness_run)
    assert "secureroute" in suites, "the SecureRouteRules suite did not report"
    run, fail, verdict = suites["secureroute"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[secureroute\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # 46 cases on the commit that added the suite, 72 since round 2 added
    # the J, O, R, K and H cases; the floor is that count, not one far
    # below it (#342). Raise it when cases are added (116 since round 5 added
    # O11-O11g).
    assert run >= 116, "the SecureRouteRules suite shrank to %d cases" % run


@pytest.mark.parametrize("name", [
    # the portal button: on-demand check with a fake transport
    "P1 on the backup a press begins ONE check of the secure address with the 8 s timeout",
    "P2 the check answers: the session flips to the secure base and the portal opens in the same press",
    "P3 control: the check times out: the session stays on the backup and the press reports it",
    "P4 the failure toast names the host:port and the 8 s timeout, word for word",
    "P6 no sentence tells the player to restart, and every hole is filled",
    "P9 a second press while the check runs joins it and starts nothing",
    # the timer with a fake clock
    "T1 on the backup the timer checks at the 5-minute marks and at no other second",
    "T2 control: a session that never left the secure base never checks",
    "T3 a live check holds the timer past its mark: never a second check beside it",
    "T3c control: once the check has answered, the mark alone decides",
    "T5 the timer stops at the first answer and the session is back on the secure base",
    "T6 off the backup no check of any trigger begins, and a press opens at once",
    # the flip mid-flight
    "F1 a request queued on the backup before the flip completes against the backup",
    "F2 control: a request built after the flip goes to the secure base",
    # round 2: the probe body (MEDIUM 1)
    "J1 a compact mod-version body is usable and restores the secure route",
    "J2 a mod-version body with whitespace between its tokens is usable and restores the secure route",
    "J3 control: a JSON body without the version member is not the SCR server and keeps the backup",
    "J4 control: a body cut off inside the version string is not the SCR server and keeps the backup",
    # round 2: the outbox follows the route (HIGH 1)
    "O1 a report queued on the backup is sent to the secure base from the first send after the flip",
    "O1c control: before the flip the same report is sent to the backup",
    "O4 a failed retry that did not carry the session token spends no attempt",
    "O5 with enforcement armed a report queued on the backup is delivered once, with the token, after the restore",
    "O5c control: the queued URL kept, as in round 1, never reaches the secure base and is never delivered",
    # round 3: a restored retry goes out only with the session (Codex round 2 HIGH 1)
    "O4b over a transport that carries the token, a report without a fresh session waits and is not sent",
    "O7 restored without a session for 2 min: no send to the secure base, no attempt spent, the entry kept",
    "O7b then the session lands: exactly one send, with the token, one settlement, an empty outbox",
    "O8 a request sent without the token after the gate passed spends nothing and removes nothing",
    "O9 a backup 401 that lands after a restore keeps the entry due by the restore's promise (20 s)",
    # round 2: the portal press (LOW 1, LOW 2)
    "R1 both refusal wordings (the portal mint's and the enforced writes') read as a session refusal",
    "R2 a mint refused for its session re-mints once, and the second refusal is reported, never looped",
    "K1 a press on the backup while the local identity is unknown still starts the check and shows it",
    "K2 a press on an explicit plaintext address while the identity is unknown still names the address",
    "H1 a player's route never checks a plaintext address, loopback included",
    # round 3: the readiness wait outlasts its own auth exchange (Codex round 2 LOW 2)
    "W1 a session the exchange lands 16-19.9 s after the press is waited for: the one mint carries it",
    # round 3: the plaintext refusal says why in the log (Codex round 2 LOW 3)
    "N1 the plaintext refusal's log line names the base as scheme://host:port and the reason, with no credential",
    # round 3: the mint failure line is bounded and token-safe (Codex round 2 LOW 4)
    "M1 a 161+ character failure body with a token: the whole line is bounded, one line, and scrubbed",
    "M2 a bare token-shaped value, a session header, a token pair and a Steam ticket are all redacted",
    # round 3: the ticket latch is released only after the cancel (Codex round 2 LOW 5)
    "MT6 a cancel that throws once keeps the handle; the next tick cancels it, and no successor is requested before that",
    "MT6b both cancels throw: the handle stays held, no successor is requested (requested=1), one line",
    "MT7 a repeated end of a failed handle, and a late end of an old serial, change nothing",
    "MT8 a held ticket whose end never arrives is abandoned (cancelled) past the exchange's timeout, then superseded",
    # round 4 (Codex round 3 HIGH 1 and LOWs 1-5)
    "O4d a 2xx to a retry that did not carry the session token removes nothing and spends nothing",
    "O10 a tokenless 2xx without a row leaves the entry queued: nothing removed, no attempt spent, 0 rows",
    "O10b then the restore and the session: exactly one token-bearing settlement, one row, an empty outbox",
    "W1d a ticket callback later than 5 s and an exchange inside its 20 s: one press mints once, with the session",
    "N1d a valid 253-character host: the whole line stays within its declared maximum, the host cut with a marker",
    "M3 FormatRequestError's text into the mint line: an authorization= value and a credential straddling character 300 are both gone, 240 held",
    "MT9 a cancel that succeeds on the third attempt frees the latch, then exactly one successor",
    "MT9b a cancel that never succeeds: retried on its 30 s bound for an hour, never a successor, the log bounded",
    "M4 a tokenless 401 with CR/LF and JSON, header, key=value, bare-token and Steam-ticket sentinels: one bounded line, none of them",
    "M4b each sentinel first after a CR/LF, raw text: the line scrubs and flattens by itself",
    "M4c a credential straddling the line's own cut is scrubbed before the cut",
    # round 5 (Codex round 4 HIGH 1): a first send's 2xx settles only when it carried the token
    "O11 a first send answered 2xx without the token and without a row is not settled: one durable entry, 0 rows",
    "O11b then the restore and the session: exactly one token-bearing POST, one row, an empty outbox",
    "O11c attempt one fails and attempt two is a tokenless 2xx without a row: queued, then delivered once with the token",
    "O11d attempts one and two fail and attempt three is a tokenless 2xx: queued, then delivered once with the token",
    "O11e attempt one carried a stale token (401) and attempt two went out without it: its 2xx is not settled",
    "O11f control: a first send that carried the token and was answered 2xx settles at once, one row, nothing queued",
    "O11g control: against the enforcing sink the three tokenless attempts fail, the report is queued and delivered once",
    # every catalogue
    "L-es every secure-route sentence is translated in the es catalogue, holes filled",
    "L-ru every secure-route sentence is translated in the ru catalogue, holes filled",
    "L-uk every secure-route sentence is translated in the uk catalogue, holes filled",
    "L-sv every secure-route sentence is translated in the sv catalogue, holes filled",
])
def test_the_secure_route_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "secureroute")
    assert line.startswith("[secureroute] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


def test_the_split_keeps_a_colon_that_belongs_to_the_value(harness_run):
    """T2a's control, asserted on the printed MEASUREMENT: the value half
    of "Label: <color=#88FF88>10:30</color>" keeps its own colon. A split at
    the last colon prints label=[Label: <color=#88FF88>10] instead."""
    line = _named_case(harness_run,
                       "T2a a colon in the value half stays in the value (control)",
                       "settingsmodel")
    assert "label=[Label] value=[<color=#88FF88>10:30</color>]" in line, line


def test_the_privacy_tab_reset_writes_nothing(harness_run):
    """No row whose home is Privacy & account is ever bulk-written, by rule
    (design section 6.4): consent, reporting and what leaves this PC are the
    player's own decisions. Asserted on the printed written set."""
    line = _named_case(harness_run, "T5-g privacy writes exactly its 0", "settingsmodel")
    assert "written=0 {}" in line, line


def test_the_session_report_suite_ran_every_case_and_none_failed(harness_run):
    """Board row 30a: the session report's envelope parser, executed against
    one envelope per kind that GET /api/v1/report produced for
    test_session_report_pg.py's seeded world (SessionReportRulesSelfTest.cs)."""
    suites = _suites(harness_run)
    assert "sessionreport" in suites, "the SessionReportRules suite did not report"
    run, fail, verdict = suites["sessionreport"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[sessionreport\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # The suite ran 31 cases on the commit that added it, 35 once board row
    # 30b added the overlay rule's cases, 38 with 30c's builds layout, 59
    # with 30d's derived numbers, 63 with 30e's race axis, 67 with 30g's
    # broadcast playback, 71 with round 2's presence rules (M1), 73 with its
    # unknown race target (M2), 75 with its playback gate (M3), 77 with the
    # watched-set lever's api rule (M4), 80 with the missing-data
    # provenance (L1), 82 with round 3's score-race pairs for 2v2 and 1v2
    # (L1) and 85 with round 4's status-target rule (LOW 2); the floor is
    # that count (#342). Raise it when cases are added.
    assert run >= 85, "the SessionReportRules suite shrank to %d cases" % run


@pytest.mark.parametrize("name", [
    # one envelope per kind, as the server's route produced it
    "ranked: kind, version and roster order",
    "ranked: three games in order with their scores",
    "ranked: game 1 picks in pick order with their pickers",
    "ranked: set rating before, after and delta",
    "casual: a truncated set counts the game it left out",
    "casual: totals are sparse - an unrecorded counter has no key, never a zero",
    "team: kind and two sides of two",
    "team: every seat carries its side's rounds",
    "team: a rating delta without before and after",
    "1v2: the solo is side 1 and the duo side 2",
    "1v2: game 2 scores and its one recorded stream",
    "ffa: kind, three games and the union roster in order",
    "ffa: a player who sat a game out has no score key in it",
    "ffa: the set rating and gold over the sitting",
    # the slicer, with its control
    "hostile strings: braces and quotes inside a name or card do not split members",
    "hostile strings (control): a string-blind matcher cuts the first player short",
])
def test_the_session_report_parse_has_a_case_per_kind(harness_run, name):
    line = _named_case(harness_run, name, "sessionreport")
    assert line.startswith("[sessionreport] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


@pytest.mark.parametrize("name", [
    "overlay: an open report stands a search field down",
    "overlay (control): report closed, page open, field on its surface -> it draws",
    "overlay: a field off its surface stays down",
    "overlay: the page closed keeps a field down",
])
def test_the_search_fields_stand_down_under_the_report(harness_run, name):
    """Board row 30b: SessionReportRules.PageElementMayDraw, executed; every
    F5 search field, the ranked callout and the FFA and 1v2 tabs' row hover
    tooltips ask it (test_session_report_overlay_guard.py)."""
    line = _named_case(harness_run, name, "sessionreport")
    assert line.startswith("[sessionreport] PASS"), line


def test_the_binder_order_is_total_under_every_mode_the_button_offers(harness_run):
    """The tail that makes the order total is reached from every branch, so a
    mode added later cannot quietly forget it.

    The modes are COUNTED here rather than named: the cycle case prints how
    many members the button visits, so a sixth mode added without a totality
    case makes the two numbers disagree. Naming them would have to be edited
    by the same change that forgets the case.
    """
    total = [l for l in harness_run.stdout.splitlines()
             if l.startswith("[bindersort] ") and " | case=the order is total under " in l]
    assert total, "no totality cases were printed"
    for line in total:
        assert line.startswith("[bindersort] PASS"), line
    cycle = _named_case(harness_run, "the cycle visits every member and returns to Name",
                        "bindersort")
    m = re.search(r"visited=(\d+) of (\d+)", cycle)
    assert m, cycle
    modes = int(m.group(2)) + 1   # the cycle prints every member BUT Name
    assert len(total) == modes, (
        "%d modes are on the cycler but only %d have a totality case"
        % (modes, len(total)))


def test_a_widening_census_can_actually_discover_a_latched_fighter(harness_run):
    """The HIGH this suite exists for, asserted on the printed MEASUREMENT.

    A seat whose identity had not arrived when the roster was taken is latched
    as unresolved. The release test used to be evaluated over the set the latch
    itself filters, so the evidence that would release it was removed before it
    could be read: the seat could never be re-admitted, and it sat out every
    remaining game of the match.

    The two cases below are one control pair. The first feeds the RAW census
    (every actor in the room, latch not consulted) and the seat must be
    released; the second feeds the pre-filtered census the old code used and
    the same seat must NOT be released. A fix that widened only the roster
    test, or one that made the release unconditional, reds exactly one of them.
    """
    good = _named_case(harness_run,
                       "a widening census discovers a latched fighter and releases it",
                       "rostercensus")
    assert good.startswith("[rostercensus] PASS"), good
    got = good.split(" | got=", 1)[1].strip()
    m = re.match(r"^census=\{(.*)\} released=\{(.*)\}$", got)
    assert m, got
    assert m.group(2) == "3", (
        "the latched seat was not the one released: " + got)

    control = _named_case(harness_run,
                          "a census that pre-excludes the latched actor cannot release it",
                          "rostercensus")
    assert control.startswith("[rostercensus] PASS"), control
    cgot = control.split(" | got=", 1)[1].strip()
    cm = re.match(r"^census=\{(.*)\} released=\{(.*)\}$", cgot)
    assert cm, cgot
    assert cm.group(2) == "", (
        "a census that cannot see the latched seat still released it -- the "
        "case above then measures nothing: " + cgot)

    # The id the raw census contributes is DERIVED from the pair, never spelled
    # out here. Both cases latch the same seat; the only difference is which
    # census they are handed, so the id the good census has and the control
    # census lacks IS the latched seat's, whatever the fixtures call it. A
    # literal here went stale the moment the fixture ids moved out of the real
    # SteamID64 range, and a stale literal in an `in` test reds for a reason
    # that has nothing to do with the rule under test.
    good_ids = [i for i in m.group(1).split(",") if i]
    control_ids = [i for i in cm.group(1).split(",") if i]
    assert set(control_ids) < set(good_ids), (
        "the two cases are not the same room plus one: raw=" + got +
        " pre-filtered=" + cgot)
    extra = sorted(set(good_ids) - set(control_ids))
    assert len(extra) == 1, (
        "the widening admitted %d ids, so 'the latched seat' is not "
        "identified by this pair: %s" % (len(extra), extra))
    assert len(extra[0]) == 17 and extra[0].isdigit(), (
        "the id the raw census contributed is not a Steam ID, so the census "
        "is not carrying identities: " + repr(extra[0]))


@pytest.mark.parametrize("name", [
    "a late entrant is not admitted by the widening",
    "an unreadable identity is neither admitted nor released",
    "an impostor keeps its latch and adds nothing",
    "a spectator is not a fighter in either rule",
    "an unfrozen room takes the whole resolvable snapshot",
    "an absent roster member is not evicted by the census",
    "the census is order-independent",
    "degenerate inputs are empty, not exceptions",
    "a second freeze does not re-open the assembly window",
    "a re-taken window would admit the actor case 10 refuses",
])
def test_the_roster_census_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "rostercensus")
    assert line.startswith("[rostercensus] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


def test_a_second_freeze_cannot_re_open_the_assembly_window(harness_run):
    """The widening's discriminator is "was this actor in the room when the
    roster was taken", so WHICH INSTANT that names is part of the rule. A later
    freeze re-taking the window moves the instant forward and every actor that
    joined in between becomes admissible -- the late entrant the freeze exists
    to refuse.

    Asserted as a PAIR on the printed measurements: the refusing case must show
    the window WITHOUT the late actor and a census of two, and its control --
    the same room with a window that WAS re-taken -- must show the same actor
    admitted. Without the control, the first case would pass equally well if D
    were being excluded for some reason of its own.
    """
    refused = _named_case(harness_run,
                          "a second freeze does not re-open the assembly window",
                          "rostercensus")
    admitted = _named_case(harness_run,
                           "a re-taken window would admit the actor case 10 refuses",
                           "rostercensus")
    assert refused.startswith("[rostercensus] PASS"), refused
    assert admitted.startswith("[rostercensus] PASS"), admitted

    m = re.search(r"window=\{([^}]*)\} census=\{([^}]*)\}", refused)
    assert m, refused
    window = [x for x in m.group(1).split(",") if x]
    kept = [x for x in m.group(2).split(",") if x]
    assert window == ["1", "2"], (
        "the window moved: the second freeze re-took it as " + repr(window))
    assert len(kept) == 2, (
        "the widening admitted %d ids from a window of two seats: %s"
        % (len(kept), kept))

    m2 = re.search(r"census=\{([^}]*)\}", admitted)
    assert m2, admitted
    widened = [x for x in m2.group(1).split(",") if x]
    assert len(widened) == len(kept) + 1, (
        "the control did not admit exactly one more seat than the case it "
        "controls: %s vs %s" % (widened, kept))
    extra = [x for x in widened if x not in kept]
    assert len(extra) == 1 and len(extra[0]) == 17 and extra[0].isdigit(), (
        "the seat the two cases differ by is not an identity: " + repr(extra))


def test_a_later_freeze_cannot_move_a_key_already_taken(harness_run):
    """First write wins. A second freeze is by definition later than the
    game-over edge -- a hook that fired twice, or a freeze that drifted back
    into the reporting path -- and by then the host may have rolled the
    property into the next game. Taking the later value gives two electors of
    one physical game two keys, which is a second settlement."""
    line = _named_case(harness_run, "a later freeze cannot move a key already taken",
                       "ffareport")
    assert line.startswith("[ffareport] PASS"), line
    got = line.split(" | got=", 1)[1].strip()
    assert got.endswith("_r7"), (
        "the second freeze moved the key: " + got)
    assert "_r8" not in got, ("the rolled-over number reached the key: " + got)
    # the negative control, so "_r7" is not simply the only number this rule
    # can produce
    control = _named_case(harness_run,
                          "a seat that froze after the rollover files a different game",
                          "ffareport")
    assert control.startswith("[ffareport] PASS"), control
    assert "_r8" in control, (
        "a snapshot taken after the rollover produced no distinguishable key: "
        + control)


def test_the_pc_trade_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "pctrade" in suites, "the PcTradeRules suite did not report"
    run, fail, verdict = suites["pctrade"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[pctrade\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # The count at the last commit that added cases (round 3, TC-L5): a floor
    # far below it would be a gate that cannot fail (#342).
    assert run >= 47, "the PcTradeRules suite shrank to %d cases" % run


@pytest.mark.parametrize("name", [
    # the digest: fixed vectors the server's own trade_items/trade_digest produced
    "items match the server's trade_items",
    "digest matches the server's trade_digest",
    "the counterparty's view hashes the same",
    "higher actor: items match the server",
    "higher actor: digest matches the server",
    "negative controls miss the server's digest",
    "a malformed id yields no digest",
    "canon_trade",
    "canon_read",
    # discovery and the lists
    "discovery classifies the four answers and keeps state on the rest",
    "discovery gates the tab, propose and reads",
    "buckets",
    # the refetch rule (round 2, TC-L3: V8 6.4/6.6 reconcile every refusal but busy)
    "a rate limit is a server refusal: the trades and the binder are re-read",
    "the version floor's outdated is a server answer: re-read",
    "every other server refusal is re-read",
    "busy is retried once instead and transport had no answer: neither is re-read",
    "the local short-circuits never reached the server: not re-read",
    "accept confirms only on the armed row inside six seconds",
    "new ids against the last summary, never against zero",
    "offered = give of sent open proposals only",
    "time left from the server clock",
    # the busy retry's fence, consulted before the retry is sent (round 2, TC-M1)
    "busy retry: Back during the delay drops it (the round-1 scenario)",
    "busy retry: a new compose with the same terms drops it",
    "busy retry: re-picked terms on the same compose drop it",
    "busy retry: an unchanged compose is sent, and only once",
    "busy retry: an identity edge drops any retry; an action retry has no compose fence",
    "the terms key sorts each side and keeps the target and the sides apart",
    # the trades cache's ordering fence (round 2, TC-L1)
    "cache fence: a late full answer does not overwrite a newer summary (the round-1 scenario)",
    "cache fence: every landing order of four reads ends on the newest and never goes back",
    "cache fence: a newer full answer is taken, answers in order are all taken, and a clear forgets",
    # the Trades view's entry edge (round 2, TC-L2)
    "entry edge: close and reopen inside five seconds forces the read (the round-1 scenario)",
    "entry edge: a leave and return between two ticks forces the read",
    "entry edge: an entry the session was not ready for is served on the next tick",
    "entry edge: staying on the view reads on entry, then on the 30 s cadence only",
    "entry edge: the five-second gap still re-arms a hide that skipped the close signal",
    # a deferred re-read and the identity generation (round 3, TC-M2)
    "deferred re-read: the scheduling generation passes, a newer one does not",
    "deferred re-read: an identity edge before the frame drops the re-ask (the round-2 scenario)",
    "deferred re-read: with no edge the kept-out answer re-asks once and the re-ask is taken",
    # state-bearing failures take the same fence (round 3, TC-L5)
    "failure fence: behind a newer answer a stale success, 404 or 503 is kept out alike",
    "failure fence: a stale 404 behind a newer success keeps the view and the 120 s cadence (the round-2 scenario)",
    "failure fence: a stale 503 behind a newer success keeps the reads and the 120 s cadence",
    "failure fence: a genuinely newer 404 or 503 is still taken and classifies, and a newer success recovers",
    "failure fence: only a success, a 404 and a 503 trading_unavailable bear state",
    "failure fence: an answer that bears no state neither decides nor keeps out an older answer",
    "failure fence: every landing order of four mixed answers ends on the newest that bears state",
])
def test_the_pc_trade_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "pctrade")
    assert line.startswith("[pctrade] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


def test_the_pc_trade_digest_vectors_are_the_servers():
    """The two expected digests in PcTradeRules.cs are recomputed here from
    the inputs the file names, by the same algorithm the server's
    player_cards.trade_items / trade_digest implement, so a constant edited to
    match a broken client cannot pass."""
    import hashlib
    import uuid
    src = (REPO / "plugin" / "PcTradeRules.cs").read_text(encoding="utf-8")

    def const(name):
        m = re.search(r'internal const string ' + name + r' = "([^"]*)";', src)
        assert m, "constant %s not found" % name
        return m.group(1)

    def items(steam, give, to, get):
        def block(party, ids):
            return party + ":" + ",".join(sorted(str(uuid.UUID(v)) for v in ids))
        first, second = sorted(((steam, give), (to, get)), key=lambda side: side[0])
        return "pctl1|" + block(*first) + "|" + block(*second)

    s1, s2 = const("VecS1"), const("VecS2")
    a, b, c, d = const("VecA"), const("VecB"), const("VecC"), const("VecD")
    i1 = items(s1, [b, a], s2, [c])
    i3 = items(s2, [d, c], s1, [b])
    assert i1 == const("VecItems1")
    assert i3 == const("VecItems3")
    assert hashlib.sha256(i1.encode("ascii")).hexdigest() == const("VecDigest1")
    assert hashlib.sha256(i3.encode("ascii")).hexdigest() == const("VecDigest3")


def _named_case(proc, name, suite="topstrip"):
    """One case line, matched on its NAME.

    Safe to match on the name here (unlike the LogScrub cases, which are
    matched on their input): every case prints its name whatever its verdict,
    so a mutation that breaks the case reds it rather than making it vanish.
    """
    hits = [l for l in proc.stdout.splitlines()
            if l.startswith("[" + suite + "] ") and (" | case=" + name + " |") in l]
    assert len(hits) == 1, "expected one %r case, found %d" % (name, len(hits))
    return hits[0]


def test_two_electors_file_one_ffa_game_under_one_key(harness_run):
    """The HIGH this suite exists for.

    The election can return two reporters, deliberately: a seat that has
    received no witness property falls back while its peers do not, because
    nobody reporting loses the sitting outright. That is only survivable if
    the server can SEE the duplicate, and the key used to carry each seat's
    own clock and its own game counter -- so the two reports collided with
    nothing and one game settled twice.

    Asserted on the printed keys, not on the verdict: a case that stopped
    comparing would still say PASS.
    """
    line = _named_case(harness_run, "two seats agree on the key", "ffareport")
    assert line.startswith("[ffareport] PASS"), line
    got = line.split(" | got=", 1)[1]
    m = re.match(r"^a=(\S+) b=(\S+)$", got.strip())
    assert m, got
    assert m.group(1) == m.group(2), "the two seats produced different keys: " + got
    assert re.search(r"_r\d+$", m.group(1)), (
        "the key lost the suffix the server parses: " + m.group(1))


def test_the_report_key_still_satisfies_the_server_contract(harness_run):
    """backend/api/main.py's _ffa_room_game_no pulls the game number out of
    this key with an anchored `_r(\\d+)$` and settles that game's bets on it.
    A key ending any other way falls back to "games_played + 1", which settles
    the wrong game's wagers on an out-of-order report -- and nothing errors."""
    line = _named_case(harness_run, "the server can recover the game number", "ffareport")
    assert line.startswith("[ffareport] PASS"), line
    assert "value=11" in line, (
        "the server's own regex no longer recovers the number the key carries: " + line)
    # And the same regex the server uses, evaluated here on the production
    # source rather than on a copy of it.
    server = (REPO / "backend" / "api" / "main.py").read_text(encoding="utf-8")
    assert r'_re.search(r"_r(\d+)$", room_id or "")' in server, (
        "the server's room-id parser moved; the client key must move with it")


@pytest.mark.parametrize("name", [
    "the key is a pure function of its inputs",
    "a rollover after the freeze cannot change the key",
    "a seat keying the rolled-over number would file a different game",
    "an absent snapshot yields no key and no eligibility",
    "mixed snapshots: the unsnapshotted seat cannot file and the others are distinguishable",
    "different games get different keys",
    "the key fits the column",
    "degenerate inputs are legal or absent, never invented",
    "election is total without witnesses",
    "witnesses are the electorate",
    "election is order-independent",
    "an empty room elects nobody",
    "an unparseable electorate still elects one seat",
    "one parseable id outranks the ordinal fallback",
    "a settled refusal is recognised, a neighbour is not",
    "409 and 403 are terminal, 503 is not",
    "a later freeze cannot move a key already taken",
    "a seat that froze after the rollover files a different game",
    "a cleared snapshot files nothing",
])
def test_the_ffa_report_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "ffareport")
    assert line.startswith("[ffareport] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


def test_the_column_lays_simultaneous_surfaces_out_disjointly(harness_run):
    """The MEDIUM this suite exists for: six surfaces painting in the same
    frame used to be given the same y, because the column stored only the
    maximum bottom edge. Asserted on the case's printed MEASUREMENT, not on its
    verdict alone -- a case that stopped measuring would otherwise still say
    PASS."""
    line = _named_case(harness_run, "six claimants are disjoint")
    assert line.startswith("[topstrip] PASS"), line
    got = line.split(" | got=", 1)[1]
    ys = [float(v) for v in got.split(",")]
    assert len(ys) == 6, got
    assert ys == sorted(ys) and len(set(ys)) == 6, (
        "the claimants were not given six distinct increasing positions: " + got)
    assert ys[0] == 0.0, "the first claimant no longer starts at the top: " + got


@pytest.mark.parametrize("name", [
    "two claims stack",
    "short close does not climb back",
    "close does not undo a claim made inside the band",
    "empty open band consumes nothing",
    "painted open band advances",
    "NaN claim consumes nothing",
    "band does not survive a frame tick",
    "stale frame reads zero",
])
def test_the_column_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name)
    assert line.startswith("[topstrip] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


def test_the_suite_carries_its_own_two_way_control(harness_run):
    """Every PASS above is a measurement of nothing unless the SAME corpus,
    unscrubbed, still counts residues. The suite's last case is that control
    and it prints both numbers."""
    line = [l for l in harness_run.stdout.splitlines() if "CONTROL unscrubbed=" in l]
    assert line, "the corpus control no longer runs"
    m = re.search(r"unscrubbed=(-?\d+) scrubbed=(-?\d+)", line[0])
    assert m, line[0]
    assert int(m.group(1)) > 0, "the residue counter saw nothing to remove -- it is blind"
    assert int(m.group(2)) == 0, "residues survived the scrub"
    assert line[0].startswith("[logscrub] PASS")


def _cases(proc):
    """(verdict, input, output) per printed LogScrub case.

    Matched on the case's INPUT, never on its output. The identifier cases
    exist to prove a token SURVIVES the scrub, so searching the output for that
    token is a check that cannot fail: the mutation those cases exist to catch
    is exactly the one that removes it, and a line that no longer contains it
    then reads as "no such case" rather than as a failure.
    """
    out = []
    for line in proc.stdout.splitlines():
        if not line.startswith("[logscrub] "):
            continue
        if " | in=" not in line or " | out=" not in line:
            continue
        head, rest = line.split(" | in=", 1)
        given, produced = rest.split(" | out=", 1)
        out.append((head, given, produced))
    return out


def test_the_identifier_cases_are_in_the_corpus(harness_run):
    """The shapes an over-wide word boundary used to eat. They are NEGATIVE
    cases: the scrub must leave them byte-identical.

    The one-sided ones matter as much as the surrounded ones. A case with a
    joiner on BOTH sides survives a widening of either boundary alone, so it
    cannot tell which side broke; the last four touch the name on one side
    each, so a widened LEADING boundary reds two of them and a widened TRAILING
    boundary reds the other two.
    """
    cases = _cases(harness_run)
    assert cases, "no case lines were printed -- the reader stopped measuring"
    for needle in ("cr_testuser_ready", "Landfall.testuser.Config", "map-testuser-3",
                   "testuser_ready", "testuser.log", "cr_testuser", "map-testuser"):
        hits = [c for c in cases if needle in c[1]]
        assert hits, "no case covers %r" % needle
        for head, given, produced in hits:
            assert head.startswith("[logscrub] PASS"), "%s | in=%s" % (head, given)
            assert " reps=0" in head, (
                "%r was rewritten by the bare-name pass: %s" % (needle, head))
            assert needle in produced, (
                "%r did not survive the scrub: %r" % (needle, produced))


def test_the_harness_compiles_only_the_rule_files():
    """A default compile glob would drag in the whole plugin tree, which does
    not build without Unity -- and would make this harness quietly untestable.
    """
    csproj = HARNESS.read_text(encoding="utf-8")
    assert "<EnableDefaultCompileItems>false</EnableDefaultCompileItems>" in csproj
    included = re.findall(r'<Compile Include="([^"]+)"', csproj)
    assert "Main.cs" in included
    for rule_file in ("plugin/LogScrub.cs", "plugin/TopStripBand.cs",
                      "plugin/FfaReportRules.cs", "plugin/RosterCensusRules.cs",
                      "plugin/BinderSortRules.cs", "plugin/TitleLadderRules.cs",
                      "plugin/PcTradeRules.cs",
                      "plugin/RoomRulesStrip.cs", "plugin/MusicLevels.cs",
                      "plugin/SecureRouteRules.cs", "plugin/SecureRouteText.cs",
                      "plugin/NameGlyphs.cs",
                      "plugin/SessionReportRules.cs", "plugin/ShowcaseRules.cs"):
        assert any(p.endswith(rule_file) for p in included), (
            "%s is not compiled into the harness" % rule_file)
    # The ladder rules' cases are the harness's own half of the partial
    # class: compiled here, and never shipped in the plugin.
    assert "TitleLadderRulesSelfTest.cs" in included
    plugin_proj = (REPO / "plugin" / "CompetitiveRounds.csproj").read_text(encoding="utf-8")
    assert "TitleLadderRulesSelfTest" not in plugin_proj
    assert not (REPO / "plugin" / "TitleLadderRulesSelfTest.cs").exists()
    # Item 13: the settings model's cases are the harness's own file; the plugin
    # compiles the model and never it. Its I18n stand-in is the board-row-27
    # I18nHarnessStub.cs, asserted below (merge pass 3: one stand-in, not two).
    assert any(p.endswith("plugin/SettingsModel.cs") for p in included)
    for harness_only in ("SettingsModelSelfTest.cs",):
        assert harness_only in included
        assert harness_only.split(".")[0] not in plugin_proj
        assert not (REPO / "plugin" / harness_only).exists()
    # Board row 27: the secure-route cases and the I18n stand-in are the
    # harness's own; the shipped catalogues compile here so the L cases read
    # them, and neither harness file may exist under plugin/.
    assert any(p.endswith("plugin/I18nCatalogues.cs") for p in included)
    for harness_only in ("SecureRouteRulesSelfTest.cs", "I18nHarnessStub.cs"):
        assert harness_only in included, "%s is not compiled into the harness" % harness_only
        assert harness_only.replace(".cs", "") not in plugin_proj
        assert not (REPO / "plugin" / harness_only).exists()
    # Board row 30a: the session report's envelope fixtures, likewise.
    assert "SessionReportRulesSelfTest.cs" in included
    assert "SessionReportRulesSelfTest" not in plugin_proj
    assert not (REPO / "plugin" / "SessionReportRulesSelfTest.cs").exists()


@pytest.mark.parametrize("name", [
    "builds: pages pack as many games as fit and a tall one alone",
    "builds (control): no cap - thirty short games share one page when they fit",
    "builds: chips wrap in pick order and a wide chip takes its own row",
])
def test_the_builds_pages_pack_and_flow_by_the_rules(harness_run, name):
    """Board row 30c: SessionReportRules.PackPages / FlowChips, executed; the
    view measures the blocks and chips and draws where these rules put them."""
    line = _named_case(harness_run, name, "sessionreport")
    assert line.startswith("[sessionreport] PASS"), line


@pytest.mark.parametrize("name", [
    "derive: 1v1 first bloods from the first point of each game",
    "derive: 1v1 longest point streak",
    "derive: 1v1 biggest comeback counts games won only",
    "derive: 1v1 seconds in the lead (rounds)",
    "derive: 1v1 lead changes over the set",
    "derive: every game's rounds race ends on its recorded rounds",
    "derive: points won and lost (1v1)",
    "derive: set shortest, longest, average and total time",
    "derive: the final score counts games won",
    "derive: damage per game in game order",
    "derive: 1v1 kills per game are the other fighter's recorded deaths",
    "derive: hit and block rate per game",
    "derive: cards picked count every pick of the player",
    "derive: gold and XP this set are the server's totals",
    "derive: per-game gold and XP in game order",
    "derive (control): without the totals the legacy gold shows and XP is omitted",
    "derive (control): a stream that skips a point is not replayed",
    "derive: 2v2 points lost are the other side's points",
    "derive: 2v2 has no first blood, streak, comeback or lead (no point events)",
    "derive: an FFA player's games count only the games they played",
    "derive: FFA has no points lost and its games are won by the top score",
])
def test_the_session_report_derives_every_totals_number(harness_run, name):
    """Board row 30d: SessionReportRules.Derive / Replay1v1, executed against
    the envelopes the server tests produced; the model and view only format
    and draw these numbers."""
    line = _named_case(harness_run, name, "sessionreport")
    assert line.startswith("[sessionreport] PASS"), line


@pytest.mark.parametrize("name", [
    "race: 1v1, 2v2 and 1v2 play to 5 rounds, FFA to its lobby's recorded target, unknown when none is recorded",
    "race: an FFA game with no recorded target draws no race to a guessed number and is counted unknown",
    "race (control): a recorded target is the axis even above the scores",
    "race: a 1v1 value of rounds*2+points plots its rounds, FFA floors its half points",
    "race (control): 2v2 and 1v2 streams are not raced (no point events)",
    "race: every 1v1 game's rounds line ends on its recorded rounds",
])
def test_the_race_axis_is_the_modes_win_target(harness_run, name):
    """Board row 30e: SessionReportRules.WinTarget / RaceDivisor /
    RoundsSeries, executed - the race panel plots rounds won against the
    rounds the mode is played to."""
    line = _named_case(harness_run, name, "sessionreport")
    assert line.startswith("[sessionreport] PASS"), line

@pytest.mark.parametrize("name", [
    "presence: a fluid lobby's game lists only who played it, best first (Delta joins in game 2)",
    "presence (control): the union roster names two players game 1 does not have",
    "presence: a side's score is its first playing seat's key; a side with no key has none",
    "presence: a two-player score line needs both keys",
])
def test_a_game_names_only_the_players_who_played_it(harness_run, name):
    """Round 2 M1: SessionReportRules.Standings / SideScore / PairScores,
    executed - a fluid FFA lobby's game omits the players who sat it out and
    a missing score key is never read as a score."""
    line = _named_case(harness_run, name, "sessionreport")
    assert line.startswith("[sessionreport] PASS"), line


@pytest.mark.parametrize("name", [
    "broadcast: a stream that dies during the report fetch defers success, failure and timeout alike",
    "broadcast (control): a live stream plays the report or the screens; the dev entry plays down; a probe that throws defers",
])
def test_every_door_into_playback_asks_the_stream_then(harness_run, name):
    """Round 2 M3: SessionReportRules.PlaybackMayStart / PlaybackAfterFetch,
    executed with a fake stream that goes down during the report fetch."""
    line = _named_case(harness_run, name, "sessionreport")
    assert line.startswith("[sessionreport] PASS"), line


@pytest.mark.parametrize("name", [
    "broadcast: the watched-set lever refuses production and every non-local api",
    "broadcast (control): a local test api is allowed",
])
def test_the_watched_set_lever_runs_only_against_a_local_api(harness_run, name):
    """Round 2 M4: SessionReportRules.DevLeverApiAllowed, executed - the
    TestWatchedSet lever refuses the public host and the LAN production
    addresses, and runs against a local test api only."""
    line = _named_case(harness_run, name, "sessionreport")
    assert line.startswith("[sessionreport] PASS"), line


@pytest.mark.parametrize("name", [
    "broadcast: a status answer replaces the target as its granted tuple, mode and roster together",
    "broadcast: a status roster without a mode the broadcaster plays is never adopted under the old mode",
    "broadcast: a 1v1 status answer names exactly two distinct players",
])
def test_the_broadcaster_retargets_only_to_a_granted_tuple(harness_run, name):
    """Round 4 LOW 2: SessionReportRules.StatusTarget, executed - a
    report-status answer (the account's watch grant, the only tuple the
    report read accepts) replaces the broadcaster's target whole or not at
    all; test_session_report.py pins that ApplyStatus changes the target only
    through it."""
    line = _named_case(harness_run, name, "sessionreport")
    assert line.startswith("[sessionreport] PASS"), line


@pytest.mark.parametrize("name", [
    "provenance: a 1v2 set with no damage reads 'not recorded for this set' - its same-mode pair carries damage",
    "provenance (control): a metric no set of the mode can carry reads 'not supported for this mode'",
    "provenance: every metric a captured set records is one its mode carries",
    "provenance: a 2v2 set with no scores reads 'not recorded for this set' - its same-mode pair carries scores",
    "provenance: a 1v2 set with no scores reads 'not recorded for this set' - its same-mode pair carries scores",
])
def test_an_empty_chart_names_the_set_or_the_mode(harness_run, name):
    """Round 2 L1: SessionReportRules.ModeCarries / MissingReason, executed
    with a same-mode 1v2 pair (one with its damage stream, one without) and
    every captured fixture's recorded metrics; round 3 L1: the same-mode
    2v2 and 1v2 pairs for the score race (every game's scores emptied)."""
    line = _named_case(harness_run, name, "sessionreport")
    assert line.startswith("[sessionreport] PASS"), line


# -- board row 31: the idle showcase's rotation -------------------------------

def test_the_showcase_suite_ran_every_case_and_none_failed(harness_run):
    """Board row 31: ShowcaseRules, executed - the idle showcase walks every
    Compare metric in the tab's own order with one dwell each and leaves the
    rest of its rotation as it was."""
    suites = _suites(harness_run)
    assert "showcase" in suites, "the ShowcaseRules suite did not report"
    run, fail, verdict = suites["showcase"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[showcase\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # 5 cases on the commit that added the suite; the floor is that count
    # (#342). Raise it when cases are added.
    assert run >= 5, "the ShowcaseRules suite shrank to %d cases" % run


@pytest.mark.parametrize("name", [
    "showcase: every metric is one Compare view, in list order, one dwell each",
    "showcase: Home, the two profiles, 2v2 and FFA keep their places and dwells",
    "showcase: the metric dwell defaults to 15 s and is held to 3-300 s",
    "showcase: one rotation shows all 34 metrics in order and logs each once",
    "showcase (control): with fewer than 2 candidates the metric walk is skipped, as before",
])
def test_the_showcase_walk_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "showcase")
    assert line.startswith("[showcase] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


@pytest.mark.parametrize("name", [
    "broadcast: the page dwell defaults to 12 s and is held to 3-300 s",
    "broadcast: the walk shows every page once, in order, then ends",
    "broadcast: the anchor is the newest in-window game and its viewer played it",
    "broadcast (control): no anchor when nobody of the roster played the newest game",
])
def test_the_broadcaster_pages_through_the_report(harness_run, name):
    """Board row 30g: SessionReportRules.BroadcastPageDwell / BroadcastNextPage
    / NewestAnchor, executed - the broadcaster's dwell per page, its walk over
    every page and the game (and player) the watched set's report is asked
    for."""
    line = _named_case(harness_run, name, "sessionreport")
    assert line.startswith("[sessionreport] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


# -- v1.41.0 item 22: the standing room-rules strip's line ----------------------

def test_the_room_rules_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "roomrules" in suites, "the RoomRulesStrip suite did not report"
    run, fail, verdict = suites["roomrules"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[roomrules\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # The suite ran 12 cases on the commit that added it (#342: a floor far
    # below the real count is a gate that cannot fail).
    assert run >= 12, "the RoomRulesStrip suite shrank to %d cases" % run


@pytest.mark.parametrize("name", [
    "default rules paint nothing",
    "same cards alone names same cards",
    "a fell-back dealer alone says same cards is off",
    "friendly fire off alone names friendly fire",
    "friendly fire off with same cards names both",
    "friendly fire off with a fell-back dealer names both",
    "every non-default pair has its own line",
    "friendly fire is named exactly when it is off",
    "the cfg key off hides every line",
    "the cfg key on paints every line but None",
    "only the fell-back lines are amber",
    "the same-cards-only chooser says nothing for a friendly-fire-off room (control)",
])
def test_the_room_rules_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "roomrules")
    assert line.startswith("[roomrules] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


# -- v1.41.0 item 23: the custom-music ceiling and fade envelopes ----------------

def test_the_music_levels_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "musiclevels" in suites, "the MusicLevels suite did not report"
    run, fail, verdict = suites["musiclevels"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[musiclevels\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # The suite ran 18 cases on the commit that added it, 26 once the
    # measured levels and the volume migration joined, and 43 once round 2's
    # per-clip gains and first-track fade decision joined (#342).
    assert run >= 43, "the MusicLevels suite shrank to %d cases" % run


@pytest.mark.parametrize("name", [
    "the slider's 100 maps to at most half of the old output",
    "every stored percent is scaled by the same factor",
    "the slider never gets quieter as it rises",
    "the slider clamps outside 0..100",
    "the pre-1.41 slider is louder than half at 100 (control)",
    "the default plays at the soundtrack's level, within 1 dB",
    "the slider's 100 is at most 6.5 dB over the soundtrack",
    "the default sits below the ceiling",
    "the pre-1.41 default sat over 30 dB above the soundtrack (control)",
    "a stored 100 becomes the default once",
    "a stored 100 stays once the migration has run",
    "the migration never changes any other value",
    "a migration that resets every value fails the leave-alone check (control)",
    "the short fade starts at zero gain (60fps)",
    "the short fade reaches full gain at 0.6 s, not before (60fps)",
    "the long fade starts at zero gain (60fps)",
    "the long fade reaches full gain at 2.5 s, not before (60fps)",
    "the short fade starts at zero gain (10fps)",
    "the short fade reaches full gain at 0.6 s, not before (10fps)",
    "the long fade starts at zero gain (10fps)",
    "the long fade reaches full gain at 2.5 s, not before (10fps)",
    "the long fade is perceptual: a quarter gain at half time",
    "at 0.6 s the long fade is still under a tenth of full gain",
    "a one-second hitch counts as a tenth of a second",
    "a zero or negative frame does not advance the fade",
    "the short envelope reaches full gain well before 2.5 s (control)",
    # round 2, M1: the per-clip gains
    "every catalog clip's gain brings it to the one target",
    "the full tracks' post-gain RMS spread is at most 3.0 dB",
    "the previews' post-gain RMS spread is at most 3.0 dB",
    "one global gain leaves the full tracks over 3 dB apart (control)",
    "the default percent plays a custom clip within 1 dB of the calibration point",
    "no clip peaks at or above 0 dBFS at the slider's 100 after its gain",
    "a target 4 dB higher would peak over full scale at 100 (control)",
    "every table clip is found and an unknown clip reads false at gain 1",
    # round 2, M2: the first-track fade decision
    "an audible vanilla menu arms the short fade and names the game's music",
    "later starts after an audible menu stay short",
    "a silent menu arms the long fade exactly once",
    "the mod's own audible menu music arms the short fade",
    "a muted game music volume makes the vanilla menu silent",
    "a start while still in the menu never consumes the decision",
    "the latest menu sample decides",
    "returning to the menu clears a stale decision",
    "the round-1 rule arms long after the default vanilla menu (control)",
])
def test_the_music_levels_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "musiclevels")
    assert line.startswith("[musiclevels] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


# -- report 3 (2026-09-30): the one name sanitiser of the list panels ----------

def test_the_name_glyphs_suite_ran_every_case_and_none_failed(harness_run):
    suites = _suites(harness_run)
    assert "nameglyphs" in suites, "the NameGlyphs suite did not report"
    run, fail, verdict = suites["nameglyphs"]
    assert fail == 0 and verdict == "PASS", harness_run.stdout[-4000:]
    printed = len(re.findall(r"^\[nameglyphs\] (PASS|FAIL) ", harness_run.stdout, re.M))
    assert printed == run, (
        "the suite declared run=%d but printed %d case lines" % (run, printed))
    # 16 cases on the commit that added it (#342).
    assert run >= 16, "the NameGlyphs suite shrank to %d cases" % run


@pytest.mark.parametrize("name", [
    "U+13171 (Egyptian hieroglyph, supplementary plane) becomes the fallback",
    "a supplementary-plane emoji (U+1F600) becomes the fallback",
    "a supplementary-plane letter the chain carries is kept whole",
    "a basic-plane glyph the chain lacks (U+25EF) becomes the fallback",
    "accented Latin and Cyrillic the chain carries are kept",
    "a pair cut by a truncation (lone high surrogate) becomes the fallback",
    "a lone low surrogate becomes the fallback",
    "controls and the line separators flatten to a space",
    "a rich-text opener cannot open a tag",
    "the glyph pass alone leaves tag characters to its caller",
    "an ASCII name is returned unchanged",
    "null and empty become empty",
    "a throwing font answer counts as not renderable",
    "the fallback is visible ASCII and not a thin letter",
    "never longer, and every code point left renders",
    "the raw name keeps the unrenderable code points (control)",
])
def test_the_name_glyphs_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "nameglyphs")
    assert line.startswith("[nameglyphs] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)
