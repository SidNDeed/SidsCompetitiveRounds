"""FAQ-R1 F1: the early-leave grace needs the leave figure, so the server requires it.

The grace (main.py _ffa_leave_decision) is decided from game_points_at_leave. A
report whose entry left DURING the game (left_early and not absent) without that
figure cannot be graded under the rule, so submit_ffa_match refuses it with 422
ahead of the session check, the settlement of other expired journal windows and
the lobby lock. An absent ghost and a present seat need no figure.

Each refusal case has a control that differs only in the field under test and
reaches the next step of the route (a sentinel raised by the session check, or,
on the settlement path, by the HMAC verification _verify_ffa_hmac), so a check that refused
everything, or nothing, is red here. The mutation control replaces the helper
with one that finds nothing and shows the refusal disappears.

On the client a 422 is not a terminal FFA refusal: FfaReportRules.IsTerminalRefusal,
both overloads, is false for 422 and 400 and true for 409 and 403, EXECUTED by
the client rules harness (its ffaleavefigure suite, with a mutant per overload
that makes 422 terminal and must be caught). OutboxPass needs Unity; the lines
of it this lane reads are pinned as source by the last test here, which states
what it asserts and no more.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from fastapi import HTTPException

import main
import schemas

REPO = Path(main.__file__).resolve().parents[2]


class _Reached(Exception):
    """The route got past the leave-figure check."""


class _NoDb:
    """A database handle that must never be touched by a refused report."""

    def __getattr__(self, name):
        raise AssertionError("the database was touched (%s) before the refusal" % name)


def _entry(steam, slot, rounds, points, *, left=False, absent=False, gp=None):
    return schemas.FfaPlayerEntry(
        steam_id=steam, slot=slot, rounds_won=rounds, points_total=points,
        left_early=left, absent=absent, game_points_at_leave=gp)


def _report(*entries):
    return schemas.FfaMatchReport(
        lobby_id="00000000-0000-0000-0000-000000000001", photon_room_id="room_r1",
        winner_steam_id=entries[0].steam_id, reported_by_steam_id=entries[0].steam_id,
        is_ranked=True, players=list(entries))


W, B, L = "76561190000000101", "76561190000000102", "76561190000000103"


def _submit(monkeypatch, report, *, journal=False):
    """Run the route up to its first step after the check. Returns the
    HTTPException it raised, or the string "reached" when it got past the
    check (the session check, or on the settlement path the HMAC verification
    _verify_ffa_hmac, raised _Reached)."""
    async def session(*_a, **_k):
        raise _Reached()

    monkeypatch.setattr(main, "_check_steam_session", session)

    async def go():
        tok = main._RDM_JOURNAL_MODE.set({"game": 1, "cls": "c"}) if journal else None
        try:
            if journal:
                # The settlement path has no session check: its first step after
                # the leave-figure check is the HMAC verification.
                monkeypatch.setattr(main, "_verify_ffa_hmac", lambda r: (_ for _ in ()).throw(_Reached()))
            await main.submit_ffa_match(report, None, _NoDb())
        except _Reached:
            return "reached"
        except HTTPException as ex:
            return ex
        finally:
            if tok is not None:
                main._RDM_JOURNAL_MODE.reset(tok)
        raise AssertionError("the route returned without raising")
    return asyncio.run(go())


FIGURELESS = (_entry(W, 0, 5, 10), _entry(B, 1, 3, 6), _entry(L, 2, 0, 1, left=True))
WITH_FIGURE = (_entry(W, 0, 5, 10), _entry(B, 1, 3, 6), _entry(L, 2, 0, 1, left=True, gp=3))
GHOST = (_entry(W, 0, 5, 10), _entry(B, 1, 3, 6), _entry(L, 2, 0, 0, left=True, absent=True))
PRESENT = (_entry(W, 0, 5, 10), _entry(B, 1, 3, 6), _entry(L, 2, 0, 1))


@pytest.mark.parametrize("journal", [False, True], ids=["request", "journal settlement"])
def test_a_figureless_entry_that_left_during_the_game_is_refused_before_any_step(monkeypatch, journal):
    got = _submit(monkeypatch, _report(*FIGURELESS), journal=journal)
    assert isinstance(got, HTTPException), got
    assert got.status_code == 422, got.status_code
    assert "game_points_at_leave" in got.detail and L in got.detail, got.detail
    assert W not in got.detail and B not in got.detail, got.detail


@pytest.mark.parametrize("journal", [False, True], ids=["request", "journal settlement"])
@pytest.mark.parametrize("players", [WITH_FIGURE, GHOST, PRESENT],
                         ids=["leaver with the figure", "absent ghost without it", "present seat"])
def test_the_controls_pass_the_check(monkeypatch, journal, players):
    assert _submit(monkeypatch, _report(*players), journal=journal) == "reached"


def test_a_figure_of_zero_is_a_figure():
    zero = _report(_entry(W, 0, 5, 10), _entry(B, 1, 3, 6), _entry(L, 2, 0, 0, left=True, gp=0))
    assert main._ffa_missing_leave_figure(zero) == []


def test_every_figureless_leaver_is_named():
    two = _report(_entry(W, 0, 5, 10), _entry(B, 1, 0, 1, left=True), _entry(L, 2, 0, 0, left=True))
    assert main._ffa_missing_leave_figure(two) == [B, L]


def test_the_refusal_is_the_helpers(monkeypatch):
    """Mutation control: with the helper finding nothing, the same figureless
    report reaches the session check."""
    monkeypatch.setattr(main, "_ffa_missing_leave_figure", lambda report: [])
    assert _submit(monkeypatch, _report(*FIGURELESS)) == "reached"


def test_the_grace_decision_is_unchanged_for_a_report_with_the_figure():
    """The check adds a refusal and changes no decision: the same leaver with
    a figure below the threshold is graced, and with one at it is not."""
    half = main._ffa_leave_grace_half_points()
    for gp, graced in ((half - 1, True), (half, False)):
        rep = _report(_entry(W, 0, 5, 10), _entry(B, 1, 3, 6), _entry(L, 2, 0, 1, left=True, gp=gp))
        _ghosts, got, _log = main._ffa_leave_decision(
            rep, True, grace_half=half, points_to_win_round=main.FFA_POINTS_TO_WIN_ROUND)
        assert (L in got) is graced, (gp, got)


def _block(src, start_pat):
    m = re.search(start_pat, src)
    assert m, start_pat
    depth, i = 0, src.index("{", m.end())
    for j in range(i, len(src)):
        depth += {"{": 1, "}": -1}.get(src[j], 0)
        if depth == 0:
            return src[i:j + 1]
    raise AssertionError("unbalanced block after " + start_pat)


from test_client_rules_harness import _suites, harness_run  # noqa: E402,F401  (the module fixture)

LEAVE_FIGURE_CASES = (
    "real: code 422 is not terminal",
    "real: text 422 is not terminal",
    "real: text 422 is the HTTP <code>: <body> form",
    "real: code 409 is terminal",
    "real: text 409 is terminal",
    "real: code 403 is terminal",
    "real: text 403 is terminal",
    "real: code 400 is not terminal",
    "real: text 400 is not terminal",
    "mutant (code overload makes 422 terminal) is caught by its own case",
    "mutant (text overload makes 422 terminal) is caught by its own case",
)


def test_both_terminal_refusal_overloads_leave_a_422_to_the_outbox(harness_run):
    """FfaReportRules.IsTerminalRefusal(long) and (string), run on 422 (the
    leave-figure refusal, as the client's own RequestErrorText formats it) and
    on the real terminals 409 and 403; a mutant of either overload that makes
    422 terminal fails exactly its own case. Each named case printed PASS, and
    the suite ran exactly these."""
    suites = _suites(harness_run)
    assert "ffaleavefigure" in suites, harness_run.stdout[-4000:]
    run, fail, verdict = suites["ffaleavefigure"]
    assert (run, fail, verdict) == (len(LEAVE_FIGURE_CASES), 0, "PASS"), harness_run.stdout[-4000:]
    printed = re.findall(r"^\[ffaleavefigure\] (PASS|FAIL) \| case=([^|]+?) \|", harness_run.stdout, re.M)
    assert sorted(name for _, name in printed) == sorted(LEAVE_FIGURE_CASES), printed
    assert {v for v, _ in printed} == {"PASS"}, printed


def test_the_outbox_permanent_predicate_reads_http_4_and_spares_401_and_429():
    """A source pin (OutboxPass needs Unity), on OutboxPass's code lines: the
    permanent predicate reads the "HTTP 4" prefix; the retryable transients
    name 429 and 401, each in both text forms; a permanent or exhausted body
    is removed (_pendingReports.Remove); and the give-back answer is computed
    from what the request carried (OutboxAnswerFor) before the permanent
    predicate, with the attempt handed back. The predicate's other terms are
    not pinned here."""
    client = (REPO / "plugin" / "ApiClient.cs").read_text(encoding="utf-8")
    outbox = _block(client, r"private static IEnumerator OutboxPass\(\)")
    code = "\n".join(line for line in outbox.splitlines() if not line.lstrip().startswith("//"))
    assert 'resp.StartsWith("HTTP 4", StringComparison.Ordinal)' in code
    assert "if (permanent || p.attempts >= OUTBOX_MAX_ATTEMPTS)" in code
    assert "_pendingReports.Remove(p)" in code.split("if (permanent || p.attempts >= OUTBOX_MAX_ATTEMPTS)")[1]
    transient = code.split("bool retryableTransient")[1].split(";")[0]
    assert re.findall(r"HTTP(?:/1\.1)? (\d{3})", transient) == ["429", "429", "401", "401"], transient
    # The give-back is decided from what the request carried, before the status.
    give_back = code.index("if (answer == SecureRouteRules.OutboxAnswer.GiveBack)")
    assert code.index("SecureRouteRules.OutboxAnswerFor(ok, carried)") < give_back
    assert "p.attempts--;" in code[give_back:code.index("bool permanent")]
    assert give_back < code.index("bool permanent")
