"""The private NameServer fetch, and the invariants that keep it private.

`RegionCatalog` opens a LoadBalancingClient of its own to read Photon's region
list, because PUN builds one only from an OpGetRegions response and a ranked
join force-connects past the gate that issues it -- so a player who only ever
queues ranked has no region list for the whole process and rung 0 can never
fire for them.

A second Photon client inside a running game is the most invasive thing in this
batch, and the design rounds kept finding the SAME hazard from new directions:
`RegionHandler`'s constructor writes a PROCESS-WIDE static, `PortToPingOverride`,
which is what `SetRegions` bakes into every address and what the real sweep reads
when it builds targets. Gating each path that could reach it is the kind of check
that has to be exhaustive to work. The bound replaces it: the probe is handed the
GAME's own port overrides so it normally writes the value already there, and the
previous value is restored on every exit unless a later writer (PUN) got there
first.

These are structure tests over the real C# source. There is no way to run this
code here -- it needs a Unity process, a Photon app id and a network -- so what
can be defended is the SHAPE: that the forced options stay literals, that the
static is saved and restored, that the fetch stays out of the game's own
NameServer window, and that there is exactly one target-construction body.
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
CATALOG = PLUGIN / "RegionCatalog.cs"
SWEEP = PLUGIN / "RegionPingSweep.cs"

CATALOG_CLASS = "internal static class RegionCatalog"
START = "static void Start(float rt, AppSettings app)"
TRY_START = "static void TryStart(float rt)"
SERVICE = "static void ServiceProbe(float rt)"


def _masked(signature, source=CATALOG):
    return mask_code(cs_block(source, signature))


def test_the_probe_forces_its_auth_options_rather_than_mirroring_them():
    """AuthOnce and AuthOnceWss leave EncryptionEstablished by a different
    branch and reach paths that reset ServerPortOverrides. Mirroring the game's
    value would make the safe case depend on a setting nobody here controls, so
    both are written as literals. A test, because 'mirror it' is the natural
    edit for someone tidying this up later."""
    body = _masked(START)
    assert "AuthMode = AuthModeOption.Auth;" in body, "AuthMode is no longer forced to plain Auth"
    assert "EnableProtocolFallback = false;" in body
    assert "app.AuthMode" not in body and "PhotonNetwork.AuthMode" not in body, (
        "the probe mirrors an auth option instead of forcing it"
    )


def test_the_probe_never_pings_because_it_never_asks_to():
    """ConnectToNameServer sets connectToBestRegion = false, which is what stops
    PUN pinging all regions after SetRegions. The probe must therefore use that
    entry point and no other -- ConnectUsingSettings or ConnectToBestCloudServer
    would both start a full region ping on our private client."""
    body = _masked(START)
    assert "ConnectToNameServer()" in body
    for forbidden in ("ConnectUsingSettings", "ConnectToBestCloudServer", "ConnectToRegion", "ConnectToMasterServer"):
        assert forbidden not in body, f"the probe calls {forbidden}, which is not a name-server-only connect"


def test_the_process_wide_port_override_is_saved_and_restored():
    """The bound the whole design rests on. Save before the connect that can
    build a RegionHandler; restore on the way out; and restore only when our own
    value is still the one in place, because a later writer is PUN and PUN's
    value is the correct one."""
    src = strip_comments_only(CATALOG.read_text(encoding="utf-8"))
    assert "savedPortOverride = RegionHandler.PortToPingOverride;" in src, (
        "the previous value of the process-wide static is never captured"
    )
    restore = _masked("static void RestorePortOverride()")
    assert "RegionHandler.PortToPingOverride == probeWrotePortOverride" in restore, (
        "the restore is unconditional -- it would clobber a value PUN wrote after us"
    )
    assert "RegionHandler.PortToPingOverride = savedPortOverride;" in restore


def test_every_probe_exit_path_restores_the_static():
    """Finish() handles publication, failure and abort alike; Release() is the
    belt. If either stopped calling the restore, the static could be left
    holding the probe's value for the rest of the process."""
    assert "RestorePortOverride()" in _masked("static void Finish(float rt, RegionHandler rh, string why)")
    assert "RestorePortOverride()" in _masked("static void Release()")


def test_the_static_is_restored_before_the_sweep_is_woken():
    """Ordering, and it is the whole bound.

    NoteCatalogReady re-enters RegionPingSweep.TryStart SYNCHRONOUSLY. If PUN
    acquired a region list of its own while this fetch was in flight, that sweep
    takes the PUN branch and reads the process-wide static directly -- so the
    static has to be the game's value again by the time the callback runs.
    Waking the sweep first would hand the single reader this bound exists to
    protect exactly the value it must not see.

    THE MUTATION THIS MUST FAIL ON: moving the NoteCatalogReady call back above
    RestorePortOverride, which is where it naturally wants to sit (right after
    the publish it announces)."""
    finish = mask_code(cs_block(CATALOG, "static void Finish(float rt, RegionHandler rh, string why)"))
    restore_at = finish.find("RestorePortOverride()")
    wake_at = finish.find("NoteCatalogReady()")
    assert restore_at != -1, "Finish no longer restores the static"
    assert wake_at != -1, "Finish no longer wakes the sweep"
    assert restore_at < wake_at, (
        "the sweep is woken before the port-override static is restored"
    )


def test_the_fetch_stays_out_of_the_games_own_nameserver_window():
    """That window is the only one in which PUN itself builds a RegionHandler or
    rewrites its port overrides. Checked BOTH before starting and on every
    service tick -- a fetch that began legally can still be overtaken."""
    assert "GameIsOnNameServer" in _masked(TRY_START), "the start gate no longer checks it"
    assert "GameIsOnNameServer" in _masked(SERVICE), "a fetch in flight is never re-checked"


def test_the_fetch_refuses_while_the_port_override_is_unset():
    """PhotonNetwork.ServerPortOverrides reads back default while
    NetworkingClient is null. Fetching then bakes Photon's stock port into every
    address, and a catalog of wrong ports measures nothing -- it does not fail
    loudly, it produces numbers for hosts nobody is listening on."""
    body = _masked(TRY_START)
    # This USED to assert only that the member was mentioned, reasoning that
    # `== 0 -> return` and `!= 0 -> proceed` are the same gate and that pinning
    # an operator breaks on a harmless rewrite (#441). That was wrong here: the
    # two spellings are only equivalent when the BRANCH flips with the operator,
    # and nothing checked the branch -- so inverting this one comparison shipped
    # D2 permanently inert with a green suite. Polarity is the invariant, so
    # polarity is what gets pinned.
    assert "ServerPortOverrides.MasterServerPort" in body, (
        "the start gate no longer looks at the port override at all"
    )
    raw_gate = strip_comments_only(cs_block(CATALOG, TRY_START))
    assert re.search(r"MasterServerPort\s*==\s*0", raw_gate), (
        "the zero test is gone or inverted -- with `!= 0` reaching the refusal, "
        "the fetch is refused whenever the port IS set, which is always"
    )
    assert not re.search(r"MasterServerPort\s*!=\s*0", raw_gate), (
        "the gate now proceeds on `!= 0`; that is only equivalent if the branch "
        "flipped too, and this test cannot see the branch"
    )
    # The reason is a string literal, and mask_code blanks those -- read it off
    # the comment-stripped block instead.
    raw = strip_comments_only(cs_block(CATALOG, TRY_START))
    assert "no-port-override" in raw, "the refusal is no longer reported"


def test_the_catalog_carries_the_port_its_own_addresses_were_built_for():
    """A catalog-sourced sweep must not read the process-wide static: the whole
    point is that the static belongs to PUN and may be rewritten at any time."""
    src = strip_comments_only(CATALOG.read_text(encoding="utf-8"))
    assert "PortOverride = probeWrotePortOverride;" in src
    # Read off the SELECTION, not the file. The previous version asked only
    # whether the string "RegionCatalog.PortOverride" appeared anywhere in
    # RegionPingSweep.cs -- which a log line or a comment satisfies, and which
    # stays true even if the ternary below always picks the static.
    sweep = strip_comments_only(SWEEP.read_text(encoding="utf-8"))
    pick = re.search(
        r"int\s+portOverride\s*=\s*(?P<expr>[^;]+);", sweep
    )
    assert pick, "the sweep no longer chooses a port override in one place"
    expr = " ".join(pick.group("expr").split())
    assert "RegionCatalog.PortOverride" in expr and "RegionHandler.PortToPingOverride" in expr, (
        f"the port for a sweep is no longer chosen between the two sources: {expr}"
    )
    assert expr.index("RegionHandler.PortToPingOverride") < expr.index("RegionCatalog.PortOverride"), (
        f"the PUN branch no longer takes the process-wide static: {expr}"
    )
    assert "punHasList" in expr, (
        f"the choice is no longer keyed on which source supplied the list: {expr}"
    )


def test_there_is_exactly_one_target_construction_body():
    """#432. Two sources, one construction: a second loop is where the port
    rule, the dedupe and the MAX_TARGETS cap drift apart."""
    sweep_src = strip_comments_only(SWEEP.read_text(encoding="utf-8"))
    assert sweep_src.count("new Target {") == 1, (
        "a second target-construction body appeared; the port rule can now differ between sources"
    )
    assert "static List<Target> BuildTargets(" in sweep_src


# Any assignment whose TARGET starts at PhotonNetwork, however deep the path:
# `PhotonNetwork.X =`, `PhotonNetwork.X.Y =`, `PhotonNetwork.X.Y.Z +=`. The
# first version stopped at one member, so `PhotonNetwork.NetworkingClient.
# CloudRegion = "eu";` -- a write straight into the game's live client, and the
# worst thing in this file's threat model -- walked past it.
# `==`/`!=`/`>=`/`<=` are excluded by the (?!=) and by requiring no leading
# comparison character.
_PN_ASSIGN = re.compile(
    r"PhotonNetwork\s*\.\s*(\w+(?:\s*\.\s*\w+)*)\s*(?:[-+*/|&^]|<<|>>)?=(?!=)"
)


def test_the_catalog_never_writes_the_games_photon_state():
    """The probe is a separate object with a separate socket. Any assignment to
    a PhotonNetwork member, or to the game's own NetworkingClient, means it
    stopped being separate.

    THE MUTATION THIS MUST FAIL ON: adding `PhotonNetwork.OfflineMode = true;`
    anywhere in the file. The first version of this test COULD NOT FAIL on that
    line: it cut the candidate name at the first SPACE, so `OfflineMode = true;`
    reduced to `OfflineMode`, carried no `=`, and passed. A check that cannot
    fail is worse than no check, because it is counted as coverage (#342/#431).
    """
    body = strip_comments_only(CATALOG.read_text(encoding="utf-8"))
    writes = _PN_ASSIGN.findall(body)
    assert not writes, f"the catalog assigns to PhotonNetwork state: {writes}"
    assert "NetworkingClient.RegionHandler =" not in body, (
        "the catalog assigns its list into the game's client"
    )


def test_a_failed_fetch_leaves_the_published_list_alone():
    """Failure direction. Entries is written in exactly one place, and only from
    a list that actually came back non-empty -- so every refusal, timeout and
    abort leaves the previous answer (usually null, which is today's
    behaviour) rather than publishing an empty or partial catalog."""
    src = strip_comments_only(CATALOG.read_text(encoding="utf-8"))
    writes = [
        line for line in src.splitlines()
        if "Entries =" in line and "==" not in line and "!=" not in line
    ]
    assert len(writes) == 1, f"Entries is written from {len(writes)} places: {writes}"
    assert "Entries = list.ToArray();" in writes[0]
    finish = _masked("static void Finish(float rt, RegionHandler rh, string why)")
    assert "if (list.Count > 0)" in finish, "an empty region list can be published"


def test_the_feature_has_a_kill_switch_that_is_checked_before_starting():
    """New networking code in a mod with a live population needs a lever that
    can be flipped without a rebuild. It gates the START only: a probe already
    in flight is still serviced and torn down, because dropping an unserviced
    client leaks the socket instead of closing it."""
    tick = _masked("public static void Tick()")
    assert "Enabled()" in tick
    assert tick.index("ServiceProbe") < tick.index("Enabled()"), (
        "the lever is checked before a live probe is serviced, which would leak the socket"
    )
    # SENSE, not just presence. `if (Enabled()) return;` is one character from
    # the truth and ships the whole feature inert with every test still green,
    # which is the failure this project keeps re-learning (#438/#443).
    assert re.search(r"if\s*\(\s*!\s*Enabled\s*\(\s*\)\s*\)\s*return\s*;", tick), (
        "the lever no longer reads `if (!Enabled()) return;` -- an un-negated "
        "check disables the feature whenever it is switched ON"
    )
    assert 'Bind(' in strip_comments_only(CATALOG.read_text(encoding="utf-8"))


@pytest.mark.parametrize("member", ["Entries", "PortOverride"])
def test_the_sweep_reads_the_catalog_through_its_published_members(member):
    """The catalog's contract with the sweep. If one end is renamed, this says so
    at the seam rather than at a null reference.

    WHAT WAS WRONG WITH THIS TEST: `assert f"public static " in ...` is an
    f-string with no placeholder, so all four parametrisations asserted the same
    constant substring -- which RegionCatalog.cs contains six times for unrelated
    reasons. Making `PortOverride` internal, the exact regression the test is
    named for, left it fully green. It also never opened RegionPingSweep.cs, so
    the seam it claims to defend was not read at either end. Narrowed to the two
    members the sweep really consumes: FetchedAt and Revision have no reader
    outside RegionCatalog.cs, so naming them here was decoration.
    """
    src = strip_comments_only(CATALOG.read_text(encoding="utf-8"))
    assert re.search(rf"public\s+static\s+\S+\s+{re.escape(member)}\s*[;={{]", src), (
        f"{member} is no longer declared as a public static on the catalog"
    )
    sweep = strip_comments_only(SWEEP.read_text(encoding="utf-8"))
    assert f"RegionCatalog.{member}" in sweep, (
        f"the sweep no longer reads RegionCatalog.{member}; the seam is broken "
        "at the consuming end"
    )
def test_the_restore_leaves_the_static_alone_when_it_holds_the_games_port():
    """The HIGH from the implementation review, and the reason the previous
    version of this bound was not a bound at all.

    PUN builds its own RegionHandler with `ServerPortOverrides.MasterServerPort`
    (LoadBalancingClient.cs:1527) -- the SAME value this probe is handed. So
    `static == probeWrotePortOverride` cannot distinguish "nobody wrote after
    us" from "PUN wrote an identical value", and in the second case the saved
    value is 0 (a ranked-only session never built a RegionHandler, which is why
    this class exists). Restoring 0 makes RegionHandler.cs:95 skip the port
    replacement on PUN's NEXT SetRegions, so PUN pings Photon's stock port --
    precisely the breakage the catalog was added to avoid.

    The invariant is therefore about the VALUE, not about who wrote it: if the
    static already carries the game's port, leave it alone.

    THE MUTATION THIS MUST FAIL ON: deleting the `want` early-return, which
    restores the old value-equality behaviour.
    """
    restore = mask_code(cs_block(CATALOG, "static void RestorePortOverride()"))
    assert "ServerPortOverrides.MasterServerPort" in restore, (
        "the restore never asks what port the GAME wants, so it can only compare "
        "against its own write -- which PUN can duplicate"
    )
    want_at = restore.find("MasterServerPort")
    undo_at = restore.find("PortToPingOverride = savedPortOverride")
    assert undo_at != -1, "the restore no longer puts the previous value back at all"
    assert want_at < undo_at, (
        "the game's own port is consulted only after the old value is written back"
    )
    assert "return;" in restore[want_at:undo_at], (
        "nothing short-circuits the undo when the static already holds the game's port"
    )
def test_every_refused_start_charges_an_attempt():
    """Consume() reads its interval from `attempts`, so a refusal that does not
    charge one retries at the SHORTEST backoff -- forever, never reaching the
    ceiling that exists to stop exactly that. Both pre-connect exits (PUN
    refusing ConnectToNameServer, and a throw during start) have to charge.

    THE MUTATION THIS MUST FAIL ON: moving `attempts++` back below the
    ConnectToNameServer refusal, which is where it sat and is the natural place
    to put it if you are thinking about the SUCCESS path only.
    """
    start = mask_code(cs_block(CATALOG, START))
    charge_at = start.find("attempts++")
    connect_at = start.find("ConnectToNameServer()")
    assert charge_at != -1, "Start no longer counts attempts at all"
    assert connect_at != -1
    assert charge_at < connect_at, (
        "the attempt is charged only after the connect succeeds, so a permanent "
        "connect refusal never ages the backoff"
    )
    # The catch that wraps the start attempt lives in TryStart, not Tick.
    guard = mask_code(cs_block(CATALOG, TRY_START))
    catch_at = guard.find("catch")
    assert catch_at != -1, "the start path no longer has a catch"
    assert "attempts++" in guard[catch_at:], (
        "a throwing start does not age the backoff, so a repeatable exception "
        "retries at the shortest interval for the life of the process"
    )
