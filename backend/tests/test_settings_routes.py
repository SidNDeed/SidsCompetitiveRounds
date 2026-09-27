"""Item 13 round 2, R2: a player-facing route into the settings page names a
settings sub-tab.

The settings page is seven sub-tabs (SubTabLabelTr in
plugin/SettingsDescriptors.g.cs), so the step a route takes after "Settings"
is a sub-tab label. Round 1 left the consent dialog pointing at
"F5 -> Settings -> Revoke", a button the reorganised page no longer has, and
two sibling routes (the dialog's delete line, the Home tab's appear-offline
hint) skipping the sub-tab.

Gates, over the FRESH extraction (tools/i18n_extract.py executed in-process
on plugin/, i.e. every string the game can show, not a registry that may be
stale):
1. every "Settings" followed by an arrow (the Unicode arrow or "->") is
   followed by a current sub-tab label;
2. neither scan is vacuous: the sub-tab table parses to its seven labels and
   the route scan finds the three known routes.

route_problems(repo) takes the tree root, so a mutation run can point it at a
scratch copy of plugin/ and tools/.
"""
import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

ARR = chr(0x2192)      # the arrow the consent dialog's routes use
ARROW = "(?:" + ARR + "|->)"
# the step after "Settings <arrow>": up to the next arrow, bracket or
# sentence punctuation
ROUTE = re.compile(r"\bSettings\s*" + ARROW + r"\s*([^()\n.,;:" + ARR + r"]+?)\s*(?=" + ARROW
                   + r"|[()\n.,;:]|$)")
CASE = re.compile(r'case "(\w+)": return I18n\.Tr\("([^"]+)"\);')


def subtab_labels(repo=REPO):
    src = (Path(repo) / "plugin" / "SettingsDescriptors.g.cs").read_text(encoding="utf-8")
    start = src.index("SubTabLabelTr(")
    end = src.index("default:", start)
    return dict(CASE.findall(src[start:end]))


def extracted_strings(repo=REPO):
    path = Path(repo) / "tools" / "i18n_extract.py"
    spec = importlib.util.spec_from_file_location("i18n_extract_for_routes", str(path))
    ix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ix)
    found, _sites = ix.extract()
    return set(found)


def route_problems(repo=REPO):
    labels = set(subtab_labels(repo).values())
    routes, bad = [], []
    for s in sorted(extracted_strings(repo)):
        for m in ROUTE.finditer(s):
            step = m.group(1).strip()
            routes.append((step, s))
            if step not in labels:
                ctx = s[max(0, m.start() - 30):m.end() + 12].replace("\n", " ")
                bad.append("route step %r is not a settings sub-tab (%s): ...%s..."
                           % (step, ", ".join(sorted(labels)), ctx.encode("ascii", "backslashreplace").decode()))
    return routes, bad


def test_subtab_table_parses_to_seven_labels():
    labels = subtab_labels()
    assert len(labels) == 7, labels
    assert "Privacy & account" in labels.values(), labels


def test_every_settings_route_names_a_subtab():
    routes, bad = route_problems()
    # the consent dialog's revoke and delete lines and the Home hint
    assert len(routes) >= 3, routes
    assert not bad, "\n".join(bad)
