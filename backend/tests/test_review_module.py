"""Design report finding 1 (choice two's interface): a private module runs in
a killable child process with an empty environment. A hang, an exit, a wrong
type, an oversized reply, a wrong API, a failed self-test or a policy refusal
leaves the caller responsive (every wait bounded) and sets the module to
refused or the measure to unknown. Every module here is SYNTHETIC."""

import os
import sys
import textwrap
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import review_module as rmod  # noqa: E402

GOOD = """
api_version = 1
def measures():
    return {"module.synthetic": "a" * 64}
def selftest():
    return True
def compute(name, inputs, params):
    return len(inputs["records"]) + inputs["subject_index"]
"""


def _module(tmp_path, body):
    d = tmp_path / "mod"
    d.mkdir()
    (d / "scr_review_module.py").write_text(textwrap.dedent(body))
    return str(d)


class Ctx:
    i = 0
    records = [{"rec": {"x": 1}}, {"rec": {"x": 2}}]


def _sup(tmp_path, body, **kw):
    kw.setdefault("start_s", 10)
    kw.setdefault("call_s", 2)
    return rmod.ModuleSupervisor(_module(tmp_path, body), policy="none", **kw)


def test_a_good_module_loads_and_computes_and_its_environment_is_empty(tmp_path):
    s = _sup(tmp_path, GOOD + "\nimport os\nENV = sorted(k for k in os.environ if k != 'SYSTEMROOT')\n"
             "def compute(name, inputs, params):\n    return len(ENV)\n")
    try:
        assert s.start() == "loaded" and s.fingerprint("module.synthetic") == "a" * 64
        assert s.compute("module.synthetic", Ctx, {}) == 0
    finally:
        s.stop()


def test_a_hang_at_import_is_killed_at_the_start_deadline(tmp_path):
    s = _sup(tmp_path, "import time\ntime.sleep(60)\n" + GOOD, start_s=1)
    t = time.monotonic()
    assert s.start() == "refused" and s.reason == "timeout"
    assert time.monotonic() - t < 8
    assert s.proc is None


def test_a_hang_in_compute_makes_the_measure_unknown_and_refuses_the_module(tmp_path):
    s = _sup(tmp_path, GOOD + "\nimport time\ndef compute(name, inputs, params):\n"
                              "    time.sleep(60)\n", call_s=1)
    assert s.start() == "loaded"
    t = time.monotonic()
    assert s.compute("module.synthetic", Ctx, {}) is None
    assert time.monotonic() - t < 6
    assert s.word == "refused" and s.reason == "timeout"
    assert s.compute("module.synthetic", Ctx, {}) is None       # not restarted silently


def test_an_exit_in_compute_refuses_the_module(tmp_path):
    s = _sup(tmp_path, GOOD + "\nimport os\ndef compute(name, inputs, params):\n    os._exit(3)\n")
    assert s.start() == "loaded"
    assert s.compute("module.synthetic", Ctx, {}) is None
    assert (s.word, s.reason) == ("refused", "exit")


def test_a_wrong_type_is_unknown_and_the_module_stays_loaded(tmp_path):
    s = _sup(tmp_path, GOOD + "\ndef compute(name, inputs, params):\n    return 'seven'\n")
    try:
        assert s.start() == "loaded"
        assert s.compute("module.synthetic", Ctx, {}) is None
        assert s.word == "loaded"
    finally:
        s.stop()


def test_an_oversized_reply_refuses(tmp_path):
    s = _sup(tmp_path, GOOD + "\ndef compute(name, inputs, params):\n    return [1] * 40000\n")
    assert s.start() == "loaded"
    assert s.compute("module.synthetic", Ctx, {}) is None
    assert (s.word, s.reason) == ("refused", "reply_size")


@pytest.mark.parametrize("body,reason", [
    (GOOD.replace("api_version = 1", "api_version = 9"), "api"),
    (GOOD.replace("return True", "return False"), "selftest"),
    ("raise ImportError('synthetic')\n", "exit"),
])
def test_a_bad_module_is_refused_at_start(tmp_path, body, reason):
    s = _sup(tmp_path, body)
    assert s.start() == "refused" and s.reason == reason


def test_the_isolation_policy_refuses_where_isolation_cannot_be_shown(tmp_path):
    """On this seat (no network namespace, or not POSIX) the runner cannot show
    isolation, so the module is refused before any of its code runs."""
    marker = tmp_path / "ran"
    body = GOOD + "\nopen(%r, 'w').write('x')\n" % str(marker)
    s = rmod.ModuleSupervisor(_module(tmp_path, body), policy="isolated", start_s=10)
    assert s.start() == "refused" and s.reason == "policy"
    assert not marker.exists()
