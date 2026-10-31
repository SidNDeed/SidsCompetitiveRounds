"""FAQ-R1 F1: the early-leave grace needs the leave figure, so the server requires it.

The grace (main.py _ffa_leave_decision) is decided from game_points_at_leave. A
report whose entry left DURING the game (left_early and not absent) without that
figure cannot be graded under the rule, so submit_ffa_match refuses it with 422
before anything runs: before the session check, before the settlement of other
expired journal windows, before the lobby lock, so before any write. An absent
ghost and a present seat need no figure.

Each refusal case has a control that differs only in the field under test and
reaches the next step of the route (a sentinel raised by the session check, or
by the journal recheck on the settlement path), so a check that refused
everything, or nothing, is red here. The mutation control replaces the helper
with one that finds nothing and shows the refusal disappears.

The 422 is chosen from the client's outbox handling (plugin/ApiClient.cs): a
422 is not a terminal FFA refusal (FfaReportRules.IsTerminalRefusal is 409 and
403 only), so the report goes to the outbox, whose first retry drops any
"HTTP 4xx" answer other than 401 and 429 as permanent. The last test pins that
reading of the client source, so a client change that would make a 422 retry
forever reddens it.
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
    check (the session check, or the journal recheck, raised _Reached)."""
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


def test_the_client_drops_a_422_from_its_outbox_rather_than_retrying_it():
    """The reading the 422 rests on. FfaReportRules.IsTerminalRefusal names 409
    and 403 only, so a 422 is queued (the FFA send's else branch); OutboxPass
    treats every "HTTP 4" answer as permanent except 401 and 429, and drops it."""
    rules = (REPO / "plugin" / "FfaReportRules.cs").read_text(encoding="utf-8")
    terminal = _block(rules, r"internal static bool IsTerminalRefusal\(long statusCode\)")
    assert "SettledRefusalStatus" in terminal and "QuarantinedRefusalStatus" in terminal
    assert re.search(r"QuarantinedRefusalStatus\s*=\s*403\b", rules)
    assert re.search(r"SettledRefusalStatus\s*=\s*409\b", rules)
    client = (REPO / "plugin" / "ApiClient.cs").read_text(encoding="utf-8")
    outbox = _block(client, r"private static IEnumerator OutboxPass\(\)")
    code = "\n".join(line for line in outbox.splitlines() if not line.lstrip().startswith("//"))
    assert 'resp.StartsWith("HTTP 4", StringComparison.Ordinal)' in code
    assert "if (permanent || p.attempts >= OUTBOX_MAX_ATTEMPTS)" in code
    assert "_pendingReports.Remove(p)" in code.split("if (permanent || p.attempts >= OUTBOX_MAX_ATTEMPTS)")[1]
    transient = code.split("bool retryableTransient")[1].split(";")[0]
    assert re.findall(r"HTTP(?:/1\.1)? (\d{3})", transient) == ["429", "429", "401", "401"], transient
    assert "422" not in code
