"""The evidence module's info lines reach the api's container log (repair A
of lane SRV-A, 16 Nov 2026).

On live, admin_evidence's warnings printed and its info lines never did. The
mechanism: the api's own lines are print() calls to stdout; uvicorn's
dictConfig configures only its own loggers (uvicorn, uvicorn.error,
uvicorn.access) and nothing gives the ROOT logger a handler, so the module
logger "admin_evidence" propagated to a root with no handler, and Python's
last-resort printer wrote WARNING records to stderr and dropped every info
record. log_lines.print_info_lines gives the module logger one print()
handler at INFO; it keeps propagating.

THE STATE A LIVE PROCESS HAS, and how it is made here: each case runs in a
FRESH interpreter (a subprocess, so no pytest handler, caplog or earlier
logging set-up is present), applies uvicorn's own logging config exactly as
`uvicorn main:app` does before it imports the app (LOGGING_CONFIG through
logging.config.dictConfig, the uvicorn loggers at INFO), imports main (which
imports admin_evidence as the live process does), then runs the warm-up and
a refusal through the module's own functions. The child's stdout and stderr
are captured whole. caplog is not used: it installs a handler of its own,
which is exactly the state live lacks.

uvicorn is not installed on every seat. When it is importable its
LOGGING_CONFIG is used and compared with the copy below; when it is not,
the copy is used with uvicorn's formatter classes replaced by the standard
one (a formatter decides how a uvicorn line looks, not which records reach
a handler).
"""
import json
import os
import subprocess
import sys

import pytest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
API = os.path.join(BACKEND, "api")

# uvicorn 0.30.6 (requirements.txt) uvicorn.config.LOGGING_CONFIG, formatters
# replaced by logging.Formatter. No "root" key: uvicorn leaves the root alone.
UVICORN_LOGGING_COPY = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(levelname)s: %(message)s"},
        "access": {"format": "%(levelname)s: %(message)s"},
    },
    "handlers": {
        "default": {"formatter": "default", "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr"},
        "access": {"formatter": "access", "class": "logging.StreamHandler",
                   "stream": "ext://sys.stdout"},
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}

CHILD = r'''
import asyncio, json, logging, logging.config, sys, types
sys.path.insert(0, sys.argv[1])
cfg = json.loads(sys.argv[2])
try:
    import uvicorn.config as _uc
    cfg = _uc.LOGGING_CONFIG
except ImportError:
    pass
logging.config.dictConfig(cfg)
for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(name).setLevel(logging.INFO)
import main  # noqa: F401  (imports admin_evidence as the live process does)
import admin_evidence as ae
mode = sys.argv[3]
if mode in ("ready", "skipped"):
    async def _warm_once(deadline):
        return types.SimpleNamespace(gen=7) if mode == "ready" else None
    ae._warm_once = _warm_once
    asyncio.run(ae.warm_display_population(delay_s=0))
elif mode == "refused_and_warning":
    ae._refuse_class("rate")
    ae._aer_log.warning("admin_evidence population unavailable: key=%r %s", "probe", "budget")
print("CHILD-ROOT-HANDLERS %d" % len(logging.getLogger().handlers), flush=True)
'''


def _child(mode):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONUNBUFFERED"] = "1"
    run = subprocess.run(
        [sys.executable, "-B", "-c", CHILD, API, json.dumps(UVICORN_LOGGING_COPY), mode],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stderr[-3000:]
    return run.stdout.splitlines(), run.stderr.splitlines()


def _lines(lines, prefix):
    return [ln for ln in lines if ln.startswith(prefix)]


def test_the_warm_up_ready_line_prints_once_on_stdout():
    out, err = _child("ready")
    ready = _lines(out, "admin_evidence population warm-up: ready gen=7 duration_ms=")
    assert len(ready) == 1, (out, err)
    assert not [ln for ln in err if "admin_evidence" in ln], err
    assert "CHILD-ROOT-HANDLERS 0" in out, out


def test_the_warm_up_skipped_line_prints_once_on_stdout():
    out, err = _child("skipped")
    want = ("admin_evidence population warm-up: skipped, the database is in recovery "
            "(reports answer primary_only here); word pending")
    assert out.count(want) == 1, (out, err)
    assert not [ln for ln in err if "admin_evidence" in ln], err


def test_an_info_line_and_a_warning_each_print_exactly_once():
    """One copy of each on stdout; nothing from the last-resort printer on
    stderr (it is used only when no handler exists anywhere in the chain)."""
    out, err = _child("refused_and_warning")
    assert out.count("admin_evidence refused: rate") == 1, (out, err)
    assert out.count("admin_evidence population unavailable: key='probe' budget") == 1, (out, err)
    assert not [ln for ln in err if "admin_evidence" in ln], err
    assert "CHILD-ROOT-HANDLERS 0" in out, out


def test_the_copy_matches_uvicorn_where_uvicorn_is_installed():
    uc = pytest.importorskip("uvicorn.config")
    real = uc.LOGGING_CONFIG
    assert "root" not in real
    assert real["disable_existing_loggers"] is False
    assert {k: {kk: vv for kk, vv in v.items()} for k, v in real["loggers"].items()} == \
        UVICORN_LOGGING_COPY["loggers"]
    assert {k: v.get("stream") for k, v in real["handlers"].items()} == \
        {k: v.get("stream") for k, v in UVICORN_LOGGING_COPY["handlers"].items()}


def test_print_info_lines_is_per_module_and_idempotent():
    import logging
    import log_lines
    with pytest.raises(ValueError):
        log_lines.print_info_lines(logging.getLogger())
    lg = logging.getLogger("srva_log_lines_probe")
    root = logging.getLogger()
    before = (root.level, list(root.handlers))
    try:
        log_lines.print_info_lines(lg)
        log_lines.print_info_lines(lg)
        assert len(lg.handlers) == 1 and lg.level == logging.INFO and lg.propagate is True
        assert (root.level, list(root.handlers)) == before
    finally:
        for h in list(lg.handlers):
            lg.removeHandler(h)
