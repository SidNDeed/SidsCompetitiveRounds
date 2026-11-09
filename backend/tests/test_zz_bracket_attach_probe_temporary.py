"""TEMPORARY (bracket names re-pin only; the re-pin commit removes this file).

The attach tool, tools/keybind_surfaces.py attach --tree <this tree>, run in
this process on the seat (whose wrapper admits pytest only). When its rows
differ from tools/keybind_surfaces_attach.tsv, its whole output is printed
between markers with its md5 and the test fails, so the seat's log carries the
tool's own output. A second test prints the check mode's problems."""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _ks():
    spec = importlib.util.spec_from_file_location("keybind_surfaces_bracket", str(REPO / "tools" / "keybind_surfaces.py"))
    ks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ks)
    return ks


def test_bracket_attach_probe_temporary():
    ks = _ks()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = ks.main(["attach", "--tree", str(REPO)])
    text = buf.getvalue()
    man = io.open(str(REPO / "tools" / "keybind_surfaces_attach.tsv"), encoding="utf-8", newline="").read().replace("\r\n", "\n")
    rows = [ln for ln in text.split("\n") if ln and not ln.startswith("#")]
    mrows = [ln for ln in man.split("\n") if ln and not ln.startswith("#")]
    if rc == 0 and rows == mrows:
        return
    print("BRACKET-ATTACH-BEGIN rc=%d lines=%d md5=%s" % (rc, len(text.splitlines()), hashlib.md5(text.encode("utf-8")).hexdigest()))
    print(text, end="")
    print("BRACKET-ATTACH-END")
    pytest.fail("BRACKET the attach tool's rows differ from the manifest: %d rows, manifest %d" % (len(rows), len(mrows)))


def test_bracket_check_probe_temporary():
    ks = _ks()
    problems, summary, _ = ks.check(str(REPO))
    print("BRACKET-CHECK-BEGIN problems=%d" % len(problems))
    for p in problems:
        print("[f1] " + p)
    print("BRACKET-CHECK-END " + summary)
    assert problems == []
