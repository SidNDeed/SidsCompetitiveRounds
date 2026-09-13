"""In-game mail, server half (Sept 6 batch, Group 4 item b; migration 297).

Style of test_h2h_summary.py: the handlers are EXECUTED against an in-memory
fake session that emulates every statement they issue — sessions, players,
mutes, bans, grants, the message and envelope tables, blocks, participant
sets, moderation cases, the outbox and the audit log — and REFUSES a
statement it does not recognise, so a query that drifts away from its
load-bearing predicates fails here instead of in production. The fan-out
fake additionally asserts the ONE INSERT ... SELECT still carries every
participant source (B-13) and never consults ranked_series.

The clock is frozen through main._utc_now (the seam the session gate and the
spam bucket day read). One test per rule in the item brief, each with a
negative control.
"""

import asyncio
import hashlib
import hmac
import inspect
import json
import math
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.sql.elements import TextClause

import main
import models

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.join(HERE, "..", "..", "plugin")
SQL_DIR = os.path.join(HERE, "..", "sql")

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
DAY = NOW.strftime("%Y-%m-%d")

A_SID, B_SID, C_SID, D_SID = ("76561198000000001", "76561198000000002",
                              "76561198000000003", "76561198000000004")
ADMIN_SID = "76561198000000009"
MOD_SID = "76561198000000008"

PLAY_SOURCES = ("matches", "team_matches", "ffa_match_players", "ovt_matches")
FANOUT_PREDICATES = ("FROM mail_blocks", "mail_from = 'nobody'", "mail_from = 'played'",
                     "FROM matches", "FROM team_matches", "FROM ffa_match_players",
                     "FROM ovt_matches", "unnest(")


# ── result shapes ─────────────────────────────────────────────────────────

def _first_value(row):
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


class _Scalars:
    def __init__(self, vals):
        self._vals = list(vals)

    def all(self):
        return list(self._vals)

    def first(self):
        return self._vals[0] if self._vals else None


class _Res:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)

    def fetchall(self):
        return list(self._rows)

    def scalar(self):
        return _first_value(self._rows[0]) if self._rows else None

    def scalar_one_or_none(self):
        return self.scalar()

    def scalars(self):
        return _Scalars(_first_value(r) for r in self._rows)


class _Savepoint:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


def _aware(dt):
    return dt if dt is None or dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ── the fake database ─────────────────────────────────────────────────────

class FakeDb:
    """In-memory emulation of every table the mail routes touch."""

    def __init__(self):
        self.sessions = {}
        self.players = {}
        self.admins = set()
        self.mod_grants = {}
        self.bans = {}
        self.recent_bans_by_admin = {}
        self.mutes = []
        self.bulk_grants = {}
        self.messages = {}
        self.recipients = {}
        self.blocks = set()
        self.played = set()
        self.cases = {}
        self.outbox = []
        self.censor_hits = []
        self.admin_actions = []
        self.added = []
        self.statements = []
        self.locks = []
        self.commits = 0
        self.message_created_at = NOW
        self.inbox_rev = {}                 # recipient_id -> rev (mail_inbox_rev, migration 300)
        self.on_identity_lock = None        # hook(sid) run when delete-account's identity lock is granted
        self.fail_outbox = False            # make the pending_channel_posts insert fail (review r1 M3)
        self.fail_admin_actions = False     # make the admin_actions insert fail (review r1 M10)
        self.commit_marks = []              # len(statements) at each commit: which statements were inside which transaction (review r2)
        self.purged_hashes = set()          # deleted_steam_ids: the deletion ledger delete_player_data writes with the scrub (review r3)

    # seeding -------------------------------------------------------------
    def add_player(self, sid, name=None, mod_seen=True, mail_from="everyone", deleted=False,
                   discord_id=None):
        pid = uuid.uuid4()
        self.players[pid] = {"id": pid, "steam_id": sid, "display_name": name or f"P{sid[-1]}",
                             "mod_seen_at": (NOW - timedelta(days=1)) if mod_seen is True else mod_seen,
                             "mail_from": mail_from,
                             "deleted_at": NOW if deleted else None, "discord_id": discord_id}
        return pid

    def add_session(self, token, sid, verified=True, expires_at=None):
        self.sessions[hashlib.sha256(token.encode()).hexdigest()] = {
            "steam_id": sid, "verified": verified,
            "expires_at": expires_at if expires_at is not None else NOW + timedelta(hours=1)}

    def player_by_sid(self, sid):
        for p in self.players.values():
            if p["steam_id"] == sid:
                return p
        return None

    def seed_message(self, sender_id, recipients, subject="Hello", body="body text", created_at=None,
                     kind="direct", key=None, read=False, deleted_by_sender_at=None, thread_id=None,
                     in_reply_to=None):
        mid = uuid.uuid4()
        self.messages[mid] = {"id": mid, "sender_id": sender_id, "kind": kind,
                              "thread_id": thread_id or mid, "in_reply_to": in_reply_to,
                              "subject": subject, "body": body, "idempotency_key": key or uuid.uuid4(),
                              "created_at": created_at or NOW,
                              "deleted_by_sender_at": deleted_by_sender_at}
        for rid, rkind, delivery in recipients:
            self.recipients[(mid, rid)] = {"kind": rkind, "delivery": delivery,
                                           "read_at": NOW if read else None, "deleted_at": None}
        return mid

    def scrub(self, sid):
        """delete_player_data's scrub for the tables the identity routes
        write — the shape of a deletion that COMMITTED while a route waited
        for the lock: the players row keeps its id but its steam_id becomes
        the tombstone, and every raw copy in the audit and moderation
        columns is rewritten to it (main.delete_player_data, table by name).
        Returns the tombstone."""
        p = self.player_by_sid(sid)
        if p is None:
            return None
        tomb = f"deleted_{uuid.uuid4().hex[:8]}"
        p.update({"steam_id": tomb, "display_name": "[Deleted User]", "discord_id": None, "deleted_at": NOW})
        for a in self.admin_actions:
            for k in ("admin", "target"):
                if a[k] == sid:
                    a[k] = tomb
        for c in self.cases.values():
            if c["resolved_by"] == sid:
                c["resolved_by"] = tomb
        for mu in self.mutes:
            if mu["steam_id"] == sid:
                mu["steam_id"], mu["revoked_at"] = tomb, mu["revoked_at"] or NOW
            if mu.get("by") == sid:
                mu["by"] = tomb
        self.bulk_grants.pop(sid, None)
        self.sessions = {k: v for k, v in self.sessions.items() if v["steam_id"] != sid}
        self.purged_hashes.add(main._hash_steam_id(sid))   # the ledger row, same transaction as the scrub
        return tomb

    # session protocol ----------------------------------------------------
    def begin_nested(self):
        return _Savepoint()

    async def commit(self):
        self.commits += 1
        self.commit_marks.append(len(self.statements))

    async def rollback(self):
        pass

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, statement, params=None):
        if isinstance(statement, TextClause):
            sql, params = str(statement), dict(params or {})
        else:
            sql, params = str(statement), dict(statement.compile().params)
        self.statements.append(sql)
        self._asyncpg_codec_check(sql, params)
        return self._dispatch(sql, params)

    @staticmethod
    def _asyncpg_codec_check(sql, params):
        """asyncpg picks the codec from the bind's SQL type: a parameter cast
        straight to text (`CAST(:p AS text)`) goes through the str codec, which
        refuses a uuid.UUID with "expected str, got UUID" (#275 class; review
        r1 HIGH 1). The same refusal here, so a bind that would fail on
        production asyncpg fails in this suite instead of passing silently."""
        for m in re.finditer(r"CAST\(:(\w+) AS text\)", sql):
            if isinstance(params.get(m.group(1)), uuid.UUID):
                raise TypeError(f"invalid input for query argument :{m.group(1)} (expected str, got UUID)")

    # emulation -----------------------------------------------------------
    def _visible_to(self, mid, me):
        env = self.recipients.get((mid, me))
        return env is not None and env["delivery"] == "delivered" and env["deleted_at"] is None

    def _played_together(self, a, b):
        return any(pair == frozenset({a, b}) and src in PLAY_SOURCES for pair, src in self.played)

    def _delivery_for(self, sender_id, rid):
        p = self.players[rid]
        if (rid, sender_id) in self.blocks:
            return "suppressed"
        if p["mail_from"] == "nobody":
            return "suppressed"
        if p["mail_from"] == "played" and not self._played_together(sender_id, rid):
            return "suppressed"
        return "delivered"

    def _sender_row(self, p):
        return {"sender_steam_id": p["steam_id"], "sender_name": p["display_name"],
                "sender_pid": str(p["id"]), "rating": 1500, "title": None, "title_color": None,
                "title_sku": None}

    def _dispatch(self, sql, params):  # noqa: C901 — one branch per emulated statement
        # sessions
        if "SELECT steam_id FROM steam_sessions WHERE token_hash = :th" in sql:
            row = self.sessions.get(params["th"])
            return _Res([{"steam_id": row["steam_id"]}] if row else [])
        if "SELECT steam_id, verified, expires_at FROM steam_sessions" in sql:
            row = self.sessions.get(params["th"])
            return _Res([row] if row else [])
        # player lookups
        if "SELECT id, steam_id, display_name, mod_seen_at, mail_from" in sql:
            p = self.player_by_sid(params["sid"])
            if p is None or p["deleted_at"] is not None:
                return _Res([])
            return _Res([{k: p[k] for k in ("id", "steam_id", "display_name", "mod_seen_at", "mail_from")}])
        if "SELECT id, steam_id FROM players" in sql and "= ANY(" in sql:
            return _Res([{"id": p["id"], "steam_id": p["steam_id"]} for p in self.players.values()
                         if p["steam_id"] in set(params["sids"]) and p["deleted_at"] is None])
        if sql.lstrip().startswith("SELECT id FROM players WHERE steam_id = :sid AND deleted_at IS NULL"):
            p = self.player_by_sid(params["sid"])
            return _Res([(p["id"],)] if p and p["deleted_at"] is None else [])
        if sql.lstrip().startswith("SELECT id FROM players WHERE steam_id = :sid"):
            p = self.player_by_sid(params["sid"])
            return _Res([(p["id"],)] if p else [])
        if "SELECT steam_id FROM players WHERE discord_id = :d" in sql:
            hits = [p for p in self.players.values()
                    if p["discord_id"] == params["d"] and p["deleted_at"] is None]
            return _Res([(hits[0]["steam_id"],)] if hits else [])
        if "UPDATE players SET mail_from" in sql:
            self.players[params["me"]]["mail_from"] = params["v"]
            return _Res()
        # the deletion ledger (review r3)
        if "FROM deleted_steam_ids" in sql:
            if "= ANY(" in sql:
                return _Res([(h,) for h in params["hashes"] if h in self.purged_hashes])
            return _Res([(1,)] if params["h"] in self.purged_hashes else [])
        # locks
        if "pg_advisory_xact_lock(hashtext('mail:'" in sql:
            self.locks.append(("mail", params["sid"]))
            return _Res([(1,)])
        if "pg_advisory_xact_lock(hashtext('ban-rate:'" in sql:
            self.locks.append(("ban-rate", params["adm"]))
            return _Res([(1,)])
        if "pg_advisory_xact_lock(hashtext(:sid))" in sql:
            self.locks.append(("identity", params["sid"]))
            if self.on_identity_lock is not None:
                self.on_identity_lock(params["sid"])        # "a deletion committed while we waited for this lock"
            return _Res([(1,)])
        if "FROM players WHERE id = :pid FOR NO KEY UPDATE" in sql:
            p = self.players.get(params["pid"])             # the lattice re-read: by id, so a scrubbed row is FOUND, tombstone and all
            return _Res([{k: p[k] for k in ("id", "steam_id", "deleted_at")}] if p else [])
        # gates
        if "SELECT reason FROM player_bans" in sql:
            r = self.bans.get(params["sid"])
            return _Res([(r,)] if r is not None else [])
        if "FROM chat_mutes" in sql and sql.lstrip().startswith("SELECT 1"):
            wants_chan = ":chan" in sql
            for mu in self.mutes:
                if mu["steam_id"] != params["sid"] or mu["revoked_at"] is not None:
                    continue
                if mu["expires_at"] is not None and mu["expires_at"] <= NOW:
                    continue
                if mu["channel"] is None or (wants_chan and mu["channel"] == params.get("chan")):
                    return _Res([(1,)])
            return _Res([])
        if "UPDATE chat_mutes SET revoked_at" in sql:
            for mu in self.mutes:
                if mu["steam_id"] == params["sid"] and mu["revoked_at"] is None and mu["channel"] == params["chan"]:
                    mu["revoked_at"] = NOW
            return _Res()
        if "INSERT INTO chat_mutes" in sql:
            mins = int(params["mins"])
            self.mutes.append({"steam_id": params["sid"], "channel": params["chan"], "revoked_at": None,
                               "expires_at": (NOW + timedelta(minutes=mins)) if mins > 0 else None,
                               "by": params["by"], "reason": params["why"], "minutes": mins})
            return _Res()
        if "FROM admin_users" in sql:
            sid = params.get("steam_id_1")
            return _Res([(sid,)] if sid in self.admins else [])
        if "FROM language_grants" in sql:
            return _Res([(c,) for c in self.mod_grants.get(params["sid"], [])])
        # grants
        if "SELECT max_recipients FROM mail_bulk_grants" in sql:
            g = self.bulk_grants.get(params["sid"])
            return _Res([(g[0],)] if g and g[1] > NOW else [])
        if "INSERT INTO mail_bulk_grants" in sql:
            exp = NOW + timedelta(days=int(params["d"]))
            self.bulk_grants[params["sid"]] = (int(params["n"]), exp)
            return _Res([(exp,)])
        if "DELETE FROM mail_bulk_grants" in sql:
            gone = self.bulk_grants.pop(params["sid"], None)
            return _Res([(1,)] if gone else [])
        # censor ledger
        if "INSERT INTO mail_censor_hits" in sql:
            self.censor_hits.append({"sender_id": params["sid"], "created_at": NOW})
            return _Res()
        # spam evaluation (before the bare censor count: it embeds the same text).
        # The same-body key is computed on the Python side ONLY (review r1 M7):
        # the sender's day of bodies is read and compared by main, so the SQL
        # must carry no normaliser of its own to drift from it.
        if sql.lstrip().startswith("SELECT body FROM mail_messages"):
            assert "kind = 'direct'" in sql and "make_interval(days => 1)" in sql
            return _Res([(m["body"],) for m in self.messages.values()
                         if m["sender_id"] == params["sid"] and m["kind"] == "direct"
                         and m["created_at"] > NOW - timedelta(days=1)])
        if "AS bulk_hour" in sql:
            for needle in ("HAVING COUNT(DISTINCT r.recipient_id) > CAST(:bulk_n AS integer)",
                           "make_interval(hours => 1)", "make_interval(days => 1)"):
                assert needle in sql, f"spam query lost: {needle}"
            for stale in ("same_body", "lower(body)", "regexp_replace", ":norm"):
                assert stale not in sql, f"spam query grew its own normaliser again: {stale}"
            sid = params["sid"]
            mine = [m for m in self.messages.values() if m["sender_id"] == sid and m["kind"] == "direct"
                    and m["created_at"] > NOW - timedelta(days=1)]
            bulk = 0
            for m in mine:
                if m["created_at"] <= NOW - timedelta(hours=1):
                    continue
                n = len({rid for (mid, rid) in self.recipients if mid == m["id"]})
                if n > int(params["bulk_n"]):
                    bulk += 1
            hits = sum(1 for h in self.censor_hits if h["sender_id"] == sid
                       and h["created_at"] > NOW - timedelta(days=1))
            return _Res([{"bulk_hour": bulk, "censor_hits": hits}])
        if "SELECT COUNT(*) FROM mail_censor_hits" in sql:
            return _Res([(sum(1 for h in self.censor_hits if h["sender_id"] == params["sid"]
                              and h["created_at"] > NOW - timedelta(days=1)),)])
        # idempotency + rate
        if "FROM mail_messages WHERE sender_id = :sid AND idempotency_key = :key" in sql:
            hit = [m for m in self.messages.values()
                   if m["sender_id"] == params["sid"] and m["idempotency_key"] == params["key"]]
            return _Res([{"id": hit[0]["id"], "kind": hit[0]["kind"],
                          "recipient_count": hit[0].get("recipient_count")}] if hit else [])
        if "AS per_minute" in sql:
            assert "kind = 'direct'" in sql, "rate window must ignore broadcasts"
            # review r1 M12: the waits are the time until the OLDEST send in
            # each window leaves it, computed against the same NOW() as the counts
            for needle in ("MIN(created_at) FILTER (WHERE created_at > NOW() - make_interval(mins => 1))",
                           "AS minute_wait", "MIN(created_at) + make_interval(days => 1) - NOW()", "AS day_wait"):
                assert needle in sql, f"rate query lost: {needle}"
            mine = [m for m in self.messages.values() if m["sender_id"] == params["sid"]
                    and m["kind"] == "direct" and m["created_at"] > NOW - timedelta(days=1)]
            minute = [m for m in mine if m["created_at"] > NOW - timedelta(minutes=1)]

            # the rounding of each wait is READ OFF ITS OWN SQL expression
            # (review r2 M12 pin): CEIL there rounds up here; a FLOOR there
            # floors here, exactly as PostgreSQL would
            def rounder(seg):
                if "CEIL(EXTRACT" in seg:
                    return math.ceil
                assert "FLOOR(EXTRACT" in seg, "rate query lost its rounding"
                return math.floor
            round_minute = rounder(sql[sql.index("AS per_day,"):sql.index("AS minute_wait")])
            round_day = rounder(sql[sql.index("AS minute_wait"):sql.index("AS day_wait")])

            def wait(rows, span, rnd):
                if not rows:
                    return None
                return rnd((min(m["created_at"] for m in rows) + span - NOW).total_seconds())
            return _Res([{"per_minute": len(minute), "per_day": len(mine),
                          "minute_wait": wait(minute, timedelta(minutes=1), round_minute),
                          "day_wait": wait(mine, timedelta(days=1), round_day)}])
        # message insert + fan-out
        if "INSERT INTO mail_messages" in sql:
            kind = "system_broadcast" if "'system_broadcast'" in sql else "direct"
            mid = params["id"]
            assert mid not in self.messages
            self.messages[mid] = {"id": mid, "sender_id": params["sid"], "kind": kind,
                                  "thread_id": params.get("tid", mid) if kind == "direct" else mid,
                                  "in_reply_to": params.get("irt"), "subject": params["subj"],
                                  "body": params["body"], "idempotency_key": params["key"],
                                  "created_at": self.message_created_at, "deleted_by_sender_at": None,
                                  "recipient_count": None}
            return _Res()
        if "UPDATE mail_messages SET recipient_count" in sql:
            self.messages[params["mid"]]["recipient_count"] = int(params["n"])
            return _Res()
        if "INSERT INTO mail_recipients" in sql and "unnest(" in sql:
            for needle in FANOUT_PREDICATES:
                assert needle in sql, f"fan-out lost predicate: {needle}"
            assert "ranked_series" not in sql, "ranked_series is not proof of play (B-13)"
            assert "INSERT INTO mail_recipients" in sql and sql.count("INSERT INTO") == 1
            assert "FOR KEY SHARE OF p" in sql, "the fan-out must hold each recipient's players row (the delete-account lattice)"
            for rid, kind in zip(params["rids"], params["kinds"]):
                p = self.players.get(rid)
                if p is None or p["deleted_at"] is not None:
                    continue
                self.recipients[(params["mid"], rid)] = {
                    "kind": kind, "delivery": self._delivery_for(params["sid"], rid),
                    "read_at": None, "deleted_at": None}
            return _Res()
        if "INSERT INTO mail_recipients" in sql and "'to', 'delivered'" in sql:
            assert "mod_seen_at > NOW() - make_interval(days => CAST(:days AS integer))" in sql
            assert "mail_blocks" not in sql and "mail_from" not in sql, "broadcast bypasses preferences"
            assert "FOR KEY SHARE OF p" in sql, "the broadcast fan-out holds the recipients' players rows too"
            out = []
            for p in self.players.values():
                if p["deleted_at"] is not None or p["id"] == params["sid"]:
                    continue
                seen = p["mod_seen_at"]
                if seen is None or _aware(seen) <= NOW - timedelta(days=int(params["days"])):
                    continue
                self.recipients[(params["mid"], p["id"])] = {"kind": "to", "delivery": "delivered",
                                                             "read_at": None, "deleted_at": None}
                out.append((1,))
            return _Res(out)
        # moderation cases
        if "INSERT INTO moderation_cases" in sql:
            key = (params["kind"], params["bucket"])
            existing = [c for c in self.cases.values() if (c["kind"], c["bucket_key"]) == key]
            if existing:
                c = existing[0]
                if "DO UPDATE" in sql:
                    ev = dict(c["evidence"])
                    ev.update(json.loads(params["ev"]))
                    ev["hits"] = int(c["evidence"].get("hits", 1)) + 1
                    c["evidence"] = ev
                    if params["mid"] is not None:
                        c["message_id"] = params["mid"]
                    return _Res([{"id": c["id"], "inserted": False}])
                return _Res([])
            cid = uuid.uuid4()
            self.cases[cid] = {"id": cid, "kind": params["kind"], "subject_player_id": params["subj"],
                               "reporter_id": params["rep"], "message_id": params["mid"],
                               "evidence": json.loads(params["ev"]), "bucket_key": params["bucket"],
                               "status": "open", "created_at": NOW, "resolved_at": None,
                               "resolved_by": None, "resolution": None, "notified_at": None}
            return _Res([{"id": cid, "inserted": True}])
        if "SELECT id FROM moderation_cases WHERE kind = :kind AND bucket_key" in sql:
            hit = [c for c in self.cases.values()
                   if (c["kind"], c["bucket_key"]) == (params["kind"], params["bucket"])]
            return _Res([(hit[0]["id"],)] if hit else [])
        if sql.lstrip().startswith("SELECT p.id AS subject_id, p.steam_id AS subject_sid"):
            c = self.cases.get(params["id"])                          # the unlocked subject pre-read (deleted rows included)
            if c is None:
                return _Res([])
            p = self.players[c["subject_player_id"]]
            return _Res([{"subject_id": p["id"], "subject_sid": p["steam_id"]}])
        if "FROM moderation_cases c JOIN players p" in sql and "FOR NO KEY UPDATE OF c" in sql:
            c = self.cases.get(params["id"])
            if c is None:
                return _Res([])
            p = self.players[c["subject_player_id"]]
            row = dict(c)
            row.update({"subject_steam_id": p["steam_id"], "subject_name": p["display_name"]})
            return _Res([row])
        if "FROM moderation_cases c" in sql and "WHERE c.status = :st" in sql:
            out = []
            for c in sorted(self.cases.values(), key=lambda c: c["created_at"], reverse=True):
                if c["status"] != params["st"]:
                    continue
                p = self.players[c["subject_player_id"]]
                rp = self.players.get(c["reporter_id"]) if c["reporter_id"] else None
                row = dict(c)
                row.update({"subject_steam_id": p["steam_id"], "subject_name": p["display_name"],
                            "reporter_steam_id": rp["steam_id"] if rp else None})
                out.append(row)
            return _Res(out[: int(params["lim"])])
        if "UPDATE moderation_cases" in sql and "SET notified_at" in sql:
            c = self.cases.get(params["id"])
            if c is None:
                return _Res([])
            c["notified_at"] = c["notified_at"] or NOW
            return _Res([(c["notified_at"],)])
        if "UPDATE moderation_cases" in sql and "SET status = :st" in sql:
            c = self.cases[params["id"]]
            c.update({"status": params["st"], "resolved_at": NOW, "resolved_by": params["by"],
                      "resolution": params["res"]})
            return _Res()
        if "INSERT INTO pending_channel_posts" in sql:
            if self.fail_outbox:
                raise RuntimeError("outbox insert refused (test)")
            self.outbox.append((params["ch"], params["c"]))
            return _Res()
        if "INSERT INTO admin_actions" in sql:
            if self.fail_admin_actions:
                raise RuntimeError("admin_actions insert refused (test)")
            self.admin_actions.append({"admin": params["a"], "action": params["act"],
                                       "target": params["t"], "details": json.loads(params["d"])})
            return _Res()
        # ban core statements (no-ops here)
        if sql.lstrip().startswith("DELETE FROM steam_sessions") or "DELETE FROM i18n_portal_sessions" in sql:
            return _Res()
        if any(f"DELETE FROM {t} WHERE player_id = :pid" in sql
               for t in ("ranked_queue", "team_queue", "ovt_queue", "ffa_queue")):
            return _Res()
        if "SELECT COUNT(*) FROM player_bans" in sql:
            return _Res([(self.recent_bans_by_admin.get(params["adm"], 0),)])
        if "SELECT COUNT(*) FROM admin_actions" in sql:
            return _Res([(0,)])
        # reads: reply original, detail, report, sent, inbox, status
        if "SELECT m.id, m.sender_id, m.kind, m.thread_id, m.subject" in sql:
            # the reply original: authorisation READ OFF the SQL (review r1 M18)
            m = self.messages.get(params["mid"])
            if m is None:
                return _Res([])
            sender_clause = "(m.sender_id = :me AND m.deleted_by_sender_at IS NULL)" in sql
            exists_clause = "EXISTS (SELECT 1 FROM mail_recipients r" in sql
            exists_visible = "r.delivery = 'delivered' AND r.deleted_at IS NULL" in sql
            env = self.recipients.get((m["id"], params["me"]))
            as_sender = m["sender_id"] == params["me"] and m["deleted_by_sender_at"] is None
            as_party = env is not None and (not exists_visible or self._visible_to(m["id"], params["me"]))
            if (sender_clause or exists_clause) and not ((sender_clause and as_sender) or (exists_clause and as_party)):
                return _Res([])
            return _Res([m])
        if "SELECT recipient_id, kind FROM mail_recipients" in sql:
            assert "delivery = 'delivered'" in sql, "reply-all must derive from DELIVERED envelopes"
            return _Res([{"recipient_id": rid, "kind": env["kind"]} for (mid, rid), env in self.recipients.items()
                         if mid == params["mid"] and env["delivery"] == "delivered"])
        if "LEFT JOIN mail_recipients r ON r.message_id = m.id AND r.recipient_id = :me" in sql:
            # the detail read (review r1 M18): every predicate is READ OFF the
            # production SQL, never assumed — drop one there and this fake stops
            # enforcing it, exactly as PostgreSQL would.
            m = self.messages.get(params["mid"])
            if m is None:
                return _Res([])
            env = self.recipients.get((m["id"], params["me"]))
            join_pred = "AND r.delivery = 'delivered' AND r.deleted_at IS NULL" in sql
            joined = env if (env and (not join_pred or (env["delivery"] == "delivered" and env["deleted_at"] is None))) else None
            need_env = "r.recipient_id IS NOT NULL" in sql
            sender_clause = "(m.sender_id = :me AND m.deleted_by_sender_at IS NULL)" in sql
            as_sender = m["sender_id"] == params["me"] and m["deleted_by_sender_at"] is None
            if (need_env or sender_clause) and not ((need_env and joined is not None) or (sender_clause and as_sender)):
                return _Res([])
            row = dict(m)
            row.update(self._sender_row(self.players[m["sender_id"]]))
            row["read_at"] = joined["read_at"] if joined else None
            return _Res([row])
        if "JOIN mail_recipients r ON r.message_id = m.id AND r.recipient_id = :me" in sql \
                and "s.display_name AS sender_name" in sql:
            # the report read: the delivered filter is taken from the SQL (M18)
            m = self.messages.get(params["mid"])
            env = self.recipients.get((params["mid"], params["me"])) if m else None
            delivered_only = "r.delivery = 'delivered'" in sql
            if m is None or env is None or (delivered_only and env["delivery"] != "delivered"):
                return _Res([])
            row = dict(m)
            row.update(self._sender_row(self.players[m["sender_id"]]))
            return _Res([row])
        if "FROM mail_recipients r" in sql and "JOIN mail_messages m ON m.id = r.message_id" in sql \
                and "JOIN players s ON s.id = m.sender_id" in sql:
            # the inbox page (review r1 M19): both envelope filters come from the SQL
            delivered_only = "r.delivery = 'delivered'" in sql
            undeleted_only = "r.deleted_at IS NULL" in sql
            rows = []
            for (mid, rid), env in self.recipients.items():
                if rid != params["me"]:
                    continue
                if (delivered_only and env["delivery"] != "delivered") or (undeleted_only and env["deleted_at"] is not None):
                    continue
                m = self.messages[mid]
                if params.get("c_at") is not None and not (
                        (m["created_at"], m["id"]) < (params["c_at"], params["c_id"])):
                    continue
                row = dict(m)
                row["read_at"] = env["read_at"]
                row.update(self._sender_row(self.players[m["sender_id"]]))
                rows.append(row)
            rows.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
            return _Res(rows[: int(params["lim"])])
        if "FROM mail_messages m" in sql and "WHERE m.sender_id = :me AND m.deleted_by_sender_at IS NULL" in sql:
            rows = [dict(m) for m in self.messages.values()
                    if m["sender_id"] == params["me"] and m["deleted_by_sender_at"] is None
                    and (params.get("c_at") is None or (m["created_at"], m["id"]) < (params["c_at"], params["c_id"]))]
            rows.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
            return _Res(rows[: int(params["lim"])])
        if "WITH a AS (" in sql and "ROW_NUMBER() OVER (PARTITION BY r.message_id" in sql:
            assert "r.delivery" not in sql, "addressee lists must not expose delivery"
            out = []
            for mid in params["mids"]:
                envs = [(rid, env) for (m, rid), env in self.recipients.items() if m == mid]
                envs.sort(key=lambda e: (0 if e[1]["kind"] == "to" else 1,
                                         self.players[e[0]]["display_name"]))
                for rid, env in envs[: int(params["cap"])]:
                    p = self.players[rid]
                    out.append({"message_id": mid, "kind": env["kind"], "steam_id": p["steam_id"],
                                "display_name": p["display_name"]})
            return _Res(out)
        # the inbox revision counter (migration 300; review r1 M4): a row-locked
        # DB delta per delivered envelope, visited in recipient order
        if "INSERT INTO mail_inbox_rev" in sql:
            assert "ON CONFLICT (recipient_id) DO UPDATE" in sql and "SET rev = mail_inbox_rev.rev + 1" in sql, \
                "the revision must be a DB delta (#326), never an absolute write"
            assert "r.delivery = 'delivered'" in sql and "ORDER BY r.recipient_id" in sql
            for (mid, rid), env in sorted(self.recipients.items(), key=lambda kv: str(kv[0][1])):
                if mid == params["mid"] and env["delivery"] == "delivered":
                    self.inbox_rev[rid] = self.inbox_rev.get(rid, 0) + 1
            return _Res()
        if "SELECT COUNT(*) FROM mail_recipients" in sql and "message_id = CAST(:mid AS uuid)" in sql:
            return _Res([(sum(1 for (mid, _rid), env in self.recipients.items()
                              if mid == params["mid"] and env["delivery"] == "delivered"),)])
        if "AS unread" in sql and "AS revision" in sql:
            assert "read_at IS NULL AND deleted_at IS NULL" in sql
            assert "FROM mail_inbox_rev" in sql, "revision must be the delivery counter (migration 300)"
            delivered_only = "delivery = 'delivered'" in sql            # review r1 M19: from the SQL
            mine = [env for (mid, rid), env in self.recipients.items()
                    if rid == params["me"] and (not delivered_only or env["delivery"] == "delivered")]
            unread = sum(1 for env in mine if env["read_at"] is None and env["deleted_at"] is None)
            return _Res([{"unread": unread, "revision": self.inbox_rev.get(params["me"])}])
        # writes: read, delete
        if "UPDATE mail_recipients SET read_at" in sql:
            env = self.recipients.get((params["mid"], params["me"]))
            if env is None or env["delivery"] != "delivered" or env["deleted_at"] is not None:
                return _Res([])
            env["read_at"] = env["read_at"] or NOW
            return _Res([(env["read_at"],)])
        if "UPDATE mail_recipients SET deleted_at = COALESCE" in sql:
            env = self.recipients.get((params["mid"], params["me"]))
            if env is None or env["delivery"] != "delivered":
                return _Res([])
            env["deleted_at"] = env["deleted_at"] or NOW
            return _Res([(1,)])
        if "UPDATE mail_messages SET deleted_by_sender_at" in sql:
            m = self.messages.get(params["mid"])
            if m is None or m["sender_id"] != params["me"]:
                return _Res([])
            m["deleted_by_sender_at"] = m["deleted_by_sender_at"] or NOW
            return _Res([(1,)])
        # blocks
        if "FROM mail_blocks b JOIN players p" in sql:
            rows = [{"steam_id": self.players[b]["steam_id"], "display_name": self.players[b]["display_name"],
                     "created_at": NOW} for (a, b) in self.blocks if a == params["me"]]
            return _Res(rows[: int(params["lim"])])
        if "SELECT COUNT(*) FROM mail_blocks" in sql:
            return _Res([(sum(1 for a, _b in self.blocks if a == params["me"]),)])
        if "INSERT INTO mail_blocks" in sql:
            self.blocks.add((params["me"], params["t"]))
            return _Res()
        if "DELETE FROM mail_blocks" in sql:
            p = self.player_by_sid(params["sid"])
            if p:
                self.blocks.discard((params["me"], p["id"]))
            return _Res()
        # janitor
        if "UPDATE mail_recipients SET deleted_at = NOW()" in sql:
            n = 0
            for (mid, _rid), env in self.recipients.items():
                m = self.messages[mid]
                if env["read_at"] is not None and env["deleted_at"] is None \
                        and m["created_at"] < NOW - timedelta(days=int(params["days"])):
                    env["deleted_at"] = NOW
                    n += 1
            return _Res([(1,)] * n)
        if "DELETE FROM mail_messages" in sql:
            gone = []
            for mid, m in list(self.messages.items()):
                live = any(env["delivery"] == "delivered" and env["deleted_at"] is None
                           for (mm, _r), env in self.recipients.items() if mm == mid)
                if not live and (m["deleted_by_sender_at"] is not None
                                 or m["created_at"] < NOW - timedelta(days=int(params["days"]))):
                    gone.append(mid)
            for mid in gone:
                self.messages.pop(mid)
                for k in [k for k in self.recipients if k[0] == mid]:
                    self.recipients.pop(k)
                for c in self.cases.values():
                    if c["message_id"] == mid:
                        c["message_id"] = None
            return _Res([(1,)] * len(gone))
        if "DELETE FROM mail_censor_hits" in sql:
            keep = [h for h in self.censor_hits if h["created_at"] >= NOW - timedelta(days=int(params["days"]))]
            n = len(self.censor_hits) - len(keep)
            self.censor_hits = keep
            return _Res([(1,)] * n)
        if "FROM rank_role_colors" in sql:
            return _Res([])
        # the ban core withdraws the Player Cards binder and announcements (c3 J)
        if "UPDATE players SET pc_collection_public = false, pc_announce = false, pc_settings_revision" in sql:
            return _Res()
        # ...and revokes any delivery lease of the banned subject, so a face
        # send already acquired cannot post their picture after the ban
        if "DELETE FROM pc_delivery_leases WHERE subject_id IN" in sql:
            return _Res()
        # ...and first WAITS for any Discord line in flight naming the player (r7 H2): none here
        if "MAX(l.until) - clock_timestamp()" in sql:
            return _Res()
        raise AssertionError(f"unexpected statement: {sql[:120]}")


# ── fixtures and helpers ──────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch):
    monkeypatch.setattr(main, "_utc_now", lambda: NOW)


def _req(token="tokA"):
    return SimpleNamespace(headers={"X-Session-Token": token} if token else {})


def _run(coro):
    return asyncio.run(coro)


def _raises(coro):
    with pytest.raises(HTTPException) as info:
        _run(coro)
    return info.value


def _world():
    """Four players (A, B, C, D), A and B with sessions; A has run the mod."""
    db = FakeDb()
    ids = {sid: db.add_player(sid) for sid in (A_SID, B_SID, C_SID, D_SID)}
    db.add_session("tokA", A_SID)
    db.add_session("tokB", B_SID)
    return db, ids


def _send(db, to, cc=(), subject="Hi there", body="A perfectly ordinary body.", key=None, token="tokA"):
    req = main._MailSendReq(to=list(to), cc=list(cc), subject=subject, body=body,
                            idempotency_key=key or str(uuid.uuid4()))
    return _run(main.mail_send(req, _req(token), db))


def _send_raises(db, **kw):
    with pytest.raises(HTTPException) as info:
        _send(db, **kw)
    return info.value


def _inbox(db, token="tokB", cursor="", limit=25):
    return _run(main.mail_inbox(_req(token), cursor, limit, db))


def _status(db, token="tokB"):
    return _run(main.mail_status(_req(token), db))


def _env(db, mid, rid):
    return db.recipients[(UUID(mid), rid)]


# ── caller resolution / gates ─────────────────────────────────────────────

def test_caller_requires_a_verified_session_named_by_the_token():
    db, ids = _world()
    assert _status(db, "tokB")["unread"] == 0                       # positive control
    for token in (None, "unknown"):
        assert _raises(main.mail_status(_req(token), db)).detail == "session_required"
    db.add_session("tokU", C_SID, verified=False)
    assert _raises(main.mail_status(_req("tokU"), db)).status_code == 401
    db.add_session("tokE", C_SID, expires_at=NOW - timedelta(seconds=1))
    assert _raises(main.mail_status(_req("tokE"), db)).detail == "session_required"
    db.add_session("tokDel", D_SID)
    db.players[ids[D_SID]]["deleted_at"] = NOW
    assert _raises(main.mail_status(_req("tokDel"), db)).status_code == 401


def test_sender_gates_mod_seen_ban_and_global_mute_only():
    db, ids = _world()
    assert _send(db, [B_SID])["accepted"] is True                   # positive control
    db.players[ids[A_SID]]["mod_seen_at"] = None
    assert _send_raises(db, to=[B_SID]).detail == "mod_required"
    db.players[ids[A_SID]]["mod_seen_at"] = NOW
    db.bans[A_SID] = ""                                              # an empty reason is still a ban
    assert _send_raises(db, to=[B_SID]).detail == "banned"
    del db.bans[A_SID]
    # B-5: a channel-scoped mute does not touch mail; a global one refuses.
    db.mutes.append({"steam_id": A_SID, "channel": "ru", "revoked_at": None, "expires_at": None})
    assert _send(db, [B_SID])["accepted"] is True
    db.mutes.append({"steam_id": A_SID, "channel": None, "revoked_at": None, "expires_at": None})
    assert _send_raises(db, to=[B_SID]).detail == "muted"
    db.mutes[-1]["revoked_at"] = NOW
    assert _send(db, [B_SID])["accepted"] is True
    db.mutes.append({"steam_id": A_SID, "channel": None, "revoked_at": None,
                     "expires_at": NOW - timedelta(minutes=1)})
    assert _send(db, [B_SID])["accepted"] is True
    mute_sql = [s for s in db.statements if "FROM chat_mutes" in s and s.lstrip().startswith("SELECT 1")]
    assert mute_sql and all("channel IS NULL" in s and ":chan" not in s for s in mute_sql)


# ── send, suppression, inbox ──────────────────────────────────────────────

def test_send_delivers_and_inbox_lists_it():
    db, ids = _world()
    res = _send(db, [B_SID], cc=[C_SID], subject="Sub", body="Body")
    assert res["accepted"] is True and UUID(res["id"])
    assert _env(db, res["id"], ids[B_SID]) == {"kind": "to", "delivery": "delivered", "read_at": None, "deleted_at": None}
    assert _env(db, res["id"], ids[C_SID])["kind"] == "cc"
    m = db.messages[UUID(res["id"])]
    assert m["thread_id"] == m["id"] and m["in_reply_to"] is None and m["kind"] == "direct"
    page = _inbox(db, "tokB")
    assert [x["id"] for x in page["messages"]] == [res["id"]]
    row = page["messages"][0]
    assert row["sender"] == {"steam_id": A_SID, "name": "P1", "title_color": ""}
    assert row["subject"] == "Sub" and row["read_at"] is None and row["kind"] == "direct"
    assert page["next_cursor"] is None
    assert db.commits == 1


@pytest.mark.parametrize("setup", ["block", "nobody", "played_no_history"])
def test_suppression_is_silent_and_never_listed(setup):
    db, ids = _world()
    control = _send(db, [B_SID])                                     # negative control: delivered
    if setup == "block":
        db.blocks.add((ids[B_SID], ids[A_SID]))
    elif setup == "nobody":
        db.players[ids[B_SID]]["mail_from"] = "nobody"
    else:
        db.players[ids[B_SID]]["mail_from"] = "played"
        db.played.add((frozenset({ids[A_SID], ids[B_SID]}), "ranked_series"))   # B-13: not proof
    res = _send(db, [B_SID])
    # L1: exact, non-disclosing values on BOTH answers — not a key-set comparison
    assert res == {"id": res["id"], "accepted": True} and control == {"id": control["id"], "accepted": True}
    assert UUID(res["id"]) != UUID(control["id"])
    assert _env(db, res["id"], ids[B_SID])["delivery"] == "suppressed"
    assert [x["id"] for x in _inbox(db, "tokB")["messages"]] == [control["id"]]
    st = _status(db, "tokB")
    assert st["unread"] == 1 and st["revision"] == "1"              # the counter moved for the delivered copy only
    # the sender's own views never say which
    sent = _run(main.mail_sent(_req("tokA"), "", 25, db))
    assert all("delivery" not in a for m in sent["messages"] for a in m["addressees"])
    assert {a["steam_id"] for a in sent["messages"][0]["addressees"]} == {B_SID}


@pytest.mark.parametrize("source", PLAY_SOURCES)
def test_played_delivers_for_every_recorded_participant_set(source):
    db, ids = _world()
    db.players[ids[B_SID]]["mail_from"] = "played"
    db.played.add((frozenset({ids[A_SID], ids[B_SID]}), source))
    res = _send(db, [B_SID])
    assert _env(db, res["id"], ids[B_SID])["delivery"] == "delivered"
    fan = [s for s in db.statements if "unnest(" in s]
    assert len(fan) == 1 and "ranked_series" not in fan[0]


def test_deleted_or_unknown_recipient_is_an_addressing_error():
    db, ids = _world()
    assert _send_raises(db, to=["76561198000000077"]).detail == "recipient_unknown"
    db.players[ids[C_SID]]["deleted_at"] = NOW
    assert _send_raises(db, to=[C_SID]).detail == "recipient_unknown"
    assert _send_raises(db, to=["not-an-id"]).detail == "recipient_invalid"
    assert _send_raises(db, to=[A_SID]).detail == "recipients_empty"   # only self -> nothing left
    assert not db.messages


# ── idempotency and the lock ──────────────────────────────────────────────

def test_idempotent_retry_returns_the_original_even_through_a_new_gate():
    db, ids = _world()
    key = str(uuid.uuid4())
    first = _send(db, [B_SID], key=key)
    db.mutes.append({"steam_id": A_SID, "channel": None, "revoked_at": None, "expires_at": None})
    again = _send(db, [B_SID], key=key)                              # muted since, still 200
    assert again == first and len(db.messages) == 1
    assert _send_raises(db, to=[B_SID], key=str(uuid.uuid4())).detail == "muted"   # a NEW key is gated
    assert _send_raises(db, to=[B_SID], key="nope").detail == "idempotency_key_invalid"


def test_advisory_lock_is_taken_first_and_pinned_in_the_send_span():
    db, ids = _world()
    res = _send(db, [B_SID])
    lock_i = next(i for i, s in enumerate(db.statements) if "hashtext('mail:'" in s)
    idem_i = next(i for i, s in enumerate(db.statements) if "idempotency_key = :key" in s)
    ins_i = next(i for i, s in enumerate(db.statements) if "INSERT INTO mail_messages" in s)
    ident_i = next(i for i, s in enumerate(db.statements) if "pg_advisory_xact_lock(hashtext(:sid))" in s)
    assert ident_i < lock_i < idem_i < ins_i                          # identity lattice -> sender lock -> replay -> write
    assert db.locks == [("identity", A_SID), ("mail", ids[A_SID])]
    for fn in (main.mail_send, main.mail_reply):
        src = inspect.getsource(fn)
        assert src.index("_mail_lock_identities(") < src.index("_mail_lock_sender(") \
            < src.index("_mail_prior_send(") < src.index("_mail_sender_gates(")
    assert "pg_advisory_xact_lock(hashtext('mail:' || CAST(CAST(:sid AS uuid) AS text)))" in inspect.getsource(main._mail_lock_sender)
    assert res["accepted"] is True


# ── limits ────────────────────────────────────────────────────────────────

def test_rate_limits_10_per_minute_and_100_per_day():
    db, ids = _world()
    for _ in range(9):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], created_at=NOW - timedelta(seconds=30))
    assert _send(db, [B_SID])["accepted"] is True                    # the 10th is fine
    exc = _send_raises(db, to=[B_SID])                               # the 11th in a minute
    # M12: Retry-After is the time until the OLDEST send in the window leaves it — 30 s here, not a flat 60
    assert exc.status_code == 429 and exc.detail == {"error": "rate_limited", "retry_after": 30}
    assert exc.headers["Retry-After"] == "30"
    db, ids = _world()
    for _ in range(9):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], created_at=NOW - timedelta(seconds=45))
    _send(db, [B_SID])
    assert _send_raises(db, to=[B_SID]).detail["retry_after"] == 15  # tracks the oldest send, not the newest
    db, ids = _world()
    for _ in range(99):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], created_at=NOW - timedelta(hours=2))
    assert _send(db, [B_SID])["accepted"] is True                    # the 100th
    exc = _send_raises(db, to=[B_SID])
    assert exc.detail == {"error": "rate_limited", "retry_after": 22 * 3600}    # ~22 h, not the hour once advertised
    assert exc.headers["Retry-After"] == str(22 * 3600)
    rate_sql = next(s for s in db.statements if "AS per_minute" in s)
    assert "AS minute_wait" in rate_sql and "AS day_wait" in rate_sql and rate_sql.count("MIN(created_at)") == 2
    # broadcasts never count against the sender's window
    db, ids = _world()
    for _ in range(100):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], kind="system_broadcast",
                        created_at=NOW - timedelta(seconds=10))
    assert _send(db, [B_SID])["accepted"] is True


def test_recipient_canonicalisation_then_the_cap():
    db, ids = _world()
    res = _send(db, to=[B_SID, B_SID], cc=[B_SID, A_SID, C_SID])
    envs = {rid: env for (mid, rid), env in db.recipients.items() if mid == UUID(res["id"])}
    assert envs == {ids[B_SID]: {"kind": "to", "delivery": "delivered", "read_at": None, "deleted_at": None},
                    ids[C_SID]: {"kind": "cc", "delivery": "delivered", "read_at": None, "deleted_at": None}}
    # To beats Cc regardless of which list is walked first
    res2 = _send(db, to=[C_SID], cc=[C_SID])
    assert _env(db, res2["id"], ids[C_SID])["kind"] == "to"
    extras = [f"7656119800000001{i}" for i in range(9)]              # 9 distinct strangers
    for s in extras:
        db.add_player(s)
    assert _send_raises(db, to=extras).detail == "too_many_recipients"
    assert _send(db, to=extras[:8])["accepted"] is True              # exactly 8 is the cap
    assert _send(db, to=extras[:8] + extras[:1], cc=[A_SID])["accepted"] is True   # 9 raw, 8 canonical


def test_bulk_grant_and_admin_lift_the_cap():
    db, ids = _world()
    extras = [f"7656119800000001{i}" for i in range(9)]
    for s in extras:
        db.add_player(s)
    db.bulk_grants[A_SID] = (20, NOW + timedelta(days=3))
    assert _send(db, to=extras)["accepted"] is True
    db.bulk_grants[A_SID] = (20, NOW - timedelta(days=1))            # expired grant: back to 8
    assert _send_raises(db, to=extras).detail == "too_many_recipients"
    db.admins.add(A_SID)
    assert _send(db, to=extras)["accepted"] is True
    db.blocks.add((ids[B_SID], ids[A_SID]))                          # B-12: an admin's mail obeys blocks
    res = _send(db, to=[B_SID])
    assert _env(db, res["id"], ids[B_SID])["delivery"] == "suppressed"


# ── plain text (B-L1) ─────────────────────────────────────────────────────

def test_plain_text_rules():
    db, ids = _world()
    ok = _send(db, [B_SID], subject="2 < 3 and <b>bold</b>", body="line one\r\nline two\n\n<i>x</i> 2 < 3")
    assert db.messages[UUID(ok["id"])]["body"] == "line one\nline two\n\n<i>x</i> 2 < 3"
    assert _send_raises(db, to=[B_SID], subject="a\u2028b").detail == "subject_newline"
    assert _send_raises(db, to=[B_SID], subject="a\u2029b").detail == "subject_newline"
    assert _send_raises(db, to=[B_SID], subject="a\nb").detail == "subject_newline"
    assert _send_raises(db, to=[B_SID], subject="a\u0085b").detail == "subject_control_character"
    assert _send_raises(db, to=[B_SID], body="tab\there").detail == "body_control_character"
    assert _send_raises(db, to=[B_SID], body="x\u0085y").detail == "body_control_character"
    assert _send_raises(db, to=[B_SID], body="a" * 41).detail == "body_repeated_characters"
    assert _send(db, [B_SID], body="a" * 40)["accepted"] is True
    assert _send_raises(db, to=[B_SID], subject="s" * 121).detail == "subject_too_long"
    assert _send(db, [B_SID], subject=("ab" * 60))["accepted"] is True
    assert _send_raises(db, to=[B_SID], body=("ab" * 1001)[:2001]).detail == "body_too_long"
    assert _send_raises(db, to=[B_SID], subject="   ").detail == "subject_empty"
    assert _send_raises(db, to=[B_SID], body="").detail == "body_empty"


def test_censor_refuses_records_the_hit_and_commits():
    db, ids = _world()
    term = next(iter(main._CHAT_CENSOR_TERMS))
    assert main._chat_censor_hit(term) is not None                   # the term really hits
    exc = _send_raises(db, to=[B_SID], body=f"you {term} here")
    assert exc.status_code == 400 and exc.detail == "censored"
    assert len(db.censor_hits) == 1 and db.commits == 1 and not db.messages
    assert _send_raises(db, to=[B_SID], subject=term).detail == "censored"   # the subject too
    assert not db.cases                                              # two hits: below the bucket


# ── threads (B-9) ─────────────────────────────────────────────────────────

def test_reply_derives_recipients_server_side():
    db, ids = _world()
    db.blocks.add((ids[D_SID], ids[A_SID]))                          # D suppressed on the original
    orig = _send(db, to=[B_SID, D_SID], cc=[C_SID], subject="Plan")
    reply = main._MailReplyReq(body="Sounds good", all=False, idempotency_key=str(uuid.uuid4()))
    r1 = _run(main.mail_reply(orig["id"], reply, _req("tokB"), db))
    m1 = db.messages[UUID(r1["id"])]
    assert m1["subject"] == "Re: Plan" and m1["thread_id"] == UUID(orig["id"]) and m1["in_reply_to"] == UUID(orig["id"])
    assert {rid for (mid, rid) in db.recipients if mid == m1["id"]} == {ids[A_SID]}
    reply_all = main._MailReplyReq(body="Everyone?", all=True, idempotency_key=str(uuid.uuid4()))
    r2 = _run(main.mail_reply(r1["id"], reply_all, _req("tokA"), db))
    m2 = db.messages[UUID(r2["id"])]
    assert m2["subject"] == "Re: Plan"                               # prefixed once
    assert {rid for (mid, rid) in db.recipients if mid == m2["id"]} == {ids[B_SID]}
    r3 = _run(main.mail_reply(orig["id"], main._MailReplyReq(body="All", all=True, idempotency_key=str(uuid.uuid4())),
                              _req("tokB"), db))
    got = {rid: env["kind"] for (mid, rid), env in db.recipients.items() if mid == UUID(r3["id"])}
    assert got == {ids[A_SID]: "to", ids[C_SID]: "cc"}               # sender + delivered addressees minus self; D excluded
    # a non-party (D's copy was suppressed) cannot reply at all
    db.add_session("tokD", D_SID)
    assert _raises(main.mail_reply(orig["id"], reply, _req("tokD"), db)).status_code == 404


def test_reply_all_refused_on_a_broadcast():
    db, ids = _world()
    mid = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], kind="system_broadcast", subject="News")
    all_req = main._MailReplyReq(body="hi", all=True, idempotency_key=str(uuid.uuid4()))
    assert _raises(main.mail_reply(str(mid), all_req, _req("tokB"), db)).detail == "reply_all_refused"
    one = main._MailReplyReq(body="hi", all=False, idempotency_key=str(uuid.uuid4()))
    res = _run(main.mail_reply(str(mid), one, _req("tokB"), db))    # a plain reply is fine
    assert db.messages[UUID(res["id"])]["kind"] == "direct"


# ── reports and spam (B-10, B-14) ─────────────────────────────────────────

def test_report_snapshots_dedupes_and_posts_once():
    db, ids = _world()
    res = _send(db, [B_SID], subject="Rude", body="<@123> @everyone hi `code`")
    rep = main._MailReportReq(reason="harassment")
    first = _run(main.mail_report(res["id"], rep, _req("tokB"), db))
    case = db.cases[UUID(first["case_id"])]
    assert case["kind"] == "mail_report" and case["bucket_key"] == f"{res['id']}:{ids[B_SID]}"
    assert case["subject_player_id"] == ids[A_SID] and case["reporter_id"] == ids[B_SID]
    assert case["evidence"] == {"subject": "Rude", "body": "<@123> @everyone hi `code`",
                                "sender_id": str(ids[A_SID]), "sender_steam_id": A_SID, "sender_name": "P1",
                                "sent_at": NOW.isoformat(), "reason": "harassment"}
    assert B_SID not in json.dumps(case["evidence"])                 # the reporter is not in the snapshot
    assert len(db.outbox) == 1
    ch, content = db.outbox[0]
    assert ch == main.MAIL_ADMIN_CHANNEL_ID
    assert content.startswith(f"{main.MAIL_CASE_MARKER}{first['case_id']}]\n")
    assert "<@" not in content and "@everyone" not in content and "`code`" not in content
    again = _run(main.mail_report(res["id"], main._MailReportReq(reason="again"), _req("tokB"), db))
    assert again == first and len(db.cases) == 1 and len(db.outbox) == 1
    assert _raises(main.mail_report(res["id"], rep, _req("tokA"), db)).status_code == 404   # the sender is no recipient
    bmid = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], kind="system_broadcast")
    assert _raises(main.mail_report(str(bmid), rep, _req("tokB"), db)).detail == "cannot_report_broadcast"


def test_spam_same_body_opens_one_case_per_day_and_bumps():
    db, ids = _world()
    for _ in range(3):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], body="Buy  GOLD now", created_at=NOW - timedelta(hours=3))
    _send(db, [C_SID], body="buy gold now")                          # 4th: below the threshold
    assert not db.cases
    _send(db, [D_SID], body="BUY GOLD\nNOW")                         # 5th same normalised body
    assert len(db.cases) == 1
    case = next(iter(db.cases.values()))
    assert case["kind"] == "mail_spam" and case["bucket_key"] == f"{ids[A_SID]}:{DAY}"
    assert case["evidence"]["same_body_day"] == 5 and case["evidence"]["hits"] == 1
    assert len(db.outbox) == 1 and db.outbox[0][1].startswith(f"{main.MAIL_CASE_MARKER}{case['id']}]\n")
    _send(db, [B_SID], body="buy gold now")                          # 6th: bumped, not re-posted
    assert len(db.cases) == 1 and case["evidence"]["hits"] == 2 and case["evidence"]["same_body_day"] == 6
    assert len(db.outbox) == 1


def test_spam_bulk_sends_and_censor_hits():
    db, ids = _world()
    db.admins.add(A_SID)
    many = [db.add_player(f"765611980000002{i:02d}") for i in range(21)]
    for _ in range(2):
        db.seed_message(ids[A_SID], [(r, "to", "delivered") for r in many], body=f"n{uuid.uuid4()}",
                        created_at=NOW - timedelta(minutes=30))
    _send(db, [db.players[r]["steam_id"] for r in many[:20]], body="twenty only")   # not > 20
    assert not db.cases
    _send(db, [db.players[r]["steam_id"] for r in many], body="twenty-one")         # 3rd bulk message
    assert len(db.cases) == 1 and next(iter(db.cases.values()))["evidence"]["bulk_hour"] == 3
    # censor hits: the third refusal in a day opens the bucket in the refusal's own transaction
    db, ids = _world()
    term = next(iter(main._CHAT_CENSOR_TERMS))
    db.censor_hits += [{"sender_id": ids[A_SID], "created_at": NOW - timedelta(hours=5)}] * 2
    assert _send_raises(db, to=[B_SID], body=term).detail == "censored"
    assert len(db.cases) == 1 and next(iter(db.cases.values()))["evidence"]["censor_hits_day"] == 3
    assert len(db.outbox) == 1 and db.commits == 1


def test_broadcast_is_exempt_from_spam_and_rate():
    db, ids = _world()
    db.add_player(ADMIN_SID)
    db.admins.add(ADMIN_SID)
    db.add_player(ADMIN_SID)
    with _admin_secret():
        for i in range(6):
            _broadcast(db, subject="Same", body="same body every time")
    assert not db.cases and len([m for m in db.messages.values() if m["kind"] == "system_broadcast"]) == 6


# ── admin: broadcast, grants, cases ───────────────────────────────────────

class _admin_secret:
    def __enter__(self):
        self._old = main.ADMIN_HMAC_SECRET
        main.ADMIN_HMAC_SECRET = "test-admin-secret"
        return self

    def __exit__(self, *exc):
        main.ADMIN_HMAC_SECRET = self._old
        return False


def _sign(admin_sid, action, target):
    return hmac.new(b"test-admin-secret", main._admin_canonical(admin_sid, action, target).encode(),
                    hashlib.sha256).hexdigest()


def _broadcast(db, subject="Notice", body="Servers restart at 04:00 UTC.", key=None, admin=ADMIN_SID, sig=None):
    key = key or str(uuid.uuid4())
    req = main._AdminMailBroadcastReq(admin_steam_id=admin, hmac_signature=sig or _sign(admin, "mail_broadcast", key),
                                      subject=subject, body=body, idempotency_key=key)
    return _run(main.admin_mail_broadcast(req, db))


def test_broadcast_targets_mod_seen_window_and_bypasses_preferences():
    db, ids = _world()
    admin_id = db.add_player(ADMIN_SID)
    db.admins.add(ADMIN_SID)
    db.players[ids[B_SID]]["mail_from"] = "nobody"
    db.blocks.add((ids[C_SID], admin_id))
    db.players[ids[D_SID]]["mod_seen_at"] = NOW - timedelta(days=200)   # outside the window
    stale = db.add_player("76561198000000031", mod_seen=None)          # never ran the mod
    gone = db.add_player("76561198000000032", deleted=True)
    with _admin_secret():
        res = _broadcast(db)
    assert res["accepted"] is True and res["recipients"] == 3
    got = {rid for (mid, rid) in db.recipients if mid == UUID(res["id"])}
    assert got == {ids[A_SID], ids[B_SID], ids[C_SID]}                 # nobody + block bypassed; D, stale, gone, self excluded
    assert stale not in got and gone not in got and admin_id not in got
    m = db.messages[UUID(res["id"])]
    assert m["kind"] == "system_broadcast" and m["thread_id"] == m["id"]
    assert [a for a in db.admin_actions if a["action"] == "mail_broadcast"][0]["details"]["recipients"] == 3
    assert _inbox(db, "tokB")["messages"][0]["kind"] == "system_broadcast"
    with _admin_secret():
        again = _broadcast(db, key=str(m["idempotency_key"]))          # idempotent
    assert again == res and len(db.messages) == 1                     # the FULL original answer, recipients included (M5)
    with _admin_secret():
        exc = _raises(main.admin_mail_broadcast(main._AdminMailBroadcastReq(
            admin_steam_id=ADMIN_SID, hmac_signature="bad", subject="x", body="y",
            idempotency_key=str(uuid.uuid4())), db))
    assert exc.status_code == 403
    db.admins.discard(ADMIN_SID)
    with _admin_secret():
        assert _raises(main.admin_mail_broadcast(main._AdminMailBroadcastReq(
            admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "mail_broadcast", "k"),
            subject="x", body="y", idempotency_key="k"), db)).status_code in (400, 403)


def test_bulk_grant_routes_upsert_and_revoke():
    db, ids = _world()
    db.add_player(ADMIN_SID)
    db.admins.add(ADMIN_SID)
    with _admin_secret():
        req = main._AdminMailBulkGrantReq(admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "mail_bulk_grant", A_SID),
                                          steam_id=A_SID, max_recipients=40, days=7)
        res = _run(main.admin_mail_bulk_grant(req, db))
        assert res["max_recipients"] == 40 and db.bulk_grants[A_SID][0] == 40
        bad = main._AdminMailBulkGrantReq(admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "mail_bulk_grant", A_SID),
                                          steam_id=A_SID, max_recipients=8, days=7)
        assert _raises(main.admin_mail_bulk_grant(bad, db)).detail == "max_recipients_invalid"
        gone = _run(main.admin_mail_bulk_grant_revoke(A_SID, ADMIN_SID, _sign(ADMIN_SID, "mail_bulk_grant_revoke", A_SID), db))
    assert gone["revoked"] is True and A_SID not in db.bulk_grants
    assert [a["action"] for a in db.admin_actions] == ["mail_bulk_grant", "mail_bulk_grant_revoke"]


def _open_case(db, ids):
    res = _send(db, [B_SID], subject="Rude", body="rude words")
    case = _run(main.mail_report(res["id"], main._MailReportReq(reason="r"), _req("tokB"), db))
    return case["case_id"]


def _act_internal(db, case_id, discord_id, action, hours=None):
    payload = {"actor_discord_id": discord_id, "actor_name": "Mod", "action": action, "reason": "button"}
    if hours:
        payload["hours"] = hours
    return _run(main.internal_moderation_case_act(case_id, payload, "internal-key", db=db))


@pytest.fixture(autouse=True)
def _internal_key(monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "internal-key")


def test_act_with_a_stale_grant_is_403_and_writes_nothing():
    db, ids = _world()
    case_id = _open_case(db, ids)
    db.add_player(MOD_SID, discord_id="d-mod")                       # linked, but holds NO grant
    before = (len(db.admin_actions), len(db.mutes), dict(db.bans))
    exc = _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-mod", "action": "mute", "hours": 24},
                                                    "internal-key", db=db))
    assert exc.status_code == 403 and exc.detail == "not_authorised"
    assert (len(db.admin_actions), len(db.mutes), dict(db.bans)) == before
    assert db.cases[UUID(case_id)]["status"] == "open"
    assert _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "nobody", "action": "dismiss"},
                                                     "internal-key", db=db)).detail == "not_linked"
    assert _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-mod", "action": "dismiss"},
                                                     "wrong-key", db=db)).status_code == 403
    # a language moderator may dismiss but not mute or ban (a mail mute is global, admin-only)
    db.mod_grants[MOD_SID] = ["ru"]
    assert _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-mod", "action": "mute", "hours": 24},
                                                     "internal-key", db=db)).detail == "admin_required"
    assert _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-mod", "action": "ban"},
                                                     "internal-key", db=db)).detail == "admin_required"
    res = _act_internal(db, case_id, "d-mod", "dismiss")
    assert res["status"] == "ok" and db.cases[UUID(case_id)]["status"] == "dismissed"
    assert db.cases[UUID(case_id)]["resolved_by"] == MOD_SID
    assert [a["action"] for a in db.admin_actions][-1] == "modcase_act"


def test_act_mute_uses_the_chat_mute_core_globally():
    db, ids = _world()
    case_id = _open_case(db, ids)
    db.add_player(ADMIN_SID, discord_id="d-admin")
    db.admins.add(ADMIN_SID)
    res = _act_internal(db, case_id, "d-admin", "mute", hours=24)
    assert res["status"] == "ok" and res["resolution"] == "mute:24h" and res["subject_steam_id"] == A_SID
    assert db.mutes == [{"steam_id": A_SID, "channel": None, "revoked_at": None,
                         "expires_at": NOW + timedelta(hours=24), "by": ADMIN_SID, "reason": "button", "minutes": 1440}]
    case = db.cases[UUID(case_id)]
    assert case["status"] == "resolved" and case["resolved_by"] == ADMIN_SID and case["resolution"] == "mute:24h"
    actions = [(a["action"], a["target"]) for a in db.admin_actions]
    assert ("chat_mute", A_SID) in actions and ("modcase_act", A_SID) in actions
    assert db.admin_actions[-1]["details"]["via"] == "discord:d-admin"
    # the muted sender can no longer mail
    assert _send_raises(db, to=[B_SID]).detail == "muted"
    # a second click is harmless
    again = _act_internal(db, case_id, "d-admin", "ban")
    assert again["status"] == "already_resolved" and not db.added
    assert _raises(main.internal_moderation_case_act(str(uuid.uuid4()), {"actor_discord_id": "d-admin", "action": "dismiss"},
                                                     "internal-key", db=db)).status_code == 404
    assert _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-admin", "action": "nuke"},
                                                     "internal-key", db=db)).detail == "action_invalid"


def test_act_ban_uses_the_ban_core_and_admin_hmac_route_agrees():
    db, ids = _world()
    case_id = _open_case(db, ids)
    db.add_player(ADMIN_SID, discord_id="d-admin")
    db.admins.add(ADMIN_SID)
    res = _act_internal(db, case_id, "d-admin", "ban")
    assert res["status"] == "ok" and res["resolution"] == "ban"
    kinds = [type(o).__name__ for o in db.added]
    assert kinds == ["PlayerBan", "AdminAction"]
    assert db.added[0].steam_id == A_SID and db.added[0].banned_by_steam_id == ADMIN_SID
    assert ("ban-rate", ADMIN_SID) in db.locks and ("identity", A_SID) in db.locks
    assert db.cases[UUID(case_id)]["status"] == "resolved"
    # the admin-HMAC route runs the same core; a signer/actor mismatch is refused
    db2, ids2 = _world()
    cid2 = _open_case(db2, ids2)
    db2.admins.add(ADMIN_SID)
    db2.add_player(ADMIN_SID)
    with _admin_secret():
        req = main._AdminModCaseActReq(admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "modcase_act", cid2),
                                       actor_steam_id=B_SID, action="dismiss")
        assert _raises(main.admin_moderation_case_act(cid2, req, db=db2)).detail == "actor_mismatch"
        req = main._AdminModCaseActReq(admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "modcase_act", cid2),
                                       action="dismiss")
        assert _run(main.admin_moderation_case_act(cid2, req, db=db2))["status"] == "ok"
        listing = _run(main.admin_moderation_cases(ADMIN_SID, _sign(ADMIN_SID, "modcase_list", ""), "dismissed", 50, db2))
    assert [c["id"] for c in listing["cases"]] == [cid2] and listing["cases"][0]["reporter_steam_id"] == B_SID


def test_notified_stamp_once():
    db, ids = _world()
    case_id = _open_case(db, ids)
    first = _run(main.internal_moderation_case_notified(case_id, "internal-key", db))
    assert first["status"] == "ok" and db.cases[UUID(case_id)]["notified_at"] == NOW
    assert _run(main.internal_moderation_case_notified(case_id, "internal-key", db))["notified_at"] == first["notified_at"]
    assert _raises(main.internal_moderation_case_notified(str(uuid.uuid4()), "internal-key", db)).status_code == 404


# ── inbox reads, status, blocks, settings ─────────────────────────────────

def test_inbox_pages_newest_first_with_an_opaque_cursor():
    db, ids = _world()
    sent = []
    for i in range(3):
        db.message_created_at = NOW - timedelta(minutes=10 - i)
        sent.append(_send(db, [B_SID], subject=f"m{i}")["id"])
    page = _inbox(db, "tokB", limit=2)
    assert [m["id"] for m in page["messages"]] == [sent[2], sent[1]] and page["next_cursor"]
    assert "|" not in page["next_cursor"] and "+" not in page["next_cursor"]
    page2 = _inbox(db, "tokB", cursor=page["next_cursor"], limit=2)
    assert [m["id"] for m in page2["messages"]] == [sent[0]] and page2["next_cursor"] is None
    assert _raises(main.mail_inbox(_req("tokB"), "@@garbage", 2, db)).detail == "cursor_invalid"


def test_read_delete_detail_and_status_revision_monotonic():
    db, ids = _world()
    db.message_created_at = NOW - timedelta(minutes=5)
    m1 = _send(db, [B_SID], subject="one")["id"]
    db.message_created_at = NOW
    m2 = _send(db, [B_SID], cc=[C_SID], subject="two")["id"]
    st = _status(db, "tokB")
    assert st == {"unread": 2, "revision": "2", "mail_from": "everyone"}
    read = _run(main.mail_read(m1, _req("tokB"), db))
    assert read["read_at"] == NOW.isoformat() and _status(db, "tokB")["unread"] == 1
    detail = _run(main.mail_detail(m2, _req("tokB"), db))
    assert detail["subject"] == "two" and detail["body"] == "A perfectly ordinary body."
    assert detail["to"] == [{"steam_id": B_SID, "name": "P2"}] and detail["cc"] == [{"steam_id": C_SID, "name": "P3"}]
    assert "delivery" not in json.dumps(detail) and detail["read_at"] is None
    assert _run(main.mail_detail(m2, _req("tokA"), db))["read_at"] is None    # the sender's view
    db.add_session("tokD", D_SID)
    assert _raises(main.mail_detail(m2, _req("tokD"), db)).status_code == 404  # not a party
    gone = _run(main.mail_delete(m2, _req("tokB"), db))
    assert gone["status"] == "deleted"
    st = _status(db, "tokB")
    assert st["unread"] == 0 and st["revision"] == "2"               # deleting the newest never moves it back
    assert [m["id"] for m in _inbox(db, "tokB")["messages"]] == [m1]
    assert _raises(main.mail_detail(m2, _req("tokB"), db)).status_code == 404
    assert _raises(main.mail_read(m2, _req("tokB"), db)).status_code == 404
    # C still has their copy; the sender's delete only touches the sender's flag
    assert _run(main.mail_detail(m2, _req("tokA"), db))["id"] == m2
    _run(main.mail_delete(m2, _req("tokA"), db))
    assert db.messages[UUID(m2)]["deleted_by_sender_at"] == NOW
    assert _raises(main.mail_detail(m2, _req("tokA"), db)).status_code == 404
    db.add_session("tokC", C_SID)
    assert _run(main.mail_detail(m2, _req("tokC"), db))["id"] == m2
    assert _raises(main.mail_delete(str(uuid.uuid4()), _req("tokB"), db)).status_code == 404


def test_block_list_is_owner_only():
    db, ids = _world()
    _run(main.mail_block_add(main._MailBlockReq(steam_id=C_SID), _req("tokA"), db))
    assert db.blocks == {(ids[A_SID], ids[C_SID])}
    mine = _run(main.mail_blocks_list(_req("tokA"), db))["blocks"]
    assert [b["steam_id"] for b in mine] == [C_SID] and mine[0]["name"] == "P3"
    assert _run(main.mail_blocks_list(_req("tokB"), db))["blocks"] == []       # B sees nothing of A's
    assert _raises(main.mail_blocks_list(_req(None), db)).status_code == 401
    assert _raises(main.mail_block_add(main._MailBlockReq(steam_id=A_SID), _req("tokA"), db)).detail == "cannot_block_self"
    assert _raises(main.mail_block_add(main._MailBlockReq(steam_id="76561198000000099"), _req("tokA"), db)).status_code == 404
    assert _raises(main.mail_block_add(main._MailBlockReq(steam_id="x"), _req("tokA"), db)).detail == "steam_id_invalid"
    _run(main.mail_block_remove(C_SID, _req("tokA"), db))
    assert db.blocks == set()


def test_settings_route_owns_mail_from():
    db, ids = _world()
    assert _run(main.mail_settings_get(_req("tokA"), db)) == {"mail_from": "everyone"}
    assert _run(main.mail_settings_put(main._MailSettingsReq(mail_from="Played"), _req("tokA"), db)) == {"mail_from": "played"}
    assert db.players[ids[A_SID]]["mail_from"] == "played"
    assert _raises(main.mail_settings_put(main._MailSettingsReq(mail_from="friends"), _req("tokA"), db)).detail == "mail_from_invalid"
    assert db.players[ids[A_SID]]["mail_from"] == "played"


# ── delete-account (B-8) and retention ────────────────────────────────────

def test_delete_account_handles_every_new_table_by_name():
    src = inspect.getsource(main.delete_player_data)
    for stmt, n in (("DELETE FROM mail_recipients WHERE recipient_id = :pid", 2),   # the early sweep and the post-rewrite sweep (H3)
                    ("DELETE FROM mail_blocks WHERE blocker_id = :pid OR blocked_id = :pid", 1),
                    ("UPDATE moderation_cases SET reporter_id = NULL WHERE reporter_id = :pid", 1),
                    ("DELETE FROM mail_bulk_grants WHERE steam_id = :sid", 1),
                    ("DELETE FROM mail_censor_hits WHERE sender_id = :pid", 1),
                    ("UPDATE moderation_cases SET resolved_by = :tomb WHERE resolved_by = :sid", 1),     # M11
                    ("UPDATE mail_bulk_grants SET granted_by = :tomb WHERE granted_by = :sid", 1),       # M11
                    ("DELETE FROM mail_inbox_rev WHERE recipient_id = :pid", 1)):                         # migration 300
        assert src.count(stmt) == n, stmt
    # H3: the second envelope sweep and the revision row go AFTER the anonymising rewrite has been flushed
    rewrite = src.index('player.steam_id = f"deleted_')
    flush = src.index("await db.flush()", rewrite)
    assert rewrite < flush < src.rindex("DELETE FROM mail_recipients WHERE recipient_id = :pid") \
        < src.index("DELETE FROM mail_inbox_rev") < src.index("await db.commit()", flush)
    assert "FOR KEY SHARE OF p" in main._MAIL_FANOUT_SQL and "FOR KEY SHARE OF p" in main._MAIL_BROADCAST_FANOUT_SQL
    # sent messages and the moderation evidence are retained (the recipients' and the moderators' property)
    assert "DELETE FROM mail_messages" not in src and "DELETE FROM moderation_cases" not in src
    ban = inspect.getsource(main._apply_ban_core)
    assert "mail_" not in ban                                        # a ban leaves mail alone


def test_janitor_retention_keeps_unread_and_purges_let_go_mail():
    db, ids = _world()
    old = NOW - timedelta(days=181)
    old_read = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], created_at=old, read=True)
    old_unread = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], created_at=old)
    let_go = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], deleted_by_sender_at=NOW)
    db.recipients[(let_go, ids[B_SID])]["deleted_at"] = NOW
    half_let_go = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered"), (ids[C_SID], "cc", "delivered")],
                                  deleted_by_sender_at=NOW)
    db.recipients[(half_let_go, ids[B_SID])]["deleted_at"] = NOW
    suppressed_only = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "suppressed")], deleted_by_sender_at=NOW)
    kept_suppressed = db.seed_message(ids[A_SID], [(ids[B_SID], "to", "suppressed")])
    db.censor_hits = [{"sender_id": ids[A_SID], "created_at": NOW - timedelta(days=3)},
                      {"sender_id": ids[A_SID], "created_at": NOW - timedelta(hours=1)}]
    expired, purged, hits = _run(main._mail_retention_sweep(db))
    assert (expired, purged, hits) == (1, 3, 1)
    assert set(db.messages) == {old_unread, half_let_go, kept_suppressed}
    assert (old_read, ids[B_SID]) not in db.recipients and (let_go, ids[B_SID]) not in db.recipients
    assert suppressed_only not in db.messages
    assert db.recipients[(old_unread, ids[B_SID])]["deleted_at"] is None
    assert len(db.censor_hits) == 1
    src = inspect.getsource(main.queue_cleanup_loop)
    assert src.count("_mail_retention_sweep(") == 1 and "[MAIL-RETENTION]" in src
    sweep = inspect.getsource(main._mail_retention_sweep)
    assert "r.delivery = 'delivered'" in sweep and "r.deleted_at IS NULL" in sweep


# ── structure pins ────────────────────────────────────────────────────────

def test_route_order_fixed_paths_before_the_message_id_route():
    paths = [(sorted(r.methods)[0], r.path) for r in main.app.routes if isinstance(r, APIRoute)]
    detail_i = paths.index(("GET", "/api/v1/mail/{message_id}"))
    for fixed in ("/api/v1/mail/inbox", "/api/v1/mail/sent", "/api/v1/mail/status",
                  "/api/v1/mail/blocks", "/api/v1/mail/settings"):
        assert paths.index(("GET", fixed)) < detail_i, fixed
    assert ("PUT", "/api/v1/mail/settings") in paths and ("DELETE", "/api/v1/mail/blocks/{steam_id}") in paths


def test_moderation_cores_are_shared_not_copied():
    mute_route = inspect.getsource(main.chat_moderate_mute)
    assert "_chat_mute_apply(" in mute_route and "INSERT INTO chat_mutes" not in mute_route
    act = inspect.getsource(main._moderation_case_act)
    for helper in ("_chat_mute_apply(", "_ban_rate_gate_or_raise(", "_apply_ban_core(", "_chat_moderator_scope("):
        assert helper in act, helper
    assert "INSERT INTO chat_mutes" not in act and "PlayerBan(" not in act
    ban_route = inspect.getsource(main.admin_ban)
    assert "_ban_rate_gate_or_raise(" in ban_route and "_apply_ban_core(" in ban_route
    assert "PlayerBan(" not in ban_route and "pg_advisory_xact_lock" not in ban_route
    core = inspect.getsource(main._apply_ban_core)
    assert "db.add(PlayerBan(" in core and "await db.commit()" not in core
    gate = inspect.getsource(main._ban_rate_gate_or_raise)
    assert gate.count("await db.commit()") == 1 and "status_code=429" in gate


def test_fanout_and_marker_contracts_pinned():
    for needle in FANOUT_PREDICATES:
        assert needle in main._MAIL_FANOUT_SQL
    assert "ranked_series" not in main._MAIL_FANOUT_SQL
    assert main._MAIL_FANOUT_SQL.count("INSERT INTO") == 1
    assert main.MAIL_CASE_MARKER == "[MODCASE:"
    assert main.MAIL_RECIPIENT_CAP == 8 and main.MAIL_RATE_PER_MINUTE == 10 and main.MAIL_RATE_PER_DAY == 100
    assert main.MAIL_SUBJECT_MAX == 120 and main.MAIL_BODY_MAX == 2000 and main.MAIL_RUN_MAX == 40
    assert main._mail_norm_body("  Buy   GOLD\n\nnow ") == "buy gold now"
    assert main._mail_text_problem("x" * 40, subject=False) is None
    assert main._mail_text_problem("x" * 41, subject=False) == "repeated_characters"


# ── review r1 pins (the server half of the Sept 6 item b repairs) ─────────

def test_sender_lock_bind_is_typed_uuid_for_asyncpg():
    """H1: asyncpg picks the codec from the bind's SQL type. The fake applies
    that rule (a text-cast bind refuses a uuid.UUID), the real helper passes
    it, and the pre-repair statement is shown to be the failing one."""
    db, ids = _world()
    assert _send(db, [B_SID])["accepted"] is True
    lock_sql = next(s for s in db.statements if "hashtext('mail:'" in s)
    assert "CAST(CAST(:sid AS uuid) AS text)" in lock_sql
    old = "SELECT pg_advisory_xact_lock(hashtext('mail:' || CAST(:sid AS text)))"
    with pytest.raises(TypeError, match="expected str, got UUID"):
        _run(db.execute(text(old), {"sid": ids[A_SID]}))
    _run(db.execute(text(old), {"sid": str(ids[A_SID])}))             # a str bind is what a text cast accepts
    assert isinstance(ids[A_SID], uuid.UUID)                         # players.id really is a UUID object here


_LATTICE = [  # route, whose row the racing deletion removes, the refusal the re-read must answer
    ("send", "actor", (401, "session_required")),
    ("reply", "actor", (401, "session_required")),
    ("report", "actor", (401, "session_required")),
    ("block_add", "actor", (401, "session_required")),
    ("block_add", "target", (404, "player_unknown")),
    ("block_remove", "actor", (401, "session_required")),
    ("broadcast", "actor", (404, "admin_player_unknown")),   # the one privileged route that needs the admin's row: it is the message's sender
    ("grant", "target", (404, "player_unknown")),
    ("act_mute", "target", (400, "subject_deleted")),
]
# The actor rows of grant/revoke/act_* and the target rows of dismiss/revoke
# are no refusals since review r2: the admin acts on admin_users membership,
# and dismiss/revoke complete against a scrubbed subject — see
# test_a_scrub_under_the_lock_is_written_as_the_tombstone.


def _lattice_world(route):
    """A world in which `route` succeeds. Returns (db, original message id,
    case id, actor steam id, target steam id)."""
    db, ids = _world()
    orig = _send(db, [B_SID])["id"]                                  # A -> B: reply / report are B's
    case_id, actor, target = None, A_SID, C_SID
    if route in ("reply", "report"):
        actor = B_SID
    if route in ("broadcast", "grant", "revoke"):
        db.add_player(ADMIN_SID)
        db.admins.add(ADMIN_SID)
        actor = ADMIN_SID
    if route.startswith("act_"):
        case_id = _open_case(db, ids)                                # subject = A, the sender
        db.add_player(ADMIN_SID, discord_id="d-admin")
        db.admins.add(ADMIN_SID)
        actor, target = ADMIN_SID, A_SID
    if route == "ban":
        db.add_player(ADMIN_SID, discord_id="d-admin")
        db.admins.add(ADMIN_SID)
        actor, target = ADMIN_SID, A_SID
    db.statements.clear()
    db.locks.clear()
    db.commits = 0
    return db, orig, case_id, actor, target


def _lattice_coro(db, route, orig, case_id):
    key = str(uuid.uuid4())
    if route == "send":
        return main.mail_send(main._MailSendReq(to=[B_SID], cc=[], subject="Hi", body="A perfectly ordinary body.",
                                                idempotency_key=key), _req("tokA"), db)
    if route == "reply":
        return main.mail_reply(orig, main._MailReplyReq(body="ok", all=False, idempotency_key=key), _req("tokB"), db)
    if route == "report":
        return main.mail_report(orig, main._MailReportReq(reason="spam"), _req("tokB"), db)
    if route == "block_add":
        return main.mail_block_add(main._MailBlockReq(steam_id=C_SID), _req("tokA"), db)
    if route == "block_remove":
        return main.mail_block_remove(C_SID, _req("tokA"), db)
    if route == "broadcast":
        return main.admin_mail_broadcast(main._AdminMailBroadcastReq(
            admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "mail_broadcast", key),
            subject="Notice", body="Servers restart at 04:00 UTC.", idempotency_key=key), db)
    if route == "grant":
        return main.admin_mail_bulk_grant(main._AdminMailBulkGrantReq(
            admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "mail_bulk_grant", C_SID),
            steam_id=C_SID, max_recipients=40, days=7), db)
    if route == "revoke":
        return main.admin_mail_bulk_grant_revoke(C_SID, ADMIN_SID, _sign(ADMIN_SID, "mail_bulk_grant_revoke", C_SID), db)
    if route == "act_mute":
        return main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-admin", "actor_name": "Mod",
                                                           "action": "mute", "hours": 24, "reason": "b"}, "internal-key", db=db)
    if route == "act_dismiss":
        return main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-admin", "actor_name": "Mod",
                                                           "action": "dismiss", "reason": "b"}, "internal-key", db=db)
    if route == "act_dismiss_hmac":
        return main.admin_moderation_case_act(case_id, main._AdminModCaseActReq(
            admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "modcase_act", case_id),
            action="dismiss", reason="b"), db=db)
    if route == "ban":
        return main.admin_ban(main._AdminBanReq(admin_steam_id=ADMIN_SID, target_steam_id=A_SID, reason="x",
                                                hmac_signature=_sign(ADMIN_SID, "ban", A_SID)), db=db)
    raise AssertionError(route)


def _is_write(sql):
    return sql.lstrip().split(" ", 1)[0].upper() in ("INSERT", "UPDATE", "DELETE")


@pytest.mark.parametrize("route,victim,refusal", _LATTICE, ids=[f"{r}-{v}" for r, v, _ in _LATTICE])
def test_every_mutation_joins_the_identity_lattice(route, victim, refusal):
    """H3: each mutation takes delete-account's own advisory lock on every
    identity it writes BEFORE its first write, re-reads it live under the
    lock, and refuses when the row is gone. The hook fires as the lock is
    granted — the shape of a deletion that committed while this transaction
    waited — so the refusal is the re-read's, not the session gate's."""
    db, orig, case_id, actor, target = _lattice_world(route)         # positive control: the route works
    with _admin_secret():
        _run(_lattice_coro(db, route, orig, case_id))
    sid = actor if victim == "actor" else target
    lock_i = next(i for i, s in enumerate(db.statements) if "pg_advisory_xact_lock(hashtext(:sid))" in s)
    reread_i = next(i for i, s in enumerate(db.statements) if "FROM players WHERE id = :pid FOR NO KEY UPDATE" in s)
    write_i = next(i for i, s in enumerate(db.statements) if _is_write(s))
    assert lock_i < reread_i < write_i and ("identity", sid) in db.locks and db.commits >= 1
    db, orig, case_id, actor, target = _lattice_world(route)         # the race
    sid = actor if victim == "actor" else target

    def deleted_under_lock(locked):
        if locked == sid:
            db.player_by_sid(sid)["deleted_at"] = NOW
    db.on_identity_lock = deleted_under_lock
    with _admin_secret():
        exc = _raises(_lattice_coro(db, route, orig, case_id))
    assert (exc.status_code, exc.detail) == refusal
    assert db.commits == 0 and not any(_is_write(s) for s in db.statements)


def test_dismiss_still_closes_a_case_whose_subject_was_deleted():
    """The lattice's one asymmetry: mute/ban have nothing to write for a
    deleted subject (refused above); dismiss locks the subject all the same
    (its identity is the audit row's target) and closes the case with the
    identity it re-read — here the tombstone of a subject deleted before
    the click."""
    db, orig, case_id, actor, target = _lattice_world("act_dismiss")
    tomb = db.scrub(A_SID)
    assert _run(_lattice_coro(db, "act_dismiss", orig, case_id))["status"] == "ok"
    assert db.cases[UUID(case_id)]["status"] == "dismissed" and ("identity", tomb) in db.locks
    assert db.admin_actions[-1]["target"] == tomb and A_SID not in json.dumps(db.admin_actions)


def test_status_revision_advances_in_commit_order_not_created_at():
    """M4: a send that STARTED first (older created_at) but commits last must
    still move the revision — the counter does, a newest-created_at cursor
    (the negative control) does not; reads, deletes and suppressed copies
    never move it."""
    db, ids = _world()
    db.message_created_at = NOW
    first = _send(db, [B_SID], subject="newer timestamp, committed first")
    assert _status(db, "tokB") == {"unread": 1, "revision": "1", "mail_from": "everyone"}
    fan_i = next(i for i, s in enumerate(db.statements) if "INSERT INTO mail_recipients" in s)
    bump_i = next(i for i, s in enumerate(db.statements) if "INSERT INTO mail_inbox_rev" in s)
    assert fan_i < bump_i < db.commit_marks[0]                       # the bump is INSIDE the sending transaction: after its fan-out, before its commit (review r2 pin)
    db.message_created_at = NOW - timedelta(hours=1)                 # the stalled send: older timestamp, later commit
    second = _send(db, [B_SID], subject="older timestamp, committed last")
    st = _status(db, "tokB")
    assert st["unread"] == 2 and st["revision"] == "2"
    newest_by_created = max(db.messages.values(), key=lambda m: (m["created_at"], m["id"]))["id"]
    assert str(newest_by_created) == first["id"]                     # the old cursor would still point at the first
    _run(main.mail_read(second["id"], _req("tokB"), db))
    _run(main.mail_delete(first["id"], _req("tokB"), db))
    assert _status(db, "tokB")["revision"] == "2"
    db.blocks.add((ids[B_SID], ids[A_SID]))
    _send(db, [B_SID])                                               # suppressed: no bump
    assert _status(db, "tokB")["revision"] == "2" and db.inbox_rev.get(ids[A_SID]) is None
    bumps = [s for s in db.statements if "INSERT INTO mail_inbox_rev" in s]
    assert bumps and all("SET rev = mail_inbox_rev.rev + 1" in s for s in bumps)   # a DB delta (#326)
    assert "FROM mail_inbox_rev" in next(s for s in db.statements if "AS revision" in s)


def test_recipient_bound_is_above_every_grant_and_the_cap_precedes_resolution():
    """M6: the raw-list guard is a payload bound above the largest grant, with
    its own code; the policy cap is judged on the CANONICAL list, before any
    id is resolved."""
    assert main.MAIL_INPUT_LIST_MAX >= 2 * main.MAIL_ADMIN_RECIPIENT_CAP
    db, ids = _world()
    res = _send(db, to=[B_SID] * 201)                                # 201 raw entries canonicalise to one
    assert res["accepted"] is True and [rid for (mid, rid) in db.recipients if mid == UUID(res["id"])] == [ids[B_SID]]
    many = [f"7656119800001{i:04d}" for i in range(300)]
    for s in many:
        db.add_player(s)
    db.admins.add(A_SID)
    res = _send(db, to=many)                                         # 300 authorised recipients: inside the admin cap
    assert sum(1 for (mid, _rid) in db.recipients if mid == UUID(res["id"])) == 300
    assert _send_raises(db, to=[B_SID] * (main.MAIL_INPUT_LIST_MAX + 1)).detail == "recipient_list_too_large"
    db.admins.discard(A_SID)
    db.statements.clear()
    assert _send_raises(db, to=many[:9]).detail == "too_many_recipients"
    assert not any("= ANY(" in s for s in db.statements)             # refused before the ids were resolved


def test_same_body_key_casefolds_and_collapses_unicode_whitespace():
    """M7: one normaliser, on the Python side, for the spam trigger."""
    norm = main._mail_norm_body
    assert norm("STRASSE") == norm("Straße") == norm("strasse")
    assert norm("buy gold now") == norm(" buy  gold\n\nnow ") == "buy gold now"
    assert norm("Buy Gold") != norm("Buy Gold Now")                  # negative control
    db, ids = _world()
    for body in ("STRASSE", "Strasse", "STRASSE"):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], body=body, created_at=NOW - timedelta(hours=3))
    _send(db, [C_SID], body="Straße")                                # 4th
    assert not db.cases
    _send(db, [D_SID], body="straße")                           # 5th: the case opens
    assert len(db.cases) == 1 and next(iter(db.cases.values()))["evidence"]["same_body_day"] == 5
    assert [s for s in db.statements if s.lstrip().startswith("SELECT body FROM mail_messages")]
    assert "_mail_norm_body(" in inspect.getsource(main._mail_spam_check)


def test_prohibited_characters_are_judged_before_trimming():
    """M8: a boundary control is a refusal, not a silent trim; a lone CR is a
    control, not a newline; CRLF is the one normalised form."""
    db, ids = _world()
    assert _send_raises(db, to=[B_SID], subject="hello\n").detail == "subject_newline"
    assert _send_raises(db, to=[B_SID], subject="hello ").detail == "subject_newline"
    assert _send_raises(db, to=[B_SID], subject="hello").detail == "subject_control_character"
    assert _send_raises(db, to=[B_SID], body="a\rb").detail == "body_control_character"
    assert _send_raises(db, to=[B_SID], body="body\r").detail == "body_control_character"
    assert _send_raises(db, to=[B_SID], body="\tbody").detail == "body_control_character"
    ok = _send(db, [B_SID], subject="  padded  ", body="a\r\nb\n")
    m = db.messages[UUID(ok["id"])]
    assert m["subject"] == "padded" and m["body"] == "a\nb"
    rep = _raises(main.mail_report(ok["id"], main._MailReportReq(reason="spam: a\rb"), _req("tokB"), db))
    assert rep.detail == "reason_control_character"


def _bcast_req():
    key = str(uuid.uuid4())
    return main._AdminMailBroadcastReq(admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "mail_broadcast", key),
                                       subject="Notice", body="Servers restart at 04:00 UTC.", idempotency_key=key)


def test_broadcast_obeys_the_sender_gates():
    """M9: an admin HMAC proves identity, not an exemption from the sending
    rules — mod-seen, ban and GLOBAL mute refuse a broadcast; a channel mute
    does not (negative control)."""
    db, ids = _world()
    db.add_player(ADMIN_SID)
    db.admins.add(ADMIN_SID)
    with _admin_secret():
        assert _run(main.admin_mail_broadcast(_bcast_req(), db))["accepted"] is True
        db.mutes.append({"steam_id": ADMIN_SID, "channel": "ru", "revoked_at": None, "expires_at": None})
        assert _run(main.admin_mail_broadcast(_bcast_req(), db))["accepted"] is True   # a channel mute is not a mail gate
        db.mutes.append({"steam_id": ADMIN_SID, "channel": None, "revoked_at": None, "expires_at": None})
        muted = _raises(main.admin_mail_broadcast(_bcast_req(), db))
        assert (muted.status_code, muted.detail) == (403, "muted")
        db.mutes.clear()
        db.bans[ADMIN_SID] = "spam"
        assert _raises(main.admin_mail_broadcast(_bcast_req(), db)).detail == "banned"
        del db.bans[ADMIN_SID]
        db.player_by_sid(ADMIN_SID)["mod_seen_at"] = None
        assert _raises(main.admin_mail_broadcast(_bcast_req(), db)).detail == "mod_required"
    assert len([m for m in db.messages.values() if m["kind"] == "system_broadcast"]) == 2
    assert "_mail_sender_gates(" in inspect.getsource(main.admin_mail_broadcast)


def test_privileged_audit_rows_are_part_of_the_transaction():
    """M10: mail's privileged actions use the STRICT audit helper — an
    admin_actions insert that fails fails the action, nothing commits. The
    soft helper the chat routes chose swallows the very same failure
    (negative control), so the two are not interchangeable."""
    db, ids = _world()
    db.add_player(ADMIN_SID, discord_id="d-admin")
    db.admins.add(ADMIN_SID)
    case_id = _open_case(db, ids)
    db.fail_admin_actions = True
    before = db.commits
    with _admin_secret():
        with pytest.raises(RuntimeError, match="admin_actions"):
            _run(main.admin_mail_broadcast(_bcast_req(), db))
        with pytest.raises(RuntimeError, match="admin_actions"):
            _run(main.admin_mail_bulk_grant(main._AdminMailBulkGrantReq(
                admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "mail_bulk_grant", A_SID),
                steam_id=A_SID, max_recipients=40, days=7), db))
        with pytest.raises(RuntimeError, match="admin_actions"):
            _run(main.admin_mail_bulk_grant_revoke(A_SID, ADMIN_SID, _sign(ADMIN_SID, "mail_bulk_grant_revoke", A_SID), db))
    with pytest.raises(RuntimeError, match="admin_actions"):
        _act_internal(db, case_id, "d-admin", "dismiss")
    assert db.commits == before and not db.admin_actions
    _run(main._log_admin_action(db, admin_steam_id=ADMIN_SID, action="x", target_steam_id=None, details={}))   # swallowed
    for fn in (main.admin_mail_broadcast, main.admin_mail_bulk_grant, main.admin_mail_bulk_grant_revoke,
               main._moderation_case_act):
        src = inspect.getsource(fn)
        assert "_log_admin_action_strict(" in src and "_log_admin_action(" not in src.replace("_log_admin_action_strict(", "")
    assert "begin_nested" not in inspect.getsource(main._log_admin_action_strict)


def test_case_without_its_outbox_row_does_not_commit():
    """M3: the moderation post is PART of the case's transaction — a failed
    outbox insert fails the report (nothing is swallowed, nothing commits),
    so the unique case cannot exist without its notification."""
    db, ids = _world()
    res = _send(db, [B_SID], subject="Rude", body="rude words")
    db.fail_outbox = True
    with pytest.raises(RuntimeError, match="outbox"):
        _run(main.mail_report(res["id"], main._MailReportReq(reason="spam"), _req("tokB"), db))
    assert db.commits == 1 and not db.outbox                         # only the send committed
    assert "begin_nested" not in inspect.getsource(main._mail_open_case)
    db.cases.clear()                                                 # the rollback this fake does not emulate
    db.fail_outbox = False
    case = _run(main.mail_report(res["id"], main._MailReportReq(reason="spam"), _req("tokB"), db))
    assert len(db.outbox) == 1 and db.outbox[0][1].startswith(f"{main.MAIL_CASE_MARKER}{case['case_id']}]")


def test_broadcast_replay_returns_the_full_original_response():
    """M5, and review r2 LOW: a same-key retry whose first answer was lost
    still learns the recipient count — the count PERSISTED on the row in
    the sending transaction, replayed verbatim, so a recipient who deleted
    their account in between cannot change the replayed answer."""
    db, ids = _world()
    db.add_player(ADMIN_SID)
    db.admins.add(ADMIN_SID)
    key = str(uuid.uuid4())
    with _admin_secret():
        first = _broadcast(db, key=key)
        mid = UUID(first["id"])
        assert db.messages[mid]["recipient_count"] == 4
        set_i = next(i for i, s in enumerate(db.statements) if "UPDATE mail_messages SET recipient_count" in s)
        assert set_i < db.commit_marks[-1]                             # persisted inside the sending transaction
        db.recipients.pop((mid, ids[D_SID]))                           # D's account went: the envelope is gone
        db.statements.clear()
        again = _broadcast(db, key=key)
    assert first["recipients"] == 4 and again == first and set(again) == {"id", "accepted", "recipients"}
    assert not any("COUNT(*) FROM mail_recipients" in s for s in db.statements)   # replayed, not recounted
    assert len([m for m in db.messages.values() if m["kind"] == "system_broadcast"]) == 1
    db.messages[mid]["recipient_count"] = None                         # control: a row written before the column falls back to its envelopes
    with _admin_secret():
        assert _broadcast(db, key=key)["recipients"] == 3


def test_fake_db_reads_its_authorisation_off_the_production_sql():
    """M18/M19 negative control: the same statements with their predicates
    removed make the fake return what PostgreSQL would — the outsider gets
    the message, the suppressed copy is listed and counted — so the 404s and
    the silent suppression above rest on the production SQL, not on the fake."""
    db, ids = _world()
    res = _send(db, [B_SID])
    db.blocks.add((ids[B_SID], ids[A_SID]))
    sup = _send(db, [B_SID])                                         # suppressed for B
    db.add_session("tokD", D_SID)
    assert _raises(main.mail_detail(res["id"], _req("tokD"), db)).status_code == 404
    assert [m["id"] for m in _inbox(db, "tokB")["messages"]] == [res["id"]]
    assert _status(db, "tokB")["unread"] == 1
    detail_sql = next(s for s in db.statements if "LEFT JOIN mail_recipients r ON r.message_id = m.id AND r.recipient_id = :me" in s)
    inbox_sql = next(s for s in db.statements if "FROM mail_recipients r" in s and "JOIN players s ON s.id = m.sender_id" in s)
    status_sql = next(s for s in db.statements if "AS unread" in s and "AS revision" in s)
    for needle, sql in (("r.recipient_id IS NOT NULL", detail_sql),
                        ("(m.sender_id = :me AND m.deleted_by_sender_at IS NULL)", detail_sql),
                        ("AND r.delivery = 'delivered'", inbox_sql), ("AND delivery = 'delivered'", status_sql)):
        assert needle in sql, needle
    naked = detail_sql.replace("r.recipient_id IS NOT NULL", "TRUE") \
                      .replace("(m.sender_id = :me AND m.deleted_by_sender_at IS NULL)", "TRUE")
    assert db._dispatch(naked, {"mid": UUID(res["id"]), "me": ids[D_SID]}).first() is not None
    listed = db._dispatch(inbox_sql.replace("AND r.delivery = 'delivered'", ""),
                          {"me": ids[B_SID], "c_at": None, "c_id": None, "lim": 25}).all()
    assert {str(r["id"]) for r in listed} == {res["id"], sup["id"]}
    assert db._dispatch(status_sql.replace("AND delivery = 'delivered'", ""), {"me": ids[B_SID]}).first()["unread"] == 2


# ── the wire contract, both halves grepped for the same literals ──────────

def _client_source(name):
    with open(os.path.join(PLUGIN_DIR, name), encoding="utf-8") as f:
        return f.read()


def test_client_parser_reads_the_keys_the_server_emits():
    """Every key the C# parser binds is emitted by the route it reads, on
    payloads produced by the routes themselves (so a rename on either side
    fails here)."""
    client_keys = set(re.findall(r'(?:Str|Raw|Int)\(m, "([a-z_]+)"\)', _client_source("MailClient.cs")))
    db, ids = _world()
    res = _send(db, [B_SID], cc=[C_SID], subject="Sub", body="Body")
    _run(main.mail_reply(res["id"], main._MailReplyReq(body="re", all=False, idempotency_key=str(uuid.uuid4())), _req("tokB"), db))
    _run(main.mail_block_add(main._MailBlockReq(steam_id=D_SID), _req("tokB"), db))
    payloads = {
        "inbox": _inbox(db, "tokB"),
        "sent": _run(main.mail_sent(_req("tokA"), "", 25, db)),
        "detail": _run(main.mail_detail(res["id"], _req("tokB"), db)),
        "status": _status(db, "tokB"),
        "blocks": _run(main.mail_blocks_list(_req("tokB"), db)),
    }

    def keys(o, out):
        if isinstance(o, dict):
            for k, v in o.items():
                out.add(k)
                keys(v, out)
        elif isinstance(o, list):
            for v in o:
                keys(v, out)
        return out
    server_keys = keys(payloads, set())
    required = {"messages", "next_cursor", "id", "thread_id", "kind", "sender", "steam_id", "name", "title_color",
                "subject", "created_at", "read_at", "addressees", "in_reply_to", "body", "to", "cc",
                "unread", "revision", "mail_from", "blocks"}
    assert required <= client_keys, sorted(required - client_keys)  # the client still reads each of them
    assert required <= server_keys, sorted(required - server_keys)  # and the server still emits each
    assert set(payloads["sent"]["messages"][-1]["addressees"][0]) == {"steam_id", "name", "kind"}
    assert set(payloads["status"]) == {"unread", "revision", "mail_from"}


def test_report_reason_bound_matches_the_client():
    """The client caps the free-text detail (MailUI.REPORT_DETAIL_MAX) under a
    fixed code prefix; the server REFUSES, never truncates, a reason over
    MAIL_REASON_MAX. The longest wire reason must fit, and the bound itself
    answers with its own code."""
    ui = _client_source("MailUI.cs")
    detail_max = int(re.search(r"REPORT_DETAIL_MAX = (\d+);", ui).group(1))
    codes = [c.strip().strip('"') for c in re.search(r"REPORT_CODES = \{ ([^}]*) \}", ui).group(1).split(",")]
    assert codes == ["spam", "harassment", "other"]
    assert max(len(c) for c in codes) + 2 + detail_max <= main.MAIL_REASON_MAX
    db, ids = _world()
    res = _send(db, [B_SID])
    reason = "harassment: " + "xy" * (detail_max // 2)
    ok = _run(main.mail_report(res["id"], main._MailReportReq(reason=reason), _req("tokB"), db))
    assert db.cases[UUID(ok["case_id"])]["evidence"]["reason"] == reason
    db2, _ids2 = _world()
    res2 = _send(db2, [B_SID])
    exact = "ab" * (main.MAIL_REASON_MAX // 2)
    assert _run(main.mail_report(res2["id"], main._MailReportReq(reason=exact), _req("tokB"), db2))["case_id"]
    db3, _ids3 = _world()
    res3 = _send(db3, [B_SID])
    exc = _raises(main.mail_report(res3["id"], main._MailReportReq(reason=exact + "c"), _req("tokB"), db3))
    assert (exc.status_code, exc.detail) == (400, "reason_too_long") and not db3.cases


def test_migration_300_matches_the_orm_and_the_readers():
    with open(os.path.join(SQL_DIR, "300_mail_inbox_rev.sql"), encoding="utf-8") as f:
        sql = f.read()
    assert "CREATE TABLE IF NOT EXISTS mail_inbox_rev" in sql and "ON CONFLICT (recipient_id) DO NOTHING" in sql
    assert sql.count("BEGIN;") == 1 and sql.count("COMMIT;") == 1
    cols = {c.name for c in models.MailInboxRev.__table__.columns}
    assert cols == {"recipient_id", "rev", "updated_at"} and all(c in sql for c in cols)
    assert models.MailInboxRev.__tablename__ == "mail_inbox_rev"
    assert "INSERT INTO mail_inbox_rev" in main._MAIL_REV_BUMP_SQL
    assert "FROM mail_inbox_rev" in inspect.getsource(main.mail_status)
    assert "DELETE FROM mail_inbox_rev" in inspect.getsource(main.delete_player_data)
    # review r2: the delivery trigger covers writers that predate this build
    # (the deploy window); statement-level, set-wise and sorted like the api's
    # own bump, installed after the backfill, rerun-safe, inside the one transaction
    fn_ddl = "CREATE OR REPLACE FUNCTION mail_inbox_rev_bump()"
    drop_ddl = "DROP TRIGGER IF EXISTS trg_mail_inbox_rev_bump ON mail_recipients;"
    trig_ddl = "CREATE TRIGGER trg_mail_inbox_rev_bump"
    assert sql.count(fn_ddl) == 1 and sql.count(drop_ddl) == 1 and sql.count(trig_ddl) == 1
    fn = sql[sql.index(fn_ddl):sql.index(drop_ddl)]
    for needle in ("INSERT INTO mail_inbox_rev (recipient_id, rev)", "FROM inserted", "WHERE delivery = 'delivered'",
                   "GROUP BY recipient_id", "ORDER BY recipient_id", "ON CONFLICT (recipient_id) DO UPDATE",
                   "SET rev = mail_inbox_rev.rev + EXCLUDED.rev", "RETURN NULL"):
        assert needle in fn, needle
    trig = sql[sql.index(trig_ddl):sql.index("COMMIT;")]
    for needle in ("AFTER INSERT ON mail_recipients", "REFERENCING NEW TABLE AS inserted", "FOR EACH STATEMENT",
                   "EXECUTE FUNCTION mail_inbox_rev_bump()"):
        assert needle in trig, needle
    assert sql.index("ON CONFLICT (recipient_id) DO NOTHING") < sql.index(fn_ddl) \
        < sql.index(drop_ddl) < sql.index(trig_ddl) < sql.index("COMMIT;")
    assert sql.index("BEGIN;") < sql.index("CREATE TABLE IF NOT EXISTS mail_inbox_rev")
    # review r3: the backfill is serialised against live writers — the table
    # lock is taken first, before the backfill it protects, inside the transaction
    lock = "LOCK TABLE mail_recipients IN SHARE ROW EXCLUSIVE MODE;"
    assert sql.count(lock) == 1
    assert sql.index("BEGIN;") < sql.index(lock) < sql.index("INSERT INTO mail_inbox_rev (recipient_id, rev)")
    # and the broadcast's persisted recipient count rides the same file
    assert "ALTER TABLE mail_messages ADD COLUMN IF NOT EXISTS recipient_count INTEGER" in sql
    assert "recipient_count" in {c.name for c in models.MailMessage.__table__.columns}
    assert "recipient_count" in inspect.getsource(main._mail_prior_send)
    assert "UPDATE mail_messages SET recipient_count" in inspect.getsource(main.admin_mail_broadcast)


# ── review r2 pins ────────────────────────────────────────────────────────

_LATTICE_TOMBSTONED = [  # route, whose row the racing deletion SCRUBS: the route completes and writes the tombstone it re-read
    ("grant", "actor"), ("revoke", "actor"), ("revoke", "target"),
    ("act_dismiss", "target"), ("act_dismiss_hmac", "target"),
]   # a case act's or a ban's ACTOR scrubbed meanwhile is refused instead (review r11): the next test but one
_LATTICE_ACTOR_REFUSED = ["act_mute", "act_dismiss", "act_dismiss_hmac", "ban"]


@pytest.mark.parametrize("route,victim", _LATTICE_TOMBSTONED, ids=[f"{r}-{v}" for r, v in _LATTICE_TOMBSTONED])
def test_a_scrub_under_the_lock_is_written_as_the_tombstone(route, victim):
    """review r2 HIGH (the dismiss and revoke targets) and MEDIUM (the
    actor's authority): every identity a route WRITES is the one it
    re-read under the lock. The scrub fires when the victim's OWN lock is
    granted — after the route's first read of that identity and before its
    re-read, the deletion that committed while the route waited — so a route
    locking only the other party would carry the raw id into its audit row
    and this stays red."""
    db, orig, case_id, actor, target = _lattice_world(route)
    if route == "revoke":
        db.bulk_grants[C_SID] = (40, NOW + timedelta(days=7))
    sid = actor if victim == "actor" else target
    tomb = {}

    def scrub_under_lock(locked):
        if locked == sid:
            tomb["v"] = db.scrub(sid)
    db.on_identity_lock = scrub_under_lock
    with _admin_secret():
        res = _run(_lattice_coro(db, route, orig, case_id))
    assert res["status"] == "ok" and "v" in tomb and db.commits == 1
    lock_i = next(i for i, s in enumerate(db.statements) if "pg_advisory_xact_lock(hashtext(:sid))" in s)
    reread_i = next(i for i, s in enumerate(db.statements) if "FROM players WHERE id = :pid FOR NO KEY UPDATE" in s)
    write_i = next(i for i, s in enumerate(db.statements) if _is_write(s))
    assert any("players" in s for s in db.statements[:lock_i])       # the route's first read of the identity precedes the lock ...
    assert lock_i < reread_i < write_i and ("identity", sid) in db.locks   # ... the re-read follows it, and every write follows the re-read
    written = json.dumps([db.admin_actions,
                          [c["resolved_by"] for c in db.cases.values()],
                          [(m["steam_id"], m.get("by")) for m in db.mutes],
                          sorted(db.bulk_grants)], default=str)
    assert sid not in written and tomb["v"] in written
    if route == "revoke" and victim == "target":
        assert res["revoked"] is False and C_SID not in db.bulk_grants   # the grant went with the account; the revoke still lands and is audited
    if route.startswith("act_"):
        assert db.cases[UUID(case_id)]["status"] in ("dismissed", "resolved")


def test_admin_without_a_players_row_acts_on_admin_users_authority():
    """review r2 MEDIUM: admin_users membership IS the authority. An admin
    who never ran the mod has no players row; grant, revoke and the case
    actions lock that row when it exists and skip it when it does not, and
    the audit actor is the admin's steam id. The broadcast is the one route
    that needs the row — it is the message's sender — and says so."""
    db, ids = _world()
    db.admins.add(ADMIN_SID)
    assert db.player_by_sid(ADMIN_SID) is None
    with _admin_secret():
        res = _run(main.admin_mail_bulk_grant(main._AdminMailBulkGrantReq(
            admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "mail_bulk_grant", A_SID),
            steam_id=A_SID, max_recipients=40, days=7), db))
        assert res["status"] == "ok" and db.bulk_grants[A_SID][0] == 40
        gone = _run(main.admin_mail_bulk_grant_revoke(A_SID, ADMIN_SID, _sign(ADMIN_SID, "mail_bulk_grant_revoke", A_SID), db))
        assert gone["revoked"] is True and A_SID not in db.bulk_grants
        case_id = _open_case(db, ids)
        req = main._AdminModCaseActReq(admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "modcase_act", case_id),
                                       action="dismiss")
        assert _run(main.admin_moderation_case_act(case_id, req, db=db))["status"] == "ok"
        case2 = _open_case(db, ids)
        req = main._AdminModCaseActReq(admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "modcase_act", case2),
                                       action="ban", reason="spam")
        assert _run(main.admin_moderation_case_act(case2, req, db=db))["resolution"] == "ban"
        exc = _raises(main.admin_mail_broadcast(_bcast_req(), db))
    assert (exc.status_code, exc.detail) == (404, "admin_player_unknown")
    assert db.cases[UUID(case_id)]["resolved_by"] == ADMIN_SID and db.cases[UUID(case2)]["resolved_by"] == ADMIN_SID
    assert [a["action"] for a in db.admin_actions] == ["mail_bulk_grant", "mail_bulk_grant_revoke", "modcase_act", "modcase_act"]
    assert {a["admin"] for a in db.admin_actions} == {ADMIN_SID}
    assert [type(o).__name__ for o in db.added] == ["PlayerBan", "AdminAction"] and db.added[0].banned_by_steam_id == ADMIN_SID
    assert ("identity", ADMIN_SID) in db.locks                        # the VALUE is still locked; there was simply no row to hold
    for fn in (main._mail_lock_admin, main._mail_lock_identities):
        assert "admin_identity_not_live" not in inspect.getsource(fn)
    # a grantee, by contrast, must be live: a cap is live authority
    with _admin_secret():
        exc = _raises(main.admin_mail_bulk_grant(main._AdminMailBulkGrantReq(
            admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "mail_bulk_grant", "76561198000000077"),
            steam_id="76561198000000077", max_recipients=40, days=7), db))
        assert (exc.status_code, exc.detail) == (404, "player_unknown")
        exc = _raises(main.admin_mail_bulk_grant_revoke("76561198000000077", ADMIN_SID,
                                                        _sign(ADMIN_SID, "mail_bulk_grant_revoke", "76561198000000077"), db))
        assert (exc.status_code, exc.detail) == (404, "player_unknown")


class _match_secret:
    """MATCH_HMAC_SECRET salts the deletion ledger's hashes (main._hash_steam_id)
    and gates its readers — _is_steam_id_purged answers False without it."""
    def __enter__(self):
        self._old = main.MATCH_HMAC_SECRET
        main.MATCH_HMAC_SECRET = "test-match-secret"
        return self

    def __exit__(self, *exc):
        main.MATCH_HMAC_SECRET = self._old
        return False


def test_a_deleted_admin_is_refused_while_a_never_created_one_acts():
    """review r3 MEDIUM: `optional` tolerates an identity that never had a
    players row, not one whose row was scrubbed. A deleted admin still listed
    in admin_users has no row under the raw id (the scrub rewrote it to the
    tombstone) and IS in the deletion ledger: every admin route refuses
    (403 account_deleted) under the identity lock, writes no audit row, and
    the raw id appears nowhere. Negative control: the same admin with the
    ledger entry gone is indistinguishable from never-created, and acts."""
    db, ids = _world()
    db.add_player(ADMIN_SID)
    db.admins.add(ADMIN_SID)
    with _admin_secret(), _match_secret():
        db.scrub(ADMIN_SID)
        assert db.player_by_sid(ADMIN_SID) is None and main._hash_steam_id(ADMIN_SID) in db.purged_hashes
        case_id = _open_case(db, ids)
        db.statements.clear()
        grant = main._AdminMailBulkGrantReq(admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "mail_bulk_grant", A_SID),
                                            steam_id=A_SID, max_recipients=40, days=7)
        act = main._AdminModCaseActReq(admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "modcase_act", case_id),
                                       action="dismiss")
        for coro in (main.admin_mail_bulk_grant(grant, db),
                     main.admin_mail_bulk_grant_revoke(A_SID, ADMIN_SID, _sign(ADMIN_SID, "mail_bulk_grant_revoke", A_SID), db),
                     main.admin_moderation_case_act(case_id, act, db=db),
                     main.admin_mail_broadcast(_bcast_req(), db)):
            exc = _raises(coro)
            assert (exc.status_code, exc.detail) == (403, "account_deleted")
        lock_i = next(i for i, s in enumerate(db.statements) if "pg_advisory_xact_lock(hashtext(:sid))" in s)
        ledger_i = next(i for i, s in enumerate(db.statements) if "FROM deleted_steam_ids" in s)
        assert lock_i < ledger_i                                          # read under the lock, after it
        assert not db.admin_actions and A_SID not in db.bulk_grants
        assert db.cases[UUID(case_id)]["status"] not in ("dismissed", "resolved")
        assert ADMIN_SID not in json.dumps(db.admin_actions) and ADMIN_SID not in json.dumps(list(db.cases.values()), default=str)
        # negative control (#391): no ledger entry = never-created = admin_users authority suffices
        db.purged_hashes.clear()
        assert _run(main.admin_mail_bulk_grant(grant, db))["status"] == "ok" and db.bulk_grants[A_SID][0] == 40
        assert db.admin_actions[-1]["admin"] == ADMIN_SID


def test_a_revoke_target_deleted_before_the_lookup_is_refused_without_an_audit_row():
    """review r3, the class behind MEDIUM 2 (#432): the same rule for a
    tolerated TARGET. A grantee scrubbed BEFORE the route looked it up has no
    row under the raw id; the revoke refuses on the ledger instead of
    landing with the raw id in the audit row's target column. (Scrubbed
    while the route WAITED, it lands with the tombstone — the r2 pin.)"""
    db, ids = _world()
    db.add_player(ADMIN_SID)
    db.admins.add(ADMIN_SID)
    with _admin_secret(), _match_secret():
        res = _run(main.admin_mail_bulk_grant(main._AdminMailBulkGrantReq(
            admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "mail_bulk_grant", C_SID),
            steam_id=C_SID, max_recipients=40, days=7), db))
        assert res["status"] == "ok" and len(db.admin_actions) == 1
        db.scrub(C_SID)
        exc = _raises(main.admin_mail_bulk_grant_revoke(C_SID, ADMIN_SID, _sign(ADMIN_SID, "mail_bulk_grant_revoke", C_SID), db))
    assert (exc.status_code, exc.detail) == (403, "account_deleted")
    assert len(db.admin_actions) == 1 and C_SID not in json.dumps(db.admin_actions)


def test_broadcast_bump_is_inside_the_sending_transaction():
    """review r3 pin audit: the direct-send pin leaves a broadcast whose
    revision bump moved after commit green, so the broadcast's own bump is
    pinned the same way — after its fan-out, before its commit, no commit
    between the two."""
    db, ids = _world()
    db.add_player(ADMIN_SID)
    db.admins.add(ADMIN_SID)
    with _admin_secret():
        first = _broadcast(db)
    fan_i = next(i for i, s in enumerate(db.statements) if "INSERT INTO mail_recipients" in s)
    bump_i = next(i for i, s in enumerate(db.statements) if "INSERT INTO mail_inbox_rev" in s)
    mark = next(m for m in db.commit_marks if m > bump_i)
    assert fan_i < bump_i < mark and not any(fan_i < m <= bump_i for m in db.commit_marks)
    assert first["recipients"] == 4 and sum(db.inbox_rev.values()) == first["recipients"]


def _first_acquisitions(locks):
    seen, out = set(), []
    for lock in locks:
        if lock not in seen:
            seen.add(lock)
            out.append(lock)
    return out


def test_every_ban_path_takes_the_identity_locks_before_the_ban_rate_lock():
    """review r2 MEDIUM: one lock order on both ban paths — the identity
    lattice (both ids, canonical order) first, the per-admin ban-rate lock
    after — recorded as the fake grants them. Inverse orders on the two
    paths would let two concurrent bans by one admin wait on each other."""
    db, ids = _world()
    db.add_player(ADMIN_SID, discord_id="d-admin")
    db.admins.add(ADMIN_SID)
    with _admin_secret():
        res = _run(main.admin_ban(main._AdminBanReq(admin_steam_id=ADMIN_SID, target_steam_id=A_SID, reason="x",
                                                    hmac_signature=_sign(ADMIN_SID, "ban", A_SID)), db=db))
    assert res["status"] == "banned"
    plain = _first_acquisitions(db.locks)
    db2, ids2 = _world()
    case_id = _open_case(db2, ids2)
    db2.add_player(ADMIN_SID, discord_id="d-admin")
    db2.admins.add(ADMIN_SID)
    db2.locks.clear()
    assert _act_internal(db2, case_id, "d-admin", "ban")["resolution"] == "ban"
    case = _first_acquisitions(db2.locks)
    expected = [("identity", s) for s in sorted((ADMIN_SID, A_SID))] + [("ban-rate", ADMIN_SID)]
    assert plain == expected and case == expected
    for locks in (db.locks, db2.locks):
        rate_i = locks.index(("ban-rate", ADMIN_SID))
        assert {v for k, v in locks if k == "identity"} == {v for k, v in locks[:rate_i] if k == "identity"}
    # the ordinary route keeps the shared helpers, and the lattice call precedes the gate in its source too
    src = inspect.getsource(main.admin_ban)
    assert src.index("_mail_lock_identities(") < src.index("_ban_rate_gate_or_raise(") < src.index("_apply_ban_core(")
    act = inspect.getsource(main._moderation_case_act)
    assert act.index("_mail_lock_identities(") < act.index("_ban_rate_gate_or_raise(")
    # the unban is on the same lattice, ahead of its write (r9 M2)
    unban = inspect.getsource(main.admin_unban)
    assert unban.index("_require_admin(") < unban.index("_mail_lock_identities(") < unban.index("UPDATE player_bans")
    assert "optional=(req.admin_steam_id, req.target_steam_id)" in unban
    # ...and writes the identities the lattice re-read, never its inputs (r10 M1)
    assert "rows = await _mail_lock_identities(" in unban
    assert unban.index("_mail_identity_to_write(rows, req.admin_steam_id)") < unban.index("UPDATE player_bans")
    assert unban.index("_mail_identity_to_write(rows, req.target_steam_id)") < unban.index("UPDATE player_bans")
    # ...and every ban-family actor must be live after the re-read, before the gate and the writes (r11 M1/M4);
    # the rate refusal receives the re-read target for its audit and alert (r11 M2)
    assert src.index("_mail_lock_identities(") < src.index("_mail_actor_live_or_raise(rows, req.admin_steam_id)") < src.index("_ban_rate_gate_or_raise(")
    assert "target_w=target_w" in src
    assert act.index("_mail_lock_identities(") < act.index("_mail_actor_live_or_raise(rows, actor_steam_id)") < act.index("_ban_rate_gate_or_raise(")
    assert "_ban_rate_gate_or_raise(db, actor_steam_id, subject_sid_pre, target_w=subject_sid)" in act
    assert unban.index("_mail_lock_identities(") < unban.index("_mail_actor_live_or_raise(rows, req.admin_steam_id)") < unban.index("UPDATE player_bans")


def test_a_repeat_ban_at_the_velocity_threshold_is_answered_already_banned_by_the_route():
    """r9 (D4, 2026-09-13), executed through the route on the fake: the retry of a ban whose caller
    timed out finds its target banned -- the route answers already_banned, taking no ban-rate lock
    and refusing nothing, however many bans the admin has in the window; the identity lattice is
    still taken first."""
    db, ids = _world()
    db.add_player(ADMIN_SID, discord_id="d-admin")
    db.admins.add(ADMIN_SID)
    db.bans[A_SID] = "x"
    db.recent_bans_by_admin[ADMIN_SID] = 5
    with _admin_secret():
        res = _run(main.admin_ban(main._AdminBanReq(admin_steam_id=ADMIN_SID, target_steam_id=A_SID, reason="x",
                                                    hmac_signature=_sign(ADMIN_SID, "ban", A_SID)), db=db))
    assert res["status"] == "already_banned"
    assert ("ban-rate", ADMIN_SID) not in db.locks and ("identity", A_SID) in db.locks


def test_broadcast_replay_precedes_the_mutable_sender_gates():
    """review r2 MEDIUM: a retry of a broadcast that already went out gets
    the stored answer even after its sender was muted or banned; a NEW key
    after the mute is refused (negative control)."""
    db, ids = _world()
    db.add_player(ADMIN_SID)
    db.admins.add(ADMIN_SID)
    key = str(uuid.uuid4())
    with _admin_secret():
        first = _broadcast(db, key=key)
        idem_i = next(i for i, s in enumerate(db.statements) if "idempotency_key = :key" in s)
        gate_i = next(i for i, s in enumerate(db.statements) if "SELECT reason FROM player_bans" in s or "FROM chat_mutes" in s)
        assert idem_i < gate_i                                       # at runtime the replay lookup ran before the first gate read
        db.mutes.append({"steam_id": ADMIN_SID, "channel": None, "revoked_at": None, "expires_at": None})
        assert _broadcast(db, key=key) == first                      # muted since: the stored 200, not a 403
        db.bans[ADMIN_SID] = "spam"
        assert _broadcast(db, key=key) == first                      # banned since: still the stored 200
        exc = _raises(main.admin_mail_broadcast(_bcast_req(), db))
    assert (exc.status_code, exc.detail) == (403, "banned")           # a NEW key meets the gates
    assert len([m for m in db.messages.values() if m["kind"] == "system_broadcast"]) == 1
    src = inspect.getsource(main.admin_mail_broadcast)
    assert src.index("_mail_lock_admin(") < src.index("_mail_lock_sender(") < src.index("_mail_prior_send(") \
        < src.index("_mail_sender_gates(") < src.index("_mail_text_or_raise(")


def test_rate_wait_is_the_maximum_across_exhausted_windows_and_rounds_up():
    """review r2 MEDIUM (M12): with BOTH windows closed the day's wait is
    advertised, not the minute's; a fractional wait rounds UP (a wait of 30
    for 30.5 s invites one refused retry). The fake rounds the way each SQL
    expression says, so a CEIL-to-FLOOR edit turns this red."""
    db, ids = _world()
    for _ in range(90):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], created_at=NOW - timedelta(hours=2))
    for _ in range(10):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], created_at=NOW - timedelta(seconds=30))
    exc = _send_raises(db, to=[B_SID])                               # 100 today, 10 this minute: both closed
    assert exc.detail == {"error": "rate_limited", "retry_after": 22 * 3600} and exc.headers["Retry-After"] == str(22 * 3600)
    db, ids = _world()
    for _ in range(10):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], created_at=NOW - timedelta(seconds=29.5))
    exc = _send_raises(db, to=[B_SID])
    assert exc.detail["retry_after"] == 31 and exc.headers["Retry-After"] == "31"
    rate_sql = next(s for s in db.statements if "AS per_minute" in s)
    assert rate_sql.count("CEIL(EXTRACT") == 2 and "FLOOR(" not in rate_sql
    floored = db._dispatch(rate_sql.replace("CEIL(EXTRACT", "FLOOR(EXTRACT"), {"sid": ids[A_SID]}).first()
    assert floored["minute_wait"] == 30                              # control: the fake follows the SQL's rounding
    src = inspect.getsource(main._mail_rate_or_raise)
    assert "max(waits)" in src and "elif per_day" not in src


def test_client_plaintext_admission_covers_every_rfc1918_range():
    """review r2: the C# admission expression, evaluated as written, admits
    10/8, 172.16/12, 192.168/16 and loopback and nothing else; without its
    172 clause the same evaluator refuses 172.16 (negative control)."""
    src = _client_source("ApiClient.cs")
    fn = src[src.index("private static bool CredentialedTransportAllowed"):]
    fn = fn[:fn.index("private static bool _loggedTokenWithheld")]
    expr = re.search(r"return\s+(\(b\[0\][^;]*);", fn).group(1)
    py = " ".join(expr.replace("&&", " and ").replace("||", " or ").split())
    assert re.fullmatch(r"[\sb\[\]0-9()=<>andor]+", py), py          # only the byte tests survive into eval

    def admitted(text_expr, *octets):
        return bool(eval(text_expr, {"__builtins__": {}}, {"b": octets}))   # noqa: S307 — the vetted C# expression
    for ip in ((10, 0, 0, 1), (10, 255, 255, 255), (172, 16, 0, 1), (172, 31, 255, 255),
               (192, 168, 72, 102), (192, 168, 0, 1), (127, 0, 0, 1)):
        assert admitted(py, *ip), ip
    for ip in ((172, 15, 255, 255), (172, 32, 0, 1), (8, 8, 8, 8), (100, 64, 0, 1), (169, 254, 1, 1),
               (192, 169, 0, 1), (11, 0, 0, 1), (1, 1, 1, 1)):
        assert not admitted(py, *ip), ip
    without = py.replace("(b[0] == 172 and b[1] >= 16 and b[1] <= 31)", "False")
    assert without != py and not admitted(without, 172, 16, 0, 1) and admitted(without, 10, 0, 0, 1)


def test_client_selftest_count_and_fingerprint_structure():
    """review r2 M7: the idempotency fingerprint length-prefixes every field
    (the collision vector runs in the launch self-test), and the self-test's
    expected count equals the cases wired, so the in-game summary cannot
    read PASS with a case missing."""
    mc = _client_source("MailClient.cs")
    selftest = mc[mc.index("internal static int SelfTest("):]
    selftest = selftest[:selftest.index("fail = failCount;")]
    n = int(re.search(r"SELFTEST_CASES = (\d+);", mc).group(1))
    assert selftest.count('Case("') == n
    assert "MailUI.FingerprintOf(" in selftest and 'Case("fingerprint_fields_do_not_collide"' in selftest
    ui = _client_source("MailUI.cs")
    fp = ui[ui.index("internal static string FingerprintOf("):]
    fp = fp[:fp.index("private static void DiscardCurrent")]
    assert "Append(v.Length.ToString(CultureInfo.InvariantCulture)).Append(':').Append(v).Append(';')" in fp
    assert fp.count("FpField(sb, ") >= 8 and "'|'" not in fp and '"|"' not in fp
    caller = ui[ui.index("private static string Fingerprint(bool reply, string subj, string body)"):ui.index("internal static string FingerprintOf(")]
    assert "FingerprintOf(reply, cReplyToId, cReplyAll, to, cc, subj, body)" in caller


@pytest.mark.parametrize("route", _LATTICE_ACTOR_REFUSED)
def test_an_actor_whose_deletion_committed_under_the_lock_is_refused(route):
    """review r11 (2026-09-13): the ACTOR of a case act or a ban is re-read under the lock like every
    identity; when the actor's own deletion committed while the route waited (the hook fires as the
    lock is granted), the route is refused 403 account_deleted before its first write -- the ban row's
    banned_by references the raw admin_users id, and a deleted account does not act. r2's
    tombstone-audit behaviour stays for the mail admin routes (grant, revoke) and for a deleted SUBJECT."""
    db, orig, case_id, actor, target = _lattice_world(route)
    tomb = {}

    def scrub_under_lock(locked):
        if locked == actor:
            tomb["v"] = db.scrub(actor)
    db.on_identity_lock = scrub_under_lock
    with _admin_secret():
        exc = _raises(_lattice_coro(db, route, orig, case_id))
    assert (exc.status_code, exc.detail) == (403, "account_deleted") and "v" in tomb
    assert db.commits == 0
    reread_i = next(i for i, s in enumerate(db.statements) if "FROM players WHERE id = :pid FOR NO KEY UPDATE" in s)
    assert not any(_is_write(s) for s in db.statements[reread_i:])
    written = json.dumps([db.admin_actions, [c["resolved_by"] for c in db.cases.values()], sorted(db.bans)], default=str)
    assert tomb["v"] not in written and target not in db.bans


def test_a_rate_refusal_audits_the_target_the_lattice_re_read():
    """review r11 M2 (2026-09-13), executed through the route on the fake: the target's deletion commits
    while the ban waits for its lock; the velocity refusal looks the target up by the raw id and audits
    and alerts the tombstone it re-read -- never the id the scrub removed."""
    db, ids = _world()
    db.add_player(ADMIN_SID, discord_id="d-admin")
    db.admins.add(ADMIN_SID)
    db.recent_bans_by_admin[ADMIN_SID] = 5
    tomb = {}

    def scrub_under_lock(locked):
        if locked == A_SID:
            tomb["v"] = db.scrub(A_SID)
    db.on_identity_lock = scrub_under_lock
    with _admin_secret():
        exc = _raises(main.admin_ban(main._AdminBanReq(admin_steam_id=ADMIN_SID, target_steam_id=A_SID, reason="x",
                                                       hmac_signature=_sign(ADMIN_SID, "ban", A_SID)), db=db))
    assert exc.status_code == 429 and "v" in tomb
    blocked = [a for a in db.admin_actions if a["action"] == "ban_rate_blocked"]
    assert len(blocked) == 1 and (blocked[0]["admin"], blocked[0]["target"]) == (ADMIN_SID, tomb["v"])
    assert len(db.outbox) == 1 and tomb["v"] in db.outbox[0][1] and A_SID not in db.outbox[0][1]
    assert A_SID not in db.bans
