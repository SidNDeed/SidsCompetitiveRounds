"""A11, A14 and design report finding 4: the private-needle check, in a
disposable repository with a SYNTHETIC private store. Separate controls for a
staged line, a committed blob, a message and a path; a clean commit passes;
the report names class and count only; a review packet admits only
allowlisted public sources, byte-verified, so a private number handed to it
cannot enter."""

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, HERE)

import review_needles as rn  # noqa: E402
import review_testkit as tk  # noqa: E402


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def world(tmp_path, monkeypatch):
    store, rev = tk.build_revision(tmp_path / "private")
    os.makedirs(os.path.join(store, "tests"))
    with open(os.path.join(store, "tests", "needles.txt"), "w", encoding="utf-8") as f:
        f.write("# synthetic\nsynthetic_private_identifier\n")
    with open(os.path.join(store, "tests", "synthetic_private_notes.md"), "w", encoding="utf-8") as f:
        f.write("synthetic\n")
    monkeypatch.setenv(rn.STORE_ENV, store)
    repo = str(tmp_path / "repo")
    subprocess.run(["git", "init", "-q", repo], check=True)
    with open(os.path.join(repo, "a.txt"), "w", encoding="utf-8") as f:
        f.write("public text\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return store, repo, _git(repo, "rev-parse", "HEAD")


def _write(repo, name, text):
    with open(os.path.join(repo, name), "w", encoding="utf-8") as f:
        f.write(text)


def test_the_needles_derive_from_the_store(world):
    store, _repo, _base = world
    n = rn.derive(store)
    assert tk.ID_PUB in n["rule_id"] and len(n["nonce"]) == 1
    assert "synthetic_private_identifier" in n["listed"]
    assert "synthetic_private_notes.md" in n["basename"]
    assert not any(b.startswith("rules-") for b in n["basename"])
    assert n["wording"]


def test_a11_a_staged_line_is_refused_with_class_and_count_only(world, capsys):
    _store, repo, _base = world
    _write(repo, "b.txt", "x %s y\n" % tk.ID_GAP)
    _git(repo, "add", "b.txt")
    assert rn.main(["staged", repo]) == 1
    out = capsys.readouterr().out
    assert "rule_id=1" in out and tk.ID_GAP not in out


def test_a11_a_clean_staged_change_passes(world, capsys):
    _store, repo, _base = world
    _write(repo, "b.txt", "nothing private here 7 11\n")
    _git(repo, "add", "b.txt")
    assert rn.main(["staged", repo]) == 0


def test_a11_a_committed_blob_is_refused_in_range_mode(world, capsys):
    _store, repo, base = world
    _write(repo, "c.txt", "synthetic published 9 over observed 1 (seat 0)\n")
    _git(repo, "add", "c.txt")
    _git(repo, "commit", "-q", "-m", "plain message")
    _write(repo, "c.txt", "gone\n")
    _git(repo, "commit", "-q", "-am", "plain message")
    assert rn.main(["range", repo, base, "HEAD"]) == 1
    out = capsys.readouterr().out
    assert "wording=1" in out and "synthetic published" not in out


def test_a11_a_commit_message_is_refused(world, capsys, tmp_path):
    _store, repo, base = world
    _write(repo, "d.txt", "public\n")
    _git(repo, "add", "d.txt")
    _git(repo, "commit", "-q", "-m", "mentions synthetic_private_identifier")
    assert rn.main(["range", repo, base, "HEAD"]) == 1
    assert "listed=1" in capsys.readouterr().out
    msg = tmp_path / "msg.txt"
    msg.write_text("subject\n\nbody naming %s\n" % tk.ID_STEP)
    assert rn.main(["message", str(msg)]) == 1


def test_a11_a_private_path_is_refused(world, capsys):
    _store, repo, _base = world
    _write(repo, "synthetic_private_notes.md", "harmless body\n")
    _git(repo, "add", "-A")
    assert rn.main(["staged", repo]) == 1
    assert "basename=" in capsys.readouterr().out


def test_a11_a_clean_range_passes(world, capsys):
    _store, repo, base = world
    _write(repo, "e.txt", "public 7\n")
    _git(repo, "add", "e.txt")
    _git(repo, "commit", "-q", "-m", "clean")
    assert rn.main(["range", repo, base, "HEAD"]) == 0
    assert "0 found" in capsys.readouterr().out


def test_a14_a_review_input_directory_reads_zero_then_one(world, tmp_path, capsys):
    d = tmp_path / "REVIEW-INPUT"
    d.mkdir()
    (d / "brief.md").write_text("generic prose about the evaluator\n")
    assert rn.main(["scan-dir", str(d)]) == 0
    (d / "planted.txt").write_text("rule %s\n" % tk.ID_NOTE)
    assert rn.main(["scan-dir", str(d)]) == 1
    assert "1 found" in capsys.readouterr().out.splitlines()[-1]


def test_finding4_a_packet_admits_only_allowlisted_public_sources(world, tmp_path, capsys):
    _store, repo, base = world
    allow = tmp_path / "allow.txt"
    allow.write_text("a.txt\n")
    out = tmp_path / "packet"
    assert rn.main(["packet", repo, base, str(allow), str(out)]) == 0
    assert sorted(os.listdir(out)) == ["a.txt"]
    # a brief holding only a private number and generic prose has no
    # needle to find -- it is refused because it is not an allowlisted source
    brief = tmp_path / "brief.md"
    brief.write_text("the floor is 17\n")
    allow.write_text("a.txt\n%s\n" % brief)
    assert rn.main(["packet", repo, base, str(allow), str(tmp_path / "p2")]) == 1
    assert "not_an_allowlisted_public_source" in capsys.readouterr().out
    assert not (tmp_path / "p2").exists()


def test_m5_unarmed_and_no_verdict_refuse_and_differ_from_a_hit(monkeypatch, tmp_path, capsys):
    """An unset store variable REFUSES (4), an unreadable or empty store
    REFUSES (3); both differ from a hit (1) and neither is a pass (0)."""
    d = tmp_path / "clean"
    d.mkdir()
    (d / "a.txt").write_text("public\n")
    monkeypatch.delenv(rn.STORE_ENV, raising=False)
    assert rn.main(["scan-dir", str(d)]) == 4
    assert "unarmed" in capsys.readouterr().out
    monkeypatch.setenv(rn.STORE_ENV, str(tmp_path / "missing"))
    assert rn.main(["scan-dir", str(d)]) == 3
    empty = tmp_path / "empty_store"
    empty.mkdir()
    monkeypatch.setenv(rn.STORE_ENV, str(empty))
    assert rn.main(["scan-dir", str(d)]) == 3


def test_m5_control_an_armed_store_passes_the_same_clean_directory(world, tmp_path):
    d = tmp_path / "clean"
    d.mkdir()
    (d / "a.txt").write_text("public\n")
    assert rn.main(["scan-dir", str(d)]) == 0


def test_m5_a_single_fragment_wording_is_a_needle(world, tmp_path, capsys):
    store, _repo, _base = world
    n = rn.derive(store)
    assert ("synthetic note seat",) in n["wording"]          # tk.ID_NOTE's one fragment
    d = tmp_path / "d"
    d.mkdir()
    (d / "x.txt").write_text("rendered: synthetic note seat 1\n")
    assert rn.main(["scan-dir", str(d)]) == 1
    assert "wording=1" in capsys.readouterr().out
    (d / "x.txt").write_text("rendered: synthetic note\n")    # control: the fragment cut short
    assert rn.main(["scan-dir", str(d)]) == 0


def test_m5_referenced_and_shipped_data_names_are_needles(world, tmp_path, capsys):
    store, _repo, _base = world
    rdir = [os.path.join(store, x) for x in os.listdir(store) if x.startswith("rules-")][0]
    os.makedirs(os.path.join(rdir, "data"))
    with open(os.path.join(rdir, "data", "synthetic_lookup_table.json"), "w", encoding="utf-8") as f:
        f.write("[]\n")
    import json
    with open(os.path.join(rdir, "rules.json"), encoding="utf-8") as f:
        doc = json.load(f)
    doc["rules"][0]["when"]["args"]["b"] = {"data": "synthetic_referenced_name.json"}
    with open(os.path.join(rdir, "rules.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f)
    n = rn.derive(store)
    assert {"synthetic_lookup_table.json", "synthetic_lookup_table",
            "synthetic_referenced_name.json", "synthetic_referenced_name"} <= n["data"]
    d = tmp_path / "d"
    d.mkdir()
    (d / "x.txt").write_text("loads synthetic_referenced_name\n")
    assert rn.main(["scan-dir", str(d)]) == 1
    assert "data=1" in capsys.readouterr().out
    (d / "x.txt").write_text("loads a lookup table\n")         # control
    assert rn.main(["scan-dir", str(d)]) == 0


def test_m4_a_packet_admits_a_pinned_document_and_refuses_an_edited_one(world, tmp_path, capsys):
    import hashlib
    _store, repo, base = world
    doc = tmp_path / "notes.md"
    doc.write_text("generic description of the evidence\n")
    digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    allow = tmp_path / "allow.txt"
    allow.write_text("a.txt\ndoc %s %s\n" % (doc, digest))
    out = tmp_path / "packet"
    assert rn.main(["packet", repo, base, str(allow), str(out)]) == 0
    assert sorted(os.listdir(out)) == ["a.txt", "docs"] and os.listdir(out / "docs") == ["notes.md"]
    doc.write_text("generic description of the evidence, edited\n")
    assert rn.main(["packet", repo, base, str(allow), str(tmp_path / "p2")]) == 1
    assert "doc_digest_differs" in capsys.readouterr().out
    assert not (tmp_path / "p2").exists()
    doc.write_text("rule %s\n" % tk.ID_NOTE)                   # pinned, but carrying a needle
    allow.write_text("doc %s %s\n" % (doc, hashlib.sha256(doc.read_bytes()).hexdigest()))
    assert rn.main(["packet", repo, base, str(allow), str(tmp_path / "p3")]) == 1
    assert "rule_id=1" in capsys.readouterr().out


# -- round 2 M5: every read of the store refuses through the one path (exit 3) -----

def _store_case(store, how):
    tests = os.path.join(store, "tests")
    if how == "needles_list":
        os.remove(os.path.join(tests, "needles.txt"))
        os.mkdir(os.path.join(tests, "needles.txt"))            # open() fails
    elif how == "public_list":
        os.mkdir(os.path.join(tests, "public.txt"))             # open() fails
    elif how == "basename_listing":
        import shutil
        shutil.rmtree(tests)
        with open(tests, "w", encoding="utf-8") as f:           # listdir() fails
            f.write("x")
    elif how == "revision_rules":
        rdir = [os.path.join(store, x) for x in os.listdir(store) if x.startswith("rules-")][0]
        with open(os.path.join(rdir, "rules.json"), "w", encoding="utf-8") as f:
            f.write("{")                                       # parse fails


@pytest.mark.parametrize("how", ["needles_list", "public_list", "basename_listing", "revision_rules"])
def test_m5_every_store_read_failure_refuses_with_3(world, tmp_path, capsys, how):
    store, _repo, _base = world
    d = tmp_path / "clean"
    d.mkdir()
    (d / "a.txt").write_text("public\n")
    assert rn.main(["scan-dir", str(d)]) == 0                         # control: armed, readable
    _store_case(store, how)
    assert rn.main(["scan-dir", str(d)]) == 3
    assert "no verdict" in capsys.readouterr().out.splitlines()[-1]


# -- round 2 M4: the deciding values are needles; the packet is manifest-pinned ------

VALUE_PLANTS = [
    ("key_beside", "the late margin was 111 in that revision\n"),
    ("key_after", "a window of 222 window_ms\n"),
    ("threshold", "a threshold of 1777 decides it\n"),
    ("sign", "flag it when the count is > 333\n"),
    ("unit", "the edge span is 444 ms long\n"),
    ("fraction_pair", "the step band is 0.41/2.3\n"),
]


@pytest.mark.parametrize("name,text", VALUE_PLANTS, ids=[p[0] for p in VALUE_PLANTS])
def test_m4_a_planted_deciding_value_is_found(world, tmp_path, capsys, name, text):
    d = tmp_path / "scratch"
    d.mkdir()
    (d / "doc.md").write_text("generic prose about the evaluator\n")
    assert rn.main(["scan-dir", str(d)]) == 0                         # control
    (d / "doc.md").write_text("generic prose\n" + text)
    assert rn.main(["scan-dir", str(d)]) == 1
    out = capsys.readouterr().out.splitlines()[-1]
    assert "value=" in out and text.strip() not in out


def test_m4_control_values_without_a_deciding_form_and_code_are_not_value_hits(world, tmp_path):
    d = tmp_path / "scratch"
    d.mkdir()
    (d / "doc.md").write_text("at most 300 words; 111 rows in 7 files; 1777 is a year; 0 or 1 or -1\n")
    assert rn.main(["scan-dir", str(d)]) == 0
    (d / "code.py").write_text("if x > 333:\n    pass\n")             # source code: the guard's job
    assert rn.main(["scan-dir", str(d)]) == 0


def test_m4_a_message_carrying_a_value_is_found(world, tmp_path, capsys):
    msg = tmp_path / "msg.txt"
    msg.write_text("subject\n\nset the late margin to 111\n")
    assert rn.main(["message", str(msg)]) == 1
    assert "value=1" in capsys.readouterr().out


def test_m4_a_public_phrase_is_exempt_only_exactly(world, tmp_path):
    store, _repo, _base = world
    with open(os.path.join(store, "tests", "public.txt"), "w", encoding="utf-8") as f:
        f.write("# public mechanics\nretry at most > 333 times\n")
    d = tmp_path / "scratch"
    d.mkdir()
    (d / "doc.md").write_text("the client may retry at most > 333 times\n")
    assert rn.main(["scan-dir", str(d)]) == 0
    (d / "doc.md").write_text("the client may retry at most > 333 times; flag when > 333\n")
    assert rn.main(["scan-dir", str(d)]) == 1


def test_m4_a_pinned_document_carrying_a_value_is_found_in_the_packet(world, tmp_path, capsys):
    import hashlib
    _store, repo, base = world
    doc = tmp_path / "notes.md"
    doc.write_text("the review found a threshold of 1777\n")
    allow = tmp_path / "allow.txt"
    allow.write_text("a.txt\ndoc %s %s\n" % (doc, hashlib.sha256(doc.read_bytes()).hexdigest()))
    assert rn.main(["packet", repo, base, str(allow), str(tmp_path / "p")]) == 1
    assert "value=1" in capsys.readouterr().out


def test_m4_the_packet_manifest_pins_it_and_refuses_any_later_change(world, tmp_path, capsys):
    import hashlib
    _store, repo, base = world
    doc = tmp_path / "notes.md"
    doc.write_text("generic description of the evidence\n")
    allow = tmp_path / "allow.txt"
    allow.write_text("a.txt\ndoc %s %s\n" % (doc, hashlib.sha256(doc.read_bytes()).hexdigest()))
    out = tmp_path / "packet"
    assert rn.main(["packet", repo, base, str(allow), str(out)]) == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    digest = line.rsplit(" manifest ", 1)[1]
    assert hashlib.sha256((out / rn.MANIFEST).read_bytes()).hexdigest() == digest
    assert sorted(os.listdir(out)) == ["PACKET-MANIFEST.txt", "a.txt", "docs"]
    assert rn.main(["packet-verify", str(out), digest]) == 0              # control
    (out / "added.txt").write_text("added after the scan\n")
    assert rn.main(["packet-verify", str(out), digest]) == 1
    assert "packet_differs_from_its_manifest" in capsys.readouterr().out
    os.remove(out / "added.txt")
    assert rn.main(["packet-verify", str(out), digest]) == 0
    (out / "a.txt").write_text("changed after the scan\n")
    assert rn.main(["packet-verify", str(out), digest]) == 1
    assert rn.main(["packet-verify", str(out), "0" * 64]) == 1
    assert "manifest_digest_differs" in capsys.readouterr().out.splitlines()[-1]
