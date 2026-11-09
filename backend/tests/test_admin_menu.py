"""Ask 15 (the admin menu reorganised): the design note's claims over the plugin's
C# sources, each pinned to the code term it names, plus the i18n and harness
obligations of its section 7 (the ask 15 design note).

Same family as test_avatar_preset_picker.py (ask 5). Every claim is a function
over the sources that raises AssertionError when the claim is false, and runs
three ways: against the tree (must pass), against an in-memory MUTATION of the
tree (must red) and against an in-memory negative CONTROL edit (must stay
green), so a claim that cannot fail, or that fails on any edit at all, is caught
here rather than trusted. Every scope is a brace-balanced span, never the whole
file, unless the claim is a census over a file.

What the layout RULE decides (a button's width from its translated label, how a
group packs into rows, pages, scope, colour slots) is executed, not read: the
client rules harness suite "adminmenu", pinned case by case in
test_client_rules_harness.py. This file pins that NativeUI DRAWS the rule's
answer and nothing else: every admin button's handler is main's (a digest of its
onClick argument, comments stripped, whitespace folded, pinned from the base
commit), widths and colours reach the buttons only through the rule, the scope
set is the table's, the labels are the design's, and the fenced tab-framework
lines are untouched.
"""
import hashlib
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

NU = "NativeUI.cs"
RL = "AdminMenuRules.cs"
CAT = "I18nCatalogues.cs"
GEN = "I18nSourceKeys.g.cs"
# Files outside plugin/, keyed by their repo-relative path.
EXTRACT = "tools/i18n_extract.py"
SOURCE_JSON = "tools/i18n_source.json"
MAIN = "tools/client-rules-harness/Main.cs"
CSPROJ = "tools/client-rules-harness/client-rules-harness.csproj"
SELFTEST = "tools/client-rules-harness/AdminMenuRulesSelfTest.cs"
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


def _one(text, sig, base=0, raw=False):
    """The single brace-balanced block after `sig`, over the masked text. With
    `raw` the signature is sought in the raw text (for one whose identity is a
    string literal, which the mask blanks); the braces are balanced masked."""
    masked = _masked(text)
    hay = text if raw else masked
    spans, search = [], 0
    while True:
        start = hay.find(sig, search)
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


def _span(text, sig, within=None, raw=False):
    if within is None:
        return _one(text, sig, raw=raw)
    a, b = _one(text, within)
    return _one(text[a:b], sig, base=a, raw=raw)


def _raw(text, sig, within=None):
    a, b = _span(text, sig, within)
    return text[a:b]


def _body(text, sig, within=None):
    return _code(_raw(text, sig, within))


def _code(text):
    return _memo(_STRIP, strip_comments_only, text)


def _fold(text):
    return re.sub(r"\s+", " ", text).strip()


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _call_args(text, open_idx):
    """The top-level arguments of the call whose '(' is at open_idx, raw text
    kept; strings, chars and comments are opaque, brackets track depth."""
    assert text[open_idx] == "(", text[open_idx:open_idx + 20]
    i, depth, args, cur, n = open_idx + 1, 1, [], [], len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\":
                    j += 1
                j += 1
            cur.append(text[i:j + 1])
            i = j + 1
            continue
        if c == "'":
            j = i + 1
            if j < n and text[j] == "\\":
                j += 1
            j += 1
            cur.append(text[i:j + 1])
            i = j + 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            cur.append(text[i:j])
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i) + 2
            cur.append(text[i:j])
            i = j
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                args.append("".join(cur))
                return args
        if c == "," and depth == 1:
            args.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    raise CsParseError("unterminated call at %d" % open_idx)


def _calls(text, name):
    """Every call `name(...)` in `text` (raw), as argument lists."""
    out, search = [], 0
    while True:
        at = text.find(name + "(", search)
        if at == -1:
            return out
        out.append(_call_args(text, at + len(name)))
        search = at + len(name)


def _button_handler(text, go):
    """The onClick argument of the one button `go`: a CreateButton call (7th
    argument) or an AdminLauncher call (3rd), comments stripped, whitespace
    folded. Exactly one site may draw a given button."""
    create = 'UIFactory.CreateButton(%s"%s"' % ("$" if "{idx}" in go else "", go)
    launch = 'AdminLauncher(slots, "%s",' % go
    sites = text.count(create) + text.count(launch)
    assert sites == 1, "button %s has %d sites" % (go, sites)
    if text.count(create):
        args = _call_args(text, text.index(create) + len("UIFactory.CreateButton"))
        arg = args[6]
    else:
        args = _call_args(text, text.index(launch) + len("AdminLauncher"))
        arg = args[2]
    return _fold(strip_comments_only(arg))


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


def _resub(src, fname, pattern, repl):
    """A regex edit that must hit exactly once."""
    s = dict(src)
    t = s[fname]
    new, n = re.subn(pattern, repl, t)
    assert n == 1, "pattern %r hit %d times in %s" % (pattern, n, fname)
    assert new != t
    s[fname] = new
    return s


def _insert_after_open(src, fname, sig, text, within=None, raw=False):
    """Insert `text` right after the opening brace of the block after `sig`."""
    s = dict(src)
    t = s[fname]
    a, _ = _span(t, sig, within, raw=raw)
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


def _control_comment(fname, sig, within=None, indent="            "):
    return lambda s: _insert_after_open(s, fname, sig, indent + "// control", within)


# -- the spans the claims scope on -----------------------------------------

BUILD = "private static GameObject BuildAdminTab(Transform parent)"
APPLY = "private static void ApplyAdminPanelScope()"
BANNED = "private static GameObject BuildBannedTab(Transform parent)"
REFRESH_BANNED = "private static void RefreshBannedTab()"
Q_ROW = "private static GameObject BuildAdminQuarantineRow(Transform parent, int idx)"
Q_FILL = "private static void FillAdminQuarantineRow(GameObject row, ApiClient.QuarantineReportEntry e)"
F_ROW = "private static GameObject BuildAdminFlagRow(Transform parent, int idx)"
B_ROW = "private static GameObject BuildAdminBanRow(Transform parent, int idx)"
S_ROW = "private static GameObject BuildAdminSeriesRow(Transform parent, int idx)"
S_FILL = "private static void FillAdminSeriesRow(GameObject row, ApiClient.AdminSeriesEntry e)"
TONE = "private static Color AdminToneColour(AdminMenuRules.Tone tone)"
VCOL = "private static Color AdminVerdictColour(string label, bool enabled)"
LSIZE = "private static Vector2 AdminLauncherSize(string label)"
SETPAGE = "private static void SetAdminPage(int page)"
GROUPROWS = ("private static void BuildAdminGroupRows(Transform parent, AdminMenuRules.Group group, "
             "string caption, Dictionary<string, Transform> slots)")
LAUNCHER = ("private static GameObject AdminLauncher(Dictionary<string, Transform> slots, string id, "
            "UnityEngine.Events.UnityAction onClick)")
# Every span that draws an admin button.
BUTTON_SPANS = (BUILD, BANNED, Q_ROW, F_ROW, B_ROW, S_ROW, LAUNCHER)
RULES = "internal static partial class AdminMenuRules"
LAUNCHERS_TABLE = "internal static readonly Launcher[] Launchers = new[]"
VERDICTS_TABLE = "internal static readonly Verdict[] Verdicts = new[]"
HEADER_TABLE = "internal static readonly string[] HeaderLaunchers ="
PAGES_TABLE = "internal static readonly string[] PageLabels ="
CAPTIONS_TABLE = "internal static readonly string[] GroupCaptions ="
TONE_FOR = "internal static Tone ToneFor(Kind kind, bool enabled)"
CLAMP = "internal static int ClampPage(int page, bool isAdmin)"
DECL = "private static readonly Dictionary<string, string> %s = new Dictionary<string, string>"
LOCALES = ("ES", "RU", "UK", "SV")
_STR = re.compile(r'"((?:[^"\\]|\\.)*)"')
_LAUNCHER = re.compile(r'new Launcher\(\s*"([^"]+)",\s*"([^"]+)",\s*Group\.(\w+),\s*(true|false)\s*\)')
_VERDICT = re.compile(r'new Verdict\(\s*"([^"]+)",\s*Kind\.(\w+)\s*\)')

# The onClick argument of every admin button at the base commit (57062e8e),
# comments stripped and whitespace folded: (length, sha256[:16]). A lane that
# changes what a click does changes a digest; one that only moves, resizes,
# recolours or relabels the button does not. A rebase onto a main that itself
# changed one of these handlers re-pins the row after reading the change.
BASE_HANDLERS = {
    "ARefresh": (297, "1727c8089f1d8a31"),
    "ABan": (25, "62dc01d8587143cb"),
    "AGrant": (44, "8cbd42c130000f13"),
    "ARev": (29, "b18258cce4b7bef6"),
    "ABugRpt": (46, "07ea5ed76e56e34a"),
    "AArtG": (280, "3b3936808af522ad"),
    "AArtR": (686, "271a8265883a880f"),
    "ACosR": (40, "d9bfa1181201f900"),
    "ATrG": (583, "2cf1abaf8e6e141b"),
    "ATrR": (1191, "458028efb3c370cb"),
    "ACosQ": (46, "e7139e9cf2e1f734"),
    "AAdmins": (29, "a840988c84249a99"),
    "AActions": (33, "d90a8aa46a73232a"),
    "AAlertNew": (719, "8f84c2a12b590201"),
    "AAlertEnd": (769, "b576b917f5878046"),
    "AMutes": (26, "916bfabbecf60a54"),
    "AMuteNew": (25, "1fd44952888f0741"),
    "AChatDel": (28, "2327a0e1bada0a6c"),
    "AMuteMsg": (37, "5d3683b687d9de7d"),
    "ALockdown": (29, "6468f4e0b6ba7f87"),
    "AALFull": (33, "d90a8aa46a73232a"),
    "ABSearch": (19, "2cda00e7badf1efd"),
    "AQA{idx}": (40, "e869e6f5b56821a0"),
    "AQD{idx}": (41, "bd4754a50f246aee"),
    "AFDT{idx}": (9, "d7c45694086281b3"),
    "ABU{idx}": (9, "d7c45694086281b3"),
    "ASB1{idx}": (9, "d7c45694086281b3"),
    "ASB2{idx}": (9, "d7c45694086281b3"),
    "ASB3{idx}": (9, "d7c45694086281b3"),
}

# The tab-framework lines the grant fences (TAB_NAMES, NUM_TABS, TAB_BANNED,
# GROUP_LABELS, GROUP_MEMBERS, GROUP_ADMIN, TabVisible), pinned as the digest of
# the one code line holding each marker, comments stripped, whitespace folded.
FENCED = {
    'string[] TAB_NAMES=>': '0d57a3b986837465',
    'const int NUM_TABS=': '26e559320103d318',
    'const int TAB_BANNED=': '9d77bc9fe2307dae',
    'string[] GROUP_LABELS=>': '07bc0f3ac9424fce',
    'int[][] GROUP_MEMBERS=': '66dbecfa515b1dc4',
    'const int GROUP_ADMIN=': 'a41420622d165a19',
    'static bool TabVisible(': 'a553cf5ed1e2cf10',
}

NEW_KEYS = ("Actions", "Queues", "Chat", "Server", "Unmute Player...", "Admin Roster...",
            "Find and Unban...", "Full Log...", "Banned Players ({0})", "Win T1", "Win T2",
            "Void Series", "Reverse")
OLD_LABELS = ("Chat Mutes...", "Admins...", "Search...", "Full log...", "Banned Users")
MODERATOR_IDS = ("AMuteNew", "AMuteMsg", "AChatDel", "AMutes")
VERDICT_KINDS = {"Accept": "Positive", "Discard": "Negative", "Details": "Launcher", "Unban": "Positive",
                 "Win T1": "Positive", "Win T2": "Positive", "Void Series": "Negative", "Reverse": "Negative"}


# -- the table, as the rules file states it ----------------------------------

def _launchers(src):
    rows = _LAUNCHER.findall(_body(src[RL], LAUNCHERS_TABLE))
    assert rows, "no launcher rows parsed"
    return rows  # (id, label, group, moderatorVisible)


def _verdicts(src):
    rows = _VERDICT.findall(_body(src[RL], VERDICTS_TABLE))
    assert rows, "no verdict rows parsed"
    return rows


def _strings(src, sig):
    return _STR.findall(_body(src[RL], sig))


def _table_labels(src):
    labels = [r[1] for r in _launchers(src)] + [r[0] for r in _verdicts(src)]
    for sig in (HEADER_TABLE, PAGES_TABLE, CAPTIONS_TABLE):
        labels += _strings(src, sig)
    assert len(labels) >= 18 + 8 + 4 + 2 + 3, labels
    return labels


def _launcher_sites(src):
    """The ids of the AdminLauncher calls in BuildAdminTab, in source order."""
    return [a[1].strip().strip('"') for a in _calls(_body(src[NU], BUILD), "AdminLauncher")]


# -- H1 every button keeps main's handler -------------------------------------

def _h1(src):
    nu = src[NU]
    bad = []
    for go, (n, d) in BASE_HANDLERS.items():
        h = _button_handler(nu, go)
        if _digest(h) != d:
            bad.append((go, len(h), _digest(h), h[:60]))
    assert not bad, "handlers that differ from main's: %r" % bad


def test_h1_every_admin_button_keeps_the_handler_main_gave_it():
    _check(_h1,
           lambda s: _replace_within(s, NU, BUILD, "StartAdminBanFlow()", "StartAdminBanFlow(true)"),
           lambda s: _replace_within(s, NU, BUILD, 'AdminLauncher(slots, "ABan", () =>',
                                     'AdminLauncher(slots, "ABan", () => /* control */'))


# -- H2 the launchers are drawn in the table's order, each exactly once --------

def _h2(src):
    table = [r[0] for r in _launchers(src)]
    sites = _launcher_sites(src)
    assert sites == table, "AdminLauncher sites %r are not the table's order %r" % (sites, table)


def test_h2_launchers_are_created_in_the_tables_order():
    def swap(s):
        s = _replace(s, RL, 'new Launcher("AMuteMsg",', 'new Launcher("SWAP",')
        s = _replace(s, RL, 'new Launcher("AMuteNew",', 'new Launcher("AMuteMsg",')
        return _replace(s, RL, 'new Launcher("SWAP",', 'new Launcher("AMuteNew",')
    _check(_h2, swap, _control_comment(NU, BUILD))


def _h3(src):
    table = [r[0] for r in _launchers(src)]
    sites = _launcher_sites(src)
    assert len(set(table)) == len(table) == 18, table
    assert sorted(sites) == sorted(table), "sites %r vs table %r" % (sorted(sites), sorted(table))
    nu = src[NU]
    strays = [i for i in table if ('UIFactory.CreateButton("%s"' % i) in nu]
    assert not strays, "table launchers still drawn by a hand-placed CreateButton: %r" % strays
    for i in table:
        assert nu.count('AdminLauncher(slots, "%s",' % i) == 1, i


def test_h3_every_table_launcher_has_one_site_and_no_hand_placed_twin():
    _check(_h3,
           lambda s: _replace_within(s, NU, BUILD, 'AdminLauncher(slots, "ACosQ",', 'AdminLauncherX(slots, "ACosQ",'),
           _control_comment(NU, BUILD))


# -- H4 colour reaches a button only through the rule -------------------------

_BG_OK = re.compile(r"^(launcherCol|AdminToneColour\(.*\)|AdminVerdictColour\(.*\))$")


def _h4(src):
    nu = src[NU]
    for sig in BUTTON_SPANS:
        raw = _raw(nu, sig)
        for args in _calls(raw, "UIFactory.CreateButton"):
            assert len(args) == 8, (sig, args[0])
            bg = _fold(strip_comments_only(args[5]))
            assert _BG_OK.match(bg), "button %s in %s takes colour %r, not the rule's" % (args[0].strip(), sig[:40], bg)
    for sig in (SETPAGE, Q_FILL):
        for args in _calls(_raw(nu, sig), "UIFactory.SetImageColor"):
            c = _fold(strip_comments_only(args[1]))
            assert c.startswith(("AdminToneColour(", "AdminVerdictColour(")), (sig[:40], c)
    fill = _body(nu, S_FILL)
    shown = [a for a in _calls(fill, "setBtn") if len(a) == 5 and a[1].strip() == "true"]
    assert len(shown) == 4, "series verdicts shown: %d" % len(shown)
    for a in shown:
        assert _fold(a[3]).startswith("AdminVerdictColour("), a[3]
    build = _body(nu, BUILD)
    assert build.count("new Color(") == 1 and "new Color(1f, 0.7f, 0.3f)" in build, \
        "BuildAdminTab draws a colour literal beyond the title's"
    for sig in (TONE, VCOL, LSIZE, SETPAGE, GROUPROWS, LAUNCHER, BANNED, REFRESH_BANNED):
        assert "new Color(" not in _body(nu, sig), sig[:50]


def test_h4_every_admin_button_colour_comes_through_the_rule():
    _check(_h4,
           lambda s: _replace_within(s, NU, B_ROW, 'AdminVerdictColour("Unban", true)', "new Color(0.2f, 0.45f, 0.2f, 0.9f)"),
           _control_comment(NU, B_ROW))


# -- H5 widths reach a button only through the rule, from translated labels ---

_SIZE_OK = re.compile(r"^sizeDelta: (AdminLauncherSize\(|new Vector2\((verdictW|AdminMenuRules\.))")


def _h5(src):
    nu = src[NU]
    for sig in BUTTON_SPANS:
        for args in _calls(_raw(nu, sig), "UIFactory.CreateButton"):
            size = _fold(strip_comments_only(args[7]))
            assert _SIZE_OK.match(size), "button %s in %s is sized %r, not by the rule" % (args[0].strip(), sig[:40], size)
    assert "new Vector2(AdminMenuRules.LauncherWidth(I18n.Tr(label)), 26)" in _body(nu, LSIZE)


def test_h5_every_admin_button_width_comes_through_the_rule():
    _check(_h5,
           lambda s: _replace_within(s, NU, BUILD, 'sizeDelta: AdminLauncherSize("Refresh")', "sizeDelta: new Vector2(90, 26)"),
           _control_comment(NU, BUILD))


def _h5b(src):
    nu = src[NU]
    rows = _body(nu, GROUPROWS)
    assert "widths[i] = AdminMenuRules.LauncherWidth(I18n.Tr(ls[i].Label));" in rows
    assert "AdminMenuRules.PackRows(widths, AdminMenuRules.RowSpacing, AdminMenuRules.ContentWidth)" in rows
    region = "".join(_body(nu, sig) for sig in BUTTON_SPANS + (LSIZE,))
    for m in re.finditer(r"\bSharedVerdictWidth\(([^;]*?)\);", region):
        inner = m.group(1)
        assert re.match(r'^new\[\] \{ I18n\.Tr\("[^"]+"\)(, I18n\.Tr\("[^"]+"\))* \}$', inner), inner
    for m in re.finditer(r"(?<!Shared)\bVerdictWidth\(([^)]*\))\)", region):
        assert m.group(1).startswith('I18n.Tr("'), m.group(0)
    for m in re.finditer(r"\bLauncherWidth\(([^)]*\))\)", region):
        assert m.group(1).startswith("I18n.Tr("), m.group(0)


def test_h5b_every_width_is_measured_on_the_translated_label():
    _check(_h5b,
           lambda s: _replace_within(s, NU, GROUPROWS, "LauncherWidth(I18n.Tr(ls[i].Label))", "LauncherWidth(ls[i].Label)"),
           _control_comment(NU, GROUPROWS))


# -- H6 the scope set is the table's --------------------------------------------

def _h6(src):
    nu = src[NU]
    build = _body(nu, BUILD)
    assert "adminOnlySections.Add(adminPageBar);" in build
    assert "adminOnlySections.Add(adminPageQueues);" in build
    assert build.count("adminOnlySections.Add(") == 2, "a hand-added scope entry in BuildAdminTab"
    assert "adminOnlySections.Clear();" in build
    assert "if (AdminMenuRules.GroupIsAdminOnly(group)) adminOnlySections.Add(block);" in _body(nu, GROUPROWS)
    assert "if (!l.ModeratorVisible && !AdminMenuRules.GroupIsAdminOnly(l.Group)) adminOnlySections.Add(btn);" in _body(nu, LAUNCHER)
    rows = _launchers(src)
    visible = [r[0] for r in rows if r[3] == "true"]
    assert visible == list(MODERATOR_IDS), visible
    assert all(r[2] == "Chat" for r in rows if r[3] == "true")
    assert [r[0] for r in rows if r[2] == "Chat" and r[3] == "false"] == ["ALockdown"]


def test_h6_a_moderator_sees_the_tables_four_chat_buttons_and_nothing_else():
    _check(_h6,
           lambda s: _resub(s, RL, r'("ALockdown",\s*"Chat Lockdown\.\.\.",\s*Group\.Chat,\s*)false', r"\1true"),
           _control_comment(RL, RULES, indent="        "))


# -- H7 the page a role may stand on ---------------------------------------------

def _h7(src):
    nu = src[NU]
    apply = _body(nu, APPLY)
    assert apply.rstrip().endswith("SetAdminPage(adminPage);\n        }"), apply[-120:]
    page = _body(nu, SETPAGE)
    assert "adminPage = AdminMenuRules.ClampPage(page, ApiClient.IsAdmin);" in page
    assert "adminPageActions.SetActive(adminPage == 0);" in page
    assert "adminPageQueues.SetActive(adminPage == 1);" in page
    assert "return isAdmin && page == 1 ? 1 : 0;" in _body(src[RL], CLAMP)


def test_h7_apply_scope_clamps_the_page_to_the_role():
    _check(_h7,
           lambda s: _replace_within(s, NU, APPLY, "            SetAdminPage(adminPage);\n", ""),
           _control_comment(NU, APPLY))


# -- H8 the labels are the design's -----------------------------------------------

def _h8(src):
    nu = src[NU]
    labels = dict((r[0], r[1]) for r in _launchers(src))
    assert labels["AMutes"] == "Unmute Player..."
    assert labels["AAdmins"] == "Admin Roster..."
    assert labels["AActions"] == "Action Log..."
    banned = _raw(nu, BANNED)
    search = [a for a in _calls(banned, "UIFactory.CreateButton") if a[0].strip() == '"ABSearch"']
    assert len(search) == 1 and search[0][2].strip() == '"Find and Unban..."', search
    full = [a for a in _calls(_raw(nu, BUILD), "UIFactory.CreateButton") if a[0].strip() == '"AALFull"']
    assert len(full) == 1 and full[0][2].strip() == '"Full Log..."', full
    region = _body(nu, BUILD) + _body(nu, BANNED) + _body(nu, REFRESH_BANNED) + _code(src[RL])
    for old in OLD_LABELS:
        assert '"%s' % old not in region, "old label %r still drawn" % old


def test_h8_the_four_relabels_hold_and_the_old_labels_are_gone():
    _check(_h8,
           lambda s: _replace(s, RL, '"Unmute Player..."', '"Chat Mutes..."'),
           _control_comment(RL, RULES, indent="        "))


def _h9(src):
    body = _body(src[NU], REFRESH_BANNED)
    assert 'UIFactory.SetText(txtAdminBansHdr, I18n.TrF("Banned Players ({0})", bans.Count));' in body
    assert "Banned Users" not in body


def test_h9_the_banned_count_header_is_translated():
    _check(_h9,
           lambda s: _replace_within(s, NU, REFRESH_BANNED, 'I18n.TrF("Banned Players ({0})", bans.Count)', '$"Banned Users ({bans.Count})"'),
           _control_comment(NU, REFRESH_BANNED))


# -- H10 the series and quarantine verdicts ------------------------------------------

def _h10(src):
    nu = src[NU]
    fill = _body(nu, S_FILL)
    for label, call in (("Win T1", 'ConfirmResolveTeam(e, "complete", 1)'), ("Win T2", 'ConfirmResolveTeam(e, "complete", 2)'),
                        ("Void Series", 'ConfirmResolveTeam(e, "void", 0)'), ("Reverse", "ConfirmReverseSeries(e)")):
        want = 'true, I18n.Tr("%s"), AdminVerdictColour("%s", true), () => %s);' % (label, label, call)
        assert want in fill, want
    row = _body(nu, S_ROW)
    assert 'AdminMenuRules.SharedVerdictWidth(new[] { I18n.Tr("Win T1"), I18n.Tr("Win T2"), I18n.Tr("Void Series"), I18n.Tr("Reverse") })' in row
    assert row.count("sizeDelta: new Vector2(verdictW, 24)") == 3


def test_h10_series_verdicts_are_translated_and_share_one_width():
    _check(_h10,
           lambda s: _replace_within(s, NU, S_FILL, 'I18n.Tr("Void Series"), AdminVerdictColour("Void Series", true)',
                                     '"Void", AdminVerdictColour("Void Series", true)'),
           _control_comment(NU, S_FILL))


def _h11(src):
    nu = src[NU]
    row = _body(nu, Q_ROW)
    assert 'int verdictW = AdminMenuRules.SharedVerdictWidth(new[] { I18n.Tr("Accept"), I18n.Tr("Discard") });' in row
    assert "prefW: verdictW + AdminMenuRules.VerdictColumnPad" in row
    assert row.count("sizeDelta: new Vector2(verdictW, 27)") == 2
    fill = _body(nu, Q_FILL)
    assert "SetButtonInteractable(accept, e.can_accept);" in fill
    assert 'UIFactory.SetImageColor(accept, AdminVerdictColour("Accept", e.can_accept));' in fill


def test_h11_quarantine_verdicts_share_one_width_and_grey_out_by_the_rule():
    _check(_h11,
           lambda s: _replace_within(s, NU, Q_FILL, 'AdminVerdictColour("Accept", e.can_accept)', 'AdminVerdictColour("Accept", true)'),
           _control_comment(NU, Q_FILL))


# -- H12 tones map to the four button colours and the bar's two -----------------------

def _h12(src):
    nu = src[NU]
    tone = _body(nu, TONE)
    for case, const in (("NavActive", "C_TABACT"), ("Nav", "C_TAB"), ("Positive", "C_ADMIN_POS"),
                        ("Negative", "C_ADMIN_NEG"), ("Disabled", "C_ADMIN_OFF")):
        assert "case AdminMenuRules.Tone.%s: return %s;" % (case, const) in tone, case
    assert "default: return C_BTN;" in tone
    assert "AdminToneColour(AdminMenuRules.ToneFor(AdminMenuRules.KindOfVerdict(label), enabled))" in _body(nu, VCOL)
    code = _code(nu)
    assert "C_ADMIN_POS = new Color(0.2f, 0.45f, 0.2f, 0.9f);" in code
    assert "C_ADMIN_NEG = new Color(0.5f, 0.25f, 0.16f, 0.9f);" in code
    assert "C_ADMIN_OFF = new Color(0.18f, 0.18f, 0.18f, 0.75f);" in code
    kinds = dict(_verdicts(src))
    assert kinds == VERDICT_KINDS, kinds
    assert "if (!enabled) return Tone.Disabled;" in _body(src[RL], TONE_FOR)


def test_h12_each_tone_maps_to_one_colour_and_each_verdict_to_one_tone():
    _check(_h12,
           lambda s: _replace_within(s, NU, TONE, "case AdminMenuRules.Tone.Positive: return C_ADMIN_POS;",
                                     "case AdminMenuRules.Tone.Positive: return C_ADMIN_NEG;"),
           _control_comment(NU, TONE))


# -- H13 headers wear C_SUB, bold ---------------------------------------------------------

def _h13(src):
    nu = src[NU]
    build = _body(nu, BUILD)
    for text, var in (("Recent Ranked Series", "txtAdminSeriesHdr"), ("Rejected Reports", "txtAdminQuarantineHdr"),
                      ("Flagged Matches", "txtAdminFlagsHdr"), ("Action Log", "txtAdminActLogHdr")):
        assert '"%s", 16f, C_SUB' % text in build, text
        assert "UIFactory.SetBold(%s, true);" % var in build, var
    banned = _body(nu, BANNED)
    assert '"Banned Players", 17f, C_SUB' in banned
    assert "UIFactory.SetBold(txtAdminBansHdr, true);" in banned


def test_h13_every_section_header_is_c_sub_and_bold():
    _check(_h13,
           lambda s: _replace_within(s, NU, BUILD, '"Recent Ranked Series", 16f, C_SUB', '"Recent Ranked Series", 16f, C_GOLD'),
           _control_comment(NU, BUILD))


# -- H14 what sits where ------------------------------------------------------------------

def _h14(src):
    nu = src[NU]
    build = _body(nu, BUILD)
    assert 'UIFactory.CreateButton("ARefresh", hdrRow.transform,' in build
    assert 'UIFactory.CreateButton("ARev", seriesHdrRow.transform,' in build
    assert 'UIFactory.CreateButton("AALFull", actHdrRow.transform,' in build
    assert "seriesHdrRow.transform.SetParent(adminPageQueues.transform, false);" in build
    assert "BuildAdminGroupRows(adminPageActions.transform, AdminMenuRules.ActionsGroups[g], AdminMenuRules.GroupCaptions[g], slots);" in build
    assert "BuildAdminGroupRows(adminPageQueues.transform, AdminMenuRules.Group.Queues, null, slots);" in build
    order = [build.index(k) for k in ('new GameObject("AHdr")', 'new GameObject("APages")', 'NewAdminBlock("APageActions"',
                                      'NewAdminBlock("APageQueues"', "BuildAdminGroupRows(adminPageActions", "AdminLauncher(slots,",
                                      'new GameObject("ASHRow")', 'CreateScrollView("ASSV"', 'new GameObject("AQHRow")', 'new GameObject("ASplit")')]
    assert order == sorted(order), "the build order changed"
    assert 'UIFactory.CreateButton("ABSearch", bansHdrRow.transform,' in _body(nu, BANNED)


def test_h14_header_launchers_sit_on_their_header_rows_and_the_pages_build_in_order():
    _check(_h14,
           lambda s: _replace_within(s, NU, BUILD, 'CreateButton("ARev", seriesHdrRow.transform,', 'CreateButton("ARev", hdrRow.transform,'),
           _control_comment(NU, BUILD))


# -- H15 the page bar ------------------------------------------------------------------------

def _h15(src):
    nu = src[NU]
    build = _body(nu, BUILD)
    assert "for (int p = 0; p < AdminMenuRules.PageLabels.Length; p++)" in build
    assert ('UIFactory.CreateButton("APage" + p, adminPageBar.transform, AdminMenuRules.PageLabels[p], '
            "AdminMenuRules.PageTabPt, C_LABEL,") in build
    assert "() => SetAdminPage(pi), sizeDelta: new Vector2(AdminMenuRules.PageTabWidth, 26)" in build
    assert "adminPageTexts[p] = UIFactory.GetButtonText(pb);" in build
    page = _body(nu, SETPAGE)
    assert "UIFactory.SetImageColor(adminPageBtns[i], AdminToneColour(AdminMenuRules.NavTone(active)));" in page
    assert "UIFactory.SetColor(adminPageTexts[i], active ? C_WHITE : C_LABEL);" in page
    assert "UIFactory.SetBold(adminPageTexts[i], active);" in page


def test_h15_the_page_bar_is_the_shops_pattern_painted_by_the_rule():
    _check(_h15,
           lambda s: _replace_within(s, NU, SETPAGE, "                    UIFactory.SetBold(adminPageTexts[i], active);\n", ""),
           _control_comment(NU, SETPAGE))


# -- H16 captions and rows --------------------------------------------------------------------

def _h16(src):
    rows = _body(src[NU], GROUPROWS)
    assert 'UIFactory.CreateText("AGC" + group, block.transform, caption, 12f, C_LABEL,' in rows
    assert "UIFactory.AddHLG(row, spacing: AdminMenuRules.RowSpacing);" in rows
    assert "slots[ls[i].Id] = row.transform;" in rows
    assert "var ls = AdminMenuRules.GroupLaunchers(group, true);" in rows
    assert "1812" not in rows and "ContentWidth" in rows


def test_h16_group_rows_pack_by_the_rules_budget_under_a_c_label_caption():
    _check(_h16,
           lambda s: _replace_within(s, NU, GROUPROWS, "AdminMenuRules.RowSpacing, AdminMenuRules.ContentWidth)", "AdminMenuRules.RowSpacing, 1812)"),
           _control_comment(NU, GROUPROWS))


def _h17(src):
    nu = src[NU]
    for sig, name in ((Q_ROW, "AQ"), (F_ROW, "AF"), (B_ROW, "AB"), (S_ROW, "AS")):
        assert 'UIFactory.CreatePanel($"%s{idx}", parent, C_PANEL);' % name in _body(nu, sig), sig[:50]


def test_h17_every_admin_row_is_a_c_panel():
    _check(_h17,
           lambda s: _replace_within(s, NU, Q_ROW, 'CreatePanel($"AQ{idx}", parent, C_PANEL)', 'CreatePanel($"AQ{idx}", parent, C_BG)'),
           _control_comment(NU, Q_ROW))


# -- H18 the fenced tab-framework lines are untouched -------------------------------------------

def _h18(src):
    lines = _code(src[NU]).splitlines()
    for marker, want in FENCED.items():
        hits = [l for l in lines if marker in l]
        assert len(hits) == 1, "%d lines hold %r" % (len(hits), marker)
        got = _digest(_fold(hits[0]))
        assert got == want, "fenced line %r changed (digest %s)" % (marker, got)


def test_h18_the_fenced_tab_framework_lines_are_untouched():
    _check(_h18,
           lambda s: _replace(s, NU, "TAB_BANNED=14;", "TAB_BANNED=15;"),
           _control_comment(NU, BUILD))


# -- I1 every key the admin menu draws is in all four catalogues ----------------------------------

def _i1(src):
    cat = src[CAT]
    keys = list(NEW_KEYS) + _table_labels(src)
    missing = []
    for loc in LOCALES:
        block = _body(cat, DECL % loc)
        for k in keys:
            if '["%s"]' % k not in block:
                missing.append((loc, k))
    assert not missing, "catalogue entries missing: %r" % missing


def test_i1_every_admin_key_is_translated_in_es_ru_uk_and_sv():
    _check(_i1,
           lambda s: _replace(s, CAT, '            ["Void Series"] = "Anular serie",\n', ""),
           lambda s: _insert_after_open(s, CAT, DECL % "ES", "            // control"))


def _i2(src):
    ex = src[EXTRACT]
    assert '"AdminMenuRules.cs",' in ex, "AdminMenuRules.cs is not in the extractor's FILES"
    block = ex[ex.index('if fn == "AdminMenuRules.cs":'):]
    block = block[:block.index("\ndef extract():")]
    for needle in ("new Launcher", "new Verdict", '"HeaderLaunchers"', '"PageLabels"', '"GroupCaptions"', "note_table("):
        assert needle in block, needle
    strings = json.loads(src[SOURCE_JSON])["strings"]
    have = set(x if isinstance(x, str) else x.get("s", x.get("key", "")) for x in strings)
    want = set(NEW_KEYS) | set(_table_labels(src))
    assert want <= have, "source strings missing: %r" % sorted(want - have)
    gen = src[GEN]
    gone = [k for k in want if '"%s",' % k.replace('"', '\\"') not in gen]
    assert not gone, "I18nSourceKeys.g.cs lacks %r" % gone
    for old in ("Chat Mutes...", "Admins...", "Search...", "Full log..."):
        assert old not in have, "retired source string %r still harvested" % old


def test_i2_the_extractor_harvests_the_rules_tables_and_the_registry_carries_the_keys():
    _check(_i2,
           lambda s: _replace(s, EXTRACT, '    "AdminMenuRules.cs",\n', ""),
           lambda s: _replace(s, EXTRACT, "# Ask 15 (AdminMenuRules.cs):", "# Ask 15 (AdminMenuRules.cs), control:"))


# -- I3 the harness suite is registered and compiled ---------------------------------------------

def _i3(src):
    a, b = _span(src[MAIN], 'RunSuite("adminmenu"', raw=True)
    main = _code(src[MAIN][a:b])
    assert "var r = AdminMenuRules.SelfTest();" in main
    assert "return new Suite(r.Passed + r.Failed, r.Failed, r.Report.ToString());" in main
    csproj = src[CSPROJ]
    assert '<Compile Include="../../plugin/AdminMenuRules.cs" />' in csproj
    assert '<Compile Include="AdminMenuRulesSelfTest.cs" />' in csproj
    st = _code(src[SELFTEST])
    assert "internal static SelfTestResult SelfTest()" in st
    assert "I18nCatalogues.Install();" in st
    assert '{ "en", "es", "ru", "uk", "sv" }' in st
    assert 'Check(r, "' in st


def test_i3_the_adminmenu_suite_is_registered_and_its_files_compiled():
    _check(_i3,
           lambda s: _replace(s, CSPROJ, '    <Compile Include="AdminMenuRulesSelfTest.cs" />\n', ""),
           lambda s: _insert_after_open(s, MAIN, 'RunSuite("adminmenu"', "                              // control", raw=True))


# -- the census: every claim above ran three ways ---------------------------------------------------

CLAIMS = [k for k in sorted(globals()) if re.match(r"^_(h\d+b?|i\d+)$", k)]


def test_every_claim_has_its_test():
    tests = [k for k in globals() if k.startswith("test_") and k != "test_every_claim_has_its_test"]
    assert len(CLAIMS) == 22, CLAIMS
    assert len(tests) == len(CLAIMS), (len(tests), len(CLAIMS))
