"""The translator-context pipeline (Sept 6 item e), end to end as source.

A translator sees WHERE a string is used, and one English word can carry a
different translation per noun it qualifies ("Uncommon" is feminine as a card
rarity in Russian and masculine as an item rarity). Four pieces have to agree
on one byte -- the composite key is english + U+0004 + context:

  * plugin/I18n.cs -- TrC(context, english) looks the composite up in the
    server overlay, then the locale catalogue, then falls back to Tr(english),
    so converting a site never un-translates it;
  * tools/i18n_extract.py -- harvests I18n.TrC/TrCF sites into that exact
    composite (and the plain English the fallback still reads), records
    surface/location/kind per key, writes format 2;
  * tools/i18n_sync_keys.py -- turns the record into i18n_keys.context
    (160 chars), key_id over the composite so a contextual key is its own row;
  * the portal (main.py _I18N_PORTAL_HTML) -- splits the composite for display
    and keeps submitting key_id.

The tools have no suite of their own, so they are imported by path and RUN on
a snippet, with a negative control: a context the extractor cannot harvest
must fail the run, because a key that never reaches the compiled allowlist is
a key no server pack can reach. The C# and the portal are read as text, the
way the other client-contract tests here do it.
"""

import ast
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

from _cs_structure import method_spans, strip_comments_only

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"
PLUGIN = REPO / "plugin"
I18N_CS = PLUGIN / "I18n.cs"
MAIN_PY = REPO / "backend" / "api" / "main.py"
SEP = "\u0004"   # I18n.ContextSeparator, written as an escape on purpose


def _load(name):
    spec = importlib.util.spec_from_file_location(f"scr_tools_{name}", TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def extractor():
    return _load("i18n_extract")


@pytest.fixture(scope="module")
def syncer():
    return _load("i18n_sync_keys")


# The unbalanced brace in the FIRST literal is deliberate: a method-span walk
# that does not mask literals closes RefreshCardStats there and every site
# below it falls to "(file scope)".
SNIPPET = '''
namespace CompetitiveRounds
{
    internal static class Snippet
    {
        private static void RefreshCardStats(string rarity, int n)
        {
            string d = "}";
            string a = I18n.TrC("card rarity", "Uncommon");
            string b = I18n.Tr("Uncommon");
            string c = I18n.TrCF("queue status", "{0} in queue", n);
            UIFactory.CreateText("lbl", null, "Refresh", 14f);
        }

        private static string Window() => I18n.TrC("betting window", "LOCKED");
    }
}
'''


def _harvest(extractor, src, fn="Snippet.cs"):
    found, sites = {}, {}
    extractor.harvest_source(fn, extractor.lf(src), found, sites)
    return found, sites


# ── (a) the extractor, run ───────────────────────────────────────────────────

def test_trc_site_yields_composite_key_with_context_record(extractor):
    found, sites = _harvest(extractor, SNIPPET)
    key = "Uncommon" + SEP + "card rarity"
    assert key in found and found[key] == ["Snippet.cs"]
    assert sites[key] == {("Snippet", "RefreshCardStats", "TrC:card rarity")}
    # The plain English is a DIFFERENT key, and it stays live: the explicit
    # Tr site records it, and so does the TrC site -- TrC falls back to
    # Tr(english), so the plain key is genuinely read from there.
    assert "Uncommon" in found
    assert sites["Uncommon"] == {("Snippet", "RefreshCardStats", "Tr"),
                                 ("Snippet", "RefreshCardStats", "TrC fallback")}
    # TrCF: the TEMPLATE is the English half; braces allowed exactly like TrF.
    fkey = "{0} in queue" + SEP + "queue status"
    assert sites[fkey] == {("Snippet", "RefreshCardStats", "TrCF:queue status")}
    assert sites["{0} in queue"] == {("Snippet", "RefreshCardStats", "TrCF fallback")}
    # A non-I18n helper records its own kind.
    assert sites["Refresh"] == {("Snippet", "RefreshCardStats", "CreateText")}
    # Expression-bodied member: the span runs to the terminating semicolon.
    lkey = "LOCKED" + SEP + "betting window"
    assert sites[lkey] == {("Snippet", "Window", "TrC:betting window")}


def test_plain_site_regexes_and_contextual_ones_are_disjoint(extractor):
    for site in extractor.SITES:
        assert not site[0].search('I18n.TrC("a", "b")'), site[0].pattern
        assert not site[0].search('I18n.TrCF("a", "b {0}", x)'), site[0].pattern
    for site_re, _helper in extractor.CTX_SITES:
        assert not site_re.search('I18n.Tr("b")'), site_re.pattern
        assert not site_re.search('I18n.TrF("b {0}", x)'), site_re.pattern


@pytest.mark.parametrize("call", [
    'I18n.TrC(ctxVar, "Text")',            # not a literal
    'I18n.TrC("card " + kind, "Text")',    # not ONE literal
    'I18n.TrC("card {0}", "Text")',        # braces would reach the validator
    'I18n.TrC("<b>card</b>", "Text")',     # tags likewise
    'I18n.TrC("Text")',                    # one argument
])
def test_unharvestable_context_fails_the_run(extractor, call):
    src = "class C { static void M() { string s = " + call + "; } }"
    with pytest.raises(extractor.ExtractError):
        _harvest(extractor, src)


def test_registry_is_format_2_with_flat_sorted_strings(extractor):
    found, sites = _harvest(extractor, SNIPPET)
    reg = extractor.build_registry(found, sites)
    assert reg["format"] == 2
    assert reg["strings"] == sorted(found)
    assert all(isinstance(s, str) for s in reg["strings"])
    assert set(reg["contexts"]) == set(reg["strings"])
    rec = reg["contexts"]["Uncommon" + SEP + "card rarity"]
    assert rec == {"surface": "Snippet", "location": "RefreshCardStats",
                   "kind": "TrC:card rarity"}
    # The separator survives the JSON round trip (json escapes it as \\u0004),
    # and the document is deterministic.
    back = json.loads(json.dumps(reg, ensure_ascii=False))
    assert "Uncommon" + SEP + "card rarity" in back["strings"]
    again = extractor.build_registry(*_harvest(extractor, SNIPPET))
    assert json.dumps(reg) == json.dumps(again)


def test_context_record_joins_distinct_sites_and_caps_at_three(extractor):
    found, sites = {}, {}
    for i in range(5):
        src = 'class C { static void M%d() { UIFactory.CreateButton("b", null, "Yes"); } }' % i
        extractor.harvest_source("File%d.cs" % i, src, found, sites)
    rec = extractor.build_registry(found, sites)["contexts"]["Yes"]
    assert rec["surface"] == "File0, File1, File2 +2"
    assert rec["location"] == "M0, M1, M2 +2"
    assert rec["kind"] == "CreateButton"


def test_generated_allowlist_escapes_the_separator(extractor):
    assert extractor.cs_escape("Uncommon" + SEP + "card rarity") == "Uncommon\\u0004card rarity"
    assert extractor.cs_escape('a "q" \\ b\n') == 'a \\"q\\" \\\\ b\\n'


def test_live_sites_use_trc_with_the_agreed_contexts():
    native = strip_comments_only((PLUGIN / "NativeUI.cs").read_text(encoding="utf-8"))
    for word in ("Common", "Uncommon", "Rare", "Unknown"):
        assert 'I18n.TrC("card rarity","%s")' % word in native, word
        assert 'I18n.Tr("%s")' % word not in native, word
    infoviz = strip_comments_only((PLUGIN / "InfoViz.cs").read_text(encoding="utf-8"))
    assert 'I18n.TrC("betting window", "LOCKED")' in infoviz
    assert 'I18n.Tr("LOCKED")' not in infoviz


# ── (b) the client half ──────────────────────────────────────────────────────

def _method(path, signature):
    spans = list(method_spans(path, signature))
    assert len(spans) == 1, f"{signature}: {len(spans)} blocks"
    a, b = spans[0]
    return strip_comments_only(path.read_text(encoding="utf-8"))[a:b]


def test_trc_looks_up_the_composite_then_falls_back_to_tr():
    src = I18N_CS.read_text(encoding="utf-8")
    assert re.search(r'public const string ContextSeparator\s*=\s*"\\u0004";', src), \
        "the separator is U+0004, the byte the extractor writes"
    body = _method(I18N_CS, "public static string TrC(string context, string english)")
    assert "NormalizeLf(english) + ContextSeparator + context" in body
    assert "_serverOverlay" in body and "_serverOverlayLocale == _locale" in body
    assert "_catalogues.TryGetValue(_locale" in body
    # The LAST statement is the fallback, so a composite miss never shows a
    # raw key or un-translates a site that was translated before conversion.
    assert re.sub(r"\s*}\s*$", "", body).rstrip().endswith("return Tr(english);")
    fmt = _method(I18N_CS, "public static string TrCF(string context, string template, params object[] args)")
    assert "TrC(context, template)" in fmt
    # The pack allowlist is the generated key set, which now carries the
    # composites (cs_escape writes them as \\u0004 escapes).
    emb = _method(I18N_CS, "private static bool IsEmbeddedKey(string s)")
    assert "I18nSourceKeys.Keys" in emb


# ── (c) the sync tool ────────────────────────────────────────────────────────

def test_sync_builds_context_for_client_keys_and_truncates(syncer):
    key = "Uncommon" + SEP + "card rarity"
    long_loc = "M" * 200
    data = {"format": 2, "strings": [key, "Yes", "Zzz"], "contexts": {
        key: {"surface": "NativeUI", "location": "RefreshCardStats", "kind": "TrC:card rarity"},
        "Yes": {"surface": "NativeUI, CompetitiveUI", "location": long_loc, "kind": "CreateButton"},
    }}
    keys = {k["msgctxt"]: k for k in syncer.build_client_keys(data)}
    assert keys[key]["context"] == "NativeUI · RefreshCardStats · card rarity"
    assert keys[key]["key_id"] == hashlib.sha1(("client\0" + key).encode("utf-8")).hexdigest()[:16]
    assert keys[key]["key_id"] != keys["Yes"]["key_id"]
    assert keys[key]["source_hash"] == hashlib.sha1(key.encode("utf-8")).hexdigest()
    assert keys[key]["namespace"] == "client"
    assert len(keys["Yes"]["context"]) == 160
    assert keys["Yes"]["context"].startswith("NativeUI, CompetitiveUI · MMM")
    # No record -> no field -> the server stores NULL exactly as before.
    assert "context" not in keys["Zzz"]


def test_sync_accepts_format_1_and_refuses_unknown_formats(syncer):
    old = syncer.build_client_keys({"format": 1, "strings": ["Yes"]})
    assert old[0]["key_id"] == hashlib.sha1(b"client\0Yes").hexdigest()[:16]
    assert "context" not in old[0]
    with pytest.raises(ValueError):
        syncer.build_client_keys({"format": 3, "strings": ["Yes"]})


def test_sync_sensitive_flag_reads_the_english_not_the_context(syncer):
    ranked_ctx = "Yes" + SEP + "ranked lobby"
    ranked_en = "Ranked" + SEP + "queue tab"
    got = {k["msgctxt"]: k["sensitive"] for k in syncer.build_client_keys(
        {"format": 2, "strings": [ranked_ctx, ranked_en], "contexts": {}})}
    assert got[ranked_ctx] is False
    assert got[ranked_en] is True


# ── (d) the server: sync handler and portal ──────────────────────────────────

def _py_function_source(text, name):
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node)
    raise AssertionError(f"function not found: {name}")


def test_server_sync_stores_context_for_every_namespace():
    text = MAIN_PY.read_text(encoding="utf-8")
    fn = _py_function_source(text, "admin_i18n_sync_keys")
    assert "context = EXCLUDED.context" in fn
    assert re.search(r'"kctx":\s*\(str\(k\.get\("context"\)\)\[:160\] if k\.get\("context"\) else None\)', fn)
    # The only namespace-conditional context rule is the game keys' refusal
    # of a MISSING context; a client key's context is stored like any other.
    assert 'if ns == "game" and not (k.get("context") or "").strip():' in fn
    assert 'if ns == "client"' not in fn


def _portal_html():
    text = MAIN_PY.read_text(encoding="utf-8")
    start = text.index('_I18N_PORTAL_HTML = """')
    end = text.index('"""', start + len('_I18N_PORTAL_HTML = """'))
    return text[start:end]


def test_portal_splits_the_composite_for_display_and_submits_key_id():
    html = _portal_html()
    assert "const CTX_SEP=String.fromCharCode(4);" in html
    assert "function srcEl(cls,s)" in html and "function srcText(s)" in html
    for site in ('srcEl("src",k.source)', 'srcEl("h-src",h.source)',
                 'srcEl("src",p.source)', 'srcEl("h-src",e.source)',
                 'mkEditor(srcText(k.source),k.target||"")'):
        assert html.count(site) == 1, site
    for gone in ('el("div","src",k.source)', 'el("div","h-src",h.source)',
                 'el("div","src",p.source)', 'el("div","h-src",e.source)'):
        assert gone not in html, gone
    assert ".b-ctx{" in html
    # The submit path is untouched: a proposal travels by key_id, never by
    # source text, so the composite never has to survive a round trip.
    assert "{key_id:k.key_id,language_code:rowLang,target:ed.value(),license_assent:true}" in html
