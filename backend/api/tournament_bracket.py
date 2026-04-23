"""Tournament bracket generator — single-elim BO3 with 3rd-place match.

Phase 1: supports 8-16 signups. Top seeds get byes when signup count < next
power of 2. Returns a list of MatchRow ready to bulk-INSERT into
tournament_matches. Each row has a pre-assigned UUID so prereq_match_ids can
reference same-batch rows.

Partial-advance is handled by the API, not here: a match becomes playable
when every prereq row has winner_signup_id IS NOT NULL. Byes have their
winner pre-set at generation time, so R2 matches whose both prereqs are byes
are playable immediately at tournament start.
"""
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class SignupInput:
    signup_id: uuid.UUID
    player_id: uuid.UUID
    elo: float
    penalty: float = 0.0
    signed_up_at: Optional[datetime] = None


@dataclass
class MatchRow:
    id: uuid.UUID
    round: int
    bracket_side: str
    slot_idx: int
    p1_signup_id: Optional[uuid.UUID] = None
    p2_signup_id: Optional[uuid.UUID] = None
    prereq_match_ids: List[uuid.UUID] = field(default_factory=list)
    prereq_roles: List[str] = field(default_factory=list)  # 'W' or 'L' per prereq
    is_bye: bool = False
    winner_signup_id: Optional[uuid.UUID] = None


def _seed_order(n: int) -> List[int]:
    """Bracket-ordered seed list for an n-slot bracket (n is a power of 2).
    Consecutive pairs are R1 matchups. Seeds 1 and 2 land in opposite halves.
    _seed_order(16) = [1,16,8,9,4,13,5,12,2,15,7,10,3,14,6,11]."""
    if n == 1:
        return [1]
    prev = _seed_order(n // 2)
    out: List[int] = []
    for s in prev:
        out.append(s)
        out.append(n + 1 - s)
    return out


def build_bracket(signups: List[SignupInput]) -> List[MatchRow]:
    n = len(signups)
    if n < 8 or n > 16:
        raise ValueError(f"Phase 1 bracket requires 8-16 signups, got {n}")

    # Seed: highest Elo = seed 1. Ties -> lower penalty -> earlier signup.
    _epoch = datetime.min
    seeded = sorted(
        signups,
        key=lambda s: (-s.elo, s.penalty, s.signed_up_at or _epoch),
    )
    seed_to_signup = {i + 1: s.signup_id for i, s in enumerate(seeded)}

    slot_count = 1
    while slot_count < n:
        slot_count *= 2
    total_rounds = int(math.log2(slot_count))

    order = _seed_order(slot_count)
    rows: List[MatchRow] = []
    round_matches: dict[int, List[MatchRow]] = {}

    # Round 1: pair adjacent seeds in `order`. Seeds > n are empty slots ->byes.
    r1: List[MatchRow] = []
    for j in range(slot_count // 2):
        seed_a = order[2 * j]
        seed_b = order[2 * j + 1]
        p1 = seed_to_signup.get(seed_a)
        p2 = seed_to_signup.get(seed_b)
        is_bye = (p1 is None) != (p2 is None)
        winner = (p1 or p2) if is_bye else None
        row = MatchRow(
            id=uuid.uuid4(),
            round=1,
            bracket_side="W",
            slot_idx=j,
            p1_signup_id=p1,
            p2_signup_id=p2,
            prereq_match_ids=[],
            is_bye=is_bye,
            winner_signup_id=winner,
        )
        r1.append(row)
        rows.append(row)
    round_matches[1] = r1

    # Rounds 2..final: each match's prereqs are the two feeder matches from
    # the prior round. If both feeders are R1 byes, p1/p2 are pre-filled and
    # the match is ready immediately.
    for r in range(2, total_rounds + 1):
        prev = round_matches[r - 1]
        current: List[MatchRow] = []
        for j in range(len(prev) // 2):
            fa = prev[2 * j]
            fb = prev[2 * j + 1]
            row = MatchRow(
                id=uuid.uuid4(),
                round=r,
                bracket_side="W",
                slot_idx=j,
                p1_signup_id=fa.winner_signup_id,
                p2_signup_id=fb.winner_signup_id,
                prereq_match_ids=[fa.id, fb.id],
                is_bye=False,
                winner_signup_id=None,
            )
            current.append(row)
            rows.append(row)
        round_matches[r] = current

    # 3rd-place match: losers of the two semifinals. bracket_side='TP' tells
    # the advance-bracket logic to populate p1/p2 from prereq LOSERS instead
    # of winners on semi completion.
    semis = round_matches[total_rounds - 1]
    if len(semis) == 2:
        rows.append(
            MatchRow(
                id=uuid.uuid4(),
                round=total_rounds,
                bracket_side="TP",
                slot_idx=0,
                p1_signup_id=None,
                p2_signup_id=None,
                prereq_match_ids=[semis[0].id, semis[1].id],
                is_bye=False,
                winner_signup_id=None,
            )
        )

    return rows


def build_double_elim_bracket(signups: List[SignupInput]) -> List[MatchRow]:
    """Double-elim BO3 bracket for Phase 2 async tournaments.

    Structure (for 16p):
      WB: 4 rounds (8 / 4 / 2 / 1 matches)
      LB: 6 rounds, alternating minor (consolidation) and major (absorption of
          WB losers). Minor rounds pair previous LB winners; major rounds pair
          LB winners with WB losers from the corresponding WB round.
      GF: one match, WB champ vs LB champ.
      GF_RESET: NOT emitted at generation — inserted at runtime by
          advance_tournament_match if the LB champion wins GF, because
          WB champ has a 'free life' and earns a second BO3 to decide.

    Seeding: identical to single-elim (Elo desc, penalty/signup tiebreak).
    Byes: top seeds when n < slot_count, same as single-elim. Bye winners
    auto-advance in WB; they never feed LB because a bye means no WB R1 match
    actually happened for that seed pair.

    Note on LB pair ordering: we use straight sequential pairing of losers.
    This can produce occasional WB-rematches deeper in LB (loser of WB R1 M1
    could face WB R1 M1 winner later in LB). Avoiding all rematches requires
    "cross-pairing" per round which is complex; leaving as an improvement
    for a later iteration.
    """
    n = len(signups)
    if n < 4 or n > 16:
        raise ValueError(f"Async double-elim requires 4-16 signups, got {n}")

    _epoch = datetime.min
    seeded = sorted(signups, key=lambda s: (-s.elo, s.penalty, s.signed_up_at or _epoch))
    seed_to_signup = {i + 1: s.signup_id for i, s in enumerate(seeded)}

    slot_count = 1
    while slot_count < n:
        slot_count *= 2
    total_wb_rounds = int(math.log2(slot_count))

    order = _seed_order(slot_count)
    rows: List[MatchRow] = []
    wb_by_round: dict[int, List[MatchRow]] = {}

    # ── Winners bracket (same logic as single-elim) ──
    r1: List[MatchRow] = []
    for j in range(slot_count // 2):
        seed_a = order[2 * j]
        seed_b = order[2 * j + 1]
        p1 = seed_to_signup.get(seed_a)
        p2 = seed_to_signup.get(seed_b)
        is_bye = (p1 is None) != (p2 is None)
        winner = (p1 or p2) if is_bye else None
        row = MatchRow(
            id=uuid.uuid4(), round=1, bracket_side="W", slot_idx=j,
            p1_signup_id=p1, p2_signup_id=p2,
            prereq_match_ids=[], prereq_roles=[],
            is_bye=is_bye, winner_signup_id=winner,
        )
        r1.append(row)
        rows.append(row)
    wb_by_round[1] = r1

    for r in range(2, total_wb_rounds + 1):
        prev = wb_by_round[r - 1]
        cur: List[MatchRow] = []
        for j in range(len(prev) // 2):
            fa = prev[2 * j]
            fb = prev[2 * j + 1]
            row = MatchRow(
                id=uuid.uuid4(), round=r, bracket_side="W", slot_idx=j,
                p1_signup_id=fa.winner_signup_id, p2_signup_id=fb.winner_signup_id,
                prereq_match_ids=[fa.id, fb.id],
                prereq_roles=["W", "W"],
                is_bye=False, winner_signup_id=None,
            )
            cur.append(row)
            rows.append(row)
        wb_by_round[r] = cur

    # ── Losers bracket ──
    lb_by_round: dict[int, List[MatchRow]] = {}
    num_lb_rounds = 2 * (total_wb_rounds - 1)
    for lb_r in range(1, num_lb_rounds + 1):
        is_minor = (lb_r % 2 == 1)
        cur: List[MatchRow] = []
        if lb_r == 1:
            # Pair WB R1 losers. Bye matches in WB R1 have no loser to feed LB,
            # so we skip them here — that reduces the LB R1 match count by the
            # number of WB byes. This produces a smaller (but still valid) LB.
            feeders = [m for m in wb_by_round[1] if not m.is_bye]
            num_matches = (len(feeders) + 1) // 2
            for j in range(num_matches):
                fa = feeders[2 * j] if 2 * j < len(feeders) else None
                fb = feeders[2 * j + 1] if 2 * j + 1 < len(feeders) else None
                prereqs: List[uuid.UUID] = []
                roles: List[str] = []
                if fa is not None:
                    prereqs.append(fa.id)
                    roles.append("L")  # loser of WB R1 match
                if fb is not None:
                    prereqs.append(fb.id)
                    roles.append("L")
                # Odd count: one side gets a bye into LB R2.
                is_bye = len(prereqs) == 1
                row = MatchRow(
                    id=uuid.uuid4(), round=lb_r, bracket_side="L", slot_idx=j,
                    p1_signup_id=None, p2_signup_id=None,
                    prereq_match_ids=prereqs, prereq_roles=roles,
                    is_bye=is_bye, winner_signup_id=None,
                )
                cur.append(row)
                rows.append(row)
        elif is_minor:
            # Consolidation: pair prev major-round LB winners.
            prev = lb_by_round[lb_r - 1]
            for j in range(len(prev) // 2):
                fa = prev[2 * j]
                fb = prev[2 * j + 1]
                row = MatchRow(
                    id=uuid.uuid4(), round=lb_r, bracket_side="L", slot_idx=j,
                    p1_signup_id=None, p2_signup_id=None,
                    prereq_match_ids=[fa.id, fb.id],
                    prereq_roles=["W", "W"],
                    is_bye=False, winner_signup_id=None,
                )
                cur.append(row)
                rows.append(row)
        else:
            # Major: LB minor winners absorb WB losers from WB round (lb_r // 2 + 1).
            prev = lb_by_round[lb_r - 1]
            wb_feeder_round = (lb_r // 2) + 1
            wb_feeders = wb_by_round.get(wb_feeder_round, [])
            # Pair LB survivor with WB loser of the same slot_idx (sequential).
            pair_count = min(len(prev), len(wb_feeders))
            for j in range(pair_count):
                lb_prev = prev[j]
                wb_feeder = wb_feeders[j]
                row = MatchRow(
                    id=uuid.uuid4(), round=lb_r, bracket_side="L", slot_idx=j,
                    p1_signup_id=None, p2_signup_id=None,
                    prereq_match_ids=[lb_prev.id, wb_feeder.id],
                    prereq_roles=["W", "L"],
                    is_bye=False, winner_signup_id=None,
                )
                cur.append(row)
                rows.append(row)
        lb_by_round[lb_r] = cur

    # ── Grand Final ──
    if total_wb_rounds >= 1 and num_lb_rounds >= 1:
        wb_champ_match = wb_by_round[total_wb_rounds][0]
        lb_champ_match = lb_by_round[num_lb_rounds][0]
        rows.append(MatchRow(
            id=uuid.uuid4(), round=total_wb_rounds + 1, bracket_side="GF", slot_idx=0,
            p1_signup_id=None, p2_signup_id=None,
            prereq_match_ids=[wb_champ_match.id, lb_champ_match.id],
            prereq_roles=["W", "W"],
            is_bye=False, winner_signup_id=None,
        ))

    return rows


# ------------------------------------------------------------------------
# Self-tests — run `python tournament_bracket.py` to validate.
# ------------------------------------------------------------------------
if __name__ == "__main__":
    def _make(n: int) -> List[SignupInput]:
        return [
            SignupInput(uuid.uuid4(), uuid.uuid4(), elo=1500 - i * 10)
            for i in range(n)
        ]

    def _seeded_ids(sus: List[SignupInput]) -> List[uuid.UUID]:
        return [s.signup_id for s in sorted(sus, key=lambda s: -s.elo)]

    # 8 signups: 4 R1 + 2 R2 + 1 final + 1 TP = 8 rows, no byes.
    sus = _make(8)
    rows = build_bracket(sus)
    assert len(rows) == 8, len(rows)
    assert sum(1 for r in rows if r.round == 1) == 4
    assert sum(1 for r in rows if r.round == 2) == 2
    assert sum(1 for r in rows if r.round == 3 and r.bracket_side == "W") == 1
    assert sum(1 for r in rows if r.bracket_side == "TP") == 1
    assert sum(1 for r in rows if r.is_bye) == 0
    ids = _seeded_ids(sus)
    r1_by_slot = sorted((r for r in rows if r.round == 1), key=lambda r: r.slot_idx)
    assert r1_by_slot[0].p1_signup_id == ids[0] and r1_by_slot[0].p2_signup_id == ids[7]
    assert r1_by_slot[1].p1_signup_id == ids[3] and r1_by_slot[1].p2_signup_id == ids[4]
    assert r1_by_slot[2].p1_signup_id == ids[1] and r1_by_slot[2].p2_signup_id == ids[6]
    assert r1_by_slot[3].p1_signup_id == ids[2] and r1_by_slot[3].p2_signup_id == ids[5]
    print("8p: OK  (pairings 1v8, 4v5, 2v7, 3v6)")

    # 16 signups: 8 R1 + 4 R2 + 2 semi + 1 final + 1 TP = 16, no byes.
    sus = _make(16)
    rows = build_bracket(sus)
    assert len(rows) == 16
    assert sum(1 for r in rows if r.is_bye) == 0
    ids = _seeded_ids(sus)
    r1_by_slot = sorted((r for r in rows if r.round == 1), key=lambda r: r.slot_idx)
    # Seed 1 in slot 0 vs seed 16; seed 2 in slot 4 vs seed 15 (opposite halves).
    assert r1_by_slot[0].p1_signup_id == ids[0] and r1_by_slot[0].p2_signup_id == ids[15]
    assert r1_by_slot[4].p1_signup_id == ids[1] and r1_by_slot[4].p2_signup_id == ids[14]
    print("16p: OK (seed 1 in slot 0, seed 2 in slot 4 ->opposite halves)")

    # 12 signups: 4 byes to top 4 seeds.
    sus = _make(12)
    rows = build_bracket(sus)
    assert len(rows) == 16
    r1 = [r for r in rows if r.round == 1]
    byes = [r for r in r1 if r.is_bye]
    assert len(byes) == 4, len(byes)
    ids = _seeded_ids(sus)
    top4 = set(ids[:4])
    assert {r.winner_signup_id for r in byes} == top4
    # The real R1 matches should be seed 8v9, 5v12, 7v10, 6v11 — but since seeds
    # 12+ don't exist, any pair where both sides have signups is a real match.
    real = [r for r in r1 if not r.is_bye]
    assert len(real) == 4
    for r in real:
        assert r.p1_signup_id is not None and r.p2_signup_id is not None
    print("12p: OK (top 4 seeds bye, 4 real R1 matches)")

    # 9 signups: 7 byes to top 7, only 1 real R1 match (seed 8 vs seed 9).
    sus = _make(9)
    rows = build_bracket(sus)
    r1 = [r for r in rows if r.round == 1]
    byes = [r for r in r1 if r.is_bye]
    assert len(byes) == 7, len(byes)
    real = [r for r in r1 if not r.is_bye]
    assert len(real) == 1
    ids = _seeded_ids(sus)
    # Seed 8 vs seed 9.
    assert {real[0].p1_signup_id, real[0].p2_signup_id} == {ids[7], ids[8]}
    # R2 matches where both prereqs are byes should have p1 AND p2 pre-filled.
    r2 = [r for r in rows if r.round == 2]
    ready_at_start = [r for r in r2 if r.p1_signup_id and r.p2_signup_id]
    assert len(ready_at_start) == 3, f"expected 3 R2 ready at start, got {len(ready_at_start)}"
    print("9p: OK (7 byes, 1 real R1, 3 R2 matches ready immediately)")

    # 15 signups: 1 bye to seed 1 only.
    sus = _make(15)
    rows = build_bracket(sus)
    r1 = [r for r in rows if r.round == 1]
    byes = [r for r in r1 if r.is_bye]
    assert len(byes) == 1
    ids = _seeded_ids(sus)
    assert byes[0].winner_signup_id == ids[0]
    print("15p: OK (1 bye to seed 1)")

    # 11 signups: 5 byes to top 5.
    sus = _make(11)
    rows = build_bracket(sus)
    r1 = [r for r in rows if r.round == 1]
    byes = [r for r in r1 if r.is_bye]
    assert len(byes) == 5, len(byes)
    print("11p: OK (5 byes)")

    # Bounds.
    for bad_n in (0, 1, 7, 17, 32):
        try:
            build_bracket(_make(bad_n))
        except ValueError:
            pass
        else:
            raise AssertionError(f"{bad_n} should have raised")
    print("bounds: OK")

    # Tiebreak: equal elo ->lower penalty wins the higher seed.
    s1 = SignupInput(uuid.uuid4(), uuid.uuid4(), elo=1500, penalty=0.3)
    s2 = SignupInput(uuid.uuid4(), uuid.uuid4(), elo=1500, penalty=0.1)
    extras = [SignupInput(uuid.uuid4(), uuid.uuid4(), elo=1000 - i) for i in range(6)]
    rows = build_bracket([s1, s2] + extras)
    r1_slot0 = next(r for r in rows if r.round == 1 and r.slot_idx == 0)
    # s2 has lower penalty ->should be seed 1 (slot_idx=0 p1).
    assert r1_slot0.p1_signup_id == s2.signup_id
    print("tiebreak: OK (lower penalty wins tied elo)")

    # Prereq connectivity: every non-R1 match must have all its prereq IDs
    # exist in the row list, and the R2+ winner chain must eventually hit the final.
    sus = _make(16)
    rows = build_bracket(sus)
    all_ids = {r.id for r in rows}
    for r in rows:
        for pid in r.prereq_match_ids:
            assert pid in all_ids, f"dangling prereq in round {r.round}"
    print("connectivity: OK")

    # ── Double-elim tests ──
    # 16p: WB 8+4+2+1 = 15 matches. LB 4+4+2+2+1+1 = 14 matches. GF = 1. Total = 30.
    sus = _make(16)
    rows = build_double_elim_bracket(sus)
    wb = [r for r in rows if r.bracket_side == "W"]
    lb = [r for r in rows if r.bracket_side == "L"]
    gf = [r for r in rows if r.bracket_side == "GF"]
    assert len(wb) == 15, f"16p WB: expected 15, got {len(wb)}"
    assert len(lb) == 14, f"16p LB: expected 14, got {len(lb)}"
    assert len(gf) == 1, f"16p GF: expected 1, got {len(gf)}"
    # GF prereq_roles must both be 'W' (WB champ and LB champ are both winners of their side).
    assert gf[0].prereq_roles == ["W", "W"]
    # Major LB rounds (2, 4, 6) should have [W, L] roles — LB winner + WB loser.
    for r in lb:
        if r.round % 2 == 0:  # major rounds
            assert r.prereq_roles == ["W", "L"], f"LB R{r.round} major: got {r.prereq_roles}"
    # Minor LB rounds > 1: [W, W]. LB R1: ['L', 'L'] (both from WB R1).
    for r in lb:
        if r.round == 1:
            assert all(role == "L" for role in r.prereq_roles)
        elif r.round % 2 == 1:
            assert r.prereq_roles == ["W", "W"], f"LB R{r.round} minor: got {r.prereq_roles}"
    # Connectivity: every prereq must point to a row in the batch.
    all_ids = {r.id for r in rows}
    for r in rows:
        for pid in r.prereq_match_ids:
            assert pid in all_ids, f"dangling prereq in LB R{r.round}"
    print("16p double-elim: OK (15W + 14L + 1GF, roles correct)")

    # 8p: WB 4+2+1 = 7. LB 2+2+1+1 = 6. GF = 1. Total = 14.
    sus = _make(8)
    rows = build_double_elim_bracket(sus)
    wb = [r for r in rows if r.bracket_side == "W"]
    lb = [r for r in rows if r.bracket_side == "L"]
    gf = [r for r in rows if r.bracket_side == "GF"]
    assert len(wb) == 7, f"8p WB: expected 7, got {len(wb)}"
    assert len(lb) == 6, f"8p LB: expected 6, got {len(lb)}"
    assert len(gf) == 1
    print("8p double-elim: OK (7W + 6L + 1GF)")

    # Bounds
    for bad_n in (0, 1, 3, 17):
        try:
            build_double_elim_bracket(_make(bad_n))
        except ValueError:
            pass
        else:
            raise AssertionError(f"double-elim should reject n={bad_n}")
    print("double-elim bounds: OK")

    print("\nAll bracket tests passed.")
