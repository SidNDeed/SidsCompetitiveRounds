"""The /health word `pc_art_rect` (bug 408, item 4).

The art rect of the layout this box's renderer LOADED, "x0,y0,x1,y1"
(pc_face.card_art_rect, rects.badge_art_back), derived at every request and
read by nothing but the release train (#306). It tells a box on the client's
geometry ("100,651,167,745") from a box on the code before bug 408 (no key at
all) even when both draw their own bundle healthily -- pc_card_art reads 3 on
both of those and keeps meaning what it meant. Both /health arms answer it
alike (no database), on both roles alike; null when the renderer module did
not import. The field is declared WITHOUT a default, so an arm that stops
passing it fails to build its answer.
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

WORD = "100,651,167,745"


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
    monkeypatch.setattr(main, "_pcf", pc_face)
    monkeypatch.setattr(main, "_pc_renderer_unavailable", lambda: None)
    pc_face._card_art_selftest_at.cache_clear()
    pc_face._card_art_bundle_at.cache_clear()
    yield
    pc_face._card_art_selftest_at.cache_clear()
    pc_face._card_art_bundle_at.cache_clear()


def test_both_arms_answer_the_client_rect(monkeypatch, tmp_path, renderer_up):
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", tmp_path / "absent")
    up, down = _health(_Up()), _health(_Down())
    assert (up["status"], up["pc_art_rect"]) == ("ok", WORD)
    assert (down["status"], down["pc_art_rect"]) == ("degraded", WORD)


def test_the_word_is_derived_from_the_loaded_layout(monkeypatch, tmp_path, renderer_up):
    """Not a constant: the 71f30e01 rects in the loaded layout read as such."""
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", tmp_path / "absent")
    monkeypatch.setitem(pc_face.LAYOUT["rects"], "badge_art_back", list(fx.OLD_BACK))
    assert _health(_Up())["pc_art_rect"] == "92,646,172,750"
    assert _health(_Down())["pc_art_rect"] == "92,646,172,750"


def test_a_new_box_with_the_old_bundle_reads_its_rect_and_art_1(monkeypatch, tmp_path, renderer_up):
    """The mixed state a staging order can pass through: this code with the
    bundle staged before bug 408. The build word names the new rect, and the
    art word reads 1 (no art drawn), never the healthy 3."""
    dest = tmp_path / "pc-cards-old"
    fx.write_bundle_as_71f30e01(dest)
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", dest)
    up, down = _health(_Up()), _health(_Down())
    assert (up["pc_art_rect"], up["pc_card_art"]) == (WORD, 1)
    assert (down["pc_art_rect"], down["pc_card_art"]) == (WORD, 1)


def test_a_new_box_with_the_new_bundle_reads_its_rect_and_art_3(monkeypatch, tmp_path, renderer_up):
    dest = tmp_path / "pc-cards-new"
    fx.write_bundle(dest)
    monkeypatch.setattr(pc_face, "_CARD_ART_PATH", dest)
    up, down = _health(_Up()), _health(_Down())
    assert (up["pc_art_rect"], up["pc_card_art"]) == (WORD, 3)
    assert (down["pc_art_rect"], down["pc_card_art"]) == (WORD, 3)


def test_no_renderer_module_reads_null(monkeypatch):
    monkeypatch.setattr(main, "_pcf", None)
    assert _health(_Up())["pc_art_rect"] is None
    assert _health(_Down())["pc_art_rect"] is None


def test_the_word_is_required_and_answered_by_both_arms():
    field = schemas.HealthResponse.model_fields["pc_art_rect"]
    assert field.is_required()
    src = inspect.getsource(main.health_check)
    assert src.count("pc_art_rect=_pc_art_rect_word()") == 2
    assert inspect.getsource(main).count("_pc_art_rect_word(") == 3      # its definition and the two arms
