"""The review module runner: the ONLY program in the `review-module` service
image (backend/api/Dockerfile.review-module). Standard library only; no api
code is in that image.

The boundary is the service, not this program: the compose service gives it
no network, a read-only root filesystem, no capabilities, no new privileges,
an unprivileged user, no environment, and exactly three mounts (the module
revision read-only, the request exchange read-only, a tmpfs to answer into).
This program checks nothing about its own isolation; the `probe` mode below
exists only so a run INSIDE the service can show that boundary (and the same
run outside it shows the opposite).

  serve <module dir> <in dir> <out dir>
      Validate the module once: the framed digest of every file of the module
      directory against its REVISION file, `scr_review_module.api_version`,
      `measures()` (names and fp_hex-character fingerprints), and every case of the
      module's selftest.json (inputs, params, expected value). Then publish
      out/status.json (word = the revision id or `refused`, the reason class,
      the measures, a heartbeat) and answer each in/<id>.req with
      out/<id>.rep. A computation over its budget refuses the module and the
      runner exits; a refused module answers nothing.

  probe <file> <host> <port>
      Try to read <file> and to open a TCP connection to <host>:<port>, and
      print one JSON line with both outcomes. Exit 0 only when BOTH were
      refused (the sandbox holds), 1 otherwise.
"""

import hashlib
import json
import math
import os
import socket
import sys
import threading
import time

CONTRACT_BOUNDS = {
    "api": 1,
    "call_s": 2,
    "poll_ms": 10,
    "beat_s": 1,
    "request_bytes_max": 1048576,
    "reply_bytes_max": 65536,
    "files_max": 64,
    "file_bytes_max": 8388608,
    "frame_bytes": 8,
    "rev_hex": 12,
    "fp_hex": 64,
    "connect_s": 3,
    "argc": 4,
    "exit_usage": 2,
}
DOMAIN = b"scr-review-module-revision\n"
STATUS = "status.json"
REQ = ".req"
REP = ".rep"
MODULE = "scr_review_module"


class Refusal(Exception):
    pass


def module_digest(files: dict) -> str:
    """sha256 over a framed manifest (the rules revision's framing under its
    own domain tag): the file count, then per file sorted by relative POSIX
    path its fixed-width path length, path, content length and content."""
    w = CONTRACT_BOUNDS["frame_bytes"]
    h = hashlib.sha256()
    h.update(DOMAIN)
    h.update(len(files).to_bytes(w, "big"))
    for path in sorted(files):
        p = path.encode("utf-8")
        c = files[path]
        h.update(len(p).to_bytes(w, "big"))
        h.update(p)
        h.update(len(c).to_bytes(w, "big"))
        h.update(c)
    return h.hexdigest()


def _module_files(root):
    files = {}
    for top, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for n in sorted(names):
            p = os.path.join(top, n)
            if os.path.islink(p) or not os.path.isfile(p):
                raise Refusal("inventory")
            if len(files) >= CONTRACT_BOUNDS["files_max"]:
                raise Refusal("inventory")
            with open(p, "rb") as f:
                data = f.read(CONTRACT_BOUNDS["file_bytes_max"] + 1)
            if len(data) > CONTRACT_BOUNDS["file_bytes_max"]:
                raise Refusal("inventory")
            files[os.path.relpath(p, root).replace(os.sep, "/")] = data
    return files


def _finite_value(v):
    if v is None:
        return True
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return math.isfinite(v)
    if isinstance(v, list):
        return all(_finite_value(x) and x is not None and not isinstance(x, list) for x in v)
    return False


class Runner:
    def __init__(self, module_dir, inbox, outbox):
        self.module_dir = module_dir
        self.inbox = inbox
        self.outbox = outbox
        self.word = "refused"
        self.reason = "start"
        self.measures = {}
        self.mod = None

    # -- validation, once --
    def load(self):
        try:
            files = _module_files(self.module_dir)
        except OSError:
            raise Refusal("unreadable")
        stated = files.pop("REVISION", b"").decode("ascii", "replace").strip()
        digest = module_digest(files)
        if stated != digest:
            raise Refusal("digest")
        sys.path.insert(0, self.module_dir)
        try:
            import scr_review_module as mod
        except Exception:                   # noqa: BLE001 -- any import failure refuses
            raise Refusal("import")
        try:
            api = mod.api_version
        except AttributeError:
            raise Refusal("api")
        if api != CONTRACT_BOUNDS["api"]:
            raise Refusal("api")
        try:
            measures = dict(mod.measures())
        except Exception:                   # noqa: BLE001
            raise Refusal("measures")
        for name, fp in measures.items():
            if (not isinstance(name, str) or not isinstance(fp, str)
                    or len(fp) != CONTRACT_BOUNDS["fp_hex"]):
                raise Refusal("measures")
        try:
            cases = json.loads(files["selftest.json"].decode("utf-8"))["cases"]
        except (KeyError, ValueError, TypeError, UnicodeDecodeError):
            raise Refusal("selftest")
        self.mod = mod
        for case in cases:
            if not isinstance(case, dict) or case.get("name") not in measures:
                raise Refusal("selftest")
            got = self.compute(case["name"], case.get("inputs"), case.get("params"))
            if got != case.get("value"):
                raise Refusal("selftest")
        self.measures = measures
        self.word = digest[: CONTRACT_BOUNDS["rev_hex"]]
        self.reason = None

    def compute(self, name, inputs, params):
        """One computation inside the per-call budget; over budget the module
        is refused and the runner leaves (a stuck thread cannot be stopped)."""
        out = {}

        def run():
            try:
                out["v"] = self.mod.compute(name, inputs, params)
            except Exception:               # noqa: BLE001 -- unknown, not fatal
                out["v"] = None
        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(CONTRACT_BOUNDS["call_s"])
        if t.is_alive():
            self.word, self.reason = "refused", "timeout"
            self.publish()
            os._exit(1)
        v = out.get("v")
        return v if _finite_value(v) else None

    # -- the exchange --
    def _write_atomic(self, name, obj):
        tmp = os.path.join(self.outbox, "." + name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, separators=(",", ":"))
        os.replace(tmp, os.path.join(self.outbox, name))

    def publish(self):
        self._write_atomic(STATUS, {"api": CONTRACT_BOUNDS["api"], "word": self.word,
                                    "reason": self.reason, "measures": self.measures,
                                    "beat": time.time()})

    def answer(self, name):
        rid = name[: -len(REQ)]
        path = os.path.join(self.inbox, name)
        try:
            with open(path, "rb") as f:
                raw = f.read(CONTRACT_BOUNDS["request_bytes_max"] + 1)
        except OSError:
            return
        value = None
        if len(raw) <= CONTRACT_BOUNDS["request_bytes_max"]:
            try:
                req = json.loads(raw.decode("utf-8"))
                if req.get("id") == rid and req.get("name") in self.measures:
                    value = self.compute(req["name"], req.get("inputs"), req.get("params"))
            except (ValueError, AttributeError, UnicodeDecodeError):
                value = None
        body = json.dumps({"id": rid, "value": value}, separators=(",", ":"))
        if len(body) > CONTRACT_BOUNDS["reply_bytes_max"]:
            body = json.dumps({"id": rid, "value": None})
        tmp = os.path.join(self.outbox, "." + rid + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, os.path.join(self.outbox, rid + REP))

    def serve(self, rounds=None):
        try:
            self.load()
        except Refusal as e:
            self.word, self.reason = "refused", str(e)
        answered = set()
        last_beat = 0.0
        n = 0
        while rounds is None or n < rounds:
            n += 1
            now = time.time()
            if now - last_beat >= CONTRACT_BOUNDS["beat_s"]:
                self.publish()
                last_beat = now
            if self.word != "refused":
                try:
                    pending = sorted(x for x in os.listdir(self.inbox) if x.endswith(REQ))
                except OSError:
                    pending = []
                for name in pending:
                    if name not in answered:
                        answered.add(name)
                        self.answer(name)
                answered &= set(pending)
            time.sleep(CONTRACT_BOUNDS["poll_ms"] / 1000)


def probe(path, host, port) -> int:
    out = {}
    try:
        with open(path, "rb") as f:
            f.read(1)
        out["undeclared_read"] = "read"
    except OSError as e:
        out["undeclared_read"] = "refused:" + type(e).__name__
    try:
        s = socket.create_connection((host, int(port)), timeout=CONTRACT_BOUNDS["connect_s"])
        s.close()
        out["network"] = "open"
    except OSError as e:
        out["network"] = "refused:" + type(e).__name__
    sys.stdout.write(json.dumps(out, sort_keys=True) + "\n")
    sys.stdout.flush()
    held = out["undeclared_read"] != "read" and out["network"] != "open"
    return 0 if held else 1


def main(argv):
    if len(argv) == CONTRACT_BOUNDS["argc"] and argv[0] == "serve":
        Runner(argv[1], argv[2], argv[3]).serve()
        return 0
    if len(argv) == CONTRACT_BOUNDS["argc"] and argv[0] == "probe":
        return probe(argv[1], argv[2], argv[3])
    sys.stdout.write(__doc__ + "\n")
    return CONTRACT_BOUNDS["exit_usage"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
