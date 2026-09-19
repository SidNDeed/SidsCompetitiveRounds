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

* They never decide STRUCTURE on raw C# text. Every structural claim -- what
  is called, what guards it, what a constant is -- is decided on
  `_cs_structure`'s mask, so a brace or a needle inside a comment, a string or
  an inactive `#if` branch is not structure (learnings #342/#431/#441).

  Two gates read other views on purpose, and neither is a structural claim.
  The stale-wording gate reads the block WITH its comments, because prose is
  the thing it is about. The reason-code gates read a view that keeps string
  literals, because a reason code IS a literal and the mask blanks it. Saying
  "never raw C# text" made both look like violations of a rule this module
  does not actually hold.
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
import functools
from pathlib import Path

import pytest

from _cs_structure import (CsParseError, and_terms, cs_block, guard_chain,
                           initialiser, mask_code, method_spans,
                           strip_comments_only)

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
PLAYER_CARDS = PLUGIN / "PlayerCardsUI.cs"
API_CLIENT = PLUGIN / "ApiClient.cs"

PC_CLASS = "internal static class PlayerCardsUI"
DISCARD_NEXT = "DiscardNext(string id)"
FINISH_DISCARD = "FinishDiscard(string id, string errorCode)"
IDENTITY_CHANGED = "OnIdentityChanged()"

_CALL = re.compile(r"\bApiClient\.(\w+)\s*\(")
_BARE_CALL = re.compile(r"\b(\w+)\s*\(")
# The three coroutines that actually put bytes on the wire. SendRequest is the
# one the old two-name list missed, and it is not an obscure corner: every
# session-authenticated call reaches the network through SessionSend, which
# delegates to it and starts no Post/GetRequest of its own.
_REQUEST_STARTERS = ("PostRequest(", "GetRequest(", "SendRequest(")
_MAX_DELEGATION_DEPTH = 6


# ── classifying an ApiClient member by its own body ──────────────────────

@functools.lru_cache(maxsize=1)
def _api_masked() -> tuple:
    """ApiClient's source and its mask, read and masked ONCE.

    The delegation walk asks for many bodies and revisits some; without this
    each ask re-read and re-masked a twenty-thousand-line file, which turned a
    two-second module into a two-minute one.
    """
    src = API_CLIENT.read_text(encoding="utf-8")
    return src, mask_code(src)


@functools.lru_cache(maxsize=None)
def _api_member_body(name: str) -> str:
    """The masked body of `ApiClient.<name>`, located structurally.

    Raises rather than returning nothing: a member that cannot be found is a
    gate that silently stopped measuring, which is the failure this module is
    written against.
    """
    src, masked = _api_masked()
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


@functools.lru_cache(maxsize=1)
def _api_member_names() -> frozenset:
    """Every name ApiClient declares as a static member.

    Used to tell an intra-class call apart from a BCL call, so the walk below
    follows the former and ignores the latter.
    """
    _, masked = _api_masked()
    return frozenset(
        re.findall(r"\bstatic\s+[\w<>,\[\]\?\. ]+?\b(\w+)\s*\(", masked)
    )


def _issues_a_request(name: str, _seen: frozenset = frozenset()) -> bool:
    """Whether `ApiClient.<name>` ends up putting a request on the wire.

    TRANSITIVE, and that is the whole point of the rewrite. This used to look
    at one level only -- does this member's own body start a coroutine over
    PostRequest or GetRequest -- so a member that DELEGATES answered False and
    was counted as costing nothing. SessionSend is the live example: it starts
    SendRequest, which was in neither name, so anything routed through it read
    as free. A gate that undercounts requests is the same defect this module
    exists to catch, wearing the reviewer's clothes.

    Bounded by a visited set and a depth cap, so a mutual call pair terminates
    rather than recursing until Python gives up.
    """
    if name in _seen or len(_seen) >= _MAX_DELEGATION_DEPTH:
        return False
    body = _api_member_body(name)
    if any(s in body for s in _REQUEST_STARTERS):
        return True
    members = _api_member_names()
    seen = _seen | {name}
    for callee in sorted(set(_BARE_CALL.findall(body))):
        if callee in members and callee not in seen and _issues_a_request(callee, seen):
            return True
    return False


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
    # A member that reaches the network only through a SIBLING. It answered
    # False while the classifier looked one level deep, which made every
    # session-authenticated call invisible to the counts below.
    assert _issues_a_request("SessionSend")
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
    # Control: delete any one of these terms from the condition -> red.
    assert "errorCode != null" in terms
    assert 'errorCode != "rate_limited"' in terms
    # The transport exclusion was absent here, so deleting it stayed green. It
    # is not decoration: "transport" means no answer arrived, and answering a
    # silent network by immediately asking it two more questions is the same
    # pile-on the rate-limit exclusions exist to prevent.
    assert 'errorCode != "transport"' in terms


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
    # The pause we are ABOUT to take counts too. Comparing only the pauses
    # already taken lets the last retry overshoot by a whole Retry-After.
    assert any("wait" in t for t in budgeted), budgeted

    value = initialiser(PLAYER_CARDS, PC_CLASS, "DiscardWaitBudget")
    assert float(value.rstrip("fF")) > 0


def test_the_wait_budget_is_compared_against_a_value_that_moves():
    """The assertion above passes on an expression that can never be false.

    `discardWaited + wait <= DiscardWaitBudget` bounds NOTHING if discardWaited
    is never advanced: it stays 0f, every ordinary Retry-After clears
    0 + wait <= 20, and the run retries without end -- which is the exact
    behaviour the budget was added to stop. Reading the comparison and not the
    accumulator is how a bound-shaped expression passes for a bound
    (#306/#342/#431). The increment has to be on the same branch that spends
    the wait, so it is looked for BETWEEN the comparison and the coroutine.
    """
    block = mask_code(cs_block(PLAYER_CARDS, DISCARD_NEXT))
    cond = block.index("DiscardWaitBudget")
    start = block.index("StartCoroutine(DiscardAfter")
    assert cond < start, "the budget is no longer tested before the wait starts"
    branch = block[cond:start]
    assert re.search(r"discardWaited\s*\+=\s*wait\s*;", branch), (
        "the branch that spends a wait does not advance the accumulator it is "
        f"compared against: {branch!r}"
    )


def test_an_identity_change_clears_the_discard_run_state():
    # FinishDiscard is not on this path, so a retry latch left set here would
    # be spent on the next account's first refusal.
    code = mask_code(cs_block(PLAYER_CARDS, IDENTITY_CHANGED))
    assert "discardRetriedIds.Clear()" in code
    assert "discardWaited = 0f" in code
    # discardInFlight was missing from this list, so dropping it from the reset
    # stayed green -- and it is the field that WEDGES the surface: left true
    # across an identity change, the binder keeps saying "discarding..." and
    # the button stays dead for an account that never started a run.
    assert "discardInFlight = false" in code


# ── the retry is ONE PER COPY, inside the run budget ─────────────────────

def test_the_retry_latch_is_keyed_by_the_copy():
    """A run-wide bool is not "one retry per copy", however the comment reads.

    It was cleared on every resumption, so it meant "one retry IN FLIGHT":
    a single stubborn print could be re-asked over and over -- six times at the
    default 3 s pause -- and spend the whole run budget by itself, leaving the
    copies queued behind it with none of the retry the rule promised them.
    """
    code = mask_code(cs_block(PLAYER_CARDS, DISCARD_NEXT))
    assert "discardRetriedIds.Contains(pid)" in code, (
        "the retry is not gated on THIS copy having had one")
    assert "discardRetriedIds.Add(pid)" in code, (
        "taking the retry does not record which copy took it")


def test_the_resumption_does_not_return_the_copys_retry():
    """Resuming IS the retry. Clearing the latch there gives it straight back,
    which is what turned per-copy into per-in-flight."""
    code = mask_code(cs_block(PLAYER_CARDS, "DiscardAfter(string id, float seconds, int ep)"))
    assert "DiscardNext(id)" in code, "the resumption no longer resumes"
    assert "discardRetried" not in code, (
        f"the resumption still touches the retry latch: {code!r}")


def test_an_exhausted_budget_is_reported_as_its_own_reason():
    # Comments stripped, literals KEPT: the reason code is a literal, so the
    # mask used everywhere else would blank the very thing being read.
    code = strip_comments_only(cs_block(PLAYER_CARDS, DISCARD_NEXT))
    assert 'FinishDiscard(id, "rate_limit_waited")' in code, (
        "an exhausted wait budget still finishes as a plain rate_limited "
        "refusal, so the player is told to wait a few seconds after we have "
        "already waited twenty")


RATE_LIMIT_REASONS = ("rate_limited", "rate_limit_waited")
LOCALES = ("es", "ru", "uk", "sv")


def _reason_sentences() -> dict:
    """code -> English sentence, read from ReasonText's own switch.

    Derived, not listed: a hand-written copy of these sentences would go on
    passing after the code reworded one of them.
    """
    block = cs_block(PLAYER_CARDS, "ReasonText(string code)")
    return dict(re.findall(
        r'case "([\w-]+)":\s*return I18n\.Tr\("([^"]+)"\);', block))


def test_the_two_rate_limit_reasons_are_different_sentences():
    pairs = _reason_sentences()
    for code in RATE_LIMIT_REASONS:
        assert code in pairs, f"ReasonText has no sentence for {code}: {sorted(pairs)}"
    assert pairs["rate_limited"] != pairs["rate_limit_waited"], (
        "both rate-limit outcomes render the same sentence")


@pytest.mark.parametrize("lang", LOCALES)
def test_both_rate_limit_sentences_are_translated_in_every_locale(lang):
    """The artifact that RENDERS is the DLL-bundled catalogue, never a SQL
    seed (#583); a key with no entry renders English with every other gate
    green (#578). Nothing else in the tree covered a PlayerCardsUI reason --
    each surface carries its own gate and this one had none -- and the
    exhausted-budget sentence is seen only after twenty seconds of waiting,
    which is the worst moment to hand somebody untranslated text.
    """
    from test_pc_sept12 import _bundled_catalogues

    pairs = _reason_sentences()
    catalogue = _bundled_catalogues()[lang]
    missing = [c for c in RATE_LIMIT_REASONS
               if not (catalogue.get(pairs[c]) or "").strip()]
    echoed = [c for c in RATE_LIMIT_REASONS if catalogue.get(pairs[c]) == pairs[c]]
    assert not missing, f"{lang}: no catalogue entry for {missing}"
    assert not echoed, f"{lang}: {echoed} still render the English sentence"


def test_an_exhausted_budget_does_not_trigger_the_refetches():
    """Two refetches on top of a limit that is already refusing us are exactly
    what the one-request-per-copy change removed. A budget we just exhausted is
    the moment we most need to stop asking."""
    for needle in ("ApiClient.FetchPcCollection(", "ApiClient.FetchPcMe("):
        terms = [t for c in guard_chain(PLAYER_CARDS, FINISH_DISCARD, needle)
                 for t in and_terms(c)]
        assert 'errorCode != "rate_limit_waited"' in terms, (
            f"{needle} is not excluded for an exhausted budget: {terms}")


# ── the negative control for the reader itself ───────────────────────────

def test_the_gates_read_a_block_that_exists():
    with pytest.raises(CsParseError):
        cs_block(PLAYER_CARDS, "DiscardNextButSpelledWrong(string id)")
