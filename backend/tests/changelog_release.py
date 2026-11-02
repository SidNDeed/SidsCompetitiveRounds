"""One release's own text in docs/CHANGELOG.md.

A test that checks what the CHANGELOG tells players about a release has to
read that release's section, never the first match in the file. The
CHANGELOG adds each release ABOVE the previous one, so a first-occurrence
reader moves to whichever release is newest: newer prose that repeats a
sentence (or a whole bullet) then satisfies the reader while the release the
test is about states something else.

release_section(version) is the text from the line "## v<version> ..." up to
the next line that starts with "## ". It raises ChangelogError unless exactly
one heading names that version.

release_bullets(version) is that section's top-level bullets, each one line
of running text (whitespace collapsed, the leading "- " dropped). A bullet
starts at a line that begins with "- " and runs over the indented lines that
follow it, blank lines included when an indented line follows them: an
indented paragraph after a blank line is the bullet's own continuation
paragraph, as Markdown renders it, so a claim placed there is read with the
bullet (rehearsal-four round 2, finding 10: the reader stopped at the blank
line and a claim in the second paragraph went unread). A line that starts at
column 0 ends the bullet, so the next bullet, a "**Heading**" paragraph or a
"### " heading is never part of it.

one_bullet(version, phrase) is the one bullet of that release whose running
text contains the phrase (compared with whitespace collapsed on both sides).
It raises ChangelogError when no bullet of the release contains it or when
more than one does: a claim the test reads has to be stated once, in the
release that makes it.

Each function takes the CHANGELOG text as an optional argument so a test can
run it on a constructed text (its negative controls) as well as on the file.
"""

from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[2] / "docs" / "CHANGELOG.md"


class ChangelogError(AssertionError):
    """The CHANGELOG does not hold the release text the test reads."""


def _flat(text):
    return " ".join(text.split())


def _text(text):
    return CHANGELOG.read_text(encoding="utf-8") if text is None else text


def release_section(version, text=None):
    lines = _text(text).splitlines()
    head = "## v" + version + " "
    starts = [i for i, line in enumerate(lines) if line.startswith(head)]
    if len(starts) != 1:
        raise ChangelogError(
            "%d headings start with %r; exactly one is required" % (len(starts), head))
    end = len(lines)
    for i in range(starts[0] + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[starts[0]:end])


def release_bullets(version, text=None):
    bullets = []
    current = None
    for line in release_section(version, text).splitlines():
        if line.startswith("- "):
            if current is not None:
                bullets.append(current)
            current = [line[2:]]
        elif current is not None and not line.strip():
            continue                # held: the next line decides
        elif current is not None and line[0] in " \t":
            current.append(line)    # a wrapped line or a continuation paragraph
        else:
            if current is not None:
                bullets.append(current)
            current = None
    if current is not None:
        bullets.append(current)
    return [_flat(" ".join(b)) for b in bullets]


def one_bullet(version, phrase, text=None):
    want = _flat(phrase)
    hits = [b for b in release_bullets(version, text) if want in b]
    if len(hits) != 1:
        raise ChangelogError(
            "v%s has %d bullets containing %r; exactly one is required"
            % (version, len(hits), want))
    return hits[0]
