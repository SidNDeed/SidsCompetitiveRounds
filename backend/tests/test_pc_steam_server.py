"""Steam pictures — the server half in main.py (design v2 + the v3 addendum
from review r2, the v4 addendum from r3): the claim's attempt id and lease, the writer's bound dispositions,
the process loop's outcomes, priming past its deadline, the sweep's earned
health word, the render probe, the blob janitor's one-lock transactions, the
events hold-back with face_ready, the settings routes' Steam-unit clear under
the revision CAS, the face cache's age bound, and the deploy wiring."""
import asyncio
import hashlib
import inspect
import io
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

from test_player_cards_server import Scripted, _main_code, _run  # noqa: E402
from test_pc_routes import PID, STEAM, NOW, _Req, _idx  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402
import pc_portrait  # noqa: E402
import pc_steam  # noqa: E402
import schemas  # noqa: E402
import steamid64  # noqa: E402
import steamid64_pg_parity  # noqa: E402
from steamid64_pg_parity import VECTORS  # noqa: E402

MAIN_SRC = inspect.getsource(main)
REPO = Path(main.__file__).resolve().parents[2]
S2, S3, S4 = "76561198720512419", "76561198041616199", "76561198860111585"
H0, H1 = "a0" * 32, "b1" * 32
R0, R1 = "c" * 40, "d" * 40
DEFAULT = "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb"


def _png(color=(10, 20, 30, 255)):
    buf = io.BytesIO()
    Image.new("RGBA", (4, 4), color).save(buf, "PNG")
    return buf.getvalue()


def _claimed(**over):
    c = {"id": PID, "steam_id": STEAM, "attempt": 1, "hash": H0}   # v4: no token, no reference
    c.update(over)
    return c


def _wrow(**over):
    r = {"game_hash": None, "steam_hash": H0, "ref": R0, "fail": 0, "attempt": 1, "deleted": False,
         "eligible": True}
    r.update(over)
    return r


def _wdb(row=..., held=(None, H0), wrote=True):
    row = _wrow() if row is ... else row
    return Scripted({
        "SELECT pc_game_portrait_hash, pc_steam_portrait_hash FROM players":
            [[{"pc_game_portrait_hash": held[0], "pc_steam_portrait_hash": held[1]}]],
        "AS eligible": [[row] if row is not None else []],
        "RETURNING id": [[{"id": PID}] if wrote else []],
    })


# ── the claim ──────────────────────────────────────────────────────────

def test_the_claim_advances_the_attempt_withdraws_the_reference_and_leases_the_row():
    db = Scripted({"WITH due AS": [[{"id": PID, "steam_id": STEAM, "attempt": 4, "hash": H0}]]})
    rows = _run(main._pc_steam_claim(db, 100))
    assert rows == [{"id": PID, "steam_id": STEAM, "attempt": 4, "hash": H0}]
    sql, params = db.log[0]
    assert "FOR NO KEY UPDATE OF p SKIP LOCKED" in sql
    assert ("UPDATE players p SET pc_steam_attempt = p.pc_steam_attempt + 1, pc_steam_portrait_at = now(), "
            "pc_steam_portrait_next_at = now() + make_interval(mins => CAST(:lease AS integer)), "
            "pc_steam_avatar_ref = NULL FROM due WHERE p.id = due.id") in sql
    assert params["lease"] == main._PC_STEAM_LEASE_MINUTES == 15 and params["lim"] == 100
    assert "RETURNING p.id, p.steam_id, p.pc_steam_attempt AS attempt, p.pc_steam_portrait_hash AS hash" in sql
    # a reference is the last COMPLETED attempt's answer: withdrawn while one is in flight (v4 §2), so
    # the claim hands the writer no reference and no token
    assert "AS ref" not in sql and "AS token" not in sql
    assert "ORDER BY p.pc_steam_portrait_next_at ASC NULLS FIRST" in sql and "m.pool_rank" in sql
    assert "(p.pc_steam_portrait_next_at IS NULL OR p.pc_steam_portrait_next_at <= now())" in sql
    eligible = " ".join(main._PC_STEAM_ELIGIBLE_SQL.split())
    assert eligible in sql
    # the priming path: only these ids, only the never attempted (a lease is an attempt)
    db = Scripted({})
    _run(main._pc_steam_claim(db, 5, ids=[PID], never_only=True))
    sql, params = db.log[0]
    assert "(p.pc_steam_portrait_next_at IS NULL)" in sql and "<= now()" not in sql
    assert "p.id = ANY(CAST(:ids AS uuid[]))" in sql and params["ids"] == [str(PID)]
    # one eligibility text: its definition, the claim, the writer's revalidation, the render probe
    assert MAIN_SRC.count("_PC_STEAM_ELIGIBLE_SQL") == 4


# ── the writer ─────────────────────────────────────────────────────────

def test_the_writer_orders_identity_blob_and_row_locks_and_binds_on_the_claim():
    png = _png()
    new_hash = hashlib.sha256(png).hexdigest()
    db = _wdb()
    word = _run(main._pc_steam_write(db, _claimed(), "changed", ref=R1, png=png))
    assert word == "applied" and db.rolled_back == 0
    order = [_idx(db, k) for k in ("pg_advisory_xact_lock(hashtext", "CAST(:cls AS integer)", "AS eligible",
                                   "INSERT INTO pc_portraits", "RETURNING id", "UPDATE pc_portraits SET unreferenced_since")]
    assert order == sorted(order), order   # I → P → R → blob in → the bound row write → release
    assert db.log[0][1] == {"sid": STEAM}
    plocks = [p["h"] for s, p in db.log if "CAST(:cls AS integer)" in s]
    assert plocks == sorted({H0, new_hash})           # the hash held AND the new one, sorted
    rread = db.log[_idx(db, "AS eligible")][0]
    assert "FOR NO KEY UPDATE OF p" in rread and "p.pc_steam_attempt AS attempt" in rread
    assert " ".join(main._PC_STEAM_ELIGIBLE_SQL.split()) in rread
    blob = db.log[_idx(db, "INSERT INTO pc_portraits")]
    assert "ON CONFLICT (hash) DO UPDATE SET unreferenced_since = NULL" in blob[0]
    assert blob[1]["h"] == new_hash and blob[1]["b"] == png and (blob[1]["w"], blob[1]["hh"]) == (4, 4)
    upd = db.log[_idx(db, "RETURNING id")]
    assert "pc_steam_portrait_hash = CAST(:h AS text)" in upd[0] and "pc_steam_portrait_fail = 0" in upd[0]
    assert upd[0].endswith(" WHERE id = CAST(:pid AS uuid) AND pc_steam_attempt = CAST(:attempt AS bigint) RETURNING id")
    assert "IS NOT DISTINCT FROM" not in upd[0]   # v4 §1: the attempt id is the whole bind
    assert upd[1] == {"pid": str(PID), "attempt": 1, "h": new_hash, "ref": R1, "d": pc_steam.REFRESH_DAYS}
    rel = db.log[_idx(db, "UPDATE pc_portraits SET unreferenced_since")]
    assert rel[1] == {"h": H0} and "NOT EXISTS" in rel[0] and "pc_steam_portrait_hash = CAST(:h AS text)" in rel[0]


def test_the_writer_drops_a_verdict_the_row_no_longer_owns():
    png = _png()
    # the row is gone
    assert _run(main._pc_steam_write(_wdb(row=None), _claimed(), "changed", ref=R1, png=png)) == "gone"
    assert _run(main._pc_steam_write(_wdb(row=_wrow(deleted=True)), _claimed(), "changed", ref=R1, png=png)) == "gone"
    # P was taken on a hash the row no longer names (only reachable without I)
    db = _wdb(row=_wrow(steam_hash=H1))
    assert _run(main._pc_steam_write(db, _claimed(), "changed", ref=R1, png=png)) == "moved" and db.rolled_back == 1
    # a newer attempt owns the row: the lease expired and a later claim advanced the id
    db = _wdb(row=_wrow(attempt=2))
    assert _run(main._pc_steam_write(db, _claimed(), "changed", ref=R1, png=png)) == "moved" and db.rolled_back == 1
    assert db.count("UPDATE players") == 0 and db.count("INSERT INTO pc_portraits") == 0
    # every invalidating mutation advances the id too, whether or not it changed a value the row
    # holds (r3): a never-attempted row (no hash, no reference) claimed, then cleared by an admin
    # while the fetch is out — the values the clear wrote are the values the claim read, and the
    # verdict must still bind to nothing, for a picture and for a failure alike
    for outcome, kw in (("changed", {"ref": R1, "png": png}), ("failed", {})):
        db = _wdb(row=_wrow(steam_hash=None, ref=None, attempt=2), held=(None, None))
        assert _run(main._pc_steam_write(db, _claimed(hash=None), outcome, **kw)) == "moved", outcome
        assert db.rolled_back == 1 and db.count("UPDATE players") == 0 and db.count("INSERT INTO pc_portraits") == 0
    # the writer takes nothing else off the claim: no token, no reference, no value comparison
    src = inspect.getsource(main._pc_steam_write)
    assert 'claimed["attempt"]' in src and 'claimed["token"]' not in src and 'claimed["ref"]' not in src
    assert "IS NOT DISTINCT FROM" not in src and src.count("pc_steam_attempt = CAST(:attempt AS bigint)") == 1
    # ineligible since the claim (None, opt-out, ban, lock): nothing written, nothing rolled back
    db = _wdb(row=_wrow(eligible=False))
    assert _run(main._pc_steam_write(db, _claimed(), "changed", ref=R1, png=png)) == "ineligible"
    assert db.count("UPDATE players") == 0 and db.rolled_back == 0
    # the bound write itself found nothing: the blob insert is rolled back with it
    db = _wdb(wrote=False)
    assert _run(main._pc_steam_write(db, _claimed(), "changed", ref=R1, png=png)) == "moved" and db.rolled_back == 1


def test_the_writer_backs_off_keeps_the_picture_and_stores_the_plate_answer():
    # failed: fail += 1, next_at backs off, the stored picture and reference STAY
    db = _wdb(row=_wrow(fail=2))
    assert _run(main._pc_steam_write(db, _claimed(), "failed")) == "backoff"
    upd = db.log[_idx(db, "RETURNING id")]
    assert upd[0].startswith("UPDATE players SET pc_steam_portrait_fail = CAST(:fail AS smallint), "
                             "pc_steam_portrait_next_at = now() + make_interval(hours => CAST(:h AS integer))")
    assert upd[1] == {"pid": str(PID), "attempt": 1, "fail": 3, "h": pc_steam.backoff_hours(3)}
    assert "pc_steam_avatar_ref" not in upd[0], "a failed attempt resolves nothing: the reference stays withdrawn (v4 §2)"
    assert "pc_steam_portrait_hash =" not in upd[0] and db.count("UPDATE pc_portraits") == 0
    # none: Steam's own no-picture answer — the reference is stored, the hash goes, the old blob is released
    db = _wdb()
    assert _run(main._pc_steam_write(db, _claimed(), "none", ref=DEFAULT)) == "plate"
    upd = db.log[_idx(db, "RETURNING id")]
    assert upd[0].startswith("UPDATE players SET pc_steam_portrait_hash = NULL, pc_steam_avatar_ref = CAST(:ref AS text), "
                             "pc_steam_portrait_fail = 0, pc_steam_portrait_next_at = now() + make_interval(days => CAST(:d AS integer))")
    assert upd[1]["ref"] == DEFAULT and db.count("INSERT INTO pc_portraits") == 0
    assert db.log[_idx(db, "UPDATE pc_portraits SET unreferenced_since")][1] == {"h": H0}
    # the same bytes again: the reference and the schedule move, no blob write, no release
    png = _png()
    same = hashlib.sha256(png).hexdigest()
    db = _wdb(row=_wrow(steam_hash=same), held=(None, same))
    assert _run(main._pc_steam_write(db, _claimed(hash=same), "changed", ref=R1, png=png)) == "touched"
    upd = db.log[_idx(db, "RETURNING id")]
    assert upd[0].startswith("UPDATE players SET pc_steam_portrait_fail = 0, pc_steam_avatar_ref = CAST(:ref AS text)")
    assert db.count("INSERT INTO pc_portraits") == 0 and db.count("UPDATE pc_portraits") == 0


# ── the process loop ───────────────────────────────────────────────────

def test_the_process_loop_downloads_every_reference_and_never_the_default(monkeypatch):
    fetched, writes, asked = [], [], []

    async def refs(ids, priority=False, deadlines=None):
        asked.append(list(ids))
        return {STEAM: "e" * 40, S2: DEFAULT, S3: None}

    async def picture(ref, priority=False, deadline=None):
        fetched.append(ref)
        return True, b"png"

    async def write(db, claimed, outcome, *, ref=None, png=None):
        writes.append((claimed["steam_id"], outcome, ref, png))
        return "applied"

    monkeypatch.setattr(main, "_pc_steam_fetch_refs", refs)
    monkeypatch.setattr(main, "_pc_steam_fetch_picture", picture)
    monkeypatch.setattr(main, "_pc_steam_write", write)
    dbs = []

    def factory():
        dbs.append(Scripted({}))
        return dbs[-1]
    monkeypatch.setattr(database, "async_session", factory)
    monkeypatch.setitem(main._PC_STEAM_SWEEP_STATE, "clean_at", None)
    claimed = [_claimed(), _claimed(steam_id=S2), _claimed(steam_id=S3), _claimed(steam_id=S4)]
    counts = _run(main._pc_steam_process(claimed))
    assert asked == [[STEAM, S2, S3, S4]]   # one feed call for the batch, every claimed id
    assert fetched == ["e" * 40]     # the default reference and a missing one are never downloaded
    assert writes == [(STEAM, "changed", "e" * 40, b"png"), (S2, "none", DEFAULT, None), (S3, "failed", None, None)]
    assert counts == {"applied": 3, "unreached": 1} and all(d.committed == 1 for d in dbs)
    assert main._PC_STEAM_SWEEP_STATE["clean_at"] is not None   # every committed write is a heartbeat
    # a picture that failed to download is that player's failure
    async def no_picture(ref, priority=False, deadline=None):
        return True, None
    monkeypatch.setattr(main, "_pc_steam_fetch_picture", no_picture)
    writes.clear()
    _run(main._pc_steam_process([_claimed()]))
    assert writes == [(STEAM, "failed", "e" * 40, None)]
    # the breaker cutting in after the picture's token wait: no request was sent, so no verdict at all
    async def not_sent(ref, priority=False, deadline=None):
        return False, None
    monkeypatch.setattr(main, "_pc_steam_fetch_picture", not_sent)
    writes.clear()
    assert _run(main._pc_steam_process([_claimed()])) == {"unreached": 1} and writes == []
    monkeypatch.setattr(main, "_pc_steam_fetch_picture", picture)
    # the breaker pausing mid-batch leaves the rest unreached (their leases expire); the default needs no network
    monkeypatch.setattr(main._pc_steam_breaker, "paused", lambda now=None: True)
    writes.clear()
    assert _run(main._pc_steam_process([_claimed(), _claimed(steam_id=S2)])) == {"unreached": 1, "applied": 1}
    assert writes == [(S2, "none", DEFAULT, None)]
    # the whole feed failing writes nothing
    async def no_refs(ids, priority=False, deadlines=None):
        return None
    monkeypatch.setattr(main, "_pc_steam_fetch_refs", no_refs)
    writes.clear()
    assert _run(main._pc_steam_process([_claimed()])) == {"batch_failed": 1} and writes == []
    # a write that raises is counted, rolled back, and does not stop the batch
    monkeypatch.setattr(main, "_pc_steam_fetch_refs", refs)
    monkeypatch.setattr(main._pc_steam_breaker, "paused", lambda now=None: False)

    async def boom(db, claimed, outcome, *, ref=None, png=None):
        raise RuntimeError("db")
    monkeypatch.setattr(main, "_pc_steam_write", boom)
    dbs.clear()
    monkeypatch.setitem(main._PC_STEAM_SWEEP_STATE, "clean_at", None)
    assert _run(main._pc_steam_process([_claimed(steam_id=S2), _claimed(steam_id=S3)])) == \
        {"error": 2, "error_class": "RuntimeError"}
    assert [d.rolled_back for d in dbs] == [1, 1]
    assert main._PC_STEAM_SWEEP_STATE["clean_at"] is None   # a write that failed is no heartbeat (v4 §3)
    # ... and neither is a verdict the writer dropped
    async def dropped(db, claimed, outcome, *, ref=None, png=None):
        return "moved"
    monkeypatch.setattr(main, "_pc_steam_write", dropped)
    assert _run(main._pc_steam_process([_claimed(steam_id=S2)])) == {"moved": 1}
    assert main._PC_STEAM_SWEEP_STATE["clean_at"] is None
    assert "ref" not in _claimed(), "v4: the claim hands the writer no reference; every reference is downloaded"


def test_the_default_references_are_steams_no_picture_answers():
    assert pc_steam.is_default_ref("0" * 40) and pc_steam.is_default_ref(DEFAULT)
    assert not pc_steam.is_default_ref("a" * 40) and not pc_steam.is_default_ref(None)
    assert pc_steam.DEFAULT_AVATAR_REFS == frozenset({"0" * 40, DEFAULT})


def _breaker_spy(monkeypatch, paused_answers):
    recorded = []
    monkeypatch.setattr(main._pc_steam_breaker, "record",
                        lambda kind, ok, status=None, now=None: recorded.append((kind, ok, status)))
    answers = list(paused_answers)
    monkeypatch.setattr(main._pc_steam_breaker, "paused", lambda now=None: answers.pop(0) if answers else False)

    async def wait(priority=False, deadline=None):
        recorded.append(("wait", priority, None))
        return True
    monkeypatch.setattr(main, "_pc_steam_wait", wait)
    return recorded


def test_the_picture_fetch_rechecks_the_breaker_and_counts_junk_behind_a_200_against_the_cdn(monkeypatch):
    # a pause that began during the token wait: no request, no verdict (v4 §3)
    recorded = _breaker_spy(monkeypatch, [True])
    gets = []
    monkeypatch.setattr(pc_steam, "http_get", lambda url, **kw: gets.append(url) or b"<html>not a picture</html>")
    assert _run(main._pc_steam_fetch_picture("e" * 40)) == (False, None)
    assert recorded == [("wait", False, None)] and gets == []
    # junk behind HTTP 200 is that player's failure AND a CDN failure: five of them pause the sweep
    recorded = _breaker_spy(monkeypatch, [False])
    assert _run(main._pc_steam_fetch_picture("e" * 40, priority=True)) == (True, None)
    assert recorded == [("wait", True, None), ("cdn", False, None)] and len(gets) == 1
    assert gets[0] == pc_steam.avatar_url("e" * 40)
    # the success is recorded only once the canonicaliser accepted the body
    good = io.BytesIO()
    Image.new("RGBA", (184, 184), (10, 20, 30, 255)).save(good, "PNG")
    monkeypatch.setattr(pc_steam, "http_get", lambda url, **kw: good.getvalue())
    recorded = _breaker_spy(monkeypatch, [False])
    attempted, png = _run(main._pc_steam_fetch_picture("e" * 40))
    assert attempted and png is not None and png.startswith(b"\x89PNG") and recorded[-1] == ("cdn", True, None)
    # a transport failure is the CDN's, with its status
    def boom(url, **kw):
        raise pc_steam.FetchError("http", 503)
    monkeypatch.setattr(pc_steam, "http_get", boom)
    recorded = _breaker_spy(monkeypatch, [False])
    assert _run(main._pc_steam_fetch_picture("e" * 40)) == (True, None) and recorded[-1] == ("cdn", False, 503)


def test_the_xml_path_counts_an_unusable_body_as_the_feeds_failure_and_rechecks_the_breaker(monkeypatch):
    monkeypatch.setitem(main._pc_steam_xml, "forced", True)   # the keyed path is out: profile XML per player
    bodies = [b"<html>rate limited</html>",
              b"<response><error>The specified profile could not be found.</error></response>",
              f"<profile><avatarFull>https://avatars.steamstatic.com/{'e' * 40}_full.jpg</avatarFull></profile>".encode()]
    monkeypatch.setattr(pc_steam, "http_get", lambda url, **kw: bodies.pop(0))
    recorded = _breaker_spy(monkeypatch, [False] * 6)
    out = _run(main._pc_steam_fetch_refs([STEAM, S2, S3]))
    # a body that is not a profile is the feed's failure (that player fails and backs off, the breaker counts
    # it); Steam's own "no such profile" is an absence; a profile with a picture is the reference
    assert out == {STEAM: None, S2: None, S3: "e" * 40}
    assert [r for r in recorded if r[0] == "xml"] == [("xml", False, None), ("xml", True, None), ("xml", True, None)]
    # the breaker is re-checked AFTER the token wait, right before the request: nothing is sent past a pause
    bodies[:] = [b"<profile/>"]
    recorded = _breaker_spy(monkeypatch, [False, True])
    assert _run(main._pc_steam_fetch_refs([STEAM, S2])) == {} and bodies == [b"<profile/>"]
    assert recorded == [("wait", False, None)]
    # the keyed path re-checks it the same way: a pause during the wait leaves the rest unreached, not failed
    monkeypatch.setitem(main._pc_steam_xml, "forced", False)
    monkeypatch.setenv("STEAM_WEB_API_KEY", "k")
    recorded = _breaker_spy(monkeypatch, [True])
    assert _run(main._pc_steam_fetch_refs([STEAM])) == {} and bodies == [b"<profile/>"]


def test_the_sweep_never_claims_a_non_steam_id():
    """The eligibility text (the claim, the writer's revalidation, the render probe) admits exactly a public
    individual SteamID64: crossplay opponents carry sixteen- to twenty-digit ids from other platforms, and both URL
    builders refuse those. v4.13 (r14): the id clause is steamid64's SQL, written from the constants its Python
    validator reads, and the URL builders call that validator; test_steamid64.py holds the rule itself. The old
    7656119 prefix admitted ids below the interval and refused every account from 76561200000000000 up."""
    clause = steamid64.individual_id_sql("p.steam_id")
    assert main._PC_STEAM_ELIGIBLE_SQL.count(clause) == 1 and "~ '^7656119" not in main._PC_STEAM_ELIGIBLE_SQL
    assert not hasattr(pc_steam, "STEAM_ID_RE") and "STEAM_ID_RE" not in MAIN_SRC
    for sid in ("76561197960265728", "76561202255233023", "76561200000000000", STEAM, S2):
        assert pc_steam.profile_xml_url(sid) == f"https://steamcommunity.com/profiles/{sid}?xml=1"
        assert pc_steam.summaries_url("k", [STEAM, sid]).endswith(f"steamids={STEAM}%2C{sid}")
    for bad in ("76561197960265727", "76561202255233024", "76561190000000001", STEAM + "\n", "2535425419861127",
                "14732509580164257529", "765611980404106530", "abcd", "", None):
        with pytest.raises(ValueError):
            pc_steam.profile_xml_url(bad)
        with pytest.raises(ValueError):
            pc_steam.summaries_url("k", [STEAM, bad])
    # ...and both builders over every spelling steamid64_pg_parity holds the validator and PostgreSQL to, not a
    # hand-picked few: 22 the rule refuses, 5 it admits. A builder drifting to the form, a prefix, or the
    # interval read through str.isdigit() and int(), sends a request for one of those 22 or refuses one of the 5.
    assert (len(VECTORS), sum(1 for _, ok in VECTORS if ok)) == (27, 5)
    for text, ok in VECTORS:
        if ok:
            assert pc_steam.profile_xml_url(text) == f"https://steamcommunity.com/profiles/{text}?xml=1"
            assert pc_steam.summaries_url("k", [STEAM, text]).endswith(f"steamids={STEAM}%2C{text}")
        else:
            with pytest.raises(ValueError):
                pc_steam.profile_xml_url(text)
            with pytest.raises(ValueError):
                pc_steam.summaries_url("k", [STEAM, text])


def test_the_sweep_only_asks_steam_about_players_the_pool_can_put_on_a_card():
    """2026-09-15 coherence r3: the sweep exists to give a CARD SUBJECT a picture, so its eligibility text
    carries the pool's mod-runner clause and not the id clause alone. Measured on the primary 2026-09-16,
    while the text still carried the id half by itself: 3471 stored pictures against the 473 players the
    merged word admits -- roughly 89% of a rate-limited Steam budget, and of the writes it makes, spent on
    rows that cannot appear on a card. The claim's ordering only partly self-corrects that: it puts the
    current snapshot's members ahead of everyone else, but never-attempted rows sort ahead of BOTH.

    The containment runs ONE way: every clause the POOL word carries is a clause of the sweep's text, in the
    pool word's own spelling, so the narrowing drops non-members and nothing else and the two texts cannot
    drift into meaning different things. The reverse is FALSE and deliberate -- the sweep carries a FIFTH
    clause the pool word does not, the admin picture lock -- so "every pool member is eligible", which this
    docstring claimed until 2026-09-16, is not true of a subject inside a clear's lock window: that subject is
    a pool member with both portrait hashes NULLed and no refill coming, which is exactly what the clear was
    asked for. Checked below as containment in one direction PLUS an exact account of the extra clause, so
    neither text can gain a clause nobody named here."""
    import re
    eli = main._PC_STEAM_ELIGIBLE_SQL
    word = main._PC_POOL_MEMBER_SQL
    assert eli.count("p.mod_seen_at IS NOT NULL") == 1
    shared = ("p.deleted_at IS NULL", "p.mod_seen_at IS NOT NULL",
              steamid64.individual_id_sql("p.steam_id"),
              main._PC_NOT_BANNED_SQL.format(a="p"))
    for clause in shared:
        assert word.count(clause) == 1 and eli.count(clause) == 1, clause
    # the fifth clause, named: in the sweep, absent from the pool word
    lock = "(p.pc_game_portrait_locked_until IS NULL OR p.pc_game_portrait_locked_until < now())"
    assert eli.count(lock) == 1 and lock not in word
    # ...and there is no SIXTH in either text. Strike out every clause named
    # above and only the conjunction scaffolding may remain, so a clause added
    # to either text -- which is how a pool member could start being skipped
    # without anyone saying so -- leaves a residue here.
    def residue(sql_text, clauses):
        for c in clauses:
            sql_text = sql_text.replace(c, "", 1)
        return re.sub(r"[\s()]|AND", "", sql_text)
    assert residue(eli, shared + (lock,)) == "", residue(eli, shared + (lock,))
    assert residue(word, shared) == "", residue(word, shared)
    # the sweep is NOT a pool membership reader: it decides whom to ask Steam about, and
    # interpolating the whole word would bring a second ban clause with it
    assert "_PC_POOL_MEMBER_SQL" not in inspect.getsource(main._pc_steam_claim)
    # ...and eligibility keeps ONE meaning: the definition plus its three readers, no fourth text
    code = _main_code()
    assert code.count("_PC_STEAM_ELIGIBLE_SQL") == 4
    assert code.count("_PC_STEAM_ELIGIBLE_SQL = ") == 1
    for fn in (main._pc_steam_claim, main._pc_steam_write, main._pc_steam_render_probe):
        assert inspect.getsource(fn).count("_PC_STEAM_ELIGIBLE_SQL") == 1, fn.__name__


def test_a_non_steam_id_costs_only_its_own_row_on_both_paths(monkeypatch):
    """One non-Steam id in a chunk used to make the keyed URL builder refuse the WHOLE chunk (a ValueError, not a
    feed error) and the batch die with no verdict for its other rows; the XML path's builder refuses per id the
    same way (2026-09-13). Now such an id is its own absence, no request is made for it, and the rest of the
    batch is fetched."""
    xbox, other = "2535425419861127", "14732509580164257529"
    monkeypatch.setattr(main._pc_steam_breaker, "paused", lambda now=None: False)
    monkeypatch.setattr(main._pc_steam_breaker, "record", lambda *a, **k: None)

    async def wait(priority=False, deadline=None):
        return True
    monkeypatch.setattr(main, "_pc_steam_wait", wait)
    # the keyed path: ONE call carrying the Steam ids only; the non-Steam ids absent without a request
    monkeypatch.setitem(main._pc_steam_xml, "forced", False)
    monkeypatch.setitem(main._pc_steam_xml, "refusals", 0)
    monkeypatch.setenv("STEAM_WEB_API_KEY", "k")
    urls = []
    body = ('{"response":{"players":['
            f'{{"steamid":"{STEAM}","avatarfull":"https://avatars.steamstatic.com/{"e" * 40}_full.jpg"}},'
            f'{{"steamid":"{S2}","avatarfull":"https://avatars.steamstatic.com/{"f" * 40}_full.jpg"}}]}}}}').encode()

    def get(url, **kw):
        urls.append(url)
        return body
    monkeypatch.setattr(pc_steam, "http_get", get)
    out = _run(main._pc_steam_fetch_refs([STEAM, xbox, S2, other]))
    assert out == {STEAM: "e" * 40, S2: "f" * 40, xbox: None, other: None}
    assert len(urls) == 1 and STEAM in urls[0] and S2 in urls[0] and xbox not in urls[0] and other not in urls[0]
    # every id non-Steam: no request at all, every row its own absence
    urls.clear()
    assert _run(main._pc_steam_fetch_refs([xbox, other])) == {xbox: None, other: None} and urls == []
    # the XML path: the Steam id is fetched, the non-Steam id is not
    monkeypatch.setitem(main._pc_steam_xml, "forced", True)
    bodies = [f"<profile><avatarFull>https://avatars.steamstatic.com/{'e' * 40}_full.jpg</avatarFull></profile>".encode()]
    monkeypatch.setattr(pc_steam, "http_get", lambda url, **kw: bodies.pop(0))
    assert _run(main._pc_steam_fetch_refs([xbox, STEAM])) == {xbox: None, STEAM: "e" * 40} and bodies == []
    # the URL builders still refuse a non-Steam id on their own: the guard above is what keeps them unreached
    with pytest.raises(ValueError):
        pc_steam.summaries_url("k", [STEAM, xbox])
    with pytest.raises(ValueError):
        pc_steam.profile_xml_url(xbox)


def test_the_batch_fetches_the_whole_interval_and_refuses_its_neighbours(monkeypatch):
    """v4.13 (r14): the batch's partition reads the shared validator, so both boundaries and an id past the old
    7656119 prefix go out in the keyed chunk, in claim order, and both neighbours are their own absence with no
    request made for them."""
    lo, hi, high = "76561197960265728", "76561202255233023", "76561200000000000"
    below, above = "76561197960265727", "76561202255233024"
    monkeypatch.setattr(main._pc_steam_breaker, "paused", lambda now=None: False)
    monkeypatch.setattr(main._pc_steam_breaker, "record", lambda *a, **k: None)

    async def wait(priority=False, deadline=None):
        return True
    monkeypatch.setattr(main, "_pc_steam_wait", wait)
    monkeypatch.setitem(main._pc_steam_xml, "forced", False)
    monkeypatch.setitem(main._pc_steam_xml, "refusals", 0)
    monkeypatch.setenv("STEAM_WEB_API_KEY", "k")
    urls = []
    body = ('{"response":{"players":['
            + ",".join(f'{{"steamid":"{s}","avatarhash":"{"e" * 40}"}}' for s in (lo, hi, high))
            + ']}}').encode()

    def get(url, **kw):
        urls.append(url)
        return body
    monkeypatch.setattr(pc_steam, "http_get", get)
    out = _run(main._pc_steam_fetch_refs([below, lo, high, hi, above]))
    assert out == {lo: "e" * 40, high: "e" * 40, hi: "e" * 40, below: None, above: None}
    assert len(urls) == 1 and urls[0].endswith(f"steamids={lo}%2C{high}%2C{hi}")
    # ...and the same partition over every spelling steamid64_pg_parity holds the validator and PostgreSQL to,
    # not a hand-picked few: ONE chunk carrying the 5 the rule admits, in claim order, while the 22 it refuses
    # are each their own absence with no request made for any of them. A partition drifting to the form, a
    # prefix, or the interval read through str.isdigit() and int() puts one of those 22 into the chunk.
    urls.clear()
    admitted = [text for text, ok in VECTORS if ok]
    body = ('{"response":{"players":['
            + ",".join(f'{{"steamid":"{s}","avatarhash":"{"e" * 40}"}}' for s in admitted)
            + ']}}').encode()
    out = _run(main._pc_steam_fetch_refs([text for text, _ in VECTORS]))
    assert out == {text: ("e" * 40 if ok else None) for text, ok in VECTORS}
    assert len(urls) == 1 and urls[0].endswith("steamids=" + "%2C".join(admitted))


def test_a_refused_id_ends_ineligible_with_nothing_written_on_both_paths(monkeypatch):
    """v4.13 (r14): an id the Steam-id rule refuses -- the interval's lower neighbour, which the old prefix
    admitted -- followed from the batch's URL step through the processor to the writer, in one batch with the
    interval's lower boundary. On the keyed path and on the profile XML path the URL step makes no request for
    the refused id and answers it with its own absence, while the boundary is fetched; the processor passes the
    absence on as `failed`. The writer's revalidation row carries, as `eligible`, PostgreSQL's recorded verdict
    for that id under the id clause of the eligibility text (steamid64_pg_parity's committed answer, which
    test_steamid64 ties to the SQL the text is built from), and it refuses the id: the disposition is
    `ineligible` -- no UPDATE, no blob, no rollback, no heartbeat -- and the boundary's plate is written. Under
    a text that admitted the id the same absence is the `failed` backoff, which the last half shows: widening
    the rule in Python or in SQL turns this test red."""
    lo, below = "76561197960265728", "76561197960265727"
    monkeypatch.setattr(main._pc_steam_breaker, "paused", lambda now=None: False)
    monkeypatch.setattr(main._pc_steam_breaker, "record", lambda *a, **k: None)

    async def wait(priority=False, deadline=None):
        return True
    monkeypatch.setattr(main, "_pc_steam_wait", wait)
    monkeypatch.setitem(main._pc_steam_xml, "refusals", 0)
    monkeypatch.setenv("STEAM_WEB_API_KEY", "k")
    marks = []
    monkeypatch.setattr(main, "_pc_steam_mark_clean", lambda: marks.append(1))
    urls = []
    dbs = []

    def session():
        # claim order: the refused id's write transaction first, then the boundary's
        sid = (below, lo)[len(dbs) % 2]
        dbs.append(_wdb(row=_wrow(eligible=steamid64_pg_parity.pg_verdict(sid))))
        return dbs[-1]
    monkeypatch.setattr(database, "async_session", session)
    keyed = ('{"response":{"players":[' f'{{"steamid":"{lo}","avatarhash":"{DEFAULT}"}}' ']}}').encode()
    xml = f"<profile><avatarFull>https://avatars.steamstatic.com/{DEFAULT}_full.jpg</avatarFull></profile>".encode()
    for forced, body, url in ((False, keyed, f"{pc_steam.SUMMARIES_URL}?key=k&steamids={lo}"),
                              (True, xml, f"https://steamcommunity.com/profiles/{lo}?xml=1")):
        monkeypatch.setitem(main._pc_steam_xml, "forced", forced)
        monkeypatch.setattr(pc_steam, "http_get", lambda u, **kw: urls.append(u) or body)
        urls.clear()
        dbs.clear()
        marks.clear()
        claimed = [_claimed(steam_id=below), _claimed(steam_id=lo)]
        assert _run(main._pc_steam_process(claimed)) == {"ineligible": 1, "plate": 1}, forced
        assert urls == [url], (forced, urls)
        refused, boundary = dbs
        assert refused.count("AS eligible") == 1 and refused.count("UPDATE players") == 0, forced
        assert refused.count("INSERT INTO pc_portraits") == 0 and refused.rolled_back == 0, forced
        assert boundary.count("UPDATE players SET pc_steam_portrait_hash = NULL") == 1, forced
        assert marks == [1], forced   # the boundary's committed plate; `ineligible` earns no heartbeat
    # the contrast: the same absence on a row the text admits is the `failed` backoff the processor asked for
    monkeypatch.setitem(main._pc_steam_xml, "forced", False)
    urls.clear()
    dbs.clear()

    def admitted():
        dbs.append(_wdb())
        return dbs[-1]
    monkeypatch.setattr(database, "async_session", admitted)
    assert _run(main._pc_steam_process([_claimed(steam_id=below)])) == {"backoff": 1}
    assert dbs[0].count("pc_steam_portrait_fail = CAST(:fail AS smallint)") == 1 and urls == []


# ── priming ────────────────────────────────────────────────────────────

def test_priming_waits_for_its_deadline_and_the_attempt_finishes_behind_it(monkeypatch):
    claims, ran = [], []

    async def claim(db, limit, ids=None, never_only=False):
        claims.append((limit, list(ids), never_only))
        return [_claimed()]

    async def process(claimed, priority=False):
        await asyncio.sleep(0.25)
        ran.append(priority)
        return {"applied": 1}
    monkeypatch.setattr(main, "_pc_steam_claim", claim)
    monkeypatch.setattr(main, "_pc_steam_process", process)
    monkeypatch.setattr(database, "async_session", lambda: Scripted({}))
    monkeypatch.setattr(main, "IS_REPLICA", False)
    monkeypatch.delenv("PC_STEAM_SWEEP", raising=False)

    async def body():
        t0 = time.monotonic()
        await main._pc_steam_prime([str(PID)], deadline=0.05)
        waited = time.monotonic() - t0
        assert ran == [] and len(main._pc_steam_tasks) == 1     # past the deadline the attempt is still running
        await asyncio.sleep(0.4)
        assert ran == [True] and not main._pc_steam_tasks       # ... and finishes under the claim it holds
        return waited
    waited = _run(body())
    assert 0.04 <= waited < 0.2
    assert claims == [(1, [str(PID)], True)]   # the priming path claims only the never attempted, only these
    # inside the deadline the caller sees the result
    async def quick(claimed, priority=False):
        ran.append("quick")
        return {"applied": 1}
    monkeypatch.setattr(main, "_pc_steam_process", quick)
    _run(main._pc_steam_prime([str(PID)], deadline=1.0))
    assert ran[-1] == "quick" and not main._pc_steam_tasks
    # no-ops: nothing to prime, the standby, the sweep paused
    claims.clear()
    _run(main._pc_steam_prime([]))
    monkeypatch.setattr(main, "IS_REPLICA", True)
    _run(main._pc_steam_prime([str(PID)]))
    monkeypatch.setattr(main, "IS_REPLICA", False)
    monkeypatch.setenv("PC_STEAM_SWEEP", "off")
    _run(main._pc_steam_prime([str(PID)]))
    assert claims == []
    # pack open (after its commit, best effort), the committed answer that every replay and the
    # result route share (a repeated pack id, a repeated nonce, /pc/packs/result), the /card preview
    assert MAIN_SRC.count("await _pc_steam_prime(") == 3
    opened = inspect.getsource(main._pc_open_for)
    assert opened.count("await _pc_steam_prime(subjects)") == 1
    assert opened.count("await _pc_committed_answer(db, row, locale)") == 3   # the void and both replays
    assert "await _pc_committed_answer(db, row, _pc_locale(request))" in inspect.getsource(main.pc_pack_result)
    committed = inspect.getsource(main._pc_committed_answer)
    replay = 'await _pc_steam_prime(await _pc_pack_subjects(db, str(row["id"])))'
    assert committed.count(replay) == 1
    # a replay primes under the done check and BEFORE its answer is built (v4 section 5)
    i = committed.index(replay)
    assert committed.rfind('if row["status"] == "done":', 0, i) > committed.rfind("await _pc_pack_answer(", 0, i)
    assert 0 < committed.find("await _pc_pack_answer(", i)


# ── the sweep's words ──────────────────────────────────────────────────

def test_the_sweep_word_is_earned_by_completed_work(monkeypatch):
    st = main._PC_STEAM_SWEEP_STATE
    monkeypatch.setitem(st, "clean_at", None)
    monkeypatch.setitem(st, "started_at", None)   # a loop start stamped earlier ages into `stale` (v4.1 §2)
    monkeypatch.setitem(st, "error", None)
    monkeypatch.setattr(main, "IS_REPLICA", False)
    monkeypatch.delenv("PC_STEAM_SWEEP", raising=False)
    assert main._pc_steam_sweep_word() == "starting"
    monkeypatch.setitem(st, "error", "OperationalError")
    assert main._pc_steam_sweep_word() == "faulted:OperationalError"
    monkeypatch.setitem(st, "error", None)
    monkeypatch.setitem(st, "clean_at", time.monotonic() - main._PC_STEAM_STALE_S - 1)
    assert main._pc_steam_sweep_word() == "stale"
    main._pc_steam_mark_clean()
    assert main._pc_steam_sweep_word() == "running" and st["error"] is None
    monkeypatch.setenv("PC_STEAM_SWEEP", "off")
    assert main._pc_steam_sweep_word() == "paused:env"
    monkeypatch.setattr(main, "IS_REPLICA", True)
    assert main._pc_steam_sweep_word() == "standby"


def test_a_batch_that_raises_faults_the_word_until_a_later_batch_completes(monkeypatch):
    st = main._PC_STEAM_SWEEP_STATE
    monkeypatch.setitem(st, "clean_at", None)
    monkeypatch.setitem(st, "error", None)
    monkeypatch.setattr(main, "IS_REPLICA", False)
    monkeypatch.delenv("PC_STEAM_SWEEP", raising=False)
    monkeypatch.setattr(main, "_PC_STEAM_BOOT_DELAY_S", 0)
    monkeypatch.setattr(main, "_PC_STEAM_IDLE_S", 0.01)
    calls = []

    async def claim(db, limit, ids=None, never_only=False):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("claim")
        return []
    monkeypatch.setattr(main, "_pc_steam_claim", claim)
    monkeypatch.setattr(database, "async_session", lambda: Scripted({}))

    async def body():
        task = asyncio.create_task(main._pc_steam_sweep_loop())
        await asyncio.sleep(0.015)
        faulted = main._pc_steam_sweep_word()
        await asyncio.sleep(0.08)
        later = main._pc_steam_sweep_word()
        task.cancel()
        return faulted, later
    faulted, later = _run(body())
    assert faulted == "faulted:RuntimeError" and later == "running" and len(calls) >= 3
    # an empty batch is completed work too
    monkeypatch.setitem(st, "clean_at", None)
    assert _run(main._pc_steam_batch()) == 0 and main._pc_steam_sweep_word() == "running"


def test_a_batch_whose_writes_all_failed_faults_the_word_and_a_refused_feed_leaves_it_to_age(monkeypatch):
    st = main._PC_STEAM_SWEEP_STATE
    monkeypatch.setitem(st, "clean_at", None)
    monkeypatch.setitem(st, "started_at", None)
    monkeypatch.setitem(st, "error", None)
    monkeypatch.setattr(main, "IS_REPLICA", False)
    monkeypatch.delenv("PC_STEAM_SWEEP", raising=False)

    async def claim(db, limit, ids=None, never_only=False):
        return [_claimed(), _claimed(steam_id=S2)]
    monkeypatch.setattr(main, "_pc_steam_claim", claim)
    monkeypatch.setattr(database, "async_session", lambda: Scripted({}))
    outcomes = [{"error": 2, "error_class": "OperationalError"}]

    async def process(claimed, priority=False):
        return outcomes[-1]
    monkeypatch.setattr(main, "_pc_steam_process", process)
    # every verdict of the batch failed to commit: faulted, and no heartbeat
    assert _run(main._pc_steam_batch()) == 2
    assert main._pc_steam_sweep_word() == "faulted:write:OperationalError" and st["clean_at"] is None
    # the feed refusing the batch or the breaker cutting it: nothing completed, the fault stands
    outcomes.append({"batch_failed": 2})
    _run(main._pc_steam_batch())
    assert main._pc_steam_sweep_word() == "faulted:write:OperationalError"
    monkeypatch.setitem(st, "error", None)
    outcomes.append({"unreached": 2})
    _run(main._pc_steam_batch())
    assert main._pc_steam_sweep_word() == "starting" and st["clean_at"] is None   # ages into stale, never running
    monkeypatch.setitem(st, "started_at", time.monotonic() - main._PC_STEAM_STALE_S - 1)   # the loop started long ago
    assert main._pc_steam_sweep_word() == "stale"   # never-clean work ages from the loop's start (v4.1 §2)
    monkeypatch.setitem(st, "started_at", time.monotonic())
    assert main._pc_steam_sweep_word() == "starting"
    assert '_PC_STEAM_SWEEP_STATE["started_at"] = time.monotonic()' in inspect.getsource(main._pc_steam_sweep_loop)
    # a batch of dropped verdicts is not completed work either
    outcomes.append({"moved": 1, "ineligible": 1})
    _run(main._pc_steam_batch())
    assert st["clean_at"] is None
    # one committed verdict clears a fault and earns running, whatever else the batch held
    monkeypatch.setitem(st, "error", "write:OperationalError")
    outcomes.append({"backoff": 1, "error": 1, "error_class": "OperationalError"})
    _run(main._pc_steam_batch())
    assert main._pc_steam_sweep_word() == "running" and st["error"] is None
    assert main._PC_STEAM_COMMITTED == frozenset({"applied", "plate", "touched", "backoff"})


# ── the render probe ───────────────────────────────────────────────────

def test_the_render_probe_composites_a_stored_steam_picture_or_says_why_not(monkeypatch):
    dbs = []

    def factory_for(*rows):
        def factory():
            dbs.append(Scripted({"SELECT p.display_name": [[r for r in rows if r]]}))
            return dbs[-1]
        return factory
    monkeypatch.setattr(database, "async_session", factory_for(None))
    assert _run(main._pc_steam_render_probe()) == "none"
    sub = {"display_name": "Sid", "subject_deleted": False, "subject_banned": False,
           "portrait_hash": None, "steam_portrait_hash": "s" * 64}
    calls = []

    async def pbytes(db, h):
        calls.append(("bytes", h))
        return b"blob"

    async def ctx(db, locale):
        calls.append(("ctx", locale))
        return {"labels": {"pc.edition": "Edition"}}

    async def pool(fn, *args, budget=None):
        calls.append(("render", fn, args))
        return b"\x89PNG\r\n\x1a\n" + b"rest"
    monkeypatch.setattr(main, "_pc_portrait_bytes", pbytes)
    monkeypatch.setattr(main, "_pc_face_ctx", ctx)
    monkeypatch.setattr(pc_portrait, "in_pool", pool)
    monkeypatch.setattr(database, "async_session", factory_for(sub))
    assert _run(main._pc_steam_render_probe()) == "ok"
    assert calls[0] == ("bytes", "s" * 64) and calls[1] == ("ctx", "en")
    kind, fn, args = calls[2]
    assert fn is main._pcf.render_face and args[1:] == ({"pc.edition": "Edition"}, b"blob", "card")
    assert args[0]["name"] == "Sid" and args[0]["subtitle"] is None and args[0]["band"] == "common"
    sql, params = dbs[-1].log[0]
    assert "WHERE p.pc_steam_portrait_hash IS NOT NULL AND p.pc_game_portrait_hash IS NULL" in sql
    # the sweep's own eligibility text (v4 §3): an open ban or a lock never becomes the probe's pick
    assert " ".join(main._PC_STEAM_ELIGIBLE_SQL.split()) in sql and "player_bans" in sql
    assert "ORDER BY p.pc_steam_portrait_at DESC NULLS LAST LIMIT CAST(:n AS integer)" in sql
    assert params == {"n": main._PC_STEAM_PROBE_CANDIDATES} == {"n": 5}
    assert " ".join(main._pc_portrait_resolve_cols("p").split()) in sql   # the face route's own resolver columns
    assert dbs[-1].count("INSERT") == 0 and dbs[-1].count("UPDATE") == 0
    # the resolver must agree that the pick's face IS the Steam picture; with no candidate resolving, say so
    monkeypatch.setattr(database, "async_session", factory_for({**sub, "subject_banned": True}))
    assert _run(main._pc_steam_render_probe()) == "failed:resolver"
    # the blob released between the two reads: the next candidate is tried, newest first
    released = {"s" * 64}

    async def some_gone(db, h):
        calls.append(("bytes", h))
        return None if h in released else b"blob"
    monkeypatch.setattr(main, "_pc_portrait_bytes", some_gone)
    calls.clear()
    monkeypatch.setattr(database, "async_session", factory_for(sub, {**sub, "steam_portrait_hash": "t" * 64}))
    assert _run(main._pc_steam_render_probe()) == "ok"
    assert calls[:2] == [("bytes", "s" * 64), ("bytes", "t" * 64)] and calls[3][2][2] == b"blob"
    # every candidate released: nothing to composite this pass
    released.add("t" * 64)
    assert _run(main._pc_steam_render_probe()) == "none"
    monkeypatch.setattr(main, "_pc_portrait_bytes", pbytes)
    monkeypatch.setattr(database, "async_session", factory_for(sub))
    assert _run(main._pc_steam_render_probe()) == "ok"
    # the renderer answering something that is not a PNG
    monkeypatch.setattr(main, "_pc_portrait_bytes", pbytes)

    async def junk(fn, *args, budget=None):
        return b"nope"
    monkeypatch.setattr(pc_portrait, "in_pool", junk)
    assert _run(main._pc_steam_render_probe()) == "failed:bytes"


TRAIN_BATCH = "sept14-gacha"   # the release-train entry THIS batch ships under
# The pool rule that entry expects: the rule the sept14 batch shipped. A later
# rule (4, migration 417) ships under its own entry; this one is history, so it
# is compared with its own number, not with the build's current constant.
TRAIN_POOL_RULE = 3


def _release_train():
    """The release train module itself, imported rather than string-sliced.

    It is local to the operating seat, so a machine without it skips. Reading
    the real BATCHES dict is what lets this test say WHICH entry an expectation
    sits in: a slice between two other batch names cannot, and one round put
    this batch's expectations inside the entry of a batch that had already
    shipped, where the text still satisfied the slice."""
    import importlib.util
    train = REPO / "scripts" / "deploy" / "release_train.py"
    if not train.exists():
        pytest.skip("the release train is local to the operating seat")
    spec = importlib.util.spec_from_file_location("release_train_under_test", train)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, train.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_network_program(monkeypatch):
    """No test in this module spawns curl, ssh or scp: a unit test asks no machine anything.

    Round 10 found one arm of the dry-run test reaching the LAN boxes with the
    control-route GETs a dry verify makes -- read-only, and still a unit test
    whose verdict depended on production answering. The spawn is refused AND
    recorded, and the record is asserted at teardown: the train turns a refused
    spawn into its own Fail, and a test waiting for a Fail must not be able to
    pass on this refusal instead of on the one it asserts."""
    import subprocess as _sp
    real, spawned = _sp.run, []

    def _guard(cmd, *args, **kw):
        first = cmd[0] if isinstance(cmd, (list, tuple)) and cmd else str(cmd).split(" ")[0]
        prog = os.path.basename(str(first)).lower().split(".")[0]
        if prog in ("curl", "ssh", "scp"):
            spawned.append(prog)
            raise OSError("a unit test does not spawn %s" % prog)
        return real(cmd, *args, **kw)

    monkeypatch.setattr(_sp, "run", _guard)
    yield spawned
    assert spawned == [], "this test tried to spawn %s" % ", ".join(spawned)


def _role_expect(entry, key):
    """Every health_expect entry for `key` that states a value per role."""
    return [e for e in entry["health_expect"] if isinstance(e, dict) and e.get("key") == key]


def test_health_carries_the_fold_marker_the_release_train_asserts_on_both_roles():
    """v4.13 §8: `pc_fold` exists only to be probed (#306). The release train requires it on BOTH api boxes: on
    the standby the sweep word reads the same on the build before this fold, and the replica write gate answers
    503 to every write before any handler, so a write probe cannot fail there. The marker is on the connected and
    on the degraded answer, declared on the response model (an undeclared keyword never reaches the response),
    read by nothing else, and the value the train expects for each role.

    The Sept 14 batch adds NO new route, so the fold marker and the pool rule are together the train's only
    build discriminator, and both are asserted here to sit in THIS batch's own entry -- exactly once each, on
    both roles. The already-shipped Sept 12 entry is asserted to carry neither: an expectation parked in a
    finished batch's entry makes that batch's re-verification fail against live boxes and attributes the failure
    to the wrong release."""
    fold = main.PC_FOLD
    assert isinstance(fold, str) and fold.startswith("v") and fold == fold.strip()

    class _Up:
        async def execute(self, *a, **k):
            return None

    class _Down:
        async def execute(self, *a, **k):
            raise OSError("database unreachable")
    up, down = _run(main.health_check(db=_Up())), _run(main.health_check(db=_Down()))
    assert (up.status, down.status) == ("ok", "degraded")
    assert up.model_dump()["pc_fold"] == fold                  # the connected answer, through the model
    assert down.model_dump()["pc_fold"] == fold                # the degraded answer too: which build is this box
    assert up.model_dump()["pc_pool_rule"] == main._PC_POOL_RULE
    assert down.model_dump()["pc_pool_rule"] == main._PC_POOL_RULE
    assert MAIN_SRC.count("PC_FOLD") == 3                      # defined once, reported twice, read by nothing else

    rt, src = _release_train()
    # A duplicate key in the dict literal would be silently shadowed by the
    # later one, and the structural reads below would never see the first.
    assert src.count('"%s": {' % TRAIN_BATCH) == 1
    assert TRAIN_BATCH in rt.BATCHES
    entry = rt.BATCHES[TRAIN_BATCH]

    # ...and the entry BINDS: an unreachable entry would satisfy every read above
    rt.select_batch(TRAIN_BATCH)
    assert rt.BRANCH == "claude/sept14-gacha-features"
    assert rt.NEW_ROUTES == []          # no new route: the markers are the whole discriminator
    assert rt.CODE_MARKERS == ["pc_fold", "pc_pool_rule"]
    assert rt.SMOKE_ROUTE and rt.SMOKE_ROUTE not in rt.NEW_ROUTES
    assert dict(rt.edge_markers()) == {"pc_fold": fold, "pc_pool_rule": TRAIN_POOL_RULE}
    assert main._PC_POOL_RULE >= TRAIN_POOL_RULE

    # the fold marker, exactly once, on both roles, in THIS batch's entry
    assert _role_expect(entry, "pc_fold") == [{"key": "pc_fold", "primary": fold, "standby": fold}]
    # the merged pool rule is the second, independent signal for the same
    # question (#438): with no new route a stale standby would otherwise answer
    # exactly like a fresh one (the bug #266 shape)
    assert _role_expect(entry, "pc_pool_rule") == [
        {"key": "pc_pool_rule", "primary": TRAIN_POOL_RULE, "standby": TRAIN_POOL_RULE}]

    # 321's own work, read back as a positive signal the feature EMITS (#438):
    # not "3 prints" but "every live rank-2 print", so a half-applied run reads 0
    # and a print discarded before the run (which 321 accepts, and which keeps
    # its epic payout) does not redden a correct deploy.
    rank2 = [q for _label, q, _min in entry["positive_sql"] if "pc_prints" in q]
    assert len(rank2) == 1 and "NOT EXISTS" in rank2[0] and "discarded_at IS NULL" in rank2[0]

    # the SHIPPED batch keeps its own expectations and gains none of ours
    shipped = rt.BATCHES["sept12-gacha"]
    assert _role_expect(shipped, "pc_fold") == [{"key": "pc_fold", "primary": "v4.13", "standby": "v4.13"}]
    assert _role_expect(shipped, "pc_pool_rule") == []
    assert [q for _l, q, _m in shipped["positive_sql"]] == [
        "SELECT count(*) FROM players WHERE pc_steam_portrait_hash IS NOT NULL;"]


def test_the_release_train_runs_a_batch_that_adds_no_route(monkeypatch):
    """A batch that adds no route is a first-class case, not a crash.

    `new_routes` was indexed unguarded (`NEW_ROUTES[0]` for the smoke route and for both edge probes) and mapped
    over in code_state, where `all([])` is True -- so an empty list raised IndexError before the train started,
    and where it did not, it made a box read as the new build and the old build at the same time. This drives the
    whole surface with no network: every batch binds, the verdicts come out of the health markers instead, and a
    no-route batch that names no marker is REFUSED rather than run with gates that cannot fail."""
    rt, _src = _release_train()

    # every batch in the table binds -- the new one and the three that shipped
    for name in sorted(rt.BATCHES):
        rt.select_batch(name)
        assert rt.SMOKE_ROUTE, name
        # one discriminator or another, never NONE. The json marker is the third:
        # a field on a route both builds answer, for a batch that adds neither a
        # route nor a health key. This line named only two of the three, so it
        # went red the moment a json-marker batch joined the table.
        assert rt.NEW_ROUTES or rt.CODE_MARKERS or rt.JSON_MARKERS, name

    rt.select_batch(TRAIN_BATCH)
    fold, rule = main.PC_FOLD, TRAIN_POOL_RULE
    new_build = {"pc_fold": fold, "pc_pool_rule": rule}
    old_build = {"pc_fold": "v4.13"}
    monkeypatch.setattr(rt, "http_code", lambda host, path, **kw: "200")

    for body, want in ((new_build, (True, False)),      # both markers matched: the new build
                       (old_build, (False, True)),      # neither matched: the old build
                       ({"pc_fold": fold}, (False, False)),   # one of each: UNKNOWN, never a build
                       ({}, (False, False))):           # health unreadable: UNKNOWN, not "old"
        monkeypatch.setattr(rt, "health_json", lambda host, _b=body: _b)
        for host in (rt.PRIMARY, rt.STANDBY):
            ok, present, absent, readings = rt.code_state(host)
            assert (present, absent) == want, (host, body)
            # the probe still REPORTS on both boxes, and names what it read:
            # one line per marker, or the reason there were no marker lines
            assert ok, host
            assert readings == (["pc_fold=%r (want %r)" % (body["pc_fold"], fold)]
                                + ["pc_pool_rule=%s (want %r)"
                                   % (repr(body["pc_pool_rule"]) if "pc_pool_rule" in body
                                      else "(absent)", rule)]
                                if body else ["/api/v1/health did not answer JSON"]), readings
    # a reading that names neither build is not a pass: nothing here is ever both
    assert not any(p and a for p, a, _r in
                   [rt.marker_state(h) for h in (rt.PRIMARY, rt.STANDBY)])

    # the routed path is probed too, from the markers the two roles agree on
    monkeypatch.setattr(rt, "health_json", lambda host, _b=new_build: _b)
    rt.assert_edge_runs_new_code()
    monkeypatch.setattr(rt, "health_json", lambda host, _b=old_build: _b)
    with pytest.raises(rt.Fail):
        rt.assert_edge_runs_new_code()
    monkeypatch.setattr(rt, "health_json", lambda host: {})
    with pytest.raises(rt.Fail):
        rt.assert_edge_runs_new_code()

    # ...and a no-route batch with no marker is refused before any phase runs
    for broken in ({"code_markers": []},                       # nothing to discriminate on
                   {"code_markers": ["pc_renderer_fp"]},       # present on the old build, no per-role value
                   {"smoke_route": None}):                     # no liveness probe left to borrow
        entry = dict(rt.BATCHES[TRAIN_BATCH])
        entry.update(broken)
        rt.BATCHES["_broken"] = entry
        with pytest.raises(rt.Fail):
            rt.select_batch("_broken")
        del rt.BATCHES["_broken"]


# ── the operating train's gates, driven with stubs (TRAIN-PARITY-1) ──────
#
# Every test below imports the release train placed at scripts/deploy/ of the
# tree it runs in and drives its functions; nothing leaves the machine. The
# world below stands in for every step that would: the controller lease, the
# plays, the local git mutators, the pushes, the migrations, the box probes.
# REPO is pointed at the test's temporary folder BEFORE a batch is selected,
# so every state file a phase writes lands there.

import contextlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

ABSENT_BATCH = "mscl"   # an entry with no migration and a skipped bot: the no-sql shape
JSON_BATCH = "bug392-server"   # an entry whose build discriminator is a json marker
NEWEST_THREE = ("mscl", "ban-cap", "qdig")   # the three newest entries when this item was written
PRECURSOR_SHA = "1" * 40
MERGE_SHA = "2" * 40
FORK_URL = "https://example.invalid/a-fork/a-repository.git"
_OLD = (True, False, True, ["marker at the old value"])
_NEW = (True, True, False, ["marker at the new value"])
_UNKNOWN = (True, False, False, ["one marker old and one new"])
_DOWN = (False, False, True, ["control answered 503"])
_TRAILER = "\n\nCo-Authored-By: A Test <test@example.invalid>"
UNKNOWN_COMMIT_SHA = "f" * 40   # HEAD after a commit whose message is not a text the train derives
_DROP = object()


def _rt_committed_text(message):
    """The whole text a commit of the train must hand git: the derived message, the trailer after it, the last
    line completed as `git commit -m` completes it. Written here and not read from the train, so a train that
    drops or changes any part of it makes a commit that no check recognises."""
    text = message + _TRAILER
    return text if text.endswith("\n") else text + "\n"


def _rt_done(kw, stdout, stderr="", rc=0):
    """A finished process as subprocess.run hands it back: text when the caller asked for text, bytes
    otherwise, standard output and standard error kept apart."""
    text = kw.get("text") or kw.get("universal_newlines") or kw.get("encoding")
    conv = (lambda v: v) if text else (lambda v: v.encode("utf-8"))
    return SimpleNamespace(returncode=rc, stdout=conv(stdout), stderr=conv(stderr))


def _rt_minted(rt, stamp="20261118_112001", label=None):
    """The name the snapshot wrapper mints: cc_, the label with every character
    outside [a-zA-Z0-9_-] made `_`, two underscores, the host's local stamp."""
    label = rt.SNAPSHOT_LABEL if label is None else label
    return "cc_%s__%s" % (re.sub(r"[^a-zA-Z0-9_-]", "_", label), stamp)


def _rt_utc(hours_ago=0.0):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rt_fresh(rt, hours_ago=1.0, **over):
    """A snapshot record that stands: the minted form, recorded by the tool's own UTC clock."""
    st = {"snapshot": _rt_minted(rt), "snapshot_recorded_at": _rt_utc(hours_ago)}
    st.update(over)
    return st


def _rt_bind(monkeypatch, rt, name, where):
    """Select `name` with every state file under `where`."""
    monkeypatch.setattr(rt, "REPO", str(where / "repo"))
    monkeypatch.setattr(rt, "BUILD_CHECK_WAIT_S", 0, raising=False)
    rt.select_batch(name)
    assert rt.STATE_PATH.startswith(str(where))
    return rt.STATE_PATH


def _rt_files(where):
    return sorted(str(p) for p in Path(where).rglob("*") if p.is_file())


def _rt_pair(rt, sha):
    """The two deploys of one sha, in the order the train must make them: the primary's selector first."""
    return [("deploy", rt.PRIMARY_SELECTOR, sha), ("deploy", rt.STANDBY_SELECTOR, sha)]


def test_the_two_box_selectors_are_two_distinct_names():
    """The pair every deploy assert is built from: two non-empty strings, and not the same one twice."""
    rt, _src = _release_train()
    p, s = rt.PRIMARY_SELECTOR, rt.STANDBY_SELECTOR
    assert isinstance(p, str) and isinstance(s, str) and p and s and p != s


def _rt_default_serve(host, sha):
    return _NEW if sha == MERGE_SHA else _OLD


class _RtWorld:
    """Everything the train would ask of another machine, answered here and
    recorded in order. A box serves what `serve(host, the sha its last deploy
    carried)` says; a commit whose message is the merge message makes HEAD the
    merge, any other commit the precursor."""

    def __init__(self, rt):
        self.rt = rt
        self.calls = []
        self.commits = []
        self.deployed = {}
        self.head = "0" * 40
        self.branch_tip = rt.REVIEWED_TIP or "e" * 40
        self.second_parent = rt.REVIEWED_TIP or "e" * 40
        self.push_urls = [getattr(rt, "ORIGIN_PUSH_URL", "the module states no push address")]
        self.push_sequence = []
        self.push_address_fails = False
        self.snapshot_out = None
        self.serve = _rt_default_serve
        self.raise_on = {}
        self.http = {}

    def kinds(self, *wanted):
        return [c for c in self.calls if c[0] in wanted]

    def run(self, cmd, check=True, want_rc=False, **kw):
        c = list(cmd)
        self.calls.append(("run",) + tuple(c[:4]))
        out = None
        if c[:2] == ["git", "rev-parse"]:
            ref = c[2]
            out = {self.rt.BRANCH: self.branch_tip, "HEAD": self.head,
                   "HEAD^2": self.second_parent}.get(ref, "b" * 40 if ":" in ref else None)
        elif c[:3] == ["git", "--no-optional-locks", "status"]:
            out = ""
        elif c[:3] == ["python", "-m", "pyflakes"]:
            out = ""
        if out is None:
            raise AssertionError("a command the stubbed train should not issue: %r" % (c,))
        return (out, 0) if want_rc else out

    def push_address(self, kw):
        """`git remote get-url --push --all origin` as the process call answers it: one line per destination
        on standard output, return code 2 when the world says the question fails."""
        self.calls.append(("push-address",))
        urls = self.push_sequence.pop(0) if self.push_sequence else self.push_urls
        return _rt_done(kw, "".join(u + "\n" for u in urls), "", 2 if self.push_address_fails else 0)

    def zap(self, playbook, limit=None, extra=None, **kw):
        if playbook == "snapshot-scr.yml":
            self.calls.append(("snapshot",))
            if self.snapshot_out is not None:
                return self.snapshot_out
            return ("TASK [snapshot] ok: %s\nPLAY RECAP box : ok=2 changed=1 unreachable=0 failed=0"
                    % _rt_minted(self.rt))
        sha = extra.split("scr_deploy_ref=")[1].split()[0]
        self.calls.append(("deploy", limit, sha))
        if self.raise_on.get("deploy"):
            raise self.raise_on["deploy"]
        self.deployed[self.rt.PRIMARY if limit == self.rt.PRIMARY_SELECTOR else self.rt.STANDBY] = sha
        return "PLAY RECAP box : ok=9 changed=2 unreachable=0 failed=0"

    def git_child(self, lease, argv):
        self.calls.append(("git",) + tuple(argv[:3]))
        if argv[:2] == ["git", "commit"]:
            # CMDLINE-1: both commits hand git their message in a file (`git commit -F PATH`), read here at the
            # call. The message must be the WHOLE text the phase derived; any other form or text moves HEAD to a
            # sha no check expects, and is recorded in self.commits.
            text = None
            if len(argv) == 4 and argv[2] == "-F":
                with open(argv[3], encoding="utf-8", newline="") as fh:
                    text = fh.read()
            self.commits.append((tuple(argv[2:]), text))
            if text == _rt_committed_text(self.rt.MERGE_MESSAGE):
                self.head = MERGE_SHA
            elif text == _rt_committed_text(self.rt.PRECURSOR_MESSAGE):
                self.head = PRECURSOR_SHA
            else:
                self.head = UNKNOWN_COMMIT_SHA
        return ""

    def blocking_child(self, lease, step, argv, kind, timeout=None):
        self.calls.append((kind, step))
        if self.raise_on.get(kind):
            raise self.raise_on[kind]
        return ("Container comp-rounds-bot  Started" if kind == "bot" else "main -> main"), 0

    def migrate_child(self, lease, f):
        self.calls.append(("migrate", f))
        if self.raise_on.get("migrate"):
            raise self.raise_on["migrate"]
        return "BEGIN\nCOMMIT"

    def code_state(self, host):
        self.calls.append(("read", host))
        return self.serve(host, self.deployed.get(host))


def _rt_world(monkeypatch, rt):
    w = _RtWorld(rt)
    for name in ("run", "zap", "git_child", "blocking_child", "migrate_child", "code_state"):
        monkeypatch.setattr(rt, name, getattr(w, name))
    monkeypatch.setattr(rt, "controller_lease_session",
                        lambda what, **kw: contextlib.nullcontext("lease"))
    monkeypatch.setattr(rt, "derive_trailer_suffix", lambda branch: _TRAILER)
    monkeypatch.setattr(rt, "train_token_write", lambda phase: None)
    monkeypatch.setattr(rt, "train_token_release", lambda: None)
    for name in ("assert_control", "assert_route_probes", "assert_health_keys"):
        monkeypatch.setattr(rt, name, lambda *a, **kw: None)
    monkeypatch.setattr(rt, "assert_edge_runs_new_code", lambda: None)
    monkeypatch.setattr(rt, "assert_positive_signals", lambda: None)
    monkeypatch.setattr(rt, "http_code", lambda host, path, **kw: w.http.get(path, "200"))
    monkeypatch.setattr(rt, "schema_state", lambda host: (
        list(rt.EXPECT_TABLES), ["%s.%s" % p for p in rt.EXPECT_COLUMNS]))
    monkeypatch.setattr(rt, "index_state", lambda host: list(rt.EXPECT_INDEXES))
    monkeypatch.setattr(rt, "sql", lambda host, query: "0")
    monkeypatch.setattr(rt, "_bot_witness", lambda **kw: w.calls.append(("witness",)))
    import subprocess as _sp
    inner = _sp.run

    def cat_file(cmd, *a, **kw):
        # the precursor asks `git cat-file -e <branch>:<file>` directly
        if isinstance(cmd, (list, tuple)) and list(cmd[:3]) == ["git", "cat-file", "-e"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if isinstance(cmd, (list, tuple)) and list(cmd[:5]) == ["git", "remote", "get-url", "--push", "--all"]:
            return w.push_address(kw)
        return inner(cmd, *a, **kw)
    monkeypatch.setattr(_sp, "run", cat_file)
    return w


GO, PLAN = SimpleNamespace(go=True), SimpleNamespace(go=False)


# ── slice 1: deploy truth ─────────────────────────────────────────────────


def test_a_batch_with_no_migration_skips_three_phases_and_moves_the_negative_control(monkeypatch, capsys,
                                                                                       tmp_path):
    """A batch carrying no sql is legal; its skips are printed, and its negative control moves to the code phase.

    With no schema moving there is no precursor, so the precursor deploy -- the one moment the train saw its
    discriminator answer OLD -- never happens. Without that reading the code phase's postcondition is a check
    never seen to fail. So for such a batch both boxes are read before the merge and before any deploy, every
    reading that is not OLD stops the train with nothing merged, and the OLD reading is recorded."""
    rt, _src = _release_train()
    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path)
    w = _rt_world(monkeypatch, rt)
    assert rt.ALL_SQL == [] and rt.SCHEMA_SQL == rt.I18N_SQL == rt.BACKFILL_SQL == []
    assert rt.BOT_SKIP_REASON and not rt.DEPLOY_BOT

    # the skip half: the precursor and its deploy print their skip and record nothing;
    # the schema phase applies nothing and records its postcondition
    st = _rt_fresh(rt)
    rt.phase_precursor(GO, st)
    rt.phase_deploy_precursor(GO, st)
    out = capsys.readouterr().out
    assert "precursor skipped" in out and "deploy-precursor skipped" in out, out
    assert "precursor_sha" not in st
    rt.phase_schema(GO, st)
    assert st["schema_done"] is True
    assert w.kinds("deploy", "git", "push", "migrate", "snapshot") == []

    # the plan names the control, both boxes and the reading, BEFORE the merge it guards
    rt.phase_code(PLAN, dict(st))
    out = capsys.readouterr().out
    assert "negative control" in out and rt.PRIMARY in out and rt.STANDBY in out and "OLD" in out, out
    assert out.index("negative control") < out.index("git merge --no-ff --no-commit %s" % rt.BRANCH), out

    # under --go it runs on both boxes before anything is merged, and stops on every reading that is not OLD
    for verdict, fragment in ((_NEW, "it already runs the new build"),
                              (_UNKNOWN, "the state is UNKNOWN"),
                              (_DOWN, "is not 200 before the code deploy")):
        w.serve = lambda host, sha, _v=verdict: _v
        del w.calls[:]
        trial = dict(st)
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(GO, trial)
        assert fragment in str(exc.value), (verdict, str(exc.value))
        assert w.kinds("git", "push", "deploy") == [], w.calls
        assert "pre_code_old_build" not in trial and "code_sha" not in trial

    # the OLD reading passes and is recorded; the merge and the deploy follow it
    w.serve = _rt_default_serve
    del w.calls[:]
    rt.phase_code(GO, st)
    assert st["pre_code_old_build"] is True and st["code_deployed"] is True
    first_git = w.calls.index(w.kinds("git")[0])
    assert w.calls[:2] == [("read", rt.PRIMARY), ("read", rt.STANDBY)], w.calls[:4]
    assert first_git > 1
    assert rt.load_state()["pre_code_old_build"] is True

    # the bot phase records its skip with the reason, and verify accepts that disposition
    rt.phase_i18n(GO, st)
    rt.phase_bot(GO, st)
    assert st["bot_deployed"] is False and st["bot_skipped"] == rt.BOT_SKIP_REASON
    assert w.kinds("bot") == []
    rt.phase_verify(GO, st)
    assert st["verified"] is True


def test_r10_m2_a_box_that_does_not_serve_the_new_build_stops_the_next_box_play(monkeypatch, tmp_path):
    """A primary that reports no failure and still serves the OLD build stops the standby's deploy.

    A play that reports failed=0 and a control route that answers 200 are both true of a container whose
    restart changed nothing. The build used to be read only after BOTH boxes had been deployed, so the box
    serving the routed reads was replaced too. Each box is now read alone, before the next box's play: the
    code phase asks for the NEW build, the precursor deploy for the OLD one."""
    rt, _src = _release_train()
    for i, (after, says) in enumerate(((_OLD, "it serves the OLD build"),
                                       (_UNKNOWN, "it reads as neither build"),
                                       (_DOWN, "the control route is not 200"))):
        _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / ("code%d" % i))
        w = _rt_world(monkeypatch, rt)
        w.head = MERGE_SHA
        w.serve = (lambda host, sha, _a=after:
                   _a if (host == rt.PRIMARY and sha == MERGE_SHA) else _rt_default_serve(host, sha))
        st = _rt_fresh(rt, schema_done=True, pre_code_old_build=True, code_sha=MERGE_SHA)
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(GO, st)
        assert says in str(exc.value) and "no further box is deployed" in str(exc.value), str(exc.value)
        assert w.kinds("deploy") == _rt_pair(rt, MERGE_SHA)[:1], w.calls
        assert "code_deployed" not in st

    # the precursor deploy: a primary that serves the NEW build after a files-only deploy
    _rt_bind(monkeypatch, rt, "ban-cap", tmp_path / "precursor")
    w = _rt_world(monkeypatch, rt)
    w.serve = lambda host, sha: _NEW if (host == rt.PRIMARY and sha == PRECURSOR_SHA) else _OLD
    with pytest.raises(rt.Fail) as exc:
        rt.phase_deploy_precursor(GO, _rt_fresh(rt, precursor_sha=PRECURSOR_SHA))
    assert "it serves the NEW build" in str(exc.value), str(exc.value)
    assert w.kinds("deploy") == _rt_pair(rt, PRECURSOR_SHA)[:1], w.calls

    # the inert twins: boxes that serve what they should are both deployed, primary first
    w.serve = _rt_default_serve
    del w.calls[:]
    rt.phase_deploy_precursor(GO, _rt_fresh(rt, precursor_sha=PRECURSOR_SHA))
    assert w.kinds("deploy") == _rt_pair(rt, PRECURSOR_SHA)
    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / "twin")
    w = _rt_world(monkeypatch, rt)
    w.head = MERGE_SHA
    st = _rt_fresh(rt, schema_done=True, pre_code_old_build=True, code_sha=MERGE_SHA)
    rt.phase_code(GO, st)
    assert st["code_deployed"] is True
    assert w.kinds("deploy") == _rt_pair(rt, MERGE_SHA)


def test_r10_m3_an_attempt_that_does_not_finish_leaves_a_word_no_gate_accepts(monkeypatch, tmp_path, capsys):
    """An earlier run's success word does not stand over an attempt that stopped half way.

    A re-run of a phase that died after its first mutating step left the previous run's True in the state
    file, and the next phase's gate then ran behind a deploy (or migration) that had not finished. Each
    phase that writes a success word (schema, code, i18n, bot, verify) now withdraws it, on disk, when a
    --go attempt starts, and writes it back only after its postcondition. Every arm reads the REAL state
    file back, as a later process would."""
    rt, _src = _release_train()

    def earlier(name, sub, **recorded):
        _rt_bind(monkeypatch, rt, name, tmp_path / sub)
        w = _rt_world(monkeypatch, rt)
        rt.save_state(_rt_fresh(rt, **recorded))
        return w, rt.load_state()

    # schema: the migration does not finish; the code phase then refuses
    w, st = earlier("qdig", "schema", schema_done=True)
    w.raise_on["migrate"] = rt.Fail("the migrate wrapper did not answer within its bound")
    with pytest.raises(rt.Fail):
        rt.phase_schema(GO, st)
    assert "schema_done" not in rt.load_state()
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(GO, rt.load_state())
    assert "schema phase has not passed" in str(exc.value)

    # code: the deploy does not finish; the recorded merge stays, the success word goes, i18n refuses
    w, st = earlier(ABSENT_BATCH, "code", schema_done=True, pre_code_old_build=True,
                    code_sha=MERGE_SHA, code_deployed=True)
    w.head = MERGE_SHA
    w.raise_on["deploy"] = rt.Fail("the deploy play did not answer within 1800 s")
    with pytest.raises(rt.Fail):
        rt.phase_code(GO, st)
    on_disk = rt.load_state()
    assert "code_deployed" not in on_disk and on_disk["code_sha"] == MERGE_SHA
    with pytest.raises(rt.Fail) as exc:
        rt.phase_i18n(GO, on_disk)
    assert "code SHA is not live" in str(exc.value)

    # i18n: a file does not apply; the bot phase then refuses
    w, st = earlier("ban-cap", "i18n", schema_done=True, code_sha=MERGE_SHA, code_deployed=True,
                    i18n_done=True)
    w.raise_on["migrate"] = rt.Fail("migration 418 reported an error")
    with pytest.raises(rt.Fail):
        rt.phase_i18n(GO, st)
    assert "i18n_done" not in rt.load_state()
    with pytest.raises(rt.Fail) as exc:
        rt.phase_bot(GO, rt.load_state())
    assert "i18n phase has not passed" in str(exc.value)

    # bot: the deploy does not finish; verify then refuses
    w, st = earlier("ban-cap", "bot", schema_done=True, code_sha=MERGE_SHA, code_deployed=True,
                    i18n_done=True, bot_deployed=True, bot_deployed_at=_rt_utc(30))
    w.raise_on["bot"] = rt.Fail("deploy-bot did not answer within 900 s")
    with pytest.raises(rt.Fail):
        rt.phase_bot(GO, st)
    assert not {"bot_deployed", "bot_deployed_at", "bot_skipped"} & set(rt.load_state())
    with pytest.raises(rt.Fail) as exc:
        rt.phase_verify(GO, rt.load_state())
    assert "the state records no bot deploy" in str(exc.value)

    # verify: a probe fails; the earlier `verified` does not stand
    w, st = earlier("ban-cap", "verify", schema_done=True, code_sha=MERGE_SHA, code_deployed=True,
                    i18n_done=True, bot_deployed=True, verified=True)
    w.deployed = {rt.PRIMARY: MERGE_SHA, rt.STANDBY: MERGE_SHA}
    w.http[rt.SMOKE_ROUTE] = "503"
    with pytest.raises(rt.Fail):
        rt.phase_verify(GO, st)
    assert "verified" not in rt.load_state()


def test_a_dry_run_writes_no_state_file(monkeypatch, tmp_path, capsys):
    """A dry run writes nothing: `plan`, and `run` without --go, from the first phase or from verify.

    The verify phase wrote `verified` at its end whether or not --go was given, so `plan --from verify`
    after the code phase recorded a verification of a rollout whose i18n and bot phases had never run.
    The boxes here already serve the new build, so every read-only probe a dry verify makes passes and
    the phase reaches its end: the only thing standing between it and the file is the --go check."""
    rt, _src = _release_train()
    for name in NEWEST_THREE:
        where = tmp_path / name
        path = _rt_bind(monkeypatch, rt, name, where)
        w = _rt_world(monkeypatch, rt)
        w.serve = lambda host, sha: _NEW
        argvs = (["plan"], ["run"], ["plan", "--from", "verify"], ["run", "--only", "verify"])
        for argv in argvs:
            monkeypatch.setattr(rt.sys, "argv", ["release_train.py"] + argv + ["--batch", name])
            assert rt.main() == 0, capsys.readouterr().out
            assert _rt_files(where) == [], (name, argv)
        assert w.kinds("deploy", "git", "push", "migrate", "bot", "snapshot", "witness") == [], w.calls
        # a state an earlier --go run left is read, and no dry run rewrites it
        w.head = MERGE_SHA
        os.makedirs(os.path.dirname(path))
        rt.save_state(_rt_fresh(rt, schema_done=True, code_sha=MERGE_SHA, code_deployed=True))
        before = Path(path).read_bytes()
        for argv in argvs:
            monkeypatch.setattr(rt.sys, "argv", ["release_train.py"] + argv + ["--batch", name])
            assert rt.main() == 0, capsys.readouterr().out
            assert Path(path).read_bytes() == before, (name, argv)
            assert _rt_files(where) == [path], (name, argv)


def test_verify_recomputes_the_bot_policy_from_the_selected_batch(monkeypatch, tmp_path):
    """`bot_skipped` in the state says what SOME earlier run did, never what this batch requires.

    The state file outlives the run that wrote it and an entry can change between them, so a batch that
    requires the bot could reach verify on an old truthy `bot_skipped` and record `verified` with no bot
    deployed. The policy is worked out again from the SELECTED batch: a batch that deploys the bot needs
    the deploy recorded, a batch that skips it needs the skip recorded under its own reason. A refusal
    comes before any probe, and writes nothing."""
    rt, _src = _release_train()
    refused = (("ban-cap", {"bot_deployed": False, "bot_skipped": "an earlier entry skipped the bot"},
                "this batch deploys the bot"),
               ("ban-cap", {}, "this batch deploys the bot"),
               (ABSENT_BATCH, {"bot_deployed": True}, "this batch skips the bot"),
               (ABSENT_BATCH, {"bot_deployed": False, "bot_skipped": "another reason"},
                "this batch skips the bot"))
    for i, (name, recorded, says) in enumerate(refused):
        path = _rt_bind(monkeypatch, rt, name, tmp_path / ("refused%d" % i))
        w = _rt_world(monkeypatch, rt)
        w.serve = lambda host, sha: _NEW
        st = _rt_fresh(rt, code_deployed=True, i18n_done=True, **recorded)
        with pytest.raises(rt.Fail) as exc:
            rt.phase_verify(GO, st)
        assert says in str(exc.value), (name, recorded, str(exc.value))
        assert "verified" not in st and not os.path.exists(path)
        assert w.calls == [], w.calls

    # the inert twins: each batch's own disposition is accepted
    for name in (ABSENT_BATCH, "ban-cap"):
        path = _rt_bind(monkeypatch, rt, name, tmp_path / ("twin-" + name))
        w = _rt_world(monkeypatch, rt)
        w.serve = lambda host, sha: _NEW
        recorded = ({"bot_deployed": True, "bot_deployed_at": _rt_utc(0.1)} if rt.DEPLOY_BOT
                    else {"bot_deployed": False, "bot_skipped": rt.BOT_SKIP_REASON})
        st = _rt_fresh(rt, code_deployed=True, i18n_done=True, **recorded)
        rt.phase_verify(GO, st)
        assert st["verified"] is True and rt.load_state()["verified"] is True


def test_every_json_marker_is_validated_even_when_the_batch_also_adds_a_route(monkeypatch):
    """Validation returned on `new_routes` before it read the json markers, and the reading never read them.

    A route batch carrying a json marker that could not fail was accepted as dead configuration. An entry is
    reviewed as a whole: its json markers are validated whether or not it adds a route, and a batch that
    carries both is READ on both -- NEW only when the routes and the markers both say new, OLD only when
    both say old, unknown otherwise, on each box and through the edge."""
    rt, _src = _release_train()
    entry = dict(rt.BATCHES[JSON_BATCH])
    m = entry["json_markers"][0]
    route = "/api/v1/a-route-neither-build-serves"

    for marker, says in ((dict(m, expect=None), "expects None"),
                         (dict(m, why=""), "carries no `why`"),
                         (dict(m, path=rt.CONTROL_ROUTE), "is read on the control route")):
        rt.BATCHES["_broken"] = dict(entry, new_routes=[route], json_markers=[marker])
        try:
            with pytest.raises(rt.Fail) as exc:
                rt.select_batch("_broken")
            assert says in str(exc.value), (marker, str(exc.value))
        finally:
            del rt.BATCHES["_broken"]

    rt.BATCHES["_both"] = dict(entry, new_routes=[route])
    rt.select_batch("_both")
    assert rt.NEW_ROUTES == [route] and rt.JSON_MARKERS == [m]
    old_body = {"version": "1.41.0"}                 # the route answers; the key is not there
    new_body = dict(old_body, **{m["key"]: m["expect"]})
    for code, body, want in (("200", new_body, (True, False)),
                             ("404", old_body, (False, True)),
                             ("200", old_body, (False, False)),
                             ("404", new_body, (False, False))):
        monkeypatch.setattr(rt, "http_code",
                            lambda host, path, _c=code, **kw: _c if path == route else "200")
        monkeypatch.setattr(rt, "route_json", lambda host, path, _b=body: _b)
        for host in (rt.PRIMARY, rt.STANDBY):
            ok, present, absent, readings = rt.code_state(host)
            assert ok and (present, absent) == want, (code, body, readings)
            assert any(m["key"] in r for r in readings), readings
        if want == (True, False):
            rt.assert_edge_runs_new_code()
        else:
            with pytest.raises(rt.Fail):
                rt.assert_edge_runs_new_code()


# ── slice 2: the rollback point ───────────────────────────────────────────


def test_the_code_phase_refuses_a_train_with_no_recorded_snapshot(monkeypatch, tmp_path, capsys):
    """The rollback point is a prerequisite of the code deploy, for every batch, and `--from code` skips phase 0.

    A train resumed at the code phase never reaches phase 0, so it could merge, push and deploy to both boxes
    with nothing to roll back to. The gate is asked before ANY command runs, including the read-only ones, so
    a refusal leaves the tree, the remote, the boxes and the state file exactly as they were. It is asked of a
    batch with migrations too: the snapshot is the rollback point for the CODE."""
    rt, _src = _release_train()
    for name in (ABSENT_BATCH, "qdig"):
        where = tmp_path / name
        _rt_bind(monkeypatch, rt, name, where)
        w = _rt_world(monkeypatch, rt)
        st = {"schema_done": True}
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(GO, st)
        assert "no rollback point" in str(exc.value) and "no snapshot is recorded" in str(exc.value)
        assert w.calls == [] and st == {"schema_done": True} and _rt_files(where) == []
        capsys.readouterr()
        rt.phase_code(PLAN, {"schema_done": True})
        out = capsys.readouterr().out
        assert "no snapshot is recorded for this train" in out and "refuses" in out, out


def test_the_recorded_snapshot_binds_to_this_train_its_label_its_age_and_the_listing(monkeypatch, tmp_path):
    """A recorded name is a rollback point only for this batch's label, and only while it is young.

    The gate asked only whether a string was truthy, so a name taken under another batch's label, or one
    taken last week, let a deploy proceed with nothing current to roll back to. The record now carries the
    tool's own UTC time beside the name, and the age is read from THAT: the stamp inside the name is the
    snapshot host's local wall clock (Pacific time), so it is checked for form and never for age. A record
    without the time is too old. (The listing half -- does the snapshot still exist -- is not ported: the
    age bound stands in for the wrapper's keep-10 prune.) Phase 0 replaces a record that does not stand with
    a fresh snapshot and keeps the old name in the state."""
    rt, _src = _release_train()
    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / "gate")
    base = {"schema_done": True, "pre_code_old_build": True}
    refused = (
        ({"snapshot": _rt_minted(rt, label="pre-ban-cap"), "snapshot_recorded_at": _rt_utc(1)},
         "is not the form the wrapper mints for label"),
        ({"snapshot": _rt_minted(rt)}, "carries no UTC time of its own"),
        (_rt_fresh(rt, hours_ago=25), "past the 24 h bound"),
        (_rt_fresh(rt, hours_ago=-2), "lies in the future"),
        ({"snapshot": _rt_minted(rt, stamp="2026111_112001"), "snapshot_recorded_at": _rt_utc(1)},
         "is not the form the wrapper mints for label"),
        ({"snapshot": _rt_minted(rt), "snapshot_recorded_at": "2026-11-18 11:20:01"},
         "is not a UTC time this tool wrote"),
        # the minted shape, but its stamp is no calendar date and time (month 13, hour 25): recorded, not printed
        ({"snapshot": _rt_minted(rt, stamp="20261345_256161"), "snapshot_recorded_at": _rt_utc(1)},
         "is not the form the wrapper mints for label"),
    )
    for record, says in refused:
        w = _rt_world(monkeypatch, rt)
        st = dict(base, **record)
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(GO, st)
        assert "no rollback point" in str(exc.value) and says in str(exc.value), (record, str(exc.value))
        assert w.calls == [], w.calls

    # the name's stamp is never read for age: one years old and one ahead of the UTC clock both stand
    ahead = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y%m%d_%H%M%S")
    for i, stamp in enumerate(("20200101_000000", ahead)):
        _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / ("stands%d" % i))
        w = _rt_world(monkeypatch, rt)
        st = dict(base, snapshot=_rt_minted(rt, stamp=stamp), snapshot_recorded_at=_rt_utc(23))
        rt.phase_code(GO, st)
        assert st["code_deployed"] is True
    assert rt.SNAPSHOT_MAX_AGE_HOURS == 24

    # phase 0: a record that does not stand is replaced, and both names stay in the state
    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / "phase0")
    w = _rt_world(monkeypatch, rt)
    old = _rt_minted(rt, stamp="20261116_090000")
    old_at = _rt_utc(30)
    st = {"snapshot": old, "snapshot_recorded_at": old_at}
    rt.phase_snapshot(GO, st)
    assert w.kinds("snapshot") == [("snapshot",)]
    assert st["snapshot"] == _rt_minted(rt) and st["snapshot_recorded_at"] != old_at
    assert st["snapshots_superseded"] == [{"name": old, "recorded_at": old_at}]
    assert rt.load_state() == st
    # ...and one that stands is not taken again
    w = _rt_world(monkeypatch, rt)
    rt.phase_snapshot(GO, _rt_fresh(rt))
    assert w.kinds("snapshot") == []


def test_a_snapshot_name_is_the_exact_form_the_wrapper_mints(monkeypatch, tmp_path):
    """`cc_` plus anything is a SHAPE, and a shape is not a name.

    The wrapper builds one form: `cc_`, the label with every character outside [a-zA-Z0-9_-] made `_`, the
    underscore its `echo` newline becomes, a second underscore, and an eight-digit, `_`, six-digit stamp.
    Phase 0 took the LAST `cc_` token of the play's output, so a name minted for another label, a token glued
    into a longer one, or a stamp no calendar has could become the train's rollback point. Only the exact form
    for this batch's label is recorded, as a whole token, and only when the output names exactly one."""
    rt, _src = _release_train()
    recap = "\nPLAY RECAP box : ok=2 changed=1 unreachable=0 failed=0"
    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / "refused")
    good = _rt_minted(rt)
    label = rt.SNAPSHOT_LABEL
    refused = (("ok: %s created" % _rt_minted(rt, label="pre-ban-cap"), "another batch's label"),
               ("ok: cc_%s_20261118_112001 created" % label, "one underscore before the stamp"),
               ("ok: %s1 created" % good, "a seventh digit glued to the stamp"),
               ("ok: x%s created" % good, "the form inside a longer token"),
               ("ok: %s created" % _rt_minted(rt, stamp="20261345_256161"), "a stamp no calendar has"),
               ("ok: %s and %s" % (good, _rt_minted(rt, stamp="20261118_112002")), "two names of the form"))
    for out, why in refused:
        w = _rt_world(monkeypatch, rt)
        w.snapshot_out = out + recap
        st = {}
        with pytest.raises(rt.Fail):
            rt.phase_snapshot(GO, st)
        assert st == {} and _rt_files(tmp_path / "refused") == [], why

    # the exact form is recorded, with the tool's own UTC time beside it
    w = _rt_world(monkeypatch, rt)
    w.snapshot_out = "TASK ok: %s\nmsg: snapshot %s created%s" % (good, good, recap)
    before = datetime.now(timezone.utc).replace(microsecond=0)
    st = {}
    rt.phase_snapshot(GO, st)
    at = datetime.strptime(st["snapshot_recorded_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert st["snapshot"] == good and before <= at <= datetime.now(timezone.utc)
    assert rt.load_state() == st

    # a label with characters the wrapper replaces mints the replaced form
    rt.BATCHES["_odd"] = dict(rt.BATCHES[ABSENT_BATCH], snapshot_label="pre.x y")
    _rt_bind(monkeypatch, rt, "_odd", tmp_path / "odd")
    w = _rt_world(monkeypatch, rt)
    w.snapshot_out = "ok: cc_pre.x y__20261118_112001" + recap
    with pytest.raises(rt.Fail):
        rt.phase_snapshot(GO, {})
    w.snapshot_out = "ok: cc_pre_x_y__20261118_112001" + recap
    st = {}
    rt.phase_snapshot(GO, st)
    assert st["snapshot"] == "cc_pre_x_y__20261118_112001"


# ── slice 2, addition 1: a rollback point before every phase that changes a server ──

_A1_SITES = (   # (phase, an entry in which that phase changes a server, the change the world records)
    ("deploy-precursor", "qdig", "deploy"),
    ("schema", "qdig", "migrate"),
    ("code", "qdig", "deploy"),
    ("i18n", "ban-cap", "migrate"),
    ("bot", "ban-cap", "bot"),
)
_A1_IDLE = (    # (phase, an entry in which that phase changes nothing, the state it leaves as today)
    ("deploy-precursor", "mscl", {}),
    ("schema", "ban-cap", {"schema_done": True}),
    ("i18n", "qdig", {"i18n_done": True}),
    ("bot", "mscl", {"bot_deployed": False}),
)
_A1_GATES = {   # what each phase's own earlier gate asks of the state, so only the rollback point is missing
    "deploy-precursor": {"precursor_sha": PRECURSOR_SHA},
    "schema": {},
    "code": {"schema_done": True},
    "i18n": {"code_deployed": True},
    "bot": {"i18n_done": True},
}
_A1_PROBLEMS = ("none recorded", "past the bound", "no UTC time")
_A1_DONE = {"schema": "schema_done", "code": "code_deployed", "i18n": "i18n_done", "bot": "bot_deployed"}


def _a1_phase(rt, phase):
    return dict(rt.PHASES)[phase]


def _a1_state(rt, phase, problem):
    st = dict(_A1_GATES[phase])
    if problem == "past the bound":
        st.update(_rt_fresh(rt, hours_ago=rt.SNAPSHOT_MAX_AGE_HOURS + 1))
    elif problem == "no UTC time":
        st["snapshot"] = _rt_minted(rt)
    return st


@pytest.mark.parametrize("problem", _A1_PROBLEMS)
@pytest.mark.parametrize("phase,name,_kind", _A1_SITES)
def test_a1_each_phase_that_changes_a_server_refuses_without_a_rollback_point(
        monkeypatch, tmp_path, phase, name, _kind, problem):
    """Under --go each of the five phases refuses when the recorded snapshot does not stand.

    A resumed run (`--from`, `--only`) never passes phase 0, so the phase asks itself: before its first
    command, and before `attempt_starts`, so the state file is left byte-equal. The refusal names the
    problem and says to resume at this phase."""
    rt, _src = _release_train()
    path = _rt_bind(monkeypatch, rt, name, tmp_path)
    w = _rt_world(monkeypatch, rt)
    st = _a1_state(rt, phase, problem)
    if phase in _A1_DONE:
        # a word an earlier attempt left: withdrawn by `attempt_starts`, so it stays only if the refusal comes first
        st[_A1_DONE[phase]] = True
    rt.save_state(st)
    before = Path(path).read_bytes()
    with pytest.raises(rt.Fail) as exc:
        _a1_phase(rt, phase)(GO, rt.load_state())
    msg = str(exc.value)
    assert "no rollback point stands" in msg and msg.endswith("then resume at %s" % phase), msg
    assert w.calls == [], w.calls
    assert Path(path).read_bytes() == before


@pytest.mark.parametrize("phase,name,_kind", _A1_SITES)
def test_a1_a_dry_run_notes_the_missing_rollback_point_and_writes_nothing(
        monkeypatch, tmp_path, capsys, phase, name, _kind):
    """Without --go each of the five phases prints the plan note and goes on; nothing is written."""
    rt, _src = _release_train()
    path = _rt_bind(monkeypatch, rt, name, tmp_path)
    w = _rt_world(monkeypatch, rt)
    _a1_phase(rt, phase)(PLAN, _a1_state(rt, phase, "none recorded"))
    out = capsys.readouterr().out
    assert ("[plan only] no snapshot is recorded for this train: under --go this phase refuses "
            "until the snapshot phase records a fresh one") in out, out
    assert not Path(path).exists() and _rt_files(tmp_path) == []
    assert w.kinds("deploy", "migrate", "bot", "git", "push") == [], w.calls


@pytest.mark.parametrize("name", NEWEST_THREE)
def test_a1_a_resumed_train_passes_each_phase_with_a_standing_rollback_point(monkeypatch, tmp_path, capsys,
                                                                               name):
    """Phase by phase, each its own `run --go --only <phase>`, with the record aged to just inside the bound.

    Every phase that changes a server in this entry names the rollback point and makes its change; every
    phase that changes nothing names none. The order of the whole train is the one a full run takes."""
    rt, _src = _release_train()
    path = _rt_bind(monkeypatch, rt, name, tmp_path)
    w = _rt_world(monkeypatch, rt)
    sites = {p: k for p, n, k in _A1_SITES}
    changes = {"deploy-precursor": bool(rt.ALL_SQL), "schema": bool(rt.SCHEMA_SQL), "code": True,
               "i18n": bool(rt.POST_CODE_SQL + rt.I18N_SQL + rt.BACKFILL_SQL), "bot": rt.DEPLOY_BOT}
    for phase, _fn in rt.PHASES:
        if phase in sites and Path(path).exists():
            st = json.loads(Path(path).read_text(encoding="utf-8"))
            st["snapshot_recorded_at"] = _rt_utc(rt.SNAPSHOT_MAX_AGE_HOURS - 1)
            rt.save_state(st)
        seen = len(w.calls)
        monkeypatch.setattr(rt.sys, "argv", ["release_train.py", "run", "--go", "--batch", name, "--only", phase])
        rc = rt.main()
        out = capsys.readouterr().out
        assert rc == 0, (phase, out)
        if phase in sites and changes[phase]:
            assert "rollback point: %s (recorded " % _rt_minted(rt) in out, (phase, out)
            assert [c for c in w.calls[seen:] if c[0] == sites[phase]], (phase, w.calls[seen:])
        else:
            assert "rollback point: " not in out, (phase, out)
    st = json.loads(Path(path).read_text(encoding="utf-8"))
    assert st["verified"] is True and st["code_deployed"] is True and st["snapshot"] == _rt_minted(rt)


@pytest.mark.parametrize("phase,name,after", _A1_IDLE)
def test_a1_a_phase_that_changes_nothing_asks_nothing(monkeypatch, tmp_path, capsys, phase, name, after):
    """A phase with nothing to change in this entry asks nothing and behaves as today, its done key included."""
    rt, _src = _release_train()
    _rt_bind(monkeypatch, rt, name, tmp_path)
    w = _rt_world(monkeypatch, rt)
    st = dict(_A1_GATES[phase])
    _a1_phase(rt, phase)(GO, st)
    out = capsys.readouterr().out
    assert "rollback point: " not in out, out
    for key, value in after.items():
        assert st.get(key) is value, (key, st)
    assert w.kinds("deploy", "migrate", "bot") == [], w.calls


# ── slice 4: the small ones ───────────────────────────────────────────────


def test_the_train_refuses_to_run_when_no_batch_is_named(monkeypatch, capsys):
    """`--batch` is required: an unnamed batch selected one nobody chose.

    `--batch` carried a default, so `plan`, `check` and `run --go` typed without it drove whichever train the
    default named. The documented commands omitted the flag too, so following the docstring was the way to hit
    it. There is no default now, the module arrives bound to no batch at all, and the refusal comes before
    anything is selected, read or probed."""
    rt, src = _release_train()
    real_select = rt.select_batch          # kept for the twin, past the refusal stubs below
    # the module arrives pointed at nothing: an import-time selection is the
    # same default wearing a different hat
    assert rt.BATCH_NAME is None and rt.BRANCH is None and rt.STATE_PATH is None
    assert "DEFAULT_BATCH" not in src
    # No command may leave this test, whatever main() decides: a train that
    # selected a batch anyway would otherwise probe live boxes from a unit test.
    monkeypatch.setattr(rt, "run", lambda cmd, **kw: _raise_no_command(cmd))

    for action in ("plan", "check", "run"):
        monkeypatch.setattr(sys, "argv", ["release_train.py", action])
        assert rt.main() == 1
        out = capsys.readouterr().out
        assert "--batch is required" in out, out
        for name in rt.BATCHES:
            assert name in out, (name, out)

    # and it refuses BEFORE it selects, reads the state file or probes anything
    monkeypatch.setattr(rt, "select_batch",
                        lambda name: pytest.fail("selected %r with no --batch" % name))
    monkeypatch.setattr(rt, "load_state", lambda: pytest.fail("read a state file"))
    monkeypatch.setattr(rt, "run", lambda cmd, **kw: pytest.fail("ran %r" % (cmd,)))
    monkeypatch.setattr(sys, "argv", ["release_train.py", "check"])
    assert rt.main() == 1
    capsys.readouterr()

    # every command this file tells an operator to type names a batch
    typed = [l for l in src.splitlines()
             if "release_train.py" in l and "python" in l and "--batch" not in l]
    assert typed == [], typed

    # the inert twin: a NAMED batch still binds
    real_select(ABSENT_BATCH)
    assert rt.BATCH_NAME == ABSENT_BATCH and rt.BRANCH == rt.BATCHES[ABSENT_BATCH]["branch"]


def test_every_lan_probe_the_check_makes_carries_the_version_header(monkeypatch, capsys):
    """`check` printed the mod-version body from an unheadered curl.

    Every other LAN probe carries the version header; this one went out bare, so wherever the gate is armed
    it read the gate's refusal on both builds -- a line that can never disagree with itself."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    cmds = []

    def run(cmd, **kw):
        cmds.append(list(cmd))
        if cmd[0] == "curl":
            return "200" if "-w" in cmd else "{}"
        if cmd[0] == "ssh":
            return ""
        return "0"
    monkeypatch.setattr(rt, "run", run)
    import subprocess as _sp
    inner = _sp.run

    def process(cmd, *a, **kw):
        if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "curl":
            cmds.append(list(cmd))
            return _rt_done(kw, "200")
        return inner(cmd, *a, **kw)
    monkeypatch.setattr(_sp, "run", process)
    rt.phase_check(PLAN, {})
    lan = [c for c in cmds if c[0] == "curl"
           and any("//%s:" % h in c[-1] for h in (rt.PRIMARY, rt.STANDBY))]
    for host in (rt.PRIMARY, rt.STANDBY):
        assert any(c[-1] == "http://%s:8443/api/v1/mod-version" % host for c in lan), (host, lan)
    for c in lan:
        assert "X-Mod-Version: " + rt.MOD_VERSION_HEADER in c, c


def test_a_control_holds_only_when_the_body_carries_its_type(monkeypatch):
    """`1 == True` and `3 == 3.0` in Python; JSON carries them as different values.

    A reading compared with == accepted a body of the wrong type as the expected value, so a wrong body, an
    error page that happens to carry the key, or another serialiser read as the new build. The defect is the
    OPERATION, so every reading with an expected value is compared at its type: the health markers on a box
    and through the edge, the role values the health check waits for, and the json markers."""
    rt, _src = _release_train()
    monkeypatch.setattr(rt, "http_code", lambda host, path, **kw: "200")
    monkeypatch.setattr(rt, "HEALTH_ROLE_WAIT_S", -1)
    monkeypatch.setattr(rt.time, "sleep", lambda s: pytest.fail("the health check waited"))

    def body_for(host, **over):
        out = {}
        for key, roles in rt.health_expectations():
            out[key] = roles[host] if roles and roles.get(host) is not None else "present"
        out.update(over)
        return out

    def same_value_other_type(v):
        return float(v) if not isinstance(v, bool) else int(v)

    for name in (TRAIN_BATCH, ABSENT_BATCH):
        rt.select_batch(name)
        key, roles = [(k, r) for k, r in rt.code_markers() if isinstance(r[rt.PRIMARY], int)][0]
        wrongs = [same_value_other_type(roles[rt.PRIMARY])]
        if roles[rt.PRIMARY] == 1:
            wrongs.append(True)
        for wrong in wrongs:
            assert wrong == roles[rt.PRIMARY]          # the value Python's == would accept
            body = body_for(rt.PRIMARY, **{key: wrong})
            monkeypatch.setattr(rt, "health_json", lambda host, _b=body: _b)
            present, absent, readings = rt.marker_state(rt.PRIMARY)
            assert not present, (name, key, wrong, readings)
            with pytest.raises(rt.Fail):
                rt.assert_health_keys((rt.PRIMARY,))
            if (key, roles[rt.PRIMARY]) in rt.edge_markers():
                with pytest.raises(rt.Fail):
                    rt.assert_edge_runs_new_code()
        # the inert twin: the expected values at their own types read as the new build
        body = body_for(rt.PRIMARY)
        monkeypatch.setattr(rt, "health_json", lambda host, _b=body: _b)
        assert rt.marker_state(rt.PRIMARY)[0] is True
        rt.assert_health_keys((rt.PRIMARY,))

    rt.select_batch(JSON_BATCH)
    m = rt.JSON_MARKERS[0]
    assert m["expect"] is True
    monkeypatch.setattr(rt, "route_json", lambda host, path: {m["key"]: 1})
    present, absent, readings = rt.json_marker_state(rt.PRIMARY)
    assert (present, absent) == (False, False), readings
    with pytest.raises(rt.Fail):
        rt.assert_edge_runs_new_code()
    monkeypatch.setattr(rt, "route_json", lambda host, path: {m["key"]: True})
    assert rt.json_marker_state(rt.PRIMARY)[:2] == (True, False)
    rt.assert_edge_runs_new_code()


def test_the_push_url_gate_asks_git_where_a_push_would_really_go(monkeypatch, tmp_path):
    """Before every push, git is asked where a push to `origin` would really go.

    The configured literals are not where `git push` writes: `pushurl` adds destinations and
    `pushInsteadOf` rewrites them at push time. `git remote get-url --push --all origin` is the verb that
    expands both, and every destination it names must be the module's expected push address. The repository
    is public, so a push is a publication: a wrong answer refuses before the precursor commit is made."""
    rt, _src = _release_train()
    url = getattr(rt, "ORIGIN_PUSH_URL", "the module states no push address")
    for i, (answer, why) in enumerate((([FORK_URL], "another repository"),
                                       ([url, FORK_URL], "two destinations, one of them right"),
                                       ([], "no destination at all"))):
        _rt_bind(monkeypatch, rt, "ban-cap", tmp_path / ("refused%d" % i))
        w = _rt_world(monkeypatch, rt)
        w.push_urls = answer
        st = _rt_fresh(rt)
        with pytest.raises(rt.Fail) as exc:
            rt.phase_precursor(GO, st)
        assert "nothing is pushed" in str(exc.value), (why, str(exc.value))
        assert w.kinds("git", "push") == [] and "precursor_sha" not in st, why

    # the inert twin: the right address once; it is asked again right before the push
    _rt_bind(monkeypatch, rt, "ban-cap", tmp_path / "twin")
    w = _rt_world(monkeypatch, rt)
    st = _rt_fresh(rt)
    rt.phase_precursor(GO, st)
    assert st["precursor_sha"] == PRECURSOR_SHA
    push = w.calls.index(("push", "git push origin"))
    assert w.calls[push - 1] == ("push-address",), w.calls[push - 3:push + 1]
    assert url.startswith("https://%s/" % rt.ORIGIN_HOST) and url.endswith("/SidsCompetitiveRounds.git")


def test_the_merge_is_authenticated_and_the_remote_checked_before_the_push(monkeypatch, tmp_path):
    """The code phase asks the push address before the merge AND again before the push.

    Asked first, a wrong destination leaves main exactly as it was: no checkout, no merge, no commit. Asked
    again immediately before the push, a destination that changed in between (a hook, a second process)
    refuses the push itself: the merge is local, nothing is published, nothing is deployed."""
    rt, _src = _release_train()
    url = getattr(rt, "ORIGIN_PUSH_URL", "the module states no push address")
    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / "before")
    w = _rt_world(monkeypatch, rt)
    w.push_urls = [FORK_URL]
    st = _rt_fresh(rt, schema_done=True, pre_code_old_build=True)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(GO, st)
    assert "nothing is pushed" in str(exc.value)
    assert w.kinds("git", "push", "deploy") == [] and "code_sha" not in st

    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / "between")
    w = _rt_world(monkeypatch, rt)
    w.push_sequence = [[url], [FORK_URL]]
    st = _rt_fresh(rt, schema_done=True, pre_code_old_build=True)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(GO, st)
    assert "nothing is pushed" in str(exc.value)
    assert w.kinds("git") and w.kinds("push", "deploy") == [] and "code_sha" not in st

    # the inert twin
    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / "twin")
    w = _rt_world(monkeypatch, rt)
    st = _rt_fresh(rt, schema_done=True, pre_code_old_build=True)
    rt.phase_code(GO, st)
    push = w.calls.index(("push", "git push origin"))
    assert w.calls[push - 1] == ("push-address",)
    assert w.kinds("push-address") == [("push-address",)] * 2
    assert w.kinds("deploy") == _rt_pair(rt, MERGE_SHA)


def test_the_remote_gate_names_the_repository_and_reads_only_what_succeeded(monkeypatch, tmp_path, capsys):
    """A command that failed is no answer, and the refusal prints no address.

    A failed command's standard output can still hold the very address being asked about; a gate that read it
    would pass on a question git never answered. The expected address is the module's own constant, the
    command's return code has to be 0, and neither the expected nor the answered address appears in the
    refusal or in anything printed."""
    rt, _src = _release_train()
    url = getattr(rt, "ORIGIN_PUSH_URL", "the module states no push address")
    for i, (fails, answer, says) in enumerate(((True, [url], "did not succeed"),
                                               (False, [FORK_URL], "differ from"))):
        _rt_bind(monkeypatch, rt, "ban-cap", tmp_path / ("case%d" % i))
        w = _rt_world(monkeypatch, rt)
        w.push_address_fails, w.push_urls = fails, answer
        capsys.readouterr()
        with pytest.raises(rt.Fail) as exc:
            rt.phase_precursor(GO, _rt_fresh(rt))
        said = str(exc.value) + capsys.readouterr().out
        assert says in str(exc.value), str(exc.value)
        assert url not in said and FORK_URL not in said
        assert w.kinds("git", "push") == []


_PUSH_E = "https://example.invalid/the-expected-owner/the-expected-repository.git"
_PUSH_DIFFER1 = "1 destination(s) that differ"
_PUSH_CASES = [
    # (id, standard output with {e} the expected address and {x} another, standard error, return code,
    #  what the process call raises, the refusal's words or None for a pass)
    ("E", "{e}\n", "", 0, None, None),
    ("E-without-a-final-line-end", "{e}", "", 0, None, None),
    ("E-E", "{e}\n{e}\n", "", 0, None, None),
    ("E-and-a-warning-on-standard-error", "{e}\n", "warning: a notice git printed\n", 0, None, None),
    ("E-blank-E", "{e}\n\n{e}\n", "", 0, None, _PUSH_DIFFER1),
    ("one-blank-line", "\n", "", 0, None, _PUSH_DIFFER1),
    ("blank-before-E", " {e}\n", "", 0, None, _PUSH_DIFFER1),
    ("blank-after-E", "{e} \n", "", 0, None, _PUSH_DIFFER1),
    ("E-then-blank-before-E", "{e}\n {e}\n", "", 0, None, _PUSH_DIFFER1),
    ("X", "{x}\n", "", 0, None, _PUSH_DIFFER1),
    ("E-X", "{e}\n{x}\n", "", 0, None, _PUSH_DIFFER1),
    ("X-E", "{x}\n{e}\n", "", 0, None, _PUSH_DIFFER1),
    ("X-X", "{x}\n{x}\n", "", 0, None, "2 destination(s) that differ"),
    ("E-phrase1-E", "{e}\nhttps://example.invalid/post-quantum/a-repository.git\n{e}\n", "", 0, None,
     _PUSH_DIFFER1),
    ("E-phrase2-E", "{e}\nhttps://example.invalid/store now, decrypt later/a-repository.git\n{e}\n", "", 0,
     None, _PUSH_DIFFER1),
    ("E-phrase3-E", "{e}\nhttps://example.invalid/openssh.com/pq/a-repository.git\n{e}\n", "", 0, None,
     _PUSH_DIFFER1),
    ("E-stars-E", "{e}\n**\n{e}\n", "", 0, None, _PUSH_DIFFER1),
    ("empty", "", "", 0, None, "names no destination"),
    ("rc2-with-E", "{e}\n", "", 2, None, "did not succeed"),
    ("timeout", "{e}\n", "", 0, subprocess.TimeoutExpired(["git"], 60), "did not succeed"),
    ("could-not-start", "", "", 0, FileNotFoundError(2, "no such program"), "did not succeed"),
]


@pytest.mark.parametrize("stdout,stderr,rc,raises,says",
                         [pytest.param(*c[1:], id=c[0]) for c in _PUSH_CASES])
def test_the_push_address_check_compares_git_standard_output_line_for_line(monkeypatch, capsys, stdout, stderr,
                                                                           rc, raises, says):
    """The check reads git's standard output alone and every line of it must be the expected address.

    The process call is answered here (standard output, standard error, return code), so whatever the check
    does to the answer is inside the test. Nothing is removed from the answer, nothing is stripped, nothing
    is joined to it; one final line end is not a line. A blank line, an address with blanks around it, a
    line that holds a phrase of the ssh notice, another address beside the expected one or alone: each is a
    line that differs. An empty answer names no destination. A return code that is not 0, a timeout and a
    program that cannot start did not succeed. Standard error is no part of the answer. A refusal names no
    address."""
    import subprocess as _sp
    rt, _src = _release_train()
    monkeypatch.setattr(rt, "ORIGIN_PUSH_URL", _PUSH_E)
    out = stdout.format(e=_PUSH_E, x=FORK_URL)
    asked = []

    def process(cmd, *a, **kw):
        asked.append(list(cmd))
        if raises is not None:
            raise raises
        return _rt_done(kw, out, stderr, rc)
    monkeypatch.setattr(_sp, "run", process)
    capsys.readouterr()
    if says is None:
        rt.assert_push_address()
    else:
        with pytest.raises(rt.Fail) as exc:
            rt.assert_push_address()
        msg = str(exc.value)
        assert says in msg and "nothing is pushed" in msg, msg
        said = msg + capsys.readouterr().out
        for line in out.split("\n"):
            assert not line.strip() or line.strip() not in said, (line, said)
    assert asked == [["git", "remote", "get-url", "--push", "--all", "origin"]], asked


def test_the_status_code_is_curls_standard_output_alone(monkeypatch, tmp_path):
    """The status code a box answers is curl's standard output, and nothing curl writes to standard error.

    A route batch's build is read from the code its routes answer: 404 is the old build. A notice on standard
    error joined to that code made `404` read as another code, and so as the NEW build, in the per-box check a
    deploy waits on. The code is read alone and as it stands; a return code that is not 0 is a Fail."""
    import subprocess as _sp
    rt, _src = _release_train()
    name = next(n for n, e in rt.BATCHES.items() if e.get("new_routes") and not e.get("json_markers"))
    _rt_bind(monkeypatch, rt, name, tmp_path)
    route = rt.NEW_ROUTES[0]
    note = "Warning: a notice curl printed\n"
    answers = {r: ("404", note, 0) for r in rt.NEW_ROUTES}

    def process(cmd, *a, **kw):
        assert cmd[0] == "curl" and "-w" in cmd, cmd
        return _rt_done(kw, *answers.get(cmd[-1].split(":8443", 1)[1], ("200", "", 0)))
    monkeypatch.setattr(_sp, "run", process)
    assert rt.http_code(rt.PRIMARY, route) == "404"
    ok, present, absent, readings = rt.code_state(rt.PRIMARY)
    assert (ok, present, absent) == (True, False, True), readings
    with pytest.raises(rt.Fail) as exc:
        rt.assert_box_build(rt.PRIMARY, "new", "a" * 40)
    assert "it serves the OLD build" in str(exc.value)
    answers[route] = ("200", "", 0)
    assert rt.http_code(rt.PRIMARY, route) == "200"
    answers[route] = ("000", "curl: (7) Failed to connect\n", 7)
    with pytest.raises(rt.Fail) as exc:
        rt.http_code(rt.PRIMARY, route)
    assert "command failed (rc=7)" in str(exc.value)


class _RtJobChild:
    """A contained child as the job primitive hands it back: its two streams kept apart, unless the caller
    sent standard error into standard output."""

    def __init__(self, stdout, stderr, merged):
        self.returncode = 0
        self._streams = (stdout + stderr, None) if merged else (stdout, stderr)

    def communicate(self, timeout=None):
        return self._streams


def test_the_snapshot_name_is_read_from_the_plays_standard_output_alone(monkeypatch, tmp_path):
    """The snapshot phase counts the names in the play's standard output, with no line of it removed.

    The child is answered at the job primitive, so what the train does to the play's output is inside the
    test. A second name on a line that also holds a phrase of the ssh notice is still a second name, and the
    phase refuses. A name that only standard error prints is no name; another name that only standard error
    prints does not count against the one standard output names."""
    import subprocess as _sp
    rt, _src = _release_train()
    recap = "PLAY RECAP box : ok=2 changed=1 unreachable=0 failed=0\n"
    notice = "** WARNING: connection is not using a post-quantum key exchange algorithm.\n"
    cases = (
        ("the minted name; the ssh notice on standard error",
         "TASK [snapshot] ok: created {new}\n" + recap, notice, None),
        ("a second name on a line that holds a phrase of the ssh notice",
         "TASK [snapshot] ok: created {new}\npruned {old} (post-quantum)\n" + recap, "", "different names"),
        ("the name only on standard error", recap, "created {new}\n", "printed no name"),
        ("another name only on standard error", "TASK [snapshot] ok: created {new}\n" + recap,
         "pruned {old}\n", None),
    )
    for i, (why, stdout, stderr, says) in enumerate(cases):
        _rt_bind(monkeypatch, rt, "ban-cap", tmp_path / ("case%d" % i))
        names = dict(new=_rt_minted(rt, "20261118_112001"), old=_rt_minted(rt, "20261117_030000"))
        spawned = []

        def job_spawn(argv, job_name=None, before_resume=None, _o=stdout.format(**names),
                      _e=stderr.format(**names), **kw):
            spawned.append(kw.get("stderr"))
            return _RtJobChild(_o, _e, kw.get("stderr") == _sp.STDOUT)
        monkeypatch.setattr(rt, "job_spawn", job_spawn)
        monkeypatch.setattr(rt, "job_end", lambda p, why="": {"empty": True})
        monkeypatch.setattr(rt, "child_ended", lambda *a, **kw: None)
        st = {}
        if says is None:
            rt.phase_snapshot(GO, st)
            assert st["snapshot"] == names["new"], (why, st)
        else:
            with pytest.raises(rt.Fail) as exc:
                rt.phase_snapshot(GO, st)
            assert says in str(exc.value), (why, str(exc.value))
            assert "snapshot" not in st, why
        assert len(spawned) == 1, why


def test_the_train_refuses_a_precursor_subject_that_describes_no_commit():
    """The files-only subject and the sql files stand or fall together (#302), as a refusal with a sentence.

    A batch with sql needs a subject for the files-only commit; a missing one was a KeyError deep in
    selection. A batch with no sql commits nothing in the precursor phase, so it names no subject, or only
    the sentence that states the skip; a commit subject there describes a commit nothing makes."""
    rt, _src = _release_train()

    def refused(base, change, says):
        entry = dict(rt.BATCHES[base])
        for k, v in change.items():
            if v is _DROP:
                entry.pop(k, None)
            else:
                entry[k] = v
        rt.BATCHES["_broken"] = entry
        try:
            with pytest.raises(rt.Fail) as exc:
                rt.select_batch("_broken")
            assert says in str(exc.value), (change, str(exc.value))
        finally:
            del rt.BATCHES["_broken"]

    refused(ABSENT_BATCH, {"precursor_message": "Migration 999 precursor (files only)"},
            "the precursor phase commits nothing")
    refused("ban-cap", {"precursor_message": _DROP}, "names no precursor_message")
    refused("ban-cap", {"precursor_message": "   "}, "names no precursor_message")
    refused("ban-cap", {"precursor_message": rt.BATCHES[ABSENT_BATCH]["precursor_message"]},
            "says it has none")
    # the inert twins: the entries as they ship, including one with an empty subject and no sql
    for name in (ABSENT_BATCH, "ban-cap", "qdig", "rehearsal-four"):
        rt.select_batch(name)


# ── KEEP-C: what the operating train already does, re-pointed at it ──────


def test_the_code_phase_takes_the_branch_only_at_its_reviewed_tip(monkeypatch, tmp_path):
    """The tip half of the provenance binding: the branch must be the pinned sha, and the merge must carry it.

    A branch name is a mutable ref. The entry pins the full sha the review certified; the code phase (and the
    precursor) refuse a branch at any other tip and an entry with no pin, and a merge whose second parent is
    not that sha is recorded nowhere and deployed nowhere. (The main half -- `main_expected` and a clean tree
    -- is TRAIN-PARITY-2's.)"""
    rt, _src = _release_train()
    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / "moved")
    w = _rt_world(monkeypatch, rt)
    w.branch_tip = "f" * 40
    st = _rt_fresh(rt, schema_done=True, pre_code_old_build=True)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(GO, st)
    assert "the review certified %s" % rt.REVIEWED_TIP in str(exc.value)
    assert w.kinds("git", "push", "deploy") == []

    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / "parent")
    w = _rt_world(monkeypatch, rt)
    w.second_parent = "f" * 40
    st = _rt_fresh(rt, schema_done=True, pre_code_old_build=True)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(GO, st)
    assert "second parent" in str(exc.value) and "NOT deployed" in str(exc.value)
    assert "code_sha" not in st and w.kinds("deploy") == []

    rt.BATCHES["_unpinned"] = {k: v for k, v in rt.BATCHES[ABSENT_BATCH].items() if k != "reviewed_tip"}
    _rt_bind(monkeypatch, rt, "_unpinned", tmp_path / "unpinned")
    w = _rt_world(monkeypatch, rt)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(GO, _rt_fresh(rt, schema_done=True, pre_code_old_build=True))
    assert "NO reviewed_tip pinned" in str(exc.value) and w.kinds("git", "push", "deploy") == []

    _rt_bind(monkeypatch, rt, "ban-cap", tmp_path / "precursor")
    w = _rt_world(monkeypatch, rt)
    w.branch_tip = "f" * 40
    with pytest.raises(rt.Fail) as exc:
        rt.phase_precursor(GO, _rt_fresh(rt))
    assert "the review certified" in str(exc.value) and w.kinds("git", "push") == []

    # the inert twin
    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / "twin")
    w = _rt_world(monkeypatch, rt)
    st = _rt_fresh(rt, schema_done=True, pre_code_old_build=True)
    rt.phase_code(GO, st)
    assert st["code_sha"] == MERGE_SHA and st["code_deployed"] is True


def test_the_reviewed_tip_is_a_full_object_id_when_the_entry_is_selected(monkeypatch, capsys):
    """The tip half of the anchors' shape: `reviewed_tip` is a full 40-hex id, asked when the entry is selected.

    An abbreviation resolves against whatever objects this checkout holds; a full id names one commit. The
    shape is asked at selection, before any git command, and the tip is printed whole."""
    rt, _src = _release_train()
    full = rt.BATCHES[ABSENT_BATCH]["reviewed_tip"]
    for tip in (full[:7], full.upper(), full + "0", "main"):
        rt.BATCHES["_tip"] = dict(rt.BATCHES[ABSENT_BATCH], reviewed_tip=tip)
        with pytest.raises(rt.Fail) as exc:
            rt.select_batch("_tip")
        assert "FULL 40-hex" in str(exc.value), tip
    rt.select_batch(ABSENT_BATCH)
    assert rt.REVIEWED_TIP == full
    monkeypatch.setattr(rt, "run", lambda cmd, **kw: full)
    assert rt.assert_reviewed_tip("code") == full
    assert full in capsys.readouterr().out


def test_the_recorded_code_sha_is_an_object_id_and_that_id_is_what_deploys(monkeypatch, tmp_path):
    """The recorded merge deploys only when HEAD is exactly it, and the playbook is handed that id.

    `code_sha` is read from a state file that outlives the run. A value that is not the commit HEAD is on --
    a revision name such as `main`, or another commit -- is refused before the boot gate and before any
    deploy, because the boot gate must read the deployed tree; the id that passes is the one each box's
    play is pinned to."""
    rt, _src = _release_train()
    for i, recorded in enumerate(("main", "f" * 40)):
        _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / ("refused%d" % i))
        w = _rt_world(monkeypatch, rt)
        w.head = MERGE_SHA
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(GO, _rt_fresh(rt, schema_done=True, pre_code_old_build=True, code_sha=recorded))
        assert "is not CODE_SHA" in str(exc.value), str(exc.value)
        assert w.kinds("deploy") == []
    _rt_bind(monkeypatch, rt, ABSENT_BATCH, tmp_path / "twin")
    w = _rt_world(monkeypatch, rt)
    w.head = MERGE_SHA
    st = _rt_fresh(rt, schema_done=True, pre_code_old_build=True, code_sha=MERGE_SHA)
    rt.phase_code(GO, st)
    assert w.kinds("deploy") == _rt_pair(rt, MERGE_SHA)
    assert w.kinds("git") == []      # a recorded merge is not merged again


# ── the newest entries, end to end ────────────────────────────────────


def test_the_three_newest_entries_run_end_to_end_under_the_train(monkeypatch, tmp_path, capsys):
    """The three newest entries, each driven from `run --go` through every phase with the world stubbed.

    Each batch shape is here: no sql and a skipped bot; sql applied after the code and a deployed bot; a
    schema migration and a deployed bot. Every gate the train has must let each of them through when the
    boxes do what they should, and the order of what would leave the machine is the order the two-SHA
    rule requires."""
    rt, _src = _release_train()
    for name in NEWEST_THREE:
        assert name in rt.BATCHES, name
        where = tmp_path / name
        path = _rt_bind(monkeypatch, rt, name, where)
        w = _rt_world(monkeypatch, rt)
        monkeypatch.setattr(rt.sys, "argv", ["release_train.py", "run", "--go", "--batch", name])
        assert rt.main() == 0, capsys.readouterr().out
        capsys.readouterr()
        st = json.loads(Path(path).read_text(encoding="utf-8"))
        assert st["verified"] is True and st["code_deployed"] is True and st["code_sha"] == MERGE_SHA
        assert st["snapshot"] == _rt_minted(rt)
        assert w.calls.index(("snapshot",)) < w.calls.index(w.kinds("git")[0])
        merge_pair = _rt_pair(rt, MERGE_SHA)
        if rt.ALL_SQL:
            pre_pair = _rt_pair(rt, PRECURSOR_SHA)
            assert w.kinds("deploy") == pre_pair + merge_pair, w.kinds("deploy")
            assert len(w.kinds("push")) == 2 and st["precursor_sha"] == PRECURSOR_SHA
        else:
            assert w.kinds("deploy") == merge_pair and len(w.kinds("push")) == 1
        assert [c[1] for c in w.kinds("migrate")] == rt.SCHEMA_SQL + rt.POST_CODE_SQL + rt.I18N_SQL + rt.BACKFILL_SQL
        if rt.DEPLOY_BOT:
            assert len(w.kinds("bot")) == 1 and st["bot_deployed"] is True
            assert w.calls.index(w.kinds("bot")[0]) > w.calls.index(merge_pair[-1])
        else:
            assert w.kinds("bot") == [] and st["bot_skipped"] == rt.BOT_SKIP_REASON


def test_every_typed_marker_expectation_has_the_type_the_api_serves():
    """Markers are now compared at their type, so each entry's expected value must have the type the api serves.

    For every entry, every per-role health value and every json marker whose key today's api still answers
    is checked against the type of today's answer: the health check's model, and the mod-version body. A
    mismatch here is an entry the new comparison would refuse on a box that is right."""
    rt, _src = _release_train()

    class _Up:
        async def execute(self, *a, **k):
            return None
    served = {"/api/v1/health": _run(main.health_check(db=_Up())).model_dump(),
              "/api/v1/mod-version": _run(main.get_mod_version())}
    assert isinstance(served["/api/v1/mod-version"], dict)
    checked = 0
    for name in rt.BATCHES:
        rt.select_batch(name)
        health = served["/api/v1/health"]
        for key, roles in rt.health_expectations():
            if roles is None or key not in health or health[key] is None:
                continue
            for want in roles.values():
                if want is not None:
                    assert type(want) is type(health[key]), (name, key, want, health[key])
                    checked += 1
        for m in rt.JSON_MARKERS:
            body = served.get(m["path"])
            if body is None or body.get(m["key"]) is None:
                continue
            assert type(m["expect"]) is type(body[m["key"]]), (name, m["key"], m["expect"])
            checked += 1
    assert checked > 100, checked


# ── round 2: the findings the cold review raised on the first pin ────────
#
# One test per finding number, each with an arm that must REDDEN when the fix
# is absent and an inert twin that must stay green. The shas below are the two
# the bug392-merge entry binds to, written out in full: the entry carries the
# abbreviations an operator reads, and the provenance check resolves them.

REVIEWED_FULL = "990cd4390c6bcc5f9e01be752d5e4c7c3883403c"
MAIN_FULL = "88204631bcff36adf97150d092c773a2ebdd9f84"
OTHER_FULL = "0123456789abcdef0123456789abcdef01234567"
MERGE_FULL = "fedcba9876543210fedcba9876543210fedcba98"


def _raise_no_command(cmd):
    raise _NoCommand(" ".join(cmd) if isinstance(cmd, list) else cmd)


class _NoCommand(Exception):
    """A command reached the stub that should not have.

    Deliberately NOT the train's own Fail: a phase that failed to stop where it
    must would otherwise satisfy pytest.raises(Fail) with the stub's own error,
    and the check could not fail (#342)."""


REVIEWED_TREE = "a" * 40
OTHER_TREE = "b" * 40


NO_REPLACE = "--no-replace-objects"


def _is_full_sha(text):
    return len(text) == 40 and all(c in "0123456789abcdef" for c in text)


ORIGIN_URL = "https://github.com/ACCOUNT/SidsCompetitiveRounds.git"


SEAT_CONTROLLER = "a-controller"
SEAT_PVE_GROUP = "a-group"
SEAT_PRIMARY_LIMIT = "a-primary-group"
SEAT_STANDBY_LIMIT = "a-standby-group"
# The absolute directory the ZAP playbooks live in on the controller. It is a
# seat value for the same reason the four above are: an absolute path on
# somebody's controller names the account it runs under, and the round-8
# mechanism has to write it into a composed playbook. The fixture is one of
# this file's fabricated `a-` names, never this seat's own path.
SEAT_PLAY_DIR = "/srv/a-play-dir/playbooks"


def _seat(monkeypatch, rt, controller=SEAT_CONTROLLER, pve_group=SEAT_PVE_GROUP,
          origin=ORIGIN_URL, primary_limit=SEAT_PRIMARY_LIMIT,
          standby_limit=SEAT_STANDBY_LIMIT, play_dir=SEAT_PLAY_DIR):
    """Point the train at a seat whose identifiers are FIXTURES, never this machine's.

    The conf file beside the script is deliberately pointed at a name that does
    not exist: a test that passed because the operating seat happens to hold
    the right value would be a test of the seat, and it would redden on any
    other machine -- or, worse, quietly read the real identifiers into a
    transcript.

    The two per-box deploy selectors are seat values too. While they were
    literals in the train they were in every review bundle built out of it, and
    the scan that was supposed to catch that kept a hand-written needle list
    which did not name them."""
    monkeypatch.setattr(rt, "TRAIN_CONF", str(Path(__file__).parent / "no-such-train-conf.json"))
    monkeypatch.setenv("SCR_TRAIN_CONTROLLER", controller)
    monkeypatch.setenv("SCR_TRAIN_PVE_GROUP", pve_group)
    monkeypatch.setenv("SCR_TRAIN_ORIGIN_URL", origin)
    monkeypatch.setenv("SCR_TRAIN_PRIMARY_LIMIT", primary_limit)
    monkeypatch.setenv("SCR_TRAIN_STANDBY_LIMIT", standby_limit)
    monkeypatch.setenv("SCR_TRAIN_PLAY_DIR", play_dir)
    # Every test gets a fresh module, so the first-read capture and the learned
    # labels start empty; a test that re-points the seat inside one process is
    # asserting about the CAPTURE, which is the point of R8-H2.
    rt._SEAT_SNAPSHOT.clear()
    rt._SEAT_FILE.clear()
    rt._LEARNED_HOSTS.clear()
    rt._FINGERPRINTS.clear()


# The machine the fixture play and the fixture listing both answer from. It is
# the RESPONDING host, which is a different fact from the selector that was
# asked for: a selector is a name for a set somebody else maintains, and the
# round this fixture was added for is the one where an unchanged selector
# resolved somewhere else.
SEAT_PLAY_HOST = "a-machine"

# ...and what that machine says about ITSELF, which is a different kind of fact
# from the label above. The endpoint it answered at and the sha256 of its own
# machine-id: a label is a name somebody else maintains and can repoint at
# another installation without changing one character of it, and six rounds
# recorded and compared exactly that. The endpoints here are deliberately NOT
# addresses -- an inventory may give a name, and a fixture that used an address
# nobody declared would put one in a review bundle.
# A second machine, announced only by a free-text `included: ... for <host>`
# line: the shape the round before had no rule for.
SEAT_SIBLING_HOST = "a-sibling"
# An endpoint this train does NOT declare, as the box would report it. RFC 5737
# documentation space: it exists to be written down and cannot be any machine's
# (R8-H5 turns it into the token OTHER at the moment it is read, so nothing
# downstream ever holds it, and this fixture is what proves that).
SEAT_BOX_ENDPOINT = "192.0.2.17"
OTHER_TOKEN = "OTHER"
SEAT_BOX_ID = "c" * 64
PRIMARY_BOX_ID = "d" * 64
STANDBY_BOX_ID = "e" * 64


def _box_facts(addr=SEAT_BOX_ENDPOINT, box_id=SEAT_BOX_ID, sha=None, host=SEAT_PLAY_HOST):
    """The block a box prints when it is asked who it is, as ansible renders it.

    Two ad-hoc commands: a `debug` whose msg carries the endpoint, and a
    `shell` whose lines carry the boot fingerprint and the checked-out object
    id of the clone the playbook deploys from."""
    out = ['%s | SUCCESS => {' % host,
           '    "msg": "SCR-BOX-ADDR %s"' % addr,
           '}',
           '%s | CHANGED | rc=0 >>' % host,
           'SCR-BOX-ID %s' % box_id]
    if sha:
        out.append('SCR-BOX-SHA %s' % sha)
    return "\n".join(out)


def _with_facts(text, **kw):
    """`text`, then the separator, then the box facts -- one ssh answer."""
    import importlib
    return "%s\n%s\n%s" % (text, "SCR-BOX-FACTS-FOLLOW", _box_facts(**kw))


def _seat_digests(controller=SEAT_CONTROLLER, pve_group=SEAT_PVE_GROUP,
                  primary_limit=SEAT_PRIMARY_LIMIT, standby_limit=SEAT_STANDBY_LIMIT,
                  conf="none", responder=SEAT_PLAY_HOST, play_dir=SEAT_PLAY_DIR,
                  box_addr=OTHER_TOKEN, box_id=SEAT_BOX_ID):
    """The seat binding a snapshot record carries, computed HERE.

    Recomputed from the fixture values rather than read back from the train's
    own helper: a record built by the code under test would satisfy that code
    whatever either of them did."""
    import hashlib
    digest = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()
    return {"controller": digest(controller), "pve_group": digest(pve_group),
            "primary_limit": digest(primary_limit), "standby_limit": digest(standby_limit),
            "play_dir": digest(play_dir),
            # `_seat` points TRAIN_CONF at a file that does not exist, which is
            # the fixed word the train records for a seat file it cannot read.
            "conf": conf,
            # The identity: what the machine said about itself, not what the
            # inventory called it. This is the pair every gate compares.
            "box": {"addr": box_addr, "id": box_id},
            # ...and the label the play's recap printed, kept for the log and
            # compared to nothing. An alias rename is not an identity change.
            "responder_label": digest(responder)}


def _minted(before=None, after=None, **over):
    """The minting provenance phase 0 records: absent before the play, present after.

    Computed rather than written down, like `created_utc`: the freshness window
    is measured from the BEFORE listing now, so a fixed moment would pass today
    and redden by itself tomorrow."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rec = {"absent_before": True, "listed_after": True,
           "before_utc": before or now, "after_utc": after or now,
           "before_count": 0, "after_count": 1}
    rec.update(over)
    return rec


def _fake_git(rt, refs, parents=None, trees=None, status="", ancestor=True, merge_tree=None,
              remote_main=None, replaced=None, unknown=(), origin=ORIGIN_URL,
              remote_rc=0, remote_stderr="", pushurl=None):
    """(`run` stub, log). It answers the READ-ONLY git queries the code phase's
    gates make -- `status --porcelain` from `status`, `rev-parse --verify` from
    `refs` and from `trees`, `rev-list --parents` from `parents`, `merge-base
    --is-ancestor` from `ancestor`, `merge-tree --write-tree` from `merge_tree`
    and `ls-remote` from `remote_main` (which defaults to whatever `refs` says
    main is) -- records every command it is handed, and raises `_NoCommand`
    for anything else, so a test can say both what was asked and that nothing
    else ran. A ref missing from `refs` answers with the empty string, which is
    what `--verify --quiet` prints for one. `ancestor=False` raises the train's
    own Fail, because a non-zero exit is how `run` reports one.

    `replaced` is a local `refs/replace/` ref, modelled the way git behaves: a
    sha listed there answers with the SUBSTITUTED parents and tree to a command
    that does not carry --no-replace-objects, and with its real ones to a
    command that does. The substitution is what the remote does not have, so a
    train that authenticates through it authenticates an object nobody
    deploys. Every command's environment is kept on `_run.envs` beside the log,
    because the option and the variable are two spellings of one instruction
    and a test that only read the argv would miss half of it."""
    log = []
    envs = []
    parents = parents or {}
    trees = trees or {}
    replaced = replaced or {}

    def _run(cmd, **kw):
        joined = " ".join(cmd) if isinstance(cmd, list) else cmd
        log.append(joined)
        envs.append(kw.get("env"))
        argv = [c for c in cmd if c != NO_REPLACE] if isinstance(cmd, list) else cmd
        replacing = isinstance(cmd, list) and NO_REPLACE not in cmd
        if argv[:3] == ["git", "status", "--porcelain"]:
            return status
        if argv[:4] == ["git", "rev-parse", "--git-path", "objects"]:
            # Where THIS repository keeps its objects. The merge-tree path asks
            # for it so it can hand the store back as a read-only alternate
            # while the objects git synthesizes go to a temporary directory
            # that is deleted -- the repository receives none of them.
            return ".git/objects"
        if argv[:3] == ["git", "rev-parse", "--verify"]:
            rev = argv[-1]
            if rev.endswith("^{tree}"):
                bare = rev[:-len("^{tree}")]
                if replacing and bare in replaced:
                    return replaced[bare][1]
                return trees.get(bare, "")
            bare = rev.replace("^{commit}", "")
            if bare in unknown:
                return ""
            if bare in refs:
                return refs[bare]
            # A repository holds the objects these tests name: a full id that no
            # `refs` entry renames resolves to itself, which is what git answers
            # for an object it has. `unknown` is how a test says it has not.
            return bare if _is_full_sha(bare) else ""
        if argv[:2] == ["git", "rev-list"]:
            rev = argv[-1]
            if replacing and rev in replaced:
                return " ".join([rev] + replaced[rev][0])
            return " ".join([rev] + parents.get(rev, []))
        if argv[:2] == ["git", "merge-base"]:
            if ancestor:
                return ""
            raise rt.Fail("merge-base --is-ancestor exited non-zero")
        if argv[:2] == ["git", "merge-tree"]:
            if merge_tree is None:
                raise _NoCommand(joined)
            return merge_tree
        if argv[:3] == ["git", "remote", "get-url"]:
            return origin or ""
        if argv[:2] == ["git", "config"]:
            # `git config --get-all` of a key that is not set exits 1 and
            # prints nothing, which `run` reports as a Fail. `pushurl=None` is
            # that ordinary, unset case. Both keys this reads are MULTI-VALUED,
            # so `pushurl` may be a list and the stub answers with one value
            # per line, exactly as git does.
            if argv[-1] == "remote.origin.url":
                return origin or ""
            if pushurl is None:
                raise rt.Fail("command failed (rc=1):\n")
            return "\n".join(pushurl) if isinstance(pushurl, (list, tuple)) else pushurl
        if argv[:2] == ["git", "ls-remote"]:
            # rc and the two streams are modelled separately: the gate requires
            # the command to have SUCCEEDED and reads its answer from stdout
            # alone, and a stub that merged them could not tell either apart.
            if remote_rc:
                raise rt.Fail("command failed (rc=%d):\n%s" % (remote_rc, remote_stderr))
            head = remote_main if remote_main is not None else refs.get("main", "")
            out = "%s\trefs/heads/main" % head if head else ""
            if remote_stderr and kw.get("merge_stderr", True):
                out = (out + "\n" + remote_stderr) if out else remote_stderr
            return out
        raise _NoCommand(joined)

    _run.envs = envs
    return _run, log


def _snap(**over):
    """A snapshot record that BINDS to the bug392-merge train, as phase 0 writes it.

    `created_utc` is computed rather than written down: the prerequisite has a
    freshness window, so a fixed timestamp would pass today and redden by
    itself tomorrow -- a test whose verdict depends on the calendar."""
    from datetime import datetime, timezone
    rec = {"batch": ABSENT_BATCH, "label": "pre-bug392-merge",
           "name": "cc_pre-bug392-merge__20260922_030000",
           "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "seat": _seat_digests(), "minted": _minted()}
    rec.update(over)
    return {"snapshot": rec}


def _attested(monkeypatch, rt, seen=None, pairs=None):
    """Let a phase past the per-box selector attestation without a network probe.

    The attestation is a read-only ad-hoc probe of each selector, and it has
    its own test with its own reddening arms. Every OTHER phase test stubs it
    the way it stubs `assert_control`: what those tests are about is what
    happens after the gate, and a probe left live here would reach a real
    controller from a unit test.

    It records the (endpoint, boot fingerprint) pair each selector resolved to,
    exactly as the real one does, because the phases below compare a play's own
    statement of who answered against it -- and it fills `_ATTESTED`, which is
    the state `assert_attested()` reads to say whether THIS run asked the
    question before it mutated anything."""
    pairs = pairs if pairs is not None else {
        "primary_limit": (rt.PRIMARY_TOKEN, PRIMARY_BOX_ID),
        "standby_limit": (rt.STANDBY_TOKEN, STANDBY_BOX_ID)}

    def _stub(values=None):
        if seen is not None:
            seen.append(values)
        rt._ATTESTED.clear()
        rt._ATTESTED.update(pairs)
        return dict(pairs)

    monkeypatch.setattr(rt, "attest_deploy_selectors", _stub)
    return pairs


# The shape `run_attested` mints for one invocation: 32 hex characters, passed
# to ansible as an extra variable and echoed back by the facts task through
# Jinja. A fixture value, so a test can compose the answer the controller would
# have printed; the real one is `uuid4().hex`.
NONCE = "0123456789abcdef" * 2
OTHER_NONCE = "f" * 32

# The SYNTHETIC VOCABULARY this module exports (round 9, A3). Every name the
# train's tests hand the train is fabricated: the a-* family, an RFC 5737
# address, a directory under a made-up root. A review harness may carry a failed
# assertion's message into a review document ONLY when every token of it is one
# of these, a word of the train's closed summary vocabulary, a number, or an
# identifier the train declares; any other token -- and ordinary prose is any
# other token -- withholds the whole message. A list rather than a pattern: an
# `a-` prefix is a naming habit, and a habit is not a guarantee.
SYNTHETIC_VOCABULARY = frozenset((
    SEAT_CONTROLLER, SEAT_PVE_GROUP, SEAT_PRIMARY_LIMIT, SEAT_STANDBY_LIMIT,
    SEAT_PLAY_DIR, SEAT_PLAY_HOST, SEAT_SIBLING_HOST, SEAT_BOX_ENDPOINT,
    "a-different-controller", "a-second-group", "a-later-controller", "a-node",
    "a-group-2", ABSENT_BATCH, TRAIN_BATCH,
))


def _facts_body(addr=SEAT_BOX_ENDPOINT, box_id=SEAT_BOX_ID, sha=None):
    """The lines a box prints inside its facts markers, as `debug` renders them."""
    lines = ['        "%s %s",' % ("SCR-BOX-ADDR", addr),
             '        "%s %s",' % ("SCR-BOX-ID", box_id)]
    if sha:
        lines.append('        "%s %s",' % ("SCR-BOX-SHA", sha))
    return "\n".join(lines)


def _facts_section(phase, nonce=NONCE, addr=SEAT_BOX_ENDPOINT, box_id=SEAT_BOX_ID, sha=None):
    """One complete facts section, markers included."""
    return ('        "SCR-FACTS-BEGIN %s %s",\n%s\n        "SCR-FACTS-END %s %s"'
            % (phase, nonce, _facts_body(addr, box_id, sha), phase, nonce))


def _list_body(name=None, stamp="2026-09-22 03:00:01", zone="", rc=0):
    """The wrapper's own listing lines, as `debug` renders them.

    R9-M1: nothing here carries a status. The listing's exit status is the
    PROCESS status the controller's ssh returns -- `_attesting_run` answers it
    beside the text -- and `rc` is kept in this signature only so the callers
    that compose an answer can still say which status they mean."""
    lines = []
    if name:
        lines.append('        "  `-> %s %s%s     auto snapshot",'
                     % (name, stamp, (" " + zone) if zone else ""))
    lines.append('        "  `-> current                   You are here!"')
    return "\n".join(lines)


def _list_section(phase, name=None, stamp="2026-09-22 03:00:01", zone="", rc=0, nonce=NONCE):
    return ('        "SCR-LIST-BEGIN %s %s",\n%s\n        "SCR-LIST-END %s %s"'
            % (phase, nonce, _list_body(name, stamp, zone, rc), phase, nonce))


def _recap(host=SEAT_PLAY_HOST, ok=3, changed=1, unreachable=0, failed=0):
    return ("PLAY RECAP ***\n%s                 : ok=%d    changed=%d    unreachable=%d    "
            "failed=%d" % (host, ok, changed, unreachable, failed))


def _attested_out(nonce=NONCE, addr=SEAT_BOX_ENDPOINT, box_id=SEAT_BOX_ID, sha=None,
                  host=SEAT_PLAY_HOST, middle="", listing=False, name=None,
                  stamp="2026-09-22 03:00:01", zone="", rc=0, after_name=None,
                  sections=None, recap=None, after_addr=None, after_id=None,
                  after_nonce=None, order=None):
    """The whole answer ONE attested `ansible-playbook` invocation prints.

    Facts, optionally the listing, the imported play's own output, optionally
    the listing again, and the facts again -- in that order, each pair of
    markers carrying the token this invocation was given. `sections` overrides
    the composed list entirely, which is how the reddening arms plant an
    absent, a duplicated or an out-of-order section.

    `order` is the order the playbook the train SENT emits, read out of the
    command by `_order_sent`; given one, the answer follows it rather than
    the order the parser wants. R9, found by running: this fixture used to
    compose the parser's order whatever the playbook said, the live after-
    play stated its facts before its listing, and every live listing was
    refused while every fixture passed."""
    if sections is None and order is not None:
        made = {
            ("SCR-FACTS", BEFORE_P): _facts_section(BEFORE_P, nonce, addr, box_id, sha),
            ("SCR-LIST", BEFORE_P): _list_section(BEFORE_P, name, stamp, zone, rc, nonce),
            ("SCR-LIST", AFTER_P): _list_section(
                AFTER_P, after_name if after_name is not None else name, stamp, zone,
                rc, nonce),
            ("SCR-FACTS", AFTER_P): _facts_section(
                AFTER_P, after_nonce or nonce, after_addr or addr, after_id or box_id,
                sha)}
        sections = [middle if step is None else made[step] for step in order]
        if middle and None not in order:
            # no import in the playbook: the output a fixture was handed
            # still sits between the halves, where it always has
            opened = len([s for s in order if s and s[1] == BEFORE_P])
            sections.insert(opened, middle)
    if sections is None:
        sections = [_facts_section(BEFORE_P, nonce, addr, box_id, sha)]
        if listing:
            sections.append(_list_section(BEFORE_P, name, stamp, zone, rc, nonce))
        if middle:
            sections.append(middle)
        if listing:
            sections.append(_list_section(AFTER_P, after_name if after_name is not None
                                          else name, stamp, zone, rc, nonce))
        sections.append(_facts_section(AFTER_P, after_nonce or nonce,
                                       after_addr or addr, after_id or box_id, sha))
    body = "\n".join(s for s in sections if s)
    return "%s\n%s" % (body, recap if recap is not None else _recap(host=host))


BEFORE_P, AFTER_P = "BEFORE", "AFTER"


def _order_sent(joined):
    """The sections the playbook in this command emits, in order; None is the import.

    Decoded out of the command with this module's OWN reading of the playbook
    -- not the train's `composed_order`, which is one of the things the tests
    that use this check. None when the command carries no playbook."""
    import base64 as _b64
    import json as _json
    import re as _re
    blob = _re.search(r"printf %s '?([A-Za-z0-9+/=]+)'? \|", joined)
    if not blob:
        return None
    order = []
    for play in _json.loads(_b64.b64decode(blob.group(1)).decode("utf-8")):
        if "import_playbook" in play:
            order.append(None)
            continue
        for task in play.get("tasks") or ():
            opened = _re.search(r"(SCR-FACTS|SCR-LIST)-BEGIN (BEFORE|AFTER) ",
                                task.get("shell") or "")
            if opened:
                order.append((opened.group(1), opened.group(2)))
    return order


def _attesting_run(rt, asked=None, **kw):
    """A `rt.run` stub that answers the composed playbook the train just sent.

    The nonce is read OUT OF THE COMMAND, which is the only way a fixture can
    echo it: the train mints a fresh one per invocation and the answer has to
    carry that one. A stub that used a constant would make the binding
    unobservable and the control that removes it would redden nothing (#342).

    R9-M1: the train reads the PROCESS status beside the text, so asked
    `with_rc` this answers `(text, status)`; `rc` (default 0) is that status,
    and nothing in the text carries one.

    R9-M2: a command carrying `scr_expect_id` composed the identity gate, and
    this answers the way the box's gate does -- PASSED when the digest the
    train sent is sha256("<token>:<this box's fingerprint>") and the address it
    sent is this box's; otherwise the facts before, a REFUSED line, a failed
    recap and status 2, with no imported play and no after-sections, because
    the process ended at the gate. `gate` forces the verdict ("PASSED",
    "REFUSED", or "SILENT" for a gate that printed nothing)."""
    import hashlib as _hl
    import re as _re
    status = kw.pop("rc", 0)
    forced = kw.pop("gate", None)

    def _run(cmd, **kwargs):
        joined = " ".join(cmd) if isinstance(cmd, list) else cmd
        if asked is not None:
            asked.append(joined)
        found = _re.search(r"-e scr_nonce=([0-9a-f]{32})", joined)
        nonce = found.group(1) if found else NONCE
        seen = dict(kw)
        if seen.get("sections"):
            # Composed sections carry the FIXTURE's token, and the answer has
            # to carry the minted one -- except where an arm planted
            # OTHER_NONCE on purpose, which this substitution leaves alone
            # because it only rewrites the fixture's own value.
            seen["sections"] = [sec.replace(NONCE, nonce) for sec in seen["sections"]]
        else:
            # ...and the answer follows the playbook the train SENT, in the
            # order that playbook emits, not the order the parser wants
            seen["order"] = _order_sent(joined)
        rc = status
        # the value ends at whitespace, at the end of the command, or at a shell
        # command separator (before round 12 a `;` followed the address directly)
        wanted = _re.search(r"-e scr_expect_id=([0-9a-f]{64}) -e scr_expect_addr=([^\s;]+)",
                            joined)
        if wanted:
            box_id = seen.get("box_id", SEAT_BOX_ID)
            addr = seen.get("addr", SEAT_BOX_ENDPOINT)
            mine = _hl.sha256(("%s:%s" % (nonce, box_id)).encode("ascii")).hexdigest()
            verdict = forced or ("PASSED" if (wanted.group(1) == mine and wanted.group(2) == addr)
                                 else "REFUSED")
            if verdict == "REFUSED":
                text = ('        "SCR-FACTS-BEGIN BEFORE %s",\n%s\n        "SCR-FACTS-END BEFORE %s"\n'
                        'fatal: [%s]: FAILED! => {"stdout": "SCR-GATE %s REFUSED"}\n%s'
                        % (nonce, _facts_body(addr, box_id), nonce, SEAT_PLAY_HOST, nonce,
                           _recap(failed=1)))
                return (text, 2) if kwargs.get("with_rc") else text
            if verdict == "PASSED":
                line = '        "SCR-GATE %s PASSED"' % nonce
                seen["middle"] = line + (("\n" + seen["middle"]) if seen.get("middle") else "")
        text = _attested_out(nonce=nonce, **seen)
        return (text, rc) if kwargs.get("with_rc") else text

    return _run


def _listing(name=None, stamp="2026-09-22 03:00:01", zone="", rc=0, agree=True,
             endpoint=None, box_id=SEAT_BOX_ID, fingerprints=None, identity=...,
             responder=SEAT_PLAY_HOST):
    """The listing dict the train's parser produces, composed directly.

    The PARSER has its own test, which drives the real `run_attested` on the
    text a controller would print. Every OTHER test is about what a phase does
    with a listing, so it takes one in the shape the phase receives it -- which
    is also how a phase test stops being a second test of the parser."""
    body = ""
    if name:
        body += "  `-> %s %s%s     auto snapshot\n" % (name, stamp, (" " + zone) if zone else "")
    body += "  `-> current                   You are here!"
    if identity is ...:
        identity = (endpoint if endpoint is not None else OTHER_TOKEN, box_id)
    fps = fingerprints if fingerprints is not None else (
        [identity[1], identity[1]] if identity else [])
    return {"raw": body, "rc": rc, "identity": identity, "responder": responder,
            "agree": agree, "fingerprints": list(fps)}


def _snapshot_is_listed(monkeypatch, rt, name=None, stamp=None):
    """The wrapper's listing, answering that this train's snapshot is still there."""
    name = name or _snap()["snapshot"]["name"]
    if stamp is None:
        from datetime import datetime, timezone
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    monkeypatch.setattr(rt, "snapshot_listing",
                        lambda values=None, _n=name, _s=stamp: _listing(_n, _s))


def test_the_code_phase_binds_the_deploy_to_the_shas_that_were_reviewed(monkeypatch, capsys):
    """H1: a GO is given on a SHA, so that sha is what deploys -- not whatever a branch name points at.

    `branch` is a mutable local ref and `main` is a branch too, so the round-1 train merged and deployed
    whatever they happened to name when the phase ran, and a persisted `code_sha` was deployed on trust.
    Code committed after the review, or a main that moved under it, still emits a canonical-only body and
    still passes every marker this train reads: the markers say WHICH BUILD, and only this says which CODE.
    So the entry names the reviewed tip and the main it was read against, the phase proves both before any
    command that writes, and a recorded merge is deployed only when its two parents are exactly those."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    entry = rt.BATCHES[ABSENT_BATCH]
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    assert entry["reviewed_tip"] == REVIEWED_FULL and entry["main_expected"] == MAIN_FULL
    assert rt.REVIEWED_TIP == REVIEWED_FULL and rt.MAIN_EXPECTED == MAIN_FULL
    assert REVIEWED_FULL in rt.provenance_words() and MAIN_FULL in rt.provenance_words()

    good = {rt.BRANCH: REVIEWED_FULL, "main": MAIN_FULL}
    trees = {REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: REVIEWED_TREE}
    go = SimpleNamespace(go=True)
    deployed = []
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    monkeypatch.setattr(rt, "_deploy_both", lambda sha, extra=None, st=None, **_kw: deployed.append(sha))
    monkeypatch.setattr(rt, "code_state", lambda host: (True, False, True, ["alias present"]))
    _snapshot_is_listed(monkeypatch, rt)

    def refuses(refs, parents, st, *must_name):
        stub, log = _fake_git(rt, refs, parents, trees)
        monkeypatch.setattr(rt, "run", stub)
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(go, dict(st))
        for text in must_name:
            assert text in str(exc.value), (text, str(exc.value))
        # nothing was merged, pushed, checked out or deployed
        assert deployed == [], log
        assert not [c for c in log if c.split()[1:2] and c.split()[1] in
                    ("merge", "push", "checkout", "commit")], log
        return str(exc.value)

    # (a) the branch moved since the GO -- both shas are printed
    refuses(dict(good, **{rt.BRANCH: OTHER_FULL}), None, _snap(), OTHER_FULL, REVIEWED_FULL)
    # ...including a branch that no longer resolves at all
    refuses({k: v for k, v in good.items() if k != rt.BRANCH}, None, _snap(),
            "unresolvable", REVIEWED_FULL)
    # (b) main moved -- the merge would carry commits the review never saw
    refuses(dict(good, main=OTHER_FULL), None, _snap(), OTHER_FULL, MAIN_FULL)
    # (c) the entry names a sha this repository does not HOLD: the binding is
    # uncheckable, which is a refusal and never a pass. A well-shaped id is not
    # the same claim as an id that exists, and only the second one can be
    # compared against anything.
    stub, log = _fake_git(rt, good, trees=trees, unknown=(REVIEWED_FULL,))
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, _snap())
    assert "reviewed_tip" in str(exc.value) and REVIEWED_FULL in str(exc.value), str(exc.value)
    assert deployed == [], log
    # (d) a persisted code_sha whose parents are not exactly the two bound shas
    stale = dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True)
    for wrong, why in (([MAIN_FULL, OTHER_FULL], "a merge of some other branch"),
                       ([OTHER_FULL, REVIEWED_FULL], "merged onto some other main"),
                       ([REVIEWED_FULL, MAIN_FULL], "the same two the wrong way round"),
                       ([MAIN_FULL], "not a merge at all"),
                       ([], "no parents: a root commit")):
        msg = refuses(good, {MERGE_FULL: wrong}, stale, MAIN_FULL, REVIEWED_FULL)
        assert MERGE_FULL in msg, why

    # inert twin 1: all three hold and there is no recorded sha, so the phase
    # proceeds -- the gates are read FIRST, and the first write is the merge
    stub, log = _fake_git(rt, good, trees=trees)
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(_NoCommand) as exc:
        rt.phase_code(go, _snap())
    assert log[0] == "git status --porcelain", log       # the clean gate opens the phase
    assert log[1].startswith("git %s rev-parse --verify" % NO_REPLACE), log
    assert str(exc.value).startswith("git checkout main"), log
    assert deployed == []

    # inert twin 2: the recorded sha IS the reviewed merge -- right parents AND
    # right tree -- so it deploys, and it is the only thing that deploys. main
    # sits on that merge, which is where `git merge` left it.
    stub, log = _fake_git(rt, dict(good, main=MERGE_FULL),
                          {MERGE_FULL: [MAIN_FULL, REVIEWED_FULL]}, trees)
    monkeypatch.setattr(rt, "run", stub)
    monkeypatch.setattr(rt, "code_state", lambda host: (True, True, False, ["alias absent"]))
    monkeypatch.setattr(rt, "assert_route_probes", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_health_keys", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_edge_runs_new_code", lambda: None)
    st = dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True)
    rt.phase_code(go, st)
    assert deployed == [MERGE_FULL] and st["code_deployed"] is True

    # the plan says what it is bound to, without running anything that writes
    capsys.readouterr()
    stub, _log = _fake_git(rt, good, trees=trees)
    monkeypatch.setattr(rt, "run", stub)
    rt.phase_code(SimpleNamespace(go=False), _snap())
    out = capsys.readouterr().out
    # the FULL ids, in the plan as well as in a refusal: an abbreviation in a
    # transcript is a reader's invitation to compare seven characters
    assert REVIEWED_FULL in out and MAIN_FULL in out, out

    # half a binding is refused: the pair says which code AND what it was read
    # against, and one end alone would announce a check that is not made
    for broken in ({"main_expected": None}, {"reviewed_tip": None}):
        rt.BATCHES["_half"] = dict(entry, **broken)
        try:
            with pytest.raises(rt.Fail) as exc:
                rt.select_batch("_half")
            assert "binding is both shas or neither" in str(exc.value)
        finally:
            del rt.BATCHES["_half"]
    rt.select_batch(ABSENT_BATCH)


# ── round 3: what the second cold review raised on the c32a1f5 pin ───────
#
# Same shape as the round-2 block above: one test per finding number, each with
# an arm that reddens when the fix is absent and an inert twin that stays green.


def test_the_code_phase_refuses_a_dirty_tree_and_a_merge_that_is_not_the_reviewed_content(monkeypatch):
    """R2-H1: exact parents do not authenticate a merge's CONTENT, and only the sql path ever asked for a clean tree.

    `git merge --no-ff` commits the INDEX. An edit staged in this checkout for any other reason -- a
    debug line, a half-finished fix, a file another session sharing this tree left behind (#418) -- is
    therefore inside a merge whose two parents are exactly main_expected and reviewed_tip, and every
    marker this train reads afterwards still says NEW, because the box really does run a build that
    retired the alias. The batch with no migration skips the precursor, which was the only phase that
    had ever asked whether the tree was clean, so nothing asked at all. Two halves, one closure: the
    clean gate opens the code phase for EVERY batch, and the tree is compared against the tree the
    reviewed merge has to carry -- on a merge this phase just made and on one it read back."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    good = {rt.BRANCH: REVIEWED_FULL, "main": MAIN_FULL}
    right = {REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: REVIEWED_TREE}
    wrong = {REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: OTHER_TREE}
    merged_parents = {MERGE_FULL: [MAIN_FULL, REVIEWED_FULL]}
    go = SimpleNamespace(go=True)
    deployed = []
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    monkeypatch.setattr(rt, "_deploy_both", lambda sha, extra=None, st=None, **_kw: deployed.append(sha))
    monkeypatch.setattr(rt, "code_state", lambda host: (True, False, True, ["alias present"]))
    _snapshot_is_listed(monkeypatch, rt)

    # (a) a staged, non-conflicting edit in the checkout: refused at the gate,
    # with the porcelain lines printed, before any command but the read itself
    staged = "M  backend/api/main.py\nA  backend/api/scratch.py"
    stub, log = _fake_git(rt, good, trees=right, status=staged)
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, _snap())
    assert "not clean" in str(exc.value) and "backend/api/main.py" in str(exc.value)
    assert "backend/api/scratch.py" in str(exc.value)
    assert log == ["git status --porcelain"], log
    assert deployed == []

    # ...and the sql path asks the same question through the same gate: one
    # implementation, so the two cannot drift into different ideas of clean
    rt.select_batch("rejoin-phase-a")
    stub, log = _fake_git(rt, good, status=staged)
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_precursor(SimpleNamespace(go=True), {})
    assert "not clean" in str(exc.value) and "backend/api/main.py" in str(exc.value)
    rt.select_batch(ABSENT_BATCH)

    # (b) the merge this phase MAKES: two correct parents, a tree that is not
    # the reviewed tree -- which is what a staged edit produces
    def fresh_path(stub_, log_):
        def _run(cmd, **kw):
            if isinstance(cmd, list) and cmd[:2] in (["git", "checkout"], ["git", "merge"],
                                                     ["git", "commit"], ["git", "push"]):
                log_.append(" ".join(cmd))
                return ""
            if cmd == ["git", "rev-parse", "HEAD"]:
                log_.append(" ".join(cmd))
                return MERGE_FULL
            return stub_(cmd, **kw)
        return _run

    stub, log = _fake_git(rt, good, merged_parents, wrong)
    monkeypatch.setattr(rt, "run", fresh_path(stub, log))
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, dict(_snap(), pre_code_old_build=True))
    assert "WRONG CONTENT" in str(exc.value) and "newly merged" in str(exc.value)
    assert OTHER_TREE in str(exc.value) and REVIEWED_TREE in str(exc.value)
    assert deployed == []                       # it is caught before the deploy

    # (c) a persisted code_sha with matching parents and a different tree: the
    # same refusal, and this one never reaches a writing command at all
    stub, log = _fake_git(rt, dict(good, main=MERGE_FULL), merged_parents, wrong)
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True))
    assert "WRONG CONTENT" in str(exc.value) and "persisted" in str(exc.value)
    assert deployed == []
    assert not [c for c in log if c.split()[1:2] and c.split()[1] in
                ("merge", "push", "checkout", "commit")], log

    # (d) inert twin: exact parents AND exact tree -> it proceeds and deploys,
    # and that merge is the only thing deployed
    stub, log = _fake_git(rt, dict(good, main=MERGE_FULL), merged_parents, right)
    monkeypatch.setattr(rt, "run", stub)
    monkeypatch.setattr(rt, "code_state", lambda host: (True, True, False, ["alias absent"]))
    monkeypatch.setattr(rt, "assert_route_probes", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_health_keys", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_edge_runs_new_code", lambda: None)
    st = dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True)
    rt.phase_code(go, st)
    assert deployed == [MERGE_FULL] and st["code_deployed"] is True

    # (e) the general branch: when main_expected is NOT an ancestor of the
    # reviewed tip the tree cannot be read off either side, so it is the tree
    # git merges the two into -- and a merge-tree that reports conflicts is a
    # merge this train cannot reproduce, which is a refusal and not a pass
    deployed[:] = []
    stub, log = _fake_git(rt, dict(good, main=MERGE_FULL), merged_parents, wrong,
                          ancestor=False, merge_tree=OTHER_TREE)
    monkeypatch.setattr(rt, "run", stub)
    rt.phase_code(go, dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True))
    assert deployed == [MERGE_FULL]             # merge-tree says OTHER_TREE, and it matches
    deployed[:] = []
    stub, log = _fake_git(rt, dict(good, main=MERGE_FULL), merged_parents, wrong,
                          ancestor=False,
                          merge_tree=OTHER_TREE + "\n100644 %s 1\tbackend/api/main.py" % OTHER_TREE)
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True))
    assert "did not produce one clean tree" in str(exc.value)
    assert deployed == []


def test_the_code_phase_accepts_main_at_its_own_merge_and_refuses_it_anywhere_else(monkeypatch):
    """R2-M2: once the merge lands main IS the merge, and the prescribed resume demanded main_expected.

    `git merge` moves main onto the commit it creates, so a train whose primary deploy succeeded and
    whose standby deploy failed has main sitting on code_sha. The documented recovery, `--from code`,
    then read main, compared it with main_expected and refused the train's own work -- leaving the fleet
    split, primary new and standby old, which is the bug #266 shape with nothing left to fix it. main now
    has two expected values, and which one applies is decided by whether an AUTHENTICATED merge is
    recorded: a state file that has not passed the parents-and-tree check may not move the goalposts."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    good = {rt.BRANCH: REVIEWED_FULL}
    right = {REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: REVIEWED_TREE}
    merged_parents = {MERGE_FULL: [MAIN_FULL, REVIEWED_FULL]}
    go = SimpleNamespace(go=True)
    deployed = []
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    monkeypatch.setattr(rt, "_deploy_both", lambda sha, extra=None, st=None, **_kw: deployed.append(sha))
    monkeypatch.setattr(rt, "assert_route_probes", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_health_keys", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_edge_runs_new_code", lambda: None)
    monkeypatch.setattr(rt, "code_state", lambda host: (True, True, False, ["alias absent"]))
    _snapshot_is_listed(monkeypatch, rt)
    resumed = dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True)

    # the recovery this exists for: the merge landed, main is on it, the primary
    # deployed and the standby did not -- `--from code` runs the deploy again
    stub, _log = _fake_git(rt, dict(good, main=MERGE_FULL), merged_parents, right)
    monkeypatch.setattr(rt, "run", stub)
    st = dict(resumed)
    rt.phase_code(go, st)
    assert deployed == [MERGE_FULL] and st["code_deployed"] is True

    # main at NEITHER expected value: a checkout holding a history this phase
    # would not deploy, so it refuses and names both
    deployed[:] = []
    stub, log = _fake_git(rt, dict(good, main=OTHER_FULL), merged_parents, right)
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, dict(resumed))
    assert OTHER_FULL in str(exc.value) and MERGE_FULL in str(exc.value)
    assert MAIN_FULL in str(exc.value)
    assert deployed == []

    # the goalposts move only for a merge that AUTHENTICATES: a recorded sha
    # with the wrong parents is refused on its own terms, even with main on it
    stub, log = _fake_git(rt, dict(good, main=MERGE_FULL),
                          {MERGE_FULL: [MAIN_FULL, OTHER_FULL]}, right)
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, dict(resumed))
    assert "not the reviewed merge" in str(exc.value)
    assert deployed == []

    # inert twin, the other arm: no merge recorded yet, so main must be the
    # reviewed main -- and it proceeds from there to make one
    stub, log = _fake_git(rt, dict(good, main=MAIN_FULL), trees=right)
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(_NoCommand) as exc:
        rt.phase_code(go, dict(_snap(), pre_code_old_build=True))
    assert str(exc.value).startswith("git checkout main")
    # ...and with no merge recorded, main sitting on one is still a refusal
    stub, log = _fake_git(rt, dict(good, main=MERGE_FULL), trees=right)
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, dict(_snap(), pre_code_old_build=True))
    assert "reviewed against" in str(exc.value) and MAIN_FULL in str(exc.value)
    assert deployed == []


def test_the_two_provenance_anchors_are_object_ids_and_the_transcript_prints_them_whole(
        monkeypatch, capsys):
    """R4-H1: `reviewed_tip` and `main_expected` were seven-hex revision NAMES, resolved at run time.

    They are the two ends of the whole provenance chain: the branch is compared against one, main
    against the other, the merge's parents have to be exactly those two and its tree has to be the
    tree the first one carries. All of that was anchored to an abbreviation -- the same form the
    persisted `code_sha` is refused for. git resolves an abbreviation against the objects this
    checkout happens to hold, so a fresh or pruned clone, or one carrying a second object whose id
    begins with the same seven characters, resolves it to a commit the review never saw; the merge
    built on it then authenticates, deploys and reads as the new build on every marker. The anchors
    are canonical ids, the shape is asked when the entry is SELECTED -- before the phase's first git
    command -- and every line that prints them prints them whole."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    entry = rt.BATCHES[ABSENT_BATCH]
    assert entry["reviewed_tip"] == REVIEWED_FULL and entry["main_expected"] == MAIN_FULL

    # (a) the reddening arm: an abbreviation, a ref, an upper-case id, an id
    # with a stray space and a number are each refused at selection -- with a
    # stub installed that raises on ANY command, so reaching one is the failure
    monkeypatch.setattr(rt, "run", lambda cmd, **kw: _raise_no_command(cmd))
    for field in ("reviewed_tip", "main_expected"):
        for bad in (REVIEWED_FULL[:7], "main", "HEAD", REVIEWED_FULL.upper(),
                    REVIEWED_FULL + " ", REVIEWED_FULL + "\n", 990):
            rt.BATCHES["_anchor"] = dict(entry, **{field: bad})
            try:
                with pytest.raises(rt.Fail) as exc:
                    rt.select_batch("_anchor")
                assert "40-character object id" in str(exc.value), (field, bad)
                assert repr(bad) in str(exc.value), (field, bad, str(exc.value))
            finally:
                del rt.BATCHES["_anchor"]
    rt.select_batch(ABSENT_BATCH)

    # (b) a well-shaped id this repository does not HOLD is a different claim,
    # and it is refused where it can be: at resolution, with the id printed
    trees = {REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: REVIEWED_TREE}
    good = {rt.BRANCH: REVIEWED_FULL, "main": MAIN_FULL}
    for missing in (REVIEWED_FULL, MAIN_FULL):
        stub, log = _fake_git(rt, good, trees=trees, unknown=(missing,))
        monkeypatch.setattr(rt, "run", stub)
        monkeypatch.setattr(rt, "save_state", lambda st_: None)
        _snapshot_is_listed(monkeypatch, rt)
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(SimpleNamespace(go=True), _snap())
        assert missing in str(exc.value), (missing, str(exc.value))
        assert "cannot resolve" in str(exc.value)
        assert not [c for c in log if c.split()[1:2] and c.split()[1] in
                    ("merge", "push", "checkout", "commit")], log

    # (c) inert twin: the anchors resolve, and the plan prints them whole --
    # both of them, and the ids the provenance line carries as well
    stub, _log = _fake_git(rt, good, trees=trees)
    monkeypatch.setattr(rt, "run", stub)
    capsys.readouterr()
    rt.phase_code(SimpleNamespace(go=False), _snap())
    out = capsys.readouterr().out
    assert REVIEWED_FULL in out and MAIN_FULL in out, out
    assert REVIEWED_FULL[:7] + " " not in out, "an abbreviation is still printed somewhere"


def test_health_reports_both_steam_words_and_the_render_loop_runs_on_both_roles():
    src = inspect.getsource(main.health_check)
    assert "pc_steam_sweep=_pc_steam_sweep_word()" in src and "pc_steam_render=_pc_steam_render_word()" in src
    assert "pc_steam_render" in schemas.HealthResponse.model_fields
    assert main._pc_steam_render_word() in ("starting", "paused:renderer")   # no loop ran under the tests
    life = inspect.getsource(main.lifespan)
    sweep = life.index("tasks.append(asyncio.create_task(_pc_steam_sweep_loop()))")
    render = life.index("tasks.append(asyncio.create_task(_pc_steam_render_loop()))")
    assert sweep < render
    assert life.rfind("if not IS_REPLICA and _pcs is not None:", 0, sweep) > life.rfind("\n\n", 0, sweep) - 400
    assert "if _pcs is not None and _pcf is not None:" in life[sweep:render]

    def indent(i):
        return i - (life.rfind("\n", 0, i) + 1)
    assert indent(render) < indent(sweep)   # the render loop sits OUTSIDE the primary-only gate
    expire = life.index("tasks.append(asyncio.create_task(_pc_face_cache_expire_loop()))")
    assert render < expire and indent(expire) == indent(render)   # the derived-face expiry runs on BOTH roles (v4 §4)
    assert "if _pc_face_cache is not None:" in life[render:expire]
    assert main._PC_STEAM_RENDER_RETRY_S == 30 and main._PC_STEAM_RENDER_IDLE_S == 600


# ── the blob janitor ───────────────────────────────────────────────────

def test_the_blob_janitor_holds_one_lock_per_transaction():
    a, b = "a" * 64, "b" * 64
    db = Scripted({"SELECT hash FROM pc_portraits": [[{"hash": a}, {"hash": b}]],
                   "DELETE FROM pc_portraits": [[{"hash": a}], []]})
    assert _run(main._pc_portrait_blob_janitor(db)) == 1
    assert db.committed == 3   # the candidate read, then one per candidate: a P lock never spans two blobs
    sel = db.log[0]
    assert "unreferenced_since < now() - make_interval(mins => CAST(:m AS integer))" in sel[0]
    assert sel[1] == {"m": main._PC_STEAM_GRACE_MINUTES, "n": main._PC_STEAM_JANITOR_BATCH} == {"m": 10, "n": 50}
    locks = [i for i, (s, _) in enumerate(db.log) if "CAST(:cls AS integer)" in s]
    deletes = [i for i, (s, _) in enumerate(db.log) if "DELETE FROM pc_portraits" in s]
    assert len(locks) == len(deletes) == 2 and all(l < d for l, d in zip(locks, deletes))
    assert [db.log[i][1]["h"] for i in locks] == [a, b] == [db.log[i][1]["h"] for i in deletes]
    dele, dparams = db.log[deletes[0]]
    assert "unreferenced_since < now() - make_interval(mins => CAST(:m AS integer))" in dele, \
        "the grace is re-checked under P: a blob re-used and released again since the candidate read is young"
    assert dparams == {"h": a, "m": main._PC_STEAM_GRACE_MINUTES}
    assert "pc_game_portrait_hash = CAST(:h AS text)" in dele
    assert "pc_steam_portrait_hash = CAST(:h AS text)" in dele and "RETURNING hash" in dele
    assert inspect.getsource(main._pc_portrait_blob_janitor).count("await _pc_lock_blob(") == 1


# ── the events hold-back ───────────────────────────────────────────────

def test_the_handout_and_card_apply_the_pools_ban_word_to_puller_and_subject():
    """r5 M3/M4 (2026-09-13): an active ban keeps a player out of the pool at
    the open (_PC_STEAM_ELIGIBLE_SQL); the handout says the same of the puller
    and the subject in its skip, its page and its final selection, and /card
    says it of the subject live rather than trusting the latest snapshot. One
    fragment, formatted with the row alias, so the word cannot drift."""
    ban = main._PC_NOT_BANNED_SQL
    assert ban == ("NOT EXISTS (SELECT 1 FROM player_bans b WHERE b.steam_id = {a}.steam_id AND "
                   + main.player_ban_active_sql("b") + ")")
    assert main._PC_STEAM_ELIGIBLE_SQL.count(ban.format(a="p")) == 1
    skip, pend = main._PC_EVENTS_SKIP_SQL, main._PC_EVENTS_PENDING_SQL
    for alias in ("pl", "su"):
        assert skip.count(ban.format(a=alias)) == 1, alias
    assert skip.index("AND NOT (pl.deleted_at IS NULL") < skip.index(ban.format(a="pl")) < skip.index("e.print_id IS NULL OR EXISTS")
    assert pend.count(ban.format(a="su")) == 2 and pend.count(ban.format(a="pl")) == 1   # page CTE + final; final
    assert pend.index(ban.format(a="su")) < pend.index("LIMIT 20")                       # the page never selects one
    card = inspect.getsource(main.internal_pc_card)
    assert "JOIN players p ON p.id = m.player_id" in card
    assert 'AND """ + _PC_POOL_MEMBER_SQL + """' in card and "_PC_NOT_BANNED_SQL" not in card   # v4.13: the pool word
    assert main._PC_POOL_MEMBER_SQL.count(ban.format(a="p")) == 1   # ... whose ban clause is this word's text
    assert card.index("JOIN players p ON p.id = m.player_id") < card.index('detail={"error": "not_in_pool"}')
    # r6 H1/M2: ONE deliverability word for the skip, the handout and the send
    frag = main._PC_EVENT_DELIVERABLE_SQL
    assert frag.count(ban.format(a="pl")) == 1 and frag.count(ban.format(a="su")) == 1
    assert frag.startswith("(pl.deleted_at IS NULL AND su.deleted_at IS NULL") and "pl.pc_announce AND su.pc_announce" in frag
    assert "e.print_id IS NULL OR EXISTS (SELECT 1 FROM pc_prints pr WHERE pr.id = e.print_id AND pr.discarded_at IS NULL)" in frag
    assert skip.count("AND NOT " + frag) == 1 and pend.count("AND " + frag) == 1
    assert skip.count("pc_announce") == 2 and pend.count("pc_announce") == 2   # no second spelling beside the word


def test_the_lease_recheck_authorises_the_whole_line_for_both_parties():
    """r6 H1/M2 (2026-09-13): the bot's send is authorised by the lease's
    re-check, so the re-check must say no when the subject is deleted OR
    banned (outright: a no-picture subject leased NULL and a ban resolves to
    NULL too), when the print stopped being the subject's, and when any event
    the lease names is no longer deliverable for EITHER party -- the puller
    included, whom the subject's row never covered."""
    src = inspect.getsource(main.internal_pc_lease_check)
    assert '_PC_PORTRAIT_RESOLVE_COLS + "," + _PC_LEASE_PRINT_OK + "," + _PC_LEASE_EVENTS_OK' in src
    assert 'row["subject_deleted"] or row["subject_banned"]' in src
    assert 'not row["print_deliverable"] or not row["events_ok"]' in src
    ok = main._PC_LEASE_EVENTS_OK
    # per named id, fail-closed (r7 H1): a named event that no longer exists withdraws the lease;
    # NULL or empty event lists (a /card lease) unnest to nothing and stay valid
    assert "FROM unnest(l.event_ids) AS named(id)" in ok
    assert (ok.index("NOT EXISTS (") < ok.index("FROM unnest(l.event_ids)") < ok.index("WHERE NOT EXISTS (")
            < ok.index("WHERE e.id = named.id AND " + main._PC_EVENT_DELIVERABLE_SQL + ")) AS events_ok"))
    assert "e.id = ANY(l.event_ids)" not in ok   # the vacuous anti-join is gone
    assert "JOIN players pl ON pl.id = e.player_id" in ok and "JOIN players su ON su.id = e.subject_player_id" in ok
    assert "AS subject_banned" in main._PC_PORTRAIT_RESOLVE_COLS


def test_the_public_pool_summary_speaks_the_pools_live_word():
    """r6 M3: /pc/pool leaves out members deleted or banned since the snapshot
    the way /card and the pack open do, in ONE statement (bands, count and
    names from one read)."""
    src = inspect.getsource(main.pc_pool_summary)
    # the pool word, WHOLE -- and the enumeration is an assertion rather than a
    # comment, because the comment that stood here listed three of its four
    # clauses (found 2026-09-15) and a prose list cannot go red when the word
    # gains or loses one
    assert src.count('AND """ + _PC_POOL_MEMBER_SQL + """') == 1
    word = main._PC_POOL_MEMBER_SQL
    for clause in ("p.deleted_at IS NULL",                       # deleted
                   main._PC_NOT_BANNED_SQL.format(a="p"),        # banned
                   main._PC_POOL_STEAM_ID_SQL,                   # id not a SteamID64 (v4.13)
                   "p.mod_seen_at IS NOT NULL"):                 # never ran the mod (the merge's rule 3)
        assert word.count(clause) == 1, clause
    assert "WITH live AS (" in src and "UNION ALL" in src and src.count("await db.execute") == 2   # the snapshot row, then the one read
    assert '"member_count": sum(bands.values())' in src and 'int(snap["member_count"])' not in src


def test_the_hold_releases_on_resolution_never_on_an_attempt_and_names_face_ready():
    res = main._PC_EVENTS_RESOLVED_SQL
    for term in ("su.pc_game_portrait_hash IS NOT NULL", "su.pc_steam_portrait_hash IS NOT NULL",
                 "(su.pc_steam_avatar_ref IS NOT NULL AND su.pc_steam_portrait_fail = 0)"):
        assert term in res, term
    for dead in ("pc_portrait_source", "pc_opted_out_at"):   # no plate by choice since 2026-09-13
        assert dead not in res, dead
    assert "next_at" not in res and "portrait_at" not in res   # an attempt, a lease or a failure resolves nothing
    assert main._PC_EVENTS_HOLD_SQL == "(" + res + " OR e.created_at < now() - INTERVAL '60 seconds')"
    pending = main._PC_EVENTS_PENDING_SQL
    assert pending.count(main._PC_EVENTS_HOLD_SQL) == 1       # decided ONCE, in the page CTE (c6 F: a page never cuts a group)
    cte = pending[:pending.index("SELECT e.id, e.kind")]
    assert main._PC_EVENTS_HOLD_SQL in cte and "JOIN players su ON su.id = e.subject_player_id" in cte
    assert pending.count(res + " AS face_ready") == 1
    assert '"face_ready": bool(r["face_ready"])' in inspect.getsource(main.internal_pc_events_pending)
    bot = (REPO / "backend" / "discord_bot.py").read_text(encoding="utf-8")
    assert 'if lease[0] and p.get("print_id") and first.get("face_ready", True):' in bot   # the face rides under the line's lease (r6 H1)


# ── the settings routes ────────────────────────────────────────────────

def test_the_settings_writer_takes_no_blob_lock_and_releases_nothing(monkeypatch):
    """2026-09-13: with no None write and no opt-out, every settings write is
    the plain CAS — actor, row lock, the revision-bound UPDATE, commit — with
    no lock of the route's own, no P lock, no blob release and no lease wait.
    (The shared identity hold lives in the actor helper, which this test
    replaces; test_pc_routes pins it there.) The two keys that used to carry
    the picture choices are refused as unknown before any read."""
    async def actor(request, steam_id, sig, canon, db):
        db.log.append(("ACTOR", {"steam_id": steam_id}))
        return SimpleNamespace(id=PID)

    async def settings_of(db, pid):
        return {"revision": 6}

    # trades_open (migration 353) exists only once the trading schema does:
    # the writer asks the schema probe first, found here
    schema = {"state": "found"}

    async def trade_schema(db):
        return schema["state"]
    monkeypatch.setattr(main, "_pc_verified_actor", actor)
    monkeypatch.setattr(main, "_pc_settings_of", settings_of)
    monkeypatch.setattr(main, "_pc_trade_schema", trade_schema)

    def call(db, key, value, revision=5):
        return _run(main.pc_set_setting(request=_Req(), steam_id=STEAM, sig="s", nonce="n" * 8, revision=revision,
                                        key=key, value=value, db=db))
    for key in main._pc.SETTINGS_KEYS:
        for value in (0, 1):
            db = Scripted({"RETURNING pc_settings_revision": [[{"pc_settings_revision": 6}]]})
            assert call(db, key, value) == {"revision": 6} and db.committed == 1 and db.rolled_back == 0
            order = [_idx(db, k) for k in ("ACTOR", "FOR NO KEY UPDATE", "RETURNING pc_settings_revision")]
            assert order == sorted(order), (key, order)
            assert db.log[_idx(db, "RETURNING pc_settings_revision")][1] == {"value": value, "pid": str(PID), "rev": 5}
            for absent in ("pg_advisory_xact_lock(hashtext", "CAST(:cls AS integer)", "UPDATE pc_portraits",
                           "SELECT pc_game_portrait_hash, pc_steam_portrait_hash", "pc_delivery_leases"):
                assert db.count(absent) == 0, (key, absent)
    # a stale revision writes nothing and rolls back
    db = Scripted({"RETURNING pc_settings_revision": [[]]})
    with pytest.raises(HTTPException) as ei:
        call(db, "announce", 0, revision=4)
    assert ei.value.status_code == 409 and ei.value.detail["error"] == "stale_revision"
    assert db.rolled_back == 1 and db.committed == 0
    # the retired keys are unknown settings: refused before the actor is even verified
    for key in ("opted_out", "portrait_source"):
        db = Scripted({})
        with pytest.raises(HTTPException) as ei:
            call(db, key, 1)
        assert ei.value.status_code == 422 and db.log == []
    # trading's switch while the probe does not find its schema: 503 before
    # the actor is verified and before any write; the other keys still write
    for state in ("missing", "partial", "unknown"):
        schema["state"] = state
        db = Scripted({})
        with pytest.raises(HTTPException) as ei:
            call(db, "trades_open", 0)
        assert ei.value.status_code == 503 and ei.value.detail == {"error": "trading_unavailable"}, state
        assert db.log == [] and db.committed == 0, state
        db = Scripted({"RETURNING pc_settings_revision": [[{"pc_settings_revision": 6}]]})
        assert call(db, "announce", 1) == {"revision": 6} and db.committed == 1, state


def test_the_admin_clear_restarts_the_steam_unit_and_the_render_guard_refuses_the_plate():
    clear = inspect.getsource(main._pc_clear_portrait_unit)
    for s in ('"pc_steam_portrait_hash = NULL"', '"pc_steam_avatar_ref = NULL"', '"pc_steam_portrait_fail = 0"',
              '"pc_steam_attempt = pc_steam_attempt + 1"',   # v4 §1: the same for the admin clear and the deletion path
              'sets.append("pc_steam_portrait_next_at = now()")',
              'sets.append("pc_steam_portrait_next_at = now() + make_interval(days => CAST(:days AS integer))")'):
        assert s in clear, s
    assert clear.count("await _pc_release_portrait_blob(db, h)") == 1 and "DELETE FROM pc_portraits" not in clear
    # the missing-blob guard on every render path: the face route's renderer, the pre-render, the preview
    assert "raise _PcPortraitMissing()" in inspect.getsource(main._pc_render_face)
    assert "except _PcPortraitMissing:" in inspect.getsource(main._pc_prerender)
    assert "raise _PcPortraitMissing()" in inspect.getsource(main._pc_preview_face)   # both preview routes draw here (row 24)
    assert MAIN_SRC.count("raise _PcPortraitMissing()") == 2
    ex = main._PcPortraitMissing()
    assert ex.status_code == 503 and ex.headers == {"Retry-After": "2"}
    assert ex.detail == {"error": "portrait_pending", "retry_after": 2}


# ── the face cache's age bound ─────────────────────────────────────────

def test_the_face_cache_forgets_faces_untouched_for_a_week(tmp_path):
    cache = pc_portrait.FaceCache(str(tmp_path), cap_bytes=1 << 20)
    old, new = "p/one/aaaa/en/card.png", "p/two/bbbb/en/tile.png"
    cache._publish(old, b"1" * 10)
    cache._publish(new, b"2" * 10)
    now = time.time()
    cache._seen[old] = now - 20
    assert cache.expire(max_age_s=10, now=now) == 1
    assert not os.path.exists(cache.path(old)) and os.path.exists(cache.path(new))
    assert old not in cache._sizes and old not in cache._atime and old not in cache._seen and new in cache._seen
    assert cache.read(new) == b"2" * 10 and cache._seen[new] >= now   # a read touches the age
    assert pc_portrait.FACE_CACHE_MAX_AGE_S == 7 * 86400
    # after a restart the age is the file's publish age
    os.utime(cache.path(new), (now - 3600, now - 3600))
    fresh = pc_portrait.FaceCache(str(tmp_path), cap_bytes=1 << 20)
    assert fresh.expire(max_age_s=600, now=now) == 1 and not os.path.exists(cache.path(new))
    assert fresh.expire(max_age_s=600, now=now) == 0
    # each box ages its own cache from the expiry loop (both roles, v4 §4); the primary-only janitor step no longer does
    assert "_pc_face_cache.expire" not in inspect.getsource(main._pc_snapshot_janitor_step)
    loop = inspect.getsource(main._pc_face_cache_expire_loop)
    assert "await asyncio.to_thread(_pc_face_cache.expire)" in loop and "_PC_FACE_EXPIRE_EVERY_S" in loop
    assert main._PC_FACE_EXPIRE_EVERY_S == 3600


def test_the_face_cache_never_leaves_a_face_nothing_tracks(tmp_path, monkeypatch):
    cache = pc_portrait.FaceCache(str(tmp_path), cap_bytes=1 << 20)
    key = "p/one/aaaa/en/card.png"
    folder = os.path.dirname(cache.path(key))
    real_replace = os.replace
    # an interrupted publish leaves no temporary behind and no index entry

    def die(src, dst):
        raise OSError("disk")
    monkeypatch.setattr(os, "replace", die)
    with pytest.raises(OSError):
        cache._publish(key, b"1" * 10)
    monkeypatch.setattr(os, "replace", real_replace)
    assert os.listdir(folder) == [] and key not in cache._sizes and key not in cache._seen
    # a temporary an earlier process left (a publish that died between the write and the swap-in) is aged out
    tmp = cache.path(key) + ".tmp-999"
    now = time.time()
    with open(tmp, "wb") as f:
        f.write(b"x")
    os.utime(tmp, (now - 7200, now - 7200))
    assert cache.expire(now=now) == 1 and not os.path.exists(tmp)
    with open(tmp, "wb") as f:   # a fresh one is a publish in progress on another thread: left alone
        f.write(b"x")
    assert cache.expire(now=now) == 0 and os.path.exists(tmp)
    os.remove(tmp)
    assert pc_portrait.FACE_CACHE_TMP_MAX_AGE_S == 3600
    # the scan never indexes a temporary as a face
    with open(tmp, "wb") as f:
        f.write(b"x")
    rescanned = pc_portrait.FaceCache(str(tmp_path), cap_bytes=1 << 20)
    rescanned._scan()
    assert not any(".tmp-" in k for k in rescanned._sizes)
    os.remove(tmp)
    # the swap-in happens under the lock expiry holds, so an expiry pass and a publish never interleave
    cache._publish(key, b"1" * 10)
    held = []

    def replace_under_lock(src, dst):
        got = cache._lock.acquire(blocking=False)   # False: the publisher holds it
        held.append(got)
        if got:
            cache._lock.release()
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", replace_under_lock)
    cache._publish(key, b"2" * 10)
    monkeypatch.setattr(os, "replace", real_replace)
    assert held == [False] and cache.read(key) == b"2" * 10
    # a face whose file will not go (a reader holds it open on Windows, a transient error) stays TRACKED,
    # so a later pass retries instead of leaving a readable file nothing tracks (v4.1 §5)
    real_remove = os.remove
    refusals = []

    def refuse_once(p):
        if not refusals:
            refusals.append(p)
            raise PermissionError("in use")
        return real_remove(p)
    monkeypatch.setattr(os, "remove", refuse_once)
    assert cache.expire(max_age_s=0, now=time.time() + 10) == 0
    assert key in cache._sizes and key in cache._seen and cache.read(key) == b"2" * 10
    assert cache.expire(max_age_s=0, now=time.time() + 10) == 1
    assert key not in cache._sizes and key not in cache._seen and cache.read(key) is None
    monkeypatch.setattr(os, "remove", real_remove)
    # forget and capacity eviction keep the entry the same way
    cache._publish(key, b"3" * 10)
    refusals.clear()
    monkeypatch.setattr(os, "remove", refuse_once)
    cache.forget(key)
    assert key in cache._sizes and cache.read(key) == b"3" * 10
    cache.forget(key)
    assert key not in cache._sizes and cache.read(key) is None
    monkeypatch.setattr(os, "remove", real_remove)
    assert "_unlink_locked(key)" in inspect.getsource(pc_portrait.FaceCache._evict_locked)
    # a read that raced an expiry does not resurrect the index entry for a face the pass removed
    cache._publish(key, b"4" * 10)
    cache._sizes.pop(key), cache._atime.pop(key), cache._seen.pop(key)   # the pass ran between the file read and the touch
    assert cache.read(key) == b"4" * 10 and key not in cache._sizes and key not in cache._seen


# ── deploy wiring ──────────────────────────────────────────────────────

INDEXES = ("pc_portraits_unreferenced_since_idx", "players_pc_game_portrait_hash_idx",
           "players_pc_steam_portrait_hash_idx", "players_pc_steam_portrait_next_at_idx")


def test_migration_311_carries_every_column_and_index_the_code_plans_on():
    sql = (REPO / "backend" / "sql" / "311_player_cards_steam_portraits.sql").read_text(encoding="utf-8")
    assert sql.lstrip().startswith("--") and "\nBEGIN;\n" in sql and sql.rstrip().endswith("COMMIT;")
    for col in ("pc_steam_portrait_hash TEXT", "pc_steam_avatar_ref TEXT", "pc_steam_portrait_at TIMESTAMPTZ",
                "pc_steam_portrait_fail SMALLINT NOT NULL DEFAULT 0", "pc_steam_portrait_next_at TIMESTAMPTZ",
                "pc_steam_attempt BIGINT NOT NULL DEFAULT 0"):
        assert "ALTER TABLE players ADD COLUMN IF NOT EXISTS " + col in sql, col
    assert "ALTER TABLE pc_portraits ADD COLUMN IF NOT EXISTS unreferenced_since TIMESTAMPTZ" in sql
    for idx in INDEXES:
        assert "CREATE INDEX IF NOT EXISTS " + idx + "\n" in sql, idx
    assert "players_pc_steam_portrait_hash_fkey" in sql and "REFERENCES pc_portraits(hash)" in sql
    assert "ON players (pc_steam_portrait_next_at ASC NULLS FIRST)" in sql


def test_the_release_train_asserts_the_indexes_and_the_render_word_on_both_roles():
    """The SHIPPED Sept 12 entry, read out of BATCHES rather than sliced between two other batch names.

    The slice this used to take ran from `"sept12-gacha": {` to `"sept10-batch": {`, so a batch added between
    them landed inside it and every assertion here still passed over the wrong entry's text -- which is how
    this batch's expectations came to sit in a finished batch's entry in the first place."""
    rt, src = _release_train()
    batch = rt.BATCHES["sept12-gacha"]
    assert list(batch["expect_indexes"]) == list(INDEXES)
    assert _role_expect(batch, "pc_steam_sweep") == [
        {"key": "pc_steam_sweep", "primary": "running", "standby": "standby"}]
    assert _role_expect(batch, "pc_steam_render") == [
        {"key": "pc_steam_render", "primary": "ok", "standby": "ok"}]
    assert [q for _l, q, _m in batch["positive_sql"]] == [
        "SELECT count(*) FROM players WHERE pc_steam_portrait_hash IS NOT NULL;"]
    cols = [tuple(c) for c in batch["expect_columns"]]
    for col in ("pc_steam_avatar_ref", "pc_steam_portrait_at", "pc_steam_portrait_fail", "pc_steam_portrait_hash",
                "pc_steam_portrait_next_at"):
        assert ("players", col) in cols, col
    assert ("pc_portraits", "unreferenced_since") in cols and ("players", "pc_steam_attempt") in cols
    # pc/pool answers 200 on BOTH builds, so it is the smoke route and never the presence discriminator (r3)
    assert batch["new_routes"] == ["/api/v1/pc/packs"] and batch["smoke_route"] == "/api/v1/pc/pool"
    assert batch["rollback_sql"] == "rollback_311_player_cards_steam_portraits.sql"
    assert batch["i18n_sql"] == ["312_i18n_keys_sept12.sql", "313_seed_machine_translations_sept12.sql"]
    # the rollback prose is this batch's, and lives in this batch's entry: it used to be hardcoded in
    # phase_check, where any other batch that set `rollback_sql` would have had it printed over its own
    note = batch["rollback_note"]
    assert "resume_311_player_cards_steam_portraits.sql" in note and "parks every player" in note
    assert "{rollback_sql}" in note and note.count("{rollback_sql}") == 1
    # The region that matters is phase_check itself, where the prose USED to be hardcoded.
    # Slicing to the first BATCHES entry covered only the module preamble, so this could
    # never fail for the defect it names (#441/#342) -- proven by putting the hardcoded
    # print back and watching it stay green.
    _check_fn = src[src.index("def phase_check("):src.index("def phase_snapshot(")]
    assert "resume_311_player_cards_steam_portraits.sql" not in _check_fn
    assert "ROLLBACK_NOTE" in _check_fn   # it prints the SELECTED batch's note instead

    assert 'present = all(c not in ("404", "000", "") for c in codes)' in src
    # the smoke route is never borrowed from an empty route list (that raised IndexError)
    assert 'SMOKE_ROUTE = batch.get("smoke_route") or (NEW_ROUTES[0] if NEW_ROUTES else None)' in src
    assert "rollback rule" in src
    # the code phase is saved only on POSITIVE presence on both boxes and a routed answer from the edge (r4)
    phase = src[src.index("def phase_code("):src.index("def phase_i18n(")]
    assert "if not present:" in phase and "assert_edge_runs_new_code()" in phase
    assert phase.index("if not present:") < phase.index("assert_edge_runs_new_code()") \
        < phase.index('st["code_deployed"] = True')
    edge = src[src.index("def assert_edge_runs_new_code("):src.index("# ---", src.index("def assert_edge_runs_new_code("))]
    assert 'if edge in ("000", ""):' in edge and 'if edge == "404":' in edge   # the route batch's half
    assert "for key, want in edge_markers():" in edge                          # the no-route batch's half
    assert "294 must run" not in src   # the i18n gate names the selected batch's files, not a stale migration
    # the index probe is scoped by schema: the literal `public` it named until the automatic-log
    # hotfix's round 7, or the schema the train now derives from both database roles and passes in
    assert "def index_state(host):" in src and (
        "FROM pg_indexes WHERE schemaname = 'public'" in src
        or "FROM pg_indexes WHERE schemaname = %s AND " in src)
    assert src.count("index_state(host)") == 4   # its definition, the check, the schema postcondition, the verify
    assert 'EXPECT_INDEXES = list(batch.get("expect_indexes", []))' in src
    assert "len(idx) != len(EXPECT_INDEXES)" in src and "len(idx) == len(EXPECT_INDEXES)" in src


def test_the_pre_rollback_clear_withdraws_every_steam_picture_and_marks_the_blobs():
    """Pre-311 code neither clears the Steam unit on opt-out / None / deletion
    nor ages the derived-face cache, so once a picture is stored a bare code
    rollback is forbidden: this file runs first (r3)."""
    sql = (REPO / "backend" / "sql" / "rollback_311_player_cards_steam_portraits.sql").read_text(encoding="utf-8")
    assert sql.lstrip().startswith("--") and "\nBEGIN;\n" in sql and sql.rstrip().endswith("COMMIT;")
    body = " ".join(sql.split())
    # every row is PARKED a century out (no claim can start in any process, before or after the old code is
    # live) as well as withdrawn; a second run matches nothing (r4)
    assert ("UPDATE players SET pc_steam_portrait_hash = NULL, pc_steam_avatar_ref = NULL, pc_steam_portrait_fail = 0, "
            "pc_steam_portrait_next_at = now() + make_interval(years => 100), pc_steam_attempt = pc_steam_attempt + 1 "
            "WHERE pc_steam_portrait_next_at IS NULL OR pc_steam_portrait_next_at < now() + make_interval(years => 50)") in body
    assert "next_at = NULL" not in body
    # the claim's due predicate can never match a parked row, so no quiescence of the sweep is needed
    assert "p.pc_steam_portrait_next_at IS NULL" in MAIN_SRC and "p.pc_steam_portrait_next_at <= now()" in MAIN_SRC
    resume = (REPO / "backend" / "sql" / "resume_311_player_cards_steam_portraits.sql").read_text(encoding="utf-8")
    rbody = " ".join(resume.split())
    assert resume.lstrip().startswith("--") and "\nBEGIN;\n" in resume and resume.rstrip().endswith("COMMIT;")
    assert ("UPDATE players SET pc_steam_portrait_next_at = NULL "
            "WHERE pc_steam_portrait_next_at > now() + make_interval(years => 50);") in rbody
    assert "PARKED" in sql and "resume_311" in sql and "quiesc" in sql
    assert "UPDATE pc_portraits p SET unreferenced_since = now() WHERE p.unreferenced_since IS NULL AND NOT EXISTS" in body
    assert "q.pc_game_portrait_hash = p.hash OR q.pc_steam_portrait_hash = p.hash" in body
    for verb in ("DROP ", "DELETE ", "ALTER ", "TRUNCATE"):
        assert verb not in body, verb   # a clear, never a schema change or a blob delete: the janitor owns those
    assert "BEFORE deploying" in sql and "PC_FACE_CACHE_DIR" in sql and "BOTH" in sql


# ── v4.1 (r4): one player deadline, the committed heartbeat under a failing commit, the key off every log line ──

def test_one_player_deadline_bounds_the_wait_the_profile_and_the_picture(monkeypatch):
    # the token wait refuses to end past the deadline (v4.1 §3)
    slept = []

    async def sleep(s):
        slept.append(s)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    takes = [2.0, 2.0, 0.0, 0.0]
    monkeypatch.setattr(main._pc_steam_bucket, "take", lambda priority=False: takes.pop(0))
    now = time.monotonic()
    assert _run(main._pc_steam_wait(False, now + 1.0)) is False and slept == []
    assert _run(main._pc_steam_wait(False, now + 60.0)) is True and slept == [2.0]
    assert _run(main._pc_steam_wait(False)) is True
    # the XML path stamps each player's deadline and hands it to the profile request
    monkeypatch.setattr(main._pc_steam_breaker, "paused", lambda now=None: False)
    monkeypatch.setattr(main._pc_steam_breaker, "record", lambda *a, **k: None)
    monkeypatch.setitem(main._pc_steam_xml, "forced", True)
    kwargs = []
    monkeypatch.setattr(pc_steam, "http_get", lambda url, **kw: kwargs.append(kw) or b"<profile/>")

    async def wait(priority=False, deadline=None):
        return True
    monkeypatch.setattr(main, "_pc_steam_wait", wait)
    deadlines = {}
    before = time.monotonic()
    assert _run(main._pc_steam_fetch_refs([STEAM], deadlines=deadlines)) == {STEAM: None}
    assert set(deadlines) == {STEAM} and before + 11.0 < deadlines[STEAM] <= time.monotonic() + pc_steam.PLAYER_DEADLINE
    assert kwargs[-1]["deadline"] == deadlines[STEAM]
    # the picture request runs under the SAME deadline, and a wait that cannot meet it means no request
    monkeypatch.setattr(pc_steam, "http_get", lambda url, **kw: kwargs.append(kw) or b"")

    async def late(priority=False, deadline=None):
        return False
    monkeypatch.setattr(main, "_pc_steam_wait", late)
    n = len(kwargs)
    assert _run(main._pc_steam_fetch_picture("e" * 40, deadline=deadlines[STEAM])) == (False, None) and len(kwargs) == n
    monkeypatch.setattr(main, "_pc_steam_wait", wait)
    monkeypatch.setattr(pc_steam, "canonical_picture", lambda raw: b"png")
    stamped = deadlines[STEAM] - 3.0   # a value no fresh budget computed now can equal (the clock ticks every 15.6 ms on Windows)
    assert _run(main._pc_steam_fetch_picture("e" * 40, deadline=stamped)) == (True, b"png")
    assert kwargs[-1]["deadline"] == stamped
    # a keyed-path player (no stamped deadline) gets a fresh budget from the picture step itself
    before = time.monotonic()
    assert _run(main._pc_steam_fetch_picture("e" * 40)) == (True, b"png")
    assert before + 11.0 < kwargs[-1]["deadline"] <= time.monotonic() + pc_steam.PLAYER_DEADLINE
    # and the process loop threads the stamped deadline into the picture step
    seen = []

    async def refs(ids, priority=False, deadlines=None):
        deadlines[STEAM] = 12345.0
        return {STEAM: "e" * 40}

    async def picture(ref, priority=False, deadline=None):
        seen.append(deadline)
        return True, b"png"

    async def write(db, claimed, outcome, *, ref=None, png=None):
        return "applied"
    monkeypatch.setattr(main, "_pc_steam_fetch_refs", refs)
    monkeypatch.setattr(main, "_pc_steam_fetch_picture", picture)
    monkeypatch.setattr(main, "_pc_steam_write", write)
    monkeypatch.setattr(database, "async_session", lambda: Scripted({}))
    assert _run(main._pc_steam_process([_claimed()])) == {"applied": 1} and seen == [12345.0]


def test_a_verdict_whose_commit_fails_earns_no_heartbeat(monkeypatch):
    st = main._PC_STEAM_SWEEP_STATE
    monkeypatch.setitem(st, "clean_at", None)
    monkeypatch.setitem(st, "error", None)

    async def refs(ids, priority=False, deadlines=None):
        return {STEAM: DEFAULT}

    async def write(db, claimed, outcome, *, ref=None, png=None):
        return "plate"   # a committed word — but the commit below fails

    class _NoCommit(Scripted):
        async def commit(self):
            raise RuntimeError("connection lost")
    monkeypatch.setattr(main, "_pc_steam_fetch_refs", refs)
    monkeypatch.setattr(main, "_pc_steam_write", write)
    monkeypatch.setattr(database, "async_session", lambda: _NoCommit({}))
    assert _run(main._pc_steam_process([_claimed()])) == {"error": 1, "error_class": "RuntimeError"}
    assert st["clean_at"] is None


def test_the_api_key_never_reaches_a_log_line_or_an_error(monkeypatch, capsys):
    key = "SENTINEL-KEY-7f3a9c"
    monkeypatch.setenv("STEAM_WEB_API_KEY", key)
    monkeypatch.setitem(main._pc_steam_xml, "forced", False)
    monkeypatch.setitem(main._pc_steam_xml, "refusals", 0)
    monkeypatch.setattr(main._pc_steam_breaker, "paused", lambda now=None: False)
    monkeypatch.setattr(main._pc_steam_breaker, "record", lambda *a, **k: None)

    async def wait(priority=False, deadline=None):
        return True
    monkeypatch.setattr(main, "_pc_steam_wait", wait)
    urls = []

    def refused(url, **kw):
        urls.append(url)
        raise pc_steam.FetchError("http", 403)
    monkeypatch.setattr(pc_steam, "http_get", refused)
    assert _run(main._pc_steam_fetch_refs([STEAM])) is None
    monkeypatch.setattr(pc_steam, "http_get", lambda url, **kw: b"<html>")
    assert _run(main._pc_steam_fetch_refs([STEAM])) is None
    out = capsys.readouterr().out
    assert urls and key in urls[0]            # the key is on the wire, where it belongs
    assert key not in out and "api.steampowered.com" not in out and "[PC-STEAM]" in out
    assert key not in str(pc_steam.FetchError("http", 403)) and key not in str(pc_steam.FeedError("shape"))


def test_the_train_code_state_tells_present_absent_and_unknown_apart(monkeypatch):
    """A ROUTE batch's discriminator, driven through the real module: 404 is the old code, any other real
    status is the new one, and curl's 000 / empty is NEITHER -- an unknown state must never be recorded as a
    build. (The no-route batch's half of the same contract is the marker test above.)"""
    rt, _src = _release_train()
    rt.select_batch("sept12-gacha")
    assert rt.NEW_ROUTES == ["/api/v1/pc/packs"]
    route = rt.NEW_ROUTES[0]
    answers = {}
    monkeypatch.setattr(rt, "http_code", lambda host, path, **kw: answers[path])
    for new, expect in (("200", (True, True, False)), ("422", (True, True, False)), ("405", (True, True, False)),
                        ("404", (True, False, True)), ("000", (True, False, False)), ("", (True, False, False))):
        answers.update({rt.CONTROL_ROUTE: "200", route: new})
        ok, present, absent, readings = rt.code_state("h")
        assert (ok, present, absent) == expect, new
        assert readings == ["%s %s" % (new, route)], new   # the probe names the route it read
    answers.update({rt.CONTROL_ROUTE: "000", route: "200"})
    assert rt.code_state("h")[0] is False


def test_the_acquire_holds_every_party_and_demands_every_named_event():
    """r7 H1/H2 (2026-09-13): a lease naming events names their pullers and subjects too. Each of
    them is try-locked SHARED for the acquisition (the exclusive holders -- a deletion, a ban, an
    admin clear -- refuse it: 409, transient) and every named id must resolve now (404 event_gone,
    not transient), as the re-check demands again at the send."""
    src = inspect.getsource(main.internal_pc_lease)
    assert 'raise HTTPException(status_code=404, detail={"error": "event_gone"})' in src
    assert 'if {int(r["id"]) for r in named} != set(event_ids):' in src
    assert 'SELECT pg_try_advisory_xact_lock_shared(hashtext(CAST(:sid AS text)))' in src
    assert src.count('detail={"error": "subject_busy", "retry_after": 2}') == 2   # the subject's lock and a party's
    assert "if party == steam:" in src   # the subject already holds its own, exclusive
    assert (src.index('"print_not_of_subject"') < src.index("if event_ids:") < src.index('"event_gone"')
            < src.index("pg_try_advisory_xact_lock_shared") < src.index("INSERT INTO pc_delivery_leases"))
    assert "JOIN players pl ON pl.id = e.player_id" in src and "JOIN players su ON su.id = e.subject_player_id" in src


def test_the_writers_wait_for_the_lines_in_flight_naming_the_player(monkeypatch):
    """r7 H2 (2026-09-13): the deletion and the ban wait, under the identity lock, until no live
    lease names the player -- as its subject or as a party of a named event -- before they commit;
    the bot releases a lease right after Discord accepted the line, so the commit lands after the
    line is on Discord. Executed: a lease with 3 s left, then none -> two reads, one short sleep."""
    slept = []

    async def _sleep(secs):
        slept.append(secs)
    monkeypatch.setattr(main.asyncio, "sleep", _sleep)
    db = Scripted({"MAX(l.until)": [3, None]})
    waited = _run(main._pc_lease_drain(db, str(PID)))
    assert isinstance(waited, float) and waited >= 0.0
    assert db.count("MAX(l.until)") == 2 and slept == [0.25]
    sql = [q for q, _ in db.log if "MAX(l.until)" in q][0]
    # the naming predicate: the subject, or either party of a named event; the clock that advances
    assert "l.subject_id = CAST(:pid AS uuid)" in sql
    assert "e.id = ANY(l.event_ids)" in sql and "e.player_id = CAST(:pid AS uuid) OR e.subject_player_id = CAST(:pid AS uuid)" in sql
    assert sql.count("clock_timestamp()") == 2 and "now()" not in sql
    # no lease at all: one read, no sleep
    slept.clear()
    db2 = Scripted({"MAX(l.until)": [None]})
    _run(main._pc_lease_drain(db2, str(PID)))
    assert db2.count("MAX(l.until)") == 1 and slept == []
    # bounded by the lease's life: a lease the bot never releases ends the wait by expiry
    src = inspect.getsource(main._pc_lease_drain)
    assert "limit = float(_pcp.LEASE_SECONDS) + 5.0" in src and "time.monotonic() - started > limit" in src
    # ...executed (r12; oracle corrected r14): a lease that never leaves -- the naming read keeps answering 3 s. The
    # limit is checked after every await (a reading, a sleep), never inside one, so a reading starts only after a
    # check found the limit not yet passed, and the wait ends within the limit plus the longer of the one sleep
    # (0.25 s) and the one reading in flight when it passes -- not a hard 65 s. The clock is the event loop's own
    # (time.monotonic): a scripted reading or sleep carries the time, not the calls.
    clock = [0.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    limit = float(main._pcp.LEASE_SECONDS) + 5.0

    class _Ticking(Scripted):
        def __init__(self, script, reading):
            super().__init__(script)
            self.reading, self.starts = reading, []

        async def execute(self, statement, params=None):
            self.starts.append(clock[0])
            clock[0] += self.reading
            return await super().execute(statement, params)

    # (a) the limit passes DURING a reading: 30 s readings, sleeps that take no time -> the readings start at 0, 30
    # and 60 (none past the limit); the one in flight when the limit passes runs to 90 and ends the wait
    slept.clear()
    db3 = _Ticking({"MAX(l.until)": [3]}, 30.0)
    reads = int(limit // 30.0) + 1
    waited = _run(main._pc_lease_drain(db3, str(PID)))
    assert db3.starts == [30.0 * i for i in range(reads)] and max(db3.starts) <= limit
    assert limit < waited == 30.0 * reads <= limit + 30.0
    assert db3.count("MAX(l.until)") == reads and slept == [0.25] * (reads - 1)

    # (b) the limit passes DURING a sleep: readings of (limit - 0.875) / 4 s and sleeps that take their 0.25 s end
    # the fourth reading 0.125 s before the limit and its sleep 0.125 s past it -> the check after the sleep ends
    # the wait, and no fifth reading starts
    async def _ticking_sleep(secs):
        slept.append(secs)
        clock[0] += secs
    monkeypatch.setattr(main.asyncio, "sleep", _ticking_sleep)
    clock[0] = 0.0
    slept.clear()
    reading = (limit - 0.875) / 4.0
    db4 = _Ticking({"MAX(l.until)": [3]}, reading)
    waited = _run(main._pc_lease_drain(db4, str(PID)))
    assert len(db4.starts) == db4.count("MAX(l.until)") == 4 and max(db4.starts) <= limit
    assert slept == [0.25] * 4 and waited == limit + 0.125 <= limit + max(0.25, reading)


def test_the_drain_never_cancels_a_reading_because_a_cancelled_statement_loses_the_writers_transaction(monkeypatch):
    """r14 (2026-09-14): the wait's limit is enforced between awaits, never by cancelling the reading in flight.
    Executed on the drain first: a reading the database answers only after the limit has long passed, on the clock
    the event loop itself reads -- so a timeout, a deadline or a scheduled cancel armed on that clock falls due
    while the reading waits for its answer -- runs to its end, ends the wait, and receives no cancellation. Then
    the same as a rule on the drain's own body, its docstring aside. Then the reason, executed on the SQLAlchemy
    the requirements pin: a statement interrupted by a cancellation or a timeout invalidates its connection, and
    the transaction refuses its next statement -- the deletion or the ban that was waiting could never commit. An
    ordinary exception leaves the connection valid (the negative case)."""
    import ast
    import textwrap

    import sqlalchemy as sa
    clock = [0.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    limit = float(main._pcp.LEASE_SECONDS) + 5.0

    class _Late(Scripted):
        def __init__(self, script):
            super().__init__(script)
            self.started = self.answered = self.cancelled = 0

        async def execute(self, statement, params=None):
            self.started += 1
            clock[0] += 2.0 * limit      # every deadline armed on the loop's clock since the wait began is now due
            loop = asyncio.get_running_loop()
            answer = loop.create_future()

            def hop(n):                  # the database answers eight turns of the event loop later
                if answer.done():
                    return
                if n:
                    loop.call_soon(hop, n - 1)
                else:
                    answer.set_result(None)
            loop.call_soon(hop, 8)
            try:
                await answer
            except asyncio.CancelledError:
                self.cancelled += 1
                raise
            self.answered += 1
            return await super().execute(statement, params)

    async def drive(db):
        try:
            waited = await main._pc_lease_drain(db, str(PID))
        except (asyncio.CancelledError, TimeoutError) as exc:   # a cancellation reached the reading and escaped
            waited = type(exc).__name__
        return waited, db.started, db.answered, db.cancelled     # counted when the wait ENDS, not at the loop's close
    late = _Late({"MAX(l.until)": [3]})
    assert _run(drive(late)) == (2.0 * limit, 1, 1, 0)
    # the same, as a rule on the drain's own body (its docstring aside): no timeout, deadline, shield or cancel
    fn = ast.parse(textwrap.dedent(inspect.getsource(main._pc_lease_drain))).body[0]
    body = fn.body[1:] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) else fn.body
    names = {n.id for s in body for n in ast.walk(s) if isinstance(n, ast.Name)}
    names |= {n.attr for s in body for n in ast.walk(s) if isinstance(n, ast.Attribute)}
    assert {"execute", "sleep", "monotonic"} <= names, names   # the body read is the drain's own
    assert not names & {"wait_for", "wait", "timeout", "timeout_at", "shield", "cancel", "call_later", "call_at"}, names
    req = (REPO / "backend" / "api" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert "sqlalchemy[asyncio]==" + sa.__version__ in req, (
        "the local SQLAlchemy %s differs from the requirements pin: re-run this witness on the pinned version "
        "(a seat mismatch, not a drain regression)" % sa.__version__)
    for exc_type, lost in ((asyncio.CancelledError, True), (asyncio.TimeoutError, True), (RuntimeError, False)):
        eng = sa.create_engine("sqlite://")
        armed = [True]

        @sa.event.listens_for(eng, "do_execute")
        def _interrupt(cursor, statement, parameters, context):
            if armed[0] and "7" in statement:
                armed[0] = False
                raise exc_type()
        with eng.connect() as conn:
            assert conn.execute(sa.text("SELECT 1")).scalar() == 1   # the writer's transaction is open
            with pytest.raises(exc_type):
                conn.execute(sa.text("SELECT 7"))                  # the reading, interrupted inside the DBAPI call
            assert conn.invalidated is lost, exc_type
            if lost:
                with pytest.raises(sa.exc.PendingRollbackError):
                    conn.execute(sa.text("SELECT 1"))              # the writer's next statement: refused
            else:
                assert conn.execute(sa.text("SELECT 1")).scalar() == 1
        eng.dispose()


def test_the_writers_gate_admits_four_at_once_and_a_fifth_waits_holding_nothing():
    """r9 M1 (2026-09-13), executed on the real event loop: the admission gate of the writers that
    can wait for the Discord lines in flight -- one Semaphore of four slots per event loop, taken by
    the `_pc_writer_slot` dependency -- lets four requests hold a transaction at once; a fifth waits
    BEFORE its first statement (the dependency runs none: it holds no pool connection and no lock
    while it waits) and is admitted when any of the four ends, however it ends -- a return or an
    exception -- so no slot is ever lost."""
    async def scenario():
        gate = main._pc_writer_gate()
        assert gate is main._pc_writer_gate() and gate._value == main._PC_WRITER_SLOTS   # one per loop, all free
        running, peak, done = 0, 0, []

        async def writer(i):
            nonlocal running, peak
            slot = main._pc_writer_slot()
            await slot.__anext__()               # admitted: the request's first statement may run
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.02)
            running -= 1
            done.append(i)
            await slot.aclose()                  # the request ended: its slot is free again
        await asyncio.gather(*[writer(i) for i in range(6)])
        assert peak == 4 and sorted(done) == list(range(6)) and gate._value == 4
        held = [main._pc_writer_slot() for _ in range(4)]
        for h in held:
            await h.__anext__()
        fifth = main._pc_writer_slot()
        waiting = asyncio.ensure_future(fifth.__anext__())
        await asyncio.sleep(0.05)
        assert not waiting.done() and gate._value == 0    # the fifth waits...
        with pytest.raises(RuntimeError):
            await held[0].athrow(RuntimeError("the handler raised"))   # ...a request that ends by raising frees its slot...
        await asyncio.wait_for(waiting, 0.5)                             # ...and the fifth is admitted
        for h in (*held[1:], fifth):
            await h.aclose()
        assert gate._value == 4
    _run(scenario())
    assert main._PC_WRITER_SLOTS == 4
    src = inspect.getsource(main._pc_lease_drain)
    assert "_pc_drains_waiting" not in src and "pc_wait_busy" not in src   # the counted refusal is gone (r8 M1 -> r9 M1)


def test_every_route_that_can_wait_for_the_lines_in_flight_declares_the_gate():
    """r9 M1: the gated handlers are DERIVED from the app's routes -- every endpoint whose source
    reaches the wait (`_pc_lease_drain` itself, or `_apply_ban_core` / `_moderation_case_act`,
    which reach it) -- not listed: each declares `_slot=Depends(_pc_writer_slot)`, and they are
    exactly the deletion, the ban and the two moderation acts -- plus the unban, gated by name (r10
    M3): it takes the admin's identity lock a waiting ban may hold, so it must not queue for that lock
    holding a connection. On every gated route the slot is declared BEFORE the session (r10 M2): taken
    first, released last."""
    reach = ("_pc_lease_drain(", "_apply_ban_core(", "_moderation_case_act(")
    gated = {}
    for route in main.app.routes:
        fn = getattr(route, "endpoint", None)
        if fn is None or getattr(fn, "__module__", None) != main.__name__:
            continue
        if any(k in inspect.getsource(fn) for k in reach):
            gated[fn.__name__] = inspect.signature(fn).parameters.get("_slot")
    assert set(gated) == {"delete_player_data", "admin_ban", "admin_moderation_case_act", "internal_moderation_case_act"}, sorted(gated)
    gated["admin_unban"] = inspect.signature(main.admin_unban).parameters.get("_slot")   # the listed exception (r10 M3)
    for name, param in gated.items():
        assert param is not None and param.default.dependency is main._pc_writer_slot, name
        sig = inspect.signature(getattr(main, name))
        names = list(sig.parameters)
        assert names.index("_slot") < names.index("db"), name   # the slot before the session (r10 M2)
        assert sig.parameters["db"].default.dependency is main.get_db, name   # the session it outlives is the main pool's (r11)
    # one gate per process because the api runs ONE uvicorn worker: passed EXPLICITLY on the compose
    # command (it overrides the image's CMD), so WEB_CONCURRENCY -- uvicorn's default for the count when
    # the flag is absent -- cannot raise it either (r11 L7)
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
    cmd = [l for l in compose.splitlines() if "uvicorn" in l and "main:app" in l]
    assert len(cmd) == 1 and '"--workers", "1"' in cmd[0] and "gunicorn" not in compose
    dockerfile = (Path(__file__).resolve().parents[1] / "api" / "Dockerfile").read_text(encoding="utf-8")
    assert '"--workers", "1"' in dockerfile
    # ...and no environment entry in either file names the variable (the comments may)
    assert not any("WEB_CONCURRENCY" in l and not l.lstrip().startswith("#")
                   for l in (compose + "\n" + dockerfile).splitlines())


def test_the_slot_outlives_the_session_on_the_real_dependency_stack():
    """r10 M2 (2026-09-13), executed through FastAPI's dependency stack (TestClient): on a route that
    declares the slot BEFORE the session, the slot is held when the session opens, while the handler
    runs and raises, and STILL when the session closes -- FastAPI unwinds yield-dependencies in reverse
    declaration order, so the rollback, the locks and the connection are gone before a queued writer
    is admitted; a route declaring them the other way round shows the defect this guards: the slot
    is free again while its session is still open."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
    trace = []

    async def fake_db():
        trace.append(("open", main._pc_writer_gate()._value))
        try:
            yield "db"
        finally:
            trace.append(("close", main._pc_writer_gate()._value))

    app = FastAPI()

    @app.get("/gated")
    async def gated(_slot=Depends(main._pc_writer_slot), db=Depends(fake_db)):
        trace.append(("handler", main._pc_writer_gate()._value))
        raise HTTPException(status_code=409, detail="the handler ended by raising")

    @app.get("/reversed")
    async def reversed_(db=Depends(fake_db), _slot=Depends(main._pc_writer_slot)):
        trace.append(("handler", main._pc_writer_gate()._value))
        raise HTTPException(status_code=409, detail="the handler ended by raising")

    @app.get("/returns")
    async def returns(_slot=Depends(main._pc_writer_slot), db=Depends(fake_db)):
        trace.append(("handler", main._pc_writer_gate()._value))
        return {"ok": True}

    @app.get("/fails")
    async def fails(_slot=Depends(main._pc_writer_slot), db=Depends(fake_db)):
        trace.append(("handler", main._pc_writer_gate()._value))
        raise RuntimeError("the handler failed")

    async def fake_release_db():
        trace.append(("open", main._pc_release_gate()._value))
        try:
            yield "db"
        finally:
            trace.append(("close", main._pc_release_gate()._value))

    @app.get("/release")
    async def release(_slot=Depends(main._pc_release_slot), db=Depends(fake_release_db)):
        trace.append(("handler", main._pc_release_gate()._value))
        return {"released": 1}

    @app.get("/release_reversed")
    async def release_reversed(db=Depends(fake_release_db), _slot=Depends(main._pc_release_slot)):
        trace.append(("handler", main._pc_release_gate()._value))
        return {"released": 1}

    @app.get("/release_slow")
    async def release_slow(_slot=Depends(main._pc_release_slot), db=Depends(fake_release_db)):
        await asyncio.sleep(0.25)
        trace.append(("handler", main._pc_release_gate()._value))
        return {"released": 1}

    @app.get("/release_409")
    async def release_409(_slot=Depends(main._pc_release_slot), db=Depends(fake_release_db)):
        trace.append(("handler", main._pc_release_gate()._value))
        raise HTTPException(status_code=409, detail="the handler ended by raising")

    @app.get("/release_fails")
    async def release_fails(_slot=Depends(main._pc_release_slot), db=Depends(fake_release_db)):
        trace.append(("handler", main._pc_release_gate()._value))
        raise RuntimeError("the handler failed")

    def settle():
        for _ in range(100):
            if any(k == "close" for k, _v in trace):
                return
            time.sleep(0.02)

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/gated").status_code == 409
        settle()
        assert trace == [("open", 3), ("handler", 3), ("close", 3)], trace
        trace.clear()
        assert client.get("/returns").status_code == 200                    # a normal return (r11)
        settle()
        assert trace == [("open", 3), ("handler", 3), ("close", 3)], trace
        trace.clear()
        assert client.get("/fails").status_code == 500                      # an arbitrary handler exception (r11)
        settle()
        assert trace == [("open", 3), ("handler", 3), ("close", 3)], trace
        trace.clear()
        assert client.get("/release").status_code == 200                    # the reserved pool's slot (r12): 5 permits
        settle()
        assert trace == [("open", 4), ("handler", 4), ("close", 4)], trace
        trace.clear()
        assert client.get("/release_reversed").status_code == 200
        settle()
        assert trace == [("open", 5), ("handler", 4), ("close", 5)], trace   # the defect, on the reversed order
        trace.clear()
        assert client.get("/release_409").status_code == 409                # an HTTPException (r13)
        settle()
        assert trace == [("open", 4), ("handler", 4), ("close", 4)], trace
        trace.clear()
        assert client.get("/release_fails").status_code == 500              # an arbitrary handler exception (r13)
        settle()
        assert trace == [("open", 4), ("handler", 4), ("close", 4)], trace
        trace.clear()
        assert client.get("/release").status_code == 200                    # every reserved slot was returned
        settle()
        assert trace == [("open", 4), ("handler", 4), ("close", 4)], trace
        trace.clear()
        assert client.get("/reversed").status_code == 409
        settle()
        assert trace == [("open", 4), ("handler", 3), ("close", 4)], trace   # the defect, on the reversed order
        trace.clear()
        assert client.get("/gated").status_code == 409                       # every slot was returned
        settle()
        assert trace == [("open", 3), ("handler", 3), ("close", 3)], trace

    # at the ASGI level (r12), on a fresh loop -- so a fresh gate of five permits: the app is called the way a
    # server calls it, with a receive channel of this test's choosing
    async def call(path, receive_msgs):
        msgs = list(receive_msgs)
        sent = []

        async def receive():
            return msgs.pop(0) if len(msgs) > 1 else msgs[0]

        async def send(message):
            sent.append(message)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
                 "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
                 "headers": [], "client": ("testclient", 50000), "server": ("testserver", 80)}
        await app(scope, receive, send)
        return next(m["status"] for m in sent if m["type"] == "http.response.start")

    async def burst(n):
        return await asyncio.gather(*[call("/release_slow", [{"type": "http.request", "body": b"", "more_body": False},
                                                             {"type": "http.disconnect"}]) for _ in range(n)])
    # seven at once against five permits: the sixth and the seventh open no session until a first one closed --
    # they wait at the slot holding nothing, never at the pool
    trace.clear()
    assert asyncio.run(burst(7)) == [200] * 7
    opens = [i for i, (k, _v) in enumerate(trace) if k == "open"]
    closes = [i for i, (k, _v) in enumerate(trace) if k == "close"]
    assert [trace[i][1] for i in opens[:5]] == [4, 3, 2, 1, 0] and len(opens) == len(closes) == 7, trace
    assert opens[5] > closes[0] and opens[6] > closes[0], trace
    # a client that disconnected before its handler ran: nothing stops the handler -- it runs to its end, the
    # session closes, the slot is returned after it (a client timeout, a disconnect or a bot restart changes
    # nothing on this side: the bound is held by the process that holds the connections)
    trace.clear()
    assert asyncio.run(call("/release_slow", [{"type": "http.disconnect"}])) == 200
    assert trace == [("open", 4), ("handler", 4), ("close", 4)], trace
    # a cancelled handler (a shutdown, D4's option d if it were ever taken): the same stack unwinds -- the session
    # closes with the slot still held, the slot is released after it; nothing of the handler's ran
    async def cancelled():
        task = asyncio.create_task(call("/release_slow", [{"type": "http.disconnect"}]))
        for _ in range(200):
            if any(k == "open" for k, _v in trace):
                break
            await asyncio.sleep(0.005)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return "cancelled"
        return "finished"
    trace.clear()
    assert asyncio.run(cancelled()) == "cancelled"
    assert trace == [("open", 4), ("close", 4)], trace
    assert main._pc_release_gates == {} or all(g._value == main._PC_RELEASE_SLOTS for g in main._pc_release_gates.values())


def test_the_lease_release_and_the_ack_run_on_the_reserved_pool():
    """r10 M3 (2026-09-13), on the engines and derived from the app's routes: the two requests that END a
    writer's wait -- the delivery-lease release and the events ack -- take their session from a RESERVED
    pool (its own engine, 3 + 2) that no other request can occupy, so however many requests hold or queue
    for the main pool's connections, the release always finds one; they are exactly the two routes on it,
    and both delete leases."""
    assert database.release_engine is not database.engine
    assert database.release_engine.url == database.engine.url
    assert database.release_engine.pool.size() == 3 and database.release_engine.pool._max_overflow == 2
    assert database.engine.pool.size() == 20 and database.engine.pool._max_overflow == 10
    assert main.get_release_db is database.get_release_db
    assert database.release_session.kw["bind"] is database.release_engine
    assert database.async_session.kw["bind"] is database.engine
    on_reserved = {}
    for route in main.app.routes:
        fn = getattr(route, "endpoint", None)
        if fn is None or getattr(fn, "__module__", None) != main.__name__:
            continue
        for p in inspect.signature(fn).parameters.values():
            if getattr(p.default, "dependency", None) is database.get_release_db:
                on_reserved[fn.__name__] = fn
    assert set(on_reserved) == {"internal_pc_lease_release", "internal_pc_events_ack"}, sorted(on_reserved)
    for fn in on_reserved.values():
        assert "DELETE FROM pc_delivery_leases" in inspect.getsource(fn)
    src = inspect.getsource(database.get_release_db)
    assert "release_session()" in src and "await session.close()" in src
    assert "release_session = async_sessionmaker(release_engine" in inspect.getsource(database)
    # the api admits exactly as many of these requests as the pool holds (r12): one slot per connection, the
    # slot declared BEFORE the reserved session on both routes and on no other route; the bot has no gate of
    # its own any more (r11's client-side gate returned its permit on a timeout while the handler ran on)
    size = database.release_engine.pool.size() + database.release_engine.pool._max_overflow
    assert main._PC_RELEASE_SLOTS == size == database.RELEASE_POOL_SIZE + database.RELEASE_POOL_OVERFLOW == 5
    admitted = {}
    for route in main.app.routes:
        fn = getattr(route, "endpoint", None)
        if fn is None or getattr(fn, "__module__", None) != main.__name__:
            continue
        for p in inspect.signature(fn).parameters.values():
            if getattr(p.default, "dependency", None) is main._pc_release_slot:
                admitted[fn.__name__] = fn
    assert set(admitted) == set(on_reserved), (sorted(admitted), sorted(on_reserved))
    for name, fn in on_reserved.items():
        names = list(inspect.signature(fn).parameters)
        assert names.index("_slot") < names.index("db"), name
    assert "async with _pc_release_gate():" in inspect.getsource(main._pc_release_slot)
    bot_src = (Path(__file__).resolve().parents[1] / "discord_bot.py").read_text(encoding="utf-8")
    assert "_pc_release_gate" not in bot_src and "_PC_RELEASE_SLOTS" not in bot_src


def test_the_gates_forget_a_closed_loop_when_the_next_loop_takes_its_own():
    """r13 (2026-09-13), executed: a gate is bound to the loop that first waited on it (one entry per loop); a
    closed loop's entry is pruned when a later loop takes its own gate -- the tests run one loop per test, and a
    process that re-created its loop must not keep a dead gate. Both gates: the reserved pool's and the ban
    family's."""
    for gates, gate in ((main._pc_release_gates, main._pc_release_gate), (main._pc_writer_gates, main._pc_writer_gate)):
        gates.clear()

        async def touch():
            loop = asyncio.get_running_loop()
            assert gate() is gate() is gates[loop] and isinstance(gates[loop], asyncio.Semaphore)
            return loop, gates[loop]
        first, first_gate = asyncio.run(touch())
        assert first.is_closed() and list(gates) == [first]            # closed, still listed until the next loop
        second, second_gate = asyncio.run(touch())
        assert second is not first and list(gates) == [second], gates   # the closed loop's entry is gone
        # r14: each loop gets its OWN semaphore -- one object shared by every loop and merely re-keyed passes the two
        # lines above, and binds to the first loop that waits on it
        assert second_gate is not first_gate and gates[second] is second_gate
        gates.clear()


def test_every_line_this_train_prints_goes_through_one_redaction_door(monkeypatch, capsys,
                                                                     tmp_path):
    """R7-H2 (R6-H2, R5-H1): the door was there, and it was asking the wrong question twice over.

    A fix that renamed the call sites would have closed the lines it touched and left the CLASS open:
    the next `print(` anybody writes is a bypass (#432). So the door IS the name -- the module defines
    `print` and shadows the builtin -- and there is nothing for an author to remember. That much held.

    What did not hold is WHAT it substitutes. It called `identifier()` on every line, which re-reads
    the environment and re-opens the seat file, so a seat edited or made unreadable after a command had
    been composed left the door substituting today's value into a line built from yesterday's -- the
    one identifier the transcript was supposed to lose is exactly the one it then kept. And it
    recognised host labels by LAYOUT: a bracket, a recap row, an ad-hoc header. Ansible has more line
    shapes than any list will hold, and `included: playbooks/x.yml for <host>` -- free text, no
    brackets -- travelled intact.

    The seat is a CAPTURE of the first read, and the labels are LEARNED from the lines that announce
    them and then removed from everything, layout and all."""
    import json
    import re as _re
    import subprocess as _sp
    rt, src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)

    # (a) ONE door, and it is the name every call site already uses. Asserted
    # of the SOURCE, because what this is about is the call sites that have not
    # been written yet.
    assert len(_re.findall(r"^def print\(", src, _re.M)) == 1, "one door, defined once"
    assert len(_re.findall(r"^def redact\(", src, _re.M)) == 1
    # The captured builtin is reachable in exactly two places -- the door, and
    # the last-resort excepthook, which writes to STDERR where the door's own
    # `print` does not go. Every one of those calls carries a literal or a
    # redacted value; a third function naming it would be a way out with no
    # rule at all. The COUNT is not the invariant -- a fix that adds a line to
    # the excepthook would redden a count and change nothing -- the invariant
    # is WHO may call it and WHAT the call carries.
    owners = set()
    for m in _re.finditer(r"\b_emit\(", src):
        at = m.start()
        owner = src.rfind("\ndef ", 0, at)
        owners.add(src[owner + 5:src.index("(", owner + 5)])
        call = src[at:src.index("\n", src.index(")", at))]
        # A literal, a redacted value, or one of the four fixed lines the
        # bootstrap defines -- each of which is asserted below to BE a literal
        # with nothing substituted into it. Those four exist because the door
        # is not always reachable: an import that fails, a redaction that
        # raises and a print that raises all have to say something, and what
        # they say has to be a constant.
        assert ('"' in call or "redact(" in call or "_LINE" in call), call
    assert owners == {"print", "_excepthook"}, owners
    fixed = _re.findall(r"^([A-Z_]+_LINE) = ", src, _re.M)
    assert len(fixed) == 4, fixed
    for named in fixed:
        at = src.index("\n%s = " % named) + 1
        end = _re.search(r"\n(?=[^\s])", src[at + len(named):])
        statement = src[at:at + len(named) + (end.start() if end else 0)]
        assert '"' in statement, statement
        for built in ("%", " + ", ".format", "redact(", "identifier("):
            assert built not in statement, (named, built)
    # ...and no other way out of the process
    for bypass in ("sys.stdout.write", "import builtins", "builtins.print",
                   "os.write(", "print_function"):
        assert bypass not in src, bypass
    # The door NEVER re-reads the seat: that is the whole of the fix, and it is
    # a property of the function's body, not of the line that happens to be in
    # front of it today.
    body = src[src.index("def redact("):src.index("def print(")]
    assert "identifier(" not in body, body
    assert "_SEAT_SNAPSHOT" in body, body

    # (b) the REAL path, not a stub standing in for it: a fake subprocess hands
    # back a play tail carrying seat values and the responding host, and the
    # train's own run() echoes the command it composed. The seat is read here
    # because that is what a run does -- the commands are composed from it --
    # and the capture of that read is what every line below is redacted
    # against.
    rt.seat_values()
    rt.identifier("origin_url")
    tail = "\n".join([
        # One seat value per line, each from a different key, so what is
        # asserted below is that the door answers for the KEY and not for one
        # remembered string.
        "PLAY [%s] ***" % SEAT_PVE_GROUP,
        "TASK [%s : deploy] ***" % SEAT_CONTROLLER,
        # ...and one seat value in FREE TEXT, where no layout rule reaches it
        # and the only thing that can remove it is knowing the value
        "skipping: no hosts matched %s" % SEAT_PRIMARY_LIMIT,
        "ok: [%s]" % SEAT_PLAY_HOST,
        'changed: [%s] => {"cmd": "git fetch %s"}' % (SEAT_PLAY_HOST, ORIGIN_URL),
        "fatal: [%s]: FAILED! => {}" % SEAT_PLAY_HOST,
        # the line the round before had no shape for: the label is at the end
        # of a sentence, in no brackets, beside an ordinary path
        "included: playbooks/deploy.yml for %s" % SEAT_PLAY_HOST,
        # ...and one whose label is announced NOWHERE ELSE in this output, so
        # the free-text line is the only place it can be learned from. Without
        # it the label is not in the set at all and no substitution can reach
        # it, whatever the rest of the door does.
        "included: playbooks/roles/health.yml for %s" % SEAT_SIBLING_HOST,
    ])
    recap = ("PLAY RECAP ***\n%s                  : ok=9    changed=3    unreachable=0    "
             "failed=0" % SEAT_PLAY_HOST)

    class _Done(object):
        returncode = 0
        stderr = ""

        def __init__(self, out):
            self.stdout = out

    def _ran(*a, **k):
        # The answer has to carry the token THIS invocation minted, so the
        # fake reads it out of the argv it was handed (#342): a constant would
        # make the binding unobservable.
        argv = a[0] if a else k.get("args")
        joined = " ".join(argv) if isinstance(argv, (list, tuple)) else str(argv)
        found = _re.search(r"-e scr_nonce=([0-9a-f]{32})", joined)
        nonce = found.group(1) if found else NONCE
        # Each selector answers as its own box (R9-M2 probes both before either
        # play), and a play composed with the identity gate carries the gate's
        # PASSED line for this invocation's token -- the box IS the attested one.
        standby = ("--limit %s " % SEAT_STANDBY_LIMIT) in joined + " "
        middle = tail
        if "scr_expect_id=" in joined:
            middle = '        "SCR-GATE %s PASSED"\n%s' % (nonce, tail)
        return _Done(_attested_out(nonce=nonce,
                                   addr=rt.STANDBY if standby else rt.PRIMARY,
                                   box_id=STANDBY_BOX_ID if standby else PRIMARY_BOX_ID,
                                   sha=MERGE_FULL, middle=middle, recap=recap,
                                   order=_order_sent(joined)))

    monkeypatch.setattr(rt, "subprocess", SimpleNamespace(
        run=_ran, TimeoutExpired=_sp.TimeoutExpired,
        SubprocessError=_sp.SubprocessError))
    monkeypatch.setattr(rt, "assert_control", lambda host: None)
    _attested(monkeypatch, rt)
    rt.attest_deploy_selectors()
    capsys.readouterr()
    # Both probes, both gated plays and both after-play readings run through
    # the REAL attested-operation code on this fake, and every line of it goes
    # through the door.
    rt._deploy_both(MERGE_FULL)
    out = capsys.readouterr().out

    # not one seat value, and not the host that answered, anywhere in it
    for value in (SEAT_CONTROLLER, SEAT_PVE_GROUP, SEAT_PRIMARY_LIMIT, SEAT_STANDBY_LIMIT,
                  ORIGIN_URL, SEAT_PLAY_HOST, SEAT_SIBLING_HOST):
        assert value not in out, (value, out)
    # ...and what stands in their place says WHICH key it was, so the
    # transcript is still readable
    for token in ("<primary_limit>", "<origin_url>"):
        assert token in out, (token, out)
    # The controller and the pve group came through a BRACKETED label, which
    # the layout rule turns into the host token before the key can be named.
    # That is the conservative direction -- the value is gone either way -- and
    # it is why the substitution itself is asserted of the door rather than
    # inferred from a transcript that may or may not carry a given shape.
    assert rt.redact("fetched by %s for %s at %s"
                     % (SEAT_CONTROLLER, SEAT_PVE_GROUP, SEAT_STANDBY_LIMIT)) == \
        "fetched by <controller> for <pve_group> at <standby_limit>"
    assert "ok: [%s]" % rt.HOST_TOKEN in out, out
    # ...and the one line this train composes itself, which carries the
    # controller and the selector by construction and prints neither
    assert "ssh -o BatchMode=yes %s" % rt.HOST_TOKEN in out, out
    # The recap is not inside the play's own output -- it follows the whole
    # playbook -- so it is not among the lines printed above. It goes through
    # the same door anyway, which is asked of the door directly.
    assert rt.redact("%s                  : ok=9    changed=3    unreachable=0    failed=0"
                     % SEAT_PLAY_HOST).startswith(rt.HOST_TOKEN)
    # the free-text line: the label is gone and the sentence is still a sentence
    assert "included: playbooks/deploy.yml for %s" % rt.HOST_TOKEN in out, out
    # ...and so is the one whose label that line was the only announcement of
    assert "included: playbooks/roles/health.yml for %s" % rt.HOST_TOKEN in out, out
    assert SEAT_SIBLING_HOST in rt._LEARNED_HOSTS, rt._LEARNED_HOSTS
    # the command echo -- a line built from the seat, not from any output -- is
    # in there and it is redacted
    assert "$ ssh" in out, out

    # (b2) a label LEARNED from an earlier play and then used bare in a later
    # line, with no ansible syntax around it at all
    assert SEAT_PLAY_HOST in rt._LEARNED_HOSTS, rt._LEARNED_HOSTS
    bare = "  the wrapper on %s answered rc=0 (see %s:/var/log)" % (SEAT_PLAY_HOST,
                                                                   SEAT_PLAY_HOST)
    assert SEAT_PLAY_HOST not in rt.redact(bare), rt.redact(bare)
    assert rt.redact(bare).count(rt.HOST_TOKEN) == 2, rt.redact(bare)

    # (c) the same door covers a REFUSAL, which is where the wrapper's own
    # output is quoted back
    assert SEAT_CONTROLLER not in rt.redact("ssh %s uptime" % SEAT_CONTROLLER)
    assert SEAT_PLAY_HOST not in rt.redact("ok: [%s]" % SEAT_PLAY_HOST)

    # (d) a WORKSTATION PATH is a local identifier too: an exception message
    # carrying the absolute path of this script names the account it runs under
    said = rt.redact('Traceback: File "%s", line 12, in run'
                     % os.path.join(rt.REPO, "scripts", "deploy", "release_train.py"))
    assert rt.REPO not in said, said
    assert "<path>" in said, said
    assert "D:\\a-dir\\a-file" not in rt.redact("D:\\a-dir\\a-file\\x.log")
    assert "<path>" in rt.redact("D:\\a-dir\\a-file\\x.log")
    # ...and the home-directory shape, written so the fixture itself is not a
    # path of the class it stands for
    assert "<path>" in rt.redact("/%s/a-person/x.log" % "home")

    # (e) the seat file changes on disk AFTER the command was composed. The
    # capture is what every line was built from, so the line in front of the
    # door still loses its value -- and the value that replaced it, which
    # nothing composed anything from, is nowhere either.
    rt2, _src2 = _release_train()
    conf = tmp_path / "seat.json"
    for env in rt2.IDENTIFIERS.values():
        monkeypatch.delenv(env, raising=False)
    conf.write_text(json.dumps({"controller": "composed-controller",
                                "pve_group": "composed-group",
                                "primary_limit": "composed-primary",
                                "standby_limit": "composed-standby",
                                "play_dir": "/srv/composed-plays",
                                "origin_url": ORIGIN_URL}), encoding="utf-8")
    monkeypatch.setattr(rt2, "TRAIN_CONF", str(conf))
    composed = rt2.seat_values()                       # the command is composed here
    assert composed["controller"] == "composed-controller"
    conf.write_text(json.dumps({"controller": "moved-controller",
                                "pve_group": "moved-group",
                                "primary_limit": "moved-primary",
                                "standby_limit": "moved-standby",
                                "play_dir": "/srv/moved-plays",
                                "origin_url": ORIGIN_URL}), encoding="utf-8")
    line = "    $ ssh -o BatchMode=yes composed-controller 'ansible composed-primary ...'"
    said = rt2.redact(line)
    assert "composed-controller" not in said, said      # what the command carried
    assert "composed-primary" not in said, said
    assert "moved-controller" not in said, said         # and what replaced it
    assert "<controller>" in said and "<primary_limit>" in said, said
    # ...and a seat file that has become unreadable does not reopen the door
    conf.unlink()
    said = rt2.redact(line)
    assert "composed-controller" not in said and "<controller>" in said, said

    # (e2) a machine fingerprint is a persistent machine identifier, and it
    # reaches this door inside output this train did not compose. A 64-hex
    # run is tokenised whether or not this process has ever seen it.
    fp = "e" * 64
    said = rt2.redact("the box reports %s as its boot identity" % fp)
    assert fp not in said, said
    assert rt2.FINGERPRINT_TOKEN in said, said
    # inert twin: a shorter hex run is an object id, and object ids are what
    # this train's transcripts exist to carry
    sha = "a" * 40
    assert sha in rt2.redact("deployed %s" % sha)

    # (f) inert twin: a line that carries none of them is printed unchanged --
    # including the addresses this train declares, which are what make a
    # transcript say WHICH box each reading came from
    plain = "  OK 192.168.72.199: the new build is live (alias absent) (control 200)"
    assert rt2.redact(plain) == plain


def test_no_exception_leaves_this_train_except_through_the_door(monkeypatch, capsys):
    """R7-H3: the door shadowed `print`, and an exception does not print -- it raises.

    `run()` let `subprocess.TimeoutExpired` out as itself. That exception carries `.cmd`, which is the
    composed command: the ssh destination and the `--limit` verbatim. `main()` caught only `Fail`, and
    the `check` path was not wrapped at all, so the interpreter printed the exception to stderr with a
    traceback whose every frame is the absolute path of this file. None of that goes near a shadowed
    `print`, so the one door had an exception-shaped hole beside it.

    Every way out of the subprocess layer is now a redacted `Fail`; both paths of `main()` share one
    handler; and a `sys.excepthook` is installed as the last resort, which prints ONE redacted line and
    discards the traceback -- a frame IS a path."""
    import re as _re
    import subprocess as _sp
    rt, src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    rt.seat_values()                 # what the commands below were composed from
    raw = ["ssh", "-o", "BatchMode=yes", SEAT_CONTROLLER,
           "cd ~/zap && ansible-playbook x.yml --limit %s" % SEAT_PRIMARY_LIMIT]

    # (a) a timeout, whose own args carry the whole composed command
    def _timeout(*a, **k):
        raise _sp.TimeoutExpired(cmd=raw, timeout=900)

    monkeypatch.setattr(rt, "subprocess", SimpleNamespace(
        run=_timeout, TimeoutExpired=_sp.TimeoutExpired, SubprocessError=_sp.SubprocessError))
    with pytest.raises(rt.Fail) as exc:
        rt.run(raw, quiet=True)
    said = str(exc.value)
    assert "did not answer within" in said, said
    for value in (SEAT_CONTROLLER, SEAT_PRIMARY_LIMIT):
        assert value not in said, (value, said)
    assert rt.REPO not in said, said

    # (b) an OSError from the spawn, whose filename is a local path. The
    # message carries the TYPE and nothing else: an OSError's `filename` is the
    # path it could not run, which is exactly the string this door exists to
    # keep out of a transcript.
    def _oserror(*a, **k):
        raise OSError(2, "No such file or directory",
                      os.path.join(rt.REPO, "scripts", "deploy", "release_train.py"))

    monkeypatch.setattr(rt, "subprocess", SimpleNamespace(
        run=_oserror, TimeoutExpired=_sp.TimeoutExpired, SubprocessError=_sp.SubprocessError))
    with pytest.raises(rt.Fail) as exc:
        rt.run(raw, quiet=True)
    said = str(exc.value)
    assert "could not be run at all (FileNotFoundError)" in said, said
    assert rt.REPO not in said and "release_train.py" not in said, said

    # (c) an exception of an UNEXPECTED type out of a phase: main() turns it
    # into one redacted line and a non-zero exit, with no traceback frame
    def _boom(*a, **k):
        raise RuntimeError("while running %s" % " ".join(raw))

    monkeypatch.setattr(rt, "_main", _boom)
    capsys.readouterr()
    prior = sys.excepthook
    try:
        rc = rt.main()
    finally:
        sys.excepthook = prior
    out = capsys.readouterr().out
    assert rc == 1, rc
    assert "unexpected RuntimeError" in out, out
    for value in (SEAT_CONTROLLER, SEAT_PRIMARY_LIMIT):
        assert value not in out, (value, out)
    assert "Traceback" not in out and ", line " not in out, out
    assert rt.REPO not in out, out

    # ...and the CHECK path is inside that same handler, which is the half that
    # was not wrapped at all
    assert len(_re.findall(r"^def main\(", src, _re.M)) == 1
    handler = src[src.index("\ndef main("):src.index("\ndef _main(")]
    assert "except BaseException" in handler, handler
    assert "return _main()" in handler, handler
    assert 'if args.action == "check"' in src[src.index("\ndef _main("):], "check is inside _main"
    assert "install_excepthook()" in handler, handler

    # (d) the last resort: the excepthook itself. One line, redacted, and the
    # traceback dropped -- asserted by CALLING it, never by reading it.
    err = io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = err
    try:
        try:
            raise ValueError("ssh %s failed; see %s"
                             % (SEAT_CONTROLLER, os.path.join(rt.REPO, "x.log")))
        except ValueError:
            rt._excepthook(*sys.exc_info())
    finally:
        sys.stderr = real_stderr
    printed = err.getvalue()
    assert "unexpected ValueError" in printed, printed
    assert SEAT_CONTROLLER not in printed, printed
    assert rt.REPO not in printed and "<path>" in printed, printed
    assert "Traceback" not in printed and "release_train.py" not in printed, printed
    assert len([l for l in printed.splitlines() if l.strip()]) == 2, printed

    # (e) the inert twin of (a) and (b): an ordinary command still answers
    class _Done(object):
        returncode = 0
        stdout = "fine"
        stderr = ""

    monkeypatch.setattr(rt, "subprocess", SimpleNamespace(
        run=lambda *a, **k: _Done(), TimeoutExpired=_sp.TimeoutExpired,
        SubprocessError=_sp.SubprocessError))
    assert rt.run(raw, quiet=True) == "fine"


# ── round 9: the method change, and the findings the round-8 review raised ──
#
# The pin no longer carries a transcript of a live run. What it carries is a
# schema-rendered document per artifact, and the whole point of the schema is
# that a free string cannot be represented in it: an identifier can only travel
# in a review bundle inside text somebody wrote, and there is no text. The door
# and the census stay as defence in depth -- for the terminal, and for the
# human-written files -- and the findings below are still fixed by number.


def _cli(monkeypatch, rt, *args):
    """Run the train's own entry point the way a shell does.

    `_main` parses `sys.argv` -- it takes no argument list -- so a test that
    wants the WHOLE path, parser included, has to hand it one the same way."""
    monkeypatch.setattr(rt.sys, "argv", ["release_train.py"] + list(args))
    return rt._main()


def test_the_door_exists_before_anything_that_can_fail_and_has_no_path_around_it(monkeypatch,
                                                                                 capsys):
    """R8-H3: three ways out of this process printed text the door had never seen.

    The excepthook was installed by `main()`, so anything raised before that -- an import of a module
    this seat does not have, a syntax error in a helper, a failure while the argument parser is still
    running -- reached the interpreter's default, which prints a traceback whose every frame is the
    absolute path of this file. `argparse` writes its usage and its errors with `_print_message`,
    straight to a file object, never through `print`, and what it writes is routinely the argument the
    operator mistyped. And a `SystemExit` whose code is a STRING is printed verbatim by the
    interpreter on the way out.

    A bootstrap block at the top of the file installs a last-resort hook BEFORE the first import that
    can fail; the parser's one output method goes through the door; a string exit code becomes a
    redacted line and a numeric status; and a failure inside the door itself prints one fixed
    constant and never the partially substituted text."""
    rt, src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)

    # (a) the bootstrap is BEFORE the imports that can fail, in the file, and
    # the four fixed lines are defined before it
    head = src.index("sys.excepthook = _bootstrap_excepthook")
    assert src.index("import sys") < head
    for line in ("BOOTSTRAP_LINE = ", "INTERRUPTED_LINE = ", "UNREDACTABLE_LINE = ",
                 "UNPRINTABLE_LINE = "):
        assert src.index(line) < head, line
    for later in ("import argparse", "import json", "import subprocess",
                  "from datetime import"):
        assert src.index(later) > head, later

    # (b) the parser: every diagnostic through the door, and a numeric status
    rt.seat_values()          # the door substitutes what was CAPTURED (R8-H2)
    rt.identifier("origin_url")
    parser = rt._Parser(prog="release train")
    parser.add_argument("--batch")
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        parser.error("unrecognized arguments: %s" % SEAT_CONTROLLER)
    said = capsys.readouterr().out
    assert exc.value.code == 2, exc.value.code
    assert not isinstance(exc.value.code, str), "a string code is printed raw by the interpreter"
    assert SEAT_CONTROLLER not in said, said
    assert "<controller>" in said, said
    # ...and the same for usage and for --help, which reach the same method
    capsys.readouterr()
    parser._print_message("usage: release train [--batch %s]" % SEAT_PVE_GROUP)
    said = capsys.readouterr().out
    assert SEAT_PVE_GROUP not in said and "<pve_group>" in said, said
    # ...and it is the ONE method the class overrides, which is what makes
    # usage, help and errors all go the same way
    assert "def _print_message(self, message, file=None):" in src
    assert src.count("class _Parser(argparse.ArgumentParser):") == 1
    assert "_Parser(" in src[src.index("def _main("):], "the train builds ITS parser from it"

    # (c) a SystemExit carrying a STRING becomes a redacted line and a status
    monkeypatch.setattr(rt, "_main", lambda: (_ for _ in ()).throw(
        SystemExit("unrecognized arguments: %s" % SEAT_CONTROLLER)))
    capsys.readouterr()
    assert rt.main() == 2
    said = capsys.readouterr().out
    assert SEAT_CONTROLLER not in said, said
    assert "<controller>" in said, said

    # (d) a failure INSIDE the door prints one fixed constant and never the
    # partially substituted text. The round before returned `out` as it stood
    # when the exception was raised, so a failure in the FIRST rule returned
    # the line unchanged -- the guarantee was untrue in exactly the state it
    # exists for.
    boom = {"n": 0}

    def _explode(*a, **k):
        boom["n"] += 1
        raise RuntimeError("inside the door")

    monkeypatch.setattr(rt, "_LABEL_IN_BRACKETS", SimpleNamespace(sub=_explode))
    said = rt.redact("ok: [%s] on %s" % (SEAT_PLAY_HOST, SEAT_CONTROLLER))
    assert boom["n"] == 1, "the arm must actually have raised inside the door"
    assert said == rt.UNREDACTABLE_LINE, said
    assert SEAT_PLAY_HOST not in said and SEAT_CONTROLLER not in said, said
    monkeypatch.undo()
    _seat(monkeypatch, rt)

    # (e) ...and a failure inside PRINT itself, where even the fixed line
    # cannot be composed
    real_emit = rt._emit

    def _emit_once(*a, **k):
        if a and a[0] != rt.UNPRINTABLE_LINE:
            raise UnicodeEncodeError("utf-8", "x", 0, 1, "no")
        return real_emit(*a, **k)

    monkeypatch.setattr(rt, "_emit", _emit_once)
    capsys.readouterr()
    rt.print("ok: [%s]" % SEAT_PLAY_HOST)
    said = capsys.readouterr().out
    assert said.strip() == rt.UNPRINTABLE_LINE, said
    monkeypatch.setattr(rt, "_emit", real_emit)

    # (f) KeyboardInterrupt, on both hooks, is one fixed word and no traceback
    errs = []
    monkeypatch.setattr(rt.sys, "stderr", SimpleNamespace(write=errs.append))
    rt._bootstrap_excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    assert errs == [rt.INTERRUPTED_LINE + "\n"], errs
    errs[:] = []
    rt._bootstrap_excepthook(ImportError, ImportError("no module named %s" % SEAT_CONTROLLER),
                             None)
    assert errs == [rt.BOOTSTRAP_LINE + "\n"], errs
    assert SEAT_CONTROLLER not in "".join(errs), errs


def test_a_dry_run_records_no_state_and_a_resumed_sha_is_authenticated(monkeypatch, capsys,
                                                                       tmp_path):
    """R8-L5 and R8-L4: `plan --from verify` wrote the word `verified` into the state file.

    Two things were wrong with that at once. A dry run whose own banner promises that no mutating step
    will execute wrote a file; and what it wrote was `verified` about a rollout it had deliberately not
    asked the exact-SHA question of, because the flag that skips the probe is the same flag that says
    this is a plan.

    And the sha it verified against was checked for its SHAPE. A 40-character string that resolves is
    not the merge this batch was reviewed on, and this phase is reached directly by `--only verify` and
    by `--from verify`, where nothing else has authenticated anything. The persisted sha goes through
    the same door a fresh merge does, and then the reviewed tip has to be reachable from it."""
    import json
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    state = tmp_path / "train-state.json"
    state.write_text(json.dumps({"code_sha": MERGE_FULL}), encoding="utf-8")
    monkeypatch.setattr(rt, "STATE_PATH", str(state))
    import hashlib as _h
    was = _h.sha256(state.read_bytes()).hexdigest()

    # (a) the dry arm: nothing probed, nothing recorded, and the file is
    # BYTE-IDENTICAL afterwards. A dry verify still READS the boxes; those
    # reads are stubbed, because a unit test asks no machine anything (round
    # 10 found this arm making the control-route GETs for real).
    for name, stub in (("assert_control", lambda host: None),
                       ("assert_health_keys", lambda hosts: None),
                       ("assert_positive_signals", lambda: None),
                       ("http_code", lambda host, path, **kw: "200"),
                       ("code_state", lambda host: (True, True, False, ["alias absent"])),
                       ("assert_edge_runs_new_code", lambda: None)):
        monkeypatch.setattr(rt, name, stub)
    rt.recording(True)
    probed = []
    monkeypatch.setattr(rt, "assert_boxes_are_on", lambda sha, values=None: probed.append(sha))
    capsys.readouterr()
    st = {"code_sha": MERGE_FULL, "bot_skipped": rt.BOT_SKIP_REASON}
    rt.phase_verify(SimpleNamespace(go=False), st)
    out = capsys.readouterr().out
    assert probed == [], "a plan asks no box anything"
    assert "verified" not in st, st
    assert _h.sha256(state.read_bytes()).hexdigest() == was, "a dry run wrote the state file"
    assert "[dry run] nothing is recorded" in out, out
    assert rt.recorded("verify")["state_written"] == "NO", rt.recorded("verify")
    assert rt.recorded("verify")["verified"] == "NO", rt.recorded("verify")

    # (b) the sha door on the resumed path: shape, then identity, then
    # reachability -- and each of the three refuses on its own
    _attested(monkeypatch, rt)
    for stub, says in (
            (lambda raw, how: (_ for _ in ()).throw(rt.Fail("not a 40-character object id")),
             "not a 40-character object id"),):
        monkeypatch.setattr(rt, "authenticated_code_sha", stub)
        with pytest.raises(rt.Fail) as exc:
            rt.phase_verify(SimpleNamespace(go=True),
                            {"code_sha": MERGE_FULL, "bot_skipped": rt.BOT_SKIP_REASON})
        assert says in str(exc.value), str(exc.value)
    monkeypatch.setattr(rt, "authenticated_code_sha", lambda raw, how: raw)
    monkeypatch.setattr(rt, "_commit_sha", lambda rev, **kw: REVIEWED_FULL)
    monkeypatch.setattr(rt, "_git_auth_succeeds", lambda args, **kw: False)
    for stub in (lambda host: (True, True, False, ["alias absent"]),):
        monkeypatch.setattr(rt, "code_state", stub)
    for name, stub in (("http_code", lambda host, path, **kw: "200"),
                       ("assert_control", lambda host: None),
                       ("assert_health_keys", lambda hosts: None),
                       ("assert_positive_signals", lambda: None),
                       ("assert_edge_runs_new_code", lambda: None),
                       ("schema_state", lambda host: ([], [])),
                       ("index_state", lambda host: []),
                       ("_bot_witness", lambda **kw: None),
                       ("save_state", lambda st_: None)):
        monkeypatch.setattr(rt, name, stub)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_verify(SimpleNamespace(go=True), {"code_sha": MERGE_FULL,
                                                   "bot_skipped": rt.BOT_SKIP_REASON})
    assert "does not contain this batch's reviewed tip" in str(exc.value), str(exc.value)
    assert probed == [], "the rollout is not verified, so no box is asked"

    # (c) inert twin: authenticated, reachable, and the phase asks both boxes
    monkeypatch.setattr(rt, "_git_auth_succeeds", lambda args, **kw: True)
    st = {"code_sha": MERGE_FULL, "bot_skipped": rt.BOT_SKIP_REASON}
    rt.phase_verify(SimpleNamespace(go=True), st)
    assert probed == [MERGE_FULL], probed
    assert st["verified"] is True
    assert rt.recorded("verify")["code_sha_provenance"] == "MATCH"
    assert rt.recorded("verify")["state_written"] == "YES"
    rt.recording(False)


def test_the_binding_question_is_asked_before_phase_zero_can_mint_anything(monkeypatch, capsys):
    """R8-L6: the stale-main refusal sat inside the code phase, four phases after the first mutation.

    A full `run --go` reaches phase 4 only after phase 0 has attested a selector, possibly minted a
    live snapshot on a container and written the state file. So a run that was ALREADY KNOWN to be
    bound to the wrong main mutated a container and a file before the refusal that exists to stop it.
    The question costs two rev-parses and no network at all.

    It is asked once, before the phase loop, and the answer is kept: a phase that needs it reads what
    was answered rather than asking again. On a DRY run it does not stop anything -- nothing can be
    mutated without `--go` -- because a plan that stopped here would describe fewer phases than the
    operator asked for, including the OLD-build negative control phase 4 carries for a batch with no
    migration."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    rt.recording(True)
    sequence = []
    monkeypatch.setattr(rt, "load_state", lambda: {})
    monkeypatch.setattr(rt, "save_state", lambda st_: sequence.append("save"))
    monkeypatch.setattr(rt, "PHASES", [
        ("snapshot", lambda args, st: sequence.append("snapshot")),
        ("code", lambda args, st: sequence.append("code"))])

    # (a) the reddening arm: the binding is wrong, and the run stops BEFORE the
    # first phase -- nothing attested, nothing minted, nothing saved
    def _refuses(st):
        sequence.append("binding")
        raise rt.Fail("main is at %s, but this batch was reviewed against %s"
                      % (OTHER_FULL, MAIN_FULL))

    monkeypatch.setattr(rt, "assert_reviewed_provenance", _refuses)
    capsys.readouterr()
    rc = _cli(monkeypatch, rt, "--batch", ABSENT_BATCH, "run", "--go")
    out = capsys.readouterr().out
    assert rc == 1, out
    assert sequence == ["binding"], sequence
    assert "NOTHING has run" in out, out
    assert out.index("BINDING") < len(out), out
    assert rt.recorded("plan")["provenance"] == "REFUSED", rt.recorded("plan")

    # (b) ...and on a DRY run the same refusal is REPORTED and the plan carries
    # on, so the phases below it are still described
    sequence[:] = []
    capsys.readouterr()
    rc = _cli(monkeypatch, rt, "--batch", ABSENT_BATCH, "plan")
    out = capsys.readouterr().out
    assert rc == 0, out
    assert sequence == ["binding", "snapshot", "code"], sequence
    assert "[plan only] a run would REFUSE HERE" in out, out
    assert "before phase 0 attests a selector" in out, out

    # (c) inert twin: a binding that answers -- asked once, before the phases,
    # and the answer is what the code phase reads
    sequence[:] = []
    monkeypatch.setattr(rt, "assert_reviewed_provenance",
                        lambda st: sequence.append("binding") or MERGE_FULL)
    rc = _cli(monkeypatch, rt, "--batch", ABSENT_BATCH, "run", "--go")
    assert rc == 0, sequence
    assert sequence == ["binding", "snapshot", "code"], sequence
    assert rt._PROVENANCE["authenticated"] == MERGE_FULL, rt._PROVENANCE
    assert rt.recorded("plan")["provenance"] == "MATCH"
    assert rt.recorded("plan")["outcome"] == "COMPLETED"
    rt.recording(False)


# ── the module's network guard ─────────────────────────────────────────


def test_r10_no_unit_test_spawns_a_network_program(_no_network_program):
    """The guard every test in this module runs under, run against itself.

    A curl is refused and RECORDED (the record is what fails a test at
    teardown); any other program still spawns."""
    import subprocess
    import sys as _sys
    with pytest.raises(OSError):
        subprocess.run(["curl", "--version"], capture_output=True)
    assert _no_network_program == ["curl"], _no_network_program
    _no_network_program.clear()        # the arm above is this guard's own control
    done = subprocess.run([_sys.executable, "--version"], capture_output=True)
    assert done.returncode == 0 and _no_network_program == []

