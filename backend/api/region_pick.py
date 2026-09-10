"""Room-region pick for multiplayer rooms (2v2, 1v2, FFA, hosted lobbies).

PURE: stdlib only, no database, no import of main.py (main -> tournaments is
already circular). The caller hands over each seat's ping map, the regions it
considers real, the 45-day volumes (a tie-break, never liveness) and the
mode's existing pick, and gets a verdict back. Design: v4 policy resolution
(sum selection over the v3 baseline/quorum/gate), residuals R1, R3, R4.

The three module-level ``_``-prefixed flags at the bottom of this header are
TEST-ONLY mutation knobs. They default off, are read at call time, and exist
so the negative controls in test_group_region_pick.py can flip one clause of
the rule each without editing this file. Production never sets them.
"""

import time
from collections import Counter, namedtuple

PING_MIN_MS = 1
PING_MAX_MS = 5000

WHY_BASELINE = "baseline"
WHY_MAJORITY = "majority"
WHY_BOUNDED = "bounded"
WHY_QUORUM = "quorum"
WHY_ERROR = "error"

# ── Test-only knobs (negative controls; see module docstring) ────────────────
_MAJORITY_STRICT = False   # majority arm `2*gain >= N` becomes `2*gain > N`
_SKIP_QUORUM = False       # the quorum guard is not applied (stale maps get used)
_SELECT_BY_WORST = False   # select by (worst, sum) instead of (sum, worst) — the v3 selection

_Seat = namedtuple("_Seat", "id home map fresh")
_Cand = namedtuple("_Cand", "region sum worst gain max_regret admitted_by")


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _clean_map(raw):
    """The map as {code: ms} with every garbage ENTRY dropped (non-str or
    empty key, non-int or bool value, value outside 1..5000). Not a dict, or
    nothing left after dropping, is absent (None): an empty map carries no
    information and cannot prove anything about a seat."""
    if not isinstance(raw, dict):
        return None
    clean = {}
    for key, ms in raw.items():
        if not isinstance(key, str) or not key:
            continue
        if isinstance(ms, bool) or not isinstance(ms, int):
            continue
        if not (PING_MIN_MS <= ms <= PING_MAX_MS):
            continue
        clean[key] = ms
    return clean or None


def _baseline(seats, legacy_pick):
    """B = the mode of the members' non-empty homes; legacy_pick when nobody
    has one. Tie policy (R3, v4): among tied modal homes, when EVERY member
    has a FRESH map containing EACH tied candidate, the lowest total ping,
    then the lowest worst, then the lexically first code; otherwise the
    lexically first code (a documented bias). Returns (B, tie) with tie in
    "sum" / "worst" / "lexical" / None (no tie)."""
    homes = [s.home for s in seats if s.home]
    if not homes:
        return legacy_pick, None
    counts = Counter(homes)
    top = max(counts.values())
    tied = sorted(code for code, n in counts.items() if n == top)
    if len(tied) == 1:
        return tied[0], None
    if all(s.fresh and all(code in s.map for code in tied) for s in seats):
        def key(code):
            return (sum(s.map[code] for s in seats), max(s.map[code] for s in seats), code)
        ranked = sorted(tied, key=key)
        best, runner_up = key(ranked[0]), key(ranked[1])
        if best[0] < runner_up[0]:
            return ranked[0], "sum"
        if best[1] < runner_up[1]:
            return ranked[0], "worst"
        return ranked[0], "lexical"
    return tied[0], "lexical"


def pick_region_for_group(members, live_regions, volumes, legacy_pick, *,
                          margin_ms=20, regret_ms=30, max_age_s=180, now=None):
    """The room's region for a group issuance: (pick, why, detail).

    Disclosure (both sentences travel together — docstring, log, changelog;
    stated at the production constants, margin 20 / regret 30): A move needs
    either half the room to gain 20 ms or nobody to lose more than 30 ms, and
    then happens only if it lowers the room's total ping — so a majority can
    move a minority, but never by more than the majority gains. The room may
    be a region no member calls home.

    Inputs. ``members``: seat-ordered dicts ``{"id", "home", "map",
    "measured_at"}`` — ``map`` is ``{code: ms}`` or None, ``measured_at`` an
    epoch float or None. ``live_regions``: the codes the server considers real
    (candidates must be in it; the baseline need not be). ``volumes``: code ->
    45-day volume, a tie-break only. ``legacy_pick``: the mode's existing pick,
    used only when no member has a home, or when this function fails.

    The rule.
      1. B (baseline) = the mode of the members' non-empty homes; the region
         every member would get today. Tie among modal homes: if every member
         has a fresh map containing each tied candidate, the lowest total
         ping, then the lowest worst, then the lexically first code; otherwise
         the lexically first code. ``detail["tie"]`` records which.
      2. Quorum: every member has a FRESH map (``now - measured_at <=
         max_age_s``) that contains B. Otherwise the verdict is B,
         ``why="quorum"``, and ``detail["seats"]`` says per seat why
         (``fresh|stale|absent|missing_baseline``). A seat whose cost at B is
         unknown can never be moved by the others' numbers.
      3. Choosable = live_regions ∩ (∩ over members of the map's codes). B is
         in every map by quorum and is admitted unconditionally.
      4. Admission of r ≠ B: gain = members whose ping drops by at least
         ``margin_ms`` (``map[B] - map[r] >= margin_ms``); max_regret = the
         largest ``map[r] - map[B]`` over members. Admitted iff
         ``2*gain >= N`` (majority arm) OR ``max_regret <= regret_ms``
         (bounded arm). Pairs and solos go through the same arithmetic.
      5. Selection among the admitted: the lowest total ping, then the lowest
         worst, then the HIGHER volume, then the lexically first code. The
         room leaves B only for a strictly lower total, or an equal total
         with a strictly lower worst (R1: volume and code order only
         candidates that already beat B). ``why`` is "baseline" when the pick
         is B, "majority" when the majority arm admitted the winner (whether
         or not the bounded arm did too), "bounded" when only the regret arm
         admitted it.

    Outcomes the rule can never reach (sum selection):
      * A lone far player never moves a 3+ room unless every other member
        pays at most ``regret_ms`` AND the room's total still falls — its own
        gain must exceed what the others pay, added up.
      * A non-majority move requires that nobody pays more than the bound;
        with the bound at 0 nobody pays anything — and a move that costs no
        one still happens when it lowers the total (R4).
      * A majority move never costs the minority more, in total, than the
        majority gains in total: the total must strictly fall. There is no
        separate cap; the majority's own gain is the cap.
      * A room with ANY seat lacking a fresh map that contains B never moves
        off B.
      * The room never leaves B for an equal total unless the worst seat
        strictly improves, and never on volume or code alone (R1).
      * The host's home has no role anywhere (H); ties fall to numbers, then
        to the documented lexical bias.

    Never raises and never returns None: any exception inside the body yields
    ``(legacy_pick, "error", {"error": repr(exc)})``. Garbage map entries are
    dropped before use (see ``_clean_map``); a garbage ``measured_at`` makes
    the seat stale; a non-dict member is an absent seat; an empty room has no
    quorum. ``detail`` carries ``baseline, n, sum_b, sum_pick, worst_b,
    worst_pick, gain, max_regret, candidates`` (selection-ordered
    ``{region, sum, worst, gain, max_regret, admitted_by}``), ``seats``
    (seat-ordered ``{id, state, cost_b, cost_pick}``) and ``tie`` — enough to
    reconstruct the pick line after the queue rows are gone. The verdict
    (pick, why) is invariant under member order."""
    try:
        return _pick(members, live_regions, volumes, legacy_pick,
                     margin_ms, regret_ms, max_age_s, now)
    except Exception as exc:  # noqa: BLE001 — the contract is "never raises"
        return legacy_pick, WHY_ERROR, {"error": repr(exc)}


def _pick(members, live_regions, volumes, legacy_pick, margin_ms, regret_ms, max_age_s, now):
    if now is None:
        now = time.time()
    live = {code for code in (live_regions or ()) if isinstance(code, str) and code}
    vols = volumes if isinstance(volumes, dict) else {}

    def volume(code):
        v = vols.get(code, 0)
        return v if _is_number(v) else 0

    seats = []
    for member in (members or ()):
        if not isinstance(member, dict):
            member = {}
        clean = _clean_map(member.get("map"))
        at = member.get("measured_at")
        fresh = clean is not None and _is_number(at) and (now - at) <= max_age_s
        home = member.get("home")
        home = home if isinstance(home, str) and home else None
        seats.append(_Seat(member.get("id"), home, clean, fresh))
    n = len(seats)

    baseline, tie = _baseline(seats, legacy_pick)

    def state(seat):
        if seat.map is None:
            return "absent"
        if not seat.fresh:
            return "stale"
        if baseline not in seat.map:
            return "missing_baseline"
        return "fresh"

    states = [state(s) for s in seats]

    def seat_rows(pick):
        return [{"id": s.id, "state": st,
                 "cost_b": s.map.get(baseline) if s.map else None,
                 "cost_pick": s.map.get(pick) if s.map else None}
                for s, st in zip(seats, states)]

    detail = {"baseline": baseline, "n": n, "sum_b": None, "sum_pick": None,
              "worst_b": None, "worst_pick": None, "gain": None, "max_regret": None,
              "candidates": [], "seats": seat_rows(baseline), "tie": tie}

    # Quorum: every seat fresh and holding B. An empty room has no quorum.
    if n == 0 or (not _SKIP_QUORUM and any(st != "fresh" for st in states)):
        return baseline, WHY_QUORUM, detail

    # From here every seat's map has B (under _SKIP_QUORUM a seat may not:
    # the KeyError/TypeError surfaces as why=error, which is the point).
    common = set(seats[0].map)
    for seat in seats[1:]:
        common &= set(seat.map)
    costs_b = [s.map[baseline] for s in seats]
    sum_b, worst_b = sum(costs_b), max(costs_b)

    cands = []
    for code in sorted((live & common) - {baseline}):
        costs = [s.map[code] for s in seats]
        gain = sum(1 for cb, c in zip(costs_b, costs) if cb - c >= margin_ms)
        max_regret = max(c - cb for cb, c in zip(costs_b, costs))
        majority = (2 * gain > n) if _MAJORITY_STRICT else (2 * gain >= n)
        bounded = max_regret <= regret_ms
        admitted_by = WHY_MAJORITY if majority else (WHY_BOUNDED if bounded else None)
        cands.append(_Cand(code, sum(costs), max(costs), gain, max_regret, admitted_by))

    def primary(total, worst):
        return (worst, total) if _SELECT_BY_WORST else (total, worst)

    def order(cand):
        return primary(cand.sum, cand.worst) + (-volume(cand.region), cand.region)

    cands.sort(key=order)
    better = [c for c in cands
              if c.admitted_by and primary(c.sum, c.worst) < primary(sum_b, worst_b)]

    if better:
        winner = better[0]
        pick, why = winner.region, winner.admitted_by
        sum_pick, worst_pick, gain, max_regret = winner.sum, winner.worst, winner.gain, winner.max_regret
    else:
        pick, why = baseline, WHY_BASELINE
        sum_pick, worst_pick, gain, max_regret = sum_b, worst_b, 0, 0

    detail.update({
        "sum_b": sum_b, "sum_pick": sum_pick, "worst_b": worst_b, "worst_pick": worst_pick,
        "gain": gain, "max_regret": max_regret,
        "candidates": [c._asdict() for c in cands],
        "seats": seat_rows(pick),
    })
    return pick, why, detail
