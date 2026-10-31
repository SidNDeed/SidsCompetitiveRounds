"""Double-elimination topology: build AND resolve every field size 8-16.

Why this file exists: no test ever RESOLVED a built bracket, which is how two
builder defects shipped. 9-14-player double-elim brackets crashed the build
outright (the grand final indexed an empty final losers-bracket round after
bye-feeder pruning halved sparse rounds to zero, so such a tournament could
never lock), and 15-player fields persisted a terminal losers-bracket bye
whose winners-bracket feeder had not resolved, silently cutting that feeder's
loser after one loss.

The BUILDER under test is production code, imported directly. The RESOLVER
here is a deliberate MIRROR of the pure resolution semantics of
tournaments._activate_ready_matches (terminal-aware prereq gate, W/L role
resolution, structural-vacancy propagation, the GF_RESET exclusion, and the
one-shot legacy-shape repair); the real function is inseparable from its
database session, and test_tournament_fence_pg.py drives it on PostgreSQL.
If those semantics change, change _resolve() to match: a divergence means
this file or the resolver is wrong, and the answer is never to weaken the
invariants below. GF_RESET is not modeled: it is created at runtime only for
a losers-bracket champion's grand-final win, so at topology level the grand
final is final (its loser may end on one loss).

Two negative controls prove the checks can fail: the resolver with vacancy
propagation switched off wedges on a double withdrawal, and the legacy 15p
shape without its repair cuts a live player after one loss.

Run: python -m pytest backend/tests/test_bracket_topology.py -q
"""
import os
import sys
import uuid
from collections import defaultdict

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "api")))
from tournament_bracket import SignupInput, build_double_elim_bracket  # noqa: E402

TERMINAL = ("completed", "forfeit", "double_forfeit", "bye_auto")
SIZES = list(range(8, 17))


def _p1(m):
    return m.p1_signup_id


def _p2(m):
    return m.p2_signup_id


DECIDERS = [pytest.param(_p1, id="p1-wins"), pytest.param(_p2, id="p2-wins")]


def _make(n):
    return [SignupInput(uuid.uuid4(), uuid.uuid4(), elo=2000 - i * 10)
            for i in range(n)]


def _loser_of(m):
    if m.winner_signup_id is None:
        return None
    return m.p1_signup_id if m.winner_signup_id == m.p2_signup_id else m.p2_signup_id


def _resolve(rows, decide, max_ticks=64, reverse=False, propagate=True, repair=True):
    """Resolve a built bracket to completion; returns losses per signup_id.
    Raises AssertionError on a wedge (pending rows with no progress).
    reverse=True iterates dependents before feeders each tick, the
    worst-case order for the legacy-repair flap. propagate / repair switch
    off the two resolver behaviours for the negative controls."""
    by_id = {r.id: r for r in rows}
    for r in rows:
        # Persistence step (lock_tournament): builder byes are terminal,
        # and lock persistence stamps no ended_at.
        r.status = "bye_auto" if r.is_bye else "pending"
        r.ended_at = None
    losses = defaultdict(int)
    for _ in range(max_ticks):
        progressed = False
        order = list(rows)
        if reverse:
            order.reverse()
        # Legacy-shape repair: a one-prereq winnerless LB bye_auto row with
        # NO ended_at reopens exactly once; a vacancy-terminalized row
        # (ended_at stamped) never reopens.
        if repair:
            for m in order:
                if (m.bracket_side == "L" and m.status == "bye_auto"
                        and m.winner_signup_id is None and m.ended_at is None
                        and len(m.prereq_match_ids or []) == 1):
                    m.status = "pending"
                    m.is_bye = False
                    progressed = True
        for m in order:
            if m.status != "pending":
                continue
            pre = [by_id[p] for p in (m.prereq_match_ids or [])]
            # Terminal-aware gate: a terminal prereq without a winner (a
            # fully-vacant bye) resolves as contributing nobody.
            if any(p.winner_signup_id is None and p.status not in TERMINAL
                   for p in pre):
                continue
            if pre:
                roles = list(m.prereq_roles or [])
                resolved = []
                for i, p in enumerate(pre):
                    role = roles[i] if i < len(roles) else "W"
                    resolved.append(_loser_of(p) if role == "L"
                                    else p.winner_signup_id)
                m.p1_signup_id = resolved[0] if len(resolved) >= 1 else None
                m.p2_signup_id = resolved[1] if len(resolved) >= 2 else None
                # Structural-vacancy propagation.
                if propagate and m.bracket_side != "GF_RESET" and not (
                        m.p1_signup_id and m.p2_signup_id):
                    m.is_bye = True
                    m.status = "bye_auto"
                    m.winner_signup_id = m.p1_signup_id or m.p2_signup_id
                    m.ended_at = True
                    progressed = True
                    continue
            if not (m.p1_signup_id and m.p2_signup_id):
                continue
            m.winner_signup_id = decide(m)
            m.status = "completed"
            losses[_loser_of(m)] += 1
            progressed = True
        if all(r.status != "pending" for r in rows):
            return losses
        if not progressed:
            stuck = [(r.bracket_side, r.round) for r in rows
                     if r.status == "pending"]
            raise AssertionError(f"wedged with pending rows: {stuck}")
    raise AssertionError("did not converge")


def _check_full_run(n, rows, decide, withdrawn=frozenset(), **kw):
    losses = _resolve(rows, decide, **kw)
    gf = next(r for r in rows if r.bracket_side == "GF")
    assert gf.status in TERMINAL, "GF unresolved"
    live = set()
    for r in rows:
        for sid in (r.p1_signup_id, r.p2_signup_id, r.winner_signup_id):
            if sid is not None and sid not in withdrawn:
                live.add(sid)
    champ = gf.winner_signup_id
    for sid in live:
        assert losses[sid] <= 2, f"n={n}: {sid} took {losses[sid]} losses"
        if losses[sid] == 0:
            assert sid == champ, f"n={n}: 0-loss non-champion cut from bracket"
        if losses[sid] == 1 and sid != champ:
            # Only the GF loser may exit on one loss (reset not modeled).
            assert sid == _loser_of(gf), \
                f"n={n}: live player cut after ONE loss"
    return losses


def _withdraw(rows, victim):
    """Mirror the FULL locked leave with no speculative pool: the surgery
    loop of _handle_leaving_signup, which rewrites only rows where the victim
    has a present opponent, followed by the signup DELETE's foreign-key
    effect (models.py ON DELETE SET NULL nulls every remaining p1/p2/winner
    reference). A bye HOLDER's own bye row and any builder-pre-filled
    next-round seat are exactly what the surgery loop skips and SET NULL
    then empties."""
    for m in rows:
        if m.p1_signup_id == victim or m.p2_signup_id == victim:
            if m.p1_signup_id == victim and m.p2_signup_id:
                m.is_bye = True
                m.winner_signup_id = m.p2_signup_id
                m.p1_signup_id = None
                m.status = "bye_auto"
            elif m.p2_signup_id == victim and m.p1_signup_id:
                m.is_bye = True
                m.winner_signup_id = m.p1_signup_id
                m.p2_signup_id = None
                m.status = "bye_auto"
    for m in rows:
        if m.p1_signup_id == victim:
            m.p1_signup_id = None
        if m.p2_signup_id == victim:
            m.p2_signup_id = None
        if m.winner_signup_id == victim:
            m.winner_signup_id = None


def _r1_entrants(rows):
    """Every player with an R1 seat, bye holders INCLUDED: the top seeds of
    9-15 fields sit in R1 byes, and their withdrawal exercises the
    winner-FK-null plus pre-filled-next-seat cascade that real-match entrants
    never touch."""
    return [sid for r in rows
            if r.round == 1 and r.bracket_side == "W"
            for sid in (r.p1_signup_id, r.p2_signup_id) if sid]


def _make_legacy_15p():
    """A 15p bracket as the OLD builder persisted it: a TERMINAL one-prereq
    LB bye whose winners-bracket feeder never resolved."""
    rows = build_double_elim_bracket(_make(15))
    bye_row = next(r for r in rows if r.round == 1
                   and r.bracket_side == "W" and r.is_bye)
    legacy = next(r for r in rows if r.bracket_side == "L"
                  and r.round == 1 and bye_row.id in r.prereq_match_ids)
    real_feeder_id = next(pid for pid in legacy.prereq_match_ids
                          if pid != bye_row.id)
    legacy.prereq_match_ids = [real_feeder_id]
    legacy.prereq_roles = ["L"]
    legacy.is_bye = True
    real_feeder = next(r for r in rows if r.id == real_feeder_id)
    return rows, real_feeder


# -- the builder's own shape ----------------------------------------------------

@pytest.mark.parametrize("n", SIZES)
def test_losers_round_one_pairs_every_winners_round_one_feeder(n):
    """Full LB topology at every size: LB R1 is slot_count/4 wide, every LB
    R1 match takes the losers of two WB R1 matches, and the builder persists
    no LB bye (vacancies are decided at runtime, never at build time)."""
    rows = build_double_elim_bracket(_make(n))
    slot_count = 8 if n <= 8 else 16
    wb1 = [r for r in rows if r.bracket_side == "W" and r.round == 1]
    lb1 = [r for r in rows if r.bracket_side == "L" and r.round == 1]
    assert len(wb1) == slot_count // 2, (n, len(wb1))
    assert len(lb1) == slot_count // 4, (n, len(lb1))
    fed = []
    for m in lb1:
        assert list(m.prereq_roles) == ["L", "L"], (n, m.prereq_roles)
        assert len(m.prereq_match_ids) == 2 and not m.is_bye, (n, m.prereq_match_ids)
        fed.extend(m.prereq_match_ids)
    assert sorted(fed, key=str) == sorted((r.id for r in wb1), key=str), n
    assert not [r for r in rows if r.bracket_side == "L" and r.is_bye], n
    assert sum(1 for r in rows if r.bracket_side == "GF") == 1, n


# -- resolution ---------------------------------------------------------------

@pytest.mark.parametrize("decide", DECIDERS)
@pytest.mark.parametrize("n", SIZES)
def test_clean_run_resolves_with_two_loss_elimination(n, decide):
    rows = build_double_elim_bracket(_make(n))
    losses = _check_full_run(n, rows, decide)
    assert sum(losses.values()) > 0


@pytest.mark.parametrize("decide", DECIDERS)
@pytest.mark.parametrize("n", SIZES)
def test_every_single_withdrawal_resolves(n, decide):
    """Every possible single pre-start withdrawal, bye holders included,
    still resolves without cutting any OTHER live player early."""
    n_entrants = len(_r1_entrants(build_double_elim_bracket(_make(n))))
    assert n_entrants == n, (n, n_entrants)
    for idx in range(n_entrants):
        rows = build_double_elim_bracket(_make(n))
        victim_id = _r1_entrants(rows)[idx]
        _withdraw(rows, victim_id)
        _check_full_run(n, rows, decide, withdrawn={victim_id})


@pytest.mark.parametrize("decide", DECIDERS)
@pytest.mark.parametrize("n", SIZES)
def test_double_withdrawal_cascades_a_winnerless_feeder(n, decide):
    """Both players of the FIRST real R1 match leave: the fully-vacant LB
    feeder must cascade winnerless; the second withdrawal empties the first
    one's surgery bye through SET NULL."""
    rows = build_double_elim_bracket(_make(n))
    first_real = next(r for r in rows if r.round == 1
                      and r.bracket_side == "W" and not r.is_bye)
    v1, v2 = first_real.p1_signup_id, first_real.p2_signup_id
    _withdraw(rows, v1)
    _withdraw(rows, v2)
    _check_full_run(n, rows, decide, withdrawn={v1, v2})


@pytest.mark.parametrize("decide", DECIDERS)
@pytest.mark.parametrize("reverse", [False, True], ids=["feeder-first", "dependent-first"])
def test_legacy_15p_shape_repair_is_one_shot(reverse, decide):
    """A 15p bracket locked under the OLD builder: the repair reopens the
    terminal one-prereq LB bye exactly once (a) so the real loser fills it,
    and (b) when a withdrawal leaves its feeder loserless, the reopened row
    vacancy-terminalizes once and stays terminal (the flap wedged dependents
    in dependent-before-feeder order, which reverse=True forces)."""
    rows, _feeder = _make_legacy_15p()
    _check_full_run(15, rows, decide, reverse=reverse)
    rows, feeder = _make_legacy_15p()
    victim = feeder.p1_signup_id
    _withdraw(rows, victim)
    _check_full_run(15, rows, decide, withdrawn={victim}, reverse=reverse)


def test_mirror_terminal_set_matches_the_resolver():
    """The mirror's terminal set is the resolver's own: the match terminal
    states plus bye_auto, which _activate_ready_matches's prereq gate and
    _maybe_complete_tournament both accept."""
    import tournaments
    assert tuple(tournaments._MATCH_TERMINAL_STATES) + ("bye_auto",) == TERMINAL


# -- negative controls: the checks above can fail ------------------------------

@pytest.mark.parametrize("n", [9, 12, 16])
def test_control_without_vacancy_propagation_a_double_withdrawal_wedges(n):
    rows = build_double_elim_bracket(_make(n))
    first_real = next(r for r in rows if r.round == 1
                      and r.bracket_side == "W" and not r.is_bye)
    v1, v2 = first_real.p1_signup_id, first_real.p2_signup_id
    _withdraw(rows, v1)
    _withdraw(rows, v2)
    with pytest.raises(AssertionError, match="wedged"):
        _check_full_run(n, rows, _p1, withdrawn={v1, v2}, propagate=False)


def test_control_legacy_shape_without_the_repair_cuts_a_live_player():
    rows, _feeder = _make_legacy_15p()
    with pytest.raises(AssertionError, match="ONE loss"):
        _check_full_run(15, rows, _p1, repair=False)
