"""The mutation runner's new-controls swap: which report it is taken from.

The runner's control `new-controls-list-credits-another-round` edits one
mutation-controls report's list of the controls new in its round. Round 17's
run of the committed runner refused before its anchor pre-check: it took the
swap from the NEWEST report, round 16's report lists none, and there was
nothing to take out of an empty list. Round 18's rule, stated in the runner
where the gate lives: the swap derives from the newest report that LISTS a new
control, and a report that lists none does not move it.

These are that rule's tests. Two on the rule itself, on fabricated reports:

  - a report that lists no new control leaves the swap where it was -- the
    negative case, and the one round 17 refused on -- and the committed
    directory obeys the same rule;
  - a report that lists one moves the swap to it.

And the control on the pair (#391): the empty-list refusal restored inside
the runner's own function reddens the first case and not the second, and an
inert twin at the same site -- the same statement reflowed -- reddens
neither. The edits are made to the function's source in memory; no file is
written.
"""
import importlib.util
import inspect
import pathlib

EVIDENCE = pathlib.Path(__file__).resolve().parent / "evidence"
RUNNER = EVIDENCE / "mutation-runner.py"
CONTROL = "new-controls-list-credits-another-round"

# The site the control below edits, inside _claim_swap_from: the rule's own
# statement. It has to resolve exactly once in that function, or the control
# would edit some other site, or none.
SKIP = ("        if not claimed:\n"
        "            # A report that lists no new control does not move the swap.\n"
        "            continue\n")
# The mutant: the refusal round 17 hit, put back -- a report that lists no
# new control stops the derivation instead of being passed over.
REFUSE = ("        if not claimed:\n"
          "            return name, UNDERIVED, UNDERIVED, UNDERIVED, (\n"
          "                '%s lists no control as new in its round' % name)\n")
# The inert twin: the same statement with its condition reflowed.
REFLOWED = ("        if len(claimed) == 0:\n"
            "            # A report that lists no new control does not move the swap.\n"
            "            continue\n")


def _runner():
    spec = importlib.util.spec_from_file_location(
        "_scr_mutation_runner_swap_rule", str(RUNNER))
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def _derivation(runner, edit=None):
    """The runner's _claim_swap_from, as committed or with `edit` = (old, new)
    applied once to its source, compiled against the runner's own globals."""
    source = inspect.getsource(runner._claim_swap_from)
    if edit is not None:
        old, new = edit
        assert source.count(old) == 1, (
            "the site this control edits resolves %d times in "
            "_claim_swap_from" % source.count(old))
        source = source.replace(old, new)
    namespace = dict(vars(runner))
    exec(compile(source, str(RUNNER), "exec"), namespace)
    return namespace["_claim_swap_from"]


def _fixtures(rules):
    """Three reports and the inventory that tags them: round 3 lists two new
    controls (the evidence rules' own fabricated report), round 4 lists none,
    round 5 lists one."""
    listed = ("r3-mutation-controls.txt", rules.FABRICATED_REPORT)
    unlisted = ("r4-mutation-controls.txt",
                "A mutation controls report.\n"
                "\n"
                "stdout: r4-run.log\n"
                "\n"
                "== this round's new controls ==\n"
                "None. This round adds no control.\n"
                "\n"
                "== a later section ==\n"
                "  not-a-claim-about-this-round\n")
    later = ("r5-mutation-controls.txt",
             "A mutation controls report.\n"
             "\n"
             "stdout: r5-run.log\n"
             "\n"
             "== this round's new controls ==\n"
             "  a-fifth-round-control\n"
             "      What it mutates.\n"
             "\n"
             "== a later section ==\n")
    inventory = (rules.FABRICATED_INVENTORY
                 + "  a-fifth-round-control (r5)  what it does\n")
    # The fixtures say what they are meant to, or the cases below prove
    # nothing: the empty report parses as listing none, the others as listing.
    assert rules.controls_claimed_new(unlisted[1]) == [], unlisted
    assert rules.controls_claimed_new(listed[1]) == [
        "a-thing-that-broke", "another-thing-that-broke"]
    assert rules.controls_claimed_new(later[1]) == ["a-fifth-round-control"]
    return listed, unlisted, later, inventory


def test_a_report_that_lists_no_new_control_leaves_the_swap_where_it_was():
    runner = _runner()
    rules = runner._RULES
    listed, unlisted, _later, inventory = _fixtures(rules)
    derive = runner._claim_swap_from

    before = derive([listed], inventory)
    assert before == ("r3-mutation-controls.txt", "  a-thing-that-broke\n",
                      "  an-older-control\n", "  a-thing-that-broke \n",
                      None), before
    # A newer report that lists none: the swap does not move, and nothing
    # refuses. In either order -- the derivation orders by round.
    assert derive([listed, unlisted], inventory) == before
    assert derive([unlisted, listed], inventory) == before
    # What still refuses: no report listing a new control at all -- and it
    # says so rather than failing on an anchor.
    source, anchor, _mutant, _inert, why = derive([unlisted], inventory)
    assert source is None and anchor == runner.UNDERIVED, (source, anchor)
    assert why and "lists a new control" in why, why

    # The committed directory, by the same rule: the swap resolved, its
    # source lists a new control, every NEWER report lists none, and the
    # control carries that report as the file it edits.
    assert runner._SWAP_WHY is None, runner._SWAP_WHY
    reports = {p.name: p.read_text(encoding="utf-8", errors="replace")
               for p in EVIDENCE.iterdir()
               if p.name.endswith("-mutation-controls.txt")}
    source = runner._SWAP_SOURCE
    assert source in reports, (source, sorted(reports))
    assert rules.controls_claimed_new(reports[source]), source
    newer = [n for n in reports
             if (rules.round_of(n) or 0) > rules.round_of(source)]
    for name in newer:
        assert not rules.controls_claimed_new(reports[name]), (name, source)
    assert pathlib.Path(runner.SWAP_REPORT).name == source
    carried = [c for c in runner.CONTROLS if c[0] == CONTROL]
    assert len(carried) == 1, len(carried)
    assert pathlib.Path(carried[0][1]).name == source, carried[0][1]
    assert carried[0][2] == runner._SWAP_ANCHOR != runner.UNDERIVED


def test_a_report_that_lists_a_new_control_moves_the_swap_to_it():
    runner = _runner()
    listed, unlisted, later, inventory = _fixtures(runner._RULES)
    derive = runner._claim_swap_from

    moved = derive([listed, unlisted, later], inventory)
    assert moved == ("r5-mutation-controls.txt", "  a-fifth-round-control\n",
                     "  a-thing-that-broke\n", "  a-fifth-round-control \n",
                     None), moved
    assert moved[0] != derive([listed, unlisted], inventory)[0]


def test_restoring_the_empty_list_refusal_reddens_the_no_control_case_only():
    runner = _runner()
    listed, unlisted, later, inventory = _fixtures(runner._RULES)
    committed = _derivation(runner)
    refusing = _derivation(runner, (SKIP, REFUSE))
    reflowed = _derivation(runner, (SKIP, REFLOWED))
    no_control = [listed, unlisted]
    moved = [listed, unlisted, later]

    # The compiled copy is the function the other two tests call.
    for case in (no_control, moved):
        assert committed(case, inventory) == runner._claim_swap_from(
            case, inventory)

    # RED: with the refusal back, the no-control case refuses, as round 17's
    # runner did -- which is exactly what the first test forbids...
    red = refusing(no_control, inventory)
    assert red[4] is not None, red
    assert red != committed(no_control, inventory), red
    # ...and only that case: a report that lists one still moves the swap.
    assert refusing(moved, inventory) == committed(moved, inventory)

    # GREEN: the inert twin changes neither case.
    for case in (no_control, moved):
        assert reflowed(case, inventory) == committed(case, inventory)
