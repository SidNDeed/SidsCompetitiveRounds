"""Verified reads, requirement 32 (M6), server half: the ONE signal the client
uses to tell an ungated read from a gated one is the `read_gate_open` list in
the OPEN /api/v1/mod-version answer (section 0 (c)). The client compiles no
list of its own; it matches each request's path against these templates.

So the property is: the advertised list equals, exactly, the templates of
every GET route the gate never refuses (OPEN, WRITE_ON_GET, ADMIN_SIGNED,
PORTAL, INTERNAL), computed here independently from the app's routes and
route_class -- and it contains every OPEN template, /mod-version itself
included (the advert must be readable on the fallback). The client half's
harness (suite `readgate`) proves the client treats exactly the advertised
templates as ungated.
"""
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import read_gate_testkit as K
import main
import read_gate

UNGATED = (read_gate.C_OPEN, read_gate.C_WRITE_ON_GET, read_gate.C_ADMIN_SIGNED,
           read_gate.C_PORTAL, read_gate.C_INTERNAL)


def _independent():
    out = set()
    for r in main.app.routes:
        if isinstance(r, APIRoute) and "GET" in r.methods and read_gate.route_class(r.path) in UNGATED:
            out.add(r.path)
    return out


@pytest.mark.parametrize("stage", ["off", "log", "enforce"])
def test_client_open_set_equals_server_open(monkeypatch, stage):
    with K.gate_env(monkeypatch, mode=stage):
        client = TestClient(main.app, raise_server_exceptions=False)
        r = client.get("/api/v1/mod-version", headers=K.headers())
        assert r.status_code == 200
        advertised = r.json()["read_gate_open"]
        assert len(advertised) == len(set(advertised)), "duplicate templates"
        assert set(advertised) == _independent()
        assert set(read_gate.OPEN) <= set(advertised)
        assert "/api/v1/mod-version" in advertised
        # nothing gated is advertised: a PUBLIC, PLAYER, BOT_ONLY or PROBE
        # template in the list would be sent without a credential
        for t in advertised:
            assert read_gate.route_class(t) in UNGATED, t


def test_advert_moves_with_the_classes(monkeypatch):
    """Negative control: a template moved out of the ungated classes leaves
    the advert, so a stale client list could not pass the equality above."""
    template = "/api/v1/release-notes/{locale}"
    with K.gate_env(monkeypatch, mode="log"):
        client = TestClient(main.app, raise_server_exceptions=False)
        before = client.get("/api/v1/mod-version", headers=K.headers()).json()["read_gate_open"]
        assert template in before
        monkeypatch.setattr(read_gate, "OPEN", {k: v for k, v in read_gate.OPEN.items() if k != template})
        after = client.get("/api/v1/mod-version", headers=K.headers()).json()["read_gate_open"]
        assert template not in after and set(after) == _independent()
