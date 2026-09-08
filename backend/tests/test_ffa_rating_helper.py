"""Golden test for _ffa_rating_deltas -- the ONE FFA Glicko-2 update shared by
submit_ffa_match (rated games) and GET /rating-preview/ffa (the Discord
`/elo ffa` preview).

Expected values come from an INDEPENDENT, deliberately plain restatement of
the FFA rating rule (`_reference` below: repeated-minimum selection and
explicit if/elif comparisons -- no sorted()-with-key, no shared code with the
helper beyond glicko2.calculate_new_rating, the primitive both must call).
Fixtures of 4, 6 (+1 ghost) and 10 players cover the tie score, the w(N)
weight, the adjacency bound, the bug-195 upset slot, its one-slot bound, its
largest-gap-first rule and its steam-key tiebreak; the reference reports the
comparison set it built so the test can PROVE each branch was exercised
rather than assume it. Negative controls perturb one input and require the
output to move -- a mutation test without one is decoration. Source-shape
tests pin that the rated path calls the helper by name and no longer carries
its own calculate_new_rating, and that the preview uses the same helper.
"""

import inspect

import pytest
from fastapi import HTTPException

import main
from glicko2 import calculate_new_rating


TAU = main.GLICKO2_TAU


# ── Independent restatement of the rule ─────────────────────────────────────

def _reference(order, unrated, placements, pre, score_target):
    """Returns (results, picks): steam_id -> (r, rd, vol) and steam_id -> the
    ordered comparison set the rule selects. Numbers 4 and 250 are the design
    values written out in the FFA notes (FFA_MAX_RATED_OPPONENTS,
    FFA_UPSET_INCLUDE_GAP); if either constant ever changes, this test is
    MEANT to fail until the golden expectations are re-derived."""
    rated = [s for s in order if s not in unrated]
    results, picks_out = {}, {}
    for me in rated:
        my_place = placements[me]
        my_r = pre[me][0]
        remaining = [q for q in rated if q != me]
        # 1. nearest placements first, canonical steam order (length, then
        #    the string) on equal gaps -- by repeated minimum extraction.
        picks = []
        while remaining and len(picks) < 4:
            best = None
            for q in remaining:
                key = (abs(placements[q] - my_place), len(q), q)
                if best is None or key < best[0]:
                    best = (key, q)
            picks.append(best[1])
            remaining.remove(best[1])
        # 2. at most ONE excluded opponent: rating gap >= 250 and the
        #    lower-rated of the pair placed strictly above; largest gap
        #    first, canonical steam order on equal gaps.
        upset = None
        for q in remaining:
            q_r = pre[q][0]
            gap = abs(my_r - q_r)
            if gap < 250.0:
                continue
            if my_r < q_r:
                inverted = my_place < placements[q]
            elif q_r < my_r:
                inverted = placements[q] < my_place
            else:
                inverted = False
            if not inverted:
                continue
            cand = (gap, len(q), q)
            if upset is None:
                upset = cand
            elif cand[0] > upset[0]:
                upset = cand
            elif cand[0] == upset[0] and (cand[1], cand[2]) < (upset[1], upset[2]):
                upset = cand
        if upset is not None:
            picks.append(upset[2])
        # 3. scores by place, then one rating period.
        opps = []
        for q in picks:
            if my_place < placements[q]:
                s = 1.0
            elif my_place > placements[q]:
                s = 0.0
            else:
                s = 0.5
            opps.append((pre[q][0], pre[q][1], s))
        w = min(1.0, (score_target - 1) / 4.0)
        weights = None if w >= 1.0 else [w for _ in opps]
        results[me] = calculate_new_rating(pre[me][0], pre[me][1], pre[me][2], opps, TAU, weights)
        picks_out[me] = picks
    return results, picks_out


# ── Fixtures ────────────────────────────────────────────────────────────────

def _sid(n):
    return f"765611980000{n:05d}"


def fixture_four():
    """4 players, first-to-5, a shared 2nd place (score 0.5 both ways).
    Report order deliberately differs from finishing order."""
    a, b, c, d = (_sid(101), _sid(102), _sid(103), _sid(104))
    return dict(
        order=[d, a, c, b],
        unrated=set(),
        placements={a: 1, b: 2, c: 2, d: 4},
        pre={a: (1500.0, 350.0, 0.06), b: (1720.5, 61.2, 0.0587),
             c: (1433.0, 120.4, 0.0612), d: (1988.9, 45.0, 0.05)},
        score_target=5,
    )


def fixture_six_plus_ghost():
    """6 rated players + 1 ghost (in the roster, unrated, holds a place),
    first-to-3 so w(N)=0.5 weights apply. The 1300-rated winner and the
    2100-rated 6th are 5 places apart -- outside each other's 4 nearest --
    and the result inverted expectation, so both gain the upset slot."""
    p = {i: _sid(200 + i) for i in range(1, 8)}
    return dict(
        order=[p[3], p[1], p[7], p[6], p[2], p[5], p[4]],
        unrated={p[7]},
        placements={p[1]: 1, p[2]: 2, p[3]: 3, p[4]: 4, p[5]: 5, p[6]: 6, p[7]: 7},
        pre={p[1]: (1300.0, 90.0, 0.06), p[2]: (1650.0, 70.0, 0.059),
             p[3]: (1580.0, 200.0, 0.061), p[4]: (1490.0, 55.0, 0.058),
             p[5]: (1700.0, 110.0, 0.06), p[6]: (2100.0, 48.0, 0.0555),
             p[7]: (1500.0, 350.0, 0.06)},
        score_target=3,
    ), p


def fixture_ten():
    """10 players, no ties, first-to-5. Player 305 (1500, 5th) has TWO
    upset candidates at the same 300 gap (309 and 310, both 1800, 9th and
    10th) -- the one-slot bound and the steam-key tiebreak decide. Player
    310 has four upset candidates at different gaps -- largest gap wins."""
    p = {i: _sid(300 + i) for i in range(1, 11)}
    return dict(
        order=[p[10], p[2], p[7], p[1], p[5], p[9], p[3], p[8], p[4], p[6]],
        unrated=set(),
        placements={p[i]: i for i in range(1, 11)},
        pre={p[1]: (1800.0, 60.0, 0.06), p[2]: (1490.0, 80.0, 0.0605),
             p[3]: (1510.0, 75.0, 0.0595), p[4]: (1505.0, 300.0, 0.06),
             p[5]: (1500.0, 100.0, 0.06), p[6]: (1495.0, 66.0, 0.0611),
             p[7]: (1520.0, 58.0, 0.0588), p[8]: (1400.0, 140.0, 0.062),
             p[9]: (1800.0, 52.0, 0.057), p[10]: (1800.0, 210.0, 0.0603)},
        score_target=5,
    ), p


def _helper(fx):
    return main._ffa_rating_deltas(fx["order"], fx["unrated"], fx["placements"],
                                   fx["pre"], fx["score_target"])


# ── Golden equality ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("make", [fixture_four, lambda: fixture_six_plus_ghost()[0],
                                  lambda: fixture_ten()[0]])
def test_helper_matches_the_independent_restatement_exactly(make):
    fx = make()
    expected, _ = _reference(**fx)
    got = _helper(fx)
    assert list(got) == [s for s in fx["order"] if s not in fx["unrated"]]
    for sid in expected:
        assert got[sid] == expected[sid], sid   # same primitive, same inputs: bit-identical


def test_four_players_compare_against_everyone_and_share_the_tie():
    fx = fixture_four()
    _, picks = _reference(**fx)
    assert all(len(v) == 3 for v in picks.values())
    got = _helper(fx)
    a, b, c, d = (_sid(101), _sid(102), _sid(103), _sid(104))
    assert got[a][0] > fx["pre"][a][0]      # beat all three
    assert got[d][0] < fx["pre"][d][0]      # lost to all three
    # the tied pair moved by the OTHER two results plus a draw, not a loss
    assert got[b][0] != fx["pre"][b][0] and got[c][0] != fx["pre"][c][0]


def test_six_players_exercise_the_upset_slot_and_the_weight():
    fx, p = fixture_six_plus_ghost()
    _, picks = _reference(**fx)
    assert len(picks[p[1]]) == 5 and picks[p[1]][-1] == p[6]      # winner gained the upset slot
    assert len(picks[p[6]]) == 5 and picks[p[6]][-1] == p[1]      # ...and reciprocally
    assert len(picks[p[4]]) == 4                                   # 190 gap: no upset
    assert p[7] not in picks and all(p[7] not in v for v in picks.values())
    # first-to-3 counts as half a game: the unweighted update moves MORE
    got = _helper(fx)
    full = main._ffa_rating_deltas(fx["order"], fx["unrated"], fx["placements"], fx["pre"], 5)
    for sid in got:
        assert abs(full[sid][0] - fx["pre"][sid][0]) > abs(got[sid][0] - fx["pre"][sid][0]), sid


def test_ten_players_bound_the_upset_slot_to_one_by_gap_then_steam_key():
    fx, p = fixture_ten()
    _, picks = _reference(**fx)
    assert picks[p[5]] == [p[4], p[6], p[3], p[7], p[9]]          # tie on gap -> lower key (309)
    assert picks[p[10]][:4] == [p[9], p[8], p[7], p[6]]
    assert picks[p[10]][4] == p[2]                                 # 310 gap beats 300/295/290
    assert all(len(v) <= 5 for v in picks.values())
    got = _helper(fx)
    assert got[p[1]][0] > fx["pre"][p[1]][0]
    assert got[p[10]][0] < fx["pre"][p[10]][0]


# ── Negative controls: one input moves, the output must move ────────────────

def test_negative_control_opponent_rating_moves_both_results():
    fx, p = fixture_ten()
    base = _helper(fx)
    fx["pre"] = dict(fx["pre"])
    r, rd, vol = fx["pre"][p[6]]
    fx["pre"][p[6]] = (r + 1.0, rd, vol)
    moved = _helper(fx)
    assert moved[p[6]] != base[p[6]]
    assert moved[p[5]] != base[p[5]]                                # 306 is in 305's set
    assert moved[p[1]] == base[p[1]]                                # 306 is NOT in 301's set


def test_negative_control_score_target_moves_every_result():
    fx, _ = fixture_ten()
    base = _helper(fx)
    fx["score_target"] = 3
    moved = _helper(fx)
    assert all(moved[s] != base[s] for s in base)


def test_negative_control_swapping_first_and_last_moves_them():
    fx, p = fixture_ten()
    base = _helper(fx)
    fx["placements"] = dict(fx["placements"])
    fx["placements"][p[1]], fx["placements"][p[10]] = 10, 1
    moved = _helper(fx)
    assert moved[p[1]] != base[p[1]] and moved[p[10]] != base[p[10]]
    assert moved[p[1]][0] < base[p[1]][0] and moved[p[10]][0] > base[p[10]][0]


def test_a_ghost_changes_nothing_for_the_rated_players():
    fx, p = fixture_six_plus_ghost()
    with_ghost = _helper(fx)
    assert p[7] not in with_ghost
    fx["order"] = [s for s in fx["order"] if s != p[7]]
    fx["unrated"] = set()
    fx["placements"] = {k: v for k, v in fx["placements"].items() if k != p[7]}
    fx["pre"] = {k: v for k, v in fx["pre"].items() if k != p[7]}
    assert _helper(fx) == with_ghost


def test_only_computes_one_player_identically():
    fx, p = fixture_ten()
    everyone = _helper(fx)
    for sid in fx["order"]:
        single = main._ffa_rating_deltas(fx["order"], fx["unrated"], fx["placements"],
                                         fx["pre"], fx["score_target"], only=sid)
        assert single == {sid: everyone[sid]}


# ── Source shape: one implementation, reached from both paths ───────────────

def test_the_rated_path_calls_the_helper_and_owns_no_glicko_call():
    src = inspect.getsource(main.submit_ffa_match)
    assert src.count("_ffa_rating_deltas(") == 1
    assert "calculate_new_rating(" not in src


def test_the_ffa_preview_calls_the_same_helper():
    src = inspect.getsource(main.get_rating_preview_ffa)
    assert "_ffa_rating_deltas(" in src
    assert "calculate_new_rating(" not in src


def test_the_helper_is_pure():
    src = inspect.getsource(main._ffa_rating_deltas)
    assert "await" not in src and "db." not in src and "text(" not in src
    assert list(inspect.signature(main._ffa_rating_deltas).parameters) == [
        "order", "unrated", "placements", "pre", "score_target", "only"]


def test_the_2v2_preview_uses_the_live_update_shape():
    src = inspect.getsource(main.get_rating_preview_2v2)
    assert src.count("calculate_new_rating(") == 2          # win and loss per player
    assert "GLICKO2_TAU" in src and "_glicko_expectancy(" in src
    assert "1.0" in src and "0.0" in src


@pytest.mark.parametrize("raw", ["", "1,2", "a,b,c", "1,1,2", "1" * 21 + ",2,3",
                                 "١,2,3", ",".join(str(i) for i in range(11))])
def test_preview_id_lists_reject_bad_input_with_400(raw):
    with pytest.raises(HTTPException) as ei:
        main._parse_steam_id_list(raw, 3, 10, "ids")
    assert ei.value.status_code == 400


def test_preview_id_lists_accept_and_trim():
    assert main._parse_steam_id_list(" 1, 2 ,3", 3, 10, "ids") == ["1", "2", "3"]
    assert main._parse_steam_id_list("7,8", 2, 2, "team_a") == ["7", "8"]


def test_the_preview_route_takes_the_lobby_score_target():
    # r5 M4: the preview's w(N) must follow the lobby's target, and the
    # response must say which target it assumed.
    import inspect
    from api import main as m
    src = inspect.getsource(m.get_rating_preview_ffa)
    assert "score_target: int | None = Query(None, ge=2, le=50" in src
    assert 'int(score_target) if score_target is not None else int(FFA_CONFIG_DEFAULTS["score_target"])' in src
    assert 'f"no ties, first to {score_target}' in src
