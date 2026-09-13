"""Player Cards portrait pivot — the routes in main.py (v22 §2.2, §3.2, §6 +
the r18 dispositions), exercised against the scripted session of
test_player_cards_server and pinned on their source where the order of two
statements is the whole guarantee."""
import ast
import asyncio
import hashlib
import json
import hmac
import inspect
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import main  # noqa: E402
import models  # noqa: E402
import pc_portrait as P  # noqa: E402
from sqlalchemy import select  # noqa: E402
from test_player_cards_server import Scripted, _run  # noqa: E402

MAIN_SRC = inspect.getsource(main)
STEAM = "76561198040410653"
PID = UUID("0b7d2f8e-3c4a-4c2a-9b1e-2f3a4b5c6d7e")
DESC = "v1|face=1000:1002:1004:1005|off=0,0;0,0;0,0;0,0|color=:|effect=|skin=0|anim=1|g=1.2.3|r=1"
DESC_COSMETIC = DESC.replace("color=:", "color=color_azure:3fa9f5").replace("effect=|", "effect=effect_embers|")
# Pinned to the grammar at import. Without this, a field added to
# DESCRIPTOR_RE turns every upload test in this file into a 422 on a route that
# is working exactly as asked -- eleven failures that name a status code and
# not the constant that caused them.
assert P.descriptor_parse(DESC) is not None, "DESC is off-grammar"
assert P.descriptor_parse(DESC_COSMETIC) is not None, "DESC_COSMETIC is off-grammar"
SKU_KEY = " ".join(str(select(models.ShopItem.sku)).split())[:24]
NOW = datetime(2026, 9, 12, 3, 0, tzinfo=timezone.utc)


def _src(fn):
    return inspect.getsource(fn)


# ── fakes ────────────────────────────────────────────────────────────────────

class _Req:
    def __init__(self, body=b"", headers=None):
        self._body = body
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}

    async def body(self):
        return self._body


class _Face:
    """The renderer contract the routes rely on (pc_face.py is Codex's)."""
    ENGLISH = {"pc.edition": "Edition", "pc.foil": "Foil", "pc.preview_footer": "Preview"}
    ASSETS_DIR = "."

    def __init__(self, ihdr=(1180, 1180, 8, 6, 0), canonical=b"canon", sha="ab" * 32, error=None,
                 coverage=0.2, ihdr_error=False):
        self.ihdr, self.canonical, self.sha, self.error, self.coverage = ihdr, canonical, sha, error, coverage
        self.ihdr_error = ihdr_error
        self.prepared = 0
        self.rendered = []

    def png_ihdr(self, body):
        if self.ihdr_error:
            raise ValueError("not a png")
        return self.ihdr

    def prepare_portrait(self, body):
        self.prepared += 1
        if self.error is not None:
            raise self.error
        # The real helper applies the cap to the canonical encoding and RAISES
        # (pc_face.py: `raise ValueError("portrait_too_large")`). A fake that
        # returned the oversized bytes instead modelled a case that cannot
        # happen and left the case that does happen untested.
        if len(self.canonical) > P.PC_PORTRAIT_MAX_BYTES:
            raise ValueError("portrait_too_large")
        return self.canonical, {"sha256": self.sha, "width": 1180, "height": 1180, "coverage": self.coverage}

    def renderer_fingerprint(self):
        return "f" * 16

    def runtime_provenance(self):
        # A healthy box. `_pc_raqm` reads `layout_engine`, never a top-level
        # "raqm" key — `test_raqm_is_read_from_the_engine_actually_in_use`
        # is what holds that, with the shapes this fake cannot carry.
        return {"features": {"raqm": {"available": True, "version": "0.10.1"}},
                "layout_engine": "raqm"}

    def render_face(self, spec, labels, pbytes, size):
        self.rendered.append((spec, size, pbytes))
        return b"\x89PNG" + size.encode()

    def render_back(self):
        return b"\x89PNGback"


def _png_body(n=2000):
    return b"\x89PNG\r\n\x1a\n" + bytes(n - 8)


def _headers(body, ct="image/png", cl=None):
    return {"content-length": str(len(body) if cl is None else cl), "content-type": ct}


def _sig(secret, body, nonce, desc):
    canon = P.canon_portrait(STEAM, nonce, hashlib.sha256(body).hexdigest(), desc)
    return hmac.new(secret.encode(), canon.encode(), hashlib.sha256).hexdigest()


def _row(**over):
    row = {"pc_opted_out_at": None, "pc_game_portrait_hash": "cd" * 32, "pc_game_portrait_descriptor": DESC + "0",
           "since_last": 100.0, "lock_left": None, "pc_game_portrait_locked_until": None, "banned": False,
           "active_player_color_id": None, "active_player_effect_id": None}
    row.update(over)
    return row


def _writer(monkeypatch, face=None, row=None, nonce_used=True, player=None, script_extra=None):
    """The upload route wired to fakes: MATCH_HMAC_SECRET, the renderer, the
    actor gate (recorded in the session log as ACTOR) and the scripted rows."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "secret")
    face = face or _Face()
    monkeypatch.setattr(main, "_pcf", face)
    player = player or SimpleNamespace(id=PID, active_player_color_id=None, active_player_effect_id=None)

    async def actor(request, steam_id, sig, canon, db):
        db.log.append(("ACTOR", {"steam_id": steam_id, "canon": canon}))
        return player
    monkeypatch.setattr(main, "_pc_verified_actor", actor)
    row = row if row is not None else _row()
    script = {
        # the unlocked read P is taken on, answered FROM THE SAME ROW so the
        # fixture cannot invent the mismatch the route refuses on
        "SELECT pc_game_portrait_hash, pc_steam_portrait_hash FROM players": [[{"pc_game_portrait_hash": row["pc_game_portrait_hash"], "pc_steam_portrait_hash": None}]],
        "AS lock_left": [[row]],
        "INSERT INTO pc_portrait_nonces": [[{"nonce": "n"}] if nonce_used else []],
        "RETURNING pc_game_portrait_at": [[{"at": NOW}]],
    }
    script.update(script_extra or {})
    return face, Scripted(script)


def _upload(db, body, nonce="nonce-0001", desc=DESC, sig=None, headers=None, secret="secret"):
    req = _Req(body, headers if headers is not None else _headers(body))
    return _run(main.pc_portrait_upload(request=req, steam_id=STEAM, sig=sig or _sig(secret, body, nonce, desc),
                                        nonce=nonce, descriptor=desc, db=db))


def _idx(db, needle):
    for i, (sql, _) in enumerate(db.log):
        if needle in sql:
            return i
    raise AssertionError(f"{needle!r} never executed: {[s[:60] for s, _ in db.log]}")


# ── the portrait writer ─────────────────────────────────────────────────────

def test_upload_happy_path_orders_lock_actor_reread_nonce_plocks_blob_row_delete(monkeypatch):
    face, db = _writer(monkeypatch)
    body = _png_body()
    ans = _upload(db, body)
    assert ans["applied"] is True and ans["portrait_hash"] == "ab" * 32 and ans["portrait_descriptor"] == DESC
    assert ans["portrait_at"] == NOW.isoformat() and "bytes" not in ans
    assert db.committed == 1 and db.rolled_back == 0 and face.prepared == 1
    # the exclusive identity lock is the FIRST statement, before the actor gate and its shared form
    assert db.log[0][0] == "SELECT pg_advisory_xact_lock(hashtext(CAST(:sid AS text)))" and db.log[0][1] == {"sid": STEAM}
    order = [_idx(db, k) for k in ("pg_advisory_xact_lock(hashtext", "ACTOR", "CAST(:cls AS integer)", "AS lock_left",
                                   "INSERT INTO pc_portrait_nonces", "INSERT INTO pc_portraits",
                                   "RETURNING pc_game_portrait_at", "UPDATE pc_portraits SET unreferenced_since")]
    assert order == sorted(order), order   # P BEFORE R — I → C → P → R
    # the re-read locks the row and excludes deleted accounts
    reread = db.log[_idx(db, "AS lock_left")]
    assert "FOR NO KEY UPDATE" in reread[0] and "deleted_at IS NULL" in reread[0] and reread[1] == {"pid": str(PID)}
    # per-hash P locks: both hashes, deduplicated, sorted, under the one class
    plocks = [p for s, p in db.log if "CAST(:cls AS integer)" in s]
    assert [p["h"] for p in plocks] == sorted({"cd" * 32, "ab" * 32}) and {p["cls"] for p in plocks} == {P.PC_P_LOCK_CLASS}
    blob = db.log[_idx(db, "INSERT INTO pc_portraits")]
    assert "ON CONFLICT (hash) DO UPDATE SET unreferenced_since = NULL" in blob[0] and blob[1]["h"] == "ab" * 32 and blob[1]["b"] == b"canon"
    upd = db.log[_idx(db, "RETURNING pc_game_portrait_at")]
    assert upd[1] == {"h": "ab" * 32, "d": DESC, "pid": str(PID)} and "deleted_at IS NULL" in upd[0]
    dele = db.log[_idx(db, "UPDATE pc_portraits SET unreferenced_since")]
    assert "NOT EXISTS" in dele[0] and dele[1] == {"h": "cd" * 32}


def test_upload_same_bytes_and_inputs_answer_200_before_the_pacing_gate(monkeypatch):
    face, db = _writer(monkeypatch, row=_row(pc_game_portrait_hash="ab" * 32, pc_game_portrait_descriptor=DESC,
                                              since_last=5.0))
    ans = _upload(db, _png_body())
    assert ans == {"applied": False, "reason": "same", "portrait_hash": "ab" * 32, "portrait_descriptor": DESC}
    assert db.rolled_back == 1 and db.committed == 0
    assert db.count("pc_portrait_nonces") == 0 and db.count("INSERT INTO pc_portraits") == 0


def test_upload_pacing_answers_409_with_the_remaining_seconds_and_consumes_no_nonce(monkeypatch):
    face, db = _writer(monkeypatch, row=_row(since_last=5.0))
    with pytest.raises(HTTPException) as ex:
        _upload(db, _png_body())
    assert ex.value.status_code == 409 and ex.value.detail == {"error": "retry_after", "retry_after": 26}
    assert db.rolled_back == 1 and db.count("pc_portrait_nonces") == 0


@pytest.mark.parametrize("over", [{"banned": True}, {"pc_opted_out_at": NOW}])
def test_upload_refused_for_a_banned_or_opted_out_subject(monkeypatch, over):
    face, db = _writer(monkeypatch, row=_row(**over))
    with pytest.raises(HTTPException) as ex:
        _upload(db, _png_body())
    assert ex.value.status_code == 403 and ex.value.detail == {"error": "portrait_refused"}
    assert db.rolled_back == 1 and db.count("pc_portrait_nonces") == 0


def test_upload_refused_while_an_admin_lock_is_live(monkeypatch):
    until = NOW + timedelta(days=3)
    face, db = _writer(monkeypatch, row=_row(lock_left=3600.0, pc_game_portrait_locked_until=until))
    with pytest.raises(HTTPException) as ex:
        _upload(db, _png_body())
    assert ex.value.status_code == 403
    assert ex.value.detail == {"error": "portrait_locked", "locked_until": until.isoformat()}


def test_upload_descriptor_must_name_the_equipped_cosmetics(monkeypatch):
    # nothing equipped, cosmetics named → 422 and no nonce consumed
    face, db = _writer(monkeypatch)
    with pytest.raises(HTTPException) as ex:
        _upload(db, _png_body(), desc=DESC_COSMETIC)
    assert ex.value.status_code == 422 and ex.value.detail == {"error": "descriptor_mismatch"}
    assert db.rolled_back == 1 and db.count("pc_portrait_nonces") == 0
    # The equipped skus are read from shop_items by the ids in the LOCKED ROW.
    # `player` is the pre-lock ORM object and carries NOTHING equipped, which
    # is what an equip committing between the actor gate and the row lock looks
    # like from before the lock. Reading it would find no skus and refuse the
    # correct descriptor with 422; reading the locked row finds 7 and 9.
    stale = SimpleNamespace(id=PID, active_player_color_id=None, active_player_effect_id=None)
    face, db = _writer(monkeypatch, player=stale,
                       row=_row(active_player_color_id=7, active_player_effect_id=9),
                       script_extra={SKU_KEY: [[{"sku": "color_azure"}], [{"sku": "effect_embers"}]]})
    assert _upload(db, _png_body(), desc=DESC_COSMETIC)["applied"] is True
    assert db.count(SKU_KEY) == 2


def test_upload_a_replayed_nonce_is_refused_after_the_reread_and_before_any_write(monkeypatch):
    face, db = _writer(monkeypatch, nonce_used=False)
    with pytest.raises(HTTPException) as ex:
        _upload(db, _png_body())
    assert ex.value.status_code == 403 and ex.value.detail == {"error": "nonce_replayed"}
    assert db.rolled_back == 1
    # P is taken before the row is read, so the replay refusal has already
    # taken it; what it must not have done is write anything.
    assert db.count("INSERT INTO pc_portraits") == 0 and db.count("RETURNING pc_game_portrait_at") == 0


def test_upload_transport_and_container_refusals_touch_no_database(monkeypatch):
    body = _png_body()
    cases = [
        (dict(headers={"content-type": "image/png"}), 411),
        (dict(headers={"content-length": str(len(body)), "transfer-encoding": "chunked", "content-type": "image/png"}), 411),
        (dict(headers={"content-length": "x", "content-type": "image/png"}), 411),
        (dict(headers=_headers(body, cl=P.PC_PORTRAIT_MAX_BYTES + 1)), 413),
        (dict(headers=_headers(body, ct="text/plain")), 415),
        (dict(headers=_headers(body, cl=len(body) + 1)), 400),
        (dict(desc="v1|garbage"), 422),
        (dict(sig="0" * 64), 403),
    ]
    for kwargs, status in cases:
        face, db = _writer(monkeypatch)
        with pytest.raises(HTTPException) as ex:
            _upload(db, body, **kwargs)
        assert ex.value.status_code == status, kwargs
        assert db.log == [] and face.prepared == 0, kwargs
    # the container: not a PNG, or not 1180x1180 RGBA 8-bit non-interlaced
    for face in (_Face(ihdr_error=True), _Face(ihdr=(1000, 1000, 8, 6, 0)), _Face(ihdr=(1180, 1180, 8, 2, 0))):
        face, db = _writer(monkeypatch, face=face)
        with pytest.raises(HTTPException) as ex:
            _upload(db, body)
        assert ex.value.status_code == 422 and ex.value.detail == {"error": "portrait_invalid"}
        assert db.log == [] and face.prepared == 0


def test_upload_decode_failures_and_the_post_canonical_cap(monkeypatch):
    """A picture whose CANONICAL encoding is over the cap is too large, not
    invalid: the client's retry path reads the two differently, and 413 is
    what the route promises."""
    for face, detail, status in (
        (_Face(error=ValueError("portrait_coverage")), {"error": "portrait_coverage"}, 422),
        (_Face(error=ValueError("anything else")), {"error": "portrait_invalid"}, 422),
        # how the real helper reports it...
        (_Face(error=ValueError("portrait_too_large")), "portrait_too_large", 413),
        # ...and the route's own re-check of the bytes it was handed
        (_Face(canonical=bytes(P.PC_PORTRAIT_MAX_BYTES + 1)), "portrait_too_large", 413),
    ):
        face, db = _writer(monkeypatch, face=face)
        with pytest.raises(HTTPException) as ex:
            _upload(db, _png_body())
        assert ex.value.status_code == status and ex.value.detail == detail
        assert db.log == []   # decode runs BEFORE the identity lock: nothing was held


def test_upload_decode_timeout_is_422_and_leaves_the_slot_to_the_worker(monkeypatch):
    face, db = _writer(monkeypatch)

    async def slow(fn, *args, budget=None):
        raise asyncio.TimeoutError()
    monkeypatch.setattr(main._pcp, "in_pool", slow)
    with pytest.raises(HTTPException) as ex:
        _upload(db, _png_body())
    assert ex.value.status_code == 422 and ex.value.detail == {"error": "portrait_invalid", "reason": "decode_timeout"}
    assert db.log == []


def test_upload_without_a_renderer_is_503(monkeypatch):
    monkeypatch.setattr(main, "_pcf", None)
    db = Scripted({})
    with pytest.raises(HTTPException) as ex:
        _upload(db, _png_body())
    assert ex.value.status_code == 503 and db.log == []


def test_upload_source_holds_the_exclusive_lock_before_the_actor_gate_and_the_sig_before_decode():
    src = _src(main.pc_portrait_upload)
    assert src.index("_pc_hmac_ok(sig, canon)") < src.index("_pcp.in_pool(_pcf.prepare_portrait")
    assert src.index("_pcp.in_pool(_pcf.prepare_portrait") < src.index("pg_advisory_xact_lock(hashtext(CAST(:sid AS text)))")
    assert src.index("pg_advisory_xact_lock(hashtext(CAST(:sid AS text)))") < src.index("_pc_verified_actor(request")
    assert src.count("pg_advisory_xact_lock(hashtext(CAST(:sid AS text)))") == 1
    assert src.index('"reason": "same"') < src.index("_pcp.PACING_SECONDS")
    assert "del body" in src


# ── the None write, the discard and the deletion sweep (static pins) ─────────

def test_the_none_write_takes_the_exclusive_lock_and_waits_out_live_leases():
    src = _src(main.pc_set_setting)
    a = src.index("_pc_hmac_ok(sig, canon)")
    b = src.index("pg_advisory_xact_lock(hashtext(CAST(:sid AS text)))")
    c = src.index("_pc_verified_actor(request")
    d = src.index("FOR NO KEY UPDATE")
    e = src.index("_pc_lease_wait(db, pid)")
    f = src.index("_PC_SETTINGS_SQL[key]")
    assert a < b < c < d < e < f
    assert "none_write = _pc_setting_revokes_picture(key, value)" in src
    assert '"error": "retry_after"' in src
    assert main._PC_SETTINGS_SQL["portrait_source"].count("'none'") == 1 and "'game'" in main._PC_SETTINGS_SQL["portrait_source"]


@pytest.mark.parametrize("key,value,revokes", [
    ("portrait_source", 0, True),      # the picture becomes none
    ("opted_out", 1, True),            # an opted-out subject resolves to none too
    ("portrait_source", 1, False),     # turning it back ON adds a picture
    ("opted_out", 0, False),
    ("announce", 0, False),
    ("announce", 1, False),
    ("collection_public", 0, False),
    ("collection_public", 1, False),
])
def test_only_the_writes_that_withdraw_the_picture_wait_for_a_live_lease(key, value, revokes):
    """Which writes wait is the whole guarantee: a write that withdraws the
    picture must not commit under a send already carrying it."""
    assert main._pc_setting_revokes_picture(key, value) is revokes
    assert key in main._pc.SETTINGS_KEYS


def test_every_settings_key_is_answered_by_the_revocation_predicate():
    # a key added to the settings surface without a decision here would
    # silently default to "does not withdraw the picture"
    for key in main._pc.SETTINGS_KEYS:
        for value in (0, 1):
            assert main._pc_setting_revokes_picture(key, value) in (True, False)
    assert set(main._pc.SETTINGS_KEYS) == {"opted_out", "collection_public", "announce", "portrait_source"}


def test_a_ban_deletes_the_subjects_leases_under_the_identity_lock():
    src = _src(main._apply_ban_core)
    assert "DELETE FROM pc_delivery_leases WHERE subject_id IN" in src
    assert src.index("DELETE FROM pc_delivery_leases") < src.index('"status": "already_banned"')


def test_a_discard_deletes_the_prints_leases_after_the_discard_write():
    src = _src(main.pc_discard_print)
    assert src.index("discarded_at") < src.index("DELETE FROM pc_delivery_leases WHERE print_id = CAST(:print AS uuid)")


def test_account_deletion_sweeps_leases_nonces_and_the_portrait_unit():
    src = _src(main.delete_player_data)
    assert "DELETE FROM pc_delivery_leases WHERE subject_id" in src
    assert "DELETE FROM pc_portrait_nonces WHERE player_id" in src
    assert '_pc_clear_portrait_unit(db, str(pid), lock_days=None, source="none")' in src


def test_the_ack_releases_leases_by_event_and_by_id():
    src = _src(main.internal_pc_events_ack)
    assert "event_ids && CAST(:ids AS bigint[])" in src and "leases" in src
    assert '"released"' in src


def test_the_janitor_sweeps_expired_leases_and_used_nonces():
    src = _src(main._pc_snapshot_janitor_step)
    assert "DELETE FROM pc_delivery_leases WHERE until < NOW() - INTERVAL '1 hour'" in src
    assert "DELETE FROM pc_portrait_nonces WHERE used_at < NOW() - INTERVAL '1 day'" in src


def test_the_face_route_has_its_own_rate_bucket_and_health_reports_the_renderer():
    src = _src(main.rate_limit_gate)
    assert "_RL_FACE_PREFIX" in src and '|f"' in src
    assert main._RL_FACE_PREFIX == "/api/v1/pc-face/" and main._RL_FACE[0] >= 60
    assert "pc_renderer_fp=_pc_renderer_fp()" in _src(main.health_check)


def test_the_print_face_select_carries_every_resolver_input():
    for col in ("subject_opted_out", "portrait_source", "portrait_hash", "subject_banned", "subject_deleted"):
        assert f"AS {col}" in main._PC_PRINT_FACE_SELECT, col


def _pc_functions():
    """Every Player Cards function in main.py, derived from the module — not a
    list of four names. A leak added to a fifth answer, or to a shared dict
    builder like `_pc_print_dict`, is only caught if the subject set grows with
    the code."""
    tree = ast.parse(MAIN_SRC)
    out = []
    lines = MAIN_SRC.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.match(r"_?(internal_)?pc_", node.name):
            out.append((node.name, "\n".join(lines[node.lineno - 1:node.end_lineno])))
    return out


def test_no_player_cards_answer_carries_a_steam_or_discord_identifier():
    subjects = _pc_functions()
    assert len(subjects) >= 50, len(subjects)      # a deriver that finds nothing proves nothing
    for name, body in subjects:
        for key in ('"owner_steam_id"', '"subject_steam_id"', '"puller_steam_id"', '"puller_discord_id"',
                    '"subject_discord_id"', '"steam_id":', '"discord_id":'):
            assert key not in body, (name, key)


# keys that end in `name` and are not a player's name
_NOT_A_PLAYER_NAME = ("rank_name", "font_name", "file_name", "band_name")


def test_the_player_cards_boundary_applies_the_coverage_projection_too():
    """`public_name` is P alone, which is correct for the global display name
    and wrong here: a Player Cards payload or a face must also lose what the
    renderer cannot draw. `public_render_name` is both halves, in order."""
    for name, body in _pc_functions():
        for line in body.splitlines():
            if "_pcp.public_name(" in line:
                raise AssertionError(
                    "%s emits P alone; the boundary wants public_render_name: %s"
                    % (name, line.strip()))
    assert MAIN_SRC.count("_pcp.public_render_name(") >= 8
    # and the labels a face draws go through the coverage removal
    assert "_pcp.coverage_strip(" in _src(main._pc_labels)


def test_every_player_cards_name_answer_goes_through_the_public_projection():
    """A display name is a constructor fallback when the account never set one,
    and that fallback is the Steam ID. Emitting a stored name unprojected is
    the same disclosure as emitting the ID, so the projection is required at
    the emission or on the local it emits."""
    checked = 0
    for name, body in _pc_functions():
        projected = set(re.findall(
            r"^\s*([a-z_]+)\s*=\s*_pcp\.public_(?:render_)?name\(", body, re.M))
        for line in body.splitlines():
            m = re.search(r'"([a-z_]*name)"\s*:\s*(.+?),?\s*$', line)
            if not m or m.group(1) in _NOT_A_PLAYER_NAME:
                continue
            checked += 1
            expr = m.group(2)
            ok = ("public_name" in expr or "public_render_name" in expr
                  or any(re.match(rf"{p}\b", expr.strip()) for p in projected))
            assert ok, (name, line.strip())
    assert checked >= 8, checked


def _print_row(**over):
    """A row in the shape `_PC_PRINT_FACE_SELECT` returns."""
    row = {"print_id": uuid4(), "card_id": uuid4(), "subject_player_id": PID, "edition_id": 1,
           "owner_player_id": PID, "minted_at": NOW, "snapshot_id": 3, "rarity": "epic",
           "foil": False, "signed": False, "pool_rank": 4, "rating": 2100.0, "peak_rating": 2200.0,
           "board_rank": 4, "series_wins": 20, "series_losses": 5, "top_card": "Leach",
           "title": "Master II", "source": "bought", "pack_id": uuid4(), "slot": 0,
           "discarded_at": None, "discard_shards": None, "subject_name": "Ace",
           "subject_deleted": False}
    row.update(over)
    return row


def test_a_renderer_that_cannot_key_a_face_refuses_instead_of_inventing_one(monkeypatch):
    """`renderer_fp` used to fall back to sixteen zeroes, so two builds with
    different pixels keyed one `face_rev` and one URL marked `immutable` — the
    cache then served whichever build wrote the file first, for a year."""
    face = _Face()
    monkeypatch.setattr(main, "_pcf", face)
    async def labels(db, locale):
        return {"pc.edition": "Edition"}

    async def colors(db):
        return {}
    monkeypatch.setattr(main, "_pc_labels", labels)
    monkeypatch.setattr(main, "_rank_colors", colors)

    ctx = _run(main._pc_face_ctx(None, "en"))
    assert ctx["renderer_fp"] == "f" * 16 and main._pc_renderer_unavailable() is None

    monkeypatch.setattr(main, "_pc_renderer_fp", lambda: None)
    ctx = _run(main._pc_face_ctx(None, "en"))
    assert ctx["renderer_fp"] is None, "a placeholder key is a promise this box cannot make"
    assert main._pc_face_inputs(_print_row(), ctx)[3] is None, "no fingerprint, no revision"
    assert main._pc_renderer_unavailable() == "renderer_fingerprint_unavailable"
    with pytest.raises(HTTPException) as ex:
        main._pc_require_renderer()
    assert ex.value.status_code == 503


def test_the_face_surface_refuses_when_the_box_cannot_shape_or_project(monkeypatch):
    """The coverage projection admits Arabic, Hebrew, Thai and Devanagari
    because the renderer carries fonts for them — and those are READABLE only
    through a shaper. Pillow falls back to the basic engine silently, so the
    choice is refusing or serving a picture of a name nobody wrote. Same for a
    coverage manifest that will not load: the projection cannot run at all."""
    monkeypatch.setattr(main, "_pcf", _Face())
    assert main._pc_renderer_unavailable() is None

    monkeypatch.setattr(main, "_pc_raqm", lambda: False)
    assert main._pc_renderer_unavailable() == "text_shaping_unavailable"
    monkeypatch.setattr(main, "_pc_raqm", lambda: True)

    monkeypatch.setattr(main._pcp, "coverage_ready", lambda: "manifest gone")
    assert main._pc_renderer_unavailable() == "name_coverage_unavailable"
    monkeypatch.setattr(main, "_pcf", None)
    assert main._pc_renderer_unavailable() == "image_processing_unavailable"


def test_the_pack_writer_refuses_before_it_debits(monkeypatch):
    """The route commits a debit and THEN builds an answer that projects names
    and keys faces. A box that cannot do either charged the player, minted the
    prints and raised 500 on the way out — and the recovery route raised the
    same 500. A precondition is only one if it is checked while refusing is
    still free."""
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "secret")
    monkeypatch.setattr(main, "_pcf", _Face())
    monkeypatch.setattr(main, "_pc_raqm", lambda: False)
    db = Scripted({})
    with pytest.raises(HTTPException) as ex:
        _run(main.pc_open_pack(request=_Req(), steam_id=STEAM, sig="x", nonce="nonce-0001",
                               pay="gold", expected_price=100, pack_id=None, db=db))
    assert ex.value.status_code == 503 and ex.value.detail == "text_shaping_unavailable"
    assert db.log == [], "a refusal that reached the database is not a precondition"
    assert db.committed == 0


def test_the_neutral_label_passes_the_predicate_the_name_failed(monkeypatch):
    """§2.4 step 3. `pc.unnamed` is the string a card shows when the NAME was
    empty, or its own Steam ID, or nothing but joiners — so a catalogue target
    that fails the same predicate cannot be the answer, and the built-in label
    (which passes by construction) is."""
    face = _Face()
    face.ENGLISH = dict(face.ENGLISH, **{"pc.unnamed": "Unnamed player"})
    monkeypatch.setattr(main, "_pcf", face)

    def labels_for(target):
        rows = [{"msgctxt": f"Unnamed playerpc.unnamed", "target": target}]
        return _run(main._pc_labels(Scripted({"FROM i18n_entries": [rows],
                                              "SELECT": [rows]}), "uk"))["pc.unnamed"]

    assert labels_for("Гравець без імені") == "Гравець без імені"
    assert labels_for(STEAM) == "Unnamed player", "a Steam-ID-shaped target is not a label"
    assert labels_for("   ") == "Unnamed player"
    assert labels_for("‍‍") == "Unnamed player", "joiners paint nothing"
    assert labels_for("AB") == "AB", "undrawable removed, the rest kept"


def test_a_payload_names_a_nameless_card_the_way_its_face_does(monkeypatch):
    """The face drew the LOCALISED `pc.unnamed`, the payload carried null, the
    client substituted its own string and Discord printed a built-in English
    one: three surfaces, three answers, one card."""
    row = _print_row(subject_name=STEAM)
    ctx = _ctx(labels={"pc.unnamed": "Гравець без імені", "pc.edition": "Видання"})
    assert main._pc_print_dict(row, ctx)["subject_name"] == "Гравець без імені"
    assert main._pc_neutral_name(ctx) == "Гравець без імені"
    # without a context there is no locale to be right about, and the built-in
    # is the string the DLL falls back to — the same bytes, not a translation
    # that happens to match
    assert main._pc_print_dict(row, None)["subject_name"] is None
    assert main._pc_neutral_name() == "Unnamed player" == main._PC_NEUTRAL_NAME


def test_the_pack_answer_carries_the_copy_count_the_mint_took():
    """`dup_at_pull` was written to pc_events and to the pack row's stored
    answer, and `_pc_pack_answer` rebuilds its prints FROM THE PRINTS TABLE,
    which has no such column — so the field the reveal strip labels NEW and
    DUPLICATE with never reached the client, and every test that touched it
    asserted `_pc_mint`'s return value instead of the wire answer."""
    ids = [uuid4() for _ in range(3)]
    stored = {"prints": [{"print_id": str(ids[0]), "dup_at_pull": 0},
                         {"print_id": str(ids[1]), "dup_at_pull": 3},
                         {"print_id": str(ids[2])}]}          # a slot from before the field
    rows = [_print_row(print_id=i, slot=n) for n, i in enumerate(ids)]

    def run(answer):
        db = Scripted({"WHERE pr.pack_id": [rows],
                       "SELECT result FROM pc_packs": [[{"result": answer}]]})
        return [p.get("dup_at_pull", "absent")
                for p in _run(main._pc_prints_of_pack(db, uuid4()))]

    assert run(stored) == [0, 3, "absent"]
    # the join is by id, not by position: the same answer in the other order
    assert run({"prints": list(reversed(stored["prints"]))}) == [0, 3, "absent"]
    # a JSON string (asyncpg hands jsonb back as text on some drivers) reads the same
    assert run(json.dumps(stored)) == [0, 3, "absent"]
    # and a pack with no stored answer at all says nothing rather than 0
    assert run(None) == ["absent"] * 3
    # ...and one query for the pack, not one per print
    db = Scripted({"WHERE pr.pack_id": [rows],
                   "SELECT result FROM pc_packs": [[{"result": stored}]]})
    _run(main._pc_prints_of_pack(db, uuid4()))
    assert db.count("SELECT result FROM pc_packs") == 1


def test_the_mint_counts_the_copies_the_opener_already_held(monkeypatch):
    """`dup_at_pull` was selected by the events route and emitted to the bot,
    and nothing wrote it — so a sixth identical copy announced exactly like
    the first. It is counted BEFORE the slot's own insert, sequentially, so
    two identical slots in one pack read 0 and then 1."""
    db = Scripted({
        "INSERT INTO pc_cards": [[{"id": uuid4()}]],
        "SELECT COUNT(*) FROM pc_prints pr JOIN pc_cards c": [[{"n": n}] for n in (0, 1, 4)],
        "INSERT INTO pc_prints": [[{"id": uuid4(), "minted_at": NOW}] for _ in range(3)],
    })
    rolled = [{"player_id": str(PID), "slot": i, "rarity": "legendary", "rolled": "legendary",
               "foil": False, "signed": False, "pool_rank": 1, "rating": 1800.0, "peak_rating": 1800.0,
               "board_rank": 2, "series_wins": 1, "series_losses": 0, "top_card": None, "title": None}
              for i in range(3)]
    out = _run(main._pc_mint(db, PID, 1, 9, uuid4(), "pack", rolled))
    assert [o["dup_at_pull"] for o in out] == [0, 1, 4]
    # the count runs BEFORE the print insert of its own slot
    first_count = _idx(db, "SELECT COUNT(*) FROM pc_prints pr JOIN pc_cards c")
    assert first_count < _idx(db, "INSERT INTO pc_prints")
    # ...and every event row carries it
    events = [p for sql, p in db.log if "INSERT INTO pc_events" in sql]
    assert events and all("dup" in p for p in events)
    # two kinds per slot here (legendary, and the opener pulled their own
    # card), and BOTH rows of a slot carry that slot's count
    assert [p["dup"] for p in events] == [0, 0, 1, 1, 4, 4]
    # a discarded copy is not one the opener holds
    sql = [s for s, _ in db.log if "SELECT COUNT(*) FROM pc_prints pr JOIN pc_cards c" in s][0]
    assert "discarded_at IS NULL" in sql and "c.subject_player_id" in sql
    assert "pr.rarity" in sql and "pr.foil" in sql and "pr.signed" in sql


def test_the_public_pool_answers_no_identifier_and_projects_the_names():
    """/pc/pool takes no signature, no session and no key: it answers anyone."""
    db = Scripted({
        "FROM pc_pool_snapshots ORDER BY id DESC": [[{"id": 4, "taken_at": NOW, "member_count": 2}]],
        "GROUP BY rarity": [[{"rarity": "legendary", "n": 1}]],
        "FROM pc_pool_members m JOIN players p": [[
            {"pool_rank": 1, "rarity": "legendary", "board_rank": 3, "rating": 1800.0, "display_name": "Sid"},
            {"pool_rank": 2, "rarity": "rare", "board_rank": 9, "rating": 1700.0, "display_name": STEAM},
        ]],
    })
    ans = _run(main.pc_pool_summary(db=db))
    assert [t["display_name"] for t in ans["top"]] == ["Sid", "Unnamed player"]
    assert "steam_id" not in json.dumps(ans) and STEAM not in json.dumps(ans)
    # the identifier is not in the SELECT either — an answer key can be dropped
    # while the column keeps travelling into logs and tracebacks
    select = [s for s, _ in db.log if "FROM pc_pool_members m JOIN players p" in s][0]
    assert "steam_id" not in select, select


def test_raqm_is_read_from_the_engine_actually_in_use(monkeypatch):
    """`runtime_provenance()` has no top-level "raqm" key: it reports the
    capability under features.raqm.available and the engine in use under
    layout_engine. Reading the top level answered false for every image ever
    built — including a compliant one a deploy assertion would then reject."""
    prov = {"features": {"raqm": {"available": True, "version": "0.10.1"}}, "layout_engine": "raqm"}
    monkeypatch.setattr(main, "_pcf", SimpleNamespace(runtime_provenance=lambda: prov))
    assert main._pc_raqm() is True
    prov["layout_engine"] = "basic"      # the feature is built in but not in use
    assert main._pc_raqm() is False
    monkeypatch.setattr(main, "_pcf", SimpleNamespace(runtime_provenance=lambda: (_ for _ in ()).throw(RuntimeError())))
    assert main._pc_raqm() is False
    monkeypatch.setattr(main, "_pcf", None)
    assert main._pc_raqm() is False


@pytest.mark.parametrize("days,expect", [
    (None, "untouched"),        # the deletion path: an admin lock is not the deleter's business
    (0, "NULL"),                # "0 = no lock", which means the earlier one goes
    (7, "interval"),
])
def test_the_clear_unit_reads_lock_days_as_leave_alone_clear_or_set(days, expect):
    db = Scripted({"SELECT pc_game_portrait_hash, pc_steam_portrait_hash FROM players": [[{"pc_game_portrait_hash": None, "pc_steam_portrait_hash": None}]],
                   "RETURNING pc_game_portrait_locked_until": [[{"l": None}]]})
    _run(main._pc_clear_portrait_unit(db, str(PID), lock_days=days, source=None))
    upd = db.log[_idx(db, "UPDATE players SET")]
    sets = upd[0].split("RETURNING")[0]
    if expect == "untouched":
        assert "pc_game_portrait_locked_until" not in sets, sets
    elif expect == "NULL":
        assert "pc_game_portrait_locked_until = NULL" in sets and "make_interval" not in sets
    else:
        assert "make_interval(days =>" in sets and upd[1]["days"] == 7


def test_the_admin_clear_passes_lock_days_through_without_folding_zero():
    src = _src(main.admin_pc_portrait_clear)
    assert "lock_days=lock_days" in src and "lock_days or None" not in src


def test_the_portrait_lock_class_is_the_only_two_argument_advisory_class():
    assert P.PC_P_LOCK_CLASS == 770902
    numeric = re.findall(r"pg_(?:try_)?advisory(?:_xact)?_lock(?:_shared)?\(\s*(\d+)\s*,", MAIN_SRC)
    assert numeric == [], numeric
    for name, value in re.findall(r"^([A-Z_]*LOCK_CLASS[A-Z_]*)\s*=\s*(\d+)", MAIN_SRC, re.M):
        assert int(value) != P.PC_P_LOCK_CLASS, name
    two_arg = re.findall(r"pg_advisory_xact_lock\(CAST\(:cls AS integer\), hashtext\(CAST\(:h AS text\)\)\)", MAIN_SRC)
    assert len(two_arg) >= 1
    assert MAIN_SRC.count('"cls": _pcp.PC_P_LOCK_CLASS') == len(two_arg)
    # and P has exactly ONE statement, `_pc_lock_blob`, with two callers: the
    # per-player set `_pc_lock_portrait_blobs` (which is what keeps "P before
    # R" a property of the code rather than of each caller) and the blob
    # janitor, which takes P before its guarded delete (Steam pictures v2 §6)
    body = _src(main._pc_lock_blob)
    assert body.count("CAST(:cls AS integer)") == len(two_arg) == 1
    assert _src(main._pc_lock_portrait_blobs).count("await _pc_lock_blob(") == 1
    assert _src(main._pc_portrait_blob_janitor).count("await _pc_lock_blob(") == 1
    assert MAIN_SRC.count("await _pc_lock_blob(") == 2


def test_the_acquire_and_the_revalidation_read_the_same_resolver_inputs():
    """`portrait_for` decides what a lease authorises. If the two statements
    that feed it selected different columns, one of them would resolve from a
    default and the two would disagree about the same subject."""
    assert main._PC_PORTRAIT_RESOLVE_COLS.count(" AS ") == 6   # + steam_portrait_hash (Steam pictures v2 §1)
    for col in ("subject_deleted", "subject_opted_out", "portrait_source", "portrait_hash", "subject_banned",
                "steam_portrait_hash"):
        assert f"AS {col}" in main._PC_PORTRAIT_RESOLVE_COLS, col
    for fn in (main.internal_pc_lease, main.internal_pc_lease_check):
        src = _src(fn)
        assert "_PC_PORTRAIT_RESOLVE_COLS" in src and "_pcp.portrait_for(" in src, fn.__name__
    # and nothing restates the rule in SQL beside it
    assert "pc_opted_out_at IS NOT NULL" not in _src(main.internal_pc_lease_check)


# ── the lease primitive ─────────────────────────────────────────────────────

def _sub(**over):
    row = {"subject_deleted": False, "subject_opted_out": False, "portrait_source": "game",
           "portrait_hash": "ef" * 32, "subject_banned": False}
    row.update(over)
    return row


def _lease_db(steam="765", got=True, sub=None, depicts=True):
    lease_id = uuid4()
    return Scripted({
        "SELECT steam_id FROM players": [[{"steam_id": steam}] if steam else []],
        "pg_try_advisory_xact_lock": [[{"got": got}]],
        "AS subject_banned": [[sub if sub is not None else _sub()]],
        # the print named must depict the subject named
        "FROM pc_prints pr JOIN pc_cards c": [[{"one": 1}] if depicts else []],
        "INSERT INTO pc_delivery_leases": [[{"id": lease_id, "until": NOW + timedelta(seconds=60)}]],
    }), lease_id


def test_lease_acquire_refuses_a_print_that_does_not_depict_the_subject(monkeypatch):
    """A binder is mostly other people's cards. Leasing its owner for a print
    of someone else puts the owner's permission, ban state and portrait in
    place of the subject's, so the pair is checked here rather than trusted."""
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    db, _ = _lease_db(depicts=False)
    with pytest.raises(HTTPException) as ex:
        _run(main.internal_pc_lease({"subject_ref": str(PID), "print_id": str(PID)}, "k", db))
    assert ex.value.status_code == 404 and ex.value.detail == {"error": "print_not_of_subject"}
    assert db.rolled_back == 1 and db.count("INSERT INTO pc_delivery_leases") == 0
    # the check is made UNDER the identity lock, not before it
    assert _idx(db, "pg_try_advisory_xact_lock") < _idx(db, "FROM pc_prints pr JOIN pc_cards c")
    # a lease naming no print does not consult pc_prints at all
    db, _ = _lease_db()
    _run(main.internal_pc_lease({"subject_ref": str(PID)}, "k", db))
    assert db.count("FROM pc_prints pr JOIN pc_cards c") == 0


def test_lease_acquire_try_locks_the_identity_then_resolves_under_it(monkeypatch):
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    db, lease_id = _lease_db()
    ans = _run(main.internal_pc_lease({"subject_ref": str(PID), "print_id": str(PID), "event_ids": [3, "4"]}, "k", db))
    assert ans == {"lease_id": str(lease_id), "until": (NOW + timedelta(seconds=60)).isoformat(),
                   "portrait_kind": "game", "portrait_hash": "ef" * 32}
    order = [_idx(db, k) for k in ("SELECT steam_id FROM players", "pg_try_advisory_xact_lock", "AS subject_banned",
                                   "INSERT INTO pc_delivery_leases")]
    assert order == sorted(order)
    ins = db.log[_idx(db, "INSERT INTO pc_delivery_leases")]
    assert ins[1] == {"sid": str(PID), "print": str(PID), "ids": [3, 4], "h": "ef" * 32, "secs": 60.0}
    assert "make_interval(secs =>" in ins[0] and db.committed == 1
    assert db.log[_idx(db, "pg_try_advisory_xact_lock")][1] == {"sid": "765"}


def test_lease_acquire_answers_409_subject_busy_when_the_identity_is_held(monkeypatch):
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    db, _ = _lease_db(got=False)
    with pytest.raises(HTTPException) as ex:
        _run(main.internal_pc_lease({"subject_ref": str(PID)}, "k", db))
    assert ex.value.status_code == 409 and ex.value.detail == {"error": "subject_busy", "retry_after": 2}
    assert db.rolled_back == 1 and db.count("INSERT INTO pc_delivery_leases") == 0


def test_lease_acquire_resolves_none_for_an_opted_out_subject_and_404s_a_deleted_one(monkeypatch):
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    db, _ = _lease_db(sub=_sub(subject_opted_out=True))
    ans = _run(main.internal_pc_lease({"subject_ref": str(PID)}, "k", db))
    assert ans["portrait_kind"] == "none" and ans["portrait_hash"] is None
    assert db.log[_idx(db, "INSERT INTO pc_delivery_leases")][1]["h"] is None
    db, _ = _lease_db(steam=None)
    with pytest.raises(HTTPException) as ex:
        _run(main.internal_pc_lease({"subject_ref": str(PID)}, "k", db))
    assert ex.value.status_code == 404 and db.count("pg_try_advisory_xact_lock") == 0
    db, _ = _lease_db(sub=_sub(subject_deleted=True))
    with pytest.raises(HTTPException) as ex:
        _run(main.internal_pc_lease({"subject_ref": str(PID)}, "k", db))
    assert ex.value.status_code == 404 and db.rolled_back == 1


def test_lease_acquire_validates_its_payload_before_any_database_work(monkeypatch):
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    for payload in ({"subject_ref": "not-a-uuid"}, {"subject_ref": str(PID), "print_id": "x"},
                    {"subject_ref": str(PID), "event_ids": ["a"]}):
        db = Scripted({})
        with pytest.raises(HTTPException) as ex:
            _run(main.internal_pc_lease(payload, "k", db))
        assert ex.value.status_code == 422 and db.log == [], payload
    db, _ = _lease_db()
    _run(main.internal_pc_lease({"subject_ref": str(PID), "event_ids": list(range(500))}, "k", db))
    assert len(db.log[_idx(db, "INSERT INTO pc_delivery_leases")][1]["ids"]) == 200


def _check_row(**over):
    """What the revalidation reads: the lease, and the subject's resolver
    inputs as they stand NOW."""
    row = {"until": NOW, "unexpired": True, "leased_hash": "ef" * 32, "print_deliverable": True,
           "subject_deleted": False, "subject_opted_out": False, "portrait_source": "game",
           "portrait_hash": "ef" * 32, "subject_banned": False}
    row.update(over)
    return row


@pytest.mark.parametrize("over,live", [
    ({}, True),
    ({"unexpired": False}, False),                                   # the clock
    ({"subject_deleted": True}, False),
    ({"print_deliverable": False}, False),                           # discarded, gone, or not theirs
    ({"subject_banned": True}, False),                               # banned since the acquire
    ({"subject_opted_out": True}, False),                            # opted out since the acquire
    ({"portrait_source": "none"}, False),                            # switched off since the acquire
    ({"portrait_hash": "ab" * 32}, False),                           # replaced since the acquire
    ({"leased_hash": None, "portrait_hash": None}, True),            # no picture then, none now
    ({"leased_hash": None, "portrait_source": "none"}, True),        # resolved none then and now
    ({"leased_hash": None}, False),                                  # none then, a picture now
])
def test_lease_check_answers_live_only_while_it_still_authorises_that_picture(monkeypatch, over, live):
    """The lease is not "a row that exists": it is the resolution recorded at
    acquire, re-resolved. Every writer that moves the resolution revokes it
    without having to find the row — including the one that cannot see it, a
    discard committing under a DIFFERENT subject's identity lock."""
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    lid = str(uuid4())
    db = Scripted({"FROM pc_delivery_leases l JOIN players p": [[_check_row(**over)]]})
    if live:
        assert _run(main.internal_pc_lease_check(lid, "k", db)) == {
            "lease_id": lid, "until": NOW.isoformat(), "live": True}
    else:
        with pytest.raises(HTTPException) as ex:
            _run(main.internal_pc_lease_check(lid, "k", db))
        assert ex.value.status_code == 404 and ex.value.detail == {"error": "lease_gone"}


def test_lease_check_and_release(monkeypatch):
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    lid = str(uuid4())
    db = Scripted({"FROM pc_delivery_leases l JOIN players p": [[_check_row()]]})
    assert _run(main.internal_pc_lease_check(lid, "k", db)) == {"lease_id": lid, "until": NOW.isoformat(), "live": True}
    # the print's deliverability is decided in the same statement, so it cannot
    # be read from a snapshot the lease row was not read in
    sql = db.log[0][0]
    assert "print_deliverable" in sql and "pc_prints" in sql and "pc_cards" in sql
    for rows in ([_check_row(unexpired=False)], []):
        db = Scripted({"FROM pc_delivery_leases l JOIN players p": [rows]})
        with pytest.raises(HTTPException) as ex:
            _run(main.internal_pc_lease_check(lid, "k", db))
        assert ex.value.status_code == 404 and ex.value.detail == {"error": "lease_gone"}
    db = Scripted({})
    with pytest.raises(HTTPException):
        _run(main.internal_pc_lease_check("nope", "k", db))
    assert db.log == []
    db = Scripted({"DELETE FROM pc_delivery_leases WHERE id": [[{"id": lid}]]})
    assert _run(main.internal_pc_lease_release(lid, "k", db)) == {"released": 1} and db.committed == 1
    db = Scripted({})
    assert _run(main.internal_pc_lease_release("nope", "k", db)) == {"released": 0} and db.log == []


def test_the_internal_key_gate_is_the_first_statement_of_every_internal_pc_route():
    import ast
    import textwrap
    for fn in (main.internal_pc_lease, main.internal_pc_lease_check, main.internal_pc_lease_release,
               main.internal_pc_face_print, main.internal_pc_face_preview, main.internal_pc_face_back):
        body = ast.parse(textwrap.dedent(_src(fn))).body[0].body
        if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]   # the docstring
        first = body[0]
        assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call), fn.__name__
        assert getattr(first.value.func, "id", None) == "_require_internal_key", fn.__name__


# ── the clear unit and the admin clear ──────────────────────────────────────

def test_lease_wait_reads_only_live_leases():
    db = Scripted({"FROM pc_delivery_leases": [[{"left": 12}]]})
    assert _run(main._pc_lease_wait(db, str(PID))) == 12
    assert "until > now()" in db.log[0][0] and db.log[0][1] == {"pid": str(PID)}
    assert _run(main._pc_lease_wait(Scripted({"FROM pc_delivery_leases": [[{"left": None}]]}), str(PID))) is None
    assert _run(main._pc_lease_wait(Scripted({"FROM pc_delivery_leases": [[{"left": 0.4}]]}), str(PID))) == 1


def test_clear_unit_locks_hash_then_row_then_writes_then_deletes_the_orphan():
    """P BEFORE R (the order is V → I → C → P → R).

    This test used to assert the opposite, because that is what the code did:
    the hash was read with FOR NO KEY UPDATE and the blob lock taken after. Two
    players sharing a portrait then deadlock — one deletion holds R(A) and
    waits for P(H) while the other holds P(H) and waits for R(A) to refund A's
    bets. A test that pins the defect turns red on the fix and green on the
    bug, which is worse than no test (#441), so the order assertion is now the
    right way round and the unlocked key read is named explicitly."""
    until = NOW + timedelta(days=7)
    db = Scripted({"SELECT pc_game_portrait_hash, pc_steam_portrait_hash FROM players": [[{"pc_game_portrait_hash": "old" * 20, "pc_steam_portrait_hash": None}]],
                   "RETURNING pc_game_portrait_locked_until": [[{"l": until}]]})
    assert _run(main._pc_clear_portrait_unit(db, str(PID), lock_days=7, source="none")) == ("old" * 20, until)
    order = [_idx(db, k) for k in ("CAST(:cls AS integer)", "FOR NO KEY UPDATE", "UPDATE players SET", "UPDATE pc_portraits SET unreferenced_since")]
    assert order == sorted(order), db.log
    # the key read that P is taken on carries no row lock of its own
    assert "FOR NO KEY UPDATE" not in db.log[0][0]
    assert "SELECT pc_game_portrait_hash, pc_steam_portrait_hash FROM players" in db.log[0][0]
    plock = db.log[_idx(db, "CAST(:cls AS integer)")]
    assert plock[1] == {"cls": P.PC_P_LOCK_CLASS, "h": "old" * 20}
    upd = db.log[_idx(db, "UPDATE players SET")]
    assert "make_interval(days => CAST(:days AS integer))" in upd[0] and upd[1]["days"] == 7
    assert "pc_portrait_source = CAST(:src AS text)" in upd[0] and upd[1]["src"] == "none"
    assert "pc_game_portrait_hash = NULL" in upd[0] and "pc_game_portrait_descriptor = NULL" in upd[0]
    assert "NOT EXISTS" in db.log[_idx(db, "UPDATE pc_portraits SET unreferenced_since")][0]
    # no previous blob: no hash lock, no delete; no lock_days / source: neither clause
    db = Scripted({"SELECT pc_game_portrait_hash, pc_steam_portrait_hash FROM players": [[{"pc_game_portrait_hash": None, "pc_steam_portrait_hash": None}]],
                   "RETURNING pc_game_portrait_locked_until": [[{"l": None}]]})
    assert _run(main._pc_clear_portrait_unit(db, str(PID), lock_days=None, source=None)) == (None, None)
    assert db.count("CAST(:cls AS integer)") == 0 and db.count("UPDATE pc_portraits SET unreferenced_since") == 0
    upd = db.log[_idx(db, "UPDATE players SET")]
    assert "make_interval" not in upd[0] and "pc_portrait_source" not in upd[0]


def test_admin_clear_verifies_then_locks_then_waits_out_leases(monkeypatch):
    calls = []

    async def admin(db, admin_id, action, target, sig):
        calls.append((admin_id, action, target, sig))
        db.log.append(("ADMIN", None))
    monkeypatch.setattr(main, "_require_admin", admin)
    db = Scripted({"SELECT id FROM players WHERE steam_id": [[{"id": PID}]],
                   "FROM pc_delivery_leases": [[{"left": None}]],
                   "SELECT pc_game_portrait_hash, pc_steam_portrait_hash FROM players": [[{"pc_game_portrait_hash": "old" * 20, "pc_steam_portrait_hash": None}]],
                   "RETURNING pc_game_portrait_locked_until": [[{"l": NOW}]]})
    ans = _run(main.admin_pc_portrait_clear({"admin_steam_id": "1", "steam_id": STEAM, "lock_days": 99999,
                                             "signature": "s"}, db))
    assert ans == {"cleared": True, "had_portrait": True, "locked_until": NOW.isoformat()}
    assert calls == [("1", "pc_portrait_clear", f"{STEAM}:3650", "s")]
    order = [_idx(db, k) for k in ("ADMIN", "pg_advisory_xact_lock(hashtext", "SELECT id FROM players WHERE steam_id",
                                   "FROM pc_delivery_leases", "UPDATE players SET")]
    assert order == sorted(order) and db.committed == 1
    assert db.log[_idx(db, "UPDATE players SET")][1]["days"] == 3650
    # a live lease: 409 with its remaining seconds, nothing written
    db = Scripted({"SELECT id FROM players WHERE steam_id": [[{"id": PID}]],
                   "FROM pc_delivery_leases": [[{"left": 7}]]})
    with pytest.raises(HTTPException) as ex:
        _run(main.admin_pc_portrait_clear({"admin_steam_id": "1", "steam_id": STEAM, "lock_days": 0, "signature": "s"}, db))
    assert ex.value.status_code == 409 and ex.value.detail == {"error": "retry_after", "retry_after": 7}
    assert db.rolled_back == 1 and db.count("UPDATE players SET") == 0
    # lock_days 0 → no lock clause; a non-string signature is treated as absent
    db = Scripted({"SELECT id FROM players WHERE steam_id": [[{"id": PID}]],
                   "FROM pc_delivery_leases": [[{"left": None}]],
                   "SELECT pc_game_portrait_hash, pc_steam_portrait_hash FROM players": [[{"pc_game_portrait_hash": None, "pc_steam_portrait_hash": None}]],
                   "RETURNING pc_game_portrait_locked_until": [[{"l": None}]]})
    _run(main.admin_pc_portrait_clear({"admin_steam_id": "1", "steam_id": STEAM, "lock_days": -4, "signature": 5}, db))
    assert calls[-1] == ("1", "pc_portrait_clear", f"{STEAM}:0", "")
    assert "make_interval" not in db.log[_idx(db, "UPDATE players SET")][0]


# ── faces ───────────────────────────────────────────────────────────────────

def _face_row(**over):
    row = {"subject_deleted": False, "subject_banned": False, "subject_opted_out": False, "portrait_source": "game",
           "portrait_hash": None, "subject_name": "Sid", "rating": None, "title": None, "rarity": "rare",
           "foil": False, "signed": False, "minted_at": NOW, "pool_rank": 12, "board_rank": None,
           "series_wins": 3, "series_losses": 1, "edition_id": 1, "print_id": PID, "top_card": False,
           "discarded_at": None}
    row.update(over)
    return row


def _ctx(**over):
    ctx = {"locale": "en", "renderer_fp": "f" * 16, "labels": {"pc.edition": "Edition"}, "cat_rev": "0" * 16, "colors": {}}
    ctx.update(over)
    return ctx


def test_face_inputs_draw_the_public_name_and_key_every_input():
    spec, kind, phash, rev = main._pc_face_inputs(_face_row(subject_name="<b>Sid</b>"), _ctx())
    assert spec["name"] == "Sid" and kind == "none" and phash is None and re.match(r"^[0-9a-f]{16}$", rev)
    assert spec["edition_label"] == "Edition 1" and spec["minted_on"] == "2026-09-12"
    assert spec["print_short"] == "#" + str(PID).replace("-", "")[:6] and spec["title"] is None
    assert main._pc_face_inputs(_face_row(subject_name=STEAM), _ctx())[0]["name"] == ""
    assert main._pc_face_inputs(_face_row(portrait_hash="ab" * 32), _ctx())[1:3] == ("game", "ab" * 32)
    assert main._pc_face_inputs(_face_row(portrait_hash="ab" * 32, subject_banned=True), _ctx())[1:3] == ("none", None)
    assert main._pc_face_inputs(_face_row(), _ctx(cat_rev="1" * 16))[3] != rev


def test_render_face_answers_none_on_a_revision_mismatch_before_any_render(monkeypatch, tmp_path):
    face = _Face()
    monkeypatch.setattr(main, "_pcf", face)
    monkeypatch.setattr(main, "_pc_face_cache", P.FaceCache(str(tmp_path)))
    row, ctx = _face_row(), _ctx()
    rev = main._pc_face_inputs(row, ctx)[3]
    db = Scripted({"SELECT bytes FROM pc_portraits": [[{"bytes": b"portrait"}]]})
    assert _run(main._pc_render_face(db, row, ctx, "card", want="0" * 16)) == (rev, None)
    assert db.log == [] and face.rendered == []
    got = _run(main._pc_render_face(db, row, ctx, "tile", want=rev))
    assert got == (rev, b"\x89PNGtile") and face.rendered[0][1] == "tile" and face.rendered[0][2] is None
    assert os.path.exists(os.path.join(str(tmp_path), P.face_key(str(PID), rev, "en", "tile")))
    # a game portrait: its bytes are read by hash and handed to the renderer
    row2 = _face_row(portrait_hash="ab" * 32)
    got2 = _run(main._pc_render_face(db, row2, ctx, "card"))
    assert face.rendered[-1][2] == b"portrait" and got2[1] == b"\x89PNGcard"
    assert db.log[-1][1] == {"h": "ab" * 32}


def test_public_face_route_validates_shape_and_locale_before_the_row_read(monkeypatch, tmp_path):
    face = _Face()
    monkeypatch.setattr(main, "_pcf", face)
    monkeypatch.setattr(main, "_pc_face_cache", P.FaceCache(str(tmp_path)))
    monkeypatch.setattr(main, "_pc_served_locales", lambda: {"uk"})
    reads = []
    row = _face_row()

    async def face_row(db, print_id):
        reads.append(print_id)
        return row

    async def ctx(db, locale):
        return _ctx(locale=locale)
    monkeypatch.setattr(main, "_pc_face_row", face_row)
    monkeypatch.setattr(main, "_pc_face_ctx", ctx)
    rev = main._pc_face_inputs(row, _ctx(locale="uk"))[3]
    db = Scripted({})
    for args in ((str(PID).upper(), rev, "uk", "card"), (str(PID), rev, "fr", "card"), (str(PID), rev, "uk", "huge"),
                 (str(PID), "A" * 16, "uk", "card")):
        with pytest.raises(HTTPException) as ex:
            _run(main.pc_face_png(*args, db=db))
        assert ex.value.status_code == 404 and reads == [], args
    with pytest.raises(HTTPException) as ex:
        _run(main.pc_face_png(str(PID), "0" * 16, "uk", "card", db=db))
    assert ex.value.status_code == 404 and reads == [str(PID)] and face.rendered == []
    resp = _run(main.pc_face_png(str(PID), rev, "uk", "card", db=db))
    assert resp.media_type == "image/png" and resp.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert resp.body == b"\x89PNGcard" and resp.headers["content-length"] == str(len(resp.body))
    row["discarded_at"] = NOW
    with pytest.raises(HTTPException) as ex:
        _run(main.pc_face_png(str(PID), rev, "uk", "card", db=db))
    assert ex.value.status_code == 404


def test_internal_print_face_answers_the_current_revision_in_a_header(monkeypatch, tmp_path):
    face = _Face()
    monkeypatch.setattr(main, "_pcf", face)
    monkeypatch.setattr(main, "_pc_face_cache", P.FaceCache(str(tmp_path)))
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    row = _face_row()

    async def face_row(db, print_id):
        return row

    async def ctx(db, locale):
        return _ctx(locale=locale)
    monkeypatch.setattr(main, "_pc_face_row", face_row)
    monkeypatch.setattr(main, "_pc_face_ctx", ctx)
    resp = _run(main.internal_pc_face_print(str(PID), "fr", "card", "k", Scripted({})))
    assert resp.headers["x-face-rev"] == main._pc_face_inputs(row, _ctx(locale="en"))[3]
    assert resp.headers["cache-control"] == "private, max-age=60"
    with pytest.raises(HTTPException) as ex:
        _run(main.internal_pc_face_print(str(PID), "en", "poster", "k", Scripted({})))
    assert ex.value.status_code == 404


def test_preview_face_reapplies_the_card_gate_before_the_member_read(monkeypatch):
    monkeypatch.setattr(main, "_pcf", _Face())
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    for sub in (_sub(subject_opted_out=True), _sub(subject_banned=True), _sub(subject_deleted=True)):
        db = Scripted({"AS subject_banned": [[{"display_name": "Sid", **sub}]]})
        with pytest.raises(HTTPException) as ex:
            _run(main.internal_pc_face_preview(str(PID), "en", "k", db))
        assert ex.value.status_code == 404 and ex.value.detail == {"error": "not_in_pool"}
        assert db.count("pc_pool_members") == 0
    db = Scripted({"AS subject_banned": [[{"display_name": "Sid", **_sub()}]], "FROM pc_pool_members": [[]]})
    with pytest.raises(HTTPException) as ex:
        _run(main.internal_pc_face_preview(str(PID), "en", "k", db))
    assert ex.value.status_code == 404 and db.count("pc_pool_members") == 1


def test_the_back_is_served_from_the_bundle_with_its_length(monkeypatch, tmp_path):
    face = _Face()
    face.ASSETS_DIR = str(tmp_path)
    with open(os.path.join(str(tmp_path), "Back.png"), "wb") as f:
        f.write(b"\x89PNG-back-bytes")
    monkeypatch.setattr(main, "_pcf", face)
    monkeypatch.setattr(main, "_pc_back_cache", {"bytes": None})
    monkeypatch.setattr(main, "_require_internal_key", lambda k: None)
    resp = _run(main.internal_pc_face_back("k"))
    assert resp.body == b"\x89PNG-back-bytes" and resp.headers["content-length"] == "15"


def test_labels_overlay_the_composite_msgctxt_rows_of_the_client_namespace(monkeypatch):
    face = _Face()
    face.ENGLISH = {"pc.edition": "Edition", "pc.foil": "Foil"}
    monkeypatch.setattr(main, "_pcf", face)
    db = Scripted({"FROM i18n_entries": [[{"msgctxt": "Edition\x04pc.edition", "target": "Видання\n"},
                                          {"msgctxt": "Foil\x04pc.foil", "target": "  "}]]})
    labels = _run(main._pc_labels(db, "uk"))
    assert labels == {"pc.edition": "Видання", "pc.foil": "Foil"}
    sql, params = db.log[0]
    assert "k.namespace = 'client'" in sql and "(k.sensitive IS FALSE OR e.state = 'approved')" in sql
    assert params == {"lang": "uk", "ctxs": ["Edition\x04pc.edition", "Foil\x04pc.foil"]}
    db = Scripted({})
    assert _run(main._pc_labels(db, "en")) == {"pc.edition": "Edition", "pc.foil": "Foil"} and db.log == []


def test_request_locale_is_the_effective_locale_of_the_informational_header(monkeypatch):
    monkeypatch.setattr(main, "_pc_served_locales", lambda: {"uk", "sv"})
    assert main._pc_locale(SimpleNamespace(headers={"X-Locale": "uk-UA"})) == "uk"
    assert main._pc_locale(SimpleNamespace(headers={"X-Locale": "fr"})) == "en"
    assert main._pc_locale(SimpleNamespace(headers={})) == "en"
