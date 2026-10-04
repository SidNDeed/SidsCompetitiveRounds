"""The offline range list (conn_ranges): its loader's bounds and checks, the
classifier, the health word and the one-line refresh log.

Every list here is SYNTHETIC and names only documentation ranges (RFC 5737,
RFC 3849), so no test carries a real provider's range or anyone's address.
Rows S1, S2, S3 and Q3 of the build bar; report findings M2 and L12."""

import os
import socket
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))

import conn_ranges as cr  # noqa: E402

RANGES = ("# synthetic, documentation ranges only\n"
          "[hosting]\n203.0.113.0/25\n203.0.113.0/26\n"
          "[vpn]\n198.51.100.0/24\n"
          "[tor]\n2001:db8:1::/48\n")
SOURCES = "synthetic-a\t2026-10-01\t" + "a" * 64 + "\n"
SELFTEST = ("203.0.113.5\thosting\n203.0.113.200\tnone\n198.51.100.7\tvpn\n"
            "2001:db8:1::1\ttor\n192.0.2.1\tnone\n")


def _draft(tmp, ranges=RANGES, sources=SOURCES, selftest=SELFTEST, name="draft"):
    d = os.path.join(str(tmp), name)
    os.makedirs(d, exist_ok=True)
    for fn, body in (("ranges.txt", ranges), ("sources.txt", sources),
                     ("selftest.txt", selftest)):
        with open(os.path.join(d, fn), "w", encoding="ascii", newline="\n") as f:
            f.write(body)
    return d


def _store(tmp):
    s = os.path.join(str(tmp), "root")
    os.makedirs(s, exist_ok=True)
    return s


def _point(root, target):
    with open(os.path.join(root, cr.CR_POINTER), "w", encoding="ascii") as f:
        f.write(target + "\n")


@pytest.fixture
def fresh(monkeypatch, tmp_path):
    """A clean published state and a private root for each case."""
    root = _store(tmp_path)
    monkeypatch.setenv(cr.CR_ROOT_ENV, root)
    monkeypatch.setattr(cr, "_CR_STATE", cr.RangesState("absent"))
    monkeypatch.setattr(cr, "_CR_KEY", None)
    monkeypatch.setattr(cr, "_CR_LOGGED", None)
    return root


def _loaded(tmp_path, root, **draft):
    rev = cr.build_ranges_revision(_draft(tmp_path, **draft), root)
    _point(root, "ranges-" + rev)
    return rev, cr.refresh_ranges()


# -- loading and classifying ----------------------------------------------------

def test_s2_a_valid_revision_loads_classifies_and_names_itself(fresh, tmp_path):
    rev, st = _loaded(tmp_path, fresh)
    assert st.word == rev and cr.ranges_health_word() == rev and len(rev) == 12
    assert cr.classify_address("203.0.113.9") == ("hosting", rev)
    assert cr.classify_address("203.0.113.130") == ("none", rev)
    assert cr.classify_address("198.51.100.255") == ("vpn", rev)
    assert cr.classify_address("2001:db8:1:ffff::2") == ("tor", rev)
    assert cr.classify_address("::ffff:198.51.100.1") == ("vpn", rev)


@pytest.mark.parametrize("addr", ["10.1.2.3", "172.20.0.1", "192.168.72.102", "127.0.0.1",
                                  "169.254.9.9", "100.64.0.1", "::1", "fd00::5", "fe80::1%eth0"])
def test_s2_lan_comes_from_the_fixed_private_use_ranges(fresh, tmp_path, addr):
    rev, _st = _loaded(tmp_path, fresh)
    assert cr.classify_address(addr) == ("lan", rev)


@pytest.mark.parametrize("host", ["unknown", "", "not-an-address", None, 7, "300.1.1.1"])
def test_an_unparsable_host_is_unknown_and_never_raises(fresh, tmp_path, host):
    rev, _st = _loaded(tmp_path, fresh)
    assert cr.classify_address(host) == ("unknown", rev)


def test_l12_same_class_overlaps_merge_into_disjoint_intervals(fresh, tmp_path):
    _rev, st = _loaded(tmp_path, fresh)
    # 203.0.113.0/25 and /26 merge to one; the vpn and tor ranges stay one each
    assert st.table.intervals == 3
    ivs = list(zip(st.table.starts[4], st.table.ends[4]))
    assert all(a[1] < b[0] for a, b in zip(ivs, ivs[1:]))


@pytest.mark.parametrize("extra", ["[vpn]\n203.0.113.64/26\n", "[relay]\n203.0.113.0/25\n",
                                   "[tor]\n198.51.100.128/32\n"])
def test_l12_any_cross_class_overlap_refuses_the_revision(fresh, tmp_path, extra):
    _rev, st = _loaded(tmp_path, fresh, ranges=RANGES + extra)
    assert (st.word, st.reason) == ("refused", "overlap")
    assert cr.ranges_health_word() == "refused"
    assert cr.classify_address("203.0.113.9") == ("unknown", "refused")


def test_l12_adjacent_ranges_of_different_classes_are_not_an_overlap(fresh, tmp_path):
    rev, st = _loaded(tmp_path, fresh, ranges=RANGES + "[relay]\n203.0.113.128/25\n",
                      selftest=SELFTEST.replace("203.0.113.200\tnone", "203.0.113.200\trelay"))
    assert st.word == rev
    assert cr.classify_address("203.0.113.127")[0] == "hosting"
    assert cr.classify_address("203.0.113.128")[0] == "relay"


# -- refusals -------------------------------------------------------------------

@pytest.mark.parametrize("over,reason", [
    ({"selftest": SELFTEST.replace("203.0.113.5\thosting", "203.0.113.5\tvpn")}, "selftest_failed"),
    ({"selftest": SELFTEST + "8.8.8.8\tnone\n"}, "selftest_address"),
    ({"selftest": "203.0.113.5\thosting\n"}, "selftest"),
    ({"selftest": SELFTEST + "192.0.2.9\tunknown\n"}, "selftest"),
    ({"ranges": "203.0.113.0/24\n"}, "no_section"),
    ({"ranges": "[datacenter]\n203.0.113.0/24\n"}, "section"),
    ({"ranges": "[hosting]\n203.0.113.1/24\n"}, "cidr"),
    ({"sources": ""}, "sources"),
    ({"sources": "bad source line\n"}, "sources"),
])
def test_s2_a_revision_failing_a_check_is_refused_with_its_class(fresh, tmp_path, over, reason,
                                                                  capsys):
    _rev, st = _loaded(tmp_path, fresh, **over)
    assert (st.word, st.reason) == ("refused", reason)
    assert cr.ranges_health_word() == "refused"
    assert capsys.readouterr().out.strip() == "[RANGES] refused (%s)" % reason


def test_s1_a_corrupted_copy_is_refused_by_its_digest(fresh, tmp_path):
    rev, st = _loaded(tmp_path, fresh)
    assert st.word == rev
    path = os.path.join(fresh, "ranges-" + rev, "ranges.txt")
    with open(path, "a", encoding="ascii") as f:
        f.write("[hosting]\n192.0.2.0/24\n")
    # an immutable revision edited in place keeps its name: force the re-read
    # a changed directory would trigger (the fixture restores the key)
    cr._CR_KEY = None
    st = cr.refresh_ranges()
    assert (st.word, st.reason) == ("refused", "digest")
    assert cr.classify_address("203.0.113.9") == ("unknown", "refused")


def test_s1_nothing_staged_and_ranges_none_both_read_absent(fresh, tmp_path):
    assert cr.refresh_ranges().word == "absent"
    assert cr.classify_address("203.0.113.9") == ("unknown", "absent")
    rev, st = _loaded(tmp_path, fresh)
    assert st.word == rev
    _point(fresh, cr.CR_NONE_TARGET)
    assert cr.refresh_ranges().word == "absent"
    assert cr.ranges_health_word() == "absent"
    assert cr.classify_address("203.0.113.9") == ("unknown", "absent")


@pytest.mark.parametrize("target", ["ranges-XYZ", "../elsewhere", "ranges-0123456789ab"])
def test_s1_a_bad_or_missing_pointer_target_is_refused(fresh, target):
    _point(fresh, target)
    st = cr.refresh_ranges()
    assert (st.word, st.reason) == ("refused", "pointer")


def test_s2_an_extra_or_missing_file_is_refused(fresh, tmp_path):
    rev = cr.build_ranges_revision(_draft(tmp_path), fresh)
    rdir = os.path.join(fresh, "ranges-" + rev)
    with open(os.path.join(rdir, "extra.txt"), "w") as f:
        f.write("x")
    _point(fresh, "ranges-" + rev)
    st = cr.refresh_ranges()
    assert (st.word, st.reason) == ("refused", "inventory")


# -- M2: resource bounds ----------------------------------------------------------

@pytest.mark.parametrize("bound,value,reason,ranges", [
    ("ranges_bytes_max", 40, "bytes", RANGES),
    ("lines_max", 4, "lines", RANGES),
    ("entries_max", 2, "entries", RANGES),
    ("intervals_max", 2, "intervals", RANGES),
    ("line_bytes_max", 10, "line", RANGES),
])
def test_m2_every_bound_refuses_a_revision_over_it(fresh, tmp_path, monkeypatch, bound, value,
                                                   reason, ranges):
    rev = cr.build_ranges_revision(_draft(tmp_path, ranges=ranges), fresh)
    monkeypatch.setitem(cr.CR_BOUNDS, bound, value)
    _point(fresh, "ranges-" + rev)
    st = cr.refresh_ranges()
    assert (st.word, st.reason) == ("refused", reason)


def test_m2_the_bounds_hold_a_control_just_inside_them(fresh, tmp_path, monkeypatch):
    rev = cr.build_ranges_revision(_draft(tmp_path), fresh)
    monkeypatch.setitem(cr.CR_BOUNDS, "entries_max", 4)
    monkeypatch.setitem(cr.CR_BOUNDS, "intervals_max", 3)
    _point(fresh, "ranges-" + rev)
    assert cr.refresh_ranges().word == rev


def test_m2_the_load_deadline_refuses(fresh, tmp_path, monkeypatch):
    rev = cr.build_ranges_revision(_draft(tmp_path), fresh)
    monkeypatch.setitem(cr.CR_BOUNDS, "deadline_s", -1)
    _point(fresh, "ranges-" + rev)
    st = cr.refresh_ranges()
    assert (st.word, st.reason) == ("refused", "deadline")


def test_m2_a_load_in_progress_answers_the_published_state(fresh, tmp_path):
    rev, st = _loaded(tmp_path, fresh)
    assert cr._CR_LOCK.acquire(blocking=False)
    try:
        _point(fresh, cr.CR_NONE_TARGET)
        assert cr.refresh_ranges() is st
        assert cr.ranges_health_word() == rev
    finally:
        cr._CR_LOCK.release()
    assert cr.refresh_ranges().word == "absent"


def test_m2_a_request_never_loads(fresh, tmp_path, monkeypatch):
    """classify_address and the health word read the published state only."""
    rev = cr.build_ranges_revision(_draft(tmp_path), fresh)
    _point(fresh, "ranges-" + rev)
    calls = []
    monkeypatch.setattr(cr, "load_ranges_dir", lambda *a, **k: calls.append(a))
    assert cr.classify_address("203.0.113.9") == ("unknown", "absent")
    assert cr.ranges_health_word() == "absent"
    assert calls == []


# -- S3 / Q3: the address goes nowhere, nothing is fetched ---------------------------

def test_s3_q3_classifying_prints_nothing_and_opens_no_socket(fresh, tmp_path, monkeypatch,
                                                              capsys):
    rev, _st = _loaded(tmp_path, fresh)
    capsys.readouterr()

    def refuse(*a, **k):
        raise AssertionError("a socket was opened")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    hosts = ("203.0.113.77", "198.51.100.77", "2001:db8:1::77", "192.0.2.77", "bogus-host")
    for host in hosts:
        cr.classify_address(host)
    # the reload of a changed list opens no socket either
    rev2 = cr.build_ranges_revision(_draft(tmp_path, ranges=RANGES + "[relay]\n192.0.2.128/25\n",
                                           name="d2"), fresh)
    _point(fresh, "ranges-" + rev2)
    assert cr.refresh_ranges().word == rev2
    out = capsys.readouterr()
    assert not [h for h in hosts if h in out.out + out.err]
    assert out.out.strip() == "[RANGES] " + rev2


def test_s3_positive_control_the_scan_finds_a_planted_address(capsys):
    print("planted 203.0.113.77")
    out = capsys.readouterr()
    assert "203.0.113.77" in out.out


def test_the_refresh_log_is_one_line_per_change(fresh, tmp_path, capsys):
    rev, _st = _loaded(tmp_path, fresh)
    for _ in range(3):
        cr.refresh_ranges()
    assert capsys.readouterr().out.strip().splitlines() == ["[RANGES] " + rev]


def test_the_build_tool_refuses_to_overwrite_a_revision(fresh, tmp_path):
    cr.build_ranges_revision(_draft(tmp_path), fresh)
    with pytest.raises(FileExistsError):
        cr.build_ranges_revision(_draft(tmp_path), fresh)


def test_a_large_synthetic_list_loads_inside_the_deadline(fresh, tmp_path):
    """Scale control for M2: 60000 disjoint /32s of one documentation /16
    equivalent (generated inside 2001:db8::/32) compile within the bound."""
    lines = ["[hosting]"] + ["2001:db8:2:%x::/64" % i for i in range(60000)]
    t = time.monotonic()
    rev, st = _loaded(tmp_path, fresh, ranges="\n".join(lines) + "\n",
                      selftest=SELFTEST.replace("2001:db8:1::1\ttor", "2001:db8:2:5::1\thosting"))
    assert st.word == rev, st.reason
    assert time.monotonic() - t < cr.CR_BOUNDS["deadline_s"]
    assert cr.classify_address("2001:db8:2:ea5f::9")[0] == "hosting"
    assert cr.classify_address("2001:db8:3::9")[0] == "none"
