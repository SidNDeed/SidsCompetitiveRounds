#!/usr/bin/env python3
"""Keep the Thunderstore CHANGELOG under Thunderstore's size limit.

/pack-thunderstore step 5 pastes the new version's section at the top of
thunderstore/SidsCompetitiveRounds_upload/CHANGELOG.md, and Thunderstore
refuses a CHANGELOG.md over 100,000 BYTES. The step used to say "trim the
oldest version sections by hand and keep the tail paragraph"; this does that
mechanically:

  * a section is a `## v...` heading and everything up to the next one;
  * the OLDEST sections (the bottom of the file) are dropped one at a time
    until the file, as UTF-8 bytes, is at or under the limit;
  * the standing tail paragraph that links to the full history on GitHub is
    kept, always, as the last thing in the file;
  * line endings are preserved byte for byte (the file is read and written
    as bytes), so a no-op is a byte-identical file.

Refuses (exit 2, nothing written) when the tail marker is missing -- trimming
then would silently drop the only pointer to the full history -- or when the
newest section alone cannot fit.

    python tools/thunderstore_changelog_trim.py            # report only
    python tools/thunderstore_changelog_trim.py --check    # exit 1 when over the limit
    python tools/thunderstore_changelog_trim.py --write    # trim in place
"""
import argparse
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(REPO, "thunderstore", "SidsCompetitiveRounds_upload", "CHANGELOG.md")
LIMIT = 100_000
MARKER = b"_(older entries trimmed - full history on GitHub)_"
_SECTION = re.compile(rb"^## v", re.M)


def split(raw: bytes):
    """(head, [sections], tail). Raises ValueError when the marker is absent."""
    at = raw.rfind(MARKER)
    if at < 0:
        raise ValueError("the tail marker %r is missing" % MARKER.decode())
    # the tail starts at the beginning of the marker's line
    tail_start = raw.rfind(b"\n", 0, at) + 1
    body, tail = raw[:tail_start], raw[tail_start:]
    starts = [m.start() for m in _SECTION.finditer(body)]
    if not starts:
        return body, [], tail
    head = body[:starts[0]]
    sections = [body[s:e] for s, e in zip(starts, starts[1:] + [len(body)])]
    return head, sections, tail


def trim(raw: bytes, limit: int = LIMIT):
    """(new bytes, dropped section headings). Raises ValueError on a refusal."""
    head, sections, tail = split(raw)
    if len(raw) <= limit:
        return raw, []
    dropped = []
    while sections and len(head) + sum(map(len, sections)) + len(tail) > limit:
        if len(sections) == 1:
            raise ValueError("the newest section alone is over the limit")
        gone = sections.pop()
        dropped.append(gone.split(b"\n", 1)[0].strip().decode("utf-8", "replace"))
    out = head + b"".join(sections)
    # one blank line between the last kept section and the tail paragraph
    out = out.rstrip(b"\r\n")
    nl = b"\r\n" if b"\r\n" in raw else b"\n"
    out = out + nl + nl + tail
    if len(out) > limit:
        raise ValueError("still over the limit after trimming")
    return out, dropped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=DEFAULT)
    ap.add_argument("--limit", type=int, default=LIMIT)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    with open(args.path, "rb") as f:
        raw = f.read()
    try:
        out, dropped = trim(raw, args.limit)
    except ValueError as ex:
        print("REFUSED: %s" % ex, file=sys.stderr)
        return 2
    print("%s: %d bytes, limit %d" % (args.path, len(raw), args.limit))
    if not dropped:
        print("under the limit: nothing to trim")
        return 0
    print("would drop %d section(s), oldest last: %s" % (len(dropped), ", ".join(dropped)))
    print("after: %d bytes" % len(out))
    if args.write:
        with open(args.path, "wb") as f:
            f.write(out)
        print("WROTE %s" % args.path)
        return 0
    return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
