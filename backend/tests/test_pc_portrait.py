"""pc_portrait.py — the pure helpers of the Player Cards portrait pivot
(v22 §1.7, §2.2, §3.2-3.4 + r18 dispositions)."""
import asyncio
import os
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import pc_portrait as P  # noqa: E402


GOOD = ("v1|face=1000:1002:1004:1005|off=0.1234567,-0.25;0,0;1E-05,-1.5E-05;12.5,0"
        "|color=color_azure:3fa9f5|effect=effect_embers|skin=0|anim=1|g=1.2.3|r=1")

PORTRAIT_CS = os.path.join(HERE, "..", "..", "plugin", "PortraitRender.cs")


def test_descriptor_grammar_accepts_lossless_offsets():
    d = P.descriptor_parse(GOOD)
    assert d is not None
    assert d["eye"] == "1000" and d["detail2"] == "1005"
    assert d["color"] == "color_azure" and d["hex"] == "3fa9f5" and d["effect"] == "effect_embers"
    assert d["game"] == "1.2.3" and d["recipe"] == "1" and d["anim"] == "1"


def test_descriptor_grammar_refuses_off_grammar_inputs():
    assert P.descriptor_parse("") is None
    assert P.descriptor_parse(None) is None
    assert P.descriptor_parse(GOOD.replace("skin=0", "skin=x")) is None
    assert P.descriptor_parse(GOOD.replace("anim=1", "anim=2")) is None
    assert P.descriptor_parse(GOOD.replace("|anim=1", "")) is None
    assert P.descriptor_parse(GOOD.replace("0.1234567", "NaN")) is None
    assert P.descriptor_parse(GOOD.replace("0.1234567", "Infinity")) is None
    assert P.descriptor_parse(GOOD.replace("color_azure", "Color Azure")) is None
    assert P.descriptor_parse(GOOD + "|x=1") is None
    assert P.descriptor_parse(GOOD.replace("1.2.3", "1.2.3é")) is None
    # the cap counts bytes: pad the game field past 24 → regex refuses; a
    # legal-grammar string over the cap is refused by the cap itself
    long = GOOD.replace("effect_embers", "e" * 40).replace("color_azure", "c" * 40)
    assert P.descriptor_parse(long) is not None
    assert len(long.encode()) <= P.DESCRIPTOR_MAX_BYTES
    padded = "v1|face=1:1:1:1|off=" + ";".join(["0.00000000000000000000001,0.00000000000000000000001"] * 4) \
             + "|color=" + "c" * 40 + ":ffffff|effect=" + "e" * 40 + "|skin=0|anim=0|g=" + "g" * 24 + "|r=999"
    assert len(padded.encode()) > 200  # would have failed v22's 200-byte cap
    assert P.descriptor_parse(padded) is not None or len(padded.encode()) > P.DESCRIPTOR_MAX_BYTES


def _client_descriptor_literals():
    """The quoted fragments of PortraitRender.cs's descriptor expression, in
    source order. Read as TEXT on purpose -- the point is the literal the C#
    compiler will emit, not anything this process can import."""
    with open(PORTRAIT_CS, encoding="utf-8", newline="") as handle:
        src = handle.read()
    start = src.index('inp.descriptor = "v1')
    expr = src[start:src.index(";", start)]
    return re.findall(r'"([^"\\]*)"', expr)


def _fields(pieces):
    """`v1|face=`, `|off=`, ... -> the field names in order."""
    joined = "".join(pieces)
    out = []
    for chunk in joined.split("|"):
        if "=" in chunk:
            out.append(chunk.split("=", 1)[0])
    return out


def test_the_client_and_the_grammar_name_the_same_fields_in_the_same_order():
    """Neither side may gain or lose a descriptor field alone.

    A field the client sends and the grammar does not know is a 422 on every
    upload, behind a healthy api and a healthy client, with the field's name
    appearing in no log on either side -- the entire picture feature inert with
    clean telemetry (#438). A field the grammar requires and the client never
    sends is the same failure from the other direction."""
    client = _fields(_client_descriptor_literals())
    server = re.findall(r"\\\|(\w+)=", P.DESCRIPTOR_RE.pattern)
    assert client, "no descriptor literals found in PortraitRender.cs"
    assert client == server, (client, server)
    # ...and the fixture every other test in this file is written against is
    # that same sequence, so the fixture cannot drift from the contract either.
    assert _fields([GOOD]) == server


def test_the_field_contract_check_can_fail():
    """The mutation control for the test above (#391): a dropped field, an
    added field and a reordering must each be caught."""
    server = re.findall(r"\\\|(\w+)=", P.DESCRIPTOR_RE.pattern)
    assert [f for f in server if f != "anim"] != server
    assert server + ["skin2"] != server
    assert list(reversed(server)) != server
    # and the extractor really reads the file, rather than returning a constant
    assert "anim" in _fields(_client_descriptor_literals())


def test_canon_line_shape():
    assert P.canon_portrait("765", "n1", "ab" * 32, GOOD) == "pcport:765:n1:" + "ab" * 32 + ":" + GOOD


def test_effective_locale():
    served = {"uk", "sv", "de"}
    assert P.effective_locale("uk", served) == "uk"
    assert P.effective_locale("UK-UA", served) == "uk"
    assert P.effective_locale("sv_SE", served) == "sv"
    assert P.effective_locale("fr", served) == "en"
    assert P.effective_locale("", served) == "en"
    assert P.effective_locale(None, served) == "en"
    assert P.effective_locale("en-GB", served) == "en"
    assert P.effective_locale("u", served) == "en"
    assert P.effective_locale("ukr", served | {"ukr"}) == "ukr"
    assert P.effective_locale("uk;q=0.9", served) == "en"


def test_the_descriptor_requires_the_literal_skin_zero():
    """The client writes `|skin=0|` and nothing else ever will. A field whose
    only legal value is a constant is the cheapest check there is to get
    right, and accepting 1..9 stored a value with no meaning on either side."""
    good = "v1|face=1:2:3:4|off=0,0;0,0;0,0;0,0|color=:|effect=|skin=0|anim=1|g=1.2.3|r=1"
    assert P.descriptor_parse(good) is not None
    for digit in "123456789":
        assert P.descriptor_parse(good.replace("skin=0", "skin=" + digit)) is None, digit


def test_public_name_strips_the_producer_tags_and_leaves_every_other_bracket():
    """The tag set is the mod's own styler's, not `<.*?>`. A name with literal
    brackets in it is a name — "AC<DC>Fan" is the bug-259 case by name."""
    assert P.public_name("<b>Sid</b>") == "Sid"
    assert P.public_name("<color=#FF00aa>Sid</color>") == "Sid"
    assert P.public_name("<size=90%>Sid</size>") == "Sid"
    assert P.public_name("<cspace=1em>Sid</cspace>") == "Sid"
    assert P.public_name("<voffset=0.5em>Sid</voffset>") == "Sid"
    assert P.public_name("<allcaps><smallcaps><i><u><s>Sid</s></u></i></smallcaps></allcaps>") == "Sid"
    # a nested construct collapses in ONE call, and a second call changes nothing
    assert P.public_name("<b<color=#FFFFFF<cspace=1em>>>Sid") == "Sid"
    assert P.public_name(P.public_name("<b<color=#FFFFFF<cspace=1em>>>Sid")) == "Sid"
    # ...and everything that is NOT that tag set is the player's own text
    for kept in ("AC<DC>Fan", "<3", "x<y>z", "</NOPARSE><B>", "<color=#GGGGGG>",
                 "<size=1000%>", "<blink>", "<b >", "<cspace=em>"):
        assert P.public_name(kept) == kept, kept


def test_public_name_normalises_controls_without_breaking_an_emoji_sequence():
    assert P.public_name("a\nb\tc  d") == "a b c d"
    assert P.public_name("a\u0085b") == "a b"                    # NEL, a C1 control
    assert P.public_name("a\u2028b\u2029c") == "a b c"          # Zl and Zp
    assert P.public_name("\u202eevil\u202c") == "evil"          # bidi override
    assert P.public_name("\u2066x\u2069") == "x"                # bidi isolate
    # the joiner and the variation selectors hold a sequence together: strip
    # them and one picture becomes two
    assert P.public_name("\U0001f469\u200d\U0001f4bb") == "\U0001f469\u200d\U0001f4bb"
    assert P.public_name("\u2764\ufe0f") == "\u2764\ufe0f"
    # A control becomes a SPACE, never nothing, so it can never complete a tag
    # for the next pass. That is why the composite's fixed point is a guard
    # here rather than a necessity -- it becomes load-bearing for a step that
    # REMOVES code points, which the coverage projection will.
    assert P.public_name("<b\x01>Sid") == "<b >Sid"
    assert P.public_name("<b\u202a>Sid") == "<b >Sid"


def test_public_name_answers_none_for_everything_unreadable():
    assert P.public_name("76561198040410653") is None
    assert P.public_name("   ") is None
    assert P.public_name(None) is None
    assert P.public_name("<b></b>") is None
    assert P.public_name("Sid") == "Sid"
    assert P.public_name("محمد") == "محمد"          # a legal name is never blanked here
    assert P.public_name("★") == "★"


def test_the_coverage_projection_removes_what_no_font_can_draw():
    """A code point with no glyph in any renderer font is drawn as tofu, and
    the face's revision key would promise those boxes are the right picture."""
    assert P.coverage_project("A\ue001B") == "AB"          # private use: no font has it
    assert P.coverage_project("A\U000f0000B") == "AB"      # supplementary private use
    assert P.coverage_project("Sid") == "Sid"
    assert P.coverage_project("محمد") == "محمد"             # bundled script: kept
    assert P.coverage_project("★") == "★"
    assert P.coverage_project("\U0001f469\u200d\U0001f4bb") == "\U0001f469\u200d\U0001f4bb"
    assert P.coverage_project(None) is None
    assert P.coverage_project("\ue001") is None            # nothing readable left
    assert P.coverage_project("\ue001\ue002 \ue003") is None


def test_the_coverage_projection_re_runs_the_strip_after_its_own_removal():
    """C REMOVES code points, so it can complete a producer tag that was not
    one before -- and the tag strip has to see the string again."""
    assert P.coverage_project("<b\ue001>Sid") == "Sid"
    assert P.coverage_project("<b\ue001>Sid</b\ue002>") == "Sid"
    # ...and it is idempotent, so a payload and a render agree
    for raw in ("<b\ue001>Sid", "A\ue001B", "محمد", "Sid", "\U0001f469\u200d\U0001f4bb"):
        once = P.coverage_project(raw)
        assert P.coverage_project(once) == once, raw


def test_the_public_render_name_is_both_halves_in_order():
    """Applying half of it is the same bug twice, so there is one function."""
    for raw in ("<b>AC<DC>Fan\ue001</b>", "76561198040410653", "  ", "<b\ue001>Sid", None,
                "AC<DC>Fan", "\u202eevil\u202c"):
        assert P.public_render_name(raw) == P.coverage_project(P.public_name(raw)), repr(raw)
    assert P.public_render_name("<b>AC<DC>Fan\ue001</b>") == "AC<DC>Fan"


def test_the_coverage_manifest_keeps_the_joiner_and_the_space():
    """Neither is a glyph and neither is in a cmap, but removing the joiner
    splits one emoji into two."""
    assert P.drawable(0x200D) and P.drawable(0x20) and P.drawable(0xFE0F)
    # Every script §1.3 names, because C blanks a whole name written in one
    # the renderer does not carry, and that is worse than the tofu C prevents.
    for sample in "Aم\u05d0\u0e01\u0939\u0986\u0b85\u10d0\u0561\u4e2d\u2605":
        assert P.drawable(ord(sample)), hex(ord(sample))
    assert not P.drawable(0xE001) and not P.drawable(0xF0000)
    cov = P._coverage()
    for name, (starts, ends) in [("union", cov["union"]), ("always", cov["always"])] + \
            [(r, v) for r, v in cov["roles"].items()]:
        assert starts == sorted(starts) and len(starts) == len(ends), name
        assert all(a <= b for a, b in zip(starts, ends)), name
        assert all(ends[i] + 1 < starts[i + 1] for i in range(len(starts) - 1)), name
    # every base role the renderer draws with is present, with a candidate
    # order that starts at that role -- a manifest missing one would silently
    # relax the projection for the surface drawn with it
    assert set(cov["candidates"]) == {"black", "bold", "script"}, sorted(cov["candidates"])
    for base, roles in cov["candidates"].items():
        assert roles[0] == base and len(set(roles)) == len(roles), (base, roles)
        assert set(roles) <= set(cov["roles"]), (base, roles)


def test_a_cluster_no_single_font_can_draw_does_not_survive():
    """The renderer needs ONE font to cover a whole grapheme cluster. "a" and
    U+0651 are each covered -- by Noto Sans and by Noto Sans Arabic -- so a
    union-of-cmaps projection kept the pair and the face drew a box under a
    revision that promised the pixels were right."""
    assert P.cluster_drawable("a") and P.cluster_drawable("\u0645")
    assert not P.cluster_drawable("a\u0651")
    assert P.coverage_project("a\u0651") is None
    assert P.coverage_project("a\u0651Sid") == "Sid"
    # ...and a cluster ONE font covers whole is kept
    assert P.cluster_drawable("Sid"[0] + "\u0301")
    assert P.coverage_project("Sid\u0301") == "Sid\u0301"


def test_a_name_that_paints_nothing_is_not_a_name():
    """The joiners and the variation selectors ride through the projection so
    they can hold a sequence together -- which made a string of nothing BUT
    them non-empty, so the neutral fallback never fired and the card drew a
    blank where a name goes."""
    assert P.coverage_project("\u200d") is None
    assert P.coverage_project("\ue001\u200d") is None
    assert P.coverage_project("\ufe0f\u200c \u2060") is None
    assert P.coverage_project("\U0001f469\u200d\U0001f4bb") == "\U0001f469\u200d\U0001f4bb"
    assert P.coverage_project("A\u200dB") == "A\u200dB"


def test_single_line_collapses():
    assert P.single_line("ЛЕГЕН\nДАРНА\r\n") == "ЛЕГЕН ДАРНА"
    assert P.single_line(None) == ""


def test_h16_is_length_framed():
    assert P.h16("ab", "c") != P.h16("a", "bc")
    assert P.h16("x") != P.h16(b"x", "")
    assert re.match(r"^[0-9a-f]{16}$", P.h16("anything"))


def test_cat_rev_and_face_rev_depend_on_every_input():
    labels = {"pc.foil": "FOIL", "pc.signed": "SIGNED"}
    r1 = P.cat_rev(labels)
    assert r1 == P.cat_rev({"pc.signed": "SIGNED", "pc.foil": "FOIL"})   # order-free
    assert r1 == P.cat_rev({"pc.foil": "FOIL\n", "pc.signed": " SIGNED "})  # single-line
    assert r1 != P.cat_rev({"pc.foil": "FOLIE", "pc.signed": "SIGNED"})
    # The spec the renderer is actually handed, field for field
    # (main._pc_face_inputs). Every one of these is drawn.
    spec = {"band": "legendary", "name": "Sid", "title": "Grand Master I", "title_rgb": (255, 215, 0),
            "rating": 1800, "pool_rank": 3, "board_rank": 7, "wins": 40, "losses": 12,
            "foil": True, "signed": False, "edition_label": "Edition 1", "minted_on": "2026-09-11",
            "print_short": "#ab12cd", "top_card": True}
    base = dict(renderer_fp="f" * 16, cat_rev_=r1, spec=spec, portrait_kind="game", portrait_hash="h" * 64)
    fr = P.face_rev(**base)
    # EVERY field of the spec, derived from the spec — a field added to it and
    # not to the key is what this has to catch, and naming them here by hand
    # is how it stopped catching anything.
    for key in spec:
        alt = dict(base, spec=dict(spec))
        v = spec[key]
        alt["spec"][key] = (not v) if isinstance(v, bool) else (0 if isinstance(v, (int, float)) else "different")
        assert P.face_rev(**alt) != fr, key
    # ...and a field REMOVED from it, and the three arguments beside it
    for key in spec:
        alt = dict(base, spec={k: v for k, v in spec.items() if k != key})
        assert P.face_rev(**alt) != fr, key
    for k, v in (("portrait_hash", None), ("portrait_kind", "none"), ("cat_rev_", "0" * 16),
                 ("renderer_fp", "e" * 16)):
        assert P.face_rev(**dict(base, **{k: v})) != fr, k
    # order-free, and typed: "True" is not True, 1 is not "1"
    assert P.face_rev(**dict(base, spec=dict(reversed(list(spec.items()))))) == fr
    assert P.face_rev(**dict(base, spec=dict(spec, foil="True"))) != fr
    assert P.face_rev(**dict(base, spec=dict(spec, pool_rank="3"))) != fr
    # the preview key is a different namespace over the same inputs
    assert P.preview_rev(**base) != fr


def test_resolver_matrix():
    row = {"subject_deleted": False, "subject_banned": False, "subject_opted_out": False,
           "portrait_source": "game", "portrait_hash": "abc"}
    assert P.portrait_for(row) == ("game", "abc")
    for k in ("subject_deleted", "subject_banned", "subject_opted_out"):
        alt = dict(row)
        alt[k] = True
        assert P.portrait_for(alt) == ("none", None), k
    assert P.portrait_for({**row, "portrait_source": "none"}) == ("none", None)
    assert P.portrait_for({**row, "portrait_hash": None}) == ("none", None)
    assert P.portrait_for({**row, "portrait_hash": ""}) == ("none", None)
    assert P.portrait_for({**row, "portrait_source": None}) == ("game", "abc")  # absent column = default


def test_face_key_shapes():
    pid = "0b7d2f8e-3c4a-4c2a-9b1e-2f3a4b5c6d7e"
    assert P.face_key(pid, "a" * 16, "uk", "card") == pid + "/" + "a" * 16 + "/uk/card.png"
    assert P.face_key(pid.upper(), "a" * 16, "uk", "card") is None
    assert P.face_key("{" + pid + "}", "a" * 16, "uk", "card") is None
    assert P.face_key(pid.replace("-", ""), "a" * 16, "uk", "card") is None
    assert P.face_key(pid, "A" * 16, "uk", "card") is None
    assert P.face_key(pid, "a" * 15, "uk", "card") is None
    assert P.face_key(pid, "a" * 16, "uk-UA", "card") is None
    assert P.face_key(pid, "a" * 16, "uk", "huge") is None
    assert P.face_key(pid, "a" * 16, "../x", "card") is None


def test_pool_slot_released_by_worker_not_by_timeout():
    """r18 M5: a timed-out request leaves the slot held until the worker ends."""
    started = threading.Event()
    release = threading.Event()

    def slow():
        started.set()
        release.wait(5)
        return "done"

    async def run():
        try:
            await P.in_pool(slow, budget=0.2)
        except asyncio.TimeoutError:
            pass
        assert started.is_set()
        # the semaphore still counts the running worker
        assert P._DECODE_SLOTS._value == 1
        release.set()
        for _ in range(50):
            if P._DECODE_SLOTS._value == 2:
                break
            await asyncio.sleep(0.02)
        assert P._DECODE_SLOTS._value == 2
    asyncio.run(run())


def test_face_cache_single_flight_and_eviction(tmp_path):
    cache = P.FaceCache(str(tmp_path), cap_bytes=30)
    calls = {"n": 0}

    def render():
        calls["n"] += 1
        time.sleep(0.1)
        return b"0123456789"  # 10 bytes

    async def run():
        key = "p/" + "a" * 16 + "/en/card.png"
        a, b, c = await asyncio.gather(cache.get_or_render(key, render), cache.get_or_render(key, render),
                                       cache.get_or_render(key, render))
        assert a == b == c == b"0123456789"
        assert calls["n"] == 1
        assert cache.read(key) == b"0123456789"
        assert await cache.get_or_render(key, render) == b"0123456789" and calls["n"] == 1
        for i in range(4):
            await cache.get_or_render("q%d/" % i + "b" * 16 + "/en/tile.png", render)
        assert sum(cache._sizes.values()) <= 30
        assert cache.read(key) is None  # the oldest went first
    asyncio.run(run())
