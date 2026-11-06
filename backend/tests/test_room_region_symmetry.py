"""The ranked room's region must not be decided by which client polled first.

`_pick_room_region` takes the REQUESTING player's signals first and both
issuance sites pass them that way, so the old chain
`my_region or opp_region or my_home or opp_home` put the room wherever the
client whose poll triggered issuance happened to be. Polling first correlates
with having the better connection to this API, so the seat that was already
ahead got the region as well.

Review r9 killed the first repair with a HIGH, and the reason is the more
interesting half. The picker validates a region by SHAPE — anything that looks
like a region code is accepted — and nothing checks the choice against the
regions Photon actually offers. Resolving a disagreement with `min()` therefore
lands on a retired region EVERY time when a stale cache names one, where the
old order-dependent chain landed there about half the time: strictly worse.

The tie-break asks which region this process has evidence two players have
actually played in. That is corroboration, not an allowlist — a static list was
refused with a good argument (`hk` and `uae` are in this project's own match
history and the game's own selector does not offer them) — and it only ever
ORDERS candidates already in play, so it cannot reject a region outright: it
breaks a tie between two signals of the same kind, and since 2026-11-05 it is
one of the signs that a cached home region is still in service (the others
are a live snapshot naming the region and a fresh ping map that measured
it), which is what lets a home be read ahead of the live snapshots.

WHERE THAT EVIDENCE COMES FROM has been rewritten twice, and the current answer
is the only one that is not a client's word for it. First it was the join-time
CloudRegion snapshot; then the match report's `region` field. Neither is signed
— the match HMAC covers seven fields and the region is not among them — so
establishing a session proves who is speaking and nothing about the region
named in the sentence. The token is now the region THIS SERVER issued for the
room, read back from `issued_room_regions` by the room id, which the HMAC does
cover. The evidence is therefore "the server sent two players here and a game
from that room was reported and accepted", and it is published only once that
report has committed.

AND WHEN CORROBORATION CANNOT DECIDE, `min(a, b)` settles the LADDER's answer
— code order, chosen because no latency measurement reaches that rung and a
deterministic tie-break is better than one that depends on which seat asked.
It is not a coin flip: with cold corroboration the same pair lands the same
way every time, and because code order correlates with geography it is a
bias (learning #597) that rung 0 exists to correct. A test below pins that the
changelog describes the fallback as the fixed order it is.

What none of this claims: that the chosen region is the BEST one for a
cross-region pair. A home is an untimestamped best-region cache: it places a
player who relocated by where they used to be, and a confirmed home is only
a region still in service. A real measurement exists as rung 0
(`_pick_region_by_pings`): when BOTH seats have sent a ping map no older
than 900 s (180 s until 2026-11-05) it may replace the ladder's answer with
the region that minimises the pair's WORST ping, taken when it beats the
ladder's worst by more than 20 ms and lies within each seat's own bound --
the worst that seat measured among the two seats' homes and the ladder's
answer, plus 20 ms (bounded minimax since 2026-09-09; the earlier "costs
neither seat more than 20 ms over its own baseline" test left every
cross-region pair observed that day on one seat's home, learning #597; the
homes as the references since 2026-11-05, learning #1112). Whenever either
map is absent, stale or malformed (a client without the ping sweep sends
none at all), whenever the two maps share no region, whenever every shared
region lies above a bound, and whenever the gain is inside the margin, the
ladder decides the room by itself, which is why the ladder is what every
test in this file is about. Rung 0 has its own file,
test_queue_region_pings.py.
"""

import ast
import inspect
import itertools
import io
import math
import re
import sys
import tokenize
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import main


MAIN_PY = Path(__file__).resolve().parents[1] / "api" / "main.py"

TOKENS = ["", "us", "eu", "asia"]


@pytest.fixture(autouse=True)
def _empty_map():
    """The corroboration map is process state. Every test starts from empty —
    which is also the state a freshly deployed api is in."""
    saved = dict(main._REGION_SEEN)
    main._REGION_SEEN.clear()
    yield
    main._REGION_SEEN.clear()
    main._REGION_SEEN.update(saved)


def _corroborate(token, players=("76561198000000001", "76561198000000002")):
    for sid in players:
        main._note_region_seen(token, sid)


# ── symmetry ─────────────────────────────────────────────────────────────────

def test_the_pick_does_not_depend_on_which_seat_asked():
    """The property, over every combination of the four signals. The caller's
    argument order is an accident of which poll arrived first."""
    for mr, mh, orr, oh in itertools.product(TOKENS, repeat=4):
        mine = main._pick_room_region(mr, mh, orr, oh, "r")
        theirs = main._pick_room_region(orr, oh, mr, mh, "r")
        assert mine == theirs, f"({mr},{mh}) vs ({orr},{oh}) -> {mine} / {theirs}"


def test_symmetry_holds_when_corroboration_is_in_play():
    """The tie-break reads process state, so it is the rung most able to
    reintroduce an order dependence."""
    _corroborate("eu")
    for mr, mh, orr, oh in itertools.product(TOKENS, repeat=4):
        assert main._pick_room_region(mr, mh, orr, oh, "r") == \
               main._pick_room_region(orr, oh, mr, mh, "r")


def test_two_agreeing_home_regions_still_win_outright():
    """Rule 1, unchanged and the thing that actually serves same-region pairs:
    it beats both live snapshots, which are wrong after casual region churn and
    empty when the client was not connected at join."""
    assert main._pick_room_region("us", "asia", "us", "asia", "r") == "asia"


def test_a_signal_that_is_not_a_region_token_counts_as_absent():
    """It would be handed to both clients to connect to, and there is no
    recovery from a room neither of them can reach."""
    for junk in ("  ", "US-EAST-1", "a", "toolongregion", "eu1!", None):
        assert main._pick_room_region(junk, "", junk, "", "r") == "us"
    assert main._pick_room_region("EU ", "", "", "", "r") == "eu", "case and space are normalised"


def test_no_signal_at_all_is_the_us_default():
    assert main._pick_room_region("", "", "", "", "r") == "us"


def test_one_signal_is_used_whichever_seat_it_came_from():
    assert main._pick_room_region("asia", "", "", "", "r") == "asia"
    assert main._pick_room_region("", "", "asia", "", "r") == "asia"
    assert main._pick_room_region("", "asia", "", "", "r") == "asia"
    assert main._pick_room_region("", "", "", "asia", "r") == "asia"


def test_a_confirmed_home_region_outranks_a_live_snapshot():
    """Reversed on 2026-11-05 (bug 457, learning #1112): a live snapshot is
    where the client was connected at join, which after quick play is
    wherever the vanilla sweep left it. A home that something confirms is
    still in service is read first, a lone one included. Here two reporters
    have been seen on asia and on eu; in the last line the map is empty and a
    live snapshot names the home's own region."""
    _corroborate("asia")
    _corroborate("eu")
    assert main._pick_room_region("us", "asia", "", "eu", "r") == "asia"
    assert main._pick_room_region("us", "", "", "eu", "r") == "eu"
    assert main._pick_room_region("us", "eu", "", "", "r") == "eu"
    main._REGION_SEEN.clear()
    assert main._pick_room_region("us", "us", "asia", "", "r") == "us"
    assert main._pick_room_region("asia", "us", "us", "", "r") == "us"


def test_a_home_region_nothing_confirms_ranks_below_a_live_snapshot():
    """A home token is an untimestamped cache and can name a region since
    retired; a room issued there is one neither client can reach. On an empty
    corroboration map, with no ping map and no snapshot naming it, nothing
    says the region is still in service, so the live snapshots are read
    first, as they were before 2026-11-05. The home is still a candidate: it
    decides when there is no snapshot, and two homes that agree win
    outright."""
    assert main._pick_room_region("us", "asia", "", "eu", "r") == "us"
    assert main._pick_room_region("us", "", "", "eu", "r") == "us"
    assert main._pick_room_region("us", "", "eu", "", "r") == "eu"
    assert main._pick_room_region("", "asia", "", "eu", "r") == "asia"
    assert main._pick_room_region("us", "asia", "", "asia", "r") == "asia"


def test_a_home_both_live_snapshots_name_is_read_before_the_other_home():
    """Both clients were connected to one region at join and one of them
    calls it home: that region, ahead of the other seat's home even when
    that one is confirmed and would win the tie between the two (here two
    reporters have been seen on eu and none on asia). The ladder answered
    this shape the same way before 2026-11-05, when the snapshots were read
    before any home that did not agree. The controls keep the rung narrow:
    one snapshot alone (either seat's), two snapshots that differ, and two
    that agree on a region NEITHER seat calls home all leave the confirmed
    home first."""
    _corroborate("eu")
    assert main._pick_room_region("asia", "eu", "asia", "asia", "r") == "asia"
    assert main._pick_room_region("asia", "asia", "asia", "eu", "r") == "asia"
    assert main._pick_room_region("asia", "eu", "", "asia", "r") == "eu"
    assert main._pick_room_region("", "eu", "asia", "asia", "r") == "eu"
    assert main._pick_room_region("asia", "eu", "us", "asia", "r") == "eu"
    assert main._pick_room_region("us", "eu", "us", "asia", "r") == "eu"


# ── corroboration ────────────────────────────────────────────────────────────

def test_a_disagreement_goes_to_the_region_that_has_been_seen_live():
    """The r9 HIGH, answered. `min()` would say "asia" both times; a stale
    cache naming a region nobody can reach would win every single pairing."""
    _corroborate("us")
    assert main._pick_room_region("", "asia", "", "us", "r") == "us"
    assert main._pick_room_region("", "us", "", "asia", "r") == "us"


def test_with_neither_side_corroborated_the_tie_is_still_stable():
    """An empty map is a freshly deployed api, and it must behave exactly as
    it did before corroboration existed rather than inventing an answer."""
    assert main._pick_room_region("", "asia", "", "us", "r") == "asia"
    assert main._pick_room_region("", "us", "", "asia", "r") == "asia"


def test_with_both_sides_corroborated_the_tie_is_still_stable():
    _corroborate("us")
    _corroborate("asia")
    assert main._pick_room_region("", "asia", "", "us", "r") == "asia"


def test_corroboration_never_rejects_a_region_it_only_orders_candidates():
    """The bound on what this mechanism can do, in both of its uses (the
    tie-break, and confirming a home). A region nobody has been seen in is
    still used when it is the only signal — otherwise a cold process would
    move every pair to the default."""
    _corroborate("us")
    assert main._pick_room_region("", "asia", "", "", "r") == "asia"
    assert main._pick_room_region("asia", "", "", "", "r") == "asia"
    assert main._pick_room_region("asia", "", "asia", "", "r") == "asia"


def test_one_client_cannot_corroborate_a_region_of_its_own_invention():
    """The live token is client-supplied. A sighting counts only once it has
    come from more than one distinct player."""
    main._note_region_seen("zz", "76561198000000001")
    main._note_region_seen("zz", "76561198000000001")
    assert not main._region_corroborated("zz")
    assert main._pick_room_region("", "asia", "", "zz", "r") == "asia", (
        "one player's word moved the tie-break"
    )
    main._note_region_seen("zz", "76561198000000002")
    assert main._region_corroborated("zz")


def test_a_home_region_cannot_corroborate_itself():
    """The map is fed from the live snapshot only. If a cached home value
    counted as a sighting, two stale caches naming a retired region would
    corroborate each other — which is exactly the case this exists for."""
    main._pick_room_region("", "asia", "", "asia", "r")
    assert main._REGION_SEEN == {}, "the picker recorded a sighting"
    picker = inspect.getsource(main._pick_room_region)
    assert "_note_region_seen" not in picker, (
        "issuance must not refresh a token's timestamp: the region the picker "
        "itself chose would then look recent forever and could never age out"
    )


def _age(token, seconds, only=None):
    """Push a token's reporters back in time. `only` ages one of them, which is
    how the per-reporter clock is separated from a token-wide one."""
    ids = main._REGION_SEEN[token]
    for rid in list(ids):
        if only is None or rid == only:
            ids[rid] = ids[rid] - seconds


def test_a_sighting_ages_out():
    _corroborate("us")
    assert main._region_corroborated("us")
    _age("us", main._REGION_SEEN_TTL_SECONDS + 1)
    assert not main._region_corroborated("us")
    # ...and a fresh sighting starts the player count over, so a region kept
    # alive by one straggler does not inherit an old quorum.
    main._note_region_seen("us", "76561198000000009")
    assert not main._region_corroborated("us")


def test_one_reporter_cannot_keep_anothers_stale_sighting_alive():
    """r11 HIGH. With one last-seen stamp per TOKEN, the reporter who queues
    from a region every day refreshes it, and the whole entry — including a
    second player's year-old sighting — stays inside the TTL forever. The map
    would then answer "two players recently" on the strength of one. Each
    reporter's sighting has to expire on its own schedule."""
    a, b = "76561198000000001", "76561198000000002"
    main._note_region_seen("eu", a)
    main._note_region_seen("eu", b)
    assert main._region_corroborated("eu")

    # b stops playing there; a keeps queueing from it.
    _age("eu", main._REGION_SEEN_TTL_SECONDS + 1, only=b)
    main._note_region_seen("eu", a)
    assert not main._region_corroborated("eu"), (
        "one active reporter preserved another's expired sighting"
    )
    # the expired reporter is dropped rather than kept as a dead entry
    assert b not in main._REGION_SEEN["eu"]

    # and b coming back restores the quorum, since this is a freshness rule
    # rather than a one-way retirement
    main._note_region_seen("eu", b)
    assert main._region_corroborated("eu")


def test_a_tokens_reporters_are_bounded_by_dropping_the_oldest():
    """A fixed first-N would let a region's original reporters hold its quorum
    open long after they stopped playing there — the same defect as the shared
    clock, one level down."""
    cap = main._REGION_SEEN_IDS_PER_TOKEN
    for i in range(cap):
        main._note_region_seen("us", "7656119800000%04d" % i)
    _age("us", 60.0)
    newcomer = "76561198000009999"
    main._note_region_seen("us", newcomer)
    ids = main._REGION_SEEN["us"]
    assert len(ids) == cap, "the per-token reporter set is not bounded"
    assert newcomer in ids, "the newest reporter was refused rather than admitted"
    assert "76561198000000000" not in ids, "the oldest reporter was kept"


def test_the_map_is_bounded_and_evicts_the_oldest():
    """This test used to feed tokens with digits in them — "r000", "r001" — and
    the token regex is letters only, so every one was rejected, the map was
    EMPTY at the assertion, and `len({}) <= 64` was true no matter what the
    eviction did. Deleting the whole eviction block left it green. It now feeds
    tokens the regex accepts and asserts the mechanism rather than the absence
    of growth."""
    tokens = [chr(97 + i // 26) + chr(97 + i % 26)
              for i in range(main._REGION_SEEN_MAX_TOKENS + 20)]
    assert len(set(tokens)) == len(tokens)
    for token in tokens:
        assert main._region_token(token) == token, "the fixture must feed real tokens"
        main._note_region_seen(token, "76561198000000001")
    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS, (
        "the map neither grew past its bound nor emptied itself"
    )
    assert tokens[0] not in main._REGION_SEEN, "the oldest sighting survived eviction"
    assert tokens[-1] in main._REGION_SEEN, "the newest sighting was evicted"


def test_eviction_is_by_last_seen_not_by_first_seen():
    """A region still in use must not be evicted ahead of one nobody has
    connected to since. The two ages are set explicitly rather than left to two
    monotonic reads a microsecond apart, and exactly one eviction is forced —
    filling past the cap evicts BOTH tokens under comparison and proves
    nothing."""
    stale, in_use = "aa", "ab"
    # `in_use` is inserted FIRST and `stale` second, so insertion order and
    # last-seen order disagree — otherwise the two orderings evict the same
    # token and the test cannot tell which rule the code is following.
    main._note_region_seen(in_use, "76561198000000001")
    main._note_region_seen(stale, "76561198000000001")
    _age(stale, 3600.0)

    # Cap minus one more tokens, so the map lands exactly one over its bound.
    fillers = [chr(97 + i // 26) + chr(97 + i % 26) + "z"
               for i in range(main._REGION_SEEN_MAX_TOKENS - 1)]
    for token in fillers:
        main._note_region_seen(token, "76561198000000003")

    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS
    assert stale not in main._REGION_SEEN, "the least recently seen token survived"
    assert in_use in main._REGION_SEEN, "a token seen moments ago was evicted"


def test_eviction_drops_the_unevidenced_before_the_corroborated():
    """Ranking purely by age lets any stream of new tokens push out the
    corroborated ones, so a full map of regions people actually play in could be
    turned over by regions nobody has connected to. Evidence ranks above age."""
    real = "eu"
    main._note_region_seen(real, "76561198000000001")
    main._note_region_seen(real, "76561198000000002")
    assert main._region_corroborated(real)
    # ...and make it the OLDEST thing in the map, so age alone would evict it
    _age(real, 3600.0)

    fillers = [chr(97 + i // 26) + chr(97 + i % 26) + "z"
               for i in range(main._REGION_SEEN_MAX_TOKENS + 5)]
    for token in fillers:
        main._note_region_seen(token, "76561198000000003")

    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS
    assert real in main._REGION_SEEN, (
        "the oldest token was evicted although it was the only corroborated one"
    )


# ── the census of the pick's reading (ruling RP-5 (3)(a)) ────────────────────
#
# A pick takes ONE reading of the monotonic clock and hands it on to every
# question it asks of the corroboration map. The cases further down ask that
# at chosen readings, through the paths their shapes take. The census asks it
# of the syntax tree of the functions that pass the reading on, whatever the
# reading and whichever path: it reads the source it is handed, so the planted
# sources of test_the_census_refuses_each_planted_source are read by the same
# code as main's own.
#
# The callees that may be handed the reading, each with the parameter that
# receives it. Where that argument sits in a call is read from the callee's
# own signature. A callee that is not on this list and is handed the reading
# is refused by the census until it is added here.
_READING_CALLEES = {
    "_region_home_confirmed": "mono",
    "_region_agreed": "now",
    "_region_corroborated": "now",
}
_LEAF = "_region_corroborated"
# The functions that pass the reading on: the name the reading has in each,
# how it may be bound there, and the callees it may be handed to there.
# "clock": exactly once, a statement of the body itself (not inside a branch
# or a loop) `<name> = time.monotonic()`. "fallback": at most once,
# `if <name> is None: <name> = time.monotonic()`. "none": never.
_CENSUS = {
    "_pick_room_region": ("mono", "clock", tuple(_READING_CALLEES)),
    "_region_home_confirmed": ("mono", "none", (_LEAF,)),
    "_region_agreed": ("now", "fallback", (_LEAF,)),
}
# What the census refuses, one rule per word. test_the_census_refuses_each_planted_source
# has, for each rule, a planted source that only that rule refuses.
_RULES = ("binding", "use", "argument", "alias", "nested")
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
                  ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _is_clock_read(node):
    """`node` is `time.monotonic()`, with no argument."""
    return (isinstance(node, ast.Call) and not node.args and not node.keywords
            and isinstance(node.func, ast.Attribute) and node.func.attr == "monotonic"
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "time")


def _reads_the_clock_into(stmt, name):
    """`stmt` is `<name> = time.monotonic()` and nothing else."""
    return (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == name
            and _is_clock_read(stmt.value))


def _is_none_test(test, name):
    """`test` is `<name> is None`."""
    return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id == name
            and len(test.ops) == 1 and isinstance(test.ops[0], ast.Is) and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant) and test.comparators[0].value is None)


def _is_fallback(stmt, name):
    """`stmt` is `if <name> is None: <name> = time.monotonic()` and nothing else."""
    return (isinstance(stmt, ast.If) and not stmt.orelse and len(stmt.body) == 1
            and _is_none_test(stmt.test, name) and _reads_the_clock_into(stmt.body[0], name))


def _binders(fn, name):
    """Every node inside `fn` that binds `name`, in any form Python has,
    other than `fn`'s own parameters."""
    a = fn.args
    own = {p for p in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg] if p is not None}
    found = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            hit = node.id == name and not isinstance(node.ctx, ast.Load)   # every assignment form, del
        elif isinstance(node, ast.arg):
            hit = node.arg == name and node not in own                      # a nested function's parameter
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            hit = node is not fn and node.name == name
        elif isinstance(node, ast.alias):
            hit = (node.asname or node.name.split(".")[0]) == name
        elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
            hit = node.name == name
        elif isinstance(node, ast.MatchMapping):
            hit = node.rest == name
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            hit = name in node.names
        else:
            hit = False
        if hit:
            found.append(node)
    return found


def _reading_argument(call):
    """What a call to a callee of _READING_CALLEES passes for the reading: an
    expression node, or None where the call leaves it out or passes a starred
    or ** argument, from which the census cannot tell what it passes."""
    callee = call.func.id
    param = _READING_CALLEES[callee]
    position = list(inspect.signature(getattr(main, callee)).parameters).index(param)
    if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
        return None
    if len(call.args) > position:
        return call.args[position]
    return next((k.value for k in call.keywords if k.arg == param), None)


def _census(source, first_line=1):
    """The census of the one function `source` defines: (refusals, sites).
    A refusal is (rule, line, the code refused); a site is (the function, the
    callee, line, column) of a call to a callee this function may hand the
    reading to. Lines are main.py's when `first_line` is the line on which the
    source starts there."""
    fn = ast.parse(source).body[0]
    parents = {child: node for node in ast.walk(fn) for child in ast.iter_child_nodes(node)}
    refusals, sites = [], []

    def refuse(rule, node):
        refusals.append((rule, node.lineno + first_line - 1, ast.unparse(node) if isinstance(node, ast.AST) else ""))

    if fn.name == _LEAF:
        return _census_of_the_leaf(fn, parents, refuse), sites
    reading, binding, callees = _CENSUS[fn.name]

    # binding: the one binding the function is allowed, and no other
    if binding == "clock":
        allowed = [s.targets[0] for s in fn.body if _reads_the_clock_into(s, reading)][:1]
        if not allowed:
            refuse("binding", fn)
    elif binding == "fallback":
        allowed = [s.body[0].targets[0] for s in ast.walk(fn) if _is_fallback(s, reading)][:1]
    else:
        allowed = []
    for node in _binders(fn, reading):
        if node not in allowed:
            refuse("binding", node)
    none_tests = {parents[parents[t]].test.left for t in allowed if binding == "fallback"}

    # argument: every call to a callee of the list hands it the bare name
    handed = set()
    for call in ast.walk(fn):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in _READING_CALLEES):
            continue
        arg = _reading_argument(call)
        if not (isinstance(arg, ast.Name) and arg.id == reading):
            refuse("argument", call)
        elif call.func.id in callees:
            handed.add(arg)
        if call.func.id in callees:
            sites.append((fn.name, call.func.id, call.lineno + first_line - 1, call.col_offset))

    # use: every other mention of the name is that argument, or the fallback's test
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id == reading and isinstance(node.ctx, ast.Load):
            if node not in handed and node not in none_tests:
                refuse("use", node)

    # alias: a callee of the list is named only to be called, by its own name
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id in _READING_CALLEES:
            parent = parents.get(node)
            if not (isinstance(parent, ast.Call) and parent.func is node):
                refuse("alias", node)
        elif isinstance(node, ast.Attribute) and node.attr in _READING_CALLEES:
            refuse("alias", node)

    # nested: no nested function, lambda, class or comprehension mentions it
    for node in ast.walk(fn):
        if node is not fn and isinstance(node, _NESTED_SCOPES):
            if any(isinstance(n, ast.Name) and n.id == reading for n in ast.walk(node)):
                refuse("nested", node)
    return refusals, sites


def _census_of_the_leaf(fn, parents, refuse):
    """Placeholder until the leaf's own rules exist: the leaf is not one of
    the functions that pass the reading on."""
    raise AssertionError("no census of the leaf yet")


def _source_of(name):
    """main.py's source of function `name` and the line it starts on."""
    lines, first = inspect.getsourcelines(getattr(main, name))
    return "".join(lines), first


def _census_of(name):
    return _census(*_source_of(name))


def test_the_census_of_mains_own_functions_refuses_nothing():
    """The pick binds its reading once, from the clock, and hands that name,
    and nothing made from it, to every call of the homes' confirmation, of the
    weighing and of the leaf; the two functions between hand their parameter
    on to the leaf in the same way, the weighing binding it only when none was
    handed in. Each function hands it to every callee it is allowed to."""
    pairs = set()
    for name in _CENSUS:
        refusals, sites = _census_of(name)
        assert refusals == [], (name, refusals)
        pairs |= {(fn, callee) for fn, callee, _, _ in sites}
    assert pairs == {(name, callee) for name, (_, _, callees) in _CENSUS.items() for callee in callees}
    for callee, param in _READING_CALLEES.items():
        assert param in inspect.signature(getattr(main, callee)).parameters, (callee, param)


def test_both_candidates_are_judged_against_one_clock_reading():
    """Two separate time.monotonic() calls put the TTL boundary between the two
    comparisons, so at the moment both sightings expire, whichever is read first
    can still be live and win a tie it should not have been in. Read by the
    census: _region_agreed binds its reading at most once, only where none was
    handed in, and hands that name to both of its questions to the leaf."""
    refusals, sites = _census_of("_region_agreed")
    assert refusals == []
    assert [callee for _, callee, _, _ in sites] == [_LEAF, _LEAF]


_BIND = "    mono = time.monotonic()\n"
_RETURN = "    return chosen\n"
_THIRD = "_region_agreed(mh, oh, mono) or"
_SECOND = "_region_agreed(mr, orr, mono)"
_SEEN = "_region_corroborated(chosen, mono)"
_HOME_LEAF = "    return _region_corroborated(home, mono)\n"
_AGREED_LEAF = "        ca, cb = _region_corroborated(a, now), _region_corroborated(b, now)\n"

# (what was planted, the function, its edits as (old, new), the rules that refuse it)
_PLANTED = [
    ("the rounding at the third weighing of Codex round REGION-R4", "_pick_room_region",
     [(_THIRD, "_region_agreed(mh, oh, round(mono - 0.5) + 0.5) or")], {"argument", "use"}),
    ("a second reading", "_pick_room_region", [(_BIND, _BIND + _BIND)], {"binding"}),
    ("the reading moved in place", "_pick_room_region", [(_BIND, _BIND + "    mono += 0.5\n")], {"binding"}),
    ("the reading rebound inside an argument", "_pick_room_region",
     [(_SECOND, "_region_agreed(mr, orr, (mono := mono + 0.5))")], {"binding", "use", "argument"}),
    ("the reading deleted", "_pick_room_region", [(_RETURN, "    del mono\n" + _RETURN)], {"binding"}),
    ("the reading taken from another clock", "_pick_room_region",
     [(_BIND, "    mono = time.time()\n")], {"binding"}),
    ("the reading rounded where it is taken", "_pick_room_region",
     [(_BIND, "    mono = round(time.monotonic())\n")], {"binding"}),
    ("the reading taken inside a branch", "_pick_room_region",
     [(_BIND, "    if True:\n        mono = time.monotonic()\n")], {"binding"}),
    ("a weighing that leaves the reading out", "_pick_room_region",
     [(_SECOND, "_region_agreed(mr, orr)")], {"argument"}),
    ("the wall-clock instant handed in its place", "_pick_room_region",
     [(_SECOND, "_region_agreed(mr, orr, now)")], {"argument"}),
    ("the reading handed to the weighing by keyword", "_pick_room_region",
     [(_SECOND, "_region_agreed(mr, orr, now=mono)")], set()),
    ("the reading handed to a home by keyword", "_pick_room_region",
     [("_region_home_confirmed(mh, lives, maps, mono)", "_region_home_confirmed(mh, lives, maps, mono=mono)")], set()),
    ("a weighing called through another name", "_pick_room_region",
     [(_BIND, _BIND + "    weigh = _region_agreed\n"), (_SECOND, "weigh(mr, orr, mono)")], {"alias", "use"}),
    ("a weighing called through the module", "_pick_room_region",
     [(_SECOND, "sys.modules[__name__]._region_agreed(mr, orr, mono)")], {"alias", "use"}),
    ("a weighing kept under another name", "_pick_room_region",
     [(_BIND, _BIND + "    weigh = _region_agreed\n")], {"alias"}),
    ("a lambda that mentions the reading", "_pick_room_region",
     [(_THIRD, "(lambda: _region_agreed(mh, oh, mono))() or")], {"nested"}),
    ("a nested function that mentions the reading", "_pick_room_region",
     [(_BIND, _BIND + "    def later():\n        return mono\n")], {"nested", "use"}),
    ("a comprehension that mentions the reading", "_pick_room_region",
     [(_SEEN, "all(_region_corroborated(c, mono) for c in (chosen,))")], {"nested"}),
    ("the reading handed to a callee that is not on the list", "_pick_room_region",
     [(_SEEN, "_region_seen_at(chosen, mono)")], {"use"}),
    ("the reading printed", "_pick_room_region", [(_RETURN, "    print(mono)\n" + _RETURN)], {"use"}),
    ("a home's confirmation hands on an expression", "_region_home_confirmed",
     [(_HOME_LEAF, "    return _region_corroborated(home, mono + 0.0)\n")], {"argument", "use"}),
    ("a home's confirmation leaves the reading out", "_region_home_confirmed",
     [(_HOME_LEAF, "    return _region_corroborated(home)\n")], {"argument"}),
    ("a home's confirmation takes a reading of its own", "_region_home_confirmed",
     [("    if not home:\n", "    mono = time.monotonic()\n    if not home:\n")], {"binding"}),
    ("a home's confirmation hands the reading to the weighing", "_region_home_confirmed",
     [(_HOME_LEAF, "    return _region_agreed(home, home, mono)\n")], {"use"}),
    ("a second reading in the weighing", "_region_agreed",
     [(_AGREED_LEAF, "        now = time.monotonic()\n" + _AGREED_LEAF)], {"binding"}),
    ("the weighing asks about its second candidate at an expression", "_region_agreed",
     [("_region_corroborated(b, now)", "_region_corroborated(b, float(now))")], {"argument", "use"}),
    ("the weighing's own reading taken on any false value", "_region_agreed",
     [("        if now is None:\n", "        if not now:\n")], {"binding", "use"}),
    ("the weighing's own reading taken from another clock", "_region_agreed",
     [("            now = time.monotonic()\n", "            now = time.perf_counter()\n")], {"binding", "use"}),
]


def test_the_census_refuses_each_planted_source():
    """Each planted source is main's own function with the edits written
    beside it, and the census refuses it by exactly the rules written there:
    none for the two that hand the reading by keyword, which is the same
    reading. Every rule is the only one to refuse at least one of them, so a
    rule that stopped refusing would leave a source it alone refuses
    accepted."""
    for label, name, edits, refused in _PLANTED:
        source, first = _source_of(name)
        for old, new in edits:
            assert source.count(old) == 1, (label, old)
            source = source.replace(old, new)
        got = {rule for rule, _, _ in _census(source, first)[0]}
        assert got == refused, (label, got)
    alone = {next(iter(refused)) for _, _, _, refused in _PLANTED if len(refused) == 1}
    assert alone == set(_RULES), set(_RULES) - alone


class _CountingClock:
    """Stands in for main's `time` module. monotonic() answers `start`, then
    one second more on every read, and counts its reads; `next` is what the
    next read will answer. Everything else is the real module's."""

    def __init__(self, real, start):
        self._real, self.next, self.reads = real, float(start), 0

    def monotonic(self):
        self.reads += 1
        value, self.next = self.next, self.next + 1.0
        return value

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture
def clock(monkeypatch):
    stand_in = _CountingClock(main.time, 10 * main._REGION_SEEN_TTL_SECONDS)
    monkeypatch.setattr(main, "time", stand_in)
    return stand_in


def _stamp_last_live(token, clock):
    """Enough reporters for `token`, stamped on the stand-in clock's own
    timeline so that the clock's NEXT reading is the last instant at which
    they are live: one second later the sighting has expired."""
    at = clock.next - main._REGION_SEEN_TTL_SECONDS
    main._REGION_SEEN[token] = {f"7656119800000010{i}": at for i in range(main._REGION_SEEN_MIN_PLAYERS)}


def _pick(capsys, *args, **kwargs):
    got = main._pick_room_region(*args, **kwargs)
    return got, [line for line in capsys.readouterr().out.splitlines() if "[QUEUE-REGION]" in line]


def test_one_pick_reads_the_monotonic_clock_once(clock, capsys):
    """Every question a pick asks of the corroboration map (is this home
    confirmed, which of two different regions has been seen live, was the
    chosen one seen) is asked of ONE instant. A second reading anywhere in
    the pick puts the instant a sighting expires between two of those
    answers. Counted over shapes that reach every rung, with and without
    sightings, with and without fresh maps."""
    shapes = [
        ("", "eu", "", "eu"),            # two homes that agree
        ("ru", "ru", "ru", "us"),        # a home that both snapshots name
        ("ru", "eu", "ru", "us"),        # two homes that differ, two snapshots that agree elsewhere
        ("us", "", "eu", ""),            # two snapshots that differ, no home
        ("", "eu", "", "us"),            # two homes that differ, no snapshot
        ("", "", "", ""),                # no signal at all
    ]
    now = datetime.now(timezone.utc)
    fresh = dict(p1_pings={"eu": 40, "us": 60}, p2_pings={"eu": 70, "us": 30},
                 p1_pings_at=now - timedelta(seconds=30), p2_pings_at=now - timedelta(seconds=30), now=now)
    for shape in shapes:
        for seen in (False, True):
            for kwargs in ({}, fresh):
                main._REGION_SEEN.clear()
                if seen:
                    _stamp_last_live("eu", clock)
                    _stamp_last_live("us", clock)
                before = clock.reads
                main._pick_room_region(*shape, "r", **kwargs)
                assert clock.reads - before == 1, (shape, seen, bool(kwargs), clock.reads - before)
    capsys.readouterr()


def test_both_homes_are_confirmed_against_the_picks_one_reading(clock, capsys):
    """Codex round REGION-R1's scenario. Each home has its reporters, stamped
    so that the pick's reading is the last instant at which they are live;
    the two snapshots name a third region. Both homes are confirmed whichever
    seat asked. A reading per home would confirm only the home that is read
    first, and the room would follow the seat order."""
    answers = []
    for args in (("ru", "eu", "ru", "us"), ("ru", "us", "ru", "eu")):
        _stamp_last_live("eu", clock)
        _stamp_last_live("us", clock)
        got, (first, second) = _pick(capsys, *args, "r")
        answers.append(got)
        assert "home_ok=(y,y)" in second and "seen=y" in second, second
    assert answers == ["eu", "eu"]


def test_two_different_snapshots_are_weighed_at_the_picks_reading(clock, capsys):
    """Two live snapshots that differ and no home: the region seen live wins
    (_region_agreed), and "seen live" is judged at the pick's one reading. A
    reading of its own, one second later on this clock, would find the
    sighting expired and fall back to the fixed order, which names the other
    region."""
    for args in (("us", "", "eu", ""), ("eu", "", "us", "")):
        main._REGION_SEEN.clear()
        _stamp_last_live("us", clock)
        got, (first, second) = _pick(capsys, *args, "r")
        assert got == "us", (args, got)
        assert "seen=y" in second, second


def test_a_reading_that_is_handed_in_is_the_reading_that_is_used(monkeypatch):
    """_region_corroborated, _region_home_confirmed and _region_agreed answer
    against the reading they are handed and take none of their own."""
    class _NoClock:
        def monotonic(self):
            raise AssertionError("a reading was handed in; the clock must not be read")

    ttl = main._REGION_SEEN_TTL_SECONDS
    main._REGION_SEEN["us"] = {f"7656119800000010{i}": 0.0 for i in range(main._REGION_SEEN_MIN_PLAYERS)}
    monkeypatch.setattr(main, "time", _NoClock())
    assert main._region_corroborated("us", ttl) is True
    assert main._region_corroborated("us", ttl + 1) is False
    assert main._region_home_confirmed("us", ("", ""), (None, None), ttl) is True
    assert main._region_home_confirmed("us", ("", ""), (None, None), ttl + 1) is False
    # us is seen at the first reading and wins the disagreement; one second
    # later neither is seen and the fixed order names eu
    assert main._region_agreed("eu", "us", ttl) == "us" == main._region_agreed("us", "eu", ttl)
    assert main._region_agreed("eu", "us", ttl + 1) == "eu" == main._region_agreed("us", "eu", ttl + 1)


class _FixedClock:
    """Stands in for main's `time` module. monotonic() answers `at` on every
    read and counts its reads. Everything else is the real module's."""

    def __init__(self, real, at):
        self._real, self.at, self.reads = real, at, 0

    def monotonic(self):
        self.reads += 1
        return self.at

    def __getattr__(self, name):
        return getattr(self._real, name)


# The instant a sighting expires, asked to the last bit. A sighting stamped
# at `ts` counts while `now - ts <= _REGION_SEEN_TTL_SECONDS`
# (_region_corroborated). Each case below is a stamp and a reading: the float
# before the last instant at which the sighting counts, that instant, and the
# float after it. There are three stamps, A, B and C; what distinguishes them,
# and that the readings are the floats this note says they are, is asserted by
# test_the_cases_around_expiry_are_adjacent_floats_and_exact_ages.
# test_every_listed_moved_or_rounded_reading_gets_a_case_wrong runs the same
# cases with readings that have been moved or rounded, and
# test_the_third_stamp_is_what_catches_a_half_going_to_the_odd_step shows what
# the third stamp is for.
_TTL = main._REGION_SEEN_TTL_SECONDS
_EXPIRES_A = 4 * _TTL + 0.375
_EXPIRES_B = math.nextafter(_EXPIRES_A, -math.inf)
_EXPIRES_C = math.nextafter(_EXPIRES_A, math.inf)


def _around(name, expires):
    """Three cases for a sighting whose last live instant is `expires`: (a
    label, the stamp, the reading, whether the sighting counts at it)."""
    stamp = expires - _TTL
    return [
        (f"{name}-before", stamp, math.nextafter(expires, -math.inf), True),
        (f"{name}-at", stamp, expires, True),
        (f"{name}-after", stamp, math.nextafter(expires, math.inf), False),
    ]


_AROUND_EXPIRY = _around("A", _EXPIRES_A) + _around("B", _EXPIRES_B) + _around("C", _EXPIRES_C)

# (the pick's arguments, the region whose reporters are stamped, what the pick
# says while the sighting is live, what it says once it has expired). Between
# them the shapes put each use of the pick's reading in charge of something
# the test asserts: the confirmation of the first and of the second home, each
# of the three weighings of two different regions, the seen= field.
_FRACTION_SHAPES = [
    # a home that only the sighting confirms (REGION-R2's scenario), and its mirror
    (("eu", "us", "eu", ""), "us", ("us", "seen=y", "home_ok=(y,-)"), ("eu", "seen=n", "home_ok=(n,-)")),
    (("eu", "", "eu", "us"), "us", ("us", "seen=y", "home_ok=(-,y)"), ("eu", "seen=n", "home_ok=(-,n)")),
    # two homes that differ, each confirmed by a live snapshot: the first weighing
    (("eu", "eu", "us", "us"), "us", ("us", "seen=y", "home_ok=(y,y)"), ("eu", "seen=n", "home_ok=(y,y)")),
    (("us", "us", "eu", "eu"), "us", ("us", "seen=y", "home_ok=(y,y)"), ("eu", "seen=n", "home_ok=(y,y)")),
    # two live snapshots that differ and no home: the second weighing
    (("us", "", "eu", ""), "us", ("us", "seen=y", "home_ok=(-,-)"), ("eu", "seen=n", "home_ok=(-,-)")),
    (("eu", "", "us", ""), "us", ("us", "seen=y", "home_ok=(-,-)"), ("eu", "seen=n", "home_ok=(-,-)")),
    # two homes that differ and no snapshot: confirmed while seen, the third weighing after
    (("", "eu", "", "us"), "us", ("us", "seen=y", "home_ok=(n,y)"), ("eu", "seen=n", "home_ok=(n,n)")),
    (("", "us", "", "eu"), "us", ("us", "seen=y", "home_ok=(y,n)"), ("eu", "seen=n", "home_ok=(n,n)")),
    # two homes that agree: the room does not move, the two fields do
    (("", "eu", "", "eu"), "eu", ("eu", "seen=y", "home_ok=(y,y)"), ("eu", "seen=n", "home_ok=(n,n)")),
]


class _Recorder:
    """Installed as the profile function for one pick, it records every call
    of the leaf (_region_corroborated) and of the two functions that hand it
    the reading: (the callee, where it was called from, where that caller was
    called from, what it received for the reading). A place is (function,
    line, column) of the call, read from the calling frame's own instruction.
    It hands every event on to the profile function it replaced."""

    def __init__(self):
        self.codes = {getattr(main, name).__code__: name for name in _READING_CALLEES}
        self.calls = []

    @staticmethod
    def _place(frame):
        if frame is None:
            return None
        line, _, col, _ = list(frame.f_code.co_positions())[frame.f_lasti // 2]
        return frame.f_code.co_name, line, col

    def __call__(self, frame, event, arg):
        name = self.codes.get(frame.f_code) if event == "call" else None
        if name is not None:
            caller = frame.f_back
            self.calls.append((name, self._place(caller), self._place(caller.f_back),
                               frame.f_locals.get(_READING_CALLEES[name])))
        if self.previous is not None:
            self.previous(frame, event, arg)

    def __enter__(self):
        self.previous = sys.getprofile()
        sys.setprofile(self)
        return self

    def __exit__(self, *exc):
        sys.setprofile(self.previous)
        return False


def _same_bits(received, reading):
    """`received` is a float with the bits of `reading`."""
    return type(received) is float and type(reading) is float and received.hex() == reading.hex()


def _wrong(monkeypatch, capsys, case, shape, distort=None, record=None):
    """One pick of `shape`, its sighting stamped as `case` says and the clock
    answering `case`'s reading (what `distort` makes of it, when given).
    Returns what the pick got wrong, an empty list when nothing: the room,
    where it is not the one the shape expects for that case; the count of log
    lines, where it is not two; the second log line, where it lacks a field
    the shape expects; the count of clock reads, where it is not one; every
    call of the leaf that received, for the reading, anything but the one
    value the clock gave, bit for bit (ruling RP-5 (3)(b)). `record`, a list
    when given, gets the pick's recorded calls appended."""
    label, stamp, reading, is_live = case
    args, sighted, live, expired = shape
    main._REGION_SEEN.clear()
    main._REGION_SEEN[sighted] = {
        f"7656119800000010{i}": stamp for i in range(main._REGION_SEEN_MIN_PLAYERS)}
    stand_in = _FixedClock(main.time, reading if distort is None else distort(reading))
    with monkeypatch.context() as patch, _Recorder() as recorder:
        patch.setattr(main, "time", stand_in)
        got, lines = _pick(capsys, *args, "r")
    if record is not None:
        record.append(recorder.calls)
    region, seen, home_ok = live if is_live else expired
    wrong = []
    if got != region:
        wrong.append(("room", got))
    if len(lines) != 2:
        wrong.append(("lines", lines))
    elif f"chosen={region} " not in lines[1] or seen not in lines[1] or home_ok not in lines[1]:
        wrong.append(("line", lines[1]))
    if stand_in.reads != 1:
        wrong.append(("reads", stand_in.reads))
    leaf = [call for call in recorder.calls if call[0] == _LEAF and not _same_bits(call[3], stand_in.at)]
    if leaf:
        wrong.append(("leaf", leaf))
    return wrong


@pytest.mark.parametrize("shape", _FRACTION_SHAPES, ids=[f"shape{n}" for n in range(1, len(_FRACTION_SHAPES) + 1)])
@pytest.mark.parametrize("case", _AROUND_EXPIRY, ids=[case[0] for case in _AROUND_EXPIRY])
def test_a_sighting_expires_at_its_own_instant_and_not_at_a_whole_second(monkeypatch, capsys, case, shape):
    """Nine shapes of a pick, each asked at the float before the last instant
    its sighting counts, at that instant and at the float after it, with three
    stamps: the pick answers as the shape says for a sighting that counts at
    the first two and not at the third, reads the clock once, and hands the
    leaf that one reading, bit for bit, at every call."""
    assert _wrong(monkeypatch, capsys, case, shape) == []


def test_every_site_of_the_census_is_reached_by_the_cases(monkeypatch, capsys):
    """Over the cases around expiry, the places the recorder sees calls come
    from are exactly the census's sites: every call of the leaf in the three
    functions, and every call of the two between in the pick, is reached by
    some case, and no recorded call comes from anywhere else. In one case at
    least the pick enters _region_agreed three times."""
    record = []
    for case in _AROUND_EXPIRY:
        for shape in _FRACTION_SHAPES:
            assert _wrong(monkeypatch, capsys, case, shape, record=record) == [], (case[0], shape[0])
    reached = {call[1] for calls in record for call in calls}
    sites = {(fn, line, col) for name in _CENSUS for fn, _, line, col in _census_of(name)[1]}
    assert reached == sites, (sorted(sites - reached), sorted(reached - sites))
    assert max(sum(1 for call in calls if call[0] == "_region_agreed") for calls in record) == 3


# Codex round REGION-R4's scenario: two us reporters stamped 1814400.5 and the
# clock at 2419200.75, a quarter of a second after their sighting expired,
# asked with the seventh shape (two homes that differ, no snapshot).
_REGION_R4_CASE = ("REGION-R4", 1814400.5, 2419200.75, False)


def _planted_pick(label):
    """The function of _PLANTED's source `label`, compiled from that source
    with main.py's line numbers and run in main's own globals; and the (line,
    column) of each call in it whose reading argument is not a bare name."""
    _, name, edits, _ = next(planted for planted in _PLANTED if planted[0] == label)
    source, first = _source_of(name)
    for old, new in edits:
        source = source.replace(old, new)
    tree = ast.parse(source)
    ast.increment_lineno(tree, first - 1)
    changed = [(c.lineno, c.col_offset) for c in ast.walk(tree)
               if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in _READING_CALLEES
               and not isinstance(_reading_argument(c), ast.Name)]
    namespace = {}
    exec(compile(tree, str(MAIN_PY), "exec"), main.__dict__, namespace)
    return namespace[name], changed


def test_the_leaf_refuses_the_rounding_of_codex_round_region_r4(monkeypatch, capsys):
    """Main's own pick gets nothing wrong in the reviewer's scenario. The pick
    whose third weighing is handed the reading rounded on a grid of whole
    seconds that starts at a half (the first planted source of the census,
    compiled) hands the leaf 2419200.5 where the clock gave 2419200.75, and
    _wrong reports each of those calls, every one from the third weighing."""
    shape = _FRACTION_SHAPES[6]
    assert shape[:2] == (("", "eu", "", "us"), "us")
    assert _wrong(monkeypatch, capsys, _REGION_R4_CASE, shape) == []
    planted, changed = _planted_pick(_PLANTED[0][0])
    assert len(changed) == 1
    with monkeypatch.context() as patch:
        patch.setattr(main, "_pick_room_region", planted)
        wrong = dict(_wrong(monkeypatch, capsys, _REGION_R4_CASE, shape))
    leaf = wrong.get("leaf")
    assert leaf, wrong
    assert {call[2][1:] for call in leaf} == set(changed), leaf
    assert {call[3] for call in leaf} == {2419200.5}, leaf


def test_a_helper_that_reads_the_clock_itself_reads_it_to_the_fraction(monkeypatch):
    """Called without a reading, _region_corroborated and _region_agreed take
    one of their own, once, and judge it as it was read: asked with the same
    stamps and readings as the picks above."""
    for label, stamp, reading, is_live in _AROUND_EXPIRY:
        main._REGION_SEEN.clear()
        main._REGION_SEEN["us"] = {
            f"7656119800000010{i}": stamp for i in range(main._REGION_SEEN_MIN_PLAYERS)}
        stand_in = _FixedClock(main.time, reading)
        with monkeypatch.context() as patch:
            patch.setattr(main, "time", stand_in)
            assert main._region_corroborated("us") is is_live, label
            assert stand_in.reads == 1, label
            want = "us" if is_live else "eu"
            assert main._region_agreed("eu", "us") == want == main._region_agreed("us", "eu"), label
            assert stand_in.reads == 3, label


def test_the_cases_around_expiry_are_adjacent_floats_and_exact_ages():
    """What the cases rest on. Stamp A's last live instant is a whole number
    of eighths of a second, of milliseconds, of microseconds and of steps of
    2**-30 s; stamp B's is the float below it and stamp C's the float above
    it. For each stamp the three readings are neighbouring floats one
    last-place unit (2**-31 s) apart, the sighting's age at the middle one is
    the TTL exactly, and at the other two it is the TTL less, and plus, that
    one unit. Two neighbouring floats, A's and C's last live instants, are
    each the reading at which one stamp's sighting last counts and the first
    reading at which another's no longer does."""
    assert all((_EXPIRES_A * per_second).is_integer() for per_second in (8, 1000, 10 ** 6, 2 ** 30))
    assert _EXPIRES_B == math.nextafter(_EXPIRES_A, -math.inf) < _EXPIRES_A
    assert _EXPIRES_C == math.nextafter(_EXPIRES_A, math.inf) > _EXPIRES_A
    unit = 2.0 ** -31
    stamps = (("A", _EXPIRES_A), ("B", _EXPIRES_B), ("C", _EXPIRES_C))
    for name, expires in stamps:
        (_, stamp, before, _), (_, _, at, _), (_, _, after, _) = cases = _around(name, expires)
        assert at == expires and [case[3] for case in cases] == [True, True, False]
        assert math.nextafter(before, math.inf) == at and math.nextafter(at, math.inf) == after
        assert at - before == unit == after - at
        assert (before - stamp, at - stamp, after - stamp) == (_TTL - unit, _TTL, _TTL + unit)
    assert _AROUND_EXPIRY == [case for name, expires in stamps for case in _around(name, expires)]
    last_counts = {reading for label, _, reading, _ in _AROUND_EXPIRY if label.endswith("-at")}
    first_expired = {reading for label, _, reading, _ in _AROUND_EXPIRY if label.endswith("-after")}
    assert last_counts & first_expired == {_EXPIRES_A, _EXPIRES_C}


def _rounded(rounding, per_second):
    """What a reading becomes when `rounding` (math.floor, math.ceil or round)
    puts it on a grid of `per_second` steps to the second."""
    return lambda t: rounding(t * per_second) / per_second


def _half_to_odd(per_second):
    """What a reading becomes on the nearest step of a grid of `per_second`
    steps to the second when a half goes to the odd step (round, which
    _rounded is given for the nearest step, sends a half to the even one)."""
    return lambda t: (round(t * per_second + 1) - 1) / per_second


# (what was done to the reading, the function that does it)
_MOVED_OR_ROUNDED = [
    ("cut down to whole seconds", _rounded(math.floor, 1)),
    ("rounded up to whole seconds", _rounded(math.ceil, 1)),
    ("rounded to the nearest whole second", _rounded(round, 1)),
    ("cut down to milliseconds", _rounded(math.floor, 1000)),
    ("rounded up to milliseconds", _rounded(math.ceil, 1000)),
    ("rounded to the nearest millisecond", _rounded(round, 1000)),
    ("cut down to microseconds", _rounded(math.floor, 10 ** 6)),
    ("rounded up to microseconds", _rounded(math.ceil, 10 ** 6)),
    ("rounded to the nearest microsecond", _rounded(round, 10 ** 6)),
    ("cut down to steps of 2**-30 s", _rounded(math.floor, 2 ** 30)),
    ("rounded up to steps of 2**-30 s", _rounded(math.ceil, 2 ** 30)),
    ("rounded to the nearest step of 2**-30 s", _rounded(round, 2 ** 30)),
    ("rounded to the nearest step of 2**-30 s, a half to the odd step", _half_to_odd(2 ** 30)),
    ("half a second later", lambda t: t + 0.5),
    ("half a second earlier", lambda t: t - 0.5),
    ("a thirty-second of a second later", lambda t: t + 0.03125),
    ("a thirty-second of a second earlier", lambda t: t - 0.03125),
    ("a microsecond later", lambda t: t + 1e-6),
    ("a microsecond earlier", lambda t: t - 1e-6),
    ("one last-place unit later", lambda t: math.nextafter(t, math.inf)),
    ("one last-place unit earlier", lambda t: math.nextafter(t, -math.inf)),
]


def test_every_listed_moved_or_rounded_reading_gets_a_case_wrong(monkeypatch, capsys):
    """With the reading left as it was read, every shape gets every case
    right. With any reading of _MOVED_OR_ROUNDED in its place, every shape
    gets some case wrong."""
    def wrong_cases(shape, distort):
        return [case[0] for case in _AROUND_EXPIRY if _wrong(monkeypatch, capsys, case, shape, distort)]

    for shape in _FRACTION_SHAPES:
        assert wrong_cases(shape, None) == [], shape[0]
        for done, distort in _MOVED_OR_ROUNDED:
            assert wrong_cases(shape, distort), (done, shape[0])


def test_the_third_stamp_is_what_catches_a_half_going_to_the_odd_step(monkeypatch, capsys):
    """Why there are three stamps. The reading put on the nearest step of
    2**-30 s with a half going to the odd step gets every case of stamps A
    and B right, for every shape, and one case of stamp C wrong."""
    distort = _half_to_odd(2 ** 30)
    for shape in _FRACTION_SHAPES:
        wrong = [case[0] for case in _AROUND_EXPIRY if _wrong(monkeypatch, capsys, case, shape, distort)]
        assert wrong == ["C-at"], (shape[0], wrong)


def test_a_sighting_needs_a_reporter_and_an_established_session():
    """The map's claim is about PLAYERS, so it is worth exactly as much as the
    binding behind the ids. _check_steam_session soft-fails by design in several
    documented conditions — it must never take down the write path it guards —
    so "it did not raise" is a weaker fact than "it verified", and only the
    stronger one may feed corroboration."""
    # no reporter, no sighting: there is no path that records an anonymous one
    main._note_region_seen("us", None)
    main._note_region_seen("us", "")
    assert main._REGION_SEEN == {}

    src = inspect.getsource(main.submit_match)
    assert "_session_was_verified(request)" in src
    assert src.index("_session_was_verified(request)") < src.index("_note_region_seen(")
    # and the verdict starts false, so an exit that neither raises nor verifies
    # cannot read as verified
    check = inspect.getsource(main._check_steam_session)
    assert "_mark_session_verified(request, False)" in check
    assert "_mark_session_verified(request, True)" in check
    assert check.index("_mark_session_verified(request, False)") < \
        check.index("_mark_session_verified(request, True)")
    reader = inspect.getsource(main._session_was_verified)
    assert "return False" in reader, "an unreadable verdict must read as unverified"


def test_only_well_formed_tokens_enter_the_map():
    for junk in ("", "  ", "US-EAST-1", "a", "toolongregion", None):
        main._note_region_seen(junk, "76561198000000001")
    assert main._REGION_SEEN == {}


def test_the_region_a_sighting_carries_is_the_one_this_server_issued():
    """SOURCE SHAPE, not execution: this asserts WHERE the token comes from.
    The behaviour of the map itself is executed by every other test here.

    r13 HIGH. The evidence was the join-time CloudRegion snapshot, then the
    match report's `region` field. Neither is signed -- the match HMAC covers
    seven fields and the region is not one of them -- so establishing a session
    proves who is speaking and nothing about the region named in the sentence,
    and two accounts one person holds could carry a region nobody can connect
    to over the two-player bar and win a tie against an honest one.

    The token is now read back from issued_room_regions, keyed by the room
    name DERIVED from the room id, which the HMAC does cover.

    This test used to assert the literal `"room": str(report.photon_room_id)`,
    and that literal was the defect r14 found: the report id is the room name
    plus a per-game suffix, so keying the lookup on it matched nothing, ever.
    A test that asserts the spelling of the line it is watching cannot fail
    while that line is wrong. What is pinned now is the property the paragraph
    above actually claims -- the key is derived from a field the signature
    covers, and no unsigned field reaches it."""
    src = inspect.getsource(main.submit_match)

    assert "_note_region_seen(report.region" not in src, (
        "the unsigned client field is back in the map"
    )
    assert "SELECT region FROM issued_room_regions" in src
    assert "_issued_room_candidates(report.photon_room_id)" in src, (
        "the lookup key must still be derived from the room id the HMAC covers"
    )
    assert "report.region" not in src[src.index("SELECT region FROM issued_room_regions") - 400:
                                      src.index("SELECT region FROM issued_room_regions") + 900], (
        "the unsigned region field must not appear anywhere in the lookup"
    )
    assert "_note_region_seen(*_region_sighting)" in src

    # The flagged path commits and returns BEFORE the lookup, so an invalidated
    # match is not evidence of anything.
    assert src.index('if ac["invalidate"]:') < src.index("issued_room_regions")

    # The REPORTER only. Recording the opponent as well would let one account
    # name an opponent and supply both halves of "two distinct players".
    assert "report.reported_by_steam_id)" in src
    assert "_region_sighting = (_issued_region, p2.steam_id)" not in src
    assert "_region_sighting = (_issued_region, p1.steam_id)" not in src

    # The old feeds are gone, not merely supplemented.
    assert "_note_region_seen(" not in inspect.getsource(main.queue_join)
    assert MAIN_PY.read_text(encoding="utf-8").count("_note_region_seen(") == 2, (
        "one definition and one caller"
    )


def test_the_sighting_is_published_only_after_the_match_has_committed():
    """r13 MEDIUM. The map is process memory and the match is not committed
    where the region is read. A rollback after the sighting -- the duplicate
    branch takes exactly that path -- would leave evidence for a game that was
    never recorded, and two of those corroborate a region on the strength of
    two failures.

    So the lookup happens inside the transaction and the PUBLICATION happens
    after it: read, hold, commit, then note."""
    src = inspect.getsource(main.submit_match)
    read_at = src.index("SELECT region FROM issued_room_regions")
    commit_at = src.index("await db.commit()", read_at)
    publish_at = src.index("_note_region_seen(*_region_sighting)")
    assert read_at < commit_at < publish_at, (
        "the sighting is published before the match it witnesses is committed"
    )
    # ...and the rollback branch returns before the publication
    duplicate_return = src.index('series_status="duplicate"')
    assert commit_at < duplicate_return < publish_at


def test_a_room_this_server_never_issued_contributes_nothing():
    """A private or tournament room has no binding, so there is no region to
    read and no sighting to make. Fail-closed: absence of a binding is not an
    invitation to fall back on what the client said."""
    src = inspect.getsource(main.submit_match)
    guard = src[src.index("_region_sighting = None"):src.index("_note_region_seen(*")]
    assert "if _issued_region:" in guard, (
        "the sighting must be conditional on the binding existing"
    )
    assert "report.region" not in guard, "no fallback to the client's field"


def test_the_issued_binding_is_written_where_the_room_is_issued():
    """One helper stamps the room on both queue rows, and both issuance sites
    go through it -- so the binding is written exactly when two players are
    told where to play, and only when the stamp actually took."""
    stamp = inspect.getsource(main._queue_stamp_room_reciprocal)
    assert "INSERT INTO issued_room_regions" in stamp
    assert "ON CONFLICT (room_name) DO NOTHING" in stamp, (
        "a reused room name must keep the issuance that sent players somewhere"
    )
    # written only on the proven-reciprocal path
    assert stamp.index("if updated != {my_pid, opp_pid}:") < stamp.index(
        "INSERT INTO issued_room_regions")
    src = MAIN_PY.read_text(encoding="utf-8")
    assert src.count("_queue_stamp_room_reciprocal(db,") == 2, (
        "both issuance sites must go through the helper that writes the binding"
    )
    assert src.count("INSERT INTO issued_room_regions") == 1


def test_the_log_line_says_whether_the_choice_was_corroborated(capsys):
    """"Both cached regions disagree and neither has been seen live" is the
    case that strands a pair behind a series that already exists. It is
    invisible unless the line says so."""
    def second_line():
        main._pick_room_region("", "eu", "", "us", "r")
        return [line for line in capsys.readouterr().out.splitlines() if "chosen=" in line][-1]

    assert "chosen=eu seen=n " in second_line()       # two homes that differ, neither seen live
    _corroborate("eu")
    assert "chosen=eu seen=y " in second_line()


def test_the_monotonic_clock_is_what_ages_a_sighting():
    """Wall-clock would let an NTP step expire or resurrect the whole map."""
    src = inspect.getsource(main._note_region_seen) + inspect.getsource(main._region_corroborated)
    assert "time.monotonic()" in src
    assert "utcnow" not in src and "datetime" not in src


def test_the_changelog_does_not_claim_the_fixed_order_is_gone():
    """r11 HIGH. The bullet said the choice no longer goes to whichever region
    came first alphabetically — and `_region_agreed` still ends in `min(a, b)`
    whenever the two candidates are equally corroborated, which includes every
    pick made on a map that is empty. The sentence has to describe the code's
    actual fallback, because a player reading it would otherwise be told a
    guarantee the server does not make."""
    changelog = (Path(__file__).parents[2] / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    start = changelog.index("The region a ranked room is created in")
    # Line wraps are a property of the file, not of the claim: flatten first so
    # a phrase split across two lines still reads as the phrase.
    bullet = " ".join(changelog[start:start + 700].split())
    assert "came first alphabetically" not in bullet, (
        "the removed-alphabetical claim is back, and min(a, b) still decides a tie"
    )
    assert "the tie falls to a fixed order" in bullet, (
        "the fallback the code actually takes has to be stated"
    )
    assert "after a server restart" in bullet, (
        "the cold-map case is when a reader is most likely to see the fallback"
    )
    # and the fallback the sentence describes is the one the code has
    agreed = inspect.getsource(main._region_agreed)
    assert "return min(a, b)" in agreed


def _fill_with_corroborated(count, pair=("76561198000000101", "76561198000000102")):
    """`count` tokens, each corroborated by the same two reporters. Returns them
    oldest-first."""
    tokens = []
    for i in range(count):
        token = chr(97 + i // 26) + chr(97 + i % 26) + "q"
        _corroborate(token, pair)
        tokens.append(token)
    return tokens


def test_a_full_map_of_corroborated_tokens_still_admits_a_new_region():
    """r12 MEDIUM. Ranking evictions by evidence has a failure of its own, and
    it is the one that was reachable: a token nobody has corroborated YET is by
    definition the least-corroborated entry in the map, so with the map full of
    corroborated tokens every first sighting of a genuine new region was
    evicted in the very call that made it. The second player to connect there
    found nothing to join, and the region could never corroborate — not slowly,
    not eventually, never.

    A region can only corroborate if its first sighting is allowed to wait, so
    the map reserves slots that no corroborated token may take."""
    filled = _fill_with_corroborated(main._REGION_SEEN_MAX_TOKENS)
    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS
    assert all(main._region_corroborated(t) for t in filled)

    main._note_region_seen("hk", "76561198000000201")
    assert "hk" in main._REGION_SEEN, (
        "the first honest sighting was evicted by the call that made it"
    )
    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS, (
        "the map still has to be bounded"
    )

    # ...and the second genuine reporter can now find it there
    main._note_region_seen("hk", "76561198000000202")
    assert main._region_corroborated("hk")


def test_the_nursery_is_bounded_and_gives_up_its_own_oldest():
    """The reserved slots are a floor, not an exemption. New tokens compete
    with other new tokens — recency inside the pool — and the corroborated pool
    is untouched while it is inside its cap."""
    cap = main._REGION_SEEN_CORROBORATED_CAP
    room = main._REGION_SEEN_MAX_TOKENS - cap
    assert 0 < cap < main._REGION_SEEN_MAX_TOKENS
    settled = _fill_with_corroborated(cap)

    newcomers = []
    for i in range(room + 5):
        token = "n" + chr(97 + i // 26) + chr(97 + i % 26)
        main._note_region_seen(token, "76561198000000301")
        newcomers.append(token)

    assert len(main._REGION_SEEN) == main._REGION_SEEN_MAX_TOKENS
    assert all(t in main._REGION_SEEN for t in settled), (
        "a corroborated token was evicted while its pool was inside its cap"
    )
    assert newcomers[-1] in main._REGION_SEEN, "the newest sighting was evicted"
    assert newcomers[0] not in main._REGION_SEEN, "the oldest newcomer survived"


def test_a_corroborated_pool_over_its_cap_gives_up_its_oldest():
    """The other direction, so the floor is not one-way: past the cap, the
    corroborated pool is the one that pays, oldest first."""
    settled = _fill_with_corroborated(main._REGION_SEEN_MAX_TOKENS)
    oldest = settled[0]
    _age(oldest, 3600.0)
    main._note_region_seen("hk", "76561198000000201")
    assert oldest not in main._REGION_SEEN, (
        "the least recently seen corroborated token survived a map over its cap"
    )
    assert "hk" in main._REGION_SEEN


def test_a_sighting_is_taken_on_every_accepted_report_not_once_per_reporter():
    """r12 MEDIUM, answered by the source rather than by a new mechanism. The
    map used to be fed at join time, once -- so two genuine clients that joined
    before their session tokens were minted were accepted, contributed nothing,
    and were never re-noted, whatever they did afterwards.

    The source is now every accepted match report, which is a recurring event:
    an unminted session costs the reports made before its token exists and
    nothing after. Pinned two ways -- the stamp refreshes on re-report, and the
    lookup is not behind any once-per-anything condition."""
    reporter = "76561198000000401"
    main._note_region_seen("eu", reporter)
    _age("eu", main._REGION_SEEN_TTL_SECONDS - 5)
    stale = main._REGION_SEEN["eu"][reporter]
    main._note_region_seen("eu", reporter)
    assert main._REGION_SEEN["eu"][reporter] > stale, (
        "a re-report did not refresh the reporter's own sighting"
    )

    src = MAIN_PY.read_text(encoding="utf-8")
    call = src.index("SELECT region FROM issued_room_regions")
    guard = src[src.rindex("if ", 0, call):call]
    assert "_session_was_verified(request)" in guard, (
        "the sighting must still require an established session"
    )
    assert "once" not in guard and "first" not in guard, (
        "the sighting is per accepted report; a one-shot guard would restore "
        "the hole this replaced"
    )



# ---------------------------------------------------------------------------
# The lookup has to match something. Review r14 HIGH: it never did.
#
# Issuance stores the Photon room name; the client reports that name with a
# per-game suffix appended, and the two were compared for equality. Every test
# above this line passed throughout, because all of them exercise the picker
# and the map directly -- none of them asked whether a real report ever reaches
# the map at all. These do, and they take the client's format from the client's
# own source rather than restating it here, because a restated contract drifts
# and a test that builds its input from the wrong shape proves nothing.
# ---------------------------------------------------------------------------

WATCHER_CS = Path(__file__).resolve().parents[2] / "plugin" / "GameStateWatcher.cs"


def test_the_client_still_builds_report_ids_the_way_this_file_assumes():
    """If the client's format changes, the derivation below is wrong and these
    tests must fail rather than keep asserting against a stale shape.

    UPDATED for the FFA half. This used to require the literal
    `{matchStartTime:HHmmss}_r{FfaMode.GameNumber}` -- a local clock and a
    per-seat counter, which is the shape that let two electors file one game
    under two keys. The FFA key is now built by FfaReportRules.ReportRoomId
    from the room name and a game number frozen at game over, so the literal
    is gone and cannot come back (test_ffa_report_identity asserts its
    absence). What this file actually depends on is unchanged and is what is
    asserted here: the id the client sends is the issued room name with a
    trailing `_r<n>` the derivation below strips, and a suffix run can carry
    more than one underscore-separated part.
    """
    src = WATCHER_CS.read_text(encoding="utf-8", errors="replace")
    assert '_r{reportRoundTotal}' in src, (
        "the 1v1 report id no longer ends in the _r<n> suffix this derivation strips"
    )
    assert 'FfaReportRules.ReportRoomId(' in src, (
        "the FFA report id is no longer built by the shared rule, so this "
        "file cannot know its shape"
    )
    rules = (Path(__file__).resolve().parents[2] / "plugin" / "FfaReportRules.cs"
             ).read_text(encoding="utf-8", errors="replace")
    suffix = " ".join(rules[rules.index("ReportRoomId(string roomName"):][:700].split())
    assert '+ "_r" + frozenGame' in suffix, (
        "the FFA report id no longer ends in the _r<n> suffix this derivation "
        "strips: " + suffix[:300]
    )
    assert '{matchStartTime:HHmmss}' not in src, (
        "a local clock is back in a report id; the derivation below strips a "
        "FIXED number of trailing parts and would hand the lookup a prefix "
        "that was never issued"
    )


def test_a_real_report_id_resolves_to_the_room_the_server_issued():
    """The finding itself. `ranked_<12hex>` is what issuance stores
    (main.py builds it with uuid4().hex[:12]); the client reports that name
    plus `_<HHmmss>_r<n>`. Equality between the two is never true."""
    issued = "ranked_a1b2c3d4e5f6"
    reported = f"{issued}_143052_r3"
    assert reported != issued, "the premise of this test is that they differ"
    cands = main._issued_room_candidates(reported)
    assert issued in cands, (
        f"the issued room name is not among the lookup candidates for {reported!r}; "
        "the corroboration map can never receive a sighting"
    )
    assert reported in cands, "the id as sent must remain a candidate too"


def test_room_names_containing_underscores_survive_intact():
    """Every name this matters for has underscores in it -- `ranked_<hex>` and
    the tournament rooms -- so a derivation that split on the first one would
    hand the lookup a prefix that was never issued to anybody."""
    for issued in ("ranked_a1b2c3d4e5f6", "sct-4f2a_qual_r1_room", "code_ABCD"):
        cands = main._issued_room_candidates(f"{issued}_091500_r12")
        assert issued in cands, f"{issued!r} did not survive suffix removal"


def test_a_bare_room_name_is_left_alone():
    """Nothing in the client sends this today. It costs one list entry to keep
    working if anything ever does, and a derivation that MANGLED it would be
    the same class of silent miss."""
    assert main._issued_room_candidates("ranked_a1b2c3d4e5f6") == ["ranked_a1b2c3d4e5f6"]
    assert main._issued_room_candidates("") == []
    assert main._issued_room_candidates(None) == []


def test_the_lookup_requires_the_pair_the_room_was_issued_to():
    """A region recorded without the pair says only that some room got a
    region, so any accepted report naming that room fed the map. The row now
    records who the server sent, and the read requires the report's two
    players to be exactly those two."""
    src = MAIN_PY.read_text(encoding="utf-8")
    call = src.index("SELECT region FROM issued_room_regions")
    stmt = src[call:src.index("})).scalar()", call)]
    assert "player1_id IS NOT NULL" in stmt and "player2_id IS NOT NULL" in stmt, (
        "a row with no pair recorded must not corroborate anything"
    )
    assert "player1_id = :pa AND player2_id = :pb" in stmt, "pair check missing"
    assert "player1_id = :pb AND player2_id = :pa" in stmt, (
        "the pair check must be order-independent -- which of the two rows the "
        "issuance wrote first is not a fact about the game"
    )
    assert "room_name = :room_full OR room_name = :room_base" in stmt, (
        "the lookup must offer the derived room name as well as the id as sent"
    )


def test_the_issuance_records_the_pair_and_prunes():
    """Both halves of the row, written where the pair is known -- and the
    deletion migration 292 promises, on the path that does the inserting.
    A promised prune with nothing that prunes is a table that grows forever."""
    src = MAIN_PY.read_text(encoding="utf-8")
    ins = src.index("INSERT INTO issued_room_regions")
    stmt = src[ins:src.index("return True", ins)]
    assert "player1_id, player2_id" in stmt, "issuance does not record the pair"
    assert '"a": my_pid, "b": opp_pid' in stmt, "the pair bound is not the issued pair"
    # Asserted by PARTS, not as one literal. The statement is now a bounded
    # range delete and the old single-substring assertion fired ON the fix --
    # the correct response to which is to check the new shape, never to weaken
    # the assertion until it passes.
    assert "DELETE FROM issued_room_regions" in stmt, (
        "migration 292 promises rows are deleted past 30 days; nothing deletes them"
    )
    assert "issued_at <" in stmt and "30 days" in stmt, "the age bound is gone"
    assert "ORDER BY issued_at" in stmt, (
        "an unordered LIMIT deletes an arbitrary 200 rows, so a backlog need "
        "never drain -- the oldest are what must go first"
    )
    assert "SKIP LOCKED" in stmt
    limit = re.search(r"LIMIT (\d+)", stmt)
    assert limit, "the sweep is not bounded in rows"
    assert 1 <= int(limit.group(1)) <= 1000, (
        f"LIMIT {limit.group(1)} is not a bound this transaction can afford; "
        "the stamp UPDATE above holds both queue rows' locks until commit"
    )
    assert "begin_nested" in stmt, (
        "the sweep is not savepoint-isolated, so a statement error aborts the "
        "room-issuance transaction it runs inside"
    )


def _main_code():
    """main.py with COMMENT tokens blanked at preserved offsets.

    Prose is not code: a phrase in a comment satisfied an occurrence count and
    a `re.findall` here matched four "sweeps" for link_codes, three of which
    were sentences. STRING tokens are KEPT on purpose - the SQL being asserted
    about lives in them.
    """
    src = MAIN_PY.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type != tokenize.COMMENT:
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        assert srow == erow, "a comment token spanning lines"
        ln = lines[srow - 1]
        lines[srow - 1] = ln[:scol] + " " * (ecol - scol) + ln[ecol:]
    return "".join(lines)


# Each retention sweep, keyed by the age predicate that DISTINGUISHES it from
# the table's ordinary deletes. link_codes in particular is deleted in three
# other places for reasons that have nothing to do with retention, so "a DELETE
# naming the table" is not the thing being counted here.
_RETENTION_SWEEPS = (
    ("issued_room_regions", "issued_at <"),
    ("link_codes", "expires_at < now()"),
    ("chat_mod_actions", "acked_at <"),
)


def test_every_in_request_retention_sweep_is_bounded():
    """r14 LOW 6 is one line; the defect is a class (#432/#330).

    An age-predicated maintenance DELETE executed inside a request transaction
    is unbounded in rows and therefore unbounded in lock time, and this file
    had three of them. They are swept together and each is asserted here, so a
    fourth added later has a place it must appear.

    The isolation deliberately DIFFERS between them, because the callers can
    tolerate opposite things -- see each site's comment. What does not differ
    is the bound.
    """
    src = _main_code()
    for table, age in _RETENTION_SWEEPS:
        found = []
        at = src.find("DELETE FROM " + table)
        while at != -1:
            window = src[at:at + 500]
            if age in window:
                found.append(window)
            at = src.find("DELETE FROM " + table, at + 1)
        assert found, f"{table}: no age-predicated retention sweep found"
        assert len(found) == 1, f"{table}: {len(found)} retention sweeps; expected one"
        stmt = found[0]
        assert "ctid IN (" in stmt, f"{table}: the bound is not applied to the delete"
        assert "ORDER BY" in stmt, f"{table}: an unordered LIMIT need never drain a backlog"
        assert "SKIP LOCKED" in stmt, f"{table}: sweep can queue behind another request"
        limit = re.search(r"LIMIT (\d+)", stmt)
        assert limit, f"{table}: sweep is not bounded in rows"
        assert 1 <= int(limit.group(1)) <= 1000, f"{table}: LIMIT {limit.group(1)}"


def test_the_retention_sweep_gate_can_fail():
    """The negative control: an unbounded sweep of the shape this replaces must
    not satisfy the gate above."""
    stmt = "DELETE FROM issued_room_regions WHERE issued_at < NOW() - INTERVAL '30 days'"
    assert "ctid IN (" not in stmt and "SKIP LOCKED" not in stmt
    assert re.search(r"LIMIT (\d+)", stmt) is None


def test_the_expired_code_lookup_does_not_depend_on_the_sweep():
    """The link_codes sweep is throttled now, so it does NOT run on most calls
    -- which is only safe because the lookup below it re-checks expiry itself.

    That predicate was already there as belt-and-braces, with a comment saying
    the ordering must not become load-bearing. Throttling the sweep is exactly
    the change that comment warned about, so the predicate stops being
    belt-and-braces and becomes the thing doing the work. It is asserted here
    rather than trusted.
    """
    src = MAIN_PY.read_text(encoding="utf-8")
    at = src.index("async def link_discord")
    body = src[at:src.index("\n@app.", at + 10)]
    assert "LinkCode.expires_at > func.now()" in body, (
        "the expired-code sweep is throttled, so nothing but this predicate "
        "stops an expired code being accepted"
    )
    # ...and the sweep must NOT be savepoint-isolated here: a rollback would
    # leave the expired rows in place, which is the failure, not the recovery.
    sweep = body[body.index("DELETE FROM link_codes"):]
    assert "begin_nested" not in body[:body.index("DELETE FROM link_codes")], (
        "isolating this sweep would hide a failure that leaves expired codes live"
    )
    assert "_link_codes_last_prune" in body, "the sweep is not throttled"


def test_the_comment_no_longer_claims_no_client_supplied_the_region():
    """`_pick_room_region` chooses from the two seats' own region and
    home_region tokens. The DECISION is the server's and that is what the row
    records -- but the file used to say the region was not client-supplied at
    all, which is a stronger claim than the code makes and the kind that gets
    trusted by the next change (r14)."""
    src = MAIN_PY.read_text(encoding="utf-8")
    assert "IT IS NOT A CLIENT-SUPPLIED REGION AT ALL" not in src, (
        "the retired absolute claim is back"
    )
    assert "IT IS NOT READ FROM THE REPORT" in src, "the true, narrower claim is missing"
    assert "the candidates come" in src and "from clients" in src, (
        "the correction must say where the candidates actually come from"
    )


def test_the_pickers_comment_names_the_real_and_only_sighting_source():
    """The picker's comment claims a sighting has exactly ONE source and names
    it: the accepted-match path in `submit_match`. It replaced a sentence that
    named `queue_join` -- which had not been a source since r12, while the
    comment went on saying so, and the picker is the one place a reader checks
    before trusting the corroboration rung.

    Both halves of the replacement can go stale independently: a second writer
    could be added, or that function renamed, and the prose would lie with a
    green suite. So this pins the FACT rather than the sentence -- the wording
    is free to change, the arrangement it describes is not.

    THE MUTATIONS THIS MUST FAIL ON: adding a second `_note_region_seen(` call
    anywhere; moving the existing one out of `submit_match`; and dropping the
    function's name from the comment."""
    src = MAIN_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_note_region_seen"
    ]
    assert len(calls) == 1, (
        f"the comment says ONE source; found {len(calls)} call sites at "
        f"{[c.lineno for c in calls]}"
    )

    # The innermost function spanning the call -- walking every def rather than
    # trusting a line number, so this survives the file moving underneath it.
    holders = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.lineno <= calls[0].lineno <= (node.end_lineno or node.lineno)
    ]
    assert holders, "the sole sighting call is not inside any function"
    enclosing = max(holders, key=lambda node: node.lineno).name
    assert enclosing == "submit_match", (
        f"the comment names submit_match; the call now lives in {enclosing}"
    )

    picker = inspect.getsource(main._pick_room_region)
    assert "submit_match" in picker, (
        "the picker's comment no longer names the source it claims to"
    )


def test_the_deploy_block_orders_every_migration_it_names():
    """Each table this release adds is SELECTed by the new API, so an API
    deployed ahead of one fails those requests with undefined_table -- and 294
    is the mirror image, a backfill only the new API's writes make meaningful,
    so it has to come after.

    Anchored on the heading rather than on the sentence that follows it. The
    first version of this gate matched the literal
    `"**Schema changes:** migration **292**"`, so adding a second migration to
    that sentence ("migration" -> "migrations") made the anchor miss and the
    gate raised ValueError instead of checking anything. A gate keyed to prose
    that is expected to change is a gate that breaks on every legitimate edit
    (#441), which is how gates come to be deleted.
    """
    changelog = (Path(__file__).resolve().parents[2] / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    start = changelog.index("**Schema changes:**")
    # Whitespace-normalised: the CHANGELOG is hard-wrapped, so any phrase long
    # enough to be worth asserting is liable to straddle a line break and a raw
    # substring test would be asserting about where the wrap happens to fall.
    block = " ".join(changelog[start:][:2400].split())

    # BEFORE the API: the tables its own statements read.
    before = block[:block.index("After it")] if "After it" in block else block
    for early, why in (("292", "the match-report path SELECTs issued_room_regions"),
                       ("293", "every path that seats a pair writes series_dc_grants"),
                       ("295", "the leave-report predicate SELECTs series_progress")):
        assert early in before, f"migration {early} is not ordered before the API — {why}"
    assert "BEFORE the API deploy" in block, "nothing is ordered before the API at all"

    # AFTER it: seeds the client already carries, and the backfill.
    #
    # Read from the ORDERED LIST, not from the block as a whole and not even
    # from everything after the pivot. Both wider slices were satisfied by 294's
    # own explanatory paragraph further down, so deleting it from the list left
    # the gate green through two attempts. The list is what a deploy is read
    # off; the prose beneath it explains the list and cannot stand in for it.
    tail_marker = "bundled in the client."
    assert tail_marker in block, (
        "the deploy block no longer ends its migration list where this gate "
        "expects, so the list cannot be isolated from the prose explaining it"
    )
    after = block[block.index("After it"):block.index(tail_marker)]
    for late in ("288", "289", "290", "291", "294"):
        assert late in after, (
            f"migration {late} dropped from the list of what runs AFTER the API"
        )
        assert late not in before, (
            f"migration {late} is ordered before the API deploy; only the tables "
            "the new code reads belong there"
        )
    assert "294 goes LAST" in block, (
        "294 backfills sittings only the new API keeps current — run before the "
        "deploy it leaves out exactly the pairs who were mid-series in the gap"
    )
