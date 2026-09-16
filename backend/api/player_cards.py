"""Player Cards — the pure rules (no I/O, no clock).

Everything a pack open, a discard, an earned-pack grant or the pool snapshot
decides is decided here, from explicit inputs, so the endpoints in main.py
only move rows and money and the tests exercise the rule itself:

  * ``PC_ECONOMY`` — every tunable in one place (prices, cap, odds, shard
    values, band edges, earned-pack odds).
  * ``rarity_for_rank`` — the fixed bands: Legendary = pool ranks 1-2, Epic
    3-10, Rare 11-20, Uncommon 21-40, Common 41+. (Legendary was rank 1 alone
    until the Sept 14 batch; this line is recomputed from ``band_max_rank`` by
    test_player_cards_rules.py, so it cannot go stale again.)
  * ``roll_slot`` — one print: an independent band roll, then the band
    actually used (the rolled band, else ONE band down, then further down —
    never up; None when the pool is empty), then a uniform index inside it.
  * ``roll_flags`` — foil and signed are two further independent rolls per
    print (nothing about the band changes their odds).
  * ``earned_pack_kind`` — the deterministic earned-pack roll from an HMAC of
    ``{mode}:{reference_id}``: 'win' or None at that mode's odds, with
    nothing about the score line as an input (the 2-0 sweep roll was removed
    in v4.13).
  * the canonical strings every signed request carries.

No pity, no floors, no streaks. A print's rolled fields are fixed at the pull
and no api path writes them again: the ``pc_prints_immutable`` trigger refuses
any UPDATE that touches one. The single documented exception is a migration
that disables that trigger for its own transaction and proves it re-armed
before committing -- ``backend/sql/321_pc_rank2_legendary.sql``, the one-time
band conversion of the rank-2 prints minted while Legendary was rank 1 alone.
"""

import hashlib
import hmac

RARITIES = ("common", "uncommon", "rare", "epic", "legendary")   # ascending

PC_ECONOMY = {
    "pack_price_gold": 100,
    "pack_price_shards": 100,
    "paid_packs_per_day": 5,
    "prints_per_pack": 5,
    # Band odds per print, in percent. They sum to 100.
    "tier_pct": {"common": 60.0, "uncommon": 25.0, "rare": 11.0, "epic": 3.5, "legendary": 0.5},
    # Independent per-print rolls, in percent (1 in 200; 1 in 2000).
    "foil_pct": 0.5,
    "signed_pct": 0.05,
    # Shards a discarded print is worth — by the PRINT's rarity, nothing else.
    "shards": {"common": 5, "uncommon": 15, "rare": 40, "epic": 150, "legendary": 600},
    # Highest pool rank of each band; Common is everything past Uncommon.
    # Legendary is the top TWO since the Sept 14 batch (one before): the pool
    # is now the players who have run the mod, and its second place is a
    # Legendary card too (product owner, 2026-09-13). The rank-2 prints minted
    # before this line are converted by backend/sql/321_pc_rank2_legendary.sql,
    # which must run AFTER the deploy that carries it (#236).
    "band_max_rank": {"legendary": 2, "epic": 10, "rare": 20, "uncommon": 40},
    # Earned packs: per ranked mode, the percent chance that the earned-pack
    # roll of a won ranked series (a won ranked FFA match) hits; a mode not
    # listed earns none. One roll whatever the score line: there is no 2-0
    # sweep roll (removed in v4.13, 2026-09-14, review round 14 -- the Sept 14
    # branch still carried the (win, sweep) tuple form and the flat odds are
    # the later decision). Pack rows the sweep roll wrote before then keep
    # kind 'sweep'.
    "earned_pct": {"1v1": 20.0, "team": 20.0, "ovt": 20.0, "ffa": 20.0},
    # A rolled subject that left the pool since the snapshot is re-rolled this
    # many times before the open is rejected as pool_changed (before any debit).
    "reroll_attempts": 3,
    "snapshot_keep": 14,
}

PACK_PAY = ("gold", "shards")
# No opt-out and no picture choice (2026-09-13): no player leaves the pool by
# choice. Who IS a subject is main._PC_POOL_MEMBER_SQL's word, and since the
# 2026-09-15 merge (_PC_POOL_RULE = 3) that word is the INTERSECTION of two
# decisions: an unbanned, undeleted player who has run the mod (mod_seen_at
# set, 2026-09-13) AND whose id is a public individual SteamID64 (v4.13).
# Every card carries a picture, and deleting all data is the one way such a
# player's card leaves the binders.
SETTINGS_KEYS = ("collection_public", "announce")


def rarity_for_rank(pool_rank: int) -> str:
    """The fixed band of a pool rank (1-based)."""
    edges = PC_ECONOMY["band_max_rank"]
    if pool_rank <= edges["legendary"]:
        return "legendary"
    if pool_rank <= edges["epic"]:
        return "epic"
    if pool_rank <= edges["rare"]:
        return "rare"
    if pool_rank <= edges["uncommon"]:
        return "uncommon"
    return "common"


def roll_rarity(rng) -> str:
    """One weighted band roll (``rng.random()`` in [0, 1))."""
    r = rng.random() * 100.0
    acc = 0.0
    for name in ("legendary", "epic", "rare", "uncommon", "common"):
        acc += PC_ECONOMY["tier_pct"][name]
        if r < acc:
            return name
    return "common"


def fall_back(rarity: str, available) -> str | None:
    """The band actually used for a roll of ``rarity``: itself when it has
    members, else the next band DOWN, and so on to Common. Never up. None
    when no band at or below it has a member."""
    i = RARITIES.index(rarity)
    for j in range(i, -1, -1):
        if RARITIES[j] in available:
            return RARITIES[j]
    return None


def roll_flags(rng) -> tuple[bool, bool]:
    """(foil, signed) — two independent rolls."""
    foil = rng.random() * 100.0 < PC_ECONOMY["foil_pct"]
    signed = rng.random() * 100.0 < PC_ECONOMY["signed_pct"]
    return foil, signed


def roll_slot(rng, band_sizes: dict) -> tuple[str, str, int] | None:
    """One print from a snapshot whose bands hold ``band_sizes[rarity]``
    members: (rolled rarity, rarity used, uniform index inside the used
    band). None when the pool is empty."""
    rolled = roll_rarity(rng)
    available = {k for k, n in band_sizes.items() if n and n > 0}
    used = fall_back(rolled, available)
    if used is None:
        return None
    return rolled, used, rng.randrange(band_sizes[used])


def shards_for(rarity: str) -> int:
    return int(PC_ECONOMY["shards"][rarity])


def earned_roll(secret: bytes, mode: str, reference_id: str) -> int:
    """Deterministic 0..9999 from HMAC-SHA256(secret, "{mode}:{reference_id}")."""
    digest = hmac.new(secret, f"{mode}:{reference_id}".encode(), hashlib.sha256).digest()
    return int.from_bytes(digest[:4], "big") % 10000


def earned_pack_kind(secret: bytes, mode: str, reference_id: str) -> str | None:
    """'win' | None: one roll at the mode's odds; None for a mode that earns
    nothing. The word is what an earned pack row's ``kind`` stores. Nothing
    about the series' score line is an input."""
    pct = PC_ECONOMY["earned_pct"].get(mode)
    if pct is None:
        return None
    return "win" if earned_roll(secret, mode, reference_id) < pct * 100 else None


# ── canonical strings (every term of an operation is inside the signed string) ──

def canon_open_purchase(steam_id: str, nonce: str, pay: str, expected_price: int) -> str:
    return f"pcopen:{steam_id}:{nonce}:{pay}:{expected_price}"


def canon_open_pack(steam_id: str, pack_id: str) -> str:
    return f"pcopen:{steam_id}:pack:{pack_id}"


def canon_result(steam_id: str, ref: str) -> str:
    return f"pcresult:{steam_id}:{ref}"


def canon_daily(steam_id: str, nonce: str) -> str:
    return f"pcdaily:{steam_id}:{nonce}"


def canon_discard(steam_id: str, print_id: str) -> str:
    return f"pcdiscard:{steam_id}:{print_id}"


def canon_settings(steam_id: str, nonce: str, revision: int, key: str, value: int) -> str:
    return f"pcset:{steam_id}:{nonce}:{revision}:{key}:{value}"


def canon_portrait(steam_id: str, nonce: str, upload_sha256: str, descriptor: str) -> str:
    """The portrait writer's signed line: the server hashes the RECEIVED body
    itself (upload_sha256), so a body cannot be swapped under a signature."""
    return f"pcport:{steam_id}:{nonce}:{upload_sha256}:{descriptor}"


def canon_read(steam_id: str, what: str, target: str) -> str:
    return f"pcread:{steam_id}:{what}:{target}"
