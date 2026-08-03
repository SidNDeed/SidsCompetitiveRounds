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
    if " " not in s:
        if not re.fullmatch(r"[A-Za-z]{3,}[.!?…]{0,3}", s):
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
    if arg is None or '$"' in arg:
        return []
    lits = [x.group(1) for x in STR_LIT.finditer(arg)]
    if not lits:
        return []
    residue = re.sub(r"[\s+]+", "", STR_LIT.sub("", arg))
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
