#!/usr/bin/env python3
"""Generate plugin/GameLocaleCatalogues.cs from tools/game_translations.json,
optionally overlaying APPROVED portal corrections (ship-time step; design
§6.3 / r2 find 2).

Plain regeneration (machine drafts only):
    python tools/gen_game_catalogues.py

Ship-time export with approved corrections: run this query through the deploy
host's read-only SQL verb over ssh (destination and verb are
environment-specific — the concrete invocation lives in the deploy runbook),
redirect it to approved_game.raw, then run the generator against that file:

    SELECT COALESCE(json_agg(json_build_object('k', k.key_id, 'l', e.language_code, 't', e.target, 'ash', e.approved_source_hash, 'sh', k.source_hash)), '[]'::json) FROM i18n_entries e JOIN i18n_keys k ON k.key_id = e.key_id WHERE k.namespace = 'game' AND e.state = 'approved' AND k.retired_at IS NULL;

    python tools/gen_game_catalogues.py --approved-dump approved_game.raw

The COALESCE is load-bearing (find 14): json_agg over zero rows returns NULL,
which prints as nothing, and a dump that does not parse as a JSON LIST is
REFUSED — so a failed redirect, a truncated file, or an ssh error can never
read as "no approvals" and silently rewrite both catalogues with drafts. A
genuinely empty result must arrive as an explicit [].

FRESHNESS CONTRACT (r2 find 2 — required, not advisory): an approved target
is used ONLY when approved_source_hash == the server key's CURRENT
source_hash == sha1(the LOCAL expected English). Any divergence keeps the
draft and prints the reason — a stale approval must never pair with new
English and defeat the runtime self-heal equality. Approved targets also
re-run the tag/hole validation locally before acceptance.
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TR = os.path.join(REPO, "tools", "game_translations.json")
OUT = os.path.join(REPO, "plugin", "GameLocaleCatalogues.cs")

_NAMED = re.compile(r"\{[A-Z][A-Z_]*\}")


def _tags(s):
    tags, i = [], 0
    while i < len(s):
        lt = s.find("<", i)
        if lt < 0:
            break
        gt = s.find(">", lt + 1)
        if gt < 0:
            break
        tags.append(s[lt:gt + 1])
        i = gt + 1
    return tags


def _digit_holes(s):
    toks, i, ok = [], 0, True
    while i < len(s):
        c = s[i]
        if c == "{":
            m = re.match(r"\{([0-9])(?::([^{}]*))?\}", s[i:])
            if m is None:
                ok = False
                break
            toks.append(m.group(0))
            i += m.end()
        elif c == "}":
            ok = False
            break
        else:
            i += 1
    return toks, ok


def mechanics_ok(src, tgt):
    """Tag sequence + named/digit hole identity (the validator's structural
    core, mirrored — a stale/hostile approved row must not damage markup)."""
    if _tags(src) != _tags(tgt):
        return False
    sn, tn = sorted(_NAMED.findall(src)), sorted(_NAMED.findall(tgt))
    if sn != tn:
        return False
    s2, t2 = _NAMED.sub("", src), _NAMED.sub("", tgt)
    st, s_ok = _digit_holes(s2)
    tt, t_ok = _digit_holes(t2)
    return t_ok and sorted(st) == sorted(tt)


def kid(ident):
    return hashlib.sha1(("game\0" + ident).encode("utf-8")).hexdigest()[:16]


def cs_escape(s):
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--approved-dump",
                    help="raw read-only SQL output holding the approved-entries "
                         "json_agg (see the docstring's query)")
    args = ap.parse_args()

    entries = json.load(io.open(TR, encoding="utf-8"))["entries"]
    by_kid = {kid(ident): ident for ident in entries}

    overlay = {}  # (ident, lang) -> approved target
    if args.approved_dump:
        raw = io.open(args.approved_dump, encoding="utf-8", newline="").read()
        # FAIL LOUD on anything that is not a JSON list (find 14). A zero-byte
        # file (failed ssh/redirect) or a NULL json_agg used to fall through to
        # "no approvals", so the catalogues were rewritten with machine drafts
        # and the release silently shipped without its approved corrections.
        # A legitimately empty result is an explicit [] — see the COALESCE in
        # the docstring's query.
        i, j = raw.find("["), raw.rfind("]")
        try:
            if i < 0 or j <= i:
                raise ValueError("no JSON list in the dump")
            rows = json.loads(raw[i:j + 1])
            if not isinstance(rows, list):
                raise ValueError(f"dump is {type(rows).__name__}, not a list")
            # k/l/t are dereferenced below; a malformed row must land here as
            # a message, not as a traceback halfway through the overlay.
            if any(not isinstance(r, dict) or not all(f in r for f in "klt")
                   for r in rows):
                raise ValueError("every row must be an object with k, l and t")
        except Exception as ex:  # noqa: BLE001
            print(f"--approved-dump {args.approved_dump}: {ex} "
                  f"({len(raw)} chars, first 200: {raw[:200]!r}). Re-run the "
                  f"export; an empty result must be an explicit [].",
                  file=sys.stderr)
            return 1
        for r in rows:
            ident = by_kid.get(r["k"])
            if ident is None:
                print(f"SKIP approved row for unknown key_id {r['k']}")
                continue
            local_hash = hashlib.sha1(
                entries[ident]["en"].encode("utf-8")).hexdigest()
            if not (r.get("ash") and r["ash"] == r.get("sh") == local_hash):
                print(f"SKIP stale approval {ident}/{r['l']}: "
                      f"approved={str(r.get('ash'))[:8]} server={str(r.get('sh'))[:8]} "
                      f"local={local_hash[:8]} (freshness contract)")
                continue
            if r["l"] not in ("uk", "sv"):
                continue
            if not mechanics_ok(entries[ident]["en"], r["t"]):
                print(f"SKIP approval with broken markup {ident}/{r['l']}")
                continue
            overlay[(ident, r["l"])] = r["t"]
        print(f"approved overlay: {len(overlay)} rows accepted")

    lines = []
    a = lines.append
    a("using System.Collections.Generic;")
    a("")
    a("namespace CompetitiveRounds")
    a("{")
    a("    /// <summary>")
    a("    /// Machine-draft (+ portal-approved) translations of ROUNDS' OWN")
    a("    /// string tables (StringTableDefault + StringTableCards) for locales")
    a("    /// the game does not ship. PER-KEY identity (localization-design")
    a('    /// §6.3): key = "TableName/ENTRY_KEY", value = [expectedEnglish,')
    a("    /// target]. The injector applies target only while the LIVE en entry")
    a("    /// still equals expectedEnglish; a reworded entry renders the new")
    a("    /// English instead of a stale translation, and the four PS/Xbox")
    a("    /// same-English pairs keep independent identities the portal can")
    a("    /// correct separately.")
    a("    ///")
    a("    /// GENERATED by tools/gen_game_catalogues.py from")
    a("    /// tools/game_translations.json — do not edit. At ship time, rerun")
    a("    /// with --approved-dump to fold in fresh approved portal rows")
    a("    /// (triple-hash freshness contract; see the tool's docstring).")
    a("    /// </summary>")
    a("    internal static class GameLocaleCatalogues")
    a("    {")
    a("        internal static Dictionary<string, string[]> ForLocale(string locale)")
    a("        {")
    a('            if (locale == "uk") return UK_GAME;')
    a('            if (locale == "sv") return SV_GAME;')
    a("            return null;")
    a("        }")
    for name, lang in (("UK_GAME", "uk"), ("SV_GAME", "sv")):
        a("")
        a(f"        private static readonly Dictionary<string, string[]> {name} = new Dictionary<string, string[]>")
        a("        {")
        for ident in sorted(entries):
            en = entries[ident]["en"]
            tgt = overlay.get((ident, lang), entries[ident][lang])
            a(f'            ["{cs_escape(ident)}"] = new[] {{ "{cs_escape(en)}", "{cs_escape(tgt)}" }},')
        a("        };")
    a("    }")
    a("}")
    with io.open(OUT, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {os.path.relpath(OUT, REPO)}: {len(entries)} keys x 2 locales")
    return 0


if __name__ == "__main__":
    sys.exit(main())
