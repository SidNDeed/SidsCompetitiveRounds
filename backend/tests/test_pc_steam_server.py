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
    # pack open, its two completed-open replays (a repeated pack id, a repeated nonce), pack result, the /card preview
    assert MAIN_SRC.count("await _pc_steam_prime(") == 5
    opened = inspect.getsource(main.pc_open_pack)
    replay = 'await _pc_steam_prime(await _pc_pack_subjects(db, str(row["id"])))'
    assert opened.count(replay) == 2
    at = 0
    for _ in range(2):   # each replay primes under the done check and BEFORE the answer is built (v4 §5)
        i = opened.index(replay, at)
        assert opened.rfind('if row["status"] == "done":', 0, i) > opened.rfind("await _pc_pack_answer(", 0, i)
        assert 0 < opened.find("await _pc_pack_answer(", i) < opened.find('if row["status"] == "done":', i)
        at = i + 1


# ── the sweep's words ──────────────────────────────────────────────────

def test_the_sweep_word_is_earned_by_completed_work(monkeypatch):
    st = main._PC_STEAM_SWEEP_STATE
    monkeypatch.setitem(st, "clean_at", None)
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
    assert dict(rt.edge_markers()) == {"pc_fold": fold, "pc_pool_rule": main._PC_POOL_RULE}

    # the fold marker, exactly once, on both roles, in THIS batch's entry
    assert _role_expect(entry, "pc_fold") == [{"key": "pc_fold", "primary": fold, "standby": fold}]
    # the merged pool rule is the second, independent signal for the same
    # question (#438): with no new route a stale standby would otherwise answer
    # exactly like a fresh one (the bug #266 shape)
    assert _role_expect(entry, "pc_pool_rule") == [
        {"key": "pc_pool_rule", "primary": main._PC_POOL_RULE, "standby": main._PC_POOL_RULE}]

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
    fold, rule = main.PC_FOLD, main._PC_POOL_RULE
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


# ── the ABSENT json marker: a batch whose change is a key GOING AWAY ──────

ABSENT_BATCH = "bug392-merge"   # the first batch of that shape, and of the no-migration shape


def _absent_marker(rt):
    """The single json marker of the ABSENT batch, bound."""
    rt.select_batch(ABSENT_BATCH)
    assert len(rt.JSON_MARKERS) == 1, rt.JSON_MARKERS
    return rt.JSON_MARKERS[0]


def test_an_ABSENT_json_marker_reads_a_missing_key_as_the_NEW_build(monkeypatch):
    """The reading runs backwards for this batch, and the control is what makes it a reading.

    Every marker before this one said "the key at this value is the new build", so an absent key meant OLD. This
    batch's whole server change is that the new build STOPS emitting `involuntary_leave_cause`, so the key gone is
    NEW -- and absence on its own is satisfied by a wrong path, an error body, or a box serving nothing at all.
    Hence the control: `ffa_involuntary_cause`, true on BOTH builds. A reading where the control does not hold is
    neither build, so the train stops instead of calling an unreadable box new."""
    rt, _src = _release_train()
    m = _absent_marker(rt)
    assert m["key"] == "involuntary_leave_cause" and m["expect"] is rt.ABSENT
    assert m["control_key"] == "ffa_involuntary_cause" and m["control_expect"] is True
    monkeypatch.setattr(rt, "http_code", lambda host, path, **kw: "200")

    new_build = {"version": "1.40.3", "min_version": "1.40.2", "ffa_involuntary_cause": True}
    old_build = dict(new_build, involuntary_leave_cause=True)
    inert = {"version": "1.40.3", "ffa_involuntary_cause": False}   # control at the wrong value
    no_control = {"version": "1.40.3"}                              # right-looking body, control gone
    for body, want, why in (
            (new_build, (True, False), "alias gone, control true: the NEW build"),
            (old_build, (False, True), "alias present at any value: the OLD build"),
            (dict(old_build, involuntary_leave_cause=False), (False, True),
             "present-but-false is still present, so still OLD"),
            (inert, (False, False), "control false: not a verdict about the build"),
            (no_control, (False, False), "control absent: the body is not the one we asked for"),
            ({}, (False, False), "did not parse: unknown, exactly as for a forward marker"),
    ):
        monkeypatch.setattr(rt, "route_json", lambda host, path, _b=body: _b)
        for host in (rt.PRIMARY, rt.STANDBY):
            ok, present, absent, readings = rt.code_state(host)
            assert ok, host
            assert (present, absent) == want, (host, body, why)
            assert not (present and absent), why          # nothing is ever both
            if not body:
                assert readings == ["%s did not answer JSON" % m["path"]], readings
                continue
            # the reading names what it saw: "(absent)" or the value, for the
            # key AND for the control, so a failure says which half failed
            got = body.get(m["key"], "(absent)")
            ctl = body.get(m["control_key"], "(absent)")
            assert readings == ["%s %s=%s (want (absent); control %s=%s want True)"
                                % (m["path"], m["key"],
                                   "(absent)" if got == "(absent)" else repr(got),
                                   m["control_key"],
                                   "(absent)" if ctl == "(absent)" else repr(ctl))], readings

    # ...and the same semantics through the edge, which is the path players traverse
    monkeypatch.setattr(rt, "route_json", lambda host, path, _b=new_build: _b)
    rt.assert_edge_runs_new_code()                     # the only reading that passes
    for body in (old_build, inert, no_control, {}):
        monkeypatch.setattr(rt, "route_json", lambda host, path, _b=body: _b)
        with pytest.raises(rt.Fail):
            rt.assert_edge_runs_new_code()


def test_the_train_refuses_an_ABSENT_marker_that_carries_no_control():
    """An ABSENT marker without a control is a check that cannot fail, and the table refuses it (#342).

    The older rejection -- `expect: None` -- has to survive alongside it: None is what a body carries for a key set
    to null, so it could never be the way to say "not there"."""
    rt, _src = _release_train()
    m = _absent_marker(rt)
    entry = dict(rt.BATCHES[ABSENT_BATCH])

    def refuse(marker, why, says):
        # The refusal is named, not merely raised: with any Fail accepted, a
        # check removed from the table could stay green on a DIFFERENT
        # refusal further down, and its control would redden nothing (B10).
        entry["json_markers"] = [marker]
        rt.BATCHES["_broken"] = entry
        try:
            with pytest.raises(rt.Fail) as exc:
                rt.select_batch("_broken")
            assert says in str(exc.value), (why, str(exc.value))
        finally:
            del rt.BATCHES["_broken"]

    no_key = {k: v for k, v in m.items() if k != "control_key"}
    no_val = {k: v for k, v in m.items() if k != "control_expect"}
    refuse(no_key, "absence with no control field named", "carries no `control_key`")
    refuse(no_val, "a control field with no value to hold it to",
           "carries no `control_expect`")
    refuse(dict(m, control_key=m["key"]), "the marker as its own control: gone AND present",
           "as its own control")
    refuse(dict(m, control_expect=rt.ABSENT),
           "a control that is itself an absence proves nothing",
           "the ABSENT sentinel as a value")
    refuse(dict(m, expect=None),
           "None, which an absent key would satisfy -- the older rule stands",
           "expects None")
    refuse(dict(m, why=""), "no `why`: a probe nobody wrote down is not reviewable",
           "carries no `why`")
    refuse(dict(m, path=rt.CONTROL_ROUTE), "read on the control route, so a down box reads as old",
           "is read on the control route")

    # and the marker as it actually ships is accepted
    rt.select_batch(ABSENT_BATCH)


def test_a_batch_with_no_migration_skips_three_phases_and_moves_the_negative_control(monkeypatch, capsys):
    """A batch carrying no sql at all is legal, and every skip is printed with its reason and recorded.

    The #477 two-SHA order exists so a new api never boots against an old schema; with no schema moving there is no
    first SHA. The phases that went with it carried something that is NOT optional, though: the precursor deploy was
    the one moment the train SAW its discriminator answer `old`. Without that reading the code phase's postcondition
    is a check that has never been seen to fail. So the reading moves to the START of the code phase, before the
    merge and before any deploy, and it stops the train when it does not hold."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    assert rt.ALL_SQL == [] and rt.SCHEMA_SQL == rt.I18N_SQL == rt.BACKFILL_SQL == []
    assert rt.PRECURSOR_MESSAGE is None          # optional for this shape, and absent
    assert rt.BOT_SKIP_REASON and not rt.DEPLOY_BOT

    args, st = SimpleNamespace(go=False), {}
    for phase, key in ((rt.phase_precursor, "precursor_skipped"),
                       (rt.phase_deploy_precursor, "deploy_precursor_skipped"),
                       (rt.phase_schema, "schema_skipped")):
        phase(args, st)
        out = capsys.readouterr().out
        assert "SKIPPED" in out and rt.NO_MIGRATION_REASON in out, (phase, out)
        assert st[key] == rt.NO_MIGRATION_REASON        # recorded, not merely printed
    assert "precursor_sha" not in st and "schema_done" not in st

    # The provenance binding is this phase's own gate and has its own test; it
    # is replaced here by a recorder so this one stays about the skipped
    # phases and the relocated control -- and so that the ORDER can be read:
    # the binding is consulted before the merge it guards.
    provenance = []
    monkeypatch.setattr(rt, "assert_reviewed_provenance",
                        lambda st_: provenance.append("checked") or print("  provenance: checked"))
    snapshotted = _snap()
    _snapshot_is_listed(monkeypatch, rt)
    # The universal clean gate is the first thing this phase runs now, so `run`
    # has to answer it even in the plan arm; everything else reaching the stub
    # is a command the plan should not have issued.
    monkeypatch.setattr(rt, "run", lambda cmd, **kw:
                        "" if list(cmd)[:3] == ["git", "status", "--porcelain"]
                        else _raise_no_command(cmd))

    # the plan says where the control went, and names the reading it will take
    rt.phase_code(args, st)
    out = capsys.readouterr().out
    assert "negative control" in out, out
    assert rt.PRIMARY in out and rt.STANDBY in out and "OLD" in out, out
    # ...and it is stated BEFORE the merge it guards, not after it
    assert out.index("negative control") < out.index("git merge --no-ff --no-commit"), out
    assert "git merge --no-ff --no-commit %s" % rt.BRANCH in out, out
    # the plan says the snapshot is a prerequisite, and the binding was read
    # before the merge line rather than after it
    assert "no snapshot binds to this train yet" in out, out
    assert provenance == ["checked"] and out.index("provenance") < out.index("git merge"), out

    # under --go the control RUNS, on both boxes, before anything is merged --
    # and it stops the train on every reading that is not OLD.
    #
    # `run` is replaced FIRST and throughout. It raises Fail on any non-zero
    # command, so a phase that failed to stop here would reach `git checkout
    # main`, fail it (main is checked out in another worktree) and satisfy
    # pytest.raises(Fail) with the wrong exception -- a check that cannot fail
    # (#342). A command reaching this stub is a Sentinel, never a Fail, and the
    # message of each stop is read so the three are not one error found three
    # ways.
    class Sentinel(Exception):
        pass

    def no_commands(cmd, **kw):
        # ...except the universal clean gate, which opens the phase and is
        # answered CLEAN here: this test is about the relocated control, and a
        # phase that stopped at the gate would never reach it.
        if list(cmd)[:3] == ["git", "status", "--porcelain"]:
            return ""
        raise Sentinel(" ".join(cmd) if isinstance(cmd, list) else cmd)

    args = SimpleNamespace(go=True)
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    monkeypatch.setattr(rt, "run", no_commands)
    for verdict, fragment in (((True, True, False, ["new"]), "it already runs the new build"),
                              ((True, False, False, ["neither"]), "the state is UNKNOWN"),
                              ((False, False, True, ["down"]), "is not 200 before the code deploy")):
        monkeypatch.setattr(rt, "code_state", lambda host, _v=verdict: _v)
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(args, dict(snapshotted))
        assert fragment in str(exc.value), (verdict, str(exc.value))

    # the OLD reading passes it and is RECORDED; the sentinel proves nothing
    # ran before that point -- the first git command is where it lands
    monkeypatch.setattr(rt, "code_state", lambda host: (True, False, True, ["alias present"]))
    st = dict(snapshotted)
    with pytest.raises(Sentinel) as exc:
        rt.phase_code(args, st)
    # nothing before the merge but the clean read and the control
    assert str(exc.value).startswith("git checkout main")
    assert st["pre_code_old_build"] is True

    # the bot phase skips with its reason, and the verify phase no longer reads
    # that skip as "the bot phase never ran" -- which stopped every skip_bot
    # train one phase from the end
    st = {}
    rt.phase_bot(SimpleNamespace(go=True), st)
    assert st["bot_deployed"] is False and st["bot_skipped"] == rt.BOT_SKIP_REASON
    assert rt.BOT_SKIP_REASON in capsys.readouterr().out
    monkeypatch.setattr(rt, "assert_control", lambda host: None)
    monkeypatch.setattr(rt, "assert_health_keys", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_positive_signals", lambda: None)
    monkeypatch.setattr(rt, "http_code", lambda host, path, **kw: "200")
    monkeypatch.setattr(rt, "code_state", lambda host: (True, True, False, ["alias absent"]))
    monkeypatch.setattr(rt, "assert_edge_runs_new_code", lambda: None)
    monkeypatch.setattr(rt, "schema_state", lambda host: ([], []))
    monkeypatch.setattr(rt, "index_state", lambda host: [])
    witnessed = []
    monkeypatch.setattr(rt, "_bot_witness", lambda **kw: witnessed.append(kw))
    # The phase now ends by asking both boxes which commit their deployed clone
    # is on, so the state has to carry one; that question has its own test with
    # its own reddening arm and is recorded rather than probed here.
    asked = []
    st["code_sha"] = MERGE_FULL
    _code_sha_authenticated(monkeypatch, rt)
    monkeypatch.setattr(rt, "assert_boxes_are_on", lambda sha, values=None: asked.append(sha))
    rt.phase_verify(SimpleNamespace(go=True), st)
    assert st["verified"] is True
    assert asked == [MERGE_FULL], asked
    assert witnessed == []      # a bot this train never touched is not witnessed
    assert "NOT witnessed" in capsys.readouterr().out


def test_the_train_refuses_a_precursor_subject_that_describes_no_commit():
    """The files-only subject and the sql files stand or fall together (#302)."""
    rt, _src = _release_train()
    for broken, why in (({"precursor_message": "Migration 999 precursor (files only)"},
                         "a subject for a commit the precursor phase will skip"),
                        ({"schema_sql": ["324_ffa_departure_cause.sql"]},
                         "sql with no subject to commit it under")):
        entry = dict(rt.BATCHES[ABSENT_BATCH])
        entry.update(broken)
        rt.BATCHES["_broken"] = entry
        try:
            with pytest.raises(rt.Fail):
                rt.select_batch("_broken")
        finally:
            del rt.BATCHES["_broken"]
        assert why


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


def _with_rc(fn, rc=0):
    """A `rt.run` stub written before R9-M1, answering `(text, rc)` when the train asks for a status."""
    def _run(cmd, **kwargs):
        text = fn(cmd, **kwargs)
        return (text, rc) if kwargs.get("with_rc") else text
    return _run


def _nonce_of(cmd):
    """The token the train minted for this invocation, read out of the command it sent."""
    import re as _re
    joined = " ".join(cmd) if isinstance(cmd, list) else cmd
    found = _re.search(r"-e scr_nonce=([0-9a-f]{32})", joined)
    return found.group(1) if found else NONCE


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


def _listing_raw(body, rc=0, endpoint=None, box_id=SEAT_BOX_ID, agree=True,
                 fingerprints=None, identity=..., responder=SEAT_PLAY_HOST):
    """A listing whose BODY is given verbatim -- for the arms about parsing it."""
    if identity is ...:
        identity = (endpoint if endpoint is not None else OTHER_TOKEN, box_id)
    fps = fingerprints if fingerprints is not None else (
        [identity[1], identity[1]] if identity else [])
    return {"raw": body, "rc": rc, "identity": identity, "responder": responder,
            "agree": agree, "fingerprints": list(fps)}


def _code_sha_authenticated(monkeypatch, rt):
    """Let a phase past the persisted-SHA door without a git command.

    The door is a git question with its own test and its own reddening arms
    (R8-L4/L5): the recorded id is an object this repository holds, it is a
    merge of the two bound shas in that order, it carries their tree, and the
    reviewed tip is reachable from it. Stubbed here for the same reason
    `_attested` is -- a test about what phase 7 asks the BOXES is not a second
    test of how it decides the recorded id is the reviewed merge."""
    monkeypatch.setattr(rt, "authenticated_code_sha", lambda raw, how: raw)
    monkeypatch.setattr(rt, "_git_auth_succeeds", lambda args, **kw: True)
    monkeypatch.setattr(rt, "_commit_sha", lambda rev, **kw: rev)


def _fresh_process(rt, *keys):
    """Forget what this process captured of the seat, as a NEW process would.

    The seat is read once per process and answered from that first reading ever
    after (R8-H2), so a test that moves an environment variable mid-test is
    describing a second RUN, not a second question inside one run. Nothing in
    the train may do this -- `_read_live_seat` refuses a key it has already
    captured -- which is why the test does it explicitly and says so."""
    for key in keys:
        rt._SEAT_SNAPSHOT.pop(key, None)


def _play_out(name, host=SEAT_PLAY_HOST, failed=0):
    """The imported snapshot play's OWN output, between the two facts sections."""
    return ("TASK [take the snapshot] ***\nchanged: [%s]\n%s"
            % (host, ("snapshot: %s" % name) if name else ""))


def _attesting_deploy(rt, calls, out="changed=2 failed=0", boxes=None, shas=None,
                      probes=None, gate=True, gated=None, probed=None):
    """A `run_attested` stub answering the way one deploy invocation does.

    Which box answers is decided by the CALL ORDER, not by the selector string,
    so a test that moves a selector value still gets the primary's box first.
    The endpoint comes back as the CLASS the train now records (R8-H5).

    R9-M2. `_deploy_both` now probes BOTH boxes read-only before either play,
    and each play carries the identity gate. A probe (no play) is answered from
    `probes` -- by default the primary's box, then the standby's, in that
    order, repeating -- and is recorded in `probed`, never in `calls`, so
    `calls` stays what it always was: the plays that RAN. With `gate` (the
    default) a play whose box is not the pair it was `expect`ed to be does what
    the box's own gate does: the process ends before the imported play,
    recorded in `gated`, never in `calls`. `gate=False` turns that off, which
    is how an arm reaches the after-play comparison behind it."""
    boxes = boxes or [(rt.PRIMARY, PRIMARY_BOX_ID), (rt.STANDBY, STANDBY_BOX_ID)]
    probes = probes or [(rt.PRIMARY, PRIMARY_BOX_ID), (rt.STANDBY, STANDBY_BOX_ID)]
    count = {"probes": 0}

    def _answer(addr, box_id, ref):
        facts = _facts_body(addr=addr, box_id=box_id, sha=ref)
        token = rt.endpoint_class(addr)
        return ({(rt.FACTS_MARK, rt.BEFORE): facts, (rt.FACTS_MARK, rt.AFTER): facts,
                 "fingerprints": [box_id, box_id], "endpoints": [token, token], "rc": 0},
                (token, box_id))

    def _stub(limit, values=None, play=None, extra=None, listing=False, st=None,
              status_keys=(), who="", timeout=1800, expect=None):
        if play is None:
            addr, box_id = probes[count["probes"] % len(probes)]
            count["probes"] += 1
            if probed is not None:
                probed.append(limit)
            sections, identity = _answer(addr, box_id, OTHER_FULL)
            return "", sections, identity, SEAT_PLAY_HOST
        addr, box_id = boxes[min(len(calls), len(boxes) - 1)]
        if gate and expect is not None and (rt.endpoint_class(addr), box_id) != tuple(expect):
            if gated is not None:
                gated.append((play, limit, extra))
            rt.refuse_attestation(st, status_keys,
                                  "%s: the ansible-playbook process this operation ran exited "
                                  "rc=2 -- the identity gate refused the box before the "
                                  "imported play" % who)
        calls.append((play, limit, extra))
        ref = None
        if "scr_deploy_ref=" in (extra or ""):
            ref = (extra or "").split("scr_deploy_ref=")[1].split()[0]
        if shas is not None:
            ref = shas[min(len(calls) - 1, len(shas) - 1)]
        sections, identity = _answer(addr, box_id, ref)
        return out, sections, identity, SEAT_PLAY_HOST

    return _stub


def _phase_zero(monkeypatch, rt, name, before=None, after=None, host=SEAT_PLAY_HOST,
                out=None, calls=None):
    """Phase 0's whole world: the attestation and the ONE attested operation.

    The container answers `before` on the way in and `after` on the way out,
    because that DIFFERENCE is the only thing that tells a snapshot this play
    took from one the container was already holding -- an old snapshot of this
    batch's own label satisfies the name grammar, the listing and the binding
    predicate exactly, and the round before stamped it with the moment of
    recording and called it fresh.

    Both listings and the play are ONE call now (R8-M1), so this stubs the one
    function that runs it."""
    _attested(monkeypatch, rt)
    state = {"minted": False}
    before_l = before if before is not None else _listing(None)
    after_l = (after if after is not None else (_listing(name) if name else before_l))

    def operation(values=None, play=None, extra=None, st=None, status_keys=(), who=""):
        state["minted"] = True
        if calls is not None:
            calls.append(((play,), {"limit": rt.snapshot_target(values), "extra": extra}))
        return (out if out is not None else _play_out(name, host=host)), before_l, after_l

    monkeypatch.setattr(rt, "snapshot_operation", operation)
    monkeypatch.setattr(rt, "snapshot_listing", lambda values=None: before_l)
    return state


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


def test_a_control_holds_only_when_the_body_carries_its_type(monkeypatch):
    """M1: `1 == True` in Python, and a control that accepts a different type is not reading this body.

    JSON carries `1`, `1.0`, `"true"` and `true` as four different things; Python's == flattens the first
    three into the fourth for a control written as `True`. The control exists to prove the body IS the one
    being asked for, so a wrong body, an error page that happens to carry the key, or an older serialiser
    satisfied it -- and the absence beside it was then read as the new build. The defect is the OPERATION,
    not the line it was found on, so every reading a batch declares an expected value for is compared the
    same way: the ABSENT control, the forward marker, and the health markers, on a box and through the edge."""
    rt, _src = _release_train()
    monkeypatch.setattr(rt, "http_code", lambda host, path, **kw: "200")

    assert rt.reading_matches(True, True) is True
    for got in (1, 1.0, "true", "True", [1]):
        assert rt.reading_matches(got, True) is False, got
    assert rt.reading_matches(False, False) is True and rt.reading_matches(0, False) is False
    assert rt.reading_matches(True, 1) is False          # and the other direction
    assert rt.reading_matches("v4.14", "v4.14") is True and rt.reading_matches(3, 3) is True
    assert rt.reading_matches(rt._MISSING, True) is False

    m = _absent_marker(rt)
    for ctl, want, why in ((1, (False, False), "JSON 1 is not the boolean the control names"),
                           (1.0, (False, False), "nor is a float"),
                           ("true", (False, False), "nor the string"),
                           (True, (True, False), "the boolean itself: the control holds")):
        body = {"version": "1.40.3", m["control_key"]: ctl}       # the alias is absent in all four
        monkeypatch.setattr(rt, "route_json", lambda host, path, _b=body: _b)
        for host in (rt.PRIMARY, rt.STANDBY):
            assert rt.code_state(host)[1:3] == want, (host, ctl, why)
        if want == (True, False):
            rt.assert_edge_runs_new_code()                        # the inert twin, through the edge
        else:
            with pytest.raises(rt.Fail) as exc:
                rt.assert_edge_runs_new_code()
            assert "control" in str(exc.value), why

    # the FORWARD marker, on the batch that shipped with one
    rt.select_batch("bug392-server")
    fwd = rt.JSON_MARKERS[0]
    assert fwd["expect"] is True
    for got, want in ((1, (False, False)), ("true", (False, False)), (True, (True, False))):
        monkeypatch.setattr(rt, "route_json", lambda host, path, _b={fwd["key"]: got}: _b)
        assert rt.code_state(rt.PRIMARY)[1:3] == want, got

    # and the health markers, the third surface the same comparison is made on
    rt.select_batch("rejoin-phase-a")
    assert rt.CODE_MARKERS == ["ffa_hold_fences"]
    for got, want in ((True, (False, True)), (1, (True, False))):
        monkeypatch.setattr(rt, "health_json", lambda host, _b={"ffa_hold_fences": got}: _b)
        assert rt.code_state(rt.PRIMARY)[1:3] == want, got
    rt.select_batch(ABSENT_BATCH)


def test_verify_recomputes_the_bot_policy_from_the_selected_batch(monkeypatch, capsys):
    """M2: `bot_skipped` in the state says what SOME earlier run did, never what this batch requires.

    The state file outlives the run that wrote it and an entry can change between them, so a batch that now
    requires the bot could resume at verify onto an old truthy `bot_skipped`, deploy no bot, witness no bot
    and still save `verified`. The policy is therefore recomputed from the SELECTED batch: a batch without
    skip_bot treats a recorded skip as a contradiction and prints the reading it refused; a batch with
    skip_bot requires the recorded skip, with its own reason, because the phase that prints the reason is
    what proves the phase ran at all."""
    rt, _src = _release_train()
    asked = []
    for name, stub in (("assert_control", lambda host: None),
                       ("assert_health_keys", lambda hosts: None),
                       ("assert_positive_signals", lambda: None),
                       ("http_code", lambda host, path, **kw: "200"),
                       ("code_state", lambda host: (True, True, False, ["alias absent"])),
                       ("assert_edge_runs_new_code", lambda: None),
                       ("schema_state", lambda host: ([], [])),
                       ("index_state", lambda host: []),
                       # The phase ends by asking both boxes which commit their
                       # deployed clone is on. That has its own test with its
                       # own reddening arm; what this one is about is the bot
                       # policy, so the states that pass carry the sha and the
                       # probe is recorded rather than made.
                       ("assert_boxes_are_on", lambda sha, values=None: asked.append(sha)),
                       ("save_state", lambda st_: None)):
        monkeypatch.setattr(rt, name, stub)
    # ...and the persisted SHA goes through the same git door a fresh merge
    # does before any of that (R8-L4/L5), which is also somebody else's test.
    _code_sha_authenticated(monkeypatch, rt)
    witnessed = []
    monkeypatch.setattr(rt, "_bot_witness", lambda **kw: witnessed.append(kw))
    go = SimpleNamespace(go=True)

    # a batch that does NOT declare skip_bot, resumed onto a state that records one
    rt.BATCHES["_no_skip"] = {k: v for k, v in rt.BATCHES[ABSENT_BATCH].items() if k != "skip_bot"}
    try:
        rt.select_batch("_no_skip")
        assert rt.DEPLOY_BOT and rt.BOT_SKIP_REASON is None
        stale = "a reason some earlier run of some other batch wrote down"
        st = {"bot_skipped": stale, "bot_deployed": False}
        with pytest.raises(rt.Fail) as exc:
            rt.phase_verify(go, st)
        assert stale in str(exc.value)                # the reading it refused is printed
        # R9-M3: a refused verify leaves the attempt sentinel, never a success
        assert st.get("verified") == rt.ATTEMPTED and witnessed == []
        # ...and this is not the old "bot phase has not run" stop wearing a new
        # message: an empty state still stops, with that one
        st = {}
        with pytest.raises(rt.Fail) as exc:
            rt.phase_verify(go, st)
        assert "bot phase has not passed" in str(exc.value)
        assert st.get("verified") == rt.ATTEMPTED
        # R9-M5 (B6): the non-skip arm accepts only the exact True a witnessed
        # deploy writes. REFUSED and ATTEMPTED are truthy words, and a truth
        # test read either as a deployed bot.
        for word in ("REFUSED", rt.ATTEMPTED, "yes", 1):
            st = {"bot_deployed": word, "code_sha": MERGE_FULL}
            with pytest.raises(rt.Fail) as exc:
                rt.phase_verify(go, st)
            assert "bot phase has not passed" in str(exc.value), (word, str(exc.value))
            assert st.get("verified") == rt.ATTEMPTED and witnessed == [], word
        # the inert twin for this arm: the bot really was deployed, so it is
        # witnessed -- and witnessed BEFORE the arm passes, ahead of every
        # other reading this phase makes (B6)
        order = []
        monkeypatch.setattr(rt, "_bot_witness",
                            lambda **kw: witnessed.append(kw) or order.append("witness"))
        monkeypatch.setattr(rt, "assert_control", lambda host: order.append("control"))
        st = {"bot_deployed": True, "code_sha": MERGE_FULL}
        rt.phase_verify(go, st)
        assert st["verified"] is True and len(witnessed) == 1
        assert order and order[0] == "witness", order
        assert asked == [MERGE_FULL], asked
        # R9-L5: the success word travels with the GO run that earned it
        assert st["verified_evidence"]["code_sha"] == MERGE_FULL, st
        assert st["verified_evidence"]["mode"] == "GO" and rt.verified_is_backed(st), st
    finally:
        del rt.BATCHES["_no_skip"]

    # the batch as it ships: the skip is declared AND recorded -> passes, no witness
    rt.select_batch(ABSENT_BATCH)
    witnessed[:] = []
    capsys.readouterr()
    st = {"bot_deployed": False, "bot_skipped": rt.BOT_SKIP_REASON, "code_sha": MERGE_FULL}
    asked[:] = []
    rt.phase_verify(go, st)
    assert st["verified"] is True and witnessed == []
    assert asked == [MERGE_FULL], asked
    assert "NOT witnessed" in capsys.readouterr().out
    # a skip batch whose bot phase never ran at all is refused: the reason is
    # written down by the phase, so its absence means the phase did not run
    st = {}
    with pytest.raises(rt.Fail) as exc:
        rt.phase_verify(go, st)
    assert "must have RUN" in str(exc.value) and st.get("verified") == rt.ATTEMPTED
    # ...as is a skip recorded under a different reason than this entry gives
    st = {"bot_skipped": "some other batch's reason"}
    with pytest.raises(rt.Fail) as exc:
        rt.phase_verify(go, st)
    assert "not made under this batch's policy" in str(exc.value)
    assert st.get("verified") == rt.ATTEMPTED


def test_the_code_phase_refuses_a_train_with_no_recorded_snapshot(monkeypatch):
    """M3: the rollback point is a prerequisite of the deploy, for every batch, and `--from code` skips phase 0.

    Phase 0 takes the PVE snapshot and records the cc_* name the wrapper minted. A train resumed at the
    code phase -- which is exactly what a rerun after any earlier stop does -- never reaches phase 0, so the
    round-1 train could merge, push and deploy to both boxes with nothing to roll back to. The gate is asked
    before ANY command runs, including the read-only ones, so a refusal leaves the tree and the boxes exactly
    as they were. It is asked of a batch with migrations too: the snapshot is the rollback point for the CODE."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    log = []

    def record(cmd, **kw):
        log.append(" ".join(cmd) if isinstance(cmd, list) else cmd)
        raise _NoCommand(log[-1])

    monkeypatch.setattr(rt, "run", record)
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    monkeypatch.setattr(rt, "code_state", lambda host: (True, False, True, ["alias present"]))

    # both resume shapes land in this phase the same way, and both refuse
    for args in (SimpleNamespace(go=True, start="code", only=None),
                 SimpleNamespace(go=True, start=None, only="code")):
        log[:] = []
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(args, {})
        assert "snapshot" in str(exc.value) and "rollback point" in str(exc.value)
        assert log == []                     # not one command ran, read-only or otherwise
    # a batch WITH migrations is asked the same question
    rt.select_batch("rejoin-phase-a")
    log[:] = []
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(SimpleNamespace(go=True, start="code", only=None), {"schema_done": True})
    assert "snapshot" in str(exc.value) and log == []
    rt.select_batch(ABSENT_BATCH)
    # and phase 0 is still first for a run that starts at the beginning: the
    # gate is for the runs that do not
    assert [p for p, _fn in rt.PHASES][0] == "snapshot"

    # inert twin: with a snapshot recorded that BINDS to this train the phase
    # proceeds -- to the clean gate, then the provenance check
    stub, log2 = _fake_git(rt, {"990cd43": REVIEWED_FULL, "8820463": MAIN_FULL,
                                rt.BRANCH: REVIEWED_FULL, "main": MAIN_FULL},
                           trees={REVIEWED_FULL: REVIEWED_TREE})
    monkeypatch.setattr(rt, "run", stub)
    _snapshot_is_listed(monkeypatch, rt)
    with pytest.raises(_NoCommand) as exc:
        rt.phase_code(SimpleNamespace(go=True, start=None, only="code"), _snap())
    assert log2[0] == "git status --porcelain", log2
    assert log2[1].startswith("git %s rev-parse --verify" % NO_REPLACE), log2
    assert str(exc.value).startswith("git checkout main"), log2


def test_the_ABSENT_sentinel_is_value_unequal_to_its_own_spelling(monkeypatch):
    """L1: subclassing str kept the sentinel identity-distinct and left it value-EQUAL to the plain string.

    Every active dispatch used `is`, so nothing misread today -- but a sentinel that compares equal to a
    string a body could legitimately carry is a trap set for the first `==` anyone writes, and the type
    exists precisely so that cannot happen. It is now a final sentinel: equal to itself and to nothing else,
    printed by repr wherever a line describes it."""
    rt, _src = _release_train()
    assert not isinstance(rt.ABSENT, str)
    assert ("ABSENT" == rt.ABSENT) is False and (rt.ABSENT == "ABSENT") is False
    assert ("ABSENT" != rt.ABSENT) is True and (rt.ABSENT != "ABSENT") is True
    assert rt.ABSENT == rt.ABSENT and rt.ABSENT is rt.ABSENT
    assert repr(rt.ABSENT) == "ABSENT" and "%r" % (rt.ABSENT,) == "ABSENT"
    other = type(rt.ABSENT)()                      # a second instance is not this value either
    assert other is not rt.ABSENT and (other == rt.ABSENT) is False

    m = _absent_marker(rt)
    assert "ABSENT" in rt.marker_words(m) and "ABSENT" in rt.discriminator_words()

    # a body whose alias key holds the STRING "ABSENT" has the key PRESENT, so
    # it is the OLD build -- on a box and through the edge
    monkeypatch.setattr(rt, "http_code", lambda host, path, **kw: "200")
    spelled = {m["control_key"]: True, m["key"]: "ABSENT"}
    monkeypatch.setattr(rt, "route_json", lambda host, path, _b=spelled: _b)
    for host in (rt.PRIMARY, rt.STANDBY):
        assert rt.code_state(host)[1:3] == (False, True), host
    with pytest.raises(rt.Fail) as exc:
        rt.assert_edge_runs_new_code()
    assert "still reports" in str(exc.value)
    # inert twin: the key really gone, control held -> the NEW build
    monkeypatch.setattr(rt, "route_json", lambda host, path, _b={m["control_key"]: True}: _b)
    assert rt.code_state(rt.PRIMARY)[1:3] == (True, False)
    rt.assert_edge_runs_new_code()


def test_every_json_marker_is_validated_even_when_the_batch_also_adds_a_route():
    """L2: validation returned on `new_routes` before it read the json markers at all.

    A route batch carrying a marker with no control -- a check that cannot fail -- was accepted as dead
    configuration, and it would stay accepted until the day the route list emptied or the precedence
    changed, at which point the unreviewed marker becomes the discriminator. An entry is reviewed as a
    whole; nothing in it is exempt because something else outranks it today. The precedence itself is
    unchanged: a route batch is still judged on its routes."""
    rt, _src = _release_train()
    m = _absent_marker(rt)
    route = "/api/v1/a-route-neither-build-serves"

    def routed(marker):
        return dict(rt.BATCHES[ABSENT_BATCH], new_routes=[route],
                    smoke_route="/api/v1/mod-version", json_markers=[marker])

    for broken, why in ((dict((k, v) for k, v in m.items() if k != "control_key"),
                         "an ABSENT marker naming no control field"),
                        (dict((k, v) for k, v in m.items() if k != "control_expect"),
                         "a control field with no value to hold it to"),
                        (dict(m, control_key=m["key"]), "the marker as its own control"),
                        (dict(m, control_expect=rt.ABSENT), "a control that is itself an absence"),
                        (dict(m, expect=None), "expect None, which an absent key satisfies"),
                        (dict(m, why=""), "a probe nobody wrote down"),
                        (dict(m, path=rt.CONTROL_ROUTE), "read on the control route")):
        rt.BATCHES["_routed"] = routed(broken)
        try:
            with pytest.raises(rt.Fail) as exc:
                rt.select_batch("_routed")
            assert "json marker" in str(exc.value), why
        finally:
            del rt.BATCHES["_routed"]

    # inert twin: the same route batch with a COMPLETE marker is accepted, and
    # the route is still what this batch is judged on
    rt.BATCHES["_routed"] = routed(dict(m))
    try:
        rt.select_batch("_routed")
        assert rt.NEW_ROUTES == [route] and rt.discriminator_words() == route
    finally:
        del rt.BATCHES["_routed"]
    rt.select_batch(ABSENT_BATCH)


def test_every_lan_probe_the_check_makes_carries_the_version_header(monkeypatch, capsys):
    """L3: the entry claimed every LAN probe carries the version header; one of them went out bare.

    `check` printed the mod-version body from an unheadered curl, so the sentence was a claim the code did
    not keep -- and an operator could read that line as evidence the gate had been traversed. The probe now
    carries the header like every other one, which is the half of the choice that makes the sentence true
    rather than the half that narrows it. An unheadered read answers 426 wherever the gate is armed, and a
    426 on both builds is a line that can never disagree with itself."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    cmds = []

    def fake_run(cmd, **kw):
        cmds.append(list(cmd) if isinstance(cmd, list) else [cmd])
        return ""

    monkeypatch.setattr(rt, "run", fake_run)
    rt.phase_check(SimpleNamespace(go=False), {})
    out = capsys.readouterr().out

    curls = [c for c in cmds if c and c[0] == "curl"]
    assert len(curls) >= 4, cmds                 # mod-version, control, marker, health, per box
    want = "X-Mod-Version: " + rt.MOD_VERSION_HEADER
    for c in curls:
        assert want in c, c                      # every one of them, with no exception
    assert [c for c in curls if any("/api/v1/mod-version" in a for a in c)], curls
    # and the binding is stated beside the tips it is about
    assert "990cd43" in out and "8820463" in out, out


def test_the_batch_comment_states_only_what_the_code_and_the_pin_can_be_held_to():
    """L3, the prose half: a comment on a batch entry is a claim, and an operator reads it as evidence.

    The entry asserted an exact GO time nothing in the pin carries. The date and the report path are what
    can be held to, so that is what it says now. The skip_bot reason is a claim about the deploy range, and
    the range is named by the entry as of this round -- so it is checked against the repo instead of
    believed (#302)."""
    import re
    import subprocess
    rt, src = _release_train()
    start = src.index('"%s": {' % ABSENT_BATCH)
    entry_src = src[start:src.index('"state_path"', start)]
    # flattened: these sentences are wrapped across comment lines, and a claim
    # is a claim whichever column it breaks at
    flat = " ".join(entry_src.replace("#", " ").split())
    assert not re.search(r"\d{1,2}:\d{2}\s*Z", flat), flat
    # The report's own name is quoted WITHOUT its extension: a dotted token
    # whose final label is a two-letter country code is a hostname shape, and a
    # census that had to decide this one from context would be a census with a
    # judgement call in it.
    assert "Codex GO on 2026-09-22" in flat and "CODEX-BUG392-MERGE-R1-REPORT" in flat
    assert "Every LAN probe this train makes carries it" in flat

    entry = rt.BATCHES[ABSENT_BATCH]
    p = subprocess.run(["git", "diff", "--name-only",
                        "%s..%s" % (entry["main_expected"], entry["reviewed_tip"]),
                        "--", "backend/"], cwd=str(REPO), capture_output=True, text=True)
    if p.returncode != 0:
        pytest.skip("this clone does not carry the reviewed range")
    touched = sorted(l.strip() for l in p.stdout.splitlines() if l.strip())
    assert touched, "an empty range would make the claim below unfalsifiable"
    outside = [f for f in touched
               if f != "backend/api/main.py" and not f.startswith("backend/tests/")]
    assert outside == [], outside                       # the reason says there are none
    assert "backend/discord_bot.py" not in touched      # ...and names this one in particular


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


def test_the_recorded_snapshot_binds_to_this_train_its_label_its_age_and_the_listing(monkeypatch):
    """R2-M1: a rollback point protects ONE deploy, and the gate asked only whether a string was truthy.

    Phase 0 wrote down the bare cc_* name the wrapper minted and phase_code asked `if st.get("snapshot")`.
    A name copied out of another train's state file, one taken under a different batch's label, one taken
    last week, or one the wrapper's keep-10 prune has already removed all satisfied that -- and each one
    is a deploy that proceeds with nothing to roll back to. The record now carries the four facts that
    make it answerable, and the fifth question -- does it still exist -- is read from the wrapper's own
    listing at the moment it is asked, never from the state file that claims it."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    go = SimpleNamespace(go=True)
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    _snapshot_is_listed(monkeypatch, rt)
    log = []

    def record(cmd, **kw):
        log.append(" ".join(cmd) if isinstance(cmd, list) else cmd)
        raise _NoCommand(log[-1])

    monkeypatch.setattr(rt, "run", record)

    def refuses(st, *must_name):
        log[:] = []
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(go, st)
        for text in must_name:
            assert text in str(exc.value), (text, str(exc.value))
        assert log == []            # the four state questions cost no command at all
        return str(exc.value)

    from datetime import datetime, timedelta, timezone
    # the round-2 shape: a bare name, which answers none of the four
    refuses({"snapshot": "cc_pre-bug392-merge__20260922_030000"}, "bare str", "rollback point")
    # ...and no record at all, which is where round 2 started
    refuses({}, "no snapshot is recorded")
    # another train wrote it
    refuses(_snap(batch="sept14-gacha"), "sept14-gacha", ABSENT_BATCH)
    # another label: the name would stand for a different box's protection
    refuses(_snap(label="pre-sept12-gacha"), "pre-sept12-gacha", "pre-bug392-merge")
    # a name the wrapper did not mint for this label -- one label being a prefix
    # of another is exactly how this would pass unnoticed
    refuses(_snap(name="cc_pre-bug392-merge-2__20260922_030000"), "cc_pre-bug392-merge_")
    # a field the record cannot do without
    refuses(_snap(created_utc=""), "missing")
    # older than the window: a picture of a box that has moved since. The
    # window is measured from the listing taken BEFORE the play -- the moment
    # this train saw the container WITHOUT this name -- rather than from the
    # moment the record was written, so that is the field this arm moves.
    refuses(_snap(minted=_minted(before=(datetime.now(timezone.utc) - timedelta(hours=25))
                                 .isoformat(timespec="seconds"))), "24 hours")
    # and a timestamp from the future, whose age cannot be judged at all
    refuses(_snap(created_utc=(datetime.now(timezone.utc) + timedelta(hours=2))
                  .isoformat(timespec="seconds")), "in the future")
    refuses(_snap(created_utc="last tuesday"), "not a timestamp")

    # the fifth question: recorded, bound and fresh -- and pruned away since.
    # Asked after the clean gate, so it is the second thing this phase does.
    stub, log2 = _fake_git(rt, {"990cd43": REVIEWED_FULL, "8820463": MAIN_FULL,
                                rt.BRANCH: REVIEWED_FULL, "main": MAIN_FULL},
                           trees={REVIEWED_FULL: REVIEWED_TREE})
    monkeypatch.setattr(rt, "run", stub)
    for listing, why, says, names in (
            # an earlier snapshot OF THIS BATCH is still there and the recorded
            # one is not: the refusal names what it found, so it can be acted
            # on without a second lookup
            (_listing("cc_pre-bug392-merge__20260921_154805", "2026-09-21 15:48:05"),
             "pruned away since it was recorded", "is not in the container's snapshot listing",
             ["cc_pre-bug392-merge__20260921_154805"]),
            # ...and another batch's snapshot is not one of this batch's names,
            # so the count says none rather than vouching for a stranger
            (_listing("cc_pre-bug392-server__20260921_154805", "2026-09-21 15:48:05"),
             "only another batch's snapshot is listed",
             "carries 0 name(s) of the form this batch's snapshots take", []),
            ("", "the wrapper answered nothing at all",
             "no process exit status at all", [])):
        monkeypatch.setattr(rt, "snapshot_listing", lambda values=None, _l=listing: _l)
        log2[:] = []
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(go, _snap())
        assert says in str(exc.value), (why, str(exc.value))
        # it prints what it DID find, so the refusal can be acted on without a
        # second lookup
        for found in names:
            assert found in str(exc.value), (why, str(exc.value))
        assert log2 == ["git status --porcelain"], log2      # nothing past the clean gate

    # inert twin: bound, fresh and listed -> the phase proceeds to the binding
    # and on to the merge (the negative control is already recorded here, so
    # this arm stays about the snapshot)
    _snapshot_is_listed(monkeypatch, rt)
    log2[:] = []
    with pytest.raises(_NoCommand) as exc:
        rt.phase_code(go, dict(_snap(), pre_code_old_build=True))
    assert str(exc.value).startswith("git checkout main"), log2
    assert log2[0] == "git status --porcelain", log2

    # phase 0: a record that does not bind is NOT a reason to skip taking one,
    # and the record it writes carries all four facts
    taken = []
    fresh = "cc_pre-bug392-merge__20260922_031500"
    _phase_zero(monkeypatch, rt, fresh, calls=taken)
    st = _snap(batch="sept14-gacha")
    rt.phase_snapshot(SimpleNamespace(go=True), st)
    assert taken, "a record that does not bind must not skip the phase"
    assert st["snapshot"]["batch"] == ABSENT_BATCH
    assert st["snapshot"]["label"] == "pre-bug392-merge"
    assert st["snapshot"]["name"] == fresh
    assert rt.snapshot_record_problem(st) is None
    # a play that minted some other label is not recorded at all
    taken[:] = []
    _phase_zero(monkeypatch, rt, fresh, calls=taken,
                out=_play_out("cc_pre-sept12-gacha__20260922_031500"))
    with pytest.raises(rt.Fail) as exc:
        rt.phase_snapshot(SimpleNamespace(go=True), {})
    assert "cc_pre-bug392-merge_" in str(exc.value)
    # inert twin: a record that DOES bind skips, and takes nothing
    taken[:] = []
    bound = _snap()
    before = dict(bound["snapshot"])
    _phase_zero(monkeypatch, rt, bound["snapshot"]["name"], calls=taken,
                before=_listing(bound["snapshot"]["name"]))
    rt.phase_snapshot(SimpleNamespace(go=True), bound)
    assert taken == []                      # no play ran
    assert bound["snapshot"] == before      # and the record was left alone


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


def _bound_refs(rt, **over):
    """The refs a repository holds when the branch and main are where the review left them."""
    refs = {rt.BRANCH: REVIEWED_FULL, "main": MAIN_FULL}
    refs.update(over)
    return refs


def _deploy_recorder(monkeypatch, rt):
    """Let the REAL _deploy_both run and record the playbook command it composes.

    Stubbing _deploy_both would hide the one line this is about: the value the
    playbook is handed. The play itself is asserted, never executed."""
    calls = []
    # The per-box selector attestation has its own test with its own reddening
    # arms; this recorder is about the VALUE the playbook is handed.
    _attested(monkeypatch, rt)

    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(rt, calls))
    monkeypatch.setattr(rt, "assert_control", lambda host: None)
    monkeypatch.setattr(rt, "assert_route_probes", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_health_keys", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_edge_runs_new_code", lambda: None)
    monkeypatch.setattr(rt, "code_state", lambda host: (True, True, False, ["alias absent"]))
    return calls


def test_the_recorded_code_sha_is_an_object_id_and_that_id_is_what_deploys(monkeypatch, capsys):
    """R3-H1: the state file's code_sha was authenticated locally and then handed to the playbook as text.

    Every revision syntax git accepts resolves locally to whatever it names at that moment. `code_sha`
    set to `main` therefore passed the parents-and-tree check while main sat on the reviewed merge, and
    the playbook was handed the four letters `main`, which resolve AGAIN on the other side of the push --
    so a main that advanced between the check and the deploy put unreviewed content on both boxes, and
    the build marker still read NEW because the box really was running a new build. A deploy is pinned to
    an object or it is not pinned: the shape is asked of the raw string before any git command can
    resolve it, and the id git resolves is what travels from there."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    go = SimpleNamespace(go=True)
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    _snapshot_is_listed(monkeypatch, rt)

    # (a) a NAME where an object id belongs, refused before any git command at
    # all -- the stub raises on every command it is handed, so reaching one is
    # the failure, not a different error
    def no_commands(cmd, **kw):
        raise _NoCommand(" ".join(cmd) if isinstance(cmd, list) else cmd)

    monkeypatch.setattr(rt, "run", no_commands)
    for raw, why in (("main", "a branch name"), ("HEAD", "a symbolic ref"),
                     ("990cd43", "an abbreviation"), (REVIEWED_FULL.upper(), "upper case"),
                     (" %s" % MERGE_FULL, "an id with a stray space"),
                     (None, "a null"), (12, "a number")):
        st = dict(_snap(), code_sha=raw, pre_code_old_build=True)
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(go, st)
        assert "not a 40-character object id" in str(exc.value), (why, str(exc.value))
        assert repr(raw) in str(exc.value), (why, str(exc.value))   # the raw value is quoted
    # ...and in the plan arm too: a state file carrying a name is a broken
    # train whether or not this run is the one that would deploy it
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(SimpleNamespace(go=False), dict(_snap(), code_sha="main"))
    assert "not a 40-character object id" in str(exc.value)

    # (b) the right shape, an object this repository does not hold: the id that
    # travels has to be one git resolved, and nothing resolved
    stub, log = _fake_git(rt, _bound_refs(rt, main=MERGE_FULL), unknown=(MERGE_FULL,))
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True))
    assert "does not name a commit in this repository" in str(exc.value), str(exc.value)

    # (c) inert twin: a full object id, the reviewed merge, main sitting on it
    # -> it deploys, and the command line the playbook gets carries exactly it
    calls = _deploy_recorder(monkeypatch, rt)
    stub, log = _fake_git(rt, _bound_refs(rt, main=MERGE_FULL),
                          {MERGE_FULL: [MAIN_FULL, REVIEWED_FULL]},
                          {REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: REVIEWED_TREE})
    monkeypatch.setattr(rt, "run", stub)
    capsys.readouterr()
    st = dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True)
    rt.phase_code(go, st)
    # The two per-box selectors come from the SEAT, in deploy order, through
    # the one grammar door -- not from a literal in the train.
    assert [c[1] for c in calls] == [rt.checked_target(k) for k in rt.DEPLOY_LIMIT_KEYS], calls
    assert [c[1] for c in calls] == [SEAT_PRIMARY_LIMIT, SEAT_STANDBY_LIMIT], calls
    for _pb, _limit, extra in calls:
        assert extra == "-e scr_deploy_ref=%s" % MERGE_FULL, calls
    out = capsys.readouterr().out
    # printed beside what it was reviewed as, so a transcript says all three
    assert "CODE_SHA = %s" % MERGE_FULL in out, out
    assert "990cd43" in out and "8820463" in out, out

    # (d) and the last door: the playbook is handed an id by construction, so a
    # caller that found a way to pass a name is refused at the deploy itself
    # ...including a 40-hex id carrying a trailing newline. Python's `$` also
    # matches immediately before a final newline, so `_FULL_SHA.match` accepted
    # one: the value read out of a file or pasted from a line passed every
    # shape check in the chain while not being the canonical id any of them
    # meant. `\Z` is the whole string and nothing else.
    for name in ("main", "990cd43", "", MERGE_FULL + "\n", "\n" + MERGE_FULL):
        with pytest.raises(rt.Fail) as exc:
            rt._deploy_both(name)
        assert "40-character object id" in str(exc.value), name
    assert rt._FULL_SHA.match(MERGE_FULL) and not rt._FULL_SHA.match(MERGE_FULL + "\n")


def test_authenticating_git_runs_without_replacements_and_the_remote_must_hold_the_merge(monkeypatch):
    """R3-H2: a local refs/replace/ ref answers every read with a different object under the same id.

    Parents, tree and content all come back from the substitute, so a wrong sha with a replacement
    exposing the expected parents and the expected tree passed every check -- and the remote, which has
    no such ref, holds the wrong sha's real content, which is what the boxes fetch. Two spellings of one
    instruction (the option and the environment variable) turn the replacement off for every command
    whose answer is an authentication. And because the boxes fetch from the REMOTE and not from this
    checkout, the remote's main is read before the first deploy command and has to BE the merge."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    go = SimpleNamespace(go=True)
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    _snapshot_is_listed(monkeypatch, rt)
    auth_verbs = ("rev-parse", "rev-list", "merge-base", "merge-tree", "ls-remote", "cat-file")

    def assert_every_authentication_disabled_replacement(stub, log):
        seen = 0
        for cmd, env in zip(log, stub.envs):
            parts = cmd.split()
            if parts[0] != "git":
                continue
            verb = parts[2] if len(parts) > 2 and parts[1] == NO_REPLACE else parts[1]
            if verb not in auth_verbs:
                continue
            seen += 1
            assert parts[1] == NO_REPLACE, cmd
            assert (env or {}).get("GIT_NO_REPLACE_OBJECTS") == "1", (cmd, env)
        assert seen >= 3, log        # the check itself has to have had something to check
        return seen

    # (a) the replacement: WITHOUT the flag this sha shows the expected parents
    # and the reviewed tree; with it, its real ones. The train must see the real
    # ones and refuse, printing the id it was told and the ids it required.
    stub, log = _fake_git(rt, _bound_refs(rt, main=MERGE_FULL),
                          parents={MERGE_FULL: [OTHER_FULL, REVIEWED_FULL]},
                          trees={REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: OTHER_TREE},
                          replaced={MERGE_FULL: ([MAIN_FULL, REVIEWED_FULL], REVIEWED_TREE)})
    monkeypatch.setattr(rt, "run", stub)
    deployed = []
    monkeypatch.setattr(rt, "_deploy_both", lambda sha, extra=None, st=None, **_kw: deployed.append(sha))
    monkeypatch.setattr(rt, "code_state", lambda host: (True, False, True, ["alias present"]))
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True))
    assert MERGE_FULL in str(exc.value) and MAIN_FULL in str(exc.value), str(exc.value)
    assert OTHER_FULL in str(exc.value), str(exc.value)
    assert deployed == []
    assert_every_authentication_disabled_replacement(stub, log)

    # (b) the remote is where the boxes fetch from: a remote main that is not
    # the authenticated merge is refused BEFORE the first deploy command
    good_parents = {MERGE_FULL: [MAIN_FULL, REVIEWED_FULL]}
    good_trees = {REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: REVIEWED_TREE}
    for remote, why in ((OTHER_FULL, "the remote moved on"), ("", "the remote named no main")):
        stub, log = _fake_git(rt, _bound_refs(rt, main=MERGE_FULL), good_parents, good_trees,
                              remote_main=remote)
        monkeypatch.setattr(rt, "run", stub)
        deployed[:] = []
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(go, dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True))
        assert "remote" in str(exc.value) and MERGE_FULL in str(exc.value), (why, str(exc.value))
        assert deployed == [], why

    # (c) inert twin: no replacement, and a remote sitting on the merge
    stub, log = _fake_git(rt, _bound_refs(rt, main=MERGE_FULL), good_parents, good_trees,
                          remote_main=MERGE_FULL)
    monkeypatch.setattr(rt, "run", stub)
    monkeypatch.setattr(rt, "code_state", lambda host: (True, True, False, ["alias absent"]))
    monkeypatch.setattr(rt, "assert_route_probes", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_health_keys", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_edge_runs_new_code", lambda: None)
    deployed[:] = []
    rt.phase_code(go, dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True))
    assert deployed == [MERGE_FULL]
    assert_every_authentication_disabled_replacement(stub, log)
    assert [c for c in log if "ls-remote" in c], log      # and it really was asked


def _printed_capture(rt, capsys, listing):
    """(dropped, the capture's lines) -- what `capture_snapshot_listing` PRINTED, between its two
    fixed lines. B11 (round 11): the capture is printed and never written, so the transcript is
    where a test reads it."""
    capsys.readouterr()
    dropped = rt.capture_snapshot_listing(listing)
    out = capsys.readouterr().out
    assert out.count(rt.CAPTURE_OPEN) == 1 and out.count(rt.CAPTURE_CLOSE) == 1, out
    body = out.split(rt.CAPTURE_OPEN, 1)[1].split(rt.CAPTURE_CLOSE, 1)[0]
    return dropped, [l for l in body.splitlines() if l.strip()]


def test_the_captured_listing_is_built_from_records_and_everything_else_is_dropped(monkeypatch,
                                                                                   capsys):
    """R4-H3: a capture that STRIPS what it recognises is a promise about every string that will ever exist.

    The round before this one tokenised the names the seat knows by value and the shapes it was told
    about -- a per-host header, a collision warning, an address, a dotted name -- and then read its own
    output back looking for the same shapes. An unknown single-label name, an IPv6 literal, or a name
    sitting inside a token no rule described walked through both halves untouched: `taken on secretbox`
    is not a header, not a warning, not an address and not dotted, so it was written into the bundle.

    So nothing of the wrapper's answer is copied at all. The answer is parsed into records whose every
    field is a fixed word from the train or a value that matched a grammar there -- a cc_ name, a
    timestamp, a status word, an exit code -- and those records are what is printed. Everything else is
    dropped and counted, and the count is the only trace it leaves."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    body = (" `-> cc_pre-bug392-merge__20260922_030000 2026-09-22 03:00:01     auto snapshot\n"
            "[WARNING]: Found both group and host with same name: a-group\n"
            "taken on secretbox\n"
            "asked of a-controller\n"
            "  `-> current                    You are here!")

    dropped, lines = _printed_capture(rt, capsys, _listing_raw(body))
    written = "\n".join(lines)
    # (a) what the gate reads survives, as a record
    assert "SNAPSHOT name=cc_pre-bug392-merge__20260922_030000 taken=2026-09-22 03:00:01" in written
    assert "SECTION phase=BEFORE rc=0" in written
    assert "GATE names=1 usable=yes" in written
    # (b) the reddening arm of the round before: a body line that is not a
    # header, not a warning, not an address and not dotted. It is ABSENT, and
    # the only thing it left behind is a number.
    assert "secretbox" not in written, written
    for leak in ("a-machine", "a-group", "a-controller", "WARNING", "You are here"):
        assert leak not in written, (leak, written)
    assert dropped == 4 and "DROPPED 4" in written, (dropped, written)
    # (c) a line that DOES parse as a record, carrying an extra token: the
    # record is printed and the extra token is not
    _d2, lines2 = _printed_capture(rt, capsys, _listing_raw(
        " `-> cc_pre-bug392-merge__20260922_030002 2026-09-22 03:00:02  on a-node.example\n"
        "  `-> current                    You are here!"))
    written2 = "\n".join(lines2)
    assert ("SNAPSHOT name=cc_pre-bug392-merge__20260922_030002 taken=2026-09-22 03:00:02 "
            "zone=none") in written2
    assert "a-node" not in written2 and "example" not in written2, written2
    # (c2) the machine's own statement is printed as a CLASS and the
    # address is dropped on the floor -- R8-H5 turns it into one at the
    # moment it is read, and this line is the second answer to the same
    # question. Handed a raw address on purpose: a fixture that hands it
    # a token already makes this check one that cannot fail.
    _d4, lines4 = _printed_capture(rt, capsys, _listing_raw(
        body, identity=(SEAT_BOX_ENDPOINT, SEAT_BOX_ID)))
    written4 = "\n".join(lines4)
    assert "BOX endpoint=OTHER fingerprint=MATCH" in written4, written4
    assert SEAT_BOX_ENDPOINT not in written4, written4
    # (d) every line printed is a header line the train spells out or a record
    # in the grammar -- the check that makes the rest a form and not a habit
    for line in lines:
        assert line in rt.CAPTURE_HEADER or rt.record_line_re().match(line), line
    # ...and it can fail: a composer that appended the wrapper's own prose
    # refuses instead of printing it, and prints NOTHING of the capture
    monkeypatch.setattr(rt, "listing_records",
                        lambda listing: (["taken on secretbox"], 0))
    capsys.readouterr()
    with pytest.raises(rt.Fail) as exc:
        rt.capture_snapshot_listing(_listing_raw(body))
    assert "not one of the record forms" in str(exc.value)
    out = capsys.readouterr().out
    assert rt.CAPTURE_OPEN not in out and "secretbox" not in out, out


def test_the_capture_prints_records_and_writes_no_file(monkeypatch, capsys, tmp_path):
    """B11 (round 11), after R7-L4, R7-L1, R4-L5, R6-L2 and R8-L1: the capture writes NOTHING.

    The frozen bar says this train writes nothing outside its state file and its printed plan. The
    capture was a FILE, and four rounds bounded that write in turn -- a destination that was an
    argument, then one place, then the final path and not its parent, then the descriptor's link
    count, then a fresh name and a rename -- and each bound left the next window, because the write
    itself was the thing the clause forbids. There is no file now: the records are composed in memory
    and printed between two fixed lines, which is the printed plan.

    So the arms of those rounds -- a symlinked destination, a hard link planted before the rename, a
    link count nobody can read -- have nothing left to aim at, and the one assertion that replaces
    them is stronger than all of them: during a capture, nothing is created, opened for writing,
    renamed, linked or made into a directory, anywhere."""
    import builtins
    import shutil
    import tempfile
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "train-state.json").write_text("{}", encoding="utf-8")
    fresh = tmp_path / "never-written" / "state"
    monkeypatch.setattr(rt, "STATE_PATH", str(fresh / "state.json"))
    listing = _listing("cc_pre-bug392-merge__20260922_030000")

    def _tree():
        return sorted((str(p.relative_to(tmp_path)), p.stat().st_size if p.is_file() else -1)
                      for p in tmp_path.rglob("*"))

    # Every primitive that can put bytes or a name on a disk, spied for the
    # length of the capture. A call to any of them is a write this train
    # does not make any more; the file-tree comparison below is the second
    # witness, for a write through a primitive this list does not name.
    writes = []
    real_open = builtins.open

    def _open(file, mode="r", *a, **kw):
        if any(c in str(mode) for c in "wax+"):
            writes.append(("open", str(mode)))
        return real_open(file, mode, *a, **kw)

    def _spy(name):
        def _refuse(*a, **kw):
            writes.append((name, None))
            raise AssertionError("the capture called %s" % name)
        return _refuse

    before = _tree()
    capsys.readouterr()
    with monkeypatch.context() as m:
        m.setattr(builtins, "open", _open)
        for mod, name in ((rt.os, "open"), (rt.os, "replace"), (rt.os, "rename"),
                          (rt.os, "link"), (rt.os, "symlink"), (rt.os, "makedirs"),
                          (rt.os, "mkdir"), (tempfile, "mkstemp"), (tempfile, "mkdtemp"),
                          (tempfile, "NamedTemporaryFile"), (shutil, "copyfile"),
                          (shutil, "move")):
            m.setattr(mod, name, _spy("%s.%s" % (mod.__name__, name)))
        dropped = rt.capture_snapshot_listing(listing)
    out = capsys.readouterr().out
    assert writes == [], writes
    assert _tree() == before, (before, _tree())
    assert not fresh.exists(), "a capture must not even create the state directory"
    # ...and what it did instead: the records, printed between the two lines
    assert out.count(rt.CAPTURE_OPEN) == 1 and out.count(rt.CAPTURE_CLOSE) == 1, out
    body = out.split(rt.CAPTURE_OPEN, 1)[1].split(rt.CAPTURE_CLOSE, 1)[0]
    assert "SNAPSHOT name=cc_pre-bug392-merge__20260922_030000" in body, body
    # the one line dropped is pct's closing `current` entry: it is read as the
    # completeness marker (R10-M1) and, like every line that is not a
    # snapshot, it is not copied
    assert "GATE names=1 usable=yes" in body and dropped == 1, (dropped, body)
    # the machinery the file needed is gone, not merely unused
    for gone in ("capture_path", "capture_destination", "link_count", "_hard_linked"):
        assert not hasattr(rt, gone), gone
    # the flag cannot carry a destination: it takes no value at all
    assert "--capture-listing" in _src
    flag = _src[_src.index('"--capture-listing"'):]
    assert 'action="store_true"' in flag[:400], flag[:400]
    assert "metavar" not in flag[:400], flag[:400]

    # ...and the record the machine's own identity leaves in it. The endpoint
    # here is one this train does NOT declare, and an endpoint it does not
    # declare is a machine address or a machine name like any other: the fixed
    # word goes in its place and the fingerprint -- a digest -- carries the
    # identity. This is what the round-8 scan found by RUNNING: the listing is
    # asked of the virtualisation host, so the address the capture actually
    # wrote was a fourth machine's, under a grammar that admitted any dotted
    # quad.
    _d, lines = _printed_capture(rt, capsys, listing)
    written = "\n".join(lines)
    assert "BOX endpoint=OTHER fingerprint=MATCH" in written, written
    assert SEAT_BOX_ENDPOINT not in written, written
    # R8-H4: the FINGERPRINT is not printed either. It is minted at first boot
    # and is the same for the life of that installation, so a line carrying
    # one identifies the installation exactly as a machine name does. It is
    # compared in memory and the VERDICT is what is printed.
    assert SEAT_BOX_ID not in written, written
    # ...and an ADDRESS this train does not declare is set aside the same way.
    # The address is RFC 5737 documentation space, which cannot be any
    # machine's.
    undeclared = _listing(None, endpoint=rt.endpoint_token("203.0.113.219"))
    _d, lines = _printed_capture(rt, capsys, undeclared)
    written = "\n".join(lines)
    assert "BOX endpoint=OTHER fingerprint=MATCH" in written, written
    assert "203.0.113.219" not in written, written
    # inert twin: an endpoint it DOES declare is printed as its class, because
    # a record that cannot say which box answered says nothing
    declared = _listing(None, endpoint=rt.endpoint_token(rt.PRIMARY))
    _d, lines = _printed_capture(rt, capsys, declared)
    assert "BOX endpoint=PRIMARY fingerprint=MATCH" in "\n".join(lines), lines
    # ...and a reading whose fingerprints did not both come back says MISSING,
    # which is not MATCH: "no comparison" is not "they agreed"
    one = _listing(None, fingerprints=[SEAT_BOX_ID])
    _d, lines = _printed_capture(rt, capsys, one)
    assert "fingerprint=MISSING" in "\n".join(lines), lines
    moved = _listing(None, fingerprints=[SEAT_BOX_ID, "f" * 64])
    _d, lines = _printed_capture(rt, capsys, moved)
    written = "\n".join(lines)
    assert "fingerprint=MISMATCH" in written, written
    assert "f" * 64 not in written, written
    # ...and the grammar itself admits the classes and nothing else
    form = rt.record_line_re()
    assert form.match("BOX endpoint=STANDBY fingerprint=MATCH")
    assert form.match("BOX endpoint=OTHER fingerprint=MISSING")
    assert not form.match("BOX endpoint=203.0.113.219 fingerprint=MATCH")
    assert not form.match("BOX endpoint=OTHER fingerprint=%s" % SEAT_BOX_ID)
    # ...and nothing anywhere under the test's directory moved across all of it
    assert _tree() == before, (before, _tree())
    assert not fresh.exists()


def test_a_listed_snapshot_matches_only_as_a_whole_token(monkeypatch):
    """R3-M1: the parse pulled `cc_*` out of the MIDDLE of a token, so a longer name answered for a shorter one.

    `re.findall(r"cc_[A-Za-z0-9_.:-]+")` reads `cc_pre-bug392-merge__T` out of `old-cc_pre-bug392-merge__T`,
    which is a different snapshot -- so the gate that exists to prove the rollback point still exists
    passed on a listing that proves it does not. Whole tokens on both ends, and ONE grammar for the
    listing and for the play's own output, so the name recorded and the name looked for cannot be two
    different readings. R11-M1 (round 12): the play's own output is read as whole tokens
    (`minted_names`), and a listing by pct's NAME FIELD (`cc_names`) -- a token found anywhere in a
    listing includes every description."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    name = _snap()["snapshot"]["name"]
    assert rt.minted_names("old-%s" % name) == []
    assert rt.minted_names("%s.bak" % name) == []      # a suffix is not the minted form either
    assert rt.minted_names("'%s'," % name) == [name]        # quoting is not a prefix
    assert rt.cc_names(" `-> old-%s 2026-09-22 03:00:01  auto" % name) == []
    assert rt.cc_names(" `-> %s.bak 2026-09-22 03:00:01  auto" % name) == []
    assert rt.cc_names(" `-> %s 2026-09-22 03:00:01  auto" % name) == [name]
    assert rt.cc_names("'%s'," % name) == []       # a bare token is no pct entry

    go = SimpleNamespace(go=True)
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    stub, log = _fake_git(rt, _bound_refs(rt), trees={REVIEWED_FULL: REVIEWED_TREE})
    monkeypatch.setattr(rt, "run", stub)
    # the embedded name: the recorded snapshot is NOT there, and the phase says so
    monkeypatch.setattr(rt, "snapshot_listing",
                        lambda values=None: _listing("old-%s" % name))
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, _snap())
    assert "is not in the container's snapshot listing" in str(exc.value), str(exc.value)
    assert log == ["git status --porcelain"], log

    # inert twin: the exact token, and the phase walks on to the merge
    _snapshot_is_listed(monkeypatch, rt)
    with pytest.raises(_NoCommand) as exc:
        rt.phase_code(go, dict(_snap(), pre_code_old_build=True))
    assert str(exc.value).startswith("git checkout main")

    # the play's own output is read under the same grammar, so an embedded
    # name is not recorded as the snapshot this train took either
    _phase_zero(monkeypatch, rt, name, out=_play_out("old-%s" % name))
    with pytest.raises(rt.Fail) as exc:
        rt.phase_snapshot(SimpleNamespace(go=True), {})
    assert "reported no cc_pre-bug392-merge__* snapshot name" in str(exc.value), str(exc.value)


def test_phase_zero_takes_a_fresh_snapshot_when_the_recorded_one_is_no_longer_listed(monkeypatch, capsys):
    """R3-M2: two predicates for one question left the prescribed recovery skipping itself.

    Phase 0 asked the four metadata questions and phase 4 asked those plus the listing. A snapshot that
    was pruned after a primary-only deploy therefore failed phase 4 -- which prints `--only snapshot` as
    the way out -- while phase 0 skipped on the metadata alone, so the prescribed command did nothing
    and the split fleet had nothing that could move it. One predicate, asked cheapest-first."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    name = _snap()["snapshot"]["name"]
    fresh = "cc_pre-bug392-merge__20260922_031500"
    taken = []

    # metadata-valid, pruned away since: the record does not bind any more, and
    # THIS phase is the one that replaces it
    _phase_zero(monkeypatch, rt, fresh, calls=taken,
                before=_listing("cc_pre-bug392-server__1"),
                after=_listing(fresh))
    st = _snap()
    assert rt.snapshot_record_problem(st) is None       # the cheap half still says yes
    assert "is not in the container's snapshot listing" in rt.snapshot_binding_problem(st)
    rt.phase_snapshot(SimpleNamespace(go=True), st)
    assert taken, "a recorded snapshot that is no longer listed must not skip phase 0"
    assert st["snapshot"]["name"] == fresh
    out = capsys.readouterr().out
    assert "it does not bind to this train" in out and "not in the container's" in out, out

    # inert twin: still listed -> skipped, nothing taken, and the reason printed
    taken[:] = []
    _snapshot_is_listed(monkeypatch, rt, name=name)
    bound = _snap()
    before = dict(bound["snapshot"])
    rt.phase_snapshot(SimpleNamespace(go=True), bound)
    assert taken == [] and bound["snapshot"] == before
    out = capsys.readouterr().out
    assert "present in the wrapper's listing" in out and "skips" in out, out

    # and the two phases agree about the SAME record: phase 4 refuses the
    # pruned one and phase 0 replaces it, which is what makes the refusal's own
    # prescription (`--only snapshot`) do something
    monkeypatch.setattr(rt, "snapshot_listing",
                        lambda values=None: _listing("cc_pre-bug392-server__1"))
    stub, log = _fake_git(rt, _bound_refs(rt), trees={REVIEWED_FULL: REVIEWED_TREE})
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(SimpleNamespace(go=True), _snap())
    assert "is not in the container's snapshot listing" in str(exc.value)
    assert "--only snapshot" in str(exc.value)
    assert "snapshot_binding(st)" in _src


def test_a_zone_less_listing_time_is_unknown_and_never_read_as_UTC(monkeypatch, capsys):
    """R4-L1: a wall clock with no zone is not a moment, and reading it as UTC made an old snapshot young.

    The round before this one measured freshness from the timestamp the listing prints and labelled it
    UTC. The wrapper prints no zone. On a container running ahead of this seat, a snapshot really thirty
    hours old arrives with a wall-clock reading that lands nineteen or twenty hours back -- inside the
    window -- so the gate whose whole job is to catch a stale rollback point passes on one, and only a
    reading that came out in the FUTURE fell back. An unknown reading is now unknown: freshness falls
    back to the recording clock, which the metadata gate has already judged, and the transcript says
    which clock answered and why. A listing that does state a zone is still used."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    from datetime import datetime, timedelta, timezone
    name = _snap()["snapshot"]["name"]
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).strftime("%Y-%m-%d %H:%M:%S")
    st = _snap()
    assert rt.snapshot_record_problem(st) is None

    # (a) the reddening arm of the defect: a zone-less reading thirty hours back
    # is NOT an age. It falls back and says so, naming the missing zone.
    monkeypatch.setattr(rt, "snapshot_listing",
                        lambda values=None: _listing(name, old))
    problem, how = rt.snapshot_listing_problem(st)
    assert problem is None, problem
    assert "names no zone" in how and "judged from the listing this train took BEFORE the play" in how, how
    moment, why_not = rt.listed_snapshot_time(rt.snapshot_listing(), name)
    assert moment is None and "names no zone" in why_not

    # (b) ...and with a zone, the container's own clock decides, in both
    # directions: thirty hours old is refused, minutes old passes and says so
    monkeypatch.setattr(rt, "snapshot_listing",
                        lambda values=None: _listing(name, old, zone="+00:00"))
    problem, how = rt.snapshot_listing_problem(st)
    assert problem and "the container's own listing says" in problem, problem
    assert "24 hours" in problem and how is None
    for zone in ("+00:00", "Z", "UTC", "+0000"):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        monkeypatch.setattr(rt, "snapshot_listing",
                            lambda values=None, _z=zone, _n=now: _listing(name, _n, zone=_z))
        problem, how = rt.snapshot_listing_problem(st)
        assert problem is None, (zone, problem)
        assert "the container's own listing says" in how, (zone, how)

    # (c) no timestamp at all, and a zoned timestamp that reads ahead of this
    # clock, both fall back to the recording clock and SAY so. Each is a WHOLE
    # listing -- it ends with pct's closing `current` entry, as every listing
    # the gate accepts must (R10-M1) -- so the arm is about the clock alone.
    ahead = (datetime.now(timezone.utc) + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
    closer = "\n  `-> current                   You are here!"
    for text, said in ((" `-> %s   auto snapshot" % name, "prints no timestamp"),
                       (" `-> %s %s +00:00  auto" % (name, ahead), "names no zone")):
        monkeypatch.setattr(rt, "snapshot_listing",
                            lambda values=None, _t=text: _listing_raw(_t + closer))
        problem, how = rt.snapshot_listing_problem(st)
        assert problem is None, problem
        assert "judged from the listing this train took BEFORE the play" in how, how
    assert said            # both arms ran

    # (c2) a zone token needs its boundary at END OF TOKEN. Without one the
    # regex found `Z` at the front of `Zebra` and `UTC` at the front of
    # `UTCdescription`, so a wall clock with an ordinary word after it read as a
    # zoned moment -- and a container running ahead of this seat then made an
    # expired rollback point look fresh. A boundary spelt as "not one of
    # [A-Za-z0-9_]" only moved the hole: that is an ASCII denial, so `Zebra`
    # stopped being a zone while any word whose next character is outside ASCII
    # still was one. The boundary is where the TOKEN ends, which is not a
    # question about alphabets at all.
    for word in ("Zebra", "UTCdescription", "GMTplus",
                 # the Unicode continuations the ASCII denial admitted
                 u"Zébra", u"UTCédescription", u"GMT中"):
        text = " `-> %s %s %s  auto" % (name, old, word)
        monkeypatch.setattr(rt, "snapshot_listing",
                            lambda values=None, _t=text: _listing_raw(_t + closer))
        moment, why_not = rt.listed_snapshot_time(rt.snapshot_listing(), name)
        assert moment is None and "names no zone" in why_not, word
        problem, how = rt.snapshot_listing_problem(st)
        assert problem is None, (word, problem)
        assert "judged from the listing this train took BEFORE the play" in how, (word, how)
    # ...and the bare token, which IS a zone, still is one
    text = " `-> %s %s Z  auto" % (name, old)
    monkeypatch.setattr(rt, "snapshot_listing",
                        lambda values=None, _t=text: _listing_raw(_t + closer))
    moment, why_not = rt.listed_snapshot_time(rt.snapshot_listing(), name)
    assert moment is not None and why_not is None, (moment, why_not)

    # (d) the phase that SKIPS on this predicate prints the same sentence the
    # phase that refuses on it prints: "fresh" is a different claim depending on
    # which clock answered, and a plan that does not say which implies the one
    # that was not read
    _snapshot_is_listed(monkeypatch, rt, name=name)
    capsys.readouterr()
    rt.phase_snapshot(SimpleNamespace(go=True), _snap())
    out = capsys.readouterr().out
    assert "freshness:" in out and "names no zone" in out, out


def test_the_listing_counts_only_the_answer_of_the_one_machine_that_answered(monkeypatch):
    """R3-L2: every block of the group's answer was read as one pile, so any member could vouch for the rollback point.

    Ansible answers per host. The rollback point sits on the machine the snapshot play targets, and a
    name found in another member's answer is another machine's snapshot -- the gate would pass while the
    box this train is about to deploy to has nothing to roll back to. One responding machine is the
    expected shape; none, several, or one that exited non-zero are all "could not tell", which is not
    yes."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    name = _snap()["snapshot"]["name"]

    # R8-M1 moved the answer one level up: the listing is a TASK of the
    # attested playbook, so "how many machines answered" is the playbook's own
    # RECAP rather than a count of header shapes in somebody else's output. Two
    # members answering is two recap rows, and it is refused before a single
    # name is read.
    two = (_recap(host="machine-a") + "\nmachine-b                 : ok=3    changed=1    "
           "unreachable=0    failed=0")
    monkeypatch.setattr(rt, "run", _attesting_run(rt, listing=True, name=name, recap=two))
    with pytest.raises(rt.Fail) as exc:
        rt.snapshot_listing()
    assert "recap names 2 machines" in str(exc.value), str(exc.value)
    # ...and a recap that names NONE is the same answer, not an empty listing
    monkeypatch.setattr(rt, "run", _attesting_run(rt, listing=True, name=name,
                                                  recap="PLAY RECAP ***"))
    with pytest.raises(rt.Fail) as exc:
        rt.snapshot_listing()
    assert "recap names 0 machines" in str(exc.value), str(exc.value)

    # a machine that answered non-zero printed something that is not a listing
    names, problem = rt.listed_snapshot_names(_listing(name, rc=2))
    assert names == [] and "rc=2" in problem, problem
    # ...and a listing carrying no process status at all is not an empty
    # listing, it is no answer: the status is the process's (R9-M1), and a
    # listing handed on without one never came through the one door that
    # reads it
    names, problem = rt.listed_snapshot_names({"raw": "", "rc": None})
    assert names == [] and "no process exit status at all" in problem, problem
    # ...and the two readings of one read-only question disagreeing means the
    # listing is a picture of two moments
    names, problem = rt.listed_snapshot_names(_listing(name, agree=False))
    assert names == [] and "picture of two moments" in problem, problem

    # inert twin: one machine, rc=0, and its own answer is what is read
    names, problem = rt.listed_snapshot_names(_listing(name))
    assert names == [name] and problem is None


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


def test_the_snapshot_play_and_the_snapshot_listing_are_aimed_at_one_target(monkeypatch, capsys):
    """R4-M1: the play chose its own machine and the listing was asked of a separately configured group.

    The snapshot phase ran `snapshot-scr.yml` with no --limit, so the play's own hosts: line decided
    which container was snapshotted, while the gate that proves the rollback point still exists asked a
    group the seat configures. Nothing compared the two. A group that holds a different machine -- or a
    pattern that selects several -- therefore answers rc=0 with a listing of somebody else's snapshots,
    and the deploy proceeds believing it has a rollback point on the box it is about to change.

    One value, declared once, consumed by both, checked against a NAME grammar before it reaches a
    command line and quoted for the remote shell when it does."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    assert set(rt.SNAPSHOT_TARGET_KEYS.values()) == {"pve_group"}
    assert rt.snapshot_target() == "a-group"

    # (a) the reddening arm for the defect itself: the two consumers configured
    # from different keys -- refused before any command, by the value both of
    # them have to come from
    monkeypatch.setitem(rt.SNAPSHOT_TARGET_KEYS, "listing", "controller")
    monkeypatch.setattr(rt, "run", lambda cmd, **kw: _raise_no_command(cmd))
    with pytest.raises(rt.Fail) as exc:
        rt.snapshot_listing()
    assert "different keys" in str(exc.value)
    with pytest.raises(rt.Fail):
        rt.phase_snapshot(SimpleNamespace(go=True), {})
    monkeypatch.setitem(rt.SNAPSHOT_TARGET_KEYS, "listing", "pve_group")

    # (b) a target that is not a plain name never reaches a command line, in
    # either consumer
    for bad in ("a-group; rm -rf /", "a-group:another", "a group", "*", "$(hostname)",
                "a-group,other", "!a-group", "a-group&other", "a-grou?"):
        # Each of these is a differently CONFIGURED seat, which is a different
        # run: the seat is read once per process and answered from that first
        # reading ever after (R8-H2).
        _fresh_process(rt, "pve_group")
        monkeypatch.setenv("SCR_TRAIN_PVE_GROUP", bad)
        with pytest.raises(rt.Fail) as exc:
            rt.snapshot_listing()
        assert "not a plain name" in str(exc.value), bad
    # ...and the three ansible reserves, which a character class cannot catch:
    # they are spelt exactly like group names and they mean every host, every
    # ungrouped host, and the controller. `--limit all` aims the snapshot play
    # -- whose wrapper prunes to the last ten -- at the whole inventory, so an
    # earlier round blessing `all` as "a NAME; the grammar is not a policy" was
    # blessing the one pattern the grammar was written to keep out.
    for reserved in ("all", "ALL", "ungrouped", "localhost"):
        _fresh_process(rt, "pve_group")
        monkeypatch.setenv("SCR_TRAIN_PVE_GROUP", reserved)
        with pytest.raises(rt.Fail) as exc:
            rt.snapshot_listing()
        assert "ansible reserves" in str(exc.value), reserved
        with pytest.raises(rt.Fail):
            rt.phase_snapshot(SimpleNamespace(go=True), {})
    _fresh_process(rt, "pve_group")
    monkeypatch.setenv("SCR_TRAIN_PVE_GROUP", "a-group")

    # (c) inert twin: both consumers carry THE SAME value, the play as an
    # argument and the listing quoted into the remote command
    asked = []

    monkeypatch.setattr(rt, "run", _attesting_run(rt, asked, listing=True,
                                                  name="cc_other__1"))
    rt.snapshot_listing()
    assert asked and "--limit a-group" in asked[-1], asked
    assert "ansible-playbook" in asked[-1], asked

    played = []
    minted = "cc_pre-bug392-merge__20260922_031500"
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    _phase_zero(monkeypatch, rt, minted, calls=played,
                before=_listing("cc_other__1"),
                after=_listing(minted),
                out=_play_out(minted))
    st = {}
    rt.phase_snapshot(SimpleNamespace(go=True), st)
    assert played and played[0][0][0] == "snapshot-scr.yml"
    assert played[0][1]["limit"] == rt.snapshot_target() == "a-group", played
    assert st["snapshot"]["name"] == minted

    # ...and the plan line says so without naming the machine
    capsys.readouterr()
    rt.phase_snapshot(SimpleNamespace(go=False), {})
    out = capsys.readouterr().out
    assert "--limit %s" % rt.HOST_TOKEN in out and "a-group" not in out, out


def test_a_machine_that_did_not_answer_the_listing_is_still_one_of_the_machines(monkeypatch):
    """R4-L2: an UNREACHABLE host left no block behind, so the group looked like one healthy responder.

    Ansible prints `host | UNREACHABLE! => {...}` for a machine it could not reach -- no rc, a different
    header shape -- and the parser recognised only the rc-bearing one. The intended host being down
    therefore did not reduce the count of answers: a second group member's rc=0 listing was read as the
    one and only answer, and its snapshots vouched for a rollback point the intended machine does not
    hold. A block that did not answer is still a block."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    name = _snap()["snapshot"]["name"]

    # R8-M1: the recap row is where this is settled now, and it carries the
    # two counters that say a machine did not answer. A group whose intended
    # machine was unreachable and whose second member answered reads as
    # `unreachable=1` on the row, which is a refusal -- and the second member's
    # own answer never becomes "the" answer, because the playbook is refused
    # before any section of it is parsed.
    for kw, says in (({"unreachable": 1}, "unreachable=1 failed=0"),
                     ({"failed": 1}, "unreachable=0 failed=1")):
        monkeypatch.setattr(rt, "run", _attesting_run(
            rt, listing=True, name=name, recap=_recap(**kw)))
        with pytest.raises(rt.Fail) as exc:
            rt.snapshot_listing()
        assert says in str(exc.value), (kw, str(exc.value))
        assert "did not answer is not a machine that answered" in str(exc.value)

    # ...and the whole gate refuses on it, rather than reporting the rollback
    # point as present
    monkeypatch.setattr(rt, "run", _attesting_run(
        rt, listing=True, name=name, recap=_recap(unreachable=1)))
    with pytest.raises(rt.Fail) as exc:
        rt.snapshot_listing_problem(_snap())
    assert "unreachable=1" in str(exc.value), str(exc.value)

    # ...and a SECOND member's listing section is a duplicated section, which
    # is the same refusal from the other direction: two machines cannot both
    # answer inside one marked pair
    monkeypatch.setattr(rt, "run", _attesting_run(rt, sections=[
        _facts_section(BEFORE_P), _list_section(BEFORE_P, name),
        _list_section(BEFORE_P, "cc_pre-bug392-server__1"),
        _list_section(AFTER_P, name), _facts_section(AFTER_P)]))
    with pytest.raises(rt.Fail) as exc:
        rt.snapshot_listing()
    assert "more than once" in str(exc.value), str(exc.value)

    # inert twin: one machine, one recap row, and it answered
    monkeypatch.setattr(rt, "run", _attesting_run(rt, listing=True, name=name))
    listing = rt.snapshot_listing()
    names, problem = rt.listed_snapshot_names(listing)
    assert names == [name] and problem is None


def test_the_remote_gate_names_the_repository_and_reads_only_what_succeeded(monkeypatch):
    """R4-L3: `ls-remote` ran with check=False on the combined streams, and nothing said which remote.

    Two holes in one gate. A command that FAILED could still have printed something that parses as a
    ref -- a warning quoting one, a partial answer before the connection dropped -- and stderr is where
    git puts everything that is not an answer, so the gate read one out of the noise. And `origin` is
    whatever this checkout calls origin: a seat pointed at a fork or a mirror passes the comparison
    perfectly while the boxes fetch from somewhere else. The batch pins the host and the repository, the
    seat holds the whole URL, the command has to have exited 0, and its answer is read from stdout."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    assert rt.ORIGIN_EXPECTED["host"] == "github.com"
    assert rt.ORIGIN_EXPECTED["path_suffix"] == "/SidsCompetitiveRounds.git"
    good = {rt.BRANCH: REVIEWED_FULL, "main": MERGE_FULL}
    parents = {MERGE_FULL: [MAIN_FULL, REVIEWED_FULL]}
    trees = {REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: REVIEWED_TREE}
    go = SimpleNamespace(go=True)
    deployed = []
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    monkeypatch.setattr(rt, "_deploy_both", lambda sha, extra=None, st=None, **_kw: deployed.append(sha))
    monkeypatch.setattr(rt, "code_state", lambda host: (True, True, False, ["alias absent"]))
    monkeypatch.setattr(rt, "assert_route_probes", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_health_keys", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_edge_runs_new_code", lambda: None)
    _snapshot_is_listed(monkeypatch, rt)
    st = lambda: dict(_snap(), code_sha=MERGE_FULL, pre_code_old_build=True)

    def refuses(says, **over):
        stub, log = _fake_git(rt, good, parents, trees,
                              **dict({"remote_main": MERGE_FULL}, **over))
        monkeypatch.setattr(rt, "run", stub)
        deployed[:] = []
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(go, st())
        assert says in str(exc.value), (says, str(exc.value))
        assert deployed == [], says
        return str(exc.value)

    # (a) origin is not the URL this seat is configured with -- and neither URL
    # is printed, because this message goes into a transcript
    msg = refuses("not the remote this seat is configured with",
                  origin="https://github.com/ACCOUNT/SomethingElse.git")
    assert "SomethingElse" not in msg and ORIGIN_URL not in msg, msg
    # (b) ...and a seat configured with a URL that is not the pinned repository.
    # A different seat is a different RUN: the seat is read once per process and
    # answered from that reading ever after (R8-H2), so this arm forgets the
    # captured value the way starting the train again would.
    _fresh_process(rt, "origin_url")
    monkeypatch.setenv("SCR_TRAIN_ORIGIN_URL", "https://example.invalid/x/other.git")
    refuses("is not github.com/SidsCompetitiveRounds.git",
            origin="https://example.invalid/x/other.git")
    _fresh_process(rt, "origin_url")
    monkeypatch.setenv("SCR_TRAIN_ORIGIN_URL", ORIGIN_URL)
    # (c) a command that did not succeed is not an answer, however well its
    # output parses
    refuses("did not succeed", remote_rc=128,
            remote_stderr="%s\trefs/heads/main" % MERGE_FULL)
    # (d) ...and a matching ref on STDERR of a successful command is not one
    # either: the gate reads stdout
    refuses("the remote named no refs/heads/main", remote_main="",
            remote_stderr="%s\trefs/heads/main" % MERGE_FULL)

    # inert twin: the pinned repository, a command that succeeded, and the
    # merge on stdout
    stub, log = _fake_git(rt, good, parents, trees, remote_main=MERGE_FULL)
    monkeypatch.setattr(rt, "run", stub)
    deployed[:] = []
    rt.phase_code(go, st())
    assert deployed == [MERGE_FULL]
    assert [c for c in log if "remote get-url origin" in c], log
    assert [c for c in log if "ls-remote" in c], log


def test_every_git_subprocess_the_train_spawns_disables_object_replacement(monkeypatch):
    """R4-L4: the sweep covered the commands that REPORT and left the commands that WRITE.

    `--no-replace-objects` and the environment variable were on the reads whose answer is an
    authentication. But a replacement changes what a command BUILDS as well as what it reports: the
    checkout, the merge and the commit read the objects they are made from, and `rev-parse HEAD`
    reports the result. One door for every git subprocess, so the environment cannot be forgotten by a
    caller, and the option stays on top of it for the authenticating ones."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    good = {rt.BRANCH: REVIEWED_FULL, "main": MAIN_FULL}
    trees = {REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: REVIEWED_TREE}
    stub, log = _fake_git(rt, dict(good), {MERGE_FULL: [MAIN_FULL, REVIEWED_FULL]}, trees,
                          remote_main=MERGE_FULL)
    writing = ("checkout", "merge", "commit", "push")

    def recorder(cmd, **kw):
        # The writing half of the phase, which the read-only stub refuses: it is
        # recorded here with its environment and answered, so the phase runs to
        # the end and every command it spawned can be judged.
        if isinstance(cmd, list) and cmd[0] == "git" and cmd[1] in writing:
            log.append(" ".join(cmd))
            stub.envs.append(kw.get("env"))
            return ""
        if isinstance(cmd, list) and cmd[1:] == ["rev-parse", "HEAD"]:
            log.append(" ".join(cmd))
            stub.envs.append(kw.get("env"))
            good["main"] = MERGE_FULL       # git merge moved it, as the real one does
            return MERGE_FULL
        return stub(cmd, **kw)

    monkeypatch.setattr(rt, "run", recorder)
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    monkeypatch.setattr(rt, "_deploy_both", lambda sha, extra=None, st=None, **_kw: None)
    monkeypatch.setattr(rt, "code_state", lambda host: (True, True, False, ["alias absent"]))
    monkeypatch.setattr(rt, "assert_route_probes", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_health_keys", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_edge_runs_new_code", lambda: None)
    _snapshot_is_listed(monkeypatch, rt)
    rt.phase_code(SimpleNamespace(go=True), dict(_snap(), pre_code_old_build=True))

    # the writing half really ran, and so did the reading half
    for verb in writing + ("rev-parse", "status", "rev-list", "ls-remote"):
        assert [c for c in log if c.split()[1:] and verb in c.split()], (verb, log)
    # EVERY git subprocess carried the environment, and every authenticating one
    # carried the option as well
    seen = 0
    for cmd, env in zip(log, stub.envs):
        parts = cmd.split()
        if parts[0] != "git":
            continue
        seen += 1
        assert (env or {}).get("GIT_NO_REPLACE_OBJECTS") == "1", (cmd, env)
        verb = parts[2] if parts[1] == NO_REPLACE else parts[1]
        if verb in ("rev-parse", "rev-list", "merge-base", "merge-tree", "ls-remote", "cat-file"):
            if parts[1:] == ["rev-parse", "HEAD"]:
                continue        # reads this repo's own HEAD back, not an authentication
            assert parts[1] == NO_REPLACE, cmd
    assert seen >= 8, log


def test_the_mergeability_check_writes_its_objects_where_they_are_deleted(monkeypatch, tmp_path):
    """R7-L4 (R3-L3): the frozen rule says this train writes nothing outside its state file.

    Two clauses were false as written, and the round before answered the row by conceding them in the
    notes rather than by making the code meet them. This is the second: `git merge-tree --write-tree`
    synthesizes the merge result and WRITES the trees into an object store, and the store it was given
    was this repository's -- unreferenced objects, collected eventually, but written by a run without
    --go. A rule a tool cannot keep is not a rule, so the objects now go to a temporary directory that
    is removed whatever the call does, with the repository's own store handed back as a read-only
    alternate so both sides can still be READ.

    (The first clause is the listing capture, which now writes only inside the state directory; its own
    test is `test_the_capture_writes_only_where_it_was_told_it_may`.)"""
    import tempfile as _tempfile
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    doc = rt.__doc__
    assert "merge-tree --write-tree" in doc, doc
    assert "GIT_OBJECT_DIRECTORY" in doc, doc
    assert "receives no objects" in doc, doc
    # the sentence the caveat used to qualify is still there, unqualified now
    assert "no ref moves, nothing is committed, pushed, deployed or migrated" in doc, doc

    # ...and the code does it. The environment of the merge-tree call is
    # captured from the REAL expected_merge_tree, through the real git() door.
    seen = {}
    objects = str(tmp_path / "objects")

    def _run(cmd, **kw):
        joined = " ".join(cmd) if isinstance(cmd, list) else cmd
        if "--is-ancestor" in joined:
            raise rt.Fail("not an ancestor")          # force the merging branch
        if "--git-path" in joined:
            return objects
        if "merge-tree" in joined:
            seen["env"] = kw.get("env") or {}
            seen["dir"] = (kw.get("env") or {}).get("GIT_OBJECT_DIRECTORY")
            seen["existed"] = os.path.isdir(seen["dir"] or "")
            return "c" * 40
        raise _NoCommand(joined)

    monkeypatch.setattr(rt, "run", _run)
    tree, how = rt.expected_merge_tree(MAIN_FULL, REVIEWED_FULL)
    assert tree == "c" * 40
    # (a) the objects were aimed somewhere else, and that somewhere EXISTED
    # while the command ran -- a variable pointing at nothing would have sent
    # them back to the default store
    assert seen["dir"] and seen["existed"], seen
    assert os.path.abspath(seen["dir"]) != os.path.abspath(objects), seen
    # (b) ...with the repository's own store readable, or the merge could not
    # have read either side
    assert seen["env"].get("GIT_ALTERNATE_OBJECT_DIRECTORIES") == objects, seen
    # (c) ...and the replacement door is still shut on the same command
    assert seen["env"].get("GIT_NO_REPLACE_OBJECTS") == "1", seen
    # (d) the temporary directory is GONE afterwards: "deleted after it" is the
    # claim, and a directory still on disk is that claim being false
    assert not os.path.exists(seen["dir"]), seen["dir"]
    assert "received no objects" in how, how

    # (e) ...and it is deleted on the FAILING path too, which is the one an
    # author forgets
    def _broken(cmd, **kw):
        joined = " ".join(cmd) if isinstance(cmd, list) else cmd
        if "--is-ancestor" in joined:
            raise rt.Fail("not an ancestor")
        if "--git-path" in joined:
            return objects
        raise rt.Fail("the merge could not be made")

    monkeypatch.setattr(rt, "run", _broken)
    before = set(os.listdir(_tempfile.gettempdir()))
    with pytest.raises(rt.Fail):
        rt.expected_merge_tree(MAIN_FULL, REVIEWED_FULL)
    left = [d for d in set(os.listdir(_tempfile.gettempdir())) - before
            if d.startswith("scr-train-mergetree-")]
    assert left == [], left


def test_the_train_refuses_to_run_when_no_batch_is_named(monkeypatch, capsys):
    """R2-L1: an unnamed batch selected one that had already shipped, and that entry is UNBOUND.

    `--batch` carried a default, so `plan`, `check` and `run --go` typed without it drove a train nobody
    chose -- an entry written before the provenance binding existed, whose own plan line says UNBOUND and
    whose branch is whatever that mutable ref names today. The documented commands omitted the flag too,
    so following the docstring was the way to hit it. There is no default now, the module arrives bound
    to no batch at all, and the refusal comes before anything is selected, read or probed."""
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

    # the inert twin: a NAMED batch still binds and still runs
    real_select(ABSENT_BATCH)
    assert rt.BATCH_NAME == ABSENT_BATCH and rt.BRANCH == "claude/bug392-merge"


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
    assert ban == "NOT EXISTS (SELECT 1 FROM player_bans b WHERE b.steam_id = {a}.steam_id AND b.unbanned_at IS NULL)"
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
    monkeypatch.setattr(main, "_pc_verified_actor", actor)
    monkeypatch.setattr(main, "_pc_settings_of", settings_of)

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
    assert "raise _PcPortraitMissing()" in inspect.getsource(main.internal_pc_face_preview)
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
    assert "def index_state(host):" in src and "FROM pg_indexes WHERE schemaname = 'public'" in src
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


def _merging_git(rt, **kw):
    """(`run` stub, log) that also lets the WRITING half of the code phase run.

    `_fake_git` answers the read-only gates and raises on anything else, which
    is what most of these tests want. This one additionally accepts the
    checkout, the merge, the commit, `rev-parse HEAD` and the push, and records
    them in the same log -- so the ORDER of the writing commands against the
    gates can be read. Nothing is executed and nothing touches a network."""
    inner, log = _fake_git(rt, **kw)

    def _run(cmd, **kw2):
        argv = [c for c in cmd if c != NO_REPLACE] if isinstance(cmd, list) else cmd
        head = argv[:2] if isinstance(argv, list) else []
        if head in (["git", "checkout"], ["git", "commit"], ["git", "push"]) or (
                head == ["git", "merge"]):
            log.append(" ".join(cmd))
            return ""
        if argv[:3] == ["git", "rev-parse", "HEAD"]:
            log.append(" ".join(cmd))
            return MERGE_FULL
        return inner(cmd, **kw2)

    _run.envs = inner.envs
    return _run, log


def test_the_two_per_box_deploy_limits_are_seat_values_checked_by_one_grammar(monkeypatch, capsys):
    """R5-H1: the deploy play's two `--limit` selectors were literals in the train.

    They name inventory groups -- the same class as the snapshot target, which was moved to the seat two
    rounds ago for exactly this reason -- so they travelled into the train file, into every transcript
    printed from it, into the tests, and into every review bundle built out of those. The scan that was
    supposed to catch that kept a hand-written list of needles and the list did not name them, so the
    bundle reported zero inventory identifiers while carrying two.

    They are seat values now, read through the same door as the controller and the snapshot target,
    checked by the same grammar before they can reach a command line, handed to the play as quoted
    arguments, and named in deploy ORDER so the authoritative box is never left behind the box that
    serves the routed reads."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    assert rt.DEPLOY_LIMIT_KEYS == ("primary_limit", "standby_limit")
    for key in rt.DEPLOY_LIMIT_KEYS:
        assert key in rt.IDENTIFIERS

    calls = []
    attested = []
    _attested(monkeypatch, rt, seen=attested)
    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(rt, calls))
    monkeypatch.setattr(rt, "assert_control", lambda host: None)

    # (a) the values the play is handed are the SEAT's, and moving the seat
    # moves them -- which a literal could not do. The PHASE attests before its
    # first mutation, and the deploy is held to that attestation: it never
    # re-attests, which would replace the answer it is compared against with
    # whatever the selectors resolve to now (R9-M2).
    rt.attest_deploy_selectors()
    rt._deploy_both(MERGE_FULL)
    assert len(attested) == 1, attested
    assert [c[1] for c in calls] == [SEAT_PRIMARY_LIMIT, SEAT_STANDBY_LIMIT], calls
    calls[:] = []
    # A moved seat is a new RUN: the seat is read once per process and answered
    # from that first reading ever after (R8-H2), so each arm below forgets the
    # captured value the way starting the train again would.
    _fresh_process(rt, "primary_limit")
    monkeypatch.setenv("SCR_TRAIN_PRIMARY_LIMIT", "other-primary")
    rt._deploy_both(MERGE_FULL)
    assert [c[1] for c in calls] == ["other-primary", SEAT_STANDBY_LIMIT], calls
    _fresh_process(rt, "primary_limit")
    monkeypatch.setenv("SCR_TRAIN_PRIMARY_LIMIT", SEAT_PRIMARY_LIMIT)

    # (b) the reddening arm: a seat that has not been told refuses and names
    # the key to set -- and it refuses before EITHER box is deployed to, not
    # after the primary has already changed. The four bound values are one
    # read, taken at the top of the step, so a key the seat cannot answer for
    # stops the step rather than the second half of it.
    calls[:] = []
    _fresh_process(rt, "standby_limit")
    monkeypatch.delenv("SCR_TRAIN_STANDBY_LIMIT")
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(MERGE_FULL)
    assert "SCR_TRAIN_STANDBY_LIMIT" in str(exc.value), str(exc.value)
    assert calls == [], calls
    _fresh_process(rt, "standby_limit")
    monkeypatch.setenv("SCR_TRAIN_STANDBY_LIMIT", SEAT_STANDBY_LIMIT)

    # (c) ...and they go through the ONE grammar door, so a pattern or one of
    # ansible's reserved names is refused here exactly as it is for the
    # snapshot target
    for bad, says in (("a:b", "not a plain name"), ("*", "not a plain name"),
                      ("all", "ansible reserves"), ("localhost", "ansible reserves")):
        calls[:] = []
        _fresh_process(rt, "primary_limit")
        monkeypatch.setenv("SCR_TRAIN_PRIMARY_LIMIT", bad)
        with pytest.raises(rt.Fail) as exc:
            rt._deploy_both(MERGE_FULL)
        assert says in str(exc.value), (bad, str(exc.value))
        assert calls == [], (bad, calls)
    _fresh_process(rt, "primary_limit")
    monkeypatch.setenv("SCR_TRAIN_PRIMARY_LIMIT", SEAT_PRIMARY_LIMIT)

    # (d) inert twin: the transcript of a deploy prints the neutral token, not
    # the selector -- a review bundle is built out of these transcripts
    capsys.readouterr()
    rt._deploy_both(MERGE_FULL)
    out = capsys.readouterr().out
    assert rt.HOST_TOKEN in out, out
    assert SEAT_PRIMARY_LIMIT not in out and SEAT_STANDBY_LIMIT not in out, out


def test_a_snapshot_name_is_the_exact_form_the_wrapper_mints(monkeypatch, tmp_path, capsys):
    """R5-H2 and R5-M2: `cc_` plus anything is a SHAPE, and a shape is not a name.

    The wrapper builds one form. Its source is `LABEL=$(echo "$ARG" | tr -c 'a-zA-Z0-9_-' '_' |
    cut -c1-40)` and then `NAME="cc_${LABEL}_$(date +%Y%m%d_%H%M%S)"` -- and because `echo` puts a
    newline after the label and `tr` turns that newline into an underscore, the label always ends in one
    and the minted name always carries TWO of them before the stamp. The stamp is eight digits, an
    underscore, six digits.

    Two defects rested on the wider shape. The capture treated every `cc_[A-Za-z0-9_.:-]+` token as safe
    and copied it verbatim, so a line carrying `cc_<an identifier>__<digits>` was written into the
    review bundle as a valid record. And the binding predicate tested a PREFIX, so `cc_<label>_fake`
    -- an old or unrelated snapshot the play happened to print -- satisfied the rollback prerequisite
    and was recorded with a fresh timestamp. One compiled pattern now answers for the extractor, the
    capture's record line and the binding predicate, so the capture can only ever write a name the
    state would bind."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    monkeypatch.setattr(rt, "STATE_PATH", str(tmp_path / "state.json"))
    real = "cc_pre-bug392-merge__20260922_030000"

    # (a) one pattern for all three consumers
    assert rt.cc_name_pattern() in rt.record_line_re().pattern
    assert rt.cc_name_re().pattern.lstrip("^").startswith("cc_")

    # (b) the reddening arm: every near-miss is not a name, in the extractor
    # and in the binding predicate alike
    for near in ("cc_pre-bug392-merge_fake",
                 "cc_pre-bug392-merge__fake",
                 "cc_pre-bug392-merge__2026092_030000",      # seven digits
                 "cc_pre-bug392-merge__20260922_03000",      # five digits
                 "cc_pre-bug392-merge__20260922-030000",     # wrong separator
                 "cc_pre-bug392-merge_20260922_030000",      # one underscore
                 "cc_pre-bug392-merge-2__20260922_030000",   # a different label
                 "cc_pre-bug392-server__20260922_030000",    # another batch
                 # a hostile token carrying an identifier where the label goes.
                 # The fixture stands in for a real machine or group name: the
                 # literal one may not be written into a tracked file.
                 "cc_a-machine__20260922_030000",
                 # R6-M2: the stamp is eight ASCII digits, an underscore and
                 # six more. `\\d` is UNICODE-wide in Python, so every one of
                 # these satisfied it -- Devanagari, Arabic-Indic and
                 # fullwidth digits are digits to `\\d` and are not what the
                 # wrapper's `date +%Y%m%d_%H%M%S` can ever emit.
                 u"cc_pre-bug392-merge__२०२००९२२_030000",
                 u"cc_pre-bug392-merge__2026092٢_030000",
                 u"cc_pre-bug392-merge__20260922_03000٠"):
        assert rt.cc_names("  `-> %s 2026-09-22 03:00:01" % near) == [], near
        assert rt._snapshot_name_binds(near) is False, near
    # ...said of the grammar itself as well as of its verdicts, so a widening
    # cannot be reintroduced somewhere the fixtures above do not reach
    assert "\\d" not in rt._CC_STAMP and "[0-9]" in rt._CC_STAMP, rt._CC_STAMP
    assert "\\d" not in rt._LISTED_AT.pattern, rt._LISTED_AT.pattern
    assert "\\d" not in rt.record_line_re().pattern, rt.record_line_re().pattern

    # (c) the same tokens reaching the CAPTURE leave a count and nothing else
    # (the listing ends with pct's closing `current` entry, as every whole
    # listing does -- R10-M1 -- and that line is dropped and counted too)
    body = (" `-> cc_a-machine__20260922_030000 2026-09-22 03:00:01  auto\n"
            " `-> cc_pre-bug392-merge_fake 2026-09-22 03:00:02  auto\n"
            " `-> %s 2026-09-22 03:00:03  auto\n"
            "  `-> current                   You are here!" % real)
    dropped, lines = _printed_capture(rt, capsys, _listing_raw(body))
    written = "\n".join(lines)
    assert "a-machine" not in written, written
    assert "_fake" not in written, written
    assert dropped == 3 and "DROPPED 3" in written, (dropped, written)

    # (d) inert twin: the real minted form is a record, it binds, and the gate
    # reads it
    assert rt.cc_names(" `-> %s 2026-09-22 03:00:03  auto" % real) == [real]
    assert rt._snapshot_name_binds(real) is True
    assert "SNAPSHOT name=%s taken=2026-09-22 03:00:03 zone=none" % real in written
    assert "GATE names=1 usable=yes" in written

    # (e) and the play that mints one of the near-misses is not recorded as
    # having taken this train's rollback point
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    _phase_zero(monkeypatch, rt, real, out=_play_out("cc_pre-bug392-merge_fake"))
    with pytest.raises(rt.Fail) as exc:
        rt.phase_snapshot(SimpleNamespace(go=True), {})
    assert "reported no cc_pre-bug392-merge__* snapshot name" in str(exc.value), str(exc.value)

    # (f) R6-M2, the reddening arm the grammar cannot reach: an EXACT name of
    # this batch's own label that the container was ALREADY holding. It passes
    # the pattern, the extractor, the listing and the binding predicate --
    # every question above says yes -- and the round before stamped it with the
    # current moment and recorded it as this train's fresh rollback point. A
    # play that took nothing reports failed=0 and prints the name it found.
    _phase_zero(monkeypatch, rt, real, before=_listing(real),
                after=_listing(real), out=_play_out(real))
    st = {}
    with pytest.raises(rt.Fail) as exc:
        rt.phase_snapshot(SimpleNamespace(go=True), st)
    assert "ALREADY in the container's listing" in str(exc.value), str(exc.value)
    assert "not restamped" in str(exc.value), str(exc.value)
    assert st == {}, st

    # (g) ...and a play whose name the container does not hold afterwards is
    # not recorded either: a name in a play's output is a claim, and the
    # listing is the fact
    _phase_zero(monkeypatch, rt, real, before=_listing(None),
                after=_listing(None), out=_play_out(real))
    with pytest.raises(rt.Fail) as exc:
        rt.phase_snapshot(SimpleNamespace(go=True), {})
    assert "does not hold it" in str(exc.value), str(exc.value)

    # (h) inert twin: a name minted BETWEEN the two listings -- absent before,
    # present after -- is recorded, with the provenance that says so, and the
    # freshness the later gates read comes from the before-listing rather than
    # from the moment the record was written
    _phase_zero(monkeypatch, rt, real)
    st = {}
    rt.phase_snapshot(SimpleNamespace(go=True), st)
    assert st["snapshot"]["name"] == real
    assert st["snapshot"]["minted"]["absent_before"] is True
    assert st["snapshot"]["minted"]["listed_after"] is True
    assert st["snapshot"]["minted"]["before_count"] == 0
    assert st["snapshot"]["minted"]["after_count"] == 1
    assert rt.snapshot_record_problem(st) is None
    # and a record whose minting moment is outside the window is refused, which
    # is what makes the provenance the thing the age is measured from
    stale = dict(st["snapshot"])
    import datetime as _dt
    stale["minted"] = dict(stale["minted"],
                           before_utc=(_dt.datetime.now(_dt.timezone.utc)
                                       - _dt.timedelta(hours=25)).isoformat(timespec="seconds"))
    assert "24 hours" in rt.snapshot_record_problem({"snapshot": stale})


def test_the_recorded_snapshot_binds_the_machine_it_was_taken_for(monkeypatch):
    """R5-M1: the record bound this train, this batch, this label and this moment -- never a machine.

    Every one of those four questions holds just as well for a snapshot sitting on a box the seat no
    longer names. The controller and the target were re-read on every resume, so a seat repointed
    between phase 0 and phase 4 -- a corrected inventory, an environment override, an edit to the seat
    file -- let a same-named snapshot on a DIFFERENT container satisfy the rollback prerequisite, and
    the deploy proceeded with nothing to roll back to.

    Phase 0 records the sha256 of each bound seat value, never the value, plus one of the seat file. The
    listing gate and the rollback prerequisite re-read them and refuse, naming the key and the phase."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    assert rt.SEAT_BINDING_KEYS == ("controller", "pve_group", "primary_limit",
                                    "standby_limit", "play_dir")

    # (a) what phase 0 writes is digests, and the values are not in it -- plus
    # the digest of the host the PLAY's own recap named, which is the identity
    # the selector digests cannot carry: a selector is a name for a set
    # somebody else maintains, and an unchanged name can be remapped from one
    # machine to another without this seat touching anything.
    listed = []
    fresh = "cc_pre-bug392-merge__20260922_031500"
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    _phase_zero(monkeypatch, rt, fresh)
    st = {}
    rt.phase_snapshot(SimpleNamespace(go=True), st)
    recorded = st["snapshot"]["seat"]
    assert set(recorded) == set(rt.SEAT_BINDING_KEYS) | {"conf", "box", "responder_label"}
    for value in (SEAT_CONTROLLER, SEAT_PVE_GROUP, SEAT_PRIMARY_LIMIT, SEAT_STANDBY_LIMIT,
                  SEAT_PLAY_HOST):
        assert value not in repr(recorded), value
    assert recorded == _seat_digests(), recorded
    # R7-M1: the identity is what the BOX said about itself -- its endpoint and
    # the sha256 of its own machine-id -- and the label the play's recap
    # printed is kept as a digest for the log. A label is a name somebody else
    # maintains; six rounds recorded and compared exactly that.
    # R8-H5: the endpoint is recorded as its CLASS. The address the box
    # reported is a machine address like any other and a state file -- which
    # `check` prints -- is not a place for one.
    assert recorded["box"] == {"addr": OTHER_TOKEN, "id": SEAT_BOX_ID}, recorded
    assert SEAT_BOX_ENDPOINT not in repr(recorded), recorded
    assert len(recorded["box"]["id"]) == 64

    # (a2) R6-M1: the values the play was HANDED and the values that were
    # DIGESTED are one read. A seat that answers differently on every read
    # makes the difference visible: while the phase read the seat again to
    # record it, the digest it wrote down was of a value nothing had ever run
    # under, and every later gate then compared against that.
    drift = {"n": 0}
    real_require = rt.require_identifier

    def drifting(key):
        if key == "pve_group":
            drift["n"] += 1
            return "a-group-%d" % drift["n"]
        return real_require(key)

    monkeypatch.setattr(rt, "require_identifier", drifting)
    played = []
    _phase_zero(monkeypatch, rt, fresh, calls=played)
    st2 = {}
    rt.phase_snapshot(SimpleNamespace(go=True), st2)
    handed = played[0][1]["limit"]
    import hashlib as _h
    assert st2["snapshot"]["seat"]["pve_group"] == _h.sha256(handed.encode("utf-8")).hexdigest(), (
        handed, drift)
    assert drift["n"] == 1, drift        # read once, used twice
    monkeypatch.setattr(rt, "require_identifier", real_require)

    # (a3) ...and the machine the play answered from is what a listing is
    # compared against. A listing whose answering block names a different host
    # is another box's snapshot list, and it is refused before any name in it
    # is trusted -- the selector has not changed, it resolves elsewhere.
    moved = dict(st["snapshot"])

    # the reddening arms, and the one the round before could not have: the
    # LABEL is held CONSTANT and the machine underneath it changes. An alias
    # repointed at another installation answers under the same name, so a gate
    # that compares the name cannot see it at all.
    relabelled = _listing(fresh, responder="b-machine")
    other_box = _listing(fresh, box_id="f" * 64)
    other_where = _listing(fresh, endpoint=rt.PRIMARY_TOKEN)

    said = rt.responder_problem(moved, other_box)
    assert said and "boot fingerprint differs" in said, said
    assert SEAT_BOX_ID not in said and "f" * 64 not in said, said
    said = rt.responder_problem(moved, other_where)
    assert said and "different endpoint" in said, said
    assert SEAT_BOX_ENDPOINT not in said, said
    monkeypatch.setattr(rt, "snapshot_listing", lambda values=None: other_box)
    problem, _how = rt.snapshot_listing_problem({"snapshot": moved})
    assert problem and "boot fingerprint differs" in problem, problem

    # ...and the INERT TWIN that says the comparison is about machines and not
    # about names: the label changes and both facts hold -- an alias rename is
    # not an identity change, and this passes.
    assert rt.responder_problem(moved, relabelled) is None,         "a renamed alias over the same installation is not a different machine"
    same = _listing(fresh)
    assert rt.responder_problem(moved, same) is None
    # ...and a record that carries no box identity at all is unbound, never
    # bound -- including one carrying only the old label digest
    for gone in ("box",):
        no_box = dict(moved, seat={k: v for k, v in moved["seat"].items() if k != gone})
        assert "does not say WHICH MACHINE" in rt.responder_problem(no_box, same), gone
    # ...and a listing whose machine stated nothing is not a match either
    silent = _listing(fresh, identity=None)
    assert "did not state its own identity" in rt.responder_problem(moved, silent)

    # (b) the reddening arm: the seat is repointed and the new target's listing
    # carries a snapshot of the SAME NAME. It is refused, before any listing
    # call is made at all, naming the key and the phase.
    bound = _snap()
    monkeypatch.setattr(rt, "snapshot_listing",
                        lambda values=None: listed.append("asked") or
                        _listing(bound["snapshot"]["name"]))
    for key, env in (("pve_group", "SCR_TRAIN_PVE_GROUP"),
                     ("controller", "SCR_TRAIN_CONTROLLER"),
                     ("primary_limit", "SCR_TRAIN_PRIMARY_LIMIT"),
                     ("standby_limit", "SCR_TRAIN_STANDBY_LIMIT")):
        was = rt.identifier(key)
        # A repointed seat is a LATER run reading a changed file or
        # environment, never a second read inside one run (R8-H2). Each arm
        # moves ONE key and puts it back, so the arm after it is not reading a
        # seat three keys of which have already moved.
        _fresh_process(rt, key)
        monkeypatch.setenv(env, "b-" + was)
        listed[:] = []
        problem, how = rt.snapshot_listing_problem(bound)
        assert problem and repr(key) in problem, (key, problem)
        assert "the listing gate" in problem, (key, problem)
        assert listed == [], (key, "the listing was asked before the seat was checked")
        assert was not in problem and ("b-" + was) not in problem, problem
        # ...and the phase-4 prerequisite refuses on the same record
        problem = rt.snapshot_record_problem(bound)
        assert problem and repr(key) in problem and "the rollback prerequisite" in problem
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(SimpleNamespace(go=True), dict(bound))
        assert repr(key) in str(exc.value), (key, str(exc.value))
        assert listed == [], key
        # ...and back, so the arm after this one moves ONE key rather than
        # reading a seat every earlier arm has already left moved
        _fresh_process(rt, key)
        monkeypatch.setenv(env, was)
        assert rt.identifier(key) == was

    # (c) a record written before this binding existed is UNBOUND, never bound
    old_shape = _snap()
    del old_shape["snapshot"]["seat"]
    problem = rt.snapshot_record_problem(old_shape)
    assert problem and "no seat binding" in problem, problem
    problem, _how = rt.snapshot_listing_problem(old_shape)
    assert problem and "no seat binding" in problem, problem
    assert listed == [], "an unbound record must not reach the listing either"

    # (d) inert twin: an untouched seat -- the record binds, the listing is
    # asked, and the gate passes
    listed[:] = []
    assert rt.snapshot_record_problem(bound) is None
    problem, how = rt.snapshot_listing_problem(bound)
    assert problem is None, problem
    assert listed == ["asked"], listed


def test_the_merge_is_authenticated_and_the_remote_checked_before_the_push(monkeypatch, capsys):
    """R5-L3: a fresh run pushed in the same breath as the merge, ahead of every gate that could refuse it.

    The push was the fourth entry of a list the phase ran straight through, so the remote was written to
    before anything had asked whether the merge just made is the reviewed content and before anything
    had asked whether `origin` is the repository the boxes clone. Every refusal that exists to stop a
    bad deploy landed after the one step that cannot be taken back.

    And `origin` has two URLs. `remote.origin.pushurl`, when it is set, is where a push goes, so a check
    that reads only the fetch URL proves the merge was authenticated against one repository while the
    push landed in another."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    go = SimpleNamespace(go=True)
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    monkeypatch.setattr(rt, "code_state", lambda host: (True, True, False, ["alias absent"]))
    monkeypatch.setattr(rt, "assert_route_probes", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_health_keys", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_edge_runs_new_code", lambda: None)
    deployed = []
    monkeypatch.setattr(rt, "_deploy_both", lambda sha, extra=None, st=None, **_kw: deployed.append(sha))
    _snapshot_is_listed(monkeypatch, rt)
    refs = {rt.BRANCH: REVIEWED_FULL, "main": MAIN_FULL}
    parents = {MERGE_FULL: [MAIN_FULL, REVIEWED_FULL]}
    trees = {REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: REVIEWED_TREE}

    def fresh_state():
        return dict(_snap(), pre_code_old_build=True)

    # (a) the reddening arm: a second push URL. The phase refuses, and the push
    # is not among the commands that ran.
    stub, log = _merging_git(rt, refs=dict(refs), parents=parents, trees=trees,
                             remote_main=MERGE_FULL,
                             pushurl="https://github.com/ACCOUNT/Elsewhere.git")
    monkeypatch.setattr(rt, "run", stub)
    deployed[:] = []
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, fresh_state())
    assert "not the remote this seat is configured with" in str(exc.value), str(exc.value)
    assert "Elsewhere" not in str(exc.value), str(exc.value)
    assert not [c for c in log if c.startswith("git push")], log
    assert deployed == [], deployed

    # (a2) R6-L3: `origin` may carry SEVERAL push URLs and git writes to every
    # one of them. `--get` answers with the LAST value, so a repository
    # configured with an unintended destination FIRST and the expected one last
    # passed the check exactly -- the gate read the value it was hoping for --
    # and `git push origin main` then wrote to both. Every configured value is
    # read, and this arm is the ordering that used to slip through.
    stub, log = _merging_git(rt, refs=dict(refs), parents=parents, trees=trees,
                             remote_main=MERGE_FULL,
                             pushurl=["https://github.com/ACCOUNT/Elsewhere.git", ORIGIN_URL])
    monkeypatch.setattr(rt, "run", stub)
    deployed[:] = []
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, fresh_state())
    assert "not the remote this seat is configured with" in str(exc.value), str(exc.value)
    assert "Elsewhere" not in str(exc.value), str(exc.value)
    assert not [c for c in log if c.startswith("git push")], log
    assert deployed == [], deployed
    # ...and the command that was used to read them is the multi-valued one
    assert [c for c in log if "--get-all remote.origin.pushurl" in c], log

    # (b) ...and a merge whose TREE is not the reviewed content refuses before
    # the push as well, which is the ordering this finding is about
    stub, log = _merging_git(rt, refs=dict(refs), parents=parents,
                             trees={REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: OTHER_TREE},
                             remote_main=MERGE_FULL)
    monkeypatch.setattr(rt, "run", stub)
    with pytest.raises(rt.Fail):
        rt.phase_code(go, fresh_state())
    assert not [c for c in log if c.startswith("git push")], log

    # (c) inert twin: no pushurl, the reviewed tree, the pinned remote -- the
    # push IS reached, and it comes after the commit, after the authentication
    # read and after the remote check
    stub, log = _merging_git(rt, refs=dict(refs), parents=parents, trees=trees,
                             remote_main=MERGE_FULL)
    monkeypatch.setattr(rt, "run", stub)
    deployed[:] = []
    rt.phase_code(go, fresh_state())
    assert deployed == [MERGE_FULL], deployed
    push = [i for i, c in enumerate(log) if c.startswith("git push")]
    assert len(push) == 1, log
    commit = [i for i, c in enumerate(log) if c.startswith("git commit")]
    parents_read = [i for i, c in enumerate(log) if "rev-list" in c]
    get_url = [i for i, c in enumerate(log) if "remote get-url origin" in c]
    config = [i for i, c in enumerate(log) if "remote.origin.pushurl" in c]
    assert commit and parents_read and get_url and config
    assert push[0] > commit[0], log
    assert push[0] > parents_read[0], log
    assert push[0] > get_url[0] and push[0] > config[0], log

    # (d) and the plan arm says the same order without running any of it
    capsys.readouterr()
    rt.phase_code(SimpleNamespace(go=False), fresh_state())
    joined = capsys.readouterr().out
    assert "then authenticate the merge and check the remote" in joined, joined
    assert joined.index("git commit") < joined.index("git push origin main"), joined


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


def test_the_push_url_gate_asks_git_where_a_push_would_really_go(monkeypatch):
    """R7-L2 (R6-L3): every configured literal can equal the pinned URL and the push still land elsewhere.

    The gate read `remote.origin.url` and `remote.origin.pushurl` out of the configuration. Those are
    the values somebody wrote down; they are not where `git push` writes. `url.<base>.pushInsteadOf`
    rewrites a destination at push time, and no reading of the raw keys can see it. So git is asked,
    with the verb whose whole job is to expand that rewriting -- and the enumeration has to have
    SUCCEEDED, because a command that failed answers with nothing and nothing is not "no other
    destination"."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)

    def answering(effective, rc=0):
        def _run(cmd, **kw):
            joined = " ".join(cmd) if isinstance(cmd, list) else cmd
            if "get-url --push --all" in joined:
                if rc:
                    raise rt.Fail("command failed (rc=%d):\nfatal: no such remote" % rc)
                return "\n".join(effective)
            if "remote get-url origin" in joined:
                return ORIGIN_URL
            if "config --get-all" in joined:
                return ORIGIN_URL if joined.endswith("remote.origin.url") else ""
            raise _NoCommand(joined)
        return _run

    # (a) inert twin: one effective destination, and it is the pinned one
    monkeypatch.setattr(rt, "run", answering([ORIGIN_URL]))
    rt.assert_origin_is_the_expected_remote()

    # (b) the reddening arm the raw keys cannot see: every literal equals the
    # pinned URL and the effective push destination is somewhere else
    monkeypatch.setattr(rt, "run", answering(["https://example.invalid/elsewhere.git"]))
    with pytest.raises(rt.Fail) as exc:
        rt.assert_origin_is_the_expected_remote()
    assert "1 destination(s)" in str(exc.value), str(exc.value)
    assert "expands the push-time rewriting" in str(exc.value), str(exc.value)

    # (c) two destinations, the pinned one among them: git writes to every one
    monkeypatch.setattr(rt, "run",
                        answering(["https://example.invalid/elsewhere.git", ORIGIN_URL]))
    with pytest.raises(rt.Fail) as exc:
        rt.assert_origin_is_the_expected_remote()
    assert "2 destination(s)" in str(exc.value), str(exc.value)

    # (d) the enumeration did not succeed: an empty answer is NOT an empty set
    monkeypatch.setattr(rt, "run", answering([], rc=128))
    with pytest.raises(rt.Fail) as exc:
        rt.assert_origin_is_the_expected_remote()
    assert "did not succeed" in str(exc.value), str(exc.value)
    assert "an unknown destination is not an empty one" in str(exc.value), str(exc.value)

    # ...and no URL is printed in any of those refusals: they go into a
    # transcript a review bundle is built from
    for arm, rc in ((["https://example.invalid/elsewhere.git"], 0), ([], 128)):
        monkeypatch.setattr(rt, "run", answering(arm, rc=rc))
        with pytest.raises(rt.Fail) as exc:
            rt.assert_origin_is_the_expected_remote()
        assert ORIGIN_URL not in str(exc.value), str(exc.value)
        assert "example.invalid" not in str(exc.value), str(exc.value)


def test_each_per_box_selector_is_attested_to_its_box_before_anything_is_mutated(monkeypatch):
    """R7-M2, R7-L3 and R4-L3 (R6-M3): a key NAME is not evidence about a machine, and neither is a second probe.

    `primary_limit` and `standby_limit` were read, grammar-checked and handed to the play in that order,
    and nothing anywhere asked which box each one actually resolves to. With the two values swapped the
    standby is deployed first and the primary second: both plays report failed=0, both boxes end on the
    new build, and the ordering that exists so the authoritative box is never left behind the box
    serving the routed reads (#266) is inverted with nothing reporting it.

    Attesting the selectors fixed half of it. The other half is that the attestation and the plays were
    two INDEPENDENT resolutions of the inventory: correct at both probes and swapped in between, the
    standby is deployed first, the still-old primary passes the liveness check in the middle, and both
    final probes pass. So each play comes back with the box's own statement of who it is, in the same
    ssh invocation, and the PRIMARY's is checked before the standby's play is started.

    And the attestation happens before ANY mutation on every path -- `--from code` and a phase 0 that
    skipped on a valid snapshot included -- which is asserted from a recorded call SEQUENCE rather than
    from where a line sits in a function."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    asked = []

    def answering(addresses, fingerprints=None, second_fact="", recap=None, plays=None):
        """A controller answering the ONE attested playbook for `addresses[limit]`.

        Both the selector and the token are read OUT OF THE COMMAND. The
        selector, because `--limit <value>` is the only thing in the invocation
        that says which key is being asked; the token, because the train mints
        a fresh one per invocation and the answer has to echo THAT one -- a
        fixture answering with a constant would make the binding unobservable
        and the arm that removes it would redden nothing (#342).

        `plays` maps a selector to the (address, fingerprint) its DEPLOY
        invocations resolve to, when that differs from what its probes resolve
        to -- the inventory moving between the read-only probe and the play.
        The status is the process's (R9-M1): an unreachable host is 4, a gate
        that refused is 2."""
        fingerprints = fingerprints or {SEAT_PRIMARY_LIMIT: PRIMARY_BOX_ID,
                                        SEAT_STANDBY_LIMIT: STANDBY_BOX_ID}
        import re as _re

        def _answer(cmd, **kw):
            joined = " ".join(cmd) if isinstance(cmd, list) else cmd
            asked.append(joined)
            found = _re.search(r"-e scr_nonce=([0-9a-f]{32})", joined)
            nonce = found.group(1) if found else NONCE
            for limit, addr in addresses.items():
                if "--limit %s " % limit not in joined + " ":
                    continue
                if addr is None:
                    return _attested_out(nonce=nonce, recap=_recap(unreachable=1)), 4
                box_id = fingerprints[limit]
                ref = _re.search(r"scr_deploy_ref=([0-9a-f]{40})", joined)
                if ref and plays is not None and limit in plays:
                    # the inventory as the PLAY resolves it, which an arm moves
                    # away from what the probes saw
                    addr, box_id = plays[limit]
                # R9-M2: the gate, as the box runs it -- sha256 of the token
                # and its own fingerprint against the digest the train sent,
                # and its own address against the one it sent
                gate = _re.search(r"-e scr_expect_id=([0-9a-f]{64}) -e scr_expect_addr=(\S+)",
                                  joined)
                middle = ""
                if gate:
                    mine = hashlib.sha256(("%s:%s" % (nonce, box_id)).encode("ascii")).hexdigest()
                    if gate.group(1) != mine or gate.group(2) != addr:
                        return (('        "SCR-FACTS-BEGIN BEFORE %s",\n%s\n'
                                 '        "SCR-FACTS-END BEFORE %s"\n'
                                 'fatal: [%s]: FAILED! => {"stdout": "SCR-GATE %s REFUSED"}\n%s'
                                 % (nonce, _facts_body(addr, box_id), nonce, SEAT_PLAY_HOST,
                                    nonce, _recap(failed=1))), 2)
                    middle = '        "SCR-GATE %s PASSED"' % nonce
                # A deploy invocation carries the id it pinned, and the box
                # states the commit its clone is on: the fake answers with the
                # id it was handed, so the arm that moves them apart is the
                # one that reddens.
                body = (_facts_body(addr, box_id,
                                    sha=ref.group(1) if ref else OTHER_FULL) + second_fact)
                sections = [
                    '        "SCR-FACTS-BEGIN %s %s",\n%s\n        "SCR-FACTS-END %s %s"'
                    % (phase, nonce, body, phase, nonce) for phase in (BEFORE_P, AFTER_P)]
                if middle:
                    sections.insert(1, middle)
                return _attested_out(sections=sections, recap=recap), 0
            raise _NoCommand(joined)

        def _run(cmd, **kw):
            text, rc = _answer(cmd, **kw)
            return (text, rc) if kw.get("with_rc") else text
        return _run

    straight = {SEAT_PRIMARY_LIMIT: rt.PRIMARY, SEAT_STANDBY_LIMIT: rt.STANDBY}

    # (a) inert twin: each selector resolves to the box its key names. Both are
    # probed, the primary's first, nothing refuses, and the pair each one
    # resolved to is what comes back -- and is left where a later phase can ask
    # whether this run attested at all.
    monkeypatch.setattr(rt, "run", answering(straight))
    asked[:] = []
    attested = rt.attest_deploy_selectors()
    assert len(asked) == 2, asked
    assert SEAT_PRIMARY_LIMIT in asked[0] and SEAT_STANDBY_LIMIT in asked[1], asked
    assert all("ansible-playbook" in a for a in asked), asked
    # ...and each invocation minted its OWN token: the token is what binds a
    # marked section to the process that asked for it, so a constant one would
    # let one invocation's answer be replayed as another's
    import re as _re2
    tokens = [_re2.search(r"-e scr_nonce=([0-9a-f]{32})", a).group(1) for a in asked]
    assert len(set(tokens)) == 2, tokens
    # What is kept is the endpoint CLASS, never the address (R8-H5)
    assert attested == {"primary_limit": (rt.PRIMARY_TOKEN, PRIMARY_BOX_ID),
                        "standby_limit": (rt.STANDBY_TOKEN, STANDBY_BOX_ID)}, attested
    assert rt._ATTESTED == attested
    for a in asked:
        assert rt.PRIMARY not in a and rt.STANDBY not in a, a

    # (b) the reddening arm: the two values are SWAPPED. Each one is a valid
    # group name, each resolves to exactly one machine, each machine is
    # healthy -- and the deploy order is inverted. Refused on the FIRST key,
    # naming the key and never the value or the address it found.
    monkeypatch.setattr(rt, "run",
                        answering({SEAT_PRIMARY_LIMIT: rt.STANDBY,
                                   SEAT_STANDBY_LIMIT: rt.PRIMARY}))
    asked[:] = []
    with pytest.raises(rt.Fail) as exc:
        rt.attest_deploy_selectors()
    assert "SCR_TRAIN_PRIMARY_LIMIT" in str(exc.value), str(exc.value)
    assert SEAT_PRIMARY_LIMIT not in str(exc.value), str(exc.value)
    assert rt.STANDBY not in str(exc.value), str(exc.value)
    assert "an endpoint this train does not declare" in str(exc.value), str(exc.value)
    assert len(asked) == 1, "it stops at the first selector that is not its box"

    # (b2) ...and two selectors, two addresses, ONE installation: a box
    # deployed to twice leaves the other on the old build with every probe
    # passing, and only the fingerprint can say so
    monkeypatch.setattr(rt, "run", answering(
        straight, fingerprints={SEAT_PRIMARY_LIMIT: PRIMARY_BOX_ID,
                                SEAT_STANDBY_LIMIT: PRIMARY_BOX_ID}))
    with pytest.raises(rt.Fail) as exc:
        rt.attest_deploy_selectors()
    assert "SAME installation" in str(exc.value), str(exc.value)

    # (c) a selector that resolves to more than one machine, one whose machine
    # did not answer, and one whose machine stated no identity at all: none of
    # them can be attested
    monkeypatch.setattr(rt, "run", answering(
        straight, second_fact='\n        "SCR-BOX-ADDR %s",' % rt.PRIMARY))
    with pytest.raises(rt.Fail) as exc:
        rt.attest_deploy_selectors()
    assert "ONE machine stating its own identity" in str(exc.value), str(exc.value)
    monkeypatch.setattr(rt, "run", answering({SEAT_PRIMARY_LIMIT: None,
                                              SEAT_STANDBY_LIMIT: rt.STANDBY}))
    with pytest.raises(rt.Fail) as exc:
        rt.attest_deploy_selectors()
    # the PROCESS said so first (ansible exits 4 on an unreachable host) and
    # nothing of the answer was read (R9-M1)
    assert "exited rc=4" in str(exc.value), str(exc.value)
    # ...and a recap that reports the host unreachable is still refused on its
    # own when the process status says nothing (the recap is the second door)
    monkeypatch.setattr(rt, "run", _with_rc(
        lambda cmd, **kw: _attested_out(nonce=_nonce_of(cmd), recap=_recap(unreachable=1))))
    with pytest.raises(rt.Fail) as exc:
        rt.attest_deploy_selectors()
    assert "unreachable=1" in str(exc.value), str(exc.value)
    # ...and a recap naming a second machine, which is the shape a group with
    # one healthy member and one intended-but-silent member takes
    monkeypatch.setattr(rt, "run", answering(
        straight, recap=_recap() + "\nb-machine                 : ok=3    changed=1    "
                                   "unreachable=0    failed=0"))
    with pytest.raises(rt.Fail) as exc:
        rt.attest_deploy_selectors()
    assert "recap names 2 machines" in str(exc.value), str(exc.value)
    # ...and an answer carrying no marked section at all
    monkeypatch.setattr(rt, "run", _with_rc(
        lambda cmd, **kw: "%s | SUCCESS => {}" % SEAT_PLAY_HOST))
    with pytest.raises(rt.Fail) as exc:
        rt.attest_deploy_selectors()
    assert "sections are [none]" in str(exc.value), str(exc.value)
    # ...and one whose sections carry ANOTHER invocation's token: the answer
    # parses perfectly and was not produced by this process
    monkeypatch.setattr(rt, "run", _with_rc(lambda cmd, **kw: _attested_out(nonce=OTHER_NONCE)))
    with pytest.raises(rt.Fail) as exc:
        rt.attest_deploy_selectors()
    assert "a token this invocation did not mint" in str(exc.value), str(exc.value)

    # (d) ...and the two selectors have to be DIFFERENT groups: one value in
    # both keys deploys to one box twice and to the other not at all
    _fresh_process(rt, "standby_limit")
    monkeypatch.setenv("SCR_TRAIN_STANDBY_LIMIT", SEAT_PRIMARY_LIMIT)
    asked[:] = []
    with pytest.raises(rt.Fail) as exc:
        rt.attest_deploy_selectors()
    assert "SAME inventory selector" in str(exc.value), str(exc.value)
    assert asked == [], "it refuses before it probes anything"
    _fresh_process(rt, "standby_limit")
    monkeypatch.setenv("SCR_TRAIN_STANDBY_LIMIT", SEAT_STANDBY_LIMIT)

    # (e) R9-M2, identity BEFORE mutation, on ONE fake controller: the phase
    # attests with the inventory straight, and then a selector is remapped.
    # The deploy is held to the PHASE's attestation (it never re-attests, which
    # would attest the remap afresh) and it probes both boxes read-only before
    # either play, so every remap below is refused with ZERO deploy
    # invocations -- the primary is not touched.
    monkeypatch.setattr(rt, "assert_control", lambda host: None)
    monkeypatch.setattr(rt, "run", answering(straight))
    rt.attest_deploy_selectors()
    for remap, fps, says in (
            # the standby's selector now resolves to the primary's box
            ({SEAT_PRIMARY_LIMIT: rt.PRIMARY, SEAT_STANDBY_LIMIT: rt.PRIMARY}, None,
             "SCR_TRAIN_STANDBY_LIMIT"),
            # the primary's selector now resolves to the standby's box
            ({SEAT_PRIMARY_LIMIT: rt.STANDBY, SEAT_STANDBY_LIMIT: rt.STANDBY}, None,
             "SCR_TRAIN_PRIMARY_LIMIT"),
            # same address, another installation behind it
            (straight, {SEAT_PRIMARY_LIMIT: "f" * 64, SEAT_STANDBY_LIMIT: STANDBY_BOX_ID},
             "boot fingerprint differs")):
        monkeypatch.setattr(rt, "run", answering(remap, fingerprints=fps))
        asked[:] = []
        with pytest.raises(rt.Fail) as exc:
            rt._deploy_both(MERGE_FULL)
        assert says in str(exc.value), (says, str(exc.value))
        assert [a for a in asked if "scr_deploy_ref" in a] == [], \
            "no deploy play may have been started (%s)" % says
        assert asked, "the refusal came from a read-only probe, not from nothing"
    # ...and nothing re-attested along the way: the pairs the phase proved are
    # the pairs still held
    assert rt._ATTESTED == {"primary_limit": (rt.PRIMARY_TOKEN, PRIMARY_BOX_ID),
                            "standby_limit": (rt.STANDBY_TOKEN, STANDBY_BOX_ID)}, rt._ATTESTED

    # (e2) R9-M2, the window a separate probe cannot close: straight at both
    # probes, and the PRIMARY's play resolves to the standby's box. The play
    # carries the identity gate, the box's own gate refuses before the import,
    # the process exits non-zero, and the standby's play is never started.
    monkeypatch.setattr(rt, "run", answering(
        straight, plays={SEAT_PRIMARY_LIMIT: (rt.STANDBY, STANDBY_BOX_ID)}))
    asked[:] = []
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(MERGE_FULL)
    assert "exited rc=2" in str(exc.value), str(exc.value)
    deploys = [a for a in asked if "scr_deploy_ref" in a]
    assert len(deploys) == 1 and "--limit %s " % SEAT_PRIMARY_LIMIT in deploys[0] + " ", deploys
    assert "scr_expect_id=" in deploys[0] and "scr_expect_addr=%s" % rt.PRIMARY in deploys[0]
    # ...the gate carries a salted DIGEST, never the fingerprint it compares
    assert PRIMARY_BOX_ID not in deploys[0], deploys[0]

    # inert twin for these arms: both attested, both probed, both gated plays
    # passed, primary first
    monkeypatch.setattr(rt, "run", answering(straight))
    asked[:] = []
    rt._deploy_both(MERGE_FULL)
    deploys = [a for a in asked if "scr_deploy_ref=%s" % MERGE_FULL in a]
    assert len(deploys) == 2, deploys
    assert "--limit %s " % SEAT_PRIMARY_LIMIT in deploys[0] + " ", deploys
    assert "--limit %s " % SEAT_STANDBY_LIMIT in deploys[1] + " ", deploys
    # the two read-only probes came first, one per box, before either play
    first_deploy = asked.index(deploys[0])
    assert first_deploy == 2 and all("scr_deploy_ref" not in a for a in asked[:2]), asked
    played = []
    # From here the ATTESTATION is stubbed and only the PLAYS go through the
    # fake: these arms are about what a play comes back with, and an
    # attestation running on the same stub would consume its answers.
    _attested(monkeypatch, rt)
    rt.attest_deploy_selectors()

    # (f) R7-M2 / R9-M2: the inventory is correct at BOTH probes and swaps
    # before the plays. Every round before R9 passed this, and round 9 caught
    # it only AFTER the primary's play had run. The play now carries the
    # identity gate: the box that is not the attested one refuses before the
    # imported play, so no play RAN and the standby's was never started.
    played[:] = []
    gated = []
    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(
        rt, played, boxes=[(rt.STANDBY, STANDBY_BOX_ID), (rt.PRIMARY, PRIMARY_BOX_ID)],
        gated=gated))
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(MERGE_FULL)
    assert "SCR_TRAIN_PRIMARY_LIMIT" in str(exc.value), str(exc.value)
    assert "identity gate" in str(exc.value), str(exc.value)
    assert played == [] and len(gated) == 1, (played, gated)
    # (f2) ...and behind the gate the after-play comparison still stands on its
    # own: with the gate taken away the box's statement after the play is
    # compared, for the PRIMARY, before the standby's play is started
    played[:] = []
    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(
        rt, played, boxes=[(rt.STANDBY, STANDBY_BOX_ID), (rt.PRIMARY, PRIMARY_BOX_ID)],
        gate=False))
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(MERGE_FULL)
    assert "SCR_TRAIN_PRIMARY_LIMIT" in str(exc.value), str(exc.value)
    assert "boot fingerprint differs" in str(exc.value), str(exc.value)
    assert len(played) == 1, "the standby's play must never have been started"
    # ...and the address half of the pair, with the fingerprint held
    played[:] = []
    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(
        rt, played, boxes=[(SEAT_BOX_ENDPOINT, PRIMARY_BOX_ID), (rt.STANDBY, STANDBY_BOX_ID)],
        gate=False))
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(MERGE_FULL)
    assert "different endpoint" in str(exc.value), str(exc.value)
    assert len(played) == 1, played

    # (g) R4-L3: the box states which COMMIT the clone it deploys from is on,
    # and it has to be the id this train deployed. A play reporting failed=0
    # and a marker reading new are not that.
    played[:] = []
    monkeypatch.setattr(rt, "run_attested",
                        _attesting_deploy(rt, played, shas=[REVIEWED_FULL]))
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(MERGE_FULL)
    assert "checked out at %s and this train deployed %s" % (REVIEWED_FULL, MERGE_FULL) \
        in str(exc.value), str(exc.value)
    assert [c[1] for c in played] == [SEAT_PRIMARY_LIMIT], played
    # ...and a play that reported no such line at all is not a pass either
    played[:] = []
    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(rt, played, shas=[None]))
    with pytest.raises(rt.Fail) as exc:
        rt._deploy_both(MERGE_FULL)
    assert "exactly one 40-character object id" in str(exc.value), str(exc.value)

    # (h) ...and phase 7 asks the same question of both boxes, in that order,
    # before it records the rollout as verified
    probes = []
    monkeypatch.setattr(rt, "probe_box",
                        lambda key, values=None: probes.append(key) or
                        (rt.PRIMARY_TOKEN if len(probes) < 2 else rt.STANDBY_TOKEN,
                         PRIMARY_BOX_ID if len(probes) < 2 else STANDBY_BOX_ID,
                         MERGE_FULL if len(probes) < 2 else REVIEWED_FULL))
    with pytest.raises(rt.Fail) as exc:
        rt.assert_boxes_are_on(MERGE_FULL)
    assert "rollout is not complete on this box" in str(exc.value), str(exc.value)
    assert probes == ["primary_limit", "standby_limit"], probes
    probes[:] = []
    monkeypatch.setattr(rt, "probe_box",
                        lambda key, values=None: probes.append(key) or
                        (rt.PRIMARY_TOKEN if len(probes) < 2 else rt.STANDBY_TOKEN,
                         PRIMARY_BOX_ID if len(probes) < 2 else STANDBY_BOX_ID, MERGE_FULL))
    rt.assert_boxes_are_on(MERGE_FULL)             # inert twin
    assert probes == ["primary_limit", "standby_limit"], probes
    # ...and R8-L4: two probes that answer from ONE installation are not two
    # boxes agreeing, whatever commit they name
    probes[:] = []
    monkeypatch.setattr(rt, "probe_box",
                        lambda key, values=None: probes.append(key) or
                        (rt.PRIMARY_TOKEN if len(probes) < 2 else rt.STANDBY_TOKEN,
                         PRIMARY_BOX_ID, MERGE_FULL))
    with pytest.raises(rt.Fail) as exc:
        rt.assert_boxes_are_on(MERGE_FULL)
    assert "SAME installation" in str(exc.value), str(exc.value)
    assert PRIMARY_BOX_ID not in str(exc.value), str(exc.value)
    # ...and two probes that answer at one endpoint class are not two boxes either
    probes[:] = []
    monkeypatch.setattr(rt, "probe_box",
                        lambda key, values=None: probes.append(key) or
                        (rt.PRIMARY_TOKEN,
                         PRIMARY_BOX_ID if len(probes) < 2 else STANDBY_BOX_ID, MERGE_FULL))
    with pytest.raises(rt.Fail) as exc:
        rt.assert_boxes_are_on(MERGE_FULL)
    assert "same endpoint class" in str(exc.value), str(exc.value)

    # (i) R7-L3: attested before ANY mutation, on every path, proved by the
    # ORDER OF THE CALLS rather than by where a line sits. A phase 0 that SKIPS
    # on a valid snapshot, and a code phase resumed with `--from code`, are the
    # two paths that reached the merge, the commit and the push with the
    # question still unasked.
    sequence = []

    def _attesting(values=None):
        sequence.append("attest")
        rt._ATTESTED.clear()
        rt._ATTESTED.update({"primary_limit": (rt.PRIMARY_TOKEN, PRIMARY_BOX_ID),
                             "standby_limit": (rt.STANDBY_TOKEN, STANDBY_BOX_ID)})
        return dict(rt._ATTESTED)

    monkeypatch.setattr(rt, "attest_deploy_selectors", _attesting)
    _snapshot_is_listed(monkeypatch, rt)
    monkeypatch.setattr(rt, "snapshot_operation",
                        lambda **k: sequence.append("play") or ("failed=0", None, None))
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    rt.phase_snapshot(SimpleNamespace(go=True), _snap())
    assert sequence == ["attest"], ("this phase 0 skipped -- and still attested", sequence)

    sequence[:] = []
    rt._ATTESTED.clear()
    stub, _log = _merging_git(rt, refs={rt.BRANCH: REVIEWED_FULL, "main": MAIN_FULL},
                              parents={MERGE_FULL: [MAIN_FULL, REVIEWED_FULL]},
                              trees={REVIEWED_FULL: REVIEWED_TREE, MERGE_FULL: REVIEWED_TREE},
                              remote_main=MERGE_FULL)

    def _recorded(cmd, **kw):
        out = stub(cmd, **kw)
        joined = (" ".join(cmd) if isinstance(cmd, list) else cmd) + " "
        for verb in ("checkout", "merge", "commit", "push"):
            if " %s " % verb in joined:
                sequence.append(verb)
        return out

    monkeypatch.setattr(rt, "run", _recorded)
    monkeypatch.setattr(rt, "code_state", lambda host: (True, True, False, ["alias absent"]))
    monkeypatch.setattr(rt, "_deploy_both", lambda sha, extra=None, st=None, **_kw: sequence.append("deploy"))
    monkeypatch.setattr(rt, "assert_route_probes", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_health_keys", lambda hosts: None)
    monkeypatch.setattr(rt, "assert_edge_runs_new_code", lambda: None)
    rt.phase_code(SimpleNamespace(go=True), dict(_snap(), pre_code_old_build=True))
    assert "attest" in sequence, sequence
    for mutation in ("checkout", "merge", "commit", "push", "deploy"):
        assert mutation in sequence, (mutation, sequence)
        assert sequence.index("attest") < sequence.index(mutation), (mutation, sequence)

    # ...and it is the STATE that is asked, not the line: a run whose
    # attestation answered nothing cannot reach the merge
    sequence[:] = []
    rt._ATTESTED.clear()
    monkeypatch.setattr(rt, "attest_deploy_selectors", lambda values=None: None)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(SimpleNamespace(go=True), dict(_snap(), pre_code_old_build=True))
    assert "before this run had proved which machine" in str(exc.value), str(exc.value)
    assert "merge" not in sequence and "push" not in sequence, sequence


# ── round 9: the method change, and the findings the round-8 review raised ──
#
# The pin no longer carries a transcript of a live run. What it carries is a
# schema-rendered document per artifact, and the whole point of the schema is
# that a free string cannot be represented in it: an identifier can only travel
# in a review bundle inside text somebody wrote, and there is no text. The door
# and the census stay as defence in depth -- for the terminal, and for the
# human-written files -- and the findings below are still fixed by number.


def _recording(rt):
    """Arm the recorder and leave it armed for the duration of one test."""
    rt.recording(True)
    return rt


def _cli(monkeypatch, rt, *args):
    """Run the train's own entry point the way a shell does.

    `_main` parses `sys.argv` -- it takes no argument list -- so a test that
    wants the WHOLE path, parser included, has to hand it one the same way."""
    monkeypatch.setattr(rt.sys, "argv", ["release_train.py"] + list(args))
    return rt._main()


def test_the_review_summary_is_a_schema_document_and_carries_no_free_text(monkeypatch):
    """R8 method change (A1/A2, and H4 with it): the pin is made of documents, not transcripts.

    Five rounds closed a named identifier path and the round after found a sibling of it, and the
    round-8 fix for M1 minted a new identifier class of its own. Scrubbing an unbounded set of
    free-text transcripts with a deny-list cannot be shown complete -- the proof obligation is
    "no member of an open set appears", and a deny-list answers a different question.

    So the artifact changes. Every value a review round reads is an enum token, an object id, an
    integer, a UTC instant, or one of the identifiers this file already declares. There is no string
    type, so there is nothing for an identifier to travel inside: a play's tail, an exception message
    and a label a box reported each have a CLASS in the document and no text anywhere.

    And because a document checked only by the program that wrote it is checked by nothing, the
    renderer refuses to emit one the grammar forbids, and a second implementation in the pin asks the
    same question again of the files that arrive there."""
    import json
    import re as _re
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _recording(rt)
    monkeypatch.setattr(rt, "_commit_sha", lambda rev, **kw: {
        rt.BRANCH: REVIEWED_FULL, "main": MAIN_FULL}.get(rev, MERGE_FULL))

    # (a) what the phases record is what the documents are made of -- the same
    # functions a real run drives, noting the class of what they just printed
    rt.record_one("plan", outcome="COMPLETED", refused_at="NONE", exit_code=0)
    rt.record("plan_phases", name="SNAPSHOT", disposition="SKIPPED", reason="NO_MIGRATION")
    rt.record_one("snapshot", dropped=4, names=1, usable="YES", endpoint="PRIMARY",
                  fingerprint="MATCH", listing_rc=0, readings_agree="YES")
    docs = rt.summary_documents()
    assert [d["artifact"] for d in docs] == list(rt.SUMMARY_ARTIFACTS), docs
    for doc in docs:
        assert doc["schema"] == rt.SUMMARY_SCHEMA and doc["version"] == rt.SUMMARY_VERSION
        assert rt.summary_problem(doc) is None, doc
        # the key set is ENUMERATED: every document carries exactly its
        # artifact's keys, and a key this run never reached is present as the
        # fixed word UNRECORDED rather than absent
        want = (set(rt.SUMMARY_HEAD) | set(rt.SUMMARY_SINGLES[doc["artifact"]])
                | set(rt.SUMMARY_ROWS[doc["artifact"]]))
        assert set(doc) == want, (doc["artifact"], set(doc) ^ want)
    plan = docs[0]
    assert plan["outcome"] == "COMPLETED" and plan["provenance"] == rt.UNRECORDED, plan
    assert plan["phases"] == [{"name": "SNAPSHOT", "disposition": "SKIPPED",
                               "reason": "NO_MIGRATION"}], plan

    # (b) the value types, asked of every shape a free string can take. Each of
    # these is a value an earlier round's transcript carried verbatim -- and the
    # last four are the ones a SHAPE-based enum admitted: an upper-cased machine
    # or group name is an upper-case word, and the vocabulary is a closed list
    for bad in ("a-machine | CHANGED | rc=0 >>", "ok: [a-machine]", "/a-dir/a-person/zap",
                "an-inventory-group", "192.0.2.17", "a" * 64, "Not An Enum", "mixedCase",
                "included: playbooks/deploy.yml for a-machine", "",
                "AN_INVENTORY_GROUP", "A_MACHINE", "SCR_TRAIN_CONTROLLER", "PRIMARY_LIMIT"):
        assert rt.summary_scalar_problem(bad), bad
    for good in (0, 7, 4200, "PRIMARY", "NO_MIGRATION", "NONE", REVIEWED_FULL,
                 REVIEWED_FULL[:7], "2026-09-22T03:00:01+00:00",
                 rt.PRIMARY, rt.STANDBY, rt.EDGE_HOST, rt.UNRECORDED,
                 # the words this file defines are derived, not retyped: every
                 # phase and every batch is a member
                 "DEPLOY_PRECURSOR", "I18N", "VERIFY", rt.batch_token(ABSENT_BATCH)):
        assert rt.summary_scalar_problem(good) is None, good
    # ...and a boolean is not an integer here: `True` renders as `true`, which
    # is a word, and the whole grammar is that a word is a vocabulary member
    assert rt.summary_scalar_problem(True), "a boolean is not a value type"
    # ...and a key is TYPED: a number where a word is required, and a word where
    # a number is, are each refused although both are members of SOME type
    assert rt.summary_scalar_problem(7, rt.SUMMARY_SINGLES["PLAN"]["outcome"])
    assert rt.summary_scalar_problem("YES", rt.SUMMARY_SINGLES["SNAPSHOT"]["dropped"])
    assert rt.summary_scalar_problem("YES", rt.SUMMARY_SINGLES["PLAN"]["outcome"]) is None

    # (c) the reddening arms: the renderer REFUSES rather than emitting a
    # document the schema forbids -- an unknown key carrying a perfectly good
    # value, a key of the wrong form, a free string, an upper-case word outside
    # the vocabulary, a value of the wrong type, a planted fingerprint, an
    # unknown key inside a row, and a row that is not an object
    for section, field, value, says in (
            ("plan", "note", "PRESENT", "is not a key this schema defines"),
            ("plan", "Note", "PRESENT", "is not a key this schema defines"),
            ("plan", "outcome", "the play said a-machine", "not a value of its type"),
            ("plan", "outcome", "AN_INVENTORY_GROUP", "not a value of its type"),
            ("plan", "outcome", 7, "not a value of its type"),
            ("snapshot", "dropped", "YES", "not a value of its type"),
            ("snapshot", "fingerprint", "c" * 64, "not a value of its type")):
        rt.recording(True)
        rt.record_one(section, **{field: value})
        with pytest.raises(rt.Fail) as exc:
            rt.summary_documents()
        assert "refusing to render" in str(exc.value), (field, str(exc.value))
        assert says in str(exc.value), (field, str(exc.value))
    rt.recording(True)
    rt.record("plan_phases", name="CODE", disposition="RAN", note="PRESENT")
    with pytest.raises(rt.Fail) as exc:
        rt.summary_documents()
    assert "not a key this schema defines for that section" in str(exc.value), str(exc.value)
    rt.recording(True)
    rt.record("plan_phases", name="CODE", disposition="RAN")
    rt._RECORDED["plan_phases"].append("not an object")
    with pytest.raises(rt.Fail) as exc:
        rt.summary_documents()
    assert "is not an object" in str(exc.value), str(exc.value)
    # ...and a MISSING key: a document that lost one -- a truncated render, a
    # hand edit -- is refused by name, at the top level and inside a row
    rt.recording(True)
    rt.record("plan_phases", name="CODE", disposition="RAN")
    whole = rt.summary_documents()
    for doc in whole:
        assert rt.summary_problem(doc) is None, doc
    cut = dict(whole[0])
    del cut["outcome"]
    assert "is missing the key 'outcome'" in (rt.summary_problem(cut) or ""), cut
    cut = dict(whole[0], phases=[{"name": "CODE", "disposition": "RAN"}])
    assert "is missing the key 'reason'" in (rt.summary_problem(cut) or ""), cut
    extra = dict(whole[0], note="PRESENT")
    assert "is not a key this schema defines" in (rt.summary_problem(extra) or ""), extra

    # (d) H4: a machine fingerprint is a persistent machine identifier -- minted
    # at first boot, the same for the life of that installation -- and it never
    # reaches a document. What reaches one is the VERDICT of comparing two
    # readings, and "no comparison" is not "they agreed".
    assert rt.fingerprint_verdict([SEAT_BOX_ID, SEAT_BOX_ID]) == "MATCH"
    assert rt.fingerprint_verdict([SEAT_BOX_ID, "f" * 64]) == "MISMATCH"
    assert rt.fingerprint_verdict([SEAT_BOX_ID]) == "MISSING"
    assert rt.fingerprint_verdict([]) == "MISSING"
    assert rt.fingerprint_verdict([SEAT_BOX_ID, None]) == "MISSING"
    rt.recording(True)
    rt.record_one("snapshot", fingerprint=rt.fingerprint_verdict([SEAT_BOX_ID, SEAT_BOX_ID]))
    rendered = json.dumps(rt.summary_documents())
    assert SEAT_BOX_ID not in rendered and "MATCH" in rendered, rendered
    assert _re.search(r"[0-9a-f]{64}", rendered) is None, rendered

    # (e) inert twin: the document a real `check` renders passes its own
    # renderer AND carries the state as classes rather than as the state file
    rt.recording(True)
    st = dict(_snap(), code_sha=MERGE_FULL, verified=True)
    summary = rt.state_summary(st)
    rt.record_one("check", **summary)
    docs = rt.summary_documents()
    check = [d for d in docs if d["artifact"] == "CHECK"][0]
    assert check["snapshot_fingerprint"] == "RECORDED", check
    assert SEAT_BOX_ID not in json.dumps(check), check
    assert check["snapshot_name"] == "PRESENT" and check["code_sha"] == MERGE_FULL, check
    rt.recording(False)


def test_the_summary_is_emitted_between_two_fences_and_nothing_else_writes(monkeypatch, capsys,
                                                                           tmp_path):
    """A2/L2: `review-summary` produces the documents on the way out of the same read-only path.

    It is not a second implementation of the phases: it runs `check`, captures the listing, walks the
    phase list in plan mode, and prints what the recorder collected. A summary that came from its own
    copy of the logic would be a document about a program nobody runs.

    It writes nothing of its own. The documents go to STDOUT between two fixed fences, and since
    round 11 the captured listing goes there too, between its own two lines: the one sentence the
    frozen bar's B11 asks about -- what this train writes -- is the state file and the printed plan,
    and a review-summary does not even write the state file (its save is stubbed here only so the
    directory comparison below is the witness, not the stub)."""
    import json
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    # `select_batch` re-derives STATE_PATH from the batch entry, and `_main`
    # calls it -- so the destination is pinned through the one function that
    # answers it rather than through the global it is computed from.
    monkeypatch.setattr(rt, "STATE_PATH", str(state_dir / "train-state.json"))
    monkeypatch.setattr(rt, "load_state", lambda: dict(_snap()))
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    monkeypatch.setattr(rt, "phase_check", lambda args, st: rt.record_one(
        "check", **rt.state_summary(st)))
    monkeypatch.setattr(rt, "snapshot_listing",
                        lambda values=None: _listing(_snap()["snapshot"]["name"]))
    monkeypatch.setattr(rt, "assert_provenance_up_front", lambda args, st: None)
    for name, _fn in rt.PHASES:
        pass
    monkeypatch.setattr(rt, "PHASES", [("snapshot", lambda args, st: None),
                                       ("code", lambda args, st: None)])
    before = sorted(p.name for p in state_dir.iterdir())
    capsys.readouterr()
    rc = _cli(monkeypatch, rt, "--batch", ABSENT_BATCH, "review-summary")
    out = capsys.readouterr().out
    assert rc == 0, out
    assert rt.SUMMARY_OPEN in out and rt.SUMMARY_CLOSE in out, out
    body = out.split(rt.SUMMARY_OPEN, 1)[1].split(rt.SUMMARY_CLOSE, 1)[0]
    docs = json.loads(body)
    assert [d["artifact"] for d in docs] == list(rt.SUMMARY_ARTIFACTS), docs
    for doc in docs:
        assert rt.summary_problem(doc) is None, doc
    # the phases it walked are in the PLAN document, as tokens
    plan = [d for d in docs if d["artifact"] == "PLAN"][0]
    assert {row["name"] for row in plan["phases"]} == {"SNAPSHOT", "CODE"}, plan
    # ...and it left NOTHING behind: the captured listing is in the
    # transcript, between its own two lines, and not in a file (B11, round 11)
    after = sorted(p.name for p in state_dir.iterdir())
    assert after == before, (before, after, out)
    assert out.count(rt.CAPTURE_OPEN) == 1 and out.count(rt.CAPTURE_CLOSE) == 1, out
    assert out.index(rt.CAPTURE_CLOSE) < out.index(rt.SUMMARY_OPEN), out
    # ...and a review-summary is never a run: it forces the dry arm
    assert "DRY RUN" in out, out


def test_the_seat_is_captured_on_first_read_and_cannot_be_read_again(monkeypatch):
    """R8-H2: the first read won for the door and lost for the caller, which is the same defect inside out.

    The capture existed so the door substitutes what the command was BUILT from. But `identifier()`
    re-read the environment and the seat file on every call and returned the later value while keeping
    the earlier one, so a seat edited between two phases gave the door one string and the command
    another -- and the identifier the transcript was supposed to lose is exactly the one it kept.

    There is no second read to lose to now. `_read_live_seat` is the only place either source is
    touched and it REFUSES for a key already captured, so a path that reaches around `identifier()`
    cannot reopen the question either."""
    rt, src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)

    # (a) the capture answers, and the live sources are not consulted at all
    first = rt.identifier("controller")
    assert first == SEAT_CONTROLLER
    monkeypatch.setenv("SCR_TRAIN_CONTROLLER", "a-different-controller")
    assert rt.identifier("controller") == first, "the capture answers, not the environment"
    assert rt.seat_values()["controller"] == first
    assert rt.require_identifier("controller") == first

    # (b) the reddening arm: the ONE reader refuses outright for a captured key
    with pytest.raises(rt.Fail) as exc:
        rt._read_live_seat("controller")
    assert "read ONCE" in str(exc.value), str(exc.value)
    assert "controller" in str(exc.value), str(exc.value)
    assert SEAT_CONTROLLER not in str(exc.value), str(exc.value)
    assert "a-different-controller" not in str(exc.value), str(exc.value)

    # ...and it is the only reader: nothing else in the file reaches either
    # source for a seat key, which is what makes the refusal above a rule
    # rather than one function's habit
    # R9-M4: the file is opened in ONE place, as bytes, and every key is
    # parsed out of that one read
    for source in ("os.environ.get(IDENTIFIERS", "open(TRAIN_CONF", "doc.get(key)"):
        assert src.count(source) == 1, (source, src.count(source))

    # (b2) ...and the capture answers the CAPTURE, never the value it was
    # handed. `setdefault` then read back: the two are the same on a first
    # capture and different on every path that reached here twice, and the
    # one that must travel is the one the door knows. Asked of `_captured`
    # directly, because the refusal above is what stops `identifier()`
    # reaching it twice -- a guard being unreachable is not a reason to
    # leave the thing behind it unexercised.
    assert rt._captured("controller", "a-later-controller") == first
    assert rt._SEAT_SNAPSHOT["controller"] == first
    assert rt.redact("reached a-later-controller") == "reached a-later-controller"

    # (c) inert twin: a key nobody has read yet still reads
    _fresh_process(rt, "pve_group")
    monkeypatch.setenv("SCR_TRAIN_PVE_GROUP", "a-second-group")
    assert rt._read_live_seat("pve_group") == "a-second-group"
    assert rt.identifier("pve_group") == "a-second-group"

    # (d) ...and a ONE-CHARACTER host label is learned like any other. The
    # shape a label had to match demanded two characters, so a machine called
    # `a` announced itself in every line of a play's output and the door had
    # nothing to substitute.
    rt._LEARNED_HOSTS.clear()
    rt.learn_hosts("ok: [a]\nchanged: [b]\nchanged: [ab]\n"
                   "c                  : ok=9    changed=3    unreachable=0    failed=0")
    assert {"a", "b", "ab", "c"} <= set(rt._LEARNED_HOSTS), rt._LEARNED_HOSTS
    said = rt.redact("included: playbooks/deploy.yml for a")
    assert said == "included: playbooks/deploy.yml for %s" % rt.HOST_TOKEN, said
    # inert twin: a word that is not a learned label is not touched
    assert "for zzz" in rt.redact("included: playbooks/deploy.yml for zzz")


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


def test_one_ansible_process_carries_the_facts_and_the_play_they_attest(monkeypatch, tmp_path):
    """R8-M1/M2: the attestation and the play it attests were two resolutions of the inventory.

    Each was correct on its own. The probe asked a selector which machine it resolves to; the play ran
    under the same selector text; and nothing at all joined the two, because a selector is a name for a
    set somebody else maintains and it is resolved afresh by every process that uses it. Correct at
    both probes and remapped in between, the standby is deployed first, the still-old primary passes
    the liveness check in the middle, and both final markers read new.

    So there is one process. One `ansible-playbook`, one `--limit`, one inventory resolution: a facts
    play, the ZAP play by `import_playbook`, the facts play again -- and for the snapshot, the listing
    before and after as tasks of the same playbook. The facts are bound to the play by a token minted
    for the invocation and passed as an extra variable, so an answer that came from anywhere else says
    so, and the playbook is fed to the controller for that invocation only: written by the same shell
    that runs it and removed by the same shell afterwards, so nothing is installed anywhere."""
    import json
    import re as _re
    import base64 as _b64
    rt, src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)

    # (a) the playbook the train composes: three plays, the middle one an
    # import of the ZAP play at the seat's own playbook directory
    book = json.loads(rt.attested_playbook(play_path="/srv/a-play-dir/playbooks/x.yml",
                                           listing=True))
    assert [p.get("name") or p.get("import_playbook") for p in book] == [
        "scr identity before", "/srv/a-play-dir/playbooks/x.yml", "scr identity after"], book
    assert all(p.get("gather_facts") is False for p in book if "hosts" in p), book
    # the token is rendered from the extra variable, never written in
    rendered = json.dumps(book)
    assert "{{ scr_nonce }}" in rendered, rendered
    assert _re.search(r"[0-9a-f]{32}", rendered) is None, "no token is baked into the playbook"
    # ...and the listing is a TASK of it, so the names read back and the
    # container the play wrote into cannot be two different containers
    assert rendered.count("SCR-LIST-BEGIN") == 2 and rendered.count("SCR-LIST-END") == 2
    assert "list-snapshots" in rendered, rendered
    # a playbook with no play to import is still two facts plays
    assert len(json.loads(rt.attested_playbook(play_path=None, listing=False))) == 2

    # (b) it travels base64-encoded through a PIPE the controller's shell makes
    # (R11-L2: no temporary file, no removal), and the line this train PRINTS
    # about it carries neither the controller nor the selector
    asked = []
    monkeypatch.setattr(rt, "run", _attesting_run(rt, asked, addr=rt.PRIMARY))
    printed = []
    monkeypatch.setattr(rt, "print", lambda *a, **k: printed.append(
        " ".join(str(x) for x in a)))
    rt.run_attested(SEAT_PRIMARY_LIMIT, play=None)
    sent = asked[-1]
    assert "ansible-playbook <(printf %s " in sent and " | base64 -d) --limit " in sent, sent
    assert "mktemp" not in sent and "rm -f" not in sent, sent
    # ...and when there IS a play, the playbook this run actually sends is
    # the one that imports it. Decoded out of the command, because the
    # composition being right is a different fact from this run passing it
    # the play: the wiring is what makes the facts and the work one
    # process.
    import base64 as _b64
    rt.run_attested(SEAT_PRIMARY_LIMIT, play="deploy-scr-backend.yml")
    blob = _re.search(r"printf %s '?([A-Za-z0-9+/=]+)'?", asked[-1])
    assert blob, asked[-1]
    book_sent = json.loads(_b64.b64decode(blob.group(1)).decode("utf-8"))
    assert [p.get("import_playbook") for p in book_sent if "import_playbook" in p] \
        == ["%s/deploy-scr-backend.yml" % SEAT_PLAY_DIR], book_sent
    assert len(book_sent) == 3, book_sent
    assert "base64 -d" in sent, sent
    blob = _re.search(r"printf %s '?([A-Za-z0-9+/=]+)'? \|", sent).group(1)
    assert json.loads(_b64.b64decode(blob).decode("utf-8")), "the blob IS the playbook"
    said = "\n".join(printed)
    assert SEAT_CONTROLLER not in said and SEAT_PRIMARY_LIMIT not in said, said
    assert rt.HOST_TOKEN in said, said
    monkeypatch.undo()
    _seat(monkeypatch, rt)

    # (c) the reddening arms, one per way an answer can fail to be ONE
    # machine's account of ONE moment. Each of these parses perfectly and each
    # of them is refused.
    facts_b, facts_a = _facts_section(BEFORE_P), _facts_section(AFTER_P)
    for sections, says in (
            ([facts_b], "sections are [SCR-FACTS/BEFORE]"),
            ([facts_a], "sections are [SCR-FACTS/AFTER]"),
            ([facts_b, facts_b, facts_a], "more than once"),
            ([facts_a, facts_b], "sections are [SCR-FACTS/AFTER SCR-FACTS/BEFORE]"),
            ([facts_b, _facts_section(AFTER_P, OTHER_NONCE)],
             "a token this invocation did not mint"),
            ([], "sections are [none]")):
        monkeypatch.setattr(rt, "run", _attesting_run(rt, sections=sections))
        with pytest.raises(rt.Fail) as exc:
            rt.run_attested(SEAT_PRIMARY_LIMIT, who="the probe")
        assert says in str(exc.value), (says, str(exc.value))
        assert "Nothing has been recorded" in str(exc.value), str(exc.value)

    # ...and the one the label cannot see: the inventory LABEL is held constant
    # across the two facts blocks and the machine underneath it changes
    monkeypatch.setattr(rt, "run", _attesting_run(rt, addr=rt.PRIMARY, after_id="f" * 64))
    with pytest.raises(rt.Fail) as exc:
        rt.run_attested(SEAT_PRIMARY_LIMIT, values=rt.seat_values(), who="the probe")
    assert "boot fingerprint or the endpoint class moved across the operation" in str(exc.value)
    assert "f" * 64 not in str(exc.value), str(exc.value)
    # ...and the same with the FINGERPRINT held and the endpoint class moved,
    # which is the half a fingerprint comparison alone cannot see. Asked of the
    # SNAPSHOT target, because a per-box deploy selector has a declared answer
    # and is refused one question earlier -- at capture, for reporting an
    # endpoint this train does not declare for that key.
    monkeypatch.setattr(rt, "run", _attesting_run(rt, addr=rt.PRIMARY,
                                                  after_addr=rt.EDGE_HOST))
    with pytest.raises(rt.Fail) as exc:
        rt.run_attested(rt.snapshot_target(), who="the probe")
    assert "moved across the operation" in str(exc.value), str(exc.value)
    # ...and an endpoint this train does not declare for that key
    monkeypatch.setattr(rt, "run", _attesting_run(rt, addr="198.51.100.9"))
    with pytest.raises(rt.Fail) as exc:
        rt.run_attested(SEAT_PRIMARY_LIMIT, values=rt.seat_values(), who="the probe")
    assert "an endpoint this train does not declare" in str(exc.value), str(exc.value)
    assert "198.51.100.9" not in str(exc.value), str(exc.value)

    # (d) R8-M2: a status this operation could have left standing is REPLACED
    # with REFUSED rather than left as an earlier success. The play reported
    # failed=0 and the facts did not come back; "it succeeded" is the one thing
    # the record may not say.
    saved = []
    monkeypatch.setattr(rt, "save_state", lambda st_: saved.append(dict(st_)))
    monkeypatch.setattr(rt, "run", _attesting_run(rt, sections=[facts_b]))
    st = {"code_deployed": True, "snapshot": {"name": "cc_x__1"}}
    with pytest.raises(rt.Fail):
        rt.run_attested(SEAT_PRIMARY_LIMIT, st=st, status_keys=("code_deployed",),
                        who="the deploy")
    assert st["code_deployed"] == "REFUSED", st
    assert saved and saved[-1]["code_deployed"] == "REFUSED", saved

    # (d2) ...and the READERS of that word. REFUSED is a non-empty string: a
    # truth test reads it as a success, and a reader that expects a record
    # crashes on it. The phase that runs this batch's post-code files is gated
    # on the code being live, and a refused deploy must stop it; the summary
    # the transcript carries must say REFUSED, not YES and not a traceback.
    sql_calls = []
    monkeypatch.setattr(rt, "sql", lambda host, q: sql_calls.append(q) or "")
    monkeypatch.setattr(rt, "ssh", lambda host, cmd, **kw: sql_calls.append(cmd) or "")
    refused = {"code_deployed": "REFUSED", "snapshot": "REFUSED"}
    with pytest.raises(rt.Fail) as exc:
        rt.phase_i18n(SimpleNamespace(go=True), dict(refused))
    assert "is not live on both boxes" in str(exc.value), str(exc.value)
    assert sql_calls == [], sql_calls
    summary = rt.state_summary(dict(refused))
    assert summary["code_deployed"] == "REFUSED" and summary["snapshot"] == "REFUSED", summary
    assert summary["snapshot_batch"] == "MISSING", summary
    for doc in (rt.state_summary({}), summary):
        assert all(rt.summary_scalar_problem(v, rt.SUMMARY_SINGLES["CHECK"].get(k)) is None
                   for k, v in doc.items()), doc
    # ...the twin: the value a success writes passes the same gate
    rt.phase_i18n(SimpleNamespace(go=True), {"code_deployed": True})
    assert rt.state_summary({"code_deployed": True})["code_deployed"] == "YES"

    # (d3) R9, found by running: the ORDER the composed playbook emits. The
    # facts bracket the operation -- first before it, LAST after it -- with
    # the imported play between the halves, and the parser requires exactly
    # that. The after-play used to state its facts before reading the
    # listing, so every live listing was refused as out of order while every
    # fixture, composing the parser's order, passed.
    design = [(rt.FACTS_MARK, rt.BEFORE), (rt.LIST_MARK, rt.BEFORE), None,
              (rt.LIST_MARK, rt.AFTER), (rt.FACTS_MARK, rt.AFTER)]
    play_at = "/srv/a-play-dir/playbooks/x.yml"
    assert rt.composed_order(rt.attested_playbook(play_path=play_at, listing=True)) \
        == design
    assert rt.composed_order(rt.attested_playbook(play_path=None, listing=True)) \
        == [s for s in design if s]
    assert rt.composed_order(rt.attested_playbook(play_path=play_at, listing=False)) \
        == [design[0], None, design[4]]
    # ...read a second way: the playbook the train actually SENT, decoded by
    # this module's own reader rather than by `composed_order`
    asked = []
    monkeypatch.setattr(rt, "run", _attesting_run(rt, asked, addr=rt.PRIMARY, listing=True))
    rt.run_attested(SEAT_PRIMARY_LIMIT, play="snapshot-scr.yml", listing=True,
                    who="the snapshot")
    assert _order_sent(asked[-1]) == design, _order_sent(asked[-1])
    # ...and a composition that would emit another order is refused BEFORE
    # anything is spawned: the controller is asked nothing at all
    honest = rt.attested_playbook

    def _facts_first_after(play_path=None, listing=False, gate=False):
        composed = json.loads(honest(play_path=play_path, listing=listing, gate=gate))
        last = composed[-1]["tasks"]
        composed[-1]["tasks"] = ([t for t in last if "facts" in t["name"]]
                                 + [t for t in last if "facts" not in t["name"]])
        return json.dumps(composed)

    for playbook in (_facts_first_after,
                     lambda play_path=None, listing=False, gate=False: json.dumps(
                         [json.loads(honest(play_path, listing, gate))[i] for i in (1, 0, 2)])):
        monkeypatch.setattr(rt, "attested_playbook", playbook)
        asked.clear()
        with pytest.raises(rt.Fail) as exc:
            rt.run_attested(SEAT_PRIMARY_LIMIT, play="snapshot-scr.yml", listing=True,
                            who="the snapshot")
        assert "Nothing has run" in str(exc.value), str(exc.value)
        assert asked == [], asked
    monkeypatch.setattr(rt, "attested_playbook", honest)

    # (e) the inert twin: an honest answer, and what comes back is the box's
    # own statement as CLASSES with the fingerprints kept for a verdict
    monkeypatch.setattr(rt, "run", _attesting_run(rt, addr=rt.PRIMARY, sha=MERGE_FULL))
    play_out, sections, identity, host = rt.run_attested(
        SEAT_PRIMARY_LIMIT, values=rt.seat_values(), who="the probe")
    assert identity == (rt.PRIMARY_TOKEN, SEAT_BOX_ID), identity
    assert sections["endpoints"] == [rt.PRIMARY_TOKEN, rt.PRIMARY_TOKEN]
    assert rt.fingerprint_verdict(sections["fingerprints"]) == "MATCH"
    assert host == SEAT_PLAY_HOST
    assert rt.box_sha(sections[(rt.FACTS_MARK, rt.AFTER)], "the probe") == MERGE_FULL


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


# ── round 10: the findings the round-9 review raised, each by number ──
#
# R9-M1 the listing's status, R9-M2 identity and the new build before the next
# box, R9-M3 the attempt sentinel, R9-M4 one read of the seat file, R9-M5 the
# exact success word at every gate, R9-L5 the stale `verified`. Every value
# handed to the train below is a fixture: the synthetic seat, the RFC 5737
# address family, and a state file under the test's own temporary directory.

_OLD_BUILD = (True, False, True, ["alias present"])
_NEW_BUILD = (True, True, False, ["alias absent"])
_TIMED_OUT = ("the command did not answer within 1800s and was killed. Nothing it may have "
              "done has been recorded.")


def _no_command(cmd, **kw):
    """`rt.run` for a test in which no command may be spawned at all."""
    _raise_no_command(cmd)


def _state_under(monkeypatch, rt, path):
    """Point the train's state file at `path`, and keep it there across `select_batch`.

    `_main` selects the batch again, and selecting a batch derives STATE_PATH
    from the entry -- the operating seat's own state file. A test that drives
    the entry point must not be able to reach that file."""
    real = rt.select_batch

    def _select(name):
        real(name)
        rt.STATE_PATH = str(path)

    monkeypatch.setattr(rt, "select_batch", _select)
    monkeypatch.setattr(rt, "STATE_PATH", str(path))
    return path


def _bot_batch(rt):
    """A copy of the no-migration entry that DOES deploy the bot, selected."""
    rt.BATCHES["_r10_bot"] = {k: v for k, v in rt.BATCHES[ABSENT_BATCH].items()
                              if k != "skip_bot"}
    rt.select_batch("_r10_bot")
    assert rt.DEPLOY_BOT and rt.BOT_SKIP_REASON is None


def _second_play_times_out(rt, calls):
    """A deploy stub whose FIRST play returns and whose second times out: a partial deploy."""
    inner = _attesting_deploy(rt, calls)

    def _stub(limit, **kw):
        if kw.get("play") and calls:
            raise rt.Fail(_TIMED_OUT)
        return inner(limit, **kw)

    return _stub


def test_r10_m1_the_listing_status_is_the_process_status_and_no_listed_text_is_one(monkeypatch):
    """R9-M1: the rollback gate read its listing's status out of the listing's own text.

    The status marker was a line printed into the same stream as the wrapper's answer, so a
    snapshot description or a wrapper line carrying `SCR-LIST-RC 0` was, to the parser, a status.
    The status is the PROCESS's now: the listing task exits with the wrapper's status under
    ansible's default failure rule, a failed task is a non-zero playbook, the controller-side shell
    exits with that status, and `run_attested` refuses a non-zero process before it parses a word.
    No text is a status."""
    import json
    rt, src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    st = _snap()
    name = st["snapshot"]["name"]
    forged = "\n".join((
        '        "SCR-LIST-RC 0",',
        '        "  `-> %s 2026-09-22 03:00:01     SCR-LIST-RC 0",' % name,
        '        "  `-> current                   You are here!"'))

    def _forged(phase):
        return ('        "SCR-LIST-BEGIN %s %s",\n%s\n        "SCR-LIST-END %s %s"'
                % (phase, NONCE, forged, phase, NONCE))

    sections = [_facts_section(BEFORE_P), _forged(BEFORE_P), _forged(AFTER_P),
                _facts_section(AFTER_P)]

    # (a) the wrapper exited 2, and its answer carries `SCR-LIST-RC 0` twice --
    # once as a wrapper line, once as the recorded snapshot's description. The
    # process status is 2, and that is the only status there is.
    monkeypatch.setattr(rt, "run", _attesting_run(rt, sections=sections, rc=2))
    with pytest.raises(rt.Fail) as exc:
        rt.snapshot_listing()
    assert "exited rc=2" in str(exc.value), str(exc.value)
    # (b) ...so the rollback gate refuses: the recorded name is in the text,
    # and the text is not an answer
    with pytest.raises(rt.Fail) as exc:
        rt.assert_snapshot_still_exists(st)
    assert "exited rc=2" in str(exc.value), str(exc.value)

    # (c) inert twin: the SAME text from a process that exited 0 is a listing,
    # the forged line is a line in it, and the gate passes on the name
    monkeypatch.setattr(rt, "run", _attesting_run(rt, sections=sections, rc=0))
    listing = rt.snapshot_listing()
    assert listing["rc"] == 0, listing
    names, problem = rt.listed_snapshot_names(listing)
    assert names == [name] and problem is None, (names, problem)
    rt.assert_snapshot_still_exists(st)

    # (d) the channel as composed: the listing task keeps ansible's default
    # failure rule and exits with the status it kept; the facts tasks, judged
    # by what they SAY, are the only tasks that opt out; and the shell on the
    # controller exits with the playbook's own status
    book = json.loads(rt.attested_playbook(play_path="/srv/a-play-dir/playbooks/x.yml",
                                           listing=True))
    tasks = [t for p in book for t in (p.get("tasks") or ())]
    listing_tasks = [t for t in tasks if "list-snapshots" in (t.get("shell") or "")]
    assert len(listing_tasks) == 2, listing_tasks
    for task in listing_tasks:
        assert "failed_when" not in task and "ignore_errors" not in task, task
        assert "__scr_list_rc=$?" in task["shell"], task["shell"]
        assert task["shell"].rstrip().endswith("exit $__scr_list_rc"), task["shell"]
    facts_tasks = [t for t in tasks if "SCR-FACTS-BEGIN" in (t.get("shell") or "")]
    assert len(facts_tasks) == 2 and all(t.get("failed_when") is False for t in facts_tasks)
    asked = []
    monkeypatch.setattr(rt, "run", _attesting_run(rt, asked, listing=True, name=name))
    rt.snapshot_listing()
    # R11-L2 (round 12): nothing runs after ansible-playbook -- no removal of a
    # temporary playbook, because there is none -- so the controller's shell
    # exits with the playbook's own status. Said of the command's END: any
    # command appended after the invocation fails this.
    import re as _re
    assert _re.search(r"&& ansible-playbook <\(printf %s '?[A-Za-z0-9+/=]+'? \| base64 -d\) "
                      r"--limit \S+ -e scr_nonce=[0-9a-f]{32}(?: -e \S+)*\Z", asked[-1]), \
        asked[-1]
    # ...and no status marker is left in the train for any text to imitate
    assert "SCR-LIST-RC" not in src


def test_r11_m1_a_listing_is_accepted_only_on_status_zero_and_pcts_closing_entry(monkeypatch,
                                                                                   capsys):
    """R10-M1: a zero status says the wrapper did not fail -- not that it printed a whole listing.

    The rollback prerequisite accepted a listing on its process status alone, and the process
    status is only as good as a wrapper this seat cannot read. So the gate asks for a second,
    POSITIVE signal as well, and takes it from the listing tool itself: `pct listsnapshot` builds
    the whole list before it prints, and prints the container's running state -- `current`, "You
    are here!", the one entry with no snapshot time -- after every snapshot. A listing cut short
    is missing its last line. Neither signal alone is an answer: the entry under a non-zero
    status is text in an answer that failed, and a zero status without it is an answer nothing
    says is whole."""
    rt, src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    st = _snap()
    name = st["snapshot"]["name"]
    snap_line = '        "  `-> %s 2026-09-22 03:00:01     auto snapshot",' % name
    closer = '        "   `-> current                   You are here!"'

    def _section(phase, *lines):
        return ('        "SCR-LIST-BEGIN %s %s",\n%s\n        "SCR-LIST-END %s %s"'
                % (phase, NONCE, "\n".join(lines), phase, NONCE))

    def _answer(before, after, rc=0):
        monkeypatch.setattr(rt, "run", _attesting_run(rt, sections=[
            _facts_section(BEFORE_P), before, after, _facts_section(AFTER_P)], rc=rc))

    def whole(phase):
        return _section(phase, snap_line, closer)

    def headless(phase):
        return _section(phase, snap_line.rstrip(","))

    # (a) the entry is there and the status is not 0: refused, by the status,
    # through the real parser and through the gate alike
    _answer(whole(BEFORE_P), whole(AFTER_P), rc=2)
    with pytest.raises(rt.Fail) as exc:
        rt.assert_snapshot_still_exists(st)
    assert "exited rc=2" in str(exc.value), str(exc.value)
    names, problem = rt.listed_snapshot_names(_listing(name, rc=2))
    assert names == [] and "exited rc=2" in problem, (names, problem)

    # (b) the status is 0 and the entry is NOT there: refused, although the
    # recorded name is in the text and a status-only gate would pass on it
    _answer(headless(BEFORE_P), headless(AFTER_P))
    listing = rt.snapshot_listing()
    assert listing["rc"] == 0 and listing["agree"] is True, listing
    assert rt.cc_names(listing["raw"]) == [name], listing["raw"]
    names, problem = rt.listed_snapshot_names(listing)
    assert names == [] and "does not END with" in problem, (names, problem)
    with pytest.raises(rt.Fail) as exc:
        rt.assert_snapshot_still_exists(st)
    assert "does not END with" in str(exc.value), str(exc.value)
    assert "Nothing has been merged, pushed or deployed" in str(exc.value), str(exc.value)
    _d, lines = _printed_capture(rt, capsys, listing)
    assert "GATE names=0 usable=no" in lines, lines

    # (c) inert twin: status 0 AND the entry as the last line -- accepted,
    # with the entry as ansible's debug renders it (quoted, indented a level)
    _answer(whole(BEFORE_P), whole(AFTER_P))
    listing = rt.snapshot_listing()
    names, problem = rt.listed_snapshot_names(listing)
    assert names == [name] and problem is None, (names, problem)
    rt.assert_snapshot_still_exists(st)
    _d, lines = _printed_capture(rt, capsys, listing)
    assert "GATE names=1 usable=yes" in lines, lines

    # (d) the entry is there with a line AFTER it -- a listing cut short on a
    # rolled-back history looks exactly like this, and so does one with a line
    # appended: refused, and the refusal says which case it cannot tell apart
    later = '        "  `-> cc_pre-bug392-merge__20260922_040000 2026-09-22 04:00:00     auto"'
    _answer(_section(BEFORE_P, snap_line, closer + ",", later),
            _section(AFTER_P, snap_line, closer + ",", later))
    names, problem = rt.listed_snapshot_names(rt.snapshot_listing())
    assert names == [] and "does not END with" in problem, (names, problem)
    assert "rolled back onto an older branch" in problem, problem

    # (e) the last line CONTAINS the entry's words and is not the entry: a
    # snapshot whose description spells it, and the entry with text after it
    for last in ('        "  `-> %s 2026-09-22 03:00:01     `-> current  You are here!"' % name,
                 '        "   `-> current                   You are here! (appended)"'):
        _answer(_section(BEFORE_P, snap_line, last), _section(AFTER_P, snap_line, last))
        names, problem = rt.listed_snapshot_names(rt.snapshot_listing())
        assert names == [] and "does not END with" in problem, (last, names, problem)

    # (f) the SECOND reading cut short: the two readings carry the same names
    # and the same status, and only one of them is whole -- a picture of two
    # moments, refused as one
    _answer(whole(BEFORE_P), headless(AFTER_P))
    listing = rt.snapshot_listing()
    assert listing["agree"] is False, listing
    with pytest.raises(rt.Fail) as exc:
        rt.assert_snapshot_still_exists(st)
    assert "picture of two moments" in str(exc.value), str(exc.value)

    # (g) the marker is the tool's, said of the pattern itself: anchored at
    # both ends of one whole line, and the one entry pct cannot give a
    # snapshot's name
    assert rt._LISTING_CLOSER.pattern.startswith("\\A`->"), rt._LISTING_CLOSER.pattern
    assert rt._LISTING_CLOSER.pattern.endswith("You are here!\\Z"), rt._LISTING_CLOSER.pattern
    assert rt.listing_complete("  `-> current   You are here!") is True
    assert rt.listing_complete("") is False and rt.listing_complete(None) is False


def test_r11_m1_the_listing_is_read_in_the_yaml_form_the_controller_prints(monkeypatch, capsys):
    """Found by running: the controller prints a listed `stdout_lines` as YAML, not JSON.

    Every fixture above renders ansible's debug list as JSON -- `"<line>",` -- and the first
    live run of the round-11 gate refused a listing that was whole and ENDED with pct's closing
    entry: this controller prints each line as a YAML item, `- '<line>'`, and the item marker of
    the closing section marker is left as a bare `-` at the end of the body. The shape below is
    the live one with synthetic names: an empty remainder after the opening marker, the tree
    indented one column per level, the closing entry last, then that bare marker. The gate
    reads it whole; the same shape cut short, or with a line after the entry, is refused."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    st = _snap()
    name = st["snapshot"]["name"]
    older = "cc_auto__20260920_030000"
    tree = ["  - '`-> %s 2026-09-20 03:00:00     auto snapshot: auto'" % older,
            "  - ' `-> %s 2026-09-22 03:00:01     auto snapshot: pre-bug392-merge'" % name]
    closer = "  - '  `-> current                                   You are here!'"

    def _section(phase, *lines):
        return ("  - SCR-LIST-BEGIN %s %s\n%s\n  - SCR-LIST-END %s %s"
                % (phase, NONCE, "\n".join(lines), phase, NONCE))

    def _answer(*lines):
        monkeypatch.setattr(rt, "run", _attesting_run(rt, sections=[
            _facts_section(BEFORE_P), _section(BEFORE_P, *lines), _section(AFTER_P, *lines),
            _facts_section(AFTER_P)]))

    # (a) the live shape, whole: every line of the body normalised, the closing
    # entry the last of them, and the gate reads the answer
    _answer(*(tree + [closer]))
    listing = rt.snapshot_listing()
    assert listing["rc"] == 0 and listing["agree"] is True, listing
    kept = rt._listing_lines(listing["raw"])
    assert kept[-1] == "`-> current                                   You are here!", kept
    assert rt.listing_complete(listing["raw"]) is True, kept
    names, problem = rt.listed_snapshot_names(listing)
    assert names == [name] and problem is None, (names, problem)
    rt.assert_snapshot_still_exists(st)
    _d, lines = _printed_capture(rt, capsys, listing)
    assert "GATE names=1 usable=yes" in lines, lines

    # (b) the same shape cut short -- no closing entry: refused
    _answer(*tree)
    names, problem = rt.listed_snapshot_names(rt.snapshot_listing())
    assert names == [] and "does not END with" in problem, (names, problem)

    # (c) the entry with a later item after it: refused, and named
    _answer(*(tree + [closer, "  - '`-> cc_auto__20260923_030000 2026-09-23 03:00:00     "
                              "auto snapshot: auto'"]))
    names, problem = rt.listed_snapshot_names(rt.snapshot_listing())
    assert names == [] and "rolled back onto an older branch" in problem, (names, problem)

    # (d) ONE item marker comes off, never two: a nested item is not the entry
    assert rt.listing_complete("  - - '`-> current   You are here!'") is False
    assert rt.listing_complete("  - '`-> current   You are here!'\n  -") is True
    assert rt._listing_lines("  -\n-\n  - ''") == []


def test_r12_m1_a_name_only_in_a_description_is_not_a_listed_snapshot(monkeypatch, capsys):
    """R11-M1: a snapshot is named by pct's NAME FIELD, never by a token anywhere in the listing.

    pct prints one entry per snapshot -- "`->", the name, the moment it was taken, the first line
    of the description -- and a description is free text whoever takes a snapshot writes. The
    listing was read as whole tokens ANYWHERE, so once the rollback point was deleted, another
    snapshot whose description carried its name made the gate report it listed and the deploy
    walk on. Every reader of the listing now takes the name field: the gate's names, the moment
    beside a name, and the capture's records. Failure direction: refusal -- a recorded name
    that survives only in a description is not listed, and nothing is merged or deployed."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    st = _snap()
    name = st["snapshot"]["name"]
    other = "cc_auto__20260920_030000"
    closer = "  - '  `-> current                                   You are here!'"
    # another snapshot, whose description carries the recorded name and a zoned moment
    described = ("  - '`-> %s 2026-09-20 03:00:00     copy of %s 2026-09-22 03:00:01Z'"
                 % (other, name))
    named = "  - ' `-> %s 2026-09-22 03:00:01     auto snapshot: pre-bug392-merge'" % name

    def _section(phase, *lines):
        return ("  - SCR-LIST-BEGIN %s %s\n%s\n  - SCR-LIST-END %s %s"
                % (phase, NONCE, "\n".join(lines), phase, NONCE))

    def _answer(*lines):
        monkeypatch.setattr(rt, "run", _attesting_run(rt, sections=[
            _facts_section(BEFORE_P), _section(BEFORE_P, *lines), _section(AFTER_P, *lines),
            _facts_section(AFTER_P)]))

    # (a) REFUSED: the rollback point is gone and another snapshot's description names it --
    # read through the controller's own YAML form by the real parser
    _answer(described, closer)
    listing = rt.snapshot_listing()
    assert listing["rc"] == 0 and rt.listing_complete(listing["raw"]), listing
    names, problem = rt.listed_snapshot_names(listing)
    assert names == [] and problem is None, (names, problem)
    with pytest.raises(rt.Fail) as exc:
        rt.assert_snapshot_still_exists(st)
    assert "is not in the container's snapshot listing" in str(exc.value), str(exc.value)
    # ...the moment beside it is not read out of the other snapshot's description either
    taken, why = rt.listed_snapshot_time(listing, name)
    assert taken is None and why == "the listing carries no line for it", (taken, why)
    # ...and the capture writes no record of it: that line is dropped and counted
    _d, lines = _printed_capture(rt, capsys, listing)
    written = "\n".join(lines)
    assert "SNAPSHOT name=%s" % name not in written, written
    assert "GATE names=0 usable=yes" in written, written

    # (b) ACCEPTED: the same listing with the name in a name field
    _answer(described, named, closer)
    listing = rt.snapshot_listing()
    names, problem = rt.listed_snapshot_names(listing)
    assert names == [name] and problem is None, (names, problem)
    rt.assert_snapshot_still_exists(st)
    taken, why = rt.listed_snapshot_time(listing, name)
    assert taken is None and "names no zone" in why, (taken, why)
    _d, lines = _printed_capture(rt, capsys, listing)
    written = "\n".join(lines)
    assert "SNAPSHOT name=%s taken=2026-09-22 03:00:01 zone=none" % name in written, written
    assert "GATE names=1 usable=yes" in written, written

    # (c) the zone: pct's time field is 23 wide and the description follows it, so a
    # description that BEGINS with a zone word is not the zone of the moment beside it...
    for word in ("UTC nightly", "Z", "+02:00 local"):
        zoned = _listing_raw("  `-> %s 2026-09-22 03:00:01     %s\n"
                             "  `-> current                   You are here!" % (name, word))
        taken, why = rt.listed_snapshot_time(zoned, name)
        assert taken is None and "names no zone" in why, (word, taken, why)
    # ...while a zone the timestamp itself states is read
    zoned = _listing_raw("  `-> %s 2026-09-22 03:00:01 UTC     auto snapshot\n"
                         "  `-> current                   You are here!" % name)
    taken, why = rt.listed_snapshot_time(zoned, name)
    assert taken is not None and why is None, (taken, why)

    # (d) a deleted rollback point whose name is only in a description REFUSES DEPLOYMENT: the
    # code phase stops before any ref moves, and its inert twin walks on to the merge
    _attested(monkeypatch, rt)
    go = SimpleNamespace(go=True)
    monkeypatch.setattr(rt, "save_state", lambda st_: None)
    stub, log = _fake_git(rt, _bound_refs(rt), trees={REVIEWED_FULL: REVIEWED_TREE})
    monkeypatch.setattr(rt, "run", stub)
    monkeypatch.setattr(rt, "snapshot_listing", lambda values=None: _listing_raw(
        "  `-> %s 2026-09-20 03:00:00     copy of %s\n"
        "  `-> current                   You are here!" % (other, name)))
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, _snap())
    assert "is not in the container's snapshot listing" in str(exc.value), str(exc.value)
    assert log == ["git status --porcelain"], log
    _snapshot_is_listed(monkeypatch, rt)
    with pytest.raises(_NoCommand) as exc:
        rt.phase_code(go, dict(_snap(), pre_code_old_build=True))
    assert str(exc.value).startswith("git checkout main")


def _posix_bash():
    """A bash with process substitution: Git's own on Windows (never the WSL launcher on the
    PATH), the system's elsewhere. None when there is none."""
    import os as _os
    import shutil as _sh
    if _os.name == "nt":
        git = _sh.which("git")
        if not git:
            return None
        # git.exe sits in cmd/, bin/ or mingw64/bin/ of the installation, and the
        # shell in usr/bin/ of its root: walk up until that root is found
        here = _os.path.dirname(_os.path.realpath(git))
        for _level in range(4):
            cand = _os.path.join(here, "usr", "bin", "bash.exe")
            if _os.path.isfile(cand):
                return cand
            here = _os.path.dirname(here)
        return None
    return _sh.which("bash")


def test_r12_l2_the_playbook_reaches_the_controller_as_a_pipe_and_no_file_is_written(
        monkeypatch, tmp_path):
    """R11-L2: every attested run -- the real listing capture's included -- wrote its composed
    playbook to a temporary file on the controller.

    The command decoded the playbook into `$(mktemp)`, ran ansible-playbook on it and removed it.
    The shell now decodes it into a PIPE (process substitution) that ansible-playbook reads in
    place of a file, so nothing is created and nothing is removed. Asserted on the command
    `snapshot_listing` composes, and by RUNNING that exact command in a real POSIX shell whose
    `ansible-playbook` is a shell function reporting what it was handed: whether that is a
    regular file, how many entries the scratch temp directory holds while it runs, and the
    playbook it read. The live proof on the controller is the read-only `check
    --capture-listing` at the pin tip; this observes the shell's half on this seat."""
    import os
    import re as _re
    import subprocess
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    name = _snap()["snapshot"]["name"]
    inner = []
    answer = _attesting_run(rt, listing=True, name=name)

    def _run(cmd, **kw):
        inner.append(cmd[-1])
        return answer(cmd, **kw)

    monkeypatch.setattr(rt, "run", _run)
    listing = rt.snapshot_listing()
    assert rt.listed_snapshot_names(listing) == ([name], None)
    sent = inner[-1]
    # (a) the command: no temporary file, no removal, and ansible-playbook is the LAST
    # command, so the status the shell exits with is the playbook's own
    assert "mktemp" not in sent and "rm -f" not in sent and "__scr_rc" not in sent, sent
    shape = _re.search(r"&& ansible-playbook <\(printf %s '?([A-Za-z0-9+/=]+)'? \| base64 -d\) "
                       r"--limit \S+ -e scr_nonce=[0-9a-f]{32}(?: -e \S+)*\Z", sent)
    assert shape, sent
    blob = shape.group(1)
    # (b) the command, RUN
    bash = _posix_bash()
    if bash is None:
        pytest.skip("no POSIX bash with process substitution on this machine")
    home = tmp_path / "home"
    venv = home / "zap" / ".venv" / "bin"
    venv.mkdir(parents=True)
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    (venv / "activate").write_bytes(
        b'ansible-playbook() {\n'
        b'  if [ -f "$1" ]; then echo "SCR-L2 REGULAR"; else echo "SCR-L2 NOT-REGULAR"; fi\n'
        b'  echo "SCR-L2 TMP $(ls -A "$TMPDIR" | wc -l)"\n'
        b'  echo "SCR-L2 BOOK $(cat "$1" | base64 | tr -d \'\\n\')"\n'
        b'  return "${SCR_L2_RC:-0}"\n'
        b'}\n')
    env = dict(os.environ, HOME=home.as_posix(), TMPDIR=tmpdir.as_posix())
    for rc in (0, 5):
        env["SCR_L2_RC"] = str(rc)
        done = subprocess.run([bash, "-c", sent], env=env, capture_output=True, timeout=120)
        out = done.stdout.decode("utf-8", "replace")
        assert done.returncode == rc, (rc, done.returncode, out, done.stderr)
        assert "SCR-L2 NOT-REGULAR" in out and "SCR-L2 REGULAR" not in out, out
        assert _re.search(r"SCR-L2 TMP\s+0\s", out), out
        read = _re.search(r"SCR-L2 BOOK (\S+)", out)
        assert read and read.group(1) == blob, (out, blob)
    # ...and nothing was left anywhere under the scratch tree
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == [
        "home", "home/zap", "home/zap/.venv", "home/zap/.venv/bin",
        "home/zap/.venv/bin/activate", "tmp"]


def test_r10_m2_a_box_that_does_not_serve_the_new_build_stops_the_next_box_play(monkeypatch):
    """R9-M2: what the primary SERVES was asked only after both plays had run.

    A clone at the deployed id and a liveness 200 are both true of a container whose restart did
    nothing, and the round before asked the semantic question only after the standby had been
    deployed too -- so the ordering that keeps the authoritative box ahead of the box serving the
    routed reads (#266) held for the clones and not for the code. Each box is now asked, alone,
    before the next box's play is started: the code phase asks for the NEW build, the precursor
    phase for the OLD one. (The remapped-selector arms, which refuse with zero plays, are (e),
    (e2) and (f) of the per-box attestation test.)"""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    rt.attest_deploy_selectors()
    for name, stub in (("assert_control", lambda host: None),
                       ("assert_route_probes", lambda hosts: None),
                       ("assert_health_keys", lambda hosts: None),
                       ("assert_edge_runs_new_code", lambda: None),
                       ("save_state", lambda st_: None),
                       ("run", _no_command)):
        monkeypatch.setattr(rt, name, stub)

    # (a) the primary's play returned, its clone is at the id and its control
    # answers -- and it still serves the OLD build (a restart that did
    # nothing), or neither build, or its control is down. The standby's play
    # is never started.
    for reading, says in ((_OLD_BUILD, "still serving the OLD build"),
                          ((True, False, False, ["alias unknown"]), "neither build"),
                          ((False, False, False, []), "is not 200")):
        calls = []
        monkeypatch.setattr(rt, "run_attested", _attesting_deploy(rt, calls))
        monkeypatch.setattr(rt, "code_state", lambda host, _r=reading: _r)
        with pytest.raises(rt.Fail) as exc:
            rt._deploy_both(MERGE_FULL, after_box=rt.assert_box_runs_new)
        assert says in str(exc.value), (says, str(exc.value))
        assert "other box has not been deployed to" in str(exc.value), str(exc.value)
        assert [c[1] for c in calls] == [SEAT_PRIMARY_LIMIT], (says, calls)

    # (b) inert twin: the primary serves the new build, so the standby is
    # deployed after it, and each box was asked once, in that order
    calls, asked = [], []
    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(rt, calls))
    monkeypatch.setattr(rt, "code_state", lambda host: asked.append(host) or _NEW_BUILD)
    rt._deploy_both(MERGE_FULL, after_box=rt.assert_box_runs_new)
    assert [c[1] for c in calls] == [SEAT_PRIMARY_LIMIT, SEAT_STANDBY_LIMIT], calls
    assert asked == [rt.PRIMARY, rt.STANDBY], asked

    # (c) the code phase hands its deploy that question: a resumed code phase
    # whose primary does not serve the new build stops before the standby's
    # play and leaves its attempt sentinel (R9-M3), never a success
    _snapshot_is_listed(monkeypatch, rt)
    monkeypatch.setattr(rt, "assert_clean_tree", lambda *a, **k: None)
    monkeypatch.setattr(rt, "assert_reviewed_provenance", lambda st_: MERGE_FULL)
    monkeypatch.setattr(rt, "assert_remote_main_is", lambda sha: None)
    calls = []
    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(rt, calls))
    monkeypatch.setattr(rt, "code_state", lambda host: _OLD_BUILD)
    st = dict(_snap(), pre_code_old_build=True, code_sha=MERGE_FULL, code_deployed=True)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(SimpleNamespace(go=True), st)
    assert "still serving the OLD build" in str(exc.value), str(exc.value)
    assert [c[1] for c in calls] == [SEAT_PRIMARY_LIMIT], calls
    assert st["code_deployed"] == rt.ATTEMPTED, st.get("code_deployed")
    # ...inert twin: the same resume with the new build live on each box
    calls = []
    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(rt, calls))
    monkeypatch.setattr(rt, "code_state", lambda host: _NEW_BUILD)
    st = dict(_snap(), pre_code_old_build=True, code_sha=MERGE_FULL)
    rt.phase_code(SimpleNamespace(go=True), st)
    assert [c[1] for c in calls] == [SEAT_PRIMARY_LIMIT, SEAT_STANDBY_LIMIT], calls
    assert st["code_deployed"] is True, st.get("code_deployed")

    # (d) the precursor phase asks each box the opposite question: a FILES-ONLY
    # deploy that left the primary serving the NEW build carried code, and the
    # standby's play is never started
    monkeypatch.setattr(rt, "ALL_SQL", ["a-file.sql"])
    calls = []
    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(rt, calls))
    monkeypatch.setattr(rt, "code_state", lambda host: _NEW_BUILD)
    st = {"precursor_sha": MERGE_FULL}
    with pytest.raises(rt.Fail) as exc:
        rt.phase_deploy_precursor(SimpleNamespace(go=True), st)
    assert "does not read as the OLD build after a FILES-ONLY deploy" in str(exc.value)
    assert "other box has not been deployed to" in str(exc.value), str(exc.value)
    assert [c[1] for c in calls] == [SEAT_PRIMARY_LIMIT], calls
    assert st["precursor_deployed"] == rt.ATTEMPTED, st
    # ...inert twin: both boxes still on the old build, one after the other
    calls = []
    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(rt, calls))
    monkeypatch.setattr(rt, "code_state", lambda host: _OLD_BUILD)
    st = {"precursor_sha": MERGE_FULL}
    rt.phase_deploy_precursor(SimpleNamespace(go=True), st)
    assert [c[1] for c in calls] == [SEAT_PRIMARY_LIMIT, SEAT_STANDBY_LIMIT], calls
    assert st["precursor_deployed"] is True, st


def test_r10_m3_an_attempt_that_does_not_finish_leaves_a_word_no_gate_accepts(monkeypatch,
                                                                             tmp_path, capsys):
    """R9-M3: a success an earlier attempt recorded stood over an attempt that did not finish.

    `REFUSED` replaced a standing True only on the paths that went through the attestation
    refusal. A timeout, an exception, or a postcondition that failed after a play had returned
    raised straight past it, so the earlier run's True was still in the state file, and `--from
    i18n` then ran the batch's files behind a deploy that had stopped half way. Every mutating
    phase now persists its attempt sentinel before its first mutating command and writes the exact
    True only after its postcondition. Each arm uses a REAL state file under the test's temporary
    directory: the word checked is what a later process reads back."""
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _state_under(monkeypatch, rt, tmp_path / "train-state.json")
    _attested(monkeypatch, rt)
    _snapshot_is_listed(monkeypatch, rt)
    for name, stub in (("assert_control", lambda host: None),
                       ("assert_route_probes", lambda hosts: None),
                       ("assert_health_keys", lambda hosts: None),
                       ("assert_edge_runs_new_code", lambda: None),
                       ("assert_clean_tree", lambda *a, **k: None),
                       ("assert_reviewed_provenance", lambda st_: MERGE_FULL),
                       ("assert_remote_main_is", lambda sha: None),
                       ("assert_provenance_up_front", lambda args, st_: None),
                       ("check_migration", lambda f, out: None),
                       ("sql", lambda host, query: "1"),
                       ("run", _no_command)):
        monkeypatch.setattr(rt, name, stub)
    go = SimpleNamespace(go=True)

    # (a) the code phase. An earlier attempt's True is in the file; this
    # attempt deploys the primary and times out on the standby -- a PARTIAL
    # deploy. The file reads ATTEMPTED, and `--from i18n` refuses.
    rt.save_state(dict(_snap(), pre_code_old_build=True, code_sha=MERGE_FULL,
                       code_deployed=True))
    calls = []
    monkeypatch.setattr(rt, "run_attested", _second_play_times_out(rt, calls))
    monkeypatch.setattr(rt, "code_state", lambda host: _NEW_BUILD)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, rt.load_state())
    assert "did not answer within" in str(exc.value), str(exc.value)
    assert [c[1] for c in calls] == [SEAT_PRIMARY_LIMIT], calls
    assert rt.load_state()["code_deployed"] == rt.ATTEMPTED, rt.load_state()
    capsys.readouterr()
    rc = _cli(monkeypatch, rt, "--batch", ABSENT_BATCH, "run", "--go", "--from", "i18n")
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "GATE FAILED in phase 'i18n'" in out, out
    assert "code SHA is not live on both boxes" in out, out
    assert "i18n_done" not in rt.load_state(), rt.load_state()
    # ...inert twin: the attempt that FINISHES writes the exact True, and the
    # same `--from i18n` passes that gate
    calls = []
    monkeypatch.setattr(rt, "run_attested", _attesting_deploy(rt, calls))
    rt.phase_code(go, rt.load_state())
    assert rt.load_state()["code_deployed"] is True, rt.load_state()
    ran = []
    monkeypatch.setattr(rt, "PHASES", [(n, (lambda args, st_, _n=n: ran.append(_n))
                                        if n == "verify" else f) for n, f in rt.PHASES])
    rc = _cli(monkeypatch, rt, "--batch", ABSENT_BATCH, "run", "--go", "--from", "i18n")
    out = capsys.readouterr().out
    assert rc == 0, out
    assert rt.load_state()["i18n_done"] is True and ran == ["verify"], (rt.load_state(), ran)

    # (b) the precursor deploy: the standby's play times out after the
    # primary's. The file reads ATTEMPTED and the schema phase refuses to apply
    # migrations read from files nothing has proved are on the boxes.
    monkeypatch.setattr(rt, "ALL_SQL", ["a-file.sql"])
    monkeypatch.setattr(rt, "SCHEMA_SQL", ["a-file.sql"])
    monkeypatch.setattr(rt, "schema_state", lambda host: ([], []))
    migrated = []
    monkeypatch.setattr(rt, "ssh", lambda host, verb: migrated.append(verb) or "")
    rt.save_state({"precursor_sha": MERGE_FULL, "precursor_deployed": True})
    calls = []
    monkeypatch.setattr(rt, "run_attested", _second_play_times_out(rt, calls))
    monkeypatch.setattr(rt, "code_state", lambda host: _OLD_BUILD)
    with pytest.raises(rt.Fail) as exc:
        rt.phase_deploy_precursor(go, rt.load_state())
    assert "did not answer within" in str(exc.value), str(exc.value)
    assert [c[1] for c in calls] == [SEAT_PRIMARY_LIMIT], calls
    assert rt.load_state()["precursor_deployed"] == rt.ATTEMPTED, rt.load_state()
    with pytest.raises(rt.Fail) as exc:
        rt.phase_schema(go, rt.load_state())
    assert "precursor deploy has not passed" in str(exc.value), str(exc.value)
    assert rt.ATTEMPTED in str(exc.value) and migrated == [], (str(exc.value), migrated)

    # (c) the schema phase: a migration times out. The file reads ATTEMPTED
    # and the code phase refuses to boot the new api against that schema.
    def _migrate_times_out(host, verb):
        migrated.append(verb)
        raise rt.Fail(_TIMED_OUT)

    monkeypatch.setattr(rt, "ssh", _migrate_times_out)
    rt.save_state(dict(_snap(), precursor_deployed=True, schema_done=True))
    with pytest.raises(rt.Fail) as exc:
        rt.phase_schema(go, rt.load_state())
    assert migrated == ["migrate:a-file.sql"], migrated
    assert rt.load_state()["schema_done"] == rt.ATTEMPTED, rt.load_state()
    with pytest.raises(rt.Fail) as exc:
        rt.phase_code(go, rt.load_state())
    assert "schema phase has not passed" in str(exc.value), str(exc.value)

    # (d) the i18n phase, in a batch that deploys the bot: a migration times
    # out. The file reads ATTEMPTED and the bot phase refuses.
    _bot_batch(rt)
    monkeypatch.setattr(rt, "POST_CODE_SQL", ["a-file.sql"])
    migrated[:] = []
    rt.save_state({"code_deployed": True, "i18n_done": True})
    with pytest.raises(rt.Fail) as exc:
        rt.phase_i18n(go, rt.load_state())
    assert migrated == ["migrate:a-file.sql"], migrated
    assert rt.load_state()["i18n_done"] == rt.ATTEMPTED, rt.load_state()
    deployed = []
    monkeypatch.setattr(rt, "ssh", lambda host, verb: deployed.append(verb) or "Started")
    with pytest.raises(rt.Fail) as exc:
        rt.phase_bot(go, rt.load_state())
    assert "i18n phase has not passed" in str(exc.value) and deployed == [], str(exc.value)

    # (e) the bot phase: the deploy verb answered and the witness never saw a
    # steady bot. The file reads ATTEMPTED, and verify refuses -- and leaves
    # its OWN sentinel where an earlier verify's backed True stood.
    def _unwitnessed(**kw):
        raise rt.Fail("the bot was not witnessed Up over two steady samples")

    monkeypatch.setattr(rt, "_bot_witness", _unwitnessed)
    rt.save_state({"code_deployed": True, "i18n_done": True, "bot_deployed": True,
                   "code_sha": MERGE_FULL, "verified": True,
                   "verified_evidence": {"code_sha": MERGE_FULL, "mode": "GO",
                                         "at": "2026-09-22T03:00:00+00:00"}})
    with pytest.raises(rt.Fail) as exc:
        rt.phase_bot(go, rt.load_state())
    assert deployed == ["deploy-bot"], deployed
    assert rt.load_state()["bot_deployed"] == rt.ATTEMPTED, rt.load_state()
    with pytest.raises(rt.Fail) as exc:
        rt.phase_verify(go, rt.load_state())
    assert "bot phase has not passed" in str(exc.value), str(exc.value)
    assert rt.load_state()["verified"] == rt.ATTEMPTED, rt.load_state()


def test_r10_m4_the_seat_file_is_read_once_and_a_replacement_cannot_make_a_hybrid(monkeypatch,
                                                                                  tmp_path):
    """R9-M4: every seat key re-opened the seat file, and its digest was a third read.

    An atomic replacement between two of those reads handed one process a controller from one
    version of the file and a selector from the next, and the digest recorded beside them matched
    neither. The file is read ONCE, as bytes; the digest is the digest of those bytes; every key is
    parsed out of them. Here the file is REPLACED on disk the moment the first read has taken its
    bytes, and every value and the digest must still be the first version's."""
    import builtins
    import hashlib
    import io
    import json
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    for env in rt.IDENTIFIERS.values():
        monkeypatch.delenv(env, raising=False)
    first = {"controller": SEAT_CONTROLLER, "pve_group": SEAT_PVE_GROUP,
             "origin_url": ORIGIN_URL, "primary_limit": SEAT_PRIMARY_LIMIT,
             "standby_limit": SEAT_STANDBY_LIMIT, "play_dir": SEAT_PLAY_DIR}
    second = {"controller": "a-different-controller", "pve_group": "a-group-2",
              "origin_url": ORIGIN_URL, "primary_limit": "a-second-group",
              "standby_limit": "a-node", "play_dir": "/srv/a-play-dir/elsewhere"}
    assert set(first) == set(rt.IDENTIFIERS), sorted(rt.IDENTIFIERS)
    first_bytes = json.dumps(first).encode("utf-8")
    second_bytes = json.dumps(second).encode("utf-8")
    conf = tmp_path / "train.conf.json"
    conf.write_bytes(first_bytes)
    monkeypatch.setattr(rt, "TRAIN_CONF", str(conf))
    rt._SEAT_SNAPSHOT.clear()
    rt._SEAT_FILE.clear()
    opens = []
    real_open = builtins.open

    def _counting_open(file, *args, **kw):
        if isinstance(file, (str, os.PathLike)) and os.path.abspath(str(file)) == str(conf):
            opens.append(args[0] if args else kw.get("mode", "r"))
            if len(opens) == 1:
                with real_open(file, "rb") as fh:
                    data = fh.read()
                conf.write_bytes(second_bytes)     # replaced right after the first read
                return io.BytesIO(data)
        return real_open(file, *args, **kw)

    monkeypatch.setattr(builtins, "open", _counting_open)
    values = {key: rt.require_identifier(key) for key in rt.IDENTIFIERS}
    digests = rt.seat_binding_digests(rt.seat_values())
    monkeypatch.setattr(builtins, "open", real_open)
    # (a) one open, as bytes
    assert opens == ["rb"], opens
    # (b) no hybrid: every value is the first version's, and so is the digest
    assert values == first, sorted(k for k in first if values.get(k) != first[k])
    assert digests["conf"] == hashlib.sha256(first_bytes).hexdigest()
    assert digests["conf"] != hashlib.sha256(second_bytes).hexdigest()
    # (c) negative control for the fixture itself: the replacement really is on
    # disk, so a SECOND read -- a new process's -- sees the other version
    assert conf.read_bytes() == second_bytes
    rt._SEAT_FILE.clear()
    rt._SEAT_SNAPSHOT.pop("controller")
    assert rt.require_identifier("controller") == second["controller"]
    assert rt.seat_file_digest() == hashlib.sha256(second_bytes).hexdigest()


# Where each status key is READ, per function. Every read is `<read> is True`,
# `<read> is not True` or `_status_word(<read>)` -- nothing takes a truth value
# of one. Pinned, so a new read anywhere is a change this test makes somebody
# look at (#432: the defect is a class, and a class is swept, not grepped for
# the one line a finding named).
_GATE_READS = {
    "verified_is_backed": {"verified": 1},
    "repair_state": {"verified": 1},
    "state_summary": {"verified": 2, "code_deployed": 1, "pre_code_old_build": 1,
                      "precursor_deployed": 1, "i18n_done": 1, "bot_deployed": 1,
                      "schema_done": 1},
    "phase_schema": {"precursor_deployed": 2},
    "phase_code": {"schema_done": 2, "pre_code_old_build": 1},
    "phase_i18n": {"code_deployed": 1},
    "phase_bot": {"i18n_done": 2, "code_deployed": 2},
    "phase_verify": {"bot_deployed": 2},
}


def _gate_reads(src, keys):
    """(reads per function, reads in any other form, non-literal reads of `st`) -- by AST."""
    import ast
    tree = ast.parse(src)
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    def function_of(node):
        while node in parent:
            node = parent[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node.name
        return "<module>"

    def literal(node):
        return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) \
            else None

    counts, other, dynamic = {}, [], []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args):
            key, target = literal(node.args[0]), node.func.value
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            key, target = literal(node.slice), node.value
        else:
            continue
        if key is None:
            if isinstance(target, ast.Name) and target.id == "st":
                dynamic.append((function_of(node), node.lineno))
            continue
        if key not in keys:
            continue
        fn = function_of(node)
        counts.setdefault(fn, {}).setdefault(key, 0)
        counts[fn][key] += 1
        up = parent.get(node)
        exact = (isinstance(up, ast.Compare) and up.left is node and len(up.ops) == 1
                 and isinstance(up.ops[0], (ast.Is, ast.IsNot))
                 and isinstance(up.comparators[0], ast.Constant)
                 and up.comparators[0].value is True)
        worded = (isinstance(up, ast.Call) and isinstance(up.func, ast.Name)
                  and up.func.id == "_status_word" and len(up.args) == 1
                  and up.args[0] is node)
        if not (exact or worded):
            other.append((fn, key, node.lineno))
    return counts, other, dynamic


def test_r10_m5_every_gate_accepts_only_the_exact_success_word(monkeypatch):
    """R9-M5: the gates read their predecessors' statuses as truth values.

    `REFUSED` and `ATTEMPTED` are non-empty words, so a truth test read either as the phase
    having passed. Every gate reading a status accepts only the exact True its predecessor's
    postcondition writes. The class is swept by AST with a count per function, and each gate has a
    control: `REFUSED` (and the sentinel, and any other truthy value) is refused; the exact True
    passes that gate."""
    rt, src = _release_train()

    # (a) the sweep, over the train's own source
    counts, other, dynamic = _gate_reads(src, set(rt.GATE_KEYS))
    assert other == [], other
    assert dynamic == [], dynamic
    assert counts == _GATE_READS, counts
    assert sum(sum(v.values()) for v in counts.values()) == 22
    # ...and its negative control: a truth test planted in a function IS found
    planted = ("def phase_x(st):\n    if not st.get('code_deployed'):\n        pass\n"
               "    return st['bot_deployed'] and st.get(k)\n")
    _c, found, dyn = _gate_reads(planted, set(rt.GATE_KEYS))
    assert found == [("phase_x", "code_deployed", 2), ("phase_x", "bot_deployed", 4)], found
    assert dyn == [("phase_x", 4)], dyn

    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    _attested(monkeypatch, rt)
    _snapshot_is_listed(monkeypatch, rt)
    for name, stub in (("save_state", lambda st_: None),
                       ("assert_clean_tree", lambda *a, **k: None),
                       ("assert_reviewed_provenance", lambda st_: MERGE_FULL),
                       ("check_migration", lambda f, out: None),
                       ("schema_state", lambda host: ([], [])),
                       ("index_state", lambda host: []),
                       ("sql", lambda host, query: "1"),
                       ("run", _no_command)):
        monkeypatch.setattr(rt, name, stub)
    go = SimpleNamespace(go=True)
    words = ("REFUSED", rt.ATTEMPTED, "yes", 1)

    # (b) the precursor gate, in the schema phase of a migration batch
    monkeypatch.setattr(rt, "ALL_SQL", ["a-file.sql"])
    monkeypatch.setattr(rt, "SCHEMA_SQL", ["a-file.sql"])
    for attr in ("EXPECT_TABLES", "EXPECT_COLUMNS", "EXPECT_INDEXES"):
        monkeypatch.setattr(rt, attr, [])
    migrated = []
    monkeypatch.setattr(rt, "ssh", lambda host, verb: migrated.append(verb) or "")
    for word in words:
        st = {"precursor_deployed": word}
        with pytest.raises(rt.Fail) as exc:
            rt.phase_schema(go, st)
        assert "precursor deploy has not passed" in str(exc.value), (word, str(exc.value))
        assert migrated == [] and "schema_done" not in st, (word, migrated, st)
    st = {"precursor_deployed": True}
    rt.phase_schema(go, st)                                  # inert twin
    assert migrated == ["migrate:a-file.sql"] and st["schema_done"] is True, (migrated, st)

    # (c) the schema gate, in the code phase of a migration batch
    for word in words:
        st = dict(_snap(), schema_done=word)
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(go, st)
        assert "schema phase has not passed" in str(exc.value), (word, str(exc.value))
        assert "code_deployed" not in st, (word, st)
    # inert twin: the exact True passes this gate, and the phase goes on to
    # its first command -- the checkout, which this test's `run` refuses
    with pytest.raises(_NoCommand) as exc:
        rt.phase_code(go, dict(_snap(), schema_done=True))
    assert "checkout" in str(exc.value), str(exc.value)

    # (d) the old-build control, in the code phase of a no-migration batch:
    # anything but the exact True re-reads both boxes before any command
    rt.select_batch(ABSENT_BATCH)
    assert not rt.ALL_SQL
    reads = []
    monkeypatch.setattr(rt, "code_state", lambda host: reads.append(host) or _NEW_BUILD)
    for word in words:
        reads[:] = []
        with pytest.raises(rt.Fail) as exc:
            rt.phase_code(go, dict(_snap(), pre_code_old_build=word))
        assert "does not read as the OLD build BEFORE" in str(exc.value), (word, str(exc.value))
        assert reads == [rt.PRIMARY], (word, reads)
    reads[:] = []
    with pytest.raises(_NoCommand):                          # inert twin
        rt.phase_code(go, dict(_snap(), pre_code_old_build=True))
    assert reads == [], reads

    # (e) the code gate, in the i18n phase
    for word in words:
        st = {"code_deployed": word}
        with pytest.raises(rt.Fail) as exc:
            rt.phase_i18n(go, st)
        assert "code SHA is not live on both boxes" in str(exc.value), (word, str(exc.value))
        assert "i18n_done" not in st, (word, st)
    st = {"code_deployed": True}
    rt.phase_i18n(go, st)                                    # inert twin
    assert st["i18n_done"] is True, st

    # (f) both gates of the bot phase, in a batch that deploys the bot
    _bot_batch(rt)
    deployed = []
    monkeypatch.setattr(rt, "ssh", lambda host, verb: deployed.append(verb) or "Started")
    monkeypatch.setattr(rt, "_bot_witness", lambda **kw: None)
    for word in words:
        for st, says in (({"i18n_done": word, "code_deployed": True},
                          "i18n phase has not passed"),
                         ({"i18n_done": True, "code_deployed": word},
                          "the code phase has not passed")):
            with pytest.raises(rt.Fail) as exc:
                rt.phase_bot(go, st)
            assert says in str(exc.value), (word, says, str(exc.value))
            assert deployed == [] and "bot_deployed" not in st, (word, deployed, st)
    st = {"i18n_done": True, "code_deployed": True}
    rt.phase_bot(go, st)                                     # inert twin
    assert deployed == ["deploy-bot"] and st["bot_deployed"] is True, (deployed, st)

    # (g) the bot gate, in verify (its twin -- a witnessed True passes, and is
    # witnessed first -- is the verify-policy test's, which drives the phase)
    for word in words:
        st = {"bot_deployed": word, "code_sha": MERGE_FULL}
        with pytest.raises(rt.Fail) as exc:
            rt.phase_verify(go, st)
        assert "bot phase has not passed" in str(exc.value), (word, str(exc.value))
        assert st["verified"] == rt.ATTEMPTED, (word, st)

    # (h) and the summary: every status renders YES only for the exact True
    fields = {"precursor_deployed": "deploy_precursor", "schema_done": "schema_phase",
              "pre_code_old_build": "pre_code_old_build", "code_deployed": "code_deployed",
              "i18n_done": "i18n", "bot_deployed": "bot", "verified": "verified"}
    assert set(fields) == set(rt.GATE_KEYS), rt.GATE_KEYS
    for key, field in fields.items():
        for word, want in (("REFUSED", "REFUSED"), (rt.ATTEMPTED, rt.ATTEMPTED), ("yes", "NO"),
                           (1, "NO"), (False, "NO"), (None, "NO")):
            got = rt.state_summary({key: word})[field]
            assert got == want, (key, word, got)
        got = rt.state_summary({key: True})[field]
        assert got == ("UNBACKED" if key == "verified" else "YES"), (key, got)


def test_r10_l5_repair_state_clears_an_unbacked_verified_and_a_dry_run_cannot_write_one(
        monkeypatch, tmp_path, capsys):
    """R9-L5: the state file still carried the `verified` a round-8 dry run had written.

    R8-L5 stopped dry runs writing, and nothing removed the word the old one left behind. The
    train's own state handling removes it now: `repair-state` clears a `verified` that no GO verify
    of the recorded code SHA backs, writes WHY beside the removal, and -- like every action of this
    train -- without `--go` it says what it would do and writes nothing. It is local: no probe, no
    ssh, no git. And a dry run still cannot write the word again."""
    import json
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    state = _state_under(monkeypatch, rt, tmp_path / "train-state.json")
    monkeypatch.setattr(rt, "run", _no_command)
    state.write_text('{"verified": true}', encoding="utf-8")   # the shape the old dry run left
    was = state.read_bytes()
    assert rt.state_summary(json.loads(was))["verified"] == "UNBACKED"

    # (a) without --go: says what it would clear, writes nothing
    capsys.readouterr()
    rc = _cli(monkeypatch, rt, "--batch", ABSENT_BATCH, "repair-state")
    out = capsys.readouterr().out
    assert rc == 0 and "[dry run] would clear verified" in out, out
    assert state.read_bytes() == was, "a dry repair wrote the state file"

    # (b) with --go: the word is gone and the reason is written beside it
    rc = _cli(monkeypatch, rt, "--batch", ABSENT_BATCH, "repair-state", "--go")
    out = capsys.readouterr().out
    doc = json.loads(state.read_text(encoding="utf-8"))
    assert rc == 0 and "cleared verified" in out, out
    assert "verified" not in doc, doc
    assert [(r["key"], r["was"]) for r in doc["repairs"]] == [("verified", "YES")], doc
    assert doc["repairs"][0]["reason"] == rt.UNBACKED_VERIFIED_REASON, doc
    assert rt.state_summary(doc)["verified"] == "NO" and rt.state_summary(doc)["repairs"] == 1

    # (c) a second run finds nothing to repair and writes nothing
    after = state.read_bytes()
    rc = _cli(monkeypatch, rt, "--batch", ABSENT_BATCH, "repair-state", "--go")
    out = capsys.readouterr().out
    assert rc == 0 and "nothing to repair" in out, out
    assert state.read_bytes() == after

    # (d) inert twin: a `verified` a GO verify of the recorded SHA wrote is kept
    backed = {"verified": True, "code_sha": MERGE_FULL,
              "verified_evidence": {"code_sha": MERGE_FULL, "mode": "GO",
                                    "at": "2026-09-22T03:00:00+00:00"}}
    state.write_text(json.dumps(backed), encoding="utf-8")
    rc = _cli(monkeypatch, rt, "--batch", ABSENT_BATCH, "repair-state", "--go")
    assert rc == 0 and json.loads(state.read_text(encoding="utf-8")) == backed
    assert rt.state_summary(backed)["verified"] == "YES"
    # ...and evidence for ANOTHER sha, or from a non-GO run, does not back it
    for evidence in ({"code_sha": REVIEWED_FULL, "mode": "GO"},
                     {"code_sha": MERGE_FULL, "mode": "PLAN"}):
        assert not rt.verified_is_backed(dict(backed, verified_evidence=evidence)), evidence

    # (e) a dry run can never write it again: `plan --from verify` over a
    # state that carries none leaves the file byte-identical
    state.write_text(json.dumps({"code_sha": MERGE_FULL, "bot_skipped": rt.BOT_SKIP_REASON}),
                     encoding="utf-8")
    was = state.read_bytes()
    # A dry verify still READS the boxes; those reads are stubbed here, so the
    # `run` that refuses every command proves the plan spawned nothing else.
    for name, stub in (("assert_provenance_up_front", lambda args, st_: None),
                       ("assert_control", lambda host: None),
                       ("assert_health_keys", lambda hosts: None),
                       ("assert_positive_signals", lambda: None),
                       ("http_code", lambda host, path, **kw: "200"),
                       ("code_state", lambda host: _NEW_BUILD),
                       ("assert_edge_runs_new_code", lambda: None)):
        monkeypatch.setattr(rt, name, stub)
    rc = _cli(monkeypatch, rt, "--batch", ABSENT_BATCH, "plan", "--from", "verify")
    out = capsys.readouterr().out
    assert rc == 0, out
    assert state.read_bytes() == was, "a dry run wrote the state file"
    assert "[dry run] nothing is recorded" in out, out


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


def test_r10_m2_the_identity_gate_runs_in_the_play_process_and_must_say_it_passed(monkeypatch):
    """R9-M2: the box a deploy play reached was compared with its attestation after the play had run.

    The gate is a task of the SAME playbook, on the same host, ahead of the imported play, in a
    play that is any_errors_fatal: the box hashes its own machine-id with this invocation's token and
    compares the result with the digest the train computed from the ATTESTED fingerprint, and it
    compares the address it was reached at with the declared one. The train then requires the gate's
    own PASSED line carrying this invocation's token -- a positive signal, never the absence of a
    refusal. What travels is the salted digest, never the fingerprint."""
    import hashlib
    import json
    rt, _src = _release_train()
    rt.select_batch(ABSENT_BATCH)
    _seat(monkeypatch, rt)
    expect = (rt.PRIMARY_TOKEN, PRIMARY_BOX_ID)
    play_path = "/srv/a-play-dir/playbooks/x.yml"

    # (a) the composition: the gate is a task of the play before the import,
    # keeps the default failure rule, and that play is any_errors_fatal
    book = rt.attested_playbook(play_path=play_path, gate=True)
    assert rt.composed_gate(book)
    plays = json.loads(book)
    assert plays[0].get("any_errors_fatal") is True and "import_playbook" in plays[1], plays
    gate = [t for t in plays[0]["tasks"] if rt.GATE_MARK in (t.get("shell") or "")]
    assert len(gate) == 1 and "failed_when" not in gate[0] and "ignore_errors" not in gate[0]
    shell = gate[0]["shell"]
    assert shell.count("exit 3") == 2, shell
    assert "{{ scr_expect_id }}" in shell and "{{ scr_expect_addr }}" in shell, shell
    assert shell.rstrip().endswith('PASSED"'), shell
    # ...and every way of weakening it fails the check `run_attested` asks of
    # the composed playbook before it spawns anything
    assert not rt.composed_gate(rt.attested_playbook(play_path=play_path, gate=False))

    def _not_fatal(p):
        p[0].pop("any_errors_fatal")

    def _tolerant(p):
        for t in p[0]["tasks"]:
            if rt.GATE_MARK in (t.get("shell") or ""):
                t["failed_when"] = False

    def _import_first(p):
        p.insert(0, p.pop(1))

    for weaken in (_not_fatal, _tolerant, _import_first):
        weak = json.loads(book)
        weaken(weak)
        assert not rt.composed_gate(json.dumps(weak)), weaken.__name__

    # (b) what travels: a digest salted with this invocation's token
    want = hashlib.sha256(("%s:%s" % (NONCE, PRIMARY_BOX_ID)).encode("ascii")).hexdigest()
    assert rt.expected_identity_digest(NONCE, PRIMARY_BOX_ID) == want
    asked = []
    monkeypatch.setattr(rt, "run", _attesting_run(rt, asked, addr=rt.PRIMARY,
                                                  box_id=PRIMARY_BOX_ID))
    rt.run_attested(SEAT_PRIMARY_LIMIT, play="x.yml", expect=expect,
                    who="SCR_TRAIN_PRIMARY_LIMIT")
    sent = asked[-1]
    digest = rt.expected_identity_digest(_nonce_of(sent), PRIMARY_BOX_ID)
    assert "-e scr_expect_id=%s" % digest in sent, sent
    assert "-e scr_expect_addr=%s" % rt.PRIMARY in sent, sent
    assert PRIMARY_BOX_ID not in sent, "the fingerprint itself never travels"

    # (c) the answer must carry the gate's own PASSED line: a gate that printed
    # nothing, at process status 0, is refused
    monkeypatch.setattr(rt, "run", _attesting_run(rt, addr=rt.PRIMARY, box_id=PRIMARY_BOX_ID,
                                                  gate="SILENT"))
    with pytest.raises(rt.Fail) as exc:
        rt.run_attested(SEAT_PRIMARY_LIMIT, play="x.yml", expect=expect,
                        who="SCR_TRAIN_PRIMARY_LIMIT")
    assert "0 PASSED" in str(exc.value), str(exc.value)
    # ...a box that is not the attested one: its gate refuses and the process
    # exits non-zero before the import
    monkeypatch.setattr(rt, "run", _attesting_run(rt, addr=rt.PRIMARY, box_id=STANDBY_BOX_ID))
    with pytest.raises(rt.Fail) as exc:
        rt.run_attested(SEAT_PRIMARY_LIMIT, play="x.yml", expect=expect,
                        who="SCR_TRAIN_PRIMARY_LIMIT")
    assert "exited rc=2" in str(exc.value), str(exc.value)
    # ...and an attested pair that is not a declared endpoint class and a
    # fingerprint cannot be gated at all, so nothing is spawned
    monkeypatch.setattr(rt, "run", _no_command)
    for bad in ((rt.PRIMARY_TOKEN, "not-a-fingerprint"), ("OTHER", PRIMARY_BOX_ID)):
        with pytest.raises(rt.Fail) as exc:
            rt.run_attested(SEAT_PRIMARY_LIMIT, play="x.yml", expect=bad,
                            who="SCR_TRAIN_PRIMARY_LIMIT")
        assert "no gate could be composed" in str(exc.value), (bad, str(exc.value))
