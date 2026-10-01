"""Item 12 follow-up (2026-09-23): the title ladders left their own
Shop-group sub-tab and became entries of the Shop's Titles section, with a
Buy button that becomes Upgrade; since the five-tier build (board row 29) a
click opens the ladder's tiers in a dropdown under the entry.

The DECISIONS (which lines render, which listing rows they replace, which
tier is held, what the button says and why) are executed by the client rules
harness -- see test_client_rules_harness.py's laddershop suite. This file
gates the WIRING the harness cannot run: the tab table that must not shift,
where RefreshShop plans and paints the ladders, where the dropdown sits and
how it closes, and that the purchase statement is the Shop row's own.

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


def _flat(text):
    return " ".join(text.split())


# ── L3: the dropdown (five-tier build, board row 29) ────────────────────
#
# The tier popup became a dropdown UNDER the clicked entry, inside the Shop's
# own list: no backdrop, no overlay child, nothing that owns input. The gate
# is one function that lists problems; the positive test asserts none and
# each mutation below must produce at least one (#391).

PAINT = "internal static int PaintShopEntries(bool show, int sibling, int? balance)"
ENTRY_PLACED = "e.root.transform.SetSiblingIndex(sibling++);"
DROP_PLACED = "drop.transform.SetSiblingIndex(sibling++);"


def _dropdown_problems(cui_src, tlu_src, nat_src):
    problems = []
    if "TitleLaddersUI" in code_of(cui_src):
        problems.append("CompetitiveUI still names TitleLaddersUI (a modal term or a shield)")
    code = code_of(tlu_src)
    if "EventSystem" in tlu_src:
        problems.append("TitleLaddersUI names the EventSystem")
    for banned in ("tCanvas", "GraphicRaycaster", "sortingOrder", "mainMenuGroup",
                   "OverlayRoot", "bypassModalBlock", "PopupOpen", "Shield", "Event.current"):
        if banned in code:
            problems.append("TitleLaddersUI carries %r" % banned)

    paint = _flat(code_of(tlu_src, PAINT))
    if paint.count(DROP_PLACED) != 1:
        problems.append("the dropdown is not placed exactly once")
    elif paint.count(ENTRY_PLACED) != 1:
        problems.append("an entry is not placed exactly once")
    else:
        e = paint.index(ENTRY_PLACED)
        d = paint.index(DROP_PLACED)
        between = paint[e:d]
        if not e < d:
            problems.append("the dropdown is placed before its entry")
        elif "if (drop != null && ln.line == openLine)" not in between or "PaintEntry(e, ln);" not in between:
            problems.append("the dropdown does not follow the OPEN entry: %r" % between)
        elif "for (" in between or "continue;" in between:
            problems.append("the dropdown is placed outside the entry's own pass")
    if "if (drop != null && !dropPlaced) drop.SetActive(false);" not in paint:
        problems.append("a dropdown not placed this paint stays visible")
    if "openLine = null;" not in paint:
        problems.append("a ladder that left the answer keeps its dropdown")

    toggle = _flat(code_of(tlu_src, "private static void ToggleDropdown(string lineId)"))
    if "openLine = openLine == lineId ? null : lineId;" not in toggle:
        problems.append("a click does not toggle one open ladder")
    build = _flat(code_of(tlu_src, "private static Entry BuildEntry(Transform parent, int idx)"))
    if "ToggleDropdown(e.line);" not in build:
        problems.append("a press on the row does not toggle its dropdown")
    drop = _flat(code_of(tlu_src, "private static void PaintDrop(ApiClient.TitleLadderLine ln)"))
    if "UIFactory.SetPrefH(drop," not in drop or "shown * DROP_ROW" not in drop:
        problems.append("the dropdown's height does not follow the tiers it shows")

    teardown = code_of(nat_src, "private static void TeardownOverlaySurfaces()")
    if "TitleLaddersUI.CollapseDropdown()" not in teardown:
        problems.append("a page close leaves the dropdown open (#369)")
    switch = code_of(nat_src, "private static void SwitchTab(int idx)")
    if "TitleLaddersUI.CollapseDropdown()" not in switch[:switch.index("currentTab=idx;")]:
        problems.append("leaving the tab leaves the dropdown open")
    return problems


def test_the_dropdown_opens_under_its_entry_and_is_not_a_modal():
    problems = _dropdown_problems(_plugin("CompetitiveUI.cs"), _plugin("TitleLaddersUI.cs"),
                                  _plugin("NativeUI.cs"))
    assert not problems, problems


DROPDOWN_MUTATIONS = [
    ("a modal term comes back", "cui",
     [("            // (The title ladders' tier popup was a term here until the\n",
       "            || TitleLaddersUI.PopupOpen\n"
       "            // (The title ladders' tier popup was a term here until the\n")]),
    ("an overlay parent", "tlu",
     [("drop = UIFactory.CreatePanel(\"TLDrop\", parent, C_DROP);",
       "drop = UIFactory.CreatePanel(\"TLDrop\", NativeUI.OverlayRoot, C_DROP);")]),
    ("the dropdown placed ahead of the entries", "tlu",
     [("                    if (drop != null && ln.line == openLine)\n"
       "                    {\n"
       "                        drop.SetActive(true);\n"
       "                        drop.transform.SetSiblingIndex(sibling++);\n"
       "                        PaintDrop(ln);\n"
       "                        dropPlaced = true;\n"
       "                    }\n", ""),
      ("                if (openLine != null && (!show",
       "                if (drop != null) drop.transform.SetSiblingIndex(sibling++);\n"
       "                if (openLine != null && (!show")]),
    ("the dropdown under every entry", "tlu",
     [("if (drop != null && ln.line == openLine)", "if (drop != null)")]),
    ("an unplaced dropdown kept visible", "tlu",
     [("if (drop != null && !dropPlaced) drop.SetActive(false);", "")]),
    ("a second click does not close", "tlu",
     [("openLine = openLine == lineId ? null : lineId;", "openLine = lineId;")]),
    ("a fixed height", "tlu",
     [("+ shown * DROP_ROW + 4 * DROP_GAP", "+ MAX_RUNGS * DROP_ROW + 4 * DROP_GAP")]),
    ("the close paths forget it", "nat",
     [("try{TitleLaddersUI.CollapseDropdown();}catch{}/* Five-tier", "try{}catch{}/* Five-tier")]),
]


@pytest.mark.parametrize("name,which,edits", DROPDOWN_MUTATIONS, ids=[m[0] for m in DROPDOWN_MUTATIONS])
def test_the_dropdown_gate_can_fail(name, which, edits):
    srcs = {"cui": _plugin("CompetitiveUI.cs"), "tlu": _plugin("TitleLaddersUI.cs"),
            "nat": _plugin("NativeUI.cs")}
    for old, new in edits:
        nl = "\r\n" if "\r\n" in srcs[which] else "\n"
        old = old.replace("\n", nl)
        new = new.replace("\n", nl)
        assert srcs[which].count(old) == 1, (name, old)
        srcs[which] = srcs[which].replace(old, new, 1)
    assert _dropdown_problems(srcs["cui"], srcs["tlu"], srcs["nat"]), name


def test_the_shop_entered_fetch_and_the_section_row_count_include_the_dropdown():
    nat = _plugin("NativeUI.cs")
    switch = code_of(nat, "private static void SwitchTab(int idx)")
    shop = switch[switch.index("if(idx==4){"):]
    shop = shop[:shop.index("}if(idx==6)")]
    assert "TitleLaddersUI.OnShopEntered();" in shop
    rows = _flat(code_of(_plugin("TitleLaddersUI.cs"), "internal static int ShopSectionRows"))
    # the sub-header, one row per entry and the open dropdown
    assert "if (n > 0) return n + 1 + (openLine != null ? 1 : 0);" in rows, rows


def test_the_lever_opens_and_closes_and_clicks_nothing():
    """The in-game witness drives the dropdown through the broadcast lever
    (see test_a_local_board_never_buys_or_wears for who can call it). The
    lever opens, closes and swaps boards; it never buys or wears."""
    src = _plugin("TitleLaddersUI.cs")
    directive = code_of(src, "internal static void DevDirective(string directive)")
    for verb in ('verb == "fixture"', 'verb == "ladder"', 'verb == "close"', 'verb == "live"'):
        assert verb in directive, verb
    assert "shield" not in directive.lower()
    for banned in ("PurchaseItem", "SetActiveTitle", "OnActionClicked", "OnWearClicked", "Invoke("):
        assert banned not in directive, banned
    opened = code_of(src, "private static void OpenDropdown(string lineId)")
    assert "ToggleDropdown(lineId)" in opened and "if (openLine != lineId)" in opened


# ── L4: the button ───────────────────────────────────────────────────────

def test_the_button_decides_at_click_time_and_buys_only_what_the_decision_names():
    body = code_of(_plugin("TitleLaddersUI.cs"),
                   "private static void OnActionClicked(string lineId)")
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
    label = code_of(src, "private static string ActionLabel(TitleLadderRules.Decision d)")
    for key in ('I18n.Tr("Maxed")', 'I18n.Tr("Upgrade")', 'I18n.Tr("Buy")'):
        assert key in label, key
    # Every disabled reason the rules can return has words on the surface.
    rules = code_of(_plugin("TitleLadderRules.cs"))
    enum = re.search(r"internal enum Reason\s*\{(.*?)\}", rules, re.S).group(1)
    members = set(re.findall(r"\b([A-Z]\w*)\b", enum)) - {"None"}
    assert len(members) >= 6, members
    reasons = code_of(src, "private static string ReasonText(TitleLadderRules.Decision d, string unit)")
    missing = sorted(m for m in members if "TitleLadderRules.Reason.%s:" % m not in reasons)
    assert not missing, "reasons with no text: %r" % missing


def test_the_entry_row_yields_only_to_an_enabled_button():
    """#540: the row and its button are raw-poll handlers on one mouse-down.
    An ENABLED button is what the player aimed at; a disabled one claims
    nothing, so the press opens the dropdown that says why."""
    build = code_of(_plugin("TitleLaddersUI.cs"), "private static Entry BuildEntry(Transform parent, int idx)")
    assert "if (e.enabled && NativeUI.PointerOverActive(e.btn)) return;" in build
    assert "ToggleDropdown(e.line);" in build
    assert "OnActionClicked(e.line)" in build


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
    "Current tier", "Current tier: {0} - {1}", "In use",
    "Locked", "Maxed", "Next tier", "No tiers listed", "Not enough gold",
    "Not on sale yet", "Owned", "Shop still loading", "Tier {0}", "Upgrade",
    "{0} tiers - click to see them all",
    # the five-tier dropdown (board row 29)
    "Title Ladders", "click to close", "Top of the ladder.", "Earned at {0}",
    "{0} games", "{0} wins", "{0} losses", "{0} gold", "{0} wins in a row",
    "{0} series", "Wear it and finish ranked series",
    "(only the ladder you are wearing counts)",
    "Not started - buy {0} in the Shop to begin this ladder.", "Not started.",
    "{0} - top of the ladder.", "Current run: {0}", "Best run: {0}",
    "{0} of {1} - {2} to go.", "{0} of {1} to {2} - {3} to go.",
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
