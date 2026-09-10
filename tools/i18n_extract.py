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
  - CompetitiveUI.ShowNotification(TEXT, ...) and ShowNotificationCritical
  - ShowInfoPopup(TITLE, BODY) title literals
Skips: empty strings, pure-markup/format scraps (< 2 letters), strings that
are obviously identity-ish (no spaces AND no letters beyond [A-Za-z0-9_]) —
those are keys, not prose.

The DO-NOT-TRANSLATE class (status enums, SKUs, room prefixes, HMAC fields,
card names) never reaches these argument positions, but keep new call sites
honest: if you route an identity string through CreateText, it becomes
translatable and WILL corrupt comparisons.

LINE-ENDING CONTRACT — EMITTED KEYS ARE ALWAYS LF.
The plugin sources are checked out CRLF on Windows (no .gitattributes,
core.autocrlf=true), and a C# VERBATIM literal (@"...") embeds the file's
actual line endings — so ModeInfoText's mode docs and NativeUI's tournament
instruction blocks contain "\r\n" at runtime while this extractor emitted
"\n" keys (Python universal newlines silently translated them on read).
I18n.Tr is an ORDINAL dictionary lookup, so every one of those multi-line
sources was a guaranteed permanent miss: the popup TITLES translated and the
BODIES stayed English on every machine, even after a restart.
Both ends are now explicit rather than incidental: this file reads with
newline="" and normalizes to LF itself (so the behaviour does not depend on
Python's universal-newline default), and I18n.NormalizeLf converts at lookup
and install time. Do NOT "fix" it by rewriting those literals into \n-joined
regular strings — that changes the English source, which re-keys them and
orphans every existing es/ru translation (learning #289).

CONTEXT FOR TRANSLATORS (Sept 6 item e) — output format 2.
I18n.TrC("ctx", "text") and I18n.TrCF("ctx", "fmt", ...) harvest the COMPOSITE
key  text + U+0004 + ctx  (I18n.ContextSeparator — a character no UI string
carries), so one English word can carry a different translation per noun it
qualifies; the plain English is harvested from the same site too, because TrC
falls back to Tr(english) and so still reads it. Every key also gets a context
record — surface (file stem), location (enclosing method, a heuristic) and
kind (the helper: "CreateText", "Tr", "TrC:card rarity") — written under
"contexts"; "strings" stays the flat sorted list format 1 wrote, so older
readers keep working. tools/i18n_sync_keys.py turns the record into
i18n_keys.context, which the portal shows under each source string.
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
    # Spectator mode (Aug 6 item 13) — new files with user-visible Tr() text.
    "SpectatorHud.cs", "SpectatorJoiner.cs", "SpectatorSync.cs",
    # Esc-menu leave confirm (Aug 12, DC #1).
    "EscMenuLeaveGuard.cs",
    # Post-session report screens (Aug 19, W7) — ~70 Tr sites; a new file
    # must be listed HERE or its keys are silently unharvestable (#357).
    "PostSessionReport.cs",
    # Info library (Aug 23) — the explainer wiki: ~31 large verbatim bodies
    # plus category/article titles, all at I18n.Tr sites.
    "InfoLibrary.cs",
    # Info-tab visualizations (Aug 30) — chart headers/captions/legends at
    # I18n.Tr sites; numeric labels deliberately raw.
    "InfoViz.cs",
    # Esc-menu LEAVE MATCH row (Aug 30) — labels + honest leave copy.
    "EscLeaveRow.cs",
    # Music feature (Sept 2) — download status lines (MusicAssets), the
    # now-playing credit format (MusicEngine). MusicCatalog/MusicEntitlements
    # deliberately absent: album/track/artist text stays raw (#368) and their
    # log lines are not user-visible.
    "MusicAssets.cs", "MusicEngine.cs",
    # Overlay idle-close (Sept 4) — broadcast-only since review r4, so it has
    # no translation sites today; listed so a future player-seat variant
    # (which would need a toast) is harvested the moment it appears.
    "OverlayIdleClose.cs",
    # In-room head-to-head line (Sept 4, Release B §1) — banner/Tab-Info
    # templates and the relative-day phrases, all at I18n.Tr/TrF sites.
    "H2HSummary.cs",
    # Lag notices (Sept 4, Release B §4) — the four corner-notice texts at
    # I18n.Tr/TrF sites; its [LAG-NOTICE] log lines are not user-visible.
    "LagNotices.cs",
    # Sept 6 batch, Group 4 (all at I18n.Tr/TrF sites): the hover profile card,
    # the in-game mail client + screens, the session report model + view and
    # the rating-graph axes. The list is FIXED, so every new source file with
    # display strings must be named here or its strings ship untranslated
    # (found by the Sept 6 integration: 195 sites in six unnamed files).
    "ProfileCard.cs", "MailClient.cs", "MailUI.cs",
    "SessionReportModel.cs", "SessionReportView.cs", "RatingGraphAxis.cs",
    # Older omissions found by the same sweep: the minimised-chat suffix
    # (Sept 6 Group 2, bug 333) and the team-colour point announcements.
    "ChatOverlayTmp.cs", "TeamColorIdentity.cs",
    # Room rules (Sept 10): the friendly-fire / same-cards summaries and the
    # game-start toast, all at I18n.Tr/TrF sites.
    "RoomRules.cs",
]

# call(...) sites and which ARGUMENT POSITIONS carry display text (wave-2
# find 4: the old scheme counted string LITERALS, not arguments — a call
# whose earlier args weren't literals shifted the index onto the wrong
# literal, silently dropping ~150 live display strings).
SITES = [
    (re.compile(r'UIFactory\.CreateText\s*\('), (2,)),
    (re.compile(r'UIFactory\.SetText\s*\('), (1,)),
    (re.compile(r'UIFactory\.CreateButton\s*\('), (2,)),
    # NOTE: the (?:Critical)? alternative is load-bearing — converting a
    # call site to ShowNotificationCritical must NOT retire its translation
    # key (Aug 12: four shipped keys were silently dropped that way, #289).
    (re.compile(r'CompetitiveUI\.ShowNotification(?:Critical)?\s*\('), (0,)),
    (re.compile(r'(?<![.\w])ShowNotification(?:Critical)?\s*\('), (0,)),
    (re.compile(r'(?<![.\w])QueueNotification\s*\('), (0,)),
    (re.compile(r'ShowInfoPopup\s*\('), (0, 1)),
    (re.compile(r'(?<![.\w])SettingsToggle\s*\('), (4,)),
    # Shop section headers (impl-r2 I16 residual): the builder's own
    # CreateText receives the label VARIABLE (Tr'd at that single funnel), so
    # the display literal — markup included, like every markup-wrapped key —
    # is only visible at the CreateSectionHeader CALL sites (parent, name,
    # LABEL). The method-definition line also matches this pattern; its
    # parameter list carries no literals, so it harvests nothing (harmless).
    (re.compile(r'(?<![.\w])CreateSectionHeader\s*\('), (2,)),
    (re.compile(r'I18n\.Tr\s*\('), (0,), True),
    (re.compile(r'I18n\.TrF\s*\('), (0,), True),
    (re.compile(r'(?<![.\w])AppendSystemChatLine\s*\('), (0,)),
]

STR_LIT = re.compile(r'"((?:[^"\\]|\\.)*)"')

# A positional format hole, including a format spec ("{0}", "{1:F0}").
_HOLE = re.compile(r"\{\d+[^{}]*\}")


# Explicit, hand-listed exemptions to the 3-letter floor, for COMPLETE lines
# whose English is genuinely this short and whose display we do not want to
# change to satisfy a heuristic.
#
# Both entries below are the whole in-match status line for a mode with only
# one side to name (a 1v2 solo has no teammates; a read with no opponents
# resolved has no foes). Their sibling "w/ {0}   vs {1}" clears the normal
# floor on its own, so without these two the same surface would be translated
# in the common case and English in the edge cases — worse than either.
#
# This list is ADDITIVE ONLY: an entry here can add a key, never remove or
# rewrite one, so a mistake costs an unused catalogue row rather than data
# (contrast learning #183, where a hand-maintained list gated a DESTRUCTIVE
# backfill). Do not use it to smuggle in connector glue — a fragment spliced
# into another sentence still belongs inside its parent template (#298c).
SHORT_WHOLE_LINES = frozenset({
    "w/ {0}",
    "vs {0}",
})


def is_whole_template(s: str) -> bool:
    """True for a COMPLETE template whose only prose is one short label.

    The 3-letter floor in looks_translatable exists to keep connector GLUE out
    of the key set (learning #295c): a fragment like " in {0}" must never
    become a key, because a translator seeing it in isolation cannot know the
    words it splices between, and compose-after-Tr is this codebase's recurring
    i18n bug shape (#298c). But "Lv {0}" is not glue — it is the whole string
    the player reads, and under the blanket floor it could never be translated
    at all, not even by a server pack.

    So the exemption is shaped to admit only strings that stand on their own,
    and is checked against the RAW literal (never the markup-stripped/trimmed
    form — trimming would erase the very whitespace that identifies glue):
      - it must carry a positional hole, and must not be padded with the
        whitespace a connector needs to splice between its neighbours, so
        " in {0}" and " - {0}" stay rejected;
      - it must OPEN with a CAPITALIZED label, so hole-first scaffolding
        ("{0} of {1}"), anything that is only punctuation plus a hole, and
        lowercase words that continue someone else's sentence all stay
        rejected. Capitalization is the only signal that separates a label
        from a connector at this length: "Lv" and "vs" are lexically
        indistinguishable, but a string a player reads as a unit starts a
        sentence and a spliced fragment does not. Verified against the live
        source: without this clause the exemption also admitted "vs {0}"
        (CompetitiveUI's match-status bar builds its line as
        TrF("w/ {0}   ") + TrF("vs {0}"), i.e. compose-after-Tr — the fix
        for that surface is one whole template at the call site, not two
        fragment keys here);
      - removing the holes must leave exactly ONE alphabetic label token, so
        multi-hole sentence scaffolding can never qualify.

    Do NOT widen this further. Anything that reads as a phrase fragment rather
    than a standalone label belongs inside its parent template, not in the
    catalogue as a separate key.

    Only reachable at I18n.Tr/TrF sites: the braces gate in looks_translatable
    already rejects every brace-bearing string harvested anywhere else.
    """
    if not _HOLE.search(s):
        return False
    if s != s.strip():
        return False
    # isupper() is False for '{', '(', '+', a space and a digit too, so this
    # single test enforces both "opens with a label" and "that label is
    # capitalized".
    if not s[:1].isupper():
        return False
    label = _HOLE.sub(" ", s).strip()
    return bool(re.fullmatch(r"[A-Za-z]{2,}[.!?…:%]{0,3}", label))


def looks_translatable(s: str, allow_braces: bool = False) -> bool:
    # The explicit allowlist short-circuits EVERY heuristic below, not just the
    # 3-letter floor: "w/ {0}" carries a single letter and was being rejected by
    # the 2-letter guard on the next line long before the floor's exemption ran.
    # An entry here is a human asserting "this exact string is a complete line",
    # which is strictly more information than any of these rules can recover.
    if s in SHORT_WHOLE_LINES:
        return True
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
        # ...unless the whole string IS a template ("Lv {0}"); see
        # is_whole_template for why the floor cannot simply be lowered, and
        # SHORT_WHOLE_LINES for the two hand-listed complete lines that are
        # shorter than any predicate can safely admit in general.
        if s not in SHORT_WHOLE_LINES and not is_whole_template(s):
            return False
    if s.startswith(("http", "file:", "[", "\"")) or "://" in s:
        return False
    return True


def lf(s: str) -> str:
    """LF-canonical form of a harvested key (see the module docstring).

    Applied to EVERY string that enters the key set, whatever its route:
    verbatim literals carry the source file's real CRLFs, escaped literals can
    spell "\\r\\n" explicitly, and shop_strings.json can carry either. The
    client mirrors this exactly in I18n.NormalizeLf.
    """
    if s is None or "\r" not in s:
        return s
    return s.replace("\r\n", "\n").replace("\r", "\n")


def unescape(s: str) -> str:
    return (s.replace('\\"', '"').replace("\\n", "\n")
             .replace("\\r", "\r").replace("\\\\", "\\"))


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


# ── Context for translators (Sept 6 item e) ──────────────────────────────────
# I18n.TrC("ctx", "text") / I18n.TrCF("ctx", "fmt", ...) give one English word
# a translation PER NOUN it qualifies. The catalogue key is the composite
# text + CTX_SEP + ctx, byte-for-byte what I18n.TrC looks up (U+0004 appears
# in no UI string, so a composite can never collide with a plain key).
CTX_SEP = "\u0004"
CTX_SITES = [
    (re.compile(r'I18n\.TrC\s*\('), "TrC"),
    (re.compile(r'I18n\.TrCF\s*\('), "TrCF"),
]
# A context is a short noun phrase. No braces, no '<', no quotes: the server
# validator reads the whole msgctxt as the source, so a brace or a tag inside
# the context would become a hole/tag every translation had to reproduce.
CTX_OK = re.compile(r"[A-Za-z][A-Za-z0-9 _/-]{1,59}")


class ExtractError(Exception):
    """A call site this tool cannot harvest. FAIL LOUD (the shop_strings.json
    rule): the client's pack allowlist is this tool's output, so a key that
    silently never made it here is a key no server correction can reach."""


def context_literal(arg: str, fn: str, helper: str) -> str:
    """The context argument of a TrC/TrCF call: exactly ONE plain literal."""
    lits = [x.group(1) for x in STR_LIT.finditer(arg)]
    residue = re.sub(r"\s+", "", STR_LIT.sub("", arg))
    if len(lits) != 1 or residue != "":
        raise ExtractError(f"{fn}: {helper} context must be one string literal, got {arg[:60]!r}")
    ctx = unescape(lits[0])
    if not CTX_OK.fullmatch(ctx):
        raise ExtractError(f"{fn}: {helper} context {ctx!r} must be 2-60 letters, digits, "
                           "spaces, '-', '/' or '_' (no braces, tags or quotes)")
    return ctx


def kind_of(m) -> str:
    """The helper a harvested string went through, read off the matched call
    text: 'UIFactory.CreateText(' -> 'CreateText', 'I18n.TrF(' -> 'TrF'."""
    return re.sub(r"[\s(]+$", "", m.group(0)).split(".")[-1]


def _mask_cs(src: str) -> str:
    """Length-preserving copy of a C# source with comment text and the INSIDE
    of string/char literals blanked, so brace depth and method signatures can
    be read without a '{' in a log line or a '(' in a format string counting.
    Newlines survive, so an offset into the result is an offset into `src`.
    Regular, verbatim (@"", "" escapes) and interpolated prefixes are handled;
    a nested quote inside an interpolation hole may mis-tokenize a few
    characters, which is why enclosing_method is documented as a heuristic."""
    out = list(src)
    n = len(src)

    def blank(a, b):
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    i = 0
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        nxt2 = src[i + 2] if i + 2 < n else ""
        if c == "/" and nxt == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif c == '"' or (c in "@$" and nxt == '"') or (c in "@$" and nxt in "@$" and nxt2 == '"'):
            q = src.index('"', i)                 # the opening quote
            verbatim = "@" in src[i:q]
            j = q + 1
            while j < n:
                ch = src[j]
                if verbatim:
                    if ch == '"':
                        if j + 1 < n and src[j + 1] == '"':
                            j += 2
                            continue
                        break
                else:
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == '"' or ch == "\n":
                        break
                j += 1
            blank(q + 1, j)
            i = j + 1
        elif c == "'":
            if nxt == "\\":
                j = src.find("'", i + 3)
                j = -1 if j < 0 else j
            else:
                j = i + 2
            if 0 <= j < n and src[j] == "'":
                blank(i + 1, j)
                i = j + 1
            else:
                i += 1
        else:
            i += 1
    return "".join(out)


# A method-shaped member: at least one modifier, a return type, a name, a
# parameter list, then a block or an expression body. Matched on the MASKED
# text, so literals and comments cannot fake one. Constructors, properties
# and local functions without modifiers are deliberately not indexed — a site
# inside one reports the enclosing indexed member or "(file scope)".
_SIG = re.compile(
    r"(?<![\w.])(?:(?:public|private|protected|internal|static|override|virtual|sealed|async)\s+)+"
    r"[\w<>\[\],.?\s]+?\s+(\w+)\s*(?:<[^<>(){};]*>)?\s*\([^(){};]*\)\s*(?:where\b[^{;]*?)?(\{|=>)")


def _block_end(masked: str, open_brace: int) -> int:
    depth = 0
    for i in range(open_brace, len(masked)):
        c = masked[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(masked)


def method_index(src: str) -> list:
    """[(start, end, name)] for every method-shaped member of one source."""
    masked = _mask_cs(src)
    out = []
    for m in _SIG.finditer(masked):
        opener = m.end() - len(m.group(2))
        if m.group(2) == "{":
            end = _block_end(masked, opener)
        else:
            end = masked.find(";", opener)
            end = len(masked) if end < 0 else end + 1
        out.append((m.start(), end, m.group(1)))
    return out


def enclosing_method(methods: list, pos: int) -> str:
    """The innermost indexed member containing `pos`, else '(file scope)'."""
    best = None
    for start, end, name in methods:
        if start <= pos < end and (best is None or start > best[0]):
            best = (start, name)
    return best[1] if best else "(file scope)"


def _joined(values, cap: int = 3) -> str:
    vals = sorted(set(values))
    text = ", ".join(vals[:cap])
    if len(vals) > cap:
        text += f" +{len(vals) - cap}"
    return text


def build_registry(found: dict, sites: dict) -> dict:
    """The tools/i18n_source.json document. format 2 (Sept 6 item e) keeps
    "strings" exactly as format 1 wrote it — a flat sorted list, so every
    older reader (the sync tool's format-1 path, the seed migrations'
    PREREQUISITE notes, --diff) keeps working — and adds "contexts": one
    {surface, location, kind} record per key, each field the sorted distinct
    values joined with ", " and capped at three (a key used from thirty
    places would otherwise flood the 160-char column it is bound for).
    Deterministic: sorted keys, fixed field order."""
    entries = sorted(found.keys())
    contexts = {}
    for key in entries:
        recs = sites.get(key) or set()
        contexts[key] = {
            "surface": _joined(r[0] for r in recs),
            "location": _joined(r[1] for r in recs),
            "kind": _joined(r[2] for r in recs),
        }
    return {"format": 2, "strings": entries, "contexts": contexts}


def cs_escape(s: str) -> str:
    """One C# regular-string literal body for I18nSourceKeys.g.cs. Every
    remaining control character (the U+0004 context separator, in practice)
    becomes a \\uXXXX escape: a raw control byte in a generated .cs is legal
    but invisible, and an editor that "cleans" it would silently drop the
    key from the allowlist."""
    s = (s.replace("\\", "\\\\").replace('"', '\\"')
          .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
    return "".join(c if ord(c) >= 0x20 else "\\u%04x" % ord(c) for c in s)


def harvest_source(fn: str, src: str, found: dict, sites: dict) -> None:
    """Harvest ONE plugin source (LF-normalized text) into `found` and `sites`.

    `found[key]` accumulates the file names a key appears in — the contract
    this tool always had. `sites[key]` (Sept 6 item e) accumulates
    (surface, location, kind) tuples: the file stem, the enclosing method
    (enclosing_method — a heuristic; "(file scope)" when nothing indexed
    encloses the site) and the helper the string went through ("CreateText",
    "Tr", "TrC:card rarity", "table" for the initializer tables). They become
    the portal's context line, so a translator sees WHERE a string is used.
    Split out of extract() so a test can run it on a snippet.
    """
    stem = fn[:-3] if fn.endswith(".cs") else fn
    methods = method_index(src)

    def note(key, pos, kind):
        found.setdefault(key, []).append(fn)
        sites.setdefault(key, set()).add((stem, enclosing_method(methods, pos), kind))

    def note_table(key, ident):
        found.setdefault(key, []).append(fn)
        sites.setdefault(key, set()).add((stem, ident, "table"))

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
                    s = lf(s)
                    if looks_translatable(s, allow_braces=allow_braces):
                        note(s, m.start(), kind_of(m))
    # Contextual sites (Sept 6 item e): I18n.TrC("ctx", "text") and
    # I18n.TrCF("ctx", "fmt", ...). Position 0 is the CONTEXT, position 1 the
    # English; the emitted key is english + CTX_SEP + ctx, byte-for-byte the
    # composite I18n.TrC looks up. The plain English is recorded from the same
    # site: TrC falls back to Tr(english) on a miss, so that key is still read
    # here and converting a site retires nothing on the server. The context
    # must be ONE pure literal (context_literal raises otherwise): a key this
    # tool cannot harvest is a key no server pack can reach.
    for site_re, helper in CTX_SITES:
        for m in site_re.finditer(src):
            body = find_call_body(src, m.end() - 1)
            if not body:
                continue
            args = split_top_level_args(body)
            if len(args) < 2:
                raise ExtractError(f"{fn}: {helper}(context, text) needs two arguments, got ({body[:80]!r})")
            ctx = context_literal(args[0].strip(), fn, helper)
            for s in arg_literals(args[1].strip()):
                s = lf(s)
                if looks_translatable(s, allow_braces=True):
                    note(s + CTX_SEP + ctx, m.start(), f"{helper}:{ctx}")
                    note(s, m.start(), f"{helper} fallback")
    # QuickChat phrase table: the wire keys ARE the English sources.
    if fn == "QuickChat.cs":
        block = re.search(r"Phrases\s*=\s*\{(.*?)\};", src, re.S)
        if block:
            for x in STR_LIT.finditer(block.group(1)):
                s = lf(unescape(x.group(1)))
                if looks_translatable(s):
                    note_table(s, "Phrases")
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
                    s = lf(unescape(x.group(1)))
                    if looks_translatable(s):
                        note_table(s, "AchievementDefs")
    # Shop category descriptions (NativeUI.cs): the per-tab description
    # lives in a string-ARRAY initializer, never at a harvested call site
    # (both render sites pass SHOP_TAB_DESCS[i] through I18n.Tr —
    # Tr(variable) is invisible to call-site harvesting, #295a). Harvest
    # the initializer literals directly, the AchievementDefs pattern.
    # Impl-r2 I16 residual: these descs and the section headers had never
    # been translatable.
    if fn == "NativeUI.cs":
        block = re.search(r"SHOP_TAB_DESCS\s*=\s*\{(.*?)\n\s*\};", src, re.S)
        if block:
            for x in STR_LIT.finditer(block.group(1)):
                s = lf(unescape(x.group(1)))
                if looks_translatable(s):
                    note_table(s, "SHOP_TAB_DESCS")


def extract():
    found = {}
    sites = {}
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
            s = lf(s)
            if looks_translatable(s):
                found.setdefault(s, []).append("shop_strings.json")
                sites.setdefault(s, set()).add(("shop catalog", "cosmetic name/description", "shop"))
    except SystemExit:
        raise
    except Exception as ex:
        print(f"ERROR: shop_strings.json invalid ({ex})")
        sys.exit(1)
    for fn in FILES:
        path = os.path.join(PLUGIN, fn)
        if not os.path.exists(path):
            continue
        # newline="" = read the file's REAL bytes (no universal-newline
        # translation), then normalize explicitly. The old plain open() relied
        # on Python silently turning CRLF into LF, which is precisely the
        # implicit behaviour that let the client and the catalogue disagree
        # about verbatim literals — see the module docstring.
        src = lf(io.open(path, encoding="utf-8", newline="").read())
        harvest_source(fn, src, found, sites)
    return found, sites


def main():
    try:
        found, sites = extract()
    except ExtractError as ex:
        print(f"ERROR: {ex}")
        sys.exit(1)
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
    json.dump(build_registry(found, sites),
              io.open(OUT, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=1)
    total_chars = sum(len(s) for s in entries)
    print(f"extracted {len(entries)} distinct display strings "
          f"({total_chars} chars; {sum(1 for e in entries if CTX_SEP in e)} contextual) "
          f"-> {os.path.relpath(OUT, REPO)}")
    # Compiled source-key registry (round-3 find N5): the client's pack
    # allowlist must be the EXTRACTED source set, not the translated
    # dictionaries — an extracted-but-not-yet-translated key is exactly the
    # one a server correction needs to reach. Regenerate + rebuild whenever
    # extraction changes.
    cs = os.path.join(PLUGIN, "I18nSourceKeys.g.cs")
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
