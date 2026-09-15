"""Player Cards portraits, delivery leases and face keys — pure helpers.

Design: ai-collab/sept10-batch/21-player-cards-look-v22.md (§1.7, §2.2,
§3.1-3.4, §6, §8) plus look-r18-dispositions.md. No FastAPI, no database and
no pixels here: main.py owns the routes and the SQL, pc_face.py owns the
rendering. Everything in this module is deterministic and unit-testable.
"""
import asyncio
import bisect
import concurrent.futures
import functools
import hashlib
import json
import os
import time
import re
import threading

# A HARD dependency, not a soft one: the projection's unit is the grapheme
# cluster and only this module splits them. A fallback that split by code point
# would make two boxes project one name differently, under a `renderer_fp` that
# says they agree — so the import failing is the right failure.
import regex as _regex

import steamid64

# ── constants ──────────────────────────────────────────────────────────────
PORTRAIT_SIZE = 1180                     # the upload's edge (§1.7)
PC_PORTRAIT_MAX_BYTES = 1 << 20          # 1 MiB upload cap; re-applied to the canonical bytes (r18 M6)
PC_FACE_MAX_BYTES = 4 << 20              # card ceiling (§1.6)
PC_TILE_MAX_BYTES = 1 << 20              # tile ceiling (§1.6)
DESCRIPTOR_MAX_BYTES = 320               # r18 H4: lossless offsets need room
PACING_SECONDS = 30                      # one accepted upload per player per 30 s (§1.7)
LEASE_SECONDS = 60                       # a delivery lease's life (§6)
LEASE_RESERVE_SECONDS = 3                # the bot's deadline = until - reserve (r18 H2)
COVERAGE_MIN, COVERAGE_MAX = 0.02, 0.60  # fraction of pixels with alpha > 0 (§1.7)
DECODE_BUDGET_S = 2.0                    # decode + canonicalise budget in the pool (§3.2 step 1)
FACE_CACHE_CAP_BYTES = 2 << 30           # disk LRU per box (§2.2)
FACE_CACHE_MAX_AGE_S = 7 * 86400         # a face neither read nor written this long goes (Steam pictures v3 §6)
FACE_CACHE_TMP_MAX_AGE_S = 3600          # a publish temporary older than this belongs to a publish that died (v4 §4)
PREVIEW_TTL_S = 60                       # /card preview cache life (§2.2)
# Two-argument advisory lock class for the per-hash P locks (§3.2 step 3):
# disjoint from the one-argument identity keys by construction (a different
# lock space) and from every other *_LOCK_CLASS in main.py (asserted by test).
PC_P_LOCK_CLASS = 770902

SIZES = ("card", "tile")

# ── the descriptor (§3.4, r18 H4) ─────────────────────────────────────────
# Offsets are the client float's shortest round-trip form ("R"): any finite
# decimal with an optional exponent. NaN / Infinity never match (422).
_NUM = r"-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?"
_PAIR = _NUM + "," + _NUM
DESCRIPTOR_RE = re.compile(
    r"^v1\|face=(?P<eye>[0-9]{1,4}):(?P<mouth>[0-9]{1,4}):(?P<detail>[0-9]{1,4}):(?P<detail2>[0-9]{1,4})"
    r"\|off=" + _PAIR + ";" + _PAIR + ";" + _PAIR + ";" + _PAIR +
    r"\|color=(?P<color>[a-z0-9_]{0,40}):(?P<hex>[0-9a-f]{0,6})"
    r"\|effect=(?P<effect>[a-z0-9_]{0,40})"
    r"\|skin=(?P<skin>0)"
    r"\|anim=(?P<anim>[01])"
    r"\|g=(?P<game>[0-9A-Za-z._-]{1,24})"
    r"\|r=(?P<recipe>[0-9]{1,3})$"
)


def descriptor_parse(descriptor):
    """The descriptor's named parts, or None when it is off-grammar, non-ASCII
    or over DESCRIPTOR_MAX_BYTES."""
    if not isinstance(descriptor, str) or not descriptor:
        return None
    try:
        raw = descriptor.encode("ascii")
    except UnicodeEncodeError:
        return None
    if len(raw) > DESCRIPTOR_MAX_BYTES:
        return None
    m = DESCRIPTOR_RE.match(descriptor)
    return m.groupdict() if m else None


def canon_portrait(steam_id, nonce, upload_sha256, descriptor):
    """The signed line of the portrait writer (mirrors player_cards.canon_*)."""
    return f"pcport:{steam_id}:{nonce}:{upload_sha256}:{descriptor}"


# ── locale (§2.2 EffectivePcLocale) ────────────────────────────────────────
_LOCALE_RE = re.compile(r"^([a-z]{2,3})(?:[-_].*)?$")


def effective_locale(value, served):
    """Lower-case; the primary subtag before any '-' or '_'; served or 'en'."""
    v = (value or "").strip().lower()[:32]
    m = _LOCALE_RE.match(v)
    if not m:
        return "en"
    primary = m.group(1)
    return primary if primary in served or primary == "en" else "en"


# ── names (§2.4 steps 1-2 + the unnamed rule; C and D are the boundary's) ──
# EXACTLY the tag set the mod's nametag styler emits — the same ASCII regex as
# `GameStateWatcher.StripKnownRichTags` (GameStateWatcher.cs:7865-7867), tag for
# tag. Not the blanket `<.*?>` of `StripRichText` beside it: that turns the name
# "AC<DC>Fan" into "ACFan", which is bug 259 and is recorded next to it. Every
# other `<…>` run is literal text and is drawn literally, by Pillow here and by
# TMP with rich text off on the client. If the styler gains a tag family, this
# regex and that one change in the same commit (#279, #341).
_TAG_RE = re.compile(
    r"</?(?:b|i|u|s|allcaps|smallcaps)>|<color=#[0-9A-Fa-f]{6}>|</color>"
    r"|<size=[0-9]{1,3}%>|</size>|<cspace=[0-9]*\.?[0-9]+em>|</cspace>"
    r"|<voffset=[0-9]*\.?[0-9]+em>|</voffset>")

# Cc (tab, CR, LF and the C1 range including NEL), Zl and Zp, and the bidi
# EMBEDDING, OVERRIDE and ISOLATE controls. Not U+200D: the zero-width joiner
# is what holds an emoji sequence together, and removing it renders 👩‍💻 as two
# separate pictures. Not the other format characters around it either — they
# are the coverage projection's business, not this step's, because this step
# also feeds the global display name and must not blank a legal name.
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f\x80-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
_WS_RE = re.compile(r"\s+")


def single_line(s):
    """LF, CR and tab (and every other control) to a space, collapse, trim."""
    if s is None:
        return ""
    s = _CTRL_RE.sub(" ", str(s))
    return _WS_RE.sub(" ", s).strip()


def public_name(stored):
    """The public render name: producer tags stripped, controls normalised,
    whitespace collapsed — the WHOLE composite repeated until the string stops
    changing. None when nothing readable is left or the stored name IS a Steam
    ID (the constructor's fallback) — the caller draws the neutral `pc.unnamed`
    label then (r12 H1).

    The composite iterates rather than just the strip. Today that is a guard
    and not a necessity: step 2 turns a control into a SPACE, never into
    nothing, so it cannot complete a tag for the next pass. It becomes
    load-bearing for any step that REMOVES code points instead of replacing
    them -- the coverage projection is exactly that, and it re-runs this
    composite after its own removal for the same reason (v22 2.4, r15 H4)."""
    s = "" if stored is None else str(stored)
    prev = None
    # Bounded by the string's length: each pass either shortens it or is the
    # last one. The cap is belt and braces against a future rule that grows.
    for _ in range(len(s) + 2):
        if s == prev:
            break
        prev = s
        s = single_line(_TAG_RE.sub("", s))
    if not s or steamid64.is_individual_id(s):
        return None
    return s


# ── the coverage projection C (§2.4, r14 H5, r16 M10) ─────────────────────
# The code points the renderer has a glyph for, generated from the font files
# by assets/pc/build_name_coverage.py and committed: both boxes must project a
# name identically, and the manifest is an input to `renderer_fp`, so changing
# it re-keys every face rather than quietly redrawing one.
COVERAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "assets", "pc", "name_coverage.json")

# A name has to have INK in it. The joiners and variation selectors are kept
# through the projection because they hold sequences together, but a string
# made only of them paints nothing at all: not empty, so the neutral fallback
# never fired, and the card carried a blank where a name goes.
_INK_RE = re.compile(r"[^\s\u200b-\u200f\u2060-\u2064\ufe00-\ufe0f\U000e0100-\U000e01ef]")


def _pairs(ranges):
    return [r[0] for r in ranges], [r[1] for r in ranges]


def _within(pair, codepoint):
    starts, ends = pair
    i = bisect.bisect_right(starts, codepoint) - 1
    return i >= 0 and codepoint <= ends[i]


@functools.lru_cache(maxsize=1)
def _coverage():
    """The manifest, parsed: per-role ranges, the always-set, the candidate
    order per base role, and the emoji rule — everything the run splitter uses
    to decide which font draws a cluster, so that this projection can decide
    the same way."""
    try:
        with open(COVERAGE_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        if int(doc["version"]) != 2:
            raise ValueError("manifest version %s, expected 2" % doc["version"])
        cov = {
            "always": _pairs(doc["always"]),
            "union": _pairs(doc["ranges"]),
            "roles": {role: _pairs(rs) for role, rs in doc["roles"].items()},
            "candidates": {base: tuple(rs) for base, rs in doc["candidates"].items()},
            "emoji_role": str(doc["emoji_role"]),
            "emoji": _regex.compile(doc["emoji_pattern"]),
        }
        if not cov["candidates"] or cov["emoji_role"] not in cov["roles"]:
            raise ValueError("manifest carries no candidate order")
        return cov
    except (OSError, ValueError, KeyError, TypeError) as ex:
        raise RuntimeError(
            "the Player Cards coverage manifest is missing or unusable (%s): %s. "
            "Run backend/api/assets/pc/build_name_coverage.py." % (COVERAGE_PATH, ex))


def coverage_ready():
    """Why the coverage manifest cannot be used, or None when it can.

    A question, not an exception: the callers that need to REFUSE (the face
    routes, the pack writer before it debits) ask this, and the projection
    itself still raises — a caller that projects a name without asking has a
    bug, and a bug is not something to answer around."""
    try:
        _coverage()
        return None
    except Exception as ex:      # noqa: BLE001 — the reason is the answer
        return str(ex)


def drawable(codepoint):
    """Whether ANY renderer font has a glyph for this code point.

    The weaker of the two questions, kept because a single code point is what
    a caller usually has; `cluster_drawable` is the one the projection asks."""
    cov = _coverage()
    return _within(cov["union"], codepoint) or _within(cov["always"], codepoint)


def _role_has(cov, role, codepoint):
    return (_within(cov["always"], codepoint)
            or _within(cov["roles"][role], codepoint))


def cluster_drawable(cluster):
    """Whether the renderer can draw this WHOLE grapheme cluster.

    The question the run splitter answers, asked the same way: it needs ONE
    font to cover every code point of a cluster, so "a" + U+0651 — Latin from
    Noto Sans, the mark from Noto Sans Arabic — is a box even though both code
    points are covered somewhere. Every BASE role must manage it: the name is
    drawn at "black" and the autograph at "script", and a cluster only one of
    them can draw is still a box on the other."""
    cov = _coverage()
    points = [ord(ch) for ch in cluster]
    if cov["emoji"].search(cluster):
        return all(_role_has(cov, cov["emoji_role"], cp) for cp in points)
    for roles in cov["candidates"].values():
        if not any(all(_role_has(cov, role, cp) for cp in points) for role in roles):
            return False
    return True


def graphemes(s):
    """UAX #29 extended grapheme clusters — the renderer's own unit."""
    return _regex.findall(r"\X", str(s))


def coverage_strip(s):
    """Remove every cluster the renderer cannot draw; collapse; trim.

    Removal, not replacement: a name is not improved by a space where a glyph
    the reader never asked about used to be. Cluster-wise, because that is the
    unit the renderer picks a font for."""
    if not s:
        return ""
    kept = "".join(c for c in graphemes(str(s)) if cluster_drawable(c))
    return _WS_RE.sub(" ", kept).strip()


def coverage_project(name):
    """C: the removal, then the WHOLE composite of steps 1-2 to a fixed point.

    The fixed point matters here in a way it does not for P alone: C REMOVES
    code points, so it can complete a producer tag that was not one before
    (`<b\ue001>` is literal text until U+E001 goes, and `<b>` after), and the
    strip has to see the string again. Idempotent by construction:
    C(C(y)) == C(y).

    None when nothing readable is left — the caller draws the neutral label,
    the same one the face draws."""
    if name is None:
        return None
    s = str(name)
    prev = None
    for _ in range(len(s) + 2):
        if s == prev:
            break
        prev = s
        s = single_line(_TAG_RE.sub("", coverage_strip(s)))
    if not s or steamid64.is_individual_id(s) or not _INK_RE.search(s):
        return None
    return s


def public_render_name(stored):
    """P then C: the string every Player Cards payload carries and every face
    draws. ONE function, because applying half of it is the same bug twice."""
    return coverage_project(public_name(stored))


# ── hashing (§2.2) ─────────────────────────────────────────────────────────
def h16(*parts):
    """16 hex of SHA-256 over length-framed parts (str → UTF-8; bytes as is;
    None → empty)."""
    h = hashlib.sha256()
    for p in parts:
        b = p if isinstance(p, bytes) else ("" if p is None else str(p)).encode("utf-8")
        h.update(len(b).to_bytes(4, "big"))
        h.update(b)
    return h.hexdigest()[:16]


def cat_rev(labels):
    """The catalogue revision of one locale: length-framed (identifier,
    effective single-line value) records sorted by identifier."""
    parts = []
    for k in sorted(labels):
        parts.append(k)
        parts.append(single_line(labels[k]))
    return h16("cat_rev", *parts)


def spec_records(spec):
    """One render spec as typed, sorted (key, value) records.

    Typed, so the string "True" and the boolean True are different inputs and
    two specs that draw differently can never hash the same. Sorted, so the
    dict's insertion order is not part of the key."""
    out = []
    for key in sorted(spec):
        value = spec[key]
        if value is None:
            token = "z"
        elif isinstance(value, bool):
            token = "b:1" if value else "b:0"
        elif isinstance(value, (int, float)):
            token = "n:" + repr(value)
        else:
            token = "s:" + str(value)
        out.append(key)
        out.append(token)
    return out


def face_rev(renderer_fp, cat_rev_, spec, portrait_kind, portrait_hash):
    """The face key of one print in one locale: EVERY input the face draws.

    `render_face(spec, labels, portrait_png, size)` draws from exactly four
    things, and all four are in this key: the code, assets and fonts through
    `renderer_fp`; `labels` through `cat_rev_`; `portrait_png` through the
    resolved kind and hash; and `spec` — hashed WHOLE rather than field by
    field, because it is the very dict handed to the renderer. Listing its
    fields here instead is how `edition_id` came to be drawn in the footer and
    missing from the key, under a URL whose whole promise is that its bytes
    never change. `size` is in the URL, not the rev."""
    return h16("face_rev", renderer_fp, cat_rev_, portrait_kind, portrait_hash, *spec_records(spec))


def preview_rev(renderer_fp, cat_rev_, spec, portrait_kind, portrait_hash):
    """The preview key: the same inputs, a different namespace."""
    return h16("preview_rev", renderer_fp, cat_rev_, portrait_kind, portrait_hash, *spec_records(spec))


# ── the resolver (§3.2, read-only, one function for every caller) ──────────
def portrait_for(row):
    """(kind, hash_or_none) from a mapping with subject_deleted, subject_banned,
    portrait_hash and steam_portrait_hash. Never reads more. The uploaded rig
    wins, else the Steam profile picture, else no picture (Steam pictures
    design v2 §1); there is no player-chosen source since 2026-09-13 — every
    card carries whichever picture exists. A row without the steam column
    (an old SELECT) simply has no fallback."""
    if row.get("subject_deleted") or row.get("subject_banned"):
        return ("none", None)
    h = row.get("portrait_hash")
    if h:
        return ("game", str(h))
    s = row.get("steam_portrait_hash")
    return ("steam", str(s)) if s else ("none", None)


# ── route-shape validation (§2.2: any other shape → 404, no render, no cache) ─
_PRINT_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_REV_RE = re.compile(r"^[0-9a-f]{16}$")
_LOCALE_SEG_RE = re.compile(r"^[a-z]{2,3}$")


def face_key(print_id, rev, locale, size):
    """The validated relative cache key, or None."""
    if not (_PRINT_ID_RE.match(print_id or "") and _REV_RE.match(rev or "")
            and _LOCALE_SEG_RE.match(locale or "") and size in SIZES):
        return None
    return f"{print_id}/{rev}/{locale}/{size}.png"


def print_id_ok(print_id):
    return bool(_PRINT_ID_RE.match(print_id or ""))


# ── the render pool (§2.1, r18 M5) ─────────────────────────────────────────
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="pc-render")
_DECODE_SLOTS = threading.BoundedSemaphore(2)


def _guarded(fn, *args):
    """Runs IN the pool: the slot is released by this worker's own finally,
    never by the awaiting request — a request that times out leaves the slot
    held until the decode really ends (r18 M5)."""
    _DECODE_SLOTS.acquire()
    try:
        return fn(*args)
    finally:
        _DECODE_SLOTS.release()


async def in_pool(fn, *args, budget=None):
    """Await fn(*args) on the render pool; budget seconds → asyncio.TimeoutError."""
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(POOL, _guarded, fn, *args)
    if budget is None:
        return await fut
    return await asyncio.wait_for(fut, budget)


# ── the disk cache (§2.2: LRU by bytes, single-flight, atomic publish) ─────
class FaceCache:
    """Rendered faces on local disk under root/<validated key>. A cached file
    is never the authority — the caller's row read is (liveness + revision);
    the cache only skips a render."""

    def __init__(self, root, cap_bytes=FACE_CACHE_CAP_BYTES):
        self.root = root
        self.cap = int(cap_bytes)
        self._lock = threading.Lock()
        self._sizes = {}          # key -> bytes
        self._clock = 0
        self._atime = {}          # key -> tick
        self._seen = {}           # key -> wall clock of the last publish or read (expire)
        self._inflight = {}       # key -> asyncio.Future
        self._scanned = False

    def _scan(self):
        if self._scanned:
            return
        self._scanned = True
        if not os.path.isdir(self.root):
            os.makedirs(self.root, exist_ok=True)
            return
        for dirpath, _dirs, files in os.walk(self.root):
            for f in files:
                if not f.endswith(".png"):
                    continue
                p = os.path.join(dirpath, f)
                key = os.path.relpath(p, self.root).replace(os.sep, "/")
                try:
                    self._sizes[key] = os.path.getsize(p)
                    self._seen.setdefault(key, os.path.getmtime(p))   # a publish or read before the scan wins
                    self._clock += 1
                    self._atime[key] = self._clock
                except OSError:
                    pass

    def path(self, key):
        return os.path.join(self.root, *key.split("/"))

    def read(self, key):
        """Cached bytes or None (touches recency)."""
        with self._lock:
            self._scan()
        p = self.path(key)
        try:
            with open(p, "rb") as f:
                data = f.read()
        except OSError:
            return None
        with self._lock:
            if key in self._sizes:   # not expired or evicted while the bytes were being read (v4 §4)
                self._clock += 1
                self._atime[key] = self._clock
                self._seen[key] = time.time()
                self._sizes[key] = len(data)
        return data

    def _publish(self, key, data):
        p = self.path(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp-%d" % threading.get_ident()
        try:
            with open(tmp, "wb") as f:
                f.write(data)
            with self._lock:   # the swap-in and the index move together, under the lock expiry holds (v4 §4)
                os.replace(tmp, p)
                self._clock += 1
                self._atime[key] = self._clock
                self._seen[key] = time.time()
                self._sizes[key] = len(data)
                self._evict_locked()
        finally:
            try:
                os.remove(tmp)   # still there only when the swap-in did not happen
            except OSError:
                pass

    def _evict_locked(self):
        total = sum(self._sizes.values())
        if total <= self.cap:
            return
        for key in sorted(self._atime, key=self._atime.get):
            if total <= self.cap:
                break
            if not self._unlink_locked(key):
                continue   # still on disk: it stays tracked and is retried later (v4.1 §5)
            total -= self._sizes.pop(key, 0)
            self._atime.pop(key, None)
            self._seen.pop(key, None)

    def _unlink_locked(self, key) -> bool:
        """Remove the file for key under the lock. True when it is gone (removed
        now or already missing); False when the remove failed, in which case
        the caller keeps the entry tracked so a later pass retries instead of
        leaving a readable file nothing tracks (v4.1 §5)."""
        try:
            os.remove(self.path(key))
        except FileNotFoundError:
            pass
        except OSError:
            return False
        return True

    def forget(self, key):
        with self._lock:
            if self._unlink_locked(key):
                self._sizes.pop(key, None)
                self._atime.pop(key, None)
                self._seen.pop(key, None)

    def _sweep_temporaries_locked(self, now, max_age_s=FACE_CACHE_TMP_MAX_AGE_S):
        """Remove publish temporaries older than max_age_s: a publish that
        died between the write and the swap-in left a complete face that no
        index entry, eviction or expiry would ever reach (v4 §4)."""
        gone = 0
        for dirpath, _dirs, files in os.walk(self.root):
            for f in files:
                if ".tmp-" not in f:
                    continue
                p = os.path.join(dirpath, f)
                try:
                    if now - os.path.getmtime(p) > max_age_s:
                        os.remove(p)
                        gone += 1
                except OSError:
                    pass
        return gone

    def expire(self, max_age_s=FACE_CACHE_MAX_AGE_S, now=None):
        """Remove every entry neither published nor read for max_age_s: the
        bound on how long a released picture survives inside derived faces
        (Steam pictures v3 §6), on every box that owns a cache (v4 §4). After
        a restart the age is the file's publish age — a hot face is simply
        rendered once more. Files go UNDER the lock, so a publish cannot slip
        a fresh file under a key this pass is removing. Stale publish
        temporaries go too. An entry whose file will not go (a reader holds
        it open on Windows, a transient error) stays tracked for the next pass
        (v4.1 §5). Returns how many files went."""
        now = time.time() if now is None else now
        with self._lock:
            self._scan()
            stale = [k for k, t in self._seen.items() if now - t > max_age_s]
            gone = 0
            for key in stale:
                if not self._unlink_locked(key):
                    continue   # still on disk: tracked until a later pass removes it (v4.1 §5)
                self._sizes.pop(key, None)
                self._atime.pop(key, None)
                self._seen.pop(key, None)
                gone += 1
            stale_tmp = self._sweep_temporaries_locked(now)
        return gone + stale_tmp

    async def get_or_render(self, key, render_sync):
        """Bytes for key: the cached file, else ONE render shared by every
        concurrent waiter (single-flight), published atomically."""
        data = self.read(key)
        if data is not None:
            return data
        loop = asyncio.get_running_loop()
        fut = self._inflight.get(key)
        if fut is not None:
            return await fut
        fut = loop.create_future()
        self._inflight[key] = fut
        try:
            data = await in_pool(render_sync)
            await loop.run_in_executor(POOL, self._publish, key, data)
            fut.set_result(data)
            return data
        except BaseException as ex:
            if not fut.done():
                fut.set_exception(ex)
            raise
        finally:
            self._inflight.pop(key, None)
