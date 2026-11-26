"""The region reader (api/geo_region.py) against stand-in files.

No database, no network. Every file is written by tests/mmdb_standin.py with
invented place names, for the public resolver addresses alone. In every
case a fixture counts the descriptors the module opens and closes through
its own alias of os, and the two are equal after each call.
"""
import ast
import logging
import os
import sys
import threading
import types
from pathlib import Path

import pytest

import geo_region as G
import mmdb_standin as S

V4 = "1.1.1.1"
V4_B = "1.0.0.1"
V4_NONE = "8.8.8.8"
V6 = "2606:4700:4700::1111"
V6_B = "2606:4700:4700::1001"

CITY, POSTCODE, LAT, LON = "Quillbrook", "QX7 9ZZ", 12.375, -45.625


class _CountingOs:
    """The module's os alias, counting the descriptors it opens and closes.
    `short_at`: the read that starts at this offset returns one byte less.
    `size_cut`: fstat reports this size instead of the file's."""

    def __init__(self, real):
        self._real = real
        self._lock = threading.Lock()
        self.opened = 0
        self.closed = 0
        self.short_at = None
        self.size_cut = None
        self._pos = threading.local()

    def __getattr__(self, name):
        return getattr(self._real, name)

    def open(self, *a, **k):
        fd = self._real.open(*a, **k)
        with self._lock:
            self.opened += 1
        return fd

    def close(self, fd):
        self._real.close(fd)
        with self._lock:
            self.closed += 1

    def lseek(self, fd, off, how):
        self._pos.at = off
        return self._real.lseek(fd, off, how)

    def read(self, fd, n):
        got = self._real.read(fd, n)
        if self.short_at is not None and getattr(self._pos, "at", None) == self.short_at and got:
            return got[:-1]
        return got

    def fstat(self, fd):
        st = self._real.fstat(fd)
        if self.size_cut is None:
            return st
        return types.SimpleNamespace(st_mode=st.st_mode, st_dev=st.st_dev, st_ino=st.st_ino,
                                     st_size=self.size_cut, st_mtime_ns=st.st_mtime_ns)


@pytest.fixture(autouse=True)
def osc(tmp_path, monkeypatch):
    folder = tmp_path / "geo"
    folder.mkdir()
    counting = _CountingOs(os)
    monkeypatch.setattr(G, "_rgn_DIR", str(folder))
    monkeypatch.setattr(G, "_rgn_os", counting)
    monkeypatch.setattr(G, "_rgn_kept", None)
    counting.folder = folder
    yield counting
    assert counting.opened == counting.closed


def region(osc, host):
    got = G.region_of(host)
    assert osc.opened == osc.closed
    assert isinstance(got, str)
    return got


def word(osc):
    got = G.file_word()
    assert osc.opened == osc.closed
    return got


def put(osc, data, name="region.mmdb"):
    if isinstance(data, S.Built):
        data = data.data
    (osc.folder / name).write_bytes(data)
    return osc.folder / name


def _traced(fn, *args):
    """fn's answer, and the text of every exception raised while it ran."""
    seen = []

    def tracer(frame, event, arg):
        if event == "exception":
            seen.append(repr(arg[1]) + " " + repr(getattr(arg[1], "args", ())))
        return tracer

    old = sys.gettrace()
    sys.settrace(tracer)
    try:
        out = fn(*args)
    finally:
        sys.settrace(old)
    return out, seen


def _values(v):
    """The values a record holds by the specification's flat rule."""
    if isinstance(v, dict):
        return 1 + sum(1 + _values(x) for x in v.values())
    if isinstance(v, list):
        return 1 + sum(_values(x) for x in v)
    return 1


# -- the answers ----------------------------------------------------------------

def test_country_and_subdivision(osc):
    put(osc, S.build([(V4, S.place("Ardenmark", "Vellshire"))]))
    assert region(osc, V4) == "Ardenmark, Vellshire"


def test_country_alone(osc):
    put(osc, S.build([(V4, S.place("Ardenmark")),
                      (V6, S.place("Brynmoor", subdivisions=[]))]))
    assert region(osc, V4) == "Ardenmark"
    assert region(osc, V6) == "Brynmoor"


def test_no_record(osc):
    put(osc, S.build([(V4, S.place("Ardenmark", "Vellshire")), (V6, S.place("Brynmoor"))]))
    assert region(osc, V4_NONE) == ""
    assert region(osc, V6_B) == ""


def test_a_record_without_a_country_name(osc):
    put(osc, S.build([(V4, {"subdivisions": [{"names": {"en": "Vellshire"}}]}),
                      (V4_B, {"country": {"names": {"de": "Ardenmark"}}}),
                      (V6, {"country": {"names": {"en": 7}}}),
                      (V6_B, ["Ardenmark"])]))
    for host in (V4, V4_B, V6, V6_B):
        assert region(osc, host) == ""


@pytest.mark.parametrize("host", ["not-an-address", "", " 1.1.1.1", "1.1.1.1/32", "300.1.1.1",
                                  None, 7, b"1.1.1.1", ["1.1.1.1"]])
def test_a_text_that_is_no_address(osc, host):
    put(osc, S.build([(V4, S.place("Ardenmark", "Vellshire"))]))
    assert region(osc, host) == ""


def test_ipv4_address_in_an_ipv6_file(osc):
    put(osc, S.build([(V4, S.place("Ardenmark", "Vellshire")), (V6, S.place("Brynmoor", "Tallfen"))],
                     ip_version=6))
    assert region(osc, V4) == "Ardenmark, Vellshire"
    assert region(osc, V6) == "Brynmoor, Tallfen"


def test_ipv4_address_in_an_ipv4_file(osc):
    put(osc, S.build([(V4, S.place("Ardenmark", "Vellshire")), (V4_B, S.place("Brynmoor"))], ip_version=4))
    assert region(osc, V4) == "Ardenmark, Vellshire"
    assert region(osc, V4_B) == "Brynmoor"


def test_ipv6_address_in_an_ipv4_file(osc):
    put(osc, S.build([(V4, S.place("Ardenmark", "Vellshire"))], ip_version=4))
    assert region(osc, V6) == ""
    assert region(osc, V4) == "Ardenmark, Vellshire"


@pytest.mark.parametrize("record_size", [24, 28, 32])
def test_each_record_size(osc, record_size):
    # Two neighbours whose last bit differs, so a left and a right record
    # of one node both lead to data.
    put(osc, S.build([("1.1.1.2", S.place("Ardenmark")), ("1.1.1.3", S.place("Brynmoor", "Tallfen")),
                      (V6, S.place("Corvale", "Dunmere"))], record_size=record_size))
    assert region(osc, "1.1.1.2") == "Ardenmark"
    assert region(osc, "1.1.1.3") == "Brynmoor, Tallfen"
    assert region(osc, V6) == "Corvale, Dunmere"
    assert region(osc, V4) == ""


@pytest.mark.parametrize("record_size", [28, 32])
def test_record_values_above_24_bits(osc, record_size):
    built = S.build([("1.1.1.2", S.place("Ardenmark")), ("1.1.1.3", S.place("Brynmoor", "Tallfen"))],
                    record_size=record_size, lead_pad=1 << 24)
    put(osc, built)
    assert region(osc, "1.1.1.2") == "Ardenmark"
    assert region(osc, "1.1.1.3") == "Brynmoor, Tallfen"


def test_a_record_reached_through_a_pointer_and_names_stored_by_pointer(osc):
    names = S.Pairs([(S.Ptr("en"), S.Ptr("Ardenmark")), ("de", S.Ptr("Ardenmark-de"))])
    rec = S.Ptr(S.Pairs([(S.Ptr("country"), S.Ptr({"names": S.Ptr(names)})),
                         ("subdivisions", S.Ptr([S.Ptr({"names": S.Ptr({"en": "Vellshire"})})]))]))
    put(osc, S.build([(V4, rec)]))
    # The subdivision's name lies 8 deep: the record's pointer, its map,
    # the array's pointer, the array, the element's pointer, the element,
    # the names' pointer, the names.
    assert region(osc, V4) == "Ardenmark, Vellshire"


@pytest.mark.parametrize("form,lead", [(0, 0), (1, 2048), (2, 526336), (3, 0)])
def test_each_pointer_form(osc, form, lead):
    rec = {"country": S.Ptr({"names": {"en": S.Ptr("Ardenmark", form)}}, form)}
    put(osc, S.build([(V4, rec)], lead_pad=lead))
    assert region(osc, V4) == "Ardenmark"


def test_city_postcode_and_location_never_leave(osc, caplog):
    caplog.set_level(logging.DEBUG)
    full = S.place("Ardenmark", "Vellshire",
                   city={"geoname_id": 77, "names": {"en": CITY, "de": CITY + "-de"}},
                   postal={"code": POSTCODE},
                   location={"latitude": LAT, "longitude": LON, "accuracy_radius": 20})
    broken = dict(full, x=[0] * 400)
    put(osc, S.build([(V4, full), (V4_B, broken)]))
    texts = []
    for host in (V4, V4_B):
        got, seen = _traced(G.region_of, host)
        assert osc.opened == osc.closed
        texts += [got] + seen
    got, seen = _traced(G.file_word)
    texts += [got] + seen
    assert texts[0] == "Ardenmark, Vellshire"
    for t in texts + [caplog.text] + [r.getMessage() for r in caplog.records]:
        for secret in (CITY, POSTCODE, repr(LAT), repr(LON), "Quill"):
            assert secret not in t
    assert caplog.records == []


def test_control_characters_are_taken_out(osc):
    put(osc, S.build([(V4, S.place("Arden\x00mark\x1b\x7f\x85\x9f", "Vell\nshire\t")),
                      (V4_B, S.place("\x01" * 10 + "B" * 60))]))
    assert region(osc, V4) == "Ardenmark, Vellshire"
    # Taken out first, then cut: sixty letters stand, not fifty.
    assert region(osc, V4_B) == "B" * 60


def test_a_name_over_60_characters_is_cut(osc):
    put(osc, S.build([(V4, S.place("A" * 70, "é" * 61)), (V4_B, S.place("C" * 60, "D" * 59))]))
    assert region(osc, V4) == "A" * 60 + ", " + "é" * 60
    assert region(osc, V4_B) == "C" * 60 + ", " + "D" * 59


def test_a_name_over_200_bytes(osc):
    put(osc, S.build([(V4, S.place("C" * 201)), (V4_B, S.place("C" * 200)),
                      (V6, S.place("Ardenmark", "S" * 201)), (V6_B, S.place("é" * 101))]))
    assert region(osc, V4) == ""
    assert region(osc, V4_B) == "C" * 60
    assert region(osc, V6) == ""
    assert region(osc, V6_B) == ""


def test_a_map_key_over_200_bytes(osc):
    put(osc, S.build([(V4, S.place("Ardenmark", **{"k" * 201: 1})), (V4_B, S.place("Brynmoor", **{"k" * 200: 1}))]))
    assert region(osc, V4) == ""
    assert region(osc, V4_B) == "Brynmoor"


def test_a_long_name_in_another_language_beside_a_short_english_one(osc):
    names = {"de": "L" * 70000, "fr": "M" * 300, "es": "N" * 100, "en": "Ardenmark", "ja": "山" * 400}
    put(osc, S.build([(V4, {"country": {"names": names},
                            "subdivisions": [{"names": {"de": "W" * 500, "en": "Vellshire"}}],
                            "city": {"names": {"en": "Z" * 5000}}})]))
    assert region(osc, V4) == "Ardenmark, Vellshire"


def test_every_other_type_is_passed_over_by_its_length(osc):
    rec = S.place("Ardenmark", "Vellshire", b=b"\x00\x01" * 40, d=2.5, f=S.F32(1.5), u16=S.Uint(65535, 5),
                  u64=S.Uint(2 ** 63, 9), u128=S.Uint(2 ** 127, 10), i32=S.Uint(2 ** 31, 8),
                  t=True, n=False, m={}, a=[], zero=S.Uint(0, 6))
    put(osc, S.build([(V4, rec)]))
    assert region(osc, V4) == "Ardenmark, Vellshire"


@pytest.mark.parametrize("raw", [bytes([0x00, 0x05]), bytes([0x00, 0x06]), bytes([0x00, 0x09]),
                                 bytes([0x00, 0x00])])
def test_a_type_that_cannot_stand_in_a_record(osc, raw):
    # 12 and 13 (deprecated), an extended type above 15, and an extended
    # byte of 0 (a type below 8).
    put(osc, S.build([(V4, S.place("Ardenmark", x=S.Raw(raw)))]))
    assert region(osc, V4) == ""


# -- damaged files ----------------------------------------------------------------

def _full():
    return S.build([(V4, S.place("Ardenmark", "Vellshire")), (V6, S.place("Brynmoor"))])


@pytest.mark.parametrize("where", ["metadata", "tree", "data"])
def test_a_cut_file(osc, where):
    b = _full()
    end = {"metadata": b.marker_at + len(S.MARKER) + 20, "tree": b.tree_size // 2,
           "data": b.data_start + 3}[where]
    put(osc, b.data[:end])
    assert region(osc, V4) == ""
    assert word(osc) == "refused"


def test_an_empty_file(osc):
    put(osc, b"")
    assert region(osc, V4) == ""
    assert word(osc) == "refused"


def test_a_file_with_no_marker(osc):
    b = _full()
    put(osc, b.data.replace(S.MARKER, b"\xab\xcd\xefNotTheMark"))
    assert region(osc, V4) == ""
    assert word(osc) == "refused"


def test_a_pointer_to_itself(osc):
    def self_map(at):
        lead = S.head(7, 1) + S._Section().encode("country")
        return lead + S.pointer(at + len(lead), 3)
    put(osc, S.build([(V4, S.Raw(lambda at: S.pointer(at, 3))), (V4_B, S.Raw(self_map)),
                      (V6, S.place("Brynmoor"))]))
    assert region(osc, V4) == ""
    assert region(osc, V4_B) == ""
    assert region(osc, V6) == "Brynmoor"


def _chain(levels):
    """A record whose deepest value lies `levels` deep (maps and pointers
    together, the record's own map the first)."""
    def below(n, ptr):
        if n == 0:
            return "end"
        return S.Ptr(below(n - 1, False)) if ptr else {"x": below(n - 1, True)}
    return S.place("Ardenmark", x=below(levels - 1, True))


def test_a_chain_nine_deep(osc):
    put(osc, S.build([(V4, _chain(9)), (V4_B, _chain(8))]))
    assert region(osc, V4) == ""
    assert region(osc, V4_B) == "Ardenmark"


def test_a_record_of_401_values(osc):
    def rec(k):
        return {"country": {"names": {"en": "Ardenmark"}}, "x": [0] * k}
    assert _values(rec(391)) == 400 and _values(rec(392)) == 401
    put(osc, S.build([(V4, rec(392)), (V4_B, rec(391)),
                      (V6, {"country": {"names": {"en": "Brynmoor"}}, "x": S.Ptr(list(range(392)))})]))
    assert region(osc, V4) == ""
    assert region(osc, V4_B) == "Ardenmark"
    assert region(osc, V6) == ""


def _settled(path):
    """Set the file's mtime a minute back, past the reader's settle margin, so its parse is kept."""
    st = os.stat(path)
    back = st.st_mtime_ns - 60 * 10 ** 9
    os.utime(path, ns=(back, back))


def test_the_kept_metadata_never_changes_an_answer(osc):
    # The record's decode has its own budget of 400 values and the
    # metadata's its own: the call that reads the metadata and the next
    # call, which uses the kept value, answer the same record alike.
    def rec(k):
        return {"country": {"names": {"en": "Ardenmark"}}, "x": [0] * k}
    _settled(put(osc, S.build([(V4, rec(392)), (V4_B, rec(391))])))
    for host, want in ((V4_B, "Ardenmark"), (V4, "")):
        G._rgn_kept = None
        assert region(osc, host) == want
        kept = G._rgn_kept
        assert kept is not None
        assert region(osc, host) == want
        assert G._rgn_kept is kept                # the second call used the kept value


def _rewrite_in_one_tick(path, data):
    """Rewrite the file in place and give it back the mtime it had, as a
    rewrite inside one tick of the file system's timestamp clock leaves it:
    the device, the inode, the size and mtime_ns all stay."""
    st = os.stat(path)
    with open(path, "r+b") as fh:
        fh.write(data)
        fh.truncate()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    after = os.stat(path)
    assert (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) == \
        (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def test_a_rewrite_in_place_inside_one_timestamp_tick_is_read_again(osc, monkeypatch):
    """ALT-BAN-1 fix 3, F3-D: the stand-in files of two build months are of
    one size, so a rewrite in place inside one timestamp tick keeps the
    whole key of the kept parse. A parse is kept only when the file's mtime
    is at least _rgn_SETTLE_NS before it, so the reader reads such a
    rewrite again. With the margin at 0 (every parse kept, the reader as it
    was) the same rewrite is answered with the old month."""
    nov = S.build([(V4, S.place("Ardenmark"))], build_epoch=1795000000).data
    dec = S.build([(V4, S.place("Ardenmark"))], build_epoch=1798761599).data
    assert len(nov) == len(dec)
    path = put(osc, nov)
    assert word(osc) == "2026-11"
    _rewrite_in_one_tick(path, dec)
    assert word(osc) == "2026-12"
    assert region(osc, V4) == "Ardenmark"
    # The old shape, inside the case: every parse kept.
    monkeypatch.setattr(G, "_rgn_SETTLE_NS", 0)
    monkeypatch.setattr(G, "_rgn_kept", None)
    _rewrite_in_one_tick(path, nov)
    assert word(osc) == "2026-11"
    _rewrite_in_one_tick(path, dec)
    assert word(osc) == "2026-11", "with every parse kept, the rewrite is to be answered from the kept parse"


def _nest(levels):
    return "end" if levels == 0 else {"a": _nest(levels - 1)}


@pytest.mark.parametrize("change", [
    lambda pairs: pairs + [("k" * 201, 1)],
    lambda pairs: pairs + [("languages_more", ["en"] * 400)],
    lambda pairs: pairs + [("nested", _nest(8))],
], ids=["key_over_200_bytes", "values_over_400", "depth_nine"])
def test_a_metadata_past_a_bound(osc, change):
    put(osc, S.build([(V4, S.place("Ardenmark"))], meta=change))
    assert word(osc) == "refused"
    assert region(osc, V4) == ""


def test_a_metadata_inside_the_bounds_beside_them(osc):
    # 23 values of its own, 16 nested 8 deep, 2 for the long key and a
    # text passed over by its length, 302 for the list: 343 in all.
    def change(pairs):
        return pairs + [("languages_more", ["en"] * 300), ("nested", _nest(7)), ("k" * 200, "D" * 5000)]
    put(osc, S.build([(V4, S.place("Ardenmark"))], meta=change))
    assert word(osc) == "2027-01"
    assert region(osc, V4) == "Ardenmark"


def test_a_file_replaced_by_another_of_the_same_size(osc):
    def two(pad_a, pad_b):
        a = S.build([(V4, S.place("Ardenmark", "Vellshire"))], record_size=24, tail_pad=pad_a)
        b = S.build([(V4, S.place("Brynmoor", "Tallfen"))], record_size=28, build_epoch=1795000000,
                    tail_pad=pad_b)
        return a, b
    a, b = two(0, 0)
    diff = len(a.data) - len(b.data)
    a, b = two(max(0, -diff), max(0, diff))
    assert len(a.data) == len(b.data)
    path = put(osc, a)
    assert region(osc, V4) == "Ardenmark, Vellshire"
    assert word(osc) == "2027-01"
    nxt = put(osc, b, "region.mmdb.next")
    os.replace(nxt, path)
    assert region(osc, V4) == "Brynmoor, Tallfen"
    assert word(osc) == "2026-11"


def test_the_folder_absent(osc, monkeypatch):
    monkeypatch.setattr(G, "_rgn_DIR", str(osc.folder / "missing"))
    assert region(osc, V4) == ""
    assert word(osc) == "absent"


def test_the_file_absent(osc):
    put(osc, _full(), "other.mmdb")
    assert region(osc, V4) == ""
    assert word(osc) == "absent"


def test_a_folder_at_the_files_name(osc):
    (osc.folder / "region.mmdb").mkdir()
    assert region(osc, V4) == ""
    assert word(osc) == "refused"


def test_file_words_three_answers(osc, monkeypatch):
    assert word(osc) == "absent"
    put(osc, b"not the format")
    assert word(osc) == "refused"
    put(osc, S.build([(V4, S.place("Ardenmark"))], build_epoch=1795000000))
    assert word(osc) == "2026-11"
    put(osc, S.build([(V4, S.place("Ardenmark"))], build_epoch=1798761599))
    assert word(osc) == "2026-12"
    put(osc, S.build([(V4, S.place("Ardenmark"))], build_epoch=1798761600))
    assert word(osc) == "2027-01"


def _meta_with(name, value):
    def change(pairs):
        return [(k, value if k == name else v) for k, v in pairs]
    return change


@pytest.mark.parametrize("change", [
    _meta_with("record_size", S.Uint(20, 5)),
    _meta_with("ip_version", S.Uint(5, 5)),
    _meta_with("binary_format_major_version", S.Uint(3, 5)),
    _meta_with("node_count", "many"),
    lambda pairs: [p for p in pairs if p[0] != "node_count"],
    lambda pairs: pairs + [("ip_version", S.Uint(6, 5))],
], ids=["record_size", "ip_version", "major", "node_count_text", "no_node_count", "repeated_key"])
def test_a_metadata_value_outside_what_the_reader_supports(osc, change):
    put(osc, S.build([(V4, S.place("Ardenmark"))], meta=change))
    assert word(osc) == "refused"
    assert region(osc, V4) == ""


def test_a_build_epoch_past_the_calendar(osc):
    # The lookup needs no month; file_word has none to give.
    put(osc, S.build([(V4, S.place("Ardenmark"))], build_epoch=2 ** 64 - 1))
    assert word(osc) == "refused"
    assert region(osc, V4) == "Ardenmark"


def test_a_read_that_returns_fewer_bytes_ends_the_call(osc):
    b = S.build([(V4, S.place("Ardenmark"))])
    put(osc, b)
    osc.short_at = b.data.index(b"Ardenmark")
    assert region(osc, V4) == ""
    osc.short_at = 0 if len(b.data) <= G._rgn_META_MAX else len(b.data) - G._rgn_META_MAX
    G._rgn_kept = None
    assert word(osc) == "refused"
    osc.short_at = None
    assert region(osc, V4) == "Ardenmark"


def test_every_read_lies_inside_the_calls_fstat_size(osc):
    def make(target):
        return S.build([(V4, {"country": {"names": {"en": S.PtrTo(target)}}}), (V6, S.place("Brynmoor"))])
    first = make(0)
    b = make(len(first.data) - first.data_start)
    assert len(b.data) == len(first.data)
    put(osc, b.data + S._Section().encode("Farreach"))
    assert region(osc, V4) == "Farreach"
    # The file as the call's fstat sees it ends where the pointer's target
    # begins (the file grew after the fstat).
    osc.size_cut = len(b.data)
    G._rgn_kept = None
    assert region(osc, V4) == ""
    assert region(osc, V6) == "Brynmoor"


def test_two_threads_at_once_on_one_file(osc):
    put(osc, S.build([(V4, S.place("Ardenmark", "Vellshire")), (V6, S.place("Brynmoor"))]))
    single = {h: G.region_of(h) for h in (V4, V6, V4_NONE)}
    assert single[V4] == "Ardenmark, Vellshire" and single[V6] == "Brynmoor" and single[V4_NONE] == ""
    G._rgn_kept = None
    start = threading.Barrier(2)
    answers = [[], []]

    def run(slot):
        start.wait()
        for i in range(150):
            h = (V4, V6, V4_NONE)[i % 3]
            answers[slot].append((h, G.region_of(h)))
            if i % 50 == 0:
                answers[slot].append(("word", G.file_word()))

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not any(t.is_alive() for t in threads)
    for got in answers:
        assert len(got) == 153
        for h, a in got:
            assert a == ("2027-01" if h == "word" else single[h])
    assert osc.opened == osc.closed


# -- names: no module-level name of geo_region.py is spelled by another api module --
# The same method as test_alt_signals_pure.py (the route-manifest gate folds a
# bare name of every api module into the fingerprint of each route spelling it).

API_DIR = Path(__file__).resolve().parents[1] / "api"


def _module_level_names(source):
    names = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
    return names


def _spelled_names(source):
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


def _clashes(mine, others):
    return {name: sorted(fn for fn, spelled in others.items() if name in spelled)
            for name in sorted(mine) if any(name in spelled for spelled in others.values())}


def test_no_module_level_name_is_spelled_by_another_api_module():
    source = (API_DIR / "geo_region.py").read_text(encoding="utf-8")
    mine = _module_level_names(source)
    assert {"_rgn_os", "_rgn_ipaddress", "_rgn_datetime", "_rgn_stat", "_rgn_DIR",
            "_rgn_kept", "region_of", "file_word"} <= mine, sorted(mine)
    assert all(n.startswith("_rgn_") for n in mine - {"region_of", "file_word"}), sorted(mine)
    imported = [(a.name, a.asname) for node in ast.parse(source).body
                if isinstance(node, (ast.Import, ast.ImportFrom)) for a in node.names]
    assert sorted(imported) == [("datetime", "_rgn_datetime"), ("ipaddress", "_rgn_ipaddress"),
                                ("os", "_rgn_os"), ("stat", "_rgn_stat")]
    others = {p.name: _spelled_names(p.read_text(encoding="utf-8"))
              for p in sorted(API_DIR.glob("*.py")) if p.name != "geo_region.py"}
    assert len(others) >= 30, sorted(others)
    assert _clashes(mine, others) == {}


def test_the_spelling_check_finds_a_plain_import_and_a_shared_name():
    others = {"x.py": _spelled_names("import os\n\ndef region_of(h):\n    return os.sep\n")}
    mine = _module_level_names("import os\nimport stat as _s\n\ndef region_of(host):\n    return host\n")
    assert _clashes(mine, others) == {"os": ["x.py"], "region_of": ["x.py"]}
