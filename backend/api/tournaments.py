"""Tournament endpoints + lifecycle helpers (Phase 1: sync single-elim BO3).

Router is mounted at /api/v1/tournaments in main.py. Lifecycle transitions
(voting -> locked -> running -> completed) are driven by tournament_tick()
which runs as a background asyncio task from main.py's lifespan.

Tournament match reporting piggybacks on the existing /api/v1/matches
pipeline. When a match becomes ready, the server creates a ranked_series
with (is_tournament=True, tournament_id=...) and stores its id on
tournament_matches.series_id. The client reports the BO3 normally. When
the series completes in main.py's match handler, it calls
advance_tournament_match(series_id) — see the hook instructions at the
bottom of this file for where that wires into main.py.
"""
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import and_, func, or_, select, text, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session, get_db
from models import (
    GlickoRating,
    Player,
    PlayerTournamentPenalty,
    RankedSeries,
    Tournament,
    TournamentForceVote,
    TournamentMatch,
    TournamentSignup,
    TournamentTimeVote,
)
from schemas import (
    TournamentCurrentResponse,
    TournamentForceVoteRequest,
    TournamentMatchEntry,
    TournamentPenaltyResponse,
    TournamentReadyRequest,
    TournamentSignupEntry,
    TournamentSignupRequest,
    TournamentTimeSlotTally,
    TournamentTimeVoteRequest,
)
from tournament_bracket import SignupInput, build_bracket, build_double_elim_bracket

router = APIRouter(prefix="/api/v1/tournaments", tags=["Tournaments"])


# ── Constants ─────────────────────────────────────────────────────

READY_STALE_SECONDS = 60          # ready_at older than this = not ready
MATCH_READY_GRACE_SECONDS = 300   # 5 min to ready up at match start
FORCE_START_WINDOW_MINUTES = 30   # all force votes within this window
VOTE_SLOT_INTERVAL_HOURS = 6      # 8 slots within ±24h of default_start
PRIZE_GOLD = {"full": (500, 300, 60), "sixty": (300, 180, 36), "thirty": (150, 90, 18), "none": (0, 0, 0)}
PRIZE_XP = {"full": (2500, 1500, 75), "sixty": (1500, 900, 45), "thirty": (750, 450, 23), "none": (0, 0, 0)}
GLICKO2_DEFAULT_RATING = 1500.0

# Weekly scheduling. Default slot = Saturday 12:00 America/Los_Angeles.
# PT_ZONE handles PST/PDT automatically via zoneinfo so the 12:00 local time
# stays stable across DST. lock_at = default - 6h, so voting closes 6h before start.
PT_ZONE = ZoneInfo("America/Los_Angeles")
TOURNAMENT_WEEKDAY = 5   # Saturday (Monday=0, Sunday=6)
TOURNAMENT_HOUR_PT = 12  # 12:00 PT
LOCK_OFFSET_HOURS = 6    # lock_at = default - 6h

# Async tournament knobs (Phase 2).
ASYNC_SIGNUP_DAYS = 7            # signups open for 7 days before lock
ASYNC_MATCH_DEADLINE_DAYS = 7    # each match has a 7-day deadline
# 16p async double-elim has a 9-match LB path — at 7 days/match that's up to
# 9 weeks worst-case. In practice most brackets finish faster because players
# don't wait the full 7 days. Set cadence to 42 days (6 weeks) so back-to-back
# tournaments typically don't overlap. If the prior one still has stragglers,
# the new signup window starts and people can join both.
ASYNC_CADENCE_DAYS = 42


# ── Helpers ───────────────────────────────────────────────────────

async def _get_player_by_steam(db: AsyncSession, steam_id: str) -> Player:
    result = await db.execute(select(Player).where(Player.steam_id == steam_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


async def _get_tournament(db: AsyncSession, tournament_id: uuid.UUID) -> Tournament:
    result = await db.execute(select(Tournament).where(Tournament.id == tournament_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return t


def _offered_time_slots(default_start_ts: datetime) -> List[datetime]:
    """8 discrete slots at 6-hour intervals within ±24h of default_start_ts.
    Returns e.g. [default-24h, default-18h, ..., default, ..., default+18h].
    The default_start_ts itself is always one of the 8 options."""
    slots = []
    for offset_h in (-24, -18, -12, -6, 0, 6, 12, 18):
        slots.append(default_start_ts + timedelta(hours=offset_h))
    return slots


async def _recompute_player_penalty(db: AsyncSession, player_id: uuid.UUID) -> float:
    """Rolling 90-day show rate with linear decay.
      raw_penalty = sum(decay(age) for each miss) / sum(decay(age) for each signup)
      decay(d) = max(0, 1 - d/90)
    Upserts the cache row, returns the numeric penalty pct (0..1)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=90)
    q = text("""
        SELECT signed_up_at, forfeited
        FROM tournament_signups
        WHERE player_id = :pid AND signed_up_at >= :cutoff
    """)
    rows = (await db.execute(q, {"pid": player_id, "cutoff": cutoff})).all()
    total_weight = 0.0
    miss_weight = 0.0
    signups_90d = 0
    missed_90d = 0
    latest_signup_at = None
    no_show_last_at = None
    for signed_up_at, forfeited in rows:
        age_d = (now - signed_up_at).total_seconds() / 86400
        w = max(0.0, 1.0 - age_d / 90.0)
        if w <= 0:
            continue
        total_weight += w
        signups_90d += 1
        if latest_signup_at is None or signed_up_at > latest_signup_at:
            latest_signup_at = signed_up_at
        if forfeited:
            miss_weight += w
            missed_90d += 1
            if no_show_last_at is None or signed_up_at > no_show_last_at:
                no_show_last_at = signed_up_at
    pct = (miss_weight / total_weight) if total_weight > 0 else 0.0

    stmt = pg_insert(PlayerTournamentPenalty).values(
        player_id=player_id,
        cached_penalty_pct=pct,
        signups_90d=signups_90d,
        missed_90d=missed_90d,
        latest_signup_at=latest_signup_at,
        no_show_last_at=no_show_last_at,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=[PlayerTournamentPenalty.player_id],
        set_={
            "cached_penalty_pct": pct,
            "signups_90d": signups_90d,
            "missed_90d": missed_90d,
            "latest_signup_at": latest_signup_at,
            "no_show_last_at": no_show_last_at,
            "updated_at": now,
        },
    )
    await db.execute(stmt)
    return pct


async def _recompute_speculation(db: AsyncSession, tournament_id: uuid.UUID) -> None:
    """Re-sort all signups for a tournament by (penalty ASC, signed_up_at ASC)
    and mark rows beyond max_players as speculative. Runs on every signup/unsignup."""
    t = await _get_tournament(db, tournament_id)
    q = select(TournamentSignup).where(TournamentSignup.tournament_id == tournament_id)
    rows = (await db.execute(q)).scalars().all()
    rows_sorted = sorted(rows, key=lambda r: (r.penalty_at_signup, r.signed_up_at))
    for i, r in enumerate(rows_sorted):
        r.is_speculative = i >= t.max_players
    # Session flush on return; caller commits.


async def _get_signup_for(db: AsyncSession, tournament_id: uuid.UUID, player_id: uuid.UUID) -> Optional[TournamentSignup]:
    q = select(TournamentSignup).where(
        and_(TournamentSignup.tournament_id == tournament_id,
             TournamentSignup.player_id == player_id)
    )
    return (await db.execute(q)).scalar_one_or_none()


def _bracket_tag(side: Optional[str]) -> str:
    return {"W": "WB", "L": "LB", "GF": "GF", "GF_RESET": "GF Reset", "TP": "TP"}.get(side or "", side or "")


def _compute_progress_labels(tournament: Tournament, all_matches: list) -> dict:
    """For each signup_id in the bracket, return a one-word label that describes
    where they are in the tournament. Called in the /current response builder
    so it runs once per request, not per signup row."""
    # Group matches by signup (each match contributes to p1 and p2).
    by_sig: dict[uuid.UUID, list] = {}
    for m in all_matches:
        for sid in (m.p1_signup_id, m.p2_signup_id):
            if sid is None: continue
            by_sig.setdefault(sid, []).append(m)
    labels: dict[uuid.UUID, str] = {}
    for sid, matches in by_sig.items():
        matches.sort(key=lambda m: m.round)
        # Pending / ready / active match the player still has to play.
        next_m = next((m for m in matches
                       if m.status in ("ready", "active", "pending")
                       and m.winner_signup_id is None), None)
        if next_m is not None:
            labels[sid] = f"{_bracket_tag(next_m.bracket_side)} R{next_m.round}"
            continue
        # No pending match — either eliminated or finished in top 3. Walk
        # backward through completed matches to find their final outcome.
        last_m = None
        for m in reversed(matches):
            if m.status in ("completed", "forfeit", "double_forfeit", "bye_auto"):
                last_m = m
                break
        if last_m is None:
            labels[sid] = "signed up"
            continue
        won = last_m.winner_signup_id == sid
        if won:
            # Won their last match but nothing pending → tournament over for them
            # as a winner. In double-elim the GF / GF_RESET winner is CHAMPION.
            if last_m.bracket_side in ("GF", "GF_RESET"):
                labels[sid] = "CHAMPION"
            else:
                labels[sid] = "advanced"  # rare: won a match but no next — transient state
        else:
            # Lost their last match. For double-elim, losing the LB final or
            # GF (without bracket-reset) → 2nd/3rd place; losing earlier = eliminated.
            labels[sid] = f"eliminated {_bracket_tag(last_m.bracket_side)} R{last_m.round}"
    return labels


async def _build_current_response(db: AsyncSession, t: Tournament, caller_player: Optional[Player]) -> TournamentCurrentResponse:
    # Signups + display names
    sq = text("""
        SELECT s.id, p.steam_id, p.display_name, s.signed_up_at, s.is_speculative,
               s.seed, s.penalty_at_signup, s.ready_at, s.forfeited, s.placed_rank
        FROM tournament_signups s
        JOIN players p ON p.id = s.player_id
        WHERE s.tournament_id = :tid
        ORDER BY s.is_speculative, s.penalty_at_signup, s.signed_up_at
    """)
    rows = (await db.execute(sq, {"tid": t.id})).all()
    now = datetime.now(timezone.utc)

    # Compute per-signup bracket progress labels (only meaningful once the
    # tournament is running/completed — voting/locked phases have no play yet).
    progress_labels: dict = {}
    if t.status in ("running", "completed"):
        allmq = select(TournamentMatch).where(TournamentMatch.tournament_id == t.id)
        progress_labels = _compute_progress_labels(t, (await db.execute(allmq)).scalars().all())

    signups = [
        TournamentSignupEntry(
            signup_id=r.id,
            steam_id=r.steam_id,
            display_name=r.display_name,
            signed_up_at=r.signed_up_at,
            is_speculative=r.is_speculative,
            seed=r.seed,
            penalty_at_signup=r.penalty_at_signup,
            ready=(r.ready_at is not None and (now - r.ready_at).total_seconds() <= READY_STALE_SECONDS),
            forfeited=r.forfeited,
            placed_rank=r.placed_rank,
            progress_label=progress_labels.get(r.id),
        ) for r in rows
    ]

    # Matches + opponent names
    mq = text("""
        SELECT m.id, m.round, m.bracket_side, m.slot_idx,
               m.p1_signup_id, m.p2_signup_id, m.prereq_match_ids,
               m.is_bye, m.status, m.series_id, m.winner_signup_id,
               m.ready_deadline_at, m.deadline_at, m.started_at, m.ended_at,
               m.photon_room_name,
               p1.display_name AS p1_name, p2.display_name AS p2_name,
               rs.p1_series_wins, rs.p2_series_wins,
               rs.player1_id AS rs_p1_player_id, s1.player_id AS s1_player_id
        FROM tournament_matches m
        LEFT JOIN tournament_signups s1 ON s1.id = m.p1_signup_id
        LEFT JOIN players p1 ON p1.id = s1.player_id
        LEFT JOIN tournament_signups s2 ON s2.id = m.p2_signup_id
        LEFT JOIN players p2 ON p2.id = s2.player_id
        LEFT JOIN ranked_series rs ON rs.id = m.series_id
        WHERE m.tournament_id = :tid
        ORDER BY m.round, m.bracket_side, m.slot_idx
    """)
    mrows = (await db.execute(mq, {"tid": t.id})).all()
    matches = []
    for r in mrows:
        # ranked_series stores p1/p2 by player_id; map back to signup_id ordering.
        p1w, p2w = None, None
        if r.series_id and r.rs_p1_player_id:
            if r.rs_p1_player_id == r.s1_player_id:
                p1w, p2w = r.p1_series_wins, r.p2_series_wins
            else:
                p1w, p2w = r.p2_series_wins, r.p1_series_wins
        matches.append(TournamentMatchEntry(
            match_id=r.id, round=r.round, bracket_side=r.bracket_side, slot_idx=r.slot_idx,
            p1_signup_id=r.p1_signup_id, p2_signup_id=r.p2_signup_id,
            p1_display_name=r.p1_name, p2_display_name=r.p2_name,
            prereq_match_ids=list(r.prereq_match_ids or []),
            is_bye=r.is_bye, status=r.status, series_id=r.series_id,
            winner_signup_id=r.winner_signup_id,
            p1_series_wins=p1w, p2_series_wins=p2w,
            ready_deadline_at=r.ready_deadline_at,
            deadline_at=r.deadline_at,
            started_at=r.started_at, ended_at=r.ended_at,
            photon_room_name=r.photon_room_name,
        ))

    # Caller-specific fields
    my_signup_id = None
    my_votes: List[datetime] = []
    my_force_at = None
    my_ready = False
    my_penalty = 0.0
    my_discord = False
    tallies: List[TournamentTimeSlotTally] = []
    if caller_player:
        my_discord = caller_player.discord_id is not None
        my_sig = await _get_signup_for(db, t.id, caller_player.id)
        if my_sig:
            my_signup_id = my_sig.id
            my_ready = (my_sig.ready_at is not None and
                        (now - my_sig.ready_at).total_seconds() <= READY_STALE_SECONDS)
        pen_row = (await db.execute(
            select(PlayerTournamentPenalty).where(PlayerTournamentPenalty.player_id == caller_player.id)
        )).scalar_one_or_none()
        my_penalty = pen_row.cached_penalty_pct if pen_row else 0.0
        # My time votes
        vq = select(TournamentTimeVote.slot_ts).where(and_(
            TournamentTimeVote.tournament_id == t.id,
            TournamentTimeVote.player_id == caller_player.id,
        ))
        my_votes = [row[0] for row in (await db.execute(vq)).all()]
        fq = select(TournamentForceVote.voted_at).where(and_(
            TournamentForceVote.tournament_id == t.id,
            TournamentForceVote.player_id == caller_player.id,
        ))
        my_force_at = (await db.execute(fq)).scalar_one_or_none()
        # Tallies only after caller has voted (prevents snooping pre-vote).
        if my_votes:
            tq = text("""
                SELECT slot_ts, COUNT(*) AS votes
                FROM tournament_time_votes
                WHERE tournament_id = :tid
                GROUP BY slot_ts ORDER BY slot_ts
            """)
            tallies = [TournamentTimeSlotTally(slot_ts=r.slot_ts, votes=r.votes)
                       for r in (await db.execute(tq, {"tid": t.id})).all()]

    # Force vote count
    fvc = (await db.execute(
        select(func.count()).select_from(TournamentForceVote).where(
            TournamentForceVote.tournament_id == t.id)
    )).scalar_one()

    return TournamentCurrentResponse(
        tournament_id=t.id, status=t.status, kind=t.kind,
        default_start_ts=t.default_start_ts,
        scheduled_start_ts=t.scheduled_start_ts,
        lock_at=t.lock_at, voting_closes_at=t.voting_closes_at,
        started_at=t.started_at, ended_at=t.ended_at,
        min_players=t.min_players, max_players=t.max_players,
        signups=signups, matches=matches,
        my_signup_id=my_signup_id, my_votes=my_votes,
        my_force_vote_at=my_force_at, my_ready=my_ready,
        my_penalty_pct=my_penalty, my_discord_linked=my_discord,
        time_slot_options=_offered_time_slots(t.default_start_ts),
        time_slot_tallies=tallies, force_vote_count=fvc,
        photon_region=t.photon_region,
    )


# ── Lifecycle ─────────────────────────────────────────────────────

async def lock_tournament(db: AsyncSession, t: Tournament) -> None:
    """Transition voting -> locked. Picks scheduled_start_ts from top-voted slot
    (random among ties), snapshots Elo for seeding, generates bracket. If
    signup count < min_players, push lock_at + start back by a week instead
    of cancelling — gives the community another full signup window to
    rally rather than skipping the cadence outright."""
    now = datetime.now(timezone.utc)

    # Confirmed signups only (is_speculative=False).
    q = select(TournamentSignup).where(and_(
        TournamentSignup.tournament_id == t.id,
        TournamentSignup.is_speculative == False,  # noqa: E712
    ))
    signups = (await db.execute(q)).scalars().all()

    if len(signups) < t.min_players:
        # Pushback path. Status stays "voting" so the cron re-enters this
        # function next week. lock_at, voting_closes_at, default_start_ts
        # all advance by 7 days. For async tournaments default_start_ts
        # equals lock_at (they begin the moment signups close); for sync,
        # default_start_ts is a separate scheduled time we also push.
        push = timedelta(days=7)
        t.lock_at = now + push
        t.voting_closes_at = t.lock_at
        if t.kind == "async":
            t.default_start_ts = t.lock_at
        else:
            # Sync: keep the same time-of-day, slide the date by 7 days.
            t.default_start_ts = t.default_start_ts + push
        # Wipe any tallied votes whose slot_ts is now in the past so the
        # next lock attempt isn't biased toward a stale slot.
        await db.execute(
            text("DELETE FROM tournament_time_votes "
                 "WHERE tournament_id = :tid AND slot_ts <= :now"),
            {"tid": t.id, "now": now},
        )
        print(f"[TOURNAMENT] {t.id} only {len(signups)}/{t.min_players} "
              f"confirmed signups — pushing lock_at to {t.lock_at.isoformat()} "
              f"(kind={t.kind}). Status stays voting.")
        return

    # Prize tier
    n = len(signups)
    if n >= 16:
        t.prize_tier = "full"
    elif n >= 12:
        t.prize_tier = "sixty"
    else:
        t.prize_tier = "thirty"

    # Pick the tournament's canonical Photon region as the mode of all signups'
    # region_at_signup values (alphabetical tiebreak on count ties). All
    # auto-connect handoffs will pin both clients to this region, so cross-
    # region brackets always land in the same Photon room. Falls back to None
    # if nobody reported a region — clients then use whichever region they're
    # currently on.
    region_counts: dict[str, int] = {}
    for s in signups:
        r = s.region_at_signup
        if not r:
            continue
        region_counts[r] = region_counts.get(r, 0) + 1
    if region_counts:
        top_count = max(region_counts.values())
        top_regions = sorted(r for r, c in region_counts.items() if c == top_count)
        t.photon_region = top_regions[0]
    else:
        # Zero signups reported a region (older clients pre-region-tracking, or
        # failed Photon region resolution). Fall back to "us" so auto-connect
        # still converges on one region. Clients that can't reach "us" will
        # forfeit but the bracket stays consistent. (Review #9)
        t.photon_region = "us"

    # Pick scheduled_start_ts from vote tallies (highest count wins, random tiebreak).
    tq = text("""
        SELECT slot_ts, COUNT(*) AS votes
        FROM tournament_time_votes
        WHERE tournament_id = :tid
        GROUP BY slot_ts ORDER BY votes DESC
    """)
    tallies = (await db.execute(tq, {"tid": t.id})).all()
    offered = _offered_time_slots(t.default_start_ts)
    if tallies:
        top_votes = tallies[0].votes
        top_slots = [r.slot_ts for r in tallies if r.votes == top_votes]
        t.scheduled_start_ts = random.choice(top_slots)
    else:
        t.scheduled_start_ts = t.default_start_ts

    # Snapshot Elo per signup.
    eq = text("""
        SELECT ts.id AS signup_id, ts.player_id,
               COALESCE(gr.rating, :default_rating) AS rating
        FROM tournament_signups ts
        LEFT JOIN glicko_ratings gr ON gr.player_id = ts.player_id
        WHERE ts.tournament_id = :tid AND ts.is_speculative = FALSE
    """)
    erows = (await db.execute(eq, {"tid": t.id, "default_rating": GLICKO2_DEFAULT_RATING})).all()
    bracket_inputs = [SignupInput(
        signup_id=r.signup_id, player_id=r.player_id, elo=r.rating,
        penalty=0.0, signed_up_at=None,
    ) for r in erows]

    # Persist cached_elo_at_lock + seed per signup.
    # build_bracket sorts internally; we re-derive seeds after by elo rank.
    sorted_ins = sorted(bracket_inputs, key=lambda s: -s.elo)
    signup_by_id = {s.id: s for s in signups}
    for seed_idx, bi in enumerate(sorted_ins, start=1):
        sig = signup_by_id[bi.signup_id]
        sig.cached_elo_at_lock = bi.elo
        sig.seed = seed_idx

    # Build bracket rows. Sync and async both default to double-elim now;
    # legacy single-elim tournaments (format=single_elim_bo3) still work.
    if t.format == "double_elim_bo3":
        match_rows = build_double_elim_bracket(bracket_inputs)
    else:
        match_rows = build_bracket(bracket_inputs)

    # Insert matches.
    for mr in match_rows:
        db.add(TournamentMatch(
            id=mr.id,
            tournament_id=t.id,
            round=mr.round,
            bracket_side=mr.bracket_side,
            slot_idx=mr.slot_idx,
            p1_signup_id=mr.p1_signup_id,
            p2_signup_id=mr.p2_signup_id,
            prereq_match_ids=mr.prereq_match_ids,
            prereq_roles=getattr(mr, "prereq_roles", []) or [],
            is_bye=mr.is_bye,
            status="bye_auto" if mr.is_bye else "pending",
            winner_signup_id=mr.winner_signup_id,
        ))

    t.status = "locked"
    t.locked_at = now
    # Async tournaments have no scheduled_start delay — they begin the moment
    # signups lock. Overwrite scheduled_start_ts so the tick's locked->running
    # transition fires on the next iteration instead of waiting for a future
    # start time that doesn't exist for async.
    if t.kind == "async":
        t.scheduled_start_ts = now
    # Speculative signups are KEPT after lock so they can backfill if a
    # confirmed player drops out before the tournament starts running. The
    # bracket was already built from confirmed signups only, so they're an
    # inert pool — see _handle_leaving_signup for the promotion path.

    # Auto-clear any ranked blocks between confirmed tournament participants. A
    # player's block prevents the normal ranked queue from pairing them, but the
    # tournament bracket generator doesn't consult player_blocks — so without
    # this sweep, two players who'd blocked each other could still land in the
    # same tournament match with no way for the auto-connect to fail gracefully.
    # Clearing the block row for the duration of the tournament (and beyond —
    # they can re-block manually if they want after the tournament is over) is
    # the least-surprising behavior: if you signed up, you're opting in to
    # playing whoever else signed up.
    confirmed_player_ids = [s.player_id for s in signups]
    if len(confirmed_player_ids) >= 2:
        cleared = await db.execute(text("""
            DELETE FROM player_blocks
             WHERE blocker_id = ANY(:pids) AND blocked_id = ANY(:pids)
         RETURNING blocker_id, blocked_id
        """), {"pids": confirmed_player_ids})
        cleared_rows = cleared.fetchall()
        if cleared_rows:
            print(f"[TOURNAMENT] Auto-cleared {len(cleared_rows)} block(s) for "
                  f"tournament {t.id}: {cleared_rows}")


async def start_tournament(db: AsyncSession, t: Tournament) -> None:
    """Transition locked -> running. First-round matches (including those with
    pre-filled p1/p2 from bye propagation) become ready."""
    now = datetime.now(timezone.utc)
    t.status = "running"
    t.started_at = now
    await _activate_ready_matches(db, t.id)


async def _activate_ready_matches(db: AsyncSession, tournament_id: uuid.UUID) -> None:
    """Find pending matches whose prereqs are all resolved, populate p1/p2
    from upstream winners (or losers, for TP/LB), create ranked_series, flip
    status to 'ready'. For async tournaments, also sets deadline_at."""
    now = datetime.now(timezone.utc)
    t = await _get_tournament(db, tournament_id)
    q = select(TournamentMatch).where(and_(
        TournamentMatch.tournament_id == tournament_id,
        TournamentMatch.status == "pending",
    ))
    pending = (await db.execute(q)).scalars().all()
    if not pending:
        return

    # Pre-fetch all matches for prereq lookup.
    allq = select(TournamentMatch).where(TournamentMatch.tournament_id == tournament_id)
    by_id = {m.id: m for m in (await db.execute(allq)).scalars().all()}

    def _loser_of(pre: TournamentMatch) -> Optional[uuid.UUID]:
        if pre.winner_signup_id is None:
            return None
        return pre.p1_signup_id if pre.winner_signup_id == pre.p2_signup_id else pre.p2_signup_id

    for m in pending:
        prereq_ids = list(m.prereq_match_ids or [])
        if prereq_ids:
            prereqs = [by_id[pid] for pid in prereq_ids if pid in by_id]
            if any(p.winner_signup_id is None for p in prereqs):
                continue
            roles = list(m.prereq_roles or [])
            # Resolve each prereq's contribution by its role tag, falling back
            # to the legacy bracket_side defaults when prereq_roles is empty
            # (sync tournaments built before the column existed).
            resolved: List[Optional[uuid.UUID]] = []
            for i, pre in enumerate(prereqs):
                role = roles[i] if i < len(roles) else None
                if role == "L":
                    resolved.append(_loser_of(pre))
                elif role == "W":
                    resolved.append(pre.winner_signup_id)
                else:
                    # Legacy fallback for single-elim TP / W.
                    if m.bracket_side == "TP":
                        resolved.append(_loser_of(pre))
                    else:
                        resolved.append(pre.winner_signup_id)
            m.p1_signup_id = resolved[0] if len(resolved) >= 1 else None
            m.p2_signup_id = resolved[1] if len(resolved) >= 2 else None

        # Forfeit detection: if either signup is forfeited, auto-advance the other.
        p1_sig = None
        p2_sig = None
        if m.p1_signup_id:
            p1_sig = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == m.p1_signup_id))).scalar_one_or_none()
        if m.p2_signup_id:
            p2_sig = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == m.p2_signup_id))).scalar_one_or_none()
        p1_ff = p1_sig is not None and p1_sig.forfeited
        p2_ff = p2_sig is not None and p2_sig.forfeited
        if p1_ff and not p2_ff and m.p2_signup_id:
            m.winner_signup_id = m.p2_signup_id
            m.status = "forfeit"
            m.ended_at = now
            continue
        if p2_ff and not p1_ff and m.p1_signup_id:
            m.winner_signup_id = m.p1_signup_id
            m.status = "forfeit"
            m.ended_at = now
            continue
        if p1_ff and p2_ff:
            # Both no-showed. Downstream matches need a winner_signup_id to
            # keep progressing. Award to the LOWER-penalty player (more
            # reliable historically) as a fair tiebreak; strict-alphabetical
            # signup_id UUID as last-resort deterministic fallback if both
            # have equal penalty. (Flag #3 / Review #5)
            p1_sig = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == m.p1_signup_id))).scalar_one_or_none()
            p2_sig = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == m.p2_signup_id))).scalar_one_or_none()
            winner_id = m.p1_signup_id
            if p1_sig and p2_sig:
                if p2_sig.penalty_at_signup < p1_sig.penalty_at_signup:
                    winner_id = m.p2_signup_id
                elif p1_sig.penalty_at_signup == p2_sig.penalty_at_signup and str(m.p2_signup_id) < str(m.p1_signup_id):
                    winner_id = m.p2_signup_id
            m.status = "double_forfeit"
            m.winner_signup_id = winner_id
            m.ended_at = now
            continue

        if not (m.p1_signup_id and m.p2_signup_id):
            continue  # shouldn't happen — defensive

        # Create ranked_series with tournament flags.
        player_ids = [
            (await db.execute(select(TournamentSignup.player_id).where(TournamentSignup.id == m.p1_signup_id))).scalar_one(),
            (await db.execute(select(TournamentSignup.player_id).where(TournamentSignup.id == m.p2_signup_id))).scalar_one(),
        ]
        series = RankedSeries(
            id=uuid.uuid4(),
            player1_id=player_ids[0],
            player2_id=player_ids[1],
            p1_series_wins=0, p2_series_wins=0,
            status="active",
            tournament_id=tournament_id,
            is_tournament=True,
            created_at=now,
        )
        db.add(series)
        m.series_id = series.id
        m.status = "ready"
        # Server-issued Photon room name. Both clients pull this from
        # /api/v1/tournaments/current rather than deriving it from match.id
        # locally — kills the dual-derivation race that could land them
        # in different rooms if the string-split logic ever drifted.
        # Format kept compatible with the legacy "sct-<12hex>" convention
        # so older clients that still derive client-side won't see a
        # mismatch (they'll arrive at the same room name).
        m.photon_room_name = "sct-" + str(m.id).replace("-", "")[:12]
        # Sync: 5-min ready-up window. Async: 7-day match deadline. The tick
        # enforces both via _apply_no_show_forfeits + the async deadline path.
        if t.kind == "async":
            m.deadline_at = now + timedelta(days=ASYNC_MATCH_DEADLINE_DAYS)
            m.ready_deadline_at = m.deadline_at
        else:
            m.ready_deadline_at = now + timedelta(seconds=MATCH_READY_GRACE_SECONDS)


async def advance_tournament_match(db: AsyncSession, series_id: uuid.UUID) -> None:
    """Call from main.py after a tournament series completes. Marks the match
    winner, sets placed_rank for eliminated players, activates downstream matches,
    and closes the tournament if the final + TP are both done.

    Idempotent on re-entry: if the match is already marked completed, returns
    without re-assigning placed_rank or triggering prizes a second time. This
    protects against double-invocation from a retried /matches POST or a tick
    racing with the series completion hook."""
    now = datetime.now(timezone.utc)

    # Find the match + series. with_for_update() serializes concurrent
    # advance_tournament_match invocations (e.g. tick + /matches hook racing
    # within the same millisecond). The second caller waits for the first to
    # commit, then sees the status guard below and returns cleanly. (Review #4)
    mq = select(TournamentMatch).where(TournamentMatch.series_id == series_id).with_for_update()
    m = (await db.execute(mq)).scalar_one_or_none()
    if not m:
        return  # not a tournament match

    # Status guard: already advanced, don't re-process.
    if m.status in ("completed", "forfeit", "double_forfeit"):
        return

    sq = select(RankedSeries).where(RankedSeries.id == series_id)
    series = (await db.execute(sq)).scalar_one()
    if series.status != "completed" or not series.winner_id:
        return

    # Map series winner back to signup. Defensive: tolerate missing signup row
    # (e.g. manual cleanup) rather than exploding the whole match handler.
    winner_sig_q = select(TournamentSignup).where(and_(
        TournamentSignup.tournament_id == m.tournament_id,
        TournamentSignup.player_id == series.winner_id,
    ))
    winner_sig = (await db.execute(winner_sig_q)).scalar_one_or_none()
    if not winner_sig:
        print(f"[TOURNAMENT] advance: winner signup not found for series {series_id}, "
              f"match {m.id} — tournament state may be inconsistent")
        return
    m.winner_signup_id = winner_sig.id
    m.status = "completed"
    m.ended_at = now

    loser_signup_id = m.p1_signup_id if winner_sig.id == m.p2_signup_id else m.p2_signup_id
    t = await _get_tournament(db, m.tournament_id)
    total_rounds = _total_rounds_for(t)

    # Placement assignment — differs by FORMAT, not kind. Both sync and async
    # can run double-elim; only the legacy single_elim_bo3 path uses the old
    # W-final + TP placements.
    if t.format == "double_elim_bo3":
        # Double-elim placements: GF winner = 1st, GF loser = 2nd, LB final
        # loser = 3rd. GF_RESET (bracket reset) may fire after GF — handled
        # below; we postpone finalizing 1st/2nd until bracket_reset is skipped
        # or GF_RESET completes.
        if m.bracket_side == "GF_RESET":
            t.winner_signup_id = winner_sig.id
            t.runner_up_signup_id = loser_signup_id
            winner_sig.placed_rank = 1
            loser_sig = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == loser_signup_id))).scalar_one_or_none()
            if loser_sig:
                loser_sig.placed_rank = 2
        elif m.bracket_side == "GF":
            # GF has two prereqs: WB final (role W) and LB final (role W). If
            # GF winner came from the LB side, they force a bracket reset.
            # Identify sides by prereq_match_ids[0] (WB final) and [1] (LB final).
            prereq_ids = list(m.prereq_match_ids or [])
            wb_champ = None
            lb_champ = None
            if len(prereq_ids) >= 2:
                wb_final = (await db.execute(select(TournamentMatch).where(TournamentMatch.id == prereq_ids[0]))).scalar_one_or_none()
                lb_final = (await db.execute(select(TournamentMatch).where(TournamentMatch.id == prereq_ids[1]))).scalar_one_or_none()
                wb_champ = wb_final.winner_signup_id if wb_final else None
                lb_champ = lb_final.winner_signup_id if lb_final else None
            if lb_champ and winner_sig.id == lb_champ:
                # LB champ won GF: insert GF_RESET as a new pending match.
                # WB champ gets a second life. If GF_RESET ends, the winner is
                # tournament champion; otherwise GF_RESET activates and plays.
                # Async GF_RESET gets the same 7-day deadline as any other
                # async match so the bracket doesn't hang indefinitely if the
                # LB champ goes offline after forcing the reset.
                reset_deadline = None
                if t.kind == "async":
                    reset_deadline = datetime.now(timezone.utc) + timedelta(days=ASYNC_MATCH_DEADLINE_DAYS)
                reset_row = TournamentMatch(
                    id=uuid.uuid4(),
                    tournament_id=t.id,
                    round=m.round + 1,
                    bracket_side="GF_RESET",
                    slot_idx=0,
                    p1_signup_id=wb_champ,   # WB champ (had no prior loss)
                    p2_signup_id=lb_champ,   # LB champ (won the first GF)
                    prereq_match_ids=[m.id],
                    prereq_roles=["W"],
                    is_bye=False,
                    status="pending",
                    deadline_at=reset_deadline,
                    ready_deadline_at=reset_deadline,
                )
                db.add(reset_row)
                print(f"[TOURNAMENT] Bracket reset triggered for {t.id}: LB champ {lb_champ} forced GF_RESET")
            else:
                # WB champ held — tournament over, they're 1st.
                t.winner_signup_id = winner_sig.id
                t.runner_up_signup_id = loser_signup_id
                winner_sig.placed_rank = 1
                loser_sig = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == loser_signup_id))).scalar_one_or_none()
                if loser_sig:
                    loser_sig.placed_rank = 2
        elif m.bracket_side == "L" and len(list(m.prereq_match_ids or [])) >= 1:
            # Determine if this was the LB final (loser → 3rd place) by checking
            # the bracket_side of downstream matches — LB final feeds GF.
            dq = select(TournamentMatch).where(and_(
                TournamentMatch.tournament_id == t.id,
                TournamentMatch.bracket_side == "GF",
            ))
            gf = (await db.execute(dq)).scalar_one_or_none()
            if gf and m.id in (gf.prereq_match_ids or []):
                # LB final loser = 3rd place
                t.third_place_signup_id = loser_signup_id
                loser_sig = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == loser_signup_id))).scalar_one_or_none()
                if loser_sig:
                    loser_sig.placed_rank = 3
    else:
        # Sync single-elim placement logic (unchanged from Phase 1).
        if m.bracket_side == "W" and m.round == total_rounds:
            t.winner_signup_id = winner_sig.id
            t.runner_up_signup_id = loser_signup_id
            winner_sig.placed_rank = 1
            loser_sig = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == loser_signup_id))).scalar_one_or_none()
            if loser_sig:
                loser_sig.placed_rank = 2
        elif m.bracket_side == "TP":
            t.third_place_signup_id = winner_sig.id
            winner_sig.placed_rank = 3
            loser_sig = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == loser_signup_id))).scalar_one_or_none()
            if loser_sig:
                loser_sig.placed_rank = 4

    # Fire downstream activation + possible tournament completion.
    await _activate_ready_matches(db, m.tournament_id)
    await _maybe_complete_tournament(db, t)


def _total_rounds_for(t: Tournament) -> int:
    # Max round of any non-TP match in the bracket. Computed indirectly from
    # max_players: log2(next_pow2(max_players)). For sync single-elim with
    # max_players=16, that's 4.
    n = t.max_players
    x = 1
    r = 0
    while x < n:
        x *= 2
        r += 1
    return r


async def _maybe_complete_tournament(db: AsyncSession, t: Tournament) -> None:
    """Complete tournament when the appropriate terminal matches are done.
    Sync (single-elim): final + TP.
    Async (double-elim): GF (if WB held) or GF_RESET (if bracket reset fired) +
        LB final (for 3rd place).
    Idempotent — short-circuits if status == 'completed'. (Review #3)"""
    if t.status == "completed":
        return
    finished_states = ("completed", "forfeit", "double_forfeit")

    if t.format == "double_elim_bo3":
        # If a GF_RESET exists and is not yet finished, wait for it.
        rq = select(TournamentMatch).where(and_(
            TournamentMatch.tournament_id == t.id,
            TournamentMatch.bracket_side == "GF_RESET",
        ))
        reset_m = (await db.execute(rq)).scalar_one_or_none()
        if reset_m is not None:
            if reset_m.status not in finished_states:
                return
        else:
            gfq = select(TournamentMatch).where(and_(
                TournamentMatch.tournament_id == t.id,
                TournamentMatch.bracket_side == "GF",
            ))
            gf_m = (await db.execute(gfq)).scalar_one_or_none()
            if not gf_m or gf_m.status not in finished_states:
                return
            # GF done but no reset was triggered — WB held, tournament over.
    else:
        total_rounds = _total_rounds_for(t)
        final_q = select(TournamentMatch).where(and_(
            TournamentMatch.tournament_id == t.id,
            TournamentMatch.round == total_rounds,
            TournamentMatch.bracket_side == "W",
        ))
        final_m = (await db.execute(final_q)).scalar_one_or_none()
        tp_q = select(TournamentMatch).where(and_(
            TournamentMatch.tournament_id == t.id,
            TournamentMatch.bracket_side == "TP",
        ))
        tp_m = (await db.execute(tp_q)).scalar_one_or_none()
        if not final_m or final_m.status not in finished_states:
            return
        if tp_m and tp_m.status not in finished_states:
            return

    t.status = "completed"
    t.ended_at = datetime.now(timezone.utc)
    await _pay_prizes(db, t)


async def _pay_prizes(db: AsyncSession, t: Tournament) -> None:
    """Award gold + XP to 1st/2nd/3rd signups. Discord trophy roles are granted
    by the bot watching for new completed tournament rows (separate task #26)."""
    tier = t.prize_tier or "none"
    golds = PRIZE_GOLD.get(tier, (0, 0, 0))
    xps = PRIZE_XP.get(tier, (0, 0, 0))

    async def do_grant(signup_id: Optional[uuid.UUID], rank_idx: int) -> None:
        if not signup_id:
            return
        sig = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == signup_id))).scalar_one_or_none()
        if not sig:
            return
        g = golds[rank_idx]
        x = xps[rank_idx]
        if g:
            await db.execute(text("""
                UPDATE players SET gold_earned = gold_earned + :g WHERE id = :pid
            """), {"g": g, "pid": sig.player_id})
            await db.execute(text("""
                INSERT INTO gold_transactions (player_id, amount, reason, created_at)
                VALUES (:pid, :g, :reason, NOW())
            """), {"pid": sig.player_id, "g": g, "reason": f"tournament_rank_{rank_idx + 1}"})
        if x:
            await db.execute(text("""
                UPDATE players SET total_xp = total_xp + :x WHERE id = :pid
            """), {"x": x, "pid": sig.player_id})

    await do_grant(t.winner_signup_id, 0)
    await do_grant(t.runner_up_signup_id, 1)
    await do_grant(t.third_place_signup_id, 2)


def _next_default_start(now_utc: datetime) -> datetime:
    """Compute the next Saturday 12:00 America/Los_Angeles strictly after now_utc.
    Uses a minimum lead time of 48h so we never schedule a tournament less
    than 2 days out — gives voting/signups a real window even when cron fires
    the first time on a Saturday morning. (Review #13)
    Returns a UTC-normalized datetime so storage is timezone-agnostic."""
    now_pt = now_utc.astimezone(PT_ZONE)
    min_lead = now_pt + timedelta(hours=48)
    days_ahead = (TOURNAMENT_WEEKDAY - now_pt.weekday()) % 7
    candidate = now_pt.replace(hour=TOURNAMENT_HOUR_PT, minute=0, second=0, microsecond=0)
    candidate = candidate + timedelta(days=days_ahead)
    while candidate <= min_lead:
        candidate = candidate + timedelta(days=7)
    return candidate.astimezone(timezone.utc)


async def _ensure_next_tournament(db: AsyncSession) -> None:
    """Create the next sync tournament if none is active AND we're not already
    scheduled ahead. Runs every tick — idempotent. Skips creation if any sync
    tournament exists in voting/locked/running state OR if a scheduled one is
    already queued for a future date within the next 14 days.

    Also drives async tournament creation on the ASYNC_CADENCE_DAYS schedule."""
    now = datetime.now(timezone.utc)
    # Active already?
    aq = select(Tournament).where(and_(
        Tournament.kind == "sync",
        Tournament.status.in_(["voting", "locked", "running"]),
    ))
    if not (await db.execute(aq)).scalars().first():
        # Upcoming one already created?
        uq = select(Tournament).where(and_(
            Tournament.kind == "sync",
            Tournament.default_start_ts > now,
        ))
        if not (await db.execute(uq)).scalars().first():
            default_start = _next_default_start(now)
            lock_at = default_start - timedelta(hours=LOCK_OFFSET_HOURS)
            t = Tournament(
                kind="sync",
                status="voting",
                format="double_elim_bo3",
                default_start_ts=default_start,
                lock_at=lock_at,
                voting_closes_at=lock_at,
                min_players=8,
                max_players=16,
                created_by="cron",
            )
            db.add(t)
            print(f"[TOURNAMENT-CRON] Created sync tournament, default_start={default_start.isoformat()}, lock_at={lock_at.isoformat()}")

    # Async cadence: separate from sync. Create a new async tournament if none
    # is active and the most recent async was created ≥ ASYNC_CADENCE_DAYS ago.
    aaq = select(Tournament).where(and_(
        Tournament.kind == "async",
        Tournament.status.in_(["voting", "locked", "running"]),
    ))
    if (await db.execute(aaq)).scalars().first():
        return
    last_async_q = select(Tournament).where(Tournament.kind == "async").order_by(Tournament.created_at.desc())
    last_async = (await db.execute(last_async_q)).scalars().first()
    if last_async and (now - last_async.created_at) < timedelta(days=ASYNC_CADENCE_DAYS):
        return
    # Async: 7-day signup window, lock and start immediately at the end. No
    # scheduled_start_ts delay — async tournaments begin as soon as signups close.
    async_lock_at = now + timedelta(days=ASYNC_SIGNUP_DAYS)
    at = Tournament(
        kind="async",
        status="voting",
        format="double_elim_bo3",
        default_start_ts=async_lock_at,
        lock_at=async_lock_at,
        voting_closes_at=async_lock_at,
        # min=8 matches the sync floor. The LB absorption pairing in
        # tournament_bracket.py has clean 1-for-1 math only at 8/16 slots —
        # at 5-7 participants the LB would leave one WB R2 loser with no slot,
        # effectively single-eliminating them.  Require a full 8 to avoid that.
        min_players=8,
        max_players=16,
        created_by="cron",
    )
    db.add(at)
    print(f"[TOURNAMENT-CRON] Created async tournament, signups until {async_lock_at.isoformat()}")


async def tournament_tick() -> None:
    """Background driver. Runs every 30s from main.py lifespan. Handles:
      - Auto-create the next weekly tournament if none is queued
      - voting -> locked when lock_at <= now
      - locked -> running when scheduled_start_ts <= now
      - running: activate newly-ready matches, apply no-show forfeits,
        close out when final+TP are done

    Per-tournament isolation (Review #2): each tournament's state mutation
    runs inside its own session so one broken row can't discard every
    other tournament's progress on the same tick. Cron-create runs in its
    own session too so a crash in that path doesn't block transitions.
    """
    import asyncio as _aio

    async def _safe(label: str, coro_factory):
        """Run a work unit with its own session + commit. Swallows exceptions
        and logs them so the caller can continue to the next unit."""
        try:
            async with async_session() as db:
                await coro_factory(db)
                await db.commit()
        except Exception as e:
            print(f"[TOURNAMENT-TICK] {label}: {e}")

    while True:
        try:
            await _aio.sleep(30)
            now = datetime.now(timezone.utc)

            # Cron create
            await _safe("ensure-next", _ensure_next_tournament)

            # Voting -> locked (one session per tournament)
            async with async_session() as db:
                vq = select(Tournament.id).where(and_(
                    Tournament.status == "voting", Tournament.lock_at <= now))
                voting_ids = [row[0] for row in (await db.execute(vq)).all()]
            for tid in voting_ids:
                async def _lock(db, _tid=tid):
                    t = (await db.execute(select(Tournament).where(Tournament.id == _tid))).scalar_one_or_none()
                    if t and t.status == "voting":
                        await lock_tournament(db, t)
                await _safe(f"lock:{tid}", _lock)

            # Locked -> running
            async with async_session() as db:
                lq = select(Tournament.id).where(and_(
                    Tournament.status == "locked",
                    Tournament.scheduled_start_ts <= now))
                locked_ids = [row[0] for row in (await db.execute(lq)).all()]
            for tid in locked_ids:
                async def _start(db, _tid=tid):
                    t = (await db.execute(select(Tournament).where(Tournament.id == _tid))).scalar_one_or_none()
                    if t and t.status == "locked":
                        await start_tournament(db, t)
                await _safe(f"start:{tid}", _start)

            # Running: per-tournament activate + forfeit + maybe-complete
            async with async_session() as db:
                rq = select(Tournament.id).where(Tournament.status == "running")
                running_ids = [row[0] for row in (await db.execute(rq)).all()]
            for tid in running_ids:
                async def _run(db, _tid=tid):
                    t = (await db.execute(select(Tournament).where(Tournament.id == _tid))).scalar_one_or_none()
                    if not t or t.status != "running":
                        return
                    await _apply_no_show_forfeits(db, _tid)
                    await _activate_ready_matches(db, _tid)
                    await _maybe_complete_tournament(db, t)
                await _safe(f"run:{tid}", _run)
        except Exception as e:
            print(f"[TOURNAMENT-TICK] Outer error: {e}")


async def _apply_no_show_forfeits(db: AsyncSession, tournament_id: uuid.UUID) -> None:
    """For every 'ready' match past ready_deadline_at, check both signups'
    ready_at heartbeats. If a signup isn't ready, mark it forfeited; if only
    one side is ready, the other side's match becomes a forfeit win."""
    now = datetime.now(timezone.utc)
    q = select(TournamentMatch).where(and_(
        TournamentMatch.tournament_id == tournament_id,
        TournamentMatch.status == "ready",
        TournamentMatch.ready_deadline_at <= now,
    ))
    for m in (await db.execute(q)).scalars().all():
        p1 = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == m.p1_signup_id))).scalar_one_or_none()
        p2 = (await db.execute(select(TournamentSignup).where(TournamentSignup.id == m.p2_signup_id))).scalar_one_or_none()
        p1_ready = p1 and p1.ready_at and (now - p1.ready_at).total_seconds() <= READY_STALE_SECONDS
        p2_ready = p2 and p2.ready_at and (now - p2.ready_at).total_seconds() <= READY_STALE_SECONDS
        if p1_ready and p2_ready:
            continue  # both ready, client will start match
        # Flag forfeit AND refresh the cached penalty inline so the UI sees
        # the updated pct immediately next refresh, not next time the player
        # signs up for something.
        if not p1_ready and p1:
            p1.forfeited = True
            await _recompute_player_penalty(db, p1.player_id)
        if not p2_ready and p2:
            p2.forfeited = True
            await _recompute_player_penalty(db, p2.player_id)
        if p1_ready and not p2_ready:
            m.winner_signup_id = m.p1_signup_id
            m.status = "forfeit"
            m.ended_at = now
        elif p2_ready and not p1_ready:
            m.winner_signup_id = m.p2_signup_id
            m.status = "forfeit"
            m.ended_at = now
        else:
            # Same penalty-aware tiebreak as _activate_ready_matches — bracket
            # progresses, lower-penalty player wins the mutual no-show.
            winner_id = m.p1_signup_id
            if p1 and p2:
                if p2.penalty_at_signup < p1.penalty_at_signup:
                    winner_id = m.p2_signup_id
                elif p1.penalty_at_signup == p2.penalty_at_signup and str(m.p2_signup_id) < str(m.p1_signup_id):
                    winner_id = m.p2_signup_id
            m.status = "double_forfeit"
            m.winner_signup_id = winner_id
            m.ended_at = now


async def _check_and_trigger_force_start(db: AsyncSession, t: Tournament) -> bool:
    """Called from the force-vote endpoint. Triggers an immediate lock+start if:
      - tournament is in 'voting'
      - every current signup has a force vote
      - max(vote_ts) - min(vote_ts) <= 30 minutes
      - signup count >= min_players"""
    if t.status != "voting":
        return False
    sq = select(TournamentSignup.player_id).where(TournamentSignup.tournament_id == t.id)
    signup_player_ids = set(row[0] for row in (await db.execute(sq)).all())
    if len(signup_player_ids) < t.min_players:
        return False
    fq = select(TournamentForceVote.player_id, TournamentForceVote.voted_at).where(
        TournamentForceVote.tournament_id == t.id)
    fv = {r.player_id: r.voted_at for r in (await db.execute(fq)).all()}
    if not all(pid in fv for pid in signup_player_ids):
        return False
    votes = [fv[pid] for pid in signup_player_ids]
    if (max(votes) - min(votes)).total_seconds() > FORCE_START_WINDOW_MINUTES * 60:
        return False
    # Trigger immediate lock + start.
    await lock_tournament(db, t)
    if t.status == "locked":
        t.scheduled_start_ts = datetime.now(timezone.utc)
        await start_tournament(db, t)
    return True


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/current", response_model=TournamentCurrentResponse)
async def get_current(
    steam_id: Optional[str] = None,
    kind: str = "sync",
    db: AsyncSession = Depends(get_db),
):
    """Returns the most recent not-yet-completed tournament of the given kind
    (default: sync), or the most recent completed one if none are active.
    `steam_id` is optional — when provided, the response includes my_signup_id,
    my_votes, etc."""
    if kind not in ("sync", "async"):
        raise HTTPException(status_code=400, detail="kind must be 'sync' or 'async'")
    q = select(Tournament).where(and_(
        Tournament.kind == kind,
        Tournament.status.in_(["voting", "locked", "running"]),
    )).order_by(Tournament.default_start_ts.asc())
    t = (await db.execute(q)).scalars().first()
    if not t:
        # Fall through to most recent completed — but only if it actually
        # finished recently. The previous logic returned the most recent
        # tournament regardless of age, so a tournament that ended weeks
        # ago kept showing as "current" in the F5 panel forever (user
        # report: async tournament from 2026-05-13 still listed end of May).
        # Short window (3 days) keeps the "bracket recap" moment but
        # clears stale entries automatically.
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        q2 = (
            select(Tournament)
            .where(and_(
                Tournament.kind == kind,
                Tournament.status == "completed",
                or_(
                    Tournament.ended_at >= recent_cutoff,
                    and_(Tournament.ended_at.is_(None), Tournament.created_at >= recent_cutoff),
                ),
            ))
            .order_by(Tournament.created_at.desc())
        )
        t = (await db.execute(q2)).scalars().first()
    if not t:
        return TournamentCurrentResponse(
            tournament_id=None, status=None, kind=None,
            default_start_ts=None, scheduled_start_ts=None, lock_at=None,
            voting_closes_at=None, started_at=None, ended_at=None,
            min_players=8, max_players=16,
            signups=[], matches=[],
            my_signup_id=None, my_votes=[], my_force_vote_at=None,
            my_ready=False, my_penalty_pct=0.0, my_discord_linked=False,
            time_slot_options=[], time_slot_tallies=[], force_vote_count=0,
        )
    caller = None
    if steam_id:
        caller = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    return await _build_current_response(db, t, caller)


@router.post("/{tournament_id}/signup", response_model=TournamentCurrentResponse)
async def signup(tournament_id: uuid.UUID, req: TournamentSignupRequest, db: AsyncSession = Depends(get_db)):
    t = await _get_tournament(db, tournament_id)
    if t.status != "voting":
        raise HTTPException(status_code=400, detail=f"Tournament not accepting signups (status={t.status})")
    player = await _get_player_by_steam(db, req.steam_id)
    if not player.discord_id:
        raise HTTPException(status_code=400, detail="Discord account must be linked before signup")
    existing = await _get_signup_for(db, tournament_id, player.id)
    if existing:
        return await _build_current_response(db, t, player)
    penalty = await _recompute_player_penalty(db, player.id)
    db.add(TournamentSignup(
        tournament_id=tournament_id,
        player_id=player.id,
        penalty_at_signup=penalty,
        is_speculative=False,  # recompute sets the real value
        region_at_signup=(req.region or None),
    ))
    await db.flush()
    await _recompute_speculation(db, tournament_id)
    await db.commit()
    return await _build_current_response(db, t, player)


@router.post("/{tournament_id}/unsignup", response_model=TournamentCurrentResponse)
async def unsignup(tournament_id: uuid.UUID, req: TournamentSignupRequest, db: AsyncSession = Depends(get_db)):
    t = await _get_tournament(db, tournament_id)
    if t.status not in ("voting", "locked"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot leave once the tournament starts playing (status={t.status}). "
                   f"Not showing up will forfeit and count toward your penalty %.")
    player = await _get_player_by_steam(db, req.steam_id)
    existing = await _get_signup_for(db, tournament_id, player.id)
    if not existing:
        return await _build_current_response(db, t, player)

    if t.status == "voting":
        # Pre-lock: delete the signup, no penalty, no bracket surgery.
        await db.delete(existing)
        await db.flush()
        await _recompute_speculation(db, tournament_id)
        await db.execute(delete(TournamentTimeVote).where(and_(
            TournamentTimeVote.tournament_id == tournament_id,
            TournamentTimeVote.player_id == player.id)))
        await db.execute(delete(TournamentForceVote).where(and_(
            TournamentForceVote.tournament_id == tournament_id,
            TournamentForceVote.player_id == player.id)))
    else:
        # Locked (bracket built, not yet started): backfill a speculative
        # signup into their slot OR collapse their matches into byes for
        # their opponents so the bracket still resolves.
        await _handle_leaving_signup(db, tournament_id, existing.id)
    await db.commit()
    return await _build_current_response(db, t, player)


async def _handle_leaving_signup(db: AsyncSession, tournament_id: uuid.UUID, leaving_signup_id: uuid.UUID) -> None:
    """Leave-during-locked handler. Tries to promote a speculative signup
    into the leaving player's bracket slot. If no speculative exists, collapses
    the leaving player's matches into byes for their opponents so the bracket
    still resolves. Deletes the leaving signup row at the end — the player
    is fully out."""
    leaving = (await db.execute(select(TournamentSignup).where(
        TournamentSignup.id == leaving_signup_id))).scalar_one_or_none()
    if leaving is None:
        return

    # Lowest-penalty speculative takes the seat.
    spec_q = select(TournamentSignup).where(and_(
        TournamentSignup.tournament_id == tournament_id,
        TournamentSignup.is_speculative == True,  # noqa: E712
    )).order_by(TournamentSignup.penalty_at_signup.asc(),
                TournamentSignup.signed_up_at.asc())
    spec = (await db.execute(spec_q)).scalars().first()

    matches_q = select(TournamentMatch).where(and_(
        TournamentMatch.tournament_id == tournament_id,
        or_(TournamentMatch.p1_signup_id == leaving_signup_id,
            TournamentMatch.p2_signup_id == leaving_signup_id),
    ))
    matches = (await db.execute(matches_q)).scalars().all()

    if spec is not None:
        # Promote: inherit seed and Elo snapshot, flip speculative off.
        spec.is_speculative = False
        spec.seed = leaving.seed
        spec.cached_elo_at_lock = leaving.cached_elo_at_lock
        for m in matches:
            if m.p1_signup_id == leaving_signup_id:
                m.p1_signup_id = spec.id
                if m.winner_signup_id == leaving_signup_id:
                    m.winner_signup_id = spec.id
            if m.p2_signup_id == leaving_signup_id:
                m.p2_signup_id = spec.id
                if m.winner_signup_id == leaving_signup_id:
                    m.winner_signup_id = spec.id
        print(f"[TOURNAMENT] Promoted speculative {spec.id} into slot of {leaving_signup_id} "
              f"(tournament {tournament_id})")
    else:
        # No backfill available — the remaining opponent gets a bye.
        for m in matches:
            if m.p1_signup_id == leaving_signup_id and m.p2_signup_id:
                m.is_bye = True
                m.winner_signup_id = m.p2_signup_id
                m.p1_signup_id = None
                m.status = "bye_auto"
            elif m.p2_signup_id == leaving_signup_id and m.p1_signup_id:
                m.is_bye = True
                m.winner_signup_id = m.p1_signup_id
                m.p2_signup_id = None
                m.status = "bye_auto"
        print(f"[TOURNAMENT] No speculative backfill for {leaving_signup_id}; "
              f"collapsed {len(matches)} match(es) into byes")

    await db.delete(leaving)


@router.post("/{tournament_id}/time-vote", response_model=TournamentCurrentResponse)
async def time_vote(tournament_id: uuid.UUID, req: TournamentTimeVoteRequest, db: AsyncSession = Depends(get_db)):
    t = await _get_tournament(db, tournament_id)
    if t.status != "voting":
        raise HTTPException(status_code=400, detail="Voting closed")
    player = await _get_player_by_steam(db, req.steam_id)
    if not await _get_signup_for(db, tournament_id, player.id):
        raise HTTPException(status_code=400, detail="Must sign up to vote")
    offered = set(_offered_time_slots(t.default_start_ts))
    bad = [s for s in req.slot_ts if s not in offered]
    if bad:
        raise HTTPException(status_code=400, detail=f"Invalid slot(s): {bad}")
    # Replace the player's votes.
    await db.execute(delete(TournamentTimeVote).where(and_(
        TournamentTimeVote.tournament_id == tournament_id,
        TournamentTimeVote.player_id == player.id)))
    for slot in req.slot_ts:
        db.add(TournamentTimeVote(
            tournament_id=tournament_id, player_id=player.id, slot_ts=slot))
    await db.commit()
    return await _build_current_response(db, t, player)


@router.post("/{tournament_id}/force-start-vote", response_model=TournamentCurrentResponse)
async def force_vote(tournament_id: uuid.UUID, req: TournamentForceVoteRequest, db: AsyncSession = Depends(get_db)):
    t = await _get_tournament(db, tournament_id)
    if t.status != "voting":
        raise HTTPException(status_code=400, detail="Force-start only during voting")
    player = await _get_player_by_steam(db, req.steam_id)
    if not await _get_signup_for(db, tournament_id, player.id):
        raise HTTPException(status_code=400, detail="Must sign up to vote")
    stmt = pg_insert(TournamentForceVote).values(
        tournament_id=tournament_id, player_id=player.id,
        voted_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=[TournamentForceVote.tournament_id, TournamentForceVote.player_id],
        set_={"voted_at": datetime.now(timezone.utc)},
    )
    await db.execute(stmt)
    await db.flush()
    triggered = await _check_and_trigger_force_start(db, t)
    await db.commit()
    return await _build_current_response(db, t, player)


@router.post("/{tournament_id}/ready", response_model=TournamentCurrentResponse)
async def ready(tournament_id: uuid.UUID, req: TournamentReadyRequest, db: AsyncSession = Depends(get_db)):
    t = await _get_tournament(db, tournament_id)
    player = await _get_player_by_steam(db, req.steam_id)
    sig = await _get_signup_for(db, tournament_id, player.id)
    if not sig:
        raise HTTPException(status_code=404, detail="Not signed up")
    sig.ready_at = datetime.now(timezone.utc)
    await db.commit()
    return await _build_current_response(db, t, player)


@router.get("/history")
async def history(limit: int = 25, offset: int = 0, db: AsyncSession = Depends(get_db)):
    q = text("""
        SELECT t.id AS tournament_id, t.kind, t.format, t.ended_at, t.prize_tier,
               w.display_name AS winner_name,
               r.display_name AS runner_up_name,
               tp.display_name AS third_place_name,
               (SELECT COUNT(*) FROM tournament_signups s WHERE s.tournament_id = t.id AND NOT s.is_speculative) AS signup_count
        FROM tournaments t
        LEFT JOIN tournament_signups ws ON ws.id = t.winner_signup_id
        LEFT JOIN players w ON w.id = ws.player_id
        LEFT JOIN tournament_signups rs ON rs.id = t.runner_up_signup_id
        LEFT JOIN players r ON r.id = rs.player_id
        LEFT JOIN tournament_signups tps ON tps.id = t.third_place_signup_id
        LEFT JOIN players tp ON tp.id = tps.player_id
        WHERE t.status = 'completed'
        ORDER BY t.ended_at DESC
        LIMIT :limit OFFSET :offset
    """)
    rows = (await db.execute(q, {"limit": limit, "offset": offset})).all()
    return [{
        "tournament_id": r.tournament_id, "kind": r.kind, "format": r.format,
        "ended_at": r.ended_at, "prize_tier": r.prize_tier,
        "winner_display_name": r.winner_name,
        "runner_up_display_name": r.runner_up_name,
        "third_place_display_name": r.third_place_name,
        "signup_count": r.signup_count,
    } for r in rows]


@router.get("/internal/watch")
async def internal_watch(
    x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Internal endpoint for the Discord bot. Returns every tournament in
    voting/locked/running/completed (within last 24h) state with enough
    context for the bot to: (a) detect state transitions and DM players,
    (b) resolve opponents for /dm-opponent, (c) grant trophy roles after
    completion."""
    expected = os.getenv("API_SECRET_KEY", "")
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=403, detail="Invalid internal key")
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    tq = text("""
        SELECT id, kind, status, default_start_ts, scheduled_start_ts,
               lock_at, started_at, ended_at, prize_tier,
               winner_signup_id, runner_up_signup_id, third_place_signup_id
        FROM tournaments
        WHERE status IN ('voting', 'locked', 'running')
           OR (status = 'completed' AND ended_at >= :cutoff)
        ORDER BY default_start_ts ASC
    """)
    trows = (await db.execute(tq, {"cutoff": cutoff})).all()
    result = []
    for t in trows:
        sq = text("""
            SELECT s.id AS signup_id, s.is_speculative, s.forfeited, s.placed_rank,
                   p.id AS player_id, p.steam_id, p.display_name, p.discord_id, p.discord_username
            FROM tournament_signups s
            JOIN players p ON p.id = s.player_id
            WHERE s.tournament_id = :tid
            ORDER BY s.is_speculative, s.penalty_at_signup, s.signed_up_at
        """)
        signups = [dict(r._mapping) for r in (await db.execute(sq, {"tid": t.id})).all()]
        mq = text("""
            SELECT m.id AS match_id, m.round, m.bracket_side, m.slot_idx, m.status,
                   m.p1_signup_id, m.p2_signup_id, m.winner_signup_id,
                   m.ready_deadline_at, m.deadline_at, m.started_at, m.ended_at,
                   p1.display_name AS p1_name, p1.discord_id AS p1_discord_id,
                   p2.display_name AS p2_name, p2.discord_id AS p2_discord_id
            FROM tournament_matches m
            LEFT JOIN tournament_signups s1 ON s1.id = m.p1_signup_id
            LEFT JOIN players p1 ON p1.id = s1.player_id
            LEFT JOIN tournament_signups s2 ON s2.id = m.p2_signup_id
            LEFT JOIN players p2 ON p2.id = s2.player_id
            WHERE m.tournament_id = :tid
            ORDER BY m.round, m.bracket_side, m.slot_idx
        """)
        matches = [dict(r._mapping) for r in (await db.execute(mq, {"tid": t.id})).all()]
        result.append({
            "tournament_id": str(t.id),
            "kind": t.kind, "status": t.status,
            "default_start_ts": t.default_start_ts.isoformat() if t.default_start_ts else None,
            "scheduled_start_ts": t.scheduled_start_ts.isoformat() if t.scheduled_start_ts else None,
            "lock_at": t.lock_at.isoformat() if t.lock_at else None,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "ended_at": t.ended_at.isoformat() if t.ended_at else None,
            "prize_tier": t.prize_tier,
            "winner_signup_id": str(t.winner_signup_id) if t.winner_signup_id else None,
            "runner_up_signup_id": str(t.runner_up_signup_id) if t.runner_up_signup_id else None,
            "third_place_signup_id": str(t.third_place_signup_id) if t.third_place_signup_id else None,
            "signups": [{
                "signup_id": str(s["signup_id"]),
                "is_speculative": s["is_speculative"],
                "forfeited": s["forfeited"],
                "placed_rank": s["placed_rank"],
                "player_id": str(s["player_id"]),
                "steam_id": s["steam_id"],
                "display_name": s["display_name"],
                "discord_id": s["discord_id"],
                "discord_username": s["discord_username"],
            } for s in signups],
            "matches": [{
                "match_id": str(m["match_id"]),
                "round": m["round"], "bracket_side": m["bracket_side"],
                "slot_idx": m["slot_idx"], "status": m["status"],
                "p1_signup_id": str(m["p1_signup_id"]) if m["p1_signup_id"] else None,
                "p2_signup_id": str(m["p2_signup_id"]) if m["p2_signup_id"] else None,
                "winner_signup_id": str(m["winner_signup_id"]) if m["winner_signup_id"] else None,
                "p1_name": m["p1_name"], "p2_name": m["p2_name"],
                "p1_discord_id": m["p1_discord_id"], "p2_discord_id": m["p2_discord_id"],
                "ready_deadline_at": m["ready_deadline_at"].isoformat() if m["ready_deadline_at"] else None,
                "deadline_at": m["deadline_at"].isoformat() if m["deadline_at"] else None,
                "started_at": m["started_at"].isoformat() if m["started_at"] else None,
                "ended_at": m["ended_at"].isoformat() if m["ended_at"] else None,
            } for m in matches],
        })
    return {"tournaments": result}


@router.get("/my-active-matches")
async def my_active_matches(steam_id: str, db: AsyncSession = Depends(get_db)):
    """Cheap lookup used by the client to show the TOURNAMENT GAME indicator
    in the top RankedRow when the local player is in a ROUNDS game with a
    tournament opponent. Returns every match currently in ready/active status
    involving the given player, across both sync and async tournaments.
    Spans tournament kinds — if the player is signed up for one sync + one
    async and has a ready match in each, both show up."""
    player = (await db.execute(select(Player).where(Player.steam_id == steam_id))).scalar_one_or_none()
    if not player:
        return {"matches": []}
    q = text("""
        SELECT m.id AS match_id, m.status, m.bracket_side, m.round,
               m.photon_room_name,
               t.id AS tournament_id, t.kind, t.photon_region,
               p1.steam_id AS p1_steam_id, p1.display_name AS p1_name,
               p2.steam_id AS p2_steam_id, p2.display_name AS p2_name,
               s1.ready_at AS p1_ready_at, s2.ready_at AS p2_ready_at
        FROM tournament_matches m
        JOIN tournaments t ON t.id = m.tournament_id
        LEFT JOIN tournament_signups s1 ON s1.id = m.p1_signup_id
        LEFT JOIN players p1 ON p1.id = s1.player_id
        LEFT JOIN tournament_signups s2 ON s2.id = m.p2_signup_id
        LEFT JOIN players p2 ON p2.id = s2.player_id
        WHERE t.status = 'running'
          AND m.status IN ('ready', 'active')
          AND (p1.id = :pid OR p2.id = :pid)
        ORDER BY m.round
    """)
    rows = (await db.execute(q, {"pid": player.id})).all()
    # Ready iff the heartbeat is recent (within 60s) — mirrors the
    # forfeit-deadline logic in _apply_no_show_forfeits.
    ready_cutoff = datetime.now(timezone.utc) - timedelta(seconds=READY_STALE_SECONDS)
    result = []
    for r in rows:
        is_p1 = r.p1_steam_id == steam_id
        my_ready = (r.p1_ready_at if is_p1 else r.p2_ready_at)
        opp_ready = (r.p2_ready_at if is_p1 else r.p1_ready_at)
        result.append({
            "tournament_id": str(r.tournament_id),
            "kind": r.kind,
            "match_id": str(r.match_id),
            "status": r.status,
            "bracket_side": r.bracket_side,
            "round": r.round,
            "opponent_steam_id": (r.p2_steam_id if is_p1 else r.p1_steam_id),
            "opponent_display_name": (r.p2_name if is_p1 else r.p1_name),
            "photon_room_name": r.photon_room_name,
            "photon_region": r.photon_region,
            "my_ready": my_ready is not None and my_ready >= ready_cutoff,
            "opp_ready": opp_ready is not None and opp_ready >= ready_cutoff,
        })
    return {"matches": result}


@router.get("/players/{steam_id}/tournaments")
async def player_tournaments(steam_id: str, limit: int = 10, db: AsyncSession = Depends(get_db)):
    """Tournament placement history for a player. Used by the Tournaments tab
    (My History section) and the leaderboard click-a-player detail."""
    player = await _get_player_by_steam(db, steam_id)
    summary_q = text("""
        SELECT
          COUNT(*) FILTER (WHERE placed_rank = 1) AS wins,
          COUNT(*) FILTER (WHERE placed_rank = 2) AS runner_ups,
          COUNT(*) FILTER (WHERE placed_rank = 3) AS thirds,
          COUNT(*) FILTER (WHERE NOT is_speculative
                            AND placed_rank IS NOT NULL) AS placed_count,
          COUNT(*) FILTER (WHERE NOT is_speculative) AS participant_count
        FROM tournament_signups s
        JOIN tournaments t ON t.id = s.tournament_id
        WHERE s.player_id = :pid AND t.status = 'completed'
    """)
    srow = (await db.execute(summary_q, {"pid": player.id})).one()
    recent_q = text("""
        SELECT t.id AS tournament_id, t.ended_at, s.placed_rank, t.kind,
               (SELECT COUNT(*) FROM tournament_signups s2
                WHERE s2.tournament_id = t.id AND NOT s2.is_speculative) AS signup_count,
               wp.display_name AS winner_display_name
        FROM tournament_signups s
        JOIN tournaments t ON t.id = s.tournament_id
        LEFT JOIN tournament_signups ws ON ws.id = t.winner_signup_id
        LEFT JOIN players wp ON wp.id = ws.player_id
        WHERE s.player_id = :pid AND t.status = 'completed' AND NOT s.is_speculative
        ORDER BY t.ended_at DESC NULLS LAST
        LIMIT :limit
    """)
    rrows = (await db.execute(recent_q, {"pid": player.id, "limit": limit})).all()
    return {
        "steam_id": steam_id,
        "winner_count": srow.wins or 0,
        "runner_up_count": srow.runner_ups or 0,
        "third_place_count": srow.thirds or 0,
        "participant_count": srow.participant_count or 0,
        "recent": [{
            "tournament_id": str(r.tournament_id),
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "placed_rank": r.placed_rank,
            "kind": r.kind,
            "signup_count": r.signup_count or 0,
            "winner_display_name": r.winner_display_name,
        } for r in rrows],
    }


@router.get("/players/{steam_id}/penalty", response_model=TournamentPenaltyResponse)
async def player_penalty(steam_id: str, db: AsyncSession = Depends(get_db)):
    player = await _get_player_by_steam(db, steam_id)
    await _recompute_player_penalty(db, player.id)
    await db.commit()
    pen = (await db.execute(
        select(PlayerTournamentPenalty).where(PlayerTournamentPenalty.player_id == player.id)
    )).scalar_one_or_none()
    if not pen:
        return TournamentPenaltyResponse(
            steam_id=steam_id, cached_penalty_pct=0.0,
            signups_90d=0, missed_90d=0, no_show_last_at=None)
    return TournamentPenaltyResponse(
        steam_id=steam_id,
        cached_penalty_pct=pen.cached_penalty_pct,
        signups_90d=pen.signups_90d, missed_90d=pen.missed_90d,
        no_show_last_at=pen.no_show_last_at,
    )


# ── Hook point for main.py ────────────────────────────────────────
#
# In main.py, after the existing POST /api/v1/matches handler marks a series
# 'completed', add:
#
#     from tournaments import advance_tournament_match
#     if series.is_tournament:
#         await advance_tournament_match(db, series.id)
#
# And in main.py lifespan(), alongside queue_cleanup_loop():
#
#     from tournaments import tournament_tick
#     task_t = asyncio.create_task(tournament_tick())
#     ...
#     task_t.cancel()
#
# And register the router:
#
#     from tournaments import router as tournaments_router
#     app.include_router(tournaments_router)
