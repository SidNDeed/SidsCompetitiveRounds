#!/usr/bin/env python3
"""Item 17 T5: the settings key-set instrument for the Controls sub-tab.

Item 13's settings key-set instrument harvests the Settings controls of
NativeUI.cs and its two cross-file builders; it never reads
NativeUI.Keybinds.cs and it recognises no row-part suffix, so the sixteen
KEYBIND rows were invisible to it (item 17 fix pass 1, finding F8). This
instrument carries that job for the Controls sub-tab:

* It FOLLOWS THE CONSTRUCTION CHAIN, it does not pattern-match names:
  NativeUI.cs passes the Controls body to BuildControlsRows; each statement
  there is a heading (KeybindHeading: chrome), a SettingsKeybind call, or a
  for-loop of SettingsKeybind calls whose bounds are evaluated over
  KeybindRules' own constants. Any other statement that builds UI is FATAL.
* It RECOGNISES the row parts by suffix: SettingsKeybind -> SettingsNewRow ->
  SettingsDecorateRow build `key`, `key_q`, `key_l`, `key_c` and, in the
  cell, `key_b`, `key_x`, `key_r`. A part with a suffix outside that list,
  or a name expression it cannot reduce, is FATAL - never a guess, never a
  row. Parts are checked under the parent they belong to.
* Every other construction in the plugin whose name is "SKb"-prefixed is
  classified by its resolved parent: under SetDetail (the help pane) it is
  chrome and ignored; under the Controls body it is a key; anywhere else, or
  unresolved, it is FATAL.

The key set is one key per row plus any raw control under the Controls
body; it must equal the checked-in baseline (controls_keyset.json, captured
from the tree of the commit that built the Controls page, a22f80ed) and
carry exactly sixteen rows. `selftest` runs four mutations (one row
dropped -> exactly that key missing; an unrecognised part suffix; a raw
control under the Controls body; a part under the wrong parent) and two
controls (a chrome button under SetDetail; an extra heading under the
Controls body), each with its expected verdict.

USAGE
    python tools/settings/controls_keyset.py check    [--tree <root>] [--baseline <json>]
    python tools/settings/controls_keyset.py capture  --out <json> [--tree <root>]
    python tools/settings/controls_keyset.py selftest [--tree <root>]

Exit 0 green, 1 red (diff or fatal), 2 usage/refusal. Reads only.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
BASELINE = os.path.join(HERE, "controls_keyset.json")

ROW_PARTS = ("_q", "_l", "_c")          # SettingsNewRow / SettingsDecorateRow, under the row
CELL_PARTS = ("_b", "_x", "_r")         # SettingsKeybind, under the row's _c cell
RECOGNISED = ROW_PARTS + CELL_PARTS
CHROME_ANCESTORS = ("SetDetail", "SetDetFoot")   # the help pane and its footer (verified under SetDetail)
ROWS_EXPECTED = 16                      # design section 2.2: sixteen rows, one key each
PREFIX = "SKb"
CONSTRUCTOR = re.compile(r"(UIFactory\s*\.\s*Create(?:Button|Text|Panel)|new\s+GameObject)\s*\(")
UI_CALL = re.compile(r"\b(UIFactory\s*\.\s*Create\w*|new\s+GameObject|Settings[A-Z]\w*|KeybindHeading)\s*\(")
FILES = ("NativeUI.cs", "NativeUI.Keybinds.cs", "NativeUI.Settings.cs", "KeybindRules.cs")


def _cs():
    path = os.path.join(REPO, "backend", "tests", "_cs_structure.py")
    spec = importlib.util.spec_from_file_location("_cs_structure_t5", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CS = None


class Fatal(Exception):
    pass


class Src:
    """One file: raw text, the code mask and the comment-free text, all at
    the same offsets."""

    def __init__(self, name, text):
        self.name = name
        self.text = text
        self.mask = CS.mask_code(text)
        self.lit = CS.strip_comments_only(text)

    def line(self, pos):
        return self.text.count("\n", 0, pos) + 1


def match(s, open_pos, o="(", c=")"):
    depth = 0
    for i in range(open_pos, len(s)):
        if s[i] == o:
            depth += 1
        elif s[i] == c:
            depth -= 1
            if depth == 0:
                return i
    raise Fatal("unbalanced %s at %d" % (o, open_pos))


def args_of(src, open_pos):
    """Top-level argument spans of the call whose '(' is at open_pos."""
    close = match(src.mask, open_pos)
    out, depth, start = [], 0, open_pos + 1
    for i in range(open_pos + 1, close):
        ch = src.mask[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append((start, i))
            start = i + 1
    out.append((start, close))
    return [(a, b) for a, b in out if src.lit[a:b].strip()], close


def text_of(src, span):
    return re.sub(r"\s+", " ", src.lit[span[0]:span[1]]).strip()


def method_body(src, signature):
    at = [m.start() for m in re.finditer(re.escape(signature), src.mask)]
    if len(at) != 1:
        raise Fatal("%s: %r found %d times" % (src.name, signature, len(at)))
    ob = src.mask.index("{", at[0] + len(signature))
    return ob + 1, match(src.mask, ob, "{", "}")


def statements(src, a, b):
    out, depth, start = [], 0, a
    for i in range(a, b):
        ch = src.mask[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ";" and depth == 0:
            if src.mask[start:i].strip():
                out.append((start, i))
            start = i + 1
    if src.mask[start:b].strip():
        raise Fatal("%s:%d: trailing text without ';'" % (src.name, src.line(start)))
    return out


def constants(rules):
    c = {}
    for m in re.finditer(r"\binternal\s+const\s+int\s+([^;]+);", rules.mask):
        for n, v in re.findall(r"([A-Za-z_]\w*)\s*=\s*(-?\d+)", rules.mask[m.start(1):m.end(1)]):
            c[n] = int(v)
    m = re.search(r"internal\s+static\s+readonly\s+string\[\]\s+RowIds\s*=\s*\{", rules.mask)
    if not m:
        raise Fatal("KeybindRules.RowIds not found")
    close = match(rules.mask, m.end() - 1, "{", "}")
    ids = re.findall(r'"([^"]*)"', rules.lit[m.end():close])
    return c, ids


def evaluate(expr, consts, src, pos):
    e = re.sub(r"\bKeybindRules\s*\.\s*([A-Za-z_]\w*)",
               lambda m: str(consts[m.group(1)]) if m.group(1) in consts else "?", expr)
    if not re.fullmatch(r"[\d\s+\-]+", e):
        raise Fatal("%s:%d: bound %r is not an expression over KeybindRules constants" % (src.name, src.line(pos), expr))
    return eval(e, {"__builtins__": {}})   # digits, spaces, + and - only (checked above)


def last_assignment(src, var, before):
    """The constructor a local was last assigned from, before `before`:
    (kind, literal name) or None."""
    pat = re.compile(r"\b%s\s*=\s*(UIFactory\s*\.\s*Create\w+|new\s+GameObject)\s*\(" % re.escape(var))
    hits = [m for m in pat.finditer(src.mask, 0, before)]
    if not hits:
        return None
    m = hits[-1]
    args, _ = args_of(src, m.end() - 1)
    name = text_of(src, args[0])
    lm = re.fullmatch(r'"([^"]*)"', name)
    return (m.group(1), lm.group(1) if lm else None)


METHOD = re.compile(r"(?:private|internal|public)\s+static\s+[\w<>\[\],.]+\s+(\w+)\s*\(([^)]*)\)\s*\{")


def resolve_parent(srcs, src, expr, pos, depth=0):
    """The literal name of the object a parent expression stands for: a
    local assigned from a named constructor, or a Transform parameter whose
    one call site passes such a local. None when it does not resolve."""
    m = re.fullmatch(r"([A-Za-z_]\w*)(?:\.transform)?", expr)
    if not m or depth > 3:
        return None
    var = m.group(1)
    anc = last_assignment(src, var, pos)
    if anc:
        return anc[1]
    enclosing = None
    for mm in METHOD.finditer(src.mask, 0, pos):
        ob = mm.end() - 1
        if match(src.mask, ob, "{", "}") > pos:
            enclosing = mm
    if not enclosing:
        return None
    params = [p.strip().split()[-1] for p in enclosing.group(2).split(",") if p.strip()]
    if var not in params:
        return None
    k = params.index(var)
    sites = []
    for s in srcs.values():
        for c in re.finditer(r"(?<![\w.])%s\s*\(" % enclosing.group(1), s.mask):
            if c.start() == enclosing.start(1):
                continue
            sites.append((s, c))
    if len(sites) != 1:
        return None
    s, c = sites[0]
    args, _ = args_of(s, c.end() - 1)
    if k >= len(args):
        return None
    return resolve_parent(srcs, s, re.sub(r"\s+", "", text_of(s, args[k])), c.start(), depth + 1)


def harvest(texts):
    """texts: {file name: source}. Returns the manifest or raises Fatal."""
    srcs = {n: Src(n, texts[n]) for n in FILES}
    consts, row_ids = constants(srcs["KeybindRules.cs"])
    if len(row_ids) != consts.get("RowCount", -1):
        raise Fatal("RowIds has %d entries, RowCount is %s" % (len(row_ids), consts.get("RowCount")))
    nui, kb, st = srcs["NativeUI.cs"], srcs["NativeUI.Keybinds.cs"], srcs["NativeUI.Settings.cs"]

    # 1. the Controls body: BuildControlsRows(<var>.transform), once
    calls = [m for m in re.finditer(r"\bBuildControlsRows\s*\(", nui.mask)]
    if len(calls) != 1:
        raise Fatal("NativeUI.cs: BuildControlsRows called %d times" % len(calls))
    args, _ = args_of(nui, calls[0].end() - 1)
    am = re.fullmatch(r"([A-Za-z_]\w*)\.transform", text_of(nui, args[0]))
    home = last_assignment(nui, am.group(1), calls[0].start()) if am else None
    if not home or home[1] is None:
        raise Fatal("NativeUI.cs:%d: the Controls body does not resolve to a named object" % nui.line(calls[0].start()))
    home = home[1]

    # 2. the chain: SettingsKeybind -> SettingsNewRow -> SettingsDecorateRow
    ka, kb_end = method_body(kb, "private static GameObject SettingsKeybind(Transform parent, int row)")
    body = kb.lit[ka:kb_end]
    if not re.search(r'string\s+key\s*=\s*"SKb"\s*\+\s*KeybindRules\s*\.\s*RowIds\s*\[\s*row\s*\]\s*;', body):
        raise Fatal("SettingsKeybind: the row key is not \"SKb\" + KeybindRules.RowIds[row]")
    if len(re.findall(r"\bSettingsNewRow\s*\(\s*parent\s*,\s*key\s*,", body)) != 1:
        raise Fatal("SettingsKeybind: not exactly one SettingsNewRow(parent, key, ...)")
    na, nb = method_body(st, "private static SettingsRowRec SettingsNewRow(Transform parent, string key, SettingsKind kind, string desc)")
    nbody = st.lit[na:nb]
    if len(re.findall(r"\bSettingsDecorateRow\s*\(\s*row\s*,\s*key\s*\)", nbody)) != 1:
        raise Fatal("SettingsNewRow: not exactly one SettingsDecorateRow(row, key)")
    if not re.search(r"\bCell\s*=\s*cell\b", nbody):
        raise Fatal("SettingsNewRow: the record's Cell is not the _c cell")
    da, db = method_body(st, "private static object SettingsDecorateRow(GameObject row, string key)")

    parts = []      # (suffix, parent node, where)
    row_node = None

    def visit(src, a, b, parent_map, where):
        nonlocal row_node
        for m in CONSTRUCTOR.finditer(src.mask, a, b):
            args, _ = args_of(src, m.end() - 1)
            name = text_of(src, args[0])
            if m.group(1).startswith("new"):
                vm = re.search(r"\b([A-Za-z_]\w*)\s*=\s*$", src.mask[max(a, m.start() - 80):m.start()])
                pm = vm and re.search(r"\b%s\s*\.\s*transform\s*\.\s*SetParent\s*\(\s*([^,]+)," % vm.group(1), src.lit[m.end():b])
                parent = re.sub(r"\s+", "", pm.group(1)) if pm else "?"
            else:
                parent = re.sub(r"\s+", "", text_of(src, args[1])) if len(args) > 1 else "?"
            node = parent_map.get(parent)
            if node is None:
                raise Fatal("%s:%d: %s parent %r does not resolve" % (src.name, src.line(m.start()), where, parent))
            if name == "key":
                if row_node is not None:
                    raise Fatal("%s:%d: a second construction named key" % (src.name, src.line(m.start())))
                row_node = node
                continue
            sm = re.fullmatch(r'key \+ "([^"]*)"', name)
            if not sm:
                raise Fatal("%s:%d: %s name %r is not key or key + literal" % (src.name, src.line(m.start()), where, name))
            if sm.group(1) not in RECOGNISED:
                raise Fatal("%s:%d: %s part suffix %r is not one of %s" % (src.name, src.line(m.start()), where, sm.group(1), ",".join(RECOGNISED)))
            parts.append((sm.group(1), node, "%s:%d" % (src.name, src.line(m.start()))))

    visit(st, na, nb, {"parent": "<home>", "row.transform": "<row>"}, "SettingsNewRow")
    visit(st, da, db, {"row.transform": "<row>"}, "SettingsDecorateRow")
    visit(kb, ka, kb_end, {"rec.Cell.transform": "<row>_c"}, "SettingsKeybind")
    if row_node != "<home>":
        raise Fatal("the row object is not built under the Controls body (got %r)" % row_node)
    suffixes = sorted(p[0] for p in parts)
    if suffixes != sorted(RECOGNISED):
        raise Fatal("row parts %s, expected each of %s once" % (suffixes, sorted(RECOGNISED)))
    for suf, node, at in parts:
        want = "<row>" if suf in ROW_PARTS else "<row>_c"
        if node != want:
            raise Fatal("%s: part %s is under %s, not %s" % (at, suf, node, want))

    # 3. BuildControlsRows(Transform body): headings, rows, raw controls
    ra, rb = method_body(kb, "private static void BuildControlsRows(Transform body)")
    rows, headings, raw_controls = [], [], []
    for a, b in statements(kb, ra, rb):
        stmt = text_of(kb, (a, b))
        mstmt = re.sub(r"\s+", " ", kb.mask[a:b]).strip()
        if not UI_CALL.search(kb.mask[a:b]):
            continue
        m = re.fullmatch(r'KeybindHeading\(body, "([^"]*)", .*\)', stmt)
        if m:
            headings.append(m.group(1))
            continue
        m = re.fullmatch(r"for \(int (\w+) = ([^;]+); \1 < ([^;]+); \1\+\+\) SettingsKeybind\(body, \1\)", stmt)
        if m:
            lo = evaluate(m.group(2), consts, kb, a)
            hi = evaluate(m.group(3), consts, kb, a)
            if not (0 <= lo <= hi <= len(row_ids)):
                raise Fatal("%s:%d: loop bounds %d..%d outside the rows" % (kb.name, kb.line(a), lo, hi))
            rows.extend(range(lo, hi))
            continue
        m = re.fullmatch(r"SettingsKeybind\(body, KeybindRules\.(\w+)\)", stmt)
        if m and m.group(1) in consts:
            rows.append(consts[m.group(1)])
            continue
        m = re.fullmatch(r'UIFactory\.Create(?:Button|Text|Panel)\("(SKb[^"]*)", body,.*\)', stmt)
        if m and mstmt.startswith("UIFactory"):
            raw_controls.append(m.group(1))
            continue
        raise Fatal("%s:%d: unrecognised UI statement in BuildControlsRows: %r" % (kb.name, kb.line(a), stmt[:90]))
    dup = sorted({r for r in rows if rows.count(r) > 1})
    if dup:
        raise Fatal("rows built twice: %s" % [row_ids[r] for r in dup])

    # 4. every other "SKb"-named construction in these files, by resolved parent
    fm = re.search(r'\b(\w+)\s*=\s*new\s+GameObject\s*\(\s*"SetDetFoot"\s*\)', st.lit)
    pm = fm and re.search(r"\b%s\s*\.\s*transform\s*\.\s*SetParent\s*\(\s*(\w+)\s*\.\s*transform" % fm.group(1), st.mask)
    if not pm or resolve_parent(srcs, st, pm.group(1), pm.start()) != "SetDetail":
        raise Fatal("NativeUI.Settings.cs: SetDetFoot is not parented under SetDetail")
    chrome = []
    chain = [(kb, ka, kb_end), (st, na, nb), (st, da, db), (kb, ra, rb)]
    for src in (nui, kb, st):
        for m in CONSTRUCTOR.finditer(src.mask):
            if any(s is src and a <= m.start() < b for s, a, b in chain):
                continue
            args, _ = args_of(src, m.end() - 1)
            name = text_of(src, args[0])
            if not name.startswith('"' + PREFIX):
                continue
            if name == '"%s" + KeybindRules.RowIds[row]' % PREFIX or re.fullmatch(r'"SKb[^"]*"', name) is None:
                raise Fatal("%s:%d: SKb construction %r outside the Controls chain" % (src.name, src.line(m.start()), name))
            lit = name.strip('"')
            parent = re.sub(r"\s+", "", text_of(src, args[1])) if len(args) > 1 else ""
            anc = resolve_parent(srcs, src, parent, m.start())
            if anc in CHROME_ANCESTORS:
                chrome.append("%s (under %s)" % (lit, anc))
            elif anc == home:
                raw_controls.append(lit)
            else:
                raise Fatal("%s:%d: SKb construction %r: parent does not resolve to the Controls body or chrome" % (src.name, src.line(m.start()), lit))

    keys = sorted([PREFIX + row_ids[r] for r in rows] + raw_controls)
    return {
        "home": home,
        "rows": [PREFIX + row_ids[r] for r in rows],
        "raw_controls": sorted(raw_controls),
        "keys": keys,
        "parts": {"row": list(ROW_PARTS), "cell": list(CELL_PARTS)},
        "headings": headings,
        "chrome": sorted(chrome),
    }


def read_tree(root):
    plugin = os.path.join(root, "plugin")
    return {n: io.open(os.path.join(plugin, n), encoding="utf-8", newline="").read() for n in FILES}


def compare(base, cur):
    """The diff that matters: the key set and its home."""
    missing = sorted(set(base["keys"]) - set(cur["keys"]))
    added = sorted(set(cur["keys"]) - set(base["keys"]))
    problems = []
    if cur["home"] != base["home"]:
        problems.append("home %s != baseline %s" % (cur["home"], base["home"]))
    if len(cur["rows"]) != ROWS_EXPECTED:
        problems.append("%d Controls rows, expected exactly %d" % (len(cur["rows"]), ROWS_EXPECTED))
    return missing, added, problems


def check(texts, base):
    try:
        cur = harvest(texts)
    except Fatal as e:
        return "FATAL", str(e), None
    missing, added, problems = compare(base, cur)
    if missing or added or problems:
        return "RED", "missing=%s added=%s problems=%s" % (missing, added, problems), cur
    return "GREEN", "keys=%d rows=%d home=%s headings=%s chrome=%s" % (
        len(cur["keys"]), len(cur["rows"]), cur["home"], cur["headings"], cur["chrome"]), cur


def _sub(texts, name, old, new):
    t = dict(texts)
    if t[name].count(old) != 1:
        raise SystemExit("selftest refused: %s: anchor occurs %d times: %r" % (name, t[name].count(old), old[:70]))
    t[name] = t[name].replace(old, new)
    assert t[name] != texts[name]
    return t


DET = 'var det = UIFactory.CreatePanel("SetDetail", cols.transform, C_PANEL);'
PROBE = ' UIFactory.CreateButton("SKbProbe", det.transform, "", 14f, C_WHITE, C_BTN, () => { }, new Vector2(26, 26));'
GAME_LOOP = "for (int r = KeybindRules.FirstGameRow; r < KeybindRules.RowCount; r++) SettingsKeybind(body, r);"
HEAD_GAME = 'KeybindHeading(body, "SKbHeadGame", I18n.Tr("Game controls"));'

CASES = (
    # (id, kind, mutation, expected verdict, expected detail substring)
    ("M1-drop-one-row", "mutation",
     lambda t: _sub(t, "NativeUI.Keybinds.cs", GAME_LOOP, GAME_LOOP.replace("r = KeybindRules.FirstGameRow;", "r = KeybindRules.FirstGameRow + 1;")),
     "RED", "missing=['SKbMoveUp'] added=[]"),
    ("M2-unrecognised-part", "mutation",
     lambda t: _sub(t, "NativeUI.Keybinds.cs", 'CreateButton(key + "_x"', 'CreateButton(key + "_y"'),
     "FATAL", "part suffix '_y'"),
    ("M3-raw-control-under-controls", "mutation",
     lambda t: _sub(t, "NativeUI.Settings.cs", DET, DET + "\n            var probeBody = new GameObject(\"SubControls\");" + PROBE.replace("det.transform", "probeBody.transform")),
     "RED", "added=['SKbProbe']"),
    ("M4-part-under-the-wrong-parent", "mutation",
     lambda t: _sub(t, "NativeUI.Keybinds.cs", 'CreateButton(key + "_r", rec.Cell.transform', 'CreateButton(key + "_r", rec.Row.transform'),
     "FATAL", "does not resolve"),
    ("C1-chrome-button-under-SetDetail", "control",
     lambda t: _sub(t, "NativeUI.Settings.cs", DET, DET + PROBE),
     "GREEN", "'SKbProbe (under SetDetail)'"),
    ("C2-chrome-heading-under-controls", "control",
     lambda t: _sub(t, "NativeUI.Keybinds.cs", HEAD_GAME, HEAD_GAME + "\n            " + HEAD_GAME.replace("SKbHeadGame", "SKbHeadExtra")),
     "GREEN", "'SKbHeadExtra'"),
)


def selftest(texts, base):
    ok = True
    v, d, _ = check(texts, base)
    print("[t5] %s unmutated: %s %s" % ("PASS" if v == "GREEN" else "FAIL", v, d))
    ok &= v == "GREEN"
    for cid, kind, mut, want, needle in CASES:
        v, d, _ = check(mut(texts), base)
        good = v == want and needle in d
        ok &= good
        print("[t5] %s %s %s: %s %s" % ("PASS" if good else "FAIL", kind, cid, v, d))
    return ok


def main(argv=None):
    global CS
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("check", "capture", "selftest"))
    ap.add_argument("--tree", default=REPO)
    ap.add_argument("--baseline", default=BASELINE)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    CS = _cs()
    texts = read_tree(a.tree)
    if a.mode == "capture":
        if not a.out:
            print("capture needs --out", file=sys.stderr)
            return 2
        if os.path.exists(a.out):
            print("refused: %s exists; a baseline is never overwritten" % a.out, file=sys.stderr)
            return 2
        cur = harvest(texts)
        io.open(a.out, "w", encoding="utf-8", newline="\n").write(json.dumps(cur, indent=1) + "\n")
        print("captured %d keys -> %s" % (len(cur["keys"]), a.out))
        return 0
    base = json.load(io.open(a.baseline, encoding="utf-8"))
    if a.mode == "check":
        v, d, _ = check(texts, base)
        print("[t5] %s %s" % (v, d))
        return 0 if v == "GREEN" else 1
    return 0 if selftest(texts, base) else 1


if __name__ == "__main__":
    raise SystemExit(main())
