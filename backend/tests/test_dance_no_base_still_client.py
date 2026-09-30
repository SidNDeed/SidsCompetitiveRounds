"""Report 1 (2026-09-30): no base still is sent while a dance is selected.

The production state the triage read: a dance motion stored and bound to the
dance still, then 56 s later a base still (no dance suffix) stored over it.
The motion's binding no longer held, so every print of the player read "no
motion" and the binder card stood still. The client's still-only path sent
that base still: a Fallback (the seat could not capture right then) or a None
fell through to the product upload.

The pure half -- which route the still-only path may take while a dance is
selected -- is EXECUTED by tools/tests/dance-cards-client (cases t58_*, with
the mutants t58_fallback_sends_base and t58_selection_ignored). These gates
are the structural half: the callers that could send a base still.

* There is exactly one base-still sender, PortraitRender.Upload, and one
  dance-still sender, DanceApiPort.UploadStill. A new PcPortraitUpload caller
  anywhere else is a finding (it would bypass the backstop).
* Upload refuses before the request while /pc/me is unread or names a dance
  selection (the backstop every caller shares, the dev lever and the pacing
  retry included).
* The decision layer routes around it: DanceVisit and RefreshStart hand a
  selected dance's None/Fallback to DanceStillOnly, which only ever renders the
  Settings preview (upload false); RefreshStart keeps an unread /pc/me armed.
* The dance job's still goes up under the dance descriptor.

Every structural decision is made on `_cs_structure`'s mask, so a needle in a
comment or a string is not structure (learnings #342/#431/#441). Each gate has
an in-memory mutation control below that must turn it red.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

import pytest

from _cs_structure import cs_block, mask_code

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"

RENDER = "PortraitRender.cs"
DANCE = "PortraitRenderDance.cs"
API = "ApiClient.cs"

UPLOAD = "private static void Upload(string key, string descriptor, byte[] png, string why)"
UPLOAD_STILL = "public void UploadStill(string descriptor, byte[] png, Action<DanceMotionCore.Answer> done)"
DANCE_VISIT = "private static bool DanceVisit(ApiClient.PcMe me, string want)"
REFRESH_START = "private static bool RefreshStart(string why)"
STILL_ONLY = ("private static bool DanceStillOnly(ApiClient.PcMe me, string want, string sku, string why, "
              "bool transient, out bool settled)")
UPLOAD_DEF = "public static void PcPortraitUpload("
SENDER = "PcPortraitUpload("

# On the mask a string literal is blanked, so Start("visit", true) reads Start(   , true).
UPLOADING_START = re.compile(r"\bStart\(\s*[^,()]*,\s*true\s*\)")

GATE = re.compile(
    r"var\s+(\w+)\s*=\s*ApiClient\.CachedPcMe\s*;\s*"
    r"if\s*\(\s*\1\s*==\s*null\s*\|\|\s*DanceMotionCore\.DanceSelected\(\s*\1\.dance_supported\s*,\s*\1\.pc_dance_sku\s*\)\s*\)\s*\{")


@functools.lru_cache(maxsize=None)
def _read_all() -> tuple:
    return tuple((p.name, p.read_text(encoding="utf-8")) for p in sorted(PLUGIN.glob("*.cs")))


def _sources() -> dict:
    return dict(_read_all())


@functools.lru_cache(maxsize=64)
def _mask(text: str) -> str:
    return mask_code(text)


@functools.lru_cache(maxsize=64)
def _block_cached(src: str, signature: str) -> str:
    return mask_code(cs_block(src, signature))


def _balanced(masked: str, open_brace: int) -> str:
    depth = 0
    for i in range(open_brace, len(masked)):
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return masked[open_brace:i + 1]
    raise AssertionError("unbalanced block")


def _block(src: str, signature: str) -> str:
    """The masked body of the one block `signature` opens."""
    return _block_cached(src, signature)


def findings(sources: dict) -> list:
    out = []
    # A. the senders: exactly the base-still backstop and the dance job's still.
    callers = {}
    for name, src in sources.items():
        if SENDER not in src:
            continue                  # the raw text is a superset of the mask: nothing to count
        masked = _mask(src)
        n = masked.count(SENDER) - (masked.count(UPLOAD_DEF) if name == API else 0)
        if n:
            callers[name] = n
    if callers != {RENDER: 1, DANCE: 1}:
        out.append("A: PcPortraitUpload callers are %r, not one in %s and one in %s" % (callers, RENDER, DANCE))
    try:
        if _block(sources[RENDER], UPLOAD).count(SENDER) != 1:
            out.append("A: PortraitRender.Upload does not hold the base-still sender exactly once")
        if _block(sources[DANCE], UPLOAD_STILL).count(SENDER) != 1:
            out.append("A: DanceApiPort.UploadStill does not hold the dance-still sender exactly once")
    except AssertionError as e:
        out.append("A: " + str(e))
    # B. the backstop: refused before the request while /pc/me is unread or names a dance.
    try:
        up = _block(sources[RENDER], UPLOAD)
        gates = list(GATE.finditer(up))
        if len(gates) != 1:
            out.append("B: Upload carries %d CachedPcMe/DanceSelected gates, not 1" % len(gates))
        else:
            g = gates[0]
            body = _balanced(up, g.end() - 1)
            if "return;" not in body:
                out.append("B: Upload's dance gate does not return")
            if up.find(SENDER) < g.start():
                out.append("B: Upload's dance gate comes after the request")
            if up.count("DanceMotionCore.DanceSelected(") != 1:
                out.append("B: DanceSelected occurs %d times in Upload" % up.count("DanceMotionCore.DanceSelected("))
    except AssertionError as e:
        out.append("B: " + str(e))
    # C. the decision layer.
    try:
        visit = _block(sources[DANCE], DANCE_VISIT)
        refresh = _block(sources[DANCE], REFRESH_START)
        only = _block(sources[DANCE], STILL_ONLY)
        if visit.count("DanceStillOnly(") != 1:
            out.append("C: DanceVisit calls DanceStillOnly %d times, not 1" % visit.count("DanceStillOnly("))
        if UPLOADING_START.search(visit) or "StartProduct(" in visit:
            out.append("C: DanceVisit starts an uploading product run itself")
        if refresh.count("DanceStillOnly(") != 1:
            out.append("C: RefreshStart calls DanceStillOnly %d times, not 1" % refresh.count("DanceStillOnly("))
        base = [m.start() for m in re.finditer(r"\bStart\(\s*why\s*,\s*true\s*\)", refresh)]
        armed = re.search(r"if\s*\(\s*me\s*==\s*null\s*\)\s*return\s+false\s*;", refresh)
        sel = refresh.find("DanceMotionCore.DanceSelected(")
        if len(base) != 1:
            out.append("C: RefreshStart holds %d uploading product starts, not 1" % len(base))
        elif armed is None or armed.start() > base[0]:
            out.append("C: RefreshStart does not keep an unread /pc/me armed before the product start")
        elif sel < 0 or sel > base[0] or refresh.find("DanceStillOnly(") > base[0]:
            out.append("C: RefreshStart reaches the product start without the dance selection route")
        if UPLOADING_START.search(only) or "StartProduct(" in only or SENDER in only:
            out.append("C: DanceStillOnly can start an upload")
        base_route = re.findall(r"if\s*\(\s*route\s*==\s*DanceMotionCore\.StillOnly\.Base\s*\)\s*return\s+false\s*;", only)
        if "DanceMotionCore.StillOnlyRoute(" not in only or len(base_route) != 1 or len(re.findall(r"\breturn\s+false\b", only)) != 1:
            out.append("C: DanceStillOnly does not return false on the Base route alone")
    except AssertionError as e:
        out.append("C: " + str(e))
    # D. the dance job's still carries the dance descriptor.
    dm = _mask(sources[DANCE])
    jobs = re.findall(r"new\s+DanceUploadJob\(\s*\w+\s*,\s*(\w+)\s*,", dm)
    bound = bool(jobs) and re.search(r"\b%s\s*=\s*DanceDescriptor\(" % re.escape(jobs[0]), dm) is not None
    if len(jobs) != 1 or not bound:
        out.append("D: the dance job is not built with a descriptor from DanceDescriptor (%r)" % (jobs,))
    return out


def test_no_base_still_is_sent_while_a_dance_is_selected():
    got = findings(_sources())
    assert got == [], "\n".join(got)


# -- mutation controls: each reverts one part of the fix in memory ------------

def _mutate(name: str, old: str, new: str) -> dict:
    src = _sources()
    assert src[name].count(old) == 1, "mutation anchor %r occurs %d times in %s" % (old, src[name].count(old), name)
    src[name] = src[name].replace(old, new)
    return src


MUTANTS = [
    ("upload_gate_removed", RENDER,
     "if (pcMe == null || DanceMotionCore.DanceSelected(pcMe.dance_supported, pcMe.pc_dance_sku))",
     "if (false)", "B:"),
    ("upload_gate_after_the_request", RENDER,
     "if (pcMe == null || DanceMotionCore.DanceSelected(pcMe.dance_supported, pcMe.pc_dance_sku))",
     "if (pcMe == null)", "B:"),
    ("refresh_falls_through", DANCE,
     "if (DanceStillOnly(me, want, sku, why, transient, out settled)) return settled;",
     "", "C:"),
    ("refresh_sends_without_pc_me", DANCE,
     "if (me == null) return false;\n", "", "C:"),
    ("visit_falls_through", DANCE,
     "if (!DanceStillOnly(me, want, sku, \"visit\", transient, out settled)) return false;",
     "if (true) return false;", "C:"),
    ("still_only_uploads", DANCE,
     "if (want != null && (PreviewTex == null || PreviewDescriptor != want)) Start(\"preview\", false);",
     "if (want != null && (PreviewTex == null || PreviewDescriptor != want)) Start(\"visit\", true);", "C:"),
    ("a_second_sender", RENDER,
     "internal static void Tick()\n        {",
     "internal static void Tick()\n        {\n            ApiClient.PcPortraitUpload(null, null, null, null, null);", "A:"),
]


@pytest.mark.parametrize("label,name,old,new,prefix", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_each_mutation_is_caught(label, name, old, new, prefix):
    src = _mutate(name, old, new)
    got = findings(src)
    assert any(f.startswith(prefix) for f in got), "mutant %s not caught: %r" % (label, got)
