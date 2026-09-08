"""The gate on the gates: `_cs_structure` must actually be able to fail.

Five test modules decide what they assert by reading C# structurally. Before
2026-09-06 each carried its own copy of a brace walk over RAW source and a
comment stripper that only dropped lines beginning with `//`. Both let an
assertion pass on text nobody chose:

* `plugin/Plugin.cs` carries a doc comment with two unmatched `{`, so a walk
  crossing it returned a block ending in the wrong place.
* `plugin/ApiClient.cs` carries JSON inside string literals - raw brace balance
  +22 - so a walk over it was arithmetic on punctuation, not structure.
* A needle sitting in a trailing comment satisfied a code assertion. One did:
  `test_music_probe_gate.py` asserted a string that ENDED in the source's own
  `// the natural end is an intended silence, not a gap`, which is a comment
  keeping a code assertion alive by itself.

Every property below is paired with something that demonstrates the failure it
prevents - usually `naive_block`, the old algorithm kept deliberately broken
for exactly this purpose (#391). A property with no live negative control is
decoration, and decoration is how a check that cannot fail gets written.
"""

from pathlib import Path

import pytest

from _cs_structure import (
    CsParseError,
    and_terms,
    cs_block,
    guard_chain,
    initialiser,
    mask_code,
    method_spans,
    naive_block,
    strip_comments_only,
)


PLUGIN = Path(__file__).resolve().parents[2] / "plugin"


def _balance(text):
    return text.count("{") - text.count("}")


# ── the mask is the structure ────────────────────────────────────────────────

def test_every_plugin_source_masks_to_a_balanced_file():
    """The whole point: after masking, brace depth is real."""
    sources = sorted(PLUGIN.glob("*.cs"))
    assert len(sources) >= 8, "the plugin tree lost files; this gate went quiet"
    for path in sources:
        src = path.read_text(encoding="utf-8")
        masked = mask_code(src)
        assert len(masked) == len(src), f"{path.name}: mask changed offsets"
        assert _balance(masked) == 0, f"{path.name}: masked braces do not balance"


def test_the_two_files_that_break_a_raw_walk_still_break_it():
    """The negative control for the mask, measured rather than asserted.

    If these two ever balance in RAW text, this file's central claim has gone
    vacuous and the masker is no longer being tested by them - which is worth a
    failure, not a silent pass.
    """
    plugin_cs = (PLUGIN / "Plugin.cs").read_text(encoding="utf-8")
    api_cs = (PLUGIN / "ApiClient.cs").read_text(encoding="utf-8")
    assert _balance(plugin_cs) != 0, "Plugin.cs no longer carries a brace in prose"
    assert _balance(api_cs) != 0, "ApiClient.cs no longer carries braces in literals"
    assert _balance(mask_code(plugin_cs)) == 0
    assert _balance(mask_code(api_cs)) == 0


def test_the_naive_walk_breaks_on_a_real_file_where_the_mask_holds():
    """The old algorithm, run against a real source, cannot find the end.

    `plugin/Plugin.cs` line 6103 carries `for (...) { if (pickrID != -1) {`
    inside a doc comment - two opens that never close. Walking the enclosing
    namespace over raw text therefore runs off the end of the file, while the
    masked walk returns a balanced block. This is the failure every caller of
    the old helper was exposed to, measured rather than described.
    """
    path = PLUGIN / "Plugin.cs"
    signature = "namespace CompetitiveRounds"
    block = cs_block(path, signature)
    # The block is returned as raw source - comments and literals intact, since
    # callers assert against text - so its balance is a property of the mask.
    assert _balance(mask_code(block)) == 0
    assert _balance(block) == 2, (
        "this block is exactly the one whose raw braces do not balance; if that "
        "changed, this control no longer exercises the defect"
    )
    with pytest.raises(AssertionError) as excinfo:
        naive_block(path, signature)
    assert "unbalanced braces" in str(excinfo.value), (
        "the naive walk now completes, so it has stopped demonstrating the bug"
    )


# ── comments ─────────────────────────────────────────────────────────────────

def test_a_trailing_comment_cannot_satisfy_a_code_assertion():
    src = "int x = 1;   // the answer is 42\n"
    kept = strip_comments_only(src)
    assert "int x = 1;" in kept
    assert "42" not in kept, "a trailing comment survived the stripper"
    # The pre-2026-09-06 stripper dropped only lines STARTING with a slash,
    # so the same needle survived it. That is the defect, stated as a control.
    old_style = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("//")
    )
    assert "42" in old_style


def test_a_doc_comment_brace_is_not_structure():
    src = "void M()\n{\n    /// for (...) { if (x) {\n    Body();\n}\n"
    assert _balance(mask_code(src)) == 0
    assert "Body();" in cs_block(src, "void M()")


def test_a_block_comment_is_removed_whole():
    src = "void M()\n{\n    /* } } } */\n    Body();\n}\n"
    assert "Body();" in cs_block(src, "void M()")


# ── literals ─────────────────────────────────────────────────────────────────

def test_braces_inside_a_string_are_not_structure():
    src = 'void M()\n{\n    Log("{\\"a\\":{}}");\n}\n'
    assert _balance(mask_code(src)) == 0


def test_a_verbatim_string_opening_with_an_escaped_quote_parses():
    """`plugin/ApiClient.cs:1733` has this shape and it is not a raw string."""
    src = 'void M()\n{\n    var r = @"""url""\\s*:\\s*""([^""]+)""";\n    Body();\n}\n'
    assert "Body();" in cs_block(src, "void M()")


def test_a_string_nested_in_an_interpolation_hole_parses():
    """`plugin/ApiClient.cs:5608`: a scanner that stops at the first quote ends
    the outer string inside the expression and desynchronises the whole file."""
    src = 'void M()\n{\n    var s = $"a{(c == null ? "null" : $"\\"{E(c)}\\"")},";\n    Body();\n}\n'
    assert "Body();" in cs_block(src, "void M()")
    assert _balance(mask_code(src)) == 0


def test_a_char_literal_brace_is_not_structure():
    src = "void M()\n{\n    char c = '{';\n    Body();\n}\n"
    assert _balance(mask_code(src)) == 0


def test_a_raw_string_is_a_failure_and_never_a_skip():
    """A parse refusal that degrades to a skip is the L4 defect one level up."""
    src = 'void M()\n{\n    var s = ' + '"' * 3 + 'x' + '"' * 3 + ';\n}\n'
    with pytest.raises(CsParseError) as excinfo:
        mask_code(src)
    assert "raw string" in str(excinfo.value)


# ── the preprocessor ─────────────────────────────────────────────────────────

def test_the_inactive_branch_is_not_code():
    src = (
        "void M()\n{\n"
        "#if THUNDERSTORE\n"
        "    Shipped();\n"
        "#else\n"
        "    Standalone();\n"
        "#endif\n"
        "}\n"
    )
    body = strip_comments_only(src)
    assert "Standalone();" in body
    assert "Shipped();" not in body, (
        "the THUNDERSTORE branch is not in the Release artifact these gates describe"
    )


def test_a_brace_split_across_an_if_directive_still_balances():
    src = (
        "void M()\n{\n"
        "#if THUNDERSTORE\n"
        "    if (a) {\n"
        "        X();\n"
        "    }\n"
        "#endif\n"
        "    Body();\n"
        "}\n"
    )
    assert _balance(mask_code(src)) == 0
    assert "Body();" in cs_block(src, "void M()")


def test_an_unclosed_if_directive_is_a_failure():
    with pytest.raises(CsParseError):
        mask_code("void M()\n{\n#if THUNDERSTORE\n}\n")


# ── spans ────────────────────────────────────────────────────────────────────

def test_an_unbalanced_signature_raises_rather_than_returning_a_body():
    """The overrun case: a caller must never be handed a stale block."""
    with pytest.raises(CsParseError):
        list(method_spans("void M()\n{\n    if (a) {\n", "void M()"))


def test_two_matching_blocks_are_an_error_not_a_coin_flip():
    src = "void M()\n{\n    A();\n}\nvoid M()\n{\n    B();\n}\n"
    assert len(list(method_spans(src, "void M()"))) == 2
    with pytest.raises(CsParseError):
        cs_block(src, "void M()")


# ── expressions ──────────────────────────────────────────────────────────────

def test_a_conjunction_splits_into_its_terms():
    assert and_terms("a != null && b.c && !d") == ["a != null", "b.c", "!d"]


def test_an_or_at_the_top_level_is_refused():
    """The `&&`-to-`||` mutation is invisible to a substring assertion."""
    with pytest.raises(CsParseError):
        and_terms("a && b || c")


def test_an_or_inside_parentheses_is_not_a_top_level_or():
    assert and_terms("a && (b || c)") == ["a", "(b || c)"]


def test_an_operator_inside_a_string_is_not_an_operator():
    assert and_terms('a && b == "x && y"') == ["a", 'b == "x && y"']


def test_an_initialiser_is_read_up_to_its_semicolon():
    src = "void M()\n{\n    bool ok = a && b;\n    Use(ok);\n}\n"
    assert initialiser(src, "void M()", "bool ok") == "a && b"


# ── dominance ────────────────────────────────────────────────────────────────

def test_a_closed_guard_does_not_dominate_a_later_statement():
    """L5, as a property.

    Offset order plus increasing indentation is satisfied by an already-closed
    block followed by a deeper unrelated one. Only a real walk tells them apart.
    """
    src = (
        "void M()\n"
        "{\n"
        "    if (isPlaying)\n"
        "    {\n"
        "        Unrelated();\n"
        "    }\n"
        "    if (other)\n"
        "    {\n"
        "        if (deeper)\n"
        "        {\n"
        "            Target();\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    chain = guard_chain(src, "void M()", "Target();")
    assert chain == ["other", "deeper"]
    assert "isPlaying" not in chain, (
        "a guard that closed before the statement was reported as dominating it"
    )
    # The control: the naive reading - "isPlaying appears earlier and the
    # statement is indented deeper" - accepts exactly the source it must reject.
    body = src[src.index("{") :]
    assert body.index("isPlaying") < body.index("Target();")


def test_a_real_nesting_is_reported_outermost_first():
    src = (
        "void M()\n"
        "{\n"
        "    if (a)\n"
        "    {\n"
        "        if (b)\n"
        "        {\n"
        "            Target();\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    assert guard_chain(src, "void M()", "Target();") == ["a", "b"]


def test_a_braceless_guard_still_dominates():
    src = "void M()\n{\n    if (a) Target();\n}\n"
    assert guard_chain(src, "void M()", "Target();") == ["a"]


def test_a_needle_in_a_comment_is_not_found_as_code():
    src = "void M()\n{\n    // Target();\n    Other();\n}\n"
    with pytest.raises(CsParseError):
        guard_chain(src, "void M()", "Target();")


def test_an_ambiguous_needle_is_refused():
    src = "void M()\n{\n    if (a) { Target(); }\n    if (b) { Target(); }\n}\n"
    with pytest.raises(CsParseError):
        guard_chain(src, "void M()", "Target();")
