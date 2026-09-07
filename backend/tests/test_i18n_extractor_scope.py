"""Gate for the i18n extractor's fixed file list (#464, #550): every plugin
source file with a real I18n call site must be named in tools/i18n_extract.py's
FILES, or its strings ship untranslated. #464 stated the rule in prose and six
files added by one batch were still missed, so the rule is a test now.
Comment-only mentions (BroadcastHud.cs says it is English-only by design) do
not count; a call site is `I18n.Tr(`, `TrF(`, `TrC(` or `TrCF(` outside a
`//` comment."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"
EXTRACTOR = ROOT / "tools" / "i18n_extract.py"
CALL = re.compile(r"\bI18n\.Tr(?:F|C|CF)?\s*\(")


def _files_list(text):
    m = re.search(r"(?ms)^FILES = \[(.*?)^\]", text)
    assert m, "FILES list not found in the extractor"
    return set(re.findall(r'"([^"]+\.cs)"', m.group(1)))


def _call_sites(path):
    n = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("//"):
            continue
        n += len(CALL.findall(line.split("//", 1)[0]))
    return n


def _unscanned(listed, plugin_dir):
    return sorted(p.name for p in plugin_dir.glob("*.cs")
                  if p.name not in listed and _call_sites(p) > 0)


def test_every_plugin_file_with_i18n_sites_is_scanned():
    listed = _files_list(EXTRACTOR.read_text(encoding="utf-8"))
    assert len(listed) > 20, "the FILES list parsed too small to be the real one"
    missing = _unscanned(listed, PLUGIN)
    assert not missing, ("plugin files with I18n call sites the extractor does not scan "
                         "(add them to FILES in tools/i18n_extract.py): " + ", ".join(missing))


def test_scope_gate_can_fail():
    """Negative control (#391): removing a scanned file from the list makes
    the gate name it."""
    listed = _files_list(EXTRACTOR.read_text(encoding="utf-8"))
    victim = "MailUI.cs"
    assert victim in listed and _call_sites(PLUGIN / victim) > 0
    assert victim in _unscanned(listed - {victim}, PLUGIN)


def test_comment_mentions_do_not_count():
    assert _call_sites(PLUGIN / "BroadcastHud.cs") == 0
    assert _call_sites(PLUGIN / "MailClient.cs") > 30
