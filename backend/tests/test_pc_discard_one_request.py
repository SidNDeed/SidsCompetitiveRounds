"""Bugs #364 and #368 — one request per discarded print, and a bounded wait.

Both reports describe the same thing: discarding cards quickly stalls every
few copies. The client used to send three requests per copy (the discard, then
a collection refetch, then a balance refetch), so a run of ten copies spent
thirty requests against a shared budget and started being refused part-way
through. The client half that sends ONE request per copy has been in the tree
since 2026-09-14 and has never been in a released DLL, and nothing anywhere
asserted the request count — which is how a report comment came to deny a
change that is built.

So these are source-shape gates on the client, in the sense of
`test_player_cards_client_text.py`: they read `plugin/PlayerCardsUI.cs`
structurally and fail when the shape the reports depend on is edited away.

Two things they deliberately do NOT do:

* They never assert on raw C# text. Everything is decided on `_cs_structure`'s
  mask, so a brace or a needle inside a comment, a string or an inactive `#if`
  branch is not structure (learnings #342/#431/#441).
* They never carry a hand-written list of "the methods that issue a request".
  Such a list is a check that cannot fail: the next fetch helper added to
  `ApiClient` is absent from it, so re-introducing a refetch under a new name
  would pass. Instead each `ApiClient` member the block actually calls is
  looked up in `ApiClient.cs` and classified by whether its OWN body starts a
  request coroutine. A helper that only parses a JSON answer is not a request;
  anything that reaches `PostRequest`/`GetRequest` is.

What they cannot see: whether the server answers, and how quickly. That is the
in-game run (ten fast discards, ten `[PC] discard` lines, no `rate_limited`).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from _cs_structure import (CsParseError, and_terms, cs_block, guard_chain,
                           initialiser, mask_code, method_spans)

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
PLAYER_CARDS = PLUGIN / "PlayerCardsUI.cs"
API_CLIENT = PLUGIN / "ApiClient.cs"

PC_CLASS = "internal static class PlayerCardsUI"
DISCARD_NEXT = "DiscardNext(string id)"
FINISH_DISCARD = "FinishDiscard(string id, string errorCode)"
IDENTITY_CHANGED = "OnIdentityChanged()"

_CALL = re.compile(r"\bApiClient\.(\w+)\s*\(")
_REQUEST_STARTERS = ("PostRequest(", "GetRequest(")


# ── classifying an ApiClient member by its own body ──────────────────────

def _api_member_body(name: str) -> str:
    """The masked body of `ApiClient.<name>`, located structurally.

    Raises rather than returning nothing: a member that cannot be found is a
    gate that silently stopped measuring, which is the failure this module is
    written against.
    """
    src = API_CLIENT.read_text(encoding="utf-8")
    masked = mask_code(src)
    decl = re.compile(rf"\bstatic\s+[\w<>,\[\]\?\. ]+?\b{re.escape(name)}\s*\(")
    hits = list(decl.finditer(masked))
    if not hits:
        raise CsParseError(f"ApiClient has no static declaration of {name!r}")

    bodies = []
    for hit in hits:
        # walk to the ) that closes the parameter list
        depth, i = 0, hit.end() - 1
        while i < len(masked):
            if masked[i] == "(":
                depth += 1
            elif masked[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        else:
            raise CsParseError(f"{name!r}: unterminated parameter list")

        after = i + 1
        while after < len(masked) and masked[after].isspace():
            after += 1
        if masked.startswith("=>", after):          # expression-bodied member
            end = masked.find(";", after)
            if end == -1:
                raise CsParseError(f"{name!r}: unterminated expression body")
            bodies.append(masked[after:end])
            continue

        signature = masked[hit.start():i + 1]
        spans = list(method_spans(src, signature))
        if len(spans) != 1:
            raise CsParseError(
                f"{len(spans)} blocks match the declaration of {name!r}"
            )
        open_brace, close = spans[0]
        bodies.append(masked[open_brace:close])

    return "\n".join(bodies)


def _issues_a_request(name: str) -> bool:
    body = _api_member_body(name)
    return "StartCoroutine(" in body and any(s in body for s in _REQUEST_STARTERS)


def _requests_in(signature: str) -> list:
    """Every `ApiClient.X(...)` call in `signature`'s block that starts a request."""
    block = cs_block(PLAYER_CARDS, signature)
    called = _CALL.findall(mask_code(block))
    return [n for n in called if _issues_a_request(n)]


# ── the gate on the classifier itself (learning #391) ────────────────────

def test_the_request_classifier_separates_a_fetch_from_a_parse_helper():
    # Without this, every assertion below could be passing because the
    # classifier answers False for everything.
    assert _issues_a_request("PcDiscard")
    assert _issues_a_request("FetchPcMe")
    assert _issues_a_request("FetchPcCollection")
    assert not _issues_a_request("PcErrorCode")
    assert not _issues_a_request("PcRetryAfter")
    assert not _issues_a_request("PcInt")


# ── #364/#368: one request per print ─────────────────────────────────────

def test_one_discard_sends_exactly_one_request_per_print():
    # Control: insert `ApiClient.FetchPcMe(id, true);` into DiscardNext -> red.
    assert _requests_in(DISCARD_NEXT) == ["PcDiscard"]


def test_a_clean_discard_run_ends_without_refetching_anything():
    # The collection and the balance are updated from each discard's own
    # answer. The one refetch left is for a refusal that suggests the local
    # copy is what was wrong, and it must stay behind that condition.
    assert sorted(_requests_in(FINISH_DISCARD)) == ["FetchPcCollection", "FetchPcMe"]

    terms = []
    for needle in ("ApiClient.FetchPcCollection(", "ApiClient.FetchPcMe("):
        conditions = guard_chain(PLAYER_CARDS, FINISH_DISCARD, needle)
        assert conditions, f"{needle} is reachable unconditionally"
        for condition in conditions:
            terms.extend(and_terms(condition))
    # Control: delete this term from the condition -> red.
    assert "errorCode != null" in terms
    assert 'errorCode != "rate_limited"' in terms


def test_the_discard_block_names_no_superseded_rate_limit():
    # The card routes have carried a budget of their own since 2026-09-15; the
    # block used to describe the shared sensitive-path limit instead, which is
    # the class of comment a numbered learning already killed (#432/#434).
    # Control: re-insert "the api's sensitive-path limit is 20 in 10 s" -> red.
    block = cs_block(PLAYER_CARDS, DISCARD_NEXT).lower()
    assert "sensitive" not in block
    assert "20 in 10" not in block


# ── the wait a refused run may do is bounded ─────────────────────────────

def test_a_refused_discard_run_is_bounded_by_a_wait_budget():
    conditions = guard_chain(PLAYER_CARDS, DISCARD_NEXT, "StartCoroutine(DiscardAfter")
    terms = [t for c in conditions for t in and_terms(c)]
    # Control: delete this term from the condition -> red.
    budgeted = [t for t in terms if "discardWaited" in t and "DiscardWaitBudget" in t]
    assert budgeted, f"the retry is not compared against a budget: {terms}"

    value = initialiser(PLAYER_CARDS, PC_CLASS, "DiscardWaitBudget")
    assert float(value.rstrip("fF")) > 0


def test_an_identity_change_clears_the_discard_run_state():
    # FinishDiscard is not on this path, so a retry flag left set here would be
    # spent on the next account's first refusal.
    code = mask_code(cs_block(PLAYER_CARDS, IDENTITY_CHANGED))
    assert "discardRetried = false" in code
    assert "discardWaited = 0f" in code


# ── the negative control for the reader itself ───────────────────────────

def test_the_gates_read_a_block_that_exists():
    with pytest.raises(CsParseError):
        cs_block(PLAYER_CARDS, "DiscardNextButSpelledWrong(string id)")
