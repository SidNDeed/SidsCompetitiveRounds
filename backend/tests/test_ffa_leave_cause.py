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
from pathlib import Path

import pytest

import main


MAIN_PATH = (Path(__file__).parents[1] / "api" / "main.py").resolve()
MAIN_SRC = MAIN_PATH.read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SRC)


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

    `_involuntary_departed` is derived once and consumed once. Every load of
    it must fall inside the ffa_match_players INSERT call — so it cannot have
    reached the placement sort, the rating application, the XP/gold award, the
    `unrated` set, or the departure record. The mutation that reddens it is
    adding any second reader; the control is the >= 1 assertion, which reds if
    a later edit deletes the consumer and leaves a dead variable.
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
    """The wire NAME, pinned byte-for-byte. This is the whole of the contract
    the first build of this lane got wrong.

    The server advertised `involuntary_leave_cause`; the client asks for
    `ffa_involuntary_cause` (plugin/TransportExit.cs, `CapabilityField`, read
    into ExtractJsonBool at the startup version check). Both lanes were green
    — each asserted its OWN key — and the gate could never open, so every
    column, writer and renderer this bug added was live and completely inert.
    The only thing that can catch that is a test that states the literal the
    OTHER side reads, which is what this line is. Changing either side's
    spelling without changing the other must redden here.

    A hardcoded literal is normally the shape of a check that cannot fail
    (#342). For a WIRE name it is the opposite: the literal IS the contract,
    it is not derived from anything, and an assertion against the constant
    that feeds the route is the only thing standing between a one-character
    rename and a silent re-run of #438/#443.
    """
    assert main._INVOLUNTARY_CAUSE_CAPABILITY_FIELD == "ffa_involuntary_cause"
    assert main._INVOLUNTARY_CAUSE_CAPABILITY_ALIAS == "involuntary_leave_cause"


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


def test_the_alias_can_never_carry_a_different_value(monkeypatch):
    """Two keys for one boolean is a transitional state, not a second source
    of truth. They are bound from one expression, so they cannot drift — in
    either direction, which is why the false case is asserted too."""
    for vocab, expected in ((main._INVOLUNTARY_EXIT_CAUSES, True),
                            (frozenset(), False)):
        monkeypatch.setattr(main, "_INVOLUNTARY_EXIT_CAUSES", vocab)
        payload = asyncio.run(main.get_mod_version())
        canonical = payload[main._INVOLUNTARY_CAUSE_CAPABILITY_FIELD]
        alias = payload[main._INVOLUNTARY_CAUSE_CAPABILITY_ALIAS]
        assert canonical is expected and alias is expected


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


# ── (6) the label stays a label (lens find 5) ────────────────────────────

_LEI = "left_early_involuntary"


def test_the_qualifier_is_read_only_by_renderers():
    """The enumeration this fix rests on, made into a tripwire.

    A false cause gains a player nothing on the integrity axis today: the
    column has ONE writer and its readers are projections and renders, so
    nothing cancels a lobby, refunds a wager, completes a series, changes a
    placement, a rating, XP or gold because of it. That is a property of the
    current call sites, not a guarantee of the design — the moment anything
    keys a penalty, a leave-rate or a readmission decision off this column,
    the enumeration stops being true and the cost stops being reputational.

    So the sites are counted. A fifth one in main.py reddens this test and
    forces that judgement to be made deliberately rather than inherited.
    """
    lines = [(i + 1, ln.strip()) for i, ln in enumerate(MAIN_SRC.splitlines())
             if _LEI in ln]
    assert len(lines) == 4, (
        "the recorded sites are: one SELECT projection and one render dict for "
        "the match-by-code route, the INSERT column list that writes it, and one "
        "render dict for the history route. Found:\n  "
        + "\n  ".join(f"main.py:{n}: {t}" for n, t in lines))
    # None of them is a branch: the column is projected and serialised, never
    # tested. `if` here would mean something DECIDES on a client-attested cause.
    for n, t in lines:
        assert not t.startswith("if ") and " if " not in t, (
            f"main.py:{n} branches on {_LEI}: {t}")


def test_the_site_counter_can_fail():
    """The negative control: the counter sees a branch when there is one."""
    probe = 'if row["left_early_involuntary"]:\n'
    hits = [ln.strip() for ln in probe.splitlines() if _LEI in ln]
    assert len(hits) == 1 and hits[0].startswith("if ")
