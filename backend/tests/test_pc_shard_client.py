"""Client structure gates for board rows 24 (the Settings full card) and 25
(the batch shard), each run on the real sources and, with its mutation and
control, on edited COPIES (#391): the mutation must turn the gate red and the
control (an edit at the same site that changes no behaviour) must leave it
green. Nothing here needs a database or the game.

Row 24 -- the Settings slot shows the WHOLE card other players see:
  G1  the client asks the server's full-card route, signed as the server
      verifies it, and decodes the answer as the CARD variant (750x1050), the
      size the server draws it at;
  G2  while a new look is on its way the slot shows the live picture with the
      pending line, and the card is fetched again once the stored portrait
      (the key) changes -- never while the look is pending.
Row 25 -- the batch shard:
  G3  the client signs the batch exactly as the server verifies it, on the
      server's path, and its cap is the server's cap;
  G4  the confirmation's total reads the server's rarity table;
  G5  the pack key is the pack id; a selection's nonce is kept for the exact
      set until an answer arrives (a lost answer asked again is a replay);
  G6  every shard control is a ClickGuard'ed button, and a tile click in
      Select mode is claimed before it picks;
  G7  the last copy is a confirmation, never a block: the second click sends;
  G8  the toast names the total the server credited, from its answer.
Row 24, round 2 of the review:
  G10 a failed refresh leaves the held card stale (only a card drawn, or the
      pool's 404, sets the fetch time), so the next try comes at the retry
      time thirty seconds out, and the held card is captioned as not loaded
      while its last refresh has failed (finding 3);
  G11 the single-flight latch cannot outlive its coroutine: a fetch with no
      answer 25 s after it was sent (past the 20 s transport timeout) is
      given up before the tick's in-flight check, and an answer to a fetch
      given up commits nothing (its serial is not the latest) -- the host
      that runs the coroutine can be destroyed and respawned (finding 4).
Both rows:
  G9  every new string is in all four catalogues with its placeholders, and
      in the extractor's registry.
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "api"))

import player_cards as _pc  # noqa: E402

PLUGIN = ROOT / "plugin"
FILES = {
    "ui": PLUGIN / "PlayerCardsUI.cs",
    "api": PLUGIN / "ApiClient.cs",
    "faces": PLUGIN / "PlayerCardFaces.cs",
    "render": PLUGIN / "PortraitRender.cs",
    "native": PLUGIN / "NativeUI.cs",
    "cats": PLUGIN / "I18nCatalogues.cs",
    "reg": ROOT / "tools" / "i18n_source.json",
    "main": ROOT / "backend" / "api" / "main.py",
}

_CACHE = {}


def _sources():
    if not _CACHE:
        for k, p in FILES.items():
            # universal newlines: the working tree is CRLF, the blobs LF
            _CACHE[k] = p.read_text(encoding="utf-8")
    return dict(_CACHE)


_MEMBER = re.compile(r"\n        (?:///|\[|(?:private|internal|public|protected)\s)")


def _member(src, signature):
    """The text of the member that starts at `signature`, up to the start of
    the next member at the class's indentation (a doc comment, an attribute or
    a declaration). The signature must occur exactly once."""
    n = src.count(signature)
    assert n == 1, "%r occurs %d times" % (signature, n)
    i = src.index(signature)
    m = _MEMBER.search(src, i + len(signature))
    return src[i:m.start() if m else len(src)]


def _at(text, needle, what):
    """Where `needle` starts in `text`; an AssertionError naming `what` when it
    is absent (a gate is red by assertion, never by a ValueError)."""
    assert needle in text, what
    return text.index(needle)


def _py_function(src, name):
    i = src.index("\nasync def %s(" % name) if ("\nasync def %s(" % name) in src else src.index("\ndef %s(" % name)
    m = re.compile(r"\n(?:@|def |async def |class |[A-Za-z_])").search(src, i + 1)
    return src[i:m.start() if m else len(src)]


# ---------------------------------------------------------------- the gates

def gate_g1_the_preview_requests_the_card_variant(s):
    api = _member(s["api"], "public static void PcFacePreview(")
    assert 'PcUrl("face/preview", steamId, $"pcread:{steamId}:face:preview", null)' in api, (
        "the Settings card no longer asks the full-card route, signed pcread:<steam>:face:preview")
    assert _pc.canon_read("S", "face", "preview") == "pcread:S:face:preview", "the server's read canon moved"
    assert '@app.get("/api/v1/pc/face/preview"' in s["main"], "the server route moved"
    route = _py_function(s["main"], "pc_face_preview")
    assert '_pc.canon_read(steam_id, "face", "preview")' in route
    helper = _py_function(s["main"], "_pc_preview_face")
    assert '_functools.partial(_pcf.render_face, spec, labels, pbytes, "card")' in helper, (
        "the server no longer draws the preview at the CARD size")
    tick = _member(s["ui"], "private static void SettingsCardTick(")
    assert "ApiClient.PcFacePreview(id, " in tick, "the Settings tick no longer fetches the full card"
    assert 'PlayerCardFaces.DecodeOwned(data, "card", true)' in tick, (
        "the Settings card is no longer decoded as the CARD variant")
    faces = s["faces"]
    assert "internal const int CARD_W = 750, CARD_H = 1050, TILE_W = 375, TILE_H = 525;" in faces
    ihdr = _member(faces, "internal static bool IhdrOk(")
    assert 'int ew = size == "card" ? CARD_W : TILE_W, eh = size == "card" ? CARD_H : TILE_H;' in ihdr
    owned = _member(faces, "internal static Texture2D DecodeOwned(")
    assert "if (!IhdrOk(data, size, out w, out h))" in owned, "the owned decode no longer checks the header size"


def gate_g2_pending_shows_the_live_picture_and_the_key_refetches(s):
    view = _member(s["ui"], "private static void SettingsCardView(")
    pend = _at(view, "if (PortraitRender.LookPending)", "the slot no longer asks whether a new look is pending")
    held = _at(view, "settingsCardKey == SettingsCardWant(me)", "the held card is no longer checked against the key")
    assert pend < held, "the held card is shown before the pending check"
    block = view[pend:held]
    assert "show = live ?? held;" in block and \
        'I18n.Tr("Saving your new picture - your card updates here once it has been sent.")' in block, (
            "a pending look no longer shows the live picture with the pending line")
    render = s["render"]
    look = _member(render, "internal static bool LookPending")
    assert "_refreshAt >= 0f || UploadInFlight || (Rendering && _productUploads)" in look, (
        "LookPending lost a term: a debouncing change, an upload or an uploading render")
    run = _member(render, "private static IEnumerator ProductRun(")
    assert run.count("_productUploads = upload;") == 1 and run.count("_productUploads = false;") == 1
    want = _member(s["ui"], "private static string SettingsCardWant(")
    for part in ("uiEpoch", "me.portrait_hash", "I18n.Locale"):
        assert part in want, "the card's key no longer carries " + part
    tick = _member(s["ui"], "private static void SettingsCardTick(")
    assert "if (PortraitRender.LookPending) return;" in tick, "the card is fetched while a new look is pending"
    assert "bool stale = want != settingsCardKey || Now - settingsCardAt > 300f;" in tick
    upload = _member(render, "private static void Upload(")
    assert "me.portrait_hash = h;" in upload, "an upload's answer no longer writes the stored hash the key reads"


def gate_g3_the_batch_is_signed_and_capped_as_the_server_verifies(s):
    api = _member(s["api"], "public static void PcDiscardBatch(")
    assert 'string joined = string.Join(",", printIds);' in api, (
        "the client's batch signature or path moved: the ids are no longer comma-joined as the server's canon is")
    assert 'PcUrl("prints/discard-batch", steamId, $"pcdiscardn:{steamId}:{key}:{joined}", null)' in api, (
        "the client's batch signature or path moved")
    assert _pc.canon_discard_batch("S", "K", ["a", "b"]) == "pcdiscardn:S:K:a,b", "the server's batch canon moved"
    assert '@app.post("/api/v1/pc/prints/discard-batch"' in s["main"]
    assert "_pc.canon_discard_batch(steam_id, key, ids)" in _py_function(s["main"], "pc_discard_batch")
    m = re.search(r"public const int PC_DISCARD_BATCH_CAP = (\d+);", s["api"])
    assert m and int(m.group(1)) == _pc.PC_DISCARD_BATCH_CAP, "the client's cap is not the server's"
    assert "printIds.Count > PC_DISCARD_BATCH_CAP" in api, "the client no longer refuses a batch over the cap unsent"


def gate_g4_the_confirmation_total_reads_the_server_table(s):
    fn = _member(s["ui"], "private static int ShardValue(")
    table = dict(re.findall(r'case "(\w+)": return (\d+);', fn))
    default = re.search(r"default: return (\d+);", fn)
    table = {k: int(v) for k, v in table.items()}
    assert default and "common" not in table
    table["common"] = int(default.group(1))
    assert table == _pc.PC_ECONOMY["shards"], "the client's shard table %r is not PC_ECONOMY's %r" % (
        table, _pc.PC_ECONOMY["shards"])


def gate_g5_the_keys(s):
    ui = s["ui"]
    pack = _member(ui, "private static void OnShardPackClick(")
    assert pack.rstrip().endswith("SendShard(id, shown.pack_id, ids, shown.pack_id);\n        }"), (
        "a Shard pack is no longer keyed by its pack id")
    sel = _member(ui, "private static void OnShardSelectedClick(")
    assert "if (shardKeyFor != set || string.IsNullOrEmpty(shardKey)) { shardKey = NewNonce(); shardKeyFor = set; }" in sel, (
        "a selection's nonce is no longer kept for its exact set")
    assert "SendShard(id, shardKey, ids, null);" in sel, "a selection is no longer sent under its kept nonce"
    assert sel.count("NewNonce()") == 1, "a selection draws a fresh nonce on every click"
    done = _member(ui, "private static void FinishShard(")
    assert "if (packId == null) { shardKey = null; shardKeyFor = null; }" in done, (
        "a selection's nonce is not retired when its answer arrives")
    fail = _member(ui, "private static void FailShard(")
    # the key is dropped only when the server says it was used with other cards
    assert fail.count("shardKey = null;") == 1, "a refusal other than key_reused drops the selection's nonce"
    assert (_at(fail, 'case "key_reused":', "no key_reused case") < _at(fail, "shardKey = null;", "the key is never dropped")
            < _at(fail, 'case "too_many":', "no too_many case")), "the key is dropped outside the key_reused case"


def gate_g6_click_guards(s):
    native = _member(s["native"], "public static GameObject CreateButton(")
    assert native.count("ClickGuard.Claim(go)") == 2, "CreateButton no longer guards both click paths"
    ui = s["ui"]
    for name, handler in (("PcShardPack", "OnShardPackClick"), ("PcBSelect", "OnSelectClick"),
                          ("PcBShardSel", "OnShardSelectedClick")):
        m = re.search(r'UIFactory\.CreateButton\("%s", [^;]*?, %s, sizeDelta' % (name, handler), ui)
        assert m, "%s is not a CreateButton wired to %s" % (name, handler)
    click = _member(ui, "private static void OnTileClick(")
    claim = _at(click, "if (!ClickGuard.Claim(t.root)) return;", "a tile click is no longer claimed")
    pick = _at(click, "ToggleSelected(t.print)", "a Select-mode tile click no longer picks the card")
    assert claim < pick, "a Select-mode pick runs before the click is claimed"


def gate_g7_the_last_copy_is_a_confirmation(s):
    ui = s["ui"]
    for sig in ("private static void OnShardPackClick(", "private static void OnShardSelectedClick("):
        fn = _member(ui, sig)
        arm = _at(fn, "if (!ShardConfirmed(", sig + ": no first-click question")
        note = _at(fn, "OnlyCopyNote(batch, col)", sig + ": the question no longer names the only copies")
        send = _at(fn, "SendShard(", sig + ": the second click no longer sends")
        close = note + _at(fn[note:], "return;", sig + ": the question does not end the first click")
        assert arm < note < close < send, sig + ": the only-copy note is not part of the first click's question"
        assert fn.count("OnlyCopyNote(") == 1, sig + ": the only-copy note gates something besides the question"
    note = _member(ui, "private static string OnlyCopyNote(")
    assert 'I18n.TrF("this is your only copy of {0}", list)' in note, "the only-copy line is no longer the question's"


def gate_g8_the_toast_names_the_credited_total(s):
    done = _member(s["ui"], "private static void FinishShard(")
    assert 'int total = ApiClient.PcInt(ApiClient.PcTopLevel(resp, "shards_gained"));' in done, (
        "the toast no longer reads the credited total from the server's answer")
    assert 'string msg = I18n.TrF("Sharded {0} cards for {1} shards", n, total);' in done, (
        "the toast no longer names the credited total")
    assert "CompetitiveUI.ShowNotification(msg, C_OK, 4f);" in done, "the credited total is no longer toasted"
    assert "ShardTotal(" not in done, "the toast reports the client's estimate, not the server's credit"


def gate_g10_a_failed_refresh_retries_in_thirty_seconds_and_says_so(s):
    tick = _member(s["ui"], "private static void SettingsCardTick(")
    assert "bool stale = want != settingsCardKey || Now - settingsCardAt > 300f;" in tick
    assert "if (!stale || Now < settingsCardRetryAt) return;" in tick
    drawn = _at(tick, "settingsCardKey = want; settingsCardState = SC_CARD; settingsCardRetryAt = 0f;",
                "the tick no longer records a drawn card")
    refused = _at(tick, "if (ok || code != 404)", "the tick no longer tells a refusal from the pool's 404")
    missing = _at(tick, "settingsCardKey = want; settingsCardState = SC_NOT_IN_POOL;", "the pool's 404 moved")
    stamps = [m.start() for m in re.finditer(re.escape("settingsCardAt = Now;"), tick)]
    assert len(stamps) == 2 and drawn < stamps[0] < refused < missing < stamps[1], (
        "a failed refresh marks the card fresh: only a card drawn or the pool's 404 may set settingsCardAt")
    branch = tick[refused:missing]
    assert "settingsCardState = SC_UNAVAILABLE;" in branch and "settingsCardRetryAt = Now + 30f;" in branch, (
        "a failed refresh no longer sets the unavailable state and the thirty-second retry")
    view = _member(s["ui"], "private static void SettingsCardView(")
    held = _at(view, "if (held != null && me != null && settingsCardKey == SettingsCardWant(me))",
               "the held card is no longer checked against the key")
    current = _at(view, 'I18n.Tr("Your card as other players see it.")', "the current-card caption moved")
    block = view[held:current]
    assert "if (settingsCardState == SC_UNAVAILABLE)" in block and \
        'I18n.Tr("Your card could not be loaded right now - it is tried again shortly.")' in block, (
            "the held card keeps a current-card caption after its refresh failed")


def gate_g11_a_fetch_that_never_answers_does_not_hold_the_latch(s):
    ui = s["ui"]
    assert "private static float settingsCardSentAt;" in ui and "private static int settingsCardSerial;" in ui
    tick = _member(ui, "private static void SettingsCardTick(")
    give_up = _at(tick, "if (settingsCardInFlight && Now - settingsCardSentAt > 25f)",
                  "a fetch that never answers holds the latch: nothing gives it up")
    guard = _at(tick, "|| settingsCardInFlight ||", "the tick no longer runs one fetch at a time")
    assert give_up < guard, "a fetch that never answers holds the latch: it is given up only after the in-flight return"
    block = tick[give_up:guard]
    assert "settingsCardInFlight = false;" in block and "settingsCardSerial++;" in block, (
        "a fetch given up does not release the latch and retire its serial")
    send = _at(tick, "settingsCardInFlight = true;", "the tick no longer sets the latch when it sends")
    call = _at(tick, "ApiClient.PcFacePreview(id, ", "the tick no longer fetches the card")
    stamp = tick[send:call]
    assert "settingsCardSentAt = Now;" in stamp and "serial = ++settingsCardSerial" in stamp, (
        "a sent fetch is not stamped with its time and serial")
    cb = tick[call:]
    epoch = _at(cb, "if (ep != uiEpoch) return;", "the identity check moved")
    drop = _at(cb, "if (serial != settingsCardSerial)", "an answer to a fetch given up still commits")
    first_write = _at(cb, "settingsCardInFlight = false;", "the answer no longer releases the latch")
    assert epoch < drop < first_write, "an answer to a fetch given up still commits"


NEW_KEYS = [
    "Saving your new picture - your card updates here once it has been sent.",
    "Other players still see this card: your new picture was not sent (the note below says why).",
    "Your card as other players see it.",
    "You are not in the card pool yet, so there is no card to show - this is your picture.",
    "Your card could not be loaded right now - it is tried again shortly.",
    "Loading your card...",
    "Shard pack (+{0})",
    "Sure? +{0} shards",
    "sharding...",
    "Select",
    "Stop selecting",
    "Shard selected ({0})",
    "Selected",
    "Click cards to select them for shards",
    "Click Shard pack again to shard {0} cards for {1} shards",
    "Click Shard selected again to shard {0} cards for {1} shards",
    "this is your only copy of {0}",
    "Sharded {0} cards for {1} shards",
    "You can shard up to {0} cards at once",
    "Loading your binder - try again in a moment",
    "One of those cards is no longer in your collection - nothing was sharded; your binder has been refreshed",
    "That shard was already done with other cards - your binder has been refreshed",
    "Shard pack is not available on this server yet - discard one card at a time for now",
    "Select cards first - click the cards you want to shard",
    "Discarding a card gives shards by its rarity: Common 5, Uncommon 15, Rare 40, Epic 150, Legendary 600. "
    "Shards buy packs. Discard takes one card and the Dupes button every other copy of that exact card; "
    "Shard pack (on a pack you opened) and Select (in the binder) shard up to 40 cards in one go.",
]

_ENTRY = re.compile(r'^\s+\["((?:[^"\\]|\\.)*)"\] = "((?:[^"\\]|\\.)*)",$', re.M)


def _unescape(lit):
    out, i = [], 0
    while i < len(lit):
        c = lit[i]
        if c == "\\":
            n = lit[i + 1]
            if n == "u":
                out.append(chr(int(lit[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append({"n": "\n", '"': '"', "\\": "\\"}[n])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def gate_g9_every_new_string_is_in_every_catalogue(s):
    cats = {}
    for block in s["cats"].split("private static readonly Dictionary<string, string> ")[1:]:
        lang = block[:2]
        body = block[:block.index("\n        };")]
        rows = [(_unescape(k), _unescape(v)) for k, v in _ENTRY.findall(body)]
        keys = [k for k, _ in rows]
        assert len(keys) == len(set(keys)), lang + " holds a duplicate key (the mod's static init would throw)"
        cats[lang] = dict(rows)
    assert sorted(cats) == ["ES", "RU", "SV", "UK"], sorted(cats)
    reg = set(json.loads(s["reg"])["strings"])
    for key in NEW_KEYS:
        assert key in s["ui"], "the key is no longer a client string: " + key[:60]
        assert key in reg, "the extractor registry lacks " + key[:60]
        want = sorted(re.findall(r"\{\d+\}", key))
        for lang, cat in cats.items():
            assert key in cat, "%s lacks %r" % (lang, key[:60])
            assert cat[key] != key, "%s leaves %r in English" % (lang, key[:60])
            assert sorted(re.findall(r"\{\d+\}", cat[key])) == want, "%s changes the placeholders of %r" % (
                lang, key[:60])


GATES = [gate_g1_the_preview_requests_the_card_variant,
         gate_g2_pending_shows_the_live_picture_and_the_key_refetches,
         gate_g3_the_batch_is_signed_and_capped_as_the_server_verifies,
         gate_g4_the_confirmation_total_reads_the_server_table,
         gate_g5_the_keys,
         gate_g6_click_guards,
         gate_g7_the_last_copy_is_a_confirmation,
         gate_g8_the_toast_names_the_credited_total,
         gate_g9_every_new_string_is_in_every_catalogue,
         gate_g10_a_failed_refresh_retries_in_thirty_seconds_and_says_so,
         gate_g11_a_fetch_that_never_answers_does_not_hold_the_latch]


@pytest.mark.parametrize("gate", GATES, ids=[g.__name__ for g in GATES])
def test_the_gate_holds_on_the_real_sources(gate):
    gate(_sources())


# (id, gate, source key, search text, mutant replacement, control replacement,
#  the named assertion the mutant must turn red). Every control is a real
# edit at the same site -- a comment, a space -- that changes no behaviour.
MUTATIONS = [
    ("M24a", gate_g1_the_preview_requests_the_card_variant, "ui",
     'PlayerCardFaces.DecodeOwned(data, "card", true)',
     'PlayerCardFaces.DecodeOwned(data, "tile", true)',
     'PlayerCardFaces.DecodeOwned(data, "card", true) ',
     "the Settings card is no longer decoded as the CARD variant"),
    ("M24b", gate_g1_the_preview_requests_the_card_variant, "api",
     'PcUrl("face/preview", steamId, $"pcread:{steamId}:face:preview", null)',
     'PcUrl("face/tile", steamId, $"pcread:{steamId}:face:preview", null)',
     'PcUrl("face/preview", steamId, $"pcread:{steamId}:face:preview", null) ',
     "the Settings card no longer asks the full-card route"),
    ("M24c", gate_g1_the_preview_requests_the_card_variant, "main",
     '_functools.partial(_pcf.render_face, spec, labels, pbytes, "card")',
     '_functools.partial(_pcf.render_face, spec, labels, pbytes, "tile")',
     '_functools.partial(_pcf.render_face, spec, labels, pbytes, "card") ',
     "the server no longer draws the preview at the CARD size"),
    ("M24d", gate_g1_the_preview_requests_the_card_variant, "ui",
     "ApiClient.PcFacePreview(id, ",
     "ApiClient.PcFaceNotAsked(id, ",
     "ApiClient.PcFacePreview(id, /* the full card */ ",
     "the Settings tick no longer fetches the full card"),
    ("M24e", gate_g2_pending_shows_the_live_picture_and_the_key_refetches, "render",
     "_refreshAt >= 0f || UploadInFlight || (Rendering && _productUploads)",
     "_refreshAt >= 0f || (Rendering && _productUploads)",
     "_refreshAt >= 0f || UploadInFlight || (Rendering && _productUploads) ",
     "LookPending lost a term"),
    ("M24f", gate_g2_pending_shows_the_live_picture_and_the_key_refetches, "ui",
     'return uiEpoch + "|" + (me != null ? me.portrait_hash ?? "" : "") + "|"',
     'return uiEpoch + "|" + "" + "|"',
     'return uiEpoch + "|" + (me != null ? me.portrait_hash ?? "" : "") + "|" ',
     "the card's key no longer carries me.portrait_hash"),
    ("M24g", gate_g2_pending_shows_the_live_picture_and_the_key_refetches, "ui",
     "            if (PortraitRender.LookPending) return;\n",
     "",
     "            if (PortraitRender.LookPending) return;   // a pending look is never fetched\n",
     "the card is fetched while a new look is pending"),
    ("M24h", gate_g9_every_new_string_is_in_every_catalogue, "cats",
     '            ["Your card as other players see it."] = "Tu carta tal como la ven los dem\\u00e1s jugadores.",\n',
     '            ["Your card as other players see it."] = "Your card as other players see it.",\n',
     '            ["Your card as other players see it."] = "Tu carta tal como la ven los  dem\\u00e1s jugadores.",\n',
     "ES leaves 'Your card as other players see it.' in English"),
    ("M25a", gate_g3_the_batch_is_signed_and_capped_as_the_server_verifies, "api",
     'string joined = string.Join(",", printIds);',
     'string joined = string.Join(";", printIds);',
     'string joined = string.Join(",", printIds); ',
     "the client's batch signature or path moved"),
    ("M25b", gate_g3_the_batch_is_signed_and_capped_as_the_server_verifies, "api",
     "public const int PC_DISCARD_BATCH_CAP = 40;",
     "public const int PC_DISCARD_BATCH_CAP = 41;",
     "public const int PC_DISCARD_BATCH_CAP = 40; ",
     "the client's cap is not the server's"),
    ("M25c", gate_g4_the_confirmation_total_reads_the_server_table, "ui",
     'case "legendary": return 600;',
     'case "legendary": return 500;',
     'case "legendary": return 600; // the top band',
     "the client's shard table"),
    ("M25d", gate_g5_the_keys, "ui",
     "if (shardKeyFor != set || string.IsNullOrEmpty(shardKey)) { shardKey = NewNonce(); shardKeyFor = set; }",
     "{ shardKey = NewNonce(); shardKeyFor = set; }",
     "if (shardKeyFor != set || string.IsNullOrEmpty(shardKey)) { shardKey = NewNonce(); shardKeyFor = set; } ",
     "a selection's nonce is no longer kept for its exact set"),
    ("M25e", gate_g5_the_keys, "ui",
     "            SendShard(id, shown.pack_id, ids, shown.pack_id);",
     "            SendShard(id, NewNonce(), ids, shown.pack_id);",
     "            // keyed by the pack id\n            SendShard(id, shown.pack_id, ids, shown.pack_id);",
     "a Shard pack is no longer keyed by its pack id"),
    ("M25f", gate_g6_click_guards, "ui",
     'UIFactory.CreateButton("PcShardPack", hdrRow.transform, "", 12f',
     'UIFactory.CreatePanel("PcShardPack", hdrRow.transform, C_DANGER); ((System.Action)(() => { }))(); var unused = ("", 12f',
     'UIFactory.CreateButton("PcShardPack", hdrRow.transform, "" /* labelled by RefreshShardPackButton */, 12f',
     "PcShardPack is not a CreateButton wired to OnShardPackClick"),
    ("M25g", gate_g6_click_guards, "ui",
     "            if (!ClickGuard.Claim(t.root)) return;\n",
     "",
     "            if (!ClickGuard.Claim(t.root)) return;   // claimed first\n",
     "a tile click is no longer claimed"),
    ("M25h", gate_g7_the_last_copy_is_a_confirmation, "ui",
     "            SendShard(id, shown.pack_id, ids, shown.pack_id);",
     "            if (OnlyCopyNote(batch, col).Length > 0) return;\n            SendShard(id, shown.pack_id, ids, shown.pack_id);",
     "            SendShard(id, shown.pack_id, ids, shown.pack_id);  ",
     "the only-copy note gates something besides the question"),
    ("M25i", gate_g8_the_toast_names_the_credited_total, "ui",
     'int total = ApiClient.PcInt(ApiClient.PcTopLevel(resp, "shards_gained"));',
     "int total = ShardTotal(sent.ConvertAll(x => (ApiClient.PcPrint)null), sent);",
     'int total = ApiClient.PcInt(ApiClient.PcTopLevel(resp, "shards_gained")); ',
     "the toast no longer reads the credited total from the server's answer"),
    ("M25j", gate_g9_every_new_string_is_in_every_catalogue, "cats",
     '            ["Shard pack (+{0})"] = "Paket till sk\\u00e4rvor (+{0})",\n',
     "",
     '            ["Shard pack (+{0})"] = "Paket till sk\\u00e4rvor  (+{0})",\n',
     "SV lacks 'Shard pack (+{0})'"),
    ("M25k", gate_g9_every_new_string_is_in_every_catalogue, "cats",
     '            ["Sure? +{0} shards"] = "S\\u00e4ker? +{0} sk\\u00e4rvor",\n',
     '            ["Sure? +{0} shards"] = "S\\u00e4ker? sk\\u00e4rvor",\n',
     '            ["Sure? +{0} shards"] = "S\\u00e4ker?  +{0} sk\\u00e4rvor",\n',
     "SV changes the placeholders of 'Sure? +{0} shards'"),
    # Round 2, finding 3. M24i is the round-1 order restored (the callback
    # stamped the fetch time before it knew the answer): the negative control.
    ("M24i", gate_g10_a_failed_refresh_retries_in_thirty_seconds_and_says_so, "ui",
     "                settingsCardInFlight = false;\n                Texture2D tex = ok ?",
     "                settingsCardInFlight = false;\n                settingsCardAt = Now;\n                Texture2D tex = ok ?",
     "                settingsCardInFlight = false;   // the answer is in\n                Texture2D tex = ok ?",
     "a failed refresh marks the card fresh"),
    ("M24j", gate_g10_a_failed_refresh_retries_in_thirty_seconds_and_says_so, "ui",
     "                if (settingsCardState == SC_UNAVAILABLE)\n                {\n",
     "                if (false)\n                {\n",
     "                if (settingsCardState == SC_UNAVAILABLE)   // its refresh failed\n                {\n",
     "the held card keeps a current-card caption after its refresh failed"),
    ("M24k", gate_g10_a_failed_refresh_retries_in_thirty_seconds_and_says_so, "ui",
     "                    settingsCardState = SC_UNAVAILABLE;\n                    settingsCardRetryAt = Now + 30f;\n",
     "                    settingsCardState = SC_UNAVAILABLE;\n                    settingsCardRetryAt = Now + 300f;\n",
     "                    settingsCardState = SC_UNAVAILABLE;\n                    settingsCardRetryAt = Now + 30f;   // thirty seconds out\n",
     "a failed refresh no longer sets the unavailable state and the thirty-second retry"),
    # Round 2, finding 4. M24l removes the give-up (the round-1 latch, held
    # until an answer that a destroyed host never delivers): the negative
    # control.
    ("M24l", gate_g11_a_fetch_that_never_answers_does_not_hold_the_latch, "ui",
     "            if (settingsCardInFlight && Now - settingsCardSentAt > 25f)\n",
     "            if (false)\n",
     "            if (settingsCardInFlight && Now - settingsCardSentAt > 25f)   // given up\n",
     "a fetch that never answers holds the latch"),
    ("M24m", gate_g11_a_fetch_that_never_answers_does_not_hold_the_latch, "ui",
     "                if (serial != settingsCardSerial)\n",
     "                if (false)\n",
     "                if (serial != settingsCardSerial)   // given up meanwhile\n",
     "an answer to a fetch given up still commits"),
    ("M24n", gate_g11_a_fetch_that_never_answers_does_not_hold_the_latch, "ui",
     "            settingsCardSentAt = Now;\n",
     "",
     "            settingsCardSentAt = Now;   // when it was sent\n",
     "a sent fetch is not stamped with its time and serial"),
]


def _edited(src, old, new):
    n = src.count(old)
    assert n == 1, "the search text occurs %d times: %r" % (n, old[:80])
    return src.replace(old, new)


@pytest.mark.parametrize("mid,gate,key,old,mutant,control,named", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_each_gate_is_red_under_its_mutation_and_green_under_its_control(mid, gate, key, old, mutant, control, named):
    s = _sources()
    red = dict(s, **{key: _edited(s[key], old, mutant)})
    assert red[key] != s[key], mid + ": the mutation did not apply"
    with pytest.raises(AssertionError, match=re.escape(named)):
        gate(red)
    green = dict(s, **{key: _edited(s[key], old, control)})
    assert green[key] != s[key], mid + ": the control did not apply"
    gate(green)
