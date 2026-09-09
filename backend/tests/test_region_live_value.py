"""D4: what "the region this client is on right now" is allowed to mean.

`PhotonNetwork.CloudRegion` is not that value. Its getter refuses only when the
client is null, not connected, or on the NameServer -- and two of those three
lie. In a lingering post-Sandbox OfflineMode (#122) `IsConnected` is hardcoded
true and `Server` reports MasterServer, so the getter hands back
`NetworkingClient.CloudRegion`, which `Disconnect()` never clears; only
`ConnectToNameServer()` does. And `IsConnected` itself is true for EVERY state
but PeerCreated and Disconnected (LoadBalancingClient.cs:186), so a client in
Disconnecting -- or part-way through reconnecting -- still names the region of
the connection it is tearing down.

Both of those report a region the player is not on, to a server that ranks a
live snapshot ABOVE a cached home. `ApiClient.LiveOnlineRegion()` is the one
place allowed to make that judgement, and these tests defend its shape and the
size of the surface that bypasses it.

Structure tests over the real C# source; there is no Unity process here.
"""

import re
from pathlib import Path

import pytest

from _cs_structure import (
    cs_block,
    mask_code,
    strip_comments_only,
)

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
API = PLUGIN / "ApiClient.cs"

LIVE = "public static string LiveOnlineRegion()"
BEST = "public static string BestKnownPhotonRegion()"


def _masked(signature, source=API):
    return mask_code(cs_block(source, signature))


def test_offline_mode_is_refused_before_the_region_is_ever_read():
    """OfflineMode is the ONLY discriminator that does not lie -- NetworkClientState,
    Server and IsConnected all report a healthy connection inside the Sandbox --
    so it has to be checked first, and on its own."""
    body = _masked(LIVE)
    off_at = body.find("PhotonNetwork.OfflineMode")
    read_at = body.find("PhotonNetwork.CloudRegion")
    assert off_at != -1, "LiveOnlineRegion no longer checks OfflineMode at all"
    assert read_at != -1, "LiveOnlineRegion no longer reads CloudRegion"
    assert off_at < read_at, (
        "the region is read before OfflineMode is ruled out, so a lingering "
        "Sandbox flag hands back a region this client is not on"
    )


def test_the_settled_states_are_named_positively():
    """An allow-list, not a deny-list, and the asymmetry is the reason.

    Being too strict returns "" and the server's ladder falls back to the
    cached home -- a real signal, just an older one. Missing one state in a
    deny-list reports a region this client is not on, which the ladder then
    ranks ABOVE both players' caches. There are five Disconnecting/Connecting
    states plus ConnectWithFallbackProtocol to forget; there are three settled
    ones to remember.

    THE MUTATION THIS MUST FAIL ON: replacing the allow-list with
    `if (!PhotonNetwork.IsConnected) return "";`, which is what the getter
    already does and what let Disconnecting through.
    """
    body = _masked(LIVE)
    assert "NetworkClientState" in body, (
        "LiveOnlineRegion no longer looks at the client state, so every state "
        "but PeerCreated and Disconnected reports a region again"
    )
    for settled in ("ConnectedToMasterServer", "JoinedLobby", "Joined"):
        assert settled in body, f"the settled state {settled} is no longer accepted"
    for transitional in ("Disconnecting", "ConnectingToMasterServer", "Authenticating"):
        assert transitional not in body, (
            f"{transitional} is named, which means the check became a deny-list -- "
            "one it does not name then reports a stale region"
        )


def test_the_state_gate_runs_before_the_region_is_read():
    """Ordering, because a gate after the read is only a filter on a value that
    was already trusted enough to fetch."""
    body = _masked(LIVE)
    assert body.find("NetworkClientState") < body.find("PhotonNetwork.CloudRegion")


def test_the_live_read_is_funnelled_through_one_helper():
    """#432: the defect was a CLASS, not a line. Every place that wants "the
    region right now" has to come through LiveOnlineRegion, or it inherits the
    OfflineMode and Disconnecting holes on its own.

    The four surviving direct reads are individually accounted for:
      ApiClient.cs        1 -- LiveOnlineRegion itself, the funnel
      CompetitiveUI.cs    1 -- display only; its defect was the enclosing gate,
                               which now requires IsConnected && InRoom && !OfflineMode
      GameStateWatcher.cs 2 -- both already behind an InRoom/!OfflineMode return

    A fifth is a new bypass and this test is where it surfaces. Raising the
    number is not the fix; routing the new caller through the helper is.
    """
    counts = {}
    for path in sorted(PLUGIN.glob("*.cs")):
        n = strip_comments_only(path.read_text(encoding="utf-8")).count("PhotonNetwork.CloudRegion")
        if n:
            counts[path.name] = n
    assert counts == {
        "ApiClient.cs": 1,
        "CompetitiveUI.cs": 1,
        "GameStateWatcher.cs": 2,
    }, f"the set of direct CloudRegion readers changed: {counts}"


def test_the_ranked_join_reports_a_live_value_and_a_cache_separately():
    """The 1v1 queue body is the one caller that must NOT fall back: it carries
    `region` and `home_region` as two distinct signals the server's ladder ranks
    against each other, so filling `region` from the cache would make a cached
    home outrank itself. Every other body wants the best value available."""
    src = strip_comments_only(API.read_text(encoding="utf-8"))
    assert src.count("region = LiveOnlineRegion();") == 1, (
        "the live-only join site is gone or has been duplicated"
    )
    # The funnel itself: BestKnownPhotonRegion's live rung must be the helper,
    # never a direct read.
    best = _masked(BEST)
    assert "LiveOnlineRegion()" in best, (
        "BestKnownPhotonRegion no longer takes its live value from the helper"
    )
    assert "PhotonNetwork.CloudRegion" not in best, (
        "BestKnownPhotonRegion reads CloudRegion directly again"
    )


@pytest.mark.parametrize(
    "signature",
    [LIVE, BEST],
)
def test_neither_helper_can_throw_at_its_caller(signature):
    """Both are called while building request bodies on the queue path. Photon
    property getters touch NetworkingClient, which can be null mid-teardown --
    an exception there would fail the join itself, so the failure direction is a
    quiet "" and the ladder decides."""
    body = _masked(signature)
    assert "catch" in body, f"{signature} no longer swallows a Photon-side throw"
    # mask_code blanks string literals, so `return "";` reads as `return   ;`
    # there -- the empty-string path has to be read off comment-stripped source.
    raw = strip_comments_only(cs_block(API, signature))
    assert re.search(r'return\s+""\s*;', raw), (
        f"{signature} no longer has an empty-string failure path"
    )
