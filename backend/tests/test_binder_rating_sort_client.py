"""Item 20 -- the binder's rating-position sort, CLIENT lane.

WHAT THIS FILE COVERS AND WHAT IT DOES NOT.

The ordering rule itself is not asserted about here: it is EXECUTED, by
`plugin/BinderSortRules.SelfTest` under `tools/client-rules-harness`, and gated
by `test_client_rules_harness.py` (41 cases, two of them negative controls).
Writing a second, paraphrased copy of the rule in Python would be a gate that
agrees with itself.

What is left is the wiring the harness cannot reach, because it runs a
Unity-free file and the wiring lives in files that need Unity: how the four new
fields are parsed, what their ABSENCE means, where the config key is bound, who
is allowed to write it, and that the deferred restore happens before the sort
rather than after it. Those are read as source -- and a source gate is only
worth its line count if it can fail, so every one of them is paired here with
the MUTATION that must red it, applied to an in-memory COPY of the file. The
tree is never modified (#391, #290).

The SERVER half of item 20 -- `_PC_BOARD_RANKS_SQL`, its keyed TTL cache,
`_PC_SUBJECT_STANDINGS_SQL`, the attach in `pc_collection`, and the design's
S1-S7 -- landed on main separately and is tested in
`test_binder_rating_sort.py`; this file was named that on the client lane and
took the `_client` suffix when main was folded in, because both files had
claimed the one name. The client is built so that an answer carrying none of
the server half (a box without it) is a supported case rather than a failure:
see `test_an_answer_without_standings_is_unranked_not_broken`.
"""
import io
import os
import re
from pathlib import Path

import pytest

from _cs_structure import cs_block, code_of, mask_code

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "plugin" / "BinderSortRules.cs"
UI = ROOT / "plugin" / "PlayerCardsUI.cs"
API = ROOT / "plugin" / "ApiClient.cs"
PLUGIN = ROOT / "plugin" / "Plugin.cs"
INFO = ROOT / "plugin" / "InfoLibrary.cs"
CAT = ROOT / "plugin" / "I18nCatalogues.cs"
EXTRACT = ROOT / "tools" / "i18n_extract.py"

LABEL_EN = "Rating position"


def _src(path):
    return io.open(path, encoding="utf-8").read()


def _doc_before(src, signature):
    """The `///` block immediately above `signature`.

    Walks BACK over consecutive `///` lines from the declaration, so it cannot
    pick up a comment that merely sits somewhere else in the file -- the point
    when the claim under test is "the doc attached to X says Y".
    """
    i = src.index(signature)
    doc = []
    for line in reversed(src[:i].splitlines()):
        s = line.strip()
        if s.startswith("///"):
            doc.append(s)
            continue
        if s == "":
            continue
        break
    return "\n".join(reversed(doc))


# ── the gates, each a function over the SOURCE TEXT ──────────────────────────
#
# Written as functions so the mutation test below can feed each one a modified
# copy and require it to raise. A gate that passes its own mutation is not
# measuring anything (#342/#441).


def gate_rated_is_a_presence_test(api_src):
    """`subject_rated` must come from PcHas, never from the float.

    PcFloat maps both "the key is absent" and "the key is JSON null" to 0f, so
    a subject with no rating row and a subject rated 0 would be the same value
    -- and the back group's rule is that the unrated sort BEHIND every rated
    one, which needs the two told apart.
    """
    block = code_of(api_src, "internal static PcPrint ParsePcPrint(string obj)")
    assert 'subject_rated = PcHas(obj, "subject_rating"),' in block, (
        "subject_rated is not read as a presence test")
    assert 'subject_rating = PcFloat(PcTopLevel(obj, "subject_rating")),' in block
    # and it must not be derived from the value
    assert not re.search(r"subject_rated\s*=\s*[^;]*subject_rating\s*[<>!=]", block), (
        "subject_rated is derived from the rating VALUE, which conflates "
        "'no rating row' with 'rated 0'")


def gate_the_four_fields_are_parsed(api_src):
    """All four per-print fields, and the collection flag, are actually read."""
    prints = code_of(api_src, "internal static PcPrint ParsePcPrint(string obj)")
    for key in ("subject_board_rank", "subject_rating", "subject_inactive"):
        assert '"%s"' % key in prints, "%s is never read off the print" % key
    coll = code_of(api_src, "internal static PcCollection ParsePcCollection(string json)")
    assert 'subject_standings = PcBool(PcTopLevel(json, "subject_standings")),' in coll, (
        "the collection flag is not parsed")


def gate_absence_is_false_not_an_error(api_src):
    """The feature-presence question is answered by the collection flag alone.

    PcBool returns true only for the literal `true`, so an api that never
    mentions subject_standings gives false -- which the UI reads as Absent and
    answers by not offering the sort. Nothing throws and nothing is defaulted
    to "available" (#276: the unhandled case expires, it does not block).
    """
    coll = code_of(api_src, "internal static PcCollection ParsePcCollection(string json)")
    assert "subject_standings = PcBool(" in coll
    assert not re.search(r"subject_standings\s*=\s*true", coll), (
        "the flag is hardcoded true on a parse path -- an api without the "
        "server half would be read as carrying standings")


def gate_standings_is_three_valued(ui_src):
    """`null` collection, `false` flag and `true` flag are three answers.

    One boolean must not mean both "no answer has been read yet" and "the
    answer carried none" (#430): the first is a paint that happens before the
    fetch lands and must not destroy the stored sort, the second is a settled
    refusal.
    """
    block = code_of(ui_src, "private static BinderSortRules.Standings CurrentStandings()")
    assert "Standings.Unknown" in block and "Standings.Present" in block \
        and "Standings.Absent" in block, (
            "CurrentStandings does not distinguish all three: " + block)
    assert "col == null" in block, "the no-answer-yet case is not separated"


def gate_the_cycler_has_no_hardcoded_length(ui_src):
    """The "% 5" literal is gone and the next mode comes from the rules file.

    A flag names a line; the defect is a class (#432). The literal was correct
    for exactly as long as there were five sorts, so it is deleted rather than
    bumped to six.
    """
    block = code_of(ui_src, "private static void CycleSort()")
    assert "BinderSortRules.Next(binderSort, CurrentStandings())" in block, block
    assert "% 5" not in block and "% 6" not in block, (
        "the cycler still carries a hardcoded member count: " + block)
    # and nowhere else in the file either
    masked = mask_code(ui_src)
    assert "(int)binderSort" not in masked, (
        "the sort is still advanced by arithmetic on its ordinal somewhere")


def gate_only_the_click_writes_the_config(ui_src):
    """Exactly one writer of Plugin.BinderSort, and it is CycleSort.

    Counted inside the function span and then across the file, never file-wide
    only (#432). A guard is judged by what its refusal costs (#430): a paint
    path or a fallback that wrote the key would turn "this api cannot serve the
    sort today" into "you no longer prefer it".
    """
    masked = mask_code(ui_src)
    writes = [m.start() for m in re.finditer(r"Plugin\.BinderSort\.Value\s*=", masked)]
    assert len(writes) == 1, (
        "%d writers of the stored sort; there must be exactly one" % len(writes))
    cycle = cs_block(ui_src, "private static void CycleSort()")
    assert "Plugin.BinderSort.Value = BinderSortRules.NameOf(binderSort);" in cycle, (
        "the one writer is not CycleSort")
    # the restore must not write, under any outcome
    refresh = code_of(ui_src, "private static void RefreshBinder(ApiClient.PcMe me)")
    assert "Plugin.BinderSort" not in refresh, (
        "the paint path writes the stored sort")
    restore = code_of(ui_src, "internal static void RestoreBinderSort(string stored)")
    assert "Plugin.BinderSort" not in restore, (
        "the restore writes the stored sort back")


def gate_the_restore_runs_before_the_sort(ui_src):
    """The deferred restore is resolved BEFORE the list is ordered.

    After the sort it would paint one frame under the wrong order on the very
    paint that made the sort available -- the first paint that has an answer.
    """
    block = code_of(ui_src, "private static void RefreshBinder(ApiClient.PcMe me)")
    at_resolve = block.index("BinderSortRules.Resolve(")
    at_sort = block.index("sorted.Sort(CompareForBinder)")
    assert at_resolve < at_sort, (
        "the restore is resolved after the list has already been ordered")
    assert "pendingBinderSort.HasValue" in block[:at_sort]
    for outcome in ("Restore.Apply", "Restore.DropForSession"):
        assert outcome in block, "%s is never acted on" % outcome


def gate_the_comparator_has_one_definition(ui_src):
    """CompareForBinder delegates; the order is not written twice.

    Two copies of a comparator is two things to keep in step, and only one of
    them would be the one the harness runs.
    """
    block = code_of(ui_src, "private static int CompareForBinder(ApiClient.PcPrint a, ApiClient.PcPrint b)")
    assert "BinderSortRules.Compare(SortKey(a), SortKey(b), binderSort)" in block, block
    assert "switch" not in block, (
        "CompareForBinder still carries per-mode branches of its own")


def gate_the_key_is_bound_under_the_existing_section(plugin_src):
    """Section "Player Cards" -- with the space -- key BinderSort, string, "Name".

    A second, near-identical section heading would appear in every player's
    CompetitiveRounds.cfg, and the name (never the ordinal) is what survives a
    mode being inserted later.
    """
    # Comments stripped, so a commented-out bind cannot satisfy this; the
    # whole file rather than a named method because Plugin.cs carries four
    # Awake() blocks and the literal below is unique across all of them.
    code = code_of(plugin_src)
    assert re.search(
        r'BinderSort\s*=\s*Config\.Bind\(\s*"Player Cards",\s*"BinderSort",\s*"Name",',
        code), (
        "the key is not bound as (section 'Player Cards', key 'BinderSort', "
        "string, default 'Name')")
    assert '"PlayerCards", "BinderSort"' not in code, (
        "bound under a second, space-less section heading")
    assert "PlayerCardsUI.RestoreBinderSort(BinderSort.Value);" in code, (
        "the stored value is never handed over")


def gate_existing_config_entries_are_untouched(plugin_src):
    """The (section, key, type) of every existing Player Cards entry stays as
    it shipped. Item 20 adds a line; it re-homes nothing."""
    assert '"Player Cards", "PortraitPreset", -1,' in plugin_src
    assert '"Internal", "PlayerCardsOpenIntent",' in plugin_src
    assert '"UI", "ShowInactiveOnBoards",' in plugin_src


def gate_the_rules_file_holds_no_translatable_string(rules_src):
    """BinderSortRules is deliberately absent from the extractor's file list,
    which is only safe while it holds no I18n call site (#464/#550)."""
    code = code_of(rules_src)
    assert "I18n.Tr" not in code and "I18n.TrF" not in code, (
        "BinderSortRules gained a translatable string but is not in "
        "tools/i18n_extract.py's FILES list")
    assert "UnityEngine" not in code and "using UnityEngine" not in rules_src, (
        "the rules file gained a Unity reference and can no longer be run by "
        "the harness")


# ── the gates run against the real tree ──────────────────────────────────────

def test_the_four_subject_fields_are_parsed_off_the_answer():
    gate_the_four_fields_are_parsed(_src(API))


def test_an_unrated_subject_is_not_a_subject_rated_zero():
    gate_rated_is_a_presence_test(_src(API))


def test_an_answer_without_standings_is_unranked_not_broken():
    """Production today sends none of item 20's fields.

    That is the supported case, not a failure: the flag parses false, the UI
    reads Absent, and the button offers the five sorts it always had. The
    client is shippable against the current api by construction.
    """
    gate_absence_is_false_not_an_error(_src(API))
    gate_standings_is_three_valued(_src(UI))
    ui = _src(UI)
    # Absent and Unknown both withhold the sort from the CYCLER ...
    assert "BinderSortRules.Next(binderSort, CurrentStandings())" in code_of(
        ui, "private static void CycleSort()")
    # ... and the rules file is where the two are told apart for the RESTORE.
    rules = code_of(_src(RULES), "internal static Restore Resolve(Mode pending, Standings standings)")
    assert "Standings.Absent" in rules and "Restore.Keep" in rules


def test_the_cycler_no_longer_carries_a_member_count():
    gate_the_cycler_has_no_hardcoded_length(_src(UI))


def test_the_stored_sort_has_exactly_one_writer_and_it_is_the_button():
    gate_only_the_click_writes_the_config(_src(UI))


def test_the_deferred_restore_resolves_before_the_list_is_ordered():
    gate_the_restore_runs_before_the_sort(_src(UI))


def test_the_order_has_one_definition():
    gate_the_comparator_has_one_definition(_src(UI))


def test_the_config_key_lands_in_the_existing_player_cards_section():
    gate_the_key_is_bound_under_the_existing_section(_src(PLUGIN))
    gate_existing_config_entries_are_untouched(_src(PLUGIN))


def test_the_rules_file_stays_out_of_the_extractor_for_a_reason():
    gate_the_rules_file_holds_no_translatable_string(_src(RULES))
    extract = _src(EXTRACT)
    files = re.search(r"FILES\s*=\s*\[(.*?)\n\]", extract, re.S)
    assert files, "the extractor's FILES list could not be read"
    assert '"BinderSortRules.cs"' not in files.group(1)
    # the two files that DO carry item 20's strings are listed
    assert '"PlayerCardsUI.cs"' in files.group(1)
    assert '"InfoLibrary.cs"' in files.group(1)


def test_the_sort_key_carries_both_ranks_and_does_not_confuse_them():
    """The number ON the card and the subject's position TODAY are different
    fields, and the whole feature is that they can disagree. A mapping that
    fed board_rank into Rank would make the new sort a copy of the old one.
    """
    block = code_of(_src(UI), "private static BinderSortRules.Subject SortKey(ApiClient.PcPrint p)")
    assert "MintBoardRank = p.board_rank," in block, block
    assert "Rank = p.subject_board_rank," in block, block
    assert "Inactive = p.subject_inactive," in block
    assert "Rated = p.subject_rated," in block
    assert "Rating = p.subject_rating," in block


# ── the mutations: every gate above must red on its own defect ───────────────
#
# Each entry is (gate, source file, a replacement applied to a COPY of that
# file's text). The tree is never touched.

MUTATIONS = [
    ("subject_rated read off the float instead of PcHas",
     gate_rated_is_a_presence_test, API,
     ('subject_rated = PcHas(obj, "subject_rating"),',
      "subject_rated = subject_rating > 0f,")),
    ("subject_inactive dropped from the parse",
     gate_the_four_fields_are_parsed, API,
     ('subject_inactive = PcBool(PcTopLevel(obj, "subject_inactive")),', "")),
    ("the collection flag hardcoded true",
     gate_absence_is_false_not_an_error, API,
     ('subject_standings = PcBool(PcTopLevel(json, "subject_standings")),',
      "subject_standings = true,")),
    ("Unknown folded into Absent at the UI",
     gate_standings_is_three_valued, UI,
     ("            if (col == null) return BinderSortRules.Standings.Unknown;",
      "            if (col == null) return BinderSortRules.Standings.Absent;")),
    ("the cycler bumped to a hardcoded six",
     gate_the_cycler_has_no_hardcoded_length, UI,
     ("binderSort = BinderSortRules.Next(binderSort, CurrentStandings());",
      "binderSort = (Sort)(((int)binderSort + 1) % 6);")),
    ("the restore persists its own fallback",
     gate_only_the_click_writes_the_config, UI,
     ("                    case BinderSortRules.Restore.DropForSession:\n"
      "                        pendingBinderSort = null;",
      "                    case BinderSortRules.Restore.DropForSession:\n"
      "                        Plugin.BinderSort.Value = \"Name\";\n"
      "                        pendingBinderSort = null;")),
    ("the comparator grows a second copy of the order",
     gate_the_comparator_has_one_definition, UI,
     ("            return BinderSortRules.Compare(SortKey(a), SortKey(b), binderSort);",
      "            switch (binderSort) { default: break; }\n"
      "            return BinderSortRules.Compare(SortKey(a), SortKey(b), binderSort);")),
    ("the key bound under a second section heading",
     gate_the_key_is_bound_under_the_existing_section, PLUGIN,
     ('"Player Cards", "BinderSort", "Name",', '"PlayerCards", "BinderSort", "Name",')),
    ("an existing config entry re-homed",
     gate_existing_config_entries_are_untouched, PLUGIN,
     ('"Player Cards", "PortraitPreset", -1,', '"PlayerCards", "PortraitPreset", -1,')),
    ("a translatable string moves into the rules file",
     gate_the_rules_file_holds_no_translatable_string, RULES,
     ("internal const int TOP_N = 100;",
      'internal const int TOP_N = 100;\n        internal static string L() { return I18n.Tr("Rating position"); }')),
]


@pytest.mark.parametrize("name,gate,path,repl",
                         MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_each_gate_reds_on_its_own_mutation(name, gate, path, repl):
    """The negative control for every gate above.

    Without this, a gate whose needle drifted out of the file would keep
    passing for the rest of the project's life and nobody would know which
    line stopped being checked.
    """
    src = _src(path)
    old, new = repl
    assert old in src, "the mutation's anchor is no longer in %s: %r" % (path.name, old[:60])
    gate(src)                                  # green on the real tree
    with pytest.raises(AssertionError):
        gate(src.replace(old, new, 1))         # red on a COPY carrying the defect


def test_the_restore_gate_reds_when_the_resolve_moves_after_the_sort():
    """The ordering gate's mutation, which is a MOVE rather than a swap and so
    does not fit the table above."""
    src = _src(UI)
    gate_the_restore_runs_before_the_sort(src)
    block = cs_block(src, "private static void RefreshBinder(ApiClient.PcMe me)")
    at = block.index("            if (pendingBinderSort.HasValue)")
    end = block.index("            sorted.Clear();")
    restore_stmt = block[at:end]
    moved = block[:at] + block[end:].replace(
        "            int total = sorted.Count;",
        restore_stmt + "            int total = sorted.Count;", 1)
    with pytest.raises(AssertionError):
        gate_the_restore_runs_before_the_sort(src.replace(block, moved, 1))


# ── the wiki block and its four translations ─────────────────────────────────

def _verbatim_after(src, marker):
    i = src.index(marker)
    j = src.index('@"', i) + 2
    out, k = [], j
    while k < len(src):
        c = src[k]
        if c == '"':
            if k + 1 < len(src) and src[k + 1] == '"':
                out.append('"')
                k += 2
                continue
            break
        out.append(c)
        k += 1
    return "".join(out)


def _catalogue_keys(cat_src, needle):
    """Every (line number, unescaped key, unescaped value) whose key contains
    `needle`, read out of I18nCatalogues.cs."""

    def unescape(s):
        out, i = [], 0
        while i < len(s):
            if s[i] == "\\":
                out.append({"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
                           .get(s[i + 1], s[i + 1]))
                i += 2
            else:
                out.append(s[i])
                i += 1
        return "".join(out)

    rows = []
    for n, line in enumerate(cat_src.split("\n"), 1):
        m = re.match(r'\s*\["((?:[^"\\]|\\.)*)"\]\s*=\s*"((?:[^"\\]|\\.)*)"', line)
        if m and needle in m.group(1):
            rows.append((n, unescape(m.group(1)), unescape(m.group(2))))
    return rows


def test_the_wiki_sentence_is_its_own_key_composed_into_the_article():
    """Never three more lines inside CardsFace.

    A translation key IS the English source string, so editing that
    1,786-character literal retires its four shipped translations and prints
    REMOVED 4. The "cards" article already composes two blocks; this follows
    it, which adds a key and removes none.
    """
    info = _src(INFO)
    assert re.search(
        r'Key = "cards-face",\s+Title = \(\) => I18n\.Tr\("Reading a card"\),\s+'
        r'Body = \(\) => CardsFace \+ "\\n\\n" \+ CardsBinderSort', info), (
        "the article does not compose the new block")
    body = _verbatim_after(info, "private static string CardsBinderSort")
    assert "<b>Rating position</b>" in body
    assert "top 100 first" in body
    assert "not seen in 90 days" in body
    assert "the rank it was minted with" in body


def test_the_binder_sort_block_is_drafted_in_all_four_locales():
    """Four locales, both keys, and the TMP tag sequence preserved.

    I18n.RegisterCatalogue refuses an entry whose tag order differs from the
    source, so a draft that reordered them would be dropped at startup and the
    page would silently render English.
    """
    cat = _src(CAT)
    body = _verbatim_after(_src(INFO), "private static string CardsBinderSort")
    tags = lambda s: re.findall(r"<[^>]{1,30}>", s)

    rows = _catalogue_keys(cat, "SORTING THE BINDER")
    assert len(rows) == 4, (
        "expected one draft per locale, found %d" % len(rows))
    for _, key, value in rows:
        assert key == body, "a draft is keyed on text that is not the source"
        assert tags(value) == tags(body), "the tag sequence was reordered"
        assert value != body, "a locale was left as the English source"

    labels = _catalogue_keys(cat, LABEL_EN)
    labels = [r for r in labels if r[1] == LABEL_EN]
    assert len(labels) == 4, (
        "expected the button label in four locales, found %d" % len(labels))


def test_the_button_label_fits_the_button_in_every_locale():
    """SetOverflowMode(..., 2) is MASKING: an over-wide label loses its tail
    with no warning and no log line (PlayerCardsUI, the PcBSort construction).

    The bar is the widest composite the 220 px button ALREADY carries, which
    is the only width it is demonstrated to hold. Arial Bold at the same point
    size is the pre-screen ai-collab/v1410/settings_copy_measure.py uses -- a
    ranking instrument, not the in-game metric -- so the bar is a comparison
    against shipping copy rather than an absolute number.
    """
    font_path = "C:/Windows/Fonts/arialbd.ttf"
    if not os.path.exists(font_path):
        pytest.skip("Arial Bold is not on this machine")
    ImageFont = pytest.importorskip("PIL.ImageFont")
    font = ImageFont.truetype(font_path, 13)

    def w(s):
        b = font.getbbox(s)
        return b[2] - b[0]

    cat = _src(CAT)

    def tr(en, locale_line_lo, locale_line_hi):
        for n, key, value in _catalogue_keys(cat, en):
            if key == en and locale_line_lo <= n <= locale_line_hi:
                return value
        return en

    # locale dictionary spans, read from the file rather than hardcoded
    spans = {}
    lines = cat.split("\n")
    order = []
    for n, line in enumerate(lines, 1):
        m = re.match(r"\s*private static readonly Dictionary<string, string> (ES|RU|UK|SV)\b", line)
        if m:
            order.append((m.group(1), n))
    assert len(order) == 4, "could not find the four locale dictionaries"
    for i, (loc, start) in enumerate(order):
        end = order[i + 1][1] - 1 if i + 1 < len(order) else len(lines)
        spans[loc] = (start, end)

    shipping = ["Name", "Rarity", "Edition", "Date obtained", "Position"]
    worst = []
    for loc, (lo, hi) in spans.items():
        prefix = tr("Sort:", lo, hi)
        bar = max(w(prefix + " " + tr(lbl, lo, hi)) for lbl in shipping)
        draft = w(prefix + " " + tr(LABEL_EN, lo, hi))
        worst.append((loc, draft, bar))
        assert draft <= bar, (
            "%s: the new label composes to %d px, wider than the %d px the "
            "button already carries -- masking will clip it silently"
            % (loc, draft, bar))
    # the English source too: it is what sized the button
    en_bar = max(w("Sort: " + lbl) for lbl in shipping)
    assert w("Sort: " + LABEL_EN) <= 220, (
        "the English composite does not fit the 220 px button")
    assert en_bar <= 220
