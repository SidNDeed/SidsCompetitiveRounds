"""Title ladders -- the catalogue, the per-kind rules, the per-game credit.

An upgradeable title: you buy the first rung of a ladder (an ordinary shop
title), wear it, and every RANKED GAME you finish while a rung of that ladder
is worn can count toward the next rung. What a game counts for depends on the
ladder's KIND (``KIND_THRESHOLDS``): one per game, one per win, one per loss,
the play gold that game paid, one per 1v1 game with a card of the ladder's
family in the build, one per 1v1 win meeting a playstyle condition, or the
best run of consecutive 1v1 wins. Cross a threshold and the next rung is
granted, owned for ever, and auto-equipped.

Every ladder has exactly five tiers: tier 1 is the entry rung (bought), tiers
2-5 are earned (granted only). The names, the kinds and the thresholds are
the approved proposal for board row 29 (its v2); the
one name that differs is recorded on the Grinder ladder below.

Four pieces live here:

  * ``LADDERS`` -- the whole catalogue as data. Migration 365 is GENERATED
    from this structure and ``backend/tests/test_title_ladders.py`` re-derives
    the migration's rows from it, so the table and this file cannot drift
    apart silently.
  * the pure rules -- ``tier_for_games``, ``rungs_at_tier``, ``next_rung``,
    ``game_row_1v1`` and the ``meets_*`` conditions -- which take numbers and
    rows and return numbers, no database, no clock.
  * ``record_completed_games`` -- the hook the three ranked game-reporting
    paths call once per GAME.
  * the ``GET /api/v1/players/{steam_id}/title-ladders`` read route.

HOW PRODUCTION REACHES THIS MODULE. In three places, and no others:

  1. THE HOOK. main.py calls ``record_completed_games`` once in each of the
     three ranked game-reporting paths -- ``submit_match`` (1v1),
     ``submit_team_match`` (2v2) and ``submit_ffa_match`` (FFA) -- each call
     inside a savepoint of its own, so a failed credit is logged as
     ``[LADDER-CREDIT] ... dropped`` and never costs the report. The
     reference_id is the GAME's id at all three: the 1v1 ``matches`` row,
     the 2v2 ``team_matches`` row and the FFA match id. The after-the-fact
     2v2 settlement (``_complete_team_series_with_ratings``) completes no
     game and is not hooked; 1v2 (``submit_ovt_match``) reports unrated and
     is not hooked. ``backend/tests/test_title_ladders.py`` asserts the set
     per mode, each call's reference expression, and that main.py holds
     exactly those three calls.
  2. THE ROUTER. main.py includes the ``router`` defined below exactly once.
  3. THE CARVE-OUT. ``main`` reads ``NOT_AUTO_OWNED_SKUS`` to take the earned
     rungs and the two retired titles out of the shop-owner exemption, on the
     ``/shop/items`` listing and on the set-active ownership check.

WHAT IS NOT HERE. No mail. ``record_completed_games`` RETURNS one event per
rung-up and the caller decides what to do with it. No client rendering: rung
names are ``shop_items`` rows like every other title.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Player, PlayerItem, ShopItem

router = APIRouter(tags=["Titles"])


# -- The hidden pool ---------------------------------------------------
#
# Rungs above the first are granted by progress and must not be buyable. The
# repo has exactly one mechanism for "granted only, still equippable by its
# owner": `shop_items.rotation_pool = 'achievement'`. `/shop/items` appends an
# item of this pool that the requesting steam_id owns (so the Shop tab can
# render its Set Active button) and the purchase endpoint 403s the pool by
# name. main.py knows the string 'achievement' and no other, which is why a
# rung reuses it rather than a new 'ladder' pool (a new name would be matched
# by neither gate). If a 'ladder' pool is ever introduced, both main.py sites
# move together with this constant.
HIDDEN_POOL = "achievement"

# The first rung sits in the ORDINARY POOL and is on sale. A new entry sku
# costs ENTRY_PRICE; an existing shop title that becomes a ladder's first rung
# keeps the price its buyers paid (the proposal names no prices).
ENTRY_POOL = None
ENTRY_PRICE = 1000

TIERS = (1, 2, 3, 4, 5)

# Rarity for a NEW rung, climbing the shop's palette (no 'mythic' exists).
# An existing shop title keeps the rarity it was sold with.
TIER_RARITY = {1: "rare", 2: "rare", 3: "epic", 4: "epic", 5: "legendary"}


# -- Kinds: what one game counts for, and the thresholds ---------------
#
# Cumulative count needed for each tier, tier 1 first (always 0: it is the
# rung you buy). WHERE A THRESHOLD ACTUALLY LIVES: here AND in the
# ``title_ladders.threshold`` column. The granting path and the GET read THIS
# table, so a change means editing here, regenerating 365's rows and
# redeploying; the column exists so the schedule can be read out of the
# database on its own, not as the source of truth.
KIND_THRESHOLDS = {
    "games":     (0, 15, 40, 100, 200),    # ranked games worn, any mode
    "wins":      (0, 8, 20, 50, 100),      # ranked wins worn, any mode
    "losses":    (0, 8, 20, 50, 100),      # ranked losses worn, any mode
    "gold":      (0, 500, 1500, 3000, 6000),   # play gold of ranked games worn
    "card":      (0, 10, 25, 60, 120),     # ranked 1v1 games worn, family card in the build
    "sniper":    (0, 3, 8, 18, 35),        # ranked 1v1 wins, hit rate >= 30 pct over >= 40 shots
    "berserker": (0, 3, 8, 20, 40),        # ranked 1v1 wins 5-0
    "blitz":     (0, 3, 8, 16, 30),        # ranked 1v1 wins in 210 s or less
    "phoenix":   (0, 2, 4, 8, 15),         # ranked 1v1 wins after trailing by 5 points
    "specter":   (0, 2, 5, 10, 20),        # ranked 1v1 wins conceding 2 points or fewer
    "streak":    (0, 5, 8, 12, 20),        # best run of consecutive ranked 1v1 wins
}

# The unit a ladder's count is in, for the client's "12 / 15 <unit>".
KIND_UNIT = {
    "games": "games", "wins": "wins", "losses": "losses", "gold": "gold",
    "card": "games", "sniper": "wins", "berserker": "wins", "blitz": "wins",
    "phoenix": "wins", "specter": "wins", "streak": "streak",
}

# Kinds measured on a ranked 1v1 game's own row. A 2v2 or FFA game claims
# nothing for them: the stats they read exist only on the 1v1 `matches` row.
ONE_V_ONE_KINDS = frozenset({"card", "sniper", "berserker", "blitz", "phoenix",
                             "specter", "streak"})

# The per-kind condition text, shown in the client's dropdown and used as the
# shop description of every rung this file creates. English source strings:
# the client renders them through I18n.Tr (section 5 of the build notes lists
# them). "Wear it" is the rule for every ladder: progress is credited only to
# the ladder whose rung is equipped when the game is reported.
KIND_CONDITION = {
    "games": "Wear it and play ranked games",
    "wins": "Wear it and win ranked games",
    "losses": "Wear it and lose ranked games",
    "gold": "Wear it and earn gold from ranked play",
    "sniper": "Wear it and win ranked 1v1 with 30% accuracy over 40+ shots",
    "berserker": "Wear it and win ranked 1v1 games 5-0",
    "blitz": "Wear it and win ranked 1v1 games in 3:30 or less",
    "phoenix": "Wear it and win ranked 1v1 after trailing by 5 points",
    "specter": "Wear it and win ranked 1v1 conceding 2 points or fewer",
    "streak": "Wear it and win ranked 1v1 games in a row",
}

# Gold that counts for a "gold" ladder: what ranked PLAY pays for THIS game,
# never bets, refunds, boosters, grants or purchases. The hook does not look
# it up: each of the three game-reporting callers already holds the amounts it
# credited to each player for the game it is recording and passes their sum
# as the row's `play_gold` -- the xp gold, the level reward, the series result
# (1v1, 2v2) or the placement (FFA), and the achievement gold newly paid
# while recording that game (main._ladder_achievement_gold). So the hook's
# work per player is fixed by the catalogue, not by the player's ledger
# history (round 2, findings 3 and 9).
PLAY_GOLD_KEY = "play_gold"


def play_gold_of(row) -> int:
    """The row's play gold for this game, as a non-negative int. A row without
    it (a caller that pays no play gold) counts 0."""
    try:
        return max(0, int((row or {}).get(PLAY_GOLD_KEY) or 0))
    except (TypeError, ValueError):
        return 0


# -- Building the catalogue ---------------------------------------------

def _rung(line, tier, spec, *, kind, color, condition):
    """One catalogue entry. `spec` is a tier name (a NEW rung, sku
    title_ladder_<line>_<tier>) or a dict naming an EXISTING shop title: its
    sku, the name it now carries, and the rarity, colour, description and
    price it already has on the shop row (an existing sku's row is renamed and
    re-pooled, never re-priced at tier 1 or re-coloured)."""
    if isinstance(spec, str):
        spec = {"name": spec}
    existing = "sku" in spec
    sku = spec.get("sku") or f"title_ladder_{line}_{tier}"
    if tier == 1:
        price = spec.get("price", ENTRY_PRICE)
    else:
        price = 0
    return {
        "line": line,
        "tier": tier,
        "sku": sku,
        "name": spec["name"],
        "description": spec.get("description", condition),
        "threshold": KIND_THRESHOLDS[kind][tier - 1],
        "rarity": spec.get("rarity", TIER_RARITY[tier]),
        "preview_color": spec.get("color", color),
        "price": price,
        "rotation_pool": ENTRY_POOL if tier == 1 else HIDDEN_POOL,
        "existing": existing,
    }


def _ladder(line, display, group, kind, color, specs, *, family=None, condition=None):
    """specs: exactly five, tier 1 first."""
    assert len(specs) == len(TIERS), line
    cond = condition or KIND_CONDITION[kind]
    return {
        "line": line,
        "display": display,
        "group": group,
        "kind": kind,
        "unit": KIND_UNIT[kind],
        "modes": "1v1" if kind in ONE_V_ONE_KINDS else "any",
        "condition": cond,
        "family": tuple(family or ()),
        "rungs": [_rung(line, t, s, kind=kind, color=color, condition=cond)
                  for t, s in zip(TIERS, specs)],
    }


def _x(sku, name, rarity, color, description, price=None):
    """An existing shop title, with the values its live row carries."""
    d = {"sku": sku, "name": name, "rarity": rarity, "color": color,
         "description": description}
    if price is not None:
        d["price"] = price
    return d


def _animal(line, display, names, colors):
    """An animal ladder. Its five skus are the existing title_ladder_<line>_<n>
    rows (migration 331), renamed in place; nobody holds any of them."""
    return _ladder(line, display, "animal", "games", colors[0],
                   [{"name": n, "color": c} for n, c in zip(names, colors)])


def _card(line, display, family, names, color, entry):
    """A card ladder: ranked 1v1 games worn with any card of the family."""
    cond = "Wear it and play ranked 1v1 with " + _or_list(family)
    return _ladder(line, display, "card", "card", color, [entry] + list(names[1:]),
                   family=family, condition=cond)


def _or_list(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def _numeral(line, sku, base, price, color, description):
    """A pronoun title climbing I to V like the rank titles."""
    numerals = ("I", "II", "III", "IV", "V")
    specs = [_x(sku, f"{base} {numerals[0]}", "common", color, description, price)]
    specs += [f"{base} {n}" for n in numerals[1:]]
    return _ladder(line, base, "numeral", "games", color, specs)


# -- The catalogue ------------------------------------------------------
#
# A rename is NOT just an UPDATE of ``shop_items.name``: the names below are
# also what the upgrade event, ``next_names`` and the GET response return, so
# a database-only rename leaves this module reporting the old name. Group
# order (animal, card, playstyle, shop, numeral) is the order the read route
# answers in.
LADDERS = [
    # Animal (proposal: "Animal ladders"); colours are the 331 rows' own.
    _animal("rat", "Rat", ["Baby Mouse", "Mouse", "Rat", "Rat Lord", "CAPYBARA"],
            ["#9AA0A6", "#B6BDC6", "#A88CE0", "#E0B33A", "#FFE066"]),
    _animal("cat", "Cat", ["Stray", "Prowler", "Alley King", "Sabertooth", "Sekhmet"],
            ["#F2C1A0", "#E8A87C", "#C97B4A", "#B25E2E", "#E5A83B"]),
    _animal("dog", "Dog", ["Pup", "Dog", "Hound", "Hellhound", "Cerberus"],
            ["#C7A87B", "#B08D5A", "#98703C", "#D4913A", "#E9AE45"]),
    _animal("turtle", "Turtle", ["Hatchling", "Turtle", "Snapper", "Leatherback", "World Turtle"],
            ["#8FBF9F", "#6FA882", "#4E8C66", "#3F7A57", "#6BC49A"]),
    _animal("rabbit", "Rabbit", ["Bunny", "Rabbit", "Jackrabbit", "Jackalope", "Moon Rabbit"],
            ["#F3C6D6", "#E3A0BC", "#CE7A9E", "#B85C86", "#C79BF0"]),
    _animal("bear", "Bear", ["Cub", "Bear", "Grizzly", "Kodiak", "Ursa Major"],
            ["#C59A6B", "#A87A4E", "#8A5C35", "#6F4526", "#D9A85C"]),
    _animal("eagle", "Eagle", ["Eaglet", "Eagle", "Golden Eagle", "Roc", "Thunderbird"],
            ["#D9CBA3", "#BFA96B", "#D4AF37", "#9FC6E8", "#7FA9FF"]),
    _animal("shark", "Shark", ["Shark Pup", "Reef Shark", "Great White", "Megalodon", "Leviathan"],
            ["#A9C6D6", "#7FA8BF", "#5B88A3", "#416B87", "#2F5570"]),

    # Card (one effect family each; any family card qualifies, decision 2).
    _card("tracker", "Tracker", ("Homing", "Target Bounce", "Remote"),
          ["Homing User", "Target Bouncer", "Remote Killer", "Elite Tracker", "No Escape"], "#FF6677",
          _x("title_tracker", "Homing User", "rare", "#FF6677", "Homing main", 2000)),
    _card("poisoner", "Poisoner", ("Poison", "Toxic Cloud", "Decay"),
          ["Poison", "Toxic Cloud", "Decay", "Plague Doctor", "Pestilence"], "#66CC44",
          _x("title_poisoner", "Poison", "rare", "#66CC44", "Poison main", 1500)),
    _card("windup", "Windup", ("Wind Up", "Quick Shot", "Fastball", "Steady Shot"),
          ["Wind Up", "Quick Shot", "Fastball", "Steady Shot", "Railgun"], "#AA66FF",
          _x("title_windup", "Wind Up", "rare", "#AA66FF", "Windup main", 1500)),
    _card("reloader", "Reloader", ("Quick Reload", "Refresh", "Scavenger", "Tactical Reload"),
          ["Quick Reload", "Refresh", "Scavenger", "Tactical", "Bottomless"], "#99CCDD",
          _x("title_reloader", "Quick Reload", "rare", "#99CCDD", "Quick Reload main", 1500)),
    _ladder("colossus", "Colossus", "card", "card", "#FFCC33", [
        _x("title_huge", "Huge", "rare", "#FFCC33", "Huge main", 1500),
        "Brawler",
        _x("title_tank", "Tank", "rare", "#88AA88", "Eats damage"),
        "Pristine",
        "Colossus",
    ], family=("Huge", "Brawler", "Tank", "Pristine Perseverance", "Defender"),
        condition="Wear it and play ranked 1v1 with "
                  + _or_list(("Huge", "Brawler", "Tank", "Pristine Perseverance", "Defender"))),
    _card("hasty", "Hasty", ("Fast Forward", "Chase", "Sneaky", "Thruster"),
          ["Fast Forward", "Chase", "Sneaky", "Thruster", "Lightspeed"], "#FF6633",
          _x("title_hasty", "Fast Forward", "rare", "#FF6633", "Fast Forward main", 1500)),
    _ladder("bounce", "Bounce", "card", "card", "#66CCEE", [
        _x("title_bouncy", "Bouncy", "rare", "#66CCEE", "Bouncy main", 1500),
        _x("title_bouncer", "Bouncer", "rare", "#BBDD44", "Target Bounce main"),
        "Ricochet",
        "Mayhem",
        "Trick Shot",
    ], family=("Bouncy", "Ricochet", "Mayhem", "Trickster"),
        condition="Wear it and play ranked 1v1 with "
                  + _or_list(("Bouncy", "Ricochet", "Mayhem", "Trickster"))),
    _card("healer", "Healer", ("Healing Field", "Leech", "Lifestealer", "Parasite"),
          ["Healing Field", "Leech", "Lifestealer", "Parasite", "Immortal"], "#44DD99",
          _x("title_healer", "Healing Field", "rare", "#44DD99", "Healing Field main", 2000)),
    _card("echo", "Echo", ("Echo", "Empower", "Shockwave", "Supernova"),
          ["Echo", "Empower", "Shockwave", "Supernova", "Big Bang"], "#88FFCC",
          _x("title_echo", "Echo", "rare", "#88FFCC", "Echo main", 2000)),

    # Playstyle (ranked 1v1 only; Pacifist stays single, decision 4). The
    # existing title carries the tier-2 name (tier 3 for Apex), so its owners
    # land there; tier 1 is a new entry rung.
    _ladder("sniper", "Sniper", "playstyle", "sniper", "#88CCFF", [
        "Marksman",
        _x("title_sniper", "Sniper", "rare", "#88CCFF", "Precision shooter"),
        "Sharpshooter", "Deadeye", "Headhunter"]),
    _ladder("berserker", "Berserker", "playstyle", "berserker", "#FF3333", [
        "Bruiser",
        _x("title_berserker", "Berserker", "rare", "#FF3333", "Pure aggression"),
        "Rampage", "Bloodbath", "Warlord"]),
    _ladder("blitz", "Blitz", "playstyle", "blitz", "#FFEE33", [
        "Rush",
        _x("title_blitz", "Blitz", "rare", "#FFEE33", "Fast finisher"),
        "Lightning", "Speedrunner", "Warp Speed"]),
    _ladder("phoenix", "Phoenix", "playstyle", "phoenix", "#FF8833", [
        "Ember",
        _x("title_phoenix", "Phoenix", "epic", "#FF8833", "Reborn after defeat"),
        "Rebirth", "From the Ashes", "Undying"]),
    _ladder("specter", "Specter", "playstyle", "specter", "#AABBFF", [
        "Shade",
        _x("title_specter", "Specter", "epic", "#AABBFF", "Hard to hit"),
        "Phantom", "Wraith", "Untouchable"]),
    _ladder("apex", "Apex", "playstyle", "streak", "#FFAA00", [
        "Contender", "Predator",
        _x("title_apex", "Apex", "epic", "#FFAA00", "Top of the food chain"),
        "Alpha", "Undefeated"]),

    # Shop titles that become ladders.
    _ladder("clown", "Clown", "shop", "games", "#FF6688", [
        _x("title_clown", "Clown", "common", "#FF6688", "Honk honk.", 800),
        "Jester", "Harlequin", "Ringmaster", "The Joker"]),
    _ladder("idiot", "Idiot", "shop", "losses", "#DDAA33", [
        _x("title_idiot", "Idiot", "uncommon", "#DDAA33", "Self-awareness is a virtue.", 1000),
        "Moron", "Buffoon", "Village Idiot", "Idiot Savant"]),
    _ladder("grandma", "Grandma", "shop", "games", "#FF66EE", [
        _x("title_grandma", "Grandma", "uncommon", "#FF66EE", "Wise beyond your years.", 1000),
        "Nana", "Great-Grandma", "Ancestor", "Ancient One"]),
    _ladder("decent", "Decent", "shop", "wins", "#88CC44", [
        _x("title_decent", "Decent", "uncommon", "#88CC44", "Not great. Not terrible.", 1000),
        "Fine", "Pretty Good", "Actually Good", "Too Good"]),
    # title_gold_rush (named Royal by 022, 0 holders) carries the tier-2 name
    # the proposal gives, "Gold Rush"; tier 1 is a new entry rung.
    _ladder("gold_rush", "Gold Rush", "shop", "gold", "#FFD94D", [
        "Prospector",
        _x("title_gold_rush", "Gold Rush", "legendary", "#FFD94D",
           "Worn by those who climbed the mountain."),
        "Forty-Niner", "Tycoon", "Midas"]),
    # Grinder: the five existing titles, owners landing on the tier they own.
    # Tier 1 stays "Noobie", NOT the proposal's "Beginner": migration 105
    # renamed title_beginner per Sid because "Beginner" is an Elo rank tier
    # name and a wearer looked like a player at that rank (bug #49). Recorded
    # as a deviation in the build notes for Sid.
    _ladder("grinder", "Grinder", "shop", "games", "#AAAAAA", [
        _x("title_beginner", "Noobie", "common", "#AAAAAA", "Everyone starts somewhere.", 500),
        _x("title_regular", "Regular", "common", "#FFFFFF", "You show up."),
        _x("title_active", "Active", "common", "#44CC88", "More ranked than not."),
        _x("title_sweaty", "Sweaty", "rare", "#FFCC33", "Sweat is just XP in liquid form."),
        _x("title_tryhard", "Tryhard", "rare", "#FF9933", "Trying, hard."),
    ]),

    # Numeral ladders: the pronoun titles climb I to V.
    _numeral("pronoun_he", "title_pronoun_he", "He/him", 100, "#EEEEEE", "Pronoun title."),
    _numeral("pronoun_she", "title_pronoun_she", "She/her", 100, "#EEEEEE", "Pronoun title."),
    _numeral("pronoun_they", "title_pronoun_they", "They/them", 100, "#EEEEEE", "Pronoun title."),
]

GROUPS = ("animal", "card", "playstyle", "shop", "numeral")

# The titles the proposal removes. Their buyers are refunded by migration 366,
# their shop rows are retired (catalog_ready FALSE), and the shop-owner
# exemption must not cover them either, or an exempt account could still
# equip one by sku.
RETIRED_SKUS = frozenset({"title_voidshot", "title_regicide"})

# Skus 331 created that this catalogue no longer has: rat's two tier-4 rungs
# and every line's tier 6. Migration 365 deletes them after proving nobody
# holds one.
DROPPED_SKUS = ("title_ladder_rat_4_king", "title_ladder_rat_4_queen",
                "title_ladder_cat_6", "title_ladder_dog_6", "title_ladder_turtle_6",
                "title_ladder_rabbit_6", "title_ladder_bear_6", "title_ladder_eagle_6",
                "title_ladder_shark_6")


# -- Derived indexes ----------------------------------------------------

LINES = {ld["line"]: ld for ld in LADDERS}
ALL_RUNGS = [r for ld in LADDERS for r in ld["rungs"]]
SKU_TO_RUNG = {r["sku"]: r for r in ALL_RUNGS}
ALL_SKUS = tuple(r["sku"] for r in ALL_RUNGS)
ENTRY_SKUS = tuple(r["sku"] for r in ALL_RUNGS if r["tier"] == 1)
# The rungs above the first. EARNED, never bought and never auto-owned:
# `main._is_shop_owner` treats its accounts as owning every cosmetic, which is
# wrong for a progression rung -- an account that holds every rung by fiat has
# no ladder left, and wearing "Leviathan" stops meaning "200 ranked games".
GRANTED_ONLY_SKUS = frozenset(r["sku"] for r in ALL_RUNGS if r["tier"] > 1)
# What main's shop-owner exemption must never cover: the earned rungs and the
# retired titles. main.py reads this one set on every surface that asks.
NOT_AUTO_OWNED_SKUS = GRANTED_ONLY_SKUS | RETIRED_SKUS


def ladder_count() -> int:
    """How many ladders this build serves -- the /health `title_ladders` word."""
    return len(LADDERS)


def max_tier(line: str) -> int:
    """Highest tier defined for a line (5 for every ladder)."""
    return max(r["tier"] for r in LINES[line]["rungs"])


def rungs_at_tier(line: str, tier: int) -> list:
    """Every rung at this tier (one per tier in this catalogue; a list so a
    shared tier would not need a new reader)."""
    return [r for r in LINES[line]["rungs"] if r["tier"] == tier]


def threshold(line: str, tier: int) -> int:
    rows = rungs_at_tier(line, tier)
    return rows[0]["threshold"] if rows else 0


def tier_for_games(line: str, games: int) -> int:
    """Highest tier whose threshold this count has reached (never below 1).
    `games` is the ladder's count in its own unit (games, wins, gold, ...)."""
    earned = 1
    for r in LINES[line]["rungs"]:
        if games >= r["threshold"] and r["tier"] > earned:
            earned = r["tier"]
    return earned


def next_rung(line: str, tier: int):
    """The (tier, threshold, names) after this one, or None at the top."""
    nxt = tier + 1
    rows = rungs_at_tier(line, nxt)
    if not rows:
        return None
    return {"tier": nxt, "threshold": rows[0]["threshold"],
            "names": [r["name"] for r in rows]}


def line_of_sku(sku):
    """Which ladder a sku belongs to, or None if it is not a rung."""
    r = SKU_TO_RUNG.get(sku or "")
    return r["line"] if r else None


# -- The per-game evaluator (pure) -------------------------------------
#
# One game row per player per game. `game_row_1v1` builds it from the 1v1
# `matches` row the report just inserted; 2v2 and FFA callers build the small
# row (`won`, `lost`, `play_gold`) themselves. Every condition below is a pure
# function of ONE row.

def _norm_card(name) -> str:
    return " ".join(str(name or "").split()).lower()


def parse_timeline(raw):
    """`point_timeline` -> [(a, b), ...] cumulative points, or None when it is
    absent or malformed (a malformed timeline answers no condition)."""
    pts = []
    for tok in str(raw or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        a, sep, b = tok.partition(":")
        if not sep:
            return None
        try:
            pts.append((int(a), int(b)))
        except ValueError:
            return None
    return pts or None


def raw_points(pts):
    """[(a, b), ...] running POINTS SCORED per side, one per timeline token,
    or None when a token is not exactly one point.

    The timeline's values are not points scored: each is the side's
    `rounds_won * 2 + points in the current round` (models.Match), so the
    side that LOSES a round drops back to its rounds * 2 -- "5:1,4:2" is the
    second side scoring and taking the round. Every token is exactly one
    point: the scorer's value rises by one and the other side's holds or
    falls. A token that is not (both rise, neither rises, a jump of two) is
    malformed, and a malformed timeline answers no condition."""
    a = b = 0
    pa = pb = 0
    out = []
    for x, y in pts:
        da, db = x - pa, y - pb
        if da == 1 and db <= 0:
            a += 1
        elif db == 1 and da <= 0:
            b += 1
        else:
            return None
        pa, pb = x, y
        out.append((a, b))
    return out or None


def game_row_1v1(match, player_id, cards=()) -> dict:
    """The one-player view of a 1v1 game. `match` is the `matches` row (any
    object with its attributes); `cards` the canonical names of this player's
    picks in that game.

    The timeline is read ORIENTATION-FREE: the winning side is the side whose
    final value is larger, so no p1/p2 mapping can be wrong. Both timeline
    conditions are in POINTS SCORED (raw_points): `worst_deficit` is the most
    points the winner was ever behind by, `loser_points` how many points the
    loser scored in the whole game. A tied, absent or malformed timeline
    answers neither the comeback nor the conceded-points condition."""
    pid = str(player_id)
    is_p1 = str(match.player1_id) == pid
    me, opp = ("p1", "p2") if is_p1 else ("p2", "p1")
    winner = getattr(match, "winner_id", None)
    won = winner is not None and str(winner) == pid
    lost = winner is not None and not won
    duration = getattr(match, "duration_seconds", None)
    if duration is None:
        duration = getattr(match, "match_duration", None)
    worst_deficit = None
    loser_points = None
    pts = parse_timeline(getattr(match, "point_timeline", None))
    raw = raw_points(pts) if pts else None
    if raw:
        fa, fb = pts[-1]
        if fa != fb:
            w = 0 if fa > fb else 1
            loser_points = raw[-1][1 - w]
            worst_deficit = max([0] + [(b - a) if w == 0 else (a - b) for a, b in raw])
    return {
        "won": won,
        "lost": lost,
        "own_rounds": getattr(match, f"{me}_rounds_won", None),
        "opp_rounds": getattr(match, f"{opp}_rounds_won", None),
        "shots": getattr(match, f"{me}_bullets_fired", None),
        "hits": getattr(match, f"{me}_bullets_hit", None),
        "duration_s": duration,
        "worst_deficit": worst_deficit,
        "loser_points": loser_points,
        "cards": frozenset(_norm_card(c) for c in (cards or ()) if c),
    }


def meets_sniper(row) -> bool:
    shots = row.get("shots") or 0
    hits = row.get("hits") or 0
    return bool(row.get("won")) and shots >= 40 and hits * 100 >= 30 * shots


def meets_berserker(row) -> bool:
    """Exactly 5-0: a won game of five rounds to none. An accepted 4-0 or 1-0
    (a shorter game the report still carries) is not a sweep."""
    return (bool(row.get("won")) and row.get("own_rounds") == 5
            and row.get("opp_rounds") == 0)


def meets_blitz(row) -> bool:
    d = row.get("duration_s")
    return bool(row.get("won")) and d is not None and 0 < d <= 210


def meets_phoenix(row) -> bool:
    w = row.get("worst_deficit")
    return bool(row.get("won")) and w is not None and w >= 5


def meets_specter(row) -> bool:
    lp = row.get("loser_points")
    return bool(row.get("won")) and lp is not None and lp <= 2


def holds_family(row, family) -> bool:
    fam = {_norm_card(c) for c in family}
    return bool(fam & set(row.get("cards") or ()))


_CONDITIONS = {
    "sniper": meets_sniper, "berserker": meets_berserker, "blitz": meets_blitz,
    "phoenix": meets_phoenix, "specter": meets_specter,
}


def counted_delta(line: str, row) -> int:
    """What one claimed game adds to this ladder's count, for every kind but
    `gold` (the caller's play_gold scalar, play_gold_of) and `streak` (needs
    the stored run). Pure."""
    ld = LINES[line]
    kind = ld["kind"]
    row = row or {}
    if kind == "games":
        return 1
    if kind == "wins":
        return 1 if row.get("won") else 0
    if kind == "losses":
        return 1 if row.get("lost") else 0
    if kind == "card":
        return 1 if holds_family(row, ld["family"]) else 0
    if kind in _CONDITIONS:
        return 1 if _CONDITIONS[kind](row) else 0
    raise ValueError(f"counted_delta does not answer kind {kind!r}")


# -- The per-game hook -------------------------------------------------

async def record_completed_games(db: AsyncSession, player_ids, *, mode: str,
                                 reference_id: str, rows=None) -> list:
    """Credit one completed RANKED GAME to every listed player's worn ladder.
    Returns one event dict per rung-up (usually none).

    WHAT ONE CREDIT IS. One row of `title_ladder_credits`, keyed
    (player_id, reference_id), and every caller passes the GAME's id: a 1v1
    series of two games credits two. The insert is the gate: the counter only
    moves for the caller that wins it, so a re-reported game, or the same game
    arriving twice, counts once -- a streak reset included. `mode` is stored
    but is not part of the key.

    `rows` maps str(player_id) -> that player's game row: `won`, `lost`,
    `play_gold` (the play gold the caller credited this player for this game,
    see PLAY_GOLD_KEY) and, for 1v1, everything `game_row_1v1` reads. A 2v2 or FFA game
    claims nothing for a 1v1-only kind (card, playstyle, Apex).

    WHERE IT IS CALLED. Inside the reporting transaction, after the game row
    and its gold are written, before the commit, in a savepoint of its own.
    Its WRITE FOOTPRINT is four tables: `title_ladder_credits`,
    `title_ladder_progress`, `players.active_title_id` (the auto-equip) and
    `player_items` (every granted rung goes through `main._grant_title_item`).

    WHAT IT DOES NOT CHECK. It does not know whether the game was ranked. The
    caller does, and calls only from a ranked game.

    A FIRST PROGRESS ROW starts at the highest tier of this ladder the player
    holds (at least the worn rung's), with the count at that tier's
    threshold: an owner of an existing title that became a higher rung starts
    there, and no rung at or below one they hold is granted or auto-equipped
    by a later game.

    LOCKING. Players are processed in canonical `str(pid)` order and the only
    row lock taken is `FOR NO KEY UPDATE` on `players` -- the weakest mode that
    still conflicts with this function's own later write of
    `active_title_id` (#202). The progress row is an upsert (it may not exist
    yet, and a gate on a row that does not exist locks nothing, #203/#207).
    Counts move by a delta (#326); the Apex best run moves by GREATEST over
    the stored run inside the same statement.
    """
    # Late import: `main` imports THIS module at its own module level, so a
    # module-level `from main import ...` here would be an import cycle.
    from main import _grant_title_item

    rows = {str(k): v for k, v in (rows or {}).items()}
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
        ld = LINES[line]
        kind = ld["kind"]
        if kind in ONE_V_ONE_KINDS and mode != "1v1":
            continue   # measured on the 1v1 row only: this game claims nothing
        game = rows.get(str(pid)) or {}

        claimed = (await db.execute(text(
            "INSERT INTO title_ladder_credits (player_id, reference_id, line, mode) "
            "VALUES (:pid, :ref, :line, :mode) "
            "ON CONFLICT (player_id, reference_id) DO NOTHING "
            "RETURNING 1"
        ), {"pid": pid, "ref": str(reference_id), "line": line, "mode": mode})).first()
        if claimed is None:
            continue   # this game already counted for this player

        # The tier a first progress row starts at: the highest rung of this
        # ladder the player HOLDS (the read route reports the same number),
        # never below the one being worn.
        held = [s for (s,) in (await db.execute(text(
            "SELECT si.sku FROM player_items pi "
            "  JOIN shop_items si ON si.id = pi.item_id "
            " WHERE pi.player_id = :pid AND si.sku = ANY(CAST(:skus AS text[]))"
        ), {"pid": pid, "skus": [r["sku"] for r in ld["rungs"]]})).all()]
        worn_tier = max([SKU_TO_RUNG[row[1]]["tier"]]
                        + [SKU_TO_RUNG[s]["tier"] for s in held if s in SKU_TO_RUNG])
        base = threshold(line, worn_tier)

        if kind == "streak":
            if game.get("won"):
                res = (await db.execute(text(
                    "INSERT INTO title_ladder_progress (player_id, line, games, tier, streak) "
                    "VALUES (:pid, :line, GREATEST(CAST(:base AS integer), 1), CAST(:wt AS integer), 1) "
                    "ON CONFLICT (player_id, line) DO UPDATE "
                    "   SET streak = title_ladder_progress.streak + 1, "
                    "       games = GREATEST(title_ladder_progress.games, "
                    "                        title_ladder_progress.streak + 1), "
                    "       tier = GREATEST(title_ladder_progress.tier, CAST(:wt AS integer)), "
                    "       updated_at = NOW() "
                    "RETURNING games, tier"
                ), {"pid": pid, "line": line, "base": base, "wt": worn_tier})).one()
            elif game.get("lost"):
                await db.execute(text(
                    "INSERT INTO title_ladder_progress (player_id, line, games, tier, streak) "
                    "VALUES (:pid, :line, CAST(:base AS integer), CAST(:wt AS integer), 0) "
                    "ON CONFLICT (player_id, line) DO UPDATE "
                    "   SET streak = 0, "
                    "       tier = GREATEST(title_ladder_progress.tier, CAST(:wt AS integer)), "
                    "       updated_at = NOW()"
                ), {"pid": pid, "line": line, "base": base, "wt": worn_tier})
                continue   # a loss never raises the best run
            else:
                continue
        else:
            if kind == "gold":
                delta = play_gold_of(game)   # the caller's per-game scalar
            else:
                delta = counted_delta(line, game)
            if delta <= 0:
                continue   # claimed, counts nothing: the game is spent for this player
            res = (await db.execute(text(
                "INSERT INTO title_ladder_progress (player_id, line, games, tier) "
                "VALUES (:pid, :line, CAST(:base AS integer) + CAST(:d AS integer), CAST(:wt AS integer)) "
                "ON CONFLICT (player_id, line) DO UPDATE "
                "   SET games = title_ladder_progress.games + CAST(:d AS integer), "
                "       tier = GREATEST(title_ladder_progress.tier, CAST(:wt AS integer)), "
                "       updated_at = NOW() "
                "RETURNING games, tier"
            ), {"pid": pid, "line": line, "base": base, "d": delta, "wt": worn_tier})).one()

        games, tier_before = res
        earned = tier_for_games(line, games)
        if earned <= tier_before:
            continue

        # Grant every rung CROSSED, not just the top one. A hole in the middle
        # of a ladder is not repairable by playing on -- the player is already
        # past that threshold for ever.
        granted = []
        reached = tier_before
        for t in range(tier_before + 1, earned + 1):
            missing = []
            for r in rungs_at_tier(line, t):
                if await _grant_title_item(db, pid, r["sku"]):
                    granted.append(r["sku"])
                else:
                    missing.append(r["sku"])
            if missing:
                # STOP at the last tier actually held; the count keeps
                # climbing and the next credited game retries (#276).
                print(f"[LADDER] {line} tier {t} NOT granted to {pid}: "
                      f"{missing} absent from shop_items. Holding at tier "
                      f"{reached}; the next credited game retries.")
                break
            reached = t

        if reached == tier_before:
            continue   # nothing landed: no tier write, no equip, no event
        earned = reached

        await db.execute(text(
            "UPDATE title_ladder_progress SET tier = GREATEST(tier, :t), updated_at = NOW() "
            " WHERE player_id = :pid AND line = :line"
        ), {"t": earned, "pid": pid, "line": line})

        # Auto-equip the new top rung. `row[1]` was read under the FOR NO KEY
        # UPDATE this transaction still holds, and it was a rung of `line`.
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
            "line_display": ld["display"],
            "games": games,
            "from_tier": tier_before,
            "to_tier": earned,
            "from_name": (rungs_at_tier(line, tier_before) or [{}])[0].get("name"),
            "to_name": top[0]["name"] if top else None,
            "granted_skus": granted,
            "equipped_sku": equipped_sku,
        })
    return events


# -- The build word main.py derives from the hook ---------------------

_HOOK_NAME = record_completed_games.__name__


def hooked_site_count(functions) -> int:
    """How many of `functions` load the name record_completed_games in their
    own compiled code (a call does; a comment or a docstring does not).
    main.py binds its /health `ladder_hook` word to this."""
    return sum(1 for fn in functions if _HOOK_NAME in fn.__code__.co_names)


# -- The read route -----------------------------------------------------

@router.get("/api/v1/players/{steam_id}/title-ladders")
async def get_title_ladders(steam_id: str, db: AsyncSession = Depends(get_db)):
    """Every ladder, what this player owns on it, and how far to the next
    rung. Pure read -- safe on the read replica.

    THE ANSWER'S SHAPE IS APPEND-ONLY. The client parses it with depth-aware
    manual string splitting (ApiClient.ParseTitleLadders); every key an older
    client reads keeps its name, object and meaning. Appended in the title
    ladders build: per ladder `group`, `kind`, `unit`, `modes`, `condition`,
    `streak`; per rung `reached`. `games` is the ladder's count in its own
    `unit`.

    Unknown steam_id is a 404 rather than an empty board.
    """
    # One snapshot per request: every read below sees the first SELECT's
    # snapshot, and READ ONLY makes any write here an error. Must stay first.
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
    from main import _auto_owned

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
        line: (games, tier, streak) for (line, games, tier, streak) in (await db.execute(text(
            "SELECT line, games, tier, streak FROM title_ladder_progress WHERE player_id = :pid"
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
        # The highest rung the player HOLDS on this ladder: an owner of an
        # existing title that became a higher rung is at that tier before
        # the first credited game writes a progress row.
        held = max([r["tier"] for r in ld["rungs"] if r["sku"] in owned_skus] or [1])
        if line in progress:
            games, tier, streak = progress[line]
            tier = max(tier, held)
        else:
            tier = held
            games, streak = threshold(line, tier), 0
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
                "owned": r["sku"] in owned_skus or _auto_owned(steam_id, r["sku"]),
                "active": r["sku"] == active_sku,
                # appended (title ladders build)
                "reached": r["tier"] <= tier,
            } for r in ld["rungs"]],
            # appended (title ladders build)
            "group": ld["group"],
            "kind": ld["kind"],
            "unit": ld["unit"],
            "modes": ld["modes"],
            "condition": ld["condition"],
            "streak": streak if ld["kind"] == "streak" else None,
        })
    return {"steam_id": steam_id, "active_line": line_of_sku(active_sku), "ladders": out}
