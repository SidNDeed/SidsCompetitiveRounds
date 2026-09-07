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
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy.sql.elements import TextClause

import main

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

    # session protocol ----------------------------------------------------
    def begin_nested(self):
        return _Savepoint()

    async def commit(self):
        self.commits += 1

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
        return self._dispatch(sql, params)

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
        # locks
        if "pg_advisory_xact_lock(hashtext('mail:'" in sql:
            self.locks.append(("mail", params["sid"]))
            return _Res([(1,)])
        if "pg_advisory_xact_lock(hashtext('ban-rate:'" in sql:
            self.locks.append(("ban-rate", params["adm"]))
            return _Res([(1,)])
        if "pg_advisory_xact_lock(hashtext(:sid))" in sql:
            self.locks.append(("identity", params["sid"]))
            return _Res([(1,)])
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
        # spam evaluation (before the bare censor count: it embeds the same text)
        if "AS same_body" in sql:
            for needle in ("HAVING COUNT(DISTINCT r.recipient_id) > CAST(:bulk_n AS integer)",
                           "make_interval(hours => 1)", "make_interval(days => 1)"):
                assert needle in sql, f"spam query lost: {needle}"
            sid = params["sid"]
            mine = [m for m in self.messages.values() if m["sender_id"] == sid and m["kind"] == "direct"
                    and m["created_at"] > NOW - timedelta(days=1)]
            same = sum(1 for m in mine if main._mail_norm_body(m["body"]) == params["norm"])
            bulk = 0
            for m in mine:
                if m["created_at"] <= NOW - timedelta(hours=1):
                    continue
                n = len({rid for (mid, rid) in self.recipients if mid == m["id"]})
                if n > int(params["bulk_n"]):
                    bulk += 1
            hits = sum(1 for h in self.censor_hits if h["sender_id"] == sid
                       and h["created_at"] > NOW - timedelta(days=1))
            return _Res([{"same_body": same, "bulk_hour": bulk, "censor_hits": hits}])
        if "SELECT COUNT(*) FROM mail_censor_hits" in sql:
            return _Res([(sum(1 for h in self.censor_hits if h["sender_id"] == params["sid"]
                              and h["created_at"] > NOW - timedelta(days=1)),)])
        # idempotency + rate
        if "FROM mail_messages WHERE sender_id = :sid AND idempotency_key = :key" in sql:
            hit = [m for m in self.messages.values()
                   if m["sender_id"] == params["sid"] and m["idempotency_key"] == params["key"]]
            return _Res([(hit[0]["id"],)] if hit else [])
        if "AS per_minute" in sql:
            assert "kind = 'direct'" in sql, "rate window must ignore broadcasts"
            mine = [m for m in self.messages.values() if m["sender_id"] == params["sid"]
                    and m["kind"] == "direct" and m["created_at"] > NOW - timedelta(days=1)]
            return _Res([{"per_minute": sum(1 for m in mine if m["created_at"] > NOW - timedelta(minutes=1)),
                          "per_day": len(mine)}])
        # message insert + fan-out
        if "INSERT INTO mail_messages" in sql:
            kind = "system_broadcast" if "'system_broadcast'" in sql else "direct"
            mid = params["id"]
            assert mid not in self.messages
            self.messages[mid] = {"id": mid, "sender_id": params["sid"], "kind": kind,
                                  "thread_id": params.get("tid", mid) if kind == "direct" else mid,
                                  "in_reply_to": params.get("irt"), "subject": params["subj"],
                                  "body": params["body"], "idempotency_key": params["key"],
                                  "created_at": self.message_created_at, "deleted_by_sender_at": None}
            return _Res()
        if "INSERT INTO mail_recipients" in sql and "unnest(" in sql:
            for needle in FANOUT_PREDICATES:
                assert needle in sql, f"fan-out lost predicate: {needle}"
            assert "ranked_series" not in sql, "ranked_series is not proof of play (B-13)"
            assert "INSERT INTO mail_recipients" in sql and sql.count("INSERT INTO") == 1
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
            self.outbox.append((params["ch"], params["c"]))
            return _Res()
        if "INSERT INTO admin_actions" in sql:
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
            m = self.messages.get(params["mid"])
            if m is None:
                return _Res([])
            ok = (m["sender_id"] == params["me"] and m["deleted_by_sender_at"] is None) \
                or self._visible_to(m["id"], params["me"])
            return _Res([m] if ok else [])
        if "SELECT recipient_id, kind FROM mail_recipients" in sql:
            assert "delivery = 'delivered'" in sql, "reply-all must derive from DELIVERED envelopes"
            return _Res([{"recipient_id": rid, "kind": env["kind"]} for (mid, rid), env in self.recipients.items()
                         if mid == params["mid"] and env["delivery"] == "delivered"])
        if "LEFT JOIN mail_recipients r ON r.message_id = m.id AND r.recipient_id = :me" in sql:
            m = self.messages.get(params["mid"])
            if m is None:
                return _Res([])
            env = self.recipients.get((m["id"], params["me"]))
            visible_env = env if (env and env["delivery"] == "delivered" and env["deleted_at"] is None) else None
            as_sender = m["sender_id"] == params["me"] and m["deleted_by_sender_at"] is None
            if visible_env is None and not as_sender:
                return _Res([])
            row = dict(m)
            row.update(self._sender_row(self.players[m["sender_id"]]))
            row["read_at"] = visible_env["read_at"] if visible_env else None
            return _Res([row])
        if "JOIN mail_recipients r ON r.message_id = m.id AND r.recipient_id = :me" in sql \
                and "s.display_name AS sender_name" in sql:
            m = self.messages.get(params["mid"])
            env = self.recipients.get((params["mid"], params["me"])) if m else None
            if m is None or env is None or env["delivery"] != "delivered":
                return _Res([])
            row = dict(m)
            row.update(self._sender_row(self.players[m["sender_id"]]))
            return _Res([row])
        if "FROM mail_recipients r" in sql and "JOIN mail_messages m ON m.id = r.message_id" in sql \
                and "JOIN players s ON s.id = m.sender_id" in sql:
            rows = []
            for (mid, rid), env in self.recipients.items():
                if rid != params["me"] or env["delivery"] != "delivered" or env["deleted_at"] is not None:
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
        if "AS unread" in sql and "AS revision" in sql:
            assert "read_at IS NULL AND deleted_at IS NULL" in sql
            mine = [(mid, env) for (mid, rid), env in self.recipients.items()
                    if rid == params["me"] and env["delivery"] == "delivered"]
            unread = sum(1 for _mid, env in mine if env["read_at"] is None and env["deleted_at"] is None)
            newest = sorted((self.messages[mid] for mid, _e in mine),
                            key=lambda m: (m["created_at"], m["id"]), reverse=True)
            return _Res([{"unread": unread, "revision": newest[0]["id"] if newest else None}])
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
    assert set(res) == set(control) and res["accepted"] is True     # identical response shape
    assert _env(db, res["id"], ids[B_SID])["delivery"] == "suppressed"
    assert [x["id"] for x in _inbox(db, "tokB")["messages"]] == [control["id"]]
    st = _status(db, "tokB")
    assert st["unread"] == 1 and st["revision"] == control["id"]
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
    assert lock_i < idem_i < ins_i
    assert db.locks == [("mail", ids[A_SID])]
    for fn in (main.mail_send, main.mail_reply):
        src = inspect.getsource(fn)
        assert src.index("_mail_lock_sender(") < src.index("_mail_prior_send(") < src.index("_mail_sender_gates(")
    assert "pg_advisory_xact_lock(hashtext('mail:' || CAST(:sid AS text)))" in inspect.getsource(main._mail_lock_sender)
    assert res["accepted"] is True


# ── limits ────────────────────────────────────────────────────────────────

def test_rate_limits_10_per_minute_and_100_per_day():
    db, ids = _world()
    for _ in range(9):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], created_at=NOW - timedelta(seconds=30))
    assert _send(db, [B_SID])["accepted"] is True                    # the 10th is fine
    exc = _send_raises(db, to=[B_SID])                               # the 11th in a minute
    assert exc.status_code == 429 and exc.detail == {"error": "rate_limited", "retry_after": 60}
    assert exc.headers["Retry-After"] == "60"
    db, ids = _world()
    for _ in range(99):
        db.seed_message(ids[A_SID], [(ids[B_SID], "to", "delivered")], created_at=NOW - timedelta(hours=2))
    assert _send(db, [B_SID])["accepted"] is True                    # the 100th
    exc = _send_raises(db, to=[B_SID])
    assert exc.detail == {"error": "rate_limited", "retry_after": 3600}
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
    assert again["id"] == res["id"] and len(db.messages) == 1
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
    return _run(main.internal_moderation_case_act(case_id, payload, "internal-key", db))


@pytest.fixture(autouse=True)
def _internal_key(monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "internal-key")


def test_act_with_a_stale_grant_is_403_and_writes_nothing():
    db, ids = _world()
    case_id = _open_case(db, ids)
    db.add_player(MOD_SID, discord_id="d-mod")                       # linked, but holds NO grant
    before = (len(db.admin_actions), len(db.mutes), dict(db.bans))
    exc = _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-mod", "action": "mute", "hours": 24},
                                                    "internal-key", db))
    assert exc.status_code == 403 and exc.detail == "not_authorised"
    assert (len(db.admin_actions), len(db.mutes), dict(db.bans)) == before
    assert db.cases[UUID(case_id)]["status"] == "open"
    assert _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "nobody", "action": "dismiss"},
                                                     "internal-key", db)).detail == "not_linked"
    assert _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-mod", "action": "dismiss"},
                                                     "wrong-key", db)).status_code == 403
    # a language moderator may dismiss but not mute or ban (a mail mute is global, admin-only)
    db.mod_grants[MOD_SID] = ["ru"]
    assert _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-mod", "action": "mute", "hours": 24},
                                                     "internal-key", db)).detail == "admin_required"
    assert _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-mod", "action": "ban"},
                                                     "internal-key", db)).detail == "admin_required"
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
                                                     "internal-key", db)).status_code == 404
    assert _raises(main.internal_moderation_case_act(case_id, {"actor_discord_id": "d-admin", "action": "nuke"},
                                                     "internal-key", db)).detail == "action_invalid"


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
        assert _raises(main.admin_moderation_case_act(cid2, req, db2)).detail == "actor_mismatch"
        req = main._AdminModCaseActReq(admin_steam_id=ADMIN_SID, hmac_signature=_sign(ADMIN_SID, "modcase_act", cid2),
                                       action="dismiss")
        assert _run(main.admin_moderation_case_act(cid2, req, db2))["status"] == "ok"
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
    assert st == {"unread": 2, "revision": m2, "mail_from": "everyone"}
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
    assert st["unread"] == 0 and st["revision"] == m2                # deleting the newest never moves it back
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
    for stmt in ("DELETE FROM mail_recipients WHERE recipient_id = :pid",
                 "DELETE FROM mail_blocks WHERE blocker_id = :pid OR blocked_id = :pid",
                 "UPDATE moderation_cases SET reporter_id = NULL WHERE reporter_id = :pid",
                 "DELETE FROM mail_bulk_grants WHERE steam_id = :sid",
                 "DELETE FROM mail_censor_hits WHERE sender_id = :pid"):
        assert src.count(stmt) == 1, stmt
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
