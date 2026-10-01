"""Verified reads, requirement 26 / finding M4: the chat socket's read-side
protocol, tested here as executable decisions (read_gate.socket_connect_verdict,
read_gate.socket_recheck_verdict, read_gate.socket_enforcing; the same text
stands in read_gate above socket_connect_verdict). The socket gate is NOT
built: SOCKET_READ_GATE_BUILT stays False, and the last tests prove that no
stage selects socket enforcement while it is.

The protocol the socket read gate must implement before that constant may
become True:

1. Connect credentials, read from the handshake headers only (the
   message-borne `auth` frame binds the inbound identity and is not a read
   credential). Exactly the three of the HTTP gate, any one valid admits:
     X-Internal-Key  equal to API_SECRET_KEY                   -> internal
     X-Session-Token whose row exists, is verified, unexpired  -> session
     X-Operator-Key  naming a live api_operator_keys row        -> operator:<name>
2. The check runs after the version check and accept(), before the socket
   joins the chat manager and before the first outbound frame, so a refused
   socket receives no chat frame.
3. Refusal closes the socket with an application close code and the HTTP
   gate's own detail word as the reason:
     4401 read_credential_required     nothing valid was presented
     4401 session_required             a session token was presented and failed
     4401 operator_key_invalid         an operator key was presented and failed
     1013 read_gate_unavailable        a lookup raised, or the stage is unknown
     1013 session_replication_pending  the standby has no row for the token
4. Rechecks while open, every SOCKET_RECHECK_SECONDS (= CRED_TTL, 60 s), and
   the stage every MODE_TTL (15 s):
     session expiry   closed 4401 session_expired at the row's expires_at
     session deleted  closed 4401 session_required
     key revoked      closed 4401 operator_key_invalid
     stage -> enforce an open socket with no valid credential is closed
                      4401 read_credential_required
     stage -> log/off nothing is closed
5. Counting is unchanged: each socket is counted once at connect by its
   class (internal, session, operator:<name>, mod_no_session, other); the
   `other` class (no version header) is tested in
   test_read_gate_outcomes.test_ws_connect_counted_other.

The protocol tests run with the constant raised inside the test only
(monkeypatch), which is what the future implementation will run under.
"""
from __future__ import annotations

import pytest

import read_gate_testkit as K   # noqa: F401  (puts backend/api on sys.path)
import main
import read_gate as G

V = G.socket_connect_verdict
R = G.socket_recheck_verdict


@pytest.fixture
def built(monkeypatch):
    monkeypatch.setattr(G, "SOCKET_READ_GATE_BUILT", True)


# -- 1. the three connect credentials ----------------------------------------

@pytest.mark.parametrize("mode", ["enforce", "log", "off"])
def test_three_connect_credentials_admit(built, mode):
    assert V(mode, True, "absent", "absent") == (True, None, None, "internal")
    assert V(mode, False, "valid", "absent") == (True, None, None, "session")
    assert V(mode, False, "absent", "valid", "scrmod") == (True, None, None, "operator:scrmod")
    # any one valid credential wins over a failed one beside it
    assert V(mode, False, "bad", "valid", "scrmod")[0] is True
    assert V(mode, False, "valid", "bad")[0] is True


# -- 3. refusal close code and reason ----------------------------------------

@pytest.mark.parametrize("session,operator,replica,version,expected", [
    ("absent", "absent", False, True, (4401, "read_credential_required", "mod_no_session")),
    ("absent", "absent", False, False, (4401, "read_credential_required", "other")),
    ("bad", "absent", False, True, (4401, "session_required", "bad_session")),
    ("miss", "absent", False, True, (4401, "session_required", "bad_session")),
    ("absent", "bad", False, True, (4401, "operator_key_invalid", "bad_operator_key")),
    ("error", "absent", False, True, (1013, "read_gate_unavailable", "lookup_error")),
    ("absent", "error", False, True, (1013, "read_gate_unavailable", "lookup_error")),
    ("miss", "absent", True, True, (1013, "session_replication_pending", "replication_pending")),
])
def test_enforce_refusals(built, session, operator, replica, version, expected):
    admit, code, reason, cls = V("enforce", False, session, operator, replica=replica,
                                 version_present=version)
    assert not admit and (code, reason, cls) == expected


def test_unknown_stage_retries_and_log_off_admit(built):
    assert V(G.UNKNOWN, False, "absent", "absent")[:3] == (False, 1013, "read_gate_unavailable")
    for mode in ("log", "off"):
        assert V(mode, False, "bad", "bad")[:3] == (True, None, None)
    assert G.SOCKET_REFUSE_CODE == 4401 and G.SOCKET_RETRY_CODE == 1013


# -- 4. rechecks: expiry, key, mode ------------------------------------------

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


# -- enforce cannot be selected while the socket gate is not built ------------

def test_socket_enforcement_unselectable_while_unbuilt(monkeypatch):
    assert G.SOCKET_READ_GATE_BUILT is False
    for mode in ("off", "log", "enforce", G.UNKNOWN):
        assert G.socket_enforcing(mode) is False, mode
        # nothing valid presented: admitted (counted only) in every stage
        assert V(mode, False, "absent", "absent")[:3] == (True, None, None), mode
        assert R(mode, "other", now=0.0) == (True, None, None), mode
    # and the stage route refuses `enforce` for exactly this reason, even with
    # every other precondition met
    monkeypatch.setattr(G, "READ_GATE_CLIENT_MIN", "0.0.1")
    assert main._read_gate_enforce_blocker() == "socket_read_gate_absent"
    monkeypatch.setattr(G, "SOCKET_READ_GATE_BUILT", True)
    assert main._read_gate_enforce_blocker() is None
    assert G.socket_enforcing("enforce") is True
