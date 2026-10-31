"""The availability-check withdrawal path (the tavail buttons of the
tournament availability DM) keeps the clicker's raw Discord id out of every
log line it can reach (the Codex FENCE-R1 M1).

Before acting, the path re-resolves the clicker's current link through
GET /players/by-discord/<id>. A failure of that lookup was logged through the
shared [TDLC] sink with the raw id, and an exception's own text can quote the
request URL, which carries the id in its path. Driven through the lifted
on_interaction over the harness's fake transport (no database):

  * the lookup raises an exception that quotes the URL: the [TDLC] line
    carries the id's last four digits and the exception's text with the id
    replaced, never the id;
  * the withdrawal goes through: the [TAVAIL] line names the user (what
    discord.py's User.__str__ prints), not the id;
  * the reply to a refused withdrawal fails to send with the id in its error
    text: the [TOURNAMENT-INTERACTION] line carries the tail only.

Every case also requires that its own sink was reached, so a run that logs
nothing cannot pass.
"""
from types import SimpleNamespace

import pytest

import discord_collection_harness as H

DID = 912345678901234567              # synthetic 18-digit Discord id
TAIL = "..." + str(DID)[-4:]
TID = "6f1c2d3e-0000-4000-8000-000000000001"
STEAM = H.steam_of(7)                 # synthetic, not an individual SteamID64
CID = "tavail:%s:%s:no" % (TID, STEAM)
FUNCS = {"on_interaction", "_tdlc_verify_clicker", "_tournament_unsignup",
         "_discord_tail", "_scrub_discord_id"}
ASSIGNS = {"_tavail_locks", "_tavail_withdrawn"}


class _User:
    """discord.py's User.__str__ prints the username, never the id."""

    def __init__(self, uid, name):
        self.id, self.name = uid, name

    def __str__(self):
        return self.name


def _rig(handler):
    fake_discord = SimpleNamespace(
        Interaction=object,
        InteractionType=SimpleNamespace(component="component"),
        AllowedMentions=SimpleNamespace(none=lambda: "none"))
    return H.BotRig(handler, funcs=FUNCS, assigns=ASSIGNS, extra={"discord": fake_discord})


def _click(rig, send_error=None):
    sent = []

    async def defer(**kw):
        return None

    async def send(content=None, **kw):
        if send_error is not None:
            raise send_error
        sent.append(content)

    async def edit(**kw):
        sent.append(kw.get("content"))

    interaction = SimpleNamespace(
        type="component", data={"custom_id": CID}, user=_User(DID, "entrant7"),
        response=SimpleNamespace(defer=defer), followup=SimpleNamespace(send=send),
        message=SimpleNamespace(edit=edit))
    H.run(rig.ns["on_interaction"](interaction))
    return sent


def _no_raw_id(rig):
    raw = [ln for ln in rig.logs if str(DID) in ln]
    assert raw == [], raw


def test_a_failed_link_lookup_logs_the_tail_and_scrubs_the_exception_text():
    async def handler(call):
        if call.path.startswith("/players/by-discord/"):
            raise RuntimeError("500, message='Internal Server Error', url='%s/api/v1/players/by-discord/%s'"
                               % (H.BASE_URL, DID))
        raise AssertionError("no other request expected: %s %s" % (call.method, call.path))
    rig = _rig(handler)
    sent = _click(rig)
    assert [c.path for c in rig.calls] == ["/players/by-discord/%s" % DID]
    assert sent and "verify your linked account" in sent[0]
    tdlc = [ln for ln in rig.logs if ln.startswith("[TDLC] link verification failed")]
    assert len(tdlc) == 1, rig.logs
    assert ("for discord %s: RuntimeError: " % TAIL) in tdlc[0], tdlc[0]
    assert ("by-discord/%s'" % TAIL) in tdlc[0], tdlc[0]
    _no_raw_id(rig)


def test_a_withdrawal_that_goes_through_logs_the_username_not_the_id():
    async def handler(call):
        if call.path.startswith("/players/by-discord/"):
            return H.Reply(200, json={"steam_id": STEAM})
        if call.path == "/tournaments/%s/unsignup" % TID:
            assert call.payload["discord_id"] == str(DID)   # the server still gets the id
            return H.Reply(200, json={})
        raise AssertionError("unexpected request: %s %s" % (call.method, call.path))
    rig = _rig(handler)
    _click(rig)
    assert [ln for ln in rig.logs if ln.startswith("[TAVAIL] entrant7 withdrew from tournament 6f1c2d3e")], rig.logs
    _no_raw_id(rig)


def test_a_reply_that_fails_with_the_id_in_its_text_logs_the_tail_only():
    async def handler(call):
        if call.path.startswith("/players/by-discord/"):
            return H.Reply(200, json={"steam_id": STEAM})
        if call.path == "/tournaments/%s/unsignup" % TID:
            return H.Reply(409, json={"detail": "This withdrawal prompt no longer matches the "
                                                "account's Discord link."})
        raise AssertionError("unexpected request: %s %s" % (call.method, call.path))
    rig = _rig(handler)
    _click(rig, send_error=RuntimeError("400 Bad Request: cannot message user %s" % DID))
    err = [ln for ln in rig.logs if ln.startswith("[TOURNAMENT-INTERACTION] error: ")]
    assert len(err) == 1, rig.logs
    assert ("cannot message user %s" % TAIL) in err[0], err[0]
    _no_raw_id(rig)


@pytest.mark.parametrize("value, want", [(DID, TAIL), (str(DID), TAIL), (None, "?"), ("", "?")])
def test_the_tail_is_four_digits_and_never_the_id(value, want):
    rig = _rig(None)
    assert rig.ns["_discord_tail"](value) == want
    assert rig.ns["_scrub_discord_id"]("id %s and %s" % (value, value), value) == (
        "id %s and %s" % (want, want) if value else "id %s and %s" % (value, value))
