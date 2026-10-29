"""build_manifest.health_word never raises into /health: a missing manifest
reads "absent", a present but unreadable one (a directory in its place, a
permission) reads "refused", and the first word stands for the process whatever
the file does after (the file is written at image build and never changes in a
running container)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import build_manifest as bm  # noqa: E402


@pytest.fixture
def fresh(monkeypatch):
    """A process that has not read its word yet."""
    monkeypatch.setattr(bm, "_WORD", {})
    return monkeypatch


def test_a_missing_manifest_reads_absent(fresh, tmp_path):
    fresh.setattr(bm, "MANIFEST", tmp_path / "build-manifest.json")
    assert bm.health_word() == "absent"


def test_an_unreadable_manifest_reads_refused_not_an_error(fresh, tmp_path):
    # A directory where the file should be: read_bytes raises an OSError that is
    # not FileNotFoundError (IsADirectoryError on Linux, PermissionError on
    # Windows). The control proves the read really raises before the word is asked.
    fresh.setattr(bm, "MANIFEST", tmp_path)
    with pytest.raises(OSError):
        bm.MANIFEST.read_bytes()
    assert bm.health_word() == "refused"


def test_the_word_is_read_once_per_process(fresh, tmp_path):
    fresh.setattr(bm, "MANIFEST", tmp_path / "build-manifest.json")
    assert bm.health_word() == "absent"
    (tmp_path / "build-manifest.json").write_bytes(b"{}")
    assert bm.health_word() == "absent"        # the first read stands
    assert bm.word_for(b"{}") == "refused"     # what a second read would have said


def test_word_for_the_three_byte_shapes():
    assert bm.word_for(None) == "absent"       # no file
    assert bm.word_for(b"") == "refused"       # unreadable, or empty
    assert bm.word_for(b"not json") == "refused"
