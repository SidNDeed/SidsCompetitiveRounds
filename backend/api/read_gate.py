"""Verified reads (board row 33, item b): the read gate.

A read is VERIFIED when it carries one of three credentials:

  internal key   X-Internal-Key equal to API_SECRET_KEY (the bot; unchanged)
  session        X-Session-Token whose sha256 names a steam_sessions row that
                 exists, is unexpired and is Steam-verified
  operator key   X-Operator-Key naming a live api_operator_keys row
                 (migration 367; issued by an admin route, stored as sha256)

`read_gate` is ONE FastAPI dependency, attached to every GET route by the
route class `ReadGateRoute`, so a new GET route is gated by default. What the
gate does depends on the route's CLASS (the named lists below) and on the
STAGE, one row in runtime_settings (`read_gate_mode`):

  off      the gate counts nothing and refuses nothing (except PROBE)
  log      every gated read is counted by credential class and passes
  enforce  a gated read with no valid credential is refused
  unknown  this process has never read the stage: gated reads answer 503
           read_gate_unavailable until one read succeeds

Classes, and what the gate requires of each:

  OPEN          nothing, in every stage; never counted
  WRITE_ON_GET  the gate takes no action at all (no lookup, no count, no
                refusal): a GET whose handler can write keeps exactly the
                requirements it has today
  ADMIN_SIGNED  the handler's admin signature check runs as today; the gate
                counts and refuses nothing
  PORTAL        the handler's portal token check runs as today; the gate
                counts and refuses nothing
  INTERNAL      the internal key, required by rate_limit_gate and by the
                handler as today; the gate counts and refuses nothing
  BOT_ONLY      enforce: the internal key only (403 internal_key_required);
                log: counted by credential class and passed; off: as today
  PLAYER        enforce: a valid session or the internal key; an operator key
                does not open these
  PUBLIC        (default) enforce: any one valid credential of the three
  PROBE         the canary route: the PUBLIC requirement in EVERY stage

ANY valid credential wins: the gate evaluates every presented credential the
class accepts and passes if one is valid, so an invalid or expired header
never shadows a valid one. With none valid, in this order: a lookup that
raised answers 503 read_gate_unavailable; a lookup the per-address limiter
refused answers 429 rate_limited; a session token unknown to the STANDBY
answers 503 session_replication_pending (the mint lands on the primary and
replication may not have carried it yet); otherwise 401.

Lookups run on their own short session (database.async_session), never the
handler's, so a failed lookup cannot abort the handler's transaction. A
lookup that would read the database (a cache miss) is charged to the
per-address rate limiter first when the request or socket has not been
charged yet (app.state.lookup_charge, set by main; on every route behind
rate_limit_gate the request is already charged and this is a no-op). A
refused charge is the verdict `limited`: no lookup runs.
Positive verdicts are cached: a session until min(now + 60 s, its
expires_at), an operator key for 60 s; negatives never. A revoked operator
key or a deleted session therefore keeps passing on a box for at most 60 s
after the change reaches that box's database.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
import uuid
from collections import OrderedDict, namedtuple
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.routing import APIRoute
from sqlalchemy import text

import database

# Release-train build marker, reported on /health as `read_gate_build`. A code
# constant, equal on both boxes by construction, read by nothing else.
READ_GATE_BUILD = "vr1"

MODES = ("off", "log", "enforce")
UNKNOWN = "unknown"
MODE_TTL = 15.0
CRED_TTL = 60.0
CRED_CACHE_CAP = 20000
MODE_SETTING_KEY = "read_gate_mode"

# The first client release that carries the hold-and-retry of verified reads.
# None until Sid names it; while None the mode route refuses `enforce`
# (409 client_floor_unnamed).
READ_GATE_CLIENT_MIN: str | None = None

# The first client version that reads the stage advert. /api/v1/mod-version
# carries `read_gate` and `read_gate_open` only for a request whose
# X-Mod-Version parses to this or later (advert_requested); every other
# request receives the trunk body unchanged. The header is client-attested,
# so it selects the response shape and nothing else.
READ_GATE_ADVERT_MIN = (1, 41, 0)
_ADVERT_VERSION_RE = re.compile(r"^[0-9]{1,6}(\.[0-9]{1,6}){0,3}$")


def advert_requested(version) -> bool:
    """True only for a strictly dotted-decimal version at or above
    READ_GATE_ADVERT_MIN; absent, empty or unparseable answers False."""
    if not isinstance(version, str) or not _ADVERT_VERSION_RE.match(version):
        return False
    parts = tuple(int(x) for x in version.split("."))
    parts += (0,) * (len(READ_GATE_ADVERT_MIN) - len(parts))
    return parts >= READ_GATE_ADVERT_MIN


# The chat socket's outbound read side is COUNTED in this build, not gated.
# The mode route refuses `enforce` (409 socket_read_gate_absent) while this is
# False, so stage 2 cannot run before the socket gate is built and reviewed.
SOCKET_READ_GATE_BUILT = False

# Same expression as main.IS_REPLICA (both read the one environment value).
REPLICA_NODE = os.getenv("SCR_REPLICA_MODE", "").strip().lower() in ("1", "true", "yes", "on")

OPERATOR_KEY_PREFIX = "scrop1_"
_OPERATOR_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
_MAX_CREDENTIAL_LEN = 128

C_OPEN = "OPEN"
C_WRITE_ON_GET = "WRITE_ON_GET"
C_ADMIN_SIGNED = "ADMIN_SIGNED"
C_PORTAL = "PORTAL"
C_INTERNAL = "INTERNAL"
C_BOT_ONLY = "BOT_ONLY"
C_PLAYER = "PLAYER"
C_PUBLIC = "PUBLIC"
C_PROBE = "PROBE"

PROBE_PATH = "/api/v1/read-gate/probe"
SOCKET_TEMPLATE = "/api/v1/ws/chat"

# -- Route classes -----------------------------------------------------------

# Readable with no credential in every stage, each with its reason.
OPEN: dict[str, str] = {
    "/api/v1/health": "the release train, the edge and both boxes' probes read it with no "
                      "session; health words only, no player data",
    "/api/v1/mod-version": "the boot probe and the version check run before any session; the "
                           "update decision and the read-gate mode advertisement rest on it",
    "/api/v1/admin/maintenance/status": "readable before the version check by design",
    "/api/v1/alerts/active": "fetched at boot before any session and aimed at clients below "
                             "the floor",
    "/api/v1/release-notes/{locale}": "part of the update path, shown to a client about to "
                                      "update",
    "/api/v1/release-notes/full/{locale}": "part of the update path",
    "/api/v1/releases/recent": "part of the update path, fetched with the notes",
    "/api/v1/i18n/pack/{locale}": "the game's own UI text, no player data; fetched at boot "
                                  "before any session",
    "/translate": "the translation portal's HTML page; it carries no data and every data "
                  "call it makes is a PORTAL route",
}

# A GET whose handler can reach a mutation or a commit that changes game,
# queue, lobby, lease, presence, bet, gold, portrait or stream state, with the
# request as its trigger. The gate takes no action on these in any stage and
# they are outside the operator version exemption: each keeps exactly the
# requirements it has today. A route that is both session-reached and a
# writer is here, not in PLAYER. test_write_on_get_inventory finds these from
# the live app; a flagged route that is neither here nor in WRITE_REVIEWED
# fails it.
WRITE_ON_GET: dict[str, str] = {
    "/api/v1/team/series/{series_id}/state": "cancels an overdue series, reconciles its bets "
                                             "and commits",
    "/api/v1/series/active": "prunes stale series and refunds their bets",
    "/api/v1/queue/poll/{steam_id}": "queue state transitions, pair publication and the "
                                     "seat lease",
    "/api/v1/team/queue/poll/{steam_id}": "team queue transitions, series lock, bet "
                                          "reconciliation and the seat lease",
    "/api/v1/ovt/queue/poll/{steam_id}": "1v2 queue transitions, group dissolution and the "
                                         "seat lease",
    "/api/v1/ffa/queue/poll/{steam_id}": "FFA queue transitions, bet settlement and refunds, "
                                         "the seat lease",
    "/api/v1/team/lobby/state": "renews the lobby lease and stores region pings",
    "/api/v1/team/lobby/resolve": "lobby resolution commits",
    "/api/v1/ovt/lobby/state": "renews the lobby lease and stores region pings",
    "/api/v1/ovt/lobby/resolve": "lobby resolution commits",
    "/api/v1/presence/ping": "writes presence and renews the lease",
    "/api/v1/pc/packs/result": "starts the Steam picture fetch, which writes the portrait",
    "/api/v1/broadcast/target": "stream-post upkeep writes the stream post state",
    "/api/v1/music/ratings/mine": "session-reached and folds matured ratings (UPDATE, DELETE, "
                                  "commit)",
    "/api/v1/mail/inbox": "session-reached and syncs podium title holders through the sender "
                          "colours",
    "/api/v1/mail/{message_id}": "session-reached and syncs podium title holders through the "
                                 "sender colours",
    "/api/v1/tournaments/players/{steam_id}/penalty": "the handler recomputes the penalty row "
                                                      "and commits",
}

# Routes test_write_on_get_inventory flags that are NOT write-on-get, each
# with the exact writer bindings it explains and why the gate may act on the
# route. A route that gains a writer not named here fails the inventory.
_PODIUM = frozenset({"_sync_podium_holders"})
_R_PODIUM = ("derived-state upkeep: the podium title holders are recomputed from the "
             "rating tables alone, idempotently, in their own session, and every board "
             "read and the match-submit path performs the same sync; a refused unverified "
             "read defers it to the next verified read and changes no outcome")
_R_NAME = ("`ready` is a name in this handler that the closure walk also resolves to the "
           "tournaments module's ready-check route; this GET never calls that route")
_R_TRADE_SQL = ("the trade claim and move statements are reached as DATA through "
                "_PC_TRADE_DERIVED (the trading health word derives its answer from their "
                "text); this GET executes neither")
_R_TRIAGE = ("the commit ends the triage's REPEATABLE READ, READ ONLY transaction; it "
             "writes nothing")
_R_INTERNAL = ("INTERNAL class: the gate never refuses or looks anything up on it; the "
               "internal key requirement is enforced by rate_limit_gate and the handler, "
               "unchanged")
WRITE_REVIEWED: dict[str, tuple[frozenset, str]] = {
    "/api/v1/achievements/{key}/earners": (_PODIUM, _R_PODIUM),
    "/api/v1/chat/recent": (_PODIUM, _R_PODIUM),
    "/api/v1/ffa/leaderboard": (_PODIUM, _R_PODIUM),
    "/api/v1/ffa/lobbies": (_PODIUM, _R_PODIUM),
    "/api/v1/ffa/recent": (_PODIUM, _R_PODIUM),
    "/api/v1/leaderboard": (_PODIUM, _R_PODIUM),
    "/api/v1/ovt/leaderboard": (_PODIUM, _R_PODIUM),
    "/api/v1/ovt/lobbies": (_PODIUM, _R_PODIUM),
    "/api/v1/players/{steam_id}": (_PODIUM, _R_PODIUM),
    "/api/v1/players/{steam_id}/matches": (_PODIUM, _R_PODIUM),
    "/api/v1/presence/online": (_PODIUM, _R_PODIUM),
    "/api/v1/records": (_PODIUM, _R_PODIUM),
    "/api/v1/team/all-series-paged": (_PODIUM, _R_PODIUM),
    "/api/v1/team/leaderboard": (_PODIUM, _R_PODIUM),
    "/api/v1/team/lobbies": (_PODIUM, _R_PODIUM),
    "/api/v1/spectate/games": (_PODIUM | {"ready"}, _R_PODIUM + "; " + _R_NAME),
    "/api/v1/tournaments/current": (_PODIUM | {"ready"}, _R_PODIUM + "; " + _R_NAME),
    "/api/v1/music/ratings": (frozenset({"_music_ratings_fold"}),
                              "derived-state upkeep: the fold publishes matured ratings, "
                              "which every read already computes exactly through the "
                              "effective-stars CASE, and the rating POST folds too; a "
                              "refused unverified read changes no answer"),
    "/api/v1/health": (frozenset({"_PC_TRADE_CLAIM_SQL", "_PC_TRADE_MOVE_SQL"}), _R_TRADE_SQL),
    "/api/v1/pc/trades": (frozenset({"_PC_TRADE_CLAIM_SQL", "_PC_TRADE_MOVE_SQL"}),
                          _R_TRADE_SQL),
    "/api/v1/admin/pc/trades": (frozenset({"_PC_TRADE_CLAIM_SQL", "_PC_TRADE_MOVE_SQL"}),
                                _R_TRADE_SQL + "; ADMIN_SIGNED: the gate refuses nothing"),
    "/api/v1/admin/quarantine/triage": (frozenset({"_triage_read_txn"}), _R_TRIAGE),
    "/api/v1/admin/quarantine/triage/{mode}/{group_id}": (frozenset({"_triage_read_txn"}),
                                                          _R_TRIAGE),
    "/api/v1/internal/quarantine/digest": (frozenset({"_triage_read_txn"}),
                                           _R_TRIAGE + "; " + _R_INTERNAL),
    "/api/v1/chat/moderate/mutes": (frozenset({"_check_steam_session"}),
                                    "the session check's one-time arming stamp, written only "
                                    "for a presented verified session; ADMIN_SIGNED: the gate "
                                    "refuses nothing"),
    "/api/v1/internal/chat/mod-actions": (frozenset({"internal_chat_mod_actions"}),
                                          _R_INTERNAL),
    "/api/v1/internal/chat/since": (_PODIUM, _R_INTERNAL),
    "/api/v1/internal/pc/events/pending": (frozenset({"internal_pc_events_pending"}),
                                           _R_INTERNAL),
    "/api/v1/internal/pc/face/preview/{player_ref}/{locale}": (
        frozenset({"_pc_release_portrait_blob", "_pc_steam_prime", "_pc_steam_process",
                   "_pc_steam_write"}), _R_INTERNAL),
    "/api/v1/internal/stream-posts/pending": (frozenset({"internal_stream_posts_pending"}),
                                              _R_INTERNAL),
}
_R_PORTAL = ("the portal token's first-use address binding (_portal_auth), written only for "
             "a presented portal token; PORTAL: the gate refuses nothing")
for _p in ("/api/v1/i18n/approved", "/api/v1/i18n/contributors", "/api/v1/i18n/grants/mine",
           "/api/v1/i18n/history", "/api/v1/i18n/keys", "/api/v1/i18n/progress",
           "/api/v1/i18n/proposals"):
    WRITE_REVIEWED[_p] = (frozenset({"_portal_auth"}), _R_PORTAL)
del _p

# Routes that already require the admin signature (admin_steam_id +
# hmac_signature, verified by _require_admin) in their handler.
ADMIN_SIGNED: frozenset = frozenset({
    "/api/v1/admin/actions",
    "/api/v1/admin/admins",
    "/api/v1/admin/alerts/list",
    "/api/v1/admin/banned-users",
    "/api/v1/admin/cosmetic-frames",
    "/api/v1/admin/cosmetic-release-candidates",
    "/api/v1/admin/cosmetic-submissions",
    "/api/v1/admin/flagged-matches",
    "/api/v1/admin/i18n/grants/list",
    "/api/v1/admin/moderation-cases",
    "/api/v1/admin/pc/trades",
    "/api/v1/admin/quarantine",
    "/api/v1/admin/quarantine/triage",
    "/api/v1/admin/quarantine/triage/{mode}/{group_id}",
    "/api/v1/admin/recent-series",
    "/api/v1/bug-reports",
    "/api/v1/bug-reports/{report_id}",
    "/api/v1/bug-reports/{report_id}/log",
    "/api/v1/chat/moderate/mutes",
    "/api/v1/chat/moderate/spam-patterns",
    "/api/v1/admin/operators",
    "/api/v1/admin/read-census",
})

# Routes that already require the translation portal token (X-Portal-Token,
# verified by _portal_auth) in their handler.
PORTAL: frozenset = frozenset({
    "/api/v1/i18n/approved",
    "/api/v1/i18n/contributors",
    "/api/v1/i18n/grants/mine",
    "/api/v1/i18n/history",
    "/api/v1/i18n/keys",
    "/api/v1/i18n/progress",
    "/api/v1/i18n/proposals",
})

# INTERNAL is every /api/v1/internal/* GET by prefix, plus these two, which
# check the internal key in their handlers. Unchanged in every stage.
INTERNAL_PREFIX = "/api/v1/internal/"
INTERNAL_NAMED: frozenset = frozenset({
    "/api/v1/admin/missing-discord-usernames",
    "/api/v1/tournaments/internal/watch",
})

# The bot's poll reads. `bug-reports/events/recent` joins the reporter's
# player row; `bug-reports/recent` returns stored report fields only. Their
# one caller, the bot, sends the internal key on every request. Governed by
# the stage: enforce requires the internal key; log counts and passes, so an
# operator calling them shows in the census; off is as today.
BOT_ONLY: frozenset = frozenset({
    "/api/v1/bug-reports/recent",
    "/api/v1/bug-reports/events/recent",
    "/api/v1/players/by-discord/{discord_id}",
})

# Routes that answer about the caller's own seat: a valid session or the
# internal key. An operator key does not open them.
PLAYER: frozenset = frozenset({
    "/api/v1/artist/cosmetic-preview",
    "/api/v1/artist/my-submissions",
    "/api/v1/artist/{steam_id}/items",
    "/api/v1/artist/{steam_id}/sales",
    "/api/v1/broadcast/report-status",
    "/api/v1/h2h/{steam_id}/{opponent_steam_id}",
    "/api/v1/mail/blocks",
    "/api/v1/mail/sent",
    "/api/v1/mail/settings",
    "/api/v1/mail/status",
    "/api/v1/pc/card",
    "/api/v1/pc/collection",
    "/api/v1/pc/me",
    "/api/v1/pc/packs",
    "/api/v1/pc/trades",
    "/api/v1/report",
})

PROBE: frozenset = frozenset({PROBE_PATH})

# The classes the gate never refuses for want of a read credential. The
# client sends a request to any of these whatever the advertised stage; it is
# published in /api/v1/mod-version as `read_gate_open`.
UNGATED_CLASSES = (C_OPEN, C_WRITE_ON_GET, C_ADMIN_SIGNED, C_PORTAL, C_INTERNAL)
# Classes exempt from the never-loaded 503 (their behaviour does not depend on
# the stage).
_UNKNOWN_EXEMPT = (C_OPEN, C_WRITE_ON_GET, C_ADMIN_SIGNED, C_PORTAL, C_INTERNAL)
# Classes that never take the version exemption for an operator key.
_NO_OPERATOR_VERSION_EXEMPTION = (C_WRITE_ON_GET, C_PLAYER, C_BOT_ONLY)


def route_class(template: str) -> str:
    """The class of a GET route template. Exactly one per template: the
    named lists are disjoint (test_read_gate_inventory asserts it)."""
    if template in PROBE:
        return C_PROBE
    if template in OPEN:
        return C_OPEN
    if template in WRITE_ON_GET:
        return C_WRITE_ON_GET
    if template in ADMIN_SIGNED:
        return C_ADMIN_SIGNED
    if template in PORTAL:
        return C_PORTAL
    if template.startswith(INTERNAL_PREFIX) or template in INTERNAL_NAMED:
        return C_INTERNAL
    if template in BOT_ONLY:
        return C_BOT_ONLY
    if template in PLAYER:
        return C_PLAYER
    return C_PUBLIC


# -- Clocks (one seam each, so a test controls time) -------------------------

def _mono() -> float:
    return time.monotonic()


def _wall() -> datetime:
    return datetime.now(timezone.utc)


_SEEN: set = set()


def _log_once(key: str, line: str) -> None:
    if key not in _SEEN:
        _SEEN.add(key)
        print(line)


# -- The stage (runtime_settings.read_gate_mode) -----------------------------
#
# TTL cache with a sticky last-known value and a generation fence, the
# chat-lockdown pattern. NEVER-LOADED is its own state, `unknown`: only a
# successful query that returns no row means `off`. A failed first read
# leaves the process `unknown` (gated reads answer 503) and is retried at TTL
# cadence, not per request; a failed later read keeps the last-known value.

_MODE_SQL = "SELECT value FROM runtime_settings WHERE key = 'read_gate_mode'"
_mode_cache = {"value": UNKNOWN, "loaded": False, "at": 0.0, "gen": 0}


def _parse_mode(raw) -> str:
    if raw is None:
        return "off"
    value = str(raw).strip().lower()
    if value not in MODES:
        raise ValueError(f"unrecognised read_gate_mode value {value[:16]!r}")
    return value


async def current_mode(db=None) -> str:
    """The stage this process acts on: off, log, enforce or unknown. `db`, when
    given, is read inside a SAVEPOINT (health passes its own session);
    otherwise a short session of its own."""
    c = _mode_cache
    now = _mono()
    if c["loaded"] and now - c["at"] <= MODE_TTL:
        return c["value"]
    if not c["loaded"] and c["at"] > 0 and now - c["at"] <= MODE_TTL:
        return UNKNOWN
    gen = c["gen"]
    try:
        if db is not None:
            async with db.begin_nested():
                raw = (await db.execute(text(_MODE_SQL))).scalar()
        else:
            async with database.async_session() as s:
                raw = (await s.execute(text(_MODE_SQL))).scalar()
        value = _parse_mode(raw)
    except Exception as ex:
        if c["gen"] == gen:
            c["at"] = _mono()
        if c["loaded"]:
            return c["value"]
        _log_once("mode-unknown", f"[READ-GATE] stage read failed with no known stage; "
                                  f"gated reads answer 503 until a read succeeds: {ex}")
        return UNKNOWN
    if c["gen"] == gen:
        c["value"] = value
        c["loaded"] = True
        c["at"] = _mono()
        return value
    return c["value"] if c["loaded"] else UNKNOWN


def mode_word() -> str:
    """The cached stage with no I/O (the degraded health arm)."""
    return _mode_cache["value"] if _mode_cache["loaded"] else UNKNOWN


def mode_cache_set(value: str) -> None:
    """After the mode route commits: this process acts on the new stage from
    its next request. An in-flight read is fenced off by the generation."""
    if value not in MODES:
        raise ValueError(value)
    _mode_cache["gen"] += 1
    _mode_cache["value"] = value
    _mode_cache["loaded"] = True
    _mode_cache["at"] = _mono()


# -- Credentials -------------------------------------------------------------

_SESSION_SQL = ("SELECT verified, expires_at FROM steam_sessions WHERE token_hash = :th")
_OPERATOR_SQL = ("SELECT id, operator_name, slot FROM api_operator_keys "
                 "WHERE key_hash = :kh AND revoked_at IS NULL")

_cred_cache: "OrderedDict[str, tuple[float, object]]" = OrderedDict()

# The per-address rate limiter's charge: app.state.lookup_charge(conn) -> True
# when the lookup may read the database, set by main on its app. It charges a
# request or socket the limiter has not charged yet (a route in
# main._RATE_LIMIT_BYPASS, the version gate's operator exemption, the chat
# socket) and is a no-op for one already charged. It is read from the app that
# serves `conn` (scope["app"]), not from a module global, so a second import of
# main (as api.main) builds a second app with its own charge and cannot change
# which buckets the first app's connections are charged to. A connection with
# no app, or an app with no charge (this module alone, as in unit tests of the
# verifiers), charges nothing.
def _lookup_charge(conn):
    scope = getattr(conn, "scope", None)
    app = scope.get("app") if isinstance(scope, dict) else None
    return getattr(getattr(app, "state", None), "lookup_charge", None)


def _lookup_allowed(conn) -> bool:
    """Charge `conn` before a database lookup; False when the limiter refused
    it. A charge that raises lets the lookup run: the limiter is an
    availability bound, and its own failure must not refuse a valid read."""
    if conn is None:
        return True
    hook = _lookup_charge(conn)
    if hook is None:
        return True
    try:
        return bool(hook(conn))
    except Exception as ex:
        _log_once("lookup-charge-error", f"[READ-GATE] lookup charge failed: {ex}")
        return True


def _cache_get(key: str):
    hit = _cred_cache.get(key)
    if hit is None:
        return None
    if hit[0] > _mono():
        return hit
    del _cred_cache[key]
    return None


def _cache_put(key: str, ttl: float, payload) -> None:
    if ttl <= 0:
        return
    _cred_cache[key] = (_mono() + ttl, payload)
    _cred_cache.move_to_end(key)
    while len(_cred_cache) > CRED_CACHE_CAP:
        _cred_cache.popitem(last=False)


def credential_cache_clear() -> None:
    _cred_cache.clear()


def forget_operator_key_id(key_row_id: int) -> None:
    """Drop this process's cached positive for one operator key row (the
    revoke route, on the box that revoked it). Other processes keep theirs
    for at most CRED_TTL."""
    for k in [k for k, v in _cred_cache.items()
              if k.startswith("o:") and isinstance(v[1], tuple) and v[1][0] == key_row_id]:
        del _cred_cache[k]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def internal_key_valid(presented) -> bool:
    """Fails closed when API_SECRET_KEY is unset."""
    expected = os.getenv("API_SECRET_KEY", "")
    if not expected or not presented:
        return False
    return hmac.compare_digest(str(presented), expected)


async def verify_session(token, conn=None):
    """("absent"|"bad"|"miss"|"error"|"limited"|"valid", None). `miss` = no
    row with this hash; `bad` = a row that is expired or not Steam-verified,
    or a token no mint could have issued; `limited` = the per-address limiter
    refused `conn` before the lookup, so none ran."""
    if not token:
        return "absent", None
    if len(token) > _MAX_CREDENTIAL_LEN:
        return "bad", None
    key = "s:" + _sha(token)
    if _cache_get(key) is not None:
        return "valid", None
    if not _lookup_allowed(conn):
        return "limited", None
    try:
        async with database.async_session() as s:
            row = (await s.execute(text(_SESSION_SQL), {"th": key[2:]})).mappings().first()
    except Exception as ex:
        _log_once("session-lookup-error", f"[READ-GATE] session lookup failed: {ex}")
        return "error", None
    if row is None:
        return "miss", None
    now = _wall()
    expires = row["expires_at"]
    if not row["verified"] or (expires is not None and expires <= now):
        return "bad", None
    ttl = CRED_TTL if expires is None else min(CRED_TTL, (expires - now).total_seconds())
    _cache_put(key, ttl, True)
    return "valid", None


async def verify_operator_key(key_value, conn=None):
    """("absent"|"bad"|"error"|"limited"|"valid", payload) where payload is
    (id, slot, operator_name) for a live key; `limited` as verify_session."""
    if not key_value:
        return "absent", None
    if (len(key_value) > _MAX_CREDENTIAL_LEN
            or not key_value.startswith(OPERATOR_KEY_PREFIX)):
        return "bad", None
    key = "o:" + _sha(key_value)
    hit = _cache_get(key)
    if hit is not None:
        return "valid", hit[1]
    if not _lookup_allowed(conn):
        return "limited", None
    try:
        async with database.async_session() as s:
            row = (await s.execute(text(_OPERATOR_SQL), {"kh": key[2:]})).mappings().first()
    except Exception as ex:
        _log_once("operator-lookup-error", f"[READ-GATE] operator key lookup failed: {ex}")
        return "error", None
    if row is None:
        return "bad", None
    payload = (int(row["id"]), int(row["slot"]), str(row["operator_name"]))
    _cache_put(key, CRED_TTL, payload)
    return "valid", payload


def canonical_operator_name(raw) -> str:
    """The ONE canonical operator identity: stripped, lowercased, and a slug
    the migration's CHECK accepts. Called before the advisory lock, the
    insert, the admin signature's target and every lookup."""
    name = str(raw or "").strip().lower()
    if not _OPERATOR_NAME_RE.fullmatch(name):
        raise ValueError("operator_name must be 2-32 characters of a-z, 0-9 and '-', "
                         "starting with a letter or digit")
    return name


def new_operator_key() -> tuple[str, str, str]:
    """(key, sha256 hex, hint). The key is shown once; only the hash is
    stored."""
    key = OPERATOR_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, _sha(key), key[len(OPERATOR_KEY_PREFIX):len(OPERATOR_KEY_PREFIX) + 6]


# -- Census (in memory, per process) -----------------------------------------

BOOT_ID = uuid.uuid4().hex
SINCE = datetime.now(timezone.utc).isoformat()
_SALT = secrets.token_bytes(16)
_SOURCES_CAP = 4096
_AGENTS_CAP = 50
_SOURCE_HOURS_KEPT = 48
UNVERIFIED_CLASSES = frozenset({"bad_session", "bad_operator_key", "replication_pending",
                                "lookup_error", "lookup_limited", "mod_no_session", "other",
                                "mode_unknown"})

_census: dict = {}
_sources: dict = {}
_agents: dict = {}


def census_reset() -> None:
    _census.clear()
    _sources.clear()
    _agents.clear()


def census_add(template, method, cred_class, key_id, version_present, refused,
          client_host=None, agent=None) -> None:
    k = (template, method, cred_class, key_id or "", bool(version_present), bool(refused))
    _census[k] = _census.get(k, 0) + 1
    hour = _wall().strftime("%Y-%m-%dT%H")
    if client_host:
        bucket = _sources.setdefault((cred_class, hour), set())
        if len(bucket) < _SOURCES_CAP:
            bucket.add(hashlib.sha256(_SALT + client_host.encode()).hexdigest()[:16])
        if len(_sources) > 64:
            keep = sorted({h for _c, h in _sources})[-_SOURCE_HOURS_KEPT:]
            for old in [x for x in _sources if x[1] not in keep]:
                del _sources[old]
    if cred_class in UNVERIFIED_CLASSES:
        agents = _agents.setdefault(cred_class, {})
        ua = (agent or "")[:60]
        if ua in agents or len(agents) < _AGENTS_CAP:
            agents[ua] = agents.get(ua, 0) + 1


def census_snapshot(mode: str) -> dict:
    return {
        "node": "standby" if REPLICA_NODE else "primary",
        "boot_id": BOOT_ID,
        "since": SINCE,
        "mode": mode,
        "build": READ_GATE_BUILD,
        "counts": [
            {"route": k[0], "method": k[1], "class": k[2], "key_id": k[3],
             "version_header": k[4], "refused": k[5], "count": v}
            for k, v in sorted(_census.items())
        ],
        "distinct_sources": [
            {"class": c, "hour": h, "count": len(s)} for (c, h), s in sorted(_sources.items())
        ],
        "agents": {c: dict(sorted(a.items())) for c, a in sorted(_agents.items())},
    }


# -- The gate ----------------------------------------------------------------

NO_STORE = "no-store, private"


def _refuse(status: int, detail: str, retry_after: int | None = None) -> HTTPException:
    headers = {"Cache-Control": NO_STORE}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return HTTPException(status_code=status, detail=detail, headers=headers)


def _key_id(payload) -> str:
    return "" if payload is None else f"{payload[0]}/{payload[1]}"


class _Evaluation:
    __slots__ = ("valid_class", "key_id", "operator_payload", "error", "limited",
                 "standby_miss", "bad_session", "bad_operator")

    def __init__(self):
        self.valid_class = None
        self.key_id = ""
        self.operator_payload = None
        self.error = False
        self.limited = False
        self.standby_miss = False
        self.bad_session = False
        self.bad_operator = False


async def _operator_verdict(request):
    """The operator verdict, reusing the one version_gate stored for the same
    key on this request (the same verifier and cache)."""
    presented = request.headers.get("X-Operator-Key")
    stored = getattr(request.state, "read_gate_operator", None)
    if presented and stored is not None and stored[0] == _sha(presented):
        return stored[1], stored[2]
    return await verify_operator_key(presented, request)


async def evaluate(request, accept_operator: bool) -> _Evaluation:
    """Every presented credential, in a fixed order; the first VALID one the
    class accepts names the class. An operator key is still looked up where
    it is not accepted, so the census can say who sent the read."""
    ev = _Evaluation()
    headers = request.headers
    if internal_key_valid(headers.get("X-Internal-Key")):
        ev.valid_class = "internal"
        return ev
    verdict, _ = await verify_session(headers.get("X-Session-Token"), request)
    if verdict == "valid":
        ev.valid_class = "session"
        return ev
    if verdict == "error":
        ev.error = True
    elif verdict == "limited":
        ev.limited = True
    elif verdict == "miss":
        if REPLICA_NODE:
            ev.standby_miss = True
        else:
            ev.bad_session = True
    elif verdict == "bad":
        ev.bad_session = True
    over, payload = await _operator_verdict(request)
    if over == "valid":
        ev.operator_payload = payload
        ev.key_id = _key_id(payload)
        if accept_operator:
            ev.valid_class = "operator:" + payload[2]
            return ev
    elif over == "error":
        if accept_operator:
            ev.error = True
    elif over == "limited":
        if accept_operator:
            ev.limited = True
    elif over == "bad":
        ev.bad_operator = True
    return ev


def _unverified_class(ev: _Evaluation, version_present: bool) -> str:
    if ev.operator_payload is not None:
        return "operator:" + ev.operator_payload[2]
    if ev.error:
        return "lookup_error"
    if ev.limited:
        return "lookup_limited"
    if ev.standby_miss:
        return "replication_pending"
    if ev.bad_session:
        return "bad_session"
    if ev.bad_operator:
        return "bad_operator_key"
    return "mod_no_session" if version_present else "other"


def _refusal_for(ev: _Evaluation, cls: str) -> HTTPException:
    if ev.error:
        return _refuse(503, "read_gate_unavailable", retry_after=5)
    if ev.limited:
        return _refuse(429, "rate_limited", retry_after=10)
    if ev.standby_miss:
        return _refuse(503, "session_replication_pending", retry_after=2)
    if ev.bad_session:
        return _refuse(401, "session_required")
    if cls == C_PLAYER:
        return _refuse(401, "player_session_required")
    if ev.bad_operator:
        return _refuse(401, "operator_key_invalid")
    return _refuse(401, "read_credential_required")


def _presence_class(request, cls: str) -> str:
    """For the classes the gate only counts: no lookups, presence only."""
    if internal_key_valid(request.headers.get("X-Internal-Key")):
        return "internal"
    if cls == C_ADMIN_SIGNED and (request.query_params.get("hmac_signature")
                                  or request.query_params.get("sig")):
        return "admin_signature"
    if cls == C_PORTAL and request.headers.get("X-Portal-Token"):
        return "portal_token"
    return "other"


def _client_host(request):
    client = getattr(request, "client", None)
    return client.host if client else None


async def read_gate(request: Request) -> None:
    """The route dependency. See the module docstring."""
    route = request.scope.get("route")
    template = getattr(route, "path", None) or request.url.path
    cls = route_class(template)
    if cls in (C_OPEN, C_WRITE_ON_GET):
        return
    method = request.method
    version_present = bool(request.headers.get("X-Mod-Version"))
    host = _client_host(request)
    agent = request.headers.get("User-Agent")
    mode = await current_mode()
    if cls in (C_ADMIN_SIGNED, C_PORTAL, C_INTERNAL):
        if mode in ("log", "enforce"):
            census_add(template, method, _presence_class(request, cls), "", version_present,
                  False, host, agent)
        return
    if mode == UNKNOWN:
        census_add(template, method, "mode_unknown", "", version_present, True, host, agent)
        raise _refuse(503, "read_gate_unavailable", retry_after=5)
    if cls == C_PROBE:
        request.state.read_gate_no_store = True
    elif mode == "off":
        return
    elif mode == "enforce":
        request.state.read_gate_no_store = True
    if cls == C_BOT_ONLY and mode == "enforce":
        if internal_key_valid(request.headers.get("X-Internal-Key")):
            census_add(template, method, "internal", "", version_present, False, host, agent)
            return
        ev = await evaluate(request, accept_operator=True)
        cred = ev.valid_class or _unverified_class(ev, version_present)
        census_add(template, method, cred, ev.key_id, version_present, True, host, agent)
        raise _refuse(403, "internal_key_required")
    ev = await evaluate(request, accept_operator=(cls != C_PLAYER))
    if ev.valid_class is not None:
        census_add(template, method, ev.valid_class, ev.key_id, version_present, False, host, agent)
        request.state.read_gate_credential = (ev.valid_class, ev.key_id)
        return
    cred = _unverified_class(ev, version_present)
    enforcing = (mode == "enforce" or cls == C_PROBE)
    census_add(template, method, cred, ev.key_id, version_present, enforcing, host, agent)
    if enforcing:
        raise _refusal_for(ev, cls)


class ReadGateRoute(APIRoute):
    """An APIRoute that carries `read_gate` exactly once on every GET route.

    The guard compares the dependency CALLABLE, so a route re-created by
    include_router (which passes the original route's dependencies back in)
    is not given a second copy."""

    def __init__(self, path, endpoint, **kwargs):
        methods = kwargs.get("methods")
        methods = {"GET"} if methods is None else {str(m).upper() for m in methods}
        if "GET" in methods:
            deps = list(kwargs.get("dependencies") or ())
            if not any(getattr(d, "dependency", None) is read_gate for d in deps):
                kwargs["dependencies"] = [Depends(read_gate)] + deps
        super().__init__(path, endpoint, **kwargs)


# -- The version gate's operator verdict -------------------------------------

def match_template(app, scope):
    """The template of the route this request would be routed to, or None."""
    from starlette.routing import Match
    for route in app.router.routes:
        try:
            match, _child = route.matches(scope)
        except Exception:
            continue
        if match == Match.FULL:
            return getattr(route, "path", None)
    return None


async def operator_version_exempt(request, app) -> bool:
    """A GET with X-Operator-Key and no X-Mod-Version may pass version_gate only
    when the key validates as live, through the gate's own verifier and cache,
    and the matched route is not WRITE_ON_GET, PLAYER or BOT_ONLY. The verdict
    is stored on request.state for the gate to reuse."""
    if request.method != "GET":
        return False
    presented = request.headers.get("X-Operator-Key")
    if not presented:
        return False
    template = match_template(app, request.scope)
    if template is None or route_class(template) in _NO_OPERATOR_VERSION_EXEMPTION:
        return False
    verdict, payload = await verify_operator_key(presented, request)
    request.state.read_gate_operator = (_sha(presented), verdict, payload)
    return verdict == "valid"


# -- The chat socket (counted in this build) ---------------------------------

def socket_census_class(internal_ok: bool, session_presented: bool, operator: str,
                        operator_name: str = "", version_present: bool = True) -> str:
    """The connect-time counting class of one chat socket, one of five:
    internal (a valid internal key), session (a session token was presented),
    operator:<name> (a live operator key), mod_no_session, other (no version
    header). `operator` is the operator verifier's word; any word but `valid`
    names no operator. The ONE definition: count_socket counts with it and the
    future socket read gate (socket_connect_verdict) reports it."""
    if internal_ok:
        return "internal"
    if session_presented:
        return "session"
    if operator == "valid":
        return "operator:" + operator_name
    return "mod_no_session" if version_present else "other"


async def count_socket(ws) -> None:
    """Count one accepted chat socket by its connect-time credential class, in
    log and enforce. Inbound behaviour is unchanged; never raises."""
    try:
        mode = await current_mode()
        if mode not in ("log", "enforce"):
            return
        headers = ws.headers
        version_present = bool(headers.get("x-mod-version"))
        internal_ok = internal_key_valid(headers.get("x-internal-key"))
        session_presented = bool(headers.get("x-session-token"))
        verdict, payload, key_id = "absent", None, ""
        if not internal_ok and not session_presented:
            verdict, payload = await verify_operator_key(headers.get("x-operator-key"), ws)
            if verdict == "valid":
                key_id = _key_id(payload)
        cred = socket_census_class(internal_ok, session_presented, verdict,
                                   payload[2] if verdict == "valid" else "", version_present)
        client = getattr(ws, "client", None)
        census_add(SOCKET_TEMPLATE, "WEBSOCKET", cred, key_id, version_present, False,
              client.host if client else None, headers.get("user-agent"))
    except Exception as ex:
        _log_once("socket-count", f"[READ-GATE] socket count failed: {ex}")


# -- The chat socket's read-side protocol (specified; NOT wired) ----------------
#
# Requirement 26 / finding M4 (round 1) and M2 (round 2). This build COUNTS the
# socket (count_socket) and refuses nothing on it; the mode route refuses
# `enforce` while SOCKET_READ_GATE_BUILT is False. The complete protocol the
# socket read gate must implement before that constant may become True is ONE
# table, Section 0 (b2) of the build notes, held row by row as PROTOCOL in
# test_read_gate_socket_protocol.py; the functions below are that table as
# executable decisions. Nothing in the app calls them yet.
#
# 1. Order at connect: the version check, accept(), then the stage. A built
#    gate on a node whose stage is unknown closes 1013 read_gate_unavailable
#    BEFORE any credential lookup (socket_stage_refusal), so no valid
#    credential is admitted on it.
# 2. Credentials from the HANDSHAKE headers only (the message-borne `auth`
#    frame binds the inbound identity and is not a read credential):
#      X-Internal-Key  equal to API_SECRET_KEY (compared, no lookup) -> internal
#      X-Session-Token whose row exists, is verified, unexpired       -> session
#      X-Operator-Key  naming a live api_operator_keys row            -> operator
#    looked up through the HTTP gate's verifiers and caches; a cache miss is
#    charged to the per-address limiter first (_lookup_allowed) and a refused
#    charge is the word `limited`. Under enforce any one valid credential
#    admits.
# 3. Two separate results: the CENSUS CLASS (socket_census_class, five
#    values) and the REFUSAL DIAGNOSIS (stage_unknown, lookup_error,
#    lookup_limited, replication_pending, bad_session, bad_operator_key,
#    no_credential; None when admitted). A diagnosis is never a census class.
# 4. With nothing valid under enforce the diagnosis is the first of the order
#    above after stage_unknown; each has one close code and reason
#    (SOCKET_CLOSE).
# 5. Counting: not built, counted in log and enforce (count_socket); built,
#    counted in log, enforce and unknown (refused when closed), not in off.
# 6. Rechecks while open (built, enforce): every SOCKET_RECHECK_SECONDS (the
#    60 s revocation bound of the HTTP gate) and the stage every MODE_TTL --
#    see socket_recheck_verdict.

SOCKET_REFUSE_CODE = 4401
SOCKET_RETRY_CODE = 1013
SOCKET_RECHECK_SECONDS = CRED_TTL

# refusal diagnosis -> (close code, close reason)
SOCKET_CLOSE = {
    "stage_unknown": (SOCKET_RETRY_CODE, "read_gate_unavailable"),
    "lookup_error": (SOCKET_RETRY_CODE, "read_gate_unavailable"),
    "lookup_limited": (SOCKET_RETRY_CODE, "rate_limited"),
    "replication_pending": (SOCKET_RETRY_CODE, "session_replication_pending"),
    "bad_session": (SOCKET_REFUSE_CODE, "session_required"),
    "bad_operator_key": (SOCKET_REFUSE_CODE, "operator_key_invalid"),
    "no_credential": (SOCKET_REFUSE_CODE, "read_credential_required"),
}


# (admit, close_code, close_reason, census_class, counted, diagnosis)
SocketVerdict = namedtuple("SocketVerdict", ("admit", "close_code", "close_reason",
                                             "census_class", "counted", "diagnosis"))


def socket_enforcing(mode: str) -> bool:
    return mode == "enforce" and SOCKET_READ_GATE_BUILT is True


def socket_stage_refusal(mode: str):
    """Step 1, before any lookup: the refusal diagnosis `stage_unknown` when a
    BUILT gate's stage is unknown, else None."""
    if SOCKET_READ_GATE_BUILT is True and mode == UNKNOWN:
        return "stage_unknown"
    return None


def _socket_diagnosis(internal_ok, session, operator, replica) -> str | None:
    """Why nothing valid admits under enforce; None when a credential is valid."""
    if internal_ok or session == "valid" or operator == "valid":
        return None
    if session == "error" or operator == "error":
        return "lookup_error"
    if session == "limited" or operator == "limited":
        return "lookup_limited"
    if session == "miss" and replica:
        return "replication_pending"
    if session in ("bad", "miss"):
        return "bad_session"
    if operator == "bad":
        return "bad_operator_key"
    return "no_credential"


def socket_connect_verdict(mode: str, internal_ok: bool, session: str = "absent",
                           operator: str = "absent", operator_name: str = "",
                           replica: bool = False, version_present: bool = True) -> SocketVerdict:
    """The table of Section 0 (b2) for one handshake. `session` and `operator`
    are the verifiers' words (absent, bad, miss, error, limited, valid; a
    session `unchecked` = presented, not looked up); under a built gate whose
    stage is unknown none of them was looked up, so only the session's
    presence names a class there."""
    stage_refusal = socket_stage_refusal(mode)
    if stage_refusal is not None:
        census = socket_census_class(internal_ok, session != "absent", "absent", "",
                                     version_present)
        code, reason = SOCKET_CLOSE[stage_refusal]
        return SocketVerdict(False, code, reason, census, True, stage_refusal)
    census = socket_census_class(internal_ok, session != "absent", operator, operator_name,
                                 version_present)
    counted = mode in ("log", "enforce")
    if not socket_enforcing(mode):
        return SocketVerdict(True, None, None, census, counted, None)
    diagnosis = _socket_diagnosis(internal_ok, session, operator, replica)
    if diagnosis is None:
        return SocketVerdict(True, None, None, census, counted, None)
    code, reason = SOCKET_CLOSE[diagnosis]
    return SocketVerdict(False, code, reason, census, counted, diagnosis)


async def socket_connect_check(ws, mode: str) -> SocketVerdict:
    """The connect half of the protocol in its ORDER (not called by ws_chat
    while SOCKET_READ_GATE_BUILT is False): the stage first, and only then the
    handshake credentials through the HTTP gate's verifiers -- the session
    unless the internal key is valid, the operator key unless the session is."""
    headers = ws.headers
    version_present = bool(headers.get("x-mod-version"))
    internal_ok = internal_key_valid(headers.get("x-internal-key"))
    token = headers.get("x-session-token")
    if socket_stage_refusal(mode) is not None:
        return socket_connect_verdict(mode, internal_ok, "unchecked" if token else "absent",
                                      "absent", "", REPLICA_NODE, version_present)
    session, operator, name = "absent", "absent", ""
    if not internal_ok:
        session, _ = await verify_session(token, ws)
        if session != "valid":
            operator, payload = await verify_operator_key(headers.get("x-operator-key"), ws)
            name = payload[2] if operator == "valid" else ""
    return socket_connect_verdict(mode, internal_ok, session, operator, name, REPLICA_NODE,
                                  version_present)


def socket_recheck_verdict(mode: str, credential: str, now: float,
                           session_expires_at: float | None = None,
                           session_still_valid: bool = True,
                           operator_still_live: bool = True) -> tuple:
    """(keep, close_code, reason) for one open socket at one recheck."""
    if socket_stage_refusal(mode) is not None:
        return (False,) + SOCKET_CLOSE["stage_unknown"]
    if not socket_enforcing(mode):
        return True, None, None
    if credential == "internal":
        return True, None, None
    if credential == "session":
        if session_expires_at is not None and now >= session_expires_at:
            return False, SOCKET_REFUSE_CODE, "session_expired"
        if not session_still_valid:
            return False, SOCKET_REFUSE_CODE, "session_required"
        return True, None, None
    if credential.startswith("operator:"):
        if not operator_still_live:
            return False, SOCKET_REFUSE_CODE, "operator_key_invalid"
        return True, None, None
    return False, SOCKET_REFUSE_CODE, "read_credential_required"


def ungated_templates(routes) -> list[str]:
    """The GET templates of `routes` the gate never refuses for want of a read
    credential (published as `read_gate_open`)."""
    out = set()
    for r in routes:
        if isinstance(r, APIRoute) and "GET" in (r.methods or ()):
            if route_class(r.path) in UNGATED_CLASSES:
                out.add(r.path)
    return sorted(out)
