"""One side of the bar BV-A comparison (test_read_gate_trunk_oracle).

    python read_gate_oracle_runner.py <tree> <dsn> <schema> <requests.json> <out.json> [<freeze epoch>]

Imports the FastAPI app of `<tree>/backend/api` (the lane's own tree, or a
scratch export of the trunk base), binds its request sessions and its
database.async_session to `<schema>` through a NullPool engine, and sends
every request of `<requests.json>` in order through a TestClient, with no
lifespan (the same for both trees). Writes, per request, the status, every
response header, the body bytes, and the wall clock just before the request
was sent and just after its answer (t0, t1). A `ws` entry opens the chat
socket with its headers, reads the first frame and closes.

With a freeze epoch, the two sources that made trunk's own answers vary run
to run are frozen identically on every side (round 2 finding M1): the app
module's `datetime.now`/`utcnow` answer that instant (the boards'
`last_updated`), and its `secrets.choice` draws from one seeded sequence (the
link code). Only the app module's own names are replaced; every other module,
and the database clock, keep the real ones.

The rate-limit buckets are cleared before each request on both sides, so a
long replay from one address is not throttled differently by timing.
"""
from __future__ import annotations

import base64
import json
import os
import random
import sys
import time
import types
from datetime import datetime as _real_datetime, timezone as _tz


def _frozen_datetime(epoch: float):
    """A datetime subclass whose now()/utcnow() answer `epoch`; isinstance
    against it accepts every real datetime, so nothing else behaves
    differently."""
    class _Meta(type(_real_datetime)):
        def __instancecheck__(cls, obj):
            return isinstance(obj, _real_datetime)

    class FrozenDatetime(_real_datetime, metaclass=_Meta):
        @classmethod
        def now(cls, tz=None):
            moment = _real_datetime.fromtimestamp(epoch, _tz.utc)
            return moment.astimezone(tz) if tz is not None else moment.astimezone().replace(tzinfo=None)

        @classmethod
        def utcnow(cls):
            return _real_datetime.fromtimestamp(epoch, _tz.utc).replace(tzinfo=None)

    return FrozenDatetime


def _seeded_secrets(real, seed: int):
    """The `secrets` module with `choice` drawn from one seeded sequence."""
    rng = random.Random(seed)
    proxy = types.ModuleType("secrets")
    for name in dir(real):
        if not name.startswith("__"):
            setattr(proxy, name, getattr(real, name))
    proxy.choice = rng.choice
    return proxy


def main(argv):
    tree, dsn, schema, req_path, out_path = argv[1:6]
    freeze = float(argv[6]) if len(argv) > 6 else None
    api = os.path.join(tree, "backend", "api")
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, api)
    sys.path.append(here)
    import database                       # noqa: E402  (the tree's own)
    import main as app_main               # noqa: E402
    import ladder_pg_harness as harness   # noqa: E402  (imports no app module)
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

    loaded = os.path.normcase(os.path.abspath(app_main.__file__))
    assert loaded.startswith(os.path.normcase(os.path.abspath(api))), (loaded, api)
    if freeze is not None:
        assert isinstance(app_main.datetime, type) and app_main.datetime is _real_datetime
        assert app_main.secrets.__name__ == "secrets"
        app_main.datetime = _frozen_datetime(freeze)
        app_main.secrets = _seeded_secrets(app_main.secrets, int(freeze))

    engine = harness.bound_engine(dsn, schema)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_db():
        async with sm() as s:
            try:
                yield s
            finally:
                await s.close()

    database.async_session = sm
    app_main.app.dependency_overrides[app_main.get_db] = _get_db
    client = TestClient(app_main.app, raise_server_exceptions=False)
    requests = json.load(open(req_path, encoding="utf-8"))
    out = []
    for r in requests:
        if hasattr(app_main, "_RL_BUCKETS"):
            app_main._RL_BUCKETS.clear()
        t0 = time.time()
        if r["method"] == "WS":
            try:
                with client.websocket_connect(r["url"], headers=r["headers"]) as ws:
                    frame = ws.receive_text()
                out.append({"status": 101, "headers": [], "body": base64.b64encode(
                    frame.encode("utf-8")).decode("ascii")})
            except Exception as exc:          # a refused socket is an answer too
                out.append({"status": -1, "headers": [], "body": base64.b64encode(
                    (type(exc).__name__ + ":" + str(getattr(exc, "code", ""))
                     + ":" + str(getattr(exc, "reason", ""))).encode()).decode("ascii")})
            out[-1].update(t0=t0, t1=time.time())
            continue
        body = r.get("body")
        resp = client.request(r["method"], r["url"], headers=r["headers"],
                              content=body.encode("utf-8") if body is not None else None)
        out.append({"status": resp.status_code,
                    "headers": sorted([k.lower(), v] for k, v in resp.headers.items()),
                    "body": base64.b64encode(resp.content).decode("ascii"),
                    "t0": t0, "t1": time.time()})
    json.dump({"main": loaded, "results": out}, open(out_path, "w", encoding="utf-8"))
    print("sent", len(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
