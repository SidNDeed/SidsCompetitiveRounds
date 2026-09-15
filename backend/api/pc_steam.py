"""Player Cards — Steam profile pictures, the pure half (design v2 §3/§4).

Feed parsing (player summaries matched BY steam id, the profile XML as the
bounded fallback), the avatar reference regex and URL construction (the CDN
URL is BUILT from the reference, never taken from a feed), one bounded HTTP
reader (https only, host allow-list, redirects refused, body capped), the
outbound token bucket and breaker, the backoff arithmetic, and the picture
canonicaliser. No database and no event loop in here: main.py's sweep and
priming call these and own the locks."""
from __future__ import annotations

import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
import xml.etree.ElementTree as ET
from typing import Iterable

from PIL import Image

import pc_face
import steamid64

AVATAR_REF_RE = re.compile(r"^[0-9a-f]{40}$")
# Steam's own "no picture" answers: the all-zero reference some summaries
# carry, and the shared default silhouette every account without a picture
# resolves to. Neither is a picture of the player, so neither is ever
# downloaded: the card's answer for them is the emblem plate (v3 §3).
DEFAULT_AVATAR_REFS = frozenset({"0" * 40, "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb"})
_AVATAR_URL_RE = re.compile(r"^https://avatars\.(?:akamai\.)?steamstatic\.com/([0-9a-f]{40})_full\.jpg$")
CDN_HOST = "avatars.steamstatic.com"
HOSTS = frozenset({"api.steampowered.com", "steamcommunity.com", CDN_HOST,
                   "avatars.akamai.steamstatic.com"})
SUMMARIES_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
SUMMARIES_PER_CALL = 100
MAX_META_BYTES = 256 * 1024
MAX_PICTURE_BYTES = 256 * 1024
REQUEST_TIMEOUT = 6.0
PLAYER_DEADLINE = 12.0
REFRESH_DAYS = 7
BACKOFF_CAP_HOURS = 720
RATE_PER_SECOND = 0.5
BURST = 10
PAUSE_SECONDS = 15 * 60
BREAKER_FAILURES = 5
USER_AGENT = "CompetitiveRounds-PlayerCards/1.0"


class FeedError(ValueError):
    """The whole answer is unusable — the batch failed, not its players."""


class FetchError(Exception):
    """One request failed; `kind` is a class word for the log, never a URL."""

    def __init__(self, kind: str, status: int | None = None):
        super().__init__(kind if status is None else f"{kind}:{status}")
        self.kind, self.status = kind, status


class RedirectRefused(Exception):
    pass


# ── references and URLs ────────────────────────────────────────────────

def avatar_url(ref: str) -> str:
    """The picture URL, built from the reference and nothing else."""
    if not AVATAR_REF_RE.match(ref or ""):
        raise ValueError("avatar_ref")
    return f"https://{CDN_HOST}/{ref}_full.jpg"


def is_default_ref(ref) -> bool:
    return isinstance(ref, str) and ref in DEFAULT_AVATAR_REFS


def ref_from_url(url) -> str | None:
    match = _AVATAR_URL_RE.match(url if isinstance(url, str) else "")
    return match.group(1) if match else None


def summaries_url(key: str, steam_ids: Iterable[str]) -> str:
    """Never log the result: it carries the Web API key."""
    ids = list(steam_ids)
    if not key:
        raise ValueError("key")
    if not ids or len(ids) > SUMMARIES_PER_CALL or not all(steamid64.is_individual_id(s) for s in ids):
        raise ValueError("steam_ids")
    return SUMMARIES_URL + "?" + urllib.parse.urlencode({"key": key, "steamids": ",".join(ids)})


def profile_xml_url(steam_id: str) -> str:
    if not steamid64.is_individual_id(steam_id):
        raise ValueError("steam_id")
    return f"https://steamcommunity.com/profiles/{steam_id}?xml=1"


# ── feed parsing ───────────────────────────────────────────────────────

def _ref_of(player: dict) -> str | None:
    ref = player.get("avatarhash")
    if isinstance(ref, str) and AVATAR_REF_RE.match(ref):
        return ref
    return ref_from_url(player.get("avatarfull"))


def parse_summaries(body: bytes, wanted: Iterable[str]) -> dict[str, str | None]:
    """{steam_id: reference or None} for every WANTED id, matched by the
    `steamid` field and never by position. An id the feed omits, or answers
    without a usable reference, is None (that player's attempt failed). A
    body that is not the documented shape raises FeedError."""
    try:
        players = json.loads(bytes(body).decode("utf-8"))["response"]["players"]
    except Exception as exc:
        raise FeedError("shape") from exc
    if not isinstance(players, list):
        raise FeedError("shape")
    out: dict[str, str | None] = {str(s): None for s in wanted}
    for player in players:
        if not isinstance(player, dict):
            continue
        sid = player.get("steamid")
        if isinstance(sid, str) and sid in out and out[sid] is None:
            out[sid] = _ref_of(player)
    return out


def parse_profile_xml(body: bytes) -> str | None:
    """The avatar reference from one profile XML body, or None when the
    profile carries no usable picture (an absence: that player's answer). A
    body that is not a profile at all — a wide encoding, a DOCTYPE or
    entity (refused before parsing), unparseable XML, a root that is neither
    <profile> nor exactly Steam's <response><error> shape — raises FeedError:
    the feed's failure, counted by the breaker, never mistaken for an
    absence (v4 §3, v4.1 §4)."""
    raw = bytes(body)
    # Steam serves UTF-8. A wide encoding (UTF-16/32: NUL bytes, a BOM) could
    # hide a DTD from a byte filter, so it is refused outright, and the
    # DTD/entity check runs on the decoded text (v4.1 §4).
    if b"\x00" in raw or raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        raise FeedError("encoding")
    lowered = raw.decode("utf-8", "replace").lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise FeedError("doctype")
    try:
        root = ET.fromstring(raw)
    except Exception as exc:
        raise FeedError("xml") from exc
    if root.tag == "response":
        # Steam's absence shape is exactly <response><error>…</error></response>;
        # a bare or different <response> is not a profile answer (v4.1 §4).
        if root.find("error") is None:
            raise FeedError("shape")
        return None
    if root.tag != "profile":
        raise FeedError("shape")
    node = root.find("avatarFull")
    return ref_from_url((node.text or "").strip()) if node is not None else None


# ── the bounded reader ─────────────────────────────────────────────────

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RedirectRefused(str(code))


def opener():
    return urllib.request.build_opener(_NoRedirect)


def _cap_socket_wait(resp, seconds: float) -> None:
    """Cap the socket wait of the response's next read: http.client keeps the
    socket behind resp.fp; a fake response has none and needs no cap."""
    try:
        resp.fp.raw._sock.settimeout(max(0.1, float(seconds)))
    except Exception:
        pass


def http_get(url: str, *, max_bytes: int, timeout: float = REQUEST_TIMEOUT, total: float = PLAYER_DEADLINE,
             open_with=None, clock=None, deadline: float | None = None) -> bytes:
    """One bounded GET: https only, host on the allow-list, redirects refused,
    Content-Length checked when present, the body read in chunks up to
    max_bytes + 1 and refused beyond, and the WHOLE exchange — connect,
    headers and every body chunk — inside the deadline (v4 §3, v4.1 §3):
    `deadline` is an absolute time on `clock` the caller shares across a
    player's requests, else `total` seconds from now; every socket wait —
    the open and EACH body read — is capped by `timeout` and by what is left
    of the deadline at that moment, a body that trickles past it is refused
    as `deadline`, and so is an EOF that arrives past it. Blocking — run
    under asyncio.to_thread. Raises FetchError(kind, status); the message
    never carries the URL."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in HOSTS:
        raise FetchError("host")
    now = clock or time.monotonic
    deadline = now() + float(total) if deadline is None else float(deadline)
    if now() >= deadline:
        raise FetchError("deadline")   # the player's budget is spent before this request: no request
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    try:
        wait = min(float(timeout), max(0.1, deadline - now()))
        with (open_with or opener()).open(request, timeout=wait) as resp:
            declared = resp.headers.get("Content-Length")
            if declared is not None and (not str(declared).isdigit() or int(declared) > max_bytes):
                raise FetchError("too_large")
            chunks, got = [], 0
            while True:
                remaining = deadline - now()
                if remaining <= 0:
                    raise FetchError("deadline")
                _cap_socket_wait(resp, min(float(timeout), remaining))   # a read begun late may not block past the deadline
                chunk = resp.read(min(65536, max_bytes + 1 - got))
                if not chunk:
                    break
                chunks.append(chunk)
                got += len(chunk)
                if got > max_bytes:
                    raise FetchError("too_large")
            if now() > deadline:
                raise FetchError("deadline")   # EOF that arrived past the deadline is still past it
            return b"".join(chunks)
    except FetchError:
        raise
    except RedirectRefused as exc:
        raise FetchError("redirect") from exc
    except urllib.error.HTTPError as exc:
        raise FetchError("http", int(exc.code)) from exc
    except Exception as exc:   # URLError, timeout, ssl, connection reset
        raise FetchError(type(exc).__name__.lower()) from exc


# ── budget, breaker, backoff ───────────────────────────────────────────

class TokenBucket:
    """The outbound budget for EVERY Steam request. take() returns the seconds
    to wait before the request may go (0.0 = now). A priority take (priming at
    mint time) may overdraw to -burst and still go now, so a pack open is
    never queued behind the sweep; the caller's deadline bounds the overdraw."""

    def __init__(self, rate: float = RATE_PER_SECOND, burst: float = BURST, now: float | None = None):
        self.rate, self.burst = float(rate), float(burst)
        self.tokens = float(burst)
        self.at = time.monotonic() if now is None else now

    def _refill(self, now: float) -> None:
        self.tokens = min(self.burst, self.tokens + max(0.0, now - self.at) * self.rate)
        self.at = now

    def take(self, cost: float = 1.0, *, priority: bool = False, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        self._refill(now)
        floor = -self.burst if priority else 0.0
        if self.tokens - cost >= floor:
            self.tokens -= cost
            return 0.0
        return (cost + floor - self.tokens) / self.rate


class Breaker:
    """BREAKER_FAILURES consecutive failures of one kind (api / xml / cdn), or
    any 429, pause every request for PAUSE_SECONDS; a success of that kind
    resets its count. state() is the health word: None when open for
    business, else 'paused:<kind>'."""

    def __init__(self, failures: int = BREAKER_FAILURES, pause: float = PAUSE_SECONDS):
        self.limit, self.pause = int(failures), float(pause)
        self.counts: dict[str, int] = {}
        self.paused_until: float | None = None
        self.reason: str | None = None

    def record(self, kind: str, ok: bool, *, status: int | None = None, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if ok:
            self.counts[kind] = 0
            return
        self.counts[kind] = self.counts.get(kind, 0) + 1
        if status == 429 or self.counts[kind] >= self.limit:
            self.paused_until, self.reason = now + self.pause, kind
            self.counts[kind] = 0

    def paused(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if self.paused_until is not None and now >= self.paused_until:
            self.paused_until, self.reason = None, None
        return self.paused_until is not None

    def state(self, now: float | None = None) -> str | None:
        return f"paused:{self.reason}" if self.paused(now) else None


def backoff_hours(fail: int) -> int:
    """Hours until the next attempt after the fail-th consecutive failure:
    2, 4, 8 … capped at BACKOFF_CAP_HOURS (30 days)."""
    return min(2 ** max(1, int(fail)), BACKOFF_CAP_HOURS)


# ── the picture canonicaliser ──────────────────────────────────────────

def canonical_picture(data: bytes) -> bytes:
    """A fetched avatar (JPEG or PNG, ≤ MAX_PICTURE_BYTES, one frame) as the
    stored blob: RGBA, centre-square-cropped, 32–1024 px, written by the
    renderer's pinned encoder (critical chunks only), so two fetches of the
    same picture hash the same. The size is judged from the header BEFORE any
    pixel is decoded. Anything else raises ValueError(kind)."""
    raw = bytes(data)
    if len(raw) > MAX_PICTURE_BYTES:
        raise ValueError("picture_too_large")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if (source.format or "").upper() not in ("JPEG", "PNG"):
                    raise ValueError("picture_format")
                width, height = source.size
                if max(width, height) > pc_face.STEAM_PICTURE_MAX_EDGE:
                    raise ValueError("picture_large")
                if min(width, height) < pc_face.STEAM_PICTURE_MIN_EDGE:
                    raise ValueError("picture_small")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("picture_animated")
                source.load()
                edge = min(width, height)
                left, top = (width - edge) // 2, (height - edge) // 2
                pixels = source.convert("RGBA").crop((left, top, left + edge, top + edge)).tobytes()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("picture_invalid") from exc
    return pc_face._encode_rgba(Image.frombytes("RGBA", (edge, edge), pixels))
