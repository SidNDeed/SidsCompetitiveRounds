"""POST /api/v1/queue/ready requires the caller's own valid Steam session.

Same fail-closed gate as GET /queue/poll (_strict_steam_session_ok) and the
same 401 body (detail "session_required"), placed before the first database
statement: a refused request writes no ready flag, stamps no room and answers
no room name. The soft compatibility gate (_check_steam_session) must not
stand in for it on this route. Source-shape tests in the style of
test_queue_pair_writers.py.
"""

import inspect
import re

import main


GATE = re.compile(
    r'if not await _strict_steam_session_ok\(request, steam_id, db\):\n'
    r'\s+raise HTTPException\(status_code=401, detail="session_required"\)'
)


def test_queue_ready_requires_own_session_before_any_statement():
    sig = inspect.signature(main.queue_ready)
    assert "request" in sig.parameters
    assert sig.parameters["request"].annotation is main.Request
    src = inspect.getsource(main.queue_ready)
    gate = src.index("_strict_steam_session_ok(request, steam_id, db)")
    first_stmt = src.index("await db.execute(")
    assert gate < first_stmt, "the session gate must run before the first database statement"
    assert 'raise HTTPException(status_code=401, detail="session_required")' in src[gate:first_stmt]
    # no soft-fail compatibility gate stands in for the strict one on this route
    assert "_check_steam_session(" not in src


def test_queue_ready_gate_is_the_poll_gate_exactly_once_each():
    for handler in (main.queue_poll, main.queue_ready):
        src = inspect.getsource(handler)
        assert len(GATE.findall(src)) == 1, handler.__name__
