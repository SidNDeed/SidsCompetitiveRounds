"""i18n extraction tool (localization-design.md §2.8).

Scans the plugin source for translatable DISPLAY literals at the known
chokepoint call sites and emits a catalogue source list:

    python tools/i18n_extract.py            # summary + writes tools/i18n_source.json
    python tools/i18n_extract.py --diff     # compare against the existing json
                                            # (the build-gate / churn-budget mode:
                                            # prints added/removed source strings
                                            # so a polish pass announces how many
                                            # approved translations it invalidates)

Extraction scope (deliberately conservative — a display string is one passed
at the TEXT argument of a UI factory; identity strings never travel through
these positions):
  - UIFactory.CreateText(name, parent, TEXT, ...)
  - UIFactory.SetText(target, TEXT)
  - UIFactory.CreateButton(name, parent, LABEL, ...)
  - CompetitiveUI.ShowNotification(TEXT, ...)
  - ShowInfoPopup(TITLE, BODY) title literals
Skips: empty strings, pure-markup/format scraps (< 2 letters), strings that
are obviously identity-ish (no spaces AND no letters beyond [A-Za-z0-9_]) —
those are keys, not prose.

The DO-NOT-TRANSLATE class (status enums, SKUs, room prefixes, HMAC fields,
card names) never reaches these argument positions, but keep new call sites
honest: if you route an identity string through CreateText, it becomes
translatable and WILL corrupt comparisons.
"""
import io
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "plugin")
OUT = os.path.join(REPO, "tools", "i18n_source.json")

FILES = [
    "NativeUI.cs", "CompetitiveUI.cs", "Plugin.cs", "ApiClient.cs",
    "FfaMode.cs", "ModeInfoText.cs", "TabStatsOverlay.cs", "GameStateWatcher.cs",
    "MatchTracker.cs", "VanillaFixes.cs", "QuickChat.cs",
]

# call(...) sites and which ARGUMENT POSITIONS carry display text (wave-2
# find 4: the old scheme counted string LITERALS, not arguments — a call
# whose earlier args weren't literals shifted the index onto the wrong
# literal, silently dropping ~150 live display strings).
SITES = [
    (re.compile(r'UIFactory\.CreateText\s*\('), (2,)),
    (re.compile(r'UIFactory\.SetText\s*\('), (1,)),
    (re.compile(r'UIFactory\.CreateButton\s*\('), (2,)),
    (re.compile(r'CompetitiveUI\.ShowNotification\s*\('), (0,)),
    (re.compile(r'(?<![.\w])ShowNotification\s*\('), (0,)),
    (re.compile(r'(?<![.\w])QueueNotification\s*\('), (0,)),
    (re.compile(r'ShowInfoPopup\s*\('), (0, 1)),
    (re.compile(r'(?<![.\w])SettingsToggle\s*\('), (4,)),
    (re.compile(r'I18n\.Tr\s*\('), (0,), True),
    (re.compile(r'I18n\.TrF\s*\('), (0,), True),
    (re.compile(r'(?<![.\w])AppendSystemChatLine\s*\('), (0,)),
]

STR_LIT = re.compile(r'"((?:[^"\\]|\\.)*)"')


def looks_translatable(s: str, allow_braces: bool = False) -> bool:
    if not s or len(s) < 2:
        return False
    letters = sum(1 for c in s if c.isalpha())
    if letters < 2:
        return False
    # Identity-ish single tokens: skus/prefixes/statuses carry '_'/'-'/digits
    # ("cr_ff", "ranked_", "sct-1"); a single token at a DISPLAY argument
    # position that is alpha with optional TRAILING punctuation is a real
    # label ("Settings", "Refresh", "Loading...", "Failed") — round-3 find
    # N3 + round-4 find F4 (the alpha-only rule dropped "Loading...").
    # Aug-3 recon: run the check on the MARKUP-STRIPPED text — a markup-
    # wrapped single word ("<color=#8899AA>Search</color>") is spaceless as
    # a raw literal and was silently dropped forever.
    _bare = re.sub(r"<[^>]{0,40}>", "", s)
    if " " not in _bare:
        # Codex review: a display LABEL may end in ':' ("Timezone:") — the old
        # pattern allowed only .!?… so such labels silently fell out of the key
        # set entirely and could never be translated, not even by a server pack.
        # Trailing '%' joined the allowed suffix set (Aug-3 completeness pass:
        # the "Pass%" column header could never be a key).
        ok_simple = re.fullmatch(r"[A-Za-z]{3,}[.!?…:%]{0,3}", _bare)
        # Aug-3 Codex find 10: display tokens with INTERIOR punctuation were
        # unreachable forever ("He/him", "They/them", "same-card", "(you)",
        # "+pick", "Day/Month/Year"). Identity strings stay excluded because
        # they carry digits or underscores ("cr_ff", "sct-1", "ranked_").
        ok_punct = (re.fullmatch(r"[+(]?[A-Za-z][A-Za-z/()'’.-]*[.!?…:%]{0,3}", _bare)
                    and sum(1 for c in _bare if c.isalpha()) >= 3
                    and not any(c.isdigit() or c == "_" for c in _bare))
        if not (ok_simple or ok_punct):
            return False
    # An interpolation HOLE normally means a $-string BODY (compiler-composed;
    # a whole-string key can never match) — EXCEPT at I18n.Tr/TrF sites, where
    # the braces-bearing TEMPLATE is exactly the catalogue key (find N3: the
    # chat-header TrF template needs a server-correctable key).
    if ("{" in s or "}" in s) and not allow_braces:
        return False
    # markup-only scraps, URLs, debug tags, JSON payloads
    stripped = re.sub(r"<[^>]{0,40}>", "", s).strip()
    if len(stripped) < 3 or sum(1 for c in stripped if c.isalpha()) < 3:
        return False
    if s.startswith(("http", "file:", "[", "\"")) or "://" in s:
        return False
    return True


def unescape(s: str) -> str:
    return s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def find_call_body(src: str, open_paren: int) -> str:
    """The text between the call's parens, string-aware."""
    depth = 0
    end = open_paren
    while end < len(src) and end < open_paren + 8000:
        c = src[end]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return src[open_paren + 1:end]
        elif c == '"':
            e2 = end + 1
            while e2 < len(src):
                if src[e2] == '\\':
                    e2 += 2
                    continue
                if src[e2] == '"':
                    break
                e2 += 1
            end = e2
        end += 1
    return ""


def split_top_level_args(body: str) -> list:
    """Split a call body on top-level commas (string/paren/bracket-aware)."""
    args, buf, depth, i = [], [], 0, 0
    while i < len(body):
        c = body[i]
        if c == '"':
            buf.append(c)
            i += 1
            while i < len(body):
                buf.append(body[i])
                if body[i] == '\\':
                    i += 1
                    if i < len(body):
                        buf.append(body[i])
                elif body[i] == '"':
                    break
                i += 1
        elif c in '([{':
            depth += 1
            buf.append(c)
        elif c in ')]}':
            depth -= 1
            buf.append(c)
        elif c == ',' and depth == 0:
            args.append(''.join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    if buf:
        args.append(''.join(buf))
    return args


def arg_literals(arg: str) -> list:
    """The argument's display string(s). A PURE literal or compile-time-
    folded concatenation yields one joined string. A ternary/conditional arg
    whose branches are literals (round-3 find N3: both consent-button texts
    live in `cond ? "a" : "b"`) yields EACH literal separately — a spurious
    condition-embedded literal costs a harmless extra key; a missing branch
    costs a translator-invisible surface. $-string args yield nothing (the
    compiler composes them; whole-string keys can never match)."""
    if arg is None:
        return []
    # Aug-3 recon: bailing on '$"' ANYWHERE in the arg dropped every PLAIN
    # literal branch of a ternary whose OTHER branch was interpolated
    # (`cond ? "Queue stalled" : $"...{x}..."` lost "Queue stalled" — this
    # alone killed several live notices). Strip $-strings FIRST; they become
    # non-literal residue, so a pure $-string arg still yields nothing and a
    # folded literal+$-string concatenation still yields nothing (correct:
    # the rendered string is compiler-composed) — but ternary/?? branches
    # that are themselves plain literals harvest.
    arg = re.sub(r'\$"(?:[^"\\]|\\.)*"', "INTERP", arg)
    lits = [x.group(1) for x in STR_LIT.finditer(arg)]
    if not lits:
        return []
    # '@' is the C# verbatim-string marker (ModeInfoText's whole-doc Tr/TrF
    # bodies) — strippable residue like whitespace/'+'. CONSTRAINT: a verbatim
    # literal harvests correctly only while it contains no backslashes (C#
    # treats them literally; unescape() here would transform them) and no ""
    # escaped quotes (STR_LIT would terminate early). The ModeInfoText bodies
    # satisfy both; keep it that way.
    residue = re.sub(r"[\s+@]+", "", STR_LIT.sub("", arg))
    if residue == "":
        return [unescape("".join(lits))]   # pure (possibly folded) literal
    if "?" in residue and ":" in residue:
        return [unescape(x) for x in lits]  # conditional — harvest branches
    if "??" in residue:
        # Null-coalescing fallback (round-4 find F4): `expr ?? "Failed"` —
        # the literal is the display fallback and must be a key.
        return [unescape(x) for x in lits]
    return []


def extract():
    found = {}
    # Server-data display strings (Sid Aug-3 item 3: shop/cosmetic names +
    # descriptions are translated now). The client renders them via
    # I18n.Tr(variable) — invisible to call-site harvesting — so the key set
    # ingests them from a checked-in snapshot of the live catalog
    # (tools/shop_strings.json, regenerated from prod when items ship).
    # This keeps them portal-moderatable like every other key.
    shop_path = os.path.join(REPO, "tools", "shop_strings.json")
    # FAIL LOUD (Aug-3 Codex find 11): a missing or malformed file must not
    # silently retire ~400 shop keys while the extractor exits 0 and writes
    # apparently-valid registries.
    if not os.path.exists(shop_path):
        print("ERROR: tools/shop_strings.json missing — its keys would silently retire")
        sys.exit(1)
    try:
        _shop = json.load(io.open(shop_path, encoding="utf-8"))
        if not isinstance(_shop, dict) or _shop.get("format") != 1:
            raise ValueError("expected an object with format == 1")
        _lst = _shop.get("strings")
        if (not isinstance(_lst, list) or not _lst
                or not all(isinstance(x, str) and x.strip() for x in _lst)):
            raise ValueError("'strings' must be a non-empty list of non-blank strings")
        for s in _lst:
            if looks_translatable(s):
                found.setdefault(s, []).append("shop_strings.json")
    except SystemExit:
        raise
    except Exception as ex:
        print(f"ERROR: shop_strings.json invalid ({ex})")
        sys.exit(1)
    for fn in FILES:
        path = os.path.join(PLUGIN, fn)
        if not os.path.exists(path):
            continue
        src = io.open(path, encoding="utf-8").read()
        for site in SITES:
            site_re, arg_positions = site[0], site[1]
            allow_braces = site[2] if len(site) > 2 else False
            for m in site_re.finditer(src):
                body = find_call_body(src, m.end() - 1)
                if not body:
                    continue
                args = split_top_level_args(body)
                for pos in arg_positions:
                    if pos >= len(args):
                        continue
                    for s in arg_literals(args[pos].strip()):
                        if looks_translatable(s, allow_braces=allow_braces):
                            found.setdefault(s, []).append(f"{fn}")
        # QuickChat phrase table: the wire keys ARE the English sources.
        if fn == "QuickChat.cs":
            block = re.search(r"Phrases\s*=\s*\{(.*?)\};", src, re.S)
            if block:
                for x in STR_LIT.finditer(block.group(1)):
                    s = unescape(x.group(1))
                    if looks_translatable(s):
                        found.setdefault(s, []).append(fn)
        # Achievement definition table (ApiClient.cs): display name + desc
        # live in a dict INITIALIZER, never at a harvested call site (the
        # render sites pass def[0]/def[1] variables). Harvest ONLY the
        # literals inside each row's value array (new[]{ name, desc }) — the
        # dictionary KEYS are wire ids ("regicide", "on_fire"); pure-alpha
        # ids would pass looks_translatable and pollute the key set if the
        # whole block were harvested QuickChat-style.
        if fn == "ApiClient.cs":
            block = re.search(
                r"AchievementDefs\s*=\s*new\s+Dictionary<string,\s*string\[\]>\s*\{(.*?)\n\s*\};",
                src, re.S)
            if block:
                for arr in re.finditer(r"new\[\]\s*\{([^}]*)\}", block.group(1)):
                    for x in STR_LIT.finditer(arr.group(1)):
                        s = unescape(x.group(1))
                        if looks_translatable(s):
                            found.setdefault(s, []).append(fn)
    return found


def main():
    found = extract()
    entries = sorted(found.keys())
    if "--diff" in sys.argv and os.path.exists(OUT):
        old = set(json.load(io.open(OUT, encoding="utf-8"))["strings"])
        new = set(entries)
        added, removed = sorted(new - old), sorted(old - new)
        print(f"ADDED {len(added)} / REMOVED {len(removed)} source strings")
        for s in added:
            print(f"  + {s[:90]!r}")
        for s in removed:
            print(f"  - {s[:90]!r}")
        if removed:
            print(f"\nCHURN BUDGET: this pass invalidates {len(removed)} approved "
                  f"translations per shipped language (localization-design Q5).")
        return
    json.dump({"format": 1, "strings": entries},
              io.open(OUT, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    total_chars = sum(len(s) for s in entries)
    print(f"extracted {len(entries)} distinct display strings "
          f"({total_chars} chars) -> {os.path.relpath(OUT, REPO)}")
    # Compiled source-key registry (round-3 find N5): the client's pack
    # allowlist must be the EXTRACTED source set, not the translated
    # dictionaries — an extracted-but-not-yet-translated key is exactly the
    # one a server correction needs to reach. Regenerate + rebuild whenever
    # extraction changes.
    cs = os.path.join(PLUGIN, "I18nSourceKeys.g.cs")
    def cs_escape(s):
        return (s.replace("\\", "\\\\").replace('"', '\\"')
                 .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
    with io.open(cs, "w", encoding="utf-8", newline="\n") as f:
        f.write("// AUTO-GENERATED by tools/i18n_extract.py — do not edit.\n")
        f.write("// The extracted translatable source set; I18n's pack\n")
        f.write("// allowlist (server packs may only override these keys).\n")
        f.write("namespace CompetitiveRounds\n{\n")
        f.write("    internal static class I18nSourceKeys\n    {\n")
        f.write("        internal static readonly string[] Keys =\n        {\n")
        for s in entries:
            f.write(f'            "{cs_escape(s)}",\n')
        f.write("        };\n    }\n}\n")
    print(f"emitted {os.path.relpath(cs, REPO)} ({len(entries)} keys)")


if __name__ == "__main__":
    main()
