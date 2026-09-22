"""Bug #392, item A step 1 — the in-room involuntary leave cause.

Four things are asserted here, one per sub-item of the brief, each with the
mutation that reddens it and the control that stops the fix from degenerating
into its own opposite:

  (1) the new tag is recognised as IN-ROOM everywhere the old literal was, and
      no comparison against an in-room literal survives anywhere in main.py;
  (3) the display reconciliation is display-ONLY — the reconciled set is read
      at exactly one place, the ffa_match_players INSERT, and nowhere else in
      the report handler;
  (4) the capability the client reads before it sends the tag is present and
      DERIVED from the vocabulary, so it can actually go false.

plus the wire constraint the tag has to fit through.

The persistence half of (2) and the executable half of (3) need a real
PostgreSQL and live in test_ffa_departure_cause_pg.py.
"""

from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path

import pytest

import main


MAIN_PATH = (Path(__file__).parents[1] / "api" / "main.py").resolve()
MAIN_SRC = MAIN_PATH.read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SRC)

REPO = MAIN_PATH.parents[2]

# The client half of bug #392 sits on this tree now, so the wire name is no
# longer transcribed here from a branch this checkout cannot see — it is read
# out of the client's own source. These two files are the whole of the wire
# contract's client side: one DECLARES the name, the other CONSUMES it.
CLIENT_CONSTANT_PATH = REPO / "plugin" / "TransportExit.cs"
CLIENT_READER_PATH = REPO / "plugin" / "ApiClient.cs"

_CLIENT_CAPABILITY_CONST = re.compile(
    r'\bconst\s+string\s+CapabilityField\s*=\s*"([^"]*)"\s*;')


def _client_capability_field(src: str) -> str:
    """The client's `CapabilityField` literal, read out of C# source text.

    Raises unless the source DECLARES it exactly once. A reader that matched
    nothing and returned a default, or that silently took the first of
    several declarations, would make the comparison it feeds a check that
    cannot fail (#342) — the server constant would be compared against a
    value this helper invented rather than one the client ships.
    """
    hits = _CLIENT_CAPABILITY_CONST.findall(src)
    if len(hits) != 1:
        raise AssertionError(
            'expected exactly one `const string CapabilityField = "..."` '
            f"declaration in the client source, found {len(hits)}: {hits}")
    return hits[0]


# ── helpers ──────────────────────────────────────────────────────────────

def _function(name: str) -> ast.AST:
    """The module-level function `name`, sync or async."""
    for node in MAIN_TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"main.py has no module-level function {name!r} — "
                         "the walk below would have silently measured nothing")


def _literal_cause_comparisons(tree: ast.AST, tags) -> list[tuple[int, str]]:
    """Every `<expr> ==/!=/in/not in <one of tags>` comparison in `tree`.

    This is the class check (#432): the fix is not "line 45208 now calls a
    helper", it is "no site anywhere decides in-room-ness by comparing against
    an in-room literal". A second handler carried the identical construct.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for operand in [node.left, *node.comparators]:
            consts = ([operand] if isinstance(operand, ast.Constant)
                      else list(getattr(operand, "elts", [])))
            for c in consts:
                if isinstance(c, ast.Constant) and c.value in tags:
                    found.append((node.lineno, str(c.value)))
    return found


def _name_events(fn: ast.AST, name: str, ctx) -> list[ast.Name]:
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ctx)]


def _calls_to(fn: ast.AST, name: str) -> list[ast.Call]:
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name]


def _route(path: str):
    for r in main.app.routes:
        if getattr(r, "path", None) == path:
            return r
    raise AssertionError(f"no route {path!r} on the app — "
                         "every assertion below would have been vacuous")


def _query_param_max_length(path: str, param: str) -> int:
    route = _route(path)
    for p in route.dependant.query_params:
        if p.name != param:
            continue
        for meta in getattr(p.field_info, "metadata", []) or []:
            ml = getattr(meta, "max_length", None)
            if ml is not None:
                return int(ml)
        ml = getattr(p.field_info, "max_length", None)
        if ml is not None:
            return int(ml)
        raise AssertionError(f"{path} query param {param!r} declares no max_length")
    raise AssertionError(f"{path} has no query param {param!r}")


# ── (0) the detector itself can fail ─────────────────────────────────────

def test_literal_comparison_detector_finds_the_construct_it_hunts():
    """Positive control for the sweep below (#342).

    A sweep that returns an empty list because it cannot see the construct is
    indistinguishable from a clean tree, and would pass forever. Feed it the
    exact shape the fix removed and require it to be seen.
    """
    planted = ast.parse(
        "def f(cause):\n"
        "    a = cause == 'in_room_exit'\n"
        "    b = cause in ('in_room_timeout', 'x')\n"
        "    c = cause == 'fresh_cancel'\n"
        "    return a, b, c\n"
    )
    hits = _literal_cause_comparisons(planted, main._IN_ROOM_EXIT_CAUSES)
    assert sorted(t for _, t in hits) == ["in_room_exit", "in_room_timeout"], hits
    # ...and it does NOT flag a cause comparison that is not an in-room tag.
    assert all(t != "fresh_cancel" for _, t in hits)


# ── (1) recognition ──────────────────────────────────────────────────────

def test_vocabulary_involuntary_is_a_subset_of_in_room():
    """An involuntary tag that was not also in-room would un-veto dissolution
    — the precise failure this item exists to prevent."""
    assert main._INVOLUNTARY_EXIT_CAUSES, "an empty involuntary set makes every test below vacuous"
    assert main._INVOLUNTARY_EXIT_CAUSES <= main._IN_ROOM_EXIT_CAUSES
    assert "in_room_exit" in main._IN_ROOM_EXIT_CAUSES, "the pre-existing tag must keep its veto"


def test_new_tag_is_in_room():
    """The mutation: drop the new tag from _IN_ROOM_EXIT_CAUSES and this reds."""
    assert main._is_in_room_exit_cause("in_room_timeout") is True
    assert main._is_in_room_exit_cause("in_room_exit") is True


def test_voluntary_and_absent_causes_are_not_in_room():
    """The negative control.

    Without it the fix degenerates into "every leave is in-room", i.e. never
    dissolve — which re-opens the husk class that the dissolution branch
    exists to close. An absent cause is an OLD CLIENT and must keep exactly
    the evidence-based behaviour it has today.
    """
    for cause in ("", None, "fresh_cancel", "menu_click", "watchdog", "in_room", "timeout"):
        assert main._is_in_room_exit_cause(cause) is False, cause


def test_involuntary_predicate_separates_the_two_in_room_tags():
    """The second negative control: `in_room_exit` is in-room but CHOSEN.

    A predicate that answered true for every in-room tag would soften the
    display mark on every ordinary mid-game quit, which is strictly worse than
    the bug — it erases genuine early leaves.
    """
    assert main._is_involuntary_exit_cause("in_room_timeout") is True
    for cause in ("in_room_exit", "", None, "fresh_cancel", "menu_click"):
        assert main._is_involuntary_exit_cause(cause) is False, cause


def test_no_in_room_literal_comparison_survives_anywhere():
    """The class sweep: not one line, the whole module."""
    hits = _literal_cause_comparisons(MAIN_TREE, main._IN_ROOM_EXIT_CAUSES)
    assert hits == [], (
        "in-room-ness is still decided by comparing against a literal at "
        f"main.py {hits} — every such site must ask _is_in_room_exit_cause")


@pytest.mark.parametrize(
    "handler, flag, expected_loads",
    [("ffa_queue_leave", "_in_room_exit", 3),
     ("ovt_queue_leave", "_ovt_in_room_exit", 2)],
)
def test_each_leave_handler_derives_its_veto_once_and_uses_every_site(
        handler, flag, expected_loads):
    """Occurrence counts asserted within the FUNCTION span, never file-wide.

    One store (the derivation) and an exact number of loads (the veto sites).
    The mutation that reddens this is deleting a veto — for the FFA handler,
    dropping `and not _in_room_exit` from either dissolution predicate, or
    `or _in_room_exit` from `game_live_now`, each of which alone would put a
    timed-out seat's lobby back on the dissolution path.
    """
    fn = _function(handler)
    assert len(_calls_to(fn, "_is_in_room_exit_cause")) == 1
    assert len(_name_events(fn, flag, ast.Store)) == 1
    assert len(_name_events(fn, flag, ast.Load)) == expected_loads


def test_every_departed_ids_writer_also_writes_the_cause():
    """(2), statically: persistence has no hole.

    Three statements append to departed_ids — the rowless-leaver path, the
    live-game branch and the closing branch. A cause persisted by two of them
    is a cause that is simply missing for whichever path a given leave takes.
    """
    ffa = _function("ffa_queue_leave")
    sqls = [c.value for c in ast.walk(ffa)
            if isinstance(c, ast.Constant) and isinstance(c.value, str)
            and "departed_ids" in c.value and "UPDATE ffa_lobbies" in c.value]
    assert len(sqls) == 3, f"expected 3 departed_ids writers, found {len(sqls)}"
    for sql in sqls:
        assert "departure_causes" in sql, (
            "a departed_ids append that does not carry the cause:\n" + sql)


# ── wire constraint ──────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/api/v1/ffa/queue/leave", "/api/v1/ovt/queue/leave"])
def test_every_in_room_tag_fits_the_declared_wire_limit(path):
    """The limit is READ off the live route, not restated here (#342).

    Hardcoding 16 would make this pass even if the route's own constraint
    moved. The mutation: lengthen any tag by one character and this reds.
    """
    limit = _query_param_max_length(path, "cause")
    assert limit > 0
    for tag in main._IN_ROOM_EXIT_CAUSES:
        assert len(tag) <= limit, f"{tag!r} ({len(tag)}) exceeds the wire limit {limit}"


def test_the_wire_limit_is_enforced_not_assumed():
    """The negative control for the limit: a tag one character too long is
    rejected by the running app, and the real tag is not."""
    from fastapi.testclient import TestClient

    limit = _query_param_max_length("/api/v1/ffa/queue/leave", "cause")
    client = TestClient(main.app, raise_server_exceptions=False)
    headers = {"X-Mod-Version": main.LATEST_MOD_VERSION}

    too_long = client.post(
        f"/api/v1/ffa/queue/leave?steam_id=0&cause={'x' * (limit + 1)}", headers=headers)
    assert too_long.status_code == 422, too_long.text
    assert "cause" in too_long.text

    # The real tag clears validation. It does NOT reach a database here, so the
    # only claim is the one being made: 422 is about the length, not the tag.
    tag = sorted(main._INVOLUNTARY_EXIT_CAUSES)[0]
    ok = client.post(f"/api/v1/ffa/queue/leave?steam_id=0&cause={tag}", headers=headers)
    assert ok.status_code != 422, ok.text


# ── (3) display only ─────────────────────────────────────────────────────

def _ffa_insert_call() -> ast.Call:
    fn = _function("submit_ffa_match")
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        for arg in node.args:
            for c in ast.walk(arg):
                if (isinstance(c, ast.Constant) and isinstance(c.value, str)
                        and "INSERT INTO ffa_match_players" in c.value):
                    return node
    raise AssertionError("submit_ffa_match no longer contains the "
                         "ffa_match_players INSERT this test is anchored to")


def test_reconciled_set_is_read_only_by_the_match_row_insert():
    """The heart of "display only", as a containment check rather than prose.

    `_involuntary_departed` is derived once and consumed at least once, and
    every load of it must fall INSIDE the ffa_match_players INSERT call — so
    no load reached the placement sort, the rating application, the XP/gold
    award, the `unrated` set, or the departure record.

    What this enforces is the LOCATION of each read, not how many reads there
    are: a second read INSIDE the INSERT is permitted by design and leaves
    this check passing, which is what the inert twin beside the mutation
    demonstrates. What reddens it is a load OUTSIDE the call — the store count
    above pins the single derivation, and the >= 1 assertion is the control
    that fires if a later edit deletes the consumer and leaves a dead
    variable.
    """
    fn = _function("submit_ffa_match")
    assert len(_name_events(fn, "_involuntary_departed", ast.Store)) == 1

    loads = _name_events(fn, "_involuntary_departed", ast.Load)
    assert len(loads) >= 1, "nothing consumes the reconciled set — the write is dead"

    call = _ffa_insert_call()
    lo, hi = call.lineno, call.end_lineno
    outside = [n.lineno for n in loads if not (lo <= n.lineno <= hi)]
    assert outside == [], (
        "the reconciled set is read outside the ffa_match_players INSERT at "
        f"main.py lines {outside} — that is no longer display-only")


def test_stored_left_early_and_the_economy_are_untouched():
    """The rating/XP/gold control.

    Whether an involuntary drop should change the placement or the rating is a
    game decision that is Sid's (section 8 q2); the default taken here is that
    it changes NEITHER. So the report's own `left_early` still lands in the
    row verbatim, and the new column is an addition beside it.
    """
    src = ast.get_source_segment(MAIN_SRC, _ffa_insert_call()) or ""
    assert '"le": bool(p.left_early)' in src, "left_early is no longer stored as reported"
    assert "left_early_involuntary" in src and ":lei" in src
    assert '"lei": bool(p.left_early) and str(pid) in _involuntary_departed' in src, (
        "the qualifier must be gated on the mark it qualifies")
    # Nothing in the rating/economy computation may name the new column.
    fn = _function("submit_ffa_match")
    insert = _ffa_insert_call()
    for node in ast.walk(fn):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and "left_early_involuntary" in node.value):
            assert insert.lineno <= node.lineno <= insert.end_lineno, (
                f"left_early_involuntary named outside the INSERT at line {node.lineno}")


@pytest.mark.parametrize("renderer", ["get_match_by_code", "ffa_recent"])
def test_both_renderers_emit_the_qualifier(renderer):
    """The read half of (3): the two endpoints that render the mark.

    A column written and never rendered reconciles nothing. Executed against a
    real row in test_ffa_departure_cause_pg.py; here it is the wiring.
    """
    src = ast.get_source_segment(MAIN_SRC, _function(renderer)) or ""
    assert '"left_early": ' in src, f"{renderer} no longer renders the mark at all"
    assert '"left_early_involuntary": ' in src, (
        f"{renderer} renders left_early without the qualifier — a reader there "
        "still cannot tell a transport failure from a choice")


# ── (4) the capability ───────────────────────────────────────────────────

def test_the_capability_field_is_spelled_the_way_the_client_reads_it():
    """The wire NAME — no longer transcribed here, but READ across the two
    files that have to agree. This is the whole of the contract the first
    build of this lane got wrong.

    The server advertised `involuntary_leave_cause`; the client asks for
    `ffa_involuntary_cause`. Both lanes were green — each asserted its OWN key
    — and the gate could never open, so every column, writer and renderer this
    bug added was live and completely inert.

    While the two halves sat on trees that could not see each other, the only
    check available was this side STATING the literal the other side reads.
    Both halves are on one tree now, so the pin is a CROSS-FILE READ: the
    client's own `CapabilityField` is parsed out of `plugin/TransportExit.cs`
    and compared with the constant the route is bound to. A rename on either
    side alone reddens here as a disagreement naming both values — which is
    exactly the case that used to pass on both sides at once.

    There is no skip-when-missing arm and no fallback to a literal. If the
    client source is not on this tree the first assertion fails, because a
    test that stands down when its subject disappears is a check that cannot
    fail (#342).
    """
    assert CLIENT_CONSTANT_PATH.exists(), (
        f"{CLIENT_CONSTANT_PATH.name} is not on this tree — the client half of "
        "bug #392 is merged into this branch and its constant is what this "
        "assertion reads; without it nothing pins the wire name at all")
    client_value = _client_capability_field(
        CLIENT_CONSTANT_PATH.read_text(encoding="utf-8"))
    assert main._INVOLUNTARY_CAUSE_CAPABILITY_FIELD == client_value, (
        "the two sides of the wire disagree: the server advertises "
        f"{main._INVOLUNTARY_CAUSE_CAPABILITY_FIELD!r} and the client reads "
        f"{client_value!r}")


def test_mod_version_advertises_the_capability():
    """The client reads this route at startup; it is the ordering gate."""
    payload = asyncio.run(main.get_mod_version())
    assert payload[main._INVOLUNTARY_CAUSE_CAPABILITY_FIELD] is True
    # The control: the fields the existing client already parses are still there.
    assert payload["version"] == main.LATEST_MOD_VERSION
    assert payload["min_version"] == main.MIN_MOD_VERSION_EFFECTIVE


def test_the_route_takes_its_field_name_from_the_pinned_constant(monkeypatch):
    """The other half of the pin, and the mutation that reddens it.

    The test above pins the constant; this one proves the ROUTE is bound to
    that constant rather than to a literal typed again in the handler — if it
    were, the pin would guard a name nothing on the wire uses. Renaming the
    constant must rename the wire field, and must leave the old name absent.
    """
    monkeypatch.setattr(main, "_INVOLUNTARY_CAUSE_CAPABILITY_FIELD", "zz_probe_field")
    payload = asyncio.run(main.get_mod_version())
    assert "zz_probe_field" in payload
    assert "ffa_involuntary_cause" not in payload


def test_the_transitional_alias_is_gone_from_the_wire():
    """The first spelling was carried as a SECOND key while the lanes were
    apart. The removal condition written at the constant was that the lanes be
    merged and the client literal be read off the merged tree; this branch is
    that merge and the test above is that read, so the route advertises one
    name for one boolean.

    An absence assertion passes trivially against a route that returned
    nothing, so the canonical key is asserted PRESENT in the same payload as
    its control. The handler's source is checked too, scoped to the function
    span rather than file-wide (#432): the paragraph at the capability
    constant still narrates the original disagreement and names the old
    spelling there as history, which is prose and not an emission.
    """
    payload = asyncio.run(main.get_mod_version())
    assert "involuntary_leave_cause" not in payload, (
        "the transitional alias is back on the wire; keys advertised: "
        f"{sorted(payload)}")
    # The control for that absence: the canonical key IS advertised, so the
    # assertion above cannot be satisfied by an empty or broken payload.
    assert payload[main._INVOLUNTARY_CAUSE_CAPABILITY_FIELD] is True
    assert not hasattr(main, "_INVOLUNTARY_CAUSE_CAPABILITY_ALIAS"), (
        "the alias CONSTANT is back in main.py")
    handler_src = ast.get_source_segment(MAIN_SRC, _function("get_mod_version"))
    assert "involuntary_leave_cause" not in handler_src, (
        "the mod-version handler names the old spelling")


# The words this project's prose uses when it talks about a SECOND spelling of
# the capability key. The census below is keyed on them and not on the retired
# literal, because that is precisely how the stale claim survived: the removal
# swept every file carrying `involuntary_leave_cause`, and the one sentence
# that said the alias was still alive named no literal at all, so the sweep
# could not see it (#432 — a flag names a LINE, the defect is a CLASS).
_SECOND_SPELLING_WORDS = (
    "alias", "transitional", "other spelling", "second spelling",
    "old spelling", "retired spelling",
)
_RETIRED_CAPABILITY_SPELLING = "involuntary_leave_cause"


def _doc_paragraphs(src: str) -> list[tuple[int, str]]:
    """Every `///` doc-comment paragraph in C# source, as (first line, text).

    A paragraph is a run of `///` lines carrying content, ended by a bare `///`
    or by any line that is not a doc comment. That is the unit a claim is
    written in, and the unit a reader takes a claim from.
    """
    out: list[tuple[int, str]] = []
    start, buf = 0, []
    for lineno, raw in enumerate(src.splitlines(), 1):
        stripped = raw.strip()
        body = stripped[3:].strip() if stripped.startswith("///") else None
        if body:
            if not buf:
                start = lineno
            buf.append(body)
            continue
        if buf:
            out.append((start, " ".join(buf)))
            buf = []
    if buf:
        out.append((start, " ".join(buf)))
    return out


def test_every_second_spelling_claim_in_the_client_note_carries_the_literal():
    """A claim about the alias, in the file that declares the wire name, must
    name the retired spelling — and the retired spelling must be off the wire.

    The pairing is the check. Naming `involuntary_leave_cause` in this file's
    prose is allowed exactly because the route no longer advertises it, and
    both halves are asserted here, so neither can quietly stop being true.

    Scope is `plugin/TransportExit.cs` and stated rather than assumed: it is
    the file whose whole subject is the client side of this wire contract.
    `plugin/ApiClient.cs` uses the word "alias" in several unrelated senses
    (chart series, a public method alias, room-name collisions), so the
    vocabulary has no discriminating power there and a census over it would be
    noise on its first run.

    What this does NOT cover is stated too: a survival claim written without
    any of these words would pass. The words are the ones this project's own
    prose reaches for, and at least one paragraph must match, so the census
    cannot go quietly empty (#342).
    """
    assert CLIENT_CONSTANT_PATH.exists(), (
        f"{CLIENT_CONSTANT_PATH.name} is not on this tree — the client half of "
        "bug #392 is merged into this branch and this census reads its prose")
    paragraphs = _doc_paragraphs(CLIENT_CONSTANT_PATH.read_text(encoding="utf-8"))
    assert len(paragraphs) >= 4, (
        f"only {len(paragraphs)} doc paragraphs parsed out of "
        f"{CLIENT_CONSTANT_PATH.name} — the paragraph reader is not reading it")

    matched = []
    for lineno, text in paragraphs:
        low = text.lower()
        words = [w for w in _SECOND_SPELLING_WORDS if w in low]
        if not words:
            continue
        matched.append((lineno, words))
        assert _RETIRED_CAPABILITY_SPELLING in text, (
            f"{CLIENT_CONSTANT_PATH.name}, doc paragraph at line {lineno}, "
            f"talks about a second spelling ({words}) without naming it. A "
            "claim about the alias that carries no literal is invisible to a "
            "literal sweep, which is how a sentence saying the alias was still "
            "alive outlived the alias: " + text[:160])

    assert matched, (
        f"no doc paragraph in {CLIENT_CONSTANT_PATH.name} mentions a second "
        "spelling at all — this census has nothing to be about, and a check "
        "with no subject passes for the wrong reason (#342)")

    # The other half of the pairing: the spelling that prose may name is the
    # one the route does not advertise. Asserted against the live payload, with
    # the canonical key as the control so an empty payload cannot satisfy it.
    payload = asyncio.run(main.get_mod_version())
    assert _RETIRED_CAPABILITY_SPELLING not in payload, (
        f"{CLIENT_CONSTANT_PATH.name} names {_RETIRED_CAPABILITY_SPELLING!r} as "
        "retired while the route still advertises it; keys advertised: "
        f"{sorted(payload)}")
    assert payload[main._INVOLUNTARY_CAUSE_CAPABILITY_FIELD] is True


def test_the_capability_can_go_false(monkeypatch):
    """The negative control that makes the flag a CHECK rather than a decoration.

    A hardcoded `True` advertises the capability on a box that lost it. Empty
    the vocabulary and the advertisement must follow — which is only possible
    because the value is derived from the same set the handlers read.
    """
    field = main._INVOLUNTARY_CAUSE_CAPABILITY_FIELD
    monkeypatch.setattr(main, "_INVOLUNTARY_EXIT_CAUSES", frozenset())
    assert asyncio.run(main.get_mod_version())[field] is False

    # And a vocabulary where the involuntary tag is NOT in-room — the shape
    # that would un-veto dissolution — must also refuse to advertise.
    monkeypatch.setattr(main, "_INVOLUNTARY_EXIT_CAUSES", frozenset({"not_in_room"}))
    assert asyncio.run(main.get_mod_version())[field] is False


def test_mod_version_stays_outside_the_version_gate():
    """The capability is useless if the client cannot read it before it has
    proved its version — the route must stay on the bypass list."""
    assert "/api/v1/mod-version" in main._VERSION_GATE_BYPASS


# ── (5) what may be STORED (lens find 7) ─────────────────────────────────

@pytest.mark.parametrize("cause", sorted(main._IN_ROOM_EXIT_CAUSES))
def test_the_vocabulary_is_storable(cause):
    """Both in-room tags, not just the involuntary one. A recorded
    `in_room_exit` occupies the slot first-attestation-wins protects, so a
    seat that has attested a chosen exit cannot follow it with a transport
    claim — narrowing storage to the involuntary tag would have handed that
    slot to the later claim (#283)."""
    assert main._persistable_exit_cause(cause) == cause


@pytest.mark.parametrize("cause", ["", None, "fresh_cancel", "whatever_16ch",
                                   "in_room_exit ", "IN_ROOM_EXIT", "{}"])
def test_everything_outside_the_vocabulary_stores_nothing(cause):
    """The route's `max_length=16` was the only filter, which made the column
    a client-writable free-text map keyed by player id while the migration
    described its values as the wire vocabulary. Anything unrecognised now
    stores nothing, which reads downstream as "no cause recorded" — today's
    behaviour for every client, and the direction that costs only the label."""
    assert main._persistable_exit_cause(cause) == ""


def test_every_cause_writer_binds_the_narrowed_value():
    """The class check (#432): not "the helper exists" but "no writer can
    bind anything else". Counted within the FUNCTION span, and the count is
    asserted — a fourth writer added later without the narrowing reddens
    here rather than quietly storing raw client text.
    """
    fn = _function("ffa_queue_leave")
    binds = [(d.lineno, v) for d in ast.walk(fn) if isinstance(d, ast.Dict)
             for k, v in zip(d.keys, d.values)
             if isinstance(k, ast.Constant) and k.value == "cause"]
    assert len(binds) == 3, f"expected the three departure writers, found {len(binds)}"
    for lineno, value in binds:
        assert isinstance(value, ast.Name) and value.id == "_pcause", (
            f"the cause bind at main.py:{lineno} does not use the narrowed value")


def test_the_writer_detector_can_fail():
    """The negative control for the test above: the walk finds a `cause` bind
    that is NOT the narrowed name, so a green result means agreement and not
    an empty search (#342)."""
    tree = ast.parse("def f():\n    g({'lid': 1, 'cause': cause or ''})\n")
    binds = [v for d in ast.walk(tree) if isinstance(d, ast.Dict)
             for k, v in zip(d.keys, d.values)
             if isinstance(k, ast.Constant) and k.value == "cause"]
    assert len(binds) == 1
    assert not (isinstance(binds[0], ast.Name) and binds[0].id == "_pcause")


# ── (6) the label stays a label (lens find 5; r1 rows B5 / L5 / LOW-1) ───

_LEI = "left_early_involuntary"


def _counted_sources() -> dict[str, str]:
    """Every source the qualifier may appear in: the whole api package, plus
    the bot.

    The first form of this tripwire read `main.py` and nothing else. Both of
    the production renderer branches live in `discord_bot.py`, so the guard
    was blind to the two branches that actually exist and to any third one
    added beside them: it watched one file while claiming a property of the
    system, which is a check that cannot fail in the direction it is quoted
    for (#342). A flag names a line, the defect is a class (#432) — so the
    class here is "every source that can name this column", and the set is
    DISCOVERED rather than listed, so a new api module that starts naming it
    is counted the moment it exists rather than the moment someone remembers
    to add it here.
    """
    backend = MAIN_PATH.parents[1]
    paths = sorted((backend / "api").rglob("*.py")) + [backend / "discord_bot.py"]
    sources: dict[str, str] = {}
    for path in paths:
        assert path.is_file(), f"counted source {path.name} is missing"
        sources[path.relative_to(backend).as_posix()] = path.read_text(encoding="utf-8")
    return sources


def _mentions_qualifier(node: ast.AST) -> bool:
    """The column named anywhere inside `node` — as a dict key or SQL string,
    as an attribute, or as a bare name."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and _LEI in sub.value:
            return True
        if isinstance(sub, ast.Attribute) and sub.attr == _LEI:
            return True
        if isinstance(sub, ast.Name) and sub.id == _LEI:
            return True
    return False


def _is_rendered_text(node: ast.AST) -> bool:
    """True when this branch ARM can only ever become displayed text: a string
    literal, an f-string, or a concatenation of those. An arm that is anything
    else is a value the program goes on to USE."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _is_rendered_text(node.left) and _is_rendered_text(node.right)
    return False


def _qualifier_sites(sources: dict[str, str]) -> dict:
    """Classify every mention of the qualifier in `sources`.

    `lines`     — the census: one row per source line that names the column.
    `decisions` — `if` STATEMENTS whose test reads it, i.e. control flow
                  branching on a client-attested cause.
    `ternaries` — conditional EXPRESSIONS whose test reads it, each carrying
                  whether BOTH arms can only be displayed text.

    The real test and its negative control both go through this one function,
    so a control that passes proves the detector the test uses can see the
    thing it is supposed to see — not that a second, hand-written copy of the
    filter can.
    """
    census: list[tuple[str, int, str]] = []
    decisions: list[tuple[str, int]] = []
    ternaries: list[tuple[str, int, bool]] = []
    for path, src in sorted(sources.items()):
        for lineno, line in enumerate(src.splitlines(), 1):
            if _LEI in line:
                census.append((path, lineno, line.strip()))
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:                       # pragma: no cover
            raise AssertionError(f"{path} does not parse: {exc}") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and _mentions_qualifier(node.test):
                decisions.append((path, node.lineno))
            elif isinstance(node, ast.IfExp) and _mentions_qualifier(node.test):
                ternaries.append((path, node.lineno,
                                  _is_rendered_text(node.body)
                                  and _is_rendered_text(node.orelse)))
    return {"lines": census, "decisions": decisions, "ternaries": ternaries}


def test_the_qualifier_is_read_only_by_renderers():
    """The enumeration this fix rests on, made into a repository-wide tripwire.

    A false cause gains a player nothing on the integrity axis today: the
    column has ONE writer and its readers are projections and renders, so
    nothing cancels a lobby, refunds a wager, completes a series, changes a
    placement, a rating, XP or gold because of it. That is a property of the
    current call sites, not a guarantee of the design — the moment anything
    keys a penalty, a leave-rate or a readmission decision off this column,
    the enumeration stops being true and the cost stops being reputational.

    So the sites are counted across every source that can name the column:
    six, four in the api and two in the bot. A seventh anywhere, an `if`
    statement anywhere, an api-side branch of any shape, or a bot branch
    whose arms are not both display text, reddens this test and forces that
    judgement to be made deliberately rather than inherited.

    The two bot sites are branches ON PURPOSE and are the only ones allowed to
    be: they choose between two rendered words for a departure that is
    reported either way. What distinguishes them from the shape this test
    exists to catch is that both arms are literal text — nothing downstream
    can tell which arm ran except a reader.
    """
    sources = _counted_sources()
    # The discovery itself first: a census over an empty or truncated file set
    # is green for the wrong reason (#342, #304).
    assert "api/main.py" in sources and "discord_bot.py" in sources, sorted(sources)
    assert len(sources) >= 10, f"only {len(sources)} sources discovered: {sorted(sources)}"

    found = _qualifier_sites(sources)

    # ORDER: the SHAPE rules are asserted first and the census last, and that
    # is deliberate. The census counts LINES, so it survives untouched a
    # rewrite that changes an existing site IN PLACE — a projection turned
    # into a ternary is still one line in one file. With the census first,
    # every mutation that ADDS a site stopped there, and the three assertions
    # that carry the actual rule were never the thing that reddened: they were
    # reachable, but no executed control had ever driven them on real sources,
    # and the in-place rewrite is precisely the shape they exist to catch. The
    # rule is that nothing may DECIDE on a client-attested cause (#283), so
    # the rule is checked first and the census is the last word — the tripwire
    # for a site that is genuinely new.

    # No `if` STATEMENT anywhere: that is the shape where something DECIDES on
    # a client-attested cause rather than printing a word for it.
    assert found["decisions"] == [], (
        "control flow branches on the qualifier at "
        + ", ".join(f"{p}:{n}" for p, n in found["decisions"]))

    # The api tests it in no shape at all: it projects and serialises it.
    api_branches = [(p, n) for p, n, _ in found["ternaries"] if p.startswith("api/")]
    assert api_branches == [], (
        "the api branches on the qualifier at "
        + ", ".join(f"{p}:{n}" for p, n in api_branches))

    bot_branches = [t for t in found["ternaries"] if t[0] == "discord_bot.py"]
    for path, lineno, text_only in bot_branches:
        assert text_only, (
            f"{path}:{lineno} branches on the qualifier into something other "
            "than displayed text — the label has started deciding")
    assert len(bot_branches) == 2, (
        "the bot's recorded branches are the /game embed head and the series-log "
        "line. Found: " + ", ".join(f"{p}:{n}" for p, n, _ in bot_branches))

    per_file: dict[str, int] = {}
    for path, _lineno, _text in found["lines"]:
        per_file[path] = per_file.get(path, 0) + 1
    assert per_file == {"api/main.py": 4, "discord_bot.py": 2}, (
        "the recorded sites are: in the api, one SELECT projection and one "
        "render dict for the match-by-code route, the INSERT column list that "
        "writes it, and one render dict for the history route; in the bot, the "
        "two display ternaries. Found:\n  "
        + "\n  ".join(f"{p}:{n}: {t}" for p, n, t in found["lines"]))


def test_the_site_counter_can_fail():
    """The negative control, driven through the SAME classifier the test above
    uses, on synthetic sources that plant each shape it must catch.

    The control this replaces re-implemented the filter inline over a one-line
    probe, so it proved that a hand-written copy of the scan could see an `if`
    — not that the shipped scan could see a renderer branch added outside the
    file it happened to read.
    """
    synthetic = {
        # four api mentions, none of them a branch: the shape that must pass
        "api/main.py": (
            'q = "SELECT fmp.left_early_involuntary FROM t"\n'
            'a = {"left_early_involuntary": bool(r["left_early_involuntary"])}\n'
            'i = "INSERT INTO t (left_early_involuntary) VALUES (:lei)"\n'
        ),
        # a THIRD bot ternary beside the two recorded ones
        "discord_bot.py": (
            'a = " *(disconnected)*" if p.get("left_early_involuntary") else " *(left)*"\n'
            'b = " *(disconnected)*" if p.get("left_early_involuntary") else " *(left)*"\n'
            'c = " *(disconnected)*" if p.get("left_early_involuntary") else " *(left)*"\n'
        ),
        # a renderer branch in an api module that is NOT main.py — the site the
        # main.py-only counter could never have seen
        "api/reports.py": (
            'def render(row):\n'
            '    return "gone" if row["left_early_involuntary"] else "left"\n'
        ),
        # and control flow deciding on the cause, in a third file again
        "api/penalties.py": (
            'def apply(row):\n'
            '    if row["left_early_involuntary"]:\n'
            '        return refund(row)\n'
            '    return None\n'
        ),
    }
    found = _qualifier_sites(synthetic)

    per_file: dict[str, int] = {}
    for path, _lineno, _text in found["lines"]:
        per_file[path] = per_file.get(path, 0) + 1
    assert per_file == {"api/main.py": 3, "api/penalties.py": 1,
                        "api/reports.py": 1, "discord_bot.py": 3}, per_file

    assert found["decisions"] == [("api/penalties.py", 2)], found["decisions"]
    assert len([t for t in found["ternaries"] if t[0] == "discord_bot.py"]) == 3
    assert [(p, n) for p, n, _ in found["ternaries"] if p.startswith("api/")] \
        == [("api/reports.py", 2)]

    # and an arm that is not displayed text is reported as such
    valued = _qualifier_sites(
        {"discord_bot.py": 'v = penalty(p) if p.get("left_early_involuntary") else 0\n'})
    assert valued["ternaries"] and valued["ternaries"][0][2] is False


# ── (7) the client side of the wire, read on this tree (r1 row LOW-3) ────
#
# This section used to hold a traceability DETECTOR. While `TransportExit.cs`
# lived only on the client lane, every mention of it here and in main.py had
# to name that branch within a few lines, or a reader following the citation
# resolved it against this checkout and found nothing. The merge dissolved
# that premise — the file resolves here now — and keeping the detector would
# mean requiring a qualifier that is no longer true.
#
# What replaced it is strictly stronger rather than merely quieter. The
# detector could only tell whether prose happened to name a branch; the checks
# below RESOLVE the file, parse the constant out of it, and compare it with
# the server's. The pin in section (4) does the same for the declaration. A
# file that moves, is renamed, or stops declaring the constant fails them, and
# it fails them by name.


def test_the_client_reads_the_capability_through_that_constant():
    """The declaration is only a contract if the client's probe goes THROUGH
    it. `CapabilityField` pinned in one file and the literal typed again at
    the call site would be the same defect one file over: the cross-file pin
    would guard a name the probe does not actually use, and a rename would
    have to be made in two places with only one of them watched.

    So the reader is required to name the constant, and required not to carry
    the literal itself.
    """
    assert CLIENT_READER_PATH.exists(), (
        f"{CLIENT_READER_PATH.name} is not on this tree — the client's version "
        "check is what consumes the capability this route advertises")
    reader = CLIENT_READER_PATH.read_text(encoding="utf-8")
    assert "TransportExit.CapabilityField" in reader, (
        "the client's version check no longer probes through "
        "TransportExit.CapabilityField — the cross-file pin would then be "
        "guarding a name nothing reads")
    literal = f'"{main._INVOLUNTARY_CAUSE_CAPABILITY_FIELD}"'
    assert literal not in reader, (
        f"the client repeats the wire literal {literal} instead of naming the "
        "constant; the pin reads the declaration, so a second copy here is a "
        "spelling nothing is watching")


def test_the_client_constant_reader_can_fail():
    """The negative control for the extractor the whole pin rests on.

    An extractor that matched nothing and returned a default, or that took the
    first of several declarations, would let
    test_the_capability_field_is_spelled_the_way_the_client_reads_it compare
    the server constant against a value this file invented — green on a tree
    where the two sides disagree.
    """
    one = 'internal const string CapabilityField = "zz_probe_name";'
    assert _client_capability_field(one) == "zz_probe_name"

    with pytest.raises(AssertionError):
        _client_capability_field("// no declaration here at all\n")
    with pytest.raises(AssertionError):
        _client_capability_field(one + "\n" + one)

    # A doc comment that merely QUOTES the name is not a declaration. The
    # client source carries exactly such a line above its constant, so an
    # extractor loose enough to accept prose would find two values in the real
    # file and have to guess between them.
    with pytest.raises(AssertionError):
        _client_capability_field('/// the client read "ffa_involuntary_cause"\n')


# ── (8) the migration is named by the number it actually has (row LOW-4) ─

_MIGRATION_FILES = sorted((MAIN_PATH.parents[1] / "sql").glob("*_ffa_departure_cause.sql"))
_THREE_DIGIT = re.compile(r"(?<!#)\b(3\d\d)\b")
# A 3xx used AS A REFERENCE TO THIS MIGRATION, in the two forms it can take in
# a file that is not the lane's own: the filename form, and prose that names
# the migration by its ROLE and then gives a number.
_MIGRATION_FILENAME_REF = re.compile(r"\b(\d{3})_ffa_departure_cause\b")
_ROLE_WORDS = re.compile(r"departure[-_ ]cause migration", re.I)
# The tokens that make a file this lane's OWN, matched against its PATH and
# never against its text. A shared production module that merely mentions the
# lane is not a lane file: promoting it on a text match would put the strict
# bare-3xx rule over a module carrying a hundred-odd unrelated 3xx numbers
# (bug ids, other lanes' migrations, timeouts), and that check would be noise
# on its first run and would be switched off, which is the same as not having
# it (#342). Files this lane owns carry the lane in their name.
#
# That argument used to be carried by a worked example naming a production
# module that mentioned this lane's client branch in a comment. The merge
# dissolved the branch and deleted the mention, and the example outlived the
# fact it rested on — a comment is a claim, and this one was about another
# file's contents with nothing checking it. What stands here now is computed:
# `test_the_lane_classifier_is_keyed_on_the_path_not_the_text` counts what the
# strict rule would cost over `api/main.py` and reads this module's own
# `is_lane` line, because on today's tree a loosening to a text match would
# change nothing — no backend source outside this lane's paths carries a lane
# token in its text — so the noise would arrive only with the first shared
# module to mention the lane, and a check that cannot fail until then is not a
# check.
_LANE_PATH_TOKENS = ("ffa_departure_cause", "bug392")


def _stale_migration_numbers(src: str, current: str) -> list[tuple[int, str]]:
    """STRICT rule, for this lane's OWN files: every bare 3xx number that is
    not the migration's own.

    `#` -prefixed numbers are learning references and are skipped: `#340` is a
    lesson, `324` is a file on disk. The two live in the same prose, which is
    why the distinction is made here rather than by eye.
    """
    out = []
    for lineno, line in enumerate(src.splitlines(), 1):
        for hit in _THREE_DIGIT.findall(line):
            if hit != current:
                out.append((lineno, hit))
    return out


def _migration_references(src: str, current: str) -> list[tuple[int, str]]:
    """WIDE rule, for every other backend source: a 3xx that is being used as a
    reference to THIS migration and is not its current number.

    The strict rule cannot be applied outside the lane — `main.py` alone
    carries over a hundred lines with a bare 3xx on them (bug numbers, other
    lanes' migrations, timeouts), so a bare-number scan there would be noise
    and would be switched off, which is the same as not having it. Two forms
    are unambiguous instead:

      * the filename form, `326_ffa_departure_cause`, anywhere at all;
      * a line that names the migration by ROLE — "the departure-cause
        migration" — and carries a bare 3xx on the same line.

    The boundary is stated rather than hidden: a line that says only
    "migration 326", with no role words and no stem, names SOME migration and
    this rule does not claim it means this one. Inside the lane's own files
    that case is still caught, by the strict rule above.
    """
    out: list[tuple[int, str]] = []
    for lineno, line in enumerate(src.splitlines(), 1):
        for hit in _MIGRATION_FILENAME_REF.findall(line):
            if hit != current:
                out.append((lineno, hit))
        if _ROLE_WORDS.search(line):
            for hit in _THREE_DIGIT.findall(line):
                if hit != current:
                    out.append((lineno, hit))
    return out


def _backend_sources() -> dict[str, Path]:
    """Every backend source a migration reference can live in: the whole api
    package, the bot, every migration and every test and fixture.

    DISCOVERED, not listed. The check this replaces walked a three-entry list
    written by hand, while its sibling tripwire in this same file was rebuilt
    in the same commit from a listed set to a discovered one for exactly this
    reason (#342/#432): a list is green about the files someone remembered.
    """
    backend = MAIN_PATH.parents[1]
    paths = sorted((backend / "api").rglob("*.py"))
    paths += [backend / "discord_bot.py"]
    for sub in ("sql", "tests"):
        paths += sorted((backend / sub).rglob("*.py"))
        paths += sorted((backend / sub).rglob("*.sql"))
    out: dict[str, Path] = {}
    for path in paths:
        if "__pycache__" in path.parts:
            continue
        assert path.is_file(), f"{path.name} is missing — this scan would prove nothing"
        out[path.relative_to(backend).as_posix()] = path
    return out


def test_no_stale_migration_number_survives_in_this_lane_s_files():
    """The renumber from 326 to 324 left the pg harness's docstring saying it
    runs 326 — so a failure triage would have gone and read a file belonging to
    a different lane. The number is DERIVED from the file on disk, so a second
    renumber cannot strand this check the way it stranded the docstring.

    Two rules over one discovered file set, because the lane's own files and
    everything else can carry different burdens of proof. In a file whose PATH
    names the lane, ANY bare 3xx that is not the current number is stale. In
    every other backend source, only a reference that is unambiguously to THIS
    migration counts — the filename form, or role words plus a number.
    """
    assert len(_MIGRATION_FILES) == 1, (
        f"expected exactly one departure-cause migration, found {_MIGRATION_FILES}")
    current = _MIGRATION_FILES[0].name.split("_", 1)[0]
    assert current.isdigit() and len(current) == 3, _MIGRATION_FILES[0].name

    sources = _backend_sources()
    # The discovery first: a scan over a truncated file set is green for the
    # wrong reason (#342, #304).
    assert "api/main.py" in sources and "discord_bot.py" in sources, sorted(sources)
    assert "sql/" + _MIGRATION_FILES[0].name in sources, sorted(sources)
    assert len(sources) >= 20, f"only {len(sources)} sources discovered"

    # This file is the scanner's own home and carries planted stale numbers in
    # the control below, so scanning it would make the check flag itself
    # forever. The exclusion is asserted to be exactly this one file rather
    # than left as a silent `continue`.
    own = Path(__file__).resolve().relative_to(MAIN_PATH.parents[1]).as_posix()
    assert own in sources, own
    lane, wide, lane_seen = {}, {}, []
    for label, path in sources.items():
        if label == own:
            continue
        text = path.read_text(encoding="utf-8")
        is_lane = any(tok in label for tok in _LANE_PATH_TOKENS)
        if is_lane:
            lane_seen.append(label)
        hits = (_stale_migration_numbers(text, current) if is_lane
                else _migration_references(text, current))
        if hits:
            (lane if is_lane else wide)[label] = hits
    # The strict rule must have had something to be strict about: a
    # classifier that promotes nothing makes the whole scan the wide rule
    # while the docstring above claims otherwise (#342).
    assert len(lane_seen) >= 3, (
        f"only {lane_seen} classified as this lane's own files — the migration, "
        "the pg harness and the fixture schema all carry the lane in their name")
    assert (lane, wide) == ({}, {}), (
        f"these files name a 3xx migration that is not {current} — lane files "
        f"{lane}, other backend sources {wide}. A bare 3xx number in this "
        "lane's files means this migration; a learning reference is written "
        "with a leading '#'; elsewhere, name the migration by its role.")


_IS_LANE_ASSIGNMENT = re.compile(r"^[ \t]*is_lane[ \t]*=[ \t]*(.+)$", re.M)


def test_the_lane_classifier_is_keyed_on_the_path_not_the_text():
    """The premise under `_LANE_PATH_TOKENS`, computed — and the keying, read
    off this module's own source.

    Two assertions, because the design has two halves that fail differently.

    The KEYING is pinned at the source line, which is the only place it can be
    pinned on this tree: no backend source outside this lane's own paths
    carries a lane token in its text today, so swapping `label` for `text`
    would classify exactly the same files and every behavioural check would
    stay green. The loosening becomes visible only when some shared module
    first mentions the lane, which is the moment the noise starts — far too
    late for the check to be the thing that refuses it.

    The PREMISE is the cost that keying avoids: `api/main.py` under the strict
    bare-3xx rule. A floor is asserted rather than the exact count, so an
    unrelated 3xx number arriving in that module cannot redden this test for a
    reason it is not about (#342). Under the rule main.py actually gets — the
    wide one — it must be clean.
    """
    own_src = Path(__file__).read_text(encoding="utf-8")
    assignments = _IS_LANE_ASSIGNMENT.findall(own_src)
    assert len(assignments) == 1, (
        "expected exactly one `is_lane =` line in this module, found "
        f"{len(assignments)}: {assignments}")
    expr = assignments[0]
    assert "_LANE_PATH_TOKENS" in expr, (
        f"the lane classifier no longer consults the lane tokens: {expr!r}")
    assert "label" in expr, (
        f"the lane classifier no longer reads the file's PATH: {expr!r}")
    assert "text" not in expr, (
        "the lane classifier was loosened to match the file's TEXT: "
        f"{expr!r}. That promotes any shared module naming this lane under the "
        "strict bare-3xx rule — see the count asserted below for what that "
        "costs over api/main.py alone.")

    sources = _backend_sources()
    current = _MIGRATION_FILES[0].name.split("_", 1)[0]
    main_label = "api/main.py"
    assert main_label in sources, sorted(sources)
    assert not any(tok in main_label for tok in _LANE_PATH_TOKENS), (
        f"{main_label} is classified as one of this lane's own files")
    main_text = sources[main_label].read_text(encoding="utf-8")
    strict_hits = _stale_migration_numbers(main_text, current)
    wide_hits = _migration_references(main_text, current)
    assert len(strict_hits) >= 100, (
        f"{main_label} yields only {len(strict_hits)} bare 3xx hits under the "
        "strict rule, so the noise argument the comment at _LANE_PATH_TOKENS "
        "makes for keying on the path is no longer true of this tree")
    assert wide_hits == [], (
        f"{main_label} names a 3xx migration that is not {current}: {wide_hits}")


def test_the_migration_number_detector_can_fail():
    """The negative control for BOTH rules: every shape either detector must
    catch is planted, and the two shapes that must NOT be flagged are too."""
    # strict, lane files
    assert _stale_migration_numbers("Run 326 the way psql -f would", "324") == [(1, "326")]
    assert _stale_migration_numbers("honouring the file's own BEGIN (#340)", "324") == []
    assert _stale_migration_numbers("applies 324 statement by statement", "324") == []
    # wide, every other backend source
    assert _migration_references("-- see sql/326_ffa_departure_cause.sql", "324") == [(1, "326")]
    assert _migration_references("# the departure-cause migration, 326", "324") == [(1, "326")]
    assert _migration_references("# predates the departure-cause migration", "324") == []
    assert _migration_references("# see sql/324_ffa_departure_cause.sql", "324") == []
    # the wide rule deliberately does NOT claim a bare number means this
    # migration, and must not start flagging every other lane's file
    assert _migration_references("# region maps (migration 307, Sept 10)", "324") == []


# ── (9) the residual's precondition, pinned (r1 row L6) ──────────────────

def _sql_literals_in(fn_name: str, *must_contain: str) -> list[str]:
    return [n.value for n in ast.walk(_function(fn_name))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and all(m in n.value for m in must_contain)]


_TIME_OR_GAME_BOUND = ("started_at", "ended_at", "game_number", "game_no",
                       "NOW()", "CURRENT_TIMESTAMP", "clock_timestamp")


def _cause_object_spans(statement: str) -> list[str]:
    """The `departure_causes = CASE … END` span of a writer, whitespace
    normalised — the only part of a writer that decides what a stored cause
    carries."""
    flat = " ".join(statement.split())
    return [m.group(0) for m in
            re.finditer(r"departure_causes = CASE .*?END", flat)]


def test_the_cause_carries_no_time_and_the_read_applies_no_game_bound():
    """The scope residual, pinned as the two facts it rests on.

    The cause is recorded per LOBBY — per sitting — while the label it
    produces is stamped per MATCH ROW, and this read applies no time and no
    game bound. It cannot: a match on this tree carries only its lobby, and
    the stored cause is a bare string with no attestation time, so there is
    nothing on either side to bound against. Accepted as a residual rather
    than closed, because closing it needs a per-match game number that another
    lane adds and this tree does not have.

    This test is the residual's tripwire, not its fix. It reddens when EITHER
    fact stops being true — when the read gains a time or game predicate, or
    when the stored value gains a timestamp — and at that moment the residual
    has to be closed properly and struck from the notes instead of being
    inherited by whoever reads them next.

    Integrity bar, unchanged either way: a cause taken from the wrong game of
    the same sitting mislabels the same seat's own row with one public word.
    It cannot move a placement, a rating, gold or XP, and it cannot reach
    another player's row at all — the set is keyed by player id and the label
    is gated on that row's own `left_early`.
    """
    reads = _sql_literals_in("submit_ffa_match", "jsonb_each_text")
    assert len(reads) == 1, f"expected one departure-cause read, found {len(reads)}"
    flat_read = " ".join(reads[0].split())
    present = [t for t in _TIME_OR_GAME_BOUND if t in flat_read]
    assert present == [], (
        f"the cause read now names {present} — it has gained a bound, so the "
        "lobby/match scope residual recorded for this lane is closed and must "
        "be struck from the notes rather than left standing.")

    writers = _sql_literals_in("ffa_queue_leave", "UPDATE ffa_lobbies", "departure_causes")
    assert len(writers) == 3, f"expected the three departure writers, found {len(writers)}"
    for writer in writers:
        spans = _cause_object_spans(writer)
        assert len(spans) == 1, f"expected one departure_causes assignment, found {len(spans)}"
        span = spans[0]
        assert re.search(r"jsonb_build_object\((?:CAST\(:pidt AS text\)|p\.id::text), "
                         r"CAST\(:cause AS text\)\)", span), (
            f"the stored cause is no longer the bare narrowed string: {span}")
        carried = [t for t in _TIME_OR_GAME_BOUND if t in span]
        assert carried == [], (
            f"the stored cause now carries {carried} — the map's value shape has "
            "changed, so the read can be bounded and the residual must be closed.")


def test_the_residual_detector_can_fail():
    """The negative control: a bound and a timestamped value are both seen."""
    bounded = " ".join("""
        SELECT key, value FROM jsonb_each_text(x) WHERE m.game_number = :g
    """.split())
    assert [t for t in _TIME_OR_GAME_BOUND if t in bounded] == ["game_number"]
    stamped = _cause_object_spans(
        "SET departure_causes = CASE WHEN 1=1 THEN d ELSE "
        "jsonb_build_object(CAST(:pidt AS text), NOW()::text) END")
    assert len(stamped) == 1 and "NOW()" in stamped[0]
    assert not re.search(r"jsonb_build_object\(CAST\(:pidt AS text\), "
                         r"CAST\(:cause AS text\)\)", stamped[0])


# ── (10) the alias's removal condition, now met (r1 row B13 / LOW-5) ─────
#
# This section held the check that the transitional alias STATED the condition
# that would remove it — "drop it once both lanes are merged and the client
# literal is read off the merged tree" — because a deviation with no removal
# condition is how a transitional thing becomes permanent.
#
# That condition is met. This branch is the merge, and the literal is read off
# it by test_the_capability_field_is_spelled_the_way_the_client_reads_it, so
# the alias is gone and a check that its promise was well worded has nothing
# left to read. What stands in its place is
# test_the_transitional_alias_is_gone_from_the_wire in section (4), which
# asserts the removal itself rather than the promise of one.
