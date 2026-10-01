"""The connect-failure lane's Steam64-shaped fixture values decode as
non-individual SteamID64s: account type nibble != 1.

A SteamID64 packs universe (bits 56-63), account type (bits 52-55),
instance (bits 32-51) and account number (bits 0-31). Individual accounts
are type 1 (steamid64.py), so a value whose type nibble is not 1 is not an
individual account id by construction, whatever account numbers exist.

The checks:
- every fixture base constant the lane's tests import, the discord
  collection harness's included, over the whole span the fixtures add to it
  (the span stays inside one high word, so one decode covers every id in it);
- a sweep of the lane's test sources, the harness included: every 17-digit
  literal beginning 765 decodes as type != 1. A failure names the file, the
  line and the decoded nibble, never the value;
- the production pool predicate (steamid64.is_individual_id, and the
  interval main._PC_POOL_STEAM_ID_SQL carries) refuses the harness's block;
- the harness's injected predicate admits that block only while its
  MonkeyPatch is open, and the production predicate is back after it.
"""
import ast
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import cf_asm  # noqa: E402
import discord_collection_harness as H  # noqa: E402
import steamid64  # noqa: E402
import test_group_region_issuance  # noqa: E402

INDIVIDUAL_TYPE = 1

# The largest offset any fixture adds to cf_asm.STEAM_BASE is 999999 (a
# stranger id) and 900000 + serial * 20 + 19 (the second pool); 10**7
# covers every serial below 455000.
CF_ASM_SPAN = 10 ** 7

# The lane's test sources: every backend/tests .py file the lane adds or
# edits against trunk, plus the trunk test file the lane's runs include.
LANE_SOURCES = (
    "cf_asm.py",
    "cf_controls.py",
    "cf_controls_client.py",
    "cf_controls_rows.py",
    "cf_pg.py",
    "cf_pool.py",
    "discord_collection_harness.py",
    "test_cf_fixture_steam_ids.py",
    "test_ffa_assembly_client_structure.py",
    "test_ffa_assembly_pg.py",
    "test_ffa_leave_cause.py",
    "test_ffa_shutout_finishing_count.py",
    "test_group_region_issuance.py",
    "test_route_manifest_net_seat.py",
    "test_sept16_dc_fallback_shape.py",
)

_STEAM64_SHAPED = re.compile(r"(?<![0-9])765[0-9]{14}(?![0-9])")


def type_nibble(value):
    return (int(value) >> 52) & 0xF


def high_word(value):
    return int(value) >> 32


def harness_block():
    return H.STEAM_BASE, H.STEAM_BASE + H.STEAM_SPAN - 1


def test_the_type_nibble_decode_reads_steamid64s_own_interval():
    # The decode itself, against steamid64's bounds: both ends of the
    # individual interval are type 1, and the id just below it is not.
    assert type_nibble(steamid64.INDIVIDUAL_MIN) == INDIVIDUAL_TYPE
    assert type_nibble(steamid64.INDIVIDUAL_MAX) == INDIVIDUAL_TYPE
    assert type_nibble(steamid64.INDIVIDUAL_MIN - (1 << 32)) == INDIVIDUAL_TYPE
    assert type_nibble((1 << 56) | (1 << 52)) == INDIVIDUAL_TYPE
    assert type_nibble((1 << 56) | ((1 << 52) - 1)) == 0


def test_every_lane_fixture_base_is_not_an_individual_id():
    bases = {
        "cf_asm.STEAM_BASE": (cf_asm.STEAM_BASE, CF_ASM_SPAN),
        "test_group_region_issuance.STEAM": (int(test_group_region_issuance.STEAM), 0),
        "discord_collection_harness.STEAM_BASE": (H.STEAM_BASE, H.STEAM_SPAN - 1),
    }
    bad = []
    for name, (base, span) in bases.items():
        if high_word(base) != high_word(base + span):
            bad.append("%s: the span crosses a high word" % name)
        if type_nibble(base) == INDIVIDUAL_TYPE:
            bad.append("%s: type nibble %d" % (name, type_nibble(base)))
        if steamid64.is_individual_id(str(base)) or steamid64.is_individual_id(str(base + span)):
            bad.append("%s: inside the individual interval" % name)
    assert not bad, bad


def test_no_lane_source_literal_decodes_as_an_individual_id():
    bad = []
    for name in LANE_SOURCES:
        path = os.path.join(HERE, name)
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                for m in _STEAM64_SHAPED.finditer(line):
                    nib = type_nibble(m.group(0))
                    if nib == INDIVIDUAL_TYPE:
                        bad.append("%s:%d type nibble %d" % (name, lineno, nib))
    assert not bad, bad


def test_the_production_pool_predicate_rejects_the_harness_block():
    lo, hi = harness_block()
    assert H.steam_of(0) == str(lo) and H.steam_of(H.STEAM_SPAN - 1) == str(hi)
    for v in (lo, lo + 1, (lo + hi) // 2, hi):
        assert not steamid64.is_individual_id(str(v))
    # The SQL reader: the literal main.py assigns to _PC_POOL_STEAM_ID_SQL,
    # read from the source so this test needs no import of main.
    with open(os.path.join(HERE, "..", "api", "main.py"), encoding="utf-8") as f:
        lines = [ln for ln in f if ln.startswith("_PC_POOL_STEAM_ID_SQL = ")]
    assert len(lines) == 1, len(lines)
    sql = ast.literal_eval(lines[0].split("=", 1)[1].strip())
    assert sql == steamid64.individual_id_sql("p.steam_id")
    found = re.findall(r"BETWEEN ([0-9]+) AND ([0-9]+)", sql)
    assert len(found) == 1, len(found)
    pmin, pmax = (int(x) for x in found[0])
    assert (pmin, pmax) == (steamid64.INDIVIDUAL_MIN, steamid64.INDIVIDUAL_MAX)
    assert hi < pmin or lo > pmax


def test_the_harness_predicate_admits_its_block_only_inside_its_monkeypatch():
    import main
    lo, hi = harness_block()
    prod_sql = steamid64.individual_id_sql("p.steam_id")
    assert main._PC_POOL_STEAM_ID_SQL == prod_sql
    with pytest.MonkeyPatch.context() as mp:
        sites = H.inject_pool_predicate(mp)
        assert "main._PC_POOL_STEAM_ID_SQL" in sites and "main._PC_POOL_MEMBER_SQL" in sites, sites
        assert steamid64.is_individual_id(str(lo)) and steamid64.is_individual_id(str(hi))
        assert not steamid64.is_individual_id(str(lo - 1)) and not steamid64.is_individual_id(str(hi + 1))
        assert "BETWEEN %d AND %d" % (lo, hi) in main._PC_POOL_STEAM_ID_SQL
        assert "BETWEEN %d AND %d" % (lo, hi) in main._PC_POOL_MEMBER_SQL
    assert main._PC_POOL_STEAM_ID_SQL == prod_sql
    assert steamid64.individual_id_sql("p.steam_id") == prod_sql
    assert not steamid64.is_individual_id(str(lo)) and not steamid64.is_individual_id(str(hi))
