"""Mechanical privacy sweep over the artifacts a review pin carries.

Round 2 of bug 392 closed its privacy row with "0 hits" from a script that
lived outside the worktree, so the row's only witness was the session that ran
it. This file is that sweep, in the tree, with its own negative control.

FIVE CLASSES
  user-path              a path under a user home directory, in either
                         separator: a drive letter followed by the users
                         directory, or the two posix forms of the same thing.
  private-address        an RFC1918 address. The loopback test DSN is allowed
                         BY EXACT FORM so the allowance cannot widen into
                         "anything on loopback".
  steam-id               a SteamID64: the 7656119 prefix and ten more digits.
  deployment-identifier  by SHAPE -- a login target (an account name, the at
                         sign, a host), a five-field cron line, an
                         orchestration command -- plus any wordlist term.
  handle                 a person's handle. Terms only; there is no shape.

WHY TWO CLASSES COME FROM A FILE AND NOT FROM HERE
  A detector that hardcodes the strings it looks for reproduces them. That is
  the same defect as a scanner that echoes its findings (#756) -- the tool
  whose job is to stop a handle or a host name from travelling would carry
  them itself, into the tree and into every pin. So the two classes that have
  no shape are driven by a wordlist that lives OUTSIDE the repository, and a
  run that has not been given one says so and exits 2. A green run that
  silently skipped two of its five classes is worse than no run (#342).

  Wordlist format, one per line, `class:term`, `#` comments ignored:
      handle:some-handle
      deployment-identifier:some-host-name

WHAT IT PRINTS
  `file:line: class` -- the class and the location, never the matched text.
  The reader opens the named file at the named line. A report that quotes what
  it found copies the thing into the evidence it was protecting (#756).

  The sanctioned maintainer name is Sid and is never a finding.

Usage:

    python backend/tests/privacy_sweep.py --wordlist <file> <path> [<path> ...]
    python backend/tests/privacy_sweep.py --self-test

Exit codes: 0 no hits, 1 hits reported, 2 a class was not configured or the
self-test failed.
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

# ── the shape classes ────────────────────────────────────────────────────
# A path under a user home, in either separator. The drive-letter form and
# the two posix forms are the three ways this has actually leaked.
_USER_PATH = re.compile(r"(?:[A-Za-z]:[\\/]Users[\\/]|(?<![\w.])/(?:home|Users)/)[A-Za-z0-9._-]+")
# RFC1918 only. Loopback is not private-range and is handled by the allowance.
_PRIVATE_ADDR = re.compile(
    r"(?<![\d.])(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![\d.])")
_STEAM_ID = re.compile(r"(?<!\d)7656119\d{10}(?!\d)")
# A login target: an account name, the at sign, a host. Excludes anything with
# a TLD-looking tail that is really an e-mail address -- a different class,
# which this sweep does not claim to find.
_SSH_TARGET = re.compile(r"(?<![\w.@-])[a-z_][a-z0-9_-]{2,}@(?:[a-z0-9-]+\.)*[a-z0-9-]+"
                         r"(?::[0-9]+)?(?![\w@])", re.I)
# Five schedule fields followed by a command: a crontab line. Every field must
# carry a digit or a `*`; without that condition a lone `/` counts as a field
# and prose like "gold 74 / 55 / 46 / 20" reads as a schedule. A shape that
# fires on a list of numbers is noise, and a noisy class gets switched off,
# which is the same as not having it (#342).
_CRON_FIELD = r"[-\d,/]*[\d*][-\d,/]*"
_CRON_LINE = re.compile(rf"^\s*(?:{_CRON_FIELD}\s+){{4}}{_CRON_FIELD}\s+\S")
# A line that RUNS a deployment is describing one, whatever it is deploying.
# Only widely used, platform-neutral commands are named here: a detector that
# named this project's own platform tooling would be telling a reader which
# platform it is, which is the class it exists to catch. Anything specific to a
# platform belongs in the wordlist, outside the repository, with the host names.
# The orchestration command's own name is assembled from fragments, for the
# same reason the control's planted values are: a detector that spells out what
# it looks for is a copy of the thing it exists to stop travelling, and this
# file travels in the patch (#756).
_DEPLOY_CMD = re.compile(r"\b(?:" + "|".join([
    "ansible" + "-playbook",
    r"docker\s+compose",
    r"systemctl\s+(?:restart|start|stop)",
]) + r")\b")
# The one allowance, by EXACT form: the throwaway local database these tests
# use. Written as a shape so a second allowance has to be added deliberately.
_ALLOWED = re.compile(r"127\.0\.0\.1:55432")

_SHAPE_CLASSES = (
    ("user-path", _USER_PATH),
    ("private-address", _PRIVATE_ADDR),
    ("steam-id", _STEAM_ID),
)
_DEPLOY_SHAPES = (_SSH_TARGET, _DEPLOY_CMD)
_WORDLIST_CLASSES = ("handle", "deployment-identifier")


def load_wordlist(path: Path | None) -> dict[str, list[str]]:
    terms: dict[str, list[str]] = {c: [] for c in _WORDLIST_CLASSES}
    if path is None:
        return terms
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cls, _, term = line.partition(":")
        cls, term = cls.strip(), term.strip()
        if term and cls in terms:
            terms[cls].append(term)
    return terms


def scan_text(text: str, terms: dict[str, list[str]]) -> list[tuple[int, str]]:
    """[(line number, class)] for one file's text, deduplicated per line+class.

    The matched text is deliberately not returned: nothing downstream can
    print what it never received.
    """
    out: list[tuple[int, str]] = []
    term_rx = {
        cls: re.compile("|".join(re.escape(t) for t in ts), re.I)
        for cls, ts in terms.items() if ts
    }
    for lineno, line in enumerate(text.splitlines(), 1):
        # Remove the allowed form before any shape runs, so the allowance is
        # one rule in one place rather than an exception per class.
        probe = _ALLOWED.sub(" ", line)
        seen: set[str] = set()
        for cls, rx in _SHAPE_CLASSES:
            if rx.search(probe):
                seen.add(cls)
        if any(rx.search(probe) for rx in _DEPLOY_SHAPES) or _CRON_LINE.match(probe):
            seen.add("deployment-identifier")
        for cls, rx in term_rx.items():
            if rx.search(probe):
                seen.add(cls)
        out.extend((lineno, cls) for cls in sorted(seen))
    return out


def sweep(paths: list[Path], terms: dict[str, list[str]]) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, cls in scan_text(text, terms):
            hits.append((path.as_posix(), lineno, cls))
    return hits


def _self_test() -> int:
    """Plant one instance of every class and require every one to be reported.

    Every planted value is ASSEMBLED AT RUN TIME from fragments, so no real
    handle, address, path or id is written into this file, into a temporary
    file, or into any log -- the failure round 2 recorded, where the control's
    own output carried real values into an outbound log (#756).
    """
    user = "C:" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "tree"
    addr = "192." + "168." + "0." + "7"
    steam = "7656119" + "9" * 10
    host = "zz" + "probe" + "host"
    handle = "zz" + "probe" + "handle"
    with tempfile.TemporaryDirectory() as td:
        wl = Path(td) / "wordlist.txt"
        wl.write_text(f"handle:{handle}\ndeployment-identifier:{host}\n", encoding="utf-8")
        sample = Path(td) / "planted.txt"
        sample.write_text(
            "\n".join([
                f"the tree is at {user}",
                f"the box answers on {addr}",
                f"the seat is {steam}",
                f"reported by {handle}",
                f"deployed to {host}",
                "account" + "@" + "examplehost",
                "*/5 * * * * some-command --flag",
                "the test database is on 127.0.0.1:55432 and is allowed",
            ]) + "\n", encoding="utf-8")
        terms = load_wordlist(wl)
        hits = sweep([sample], terms)

    found = {cls for _f, _n, cls in hits}
    lines_by_cls = {}
    for _f, n, cls in hits:
        lines_by_cls.setdefault(cls, []).append(n)
    required = {"user-path", "private-address", "steam-id",
                "deployment-identifier", "handle"}
    checks = {
        "every class reported": required <= found,
        "the ssh-target shape is reported": 6 in lines_by_cls.get("deployment-identifier", []),
        "the cron shape is reported": 7 in lines_by_cls.get("deployment-identifier", []),
        "the allowed local DSN is NOT reported": 8 not in [n for _f, n, _c in hits],
        "no matched text is returned": all(len(h) == 3 and isinstance(h[2], str) for h in hits),
    }
    for cls in sorted(required):
        print(f"  {'ok  ' if cls in found else 'FAIL'} class reported: {cls}")
    for k, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {k}")
    missing = sorted(required - found) + [k for k, ok in checks.items() if not ok]
    print("SELF-TEST:", "every class caught, the allowance held"
          if not missing else f"FAILED: {missing}")
    return 2 if missing else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--wordlist", type=Path,
                    help="local-only file of `class:term` lines; see the module docstring")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if not args.paths:
        ap.error("give at least one path to sweep, or --self-test")

    terms = load_wordlist(args.wordlist)
    unconfigured = [c for c in _WORDLIST_CLASSES if not terms[c]]
    missing = [p for p in args.paths if not p.is_file()]
    if missing:
        print("REFUSING: not a file: " + ", ".join(p.as_posix() for p in missing))
        return 2

    hits = sweep(args.paths, terms)
    print(f"swept {len(args.paths)} files")
    for cls, _rx in _SHAPE_CLASSES:
        print(f"  class {cls}: by shape")
    print("  class deployment-identifier: by shape"
          + (f" + {len(terms['deployment-identifier'])} terms"
             if terms["deployment-identifier"] else ""))
    print(f"  class handle: {len(terms['handle'])} terms"
          if terms["handle"] else "  class handle: NOT CONFIGURED")
    for f, n, cls in hits:
        print(f"{f}:{n}: {cls}")
    print(f"HITS: {len(hits)}")
    if unconfigured:
        print("REFUSING a verdict: no terms supplied for "
              + ", ".join(unconfigured)
              + " — those classes were NOT checked. Supply --wordlist.")
        return 2
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
