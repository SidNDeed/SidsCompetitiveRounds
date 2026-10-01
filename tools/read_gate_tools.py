"""Verified reads: the seat's control caller and the census ledger.

Two thin seat CLIs import this module (scripts/ is local-only, so the logic
that tests exercise lives here, in the repo):

  scripts/read_gate_admin.py   -- run under scripts/run_with_admin_secret.py:
                                  mode off|log|enforce, keys issue|revoke|list,
                                  census. Every request is built by
                                  AdminCaller, which takes a TRANSPORT, so the
                                  tests drive the real app with no network.
  scripts/read_census_pull.py  -- pull | coverage --days 14 | canary --n 20.

Control requests carry the admin signature and NO X-Mod-Version: the five
control paths are in the version gate's bypass (main.py).

Ledger
------
A JSON-lines file, one record per pull attempt:
  {"node", "box", "at", "ok", "boot_id", "since", "counts": {key: n}, "error"}
`key` is the census row key joined with "|":
  route|method|class|key_id|version_header|refused

* deltas(records): per (node, boot_id) series, each successful pull's counts
  minus the previous successful pull of the SAME series. A repeated pull gives
  zero. A new boot id starts a new series whose first delta is its whole
  census since that boot.
* gaps(records): per node, every interval between consecutive successful
  pulls, plus, at a boot change, the UNRECORDED interval: from the old
  series' last successful pull to the new series' `since` (what the old
  process counted after its last pull is lost).
* coverage(records, days, now): per node over [now - days, now]: the
  covered fraction (window time not inside an uncovered interval: a gap over
  GAP_LIMIT, an unrecorded boot interval, the time before the first pull, the
  time since the last) and the longest gap. Fails when any gap exceeds
  GAP_LIMIT (60 minutes).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

PROBE_PATH = "/api/v1/read-gate/probe"
CENSUS_PATH = "/api/v1/admin/read-census"
GAP_LIMIT = 60 * 60
MODES = ("off", "log", "enforce")


def sign(secret: str, admin: str, action: str, target: str) -> str:
    canonical = f"admin:{admin}:{action}:{target or ''}"
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


# -- transports: (method, path, params, body, headers) -> (status, json|None) --

class UrllibTransport:
    """The seat's transport: one base URL (a box by LAN address, or the
    edge), stdlib only."""

    def __init__(self, base: str, timeout: float = 15.0):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def __call__(self, method, path, params=None, body=None, headers=None):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None
        h = dict(headers or {})
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw, status = r.read(), r.status
        except urllib.error.HTTPError as e:
            raw, status = e.read(), e.code
        try:
            return status, json.loads(raw.decode() or "null")
        except ValueError:
            return status, None


class AdminCaller:
    """Builds every control request. The transport decides where it goes."""

    def __init__(self, transport, admin: str, secret: str):
        if not admin or not secret:
            raise ValueError("admin identity and secret are both required")
        self.t, self.admin, self.secret = transport, admin, secret

    def _sig(self, action, target=""):
        return sign(self.secret, self.admin, action, target)

    def set_mode(self, mode: str):
        if mode not in MODES:
            raise ValueError(mode)
        return self.t("POST", "/api/v1/admin/read-gate/mode", body={
            "admin_steam_id": self.admin, "hmac_signature": self._sig("read_gate_mode", mode),
            "mode": mode})

    def issue_key(self, operator_name: str, contact: str):
        name = operator_name.strip().lower()
        return self.t("POST", "/api/v1/admin/operators/keys", body={
            "admin_steam_id": self.admin, "hmac_signature": self._sig("operator_key_issue", name),
            "operator_name": name, "contact": contact})

    def revoke_key(self, key_id: int):
        return self.t("POST", "/api/v1/admin/operators/keys/revoke", body={
            "admin_steam_id": self.admin,
            "hmac_signature": self._sig("operator_key_revoke", str(int(key_id))), "id": int(key_id)})

    def list_operators(self):
        return self.t("GET", "/api/v1/admin/operators", params={
            "admin_steam_id": self.admin, "hmac_signature": self._sig("operator_key_list", "")})

    def census(self):
        return self.t("GET", CENSUS_PATH, params={
            "admin_steam_id": self.admin, "hmac_signature": self._sig("read_census", "")})


# -- ledger -------------------------------------------------------------------

def row_key(row: dict) -> str:
    return "|".join(str(row[k]) for k in ("route", "method", "class", "key_id",
                                          "version_header", "refused"))


def pull_record(box: str, status, body, at: float) -> dict:
    """One ledger record from one census answer (or failure)."""
    if status == 200 and isinstance(body, dict) and "boot_id" in body:
        return {"node": body["node"], "box": box, "at": at, "ok": True,
                "boot_id": body["boot_id"], "since": body["since"],
                "counts": {row_key(r): int(r["count"]) for r in body.get("counts", [])},
                "error": ""}
    return {"node": None, "box": box, "at": at, "ok": False, "boot_id": None, "since": None,
            "counts": {}, "error": f"status {status}"}


def append(path: str, record: dict) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def load(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _epoch(since) -> float:
    """The census `since` (ISO 8601, UTC) as epoch seconds."""
    if isinstance(since, (int, float)):
        return float(since)
    from datetime import datetime
    return datetime.fromisoformat(str(since)).timestamp()


def _successes(records):
    by_node = {}
    for r in sorted(records, key=lambda r: r["at"]):
        if r["ok"]:
            by_node.setdefault(r["node"], []).append(r)
    return by_node


def deltas(records) -> list:
    """[(node, boot_id, at, {key: delta})] for every successful pull."""
    out, last = [], {}
    for r in sorted(records, key=lambda r: r["at"]):
        if not r["ok"]:
            continue
        series = (r["node"], r["boot_id"])
        prev = last.get(series, {})
        d = {k: v - prev.get(k, 0) for k, v in r["counts"].items() if v - prev.get(k, 0)}
        out.append((r["node"], r["boot_id"], r["at"], d))
        last[series] = r["counts"]
    return out


@dataclass
class Gap:
    node: str
    start: float
    end: float
    kind: str           # "between_pulls" | "unrecorded_boot"

    @property
    def seconds(self) -> float:
        return max(0.0, self.end - self.start)


def gaps(records) -> list:
    out = []
    for node, pulls in _successes(records).items():
        for a, b in zip(pulls, pulls[1:]):
            out.append(Gap(node, a["at"], b["at"], "between_pulls"))
            if a["boot_id"] != b["boot_id"]:
                out.append(Gap(node, a["at"], min(_epoch(b["since"]), b["at"]), "unrecorded_boot"))
    return out


def coverage(records, days: float, now: float) -> dict:
    """{node: {"covered": fraction, "longest_gap": seconds, "ok": bool}}."""
    start = now - days * 86400
    result = {}
    succ = _successes(records)
    all_gaps = gaps(records)
    for node, pulls in succ.items():
        uncovered = []
        first, last = pulls[0]["at"], pulls[-1]["at"]
        if first > start:
            uncovered.append((start, first))
        if now > last:
            uncovered.append((last, now))
        node_gaps = [g for g in all_gaps if g.node == node]
        for g in node_gaps:
            if g.kind == "unrecorded_boot" or g.seconds > GAP_LIMIT:
                uncovered.append((g.start, g.end))
        lost = _union_length([(max(a, start), min(b, now)) for a, b in uncovered if b > start])
        span = max(1.0, now - start)
        longest = max([g.seconds for g in node_gaps] + [max(0.0, now - last)])
        result[node] = {"covered": round(max(0.0, 1 - lost / span), 6),
                        "longest_gap": longest, "ok": longest <= GAP_LIMIT}
    return result


def _union_length(intervals) -> float:
    total, cur_a, cur_b = 0.0, None, None
    for a, b in sorted(i for i in intervals if i[1] > i[0]):
        if cur_b is None or a > cur_b:
            if cur_b is not None:
                total += cur_b - cur_a
            cur_a, cur_b = a, b
        else:
            cur_b = max(cur_b, b)
    if cur_b is not None:
        total += cur_b - cur_a
    return total


# -- canary -------------------------------------------------------------------

def probe_total(census_body: dict) -> int:
    return sum(int(r["count"]) for r in census_body.get("counts", []) if r["route"] == PROBE_PATH)


def canary(caller: AdminCaller, transport, n: int, headers=None) -> dict:
    """Send n probe GETs to ONE box and assert its census delta for the probe
    route is exactly n (any class, refused or not). Returns the verdict."""
    s0, before = caller.census()
    if s0 != 200:
        return {"ok": False, "why": f"census read {s0}"}
    statuses = [transport("GET", PROBE_PATH, headers=headers or {})[0] for _ in range(n)]
    s1, after = caller.census()
    if s1 != 200:
        return {"ok": False, "why": f"census read {s1}"}
    if after["boot_id"] != before["boot_id"]:
        return {"ok": False, "why": "the box restarted during the canary"}
    delta = probe_total(after) - probe_total(before)
    return {"ok": delta == n, "node": after["node"], "sent": n, "delta": delta,
            "statuses": sorted(set(statuses)), "why": "" if delta == n else "delta != sent"}


def now() -> float:
    return time.time()


# -- CLI bodies (the seat scripts call these) ---------------------------------

def pull_cli(ledger: str, callers: dict, at: float | None = None) -> int:
    """One pull per box: append a record for each, success or failure.
    Exit 0 when every box answered."""
    failures = 0
    for box, caller in callers.items():
        t = now() if at is None else at
        try:
            status, body = caller.census()
        except Exception as ex:                 # transport failure is a failed pull
            status, body = f"error {type(ex).__name__}", None
        rec = pull_record(box, status, body, t)
        append(ledger, rec)
        failures += 0 if rec["ok"] else 1
        print(f"{box}: {'ok' if rec['ok'] else rec['error']}"
              + (f" node={rec['node']} rows={len(rec['counts'])}" if rec["ok"] else ""))
    return 1 if failures else 0


def coverage_cli(ledger: str, days: float, at: float | None = None) -> int:
    records = load(ledger)
    result = coverage(records, days, now() if at is None else at)
    if not result:
        print("no successful pulls in the ledger")
        return 1
    bad = 0
    for node, v in sorted(result.items()):
        print(f"{node}: covered {v['covered'] * 100:.2f}% of {days:g} days, "
              f"longest gap {v['longest_gap'] / 60:.1f} min, {'ok' if v['ok'] else 'FAIL'}")
        bad += 0 if v["ok"] else 1
    return 1 if bad else 0


def canary_cli(boxes: dict, n: int, headers: dict) -> int:
    """boxes: {name: (caller, transport)} -- each box by LAN address."""
    bad = 0
    for box, (caller, transport) in boxes.items():
        v = canary(caller, transport, n, headers=headers)
        print(f"{box}: sent {n}, census delta {v.get('delta')}, "
              f"statuses {v.get('statuses')}, {'ok' if v['ok'] else 'FAIL ' + v['why']}")
        bad += 0 if v["ok"] else 1
    return 1 if bad else 0
