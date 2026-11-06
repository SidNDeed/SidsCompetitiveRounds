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
import math
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


# ── H2: contributions without the subject's own record ────────────────────

@pytest.mark.parametrize("src", ("card", "combat"))
def test_h2_a_contribution_about_a_seat_with_no_record_is_shown(src):
    """A supplies the only record; it produced a stored `meas` contribution
    about B. B's seat keeps `no_record` and shows that contribution; B's
    window total carries it; A's seat shows none of it."""
    a, b = _pair()
    g = _game(a, b)
    cols = {"hands": 4} if src == "card" else {"sums": '{"a1s": [1, 2, 3]}'}
    data = _data(records=[_rec(src, "k1", a, b, "room-1")],
                 games=[_grow(src, "k1", a, b, g["id"])],
                 contrib=[_crow(src, "k1", a, b, b, source="meas", **cols)],
                 switches=_on(src))
    s = ae.game_section(src, data, g, {a: 0, b: 1})
    sb, fb = _seat(s, 1)
    sa, fa = _seat(s, 0)
    assert (sa, sb) == ("ok", "no_record")
    assert fb.get("contrib1.source") == "meas", fb
    want = ("contrib1.hands", "4") if src == "card" else ("contrib1.a1s.total", "6")
    assert fb.get(want[0]) == want[1], fb
    assert "contrib1.source" not in fa and fa["contrib"] == "not_derived"
    t = ae.summary_section(src, data, [g], b, 1)
    f = _facts(t["facts"])
    assert (t["state"], f["with_record"]) == ("no_record", "0")
    total = ("meas.hands", "4") if src == "card" else ("meas.a1s.total", "6")
    assert f.get(total[0]) == total[1] and "contrib" not in f, f
    # a seat with neither a record nor a contribution about it stays empty
    empty = ae.game_section(src, _data(records=[_rec(src, "k1", a, b, "room-1")],
                                       games=[_grow(src, "k1", a, b, g["id"])]),
                            g, {a: 0, b: 1})
    assert empty["seats"][1] == {"subject": 1, "state": "no_record", "facts": []}


# ── H3: a record is the game's only when its own attach key is the room ───

@pytest.mark.parametrize("src", ae.SECTION_SOURCES)
@pytest.mark.parametrize("attached", (True, False))
def test_h3_a_record_naming_another_room_is_excluded_and_counted(src, attached):
    """A and B share stable key K; A names K_r8, B names K_r9; the games row
    for (K, A, B) is attached to the K_r8 match (or not attached yet). B's
    record is another attachment's: excluded, counted in `other_game`."""
    a, b = _pair()
    g = _game(a, b, room="K_r8")
    data = _data(records=[_rec(src, "K", a, b, "K_r8", received_at=T0),
                          _rec(src, "K", b, a, "K_r9", received_at=T0)],
                 games=[_grow(src, "K", a, b, g["id"] if attached else None)],
                 switches=_on(src))
    s = ae.game_section(src, data, g, {a: 0, b: 1})
    gf = _facts(s["game"])
    assert gf["paired"] == ("attached" if attached else "waiting")
    assert s["state"] == "ok" and gf.get("other_game") == "1", gf
    assert _seat(s, 0)[0] == "ok" and _seat(s, 1) == ("no_record", {})
    ta = ae.summary_section(src, data, [g], a, 0)
    tb = ae.summary_section(src, data, [g], b, 1)
    assert _facts(ta["facts"])["with_record"] == "1"
    assert _facts(tb["facts"])["with_record"] == "0" and tb["state"] == "no_record"


# ── H4: the pair is part of every stored identity ─────────────────────────

def _four():
    ids = sorted(str(uuid.uuid4()) for _ in range(4))
    return ids


@pytest.mark.parametrize("src", ae.SECTION_SOURCES)
def test_h4_another_pairs_attached_row_does_not_hold_back_this_pairs_records(src):
    """Under one stable key K: A/B's records name this game's room and their
    games row is not attached yet; C/D's games row under K is attached to
    another match. A/B's records are waiting for this game."""
    a, b, c, d = _four()
    g = _game(a, b, room="room-ab")
    data = _data(records=[_rec(src, "K", a, b, "room-ab"), _rec(src, "K", b, a, "room-ab"),
                          _rec(src, "K", c, d, "room-cd"), _rec(src, "K", d, c, "room-cd")],
                 games=[_grow(src, "K", a, b, None),
                        _grow(src, "K", c, d, str(uuid.uuid4()))],
                 switches=_on(src))
    s = ae.game_section(src, data, g, {a: 0, b: 1})
    gf = _facts(s["game"])
    assert (s["state"], gf["paired"]) == ("ok", "waiting"), (s["state"], gf)
    assert "other_game" not in gf
    assert [x["state"] for x in s["seats"]] == ["ok", "ok"]
    t = ae.summary_section(src, data, [g], a, 0)
    assert _facts(t["facts"])["waiting"] == "1"


@pytest.mark.parametrize("src", ("card", "combat"))
def test_h4_another_pairs_contribution_about_the_same_subject_is_not_this_games(src):
    """Under one stable key K: A's own A/B contribution, and C's measurement
    of A in pair A/C (C's record under K names A; A's one record under K is
    in A/B). A/B's game shows only the first, in the seat facts and in the
    window totals."""
    a, b, c, _d = _four()
    g = _game(a, b, room="room-ab")
    other = str(uuid.uuid4())
    mine = {"hands": 5} if src == "card" else {"sums": '{"a1s": [5]}'}
    theirs = {"hands": 7} if src == "card" else {"sums": '{"a1s": [7]}'}
    data = _data(records=[_rec(src, "K", a, b, "room-ab"), _rec(src, "K", b, a, "room-ab"),
                          _rec(src, "K", c, a, "room-ac")],
                 games=[_grow(src, "K", a, b, g["id"]), _grow(src, "K", a, c, other)],
                 contrib=[_crow(src, "K", a, b, a, **mine),
                          _crow(src, "K", a, c, a, source="meas", **theirs)],
                 switches=_on(src))
    s = ae.game_section(src, data, g, {a: 0, b: 1})
    _sa, fa = _seat(s, 0)
    assert fa["contrib1.source"] == "self" and "contrib2.source" not in fa, fa
    assert "games_rows" not in _facts(s["game"])
    f = _facts(ae.summary_section(src, data, [g], a, 0)["facts"])
    if src == "card":
        assert f["self.hands"] == "5" and "meas.hands" not in f, f
    else:
        assert f["self.a1s.total"] == "5" and "meas.a1s.total" not in f, f


# ── M1: fact lines inside the rendered width ──────────────────────────────

DPI = 100                       # aer_render_worker.render's figure dpi
MONO_ADVANCE = 1233 / 2048      # DejaVu Sans Mono's advance width in em, regular and bold
TEXT_X = 0.01                   # the worker's text origin for an unfilled kind, in widths


def _fit(kind):
    """The characters of `kind` that fit between the worker's text origin
    and the image's right edge: Agg hints each advance up to whole pixels
    (the facts kind's 7.5 px draws as 8; 160 characters measured 1280 px)."""
    width = worker.WIDTH_IN * DPI
    per_char = math.ceil(worker.FONT_SIZES[kind] * MONO_ADVANCE * DPI / 72.0)
    return int(width * (1 - TEXT_X) // per_char)


def _long_body(profile, hands):
    """The game page of game_body() whose card section's seat 0 carries a
    record and one contribution with `profile`; every other section is
    unavailable."""
    a, b = _pair()
    g = _game(a, b)
    data = _data(records=[_rec("card", "k1", a, b, "room-1", pool_state="ok",
                               deal_profile=profile, header_mod_version="1.41.0",
                               received_at=T0)],
                 games=[_grow("card", "k1", a, b, g["id"], processed_at=T0)],
                 contrib=[_crow("card", "k1", a, b, a, deal_profile=profile, hands=hands)],
                 switches=_on("card"))
    body = game_body()
    body["games"][0]["sections"] = [
        ae.game_section(src, data if src == "card" else None, g, {a: 0, b: 1})
        for src in ae.SECTION_SOURCES]
    return body


@pytest.mark.parametrize("profile,hands,line", (
    ("p" * 48, 12, 217),            # the round's measured line: a 48-character profile
    (None, 3, None)))               # a whole genuine profile
def test_m1_a_long_fact_line_is_wrapped_to_the_rendered_width(profile, hands, line):
    bot = bot_ns()
    body = _long_body(profile or _profile("m1"), hands)
    facts = body["games"][0]["sections"][0]["seats"][0]["facts"]
    eight = " ".join("%s=%s" % (n, "-" if v is None else v) for n, v in facts[8:16])
    if line is not None:
        assert len(eight) == line, len(eight)
    assert len(eight) > _fit("facts"), (len(eight), _fit("facts"))
    _page, plan = check_plan(bot, body)
    longest = max(len(i.text) for i in plan if i.kind == "facts")
    assert longest <= _fit("facts"), (longest, _fit("facts"))


EDGE_WORKER = '''
import base64, json, sys
OVER = None
inp, out = sys.stdin.buffer, sys.stdout.buffer
while True:
    head = inp.read(4)
    if len(head) < 4:
        break
    plan = json.loads(inp.read(int.from_bytes(head, "big")).decode("utf-8"))
    width = 1400
    longest = max(range(len(plan)), key=lambda i: len(plan[i][1]))
    drawn = [[i, t, [14, 0, width + 1 if (OVER and i == longest) else 100, 10]]
             for i, (k, t) in enumerate(plan)]
    png = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)) + b"fake"
    reply = {"png": base64.b64encode(png).decode("ascii"), "drawn": drawn, "width": width}
    data = json.dumps(reply).encode("utf-8")
    out.write(len(data).to_bytes(4, "big") + data)
    out.flush()
'''


@pytest.mark.parametrize("over", (False, True))
def test_m1_a_drawing_past_the_image_edge_gives_the_complete_text_fallback(tmp_path, over):
    """The worker reports each item's drawn box and the image width; a box
    past the edge gives the complete text fallback (every plan line), and
    the worker is kept for the next page. Inside the edge: the PNG."""
    script = tmp_path / "edge_worker.py"
    script.write_text(EDGE_WORKER.replace("OVER = None", "OVER = %r" % over), encoding="utf-8")
    body = _long_body(_profile("m1-edge"), 3)
    events = []
    ns = bot_ns(_Api(lambda path, actor: (200, copy.deepcopy(body), {}), events), events,
                mpl=True)
    ns["AER_WORKER_PATH"] = str(script)
    spawned = []
    real_spawn = ns["_aer_worker_spawn"]

    async def spawn():
        proc = await real_spawn()
        spawned.append(proc)
        return proc

    ns["_aer_worker_spawn"] = spawn

    async def go():
        try:
            out = []
            for _ in range(2):
                it = _Interaction(events, ADMIN)
                await ns["_aer_command"](it, dict(REQ))
                out.append(it)
            return out
        finally:
            for proc in spawned:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()

    shown_items = asyncio.run(asyncio.wait_for(go(), 40))
    plan = ns["_aer_plan"](ns["_aer_decode_response"](copy.deepcopy(body), "1a"))
    for it in shown_items:
        content, kw = it.channel.sent[0]
        pngs = [f for f in kw["files"] if f.filename.endswith(".png")]
        if not over:
            assert len(pngs) == 1 and pngs[0].data.startswith(PNG)
            continue
        assert pngs == [], [f.filename for f in kw["files"]]
        shown = content if not kw["files"] else kw["files"][0].data.decode("utf-8")
        missing = [i.text for i in plan if i.text not in shown]
        assert missing == [], missing[:3]
    assert len(spawned) == 1


def test_m1_the_worker_reports_the_image_width_with_its_drawing():
    import io
    from test_discord_evidence_render import _frame, _replies

    def draw(plan):
        return PNG + b"x", [(i, t, (0, 0, 1, 1)) for i, (_k, t) in enumerate(plan)]

    out = io.BytesIO()
    worker.serve(io.BytesIO(_frame([["title", "EVIDENCE game"]])), out, draw)
    (reply,) = _replies(out.getvalue())
    assert reply.get("width") == int(worker.WIDTH_IN * DPI), reply
    assert getattr(worker, "DPI", None) == DPI
