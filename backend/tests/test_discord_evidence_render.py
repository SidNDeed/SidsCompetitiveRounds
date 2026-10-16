"""Admin evidence report, item 1a-7: the render plan, the PNG worker and its
isolation (design 5.2 and 5.6, phase 1a). No database.

  P12 (5.2) `_aer_plan` is a bijection over every field of the served page:
      each field is shown by exactly one plan item, as the text the field's
      value reads as, in item order; every item kind is a 1a kind (no class,
      mark or swatch); no escaped-set code point reaches any item text; each
      cell carries its catalog key's provenance letter; the legend is the 1a
      lines of 5.6. Fixtures: a served game page, the spread (summary) page
      and a control page with escapes, `$` and extreme values.
  P12 stage control: a seat window's `flag_obs` reads the same at the
      response, the BotPage, the plan and the text fallback.
  P23 (5.2) a render worker that never answers gives the text fallback in
      time and is ended; the next report renders a PNG from a replacement
      worker; a /compare chart taking `_mpl_render_lock` meanwhile succeeds.
  Worker protocol: one framed plan in, one framed reply out, an error reply
      for a plan it refuses, and the input's end stops it.
  P14 and P12's drawn-text comparison need matplotlib (the bot image has it):
      the drawn text equals the plan text, cells sit on the one neutral fill,
      other items on the page background, and the status band reads
      `UNCOLORED (absent)`. They skip where matplotlib is not installed.
"""

import asyncio
import copy
import io
import json
import os
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from test_discord_evidence_bot import (ADMIN, _Api, _Interaction, ae, bot_ns,  # noqa: E402
                                       game_body, summary_body)
import aer_render_worker as worker  # noqa: E402

PNG = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))
BS = chr(0x5C)
LEGEND_1A = [
    "- = not recorded",
    "? = unknown",
    "T = own baseline truncated",
    "FLAG = kept only when an advisory heuristic fired; not ranked",
    "S SELF, P PEER, O OTHER, D derived, F FLAG, M MEAS",
    "max/median of n = window over n values",
    BS + "u{..} = escaped character",
    "ranks are mid-ranks in [0,1]",
]
GAME_SCALARS = ("code", "ended_at", "is_ranked", "invalidated", "rounds", "series_id",
                "match_id")
UNCHECKED = ("population", "baseline", "registry", "windows")
REQ = {"shape": "game", "code": "0" * 12, "page": 1}


def run(coro):
    return asyncio.run(coro)


# ── fixtures ──────────────────────────────────────────────────────────────

def control_body():
    """A game page with an escaped name and reason, `$` text, the Arabic
    letter mark, U+200E and U+200F raw in an unchecked population value, a
    backslash, an
    invalidated game, and extreme or unknown cell values."""
    body = game_body()
    base = [e for e in ae.REPORT_REGISTRY if not e.is_window][:2]
    body["subjects"][1]["name"] = ae._aer_enc("$x^2$ " + chr(0x200F) + BS)
    body["population"]["key"] = "all" + chr(0x61C) + chr(0x200E) + chr(0x200F) + "`" + BS
    body["population"]["truncated"] = ["seat" + chr(0x202E)]
    body["baseline"]["note"] = {"k": [1, chr(0x1B)]}
    body["registry"]["census"] = {"macro": 3}
    g = body["games"][0]
    g["invalidated"] = ae._aer_enc("cheat $1")
    g["series_id"] = "s" * 32
    cells = [[base[0].ki, 1e308, -0.0, 3, "truncated", 0.5, 1.0, 40, "ok"],
             [base[1].ki, None, None, None, "none", None, None, None, "unknown"]]
    g["seats"][0]["cells"] = cells
    g["flags"][0]["reason"] = ae._aer_enc("macro" + chr(0x1B) + "[31m")
    g["flags"].append({"reason": "manual", "subject": None, "reviewed": True,
                       "current": False, "created_at": "2026-10-15T00:00:00+00:00"})
    return body


def spread_body():
    body = summary_body()
    body["windows"][0]["flag_obs"] = 7
    return body


# ── an independent reading of the served page ─────────────────────────────

def api_fields(body):
    out = [("shape",), ("page",), ("pages",), ("rules", "report")]
    for i, _s in enumerate(body["subjects"]):
        out += [("subjects", i, "name"), ("subjects", i, "steam_id")]
    for gi, g in enumerate(body["games"]):
        out += [("games", gi, k) for k in GAME_SCALARS]
        for si, seat in enumerate(g["seats"]):
            out += [("games", gi, "seats", si, "subject"), ("games", gi, "seats", si, "reporter")]
            for ci, _c in enumerate(seat["cells"]):
                out += [("games", gi, "seats", si, "cells", ci, slot)
                        for slot in ae.AER_WIRE["1a"]["seat"]]
        for fi, f in enumerate(g["flags"]):
            out += [("games", gi, "flags", fi, k) for k in f]
    for wi, w in enumerate(body.get("windows", [])):
        out += [("windows", wi, k) for k in w]
    for si, s in enumerate(body.get("summary", [])):
        out.append(("summary", si, "oi"))
        for ci, _c in enumerate(s["cells"]):
            out += [("summary", si, "cells", ci, slot) for slot in ae.AER_WIRE["1a"]["summary"]]
    for row in body["catalog"]:
        out += [("catalog", row["ki"], k) for k in row]
    for part in ("population", "baseline", "registry"):
        out += [(part, k) for k in body[part]]
    return out


def lookup(body, path):
    if path == ("rules", "report"):
        return body["rules"]["report"]
    if path[0] == "catalog":
        return next(r for r in body["catalog"] if r["ki"] == path[1])[path[2]]
    node = body
    for i, step in enumerate(path):
        if isinstance(node, list) and isinstance(step, str):
            table = "seat" if path[0] == "games" else "summary"
            return node[ae.AER_WIRE["1a"][table].index(step)]
        node = node[step]
    return node


def _plain(value, unchecked):
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return ae._aer_enc(value) if unchecked else value
    return ae._aer_enc(json.dumps(value, sort_keys=True, separators=(",", ":")))


def expect(body, path):
    value = lookup(body, path)
    last, unchecked = path[-1], path[0] in UNCHECKED
    if path == ("rules", "report"):
        return "UNCOLORED (absent)"
    if path[0] == "games" and len(path) == 3:
        if last == "is_ranked":
            return "ranked" if value else "casual"
        if last == "invalidated":
            return "valid" if value is None else "INVALIDATED " + value
        if last == "rounds":
            return "-".join(_plain(r, True) for r in value)
    if path[0] == "games" and path[2] == "seats" and len(path) == 5:
        return ("R" if value else "-") if last == "reporter" else repr(value)
    if path[0] == "games" and path[2] == "flags" and last == "subject":
        return "-" if value is None else "#%d" % value
    if path[0] == "windows" and last == "subj":
        return " ".join(_plain(x, True) for x in value)
    if "cells" in path and last == "val" and value is None:
        return "?" if lookup(body, path[:-1] + ("state",)) == "unknown" else "-"
    return _plain(value, unchecked)


def check_plan(ns, body):
    page = ns["_aer_decode_response"](copy.deepcopy(body), "1a")
    plan = ns["_aer_plan"](page)
    assert plan == ns["_aer_plan"](page)                               # pure
    seen = [f for item in plan for f in item.fields]
    assert len(seen) == len(set(seen)), [f for f in seen if seen.count(f) > 1][:5]
    want = api_fields(body)
    assert set(seen) == set(want) and len(seen) == len(want), (
        sorted(map(str, set(want) - set(seen)))[:5], sorted(map(str, set(seen) - set(want)))[:5])
    kinds = ns["AER_ITEM_KINDS_1A"]
    for item in plan:
        assert item.kind in kinds and len(item.fields) == len(item.parts), item
        assert not any(ord(ch) in ae.AER_ESC for ch in item.text), item.text
        pos = 0
        for f, part in zip(item.fields, item.parts):
            assert part == expect(body, f), (f, part, expect(body, f))
            at = item.text.find(part, pos)
            assert at >= 0, (f, part, item.text)
            pos = at + len(part)
        if item.kind in ("cell", "summary"):
            ki = lookup(body, item.fields[0])
            key = next(r for r in body["catalog"] if r["ki"] == ki)["key"].split("|")
            assert item.text.split(" ")[0] == ae.PROV_LETTER[key[1]], item.text
    assert not {"class", "mark", "swatch"} & {i.kind for i in plan}
    assert [i.text for i in plan if i.kind == "legend"] == LEGEND_1A
    return page, plan


# ── P12 ───────────────────────────────────────────────────────────────────

def test_p12_the_plan_is_a_bijection_over_every_served_field():
    ns = bot_ns()
    assert ns["AER_PROV_LETTER"] == ae.PROV_LETTER
    assert ns["AER_RENDER_TIMEOUT_S"] == 15 and ns["AER_FALLBACK_MSG_MAX"] == 1900
    counts = []
    for name, body in (("game", game_body()), ("spread", spread_body()),
                       ("control", control_body())):
        _page, plan = check_plan(ns, body)
        counts.append((name, len(plan), sum(len(i.fields) for i in plan)))
    print("GATE p12 bijection: (fixture, items, fields) %s; every field once, in order, as its "
          "value reads; 1a kinds only; no escaped-set code point drawn; 8 legend lines" % counts)


def test_p12_flag_obs_reads_the_same_at_every_stage():
    ns = bot_ns()
    body = spread_body()
    page = ns["_aer_decode_response"](copy.deepcopy(body), "1a")
    assert body["windows"][0]["flag_obs"] == 7 and page.windows[0]["flag_obs"] == 7
    plan = ns["_aer_plan"](page)
    win = [i for i in plan if ("windows", 0, "flag_obs") in i.fields]
    assert len(win) == 1 and win[0].parts[win[0].fields.index(("windows", 0, "flag_obs"))] == "7"
    content, files = ns["_aer_fallback"]("Evidence report: pair 1001 1002, page 1 of 3", plan,
                                         "1001-1002", 1)
    assert files == [] and "flag_obs=7" in content and content.count("flag_obs=") == 1
    print("GATE p12 flag_obs stages: response 7, BotPage 7, plan 7, fallback 7")


# ── P23 ───────────────────────────────────────────────────────────────────

FAKE_WORKER = '''
import base64, json, os, sys, time
marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hung-once")
inp, out = sys.stdin.buffer, sys.stdout.buffer
while True:
    head = inp.read(4)
    if len(head) < 4:
        break
    plan = json.loads(inp.read(int.from_bytes(head, "big")).decode("utf-8"))
    if not os.path.exists(marker):
        open(marker, "w").close()
        time.sleep(600)
    png = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)) + b"fake"
    reply = {"png": base64.b64encode(png).decode("ascii"),
             "drawn": [[i, t, [0, 0, 1, 1]] for i, (k, t) in enumerate(plan)]}
    data = json.dumps(reply).encode("utf-8")
    out.write(len(data).to_bytes(4, "big") + data)
    out.flush()
'''


def test_p23_a_hung_worker_gives_the_fallback_in_time_then_a_png(tmp_path):
    script = tmp_path / "fake_worker.py"
    script.write_text(FAKE_WORKER, encoding="utf-8")
    events = []
    ns = bot_ns(_Api(lambda path, actor: (200, game_body(), {}), events), events, mpl=True)
    ns["AER_WORKER_PATH"] = str(script)
    ns["AER_RENDER_TIMEOUT_S"] = 4
    spawned = []
    real_spawn = ns["_aer_worker_spawn"]

    async def spawn():
        proc = await real_spawn()
        spawned.append(proc)
        return proc

    ns["_aer_worker_spawn"] = spawn
    lock = ns["_mpl_render_lock"]

    def compare_chart():
        """What /compare does around its matplotlib calls."""
        if not lock.acquire(timeout=2):
            return False
        lock.release()
        return True

    async def go():
        try:
            first = _Interaction(events, ADMIN)
            t0 = time.monotonic()
            task = asyncio.ensure_future(ns["_aer_command"](first, dict(REQ)))
            await asyncio.sleep(1.0)
            chart = await asyncio.to_thread(compare_chart)
            await task
            took = time.monotonic() - t0
            first_ended = spawned[0].returncode is not None
            second = _Interaction(events, ADMIN)
            await ns["_aer_command"](second, dict(REQ))
            return first, second, took, chart, first_ended
        finally:
            for proc in spawned:
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()

    first, second, took, chart, first_ended = run(asyncio.wait_for(go(), 40))
    content, kw = first.channel.sent[0]
    assert kw["files"] == [] and "```" in content and first.ephemeral == ["Posted."]
    assert took < 4 + 3, took
    assert first_ended and len(spawned) == 2
    content2, kw2 = second.channel.sent[0]
    assert [f.filename for f in kw2["files"]] == ["evidence-000000000000-p1.png"]
    assert kw2["files"][0].data.startswith(PNG) and "```" not in content2
    assert chart is True
    print("GATE p23: hung worker -> fallback after %.1f s (bound 4 s), worker ended; the next "
          "report rendered a PNG from a replacement; a /compare lock take meanwhile: %s"
          % (took, chart))


def test_without_matplotlib_the_page_falls_back_without_a_worker():
    events = []
    ns = bot_ns(_Api(lambda path, actor: (200, game_body(), {}), events), events, mpl=False)

    async def never():
        raise AssertionError("a worker was started without matplotlib")

    ns["_aer_worker_spawn"] = never
    it = _Interaction(events, ADMIN)
    run(ns["_aer_command"](it, dict(REQ)))
    content, kw = it.channel.sent[0]
    assert kw["files"] == [] and content.startswith("Evidence report: game 000000000000")
    assert "UNCOLORED (absent)" in content


# ── the worker's protocol (no matplotlib needed) ──────────────────────────

def _frame(obj):
    data = json.dumps(obj).encode("utf-8")
    return len(data).to_bytes(4, "big") + data


def _replies(raw):
    out, pos = [], 0
    while pos < len(raw):
        n = int.from_bytes(raw[pos:pos + 4], "big")
        out.append(json.loads(raw[pos + 4:pos + 4 + n].decode("utf-8")))
        pos += 4 + n
    return out


def test_the_worker_answers_one_framed_reply_per_plan():
    def draw(plan):
        if plan and plan[0][0] == "class":
            raise ValueError("refused")
        return PNG + b"x", [(i, t, (0, 0, 1, 1)) for i, (_k, t) in enumerate(plan)]

    out = io.BytesIO()
    inp = io.BytesIO(_frame([["title", "EVIDENCE game"], ["cell", "S a"]])
                     + _frame([["class", "c1"]]))
    worker.serve(inp, out, draw)
    first, second = _replies(out.getvalue())
    import base64
    assert base64.b64decode(first["png"]).startswith(PNG)
    assert [d[1] for d in first["drawn"]] == ["EVIDENCE game", "S a"]
    assert second == {"error": "ValueError"}
    assert set(worker.FONT_SIZES) == set(bot_ns()["AER_ITEM_KINDS_1A"])
    assert worker.FILLED_KINDS == {"cell", "summary"}


# ── P12 drawn text and P14, with matplotlib ───────────────────────────────

def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in rgb[:3])


def test_p12_p14_the_png_draws_the_plan_on_fixed_chrome():
    pytest.importorskip("matplotlib")
    import matplotlib.image as mpimg
    ns = bot_ns()
    for body in (game_body(), spread_body(), control_body()):
        page = ns["_aer_decode_response"](copy.deepcopy(body), "1a")
        plan = ns["_aer_plan"](page)
        png, drawn = worker.render([(i.kind, i.text) for i in plan])
        assert png.startswith(PNG)
        assert [t for _i, t, _b in drawn] == [i.text for i in plan]
        img = mpimg.imread(io.BytesIO(png))
        height = img.shape[0]
        for (i, _t, (x0, y0, x1, y1)), item in zip(drawn, plan):
            px = img[int(height - (y0 + y1) / 2), max(int(x0) - 1, 0)]
            want = worker.CELL_FILL if item.kind in ("cell", "summary") else worker.BACKGROUND
            assert _hex(px) == want, (item.kind, _hex(px))
        status = next(i for i in plan if i.kind == "status")
        assert status.text.startswith("STATUS UNCOLORED (absent)")
