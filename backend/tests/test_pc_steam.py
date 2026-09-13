"""Steam profile pictures — the pure half (pc_steam) and the renderer's two
new shapes (the Steam picture and the emblem plate). Every fixture is
generated here by Pillow: nothing binary is tracked (#633)."""
import hashlib
import io
import os
import sys
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest
from PIL import Image, ImageChops, PngImagePlugin

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

import pc_face  # noqa: E402
import pc_steam  # noqa: E402

REF = "0123456789abcdef0123456789abcdef01234567"
SID, SID2 = "76561198040410653", "76561198720512419"


def _jpeg(width, height, colour=(200, 40, 40)):
    out = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(out, format="JPEG", quality=90)
    return out.getvalue()


def _png(width, height, mode="RGBA", colour=(40, 200, 40, 255), **save):
    out = io.BytesIO()
    Image.new(mode, (width, height), colour[:len(mode)] if mode != "P" else 3).save(out, format="PNG", **save)
    return out.getvalue()


# ── references and URLs ────────────────────────────────────────────────

def test_the_picture_url_is_built_from_the_reference_and_nothing_else():
    assert pc_steam.avatar_url(REF) == f"https://avatars.steamstatic.com/{REF}_full.jpg"
    for bad in ("", REF[:-1], REF.upper(), REF + "0", "../" + REF[3:], None):
        with pytest.raises(ValueError):
            pc_steam.avatar_url(bad)
    assert pc_steam.ref_from_url(f"https://avatars.steamstatic.com/{REF}_full.jpg") == REF
    assert pc_steam.ref_from_url(f"https://avatars.akamai.steamstatic.com/{REF}_full.jpg") == REF
    for bad in (f"http://avatars.steamstatic.com/{REF}_full.jpg", f"https://evil.example/{REF}_full.jpg",
                f"https://avatars.steamstatic.com/{REF}_medium.jpg", f"https://avatars.steamstatic.com/{REF}_full.jpg?x=1",
                f"https://avatars.steamstatic.com/{REF.upper()}_full.jpg", "", None, 5):
        assert pc_steam.ref_from_url(bad) is None, bad
    url = pc_steam.summaries_url("K3Y", [SID, SID2])
    assert url.startswith(pc_steam.SUMMARIES_URL + "?") and "key=K3Y" in url and f"steamids={SID}%2C{SID2}" in url
    with pytest.raises(ValueError):
        pc_steam.summaries_url("", [SID])
    with pytest.raises(ValueError):
        pc_steam.summaries_url("K", [])
    with pytest.raises(ValueError):
        pc_steam.summaries_url("K", ["not-an-id"])
    with pytest.raises(ValueError):
        pc_steam.summaries_url("K", [SID] * 101)
    assert pc_steam.profile_xml_url(SID) == f"https://steamcommunity.com/profiles/{SID}?xml=1"
    with pytest.raises(ValueError):
        pc_steam.profile_xml_url("1; DROP")


# ── feed parsing ───────────────────────────────────────────────────────

def test_summaries_are_matched_by_steam_id_never_by_position():
    other = "76561198041616199"
    body = ('{"response":{"players":['
            f'{{"steamid":"{other}","avatarhash":"{"f" * 40}"}},'
            f'{{"steamid":"{SID2}","avatarfull":"https://avatars.steamstatic.com/{"e" * 40}_full.jpg"}},'
            f'{{"steamid":"{SID}","avatarhash":"{REF}"}},'
            '{"steamid":"76561198860111585","avatarhash":"NOT-A-HASH"},'
            '"junk", {"no":"steamid"}]}}').encode()
    out = pc_steam.parse_summaries(body, [SID, SID2, "76561198860111585", "76561198709950406"])
    assert out == {SID: REF, SID2: "e" * 40, "76561198860111585": None, "76561198709950406": None}
    assert other not in out, "an id nobody asked for is never written"
    # avatarhash wins over the URL; a bad hash falls back to the URL's segment
    body = (f'{{"response":{{"players":[{{"steamid":"{SID}","avatarhash":"zz",'
            f'"avatarfull":"https://avatars.steamstatic.com/{REF}_full.jpg"}}]}}}}').encode()
    assert pc_steam.parse_summaries(body, [SID]) == {SID: REF}
    for bad in (b"not json", b'{"response":{}}', b'{"response":{"players":{}}}', b"[]", b""):
        with pytest.raises(pc_steam.FeedError):
            pc_steam.parse_summaries(bad, [SID])


def test_the_profile_xml_fallback_reads_avatar_full_and_refuses_doctype():
    cdata = f'<?xml version="1.0"?><profile><avatarFull><![CDATA[https://avatars.steamstatic.com/{REF}_full.jpg]]></avatarFull></profile>'
    plain = f'<profile><steamID64>{SID}</steamID64><avatarFull>https://avatars.akamai.steamstatic.com/{REF}_full.jpg</avatarFull></profile>'
    assert pc_steam.parse_profile_xml(cdata.encode()) == REF
    assert pc_steam.parse_profile_xml(plain.encode()) == REF
    # an ABSENCE (that player's answer, the plate): Steam's own no-such-profile shape, a profile without a
    # usable picture, a picture off the CDN
    assert pc_steam.parse_profile_xml(b"<response><error>The specified profile could not be found.</error></response>") is None
    assert pc_steam.parse_profile_xml(f"<profile><avatarFull>https://evil.example/{REF}_full.jpg</avatarFull></profile>".encode()) is None
    assert pc_steam.parse_profile_xml(b"<profile><steamID64>1</steamID64></profile>") is None
    # a body that is not a profile at all is the FEED's failure (v4 §3): counted by the breaker, never an absence
    doctype = f'<!DOCTYPE profile [<!ENTITY a "aaaa">]><profile><avatarFull>https://avatars.steamstatic.com/{REF}_full.jpg</avatarFull></profile>'
    for junk in (b"<html>rate limited</html>", b"not xml at all <<", b"", doctype.encode(),
                 b"<!ENTITY a 'b'><profile/>"):
        with pytest.raises(pc_steam.FeedError):
            pc_steam.parse_profile_xml(junk)
    assert pc_steam.FetchError not in pc_steam.FeedError.__mro__   # the caller tells them apart by class


# ── the bounded reader ─────────────────────────────────────────────────

class _Resp:
    def __init__(self, body, length=None):
        self.body, self.pos = body, 0
        self.headers = {"Content-Length": str(length)} if length is not None else {}

    def read(self, n):
        chunk = self.body[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Opener:
    def __init__(self, answer):
        self.answer, self.requests = answer, []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_the_reader_bounds_hosts_redirects_and_size():
    url = pc_steam.avatar_url(REF)
    opener = _Opener(_Resp(b"x" * 100, length=100))
    assert pc_steam.http_get(url, max_bytes=100, open_with=opener) == b"x" * 100
    request, timeout = opener.requests[0]
    assert request.get_header("User-agent") == pc_steam.USER_AGENT and timeout == pc_steam.REQUEST_TIMEOUT
    assert request.get_header("Accept-encoding") == "identity"
    # a declared length over the cap is refused before a byte is read
    opener = _Opener(_Resp(b"x" * 10, length=101))
    with pytest.raises(pc_steam.FetchError) as ex:
        pc_steam.http_get(url, max_bytes=100, open_with=opener)
    assert ex.value.kind == "too_large" and opener.answer.pos == 0
    # an undeclared body is read at most max_bytes + 1 and refused beyond
    opener = _Opener(_Resp(b"x" * 5000))
    with pytest.raises(pc_steam.FetchError) as ex:
        pc_steam.http_get(url, max_bytes=100, open_with=opener)
    assert ex.value.kind == "too_large" and opener.answer.pos == 101
    # hosts and schemes off the list never open a connection
    for bad in (f"http://avatars.steamstatic.com/{REF}_full.jpg", f"https://evil.example/{REF}_full.jpg",
                f"https://avatars.steamstatic.com.evil.example/{REF}_full.jpg"):
        opener = _Opener(_Resp(b"x"))
        with pytest.raises(pc_steam.FetchError) as ex:
            pc_steam.http_get(bad, max_bytes=100, open_with=opener)
        assert ex.value.kind == "host" and opener.requests == []
    # redirects are refused by the handler and reported by class, statuses by number
    with pytest.raises(pc_steam.RedirectRefused):
        pc_steam._NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example/")
    with pytest.raises(pc_steam.FetchError) as ex:
        pc_steam.http_get(url, max_bytes=100, open_with=_Opener(pc_steam.RedirectRefused("302")))
    assert ex.value.kind == "redirect"
    with pytest.raises(pc_steam.FetchError) as ex:
        pc_steam.http_get(url, max_bytes=100, open_with=_Opener(urllib.error.HTTPError(url, 429, "slow down", {}, None)))
    assert (ex.value.kind, ex.value.status) == ("http", 429)
    with pytest.raises(pc_steam.FetchError) as ex:
        pc_steam.http_get(url, max_bytes=100, open_with=_Opener(TimeoutError("timed out")))
    assert ex.value.kind == "timeouterror" and url not in str(ex.value)
    assert isinstance(pc_steam.opener().handlers[0], urllib.request.BaseHandler)
    assert any(isinstance(h, pc_steam._NoRedirect) for h in pc_steam.opener().handlers)


def test_the_reader_holds_the_whole_exchange_inside_the_player_deadline():
    url = pc_steam.avatar_url(REF)
    clock = [0.0]

    class _Trickle(_Resp):
        def read(self, n):
            clock[0] += 5.0            # every chunk costs five seconds of wall clock
            return super().read(min(n, 1))
    opener = _Opener(_Trickle(b"x" * 10))
    with pytest.raises(pc_steam.FetchError) as ex:
        pc_steam.http_get(url, max_bytes=100, open_with=opener, clock=lambda: clock[0])
    assert ex.value.kind == "deadline" and opener.answer.pos == 3   # 15 s of a 12 s budget: refused mid-body
    assert opener.requests[0][1] == pc_steam.REQUEST_TIMEOUT   # each socket wait is still capped by the request timeout
    # a total shorter than the request timeout caps the socket wait too
    clock[0] = 0.0
    opener = _Opener(_Resp(b"x" * 3, length=3))
    assert pc_steam.http_get(url, max_bytes=100, open_with=opener, total=2.5, clock=lambda: clock[0]) == b"xxx"
    assert opener.requests[0][1] == 2.5
    assert pc_steam.PLAYER_DEADLINE == 12.0 and pc_steam.REQUEST_TIMEOUT == 6.0


# ── budget, breaker, backoff ───────────────────────────────────────────

def test_the_token_bucket_charges_every_request_and_lets_priming_overdraw():
    bucket = pc_steam.TokenBucket(rate=0.5, burst=10, now=0.0)
    assert [bucket.take(now=0.0) for _ in range(10)] == [0.0] * 10
    assert bucket.take(now=0.0) == pytest.approx(2.0), "the 11th request waits one token's worth"
    assert bucket.take(now=2.0) == 0.0 and bucket.take(now=2.0) == pytest.approx(2.0)
    # priming may overdraw to -burst and still go now
    assert [bucket.take(priority=True, now=2.0) for _ in range(10)] == [0.0] * 10
    assert bucket.take(priority=True, now=2.0) == pytest.approx(2.0)
    assert bucket.tokens == pytest.approx(-10.0)
    # the overdraft is paid back before the sweep gets a token again
    assert bucket.take(now=2.0) == pytest.approx(22.0)
    assert bucket.take(now=24.0) == 0.0
    # refill never exceeds the burst
    bucket.take(now=10_000.0)
    assert bucket.tokens == pytest.approx(9.0)


def test_the_breaker_pauses_on_five_failures_or_any_429_and_resumes():
    breaker = pc_steam.Breaker(failures=5, pause=900)
    for _ in range(4):
        breaker.record("cdn", False, now=0.0)
    assert breaker.state(0.0) is None
    breaker.record("cdn", True, now=0.0)          # a success resets the run
    for _ in range(4):
        breaker.record("cdn", False, now=0.0)
    assert breaker.state(0.0) is None
    breaker.record("cdn", False, now=0.0)
    assert breaker.state(1.0) == "paused:cdn" and breaker.paused(899.0)
    assert breaker.state(900.0) is None, "the pause expires by itself"
    breaker.record("api", False, status=429, now=1000.0)
    assert breaker.state(1000.0) == "paused:api" and breaker.counts["api"] == 0
    # failures of one kind never count against another
    fresh = pc_steam.Breaker(failures=5, pause=900)
    for kind in ("api", "xml", "cdn", "api", "xml", "cdn", "api", "xml"):
        fresh.record(kind, False, now=0.0)
    assert fresh.state(0.0) is None


def test_backoff_doubles_from_two_hours_and_caps_at_thirty_days():
    assert [pc_steam.backoff_hours(f) for f in (0, 1, 2, 3, 9, 10, 40)] == [2, 2, 4, 8, 512, 720, 720]
    assert pc_steam.REFRESH_DAYS == 7 and pc_steam.BACKOFF_CAP_HOURS == 720


# ── the canonicaliser ──────────────────────────────────────────────────

def test_the_canonical_picture_is_a_square_critical_chunk_rgba_png():
    out = pc_steam.canonical_picture(_jpeg(300, 200))
    assert pc_face.png_ihdr(out) == (200, 200, 8, 6, 0)
    assert {kind for kind, _ in pc_face.png_chunks(out)} == pc_face._PNG_OUTPUT_CHUNKS
    assert pc_face.steam_picture_ihdr(pc_face.png_ihdr(out))
    assert pc_steam.canonical_picture(_jpeg(300, 200)) == out, "two fetches of one picture hash the same"
    assert hashlib.sha256(out).hexdigest() == hashlib.sha256(pc_steam.canonical_picture(_jpeg(300, 200))).hexdigest()
    # a PNG with ancillary chunks and a palette comes out the same shape, the chunks dropped
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "ancillary")
    palette = _png(184, 184, mode="P", pnginfo=info)
    assert b"tEXt" in palette and b"PLTE" in palette   # the input really carries them
    out = pc_steam.canonical_picture(palette)
    assert pc_face.png_ihdr(out) == (184, 184, 8, 6, 0) and b"tEXt" not in out and b"PLTE" not in out
    # the tall picture is centre-cropped, not squashed: the crop keeps the middle band
    tall = Image.new("RGB", (100, 300), (0, 0, 0))
    tall.paste((255, 255, 255), (0, 100, 100, 200))
    buf = io.BytesIO()
    tall.save(buf, format="PNG")
    cropped = Image.open(io.BytesIO(pc_steam.canonical_picture(buf.getvalue())))
    assert cropped.size == (100, 100) and cropped.getpixel((50, 50))[:3] == (255, 255, 255)
    for data, kind in ((_jpeg(16, 16), "picture_small"), (_jpeg(1100, 1100), "picture_large"),
                       (_jpeg(300, 20), "picture_small"), (b"\x89PNG\r\n\x1a\nbroken", "picture_invalid"),
                       (b"GIF89a" + b"\x00" * 40, "picture_invalid"), (b"", "picture_invalid"),
                       (b"x" * (pc_steam.MAX_PICTURE_BYTES + 1), "picture_too_large")):
        with pytest.raises(ValueError) as ex:
            pc_steam.canonical_picture(data)
        assert str(ex.value) == kind, kind
    gif = io.BytesIO()
    Image.new("P", (64, 64)).save(gif, format="GIF")
    with pytest.raises(ValueError) as ex:
        pc_steam.canonical_picture(gif.getvalue())
    assert str(ex.value) == "picture_format"


# ── the renderer: the Steam shape and the emblem plate ─────────────────

_BASE = dict(band="rare", name="Ace", title="Advanced III", title_rgb=(52, 152, 219), rating=1800,
             pool_rank=12, board_rank=None, wins=3, losses=1, foil=False, signed=False,
             edition_label="Edition 1", minted_on="2026-09-12", print_short="#abc123", top_card=False)


def _rect(size):
    rect = pc_face.LAYOUT["rects"]["portrait"]
    return tuple(rect) if size == "card" else tuple(pc_face._scale_rect(rect, 0.5))


def _face(size, portrait=None, **spec):
    return Image.open(io.BytesIO(pc_face.render_face(dict(_BASE, **spec), {}, portrait, size)))


def _differs(a, b, rect):
    return ImageChops.difference(a.crop(rect).convert("RGB"), b.crop(rect).convert("RGB")).getbbox() is not None


def test_the_steam_shape_is_accepted_at_both_edges_and_nothing_else_is():
    picture = pc_steam.canonical_picture(_jpeg(184, 184))
    assert pc_face._portrait_image(picture, pc_face.PORTRAIT_CARD).size == (590, 590)
    assert pc_face._portrait_image(picture, pc_face.PORTRAIT_TILE).size == (295, 295)
    for bad in (_png(20, 20), _png(200, 100), _png(200, 200, mode="RGB"), _png(1180, 1180, mode="RGB"), b"nope"):
        with pytest.raises(ValueError):
            pc_face._portrait_image(bad, pc_face.PORTRAIT_CARD)
    assert not pc_face.steam_picture_ihdr(pc_face._PORTRAIT_IHDR), "the rig keeps its own path"


def test_the_plate_replaces_the_disc_and_the_picture_replaces_the_plate():
    src = open(pc_face.__file__, encoding="utf-8").read()
    assert not hasattr(pc_face, "_initial") and "draw.ellipse((inset" not in src, "the letter disc is gone as a class"
    assert src.count("_emblem_plate(colour, portrait_edge)") == 1
    for size in ("card", "tile"):
        rect = _rect(size)
        plate = _face(size)
        assert not _differs(plate, _face(size, name="Zed"), rect), "no letter: the plate ignores the name"
        assert not _differs(plate, _face(size, name=""), rect)
        assert _differs(plate, _face(size, band="legendary"), rect), "the plate carries the band tint"
        picture = pc_steam.canonical_picture(_jpeg(184, 184, colour=(250, 250, 250)))
        assert _differs(plate, _face(size, portrait=picture), rect)
        # the plate is not flat: the motif is drawn
        crop = plate.crop(rect).convert("RGB")
        assert len(crop.getcolors(maxcolors=1 << 20)) > 8
    # the tile plate is the card plate's exact reduction
    card = pc_face._emblem_plate((52, 152, 219), pc_face.PORTRAIT_CARD)
    tile = pc_face._emblem_plate((52, 152, 219), pc_face.PORTRAIT_TILE)
    assert tile.size == (295, 295) and ImageChops.difference(card.reduce(2).convert("RGB"), tile.convert("RGB")).getbbox() is None


# ── v4.1 (r4): the profile XML's exact shapes and encodings; the reader's per-read caps and late EOF ──

def test_the_profile_xml_accepts_only_steams_error_shape_and_refuses_wide_encodings():
    # Steam's absence shape has an <error> child; a bare <response> is the feed's failure, never an absence (v4.1 §4)
    assert pc_steam.parse_profile_xml(
        b"<response><error><![CDATA[The specified profile could not be found.]]></error></response>") is None
    for junk in (b"<response/>", b"<response></response>", b"<response><players/></response>"):
        with pytest.raises(pc_steam.FeedError) as ex:
            pc_steam.parse_profile_xml(junk)
        assert str(ex.value) == "shape"
    # a DTD hidden behind a wide encoding never reaches the parser: NUL bytes or a UTF-16 BOM are refused outright
    wide = ('<?xml version="1.0" encoding="utf-16"?><!DOCTYPE profile [<!ENTITY a "aaaa">]><profile><avatarFull>'
            f"https://avatars.steamstatic.com/{REF}_full.jpg</avatarFull></profile>").encode("utf-16")
    with pytest.raises(pc_steam.FeedError) as ex:
        pc_steam.parse_profile_xml(wide)
    assert str(ex.value) == "encoding"
    with pytest.raises(pc_steam.FeedError) as ex:
        pc_steam.parse_profile_xml(b"\xff\xfe<profile/>")
    assert str(ex.value) == "encoding"
    # the DTD check runs on the decoded text, case-insensitively
    with pytest.raises(pc_steam.FeedError) as ex:
        pc_steam.parse_profile_xml(b"<!doctype profile><profile/>")
    assert str(ex.value) == "doctype"
    # a plain UTF-8 profile still answers; a private profile without a picture is still an absence
    assert pc_steam.parse_profile_xml(
        ('<?xml version="1.0" encoding="UTF-8"?><profile><avatarFull>'
         f"https://avatars.steamstatic.com/{REF}_full.jpg</avatarFull></profile>").encode()) == REF
    assert pc_steam.parse_profile_xml(b"<profile><privacyState>private</privacyState></profile>") is None


def test_the_reader_caps_every_body_read_to_the_remaining_deadline_and_refuses_a_late_eof():
    url = pc_steam.avatar_url(REF)
    clock = [0.0]
    caps = []

    class _Sock:
        def settimeout(self, s):
            caps.append(s)

    class _Trickle(_Resp):
        def __init__(self, body, length=None):
            super().__init__(body, length)
            self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=_Sock()))

        def read(self, n):
            clock[0] += 5.0            # every chunk costs five seconds of wall clock
            return super().read(min(n, 1))
    # each read's socket wait is the request timeout or what is left of the deadline, whichever is smaller (v4.1 §3)
    opener = _Opener(_Trickle(b"x" * 10))
    with pytest.raises(pc_steam.FetchError) as ex:
        pc_steam.http_get(url, max_bytes=100, open_with=opener, clock=lambda: clock[0])
    assert ex.value.kind == "deadline" and caps == [6.0, 6.0, 2.0]
    # an absolute deadline shared with the caller's earlier requests: three seconds left means one capped read, then refusal
    clock[0] = 100.0
    caps.clear()
    opener = _Opener(_Trickle(b"x" * 10))
    with pytest.raises(pc_steam.FetchError) as ex:
        pc_steam.http_get(url, max_bytes=100, open_with=opener, clock=lambda: clock[0], deadline=103.0)
    assert ex.value.kind == "deadline" and caps == [3.0] and opener.answer.pos == 1
    assert opener.requests[0][1] == 3.0   # the open's own wait is capped the same way
    # a deadline already past: no request at all
    opener = _Opener(_Trickle(b"x"))
    with pytest.raises(pc_steam.FetchError) as ex:
        pc_steam.http_get(url, max_bytes=100, open_with=opener, clock=lambda: clock[0], deadline=99.0)
    assert ex.value.kind == "deadline" and opener.requests == []
    # an EOF that arrives past the deadline is refused too
    clock[0] = 0.0
    opener = _Opener(_Trickle(b""))
    with pytest.raises(pc_steam.FetchError) as ex:
        pc_steam.http_get(url, max_bytes=100, open_with=opener, clock=lambda: clock[0], deadline=3.0)
    assert ex.value.kind == "deadline" and opener.answer.pos == 0
