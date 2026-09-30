"""Dance cards: /card posts the motion preview GIF (design S6.3; M5; section
12 L6's send half) -- T42.

The bot's own code is lifted from discord_bot.py -- cmd_pc_card, the upload
cap, the one send under the lease, the lease clock and their constants --
and run against stubs of the api calls, the lease calls, the clock and
discord.py, so every margin is exact. Each test is one named assertion; the
mutation that must fail it is planted by the lane's mutation runner and
recorded in its log, and the test's own passing case is the control (#391).
"""
import asyncio
import io
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import discord_collection_harness as H  # noqa: E402

BOT = os.path.join(HERE, "..", "discord_bot.py")
FUNCS = {"cmd_pc_card", "_pc_upload_cap", "_pc_send_face", "_pc_lease_left"}
ASSIGNS = {"_PC_FACE_MAX_BYTES", "_PC_LEASE_RESERVE_S", "_PC_MOTION_GIF_MARGIN_S", "_PC_MOTION_GIF_TIMEOUT_S"}
REF = "11111111-1111-4111-8111-111111111111"
STILL = "ab" * 32
MIB = 1 << 20
PNG = b"PNG-preview"
GIF = b"GIF89a-motion"
PREVIEW = "/internal/pc/face/preview/%s/en" % REF
MOTION = "/internal/pc/motion/preview/%s/en.gif" % REF
CARD = {"player_ref": REF, "snapshot_id": 41, "subject_name": "Ace", "rarity": "rare", "pool_rank": 3,
        "rating": 1500, "peak_rating": 1600, "board_rank": 7,
        "in_circulation": {"prints": 2, "holders": 2, "foil": 0, "signed": 0}}


class _Embed:
    def __init__(self, **kw):
        self.image = None
        self.fields = []

    def add_field(self, **kw):
        self.fields.append(kw)

    def set_footer(self, **kw):
        pass

    def set_image(self, url):
        self.image = url


class _File:
    def __init__(self, fp, filename):
        self.data = fp.read()
        self.filename = filename


class _Unreadable:
    @property
    def filesize_limit(self):
        raise RuntimeError("no limit")


class Rig:
    """One /card run. `left` is the lease's seconds beyond the send reserve,
    `still` the picture the lease names, `gif` the motion route's (status,
    bytes, X-Motion-Static-Hash), `live` the api's revalidation answer and
    `guild` the destination (None: a DM)."""

    def __init__(self, *, left=30.0, still=STILL, preview=200, gif=(200, GIF, STILL), live=True,
                 guild=SimpleNamespace(filesize_limit=25 * MIB)):
        self.now = 1000.0
        self.left, self.still, self.preview, self.gif, self.live = left, still, preview, gif, live
        self.guild = guild
        self.fetched, self.checked, self.released, self.posted, self.said = [], [], [], [], []
        ns = {"asyncio": asyncio, "io": io, "time": SimpleNamespace(monotonic=lambda: self.now),
              "discord": SimpleNamespace(Member=object, Embed=_Embed, File=_File, utils=SimpleNamespace(
                  escape_markdown=lambda s: s, DEFAULT_FILE_SIZE_LIMIT_BYTES=10 * MIB)),
              "_maybe_defer": self._defer, "_pc_api": self._api, "_pc_api_bytes": self._bytes,
              "_pc_lease": self._lease, "_pc_lease_live": self._live, "_pc_lease_release": self._release,
              "_pc_detail": lambda body: body if isinstance(body, dict) else {},
              "_pc_not_linked": lambda ctx, target: "not linked", "_pc_name": lambda s: s,
              "_PC_RARITY_EMOJI": {}, "_PC_RARITY_COLOR": {}, "get_rank_name": lambda rating: "Gold",
              "rank_emoji": lambda name: "", "_pc_locale_of": lambda ctx: "en"}
        exec(compile(H.lift(FUNCS, ASSIGNS), BOT, "exec"), ns)
        self.ns = ns

    async def _defer(self, ctx):
        return None

    async def _api(self, method, path, params=None, **kw):
        assert (method, path) == ("GET", "/internal/pc/card"), (method, path)
        return 200, dict(CARD)

    async def _lease(self, ref, *args, **kw):
        assert ref == REF, ref
        return "L1", self.now + self.left, False, 200, self.still

    async def _bytes(self, path, params=None, timeout=10.0, max_bytes=4 * MIB):
        self.fetched.append((path, params, timeout, max_bytes))
        if path == PREVIEW:
            return self.preview, (PNG if self.preview == 200 else None), {}
        assert path == MOTION, path
        status, data, still = self.gif
        meta = {"x-motion-static-hash": still} if still else {}
        if status != 200 or data is None or len(data) > max_bytes:   # the real helper refuses over max_bytes
            return status, None, meta
        return status, data, meta

    async def _live(self, lease_id, **kw):
        self.checked.append(lease_id)
        return self.live

    async def _release(self, lease_id):
        self.released.append(lease_id)

    def run(self):
        async def send(*args, **kw):
            if args:
                self.said.append(args[0])
            else:
                self.posted.append(kw)
        ctx = SimpleNamespace(author=SimpleNamespace(id=1, display_name="Me"), send=send, guild=self.guild)
        asyncio.run(self.ns["cmd_pc_card"](ctx, None))
        return self

    def picture(self):
        """(filename, bytes, the embed's image) of the one post, or None when it carried no file."""
        assert len(self.posted) == 1 and self.said == [], (self.posted, self.said)
        post = self.posted[0]
        if "file" not in post:
            return None
        return post["file"].filename, post["file"].data, post["embed"].image


def test_card_gif_branch():
    """T42 (S6.3): with the lease naming a still and more than 12 s left
    beyond the send reserve, ONE request goes to the motion route -- the
    embed's snapshot and the lease, its own 2 s ceiling, the capped size --
    and a 200 naming the leased still posts card.gif; any other answer (404,
    503, no answer, another still, no still named) posts the preview PNG
    exactly as before; a lease naming no picture, or a preview that failed,
    asks for no GIF. Control: the PNG path unchanged. Mutation: the still
    check dropped."""
    rig = Rig().run()
    assert rig.fetched == [(PREVIEW, {"snapshot_id": 41}, 10.0, 4 * MIB),
                           (MOTION, {"snapshot_id": 41, "lease_id": "L1"}, 2.0, 4 * MIB)], rig.fetched
    assert rig.picture() == ("card.gif", GIF, "attachment://card.gif")
    assert rig.checked == ["L1"] and rig.released == ["L1"]
    for gif in ((404, None, None), (503, None, None), (0, None, None), (200, GIF, "cd" * 32), (200, GIF, None)):
        rig = Rig(gif=gif).run()
        assert [f[0] for f in rig.fetched] == [PREVIEW, MOTION], gif
        assert rig.picture() == ("card.png", PNG, "attachment://card.png"), gif
        assert rig.checked == ["L1"] and rig.released == ["L1"], gif
    rig = Rig(still=None).run()
    assert [f[0] for f in rig.fetched] == [PREVIEW] and rig.picture() == ("card.png", PNG, "attachment://card.png")
    rig = Rig(preview=404).run()
    assert [f[0] for f in rig.fetched] == [PREVIEW] and rig.picture() is None


def test_no_gif_request_with_twelve_seconds_or_less_beyond_the_reserve():
    """T42 (S6.3): the GIF is asked for only while the lease has MORE than
    12 s left beyond the 3 s send reserve: 12 s exactly, 11 s and 5 s ask
    nothing and post the PNG; 12.5 s asks and posts the GIF. Control: the
    PNG path unchanged. Mutation: the margin dropped."""
    for left in (12.0, 11.0, 5.0):
        rig = Rig(left=left).run()
        assert [f[0] for f in rig.fetched] == [PREVIEW] and rig.picture()[0] == "card.png", left
    rig = Rig(left=12.5).run()
    assert [f[0] for f in rig.fetched] == [PREVIEW, MOTION] and rig.picture()[0] == "card.gif"


def test_the_gif_cap_is_the_lower_of_the_face_cap_and_the_upload_limit():
    """T42 and M5 (S6.3): the motion request's max_bytes is the 4 MiB face
    cap or the destination's upload limit, whichever is lower, never the cap
    alone -- a 1 MiB guild asks for at most 1 MiB, so a 2 MiB GIF is refused
    and the PNG posts while a 512 KiB one posts; a 25 MiB guild and a DM
    (Discord's default limit) ask for 4 MiB, so a 5 MiB GIF is refused; a
    limit that cannot be read asks for nothing. Control: the PNG path
    unchanged. Mutation: the guild cap removed (the face cap alone)."""
    small = b"GIF89a" + b"s" * (512 * 1024)
    big = b"GIF89a" + b"b" * (2 * MIB)
    huge = b"GIF89a" + b"h" * (5 * MIB)
    rig = Rig(guild=SimpleNamespace(filesize_limit=1 * MIB), gif=(200, big, STILL)).run()
    assert rig.fetched[1][3] == 1 * MIB and rig.picture()[0] == "card.png", rig.fetched
    rig = Rig(guild=SimpleNamespace(filesize_limit=1 * MIB), gif=(200, small, STILL)).run()
    assert rig.fetched[1][3] == 1 * MIB and rig.picture()[:2] == ("card.gif", small)
    rig = Rig(guild=SimpleNamespace(filesize_limit=25 * MIB), gif=(200, big, STILL)).run()
    assert rig.fetched[1][3] == 4 * MIB and rig.picture()[:2] == ("card.gif", big)
    rig = Rig(guild=None, gif=(200, big, STILL)).run()
    assert rig.fetched[1][3] == 4 * MIB and rig.picture()[:2] == ("card.gif", big)
    rig = Rig(guild=SimpleNamespace(filesize_limit=25 * MIB), gif=(200, huge, STILL)).run()
    assert rig.fetched[1][3] == 4 * MIB and rig.picture()[0] == "card.png"
    rig = Rig(guild=_Unreadable()).run()
    assert [f[0] for f in rig.fetched] == [PREVIEW] and rig.picture()[0] == "card.png"


def test_the_lease_revalidation_gates_the_gif_send():
    """T42 and T61's send half (S6.3, L6): the GIF rides the same lease
    revalidation as the PNG, right before the send -- a lease the api no
    longer holds live (an admin clear, a deletion or a ban took it) posts
    nothing at all, says the card is unavailable, and releases the lease.
    Control: a live lease posts the GIF. Mutation: the send without
    revalidation."""
    rig = Rig(live=False).run()
    assert [f[0] for f in rig.fetched] == [PREVIEW, MOTION]
    assert rig.posted == [] and len(rig.said) == 1 and "isn't available" in rig.said[0], (rig.posted, rig.said)
    assert rig.checked == ["L1"] and rig.released == ["L1"]
    rig = Rig(live=True).run()
    assert rig.picture()[0] == "card.gif" and rig.checked == ["L1"]


def test_the_gif_numbers_are_the_designs():
    """S6.3's numbers: the 3 s send reserve unchanged, 12 s of margin beyond
    it, a 2 s ceiling on the one request, and the 4 MiB face cap as the
    upper bound of the GIF's size."""
    ns = Rig().ns
    assert (ns["_PC_LEASE_RESERVE_S"], ns["_PC_MOTION_GIF_MARGIN_S"], ns["_PC_MOTION_GIF_TIMEOUT_S"]) == (3.0, 12.0, 2.0)
    assert ns["_PC_FACE_MAX_BYTES"] == 4 * MIB
