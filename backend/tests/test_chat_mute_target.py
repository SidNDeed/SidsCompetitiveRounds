"""v4.13 (review r14), the chat mute target. /chat/moderate/mute and /unmute accepted any target string, keyed
chat_mutes on its first thirty-two characters and reported the full string in the audit row, the log line and the
response, so a longer target muted a different identity than every record of the action named. Now both routes use
the moderation target's domain -- main._mod_target_ok, one to twenty ASCII digits, the whole string, the one domain
the ban family uses (integrator decision D-f) -- and one unsliced string throughout:
  * the mute route checks its target with _mod_target_or_422 as its first statement, and the shared write core
    checks its key the same way before either of its statements;
  * the unmute route, as the unban does, calls _mod_release_or_422 after its UPDATE: a target outside the domain is
    refused when the UPDATE revoked no row and admitted when it revoked one, so a row stored under such a key stays
    revocable;
  * every chat_mutes key is bound unsliced.
The routes are driven through FastAPI's request stack (the body model, the Query bound on the admin-actions filter,
the dependency override), with the database scripted and the identity proof stubbed."""
import ast
import asyncio
import inspect

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import main

ADMIN, MOD = "76561198000000009", "76561198000000007"
DETAIL = "target_steam_id must be a numeric steam id"
# PostgreSQL evaluated `v ~ '^[0-9]{1,20}$'` (the domain anchored at both ends) for each value below on the primary,
# 2026-09-15 00:28 UTC: true for GOOD, false for BAD. GOOD: a Steam id, the twenty-digit bound, one digit. BAD: one
# digit past the bound (the r14 case), chat_mutes' width and one past it, empty, a space either side, a trailing
# newline, a letter, a colon, Arabic-Indic digits, fullwidth digits, a photon_ id, a leading newline, CR LF.
GOOD = ("76561198000000008", "12345678901234567890", "1")
BAD = ("7" * 21, "7" * 32, "7" * 33, "", " 76561198000000008", "76561198000000008 ", "76561198000000008\n",
       "7656119800000000x", "76561198000000008:ru", chr(0x0667) * 17, chr(0xFF11) + chr(0xFF12), "photon_1", "\n1",
       "1\r\n")
# the BAD values a chat_mutes row can carry as its key (steam_id VARCHAR(32) NOT NULL, migration 192)
LEGACY = tuple(b for b in BAD if 1 <= len(b) <= 32)
# the unmute's three arms: (actor, channel, a fragment only that arm's UPDATE has, the log line's scope label)
ARMS = ((ADMIN, "ru", "AND channel = :chan", "ru"),
        (ADMIN, None, "revoked_at IS NULL RETURNING id", "their scope"),
        (MOD, None, "channel = ANY(:chans)", "their scope"))


class _Res:
    def __init__(self, rows=(), scalar=None):
        self._rows, self._scalar = list(rows), scalar

    def scalars(self):
        return self

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._scalar


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Db:
    """Logs every statement as normalised SQL with a copy of its binds. An UPDATE ... RETURNING id revokes
    `released` rows (one unless told otherwise) and a COUNT is zero."""

    def __init__(self, released=1):
        self.log, self.committed, self.released = [], 0, released

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.log.append((sql, dict(params or {})))
        if "RETURNING id" in sql:
            return _Res(rows=list(range(1, self.released + 1)))
        if sql.startswith("SELECT COUNT(*)"):
            return _Res(scalar=0)
        return _Res()

    def begin_nested(self):
        return _Nested()

    async def commit(self):
        self.committed += 1

    def binds(self, fragment, key):
        return [p.get(key) for sql, p in self.log if fragment in sql]


def _client(monkeypatch):
    seen = {"scope": [], "hmac": [], "session": []}
    holder = {"db": None}

    async def scope(_db, sid):
        seen["scope"].append(sid)
        return {ADMIN: ("admin", None), MOD: ("moderator", {"ru"})}.get(sid, (None, None))

    def hmac_ok(sid, action, target, sig):
        seen["hmac"].append((action, target))
        return True

    async def session_ok(request, sid, _db):
        seen["session"].append(sid)

    async def admin_ok(_db, adm, action, target, sig):
        seen["hmac"].append((action, target))

    monkeypatch.setattr(main, "_chat_moderator_scope", scope)
    monkeypatch.setattr(main, "_verify_admin_hmac", hmac_ok)
    monkeypatch.setattr(main, "_check_steam_session", session_ok)
    monkeypatch.setattr(main, "_require_admin", admin_ok)
    app = FastAPI()
    app.add_api_route("/mute", main.chat_moderate_mute, methods=["POST"])
    app.add_api_route("/unmute", main.chat_moderate_unmute, methods=["POST"])
    app.add_api_route("/actions", main.admin_list_actions, methods=["GET"])

    async def fake_db():
        yield holder["db"]
    app.dependency_overrides[main.get_db] = fake_db
    return TestClient(app), seen, holder


def _body(actor, target, chan):
    return {"steam_id": actor, "target_steam_id": target, "channel": chan,
            "duration_minutes": None, "reason": "", "hmac_signature": "sig"}


def _clear(seen):
    for v in seen.values():
        v.clear()


def test_a_chat_mute_target_outside_the_domain_is_refused_before_any_read_signature_or_write(monkeypatch, capsys):
    """Every refused shape answers the mute with 422 and the check's own detail (not FastAPI's body validation) --
    with no channel, a valid channel and an unknown one, so the target is checked before the channel is -- and
    nothing else happens: no statement, no commit, no identity proof, no scope read, no log line, so no chat_mutes
    row and no audit row. The shared write core refuses the same values before its first statement, for a caller
    that reaches it without the route."""
    client, seen, holder = _client(monkeypatch)
    for bad in BAD:
        for chan in (None, "ru", "xx"):
            holder["db"] = db = _Db()
            _clear(seen)
            r = client.post("/mute", json=_body(ADMIN, bad, chan))
            assert r.status_code == 422 and r.json() == {"detail": DETAIL}, (chan, bad, r.text)
            assert db.log == [] and db.committed == 0, (chan, bad, db.log)
            assert seen == {"scope": [], "hmac": [], "session": []}, (chan, bad, seen)
        db = _Db()
        with pytest.raises(HTTPException) as ex:
            asyncio.run(main._chat_mute_apply(db, target_steam_id=bad, channel=None, by_steam_id=ADMIN,
                                              reason="", minutes=0))
        assert (ex.value.status_code, ex.value.detail) == (422, DETAIL) and db.log == [], repr(bad)
    assert "[CHAT-MOD]" not in capsys.readouterr().out


def test_one_target_string_reaches_the_signature_chat_mutes_the_audit_the_filter_the_log_and_the_response(
        monkeypatch, capsys):
    """Each accepted target (a Steam id, twenty digits, one digit) is the one string in the signed target, the
    moderator-target check, the key the route hands the core, both core binds, each of the three unmute arms, the
    audit row, the admin-actions filter (its Query bound admits it and both of its statements bind it), the log line
    and the response."""
    client, seen, holder = _client(monkeypatch)

    def call(method, path, **kw):
        holder["db"] = db = _Db()
        _clear(seen)
        r = getattr(client, method)(path, **kw)
        assert r.status_code == 200, (path, kw, r.text)
        return db, r.json(), capsys.readouterr().out

    for t in GOOD:
        # mute by an admin, every channel
        db, res, out = call("post", "/mute", json=_body(ADMIN, t, None))
        assert seen["hmac"] == [("chat_mute", f"{t}:all")] and seen["scope"] == [ADMIN], (t, seen)
        assert [sql.split(" ")[0] for sql, _ in db.log if "chat_mutes" in sql] == ["UPDATE", "INSERT"], db.log
        assert db.binds("chat_mutes", "sid") == [t, t], db.log
        assert db.binds("INSERT INTO admin_actions", "t") == [t] and db.committed == 1
        assert res["target_steam_id"] == t and f"[CHAT-MOD] admin {ADMIN} muted {t} in [ALL] for ever min" in out
        # mute by a moderator in their channel: the moderator-target check reads the same string
        db, res, out = call("post", "/mute", json=_body(MOD, t, "ru"))
        assert seen == {"scope": [MOD, t], "hmac": [], "session": [MOD]}, (t, seen)
        assert db.binds("chat_mutes", "sid") == [t, t] and db.binds("INSERT INTO admin_actions", "t") == [t]
        assert res["target_steam_id"] == t and f"[CHAT-MOD] moderator {MOD} muted {t} in [ru] for ever min" in out
        # unmute: the channel arm, the admin arm, the moderator's own-languages arm, each identified by its SQL
        for actor, chan, arm, label in ARMS:
            role = "admin" if actor == ADMIN else "moderator"
            db, res, out = call("post", "/unmute", json=_body(actor, t, chan))
            signed = [("chat_unmute", f"{t}:{chan or 'all'}")] if actor == ADMIN else []
            assert seen["hmac"] == signed, (t, actor, chan, seen)
            updates = [(sql, p) for sql, p in db.log if sql.startswith("UPDATE chat_mutes")]
            assert len(updates) == 1 and arm in updates[0][0] and updates[0][1]["sid"] == t, (t, actor, chan, db.log)
            assert db.binds("INSERT INTO admin_actions", "t") == [t] and db.committed == 1
            assert res["target_steam_id"] == t and res["cleared"] == 1, res
            assert f"[CHAT-MOD] {role} {actor} unmuted {t} in [{label}] (1 row(s))" in out, out
        # the admin-actions filter admits the target and binds it unchanged on the count and on the page
        db, res, out = call("get", "/actions", params={"admin_steam_id": ADMIN, "target_steam_id": t})
        assert db.binds("aa.target_steam_id = :target", "target") == [t, t], db.log


def test_the_unmute_revokes_a_key_outside_the_domain_only_when_a_row_carries_it(monkeypatch, capsys):
    """The unmute checks its target after its UPDATE, as the unban does (_mod_release_or_422). On each of its three
    arms:
    - a target outside the domain whose UPDATE revoked no row answers 422 with the check's detail, after the identity
      proof and that one UPDATE (bound to the exact string), with no audit row, no commit and no log line;
    - a key a chat_mutes row can carry whose UPDATE revoked a row is admitted: the signature, the UPDATE, the audit
      row, the log line and the response all carry that exact key, and the route commits -- a row stored under a key
      outside the domain stays revocable;
    - a target inside the domain whose UPDATE revoked nothing is not refused: 200, cleared 0, no audit row."""
    client, seen, holder = _client(monkeypatch)

    def call(target, actor, chan, released):
        holder["db"] = db = _Db(released)
        _clear(seen)
        r = client.post("/unmute", json=_body(actor, target, chan))
        return r, db, capsys.readouterr().out

    def proof(target, actor, chan):
        if actor == ADMIN:
            return {"scope": [ADMIN], "hmac": [("chat_unmute", f"{target}:{chan or 'all'}")], "session": []}
        return {"scope": [MOD], "hmac": [], "session": [MOD]}

    assert len(LEGACY) >= 10 and "7" * 32 in LEGACY and "7" * 21 in LEGACY and "photon_1" in LEGACY
    for actor, chan, arm, label in ARMS:
        role = "admin" if actor == ADMIN else "moderator"
        for bad in BAD:
            r, db, out = call(bad, actor, chan, 0)
            assert r.status_code == 422 and r.json() == {"detail": DETAIL}, (actor, chan, bad, r.text)
            assert seen == proof(bad, actor, chan), (actor, chan, bad, seen)
            assert len(db.log) == 1 and db.log[0][0].startswith("UPDATE chat_mutes") and arm in db.log[0][0], db.log
            assert db.log[0][1]["sid"] == bad and db.committed == 0, (actor, chan, bad, db.log, db.committed)
            assert "[CHAT-MOD]" not in out, out
        for key in LEGACY:
            r, db, out = call(key, actor, chan, 1)
            assert r.status_code == 200, (actor, chan, key, r.text)
            assert r.json() == {"status": "ok", "cleared": 1, "target_steam_id": key, "channel": chan}, r.json()
            assert seen == proof(key, actor, chan), (actor, chan, key, seen)
            assert db.binds("UPDATE chat_mutes", "sid") == [key], db.log
            assert db.binds("INSERT INTO admin_actions", "t") == [key] and db.committed == 1, db.log
            assert f"[CHAT-MOD] {role} {actor} unmuted {key} in [{label}] (1 row(s))" in out, out
        for good in GOOD:
            r, db, out = call(good, actor, chan, 0)
            assert r.status_code == 200, (actor, chan, good, r.text)
            assert r.json() == {"status": "ok", "cleared": 0, "target_steam_id": good, "channel": chan}, r.json()
            assert db.binds("UPDATE chat_mutes", "sid") == [good] and db.binds("INSERT INTO admin_actions", "t") == []
            assert db.committed == 1 and f"[CHAT-MOD] {role} {actor} unmuted {good} in [{label}] (0 row(s))" in out


def _functions(tree):
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _body_after_docstring(fn):
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return body


def _has_slice(node):
    return any(isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Slice) for n in ast.walk(node))


def _sliced(expr, fn):
    """The bind expression contains a slice, or names a local that the same function assigns from one."""
    if _has_slice(expr):
        return True
    names = {n.id for n in ast.walk(expr) if isinstance(n, ast.Name)}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            targets = [node.target]
        else:
            continue
        if node.value is not None and _has_slice(node.value) \
                and any(isinstance(t, ast.Name) and t.id in names for t in targets):
            return True
    return False


def test_the_mute_checks_first_the_unmute_after_its_update_and_no_chat_mutes_statement_binds_a_sliced_key():
    """Placement and the class.
    - The mute route's first statement (after its docstring) checks the request's target, which it reads nowhere
      else; the write core's first statement checks its key parameter, which it reads nowhere else.
    - The unmute route calls no restriction check. Its one _mod_release_or_422 call is the statement right after its
      UPDATE arms and right before its audit block, and passes the number of rows the arm revoked.
    - The r14 class is a chat_mutes key bound as a slice of its input: over main.py's syntax tree, every db.execute
      whose SQL names chat_mutes and whose binds carry "sid" is found (the writer functions among them must include
      the five known ones), and none binds "sid" to an expression containing a slice, or to a local the same
      function assigns from one. (A slice made in a caller and passed in as an argument is outside what this pin
      reads.)"""
    with open(inspect.getsourcefile(main), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    funcs = _functions(tree)
    for name, var, arg in (("chat_moderate_mute", "target", "req.target_steam_id"),
                           ("_chat_mute_apply", "sid", "target_steam_id")):
        fn = funcs[name]
        assert ast.unparse(_body_after_docstring(fn)[0]) == f"{var} = _mod_target_or_422({arg})", name
        reads = [n for n in ast.walk(fn) if ast.unparse(n) == arg and isinstance(n, (ast.Attribute, ast.Name))
                 and isinstance(n.ctx, ast.Load)]
        assert len(reads) == 1, (name, len(reads))
    unmute = funcs["chat_moderate_unmute"]
    called = [ast.unparse(n.func) for n in ast.walk(unmute) if isinstance(n, ast.Call)]
    assert "_mod_target_or_422" not in called and called.count("_mod_release_or_422") == 1, called
    heads = [ast.unparse(s).split("\n")[0] for s in _body_after_docstring(unmute)]
    at = heads.index("_mod_release_or_422(req.target_steam_id, len(cleared))")
    assert heads[at - 1] == "if chan is not None:" and heads[at + 1] == "if cleared:", heads
    binds, writers = [], set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(fn):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "execute" and len(call.args) >= 2 and isinstance(call.args[1], ast.Dict)):
                continue
            sql = ast.unparse(call.args[0])
            if "chat_mutes" not in sql:
                continue
            if "UPDATE chat_mutes" in sql or "INSERT INTO chat_mutes" in sql:
                writers.add(fn.name)
            binds += [(fn, v) for k, v in zip(call.args[1].keys, call.args[1].values)
                      if isinstance(k, ast.Constant) and k.value == "sid"]
    assert {"_chat_mute_apply", "chat_moderate_unmute", "_apply_mute_for_row", "_chat_censor_strike",
            "delete_player_data"} <= writers, sorted(writers)
    per_function = {}
    for fn, _ in binds:
        per_function[fn.name] = per_function.get(fn.name, 0) + 1
    # the nine binds r14 found sliced are among those read: two in the core, three unmute arms, four by-message binds
    assert {k: per_function.get(k) for k in ("_chat_mute_apply", "chat_moderate_unmute", "_apply_mute_for_row")} \
        == {"_chat_mute_apply": 2, "chat_moderate_unmute": 3, "_apply_mute_for_row": 4}, per_function
    assert [(fn.name, ast.unparse(v)) for fn, v in binds if _sliced(v, fn)] == []
