#!/usr/bin/env python3
"""ft_notes.py: the notes of ruling R6-A3.11.172 (5) b and c beside a sitting's report. Stdlib only.

Reported only: no verdict and no guard reads a line of this script. The guards are ft_parse.py's own (vr2's spread
check over the measured games; disarms() and the VR6 rows that read it). The notes show a reader of the report what
those two rules left out, so that nothing they exempt is exempt silently:

  f_hat    per seat: the settled f_hat values VR2's spread check judges (the measured games: the two extremes and
           their spread as a percent of the lower one, VR2's own measure); the same measure over every game from 0,
           the reading before that ruling, with its word against the same limit; and every value the check does
           not judge (each menu segment, each game before the first measured game, any value not above 0), named
           with its game.
  end line per seat: every disarm line that is the completed sitting's own end and so no VR6 failure (ft_parse's
           disarms(recs, True)), once for the seat that printed it and once on its peer's row.

Usage: python -I -B ft_notes.py <seat>=<sitting log> <seat>=<sitting log>
       (the two seats of one sitting, V or C, each by its name; the first measured game is 1, as ft_parse reads it)
Exit: 0 the notes printed; 3 REFUSED (the seats are not two, named and distinct, or ft_parse refuses a log as a
sitting input); 4 FT-PARSE REFUSED (ft_parse's record refusal, its own line).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ft_parse as P  # noqa: E402

FIRST_GAME = 1


def fhat_note(label, recs, first_game=FIRST_GAME):
    """The seat's f_hat line: what VR2's spread check judges; the same measure over every game from 0, the reading
    before ruling R6-A3.11.172 (5) b, so that both readings stand (a rule changed after its data); and every settled
    value the check does not judge, named with its game: each menu segment, each game before the first measured
    one, and any value that is not above 0 (the check reads values above 0 only)."""
    fh = [(r["g"], r.get("f_hat", 0)) for r in recs if r["kind"] == "settled"]
    judged = [v for g, v in fh if g >= first_game and v > 0]
    left = ", ".join("%s %d" % ("a menu segment" if g < 0 else "game %d" % g, v)
                     for g, v in fh if g < first_game or v <= 0)
    if not judged:
        return ("V6 NOTE seat %s: f_hat: no settled line of a measured game prints one; not judged by VR2's spread: %s"
                % (label, left or "none"))
    was = [v for g, v in fh if g >= 0 and v > 0]
    return ("V6 NOTE seat %s: f_hat over the measured games (%d and up, %d values) %d..%d, spread %.2f percent of the "
            "lower (VR2 judges these, limit 2 percent); over every game from 0 (%d values, the reading before ruling "
            "R6-A3.11.172 (5) b) %d..%d, spread %.2f percent (%s that limit); not judged by VR2's spread: %s"
            % (label, first_game, len(judged), min(judged), max(judged),
               100.0 * (max(judged) - min(judged)) / min(judged), len(was), min(was), max(was),
               100.0 * (max(was) - min(was)) / min(was),
               "over" if max(was) - min(was) > 0.02 * min(was) else "within", left or "none"))


def end_notes(label, recs, peer_label, peer_recs):
    """The seat's end-line notes: its own exempted disarm lines, then its peer's (the peer's row reads them too)."""
    out = ["V6 NOTE seat %s: its disarm line '%s' is the completed sitting's own end (ruling R6-A3.11.172 (5) c): no "
           "VR6 failure" % (label, d) for d in P.disarms(recs, True)]
    out += ["V6 NOTE seat %s: the disarm line '%s' of its peer %s is that sitting's own end: no VR6 failure on this "
            "seat's row" % (label, d, peer_label) for d in P.disarms(peer_recs, True)]
    return out


def notes(seats, first_game=FIRST_GAME):
    """seats: [(name, log text), (name, log text)]. The notes of both seats, in the order given."""
    (a, ta), (b, tb) = seats
    ra, rb = P.read_sitting(ta, "N:" + a), P.read_sitting(tb, "N:" + b)
    return ([fhat_note(a, ra, first_game)] + end_notes(a, ra, b, rb)
            + [fhat_note(b, rb, first_game)] + end_notes(b, rb, a, ra))


def pairs(args):
    """The two <seat>=<log> arguments as [(name, path), (name, path)], or Refused."""
    got = [x.split("=", 1) for x in args]
    if (len(got) != 2 or any(len(x) != 2 or not re.fullmatch(r"[A-Za-z0-9][\w.-]*", x[0]) or not x[1] for x in got)
            or got[0][0] == got[1][0]):
        raise P.Refused("NOTES: ft_notes.py takes exactly two seats, each as <seat>=<sitting log>, the names distinct "
                        "(got %s)" % list(args))
    return [(x[0], x[1]) for x in got]


if __name__ == "__main__":
    try:
        for line in notes([(n, open(p, encoding="utf-8", errors="replace").read()) for n, p in pairs(sys.argv[1:])]):
            print(line)
    except P.RecordRefused as e:
        print(str(e))
        sys.exit(P.REFUSED_RECORD_EXIT)
    except P.Refused as e:
        print("REFUSED: %s" % e)
        sys.exit(3)
    except OSError as e:
        print("REFUSED: NOTES: a log cannot be read (%s)" % e)
        sys.exit(3)
