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
  * ``PC_TRADE`` -- every trading tunable (caps, cooldowns, windows,
    the traded discard value) -- and ``trade_items`` / ``trade_digest``,
    the canonical item list of a trade and its SHA-256, which the
    client mirrors byte for byte.

No pity, no floors, no streaks. A print's rolled fields are fixed at the pull
and no api path writes them again: the ``pc_prints_immutable`` trigger refuses
any UPDATE that touches one. The single documented exception is a migration
that disables that trigger for its own transaction and proves it re-armed
before committing -- ``backend/sql/321_pc_rank2_legendary.sql``, the one-time
band conversion of the rank-2 prints minted while Legendary was rank 1 alone.
"""

import hashlib
import hmac
import uuid as _uuid

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

# Card trading (migration 353): cards for cards between two players and
# nothing else. The server enforces every value; the client only displays
# them, read from the bounds of the full trades read, and hardcodes none.
PC_TRADE = {
    "enabled": True,                    # the kill switch for propose and accept (3.13)
    "prints_per_side_max": 3,           # Q2
    "ttl_hours": 48,                    # Q3
    "open_sent_max": 5,                 # open proposals one player has sent
    "open_received_max": 10,            # open proposals one player can be sent
    "proposals_per_day": 20,            # proposals one player may create per UTC day
    "executed_per_day": 5,              # executed trades per player per UTC day, either role; reversed ones count (Q1)
    "executed_per_pair_day": 2,         # executed trades per pair per UTC day (Q1)
    "decline_cooldown_hours": 24,       # a declined proposer to that receiver (Q5)
    "reversal_window_minutes": 60,      # the admin window AND the re-trade freeze on a moved print
    "reversal_cooldown_hours": 72,      # both parties of a reversed trade (Q5)
    "min_ranked_series": 3,             # Q6
    "min_mod_age_days": 7,              # Q6
    "traded_discard_shards": 0,         # shards for discarding a print ever received by trade, any rarity (Q7, ruled)
    "recent_days": 7,                   # closed trades the full read returns
    "retention_closed_days": 30,
    "retention_executed_days": 180,
}

PACK_PAY = ("gold", "shards")
# No opt-out and no picture choice (2026-09-13): no player leaves the pool by
# choice. Who IS a subject is main._PC_POOL_MEMBER_SQL's word, and since the
# 2026-09-15 merge (_PC_POOL_RULE = 3) that word is the INTERSECTION of two
# decisions: an unbanned, undeleted player who has run the mod (mod_seen_at
# set, 2026-09-13) AND whose id is a public individual SteamID64 (v4.13).
# Every card carries a picture, and deleting all data is the one way such a
# player's card leaves the binders.
# trades_open (migration 353) is the trader-side consent of card trading;
# like the other two it moves no picture and takes no card out of a binder.
SETTINGS_KEYS = ("collection_public", "announce", "trades_open")


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


# -- card trading: the canonical item list, its digest, the signed term --

def trade_items(steam_id: str, give, to: str, get) -> str:
    """The canonical item list of a trade in which `steam_id` gives the prints
    `give` and `to` gives the prints `get`:

        items = "pctl1|" + block(X) + "|" + block(Y)
        block = steam_id + ":" + ",".join(print ids this party gives, ascending)

    X and Y are the two parties in ascending steam id text order (both are
    17-digit SteamID64 strings, so text order is numeric order), and every id
    is its lowercase 8-4-4-4-12 text. The client builds the same string with
    Guid.ToString("D"). Raises ValueError on an id that is not a UUID."""
    def block(party, ids):
        return str(party) + ":" + ",".join(sorted(str(_uuid.UUID(str(v))) for v in ids))
    first, second = sorted(((str(steam_id), give), (str(to), get)), key=lambda side: side[0])
    return "pctl1|" + block(*first) + "|" + block(*second)


def trade_digest(items: str) -> str:
    """Lowercase hex SHA-256 of the ASCII bytes of the canonical item list."""
    return hashlib.sha256(items.encode("ascii")).hexdigest()


def canon_trade(steam_id: str, nonce: str, action: str, target: str, digest: str) -> str:
    """The signed term of every trade action: `target` is the counterparty's
    steam id for a propose (no trade id exists yet) and the trade id for an
    accept, a decline or a cancel. Every field but the nonce has a fixed
    format with no colon, and the nonce's grammar excludes it too, so the
    string is injective."""
    return f"pctrade:{steam_id}:{nonce}:{action}:{target}:{digest}"
