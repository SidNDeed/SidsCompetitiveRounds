"""Choice two (designed, NOT built): the interface for a private module that
ADDS measures. It never decides: every review item is still a rule in the
rules revision, so wording, arming and values keep one home.

The api never imports a private module. A module runs in its own killable
process (review_module_runner.py), started and supervised from here:

  * isolation the runner proves BEFORE it imports anything of the module, or
    it refuses: it is not root, it sees no network interface but loopback,
    and its environment is empty (the supervisor passes none, so no database
    address or credential reaches it). On a platform where this cannot be
    shown the module is refused. Deployment supplies the isolation (a
    sibling container with networking disabled, or a network namespace)
    and stages the module directory read-only, like a rules revision;
  * inputs are copies sent over the child's stdin as JSON lines; replies are
    single bounded JSON lines on its stdout; nothing else is shared;
  * deadlines: import, handshake and the module's own self-test share one
    start deadline; each computation has its own. A timeout, an exit, an
    oversized or malformed reply, a wrong API version, a policy refusal or a
    failed self-test kills the child and refuses the module at start; during
    a computation the measure is unknown and the module is refused for the
    rest of the process (it is not restarted silently).

A refused or absent module makes every module measure unknown, so a rule that
needs one never fires and every other rule runs. The api stays responsive in
every case: every wait is bounded and the child is killed, never awaited
unbounded.

Protocol (MODULE_API):
  {"call": "hello"}     -> {"api": <int>, "measures": {name: fingerprint}}
  {"call": "selftest"}  -> {"ok": <bool>}
  {"call": "compute", "name": n, "inputs": {...}, "params": {...}}
                        -> {"value": <number | list of numbers | null>}
"""

from __future__ import annotations

import json
import math
import os
import queue
import subprocess
import sys
import threading

CONTRACT_BOUNDS = {
    "api": 1,
    "start_s": 20,
    "call_s": 2,
    "line_bytes_max": 65536,
    "nobody_uid": 65534,
    "reason_max": 32,
}
MODULE_API = CONTRACT_BOUNDS["api"]
RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review_module_runner.py")


class ModuleRefused(Exception):
    def __init__(self, cls):
        super().__init__(cls)
        self.cls = cls


def _drop_privileges():                      # runs in the child before exec (POSIX only)
    uid = CONTRACT_BOUNDS["nobody_uid"]
    os.setgroups([])
    os.setgid(uid)
    os.setuid(uid)


def _value_ok(v) -> bool:
    if v is None:
        return True
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return math.isfinite(v)
    if isinstance(v, list):
        return all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
                   for x in v)
    return False


class ModuleSupervisor:
    """One module process. `policy` is "isolated" in production; a test may
    pass "none" to exercise the deadlines on a seat that cannot show
    isolation (the runner then skips only the isolation probe)."""

    def __init__(self, module_dir, *, policy="isolated", start_s=None, call_s=None):
        self.module_dir = module_dir
        self.policy = policy
        self.start_s = CONTRACT_BOUNDS["start_s"] if start_s is None else start_s
        self.call_s = CONTRACT_BOUNDS["call_s"] if call_s is None else call_s
        self.proc = None
        self.lines = queue.Queue()
        self.word = "absent"
        self.reason = None
        self.measures = {}

    # -- process plumbing --
    def _spawn(self):
        env = {}
        if os.name == "nt":                     # the interpreter cannot start without it there
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        kw = {}
        if os.name == "posix" and self.policy == "isolated" and os.geteuid() == 0:
            kw["preexec_fn"] = _drop_privileges
        self.proc = subprocess.Popen(
            [sys.executable, "-I", RUNNER, self.module_dir, self.policy],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, cwd=self.module_dir, **kw)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def _read(self, proc):
        limit = CONTRACT_BOUNDS["line_bytes_max"]
        try:
            while True:
                line = proc.stdout.readline(limit + 1)
                if not line:
                    break
                self.lines.put(line)
        finally:
            self.lines.put(None)

    def _kill(self):
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.wait(timeout=self.call_s)
            except Exception:                   # noqa: BLE001 -- best effort; the process is gone or going
                pass
            self.proc = None

    def _call(self, msg, timeout):
        try:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode())
            self.proc.stdin.flush()
        except OSError:
            raise ModuleRefused("exit")
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty:
            raise ModuleRefused("timeout")
        if line is None:
            raise ModuleRefused("exit")
        if len(line) > CONTRACT_BOUNDS["line_bytes_max"] or not line.endswith(b"\n"):
            raise ModuleRefused("reply_size")
        try:
            reply = json.loads(line)
        except ValueError:
            raise ModuleRefused("reply")
        if not isinstance(reply, dict):
            raise ModuleRefused("reply")
        if "error" in reply:
            raise ModuleRefused(str(reply["error"])[: CONTRACT_BOUNDS["reason_max"]] or "error")
        return reply

    # -- public --
    def start(self) -> str:
        """Start, handshake and self-test inside the start deadline. Returns
        the module word: "loaded" or "refused" (reason in .reason)."""
        try:
            self._spawn()
            hello = self._call({"call": "hello"}, self.start_s)
            if hello.get("api") != MODULE_API or not isinstance(hello.get("measures"), dict):
                raise ModuleRefused("api")
            ok = self._call({"call": "selftest"}, self.start_s)
            if ok.get("ok") is not True:
                raise ModuleRefused("selftest")
            self.measures = {str(k): str(v) for k, v in hello["measures"].items()}
            self.word = "loaded"
        except ModuleRefused as e:
            self._kill()
            self.word, self.reason = "refused", e.cls
        except OSError:
            self._kill()
            self.word, self.reason = "refused", "spawn"
        return self.word

    def fingerprint(self, name):
        return self.measures.get(name) if self.word == "loaded" else None

    def compute(self, name, ctx, params):
        """One module measure for one subject, or None (unknown)."""
        if self.word != "loaded":
            return None
        inputs = {"subject_index": ctx.i, "records": [r["rec"] for r in ctx.records]}
        try:
            reply = self._call({"call": "compute", "name": name, "inputs": inputs,
                                "params": params}, self.call_s)
            v = reply.get("value")
            if not _value_ok(v):
                return None
            return v
        except ModuleRefused as e:
            self._kill()
            self.word, self.reason = "refused", e.cls
            return None

    def stop(self):
        self._kill()
