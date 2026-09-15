"""v4.13 (review r15 sweep), the ids and texts the admin moderation routes are sent. A statement fails (500) when it
binds a string no text bind can carry (PostgreSQL text holds no NUL character; a lone surrogate has no UTF-8
encoding) or binds, as a uuid, a string that is not a UUID. The routes below bound such strings with no check on
them. Each now checks them before the admin check and every statement:
  * the record exclusion refuses a board, match id, steam id or reason no text bind can carry (422), each as the
    route's existing slice of it: its first 32, 40, 20 and 400 characters;
  * the flag review and the flag restoration parse the flag's id as a UUID (400 flag_id_invalid) and bind the
    parsed UUID in their read; the signature, the audit row and the answer keep the id as sent;
  * the quarantine discard and accept parse the report's id as a UUID (400 qid_invalid) and bind the parsed id's
    canonical text in every statement, the signature keeping the id as sent; the discard refuses a note no text
    bind can carry (422), as the route's existing slice of it, its first 500 characters.
The admin portrait clear's target is tested in test_pc_routes.py; the Discord delete event's ids and the
admin-actions action filter in test_chat_mute_target.py. The routes are called directly, with the database
scripted and the admin check stubbed."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

import main

# strings no text bind can carry: a NUL character (PostgreSQL text holds none) and lone surrogates (no UTF-8 encoding)
UNBINDABLE = ("\x00", "7656119800000000\x00", "photon_\x00", "\ud800", "76561198000000008\udfff")
# strings a text bind carries: a photon_ id, a noncharacter, the last code point, Arabic-Indic digits
CARRIED = ("photon_1", "￾", "\U0010ffff", chr(0x0667) * 17)
STEAM = "76561198000000008"
MATCH = UUID("5f1c2b9e-8d3a-4c71-9e0b-2a6d4f8c1e37")
P1, P2 = UUID("0b6e6f55-3a53-4f0e-8f55-7d1f6c3a9b21"), UUID("7c2d9a41-51b8-4e3c-a0d4-93e6f1b27c58")
FLAG = UUID("3e9b7c1a-6d24-4f8b-9a15-c7e0d2b4f613")
QID = UUID("a47c3e2b-19d5-4b6a-8e70-5f2c9d1b3e84")
# strings that are not UUIDs: empty, words, one hex digit short or over, a UUID's text followed by a NUL character,
# a UUID's text with a lone surrogate in its last place, and the strings no text bind can carry
NOT_UUIDS = ("", "not-a-uuid", "1234", str(FLAG)[:-1], str(FLAG) + "0", str(FLAG) + "\x00", str(FLAG)[:-1] + "\ud800",
             "g" * 32) + UNBINDABLE


def _spellings(value):
    """Spellings of one UUID the parse admits: canonical, upper case, in braces, without hyphens."""
    s = str(value)
    return (s, s.upper(), "{" + s + "}", s.replace("-", ""))


class _Res:
    def __init__(self, rows=(), rowcount=0):
        self._rows, self.rowcount = list(rows), rowcount

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _Nested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Db:
    """Logs every statement as normalised SQL with a copy of its binds. Answers the record exclusion's reads (the
    match, P1 and P2 in its seats; the player P1) and the quarantine's row read (`row`); every other statement
    reports `rowcount` rows."""

    def __init__(self, row=None, rowcount=1):
        self.log, self.committed, self.row, self.rowcount = [], 0, row, rowcount

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.log.append((sql, dict(params or {})))
        if sql.startswith("SELECT id, player1_id, player2_id FROM matches"):
            return _Res([{"id": MATCH, "player1_id": P1, "player2_id": P2}])
        if sql.startswith("SELECT id FROM players WHERE steam_id"):
            return _Res([(P1,)])
        if sql.startswith("SELECT player_ids, created_at, status, mode FROM match_report_quarantine"):
            return _Res([self.row] if self.row else [])
        return _Res(rowcount=self.rowcount)

    def begin_nested(self):
        return _Nested()

    async def commit(self):
        self.committed += 1

    def binds(self, fragment, key):
        return [p.get(key) for sql, p in self.log if fragment in sql]


class _FlagDb:
    """Keeps each statement object; the flag read answers `fm`."""

    def __init__(self, fm=None):
        self.statements, self.added, self.committed, self.fm = [], [], 0, fm

    async def execute(self, statement, params=None):
        self.statements.append(statement)
        return SimpleNamespace(scalar_one_or_none=lambda: self.fm)

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.committed += 1


def _admin(monkeypatch):
    """The admin check, stubbed: records (action, target) and admits."""
    reached = []

    async def admin(_db, _adm, action, target, _sig):
        reached.append((action, target))

    monkeypatch.setattr(main, "_require_admin", admin)
    return reached


def _refused(coro, status, detail):
    with pytest.raises(HTTPException) as ex:
        asyncio.run(coro)
    assert (ex.value.status_code, ex.value.detail) == (status, detail), (ex.value.status_code, ex.value.detail)


# ── the record exclusion ─────────────────────────────────────────────────────


def _exclusion(**fields):
    return {"admin_steam_id": "9", "board": "*", "match_id": str(MATCH), "steam_id": STEAM, "reason": "r",
            "signature": "s", **fields}


def test_the_record_exclusion_refuses_a_string_no_text_bind_can_carry_before_any_statement(monkeypatch):
    """The record exclusion keeps the first 32 characters of its board, 40 of its match id, 20 of its steam id and
    400 of its reason (the route's existing slices). It signs the board, match id and steam id (an empty or "-" steam
    id is the match-wide one), and binds the steam id (the players read) and the reason (the exclusion's insert and
    the audit row). Any of the four whose slice no text bind can carry is refused 422 before the admin check and any
    statement, with nothing committed. A board, match id or steam id whose slice a text bind carries reaches the
    admin check as that slice, and the new check alters nothing: a board or match id no exclusion admits is then
    refused with no statement, and a steam id or reason reaches its statements as its slice (a match-wide steam id
    has no players read, and the insert binds an empty reason as NULL)."""
    reached = _admin(monkeypatch)
    for field in ("board", "match_id", "steam_id", "reason"):
        for bad in UNBINDABLE:
            db = _Db()
            _refused(main.admin_record_exclude(_exclusion(**{field: bad}), db=db), 422, f"{field} is not storable text")
            assert db.log == [] and db.committed == 0 and reached == [], (field, repr(bad), db.log, reached)
    for key in CARRIED:
        db = _Db()
        _refused(main.admin_record_exclude(_exclusion(board=key), db=db), 400, "unknown board")
        assert reached[-1] == ("record_exclude", f"{key}:{MATCH}:{STEAM}") and db.log == [], (repr(key), reached)
        _refused(main.admin_record_exclude(_exclusion(match_id=key), db=db), 400, "bad match_id")
        assert reached[-1] == ("record_exclude", f"*:{key}:{STEAM}") and db.log == [], (repr(key), reached)
        db = _Db()
        assert asyncio.run(main.admin_record_exclude(_exclusion(steam_id=key, reason=key), db=db)) == {"status": "ok"}
        assert reached[-1] == ("record_exclude", f"*:{MATCH}:{key}"), (repr(key), reached)
        assert db.binds("SELECT id FROM players WHERE steam_id", "s") == [key], (repr(key), db.log)
        assert db.binds("INSERT INTO record_exclusions", "r") == [key] and db.committed == 1, (repr(key), db.log)
    assert len(reached) == 3 * len(CARRIED)


# ── the flag review and the flag restoration ─────────────────────────────────


def _bound(statement):
    """The values a SQLAlchemy statement binds, in order."""
    return list(statement.compile().params.values())


def _review(flag_id):
    return main._AdminReviewFlagReq(admin_steam_id="9", flag_id=flag_id, review_action="false_positive",
                                    evidence_revision=1, signature_version=3, hmac_signature="s")


def test_the_flag_review_parses_the_flags_id_before_the_admin_check_and_reads_by_the_parsed_uuid(monkeypatch):
    """The flag review binds its flag's id in its read, against the uuid column, where a string that is not a UUID
    fails the bind (500). The id is parsed first: one that is not a UUID -- a NUL character or a lone surrogate
    included -- is refused 400 flag_id_invalid before the admin check and any statement. An id the parse admits is
    signed as sent, the read binds the parsed UUID, and the audit row and the answer carry the id as sent."""
    reached = _admin(monkeypatch)
    for bad in NOT_UUIDS:
        db = _FlagDb()
        _refused(main.admin_review_flag(_review(bad), db=db), 400, "flag_id_invalid")
        assert db.statements == [] and db.committed == 0 and reached == [], (repr(bad), reached)
    for sent in _spellings(FLAG):
        db = _FlagDb()
        _refused(main.admin_review_flag(_review(sent), db=db), 404, "Flag not found")
        assert reached[-1] == ("review_flag", f"{sent}:false_positive:1"), (sent, reached)
        assert len(db.statements) == 1 and _bound(db.statements[0]) == [FLAG], (sent, db.statements)
        assert type(_bound(db.statements[0])[0]) is UUID, sent
        fm = SimpleNamespace(discord_evidence_revision=1, reviewed_at=None, reviewed_by_steam_id=None,
                             review_action=None, auto_invalidated=False, restoration_required=False, match_id=MATCH)
        db = _FlagDb(fm)
        ans = asyncio.run(main.admin_review_flag(_review(sent), db=db))
        assert ans == {"status": "reviewed", "flag_id": sent, "review_action": "false_positive",
                       "restoration_required": False}, ans
        assert [row.details["flag_id"] for row in db.added] == [sent] and db.committed == 1, (sent, db.added)


def test_the_flag_restoration_parses_the_flags_id_before_the_admin_check_and_reads_by_the_parsed_uuid(monkeypatch):
    """The flag restoration reads its flag the same way: an id that is not a UUID is refused 400 flag_id_invalid
    before the admin check and any statement; an id the parse admits is signed as sent, the read binds the parsed
    UUID, and the audit row and the answer carry the id as sent."""
    reached = _admin(monkeypatch)

    def req(flag_id):
        return main._AdminResolveFlagRestorationReq(admin_steam_id="9", flag_id=flag_id, hmac_signature="s")

    for bad in NOT_UUIDS:
        db = _FlagDb()
        _refused(main.admin_resolve_flag_restoration(req(bad), db=db), 400, "flag_id_invalid")
        assert db.statements == [] and db.committed == 0 and reached == [], (repr(bad), reached)
    for sent in _spellings(FLAG):
        db = _FlagDb()
        _refused(main.admin_resolve_flag_restoration(req(sent), db=db), 404, "Flag not found")
        assert reached[-1] == ("resolve_flag_restoration", sent), (sent, reached)
        assert len(db.statements) == 1 and _bound(db.statements[0]) == [FLAG], (sent, db.statements)
        assert type(_bound(db.statements[0])[0]) is UUID, sent
        fm = SimpleNamespace(review_action="false_positive", reviewed_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
                             restoration_required=True, match_id=MATCH)
        db = _FlagDb(fm)
        ans = asyncio.run(main.admin_resolve_flag_restoration(req(sent), db=db))
        assert ans == {"status": "restoration_completed", "flag_id": sent}, ans
        assert [row.details for row in db.added] == [{"flag_id": sent}] and db.committed == 1, (sent, db.added)


# ── the quarantine discard and accept ────────────────────────────────────────


def _quarantine(note=None):
    return main._AdminQuarantineReq(admin_steam_id="9", hmac_signature="s", note=note)


def test_the_quarantine_discard_checks_the_reports_id_and_note_before_the_admin_check(monkeypatch):
    """The quarantine discard binds the report's id as a uuid and its note as text in its UPDATE, the note as the
    route's existing slice of it, its first 500 characters. An id that is not a UUID is refused 400 qid_invalid, and
    a note whose slice no text bind can carry 422, before the admin check and the UPDATE. An id the parse admits is
    signed as sent and bound as the parsed id's canonical text; a note whose slice a text bind carries is bound as
    that slice, and the new check alters nothing (no note, as the empty string)."""
    reached = _admin(monkeypatch)
    for bad in NOT_UUIDS:
        db = _Db()
        _refused(main.admin_discard_quarantine(bad, _quarantine("n"), db=db), 400, "qid_invalid")
        assert db.log == [] and db.committed == 0 and reached == [], (repr(bad), db.log, reached)
    for bad in UNBINDABLE:
        db = _Db()
        _refused(main.admin_discard_quarantine(str(QID), _quarantine(bad), db=db), 422, "note is not storable text")
        assert db.log == [] and db.committed == 0 and reached == [], (repr(bad), db.log, reached)
    for sent, note in zip(_spellings(QID), CARRIED):
        for sent_note, bound_note in ((note, note), (None, "")):
            db = _Db(rowcount=1)
            ans = asyncio.run(main.admin_discard_quarantine(sent, _quarantine(sent_note), db=db))
            assert ans == {"status": "discarded"} and reached[-1] == ("quarantine_action", sent), (sent, ans, reached)
            assert db.binds("UPDATE match_report_quarantine", "qid") == [str(QID)], (sent, db.log)
            assert db.binds("UPDATE match_report_quarantine", "note") == [bound_note] and db.committed == 1, db.log


def test_the_quarantine_accept_parses_the_reports_id_before_the_admin_check_and_binds_its_canonical_text(
        monkeypatch, capsys):
    """The quarantine accept binds the report's id as a uuid in its row read and its UPDATE. An id that is not a
    UUID is refused 400 qid_invalid before the admin check and any statement. An id the parse admits is signed as
    sent, and both statements bind the parsed id's canonical text."""
    reached = _admin(monkeypatch)

    async def no_service_subject(_db, **_kw):
        return None

    async def no_later_games(*_a, **_kw):
        return 0

    monkeypatch.setattr(main, "_assert_no_service_subject", no_service_subject)
    monkeypatch.setattr(main, "_quarantine_later_rated_count", no_later_games)
    for bad in NOT_UUIDS:
        db = _Db()
        _refused(main.admin_accept_quarantine(bad, _quarantine(), db=db), 400, "qid_invalid")
        assert db.log == [] and db.committed == 0 and reached == [], (repr(bad), db.log, reached)
    row = {"player_ids": [], "created_at": datetime(2026, 9, 15, tzinfo=timezone.utc), "status": "pending",
           "mode": "1v1"}
    for sent in _spellings(QID):
        db = _Db(row=row)
        assert asyncio.run(main.admin_accept_quarantine(sent, _quarantine(), db=db)) == {"status": "accepted"}
        assert reached[-1] == ("quarantine_action", sent), (sent, reached)
        assert db.binds("FROM match_report_quarantine WHERE id = CAST(:qid AS UUID) FOR UPDATE", "qid") == [str(QID)]
        assert db.binds("UPDATE match_report_quarantine", "qid") == [str(QID)] and db.committed == 1, (sent, db.log)
    assert capsys.readouterr().out.count("[QUARANTINE]") == len(_spellings(QID))
