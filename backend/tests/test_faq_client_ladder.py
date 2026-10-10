"""The FAQ refresh's client half: the three Info-library articles state what
the code enforces, and each corrected article is the key the translated game
renders.

The specification is docs/faq-refresh-client-contract.md on the FAQ server
lane, sections 1 and 2. On this lineage the client half landed whole in
63343169 (the three article edits, the extractor re-run, the four bundled
locales), and 2a67ec33 later corrected the same economy article again (the FFA
shutout tiers count the players who finished). This module holds the tree to
the contract from here on. Source-reading only: no database, no game, no
dotnet.

The binding is to the code a sentence describes, not to the sentence alone:
the gold ladder is compared with the payouts backend/api/main.py prices and
the labels ACHIEVEMENT_DEFS ships, tier by tier, so a re-priced, added or
renamed achievement turns a test red here instead of leaving the article
describing a ladder that no longer exists.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INFO = ROOT / "plugin" / "InfoLibrary.cs"
CATS = ROOT / "plugin" / "I18nCatalogues.cs"
SOURCE_KEYS = ROOT / "plugin" / "I18nSourceKeys.g.cs"
REGISTRY = ROOT / "tools" / "i18n_source.json"
MAIN = ROOT / "backend" / "api" / "main.py"

LOCALES = ("ES", "RU", "UK", "SV")

# The Info-library properties the contract corrects, by the property each
# article is held in.
ARTICLES = {
    "ranked 1v1 article": "Ranked1v1",
    "economy article": "Rewards",
    "cosmetics article": "Cosmetics",
}

# The contract's section 1, verbatim: (article, before, after). An "after" is
# a whole line of the article or a prefix of one; a "before" may survive
# nowhere.
TIER_500_BEFORE = ("- <color=#7FD4FF>500g</color> - Master (reach 1980), Tag Team Sweep, "
                   "Rise from the Ashes, Casual Conqueror, Twins!, Immortal, "
                   "Hostile Takeover, Bodycount.")
TIER_500_AFTER = ("- <color=#7FD4FF>500g</color> - Master (reach 1980), Tag Team Sweep, "
                  "Rise from the Ashes, Casual Conqueror, Twins!, Immortal, "
                  "Hostile Takeover, Bodycount, Sync Champion, Async Champion.")
TIER_300_BEFORE = ("- <color=#7FD4FF>300g</color> - Stacked Deck, Flawless, Silly Drill, "
                   "Into the Deep End, Century Club, Unstoppable, Party Crasher, "
                   "Heartbreak, Dragoman.")
TIER_300_AFTER = ("- <color=#7FD4FF>300g</color> - Stacked Deck, Flawless, Silly Drill, "
                  "Into the Deep End, Century Club, Unstoppable, Party Crasher, "
                  "Heartbreak, Dragoman, Sync Finalist, Async Finalist.")
CORRECTIONS = (
    ("ranked 1v1 article",
     "- If your opponent never arrives: a warning at 25 seconds, then an automatic return to the menu at 60.",
     "- If your opponent never arrives: a warning at 15 seconds, then an automatic return to the menu at 60."),
    ("economy article", TIER_500_BEFORE, TIER_500_AFTER),
    ("economy article", TIER_300_BEFORE, TIER_300_AFTER),
    ("cosmetics article",
     "- An artist (a role granted in-game) submits art from the Artist tab: a PNG or animated "
     "frames, positioned on a live on-body preview with slot, scale and offset.",
     "- An artist (a role granted in-game) submits art from the Artist tab: one 512x512 PNG, a GIF, "
     "or up to 16 numbered PNG frames, positioned on a live on-body preview with slot, scale and offset."),
)

# The four achievements the contract appends, each on the tier that pays it.
TOURNAMENT_ADDITIONS = {500: ("Sync Champion", "Async Champion"),
                        300: ("Sync Finalist", "Async Finalist")}

_TIER_LINE = re.compile(r"^- <color=#7FD4FF>(\d+)g</color> - (.+)$", re.M)


def _read(path):
    return path.read_text(encoding="utf-8")


def _verbatim_after(src, start):
    """The C# verbatim string body that begins at src[start] (just past @")."""
    out = []
    i = start
    while True:
        j = src.index('"', i)
        out.append(src[i:j])
        if src.startswith('""', j):
            out.append('"')
            i = j + 2
            continue
        return "".join(out)


def _cs_literal(body):
    """Decode a C# regular string literal body."""
    out = []
    i = 0
    simple = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "0": "\0"}
    while i < len(body):
        c = body[i]
        if c == "\\":
            n = body[i + 1]
            if n == "u":
                out.append(chr(int(body[i + 2:i + 6], 16)))
                i += 6
                continue
            assert n in simple, "unexpected escape \\%s in a catalogue literal" % n
            out.append(simple[n])
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def article_sources():
    """{article: English source} read out of InfoLibrary.cs's own literals."""
    src = _read(INFO)
    out = {}
    for name, prop in ARTICLES.items():
        decl = "private static string %s => I18n.Tr(@\"" % prop
        assert src.count(decl) == 1, "%s: %r occurs %d times in InfoLibrary.cs" % (
            name, decl, src.count(decl))
        out[name] = _verbatim_after(src, src.index(decl) + len(decl))
    return out


def catalogues():
    """{locale: {decoded key: decoded value}} for the four bundled catalogues,
    plus the number of entries per key (a duplicate key would not compile, but
    the count is what is asserted, not assumed)."""
    lines = _read(CATS).split("\n")
    starts = {}
    for i, line in enumerate(lines):
        m = re.match(r"\s*private static readonly Dictionary<string, string> (ES|RU|UK|SV) = ", line)
        if m:
            assert m.group(1) not in starts, "%s is declared twice" % m.group(1)
            starts[m.group(1)] = i
    assert sorted(starts) == sorted(LOCALES), "catalogues declared: %s" % sorted(starts)
    order = sorted(starts.items(), key=lambda kv: kv[1])
    entry = re.compile(r'^\s*\["((?:[^"\\]|\\.)*)"\]\s*=\s*"((?:[^"\\]|\\.)*)",?\s*$')
    out = {}
    for idx, (lang, first) in enumerate(order):
        last = order[idx + 1][1] if idx + 1 < len(order) else len(lines)
        table, counts = {}, {}
        for j in range(first, last):
            m = entry.match(lines[j])
            if m:
                k = _cs_literal(m.group(1))
                table[k] = _cs_literal(m.group(2))
                counts[k] = counts.get(k, 0) + 1
        assert len(table) > 1000, "%s: only %d entries parsed" % (lang, len(table))
        out[lang] = (table, counts)
    return out


def _gold_tables():
    body = _read(MAIN)
    default = int(re.search(r"^ACHIEVEMENT_GOLD = (\d+)$", body, re.M).group(1))
    start = body.index("ACHIEVEMENT_GOLD_OVERRIDES = {")
    block = body[start:body.index("\n}", start)]
    overrides = {k: int(v) for k, v in re.findall(r'"([a-z0-9_]+)":\s*(\d+)', block)}
    start = body.index("ACHIEVEMENT_DEFS = {")
    block = body[start:body.index("\n}", start)]
    names = dict(re.findall(r'"([a-z0-9_]+)":\s*\{"name":\s*"([^"]+)"', block))
    return default, overrides, names


def _tier_lines(article):
    out = {}
    for gold, members in _TIER_LINE.findall(article):
        assert int(gold) not in out, "the %sg tier is listed twice" % gold
        items = [re.sub(r"\s*\([^)]*\)\s*$", "", m.strip().rstrip(".")) for m in members.split(",")]
        out[int(gold)] = [m for m in items if m]
    return out


def test_every_paid_tier_line_lists_exactly_the_achievements_paid_at_it():
    """Membership in both directions, by the labels the server ships: a key
    priced at a tier and missing from its line, a label on a line whose key
    is paid something else, and a tier line for a payout nobody receives
    each fail. The article lists the 100g default by exclusion ("unless
    listed here"), so the default tier has no line."""
    default, overrides, names = _gold_tables()
    n_priced, n_defined = len(overrides), len(names)
    # 29 and 55 when this was written: a floor well under both, so a block
    # that moved or changed shape reads as a failure, not as an empty ladder.
    assert n_priced >= 25 and n_defined >= 50, (
        "parsed %d overrides and %d definitions: the blocks moved and this "
        "would be reading nothing" % (n_priced, n_defined))
    unnamed = sorted(k for k in overrides if k not in names)
    assert not unnamed, "priced but not defined: %s" % unnamed
    paid = {}
    for key, gold in overrides.items():
        if gold != default:
            paid.setdefault(gold, set()).add(names[key])
    tiers = _tier_lines(article_sources()["economy article"])
    assert sorted(tiers) == sorted(paid), (
        "the article lists tiers %s; the server pays %s above the default"
        % (sorted(tiers), sorted(paid)))
    for gold in sorted(paid):
        listed = tiers[gold]
        assert len(listed) == len(set(listed)), "the %dg line names an achievement twice" % gold
        missing = sorted(paid[gold] - set(listed))
        extra = sorted(set(listed) - paid[gold])
        assert not missing and not extra, (
            "the %dg line is not the %dg tier: paid there but not listed %s; "
            "listed but paid elsewhere or not an achievement label %s"
            % (gold, gold, missing, extra))


def test_the_corrected_lines_are_the_contracts_text_in_its_order():
    """Each correction's AFTER text, verbatim, exactly once in its article,
    and the two tier lines are whole lines (the contract appends the four
    tournament achievements after the existing members, in this order)."""
    sources = article_sources()
    for name, _before, after in CORRECTIONS:
        n = sources[name].count(after)
        assert n == 1, "%s carries the contract's corrected text %d times: %r" % (name, n, after)
    lines = sources["economy article"].split("\n")
    for after in (TIER_500_AFTER, TIER_300_AFTER):
        assert lines.count(after) == 1, "not a whole line of the economy article: %r" % after
    tiers = _tier_lines(sources["economy article"])
    for gold, added in TOURNAMENT_ADDITIONS.items():
        assert tuple(tiers[gold][-2:]) == added, (
            "the %dg line does not end with %s" % (gold, " then ".join(added)))


def test_no_predecessor_sentence_survives_in_any_artifact_the_game_renders_from():
    """A predecessor surviving in the registry or as a catalogue KEY is an
    article the extractor or a locale still serves under the old English."""
    sources = article_sources()
    registry = json.loads(_read(REGISTRY))["strings"]
    cats = catalogues()
    for name, before, _after in CORRECTIONS:
        assert before not in sources[name], "%s still carries %r" % (name, before)
        hits = [s[:60] for s in registry if before in s]
        assert not hits, "tools/i18n_source.json still registers the predecessor of %s" % name
        for lang, (table, _counts) in cats.items():
            keyed = [k[:60] for k in table if before in k]
            assert not keyed, "%s is keyed by a predecessor of %s: %s" % (lang, name, keyed)


def test_each_corrected_article_is_the_registered_key_in_every_bundled_locale():
    """The catalogue key IS the English source, so an article whose English
    moved without its key renders in English in all four locales. Each
    corrected article must be: one registry string, one entry of the
    generated allowlist, and one translated entry under exactly that key in
    ES, RU, UK and SV."""
    sources = article_sources()
    registry = json.loads(_read(REGISTRY))["strings"]
    allow = [_cs_literal(m) for m in re.findall(r'^\s*"((?:[^"\\]|\\.)*)",\s*$', _read(SOURCE_KEYS), re.M)]
    assert len(allow) > 1000, "only %d allowlist keys parsed" % len(allow)
    cats = catalogues()
    for name, english in sources.items():
        assert registry.count(english) == 1, (
            "%s: tools/i18n_source.json registers its English %d times"
            % (name, registry.count(english)))
        assert allow.count(english) == 1, (
            "%s: I18nSourceKeys.g.cs carries its English %d times — the "
            "generated allowlist and the registry disagree" % (name, allow.count(english)))
        for lang, (table, counts) in cats.items():
            assert counts.get(english, 0) == 1, (
                "%s: the %s catalogue has %d entries keyed by its English"
                % (name, lang, counts.get(english, 0)))
            value = table[english]
            assert value.strip() and value != english, (
                "%s: the %s entry is empty or untranslated" % (name, lang))


def test_each_locale_names_the_four_additions_by_its_own_label_for_them():
    """A re-keyed translation that kept its old meaning (#289) would carry the
    new key and the old ladder. Each locale's economy article must carry the
    English article's tiers, each with as many members, and end its 500g and
    300g lines with the labels that same catalogue gives the four tournament
    achievements, in the English order. Members are compared whole, never
    counted as substrings: a label inside a longer label would read as
    listed (#680)."""
    english = article_sources()["economy article"]
    en_tiers = _tier_lines(english)
    for lang, (table, _counts) in catalogues().items():
        tiers = _tier_lines(table[english])
        assert sorted(tiers) == sorted(en_tiers), (
            "%s's economy article lists tiers %s; the English lists %s"
            % (lang, sorted(tiers), sorted(en_tiers)))
        for gold in sorted(en_tiers):
            assert len(tiers[gold]) == len(en_tiers[gold]), (
                "%s's %dg line has %d members; the English one has %d"
                % (lang, gold, len(tiers[gold]), len(en_tiers[gold])))
        for gold, added in TOURNAMENT_ADDITIONS.items():
            local = tuple(table.get(label) for label in added)
            assert all(local), "%s has no catalogue label for one of %s" % (lang, " and ".join(added))
            assert tuple(tiers[gold][-len(added):]) == local, (
                "%s's %dg line does not end with its own labels for %s"
                % (lang, gold, " then ".join(added)))
