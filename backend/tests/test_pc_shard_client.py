"""Client structure gates for board row 24 (the Settings full card), each
run on the real sources and, with its mutation and control, on edited COPIES
(#391): the mutation must turn the gate red and the control (an edit at the
same site that changes no behaviour) must leave it green. Nothing here needs a
database or the game.

Row 24 -- the Settings slot shows the WHOLE card other players see:
  G1  the client asks the server's full-card route, signed as the server
      verifies it, and decodes the answer as the CARD variant (750x1050), the
      size the server draws it at;
  G2  while a new look is on its way the slot shows the live picture with the
      pending line, and the card is fetched again once the stored portrait
      (the key) changes -- never while the look is pending.
Its strings:
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


NEW_KEYS = [
    "Saving your new picture - your card updates here once it has been sent.",
    "Other players still see this card: your new picture was not sent (the note below says why).",
    "Your card as other players see it.",
    "You are not in the card pool yet, so there is no card to show - this is your picture.",
    "Your card could not be loaded right now - it is tried again shortly.",
    "Loading your card...",
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
         gate_g9_every_new_string_is_in_every_catalogue]


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
