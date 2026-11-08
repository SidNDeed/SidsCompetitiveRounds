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


def test_p4_the_precondition_and_the_room_cost_no_retry():
    _check(_p4,
           lambda s: _replace(s, PP, "if (anchor == null) return;", "if (anchor == null) { }"),
           _control_comment(PP, TRY))


# -- P5 every click behind ClickGuard -------------------------------------------

def _p5(src):
    b = _body(src[PP], ONCLICK, within=ROW_BUTTON)
    assert "ClickGuard.Claim(this)" in b, "the row's click is not behind ClickGuard"
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
                 "x = (itemOffX + faceOffX) * k", "y = (itemOffY + faceOffY) * k"):
        assert term in b, "the SpawnItem term %r is gone" % term
    pp = src[PP]
    for sig, within in (("private void Update()", ESC), ("private void LateUpdate()", ROW_BUTTON)):
        u = _body(pp, sig, within=within)
        for bad in PER_FRAME_BAD:
            assert bad not in u, "%s does %s per frame" % (sig, bad)
    t = _body(pp, TRY)
    for bad in ("Rebuild(", "Compose(", "GetItem("):
        assert bad not in t, "the row poll does %s" % bad
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
    k = code.index("MainMenuInjector.Reset();")
    l = code.index("AvatarPresetPicker.Reset();")
    assert 0 < l - k < 200, "the picker's reset does not sit beside the injector's"


def test_p15_the_poll_and_the_reset_sit_beside_the_injectors():
    _check(_p15,
           lambda s: _replace(s, PL, "try { AvatarPresetPicker.TryPlaceRow(); } catch { }", ""),
           lambda s: _replace(s, PL, "try { MainMenuInjector.TryInject(); } catch { }",
                              "try { MainMenuInjector.TryInject(); } catch { } // control"))


def _p16(src):
    m = src[MAIN]
    assert 'RunSuite("avatarpicker"' in m and "AvatarPickerRules.SelfTest()" in m, "the suite is not registered"
    c = src[CSPROJ]
    assert '<Compile Include="../../plugin/AvatarPickerRules.cs" />' in c, "the harness does not compile the rules"
    assert '<Compile Include="AvatarPickerRulesSelfTest.cs" />' in c, "the harness does not compile the self-test"
    st = _code(src[SELFTEST])
    assert st.count("Check(r, ") == 12, "the suite does not have twelve cases"
    assert '"PASS" : "FAIL"' in st and '" | got="' in st, "a case prints no verdict or no measurement"


def test_p16_the_harness_runs_the_suite():
    _check(_p16,
           lambda s: _replace(s, MAIN, 'RunSuite("avatarpicker"', 'RunSuite("avatarpickr"'),
           lambda s: _replace(s, MAIN, 'RunSuite("avatarpicker"', 'RunSuite("avatarpicker" /* control */'))
