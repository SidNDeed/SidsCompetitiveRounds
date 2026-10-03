"""Choice two: a private module that ADDS measures, run as its own sandboxed
service. It never decides: every review item is still a rule in the rules
revision, so wording, arming and values keep one home.

The api never imports, starts or hosts a module. A module runs in the compose
service `review-module` (backend/docker-compose.yml, profile `review-module`,
image backend/api/Dockerfile.review-module holding only the runner):

  * no network at all (network_mode: none), a read-only root filesystem, no
    capabilities, no new privileges, an unprivileged user and no environment;
  * exactly three mounts, and nothing else of the host: the module revision
    directory READ-ONLY, the request exchange READ-ONLY, and a tmpfs the
    runner answers into;
  * the api reaches it ONLY through that exchange (two tmpfs volumes shared
    with the api):
        <exchange>/in/<id>.req      the api writes (atomic rename); the runner reads
        <exchange>/out/<id>.rep     the runner writes (atomic rename); the api reads
                                    and removes it
        <exchange>/out/status.json  the runner's word, its measures and a heartbeat

The runner validates the module ONCE, at its own start (code is never
reloaded): the framed digest of the revision directory against its REVISION
file, the module's api version, its measure names and fingerprints, and its
own selftest.json of inputs and expected outputs. The api then checks the
names against the public vocabulary (a module measure may not collide with a
public one).

Health word `review_module`: the module revision id (rev_hex characters) when the
runner's status says loaded, its heartbeat is fresh and the names are
admissible; `absent` when no status was ever written (the service is not
running, the default); `refused` otherwise. The refusal class goes to the
log once per change, never to the health word.

A refused or absent module makes every module measure unknown, so a rule that
needs one never fires and every other rule runs. Every wait here is bounded.
A computation that times out makes its measure unknown and refuses the module
for the rest of this process (it is not retried silently)."""

from __future__ import annotations

import json
import math
import os
import re
import secrets
import threading
import time

import review_measures as rm

CONTRACT_BOUNDS = {
    "api": 1,
    "call_s": 2,
    "poll_ms": 10,
    "reply_bytes_max": 65536,
    "status_bytes_max": 65536,
    "heartbeat_stale_s": 10,
    "reason_max": 32,
    "rev_hex": 12,
    "fp_hex": 64,
    "id_bytes": 8,
}
MODULE_API = CONTRACT_BOUNDS["api"]
EXCHANGE_ENV = "SCR_REVIEW_MODULE_EXCHANGE"
DEFAULT_EXCHANGE = "/app/private/review-module-exchange"
STATUS = "status.json"
MODULE_PREFIX = "module."

_HEX = re.compile(r"[a-f\d]+")


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


def _read_capped(path, cap):
    with open(path, "rb") as f:
        data = f.read(cap + 1)
    if len(data) > cap:
        raise ValueError("oversized")
    return data


class ExchangeModule:
    """The api's side of the exchange with one running module service."""

    def __init__(self, root, *, call_s=None, stale_s=None):
        self.root = root
        self.call_s = CONTRACT_BOUNDS["call_s"] if call_s is None else call_s
        self.stale_s = CONTRACT_BOUNDS["heartbeat_stale_s"] if stale_s is None else stale_s
        self.failed = None          # a refusal this process saw during a computation
        self.lock = threading.Lock()

    @property
    def inbox(self):
        return os.path.join(self.root, "in")

    @property
    def outbox(self):
        return os.path.join(self.root, "out")

    def status(self):
        """(word, reason, measures): the runner's status checked here."""
        if self.failed is not None:
            return "refused", self.failed, {}
        path = os.path.join(self.outbox, STATUS)
        try:
            doc = json.loads(_read_capped(path, CONTRACT_BOUNDS["status_bytes_max"]).decode("utf-8"))
        except FileNotFoundError:
            return "absent", None, {}
        except (OSError, ValueError, UnicodeDecodeError):
            return "refused", "status", {}
        if not isinstance(doc, dict) or doc.get("api") != MODULE_API:
            return "refused", "api", {}
        beat = doc.get("beat")
        if not isinstance(beat, (int, float)) or abs(time.time() - beat) > self.stale_s:
            return "refused", "stale", {}
        word = doc.get("word")
        if word == "refused":
            reason = str(doc.get("reason") or "runner")[: CONTRACT_BOUNDS["reason_max"]]
            return "refused", "runner:" + reason, {}
        if (not isinstance(word, str) or len(word) != CONTRACT_BOUNDS["rev_hex"]
                or not _HEX.fullmatch(word)):
            return "refused", "word", {}
        measures = doc.get("measures")
        if not isinstance(measures, dict):
            return "refused", "measures", {}
        for name, fp in measures.items():
            if (not isinstance(name, str) or not name.startswith(MODULE_PREFIX)
                    or name in rm.REGISTRY):
                return "refused", "collision", {}
            if (not isinstance(fp, str) or len(fp) != CONTRACT_BOUNDS["fp_hex"]
                    or not _HEX.fullmatch(fp)):
                return "refused", "fingerprint", {}
        return word, None, dict(measures)

    def word(self) -> str:
        return self.status()[0]

    def fingerprint(self, name):
        word, _reason, measures = self.status()
        if word in ("absent", "refused"):
            return None
        return measures.get(name)

    def compute(self, name, ctx, params):
        """One module measure for one subject, or None (unknown)."""
        if self.fingerprint(name) is None:
            return None
        rid = secrets.token_hex(CONTRACT_BOUNDS["id_bytes"])
        req = {"id": rid, "name": name, "params": params,
               "inputs": {"subject_index": ctx.i, "records": [r["rec"] for r in ctx.records]}}
        tmp = os.path.join(self.inbox, "." + rid + ".tmp")
        final = os.path.join(self.inbox, rid + ".req")
        reply = os.path.join(self.outbox, rid + ".rep")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(req, f, separators=(",", ":"))
            os.replace(tmp, final)
            deadline = time.monotonic() + self.call_s
            while not os.path.exists(reply):
                if time.monotonic() > deadline:
                    self._refuse("timeout")
                    return None
                time.sleep(CONTRACT_BOUNDS["poll_ms"] / 1000)
            try:
                doc = json.loads(_read_capped(reply, CONTRACT_BOUNDS["reply_bytes_max"]).decode("utf-8"))
            except ValueError:
                self._refuse("reply")
                return None
            if not isinstance(doc, dict) or doc.get("id") != rid:
                self._refuse("reply")
                return None
            v = doc.get("value")
            return v if _value_ok(v) else None
        except OSError:
            self._refuse("exchange")
            return None
        finally:
            for p in (tmp, final, reply):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def _refuse(self, cls):
        with self.lock:
            if self.failed is None:
                self.failed = cls


_MODULE = None
_LOGGED = None


def exchange_root() -> str:
    return os.environ.get(EXCHANGE_ENV) or DEFAULT_EXCHANGE


def _module() -> ExchangeModule:
    global _MODULE
    root = exchange_root()
    if _MODULE is None or _MODULE.root != root:
        _MODULE = ExchangeModule(root)
    return _MODULE


def _log(word, reason):
    global _LOGGED
    sig = (word, reason)
    if sig != _LOGGED:
        _LOGGED = sig
        if word == "refused":
            print("[REVIEW] module: refused (%s)" % reason, flush=True)
        else:
            print("[REVIEW] module: %s" % word, flush=True)


def health_word() -> str:
    """The revision id | absent | refused, derived on every call."""
    word, reason, _m = _module().status()
    _log(word, reason)
    return word


def current_module():
    """The module for a pass, or None when it is absent or refused."""
    m = _module()
    word, reason, _measures = m.status()
    _log(word, reason)
    return None if word in ("absent", "refused") else m
