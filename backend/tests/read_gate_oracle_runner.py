"""One side of the bar BV-A comparison (test_read_gate_trunk_oracle).

    python read_gate_oracle_runner.py <tree> <dsn> <schema> <requests.json> <out.json>

Imports the FastAPI app of `<tree>/backend/api` (the lane's own tree, or a
scratch export of the trunk base), binds its request sessions and its
database.async_session to `<schema>` through a NullPool engine, and sends
every request of `<requests.json>` in order through a TestClient, with no
lifespan (the same for both trees). Writes, per request, the status, every
response header and the body bytes. A `ws` entry opens the chat socket with
its headers, reads the first frame and closes.

The rate-limit buckets are cleared before each request on both sides, so a
long replay from one address is not throttled differently by timing.
"""
from __future__ import annotations

import base64
import json
import os
import sys


def main(argv):
    tree, dsn, schema, req_path, out_path = argv[1:6]
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
            continue
        body = r.get("body")
        resp = client.request(r["method"], r["url"], headers=r["headers"],
                              content=body.encode("utf-8") if body is not None else None)
        out.append({"status": resp.status_code,
                    "headers": sorted([k.lower(), v] for k, v in resp.headers.items()),
                    "body": base64.b64encode(resp.content).decode("ascii")})
    json.dump({"main": loaded, "results": out}, open(out_path, "w", encoding="utf-8"))
    print("sent", len(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
