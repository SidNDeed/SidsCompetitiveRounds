"""Admin evidence report, phase 1a item 2: registry, cell identity, encoding.

P21 (design 2.10): the census equals the expansion of every family's
declarations plus exactly two window keys per ranked non-FLAG base key, and
equals the design's numbers (59 base keys, 96 window keys, 155 entries; per
family M 16/20, N 15/28, O 10/20, C 18/28). The expected declarations below
are typed from design 2.10, NOT read from the module, so a change to the
module's declarations reds here instead of moving both sides (#342).

P10, identity half (design 2.1): every key dimension, the window, basis and
`n` of a comparability key, both aggregations and the subject tag each keep
two cells apart.

2.12: the control fixture round-trips through `_aer_enc` and no output
carries a code point of the escaped set as THIS test lists it (not the
module's `AER_ESC`), so dropping a code point from `AER_ESC` reds here.

No database.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import admin_evidence as ae  # noqa: E402

# ── Design 2.10, typed: (variable, provenances, kind) per family ────────────

SP = ("SELF", "PEER")
DESIGN = {
    "M": [("macro.suspect_s", ("SELF", "FLAG"), "R"),
          ("macro.peak_kps", ("SELF", "FLAG"), "R"),
          ("macro.peak_cps", ("SELF", "FLAG"), "R"),
          ("macro.peak_eps", ("SELF", "FLAG"), "R"),
          ("macro.timeline", ("SELF", "FLAG"), "D"),
          ("macro.keys", SP, "R"),
          ("macro.active_s", SP, "R"),
          ("macro.key_rate", ("D:SELF", "D:PEER"), "R")],
    "N": [("net.%s" % v, ("SELF",), "R") for v in (
            "writes", "unchanged", "move_raise_attempted", "move_raise_accepted",
            "resent_reliable", "discarded", "crc_loss", "queued_out_max",
            "queued_in_max", "fragment_cmds", "view_update_faults", "hitch50",
            "hitch200", "worst_frame_ms")]
         + [("net.worst_frame_tags", ("SELF",), "T")],
    "O": [("obs.%s" % v, ("OTHER",), "R") for v in (
            "gap300", "gap750", "gap1500", "excess150", "payload_equal_gaps",
            "receiver_frame_gaps", "phoenix_intervals", "batches", "max_gap_ms",
            "max_excess_ms")],
    "C": [("conn.recv_gaps", SP, "R"), ("conn.recv_gap_max_ms", ("SELF",), "R"),
          ("conn.hb_gaps", ("OTHER",), "R"), ("conn.ping_avg", SP, "R"),
          ("conn.ping_max", ("SELF",), "R"), ("conn.fps_avg", SP, "R"),
          ("conn.freezes", SP, "R"), ("conn.freezes_focused", SP, "R"),
          ("conn.freeze_total_s", ("SELF",), "R"), ("conn.fps_timeline", SP, "D"),
          ("conn.ping_timeline", SP, "D")],
}
DESIGN_CENSUS = {"M": [16, 20], "N": [15, 28], "O": [10, 20], "C": [18, 28]}


def _design_keys():
    base, window = [], []
    for fam, rows in DESIGN.items():
        for var, provs, kind in rows:
            for prov in provs:
                source = "flag_row" if prov == "FLAG" else "match_row"
                key = "%s|%s|seat|%s|na|cell|na" % (var, prov, source)
                base.append(key)
                if kind == "R" and prov != "FLAG":
                    for agg in ("win_median", "win_max"):
                        window.append("%s|%s|seat|%s|na|%s.cell|na"
                                      % (var, prov, source, agg))
    return base, window


def test_p21_census_equals_the_expansion_and_the_design_numbers():
    base, window = _design_keys()
    assert len(base) == 59 and len(window) == 96
    census = ae.registry_census()
    assert census == DESIGN_CENSUS, census
    assert ae.registry_totals() == {"base": 59, "window": 96, "entries": 155}
    keys = [e.key for e in ae.REPORT_REGISTRY]
    assert len(keys) == len(set(keys)) == 155
    assert sorted(keys) == sorted(base + window)
    assert ae.registry_problems(ae.REPORT_REGISTRY, ae.FAMILIES) == []
    print("GATE p21 census %r totals %r fingerprint %s"
          % (census, ae.registry_totals(), ae.registry_fingerprint()))


def test_p21_the_response_census_is_the_live_census():
    block = ae.registry_block()
    assert block["census"] == ae.registry_census() == DESIGN_CENSUS
    assert len(block["fingerprint"]) == 8
    int(block["fingerprint"], 16)


def test_p21_every_ranked_base_key_has_exactly_both_aggregations():
    for b in ae.REPORT_REGISTRY:
        wins = [w for w in ae.REPORT_REGISTRY if w.base == b.ki]
        if b.is_window or not b.ranked:
            assert wins == [], b.key
            continue
        assert sorted(w.agg for w in wins) == ["win_max.cell", "win_median.cell"], b.key
        for w in wins:
            assert w.key == b.key.replace("|cell|", "|%s|" % w.agg), (w.key, b.key)
            assert (w.var, w.prov, w.scope, w.source, w.coverage, w.stratum) == (
                b.var, b.prov, b.scope, b.source, b.coverage, b.stratum)
    for i, e in enumerate(ae.REPORT_REGISTRY):
        assert e.ki == i


def test_p21_no_phase_1_key_is_pair_global():
    assert {e.scope for e in ae.REPORT_REGISTRY} == {"seat"}


# A test-local family with one declared pair-global variable: the production
# registry has none, so the pair rules of P21 are exercised here.
TEST_PAIR = ae.Family("T", "test pair", (
    ae.Var("t.pair", "count", "R", ("SELF",), "t_pair", subject="pair"),
    ae.Var("t.seat", "count", "R", ("SELF",), "{s}_t_seat"),
), pair_global=frozenset({"t.pair"}))


def test_p21_a_pair_global_window_key_exists_only_at_basis_pair():
    families = ae.FAMILIES + (TEST_PAIR,)
    entries = ae._expand(families)
    assert ae.registry_problems(entries, families) == []
    pair_windows = [e for e in entries if e.is_window and e.scope == "pair"]
    assert len(pair_windows) == 2
    assert all(e.bases == ("pair",) for e in pair_windows)
    seat_windows = [e for e in entries if e.is_window and e.var == "t.seat"]
    assert all(e.bases == ("player", "pair") for e in seat_windows)


def test_p21_an_undeclared_pair_subject_is_refused():
    undeclared = ae.Family("U", "undeclared", (
        ae.Var("u.pair", "count", "R", ("SELF",), "u_pair", subject="pair"),))
    entries_ok = ae.REPORT_REGISTRY
    problems = ae.registry_problems(entries_ok, ae.FAMILIES + (undeclared,))
    assert any("not declared pair-global" in p for p in problems), problems


def test_p21_problems_name_omitted_duplicated_and_missing_aggregation():
    reg = list(ae.REPORT_REGISTRY)
    assert any("omitted" in p for p in ae.registry_problems(reg[:-1], ae.FAMILIES))
    dup = reg + [reg[0]]
    assert any("duplicated" in p for p in ae.registry_problems(dup, ae.FAMILIES))
    no_max = [e for e in reg if not e.agg.startswith("win_max")]
    assert any("window aggregations" in p
               for p in ae.registry_problems(no_max, ae.FAMILIES))


# ── P10, identity half ─────────────────────────────────────────────────────

def test_p10_each_key_dimension_keeps_two_keys_apart():
    base = dict(var="v", prov="SELF", scope="seat", source="match_row",
                coverage="na", agg="cell", stratum="na")
    alt = dict(var="w", prov="MEAS", scope="pair", source="card_record",
               coverage="paired", agg="win_max.cell", stratum="pool:ab")
    k0 = ae.aer_key_id(**base)
    for dim in base:
        changed = dict(base, **{dim: alt[dim]})
        assert ae.aer_key_id(**changed) != k0, dim
    assert k0.count("|") == 6


def test_p10_comparability_key_keeps_window_basis_and_n_apart():
    w0 = ae.REPORT_REGISTRY[59].key
    w1 = ae.REPORT_REGISTRY[60].key
    ck = ae.comparability_key(w0, "player", 30)
    assert ae.comparability_key(w1, "player", 30) != ck
    assert ae.comparability_key(w0, "pair", 30) != ck
    assert ae.comparability_key(w0, "player", 1) != ck
    assert len(ck) == 3


def test_p10_subject_tags_and_pair_order():
    a, b = "00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"
    assert ae.pair_subject(a, b) == ae.pair_subject(b, a) == ("pair", a, b)
    assert ae.seat_subject(a) == ("seat", a, None)
    assert ae.seat_subject(a, b) != ae.seat_subject(a)
    occ = ae.game_occurrence("g")
    key = ae.REPORT_REGISTRY[0].key
    assert ae.cell_identity(occ, ae.seat_subject(a, b), key) != ae.cell_identity(
        occ, ae.pair_subject(a, b), key)
    assert ae.cell_identity(ae.window_occurrence(0), ae.seat_subject(a), key) != (
        ae.cell_identity(ae.window_occurrence(1), ae.seat_subject(a), key))


# ── 2.12 encoding ──────────────────────────────────────────────────────────

# The escaped set as THIS test lists it (design 2.12), not ae.AER_ESC.
ESCAPED = (set(range(0x00, 0x20)) | {0x7F} | set(range(0x80, 0xA0))
           | {0x2028, 0x2029, 0x061C, 0x200E, 0x200F}
           | set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A)) | {0x60})

BACKSLASH = chr(0x5C)
CONTROL_FIXTURE = [
    "GC" + chr(0x1B) + "[31m" + chr(0x9B) + chr(0x07),
    "line" + chr(0x0A) + "cr" + chr(0x0D) + chr(0x202E) + "rlo",
    chr(0x061C) + chr(0x200E) + chr(0x200F) + "marks",
    chr(0x60) * 3 + "fence" + chr(0x60) * 3,
    BACKSLASH + "u{1b}" + BACKSLASH + BACKSLASH + "$x$",
    "".join(chr(cp) for cp in sorted(ESCAPED)),
]


def test_2_12_control_fixture_round_trips_and_holds_no_escaped_code_point():
    for value in CONTROL_FIXTURE:
        enc = ae._aer_enc(value)
        assert ae._aer_dec(enc) == value
        bad = sorted({hex(ord(c)) for c in enc if ord(c) in ESCAPED})
        assert not bad, (value, bad)
    print("GATE 2.12 control fixture: %d values round-trip, 0 escaped code points"
          % len(CONTROL_FIXTURE))


def test_2_12_each_bidi_mark_is_escaped_by_name():
    for cp in (0x061C, 0x200E, 0x200F):
        assert ae._aer_enc(chr(cp)) == "%su{%x}" % (BACKSLASH, cp)


def test_2_12_backslash_is_doubled_so_decoding_is_unambiguous():
    assert ae._aer_enc(BACKSLASH) == BACKSLASH * 2
    literal = BACKSLASH + "u{41}"
    assert ae._aer_dec(ae._aer_enc(literal)) == literal


def test_aer_wire_1a_has_no_class_or_mark_slot():
    for table in ae.AER_WIRE["1a"].values():
        assert "cls" not in table and "mark" not in table
    assert set(ae.AER_WIRE) == {"1a"}
