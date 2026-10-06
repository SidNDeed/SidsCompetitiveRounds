"""tools/thunderstore_changelog_trim.py: the Thunderstore CHANGELOG stays
under 100,000 bytes, the oldest sections go first, and the tail paragraph that
links to the full history always survives.

Each check has its control: the no-op case proves the tool does not rewrite a
file that fits (byte-identical, CRLF kept), and the refusals prove it will not
trim a file it would damage."""
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("ts_trim", REPO / "tools" / "thunderstore_changelog_trim.py")
ts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ts)

TAIL = ts.MARKER + b"\n"


def _doc(n, body=b"x" * 200, nl=b"\n"):
    secs = b"".join(b"## v1.%d.0 - day %d" % (n - i, n - i) + nl + nl + body + nl + nl for i in range(n))
    return secs + TAIL.replace(b"\n", nl)


def test_under_the_limit_is_a_byte_identical_no_op():
    for nl in (b"\n", b"\r\n"):
        raw = _doc(5, nl=nl)
        out, dropped = ts.trim(raw, limit=len(raw))
        assert out == raw and dropped == []


def test_the_oldest_sections_go_first_and_the_tail_stays():
    raw = _doc(6)
    limit = len(raw) - 300
    out, dropped = ts.trim(raw, limit=limit)
    assert len(out) <= limit
    assert dropped == ["## v1.1.0 - day 1", "## v1.2.0 - day 2"]
    assert out.startswith(b"## v1.6.0") and b"## v1.3.0" in out and b"## v1.2.0" not in out
    assert out.endswith(TAIL) and out.count(ts.MARKER) == 1


def test_crlf_files_keep_their_line_endings():
    raw = _doc(6, nl=b"\r\n")
    out, _ = ts.trim(raw, limit=len(raw) - 300)
    assert b"\n" not in out.replace(b"\r\n", b"")


def test_a_missing_marker_is_refused():
    raw = _doc(4).replace(ts.MARKER, b"(gone)")
    with pytest.raises(ValueError):
        ts.trim(raw, limit=10)


def test_a_newest_section_over_the_limit_is_refused():
    raw = _doc(3, body=b"y" * 5000)
    with pytest.raises(ValueError):
        ts.trim(raw, limit=1000)


def test_the_shipped_template_is_under_the_limit_and_carries_the_marker():
    path = REPO / "thunderstore" / "SidsCompetitiveRounds_upload" / "CHANGELOG.md"
    raw = path.read_bytes()
    head, sections, tail = ts.split(raw)
    assert sections and tail.startswith(ts.MARKER)
    assert len(raw) <= ts.LIMIT
    assert ts.trim(raw)[0] == raw
