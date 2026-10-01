"""The /health word `pc_card_art` (Discord card render parity, item 3).

3 = the renderer is up, the private art bundle validated in full and the
renderer's own self-test DREW every entry into its rect; 1 = the renderer is
up and the bundle is absent or invalid (the base face serves, nothing is
refused); 0 = the renderer cannot serve faces, or an accepted bundle failed
its proof. The release train requires 3 on every role; 1 is the value
before staging and must not pass it. Both /health arms answer it -- the word
needs no database. The field is declared WITHOUT a default, so an arm that
stops passing it fails to build its answer (the connected arm then falls to
the degraded arm, whose status says so); ai-collab's mutation runner removes
the field and each constructor argument and runs these against the result.
"""
import inspect
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))
sys.path.insert(0, HERE)

from test_player_cards_server import _run                        # noqa: E402
import card_art_fixture as fx                                    # noqa: E402
import main                                                      # noqa: E402
import pc_face                                                   # noqa: E402
import schemas                                                   # noqa: E402


class _Up:
    async def execute(self, stmt, params=None, *a, **k):
        return None

    async def rollback(self):
        return None


class _Down:
    async def execute(self, *a, **k):
        raise OSError("database unreachable")


def _health(db):
    return _run(main.health_check(db=db)).model_dump()


@pytest.fixture
def renderer_up(monkeypatch):
    """Every other condition of the face routes holds (they are the train's
    to read through their own words); this file is about the art."""
    monkeypatch.setattr(main, "_pcf", pc_face)
    monkeypatch.setattr(main, "_pc_renderer_unavailable", lambda: None)
    pc_face._card_art_selftest_at.cache_clear()
    yield
    pc_face._card_art_selftest_at.cache_clear()


def _bundle(monkeypatch, tmp_path):
    dest = tmp_path / "cards"
    fx.write_bundle(dest)
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", dest)
    return dest


def test_an_accepted_and_drawn_bundle_reads_3_on_both_arms(monkeypatch, tmp_path, renderer_up):
    _bundle(monkeypatch, tmp_path)
    up, down = _health(_Up()), _health(_Down())
    assert (up["status"], up["pc_card_art"]) == ("ok", 3)
    assert (down["status"], down["pc_card_art"]) == ("degraded", 3)


def test_an_absent_bundle_reads_1_on_both_arms(monkeypatch, tmp_path, renderer_up):
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", tmp_path / "absent")
    up, down = _health(_Up()), _health(_Down())
    assert (up["status"], up["pc_card_art"]) == ("ok", 1)
    assert (down["status"], down["pc_card_art"]) == ("degraded", 1)


def test_an_invalid_bundle_reads_1(monkeypatch, tmp_path, renderer_up):
    dest = _bundle(monkeypatch, tmp_path)
    fx.drop_entry(dest, pc_face.card_art_names()[3])
    assert _health(_Up())["pc_card_art"] == 1


def test_a_renderer_that_cannot_serve_faces_reads_0_whatever_the_bundle(monkeypatch, tmp_path, renderer_up):
    _bundle(monkeypatch, tmp_path)
    assert _health(_Up())["pc_card_art"] == 3                                   # control
    for reason in ("image_processing_unavailable", "renderer_fingerprint_unavailable",
                   "name_coverage_unavailable", "card_themes_unavailable", "text_shaping_unavailable"):
        monkeypatch.setattr(main, "_pc_renderer_unavailable", lambda r=reason: r)
        assert _health(_Up())["pc_card_art"] == 0, reason
        assert _health(_Down())["pc_card_art"] == 0, reason


def test_an_accepted_bundle_the_renderer_does_not_draw_reads_0(monkeypatch, tmp_path, renderer_up):
    """The no-op resolver: accepted, never pasted. Never 3, and never 1 (which
    the train would wait on rather than fail)."""
    _bundle(monkeypatch, tmp_path)
    monkeypatch.setattr(pc_face, "card_art_patch", lambda _n, _s: None)
    assert _health(_Up())["pc_card_art"] == 0


def test_a_self_test_that_raises_reads_0(monkeypatch, tmp_path, renderer_up):
    _bundle(monkeypatch, tmp_path)

    def boom():
        raise RuntimeError("render failed")
    monkeypatch.setattr(pc_face, "card_art_selftest", boom)
    assert _health(_Up())["pc_card_art"] == 0


def test_the_real_renderer_conditions_reach_the_word(monkeypatch, tmp_path):
    """Without the fixture's stub: whatever _pc_renderer_unavailable answers
    on this box, a reason means 0."""
    monkeypatch.setattr(main, "_pcf", None)
    assert main._pc_renderer_unavailable() == "image_processing_unavailable"
    assert _health(_Up())["pc_card_art"] == 0


def test_the_word_is_required_and_answered_by_both_arms():
    field = schemas.HealthResponse.model_fields["pc_card_art"]
    assert field.is_required() and field.annotation is int
    src = inspect.getsource(main.health_check)
    assert src.count("pc_card_art=await _pc_card_art_word()") == 2
    assert inspect.getsource(main).count("_pc_card_art_word(") == 3      # its definition and the two arms
