"""The /health word that says this build loaded the card ink map.

This batch adds no route and no new unauthenticated field anywhere else, so
`pc_card_themes` is the release train's whole build discriminator for it: the
key is absent on the build running in production today, `ready` on this build
with migration 333 applied, and `empty` on this build against a database whose
333 has not run. The train reads absent as the OLD build, the expected value
as the NEW one and anything else as neither -- so `empty` stops the train
rather than passing it, which is the point of having three states.

The marker is the FEATURE'S OWN signal and not a version stamp (#438/#443):
the map is read once at startup from the table 333 creates, and the face routes
refuse while it is empty. A stamp would say the code shipped; this says the
code shipped and its data arrived.
"""
import inspect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))

from test_player_cards_server import _run                        # noqa: E402
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


def test_the_health_word_reports_the_map_it_is_named_after(monkeypatch):
    """BOTH arms, and they must differ.

    A word that read `ready` whichever way the map went would be a stamp: it
    would pass on a box whose 333 never ran, which is the one deploy failure
    this marker exists to catch (#342 -- a check that cannot fail is worse
    than none). So the reddening arm is an EMPTY map and the inert twin is a
    populated one, and the two readings are asserted to be different values.
    """
    monkeypatch.setattr(main, "_PC_CARD_THEMES", {"Poison": (1, 2, 3)})
    loaded_up, loaded_down = _health()

    monkeypatch.setattr(main, "_PC_CARD_THEMES", {})
    empty_up, empty_down = _health()

    assert loaded_up["pc_card_themes"] == "ready"
    assert empty_up["pc_card_themes"] == "empty"
    assert loaded_up["pc_card_themes"] != empty_up["pc_card_themes"]

    # The degraded answer carries it too: "which build is this box" is exactly
    # the question being asked when the database is unreachable, and the map is
    # a process-local read that needs no database to answer.
    assert (loaded_up["status"], loaded_down["status"]) == ("ok", "degraded")
    assert loaded_down["pc_card_themes"] == "ready"
    assert empty_down["pc_card_themes"] == "empty"


def test_the_word_is_declared_on_the_response_model():
    """An undeclared keyword never reaches the response.

    `HealthResponse` drops what it does not declare, so passing the word from
    the handler is not by itself enough for a probe to see it. The negative
    control is a name that is NOT declared: it must be missing from the same
    dump, or "the key is present" would prove nothing about the declaration.
    """
    assert "pc_card_themes" in schemas.HealthResponse.model_fields
    up, _ = _health()
    assert "pc_card_themes" in up
    assert "pc_card_themes_not_a_field" not in up
    assert "pc_card_themes_not_a_field" not in schemas.HealthResponse.model_fields


def test_the_word_is_read_by_nothing_else_in_the_api():
    """It exists only to be probed (#306).

    A marker that some other code path also consumes stops being a free
    signal: changing it then means changing behaviour, and the next person to
    need a different word leaves the probe reading a stale one. `main` may
    mention the helper exactly twice -- its definition and the two calls in the
    two health branches -- and nothing may read the WORD itself.
    """
    src = inspect.getsource(main)
    assert src.count("_pc_card_themes_word") == 3
    assert src.count('"ready" if _PC_CARD_THEMES else "empty"') == 1
    # The literal words appear nowhere else in the api: a second producer would
    # mean two places deciding what the probe reads.
    assert src.count('== "ready"') == 0
