"""Choice two: a private module runs as its own compose service, reached only
through a mounted exchange (review_module.py, review_module_runner.py,
Dockerfile.review-module, the `review-module` service of
backend/docker-compose.yml).

What this file shows on any seat:
  * the service declaration IS the sandbox: no network, read-only root, no
    capabilities, no new privileges, an unprivileged user, no environment,
    exactly three mounts (module read-only, requests read-only, a tmpfs to
    answer into), and an image that carries only the runner;
  * the api side and the runner speak the exchange: a valid module loads and
    computes; absent, stale, collided, refused, hung, wrong-typed and
    oversized cases each give the word or the unknown value the design says,
    with every wait bounded;
  * the probe the sandbox proofs use: OUTSIDE the sandbox (here) it reads an
    ordinary file and opens a local connection, and exits 1. Its run INSIDE
    the running service is the positive proof; that run needs the container
    runtime, which this seat does not have (the notes record it as owed).
Every module here is SYNTHETIC."""

import json
import os
import socket
import subprocess
import sys
import textwrap
import time

import pytest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(HERE, "..", "api")
sys.path.insert(0, API)

import review_measures as rm  # noqa: E402
import review_module as rmod  # noqa: E402
import review_module_runner as runner  # noqa: E402

RUNNER = os.path.join(API, "review_module_runner.py")
COMPOSE = os.path.join(HERE, "..", "docker-compose.yml")
DOCKERFILE = os.path.join(API, "Dockerfile.review-module")

GOOD = """
api_version = 1
def measures():
    return {"module.synthetic": "a" * 64}
def compute(name, inputs, params):
    return len(inputs["records"]) + inputs["subject_index"]
"""
GOOD_CASES = [{"name": "module.synthetic", "inputs": {"records": [1, 2], "subject_index": 1},
               "params": {}, "value": 3}]


class Ctx:
    i = 0
    records = [{"rec": {"x": 1}}, {"rec": {"x": 2}}]


def _module(tmp_path, body, cases=None, seal=True):
    d = tmp_path / "mod"
    d.mkdir()
    (d / "scr_review_module.py").write_text(textwrap.dedent(body))
    (d / "selftest.json").write_text(json.dumps({"cases": GOOD_CASES if cases is None else cases}))
    if seal:
        files = {n: (d / n).read_bytes() for n in ("scr_review_module.py", "selftest.json")}
        (d / "REVISION").write_text(runner.module_digest(files) + "\n")
    return str(d)


def _exchange(tmp_path):
    root = tmp_path / "xch"
    (root / "in").mkdir(parents=True)
    (root / "out").mkdir()
    return str(root)


class _Service:
    """The runner as its own process over a module dir and an exchange, as the
    compose service runs it (python -I, nothing inherited but the path)."""

    def __init__(self, tmp_path, body, cases=None, seal=True):
        self.root = _exchange(tmp_path)
        mod = _module(tmp_path, body, cases, seal)
        env = {"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")} if os.name == "nt" else {}
        self.proc = subprocess.Popen(
            [sys.executable, "-I", RUNNER, "serve", mod, os.path.join(self.root, "in"),
             os.path.join(self.root, "out")], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def wait_status(self, deadline_s=15):
        end = time.monotonic() + deadline_s
        path = os.path.join(self.root, "out", rmod.STATUS)
        while time.monotonic() < end:
            if os.path.exists(path):
                return
            time.sleep(0.05)
        raise AssertionError("no status within the bound")

    def stop(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(timeout=10)


@pytest.fixture
def service(tmp_path):
    made = []

    def make(body=GOOD, cases=None, seal=True):
        s = _Service(tmp_path, body, cases, seal)
        made.append(s)
        s.wait_status()
        return s
    yield make
    for s in made:
        s.stop()


# -- the service declaration is the sandbox --------------------------------

def _compose():
    with open(COMPOSE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def sandbox_violations(doc, dockerfile_text):
    """Every way the declaration falls short of the sandbox, as short names
    (an empty list means the declaration holds)."""
    out = []
    svc = doc.get("services", {}).get("review-module") or {}
    if svc.get("network_mode") != "none":
        out.append("network")
    if svc.get("read_only") is not True:
        out.append("read_only")
    if svc.get("user") != "65534:65534":
        out.append("user")
    if svc.get("cap_drop") != ["ALL"]:
        out.append("cap_drop")
    if "no-new-privileges:true" not in (svc.get("security_opt") or []):
        out.append("no_new_privileges")
    for key in ("environment", "env_file", "ports", "networks", "devices", "privileged",
                "volumes_from", "cap_add", "pid", "ipc"):
        if key in svc:
            out.append("extra:" + key)
    if svc.get("profiles") != ["review-module"]:
        out.append("profile")
    vols = svc.get("volumes") or []
    targets = {}
    for v in vols:
        parts = v.split(":")
        mode = parts[-1] if parts[-1] in ("ro", "rw") else "rw"
        target = parts[-2] if parts[-1] in ("ro", "rw") else parts[-1]
        targets[target] = (parts[0], mode)
    want = {"/module": "ro", "/exchange/in": "ro", "/exchange/out": "rw"}
    if set(targets) != set(want) or any(targets[t][1] != m for t, m in want.items()):
        out.append("mounts")
    top = doc.get("volumes") or {}
    for t in ("/exchange/in", "/exchange/out"):
        name = targets.get(t, ("",))[0]
        opts = (top.get(name) or {}).get("driver_opts") or {}
        if opts.get("type") != "tmpfs":
            out.append("tmpfs:" + t)
    tmpfs = svc.get("tmpfs") or []
    if any(not str(x).startswith("/tmp") for x in tmpfs):
        out.append("tmpfs_extra")
    api_vols = (doc.get("services", {}).get("api") or {}).get("volumes") or []
    exchange = [v for v in api_vols if v.split(":")[0] in (targets.get("/exchange/in", ("",))[0],
                                                           targets.get("/exchange/out", ("",))[0])]
    if len(exchange) != 2:
        out.append("api_exchange")
    module_src = targets.get("/module", ("",))[0]
    if any(v.split(":")[0] == module_src for v in api_vols):
        out.append("api_module")
    copies = [ln for ln in dockerfile_text.splitlines() if ln.strip().upper().startswith(("COPY", "ADD"))]
    if copies != ["COPY review_module_runner.py /runner/review_module_runner.py"]:
        out.append("image")
    if "USER 65534:65534" not in dockerfile_text:
        out.append("image_user")
    return out


def _dockerfile():
    with open(DOCKERFILE, encoding="utf-8") as f:
        return f.read()


def test_the_service_declaration_is_the_sandbox():
    assert sandbox_violations(_compose(), _dockerfile()) == []


@pytest.mark.parametrize("edit,name", [
    (lambda d: d["services"]["review-module"].pop("network_mode"), "network"),
    (lambda d: d["services"]["review-module"].__setitem__("read_only", False), "read_only"),
    (lambda d: d["services"]["review-module"]["volumes"].append("/opt:/host:ro"), "mounts"),
    (lambda d: d["services"]["review-module"].__setitem__("environment", {"X": "1"}), "extra:environment"),
    (lambda d: d["volumes"]["review-module-out"].pop("driver_opts"), "tmpfs:/exchange/out"),
    (lambda d: d["services"]["api"]["volumes"].append(
        "${SCR_REVIEW_MODULE_DIR:-/opt/competitive-rounds/private/review-module/current}:/m:ro"),
     "api_module"),
])
def test_each_sandbox_property_is_load_bearing(edit, name):
    """Negative controls: one property removed is named, and only it."""
    doc = _compose()
    edit(doc)
    assert sandbox_violations(doc, _dockerfile()) == [name]


def test_the_image_carries_only_the_runner():
    assert sandbox_violations(_compose(), _dockerfile() + "\nCOPY . /app\n") == ["image"]


# -- the probe, outside the sandbox (the negative control) -----------------

def test_outside_the_sandbox_the_probe_reads_the_file_and_reaches_the_network(tmp_path):
    f = tmp_path / "undeclared"
    f.write_text("x")
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        p = subprocess.run([sys.executable, "-I", RUNNER, "probe", str(f), "127.0.0.1",
                            str(srv.getsockname()[1])], capture_output=True, text=True, timeout=30)
    finally:
        srv.close()
    assert p.returncode == 1
    assert json.loads(p.stdout) == {"network": "open", "undeclared_read": "read"}


def test_the_probe_holds_only_when_both_attempts_are_refused(tmp_path):
    """The probe's verdict logic: a missing file and a closed port both count
    as refused, so exit 0; either one open is exit 1."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    p = subprocess.run([sys.executable, "-I", RUNNER, "probe", str(tmp_path / "none"),
                        "127.0.0.1", str(port)], capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stdout
    out = json.loads(p.stdout)
    assert out["undeclared_read"].startswith("refused:") and out["network"].startswith("refused:")


# -- the exchange ------------------------------------------------------------

def test_no_status_is_absent_and_no_module_is_used(tmp_path, monkeypatch):
    monkeypatch.setenv(rmod.EXCHANGE_ENV, _exchange(tmp_path))
    assert rmod.health_word() == "absent"
    assert rmod.current_module() is None


def test_a_valid_module_loads_and_computes_through_the_exchange(service, monkeypatch):
    s = service()
    monkeypatch.setenv(rmod.EXCHANGE_ENV, s.root)
    word = rmod.health_word()
    assert len(word) == 12 and word not in ("absent", "refused")
    m = rmod.current_module()
    assert m.fingerprint("module.synthetic") == "a" * 64
    assert m.compute("module.synthetic", Ctx, {}) == 2
    assert os.listdir(os.path.join(s.root, "in")) == []
    assert sorted(os.listdir(os.path.join(s.root, "out"))) == [rmod.STATUS]


def test_a_stale_heartbeat_is_refused(service, monkeypatch):
    s = service()
    s.stop()
    m = rmod.ExchangeModule(s.root, stale_s=0)
    time.sleep(0.05)
    assert m.status()[:2] == ("refused", "stale")


@pytest.mark.parametrize("body,cases,seal,reason", [
    (GOOD, None, False, "runner:digest"),
    (GOOD.replace("api_version = 1", "api_version = 9"), None, True, "runner:api"),
    (GOOD, [dict(GOOD_CASES[0], value=4)], True, "runner:selftest"),
    ("raise ImportError('synthetic')\n", None, True, "runner:import"),
])
def test_a_bad_module_is_refused_by_the_runner(service, body, cases, seal, reason):
    s = service(body, cases, seal)
    assert rmod.ExchangeModule(s.root).status()[:2] == ("refused", reason)


def test_a_measure_that_collides_with_the_public_vocabulary_is_refused(service):
    public = sorted(rm.REGISTRY)[0]
    s = service(GOOD.replace('"module.synthetic"', repr(public)),
                [dict(GOOD_CASES[0], name=public)])
    assert rmod.ExchangeModule(s.root).status()[:2] == ("refused", "collision")


def test_a_hang_in_compute_is_unknown_within_the_bound_and_refuses_for_good(service):
    s = service(GOOD + "\nimport time\n_n = [0]\ndef compute(name, inputs, params):\n"
                       "    _n[0] += 1\n    if _n[0] > 1:\n        time.sleep(60)\n"
                       "    return len(inputs['records']) + inputs['subject_index']\n")
    m = rmod.ExchangeModule(s.root, call_s=1)
    t = time.monotonic()
    assert m.compute("module.synthetic", Ctx, {}) is None
    assert time.monotonic() - t < 5
    assert m.status()[:2] == ("refused", "timeout")
    assert m.compute("module.synthetic", Ctx, {}) is None     # never retried silently
    s.proc.wait(timeout=15)                                     # the runner leaves over budget
    assert s.proc.returncode != 0


def test_a_wrong_type_is_unknown_and_the_module_stays_loaded(service):
    s = service(GOOD + "\n_n = [0]\ndef compute(name, inputs, params):\n    _n[0] += 1\n"
                       "    return 3 if _n[0] == 1 else 'seven'\n")
    m = rmod.ExchangeModule(s.root)
    assert m.compute("module.synthetic", Ctx, {}) is None
    assert m.word() not in ("absent", "refused")


def test_an_oversized_reply_is_unknown(service):
    s = service(GOOD + "\n_n = [0]\ndef compute(name, inputs, params):\n    _n[0] += 1\n"
                       "    return 3 if _n[0] == 1 else [1] * 40000\n")
    m = rmod.ExchangeModule(s.root)
    assert m.compute("module.synthetic", Ctx, {}) is None


def test_the_refusal_class_goes_to_the_log_once_and_never_to_the_word(service, monkeypatch, capsys):
    s = service(GOOD, None, False)
    monkeypatch.setenv(rmod.EXCHANGE_ENV, s.root)
    monkeypatch.setattr(rmod, "_LOGGED", None)
    assert rmod.health_word() == "refused"
    assert rmod.health_word() == "refused"
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("[REVIEW] module")]
    assert lines == ["[REVIEW] module: refused (runner:digest)"]


def test_no_isolation_self_check_remains_in_the_tree():
    """The interface-only isolation (a process inspecting its own uid,
    interfaces and environment) is gone: the boundary is the service."""
    for name in ("review_module.py", "review_module_runner.py"):
        with open(os.path.join(API, name), encoding="utf-8") as f:
            src = f.read()
        for gone in ("_isolated", "/sys/class/net", "getuid", "ModuleSupervisor"):
            assert gone not in src, (name, gone)
