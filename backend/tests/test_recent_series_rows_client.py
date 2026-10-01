"""Report 3 follow-up (2026-10-01): the Recent Ranked Series page is one TMP element per row.

The page used to be ONE TMP element holding all 50 rows, so a single name glyph no
font carried blanked the whole page (report 3). The glyph sanitiser removes that
cause; this change bounds the class: each series row (its bet sub-lines included)
is painted into its own pooled element (NativeUI.ShowRecentSeriesRows), so any
future row TMP cannot lay out costs that row, not the page. txtRecentSeries keeps
only the panel's two status lines.

Structural gates over the comments-stripped code (literals kept), blocks found on
the mask (learnings #342/#431/#441). Each gate has an in-memory mutation control
that must turn it red; the pre-change tree (e421286e) is run through the same
findings() by the sitting's revert control (logged, not pinned here).
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

import pytest

from _cs_structure import mask_code, strip_comments_only

NATIVE_PATH = Path(__file__).resolve().parents[2] / "plugin" / "NativeUI.cs"

REFRESH = "private static void RefreshRecentSeries()"
SHOW = "private static void ShowRecentSeriesRows(List<string> rows)"
BUILD_PAGE = "private static void BuildPage(Transform canvasParent)"
STATUS_LINES = ('"Loading recent series..."', '"No recent series"')


@functools.lru_cache(maxsize=None)
def _native() -> str:
    return NATIVE_PATH.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=8)
def _views(src: str) -> tuple:
    return mask_code(src), strip_comments_only(src)


@functools.lru_cache(maxsize=64)
def _code(src: str, signature: str) -> str:
    """The one block `signature` opens (found on the mask), cut from the
    comments-stripped view at the same offsets. Exactly one match."""
    masked, code = _views(src)
    at = masked.find(signature)
    if at < 0:
        raise AssertionError("signature not found: %r" % signature)
    if masked.find(signature, at + 1) >= 0:
        raise AssertionError("more than one block matches %r" % signature)
    open_brace = masked.find("{", at + len(signature))
    depth = 0
    for i in range(open_brace, len(masked)):
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return code[open_brace:i + 1]
    raise AssertionError("unbalanced block after %r" % signature)


def _for_body(block: str) -> str:
    """The body of the page loop `for(int i=start;i<end;i++)` in RefreshRecentSeries."""
    m = re.search(r"for\s*\(\s*int\s+i\s*=\s*start\s*;\s*i\s*<\s*end\s*;\s*i\+\+\s*\)\s*\{", block)
    if not m:
        raise AssertionError("page loop not found")
    depth, start = 0, m.end() - 1
    for i in range(start, len(block)):
        if block[i] == "{":
            depth += 1
        elif block[i] == "}":
            depth -= 1
            if depth == 0:
                return block[start:i + 1]
    raise AssertionError("unbalanced page loop")


def findings(native: str) -> list:
    out = []
    blocks = {}
    for key, sig in (("refresh", REFRESH), ("show", SHOW), ("build", BUILD_PAGE)):
        try:
            blocks[key] = _code(native, sig)
        except AssertionError as e:
            out.append(str(e))
            blocks[key] = ""
    refresh, show, build = blocks["refresh"], blocks["show"], blocks["build"]

    # A. RefreshRecentSeries: the status element only ever gets a status literal,
    # each status write first hides the rows, and the page goes to the row pool.
    writes = re.findall(r"UIFactory\.SetText(?:Raw)?\(\s*txtRecentSeries\s*,\s*([^;]*?)\)\s*;", refresh)
    for arg in writes:
        if arg.strip() not in STATUS_LINES:
            out.append("A: txtRecentSeries is written with a non-status value: %s" % arg.strip()[:60])
    for lit in STATUS_LINES:
        n = len(re.findall(r"ShowRecentSeriesRows\(\s*null\s*\)\s*;\s*UIFactory\.SetText\(\s*txtRecentSeries\s*,\s*"
                           + re.escape(lit) + r"\s*\)", refresh))
        if n != 1:
            out.append("A: the status line %s is shown %d times after ShowRecentSeriesRows(null), not 1" % (lit, n))
    n_show = len(re.findall(r"ShowRecentSeriesRows\(\s*rows\s*\)", refresh))
    if n_show != 1:
        out.append("A: ShowRecentSeriesRows(rows) occurs %d times, not 1" % n_show)
    if not re.search(r"var\s+rows\s*=\s*new\s+List<string>", refresh):
        out.append("A: no per-row list (var rows=new List<string>) in RefreshRecentSeries")
    # B. one row per entry: the loop adds exactly two ways (multimode, 1v1), the 1v1
    # row's text is declared INSIDE the loop, and no row is ever appended to another.
    try:
        body = _for_body(refresh)
    except AssertionError as e:
        out.append("B: " + str(e))
        body = ""
    n_add = len(re.findall(r"\brows\.Add\(", body))
    if n_add != 2:
        out.append("B: rows.Add occurs %d times in the page loop, not 2" % n_add)
    if not re.search(r"\bstring\s+txt\s*=", body):
        out.append("B: the 1v1 row text is not declared inside the page loop")
    if re.search(r"\bstring\s+txt\s*=", refresh[:refresh.find(body)] if body else refresh):
        out.append("B: a page-wide txt accumulator is declared before the loop")
    if re.search(r"\brows\s*\[[^\]]*\]\s*\+?=", refresh):
        out.append("B: a row is written by index (rows[...] = / +=), so two entries can share one element")
    # C. ShowRecentSeriesRows: rows -> pool elements, status element hidden while rows show.
    if not re.search(r"statusGO\.SetActive\(\s*rows\s*==\s*null\s*\)", show):
        out.append("C: the status element is not hidden while rows show")
    if not re.search(r"UIFactory\.CreateText\([^;]*recentSeriesRowsParent", show):
        out.append("C: pool elements are not created under recentSeriesRowsParent")
    if len(re.findall(r"UIFactory\.SetTextRaw\(\s*recentSeriesRows\[i\]\s*,", show)) != 1:
        out.append("C: row i is not written to pool element i exactly once")
    if re.search(r"SetText(?:Raw)?\(\s*txtRecentSeries", show):
        out.append("C: ShowRecentSeriesRows writes into the status element")
    if not re.search(r"go\.SetActive\(\s*on\s*\)", show):
        out.append("C: spare pool elements are not hidden")
    # D. pool hygiene (#147/#149/#150): cleared on every BuildPage, parent re-pointed at the build.
    if not re.search(r"recentSeriesRows\.Clear\(\)\s*;\s*recentSeriesRowsParent\s*=\s*null", build):
        out.append("D: BuildPage does not clear the row pool and its parent")
    masked, code = _views(native)
    n_parent = len(re.findall(r"txtRecentSeries=UIFactory\.CreateText\(\"RST\",rsSV\.content\.transform[^;]*;"
                              r"recentSeriesRows\.Clear\(\);recentSeriesRowsParent=rsSV\.content\.transform;", code))
    if n_parent != 1:
        out.append("D: the build line re-points the pool %d times, not 1" % n_parent)
    return out


def test_recent_series_is_one_element_per_row():
    assert findings(_native()) == []


def _mutate(find: str, repl: str, count: int = 1) -> str:
    src = _native()
    assert src.count(find) == count, (find, src.count(find))
    return src.replace(find, repl)


MUTANTS = [
    ("one_element_again", "            ShowRecentSeriesRows(rows);",
     "            UIFactory.SetText(txtRecentSeries,string.Join(\"\",rows));"),
    ("rows_folded_into_one", "                rows.Add(txt);",
     "                if(rows.Count==0)rows.Add(txt);else rows[0]+=txt;"),
    ("loading_keeps_rows", "ShowRecentSeriesRows(null);UIFactory.SetText(txtRecentSeries,\"Loading recent series...\");",
     "UIFactory.SetText(txtRecentSeries,\"Loading recent series...\");"),
    ("status_never_hidden", "statusGO.SetActive(rows==null);", "statusGO.SetActive(true);"),
    ("row_into_status", "UIFactory.SetTextRaw(recentSeriesRows[i],", "UIFactory.SetTextRaw(txtRecentSeries,"),
    ("pool_not_cleared", "            recentSeriesRows.Clear();recentSeriesRowsParent=null;", "            "),
    ("parent_not_set", "recentSeriesRows.Clear();recentSeriesRowsParent=rsSV.content.transform;", ""),
]


@pytest.mark.parametrize("name,find,repl", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_mutation_control_turns_the_gate_red(name, find, repl):
    assert findings(_mutate(find, repl)) != [], name
