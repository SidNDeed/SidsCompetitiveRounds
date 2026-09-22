"""Animal title ladders — the rungs, the thresholds, the progression.

An upgradeable title: you buy the first rung of a line (``Rat``, 1000 g,
ordinary shop item), equip it, and every COMPLETED RATED SERIES you finish
while a rung of that line is equipped counts +1 toward the next rung. One
series, one credit -- not one per game within it; see WHAT ONE CREDIT IS on
``record_completed_games``. Cross a
threshold and the next rung is granted, owned for ever, and auto-equipped.

Three pieces live here and nothing else does:

  * ``LADDERS`` — the whole catalogue as data: eight animal lines, each an
    ordered list of rungs (sku, display name, tier, threshold, rarity,
    colour). Migration 331 is GENERATED from this structure and
    ``backend/tests/test_title_ladders.py`` re-derives the migration's rows
    from it, so the table and this file cannot drift apart silently.
  * the pure rules — ``tier_for_games``, ``rungs_at_tier``, ``next_rung`` —
    which take numbers and return numbers, no database, no clock.
  * ``record_completed_games`` — the hook the four completion paths WILL
    call, and the ``GET /api/v1/players/{steam_id}/title-ladders`` read route
    the client WILL draw the progress bar from. Neither is reachable in
    production today; see WHAT IS NOT WIRED below.

WHAT IS NOT HERE. No mail. A rung-up should tell the player, and the system
mail + Discord relay that would carry that message is a different item's
surface; ``record_completed_games`` RETURNS one event per rung-up and the
caller decides what to do with it. No client rendering: rung names are
``shop_items`` rows like every other title and render through the existing
title path.

WHAT IS NOT WIRED. This module is the DATA HALF of item 12. Production
imports it for exactly ONE thing: ``main`` reads ``GRANTED_ONLY_SKUS`` to
carve the forty earned rungs out of the shop-owner exemption, on the
``/shop/items`` listing and on the set-active ownership check. That import
mounts no route and calls no hook. (An earlier version of this docstring said
production did not import this module at all, which was true when it was
written and is the kind of claim that goes stale the moment anything reads a
constant from here.) Two things are still unwired, and an earlier version
named only the first — which is why the second is spelled out here.

  1. THE HOOK. Nothing in main.py calls ``record_completed_games``. The four
     call sites belong to a rewrite of the lease surface that is in flight in
     another branch, and two sessions meeting inside those function bodies is
     the failure this was deliberately kept out of. See that function's
     docstring for the exact call shape, and note in particular that 2v2 has
     TWO completion paths, not one.
  2. THE ROUTER. main.py never calls ``include_router`` for the ``router``
     defined below, so ``GET /api/v1/players/{steam_id}/title-ladders``
     answers 404 in production. The route is written and unit-tested; it is
     not served. Do not cite it as the client's progress surface until an
     ``include_router`` line exists.

Migration 331 is therefore inert on its own: every tier-1 rung lands
``catalog_ready = FALSE``, so nothing is listed, nothing can be bought, and no
progress row is ever written. That inertness is what makes the data half safe
to deploy ahead of the wiring, and it is deliberate rather than incidental.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Player, PlayerItem, ShopItem

router = APIRouter(tags=["Titles"])


# ── The hidden pool ────────────────────────────────────────────────
#
# Rungs above the first are granted by progress and must not be buyable. The
# repo already has exactly one mechanism for "granted only, still equippable
# by its owner": `shop_items.rotation_pool = 'achievement'`. It does two
# things at once, both of which a ladder rung needs:
#
#   * `/shop/items` appends an item of this pool that the REQUESTING steam_id
#     owns, so the Shop tab can render its Set Active button, and shows it to
#     nobody else -- with one pre-existing carve-out that is not ours:
#     `_is_shop_owner` accounts see the whole pool owned or not. That surface
#     exists at all because achievement titles spent three releases with no
#     way for their owners to equip them (#151).
#   * the purchase endpoint 403s the pool by name
#     ("Unlocked by achievement, not purchasable").
#
# The plan for this item proposed a NEW pool name, 'ladder'. A new name buys
# a tidier label and costs both of the behaviours above: main.py knows the
# string 'achievement' and no other, so a 'ladder' rung would be invisible to
# the player who earned it AND purchasable for its listed price by anything
# that can name the sku — the shop hides it, the purchase path does not
# refuse it. Reusing the pool that already carries both gates is a deliberate
# deviation from the plan, recorded here rather than made silently.
#
# If a later change does introduce a 'ladder' pool, both main.py sites move
# together: the `/shop/items` append and the purchase refusal. Changing this
# constant alone is not enough, which is why it is a constant and not a
# literal sprinkled through the migration.
HIDDEN_POOL = "achievement"

# The first rung sits in the ORDINARY POOL — that is the whole of what this
# constant says. It is not hidden behind ``rotation_pool`` the way rungs 2+
# are. It is NOT on sale: migration 331 lands every tier-1 rung
# ``catalog_ready = FALSE``, because a line that can be bought before the
# progression hook exists is a line that can never advance. Flipping that flag
# is a later activation migration, not this one.
ENTRY_POOL = None
ENTRY_PRICE = 1000

# Cumulative games needed for each tier, indexed by tier number. Tier 1 is
# the purchased rung, so its threshold is 0. From the plan's proposal, which
# Sid has not yet ruled on. NOTE the asymmetry this produces, stated as an
# observation and not defended: Rat is the one five-rung line, so Rat God
# lands at tier 5 = 150 games while every other line's top rung is tier 6 =
# 300.
#
# WHERE A THRESHOLD ACTUALLY LIVES: in this dict AND in the
# ``title_ladders.threshold`` column. Both the granting path and the GET
# response read THIS dict, so an UPDATE to the column alone moves nothing —
# the ladder keeps granting and reporting the old number. Changing a threshold
# means editing here and redeploying; the column exists so the schedule can be
# read out of the database on its own, not as the source of truth. (An earlier
# comment here said one UPDATE was enough. It was wrong.)
TIER_THRESHOLDS = {1: 0, 2: 10, 3: 30, 4: 75, 5: 150, 6: 300}

# Rarity by tier, climbing the shop's existing palette. There is no 'mythic'
# rarity in this codebase (five values appear in backend/sql: common,
# uncommon, rare, epic, legendary), so the top rung is legendary and the
# "reads like a god at a glance" job is done by preview_color.
TIER_RARITY = {1: "rare", 2: "rare", 3: "epic", 4: "epic", 5: "legendary", 6: "legendary"}


def _rung(line, tier, slug, name, color, description):
    """One catalogue entry. `slug` distinguishes two rungs sharing a tier."""
    sku = f"title_ladder_{line}_{tier}" if slug is None else f"title_ladder_{line}_{tier}_{slug}"
    return {
        "line": line,
        "tier": tier,
        "sku": sku,
        "name": name,
        "description": description,
        "threshold": TIER_THRESHOLDS[tier],
        "rarity": TIER_RARITY[tier],
        "preview_color": color,
        "price": ENTRY_PRICE if tier == 1 else 0,
        "rotation_pool": ENTRY_POOL if tier == 1 else HIDDEN_POOL,
    }


def _line(line, display, entries):
    """entries: (tier, slug, name, colour, description) in ascending tier."""
    return {
        "line": line,
        "display": display,
        "rungs": [_rung(line, t, slug, name, color, desc) for (t, slug, name, color, desc) in entries],
    }


# ── The catalogue ──────────────────────────────────────────────────
#
# Names are the plan's proposal and the skus do not encode them — but a
# rename is NOT just an UPDATE of ``shop_items.name``. The display names below
# are also what the upgrade event, ``next_names`` and the GET response return,
# so a database-only rename leaves this module still reporting the old name to
# the client. A rename means editing here too. (An earlier comment claimed it
# touched nothing else. It was wrong.)
# Rat is the only line whose top tier is 4-with-two-rungs
# (King and Queen, either of which IS rung 4) — every consumer here reads
# rungs as a list per tier for exactly that reason, never as one row.
LADDERS = [
    _line("rat", "Rat", [
        (1, None, "Rat", "#9AA0A6", "Small, quick, everywhere."),
        (2, None, "Rat Leader", "#B6BDC6", "The other rats listen."),
        (3, None, "Rat Lord", "#A88CE0", "A lordship of gutters."),
        (4, "king", "Rat King", "#E0B33A", "Crowned in the tunnels."),
        (4, "queen", "Rat Queen", "#E0B33A", "Crowned in the tunnels."),
        (5, None, "Rat God", "#FFE066", "Worshipped. Still a rat."),
    ]),
    _line("cat", "Cat", [
        (1, None, "Kitten", "#F2C1A0", "Mostly paws."),
        (2, None, "Cat", "#E8A87C", "Sovereign of the sofa."),
        (3, None, "Big Cat", "#C97B4A", "No longer a lap animal."),
        (4, None, "Alpha Cat", "#B25E2E", "The fight ends when you say."),
        (5, None, "President Meow", "#E5A83B", "Elected unopposed."),
        (6, None, "Cat Deity", "#FFD966", "Nine lives, one throne."),
    ]),
    _line("dog", "Dog", [
        (1, None, "Pup", "#C7A87B", "Enthusiasm exceeds skill."),
        (2, None, "Dog", "#B08D5A", "Reliable. Loud."),
        (3, None, "Good Dog", "#98703C", "Told so, repeatedly."),
        (4, None, "Top Dog", "#D4913A", "Head of the pack."),
        (5, None, "Big Dog", "#E9AE45", "The pack is now a problem."),
        (6, None, "Dog God", "#FFDE8A", "Very good. Divine, even."),
    ]),
    _line("turtle", "Turtle", [
        (1, None, "Hatchling", "#8FBF9F", "Freshly out of the shell."),
        (2, None, "Turtle", "#6FA882", "Slow is a strategy."),
        (3, None, "Snapper", "#4E8C66", "The bite lands first."),
        (4, None, "Elder Turtle", "#3F7A57", "Outlasted everyone."),
        (5, None, "Turtle Sage", "#6BC49A", "Patience as a weapon."),
        (6, None, "World Turtle", "#9BF0C4", "Everything rests on you."),
    ]),
    _line("rabbit", "Rabbit", [
        (1, None, "Bunny", "#F3C6D6", "Twitchy and fast."),
        (2, None, "Rabbit", "#E3A0BC", "Gone before the shot."),
        (3, None, "Jackrabbit", "#CE7A9E", "Nothing catches you."),
        (4, None, "Hare Apparent", "#B85C86", "Next in line."),
        (5, None, "Moon Rabbit", "#C79BF0", "Pounding something on the moon."),
        (6, None, "Rabbit God", "#EBD1FF", "A god of small quick things."),
    ]),
    _line("bear", "Bear", [
        (1, None, "Cub", "#C59A6B", "Cute until it is not."),
        (2, None, "Bear", "#A87A4E", "Simply large."),
        (3, None, "Grizzly", "#8A5C35", "The argument is over."),
        (4, None, "Bear Boss", "#6F4526", "Runs the woods."),
        (5, None, "Ursa Major", "#D9A85C", "Written into the sky."),
        (6, None, "Bear God", "#FFDDA1", "The woods run themselves now."),
    ]),
    _line("eagle", "Eagle", [
        (1, None, "Eaglet", "#D9CBA3", "Not yet airborne."),
        (2, None, "Eagle", "#BFA96B", "The sky is a map."),
        (3, None, "Golden Eagle", "#D4AF37", "Gilded and patient."),
        (4, None, "Sky Lord", "#9FC6E8", "Owns the airspace."),
        (5, None, "Thunderbird", "#7FA9FF", "Arrives with the storm."),
        (6, None, "Eagle God", "#CFE4FF", "The storm arrives with you."),
    ]),
    _line("shark", "Shark", [
        (1, None, "Shark Pup", "#A9C6D6", "Teeth already."),
        (2, None, "Shark", "#7FA8BF", "Never stops moving."),
        (3, None, "Great White", "#5B88A3", "The water empties."),
        (4, None, "Apex Shark", "#416B87", "Top of every chain here."),
        (5, None, "Megalodon", "#2F5570", "Too big for the ocean."),
        (6, None, "Shark God", "#8FD8FF", "The ocean is the pet."),
    ]),
]


# ── Derived indexes ────────────────────────────────────────────────

LINES = {ld["line"]: ld for ld in LADDERS}
ALL_RUNGS = [r for ld in LADDERS for r in ld["rungs"]]
SKU_TO_RUNG = {r["sku"]: r for r in ALL_RUNGS}
ALL_SKUS = tuple(r["sku"] for r in ALL_RUNGS)
# The entry rung of each line: ordinary pool, priced, and the row a future
# activation migration flips to ``catalog_ready = TRUE``. `/shop/items` filters
# on readiness, so it surfaces NONE of these today — see ENTRY_POOL above.
ENTRY_SKUS = tuple(r["sku"] for r in ALL_RUNGS if r["tier"] == 1)
# The forty rungs above the first. These are EARNED, never bought and never
# auto-owned: `main._is_shop_owner` treats its accounts as owning every
# cosmetic and lists them the whole hidden pool, and both of those are wrong
# for a progression rung. An account that holds all forty by fiat is an
# account for which the ladder has no rungs left, and "wearing Shark God"
# stops meaning "finished 300 rated series". main.py reads this set to carve
# the rungs out of that exemption on BOTH surfaces -- the /shop/items listing
# and the set-active ownership check -- because carving out only the listing
# leaves the equip reachable by sku for anything that can name one.
GRANTED_ONLY_SKUS = frozenset(r["sku"] for r in ALL_RUNGS if r["tier"] > 1)


def max_tier(line: str) -> int:
    """Highest tier defined for a line (5 for rat, 6 for the rest)."""
    return max(r["tier"] for r in LINES[line]["rungs"])


def rungs_at_tier(line: str, tier: int) -> list:
    """Every rung at this tier. A LIST because rat's tier 4 is King AND
    Queen: both are rung 4 and reaching it grants both."""
    return [r for r in LINES[line]["rungs"] if r["tier"] == tier]


def tier_for_games(line: str, games: int) -> int:
    """Highest tier whose threshold this game count has reached.

    Never below 1: tier 1's threshold is 0, and a player only has a progress
    row at all because they bought and equipped rung 1.
    """
    earned = 1
    for r in LINES[line]["rungs"]:
        if games >= r["threshold"] and r["tier"] > earned:
            earned = r["tier"]
    return earned


def next_rung(line: str, tier: int):
    """The (tier, threshold) after this one, or None at the top of the line.

    The threshold is the same for every rung sharing a tier — migration 331's
    post-check asserts that, so reading the first is reading all of them.
    """
    nxt = tier + 1
    rows = rungs_at_tier(line, nxt)
    if not rows:
        return None
    return {"tier": nxt, "threshold": rows[0]["threshold"],
            "names": [r["name"] for r in rows]}


def line_of_sku(sku):
    """Which ladder line a sku belongs to, or None if it is not a rung."""
    r = SKU_TO_RUNG.get(sku or "")
    return r["line"] if r else None


# ── The completion hook ────────────────────────────────────────────

async def record_completed_games(db: AsyncSession, player_ids, *, mode: str, reference_id: str) -> list:
    """Credit one completed rated SERIES to every listed player's equipped
    ladder line. Returns one event dict per rung-up (usually none).

    WHAT ONE CREDIT IS. One row of `title_ladder_credits`, keyed
    (player_id, reference_id) -- so the unit of credit is whatever the caller
    passes as `reference_id`, and for every mode that is the SERIES or sitting,
    never an individual game inside it. A best-of-three 2v2 series is ONE
    credit, because both of its completion sites pass the team series id (see
    below) and the second insert loses the key. That is the intended
    behaviour, not a limitation: the plan specifies "a 1v1 series, a 2v2
    series, or an FFA sitting each count 1".

    Earlier drafts of this docstring and of migration 331 called the unit a
    "game" while simultaneously requiring a series id, which cannot both hold.
    The wording is fixed; the BEHAVIOUR was always what was asked for.

    AND THE THRESHOLDS MATCH IT -- checked, because an earlier version of this
    paragraph claimed they did not. QUESTIONS.md #8 reads "+1 per completed
    rated game (1v1 series, 2v2 series, FFA sitting) ... thresholds 10 / 30 /
    75 / 150 / 300": the parenthetical DEFINES a "game" as a series, in the
    same settled sentence that sets the numbers. So 300 means 300 series and
    always did. Do not re-open this with Sid on the strength of the word
    "game" appearing here -- that question was asked and answered, and a
    docstring claiming otherwise is how it gets asked twice.

    If the unit is ever changed to a real per-game credit, `reference_id` has
    to become per-game AND the after-the-fact settlement path needs its own
    dedupe key, or a forfeit-settled series double-credits. The thresholds
    would need revisiting in that case, since they were set against series.

    HOW A HOOK AUTHOR CALLS THIS — one line per completion site::

        events = await title_ladders.record_completed_games(
            db, [p1.id, p2.id], mode="1v1", reference_id=str(series.id))

    Inside the completing transaction, after the result is settled, before the
    commit. Its WRITE FOOTPRINT is FOUR tables, not the three named after this
    module: `title_ladder_credits` (the once-per-completion gate),
    `title_ladder_progress` (the counter and the stored tier),
    `players.active_title_id` (the auto-equip) AND `player_items` -- every
    granted rung goes through `main._grant_title_item`, which inserts the
    ownership row. That fourth one is the write that actually gives the player
    the title, and an earlier version of this paragraph left it out, which
    made the footprint read as ladder-local when it reaches the shared
    inventory table. It takes no lock the caller does not already hold, and
    returns [] for a player on no ladder — which is almost everyone.

    THERE ARE FOUR CALL SITES ACROSS THREE MODES, NOT ONE PER MODE. 2v2
    completes in two different places: `submit_team_match` and
    `_complete_team_series_with_ratings`, which settles a forfeit or a
    disconnect after the fact and is reached from two callers of its own. A
    hook that lives only in `submit_team_match` stops counting for every
    forfeit-settled series, and an "exactly one call per function" check
    passes while it does. The four sites are `submit_match` (1v1),
    `submit_team_match` and `_complete_team_series_with_ratings` (2v2), and
    `submit_ffa_match` (FFA) — all four re-derived by symbol against merged
    main, none of them by line number.

    1v2 IS DELIBERATELY NOT ONE OF THEM, and this is the one exclusion in the
    list. `submit_ovt_match` writes `is_ranked` as a literal `false` — not a
    parameter, a constant — and its own docstring says "NO rating at launch".
    Crediting it would make the first line of this module ("every COMPLETED
    RATED SERIES") false, and the plan's enumeration of what counts names
    1v1, 2v2 and FFA and not 1v2. The exclusion is asserted rather than
    assumed: `test_ovt_is_excluded_while_it_reports_unrated` reads that
    literal out of the INSERT and fails the day it stops being `false`, which
    is the day the question has to be answered properly. Whether a 1v2-only
    player should advance a ladder they bought is a design question, not this
    module's to settle.

    WHICH IS WHY DOUBLE-CREDIT IS STRUCTURAL HERE, NOT A CALLER PROMISE. The
    two 2v2 paths can both run for one series, and a retried report can run a
    path twice. `title_ladder_credits` has PRIMARY KEY (player_id,
    reference_id) and the insert is the gate: the increment only happens for
    the caller that wins that insert. `mode` is stored but is NOT part of the
    key, deliberately — if it were, the same series arriving under two
    different mode strings would be credited twice, which is precisely the
    2v2 shape. **Both 2v2 sites must pass the TEAM SERIES id as
    reference_id**; passing a per-match id from one and a series id from the
    other reopens the hole the key exists to close.

    WHAT IT DOES NOT CHECK. It does not know whether the game was rated. The
    caller does, and must only call from a rated completion. A wrong call is
    at least auditable after the fact: every credit row carries its mode and
    reference_id.

    LOCKING. Players are processed in canonical `str(pid)` order and the only
    row lock taken is `FOR NO KEY UPDATE` on `players` — the weakest mode that
    still conflicts with this function's own later write of
    `active_title_id`, and the mode a plain UPDATE would take anyway, so it
    enrols no foreign-key insert in the lock graph (#202). That order was
    chosen to match the completion paths rather than to differ from them:
    `submit_match` locks its players with `sorted(pids, key=str)` and
    `FOR NO KEY UPDATE`, and the 2v2 completion helper takes the same sorted
    pass (#202). Those two were READ; the OVT and FFA paths were not, so
    whoever wires those two sites should confirm the same discipline there
    before assuming this re-locks rather than waits. The progress row is an
    upsert rather than a lock-then-write: it
    may not exist yet, and a gate on a row that does not exist locks nothing
    (#203/#207). `games` is only ever moved by a delta (#326).

    `active_title_id` is read INSIDE this transaction under that lock, and the
    auto-equip only fires when the title still equipped at that moment is a
    rung of the line being credited — a player who switched to another line
    mid-series keeps their choice.
    """
    # Late import, and it has to stay late: `main` imports THIS module at its
    # own module level (for GRANTED_ONLY_SKUS), so a module-level
    # `from main import ...` here would be a genuine import cycle. Deferring
    # it to call time keeps the cycle out of the import graph and keeps this
    # module importable on its own, which is how its tests load it.
    from main import _grant_title_item

    events = []
    for pid in sorted(player_ids, key=lambda p: str(p)):
        row = (await db.execute(text(
            "SELECT p.active_title_id, si.sku "
            "  FROM players p "
            "  LEFT JOIN shop_items si ON si.id = p.active_title_id "
            " WHERE p.id = :pid "
            "   FOR NO KEY UPDATE OF p"
        ), {"pid": pid})).first()
        if row is None:
            continue
        line = line_of_sku(row[1])
        if line is None:
            continue   # not wearing a ladder rung: nothing to credit

        claimed = (await db.execute(text(
            "INSERT INTO title_ladder_credits (player_id, reference_id, line, mode) "
            "VALUES (:pid, :ref, :line, :mode) "
            "ON CONFLICT (player_id, reference_id) DO NOTHING "
            "RETURNING 1"
        ), {"pid": pid, "ref": str(reference_id), "line": line, "mode": mode})).first()
        if claimed is None:
            continue   # this completion already counted for this player

        games, tier_before = (await db.execute(text(
            "INSERT INTO title_ladder_progress (player_id, line, games, tier) "
            "VALUES (:pid, :line, 1, 1) "
            "ON CONFLICT (player_id, line) DO UPDATE "
            "   SET games = title_ladder_progress.games + 1, updated_at = NOW() "
            "RETURNING games, tier"
        ), {"pid": pid, "line": line})).one()

        earned = tier_for_games(line, games)
        if earned <= tier_before:
            continue

        # Grant every rung CROSSED, not just the top one. A threshold edit or
        # a backfilled count can move a player more than one tier in a single
        # game, and a hole in the middle of a ladder is not repairable by
        # playing on — the player is already past that threshold for ever.
        granted = []
        reached = tier_before
        for t in range(tier_before + 1, earned + 1):
            rungs = rungs_at_tier(line, t)
            missing = []
            for r in rungs:
                if await _grant_title_item(db, pid, r["sku"]):
                    granted.append(r["sku"])
                else:
                    missing.append(r["sku"])
            if missing:
                # STOP at the last tier the player actually holds. Advancing
                # past a rung that was not granted is the one move that cannot
                # be undone by playing on, because the threshold is already
                # behind them. Leaving `tier` where it is keeps the games
                # count climbing and makes the NEXT completed game retry the
                # grant, so a shop row that comes back repairs itself (#276).
                print(f"[LADDER] {line} tier {t} NOT granted to {pid}: "
                      f"{missing} absent from shop_items. Holding at tier "
                      f"{reached}; the next completed game retries.")
                break
            reached = t

        if reached == tier_before:
            # Nothing landed. No tier write, no auto-equip, no event: an event
            # here would tell the player they had been promoted to a title
            # they do not own.
            continue
        earned = reached

        await db.execute(text(
            "UPDATE title_ladder_progress SET tier = GREATEST(tier, :t), updated_at = NOW() "
            " WHERE player_id = :pid AND line = :line"
        ), {"t": earned, "pid": pid, "line": line})

        # Auto-equip the new top rung. `row[1]` was read under the
        # FOR NO KEY UPDATE this transaction still holds on that players
        # row, and it was a rung of `line`, so for as long as that lock
        # stands this replaces one rung of the player's own line with a
        # higher one. It is NOT a claim about a player who equips something
        # else after this transaction commits -- that write is theirs and
        # wins. Where a tier has two rungs (rat 4), the first listed is the
        # one worn; the other is owned and equippable from the Shop tab.
        top = rungs_at_tier(line, earned)
        equipped_sku = None
        if top:
            equipped_sku = top[0]["sku"]
            await db.execute(text(
                "UPDATE players SET active_title_id = si.id "
                "  FROM shop_items si "
                " WHERE si.sku = :sku AND players.id = :pid"
            ), {"sku": equipped_sku, "pid": pid})

        events.append({
            "player_id": str(pid),
            "line": line,
            "line_display": LINES[line]["display"],
            "games": games,
            "from_tier": tier_before,
            "to_tier": earned,
            "from_name": (rungs_at_tier(line, tier_before) or [{}])[0].get("name"),
            "to_name": top[0]["name"] if top else None,
            "granted_skus": granted,
            "equipped_sku": equipped_sku,
        })
    return events


# ── The read route ─────────────────────────────────────────────────

@router.get("/api/v1/players/{steam_id}/title-ladders")
async def get_title_ladders(steam_id: str, db: AsyncSession = Depends(get_db)):
    """Every ladder line, what this player owns on it, and how far to the next
    rung. Pure read — no row is written, so it is safe on the read replica.

    Unknown steam_id is a 404 rather than an empty board: the client uses this
    to draw a progress bar for an account it believes exists, and a silent
    all-zeroes answer would render as "you have made no progress" for what is
    actually a wrong id.
    """
    player = (await db.execute(
        select(Player).where(Player.steam_id == steam_id)
    )).scalar_one_or_none()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    owned_skus = {
        s for (s,) in (await db.execute(
            select(ShopItem.sku)
            .join(PlayerItem, PlayerItem.item_id == ShopItem.id)
            .where(PlayerItem.player_id == player.id,
                   ShopItem.sku.in_(ALL_SKUS))
        )).all()
    }
    item_ids = {
        sku: iid for (sku, iid) in (await db.execute(
            select(ShopItem.sku, ShopItem.id).where(ShopItem.sku.in_(ALL_SKUS))
        )).all()
    }
    progress = {
        line: (games, tier) for (line, games, tier) in (await db.execute(text(
            "SELECT line, games, tier FROM title_ladder_progress WHERE player_id = :pid"
        ), {"pid": player.id})).all()
    }
    active_sku = None
    if player.active_title_id is not None:
        active_sku = (await db.execute(
            select(ShopItem.sku).where(ShopItem.id == player.active_title_id)
        )).scalar_one_or_none()

    out = []
    for ld in LADDERS:
        line = ld["line"]
        games, tier = progress.get(line, (0, 1))
        nxt = next_rung(line, tier)
        out.append({
            "line": line,
            "name": ld["display"],
            "games": games,
            "tier": tier,
            "max_tier": max_tier(line),
            "next_tier": nxt["tier"] if nxt else None,
            "next_threshold": nxt["threshold"] if nxt else None,
            "next_names": nxt["names"] if nxt else [],
            # Never negative: a player past the top has no next rung at all.
            "games_to_next": max(0, nxt["threshold"] - games) if nxt else None,
            "rungs": [{
                "tier": r["tier"],
                "sku": r["sku"],
                "item_id": item_ids.get(r["sku"]),
                "name": r["name"],
                "description": r["description"],
                "rarity": r["rarity"],
                "preview_color": r["preview_color"],
                "threshold": r["threshold"],
                "price": r["price"],
                "owned": r["sku"] in owned_skus,
                "active": r["sku"] == active_sku,
            } for r in ld["rungs"]],
        })
    return {"steam_id": steam_id, "active_line": line_of_sku(active_sku), "ladders": out}
