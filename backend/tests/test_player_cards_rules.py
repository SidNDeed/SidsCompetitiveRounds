"""Player Cards — the pure rules (backend/api/player_cards.py), executed.

Every property Nic was firm on has a test AND a negative control: the band
edges, the never-up fallback, the independence of the three per-print rolls,
the exclusive sweep, and the determinism of the earned roll. The migration
that carries the immutability trigger is pinned by text.
"""

import os
import random
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import player_cards as pc  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


class _Rng:
    """A scripted rng: random() pops from a list (values in [0, 1)),
    randrange(n) returns the next scripted index modulo n."""

    def __init__(self, randoms, indexes=None):
        self.randoms = list(randoms)
        self.indexes = list(indexes or [])

    def random(self):
        return self.randoms.pop(0)

    def randrange(self, n):
        v = self.indexes.pop(0) if self.indexes else 0
        return v % n


# ── bands ──

@pytest.mark.parametrize("rank,rarity", [
    (1, "legendary"), (2, "epic"), (10, "epic"), (11, "rare"), (20, "rare"),
    (21, "uncommon"), (40, "uncommon"), (41, "common"), (4818, "common"),
])
def test_band_edges_are_the_fixed_ones(rank, rarity):
    assert pc.rarity_for_rank(rank) == rarity


def test_tier_odds_sum_to_one_hundred():
    assert abs(sum(pc.PC_ECONOMY["tier_pct"].values()) - 100.0) < 1e-9


@pytest.mark.parametrize("r,rarity", [
    (0.0, "legendary"), (0.0049, "legendary"), (0.005, "epic"), (0.0399, "epic"),
    (0.04, "rare"), (0.1499, "rare"), (0.15, "uncommon"), (0.3999, "uncommon"),
    (0.40, "common"), (0.999999, "common"),
])
def test_rarity_roll_maps_the_unit_interval_to_the_percentages(r, rarity):
    assert pc.roll_rarity(_Rng([r])) == rarity


def test_rarity_roll_distribution_matches_the_odds_within_tolerance():
    rng = random.Random(1234)
    n = 200_000
    counts = {k: 0 for k in pc.RARITIES}
    for _ in range(n):
        counts[pc.roll_rarity(rng)] += 1
    for k, pct in pc.PC_ECONOMY["tier_pct"].items():
        assert abs(counts[k] / n * 100.0 - pct) < max(0.25, pct * 0.15), (k, counts[k])


# ── fallback: one band down, then further down, never up ──

def test_fallback_uses_the_rolled_band_when_it_has_members():
    assert pc.fall_back("epic", {"epic", "common"}) == "epic"


def test_fallback_goes_down_one_band_then_further_down():
    assert pc.fall_back("legendary", {"epic", "common"}) == "epic"
    assert pc.fall_back("legendary", {"rare", "common"}) == "rare"
    assert pc.fall_back("epic", {"common"}) == "common"


def test_fallback_never_goes_up():
    # Negative control: Rare rolled, only Epic and Legendary available -> nothing.
    assert pc.fall_back("rare", {"epic", "legendary"}) is None
    assert pc.fall_back("common", {"uncommon"}) is None


def test_roll_slot_is_none_only_when_no_band_at_or_below_has_members():
    assert pc.roll_slot(_Rng([0.5]), {"common": 0, "uncommon": 0}) is None
    assert pc.roll_slot(_Rng([0.5]), {}) is None
    # Common rolled (0.5) with an empty Common band and members only above -> None.
    assert pc.roll_slot(_Rng([0.5]), {"common": 0, "rare": 3}) is None
    # ...but a Rare roll (0.1) with the same sizes lands in Rare.
    assert pc.roll_slot(_Rng([0.1], [2]), {"common": 0, "rare": 3}) == ("rare", "rare", 2)


def test_roll_slot_index_is_inside_the_used_band():
    rolled, used, idx = pc.roll_slot(_Rng([0.0], [7]), {"legendary": 0, "epic": 4, "common": 100})
    assert (rolled, used) == ("legendary", "epic") and 0 <= idx < 4


# ── foil / signed: independent rolls ──

def test_flags_are_two_independent_rolls():
    assert pc.roll_flags(_Rng([0.0049, 0.9])) == (True, False)
    assert pc.roll_flags(_Rng([0.9, 0.00049])) == (False, True)
    assert pc.roll_flags(_Rng([0.0, 0.0])) == (True, True)
    # Negative control: exactly at the threshold is a miss.
    assert pc.roll_flags(_Rng([0.005, 0.0005])) == (False, False)


def test_shard_values_are_by_rarity_only():
    assert [pc.shards_for(r) for r in pc.RARITIES] == [5, 15, 40, 150, 600]


# ── earned packs: deterministic, exclusive sweep ──

def test_earned_roll_is_deterministic_and_keyed_by_mode_and_reference():
    a = pc.earned_roll(b"k", "1v1", "s1")
    assert a == pc.earned_roll(b"k", "1v1", "s1")
    assert 0 <= a < 10000
    assert pc.earned_roll(b"k", "team", "s1") != a or pc.earned_roll(b"k", "1v1", "s2") != a
    assert pc.earned_roll(b"other", "1v1", "s1") != a or pc.earned_roll(b"other", "1v1", "s3") != a


def test_sweep_is_exclusive_and_the_1v1_sweep_is_certain():
    # 1v1 sweep = 100 %: every reference grants the sweep pack.
    for i in range(50):
        assert pc.earned_pack_kind(b"k", "1v1", f"s{i}", sweep=True) == "sweep"
    # The win roll at 20 % / the half-odds modes: the empirical rate matches.
    n = 4000
    wins = sum(1 for i in range(n) if pc.earned_pack_kind(b"k", "1v1", f"w{i}", sweep=False) == "win")
    assert 0.16 * n < wins < 0.24 * n, wins
    sweeps = sum(1 for i in range(n) if pc.earned_pack_kind(b"k", "team", f"t{i}", sweep=True) == "sweep")
    assert 0.45 * n < sweeps < 0.55 * n, sweeps
    # Negative controls: a sweep never yields 'win'; an unknown mode yields nothing.
    assert all(pc.earned_pack_kind(b"k", "team", f"t{i}", sweep=True) != "win" for i in range(200))
    assert pc.earned_pack_kind(b"k", "duel", "x", sweep=True) is None


# ── canonical strings ──

def test_every_operation_term_is_inside_its_signed_string():
    assert pc.canon_open_purchase("7", "n1", "gold", 100) == "pcopen:7:n1:gold:100"
    assert pc.canon_open_pack("7", "p1") == "pcopen:7:pack:p1"
    assert pc.canon_result("7", "n1") == "pcresult:7:n1"
    assert pc.canon_daily("7", "n2") == "pcdaily:7:n2"
    assert pc.canon_discard("7", "pr1") == "pcdiscard:7:pr1"
    assert pc.canon_settings("7", "n3", 4, "opted_out", 1) == "pcset:7:n3:4:opted_out:1"
    assert pc.canon_read("7", "collection", "8") == "pcread:7:collection:8"


# ── migration 308 pins ──

def test_migration_308_carries_the_immutability_trigger_and_every_frozen_column():
    sql = open(os.path.join(ROOT, "backend", "sql", "308_player_cards.sql"), encoding="utf-8").read()
    assert sql.count("BEGIN;") == 1 and sql.count("COMMIT;") == 1
    assert "BEFORE the api" in sql
    assert "CREATE TRIGGER pc_prints_immutable BEFORE UPDATE ON pc_prints" in sql
    frozen = ["id", "card_id", "minted_at", "snapshot_id", "rarity", "foil", "signed", "pool_rank",
              "rating", "peak_rating", "board_rank", "series_wins", "series_losses", "top_card",
              "title", "source", "pack_id", "slot"]
    for col in frozen:
        assert f"NEW.{col} IS DISTINCT FROM OLD.{col}" in sql, col
    # The mutable trio is NOT in the frozen list.
    for col in ("owner_player_id", "discarded_at", "discard_shards"):
        assert f"NEW.{col} IS DISTINCT FROM OLD.{col}" not in sql.split("IF OLD.discarded_at IS NOT NULL")[0], col
    assert "a discarded print cannot change" in sql
    for needle in (
        "pc_editions_one_active ON pc_editions ((1)) WHERE ended_at IS NULL",
        "pc_packs_player_nonce ON pc_packs (player_id, nonce) WHERE nonce IS NOT NULL",
        "pc_packs_player_source_ref ON pc_packs (player_id, source, reference_id) WHERE reference_id IS NOT NULL",
        "PRIMARY KEY (player_id, claimed_on)",
        "pc_shards INTEGER NOT NULL DEFAULT 0",
        "pc_opted_out_at TIMESTAMPTZ NULL",
        "pc_settings_revision INTEGER NOT NULL DEFAULT 0",
    ):
        assert needle in sql, needle
