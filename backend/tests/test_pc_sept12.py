"""Sept 12 gacha feedback batch — the server half.

The RANK slot draws the rating tier and only the tier; a shop title the
player wears is the header subtitle; the snapshot stores no rank-title text;
the daily paid-pack cap exempts ONE account (not admins); the pack history
pager route (`GET /api/v1/pc/packs`) pages newest-first on a keyset cursor
and never pre-renders."""
import inspect
import io
import os
import sys
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from PIL import Image, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import main  # noqa: E402
import pc_face  # noqa: E402
from test_player_cards_server import Scripted, _run  # noqa: E402
from test_pc_routes import NOW, PID, STEAM, _Req, _ctx, _face_row, _print_row  # noqa: E402

OTHER = "76561198000000001"   # a synthetic Steam-shaped id that is NOT exempt


def _src(fn):
    return inspect.getsource(fn)


def _tier(rating):
    return main._rank_name_for(main._pc_board_rating(rating))


# ── the RANK slot and the subtitle ─────────────────────────────────────

def test_the_rank_slot_draws_the_tier_never_the_shop_title():
    # the live case that started this: a 1487 player still wearing the
    # retired "Beta" title read "Beta" in the RANK slot
    spec = main._pc_face_inputs(_face_row(rating=1487.0, title="Beta"), _ctx())[0]
    assert spec["title"] == _tier(1487.0) == "Beginner V"
    assert spec["subtitle"] == "Beta"
    # rank-title wearers minted before the change stored the rank's live
    # text: it is the rank, so no subtitle and no card that says its rank twice
    spec = main._pc_face_inputs(_face_row(rating=1500.0, title="Intermediate I"), _ctx())[0]
    assert spec["title"] == "Intermediate I" and spec["subtitle"] is None
    # ...even when the stored text is a DIFFERENT tier than the frozen rating's
    spec = main._pc_face_inputs(_face_row(rating=1800.0, title="Intermediate I"), _ctx())[0]
    assert spec["title"] == "Advanced III" and spec["subtitle"] is None
    # a real shop title becomes the subtitle
    spec = main._pc_face_inputs(_face_row(rating=1800.0, title="Champion"), _ctx())[0]
    assert spec["title"] == "Advanced III" and spec["subtitle"] == "Champion"
    # no rating: the RANK slot stays empty (RATING already says Unranked)
    spec = main._pc_face_inputs(_face_row(rating=None, title="Champion"), _ctx())[0]
    assert spec["title"] is None and spec["subtitle"] == "Champion"
    # the slot's colour follows the tier, not the title
    spec = main._pc_face_inputs(_face_row(rating=1800.0, title="Beta"), _ctx())[0]
    assert spec["title_rgb"] == main._pc_hex_rgb(main._rank_fallback_color("Advanced III"))


def test_every_tier_name_is_the_rank_and_not_a_subtitle():
    for _threshold, name in main.RANK_TIERS:
        assert main._pc_shop_title(name, "Beginner I") is None, name
    assert main._pc_shop_title("Beginner", "Beginner I") is None
    assert main._pc_shop_title("   ", "Advanced I") is None
    assert main._pc_shop_title("Champion", "Champion") is None
    assert main._pc_shop_title(None, None) is None
    assert main._pc_shop_title("Beta", "Beginner V") == "Beta"
    assert main._pc_shop_title("  Champion ", "Advanced I") == "Champion"


def test_the_subtitle_is_one_of_the_inputs_the_face_revision_covers():
    revs = {main._pc_face_inputs(_face_row(rating=1800.0, title=t), _ctx())[3]
            for t in ("Champion", "Beta", None)}
    assert len(revs) == 3, "a subtitle change that keeps the rev is a picture that never updates"


def test_the_print_answer_separates_the_tier_from_the_shop_title():
    d = main._pc_print_dict(_print_row(rating=2100.0, title="Master II"))   # legacy rank text
    assert d["rank_name"] == "Master II" and d["title"] is None
    d = main._pc_print_dict(_print_row(rating=2100.0, title="Beta"))
    assert d["rank_name"] == "Master II" and d["title"] == "Beta"
    d = main._pc_print_dict(_print_row(rating=None, title="Beta"))
    assert d["rank_name"] is None and d["title"] == "Beta"
    d = main._pc_print_dict(_print_row(discarded_at=NOW, discard_shards=5))
    assert d["discarded"] is True and d["discard_shards"] == 5
    assert main._pc_print_dict(_print_row())["discard_shards"] is None
    assert main._pc_print_dict(_print_row(discarded_at=None))["discarded"] is False


def test_the_renderer_draws_the_subtitle_under_the_name_and_nowhere_else():
    anchors = pc_face.LAYOUT["anchors"]
    assert anchors["subtitle"] == [54, 113] and anchors["name_subtitled"] == [54, 71]
    assert anchors["name"] == [54, 85]
    base = dict(band="rare", name="Ace", title="Advanced III", title_rgb=(52, 152, 219), rating=1800,
                pool_rank=12, board_rank=None, wins=3, losses=1, foil=False, signed=False,
                edition_label="Edition 1", minted_on="2026-09-12", print_short="#abc123", top_card=False)
    plain = Image.open(io.BytesIO(pc_face.render_face(dict(base, subtitle=None), {}, None, "card")))
    titled = Image.open(io.BytesIO(pc_face.render_face(dict(base, subtitle="Champion"), {}, None, "card")))
    header = tuple(pc_face.LAYOUT["rects"]["header"])
    assert ImageChops.difference(plain.crop(header), titled.crop(header)).convert("RGB").getbbox() is not None
    # the stats block is not the subtitle's to touch: RANK stays the tier
    stats = tuple(pc_face.LAYOUT["rects"]["stats"])
    assert ImageChops.difference(plain.crop(stats), titled.crop(stats)).convert("RGB").getbbox() is None
    # a blank subtitle is no subtitle: the name keeps its anchor
    blank = Image.open(io.BytesIO(pc_face.render_face(dict(base, subtitle="   "), {}, None, "card")))
    assert ImageChops.difference(plain.crop(header), blank.crop(header)).convert("RGB").getbbox() is None
    # the tile keeps the same two-way answer
    a = pc_face.render_face(dict(base, subtitle=None), {}, None, "tile")
    b = pc_face.render_face(dict(base, subtitle="Champion"), {}, None, "tile")
    assert a != b


def test_the_snapshot_stores_no_title_for_rank_title_wearers():
    src = _src(main._pc_take_snapshot)
    guard = 'if r["title_sku"] == TITLE_RANK_SKU:'
    assert src.count(guard) == 1
    at = src.index(guard)
    assert src.index("title = None", at) < src.index('"title": title', at), \
        "the NULL must land before the member params are built"


# ── the daily paid-pack cap exemption ──────────────────────────────────

def test_the_daily_cap_exemption_is_one_account_and_not_admins():
    assert main.PC_PACK_CAP_EXEMPT_STEAM_IDS == frozenset({STEAM})
    src = _src(main.pc_open_pack)
    guard = 'if source == "bought" and steam_id not in PC_PACK_CAP_EXEMPT_STEAM_IDS:'
    assert src.count(guard) == 1
    block = src[src.index(guard):src.index("# ── 4. the roll", src.index(guard))]
    assert "daily_cap" in block and "paid_packs_per_day" in block
    assert "_is_admin" not in block and "AdminUser" not in block, "the exemption is by Steam ID, not by admin"
    # the unexempt path still counts today's paid packs
    assert "source = 'bought' AND status = 'done'" in block


def _me_db(paid_today=5):
    settings = {"pc_opted_out_at": None, "pc_collection_public": True, "pc_announce": True,
                "pc_settings_revision": 3, "pc_shards": 100, "pc_portrait_source": "game",
                "pc_game_portrait_descriptor": None, "pc_game_portrait_hash": None,
                "pc_game_portrait_locked_until": None}
    today = {"paid_today": paid_today, "daily_pack": None, "next_reset": NOW, "prints": 10}
    return Scripted({"pc_settings_revision, pc_shards": [[settings]], "AS paid_today": [[today]],
                     "status = 'unopened'": [[]], "FROM pc_pool_snapshots": [[]],
                     "FROM pc_daily_claims": [[]]})


def test_pc_me_reports_the_exemption_for_that_account_only(monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "secret")

    async def actor(request, steam_id, sig, canon, db):
        return SimpleNamespace(id=PID)
    monkeypatch.setattr(main, "_pc_verified_actor", actor)
    me = _run(main.pc_me(request=_Req(), steam_id=STEAM, sig="x", db=_me_db()))
    assert me["paid_cap_exempt"] is True
    assert me["paid_today"] == 5 and me["prices"]["paid_packs_per_day"] == 5, \
        "the count and the cap are still reported: the client shows them, it just does not refuse on them"
    other = _run(main.pc_me(request=_Req(), steam_id=OTHER, sig="x", db=_me_db()))
    assert other["paid_cap_exempt"] is False


# ── the pack history pager ─────────────────────────────────────────────

def _pack_row(i):
    at = NOW - timedelta(minutes=i)
    return {"id": UUID(int=i + 1), "status": "done", "source": "bought", "mode": None, "kind": None,
            "pay": "gold", "price": 100, "reject_reason": None, "created_at": at, "opened_at": at}


def _hist_db(rows, total):
    # the page query carries the total on every row (one snapshot, v4 §7); the bare count answers only an empty page
    return Scripted({"(opened_at, id) < (SELECT": [[{**r, "total": total} for r in rows]],
                     "SELECT COUNT(*) FROM pc_packs WHERE": [[{"count": total}]]})


def _history_fakes(monkeypatch):
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", "secret")
    canons = []

    async def actor(request, steam_id, sig, canon, db):
        canons.append(canon)
        return SimpleNamespace(id=PID)
    monkeypatch.setattr(main, "_pc_verified_actor", actor)

    async def ctx(db, locale):
        return _ctx()
    monkeypatch.setattr(main, "_pc_face_ctx", ctx)

    async def prints(db, pack_id, ctx=None):
        return [{"print_id": "p-" + str(pack_id)[-1]}]
    monkeypatch.setattr(main, "_pc_prints_of_pack", prints)
    scheduled = []
    monkeypatch.setattr(main, "_pc_schedule_prerender", lambda ids, locale: scheduled.append(list(ids)))
    return canons, scheduled


def test_the_history_pages_newest_first_on_a_keyset_cursor(monkeypatch):
    canons, scheduled = _history_fakes(monkeypatch)
    rows = [_pack_row(i) for i in range(3)]   # limit 2 + 1: a further page exists
    db = _hist_db(rows, 7)
    out = _run(main.pc_packs_history(request=_Req(), steam_id=STEAM, sig="x", before=None, limit=2, db=db))
    assert canons == [f"pcread:{STEAM}:packs:-"]
    assert [p["pack_id"] for p in out["packs"]] == [str(rows[0]["id"]), str(rows[1]["id"])]
    assert out["total"] == 7 and out["locale"] == "en"
    assert db.count("SELECT COUNT(*) FROM pc_packs WHERE") == 0, "rows and total come from ONE statement's snapshot (v4 §7)"
    assert out["next_before"] == str(rows[1]["id"]), "the cursor is the LAST pack shown, never the peeked one"
    assert out["packs"][0]["prints"] == [{"print_id": "p-1"}] and out["packs"][0]["status"] == "done"
    assert scheduled == [], "the history never pre-renders fifty faces the player may not page to"
    sql, params = next((s, p) for s, p in db.log if "(opened_at, id) < (SELECT" in s)
    assert params == {"pid": str(PID), "before": None, "lim": 3}
    assert ("(SELECT COUNT(*) FROM pc_packs t WHERE t.player_id = CAST(:pid AS uuid) AND t.status = 'done') AS total"
            in sql)
    assert "ORDER BY opened_at DESC, id DESC" in sql and "status = 'done'" in sql
    assert "player_id = CAST(:pid AS uuid)" in sql and "c.player_id = CAST(:pid AS uuid)" in sql, \
        "the cursor pack is looked up under the caller's own id, so a foreign pack_id pages nothing"
    assert "CAST(:before AS uuid) IS NULL" in sql

    # the last page: exactly `limit` rows back means no cursor beyond it
    db = _hist_db(rows[:2], 7)
    out = _run(main.pc_packs_history(request=_Req(), steam_id=STEAM, sig="x", before=str(rows[1]["id"]),
                                     limit=2, db=db))
    assert out["next_before"] is None
    assert canons[-1] == f"pcread:{STEAM}:packs:{rows[1]['id']}", "the cursor is inside the signed string"
    _, params = next((s, p) for s, p in db.log if "(opened_at, id) < (SELECT" in s)
    assert params["before"] == str(rows[1]["id"])

    # an empty history is an empty page, not an error; it has no row to carry the total, so that is counted
    empty = _hist_db([], 0)
    out = _run(main.pc_packs_history(request=_Req(), steam_id=STEAM, sig="x", before=None, limit=10, db=empty))
    assert out == {"packs": [], "total": 0, "locale": "en", "next_before": None}
    assert empty.count("SELECT COUNT(*) FROM pc_packs WHERE") == 1


def test_the_card_preview_draws_the_minted_projection(monkeypatch):
    """The /card preview shows the tier in the rank slot and the equipped shop
    title as the subtitle — the same projection a minted face gets (r3)."""
    monkeypatch.setattr(main, "_require_internal_key", lambda key: None)
    monkeypatch.setattr(main, "_pc_require_renderer", lambda: None)

    async def prime(ids, deadline=None):
        return None
    monkeypatch.setattr(main, "_pc_steam_prime", prime)

    async def ctx(db, locale):
        return _ctx()
    monkeypatch.setattr(main, "_pc_face_ctx", ctx)

    async def no_bytes(db, h):
        return None
    monkeypatch.setattr(main, "_pc_portrait_bytes", no_bytes)
    specs = []

    class _Cache:
        async def get_or_render(self, key, render):
            specs.append(render.args[0])
            return b"\x89PNG\r\n\x1a\n" + b"rest"
    monkeypatch.setattr(main, "_pc_face_cache", _Cache())
    sub = {"display_name": "Sid", "subject_deleted": False, "subject_banned": False, "subject_opted_out": False,
           "portrait_source": "game", "portrait_hash": None, "steam_portrait_hash": None}

    def preview(title):
        member = {"pool_rank": 3, "rarity": "rare", "rating": 1980.0, "board_rank": 5, "series_wins": 4,
                  "series_losses": 1, "top_card": None, "title": title}
        db = Scripted({"SELECT p.display_name": [[sub]], "FROM pc_pool_members m": [[member]]})
        _run(main.internal_pc_face_preview(player_ref=str(PID), locale="en", x_internal_key="k", db=db))
        return specs[-1]
    spec = preview("Champion")
    assert spec["title"] == _tier(1980.0) and spec["subtitle"] == "Champion" and spec["rating"] == 1980
    assert spec["name"] == "Sid" and spec["band"] == "rare" and spec["foil"] is False
    assert preview(_tier(1980.0))["subtitle"] is None   # a stored value that names a tier is the rank, never a subtitle
    assert preview(None)["subtitle"] is None and preview("  ")["subtitle"] is None
    assert preview("Champion")["title"] != "Champion"   # the shop title never takes the rank slot


def test_the_history_refuses_a_malformed_cursor_after_the_signature(monkeypatch):
    canons, _ = _history_fakes(monkeypatch)
    with pytest.raises(HTTPException) as ex:
        _run(main.pc_packs_history(request=_Req(), steam_id=STEAM, sig="x", before="x" * 36, limit=2,
                                   db=Scripted({})))
    assert ex.value.status_code == 422
    assert canons == [f"pcread:{STEAM}:packs:{'x' * 36}"], "signature first: an unsigned request never reaches the parse"


def test_the_pack_answer_only_prerenders_when_asked(monkeypatch):
    scheduled = []
    monkeypatch.setattr(main, "_pc_schedule_prerender", lambda ids, locale: scheduled.append(list(ids)))

    async def prints(db, pack_id, ctx=None):
        return [{"print_id": "p1"}]
    monkeypatch.setattr(main, "_pc_prints_of_pack", prints)
    row = _pack_row(0)
    _run(main._pc_pack_answer(None, row, _ctx()))
    assert scheduled == [], "only the minting request asks for a pre-render (v4.13 §9)"
    _run(main._pc_pack_answer(None, row, _ctx(), prerender=True))
    assert scheduled == [["p1"]]
    _run(main._pc_pack_answer(None, row, _ctx(), prerender=False))
    assert scheduled == [["p1"]]
    assert "prints" not in _run(main._pc_pack_answer(None, dict(row, status="unopened"), _ctx(), prerender=True))


# ── v4.1 (r4): the i18n migrations recompute from the sync tool and match the bundled catalogues ──

def _pg_e(lit):
    """The text of a PostgreSQL E'...' literal as the generator writes them."""
    assert lit.startswith("E'") and lit.endswith("'"), lit[:20]
    s, out, i = lit[2:-1], [], 0
    while i < len(s):
        c = s[i]
        if c == "'" and s[i + 1:i + 2] == "'":
            out.append("'")
            i += 2
        elif c == "\\":
            n = s[i + 1]
            if n == "n":
                out.append("\n")
                i += 2
            elif n == "x":
                out.append(chr(int(s[i + 2:i + 4], 16)))
                i += 4
            elif n == "\\":
                out.append("\\")
                i += 2
            else:
                raise AssertionError("unexpected escape " + s[i:i + 2])
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _cs(lit):
    """The text of a C# string literal body as the catalogue writes them."""
    out, i = [], 0
    while i < len(lit):
        c = lit[i]
        if c == "\\":
            n = lit[i + 1]
            if n == "n":
                out.append("\n")
                i += 2
            elif n == '"':
                out.append('"')
                i += 2
            elif n == "\\":
                out.append("\\")
                i += 2
            elif n == "u":
                out.append(chr(int(lit[i + 2:i + 6], 16)))
                i += 6
            else:
                raise AssertionError("unexpected escape " + lit[i:i + 2])
        else:
            out.append(c)
            i += 1
    return "".join(out)


def test_the_sept12_i18n_migrations_recompute_from_the_sync_tool_and_match_the_bundled_catalogues():
    import json
    import re
    repo = os.path.abspath(os.path.join(os.path.dirname(main.__file__), "..", ".."))
    sys.path.insert(0, os.path.join(repo, "tools"))
    import i18n_sync_keys as sk
    with io.open(os.path.join(repo, "tools", "i18n_source.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    recs = {r["key_id"]: r for r in sk.build_client_keys(data)}
    with io.open(os.path.join(repo, "backend", "sql", "312_i18n_keys_sept12.sql"), encoding="utf-8") as fh:
        keys_sql = fh.read()
    values = keys_sql[keys_sql.index("FROM (VALUES"):keys_sql.index(") AS v(key_id")]
    row_re = re.compile(r"\('(?P<id>[0-9a-f]{16})', 'client', (?P<msg>\$k312\$.*?\$k312\$|E'(?:[^'\\]|\\.|'')*'), "
                        r"'(?P<hash>[0-9a-f]{40})', (?P<sens>TRUE|FALSE), (?P<ctx>E'(?:[^'\\]|\\.|'')*'|NULL)\)", re.S)
    rows = list(row_re.finditer(values))
    expected = int(re.search(r"v_expected INT := (\d+);", keys_sql).group(1))
    assert len(rows) == expected == 25 and len({m.group("id") for m in rows}) == 25
    english = {}
    for m in rows:
        rec = recs[m.group("id")]   # every key is a live client string the extractor knows
        msg = m.group("msg")
        msg = msg[6:-6] if msg.startswith("$k312$") else _pg_e(msg)
        assert msg == rec["msgctxt"], m.group("id")
        assert m.group("hash") == rec["source_hash"] and (m.group("sens") == "TRUE") == rec["sensitive"], m.group("id")
        ctx = None if m.group("ctx") == "NULL" else _pg_e(m.group("ctx"))
        assert ctx == rec.get("context"), m.group("id")
        english[m.group("id")] = msg
    with io.open(os.path.join(repo, "plugin", "I18nCatalogues.cs"), encoding="utf-8") as fh:
        cs = fh.read()
    catalogue = {}
    entry_re = re.compile(r'^\s+\["((?:[^"\\]|\\.)*)"\] = "((?:[^"\\]|\\.)*)",$', re.M)
    for block in cs.split("private static readonly Dictionary<string, string> ")[1:]:
        lang = block[:2].lower()
        body = block[:block.index("\n        };")]
        entries = entry_re.findall(body)
        assert len(entries) == len({k for k, _ in entries}), lang   # a duplicate key throws at the mod's static init
        catalogue[lang] = {_cs(k): _cs(v) for k, v in entries}
    with io.open(os.path.join(repo, "backend", "sql", "313_seed_machine_translations_sept12.sql"), encoding="utf-8") as fh:
        seeds_sql = fh.read()
    seed_re = re.compile(r"\('([0-9a-f]{16})', '(es|ru|uk|sv)', '([0-9a-f]{40})', (E'(?:[^'\\]|\\.|'')*')\)")
    seeds = seed_re.findall(seeds_sql[seeds_sql.index("INSERT INTO _seed313"):seeds_sql.index("INSERT INTO i18n_proposals")])
    assert len(seeds) == 100 and len({(k, lang) for k, lang, _h, _t in seeds}) == 100
    assert "of 100 seed pairs" in seeds_sql and "(25 keys x es/ru/uk/sv)" in seeds_sql
    for key_id, lang, source_hash, target in seeds:
        assert key_id in english and source_hash == recs[key_id]["source_hash"], key_id
        assert catalogue[lang][english[key_id]] == _pg_e(target), (key_id, lang)   # the seed IS the bundled text
    # the plain and the contextual DISCARDED keys carry the same translation in every language
    plain = [k for k, e in english.items() if e == "DISCARDED"]
    ctxd = [k for k, e in english.items() if e == "DISCARDED\u0004pack open"]
    assert len(plain) == 1 and len(ctxd) == 1
    for lang in ("es", "ru", "uk", "sv"):
        assert catalogue[lang]["DISCARDED"] == catalogue[lang]["DISCARDED\u0004pack open"]


def test_the_extracted_source_registry_matches_the_client_sources_byte_for_byte():
    """r6 tests (2026-09-13): the generated registry (tools/i18n_source.json)
    and the compiled key list (plugin/I18nSourceKeys.g.cs) are what the
    extractor produces from the plugin sources NOW -- a live C# sentence that
    drifts from the seeds fails here, not in a player's language."""
    import importlib.util
    import json
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("i18n_extract_under_test", str(root / "tools" / "i18n_extract.py"))
    ex = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ex)
    found, sites = ex.extract()
    fresh = ex.build_registry(found, sites)
    on_disk = json.loads((root / "tools" / "i18n_source.json").read_text(encoding="utf-8"))
    assert fresh == on_disk
    keys = (root / "plugin" / "I18nSourceKeys.g.cs").read_text(encoding="utf-8")
    entries = sorted(found.keys())
    listed = re.findall(r'\n            "((?:[^"\\]|\\.)*)",', keys)
    assert len(listed) == len(entries)
    assert len(set(listed)) == len(listed)   # the generated file lists each key once (r8: a dict's keys compared with themselves)
    for s in entries:   # every one (r7: sampling the ends let a middle substitution through)
        assert '"' + ex.cs_escape(s) + '",' in keys
