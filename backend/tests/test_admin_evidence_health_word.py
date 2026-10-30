"""The admin evidence report landing's build discriminator: /health carries
`admin_evidence`, derived on every request from the four report routes'
registration (main._admin_evidence_health_word), on both health_check arms,
required by the schema. The routes themselves cannot be probed for presence:
the internal prefix answers 403 before routing on every build, so a probe of
GET /api/v1/internal/evidence-report/pair reads the same on a build without
the lane. The form is the combat lane's (test_combat_evidence_unit.py)."""
import inspect

import admin_evidence
import main
import schemas


def test_the_health_word_is_derived_from_the_routes(monkeypatch):
    assert main._admin_evidence_health_word() == 1
    kept = [r for r in main.app.router.routes
            if getattr(r, "endpoint", None) is not admin_evidence.evidence_report_pair]
    monkeypatch.setattr(main.app.router, "routes", kept)
    assert main._admin_evidence_health_word() == 0


def test_the_health_answer_carries_the_word_on_both_arms():
    src = inspect.getsource(main.health_check)
    assert src.count("admin_evidence=_admin_evidence_health_word()") == 2
    assert schemas.HealthResponse.model_fields["admin_evidence"].is_required()


def test_all_four_report_routes_are_registered():
    registered = {id(getattr(r, "endpoint", None)) for r in main.app.routes}
    assert len(main._ADMIN_EVIDENCE_ROUTES) == 4
    assert {fn.__name__ for fn in main._ADMIN_EVIDENCE_ROUTES} == {
        "evidence_report_game", "evidence_report_series",
        "evidence_report_pair", "evidence_report_player"}
    assert all(id(fn) in registered for fn in main._ADMIN_EVIDENCE_ROUTES)
