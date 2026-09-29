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
    """Item 12 follow-up: the animal title ladders as entries of the Shop's
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
    # The suite ran 38 cases on the commit that added it and 51 once the
    # popup's IMGUI event shield joined it (r2); the floor is that count, not
    # one far below it (#342). Raise it when cases are added.
    assert run >= 51, "the TitleLadderRules suite shrank to %d cases" % run


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
    # the popup's tier rows and bar
    "tier rows read Owned, Current, Next, then Locked",
    "not started: the entry rung is Next and every other rung Locked",
    "a line held at the top has one Current row and no Next row (control)",
    "80 series held at tier 4 fills 5 of 75",
    "not started draws an empty bar",
    "the top draws a full bar",
    "a line with no rungs: Buy, disabled, no rungs",
    # the popup's IMGUI event shield (r2)
    "a press inside the open popup is used and latches its button",
    "a press outside the popup's extent passes (control)",
    "the frame the popup closed still uses a press inside its extent",
    "the frame after it passes a fresh press (control)",
    "the release of a latched press is used after the popup has gone, and clears the latch",
    "a release with no latch and no popup passes (control)",
    "a drag of the latched button is used wherever it lands and keeps the latch",
    "a drag of another button passes (control)",
    "two latched buttons release one at a time",
    "a press the shield lets through clears that button's stale latch",
    "an IMGUI modal above the popup keeps its clicks and the latch is dropped",
    "Layout, Repaint and keys are never used and never move the latch",
    "a scroll and a context click inside the open popup are used and latch nothing",
])
def test_the_ladder_shop_guarantees_each_have_a_case(harness_run, name):
    line = _named_case(harness_run, name, "laddershop")
    assert line.startswith("[laddershop] PASS"), line
    assert " | got=" in line and not line.rstrip().endswith("| got="), (
        "the case printed no measurement: " + line)


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
                      "plugin/RoomRulesStrip.cs", "plugin/MusicLevels.cs"):
        assert any(p.endswith(rule_file) for p in included), (
            "%s is not compiled into the harness" % rule_file)
    # The ladder rules' cases are the harness's own half of the partial
    # class: compiled here, and never shipped in the plugin.
    assert "TitleLadderRulesSelfTest.cs" in included
    plugin_proj = (REPO / "plugin" / "CompetitiveRounds.csproj").read_text(encoding="utf-8")
    assert "TitleLadderRulesSelfTest" not in plugin_proj
    assert not (REPO / "plugin" / "TitleLadderRulesSelfTest.cs").exists()


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
