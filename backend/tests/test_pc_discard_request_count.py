"""Bugs #364 and #368 -- how many requests ONE clean discard puts on the wire.

The reports: discarding cards quickly stalls every few copies. The diagnosis
(2026-09-16): each discard sent three requests -- the discard, then a forced
re-read of the binder, then a forced re-read of the balance -- so about seven
quick discards spent a twenty-in-ten-seconds budget. The client half that sends
ONE request per discard is commit 0079fdd9 (2026-09-13), carried into the
v1.41.0 client lane and never in a released DLL.

`test_pc_discard_one_request.py` pins the SHAPE of today's discard path. This
module COUNTS: it walks a clean one-copy discard -- the discard step, then the
run's finish with no error code -- and adds up the request-issuing ApiClient
calls reachable on that path, at two revisions of plugin/PlayerCardsUI.cs:

  * BEFORE: b4831add, the last revision before 0079fdd9 (read from git);
  * AFTER: the working tree.

and asserts 3 and 1. The BEFORE arm is the negative control: the same walk,
the same classifier, the same guard evaluation, red on the pre-fix source --
so a walk that stopped seeing requests would turn BEFORE to 0 and fail here.

How a call is judged reachable on the clean path: every `if` that dominates it
(`_cs_structure.guard_chain`) is split into its && terms and each term is
evaluated with `errorCode = null` and `id` non-null (a clean run of a signed-in
player). A term the evaluator does not model fails the test rather than being
guessed, so a new condition cannot quietly count as "taken" or "not taken".

The request classifier is `test_pc_discard_one_request._issues_a_request`
(transitive over ApiClient), applied to both revisions by NAME; the three names
involved -- PcDiscard, FetchPcCollection, FetchPcMe -- issue requests at both.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from _cs_structure import CsParseError, and_terms, cs_block, guard_chain, mask_code
from test_pc_discard_one_request import _issues_a_request

REPO = Path(__file__).resolve().parents[2]
PLAYER_CARDS = REPO / "plugin" / "PlayerCardsUI.cs"
BEFORE_REV = "b4831add"
_CALL = re.compile(r"\bApiClient\.(\w+)\s*\(")


def _before_source() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "show", BEFORE_REV + ":plugin/PlayerCardsUI.cs"],
                              capture_output=True, text=True, encoding="utf-8", check=True, timeout=60).stdout
    except (OSError, subprocess.CalledProcessError) as ex:
        pytest.fail("the BEFORE revision %s is not readable from git: %s" % (BEFORE_REV, ex))


def _signature(src: str, name: str) -> str:
    sigs = re.findall(r"\b(%s\([^)]*\))" % re.escape(name), mask_code(src))
    decls = sorted({s for s in sigs if s.startswith(name + "(string")})
    if len(decls) != 1:
        raise CsParseError("%s: %d declarations %r" % (name, len(decls), decls))
    return decls[0]


def _term_on_clean_path(term: str) -> bool:
    t = " ".join(term.split())
    if t == "id != null":
        return True
    if t == "errorCode != null":
        return False
    if t == "errorCode == null":
        return True
    if re.fullmatch(r'errorCode != "[a-z_]+"', t):
        return True
    if re.fullmatch(r'errorCode == "[a-z_]+"', t):
        return False
    raise AssertionError("a guard term this count does not model: %r" % t)


def _clean_path_requests(src: str, method: str) -> list:
    sig = _signature(src, method)
    block = mask_code(cs_block(src, sig))
    names = [n for n in _CALL.findall(block) if _issues_a_request(n)]
    taken = []
    for n in sorted(set(names)):
        if names.count(n) != 1:
            raise CsParseError("%s calls ApiClient.%s %d times; the walk needs one" % (method, n, names.count(n)))
        conditions = guard_chain(src, sig, "ApiClient.%s(" % n)
        if all(_term_on_clean_path(t) for c in conditions for t in and_terms(c)):
            taken.append(n)
    return taken


def requests_per_clean_discard(src: str) -> tuple:
    step = _clean_path_requests(src, "DiscardNext")
    finish = _clean_path_requests(src, "FinishDiscard")
    return len(step) + len(finish), step, finish


def test_before_the_fix_one_discard_sent_three_requests():
    n, step, finish = requests_per_clean_discard(_before_source())
    assert (n, step, sorted(finish)) == (3, ["PcDiscard"], ["FetchPcCollection", "FetchPcMe"]), (n, step, finish)


def test_after_the_fix_one_discard_sends_one_request():
    n, step, finish = requests_per_clean_discard(PLAYER_CARDS.read_text(encoding="utf-8"))
    assert (n, step, finish) == (1, ["PcDiscard"], []), (n, step, finish)


def test_the_guard_evaluator_refuses_a_term_it_does_not_model():
    assert _term_on_clean_path("id != null") is True
    assert _term_on_clean_path('errorCode != "transport"') is True
    assert _term_on_clean_path("errorCode != null") is False
    with pytest.raises(AssertionError):
        _term_on_clean_path("discardDone > 0")
