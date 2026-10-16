"""Admin evidence report, item 1a-8: the text fallback (design 5.3, phase 1a).
No database, no matplotlib.

  P13 (5.3) a maximum page (5 games, every seat family, maximum-width values)
      under a forced render failure, and the control fixture, each give ONE
      public message whose text parses back, escapes decoded, to the stored
      values: every plan line present and in order, nothing truncated, every
      number exact, every text field equal to the value before the api
      encoded it; no escaped-set code point (U+061C, U+200E and U+200F
      included) reaches the message raw.
  P14 a forced fallback carries `UNCOLORED (absent)` and no class column, mark
      column or ANSI code.
  P24 a page replaced by a button press edits the one message and replaces
      its attachments: an inline page after an attachment page leaves no
      attachment behind, and an attachment page after an inline page carries
      exactly its own file.
"""

import asyncio
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_discord_evidence_bot import (ADMIN, _Api, _Interaction, _Message, ae,  # noqa: E402
                                       bot_ns, game_body)
from test_discord_evidence_render import control_body  # noqa: E402

BS = chr(0x5C)
FENCE = "`" * 3
UNCHECKED = ("population", "baseline", "registry", "windows")
CODE = "0" * 12


def run(coro):
    return asyncio.run(coro)


def unescape(text):
    """The inverse of the api's `_aer_enc`."""
    out, i = [], 0
    while i < len(text):
        if text[i] == BS and text[i + 1] == BS:
            out.append(BS)
            i += 2
        elif text[i] == BS and text[i + 1:i + 3] == "u{":
            j = text.index("}", i)
            out.append(chr(int(text[i + 3:j], 16)))
            i = j + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def max_body():
    """Five games, both seats carrying every seat-scope base key, values at
    full repr width, long encoded names and reasons."""
    body = game_body(page=1, pages=1, shape="series")
    base = [e for e in ae.REPORT_REGISTRY if not e.is_window and e.scope == "seat"]
    body["catalog"] = [ae._catalog_row(e, {"pop_p50": -1.2345678901234567e+300,
                                           "pop_p90": 2.2250738585072014e-308,
                                           "pop_p99": 1.7976931348623157e+308}) for e in base]
    body["subjects"] = [{"steam_id": "9" * 16, "name": ae._aer_enc("W" * 32 + chr(0x200E))},
                        {"steam_id": "8" * 16, "name": ae._aer_enc("$" * 32 + chr(0x061C))}]
    cells = [[e.ki, -1.2345678901234567e+300, 1.7976931348623157e+308, 2 ** 31 - 1,
              "partial", 0.12345678901234568, 0.9876543210987654, 2 ** 31 - 1, "ok"]
             for e in base]
    games = []
    for n in range(5):
        g = copy.deepcopy(body["games"][0])
        g["code"] = ("%x" % (n + 10)) * 12
        g["match_id"] = g["code"] + "0" * 20
        g["series_id"] = "a" * 32
        g["invalidated"] = ae._aer_enc("reason " + chr(0x200F) + BS + "$1")
        g["seats"][0]["cells"] = cells
        g["seats"][1]["cells"] = cells
        games.append(g)
    body["games"] = games
    return body


def served_message(body, render_fails=True):
    """One `/evidence` command served `body` with matplotlib present and the
    render worker failing: the one public message and its files."""
    events = []
    ns = bot_ns(_Api(lambda path, actor: (200, copy.deepcopy(body), {}), events), events,
                mpl=True)

    async def broken_spawn():
        raise OSError("forced render failure")

    if render_fails:
        ns["_aer_worker_spawn"] = broken_spawn
    it = _Interaction(events, ADMIN)
    req = {"shape": body["shape"], "code": CODE, "page": 1}
    run(ns["_aer_command"](it, req))
    assert it.ephemeral == ["Posted."] and len(it.channel.sent) == 1
    content, kw = it.channel.sent[0]
    return ns, content, kw["files"]


def message_lines(content, files):
    if files:
        assert len(files) == 1 and FENCE not in content and "\n" not in content
        assert files[0].filename.endswith(".txt")
        return files[0].data.decode("utf-8").split("\n")
    head, rest = content.split("\n", 1)
    assert rest.startswith(FENCE + "\n") and rest.endswith("\n" + FENCE)
    return rest[len(FENCE) + 1:-len(FENCE) - 1].split("\n")


def parse_back(ns, body, lines):
    """Every plan line in order, then every field read back from its line."""
    page = ns["_aer_decode_response"](copy.deepcopy(body), "1a")
    plan = ns["_aer_plan"](page)
    assert lines == [item.text for item in plan]
    from test_discord_evidence_render import lookup
    checked = 0
    for line, item in zip(lines, plan):
        assert not any(ord(ch) in ae.AER_ESC for ch in line), line
        pos = 0
        for field, part in zip(item.fields, item.parts):
            at = line.find(part, pos)
            assert at >= 0, (field, part)
            pos = at + len(part)
            value = lookup(body, field)
            if (isinstance(value, bool) or value is None
                    or field[-1] in ("ki", "subject", "oi", "page", "pages", "shape")
                    or field == ("rules", "report")):
                continue                    # an index or a word, not a stored value
            if isinstance(value, (int, float)):
                assert float(part) == value, (field, part, value)
                checked += 1
            elif isinstance(value, str):
                if field[-1] == "invalidated":
                    part = part[len("INVALIDATED "):]
                # api-encoded slots decode to the stored text; the unchecked
                # parts (population, baseline, registry, windows) were sent raw
                stored = value if field[0] in UNCHECKED else unescape(value)
                assert unescape(part) == stored, (field, part, stored)
                checked += 1
    return plan, checked


def test_p13_a_maximum_page_under_a_forced_render_failure_parses_back():
    body = max_body()
    ns, content, files = served_message(body)
    assert content == "Evidence report: series %s, page 1 of 1" % CODE
    assert [f.filename for f in files] == ["evidence-%s-p1.txt" % CODE]
    lines = message_lines(content, files)
    plan, checked = parse_back(ns, body, lines)
    total = len("\n".join(lines))
    assert total > ns["AER_FALLBACK_MSG_MAX"]
    print("GATE p13 maximum page: one message, header plus one attachment of %d characters, "
          "%d plan lines, %d stored values parsed back exactly" % (total, len(plan), checked))


def test_p13_p14_the_control_fixture_parses_back_inline():
    body = control_body()
    ns, content, files = served_message(body)
    assert files == []
    lines = message_lines(content, files)
    plan, checked = parse_back(ns, body, lines)
    joined = "\n".join(lines)
    assert "UNCOLORED (absent)" in joined
    assert chr(0x1B) not in content and "class" not in {i.kind for i in plan}
    assert not [i for i in plan if i.kind in ("class", "mark", "swatch")]
    name = next(p for i in plan for f, p in zip(i.fields, i.parts) if f == ("subjects", 1, "name"))
    assert unescape(name) == "$x^2$ " + chr(0x200F) + BS
    pop = next(p for i in plan for f, p in zip(i.fields, i.parts) if f == ("population", "key"))
    assert unescape(pop) == "all" + chr(0x61C) + chr(0x200E) + chr(0x200F) + "`" + BS
    for cp in (0x061C, 0x200E, 0x200F):
        assert chr(cp) not in content
    print("GATE p13 control: inline, %d lines, %d stored values parsed back; U+061C, U+200E, "
          "U+200F and the backtick escaped; UNCOLORED (absent); no class, mark or ANSI"
          % (len(lines), checked))


def test_p24_a_replaced_fallback_page_replaces_its_attachments():
    small, big = game_body(page=1, pages=2, shape="series"), max_body()
    big["page"], big["pages"] = 2, 2

    def answer(path, actor):
        return 200, copy.deepcopy(big if "page=2" in path else small), {}

    out = []
    for first, second in ((2, 1), (1, 2)):
        events = []
        ns = bot_ns(_Api(answer, events), events, mpl=False)
        msg = _Message(events)
        for page in (first, second):
            it = _Interaction(events, ADMIN, custom_id="aer:s:%s:%d" % (CODE, page), message=msg)
            run(ns["on_interaction"](it))
            assert it.ephemeral == ["Posted."]
        out.append(msg.edits)
    inline_after_file, file_after_inline = out
    assert [f.filename for f in inline_after_file[0]["attachments"]] == ["evidence-%s-p2.txt" % CODE]
    assert inline_after_file[1]["attachments"] == [] and FENCE in inline_after_file[1]["content"]
    assert file_after_inline[0]["attachments"] == []
    assert [f.filename for f in file_after_inline[1]["attachments"]] == ["evidence-%s-p2.txt" % CODE]
    assert FENCE not in file_after_inline[1]["content"]
    print("GATE p24 fallback replacement: attachment then inline leaves no attachment; inline "
          "then attachment carries exactly its own file; one message edited each time")
