"""test_ft_notes.py: ft_notes.py's notes (ruling R6-A3.11.172 (5) b and c) on test_ft_parse.py's sitting fixtures.
Each note is held against the guard it stands beside: the f_hat note's extremes against vr2's own failure text, an
end-line note against disarms() and the VR6 row, and a line the guards do not exempt gets no note."""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ft_notes as N  # noqa: E402
import ft_parse as P  # noqa: E402
import test_ft_parse as T  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ft_notes.py")
QUIT = T.LOG_PREFIX + "[FRAME-TIME] refusals why=quit"


def _low(text, g, per_mille):
    """Game g's f_hat per_mille thousandths lower, on its settled line and on its calibration's fhat line."""
    out, n = [], 0
    for ln in text.splitlines():
        if " settled g=%d " % g in ln or " why=game%d kind=fhat " % g in ln:
            ln, k = re.subn(r" f_hat=(\d+)", lambda x: " f_hat=%d" % (int(x.group(1)) * (1000 - per_mille) // 1000), ln)
            n += k
        out.append(ln)
    assert n == 2, (g, n)
    return "\n".join(out)


def _zero(text, g):
    """Game g's settled line with f_hat=0 (that line alone: its calibration's fhat line stays as it is)."""
    out, n = [], 0
    for ln in text.splitlines():
        if " settled g=%d " % g in ln:
            ln, k = re.subn(r" f_hat=\d+", " f_hat=0", ln)
            n += k
        out.append(ln)
    assert n == 1, (g, n)
    return "\n".join(out)


def _disarm(why, pt):
    return T.LOG_PREFIX + "[FRAME-TIME] disarmed input=%s pt=%s" % (why, pt)


def _last_pt(text):
    p = [r for r in P.read(text) if r["kind"] == "p"][-1]
    assert p["game"] == P.LAST_GAME
    return p["pt"]


def test_fhat_note_gives_the_judged_extremes_and_names_what_is_left_out():
    v = T._v_text()
    base = [r["f_hat"] for r in P.read(v) if r["kind"] == "settled" and r["g"] == 1][0]
    note = N.fhat_note("a", P.read(v))
    assert note.startswith("V6 NOTE seat a: f_hat over the measured games (1 and up, %d values) %d..%d, spread 0.00 "
                           "percent of the lower (VR2 judges these, limit 2 percent); over every game from 0 (%d values, "
                           "the reading before ruling R6-A3.11.172 (5) b) %d..%d, spread 0.00 percent (within that "
                           "limit); not judged by VR2's spread: "
                           % (P.LAST_GAME, base, base, P.LAST_GAME + 1, base, base)), note
    assert "game 0 %d" % base in note.split("not judged by VR2's spread: ")[1], note
    # game 0 a tenth lower: outside the judged values, named as left out, and VR2's own row passes (the same rule).
    # The reading before .172 (5) b stands beside it: the spread from game 0 on, which that reading's own rule fails
    g0 = P.read(_low(v, 0, 100))
    note = N.fhat_note("a", g0)
    lo0 = base * 9 // 10
    assert " %d..%d, spread 0.00 percent of the lower " % (base, base) in note and "game 0 %d" % lo0 in note, note
    assert ("over every game from 0 (%d values, the reading before ruling R6-A3.11.172 (5) b) %d..%d, spread %.2f "
            "percent (over that limit)" % (P.LAST_GAME + 1, lo0, base, 100.0 * (base - lo0) / lo0)) in note, note
    assert P.vr2(g0, P.LAST_GAME, 1) == (True, [])
    assert P.vr2(g0, P.LAST_GAME, 0) == (False, ["f_hat spread %d..%d exceeds 2 percent" % (lo0, base)])
    # a measured game 1.5 percent lower: inside the limit, and the note prints VR2's own measure of it
    g5 = P.read(_low(v, 5, 15))
    note = N.fhat_note("a", g5)
    lo = base * 985 // 1000
    assert " %d..%d, spread %.2f percent " % (lo, base, 100.0 * (base - lo) / lo) in note, note
    assert P.vr2(g5, P.LAST_GAME, 1) == (True, [])
    # a measured game 3 percent lower: the note's two extremes are the ones VR2's failure text names
    g5 = P.read(_low(v, 5, 30))
    ok, bad = P.vr2(g5, P.LAST_GAME, 1)
    assert not ok and len(bad) == 1, bad
    ends = re.search(r"f_hat spread (\d+)\.\.(\d+) exceeds 2 percent", bad[0]).groups()
    assert " %s..%s, spread 3.09 percent " % ends in N.fhat_note("a", g5), (ends, N.fhat_note("a", g5))
    # no measured game prints one: said so, never a number
    none = "\n".join(ln for ln in v.splitlines() if " settled g=" not in ln or " settled g=0 " in ln)
    assert N.fhat_note("a", P.read(none)).startswith("V6 NOTE seat a: f_hat: no settled line of a measured game prints "
                                                     "one; not judged by VR2's spread: ")
    # a settled value that is not above 0 is never judged (vr2 reads the values above 0): it is named, whichever game
    # prints it, and it enters neither reading's count
    note = N.fhat_note("a", P.read(_zero(v, 0)))
    assert "game 0 0" in note.split("not judged by VR2's spread: ")[1], note
    assert "(1 and up, %d values)" % P.LAST_GAME in note and "from 0 (%d values, " % P.LAST_GAME in note, note
    note = N.fhat_note("a", P.read(_zero(v, 5)))
    left = note.split("not judged by VR2's spread: ")[1]
    assert "game 5 0" in left and "game 0 %d" % base in left, note
    assert "(1 and up, %d values)" % (P.LAST_GAME - 1) in note and "from 0 (%d values, " % P.LAST_GAME in note, note


def test_end_notes_stand_beside_the_exemption_for_the_seat_and_for_its_peer():
    v = T._v_text()
    last = _last_pt(v)
    own = T._insert_before(v, QUIT, _disarm("fighters", last))
    assert P.disarms(P.read(own)) == [] and P.disarms(P.read(own), True) == ["fighters at %s" % last]
    got = N.notes([("vm", own), ("laptop", v)])
    assert len(got) == 4 and got[0].startswith("V6 NOTE seat vm: f_hat ") and got[2].startswith(
        "V6 NOTE seat laptop: f_hat "), got
    assert got[1] == ("V6 NOTE seat vm: its disarm line 'fighters at %s' is the completed sitting's own end (ruling "
                      "R6-A3.11.172 (5) c): no VR6 failure" % last), got[1]
    assert got[3] == ("V6 NOTE seat laptop: the disarm line 'fighters at %s' of its peer vm is that sitting's own end: "
                      "no VR6 failure on this seat's row" % last), got[3]
    # the same two seats named the other way round: each note follows its seat
    back = N.notes([("laptop", v), ("vm", own)])
    assert back == [got[2], got[3], got[0], got[1]], back
    # a line the guard does not exempt gets no note: it stays VR6's failure (another input; the middle of the sitting)
    for bad in (T._insert_before(v, QUIT, _disarm("room", last)),
                T._insert_before(v, T.LOG_PREFIX + "[FRAME-TIME] settled g=9 ", _disarm("fighters", "8.1.1"))):
        assert len(P.disarms(P.read(bad))) == 1 and not P.vr6_build(P.read(bad))[0]
        assert [x for x in N.notes([("vm", bad), ("laptop", v)]) if "disarm line" in x] == [], bad[-300:]
    assert [x for x in N.notes([("vm", v), ("laptop", v)]) if "disarm line" in x] == []


def _run(*args):
    r = subprocess.run([sys.executable, "-I", "-B", SCRIPT] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def test_script_prints_the_notes_and_refuses_what_is_no_pair(tmp_path):
    v = T._v_text()
    own = T._insert_before(v, QUIT, _disarm("fighters", _last_pt(v)))
    a, b = tmp_path / "vm.log", tmp_path / "laptop.log"
    a.write_text(own + "\n", encoding="utf-8")
    b.write_text(v + "\n", encoding="utf-8")
    rc, out, err = _run("vm=%s" % a, "laptop=%s" % b)
    assert rc == 0 and out.splitlines() == N.notes([("vm", own), ("laptop", v)]) and not err, (rc, out, err)
    for args in (["vm=%s" % a], ["vm=%s" % a, "vm=%s" % b], ["%s" % a, "laptop=%s" % b], ["vm=", "laptop=%s" % b],
                 ["vm=%s" % a, "laptop=%s" % b, "third=%s" % b], []):
        rc, out, err = _run(*args)
        assert rc == 3 and out.startswith("REFUSED: NOTES: ft_notes.py takes exactly two seats"), (args, rc, out, err)
    rc, out, err = _run("vm=%s" % a, "laptop=%s" % (tmp_path / "absent.log"))
    assert rc == 3 and out.startswith("REFUSED: NOTES: a log cannot be read"), (rc, out, err)
    # a sitting input ft_parse refuses is refused here by the same reader (a control run's boot log is no sitting)
    k = tmp_path / "k1.log"
    k.write_text(T._v_text(boot={"controls": "controls k_mutant=k1", "alloc": T.K1_OUT}) + "\n", encoding="utf-8")
    rc, out, err = _run("vm=%s" % k, "laptop=%s" % b)
    assert rc == 3 and out.startswith("REFUSED: K-MUTANT: "), (rc, out, err)
