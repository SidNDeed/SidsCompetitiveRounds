"""Board row 24 (the full card in the Settings preview), the server half,
EXECUTED against a real PostgreSQL.

GET /api/v1/pc/face/preview answers the caller's OWN card as the pool sees
it now -- frame, rarity band, name, rank title, rating, record and picture --
as one 750x1050 PNG. It draws through main._pc_preview_face, the helper the
bot's /card preview (internal_pc_face_preview) draws with, so the card a
player is shown of themselves and the card the bot shows others cannot come
from two renderers.

The database harness (schema pc_shard_t, the migration replay, the reset,
the per-client sessions) is test_pc_shard_batch's, imported rather than
copied; see that module's docstring for the DSN, the opt-out and how the
schema is built. Without PC_SHARD_TEST_PG_DSN every database test here FAILS
by name as it does there.

RUNNING IT
----------
    PC_SHARD_TEST_PG_DSN="postgresql://postgres@127.0.0.1:55432/asksb_cards" \\
        python -m pytest backend/tests/test_pc_settings_preview.py -q
"""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from test_pc_shard_batch import (  # noqa: E402,F401  (pg_build and env are fixtures)
    INTERNAL_KEY, REQ, _call, _code, _err, _fn_src, _pc, _player, _scenario, _sign, env, main, pg_build,
)

PNG_SIGNATURE = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])


def _preview(ctx, name, who, sig=None):
    return _call(ctx, name, main.pc_face_preview, request=REQ, steam_id=who.steam,
                 sig=sig if sig is not None else _sign(_pc.canon_read(who.steam, "face", "preview")))


def _stub_renderer(env):
    """The face renderer replaced by a recorder: every draw is logged with
    its size and returns a PNG-signed body naming the size, band, name and
    pool rank, so two routes that draw the same card return the same bytes."""
    calls = []

    def render_face(spec, labels, pbytes, size):
        calls.append({"size": size, "name": spec.get("name"), "band": spec.get("band"),
                      "footer": spec.get("edition_label")})
        body = "%s|%s|%s|%s" % (size, spec.get("band"), spec.get("name"), spec.get("pool_rank"))
        return PNG_SIGNATURE + body.encode()
    assert main._pcf is not None, "the face module did not import, so no face route can answer"
    env.monkeypatch.setattr(main._pcf, "render_face", render_face)
    env.monkeypatch.setattr(main, "_pc_require_renderer", lambda: None)
    env.monkeypatch.setattr(main, "_pc_renderer_fp", lambda: "fp-shard-test")
    return calls


def test_the_settings_preview_draws_the_callers_own_card_at_card_size(env):
    """The caller's card, drawn once at size card, private and not
    immutable; another member's request draws THEIR card."""
    calls = _stub_renderer(env)

    async def body(ctx):
        me = await _player(1, name="Preview Me", member=("epic", 21))
        other = await _player(3, name="Someone Else", member=("common", 300))
        status, resp = await _preview(ctx, "me", me)
        assert status == 200, resp
        assert resp.body == PNG_SIGNATURE + b"card|epic|Preview Me|21"
        assert resp.headers["cache-control"] == "private, max-age=60"
        assert calls[-1]["size"] == "card" and calls[-1]["name"] == "Preview Me"
        status, resp = await _preview(ctx, "other", other)
        assert status == 200 and resp.body.endswith(b"card|common|Someone Else|300"), resp
    _scenario(env, body)


def test_the_settings_preview_and_the_bot_preview_are_one_drawing(env):
    """For one member the Settings route and the bot's internal /card preview
    answer the same bytes through the same cache key: one renderer, nothing
    to drift."""
    calls = _stub_renderer(env)

    async def body(ctx):
        me = await _player(1, name="Same Card", member=("rare", 57))
        status, mine = await _preview(ctx, "me", me)
        assert status == 200, mine
        status, bot = await _call(ctx, "bot", main.internal_pc_face_preview, player_ref=me.pid, locale="en",
                                  x_internal_key=INTERNAL_KEY, snapshot_id=None)
        assert status == 200, bot
        assert mine.body == bot.body
        assert len(calls) == 1, "the second route drew again instead of reading the shared cache key"
    _scenario(env, body)


def test_the_settings_preview_refuses_a_player_with_no_card_and_a_bad_signature(env):
    """No row in the pool snapshot in force: 404 not_in_pool (the client
    keeps the live portrait and says so). A signature over another read: 403."""
    _stub_renderer(env)

    async def body(ctx):
        nobody = await _player(4, name="Not Pooled")
        assert _err(await _preview(ctx, "n", nobody)) == (404, "not_in_pool")
        member = await _player(5, member=("uncommon", 99))
        bad = _sign(_pc.canon_read(member.steam, "me", "-"))
        assert (await _preview(ctx, "b", member, sig=bad))[0] == 403
    _scenario(env, body)


def test_the_real_renderer_answers_a_750_by_1050_png(env):
    """The shipped renderer draws the Settings preview: a PNG whose header
    says 750 x 1050, the size the client's card decode requires. Waived: the
    box-readiness gate (a seat without a raqm build) and any declared font
    file the seat lacks, for which a copy of the bold face stands in inside a
    temporary directory. The font caches key on the directory, so nothing
    loaded here answers for any later test."""
    pcf = main._pcf
    assert pcf is not None, "the face module did not import, so no face route can answer"
    real = Path(pcf.FONTS_DIR)
    stand_in = (real / pcf._FONT_FILES["bold"]).read_bytes()
    fonts = env.tmp / "fonts"
    fonts.mkdir()
    for name in pcf._FONT_FILES.values():
        (fonts / name).write_bytes((real / name).read_bytes() if (real / name).exists() else stand_in)
    env.monkeypatch.setattr(pcf, "_FONTS_PATH", fonts)
    env.monkeypatch.setattr(main, "_pc_require_renderer", lambda: None)
    assert main._pc_renderer_fp() is not None, "the renderer cannot fingerprint itself"

    async def body(ctx):
        me = await _player(1, name="Full Card", member=("legendary", 3))
        status, resp = await _preview(ctx, "me", me)
        assert status == 200, resp
        data = resp.body
        assert data[:8] == PNG_SIGNATURE and data[12:16] == b"IHDR"
        assert struct.unpack(">II", data[16:24]) == (750, 1050)
    _scenario(env, body)


def test_the_preview_routes_share_the_drawing_helper_and_draw_at_card_size():
    """Structure: both preview routes call _pc_preview_face exactly once, the
    Settings route through the verified actor on the caller's OWN id, and the
    helper draws size "card"."""
    mine = _code(_fn_src("pc_face_preview"))
    assert mine.count("await _pc_preview_face ( db , pid ,") == 1
    assert mine.count("await _pc_verified_actor ( request , steam_id , sig , _pc . canon_read ( steam_id , "
                      "\"face\" , \"preview\" )") == 1
    assert "pid = str ( player . id )" in mine
    bot = _code(_fn_src("internal_pc_face_preview"))
    assert bot.count("await _pc_preview_face ( db , player_ref , loc , snapshot_id )") == 1
    helper = _fn_src("_pc_preview_face")
    assert helper.count('_functools.partial(_pcf.render_face, spec, labels, pbytes, "card")') == 1
