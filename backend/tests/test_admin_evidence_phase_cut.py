"""Admin evidence report, phase 1a item 10: the phase-cut proof (design 6.5 AE6,
8 phase 1a, 4.5 1a schema, 4.4 1a audit).

Phase 1a carries no class or mark path anywhere a report can reach: the
schema, the plan, the PNG worker, the text fallback, the audit row, or an
appearance parameter. A static reading of the three report modules
(backend/api/admin_evidence.py, the `_aer_*` code of backend/discord_bot.py,
backend/aer_render_worker.py), plus the bot's 1a decoder run on a response
that carries a class slot:

  4.5  `AER_WIRE["1a"]` (api and bot) holds no `cls` or `mark` slot; the
       response carries no `legend` key and its `rules` is exactly
       `{"report": "absent"}`.
  4.4  the audit's `details.rules` is the response's `rules` copied, and no
       1a builder names `loader`, `eval`, `marks` or `legend` as a key, slot or
       keyword.
  P14  a response with a class slot (`cls:c3` as a tenth seat slot) and one
       with 1b rules are `unavailable (schema)` to the 1a decoder; the plan has
       only the 1a item kinds (no class, mark or swatch kind), the worker draws
       exactly those kinds, and no report module holds an ESC byte or an ANSI
       sequence (no colour by class in the fallback).

The vocabulary signature equal on base and tip (`review_eval()`) is read after
REFIT-E1, when the review tooling is on main; it is not part of this file.
"""

import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from test_discord_evidence_bot import ae, bot_ns, game_body, summary_body  # noqa: E402
import aer_render_worker as worker  # noqa: E402

BACKEND = os.path.dirname(HERE)
API = os.path.join(BACKEND, "api", "admin_evidence.py")
BOT = os.path.join(BACKEND, "discord_bot.py")
WORKER = os.path.join(BACKEND, "aer_render_worker.py")
# The 1b wire words. `legend` is a 1b WIRE key (the response's class legend)
# and also the 1a plan kind of the fixed AER_LEGEND_1A chrome lines, so it is
# checked as a wire key where the wire is built and read: the api module and
# the bot's report code; the worker draws plan kinds only.
PHASE_1B_WORDS = frozenset({"loader", "eval", "marks", "report_legend", "cls", "mark"})
WIRE_ONLY_WORDS = frozenset({"legend"})
CLASS_KINDS = frozenset({"class", "mark", "swatch", "legend_swatch", "cls"})
ESC = chr(0x1B)


def _tree(path):
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _bot_report_nodes():
    """The bot's report code: every `_aer_*` function and every AER constant."""
    out = []
    for node in _tree(BOT).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                node.name.startswith("_aer_"):
            out.append(node)
        elif isinstance(node, ast.Assign):
            names = [n.id for t in node.targets for n in ast.walk(t) if isinstance(n, ast.Name)]
            if any(n.startswith(("AER_", "_AER_", "AerItem", "BotPage")) for n in names):
                out.append(node)
    return out


def _bot_const(name):
    for node in _tree(BOT).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            v = node.value
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and \
                    v.func.id == "frozenset" and len(v.args) == 1 and not v.keywords:
                return frozenset(ast.literal_eval(v.args[0]))
            return ast.literal_eval(v)
    raise AssertionError("no module constant %s in discord_bot.py" % name)


def _keys_and_keywords(nodes):
    """Every constant dict key, constant subscript key and keyword name."""
    out = []
    for top in nodes:
        for n in ast.walk(top):
            if isinstance(n, ast.Dict):
                out += [(k.value, k.lineno) for k in n.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            elif isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and \
                    isinstance(n.slice.value, str):
                out.append((n.slice.value, n.lineno))
            elif isinstance(n, ast.Call):
                out += [(k.arg, n.lineno) for k in n.keywords if k.arg]
    return out


def test_1a_wire_tables_hold_no_class_or_mark_slot():
    bot_wire = _bot_const("AER_WIRE")
    assert set(ae.AER_WIRE) == {"1a"} and set(bot_wire) == {"1a"}
    for table, slots in ae.AER_WIRE["1a"].items():
        assert not set(slots) & {"cls", "mark"}, table
        assert tuple(bot_wire["1a"][table]) == tuple(slots), table


def test_1a_builders_name_no_phase_1b_key_slot_or_keyword():
    """No 1a builder in the api or the bot writes or reads a 1b field."""
    wire = PHASE_1B_WORDS | WIRE_ONLY_WORDS
    found = [("api", k, line) for k, line in _keys_and_keywords([_tree(API)]) if k in wire]
    found += [("bot", k, line) for k, line in _keys_and_keywords(_bot_report_nodes())
              if k in wire]
    found += [("worker", k, line) for k, line in _keys_and_keywords([_tree(WORKER)])
              if k in PHASE_1B_WORDS]
    assert found == [], found


def test_1a_rules_are_exactly_report_absent_and_the_audit_copies_them():
    """Every `rules` value the api builds is the literal {"report": "absent"},
    and the audit's details.rules is a plain copy of the response's."""
    literal, copied = [], []
    for n in ast.walk(_tree(API)):
        if not isinstance(n, ast.Dict):
            continue
        for k, v in zip(n.keys, n.values):
            if not (isinstance(k, ast.Constant) and k.value == "rules"):
                continue
            if isinstance(v, ast.Dict):
                assert ast.literal_eval(v) == {"report": "absent"}, ast.unparse(v)
                literal.append(n.lineno)
            else:
                # dict(body["rules"]) and nothing beside it
                assert isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and \
                    v.func.id == "dict" and len(v.args) == 1 and not v.keywords and \
                    ast.unparse(v.args[0]) == "body['rules']", ast.unparse(v)
                copied.append(n.lineno)
    assert len(literal) == 1 and len(copied) == 1, (literal, copied)
    assert "legend" not in _bot_const("_AER_TOP_KEYS")


def test_p14_the_1a_decoder_refuses_a_class_slot_and_1b_rules():
    ns = bot_ns()
    word = "Evidence report: unavailable (schema)."
    good = game_body()
    page, w = ns["_aer_outcome"](200, good)
    assert page is not None and w is None
    with_class = game_body()
    with_class["games"][0]["seats"][0]["cells"][0].append("c3")      # cls:c3
    assert ns["_aer_outcome"](200, with_class) == (None, word)
    armed = game_body()
    armed["rules"] = {"report": "armed", "loader": "r" * 12, "eval": "e" * 12}
    assert ns["_aer_outcome"](200, armed) == (None, word)
    legend = game_body()
    legend["legend"] = {"c1": "x"}
    assert ns["_aer_outcome"](200, legend) == (None, word)


def test_p14_the_1a_decoder_refuses_metadata_map_extras():
    ns = bot_ns()
    word = "Evidence report: unavailable (schema)."
    assert ns["_aer_outcome"](200, game_body())[1] is None
    assert ns["_aer_outcome"](200, summary_body())[1] is None
    for part, key in (("population", "cls"), ("baseline", "mark"),
                      ("registry", "legend")):
        body = game_body()
        body[part][key] = "extra"
        assert ns["_aer_outcome"](200, body) == (None, word), (part, key)


def test_p14_the_plan_and_the_worker_have_only_the_1a_item_kinds():
    kinds = tuple(_bot_const("AER_ITEM_KINDS_1A"))
    assert not set(kinds) & CLASS_KINDS
    used = set()
    for top in _bot_report_nodes():
        for n in ast.walk(top):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and \
                    n.func.id in ("AerItem", "_aer_item") and n.args:
                first = n.args[0]
                for c in ast.walk(first):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                        used.add(c.value)
    assert used and used <= set(kinds), sorted(used - set(kinds))
    assert set(worker.FONT_SIZES) == set(kinds)
    assert not set(worker.FILLED_KINDS) - {"cell", "summary"}


def test_p14_no_report_module_holds_an_escape_byte_or_an_ansi_sequence():
    """The 1a fallback is plain text: no ESC byte, no ANSI table, anywhere the
    report's code builds a string."""
    hits = []
    for label, nodes in (("api", [_tree(API)]), ("bot", _bot_report_nodes()),
                         ("worker", [_tree(WORKER)])):
        for top in nodes:
            for n in ast.walk(top):
                if isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes)):
                    text = n.value if isinstance(n.value, str) else n.value.decode("latin-1")
                    if ESC in text or "[3" + "1m" in text or "[0m" in text:
                        hits.append((label, n.lineno))
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and \
                        n.func.id == "chr" and n.args and isinstance(n.args[0], ast.Constant) \
                        and n.args[0].value == 0x1B:
                    hits.append((label, n.lineno))
    assert hits == [], hits
