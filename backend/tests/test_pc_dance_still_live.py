"""Dance cards: the still writer's dance suffix and /pc/me's three keys
(design S2.8, S2.9, S4.9) against a real PostgreSQL -- T18 and T63.

Each test is one named assertion; the mutation that must fail it is planted
by the lane's mutation runner and recorded in its log, and the test's own
passing case is the control (#391). The HMAC key is a random test value, the
strict session check is replaced (dance_pg_harness.Sessions), and every
player is synthetic.
"""
import os
import re
import sys
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import dance_pg_harness as dp  # noqa: E402
import main  # noqa: E402

SECRET = "dance-test-" + uuid.uuid4().hex
DANCER = dp.DESC + "|dance=dance_bounce|ar=1"
KEYS = ("pc_dance_sku", "pc_dance_item", "pc_motion")
API_CLIENT = os.path.join(HERE, "..", "..", "plugin", "ApiClient.cs")


@pytest.fixture(scope="module")
def lane():
    dp.require_live_pg()
    return dp.shared_lane()


@pytest.fixture
def env(monkeypatch, lane):
    sessions = dp.Sessions()
    dp.open_routes(monkeypatch, sessions, SECRET)
    return sessions


def player(lane, sessions, **kw):
    steam = dp.steam_id()
    pid, still = lane.run(dp.make_player(lane, steam, **kw))
    sessions.live.add(steam)
    return steam, pid, still


def still_up(lane, steam, png, descriptor):
    return lane.run(dp.still_upload(lane, steam, SECRET, png, descriptor))


def still_row(lane, pid):
    return dict(lane.run(dp.fetch(
        lane, "SELECT pc_game_portrait_hash, pc_game_portrait_descriptor, pc_game_portrait_at FROM players "
              "WHERE id = CAST(:pid AS uuid)", pid=pid))[0])


def age_still(lane, pid):
    lane.run(dp.execute(
        lane, "UPDATE players SET pc_game_portrait_at = now() - interval '1 hour' WHERE id = CAST(:pid AS uuid)",
        pid=pid))


def me(lane, steam):
    return lane.run(dp.pc_me(lane, steam, SECRET))


def dance_state(lane, steam):
    answer = me(lane, steam)
    return tuple(answer[k] for k in KEYS)


_COLUMN_TYPES = {"pc_game_portrait_descriptor": "text", "pc_game_portrait_hash": "text",
                 "active_dance_id": "bigint"}


def set_player(lane, pid, column, value):
    lane.run(dp.execute(
        lane, f"UPDATE players SET {column} = CAST(:v AS {_COLUMN_TYPES[column]}) WHERE id = CAST(:pid AS uuid)",
        v=value, pid=pid))


# -- T18: the still writer's dual grammar ---------------------------------------

def test_still_writer_dance_suffix(lane, env):
    """T18 (S2.8): against the writer's locked row, a present suffix naming
    another dance than the selection is 422 descriptor_mismatch and one whose
    `ar` is not a recipe in the table is 422 descriptor_invalid, with nothing
    stored; an ABSENT suffix is accepted while a dance is selected (an older
    client's still); with no selection any suffix is a mismatch. Control: the
    matching suffix is accepted. Mutation: the grammar requires the suffix."""
    steam, pid, _still = player(lane, env)                 # dance_bounce selected and owned
    before = still_row(lane, pid)
    png = dp.still_png("t18-" + steam)
    assert still_up(lane, steam, png, DANCER.replace("dance_bounce", "dance_wave")) \
        == (422, {"error": "descriptor_mismatch"})
    assert still_up(lane, steam, png, dp.DESC + "|dance=dance_bounce|ar=2") == (422, {"error": "descriptor_invalid"})
    assert still_row(lane, pid) == before
    status, answer = still_up(lane, steam, png, DANCER)
    assert status == 200 and answer["applied"] is True, (status, answer)
    assert still_row(lane, pid)["pc_game_portrait_descriptor"] == DANCER
    age_still(lane, pid)
    status, answer = still_up(lane, steam, dp.still_png("t18b-" + steam), dp.DESC)
    assert status == 200 and answer["applied"] is True, (status, answer)
    assert still_row(lane, pid)["pc_game_portrait_descriptor"] == dp.DESC
    other, opid, _ostill = player(lane, env, dance=None)
    obefore = still_row(lane, opid)
    assert still_up(lane, other, png, DANCER) == (422, {"error": "descriptor_mismatch"})
    assert still_row(lane, opid) == obefore


# -- T63: /pc/me's dance keys ----------------------------------------------------

def test_pc_me_dance_keys(lane, env, monkeypatch):
    """T63 (S2.9, S4.9): /pc/me names the selection only while it is a ready
    dance the player owns (bought, or through the exemption), and names the
    stored motion as "<motion_hash>:<static_hash>:<recipe>" only while it is
    servable: another still descriptor, another still hash or another
    selection empties it. Without the motion module the three keys are
    absent, as from an older server. Control: a bound, owned, ready motion is
    named."""
    steam, pid, still = player(lane, env)
    item = lane.items["dance_bounce"]
    assert dance_state(lane, steam) == ("dance_bounce", item, "")
    h = lane.run(dp.put_motion(lane, pid, still))
    named = f"{h}:{still}:1"
    assert dance_state(lane, steam) == ("dance_bounce", item, named)
    # the binding (S3.4): the still's descriptor, then its hash
    set_player(lane, pid, "pc_game_portrait_descriptor", dp.DESC.replace("anim=1", "anim=0"))
    assert dance_state(lane, steam) == ("dance_bounce", item, "")
    set_player(lane, pid, "pc_game_portrait_descriptor", dp.DESC)
    assert dance_state(lane, steam) == ("dance_bounce", item, named)
    other = dp.still_hash("t63-other-" + steam)
    lane.run(_blob(lane, other))
    set_player(lane, pid, "pc_game_portrait_hash", other)
    assert dance_state(lane, steam) == ("dance_bounce", item, "")
    set_player(lane, pid, "pc_game_portrait_hash", still)
    # the selection moved to another owned dance: the motion was for the old one
    wave = lane.items["dance_wave"]
    lane.run(dp.execute(lane, "INSERT INTO player_items (player_id, item_id, purchase_price) "
                              "VALUES (CAST(:pid AS uuid), CAST(:item AS bigint), 0)", pid=pid, item=wave))
    set_player(lane, pid, "active_dance_id", wave)
    assert dance_state(lane, steam) == ("dance_wave", wave, "")
    set_player(lane, pid, "active_dance_id", item)
    assert dance_state(lane, steam) == ("dance_bounce", item, named)
    # ownership: lost, the selection hides; the exemption owns it again
    lane.run(dp.execute(lane, "DELETE FROM player_items WHERE player_id = CAST(:pid AS uuid) "
                              "AND item_id = CAST(:item AS bigint)", pid=pid, item=item))
    assert dance_state(lane, steam) == ("", 0, "")
    monkeypatch.setattr(main, "SHOP_OWNER_STEAM_IDS", {steam})
    assert dance_state(lane, steam) == ("dance_bounce", item, named)
    # readiness: an unready item hides, even from the exemption
    lane.run(dp.execute(lane, "UPDATE shop_items SET catalog_ready = false WHERE sku = 'dance_bounce'"))
    try:
        assert dance_state(lane, steam) == ("", 0, "")
    finally:
        lane.run(dp.execute(lane, "UPDATE shop_items SET catalog_ready = true WHERE sku = 'dance_bounce'"))
    # no selection at all
    set_player(lane, pid, "active_dance_id", None)
    assert dance_state(lane, steam) == ("", 0, "")
    # the motion module not loaded: no keys, exactly as from an older server
    monkeypatch.setattr(main, "_pcm", None)
    assert not any(k in me(lane, steam) for k in KEYS)


async def _blob(lane, h):
    async with lane.sm() as db:
        await dp.still_blob(db, h)
        await db.commit()


def test_pc_me_dance_keys_are_what_the_client_reads():
    """T63's contract half: the three keys /pc/me answers are the three
    top-level keys ApiClient.ParsePcMe reads, and the client decides that
    the server supports dance cards by the presence of `pc_dance_sku` alone
    (S5.8). Read as text: the point is what each side names."""
    with open(API_CLIENT, encoding="utf-8", newline="") as handle:
        src = handle.read()
    parse = src[src.index("internal static PcMe ParsePcMe(string json)"):]
    parse = parse[:parse.index("\n        }\n") if "\n        }\n" in parse else parse.index("\r\n        }\r\n")]
    client = re.findall(r'PcTopLevel\(json, "(pc_[a-z_]+)"\)', parse)
    assert client == list(KEYS), client
    assert 'me.dance_supported = PcHas(json, "pc_dance_sku");' in parse
