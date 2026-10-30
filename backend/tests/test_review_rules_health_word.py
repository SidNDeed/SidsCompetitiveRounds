"""The public /health `review_rules` word (small docket item b).

Required behaviour: /health reports whether a private review rules revision is
loaded and, when one is, which one -- the loader's state word and nothing
about the revision's contents:

  * the revision's id when a staged revision passed every check (present),
  * `absent` when none is staged, which is the answer on every machine
    without the private rules (this seat included),
  * `refused` when the staged revision failed a check.

Both constructors of health_check carry the word, so a degraded answer reports
it too, and reading it cannot fail the route: review_rules.health_word()
returns the state the loader's last refresh published, with no I/O.

The word has been on /health since the seat evidence server landed
(47669b66); until this file nothing held the ROUTE to it. The loader's own
transitions are test_review_rules.py's. Here: the schema requires the word,
each arm passes it once and passes the loader's word, and the executed route
answers absent, a loaded revision's id and refused on both arms. The form is
test_admin_evidence_health_word.py's and test_health_read_gate_marker.py's
(whose session fakes this file reuses).
"""
import ast
import os
import pathlib
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "api")))
sys.path.insert(0, HERE)

from test_player_cards_server import _run                        # noqa: E402
from test_health_read_gate_marker import _Down, _Up              # noqa: E402
import main                                                      # noqa: E402
import review_rules as rr                                        # noqa: E402
import review_testkit as tk                                      # noqa: E402
import schemas                                                   # noqa: E402

MAIN_PY = pathlib.Path(main.__file__).resolve()
WORD = "review_rules"


@pytest.fixture
def fresh(monkeypatch, tmp_path):
    """A clean loader state and an empty review root (test_review_rules.py)."""
    monkeypatch.setattr(rr, "_STATE", rr.State("absent"))
    monkeypatch.setattr(rr, "_KEY", None)
    monkeypatch.setattr(rr, "_LOGGED", None)
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv(rr.ROOT_ENV, str(root))
    return root


def _both_arms():
    up = _run(main.health_check(db=_Up(None))).model_dump()
    down = _run(main.health_check(db=_Down())).model_dump()
    assert (up["status"], down["status"]) == ("ok", "degraded"), (up["status"], down["status"])
    return up[WORD], down[WORD]


def test_the_schema_requires_the_word():
    field = schemas.HealthResponse.model_fields[WORD]
    assert field.is_required() and field.annotation is str


def test_each_arm_passes_the_loaders_word_once():
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    health = [n for n in tree.body
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "health_check"]
    assert len(health) == 1
    tries = [n for n in ast.walk(health[0]) if isinstance(n, ast.Try)]
    assert len(tries) == 1
    ok_arm = {id(n) for s in tries[0].body for n in ast.walk(s)}
    degraded = {id(n) for h in tries[0].handlers for n in ast.walk(h)}
    kws = [k for k in ast.walk(health[0]) if isinstance(k, ast.keyword) and k.arg == WORD]
    assert len(kws) == 2, len(kws)
    assert sum(id(k) in ok_arm for k in kws) == 1 and sum(id(k) in degraded for k in kws) == 1
    # the value is the loader's word, read at request time, on both arms
    assert all(ast.unparse(k.value) == "_review_rules.health_word()" for k in kws), \
        [ast.unparse(k.value) for k in kws]
    assert main._review_rules is rr


def test_without_a_private_revision_both_arms_answer_absent(fresh, monkeypatch, tmp_path):
    assert rr.refresh_rules().word == "absent"
    assert _both_arms() == ("absent", "absent")
    # a review root that does not exist at all reads the same
    monkeypatch.setenv(rr.ROOT_ENV, str(tmp_path / "no-such-root"))
    assert rr.refresh_rules().word == "absent"
    assert _both_arms() == ("absent", "absent")


def test_a_loaded_revision_is_reported_by_its_id_on_both_arms(fresh, tmp_path):
    store, rev = tk.build_revision(tmp_path)
    rdir = os.path.join(store, "rules-" + rev)
    shutil.copytree(rdir, os.path.join(str(fresh), os.path.basename(rdir)))
    tk.point(fresh, "rules-" + rev)
    assert rr.refresh_rules().word == rev
    assert _both_arms() == (rev, rev)
    assert rev not in ("absent", "refused") and len(rev) == rr.CONTRACT_BOUNDS["rev_hex"]


def test_a_refused_revision_reads_refused_on_both_arms(fresh):
    tk.point(fresh, "rules-" + "0" * rr.CONTRACT_BOUNDS["rev_hex"])
    assert rr.refresh_rules().word == "refused"
    assert _both_arms() == ("refused", "refused")
