"""Merge pass 5, item 4: the title ladders client (the five-tier layout) against
the server's CURRENT answer, whose five-tier half has not landed.

Required behaviour, against every answer the current server gives: the client
shows what it shows today, or the new layout with the old data. It never
throws, never hides a title the player holds, and never shows a rung the
server did not send.

How it is proven. The shipped parser (ApiClient's title-ladder members and the
json helpers they call) and the Titles section's text and rung members
(TitleLaddersUI) are copied out of the plugin sources at test time, compiled
beside the real plugin/TitleLadderRules.cs (tools/tests/title-ladders-compat)
and run over answer files. This file is the oracle: it reads the same answers
and compares what the client parsed, planned, decided and wrote.

The answers:
  * fixtures/title_ladders_current_answer.json: the live answer of the current
    server, GET /api/v1/players/{steam_id}/title-ladders through the edge at
    2026-10-02T00:48:30Z, for an account that owns no rung. Only the steam_id
    is replaced (by a placeholder); every other key and value is the
    server's, in its order, re-indented. It has
    eight lines of six rungs each, and the rat line's King and Queen share a
    tier (max_tier 5, six rungs).
  * built from it here: the same answer with rungs owned and worn (a started
    line, a line held at the top, a line holding only a middle rung); with one
    rung's sku removed; cut short; empty; ladders null; and the same answer
    with every key the five-tier server build appends.

What the client does with each key the five-tier server adds (asserted by
test_the_section_reads_only_these_appended_keys and the new-server case):
  unit      -> the count's wording ("15 games", "8 wins"); absent reads "series".
  condition -> the dropdown's rule sentence, translated as data; absent reads
               the old "Wear it and finish ranked series".
  streak    -> "Current run: N" on the progress line; absent or null prints none.
  group, kind, modes, reached -> parsed and kept on the line, displayed nowhere.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGIN = os.path.join(ROOT, "plugin")
PROJ_DIR = os.path.join(ROOT, "tools", "tests", "title-ladders-compat")
PROJ = os.path.join(PROJ_DIR, "TitleLaddersCompat.csproj")
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "title_ladders_current_answer.json")
# Merge pass 6: the five-tier server half has landed (main e9a3f1e1). This is
# its real answer, asked of main.app's route on a schema built from migrations
# 331 and 365 for an account that owns no rung, steam_id replaced by the same
# placeholder; every other key and value is the server's. test_title_ladder_
# route_live.py checks the route still answers exactly these key sets.
FIXTURE_FIVE = os.path.join(os.path.dirname(__file__), "fixtures", "title_ladders_five_tier_answer.json")

# The members copied out of the plugin, by the text that starts each one.
API_MEMBERS = [
    "internal class TitleLadderRung",
    "internal class TitleLadderLine",
    "internal class TitleLadders",
    "internal static string PcTopLevel(string json, string key)",
    "private static string PcRawValue(string json, int j)",
    "internal static string PcStr(string raw)",
    "internal static int PcInt(string raw)",
    "internal static bool PcBool(string raw)",
    "internal static long PcLong(string raw)",
    "internal static string[] PcStrArray(string rawArray)",
    "private static List<string> SliceTopLevelObjects(string json)",
    "internal static TitleLadderRung ParseTitleLadderRung(string obj)",
    "internal static TitleLadders ParseTitleLadders(string json)",
]
UI_MEMBERS = [
    "private const int MAX_LINES",
    "private static List<TitleLadderRules.Rung> RulesRungs(ApiClient.TitleLadderLine ln, HashSet<string> listedOwned)",
    "private static string UnitCount(string unit, int n)",
    "private static string ReasonText(TitleLadderRules.Decision d, string unit)",
    "private static string LadderName(string serverName)",
    "private static string TierNames(ApiClient.TitleLadderLine ln, int tier)",
    "private static string ProgressText(ApiClient.TitleLadderLine ln, TitleLadderRules.Decision d)",
]


def _read(name):
    with open(os.path.join(PLUGIN, name), encoding="utf-8-sig") as f:
        return f.read().replace("\r\n", "\n")


def _member(src, start, where):
    """The member that begins with `start` (which must occur exactly once):
    through its closing brace, or through the `;` of a field or an
    expression-bodied member. Strings, chars and comments are skipped, so a
    brace inside a literal does not count."""
    assert src.count(start) == 1, ("member start not unique", where, start, src.count(start))
    i = src.index(start)
    n = len(src)
    depth = 0
    k = i
    while k < n:
        c = src[k]
        if src.startswith("//", k):
            k = src.index("\n", k)
            continue
        if src.startswith("/*", k):
            k = src.index("*/", k) + 2
            continue
        if src.startswith('@"', k):
            k += 2
            while not (src[k] == '"' and src[k + 1] != '"'):
                k += 2 if src[k] == '"' else 1
            k += 1
            continue
        if c == '"':
            k += 1
            while src[k] != '"':
                k += 2 if src[k] == "\\" else 1
            k += 1
            continue
        if c == "'":
            k += 1
            while src[k] != "'":
                k += 2 if src[k] == "\\" else 1
            k += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        elif c == ";" and depth == 0:
            return src[i:k + 1]
        k += 1
    raise AssertionError(("member not closed", where, start))


def _public(member):
    return re.sub(r"^private ", "internal ", member)


def _extracted():
    api = _read("ApiClient.cs")
    ui = _read("TitleLaddersUI.cs")
    out = ["// Generated by test_title_ladders_current_server_compat.py from the plugin sources.",
           "using System;", "using System.Collections.Generic;", "using System.Text;", "",
           "namespace CompetitiveRounds", "{", "    internal static class ApiClient", "    {"]
    out += [_public(_member(api, s, "ApiClient.cs")) for s in API_MEMBERS]
    out += ["    }", "    internal static class TitleLaddersUI", "    {",
            "        // A locally loaded board: none here, as on a seat with no dev board.",
            "        private static object devBoard = null;"]
    out += [_public(_member(ui, s, "TitleLaddersUI.cs")) for s in UI_MEMBERS]
    out += ["    }", "}", ""]
    return "\n".join(out)


def _answer(path=FIXTURE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _own(answer):
    """The answer with rungs owned and worn: rat started (tiers 1 and 2 held,
    tier 2 worn), cat held at the top, dog holding only a middle rung."""
    owned = json.loads(json.dumps(answer))
    for ln in owned["ladders"]:
        rs = ln["rungs"]
        if ln["line"] == "rat":      # started: tiers 1 and 2 held, the tier-2 rung worn
            for r in rs:
                if r["tier"] <= 2:
                    r["owned"] = True
                r["active"] = r["tier"] == 2
            ln["games"] = rs[2]["threshold"] - 1
        elif ln["line"] == "cat":    # held at the top
            for r in rs:
                r["owned"] = True
            ln["games"] = rs[-1]["threshold"] + 3
        elif ln["line"] == "dog":    # only a middle rung held
            rs[2]["owned"] = True
            ln["games"] = rs[2]["threshold"]
    owned["active_line"] = "rat"
    return owned


def _variants():
    """Every answer file the client is run over, by file name."""
    cur = _answer()
    v = {"current.json": cur}
    owned = _own(cur)
    v["owned.json"] = owned
    five = _answer(FIXTURE_FIVE)
    v["five.json"] = five
    v["fiveowned.json"] = _own(five)

    nosku = json.loads(json.dumps(owned))
    del nosku["ladders"][0]["rungs"][3]["sku"]
    v["nosku.json"] = nosku

    new = json.loads(json.dumps(owned))
    for ln in new["ladders"]:
        ln.update({"group": "animal", "kind": "ladder", "unit": "games", "modes": "any",
                   "condition": "Wear it and play ranked games", "streak": None})
        for r in ln["rungs"]:
            r["reached"] = ln["games"] >= r["threshold"]
    new["ladders"][0].update({"unit": "streak", "streak": 3})
    v["newserver.json"] = new

    v["empty.json"] = ""
    v["nullladders.json"] = {"steam_id": "x", "active_line": None, "ladders": None}
    v["truncated.json"] = json.dumps(cur)[: len(json.dumps(cur)) // 2]
    return v


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    if shutil.which("dotnet") is None:
        pytest.fail("dotnet is not on PATH: the compat program cannot be built")
    work = tmp_path_factory.mktemp("tlc")
    gen = work / "Extracted.g.cs"
    gen.write_text(_extracted(), encoding="utf-8")
    b = subprocess.run(["dotnet", "build", PROJ, "-c", "Release", "-nologo", "-v", "q",
                        "-p:ExtractedSource=" + str(gen),
                        "-p:IntermediateOutputPath=" + str(work / "obj") + os.sep,
                        "-p:OutDir=" + str(work / "bin") + os.sep],
                       capture_output=True, text=True)
    assert b.returncode == 0, ("build failed", b.stdout[-3000:], b.stderr[-2000:])
    files = []
    for name, body in _variants().items():
        p = work / name
        p.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
        files.append(str(p))
    exe = os.path.join(str(work / "bin"), "TitleLaddersCompat.dll")
    r = subprocess.run(["dotnet", exe] + files, capture_output=True, text=True, encoding="utf-8")
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        row = {"_t": parts[0]}
        for p in parts[1:]:
            k, _, val = p.partition("=")
            row[k] = val
        rows.append(row)
    return r.returncode, rows, r.stdout


def _rows(rows, kind, file):
    """The rows of one type (ANSWER, PLAN, LINE) for one answer file. The
    type is stored under "_t": a LINE row has its own field named kind."""
    return [x for x in rows if x["_t"] == kind and x.get("file") == file]


def _lines(rows, file):
    """The LINE rows of one answer file, one per ladder the answer sends:
    a run that printed none (or too few) fails here, never passes empty."""
    got = _rows(rows, "LINE", file)
    want = len(_variants()[file]["ladders"])
    assert want > 0 and len(got) == want, (file, len(got), want)
    return got


def _split(s):
    return [] if s == "" else s.split(",")


def test_no_answer_makes_the_client_throw(run):
    rc, rows, out = run
    assert rc == 0 and not [x for x in rows if x["_t"] == "THREW"], out
    files = {x["file"] for x in rows if x["_t"] == "ANSWER"}
    assert files == set(_variants()), (sorted(files), out)


def test_bodies_with_no_ladders_read_as_no_board(run):
    """An empty, cut-short or ladders-null body is no board (the caller shows
    UNAVAILABLE), never a board of zeroes."""
    _, rows, out = run
    for f in ("empty.json", "nullladders.json", "truncated.json"):
        a = _rows(rows, "ANSWER", f)
        assert len(a) == 1 and a[0]["null"] == "True", (f, out)


@pytest.mark.parametrize("file", ["current.json", "owned.json", "newserver.json",
                                  "five.json", "fiveowned.json"])
def test_every_rung_shown_is_a_rung_the_server_sent_and_none_is_dropped(run, file):
    """Line for line and rung for rung, in the server's order: no rung is
    added, none is dropped, every line renders, and the listing rows folded
    into the entries are exactly the rungs sent."""
    _, rows, out = run
    ans = _variants()[file]
    lines = _lines(rows, file)
    assert [x["line"] for x in lines] == [ln["line"] for ln in ans["ladders"]], out
    for x, ln in zip(lines, ans["ladders"]):
        assert _split(x["skus"]) == [r["sku"] for r in ln["rungs"]], (file, ln["line"], x["skus"])
        assert _split(x["tiers"]) == [str(r["tier"]) for r in ln["rungs"]], (file, ln["line"])
        assert len(_split(x["states"])) == len(ln["rungs"]), (file, ln["line"], x["states"])
    plan = _rows(rows, "PLAN", file)[0]
    assert _split(plan["rendered"]) == [ln["line"] for ln in ans["ladders"]], plan
    assert plan["unrendered"] == "0", plan
    assert _split(plan["folded"]) == sorted(r["sku"] for ln in ans["ladders"] for r in ln["rungs"]), plan


def test_a_rung_without_a_sku_is_dropped_and_no_other_is(run):
    _, rows, out = run
    ans = _variants()["nosku.json"]
    for x, ln in zip(_lines(rows, "nosku.json"), ans["ladders"]):
        assert _split(x["skus"]) == [r["sku"] for r in ln["rungs"] if "sku" in r], (ln["line"], x["skus"])


@pytest.mark.parametrize("file", ["owned.json", "newserver.json", "fiveowned.json"])
def test_every_title_the_player_holds_is_shown_and_held(run, file):
    """Every owned rung is parsed as owned on a rendered line; the held tier is
    the highest owned tier; the rung that names it is owned, and is the worn
    one when one is worn; a line held at the top is Maxed."""
    _, rows, out = run
    ans = _variants()[file]
    rendered = _split(_rows(rows, "PLAN", file)[0]["rendered"])
    for x, ln in zip(_lines(rows, file), ans["ladders"]):
        own = [r for r in ln["rungs"] if r.get("owned")]
        assert _split(x["owned"]) == [r["sku"] for r in own], (ln["line"], x["owned"])
        if not own:
            assert x["held"] == "0" and x["heldsku"] == "-", (ln["line"], x)
            continue
        assert ln["line"] in rendered, (ln["line"], rendered)
        top = max(r["tier"] for r in own)
        assert x["held"] == str(top), (ln["line"], x["held"], top)
        worn = [r["sku"] for r in own if r["tier"] == top and r.get("active")]
        assert x["heldsku"] in ([worn[0]] if worn else [r["sku"] for r in own if r["tier"] == top]), (ln["line"], x)
        if top == ln["max_tier"]:
            assert x["label"] == "Maxed", (ln["line"], x["label"])


@pytest.mark.parametrize("file", ["current.json", "owned.json"])
def test_the_current_answer_reads_in_the_old_wording(run, file):
    """No appended key on the current answer: every one parses as absent, no
    run is printed, and every count reads in series (what that server
    counts), as the client shows it today."""
    _, rows, out = run
    for x in _lines(rows, file):
        for k in ("unit", "group", "kind", "modes", "condition"):
            assert x[k] == "null", (x["line"], k, x[k])
        assert x["has_streak"] == "False" and x["reached"] == "", (x["line"], x)
        assert "Current run" not in x["progress"], (x["line"], x["progress"])
        if x["held"] != "0":
            assert " series" in x["progress"], (x["line"], x["progress"])
        else:
            assert x["progress"].startswith("Not started"), (x["line"], x["progress"])
        for unit in (" games", " wins", " losses", " gold", " in a row"):
            assert unit not in x["progress"] and unit not in x["why"], (x["line"], unit, x)


def test_the_new_server_keys_pass_through_and_change_only_the_wording(run):
    _, rows, out = run
    ans = _variants()["newserver.json"]
    old = {x["line"]: x for x in _lines(rows, "owned.json")}
    for x, ln in zip(_lines(rows, "newserver.json"), ans["ladders"]):
        for k in ("unit", "group", "kind", "modes", "condition"):
            assert x[k] == ln[k], (ln["line"], k, x[k])
        assert _split(x["reached"]) == [r["sku"] for r in ln["rungs"] if r["reached"]], (ln["line"], x["reached"])
        assert x["has_streak"] == ("True" if ln["streak"] is not None else "False"), (ln["line"], x)
        for k in ("skus", "owned", "held", "next", "label", "reason", "heldsku", "states"):
            assert x[k] == old[ln["line"]][k], ("an appended key moved a decision", ln["line"], k)
        if x["held"] != "0":
            want = " in a row" if ln["unit"] == "streak" else " games"
            assert want in x["progress"] and " series" not in x["progress"], (ln["line"], x["progress"])
            assert ("Current run: 3" in x["progress"]) == (ln["streak"] == 3), (ln["line"], x["progress"])


UNIT_WORDS = {"games": " games", "wins": " wins", "losses": " losses", "gold": " gold",
              "streak": " wins in a row"}


@pytest.mark.parametrize("file", ["five.json", "fiveowned.json"])
def test_the_landed_five_tier_answer_reads_in_its_own_units(run, file):
    """The five-tier server's REAL answer (merge pass 6): every line renders,
    every appended key reaches the line as the server sent it, a held line
    counts in the line's own unit (never "series"), a line the server sends a
    streak for prints its run, and an unheld line reads Not started."""
    _, rows, out = run
    ans = _variants()[file]
    plan = _rows(rows, "PLAN", file)[0]
    assert plan["unrendered"] == "0", plan
    for x, ln in zip(_lines(rows, file), ans["ladders"]):
        for k in ("unit", "group", "kind", "modes", "condition"):
            assert x[k] == ln[k], (ln["line"], k, x[k], ln[k])
        assert _split(x["reached"]) == [r["sku"] for r in ln["rungs"] if r["reached"]], (ln["line"], x["reached"])
        assert x["has_streak"] == ("True" if ln["streak"] is not None else "False"), (ln["line"], x)
        if x["held"] == "0":
            assert x["progress"].startswith("Not started"), (ln["line"], x["progress"])
            continue
        assert UNIT_WORDS[ln["unit"]] in x["progress"] and " series" not in x["progress"], (
            ln["line"], ln["unit"], x["progress"])
        assert ("Current run: %s" % ln["streak"] in x["progress"]) == (ln["streak"] is not None), (
            ln["line"], x["progress"])


def test_the_five_tier_fixture_carries_the_appended_keys_and_no_account_id():
    """The five-tier fixture is the five-tier shape (the current fixture's keys
    plus the ones that build appends) and carries no 17-digit value."""
    with open(FIXTURE_FIVE, encoding="utf-8") as f:
        raw = f.read()
    assert not re.search(r"\d{17}", raw)
    a = json.loads(raw)
    assert set(a) == {"steam_id", "active_line", "ladders"} and a["steam_id"] == "STEAM-ID-PLACEHOLDER"
    assert len(a["ladders"]) == 32
    for ln in a["ladders"]:
        assert set(ln) == {"line", "name", "games", "tier", "max_tier", "next_tier", "next_threshold",
                           "next_names", "games_to_next", "rungs",
                           "group", "kind", "unit", "modes", "condition", "streak"}, ln["line"]
        assert ln["unit"] in UNIT_WORDS, (ln["line"], ln["unit"])
        for r in ln["rungs"]:
            assert set(r) == {"tier", "sku", "item_id", "name", "description", "rarity", "preview_color",
                              "threshold", "price", "owned", "active", "reached"}, (ln["line"], r.get("sku"))


def test_the_section_reads_only_these_appended_keys():
    """The five-tier keys the Titles section reads: unit, condition and the
    streak. group, kind, modes and reached are parsed and displayed nowhere,
    and the condition falls back to the old rule when the server sends none."""
    ui = _read("TitleLaddersUI.cs")
    read = set(re.findall(r"\bln\.(unit|condition|has_streak|streak|group|kind|modes)\b", ui))
    read |= set(re.findall(r"\.(reached)\b", ui))
    assert read == {"unit", "condition", "has_streak", "streak"}, sorted(read)
    drop = _member(ui, "private static void PaintDrop(ApiClient.TitleLadderLine ln)", "TitleLaddersUI.cs")
    assert re.search(r'!string\.IsNullOrEmpty\(ln\.condition\)\s*\?\s*LadderName\(ln\.condition\)\s*:\s*'
                     r'I18n\.Tr\("Wear it and finish ranked series"\)', drop), "the condition fallback moved"


def test_the_fixture_is_the_current_answer_shape_with_no_account_id():
    """The fixture keeps the current server's keys (none appended) and carries
    no 17-digit value."""
    with open(FIXTURE, encoding="utf-8") as f:
        raw = f.read()
    assert not re.search(r"\d{17}", raw)
    a = json.loads(raw)
    assert set(a) == {"steam_id", "active_line", "ladders"}
    for ln in a["ladders"]:
        assert set(ln) == {"line", "name", "games", "tier", "max_tier", "next_tier", "next_threshold",
                           "next_names", "games_to_next", "rungs"}, ln["line"]
        for r in ln["rungs"]:
            assert set(r) == {"tier", "sku", "item_id", "name", "description", "rarity", "preview_color",
                              "threshold", "price", "owned", "active"}, (ln["line"], r.get("sku"))
