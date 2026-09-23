"""Item 12 follow-up (2026-09-23): the animal title ladders left their own
Shop-group sub-tab and became entries of the Shop's Titles section, with a
tier popup on click and a Buy button that becomes Upgrade.

The DECISIONS (which lines render, which listing rows they replace, which
tier is held, what the button says and why) are executed by the client rules
harness -- see test_client_rules_harness.py's laddershop suite. This file
gates the WIRING the harness cannot run: the tab table that must not shift,
where RefreshShop plans and paints the ladders, how the popup is torn down
and owns input, and that the purchase statement is the Shop row's own.

Every table gate here carries an in-memory mutation of the real source that
it must catch, so a parser that stops seeing the table reds instead of
passing over nothing (#391).
"""
import io
import os
import re

import pytest

from _cs_structure import code_of, strip_comments_only

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
LOCALES = ("es", "ru", "uk", "sv")


def _plugin(name):
    with io.open(os.path.join(REPO, "plugin", name), encoding="utf-8") as fh:
        return fh.read()


# ── L1: the Titles sub-tab is gone and no other tab moved ────────────────

# The table as it stood at 5423e08 minus index 19 (Titles), which was the
# LAST index -- so removing it shifts nothing.
EXPECTED_TABS = ["My Stats", "Leaderboard", "Card Stats", "Achievements", "Shop",
                 "Settings", "Admin", "Tournaments", "2v2", "Compare", "Artist",
                 "1v2", "FFA", "Home", "Banned", "Info", "Music", "Mail",
                 "Collection"]
EXPECTED_CONSTS = {"TAB_HOME": 13, "TAB_BANNED": 14, "TAB_INFO": 15,
                   "TAB_SETTINGS": 5, "TAB_COLLECTION": 18, "TAB_MAIL": 17}
EXPECTED_GROUPS = [[13], [0, 2, 3], [1, 9], [7], [8, 11, 12], [4, 10, 18],
                   [6, 14], [5, 15]]


def _tab_table(src):
    code = strip_comments_only(src)
    m = re.search(r"TAB_NAMES\s*=>\s*new\[\]\{(.*?)\};", code, re.S)
    names = re.findall(r'I18n\.Tr\("([^"]*)"\)', m.group(1)) if m else None
    n = re.search(r"const int NUM_TABS\s*=\s*(\d+)", code)
    consts = {k: int(v) for k, v in
              re.findall(r"const int (TAB_[A-Z_]+)\s*=\s*(\d+)", code)}
    g = re.search(r"GROUP_MEMBERS\s*=\s*\{(.*?)\};", code, re.S)
    groups = ([[int(x) for x in re.findall(r"\d+", grp)]
               for grp in re.findall(r"new\[\]\{([^}]*)\}", g.group(1))]
              if g else None)
    return names, (int(n.group(1)) if n else None), consts, groups


def _table_problems(src):
    names, num, consts, groups = _tab_table(src)
    bad = []
    if names != EXPECTED_TABS:
        bad.append(("TAB_NAMES", names))
    if num != len(EXPECTED_TABS):
        bad.append(("NUM_TABS", num))
    if consts != EXPECTED_CONSTS:
        bad.append(("TAB_* constants", consts))
    if groups != EXPECTED_GROUPS:
        bad.append(("GROUP_MEMBERS", groups))
    return bad


def test_every_tab_keeps_its_index_and_its_name():
    assert _table_problems(_plugin("NativeUI.cs")) == []


@pytest.mark.parametrize("old, new", [
    # the Titles tab comes back
    ('I18n.Tr("Collection")};', 'I18n.Tr("Collection"),I18n.Tr("Titles")};'),
    # a tab is inserted mid-list, shifting every later index
    ('I18n.Tr("Shop"),I18n.Tr("Settings")', 'I18n.Tr("Shop"),I18n.Tr("Titles"),I18n.Tr("Settings")'),
    # the count drifts from the names
    ("NUM_TABS=19;", "NUM_TABS=20;"),
    # the Shop group regains the removed member
    ("new[]{4,10,18}", "new[]{4,10,18,19}"),
    # a named index moves
    ("TAB_COLLECTION=18;", "TAB_COLLECTION=19;"),
])
def test_the_tab_table_gate_can_fail(old, new):
    """Negative controls: each mutation of the REAL source must be seen."""
    src = _plugin("NativeUI.cs")
    assert src.count(old) == 1, "the control no longer matches the source: %r" % old
    assert _table_problems(src.replace(old, new)) != [], (
        "the tab table gate passed a source with %r -> %r" % (old, new))


def test_the_titles_tab_and_its_deep_link_left_every_file():
    """The tab name, its anchor, its panel, its fetch, its repaint and the
    'buy it in the Shop' deep-link (both directions) retire together."""
    gone = ("TAB_TITLES", "TAB_SHOP", "BuildTitlesTab", "SwitchToShopTab",
            "SHTlLink", "TitleLaddersUI.BuildInto", "TitleLaddersUI.OnTabEntered",
            "TitleLaddersUI.Refresh(")
    plugin_dir = os.path.join(REPO, "plugin")
    for name in sorted(os.listdir(plugin_dir)):
        if not name.endswith(".cs"):
            continue
        code = code_of(_plugin(name))
        for g in gone:
            assert g not in code, "%s still carries %s" % (name, g)


# ── L2: every ladder once, in the Titles section ─────────────────────────

REFRESH_SHOP = "private static void RefreshShop()"


def _section_order_ok(body):
    try:
        plan = body.index("TitleLaddersUI.PlanShopSection()")
        fold = body.index("titles.RemoveAll(")
        header = body.index("shopTitlesHeader.SetActive(true)")
        paint = body.index("TitleLaddersUI.PaintShopEntries(")
        loop = body.index("for (int i = 0; i < titles.Count")
    except ValueError:
        return False
    return plan < fold < header < paint < loop


def test_the_ladders_are_planned_before_the_header_and_painted_before_the_titles():
    """The fold must precede the header decision (a section holding only
    ladders still gets its header, and a folded rung is not also drawn as an
    ordinary row), and the entries go between the header and the ordinary
    titles -- once each."""
    body = code_of(_plugin("NativeUI.cs"), REFRESH_SHOP)
    assert _section_order_ok(body), body[:2000]
    assert body.count("TitleLaddersUI.PlanShopSection()") == 1
    assert body.count("TitleLaddersUI.PaintShopEntries(") == 1
    assert body.count("titles.RemoveAll(") == 1
    assert "if ((titles.Count > 0 || ladderRows > 0) && shopTitlesHeader != null)" in body
    # All and Titles are the two filters that show the Titles section.
    assert "bool showLadders = shopCategoryFilter == 0 || shopCategoryFilter == 4;" in body


def test_the_section_order_gate_can_fail():
    body = code_of(_plugin("NativeUI.cs"), REFRESH_SHOP)
    fold = re.search(r"titles\.RemoveAll\([^;]*;", body).group(0)
    moved = body.replace(fold, "", 1)
    anchor = "else if (shopTitlesHeader != null) shopTitlesHeader.SetActive(false);"
    assert moved.count(anchor) == 1
    moved = moved.replace(anchor, anchor + fold, 1)
    assert not _section_order_ok(moved), "a fold AFTER the header decision passed"


def test_the_entries_are_built_into_the_shop_rows_container_once():
    build = code_of(_plugin("NativeUI.cs"), "private static GameObject BuildShopTab(Transform parent)")
    assert build.count("TitleLaddersUI.BuildShopEntries(shopRowsContainer.transform)") == 1
    pool = build.index("shopRows.Add(CreateShopRow(")
    assert build.index("TitleLaddersUI.BuildShopEntries(") > pool


# ── L3: the popup ────────────────────────────────────────────────────────

def test_the_popup_closes_on_every_close_path_and_on_leaving_the_tab():
    nat = _plugin("NativeUI.cs")
    teardown = code_of(nat, "private static void TeardownOverlaySurfaces()")
    assert "TitleLaddersUI.HidePopup()" in teardown, (
        "the popup is a persistent-overlay child; every close and recovery "
        "path goes through TeardownOverlaySurfaces (#369)")
    switch = code_of(nat, "private static void SwitchTab(int idx)")
    leaving = switch[:switch.index("currentTab=idx;")]
    assert "TitleLaddersUI.HidePopup()" in leaving
    shop = switch[switch.index("if(idx==4){"):]
    shop = shop[:shop.index("}if(idx==6)")]
    assert "TitleLaddersUI.OnShopEntered();" in shop


def test_the_popup_owns_input_while_it_is_open():
    cui = code_of(_plugin("CompetitiveUI.cs"))
    for prop in ("internal static bool OtherModalOwnsInput =>",
                 "internal static bool PopupCoversPage =>"):
        i = cui.index(prop)
        expr = cui[i:cui.index(";", i)]
        assert "TitleLaddersUI.PopupOpen" in expr, prop


def test_the_popup_creates_no_canvas_and_never_touches_the_event_system():
    src = _plugin("TitleLaddersUI.cs")
    assert "EventSystem" not in src
    code = code_of(src)
    for banned in ("tCanvas", "GraphicRaycaster", "sortingOrder", "mainMenuGroup"):
        assert banned not in code, banned
    opened = code_of(src, "private static void OpenPopup(string lineId)")
    assert "NativeUI.OverlayRoot" in opened
    assert "bdClick.bypassModalBlock = true;" in opened
    assert "NativeUI.MarkPopupChildrenInteractive(popupGO);" in opened
    # a press on the box is not a backdrop click, and neither is the opening press
    assert "NativeUI.PointerOverActive(popupBox)" in opened
    assert "Time.frameCount == popupFrame" in opened
    hide = code_of(src, "internal static void HidePopup()")
    assert hide.index("go.SetActive(false)") < hide.index("Destroy(go)"), (
        "Destroy is deferred to the end of the frame; the popup must be "
        "inactive first so its raw-poll Buy cannot fire (#369 rule b)")
    assert "popupGO = null;" in hide


# ── r2 (Codex r1 M1): the popup's IMGUI event shield ─────────────────────
#
# The click-blocking rule is an IMGUI backdrop plus Event.Use. The popup is
# uGUI, so its IMGUI half is TitleLaddersUI.ShieldImguiEvents:
#   * DrawUI calls it before any draw that can take a click;
#   * it uses pointer events exactly as TitleLadderRules.Shield decides (the
#     harness's laddershop suite executes that decision);
#   * every close arms it for the rest of the closing frame, whose IMGUI pass
#     runs after the close;
#   * a click's close runs in LateUpdate, so the pressing frame's uGUI pass
#     still finds the popup whichever Update runs first.
# The gate is one function that lists problems. The positive test asserts
# none, and each mutation below must produce at least one (#391).

SHIELD_CALL = "TitleLaddersUI.ShieldImguiEvents(Event.current, ImguiModalAbovePopups);"
DRAW_UI = "public static void DrawUI()"
POINTER_KINDS = {"MouseDown": "Press", "MouseUp": "Release", "MouseDrag": "Drag",
                 "ScrollWheel": "Scroll", "ContextClick": "Context"}


def _flat(text):
    return " ".join(text.split())


def _shield_problems(cui_src, tlu_src):
    problems = []

    draw = code_of(cui_src, DRAW_UI)
    if draw.count(SHIELD_CALL) != 1:
        problems.append("DrawUI does not call the shield exactly once")
    else:
        before = draw[draw.index("{") + 1:draw.index(SHIELD_CALL)]
        if _flat(before) != "TickChatLockWatchdog();":
            problems.append("DrawUI runs more than the watchdog before the shield: %r" % _flat(before))
    cui = code_of(cui_src)
    i = cui.find("internal static bool ImguiModalAbovePopups =>")
    if i < 0:
        problems.append("no ImguiModalAbovePopups")
    else:
        expr = _flat(cui[i:cui.index(";", i)])
        if expr != "internal static bool ImguiModalAbovePopups => BackdroplessModalOpen || !Plugin.DataConsentAsked":
            problems.append("the modal-above set changed: %r" % expr)

    shield = _flat(code_of(tlu_src, "internal static void ShieldImguiEvents(Event ev, bool modalAbove)"))
    for need in ("if (input == TitleLadderRules.ShieldInput.Other) return;",
                 "if (popupGO != null) CaptureShieldExtent();",
                 "var v = TitleLadderRules.Shield(input, ev.button, inside, popupGO != null, "
                 "Time.frameCount == shieldClosedFrame, modalAbove, shieldLatch);",
                 "shieldLatch = v.Latch;",
                 "if (v.Consume) ev.Use();"):
        if need not in shield:
            problems.append("ShieldImguiEvents lacks %r" % need)
    if shield.count(".Use()") != 1:
        problems.append("ShieldImguiEvents uses an event the rules did not decide")

    kinds = _flat(code_of(tlu_src, "private static TitleLadderRules.ShieldInput ShieldInputOf(EventType t)"))
    for ev, kind in sorted(POINTER_KINDS.items()):
        if "case EventType.%s: return TitleLadderRules.ShieldInput.%s;" % (ev, kind) not in kinds:
            problems.append("the shield does not read %s as %s" % (ev, kind))
    if "default: return TitleLadderRules.ShieldInput.Other;" not in kinds:
        problems.append("an unlisted event is not Other")
    if kinds.count("case EventType.") != len(POINTER_KINDS):
        problems.append("the shield reads an event type that is not pointer input")

    hide = code_of(tlu_src, "internal static void HidePopup()")
    release = hide.index("popupGO = null;")
    for need in ("CaptureShieldExtent();", "shieldClosedFrame = Time.frameCount;"):
        if need not in hide:
            problems.append("HidePopup lacks %r" % need)
        elif hide.index(need) > release:
            problems.append("HidePopup runs %r after releasing the popup" % need)

    opened = _flat(code_of(tlu_src, "private static void OpenPopup(string lineId)"))
    for need in ("popupGO.AddComponent<PopupLateClose>();",
                 "if (ClickGuard.Claim(bd)) RequestClose();",
                 "() => { if (Time.frameCount != popupFrame) RequestClose(); }"):
        if need not in opened:
            problems.append("OpenPopup lacks %r" % need)
    if opened.count("HidePopup();") != 2:
        problems.append("OpenPopup closes directly outside its reset and its fault path")
    late = _flat(code_of(tlu_src, "private sealed class PopupLateClose : MonoBehaviour"))
    if "private void LateUpdate() { if (closeRequested && popupGO == gameObject) HidePopup(); }" not in late:
        problems.append("PopupLateClose does not run the requested close in LateUpdate")
    req = _flat(code_of(tlu_src, "private static void RequestClose()"))
    if "if (popupGO != null) closeRequested = true;" not in req:
        problems.append("RequestClose does not request")
    return problems


def test_the_popup_has_an_imgui_event_shield_first_in_the_pass():
    problems = _shield_problems(_plugin("CompetitiveUI.cs"), _plugin("TitleLaddersUI.cs"))
    assert not problems, problems


SHIELD_MUTATIONS = [
    ("no shield call", "cui", [(SHIELD_CALL, "")]),
    ("the shield after the spectator HUD", "cui",
     [(SHIELD_CALL, ""), ("SpectatorHud.Draw();", "SpectatorHud.Draw();" + SHIELD_CALL)]),
    ("a modal above loses the backdrop-less set", "cui",
     [("ImguiModalAbovePopups => BackdroplessModalOpen || !Plugin.DataConsentAsked",
       "ImguiModalAbovePopups => !Plugin.DataConsentAsked")]),
    ("the verdict is never applied", "tlu", [("if (v.Consume) ev.Use();", "")]),
    ("the closed frame is not passed", "tlu",
     [("Time.frameCount == shieldClosedFrame, modalAbove", "false, modalAbove")]),
    ("the latch is not kept", "tlu", [("shieldLatch = v.Latch;", "")]),
    ("Repaint read as pointer input", "tlu",
     [("case EventType.ContextClick:", "case EventType.Repaint: case EventType.ContextClick:")]),
    ("a close does not arm its frame", "tlu", [("shieldClosedFrame = Time.frameCount;", "")]),
    ("the extent captured after the release", "tlu",
     [("            CaptureShieldExtent();\n            shieldClosedFrame", "            shieldClosedFrame"),
      ("popupGO = null; popupBox = null;", "popupGO = null; CaptureShieldExtent(); popupBox = null;")]),
    ("the backdrop closes at once", "tlu",
     [("if (ClickGuard.Claim(bd)) RequestClose();", "if (ClickGuard.Claim(bd)) HidePopup();")]),
    ("the Close button closes at once", "tlu",
     [("if (Time.frameCount != popupFrame) RequestClose(); }", "if (Time.frameCount != popupFrame) HidePopup(); }")]),
    ("LateUpdate never closes", "tlu",
     [("if (closeRequested && popupGO == gameObject) HidePopup();", "")]),
]


@pytest.mark.parametrize("name,which,edits", SHIELD_MUTATIONS, ids=[m[0] for m in SHIELD_MUTATIONS])
def test_the_shield_gate_can_fail(name, which, edits):
    srcs = {"cui": _plugin("CompetitiveUI.cs"), "tlu": _plugin("TitleLaddersUI.cs")}
    for old, new in edits:
        assert srcs[which].count(old) == 1, (name, old)
        srcs[which] = srcs[which].replace(old, new, 1)
    assert _shield_problems(srcs["cui"], srcs["tlu"]), name


def test_the_shield_probe_is_a_broadcast_lever_that_clicks_nothing():
    """The in-game witness drives the shield with a synthetic event and only
    READS the other two paths. It never invokes a control, and only the
    lever (broadcast identity, see test_a_local_board_never_buys_or_wears)
    starts it."""
    src = _plugin("TitleLaddersUI.cs")
    probe = code_of(src, "private sealed class ShieldProbe : MonoBehaviour")
    for banned in ("PurchaseItem", "SetActiveTitle", "OnActionClicked", "OnWearClicked",
                   "onClick", "Invoke(", "HidePopup(", "OpenPopup("):
        assert banned not in probe, banned
    assert "ShieldImguiEvents(down, above);" in probe
    assert "RequestClose();" in probe
    assert "NativeUI.DevTopHit(sp)" in probe
    starts = [n for n in sorted(os.listdir(os.path.join(REPO, "plugin")))
              if n.endswith(".cs") and "AddComponent<ShieldProbe>()" in code_of(_plugin(n))]
    assert starts == ["TitleLaddersUI.cs"], starts
    directive = code_of(src, "internal static void DevDirective(string directive)")
    assert "probe = pgo.AddComponent<ShieldProbe>();" in directive
    # The read-only raycast: it sets and toggles nothing on the input system.
    gate = code_of(_plugin("OverlayInputGate.cs"), "internal static GameObject DevTopHit(Vector2 screenPoint)")
    for banned in ("SetValue(es", "SetSelected", "enabled", "SetActive"):
        assert banned not in gate, banned


# ── L4: the button ───────────────────────────────────────────────────────

def test_the_button_decides_at_click_time_and_buys_only_what_the_decision_names():
    body = code_of(_plugin("TitleLaddersUI.cs"),
                   "private static void OnActionClicked(string lineId, bool fromPopup)")
    order = [body.index(s) for s in (
        "DecideFor(",
        "if (!d.Enabled || string.IsNullOrEmpty(d.TargetSku))",
        "ln.rungs[i].sku == d.TargetSku",
        "if (devBoard != null)",
        "ApiClient.PurchaseItem(")]
    assert order == sorted(order), order
    assert body.count("ApiClient.PurchaseItem(") == 1


def test_every_painted_button_reads_its_label_and_state_from_the_rules():
    src = _plugin("TitleLaddersUI.cs")
    paint = code_of(src, "private static void PaintAction(GameObject btn, object txt, TitleLadderRules.Decision d)")
    assert "ActionLabel(d)" in paint
    assert "NativeUI.SetButtonInteractable(btn, d.Enabled)" in paint
    code = code_of(src)
    assert "PaintAction(e.btn, e.btnTxt, d);" in code
    assert "PaintAction(popupAction, popActionTxt, d);" in code
    label = code_of(src, "private static string ActionLabel(TitleLadderRules.Decision d)")
    for key in ('I18n.Tr("Maxed")', 'I18n.Tr("Upgrade")', 'I18n.Tr("Buy")'):
        assert key in label, key
    # Every disabled reason the rules can return has words on the surface.
    rules = code_of(_plugin("TitleLadderRules.cs"))
    enum = re.search(r"internal enum Reason\s*\{(.*?)\}", rules, re.S).group(1)
    members = set(re.findall(r"\b([A-Z]\w*)\b", enum)) - {"None"}
    assert len(members) >= 6, members
    reasons = code_of(src, "private static string ReasonText(TitleLadderRules.Decision d)")
    missing = sorted(m for m in members if "TitleLadderRules.Reason.%s:" % m not in reasons)
    assert not missing, "reasons with no text: %r" % missing


def test_the_entry_row_yields_only_to_an_enabled_button():
    """#540: the row and its button are raw-poll handlers on one mouse-down.
    An ENABLED button is what the player aimed at; a disabled one claims
    nothing, so the press opens the popup that says why."""
    build = code_of(_plugin("TitleLaddersUI.cs"), "private static Entry BuildEntry(Transform parent, int idx)")
    assert "if (e.enabled && NativeUI.PointerOverActive(e.btn)) return;" in build
    assert "OpenPopup(e.line);" in build
    assert "OnActionClicked(e.line, false)" in build


def test_a_local_board_never_buys_or_wears():
    src = _plugin("TitleLaddersUI.cs")
    wear = code_of(src, "private static void OnWearClicked(TierRow row)")
    assert wear.index("if (devBoard != null)") < wear.index("ApiClient.SetActiveTitle(")
    # ...and only the broadcast seat can load one.
    hits = []
    for name in sorted(os.listdir(os.path.join(REPO, "plugin"))):
        if name.endswith(".cs") and "TitleLaddersUI.DevDirective(" in code_of(_plugin(name)):
            hits.append(name)
    assert hits == ["Plugin.cs"], hits
    tick = code_of(_plugin("Plugin.cs"), "private void TickTestOpenTab()")
    first = tick[tick.index("{") + 1:].lstrip().split(";", 1)[0]
    assert "!BroadcastMode.IsBroadcastIdentity) return" in first, first


# ── L5: one purchase path ────────────────────────────────────────────────

def test_the_purchase_statement_is_the_shop_rows_byte_for_byte():
    shop = [l.strip() for l in _plugin("NativeUI.cs").splitlines()
            if "ApiClient.PurchaseItem(id, r.sku, pcb);" in l]
    ours = [l.strip() for l in _plugin("TitleLaddersUI.cs").splitlines()
            if "ApiClient.PurchaseItem(" in l]
    assert len(shop) == 1 and len(ours) == 1, (shop, ours)
    assert ours[0] == shop[0], (ours[0], shop[0])
    assert "expectedPrice" not in code_of(_plugin("TitleLaddersUI.cs"))


# ── L6: the new strings ──────────────────────────────────────────────────

NEW_KEYS = [
    "Current tier", "Current tier: {0} - {1}", "Earned at {0} series", "In use",
    "Locked", "Maxed", "Next tier", "No tiers listed", "Not enough gold",
    "Not on sale yet", "Owned", "Shop still loading", "Tier {0}", "Upgrade",
    "{0} tiers - click to see them all",
]


@pytest.mark.parametrize("lang", LOCALES)
def test_every_new_key_is_translated_in_every_catalogue(lang):
    from test_pc_sept12 import _bundled_catalogues
    catalogue = _bundled_catalogues()[lang]
    ui = _plugin("TitleLaddersUI.cs")
    bad = []
    for k in NEW_KEYS:
        if ('I18n.Tr("%s")' % k) not in ui and ('I18n.TrF("%s"' % k) not in ui:
            bad.append(("not used", k))
        v = catalogue.get(k)
        if not v or not v.strip():
            bad.append(("missing", k))
        elif v == k:
            bad.append(("english", k))
        elif sorted(re.findall(r"\{\d+\}", k)) != sorted(re.findall(r"\{\d+\}", v)):
            bad.append(("placeholders", k, v))
    assert not bad, bad


def test_the_rules_file_carries_no_translation_no_unity_and_no_real_sku():
    rules = _plugin("TitleLadderRules.cs")
    code = code_of(rules)
    assert "I18n" not in code
    assert "UnityEngine" not in code
    assert "title_ladder_" not in rules
    with io.open(os.path.join(REPO, "tools", "i18n_extract.py"), encoding="utf-8") as fh:
        assert '"TitleLadderRules.cs"' not in fh.read()
