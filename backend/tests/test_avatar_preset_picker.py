"""Ask 5 (avatar presets chosen in the main menu): the design note's section
2.5 claims over the plugin's C# sources, each pinned to the code term it
names, and the i18n obligations of its section 2.7.

Same family as test_client_avatar_defaults.py. Every claim is a function over
the sources that raises AssertionError when the claim is false, and runs
three ways: against the tree (must pass), against an in-memory MUTATION of
the tree (must red) and against an in-memory negative CONTROL edit (must stay
green), so a claim that cannot fail, or that fails on any edit at all, is
caught here rather than trusted. Every scope is a brace-balanced span, never
the whole file, unless the claim is a census over a file.

The picker's pure rules (a tile's ring and live buttons, what a click does,
the preview geometry) are executed, not read: the client rules harness suite
"avatarpicker", pinned case by case in test_client_rules_harness.py.
"""
import io
import json
import os
import re
from pathlib import Path

import pytest

from _cs_structure import CsParseError, mask_code, strip_comments_only

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PLUGIN = Path(REPO) / "plugin"

PP = "AvatarPresetPicker.cs"
RL = "AvatarPickerRules.cs"
PL = "Plugin.cs"
NU = "NativeUI.cs"
CAT = "I18nCatalogues.cs"
# Files outside plugin/, keyed by their repo-relative path.
EXTRACT = "tools/i18n_extract.py"
SOURCE_JSON = "tools/i18n_source.json"
MAIN = "tools/client-rules-harness/Main.cs"
CSPROJ = "tools/client-rules-harness/client-rules-harness.csproj"
SELFTEST = "tools/client-rules-harness/AvatarPickerRulesSelfTest.cs"
NEW_FILES = (PP, RL)
EXTRA = (EXTRACT, SOURCE_JSON, MAIN, CSPROJ, SELFTEST)

_CACHE = {}


def _tree():
    if not _CACHE:
        for p in sorted(PLUGIN.glob("*.cs")):
            with io.open(str(p), encoding="utf-8") as fh:
                _CACHE[p.name] = fh.read()
        for rel in EXTRA:
            with io.open(os.path.join(REPO, rel), encoding="utf-8") as fh:
                _CACHE[rel] = fh.read()
    return dict(_CACHE)


# -- span helpers ---------------------------------------------------------

_MASK = {}
_STRIP = {}


def _memo(cache, fn, text):
    """Memoise only the tree's own file texts (identity, not equality):
    mutated copies and spans are computed fresh and never retained."""
    if not any(text is t for t in _CACHE.values()):
        return fn(text)
    k = id(text)
    if k not in cache:
        cache[k] = fn(text)
    return cache[k]


def _masked(text):
    return _memo(_MASK, mask_code, text)


def _one(text, sig, base=0):
    """The single brace-balanced block after `sig`, over the masked text."""
    masked = _masked(text)
    spans, search = [], 0
    while True:
        start = masked.find(sig, search)
        if start == -1:
            break
        ob = masked.find("{", start + len(sig))
        if ob == -1:
            raise CsParseError("no block opens after %r" % sig)
        depth, end = 0, None
        for i in range(ob, len(masked)):
            if masked[i] == "{":
                depth += 1
            elif masked[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            raise CsParseError("unbalanced braces after %r" % sig)
        spans.append((ob, end))
        search = end
    assert len(spans) == 1, "%d blocks match %r" % (len(spans), sig)
    a, b = spans[0]
    return base + a, base + b


def _span(text, sig, within=None):
    if within is None:
        return _one(text, sig)
    a, b = _one(text, within)
    return _one(text[a:b], sig, base=a)


def _body(text, sig, within=None):
    a, b = _span(text, sig, within)
    return _code(text[a:b])


def _code(text):
    return _memo(_STRIP, strip_comments_only, text)


# -- edit helpers (mutations and controls) ---------------------------------

def _replace(src, fname, old, new):
    s = dict(src)
    t = s[fname]
    assert t.count(old) == 1, "edit anchor %r occurs %d times in %s" % (old, t.count(old), fname)
    s[fname] = t.replace(old, new, 1)
    assert s[fname] != t
    return s


def _replace_within(src, fname, sig, old, new, within=None):
    """`_replace`, but the anchor is sought only inside the block after `sig`."""
    s = dict(src)
    t = s[fname]
    a, b = _span(t, sig, within)
    block = t[a:b]
    assert block.count(old) == 1, "edit anchor %r occurs %d times inside %r in %s" % (old, block.count(old), sig, fname)
    s[fname] = t[:a] + block.replace(old, new, 1) + t[b:]
    assert s[fname] != t
    return s


def _insert_after_open(src, fname, sig, text, within=None):
    """Insert `text` right after the opening brace of the block after `sig`."""
    s = dict(src)
    t = s[fname]
    a, _ = _span(t, sig, within)
    s[fname] = t[:a + 1] + "\n" + text + "\n" + t[a + 1:]
    return s


def _check(claim, mutation, control):
    """The three-way run. A parse failure never counts as the mutation's red."""
    src = _tree()
    claim(src)
    m = mutation(src)
    assert m != src, "the mutation changed nothing"
    try:
        claim(m)
    except CsParseError as e:
        raise AssertionError("the mutation broke parsing instead of the claim: %s" % e)
    except AssertionError:
        pass
    else:
        raise AssertionError("the mutation STAYED GREEN")
    c = control(src)
    assert c != src, "the control changed nothing"
    claim(c)


# -- the spans the claims scope on -----------------------------------------

PICKER = "internal static class AvatarPresetPicker"
TRY = "internal static void TryPlaceRow()"
FIND_TEMPLATE = "private static ListMenuButton FindTemplate(ListMenuButton anchor)"
PLACE = "private static void PlaceRow(ListMenuButton anchor)"
ENSURE = "private static void EnsureCanvas()"
REBUILD = "private static void Rebuild()"
COMPOSE = "private static void Compose(GameObject area, PlayerFace face, float k)"
ADD_PART = ("private static void AddPart(List<Part> parts, CharacterCreatorItemLoader loader, "
            "int id, CharacterItemType type, Vector2 faceOffset)")
APPLY = "private static void Apply(PickerAction action, int slot)"
ROW_BUTTON = "internal sealed class AvatarPresetsMenuButton : MonoBehaviour"
ESC = "internal sealed class AvatarPickerEscape : MonoBehaviour"
ONCLICK = "private void OnClick()"
RULES = "internal static partial class AvatarPickerRules"
PART_RECT = "internal static void PartRect("
CREATE_BUTTON = ("public static GameObject CreateButton(string name,Transform parent,string label,"
                 "float fontSize,Color textColor,Color bgColor,UnityEngine.Events.UnityAction onClick,"
                 "Vector2? sizeDelta=null)")
CREATE_PANEL = "public static GameObject CreatePanel(string name,Transform parent,Color bgColor,Vector2? sizeDelta=null)"
DECL = "private static readonly Dictionary<string, string> %s = new Dictionary<string, string>"
LOCALES = ("ES", "RU", "UK", "SV")

NEW_KEYS = ("AVATAR PRESETS", "Avatar presets", "Modded", "Vanilla", "Empty", "Has modded items")
REUSED_KEYS = ("Back", "Clear",
               "Modded avatar: <color=#88CCFF>{0}</color>",
               "Vanilla avatar: <color=#88CCFF>{0}</color>",
               "Avatar auto-switch: <color=#88CCFF>ON</color>",
               "Avatar auto-switch: <color=#88CCFF>OFF</color>",
               "Gold ring: your modded default",
               "Blue ring: your vanilla default",
               "Both rings: this preset is both of your defaults",
               "Red ring: this preset has items an unmodded player cannot see, so it cannot be your vanilla default")
FUNNELS = ("I18n.Tr(", "I18n.TrF(", "UIFactory.CreateText(", "UIFactory.CreateButton(", "UIFactory.SetText(")


def _control_comment(fname, sig, within=None, indent="            "):
    return lambda s: _insert_after_open(s, fname, sig, indent + "// control", within)


# -- P1 the row: the template and its placement -----------------------------

def _p1(src):
    b = _body(src[PP], FIND_TEMPLATE)
    assert "GetComponent<QuitButton>()" in b, "the template is not found by its QuitButton component"
    assert '== "QUIT"' in b, "the TMP text QUIT fallback is gone"
    assert "tmpTextProp.GetValue(" in b, "the fallback does not read the TMP text through reflection"
    assert "b.transform.parent == anchor.transform.parent && b.GetComponent<QuitButton>() != null" in b, \
        "the template is not required to share the anchor's container"
    assert "b.transform.parent != anchor.transform.parent) continue;" in b, "the TMP fallback leaves the anchor's container"


def test_p1_the_template_is_the_quit_button_with_the_tmp_text_fallback():
    _check(_p1,
           lambda s: _replace(s, PP, "b.GetComponent<QuitButton>() != null", "false"),
           _control_comment(PP, FIND_TEMPLATE))


def _p2(src):
    b = _body(src[PP], PLACE)
    assert b.count("SetSiblingIndex(") == 1, "the row is not placed by exactly one SetSiblingIndex"
    assert "anchor.transform.GetSiblingIndex() + 1" in b, "the row does not sit right under the anchor row"
    for bad in ("SetAsLastSibling", "SetAsFirstSibling", "anchoredPosition", "localPosition", ".SetParent("):
        assert bad not in b, "the row is positioned by %s, not by its sibling index" % bad
    assert "var container = template.transform.parent;" in b and "Instantiate(template.gameObject, container)" in b, \
        "the clone is not born under the template's container"


def test_p2_the_sibling_index_is_the_only_placement():
    _check(_p2,
           lambda s: _replace(s, PP, "clone.transform.SetSiblingIndex(anchor.transform.GetSiblingIndex() + 1);",
                              "clone.transform.SetAsLastSibling();"),
           _control_comment(PP, PLACE))


def _p3(src):
    b = _body(src[PP], PLACE)
    assert "GetComponent<QuitButton>()" in b and "Destroy(quit)" in b, "the clone keeps its QuitButton"
    assert "GetComponent<GoBack>()" in b and "Destroy(back)" in b, "the clone keeps its GoBack"
    assert "AddComponent<AvatarPresetsMenuButton>()" in b, "the clone gets no click component"
    assert "clone.GetComponent<QuitButton>()" in b and "clone.GetComponent<GoBack>()" in b, \
        "the components destroyed are not the clone's"


def test_p3_the_clone_loses_quit_button_and_go_back():
    _check(_p3,
           lambda s: _replace(s, PP, "if (back != null) UnityEngine.Object.Destroy(back);", "if (back != null) { }"),
           _control_comment(PP, PLACE))


def _p4(src):
    b = _body(src[PP], TRY)
    pre = b.find("if (anchor == null) return;")
    tick = b.find("retryCount++")
    assert pre != -1, "the anchor precondition is gone"
    assert tick != -1 and pre < tick, "a retry is spent before the anchor precondition"
    room = b.find("if (inRoom)")
    assert room != -1 and room < tick, "a room costs a retry"
    assert "addedRow == null" in b, "a destroyed row is not placed again"
    assert "retryCount % 10" in b, "the exhausted budget stops trying instead of slowing down"
    assert re.search(r"if \(inRoom\)\s*\{[^}]*\breturn;", b), "a room does not end the poll"


def test_p4_the_precondition_and_the_room_cost_no_retry():
    _check(_p4,
           lambda s: _replace(s, PP, "if (anchor == null) return;", "if (anchor == null) { }"),
           _control_comment(PP, TRY))


# -- P5 every click behind ClickGuard -------------------------------------------

def _p5(src):
    b = _body(src[PP], ONCLICK, within=ROW_BUTTON)
    assert "ClickGuard.Claim(this)" in b, "the row's click is not behind ClickGuard"
    assert "if (!ClickGuard.Claim(this)) return;" in b, "the row's click guard is not the house form"
    code = _code(src[PP])
    assert code.count("UIFactory.CreateButton(") >= 6, "the picker's buttons are not all UIFactory buttons"
    assert "AddComponent<ClickHandler>" not in code and "onClick.AddListener" not in code, \
        "a picker button is wired outside UIFactory.CreateButton"
    cb = _body(src[NU], CREATE_BUTTON)
    assert cb.count("ClickGuard.Claim(go)") >= 2, "UIFactory.CreateButton no longer guards its click"


def test_p5_the_row_click_is_guarded():
    _check(_p5,
           lambda s: _replace(s, PP, "if (!ClickGuard.Claim(this)) return;", ""),
           _control_comment(PP, ONCLICK, within=ROW_BUTTON))


def test_p5_the_factory_button_is_guarded():
    _check(_p5,
           lambda s: _replace_within(s, NU, CREATE_BUTTON,
                                     "var guarded=new UnityEngine.Events.UnityAction(()=>{if(ClickGuard.Claim(go))onClick();});",
                                     "var guarded=new UnityEngine.Events.UnityAction(()=>{onClick();});"),
           _control_comment(PP, ONCLICK, within=ROW_BUTTON))


# -- P6 its own canvas; nothing of the menu's touched ---------------------------

def _p6(src):
    b = _body(src[PP], ENSURE)
    assert '"sortingOrder"' in b and "30000" in b, "the picker's canvas is not at sortingOrder 30000"
    assert 'new GameObject("CR_AvatarPickerCanvas")' in b, "the picker does not own its canvas"
    m = re.search(r'CreatePanel\("BG", canvasGO\.transform, new Color\(([^)]*)\)\)', b)
    assert m, "the background panel is gone"
    alpha = float(m.group(1).split(",")[-1].strip().rstrip("f"))
    assert alpha > 0, "a transparent background takes no raycast"
    cp = _body(src[NU], CREATE_PANEL)
    assert "pImgRaycastTarget?.SetValue(img,true)" in cp, "CreatePanel no longer makes its image a raycast target"
    assert "canvasGO.AddComponent(UIFactory.tGR)" in b, "the picker's canvas has no raycaster of its own"


def test_p6_the_overlay_canvas_sits_at_30000_over_a_raycast_background():
    _check(_p6,
           lambda s: _replace(s, PP, "if (so != null) so.SetValue(cv, 30000);", "if (so != null) so.SetValue(cv, 0);"),
           _control_comment(PP, ENSURE))


def _p7(src):
    for f in NEW_FILES + (SELFTEST,):
        code = _code(src[f])
        for bad in ("using UnityEngine.UI;", "using TMPro;", "EventSystem", "mainMenuGroup", "GraphicRaycaster"):
            assert bad not in code, "%s carries %s" % (f, bad)
    for f in (RL, SELFTEST):
        assert "using UnityEngine" not in _code(src[f]), "%s is not Unity-free" % f
    pp = src[PP]
    ea, ez = _span(pp, ENSURE)
    for m in re.finditer(r"UIFactory\.tGR", pp):
        assert ea <= m.start() < ez, "a raycaster is added outside EnsureCanvas (offset %d)" % m.start()


def test_p7_no_ui_assembly_reference_no_event_system_no_menu_group():
    _check(_p7,
           lambda s: _replace(s, PP, "using UnityEngine;\n", "using UnityEngine;\nusing UnityEngine.UI;\n"),
           _control_comment(PP, PICKER, indent="        "))


# -- P8 the writes: item 19's three setters and nothing else --------------------

ALLOWED = {"SetModded", "SetVanilla", "SetAuto", "ReadSetting", "PresetLabel", "VanillaUsable", "MenuPortraits"}


def _p8(src):
    code = _code(src[PP])
    used = set(re.findall(r"AvatarDefaults\.([A-Za-z_]+)", code))
    assert used <= ALLOWED, "the picker reaches AvatarDefaults members outside its allowance: %s" % sorted(used - ALLOWED)
    assert {"SetModded", "SetVanilla", "SetAuto"} <= used, "a setter is no longer called"
    for bad in ("PlayerPrefs", "SelectFace(", "ClickButton(", ".Value =", "Config.Bind", "Config["):
        assert bad not in code, "the picker writes through %s" % bad
    assert not re.search(r"\.Value\s*=[^=]", code), "the picker assigns a config value"
    b = _body(src[PP], APPLY)
    for call in ("AvatarDefaults.SetModded(slot)", "AvatarDefaults.SetModded(-1)",
                 "AvatarDefaults.SetVanilla(slot)", "AvatarDefaults.SetVanilla(-1)"):
        assert call in b, "Apply lost %s" % call
    assert "default: return;" in b, "a refused action still rebuilds"


def test_p8_no_player_prefs_write():
    _check(_p8,
           lambda s: _insert_after_open(s, PP, APPLY, '            PlayerPrefs.SetInt("SelectedPlayerFace", slot);'),
           _control_comment(PP, APPLY))


def test_p8_no_avatar_defaults_member_outside_the_allowance():
    _check(_p8,
           lambda s: _insert_after_open(s, PP, APPLY, '            AvatarDefaults.Apply(slot, "picker");'),
           _control_comment(PP, APPLY))


# -- P9 eight tiles, four by two --------------------------------------------------

def _p9(src):
    code = _code(src[RL])
    assert "internal const int Tiles = 8;" in code, "the tile count is not eight"
    assert "internal const int Columns = 4;" in code, "the grid is not four wide"
    rb = _body(src[PP], REBUILD)
    assert "for (int s = 0; s < AvatarPickerRules.Tiles; s++)" in rb, "the picker does not loop the rules' tile count"
    assert "AvatarPickerRules.Row(s)" in rb, "a tile is not placed by the rules' row"
    assert "AvatarPickerRules.Tile(s, present, authored, clean, setting.Modded, setting.Vanilla)" in rb, \
        "a tile's state is not the rules' decision"
    loop = _body(src[PP], "for (int s = 0; s < AvatarPickerRules.Tiles; s++)", within=REBUILD)
    assert "continue" not in loop and "break" not in loop, "a tile is skipped inside the eight-slot loop"
    assert not re.search(r"\bs\s*(==|!=|<=|>=|<|>)\s*\d", loop), "a slot is singled out inside the eight-slot loop"


def test_p9_eight_tiles_in_four_columns():
    _check(_p9,
           lambda s: _replace(s, RL, "internal const int Tiles = 8;", "internal const int Tiles = 10;"),
           _control_comment(RL, RULES, indent="        "))


# -- P10 GetItem is the only part source ------------------------------------------

def _p10(src):
    code = _code(src[PP])
    ap = _body(src[PP], ADD_PART)
    assert "loader.GetItem(id, type)" in ap, "a part is not fetched through GetItem"
    for bad in (".eyes[", ".mouths[", ".accessories[", "FindObjectsOfType<CharacterItem>", "Resources.Load", "CustomCosmetics."):
        assert bad not in code, "a part comes from %s, not GetItem" % bad
    cp = _body(src[PP], COMPOSE)
    assert "CharacterCreatorItemLoader.instance" in cp, "the loader is not the game's singleton"
    assert cp.count("AddPart(parts, loader,") == 4, "a face has four parts"
    assert "parts.Sort(" in cp, "the parts are not ordered by sorting order"
    for idn, off in (("face.eyeID", "face.eyeOffset"), ("face.mouthID", "face.mouthOffset"),
                     ("face.detailID", "face.detailOffset"), ("face.detail2ID", "face.detail2Offset")):
        assert cp.count(idn + ",") == 1 and cp.count(off) == 1, "the part %s is not composed exactly once with its offset" % idn


def test_p10_get_item_is_the_only_part_source():
    _check(_p10,
           lambda s: _replace(s, PP, "try { item = loader.GetItem(id, type); } catch { }",
                              "try { item = loader.eyes[id]; } catch { }"),
           _control_comment(PP, ADD_PART))


# -- P11 the SpawnItem math; composition never per frame ----------------------------

PER_FRAME_BAD = ("Rebuild(", "Compose(", "GetItem(", "FindObjectsOfType", "GetProperty(", "GetMethod(", "GetType(", "AppDomain")


def _p11(src):
    b = _body(src[RL], PART_RECT)
    for term in ("w = spriteW * itemScale * k;", "h = spriteH * itemScale * k;",
                 "x = (itemOffX + faceOffX) * k + (0.5f - pivotFracX) * w;",
                 "y = (itemOffY + faceOffY) * k + (0.5f - pivotFracY) * h;"):
        assert term in b, "the SpawnItem term %r is gone" % term
    pp = src[PP]
    for sig, within in (("private void Update()", ESC), ("private void LateUpdate()", ROW_BUTTON)):
        u = _body(pp, sig, within=within)
        for bad in PER_FRAME_BAD:
            assert bad not in u, "%s does %s per frame" % (sig, bad)
    t = _body(pp, TRY)
    for bad in ("Rebuild(", "Compose(", "GetItem("):
        assert bad not in t, "the row poll does %s" % bad
    rf = _body(pp, REFRESH)
    g = rf.find(GEN_GUARD)
    assert g != -1 and g < rf.find("Close();"), "the per-frame tick's staleness check closes without a catalogue change"
    code = _code(pp)
    assert code.count("Compose(area, face, k)") == 1, "the face is composed from more than one site"
    assert "AvatarPickerRules.PartRect(" in _body(pp, COMPOSE), "the composition does not use the rules' rect"


def test_p11_the_face_offset_is_added_to_the_item_offset():
    _check(_p11,
           lambda s: _replace(s, RL, "x = (itemOffX + faceOffX) * k", "x = (itemOffX) * k"),
           _control_comment(RL, PART_RECT))


def test_p11_nothing_composes_per_frame():
    _check(_p11,
           lambda s: _insert_after_open(s, PP, "private void Update()", "            Rebuild();", within=ESC),
           _control_comment(PP, "private void Update()", within=ESC))


# -- P12 every display literal through a translation funnel ------------------------

def _p12(src):
    code = _code(src[PP])
    lines = code.splitlines()
    # every literal a SetTextRaw call carries is markup, whitespace or an escape: the words come through Tr/TrF
    pos = 0
    while True:
        i0 = code.find("UIFactory.SetTextRaw(", pos)
        if i0 == -1:
            break
        j0 = code.index("(", i0)
        depth, k0 = 0, j0
        while k0 < len(code):
            ch = code[k0]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            k0 += 1
        args = re.sub(r'I18n\.TrF?\(\s*"(?:[^"\\]|\\.)*"', "I18n.Tr(", code[j0 + 1:k0])
        for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', args):
            bare = re.sub(r"\\.", "", re.sub(r"<[^>]*>", "", lit))
            assert not re.search(r"[A-Za-z]", bare), "SetTextRaw carries the untranslated literal %r" % lit
        pos = k0
    for key in NEW_KEYS + REUSED_KEYS:
        lit = '"%s"' % key
        hits = [i for i, l in enumerate(lines) if lit in l]
        assert hits, "the picker no longer shows %r" % key
        for i in hits:
            window = "\n".join(lines[max(0, i - 2): i + 1])
            assert any(f in window for f in FUNNELS), \
                "%r is shown outside the translation funnels: %s" % (key, lines[i].strip())
    strings = json.loads(src[SOURCE_JSON])["strings"]
    for key in NEW_KEYS:
        assert key in strings, "tools/i18n_source.json lacks %r: the extractor did not run in the lane" % key


def test_p12_every_display_literal_is_translated():
    _check(_p12,
           lambda s: _replace(s, PP, 'tmpTextProp.SetValue(tmp, I18n.Tr("AVATAR PRESETS"));',
                              'tmpTextProp.SetValue(tmp, "AVATAR PRESETS");'),
           _control_comment(PP, PLACE))


def _p13(src):
    t = src[EXTRACT]
    m = re.search(r"^FILES\s*=\s*\[", t, re.M)
    assert m, "the extractor's FILES list is gone"
    end = t.index("\n]", m.end())
    # Only live entries count: a commented-out name is still a substring of the block.
    live = [ln.split("#", 1)[0] for ln in t[m.end():end].splitlines()]
    assert any('"AvatarPresetPicker.cs"' in ln for ln in live), "the picker is not a live entry of the extractor's FILES list"
    out = src[SOURCE_JSON]
    for key in NEW_KEYS:
        assert '"%s"' % key in out, "the extractor's output lacks %r" % key


def test_p13_the_extractor_scans_the_picker():
    _check(_p13,
           lambda s: _replace(s, EXTRACT, '    "AvatarPresetPicker.cs",', '    # "AvatarPresetPicker.cs",'),
           lambda s: _replace(s, EXTRACT, "FILES = [", "FILES = [  # control"))


def _p14(src):
    for name in LOCALES:
        b = _body(src[CAT], DECL % name)
        for key in NEW_KEYS:
            m = re.search(r'\["%s"\] = "([^"]*)"' % re.escape(key), b)
            assert m, "%s lacks %r" % (name, key)
            assert m.group(1).strip(), "%s has an empty %r" % (name, key)


def test_p14_four_locale_entries_for_every_new_key():
    _check(_p14,
           lambda s: _replace(s, CAT, '["Has modded items"] = "Tiene objetos con mod",', ""),
           _control_comment(CAT, DECL % "ES"))


# -- P15 the hook beside the injector's; P16 the harness registration -------------------

def _p15(src):
    code = _code(src[PL])
    assert code.count("AvatarPresetPicker.TryPlaceRow();") == 1, "the row poll is not hooked exactly once"
    assert code.count("AvatarPresetPicker.Reset();") == 1, "the reset is not hooked exactly once"
    assert "try { AvatarPresetPicker.TryPlaceRow(); } catch { }" in code, "the row poll is not wrapped"
    i = code.index("MainMenuInjector.TryInject();")
    j = code.index("AvatarPresetPicker.TryPlaceRow();")
    assert 0 < j - i < 300, "the picker's poll does not sit beside the injector's"
    masked = _masked(src[PL])
    mi = masked.index("MainMenuInjector.TryInject();")
    mj = masked.index("AvatarPresetPicker.TryPlaceRow();")
    assert masked.count("{", 0, mi) - masked.count("}", 0, mi) == masked.count("{", 0, mj) - masked.count("}", 0, mj), \
        "the picker's poll is nested deeper than the injector's"
    k = code.index("MainMenuInjector.Reset();")
    l = code.index("AvatarPresetPicker.Reset();")
    assert 0 < l - k < 200, "the picker's reset does not sit beside the injector's"


def test_p15_the_poll_and_the_reset_sit_beside_the_injectors():
    _check(_p15,
           lambda s: _replace(s, PL, "try { AvatarPresetPicker.TryPlaceRow(); } catch { }", ""),
           lambda s: _replace(s, PL, "try { MainMenuInjector.TryInject(); } catch { }",
                              "try { MainMenuInjector.TryInject(); } catch { } // control"))


def _p16(src):
    m = _code(src[MAIN])
    assert 'RunSuite("avatarpicker"' in m and "AvatarPickerRules.SelfTest()" in m, "the suite is not registered"
    c = src[CSPROJ]
    assert '<Compile Include="../../plugin/AvatarPickerRules.cs" />' in c, "the harness does not compile the rules"
    assert '<Compile Include="AvatarPickerRulesSelfTest.cs" />' in c, "the harness does not compile the self-test"
    st = _code(src[SELFTEST])
    assert st.count("Check(r, ") == 14, "the suite does not have fourteen cases"
    assert '"PASS" : "FAIL"' in st and '" | got="' in st, "a case prints no verdict or no measurement"


def test_p16_the_harness_runs_the_suite():
    _check(_p16,
           lambda s: _replace(s, MAIN, 'RunSuite("avatarpicker"', 'RunSuite("avatarpickr"'),
           lambda s: _replace(s, MAIN, 'RunSuite("avatarpicker"', 'RunSuite("avatarpicker" /* control */'))


# -- Codex r1 fixes: H1 the live write gate, H2 the menu exclusion, H3 the camera
#    handles, M1 the row wiring, L1 the catalogue generation ------------------------

CU = "CompetitiveUI.cs"
GATE = "private static bool WriteGateOpen(string what)"
TOGGLE_AUTO = "private static void ToggleAuto()"
REFRESH = "internal static void CloseIfStale()"
OPEN = "internal static void Open()"
TRY_WIRE = "private bool TryWire()"
START = "private void Start()"
LATE = "private void LateUpdate()"
RESOLVE = "private void ResolveCamera()"
INIT_TYPES = "public static bool InitTypes()"
WRITE_ALLOWED = "internal static bool WriteAllowed(bool inRoom, bool roomUnreadable, int heldHome)"
GATE_APPLY = 'if (!WriteGateOpen("nomination")) { Close(); return; }'
GATE_AUTO = 'if (!WriteGateOpen("auto toggle")) { Close(); return; }'
MENU_TERM = "ModalOwnsInputBesidesAvatarPicker || AvatarPresetPicker.IsOpen"
YIELD_OPEN = "if (CompetitiveUI.InputOwnedBesidesAvatarPicker) return;"
YIELD_TICK = "if (CompetitiveUI.InputOwnedBesidesAvatarPicker) { AvatarPresetPicker.Close(); return; }"
TYPES_PRE = "if (UIFactory.tButton == null && !UIFactory.InitTypes()) return;"
GEN_GUARD = "if (I18n.CatalogueGeneration == openGeneration) return;"
GEN_LABEL = "if (gen != labelGeneration) { labelGeneration = gen; label = RowLabel(); }"
SETTERS = ("AvatarDefaults.SetModded(", "AvatarDefaults.SetVanilla(", "AvatarDefaults.SetAuto(")
GATE_LIVE = "try { inRoom = Photon.Pun.PhotonNetwork.InRoom && !Photon.Pun.PhotonNetwork.OfflineMode; } catch { unreadable = true; }"
GATE_CALL = "AvatarPickerRules.WriteAllowed(inRoom, unreadable, heldHome)"
CLOSE = "internal static void Close()"
CLEAR = "private static void ClearContent()"
TICK_BAD = ("Rebuild(", "Compose(", "Open(", "Toggle(", "RefreshIfStale")


def _p17(src):
    a = _body(src[PP], APPLY)
    g = a.find(GATE_APPLY)
    assert g != -1 and g < a.find("switch (action)"), "a nomination reaches a setter before the live gate"
    t = _body(src[PP], TOGGLE_AUTO)
    assert t.find(GATE_AUTO) != -1 and t.find(GATE_AUTO) < t.find("AvatarDefaults.SetAuto("), \
        "the auto toggle reaches SetAuto before the live gate"
    assert "() => ToggleAuto()" in _body(src[PP], REBUILD), "the auto-switch button does not go through ToggleAuto"
    gb = _body(src[PP], GATE)
    for term in (GATE_LIVE, "Plugin.AvatarHomeSlot", GATE_CALL):
        assert term in gb, "the gate no longer reads %s" % term
    assert "GameStateWatcher" not in gb, "the gate reads the watcher's polled room flag (Codex r2 H1)"
    assert "unreadable = true" in gb, "an unreadable room state does not fail closed"
    assert "return !inRoom && !roomUnreadable && heldHome < 0;" in _body(src[RL], WRITE_ALLOWED), "the gate rule changed"
    # every setter call sits inside one of the two gated bodies
    raw = src[PP]
    ga, gt = _span(raw, APPLY), _span(raw, TOGGLE_AUTO)
    for setter in SETTERS:
        hits = [m.start() for m in re.finditer(re.escape(setter), raw)]
        assert hits, "%s is no longer called" % setter
        for h in hits:
            assert ga[0] <= h < ga[1] or gt[0] <= h < gt[1], "%s is called outside the gated bodies" % setter


def test_p17_a_nomination_passes_the_live_gate():
    _check(_p17,
           lambda s: _replace(s, PP, "            " + GATE_APPLY + "\n", ""),
           _control_comment(PP, APPLY))


def test_p17_the_auto_toggle_passes_the_live_gate():
    _check(_p17,
           lambda s: _replace(s, PP, "            " + GATE_AUTO + "\n", ""),
           _control_comment(PP, TOGGLE_AUTO))


def test_p17_the_gate_rule_refuses_a_held_home_face():
    _check(_p17,
           lambda s: _replace(s, RL, "return !inRoom && !roomUnreadable && heldHome < 0;",
                              "return !inRoom && !roomUnreadable;"),
           _control_comment(RL, WRITE_ALLOWED))


def _p18(src):
    t = src[CU]
    m = re.search(r"OtherModalOwnsInput\s*=>", t)
    assert m, "the modal-ownership term is gone"
    expr = t[m.end():t.index(";", m.end())]
    assert "AvatarPresetPicker.IsOpen" in _code(expr), "the open picker does not own the raw click handlers' input"
    code = _code(t)
    writes = re.findall(r"ClickHandler\.ModalBlockInput\s*=[^=]", code)
    assert len(writes) == 1, "ModalBlockInput is written %d times in CompetitiveUI" % len(writes)
    assert "ClickHandler.ModalBlockInput = KeyboardInputOwnedByModal || Keybinds.CaptureOwnsInput;" in code, \
        "the raw-click block is not written from the keyboard gate"
    assert "AnyModalOwnsInput" in _expr(code, "KeyboardInputOwnedByModal") and "OtherModalOwnsInput" in _expr(code, "AnyModalOwnsInput"), \
        "the chain from the modal term to the raw-click block is broken"


def test_p18_the_open_picker_owns_the_raw_click_input():
    _check(_p18,
           lambda s: _replace(s, CU, MENU_TERM, "ModalOwnsInputBesidesAvatarPicker"),
           lambda s: _replace(s, CU, "// Ask 5 (Codex r1 H2): the avatar-preset picker",
                              "// control: the avatar-preset picker"))


def _p19(src):
    o = _body(src[PP], OPEN)
    y = o.find(YIELD_OPEN)
    assert y != -1 and y < o.find("EnsureCanvas();"), "the picker opens over the menu"
    assert re.match(r"\{\s*try\s*\{\s*" + re.escape(YIELD_OPEN), o), "something runs in Open before the yield"
    u = _body(src[PP], "private void Update()", within=ESC)
    assert YIELD_TICK in u, "the picker stays open when the menu opens"


def test_p19_the_picker_refuses_to_open_over_the_menu():
    _check(_p19,
           lambda s: _replace(s, PP, YIELD_OPEN, "if (false) return;"),
           _control_comment(PP, OPEN, indent="                "))


def test_p19_the_picker_closes_when_the_menu_opens():
    _check(_p19,
           lambda s: _replace(s, PP, "            " + YIELD_TICK + "\n", ""),
           _control_comment(PP, "private void Update()", within=ESC))


def _p20(src):
    r = _body(src[NU], RESOLVE)
    assert "GetProperty(" not in r and "GetMethod(" not in r, \
        "ResolveCamera does a reflection lookup in the click handler's Update path"
    for bad in ("GetType(", "GetField(", "GetMembers(", "InvokeMember("):
        assert bad not in r, "ResolveCamera does %s in the click handler's Update path" % bad
    assert "UIFactory.pCanvasRenderMode" in r and "UIFactory.pCanvasWorldCamera" in r, \
        "ResolveCamera does not read the cached canvas handles"
    i = _body(src[NU], INIT_TYPES)
    assert 'pCanvasRenderMode=tCanvas?.GetProperty("renderMode",bf)' in i, "InitTypes no longer resolves the render-mode handle"
    assert 'pCanvasWorldCamera=tCanvas?.GetProperty("worldCamera",bf)' in i, "InitTypes no longer resolves the camera handle"


def test_p20_the_click_handler_resolves_its_camera_without_a_lookup():
    _check(_p20,
           lambda s: _replace(s, NU, "var rmP=UIFactory.pCanvasRenderMode;int rm=rmP!=null?(int)rmP.GetValue(cc):0;",
                              'int rm=(int)UIFactory.tCanvas.GetProperty("renderMode",BindingFlags.Public|BindingFlags.Instance).GetValue(cc);'),
           _control_comment(NU, RESOLVE))


def _p21(src):
    t = _body(src[PP], TRY)
    pre = t.find(TYPES_PRE)
    assert pre != -1 and pre < t.find("FindAnchorRow()"), "the row is placed before the factory's types are resolved"
    assert pre < t.find("retryCount++"), "the types precondition costs a retry"
    st = _body(src[PP], START, within=ROW_BUTTON)
    w = st.find("if (!TryWire())")
    assert w != -1 and st.find("UnityEngine.Object.Destroy(gameObject);", w) != -1, \
        "a row whose wiring failed is kept as if complete"
    tw = _body(src[PP], TRY_WIRE, within=ROW_BUTTON)
    for term in ("if (bt == null) return false;", "if (btn == null) return false;",
                 "if (onClick == null) return false;", "if (add == null) return false;", "return true;"):
        assert term in tw, "TryWire lost %s" % term
    assert "add.Invoke(onClick, new object[] { action });" in tw, "TryWire reports success without adding the listener"
    assert tw.find("add.Invoke(") < tw.find("return true;"), "TryWire returns before the listener is added"
    assert "addedRow == null" in t, "a destroyed row is not placed again"


def test_p21_the_row_waits_for_the_factory_types():
    _check(_p21,
           lambda s: _replace(s, PP, "            " + TYPES_PRE + "\n", ""),
           _control_comment(PP, TRY))


def test_p21_a_row_whose_wiring_failed_is_placed_again():
    _check(_p21,
           lambda s: _replace(s, PP, "                UnityEngine.Object.Destroy(gameObject);\n", ""),
           _control_comment(PP, START, within=ROW_BUTTON))


def _p22(src):
    l = _body(src[PP], LATE, within=ROW_BUTTON)
    assert "int gen = I18n.CatalogueGeneration;" in l and GEN_LABEL in l, \
        "the row's label does not follow the catalogue generation"
    assert "I18n.Tr(" not in l, "the row translates on every tick"
    assert "textProp.SetValue(tmp, label)" in l, "the row caches a new label but never shows it"
    assert 'return I18n.Tr("AVATAR PRESETS");' in _body(src[PP], ROW_LABEL, within=ROW_BUTTON), \
        "the row's label is not the whole key through Tr"
    rf = _body(src[PP], REFRESH)
    g = rf.find(GEN_GUARD)
    assert g != -1 and g < rf.find("Close();"), "the open picker closes without a catalogue change"
    assert "Rebuild(" not in rf and "Compose(" not in rf, "a catalogue change composes from the per-frame tick (Codex r2 H3)"
    assert "openGeneration = I18n.CatalogueGeneration;" in _body(src[PP], REBUILD), \
        "Rebuild does not record the catalogue generation"
    u = _body(src[PP], "private void Update()", within=ESC)
    assert "AvatarPresetPicker.CloseIfStale();" in u, "the per-frame tick does not close a stale picker"


def test_p22_the_row_label_follows_a_language_change():
    _check(_p22,
           lambda s: _replace(s, PP, "                " + GEN_LABEL + "   // L1: a language change re-translates the label\n", ""),
           _control_comment(PP, LATE, within=ROW_BUTTON))


def test_p22_a_stale_picker_closes_once_per_catalogue_change_only():
    _check(_p22,
           lambda s: _replace(s, PP, "            " + GEN_GUARD + "\n", ""),
           _control_comment(PP, REFRESH))



# -- Codex r2 fixes: H1 the live room read, H2 the shared yield predicate, H3 no rebuild
#    on the per-frame path ----------------------------------------------------------------

def _p23(src):
    gb = _body(src[PP], GATE)
    assert GATE_LIVE in gb, "the gate does not read Photon's two flags live, failing closed on a throw"
    assert "GameStateWatcher" not in gb, "the gate reads the watcher's polled room flag"
    assert GATE_CALL in gb, "the gate does not pass its three live readings to the rule"
    # the poll keeps its own live read: the two sites agree on the source
    assert "Photon.Pun.PhotonNetwork.InRoom && !Photon.Pun.PhotonNetwork.OfflineMode" in _body(src[PP], TRY), \
        "the row poll no longer reads Photon live"


def test_p23_the_gate_reads_the_room_live():
    _check(_p23,
           lambda s: _replace(s, PP, GATE_LIVE, "try { inRoom = GameStateWatcher.IsInOnlineRoom; } catch { unreadable = true; }"),
           _control_comment(PP, GATE))


def test_p23_the_gate_passes_the_held_home_face_it_read():
    _check(_p23,
           lambda s: _replace(s, PP, GATE_CALL, "AvatarPickerRules.WriteAllowed(inRoom, unreadable, -1)"),
           _control_comment(PP, GATE))


def _expr(t, name):
    m = re.search(re.escape(name) + r"\s*=>", t)
    assert m, "%s is gone" % name
    return t[m.end():t.index(";", m.end())]


def _p24(src):
    t = _code(src[CU])
    other = _expr(t, "OtherModalOwnsInput")
    assert "ModalOwnsInputBesidesAvatarPicker" in other and "AvatarPresetPicker.IsOpen" in other, \
        "the modal term is not the shared predicate plus the picker"
    shared = _expr(t, "ModalOwnsInputBesidesAvatarPicker")
    for term in ("BackdroplessModalOpen", "NativeUI.InfoPopupOpen", "NativeUI.PickerOpen", "NativeUI.LangPromptOpen",
                 "NativeUI.CardPreviewOpen", "PlayerCardsUI.CardPopupOpen", "!Plugin.DataConsentAsked"):
        assert term in shared, "the shared predicate lost %s" % term
    assert "AvatarPresetPicker" not in shared, "the shared predicate names the picker"
    yld = _expr(t, "InputOwnedBesidesAvatarPicker")
    for term in ("NativeUI.IsOpen", "ModalOwnsInputBesidesAvatarPicker", "NativeUI.UtilityPopupOpen"):
        assert term in yld, "the picker's yield predicate lost %s" % term
    assert "AvatarPresetPicker" not in yld, "the picker would yield to itself"
    pp = src[PP]
    assert "CompetitiveUI.InputOwnedBesidesAvatarPicker" in _body(pp, OPEN), "Open does not read the yield predicate"
    assert "CompetitiveUI.InputOwnedBesidesAvatarPicker" in _body(pp, "private void Update()", within=ESC), \
        "the tick does not read the yield predicate"


def test_p24_a_popup_is_an_owner_the_picker_yields_to():
    _check(_p24,
           lambda s: _replace(s, CU, "            || NativeUI.PickerOpen || NativeUI.LangPromptOpen\n",
                              "            || NativeUI.LangPromptOpen\n"),
           lambda s: _replace(s, CU, "Ask 5 (Codex r2 H2): what the avatar-preset picker yields to:",
                              "control: what the avatar-preset picker yields to:"))


def test_p24_the_yield_predicate_carries_every_other_modal_term():
    _check(_p24,
           lambda s: _replace(s, CU, "               NativeUI.IsOpen || ModalOwnsInputBesidesAvatarPicker\n",
                              "               NativeUI.IsOpen || BackdroplessModalOpen\n"),
           lambda s: _replace(s, CU, "Ask 5 (Codex r2 H2): what the avatar-preset picker yields to:",
                              "control: what the avatar-preset picker yields to:"))


def _p25(src):
    pp = src[PP]
    rf = _body(pp, REFRESH)
    assert GEN_GUARD in rf and "Close();" in rf, "a stale picker is not closed"
    for bad in PER_FRAME_BAD + TICK_BAD:
        assert bad not in rf, "the staleness check does %s" % bad
    for sig in (CLOSE, CLEAR):
        b = _body(pp, sig)
        for bad in PER_FRAME_BAD + TICK_BAD:
            assert bad not in b, "%s does %s on the per-frame path" % (sig, bad)
    u = _body(pp, "private void Update()", within=ESC)
    for bad in PER_FRAME_BAD + TICK_BAD:
        assert bad not in u, "the per-frame tick does %s" % bad
    calls = set(re.findall(r"AvatarPresetPicker\.(\w+)\(", u))
    assert calls == {"Close", "CloseIfStale"}, "the per-frame tick reaches %s" % sorted(calls)
    assert "openGeneration = I18n.CatalogueGeneration;" in _body(pp, REBUILD), "Rebuild does not record the catalogue generation"


def test_p25_a_catalogue_change_closes_the_picker_without_a_rebuild():
    _check(_p25,
           lambda s: _replace_within(s, PP, REFRESH, "Close();", "Rebuild();"),
           _control_comment(PP, REFRESH))


def test_p25_the_tick_reaches_nothing_that_composes():
    _check(_p25,
           lambda s: _replace(s, PP, "            AvatarPresetPicker.CloseIfStale();\n",
                              "            AvatarPresetPicker.CloseIfStale();\n            AvatarPresetPicker.Open();\n"),
           _control_comment(PP, "private void Update()", within=ESC))



# -- Codex r1's blind spots: one mutant per route with its control (test-only hardening) -------

READOUT_LINE = ('            var modded = UIFactory.CreateText("ModdedReadout", choices.transform, "", 20f, Color.white, '
                'UIFactory.AlignMidLeft, new Vector2(340f, 44f));')


def test_b1_the_template_shares_the_anchor_container():
    _check(_p1,
           lambda s: _replace(s, PP, "b.transform.parent == anchor.transform.parent && b.GetComponent<QuitButton>() != null",
                              "b.transform.parent != anchor.transform.parent && b.GetComponent<QuitButton>() != null"),
           _control_comment(PP, FIND_TEMPLATE))


def test_b2_the_clone_is_born_under_the_template_container():
    _check(_p2,
           lambda s: _replace(s, PP, "Instantiate(template.gameObject, container)", "Instantiate(template.gameObject, anchor.transform)"),
           _control_comment(PP, PLACE))


def test_b3_the_destroyed_components_are_the_clones():
    _check(_p3,
           lambda s: _replace(s, PP, "var quit = clone.GetComponent<QuitButton>();", "var quit = template.GetComponent<QuitButton>();"),
           _control_comment(PP, PLACE))


def test_b4_a_room_ends_the_poll():
    _check(_p4,
           lambda s: _replace(s, PP, "                if (IsOpen) Close();\n                return;\n", "                if (IsOpen) Close();\n"),
           _control_comment(PP, TRY))


def test_b5_the_row_guard_is_not_reversed():
    _check(_p5,
           lambda s: _replace(s, PP, "if (!ClickGuard.Claim(this)) return;", "if (ClickGuard.Claim(this)) return;"),
           _control_comment(PP, ONCLICK, within=ROW_BUTTON))


def test_b6_the_picker_canvas_keeps_its_raycaster():
    _check(_p6,
           lambda s: _replace(s, PP, "            if (UIFactory.tGR != null) canvasGO.AddComponent(UIFactory.tGR);\n", ""),
           _control_comment(PP, ENSURE))


def test_b7_no_raycaster_outside_the_picker_canvas():
    _check(_p7,
           lambda s: _replace(s, PP, "            var container = template.transform.parent;\n",
                              "            var container = template.transform.parent;\n"
                              "            container.gameObject.AddComponent(UIFactory.tGR);\n"),
           _control_comment(PP, PLACE))


def test_b8_no_config_assignment_however_spaced():
    _check(_p8,
           lambda s: _replace(s, PP, '            if (!WriteGateOpen("nomination")) { Close(); return; }\n',
                              '            if (!WriteGateOpen("nomination")) { Close(); return; }\n'
                              '            Plugin.AvatarModdedPreset.Value=slot;\n'),
           _control_comment(PP, APPLY))


def test_b9_no_slot_is_skipped_inside_the_loop():
    _check(_p9,
           lambda s: _insert_after_open(s, PP, "for (int s = 0; s < AvatarPickerRules.Tiles; s++)",
                                        "                if (s == 7) continue;", within=REBUILD),
           _control_comment(PP, REBUILD))


def test_b10_each_part_is_composed_once():
    _check(_p10,
           lambda s: _replace(s, PP, "AddPart(parts, loader, face.detail2ID, CharacterItemType.Detail, face.detail2Offset);",
                              "AddPart(parts, loader, face.detailID, CharacterItemType.Detail, face.detailOffset);"),
           _control_comment(PP, COMPOSE))


def test_b11_the_horizontal_pivot_term_stays():
    _check(_p11,
           lambda s: _replace(s, RL, "x = (itemOffX + faceOffX) * k + (0.5f - pivotFracX) * w;", "x = (itemOffX + faceOffX) * k;"),
           _control_comment(RL, PART_RECT))


def test_b12_no_raw_literal_reaches_set_text_raw():
    _check(_p12,
           lambda s: _replace(s, PP, READOUT_LINE, READOUT_LINE + '\n            UIFactory.SetTextRaw(modded, "Presets");'),
           _control_comment(PP, REBUILD))


def test_b15_the_poll_is_not_nested_away():
    _check(_p15,
           lambda s: _replace(s, PL, "try { AvatarPresetPicker.TryPlaceRow(); } catch { }",
                              "if (false) { try { AvatarPresetPicker.TryPlaceRow(); } catch { } }"),
           lambda s: _replace(s, PL, "// Ask 5: the AVATAR PRESETS row under the mod's row (AvatarPresetPicker.cs).",
                              "// control: the AVATAR PRESETS row under the mod's row (AvatarPresetPicker.cs)."))


def test_b16_a_commented_registration_reads_red():
    _check(_p16,
           lambda s: _replace(s, MAIN, 'RunSuite("avatarpicker"', '/* RunSuite("avatarpicker" */'),
           lambda s: _replace(s, MAIN, "// Ask 5 (avatar presets in the main menu): the picker's tile",
                              "// control (avatar presets in the main menu): the picker's tile"))


# -- the round-2 table: the P17 to P22 blind spots and the RowLabel split --------------------

ROW_LABEL = "private static string RowLabel()"


def test_b17_the_raw_click_block_has_one_writer():
    _check(_p18,
           lambda s: _replace(s, CU, "            ClickHandler.ModalBlockInput = KeyboardInputOwnedByModal || Keybinds.CaptureOwnsInput;\n",
                              "            ClickHandler.ModalBlockInput = KeyboardInputOwnedByModal || Keybinds.CaptureOwnsInput;\n"
                              "            ClickHandler.ModalBlockInput = false;\n"),
           lambda s: _replace(s, CU, "// Ask 5 (Codex r1 H2): the avatar-preset picker", "// control: the avatar-preset picker"))


def test_b18_nothing_runs_in_open_before_the_yield():
    _check(_p19,
           lambda s: _insert_after_open(s, PP, OPEN, "            if (canvasGO != null) canvasGO.SetActive(true);"),
           _control_comment(PP, OPEN, indent="                "))


def test_b19_resolve_camera_takes_no_type_either():
    _check(_p20,
           lambda s: _insert_after_open(s, NU, RESOLVE, "var tt=cc.GetType();"),
           _control_comment(NU, RESOLVE))


def test_b20_try_wire_adds_the_listener_it_reports():
    _check(_p21,
           lambda s: _replace(s, PP, "                add.Invoke(onClick, new object[] { action });\n", ""),
           _control_comment(PP, TRY_WIRE, within=ROW_BUTTON))


def test_b21_the_row_shows_the_label_it_caches():
    _check(_p22,
           lambda s: _replace(s, PP, "                if ((textProp.GetValue(tmp) as string) != label) textProp.SetValue(tmp, label);\n", ""),
           _control_comment(PP, LATE, within=ROW_BUTTON))


def test_b22_the_row_label_is_the_whole_key():
    _check(_p22,
           lambda s: _replace(s, PP, 'return I18n.Tr("AVATAR PRESETS");', 'return I18n.Tr("AVATAR " + "PRESETS");'),
           _control_comment(PP, ROW_LABEL, within=ROW_BUTTON))
