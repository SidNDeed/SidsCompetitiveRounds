"""Credential redaction for client log text: the ONE rule.

WHAT IT REMOVES
  ROUNDS' own Steam runtime writes the first web-API ticket delivered to its
  callback into the Unity log as "Steam Login success. Session Ticket: <hex>".
  The mod requests its own ticket for POST /api/v1/auth/steam, so that hex can
  be the very credential the endpoint exchanges for a session, and the line
  rides every bundle the client sends: the bug report's attachment and the
  automatic post-match upload.

  The rule replaces the VALUE after "Session Ticket:" -- a run of 32 or more
  hexadecimal characters, either case, starting after any spaces or tabs that
  follow the colon and ending where the hex ends (in the game's line, the end of
  the line) -- with a fixed marker:

      [redacted len=<number of hex characters> sha256=<first 8 hex of SHA-256>]

  the digest taken over the value's UTF-8 bytes exactly as logged. The label and
  the whitespace before the value stay; nothing after the value is touched.
  The marker is byte-identical to the client's own redaction of the same line
  (the v1.41.0 client lane's LogScrub pass 0), so a log redacted by either layer
  reads the same, and 32 bits of a digest tell two logs' tickets apart without
  giving one back.

WHAT IT DOES NOT DO
  Nothing else is altered: a text with no ticket comes back as the SAME object,
  byte-identical, and a text with tickets differs only inside the replaced
  values. A run of 31 hex characters is not a ticket. The label is matched
  exactly as the game writes it, behind anything (a log-level tag, a
  timestamp); the hex in either case. A value already in marker form carries no
  hex run, so a second pass is a no-op.

THE RULE RUNS BEFORE ANY CUT
  Every reader that shortens a text (a length clamp, a head or tail window, a
  snippet) applies the rule to the text as it has it FIRST. A cut made before
  the rule can drop a ticket's label and keep its value, or keep a head of the
  value shorter than 32 characters; either way the rule no longer recognises
  what is left, and what is left is part of the credential. A reader that gets
  its text in pieces uses settled_length() below to apply the rule to each
  piece as it arrives without splitting a ticket between two pieces.

WHY IT IS ITS OWN MODULE, STANDARD LIBRARY ONLY
  Three kinds of reader load this file: the api (every receive path and every
  read-back door of stored log text), a filter the ops wrapper can pipe a stored
  bundle through inside the api container (`python log_redaction.py`, stdin to
  stdout), and the local evidence tools that scan or scrub pins and lane folders,
  which load it by path. One file keeps the three from drifting into three rules.
"""
from __future__ import annotations

# Aliased to names no other api module binds. The route-manifest gate
# (backend/tests/test_route_manifest_net_seat.py) resolves a bare name in EVERY
# api module and folds every match into a route's fingerprint, so a plain
# `import re` here would enter every route that names `re` anywhere and move
# some two hundred fingerprints that do not depend on this file.
import codecs as _lr_codecs
import hashlib as _lr_hashlib
import re as _lr_re
import sys as _lr_sys

# THE RULE, stated once. Group 1 is kept (the label and the whitespace after
# its colon); group 2 is the value. The hex class names both cases itself, so
# no flag is needed, and NO FLAG IS WANTED: the label is matched exactly as the
# game writes it, which is what keeps it a literal prefix the engine can search
# for at memory speed. With re.IGNORECASE the same scan of a 12 MB bundle with
# no ticket in it took ~250 ms, one uninterrupted scan holding the GIL on an api
# that runs one worker by design (#125).
TICKET_PATTERN = r"(Session Ticket:[ \t]*)([0-9A-Fa-f]{32,})"
TICKET_RE = _lr_re.compile(TICKET_PATTERN)
_TICKET_RE_BYTES = _lr_re.compile(TICKET_PATTERN.encode("ascii"))

MARKER_FORMAT = "[redacted len={length} sha256={digest8}]"


def ticket_marker(value: str) -> str:
    """The marker for one ticket value: its length and the first 8 hex digits
    of the SHA-256 of its UTF-8 bytes."""
    digest8 = _lr_hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return MARKER_FORMAT.format(length=len(value), digest8=digest8)


def redact_credentials_counted(text):
    """(redacted text, number of tickets replaced). A falsy input (None, "")
    and a text without a ticket come back as the same object with 0."""
    if not text:
        return text, 0
    replaced = 0

    def _marker(m):
        nonlocal replaced
        replaced += 1
        return m.group(1) + ticket_marker(m.group(2))

    out = TICKET_RE.sub(_marker, text)
    if not replaced:
        return text, 0
    return out, replaced


def redact_credentials(text):
    """The text with every ticket value replaced by its marker (see above)."""
    return redact_credentials_counted(text)[0]


# The unfinished end of a text that is still arriving: the label, the spaces
# and tabs after it and any hex after those, running to the very end. The next
# piece can still complete it into a ticket, or lengthen a value that already
# counts as one.
_UNSETTLED_TAIL_RE = _lr_re.compile(r"Session Ticket:[ \t]*[0-9A-Fa-f]*\Z")
_LABEL = "Session Ticket:"


def settled_length(text: str) -> int:
    """How many leading characters of `text` the rule can be applied to NOW,
    when more text may still follow it.

    For any continuation, redact_credentials(text[:n]) followed by the rule over
    text[n:] + the continuation equals the rule over the whole. The part held
    back is an unfinished end: the label with its spaces/tabs and any hex after
    them running to the end, or the first characters of the label itself. No
    match can straddle the returned index. When something is held back, the
    index is the label's capital "S", and a match holds that character only as
    its own first one. When nothing is held back, a match running on into the
    next piece would begin with an unfinished end, which would have been held
    back. A reader that applies the rule to a stream (a bundle read in pieces,
    then cut to a window) redacts each settled prefix and carries the rest into
    the next piece.
    """
    if not text:
        return 0
    m = _UNSETTLED_TAIL_RE.search(text)
    if m:
        return m.start()
    for n in range(min(len(_LABEL) - 1, len(text)), 0, -1):
        if text.endswith(_LABEL[:n]):
            return len(text) - n
    return len(text)


def count_credentials(text) -> int:
    """How many ticket values a text carries (0 for None or "")."""
    if not text:
        return 0
    return sum(1 for _ in TICKET_RE.finditer(text))


def count_credentials_bytes(data: bytes) -> int:
    """How many ticket values a file's bytes carry, whatever its text encoding.

    One scan of the bytes finds a ticket in UTF-8, ASCII or any single-byte
    encoding. A file holding NUL bytes is also read as UTF-16LE at BOTH byte
    alignments: text written by a tool that defaults to UTF-16, or a wide string
    inside a binary, can start at an odd offset, and a single view from byte 0
    reads every such string as noise. A given ticket is visible in exactly one
    of the three views, so the counts add.
    """
    if not data:
        return 0
    total = sum(1 for _ in _TICKET_RE_BYTES.finditer(data))
    if b"\x00" in data:
        for start in (0, 1):
            total += count_credentials(data[start:].decode("utf-16-le", "ignore"))
    return total


def redact_credentials_bytes(data: bytes):
    """(bytes, number replaced) for a whole file. A UTF-16 file with a byte
    order mark is rewritten in its own encoding with its own mark; anything
    else is read as UTF-8 with every undecodable byte carried through
    unchanged, so the only bytes that move are the replaced values. A file with
    nothing to replace comes back as the same object."""
    if not data:
        return data, 0
    for bom, codec in ((_lr_codecs.BOM_UTF16_LE, "utf-16-le"), (_lr_codecs.BOM_UTF16_BE, "utf-16-be")):
        if data.startswith(bom):
            try:
                text = data[len(bom):].decode(codec)
            except UnicodeDecodeError:
                break   # not really UTF-16: fall through to the byte view
            out, replaced = redact_credentials_counted(text)
            if not replaced:
                return data, 0
            return bom + out.encode(codec), replaced
    text = data.decode("utf-8", "surrogateescape")
    out, replaced = redact_credentials_counted(text)
    if not replaced:
        return data, 0
    return out.encode("utf-8", "surrogateescape"), replaced


def _filter_stdin_to_stdout() -> int:
    """`python log_redaction.py`: redact stdin onto stdout. The count goes to
    stderr, so a caller gets a positive signal without it mixing into the text."""
    data = _lr_sys.stdin.buffer.read()
    out, replaced = redact_credentials_bytes(data)
    _lr_sys.stdout.buffer.write(out)
    _lr_sys.stdout.buffer.flush()
    print(f"[log_redaction] credentials redacted: {replaced}", file=_lr_sys.stderr)
    return 0


if __name__ == "__main__":
    _lr_sys.exit(_filter_stdin_to_stdout())
