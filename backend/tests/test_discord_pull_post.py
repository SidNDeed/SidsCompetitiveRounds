"""Discord fix round 1 (player report 2026-09-28), D3: the notable-pull post in
the gambler chat (poll_pc_events).

The report - the post rendered as text only - was not reproduced on the
shipped build, and the production logs could not show what Discord stored:
the drain discarded the answer to its own send, and a 200 from the face route
whose body the reader refused posted the line text-only without a trace. This
round changes three things, each pinned here:

(a) the drain logs Discord's receipt of every post it makes - the attachments
    Discord stored (name, content type, size, pixel size) and the embed image
    as Discord resolved it - or why the post went without a picture;
(b) a 200 whose body the byte reader refused is named in the log and retried
    like a 5xx, within the drain's bounded tries, instead of posting the line
    text-only at once;
(c) the face is bound into an embed (look design v22 section 6:
    embed.set_image(url="attachment://card.png")), never a loose attachment;
    the line stays the message text.

Round 2, L1 (Codex round 1 LOW 1): a face route answering 404 - the print was
discarded between the handout and the GET - posts NOTHING, acks NOTHING and
releases the lease (v22 section 6 (2)); the groups behind it still post.

Stubbed rows: the drain's requests are answered by a stub on the harness
BotRig's clock; no database is read.
"""

import asyncio
import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import discord_collection_harness as H

FUNCS = H.REVEAL_FUNCS | {"_pc_send_face", "_pc_receipt", "poll_pc_events", "_pc_event_lines"}
ASSIGNS = H.REVEAL_ASSIGNS | {"_pc_events_sent", "_pc_face_tries", "_PC_FACE_TRIES", "_PC_RARITY_COLOR"}
CHANNEL = 4242
FACE_PATH = "/internal/pc/face/print/"
CAP = 4 * 1024 * 1024


def png(pad=0):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (40, 60, 80)).save(buf, format="PNG")
    return buf.getvalue() + bytes(pad)


class Embed:
    def __init__(self, title=None, color=None, description=None, **kw):
        self.title, self.color, self.description, self.image = title, color, description, None

    def set_image(self, url=None):
        self.image = url
        return self


class Drain:
    """The routes the drain reads, in their shapes: one pending event of one
    print until it is acked, the ack, the lease routes, and the face route
    answering `faces` in turn (the last one repeats)."""

    def __init__(self, faces, face_ready=True, rarity="epic"):
        self.subject = "11111111-1111-1111-1111-111111111111"
        self.print_id = "22222222-2222-2222-2222-222222222222"
        self.faces = list(faces)
        self.face_ready, self.rarity = face_ready, rarity
        self.acked = []

    async def __call__(self, call):
        p, m = call.path, call.method
        if m == "GET" and p == "/internal/pc/events/pending":
            if self.acked:
                return H.Reply(200, json={"events": []})
            return H.Reply(200, json={"events": [{
                "id": 7, "kind": self.rarity, "puller_name": "Fixture puller", "subject_name": "Fixture subject",
                "subject_ref": self.subject, "face_ready": self.face_ready, "dup_at_pull": 0,
                "print": {"print_id": self.print_id, "rarity": self.rarity, "pool_rank": 4}}]})
        if m == "POST" and p == "/internal/pc/events/ack":
            self.acked.append(dict(call.params))
            return H.Reply(200, json={"acked": 1})
        if m == "POST" and p == "/internal/pc/lease":
            until = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
            return H.Reply(200, json={"lease_id": "lease-1", "until": until})
        if m == "GET" and p.startswith("/internal/pc/lease/"):
            return H.Reply(200, json={"live": True})
        if m == "DELETE" and p.startswith("/internal/pc/lease/"):
            return H.Reply(200, json={"released": True})
        if m == "GET" and p.startswith(FACE_PATH):
            return self.faces.pop(0) if len(self.faces) > 1 else self.faces[0]
        raise AssertionError(f"unexpected request {m} {p}")


def _fake_wait_for(clock):
    async def wait_for(aw, timeout=None):
        t0 = clock.now
        out = await aw
        if timeout is not None and clock.now - t0 > float(timeout):
            raise asyncio.TimeoutError()
        return out
    return wait_for


def rig_for(handler, stored=None):
    """The lifted drain over `handler`; the channel's send returns
    `stored(kwargs)` - a Message-like object, as discord.py's send returns
    the created message - or None."""
    holder = {}

    async def send(content=None, **kw):
        holder["rig"].sent.append(H.Sent(content=content, file=kw.get("file"), ephemeral=False,
                                         kw={k: v for k, v in kw.items() if k != "file"}))
        return stored(kw) if stored is not None else None
    channel = SimpleNamespace(id=CHANNEL, send=send)
    fake_discord = SimpleNamespace(
        Member=SimpleNamespace, File=H._File, HTTPException=H._HTTPException, Forbidden=H._HTTPException,
        NotFound=type("NotFound", (Exception,), {}), Embed=Embed,
        AllowedMentions=SimpleNamespace(none=lambda: "none"),
        utils=SimpleNamespace(escape_markdown=lambda s, **k: str(s)))
    extra = {"discord": fake_discord, "PC_EVENTS_CHANNEL_ID": CHANNEL,
             "bot": SimpleNamespace(get_channel=lambda cid: channel if cid == CHANNEL else None)}
    rig = H.BotRig(handler, funcs=FUNCS, assigns=ASSIGNS, extra=extra)
    rig.ns["asyncio"].wait_for = _fake_wait_for(rig.clock)
    holder["rig"] = rig
    return rig


def tick(rig):
    H.run(rig.ns["poll_pc_events"]())


def good_face(face):
    return H.Reply(200, face, {"content-type": "image/png"})


def short_face(face):
    """A 200 that declares ten bytes more than it sends."""
    return H.Reply(200, face, {"content-type": "image/png", "content-length": str(len(face) + 10)})


# -- (c) the embed binding ----------------------------------------------------------------------

def test_d3_the_face_rides_inside_an_embed_and_the_line_stays_the_text():
    face = png()
    drain = Drain([good_face(face)])
    rig = rig_for(drain)
    tick(rig)
    assert len(rig.sent) == 1, [s.content for s in rig.sent]
    post = rig.sent[0]
    assert post.content.startswith("**Fixture puller** pulled a ") and "**Fixture subject** (#4 in the pool)!" in post.content
    embed = post.kw.get("embed")
    assert embed is not None, "the face went as a loose attachment"
    assert embed.image == "attachment://card.png"
    assert embed.color == rig.ns["_PC_RARITY_COLOR"]["epic"]
    assert post.file is not None and post.file.filename == "card.png" and post.file.data == face
    assert drain.acked == [{"ids": "7", "leases": "lease-1"}]


# -- (a) the receipt ------------------------------------------------------------------------------

def test_d3_the_drain_logs_what_discord_stored_for_the_post():
    face = png()

    def stored(kw):
        return SimpleNamespace(
            attachments=[SimpleNamespace(filename="card.png", content_type="image/png", size=len(face),
                                         width=750, height=1050)],
            embeds=[SimpleNamespace(image=SimpleNamespace(url="https://media.test/card.png", width=750,
                                                          height=1050))])
    rig = rig_for(Drain([good_face(face)]), stored)
    tick(rig)
    # The trailing art note (Discord card render parity): this fixture's face
    # answer carries no X-Face-Art / X-Face-Still, as an older api's would not.
    want = (f"[PC-EVENTS] line for [7] stored by Discord: attachments [card.png image/png {len(face)} B 750x1050],"
            " embed image 750x1050 art=- still=-")
    assert want in rig.logs, rig.logs


def test_d3_a_post_whose_picture_discord_did_not_keep_says_so_in_the_log():
    """The reported symptom, as the receipt shows it: the send carried the
    face, and Discord's answer lists no attachment and no embed image."""
    rig = rig_for(Drain([good_face(png())]), lambda kw: SimpleNamespace(attachments=[], embeds=[]))
    tick(rig)
    assert ("[PC-EVENTS] line for [7] stored by Discord: attachments [none], embed image none art=- still=-"
            in rig.logs), rig.logs


def test_d3_a_post_sent_without_a_picture_logs_why():
    rig = rig_for(Drain([good_face(png())], face_ready=False))
    tick(rig)
    assert len(rig.sent) == 1 and rig.sent[0].file is None and rig.sent[0].kw.get("embed") is None
    assert ("[PC-EVENTS] line for [7] posted without a picture (the subject's picture was unresolved when the"
            " hold ran out (face_ready false))") in rig.logs, rig.logs


def test_d3_an_unreadable_receipt_never_fails_a_post_that_went_out():
    class Broken:
        @property
        def attachments(self):
            raise RuntimeError("odd message")
    drain = Drain([good_face(png())])
    rig = rig_for(drain, lambda kw: Broken())
    tick(rig)
    assert len(rig.sent) == 1 and drain.acked, "the post went out and is acked, not re-driven"
    assert ("[PC-EVENTS] line for [7] posted; the receipt could not be read (RuntimeError) art=- still=-"
            in rig.logs), rig.logs
    tick(rig)
    assert len(rig.sent) == 1, "posted once"


# -- (b) a 200 without a usable body ---------------------------------------------------------------

def test_d3_a_200_whose_body_is_refused_is_retried_and_not_posted_text_only():
    face = png()
    drain = Drain([short_face(face), good_face(face)])
    rig = rig_for(drain)
    tick(rig)
    assert rig.sent == [] and drain.acked == [], [s.content for s in rig.sent]
    refused = [line for line in rig.logs if line.startswith("API GET " + FACE_PATH)]
    assert refused and refused[0].endswith(f"-> HTTP 200 with {len(face)} of its {len(face) + 10} bytes: body refused"), rig.logs
    assert any("no picture for 7 yet (try 1)" in line for line in rig.logs), rig.logs
    tick(rig)
    assert len(rig.sent) == 1 and rig.sent[0].file is not None and rig.sent[0].file.data == face
    assert rig.sent[0].kw["embed"].image == "attachment://card.png" and drain.acked


def test_d3_a_face_route_that_keeps_refusing_posts_after_the_bounded_tries_and_says_why():
    drain = Drain([short_face(png())])
    rig = rig_for(drain)
    for _ in range(3):
        tick(rig)
        assert rig.sent == []
    tick(rig)
    assert len(rig.sent) == 1 and rig.sent[0].file is None and rig.sent[0].kw.get("embed") is None
    assert ("[PC-EVENTS] line for [7] posted without a picture (the face route answered HTTP 200 without a"
            " usable body, retried 3 times)") in rig.logs, rig.logs
    assert drain.acked


def _cl_missing(face):
    reply = H.Reply(200, face, {"content-type": "image/png"})
    del reply.headers["content-length"]
    return reply


@pytest.mark.parametrize("make, tail", [
    (_cl_missing, "-> HTTP 200 without a Content-Length: body refused"),
    (lambda face: H.Reply(200, b"", {"content-type": "image/png", "content-length": "0"}),
     f"-> HTTP 200 declaring 0 bytes, outside 1..{CAP}: body refused"),
    (lambda face: H.Reply(200, face, {"content-type": "image/png", "content-length": str(CAP + 1)}),
     f"-> HTTP 200 declaring {CAP + 1} bytes, outside 1..{CAP}: body refused"),
    (lambda face: H.Reply(200, face + b"x", {"content-type": "image/png", "content-length": str(len(face))}),
     "-> HTTP 200 longer than its {n} bytes: body refused"),
])
def test_d3_the_byte_reader_names_every_200_it_refuses(make, tail):
    face = png()
    reply = make(face)

    async def handler(call):
        return reply
    rig = H.BotRig(handler, funcs=FUNCS, assigns=ASSIGNS)
    st, data, _meta = H.run(rig.ns["_pc_api_bytes"](FACE_PATH + "x/en"))
    assert (st, data) == (200, None)
    want = "API GET " + FACE_PATH + "x/en " + tail.format(n=len(face))
    assert want in rig.logs, rig.logs


# -- round 2, L1: a face 404 posts nothing ------------------------------------------------------
#
# Codex round 1 LOW 1: a face route answering 404 posted the line text-only
# and acked it. Look design v22 section 6 (2): a 404 (the print was discarded
# between the pending answer and the GET) sends NOTHING, acks NOTHING and
# releases the lease - the pending query excludes discarded prints, so the
# event is not offered again - and any other failure stops the batch.

GONE_PRINT = "33333333-3333-3333-3333-333333333333"


def released(rig):
    """The lease ids the drain gave back with DELETE /internal/pc/lease/<id>."""
    return [c.path.rsplit("/", 1)[1] for c in rig.calls
            if c.method == "DELETE" and c.path.startswith("/internal/pc/lease/")]


def test_l1_a_face_404_posts_nothing_acks_nothing_and_releases_the_lease():
    drain = Drain([H.Reply(404, json={"detail": "Not Found"})])
    rig = rig_for(drain)
    tick(rig)
    assert rig.sent == [], [s.content for s in rig.sent]
    assert [c.path for c in rig.calls if c.path == "/internal/pc/events/ack"] == [] and drain.acked == []
    assert released(rig) == ["lease-1"], [(c.method, c.path) for c in rig.calls]
    assert ("[PC-EVENTS] face for [7] answered HTTP 404 (the print is gone) - nothing posted, nothing acked,"
            " lease released") in rig.logs, rig.logs
    assert rig.ns["_pc_events_sent"] == {} and rig.ns["_pc_face_tries"] == {}


class TwoPrints(Drain):
    """Two pending events of two prints, each with its own lease: the face
    route answers `gone` for the first print and a picture for the second."""

    def __init__(self, gone, kept):
        super().__init__([kept])
        self.gone, self.leases = gone, 0

    async def __call__(self, call):
        p, m = call.path, call.method
        if m == "GET" and p == "/internal/pc/events/pending":
            return H.Reply(200, json={"events": [
                {"id": 7, "kind": "legendary", "puller_name": "First puller", "subject_name": "First subject",
                 "subject_ref": self.subject, "face_ready": True, "dup_at_pull": 0,
                 "print": {"print_id": GONE_PRINT, "rarity": "legendary", "pool_rank": 1}},
                {"id": 8, "kind": "epic", "puller_name": "Second puller", "subject_name": "Second subject",
                 "subject_ref": self.subject, "face_ready": True, "dup_at_pull": 0,
                 "print": {"print_id": self.print_id, "rarity": "epic", "pool_rank": 4}}]})
        if m == "POST" and p == "/internal/pc/lease":
            self.leases += 1
            until = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
            return H.Reply(200, json={"lease_id": f"lease-{self.leases}", "until": until})
        if m == "GET" and p.startswith(FACE_PATH + GONE_PRINT):
            return self.gone
        return await super().__call__(call)


def test_l1_a_face_404_skips_only_its_own_group_and_the_groups_behind_it_still_post():
    face = png()
    drain = TwoPrints(H.Reply(404, json={"detail": "Not Found"}), good_face(face))
    rig = rig_for(drain)
    tick(rig)
    assert len(rig.sent) == 1, [s.content for s in rig.sent]
    assert rig.sent[0].content.startswith("**Second puller** pulled a ")
    assert rig.sent[0].file is not None and rig.sent[0].file.data == face
    assert drain.acked == [{"ids": "8", "leases": "lease-2"}]
    # the 404's own release, before the next group is leased; then the post's (_pc_send_face)
    assert released(rig) == ["lease-1", "lease-2"], [(c.method, c.path) for c in rig.calls]
    gave_back = next(i for i, c in enumerate(rig.calls) if c.method == "DELETE" and c.path.endswith("/lease-1"))
    leased = [i for i, c in enumerate(rig.calls) if c.method == "POST" and c.path == "/internal/pc/lease"]
    assert len(leased) == 2 and gave_back < leased[1]
    assert any(line.startswith("[PC-EVENTS] face for [7] answered HTTP 404") for line in rig.logs), rig.logs
