#!/usr/bin/env python3
"""Dump ROUNDS' Unity.Localization string tables to tools/game_strings.json.

The base game ships 9 locales (de, en-US, es, fr, it, ja, pt-BR, ru, zh) as
addressable bundles under StreamingAssets/aa/StandaloneWindows64. This tool
reads the SharedTableData (key names) plus the en-US / ru / es string tables
and writes one JSON the base-game-locale work consumes:

  { "format": 1,
    "tables": {
      "StringTableDefault": { "<KEY>": {"en": "...", "ru": "...", "es": "...",
                                        "smart": false}, ... },
      "StringTableCards":   { ... } } }

`smart` mirrors the entry's SmartFormatTag shared metadata (PROMPT_ROOMCODE is
the only smart entry in the shipped corpus) — the runtime table injector must
set IsSmart on exactly those entries.

Also prints a glyph-coverage probe of the shared fonts for the Swedish and
Ukrainian target characters (decides per-locale font fallback needs).

Usage:  python tools/dump_base_game_tables.py [--game-dir <ROUNDS dir>]
                                              [--with-refs]
Requires: UnityPy (pip install UnityPy). Re-run after a game update; the
extractor-style rule applies — a changed key set changes the portal key set.

The CHECKED-IN tools/game_strings.json carries only the English text, the
smart flag, and Landfall's translator comments — the minimum the sync tool,
seed generator, and catalogue generator need. --with-refs additionally embeds
the official ru/es translations (translator context for a LOCAL draft pass);
keep that variant out of the repo — it is Landfall's translation work and the
public repo has no need to redistribute it.
"""
import argparse
import io
import json
import os
import sys

GAME_DEFAULT = r"C:\Program Files (x86)\Steam\steamapps\common\ROUNDS"
AA_SUB = os.path.join("ROUNDS_Data", "StreamingAssets", "aa",
                      "StandaloneWindows64")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "tools", "game_strings.json")

BUNDLES = {
    "en": "localization-string-tables-english(unitedstates)(en-us)_assets_all.bundle",
    "ru": "localization-string-tables-russian(ru)_assets_all.bundle",
    "es": "localization-string-tables-spanish(es)_assets_all.bundle",
}
SHARED = "localization-assets-shared_assets_all.bundle"
RU_ASSETS = "localization-assets-russian(ru)_assets_all.bundle"

SV_PROBE = "åäöÅÄÖé"
UK_PROBE = "ЄєІіЇїҐґ"


def load_bundle(path):
    import UnityPy
    return UnityPy.load(path)


def read_shared_table_data(aa_dir):
    """SharedTableData: table name -> {entry_id -> key_name}."""
    env = load_bundle(os.path.join(aa_dir, SHARED))
    shared = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tt = obj.read_typetree()
        if "m_TableCollectionName" in tt and "m_Entries" in tt:
            name = tt["m_TableCollectionName"]
            ids = {e["m_Id"]: e["m_Key"] for e in tt["m_Entries"]}
            shared[name] = ids
    return shared


def read_string_tables(aa_dir, bundle):
    """{table_name: {entry_id: (localized_text, is_smart, comment)}}.

    Entry metadata is a list of {rid} items resolved through the table-level
    `references.RefIds` block: class SmartFormatTag marks a smart-format
    entry; class Comment carries Landfall's own translator notes."""
    env = load_bundle(os.path.join(aa_dir, bundle))
    tables = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tt = obj.read_typetree()
        if "m_TableData" in tt and "m_Name" in tt:
            rid_map = {}
            for r in (tt.get("references") or {}).get("RefIds", []):
                rid_map[r["rid"]] = (r.get("type", {}).get("class", ""),
                                     r.get("data", {}))
            # m_Name like "StringTableDefault_en-US"
            tname = tt["m_Name"].rsplit("_", 1)[0]
            rows = {}
            for e in tt["m_TableData"]:
                smart = False
                comments = []
                for item in (e.get("m_Metadata") or {}).get("m_Items", []):
                    cls, data = rid_map.get(item.get("rid"), ("", {}))
                    if cls == "SmartFormatTag":
                        smart = True
                    elif cls == "Comment":
                        c = (data or {}).get("m_CommentText", "")
                        if c:
                            comments.append(c)
                rows[e["m_Id"]] = (e.get("m_Localized", ""), smart,
                                  " | ".join(comments))
            tables[tname] = rows
    return tables


def probe_fonts(aa_dir):
    import UnityPy
    for label, bundle in (("shared", SHARED), ("ru-assets", RU_ASSETS)):
        p = os.path.join(aa_dir, bundle)
        if not os.path.exists(p):
            print(f"[fonts] {label}: bundle missing")
            continue
        env = UnityPy.load(p)
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tt = obj.read_typetree()
            except Exception:
                continue
            if "m_CharacterTable" not in tt:
                continue
            name = tt.get("m_Name", "?")
            chars = {c.get("m_Unicode") for c in tt["m_CharacterTable"]}
            sv = "".join(c for c in SV_PROBE if ord(c) in chars)
            uk = "".join(c for c in UK_PROBE if ord(c) in chars)
            print(f"[fonts] {label}/{name}: {len(chars)} glyphs; "
                  f"sv-probe has [{sv}] missing "
                  f"[{''.join(c for c in SV_PROBE if ord(c) not in chars)}]; "
                  f"uk-probe has [{uk}]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-dir", default=GAME_DEFAULT)
    ap.add_argument("--with-refs", action="store_true")
    args = ap.parse_args()
    aa_dir = os.path.join(args.game_dir, AA_SUB)
    if not os.path.isdir(aa_dir):
        print(f"addressables dir not found: {aa_dir}", file=sys.stderr)
        return 1

    shared = read_shared_table_data(aa_dir)
    per_locale = {loc: read_string_tables(aa_dir, b)
                  for loc, b in BUNDLES.items()}

    out = {"format": 1, "tables": {}}
    for tname, ids in sorted(shared.items()):
        if not tname.startswith("StringTable"):
            continue
        rows = {}
        en = per_locale["en"].get(tname, {})
        for eid, key in sorted(ids.items(), key=lambda kv: kv[1]):
            en_text, en_smart, en_comment = en.get(eid, ("", False, ""))
            row = {"en": en_text}
            if args.with_refs:
                for loc in ("ru", "es"):
                    v = per_locale[loc].get(tname, {}).get(eid)
                    row[loc] = v[0] if v else ""
            # smart = SmartFormatTag on ANY locale's entry (the shipped smart
            # tag rides every locale's PROMPT_ROOMCODE).
            smart = en_smart or any(
                (per_locale[loc].get(tname, {}).get(eid) or ("", False, ""))[1]
                for loc in ("ru", "es"))
            row["smart"] = smart
            if en_comment:
                # Landfall's own translator note — context for drafts.
                row["comment"] = en_comment
            rows[key] = row
        out["tables"][tname] = rows
        n_smart = sum(1 for r in rows.values() if r["smart"])
        n_empty = sum(1 for r in rows.values() if not r["en"])
        print(f"{tname}: {len(rows)} keys ({n_smart} smart, "
              f"{n_empty} empty-en)")

    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"wrote {os.path.relpath(OUT, REPO)}")

    probe_fonts(aa_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
