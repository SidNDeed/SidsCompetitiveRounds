"""The marker line is a contract between two files that never import each other.

`backend/api/mail_discord.py` writes the marker into the DM text; the bot in
`backend/discord_bot.py` reads it back. They run in different containers and
share no code, so the patterns exist twice -- and two copies of one contract
drifting apart is a failure this project has already paid for (#329/#341).

Everything here is checked against the REAL literals lifted out of both files.
Retyping the pattern into the test would only prove the test agrees with
itself: the check has to be able to fail (#342/#431).
"""
import ast
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))

import mail_discord  # noqa: E402
import main  # noqa: E402

BOT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "discord_bot.py")
BOT_SRC = open(BOT_PATH, encoding="utf-8").read()
API_SRC = open(mail_discord.__file__, encoding="utf-8").read()

# The names that MUST mean the same thing on both sides of the wire.
SHARED = ("RELAY_CODE_ALPHABET", "RELAY_CODE_LEN", "_CODE_BODY",
          "RELAY_CODE_RE", "RELAY_CODE_ANY_RE")


def _toplevel_assignments(src):
    """{name: unparsed source of the assigned expression} for module scope.

    Compared as SOURCE, not as compiled objects: two `re.compile` results are
    hard to compare and easy to compare wrongly, while the text is exactly the
    thing that has to stay identical."""
    out = {}
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            out[node.targets[0].id] = ast.unparse(node.value)
    return out


def _lift(src, names):
    """Execute just these module-level assignments, against a real `re`."""
    want = set(names)
    body = [n for n in ast.parse(src).body
            if isinstance(n, ast.Assign) and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id in want]
    assert len(body) == len(want), (
        "expected %d assignments, lifted %d" % (len(want), len(body)))
    ns = {"re": re}
    exec(compile(ast.Module(body=body, type_ignores=[]), "<lift>", "exec"), ns)
    return ns


def _lift_func(src, name, ns):
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            node.decorator_list = []
            exec(compile(ast.Module(body=[node], type_ignores=[]),
                         "<lift>", "exec"), ns)
            return ns[name]
    raise AssertionError("no function named %s in this source" % name)


def test_the_bot_and_the_api_agree_on_the_marker():
    """Both files' definitions, compared as text, name by name.

    MUTATION: change RELAY_CODE_LEN to 11 in discord_bot.py only, or relax the
    bot's RELAY_CODE_RE anchor. Either must fail here."""
    api = _toplevel_assignments(API_SRC)
    bot = _toplevel_assignments(BOT_SRC)
    missing = [n for n in SHARED if n not in api or n not in bot]
    assert not missing, "not defined in both files: %s" % missing
    for name in SHARED:
        assert api[name] == bot[name], (
            "%s has drifted:\n  api: %s\n  bot: %s" % (name, api[name], bot[name]))


def test_the_two_normalizers_cannot_disagree_about_a_typed_code():
    """`normalize_relay_code` decides what a player's typing MEANS, on both
    sides. A code the bot accepts and the api rejects is a refusal the player
    cannot act on, and the reverse routes a reply by a rule only one file
    knows.

    MUTATION: drop the O->0 substitution from either copy. Must fail."""
    api_fn = _lift_func(API_SRC, "normalize_relay_code",
                        _lift(API_SRC, SHARED) | {"re": re})
    bot_fn = _lift_func(BOT_SRC, "normalize_relay_code",
                        _lift(BOT_SRC, SHARED) | {"re": re})
    corpus = [
        "SCR-7K2Q9XM4TB3H", "scr-7k2q9xm4tb3h", "SCR7K2Q9XM4TB3H",
        "SCR 7K2Q9XM4TB3H", " SCR-7K2Q9XM4TB3H ", "scr_7k2q9xm4tb3h",
        # Crockford's eye-substitutions
        "SCR-IK2Q9XM4TB3H", "SCR-LK2Q9XM4TB3H", "SCR-OK2Q9XM4TB3H",
        # U is not in the alphabet and is deliberately NOT remapped
        "SCR-UK2Q9XM4TB3H",
        # lengths either side, and things that are not codes at all
        "SCR-7K2Q9XM4TB3", "SCR-7K2Q9XM4TB3HH", "", "hello", "SCR-",
        "#12 still broken", "!link ABC123",
    ]
    for s in corpus:
        assert api_fn(s) == bot_fn(s), "disagree on %r" % s
    # ...and the substitutions actually happen, or the loop above is vacuous.
    assert api_fn("SCR-IK2Q9XM4TB3H") == "SCR-1K2Q9XM4TB3H"
    assert api_fn("SCR-OK2Q9XM4TB3H") == "SCR-0K2Q9XM4TB3H"
    assert api_fn("SCR-UK2Q9XM4TB3H") == ""


def test_the_marker_is_recognised_only_as_its_own_line():
    """The anchor is the whole guarantee. `RELAY_CODE_RE` must match the line
    the DM ends with and must NOT match the same characters inside a sentence
    a player wrote -- otherwise quoting a code back at the bot names a thread.

    NEGATIVE CONTROL: `RELAY_CODE_ANY_RE` is the loose pattern and DOES find
    the in-sentence form; without it this test would pass against a regex that
    matches nothing at all (#391).

    MUTATION: relax `^-# \\u21a9 ` to a bare search. Must fail."""
    ns = _lift(API_SRC, SHARED)
    strict, loose = ns["RELAY_CODE_RE"], ns["RELAY_CODE_ANY_RE"]
    code = "SCR-7K2Q9XM4TB3H"
    own_line = "Body text\n-# ↩ %s" % code
    assert strict.findall(own_line) == [code]
    for inside in ("please use -# ↩ %s to answer" % code,
                   "my code is %s" % code,
                   "-#  ↩ %s" % code,          # two spaces
                   "- # ↩ %s" % code,          # split marker
                   "-# ↩ %s trailing words" % code,
                   "x-# ↩ %s" % code):         # not line-leading
        assert strict.findall(inside) == [], "matched inside text: %r" % inside
        assert loose.search(inside), "negative control found nothing in %r" % inside
    # Trailing horizontal whitespace is tolerated; a following line is not a
    # reason to stop matching.
    assert strict.findall("-# ↩ %s  \nmore" % code) == [code]


def test_player_text_cannot_render_as_the_marker_line():
    """T2. The escaper is what makes the anchor unforgeable: it rewrites a
    line-leading `-#` and collapses intra-line whitespace, so a body that
    LOOKS like the marker cannot come out of `relay_dm_text` as one.

    MUTATION: drop the line-leading `-#` escape from `_mail_discord_safe`, or
    relax the anchor. Either must fail."""
    ns = _lift(API_SRC, SHARED)
    strict = ns["RELAY_CODE_RE"]
    real = "SCR-ABCDEFGHJKMN"
    forged = "SCR-7K2Q9XM4TB3H"
    marker = "-# ↩ %s" % forged
    for body in (marker,
                 "  " + marker,
                 "first line\n" + marker,
                 "first line\n   " + marker + "   ",
                 marker + "\nand more",
                 "\n\n" + marker):
        out = mail_discord.relay_dm_text(
            main._mail_discord_safe, sender_name="Bob", sender_steam_id="7",
            subject="Hi", body=body, code=real)
        found = strict.findall(out)
        assert found == [real], (
            "body %r produced markers %r; the DM must name exactly the real "
            "thread and nothing else" % (body, found))


def test_the_dm_keeps_its_marker_at_the_size_limit():
    """T3. Discord refuses a DM over 2000 characters, so the marker has to be
    inside the budget rather than appended after the clip -- otherwise the one
    line that makes the DM answerable is the first thing lost on a long mail.

    MUTATION: append the marker after clipping the body to RELAY_BODY_MAX.
    The length assertion, the marker assertion, or both must fail."""
    ns = _lift(API_SRC, SHARED)
    strict = ns["RELAY_CODE_RE"]
    code = "SCR-ABCDEFGHJKMN"
    # Characters the escaper EXPANDS, so the worst case is really the worst.
    out = mail_discord.relay_dm_text(
        main._mail_discord_safe, sender_name="N" * 200, sender_steam_id="7" * 20,
        subject="*_`~|" * 200, body="-#*_`>@\n" * 900, code=code)
    assert len(out) <= mail_discord.RELAY_DM_MAX, len(out)
    assert strict.findall(out) == [code], "the marker did not survive the clip"


def test_the_bot_reads_a_code_only_from_the_front_of_what_a_player_typed():
    """A code sitting in the middle of a message is the player QUOTING one --
    most often out of the listing the bot just sent them. Only a leading code
    is an instruction.

    MUTATION: swap `match` for `search` in `_RELAY_CODE_LEAD_RE`'s use, or
    anchor-strip the pattern. Must fail."""
    ns = _lift(BOT_SRC, ("RELAY_CODE_LEN",))
    lead = _toplevel_assignments(BOT_SRC)["_RELAY_CODE_LEAD_RE"]
    rx = eval(lead, {"re": re, "RELAY_CODE_LEN": ns["RELAY_CODE_LEN"]})
    m = rx.match("SCR-7K2Q9XM4TB3H thanks, fixed it")
    assert m and m.group(1) == "SCR-7K2Q9XM4TB3H"
    assert m.group(2) == "thanks, fixed it"
    # Leading whitespace is a typo, not a different intent.
    assert rx.match("  scr 7k2q9xm4tb3h ok").group(2) == "ok"
    # ...and a code that is not at the front is text.
    for s in ("thanks SCR-7K2Q9XM4TB3H", "I got SCR-7K2Q9XM4TB3H yesterday"):
        m2 = rx.match(s)
        assert m2 is None or not m2.group(1).startswith("SCR"), s


def test_the_marker_helpers_are_the_only_thing_the_dm_appends():
    """`relay_code_line` is duplicated too, and it is what the DM ends with.
    If the two files build that line differently, every reply refuses.

    MUTATION: change the bot's copy to use a different dash or drop the
    leading newline. Must fail."""
    api_fn = _lift_func(API_SRC, "relay_code_line", {})
    bot_fn = _lift_func(BOT_SRC, "relay_code_line", {})
    code = "SCR-7K2Q9XM4TB3H"
    assert api_fn(code) == bot_fn(code)
    # ...and what it produces is recognised by the pattern that has to read it.
    ns = _lift(BOT_SRC, SHARED)
    assert ns["RELAY_CODE_RE"].findall("mail body" + bot_fn(code)) == [code]


def test_a_minted_code_is_in_the_alphabet_the_readers_accept():
    """The minter, the strict pattern and the normalizer are three separate
    statements of one alphabet. This runs the minter enough times to catch a
    character that only one of them allows.

    MUTATION: add I, L, O or U to RELAY_CODE_ALPHABET. Must fail."""
    ns = _lift(API_SRC, SHARED)
    strict, loose = ns["RELAY_CODE_RE"], ns["RELAY_CODE_ANY_RE"]
    norm = _lift_func(API_SRC, "normalize_relay_code", dict(ns, re=re))
    seen = set()
    for _ in range(400):
        code = mail_discord.mint_relay_code()
        seen.add(code)
        assert loose.fullmatch(code), code
        assert strict.findall("x\n-# ↩ %s" % code) == [code], code
        # A minted code must survive a round trip through the reader that
        # handles typed ones, unchanged.
        assert norm(code) == code, code
    assert len(seen) > 390, "the minter is not producing distinct codes"


@pytest.mark.parametrize("name", SHARED)
def test_neither_file_defines_the_shared_names_twice(name):
    """A second assignment further down either file would silently win at
    import while this test still read the first one."""
    for label, src in (("api", API_SRC), ("bot", BOT_SRC)):
        n = sum(1 for node in ast.parse(src).body
                if isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name)
        assert n == 1, "%s assigns %s %d times" % (label, name, n)
