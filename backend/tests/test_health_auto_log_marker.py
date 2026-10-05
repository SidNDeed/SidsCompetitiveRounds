"""The /health word that says this box serves the automatic log upload.

`auto_log` is the release train's acceptance signal for the automatic
post-match log upload: absent on the build production runs today, which has
no such route; auto_logs.AUTO_LOG_REVISION on this build, where POST
/api/v1/logs/auto is mounted; 0 on a build that imports the module but does
not mount the route. The train reads absent as the OLD build, the revision as
the NEW one, and anything else as neither.

The word is DERIVED from the routing table that answers requests, not written
down beside it (#342), so it is the route's own signal (#438/#443): a box that
reads the revision is a box whose app routes the upload.
"""
import inspect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

from test_player_cards_server import _run                        # noqa: E402
import auto_logs                                                 # noqa: E402
import main                                                      # noqa: E402
import schemas                                                   # noqa: E402


class _Up:
    async def execute(self, *a, **k):
        return None


class _Down:
    async def execute(self, *a, **k):
        raise OSError("database unreachable")


def _health():
    """(connected answer, degraded answer) as the response model renders them."""
    return (_run(main.health_check(db=_Up())).model_dump(),
            _run(main.health_check(db=_Down())).model_dump())


def _is_upload(r):
    return (getattr(r, "path", None) == "/api/v1/logs/auto"
            and "POST" in (getattr(r, "methods", None) or ()))


def test_the_word_reports_the_route_it_is_named_after(monkeypatch):
    """BOTH arms, and the reddening twin must differ.

    With the route mounted both arms read the revision; with the same app's
    routing table stripped of that one route both read 0. A word that read
    the revision either way would be a stamp, true on a box that does not
    serve the upload (#342).
    """
    assert auto_logs.AUTO_LOG_REVISION >= 1
    assert sum(1 for r in main.app.routes if _is_upload(r)) == 1
    mounted_up, mounted_down = _health()

    stripped = [r for r in main.app.router.routes if not _is_upload(r)]
    assert len(stripped) == len(main.app.router.routes) - 1
    monkeypatch.setattr(main.app.router, "routes", stripped)
    gone_up, gone_down = _health()

    assert (mounted_up["status"], mounted_down["status"]) == ("ok", "degraded")
    assert mounted_up["auto_log"] == auto_logs.AUTO_LOG_REVISION
    assert mounted_down["auto_log"] == auto_logs.AUTO_LOG_REVISION
    assert gone_up["auto_log"] == 0
    assert gone_down["auto_log"] == 0


def test_the_word_needs_the_real_handler_not_just_the_path(monkeypatch):
    """A different endpoint at the same path and method is not the upload."""
    import fastapi.routing as fr

    async def _other():
        return {}

    swapped = []
    for r in main.app.router.routes:
        if _is_upload(r):
            swapped.append(fr.APIRoute("/api/v1/logs/auto", _other, methods=["POST"]))
        else:
            swapped.append(r)
    monkeypatch.setattr(main.app.router, "routes", swapped)
    up, down = _health()
    assert up["auto_log"] == 0 and down["auto_log"] == 0


def test_the_word_is_declared_on_the_response_model():
    """An undeclared keyword never reaches the response; the negative control
    is a name that is not declared and must be missing from the same dump."""
    assert "auto_log" in schemas.HealthResponse.model_fields
    assert schemas.HealthResponse.model_fields["auto_log"].is_required()
    up, _ = _health()
    assert "auto_log" in up
    assert "auto_log_not_a_field" not in up
    assert "auto_log_not_a_field" not in schemas.HealthResponse.model_fields


def test_the_word_is_read_by_nothing_else_in_the_api():
    """It exists only to be probed (#306): the helper is named once for its
    definition and once per health arm, and the revision is read only by it."""
    src = inspect.getsource(main)
    assert src.count("_auto_log_health_word") == 3
    # the helper's docstring and its return statement, nothing else
    assert src.count("AUTO_LOG_REVISION") == 2
    assert inspect.getsource(auto_logs).count("AUTO_LOG_REVISION") == 1
