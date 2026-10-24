"""Verified reads, requirement 26 (round 1 M4, round 2 M2): the chat socket's
read-side protocol, tested as executable decisions (read_gate.socket_stage_refusal,
socket_census_class, socket_connect_verdict, socket_recheck_verdict,
socket_enforcing). The socket gate is NOT built: SOCKET_READ_GATE_BUILT stays
False, and the last tests prove that no stage selects socket enforcement while
it is.

The complete protocol is ONE table: Section 0 (b2) of the build notes, held
here as PROTOCOL, one row per (gate built or not, stage, credential at
connect), and asserted row by row by test_protocol_row. Its rules:

1. Order at connect: the version check, accept(), then the stage. A built
   gate on a node whose stage is unknown closes 1013 read_gate_unavailable
   BEFORE any credential lookup, so no valid credential is admitted on it.
2. Credentials from the handshake headers only: X-Internal-Key (compared with
   API_SECRET_KEY), X-Session-Token and X-Operator-Key (looked up through the
   HTTP gate's verifiers; a cache miss is charged to the per-address limiter
   first, and a refused charge is the word `limited`). Under enforce any one
   valid credential admits.
3. Two separate results: the census class (five values: internal, session,
   operator:<name>, mod_no_session, other) and the refusal diagnosis
   (stage_unknown, lookup_error, lookup_limited, replication_pending,
   bad_session, bad_operator_key, no_credential; None when admitted).
4. Close code and reason per diagnosis: 1013 read_gate_unavailable
   (stage_unknown, lookup_error), 1013 rate_limited, 1013
   session_replication_pending, 4401 session_required, 4401
   operator_key_invalid, 4401 read_credential_required.
5. Counting: not built, counted in log and enforce; built, counted in log,
   enforce and unknown, not in off.
6. Rechecks while open (built, enforce): session expiry 4401 session_expired
   at expires_at; a deleted session 4401 session_required; a revoked key 4401
   operator_key_invalid; an unverified socket 4401 read_credential_required;
   log and off close nothing; a built gate whose stage reads unknown closes
   1013 read_gate_unavailable.

The `other` class of a real accepted socket is tested in
test_read_gate_outcomes.test_ws_connect_counted_other. Protocol tests run with
the constant raised inside the test only (monkeypatch), which is what the
future implementation will run under.
"""
from __future__ import annotations

import pytest

import read_gate_testkit as K   # noqa: F401  (puts backend/api on sys.path)
import main
import read_gate as G

V = G.socket_connect_verdict
R = G.socket_recheck_verdict
STAGES = ("off", "log", "enforce", G.UNKNOWN)
CENSUS_CLASSES = {"internal", "session", "operator:scrmod", "mod_no_session", "other"}
DIAGNOSES = {"stage_unknown", "lookup_error", "lookup_limited", "replication_pending",
             "bad_session", "bad_operator_key", "no_credential"}

PROTOCOL = [
    # (built, stage, credential, verdict inputs, admit, close code, close reason,
    #  census class, counted, refusal diagnosis)
    (False, 'any', 'internal key valid', {'internal': True}, True, None, None, 'internal', 'log/enforce', None),
    (False, 'any', 'internal key wrong', {}, True, None, None, 'mod_no_session', 'log/enforce', None),
    (False, 'any', 'session valid', {'session': 'valid'}, True, None, None, 'session', 'log/enforce', None),
    (False, 'any', 'session expired or unverified', {'session': 'bad'}, True, None, None, 'session', 'log/enforce', None),
    (False, 'any', 'session unknown, primary', {'session': 'miss'}, True, None, None, 'session', 'log/enforce', None),
    (False, 'any', 'session unknown, standby', {'session': 'miss', 'replica': True}, True, None, None, 'session', 'log/enforce', None),
    (False, 'any', 'session lookup raised', {'session': 'error'}, True, None, None, 'session', 'log/enforce', None),
    (False, 'any', 'session lookup limited', {'session': 'limited'}, True, None, None, 'session', 'log/enforce', None),
    (False, 'any', 'operator key live', {'operator': 'valid'}, True, None, None, 'operator:scrmod', 'log/enforce', None),
    (False, 'any', 'operator key unissued or revoked', {'operator': 'bad'}, True, None, None, 'mod_no_session', 'log/enforce', None),
    (False, 'any', 'operator lookup raised', {'operator': 'error'}, True, None, None, 'mod_no_session', 'log/enforce', None),
    (False, 'any', 'operator lookup limited', {'operator': 'limited'}, True, None, None, 'mod_no_session', 'log/enforce', None),
    (False, 'any', 'nothing, version header', {}, True, None, None, 'mod_no_session', 'log/enforce', None),
    (False, 'any', 'nothing, no version header', {'version_present': False}, True, None, None, 'other', 'log/enforce', None),
    (False, 'any', 'failed session beside a live operator key', {'session': 'bad', 'operator': 'valid'}, True, None, None, 'session', 'log/enforce', None),
    (True, 'unknown', 'internal key valid', {'internal': True}, False, 1013, 'read_gate_unavailable', 'internal', 'yes', 'stage_unknown'),
    (True, 'unknown', 'internal key wrong', {}, False, 1013, 'read_gate_unavailable', 'mod_no_session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'session valid', {'session': 'valid'}, False, 1013, 'read_gate_unavailable', 'session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'session expired or unverified', {'session': 'bad'}, False, 1013, 'read_gate_unavailable', 'session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'session unknown, primary', {'session': 'miss'}, False, 1013, 'read_gate_unavailable', 'session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'session unknown, standby', {'session': 'miss', 'replica': True}, False, 1013, 'read_gate_unavailable', 'session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'session lookup raised', {'session': 'error'}, False, 1013, 'read_gate_unavailable', 'session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'session lookup limited', {'session': 'limited'}, False, 1013, 'read_gate_unavailable', 'session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'operator key live', {'operator': 'valid'}, False, 1013, 'read_gate_unavailable', 'mod_no_session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'operator key unissued or revoked', {'operator': 'bad'}, False, 1013, 'read_gate_unavailable', 'mod_no_session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'operator lookup raised', {'operator': 'error'}, False, 1013, 'read_gate_unavailable', 'mod_no_session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'operator lookup limited', {'operator': 'limited'}, False, 1013, 'read_gate_unavailable', 'mod_no_session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'nothing, version header', {}, False, 1013, 'read_gate_unavailable', 'mod_no_session', 'yes', 'stage_unknown'),
    (True, 'unknown', 'nothing, no version header', {'version_present': False}, False, 1013, 'read_gate_unavailable', 'other', 'yes', 'stage_unknown'),
    (True, 'unknown', 'failed session beside a live operator key', {'session': 'bad', 'operator': 'valid'}, False, 1013, 'read_gate_unavailable', 'session', 'yes', 'stage_unknown'),
    (True, 'off', 'internal key valid', {'internal': True}, True, None, None, 'internal', 'no', None),
    (True, 'off', 'internal key wrong', {}, True, None, None, 'mod_no_session', 'no', None),
    (True, 'off', 'session valid', {'session': 'valid'}, True, None, None, 'session', 'no', None),
    (True, 'off', 'session expired or unverified', {'session': 'bad'}, True, None, None, 'session', 'no', None),
    (True, 'off', 'session unknown, primary', {'session': 'miss'}, True, None, None, 'session', 'no', None),
    (True, 'off', 'session unknown, standby', {'session': 'miss', 'replica': True}, True, None, None, 'session', 'no', None),
    (True, 'off', 'session lookup raised', {'session': 'error'}, True, None, None, 'session', 'no', None),
    (True, 'off', 'session lookup limited', {'session': 'limited'}, True, None, None, 'session', 'no', None),
    (True, 'off', 'operator key live', {'operator': 'valid'}, True, None, None, 'operator:scrmod', 'no', None),
    (True, 'off', 'operator key unissued or revoked', {'operator': 'bad'}, True, None, None, 'mod_no_session', 'no', None),
    (True, 'off', 'operator lookup raised', {'operator': 'error'}, True, None, None, 'mod_no_session', 'no', None),
    (True, 'off', 'operator lookup limited', {'operator': 'limited'}, True, None, None, 'mod_no_session', 'no', None),
    (True, 'off', 'nothing, version header', {}, True, None, None, 'mod_no_session', 'no', None),
    (True, 'off', 'nothing, no version header', {'version_present': False}, True, None, None, 'other', 'no', None),
    (True, 'off', 'failed session beside a live operator key', {'session': 'bad', 'operator': 'valid'}, True, None, None, 'session', 'no', None),
    (True, 'log', 'internal key valid', {'internal': True}, True, None, None, 'internal', 'yes', None),
    (True, 'log', 'internal key wrong', {}, True, None, None, 'mod_no_session', 'yes', None),
    (True, 'log', 'session valid', {'session': 'valid'}, True, None, None, 'session', 'yes', None),
    (True, 'log', 'session expired or unverified', {'session': 'bad'}, True, None, None, 'session', 'yes', None),
    (True, 'log', 'session unknown, primary', {'session': 'miss'}, True, None, None, 'session', 'yes', None),
    (True, 'log', 'session unknown, standby', {'session': 'miss', 'replica': True}, True, None, None, 'session', 'yes', None),
    (True, 'log', 'session lookup raised', {'session': 'error'}, True, None, None, 'session', 'yes', None),
    (True, 'log', 'session lookup limited', {'session': 'limited'}, True, None, None, 'session', 'yes', None),
    (True, 'log', 'operator key live', {'operator': 'valid'}, True, None, None, 'operator:scrmod', 'yes', None),
    (True, 'log', 'operator key unissued or revoked', {'operator': 'bad'}, True, None, None, 'mod_no_session', 'yes', None),
    (True, 'log', 'operator lookup raised', {'operator': 'error'}, True, None, None, 'mod_no_session', 'yes', None),
    (True, 'log', 'operator lookup limited', {'operator': 'limited'}, True, None, None, 'mod_no_session', 'yes', None),
    (True, 'log', 'nothing, version header', {}, True, None, None, 'mod_no_session', 'yes', None),
    (True, 'log', 'nothing, no version header', {'version_present': False}, True, None, None, 'other', 'yes', None),
    (True, 'log', 'failed session beside a live operator key', {'session': 'bad', 'operator': 'valid'}, True, None, None, 'session', 'yes', None),
    (True, 'enforce', 'internal key valid', {'internal': True}, True, None, None, 'internal', 'yes', None),
    (True, 'enforce', 'internal key wrong', {}, False, 4401, 'read_credential_required', 'mod_no_session', 'yes', 'no_credential'),
    (True, 'enforce', 'session valid', {'session': 'valid'}, True, None, None, 'session', 'yes', None),
    (True, 'enforce', 'session expired or unverified', {'session': 'bad'}, False, 4401, 'session_required', 'session', 'yes', 'bad_session'),
    (True, 'enforce', 'session unknown, primary', {'session': 'miss'}, False, 4401, 'session_required', 'session', 'yes', 'bad_session'),
    (True, 'enforce', 'session unknown, standby', {'session': 'miss', 'replica': True}, False, 1013, 'session_replication_pending', 'session', 'yes', 'replication_pending'),
    (True, 'enforce', 'session lookup raised', {'session': 'error'}, False, 1013, 'read_gate_unavailable', 'session', 'yes', 'lookup_error'),
    (True, 'enforce', 'session lookup limited', {'session': 'limited'}, False, 1013, 'rate_limited', 'session', 'yes', 'lookup_limited'),
    (True, 'enforce', 'operator key live', {'operator': 'valid'}, True, None, None, 'operator:scrmod', 'yes', None),
    (True, 'enforce', 'operator key unissued or revoked', {'operator': 'bad'}, False, 4401, 'operator_key_invalid', 'mod_no_session', 'yes', 'bad_operator_key'),
    (True, 'enforce', 'operator lookup raised', {'operator': 'error'}, False, 1013, 'read_gate_unavailable', 'mod_no_session', 'yes', 'lookup_error'),
    (True, 'enforce', 'operator lookup limited', {'operator': 'limited'}, False, 1013, 'rate_limited', 'mod_no_session', 'yes', 'lookup_limited'),
    (True, 'enforce', 'nothing, version header', {}, False, 4401, 'read_credential_required', 'mod_no_session', 'yes', 'no_credential'),
    (True, 'enforce', 'nothing, no version header', {'version_present': False}, False, 4401, 'read_credential_required', 'other', 'yes', 'no_credential'),
    (True, 'enforce', 'failed session beside a live operator key', {'session': 'bad', 'operator': 'valid'}, True, None, None, 'session', 'yes', None),
]


def _inputs(inputs):
    kw = dict(inputs)
    internal = kw.pop("internal", False)
    if kw.get("operator") == "valid":
        kw["operator_name"] = "scrmod"
    return internal, kw


# The unbuilt rows hold in EVERY stage: expand `any` to the four.
EXPANDED = [(s, row) for row in PROTOCOL for s in (STAGES if row[1] == "any" else (row[1],))]


@pytest.mark.parametrize("stage,row", EXPANDED, ids=[
    f"{'built' if r[0] else 'unbuilt'}-{s}-{r[2].replace(' ', '_').replace(',', '')}"
    for s, r in EXPANDED])
def test_protocol_row(monkeypatch, stage, row):
    built, _stage, _label, inputs, admit, code, reason, census, counted, diagnosis = row
    monkeypatch.setattr(G, "SOCKET_READ_GATE_BUILT", built)
    internal, kw = _inputs(inputs)
    want_counted = {"log/enforce": stage in ("log", "enforce"), "yes": True, "no": False}[counted]
    assert tuple(V(stage, internal, **kw)) == (admit, code, reason, census, want_counted, diagnosis)


def test_protocol_table_is_complete():
    """Every regime x every credential kind exactly once; census classes and
    refusal diagnoses each from their own vocabulary, never mixed."""
    kinds = [r[2] for r in PROTOCOL if r[0] is False]
    assert len(kinds) == len(set(kinds)) == 15
    for regime in ((False, "any"), (True, G.UNKNOWN), (True, "off"), (True, "log"), (True, "enforce")):
        assert [r[2] for r in PROTOCOL if (r[0], r[1]) == regime] == kinds, regime
    assert len(PROTOCOL) == 75
    for r in PROTOCOL:
        assert r[7] in CENSUS_CLASSES and r[7] not in DIAGNOSES, r
        assert r[9] is None or (r[9] in DIAGNOSES and r[9] not in CENSUS_CLASSES), r
        assert (r[4] is True) == (r[9] is None) == (r[5] is None), r
        if r[9] is not None:
            assert (r[5], r[6]) == G.SOCKET_CLOSE[r[9]], r


# -- built + unknown refuses before EVERY valid admission ----------------------

@pytest.mark.parametrize("valid", [{"internal": True}, {"session": "valid"},
                                   {"operator": "valid", "operator_name": "scrmod"}],
                         ids=["internal", "session", "operator"])
def test_unknown_refuses_all_three_valid_credentials(monkeypatch, valid):
    monkeypatch.setattr(G, "SOCKET_READ_GATE_BUILT", True)
    kw = dict(valid)
    internal = kw.pop("internal", False)
    v = V(G.UNKNOWN, internal, **kw)
    assert (v.admit, v.close_code, v.close_reason, v.diagnosis) == \
        (False, 1013, "read_gate_unavailable", "stage_unknown")
    assert v.census_class in CENSUS_CLASSES
    # the same credential is admitted once the stage is known
    for mode in ("off", "log", "enforce"):
        assert V(mode, internal, **kw).admit is True, mode


class _WS:
    """A handshake as socket_connect_check reads it."""

    def __init__(self, headers):
        from types import SimpleNamespace
        from starlette.datastructures import Headers
        self.headers = Headers(headers)
        self.client = None
        self.state = SimpleNamespace()
        self.url = SimpleNamespace(path=G.SOCKET_TEMPLATE)


GOOD = "socket-protocol-session-token-0123456789ab"
OP = "scrop1_" + "S" * 43


@pytest.fixture
def seam(monkeypatch):
    from datetime import timedelta
    with K.gate_env(monkeypatch, mode="enforce") as (stub, clock):
        monkeypatch.setattr(main, "_RL_BUCKETS",
                            main._RL_BUCKETS.__class__(main._RL_BUCKETS.default_factory))
        stub.add_session(GOOD, expires_at=clock.wall + timedelta(hours=1))
        stub.add_operator(OP, row_id=7, name="scrmod", slot=1)
        monkeypatch.setattr(G, "SOCKET_READ_GATE_BUILT", True)
        yield stub


@pytest.mark.parametrize("headers,census", [
    ({"x-internal-key": K.INTERNAL_KEY}, "internal"),
    ({"x-mod-version": K.LIVE_VERSION, "x-session-token": GOOD}, "session"),
    ({"x-mod-version": K.LIVE_VERSION, "x-operator-key": OP}, "operator:scrmod"),
], ids=["internal", "session", "operator"])
def test_connect_check_unknown_refuses_before_any_lookup(seam, headers, census):
    """The protocol's order, executed: under a built gate with the stage
    unknown the socket is refused with NO credential lookup; with the stage
    known the same handshake is looked up and admitted."""
    import asyncio
    v = asyncio.run(G.socket_connect_check(_WS(headers), G.UNKNOWN))
    assert (v.admit, v.close_code, v.close_reason, v.diagnosis) == \
        (False, 1013, "read_gate_unavailable", "stage_unknown")
    assert sum(seam.calls.values()) == 0, seam.calls
    v = asyncio.run(G.socket_connect_check(_WS(headers), "enforce"))
    assert (v.admit, v.census_class, v.diagnosis) == (True, census, None)


def test_connect_check_refusals_through_the_verifiers(seam):
    import asyncio
    cases = [({"x-mod-version": K.LIVE_VERSION}, (4401, "read_credential_required", "no_credential")),
             ({"x-mod-version": K.LIVE_VERSION, "x-session-token": GOOD + "x"},
              (4401, "session_required", "bad_session")),
             ({"x-mod-version": K.LIVE_VERSION, "x-operator-key": OP + "x"},
              (4401, "operator_key_invalid", "bad_operator_key"))]
    for headers, want in cases:
        v = asyncio.run(G.socket_connect_check(_WS(headers), "enforce"))
        assert (v.admit, v.close_code, v.close_reason, v.diagnosis) == (False,) + want, headers
        assert v.census_class in CENSUS_CLASSES


# -- 1. the three connect credentials ----------------------------------------

@pytest.fixture
def built(monkeypatch):
    monkeypatch.setattr(G, "SOCKET_READ_GATE_BUILT", True)


@pytest.mark.parametrize("mode", ["enforce", "log", "off"])
def test_three_connect_credentials_admit(built, mode):
    counted = mode != "off"
    assert tuple(V(mode, True)) == (True, None, None, "internal", counted, None)
    assert tuple(V(mode, False, "valid")) == (True, None, None, "session", counted, None)
    assert tuple(V(mode, False, "absent", "valid", "scrmod")) == \
        (True, None, None, "operator:scrmod", counted, None)
    # any one valid credential wins over a failed one beside it
    assert V(mode, False, "bad", "valid", "scrmod").admit is True
    assert V(mode, False, "valid", "bad").admit is True


# -- 3./4. refusal close code, reason, census class and diagnosis --------------

@pytest.mark.parametrize("session,operator,replica,version,expected", [
    ("absent", "absent", False, True, (4401, "read_credential_required", "mod_no_session", "no_credential")),
    ("absent", "absent", False, False, (4401, "read_credential_required", "other", "no_credential")),
    ("bad", "absent", False, True, (4401, "session_required", "session", "bad_session")),
    ("miss", "absent", False, True, (4401, "session_required", "session", "bad_session")),
    ("absent", "bad", False, True, (4401, "operator_key_invalid", "mod_no_session", "bad_operator_key")),
    ("error", "absent", False, True, (1013, "read_gate_unavailable", "session", "lookup_error")),
    ("absent", "error", False, True, (1013, "read_gate_unavailable", "mod_no_session", "lookup_error")),
    ("limited", "absent", False, True, (1013, "rate_limited", "session", "lookup_limited")),
    ("miss", "absent", True, True, (1013, "session_replication_pending", "session", "replication_pending")),
])
def test_enforce_refusals(built, session, operator, replica, version, expected):
    v = V("enforce", False, session, operator, replica=replica, version_present=version)
    assert not v.admit and (v.close_code, v.close_reason, v.census_class, v.diagnosis) == expected
    assert v.counted is True


def test_log_off_admit_everything(built):
    for mode in ("log", "off"):
        v = V(mode, False, "bad", "bad")
        assert (v.admit, v.close_code, v.diagnosis) == (True, None, None)
    assert G.SOCKET_REFUSE_CODE == 4401 and G.SOCKET_RETRY_CODE == 1013


# -- 6. rechecks: expiry, key, mode ------------------------------------------

def test_recheck_session_expiry_and_deletion(built):
    assert R("enforce", "session", now=99.0, session_expires_at=100.0) == (True, None, None)
    assert R("enforce", "session", now=100.0, session_expires_at=100.0) == (False, 4401, "session_expired")
    assert R("enforce", "session", now=50.0, session_expires_at=100.0,
             session_still_valid=False) == (False, 4401, "session_required")


def test_recheck_operator_key_revocation(built):
    assert R("enforce", "operator:scrmod", now=0.0) == (True, None, None)
    assert R("enforce", "operator:scrmod", now=0.0,
             operator_still_live=False) == (False, 4401, "operator_key_invalid")
    assert G.SOCKET_RECHECK_SECONDS == G.CRED_TTL == 60.0


def test_recheck_mode_change(built):
    # an unverified socket opened under log is closed when the stage becomes enforce
    assert R("log", "mod_no_session", now=0.0) == (True, None, None)
    assert R("enforce", "mod_no_session", now=0.0) == (False, 4401, "read_credential_required")
    assert R("enforce", "other", now=0.0) == (False, 4401, "read_credential_required")
    # rollback to log or off closes nothing, even an expired session
    for mode in ("log", "off"):
        assert R(mode, "session", now=200.0, session_expires_at=100.0) == (True, None, None)
        assert R(mode, "operator:scrmod", now=0.0, operator_still_live=False) == (True, None, None)
    assert R("enforce", "internal", now=0.0) == (True, None, None)
    # a built gate whose stage reads unknown closes every socket, verified or not
    for cred in ("internal", "session", "operator:scrmod", "mod_no_session"):
        assert R(G.UNKNOWN, cred, now=0.0) == (False, 1013, "read_gate_unavailable"), cred


# -- enforce cannot be selected while the socket gate is not built ------------

def test_socket_enforcement_unselectable_while_unbuilt(monkeypatch):
    assert G.SOCKET_READ_GATE_BUILT is False
    for mode in STAGES:
        assert G.socket_enforcing(mode) is False, mode
        assert G.socket_stage_refusal(mode) is None, mode
        # nothing valid presented: admitted (counted only) in every stage
        v = V(mode, False)
        assert (v.admit, v.close_code, v.diagnosis) == (True, None, None), mode
        assert R(mode, "other", now=0.0) == (True, None, None), mode
    # and the stage route refuses `enforce` for exactly this reason, even with
    # every other precondition met
    monkeypatch.setattr(G, "READ_GATE_CLIENT_MIN", "0.0.1")
    assert main._read_gate_enforce_blocker() == "socket_read_gate_absent"
    monkeypatch.setattr(G, "SOCKET_READ_GATE_BUILT", True)
    assert main._read_gate_enforce_blocker() is None
    assert G.socket_enforcing("enforce") is True


def test_count_socket_uses_the_protocol_census_class():
    """The five census classes by connect-time presence (count_socket counts
    with this function: test_read_gate_outcomes.test_ws_connect_counted_by_class
    and test_ws_connect_counted_other exercise it through real sockets)."""
    for args, want in (((True, True, "valid", "x", True), "internal"),
                       ((False, True, "valid", "x", True), "session"),
                       ((False, False, "valid", "x", True), "operator:x"),
                       ((False, False, "bad", "", True), "mod_no_session"),
                       ((False, False, "absent", "", False), "other")):
        assert G.socket_census_class(*args) == want, args
