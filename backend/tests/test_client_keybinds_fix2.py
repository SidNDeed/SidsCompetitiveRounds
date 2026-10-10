"""Item 17 fix pass 2 (round-2 findings M1, M2, M3): the production wiring
of the mechanisms the harness executes. The decisions themselves run in
tools/client-rules-harness (the keybinds suite's T1 cases 25-29 and the
keybindfix2 suite, which also runs on the reviewed pin); these gates assert
that the plugin feeds them and acts on them.

Every decision is taken on `_cs_structure`'s mask or comment strip and
scoped to a span resolved by signature, never file-wide and never by line
number (#432/#330).
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

import _cs_structure

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PLUGIN = REPO / "plugin"
KB = PLUGIN / "Keybinds.cs"
RULES = PLUGIN / "KeybindRules.cs"


@functools.lru_cache(maxsize=None)
def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=64)
def _mask(src: str) -> str:
    return _cs_structure.mask_code(src)


@functools.lru_cache(maxsize=64)
def _strip(src: str) -> str:
    return _cs_structure.strip_comments_only(src)


def _span(src: str, signature: str):
    """The one block that follows `signature` in the mask."""
    masked = _mask(src)
    spans, search = [], 0
    while True:
        start = masked.find(signature, search)
        if start == -1:
            break
        open_brace = masked.find("{", start + len(signature))
        assert open_brace != -1, signature
        depth, end = 0, None
        for i in range(open_brace, len(masked)):
            if masked[i] == "{":
                depth += 1
            elif masked[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        assert end is not None, "unbalanced after %r" % signature
        spans.append((open_brace, end))
        search = end
    assert len(spans) == 1, "%r resolved to %d bodies" % (signature, len(spans))
    return spans[0]


def _code(src: str, signature: str) -> str:
    a, b = _span(src, signature)
    return _mask(src)[a:b]


def _text(src: str, signature: str) -> str:
    a, b = _span(src, signature)
    return _strip(src)[a:b]


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s)


# -- M1 (round-2 F2): the independently latched keyboard-edge source ---------

def test_m1_the_frame_source_carries_the_independent_keyboard_channel():
    body = _ws(_text(_src(RULES), "internal interface IFrameInput"))
    assert "int KeyboardEdges();" in body


def test_m1_the_attribution_reads_the_source_before_its_early_return():
    body = _ws(_text(_src(RULES), "internal static EdgeAttribution Attribute(IFrameInput io, int[] alias, int[] scan)"))
    assert body.count("io.KeyboardEdges()") == 1
    read = body.index("io.KeyboardEdges()")
    early = body.index("if (!any && !typed && kb <= 0) return a;")
    assert read < early
    # the comparison is independent of the mouse: no Mouse term on its line
    assert "if (kb > named) a |= EdgeAttribution.Unknown;" in body
    assert "if (kb < 0 && (a & EdgeAttribution.Mouse) != 0) a |= EdgeAttribution.Unknown;" in body
    # every keyboard KeyCode the scan names is counted, the alias's included
    assert body.count("if (IsKeyboardCode(c)) named++;") == 2


def test_m1_the_real_input_reads_the_latch():
    body = _ws(_text(_src(KB), "private sealed class RealInput : IFrameInput"))
    assert "public int KeyboardEdges() { return KeyboardEdgeLatch.EdgesThisFrame(); }" in body


def test_m1_the_latch_reads_the_thread_keyboard_state_once_a_frame():
    cls = _ws(_text(_src(KB), "internal static class KeyboardEdgeLatch"))
    assert '[DllImport("user32.dll")] private static extern bool GetKeyboardState([Out] byte[] lpKeyState);' in cls
    edges = _ws(_text(_src(KB), "internal static int EdgesThisFrame()"))
    assert "if (f == readFrame) return edges;" in edges
    assert "ok = GetKeyboardState(cur);" in edges
    assert "if ((down && !wasDown) || flipped) n++;" in edges
    assert "Buffer.BlockCopy(cur, 0, prev, 0, 256);" in edges
    counted = _ws(_text(_src(KB), "internal static bool Counted(int vk)"))
    # the mouse buttons and the generic modifiers are never keyboard edges
    assert "if (vk < 3 || vk > 254) return false;" in counted
    assert "if (vk == 4 || vk == 5 || vk == 6) return false;" in counted
    assert "if (vk == 0x10 || vk == 0x11 || vk == 0x12) return false;" in counted


def test_m1_the_chat_tap_reads_the_latch_on_every_call():
    body = _code(_src(KB), "internal static bool ChatChannelTapped(bool chatInputOpen)")
    first = body.index("KeyboardEdgeLatch.EdgesThisFrame();")
    assert first < body.index("if (CaptureOwnsInput)")
    assert first < body.index("if (!chatInputOpen)")
