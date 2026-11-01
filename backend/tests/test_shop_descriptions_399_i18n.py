"""The 19 descriptions migration 399 writes are client translation keys with a
row in every bundled language, the way the five v1.41.0 faces' shipped
description is (13b824fc): tools/shop_strings.json, the extractor's outputs
(tools/i18n_source.json, plugin/I18nSourceKeys.g.cs), one N rule:N1
disposition in tools/keybind_surfaces.tsv, and an es/ru/uk/sv row in
plugin/I18nCatalogues.cs. The client renders a shop description through
I18n.Tr, an ordinal lookup by the exact English text, so a text missing here
shows in English in all four languages.
"""
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend" / "sql" / "399_shop_face_descriptions.sql"
SHOP_STRINGS = ROOT / "tools" / "shop_strings.json"
SOURCE = ROOT / "tools" / "i18n_source.json"
KEYS = ROOT / "plugin" / "I18nSourceKeys.g.cs"
SURFACES = ROOT / "tools" / "keybind_surfaces.tsv"
CATALOGUES = ROOT / "plugin" / "I18nCatalogues.cs"

# Per language: the slot words the placeholders' rows use, the house tail,
# and the word for "(animated)" the house rows use.
LANGS = {
    "ES": ({"Detail": "Detalle:", "Eyes": "Ojos:", "Mouth": "Boca:"}, " en el editor de personaje.", "(animad"),
    "RU": ({"Detail": "Деталь:", "Eyes": "Глаза:", "Mouth": "Рот:"}, " в редакторе персонажа.", "(анимация)"),
    "UK": ({"Detail": "Деталь:", "Eyes": "Очі:", "Mouth": "Рот:"}, " в редакторі персонажа.", "(анімація)"),
    "SV": ({"Detail": "Detalj:", "Eyes": "Ögon:", "Mouth": "Mun:"}, " Utrusta i karaktärseditorn.", "(animerad)"),
}
ROW_RE = re.compile(r'^\s*\["((?:[^"\\]|\\.)*)"\] = "((?:[^"\\]|\\.)*)",\s*$')


def _new_texts():
    text = MIGRATION.read_text(encoding="utf-8")
    rows = re.findall(r"\['(\d+)', '([a-z_]+)', '((?:[^']|'')*)', '((?:[^']|'')*)'\]", text)
    assert len(rows) == 19
    return [r[3].replace("''", "'") for r in rows]


def _dicts():
    lines = CATALOGUES.read_text(encoding="utf-8").splitlines()
    starts = []
    for k, l in enumerate(lines):
        m = re.search(r"static readonly Dictionary<string, string> (ES|RU|UK|SV) = ", l)
        if m:
            starts.append((k, m.group(1)))
    out = {}
    for n, (k, lang) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        rows = {}
        for l in lines[k:end]:
            m = ROW_RE.match(l)
            if m:
                rows.setdefault(m.group(1), []).append(m.group(2))
        out[lang] = rows
    return out


def test_every_text_is_a_shop_display_string():
    strings = json.loads(SHOP_STRINGS.read_text(encoding="utf-8"))["strings"]
    assert strings == sorted(strings)
    for t in _new_texts():
        assert strings.count(t) == 1, t


def test_every_text_is_an_extracted_key():
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    flat = json.dumps(src, ensure_ascii=False)
    keys = KEYS.read_text(encoding="utf-8")
    for t in _new_texts():
        assert json.dumps(t, ensure_ascii=False) in flat, t
        assert keys.count('"%s",' % t) == 1, t


def test_every_text_has_its_n1_disposition():
    rows = [l.split("\t") for l in SURFACES.read_text(encoding="utf-8").splitlines()[1:]]
    by_text = {}
    for r in rows:
        by_text.setdefault(r[3], []).append(r)
    for t in _new_texts():
        assert by_text.get(t) == [[hashlib.sha1(t.encode("utf-8")).hexdigest()[:16], "N", "rule:N1", t]], t


def test_every_text_has_a_row_in_every_language():
    dicts = _dicts()
    assert sorted(dicts) == sorted(LANGS)
    for t in _new_texts():
        slot = t.split(":", 1)[0]
        for lang, (slots, tail, anim) in LANGS.items():
            got = dicts[lang].get(t)
            assert got is not None and len(got) == 1, (lang, t)
            tr = got[0]
            assert tr and tr != t, (lang, t)
            assert tr.startswith(slots[slot] + " "), (lang, t, tr)
            assert tr.endswith(tail), (lang, t, tr)
            assert (anim in tr) == ("(animated)" in t), (lang, t, tr)
