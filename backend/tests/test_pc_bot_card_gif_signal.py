"""Dance cards, round two (the integrator's addendum to the round-2 brief): the
rebuilt bot's positive signal for the release train's bot arm.

The train's witness ([BOT-BOOT] and [BOT-READY], matched by generation)
proves that a new bot process started, not which build it runs, so a bot
rebuild is otherwise silent. on_ready therefore prints ONE more whole line
just before its ready line, carrying the same generation:

    [BOT-FEATURE] card_motion_gif=<n> -- gen=<gen>

<n> is derived from /card's compiled callback (discord_bot._pc_card_gif_word):
1 when its code loads every name of _PC_CARD_GIF_NAMES (the GIF branch's
margin, its request timeout and the upload cap), 0 on a build whose /card lost
that branch, and the exception's type name when the derivation fails. The
bot's own code is lifted from discord_bot.py (discord_collection_harness.lift)
and run against a stub generation. Each test is one named assertion; the
mutation that must fail it is planted by the lane's mutation runner and
recorded in its log, and the test's own passing case is the control (#391).
"""
import ast
import os
import re
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import discord_collection_harness as H  # noqa: E402

BOT = os.path.join(HERE, "..", "discord_bot.py")
FUNCS = {"cmd_pc_card", "_pc_card_gif_word", "_pc_card_gif_signal"}
ASSIGNS = {"_PC_CARD_GIF_NAMES"}
GEN = "0123456789ab"
# The whole line, as the train matches a marker after the compose prefix.
LINE = re.compile(r"\A\[BOT-FEATURE\] card_motion_gif=(\S+) -- gen=(\w+)\Z")


def _lifted():
    ns = {"_BOT_GEN": GEN, "discord": SimpleNamespace(Member=object)}
    exec(compile(H.lift(FUNCS, ASSIGNS), BOT, "exec"), ns)
    return ns


def _calls(node, name):
    return [c for c in ast.walk(node)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == name]


# Synthetic callbacks for the derivation, compiled and never called: the names
# below are loaded as globals by their code, which is all the word reads.
async def _plain(ctx):
    return await ctx.fetch("face")


async def _nested(ctx):
    async def inner():
        return _PC_MOTION_GIF_MARGIN_S, _PC_MOTION_GIF_TIMEOUT_S, _pc_upload_cap(ctx)  # noqa: F821
    return await inner()


async def _partial(ctx):
    return _PC_MOTION_GIF_MARGIN_S, _pc_upload_cap(ctx)  # noqa: F821


async def _documented(ctx):
    """Names _PC_MOTION_GIF_MARGIN_S, _PC_MOTION_GIF_TIMEOUT_S and _pc_upload_cap in prose only."""
    return await ctx.fetch("face")


def test_the_signal_reads_one_on_this_build():
    """The real /card callback carries the GIF branch, so the line reads
    card_motion_gif=1 and carries this process's generation."""
    ns = _lifted()
    assert ns["_pc_card_gif_word"](ns["cmd_pc_card"]) == 1
    line = ns["_pc_card_gif_signal"]()
    m = LINE.match(line)
    assert m, line
    assert (m.group(1), m.group(2)) == ("1", GEN), line


def test_the_word_is_derived_from_the_callbacks_code():
    """Read from the compiled code, never written down: a callback loading
    none of the names reads 0, one whose nested code loads all of them 1, one
    loading only some 0, one whose docstring alone names them 0, and a command
    object is read through its callback, as discord.py's hybrid command is."""
    word = _lifted()["_pc_card_gif_word"]
    assert word(_plain) == 0
    assert word(_nested) == 1
    assert word(_partial) == 0
    assert word(_documented) == 0
    assert word(SimpleNamespace(callback=_nested)) == 1
    assert word(SimpleNamespace(callback=_plain)) == 0


def test_a_failing_derivation_never_stops_the_line():
    """A derivation that raises still yields one whole line, which names the
    exception instead of 1 -- so it cannot pass for the new build -- and
    returns rather than raising, so on_ready still reaches its ready line."""
    ns = _lifted()
    ns["cmd_pc_card"] = SimpleNamespace(callback=None)
    line = ns["_pc_card_gif_signal"]()
    m = LINE.match(line)
    assert m, line
    assert (m.group(1), m.group(2)) == ("error:AttributeError", GEN), line


def test_on_ready_prints_the_signal_just_before_the_ready_line():
    """on_ready's own statement list prints the signal (flushed) immediately
    before its last statement, the ready line: never under a condition, never
    after the ready line, and nowhere else in the bot."""
    tree = ast.parse(H.bot_source())
    ready = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_ready"]
    assert len(ready) == 1
    body = ready[0].body
    last = body[-1]
    assert isinstance(last, ast.Expr) and "[BOT-READY]" in ast.unparse(last), ast.unparse(last)
    before = body[-2]
    assert isinstance(before, ast.Expr) and isinstance(before.value, ast.Call), ast.unparse(before)
    call = before.value
    assert isinstance(call.func, ast.Name) and call.func.id == "print", ast.unparse(before)
    assert [ast.unparse(a) for a in call.args] == ["_pc_card_gif_signal()"], ast.unparse(before)
    assert [(k.arg, ast.unparse(k.value)) for k in call.keywords] == [("flush", "True")], ast.unparse(before)
    assert len(_calls(tree, "_pc_card_gif_signal")) == 1


def test_the_line_is_not_one_of_the_witness_markers():
    """The signal is its own marker: one line, never read as a boot or a
    ready line by the train's existing grammar."""
    line = _lifted()["_pc_card_gif_signal"]()
    assert chr(10) not in line and chr(13) not in line
    assert not line.startswith("[BOT-BOOT]") and not line.startswith("[BOT-READY]")
    assert line.startswith("[BOT-FEATURE] ")
