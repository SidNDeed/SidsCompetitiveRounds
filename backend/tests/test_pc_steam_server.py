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

from test_player_cards_server import Scripted, _run  # noqa: E402
from test_pc_routes import PID, STEAM, NOW, _Req, _idx  # noqa: E402
import database  # noqa: E402
import main  # noqa: E402
import pc_portrait  # noqa: E402
import pc_steam  # noqa: E402
import schemas  # noqa: E402
import steamid64  # noqa: E402
import steamid64_pg_parity  # noqa: E402

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


def test_health_carries_the_fold_marker_the_release_train_asserts_on_both_roles():
    """v4.13 §8: `pc_fold` exists only to be probed (#306). The release train requires it on BOTH api boxes: on
    the standby its new-route check and the sweep word read the same on the build before this fold, and the replica
    write gate answers 503 to every write before any handler, so a write probe cannot fail there. The marker is on
    the connected and on the degraded answer, declared on the response model (an undeclared keyword never reaches
    the response), read by nothing else, and the value the train expects for each role; the train's picture signal
    requires more than the 183 pictures stored before this fold (R19), so that signal can fail."""
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
    assert MAIN_SRC.count("PC_FOLD") == 3                      # defined once, reported twice, read by nothing else
    train = REPO / "scripts" / "deploy" / "release_train.py"
    if not train.exists():
        pytest.skip("the release train is local to the operating seat")
    src = train.read_text(encoding="utf-8")
    batch = src[src.index('"sept12-gacha": {'):src.index('"sept10-batch": {')]
    assert batch.count('"pc_fold"') == 1
    assert '{"key": "pc_fold", "primary": "%s", "standby": "%s"},' % (fold, fold) in batch
    assert '"SELECT count(*) FROM players WHERE pc_steam_portrait_hash IS NOT NULL;", 184),' in batch


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
    assert src.count('AND """ + _PC_POOL_MEMBER_SQL + """') == 1   # v4.13: the pool word (deleted, banned, not a SteamID64)
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
    train = REPO / "scripts" / "deploy" / "release_train.py"
    if not train.exists():
        pytest.skip("the release train is local to the operating seat")
    src = train.read_text(encoding="utf-8")
    batch = src[src.index('"sept12-gacha": {'):src.index('"sept10-batch": {')]
    for idx in INDEXES:
        assert '"%s",' % idx in batch, idx
    assert '{"key": "pc_steam_sweep", "primary": "running", "standby": "standby"},' in batch
    assert '{"key": "pc_steam_render", "primary": "ok", "standby": "ok"},' in batch
    assert "SELECT count(*) FROM players WHERE pc_steam_portrait_hash IS NOT NULL;" in batch
    for col in ("pc_steam_avatar_ref", "pc_steam_portrait_at", "pc_steam_portrait_fail", "pc_steam_portrait_hash",
                "pc_steam_portrait_next_at"):
        assert '("players", "%s"),' % col in batch, col
    assert '("pc_portraits", "unreferenced_since"),' in batch and '("players", "pc_steam_attempt"),' in batch
    # pc/pool answers 200 on BOTH builds, so it is the smoke route and never the presence discriminator (r3)
    assert '"new_routes": ["/api/v1/pc/packs"],' in batch and '"smoke_route": "/api/v1/pc/pool",' in batch
    assert '"rollback_sql": "rollback_311_player_cards_steam_portraits.sql",' in batch
    assert '"i18n_sql": ["312_i18n_keys_sept12.sql", "313_seed_machine_translations_sept12.sql"],' in batch
    assert 'present = all(c not in ("404", "000", "") for c in codes)' in src
    assert 'SMOKE_ROUTE = batch.get("smoke_route", NEW_ROUTES[0])' in src and "rollback rule" in src
    # the code phase is saved only on POSITIVE presence on both boxes and a routed answer from the edge (r4)
    phase = src[src.index("def phase_code("):src.index("def phase_i18n(")]
    assert "if not present:" in phase and 'if edge in ("000", ""):' in phase and 'if edge == "404":' in phase
    assert phase.index("if not present:") < phase.index('st["code_deployed"] = True')
    assert "294 must run" not in src   # the i18n gate names the selected batch's files, not a stale migration
    assert "resume_311_player_cards_steam_portraits.sql" in src and "parks every player" in src
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


def test_the_train_code_state_tells_present_absent_and_unknown_apart():
    train = REPO / "scripts" / "deploy" / "release_train.py"
    if not train.exists():
        pytest.skip("the release train is local to the operating seat")
    src = train.read_text(encoding="utf-8")
    fn = src[src.index("def code_state(host):"):src.index("def health_json(host):")]
    answers = {}
    ns = {"CONTROL_ROUTE": "/control", "NEW_ROUTES": ["/new"], "http_code": lambda host, route: answers[route]}
    exec(fn, ns)
    for new, expect in (("200", (True, True, False)), ("422", (True, True, False)), ("405", (True, True, False)),
                        ("404", (True, False, True)), ("000", (True, False, False)), ("", (True, False, False))):
        answers.update({"/control": "200", "/new": new})
        ok, present, absent, codes = ns["code_state"]("h")
        assert (ok, present, absent) == expect and codes == [new], new
    answers.update({"/control": "000", "/new": "200"})
    assert ns["code_state"]("h")[0] is False


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
