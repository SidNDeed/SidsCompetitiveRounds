"""Admin evidence report, phase 2 (ship-gate row B10): the required behaviours
of review round B10-R1 (ruling B10-A2), each proven by a test here that fails
on the reviewed tip 6348207e and passes at the fix.

  H1  every admitted section value reaches the body whole: a genuine
      64-character deal profile (card_measures.deal_profile) is shown in full
      at its seat and in its contribution; a switch value and the fault words
      too.
  H2  contributions are selected by the game's stored identity and their
      subject, independent of the subject's own record: a seat with no record
      shows the stored contribution about it in its game facts and its
      window totals, and keeps its `no_record` state.
  H3  a record is included only when its own attach key is the report game's
      room (seat_evidence.attached_records, the workers' rule); a record of
      the same stable key and pair naming another room is excluded and
      counted in `other_game`.
  H4  association carries the pair: another pair's games row under the same
      stable key neither attaches nor holds back this pair's records, and
      another pair's contribution about the same subject is not this game's.
  M1  fact lines fit the rendered width (a 217-character line is wrapped),
      and a drawing that reaches past the image edge gives the complete text
      fallback.
"""

import asyncio
import copy
import hashlib
import json
import os
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import aer_render_worker as worker  # noqa: E402
import card_measures  # noqa: E402
from test_admin_evidence_sections import (T0, _data, _facts, _game, _grow, _on,  # noqa: E402
                                          _pair, _rec, ae)
from test_discord_evidence_bot import ADMIN, _Api, _Interaction, bot_ns, game_body  # noqa: E402
from test_discord_evidence_render import PNG, REQ, check_plan  # noqa: E402


def _crow(src, key, a, b, subject, **cols):
    """A stored contribution row of pair (a, b) about `subject`, carrying the
    table's identity columns (stable_game_key, pair_lo, pair_hi)."""
    lo, hi = sorted((a, b))
    row = {"stable_game_key": key, "pair_lo": lo, "pair_hi": hi, "subject_player_id": subject,
           "source": "self", "coverage": "one", "computed_at": T0}
    row.update({c: 0 for c in ae._SECTION_SPEC[src]["contrib_cols"]})
    if src == "combat":
        row["sums"] = "{}"
    row.update(cols)
    return row


def _seat(section, i):
    return section["seats"][i]["state"], _facts(section["seats"][i]["facts"])


# ── H1: section values whole ───────────────────────────────────────────────

def _profile(tag):
    """A genuine deal profile: card_measures' own function over a record."""
    rec = {"prof": [tag] * 9, "pool": ["ok", hashlib.sha256(tag.encode()).hexdigest()],
           "ns": 12}
    return card_measures.deal_profile(rec)


def test_h1_a_64_character_deal_profile_reaches_the_body_whole():
    a, b = _pair()
    g = _game(a, b)
    pa, pc = _profile("seat-a"), _profile("contrib-a")
    assert len(pa) == len(pc) == 64
    long_switch = "1" + "0" * 99
    faults = {"f%02d_%s" % (i, "x" * 20): 1 for i in range(6)}
    data = _data(records=[_rec("card", "k1", a, b, "room-1", deal_profile=pa)],
                 games=[_grow("card", "k1", a, b, g["id"])],
                 contrib=[_crow("card", "k1", a, b, a, deal_profile=pc, hands=3)],
                 switches=dict(_on("card"), card_evidence_worker=long_switch))
    s = ae.game_section("card", data, g, {a: 0, b: 1})
    _state, fa = _seat(s, 0)
    assert fa["deal_profile"] == pa, fa["deal_profile"]
    assert fa["contrib1.deal_profile"] == pc, fa["contrib1.deal_profile"]
    assert _facts(s["game"])["worker"] == long_switch
    cdata = _data(records=[_rec("combat", "k1", a, b, "room-1")],
                  games=[_grow("combat", "k1", a, b, g["id"], record_faults=json.dumps(faults))])
    words = _facts(ae.game_section("combat", cdata, g, {a: 0, b: 1})["game"])["record_faults"]
    assert words == ",".join(sorted(faults)) and len(words) > 48, words
