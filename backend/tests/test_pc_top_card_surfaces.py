"""Item 9a observation 4 — the Top Card on the bot's text surfaces.

/card already named it. The binder's "Best prints" line and the pc-events
mint relay line did not, although the print carries the column. These tests
RUN both line builders (the `_load` exec harness of test_pc_bot_faces, not a
source-text pin: this file's subject is what the functions render), and they
pin BOTH sides of the relay's payload contract -- a bot reading a field the
api never sends would print nothing forever and every "it works" check built
only on the bot half would stay green (#341).
"""
import re
from pathlib import Path
from types import SimpleNamespace

BOT_SRC = (Path(__file__).resolve().parents[1] / "discord_bot.py").read_text(encoding="utf-8")
MAIN_SRC = (Path(__file__).resolve().parents[1] / "api" / "main.py").read_text(encoding="utf-8")

# A deterministic stand-in for the rarity emoji map, so the expected strings
# below are exact rather than "contains".
EMOJI = {"legendary": "L", "epic": "E", "rare": "R"}


def _fn(src, name):
    m = re.search(rf"^(?:async )?def {re.escape(name)}\(.*?(?=^(?:async def |def |@|# ──)|\Z)", src, re.S | re.M)
    assert m, name
    return m.group(0)


def _load(*names):
    """Run these bot functions in a namespace of stubs and return it."""
    ns = {
        "discord": SimpleNamespace(utils=SimpleNamespace(escape_markdown=lambda s: s)),
        "_PC_RARITY_EMOJI": EMOJI,
    }
    for n in names:
        exec(compile(_fn(BOT_SRC, n), "<discord_bot>", "exec"), ns)
    return ns


def _binder(**over):
    p = {"rarity": "epic", "subject_name": "Spirit", "pool_rank": 8, "rating": 1839}
    p.update(over)
    return p


def _event(**over):
    pr = {"print_id": "p1", "rarity": "epic", "pool_rank": 3}
    pr.update(over.pop("print", {}))
    e = {"id": 1, "kind": "epic", "puller_name": "Sid", "subject_name": "Spirit",
         "dup_at_pull": 0, "print": pr}
    e.update(over)
    return e


# ── controls: the name appears ──

def test_the_binder_best_prints_line_names_the_top_card():
    ns = _load("_pc_name", "_pc_print_line")
    line = ns["_pc_print_line"](_binder(top_card="Poison"))
    assert "Poison" in line
    assert line == "E **Spirit** #8 · 1839 · 🃏 Poison"


def test_the_mint_relay_line_names_the_top_card():
    ns = _load("_pc_name", "_pc_event_lines")
    lines = ns["_pc_event_lines"]([_event(print={"top_card": "Poison"})])
    assert "Poison" in lines[0]
    assert lines[0] == "**Sid** pulled a E Epic **Spirit** (#3 in the pool)!  ·  NEW to the binder  ·  🃏 Poison"


def test_the_relay_names_the_top_card_on_an_own_card_pull_too():
    # the "self" branch is a separate f-string and can drift on its own
    ns = _load("_pc_name", "_pc_event_lines")
    lines = ns["_pc_event_lines"]([_event(kind="self", print={"top_card": "Wind Up"})])
    assert lines[0].startswith("🪞 ")
    assert lines[0].endswith("  ·  🃏 Wind Up")


def test_the_top_card_is_escaped_like_every_other_api_name():
    # _pc_name is the escape seam; a top card reaching the line raw would be
    # the one unescaped api string on the surface
    ns = _load("_pc_name", "_pc_print_line")
    marks = []
    ns["discord"] = SimpleNamespace(utils=SimpleNamespace(
        escape_markdown=lambda s: marks.append(s) or s))
    ns["_pc_print_line"](_binder(top_card="Poison"))
    assert "Poison" in marks


# ── negative controls: no top card renders the PRE-CHANGE line exactly ──

PRE_CHANGE_BINDER = "E **Spirit** #8 · 1839"
PRE_CHANGE_RELAY = "**Sid** pulled a E Epic **Spirit** (#3 in the pool)!  ·  NEW to the binder"


def test_a_print_with_no_top_card_renders_the_line_it_rendered_before():
    ns = _load("_pc_name", "_pc_print_line")
    f = ns["_pc_print_line"]
    # absent key, explicit null, and empty string are the three shapes the
    # payload can take; all three must add no separator and no dash
    assert f(_binder()) == PRE_CHANGE_BINDER
    assert f(_binder(top_card=None)) == PRE_CHANGE_BINDER
    assert f(_binder(top_card="")) == PRE_CHANGE_BINDER
    # and the segment's own marker is absent, not merely empty-valued
    assert "🃏" not in f(_binder())


def test_a_relay_event_with_no_top_card_renders_the_line_it_rendered_before():
    ns = _load("_pc_name", "_pc_event_lines")
    f = ns["_pc_event_lines"]
    assert f([_event()])[0] == PRE_CHANGE_RELAY
    assert f([_event(print={"top_card": None})])[0] == PRE_CHANGE_RELAY
    assert f([_event(print={"top_card": ""})])[0] == PRE_CHANGE_RELAY


# ── the payload contract, both sides ──

def test_the_events_payload_carries_the_top_card_the_relay_reads():
    # the bot reads it off the nested print dict...
    assert 'top = p.get("top_card")' in _fn(BOT_SRC, "_pc_event_lines")
    # ...the endpoint sends it on that same dict...
    events = MAIN_SRC[MAIN_SRC.index('@app.get("/api/v1/internal/pc/events/pending"'):]
    events = events[:events.index("\n\n\n")]
    assert '"top_card": r["top_card"]' in events
    # ...and the query it is read from actually selects the column, or the
    # field above raises KeyError on every poll
    sql = " ".join(MAIN_SRC[MAIN_SRC.index("_PC_EVENTS_PENDING_SQL = "):].split("\n\n\n")[0].split())
    assert "pr.rating, pr.title, pr.top_card," in sql


def test_the_collection_payload_already_carries_the_top_card():
    # _pc_print_dict feeds /collection's "best"; no api change was needed there
    dict_src = MAIN_SRC[MAIN_SRC.index("def _pc_print_dict("):]
    dict_src = dict_src[:dict_src.index("\n\n\n")]
    assert '"top_card": row["top_card"]' in dict_src
    assert 'top = p.get("top_card")' in _fn(BOT_SRC, "_pc_print_line")


# ── the field the Top card segment made long enough to matter ──
#
# Every "Best prints" line grew by " · 🃏 <name>". Ten of them with long
# subject names and long top cards now pass 1024, which the pre-change binder
# could not reach -- so how the block is bounded became load-bearing.

LONG_NAME = ("Pristine Perseverance " * 4)[:74]   # geometry: see the precondition


def _long_lines(ns):
    f = ns["_pc_print_line"]
    return [f(_binder(subject_name=LONG_NAME, pool_rank=i, top_card="Abyssal Countdown"))
            for i in range(10)]


def test_the_long_binder_actually_reaches_the_cap_and_breaks_under_a_slice():
    """The precondition for the two tests below.

    Without it they would pass on data that never reaches 1024, i.e. on a
    check that cannot fail (#342). Both halves are asserted: the block is
    over the cap, AND a raw slice of it cuts inside a bold run.
    """
    ns = _load("_pc_name", "_pc_print_line")
    naive = "\n".join(_long_lines(ns))
    assert len(naive) > 1024, len(naive)
    assert naive[:1024].count("**") % 2 == 1, "the slice no longer lands inside a ** run"


def test_a_long_best_prints_field_is_cut_between_lines_not_inside_one():
    ns = _load("_pc_name", "_pc_print_line", "_pc_fit_field")
    lines = _long_lines(ns)
    value = ns["_pc_fit_field"](lines)
    assert len(value) <= 1024, len(value)
    # every bold run that opened also closed -- the defect the slice has
    assert value.count("**") % 2 == 0
    # and the value is whole lines only, plus the marker
    got = value.split("\n")
    assert got[-1] == "…"
    assert got[:-1] == lines[:len(got) - 1]


def test_the_best_prints_field_is_built_line_by_line_not_sliced():
    body = BOT_SRC[BOT_SRC.index("async def cmd_pc_collection"):]
    body = body[:body.index("\n@bot.")]
    assert "_pc_fit_field(" in body
    assert "[:1024]" not in body


# ── negative control: a binder that fits renders exactly what it always did ──

def test_a_short_binder_renders_exactly_the_lines_it_always_did():
    ns = _load("_pc_name", "_pc_print_line", "_pc_fit_field")
    lines = [ns["_pc_print_line"](_binder(pool_rank=i, top_card="Poison")) for i in range(10)]
    assert len("\n".join(lines)) <= 1024
    value = ns["_pc_fit_field"](lines)
    assert value == "\n".join(lines)
    assert "…" not in value
