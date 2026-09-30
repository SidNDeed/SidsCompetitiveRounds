"""The connect-failure lane's Steam64-shaped fixture values decode as
non-individual SteamID64s: account type nibble != 1.

A SteamID64 packs universe (bits 56-63), account type (bits 52-55),
instance (bits 32-51) and account number (bits 0-31). Individual accounts
are type 1 (steamid64.py), so a value whose type nibble is not 1 is not an
individual account id by construction, whatever account numbers exist.

Two checks, each on the decode alone:
- every fixture base constant the lane's tests import, over the whole span
  the fixtures add to it (the span stays inside one high word, so one
  decode covers every id in it);
- a sweep of the lane's test sources: every 17-digit literal beginning 765
  decodes as type != 1. A failure names the file, the line and the decoded
  nibble, never the value.

The discord collection harness's STEAM_BASE is the one base that is type 1
on purpose: the pc pool's range check (steamid64.is_individual_id) admits
only individual ids, so its fixtures must be inside that interval. It is
not a base of this lane; the last test pins that it is inside the interval,
which is the reason it is exempt, and nothing else about it.
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import cf_asm  # noqa: E402
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


def test_the_discord_harness_base_is_type_1_because_the_pool_requires_it():
    path = os.path.join(HERE, "discord_collection_harness.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    values = [n.value.value for n in ast.walk(tree)
              if isinstance(n, ast.Assign) and len(n.targets) == 1
              and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "STEAM_BASE"
              and isinstance(n.value, ast.Constant)]
    assert len(values) == 1, len(values)
    assert steamid64.is_individual_id(str(values[0]))
