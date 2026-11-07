"""The admin evidence report phase 2 landing's build discriminator: /health
carries `admin_report_p2_build`, derived on every request from the presence of
the phase 2 evidence sections (main._admin_report_p2_build_health_word), on
both health_check arms, required by the schema. Phase 2 adds no route and the
report routes answer 403 before routing on every build, so the release train
tells a refreshed box from a stale one by this key (learning 794). The form is
the phase 1a word's (test_admin_evidence_health_word.py)."""
import asyncio
import inspect

import pydantic
import pytest

import admin_evidence
import main
import schemas


class _DownSession:
    """A session whose server is gone: every statement raises."""

    async def execute(self, *a, **k):
        raise OSError("admin_report_p2_build: the database is down")

    async def rollback(self):
        pass


def test_the_health_word_is_derived_from_the_phase_2_sections(monkeypatch):
    assert main._admin_report_p2_build_health_word() == 1
    monkeypatch.delattr(admin_evidence, "read_sections")
    assert main._admin_report_p2_build_health_word() == 0


def test_the_health_route_answers_the_word_on_both_arms():
    src = inspect.getsource(main.health_check)
    assert src.count("admin_report_p2_build=_admin_report_p2_build_health_word()") == 2
    field = schemas.HealthResponse.model_fields.get("admin_report_p2_build")
    assert field is not None and field.annotation is int and field.is_required(), field
    answer = asyncio.run(main.health_check(db=_DownSession())).model_dump()
    assert answer["status"] == "degraded" and answer["admin_report_p2_build"] == 1, answer
    answer.pop("admin_report_p2_build")
    with pytest.raises(pydantic.ValidationError):
        schemas.HealthResponse(**answer)
