"""Item 17 fix pass 1 F10: refreshing the production shop snapshot keeps
the two DanceWheel "{0}" templates.

tools/refresh_shop_strings.py builds the snapshot from a prod dump. The
server's two dance descriptions end with the fixed phrase " with the E
wheel."; the client renders them through the " with the {0} wheel."
template (plugin/NativeUI.Keybinds.cs KbShopItemDesc). The refresh must
register the template, never the legacy text, so the translated templates
survive the next extraction. Pure: a fake dump, no ssh.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TOOL = REPO / "tools" / "refresh_shop_strings.py"
SNAP = REPO / "tools" / "shop_strings.json"
KBUI = REPO / "plugin" / "NativeUI.Keybinds.cs"

HOP = "Hop to the beat, arms pumping. Play it between rounds"
SWAY = "Sway and wave to the crowd. Play it between rounds"


def _tool():
    spec = importlib.util.spec_from_file_location("refresh_shop_strings_f10", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["refresh_shop_strings_f10"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_f10_a_prod_dump_with_the_legacy_wheel_text_keeps_the_templates():
    t = _tool()
    items = [
        {"n": "Hop", "d": HOP + " with the E wheel."},
        {"n": "Sway", "d": SWAY + " with the E wheel."},
        {"n": "Hat", "d": "A hat. Wear it with the E key held."},
        {"n": "Blank", "d": ""},
    ]
    out = t.snapshot_strings(items)
    assert HOP + " with the {0} wheel." in out
    assert SWAY + " with the {0} wheel." in out
    assert not any(s.endswith(" with the E wheel.") for s in out), out
    # only the exact suffix is rewritten
    assert "A hat. Wear it with the E key held." in out
    assert out == sorted(set(out))


def test_f10_the_refresh_reproduces_the_checked_in_templates():
    t = _tool()
    snap = json.loads(SNAP.read_text(encoding="utf-8"))["strings"]
    templates = [s for s in snap if s.endswith(" with the {0} wheel.")]
    assert sorted(templates) == sorted([HOP + " with the {0} wheel.", SWAY + " with the {0} wheel."])
    legacy = [{"n": "x", "d": s.replace("{0}", "E")} for s in templates]
    assert sorted(t.snapshot_strings(legacy)) == sorted(templates + ["x"])


def test_f10_the_tool_and_the_client_share_one_suffix_rule():
    t = _tool()
    body = KBUI.read_text(encoding="utf-8")
    m = re.search(r'const string legacy = "([^"]*)";', body)
    assert m and m.group(1) == t.LEGACY_WHEEL_SUFFIX
    assert '" with the {0} wheel."' in body
    assert t.TEMPLATE_WHEEL_SUFFIX == " with the {0} wheel."
