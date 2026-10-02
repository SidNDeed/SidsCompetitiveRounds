"""Discord card render parity, the bot (design section 3.2; build item 4).

The bot never composites: every picture it posts is the api's render, so the
top card's art reaches Discord through the existing internal routes and
credential with no new send. What the bot gains is observability only:

- the relay's receipt line ends with ` art=<drawn|none> still=<still>` when
  the picture went, from the face answer's X-Face-Art / X-Face-Still headers;
- the reveal run's picture path prints `[PC-REVEAL] <kind> ref=<ref> posted
  art=<drawn>/<face tiles>` from X-Strip-Art / X-Grid-Art;
- a boot witness `[BOT-FEATURE] card_art=<n> -- gen=<gen>`, DERIVED from the
  compiled code of the two senders (1 when both load _pc_art_note).

The row-12 delivery rule is held here as well: one reveal message per
invocation, the picture fetched once; a refused or failed picture posts the
text alone, never a second reveal. Each assertion's mutation is planted by
ai-collab's mutation runner; the passing case is the control.
"""
import ast
import os
import re
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import discord_collection_harness as H  # noqa: E402
import test_discord_pull_post as PP  # noqa: E402
from test_discord_collection_bot import (Synth, make_rig, synth_pack, synth_binder,  # noqa: E402
                                         one_post_with_image, one_post_without_image, busy)

BOT = os.path.join(HERE, "..", "discord_bot.py")
GEN = "0123456789ab"
LINE = re.compile(r"\A\[BOT-FEATURE\] card_art=(\S+) -- gen=(\w+)\Z")
WITNESS_FUNCS = {"_pc_card_art_word", "_pc_card_art_signal", "_pc_art_note", "_pc_reveal_run", "poll_pc_events"}


def _lifted(funcs=WITNESS_FUNCS):
    ns = {"_BOT_GEN": GEN, "discord": SimpleNamespace(Member=object)}
    exec(compile(H.lift(funcs, {"_PC_CARD_ART_READERS"}), BOT, "exec"), ns)
    return ns


# -- the note -----------------------------------------------------------------------------

def test_the_note_reads_the_headers_of_the_answer_it_is_given():
    note = _lifted()["_pc_art_note"]
    assert note({"x-face-art": "drawn", "x-face-still": "dance"}, "face") == "art=drawn still=dance"
    assert note({"x-face-art": "none", "x-face-still": "base"}, "face") == "art=none still=base"
    assert note({}, "face") == "art=- still=-"
    assert note(None, "face") == "art=- still=-"
    assert note({"x-strip-art": "4/5", "x-grid-art": "9/9"}, "pack") == "art=4/5"
    assert note({"x-strip-art": "4/5", "x-grid-art": "9/9"}, "binder") == "art=9/9"
    assert note({}, "binder") == "art=-"


# -- the relay ------------------------------------------------------------------------------

def _stored(face):
    def stored(kw):
        return SimpleNamespace(
            attachments=[SimpleNamespace(filename="card.png", content_type="image/png", size=len(face),
                                         width=750, height=1050)],
            embeds=[SimpleNamespace(image=SimpleNamespace(url="https://media.test/card.png", width=750,
                                                          height=1050))])
    return stored


def test_the_relay_receipt_carries_the_faces_art_and_still():
    face = PP.png()
    reply = H.Reply(200, face, {"content-type": "image/png", "x-face-art": "drawn", "x-face-still": "dance"})
    drain = PP.Drain([reply])
    rig = PP.rig_for(drain, _stored(face))
    PP.tick(rig)
    want = (f"[PC-EVENTS] line for [7] stored by Discord: attachments [card.png image/png {len(face)} B 750x1050],"
            " embed image 750x1050 art=drawn still=dance")
    assert want in rig.logs, rig.logs
    assert len(rig.sent) == 1 and drain.acked
    faces = [c for c in rig.calls if c.path.startswith(PP.FACE_PATH)]
    assert len(faces) == 1 and faces[0].params.get("size") == "card"     # the same route, fetched once


def test_a_relay_line_without_its_picture_carries_no_art_note():
    rig = PP.rig_for(PP.Drain([PP.good_face(PP.png())], face_ready=False))
    PP.tick(rig)
    lines = [ln for ln in rig.logs if ln.startswith("[PC-EVENTS] line for [7]")]
    assert lines and all("art=" not in ln for ln in lines), lines


# -- the reveal ------------------------------------------------------------------------------

class ArtSynth(Synth):
    def __init__(self, kind="pack", art="5/5", **kw):
        super().__init__(kind=kind, **kw)
        self.art = art

    def headers(self):
        out = dict(super().headers())
        out["x-strip-art" if self.kind == "pack" else "x-grid-art"] = self.art
        return out


def test_the_pack_reveal_posts_once_and_says_how_many_faces_carry_art():
    synth = ArtSynth("pack", art="4/5")
    rig = make_rig(synth)
    H.run(synth_pack(rig))
    one_post_with_image(rig)
    assert len(rig.byte_gets()) == 1
    posted = [ln for ln in rig.logs if ln.startswith("[PC-REVEAL] pack ref=") and " posted " in ln]
    assert len(posted) == 1 and posted[0].endswith(" posted art=4/5"), rig.logs


def test_the_binder_reveal_reads_the_grid_header():
    synth = ArtSynth("binder", art="10/10")
    rig = make_rig(synth)
    H.run(synth_binder(rig))
    one_post_with_image(rig)
    posted = [ln for ln in rig.logs if ln.startswith("[PC-REVEAL] binder ref=") and " posted " in ln]
    assert len(posted) == 1 and posted[0].endswith(" posted art=10/10"), rig.logs


def test_a_reveal_whose_picture_fails_posts_the_text_alone_once():
    """Slow or failing renders keep the existing ladder: the picture's GETs
    retry on the retryable code, then the text posts alone -- one message,
    no posted-art line, never a second reveal."""
    synth = ArtSynth("pack")
    synth.on_bytes = lambda k, call: busy()
    rig = make_rig(synth)
    H.run(synth_pack(rig))
    one_post_without_image(rig)
    assert not [ln for ln in rig.logs if " posted art=" in ln], rig.logs


# -- the boot witness ------------------------------------------------------------------------

def test_the_witness_reads_one_on_this_build():
    ns = _lifted()
    assert ns["_pc_card_art_word"]() == 1
    m = LINE.match(ns["_pc_card_art_signal"]())
    assert m and (m.group(1), m.group(2)) == ("1", GEN)


async def _no_note(*a, **k):
    return "posted"


def test_the_witness_is_derived_from_both_senders_code():
    ns = _lifted()
    real = ns["poll_pc_events"]
    ns["poll_pc_events"] = _no_note
    assert ns["_pc_card_art_word"]() == 0
    ns["poll_pc_events"] = SimpleNamespace(coro=real)          # a tasks.Loop is read through .coro
    assert ns["_pc_card_art_word"]() == 1
    ns["_pc_reveal_run"] = _no_note
    assert ns["_pc_card_art_word"]() == 0


def test_a_failing_derivation_never_stops_the_line():
    ns = _lifted()
    ns["poll_pc_events"] = SimpleNamespace(coro=None)
    m = LINE.match(ns["_pc_card_art_signal"]())
    assert m and m.group(1).startswith("error:"), m


def test_on_ready_prints_the_witness_once_before_the_discord_fix_witness():
    tree = ast.parse(H.bot_source())
    ready = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_ready"]
    assert len(ready) == 1
    stmts = [ast.unparse(s) for s in ready[0].body]
    assert stmts.count("print(_pc_card_art_signal(), flush=True)") == 1
    assert stmts.index("print(_pc_card_art_signal(), flush=True)") < stmts.index("print(_pc_fix_ready_line())")
    calls = [c for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
             and c.func.id == "_pc_card_art_signal"]
    assert len(calls) == 1
